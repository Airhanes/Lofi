# secrets/

Gitignored. Put these here (never commit them):

- `client_secret.json` — OAuth client (Desktop app) from the Google Cloud project used for uploads
- `token.json` — written by `lofi upload` after the first OAuth consent

Stream keys and API keys go in `.env` (also gitignored), e.g.

```
YT_UPLOAD_ENABLED=0
STREAM_KEY=xxxx-xxxx-xxxx-xxxx
GOOGLE_CLOUD_PROJECT=my-project
GOOGLE_CLOUD_LOCATION=us-central1
# or GOOGLE_API_KEY=... for the Gemini API instead of Vertex AI
```
