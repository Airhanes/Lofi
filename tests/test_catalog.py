import pytest

from lofi import catalog, core


def tr(h, f=None):
    return {"hash": h, "file": f or f"{h}.flac", "title": h}


def test_empty_catalog_has_no_conflicts(tmp_path):
    assert catalog.read(tmp_path / "missing.csv") == []
    assert catalog.conflicts("s01e01", [tr("a"), tr("b")], []) == []


def test_claim_then_reuse_in_other_episode_conflicts(tmp_path):
    path = tmp_path / "catalog.csv"
    assert catalog.claim("s01e01", [tr("a"), tr("b")], path) == 2
    rows = catalog.read(path)
    assert {r["hash"] for r in rows} == {"a", "b"}
    problems = catalog.conflicts("s01e02", [tr("c"), tr("b", "renamed.mp3")], rows)
    assert len(problems) == 1 and "s01e01" in problems[0] and "renamed.mp3" in problems[0]
    with pytest.raises(core.LofiError):
        catalog.claim("s01e02", [tr("b")], path)
    assert len(catalog.read(path)) == 2  # refused claims write nothing


def test_rerender_same_episode_is_idempotent(tmp_path):
    path = tmp_path / "catalog.csv"
    catalog.claim("s01e01", [tr("a")], path)
    assert catalog.claim("s01e01", [tr("a")], path) == 0
    assert catalog.conflicts("s01e01", [tr("a")], catalog.read(path)) == []
    assert len(catalog.read(path)) == 1


def test_duplicate_within_one_tracklist(tmp_path):
    problems = catalog.conflicts("s01e01", [tr("a", "x.flac"), tr("a", "y.flac")], [])
    assert len(problems) == 1 and "x.flac" in problems[0]


def test_header_written_once(tmp_path):
    path = tmp_path / "catalog.csv"
    path.write_text("hash,episode,file,title,added\n")
    catalog.claim("s01e01", [tr("a")], path)
    catalog.claim("s01e02", [tr("b")], path)
    assert path.read_text().count("hash,episode") == 1
