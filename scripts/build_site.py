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
SITE_DESCRIPTION = "New model releases across cloud providers"

PROVIDER_SVGS = {
    "AWS Bedrock": '<svg class="pi" viewBox="0 0 40 40"><path d="M20 4L4 12v16l16 8 16-8V12L20 4z" fill="#232f3e"/><path d="M20 4L4 12l16 8 16-8L20 4z" fill="#ff9900"/><path d="M20 20v16l16-8V12L20 20z" fill="#f90" opacity=".35"/></svg>',
    "Vertex AI": '<svg class="pi" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="#4285f4"/><path d="M11 28l9-18 9 18" fill="none" stroke="#fff" stroke-width="2.5" stroke-linejoin="round"/><circle cx="20" cy="14" r="2" fill="#fff"/></svg>',
    "Azure OpenAI": '<svg class="pi" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="#0078d4"/><path d="M10 26L20 10l10 16H10z" fill="#50e6ff" opacity=".9"/><path d="M14 26l6-10 6 10H14z" fill="#fff" opacity=".5"/></svg>',
    "Anthropic": '<svg class="pi" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="#d97757"/><path d="M20 10l-8 20h4.5l1.8-5h7.4l1.8 5H32L20 10zm0 7l2.5 6.5h-5L20 17z" fill="#fff"/></svg>',
    "Google": '<svg class="pi" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="#fff" stroke="#dadce0"/><circle cx="14" cy="14" r="5" fill="#4285f4"/><circle cx="26" cy="14" r="5" fill="#ea4335"/><circle cx="14" cy="26" r="5" fill="#34a853"/><circle cx="26" cy="26" r="5" fill="#fbbc05"/></svg>',
    "Google DeepMind": '<svg class="pi" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="#fff" stroke="#dadce0"/><circle cx="14" cy="14" r="5" fill="#4285f4"/><circle cx="26" cy="14" r="5" fill="#ea4335"/><circle cx="14" cy="26" r="5" fill="#34a853"/><circle cx="26" cy="26" r="5" fill="#fbbc05"/></svg>',
    "OpenAI": '<svg class="pi" viewBox="0 0 40 40"><rect width="40" height="40" rx="8" fill="#000"/><path d="M20 8c-6.6 0-12 5.4-12 12s5.4 12 12 12 12-5.4 12-12S26.6 8 20 8zm0 3c2 0 3.8.7 5.3 1.8L15.8 22.3c-.2-.7-.3-1.5-.3-2.3 0-2.5 1-4.7 2.6-6.3A8.9 8.9 0 0120 11zm0 18a8.9 8.9 0 01-5.3-1.8l9.5-9.5c.2.7.3 1.5.3 2.3 0 2.5-1 4.7-2.6 6.3A8.9 8.9 0 0120 29z" fill="#fff"/></svg>',
}

PROVIDER_LABELS = {
    "AWS Bedrock": "AWS Bedrock",
    "Vertex AI": "Vertex AI",
    "Azure OpenAI": "Azure OpenAI",
    "Anthropic": "Anthropic",
    "Google": "Google",
    "Google DeepMind": "Google DeepMind",
    "OpenAI": "OpenAI",
}

# Order for display (first-party providers first, then cloud)
PROVIDER_ORDER = ["Anthropic", "OpenAI", "Google", "Google DeepMind", "AWS Bedrock", "Vertex AI", "Azure OpenAI"]


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
    text = re.sub(r"\bintroducing\s+", "", text)
    text = re.sub(r"[^a-z0-9.\-\s]", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def group_models(models: list[dict]) -> list[dict]:
    """Group entries that refer to the same model across providers."""
    groups: list[dict] = []

    for m in models:
        name = normalize_model_name(m["title"])
        if len(name) < 3:
            groups.append({
                "name": name,
                "entries": [m],
                "date": m["date"],
            })
            continue

        found = False
        for group in groups:
            if group["name"] == name and abs(
                (datetime.strptime(m["date"], "%Y-%m-%d") - datetime.strptime(group["date"], "%Y-%m-%d")).days
            ) <= 14:
                group["entries"].append(m)
                if m["date"] > group["date"]:
                    group["date"] = m["date"]
                found = True
                break

        if not found:
            groups.append({
                "name": name,
                "entries": [m],
                "date": m["date"],
            })

    groups.sort(key=lambda x: x["date"], reverse=True)
    return groups


def pick_display_title(entries: list[dict]) -> str:
    """Pick the cleanest title from grouped entries."""
    ranked = []
    for e in entries:
        t = e["title"]
        score = 0
        if t.startswith("["):
            score -= 10
        if "amazon bedrock" in t.lower() or "azure databricks" in t.lower():
            score -= 5
        if "model garden" in t.lower():
            score -= 5
        if re.search(r"introduc", t, re.IGNORECASE):
            score += 5
        ranked.append((score, t))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


def format_relative_date(date_str: str) -> str:
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        now = datetime.now()
        delta = (now - dt).days
        if delta == 0:
            return "Today"
        if delta == 1:
            return "Yesterday"
        if delta < 7:
            return f"{delta}d ago"
        if delta < 30:
            weeks = delta // 7
            return f"{weeks}w ago"
        if delta < 365:
            months = delta // 30
            return f"{months}mo ago"
        return dt.strftime("%b %Y")
    except Exception:
        return date_str


def build_html(models: list[dict]) -> str:
    grouped = group_models(models)

    cards = []
    for group in grouped:
        entries = group["entries"]
        title = pick_display_title(entries)
        date = group["date"]
        relative = format_relative_date(date)

        providers_html = []
        for e in sorted(entries, key=lambda x: PROVIDER_ORDER.index(x["provider"]) if x["provider"] in PROVIDER_ORDER else 99):
            svg = PROVIDER_SVGS.get(e["provider"], "")
            label = PROVIDER_LABELS.get(e["provider"], e["provider"])
            regions = e.get("regions", [])
            region_html = f'<span class="chip-region">{escape(", ".join(regions))}</span>' if regions else ""
            providers_html.append(
                f'<a href="{escape(e["link"])}" class="provider-chip" title="{escape(e["provider"])}">'
                f'{svg}<span class="chip-label">{escape(label)}</span>{region_html}</a>'
            )

        desc = entries[0].get("description", "")
        if len(desc) > 200:
            desc = desc[:197] + "..."

        all_providers = sorted(set(e["provider"] for e in entries))
        data_providers = "|".join(escape(p) for p in all_providers)

        cards.append(f"""      <article class="card" data-providers="{data_providers}">
        <div class="card-header">
          <h2 class="card-title">{escape(title)}</h2>
          <time class="card-date" datetime="{escape(date)}" title="{escape(date)}">{escape(relative)}</time>
        </div>
        <p class="card-desc">{escape(desc)}</p>
        <div class="card-providers">{" ".join(providers_html)}</div>
      </article>""")

    cards_html = "\n".join(cards) if cards else '      <p class="empty">No releases tracked yet.</p>'

    all_providers_in_data = []
    seen = set()
    for group in grouped:
        for e in group["entries"]:
            if e["provider"] not in seen:
                seen.add(e["provider"])
                all_providers_in_data.append(e["provider"])
    all_providers_in_data.sort(key=lambda p: PROVIDER_ORDER.index(p) if p in PROVIDER_ORDER else 99)

    filter_buttons = []
    for p in all_providers_in_data:
        svg = PROVIDER_SVGS.get(p, "")
        label = PROVIDER_LABELS.get(p, p)
        filter_buttons.append(
            f'<button class="filter-btn active" data-provider="{escape(p)}" title="{escape(p)}">'
            f'{svg}<span class="filter-label">{escape(label)}</span></button>'
        )
    filters_html = "\n        ".join(filter_buttons)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{SITE_TITLE}</title>
  <link rel="alternate" type="application/rss+xml" title="{SITE_TITLE}" href="{SITE_URL}/feed.xml">
  <style>
    :root {{
      --bg: #f0f2f5;
      --surface: #ffffff;
      --border: #e4e6ea;
      --text: #1c1e21;
      --text-2: #606770;
      --text-3: #8a8d91;
      --accent: #e88a1a;
      --radius: 12px;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Inter, Roboto, sans-serif;
      max-width: 720px;
      margin: 0 auto;
      padding: 2.5rem 1rem 2rem;
      color: var(--text);
      background: var(--bg);
      -webkit-font-smoothing: antialiased;
    }}
    header {{
      text-align: center;
      margin-bottom: 2rem;
    }}
    h1 {{
      font-size: 1.6rem;
      font-weight: 700;
      letter-spacing: -0.02em;
    }}
    .subtitle {{
      color: var(--text-2);
      font-size: 0.85rem;
      margin-top: 0.35rem;
    }}
    .header-links {{
      margin-top: 0.75rem;
      display: flex;
      justify-content: center;
      gap: 0.75rem;
    }}
    .header-link {{
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      font-size: 0.8rem;
      font-weight: 500;
      text-decoration: none;
      padding: 0.3rem 0.75rem;
      border-radius: 20px;
      transition: background 0.15s;
    }}
    .rss-link {{
      color: var(--accent);
      background: rgba(232,138,26,0.08);
    }}
    .rss-link:hover {{ background: rgba(232,138,26,0.15); }}
    .rss-icon {{ width: 13px; height: 13px; }}
    .card {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 1.25rem;
      margin-bottom: 0.75rem;
      transition: box-shadow 0.15s;
    }}
    .card:hover {{
      box-shadow: 0 2px 8px rgba(0,0,0,0.08);
    }}
    .card-header {{
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      margin-bottom: 0.5rem;
    }}
    .card-title {{
      font-size: 0.95rem;
      font-weight: 600;
      line-height: 1.4;
      flex: 1;
    }}
    .card-date {{
      font-size: 0.75rem;
      color: var(--text-3);
      white-space: nowrap;
      padding-top: 0.15rem;
    }}
    .card-desc {{
      font-size: 0.82rem;
      color: var(--text-2);
      line-height: 1.5;
      margin-bottom: 0.75rem;
    }}
    .card-providers {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem;
    }}
    .provider-chip {{
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.3rem 0.65rem 0.3rem 0.35rem;
      border-radius: 8px;
      background: var(--bg);
      border: 1px solid var(--border);
      text-decoration: none;
      color: var(--text-2);
      font-size: 0.75rem;
      font-weight: 500;
      transition: border-color 0.15s, box-shadow 0.15s;
    }}
    .provider-chip:hover {{
      border-color: var(--text-3);
      box-shadow: 0 1px 3px rgba(0,0,0,0.08);
    }}
    .pi {{
      width: 20px;
      height: 20px;
      border-radius: 4px;
      flex-shrink: 0;
    }}
    .chip-label {{
      line-height: 1;
    }}
    .chip-region {{
      font-size: 0.65rem;
      color: var(--text-3);
      font-weight: 400;
      margin-left: 0.15rem;
    }}
    .toolbar {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 0.75rem 1rem;
      margin-bottom: 1rem;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
    }}
    .search-row {{
      position: relative;
    }}
    .search-icon {{
      position: absolute;
      left: 0.7rem;
      top: 50%;
      transform: translateY(-50%);
      width: 15px;
      height: 15px;
      color: var(--text-3);
      pointer-events: none;
    }}
    .search-input {{
      width: 100%;
      padding: 0.5rem 0.75rem 0.5rem 2.1rem;
      border: 1px solid var(--border);
      border-radius: 8px;
      font-size: 0.82rem;
      font-family: inherit;
      color: var(--text);
      background: var(--bg);
      outline: none;
      transition: border-color 0.15s;
    }}
    .search-input:focus {{
      border-color: var(--text-3);
    }}
    .search-input::placeholder {{
      color: var(--text-3);
    }}
    .filter-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
      align-items: center;
    }}
    .filter-btn {{
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      padding: 0.3rem 0.6rem 0.3rem 0.3rem;
      border-radius: 8px;
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text-3);
      font-size: 0.72rem;
      font-weight: 500;
      font-family: inherit;
      cursor: pointer;
      transition: all 0.15s;
      opacity: 0.45;
    }}
    .filter-btn.active {{
      opacity: 1;
      color: var(--text-2);
      border-color: var(--text-3);
    }}
    .filter-btn:hover {{
      opacity: 0.85;
    }}
    .filter-btn .pi {{
      width: 18px;
      height: 18px;
    }}
    .no-results {{
      text-align: center;
      color: var(--text-3);
      padding: 2.5rem 1rem;
      font-size: 0.85rem;
      display: none;
    }}
    .empty {{
      text-align: center;
      color: var(--text-3);
      padding: 3rem;
    }}
    footer {{
      margin-top: 1.5rem;
      text-align: center;
      font-size: 0.75rem;
      color: var(--text-3);
    }}
    @media (max-width: 500px) {{
      body {{ padding: 1.25rem 0.75rem; }}
      .card {{ padding: 1rem; }}
      .card-title {{ font-size: 0.9rem; }}
      .chip-label {{ display: none; }}
      .provider-chip {{ padding: 0.3rem; }}
      .filter-label {{ display: none; }}
      .filter-btn {{ padding: 0.3rem; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{SITE_TITLE}</h1>
    <p class="subtitle">Tracking new model releases across cloud providers</p>
    <div class="header-links">
      <a class="header-link rss-link" href="{SITE_URL}/feed.xml">
        <svg class="rss-icon" viewBox="0 0 24 24" fill="currentColor"><circle cx="6.18" cy="17.82" r="2.18"/><path d="M4 4.44v2.83c7.03 0 12.73 5.7 12.73 12.73h2.83c0-8.59-6.97-15.56-15.56-15.56zm0 5.66v2.83c3.9 0 7.07 3.17 7.07 7.07h2.83c0-5.47-4.43-9.9-9.9-9.9z"/></svg>
        RSS Feed
      </a>
    </div>
  </header>
  <div class="toolbar">
    <div class="search-row">
      <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
      <input type="text" class="search-input" placeholder="Search models..." id="search">
    </div>
    <div class="filter-row">
      {filters_html}
    </div>
  </div>
  <main id="cards">
{cards_html}
  </main>
  <p class="no-results" id="no-results">No matching releases found.</p>
  <footer>Updated {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")}</footer>
  <script>
  (function() {{
    var btns = document.querySelectorAll('.filter-btn');
    var cards = document.querySelectorAll('.card');
    var search = document.getElementById('search');
    var noResults = document.getElementById('no-results');

    function activeProviders() {{
      var s = new Set();
      btns.forEach(function(b) {{ if (b.classList.contains('active')) s.add(b.dataset.provider); }});
      return s;
    }}

    function applyFilters() {{
      var q = search.value.toLowerCase().trim();
      var providers = activeProviders();
      var visible = 0;
      cards.forEach(function(card) {{
        var cp = card.dataset.providers.split('|');
        var providerMatch = cp.some(function(p) {{ return providers.has(p); }});
        var textMatch = !q || card.textContent.toLowerCase().indexOf(q) !== -1;
        var show = providerMatch && textMatch;
        card.style.display = show ? '' : 'none';
        if (show) visible++;
      }});
      noResults.style.display = visible === 0 ? '' : 'none';
    }}

    btns.forEach(function(btn) {{
      btn.addEventListener('click', function() {{
        btn.classList.toggle('active');
        applyFilters();
      }});
    }});

    search.addEventListener('input', applyFilters);
  }})();
  </script>
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
