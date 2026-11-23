from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    cors_origins: str = "http://localhost:3000"

    # Vide = automatique : OpenAI si OPENAI_API_KEY est renseignée, sinon Groq.
    ai_provider: Literal["openai", "groq"] | None = None

    openai_api_key: str = ""
    openai_llm_model: str = "gpt-4o"
    openai_transcription_model: str = "whisper-1"
    openai_tts_model: str = "gpt-4o-mini-tts"
    openai_tts_voice: str = "alloy"

    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    groq_llm_model: str = "openai/gpt-oss-120b"
    groq_transcription_model: str = "whisper-large-v3-turbo"
    groq_reasoning_effort: Literal["low", "medium", "high"] | None = "low"
    # L'offre gratuite de Groq limite gpt-oss à 8 000 tokens par minute (prompt + réponse).
    groq_max_transcript_chars: int = 14_000

    # Vide = automatique : "openai" avec OpenAI, "edge" (edge-tts, gratuit) avec Groq.
    tts_provider: Literal["openai", "elevenlabs", "edge"] | None = None
    edge_tts_voice: str = "fr-FR-RemyMultilingualNeural"
    edge_tts_rate: str = "+8%"
    elevenlabs_api_key: str = ""
    elevenlabs_voice_id: str = ""
    elevenlabs_model_id: str = "eleven_multilingual_v2"

    media_root: Path = Path("./media")
    max_source_duration_seconds: int = 3600
    ytdlp_cookies_file: Path | None = None

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    video_preset: str = "medium"
    video_crf: int = 20

    subtitle_font: str = "Montserrat"
    fonts_dir: Path | None = None

    # Volume de l'audio original quand une voix off est présente (20 à 25 %).
    original_volume_with_voiceover: float = Field(default=0.22, ge=0.20, le=0.25)

    # L'API Whisper refuse les fichiers de plus de 25 Mo.
    whisper_max_upload_bytes: int = 24 * 1024 * 1024
    whisper_chunk_seconds: int = 1200

    @field_validator(
        "ytdlp_cookies_file",
        "fonts_dir",
        "ai_provider",
        "tts_provider",
        "groq_reasoning_effort",
        mode="before",
    )
    @classmethod
    def _empty_is_none(cls, value: object) -> object:
        return None if value == "" else value

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
