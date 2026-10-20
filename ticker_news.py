#!/usr/bin/env python3
"""ticker news collector: gnews per-ticker RSS (holdings watchlist)
- tickers.txt: one per line, `SYMBOL` or `SYMBOL|中文名` (# comments / blank skipped)
- per ticker: en query (symbol) + zh query (symbol or 中文名), gnews search when:1d
- output: ticker_news.jsonl (ALWAYS created, even with 0 tickers; dedup by link, fresh<=24h)
- stdlib-only, zero credentials
"""
import time, json, urllib.request, urllib.error, urllib.parse, xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
FRESH_H = 24

def _err_detail(e):
    if isinstance(e, urllib.error.HTTPError):
        try: body = e.read(150).decode("utf-8","replace").replace("\n"," ").strip()
        except Exception: body = ""
        return "http %s %s" % (e.code, body[:100])
    return "%s: %s" % (type(e).__name__, str(e)[:90])

def fetch(url):
    req = urllib.request.Request(url, headers=UA)
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.read()
    except Exception as e:
        raise RuntimeError(_err_detail(e))

def fresh(ts, limit=FRESH_H):
    if not ts: return True
    t = ts.strip()
    for fn in (lambda x: parsedate_to_datetime(x).timestamp(),
               lambda x: __import__("datetime").datetime.fromisoformat(x.replace("Z","+00:00")).timestamp()):
        try: return (time.time()-fn(t))/3600.0 <= limit
        except Exception: continue
    return True

def gnews(q, lang):
    hl, gl, ceid = ("en-US","US","US:en") if lang=="en" else ("zh-CN","CN","CN:zh")
    url = "https://news.google.com/rss/search?q=%s+when:1d&hl=%s&gl=%s&ceid=%s" % (urllib.parse.quote(q), hl, gl, ceid)
    root = ET.fromstring(fetch(url))
    items = []
    for it in root.iter():
        if it.tag.split("}")[-1] != "item": continue
        d = {"title": None, "link": None, "ts": None, "src": None}
        for ch in it:
            t = ch.tag.split("}")[-1]
            if t == "title" and ch.text: d["title"] = " ".join(ch.text.split())
            elif t == "link" and ch.text: d["link"] = ch.text.strip()
            elif t in ("pubDate","published","updated") and ch.text: d["ts"] = " ".join(ch.text.split())
            elif t == "source" and ch.text: d["src"] = ch.text.strip()
        if d["title"] and d["link"] and fresh(d["ts"]):
            d["lang"] = lang; items.append(d)
    return items

def load_tickers(path):
    out = []
    try:
        for line in open(path, encoding="utf-8"):
            s = line.strip()
            if not s or s.startswith("#"): continue
            sym, _, alias = s.partition("|")
            out.append((sym.strip().upper(), alias.strip()))
    except FileNotFoundError:
        pass
    return out

def main():
    tickers = load_tickers("tickers.txt")
    rows = []; seen = set(); stat = []
    for sym, alias in tickers:
        got = 0
        for q, lang in ((sym,"en"), (alias or sym,"zh")):
            try:
                for d in gnews(q, lang):
                    k = d["link"]
                    if k in seen: continue
                    seen.add(k); d["ticker"] = sym; rows.append(d); got += 1
            except Exception as e:
                stat.append("%s/%s:ERR(%s)" % (sym, lang, str(e)[:60]))
        stat.append("%s:%d" % (sym, got))
        time.sleep(1.2)
    with open("ticker_news.jsonl","w",encoding="utf-8") as f:
        for d in rows: f.write(json.dumps(d, ensure_ascii=False)+"\n")
    print("[ticker-news] tickers=%d items=%d | %s"%(len(tickers),len(rows)," ".join(stat)),flush=True)

if __name__ == "__main__":
    main()
