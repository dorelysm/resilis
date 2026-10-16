"""Punto de entrada de la aplicación web de Resilis."""
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.db import SessionLocal, crear_tablas, get_db
from app.models import Municipio, Rol, Usuario, ahora
from app.rutas import admin, auth, formularios
from app.seguridad import hash_password
from app.web import render, solo_digitos


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Al arrancar: crea las tablas que falten. No carga datos: la carga de viviendas es explícita
    (`uv run python -m app.cargas`) y todavía no se ha ejecutado."""
    crear_tablas()
    crear_primer_admin()
    yield


def crear_primer_admin() -> None:
    """Si se definieron ADMIN_TELEFONO y ADMIN_PASSWORD y aún no hay administrador, lo crea."""
    s = get_settings()
    tel = solo_digitos(s.admin_telefono)
    if not tel or len(s.admin_password) < 8:
        return
    with SessionLocal() as db:
        if db.scalar(select(Usuario.id).where(Usuario.rol == Rol.ADMINISTRADOR, Usuario.ficticio.is_(False))):
            return
        db.add(Usuario(nombre=s.admin_nombre, telefono=tel, rol=Rol.ADMINISTRADOR,
                       password_hash=hash_password(s.admin_password), consentimiento_datos=True,
                       consentimiento_fecha=ahora(), ficticio=False))
        db.commit()


settings = get_settings()
app = FastAPI(title="Resilis", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware, secret_key=settings.secret_key, max_age=8 * 3600, same_site="lax",
    https_only=settings.entorno == "produccion", session_cookie="resilis_sesion",
)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(auth.router)
app.include_router(formularios.router)
app.include_router(admin.router)


@app.exception_handler(StarletteHTTPException)
async def errores_http(request: Request, exc: StarletteHTTPException):
    """Las redirecciones (303) siguen su camino; los demás errores se muestran en una página sencilla."""
    if exc.status_code in (303, 307) or "text/html" not in request.headers.get("accept", "text/html"):
        return await http_exception_handler(request, exc)
    textos = {403: "No tiene permiso para ver esta página.", 404: "No encontramos esta página.",
              429: "Hay demasiadas solicitudes. Espere un momento."}
    return render(request, "error.html", None, estado=exc.status_code, codigo=exc.status_code,
                  texto=exc.detail if isinstance(exc.detail, str) and exc.status_code != 404 else
                  textos.get(exc.status_code, "Ocurrió un problema."))


@app.get("/salud")
def salud(db: Session = Depends(get_db)) -> dict:
    """Comprueba que la aplicación y la base de datos responden."""
    db.execute(text("SELECT 1"))
    municipios = db.scalar(select(func.count()).select_from(Municipio))
    return {"estado": "ok", "base_de_datos": "ok", "municipios": municipios}
