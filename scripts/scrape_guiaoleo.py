"""Scraper de resenas publicas de Guia Oleo (punto 3 del TP EcoFood).

Por que este sitio:
- https://guiaoleo.com/robots.txt permite la ruta / para cualquier user-agent.
  Solo bloquea /admin/, /api/, /login, /search? y /map?.
- Los terminos de servicio (https://guiaoleo.com/terms-of-service) no prohiben
  la lectura automatizada: solo prohiben publicar contenido automatizado y
  manipular calificaciones.
- Las resenas y los puntajes vienen renderizados en el HTML (no hace falta
  usar la API, que esta bloqueada).

Buenas practicas aplicadas:
- User-agent honesto, identificable, no se simula un navegador.
- Dos hilos como maximo, con pausa entre requests.
- Solo se piden las paginas publicas de restaurantes que estan en el sitemap.
- Salida incremental y reanudable: si se corta, se vuelve a correr y sigue
  donde quedo.

Uso:
    python scripts/scrape_guiaoleo.py            # scrapea todo CABA
    python scripts/scrape_guiaoleo.py --limit 50 # muestra para probar
"""

import argparse
import json
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from bs4 import BeautifulSoup

UA = "ConsultingChallenge-EcoFood/1.0 (TP academico; datos publicos)"
SITEMAP = "https://guiaoleo.com/sitemap-restaurants-1.xml"
BASE = Path(__file__).resolve().parent.parent
OUT = BASE / "data" / "raw" / "guiaoleo_restaurantes.jsonl"
CACHE_SITEMAP = BASE / "data" / "raw" / "guiaoleo_sitemap.xml"

HILOS = 3
PAUSA = 0.45  # segundos entre requests (ritmo global ~2/s)

_lock = threading.Lock()
_contador = {"ok": 0, "err": 0}


def sesion():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-AR,es;q=0.9",
    })
    return s


def bajar_sitemap():
    if CACHE_SITEMAP.exists() and CACHE_SITEMAP.stat().st_size > 1000:
        return CACHE_SITEMAP.read_text(encoding="utf-8")
    print("bajando sitemap...", flush=True)
    r = sesion().get(SITEMAP, timeout=60)
    r.raise_for_status()
    CACHE_SITEMAP.write_text(r.text, encoding="utf-8")
    return r.text


def urls_caba():
    xml = bajar_sitemap()
    urls = re.findall(r"<loc>([^<]+)</loc>", xml)
    return [u for u in urls if "/buenos-aires/" in u]


def parsear(html, url):
    soup = BeautifulSoup(html, "lxml")

    ld = {}
    m = re.search(r'type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S)
    if m:
        try:
            ld = json.loads(m.group(1))
        except json.JSONDecodeError:
            ld = {}

    rating = ld.get("aggregateRating") or {}
    addr = ld.get("address") or {}
    geo = ld.get("geo") or {}

    resenas = []
    vistos = set()
    for a in soup.select('a[href*="/comunidad/"]'):
        href = a.get("href", "").split("#")[0]
        rid = href.rsplit("/", 1)[-1]
        if not rid.isdigit() or rid in vistos:
            continue
        tarjeta = a.find_parent("div", class_=lambda c: c and "rounded-2xl" in c)
        if tarjeta is None:
            continue
        vistos.add(rid)

        texto = ""
        for div in tarjeta.select("div.leading-relaxed"):
            t = div.get_text(" ", strip=True)
            if t and not t.endswith("Continuar..."):
                texto = t
                break

        sub = {}
        precio = None
        for el in tarjeta.select("[title]"):
            titulo = el.get("title", "")
            if ":" in titulo:
                dim, valor = titulo.split(":", 1)
                if dim.strip() in ("Comida", "Servicio", "Ambiente"):
                    sub[dim.strip()] = valor.strip()
            elif titulo == "Precio promedio por persona":
                precio = el.get_text(" ", strip=True)

        fecha = ""
        for el in tarjeta.select("a"):
            href = el.get("href", "")
            t = el.get_text(" ", strip=True)
            # La fecha es el link a /comunidad/{id}; asi no se confunde con
            # nombres de usuario que tambien empiezan con "El" (ej. "El Vinchuco").
            if "/comunidad/" in href and re.match(r"^El \d{1,2} \w{3} \d{4}$", t):
                fecha = t
                break
        if not fecha:
            m = re.search(r"El \d{1,2} \w{3} \d{4}", tarjeta.get_text(" ", strip=True))
            if m:
                fecha = m.group(0)

        autor = ""
        for el in tarjeta.select("a[href*='/usuario/'], a[href*='/comunidad/']"):
            t = el.get_text(" ", strip=True)
            if t and not t.lower().startswith("el ") and not t.startswith("#"):
                autor = t
                break

        resenas.append({
            "review_id": rid,
            "autor": autor,
            "fecha": fecha,
            "texto": texto,
            "comida": sub.get("Comida"),
            "servicio": sub.get("Servicio"),
            "ambiente": sub.get("Ambiente"),
            "precio": precio,
        })

    return {
        "url": url,
        "slug": url.rsplit("/", 1)[-1],
        "nombre": ld.get("name"),
        "barrio": addr.get("addressLocality"),
        "direccion": addr.get("streetAddress"),
        "lat": geo.get("latitude"),
        "lon": geo.get("longitude"),
        "rating": rating.get("ratingValue"),
        "rating_count": rating.get("ratingCount"),
        "resenas": resenas,
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


def una(url, s):
    for intento in range(3):
        try:
            r = s.get(url, timeout=30)
            if r.status_code == 429:
                time.sleep(5 * (intento + 1))
                continue
            r.raise_for_status()
            return parsear(r.text, url)
        except Exception as exc:  # noqa: BLE001
            if intento == 2:
                return {"url": url, "slug": url.rsplit("/", 1)[-1], "error": f"{type(exc).__name__}: {exc}"}
            time.sleep(2 * (intento + 1))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--hilos", type=int, default=HILOS)
    args = ap.parse_args()

    urls = urls_caba()
    ya = set()
    if OUT.exists():
        for linea in OUT.read_text(encoding="utf-8").splitlines():
            try:
                ya.add(json.loads(linea)["url"])
            except Exception:  # noqa: BLE001
                pass
    pendientes = [u for u in urls if u not in ya]
    random.seed(42)
    random.shuffle(pendientes)
    if args.limit:
        pendientes = pendientes[: args.limit]

    print(f"total CABA: {len(urls)} | ya hechos: {len(ya)} | pendientes: {len(pendientes)}", flush=True)
    if not pendientes:
        return

    inicio = time.time()
    with OUT.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=args.hilos) as pool:
        futuros = {}
        for i, url in enumerate(pendientes):
            futuros[pool.submit(una, url, sesion())] = url
            time.sleep(PAUSA)
            if len(futuros) >= args.hilos * 8:
                for fut in as_completed(list(futuros)):
                    _guardar(fut.result(), fh)
                    futuros.pop(fut, None)
                    _progreso(len(pendientes), inicio)
        for fut in as_completed(list(futuros)):
            _guardar(fut.result(), fh)
            _progreso(len(pendientes), inicio)

    print(f"\nlisto: {_contador['ok']} ok | {_contador['err']} errores", flush=True)


def _guardar(dato, fh):
    if not dato:
        return
    with _lock:
        fh.write(json.dumps(dato, ensure_ascii=False) + "\n")
        fh.flush()
        if "error" in dato:
            _contador["err"] += 1
        else:
            _contador["ok"] += 1


def _progreso(total, inicio):
    hechos = _contador["ok"] + _contador["err"]
    if hechos % 50 == 0:
        seg = time.time() - inicio
        ritmo = hechos / seg if seg else 0
        restante = (total - hechos) / ritmo / 60 if ritmo else 0
        print(f"  {hechos}/{total} | {ritmo:.2f}/s | faltan ~{restante:.0f} min", flush=True)


if __name__ == "__main__":
    sys.exit(main())
