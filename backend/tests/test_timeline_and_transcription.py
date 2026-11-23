from types import SimpleNamespace

from app.models.schemas import Word
from app.pipeline.timeline import clip_words, merge_voiceover_words
from app.pipeline.transcription import parse_whisper_words


def w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def test_parse_whisper_words_from_sdk_object_with_offset():
    response = SimpleNamespace(
        text="bonjour à tous",
        words=[
            SimpleNamespace(word=" à", start=0.6, end=0.7),
            SimpleNamespace(word="bonjour", start=0.0, end=0.5),
            SimpleNamespace(word="  ", start=0.7, end=0.8),
            SimpleNamespace(word="tous", start=0.9, end=0.85),
        ],
    )
    words = parse_whisper_words(response, offset=10)
    assert words == [w("bonjour", 10.0, 10.5), w("à", 10.6, 10.7), w("tous", 10.9, 10.9)]


def test_parse_whisper_words_from_dict_and_missing_words():
    assert parse_whisper_words({"words": [{"word": "ok", "start": 1, "end": 2}]}) == [w("ok", 1, 2)]
    assert parse_whisper_words({"text": "x"}) == []


def test_clip_words_shifts_and_clamps():
    words = [w("a", 9.5, 10.2), w("b", 11, 12), w("c", 19.8, 20.5), w("d", 21, 22)]
    assert clip_words(words, 10, 20) == [w("a", 0, 0.2), w("b", 1, 2), w("c", 9.8, 10)]


def test_merge_voiceover_words_hides_original_while_voiceover_speaks():
    original = [w("o1", 0.5, 1.0), w("o2", 2.0, 2.5), w("o3", 3.1, 3.5)]
    voiceover = [w("v1", 0.0, 1.5), w("v2", 1.6, 3.0)]
    merged = merge_voiceover_words(original, voiceover, clip_duration=30)
    assert [x.text for x in merged] == ["v1", "v2", "o3"]


def test_merge_voiceover_words_clamps_to_clip_and_handles_empty():
    original = [w("o1", 0.5, 1.0)]
    assert merge_voiceover_words(original, [], 30) == original
    merged = merge_voiceover_words([], [w("v1", 0, 1), w("v2", 29.5, 31), w("v3", 31, 32)], 30)
    assert merged == [w("v1", 0, 1), w("v2", 29.5, 30)]
