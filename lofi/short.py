"""`lofi short <id>` — a 30–45 s vertical (1080×1920) teaser with the title on screen → out/short.mp4."""

from __future__ import annotations

import textwrap
from pathlib import Path

from . import core
from .loop import x264_args
from .render import _esc


def pick_start(stamps: list[dict], total: float, seconds: float) -> float:
    """Start inside track 2 (past the crossfade) when there is one — a settled groove, not an intro."""
    start = stamps[1]["start"] + 12 if len(stamps) > 1 else 5.0
    return max(0.0, min(start, total - seconds - 1))


def run(ep_id: str, *, log=print) -> str:
    ep = core.load_episode(ep_id)
    out, art = core.ep_path(ep_id, "out"), core.ep_path(ep_id, "art")
    mix_path, loop = out / "mix.flac", art / "loop.mp4"
    stamps_doc = core.read_json(out / "timestamps.json")
    if not mix_path.exists() or not stamps_doc or not loop.exists():
        raise core.LofiError(f"{ep_id}: render the episode first (`lofi render {ep_id}`)")
    rec = core.read_json(out / "render.json", {}) or {}
    total = core.media_duration(mix_path)
    seconds = float(core.config().get("short", {}).get("seconds", 40))
    seconds = max(30.0, min(45.0, seconds, total))
    start = pick_start(stamps_doc["tracks"], total, seconds)

    work = out / ".work"
    work.mkdir(exist_ok=True)
    stem = core.strip_emoji(ep["title"].split(" soulful lofi")[0])
    title_file = work / "short_title.txt"
    title_file.write_text("\n".join(textwrap.wrap(stem, 16)))
    sub_file = work / "short_sub.txt"
    sub_file.write_text("soulful lofi · full hour on the channel")
    display, body = _esc(Path(core.font_path("display"))), _esc(Path(core.font_path("body")))
    pal = core.palette()
    hexc = lambda k, a=1.0: "0x%02X%02X%02X@%.2f" % (*pal[k], a)

    focus = ((ep["art"].get("anchors") or {}).get("record") or [0.5])[0]
    v = core.config().get("video", {})
    fps = int(v.get("fps", 30))
    steps = [
        "scale=-2:1920",
        f"crop=1080:1920:'min(max(iw*{focus}-540,0),iw-1080)':0",
        f"drawbox=x=0:y=0:w=iw:h=520:color={hexc('indigo', 0.55)}:t=fill",
        f"drawtext=fontfile='{display}':textfile='{_esc(title_file)}':fontsize=96:line_spacing=6:fontcolor={hexc('mustard')}:"
        f"shadowcolor={hexc('indigo', 0.9)}:shadowx=3:shadowy=4:x=(w-text_w)/2:y=170",
        f"drawtext=fontfile='{body}':textfile='{_esc(sub_file)}':fontsize=40:fontcolor={hexc('cream')}:x=(w-text_w)/2:y=h-260",
    ]
    if rec.get("proof"):
        pf = work / "proof.txt"
        pf.write_text(core.PROOF_TEXT)
        steps.append(f"drawtext=fontfile='{display}':textfile='{_esc(pf)}':fontsize=48:fontcolor=0xFF5A5A@0.9:"
                     f"box=1:boxcolor=0x000000@0.5:boxborderw=18:x=(w-text_w)/2:y=60")
    steps.append("format=yuv420p")
    fade_out = seconds - 2.5
    dst = out / "short.mp4"
    a = core.config().get("audio", {})
    log(f"[{ep_id}] short: {seconds:.0f}s from {start:.0f}s into the mix")
    core.ffmpeg("-stream_loop", "-1", "-i", str(loop), "-ss", f"{start:.3f}", "-t", f"{seconds:.3f}", "-i", str(mix_path),
                "-filter_complex", f"[0:v]{','.join(steps)}[v];[1:a]afade=t=in:d=1.5,afade=t=out:st={fade_out:.3f}:d=2.5[a]",
                "-map", "[v]", "-map", "[a]", *x264_args(fps), "-c:a", "aac", "-b:a", "256k",
                "-ar", str(a.get("sample_rate", 48000)), "-ac", "2", "-t", f"{seconds:.3f}", "-movflags", "+faststart", str(dst))
    return str(dst)
