"""Prioridades de barrios y solicitudes, su explicación, y los pesos ajustables (bloque 5)."""
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


def _resumen_municipios(db: Session) -> list[dict]:
    """Un renglón por municipio: cuántos barrios tiene, qué tan alta es su prioridad y cuánto falta por atender."""
    pendientes = dict(db.execute(
        select(m.Barrio.municipio_codigo, func.count(m.Solicitud.id)).join(m.Barrio, m.Barrio.id == m.Solicitud.barrio_id)
        .where(m.Solicitud.estado.in_(["registrada", "verificada"])).group_by(m.Barrio.municipio_codigo)).all())
    por_municipio: dict[str, dict] = {}
    for p, codigo, nombre in db.execute(
            select(m.PuntajeBarrio, m.Barrio.municipio_codigo, m.Municipio.nombre)
            .join(m.Barrio, m.Barrio.id == m.PuntajeBarrio.barrio_id)
            .join(m.Municipio, m.Municipio.codigo == m.Barrio.municipio_codigo)).all():
        r = por_municipio.setdefault(codigo, {"codigo": codigo, "nombre": nombre, "barrios": 0, "suma": 0.0,
                                              "maxima": 0.0, "con_alerta": 0, "pendientes": pendientes.get(codigo, 0)})
        r["barrios"] += 1
        r["suma"] += p.prioridad
        r["maxima"] = max(r["maxima"], p.prioridad)
        r["con_alerta"] += 1 if p.alertas else 0
    filas = list(por_municipio.values())
    for r in filas:
        r["promedio"] = r["suma"] / r["barrios"]
    return sorted(filas, key=lambda r: -r["maxima"])


@router.get("/prioridades")
def prioridades(request: Request, db: Db, usuario: Ve, todos: str = "", municipio: str = ""):
    if db.scalar(select(func.count()).select_from(m.PuntajeBarrio)) == 0:
        refrescar(db)
    limite = 1000 if todos == "si" else 25
    municipios = _resumen_municipios(db)
    elegido = municipio if any(r["codigo"] == municipio for r in municipios) else ""
    filtro_b = [m.Barrio.municipio_codigo == elegido] if elegido else []
    barrios = db.execute(
        select(m.PuntajeBarrio, m.Barrio.nombre, m.Municipio.nombre)
        .join(m.Barrio, m.Barrio.id == m.PuntajeBarrio.barrio_id)
        .join(m.Municipio, m.Municipio.codigo == m.Barrio.municipio_codigo).where(*filtro_b)
        .order_by(m.PuntajeBarrio.posicion).limit(limite)).all()
    total_barrios = db.scalar(select(func.count()).select_from(m.PuntajeBarrio))
    con_alerta = sum(1 for a in db.scalars(select(m.PuntajeBarrio.alertas)) if a)
    solicitudes = db.execute(
        select(m.Solicitud, m.Barrio.nombre, m.Municipio.nombre).join(m.Barrio, m.Barrio.id == m.Solicitud.barrio_id)
        .join(m.Municipio, m.Municipio.codigo == m.Barrio.municipio_codigo)
        .where(m.Solicitud.prioridad.is_not(None), m.Solicitud.estado.in_(["registrada", "verificada"]), *filtro_b)
        .order_by(m.Solicitud.prioridad.desc()).limit(limite)).all()
    return render(request, "prioridades.html", usuario, barrios=barrios, solicitudes=solicitudes,
                  municipios=municipios, elegido=elegido, total_barrios=total_barrios, con_alerta=con_alerta,
                  alertas=pj.ALERTAS, necesidad=NECESIDAD, urgencia=URGENCIA, pct=_pct, todos=todos == "si",
                  puede_pesos=usuario.rol != m.Rol.BRIGADISTA)


@router.post("/prioridades/recalcular")
def recalcular(request: Request, db: Db, usuario: Ve, csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    pj.recalcular(db)
    mensaje(request, "Las prioridades se recalcularon con los datos de ahora.")
    return RedirectResponse("/prioridades", status_code=303)


@router.get("/prioridades/barrios/{barrio_id}")
def detalle_barrio(barrio_id: int, request: Request, db: Db, usuario: Ve):
    fila = db.execute(
        select(m.PuntajeBarrio, m.Barrio).join(m.Barrio, m.Barrio.id == m.PuntajeBarrio.barrio_id)
        .where(m.PuntajeBarrio.barrio_id == barrio_id)).first()
    if fila is None:
        raise HTTPException(status_code=404)
    p, barrio = fila
    total = db.scalar(select(func.count()).select_from(m.PuntajeBarrio))
    reportes = db.execute(
        select(m.ReporteDanos, m.Usuario.rol).outerjoin(m.Usuario, m.Usuario.id == m.ReporteDanos.autor_id)
        .where(m.ReporteDanos.barrio_id == barrio_id, m.ReporteDanos.estado == "activo")
        .order_by(m.ReporteDanos.hora_captura.desc()).limit(30)).all()
    revision = {}
    for v in db.scalars(select(m.Verificacion).where(m.Verificacion.objeto_tipo == "reporte",
                                                     m.Verificacion.objeto_id.in_([r.id for r, _ in reportes]))):
        revision[v.objeto_id] = v.resultado
    solicitudes = db.scalars(select(m.Solicitud).where(
        m.Solicitud.barrio_id == barrio_id, m.Solicitud.estado.in_(["registrada", "verificada", "asignada", "en_camino"]))
        .order_by(m.Solicitud.prioridad.desc().nulls_last()).limit(30)).all()
    ranking = sorted(((p.aportes or {}).items()), key=lambda kv: -kv[1])
    pesos = pj.leer_pesos(db)["barrio"]
    return render(request, "barrio_detalle.html", usuario, p=p, barrio=barrio, total=total, reportes=reportes,
                  revision=revision, solicitudes=solicitudes, ranking=ranking, pesos=pesos, etiquetas=motor.ETIQUETAS,
                  alertas=pj.ALERTAS, dano=DANO, necesidad=NECESIDAD, urgencia=URGENCIA, pct=_pct,
                  puede_pesos=usuario.rol != m.Rol.BRIGADISTA)


# ----------------------------------------------------------------------------- pesos
def _contexto_pesos(db: Session, errores=None, datos=None):
    vigentes = pj.leer_pesos(db)
    return dict(
        grupos=[("barrio", "Cómo se ordenan los barrios", motor.CRITERIOS_BARRIO, vigentes["barrio"]),
                ("solicitud", "Cómo se ordenan las solicitudes", motor.CRITERIOS_SOLICITUD, vigentes["solicitud"])],
        etiquetas=motor.ETIQUETAS, errores=errores or {}, datos=datos or {})


@router.get("/pesos")
def pesos(request: Request, db: Db, usuario: Decide):
    return render(request, "pesos.html", usuario, **_contexto_pesos(db))


@router.post("/pesos/{ambito}")
async def guardar_pesos(ambito: str, request: Request, db: Db, usuario: Decide):
    if ambito not in ("barrio", "solicitud"):
        raise HTTPException(status_code=404)
    form = await request.form()
    chequear_csrf(request, str(form.get("csrf", "")))
    criterios = motor.CRITERIOS_BARRIO if ambito == "barrio" else motor.CRITERIOS_SOLICITUD
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
