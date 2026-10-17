"""Mapa de sectores: prioridad y confianza sobre el territorio (bloque 7). No lleva datos de personas."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app import puntaje as pj
from app.db import get_db
from app.rutas.prioridades import refrescar
from app.web import render, requiere_rol

router = APIRouter(prefix="/mapa")
Db = Annotated[Session, Depends(get_db)]
Ve = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.ENTIDAD, m.Rol.BRIGADISTA, m.Rol.ADMINISTRADOR))]


@router.get("")
def mapa(request: Request, db: Db, usuario: Ve):
    return render(request, "mapa.html", usuario, alertas=pj.ALERTAS)


@router.get("/datos.json")
def datos(db: Db, usuario: Ve):
    """Un renglón por sector con ubicación: lo justo para dibujarlo. Si todavía no se calculó nada, se calcula."""
    if db.scalar(select(func.count()).select_from(m.PuntajeSector)) == 0:
        refrescar(db)
    filas = db.execute(
        select(m.PuntajeSector, m.Sector, m.Municipio.nombre)
        .join(m.Sector, m.Sector.id == m.PuntajeSector.sector_id)
        .join(m.Municipio, m.Municipio.codigo == m.Sector.municipio_codigo)
        .where(m.Sector.lat.is_not(None), m.Sector.lon.is_not(None))
        .order_by(m.PuntajeSector.posicion)).all()
    sectores = [{
        "id": s.id, "nombre": s.nombre, "municipio": municipio, "codigo_municipio": s.municipio_codigo,
        "lat": round(s.lat, 5), "lon": round(s.lon, 5), "personas": s.personas,
        "prioridad": round(p.prioridad, 4), "posicion": p.posicion, "confianza": round(p.confianza, 4),
        "alertas": p.alertas or [], "n_reportes": p.n_reportes, "n_solicitudes": p.n_solicitudes,
        "base_previa": bool(p.base_previa),
    } for p, s, municipio in filas]
    municipios = sorted({(x["codigo_municipio"], x["municipio"]) for x in sectores}, key=lambda t: t[1])
    calculado = max((p.calculado_en for p, _, _ in filas), default=None)
    return JSONResponse(
        {"sectores": sectores, "total": len(sectores), "alertas": pj.ALERTAS,
         "municipios": [{"codigo": c, "nombre": n} for c, n in municipios],
         "calculado_en": calculado.isoformat() if calculado else None},
        headers={"Cache-Control": "no-store"})
