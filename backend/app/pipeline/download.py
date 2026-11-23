from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.pipeline.errors import PipelineError

SUPPORTED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "twitch.tv",
    "www.twitch.tv",
    "m.twitch.tv",
    "clips.twitch.tv",
}


@dataclass(frozen=True)
class DownloadedVideo:
    path: Path
    title: str
    duration: float


def is_supported_url(url: str) -> bool:
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in SUPPORTED_HOSTS


def build_ydl_options(dest_dir: Path, cookies_file: Path | None = None) -> dict[str, Any]:
    options: dict[str, Any] = {
        "format": "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b",
        "merge_output_format": "mp4",
        "outtmpl": str(dest_dir / "source.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
    }
    # YouTube exige souvent des cookies depuis les IP de serveurs (« Sign in to confirm you're not a bot »).
    if cookies_file is not None:
        options["cookiefile"] = str(cookies_file)
    return options


def download_video(
    url: str, dest_dir: Path, max_duration_seconds: int, cookies_file: Path | None = None
) -> DownloadedVideo:
    """Télécharge la vidéo (1080p max) dans `dest_dir` après vérification de ses métadonnées."""
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError

    try:
        with YoutubeDL(build_ydl_options(dest_dir, cookies_file)) as ydl:
            info = ydl.extract_info(url, download=False)
            if info.get("is_live"):
                raise PipelineError("Les diffusions en direct ne sont pas prises en charge.")
            duration = float(info.get("duration") or 0)
            if duration > max_duration_seconds:
                raise PipelineError(
                    f"La vidéo dure {duration / 60:.0f} min, la limite est de "
                    f"{max_duration_seconds / 60:.0f} min."
                )
            info = ydl.process_ie_result(info, download=True)
    except DownloadError as exc:
        raise PipelineError(f"Téléchargement impossible : {exc}") from exc

    candidates = sorted(dest_dir.glob("source.*"))
    video_path = dest_dir / "source.mp4"
    if not video_path.exists():
        if not candidates:
            raise PipelineError("yt-dlp n'a produit aucun fichier vidéo.")
        video_path = candidates[0]
    return DownloadedVideo(
        path=video_path,
        title=str(info.get("title") or ""),
        duration=float(info.get("duration") or 0),
    )
