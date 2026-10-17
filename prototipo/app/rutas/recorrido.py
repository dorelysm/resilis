"""Recorrido de la ayuda: dónde está cada cosa y dónde se acumula el trabajo."""
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app import models as m
from app import recorrido as rc
from app.solicitud_info import adjuntar_detalles
from app.db import get_db
from app.rutas.prioridades import NECESIDAD, URGENCIA
from app.web import render, requiere_rol

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Ve = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.ENTIDAD, m.Rol.BRIGADISTA, m.Rol.ADMINISTRADOR))]


@router.get("/recorrido")
def ver_recorrido(request: Request, db: Db, usuario: Ve, tipo: str = "", etapa: str = ""):
    elegida, elementos, total_etapa = None, [], 0
    if tipo in rc.ETAPAS:
        for clave, titulo, ayuda in rc.ETAPAS[tipo]:
            if clave == etapa:
                elegida = {"titulo": rc.TITULOS[tipo], "etapa_titulo": titulo, "ayuda": ayuda}
                todos = rc.elementos_de_etapa(db, tipo, etapa, limite=10_000)
                total_etapa, elementos = len(todos), todos[:25]
    return render(request, "recorrido.html", usuario, recorridos=rc.panel(db), tipo=tipo if elegida else "",
                  etapa=etapa if elegida else "", elegida=elegida, elementos=elementos, total_etapa=total_etapa,
                  puede_logistica=usuario.rol in (m.Rol.ENTIDAD, m.Rol.ADMINISTRADOR))


@router.get("/recorrido/solicitudes/{sol_id}")
def recorrido_solicitud(sol_id: int, request: Request, db: Db, usuario: Ve):
    sol = db.get(m.Solicitud, sol_id)
    if sol is None:
        raise HTTPException(status_code=404)
    barrio = db.get(m.Barrio, sol.barrio_id)
    adjuntar_detalles(db, [sol])
    return render(request, "recorrido_solicitud.html", usuario, sol=sol, barrio=barrio.etiqueta if barrio else "",
                  pasos=rc.pasos_solicitud(db, sol), necesidad=NECESIDAD, urgencia=URGENCIA)
