"""Escenario guionado: un vendaval en Malambo.

A diferencia del generador general (app/simulacion.py), esto es una historia corta y controlada para recorrer el ciclo
completo en una demostración: un barrio epicentro con daño máximo que baja con la distancia, los reportes de la gente,
10 solicitudes de ayuda (8 para reparar viviendas y 2 casos especiales), y un inventario que alcanza para casi todo
menos la silla de ruedas. Todas las personas que reportan, piden ayuda o donan son cuentas ficticias (sin contraseña).

Lo deja listo para que las cuentas reales lo operen: las solicitudes y los reportes quedan SIN verificar, hay una
donación ofrecida esperando que el centro de acopio la reciba, y no hay ningún plan.

Uso en producción: variable CARGAR_ESCENARIO_MALAMBO=true (de un solo uso). Se niega si ya hay algún evento.
"""
import math
from datetime import timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app import puntaje as pj
from app import servicios as sv
from app.simulacion import UNIDADES, _documento, _persona, _telefono, sembrar_pesos

CODIGO_MALAMBO = "08433"
EPICENTRO = "El Edén"         # el barrio de Malambo con sus 4 vecinos más cercanos todos a menos de 250 m
N_AFECTADOS = 5               # el epicentro y sus 4 vecinos más cercanos; ningún otro barrio queda afectado
INTENSIDAD = 0.9
ESCALA_KM = 0.25              # el daño cae a 1/e cada 250 m
HORAS_ANTES = 6.0             # el vendaval ocurrió hace 6 horas

REPARACIONES = [
    "El vendaval se llevó parte del techo y entra el agua. Necesitamos láminas y clavos para repararlo.",
    "Se cayó una pared de la cocina con el viento. Necesitamos materiales para levantarla.",
    "El techo de la casa quedó destruido. Necesitamos láminas, madera y lonas para cubrirlo.",
    "Una lámina cayó sobre la sala y dañó el techo. Necesitamos materiales para repararlo.",
    "Perdimos el techo del cuarto de los niños. Necesitamos láminas para repararlo.",
    "El viento arrancó el techo y la puerta. Necesitamos materiales para reparar la vivienda.",
    "El techo de zinc se desprendió. Necesitamos láminas nuevas y clavos.",
    "Una rama grande rompió el techo. Necesitamos materiales para el arreglo.",
]


def _km(a: tuple[float, float], b: tuple[float, float]) -> float:
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


def afectados(barrios: list[m.Barrio], epicentro: m.Barrio) -> list[m.Barrio]:
    """El epicentro y sus vecinos más cercanos, de más cerca a más lejos."""
    centro = (epicentro.lat, epicentro.lon)
    return sorted(barrios, key=lambda b: (_km(centro, (b.lat, b.lon)), b.nombre))[:N_AFECTADOS]


def danos(barrios: list[m.Barrio], epicentro: m.Barrio) -> dict[int, float]:
    """Daño de cada barrio (0 a 1): máximo en el epicentro y menor en sus 4 vecinos más cercanos; 0 en todos los demás."""
    centro = (epicentro.lat, epicentro.lon)
    cerca = {b.id for b in afectados(barrios, epicentro)}
    return {b.id: round(INTENSIDAD * math.exp(-_km(centro, (b.lat, b.lon)) / ESCALA_KM), 3) if b.id in cerca else 0.0
            for b in barrios}


def _usuario(db: Session, rng, ahora, rol: str, barrio: m.Barrio | None = None) -> m.Usuario:
    u = m.Usuario(nombre=_persona(rng), telefono=_telefono(rng), documento=_documento(rng), rol=rol,
                  barrio_id=barrio.id if barrio else None, consentimiento_datos=True, consentimiento_fecha=ahora,
                  ficticio=True, creado_en=ahora)
    db.add(u)
    db.flush()
    return u


def cargar(db: Session, semilla: int = 2026, ahora=None) -> dict:
    """Crea el evento, los reportes, las 10 solicitudes y el inventario. Hace commit y recalcula las prioridades."""
    if db.scalar(select(m.Evento.id).limit(1)) is not None:
        raise RuntimeError("Ya hay un evento cargado: el escenario de Malambo solo se carga sobre una base sin eventos.")
    barrios = list(db.scalars(select(m.Barrio).where(m.Barrio.municipio_codigo == CODIGO_MALAMBO, m.Barrio.lat.is_not(None))
                              .order_by(m.Barrio.id)))
    epicentro = next((b for b in barrios if b.nombre == EPICENTRO), None)
    if epicentro is None:
        raise RuntimeError(f"No se encontró el barrio {EPICENTRO} de Malambo: hay que cargar los barrios primero.")
    rng = np.random.default_rng(semilla)
    ahora = ahora or m.ahora()
    fecha = ahora - timedelta(hours=HORAS_ANTES)
    dano = danos(barrios, epicentro)

    evento = m.Evento(tipo=m.TipoEvento.VENDAVAL, nombre="Vendaval en Malambo (simulado)", fecha=fecha,
                      zona={"lat": epicentro.lat, "lon": epicentro.lon, "radio_km": round(ESCALA_KM * 2.5, 1)},
                      intensidad=INTENSIDAD, origen=m.OrigenDato.SIMULADO, semilla=semilla)
    db.add(evento)
    db.flush()

    brigadistas = [_usuario(db, rng, ahora, m.Rol.BRIGADISTA) for _ in range(3)]
    entidad = _usuario(db, rng, ahora, m.Rol.ENTIDAD)
    ciudadanos: dict[int, list[m.Usuario]] = {}

    # ---- reportes: solo en los 5 barrios afectados; reportan más donde hay más daño y cada reporte trae algo de ruido
    reportes = 0
    cerca = afectados(barrios, epicentro)
    for b in cerca:
        d = dano[b.id]
        for _ in range(2 + int(rng.poisson(2 * d))):
            r = rng.random()
            if r < 0.65:
                pool = ciudadanos.setdefault(b.id, [])
                autor = pool[int(rng.integers(len(pool)))] if pool and rng.random() < 0.4 else _usuario(db, rng, ahora, m.Rol.SOLICITANTE, b)
                if autor not in pool:
                    pool.append(autor)
                ruido = 0.8
            elif r < 0.9:
                autor, ruido = brigadistas[int(rng.integers(len(brigadistas)))], 0.35
            else:
                autor, ruido = entidad, 0.25
            nivel = int(np.clip(round(3 * d + rng.normal(0, ruido)), 0, 3))
            db.add(m.ReporteDanos(
                barrio_id=b.id, evento_id=evento.id, autor_id=autor.id, fuente=m.FuenteReporte.APP,
                hora_evento=fecha, hora_captura=fecha + timedelta(hours=min(5.0, float(rng.exponential(1.5)))),
                nivel_dano=nivel, personas_afectadas=int(d * b.personas * rng.uniform(0.05, 0.25)),
                acceso=round(float(np.clip(b.acceso_base * (1 - 0.3 * d) + rng.normal(0, 0.05), 0, 1)), 3)))
            reportes += 1
    db.flush()

    # ---- 10 solicitudes, todas de los 5 barrios afectados: más donde hay más daño (el epicentro, 3) y los dos casos
    # especiales en barrios vecinos
    e0, e1, e2, e3, e4 = cerca  # de más cerca a más lejos del epicentro
    reparaciones_en = [e0, e0, e0, e1, e1, e2, e3, e4]
    medicinas_en, silla_en = e1, e2

    def nueva(barrio, necesidad, cantidad, hogar, texto, urgencia, creador=None, fuente=m.FuenteReporte.APP):
        solicitante = _usuario(db, rng, ahora, m.Rol.SOLICITANTE, barrio)
        sol = m.Solicitud(
            solicitante_id=solicitante.id, creador_id=(creador or solicitante).id, barrio_id=barrio.id,
            evento_id=evento.id, necesidad=necesidad, cantidad=cantidad, personas_hogar=hogar, descripcion=texto,
            urgencia=urgencia, direccion=f"Calle {rng.integers(1, 60)} # {rng.integers(1, 60)}-{rng.integers(1, 99)}",
            lat=float(barrio.lat + rng.normal(0, 0.002)), lon=float(barrio.lon + rng.normal(0, 0.002)),
            fuente=fuente, estado=m.EstadoSolicitud.REGISTRADA,
            creado_en=fecha + timedelta(hours=float(rng.uniform(1.0, 5.5))))
        db.add(sol)
        db.flush()
        return sol

    for i in range(8):
        b = reparaciones_en[i]
        urgencia = 2 if dano[b.id] >= 0.5 else 1
        nueva(b, m.TipoNecesidad.ABRIGO_VIVIENDA, int(rng.integers(2, 5)), int(rng.integers(3, 7)), REPARACIONES[i], urgencia)

    medicinas = nueva(medicinas_en, m.TipoNecesidad.MEDICAMENTOS, 1, 2,
                      "Perdí mis medicinas de uso continuo cuando se cayó el techo. Las necesito para seguir viviendo.", 3)
    db.add(m.Vulnerabilidad(solicitud_id=medicinas.id, tipo="cronica", consentimiento=True,
                            consentimiento_fecha=medicinas.creado_en,
                            descripcion_situacion="Persona con enfermedad crónica que perdió su medicación en el desastre.",
                            necesidad_especifica="Medicamentos de uso continuo"))
    silla = nueva(silla_en, m.TipoNecesidad.OTRO, 1, 1,
                  "Mi silla de ruedas quedó destruida con el vendaval y ya no sirve. No puedo salir de la casa.", 2,
                  creador=brigadistas[0], fuente=m.FuenteReporte.PAPEL)
    db.add(m.Vulnerabilidad(solicitud_id=silla.id, tipo="discapacidad", consentimiento=True,
                            consentimiento_fecha=silla.creado_en,
                            descripcion_situacion="Persona con movilidad reducida cuya silla de ruedas quedó inservible.",
                            necesidad_especifica="Silla de ruedas"))
    db.flush()

    # ---- inventario: alcanza para casi todo, pero no hay silla de ruedas (nadie donó nada del tipo "otro")
    centro = db.scalar(select(m.CentroAcopio).join(m.Usuario, m.Usuario.id == m.CentroAcopio.responsable_id)
                       .where(m.Usuario.ficticio.is_(False)).order_by(m.CentroAcopio.id).limit(1))
    if centro is None:
        resp = _usuario(db, rng, ahora, m.Rol.CENTRO_ACOPIO, epicentro)
        centro = m.CentroAcopio(nombre="Centro de acopio de Malambo (simulado)", barrio_id=epicentro.id, lat=epicentro.lat,
                                lon=epicentro.lon, responsable_id=resp.id)
        db.add(centro)
        db.flush()
    responsable = db.get(m.Usuario, centro.responsable_id)
    donantes = []
    for tipo in ("persona", "empresa", "organizacion", "persona"):
        u = _usuario(db, rng, ahora, m.Rol.DONANTE)
        d = m.Donante(usuario_id=u.id, nombre=u.nombre if tipo == "persona" else f"{tipo.capitalize()} simulada {u.id}",
                      tipo=tipo, contacto=u.telefono, nombre_publico=True, consentimiento=True)
        db.add(d)
        donantes.append(d)
    db.flush()

    donaciones = [  # (donante, tipo, cantidad, vence en días, ¿ya recibida?)
        (0, m.TipoNecesidad.ABRIGO_VIVIENDA, 25, None, True),
        (1, m.TipoNecesidad.ABRIGO_VIVIENDA, 15, None, True),
        (2, m.TipoNecesidad.MEDICAMENTOS, 6, 90, True),
        (3, m.TipoNecesidad.AGUA, 300, None, True),
        (3, m.TipoNecesidad.HIGIENE, 30, None, True),
        (2, m.TipoNecesidad.ALIMENTOS, 120, 60, True),
        (1, m.TipoNecesidad.ABRIGO_VIVIENDA, 20, None, False),  # ofrecida: el centro de acopio la recibe en la demostración
    ]
    for i, (quien, tipo, cantidad, dias, recibida) in enumerate(donaciones):
        venc = ahora + timedelta(days=dias) if dias else None
        don = m.Donacion(donante_id=donantes[quien].id, centro_id=centro.id, tipo_bien=tipo, cantidad=cantidad,
                         unidad=UNIDADES[tipo], vencimiento=venc, estado=m.EstadoDonacion.OFRECIDA,
                         creado_en=fecha + timedelta(hours=2 + i * 0.5))
        db.add(don)
        db.flush()
        if recibida:
            sv.recibir_donacion(db, don, centro, responsable, cantidad, "nuevo", venc)

    sembrar_pesos(db)
    db.commit()
    resumen = pj.recalcular(db, evento)
    nombre = {b.id: b.nombre for b in barrios}
    return {"evento_id": evento.id, "epicentro": epicentro.nombre, "barrios_malambo": len(barrios), "reportes": reportes,
            "solicitudes": 10, "donaciones": len(donaciones), "centro": centro.nombre,
            "afectados": [(b.nombre, dano[b.id]) for b in cerca], "prioridades": resumen}
