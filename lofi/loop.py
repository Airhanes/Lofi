"""`lofi loop <id>` — a seamless 1920×1080/30 fps motion loop → episodes/<id>/art/loop.mp4.

Two routes:
* a motion clip exists (video model or owner): conform it and crossfade its tail into its head;
* otherwise motion is built in code on top of key.png: depth parallax, rain, steam, dust, fireflies,
  lamp/neon/TV flicker and a spinning record. Every layer is a periodic function of loop phase
  p ∈ [0, 1) with whole-number cycles, so the last frame flows into the first by construction.
"""

from __future__ import annotations

import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from . import core

# ---------------------------------------------------------------- encoding


def x264_args(fps: int) -> list[str]:
    v = core.config().get("video", {})
    gop = int(v.get("gop_seconds", 2) * fps)
    return ["-c:v", "libx264", "-preset", v.get("preset", "medium"), "-profile:v", "high", "-level", "4.2",
            "-pix_fmt", "yuv420p", "-b:v", v.get("bitrate", "10M"), "-maxrate", v.get("maxrate", "12M"),
            "-bufsize", v.get("bufsize", "20M"), "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0",
            "-r", str(fps)]


# ---------------------------------------------------------------- clip route

def from_clip(src: Path, dst: Path, seconds: float, fps: int, w: int, h: int, log=print) -> dict:
    clip_len = core.media_duration(src)
    xf = min(1.5, seconds * 0.2)
    body = min(seconds, clip_len - xf)
    if body < 3:
        raise core.LofiError(f"{src.name} is {clip_len:.1f}s — too short to loop; need at least {3 + xf:.1f}s")
    repeat = max(1, math.ceil(8 / body))  # loops must be ≥ 8 s; repeat a short seamless cycle
    log(f"  conforming {src.name}: {body:.2f}s cycle, {xf:.2f}s tail→head crossfade" + (f", ×{repeat}" if repeat > 1 else ""))
    frames = round(body * fps)
    body = frames / fps
    graph = (
        f"[0:v]fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},setsar=1,format=yuv420p,split=3[a][b][c];"
        f"[a]trim=start={body}:end={body + xf},setpts=PTS-STARTPTS[tail];"
        f"[b]trim=start=0:end={xf},setpts=PTS-STARTPTS[head];"
        f"[c]trim=start={xf}:end={body},setpts=PTS-STARTPTS[mid];"
        f"[tail][head]xfade=transition=fade:duration={xf}:offset=0[seam];"
        f"[seam][mid]concat=n=2:v=1:a=0,loop=loop={repeat - 1}:size={frames}:start=0,setpts=N/{fps}/TB[out]"
    )
    core.ffmpeg("-i", str(src), "-filter_complex", graph, "-map", "[out]", "-an", *x264_args(fps),
                "-frames:v", str(frames * repeat), "-movflags", "+faststart", str(dst))
    return {"route": "clip", "source": src.name, "seconds": round(body * repeat, 3), "crossfade": xf}


# ---------------------------------------------------------------- code route: helpers

def _sprite(size: int, sharp: float = 2.2) -> np.ndarray:
    yy, xx = np.mgrid[-1:1:size * 1j, -1:1:size * 1j]
    return np.exp(-(xx ** 2 + yy ** 2) * sharp).astype(np.float32)


def _stamp(frame: np.ndarray, sprite: np.ndarray, cx: float, cy: float, color: np.ndarray, alpha: float) -> None:
    """Additively blend a soft sprite (HxW in 0..1) centred at (cx, cy)."""
    h, w = sprite.shape
    x0, y0 = int(cx - w / 2), int(cy - h / 2)
    fx0, fy0 = max(x0, 0), max(y0, 0)
    fx1, fy1 = min(x0 + w, frame.shape[1]), min(y0 + h, frame.shape[0])
    if fx0 >= fx1 or fy0 >= fy1 or alpha <= 0:
        return
    s = sprite[fy0 - y0:fy1 - y0, fx0 - x0:fx1 - x0, None] * alpha
    region = frame[fy0:fy1, fx0:fx1]
    region += s * (color - region)  # "over" blend: brightens toward the sprite color


def _periodic(p: float, terms: list[tuple[int, float, float]]) -> float:
    """Sum of sines with whole-number cycles per loop → seamless flicker."""
    return sum(a * math.sin(2 * math.pi * (n * p + ph)) for n, a, ph in terms)


def _wrap(d: float) -> float:
    return (d + 0.5) % 1.0 - 0.5


# ---------------------------------------------------------------- code route: scene

NEON = np.array([224, 86, 122], np.float32)
TV = np.array([110, 150, 230], np.float32)
SUN = np.array([255, 214, 150], np.float32)
STEAM = np.array([238, 228, 214], np.float32)
DUST = np.array([255, 226, 170], np.float32)
FIREFLY = np.array([226, 240, 120], np.float32)


class Scene:
    def __init__(self, key: Path, depth: Path | None, anchors: dict, motion: list[str], seconds: float,
                 fps: int, w: int, h: int, seed: int = 7):
        self.w, self.h, self.fps, self.seconds = w, h, fps, seconds
        self.n = round(seconds * fps)
        self.motion = set(motion)
        self.rng = np.random.default_rng(seed)
        img = Image.open(key).convert("RGB")
        if img.size != (w, h):
            img = img.resize((w, h), Image.LANCZOS)
        self.base_img = img
        self.base = np.asarray(img, np.float32)
        if depth and depth.exists():
            d = np.asarray(Image.open(depth).convert("L").resize((w, h)), np.float32) / 255.0
        else:  # no depth map: the bottom of the frame is nearer than the top
            d = np.broadcast_to(np.linspace(0.15, 1.0, h, dtype=np.float32)[:, None], (h, w)).copy()
        self.depth = d
        self.a = {k: v for k, v in (anchors or {}).items() if v}
        self.xs = np.arange(w, dtype=np.float32)[None, :].repeat(h, 0)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        self._yy, self._xx = yy, xx
        # the vignette is linear, so bake it into the base and the light layers once instead of per frame
        self.vignette = (1 - 0.35 * (((xx - w / 2) / (w / 2)) ** 2 + ((yy - h / 2) / (h / 2)) ** 2) ** 1.4).clip(0.45, 1)[..., None]
        self.base *= self.vignette
        self.flat = self.base.reshape(-1, 3)
        self.row_base = (np.arange(h, dtype=np.int32) * w)[:, None]
        self.grain = []
        for _ in range(12):  # film grain at half resolution, upscaled: softer and cheaper
            g = self.rng.standard_normal((h // 2 + 1, w // 2 + 1)).astype(np.float32) * 5.0
            self.grain.append(np.repeat(np.repeat(g, 2, 0), 2, 1)[:h, :w, None].copy())
        self._setup_layers()

    def px(self, xy):
        return xy[0] * self.w, xy[1] * self.h

    def glow(self, xy, radius_frac: float) -> np.ndarray:
        cx, cy = self.px(xy)
        r = radius_frac * self.w
        return np.exp(-((self._xx - cx) ** 2 + (self._yy - cy) ** 2) / (r * r))[..., None].astype(np.float32)

    def _setup_layers(self):
        rng, w, h, n = self.rng, self.w, self.h, self.n
        a, m = self.a, self.motion
        self.lamp = self.glow(a.get("lamp", [0.8, 0.3]), 0.22) if "lamp_flicker" in m else None
        self.neon = (self.glow(a.get("neon", [0.25, 0.16]), 0.12) * NEON * self.vignette) if "neon_flicker" in m else None
        self.tv = (self.glow(a.get("tv", [0.0, 0.55]), 0.45) * TV * self.vignette) if "tv_flicker" in m else None
        self.beam = None
        self.steam, self.flies = [], []
        self.rain_color = np.array([200, 215, 240], np.float32)

        if "rain" in m:
            win = a.get("window")
            box = (np.array(win) * [w, h, w, h]).astype(int) if win else np.array([0, 0, w, h])
            self.rain_box = box
            area = (box[2] - box[0]) * (box[3] - box[1]) / (w * h)
            count = int(260 * max(area, 0.15) / 0.2) if win else 380
            bh = box[3] - box[1]
            self.rain = [dict(x=rng.uniform(box[0], box[2]), u=rng.uniform(), k=int(rng.integers(14, 26)) * max(1, round(self.seconds / 12)),
                              length=rng.uniform(0.05, 0.11) * bh, alpha=rng.uniform(0.18, 0.5) if win else rng.uniform(0.05, 0.16))
                         for _ in range(count)]
            self.slides = [dict(x=rng.uniform(box[0] + 8, box[2] - 8), u=rng.uniform(), k=int(rng.integers(1, 3)),
                                r=rng.uniform(2.5, 5)) for _ in range(18 if win else 0)]

        if "record" in m and a.get("record"):
            rx, ry, rr = a["record"][0] * w, a["record"][1] * h, a["record"][2] * w
            box = (int(rx - rr), int(ry - rr), int(rx + rr), int(ry + rr))
            self.disc = Image.fromarray(self.base.clip(0, 255).astype(np.uint8)).crop(box)  # already vignetted
            mask = Image.new("L", self.disc.size, 0)
            ImageDraw.Draw(mask).ellipse([1, 1, self.disc.size[0] - 2, self.disc.size[1] - 2], fill=255)
            self.disc_alpha = (np.asarray(mask.filter(ImageFilter.GaussianBlur(1)), np.float32) / 255.0)[..., None]
            self.disc_box = box
            self.disc_depth = float(self.depth[int(ry), int(rx)])
            self.revs = max(1, round(self.seconds * 33.333 / 60))  # 33⅓ rpm, whole turns per loop
        else:
            self.disc = None

        self.puff8 = (_sprite(96, 2.6) * 255).astype(np.uint8)
        if "steam" in m:
            sx, sy = self.px(a.get("steam", [0.5, 0.7]))
            cycles = max(1, round(self.seconds / 4))
            self.steam = [dict(x=sx + rng.uniform(-14, 14), y=sy, ph=i / 14 + rng.uniform(0, 0.03), k=cycles,
                               sway=rng.uniform(0, 1)) for i in range(14)]
        self.mote = _sprite(10, 3.0)
        dust_n = (60 if "dust" in m else 0) + (90 if "sunbeam_dust" in m else 0)
        self.dust = [dict(x=rng.uniform(0, w), y=rng.uniform(0, h), ax=rng.uniform(20, 90), ay=rng.uniform(15, 60),
                          fx=int(rng.integers(1, 3)), fy=int(rng.integers(1, 3)), ph=rng.uniform(0, 1),
                          tw=int(rng.integers(1, 4)), s=rng.uniform(0.25, 0.7)) for _ in range(dust_n)]
        if "sunbeam_dust" in m:
            win = a.get("window", [0.07, 0.1, 0.43, 0.6])
            beam = Image.new("L", (w, h), 0)
            x0, y0, x1, y1 = win[0] * w, win[1] * h, win[2] * w, win[3] * h
            ImageDraw.Draw(beam).polygon([(x0, y0), (x1, y0), (x1 + w * 0.35, h), (x0 + w * 0.18, h)], fill=255)
            self.beam = (np.asarray(beam.filter(ImageFilter.GaussianBlur(60)), np.float32) / 255.0)[..., None] * SUN * self.vignette
            # keep sunbeam dust inside the beam
            for d in self.dust[-90:]:
                t = rng.uniform(0.1, 0.9)
                d["y"] = y0 + (h - y0) * t
                d["x"] = (x0 + (x0 + w * 0.18 - x0) * t) + rng.uniform(0, (x1 - x0) + w * 0.17 * t)
        self.fly = _sprite(28, 2.0)
        if "fireflies" in m:
            win = a.get("window", [0.0, 0.0, 1.0, 0.7])
            self.flies = [dict(x=rng.uniform(win[0], win[2]) * w, y=rng.uniform(win[1] + 0.1, win[3]) * h,
                               ax=rng.uniform(15, 60), ay=rng.uniform(10, 40), ph=rng.uniform(0, 1),
                               blink=int(rng.integers(2, 5))) for _ in range(22)]

    # -- per frame

    def frame(self, i: int) -> np.ndarray:
        p = i / self.n
        w, h = self.w, self.h

        # depth parallax: a slow horizontal sway, nearer pixels move more (bilinear in x)
        shift = 5.0 * math.sin(2 * math.pi * p)
        sx = (self.xs - shift * self.depth).clip(0, w - 1.001)
        x0 = sx.astype(np.int32)
        idx = (self.row_base + x0).ravel()
        out = np.take(self.flat, idx, axis=0).reshape(h, w, 3)
        nxt = np.take(self.flat, idx + 1, axis=0).reshape(h, w, 3)
        nxt -= out
        nxt *= (sx - x0)[..., None]
        out += nxt

        if self.disc is not None:  # spin the record, then drop it back in where the sway put it
            bx, by = self.disc_box[:2]
            bx += int(round(-shift * self.disc_depth))
            spun = np.asarray(self.disc.rotate(-360.0 * self.revs * p, resample=Image.BICUBIC), np.float32)
            dh, dw = spun.shape[:2]
            region = out[by:by + dh, bx:bx + dw]
            region += (spun[:region.shape[0], :region.shape[1]] - region) * self.disc_alpha[:region.shape[0], :region.shape[1]]

        if self.lamp is not None:
            f = _periodic(p, [(3, 0.05, 0.0), (7, 0.025, 0.3), (17, 0.012, 0.7)])
            out *= 1 + self.lamp * (0.10 + f)
        if self.neon is not None:
            f = _periodic(p, [(5, 0.06, 0.1), (23, 0.03, 0.5)])
            dip = sum(math.exp(-(_wrap(p - c) / 0.006) ** 2) for c in (0.23, 0.245, 0.71))  # neon stutters
            out += self.neon * max(0.0, 0.32 + f - 0.3 * dip)
        if self.tv is not None:
            f = _periodic(p, [(11, 0.25, 0.0), (29, 0.15, 0.4), (53, 0.1, 0.8), (3, 0.2, 0.2)])
            out += self.tv * max(0.0, 0.28 + 0.25 * f)
        if self.beam is not None:
            out += self.beam * (0.16 + 0.03 * math.sin(2 * math.pi * p))

        if "rain" in self.motion:
            b = self.rain_box
            bw, bh = b[2] - b[0], b[3] - b[1]
            layer = Image.new("L", (bw, bh), 0)
            d = ImageDraw.Draw(layer)
            for r in self.rain:
                x = r["x"] - b[0]
                y = ((r["u"] + r["k"] * p) % 1.0) * (bh + r["length"]) - r["length"]
                d.line([(x, y), (x - r["length"] * 0.08, y + r["length"])], fill=int(255 * r["alpha"]), width=2)
            for s in self.slides:  # drops sliding down the glass
                x, y, rr = s["x"] - b[0], ((s["u"] + s["k"] * p) % 1.0) * bh, s["r"]
                d.ellipse([x - rr, y - rr, x + rr, y + rr * 1.4], fill=150)
                d.line([(x, y - 40), (x, y)], fill=50, width=2)
            rain = np.asarray(layer.filter(ImageFilter.GaussianBlur(0.8)), np.float32)[..., None] * (0.6 / 255.0)
            region = out[b[1]:b[3], b[0]:b[2]]
            region += rain * (self.rain_color - region)

        if self.steam:
            for s in self.steam:
                q = (s["k"] * p + s["ph"]) % 1.0
                size = int(30 + 110 * q)
                spr = np.asarray(Image.fromarray(self.puff8).resize((size, size)), np.float32) / 255
                x = s["x"] + 26 * math.sin(2 * math.pi * (q * 1.3 + s["sway"])) * q
                y = s["y"] - 260 * q
                _stamp(out, spr, x, y, STEAM, 0.22 * math.sin(math.pi * q) ** 1.5)

        for dm in self.dust:
            x = dm["x"] + dm["ax"] * math.sin(2 * math.pi * (dm["fx"] * p + dm["ph"]))
            y = dm["y"] + dm["ay"] * math.sin(2 * math.pi * (dm["fy"] * p + dm["ph"] * 1.7))
            tw = 0.5 + 0.5 * math.sin(2 * math.pi * (dm["tw"] * p + dm["ph"]))
            _stamp(out, self.mote, x, y, DUST, dm["s"] * tw)

        for f in self.flies:
            x = f["x"] + f["ax"] * math.sin(2 * math.pi * (p + f["ph"]))
            y = f["y"] + f["ay"] * math.sin(2 * math.pi * (2 * p + f["ph"]))
            b = max(0.0, math.sin(2 * math.pi * (f["blink"] * p + f["ph"]))) ** 6
            _stamp(out, self.fly, x, y, FIREFLY, 0.9 * b)

        out += self.grain[i % len(self.grain)]
        np.clip(out, 0, 255, out=out)
        return out.astype(np.uint8)


def from_code(key: Path, depth: Path | None, anchors: dict, motion: list[str], dst: Path, seconds: float,
              fps: int, w: int, h: int, log=print) -> dict:
    scene = Scene(key, depth, anchors, motion, seconds, fps, w, h)
    layers = sorted(scene.motion | {"parallax", "grain"})
    log(f"  building motion in code: {', '.join(layers)} — {scene.n} frames")
    cmd = ["ffmpeg", "-hide_banner", "-nostdin", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-an", *x264_args(fps), "-movflags", "+faststart", str(dst)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        for i in range(scene.n):
            proc.stdin.write(scene.frame(i).tobytes())
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors="replace")
    if proc.wait() != 0:
        raise core.LofiError(f"ffmpeg failed encoding the loop:\n{err[-1500:]}")
    return {"route": "code", "layers": layers, "seconds": scene.n / fps, "seamless": "periodic by construction"}


# ---------------------------------------------------------------- entry point

def run(ep_id: str, *, log=print) -> Path:
    ep = core.load_episode(ep_id)
    art = core.ep_path(ep_id, "art")
    manifest = core.read_json(art / "manifest.json")
    if not manifest or not (art / "key.png").exists():
        raise core.LofiError(f"{ep_id}: no key art yet — run `lofi art {ep_id}` first")
    v = core.config().get("video", {})
    fps, w, h = int(v.get("fps", 30)), int(v.get("width", 1920)), int(v.get("height", 1080))
    seconds = float(ep["art"].get("loop_seconds", 12))
    if not 8 <= seconds <= 20:
        raise core.LofiError(f"{ep_id}: art.loop_seconds must be 8–20 (is {seconds})")
    dst = art / "loop.mp4"
    clip = art / manifest["clip"] if manifest.get("clip") else None
    if clip and clip.exists():
        info = from_clip(clip, dst, seconds, fps, w, h, log=log)
    else:
        motion = ep["art"].get("motion") or ["dust", "lamp_flicker"]
        anchors = {**(manifest.get("anchors") or {}), **(ep["art"].get("anchors") or {})}
        depth = art / "depth.png"
        info = from_code(art / "key.png", depth if depth.exists() else None, anchors, motion, dst, seconds, fps, w, h, log=log)
        if "record" in motion and not anchors.get("record"):
            log("  note: 'record' motion needs art.anchors.record [x, y, r] to know where the turntable is — skipped")
    manifest["loop"] = info
    if info["route"] == "code" and not any("motion:" in t for t in manifest["tools"]):
        manifest["tools"].append("motion: built in code (parallax, particles, light flicker)")
    core.write_json(art / "manifest.json", manifest)
    return dst
