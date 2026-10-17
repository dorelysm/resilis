"""Punto de entrada de la aplicación web de Resilis."""
import mimetypes
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.config import get_settings
from app.cargas import cargar_viviendas
from app.db import SessionLocal, crear_tablas, engine, get_db
from app.migracion import migrar_sectores_a_barrios
from app.models import (
    Barrio, CentroAcopio, Entrega, Lote, Municipio, PlanAsignacion, Rol, Solicitud, Usuario, Verificacion, ahora,
)
from app.rutas import admin, auth, formularios, mapa, operacion, plan, prioridades
from app.seguridad import hash_password
from app.simulacion import generar
from app.territorio import corregir_nombres_municipios
from app.web import render, solo_digitos


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Al arrancar: crea las tablas que falten. No carga datos: la carga de viviendas es explícita
    (`uv run python -m app.cargas`). Si la base viene del esquema con sectores, los reemplaza por barrios."""
    borrado = migrar_sectores_a_barrios(engine)
    if borrado is not None:
        print(f"Sectores reemplazados por barrios. Registros borrados: {borrado}", flush=True)
    crear_tablas()
    with SessionLocal() as db:
        corregir_nombres_municipios(db)
    if get_settings().sembrar_demo:
        sembrar_demo()
    if get_settings().reiniciar_demo:
        reiniciar_demo()
    crear_primer_admin()
    if get_settings().listar_cuentas:
        listar_cuentas()
    yield


def sembrar_demo() -> None:
    """Carga las viviendas y genera un escenario simulado, solo si la base todavía no tiene barrios.
    Nunca borra nada: si ya hay datos, no hace nada."""
    with SessionLocal() as db:
        if db.scalar(select(Barrio.id).limit(1)) is not None:
            return
        cargar_viviendas(db)
        generar(db, semilla=42, tipo="inundacion", reiniciar=False)


def reiniciar_demo() -> None:
    """Renueva el escenario simulado (semilla 42, inundación). Conserva todas las cuentas reales y se niega, sin
    tumbar la aplicación, si esas cuentas ya hicieron algo (solicitudes, reportes, donaciones...). Todo ocurre en
    una sola transacción: si algo falla, queda lo anterior."""
    try:
        with SessionLocal() as db:
            r = generar(db, semilla=42, tipo="inundacion", reiniciar=True, conservar_cuentas=True)
        print(f"DEMO renovada: {r['barrios']} barrios, {r['reportes']} reportes, {r['solicitudes']} solicitudes, "
              f"{r['lotes']} lotes", flush=True)
    except RuntimeError as e:
        print(f"DEMO no renovada: {e}", flush=True)


def listar_cuentas() -> None:
    """Imprime las cuentas reales para revisarlas en los registros: sin contraseñas y con el teléfono recortado."""
    with SessionLocal() as db:
        filas = db.execute(select(Usuario, Barrio.etiqueta).outerjoin(Barrio, Barrio.id == Usuario.barrio_id)
                           .where(Usuario.ficticio.is_(False)).order_by(Usuario.id)).all()
        for u, barrio in filas:
            print(f"CUENTA id={u.id} rol={u.rol} nombre={u.nombre!r} tel=***{u.telefono[-4:]} aprobada={u.aprobado} "
                  f"organizacion={u.es_organizacion} con_clave={u.password_hash is not None} barrio={barrio}", flush=True)
        centros = db.scalars(select(CentroAcopio).join(Usuario, Usuario.id == CentroAcopio.responsable_id)
                             .where(Usuario.ficticio.is_(False))).all()
        estados = dict(db.execute(select(Solicitud.estado, func.count()).group_by(Solicitud.estado)).all())
        verificadas_reales = db.scalar(select(func.count()).select_from(Verificacion).where(
            Verificacion.objeto_tipo == "solicitud", Verificacion.nota != "Verificación simulada")) or 0
        inventario = db.execute(select(Lote.tipo_bien, func.sum(Lote.cantidad_disponible), func.sum(Lote.cantidad_reservada),
                                       func.sum(Lote.cantidad_entregada)).group_by(Lote.tipo_bien)).all()
        planes = db.execute(select(PlanAsignacion.id, PlanAsignacion.estado, PlanAsignacion.metodo,
                                   PlanAsignacion.necesidad_cubierta, PlanAsignacion.necesidad_total)).all()
        entregas = dict(db.execute(select(Entrega.estado, func.count()).group_by(Entrega.estado)).all())
        print(f"RESUMEN solicitudes={estados} verificaciones_no_simuladas={verificadas_reales} "
              f"inventario(disp,res,entr)={[(t, int(a or 0), int(b or 0), int(c or 0)) for t, a, b, c in inventario]} "
              f"planes={[tuple(p) for p in planes]} entregas={entregas}", flush=True)
        print(f"CUENTAS: {len(filas)} reales; centros de acopio reales: {[(c.id, c.nombre) for c in centros]}", flush=True)


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


mimetypes.add_type("image/webp", ".webp")  # no todos los sistemas lo traen registrado
settings = get_settings()
app = FastAPI(title="Resilis", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    SessionMiddleware, secret_key=settings.secret_key, max_age=8 * 3600, same_site="lax",
    https_only=settings.entorno == "produccion", session_cookie="resilis_sesion",
)
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
app.include_router(auth.router)
app.include_router(formularios.router)
app.include_router(operacion.router)
app.include_router(prioridades.router)
app.include_router(mapa.router)
app.include_router(plan.router)
app.include_router(admin.router)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    """Los navegadores piden el icono en esta ruta aunque la página indique otra."""
    return FileResponse(Path(__file__).parent / "static" / "img" / "favicon.ico", media_type="image/x-icon",
                        headers={"Cache-Control": "public, max-age=86400"})


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    """El service worker se sirve desde la raíz para poder cubrir /entregas (uso sin conexión)."""
    return FileResponse(Path(__file__).parent / "static" / "sw.js", media_type="text/javascript",
                        headers={"Service-Worker-Allowed": "/", "Cache-Control": "no-cache"})


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
    barrios = db.scalar(select(func.count()).select_from(Barrio))
    return {"estado": "ok", "base_de_datos": "ok", "municipios": municipios, "barrios": barrios}
