from dataclasses import dataclass
from pathlib import Path

from app.models.schemas import Word

SENTENCE_END = (".", "!", "?", "…")


@dataclass(frozen=True)
class SubtitleStyle:
    """Style TikTok/Reels. Couleurs ASS au format &HAABBGGRR."""

    font_name: str = "Montserrat"
    font_size: int = 88
    primary_color: str = "&H00FFFFFF"
    highlight_color: str = "&H0000FFFF"
    outline_color: str = "&H00000000"
    back_color: str = "&H80000000"
    outline: int = 7
    shadow: int = 2
    highlight_scale: int = 112
    margin_v: int = 480
    margin_h: int = 80
    play_res_x: int = 1080
    play_res_y: int = 1920
    max_words: int = 3
    max_chars: int = 20
    max_gap: float = 0.6
    linger: float = 0.3
    uppercase: bool = True


def group_words(
    words: list[Word], max_words: int = 3, max_chars: int = 20, max_gap: float = 0.6
) -> list[list[Word]]:
    """Regroupe les mots en blocs affichés ensemble (3 mots par défaut, 4 au maximum conseillé).

    Un nouveau bloc commence quand le bloc est plein, trop long en caractères,
    après une pause de plus de `max_gap` secondes ou après une fin de phrase.
    """
    groups: list[list[Word]] = []
    current: list[Word] = []
    for word in words:
        if current:
            chars = sum(len(w.text) for w in current) + len(current) + len(word.text)
            if (
                len(current) >= max_words
                or chars > max_chars
                or word.start - current[-1].end > max_gap
                or current[-1].text.endswith(SENTENCE_END)
            ):
                groups.append(current)
                current = []
        current.append(word)
    if current:
        groups.append(current)
    return groups


def format_ass_time(seconds: float) -> str:
    centiseconds = max(0, round(seconds * 100))
    hours, rest = divmod(centiseconds, 360_000)
    minutes, rest = divmod(rest, 6_000)
    secs, cs = divmod(rest, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def escape_ass_text(text: str) -> str:
    """Neutralise les caractères interprétés par libass (`{`, `}`, `\\`)."""
    return text.replace("\\", "/").replace("{", "(").replace("}", ")").replace("\n", " ")


def _render_group_text(group: list[Word], highlighted: int, style: SubtitleStyle) -> str:
    parts = []
    for i, word in enumerate(group):
        text = escape_ass_text(word.text.upper() if style.uppercase else word.text)
        if i == highlighted:
            scale = style.highlight_scale
            text = f"{{\\c{style.highlight_color}&\\fscx{scale}\\fscy{scale}}}{text}{{\\r}}"
        parts.append(text)
    return " ".join(parts)


def build_dialogue_events(
    words: list[Word], style: SubtitleStyle, clip_duration: float | None = None
) -> list[str]:
    """Un événement par mot : le bloc entier est affiché, le mot prononcé est surligné."""
    groups = group_words(words, style.max_words, style.max_chars, style.max_gap)
    events: list[str] = []
    for gi, group in enumerate(groups):
        group_end = group[-1].end + style.linger
        if gi + 1 < len(groups):
            group_end = min(group_end, groups[gi + 1][0].start)
        group_end = max(group_end, group[-1].end)
        if clip_duration is not None:
            group_end = min(group_end, clip_duration)

        for i, word in enumerate(group):
            start = word.start
            end = group[i + 1].start if i + 1 < len(group) else group_end
            if end <= start:
                continue
            text = _render_group_text(group, i, style)
            timing = f"{format_ass_time(start)},{format_ass_time(end)}"
            events.append(f"Dialogue: 0,{timing},Default,,0,0,0,,{text}")
    return events


def build_ass(
    words: list[Word], style: SubtitleStyle | None = None, clip_duration: float | None = None
) -> str:
    style = style or SubtitleStyle()
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {style.play_res_x}
PlayResY: {style.play_res_y}
WrapStyle: 0
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.font_name},{style.font_size},{style.primary_color},{style.highlight_color},{style.outline_color},{style.back_color},-1,0,0,0,100,100,0,0,1,{style.outline},{style.shadow},2,{style.margin_h},{style.margin_h},{style.margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = build_dialogue_events(words, style, clip_duration)
    return header + "\n".join(events) + ("\n" if events else "")


def write_ass(
    path: Path,
    words: list[Word],
    style: SubtitleStyle | None = None,
    clip_duration: float | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build_ass(words, style, clip_duration), encoding="utf-8")
    return path
