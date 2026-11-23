from pathlib import Path

from app.pipeline.ffmpeg_utils import escape_filter_value

OUTPUT_WIDTH = 1080
OUTPUT_HEIGHT = 1920

# Recadrage centré au ratio 9:16 (quelle que soit l'orientation de la source), puis mise à l'échelle.
CROP_9_16_FILTER = (
    "crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',"
    f"scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT}:flags=lanczos,setsar=1,fps=30"
)


def build_ass_filter(ass_path: Path, fonts_dir: Path | None = None) -> str:
    value = f"ass=filename={escape_filter_value(str(ass_path))}"
    if fonts_dir is not None:
        value += f":fontsdir={escape_filter_value(str(fonts_dir))}"
    return value


def build_render_command(
    *,
    ffmpeg: str,
    source: Path,
    start: float,
    duration: float,
    ass_path: Path,
    output: Path,
    voiceover: Path | None = None,
    original_volume: float = 0.22,
    fonts_dir: Path | None = None,
    preset: str = "medium",
    crf: int = 20,
) -> list[str]:
    """Commande FFmpeg d'un clip : découpe, recadrage 9:16, sous-titres incrustés et mixage.

    Avec voix off, l'original est ramené à `original_volume` et la voix off reste à 100 % ;
    sans voix off, l'audio original est conservé tel quel.
    """
    cmd = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(source),
    ]  # fmt: skip
    filters = [f"[0:v]{CROP_9_16_FILTER},{build_ass_filter(ass_path, fonts_dir)}[v]"]
    if voiceover is not None:
        cmd += ["-i", str(voiceover)]
        filters.append(
            f"[0:a]volume={original_volume}[orig];"
            "[1:a]volume=1.0,apad[vo];"
            "[orig][vo]amix=inputs=2:duration=first:dropout_transition=0:normalize=0,"
            "alimiter=limit=0.95[a]"
        )
        audio_map = "[a]"
    else:
        audio_map = "0:a:0?"
    cmd += [
        "-filter_complex", ";".join(filters),
        "-map", "[v]", "-map", audio_map,
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
        "-movflags", "+faststart",
        str(output),
    ]  # fmt: skip
    return cmd
