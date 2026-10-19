# 24/7 stream (optional)

1. On a small cloud VM (2 vCPU is plenty — video is stream-copied), install ffmpeg + python3 and put the repo at `/opt/lofi` with the rendered `episodes/*/out/final.mp4` files.
2. `sudo install -m 600 /dev/null /etc/lofi/stream.env` and write `STREAM_KEY=...` into it (from YouTube Studio → Go live → Stream). Never commit it.
3. `sudo cp lofi-stream.service /etc/systemd/system/ && sudo systemctl enable --now lofi-stream`.

`build_playlist.py` includes only episodes whose render is not a proof and whose `qa.md` says **PASS**. Re-run (or restart the service) after each release. All renders share codec settings (H.264 High 1080p30, 2 s GOP), so the concat demuxer can copy video across episode boundaries; audio is re-encoded to 160 kbps for the stream.
