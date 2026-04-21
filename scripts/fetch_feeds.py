#!/usr/bin/env python3
"""Fetch provider RSS/Atom feeds and extract new model release announcements."""

import hashlib
import json
import re
import ssl
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "models.json"

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
    r"\bgpt[\s\-]?[345o]",
    r"\bdall[\s\-]?e\b",
    r"\bwhisper\b",
    r"\bphi[\s\-]?\d",
    r"\bdeepseek\b",
    r"\bmeta\s+llama\b",
    r"\bo[13]\b(?:[\s\-](?:mini|pro))?",
    r"\bflash\b",
    r"\bsora\b",
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
    ctx = ssl.create_default_context()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "llm-releases-bot/1.0"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
            return resp.read()
    except ssl.SSLCertVerificationError:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(url, headers={"User-Agent": "llm-releases-bot/1.0"})
        with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
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
    data = fetch_url("https://aws.amazon.com/about-aws/whats-new/recent/feed/")
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

        items.append({
            "id": make_id("AWS Bedrock", title),
            "provider": "AWS Bedrock",
            "title": title,
            "description": description[:500],
            "link": link,
            "date": date_str,
            "regions": extract_regions(description),
        })
    return items


def fetch_vertex_ai() -> list[dict]:
    data = fetch_url("https://cloud.google.com/feeds/vertex-ai-release-notes.xml")
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
            items.append({
                "id": make_id("Vertex AI", f"{entry_title}:{title}"),
                "provider": "Vertex AI",
                "title": title,
                "description": section[:500],
                "link": link,
                "date": date_str,
                "regions": extract_regions(section),
            })
    return items


def fetch_azure_openai() -> list[dict]:
    data = fetch_url("https://www.microsoft.com/releasecommunications/api/v2/azure/rss")
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

        items.append({
            "id": make_id("Azure OpenAI", title),
            "provider": "Azure OpenAI",
            "title": title,
            "description": description[:500],
            "link": link,
            "date": date_str,
            "regions": extract_regions(description),
        })
    return items


def fetch_anthropic() -> list[dict]:
    data = fetch_url("https://www.anthropic.com/rss.xml")
    root = ET.fromstring(data)
    items = []
    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        description = strip_html(item.findtext("description", ""))
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()

        if not re.search(r"\bclaude\b", f"{title} {description}", re.IGNORECASE):
            continue
        if not is_model_release(title, description):
            continue

        try:
            dt = parsedate_to_datetime(pub_date)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = pub_date

        items.append({
            "id": make_id("Anthropic", title),
            "provider": "Anthropic",
            "title": title,
            "description": description[:500],
            "link": link,
            "date": date_str,
            "regions": [],
        })
    return items


GEMINI_MODEL_RE = re.compile(
    r"\b(?:gemini|gemma|imagen|veo)\s+[\d]", re.IGNORECASE
)

GEMINI_ENTRY_RE = re.compile(
    r"(\d{4})\.(\d{2})\.(\d{2})(.*?)(?=\d{4}\.\d{2}\.\d{2}|\Z)",
    re.DOTALL,
)

GEMINI_LAUNCH_RE = re.compile(
    r"\b(?:introducing|announcing|launching|releasing|now (?:the )?(?:new )?default|rolling out|is (?:now )?available|available to)\b",
    re.IGNORECASE,
)


def fetch_google_deepmind() -> list[dict]:
    """Scrape gemini.google/release-notes/ for model releases."""
    data = fetch_url("https://gemini.google/release-notes/")
    text = data.decode("utf-8", errors="replace")
    text = strip_html(text)

    items = []
    for match in GEMINI_ENTRY_RE.finditer(text):
        year, month, day = match.group(1), match.group(2), match.group(3)
        date_str = f"{year}-{month}-{day}"
        body = match.group(4).strip()

        title_end = body.find("What:")
        if title_end > 0:
            title = body[:title_end].strip()
            desc = body[title_end + 5:].strip()[:500]
        else:
            title = body[:150].split(".")[0].strip()
            desc = body[:500]

        full_text = f"{title} {desc}"
        if not GEMINI_MODEL_RE.search(full_text):
            continue
        if not GEMINI_LAUNCH_RE.search(full_text):
            continue

        items.append({
            "id": make_id("Google", f"{date_str}:{title}"),
            "provider": "Google",
            "title": title,
            "description": desc,
            "link": "https://gemini.google/release-notes/",
            "date": date_str,
            "regions": [],
        })

    return items


OPENAI_LAUNCH_RE = re.compile(
    r"^introducing\s+(?:gpt[\s\-]?[345o]|dall|sora|whisper|openai\s+o[13])",
    re.IGNORECASE,
)

OPENAI_MODEL_LAUNCH_RE = re.compile(
    r"^(?:hello|new)\s+(?:gpt[\s\-]?[345o]|dall|sora)",
    re.IGNORECASE,
)

OPENAI_SORA_LAUNCH_RE = re.compile(
    r"^sora\s+(?:\d\s+)?is\s+here",
    re.IGNORECASE,
)


def fetch_openai() -> list[dict]:
    data = fetch_url("https://openai.com/blog/rss.xml")
    root = ET.fromstring(data)
    items = []
    for item in root.iter("item"):
        title = item.findtext("title", "").strip()
        description = strip_html(item.findtext("description", ""))
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()

        is_launch = (
            OPENAI_LAUNCH_RE.search(title)
            or OPENAI_MODEL_LAUNCH_RE.search(title)
            or OPENAI_SORA_LAUNCH_RE.search(title)
        )
        if not is_launch:
            continue

        try:
            dt = parsedate_to_datetime(pub_date)
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            date_str = pub_date

        items.append({
            "id": make_id("OpenAI", title),
            "provider": "OpenAI",
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
    fetchers = [
        fetch_aws_bedrock,
        fetch_vertex_ai,
        fetch_azure_openai,
        fetch_anthropic,
        fetch_google_deepmind,
        fetch_openai,
    ]

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
