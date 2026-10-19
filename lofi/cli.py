"""lofi — the channel's production CLI."""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from typing import Optional

import typer

from . import core
from .season import SEASON_1

app = typer.Typer(add_completion=False, no_args_is_help=True, help=__doc__)


def fail(msg: str) -> None:
    typer.secho(msg, fg=typer.colors.RED, err=True)
    raise typer.Exit(1)


def guarded(fn):
    """Turn LofiError into a clean red message + exit 1."""
    import functools

    @functools.wraps(fn)
    def wrapper(*a, **kw):
        try:
            return fn(*a, **kw)
        except core.LofiError as e:
            fail(str(e))
    return wrapper


# ---------------------------------------------------------------- toolchain

@app.command()
@guarded
def doctor(fix: bool = typer.Option(False, help="pip-install missing Python packages (and apt-get ffmpeg if root)")):
    """Check the toolchain: Python, ffmpeg/ffprobe (+ filters), packages, fonts."""
    ok = True

    def line(good: bool, what: str, note: str = ""):
        nonlocal ok
        ok &= good
        typer.echo(f"  {'✓' if good else '✗'} {what}" + (f" — {note}" if note else ""))

    line(sys.version_info >= (3, 11), f"python {sys.version.split()[0]}", "" if sys.version_info >= (3, 11) else "need 3.11+")
    if fix and not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        subprocess.run(["apt-get", "install", "-y", "ffmpeg"], check=False)
    for tool in ("ffmpeg", "ffprobe"):
        line(shutil.which(tool) is not None, tool, shutil.which(tool) or "install ffmpeg (apt install ffmpeg / brew install ffmpeg)")
    if shutil.which("ffmpeg"):
        filters = subprocess.run(["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True).stdout
        encoders = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
        for f in ("drawtext", "loudnorm", "acrossfade", "xfade", "showwaves"):
            line(f" {f} " in filters, f"ffmpeg filter {f}", "" if f" {f} " in filters else "rebuild ffmpeg with libfreetype")
        line("libx264" in encoders, "ffmpeg encoder libx264")
    required = {"typer": "typer", "yaml": "PyYAML", "PIL": "Pillow", "numpy": "numpy", "pytest": "pytest"}
    optional = {"googleapiclient": "google-api-python-client", "google_auth_oauthlib": "google-auth-oauthlib"}
    missing = [pkg for mod, pkg in required.items() if importlib.util.find_spec(mod) is None]
    if fix and missing:
        subprocess.run([sys.executable, "-m", "pip", "install", *missing], check=False)
        missing = [pkg for mod, pkg in required.items() if importlib.util.find_spec(mod) is None]
    for mod, pkg in required.items():
        line(pkg not in missing, pkg)
    for mod, pkg in optional.items():
        have = importlib.util.find_spec(mod) is not None
        typer.echo(f"  {'✓' if have else '·'} {pkg} (uploads only)")
    try:
        genai = importlib.util.find_spec("google.genai") is not None
    except ModuleNotFoundError:
        genai = False
    typer.echo(f"  {'✓' if genai else '·'} google-genai (API art generation only)")
    try:
        line(True, f"display font {core.font_path('display')}")
        line(True, f"body font {core.font_path('body')}")
    except core.LofiError as e:
        line(False, "fonts", str(e))
    if not ok:
        fail("toolchain incomplete — fix the ✗ items (or run `lofi doctor --fix`)")
    typer.secho("toolchain ok", fg=typer.colors.GREEN)


# ---------------------------------------------------------------- episodes

@app.command()
@guarded
def new(ep_id: str, theme: str, stem: Optional[str] = typer.Option(None, help="title stem (defaults from the Season 1 plan)"),
        force: bool = typer.Option(False, help="overwrite an existing episode.yaml")):
    """Create episodes/<id>/ with episode.yaml, tracks/, art/, out/."""
    d = core.ep_dir(ep_id)
    if (d / "episode.yaml").exists() and not force:
        fail(f"{ep_id} already exists (use --force to overwrite)")
    plan = SEASON_1.get(ep_id, {})
    stem = stem or plan.get("title_stem")
    if not stem:
        fail("not in the Season 1 plan — pass --stem \"<lowercase title stem + one emoji>\"")
    for sub in ("tracks", "art", "out"):
        (d / sub).mkdir(parents=True, exist_ok=True)
        (d / sub / ".gitkeep").touch()
    thumb = plan.get("thumb", ["", ""])
    ep = {
        "id": ep_id,
        "title": core.title_for(stem),
        "theme": theme,
        "director_note": "",
        "music": {"bpm": plan.get("bpm", [74, 80]), "palette": plan.get("palette", []), "target_minutes": 60,
                  "crossfade_seconds": 4, "credits": "", "tracklist": [], "approved": False},
        "art": {"scene_prompt": plan.get("scene_prompt") or theme,
                "loop_seconds": 12, "motion": plan.get("motion", ["dust", "lamp_flicker"]), "anchors": {},
                "realistic": None, "approved": False},
        "thumbnail": {"text_a": thumb[0], "text_b": thumb[1]},
        "overlays": {"now_playing": True, "visualizer": False},
    }
    core.save_episode(ep)
    typer.echo(f"created {d / 'episode.yaml'}")


@app.command()
@guarded
def prompts(ep_id: str):
    """Write episodes/<id>/suno_prompts.md (~25 prompts; keep the best ~20)."""
    from . import prompts as p
    p.write(ep_id)
    typer.echo(f"wrote {core.ep_path(ep_id, 'suno_prompts.md')}")


@app.command()
@guarded
def art(ep_id: str, generator: Optional[str] = typer.Option(None, help="auto | google | owner"),
        video: bool = typer.Option(True, help="also generate a motion clip when using Google"),
        force: bool = typer.Option(False, help="replace approved art (resets art.approved)")):
    """Key art from Google's models, or the owner's files in art/. Writes prompt.txt and REVIEW.md."""
    from . import art as a
    m = a.run(ep_id, generator=generator, video=video, force=force)
    typer.echo(f"art: {m['source']} → {core.ep_path(ep_id, 'art', 'key.png')}  (review: art/REVIEW.md)")


@app.command()
@guarded
def loop(ep_id: str):
    """Build the seamless 1920×1080/30 fps motion loop → art/loop.mp4."""
    from . import loop as lp
    typer.echo(f"loop → {lp.run(ep_id)}")


@app.command()
@guarded
def scan(ep_id: str):
    """Hash and probe tracks/ into the tracklist (keeps the owner's order)."""
    from . import mix
    _, notes = mix.scan(ep_id)
    for n in notes:
        typer.secho("  " + n, fg=typer.colors.RED if n.startswith(("WARNING", "REUSE")) else None)


@app.command()
@guarded
def render(ep_id: str, proof: bool = typer.Option(False, "--proof", help="skip approval gates, burn PROOF — NOT FOR UPLOAD, never touch catalog.csv")):
    """Mix + video → out/final.mp4, thumbnails, description. Refuses without owner approvals (unless --proof)."""
    from . import render as r
    r.run(ep_id, proof=proof)
    typer.secho(f"rendered {core.ep_path(ep_id, 'out', 'final.mp4')} — run `lofi qa {ep_id}`", fg=typer.colors.GREEN)


@app.command()
@guarded
def qa(ep_id: str):
    """Check the render against the spec → out/qa.md. Exit 1 on any failure."""
    from . import qa as q
    report = q.run(ep_id)
    path = core.ep_path(ep_id, "out", "qa.md")
    if report.failed:
        fail(f"QA FAILED — {path}")
    typer.secho(f"QA {'proof OK (release checks waived)' if report.proof else 'PASS'} — {path}", fg=typer.colors.GREEN)


@app.command()
@guarded
def short(ep_id: str):
    """30–45 s vertical teaser with the title on screen → out/short.mp4."""
    from . import short as s
    typer.echo(f"short → {s.run(ep_id)}")


@app.command()
@guarded
def season(qa_after: bool = typer.Option(True, "--qa/--no-qa"), shorts: bool = typer.Option(True, "--shorts/--no-shorts")):
    """Render every episode whose art and music are approved (then Short + QA)."""
    from . import qa as q, render as r, short as s
    ready, skipped, failed = [], [], []
    for ep_id in core.list_episodes():
        ep = core.load_episode(ep_id)
        if not (ep["art"].get("approved") and ep["music"].get("approved")):
            skipped.append(ep_id)
            continue
        ready.append(ep_id)
    typer.echo(f"approved: {', '.join(ready) or 'none'} · waiting on the owner: {', '.join(skipped) or 'none'}")
    for ep_id in ready:
        try:
            r.run(ep_id)
            if shorts:
                s.run(ep_id)
            if qa_after and q.run(ep_id).failed:
                failed.append(ep_id)
        except core.LofiError as e:
            typer.secho(str(e), fg=typer.colors.RED, err=True)
            failed.append(ep_id)
    if failed:
        fail(f"failed: {', '.join(failed)}")
    typer.secho(f"season done: {len(ready)} rendered", fg=typer.colors.GREEN)


@app.command()
@guarded
def upload(ep_id: str, short_: bool = typer.Option(False, "--short", help="upload out/short.mp4 instead")):
    """Upload as PRIVATE with the thumbnail set (disabled unless YT_UPLOAD_ENABLED=1)."""
    from . import upload as u
    u.run(ep_id, short=short_)


@app.command()
@guarded
def placeholder(ep_id: str, audio: bool = typer.Option(True, "--audio/--no-audio"), art_: bool = typer.Option(True, "--art/--no-art"),
                tracks: int = 3, seconds: float = 62.0):
    """Generate PLACEHOLDER audio and art for pipeline proofs (never releasable)."""
    from . import placeholder as ph
    ep = core.load_episode(ep_id)
    if audio:
        for p in ph.make_audio(ep, core.ep_path(ep_id, "tracks"), tracks, seconds):
            typer.echo(f"  audio → {p}")
    if art_:
        art_dir = core.ep_path(ep_id, "art")
        if ep["art"].get("approved"):
            fail(f"{ep_id}: art is approved — not overwriting it with placeholder art")
        anchors = ph.make_art(ep_id, art_dir)
        from .art import review_md, sha, image_prompt, video_prompt
        manifest = {"source": "placeholder", "tools": ["key art: PLACEHOLDER drawn in code (not for release)"],
                    "realistic_hint": False, "anchors": anchors, "key_sha": sha(art_dir / "key.png"),
                    "has_depth": True, "has_clip": False, "clip": None}
        core.write_json(art_dir / "manifest.json", manifest)
        (art_dir / "prompt.txt").write_text(f"IMAGE PROMPT\n{image_prompt(ep)}\n\nVIDEO PROMPT (image-to-video)\n{video_prompt(ep)}\n")
        (art_dir / "REVIEW.md").write_text(review_md(ep, manifest))
        typer.echo(f"  art → {art_dir / 'key.png'}")


if __name__ == "__main__":
    app()
