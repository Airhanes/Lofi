# qa — s01e01

**PROOF OK — pipeline checks pass; release checks waived** · 2026-10-19T01:36:53 · proof render (not for upload)

| | check | detail |
|---|---|---|
| ➖ WAIVED | art approved by owner | art.approved |
| ➖ WAIVED | music approved by owner | music.approved |
| ➖ WAIVED | director's note present | director_note |
| ➖ WAIVED | no placeholder audio | placeholder_01.flac, placeholder_02.flac, placeholder_03.flac |
| ➖ WAIVED | no placeholder art | art source: placeholder |
| ✅ PASS | no reused tracks | 3 tracks, none used elsewhere |
| ✅ PASS | decodes cleanly | ffmpeg decoded every frame with no errors |
| ✅ PASS | video codec H.264 High | h264 High |
| ✅ PASS | 1920×1080 | 1920×1080 |
| ✅ PASS | yuv420p | yuv420p |
| ✅ PASS | 30 fps | 30.000 |
| ✅ PASS | video bitrate ~8–12 Mbps | 10.0 Mbps |
| ✅ PASS | keyframe every 2 s | 89 keyframes, max gap 2.00s |
| ✅ PASS | AAC 48 kHz stereo | aac 48000 Hz 2ch |
| ⚠️ WARN | audio bitrate 384k | 284 kbps measured — encoder undershoots on sparse audio; fine for YouTube, recheck with real tracks |
| ✅ PASS | +faststart (moov before mdat) | ftyp → moov → free → mdat |
| ✅ PASS | duration matches mix math | expected 178.00s (Σ tracks − 2×crossfade); file 178.00s, video 178.00s, audio 178.00s |
| ✅ PASS | loudness -14.0 LUFS ±1 | -14.20 LUFS integrated |
| ✅ PASS | true peak ≤ -1.0 dBTP | -1.14 dBTP |
| ✅ PASS | loop has real motion | 3.90% of frame changes per ½ s; layers: dust, grain, neon_flicker, parallax, rain, record |
| ✅ PASS | loop seam invisible | last→first jump 1.25 vs typical frame step 1.09 |
| ✅ PASS | loop 8–20 s | 12.00s |
| ✅ PASS | chapters valid | 3 chapters from 0:00, each ≥ 10 s |
| ✅ PASS | chapters match timestamps.json | 3 track starts |
| ➖ WAIVED | description opens with director's note |  |
| ✅ PASS | ≤ 3 hashtags | #lofi #soulfullofi #lofihiphop |
| ✅ PASS | description fits YouTube limits | 579 chars, no angle brackets |
| ✅ PASS | credits name the tools |  |
| ✅ PASS | title lowercase, ≤ 100 chars | 59 chars |
| ✅ PASS | tags ≤ 500 chars | 10 tags |
| ℹ️ INFO | altered/synthetic content setting | off (set art.realistic: true if the imagery looks photoreal) |
| ✅ PASS | thumbnail A spec | JPEG 1280×720, 78 KB, 2 words |
| ✅ PASS | thumbnail B spec | JPEG 1280×720, 79 KB, 3 words |
| ✅ PASS | short 1080×1920, 30–45 s | 1080×1920, 40.0s |

pass: 26 · warn: 1 · waived: 6 · info: 1
