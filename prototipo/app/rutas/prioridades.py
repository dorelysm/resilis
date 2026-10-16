"""Prioridades de sectores y solicitudes, su explicación, y los pesos ajustables (bloque 5)."""
import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app import motor
from app import puntaje as pj
from app.db import get_db
from app.web import chequear_csrf, mensaje, mensaje_error, render, requiere_rol

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Ve = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.ENTIDAD, m.Rol.BRIGADISTA, m.Rol.ADMINISTRADOR))]
Decide = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.ENTIDAD, m.Rol.ADMINISTRADOR))]

log = logging.getLogger("resilis.puntaje")
NECESIDAD = {t.value: t.name.replace("_", " ").capitalize() for t in m.TipoNecesidad}
URGENCIA = {0: "Puede esperar", 1: "Pronto", 2: "Urgente", 3: "Riesgo para la vida"}
DANO = {0: "Sin daño", 1: "Daño leve", 2: "Daño moderado", 3: "Daño grave"}
ESTADO_REPORTE = {"verificado": "Verificado", "desmentido": "Desmentido"}


def refrescar(db: Session) -> None:
    """Recalcula las prioridades después de un cambio. Si falla, no deshace lo que la persona acaba de hacer."""
    try:
        pj.recalcular(db)
    except Exception:  # pragma: no cover - solo se registra
        db.rollback()
        log.exception("No se pudieron recalcular las prioridades")


def _pct(valor: float) -> str:
    return f"{round(valor * 100)} %"


@router.get("/prioridades")
def prioridades(request: Request, db: Db, usuario: Ve, todos: str = ""):
    if db.scalar(select(func.count()).select_from(m.PuntajeSector)) == 0:
        refrescar(db)
    limite = 1000 if todos == "si" else 25
    sectores = db.execute(
        select(m.PuntajeSector, m.Sector.nombre).join(m.Sector, m.Sector.id == m.PuntajeSector.sector_id)
        .order_by(m.PuntajeSector.posicion).limit(limite)).all()
    total_sectores = db.scalar(select(func.count()).select_from(m.PuntajeSector))
    con_alerta = sum(1 for a in db.scalars(select(m.PuntajeSector.alertas)) if a)
    solicitudes = db.execute(
        select(m.Solicitud, m.Sector.nombre).join(m.Sector, m.Sector.id == m.Solicitud.sector_id)
        .where(m.Solicitud.prioridad.is_not(None), m.Solicitud.estado.in_(["registrada", "verificada"]))
        .order_by(m.Solicitud.prioridad.desc()).limit(limite)).all()
    return render(request, "prioridades.html", usuario, sectores=sectores, solicitudes=solicitudes,
                  total_sectores=total_sectores, con_alerta=con_alerta, alertas=pj.ALERTAS, necesidad=NECESIDAD,
                  urgencia=URGENCIA, pct=_pct, todos=todos == "si", puede_pesos=usuario.rol != m.Rol.BRIGADISTA)


@router.post("/prioridades/recalcular")
def recalcular(request: Request, db: Db, usuario: Ve, csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    pj.recalcular(db)
    mensaje(request, "Las prioridades se recalcularon con los datos de ahora.")
    return RedirectResponse("/prioridades", status_code=303)


@router.get("/prioridades/sectores/{sector_id}")
def detalle_sector(sector_id: int, request: Request, db: Db, usuario: Ve):
    fila = db.execute(
        select(m.PuntajeSector, m.Sector).join(m.Sector, m.Sector.id == m.PuntajeSector.sector_id)
        .where(m.PuntajeSector.sector_id == sector_id)).first()
    if fila is None:
        raise HTTPException(status_code=404)
    p, sector = fila
    total = db.scalar(select(func.count()).select_from(m.PuntajeSector))
    reportes = db.execute(
        select(m.ReporteDanos, m.Usuario.rol).outerjoin(m.Usuario, m.Usuario.id == m.ReporteDanos.autor_id)
        .where(m.ReporteDanos.sector_id == sector_id, m.ReporteDanos.estado == "activo")
        .order_by(m.ReporteDanos.hora_captura.desc()).limit(30)).all()
    revision = {}
    for v in db.scalars(select(m.Verificacion).where(m.Verificacion.objeto_tipo == "reporte",
                                                     m.Verificacion.objeto_id.in_([r.id for r, _ in reportes]))):
        revision[v.objeto_id] = v.resultado
    solicitudes = db.scalars(select(m.Solicitud).where(
        m.Solicitud.sector_id == sector_id, m.Solicitud.estado.in_(["registrada", "verificada", "asignada", "en_camino"]))
        .order_by(m.Solicitud.prioridad.desc().nulls_last()).limit(30)).all()
    ranking = sorted(((p.aportes or {}).items()), key=lambda kv: -kv[1])
    pesos = pj.leer_pesos(db)["sector"]
    return render(request, "sector_detalle.html", usuario, p=p, sector=sector, total=total, reportes=reportes,
                  revision=revision, solicitudes=solicitudes, ranking=ranking, pesos=pesos, etiquetas=motor.ETIQUETAS,
                  alertas=pj.ALERTAS, dano=DANO, necesidad=NECESIDAD, urgencia=URGENCIA, pct=_pct,
                  puede_pesos=usuario.rol != m.Rol.BRIGADISTA)


# ----------------------------------------------------------------------------- pesos
def _contexto_pesos(db: Session, errores=None, datos=None):
    vigentes = pj.leer_pesos(db)
    return dict(
        grupos=[("sector", "Cómo se ordenan los sectores", motor.CRITERIOS_SECTOR, vigentes["sector"]),
                ("solicitud", "Cómo se ordenan las solicitudes", motor.CRITERIOS_SOLICITUD, vigentes["solicitud"])],
        etiquetas=motor.ETIQUETAS, errores=errores or {}, datos=datos or {})


@router.get("/pesos")
def pesos(request: Request, db: Db, usuario: Decide):
    return render(request, "pesos.html", usuario, **_contexto_pesos(db))


@router.post("/pesos/{ambito}")
async def guardar_pesos(ambito: str, request: Request, db: Db, usuario: Decide):
    if ambito not in ("sector", "solicitud"):
        raise HTTPException(status_code=404)
    form = await request.form()
    chequear_csrf(request, str(form.get("csrf", "")))
    criterios = motor.CRITERIOS_SECTOR if ambito == "sector" else motor.CRITERIOS_SOLICITUD
    valores, errores = {}, {}
    for c in criterios:
        crudo = str(form.get(f"{ambito}_{c}", "")).strip().replace(",", ".")
        try:
            numero = float(crudo)
        except ValueError:
            errores[f"{ambito}_{c}"] = "Escriba un número."
            continue
        if not 0 <= numero <= 100:
            errores[f"{ambito}_{c}"] = "Escriba un número entre 0 y 100."
        valores[c] = numero
    if not errores and sum(valores.values()) <= 0:
        errores[f"{ambito}_{criterios[0]}"] = "Al menos un peso debe ser mayor que cero."
    if errores:
        datos = {k: str(v) for k, v in form.items()}
        return render(request, "pesos.html", usuario, estado=422, **_contexto_pesos(db, errores, datos))
    pj.guardar_pesos(db, ambito, valores, usuario)
    db.commit()
    pj.recalcular(db)
    mensaje(request, "Los pesos se guardaron y las prioridades se recalcularon.")
    return RedirectResponse("/pesos", status_code=303)
