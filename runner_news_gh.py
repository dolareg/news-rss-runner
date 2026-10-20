#!/usr/bin/env python3
"""news RSS runner v3 (GH Actions edition)
Changes vs v2 (2026-10-20, after demo run 39366926550):
  1. failed sources log HTTP status + error body snippet      -- was bare "ERR", 429s were unprovable
  2. reddit: 8s spacing + 429-aware retry (40s/60s backoff)   -- still last-round-only
  3. zero-new sources show raw/drop counts                    -- "un:0" is now explainable
  4. dropped mw-pulse (feed frozen since 2025-07; MarketWatch retired the column)
  5. un freshness override 24h (UN News stamps all items with one daily 12:00 UTC ts)
v2 (2026-10-20): NEWS_OUT env / <=12h freshness / reddit last-round-only / gz artifact
still stdlib-only, zero credentials.
"""
import time, gzip, base64, json, os, ssl, urllib.request, urllib.error, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

S = [
("bbc-top","breaking","https://feeds.bbci.co.uk/news/rss.xml"),
("aljazeera","breaking","https://www.aljazeera.com/xml/rss/all.xml"),
("rdt-worldnews","breaking","https://www.reddit.com/r/worldnews/.rss"),
("bbc-world","politics","https://feeds.bbci.co.uk/news/world/rss.xml"),
("nyt-world","politics","https://rss.nytimes.com/services/xml/rss/nyt/World.xml"),
("guardian","politics","https://www.theguardian.com/world/rss"),
("dw","politics","https://rss.dw.com/rdf/rss-en-world"),
("npr","politics","https://feeds.npr.org/1004/rss.xml"),
("un","politics","https://news.un.org/feed/subscribe/en/news/all/rss.xml"),
("france24","politics","https://www.france24.com/en/rss"),
("rdt-geopolitics","politics","https://www.reddit.com/r/geopolitics/.rss"),
("mw-top","finance","https://feeds.content.dowjones.io/public/rss/mw_topstories"),
("cnbc-top","finance","https://www.cnbc.com/id/100003114/device/rss/rss.html"),
("cnbc-fin","finance","https://www.cnbc.com/id/20910258/device/rss/rss.html"),
("yfin","finance","https://feeds.finance.yahoo.com/rss/2.0/headline?s=%5EGSPC&region=US&lang=en-US"),
("investing","finance","https://www.investing.com/rss/news_25.rss"),
("gnews-fin","finance","https://news.google.com/rss/search?q=finance+OR+markets+when:1d&hl=en-US&gl=US&ceid=US:en"),
("sa","finance","https://seekingalpha.com/market_currents.xml"),
("rdt-finance","finance","https://www.reddit.com/r/finance/.rss"),
("rdt-economics","finance","https://www.reddit.com/r/Economics/.rss"),
("hn","tech","https://hnrss.org/frontpage"),
("techcrunch","tech","https://techcrunch.com/feed/"),
("arstechnica","tech","https://feeds.arstechnica.com/arstechnica/index"),
("verge","tech","https://www.theverge.com/rss/index.xml"),
("wired","tech","https://www.wired.com/feed/rss"),
("mittr","tech","https://www.technologyreview.com/feed/"),
("rdt-technology","tech","https://www.reddit.com/r/technology/.rss"),
]
UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
OUT = os.environ.get("NEWS_OUT", "news.jsonl")
FRESH_H = 12            # hard freshness window (hours)
FRESH_OVR = {"un": 24}  # per-source override: UN News daily-digest stamps (all items share one 12:00 UTC ts)
REDDIT_GAP_S = 8        # spacing between reddit fetches
seen = set(); out = None

class FetchErr(Exception):
    """fetch/parse failure carrying HTTP status or error detail"""

def _err_detail(e):
    if isinstance(e, urllib.error.HTTPError):
        try:
            body = e.read(200).decode("utf-8", "replace").replace("\n", " ").strip()
        except Exception:
            body = ""
        return "http %s %s" % (e.code, body[:120])
    return "%s: %s" % (type(e).__name__, str(e)[:100])

def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read()
    except Exception as e:
        raise FetchErr(_err_detail(e))

def fetch_reddit(url):
    """429-aware fetch: two backoff retries (40s, 60s), then give up."""
    for attempt in range(3):
        try:
            return fetch(url)
        except FetchErr as e:
            if attempt < 2 and "http 429" in str(e):
                time.sleep(40 if attempt == 0 else 60)
                continue
            raise

def fresh(ts, limit=None):
    """True = keep. Undateable -> keep (conservative). Parseable & older than limit -> drop."""
    if limit is None: limit = FRESH_H
    if not ts: return True
    t = ts.strip()
    for fn in (lambda x: parsedate_to_datetime(x).timestamp(),
               lambda x: __import__("datetime").datetime.fromisoformat(x.replace("Z","+00:00")).timestamp()):
        try:
            age_h = (time.time() - fn(t))/3600.0
            return age_h <= limit
        except Exception: continue
    return True

def parse(name, cat, raw, limit):
    """returns (items, n_raw, n_filtered); raises FetchErr on XML parse failure"""
    try:
        root = ET.fromstring(raw)
    except Exception as e:
        raise FetchErr("xml: %s" % str(e)[:100])
    items = []; n_raw = 0; n_filtered = 0
    for it in root.iter():
        tag = it.tag.split("}")[-1]
        if tag in ("item", "entry"):
            n_raw += 1
            d = {"src": name, "cat": cat}
            for ch in it:
                t = ch.tag.split("}")[-1]
                if t == "title" and ch.text: d["title"] = " ".join(ch.text.split())
                elif t == "link": d["link"] = (ch.get("href") or ch.text or "").strip()
                elif t in ("guid","id") and ch.text and "link" not in d: d["link"] = ch.text.strip()
                elif t in ("pubDate","published","updated","date") and ch.text: d["ts"] = " ".join(ch.text.split())
            if d.get("title") and d.get("link"):
                if fresh(d.get("ts"), limit): items.append(d)
                else: n_filtered += 1
    return items, n_raw, n_filtered

def round_n(n, total):
    tot = 0; stat = []
    last = (n == total)
    for name, cat, url in S:
        if name.startswith("rdt") and not last: continue   # reddit only in final round
        if name.startswith("rdt"): time.sleep(REDDIT_GAP_S)
        try:
            raw = fetch_reddit(url) if name.startswith("rdt") else fetch(url)
            items, n_raw, n_drop = parse(name, cat, raw, FRESH_OVR.get(name))
            new = 0
            for d in items:
                k = d["link"]
                if k in seen: continue
                seen.add(k); d["first_seen"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                out.write(json.dumps(d, ensure_ascii=False) + "\n"); new += 1
            tot += new
            stat.append("%s:%d%s" % (name, new, "" if new else "(raw=%d,drop=%d)" % (n_raw, n_drop)))
        except FetchErr as e:
            stat.append("%s:ERR(%s)" % (name, e))
    out.flush()
    print("[round %d/%d] new=%d | %s"%(n,total,tot," ".join(stat)),flush=True)

def main():
    global out
    out = open(OUT, "a", encoding="utf-8")
    ROUNDS=7
    start=time.time()
    for n in range(ROUNDS):
        round_n(n+1,ROUNDS)
        if n<ROUNDS-1:
            wait=start+(n+1)*420-time.time()
            if wait>0: time.sleep(wait)

    out.close()
    raw=open(OUT,"rb").read()
    gz=gzip.compress(raw,9)
    open(OUT+".gz","wb").write(gz)   # artifact payload
    b=base64.b64encode(gz).decode()
    print("===PAYLOAD items=%d bytes=%d==="%(len(seen),len(raw)),flush=True)
    for i in range(0,len(b),76): print(b[i:i+76],flush=True)
    print("===END===",flush=True)

if __name__ == "__main__":
    main()
