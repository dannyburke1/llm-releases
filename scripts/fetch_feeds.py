#!/usr/bin/env python3
"""Fetch provider RSS/Atom feeds and extract new model release announcements."""

import hashlib
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "models.json"

FEEDS = {
    "aws_bedrock": {
        "url": "https://aws.amazon.com/about-aws/whats-new/recent/feed/",
        "type": "rss",
        "provider": "AWS Bedrock",
    },
    "vertex_ai": {
        "url": "https://cloud.google.com/feeds/vertex-ai-release-notes.xml",
        "type": "atom",
        "provider": "Vertex AI",
    },
    "azure_openai": {
        "url": "https://www.microsoft.com/releasecommunications/api/v2/azure/rss",
        "type": "rss",
        "provider": "Azure OpenAI",
    },
    "anthropic": {
        "url": "https://www.anthropic.com/rss.xml",
        "type": "rss",
        "provider": "Anthropic",
    },
}

MODEL_KEYWORDS = [
    r"(?:now|newly)\s+available",
    r"general(?:ly)?\s+available",
    r"launches?\b",
    r"introduc(?:es?|ing)\b",
    r"announc(?:es?|ing)\b",
    r"released?\b",
    r"new model",
    r"foundation model",
    r"(?:is|are)\s+available",
]

MODEL_NAMES = [
    r"\bclaude\b",
    r"\bllama\b",
    r"\bmistral\b",
    r"\bamazon\s+titan\b",
    r"\banthropic\b",
    r"\bcohere\b",
    r"\bcommand[\s\-]?r\b",
    r"\bjamba\b",
    r"\bai21\b",
    r"\bstability\s+ai\b",
    r"\bstable\s*diffusion\b",
    r"\bsdxl\b",
    r"\bamazon\s+nova\b",
    r"\bgemini\b",
    r"\bgemma\b",
    r"\bpalm\s*2?\b",
    r"\bgpt[\s\-]?[34o]",
    r"\bdall[\s\-]?e\b",
    r"\bwhisper\b",
    r"\bphi[\s\-]?\d",
    r"\bdeepseek\b",
    r"\bmeta\s+llama\b",
    r"\bo[13]\b(?:[\s\-](?:mini|pro))?",
]

EXCLUDE_PATTERNS = [
    r"pric(?:e|ing)\s+(?:reduc|cut|drop|chang)",
    r"region\s+(?:expansion|availab)",
    r"now available in .{0,30}(?:region|zone)",
    r"retir(?:e|ing|ement)",
    r"deprecat",
    r"end[\s\-]of[\s\-](?:life|support)",
    r"\bsagemaker\b",
]

MODEL_PATTERN = re.compile("|".join(MODEL_KEYWORDS), re.IGNORECASE)
NAME_PATTERN = re.compile("|".join(MODEL_NAMES), re.IGNORECASE)
EXCLUDE_PATTERN = re.compile("|".join(EXCLUDE_PATTERNS), re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")

REGION_PATTERNS = [
    re.compile(r"(?:US (?:East|West)\s*\([^)]+\)|EU \([^)]+\)|Asia Pacific\s*\([^)]+\)|Canada\s*\([^)]+\)|South America\s*\([^)]+\)|Middle East\s*\([^)]+\)|Africa\s*\([^)]+\)|Europe\s*\([^)]+\))"),
    re.compile(r"(?:us-east-\d|us-west-\d|eu-west-\d|eu-central-\d|ap-southeast-\d|ap-northeast-\d|ap-south-\d|sa-east-\d|ca-central-\d|me-south-\d|af-south-\d)[a-z]?"),
    re.compile(r"(?:us-central1|europe-west[1-9]|asia-east[12]|asia-northeast[1-3]|asia-southeast[12]|australia-southeast[12]|northamerica-northeast[12]|southamerica-east1)"),
    re.compile(r"(?:eastus|westus|northeurope|westeurope|uksouth|eastasia|southeastasia|japaneast|australiaeast|canadacentral|centralindia|koreacentral|francecentral|germanywestcentral|swedencentral|switzerlandnorth)\d?"),
]


def strip_html(text: str) -> str:
    return TAG_RE.sub("", unescape(text)).strip()


def make_id(provider: str, title: str) -> str:
    raw = f"{provider}:{title}".lower().strip()
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_model_release(title: str, description: str) -> bool:
    text = f"{title} {description}"
    if EXCLUDE_PATTERN.search(text):
        return False
    has_keyword = MODEL_PATTERN.search(text) is not None
    has_name = NAME_PATTERN.search(text) is not None
    return has_keyword and has_name


def extract_regions(text: str) -> list[str]:
    regions = []
    for pattern in REGION_PATTERNS:
        for match in pattern.finditer(text):
            regions.append(match.group(0).strip())
    return sorted(set(regions)) if regions else []


def fetch_url(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "llm-releases-bot/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read()


VERTEX_SECTION_RE = re.compile(r"(?:Feature|Changed|Announcement)\s*\n", re.IGNORECASE)


def split_vertex_sections(content: str) -> list[str]:
    parts = VERTEX_SECTION_RE.split(content)
    return [p.strip() for p in parts if p.strip()]


def extract_vertex_title(section: str) -> str:
    first_line = section.split("\n")[0].strip()
    if len(first_line) <= 120:
        return first_line
    return first_line[:117] + "..."


AWS_AI_CATEGORIES = re.compile(
    r"bedrock|artificial.intelligence|machine.learning|generative.ai",
    re.IGNORECASE,
)


def fetch_aws_bedrock() -> list[dict]:
    cfg = FEEDS["aws_bedrock"]
    data = fetch_url(cfg["url"])
    root = ET.fromstring(data)
    items = []
    for item in root.iter("item"):
        categories = [c.text for c in item.findall("category") if c.text]
        cat_text = " ".join(categories)
        if not AWS_AI_CATEGORIES.search(cat_text):
            continue

        title = item.findtext("title", "").strip()
        description = strip_html(item.findtext("description", ""))
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()

        if not is_model_release(title, f"{description} {cat_text}"):
            continue

        try:
            dt = parsedate_to_datetime(pub_date)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = pub_date

        regions = extract_regions(description)

        items.append({
            "id": make_id(cfg["provider"], title),
            "provider": cfg["provider"],
            "title": title,
            "description": description[:500],
            "link": link,
            "date": date_str,
            "regions": regions,
        })
    return items


def fetch_vertex_ai() -> list[dict]:
    cfg = FEEDS["vertex_ai"]
    data = fetch_url(cfg["url"])
    root = ET.fromstring(data)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items = []
    for entry in root.findall("atom:entry", ns):
        entry_title = entry.findtext("atom:title", "", ns).strip()
        content_el = entry.find("atom:content", ns)
        content = strip_html(content_el.text or "") if content_el is not None else ""
        link_el = entry.find("atom:link", ns)
        link = link_el.get("href", "") if link_el is not None else ""
        updated = entry.findtext("atom:updated", "", ns).strip()

        try:
            dt = datetime.fromisoformat(updated)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = updated

        sections = split_vertex_sections(content)
        if not sections:
            sections = [content]

        for section in sections:
            if not is_model_release(entry_title, section):
                continue
            title = extract_vertex_title(section)
            regions = extract_regions(section)
            items.append({
                "id": make_id(cfg["provider"], f"{entry_title}:{title}"),
                "provider": cfg["provider"],
                "title": title,
                "description": section[:500],
                "link": link,
                "date": date_str,
                "regions": regions,
            })
    return items


def fetch_azure_openai() -> list[dict]:
    cfg = FEEDS["azure_openai"]
    data = fetch_url(cfg["url"])
    root = ET.fromstring(data)
    items = []
    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        description = strip_html(item.findtext("description", ""))
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()
        categories = [c.text for c in item.findall("category") if c.text]
        cat_text = " ".join(categories)

        if not re.search(r"azure\s+openai|openai|azure\s+ai|azure\s+databricks", f"{title} {description} {cat_text}", re.IGNORECASE):
            continue

        if not is_model_release(title, f"{description} {cat_text}"):
            continue

        try:
            dt = parsedate_to_datetime(pub_date)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = pub_date

        regions = extract_regions(description)

        items.append({
            "id": make_id(cfg["provider"], title),
            "provider": cfg["provider"],
            "title": title,
            "description": description[:500],
            "link": link,
            "date": date_str,
            "regions": regions,
        })
    return items


ANTHROPIC_MODEL_RE = re.compile(
    r"\bclaude\b", re.IGNORECASE
)


def fetch_anthropic() -> list[dict]:
    cfg = FEEDS["anthropic"]
    data = fetch_url(cfg["url"])
    root = ET.fromstring(data)
    items = []
    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        description = strip_html(item.findtext("description", ""))
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()

        if not ANTHROPIC_MODEL_RE.search(f"{title} {description}"):
            continue
        if not is_model_release(title, description):
            continue

        try:
            dt = parsedate_to_datetime(pub_date)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = pub_date

        items.append({
            "id": make_id(cfg["provider"], title),
            "provider": cfg["provider"],
            "title": title,
            "description": description[:500],
            "link": link,
            "date": date_str,
            "regions": [],
        })
    return items


def main() -> None:
    existing = json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else []
    existing_ids = {m["id"] for m in existing}

    new_items = []
    fetchers = [fetch_aws_bedrock, fetch_vertex_ai, fetch_azure_openai, fetch_anthropic]

    for fetcher in fetchers:
        try:
            items = fetcher()
            for item in items:
                if item["id"] not in existing_ids:
                    new_items.append(item)
                    existing_ids.add(item["id"])
            print(f"  {fetcher.__name__}: found {len(items)} matching items")
        except Exception as e:
            print(f"  {fetcher.__name__}: error - {e}", file=sys.stderr)

    if new_items:
        all_items = existing + new_items
        all_items.sort(key=lambda x: x["date"], reverse=True)
        DATA_FILE.write_text(json.dumps(all_items, indent=2) + "\n")
        print(f"\nAdded {len(new_items)} new entries ({len(all_items)} total)")
    else:
        print("\nNo new entries found")


if __name__ == "__main__":
    main()
