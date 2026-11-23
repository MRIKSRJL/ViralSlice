from app.models.schemas import Word


def clip_words(words: list[Word], start: float, end: float) -> list[Word]:
    """Mots de la source compris dans [start, end], recalés sur le début du clip."""
    duration = end - start
    result: list[Word] = []
    for word in words:
        if word.end <= start or word.start >= end:
            continue
        result.append(
            Word(
                text=word.text,
                start=round(max(0.0, word.start - start), 3),
                end=round(min(duration, word.end - start), 3),
            )
        )
    return result


def merge_voiceover_words(
    original: list[Word], voiceover: list[Word], clip_duration: float
) -> list[Word]:
    """Sous-titres de la voix off tant qu'elle parle, puis ceux de l'audio original.

    La voix off démarre au début du clip ; les mots originaux prononcés pendant
    qu'elle couvre le clip sont masqués (l'original n'est alors qu'à 20-25 %).
    """
    vo_words = [
        Word(text=w.text, start=w.start, end=min(w.end, clip_duration))
        for w in voiceover
        if w.start < clip_duration
    ]
    if not vo_words:
        return list(original)
    covered_until = vo_words[-1].end
    return vo_words + [w for w in original if w.start >= covered_until]
