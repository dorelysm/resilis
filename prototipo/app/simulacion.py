"""Generador de datos simulados (bloque 2 del plan).

Todo es ficticio y reproducible: con la misma semilla se obtienen los mismos datos. Lo único real son las
viviendas proyectadas por municipio, que sirven de ancla: las viviendas de los sectores simulados suman la cifra
municipal (RD-09). Los daños, las personas, los reportes, las solicitudes, las donaciones y el inventario se
simulan (RD-10 a RD-13, RD-22 de los requisitos).

Uso:  uv run python -m app.simulacion --seed 42 --tipo inundacion
"""
import argparse
import math
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import models as m

BASE_FECHA = datetime(2026, 10, 16, 8, 0, tzinfo=timezone.utc)  # fija, para que el resultado se repita

# Centros aproximados (lat, lon, dispersión en grados). Son referencias para ubicar sectores simulados,
# no datos oficiales.
MUNICIPIOS = {
    "08001": ("Barranquilla", 10.9685, -74.7813, 0.060),
    "08758": ("Soledad", 10.9184, -74.7646, 0.040),
    "08433": ("Malambo", 10.8596, -74.7737, 0.025),
    "08296": ("Galapa", 10.8967, -74.8864, 0.020),
    "08573": ("Puerto Colombia", 10.9878, -74.9547, 0.020),
    "08078": ("Baranoa", 10.7942, -74.9158, 0.020),
    "08638": ("Sabanalarga", 10.6317, -74.9214, 0.025),
}

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
    "sector": {"gravedad": 0.30, "urgencia": 0.25, "expuestas": 0.25, "accesibilidad": 0.10, "recursos": 0.10},
    "solicitud": {"urgencia": 0.30, "vulnerabilidad": 0.25, "personas_hogar": 0.15, "tiempo_espera": 0.15,
                  "prioridad_sector": 0.15},
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


def limpiar_simulacion(db: Session, conservar_administradores: bool = False) -> None:
    """Borra todo lo simulado (RF-50), menos los municipios, las proyecciones y los datos oficiales.

    Por seguridad se niega a actuar si ya hay cuentas reales: borraría sus solicitudes y sus datos.
    Con `conservar_administradores` se permite una sola excepción: que las únicas cuentas reales sean de
    administradores. Esas cuentas y su historial se conservan (sirve para renovar la demostración en producción
    después de crear el primer administrador, y antes de crear otras cuentas)."""
    reales = db.scalars(select(m.Usuario).where(m.Usuario.ficticio.is_(False))).all()
    if reales and not (conservar_administradores and all(u.rol == m.Rol.ADMINISTRADOR for u in reales)):
        raise RuntimeError("Hay cuentas reales: reiniciar la simulación borraría datos de personas. "
                           "Use generar(..., reiniciar=False) o limpie la base de desarrollo.")
    simulados = select(m.Usuario.id).where(m.Usuario.ficticio.is_(True))
    db.execute(delete(m.Bitacora).where(m.Bitacora.usuario_id.is_(None) | m.Bitacora.usuario_id.in_(simulados)))
    for modelo in (
        m.MovimientoInventario, m.PlanResumen, m.PlanLinea, m.PlanAsignacion, m.Incidencia, m.Entrega,
        m.Verificacion, m.Vulnerabilidad, m.Lote, m.Donacion, m.Donante, m.CentroAcopio, m.Solicitud,
        m.ReporteDanos, m.PuntajeSector, m.EventoAuditoria, m.Peso,
    ):
        db.execute(delete(modelo))
    db.execute(delete(m.Usuario).where(m.Usuario.ficticio.is_(True)))
    db.execute(delete(m.Evento))
    db.execute(delete(m.Sector))
    db.flush()


# ----------------------------------------------------------------------------- sectores
def crear_sectores(db: Session, rng, municipios: list[str], viviendas_por_sector: int = 5000) -> list[m.Sector]:
    sectores: list[m.Sector] = []
    for codigo in municipios:
        nombre, lat, lon, dispersion = MUNICIPIOS[codigo]
        total = db.scalar(
            select(m.ViviendaProyeccion.viviendas).where(
                m.ViviendaProyeccion.municipio_codigo == codigo,
                m.ViviendaProyeccion.area == "Cabecera",
                m.ViviendaProyeccion.anio == 2026,
            )
        )
        if total is None:
            raise RuntimeError(f"Faltan las proyecciones de viviendas de {nombre}: cargarlas con `python -m app.cargas`.")
        n = max(3, round(total / viviendas_por_sector))
        partes = rng.dirichlet(np.full(n, 4.0)) * total
        viv = np.floor(partes).astype(int)
        viv[: total - viv.sum()] += 1  # el resto se reparte para que la suma sea exacta
        for i in range(n):
            la, lo = _jitter(rng, lat, lon, dispersion)
            sectores.append(
                m.Sector(
                    municipio_codigo=codigo,
                    nombre=f"{nombre} - Sector {i + 1:02d}",
                    lat=la, lon=lo,
                    viviendas=int(viv[i]),
                    personas=int(viv[i] * float(np.clip(rng.normal(3.4, 0.4), 2.2, 4.5))),
                    vulnerabilidad_base=round(float(rng.beta(2, 5)), 3),
                    amenaza_base=round(float(rng.beta(2, 4)), 3),
                    acceso_base=round(float(rng.beta(6, 2)), 3),
                    simulado=True,
                )
            )
    db.add_all(sectores)
    db.flush()
    return sectores


# ----------------------------------------------------------------------------- evento y daño verdadero
def _dano_verdadero(tipo: str, sectores: list[m.Sector], intensidad: float, rng) -> tuple[np.ndarray, dict]:
    """Daño real (0 a 1) de cada sector, que los reportes después observan con ruido."""
    lat = np.array([s.lat for s in sectores])
    lon = np.array([s.lon for s in sectores])
    vul = np.array([s.vulnerabilidad_base for s in sectores])
    amen = np.array([s.amenaza_base for s in sectores])

    if tipo == "terremoto":  # foco puntual con atenuación por la distancia
        foco = rng.integers(len(sectores))
        r0 = rng.uniform(0.05, 0.10)
        dist = np.hypot(lat - lat[foco], lon - lon[foco])
        d = intensidad * np.exp(-dist / r0) * (0.7 + 0.6 * vul)
        zona = {"lat": float(lat[foco]), "lon": float(lon[foco]), "radio_km": float(r0 * 111)}
    elif tipo == "inundacion":  # zonas bajas: sigue a la amenaza de base
        d = intensidad * (1.6 * amen + 0.2 * rng.normal(size=len(sectores)))
        zona = {"lat": float(lat.mean()), "lon": float(lon.mean()), "radio_km": 25.0}
    elif tipo == "vendaval":  # franja amplia que cruza el área
        theta = rng.uniform(0, math.pi)
        cx, cy = lon.mean(), lat.mean()
        perp = np.abs((lon - cx) * math.sin(theta) - (lat - cy) * math.cos(theta))
        ancho = 0.04
        d = intensidad * np.exp(-((perp / ancho) ** 2)) * (0.6 + 0.8 * vul)
        zona = {"lat": float(cy), "lon": float(cx), "radio_km": float(ancho * 111), "angulo": float(theta)}
    elif tipo == "deslizamiento":  # focos localizados en sectores de alta amenaza
        k = min(5, len(sectores))
        focos = np.argsort(-amen)[:k]
        d = np.zeros(len(sectores))
        for f in focos:
            d = np.maximum(d, np.exp(-np.hypot(lat - lat[f], lon - lon[f]) / 0.015))
        d = intensidad * d * (0.5 + amen)
        zona = {"lat": float(lat[focos[0]]), "lon": float(lon[focos[0]]), "radio_km": 2.0}
    else:
        raise ValueError(f"Tipo de evento desconocido: {tipo}")
    d = np.clip(d + rng.normal(0, 0.02, len(sectores)), 0, 1)
    return d, zona


# ----------------------------------------------------------------------------- usuarios
class _Usuarios:
    """Crea usuarios ficticios de cada rol y los reparte entre los sectores."""

    def __init__(self, db: Session, rng, sectores: list[m.Sector]):
        self.db, self.rng, self.sectores = db, rng, sectores
        self.ciudadanos: dict[int, list[m.Usuario]] = {}

    def nuevo(self, rol: str, sector: m.Sector | None = None, **extra) -> m.Usuario:
        u = m.Usuario(
            nombre=_persona(self.rng), telefono=_telefono(self.rng),
            documento=_documento(self.rng) if self.rng.random() < 0.6 else None,
            rol=rol, sector_id=sector.id if sector else None,
            consentimiento_datos=True, consentimiento_fecha=BASE_FECHA, ficticio=True,
            creado_en=BASE_FECHA, **extra,
        )
        self.db.add(u)
        self.db.flush()
        return u

    def ciudadano(self, sector: m.Sector) -> m.Usuario:
        pool = self.ciudadanos.setdefault(sector.id, [])
        if pool and self.rng.random() < 0.5:
            return pool[self.rng.integers(len(pool))]
        u = self.nuevo(m.Rol.SOLICITANTE, sector)
        pool.append(u)
        return u


# ----------------------------------------------------------------------------- reportes y solicitudes
SD_RUIDO = {m.Rol.SOLICITANTE: 0.8, m.Rol.BRIGADISTA: 0.35, m.Rol.ENTIDAD: 0.25}


def crear_reportes(db, rng, evento, sectores, dano, usuarios, brigadistas, entidades, verdad) -> int:
    p90 = np.percentile([s.personas for s in sectores], 90)
    total = 0
    for s, d in zip(sectores, dano):
        # Quién reporta: más donde hay más población y daño (sesgo conocido de las fuentes ciudadanas)
        p_cobertura = float(np.clip(0.25 + 0.5 * d + 0.2 * min(1.0, s.personas / p90), 0, 0.95))
        if rng.random() > p_cobertura:
            continue  # sector sin reportes: información faltante
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
                sector_id=s.id, evento_id=evento.id, autor_id=autor.id,
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


def crear_solicitudes(db, rng, evento, sectores, dano, usuarios, brigadistas, verdad) -> int:
    perfil = PERFIL_NECESIDAD[evento.tipo]
    total = 0
    for s, d in zip(sectores, dano):
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
                solicitante_id=solicitante.id, creador_id=creador.id, sector_id=s.id, evento_id=evento.id,
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
                    sector_id=s.id, consentimiento_datos=True, consentimiento_fecha=BASE_FECHA, ficticio=True,
                    creado_en=BASE_FECHA,
                )
                db.add(otro)
                db.flush()
                copia = m.Solicitud(
                    solicitante_id=otro.id, creador_id=otro.id, sector_id=s.id, evento_id=evento.id,
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
def crear_apoyo(db, rng, evento, sectores, usuarios, verdad) -> dict:
    """Centros de acopio, donantes, donaciones y lotes. La oferta es una fracción de la demanda simulada."""
    solicitudes = db.scalars(select(m.Solicitud)).all()
    demanda = {t: 0 for t in NECESIDADES}
    for sol in solicitudes:
        demanda[sol.necesidad] += sol.cantidad

    grandes = sorted(sectores, key=lambda s: -s.viviendas)[:4]
    centros = []
    for i, s in enumerate(grandes):
        resp = usuarios.nuevo(m.Rol.CENTRO_ACOPIO, s)
        c = m.CentroAcopio(nombre=f"Centro de acopio {i + 1} ({s.nombre})", sector_id=s.id, lat=s.lat, lon=s.lon,
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
            destino_sector = int(rng.choice([s.id for s in sectores])) if dirigida and rng.random() < 0.5 else None
            destino_tipo = tipo if dirigida and destino_sector is None else None
            recibida = rng.random() > 0.08  # algunas siguen solo ofrecidas
            don = m.Donacion(
                donante_id=donante.id, centro_id=centro.id, tipo_bien=tipo, cantidad=int(cantidad),
                unidad=UNIDADES[tipo], vencimiento=venc, destino_sector_id=destino_sector,
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
                    destino_sector_id=destino_sector, destino_tipo_necesidad=destino_tipo,
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
    n = 0
    for ambito, dims in PESOS_INICIALES.items():
        for dimension, valor in dims.items():
            db.add(m.Peso(ambito=ambito, dimension=dimension, valor=valor))
            n += 1
    db.flush()
    return n


# ----------------------------------------------------------------------------- orquestación
def generar(db: Session, semilla: int = 42, tipo: str = "inundacion", municipios: list[str] | None = None,
            reiniciar: bool = True, conservar_administradores: bool = False) -> dict:
    """Genera un escenario completo. Devuelve un resumen con los conteos."""
    rng = np.random.default_rng(semilla)
    municipios = municipios or list(MUNICIPIOS)
    if reiniciar:
        limpiar_simulacion(db, conservar_administradores)

    sectores = crear_sectores(db, rng, municipios)
    intensidad = float(rng.uniform(0.6, 1.0))
    dano, zona = _dano_verdadero(tipo, sectores, intensidad, rng)
    evento = m.Evento(tipo=tipo, nombre=f"{tipo.capitalize()} simulado (semilla {semilla})", fecha=BASE_FECHA,
                      zona=zona, intensidad=round(intensidad, 3), origen=m.OrigenDato.SIMULADO, semilla=semilla)
    db.add(evento)
    db.flush()

    usuarios = _Usuarios(db, rng, sectores)
    admin = usuarios.nuevo(m.Rol.ADMINISTRADOR)
    entidades = [usuarios.nuevo(m.Rol.ENTIDAD) for _ in range(2)]
    brigadistas = [usuarios.nuevo(m.Rol.BRIGADISTA, sectores[rng.integers(len(sectores))]) for _ in range(30)]
    equipos = [usuarios.nuevo(m.Rol.EQUIPO_ENTREGA, es_organizacion=bool(i % 2), aprobado=(i != 5)) for i in range(6)]

    verdad = {"semilla": semilla, "tipo": tipo, "reportes_falsos": [], "solicitudes_falsas": [], "duplicadas": [],
              "dano": {s.id: round(float(d), 3) for s, d in zip(sectores, dano)}}

    n_reportes = crear_reportes(db, rng, evento, sectores, dano, usuarios, brigadistas, entidades, verdad)
    n_solicitudes = crear_solicitudes(db, rng, evento, sectores, dano, usuarios, brigadistas, verdad)
    apoyo = crear_apoyo(db, rng, evento, sectores, usuarios, verdad)
    n_pesos = sembrar_pesos(db)

    # La verdad del escenario queda guardada para poder medir luego qué tan bien se recupera (validación sintética)
    db.add(m.Bitacora(usuario_id=admin.id, accion="simulacion_verdad", objeto=f"evento:{evento.id}", detalle=verdad,
                      hora=BASE_FECHA))
    db.commit()
    return {
        "semilla": semilla, "tipo": tipo, "evento_id": evento.id, "sectores": len(sectores),
        "viviendas": sum(s.viviendas for s in sectores), "reportes": n_reportes, "solicitudes": n_solicitudes,
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
