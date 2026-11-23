import pytest

from app.core.config import Settings
from app.core.providers import (
    ProviderConfigError,
    create_ai_client,
    resolve_ai_profile,
)


def settings(**overrides) -> Settings:
    base = {"openai_api_key": "", "groq_api_key": "", "_env_file": None}
    return Settings(**{**base, **overrides})


def test_groq_key_alone_selects_free_path():
    profile = resolve_ai_profile(settings(groq_api_key="gsk_test"))
    assert profile.name == "groq"
    assert profile.base_url == "https://api.groq.com/openai/v1"
    assert profile.transcription_model == "whisper-large-v3-turbo"
    assert profile.llm_model == "openai/gpt-oss-120b"
    assert profile.tts_provider == "edge"
    assert profile.llm_options == {"reasoning_effort": "low"}
    assert profile.max_transcript_chars == 14_000


def test_openai_key_keeps_existing_path():
    profile = resolve_ai_profile(settings(openai_api_key="sk-test", groq_api_key="gsk_test"))
    assert profile.name == "openai"
    assert profile.base_url is None
    assert (profile.transcription_model, profile.llm_model) == ("whisper-1", "gpt-4o")
    assert profile.tts_provider == "openai"
    assert profile.llm_options == {}
    assert profile.max_transcript_chars is None


def test_ai_provider_override_wins():
    profile = resolve_ai_profile(
        settings(ai_provider="groq", openai_api_key="sk-test", groq_api_key="gsk_test")
    )
    assert profile.name == "groq"
    assert profile.tts_provider == "edge"


@pytest.mark.parametrize(
    "overrides",
    [
        {},
        {"ai_provider": "openai", "groq_api_key": "gsk_test"},
        {"ai_provider": "groq", "openai_api_key": "sk-test"},
        {"groq_api_key": "gsk_test", "tts_provider": "openai"},
        {"groq_api_key": "gsk_test", "tts_provider": "elevenlabs"},
    ],
)
def test_misconfiguration_is_reported(overrides):
    with pytest.raises(ProviderConfigError):
        resolve_ai_profile(settings(**overrides))


def test_elevenlabs_stays_optional_on_groq_path():
    profile = resolve_ai_profile(
        settings(
            groq_api_key="gsk_test",
            tts_provider="elevenlabs",
            elevenlabs_api_key="el",
            elevenlabs_voice_id="voice",
        )
    )
    assert profile.tts_provider == "elevenlabs"


def test_empty_env_values_mean_automatic(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "")
    monkeypatch.setenv("TTS_PROVIDER", "")
    monkeypatch.setenv("GROQ_REASONING_EFFORT", "")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    profile = resolve_ai_profile(Settings(_env_file=None))
    assert profile.name == "groq"
    assert profile.tts_provider == "edge"
    assert profile.llm_options == {}


def test_example_env_file_defaults_to_groq_once_key_is_set(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    profile = resolve_ai_profile(Settings(_env_file=".env.example"))
    assert profile.name == "groq" and profile.tts_provider == "edge"


def test_groq_client_targets_groq_endpoint():
    client = create_ai_client(resolve_ai_profile(settings(groq_api_key="gsk_test")))
    assert str(client.base_url).startswith("https://api.groq.com/openai/v1")
    assert client.api_key == "gsk_test"
