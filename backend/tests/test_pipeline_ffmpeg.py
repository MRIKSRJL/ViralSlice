"""Tests d'intégration : FFmpeg réel, API OpenAI et yt-dlp remplacés par des doublures."""

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.core.config import Settings
from app.jobs.store import InMemoryJobStore
from app.models.schemas import CommentaryMode, JobStatus, Word
from app.pipeline import download, runner
from app.pipeline.download import DownloadedVideo
from app.pipeline.editing import build_render_command
from app.pipeline.ffmpeg_utils import probe_duration, run_command
from app.pipeline.subtitles import write_ass

pytestmark = [
    pytest.mark.ffmpeg,
    pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="FFmpeg non installé"),
]

SOURCE_SECONDS = 95


def make_source(path: Path, seconds: int = SOURCE_SECONDS) -> Path:
    run_command([
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", f"testsrc2=size=1280x720:rate=30:duration={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=220:duration={seconds}",
        "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac", "-shortest", str(path),
    ])  # fmt: skip
    return path


def probe_stream(path: Path, stream: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", stream, "-show_entries",
         "stream=width,height,codec_name,sample_rate", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    streams = json.loads(out)["streams"]
    return streams[0] if streams else {}


def mean_volume(path: Path, start: float, duration: float) -> float:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-ss", str(start), "-t", str(duration), "-i", str(path),
         "-af", "volumedetect", "-vn", "-f", "null", "-"],
        capture_output=True, text=True, check=False,
    )  # fmt: skip
    line = next(x for x in result.stderr.splitlines() if "mean_volume" in x)
    return float(line.split("mean_volume:")[1].split("dB")[0])


class FakeOpenAI:
    def __init__(self, moments_payload: dict):
        self.transcription_calls: list[dict] = []
        self.moments_payload = moments_payload
        self.audio = SimpleNamespace(
            transcriptions=SimpleNamespace(create=self._transcribe),
            speech=SimpleNamespace(create=self._speech),
        )
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self._chat))

    def _transcribe(self, *, file, **kwargs):
        self.transcription_calls.append({"name": Path(file.name).name, **kwargs})
        if Path(file.name).name == "voiceover.mp3":
            words = [{"word": t, "start": i * 0.5, "end": i * 0.5 + 0.4}
                     for i, t in enumerate(["Attendez", "de", "voir", "la", "suite"])]  # fmt: skip
        else:
            words = [{"word": f"mot{i}", "start": i * 0.5, "end": i * 0.5 + 0.4}
                     for i in range(SOURCE_SECONDS * 2)]  # fmt: skip
        return SimpleNamespace(text="", words=[SimpleNamespace(**w) for w in words])

    def _chat(self, **kwargs):
        content = json.dumps(self.moments_payload)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])

    def _speech(self, **kwargs):
        def write_to_file(path):
            run_command([
                "ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                "-i", "sine=frequency=880:duration=4", "-c:a", "libmp3lame", str(path),
            ])  # fmt: skip

        return SimpleNamespace(write_to_file=write_to_file)


def test_full_pipeline_renders_vertical_clips(tmp_path, monkeypatch):
    source = make_source(tmp_path / "source.mp4")

    def fake_download(url, dest_dir, max_duration_seconds, cookies_file=None):
        target = Path(dest_dir) / "source.mp4"
        shutil.copy(source, target)
        return DownloadedVideo(path=target, title="Vidéo test", duration=SOURCE_SECONDS)

    monkeypatch.setattr(download, "download_video", fake_download)
    fake = FakeOpenAI({
        "moments": [
            {"start": 0, "end": 30, "title": "A", "reason": "r", "needs_commentary": True,
             "commentary_script": "Attendez de voir la suite"},
            {"start": 32, "end": 62, "title": "B", "reason": "r", "needs_commentary": False,
             "commentary_script": None},
            {"start": 64, "end": 94, "title": "C", "reason": "r", "needs_commentary": False,
             "commentary_script": None},
        ]
    })  # fmt: skip
    settings = Settings(
        openai_api_key="test", media_root=tmp_path / "media", video_preset="ultrafast"
    )
    store = InMemoryJobStore()
    job = store.create("https://youtu.be/abc", CommentaryMode.AUTO)

    runner.run_pipeline(job.job_id, job.url, CommentaryMode.AUTO, store, settings, client=fake)

    state = store.get(job.job_id)
    assert state.error is None
    assert state.status is JobStatus.COMPLETED and state.progress == 100
    assert [c.has_voiceover for c in state.clips] == [True, False, False]
    assert all(c["timestamp_granularities"] == ["word"] for c in fake.transcription_calls)
    assert [c["name"] for c in fake.transcription_calls] == ["audio.mp3", "voiceover.mp3"]

    for clip in state.clips:
        path = settings.media_root / job.job_id / clip.filename
        video = probe_stream(path, "v:0")
        assert (video["width"], video["height"]) == (1080, 1920)
        assert probe_stream(path, "a:0")["codec_name"] == "aac"
        assert abs(probe_duration(path) - 30) < 0.2

    # L'original est atténué pendant la voix off (clip 1) mais pas dans le clip 2.
    clip1 = settings.media_root / job.job_id / "clip_1.mp4"
    clip2 = settings.media_root / job.job_id / "clip_2.mp4"
    assert mean_volume(clip1, 10, 5) < mean_volume(clip2, 10, 5) - 10


def test_pipeline_failure_is_reported_on_job(tmp_path, monkeypatch):
    def failing_download(*args):
        raise download.PipelineError("Téléchargement impossible : vidéo privée")

    monkeypatch.setattr(download, "download_video", failing_download)
    store = InMemoryJobStore()
    job = store.create("https://youtu.be/abc", CommentaryMode.NEVER)
    settings = Settings(openai_api_key="test", media_root=tmp_path)
    runner.run_pipeline(job.job_id, job.url, CommentaryMode.NEVER, store, settings, client=object())
    state = store.get(job.job_id)
    assert state.status is JobStatus.FAILED
    assert state.error == "Téléchargement impossible : vidéo privée"


def test_subtitles_burn_with_special_characters_in_path(tmp_path):
    weird = tmp_path / "dossier: bizarre, [x]"
    weird.mkdir()
    source = make_source(weird / "source.mp4", seconds=3)
    ass = write_ass(
        weird / "sous-titres.ass", [Word(text="Salut", start=0, end=1)], clip_duration=2
    )
    output = weird / "out.mp4"
    run_command(build_render_command(
        ffmpeg="ffmpeg", source=source, start=0.5, duration=2, ass_path=ass,
        output=output, preset="ultrafast", fonts_dir=weird,
    ))  # fmt: skip
    assert probe_stream(output, "v:0")["height"] == 1920
