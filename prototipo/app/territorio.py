"""Territorio: los 23 municipios del Atlántico y los barrios de cada uno.

Los nombres y las coordenadas de los barrios salen de OpenStreetMap (© colaboradores de OpenStreetMap, ODbL), guardados
en data/barrios_atlantico.csv por scripts/construir_barrios.py. Donde OpenStreetMap no tiene barrios (varios
municipios pequeños) se usan los centros poblados. El conteo de viviendas de cada barrio NO es oficial: se reparte de
forma simulada de modo que la suma de los barrios de un municipio coincida con la cifra oficial del municipio.
"""
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

CSV_BARRIOS = Path(__file__).resolve().parent.parent / "data" / "barrios_atlantico.csv"

# Código DANE -> nombre correcto (el archivo de viviendas perdió las tildes de algunos nombres).
MUNICIPIOS = {
    "08001": "Barranquilla", "08078": "Baranoa", "08137": "Campo de la Cruz", "08141": "Candelaria",
    "08296": "Galapa", "08372": "Juan de Acosta", "08421": "Luruaco", "08433": "Malambo", "08436": "Manatí",
    "08520": "Palmar de Varela", "08549": "Piojó", "08558": "Polonuevo", "08560": "Ponedera",
    "08573": "Puerto Colombia", "08606": "Repelón", "08634": "Sabanagrande", "08638": "Sabanalarga",
    "08675": "Santa Lucía", "08685": "Santo Tomás", "08758": "Soledad", "08770": "Suan", "08832": "Tubará",
    "08849": "Usiacurí",
}


def leer_barrios(ruta: Path = CSV_BARRIOS) -> dict[str, list[dict]]:
    """Barrios del archivo, agrupados por código de municipio: [{nombre, tipo, lat, lon}]."""
    por_municipio: dict[str, list[dict]] = {}
    with open(ruta, encoding="utf-8", newline="") as f:
        for fila in csv.DictReader(f):
            por_municipio.setdefault(fila["municipio_codigo"], []).append(
                {"nombre": fila["barrio"], "tipo": fila["tipo"], "lat": float(fila["lat"]), "lon": float(fila["lon"])})
    return por_municipio


def corregir_nombres_municipios(db: Session) -> int:
    """Pone los nombres con sus tildes. Devuelve cuántos cambió."""
    from app.models import Municipio

    n = 0
    for mun in db.scalars(select(Municipio)):
        correcto = MUNICIPIOS.get(mun.codigo)
        if correcto and mun.nombre != correcto:
            mun.nombre = correcto
            n += 1
    if n:
        db.commit()
    return n
