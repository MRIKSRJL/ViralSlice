import subprocess
from pathlib import Path

from app.pipeline.errors import FFmpegError


def run_command(cmd: list[str]) -> None:
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        tail = "\n".join(result.stderr.strip().splitlines()[-15:])
        raise FFmpegError(f"{Path(cmd[0]).name} a échoué (code {result.returncode}) : {tail}")


def probe_duration(path: Path, ffprobe: str = "ffprobe") -> float:
    cmd = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise FFmpegError(f"ffprobe n'a pas pu lire {path.name} : {result.stderr.strip()}")
    return float(result.stdout.strip())


def escape_filter_value(value: str) -> str:
    """Échappe une valeur d'option pour un filtergraph FFmpeg.

    Deux niveaux d'échappement sont nécessaires : celui des options de filtre
    (`\\`, `'`, `:`) puis celui du filtergraph (`\\`, `'`, `[`, `]`, `,`, `;`).
    """
    for char in ("\\", "'", ":"):
        value = value.replace(char, "\\" + char)
    for char in ("\\", "'", "[", "]", ",", ";"):
        value = value.replace(char, "\\" + char)
    return value
