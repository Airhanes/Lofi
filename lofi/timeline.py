"""Pure mix math and chapter logic (no ffmpeg) — the parts with unit tests."""

from __future__ import annotations

import re

MIN_CHAPTERS = 3
MIN_CHAPTER_SECONDS = 10.0


def mix_duration(durations: list[float], crossfade: float) -> float:
    """Length of a chain of tracks joined by overlapping crossfades."""
    if not durations:
        return 0.0
    return sum(durations) - crossfade * (len(durations) - 1)


def track_starts(durations: list[float], crossfade: float) -> list[float]:
    """Start time of each track in the mix: each one begins as the previous one starts fading out."""
    starts, t = [], 0.0
    for i, d in enumerate(durations):
        starts.append(round(t, 3))
        t += d - crossfade
    return starts


def check_crossfade(durations: list[float], crossfade: float) -> None:
    """A crossfade can't be longer than either track it joins (acrossfade would fail or eat a whole track)."""
    if crossfade < 0:
        raise ValueError("crossfade_seconds must be ≥ 0")
    for i, d in enumerate(durations):
        neighbours = (i > 0) + (i < len(durations) - 1)
        if d <= crossfade * neighbours:
            raise ValueError(f"track {i + 1} is {d:.1f}s — too short for {crossfade}s crossfades on both sides")


def timestamps(tracks: list[dict], crossfade: float) -> list[dict]:
    """[{title, file, hash, start, duration}] for timestamps.json and chapters."""
    durations = [float(t["duration"]) for t in tracks]
    check_crossfade(durations, crossfade)
    starts = track_starts(durations, crossfade)
    return [
        {"index": i + 1, "title": t["title"], "file": t.get("file", ""), "hash": t.get("hash", ""),
         "start": s, "duration": round(d, 3)}
        for i, (t, s, d) in enumerate(zip(tracks, starts, durations))
    ]


def fmt_ts(seconds: float, force_hours: bool = False) -> str:
    """YouTube chapter timestamp: m:ss, or h:mm:ss once the video passes an hour."""
    s = int(seconds)  # floor: a chapter must never point past the moment its track starts
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h or force_hours:
        return f"{h}:{m:02d}:{sec:02d}"
    return f"{m}:{sec:02d}"


def parse_ts(text: str) -> int:
    parts = [int(p) for p in text.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    if len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    raise ValueError(f"bad timestamp {text!r}")


def chapter_lines(stamps: list[dict], total: float) -> list[str]:
    hours = total >= 3600
    return [f"{fmt_ts(t['start'], hours)} {t['title']}" for t in stamps]


CHAPTER_RE = re.compile(r"^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$")


def parse_chapters(text: str) -> list[tuple[int, str]]:
    """Pull chapter lines (timestamp + title) out of a description."""
    out = []
    for line in text.splitlines():
        m = CHAPTER_RE.match(line.strip())
        if m:
            out.append((parse_ts(m.group(1)), m.group(2)))
    return out


def validate_chapters(chapters: list[tuple[int, str]], total: float) -> list[str]:
    """YouTube's chapter rules; returns a list of problems (empty = valid)."""
    problems = []
    if len(chapters) < MIN_CHAPTERS:
        problems.append(f"need at least {MIN_CHAPTERS} chapters, found {len(chapters)}")
    if not chapters:
        return problems
    if chapters[0][0] != 0:
        problems.append(f"first chapter must start at 0:00, starts at {fmt_ts(chapters[0][0])}")
    bounds = [c[0] for c in chapters] + [total]
    for i, (start, title) in enumerate(chapters):
        if not title.strip():
            problems.append(f"chapter {i + 1} has no title")
        length = bounds[i + 1] - start
        if length < MIN_CHAPTER_SECONDS:
            problems.append(f"chapter {i + 1} ({title!r}) is {length:.0f}s — chapters must be ≥ {MIN_CHAPTER_SECONDS:.0f}s")
    if any(b <= a for a, b in zip(bounds, bounds[1:-1])):
        problems.append("chapter timestamps must strictly increase")
    if chapters[-1][0] >= total:
        problems.append("last chapter starts after the video ends")
    return problems
