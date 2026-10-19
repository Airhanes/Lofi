# lofi — production pipeline

The production pipeline for a soulful lofi YouTube channel. The spec is in [`CLAUDE.md`](CLAUDE.md), the look and sound are in [`brand/`](brand/), and the two host options to choose from are in [`brand/host.md`](brand/host.md).

```bash
pip install -e '.[dev]'        # + '.[upload]' for YouTube, '.[genai]' for Google art generation
lofi doctor                    # toolchain check (--fix installs missing Python packages)
pytest
```

## an episode, start to finish

| step | who | command / action |
|---|---|---|
| 1 | pipeline | `lofi prompts s01e01` → `episodes/s01e01/suno_prompts.md` (25 prompts) |
| 2 | **owner** | generate in Suno (paid plan), keep ~20, drop the files into `episodes/s01e01/tracks/` |
| 3 | pipeline | `lofi scan s01e01` → hashes and probes the tracks into `episode.yaml`, warns on reuse |
| 4 | **owner** | reorder `music.tracklist`, fix titles, set `music.approved: true` |
| 5 | pipeline | `lofi art s01e01` → key art (Google if configured, else your file in `art/`) + `art/REVIEW.md` |
| 6 | pipeline | `lofi loop s01e01` → `art/loop.mp4` (seamless, real motion) |
| 7 | **owner** | go through `art/REVIEW.md`, then set `art.approved: true` and write the `director_note` |
| 8 | pipeline | `lofi render s01e01` → `out/final.mp4`, thumbnails, description, metadata, catalog claim |
| 9 | pipeline | `lofi short s01e01` and `lofi qa s01e01` → `out/short.mp4`, `out/qa.md` |
| 10 | **owner** | follow the release checklist in YouTube Studio (in `CLAUDE.md`) |

`lofi season` runs steps 8–9 for every episode whose art and music are both approved.

**Approvals are yours alone.** The pipeline never sets `approved: true` and never writes a director's note. It will *reset* an approval to false when the thing you approved changes, for example a different tracklist after `lofi scan` or replaced art after `lofi art --force`. `lofi render` refuses to run without both approvals, and it also refuses placeholder audio or art, track files that changed since the scan, and any track already used in another episode (`catalog.csv`).

**Proofs.** `lofi placeholder <id>` writes 3 PLACEHOLDER tracks and placeholder art. `lofi render <id> --proof` skips the approval gates, burns "PROOF — NOT FOR UPLOAD" into the video and thumbnails, and never writes to `catalog.csv`. QA marks the release checks as waived on proofs. Uploads and the stream playlist reject proof renders.

## art without a video model

Drop `key.png` (or any image) into `art/`. Without a `loop_source.mp4`, the motion is built in code from the layers named in `art.motion` (`rain neon_flicker lamp_flicker tv_flicker steam dust sunbeam_dust fireflies record`), plus depth parallax and film grain. The rain, lamp, record and steam layers need to know where things are in your image. Give their positions in `art.anchors` as 0–1 fractions of the frame, for example `{window: [0.07, 0.1, 0.43, 0.6], lamp: [0.8, 0.3], record: [0.62, 0.79, 0.058], steam: [0.33, 0.7]}`. A `depth.png` (white = near) makes the parallax better. Every layer repeats a whole number of times per loop, so the last frame flows into the first. If you supply a clip instead, the pipeline crossfades its tail into its head.

## distribution (optional)

- `lofi upload <id>` only works with `YT_UPLOAD_ENABLED=1` in `.env` and an OAuth client in `secrets/`. It uploads as **private** with thumbnail A set, and publishing stays with you. See `lofi/upload.py` for the audit and 7-day token caveats.
- 24/7 stream: see `stream/README.md`.

## render times (4-core container)

- Overlay path (now-playing cards): about 0.6× realtime, so a 60-minute episode takes about 1.5 hours at `preset: medium`. Set `video.preset: faster` in `config.yaml` to trade quality for speed.
- Fast path (overlays off): stream copy, about 4 minutes for an hour.
