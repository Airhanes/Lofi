"""`lofi scan` (tracks → tracklist) and the mix: equal-power crossfades + two-pass loudnorm."""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import catalog, core, timeline


# ---------------------------------------------------------------- scan

def audio_hash(path: Path) -> str:
    """sha256 of the decoded audio, so renaming or re-tagging a file doesn't dodge the reuse guard."""
    proc = core.run(["ffmpeg", "-hide_banner", "-nostdin", "-v", "error", "-i", str(path), "-map", "0:a:0",
                     "-f", "hash", "-hash", "sha256", "-"])
    return proc.stdout.decode().strip().split("=", 1)[-1]


def track_title(path: Path, probe: dict) -> str:
    tags = {k.lower(): v for k, v in (probe.get("format", {}).get("tags") or {}).items()}
    for s in probe.get("streams", []):
        tags.update({k.lower(): v for k, v in (s.get("tags") or {}).items() if k.lower() == "title"})
    title = (tags.get("title") or "").strip()
    if not title:
        title = re.sub(r"^\d+\s*[-_. ]\s*", "", path.stem)        # "03 - rainy glass" → "rainy glass"
        title = re.sub(r"[_]+", " ", title).strip()
    return title.lower() if not title.startswith("PLACEHOLDER") else title


def probe_track(path: Path) -> dict:
    probe = core.ffprobe_json(path)
    if not any(s.get("codec_type") == "audio" for s in probe.get("streams", [])):
        raise core.LofiError(f"{path.name}: no audio stream")
    return {
        "file": path.name,
        "title": track_title(path, probe),
        "duration": round(float(probe["format"]["duration"]), 3),
        "hash": audio_hash(path),
    }


def scan(ep_id: str) -> tuple[dict, list[str]]:
    """Merge the files in tracks/ into the tracklist, keeping the owner's order. Returns (episode, notes)."""
    ep = core.load_episode(ep_id)
    tdir = core.ep_path(ep_id, "tracks")
    files = sorted(p for p in tdir.iterdir() if p.suffix.lower() in core.AUDIO_EXTS) if tdir.exists() else []
    old = ep["music"].get("tracklist") or []
    by_file = {t["file"]: t for t in old}
    notes: list[str] = []
    fresh = {p.name: probe_track(p) for p in files}

    merged = []
    for t in old:                                     # owner's order first
        if t["file"] not in fresh:
            notes.append(f"removed {t['file']} (file is gone)")
            continue
        new = fresh[t["file"]]
        if t.get("hash") and t["hash"] != new["hash"]:
            notes.append(f"{t['file']}: audio changed since the last scan")
        new["title"] = t.get("title") or new["title"]  # keep owner-edited titles
        merged.append(new)
    for name, new in fresh.items():                   # new files go on the end
        if name not in by_file:
            notes.append(f"added {name} ({new['duration']:.0f}s)")
            merged.append(new)

    changed = [(t["file"], t["hash"]) for t in merged] != [(t.get("file"), t.get("hash")) for t in old]
    if changed and ep["music"].get("approved"):
        # approval covers a specific tracklist; a different one needs the owner's ears again
        notes.append("WARNING: the tracklist changed after it was approved — music.approved reset to false; "
                     "re-listen and re-approve")
        ep["music"]["approved"] = False
    ep["music"]["tracklist"] = merged
    for problem in catalog.conflicts(ep_id, merged, catalog.read()):
        notes.append("REUSE: " + problem)
    total = timeline.mix_duration([t["duration"] for t in merged], ep["music"].get("crossfade_seconds", 4))
    target = ep["music"].get("target_minutes", 60) * 60
    notes.append(f"{len(merged)} tracks → {total / 60:.1f} min mix (target {target / 60:.0f} min)")
    core.save_episode(ep)
    return ep, notes


# ---------------------------------------------------------------- loudness

def measure(src: Path) -> dict:
    """loudnorm measurement pass → input_i (LUFS), input_tp (dBTP), input_lra, input_thresh, target_offset."""
    cfg = core.config().get("mix", {})
    af = f"loudnorm=I={cfg.get('target_lufs', -14)}:TP={cfg.get('loudnorm_true_peak', -1.5)}:LRA=11:print_format=json"
    proc = core.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(src), "-map", "0:a:0", "-af", af, "-f", "null", "-"])
    err = proc.stderr.decode(errors="replace")
    blob = json.loads(err[err.rindex("{"): err.rindex("}") + 1])
    return {k: (v if k == "normalization_type" else float(v)) for k, v in blob.items()}


def loudness(path: Path) -> tuple[float, float]:
    """(integrated LUFS, true peak dBTP) of a file's first audio stream."""
    m = measure(path)
    return m["input_i"], m["input_tp"]


# ---------------------------------------------------------------- mix

def _chain(n: int, crossfade: float, sr: int) -> str:
    """filter_complex joining n inputs with equal-power (qsin) crossfades → [mix]."""
    parts = [f"[{i}:a:0]aresample={sr},aformat=sample_fmts=fltp:channel_layouts=stereo[t{i}]" for i in range(n)]
    if n == 1:
        parts.append("[t0]anull[mix]")
        return ";".join(parts)
    prev = "t0"
    for i in range(1, n):
        out = "mix" if i == n - 1 else f"x{i}"
        if crossfade > 0:
            parts.append(f"[{prev}][t{i}]acrossfade=d={crossfade}:c1=qsin:c2=qsin[{out}]")
        else:
            parts.append(f"[{prev}][t{i}]concat=n=2:v=0:a=1[{out}]")
        prev = out
    return ";".join(parts)


def build(ep: dict, *, log=print) -> tuple[Path, list[dict]]:
    """Render out/mix.flac (normalised) and out/timestamps.json. Returns (mix path, timestamps)."""
    ep_id = ep["id"]
    tracks = ep["music"].get("tracklist") or []
    if not tracks:
        raise core.LofiError(f"{ep_id}: tracklist is empty — drop audio in tracks/ and run `lofi scan {ep_id}`")
    xf = float(ep["music"].get("crossfade_seconds", 4))
    stamps = timeline.timestamps(tracks, xf)
    sr = int(core.config().get("audio", {}).get("sample_rate", 48000))
    tdir, out = core.ep_path(ep_id, "tracks"), core.ep_path(ep_id, "out")
    out.mkdir(parents=True, exist_ok=True)
    inputs = []
    for t in tracks:
        p = tdir / t["file"]
        if not p.exists():
            raise core.LofiError(f"{ep_id}: missing track file {p} — re-run `lofi scan {ep_id}`")
        inputs += ["-i", str(p)]

    raw = out / "mix_raw.flac"
    log(f"  mixing {len(tracks)} tracks with {xf:g}s equal-power crossfades")
    core.ffmpeg(*inputs, "-filter_complex", _chain(len(tracks), xf, sr), "-map", "[mix]",
                "-ar", str(sr), "-c:a", "flac", str(raw))

    cfg = core.config().get("mix", {})
    target, tp = cfg.get("target_lufs", -14.0), cfg.get("loudnorm_true_peak", -1.5)
    log("  loudnorm pass 1 (measure)")
    m = measure(raw)
    log(f"    measured {m['input_i']:.1f} LUFS, {m['input_tp']:.1f} dBTP, LRA {m['input_lra']:.1f}")
    af = (f"loudnorm=I={target}:TP={tp}:LRA=11:measured_I={m['input_i']}:measured_TP={m['input_tp']}"
          f":measured_LRA={m['input_lra']}:measured_thresh={m['input_thresh']}:offset={m['target_offset']}"
          f":linear=true:print_format=json,aresample={sr}")
    mix = out / "mix.flac"
    log("  loudnorm pass 2 (apply)")
    core.ffmpeg("-i", str(raw), "-af", af, "-ar", str(sr), "-c:a", "flac", str(mix))
    raw.unlink(missing_ok=True)

    actual = core.media_duration(mix)
    expected = timeline.mix_duration([t["duration"] for t in tracks], xf)
    core.write_json(out / "timestamps.json", {
        "episode": ep_id, "crossfade_seconds": xf, "expected_duration": round(expected, 3),
        "mix_duration": round(actual, 3), "tracks": stamps,
    })
    return mix, stamps
