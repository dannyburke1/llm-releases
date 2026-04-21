#!/usr/bin/env python3
"""Build static site and RSS feed from models.json."""

import json
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "models.json"
DOCS_DIR = ROOT / "docs"
SITE_TITLE = "LLM Releases"
SITE_URL = "https://llm-releases.github.io"
SITE_DESCRIPTION = "New model releases across AWS Bedrock, Vertex AI, and Azure OpenAI"

PROVIDER_COLORS = {
    "AWS Bedrock": "#ff9900",
    "Vertex AI": "#4285f4",
    "Azure OpenAI": "#0078d4",
}


def build_html(models: list[dict]) -> str:
    rows = []
    for m in models:
        color = PROVIDER_COLORS.get(m["provider"], "#666")
        rows.append(f"""        <tr>
          <td>{escape(m["date"])}</td>
          <td><span class="provider" style="background:{color}">{escape(m["provider"])}</span></td>
          <td><a href="{escape(m["link"])}">{escape(m["title"])}</a></td>
        </tr>""")

    table_rows = "\n".join(rows) if rows else "        <tr><td colspan='3'>No releases tracked yet.</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{SITE_TITLE}</title>
  <link rel="alternate" type="application/rss+xml" title="{SITE_TITLE}" href="{SITE_URL}/feed.xml">
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; max-width: 900px; margin: 0 auto; padding: 2rem 1rem; color: #1a1a1a; background: #fafafa; }}
    h1 {{ font-size: 1.5rem; margin-bottom: 0.25rem; }}
    .subtitle {{ color: #666; margin-bottom: 1.5rem; font-size: 0.9rem; }}
    .rss-link {{ color: #e88a1a; text-decoration: none; font-size: 0.85rem; }}
    .rss-link:hover {{ text-decoration: underline; }}
    table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
    th {{ text-align: left; padding: 0.75rem 1rem; background: #f0f0f0; font-size: 0.8rem; text-transform: uppercase; color: #555; }}
    td {{ padding: 0.75rem 1rem; border-top: 1px solid #eee; font-size: 0.9rem; }}
    td a {{ color: #1a1a1a; text-decoration: none; }}
    td a:hover {{ text-decoration: underline; }}
    .provider {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 4px; color: #fff; font-size: 0.75rem; font-weight: 600; white-space: nowrap; }}
    footer {{ margin-top: 2rem; font-size: 0.8rem; color: #999; }}
  </style>
</head>
<body>
  <h1>{SITE_TITLE}</h1>
  <p class="subtitle">New model releases across AWS Bedrock, Vertex AI, and Azure OpenAI &middot; <a class="rss-link" href="{SITE_URL}/feed.xml">RSS Feed</a></p>
  <table>
    <thead>
      <tr>
        <th>Date</th>
        <th>Provider</th>
        <th>Announcement</th>
      </tr>
    </thead>
    <tbody>
{table_rows}
    </tbody>
  </table>
  <footer>Updated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")} &middot; Data sourced from provider RSS feeds</footer>
</body>
</html>
"""


def build_rss(models: list[dict]) -> str:
    items = []
    for m in models[:50]:
        try:
            dt = datetime.strptime(m["date"], "%Y-%m-%d").replace(tzinfo=timezone.utc)
            pub_date = format_datetime(dt)
        except Exception:
            pub_date = m["date"]

        items.append(f"""    <item>
      <title>{escape(m["title"])}</title>
      <link>{escape(m["link"])}</link>
      <description>{escape(m["description"])}</description>
      <pubDate>{pub_date}</pubDate>
      <category>{escape(m["provider"])}</category>
      <guid isPermaLink="false">{m["id"]}</guid>
    </item>""")

    items_xml = "\n".join(items)
    now = format_datetime(datetime.now(timezone.utc))

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">
  <channel>
    <title>{SITE_TITLE}</title>
    <link>{SITE_URL}</link>
    <description>{SITE_DESCRIPTION}</description>
    <lastBuildDate>{now}</lastBuildDate>
    <atom:link href="{SITE_URL}/feed.xml" rel="self" type="application/rss+xml"/>
{items_xml}
  </channel>
</rss>
"""


def main() -> None:
    models = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else []
    DOCS_DIR.mkdir(exist_ok=True)
    (DOCS_DIR / "index.html").write_text(build_html(models))
    (DOCS_DIR / "feed.xml").write_text(build_rss(models))
    print(f"Built site with {len(models)} entries in {DOCS_DIR}")


if __name__ == "__main__":
    main()
