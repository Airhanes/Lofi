"""`lofi render <id> [--proof]` — mix + looped video → out/final.mp4, then thumbnails and metadata."""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from . import catalog, core, meta, mix, thumb, timeline
from .loop import x264_args


def is_placeholder(t: dict) -> bool:
    return "PLACEHOLDER" in t.get("title", "").upper() or t.get("file", "").lower().startswith("placeholder")


def gate(ep: dict, *, proof: bool) -> tuple[list[str], list[str]]:
    """(blockers, warnings). --proof turns the approval/release blockers into warnings."""
    hard, soft = [], []
    release = soft if proof else hard
    if not ep["art"].get("approved"):
        release.append("art.approved is not true (owner only)")
    if not ep["music"].get("approved"):
        release.append("music.approved is not true (owner only)")
    tracks = ep["music"].get("tracklist") or []
    if not tracks:
        hard.append(f"tracklist is empty — drop audio into tracks/ and run `lofi scan {ep['id']}`")
    if any(is_placeholder(t) for t in tracks):
        release.append("tracklist contains PLACEHOLDER audio")
    manifest = core.read_json(core.ep_path(ep["id"], "art", "manifest.json"), {}) or {}
    if manifest.get("source") == "placeholder":
        release.append("key art is PLACEHOLDER art")
    for problem in catalog.conflicts(ep["id"], tracks, catalog.read()):
        release.append("track reuse: " + problem)
    if not (ep.get("director_note") or "").strip():
        soft.append("director_note is empty — required before release (QA will fail)")
    if not core.ep_path(ep["id"], "art", "loop.mp4").exists():
        hard.append(f"no loop yet — run `lofi loop {ep['id']}`")
    return hard, soft


def verify_tracks(ep: dict) -> list[str]:
    """The audio must be exactly what was scanned (and approved)."""
    problems = []
    for t in ep["music"].get("tracklist") or []:
        p = core.ep_path(ep["id"], "tracks", t["file"])
        if not p.exists():
            problems.append(f"{t['file']} is missing")
        elif mix.audio_hash(p) != t["hash"]:
            problems.append(f"{t['file']} changed since `lofi scan` — re-scan and re-approve")
    return problems


def _esc(path: Path) -> str:
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def overlay_graph(ep: dict, stamps: list[dict], total: float, work: Path, *, proof: bool) -> tuple[str, bool]:
    """filter_complex script: lower-thirds per track window, optional visualizer, proof watermark."""
    cfg = core.config()
    lt = float(cfg.get("overlays", {}).get("lower_third_seconds", 10))
    body, display = _esc(Path(core.font_path("body"))), _esc(Path(core.font_path("display")))
    pal = core.palette()
    hexc = lambda k, a=1.0: "0x%02X%02X%02X@%.2f" % (*pal[k], a)
    chains, v = [], "[0:v]"
    audio_out = False
    if ep["overlays"].get("visualizer"):
        chains.append("[1:a]asplit=2[aout][aviz]")
        chains.append(f"[aviz]showwaves=s=1920x120:mode=cline:rate=30:colors={hexc('amber')},format=rgba,"
                      f"colorchannelmixer=aa=0.22[wave]")
        chains.append(f"{v}[wave]overlay=0:H-h-24:shortest=1[vz]")
        v, audio_out = "[vz]", True
    steps = []
    if ep["overlays"].get("now_playing"):
        for s in stamps:
            start = s["start"] + (1.5 if s["index"] > 1 else 2.0)   # let the crossfade land first
            end = min(start + lt, total - 0.5)
            if end - start < 3:
                continue
            tf = work / f"np_{s['index']:02d}.txt"
            tf.write_text(core.strip_emoji(s["title"]))
            alpha = f"if(lt(t,{start + 0.8:.3f}),(t-{start:.3f})/0.8,if(gt(t,{end - 0.8:.3f}),({end:.3f}-t)/0.8,1))"
            enable = f"between(t,{start:.3f},{end:.3f})"
            steps.append(f"drawtext=fontfile='{body}':text='now playing':fontsize=26:fontcolor={hexc('amber')}:"
                         f"x=72:y=h-188:alpha='{alpha}':enable='{enable}'")
            steps.append(f"drawtext=fontfile='{display}':textfile='{_esc(tf)}':fontsize=46:fontcolor={hexc('cream')}:"
                         f"shadowcolor={hexc('indigo', 0.8)}:shadowx=2:shadowy=3:x=72:y=h-150:alpha='{alpha}':enable='{enable}'")
    if proof:
        pf = work / "proof.txt"
        pf.write_text(core.PROOF_TEXT)
        steps.append(f"drawtext=fontfile='{display}':textfile='{_esc(pf)}':fontsize=64:fontcolor=0xFF5A5A@0.85:"
                     f"box=1:boxcolor=0x000000@0.45:boxborderw=24:x=(w-text_w)/2:y=60")
    chains.append(f"{v}{','.join(steps) if steps else 'null'},format=yuv420p[vout]")
    return ";\n".join(chains), audio_out


def run(ep_id: str, *, proof: bool = False, log=print) -> dict:
    core.need("ffmpeg", "ffprobe")
    ep = core.load_episode(ep_id)
    hard, soft = gate(ep, proof=proof)
    changed = verify_tracks(ep)
    (soft if proof else hard).extend(changed)
    for w in soft:
        log(f"  ! {w}")
    if hard:
        raise core.LofiError(f"{ep_id}: render refused:\n  - " + "\n  - ".join(hard))

    out = core.ep_path(ep_id, "out")
    out.mkdir(parents=True, exist_ok=True)
    work = out / ".work"
    work.mkdir(exist_ok=True)
    log(f"[{ep_id}] mix")
    mix_path, stamps = mix.build(ep, log=log)
    total = core.media_duration(mix_path)

    v, a = core.config().get("video", {}), core.config().get("audio", {})
    fps = int(v.get("fps", 30))
    loop = core.ep_path(ep_id, "art", "loop.mp4")
    final = out / "final.mp4"
    audio_args = ["-c:a", "aac", "-b:a", a.get("bitrate", "384k"), "-ar", str(a.get("sample_rate", 48000)), "-ac", "2"]
    fast = not proof and not ep["overlays"].get("now_playing") and not ep["overlays"].get("visualizer")
    if fast:
        log(f"[{ep_id}] video: fast path (looping the pre-encoded clip, no re-encode) → {total / 60:.1f} min")
        core.ffmpeg("-stream_loop", "-1", "-i", str(loop), "-i", str(mix_path), "-map", "0:v:0", "-map", "1:a:0",
                    "-c:v", "copy", *audio_args, "-t", f"{total:.3f}", "-movflags", "+faststart", str(final))
    else:
        log(f"[{ep_id}] video: overlay path (re-encode with "
            + ", ".join(x for x, on in (("now-playing cards", ep["overlays"].get("now_playing")),
                                        ("visualizer", ep["overlays"].get("visualizer")),
                                        ("PROOF watermark", proof)) if on) + f") → {total / 60:.1f} min")
        graph, audio_from_graph = overlay_graph(ep, stamps, total, work, proof=proof)
        script = work / "graph.txt"
        script.write_text(graph)
        core.ffmpeg("-stream_loop", "-1", "-i", str(loop), "-i", str(mix_path), "-filter_complex_script", str(script),
                    "-map", "[vout]", "-map", "[aout]" if audio_from_graph else "1:a:0",
                    *x264_args(fps), *audio_args, "-t", f"{total:.3f}", "-movflags", "+faststart", str(final))

    log(f"[{ep_id}] thumbnails + description")
    thumb.make(ep, proof=proof)
    meta.make(ep, stamps, total, proof=proof)
    record = {
        "episode": ep_id, "proof": proof, "rendered_at": dt.datetime.now().isoformat(timespec="seconds"),
        "path": "fast" if fast else "overlay", "mix_duration": round(total, 3),
        "expected_duration": round(timeline.mix_duration([t["duration"] for t in ep["music"]["tracklist"]],
                                                         float(ep["music"].get("crossfade_seconds", 4))), 3),
        "tracks": [t["hash"] for t in ep["music"]["tracklist"]],
    }
    core.write_json(out / "render.json", record)
    if proof:
        log(f"[{ep_id}] proof render — catalog.csv untouched")
    else:
        added = catalog.claim(ep_id, ep["music"]["tracklist"])
        log(f"[{ep_id}] catalog.csv: {added} new track(s) claimed for {ep_id}")
    return record
