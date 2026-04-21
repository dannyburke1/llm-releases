#!/usr/bin/env python3
"""Build static site and RSS feed from models.json."""

import json
import re
from datetime import datetime, timezone
from email.utils import format_datetime
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "models.json"
DOCS_DIR = ROOT / "docs"
SITE_TITLE = "LLM Releases"
SITE_URL = "https://dannyburke1.github.io/llm-releases"
SITE_DESCRIPTION = "New model releases across AWS Bedrock, Vertex AI, Azure OpenAI, and Anthropic"

PROVIDER_SVGS = {
    "AWS Bedrock": '<svg class="provider-icon" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 7v10l10 5 10-5V7L12 2z" fill="#ff9900"/><path d="M12 7v10M7 9.5l10 5M17 9.5l-10 5" stroke="#fff" stroke-width="1.2"/></svg>',
    "Vertex AI": '<svg class="provider-icon" viewBox="0 0 24 24" fill="none"><path d="M12 2L2 19h20L12 2z" fill="#4285f4"/><path d="M12 2l4 8.5H8L12 2z" fill="#669df6"/><circle cx="12" cy="15" r="2.5" fill="#fff"/></svg>',
    "Azure OpenAI": '<svg class="provider-icon" viewBox="0 0 24 24" fill="none"><path d="M2 15L12 2l10 13H2z" fill="#0078d4"/><path d="M5 15l7-9 7 9" fill="#50a0e6"/><rect x="8" y="17" width="8" height="3" rx="1" fill="#0078d4"/></svg>',
    "Anthropic": '<svg class="provider-icon" viewBox="0 0 24 24" fill="none"><path d="M12 3L4 21h4l1.5-4h5L16 21h4L12 3zm0 6.5L14.5 15h-5L12 9.5z" fill="#d97757"/></svg>',
}

PROVIDER_LABELS = {
    "AWS Bedrock": "AWS",
    "Vertex AI": "GCP",
    "Azure OpenAI": "Azure",
    "Anthropic": "Anthropic",
}


def normalize_model_name(title: str) -> str:
    """Extract a canonical model name for cross-provider grouping."""
    text = title.lower()
    text = re.sub(r"^\[(?:launched|preview|in preview)\]\s*", "", text)
    text = re.sub(r"generally available:\s*", "", text)
    text = re.sub(r"\b(?:amazon bedrock|aws bedrock|azure databricks?)\b.*?(?:offers?|supports?|now offers?)\s*", "", text)
    text = re.sub(r"\bon (?:amazon bedrock|aws bedrock|azure databricks|vertex ai|model garden).*", "", text)
    text = re.sub(r"\bin (?:amazon bedrock|aws bedrock|azure databricks|vertex ai|model garden).*", "", text)
    text = re.sub(r"\bthrough (?:model garden|vertex ai).*", "", text)
    text = re.sub(r"\b(?:is |are )?(?:now |newly )?(?:available|launched?)\b.*", "", text)
    text = re.sub(r"anthropic'?s?\s*", "", text)
    text = re.sub(r"openai'?s?\s*", "", text)
    text = re.sub(r"[^a-z0-9.\-\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def group_models(models: list[dict]) -> list[dict]:
    """Group entries that refer to the same model across providers."""
    groups: dict[str, dict] = {}
    ungrouped = []

    for m in models:
        name = normalize_model_name(m["title"])
        if len(name) < 3:
            ungrouped.append(m)
            continue

        key = f"{m['date']}:{name}"

        found = False
        for existing_key, group in groups.items():
            existing_date, existing_name = existing_key.split(":", 1)
            if existing_name == name and abs(
                (datetime.strptime(m["date"], "%Y-%m-%d") - datetime.strptime(existing_date, "%Y-%m-%d")).days
            ) <= 7:
                group["providers"].append(m["provider"])
                group["links"].append({"provider": m["provider"], "link": m["link"]})
                regions = m.get("regions", [])
                if regions:
                    group["regions"] = sorted(set(group.get("regions", []) + regions))
                found = True
                break

        if not found:
            groups[key] = {
                "title": m["title"],
                "description": m["description"],
                "date": m["date"],
                "providers": [m["provider"]],
                "links": [{"provider": m["provider"], "link": m["link"]}],
                "regions": m.get("regions", []),
                "id": m["id"],
            }

    result = list(groups.values()) + [{
        "title": m["title"],
        "description": m["description"],
        "date": m["date"],
        "providers": [m["provider"]],
        "links": [{"provider": m["provider"], "link": m["link"]}],
        "regions": m.get("regions", []),
        "id": m["id"],
    } for m in ungrouped]

    result.sort(key=lambda x: x["date"], reverse=True)
    return result


def format_date_display(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return f'<span class="date-month">{dt.strftime("%b")}</span><span class="date-day">{dt.day}</span><span class="date-year">{dt.year}</span>'
    except Exception:
        return escape(date_str)


def build_html(models: list[dict]) -> str:
    grouped = group_models(models)

    rows = []
    for m in grouped:
        badges = []
        for p in sorted(set(m["providers"])):
            svg = PROVIDER_SVGS.get(p, "")
            label = PROVIDER_LABELS.get(p, p)
            badges.append(f'<span class="provider-badge" title="{escape(p)}">{svg}<span class="provider-label">{escape(label)}</span></span>')
        provider_html = "".join(badges)

        if len(m["links"]) == 1:
            title_html = f'<a href="{escape(m["links"][0]["link"])}" class="entry-link">{escape(m["title"])}</a>'
        else:
            link_parts = []
            for lnk in m["links"]:
                label = PROVIDER_LABELS.get(lnk["provider"], lnk["provider"])
                link_parts.append(f'<a href="{escape(lnk["link"])}" class="source-link">{escape(label)}</a>')
            title_html = f'<span class="entry-title">{escape(m["title"])}</span><span class="source-links">{" ".join(link_parts)}</span>'

        regions = m.get("regions", [])
        region_html = ""
        if regions:
            region_html = f'<span class="regions">{escape(", ".join(regions))}</span>'

        date_html = format_date_display(m["date"])

        rows.append(f"""          <tr>
            <td class="col-date"><div class="date-cell">{date_html}</div></td>
            <td class="col-providers"><div class="providers-cell">{provider_html}</div></td>
            <td class="col-announcement">{title_html}{region_html}</td>
          </tr>""")

    table_rows = "\n".join(rows) if rows else '          <tr><td colspan="3" class="empty">No releases tracked yet.</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{SITE_TITLE}</title>
  <link rel="alternate" type="application/rss+xml" title="{SITE_TITLE}" href="{SITE_URL}/feed.xml">
  <style>
    :root {{
      --bg: #f5f6f8;
      --surface: #ffffff;
      --surface-hover: #fafbfc;
      --border: #e8eaed;
      --text: #1a1d21;
      --text-secondary: #5f6368;
      --text-tertiary: #9aa0a6;
      --accent: #e88a1a;
      --shadow-sm: 0 1px 2px rgba(0,0,0,0.06), 0 1px 3px rgba(0,0,0,0.1);
      --shadow-md: 0 4px 6px -1px rgba(0,0,0,0.07), 0 2px 4px -2px rgba(0,0,0,0.05);
      --radius: 12px;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
      max-width: 1000px;
      margin: 0 auto;
      padding: 3rem 1.5rem 2rem;
      color: var(--text);
      background: var(--bg);
      -webkit-font-smoothing: antialiased;
    }}
    header {{
      margin-bottom: 2rem;
    }}
    h1 {{
      font-size: 1.75rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin-bottom: 0.5rem;
    }}
    .subtitle {{
      color: var(--text-secondary);
      font-size: 0.9rem;
      line-height: 1.5;
    }}
    .rss-link {{
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      color: var(--accent);
      text-decoration: none;
      font-weight: 500;
      font-size: 0.85rem;
      margin-left: 0.5rem;
      padding: 0.2rem 0.6rem;
      border-radius: 6px;
      background: rgba(232,138,26,0.08);
      transition: background 0.15s;
    }}
    .rss-link:hover {{
      background: rgba(232,138,26,0.15);
    }}
    .rss-icon {{
      width: 14px;
      height: 14px;
    }}
    .table-wrapper {{
      background: var(--surface);
      border-radius: var(--radius);
      box-shadow: var(--shadow-sm);
      overflow: hidden;
      border: 1px solid var(--border);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
    }}
    thead th {{
      text-align: left;
      padding: 0.75rem 1rem;
      font-size: 0.7rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-tertiary);
      border-bottom: 1px solid var(--border);
      background: var(--surface);
    }}
    tbody tr {{
      transition: background 0.1s;
    }}
    tbody tr:hover {{
      background: var(--surface-hover);
    }}
    tbody td {{
      padding: 0.85rem 1rem;
      border-top: 1px solid var(--border);
      font-size: 0.9rem;
      vertical-align: middle;
    }}
    tbody tr:first-child td {{
      border-top: none;
    }}
    .col-date {{
      width: 80px;
      white-space: nowrap;
    }}
    .date-cell {{
      display: flex;
      flex-direction: column;
      align-items: center;
      line-height: 1.1;
    }}
    .date-month {{
      font-size: 0.65rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-tertiary);
    }}
    .date-day {{
      font-size: 1.25rem;
      font-weight: 700;
      color: var(--text);
    }}
    .date-year {{
      font-size: 0.65rem;
      color: var(--text-tertiary);
    }}
    .col-providers {{
      width: 110px;
    }}
    .providers-cell {{
      display: flex;
      gap: 0.35rem;
      flex-wrap: wrap;
    }}
    .provider-badge {{
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      padding: 0.25rem 0.55rem;
      border-radius: 6px;
      background: var(--bg);
      border: 1px solid var(--border);
      font-size: 0.7rem;
      font-weight: 500;
      color: var(--text-secondary);
      white-space: nowrap;
      transition: box-shadow 0.15s;
    }}
    .provider-badge:hover {{
      box-shadow: var(--shadow-sm);
    }}
    .provider-icon {{
      width: 16px;
      height: 16px;
      flex-shrink: 0;
    }}
    .provider-label {{
      line-height: 1;
    }}
    .col-announcement {{
      line-height: 1.5;
    }}
    .entry-link {{
      color: var(--text);
      text-decoration: none;
      font-weight: 500;
    }}
    .entry-link:hover {{
      text-decoration: underline;
      text-decoration-color: var(--text-tertiary);
      text-underline-offset: 2px;
    }}
    .entry-title {{
      font-weight: 500;
    }}
    .source-links {{
      margin-left: 0.5rem;
    }}
    .source-link {{
      display: inline-block;
      font-size: 0.75rem;
      color: var(--text-tertiary);
      text-decoration: none;
      padding: 0.1rem 0.4rem;
      border-radius: 4px;
      background: var(--bg);
      border: 1px solid var(--border);
      transition: color 0.15s, border-color 0.15s;
    }}
    .source-link:hover {{
      color: var(--text-secondary);
      border-color: var(--text-tertiary);
    }}
    .regions {{
      display: block;
      font-size: 0.75rem;
      color: var(--text-tertiary);
      margin-top: 0.25rem;
    }}
    .empty {{
      text-align: center;
      color: var(--text-tertiary);
      padding: 3rem 1rem !important;
    }}
    footer {{
      margin-top: 2rem;
      text-align: center;
      font-size: 0.8rem;
      color: var(--text-tertiary);
    }}
    @media (max-width: 640px) {{
      body {{ padding: 1.5rem 1rem; }}
      .col-date {{ width: 60px; }}
      .col-providers {{ width: 50px; }}
      .provider-label {{ display: none; }}
      .provider-badge {{ padding: 0.25rem; }}
      .date-day {{ font-size: 1.1rem; }}
      .source-links {{ display: block; margin-left: 0; margin-top: 0.3rem; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{SITE_TITLE}</h1>
    <p class="subtitle">
      New model releases across AWS Bedrock, Vertex AI, Azure OpenAI &amp; Anthropic
      <a class="rss-link" href="{SITE_URL}/feed.xml">
        <svg class="rss-icon" viewBox="0 0 24 24" fill="currentColor"><circle cx="6.18" cy="17.82" r="2.18"/><path d="M4 4.44v2.83c7.03 0 12.73 5.7 12.73 12.73h2.83c0-8.59-6.97-15.56-15.56-15.56zm0 5.66v2.83c3.9 0 7.07 3.17 7.07 7.07h2.83c0-5.47-4.43-9.9-9.9-9.9z"/></svg>
        RSS
      </a>
    </p>
  </header>
  <div class="table-wrapper">
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
  </div>
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
