"""`lofi upload <id>` — gated YouTube upload. Always private, thumbnail set; publishing stays with the owner.

Off unless YT_UPLOAD_ENABLED=1. Uploads from an unaudited Google Cloud project are forced private by YouTube
anyway, so leave this off until the project passes the YouTube API compliance audit. OAuth apps left in
"Testing" status get refresh tokens that expire after 7 days — expect to re-consent weekly until published.
"""

from __future__ import annotations

import os

from . import core, qa

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]


def _credentials():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise core.LofiError("uploads need: pip install 'lofi[upload]'") from e
    secrets = core.ROOT / "secrets"
    client, token = secrets / "client_secret.json", secrets / "token.json"
    creds = Credentials.from_authorized_user_file(str(token), SCOPES) if token.exists() else None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:  # Testing-status apps: refresh tokens die after 7 days
            creds = None
    if not creds or not creds.valid:
        if not client.exists():
            raise core.LofiError(f"missing {client} — create an OAuth client (Desktop app) in Google Cloud")
        creds = InstalledAppFlow.from_client_secrets_file(str(client), SCOPES).run_local_server(port=0)
    token.write_text(creds.to_json())
    return creds


def run(ep_id: str, *, short: bool = False, log=print) -> str:
    core.load_env()
    if os.environ.get("YT_UPLOAD_ENABLED") != "1":
        raise core.LofiError("uploads are disabled — set YT_UPLOAD_ENABLED=1 in .env once the Google Cloud project "
                             "has passed YouTube's API compliance audit (until then uploads are forced private)")
    ep = core.load_episode(ep_id)
    out = core.ep_path(ep_id, "out")
    meta = core.read_json(out / "metadata.json")
    rec = core.read_json(out / "render.json", {}) or {}
    if not meta or rec.get("proof"):
        raise core.LofiError(f"{ep_id}: no release render — proof renders never upload; run `lofi render {ep_id}`")
    report = qa.run(ep_id, log=log)
    if report.failed:
        raise core.LofiError(f"{ep_id}: QA failed — see {out / 'qa.md'}")

    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    youtube = build("youtube", "v3", credentials=_credentials())
    video = out / ("short.mp4" if short else "final.mp4")
    title = ep["title"] if not short else core.strip_emoji(ep["title"].split(" soulful lofi")[0]) + " #shorts"
    body = {
        "snippet": {"title": title[:100], "description": (out / "description.txt").read_text(),
                    "tags": meta["tags"], "categoryId": meta["category_id"], "defaultLanguage": meta["default_language"]},
        "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False,
                   "containsSyntheticMedia": bool(meta["contains_synthetic_media"])},
    }
    log(f"[{ep_id}] uploading {video.name} as PRIVATE")
    req = youtube.videos().insert(part="snippet,status", body=body,
                                  media_body=MediaFileUpload(str(video), chunksize=64 * 1024 * 1024, resumable=True))
    resp = None
    while resp is None:
        status, resp = req.next_chunk()
        if status:
            log(f"  {status.progress() * 100:.0f}%")
    vid = resp["id"]
    if not short:
        youtube.thumbnails().set(videoId=vid, media_body=MediaFileUpload(str(out / meta["thumbnail"]))).execute()
        log("  thumbnail A set — add thumbnail B in Studio for Test & Compare")
    core.write_json(out / ("upload_short.json" if short else "upload.json"), {"video_id": vid, "privacy": "private"})
    log(f"  https://studio.youtube.com/video/{vid}/edit — finish the release checklist in Studio")
    return vid
