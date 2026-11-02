"""Lee los RSS de feeds.json y genera news.json. Solo biblioteca estándar de Python."""
import json, re, html, hashlib, urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

MAX_POR_FEED = 40
MAX_TOTAL = 400

def limpiar(t):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    t = re.sub(r"\s+", " ", t).strip()
    return t[:280]

def fecha(s):
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except Exception:
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except Exception:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc).isoformat()

def txt(el, *tags):
    for t in tags:
        f = el.find(t)
        if f is not None and (f.text or "").strip():
            return f.text.strip()
    return ""

def leer(feed):
    req = urllib.request.Request(feed["url"], headers={"User-Agent": "Observatorio/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        raiz = ET.fromstring(r.read())
    out = []
    A = "{http://www.w3.org/2005/Atom}"
    for it in (raiz.findall(".//item") or raiz.findall(".//" + A + "entry"))[:MAX_POR_FEED]:
        link = txt(it, "link")
        if not link:
            l = it.find(A + "link")
            link = l.get("href", "") if l is not None else ""
        d = fecha(txt(it, "pubDate", A + "published", A + "updated"))
        titulo = limpiar(txt(it, "title", A + "title"))
        if not (titulo and link and d):
            continue
        out.append({
            "id": hashlib.md5(link.encode()).hexdigest()[:12],
            "source": feed["source"], "title": titulo,
            "description": limpiar(txt(it, "description", A + "summary", A + "content")),
            "url": link, "date": d, "category": feed.get("category", ""),
        })
    return out

items = []
for f in json.load(open("feeds.json", encoding="utf-8")):
    try:
        items += leer(f)
        print("OK ", f["source"])
    except Exception as e:
        print("FALLÓ", f["source"], e)

vistos, unicos = set(), []
for i in sorted(items, key=lambda x: x["date"], reverse=True):
    if i["url"] not in vistos:
        vistos.add(i["url"]); unicos.append(i)

# Si todos los feeds fallan, no se sobrescribe el news.json anterior.
if unicos:
    json.dump({"updated": datetime.now(timezone.utc).isoformat(), "items": unicos[:MAX_TOTAL]},
              open("news.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
