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
- Tres hilos como maximo, con pausa entre requests (~2 por segundo en total).
- Antes de empezar se vuelve a leer el robots.txt: si dejo de permitir la
  lectura, no se scrapea.
- Solo se piden las paginas publicas de restaurantes que estan en el sitemap.

Captura de respaldo (si el scrape falla, se usa la ultima buena):
- La captura vigente es data/raw/guiaoleo_restaurantes.jsonl. Es la que usa
  el notebook 03 y nunca se escribe a medias.
- Cada corrida escribe en guiaoleo_restaurantes.parcial.jsonl. Si se corta,
  se vuelve a correr y sigue donde quedo.
- Al terminar se valida la captura nueva (cobertura del sitemap, que el parser
  siga encontrando nombres y que no se pierdan la mitad de las resenas). Solo
  si pasa, reemplaza a la vigente, de una sola vez.
- Si falla cualquier cosa (sin red, sitio caido, robots.txt que ahora prohibe,
  rediseno del sitio que rompe el parser), la captura vigente queda intacta y
  el motivo se registra en data/raw/guiaoleo_captura.json.
- Si la captura nueva es buena pero algunas paginas fallaron, esos locales se
  completan con su registro de la captura anterior, marcados con
  "de_captura_anterior": true.

Uso:
    python scripts/scrape_guiaoleo.py              # actualiza todo CABA
    python scripts/scrape_guiaoleo.py --limit 50   # muestra de prueba; no toca la vigente
    python scripts/scrape_guiaoleo.py --desde-cero # descarta una captura parcial vieja
"""

import argparse
import json
import os
import random
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

UA = "ConsultingChallenge-EcoFood/1.0 (TP academico; datos publicos)"
SITIO = "https://guiaoleo.com"
SITEMAP = f"{SITIO}/sitemap-restaurants-1.xml"
BASE = Path(__file__).resolve().parent.parent
RAW = BASE / "data" / "raw"
VIGENTE = RAW / "guiaoleo_restaurantes.jsonl"
PARCIAL = RAW / "guiaoleo_restaurantes.parcial.jsonl"
CACHE_SITEMAP = RAW / "guiaoleo_sitemap.xml"
META = RAW / "guiaoleo_captura.json"

HILOS = 3
PAUSA = 0.45  # segundos entre requests (ritmo global ~2/s)

# Condiciones para que una captura nueva reemplace a la vigente.
MIN_COBERTURA = 0.90       # al menos 90% de las URLs del sitemap bajadas sin error
MIN_CON_NOMBRE = 0.90      # al menos 90% de las paginas con nombre parseado
MIN_RESENAS_VS_ANTERIOR = 0.50  # no perder mas de la mitad de las resenas

_lock = threading.Lock()
_contador = {"ok": 0, "err": 0}


def ahora():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def sesion():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "es-AR,es;q=0.9",
    })
    return s


def verificar_robots():
    """Falla si no se puede leer el robots.txt o si ya no permite las paginas de restaurantes."""
    r = sesion().get(f"{SITIO}/robots.txt", timeout=20)
    r.raise_for_status()
    rp = RobotFileParser()
    rp.parse(r.text.splitlines())
    prueba = f"{SITIO}/buenos-aires/mishiguene"
    if not rp.can_fetch(UA, prueba):
        raise PermissionError("el robots.txt ya no permite leer las paginas de restaurantes")


def bajar_sitemap():
    """Baja el sitemap fresco; si falla, usa el ultimo guardado."""
    try:
        r = sesion().get(SITEMAP, timeout=60)
        r.raise_for_status()
        if "<loc>" not in r.text:
            raise ValueError("el sitemap no trae URLs")
        tmp = CACHE_SITEMAP.with_suffix(".xml.tmp")
        tmp.write_text(r.text, encoding="utf-8")
        os.replace(tmp, CACHE_SITEMAP)
        return r.text
    except Exception as exc:  # noqa: BLE001
        if CACHE_SITEMAP.exists() and CACHE_SITEMAP.stat().st_size > 1000:
            print(f"no se pudo bajar el sitemap ({type(exc).__name__}); se usa el guardado", flush=True)
            return CACHE_SITEMAP.read_text(encoding="utf-8")
        raise


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
        "scraped_at": ahora(),
    }


def una(url, s):
    error = "sin respuesta"
    for intento in range(3):
        try:
            r = s.get(url, timeout=30)
            if r.status_code == 429:
                error = "HTTP 429 (demasiados pedidos) en los 3 intentos"
                time.sleep(5 * (intento + 1))
                continue
            r.raise_for_status()
            return parsear(r.text, url)
        except Exception as exc:  # noqa: BLE001
            error = f"{type(exc).__name__}: {exc}"
            if intento < 2:
                time.sleep(2 * (intento + 1))
    return {"url": url, "slug": url.rsplit("/", 1)[-1], "error": error, "scraped_at": ahora()}


def leer_jsonl(ruta):
    """Devuelve {url: registro}. Si una URL aparece varias veces, gana el ultimo registro sin error."""
    registros = {}
    if not ruta.exists():
        return registros
    for linea in ruta.read_text(encoding="utf-8").splitlines():
        try:
            dato = json.loads(linea)
        except json.JSONDecodeError:
            continue  # linea cortada por una interrupcion
        previo = registros.get(dato.get("url"))
        if previo is None or "error" in previo or "error" not in dato:
            registros[dato["url"]] = dato
    return registros


def leer_meta():
    if META.exists():
        try:
            return json.loads(META.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def escribir_meta(meta):
    tmp = META.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, META)


def registrar_intento(resultado, detalle=""):
    meta = leer_meta()
    meta["ultimo_intento"] = {"fecha": ahora(), "resultado": resultado, "detalle": detalle}
    escribir_meta(meta)


def fecha_de_captura(registros):
    fechas = [d.get("scraped_at") for d in registros.values() if d.get("scraped_at")]
    return max(fechas) if fechas else "fecha desconocida"


def avisar_respaldo(motivo):
    vigente = leer_meta().get("captura_vigente") or {}
    print(f"\nNO se actualizo la captura: {motivo}", flush=True)
    if VIGENTE.exists():
        fecha = vigente.get("fecha") or fecha_de_captura(leer_jsonl(VIGENTE))
        print(f"Se mantiene la captura vigente ({fecha}) en {VIGENTE.relative_to(BASE)}.", flush=True)
        print("El notebook 03 sigue funcionando con esos datos.", flush=True)
    else:
        print("Ojo: tampoco hay una captura anterior. El notebook 03 no tiene datos.", flush=True)
    if PARCIAL.exists():
        print(f"Lo bajado hasta ahora queda en {PARCIAL.relative_to(BASE)}: "
              "al volver a correr se sigue desde ahi.", flush=True)


def capturar(urls, hilos, limit):
    """Baja las URLs que faltan en la captura parcial. Devuelve los registros de la parcial."""
    _contador.update(ok=0, err=0)
    hechos ={u for u, d in leer_jsonl(PARCIAL).items() if "error" not in d}
    pendientes = [u for u in urls if u not in hechos]
    random.seed(42)
    random.shuffle(pendientes)
    if limit:
        pendientes = pendientes[:limit]

    print(f"total CABA: {len(urls)} | ya en la parcial: {len(hechos)} | pendientes: {len(pendientes)}", flush=True)
    if pendientes:
        inicio = time.time()
        with PARCIAL.open("a", encoding="utf-8") as fh, ThreadPoolExecutor(max_workers=hilos) as pool:
            futuros = {}
            for url in pendientes:
                futuros[pool.submit(una, url, sesion())] = url
                time.sleep(PAUSA)
                if len(futuros) >= hilos * 8:
                    for fut in as_completed(list(futuros)):
                        _guardar(fut.result(), fh)
                        futuros.pop(fut, None)
                        _progreso(len(pendientes), inicio)
            for fut in as_completed(list(futuros)):
                _guardar(fut.result(), fh)
                _progreso(len(pendientes), inicio)
        print(f"\nesta corrida: {_contador['ok']} ok | {_contador['err']} errores", flush=True)
    return leer_jsonl(PARCIAL)


def validar(urls, nuevos, anteriores):
    """Devuelve el motivo por el que la captura nueva NO sirve, o None si sirve."""
    ok = [nuevos[u] for u in urls if u in nuevos and "error" not in nuevos[u]]
    cobertura = len(ok) / len(urls) if urls else 0
    if cobertura < MIN_COBERTURA:
        return f"solo {cobertura:.0%} de las paginas se bajaron bien (minimo {MIN_COBERTURA:.0%})"
    con_nombre = sum(1 for d in ok if d.get("nombre")) / len(ok)
    if con_nombre < MIN_CON_NOMBRE:
        return (f"solo {con_nombre:.0%} de las paginas traen nombre: "
                "probablemente el sitio cambio y el parser ya no lo entiende")
    resenas_nuevas = sum(len(d.get("resenas") or []) for d in ok)
    resenas_antes = sum(len(d.get("resenas") or []) for d in anteriores.values() if "error" not in d)
    if resenas_antes and resenas_nuevas < MIN_RESENAS_VS_ANTERIOR * resenas_antes:
        return (f"la captura nueva trae {resenas_nuevas} resenas contra {resenas_antes} de la anterior: "
                "probablemente el parser dejo de encontrarlas")
    return None


def promover(urls, nuevos, anteriores):
    """Arma la captura final y reemplaza la vigente de una sola vez."""
    final, completados, errores = [], 0, 0
    for url in urls:
        dato = nuevos.get(url)
        if dato is not None and "error" not in dato:
            final.append(dato)
        elif url in anteriores and "error" not in anteriores[url]:
            final.append({**anteriores[url], "de_captura_anterior": True})
            completados += 1
        else:
            final.append(dato or {"url": url, "slug": url.rsplit("/", 1)[-1], "error": "no se bajo", "scraped_at": ahora()})
            errores += 1

    tmp = VIGENTE.with_suffix(".jsonl.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        for dato in final:
            fh.write(json.dumps(dato, ensure_ascii=False) + "\n")
    os.replace(tmp, VIGENTE)
    PARCIAL.unlink(missing_ok=True)

    meta = leer_meta()
    meta["captura_vigente"] = {
        "fecha": ahora(),
        "locales": len(final),
        "resenas": sum(len(d.get("resenas") or []) for d in final),
        "completados_con_captura_anterior": completados,
        "errores": errores,
    }
    meta["ultimo_intento"] = {"fecha": ahora(), "resultado": "ok", "detalle": "captura nueva promovida"}
    escribir_meta(meta)
    print(f"captura actualizada: {len(final)} locales | {completados} completados con la anterior | {errores} con error", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="muestra de prueba: no reemplaza la captura vigente")
    ap.add_argument("--hilos", type=int, default=HILOS)
    ap.add_argument("--desde-cero", action="store_true", help="descarta la captura parcial antes de empezar")
    args = ap.parse_args()

    if args.desde_cero:
        PARCIAL.unlink(missing_ok=True)

    try:
        verificar_robots()
        urls = urls_caba()
        if not urls:
            raise ValueError("el sitemap no tiene restaurantes de buenos-aires")
        nuevos = capturar(urls, args.hilos, args.limit)
    except KeyboardInterrupt:
        registrar_intento("interrumpido", "corte manual")
        avisar_respaldo("se interrumpio a mano")
        return 130
    except Exception as exc:  # noqa: BLE001
        registrar_intento("fallo", f"{type(exc).__name__}: {exc}")
        avisar_respaldo(f"{type(exc).__name__}: {exc}")
        return 1

    if args.limit:
        print(f"modo muestra: {len(nuevos)} registros en {PARCIAL.relative_to(BASE)}; "
              "la captura vigente no se toca", flush=True)
        return 0

    anteriores = leer_jsonl(VIGENTE)
    motivo = validar(urls, nuevos, anteriores)
    if motivo:
        registrar_intento("descartado", motivo)
        avisar_respaldo(motivo)
        return 1

    promover(urls, nuevos, anteriores)
    return 0


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
