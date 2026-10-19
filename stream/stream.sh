#!/usr/bin/env bash
# 24/7 stream: loop every released episode to YouTube Live, video stream-copied (renders use a 2 s GOP).
# STREAM_KEY comes from the environment (systemd EnvironmentFile) or a secret manager — never from git.
set -euo pipefail
cd "$(dirname "$0")"
: "${STREAM_KEY:?set STREAM_KEY in the environment}"
python3 build_playlist.py
exec ffmpeg -hide_banner -loglevel warning -re -stream_loop -1 -f concat -safe 0 -i playlist.txt \
  -c:v copy -c:a aac -b:a 160k -ar 48000 \
  -f flv "rtmp://a.rtmp.youtube.com/live2/${STREAM_KEY}"
