#!/usr/bin/env python3
"""policy/press watcher: snapshot latest items per source, diff vs repo state
- config: policy_watch.json [{name, mode: rss|html, url, link_regex (html only), limit=30}]
- state: policy_state/<name>.json (committed to repo by CI; FIRST run = baseline, diff empty)
- output: policy_diff.json {generated, sources:{name:{added:[...]}}} ; prints ===POLICY-CHANGED=== N / ===POLICY-CLEAN===
- stdlib-only, zero credentials
"""
import time, json, re, os, urllib.request, urllib.error, urllib.parse, xml.etree.ElementTree as ET

UA = {"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"}
LIM_DEF = 30

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

def parse_rss(raw, limit):
    root = ET.fromstring(raw); items = []
    for it in root.iter():
        if it.tag.split("}")[-1] != "item": continue
        title = link = None
        for ch in it:
            t = ch.tag.split("}")[-1]
            if t == "title" and ch.text: title = " ".join(ch.text.split())
            elif t == "link" and ch.text: link = ch.text.strip()
        if title and link: items.append({"title": title, "link": link})
        if len(items) >= limit: break
    return items

def parse_html(raw, base, link_regex, limit):
    items = []; seen = set()
    for m in re.finditer(r'<a[^>]+href="([^"#]+)"[^>]*>(.*?)</a>', raw.decode("utf-8","replace"), re.S|re.I):
        href, txt = m.group(1).strip(), re.sub(r"<[^>]+>","",m.group(2))
        txt = " ".join(txt.split())
        if not txt or not re.search(link_regex, href): continue
        link = urllib.parse.urljoin(base, href)
        if link in seen: continue
        seen.add(link); items.append({"title": txt, "link": link})
        if len(items) >= limit: break
    return items

def main():
    cfg = json.load(open("policy_watch.json", encoding="utf-8"))
    os.makedirs("policy_state", exist_ok=True)
    out = {"generated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "sources": {}}
    total = 0
    for src in cfg:
        name, mode, url = src["name"], src["mode"], src["url"]
        limit = src.get("limit", LIM_DEF)
        try:
            raw = fetch(url)
            items = parse_rss(raw, limit) if mode == "rss" else parse_html(raw, url, src["link_regex"], limit)
        except Exception as e:
            out["sources"][name] = {"error": str(e)[:100]}; continue
        spath = "policy_state/%s.json" % name
        try:
            prev = {x["link"] for x in json.load(open(spath, encoding="utf-8"))}
            added = [x for x in items if x["link"] not in prev]
        except FileNotFoundError:
            added = []   # first run = baseline, no alert
        json.dump(items, open(spath, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        out["sources"][name] = {"items": len(items), "added": added}
        total += len(added)
    json.dump(out, open("policy_diff.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print("===POLICY-CHANGED=== %d"%total if total else "===POLICY-CLEAN===", flush=True)

if __name__ == "__main__":
    main()
