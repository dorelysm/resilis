"""Punto de entrada de la aplicación web de Resilis."""
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import crear_tablas, get_db
from app.models import Municipio


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Al arrancar: crea las tablas que falten. No carga datos: la carga de viviendas es explícita
    (`uv run python -m app.cargas`) y todavía no se ha ejecutado."""
    crear_tablas()
    yield


app = FastAPI(title="Resilis", version="0.1.0", lifespan=lifespan)


@app.get("/salud")
def salud(db: Session = Depends(get_db)) -> dict:
    """Comprueba que la aplicación y la base de datos responden."""
    db.execute(text("SELECT 1"))
    municipios = db.scalar(select(func.count()).select_from(Municipio))
    return {"estado": "ok", "base_de_datos": "ok", "municipios": municipios}
