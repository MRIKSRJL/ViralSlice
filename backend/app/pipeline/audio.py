from pathlib import Path

from app.pipeline.ffmpeg_utils import probe_duration, run_command


def build_extract_audio_command(ffmpeg: str, source: Path, output: Path) -> list[str]:
    """Audio mono 16 kHz en MP3 64 kb/s : environ 0,5 Mo par minute pour l'API Whisper."""
    return [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-vn", "-ac", "1", "-ar", "16000", "-c:a", "libmp3lame", "-b:a", "64k",
        str(output),
    ]  # fmt: skip


def build_split_audio_command(
    ffmpeg: str, source: Path, pattern: Path, chunk_seconds: int
) -> list[str]:
    return [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-i", str(source),
        "-f", "segment", "-segment_time", str(chunk_seconds), "-c", "copy",
        str(pattern),
    ]  # fmt: skip


def extract_audio(ffmpeg: str, source: Path, output: Path) -> Path:
    run_command(build_extract_audio_command(ffmpeg, source, output))
    return output


def split_audio_if_needed(
    ffmpeg: str,
    ffprobe: str,
    audio: Path,
    max_bytes: int,
    chunk_seconds: int,
) -> list[tuple[Path, float]]:
    """Découpe l'audio en morceaux acceptés par l'API Whisper.

    Retourne des couples (fichier, décalage en secondes depuis le début de la source).
    """
    if audio.stat().st_size <= max_bytes:
        return [(audio, 0.0)]
    chunk_dir = audio.parent / "audio_chunks"
    chunk_dir.mkdir(exist_ok=True)
    run_command(
        build_split_audio_command(ffmpeg, audio, chunk_dir / "chunk_%03d.mp3", chunk_seconds)
    )
    chunks: list[tuple[Path, float]] = []
    offset = 0.0
    for chunk in sorted(chunk_dir.glob("chunk_*.mp3")):
        chunks.append((chunk, offset))
        offset += probe_duration(chunk, ffprobe)
    return chunks
