import json
from types import SimpleNamespace

import pytest

from app.models.schemas import CommentaryMode, Word
from app.pipeline.errors import LLMResponseError
from app.pipeline.moments import (
    MOMENTS_JSON_SCHEMA,
    build_messages,
    build_transcript_lines,
    detect_viral_moments,
    parse_moments_response,
)


def moment(start, end, needs=False, script=None, title="Titre"):
    return {
        "start": start,
        "end": end,
        "title": title,
        "reason": "Parce que.",
        "needs_commentary": needs,
        "commentary_script": script,
    }


def payload(*moments) -> str:
    return json.dumps({"moments": list(moments)})


def parse(content, mode=CommentaryMode.AUTO, duration=600.0, words=None):
    return parse_moments_response(content, video_duration=duration, mode=mode, words=words)


def test_parses_three_moments_in_order():
    result = parse(payload(moment(10, 50), moment(100, 145.5), moment(200, 260), moment(300, 340)))
    assert [(m.start, m.end) for m in result] == [(10, 50), (100, 145.5), (200, 260)]


def test_duration_is_brought_into_30_60_seconds():
    result = parse(payload(moment(10, 20), moment(100, 190), moment(590, 600)))
    assert [(m.start, m.end) for m in result] == [(10, 40), (100, 160), (570, 600)]


def test_short_source_yields_whole_video_clip():
    result = parse(payload(moment(0, 12)), duration=20)
    assert [(m.start, m.end) for m in result] == [(0, 20)]


def test_overlapping_and_invalid_moments_are_dropped():
    result = parse(
        payload(
            moment(10, 50),
            moment(40, 80),
            moment(50, 40),
            moment(700, 740),
            {"start": "x", "end": 1},
            moment(100, 140),
        )
    )
    assert [(m.start, m.end) for m in result] == [(10, 50), (100, 140)]


def test_bounds_snap_to_word_boundaries():
    words = [Word(text="a", start=9.8, end=10.4), Word(text="b", start=49.7, end=50.3)]
    result = parse(payload(moment(10, 50)), words=words)
    assert (result[0].start, result[0].end) == (9.8, 50.3)


def test_auto_mode_keeps_commentary_only_when_needed():
    result = parse(
        payload(
            moment(0, 40, needs=True, script="  Attendez   la fin !  "),
            moment(50, 90, needs=False, script="ignoré"),
            moment(100, 140, needs=True, script="   "),
        )
    )
    assert [(m.needs_commentary, m.commentary_script) for m in result] == [
        (True, "Attendez la fin !"),
        (False, None),
        (False, None),
    ]


def test_never_mode_strips_commentary():
    result = parse(payload(moment(0, 40, needs=True, script="x")), mode=CommentaryMode.NEVER)
    assert (result[0].needs_commentary, result[0].commentary_script) == (False, None)


def test_always_mode_forces_commentary_and_requires_script():
    result = parse(payload(moment(0, 40, needs=False, script="Hook")), mode=CommentaryMode.ALWAYS)
    assert (result[0].needs_commentary, result[0].commentary_script) == (True, "Hook")
    with pytest.raises(LLMResponseError):
        parse(payload(moment(0, 40, needs=True, script=None)), mode=CommentaryMode.ALWAYS)


@pytest.mark.parametrize("content", ["pas du json", "{}", '{"moments": {}}', payload()])
def test_unusable_responses_raise(content):
    with pytest.raises(LLMResponseError):
        parse(content)


def test_schema_is_strict_and_requires_all_fields():
    item = MOMENTS_JSON_SCHEMA["schema"]["properties"]["moments"]["items"]
    assert MOMENTS_JSON_SCHEMA["strict"] is True
    assert set(item["required"]) == set(item["properties"])
    assert item["additionalProperties"] is False


def test_transcript_lines_and_messages_mention_mode():
    words = [Word(text=f"m{i}", start=i, end=i + 0.5) for i in range(20)]
    lines = build_transcript_lines(words, max_words=14)
    assert lines[0].startswith("[0.0-13.5] m0 m1")
    assert len(lines) == 2
    messages = build_messages(words, 20, CommentaryMode.AUTO)
    assert "ONLY if the clip lacks context" in messages[0]["content"]
    assert "Video duration: 20.0 s" in messages[1]["content"]


class FakeCompletions:
    def __init__(self, contents):
        self.contents = list(contents)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        content = self.contents.pop(0)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def test_detect_viral_moments_retries_once_on_bad_json():
    completions = FakeCompletions(["oops", payload(moment(0, 40))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    result = detect_viral_moments(client, "gpt-4o", [], 600, CommentaryMode.NEVER)
    assert len(result) == 1
    assert len(completions.calls) == 2
    fmt = completions.calls[0]["response_format"]
    assert fmt["type"] == "json_schema" and fmt["json_schema"]["strict"] is True
    assert completions.calls[0]["model"] == "gpt-4o"
