"""Esquema de la base de datos de Resilis.

Sigue la tabla de entidades de Requerimientos/secciones/04_datos.tex. Se usan tipos genéricos de
SQLAlchemy (JSON, String, Integer) para que el mismo esquema corra en PostgreSQL y en SQLite (pruebas).
"""
import enum
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    select,
)
from sqlalchemy.orm import Mapped, column_property, mapped_column, relationship

from app.db import Base


def ahora() -> datetime:
    return datetime.now(timezone.utc)


# ----------------------------------------------------------------------------- catálogos
class Rol(enum.StrEnum):
    SOLICITANTE = "solicitante"
    BRIGADISTA = "brigadista"
    EQUIPO_ENTREGA = "equipo_entrega"
    ENTIDAD = "entidad"
    ADMINISTRADOR = "administrador"
    DONANTE = "donante"
    CENTRO_ACOPIO = "centro_acopio"


class TipoEvento(enum.StrEnum):
    TERREMOTO = "terremoto"
    INUNDACION = "inundacion"
    VENDAVAL = "vendaval"
    DESLIZAMIENTO = "deslizamiento"


class OrigenDato(enum.StrEnum):
    SIMULADO = "simulado"
    OFICIAL = "oficial"
    REAL = "real"


class FuenteReporte(enum.StrEnum):
    APP = "app"
    PAPEL = "papel"
    ESTADO = "estado"


class EstadoSolicitud(enum.StrEnum):
    REGISTRADA = "registrada"
    VERIFICADA = "verificada"
    ASIGNADA = "asignada"
    EN_CAMINO = "en_camino"
    ENTREGADA = "entregada"
    CERRADA = "cerrada"
    ANULADA = "anulada"


class TipoNecesidad(enum.StrEnum):
    ALIMENTOS = "alimentos"
    AGUA = "agua"
    MEDICAMENTOS = "medicamentos"
    HIGIENE = "higiene"
    ABRIGO_VIVIENDA = "abrigo_vivienda"
    OTRO = "otro"


class EstadoDonacion(enum.StrEnum):
    OFRECIDA = "ofrecida"
    RECIBIDA = "recibida"
    EN_INVENTARIO = "en_inventario"
    ASIGNADA = "asignada"
    ENTREGADA = "entregada"


class EstadoPlan(enum.StrEnum):
    PROPUESTO = "propuesto"
    APROBADO = "aprobado"
    RECHAZADO = "rechazado"


class EstadoCodigo(enum.StrEnum):
    ACTIVO = "activo"
    USADO = "usado"
    INVALIDADO = "invalidado"


# ----------------------------------------------------------------------------- territorio
class Municipio(Base):
    __tablename__ = "municipio"

    codigo: Mapped[str] = mapped_column(String(5), primary_key=True)  # código DANE
    nombre: Mapped[str] = mapped_column(String(80))

    proyecciones: Mapped[list["ViviendaProyeccion"]] = relationship(back_populates="municipio")
    barrios: Mapped[list["Barrio"]] = relationship(back_populates="municipio")


class ViviendaProyeccion(Base):
    """Viviendas proyectadas por municipio, área y año (conjunto de datos abiertos del Atlántico)."""

    __tablename__ = "vivienda_proyeccion"
    __table_args__ = (UniqueConstraint("municipio_codigo", "area", "anio"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    municipio_codigo: Mapped[str] = mapped_column(ForeignKey("municipio.codigo"), index=True)
    area: Mapped[str] = mapped_column(String(60))  # Total, Cabecera, Centros Poblados y Rural Disperso
    anio: Mapped[int] = mapped_column(Integer)
    viviendas: Mapped[int] = mapped_column(Integer)

    municipio: Mapped[Municipio] = relationship(back_populates="proyecciones")


class Barrio(Base):
    __tablename__ = "barrio"

    id: Mapped[int] = mapped_column(primary_key=True)
    municipio_codigo: Mapped[str] = mapped_column(ForeignKey("municipio.codigo"), index=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(20), default="barrio")  # barrio | centro poblado
    geometria: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # GeoJSON
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    viviendas: Mapped[int] = mapped_column(Integer, default=0)
    personas: Mapped[int] = mapped_column(Integer, default=0)
    vulnerabilidad_base: Mapped[float] = mapped_column(Float, default=0.0)  # 0 a 1
    amenaza_base: Mapped[float] = mapped_column(Float, default=0.0)  # 0 a 1
    acceso_base: Mapped[float] = mapped_column(Float, default=1.0)  # 0 bloqueado, 1 libre
    simulado: Mapped[bool] = mapped_column(Boolean, default=True)

    municipio: Mapped[Municipio] = relationship(back_populates="barrios")


# "Barrio, Municipio": los nombres de barrio se repiten entre municipios, así que se muestran siempre juntos.
Barrio.etiqueta = column_property(
    Barrio.nombre + ", " + select(Municipio.nombre).where(Municipio.codigo == Barrio.municipio_codigo).correlate_except(Municipio).scalar_subquery(),
    deferred=False)


# ----------------------------------------------------------------------------- usuarios
class Usuario(Base):
    __tablename__ = "usuario"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    telefono: Mapped[str] = mapped_column(String(30), index=True)
    documento: Mapped[str | None] = mapped_column(String(30), nullable=True, index=True)
    rol: Mapped[str] = mapped_column(String(20), index=True)
    barrio_id: Mapped[int | None] = mapped_column(ForeignKey("barrio.id"), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    consentimiento_datos: Mapped[bool] = mapped_column(Boolean, default=False)
    consentimiento_fecha: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    es_organizacion: Mapped[bool] = mapped_column(Boolean, default=False)
    aprobado: Mapped[bool] = mapped_column(Boolean, default=True)  # las organizaciones requieren aprobación
    ficticio: Mapped[bool] = mapped_column(Boolean, default=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


# ----------------------------------------------------------------------------- eventos y reportes
class Evento(Base):
    __tablename__ = "evento"

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(20))
    nombre: Mapped[str] = mapped_column(String(120))
    fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    zona: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # {"lat":..., "lon":..., "radio_km":...}
    intensidad: Mapped[float] = mapped_column(Float, default=0.0)  # 0 a 1
    origen: Mapped[str] = mapped_column(String(10), default=OrigenDato.SIMULADO)
    semilla: Mapped[int | None] = mapped_column(Integer, nullable=True)


class ReporteDanos(Base):
    __tablename__ = "reporte_danos"
    __table_args__ = (CheckConstraint("nivel_dano BETWEEN 0 AND 3"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    barrio_id: Mapped[int] = mapped_column(ForeignKey("barrio.id"), index=True)
    evento_id: Mapped[int] = mapped_column(ForeignKey("evento.id"), index=True)
    autor_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    fuente: Mapped[str] = mapped_column(String(10), default=FuenteReporte.APP)
    hora_evento: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    hora_captura: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    nivel_dano: Mapped[int] = mapped_column(Integer)  # 0 a 3
    personas_afectadas: Mapped[int] = mapped_column(Integer, default=0)
    acceso: Mapped[float] = mapped_column(Float, default=1.0)  # 0 bloqueado, 1 libre
    estado: Mapped[str] = mapped_column(String(10), default="activo")  # activo | anulado
    motivo_anulacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    confianza: Mapped[float | None] = mapped_column(Float, nullable=True)  # se calcula
    anomalo: Mapped[bool] = mapped_column(Boolean, default=False)


class DatoOficial(Base):
    """Registros cargados desde archivos abiertos del Estado (eventos, daños, amenazas)."""

    __tablename__ = "dato_oficial"

    id: Mapped[int] = mapped_column(primary_key=True)
    origen: Mapped[str] = mapped_column(String(120))
    fecha_publicacion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    tipo: Mapped[str] = mapped_column(String(20))  # evento | dano | amenaza
    datos: Mapped[dict] = mapped_column(JSON)
    cargado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


# ----------------------------------------------------------------------------- solicitudes
class Solicitud(Base):
    __tablename__ = "solicitud"
    __table_args__ = (CheckConstraint("urgencia BETWEEN 0 AND 3"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitante_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    creador_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))  # distinto si lo crea un brigadista
    barrio_id: Mapped[int] = mapped_column(ForeignKey("barrio.id"), index=True)
    evento_id: Mapped[int | None] = mapped_column(ForeignKey("evento.id"), nullable=True)
    necesidad: Mapped[str] = mapped_column(String(20))  # TipoNecesidad
    cantidad: Mapped[int] = mapped_column(Integer, default=1)  # cantidad necesaria, en la unidad del bien
    personas_hogar: Mapped[int] = mapped_column(Integer, default=1)
    descripcion: Mapped[str] = mapped_column(Text, default="")
    urgencia: Mapped[int] = mapped_column(Integer, default=1)  # 0 a 3, declarada
    direccion: Mapped[str] = mapped_column(String(200), default="")
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    fuente: Mapped[str] = mapped_column(String(10), default=FuenteReporte.APP)
    estado: Mapped[str] = mapped_column(String(15), default=EstadoSolicitud.REGISTRADA, index=True)
    prioridad: Mapped[float | None] = mapped_column(Float, nullable=True)  # se calcula (TOPSIS)
    confianza: Mapped[float | None] = mapped_column(Float, nullable=True)  # se calcula
    duplicada: Mapped[bool] = mapped_column(Boolean, default=False)
    anomala: Mapped[bool] = mapped_column(Boolean, default=False)
    motivo_anulacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    vulnerabilidad: Mapped["Vulnerabilidad | None"] = relationship(back_populates="solicitud", uselist=False)


class Vulnerabilidad(Base):
    """Dato sensible: se guarda aparte y solo con consentimiento expreso."""

    __tablename__ = "vulnerabilidad"
    __table_args__ = (CheckConstraint("consentimiento", name="ck_vulnerabilidad_consentimiento"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitud.id"), unique=True)
    tipo: Mapped[str] = mapped_column(String(30))  # discapacidad, adulto_mayor, menor, embarazo, cronica, otra
    descripcion_situacion: Mapped[str] = mapped_column(Text)
    necesidad_especifica: Mapped[str] = mapped_column(Text, default="")
    consentimiento: Mapped[bool] = mapped_column(Boolean)
    consentimiento_fecha: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)

    solicitud: Mapped[Solicitud] = relationship(back_populates="vulnerabilidad")


class Verificacion(Base):
    __tablename__ = "verificacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    objeto_tipo: Mapped[str] = mapped_column(String(10))  # reporte | solicitud
    objeto_id: Mapped[int] = mapped_column(Integer, index=True)
    verificador_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"))
    resultado: Mapped[str] = mapped_column(String(12))  # verificado | desmentido
    nota: Mapped[str] = mapped_column(Text, default="")
    hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


# ----------------------------------------------------------------------------- donaciones e inventario
class CentroAcopio(Base):
    __tablename__ = "centro_acopio"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(120))
    barrio_id: Mapped[int | None] = mapped_column(ForeignKey("barrio.id"), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    responsable_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)


class Donante(Base):
    __tablename__ = "donante"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    nombre: Mapped[str] = mapped_column(String(120))
    tipo: Mapped[str] = mapped_column(String(15))  # persona | organizacion | empresa
    contacto: Mapped[str] = mapped_column(String(120), default="")
    nombre_publico: Mapped[bool] = mapped_column(Boolean, default=True)  # False: no aparece en vistas públicas
    consentimiento: Mapped[bool] = mapped_column(Boolean, default=False)


class Donacion(Base):
    __tablename__ = "donacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    donante_id: Mapped[int] = mapped_column(ForeignKey("donante.id"), index=True)
    centro_id: Mapped[int | None] = mapped_column(ForeignKey("centro_acopio.id"), nullable=True)
    tipo_bien: Mapped[str] = mapped_column(String(20))  # TipoNecesidad
    monetaria: Mapped[bool] = mapped_column(Boolean, default=False)
    monto: Mapped[int | None] = mapped_column(Integer, nullable=True)  # solo constancia; no se procesan pagos
    cantidad: Mapped[int] = mapped_column(Integer, default=0)
    unidad: Mapped[str] = mapped_column(String(20), default="unidad")
    estado_producto: Mapped[str] = mapped_column(String(20), default="nuevo")
    vencimiento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Donación dirigida: a un barrio, a un tipo de necesidad o a una solicitud
    destino_barrio_id: Mapped[int | None] = mapped_column(ForeignKey("barrio.id"), nullable=True)
    destino_tipo_necesidad: Mapped[str | None] = mapped_column(String(20), nullable=True)
    destino_solicitud_id: Mapped[int | None] = mapped_column(ForeignKey("solicitud.id"), nullable=True)
    estado: Mapped[str] = mapped_column(String(15), default=EstadoDonacion.OFRECIDA, index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class Lote(Base):
    """Unidad de inventario. Siempre se cumple: disponible + reservada + entregada = recibida."""

    __tablename__ = "lote"
    __table_args__ = (
        CheckConstraint("cantidad_disponible >= 0 AND cantidad_reservada >= 0 AND cantidad_entregada >= 0"),
        CheckConstraint("cantidad_disponible + cantidad_reservada + cantidad_entregada = cantidad_recibida"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    donacion_id: Mapped[int] = mapped_column(ForeignKey("donacion.id"), index=True)
    centro_id: Mapped[int] = mapped_column(ForeignKey("centro_acopio.id"), index=True)
    tipo_bien: Mapped[str] = mapped_column(String(20), index=True)
    unidad: Mapped[str] = mapped_column(String(20), default="unidad")
    cantidad_recibida: Mapped[int] = mapped_column(Integer)
    cantidad_disponible: Mapped[int] = mapped_column(Integer)
    cantidad_reservada: Mapped[int] = mapped_column(Integer, default=0)
    cantidad_entregada: Mapped[int] = mapped_column(Integer, default=0)
    estado_producto: Mapped[str] = mapped_column(String(20), default="nuevo")
    vencimiento: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    destino_barrio_id: Mapped[int | None] = mapped_column(ForeignKey("barrio.id"), nullable=True)
    destino_tipo_necesidad: Mapped[str | None] = mapped_column(String(20), nullable=True)
    destino_solicitud_id: Mapped[int | None] = mapped_column(ForeignKey("solicitud.id"), nullable=True)


class MovimientoInventario(Base):
    """Cada cambio del inventario deja un registro (RNF-17)."""

    __tablename__ = "movimiento_inventario"

    id: Mapped[int] = mapped_column(primary_key=True)
    lote_id: Mapped[int] = mapped_column(ForeignKey("lote.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(15))  # recepcion | reserva | liberacion | entrega | ajuste
    cantidad: Mapped[int] = mapped_column(Integer)
    plan_id: Mapped[int | None] = mapped_column(ForeignKey("plan_asignacion.id"), nullable=True)
    solicitud_id: Mapped[int | None] = mapped_column(ForeignKey("solicitud.id"), nullable=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


# ----------------------------------------------------------------------------- plan, entrega y auditoría
class PlanAsignacion(Base):
    __tablename__ = "plan_asignacion"

    id: Mapped[int] = mapped_column(primary_key=True)
    evento_id: Mapped[int | None] = mapped_column(ForeignKey("evento.id"), nullable=True)
    estado: Mapped[str] = mapped_column(String(10), default=EstadoPlan.PROPUESTO)
    metodo: Mapped[str] = mapped_column(String(15), default="optimizado")  # optimizado | voraz
    necesidad_total: Mapped[float] = mapped_column(Float, default=0.0)
    necesidad_cubierta: Mapped[float] = mapped_column(Float, default=0.0)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    aprobado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    aprobado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    lineas: Mapped[list["PlanLinea"]] = relationship(back_populates="plan", cascade="all, delete-orphan")


class PlanResumen(Base):
    """Datos de un plan de asignación: parámetros, comparación con la asignación voraz, avisos y lo que quedó sin
    cubrir. Va en una tabla aparte para poder agregarlo sin migrar la tabla plan_asignacion."""

    __tablename__ = "plan_resumen"

    plan_id: Mapped[int] = mapped_column(ForeignKey("plan_asignacion.id"), primary_key=True)
    datos: Mapped[dict] = mapped_column(JSON)


class PlanLinea(Base):
    __tablename__ = "plan_linea"

    id: Mapped[int] = mapped_column(primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan_asignacion.id"), index=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitud.id"), index=True)
    lote_id: Mapped[int | None] = mapped_column(ForeignKey("lote.id"), nullable=True)
    cantidad: Mapped[int] = mapped_column(Integer, default=0)
    equipo_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    razon: Mapped[str] = mapped_column(Text, default="")  # por qué recibe lo que recibe

    plan: Mapped[PlanAsignacion] = relationship(back_populates="lineas")


class Entrega(Base):
    """Entrega de una solicitud. El código se guarda solo como huella con sal."""

    __tablename__ = "entrega"

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int] = mapped_column(ForeignKey("solicitud.id"), index=True)
    equipo_id: Mapped[int] = mapped_column(ForeignKey("usuario.id"), index=True)
    plan_linea_id: Mapped[int | None] = mapped_column(ForeignKey("plan_linea.id"), nullable=True)
    codigo_hash: Mapped[str] = mapped_column(String(64))
    codigo_sal: Mapped[str] = mapped_column(String(32))
    estado_codigo: Mapped[str] = mapped_column(String(12), default=EstadoCodigo.ACTIVO)
    vence_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    estado: Mapped[str] = mapped_column(String(15), default="asignada")  # asignada | en_camino | entregada | incidencia
    entregada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lat: Mapped[float | None] = mapped_column(Float, nullable=True)
    lon: Mapped[float | None] = mapped_column(Float, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class Incidencia(Base):
    __tablename__ = "incidencia"

    id: Mapped[int] = mapped_column(primary_key=True)
    entrega_id: Mapped[int] = mapped_column(ForeignKey("entrega.id"), index=True)
    tipo: Mapped[str] = mapped_column(String(20))  # no_encontrada | parcial | rechazo | no_llego
    nota: Mapped[str] = mapped_column(Text, default="")
    hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class EventoAuditoria(Base):
    """Registro encadenado por hash. No contiene datos personales (RD-18)."""

    __tablename__ = "evento_auditoria"

    id: Mapped[int] = mapped_column(primary_key=True)
    solicitud_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    tipo: Mapped[str] = mapped_column(String(25))
    hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
    hash_previo: Mapped[str] = mapped_column(String(64), default="")
    hash: Mapped[str] = mapped_column(String(64))


# ----------------------------------------------------------------------------- puntajes calculados
class PuntajeBarrio(Base):
    """Resultado del cálculo de prioridad y confianza de cada barrio (bloque 5). Se recalcula completo."""

    __tablename__ = "puntaje_barrio"

    barrio_id: Mapped[int] = mapped_column(ForeignKey("barrio.id"), primary_key=True)
    evento_id: Mapped[int | None] = mapped_column(ForeignKey("evento.id"), nullable=True)
    prioridad: Mapped[float] = mapped_column(Float, default=0.0)  # P (TOPSIS), de 0 a 1
    posicion: Mapped[int] = mapped_column(Integer, default=0)  # 1 = el que se debe atender primero
    confianza: Mapped[float] = mapped_column(Float, default=0.0)  # C, de 0 a 1
    dispersion: Mapped[float] = mapped_column(Float, default=0.0)  # D: contradicción entre reportes
    n_reportes: Mapped[int] = mapped_column(Integer, default=0)
    n_solicitudes: Mapped[int] = mapped_column(Integer, default=0)
    horas_ultimo_reporte: Mapped[float | None] = mapped_column(Float, nullable=True)
    base_previa: Mapped[bool] = mapped_column(Boolean, default=False)  # True: sin reportes, se usó solo la línea base
    indicadores: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # valores de cada dimensión (0 a 1)
    aportes: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # parte de cada dimensión en el puntaje
    alertas: Mapped[list | None] = mapped_column(JSON, nullable=True)  # códigos de alerta de información faltante
    calculado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


# ----------------------------------------------------------------------------- parámetros y bitácora
class Peso(Base):
    __tablename__ = "peso"
    __table_args__ = (UniqueConstraint("ambito", "dimension"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    ambito: Mapped[str] = mapped_column(String(15))  # barrio | solicitud | confianza
    dimension: Mapped[str] = mapped_column(String(30))
    valor: Mapped[float] = mapped_column(Float)
    actualizado_por: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)


class Bitacora(Base):
    __tablename__ = "bitacora"

    id: Mapped[int] = mapped_column(primary_key=True)
    usuario_id: Mapped[int | None] = mapped_column(ForeignKey("usuario.id"), nullable=True)
    accion: Mapped[str] = mapped_column(String(40))
    objeto: Mapped[str] = mapped_column(String(40), default="")
    detalle: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    hora: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=ahora)
