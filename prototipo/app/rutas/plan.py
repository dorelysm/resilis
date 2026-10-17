"""Plan de asignación optimizado: calcularlo, ver por qué, y aprobarlo o rechazarlo (bloque 6). Solo la entidad."""
from collections import defaultdict
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app import plan as pl
from app.solicitud_info import adjuntar_detalles
from app import servicios as sv
from app.config import get_settings
from app.formato import plural
from app.simulacion import UNIDADES
from app.db import get_db
from app.rutas.prioridades import refrescar
from app.web import chequear_csrf, mensaje, mensaje_error, render, requiere_rol

router = APIRouter(prefix="/plan")
Db = Annotated[Session, Depends(get_db)]
Entidad = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.ENTIDAD))]

NECESIDAD = {t.value: t.name.replace("_", " ").capitalize() for t in m.TipoNecesidad}
URGENCIA = {0: "Puede esperar", 1: "Pronto", 2: "Urgente", 3: "Riesgo para la vida"}
UNIDAD = dict(UNIDADES)
ESTADOS = {"propuesto": "Propuesto", "aprobado": "Aprobado", "rechazado": "Rechazado"}
LIMITES = {"theta": (0.0, 1.0, "La fracción mínima debe estar entre 0 y 1."),
           "kappa": (0.0, 1.0, "El peso del vencimiento debe estar entre 0 y 1."),
           "lambda": (0.0, 0.1, "El costo por kilómetro debe estar entre 0 y 0,1.")}


def _equipos(db: Session) -> list[tuple[int, str]]:
    return [(u.id, u.nombre) for u in db.scalars(select(m.Usuario).where(
        m.Usuario.rol == m.Rol.EQUIPO_ENTREGA, m.Usuario.aprobado.is_(True), m.Usuario.password_hash.is_not(None))
        .order_by(m.Usuario.nombre))]


MAX_GRUPOS = 40  # cuántas solicitudes se detallan en pantalla; el resto se aprueba con el equipo propuesto


PAQUETES_ABIERTOS = 1  # cuántos paquetes se muestran abiertos para revisar; el resto, en una lista corta


def _paquetes_vista(db: Session, plan: m.PlanAsignacion | None) -> dict | None:
    """Los paquetes pendientes, cada uno con lo mínimo para decidir: qué, dónde, para cuántas personas."""
    if plan is None or not db.scalar(select(func.count()).select_from(m.PlanLinea).where(m.PlanLinea.plan_id == plan.id)):
        return None
    todos = pl.armar_paquetes(db, plan)
    barrios = {b.id: b for b in db.scalars(select(m.Barrio))}
    lineas = pl._lineas_por_solicitud(db, plan)
    datos = (db.get(m.PlanResumen, plan.id).datos if db.get(m.PlanResumen, plan.id) else {})
    for p in todos:
        filas = []
        for sol_id in p["solicitudes"]:
            sol = db.get(m.Solicitud, sol_id)
            barrio = barrios.get(sol.barrio_id)
            filas.append({"sol": sol, "barrio": barrio.etiqueta if barrio else "",
                          "asignado": sum(l.cantidad for l in lineas[sol_id]), "aislado": sol_id in datos.get("acceso_bloqueado", [])})
        p["filas"] = filas
        p["unidades"] = sum(f["asignado"] for f in filas)
    adjuntar_detalles(db, [f["sol"] for p in todos for f in p["filas"]])
    pendientes = [p for p in todos if not p["resuelto"]]
    return {"todos": todos, "pendientes": pendientes, "abiertos": pendientes[:PAQUETES_ABIERTOS],
            "siguientes": pendientes[PAQUETES_ABIERTOS:PAQUETES_ABIERTOS + 12],
            "mas": max(0, len(pendientes) - PAQUETES_ABIERTOS - 12), "hechos": len(todos) - len(pendientes),
            "equipo_sugerido": pl.equipo_sugerido(db)}


def _vista(db: Session, plan: m.PlanAsignacion | None, todos: bool = False):
    """Todo lo que la página necesita saber de un plan, ya ordenado y con nombres."""
    if plan is None:
        return None
    resumen = db.get(m.PlanResumen, plan.id)
    datos = resumen.datos if resumen else {}
    por_sol: dict[int, list[m.PlanLinea]] = defaultdict(list)
    for l in db.scalars(select(m.PlanLinea).where(m.PlanLinea.plan_id == plan.id).order_by(m.PlanLinea.id)):
        por_sol[l.solicitud_id].append(l)
    grupos = []
    for sol_id, ls in por_sol.items():
        sol = db.get(m.Solicitud, sol_id)
        barrio = db.get(m.Barrio, sol.barrio_id)
        grupos.append({"sol": sol, "barrio": barrio.etiqueta if barrio else "", "lineas": ls,
                       "asignado": sum(l.cantidad for l in ls), "equipo_id": ls[0].equipo_id,
                       "aislado": sol_id in datos.get("acceso_bloqueado", [])})
    grupos.sort(key=lambda g: -(g["sol"].prioridad or 0))
    total_grupos = len(grupos)
    if not todos:
        grupos = grupos[:MAX_GRUPOS]
    sin = [{**s, "sol": db.get(m.Solicitud, s["solicitud_id"])} for s in datos.get("sin_cubrir", [])]
    adjuntar_detalles(db, [s["sol"] for s in sin])
    mejora = None
    base = datos.get("cubierta_ponderada_voraz") or 0.0
    if base > 0:
        mejora = round((datos.get("cubierta_ponderada", 0.0) / base - 1.0) * 100, 1)
    return {"plan": plan, "datos": datos, "paquetes": _paquetes_vista(db, plan), "grupos": grupos, "sin_cubrir": sin, "mejora": mejora,
            "total_grupos": total_grupos, "ocultos": total_grupos - len(grupos)}


def _redir() -> RedirectResponse:
    return RedirectResponse("/plan", status_code=303)


@router.get("")
def ver_plan(request: Request, db: Db, usuario: Entidad, todos: str = ""):
    recientes = db.scalars(select(m.PlanAsignacion).order_by(m.PlanAsignacion.id.desc()).limit(6)).all()
    verificadas = db.scalar(select(func.count()).select_from(m.Solicitud).where(
        m.Solicitud.estado == m.EstadoSolicitud.VERIFICADA))
    disponible = db.scalar(select(func.coalesce(func.sum(m.Lote.cantidad_disponible), 0)))
    return render(request, "plan.html", usuario, vista=_vista(db, recientes[0] if recientes else None, todos == "si"),
                  historial=recientes[1:], equipos=_equipos(db), parametros=pl.leer_parametros(db), estados=ESTADOS,
                  necesidad=NECESIDAD, urgencia=URGENCIA, unidad=UNIDAD, verificadas=verificadas, disponible=disponible,
                  errores={})


@router.post("/calcular")
async def calcular(request: Request, db: Db, usuario: Entidad):
    chequear_csrf(request, str((await request.form()).get("csrf", "")))
    plan = pl.calcular_plan(db, usuario)
    if plan is None:
        mensaje_error(request, "No hay nada que planear: hace falta al menos una solicitud verificada y inventario disponible.")
    else:
        mensaje(request, "El plan está listo. Revíselo antes de aprobarlo: hasta entonces no se reserva nada.")
    return _redir()


@router.post("/parametros")
async def parametros(request: Request, db: Db, usuario: Entidad):
    form = await request.form()
    chequear_csrf(request, str(form.get("csrf", "")))
    valores, errores = {}, {}
    for clave, (minimo, maximo, texto) in LIMITES.items():
        try:
            numero = float(str(form.get(clave, "")).strip().replace(",", "."))
        except ValueError:
            errores[clave] = "Escriba un número."
            continue
        if not minimo <= numero <= maximo:
            errores[clave] = texto
        valores[clave] = numero
    if errores:
        recientes = db.scalars(select(m.PlanAsignacion).order_by(m.PlanAsignacion.id.desc()).limit(6)).all()
        return render(request, "plan.html", usuario, estado=422, vista=_vista(db, recientes[0] if recientes else None),
                      historial=recientes[1:], equipos=_equipos(db), parametros={**pl.leer_parametros(db), **valores},
                      estados=ESTADOS, necesidad=NECESIDAD, urgencia=URGENCIA, unidad=UNIDAD, errores=errores,
                      verificadas=None, disponible=None)
    pl.guardar_parametros(db, valores, usuario)
    db.commit()
    mensaje(request, "Los parámetros se guardaron. Calcule el plan de nuevo para que se apliquen.")
    return _redir()


def _plan(db: Session, plan_id: int) -> m.PlanAsignacion:
    plan = db.get(m.PlanAsignacion, plan_id)
    if plan is None:
        raise HTTPException(status_code=404)
    return plan


@router.post("/{plan_id}/aprobar")
async def aprobar(plan_id: int, request: Request, db: Db, usuario: Entidad):
    form = await request.form()
    chequear_csrf(request, str(form.get("csrf", "")))
    plan = _plan(db, plan_id)
    todas = {l.solicitud_id for l in db.scalars(select(m.PlanLinea).where(m.PlanLinea.plan_id == plan.id))}
    excluidas = {sid for sid in todas if form.get(f"excluir_{sid}")}  # solo las que la entidad marcó
    equipos = {}
    for sid in todas:
        crudo = str(form.get(f"equipo_{sid}", "")).strip()
        if crudo.isdigit():
            equipos[sid] = int(crudo)
    try:
        r = pl.aprobar_plan(db, plan, usuario, get_settings().secret_key, equipos, excluidas)
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
        return _redir()
    refrescar(db)
    texto = f"Plan aprobado: {plural(r['asignadas'], 'solicitud asignada', 'solicitudes asignadas')}, cada una con su código de entrega."
    if r["omitidas"]:
        texto += f" {len(r['omitidas'])} no se pudieron asignar porque el inventario cambió."
    if r["excluidas"]:
        texto += f" {r['excluidas']} quedaron fuera por decisión suya."
    mensaje(request, texto)
    return _redir()


@router.post("/{plan_id}/paquete")
async def aprobar_un_paquete(plan_id: int, request: Request, db: Db, usuario: Entidad):
    form = await request.form()
    chequear_csrf(request, str(form.get("csrf", "")))
    plan = _plan(db, plan_id)
    ids = [int(x) for x in str(form.get("solicitudes", "")).split(",") if x.strip().isdigit()]
    equipo = str(form.get("equipo", "")).strip()
    if not equipo.isdigit() or db.get(m.Usuario, int(equipo)) is None:
        mensaje_error(request, "Elija el equipo de entrega de este paquete.")
        return _redir()
    excluidas = {j for j in ids if form.get(f"excluir_{j}")}
    try:
        r = pl.aprobar_paquete(db, plan, usuario, get_settings().secret_key, ids, int(equipo), excluidas)
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
        return _redir()
    refrescar(db)
    texto = f"Paquete aprobado: {plural(r['asignadas'], 'entrega asignada', 'entregas asignadas')}, cada una con su código."
    if r["omitidas"]:
        texto += f" {len(r['omitidas'])} no se pudieron asignar porque el inventario cambió."
    if r["excluidas"]:
        texto += f" {r['excluidas']} quedaron fuera por decisión suya."
    mensaje(request, texto)
    return _redir()


@router.post("/{plan_id}/rechazar")
async def rechazar(plan_id: int, request: Request, db: Db, usuario: Entidad):
    form = await request.form()
    chequear_csrf(request, str(form.get("csrf", "")))
    try:
        pl.rechazar_plan(db, _plan(db, plan_id), usuario, str(form.get("motivo", "")))
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
    else:
        mensaje(request, "El plan se rechazó. No se reservó nada.")
    return _redir()
