#!/usr/bin/env python3
"""Write stream/playlist.txt (ffmpeg concat list) from released renders — never proof renders."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    lines, skipped = [], []
    for ep in sorted((ROOT / "episodes").glob("*/out/final.mp4")):
        rec = ep.parent / "render.json"
        info = json.loads(rec.read_text()) if rec.exists() else {}
        qa = ep.parent / "qa.md"
        if info.get("proof") or not qa.exists() or "**PASS**" not in qa.read_text():
            skipped.append(ep.parent.parent.name)
            continue
        lines.append(f"file '{ep.resolve()}'")
    if not lines:
        print("no released (non-proof, QA-passed) episodes yet", file=sys.stderr)
        return 1
    (ROOT / "stream" / "playlist.txt").write_text("\n".join(lines) + "\n")
    print(f"playlist: {len(lines)} episode(s)" + (f"; skipped {', '.join(skipped)}" if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
