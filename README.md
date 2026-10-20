# news-rss-runner

Scheduled news RSS aggregation runner. Fetches ~27 public news RSS feeds
(BBC / Al Jazeera / Guardian / CNBC / MarketWatch / HN / etc.) in 7 rounds
over ~50 minutes, dedupes by link, filters to items published within 12h (UN News: 24h, daily-digest stamps),
and uploads the result as a workflow artifact.

- stdlib-only Python (no dependencies)
- no credentials in this repo; read-only public feeds
