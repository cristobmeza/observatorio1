"""Lee los RSS de feeds.json y genera news.json y estado.json. Solo biblioteca estándar.

Por cada medio: usa "url" si existe; si no, intenta descubrir el RSS en la página
principal ("site") mediante <link rel="alternate">. Si no encuentra uno válido,
lo registra como «sin RSS utilizable» y no inventa nada.
"""
import json, re, html, hashlib, urllib.request, urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

MAX_POR_FEED, MAX_TOTAL = 40, 400
UA = {"User-Agent": "Mozilla/5.0 (compatible; Observatorio/1.0)"}
A = "{http://www.w3.org/2005/Atom}"

# Clasificación por palabras clave (heurística; coincide con el inicio de palabra).
# Orden: ante empate gana la primera subsección.
KW = {
"Elecciones": ["elecci", "electoral", "servel", "candidat", "plebiscit", "primarias", "votaci"],
"Congreso Nacional": ["diputad", "senador", "senadora", "senado", "congreso", "cámara de diputados"],
"Partidos políticos": ["partido", "militante", "oficialismo", "oposición", "coalición", "directiva del"],
"Regiones (Los Ríos)": ["valdivia", "los ríos", "la unión", "panguipulli", "río bueno", "lago ranco", "paillaco", "futrono"],
"Gobierno y administración pública": ["gobierno", "ministr", "subsecretar", "la moneda", "gabinete", "alcalde", "delegado presidencial"],
"Economía nacional": ["imacec", "desempleo", "cobre", "ipc", "pib", "inflación"],
"Sociedad": ["educación", "salud", "delincuencia", "vivienda", "pensiones", "migra", "seguridad ciudadana"],
"Política monetaria": ["tasa de interés", "reserva federal", "banco central", "tpm"],
"Finanzas públicas": ["presupuesto", "déficit fiscal", "deuda pública", "dipres", "gasto fiscal"],
"Tributación": ["impuesto", "tributari", "sii", "reforma tributaria"],
"Comercio internacional": ["arancel", "exportaci", "importaci", "comercio exterior", "omc", "libre comercio"],
"Empresas y mercados": ["bolsa", "acciones", "utilidades", "fusión", "mercados", "empresa"],
"Jurisprudencia": ["corte suprema", "corte de apelaciones", "sentencia", "fallo", "tribunal"],
"Derecho constitucional": ["constitución", "constitucional", "tribunal constitucional"],
"Legislación chilena": ["proyecto de ley", "promulg", "diario oficial", "tramitación"],
"Administración pública": ["contraloría", "funcionarios públicos", "servicio civil"],
"Derecho internacional": ["corte internacional", "tribunal penal internacional", "derecho internacional", "tratado"],
"Rusia y espacio postsoviético": ["rusia", "putin", "kremlin", "ucrania", "moscú", "kiev", "bielorrusia"],
"Oriente Medio": ["gaza", "israel", "irán", "palestin", "siria", "líbano", "yemen", "arabia saudita", "hamás"],
"Conflictos armados y seguridad internacional": ["guerra", "misil", "bombardeo", "alto el fuego", "ejército", "ofensiva"],
"China y Asia": ["china", "pekín", "japón", "india", "taiwán", "corea", "asia"],
"África": ["áfrica", "sudán", "nigeria", "etiopía", "congo", "sahel"],
"Estados Unidos y Canadá": ["estados unidos", "trump", "casa blanca", "canadá", "washington"],
"Europa": ["unión europea", "bruselas", "alemania", "francia", "españa", "reino unido", "italia", "europa"],
"América Latina": ["argentina", "brasil", "méxico", "colombia", "venezuela", "perú", "bolivia", "ecuador", "cuba", "latinoamérica"],
"Relaciones internacionales y geopolítica": ["onu", "otan", "cumbre", "diplomac", "sanciones", "brics", "g20"],
"Filosofía política": ["filosof", "ensayo"],
"Socialismo y pensamiento económico": ["socialis", "marx", "keynes"],
}

def clasificar(titulo, desc, defecto):
    t = (titulo + " " + desc).lower()
    mejor, n = None, 0
    for sub, kws in KW.items():
        h = sum(1 for k in kws if re.search(r"\b" + re.escape(k), t))
        if h > n:
            mejor, n = sub, h
    return mejor or defecto or ""

def limpiar(t):
    t = re.sub(r"<[^>]+>", " ", html.unescape(t or ""))
    return re.sub(r"\s+", " ", t).strip()[:280]

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

def local(e):
    return e.tag.rsplit("}", 1)[-1] if isinstance(e.tag, str) else ""

def txt(el, *names):
    for n in names:
        for c in el:
            if local(c) == n and (c.text or "").strip():
                return c.text.strip()
    return ""

def enlace(el):
    href = ""
    for c in el:
        if local(c) == "link":
            if (c.text or "").strip():
                return c.text.strip()
            if c.get("href") and (not href or c.get("rel") in (None, "alternate")):
                href = c.get("href")
    return href

def descargar(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
        return r.read()

def descubrir(site):
    """Busca <link rel="alternate" type="application/rss+xml|atom+xml"> en la portada."""
    h = descargar(site).decode("utf-8", "ignore")
    urls = []
    for tag in re.findall(r"<link[^>]+>", h, flags=re.I):
        if re.search(r"alternate", tag, re.I) and re.search(r"(rss|atom)\+xml", tag, re.I):
            m = re.search(r'href=["\']([^"\']+)', tag, re.I)
            if m:
                urls.append(urllib.parse.urljoin(site, html.unescape(m.group(1))))
    return urls

def parsear(raw, nombre, defecto):
    raiz = ET.fromstring(raw)
    nodos = [e for e in raiz.iter() if local(e) in ("item", "entry")]
    out = []
    for it in nodos[:MAX_POR_FEED]:
        link, d = enlace(it), fecha(txt(it, "pubDate", "published", "updated", "date"))
        titulo = limpiar(txt(it, "title"))
        if not (titulo and link and d):
            continue
        desc = limpiar(txt(it, "description", "summary", "content"))
        out.append({"id": hashlib.md5(link.encode()).hexdigest()[:12], "source": nombre,
                    "title": titulo, "description": desc, "url": link, "date": d,
                    "category": clasificar(titulo, desc, defecto)})
    print("   ", nombre, "-> elementos en el XML:", len(nodos), "| válidos:", len(out))
    return out

items, estado = [], {}
for f in json.load(open("feeds.json", encoding="utf-8")):
    nombre, err, usada = f["source"], "", ""
    try:
        cand = list(f.get("urls", []))
        if f.get("url"):
            cand.append(f["url"])
        if not cand and f.get("site"):
            try:
                cand = descubrir(f["site"])
            except Exception as e:
                err = str(e)[:120]
            # Rutas habituales de RSS; solo valen si responden con un feed válido.
            cand += [urllib.parse.urljoin(f["site"], p) for p in ("/feed/", "/rss", "/rss.xml", "/feed")]
        if not cand:
            raise RuntimeError("no se encontró RSS")
        got = None
        for u in cand:
            try:
                got = parsear(descargar(u), nombre, f.get("category"))
                if got:
                    usada = u
                    break
            except Exception as e:
                err = str(e)[:120]
        if not got:
            raise RuntimeError(err or "feed vacío")
        items += got
        estado[nombre] = {"ok": True, "n": len(got), "url": usada}
        print("OK    ", nombre, len(got), usada)
    except Exception as e:
        estado[nombre] = {"ok": False, "err": str(e)[:120]}
        print("FALLÓ ", nombre, e)

vistos, unicos = set(), []
for i in sorted(items, key=lambda x: x["date"], reverse=True):
    if i["url"] not in vistos:
        vistos.add(i["url"]); unicos.append(i)

now = datetime.now(timezone.utc).isoformat()
if unicos:  # si todo falla, se conserva el news.json anterior
    json.dump({"updated": now, "items": unicos[:MAX_TOTAL]}, open("news.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
json.dump({"updated": now, "feeds": estado}, open("estado.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
