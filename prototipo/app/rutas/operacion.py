"""Operación de la respuesta: verificación, recepción e inventario, asignación, entregas y seguimiento (bloque 4)."""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app import recorrido as rc
from app import servicios as sv
from app.config import get_settings
from app.db import get_db
from app.rutas.prioridades import refrescar
from app.web import chequear_csrf, entero, mensaje, mensaje_error, render, requiere_rol

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]
Verificador = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.BRIGADISTA, m.Rol.ENTIDAD))]
Entidad = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.ENTIDAD))]
Equipo = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.EQUIPO_ENTREGA))]
Acopio = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.CENTRO_ACOPIO))]
Solicitante = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.SOLICITANTE))]
VeInventario = Annotated[m.Usuario, Depends(requiere_rol(m.Rol.CENTRO_ACOPIO, m.Rol.ENTIDAD))]

NECESIDAD = {t.value: t.name.replace("_", " ").capitalize() for t in m.TipoNecesidad}
URGENCIA = {0: "Puede esperar", 1: "Pronto", 2: "Urgente", 3: "Riesgo para la vida"}
DANO = {0: "Sin daño", 1: "Daño leve", 2: "Daño moderado", 3: "Daño grave"}
TIPO_VULNERABILIDAD = {"discapacidad": "Persona con discapacidad", "adulto_mayor": "Adulto mayor",
                       "menor": "Niño o niña pequeño", "embarazo": "Embarazo", "cronica": "Enfermedad crónica",
                       "otra": "Otra situación"}
ESTADO = {"registrada": "Registrada", "verificada": "Verificada", "asignada": "Asignada", "en_camino": "En camino",
          "entregada": "Entregada", "cerrada": "Cerrada", "anulada": "Anulada"}
HITOS = {"verificada": "Verificaron su solicitud", "desmentida": "No se pudo verificar su solicitud",
         "asignada": "Se asignó un equipo para entregarle la ayuda", "en_camino": "El equipo va en camino",
         "entregada": "El equipo registró la entrega", "cerrada": "Usted confirmó que recibió la ayuda",
         "entrega_parcial": "Recibió una parte de la ayuda; el resto se entregará cuando haya inventario",
         "incidencia": "La entrega no se pudo hacer; se asignará de nuevo"}


def _redir(url: str) -> RedirectResponse:
    return RedirectResponse(url, status_code=303)


def _como_utc(hora: datetime | None) -> datetime | None:
    return hora.replace(tzinfo=timezone.utc) if hora is not None and hora.tzinfo is None else hora


# ----------------------------------------------------------------------------- verificación
def _solicitudes_a_verificar(db: Session, usuario: m.Usuario):
    q = (select(m.Solicitud, m.Usuario.nombre, m.Barrio.etiqueta)
         .join(m.Usuario, m.Usuario.id == m.Solicitud.solicitante_id)
         .join(m.Barrio, m.Barrio.id == m.Solicitud.barrio_id)
         .where(m.Solicitud.estado == m.EstadoSolicitud.REGISTRADA)
         .order_by(m.Solicitud.urgencia.desc(), m.Solicitud.creado_en).limit(100))
    if usuario.rol == m.Rol.BRIGADISTA and usuario.barrio_id:  # un brigadista revisa lo de su zona de trabajo
        zona = db.get(m.Barrio, usuario.barrio_id)
        q = q.where(m.Barrio.municipio_codigo == zona.municipio_codigo)
    return db.execute(q).all()


@router.get("/verificacion")
def verificacion(request: Request, db: Db, usuario: Verificador):
    reportes = db.execute(
        select(m.ReporteDanos, m.Barrio.etiqueta).join(m.Barrio, m.Barrio.id == m.ReporteDanos.barrio_id)
        .where(~select(m.Verificacion.id).where(m.Verificacion.objeto_tipo == "reporte",
                                                m.Verificacion.objeto_id == m.ReporteDanos.id).exists(),
               m.ReporteDanos.estado == "activo")
        .order_by(m.ReporteDanos.hora_captura.desc()).limit(50)).all()
    return render(request, "verificacion.html", usuario, solicitudes=_solicitudes_a_verificar(db, usuario),
                  reportes=reportes, necesidad=NECESIDAD, urgencia=URGENCIA, dano=DANO)


def _detalle_solicitud(db: Session, sol_id: int):
    fila = db.execute(
        select(m.Solicitud, m.Usuario, m.Barrio).join(m.Usuario, m.Usuario.id == m.Solicitud.solicitante_id)
        .join(m.Barrio, m.Barrio.id == m.Solicitud.barrio_id).where(m.Solicitud.id == sol_id)).first()
    if fila is None:
        raise HTTPException(status_code=404)
    return fila


@router.get("/verificacion/solicitudes/{sol_id}")
def verificar_solicitud_form(sol_id: int, request: Request, db: Db, usuario: Verificador):
    sol, persona, barrio = _detalle_solicitud(db, sol_id)
    vuln = db.scalar(select(m.Vulnerabilidad).where(m.Vulnerabilidad.solicitud_id == sol.id))
    return render(request, "verificar_solicitud.html", usuario, sol=sol, persona=persona, barrio=barrio, vuln=vuln,
                  necesidad=NECESIDAD, urgencia=URGENCIA, tipo_vuln=TIPO_VULNERABILIDAD)


@router.post("/verificacion/solicitudes/{sol_id}")
def verificar_solicitud(sol_id: int, request: Request, db: Db, usuario: Verificador,
                        resultado: Annotated[str, Form()] = "", nota: Annotated[str, Form()] = "",
                        csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    sol, *_ = _detalle_solicitud(db, sol_id)
    try:
        sv.verificar_solicitud(db, sol, usuario, resultado, nota)
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
        return _redir(f"/verificacion/solicitudes/{sol_id}")
    refrescar(db)
    mensaje(request, "Solicitud verificada." if resultado == "verificado" else "Solicitud desmentida.")
    return _redir("/verificacion")


@router.post("/verificacion/reportes/{rep_id}")
def verificar_reporte(rep_id: int, request: Request, db: Db, usuario: Verificador,
                      resultado: Annotated[str, Form()] = "", nota: Annotated[str, Form()] = "",
                      csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    rep = db.get(m.ReporteDanos, rep_id)
    if rep is None:
        raise HTTPException(status_code=404)
    try:
        sv.verificar_reporte(db, rep, usuario, resultado, nota)
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
    else:
        refrescar(db)
        mensaje(request, "Reporte revisado.")
    return _redir("/verificacion")


# ----------------------------------------------------------------------------- recepción e inventario
def _centro_de(db: Session, usuario: m.Usuario) -> m.CentroAcopio | None:
    return db.scalar(select(m.CentroAcopio).where(m.CentroAcopio.responsable_id == usuario.id))


@router.get("/recepcion")
def recepcion(request: Request, db: Db, usuario: Acopio):
    centro = _centro_de(db, usuario)
    pendientes = []
    if centro:
        pendientes = db.execute(
            select(m.Donacion, m.Donante).join(m.Donante, m.Donante.id == m.Donacion.donante_id)
            .where(m.Donacion.estado == m.EstadoDonacion.OFRECIDA,
                   (m.Donacion.centro_id == centro.id) | (m.Donacion.centro_id.is_(None)))
            .order_by(m.Donacion.creado_en).limit(100)).all()
    return render(request, "recepcion.html", usuario, centro=centro, pendientes=pendientes, tipos=NECESIDAD)


@router.post("/recepcion/{don_id}")
def recibir(don_id: int, request: Request, db: Db, usuario: Acopio, cantidad: Annotated[str, Form()] = "",
            estado_producto: Annotated[str, Form()] = "nuevo", vencimiento: Annotated[str, Form()] = "",
            csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    centro, don = _centro_de(db, usuario), db.get(m.Donacion, don_id)
    if centro is None or don is None:
        raise HTTPException(status_code=404)
    venc = None
    if vencimiento:
        try:
            venc = datetime.fromisoformat(vencimiento).replace(tzinfo=timezone.utc)
        except ValueError:
            mensaje_error(request, "Escriba una fecha de vencimiento válida.")
            return _redir("/recepcion")
    try:
        sv.recibir_donacion(db, don, centro, usuario, entero(cantidad, 0, 10**7, 0), estado_producto, venc)
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
    else:
        refrescar(db)
        mensaje(request, "La donación quedó recibida en su inventario.")
    return _redir("/recepcion")


@router.get("/inventario")
def inventario(request: Request, db: Db, usuario: VeInventario):
    q = (select(m.Lote, m.CentroAcopio.nombre).join(m.CentroAcopio, m.CentroAcopio.id == m.Lote.centro_id)
         .order_by(m.Lote.tipo_bien, m.Lote.vencimiento.is_(None), m.Lote.vencimiento))
    centro = None
    if usuario.rol == m.Rol.CENTRO_ACOPIO:
        centro = _centro_de(db, usuario)
        q = q.where(m.Lote.centro_id == (centro.id if centro else -1))
    filas = db.execute(q.limit(300)).all()
    totales: dict[str, dict[str, int]] = {}
    for lote, _ in filas:
        t = totales.setdefault(lote.tipo_bien, {"disponible": 0, "reservada": 0, "entregada": 0})
        t["disponible"] += lote.cantidad_disponible
        t["reservada"] += lote.cantidad_reservada
        t["entregada"] += lote.cantidad_entregada
    return render(request, "inventario.html", usuario, filas=filas, totales=totales, tipos=NECESIDAD, centro=centro,
                  hoy=datetime.now(timezone.utc))


# ----------------------------------------------------------------------------- asignación
@router.get("/asignacion")
def asignacion(request: Request, db: Db, usuario: Entidad):
    verificadas = db.execute(
        select(m.Solicitud, m.Barrio.etiqueta).join(m.Barrio, m.Barrio.id == m.Solicitud.barrio_id)
        .where(m.Solicitud.estado == m.EstadoSolicitud.VERIFICADA)  # la prioridad la calcula el bloque 5
        .order_by(m.Solicitud.prioridad.desc().nulls_last(), m.Solicitud.urgencia.desc(), m.Solicitud.creado_en)
        .limit(100)).all()
    filas = [(sol, barrio, sv.disponible_para(db, sol)) for sol, barrio in verificadas]
    equipos = [(u.id, u.nombre) for u in db.scalars(select(m.Usuario).where(
        m.Usuario.rol == m.Rol.EQUIPO_ENTREGA, m.Usuario.aprobado.is_(True), m.Usuario.password_hash.is_not(None)))]
    en_curso = db.execute(
        select(m.Entrega, m.Usuario.nombre).join(m.Usuario, m.Usuario.id == m.Entrega.equipo_id)
        .where(m.Entrega.estado.in_(["asignada", "en_camino"]), m.Entrega.estado_codigo == "activo")
        .order_by(m.Entrega.creado_en.desc()).limit(50)).all()
    return render(request, "asignacion.html", usuario, filas=filas, equipos=equipos, en_curso=en_curso,
                  necesidad=NECESIDAD, urgencia=URGENCIA)


@router.post("/asignacion/{sol_id}")
def asignar(sol_id: int, request: Request, db: Db, usuario: Entidad, equipo_id: Annotated[str, Form()] = "",
            csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    sol = db.get(m.Solicitud, sol_id)
    equipo = db.get(m.Usuario, entero(equipo_id, 1, 10**9, 0) or 0)
    if sol is None:
        raise HTTPException(status_code=404)
    if equipo is None:
        mensaje_error(request, "Elija un equipo de entrega.")
        return _redir("/asignacion")
    try:
        sv.asignar(db, sol, equipo, usuario, get_settings().secret_key)
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
    else:
        refrescar(db)
        mensaje(request, f"Solicitud asignada a {equipo.nombre}.")
    return _redir("/asignacion")


# ----------------------------------------------------------------------------- entregas (equipo)
def _mis_entregas(db: Session, equipo: m.Usuario):
    return db.execute(
        select(m.Entrega, m.Solicitud, m.Usuario, m.Barrio)
        .join(m.Solicitud, m.Solicitud.id == m.Entrega.solicitud_id)
        .join(m.Usuario, m.Usuario.id == m.Solicitud.solicitante_id)
        .join(m.Barrio, m.Barrio.id == m.Solicitud.barrio_id)
        .where(m.Entrega.equipo_id == equipo.id, m.Entrega.estado.in_(["asignada", "en_camino"]),
               m.Entrega.estado_codigo == "activo").order_by(m.Entrega.vence_en)).all()


@router.get("/entregas")
def entregas(request: Request, db: Db, usuario: Equipo):
    filas = []
    for e, sol, persona, barrio in _mis_entregas(db, usuario):
        vuln = db.scalar(select(m.Vulnerabilidad).where(m.Vulnerabilidad.solicitud_id == sol.id))
        filas.append((e, sol, persona, barrio, vuln))
    return render(request, "entregas.html", usuario, filas=filas, necesidad=NECESIDAD, urgencia=URGENCIA,
                  tipo_vuln=TIPO_VULNERABILIDAD)


@router.get("/entregas/datos.json")
def entregas_datos(db: Db, usuario: Equipo):
    """Lo mínimo que el dispositivo necesita para validar códigos sin conexión: la sal y la huella de cada código."""
    return JSONResponse(
        {"entregas": [{"id": e.id, "sal": e.codigo_sal, "huella": e.codigo_hash,
                       "vence": _como_utc(e.vence_en).isoformat() if e.vence_en else None}
                      for e, *_ in _mis_entregas(db, usuario)]},
        headers={"Cache-Control": "no-store"})


def _entrega_propia(db: Session, entrega_id: int, usuario: m.Usuario) -> m.Entrega:
    e = db.get(m.Entrega, entrega_id)
    if e is None or e.equipo_id != usuario.id:
        raise HTTPException(status_code=404)
    return e


@router.post("/entregas/{entrega_id}/en-camino")
def entrega_en_camino(entrega_id: int, request: Request, db: Db, usuario: Equipo, csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    try:
        sv.en_camino(db, _entrega_propia(db, entrega_id, usuario), usuario)
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
    else:
        mensaje(request, "Marcada como en camino. La persona ya lo puede ver.")
    return _redir("/entregas")


@router.post("/entregas/{entrega_id}/confirmar")
def entrega_confirmar(entrega_id: int, request: Request, db: Db, usuario: Equipo,
                      codigo: Annotated[str, Form()] = "", csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    try:
        sv.confirmar_entrega(db, _entrega_propia(db, entrega_id, usuario), usuario, codigo)
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
    else:
        refrescar(db)
        mensaje(request, "Entrega confirmada. Gracias.")
    return _redir("/entregas")


@router.post("/entregas/{entrega_id}/incidencia")
def entrega_incidencia(entrega_id: int, request: Request, db: Db, usuario: Equipo, tipo: Annotated[str, Form()] = "",
                       nota: Annotated[str, Form()] = "", csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    try:
        sv.registrar_incidencia(db, _entrega_propia(db, entrega_id, usuario), usuario, tipo, nota)
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
    else:
        refrescar(db)
        mensaje(request, "Incidencia registrada. La entidad volverá a asignar la solicitud.")
    return _redir("/entregas")


@router.post("/entregas/sincronizar")
async def entregas_sincronizar(request: Request, db: Db, usuario: Equipo):
    """Recibe las entregas confirmadas sin conexión. El servidor vuelve a validar cada código."""
    if not request.session.get("csrf") or request.headers.get("x-csrf-token") != request.session["csrf"]:
        raise HTTPException(status_code=403, detail="La página caducó. Vuelva a cargarla.")
    try:
        cuerpo = await request.json()
        pendientes = cuerpo["entregas"]
        assert isinstance(pendientes, list) and len(pendientes) <= 100
    except Exception:
        raise HTTPException(status_code=400, detail="Datos no válidos.")
    resultados = []
    for p in pendientes:
        eid = p.get("id") if isinstance(p, dict) else None
        entrega = db.get(m.Entrega, eid) if isinstance(eid, int) else None
        if entrega is None or entrega.equipo_id != usuario.id:
            resultados.append({"id": eid, "ok": False, "mensaje": "Esta entrega no es de su equipo."})
            continue
        try:
            repetida = sv.confirmar_entrega(db, entrega, usuario, str(p.get("codigo", "")))
            resultados.append({"id": eid, "ok": True, "repetida": repetida})
        except sv.ErrorNegocio as e:
            resultados.append({"id": eid, "ok": False, "mensaje": str(e)})
    if any(r["ok"] and not r.get("repetida") for r in resultados):
        refrescar(db)
    return JSONResponse({"resultados": resultados}, headers={"Cache-Control": "no-store"})


# ----------------------------------------------------------------------------- seguimiento (solicitante)
def _solicitud_propia(db: Session, sol_id: int, usuario: m.Usuario) -> m.Solicitud:
    sol = db.get(m.Solicitud, sol_id)
    if sol is None or sol.solicitante_id != usuario.id:
        raise HTTPException(status_code=404)
    return sol


def _contexto_seguimiento(db: Session, sol: m.Solicitud):
    hitos = [(sol.creado_en, "Registró su solicitud")]
    for ev in db.scalars(select(m.EventoAuditoria).where(m.EventoAuditoria.solicitud_id == sol.id)
                         .order_by(m.EventoAuditoria.id)):
        if ev.tipo in HITOS:
            hitos.append((ev.hora, HITOS[ev.tipo]))
    entrega, codigo, equipo = sv.entrega_activa(db, sol.id), None, None
    if entrega and sol.estado in (m.EstadoSolicitud.ASIGNADA, m.EstadoSolicitud.EN_CAMINO):
        codigo = sv.con_guion(sv.codigo_para(get_settings().secret_key, entrega.id, entrega.codigo_sal))
        equipo = db.get(m.Usuario, entrega.equipo_id)
    return dict(sol=sol, hitos=hitos, pasos=rc.pasos_solicitud(db, sol), codigo=codigo, equipo=equipo, entrega=entrega, nombres_estado=ESTADO,
                necesidad=NECESIDAD, urgencia=URGENCIA)


@router.get("/solicitudes/{sol_id}")
def seguimiento(sol_id: int, request: Request, db: Db, usuario: Solicitante):
    sol = _solicitud_propia(db, sol_id, usuario)
    return render(request, "seguimiento.html", usuario, **_contexto_seguimiento(db, sol))


@router.get("/solicitudes/{sol_id}/ficha")
def ficha(sol_id: int, request: Request, db: Db, usuario: Solicitante):
    sol = _solicitud_propia(db, sol_id, usuario)
    return render(request, "ficha.html", usuario, **_contexto_seguimiento(db, sol))


@router.post("/solicitudes/{sol_id}/confirmar")
def confirmar_recepcion(sol_id: int, request: Request, db: Db, usuario: Solicitante,
                        csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    sol = _solicitud_propia(db, sol_id, usuario)
    try:
        sv.cerrar_solicitud(db, sol, usuario)
    except sv.ErrorNegocio as e:
        mensaje_error(request, str(e))
    else:
        mensaje(request, "Gracias por confirmar. Su solicitud quedó cerrada.")
    return _redir(f"/solicitudes/{sol_id}")
