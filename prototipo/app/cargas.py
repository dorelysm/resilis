"""Carga de datos base: proyecciones de viviendas por municipio del Atlántico (datos abiertos)."""
import csv
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Municipio, ViviendaProyeccion
from app.territorio import MUNICIPIOS

CSV_VIVIENDAS = Path(__file__).resolve().parent.parent / "data" / "viviendas_atlantico.csv"


def _entero(valor: str) -> int:
    """'344.262' -> 344262. El archivo usa el punto como separador de miles."""
    return int(valor.replace(".", "").replace(",", "").strip())


def cargar_viviendas(db: Session, ruta: Path = CSV_VIVIENDAS) -> dict[str, int]:
    # Solo se ejecuta de forma explícita; la aplicación no la llama al arrancar.
    """Carga municipios y proyecciones. Es idempotente: si ya hay datos, no los duplica."""
    if db.scalar(select(ViviendaProyeccion.id).limit(1)) is not None:
        return {"municipios": 0, "proyecciones": 0}

    municipios: dict[str, Municipio] = {}
    n_proy = 0
    with open(ruta, encoding="utf-8-sig", newline="") as f:
        lector = csv.DictReader(f)
        anios = [c for c in lector.fieldnames if c.isdigit()]
        for fila in lector:
            codigo = fila["Código Municipio"].strip()
            if codigo not in municipios:
                m = db.get(Municipio, codigo) or Municipio(codigo=codigo, nombre=MUNICIPIOS.get(codigo, fila["Nombre Municipio"].strip()))
                db.add(m)
                municipios[codigo] = m
            for anio in anios:
                db.add(
                    ViviendaProyeccion(
                        municipio_codigo=codigo,
                        area=fila["Área"].strip(),
                        anio=int(anio),
                        viviendas=_entero(fila[anio]),
                    )
                )
                n_proy += 1
    db.commit()
    return {"municipios": len(municipios), "proyecciones": n_proy}


if __name__ == "__main__":  # uv run python -m app.cargas
    from app.db import SessionLocal

    with SessionLocal() as sesion:
        print(cargar_viviendas(sesion))
