"""Two thumbnails per episode (A/B for Test & Compare): 1280×720 JPEG under 2 MB, 2–4 words, phone-readable."""

from __future__ import annotations

import io
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from . import core

SIZE = (1280, 720)
MAX_BYTES = 2 * 1024 * 1024


def thumb_words(ep: dict, variant: str) -> str:
    text = (ep.get("thumbnail") or {}).get(f"text_{variant}") or ""
    if not text:
        stem = core.strip_emoji(ep["title"].split(" soulful lofi")[0])
        words = stem.split()
        text = " ".join(words[:3] if variant == "a" else words[-3:])
    return core.strip_emoji(text).lower()


def _fit(draw: ImageDraw.ImageDraw, lines: list[str], max_w: int, start: int) -> ImageFont.FreeTypeFont:
    size = start
    while size > 40:
        font = ImageFont.truetype(core.font_path("display"), size)
        if max(draw.textlength(ln, font=font) for ln in lines) <= max_w:
            return font
        size -= 4
    return ImageFont.truetype(core.font_path("display"), size)


def _lines(text: str) -> list[str]:
    """One line for 1–2 words; otherwise the two-line break with the most even line lengths."""
    words = text.split()
    if len(words) <= 2:
        return [text]
    cut = min(range(1, len(words)), key=lambda i: abs(len(" ".join(words[:i])) - len(" ".join(words[i:]))))
    return [" ".join(words[:cut]), " ".join(words[cut:])]


def _shadowed(img: Image.Image, xy, lines, font, fill, shadow, spacing: int, anchor="ls"):
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x, y = xy
    step = font.size + spacing
    ys = [y + i * step for i in range(len(lines))] if anchor.endswith("a") else [y - (len(lines) - 1 - i) * step for i in range(len(lines))]
    for ln, yy in zip(lines, ys):
        d.text((x + 5, yy + 6), ln, font=font, fill=(*shadow, 230), anchor=anchor)
    layer = layer.filter(ImageFilter.GaussianBlur(3))
    d = ImageDraw.Draw(layer)
    for ln, yy in zip(lines, ys):
        d.text((x, yy), ln, font=font, fill=(*fill, 255), anchor=anchor, stroke_width=2, stroke_fill=(*shadow, 255))
    img.alpha_composite(layer)


def _proof_tag(img: Image.Image):
    d = ImageDraw.Draw(img)
    font = ImageFont.truetype(core.font_path("body"), 30)
    d.rectangle([SIZE[0] - 300, 20, SIZE[0] - 20, 70], fill=(170, 30, 30, 235))
    d.text((SIZE[0] - 160, 45), "PROOF", font=font, fill=(255, 255, 255, 255), anchor="mm")


def variant_a(key: Image.Image, text: str, pal: dict) -> Image.Image:
    """Full-bleed scene, big title bottom-left over a soft dark gradient."""
    img = ImageOps.fit(key, SIZE, Image.LANCZOS).convert("RGBA")
    grad = np.linspace(0, 1, SIZE[1], dtype=np.float32) ** 2.2
    shade = Image.fromarray((grad[:, None].repeat(SIZE[0], 1) * 170).astype(np.uint8))
    img.alpha_composite(Image.merge("RGBA", [Image.new("L", SIZE, c) for c in pal["indigo"]] + [shade]))
    d = ImageDraw.Draw(img)
    lines = _lines(text)
    font = _fit(d, lines, int(SIZE[0] * 0.78), 150)
    _shadowed(img, (56, SIZE[1] - 56), lines, font, pal["mustard"], pal["indigo"], spacing=-6)
    return img


def variant_b(key: Image.Image, text: str, pal: dict, focus=(0.62, 0.6)) -> Image.Image:
    """Tighter crop on the props, title top-left in cream on an indigo band with a mustard rule."""
    w, h = key.size
    crop_w, crop_h = int(w / 1.35), int(h / 1.35)
    cx, cy = int(focus[0] * w), int(focus[1] * h)
    x0 = min(max(cx - crop_w // 2, 0), w - crop_w)
    y0 = min(max(cy - crop_h // 2, 0), h - crop_h)
    img = key.crop((x0, y0, x0 + crop_w, y0 + crop_h)).resize(SIZE, Image.LANCZOS).convert("RGBA")
    d = ImageDraw.Draw(img)
    lines = _lines(text)
    font = _fit(d, lines, int(SIZE[0] * 0.8), 140)
    band_h = 60 + len(lines) * (font.size - 6)
    band = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    ImageDraw.Draw(band).rectangle([0, 0, SIZE[0], band_h], fill=(*pal["indigo"], 205))
    img.alpha_composite(band)
    d = ImageDraw.Draw(img)
    d.rectangle([56, band_h - 18, 56 + 180, band_h - 8], fill=(*pal["mustard"], 255))
    _shadowed(img, (56, 34), lines, font, pal["cream"], pal["plum"], spacing=-6, anchor="la")
    return img


def save_jpeg(img: Image.Image, path: Path) -> Path:
    rgb = img.convert("RGB")
    for q in (92, 88, 84, 80, 75, 70):
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=q, optimize=True, progressive=True)
        if buf.tell() < MAX_BYTES:
            path.write_bytes(buf.getvalue())
            return path
    raise core.LofiError(f"could not get {path.name} under 2 MB")


def make(ep: dict, *, proof: bool) -> list[Path]:
    art, out = core.ep_path(ep["id"], "art"), core.ep_path(ep["id"], "out")
    key = Image.open(art / "key.png").convert("RGB")
    pal = core.palette()
    manifest = core.read_json(art / "manifest.json", {}) or {}
    rec = ({**(manifest.get("anchors") or {}), **(ep["art"].get("anchors") or {})}).get("record")
    paths = []
    for variant, build in (("a", lambda t: variant_a(key, t, pal)),
                           ("b", lambda t: variant_b(key, t, pal, focus=(rec[0], rec[1] - 0.12) if rec else (0.6, 0.55)))):
        img = build(thumb_words(ep, variant))
        if proof:
            _proof_tag(img)
        paths.append(save_jpeg(img, out / f"thumb_{variant}.jpg"))
    return paths
