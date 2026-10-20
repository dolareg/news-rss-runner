#!/usr/bin/env python3
"""news RSS runner v2 (GH Actions edition)
Changes vs box v1 (2026-10-12 demo):
  1. output path via env NEWS_OUT (default ./news.jsonl)  -- was hardcoded /root/
  2. pubDate <=12h hard freshness filter                  -- fixes 60% stale pollution
  3. reddit sources polled only in the LAST round         -- 429 mitigation (datacenter IPs)
  4. writes news.jsonl.gz for artifact upload; stdout payload markers kept as backup channel
still stdlib-only, zero credentials.
"""
import time, gzip, base64, json, os, ssl, urllib.request, xml.etree.ElementTree as ET
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
("mw-pulse","finance","https://feeds.content.dowjones.io/public/rss/mw_marketpulse"),
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
FRESH_H = 12  # hard freshness window
seen = set(); out = None

def fresh(ts):
    """True = keep. Undateable -> keep (conservative). Parseable & >12h old -> drop."""
    if not ts: return True
    t = ts.strip()
    for fn in (lambda x: parsedate_to_datetime(x).timestamp(),
               lambda x: __import__("datetime").datetime.fromisoformat(x.replace("Z","+00:00")).timestamp()):
        try:
            age_h = (time.time() - fn(t))/3600.0
            return age_h <= FRESH_H
        except Exception: continue
    return True

def parse(name,cat,raw):
    items=[]
    try:
        root=ET.fromstring(raw)
        for it in root.iter():
            tag=it.tag.split("}")[-1]
            if tag in ("item","entry"):
                d={"src":name,"cat":cat}
                for ch in it:
                    t=ch.tag.split("}")[-1]
                    if t=="title" and ch.text: d["title"]=" ".join(ch.text.split())
                    elif t=="link": d["link"]=(ch.get("href") or ch.text or "").strip()
                    elif t in ("guid","id") and ch.text and "link" not in d: d["link"]=ch.text.strip()
                    elif t in ("pubDate","published","updated","date") and ch.text: d["ts"]=" ".join(ch.text.split())
                if d.get("title") and d.get("link") and fresh(d.get("ts")): items.append(d)
    except Exception: pass
    return items

def fetch(url):
    req=urllib.request.Request(url,headers=UA)
    with urllib.request.urlopen(req,timeout=15) as r: return r.read()

def round_n(n,total):
    tot=0; stat=[]
    last = (n==total)
    for name,cat,url in S:
        if name.startswith("rdt") and not last: continue   # reddit only in final round
        if name.startswith("rdt"): time.sleep(5)
        try:
            new=0
            for d in parse(name,cat,fetch(url)):
                k=d["link"]
                if k in seen: continue
                seen.add(k); d["first_seen"]=time.strftime("%Y-%m-%dT%H:%M:%SZ",time.gmtime())
                out.write(json.dumps(d,ensure_ascii=False)+"\n"); new+=1
            tot+=new; stat.append(name+":"+str(new))
        except Exception: stat.append(name+":ERR")
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
