from lofi import timeline


def chapters(text):
    return timeline.parse_chapters(text)


def test_chapter_lines_parse_back():
    stamps = timeline.timestamps([{"title": f"track {i}", "duration": 200} for i in range(20)], 4)
    total = timeline.mix_duration([200] * 20, 4)
    lines = timeline.chapter_lines(stamps, total)
    assert lines[0] == "0:00:00 track 0"           # over an hour → h:mm:ss everywhere
    parsed = chapters("note\n\ntracklist\n" + "\n".join(lines) + "\n\n#lofi")
    assert [p[0] for p in parsed] == [int(s["start"]) for s in stamps]
    assert timeline.validate_chapters(parsed, total) == []


def test_parse_ignores_non_chapter_lines():
    text = "a note about 3:00 am\n0:00 one\n1:00 two\nseason 1 playlist: http://x\n2:00 three\n"
    assert chapters(text) == [(0, "one"), (60, "two"), (120, "three")]


def test_needs_three_chapters():
    assert any("at least 3" in p for p in timeline.validate_chapters([(0, "a"), (60, "b")], 120))


def test_must_start_at_zero():
    assert any("0:00" in p for p in timeline.validate_chapters([(5, "a"), (60, "b"), (120, "c")], 200))


def test_chapters_at_least_ten_seconds():
    problems = timeline.validate_chapters([(0, "a"), (60, "b"), (65, "c")], 200)
    assert any("≥ 10s" in p for p in problems)
    # the last chapter runs to the end of the video
    assert any("≥ 10s" in p for p in timeline.validate_chapters([(0, "a"), (60, "b"), (195, "c")], 200))


def test_must_increase():
    assert any("increase" in p for p in timeline.validate_chapters([(0, "a"), (90, "b"), (60, "c")], 200))


def test_valid_set():
    assert timeline.validate_chapters([(0, "a"), (60, "b"), (120, "c")], 200) == []
