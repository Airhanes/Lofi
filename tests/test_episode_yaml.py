import yaml

from lofi import core


def sample():
    return {
        "id": "s01e09", "title": "test 🎶 soulful lofi beats [1 hour]", "theme": "a: theme, with punctuation",
        "director_note": "line one\nline two",
        "music": {"bpm": [70, 76], "palette": ["rhodes"], "target_minutes": 60, "crossfade_seconds": 4, "credits": "",
                  "tracklist": [{"file": "a b.flac", "title": "it's late", "duration": 61.2, "hash": "ab" * 32}],
                  "approved": True},
        "art": {"scene_prompt": "x", "loop_seconds": 12, "motion": ["rain"], "anchors": {"lamp": [0.5, 0.5]},
                "realistic": None, "approved": False},
        "thumbnail": {"text_a": "late night", "text_b": "two words"},
        "overlays": {"now_playing": True, "visualizer": False},
    }


def test_dump_roundtrips_and_keeps_comments():
    ep = sample()
    text = core.dump_episode(ep)
    assert yaml.safe_load(text) == ep
    assert "# owner only" in text


def test_single_line_note_roundtrips():
    ep = sample()
    ep["director_note"] = "one line: with a colon"
    assert yaml.safe_load(core.dump_episode(ep)) == ep


def test_strip_emoji():
    assert core.strip_emoji("sunday morning in grandma's kitchen ☀️") == "sunday morning in grandma's kitchen"
    assert core.strip_emoji("crate digging at dusk 🎶 x") == "crate digging at dusk x"
