"""`lofi prompts <id>` — Suno prompt sheet for the owner (we never automate Suno)."""

from __future__ import annotations

import random

from . import core

KEYS = ["C major", "A minor", "F major", "D minor", "B♭ major", "G minor", "E♭ major", "C minor",
        "A♭ major", "F minor", "D♭ major", "B♭ minor", "G major", "E minor", "D major", "B minor"]

# the jazz → soul → gospel → neo-soul lineage; the episode palette leads, these fill in
LINEAGE = ["rhodes electric piano", "wurlitzer", "upright bass", "warm electric bass", "swung off-grid drums",
           "brushed snare", "gospel organ swells", "muted trumpet", "breathy tenor sax", "vibraphone",
           "wordless soul vocal textures", "jazz guitar", "soft choir pads"]

# instruments that can carry a melody; bass, drums and pads support
LEAD_CAPABLE = ["rhodes electric piano", "wurlitzer", "gospel organ", "muted trumpet", "breathy tenor sax", "vibraphone",
                "jazz guitar", "jazz piano", "soul guitar", "neo-soul keys", "mellow rhodes", "warm keys"]
SUPPORT_ONLY = ("bass", "drums", "crackle", "pads", "crickets", "boom-bap", "breaks", "tape", "textures")

TEXTURES = ["vinyl crackle", "tape warmth", "tape wow and flutter", "dusty sampled feel", "room reverb",
            "soft sidechain pump", "warm saturation"]

MOODS = ["late-night", "nostalgic", "unhurried", "tender", "smoky", "golden", "hushed", "hopeful",
         "bittersweet", "cozy", "reflective", "sunlit"]

FORMS = ["head-nod groove that builds slowly", "loose jam with a soft bridge", "two-chord vamp with call-and-response",
         "chord progression with jazzy extensions and a gentle turnaround", "laid-back pocket with a short breakdown",
         "simple motif that returns with variation"]

EXCLUDE = "lyrics, rap vocals, trap hi-hats, 808 rolls, EDM drops, autotune, harsh distortion"


def build(ep: dict, n: int = 25) -> list[dict]:
    rng = random.Random(ep["id"])  # stable per episode, different across episodes
    lo, hi = ep["music"]["bpm"]
    palette = list(ep["music"].get("palette") or [])
    leads = [p for p in palette if not any(w in p for w in SUPPORT_ONLY)] or LEAD_CAPABLE[:3]
    keys = KEYS[:]
    rng.shuffle(keys)
    out = []
    for i in range(n):
        lead = leads[i % len(leads)] if rng.random() < 0.65 else rng.choice([x for x in LEAD_CAPABLE if x not in leads])
        support = rng.sample([x for x in palette + LINEAGE if x != lead], 3)
        bpm = round(lo + (hi - lo) * (i / max(n - 1, 1)))  # sweep the whole range
        out.append({
            "n": i + 1,
            "bpm": bpm,
            "key": keys[i % len(keys)],
            "lead": lead,
            "style": ", ".join([
                f"instrumental soulful lofi hip hop", f"{bpm} bpm", keys[i % len(keys)],
                f"{rng.choice(MOODS)} {lead} lead", *support,
                rng.choice(TEXTURES), rng.choice(FORMS),
            ]),
        })
    rng.shuffle(out)  # so the owner isn't handed 25 prompts in tempo order
    for i, p in enumerate(out):
        p["n"] = i + 1
    return out


def write(ep_id: str) -> str:
    ep = core.load_episode(ep_id)
    prompts = build(ep)
    lo, hi = ep["music"]["bpm"]
    lines = [
        f"# suno prompts — {ep['id']}: {ep['title']}",
        "",
        f"scene: {ep['theme']}  ",
        f"tempo range: {lo}–{hi} bpm · palette: {', '.join(ep['music']['palette'])}",
        "",
        "## how to use",
        "",
        "- Generate in Suno **on a paid plan** (commercial rights only cover songs made and downloaded on a paid plan). "
        "Pro = 20 downloads/month, Premier = 60/month, Suno Studio downloads on Premier are uncapped. Re-check Suno's terms before each release.",
        "- Turn on **Instrumental**. Paste the style line into *Style of Music*; paste the exclude line into *Exclude Styles* if your plan has it.",
        "- Aim for 2:30–4:00 per track. A 60-minute mix needs ~20 keepers — there are 25 prompts here, keep the best ~20.",
        "- Download, then drop the files into `episodes/{id}/tracks/` and run `lofi scan {id}`. Name files the way you want the chapter titles to read (lowercase), or set the title tag.".format(id=ep["id"]),
        "- Never add artist names or ask for samples of real records. Tracks used in another episode can't be reused — `catalog.csv` blocks it.",
        "",
        f"**exclude styles (all prompts):** `{EXCLUDE}`",
        "",
        "## prompts",
        "",
    ]
    for p in prompts:
        lines += [
            f"### {p['n']:02d} — {p['lead']}, {p['bpm']} bpm, {p['key']}",
            "",
            f"```\n{p['style']}\n```",
            "",
        ]
    lines += ["## keepers", "", "Tick the ones you keep (for your own records):", ""]
    lines += [f"- [ ] {p['n']:02d}" for p in prompts]
    text = "\n".join(lines) + "\n"
    core.ep_path(ep_id, "suno_prompts.md").write_text(text)
    return text
