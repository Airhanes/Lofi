"""`lofi art <id>` — key art (and optionally a motion clip) from Google's models, or the owner's files.

Outputs in episodes/<id>/art/:
  key.png          1920×1080 key art (used by the loop, thumbnails and the Short)
  depth.png        optional depth map (white = near) for parallax
  loop_source.mp4  optional motion clip (video model or owner-supplied); otherwise motion is built in code
  prompt.txt       the full image/video prompt, so the owner can also use it in any tool by hand
  manifest.json    where the art came from — feeds the credits and the synthetic-content flag
  REVIEW.md        the owner's approval checklist
"""

from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from PIL import Image, ImageOps

from . import core

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}

STYLE = ("richly painted illustration with soft gouache texture and visible film grain, the warmth of a 1970s soul "
         "record sleeve; golden-hour amber and lamplight against deep indigo night; accents of burnt orange, mustard, "
         "plum and forest green; one warm practical light source, soft halation, lifted blacks; eye-level medium-wide "
         "framing with a lived-in foreground; calm lower-left area for on-screen text; cozy, nostalgic, a little cinematic; "
         "feels like a real place someone remembers")

PEOPLE_RULE = ("Any person who appears is Black with deep brown skin rendered accurately in highlights and shadows and "
               "natural hair texture clearly visible; never lighten skin in the golden light, never straighten or smooth the hair.")

NEGATIVE = ("text, letters, logos, watermarks, brand names, caricatured or exaggerated features, lightened skin, "
            "straightened or loosened hair texture, costume clothing, stereotyped props, neon cyberpunk, harsh digital sharpness")

PROPS = "a walnut record player, a trailing pothos plant and a worn composition notebook"

MOTION_WORDS = {
    "rain": "rain streaking down the window glass",
    "neon_flicker": "a soft neon glow flickering gently",
    "lamp_flicker": "warm lamplight flickering softly",
    "tv_flicker": "TV glow flickering blue and warm across the room",
    "steam": "steam curling up and drifting",
    "dust": "dust motes drifting in the light",
    "sunbeam_dust": "dust drifting through a sunbeam",
    "fireflies": "lightning bugs blinking in the dark yard",
    "record": "the record on the turntable spinning",
}


def host_fragment() -> str | None:
    pick = (core.config().get("host") or "")
    pick = str(pick).strip().upper()
    if pick not in {"A", "B"}:
        return None
    text = (core.BRAND / "host.md").read_text()
    section = text.split(f"## option {pick.lower()}", 1)[1]
    quote = section.split("**Prompt fragment**", 1)[1].split(">", 1)[1].split("\n\n", 1)[0]
    return " ".join(quote.split())


def image_prompt(ep: dict) -> str:
    scene = ep["art"].get("scene_prompt") or ep["theme"]
    host = host_fragment()
    who = (f"The channel's host is in the scene, relaxed and absorbed in the moment: {host}." if host
           else "No people in frame; the scene waits for someone to come back to it.")
    return (f"{scene}. Somewhere in the scene: {PROPS}. {who} {PEOPLE_RULE} Style: {STYLE}. "
            f"16:9, 1920x1080. Avoid: {NEGATIVE}.")


def video_prompt(ep: dict) -> str:
    motion = [MOTION_WORDS[m] for m in ep["art"].get("motion", []) if m in MOTION_WORDS]
    host = host_fragment()
    moves = ", ".join(motion) or "gentle ambient movement"
    who = " The host breathes and nods slowly to the music, staying in place." if host else ""
    return (f"Locked-off camera, no cuts, no zoom. Subtle continuous ambient motion that can loop: {moves}.{who} "
            f"Keep the composition, colors and lighting of the source image exactly. {PEOPLE_RULE}")


# ---------------------------------------------------------------- helpers

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cover(img: Image.Image, size=(1920, 1080), focus=(0.5, 0.5)) -> Image.Image:
    return ImageOps.fit(img.convert("RGB"), size, Image.LANCZOS, centering=focus)


def google_ready() -> bool:
    core.load_env()
    return bool(os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_CLOUD_PROJECT"))


def _client():
    try:
        from google import genai
    except ImportError as e:
        raise core.LofiError("Google art generation needs the GenAI SDK: pip install 'lofi[genai]'") from e
    if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
        return genai.Client(api_key=os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"))
    return genai.Client(vertexai=True, project=os.environ["GOOGLE_CLOUD_PROJECT"],
                        location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"))


def generate_google(ep: dict, art: Path, *, video: bool, log=print) -> list[str]:
    """Key art via the image model, then (optionally) an image-to-video motion clip. Returns tool credits."""
    from google.genai import types

    cfg = core.config().get("art", {})
    client = _client()
    log(f"  generating key art with {cfg.get('image_model')}")
    resp = client.models.generate_images(
        model=cfg.get("image_model", "imagen-4.0-generate-001"), prompt=image_prompt(ep),
        config=types.GenerateImagesConfig(number_of_images=1, aspect_ratio="16:9"),
    )
    if not resp.generated_images:
        raise core.LofiError("image model returned nothing (prompt may have been filtered) — edit art.scene_prompt")
    raw = art / "key_generated.png"
    raw.write_bytes(resp.generated_images[0].image.image_bytes)
    cover(Image.open(raw)).save(art / "key.png")
    tools = [f"key art: {cfg.get('image_model')} (Google)"]
    if not video:
        return tools
    log(f"  generating motion clip with {cfg.get('video_model')} (this takes a few minutes)")
    op = client.models.generate_videos(
        model=cfg.get("video_model", "veo-3.0-generate-001"), prompt=video_prompt(ep),
        image=types.Image(image_bytes=raw.read_bytes(), mime_type="image/png"),
        config=types.GenerateVideosConfig(aspect_ratio="16:9", number_of_videos=1),
    )
    deadline = time.time() + 15 * 60
    while not op.done:
        if time.time() > deadline:
            raise core.LofiError("video generation timed out after 15 min — re-run `lofi art` or build motion in code")
        time.sleep(15)
        op = client.operations.get(op)
    vids = getattr(op.response, "generated_videos", None) or []
    if not vids:
        raise core.LofiError("video model returned nothing — motion will be built in code; re-run `lofi loop`")
    clip = vids[0].video
    if getattr(clip, "video_bytes", None):
        (art / "loop_source.mp4").write_bytes(clip.video_bytes)
    else:
        client.files.download(file=clip)
        clip.save(str(art / "loop_source.mp4"))
    tools.append(f"motion: {cfg.get('video_model')} (Google), looped in code")
    return tools


def find_owner_art(art: Path) -> tuple[Path | None, Path | None]:
    skip = {"key.png", "depth.png", "key_generated.png", "loop.mp4"}
    images = sorted(p for p in art.iterdir() if p.suffix.lower() in IMAGE_EXTS and p.name not in skip
                    and not p.name.startswith(("placeholder", "thumb")))
    videos = sorted(p for p in art.iterdir() if p.suffix.lower() in VIDEO_EXTS and p.name not in skip)
    key = next((p for p in images if p.stem.lower() in {"key", "key_art", "keyart"}), images[0] if images else None)
    if (art / "key.png").exists() and key is None:
        key = art / "key.png"
    vid = next((p for p in videos if p.stem.lower() == "loop_source"), videos[0] if videos else None)
    return key, vid


def review_md(ep: dict, manifest: dict) -> str:
    host = host_fragment()
    return f"""# art review — {ep['id']}

Source: **{manifest['source']}** · {', '.join(manifest['tools'])}

Look at `key.png` and, after `lofi loop {ep['id']}`, watch `loop.mp4` a few times through the seam. Set `art.approved: true` in episode.yaml only if every box is true:

- [ ] it feels like a real place someone remembers — specific, warm, lived-in; nothing reads as costume or punchline
- [ ] {"the host matches the character sheet (" + host + ")" if host else "no host yet (owner hasn't picked A/B) — props-only scene is fine"}
- [ ] skin is deep brown and stays deep brown in the warm light; hair texture is natural and visible (not flattened, loosened or smoothed)
- [ ] no caricatured features, no stereotyped props, no stray text/logos/watermarks
- [ ] palette and light fit `brand/style.md` (amber/lamplight vs indigo night; grain)
- [ ] doesn't resemble another channel's signature character or composition
- [ ] the loop has real motion (rain, steam, flicker, spinning record, the host moving) — not a still or a slow zoom
- [ ] the loop seam is invisible
- [ ] if it looks photoreal, set `art.realistic: true` so the upload flags YouTube's altered/synthetic content setting
"""


# ---------------------------------------------------------------- entry point

def run(ep_id: str, *, generator: str | None = None, video: bool = True, force: bool = False, log=print) -> dict:
    ep = core.load_episode(ep_id)
    art = core.ep_path(ep_id, "art")
    art.mkdir(parents=True, exist_ok=True)
    if ep["art"].get("approved") and not force:
        raise core.LofiError(f"{ep_id}: art is already approved — pass --force to replace it (this resets art.approved)")

    (art / "prompt.txt").write_text(f"IMAGE PROMPT\n{image_prompt(ep)}\n\nVIDEO PROMPT (image-to-video)\n{video_prompt(ep)}\n")
    mode = generator or core.config().get("art", {}).get("generator", "auto")
    owner_key, owner_vid = find_owner_art(art)
    old = core.read_json(art / "manifest.json", {}) or {}
    # key.png that we generated earlier (placeholder or Google) is not "owner art"
    generated = ((art / "key.png").exists() and old.get("source") in {"placeholder", "google"}
                 and old.get("key_sha") == sha(art / "key.png"))
    if generated and owner_key is not None and owner_key.name == "key.png":
        owner_key = None

    if mode == "google" or (mode == "auto" and google_ready() and owner_key is None and not generated):
        tools = generate_google(ep, art, video=video, log=log)
        source, realistic_hint = "google", True
    elif owner_key is not None:
        if owner_key.name != "key.png" or old.get("source") != "owner" or old.get("key_sha") != sha(owner_key):
            cover(Image.open(owner_key)).save(art / "key.png")
        source, realistic_hint = "owner", None
        tools = ["key art: supplied by the owner"]
        if owner_vid:
            tools.append("motion: owner-supplied clip, looped in code")
        log(f"  using owner art {owner_key.name}" + (f" + clip {owner_vid.name}" if owner_vid else ""))
    elif generated:
        source, realistic_hint, tools = old["source"], old.get("realistic_hint"), old["tools"]
        log(f"  keeping existing {source} key art (pass --generator google to regenerate)")
    else:
        raise core.LofiError(
            f"{ep_id}: no art. Either drop key art (and optionally a loop_source.mp4) into {art}/, "
            f"configure Google credentials in .env (GOOGLE_CLOUD_PROJECT or GOOGLE_API_KEY), "
            f"or make placeholder art with `lofi placeholder {ep_id}`. The prompt is in {art / 'prompt.txt'}.")

    manifest = {**old, "source": source, "tools": tools, "realistic_hint": realistic_hint,
                "key_sha": sha(art / "key.png"), "has_depth": (art / "depth.png").exists(),
                "has_clip": (art / "loop_source.mp4").exists() or bool(owner_vid),
                "clip": (owner_vid.name if owner_vid else "loop_source.mp4") if (owner_vid or (art / "loop_source.mp4").exists()) else None}
    core.write_json(art / "manifest.json", manifest)
    (art / "REVIEW.md").write_text(review_md(ep, manifest))
    if force and ep["art"].get("approved"):
        ep["art"]["approved"] = False
        core.save_episode(ep)
        log("  art changed — art.approved reset to false")
    return manifest
