"""Generador de datos simulados (bloque 2 del plan).

Todo es ficticio y reproducible: con la misma semilla se obtienen los mismos datos. Lo único real son las
viviendas proyectadas por municipio, que sirven de ancla: las viviendas de los barrios suman la cifra
municipal (RD-09). Los daños, las personas, los reportes, las solicitudes, las donaciones y el inventario se
simulan (RD-10 a RD-13, RD-22 de los requisitos).

Uso:  uv run python -m app.simulacion --seed 42 --tipo inundacion
"""
import argparse
import math
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app import models as m
from app.territorio import MUNICIPIOS, leer_barrios

BASE_FECHA = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)  # fija, para que el resultado se repita

NOMBRES = ["Camila", "Mateo", "Valentina", "Santiago", "Sofía", "Samuel", "Isabella", "Daniel", "Mariana", "Andrés",
           "Laura", "Julián", "Paula", "Sebastián", "Daniela", "Felipe", "Natalia", "Alejandro", "Carolina", "Camilo"]
APELLIDOS = ["Ramos", "Vargas", "Castro", "Ortiz", "Mendoza", "Pérez", "Rojas", "Herrera", "Molina", "Cantillo",
             "Barraza", "Orozco", "Polo", "Escorcia", "Ariza", "Salcedo", "Villa", "Cervantes", "Mejía", "Pacheco"]

# Qué necesitan las personas según el tipo de evento (probabilidades; el orden sigue a TipoNecesidad)
NECESIDADES = ["alimentos", "agua", "medicamentos", "higiene", "abrigo_vivienda", "otro"]
PERFIL_NECESIDAD = {
    "terremoto": [0.15, 0.15, 0.20, 0.05, 0.40, 0.05],
    "inundacion": [0.25, 0.25, 0.05, 0.20, 0.20, 0.05],
    "vendaval": [0.15, 0.10, 0.05, 0.05, 0.60, 0.05],
    "deslizamiento": [0.20, 0.15, 0.15, 0.05, 0.40, 0.05],
}
UNIDAD_POR_PERSONA = {"alimentos": 3, "agua": 6, "medicamentos": 1, "higiene": 2, "abrigo_vivienda": 1, "otro": 1}
UNIDADES = {"alimentos": "raciones", "agua": "litros", "medicamentos": "kits", "higiene": "kits",
            "abrigo_vivienda": "kits", "otro": "unidades"}

VULNERABILIDADES = [
    ("discapacidad", 0.25, "Persona con movilidad reducida que no puede salir sola de la vivienda.",
     "Silla de ruedas o apoyo para traslado"),
    ("adulto_mayor", 0.30, "Adulto mayor que vive solo y necesita ayuda para conseguir alimentos.",
     "Alimentos blandos y acompañamiento"),
    ("menor", 0.15, "Hogar con niños pequeños sin acceso a leche ni pañales.", "Fórmula láctea y pañales"),
    ("embarazo", 0.10, "Mujer en embarazo que requiere control médico y alimentación.", "Atención prenatal"),
    ("cronica", 0.15, "Persona con enfermedad crónica sin su medicación.", "Medicamentos de uso continuo"),
    ("otra", 0.05, "Situación especial descrita por el solicitante.", "A definir en la verificación"),
]

PESOS_INICIALES = {
    "barrio": {"gravedad": 0.30, "urgencia": 0.25, "expuestas": 0.25, "accesibilidad": 0.10, "recursos": 0.10},
    "solicitud": {"urgencia": 0.30, "vulnerabilidad": 0.25, "personas_hogar": 0.15, "tiempo_espera": 0.15,
                  "prioridad_barrio": 0.15},
    "confianza": {"fuente": 0.35, "verificacion": 0.30, "vigencia": 0.15, "corroboracion": 0.20},
}


# ----------------------------------------------------------------------------- utilidades
def _persona(rng: np.random.Generator) -> str:
    return f"{NOMBRES[rng.integers(len(NOMBRES))]} {APELLIDOS[rng.integers(len(APELLIDOS))]} {APELLIDOS[rng.integers(len(APELLIDOS))]}"


def _telefono(rng: np.random.Generator) -> str:
    return "999" + "".join(str(d) for d in rng.integers(0, 10, 7))  # no es un celular colombiano válido


def _documento(rng: np.random.Generator) -> str:
    return "SIM-" + "".join(str(d) for d in rng.integers(0, 10, 8))


def _jitter(rng, lat, lon, grados=0.004):
    return float(lat + rng.normal(0, grados)), float(lon + rng.normal(0, grados))


def _datos_de_cuentas_reales(db: Session, ids: list[int]) -> dict[str, int]:
    """Cuántos registros hicieron las cuentas reales. Si hay alguno, renovar la simulación podría dañarlos."""
    def contar(consulta) -> int:
        return db.scalar(select(func.count()).select_from(consulta.subquery())) or 0

    return {k: v for k, v in {
        "solicitudes": contar(select(m.Solicitud.id).where(m.Solicitud.solicitante_id.in_(ids) | m.Solicitud.creador_id.in_(ids))),
        "reportes de daños": contar(select(m.ReporteDanos.id).where(m.ReporteDanos.autor_id.in_(ids))),
        "donaciones": contar(select(m.Donacion.id).join(m.Donante, m.Donante.id == m.Donacion.donante_id)
                             .where(m.Donante.usuario_id.in_(ids))),
        "verificaciones": contar(select(m.Verificacion.id).where(m.Verificacion.verificador_id.in_(ids))),
        "entregas": contar(select(m.Entrega.id).where(m.Entrega.equipo_id.in_(ids))),
        "planes aprobados": contar(select(m.PlanAsignacion.id).where(m.PlanAsignacion.aprobado_por.in_(ids))),
        "movimientos de inventario": contar(select(m.MovimientoInventario.id).where(m.MovimientoInventario.usuario_id.in_(ids))),
    }.items() if v}


def limpiar_simulacion(db: Session, conservar_cuentas: bool = False) -> dict:
    """Borra todo lo simulado (RF-50), menos los municipios, las proyecciones y los datos oficiales.

    Por seguridad se niega a actuar si ya hay cuentas reales: borraría sus solicitudes y sus datos.
    Con `conservar_cuentas` se permite renovar la simulación aunque haya cuentas reales, siempre que todavía no
    hayan hecho nada (ni solicitudes, ni reportes, ni donaciones, ni verificaciones, ni entregas). Las cuentas, su
    historial, los centros de acopio que administran y los pesos que cambiaron se conservan. Devuelve en qué barrio
    estaba cada cuenta y cada centro, para volver a ubicarlos cuando se genere de nuevo."""
    reales = db.scalars(select(m.Usuario).where(m.Usuario.ficticio.is_(False))).all()
    if reales and not conservar_cuentas:
        raise RuntimeError("Hay cuentas reales: reiniciar la simulación borraría datos de personas. "
                           "Use generar(..., reiniciar=False) o limpie la base de desarrollo.")
    ids = [u.id for u in reales]
    if ids:
        hecho = _datos_de_cuentas_reales(db, ids)
        if hecho:
            detalle = ", ".join(f"{n} {k}" for k, n in hecho.items())
            raise RuntimeError(f"Las cuentas reales ya tienen datos ({detalle}): renovar la simulación podría borrarlos.")
    nombre_barrio = {s.id: (s.municipio_codigo, s.nombre) for s in db.scalars(select(m.Barrio))}
    centros_reales = db.scalars(select(m.CentroAcopio).where(m.CentroAcopio.responsable_id.in_(ids))).all() if ids else []
    donde = {"usuarios": {u.id: nombre_barrio.get(u.barrio_id) for u in reales if u.barrio_id},
             "centros": {c.id: nombre_barrio.get(c.barrio_id) for c in centros_reales if c.barrio_id}}
    for u in reales:  # se sueltan de los barrios que se van a borrar; luego se vuelven a ubicar por nombre
        u.barrio_id = None
    for c in centros_reales:
        c.barrio_id = None
    db.flush()

    simulados = select(m.Usuario.id).where(m.Usuario.ficticio.is_(True))
    db.execute(delete(m.Bitacora).where(m.Bitacora.usuario_id.is_(None) | m.Bitacora.usuario_id.in_(simulados)))
    for modelo in (
        m.MovimientoInventario, m.PlanResumen, m.PlanLinea, m.PlanAsignacion, m.Incidencia, m.Entrega,
        m.Verificacion, m.Vulnerabilidad, m.Lote, m.Donacion, m.Solicitud,
        m.ReporteDanos, m.PuntajeBarrio, m.EventoAuditoria,
    ):
        db.execute(delete(modelo))
    db.execute(delete(m.Donante).where(m.Donante.usuario_id.is_(None) | m.Donante.usuario_id.in_(simulados)))  # los reales se conservan
    conservados = [c.id for c in centros_reales]
    db.execute(delete(m.CentroAcopio).where(m.CentroAcopio.id.not_in(conservados)) if conservados
               else delete(m.CentroAcopio))
    db.execute(delete(m.Peso).where(m.Peso.actualizado_por.is_(None) | m.Peso.actualizado_por.in_(simulados)))
    db.execute(delete(m.Usuario).where(m.Usuario.ficticio.is_(True)))
    db.execute(delete(m.Evento))
    db.execute(delete(m.Barrio))
    db.flush()
    return donde


def reubicar_cuentas(db: Session, donde: dict, barrios: list[m.Barrio]) -> None:
    """Vuelve a poner cada cuenta real y cada centro conservado en el barrio que tenía, buscándolo por municipio y nombre."""
    por_nombre = {(s.municipio_codigo, s.nombre): s.id for s in barrios}
    for uid, nombre in donde.get("usuarios", {}).items():
        db.get(m.Usuario, uid).barrio_id = por_nombre.get(nombre)
    for cid, nombre in donde.get("centros", {}).items():
        db.get(m.CentroAcopio, cid).barrio_id = por_nombre.get(nombre)
    db.flush()


# ----------------------------------------------------------------------------- barrios
def crear_barrios(db: Session, rng, municipios: list[str], viviendas_por_barrio: int = 5000) -> list[m.Barrio]:
    """Crea los barrios reales de cada municipio (data/barrios_atlantico.csv). Lo que se simula es cuántas viviendas
    tiene cada uno, su vulnerabilidad, su amenaza y su acceso; la suma de viviendas coincide con la cifra municipal."""
    del viviendas_por_barrio  # ya no se inventan barrios: se usan los del archivo
    del_archivo = leer_barrios()
    barrios: list[m.Barrio] = []
    for codigo in municipios:
        nombre = MUNICIPIOS[codigo]
        lugares = del_archivo.get(codigo, [])
        if not lugares:
            raise RuntimeError(f"No hay barrios de {nombre} en data/barrios_atlantico.csv.")
        solo_poblados = all(x["tipo"] != "barrio" for x in lugares)
        total = db.scalar(
            select(m.ViviendaProyeccion.viviendas).where(
                m.ViviendaProyeccion.municipio_codigo == codigo,
                m.ViviendaProyeccion.area == ("Total" if solo_poblados else "Cabecera"),
                m.ViviendaProyeccion.anio == 2026,
            )
        )
        if total is None:
            raise RuntimeError(f"Faltan las proyecciones de viviendas de {nombre}: cargarlas con `python -m app.cargas`.")
        n = len(lugares)
        partes = rng.dirichlet(np.full(n, 4.0)) * total
        viv = np.floor(partes).astype(int)
        viv[: total - viv.sum()] += 1  # el resto se reparte para que la suma sea exacta
        for i, lugar in enumerate(lugares):
            barrios.append(
                m.Barrio(
                    municipio_codigo=codigo, nombre=lugar["nombre"], tipo=lugar["tipo"],
                    lat=lugar["lat"], lon=lugar["lon"],
                    viviendas=int(viv[i]),
                    personas=int(viv[i] * float(np.clip(rng.normal(3.4, 0.4), 2.2, 4.5))),
                    vulnerabilidad_base=round(float(rng.beta(2, 5)), 3),
                    amenaza_base=round(float(rng.beta(2, 4)), 3),
                    acceso_base=round(float(rng.beta(6, 2)), 3),
                    simulado=True,
                )
            )
    db.add_all(barrios)
    db.flush()
    return barrios


# ----------------------------------------------------------------------------- evento y daño verdadero
def _dano_verdadero(tipo: str, barrios: list[m.Barrio], intensidad: float, rng) -> tuple[np.ndarray, dict]:
    """Daño real (0 a 1) de cada barrio, que los reportes después observan con ruido."""
    lat = np.array([s.lat for s in barrios])
    lon = np.array([s.lon for s in barrios])
    vul = np.array([s.vulnerabilidad_base for s in barrios])
    amen = np.array([s.amenaza_base for s in barrios])

    if tipo == "terremoto":  # foco puntual con atenuación por la distancia
        foco = rng.integers(len(barrios))
        r0 = rng.uniform(0.05, 0.10)
        dist = np.hypot(lat - lat[foco], lon - lon[foco])
        d = intensidad * np.exp(-dist / r0) * (0.7 + 0.6 * vul)
        zona = {"lat": float(lat[foco]), "lon": float(lon[foco]), "radio_km": float(r0 * 111)}
    elif tipo == "inundacion":  # zonas bajas: sigue a la amenaza de base
        d = intensidad * (1.6 * amen + 0.2 * rng.normal(size=len(barrios)))
        zona = {"lat": float(lat.mean()), "lon": float(lon.mean()), "radio_km": 25.0}
    elif tipo == "vendaval":  # franja amplia que cruza el área
        theta = rng.uniform(0, math.pi)
        cx, cy = lon.mean(), lat.mean()
        perp = np.abs((lon - cx) * math.sin(theta) - (lat - cy) * math.cos(theta))
        ancho = 0.04
        d = intensidad * np.exp(-((perp / ancho) ** 2)) * (0.6 + 0.8 * vul)
        zona = {"lat": float(cy), "lon": float(cx), "radio_km": float(ancho * 111), "angulo": float(theta)}
    elif tipo == "deslizamiento":  # focos localizados en barrios de alta amenaza
        k = min(5, len(barrios))
        focos = np.argsort(-amen)[:k]
        d = np.zeros(len(barrios))
        for f in focos:
            d = np.maximum(d, np.exp(-np.hypot(lat - lat[f], lon - lon[f]) / 0.015))
        d = intensidad * d * (0.5 + amen)
        zona = {"lat": float(lat[focos[0]]), "lon": float(lon[focos[0]]), "radio_km": 2.0}
    else:
        raise ValueError(f"Tipo de evento desconocido: {tipo}")
    d = np.clip(d + rng.normal(0, 0.02, len(barrios)), 0, 1)
    return d, zona


# ----------------------------------------------------------------------------- usuarios
class _Usuarios:
    """Crea usuarios ficticios de cada rol y los reparte entre los barrios."""

    def __init__(self, db: Session, rng, barrios: list[m.Barrio]):
        self.db, self.rng, self.barrios = db, rng, barrios
        self.ciudadanos: dict[int, list[m.Usuario]] = {}

    def nuevo(self, rol: str, barrio: m.Barrio | None = None, **extra) -> m.Usuario:
        u = m.Usuario(
            nombre=_persona(self.rng), telefono=_telefono(self.rng),
            documento=_documento(self.rng) if self.rng.random() < 0.6 else None,
            rol=rol, barrio_id=barrio.id if barrio else None,
            consentimiento_datos=True, consentimiento_fecha=BASE_FECHA, ficticio=True,
            creado_en=BASE_FECHA, **extra,
        )
        self.db.add(u)
        self.db.flush()
        return u

    def ciudadano(self, barrio: m.Barrio) -> m.Usuario:
        pool = self.ciudadanos.setdefault(barrio.id, [])
        if pool and self.rng.random() < 0.5:
            return pool[self.rng.integers(len(pool))]
        u = self.nuevo(m.Rol.SOLICITANTE, barrio)
        pool.append(u)
        return u


# ----------------------------------------------------------------------------- reportes y solicitudes
SD_RUIDO = {m.Rol.SOLICITANTE: 0.8, m.Rol.BRIGADISTA: 0.35, m.Rol.ENTIDAD: 0.25}


def crear_reportes(db, rng, evento, barrios, dano, usuarios, brigadistas, entidades, verdad) -> int:
    p90 = np.percentile([s.personas for s in barrios], 90)
    total = 0
    for s, d in zip(barrios, dano):
        # Quién reporta: más donde hay más población y daño (sesgo conocido de las fuentes ciudadanas)
        p_cobertura = float(np.clip(0.25 + 0.5 * d + 0.2 * min(1.0, s.personas / p90), 0, 0.95))
        if rng.random() > p_cobertura:
            continue  # barrio sin reportes: información faltante
        n = 1 + rng.poisson(3 * d)
        for _ in range(n):
            r = rng.random()
            if r < 0.6:
                rol, autor = m.Rol.SOLICITANTE, usuarios.ciudadano(s)
            elif r < 0.9:
                rol, autor = m.Rol.BRIGADISTA, brigadistas[rng.integers(len(brigadistas))]
            else:
                rol, autor = m.Rol.ENTIDAD, entidades[rng.integers(len(entidades))]
            nivel = int(np.clip(round(3 * d + rng.normal(0, SD_RUIDO[rol])), 0, 3))
            falso = rol == m.Rol.SOLICITANTE and rng.random() < 0.03
            if falso:  # reporte contradictorio o falso
                nivel = int((nivel + rng.integers(1, 3)) % 4)
            tipo_perdida = 0.7 if evento.tipo != "vendaval" else 0.3
            acceso = float(np.clip(s.acceso_base * (1 - tipo_perdida * d) + rng.normal(0, 0.05), 0, 1))
            fila = m.ReporteDanos(
                barrio_id=s.id, evento_id=evento.id, autor_id=autor.id,
                fuente=m.FuenteReporte.PAPEL if (rol == m.Rol.BRIGADISTA and rng.random() < 0.08) else m.FuenteReporte.APP,
                hora_evento=evento.fecha,
                hora_captura=evento.fecha + timedelta(hours=min(12.0, float(rng.exponential(4)))),  # primeras 12 h
                nivel_dano=nivel,
                personas_afectadas=int(d * s.personas * rng.uniform(0.2, 0.6)),
                acceso=round(acceso, 3),
            )
            db.add(fila)
            db.flush()
            if falso:
                verdad["reportes_falsos"].append(fila.id)
            total += 1
    return total


def crear_solicitudes(db, rng, evento, barrios, dano, usuarios, brigadistas, verdad) -> int:
    perfil = PERFIL_NECESIDAD[evento.tipo]
    total = 0
    for s, d in zip(barrios, dano):
        if d < 0.15:
            continue
        n = min(12, int(rng.poisson(d * s.personas / 1000 * 1.2)))
        for _ in range(n):
            solicitante = usuarios.nuevo(m.Rol.SOLICITANTE, s)
            creador = solicitante if rng.random() < 0.85 else brigadistas[rng.integers(len(brigadistas))]
            necesidad = NECESIDADES[rng.choice(len(NECESIDADES), p=perfil)]
            hogar = int(np.clip(rng.poisson(3) + 1, 1, 9))
            falsa = rng.random() < 0.02
            urgencia = 3 if falsa else int(np.clip(round(3 * d + rng.normal(0, 0.7)), 0, 3))
            la, lo = _jitter(rng, s.lat, s.lon)
            sol = m.Solicitud(
                solicitante_id=solicitante.id, creador_id=creador.id, barrio_id=s.id, evento_id=evento.id,
                necesidad=necesidad, personas_hogar=hogar,
                cantidad=hogar * UNIDAD_POR_PERSONA[necesidad] * (3 if falsa else 1),
                descripcion=f"Necesita {necesidad.replace('_', ' ')} para {hogar} persona(s) tras el evento.",
                urgencia=urgencia, direccion=f"Calle {rng.integers(1, 99)} # {rng.integers(1, 99)}-{rng.integers(1, 99)}",
                lat=la, lon=lo,
                fuente=m.FuenteReporte.PAPEL if creador is not solicitante and rng.random() < 0.5 else m.FuenteReporte.APP,
                creado_en=evento.fecha + timedelta(hours=min(18.0, float(rng.exponential(6)))),
            )
            db.add(sol)
            db.flush()
            if falsa:
                verdad["solicitudes_falsas"].append(sol.id)
            if rng.random() < (0.1 if falsa else 0.4):  # parte ya la revisó un brigadista en campo
                revisor = brigadistas[rng.integers(len(brigadistas))]
                db.add(m.Verificacion(objeto_tipo="solicitud", objeto_id=sol.id, verificador_id=revisor.id,
                                      resultado="verificado", nota="Verificación simulada",
                                      hora=sol.creado_en + timedelta(hours=2)))
                sol.estado = m.EstadoSolicitud.VERIFICADA

            if rng.random() < 0.15 + 0.2 * s.vulnerabilidad_base:  # persona vulnerable, con consentimiento
                tipos = [v[0] for v in VULNERABILIDADES]
                pesos = np.array([v[1] for v in VULNERABILIDADES])
                v = VULNERABILIDADES[rng.choice(len(tipos), p=pesos / pesos.sum())]
                db.add(m.Vulnerabilidad(
                    solicitud_id=sol.id, tipo=v[0], descripcion_situacion=v[2], necesidad_especifica=v[3],
                    consentimiento=True, consentimiento_fecha=sol.creado_en,
                ))

            if rng.random() < 0.04:  # el mismo documento, teléfono y dirección, registrado otra vez
                otro = m.Usuario(
                    nombre=solicitante.nombre, telefono=solicitante.telefono,
                    documento=solicitante.documento or _documento(rng), rol=m.Rol.SOLICITANTE,
                    barrio_id=s.id, consentimiento_datos=True, consentimiento_fecha=BASE_FECHA, ficticio=True,
                    creado_en=BASE_FECHA,
                )
                db.add(otro)
                db.flush()
                copia = m.Solicitud(
                    solicitante_id=otro.id, creador_id=otro.id, barrio_id=s.id, evento_id=evento.id,
                    necesidad=sol.necesidad, personas_hogar=sol.personas_hogar, cantidad=sol.cantidad,
                    descripcion=sol.descripcion, urgencia=sol.urgencia, direccion=sol.direccion,
                    lat=sol.lat, lon=sol.lon, fuente=m.FuenteReporte.APP,
                    creado_en=sol.creado_en + timedelta(hours=float(rng.uniform(1, 3))),
                )
                db.add(copia)
                db.flush()
                verdad["duplicadas"].append([sol.id, copia.id])
                total += 1
            total += 1
    return total


# ----------------------------------------------------------------------------- donaciones e inventario
def crear_apoyo(db, rng, evento, barrios, usuarios, verdad) -> dict:
    """Centros de acopio, donantes, donaciones y lotes. La oferta es una fracción de la demanda simulada."""
    solicitudes = db.scalars(select(m.Solicitud)).all()
    demanda = {t: 0 for t in NECESIDADES}
    for sol in solicitudes:
        demanda[sol.necesidad] += sol.cantidad

    grandes = sorted(barrios, key=lambda s: -s.viviendas)[:4]
    centros = []
    for i, s in enumerate(grandes):
        resp = usuarios.nuevo(m.Rol.CENTRO_ACOPIO, s)
        c = m.CentroAcopio(nombre=f"Centro de acopio {i + 1} ({s.nombre})", barrio_id=s.id, lat=s.lat, lon=s.lon,
                           responsable_id=resp.id)
        db.add(c)
        centros.append(c)
    db.flush()

    donantes = []
    for _ in range(24):
        tipo = ["persona", "organizacion", "empresa"][rng.choice(3, p=[0.5, 0.3, 0.2])]
        u = usuarios.nuevo(m.Rol.DONANTE)
        d = m.Donante(usuario_id=u.id, nombre=u.nombre if tipo == "persona" else f"Organización simulada {u.id}",
                      tipo=tipo, contacto=u.telefono, nombre_publico=bool(rng.random() < 0.8), consentimiento=True)
        db.add(d)
        donantes.append(d)
    db.flush()

    n_lotes = n_monetarias = 0
    for tipo in NECESIDADES:
        oferta = int(demanda[tipo] * rng.uniform(0.5, 0.9))
        if oferta <= 0:
            continue
        k = int(rng.integers(3, 9))
        partes = np.maximum(1, (rng.dirichlet(np.ones(k)) * oferta).astype(int))
        for cantidad in partes:
            donante = donantes[rng.integers(len(donantes))]
            centro = centros[rng.integers(len(centros))]
            perecedero = tipo in ("alimentos", "medicamentos")
            venc = None
            if perecedero:
                dias = float(rng.uniform(2, 6)) if rng.random() < 0.15 else float(rng.uniform(30, 365))
                venc = evento.fecha + timedelta(days=dias)
            dirigida = rng.random() < 0.10
            destino_barrio = int(rng.choice([s.id for s in barrios])) if dirigida and rng.random() < 0.5 else None
            destino_tipo = tipo if dirigida and destino_barrio is None else None
            recibida = rng.random() > 0.08  # algunas siguen solo ofrecidas
            don = m.Donacion(
                donante_id=donante.id, centro_id=centro.id, tipo_bien=tipo, cantidad=int(cantidad),
                unidad=UNIDADES[tipo], vencimiento=venc, destino_barrio_id=destino_barrio,
                destino_tipo_necesidad=destino_tipo,
                estado=m.EstadoDonacion.EN_INVENTARIO if recibida else m.EstadoDonacion.OFRECIDA,
                creado_en=evento.fecha + timedelta(hours=min(24.0, float(rng.exponential(10)))),
            )
            db.add(don)
            db.flush()
            if recibida:
                lote = m.Lote(
                    donacion_id=don.id, centro_id=centro.id, tipo_bien=tipo, unidad=UNIDADES[tipo],
                    cantidad_recibida=int(cantidad), cantidad_disponible=int(cantidad), vencimiento=venc,
                    destino_barrio_id=destino_barrio, destino_tipo_necesidad=destino_tipo,
                )
                db.add(lote)
                db.flush()
                db.add(m.MovimientoInventario(lote_id=lote.id, tipo="recepcion", cantidad=int(cantidad),
                                              usuario_id=centro.responsable_id, hora=don.creado_en))
                n_lotes += 1
    for _ in range(int(rng.integers(2, 5))):  # donaciones monetarias: solo constancia, sin pagos
        donante = donantes[rng.integers(len(donantes))]
        db.add(m.Donacion(donante_id=donante.id, tipo_bien="otro", monetaria=True,
                          monto=int(rng.integers(5, 200)) * 10_000, cantidad=0, unidad="COP",
                          estado=m.EstadoDonacion.RECIBIDA, creado_en=evento.fecha))
        n_monetarias += 1
    db.flush()
    return {"centros": len(centros), "donantes": len(donantes), "lotes": n_lotes, "monetarias": n_monetarias,
            "demanda": demanda}


def sembrar_pesos(db: Session) -> int:
    """Pesos iniciales. Los que ya existan (por ejemplo, los que cambió una cuenta real) no se tocan."""
    existentes = {(p.ambito, p.dimension) for p in db.scalars(select(m.Peso))}
    n = 0
    for ambito, dims in PESOS_INICIALES.items():
        for dimension, valor in dims.items():
            if (ambito, dimension) in existentes:
                continue
            db.add(m.Peso(ambito=ambito, dimension=dimension, valor=valor))
            n += 1
    db.flush()
    return n


# ----------------------------------------------------------------------------- orquestación
def generar(db: Session, semilla: int = 42, tipo: str = "inundacion", municipios: list[str] | None = None,
            reiniciar: bool = True, conservar_cuentas: bool = False) -> dict:
    """Genera un escenario completo. Devuelve un resumen con los conteos."""
    rng = np.random.default_rng(semilla)
    municipios = municipios or list(MUNICIPIOS)
    donde = limpiar_simulacion(db, conservar_cuentas) if reiniciar else {}

    barrios = crear_barrios(db, rng, municipios)
    reubicar_cuentas(db, donde, barrios)
    intensidad = float(rng.uniform(0.6, 1.0))
    dano, zona = _dano_verdadero(tipo, barrios, intensidad, rng)
    evento = m.Evento(tipo=tipo, nombre=f"{tipo.capitalize()} simulado (semilla {semilla})", fecha=BASE_FECHA,
                      zona=zona, intensidad=round(intensidad, 3), origen=m.OrigenDato.SIMULADO, semilla=semilla)
    db.add(evento)
    db.flush()

    usuarios = _Usuarios(db, rng, barrios)
    admin = usuarios.nuevo(m.Rol.ADMINISTRADOR)
    entidades = [usuarios.nuevo(m.Rol.ENTIDAD) for _ in range(2)]
    brigadistas = [usuarios.nuevo(m.Rol.BRIGADISTA, barrios[rng.integers(len(barrios))]) for _ in range(30)]
    equipos = [usuarios.nuevo(m.Rol.EQUIPO_ENTREGA, es_organizacion=bool(i % 2), aprobado=(i != 5)) for i in range(6)]

    verdad = {"semilla": semilla, "tipo": tipo, "reportes_falsos": [], "solicitudes_falsas": [], "duplicadas": [],
              "dano": {s.id: round(float(d), 3) for s, d in zip(barrios, dano)}}

    n_reportes = crear_reportes(db, rng, evento, barrios, dano, usuarios, brigadistas, entidades, verdad)
    n_solicitudes = crear_solicitudes(db, rng, evento, barrios, dano, usuarios, brigadistas, verdad)
    apoyo = crear_apoyo(db, rng, evento, barrios, usuarios, verdad)
    n_pesos = sembrar_pesos(db)

    # La verdad del escenario queda guardada para poder medir luego qué tan bien se recupera (validación sintética)
    db.add(m.Bitacora(usuario_id=admin.id, accion="simulacion_verdad", objeto=f"evento:{evento.id}", detalle=verdad,
                      hora=BASE_FECHA))
    db.commit()
    return {
        "semilla": semilla, "tipo": tipo, "evento_id": evento.id, "barrios": len(barrios),
        "viviendas": sum(s.viviendas for s in barrios), "reportes": n_reportes, "solicitudes": n_solicitudes,
        "equipos": len(equipos), "brigadistas": len(brigadistas), "pesos": n_pesos, **apoyo,
    }


if __name__ == "__main__":
    from app.db import SessionLocal, crear_tablas

    ap = argparse.ArgumentParser(description="Genera un escenario simulado.")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tipo", default="inundacion", choices=list(PERFIL_NECESIDAD))
    ap.add_argument("--no-reiniciar", action="store_true", help="no borra los datos simulados anteriores")
    args = ap.parse_args()
    crear_tablas()
    with SessionLocal() as sesion:
        print(generar(sesion, semilla=args.seed, tipo=args.tipo, reiniciar=not args.no_reiniciar))
