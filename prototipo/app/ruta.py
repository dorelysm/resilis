"""Por dónde va una entrega: del centro de acopio al destino, con la posición del equipo.

IMPORTANTE: en este prototipo la posición del equipo es SIMULADA. Se calcula sobre la línea recta entre el centro de
acopio y el destino, a partir de la hora a la que el equipo marcó "en camino", y con el tiempo acelerado para que se
vea el movimiento durante una demostración. No hay GPS real. Cada respuesta lo dice (`simulada: True`) y las pantallas
lo avisan. Para usar posiciones reales bastaría con reemplazar `_posicion_simulada`.

Privacidad: la persona que recibe ve el destino exacto de su propia solicitud. Quien dona y el personal solo ven el
barrio (con un círculo aproximado), nunca direcciones, nombres ni teléfonos.
"""
import math
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m

VELOCIDAD_DEMO_KMH = 600.0     # velocidad simulada (unas 20 veces la real), para que la demo no dure media hora
DURACION_MINIMA_S = 40.0
DURACION_MAXIMA_S = 240.0
DISTANCIA_CERCA_KM = 0.5       # a esta distancia se avisa que el equipo está cerca
RADIO_APROXIMADO_M = 300       # círculo que ve quien dona en lugar de un punto exacto
AVISO_SIMULACION = "Ruta simulada para la demostración: el movimiento va acelerado y no es la posición real de nadie."


def _utc(hora: datetime | None) -> datetime | None:
    return hora.replace(tzinfo=timezone.utc) if hora is not None and hora.tzinfo is None else hora


def kilometros(a: tuple[float, float], b: tuple[float, float]) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def duracion_demo(km: float) -> float:
    return min(DURACION_MAXIMA_S, max(DURACION_MINIMA_S, km / VELOCIDAD_DEMO_KMH * 3600))


def _posicion_simulada(origen: tuple[float, float], destino: tuple[float, float], desde: datetime, ahora: datetime):
    """(progreso de 0 a 1, posición) del equipo que salió `desde`. Línea recta entre el origen y el destino."""
    km = kilometros(origen, destino)
    segundos = max(0.0, (_utc(ahora) - _utc(desde)).total_seconds())
    progreso = min(1.0, segundos / duracion_demo(km))
    return progreso, (origen[0] + (destino[0] - origen[0]) * progreso, origen[1] + (destino[1] - origen[1]) * progreso)


def texto_tiempo(segundos: float) -> str:
    if segundos < 60:
        return "menos de un minuto"
    minutos = round(segundos / 60)
    return "1 minuto" if minutos == 1 else f"{minutos} minutos"


def _punto(lat, lon) -> tuple[float, float] | None:
    return (float(lat), float(lon)) if lat is not None and lon is not None else None


def _lugar_barrio(db: Session, barrio_id: int | None) -> tuple[tuple[float, float] | None, str]:
    barrio = db.get(m.Barrio, barrio_id) if barrio_id else None
    return (_punto(barrio.lat, barrio.lon) if barrio else None), (barrio.etiqueta if barrio else "")


def _centro_de(db: Session, solicitud_id: int) -> tuple[tuple[float, float] | None, str]:
    """El centro de acopio de donde sale la ayuda de una solicitud (según lo que se reservó o entregó para ella)."""
    mov = db.scalar(select(m.MovimientoInventario).where(
        m.MovimientoInventario.solicitud_id == solicitud_id,
        m.MovimientoInventario.tipo.in_(["reserva", "entrega"])).order_by(m.MovimientoInventario.id.desc()).limit(1))
    lote = db.get(m.Lote, mov.lote_id) if mov else None
    centro = db.get(m.CentroAcopio, lote.centro_id) if lote else None
    if centro is None:
        return None, ""
    punto = _punto(centro.lat, centro.lon) or _lugar_barrio(db, centro.barrio_id)[0]
    return punto, centro.nombre


def _inicio_en_camino(db: Session, solicitud_id: int) -> datetime | None:
    return db.scalar(select(m.EventoAuditoria.hora).where(
        m.EventoAuditoria.solicitud_id == solicitud_id, m.EventoAuditoria.tipo == "en_camino")
        .order_by(m.EventoAuditoria.id.desc()).limit(1))


def ruta_de_solicitud(db: Session, sol: m.Solicitud, exacta: bool, ahora: datetime | None = None) -> dict:
    """Todo lo que el mapa de una solicitud necesita. `exacta`: el destino es el punto de la solicitud (solo para la
    persona que la hizo); si no, es el centro del barrio."""
    ahora = _utc(ahora) or m.ahora()
    entrega = db.scalar(select(m.Entrega).where(m.Entrega.solicitud_id == sol.id).order_by(m.Entrega.id.desc()).limit(1))
    barrio_punto, barrio_nombre = _lugar_barrio(db, sol.barrio_id)
    destino = (_punto(sol.lat, sol.lon) if exacta else None) or barrio_punto
    origen, nombre_centro = _centro_de(db, sol.id)
    base = {"simulada": True, "aviso": AVISO_SIMULACION, "actualizado": ahora.isoformat(), "etapa": "sin_entrega",
            "texto": "Todavía no hay una entrega asignada para esta solicitud.", "progreso": 0.0, "posicion": None,
            "origen": {"nombre": nombre_centro, "lat": origen[0], "lon": origen[1]} if origen else None,
            "destino": {"nombre": "Su dirección" if exacta else barrio_nombre, "lat": destino[0], "lon": destino[1]} if destino else None,
            "km": None, "restante_km": None, "eta_segundos": None, "cerca": False}
    if entrega is None or origen is None or destino is None or sol.estado in ("registrada", "verificada", "anulada"):
        return base
    km = kilometros(origen, destino)
    base["km"] = round(km, 2)
    estado = sol.estado
    if estado in (m.EstadoSolicitud.ENTREGADA, m.EstadoSolicitud.CERRADA):
        return {**base, "etapa": "entregada", "progreso": 1.0, "posicion": {"lat": destino[0], "lon": destino[1]},
                "restante_km": 0.0, "eta_segundos": 0, "texto": "El equipo ya entregó la ayuda."}
    if estado == m.EstadoSolicitud.ASIGNADA or entrega.estado == "asignada":
        return {**base, "etapa": "asignada", "posicion": {"lat": origen[0], "lon": origen[1]}, "restante_km": round(km, 2),
                "texto": f"Su ayuda sale de {nombre_centro}. El equipo todavía no ha salido."}
    desde = _inicio_en_camino(db, sol.id) or entrega.creado_en
    progreso, pos = _posicion_simulada(origen, destino, desde, ahora)
    restante = km * (1 - progreso)
    eta = (1 - progreso) * duracion_demo(km)
    cerca = restante <= DISTANCIA_CERCA_KM
    if progreso >= 1.0:
        texto = "El equipo llegó. Tenga a la mano su código de entrega."
    elif cerca:
        texto = "El equipo está cerca. Tenga a la mano su código de entrega."
    else:
        texto = f"El equipo va en camino: faltan {restante:.1f} km, llega en unos {texto_tiempo(eta)}."
    return {**base, "etapa": "en_camino", "progreso": round(progreso, 3), "posicion": {"lat": pos[0], "lon": pos[1]},
            "restante_km": round(restante, 2), "eta_segundos": round(eta), "cerca": cerca, "texto": texto}


def ruta_de_donante(db: Session, donante: m.Donante | None, ahora: datetime | None = None) -> dict:
    """Por dónde van las entregas hechas con lo que donó una persona: centros de origen y barrios de destino, con un
    círculo aproximado. Sin direcciones ni datos de quien recibe."""
    ahora = _utc(ahora) or m.ahora()
    vacio = {"simulada": True, "aviso": AVISO_SIMULACION, "actualizado": ahora.isoformat(), "origenes": [], "destinos": [],
             "en_camino": [], "texto": "Todavía no hay entregas hechas con su donación."}
    if donante is None:
        return vacio
    donaciones = [d.id for d in db.scalars(select(m.Donacion).where(m.Donacion.donante_id == donante.id))]
    lotes = db.scalars(select(m.Lote).where(m.Lote.donacion_id.in_(donaciones))).all() if donaciones else []
    if not lotes:
        return vacio
    origenes = {}
    for lote in lotes:
        centro = db.get(m.CentroAcopio, lote.centro_id)
        punto = (_punto(centro.lat, centro.lon) or _lugar_barrio(db, centro.barrio_id)[0]) if centro else None
        if punto:
            origenes[centro.id] = {"nombre": centro.nombre, "lat": punto[0], "lon": punto[1]}
    movimientos = db.execute(select(m.MovimientoInventario.solicitud_id, m.MovimientoInventario.lote_id)
                             .where(m.MovimientoInventario.lote_id.in_([l.id for l in lotes]),
                                    m.MovimientoInventario.solicitud_id.is_not(None),
                                    m.MovimientoInventario.tipo.in_(["reserva", "entrega"]))).all()
    por_lote = {l.id: l for l in lotes}
    por_sol = {}
    for sol_id, lote_id in movimientos:
        por_sol.setdefault(sol_id, por_lote[lote_id])  # un lote de origen por solicitud basta para ubicar el viaje
    destinos: dict[int, dict] = {}
    en_camino = []
    for sol_id, lote in por_sol.items():
        sol = db.get(m.Solicitud, sol_id)
        if sol is None or sol.estado in ("registrada", "verificada", "anulada"):
            continue
        punto, nombre = _lugar_barrio(db, sol.barrio_id)
        if punto is None:
            continue
        d = destinos.setdefault(sol.barrio_id, {"barrio": nombre, "lat": punto[0], "lon": punto[1], "radio_m": RADIO_APROXIMADO_M,
                                               "entregas": 0, "en_camino": 0, "entregadas": 0})
        d["entregas"] += 1
        if sol.estado == m.EstadoSolicitud.EN_CAMINO:
            d["en_camino"] += 1
            centro = origenes.get(lote.centro_id)
            desde = _inicio_en_camino(db, sol_id)
            if centro and desde:
                _, pos = _posicion_simulada((centro["lat"], centro["lon"]), punto, desde, ahora)
                en_camino.append({"hacia": nombre, "lat": pos[0], "lon": pos[1]})
        elif sol.estado in (m.EstadoSolicitud.ENTREGADA, m.EstadoSolicitud.CERRADA):
            d["entregadas"] += 1
    lista = sorted(destinos.values(), key=lambda x: x["barrio"])
    total = sum(d["entregas"] for d in lista)
    texto = (f"Su ayuda va a {total} entrega(s) en {len(lista)} barrio(s): "
             f"{sum(d['entregadas'] for d in lista)} entregada(s), {sum(d['en_camino'] for d in lista)} en camino."
             if lista else "Todavía no hay entregas hechas con su donación.")
    return {**vacio, "origenes": list(origenes.values()), "destinos": lista, "en_camino": en_camino, "texto": texto}
