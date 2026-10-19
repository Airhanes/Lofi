"""`lofi qa <id>` — check a render against the spec and write out/qa.md. Fails loudly."""

from __future__ import annotations

import datetime as dt
import re
import struct
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image

from . import catalog, core, mix, render, timeline

PASS, FAIL, WARN, WAIVED, INFO = "PASS", "FAIL", "WARN", "WAIVED", "INFO"
ICON = {PASS: "✅", FAIL: "❌", WARN: "⚠️", WAIVED: "➖", INFO: "ℹ️"}


class Report:
    def __init__(self, ep_id: str, proof: bool):
        self.ep_id, self.proof, self.rows = ep_id, proof, []

    def add(self, status: str, check: str, detail: str = ""):
        self.rows.append((status, check, detail))

    def check(self, ok: bool, check: str, detail: str = "", *, release: bool = False):
        """release=True checks are waived (not failed) on proof renders."""
        self.add(PASS if ok else (WAIVED if release and self.proof else FAIL), check, detail)

    @property
    def failed(self) -> bool:
        return any(s == FAIL for s, _, _ in self.rows)

    def markdown(self) -> str:
        verdict = "FAIL" if self.failed else ("PROOF OK — pipeline checks pass; release checks waived" if self.proof else "PASS")
        lines = [f"# qa — {self.ep_id}", "",
                 f"**{verdict}** · {dt.datetime.now().isoformat(timespec='seconds')}" + (" · proof render (not for upload)" if self.proof else ""),
                 "", "| | check | detail |", "|---|---|---|"]
        for s, c, d in self.rows:
            lines.append(f"| {ICON[s]} {s} | {c} | {d.replace('|', '/')} |")
        counts = {k: sum(1 for s, _, _ in self.rows if s == k) for k in ICON}
        lines += ["", " · ".join(f"{k.lower()}: {v}" for k, v in counts.items() if v)]
        return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- probes

def top_level_atoms(path: Path) -> list[str]:
    atoms = []
    with path.open("rb") as f:
        while True:
            head = f.read(8)
            if len(head) < 8:
                break
            size, kind = struct.unpack(">I4s", head)
            if size == 1:
                size = struct.unpack(">Q", f.read(8))[0]
                f.seek(size - 16, 1)
            elif size == 0:
                atoms.append(kind.decode(errors="replace"))
                break
            else:
                f.seek(size - 8, 1)
            atoms.append(kind.decode(errors="replace"))
    return atoms


def keyframe_times(path: Path) -> list[float]:
    proc = core.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                     "-show_entries", "frame=pts_time", "-of", "csv=p=0", str(path)])
    vals = (x.strip().strip(",") for x in proc.stdout.decode().split())
    return [float(x) for x in vals if x and x != "N/A"]


def decode_errors(path: Path) -> str:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-i", str(path), "-f", "null", "-"],
                          capture_output=True)
    return (proc.stderr.decode(errors="replace").strip() or ("" if proc.returncode == 0 else f"exit {proc.returncode}"))


def motion_stats(loop: Path) -> dict:
    """Motion in a loop at 192×108 gray: how much of the frame moves, and how big the seam jump is."""
    proc = core.run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-i", str(loop), "-vf",
                     "scale=192:108,format=gray", "-f", "rawvideo", "-"])
    frames = np.frombuffer(proc.stdout, np.uint8).reshape(-1, 108, 192).astype(np.int16)
    adj = np.abs(np.diff(frames, axis=0)).mean(axis=(1, 2))
    half = min(15, len(frames) - 1)
    moving = np.mean([(np.abs(frames[i + half] - frames[i]) > 6).mean() for i in range(0, len(frames) - half, 10)])
    seam = float(np.abs(frames[0] - frames[-1]).mean())
    return {"frames": len(frames), "adjacent_median": float(np.median(adj)), "adjacent_p95": float(np.percentile(adj, 95)),
            "seam": seam, "moving_fraction": float(moving)}


# ---------------------------------------------------------------- the checks

def run(ep_id: str, *, log=print) -> Report:
    ep = core.load_episode(ep_id)
    out, art = core.ep_path(ep_id, "out"), core.ep_path(ep_id, "art")
    rec = core.read_json(out / "render.json", {}) or {}
    r = Report(ep_id, proof=bool(rec.get("proof")))
    final = out / "final.mp4"
    cfg = core.config()
    tracks = ep["music"].get("tracklist") or []

    # -- approvals & provenance
    r.check(bool(ep["art"].get("approved")), "art approved by owner", "art.approved", release=True)
    r.check(bool(ep["music"].get("approved")), "music approved by owner", "music.approved", release=True)
    r.check(bool((ep.get("director_note") or "").strip()), "director's note present", "director_note", release=True)
    ph = [t["file"] for t in tracks if render.is_placeholder(t)]
    r.check(not ph, "no placeholder audio", ", ".join(ph) or "all tracks are real", release=True)
    manifest = core.read_json(art / "manifest.json", {}) or {}
    r.check(manifest.get("source") != "placeholder", "no placeholder art", f"art source: {manifest.get('source')}", release=True)

    # -- reuse
    problems = catalog.conflicts(ep_id, tracks, catalog.read())
    r.check(not problems, "no reused tracks", "; ".join(problems) or f"{len(tracks)} tracks, none used elsewhere")
    if rec and rec.get("tracks") != [t["hash"] for t in tracks]:
        r.add(FAIL, "render matches tracklist", "tracklist changed since this render — re-render")

    if not final.exists():
        r.add(FAIL, "final.mp4 exists", f"run `lofi render {ep_id}`")
        return _finish(r, out, log)

    # -- decode + container
    errs = decode_errors(final)
    r.check(not errs, "decodes cleanly", errs.splitlines()[0][:160] if errs else "ffmpeg decoded every frame with no errors")
    probe = core.ffprobe_json(final)
    vs = next((s for s in probe["streams"] if s["codec_type"] == "video"), {})
    aus = next((s for s in probe["streams"] if s["codec_type"] == "audio"), {})
    v = cfg.get("video", {})
    num, _, den = (vs.get("avg_frame_rate") or "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    r.check(vs.get("codec_name") == "h264" and vs.get("profile") == "High", "video codec H.264 High",
            f"{vs.get('codec_name')} {vs.get('profile')}")
    r.check((vs.get("width"), vs.get("height")) == (v.get("width", 1920), v.get("height", 1080)), "1920×1080",
            f"{vs.get('width')}×{vs.get('height')}")
    r.check(vs.get("pix_fmt") == "yuv420p", "yuv420p", str(vs.get("pix_fmt")))
    r.check(abs(fps - v.get("fps", 30)) < 0.01, "30 fps", f"{fps:.3f}")
    vbr = int(vs.get("bit_rate") or 0) / 1e6
    r.check(7.5 <= vbr <= 12.5, "video bitrate ~8–12 Mbps", f"{vbr:.1f} Mbps")
    kf = keyframe_times(final)
    gaps = np.diff(kf) if len(kf) > 1 else np.array([0.0])
    gop = float(v.get("gop_seconds", 2))
    r.check(bool(kf) and kf[0] == 0.0 and gaps.max() <= gop + 0.05, f"keyframe every {gop:g} s",
            f"{len(kf)} keyframes, max gap {gaps.max():.2f}s")
    a = cfg.get("audio", {})
    abr = int(aus.get("bit_rate") or 0) / 1000
    r.check(aus.get("codec_name") == "aac" and int(aus.get("sample_rate", 0)) == a.get("sample_rate", 48000)
            and aus.get("channels") == 2, "AAC 48 kHz stereo", f"{aus.get('codec_name')} {aus.get('sample_rate')} Hz {aus.get('channels')}ch")
    # ffmpeg's AAC encoder is asked for 384k but spends less on sparse material; report, don't fail
    r.add(PASS if abr >= 350 else WARN, f"audio bitrate {a.get('bitrate', '384k')}",
          f"{abr:.0f} kbps measured" + ("" if abr >= 350 else " — encoder undershoots on sparse audio; fine for YouTube, "
                                        "recheck with real tracks"))
    atoms = top_level_atoms(final)
    r.check("moov" in atoms and "mdat" in atoms and atoms.index("moov") < atoms.index("mdat"), "+faststart (moov before mdat)",
            " → ".join(atoms))

    # -- duration
    expected = timeline.mix_duration([t["duration"] for t in tracks], float(ep["music"].get("crossfade_seconds", 4)))
    fdur, vdur, adur = float(probe["format"]["duration"]), float(vs.get("duration", 0)), float(aus.get("duration", 0))
    worst = max(abs(fdur - expected), abs(vdur - expected), abs(adur - expected))
    r.check(worst <= 0.5, "duration matches mix math",
            f"expected {expected:.2f}s (Σ tracks − {len(tracks) - 1}×crossfade); file {fdur:.2f}s, video {vdur:.2f}s, audio {adur:.2f}s")
    target = float(ep["music"].get("target_minutes", 60)) * 60
    if not r.proof:
        r.check(abs(fdur - target) <= 0.1 * target, "length near target", f"{fdur / 60:.1f} min vs {target / 60:.0f} min target")

    # -- loudness
    m = cfg.get("mix", {})
    lufs, tp = mix.loudness(final)
    tol = float(m.get("qa_lufs_tolerance", 1.0))
    r.check(abs(lufs - m.get("target_lufs", -14)) <= tol, f"loudness {m.get('target_lufs', -14)} LUFS ±{tol:g}", f"{lufs:.2f} LUFS integrated")
    r.check(tp <= m.get("qa_true_peak_max", -1.0), f"true peak ≤ {m.get('qa_true_peak_max', -1.0)} dBTP", f"{tp:.2f} dBTP")

    # -- motion
    loop = art / "loop.mp4"
    if loop.exists():
        ms = motion_stats(loop)
        r.check(ms["moving_fraction"] >= 0.002 and ms["adjacent_median"] >= 0.05, "loop has real motion",
                f"{ms['moving_fraction'] * 100:.2f}% of frame changes per ½ s; layers: {', '.join((manifest.get('loop') or {}).get('layers', [])) or (manifest.get('loop') or {}).get('route', '?')}")
        r.check(ms["seam"] <= max(3 * ms["adjacent_p95"], 0.5), "loop seam invisible",
                f"last→first jump {ms['seam']:.2f} vs typical frame step {ms['adjacent_median']:.2f}")
        lk = core.ffprobe_json(loop)
        ldur = float(lk["format"]["duration"])
        r.check(8 <= ldur <= 20.05, "loop 8–20 s", f"{ldur:.2f}s")

    # -- description & chapters
    desc_path = out / "description.txt"
    desc = desc_path.read_text() if desc_path.exists() else ""
    chapters = timeline.parse_chapters(desc)
    problems = timeline.validate_chapters(chapters, fdur)
    r.check(not problems, "chapters valid", "; ".join(problems) or f"{len(chapters)} chapters from 0:00, each ≥ 10 s")
    stamps = core.read_json(out / "timestamps.json", {}) or {}
    starts = [int(t["start"]) for t in stamps.get("tracks", [])]
    r.check([c[0] for c in chapters] == starts, "chapters match timestamps.json", f"{len(starts)} track starts")
    note = (ep.get("director_note") or "").strip()
    r.check(bool(note) and desc.startswith(note), "description opens with director's note", "", release=True)
    tags_in_desc = re.findall(r"(?<!\S)#\w+", desc)
    r.check(1 <= len(tags_in_desc) <= 3, "≤ 3 hashtags", " ".join(tags_in_desc))
    r.check(len(desc) <= 5000 and "<" not in desc and ">" not in desc, "description fits YouTube limits",
            f"{len(desc)} chars, no angle brackets")
    r.check("credits" in desc and "music —" in desc, "credits name the tools", "")
    title = ep.get("title", "")
    r.check(0 < len(title) <= 100 and title == title.lower(), "title lowercase, ≤ 100 chars", f"{len(title)} chars")
    tags = cfg.get("tags", [])
    r.check(sum(len(t) + 1 for t in tags) <= 500, "tags ≤ 500 chars", f"{len(tags)} tags")
    meta = core.read_json(out / "metadata.json", {}) or {}
    r.add(INFO, "altered/synthetic content setting", "ON — imagery treated as realistic" if meta.get("contains_synthetic_media")
          else "off (set art.realistic: true if the imagery looks photoreal)")

    # -- thumbnails
    for variant in ("a", "b"):
        p = out / f"thumb_{variant}.jpg"
        if not p.exists():
            r.add(FAIL, f"thumbnail {variant.upper()}", "missing")
            continue
        im = Image.open(p)
        words = len(((ep.get("thumbnail") or {}).get(f"text_{variant}") or "").split())
        r.check(im.format == "JPEG" and im.size == (1280, 720) and p.stat().st_size < 2 * 1024 * 1024 and 2 <= words <= 4,
                f"thumbnail {variant.upper()} spec", f"{im.format} {im.size[0]}×{im.size[1]}, {p.stat().st_size / 1024:.0f} KB, {words} words")

    # -- short
    sp = out / "short.mp4"
    if sp.exists():
        sprobe = core.ffprobe_json(sp)
        ss = next((s for s in sprobe["streams"] if s["codec_type"] == "video"), {})
        sd = float(sprobe["format"]["duration"])
        r.check((ss.get("width"), ss.get("height")) == (1080, 1920) and 29.9 <= sd <= 45.2
                and any(s["codec_type"] == "audio" for s in sprobe["streams"]), "short 1080×1920, 30–45 s",
                f"{ss.get('width')}×{ss.get('height')}, {sd:.1f}s")
    else:
        r.add(WARN, "short", f"not made yet — `lofi short {ep_id}`")
    return _finish(r, out, log)


def _finish(r: Report, out: Path, log) -> Report:
    out.mkdir(parents=True, exist_ok=True)
    (out / "qa.md").write_text(r.markdown())
    for s, c, d in r.rows:
        if s in (FAIL, WARN, WAIVED):
            log(f"  {s:6} {c} — {d}")
    return r
