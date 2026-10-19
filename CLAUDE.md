# CLAUDE.md — Lofi Soul Channel

Build and run the production pipeline for a lofi YouTube channel with an African American soul aesthetic, start to finish: brand → art → animated loops → mixes → renders → thumbnails → metadata → (optional) Shorts, uploads and a 24/7 stream. The owner supplies the music and makes the creative calls; you build and run everything else.

Channel name: `CHANNEL_NAME` in `config.yaml` until the owner picks one (ideas to check: Porch Light Radio, After Hours Soul).

## Non-negotiables

1. **No scraping, no unofficial APIs.** Never automate Suno or any music site. Tracks arrive as files the owner drops into `episodes/<id>/tracks/`.
2. **Human approval gates.** `lofi render` refuses to run unless `art.approved` and `music.approved` are `true` in `episode.yaml`, and release requires a non-empty `director_note`. Only the owner sets these — they are the channel's evidence of human creative direction under YouTube's inauthentic-content policy. The one exception is `--proof` (see CLI).
3. **Every episode is distinct.** New scene, new loop, new tracklist, new title and thumbnails. A track appears in only one long-form mix; `catalog.csv` (audio hash → episode) enforces this and QA fails on reuse.
4. **Real motion, not a still.** A static image — or a still with only a slow zoom — over music is the pattern YouTube demonetizes. Loops need actual movement: rain, steam, flickering light, a spinning record, the host moving.
5. **Secrets stay out of git.** OAuth client files, tokens, API keys and stream keys live in `.env` / `secrets/`, both gitignored.

## Creative direction

**Feel:** warm, specific, everyday Black life rendered with love — cozy, nostalgic, a little cinematic. Every scene should feel like a real place someone remembers. Never a costume, never a punchline.

**Sound:** the jazz → soul → gospel → neo-soul lineage over boom-bap. Rhodes and Wurlitzer, warm upright or electric bass, swung off-grid drums, gospel organ swells, muted trumpet or sax, vibraphone, wordless soul vocal textures, vinyl crackle, tape warmth. 68–90 BPM. Prompts describe instruments and feel — never artist names, never samples of real records.

**Look:** golden-hour amber and lamplight against deep indigo nights; burnt orange, mustard, plum, forest green; film grain; the warmth of a 70s soul record sleeve. Lowercase titles.

**Recurring host:** draft a character sheet with two options for the owner to choose from — e.g., a young Black woman with deep brown skin, shoulder-length locs, oversized headphones and a mustard cardigan; or a young Black man with a low fade, a beard, headphones and a vintage varsity jacket. Recurring props: record player, pothos plant, worn composition notebook.

**Guardrails**
- Name skin tone and hair texture explicitly in every image prompt; reject outputs where skin drifts lighter or hair texture flattens.
- No caricatured features, slang-stuffed titles, or stereotypes used as props or jokes.
- Don't imitate another channel's signature character or scene composition.

## Season 1 — six ~60-minute episodes

| id | title stem | scene | sound | BPM |
|---|---|---|---|---|
| s01e01 | after hours at the barbershop 💈 | shop closed for the night, clippers resting on a towel, rain on the glass, soft neon glow | jazz piano, muted trumpet, brushed drums | 74–80 |
| s01e02 | finals week at the hbcu library 📚 | late-night stacks, green desk lamp, campus quad through the window | mellow Rhodes, boom-bap, upright bass | 80–86 |
| s01e03 | sunday morning in grandma's kitchen ☀️ | sun through lace curtains, steam off the stove, a church hat on a chair | gospel organ, soft choir pads, warm keys | 68–74 |
| s01e04 | porch light summer 🌙 | screen door, lightning bugs, sweet tea sweating on the rail | soul guitar, warm bass, crickets | 72–78 |
| s01e05 | crate digging at dusk 🎶 | record shop listening booth, golden light over the bins | dusty jazz breaks, vibraphone | 82–88 |
| s01e06 | late night braid session ✨ | kitchen chair, TV glow, rat-tail comb and edge brush on the table | neo-soul keys, soft sub bass | 72–78 |

Title format: `{title stem} soulful lofi beats [1 hour]`

## Music sourcing (owner's job)

- **Default — Suno, paid plan.** Commercial rights apply only to songs downloaded through Suno on a paid plan. Since Sept 3, 2026: Pro = 20 downloads/month, Premier = 60/month; Suno Studio downloads (Premier) are uncapped. A 60-minute mix needs ~20 tracks. Re-check Suno's terms before each release.
- **Alternative — human producers** (a natural fit: Black lofi/soul beatmakers). Written license per beat; samples cleared.
- `lofi prompts <id>` writes `episodes/<id>/suno_prompts.md`: ~25 prompts (owner keeps the best ~20), varied in key, tempo within the episode's range, and lead instrument.

## Repo layout

```
lofi/                  # Python package + Typer CLI
  cli.py  prompts.py  art.py  loop.py  mix.py  render.py
  thumb.py  meta.py  qa.py  short.py  upload.py
brand/                 # style.md, host character sheet, palette, fonts, title template
episodes/<id>/
  episode.yaml
  tracks/              # owner drops audio here
  art/                 # key art + loop source
  out/                 # final.mp4, thumb_a.jpg, thumb_b.jpg, description.txt, short.mp4, qa.md
catalog.csv            # audio hash → episode (reuse guard)
config.yaml            # channel name, defaults
stream/                # optional 24/7 stream scripts
tests/
```

## episode.yaml

```yaml
id: s01e01
title: "after hours at the barbershop 💈 soulful lofi beats [1 hour]"
theme: "barbershop after closing, rain on the glass, soft neon glow"
director_note: ""        # 2–3 lines written by the owner; required for release
music:
  bpm: [74, 80]
  palette: [jazz piano, muted trumpet, brushed drums, upright bass, vinyl crackle]
  target_minutes: 60
  crossfade_seconds: 4
  tracklist: []          # filled by `lofi scan`; owner sets the order
  approved: false        # owner only
art:
  scene_prompt: ""
  loop_seconds: 12
  approved: false        # owner only
overlays:
  now_playing: true      # per-track lower-third
  visualizer: false      # subtle audio-reactive element
```

## CLI

`lofi new <id> "<theme>"` · `lofi prompts <id>` · `lofi art <id>` · `lofi loop <id>` · `lofi scan <id>` · `lofi render <id> [--proof]` · `lofi qa <id>` · `lofi short <id>` · `lofi season` (render every approved episode) · `lofi upload <id>` (disabled unless `YT_UPLOAD_ENABLED=1`)

`--proof` skips the approval gates for pipeline testing, burns "PROOF — NOT FOR UPLOAD" into the video, and never writes to `catalog.csv`.

## Technical spec

- **Toolchain:** Python 3.11+, ffmpeg/ffprobe, Typer, PyYAML, Pillow, pytest; `google-api-python-client` + `google-auth-oauthlib` for uploads; Google's GenAI SDK only if API art generation is enabled. Check for ffmpeg first and install what's missing.
- **Art:** if Google Cloud credentials are configured, generate key art and a short loop clip with Google's image and video models (Imagen/Veo or their current successors) from `scene_prompt` plus the host sheet; otherwise use what the owner puts in `art/`. No video model? Build motion in code: depth-based parallax, rain/dust/steam particle layers, lamp flicker, a rotating record.
- **Loop:** 1920×1080, 30 fps, 8–20 s, seamless (tail crossfaded into head), H.264 yuv420p, keyframe at frame 0.
- **Mix:** owner's track order; equal-power crossfades of `crossfade_seconds`; two-pass `loudnorm` to −14 LUFS integrated and −1 dBTP true peak; per-track start times to `out/timestamps.json`.
- **Render:** loop the clip for the mix's length. Fast path (no overlays): loop the pre-encoded clip without re-encoding. Overlay path: re-encode with now-playing lower-thirds (`drawtext` enabled per track window) and the optional visualizer at low opacity. Output MP4: H.264 High, 1080p, ~8–12 Mbps, keyframe every 2 s (so episodes can be stream-copied to a live stream), AAC 48 kHz 384 kbps stereo, `+faststart`.
- **Thumbnails:** two variants (for YouTube's Test & Compare), 1280×720 JPG under 2 MB; key art plus a 2–4 word title, readable at phone size.
- **Description:** director's note → chapters tracklist starting at 0:00 (at least 3 chapters, each ≥ 10 s) → credits naming the tools used → playlist link → up to 3 hashtags. Also tags and category (Music). Flag YouTube's altered/synthetic content setting whenever imagery looks realistic.
- **Short:** 30–45 s vertical (1080×1920) teaser per episode with the title on screen.
- **QA (`out/qa.md`, fail loudly):** duration matches mix math; loudness within ±1 LU of −14; true peak ≤ −1 dBTP; chapters valid; thumbnails meet spec; no reused tracks; approvals and director's note present; ffprobe decodes the file cleanly.
- **Upload (gated):** OAuth with the `youtube.upload` scope. API uploads from an unaudited Google Cloud project are forced private, so keep this off until the project passes YouTube's API compliance audit. OAuth apps left in "Testing" status get refresh tokens that expire after 7 days. Always upload as private with the thumbnail set; publishing stays with the owner.
- **24/7 stream (optional):** concat rendered episodes into a playlist and push with `ffmpeg -re -stream_loop -1 -f concat -safe 0 -i playlist.txt -c:v copy -c:a aac -b:a 160k -f flv rtmp://a.rtmp.youtube.com/live2/$STREAM_KEY` under systemd on a small cloud VM. Stream key comes from the environment or a secret manager.

## Phases

1. **Foundation:** scaffold repo + CLI, toolchain check, `brand/style.md`, two host options (don't block on the owner's pick), episode template, and s01e01–s01e06 created from the Season 1 table.
2. **Pipeline:** prompts, art, loop, scan, mix, render, thumbnails, description, Short, QA, catalog; pytest for timestamp, chapter and catalog logic.
3. **Proof:** run s01e01 end to end with `--proof`, using generated placeholder audio (3 short tracks labeled PLACEHOLDER, ~3 minutes total, to keep it fast) and placeholder art; write `qa.md` and report what passed.
4. **Season 1:** after the owner picks the host, drops real tracks, and approves art and tracklists, run `lofi season`.
5. **Distribution (optional):** gated uploader, Shorts workflow, 24/7 stream.

## Release checklist (owner, in YouTube Studio)

Upload `final.mp4` as private → paste title, description and tags → thumbnail A (B for Test & Compare) → wait for Studio's copyright Checks to finish → schedule → add to the Season 1 playlist → post the Short. Cadence: 1–2 episodes a week, never daily dumps.
