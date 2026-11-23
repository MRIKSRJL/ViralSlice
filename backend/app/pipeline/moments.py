import json
import logging
from typing import Any

from app.models.schemas import CommentaryMode, ViralMoment, Word
from app.pipeline.errors import LLMResponseError

logger = logging.getLogger(__name__)

CLIP_COUNT = 3
MIN_CLIP_SECONDS = 30.0
MAX_CLIP_SECONDS = 60.0
# Marge tolérée après recalage des bornes sur les mots.
DURATION_TOLERANCE = 1.5

MOMENTS_JSON_SCHEMA: dict[str, Any] = {
    "name": "viral_moments",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "moments": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "start": {"type": "number"},
                        "end": {"type": "number"},
                        "title": {"type": "string"},
                        "reason": {"type": "string"},
                        "needs_commentary": {"type": "boolean"},
                        "commentary_script": {"type": ["string", "null"]},
                    },
                    "required": [
                        "start",
                        "end",
                        "title",
                        "reason",
                        "needs_commentary",
                        "commentary_script",
                    ],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["moments"],
        "additionalProperties": False,
    },
}

_MODE_INSTRUCTIONS = {
    CommentaryMode.AUTO: (
        "For each moment decide `needs_commentary`. Set it to true ONLY if the clip lacks context "
        "when watched alone, or if it needs a punchy intro hook to grab attention in the first "
        "seconds. Otherwise set it to false and `commentary_script` to null."
    ),
    CommentaryMode.ALWAYS: (
        "Every moment gets a voice-over: set `needs_commentary` to true and always write "
        "`commentary_script`."
    ),
    CommentaryMode.NEVER: (
        "No voice-over: set `needs_commentary` to false and `commentary_script` to null."
    ),
}

SYSTEM_PROMPT = """You are a senior short-form video editor for TikTok, Instagram Reels and YouTube Shorts.
You receive a timestamped transcript of a long video and pick the {count} best viral moments.

Rules for moments:
- Each moment lasts between {min_s:.0f} and {max_s:.0f} seconds and is self-contained (clear start, payoff before the end).
- Start on a strong hook (surprise, question, bold claim, emotion, conflict, punchline setup), never mid-sentence.
- Moments must not overlap. Use timestamps from the transcript, in seconds.
- Order moments from most to least viral.
- `title`: catchy short title in the transcript's language. `reason`: one sentence on why it can go viral.

Commentary:
{mode_instructions}
When written, `commentary_script` is a short, dynamic voice-over read over the very beginning of the clip:
1 to 2 punchy sentences, 25 words maximum (under 10 seconds spoken), in the transcript's language,
no hashtags, no emojis, no stage directions. It adds context or a hook, it does not paraphrase the clip.

Answer only with JSON matching the provided schema."""


def build_transcript_lines(
    words: list[Word], max_words: int = 14, max_gap: float = 1.0
) -> list[str]:
    """Regroupe les mots en lignes horodatées `[début-fin] texte` pour le prompt."""
    lines: list[str] = []
    current: list[Word] = []

    def flush() -> None:
        if current:
            text = " ".join(w.text for w in current)
            lines.append(f"[{current[0].start:.1f}-{current[-1].end:.1f}] {text}")
            current.clear()

    for word in words:
        if current and (len(current) >= max_words or word.start - current[-1].end > max_gap):
            flush()
        current.append(word)
        if word.text.endswith((".", "!", "?")) and len(current) >= 4:
            flush()
    flush()
    return lines


OMISSION_MARKER = "[...]"


def fit_transcript_lines(
    lines: list[str], max_chars: int | None, block_size: int = 60
) -> tuple[list[str], bool]:
    """Réduit la transcription à `max_chars` en gardant le début de chaque bloc de lignes.

    Toute la durée de la vidéo reste représentée par des extraits contigus (plusieurs
    minutes par bloc), séparés par `OMISSION_MARKER`. Retourne (lignes, tronquée ?).
    """
    total = sum(len(line) + 1 for line in lines)
    if max_chars is None or total <= max_chars:
        return lines, False
    blocks = [lines[i : i + block_size] for i in range(0, len(lines), block_size)]
    ratio = max(0.0, max_chars - len(blocks) * (len(OMISSION_MARKER) + 1)) / total
    kept: list[str] = []
    for block in blocks:
        budget = sum(len(line) + 1 for line in block) * ratio
        used = 0
        taken = 0
        for line in block:
            if used + len(line) + 1 > budget:
                break
            kept.append(line)
            used += len(line) + 1
            taken += 1
        if taken < len(block):
            kept.append(OMISSION_MARKER)
    return kept, True


def build_messages(
    words: list[Word],
    video_duration: float,
    mode: CommentaryMode,
    max_transcript_chars: int | None = None,
) -> list[dict[str, str]]:
    system = SYSTEM_PROMPT.format(
        count=CLIP_COUNT,
        min_s=MIN_CLIP_SECONDS,
        max_s=MAX_CLIP_SECONDS,
        mode_instructions=_MODE_INSTRUCTIONS[mode],
    )
    lines, truncated = fit_transcript_lines(build_transcript_lines(words), max_transcript_chars)
    if truncated:
        logger.warning("Transcription réduite à %s caractères pour le LLM", max_transcript_chars)
    note = (
        f"\nParts of the transcript were omitted and replaced by {OMISSION_MARKER}; "
        "a moment must never span an omission."
        if truncated
        else ""
    )
    transcript = "\n".join(lines)
    user = f"Video duration: {video_duration:.1f} s{note}\n\nTranscript:\n{transcript}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _snap_to_words(start: float, end: float, words: list[Word]) -> tuple[float, float]:
    """Évite de couper un mot : le début recule au début du mot, la fin avance à sa fin."""
    for word in words:
        if word.start <= start < word.end:
            start = word.start
            break
    for word in words:
        if word.start < end <= word.end:
            end = word.end
            break
    return start, end


def _fit_duration(start: float, end: float, video_duration: float) -> tuple[float, float]:
    min_s = min(MIN_CLIP_SECONDS, video_duration)
    start = max(0.0, min(start, video_duration))
    end = max(0.0, min(end, video_duration))
    if end - start > MAX_CLIP_SECONDS:
        end = start + MAX_CLIP_SECONDS
    if end - start < min_s:
        end = min(video_duration, start + min_s)
        start = max(0.0, end - min_s)
    return start, end


def _clean_script(script: Any) -> str | None:
    if not isinstance(script, str):
        return None
    cleaned = " ".join(script.split())
    return cleaned or None


def parse_moments_response(
    content: str,
    *,
    video_duration: float,
    mode: CommentaryMode,
    words: list[Word] | None = None,
    count: int = CLIP_COUNT,
) -> list[ViralMoment]:
    """Valide la réponse JSON du LLM et applique les règles de durée et de commentaire."""
    try:
        payload = json.loads(content)
        raw_moments = payload["moments"]
        if not isinstance(raw_moments, list):
            raise TypeError("`moments` n'est pas une liste")
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise LLMResponseError(f"Réponse du LLM illisible : {exc}") from exc

    max_duration = MAX_CLIP_SECONDS + DURATION_TOLERANCE
    moments: list[ViralMoment] = []
    for raw in raw_moments:
        try:
            start, end = float(raw["start"]), float(raw["end"])
        except (KeyError, TypeError, ValueError):
            logger.warning("Moment ignoré, bornes invalides : %r", raw)
            continue
        if end <= start or start >= video_duration:
            logger.warning("Moment ignoré, bornes incohérentes : %r", raw)
            continue

        start, end = _fit_duration(start, end, video_duration)
        if words:
            snapped = _snap_to_words(start, end, words)
            if snapped[1] - snapped[0] <= max_duration:
                start, end = snapped
        if any(start < m.end and m.start < end for m in moments):
            logger.warning("Moment ignoré, chevauchement : %.1f-%.1f", start, end)
            continue

        script = _clean_script(raw.get("commentary_script"))
        if mode is CommentaryMode.NEVER:
            needs, script = False, None
        elif mode is CommentaryMode.ALWAYS:
            if script is None:
                raise LLMResponseError("Le mode « always » exige un commentaire pour chaque clip.")
            needs = True
        else:
            needs = bool(raw.get("needs_commentary")) and script is not None
            if not needs:
                script = None

        moments.append(
            ViralMoment(
                start=round(start, 3),
                end=round(end, 3),
                title=str(raw.get("title") or "").strip() or f"Clip {len(moments) + 1}",
                reason=str(raw.get("reason") or "").strip(),
                needs_commentary=needs,
                commentary_script=script,
            )
        )
        if len(moments) == count:
            break

    if not moments:
        raise LLMResponseError("Le LLM n'a renvoyé aucun moment exploitable.")
    return moments


def detect_viral_moments(
    client: Any,
    model: str,
    words: list[Word],
    video_duration: float,
    mode: CommentaryMode,
    attempts: int = 2,
    *,
    llm_options: dict[str, Any] | None = None,
    max_transcript_chars: int | None = None,
) -> list[ViralMoment]:
    messages = build_messages(words, video_duration, mode, max_transcript_chars)
    last_error: LLMResponseError | None = None
    for _ in range(attempts):
        completion = client.chat.completions.create(
            model=model,
            messages=messages,
            response_format={"type": "json_schema", "json_schema": MOMENTS_JSON_SCHEMA},
            temperature=0.4,
            **(llm_options or {}),
        )
        content = completion.choices[0].message.content or ""
        try:
            return parse_moments_response(
                content, video_duration=video_duration, mode=mode, words=words
            )
        except LLMResponseError as exc:
            logger.warning("Réponse LLM rejetée : %s", exc)
            last_error = exc
    assert last_error is not None
    raise last_error
