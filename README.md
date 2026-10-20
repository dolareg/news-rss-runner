# news-rss-runner

Scheduled news / ticker-news / policy-watch aggregation runner. Fetches ~27 public news RSS feeds
(BBC / Al Jazeera / Guardian / CNBC / MarketWatch / HN / etc.) in 7 rounds
over ~50 minutes, dedupes by link, filters to items published within 12h (UN News: 24h, daily-digest stamps),
and uploads the result as a workflow artifact.

- stdlib-only Python (no dependencies)
- ticker-news: gnews per-ticker RSS from `tickers.txt` (no-op when empty)
- policy-watch: Fed/SEC press + SAFE policy pages, diff vs committed `policy_state/` (changed-only alerts)
- no credentials in this repo; read-only public feeds
