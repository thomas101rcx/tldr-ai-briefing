# TLDR AI Daily Audio Briefing

This automation:
1. Logs into your Gmail inbox via IMAP.
2. Finds the latest TLDR AI newsletter email.
3. Opens links found in the email (including PDF/paper links).
4. Extracts readable content from each source.
5. Uses OpenAI to create a spoken daily summary.
6. Produces `briefing.txt`, `briefing.md`, and `briefing.mp3`.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export GMAIL_ADDRESS="you@gmail.com"
export GMAIL_APP_PASSWORD="your-google-app-password"
export OPENAI_API_KEY="sk-..."

# Optional tuning
export TLDR_FROM_CONTAINS="tldr"
export TLDR_SUBJECT_CONTAINS="tldr ai"
export MAX_LINKS="80"
export MAX_CHARS_PER_SOURCE="1200"
export MAX_TOTAL_CHARS="90000"

python tldr_ai_briefing.py
```

Output lands in `output/YYYY-MM-DD/`.

## GitHub Actions setup

Add these repository secrets:
- `GMAIL_ADDRESS`
- `GMAIL_APP_PASSWORD`
- `OPENAI_API_KEY`

Optional secrets (defaults are used if blank):
- `TLDR_FROM_CONTAINS` (default: `tldr`)
- `TLDR_SUBJECT_CONTAINS` (default: `tldr ai`)

Workflow file: `.github/workflows/tldr-ai-briefing.yml`

## Gmail app password

Use a Google App Password (requires 2FA enabled on your account):
- Google Account -> Security -> 2-Step Verification -> App passwords
- Gmail -> Settings -> See all settings -> Forwarding and POP/IMAP -> Enable IMAP

Do not use your regular Gmail password.

## Notes

- GitHub Actions cron is in UTC. The workflow is set to `15:00 UTC` (7:00 AM PST).
- If newsletter formatting changes, tune `TLDR_FROM_CONTAINS` and `TLDR_SUBJECT_CONTAINS`.
- Some sites may block scraping or require JavaScript, which can reduce source coverage.
