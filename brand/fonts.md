# fonts

The pipeline resolves fonts through fontconfig using the names in `config.yaml → fonts`. Defaults are system fonts so the pipeline runs anywhere:

- **display** (thumbnail titles, Short titles): `Inter Display` Bold, set lowercase, tight tracking.
- **body** (now-playing lower-thirds, credits): `Inter` Medium.

To give the channel a warmer 70s-sleeve voice, drop an OFL-licensed font into `brand/fonts/` and point `config.yaml` at it by file path, e.g. a soft display serif such as Fraunces or DM Serif Display for titles. Fonts in `brand/fonts/` take precedence when `fonts.display` / `fonts.body` is a path. Check the license of anything you add — OFL or a paid license that covers video and thumbnails.
