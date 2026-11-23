import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import ClassVar

import pytest

from app.core.config import Settings
from app.pipeline.errors import PipelineError
from app.pipeline.tts import synthesize_voiceover


class FakeCommunicate:
    calls: ClassVar[list[tuple]] = []

    def __init__(self, text, voice, rate):
        FakeCommunicate.calls.append((text, voice, rate))

    async def save(self, path):
        Path(path).write_bytes(b"ID3fake")


@pytest.fixture
def fake_edge(monkeypatch):
    module = ModuleType("edge_tts")
    module.Communicate = FakeCommunicate
    FakeCommunicate.calls = []
    monkeypatch.setitem(sys.modules, "edge_tts", module)
    return FakeCommunicate


def test_edge_tts_needs_no_key(tmp_path, fake_edge):
    out = synthesize_voiceover(
        "Regardez bien !", tmp_path / "vo.mp3", Settings(_env_file=None), "edge"
    )
    assert out.read_bytes() == b"ID3fake"
    assert fake_edge.calls == [("Regardez bien !", "fr-FR-RemyMultilingualNeural", "+8%")]


def test_edge_tts_errors_become_pipeline_errors(tmp_path, monkeypatch):
    class Broken(FakeCommunicate):
        async def save(self, path):
            raise ConnectionError("hors ligne")

    module = ModuleType("edge_tts")
    module.Communicate = Broken
    monkeypatch.setitem(sys.modules, "edge_tts", module)
    with pytest.raises(PipelineError, match="edge-tts"):
        synthesize_voiceover("x", tmp_path / "vo.mp3", Settings(_env_file=None), "edge")


def test_openai_tts_uses_given_client(tmp_path):
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(write_to_file=lambda path: path.write_bytes(b"mp3"))

    client = SimpleNamespace(audio=SimpleNamespace(speech=SimpleNamespace(create=create)))
    synthesize_voiceover("Salut", tmp_path / "vo.mp3", Settings(_env_file=None), "openai", client)
    assert calls[0]["model"] == "gpt-4o-mini-tts" and calls[0]["input"] == "Salut"
    with pytest.raises(PipelineError):
        synthesize_voiceover("Salut", tmp_path / "vo2.mp3", Settings(_env_file=None), "openai")
