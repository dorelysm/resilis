"""Formularios de reporte de daños, solicitud de ayuda y donación (RF-05, RF-06, RF-12, RF-13, RF-52)."""
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import recorrido as rc
from app.db import get_db
from app.models import (
    CentroAcopio, Donacion, Donante, EstadoDonacion, Evento, FuenteReporte, ReporteDanos, Rol, Barrio, Solicitud,
    TipoNecesidad, Usuario, Vulnerabilidad, ahora,
)
from app.simulacion import UNIDAD_POR_PERSONA, UNIDADES
from app.rutas.prioridades import refrescar
from app.web import chequear_csrf, entero, mensaje, opciones_barrios, render, requiere_rol

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]

MAX_ENVIOS_POR_HORA = 20  # límite por usuario (RNF-07)
NECESIDADES = [(t.value, t.name.replace("_", " ").capitalize()) for t in TipoNecesidad]
NIVELES_DANO = [(0, "Sin daño"), (1, "Daño leve"), (2, "Daño moderado"), (3, "Daño grave")]
ACCESOS = [("1", "Se puede llegar sin problema"), ("0.5", "Se llega con dificultad"), ("0", "No se puede llegar")]
URGENCIAS = [(0, "Puedo esperar"), (1, "Lo necesito pronto"), (2, "Es urgente"), (3, "Hay riesgo para la vida")]
VULNERABILIDADES = [("discapacidad", "Persona con discapacidad"), ("adulto_mayor", "Adulto mayor"),
                    ("menor", "Niño o niña pequeño"), ("embarazo", "Embarazo"),
                    ("cronica", "Enfermedad crónica"), ("otra", "Otra situación")]
ESTADOS_PRODUCTO = [("nuevo", "Nuevo"), ("usado", "Usado en buen estado")]
ROLES_REPORTAN = (Rol.SOLICITANTE, Rol.BRIGADISTA, Rol.ENTIDAD)


def _barrios(db: Session) -> list[tuple[int, str]]:
    return opciones_barrios(db)


def _evento_actual(db: Session) -> Evento | None:
    return db.scalar(select(Evento).order_by(Evento.fecha.desc(), Evento.id.desc()).limit(1))


def _limite(db: Session, modelo, campo_usuario, usuario: Usuario, campo_hora) -> None:
    desde = ahora() - timedelta(hours=1)
    n = db.scalar(select(func.count()).select_from(modelo).where(campo_usuario == usuario.id, campo_hora >= desde))
    if n >= MAX_ENVIOS_POR_HORA:
        raise HTTPException(status_code=429, detail="Envió muchos formularios en poco tiempo. Espere un rato e intente de nuevo.")


def _hora(texto: str) -> datetime | None:
    try:
        return datetime.fromisoformat(texto).replace(tzinfo=timezone.utc) if texto else None
    except ValueError:
        return None


# ----------------------------------------------------------------------------- reportes de daños
@router.get("/reportes/nuevo")
def reporte_form(request: Request, db: Db, usuario: Annotated[Usuario, Depends(requiere_rol(*ROLES_REPORTAN))]):
    return render(request, "reporte_nuevo.html", usuario, barrios=_barrios(db), evento=_evento_actual(db),
                  niveles=NIVELES_DANO, accesos=ACCESOS, datos={"barrio_id": str(usuario.barrio_id or "")}, errores={})


@router.post("/reportes/nuevo")
def reporte(
    request: Request, db: Db, usuario: Annotated[Usuario, Depends(requiere_rol(*ROLES_REPORTAN))],
    barrio_id: Annotated[str, Form()] = "", nivel_dano: Annotated[str, Form()] = "",
    personas_afectadas: Annotated[str, Form()] = "0", acceso: Annotated[str, Form()] = "1",
    hora_evento: Annotated[str, Form()] = "", csrf: Annotated[str, Form()] = "",
):
    chequear_csrf(request, csrf)
    evento = _evento_actual(db)
    datos = {"barrio_id": barrio_id, "nivel_dano": nivel_dano, "personas_afectadas": personas_afectadas,
             "acceso": acceso, "hora_evento": hora_evento}
    errores: dict[str, str] = {}
    sid = entero(barrio_id, 1, 10**9)
    if sid is None or db.get(Barrio, sid) is None:
        errores["barrio_id"] = "Elija el barrio."
    nivel = entero(nivel_dano, 0, 3)
    if nivel is None:
        errores["nivel_dano"] = "Elija el nivel de daño."
    personas = entero(personas_afectadas, 0, 100000)
    if personas is None:
        errores["personas_afectadas"] = "Escriba un número entre 0 y 100000."
    if acceso not in dict(ACCESOS):
        errores["acceso"] = "Elija cómo está el acceso."
    if evento is None:
        errores["general"] = "Todavía no hay un evento registrado. Pida a la entidad coordinadora que lo cree."
    if errores:
        return render(request, "reporte_nuevo.html", usuario, estado=422, barrios=_barrios(db), evento=evento,
                      niveles=NIVELES_DANO, accesos=ACCESOS, datos=datos, errores=errores)
    _limite(db, ReporteDanos, ReporteDanos.autor_id, usuario, ReporteDanos.hora_captura)
    db.add(ReporteDanos(
        barrio_id=sid, evento_id=evento.id, autor_id=usuario.id, fuente=FuenteReporte.APP,
        hora_evento=_hora(hora_evento) or ahora(), hora_captura=ahora(), nivel_dano=nivel,
        personas_afectadas=personas, acceso=float(acceso),
    ))
    db.commit()
    refrescar(db)
    mensaje(request, "Su reporte fue enviado. Gracias por avisar.")
    return RedirectResponse("/reportes", status_code=303)


@router.get("/reportes")
def mis_reportes(request: Request, db: Db, usuario: Annotated[Usuario, Depends(requiere_rol(*ROLES_REPORTAN))]):
    filas = db.execute(
        select(ReporteDanos, Barrio.etiqueta).join(Barrio, Barrio.id == ReporteDanos.barrio_id)
        .where(ReporteDanos.autor_id == usuario.id).order_by(ReporteDanos.hora_captura.desc()).limit(30)
    ).all()
    pasos = {r.id: rc.pasos_reporte(db, r) for r, _ in filas}
    return render(request, "mis_reportes.html", usuario, filas=filas, pasos=pasos, niveles=dict(NIVELES_DANO))


# ----------------------------------------------------------------------------- solicitudes de ayuda
def _ctx_solicitud(db, datos, errores):
    return dict(barrios=_barrios(db), necesidades=NECESIDADES, urgencias=URGENCIAS,
                vulnerabilidades=VULNERABILIDADES, datos=datos, errores=errores)


@router.get("/solicitudes/nueva")
def solicitud_form(request: Request, db: Db, usuario: Annotated[Usuario, Depends(requiere_rol(Rol.SOLICITANTE))]):
    return render(request, "solicitud_nueva.html", usuario,
                  **_ctx_solicitud(db, {"barrio_id": str(usuario.barrio_id or ""), "personas_hogar": "1"}, {}))


@router.post("/solicitudes/nueva")
def solicitud(
    request: Request, db: Db, usuario: Annotated[Usuario, Depends(requiere_rol(Rol.SOLICITANTE))],
    barrio_id: Annotated[str, Form()] = "", necesidad: Annotated[str, Form()] = "",
    personas_hogar: Annotated[str, Form()] = "1", descripcion: Annotated[str, Form()] = "",
    urgencia: Annotated[str, Form()] = "", direccion: Annotated[str, Form()] = "",
    vulnerable: Annotated[str, Form()] = "", vuln_tipo: Annotated[str, Form()] = "",
    vuln_descripcion: Annotated[str, Form()] = "", vuln_necesidad: Annotated[str, Form()] = "",
    vuln_consentimiento: Annotated[str, Form()] = "", csrf: Annotated[str, Form()] = "",
):
    chequear_csrf(request, csrf)
    datos = {"barrio_id": barrio_id, "necesidad": necesidad, "personas_hogar": personas_hogar,
             "descripcion": descripcion, "urgencia": urgencia, "direccion": direccion, "vulnerable": vulnerable,
             "vuln_tipo": vuln_tipo, "vuln_descripcion": vuln_descripcion, "vuln_necesidad": vuln_necesidad}
    errores: dict[str, str] = {}
    sid = entero(barrio_id, 1, 10**9)
    if sid is None or db.get(Barrio, sid) is None:
        errores["barrio_id"] = "Elija el barrio donde está."
    if necesidad not in dict(NECESIDADES):
        errores["necesidad"] = "Elija qué necesita."
    hogar = entero(personas_hogar, 1, 30)
    if hogar is None:
        errores["personas_hogar"] = "Escriba cuántas personas viven con usted (de 1 a 30)."
    urg = entero(urgencia, 0, 3)
    if urg is None:
        errores["urgencia"] = "Elija qué tan urgente es."
    if len(descripcion.strip()) < 5:
        errores["descripcion"] = "Cuéntenos brevemente su situación."
    if len(direccion.strip()) < 3:
        errores["direccion"] = "Escriba su dirección o un punto de referencia."
    if vulnerable == "si":
        if vuln_tipo not in dict(VULNERABILIDADES):
            errores["vuln_tipo"] = "Elija la situación de vulnerabilidad."
        if len(vuln_descripcion.strip()) < 5:
            errores["vuln_descripcion"] = "Describa la situación de la persona."
        if vuln_consentimiento != "si":
            errores["vuln_consentimiento"] = "Para guardar estos datos necesitamos su autorización expresa."
    if errores:
        return render(request, "solicitud_nueva.html", usuario, estado=422, **_ctx_solicitud(db, datos, errores))

    _limite(db, Solicitud, Solicitud.creador_id, usuario, Solicitud.creado_en)
    evento = _evento_actual(db)
    sol = Solicitud(
        solicitante_id=usuario.id, creador_id=usuario.id, barrio_id=sid, evento_id=evento.id if evento else None,
        necesidad=necesidad, personas_hogar=hogar, cantidad=hogar * UNIDAD_POR_PERSONA[necesidad],
        descripcion=descripcion.strip(), urgencia=urg, direccion=direccion.strip(), fuente=FuenteReporte.APP,
        creado_en=ahora(),
    )
    db.add(sol)
    db.flush()
    if vulnerable == "si":
        db.add(Vulnerabilidad(solicitud_id=sol.id, tipo=vuln_tipo, descripcion_situacion=vuln_descripcion.strip(),
                              necesidad_especifica=vuln_necesidad.strip(), consentimiento=True,
                              consentimiento_fecha=ahora()))
    db.commit()
    refrescar(db)
    mensaje(request, "Su solicitud fue registrada. Aquí puede ver cómo avanza.")
    return RedirectResponse("/solicitudes", status_code=303)


ESTADOS = {"registrada": "Registrada", "verificada": "Verificada", "asignada": "Asignada", "en_camino": "En camino",
           "entregada": "Entregada", "cerrada": "Cerrada", "anulada": "Anulada"}


@router.get("/solicitudes")
def mis_solicitudes(request: Request, db: Db, usuario: Annotated[Usuario, Depends(requiere_rol(Rol.SOLICITANTE))]):
    filas = db.scalars(select(Solicitud).where(Solicitud.solicitante_id == usuario.id)
                       .order_by(Solicitud.creado_en.desc()).limit(100)).all()
    return render(request, "mis_solicitudes.html", usuario, filas=filas, estados=ESTADOS,
                  necesidades=dict(NECESIDADES), urgencias=dict(URGENCIAS))


# ----------------------------------------------------------------------------- donaciones
def _ctx_donacion(db, datos, errores):
    return dict(tipos=NECESIDADES, estados_producto=ESTADOS_PRODUCTO, barrios=_barrios(db),
                centros=[(c.id, c.nombre) for c in db.scalars(select(CentroAcopio).order_by(CentroAcopio.nombre))],
                datos=datos, errores=errores)


@router.get("/donaciones/nueva")
def donacion_form(request: Request, db: Db, usuario: Annotated[Usuario, Depends(requiere_rol(Rol.DONANTE))]):
    return render(request, "donacion_nueva.html", usuario, **_ctx_donacion(db, {"destino": "ninguno"}, {}))


@router.post("/donaciones/nueva")
def donacion(
    request: Request, db: Db, usuario: Annotated[Usuario, Depends(requiere_rol(Rol.DONANTE))],
    forma: Annotated[str, Form()] = "especie", tipo_bien: Annotated[str, Form()] = "",
    cantidad: Annotated[str, Form()] = "", monto: Annotated[str, Form()] = "",
    estado_producto: Annotated[str, Form()] = "nuevo", vencimiento: Annotated[str, Form()] = "",
    centro_id: Annotated[str, Form()] = "", destino: Annotated[str, Form()] = "ninguno",
    destino_barrio_id: Annotated[str, Form()] = "", csrf: Annotated[str, Form()] = "",
):
    chequear_csrf(request, csrf)
    datos = {"forma": forma, "tipo_bien": tipo_bien, "cantidad": cantidad, "monto": monto,
             "estado_producto": estado_producto, "vencimiento": vencimiento, "centro_id": centro_id,
             "destino": destino, "destino_barrio_id": destino_barrio_id}
    errores: dict[str, str] = {}
    donante = db.scalar(select(Donante).where(Donante.usuario_id == usuario.id))
    if donante is None:
        raise HTTPException(status_code=403, detail="Su cuenta no tiene un perfil de donante.")

    monetaria = forma == "monetaria"
    cant = monto_cop = None
    if monetaria:
        monto_cop = entero(monto, 1, 10**10)
        if monto_cop is None:
            errores["monto"] = "Escriba el valor en pesos."
    else:
        if tipo_bien not in dict(NECESIDADES):
            errores["tipo_bien"] = "Elija qué va a donar."
        cant = entero(cantidad, 1, 10**7)
        if cant is None:
            errores["cantidad"] = "Escriba una cantidad mayor que cero."
        if estado_producto not in dict(ESTADOS_PRODUCTO):
            errores["estado_producto"] = "Elija el estado del producto."
    venc = None
    if vencimiento:
        try:
            venc = datetime.fromisoformat(vencimiento).replace(tzinfo=timezone.utc)
        except ValueError:
            errores["vencimiento"] = "Escriba una fecha válida."
    cid = entero(centro_id, 1, 10**9) if centro_id else None
    if centro_id and (cid is None or db.get(CentroAcopio, cid) is None):
        errores["centro_id"] = "Elija un centro de acopio de la lista."
    dsid = None
    if destino == "barrio":
        dsid = entero(destino_barrio_id, 1, 10**9)
        if dsid is None or db.get(Barrio, dsid) is None:
            errores["destino_barrio_id"] = "Elija el barrio al que quiere dirigir la donación."
    elif destino not in ("ninguno", "tipo"):
        errores["destino"] = "Elija el destino de la donación."
    if errores:
        return render(request, "donacion_nueva.html", usuario, estado=422, **_ctx_donacion(db, datos, errores))

    db.add(Donacion(
        donante_id=donante.id, centro_id=cid, tipo_bien="otro" if monetaria else tipo_bien, monetaria=monetaria,
        monto=monto_cop, cantidad=0 if monetaria else cant,
        unidad="COP" if monetaria else UNIDADES[tipo_bien], estado_producto=estado_producto,
        vencimiento=venc, destino_barrio_id=dsid,
        destino_tipo_necesidad=tipo_bien if (destino == "tipo" and not monetaria) else None,
        estado=EstadoDonacion.OFRECIDA, creado_en=ahora(),
    ))
    db.commit()
    mensaje(request, "Gracias. Su donación quedó registrada como ofrecida.")
    return RedirectResponse("/donaciones", status_code=303)


@router.get("/donaciones")
def mis_donaciones(request: Request, db: Db, usuario: Annotated[Usuario, Depends(requiere_rol(Rol.DONANTE))]):
    donante = db.scalar(select(Donante).where(Donante.usuario_id == usuario.id))
    filas = []
    if donante:
        filas = db.scalars(select(Donacion).where(Donacion.donante_id == donante.id)
                           .order_by(Donacion.creado_en.desc()).limit(30)).all()
    pasos = {d.id: rc.pasos_donacion(db, d) for d in filas}
    return render(request, "mis_donaciones.html", usuario, filas=filas, pasos=pasos, tipos=dict(NECESIDADES))
