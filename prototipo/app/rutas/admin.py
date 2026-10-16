"""Administración de cuentas (RF-03): crear brigadistas, entidades, equipos de entrega y centros de acopio."""
from typing import Annotated

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app import servicios
from app.models import Bitacora, CentroAcopio, EventoAuditoria, Rol, Sector, Usuario, ahora
from app.seguridad import hash_password
from app.web import ETIQUETA_ROL, chequear_csrf, entero, mensaje, opciones_sectores, render, requiere_rol, solo_digitos

router = APIRouter(prefix="/admin")
Db = Annotated[Session, Depends(get_db)]
Admin = Annotated[Usuario, Depends(requiere_rol(Rol.ADMINISTRADOR))]

ROLES_CREABLES = (Rol.BRIGADISTA, Rol.ENTIDAD, Rol.EQUIPO_ENTREGA, Rol.CENTRO_ACOPIO)


def _contexto(db: Session, datos=None, errores=None):
    cuentas = db.scalars(select(Usuario).where(Usuario.ficticio.is_(False)).order_by(Usuario.creado_en.desc())
                         .limit(200)).all()
    sectores = opciones_sectores(db)
    return dict(cuentas=cuentas, sectores=sectores, roles=[(r.value, ETIQUETA_ROL[r]) for r in ROLES_CREABLES],
                datos=datos or {}, errores=errores or {})


@router.get("/usuarios")
def usuarios(request: Request, db: Db, admin: Admin):
    return render(request, "admin_usuarios.html", admin, **_contexto(db))


@router.post("/usuarios")
def crear_usuario(
    request: Request, db: Db, admin: Admin,
    nombre: Annotated[str, Form()] = "", telefono: Annotated[str, Form()] = "", rol: Annotated[str, Form()] = "",
    sector_id: Annotated[str, Form()] = "", es_organizacion: Annotated[str, Form()] = "",
    password: Annotated[str, Form()] = "", csrf: Annotated[str, Form()] = "",
):
    chequear_csrf(request, csrf)
    datos = {"nombre": nombre, "telefono": telefono, "rol": rol, "sector_id": sector_id,
             "es_organizacion": es_organizacion}
    errores: dict[str, str] = {}
    if len(nombre.strip()) < 3:
        errores["nombre"] = "Escriba el nombre."
    tel = solo_digitos(telefono)
    if not 7 <= len(tel) <= 12:
        errores["telefono"] = "Escriba un teléfono de 7 a 12 dígitos."
    elif db.scalar(select(Usuario.id).where(Usuario.telefono == tel, Usuario.password_hash.is_not(None))):
        errores["telefono"] = "Ya existe una cuenta con este teléfono."
    if rol not in {r.value for r in ROLES_CREABLES}:
        errores["rol"] = "Elija un tipo de cuenta."
    if len(password) < 8:
        errores["password"] = "La contraseña temporal debe tener al menos 8 caracteres."
    sid = entero(sector_id, 1, 10**9) if sector_id else None
    if sector_id and (sid is None or db.get(Sector, sid) is None):
        errores["sector_id"] = "Elija un sector de la lista."
    if errores:
        return render(request, "admin_usuarios.html", admin, estado=422, **_contexto(db, datos, errores))

    organizacion = es_organizacion == "si"
    nuevo = Usuario(
        nombre=nombre.strip(), telefono=tel, rol=rol, sector_id=sid, password_hash=hash_password(password),
        consentimiento_datos=True, consentimiento_fecha=ahora(), ficticio=False,
        es_organizacion=organizacion, aprobado=not organizacion,  # las organizaciones requieren aprobación
    )
    db.add(nuevo)
    db.flush()
    if rol == Rol.CENTRO_ACOPIO:  # un centro de acopio necesita su sitio de inventario
        db.add(CentroAcopio(nombre=f"Centro de acopio de {nuevo.nombre}", sector_id=sid, responsable_id=nuevo.id))
    db.add(Bitacora(usuario_id=admin.id, accion="crear_usuario", objeto=f"usuario:{nuevo.id}", detalle={"rol": rol}))
    db.commit()
    mensaje(request, "La cuenta fue creada." + (" Falta aprobarla." if organizacion else ""))
    return RedirectResponse("/admin/usuarios", status_code=303)


@router.get("/auditoria")
def auditoria(request: Request, db: Db, admin: Admin):
    """Revisa la cadena de eventos: si alguien alteró uno, se muestra cuál."""
    integra, roto = servicios.verificar_cadena(db)
    total = db.scalar(select(func.count()).select_from(EventoAuditoria))
    ultimos = db.scalars(select(EventoAuditoria).order_by(EventoAuditoria.id.desc()).limit(30)).all()
    return render(request, "admin_auditoria.html", admin, integra=integra, roto=roto, total=total, ultimos=ultimos)


@router.post("/usuarios/{usuario_id}/aprobar")
def aprobar(usuario_id: int, request: Request, db: Db, admin: Admin, csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    u = db.get(Usuario, usuario_id)
    if u is None or u.ficticio:
        raise HTTPException(status_code=404, detail="No se encontró la cuenta.")
    u.aprobado = True
    db.add(Bitacora(usuario_id=admin.id, accion="aprobar_usuario", objeto=f"usuario:{u.id}"))
    db.commit()
    mensaje(request, f"La cuenta de {u.nombre} fue aprobada.")
    return RedirectResponse("/admin/usuarios", status_code=303)
