"""Description, tags and upload metadata → out/description.txt + out/metadata.json."""

from __future__ import annotations

from . import core, timeline

NOTE_PLACEHOLDER = "[director's note — the owner writes 2–3 lines here before release]"


def synthetic_flag(ep: dict, manifest: dict) -> bool:
    """YouTube's altered/synthetic content setting: on when imagery looks realistic.

    The owner's call (art.realistic) wins; otherwise assume generative-model art is realistic enough to flag.
    """
    if ep["art"].get("realistic") is not None:
        return bool(ep["art"]["realistic"])
    return bool(manifest.get("realistic_hint"))


def description(ep: dict, stamps: list[dict], total: float, manifest: dict) -> str:
    cfg = core.config()
    note = (ep.get("director_note") or "").strip() or NOTE_PLACEHOLDER
    credits = cfg.get("credits", {})
    music_credit = (ep["music"].get("credits") or credits.get("music") or "").strip()
    tools = manifest.get("tools") or []
    playlist = cfg.get("season_playlist_url") or "[season 1 playlist link — set season_playlist_url in config.yaml]"
    hashtags = " ".join(cfg.get("hashtags", [])[:3])
    parts = [
        note,
        "",
        "tracklist",
        *timeline.chapter_lines(stamps, total),
        "",
        "credits",
        f"music — {music_credit}",
        *[f"{t.split(':', 1)[0]} — {t.split(':', 1)[1].strip()}" if ":" in t else t for t in tools],
        f"mix & render — {credits.get('mix', 'ffmpeg')}",
        "",
        f"season 1 playlist: {playlist}",
        "",
        hashtags,
    ]
    return "\n".join(parts).strip() + "\n"


def make(ep: dict, stamps: list[dict], total: float, *, proof: bool) -> dict:
    cfg = core.config()
    out = core.ep_path(ep["id"], "out")
    manifest = core.read_json(core.ep_path(ep["id"], "art", "manifest.json"), {}) or {}
    text = description(ep, stamps, total, manifest)
    (out / "description.txt").write_text(text)
    meta = {
        "title": ep["title"],
        "description_file": "description.txt",
        "tags": cfg.get("tags", []),
        "category_id": str(cfg.get("category_id", "10")),
        "privacy_status": "private",                 # publishing stays with the owner
        "made_for_kids": False,
        "contains_synthetic_media": synthetic_flag(ep, manifest),
        "default_language": "en",
        "thumbnail": "thumb_a.jpg",
        "thumbnail_test": "thumb_b.jpg",
        "playlist_url": cfg.get("season_playlist_url", ""),
        "proof": proof,
    }
    core.write_json(out / "metadata.json", meta)
    return meta
