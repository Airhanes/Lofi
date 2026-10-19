"""catalog.csv — audio hash → episode. A track may appear in only one long-form mix."""

from __future__ import annotations

import csv
import datetime as dt
from pathlib import Path

from . import core

FIELDS = ["hash", "episode", "file", "title", "added"]


def read(path: Path | None = None) -> list[dict]:
    path = path or core.CATALOG
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return [row for row in csv.DictReader(f) if row.get("hash")]


def owners(rows: list[dict]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    for row in rows:
        out.setdefault(row["hash"], set()).add(row["episode"])
    return out


def conflicts(episode: str, tracks: list[dict], rows: list[dict]) -> list[str]:
    """Problems that would put one track into two mixes (or twice into one)."""
    problems = []
    by_hash = owners(rows)
    seen: dict[str, str] = {}
    for t in tracks:
        h = t["hash"]
        if h in seen:
            problems.append(f"{t['file']}: same audio as {seen[h]} in this tracklist")
        seen[h] = t["file"]
        others = sorted(by_hash.get(h, set()) - {episode})
        if others:
            problems.append(f"{t['file']}: already used in {', '.join(others)}")
    return problems


def claim(episode: str, tracks: list[dict], path: Path | None = None) -> int:
    """Record this episode's tracks. Idempotent for re-renders; refuses on any conflict."""
    path = path or core.CATALOG
    rows = read(path)
    problems = conflicts(episode, tracks, rows)
    if problems:
        raise core.LofiError("catalog conflict — a track can only appear in one mix:\n  " + "\n  ".join(problems))
    have = {(r["hash"], r["episode"]) for r in rows}
    today = dt.date.today().isoformat()
    new = [{"hash": t["hash"], "episode": episode, "file": t["file"], "title": t["title"], "added": today}
           for t in tracks if (t["hash"], episode) not in have]
    if new or not path.exists():
        write_header = not path.exists() or path.stat().st_size == 0
        with path.open("a", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            if write_header:
                w.writeheader()
            w.writerows(new)
    return len(new)
