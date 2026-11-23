from dataclasses import dataclass, field
from typing import Any, Literal

from app.core.config import Settings
from app.pipeline.errors import PipelineError

AIProviderName = Literal["openai", "groq"]
TTSProviderName = Literal["openai", "elevenlabs", "edge"]


class ProviderConfigError(PipelineError):
    pass


@dataclass(frozen=True)
class AIProfile:
    """Fournisseur IA résolu : transcription Whisper, LLM et voix off."""

    name: AIProviderName
    api_key: str
    base_url: str | None
    transcription_model: str
    llm_model: str
    tts_provider: TTSProviderName
    # Paramètres supplémentaires passés à chat.completions.create.
    llm_options: dict[str, Any] = field(default_factory=dict)
    # Taille maximale de la transcription envoyée au LLM (None = sans limite).
    max_transcript_chars: int | None = None


def resolve_ai_provider(settings: Settings) -> AIProviderName:
    """`AI_PROVIDER` si défini, sinon OpenAI si sa clé existe, sinon Groq (gratuit)."""
    if settings.ai_provider is not None:
        provider = settings.ai_provider
    elif settings.openai_api_key:
        provider = "openai"
    elif settings.groq_api_key:
        provider = "groq"
    else:
        raise ProviderConfigError(
            "Aucune clé IA configurée : renseignez GROQ_API_KEY (gratuit) ou OPENAI_API_KEY."
        )
    if provider == "openai" and not settings.openai_api_key:
        raise ProviderConfigError("AI_PROVIDER=openai exige OPENAI_API_KEY.")
    if provider == "groq" and not settings.groq_api_key:
        raise ProviderConfigError("AI_PROVIDER=groq exige GROQ_API_KEY.")
    return provider


def resolve_tts_provider(settings: Settings, ai_provider: AIProviderName) -> TTSProviderName:
    """`TTS_PROVIDER` si défini, sinon OpenAI TTS avec OpenAI et edge-tts (gratuit) avec Groq."""
    tts = settings.tts_provider or ("openai" if ai_provider == "openai" else "edge")
    if tts == "openai" and not settings.openai_api_key:
        raise ProviderConfigError("TTS_PROVIDER=openai exige OPENAI_API_KEY.")
    if tts == "elevenlabs" and not (settings.elevenlabs_api_key and settings.elevenlabs_voice_id):
        raise ProviderConfigError(
            "TTS_PROVIDER=elevenlabs exige ELEVENLABS_API_KEY et ELEVENLABS_VOICE_ID."
        )
    return tts


def resolve_ai_profile(settings: Settings) -> AIProfile:
    provider = resolve_ai_provider(settings)
    tts = resolve_tts_provider(settings, provider)
    if provider == "groq":
        options: dict[str, Any] = {}
        if settings.groq_reasoning_effort:
            options["reasoning_effort"] = settings.groq_reasoning_effort
        return AIProfile(
            name="groq",
            api_key=settings.groq_api_key,
            base_url=settings.groq_base_url,
            transcription_model=settings.groq_transcription_model,
            llm_model=settings.groq_llm_model,
            tts_provider=tts,
            llm_options=options,
            max_transcript_chars=settings.groq_max_transcript_chars,
        )
    return AIProfile(
        name="openai",
        api_key=settings.openai_api_key,
        base_url=None,
        transcription_model=settings.openai_transcription_model,
        llm_model=settings.openai_llm_model,
        tts_provider=tts,
    )


def create_ai_client(profile: AIProfile) -> Any:
    """Client OpenAI, pointé vers l'API compatible OpenAI de Groq si besoin."""
    from openai import OpenAI

    return OpenAI(api_key=profile.api_key, base_url=profile.base_url, max_retries=3)


def create_openai_tts_client(settings: Settings) -> Any:
    from openai import OpenAI

    return OpenAI(api_key=settings.openai_api_key, max_retries=3)
