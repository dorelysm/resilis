"""Piezas comunes de la interfaz web: plantillas, sesión, roles, mensajes y CSRF."""
from pathlib import Path
from typing import Annotated

from fastapi import Depends, HTTPException, Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Rol, Usuario
from app.seguridad import csrf_valido, token_csrf

plantillas = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

ETIQUETA_ROL = {
    Rol.SOLICITANTE: "Persona que necesita ayuda",
    Rol.BRIGADISTA: "Brigadista",
    Rol.EQUIPO_ENTREGA: "Equipo de entrega",
    Rol.ENTIDAD: "Entidad coordinadora",
    Rol.ADMINISTRADOR: "Administrador",
    Rol.DONANTE: "Donante",
    Rol.CENTRO_ACOPIO: "Centro de acopio",
}


def usuario_actual(request: Request, db: Annotated[Session, Depends(get_db)]) -> Usuario | None:
    uid = request.session.get("usuario_id")
    return db.get(Usuario, uid) if uid else None


UsuarioOpcional = Annotated[Usuario | None, Depends(usuario_actual)]


def requiere_rol(*roles: str):
    """Dependencia: exige sesión iniciada y, si se indican roles, que el usuario tenga uno de ellos."""

    def _dep(usuario: UsuarioOpcional) -> Usuario:
        if usuario is None:
            raise HTTPException(status_code=303, headers={"Location": "/entrar"})
        if roles and usuario.rol not in roles:
            raise HTTPException(status_code=403, detail="Esta página no está disponible para su tipo de usuario.")
        return usuario

    return _dep


def mensaje(request: Request, texto: str) -> None:
    request.session.setdefault("mensajes", []).append(texto)


def mensaje_error(request: Request, texto: str) -> None:
    """Un aviso de algo que salió mal; la plantilla lo muestra como alerta."""
    request.session.setdefault("mensajes", []).append("!" + texto)


def render(request: Request, nombre: str, usuario: Usuario | None = None, estado: int = 200, **contexto):
    mensajes = request.session.pop("mensajes", [])
    contexto.update(usuario=usuario, csrf=token_csrf(request.session), mensajes=mensajes,
                    etiqueta_rol=ETIQUETA_ROL)
    return plantillas.TemplateResponse(request, nombre, contexto, status_code=estado)


def chequear_csrf(request: Request, enviado: str | None) -> None:
    if not csrf_valido(request.session, enviado):
        raise HTTPException(status_code=403, detail="La página caducó. Vuelva a cargarla e intente de nuevo.")


def opciones_barrios(db: Session) -> list[tuple[int, str, str]]:
    """Barrios como (id, nombre, municipio) para las listas desplegables, agrupados por municipio."""
    from sqlalchemy import select

    from app.models import Barrio, Municipio

    filas = db.execute(select(Barrio.id, Barrio.nombre, Municipio.nombre).join(Municipio)
                       .order_by(Municipio.nombre, Barrio.nombre)).all()
    return [(i, nombre, municipio) for i, nombre, municipio in filas]


def solo_digitos(texto: str) -> str:
    return "".join(c for c in texto if c.isdigit())


def entero(valor: str | None, minimo: int, maximo: int, por_defecto: int | None = None) -> int | None:
    try:
        n = int(valor)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return por_defecto
    return n if minimo <= n <= maximo else por_defecto
