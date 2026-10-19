"""Placeholder art and audio for pipeline proofs. Everything here is labeled PLACEHOLDER and never ships."""

from __future__ import annotations

import subprocess
import zlib
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import core

W, H = 1920, 1080

# per-scene mood for the placeholder room: wall top/bottom, outside top/bottom, bokeh colors, daytime?
MOODS = {
    "s01e01": dict(wall=("#1B1A3A", "#3A2244"), sky=("#0E1230", "#1E2A52"), bokeh=["#E0567A", "#3FB8B0", "#F2B35B"], day=False),
    "s01e02": dict(wall=("#18233A", "#2F4A3A"), sky=("#0D1428", "#1C2B44"), bokeh=["#F2B35B", "#F4E6CC"], day=False),
    "s01e03": dict(wall=("#C98A4B", "#7A4A2A"), sky=("#F4E6CC", "#F2B35B"), bokeh=["#FFF4DC"], day=True),
    "s01e04": dict(wall=("#1B1A3A", "#2F4A3A"), sky=("#0B1424", "#1A2E2A"), bokeh=["#D8E87A", "#F2B35B"], day=False),
    "s01e05": dict(wall=("#4A2545", "#C8582A"), sky=("#D9A13B", "#4A2545"), bokeh=["#F2B35B", "#F4E6CC"], day=False),
    "s01e06": dict(wall=("#1B1A3A", "#4A2545"), sky=("#0B0F24", "#1B1A3A"), bokeh=["#6FA8DC", "#F2B35B"], day=False),
}

ANCHORS = {
    "window": [0.07, 0.10, 0.43, 0.60],
    "lamp": [0.80, 0.30],
    "record": [0.62, 0.79, 0.058],     # x, y, radius (fraction of width)
    "steam": [0.335, 0.705],
    "neon": [0.25, 0.16],
    "tv": [0.0, 0.55],
}


def _hex(c: str) -> tuple[int, int, int]:
    return tuple(int(c[i:i + 2], 16) for i in (1, 3, 5))


def _vgrad(w: int, h: int, top: str, bottom: str) -> np.ndarray:
    a, b = np.array(_hex(top), np.float32), np.array(_hex(bottom), np.float32)
    t = np.linspace(0, 1, h, dtype=np.float32)[:, None, None]
    return np.broadcast_to(a + (b - a) * t, (h, w, 3)).copy()


def _glow(cx: float, cy: float, radius: float, color: str, strength: float) -> np.ndarray:
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    d2 = ((xx - cx) ** 2 + (yy - cy) ** 2) / (radius ** 2)
    return np.exp(-d2)[..., None] * np.array(_hex(color), np.float32) * strength


def make_art(ep_id: str, out_dir: Path) -> dict:
    """Draw a stylized placeholder room with the recurring props; returns motion anchors."""
    mood = MOODS.get(ep_id, MOODS["s01e01"])
    rng = np.random.default_rng(zlib.crc32(ep_id.encode()))
    img = _vgrad(W, H, *mood["wall"])
    lx, ly = ANCHORS["lamp"][0] * W, ANCHORS["lamp"][1] * H
    img += _glow(lx, ly + 60, 520, "#F2B35B", 0.55)

    # window with the outside world
    x0, y0, x1, y1 = (int(v * (W if i % 2 == 0 else H)) for i, v in enumerate(ANCHORS["window"]))
    sky = _vgrad(x1 - x0, y1 - y0, *mood["sky"])
    img[y0:y1, x0:x1] = sky
    base = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8))

    bokeh = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bokeh)
    for _ in range(26):
        c = _hex(rng.choice(mood["bokeh"]))
        r = int(rng.uniform(10, 34))
        cx, cy = rng.uniform(x0 + 20, x1 - 20), rng.uniform(y0 + (y1 - y0) * 0.35, y1 - 20)
        bd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(*c, int(rng.uniform(70, 160))))
    bokeh = bokeh.filter(ImageFilter.GaussianBlur(6))
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).rectangle([x0, y0, x1, y1], fill=255)
    base.paste(bokeh, (0, 0), Image.composite(bokeh, Image.new("RGBA", (W, H)), mask))
    d = ImageDraw.Draw(base)
    frame = _hex("#5A3A26")
    d.rectangle([x0 - 14, y0 - 14, x1 + 14, y1 + 14], outline=frame, width=16)
    d.line([((x0 + x1) // 2, y0), ((x0 + x1) // 2, y1)], fill=frame, width=10)
    d.line([(x0, (y0 + y1) // 2), (x1, (y0 + y1) // 2)], fill=frame, width=10)
    d.rectangle([x0 - 30, y1 + 14, x1 + 30, y1 + 30], fill=_hex("#6B4630"))  # sill

    if ep_id == "s01e01":  # a neon tube shape in the window — no lettering
        nx, ny = ANCHORS["neon"][0] * W, ANCHORS["neon"][1] * H
        d.rounded_rectangle([nx - 120, ny + 10, nx + 120, ny + 70], radius=30, outline=_hex("#E0567A"), width=7)

    # table
    ty = int(H * 0.74)
    table = _vgrad(W, H - ty, "#6B4630", "#2E1C12")
    base.paste(Image.fromarray(table.astype(np.uint8)), (0, ty))
    d.line([(0, ty), (W, ty)], fill=_hex("#8A5E3E"), width=4)

    # lamp
    d.polygon([(lx - 110, ly + 40), (lx + 110, ly + 40), (lx + 70, ly - 90), (lx - 70, ly - 90)], fill=_hex("#D9A13B"))
    d.rectangle([lx - 8, ly + 40, lx + 8, ty], fill=_hex("#3A2A20"))
    d.ellipse([lx - 70, ty - 18, lx + 70, ty + 10], fill=_hex("#3A2A20"))

    # record player: plinth + disc with label and a notch so rotation reads
    rx, ry, rr = ANCHORS["record"][0] * W, ANCHORS["record"][1] * H, ANCHORS["record"][2] * W
    d.rounded_rectangle([rx - rr - 70, ry - rr - 30, rx + rr + 110, ry + rr + 30], radius=14, fill=_hex("#5A3A26"))
    d.ellipse([rx - rr, ry - rr, rx + rr, ry + rr], fill=(18, 16, 20))
    for k in range(8, int(rr) - 30, 9):
        d.ellipse([rx - rr + k, ry - rr + k, rx + rr - k, ry + rr - k], outline=(34, 30, 38), width=2)
    d.ellipse([rx - 34, ry - 34, rx + 34, ry + 34], fill=_hex("#C8582A"))
    d.rectangle([rx - 4, ry - 30, rx + 4, ry - 14], fill=_hex("#F4E6CC"))
    d.ellipse([rx - 4, ry - 4, rx + 4, ry + 4], fill=(200, 200, 200))
    # tonearm parked off the record, so the spinning disc doesn't carry it round
    d.ellipse([rx + rr + 64, ry - rr - 6, rx + rr + 96, ry - rr + 26], fill=(150, 145, 140))
    d.line([(rx + rr + 80, ry - rr + 10), (rx + rr + 70, ry + rr * 0.7)], fill=(190, 185, 175), width=6)

    # mug (steam source) and composition notebook
    mx, my = ANCHORS["steam"][0] * W, ANCHORS["steam"][1] * H
    d.rounded_rectangle([mx - 34, my, mx + 34, my + 72], radius=8, fill=_hex("#C8582A"))
    d.arc([mx + 22, my + 14, mx + 58, my + 50], -90, 90, fill=_hex("#C8582A"), width=8)
    nb = np.where(rng.random((150, 220)) > 0.5, 235, 25).astype(np.uint8)
    nb_img = Image.fromarray(nb).resize((220, 150), Image.NEAREST).filter(ImageFilter.GaussianBlur(1.2)).convert("RGB")
    nb_img = nb_img.rotate(-8, expand=True, fillcolor=(0, 0, 0))
    nb_mask = Image.new("L", (220, 150), 255).rotate(-8, expand=True)
    base.paste(nb_img, (int(W * 0.12), int(H * 0.80)), nb_mask)

    # pothos trailing from the top right of the window
    px = x1 + 90
    d.rectangle([px - 40, 40, px + 40, 110], fill=_hex("#C8582A"))
    for i in range(18):
        t = i / 17
        cx, cy = px + 60 * np.sin(t * 4.2) - 20, 110 + t * 520
        d.ellipse([cx - 26, cy - 16, cx + 26, cy + 16], fill=_hex("#2F4A3A") if i % 2 else (64, 104, 70))

    # label
    font = ImageFont.truetype(core.font_path("body"), 26)
    d.text((W - 40, 30), f"PLACEHOLDER ART · {ep_id} · not for upload", font=font, fill=_hex("#F4E6CC"), anchor="ra")

    base = base.filter(ImageFilter.GaussianBlur(0.6))
    out_dir.mkdir(parents=True, exist_ok=True)
    base.save(out_dir / "key.png")

    # depth: wall far, table near, record player nearest
    depth = np.full((H, W), 70, np.float32)
    depth[y0:y1, x0:x1] = 20
    depth[ty:] = np.linspace(170, 255, H - ty)[:, None]
    dimg = Image.fromarray(depth.astype(np.uint8))
    dd = ImageDraw.Draw(dimg)
    dd.ellipse([rx - rr - 70, ry - rr - 30, rx + rr + 110, ry + rr + 30], fill=245)
    dd.rectangle([lx - 110, ly - 90, lx + 110, ty], fill=140)
    dimg.filter(ImageFilter.GaussianBlur(25)).save(out_dir / "depth.png")
    return ANCHORS


# ---------------------------------------------------------------- audio

SR = 48_000
NOTE = {"C": 0, "D♭": 1, "D": 2, "E♭": 3, "E": 4, "F": 5, "G♭": 6, "G": 7, "A♭": 8, "A": 9, "B♭": 10, "B": 11}


def _hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def _env(n: int, attack: float, decay: float) -> np.ndarray:
    t = np.arange(n) / SR
    return np.minimum(t / attack, 1.0) * np.exp(-t / decay)


def _lowpass(x: np.ndarray, cutoff: float) -> np.ndarray:
    spec = np.fft.rfft(x, axis=0)
    f = np.fft.rfftfreq(x.shape[0], 1 / SR)
    spec *= (1 / np.sqrt(1 + (f / cutoff) ** 4))[:, None] if x.ndim == 2 else 1 / np.sqrt(1 + (f / cutoff) ** 4)
    return np.fft.irfft(spec, n=x.shape[0], axis=0)


def synth_track(bpm: float, root: str, seconds: float, seed: int) -> np.ndarray:
    """A short swung keys/bass/drums groove with vinyl crackle — obviously a test signal, not music to ship."""
    rng = np.random.default_rng(seed)
    n = int(seconds * SR)
    out = np.zeros((n, 2), np.float32)
    beat = 60.0 / bpm
    bar = beat * 4
    r = 48 + NOTE[root]
    # ii7 – V7 – Imaj7 – vi7, one chord per bar
    prog = [[2, 5, 9, 12], [7, 11, 14, 17], [0, 4, 7, 11], [9, 12, 16, 19]]
    swing = 0.62

    def add(sig: np.ndarray, at: float, pan: float = 0.0, gain: float = 1.0):
        i = int(at * SR)
        if i >= n:
            return
        sig = sig[: n - i] * gain
        out[i:i + len(sig), 0] += sig * (1 - max(pan, 0))
        out[i:i + len(sig), 1] += sig * (1 + min(pan, 0))

    t_chord = np.arange(int(bar * SR)) / SR
    bars = int(seconds / bar) + 1
    for b in range(bars):
        chord = prog[b % 4]
        sig = np.zeros_like(t_chord)
        for k, iv in enumerate(chord):
            f = _hz(r + iv + 12)
            tone = np.sin(2 * np.pi * f * t_chord) + 0.3 * np.sin(4 * np.pi * f * t_chord) * np.exp(-t_chord * 3)
            sig += tone * _env(len(t_chord), 0.01 + 0.012 * k, 1.6)
        sig *= 1 + 0.15 * np.sin(2 * np.pi * 4.5 * t_chord)   # rhodes-ish tremolo
        add(sig.astype(np.float32), b * bar + rng.uniform(0, 0.02), pan=0.15, gain=0.07)
        for step, iv in ((0, 0), (2 + swing - 0.5, 7), (2, 0)):
            bt = np.arange(int(beat * 1.4 * SR)) / SR
            bass = np.sin(2 * np.pi * _hz(r - 12 + chord[0] + iv) * bt) * _env(len(bt), 0.005, 0.5)
            add(bass.astype(np.float32), b * bar + step * beat, gain=0.22)

    kt = np.arange(int(0.35 * SR)) / SR
    kick = np.sin(2 * np.pi * (45 + 70 * np.exp(-kt * 30)) * kt) * np.exp(-kt * 9)
    st = np.arange(int(0.25 * SR)) / SR
    snare = (rng.standard_normal(len(st)) * 0.6 + np.sin(2 * np.pi * 190 * st)) * np.exp(-st * 18)
    ht = np.arange(int(0.05 * SR)) / SR
    hat = np.diff(rng.standard_normal(len(ht) + 1)) * np.exp(-ht * 70)
    beats = int(seconds / beat) + 1
    for i in range(beats):
        t0 = i * beat
        if i % 4 in (0,) or (i % 8 == 6):
            add(kick.astype(np.float32), t0 + rng.uniform(0, 0.012), gain=0.5)
        if i % 4 in (1, 3):
            add(snare.astype(np.float32), t0 + 0.018 + rng.uniform(0, 0.01), gain=0.16)
        add(hat.astype(np.float32), t0, pan=-0.3, gain=0.05)
        add(hat.astype(np.float32), t0 + beat * swing, pan=-0.3, gain=0.035)

    out = _lowpass(out, 5200).astype(np.float32)
    crackle = np.zeros(n, np.float32)
    pops = rng.integers(0, n, int(seconds * 9))
    crackle[pops] = rng.uniform(-0.25, 0.25, len(pops))
    crackle += rng.standard_normal(n).astype(np.float32) * 0.004
    out += _lowpass(crackle, 7000)[:, None].astype(np.float32)
    fade = int(2.5 * SR)
    ramp = np.linspace(0, 1, fade, dtype=np.float32)[:, None]
    out[:fade] *= ramp
    out[-fade:] *= ramp[::-1]
    return out / max(np.abs(out).max(), 1e-6) * 0.7


def make_audio(ep: dict, tracks_dir: Path, count: int = 3, seconds: float = 62.0) -> list[Path]:
    lo, hi = ep["music"]["bpm"]
    roots = ["F", "E♭", "A♭", "D", "B♭"]
    names = ["rain on the glass", "last cut of the night", "neon hum"] if ep["id"] == "s01e01" else \
        [f"test groove {i + 1}" for i in range(count)]
    tracks_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for i in range(count):
        bpm = lo + (hi - lo) * i / max(count - 1, 1)
        audio = synth_track(bpm, roots[i % len(roots)], seconds, seed=i + 1)
        pcm = (np.clip(audio, -1, 1) * 32767).astype("<i2").tobytes()
        path = tracks_dir / f"placeholder_{i + 1:02d}.flac"
        title = f"PLACEHOLDER {i + 1} — {names[i % len(names)]}"
        subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-y", "-v", "error", "-f", "s16le", "-ar", str(SR), "-ac", "2",
                        "-i", "-", "-metadata", f"title={title}", "-metadata", "comment=PLACEHOLDER — pipeline test signal, not for release",
                        "-c:a", "flac", str(path)], input=pcm, check=True)
        paths.append(path)
    return paths
