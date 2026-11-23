from app.models.schemas import Word
from app.pipeline.subtitles import (
    SubtitleStyle,
    build_ass,
    build_dialogue_events,
    escape_ass_text,
    format_ass_time,
    group_words,
)


def w(text: str, start: float, end: float) -> Word:
    return Word(text=text, start=start, end=end)


def test_group_words_caps_group_size():
    words = [w(f"m{i}", i * 0.3, i * 0.3 + 0.25) for i in range(7)]
    groups = group_words(words, max_words=3)
    assert [len(g) for g in groups] == [3, 3, 1]


def test_group_words_splits_on_pause_and_sentence_end():
    words = [
        w("Salut", 0.0, 0.3),
        w("tout", 0.35, 0.5),
        w("monde.", 0.55, 0.9),
        w("Regardez", 1.0, 1.4),
        w("ça", 2.5, 2.7),
    ]
    groups = group_words(words, max_words=4, max_chars=40)
    assert [[x.text for x in g] for g in groups] == [
        ["Salut", "tout", "monde."],
        ["Regardez"],
        ["ça"],
    ]


def test_group_words_respects_char_limit_but_keeps_long_words():
    words = [w("incroyablement", 0, 0.5), w("extraordinaire", 0.5, 1.0), w("ok", 1.0, 1.2)]
    groups = group_words(words, max_words=3, max_chars=20)
    assert [[x.text for x in g] for g in groups] == [["incroyablement"], ["extraordinaire", "ok"]]


def test_format_ass_time():
    assert format_ass_time(0) == "0:00:00.00"
    assert format_ass_time(61.234) == "0:01:01.23"
    assert format_ass_time(3725.5) == "1:02:05.50"
    assert format_ass_time(-1) == "0:00:00.00"


def test_escape_ass_text_neutralises_override_tags():
    assert escape_ass_text("a{\\b1}b\nc") == "a(/b1)b c"


def test_events_highlight_current_word_and_are_contiguous():
    words = [w("un", 0.0, 0.4), w("deux", 0.5, 0.9), w("trois", 1.0, 1.3)]
    style = SubtitleStyle()
    events = build_dialogue_events(words, style)
    assert len(events) == 3
    assert events[0].startswith("Dialogue: 0,0:00:00.00,0:00:00.50,Default")
    assert events[1].startswith("Dialogue: 0,0:00:00.50,0:00:01.00,Default")
    assert events[2].startswith("Dialogue: 0,0:00:01.00,0:00:01.60,Default")
    hl = "{\\c&H0000FFFF&\\fscx112\\fscy112}"
    assert events[0].endswith(f"{hl}UN{{\\r}} DEUX TROIS")
    assert events[1].endswith(f"UN {hl}DEUX{{\\r}} TROIS")
    assert events[2].endswith(f"UN DEUX {hl}TROIS{{\\r}}")


def test_group_display_does_not_overlap_next_group_and_respects_clip_end():
    words = [w(f"m{i}", i * 0.4, i * 0.4 + 0.3) for i in range(4)]
    events = build_dialogue_events(words, SubtitleStyle(max_words=3), clip_duration=1.5)
    # Le 3e mot du 1er bloc s'arrête au début du bloc suivant (1.2 s).
    assert ",0:00:00.80,0:00:01.20," in events[2]
    # Le dernier bloc est coupé à la fin du clip.
    assert ",0:00:01.20,0:00:01.50," in events[3]


def test_build_ass_header_style():
    ass = build_ass([w("hello", 0, 1)], SubtitleStyle(font_name="Montserrat"))
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass
    style_line = next(line for line in ass.splitlines() if line.startswith("Style: Default"))
    fields = style_line.removeprefix("Style: ").split(",")
    assert fields[1] == "Montserrat"
    assert fields[3] == "&H00FFFFFF"  # texte blanc
    assert fields[5] == "&H00000000"  # contour noir
    assert fields[7] == "-1"  # gras
    assert fields[15] == "1"  # contour + ombre
    assert int(fields[16]) >= 5  # contour épais
    assert fields[18] == "2"  # centré en bas
    assert ass.rstrip().endswith("{\\r}")


def test_build_ass_without_words_has_no_events():
    ass = build_ass([])
    assert "[Events]" in ass
    assert "Dialogue:" not in ass
