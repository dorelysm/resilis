"""Datos para los mapas de ruta de las entregas (posición simulada del equipo; ver app/ruta.py)."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app import ruta as rt
from app.db import get_db
from app.web import requiere_rol

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Solicitante = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.SOLICITANTE))]
Donante = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.DONANTE))]
Personal = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.ENTIDAD, m.Rol.BRIGADISTA, m.Rol.ADMINISTRADOR))]
Logistica = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.ENTIDAD, m.Rol.ADMINISTRADOR))]
Equipo = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.EQUIPO_ENTREGA))]
SIN_CACHE = {"Cache-Control": "no-store"}


@router.get("/solicitudes/{sol_id}/ruta.json")
def ruta_propia(sol_id: int, db: Db, usuario: Solicitante):
    sol = db.get(m.Solicitud, sol_id)
    if sol is None or sol.solicitante_id != usuario.id:
        raise HTTPException(status_code=404)
    return JSONResponse(rt.ruta_de_solicitud(db, sol, exacta=True), headers=SIN_CACHE)


@router.get("/recorrido/solicitudes/{sol_id}/ruta.json")
def ruta_del_personal(sol_id: int, db: Db, usuario: Personal):
    sol = db.get(m.Solicitud, sol_id)
    if sol is None:
        raise HTTPException(status_code=404)
    return JSONResponse(rt.ruta_de_solicitud(db, sol, exacta=False), headers=SIN_CACHE)


@router.get("/recorrido/entregas/ruta.json")
def ruta_logistica(db: Db, usuario: Logistica):
    """Todas las entregas en marcha, para llevar el control logístico."""
    return JSONResponse(rt.ruta_logistica(db), headers=SIN_CACHE)


@router.get("/entregas/ruta.json")
def ruta_de_mis_entregas(db: Db, usuario: Equipo):
    """Las entregas en marcha de un equipo de entrega."""
    return JSONResponse(rt.ruta_logistica(db, equipo_id=usuario.id), headers=SIN_CACHE)


@router.get("/donaciones/ruta.json")
def ruta_del_donante(db: Db, usuario: Donante):
    donante = db.scalar(select(m.Donante).where(m.Donante.usuario_id == usuario.id))
    return JSONResponse(rt.ruta_de_donante(db, donante), headers=SIN_CACHE)
