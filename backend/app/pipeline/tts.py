import asyncio
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.pipeline.errors import PipelineError

OPENAI_TTS_INSTRUCTIONS = (
    "Voix off de créateur TikTok : énergique, rythmée, enthousiaste, articulation nette."
)


def synthesize_voiceover(
    text: str,
    output: Path,
    settings: Settings,
    provider: str,
    openai_client: Any = None,
) -> Path:
    """Génère la voix off en MP3 avec `provider` : "openai", "elevenlabs" ou "edge"."""
    output.parent.mkdir(parents=True, exist_ok=True)
    if provider == "edge":
        return _synthesize_edge(text, output, settings)
    if provider == "elevenlabs":
        return _synthesize_elevenlabs(text, output, settings)
    if openai_client is None:
        raise PipelineError("La voix off OpenAI exige un client OpenAI.")

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


def _synthesize_edge(text: str, output: Path, settings: Settings) -> Path:
    """edge-tts : voix neuronales Microsoft Edge, sans compte ni clé.

    Les voix « Multilingual » lisent le texte dans sa langue, quelle que soit leur locale.
    """
    import edge_tts

    async def _save() -> None:
        communicate = edge_tts.Communicate(
            text, settings.edge_tts_voice, rate=settings.edge_tts_rate
        )
        await communicate.save(str(output))

    try:
        asyncio.run(_save())
    except Exception as exc:
        raise PipelineError(f"Voix off edge-tts impossible : {exc}") from exc
    if not output.exists() or output.stat().st_size == 0:
        raise PipelineError("edge-tts n'a produit aucun audio.")
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
