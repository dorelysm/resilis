"""Reglas de negocio del bloque 4: verificación, inventario, asignación, código de entrega y auditoría.

Las rutas web solo llaman a estas funciones. Cada una valida, cambia la base de datos y deja registro; si algo
no se puede hacer, lanza ErrorNegocio con un mensaje en lenguaje sencillo.
"""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.models import ahora

ALFABETO = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # sin I, L, O, 0 ni 1, para no confundirlos al dictar el código
LARGO_CODIGO = 8
VIGENCIA_CODIGO_HORAS = 72
MAX_INTENTOS_CODIGO = 5


class ErrorNegocio(Exception):
    """Algo que el usuario puede corregir; el mensaje se muestra tal cual."""


# ----------------------------------------------------------------------------- auditoría encadenada
def _canonica(hora: datetime) -> str:
    if hora.tzinfo is not None:
        hora = hora.astimezone(timezone.utc)
    return hora.strftime("%Y-%m-%dT%H:%M:%S.%f")


def _huella_evento(previo: str, tipo: str, solicitud_id: int | None, hora: datetime) -> str:
    return hashlib.sha256(f"{previo}|{tipo}|{solicitud_id}|{_canonica(hora)}".encode()).hexdigest()


def registrar_evento(db: Session, tipo: str, solicitud_id: int | None = None) -> m.EventoAuditoria:
    """Agrega un evento a la cadena. Cada evento guarda la huella del anterior y no lleva datos personales."""
    previo = db.scalar(select(m.EventoAuditoria.hash).order_by(m.EventoAuditoria.id.desc()).limit(1)) or ""
    hora = ahora()
    ev = m.EventoAuditoria(solicitud_id=solicitud_id, tipo=tipo, hora=hora, hash_previo=previo,
                           hash=_huella_evento(previo, tipo, solicitud_id, hora))
    db.add(ev)
    db.flush()
    return ev


def verificar_cadena(db: Session) -> tuple[bool, int | None]:
    """Recorre la cadena. Devuelve (íntegra, id del primer evento alterado)."""
    previo = ""
    for ev in db.scalars(select(m.EventoAuditoria).order_by(m.EventoAuditoria.id)):
        if ev.hash_previo != previo or ev.hash != _huella_evento(ev.hash_previo, ev.tipo, ev.solicitud_id, ev.hora):
            return False, ev.id
        previo = ev.hash
    return True, None


# ----------------------------------------------------------------------------- código de entrega
def normalizar_codigo(texto: str) -> str:
    return "".join(c for c in (texto or "").upper() if c.isalnum())


def codigo_para(secreto: str, entrega_id: int, sal: str) -> str:
    """Código de la entrega. Se calcula con la clave del servidor, así que la base de datos solo guarda su huella."""
    n = int.from_bytes(hmac.new(secreto.encode(), f"{entrega_id}:{sal}".encode(), hashlib.sha256).digest()[:8], "big")
    letras = []
    for _ in range(LARGO_CODIGO):
        n, resto = divmod(n, len(ALFABETO))
        letras.append(ALFABETO[resto])
    return "".join(letras)


def con_guion(codigo: str) -> str:
    return f"{codigo[:4]}-{codigo[4:]}"


def huella_codigo(sal: str, codigo: str) -> str:
    """sha256 de 'sal:código'. El navegador del equipo de entrega calcula lo mismo para validar sin conexión."""
    return hashlib.sha256(f"{sal}:{normalizar_codigo(codigo)}".encode()).hexdigest()


# ----------------------------------------------------------------------------- verificación
def verificar_solicitud(db: Session, solicitud: m.Solicitud, verificador: m.Usuario, resultado: str, nota: str) -> None:
    if resultado not in ("verificado", "desmentido"):
        raise ErrorNegocio("Elija si la solicitud se verifica o se desmiente.")
    if solicitud.estado != m.EstadoSolicitud.REGISTRADA:
        raise ErrorNegocio("Esta solicitud ya fue revisada.")
    if resultado == "desmentido" and len(nota.strip()) < 5:
        raise ErrorNegocio("Para desmentir una solicitud escriba el motivo.")
    db.add(m.Verificacion(objeto_tipo="solicitud", objeto_id=solicitud.id, verificador_id=verificador.id,
                          resultado=resultado, nota=nota.strip()))
    if resultado == "verificado":
        solicitud.estado = m.EstadoSolicitud.VERIFICADA
        registrar_evento(db, "verificada", solicitud.id)
    else:
        solicitud.estado = m.EstadoSolicitud.ANULADA
        solicitud.motivo_anulacion = f"Desmentida: {nota.strip()}"
        registrar_evento(db, "desmentida", solicitud.id)
    db.commit()


def verificar_reporte(db: Session, reporte: m.ReporteDanos, verificador: m.Usuario, resultado: str, nota: str) -> None:
    if resultado not in ("verificado", "desmentido"):
        raise ErrorNegocio("Elija si el reporte se verifica o se desmiente.")
    if db.scalar(select(m.Verificacion.id).where(m.Verificacion.objeto_tipo == "reporte",
                                                 m.Verificacion.objeto_id == reporte.id)):
        raise ErrorNegocio("Este reporte ya fue revisado.")
    db.add(m.Verificacion(objeto_tipo="reporte", objeto_id=reporte.id, verificador_id=verificador.id,
                          resultado=resultado, nota=nota.strip()))
    db.commit()


# ----------------------------------------------------------------------------- recepción e inventario
def recibir_donacion(db: Session, donacion: m.Donacion, centro: m.CentroAcopio, usuario: m.Usuario,
                     cantidad: int, estado_producto: str, vencimiento: datetime | None) -> m.Lote | None:
    if donacion.estado != m.EstadoDonacion.OFRECIDA:
        raise ErrorNegocio("Esta donación ya fue recibida.")
    if donacion.centro_id not in (None, centro.id):
        raise ErrorNegocio("Esta donación fue dirigida a otro centro de acopio.")
    donacion.centro_id = centro.id
    if donacion.monetaria:  # el dinero solo queda como constancia
        donacion.estado = m.EstadoDonacion.RECIBIDA
        db.commit()
        return None
    if cantidad < 1:
        raise ErrorNegocio("Escriba la cantidad que realmente recibió.")
    donacion.cantidad = cantidad
    donacion.estado_producto = estado_producto
    donacion.vencimiento = vencimiento or donacion.vencimiento
    donacion.estado = m.EstadoDonacion.EN_INVENTARIO
    lote = m.Lote(
        donacion_id=donacion.id, centro_id=centro.id, tipo_bien=donacion.tipo_bien, unidad=donacion.unidad,
        cantidad_recibida=cantidad, cantidad_disponible=cantidad, estado_producto=estado_producto,
        vencimiento=donacion.vencimiento, destino_sector_id=donacion.destino_sector_id,
        destino_tipo_necesidad=donacion.destino_tipo_necesidad, destino_solicitud_id=donacion.destino_solicitud_id,
    )
    db.add(lote)
    db.flush()
    db.add(m.MovimientoInventario(lote_id=lote.id, tipo="recepcion", cantidad=cantidad, usuario_id=usuario.id))
    db.commit()
    return lote


def _lote_admite(lote: m.Lote, sol: m.Solicitud) -> int:
    """0 si el lote no puede usarse para la solicitud; si puede, su prioridad (menor = antes)."""
    if lote.destino_solicitud_id is not None:
        return 1 if lote.destino_solicitud_id == sol.id else 0
    if lote.destino_sector_id is not None:
        return 2 if lote.destino_sector_id == sol.sector_id else 0
    if lote.destino_tipo_necesidad is not None:
        return 3 if lote.destino_tipo_necesidad == sol.necesidad else 0
    return 4


def lotes_para(db: Session, sol: m.Solicitud) -> list[m.Lote]:
    """Lotes que sirven para la solicitud: primero los dirigidos a ella, luego los generales, y dentro de cada
    grupo el que vence antes (primero en vencer, primero en salir)."""
    ahora_ = ahora()
    candidatos = db.scalars(select(m.Lote).where(m.Lote.tipo_bien == sol.necesidad, m.Lote.cantidad_disponible > 0))
    utiles = []
    for lote in candidatos:
        venc = lote.vencimiento
        if venc is not None and (venc.replace(tzinfo=timezone.utc) if venc.tzinfo is None else venc) <= ahora_:
            continue  # un producto vencido no se entrega
        prioridad = _lote_admite(lote, sol)
        if prioridad:
            utiles.append((prioridad, venc is None, venc.replace(tzinfo=None) if venc else datetime.max, lote.id, lote))
    utiles.sort(key=lambda t: t[:4])
    return [t[4] for t in utiles]


def disponible_para(db: Session, sol: m.Solicitud) -> int:
    return sum(lote.cantidad_disponible for lote in lotes_para(db, sol))


def _reservas_de(db: Session, solicitud_id: int) -> dict[int, int]:
    """Cuánto tiene reservado cada lote para una solicitud (reservas menos liberaciones y entregas)."""
    neto: dict[int, int] = {}
    for mov in db.scalars(select(m.MovimientoInventario).where(m.MovimientoInventario.solicitud_id == solicitud_id)):
        signo = 1 if mov.tipo == "reserva" else -1 if mov.tipo in ("liberacion", "entrega") else 0
        neto[mov.lote_id] = neto.get(mov.lote_id, 0) + signo * mov.cantidad
    return {k: v for k, v in neto.items() if v > 0}


def _actualizar_donacion(db: Session, lote: m.Lote) -> None:
    don = db.get(m.Donacion, lote.donacion_id)
    if don is None:
        return
    if lote.cantidad_disponible == 0 and lote.cantidad_reservada == 0:
        don.estado = m.EstadoDonacion.ENTREGADA
    elif lote.cantidad_disponible == 0:
        don.estado = m.EstadoDonacion.ASIGNADA
    else:
        don.estado = m.EstadoDonacion.EN_INVENTARIO


# ----------------------------------------------------------------------------- asignación y entrega
def asignar(db: Session, sol: m.Solicitud, equipo: m.Usuario, por: m.Usuario, secreto: str) -> m.Entrega:
    """Reserva el inventario, crea la entrega y su código. Todo o nada: si falta inventario no cambia nada."""
    if sol.estado != m.EstadoSolicitud.VERIFICADA:
        raise ErrorNegocio("Solo se puede asignar una solicitud verificada.")
    if equipo.rol != m.Rol.EQUIPO_ENTREGA or not equipo.aprobado:
        raise ErrorNegocio("Elija un equipo de entrega aprobado.")
    lotes = lotes_para(db, sol)
    if sum(lote.cantidad_disponible for lote in lotes) < sol.cantidad:
        raise ErrorNegocio(f"No hay inventario suficiente de {sol.necesidad.replace('_', ' ')} "
                           f"({sum(lote.cantidad_disponible for lote in lotes)} disponibles, se necesitan {sol.cantidad}).")
    faltante = sol.cantidad
    for lote in lotes:
        tomar = min(faltante, lote.cantidad_disponible)
        lote.cantidad_disponible -= tomar
        lote.cantidad_reservada += tomar
        db.add(m.MovimientoInventario(lote_id=lote.id, tipo="reserva", cantidad=tomar, solicitud_id=sol.id,
                                      usuario_id=por.id))
        _actualizar_donacion(db, lote)
        faltante -= tomar
        if faltante == 0:
            break

    sal = secrets.token_hex(8)
    entrega = m.Entrega(solicitud_id=sol.id, equipo_id=equipo.id, codigo_hash="", codigo_sal=sal,
                        estado_codigo=m.EstadoCodigo.ACTIVO, estado="asignada",
                        vence_en=ahora() + timedelta(hours=VIGENCIA_CODIGO_HORAS))
    db.add(entrega)
    db.flush()
    entrega.codigo_hash = huella_codigo(sal, codigo_para(secreto, entrega.id, sal))
    sol.estado = m.EstadoSolicitud.ASIGNADA
    registrar_evento(db, "asignada", sol.id)
    db.add(m.Bitacora(usuario_id=por.id, accion="asignar", objeto=f"solicitud:{sol.id}", detalle={"equipo": equipo.id}))
    db.commit()
    return entrega


def entrega_activa(db: Session, solicitud_id: int) -> m.Entrega | None:
    return db.scalar(select(m.Entrega).where(m.Entrega.solicitud_id == solicitud_id,
                                             m.Entrega.estado_codigo == m.EstadoCodigo.ACTIVO)
                     .order_by(m.Entrega.id.desc()).limit(1))


def en_camino(db: Session, entrega: m.Entrega, equipo: m.Usuario) -> None:
    _propia(entrega, equipo)
    if entrega.estado != "asignada":
        raise ErrorNegocio("Esta entrega ya está en camino o terminó.")
    entrega.estado = "en_camino"
    sol = db.get(m.Solicitud, entrega.solicitud_id)
    sol.estado = m.EstadoSolicitud.EN_CAMINO
    registrar_evento(db, "en_camino", sol.id)
    db.commit()


def _propia(entrega: m.Entrega, equipo: m.Usuario) -> None:
    if entrega.equipo_id != equipo.id:
        raise ErrorNegocio("Esta entrega fue asignada a otro equipo.")


def confirmar_entrega(db: Session, entrega: m.Entrega, equipo: m.Usuario, codigo: str,
                      lat: float | None = None, lon: float | None = None) -> bool:
    """Valida el código y confirma la entrega. Devuelve True si ya estaba confirmada con ese mismo código
    (así reenviar desde un dispositivo que estuvo sin conexión no da error)."""
    _propia(entrega, equipo)
    huella = huella_codigo(entrega.codigo_sal, codigo)
    if entrega.estado == "entregada" and hmac.compare_digest(huella, entrega.codigo_hash):
        return True
    if entrega.estado_codigo != m.EstadoCodigo.ACTIVO:
        raise ErrorNegocio("Este código ya se usó o dejó de valer.")
    if entrega.vence_en is not None:
        venc = entrega.vence_en.replace(tzinfo=timezone.utc) if entrega.vence_en.tzinfo is None else entrega.vence_en
        if venc <= ahora():
            entrega.estado_codigo = m.EstadoCodigo.INVALIDADO
            db.commit()
            raise ErrorNegocio("El código venció. La solicitud debe asignarse de nuevo.")
    if not hmac.compare_digest(huella, entrega.codigo_hash):
        desde = db.scalar(select(func.max(m.EventoAuditoria.id)).where(
            m.EventoAuditoria.solicitud_id == entrega.solicitud_id, m.EventoAuditoria.tipo == "asignada")) or 0
        intentos = db.scalar(select(func.count()).select_from(m.EventoAuditoria).where(
            m.EventoAuditoria.solicitud_id == entrega.solicitud_id, m.EventoAuditoria.tipo == "codigo_incorrecto",
            m.EventoAuditoria.id > desde)) or 0  # solo cuentan los intentos desde la última asignación
        registrar_evento(db, "codigo_incorrecto", entrega.solicitud_id)
        if intentos + 1 >= MAX_INTENTOS_CODIGO:
            entrega.estado_codigo = m.EstadoCodigo.INVALIDADO
            db.commit()
            raise ErrorNegocio("Demasiados intentos con un código incorrecto. La solicitud debe asignarse de nuevo.")
        db.commit()
        raise ErrorNegocio("El código no es correcto. Revise que sea el que tiene la persona.")

    sol = db.get(m.Solicitud, entrega.solicitud_id)
    for lote_id, cantidad in _reservas_de(db, sol.id).items():
        lote = db.get(m.Lote, lote_id)
        lote.cantidad_reservada -= cantidad
        lote.cantidad_entregada += cantidad
        db.add(m.MovimientoInventario(lote_id=lote_id, tipo="entrega", cantidad=cantidad, solicitud_id=sol.id,
                                      usuario_id=equipo.id))
        db.flush()
        _actualizar_donacion(db, lote)
    entrega.estado = "entregada"
    entrega.estado_codigo = m.EstadoCodigo.USADO
    entrega.entregada_en = ahora()
    entrega.lat, entrega.lon = lat, lon
    sol.estado = m.EstadoSolicitud.ENTREGADA
    registrar_evento(db, "entregada", sol.id)
    db.commit()
    return False


def registrar_incidencia(db: Session, entrega: m.Entrega, equipo: m.Usuario, tipo: str, nota: str) -> None:
    """La entrega no se pudo hacer: se libera el inventario, el código deja de valer y la solicitud vuelve a
    estar verificada para poder asignarse otra vez."""
    _propia(entrega, equipo)
    if tipo not in ("no_encontrada", "rechazo", "no_llego"):
        raise ErrorNegocio("Elija qué pasó.")
    if entrega.estado in ("entregada", "incidencia"):
        raise ErrorNegocio("Esta entrega ya terminó.")
    sol = db.get(m.Solicitud, entrega.solicitud_id)
    for lote_id, cantidad in _reservas_de(db, sol.id).items():
        lote = db.get(m.Lote, lote_id)
        lote.cantidad_reservada -= cantidad
        lote.cantidad_disponible += cantidad
        db.add(m.MovimientoInventario(lote_id=lote_id, tipo="liberacion", cantidad=cantidad, solicitud_id=sol.id,
                                      usuario_id=equipo.id))
        db.flush()
        _actualizar_donacion(db, lote)
    db.add(m.Incidencia(entrega_id=entrega.id, tipo=tipo, nota=nota.strip()))
    entrega.estado = "incidencia"
    entrega.estado_codigo = m.EstadoCodigo.INVALIDADO
    sol.estado = m.EstadoSolicitud.VERIFICADA
    registrar_evento(db, "incidencia", sol.id)
    db.commit()


def cerrar_solicitud(db: Session, sol: m.Solicitud, usuario: m.Usuario) -> None:
    if sol.solicitante_id != usuario.id:
        raise ErrorNegocio("Solo la persona que pidió la ayuda puede confirmar que la recibió.")
    if sol.estado != m.EstadoSolicitud.ENTREGADA:
        raise ErrorNegocio("La ayuda todavía no figura como entregada.")
    sol.estado = m.EstadoSolicitud.CERRADA
    registrar_evento(db, "cerrada", sol.id)
    db.commit()
