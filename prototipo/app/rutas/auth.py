"""Inicio, registro, entrada y salida."""
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Donante, Rol, Barrio, Usuario, ahora
from app.seguridad import hash_password, verificar_password
from app.inicio import que_sigue
from app.web import UsuarioOpcional, chequear_csrf, entero, mensaje, opciones_barrios, render, solo_digitos

router = APIRouter()
Db = Annotated[Session, Depends(get_db)]

_HASH_FALSO = hash_password("contraseña-que-nadie-usa")
CUENTAS_PUBLICAS = {"solicitante": Rol.SOLICITANTE, "donante": Rol.DONANTE}
TIPOS_DONANTE = ("persona", "organizacion", "empresa")


def _barrios(db: Session) -> list[tuple[int, str]]:
    return opciones_barrios(db)


@router.get("/")
def inicio(request: Request, db: Db, usuario: UsuarioOpcional):
    return render(request, "inicio.html", usuario, pendientes=que_sigue(db, usuario) if usuario else [])


@router.get("/como-funciona")
def como_funciona(request: Request, usuario: UsuarioOpcional):
    """Explicación detallada del sistema, abierta a todos (sin cuenta)."""
    return render(request, "como_funciona.html", usuario)


@router.get("/registro")
def registro_form(request: Request, db: Db, usuario: UsuarioOpcional):
    return render(request, "registro.html", usuario, barrios=_barrios(db), datos={}, errores={})


@router.post("/registro")
def registro(
    request: Request, db: Db, usuario: UsuarioOpcional,
    nombre: Annotated[str, Form()] = "", telefono: Annotated[str, Form()] = "",
    barrio_id: Annotated[str, Form()] = "", documento: Annotated[str, Form()] = "",
    tipo_cuenta: Annotated[str, Form()] = "solicitante", tipo_donante: Annotated[str, Form()] = "persona",
    password: Annotated[str, Form()] = "", password2: Annotated[str, Form()] = "",
    consentimiento: Annotated[str, Form()] = "", csrf: Annotated[str, Form()] = "",
):
    chequear_csrf(request, csrf)
    datos = {"nombre": nombre.strip(), "telefono": telefono.strip(), "barrio_id": barrio_id,
             "documento": documento.strip(), "tipo_cuenta": tipo_cuenta, "tipo_donante": tipo_donante}
    errores: dict[str, str] = {}

    if len(datos["nombre"]) < 3:
        errores["nombre"] = "Escriba su nombre completo."
    tel = solo_digitos(telefono)
    if not 7 <= len(tel) <= 12:
        errores["telefono"] = "Escriba un número de teléfono de 7 a 12 dígitos."
    elif db.scalar(select(Usuario.id).where(Usuario.telefono == tel, Usuario.password_hash.is_not(None))):
        errores["telefono"] = "Ya existe una cuenta con este teléfono. Use la opción Entrar."
    if tipo_cuenta not in CUENTAS_PUBLICAS:
        errores["tipo_cuenta"] = "Elija un tipo de cuenta."
    sid = entero(barrio_id, 1, 10**9)
    if tipo_cuenta == "solicitante" and (sid is None or db.get(Barrio, sid) is None):
        errores["barrio_id"] = "Elija el barrio donde vive."
    if len(password) < 8:
        errores["password"] = "La contraseña debe tener al menos 8 caracteres."
    elif password != password2:
        errores["password2"] = "Las contraseñas no coinciden."
    if consentimiento != "si":
        errores["consentimiento"] = "Para crear la cuenta debe autorizar el uso de sus datos."
    if tipo_cuenta == "donante" and tipo_donante not in TIPOS_DONANTE:
        errores["tipo_donante"] = "Elija el tipo de donante."

    if errores:
        return render(request, "registro.html", usuario, estado=422, barrios=_barrios(db), datos=datos,
                      errores=errores)

    nuevo = Usuario(
        nombre=datos["nombre"], telefono=tel, documento=datos["documento"] or None, rol=CUENTAS_PUBLICAS[tipo_cuenta],
        barrio_id=sid if db.get(Barrio, sid or 0) else None, password_hash=hash_password(password),
        consentimiento_datos=True, consentimiento_fecha=ahora(), ficticio=False,
    )
    db.add(nuevo)
    db.flush()
    if tipo_cuenta == "donante":
        db.add(Donante(usuario_id=nuevo.id, nombre=nuevo.nombre, tipo=tipo_donante, contacto=tel, consentimiento=True))
    db.commit()
    request.session.clear()
    request.session["usuario_id"] = nuevo.id
    mensaje(request, "Su cuenta fue creada.")
    return RedirectResponse("/", status_code=303)


@router.get("/entrar")
def entrar_form(request: Request, usuario: UsuarioOpcional):
    return render(request, "entrar.html", usuario, datos={}, error=None)


@router.post("/entrar")
def entrar(request: Request, db: Db, usuario: UsuarioOpcional,
           telefono: Annotated[str, Form()] = "", password: Annotated[str, Form()] = "",
           csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    tel = solo_digitos(telefono)
    candidato = db.scalar(select(Usuario).where(Usuario.telefono == tel, Usuario.password_hash.is_not(None)))
    # Se verifica siempre una contraseña, exista o no el usuario, para no revelar cuáles teléfonos tienen cuenta
    if not verificar_password(password, candidato.password_hash if candidato else _HASH_FALSO) or not candidato:
        return render(request, "entrar.html", usuario, estado=401, datos={"telefono": telefono},
                      error="El teléfono o la contraseña no son correctos.")
    if not candidato.aprobado:
        return render(request, "entrar.html", usuario, estado=403, datos={"telefono": telefono},
                      error="Su cuenta todavía no ha sido aprobada.")
    request.session.clear()  # evita reutilizar una sesión anterior
    request.session["usuario_id"] = candidato.id
    return RedirectResponse("/", status_code=303)


@router.post("/salir")
def salir(request: Request, csrf: Annotated[str, Form()] = ""):
    chequear_csrf(request, csrf)
    request.session.clear()
    return RedirectResponse("/", status_code=303)
