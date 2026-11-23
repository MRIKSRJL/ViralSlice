import logging
import tempfile
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.core.providers import (
    AIProfile,
    create_ai_client,
    create_openai_tts_client,
    resolve_ai_profile,
)
from app.jobs.store import InMemoryJobStore
from app.models.schemas import ClipResult, CommentaryMode, JobStatus, ViralMoment, Word
from app.pipeline import download
from app.pipeline.audio import extract_audio, split_audio_if_needed
from app.pipeline.editing import build_render_command
from app.pipeline.errors import PipelineError
from app.pipeline.ffmpeg_utils import run_command
from app.pipeline.moments import detect_viral_moments
from app.pipeline.subtitles import SubtitleStyle, write_ass
from app.pipeline.timeline import clip_words, merge_voiceover_words
from app.pipeline.transcription import transcribe_chunks, transcribe_words
from app.pipeline.tts import synthesize_voiceover

logger = logging.getLogger(__name__)


def clip_download_url(job_id: str, index: int) -> str:
    return f"/api/jobs/{job_id}/clips/{index}"


def render_clip(
    *,
    job_id: str,
    index: int,
    moment: ViralMoment,
    source: Path,
    words: list[Word],
    work_dir: Path,
    output_dir: Path,
    settings: Settings,
    profile: AIProfile,
    client: Any,
    tts_client: Any,
) -> ClipResult:
    clip_dir = work_dir / f"clip_{index}"
    clip_dir.mkdir(parents=True, exist_ok=True)
    duration = moment.end - moment.start
    subtitle_words = clip_words(words, moment.start, moment.end)

    voiceover: Path | None = None
    if moment.needs_commentary and moment.commentary_script:
        voiceover = synthesize_voiceover(
            moment.commentary_script,
            clip_dir / "voiceover.mp3",
            settings,
            profile.tts_provider,
            tts_client,
        )
        vo_words = transcribe_words(client, voiceover, profile.transcription_model)
        subtitle_words = merge_voiceover_words(subtitle_words, vo_words, duration)

    style = SubtitleStyle(font_name=settings.subtitle_font)
    ass_path = write_ass(clip_dir / "subtitles.ass", subtitle_words, style, duration)

    filename = f"clip_{index}.mp4"
    output = output_dir / filename
    run_command(
        build_render_command(
            ffmpeg=settings.ffmpeg_binary,
            source=source,
            start=moment.start,
            duration=duration,
            ass_path=ass_path,
            output=output,
            voiceover=voiceover,
            original_volume=settings.original_volume_with_voiceover,
            fonts_dir=settings.fonts_dir,
            preset=settings.video_preset,
            crf=settings.video_crf,
        )
    )
    return ClipResult(
        index=index,
        start=moment.start,
        end=moment.end,
        title=moment.title,
        reason=moment.reason,
        needs_commentary=moment.needs_commentary,
        commentary_script=moment.commentary_script,
        has_voiceover=voiceover is not None,
        filename=filename,
        download_url=clip_download_url(job_id, index),
    )


def run_pipeline(
    job_id: str,
    url: str,
    commentary_mode: CommentaryMode,
    store: InMemoryJobStore,
    settings: Settings,
    client: Any | None = None,
) -> None:
    """Exécute le pipeline complet d'un job et met à jour son état à chaque étape."""
    output_dir = settings.media_root / job_id
    try:
        profile = resolve_ai_profile(settings)
        client = client or create_ai_client(profile)
        tts_client = None
        if profile.tts_provider == "openai":
            tts_client = client if profile.name == "openai" else create_openai_tts_client(settings)
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"viralslice-{job_id}-") as tmp:
            work_dir = Path(tmp)

            store.update(job_id, status=JobStatus.DOWNLOADING, progress=5)
            video = download.download_video(
                url, work_dir, settings.max_source_duration_seconds, settings.ytdlp_cookies_file
            )

            store.update(
                job_id,
                status=JobStatus.TRANSCRIBING,
                progress=20,
                source_title=video.title,
                source_duration=video.duration,
            )
            audio = extract_audio(settings.ffmpeg_binary, video.path, work_dir / "audio.mp3")
            chunks = split_audio_if_needed(
                settings.ffmpeg_binary,
                settings.ffprobe_binary,
                audio,
                settings.whisper_max_upload_bytes,
                settings.whisper_chunk_seconds,
            )
            words = transcribe_chunks(client, chunks, profile.transcription_model)
            if not words:
                raise PipelineError("Aucune parole détectée dans la vidéo.")

            store.update(job_id, status=JobStatus.DETECTING_MOMENTS, progress=35)
            moments = detect_viral_moments(
                client,
                profile.llm_model,
                words,
                video.duration,
                commentary_mode,
                llm_options=profile.llm_options,
                max_transcript_chars=profile.max_transcript_chars,
            )

            store.update(job_id, status=JobStatus.RENDERING, progress=45, moments=moments)
            clips: list[ClipResult] = []
            for i, moment in enumerate(moments, start=1):
                clips.append(
                    render_clip(
                        job_id=job_id,
                        index=i,
                        moment=moment,
                        source=video.path,
                        words=words,
                        work_dir=work_dir,
                        output_dir=output_dir,
                        settings=settings,
                        profile=profile,
                        client=client,
                        tts_client=tts_client,
                    )
                )
                store.update(job_id, progress=45 + round(55 * i / len(moments)), clips=clips)

        store.update(job_id, status=JobStatus.COMPLETED, progress=100)
    except PipelineError as exc:
        logger.warning("Job %s en échec : %s", job_id, exc)
        store.update(job_id, status=JobStatus.FAILED, error=str(exc))
    except Exception as exc:
        logger.exception("Job %s : erreur inattendue", job_id)
        store.update(
            job_id, status=JobStatus.FAILED, error=f"Erreur interne ({type(exc).__name__}) : {exc}"
        )
