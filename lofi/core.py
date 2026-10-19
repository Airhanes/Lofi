"""Shared plumbing: repo paths, config, episode.yaml I/O, subprocess helpers, fonts."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(os.environ.get("LOFI_ROOT", Path(__file__).resolve().parent.parent))
EPISODES = ROOT / "episodes"
BRAND = ROOT / "brand"
CATALOG = ROOT / "catalog.csv"

AUDIO_EXTS = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".aiff", ".aif"}
PROOF_TEXT = "PROOF — NOT FOR UPLOAD"


class LofiError(RuntimeError):
    """A pipeline step refused to run or failed; the message is shown to the owner."""


# ---------------------------------------------------------------- config

@lru_cache(maxsize=1)
def config() -> dict:
    path = ROOT / "config.yaml"
    return yaml.safe_load(path.read_text()) if path.exists() else {}


def load_env() -> None:
    """Load KEY=VALUE lines from .env into os.environ (without overriding real env vars)."""
    path = ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# ---------------------------------------------------------------- episodes

def ep_dir(ep_id: str) -> Path:
    return EPISODES / ep_id


def ep_path(ep_id: str, *parts: str) -> Path:
    return ep_dir(ep_id).joinpath(*parts)


def load_episode(ep_id: str) -> dict:
    path = ep_path(ep_id, "episode.yaml")
    if not path.exists():
        raise LofiError(f"no episode {ep_id!r} — create it with `lofi new {ep_id} \"<theme>\"`")
    return yaml.safe_load(path.read_text())


def _y(value) -> str:
    """One YAML scalar or flow collection, on one line."""
    return yaml.safe_dump(value, default_flow_style=True, allow_unicode=True, width=10_000).strip().removesuffix("\n...").strip()


def _block(value, indent: int) -> str:
    text = yaml.safe_dump(value, default_flow_style=False, allow_unicode=True, sort_keys=False, width=10_000)
    pad = " " * indent
    return "\n".join(pad + line for line in text.rstrip().splitlines())


def dump_episode(ep: dict) -> str:
    """Render episode.yaml in its canonical, commented layout.

    PyYAML drops comments, so every save rewrites the file from this template —
    the owner-facing comments survive `lofi scan` and friends.
    """
    m, a, o = ep.get("music", {}), ep.get("art", {}), ep.get("overlays", {})
    t = ep.get("thumbnail", {})
    known_music = {"bpm", "palette", "target_minutes", "crossfade_seconds", "tracklist", "approved", "credits"}
    known_art = {"scene_prompt", "loop_seconds", "approved", "motion", "anchors", "realistic"}
    note = ep.get("director_note") or ""
    note_comment = "# 2–3 lines written by the owner; required for release"
    lines = [
        f"id: {ep['id']}",
        f"title: {_y(ep.get('title', ''))}",
        f"theme: {_y(ep.get('theme', ''))}",
    ]
    if "\n" in note.strip():
        lines.append(f"director_note: {'|' if note.endswith(chr(10)) else '|-'}   {note_comment}")
        lines += ["  " + ln if ln else "" for ln in note.rstrip("\n").splitlines()]
    else:
        lines.append(f"director_note: {_y(note)}        {note_comment}")
    lines += [
        "music:",
        f"  bpm: {_y(m.get('bpm', [74, 80]))}",
        f"  palette: {_y(m.get('palette', []))}",
        f"  target_minutes: {_y(m.get('target_minutes', 60))}",
        f"  crossfade_seconds: {_y(m.get('crossfade_seconds', 4))}",
        f"  credits: {_y(m.get('credits', ''))}   # blank = config.yaml credits.music (say so if a human producer made a beat)",
    ]
    tracklist = m.get("tracklist") or []
    if tracklist:
        lines.append("  tracklist:              # filled by `lofi scan`; owner sets the order (move whole entries)")
        lines.append(_block(tracklist, 4))
    else:
        lines.append("  tracklist: []          # filled by `lofi scan`; owner sets the order")
    lines.append(f"  approved: {_y(bool(m.get('approved', False)))}        # owner only")
    for k, v in m.items():
        if k not in known_music:
            lines.append(f"  {k}: {_y(v)}")
    lines += [
        "art:",
        f"  scene_prompt: {_y(a.get('scene_prompt', ''))}",
        f"  loop_seconds: {_y(a.get('loop_seconds', 12))}",
        f"  motion: {_y(a.get('motion', []))}   # code-built layers: rain neon_flicker lamp_flicker tv_flicker steam dust sunbeam_dust fireflies record",
        f"  anchors: {_y(a.get('anchors', {}))}   # optional, for owner art: window [x0,y0,x1,y1], lamp [x,y], record [x,y,r], steam [x,y] in 0–1 coords",
        f"  realistic: {_y(a.get('realistic'))}   # owner: true if imagery looks photoreal (sets YouTube's altered/synthetic flag); null = infer from tools",
        f"  approved: {_y(bool(a.get('approved', False)))}        # owner only",
    ]
    for k, v in a.items():
        if k not in known_art:
            lines.append(f"  {k}: {_y(v)}")
    lines += [
        "thumbnail:               # 2–4 words each, readable at phone size",
        f"  text_a: {_y(t.get('text_a', ''))}",
        f"  text_b: {_y(t.get('text_b', ''))}",
        "overlays:",
        f"  now_playing: {_y(bool(o.get('now_playing', True)))}      # per-track lower-third",
        f"  visualizer: {_y(bool(o.get('visualizer', False)))}      # subtle audio-reactive element",
    ]
    known_top = {"id", "title", "theme", "director_note", "music", "art", "thumbnail", "overlays"}
    for k, v in ep.items():
        if k not in known_top:
            lines.append(f"{k}: {_y(v)}")
    return "\n".join(lines) + "\n"


def save_episode(ep: dict) -> Path:
    path = ep_path(ep["id"], "episode.yaml")
    text = dump_episode(ep)
    if yaml.safe_load(text) != yaml.safe_load(yaml.safe_dump(ep, allow_unicode=True)):
        raise LofiError("internal error: episode.yaml round-trip mismatch")  # never silently lose owner data
    path.write_text(text)
    return path


def list_episodes() -> list[str]:
    return sorted(p.parent.name for p in EPISODES.glob("*/episode.yaml"))


# ---------------------------------------------------------------- subprocess

def need(*tools: str) -> None:
    missing = [t for t in tools if shutil.which(t) is None]
    if missing:
        raise LofiError(f"missing tools: {', '.join(missing)} — run `lofi doctor`")


def run(cmd: list[str], *, quiet: bool = True, input: bytes | None = None) -> subprocess.CompletedProcess:
    """Run a command; raise LofiError with the stderr tail on failure."""
    proc = subprocess.run(cmd, input=input, capture_output=True)
    if proc.returncode != 0:
        tail = proc.stderr.decode(errors="replace").strip().splitlines()[-15:]
        raise LofiError(f"command failed ({cmd[0]}):\n  " + " ".join(cmd[:12]) + (" …" if len(cmd) > 12 else "")
                        + "\n" + "\n".join(tail))
    return proc


def ffmpeg(*args: str) -> subprocess.CompletedProcess:
    return run(["ffmpeg", "-hide_banner", "-nostdin", "-y", *args])


def ffprobe_json(path: Path, *extra: str) -> dict:
    proc = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", *extra, str(path)])
    return json.loads(proc.stdout)


def media_duration(path: Path) -> float:
    return float(ffprobe_json(path)["format"]["duration"])


# ---------------------------------------------------------------- fonts & text

@lru_cache(maxsize=8)
def font_path(role: str = "display") -> str:
    spec = config().get("fonts", {}).get(role, "Inter Display:bold" if role == "display" else "Inter:medium")
    candidate = Path(spec) if "/" in spec else BRAND / "fonts" / spec
    if candidate.suffix.lower() in {".ttf", ".otf"} and candidate.exists():
        return str(candidate)
    if shutil.which("fc-match"):
        proc = subprocess.run(["fc-match", "-f", "%{file}", spec], capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout and Path(proc.stdout).exists():
            return proc.stdout
    for fallback in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if Path(fallback).exists():
            return fallback
    raise LofiError("no usable font found — install fonts-dejavu or set fonts.* in config.yaml to a .ttf path")


_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF☀-➿⬀-⯿️‍\U0001F1E6-\U0001F1FF]+"
)


def strip_emoji(text: str) -> str:
    """drawtext and Pillow's outline fonts can't draw color emoji — strip them from burned-in text."""
    return re.sub(r"\s{2,}", " ", _EMOJI.sub("", text)).strip()


def palette() -> dict[str, tuple[int, int, int]]:
    data = json.loads((BRAND / "palette.json").read_text())
    return {k: tuple(int(v[i:i + 2], 16) for i in (1, 3, 5)) for k, v in data.items()}


def title_for(stem: str) -> str:
    return config().get("title_template", "{title_stem} soulful lofi beats [1 hour]").format(title_stem=stem)


def read_json(path: Path, default=None):
    return json.loads(path.read_text()) if path.exists() else default


def write_json(path: Path, data) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return path
