"""Construye data/barrios_atlantico.csv con los barrios de cada municipio del Atlántico.

Fuente: OpenStreetMap (© colaboradores de OpenStreetMap, licencia ODbL), consultada con la API Overpass:
lugares marcados como barrio, urbanización o sector (place=suburb|neighbourhood|quarter) dentro de cada límite
municipal. Cada lugar se asigna al municipio cuyo límite lo contiene.

Uso (necesita internet, se ejecuta una sola vez y el resultado se guarda en el repositorio):
    uv run python scripts/construir_barrios.py
"""
import csv
import json
import re
import unicodedata
import urllib.parse
import sys
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

from app.territorio import MUNICIPIOS  # noqa: E402
SALIDA = RAIZ / "data" / "barrios_atlantico.csv"
ENDPOINT = "https://overpass-api.de/api/interpreter"
AGENTE = "ResilisPrototipo/0.2 (rally-innovacion)"

CONSULTA_BARRIOS = """[out:json][timeout:120];
area["ISO3166-2"="CO-ATL"]->.a;
(node["place"~"^(suburb|neighbourhood|quarter)$"](area.a);
 way["place"~"^(suburb|neighbourhood|quarter)$"](area.a););
out center tags;"""
CONSULTA_POBLADOS = """[out:json][timeout:120];
area["ISO3166-2"="CO-ATL"]->.a;
(node["place"~"^(city|town|village|hamlet)$"](area.a);
 way["place"~"^(city|town|village|hamlet)$"](area.a););
out center tags;"""
CONSULTA_LIMITES = """[out:json][timeout:180];
area["ISO3166-2"="CO-ATL"]->.a;
rel(area.a)["boundary"="administrative"]["admin_level"="6"];
out geom;"""

def clave(texto: str) -> str:
    sin = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", sin.lower())


def consultar(q: str) -> dict:
    req = urllib.request.Request(ENDPOINT, data=urllib.parse.urlencode({"data": q}).encode(),
                                 headers={"User-Agent": AGENTE})
    return json.load(urllib.request.urlopen(req, timeout=200))


def anillos(rel: dict) -> list[list[tuple[float, float]]]:
    """Une los tramos exteriores de una relación en anillos cerrados de (lon, lat)."""
    tramos = [[(p["lon"], p["lat"]) for p in m["geometry"]] for m in rel["members"]
              if m.get("role") == "outer" and m.get("geometry")]
    cerrados = []
    while tramos:
        actual = tramos.pop(0)
        avanzo = True
        while avanzo and actual[0] != actual[-1]:
            avanzo = False
            for i, t in enumerate(tramos):
                if t[0] == actual[-1]:
                    actual += t[1:]
                elif t[-1] == actual[-1]:
                    actual += t[::-1][1:]
                elif t[-1] == actual[0]:
                    actual = t[:-1] + actual
                elif t[0] == actual[0]:
                    actual = t[::-1][:-1] + actual
                else:
                    continue
                tramos.pop(i)
                avanzo = True
                break
        cerrados.append(actual)
    return cerrados


def dentro(punto: tuple[float, float], anillo: list[tuple[float, float]]) -> bool:
    x, y = punto
    d = False
    for (x1, y1), (x2, y2) in zip(anillo, anillo[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            d = not d
    return d


def main() -> None:
    limites = {}
    por_clave = {clave(n): c for c, n in MUNICIPIOS.items()}
    for rel in consultar(CONSULTA_LIMITES)["elements"]:
        codigo = por_clave.get(clave(rel["tags"].get("name", "")))
        if codigo:
            limites[codigo] = anillos(rel)
    faltan = set(MUNICIPIOS) - set(limites)
    if faltan:
        raise SystemExit(f"Sin límite para: {sorted(faltan)}")

    filas, vistos = [], set()

    def agregar(elementos, tipo, solo_codigos=None):
        for e in elementos:
            _agregar(e, tipo, solo_codigos)

    def _agregar(e, tipo, solo_codigos):
        nombre = e.get("tags", {}).get("name", "").strip()
        lat = e.get("lat") or e.get("center", {}).get("lat")
        lon = e.get("lon") or e.get("center", {}).get("lon")
        if not nombre or lat is None:
            return
        codigo = next((c for c, rs in limites.items() if any(dentro((lon, lat), r) for r in rs)), None)
        if codigo is None or (codigo, clave(nombre)) in vistos or (solo_codigos is not None and codigo not in solo_codigos):
            return
        vistos.add((codigo, clave(nombre)))
        filas.append((codigo, nombre, tipo, round(lat, 5), round(lon, 5)))

    agregar(consultar(CONSULTA_BARRIOS)["elements"], "barrio")
    con_barrios = {c for c, *_ in filas}
    # Municipios sin barrios en OpenStreetMap: se usan sus centros poblados y la cabecera municipal.
    agregar(consultar(CONSULTA_POBLADOS)["elements"], "centro poblado", set(MUNICIPIOS) - con_barrios)
    filas.sort()
    with open(SALIDA, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["municipio_codigo", "barrio", "tipo", "lat", "lon"])
        w.writerows(filas)
    conteo = {}
    for c, *_ in filas:
        conteo[c] = conteo.get(c, 0) + 1
    print(f"{len(filas)} barrios en {len(conteo)} municipios")
    for c, n in sorted(conteo.items()):
        print(f"  {MUNICIPIOS[c]}: {n}")
    print("Sin barrios:", [MUNICIPIOS[c] for c in MUNICIPIOS if c not in conteo])


if __name__ == "__main__":
    main()
