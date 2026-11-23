from pathlib import Path
from typing import Any

from app.models.schemas import Word


def _field(obj: Any, name: str) -> Any:
    return obj.get(name) if isinstance(obj, dict) else getattr(obj, name, None)


def parse_whisper_words(response: Any, offset: float = 0.0) -> list[Word]:
    """Convertit une réponse Whisper `verbose_json` en mots horodatés, triés et décalés de `offset`."""
    raw_words = _field(response, "words") or []
    words: list[Word] = []
    for raw in raw_words:
        text = str(_field(raw, "word") or "").strip()
        if not text:
            continue
        start = float(_field(raw, "start"))
        end = max(float(_field(raw, "end")), start)
        words.append(Word(text=text, start=round(start + offset, 3), end=round(end + offset, 3)))
    words.sort(key=lambda w: w.start)
    return words


def transcribe_words(client: Any, audio: Path, model: str, offset: float = 0.0) -> list[Word]:
    with audio.open("rb") as handle:
        response = client.audio.transcriptions.create(
            file=handle,
            model=model,
            response_format="verbose_json",
            timestamp_granularities=["word"],
        )
    return parse_whisper_words(response, offset=offset)


def transcribe_chunks(client: Any, chunks: list[tuple[Path, float]], model: str) -> list[Word]:
    words: list[Word] = []
    for path, offset in chunks:
        words.extend(transcribe_words(client, path, model, offset=offset))
    return words
