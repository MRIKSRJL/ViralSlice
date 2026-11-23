from pathlib import Path

from app.pipeline.audio import build_extract_audio_command
from app.pipeline.editing import build_ass_filter, build_render_command
from app.pipeline.ffmpeg_utils import escape_filter_value


def _arg(cmd: list[str], flag: str) -> str:
    return cmd[cmd.index(flag) + 1]


def _all_args(cmd: list[str], flag: str) -> list[str]:
    return [cmd[i + 1] for i, value in enumerate(cmd) if value == flag]


def test_escape_filter_value_handles_special_characters():
    assert escape_filter_value("/tmp/a b/subs.ass") == "/tmp/a b/subs.ass"
    assert escape_filter_value("/tmp/a:b/x.ass") == "/tmp/a\\\\:b/x.ass"
    assert escape_filter_value("/tmp/a,b") == "/tmp/a\\,b"


def test_ass_filter_with_fonts_dir():
    assert build_ass_filter(Path("/w/s.ass")) == "ass=filename=/w/s.ass"
    assert (
        build_ass_filter(Path("/w/s.ass"), Path("/fonts"))
        == "ass=filename=/w/s.ass:fontsdir=/fonts"
    )


def test_render_without_voiceover_keeps_original_audio():
    cmd = build_render_command(
        ffmpeg="ffmpeg",
        source=Path("/w/source.mp4"),
        start=12.5,
        duration=42.25,
        ass_path=Path("/w/subs.ass"),
        output=Path("/out/clip_1.mp4"),
    )
    assert _arg(cmd, "-ss") == "12.500"
    assert _arg(cmd, "-t") == "42.250"
    assert _all_args(cmd, "-i") == ["/w/source.mp4"]
    graph = _arg(cmd, "-filter_complex")
    assert graph.startswith("[0:v]crop='min(iw,ih*9/16)':'min(ih,iw*16/9)',scale=1080:1920")
    assert graph.endswith("ass=filename=/w/subs.ass[v]")
    assert "volume" not in graph and "amix" not in graph
    assert _all_args(cmd, "-map") == ["[v]", "0:a:0?"]
    assert cmd.index("-ss") < cmd.index("-i")
    assert cmd[-1] == "/out/clip_1.mp4"


def test_render_with_voiceover_ducks_original_audio():
    cmd = build_render_command(
        ffmpeg="ffmpeg",
        source=Path("/w/source.mp4"),
        start=0,
        duration=30,
        ass_path=Path("/w/subs.ass"),
        output=Path("/out/clip_1.mp4"),
        voiceover=Path("/w/vo.mp3"),
        original_volume=0.22,
        preset="ultrafast",
    )
    assert _all_args(cmd, "-i") == ["/w/source.mp4", "/w/vo.mp3"]
    graph = _arg(cmd, "-filter_complex")
    assert "[0:a]volume=0.22[orig]" in graph
    assert "[1:a]volume=1.0,apad[vo]" in graph
    assert "amix=inputs=2:duration=first" in graph and "normalize=0" in graph
    assert _all_args(cmd, "-map") == ["[v]", "[a]"]
    assert _arg(cmd, "-preset") == "ultrafast"
    assert _arg(cmd, "-c:v") == "libx264" and _arg(cmd, "-pix_fmt") == "yuv420p"


def test_extract_audio_command_targets_whisper_friendly_mp3():
    cmd = build_extract_audio_command("ffmpeg", Path("/w/s.mp4"), Path("/w/a.mp3"))
    assert _arg(cmd, "-ac") == "1" and _arg(cmd, "-ar") == "16000" and "-vn" in cmd
