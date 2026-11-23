from pathlib import Path

import pytest

from app.pipeline.download import build_ydl_options, is_supported_url


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=abc",
        "https://youtu.be/abc",
        "https://m.youtube.com/shorts/abc",
        "https://www.twitch.tv/videos/123",
        "https://clips.twitch.tv/SomeClip",
    ],
)
def test_supported_urls(url):
    assert is_supported_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://vimeo.com/1",
        "ftp://youtube.com/x",
        "https://youtube.com.evil.io/x",
        "youtube.com/watch",
    ],
)
def test_unsupported_urls(url):
    assert not is_supported_url(url)


def test_ydl_options_cap_resolution_and_output_mp4():
    options = build_ydl_options(Path("/tmp/job"))
    assert "height<=1080" in options["format"]
    assert options["merge_output_format"] == "mp4"
    assert options["outtmpl"] == "/tmp/job/source.%(ext)s"
    assert options["noplaylist"] is True
    assert "cookiefile" not in options
    assert build_ydl_options(Path("/tmp/job"), Path("/c.txt"))["cookiefile"] == "/c.txt"
