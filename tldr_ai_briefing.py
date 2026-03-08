#!/usr/bin/env python3
"""Build a daily audio briefing from the TLDR AI newsletter in Gmail."""

from __future__ import annotations

import email
import imaplib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from email.header import decode_header
from io import BytesIO
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import requests
import trafilatura
from bs4 import BeautifulSoup
from pypdf import PdfReader

IMAP_HOST = "imap.gmail.com"
LA_TZ = ZoneInfo("America/Los_Angeles")
USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko)"


@dataclass
class Article:
    url: str
    title: str
    text: str


def require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def optional_env(name: str, default: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip()


def decode_mime_header(raw_value: str | None) -> str:
    if not raw_value:
        return ""
    parts = decode_header(raw_value)
    decoded: list[str] = []
    for content, charset in parts:
        if isinstance(content, bytes):
            decoded.append(content.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(content)
    return "".join(decoded)


def get_message_bodies(message: email.message.Message) -> tuple[str, str]:
    html_body = ""
    text_body = ""

    if message.is_multipart():
        for part in message.walk():
            content_type = part.get_content_type()
            disposition = str(part.get("Content-Disposition", "")).lower()
            if "attachment" in disposition:
                continue
            payload = part.get_payload(decode=True)
            if not payload:
                continue
            charset = part.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if content_type == "text/html" and not html_body:
                html_body = decoded
            elif content_type == "text/plain" and not text_body:
                text_body = decoded
    else:
        payload = message.get_payload(decode=True)
        if payload:
            charset = message.get_content_charset() or "utf-8"
            decoded = payload.decode(charset, errors="replace")
            if message.get_content_type() == "text/html":
                html_body = decoded
            else:
                text_body = decoded

    return html_body, text_body


def normalize_urls(urls: Iterable[str]) -> list[str]:
    skip_fragments = (
        "unsubscribe",
        "sponsor",
        "advertise",
        "privacy",
        "preferences",
        "mailto:",
    )

    seen: set[str] = set()
    normalized: list[str] = []

    for raw in urls:
        candidate = raw.strip()
        if not candidate:
            continue
        if any(fragment in candidate.lower() for fragment in skip_fragments):
            continue

        parsed = urlparse(candidate)
        if parsed.scheme not in ("http", "https"):
            continue

        compact = candidate.rstrip("/ ")
        if compact in seen:
            continue
        seen.add(compact)
        normalized.append(compact)

    return normalized


def extract_links(html_body: str, text_body: str) -> list[str]:
    links: list[str] = []

    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        for anchor in soup.select("a[href]"):
            href = anchor.get("href", "")
            if href:
                links.append(href)

    if text_body:
        links.extend(re.findall(r"https?://[^\s)>]+", text_body))

    return normalize_urls(links)


def fetch_tldr_message(
    gmail_address: str,
    gmail_app_password: str,
    from_contains: str,
    subject_contains: str,
    lookback_days: int,
) -> email.message.Message:
    with imaplib.IMAP4_SSL(IMAP_HOST) as mailbox:
        mailbox.login(gmail_address, gmail_app_password)
        mailbox.select("INBOX")

        since = (datetime.now() - timedelta(days=lookback_days)).strftime("%d-%b-%Y")
        status, data = mailbox.search(None, f'(SINCE "{since}")')
        if status != "OK":
            raise RuntimeError("Unable to query Gmail inbox")

        message_ids = data[0].split()
        if not message_ids:
            raise RuntimeError("No recent emails found in Gmail inbox")

        from_contains_l = from_contains.lower()
        subject_contains_l = subject_contains.lower()

        for msg_id in reversed(message_ids):
            status, payload = mailbox.fetch(msg_id, "(RFC822)")
            if status != "OK" or not payload or not payload[0]:
                continue

            raw = payload[0][1]
            message = email.message_from_bytes(raw)

            sender = decode_mime_header(message.get("From", "")).lower()
            subject = decode_mime_header(message.get("Subject", "")).lower()

            if from_contains_l in sender and subject_contains_l in subject:
                return message

        raise RuntimeError(
            "Could not find a matching TLDR AI email. "
            "Adjust TLDR_FROM_CONTAINS / TLDR_SUBJECT_CONTAINS if needed."
        )


def fetch_url_text(url: str, timeout_seconds: int, max_chars_per_source: int) -> Article | None:
    headers = {"User-Agent": USER_AGENT}

    try:
        response = requests.get(url, headers=headers, timeout=timeout_seconds)
        response.raise_for_status()
    except Exception as exc:
        logging.warning("Skipping %s (request failed: %s)", url, exc)
        return None

    content_type = response.headers.get("content-type", "").lower()
    content = response.content
    title = url
    text = ""

    is_pdf = ".pdf" in url.lower() or "application/pdf" in content_type

    if is_pdf:
        try:
            reader = PdfReader(BytesIO(content))
            page_text: list[str] = []
            for page in reader.pages[:6]:
                page_text.append(page.extract_text() or "")
            text = "\n".join(page_text).strip()
        except Exception as exc:
            logging.warning("Skipping %s (PDF parsing failed: %s)", url, exc)
            return None
    else:
        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        if soup.title and soup.title.text:
            title = soup.title.text.strip()[:200]

        extracted = trafilatura.extract(
            html,
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            deduplicate=True,
        )
        if extracted:
            text = extracted.strip()
        else:
            text = soup.get_text(" ", strip=True)

    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return None

    return Article(url=url, title=title, text=text[:max_chars_per_source])


def openai_request_json(api_key: str, payload: dict) -> dict:
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=180,
    )
    response.raise_for_status()
    return response.json()


def extract_output_text(response_json: dict) -> str:
    direct = response_json.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    chunks: list[str] = []
    for item in response_json.get("output", []):
        for content in item.get("content", []):
            text = content.get("text")
            if text:
                chunks.append(text)

    return "\n".join(chunks).strip()


def summarize_articles(
    api_key: str,
    model: str,
    articles: list[Article],
    max_total_chars: int,
) -> str:
    combined_sections = []
    consumed_chars = 0
    for idx, article in enumerate(articles, start=1):
        snippet = article.text
        remaining = max_total_chars - consumed_chars
        if remaining <= 0:
            break
        if len(snippet) > remaining:
            snippet = snippet[:remaining]
        consumed_chars += len(snippet)
        combined_sections.append(
            f"[{idx}] {article.title}\nURL: {article.url}\nExcerpt: {snippet}\n"
        )

    digest_input = "\n".join(combined_sections)

    payload = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are a concise analyst producing a spoken daily AI news briefing. "
                            "Summarize key developments, why they matter, and practical takeaways."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Create a 3-5 minute daily briefing script from these sources.\n"
                            "Requirements:\n"
                            "1) Start with a one-sentence headline summary.\n"
                            "2) Group by themes with short section headers.\n"
                            "3) Mention major papers/research and practical impacts.\n"
                            "4) End with three bullet takeaways.\n"
                            "5) Keep it plain text for text-to-speech.\n\n"
                            f"Sources:\n{digest_input}"
                        ),
                    }
                ],
            },
        ],
        "temperature": 0.2,
    }

    response_json = openai_request_json(api_key, payload)
    summary = extract_output_text(response_json)
    if not summary:
        raise RuntimeError("OpenAI summary response was empty")
    return summary


def synthesize_audio(api_key: str, model: str, voice: str, text: str, output_path: Path) -> None:
    response = requests.post(
        "https://api.openai.com/v1/audio/speech",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json={
            "model": model,
            "voice": voice,
            "format": "mp3",
            "input": text[:4000],
        },
        timeout=180,
    )
    response.raise_for_status()
    output_path.write_bytes(response.content)


def write_outputs(output_root: Path, summary_text: str) -> tuple[Path, Path]:
    date_slug = datetime.now(LA_TZ).strftime("%Y-%m-%d")
    output_dir = output_root / date_slug
    output_dir.mkdir(parents=True, exist_ok=True)

    txt_path = output_dir / "briefing.txt"
    md_path = output_dir / "briefing.md"

    txt_path.write_text(summary_text + "\n", encoding="utf-8")
    md_path.write_text(
        f"# TLDR AI Briefing ({date_slug})\n\n" + summary_text + "\n",
        encoding="utf-8",
    )

    return txt_path, md_path


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    gmail_address = require_env("GMAIL_ADDRESS")
    gmail_app_password = require_env("GMAIL_APP_PASSWORD")
    openai_api_key = require_env("OPENAI_API_KEY")

    subject_contains = optional_env("TLDR_SUBJECT_CONTAINS", "tldr ai")
    from_contains = optional_env("TLDR_FROM_CONTAINS", "tldr")
    lookback_days = int(os.getenv("TLDR_LOOKBACK_DAYS", "3"))
    max_links = int(os.getenv("MAX_LINKS", "80"))
    timeout_seconds = int(os.getenv("LINK_TIMEOUT_SECONDS", "25"))
    max_chars_per_source = int(os.getenv("MAX_CHARS_PER_SOURCE", "1200"))
    max_total_chars = int(os.getenv("MAX_TOTAL_CHARS", "90000"))

    text_model = os.getenv("OPENAI_TEXT_MODEL", "gpt-4.1-mini")
    tts_model = os.getenv("OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    tts_voice = os.getenv("OPENAI_TTS_VOICE", "alloy")

    output_root = Path(os.getenv("OUTPUT_DIR", "output"))

    logging.info("Searching Gmail for latest TLDR AI email")
    message = fetch_tldr_message(
        gmail_address=gmail_address,
        gmail_app_password=gmail_app_password,
        from_contains=from_contains,
        subject_contains=subject_contains,
        lookback_days=lookback_days,
    )

    html_body, text_body = get_message_bodies(message)
    links = extract_links(html_body, text_body)
    if not links:
        raise RuntimeError("No links found in the TLDR AI email")

    logging.info("Found %s links in newsletter", len(links))

    articles: list[Article] = []
    for link in links[:max_links]:
        article = fetch_url_text(link, timeout_seconds, max_chars_per_source)
        if article:
            articles.append(article)

    if not articles:
        raise RuntimeError("Could not extract readable text from newsletter links")

    logging.info("Extracted readable content from %s links", len(articles))
    summary_text = summarize_articles(
        openai_api_key,
        text_model,
        articles,
        max_total_chars=max_total_chars,
    )

    txt_path, md_path = write_outputs(output_root, summary_text)

    mp3_path = txt_path.with_suffix(".mp3")
    synthesize_audio(openai_api_key, tts_model, tts_voice, summary_text, mp3_path)

    logging.info("Summary written to %s", txt_path)
    logging.info("Markdown copy written to %s", md_path)
    logging.info("Audio briefing written to %s", mp3_path)


if __name__ == "__main__":
    main()
