# LLM Releases

A simple static site and RSS feed that tracks new model releases across cloud providers — so you don't have to watch four different feeds.

**Live site:** https://dannyburke1.github.io/llm-releases

## Providers tracked

- **AWS Bedrock** — via the [AWS What's New](https://aws.amazon.com/about-aws/whats-new/recent/feed/) RSS feed
- **Vertex AI (GCP)** — via the [Vertex AI release notes](https://cloud.google.com/feeds/vertex-ai-release-notes.xml) Atom feed
- **Azure OpenAI** — via the [Azure service updates](https://www.microsoft.com/releasecommunications/api/v2/azure/rss) RSS feed
- **Anthropic** — via the [Anthropic news](https://www.anthropic.com/rss.xml) RSS feed

## How it works

1. A GitHub Actions cron runs daily at 08:00 UTC
2. `scripts/fetch_feeds.py` pulls each provider's public feed, filters for model-related announcements using keyword matching, and deduplicates against existing entries
3. `scripts/build_site.py` generates a static HTML page and RSS feed from `data/models.json`, grouping the same model across providers into a single row
4. If anything changed, the workflow commits and pushes — GitHub Pages serves the result

No API keys or credentials required — everything uses public feeds.

## Running locally

```bash
# Fetch new entries
python3 scripts/fetch_feeds.py

# Build the site
python3 scripts/build_site.py

# Output is in docs/
open docs/index.html
```

## RSS

Subscribe to the feed at: https://dannyburke1.github.io/llm-releases/feed.xml
