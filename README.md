# TLDR AI Daily Audio Briefing

This automation:
1. Logs into your Gmail inbox via IMAP.
2. Finds the latest TLDR AI newsletter email.
3. Opens links found in the email (including PDF/paper links).
4. Extracts readable content from each source.
5. Uses a free OpenRouter model to create a spoken daily summary script.
6. Uses free `edge-tts` to generate MP3 audio.
7. Produces `tldr-ai-briefing-YYYY-MM-DD.txt`, `.md`, and `.mp3`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export GMAIL_ADDRESS="you@gmail.com"
export GMAIL_APP_PASSWORD="your-google-app-password"
export OPENROUTER_API_KEY="your-openrouter-key"

# Optional tuning
export OPENROUTER_MODEL="openrouter/free"
export TLDR_FROM_CONTAINS="tldr"
export TLDR_SUBJECT_CONTAINS="tldr ai"
export MAX_LINKS="80"
export MAX_CHARS_PER_SOURCE="1200"
export MAX_TOTAL_CHARS="90000"
export TTS_VOICE="en-US-JennyNeural"
export TTS_RATE="+0%"

python tldr_ai_briefing.py
```

Output lands in `output/YYYY-MM-DD/`.

## GitHub Actions setup

Add these repository secrets:
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `OPENROUTER_API_KEY`

Optional secrets (defaults are used if blank):
- `OPENROUTER_MODEL` (default: `openrouter/free`)
- `TLDR_FROM_CONTAINS` (default: `tldr`)
- `TLDR_SUBJECT_CONTAINS` (default: `tldr ai`)

Workflow file: `.github/workflows/tldr-ai-briefing.yml`

## Gmail app password

Use a Google App Password (requires 2FA enabled on your account):
- Google Account -> Security -> 2-Step Verification -> App passwords
- Gmail -> Settings -> See all settings -> Forwarding and POP/IMAP -> Enable IMAP

Do not use your regular Gmail password.

## Notes

- GitHub Actions cron is in UTC and runs Monday-Friday at `14:00 UTC`.
- `14:00 UTC` maps to `6:00 AM PST` during standard time and `7:00 AM PDT` during daylight time.
- Current default model is `openrouter/free`, which routes to an available free OpenRouter model.
- If newsletter formatting changes, tune `TLDR_FROM_CONTAINS` and `TLDR_SUBJECT_CONTAINS`.
- Some sites may block scraping or require JavaScript, which can reduce source coverage.
- Weekend safety: if run manually on Saturday/Sunday and latest newsletter is from an earlier day, script skips regeneration by default (`SKIP_WEEKEND_STALE=true`).
