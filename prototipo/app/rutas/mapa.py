"""Mapa de barrios: prioridad, confianza y qué se necesita en cada uno (bloque 7). No lleva datos de personas: las
necesidades van por barrio, sin nombres, teléfonos, direcciones ni el punto de cada vivienda."""
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app import puntaje as pj
from app.db import get_db
from app.rutas.prioridades import refrescar
from app.simulacion import UNIDADES
from app.solicitud_info import adjuntar_detalles
from app.web import render, requiere_rol

router = APIRouter(prefix="/mapa")
Db = Annotated[Session, Depends(get_db)]
Ve = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.ENTIDAD, m.Rol.BRIGADISTA, m.Rol.ADMINISTRADOR))]
ABIERTAS = [m.EstadoSolicitud.REGISTRADA, m.EstadoSolicitud.VERIFICADA, m.EstadoSolicitud.ASIGNADA,
            m.EstadoSolicitud.EN_CAMINO]
MAX_NECESIDADES_POR_BARRIO = 12
LARGO_DESCRIPCION = 160


def _necesidades_por_barrio(db: Session) -> dict[int, list[dict]]:
    """Las solicitudes abiertas de cada barrio, de la más a la menos prioritaria: qué piden, cuánto y lo que escribieron."""
    solicitudes = db.scalars(select(m.Solicitud).where(m.Solicitud.estado.in_(ABIERTAS))
                             .order_by(m.Solicitud.prioridad.desc().nulls_last(), m.Solicitud.id)).all()
    adjuntar_detalles(db, solicitudes)
    por_barrio: dict[int, list[dict]] = {}
    for s in solicitudes:
        lista = por_barrio.setdefault(s.barrio_id, [])
        if len(lista) < MAX_NECESIDADES_POR_BARRIO:
            texto = (s.descripcion or "").strip()
            lista.append({"id": s.id, "tipo": s.necesidad, "especifica": s.especifica, "cantidad": s.cantidad,
                          "unidad": UNIDADES.get(s.necesidad, "unidades"), "urgencia": s.urgencia, "estado": s.estado,
                          "descripcion": texto if len(texto) <= LARGO_DESCRIPCION else texto[:LARGO_DESCRIPCION - 1] + "…"})
    return por_barrio


@router.get("")
def mapa(request: Request, db: Db, usuario: Ve):
    return render(request, "mapa.html", usuario, alertas=pj.ALERTAS)


@router.get("/datos.json")
def datos(db: Db, usuario: Ve):
    """Un renglón por barrio con ubicación: lo justo para dibujarlo. Si todavía no se calculó nada, se calcula."""
    if db.scalar(select(func.count()).select_from(m.PuntajeBarrio)) == 0:
        refrescar(db)
    filas = db.execute(
        select(m.PuntajeBarrio, m.Barrio, m.Municipio.nombre)
        .join(m.Barrio, m.Barrio.id == m.PuntajeBarrio.barrio_id)
        .join(m.Municipio, m.Municipio.codigo == m.Barrio.municipio_codigo)
        .where(m.Barrio.lat.is_not(None), m.Barrio.lon.is_not(None))
        .order_by(m.PuntajeBarrio.posicion)).all()
    necesidades = _necesidades_por_barrio(db)
    barrios = [{
        "id": s.id, "nombre": s.nombre, "municipio": municipio, "codigo_municipio": s.municipio_codigo,
        "lat": round(s.lat, 5), "lon": round(s.lon, 5), "personas": s.personas,
        "prioridad": round(p.prioridad, 4), "posicion": p.posicion, "confianza": round(p.confianza, 4),
        "alertas": p.alertas or [], "n_reportes": p.n_reportes, "n_solicitudes": p.n_solicitudes,
        "base_previa": bool(p.base_previa), "necesidades": necesidades.get(s.id, []),
    } for p, s, municipio in filas]
    municipios = sorted({(x["codigo_municipio"], x["municipio"]) for x in barrios}, key=lambda t: t[1])
    calculado = max((p.calculado_en for p, _, _ in filas), default=None)
    return JSONResponse(
        {"barrios": barrios, "total": len(barrios), "alertas": pj.ALERTAS,
         "tipos": [{"clave": t.value, "nombre": t.name.replace("_", " ").capitalize(),
                    "unidad": UNIDADES.get(t.value, "unidades")} for t in m.TipoNecesidad],
         "municipios": [{"codigo": c, "nombre": n} for c, n in municipios],
         "calculado_en": calculado.isoformat() if calculado else None},
        headers={"Cache-Control": "no-store"})
