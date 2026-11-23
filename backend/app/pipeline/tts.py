from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.pipeline.errors import PipelineError

OPENAI_TTS_INSTRUCTIONS = (
    "Voix off de créateur TikTok : énergique, rythmée, enthousiaste, articulation nette."
)


def synthesize_voiceover(text: str, output: Path, settings: Settings, openai_client: Any) -> Path:
    """Génère la voix off en MP3 avec le fournisseur configuré (`TTS_PROVIDER`)."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if settings.tts_provider == "elevenlabs":
        return _synthesize_elevenlabs(text, output, settings)

    params: dict[str, Any] = {
        "model": settings.openai_tts_model,
        "voice": settings.openai_tts_voice,
        "input": text,
        "response_format": "mp3",
    }
    if settings.openai_tts_model.startswith("gpt-4o"):
        params["instructions"] = OPENAI_TTS_INSTRUCTIONS
    response = openai_client.audio.speech.create(**params)
    response.write_to_file(output)
    return output


def _synthesize_elevenlabs(text: str, output: Path, settings: Settings) -> Path:
    if not settings.elevenlabs_api_key or not settings.elevenlabs_voice_id:
        raise PipelineError(
            "ELEVENLABS_API_KEY et ELEVENLABS_VOICE_ID sont requis avec TTS_PROVIDER=elevenlabs."
        )
    from elevenlabs.client import ElevenLabs

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    audio = client.text_to_speech.convert(
        settings.elevenlabs_voice_id,
        text=text,
        model_id=settings.elevenlabs_model_id,
        output_format="mp3_44100_128",
    )
    with output.open("wb") as handle:
        for chunk in audio:
            handle.write(chunk)
    return output
