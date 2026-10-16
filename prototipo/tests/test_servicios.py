from datetime import timedelta

import pytest
from sqlalchemy import func, select, update

from app import models as m
from app import servicios as sv
from app.models import ahora

SECRETO = "clave-de-prueba"


def usuario(db, rol, nombre="Persona Ficticia", **extra):
    u = m.Usuario(nombre=nombre, telefono="3000000000", rol=rol, ficticio=False, **extra)
    db.add(u)
    db.flush()
    return u


@pytest.fixture()
def mundo(db):
    db.add(m.Municipio(codigo="08001", nombre="Barranquilla"))
    db.flush()
    sector = m.Sector(municipio_codigo="08001", nombre="Sector 1")
    otro = m.Sector(municipio_codigo="08001", nombre="Sector 2")
    db.add_all([sector, otro])
    db.flush()
    centro_resp = usuario(db, m.Rol.CENTRO_ACOPIO, "Responsable")
    centro = m.CentroAcopio(nombre="Centro 1", sector_id=sector.id, responsable_id=centro_resp.id)
    donante = m.Donante(nombre="Donante", tipo="persona")
    db.add_all([centro, donante])
    db.flush()
    return {
        "sector": sector, "otro": otro, "centro": centro, "centro_resp": centro_resp, "donante": donante,
        "solicitante": usuario(db, m.Rol.SOLICITANTE, "Solicitante", sector_id=sector.id),
        "brigadista": usuario(db, m.Rol.BRIGADISTA, "Brigadista"),
        "entidad": usuario(db, m.Rol.ENTIDAD, "Entidad"),
        "equipo": usuario(db, m.Rol.EQUIPO_ENTREGA, "Equipo A"),
        "equipo2": usuario(db, m.Rol.EQUIPO_ENTREGA, "Equipo B"),
    }


def donar(db, mundo, cantidad, tipo="agua", dias=None, **dest):
    don = m.Donacion(donante_id=mundo["donante"].id, tipo_bien=tipo, cantidad=cantidad, unidad="litros",
                     vencimiento=ahora() + timedelta(days=dias) if dias else None, **dest)
    db.add(don)
    db.flush()
    return sv.recibir_donacion(db, don, mundo["centro"], mundo["centro_resp"], cantidad, "nuevo", None)


def pedir(db, mundo, cantidad=10, necesidad="agua", estado=m.EstadoSolicitud.VERIFICADA):
    s = m.Solicitud(solicitante_id=mundo["solicitante"].id, creador_id=mundo["solicitante"].id,
                    sector_id=mundo["sector"].id, necesidad=necesidad, cantidad=cantidad, estado=estado)
    db.add(s)
    db.flush()
    return s


def lote_de(db, lote):
    db.refresh(lote)
    return lote


# ----------------------------------------------------------------------------- verificación
def test_verificar_y_desmentir_solicitudes(db, mundo):
    ok = pedir(db, mundo, estado=m.EstadoSolicitud.REGISTRADA)
    sv.verificar_solicitud(db, ok, mundo["brigadista"], "verificado", "Visité la vivienda")
    assert ok.estado == m.EstadoSolicitud.VERIFICADA

    falsa = pedir(db, mundo, estado=m.EstadoSolicitud.REGISTRADA)
    with pytest.raises(sv.ErrorNegocio, match="motivo"):
        sv.verificar_solicitud(db, falsa, mundo["brigadista"], "desmentido", "")
    sv.verificar_solicitud(db, falsa, mundo["brigadista"], "desmentido", "La dirección no existe")
    assert falsa.estado == m.EstadoSolicitud.ANULADA and "no existe" in falsa.motivo_anulacion
    with pytest.raises(sv.ErrorNegocio, match="ya fue revisada"):
        sv.verificar_solicitud(db, ok, mundo["brigadista"], "verificado", "")


# ----------------------------------------------------------------------------- inventario
def test_la_recepcion_usa_la_cantidad_realmente_recibida(db, mundo):
    don = m.Donacion(donante_id=mundo["donante"].id, tipo_bien="agua", cantidad=100, unidad="litros")
    db.add(don)
    db.flush()
    lote = sv.recibir_donacion(db, don, mundo["centro"], mundo["centro_resp"], 90, "nuevo", None)
    assert (lote.cantidad_recibida, lote.cantidad_disponible, don.cantidad, don.estado) == (90, 90, 90, "en_inventario")
    assert db.scalar(select(m.MovimientoInventario.tipo)) == "recepcion"
    with pytest.raises(sv.ErrorNegocio, match="ya fue recibida"):
        sv.recibir_donacion(db, don, mundo["centro"], mundo["centro_resp"], 90, "nuevo", None)


def test_el_dinero_solo_queda_como_constancia(db, mundo):
    don = m.Donacion(donante_id=mundo["donante"].id, tipo_bien="otro", monetaria=True, monto=50000, cantidad=0)
    db.add(don)
    db.flush()
    assert sv.recibir_donacion(db, don, mundo["centro"], mundo["centro_resp"], 0, "nuevo", None) is None
    assert don.estado == "recibida" and db.scalar(select(func.count()).select_from(m.Lote)) == 0


# ----------------------------------------------------------------------------- asignación y código
def test_asignar_reserva_inventario_y_guarda_solo_la_huella(db, mundo):
    lote = donar(db, mundo, 100)
    sol = pedir(db, mundo, cantidad=30)
    e = sv.asignar(db, sol, mundo["equipo"], mundo["entidad"], SECRETO)
    lote_de(db, lote)
    assert (lote.cantidad_disponible, lote.cantidad_reservada) == (70, 30)
    assert sol.estado == m.EstadoSolicitud.ASIGNADA and e.estado_codigo == "activo"
    codigo = sv.codigo_para(SECRETO, e.id, e.codigo_sal)
    assert len(codigo) == sv.LARGO_CODIGO and codigo not in e.codigo_hash
    assert e.codigo_hash == sv.huella_codigo(e.codigo_sal, codigo)  # lo que valida el dispositivo sin conexión
    assert sv.huella_codigo(e.codigo_sal, sv.con_guion(codigo.lower())) == e.codigo_hash  # tolera guion y minúsculas


def test_sin_inventario_suficiente_no_cambia_nada(db, mundo):
    lote = donar(db, mundo, 20)
    sol = pedir(db, mundo, cantidad=30)
    with pytest.raises(sv.ErrorNegocio, match="No hay inventario suficiente"):
        sv.asignar(db, sol, mundo["equipo"], mundo["entidad"], SECRETO)
    lote_de(db, lote)
    assert (lote.cantidad_disponible, lote.cantidad_reservada) == (20, 0)
    assert sol.estado == m.EstadoSolicitud.VERIFICADA and db.scalar(select(func.count()).select_from(m.Entrega)) == 0


def test_solo_se_asigna_lo_verificado_y_a_equipos_aprobados(db, mundo):
    donar(db, mundo, 50)
    with pytest.raises(sv.ErrorNegocio, match="verificada"):
        sv.asignar(db, pedir(db, mundo, estado=m.EstadoSolicitud.REGISTRADA), mundo["equipo"], mundo["entidad"], SECRETO)
    mundo["equipo"].aprobado = False
    with pytest.raises(sv.ErrorNegocio, match="aprobado"):
        sv.asignar(db, pedir(db, mundo), mundo["equipo"], mundo["entidad"], SECRETO)
    with pytest.raises(sv.ErrorNegocio, match="aprobado"):
        sv.asignar(db, pedir(db, mundo), mundo["solicitante"], mundo["entidad"], SECRETO)


def test_primero_en_vencer_primero_en_salir_y_sin_vencidos(db, mundo):
    tarde = donar(db, mundo, 50, dias=90)
    pronto = donar(db, mundo, 50, dias=5)
    vencido = donar(db, mundo, 50, dias=-1)
    sol = pedir(db, mundo, cantidad=60)
    sv.asignar(db, sol, mundo["equipo"], mundo["entidad"], SECRETO)
    for lote in (tarde, pronto, vencido):
        lote_de(db, lote)
    assert pronto.cantidad_reservada == 50 and tarde.cantidad_reservada == 10  # vence antes, sale antes
    assert vencido.cantidad_reservada == 0 and vencido.cantidad_disponible == 50  # no se entrega vencido


def test_los_lotes_dirigidos_solo_van_a_su_destino(db, mundo):
    dirigido = donar(db, mundo, 100, destino_sector_id=mundo["otro"].id)
    general = donar(db, mundo, 10)
    sol = pedir(db, mundo, cantidad=10)  # el sector de la solicitud es el 1, no el 2
    sv.asignar(db, sol, mundo["equipo"], mundo["entidad"], SECRETO)
    assert lote_de(db, dirigido).cantidad_reservada == 0 and lote_de(db, general).cantidad_reservada == 10
    otra = pedir(db, mundo, cantidad=5)
    with pytest.raises(sv.ErrorNegocio, match="No hay inventario suficiente"):
        sv.asignar(db, otra, mundo["equipo"], mundo["entidad"], SECRETO)  # el dirigido no es para este sector


# ----------------------------------------------------------------------------- entrega
def _asignada(db, mundo, cantidad=30):
    lote = donar(db, mundo, 100)
    sol = pedir(db, mundo, cantidad=cantidad)
    e = sv.asignar(db, sol, mundo["equipo"], mundo["entidad"], SECRETO)
    return lote, sol, e, sv.codigo_para(SECRETO, e.id, e.codigo_sal)


def test_entrega_con_el_codigo_correcto(db, mundo):
    lote, sol, e, codigo = _asignada(db, mundo)
    sv.en_camino(db, e, mundo["equipo"])
    assert sol.estado == m.EstadoSolicitud.EN_CAMINO
    assert sv.confirmar_entrega(db, e, mundo["equipo"], sv.con_guion(codigo)) is False
    lote_de(db, lote)
    assert (lote.cantidad_disponible, lote.cantidad_reservada, lote.cantidad_entregada) == (70, 0, 30)
    assert sol.estado == m.EstadoSolicitud.ENTREGADA and e.estado_codigo == "usado" and e.entregada_en
    # reenviar desde un dispositivo que estuvo sin conexión no duplica ni da error
    assert sv.confirmar_entrega(db, e, mundo["equipo"], codigo) is True
    assert lote_de(db, lote).cantidad_entregada == 30


def test_un_codigo_incorrecto_o_de_otro_equipo_se_rechaza(db, mundo):
    lote, sol, e, codigo = _asignada(db, mundo)
    with pytest.raises(sv.ErrorNegocio, match="no es correcto"):
        sv.confirmar_entrega(db, e, mundo["equipo"], "AAAAAAAA")
    with pytest.raises(sv.ErrorNegocio, match="otro equipo"):
        sv.confirmar_entrega(db, e, mundo["equipo2"], codigo)
    assert sol.estado == m.EstadoSolicitud.ASIGNADA and lote_de(db, lote).cantidad_entregada == 0


def test_el_codigo_de_una_entrega_no_sirve_para_otra(db, mundo):
    donar(db, mundo, 100)
    e1 = sv.asignar(db, pedir(db, mundo, cantidad=10), mundo["equipo"], mundo["entidad"], SECRETO)
    e2 = sv.asignar(db, pedir(db, mundo, cantidad=10), mundo["equipo"], mundo["entidad"], SECRETO)
    c1 = sv.codigo_para(SECRETO, e1.id, e1.codigo_sal)
    with pytest.raises(sv.ErrorNegocio, match="no es correcto"):
        sv.confirmar_entrega(db, e2, mundo["equipo"], c1)


def test_cinco_intentos_fallidos_invalidan_el_codigo(db, mundo):
    _, sol, e, codigo = _asignada(db, mundo)
    for _ in range(sv.MAX_INTENTOS_CODIGO - 1):
        with pytest.raises(sv.ErrorNegocio, match="no es correcto"):
            sv.confirmar_entrega(db, e, mundo["equipo"], "BBBBBBBB")
    with pytest.raises(sv.ErrorNegocio, match="Demasiados intentos"):
        sv.confirmar_entrega(db, e, mundo["equipo"], "BBBBBBBB")
    with pytest.raises(sv.ErrorNegocio, match="ya se usó o dejó de valer"):
        sv.confirmar_entrega(db, e, mundo["equipo"], codigo)  # ni el código correcto sirve ya


def test_un_codigo_vencido_se_rechaza(db, mundo):
    _, _, e, codigo = _asignada(db, mundo)
    e.vence_en = ahora() - timedelta(minutes=1)
    with pytest.raises(sv.ErrorNegocio, match="venció"):
        sv.confirmar_entrega(db, e, mundo["equipo"], codigo)


def test_incidencia_libera_el_inventario_y_permite_reasignar(db, mundo):
    lote, sol, e, codigo = _asignada(db, mundo)
    sv.registrar_incidencia(db, e, mundo["equipo"], "no_encontrada", "No estaba en casa")
    assert sol.estado == m.EstadoSolicitud.VERIFICADA and e.estado_codigo == "invalidado"
    assert (lote_de(db, lote).cantidad_disponible, lote.cantidad_reservada) == (100, 0)
    with pytest.raises(sv.ErrorNegocio, match="ya se usó o dejó de valer"):
        sv.confirmar_entrega(db, e, mundo["equipo"], codigo)

    e2 = sv.asignar(db, sol, mundo["equipo2"], mundo["entidad"], SECRETO)  # se reasigna a otro equipo
    assert e2.id != e.id and sv.codigo_para(SECRETO, e2.id, e2.codigo_sal) != codigo
    assert sv.entrega_activa(db, sol.id).id == e2.id


def test_el_inventario_siempre_cuadra(db, mundo):
    """Tras reservar, liberar y entregar varias solicitudes, los saldos cuadran (lo exige una restricción)."""
    lote = donar(db, mundo, 100)
    solicitudes = [pedir(db, mundo, cantidad=c) for c in (10, 25, 40)]
    entregas = [sv.asignar(db, s, mundo["equipo"], mundo["entidad"], SECRETO) for s in solicitudes]
    sv.registrar_incidencia(db, entregas[0], mundo["equipo"], "rechazo", "")
    for e in entregas[1:]:
        sv.confirmar_entrega(db, e, mundo["equipo"], sv.codigo_para(SECRETO, e.id, e.codigo_sal))
    lote_de(db, lote)
    assert (lote.cantidad_disponible, lote.cantidad_reservada, lote.cantidad_entregada) == (35, 0, 65)
    assert lote.cantidad_disponible + lote.cantidad_reservada + lote.cantidad_entregada == lote.cantidad_recibida


# ----------------------------------------------------------------------------- seguimiento y auditoría
def test_la_solicitante_confirma_y_cierra(db, mundo):
    _, sol, e, codigo = _asignada(db, mundo)
    with pytest.raises(sv.ErrorNegocio, match="todavía no figura"):
        sv.cerrar_solicitud(db, sol, mundo["solicitante"])
    sv.confirmar_entrega(db, e, mundo["equipo"], codigo)
    with pytest.raises(sv.ErrorNegocio, match="Solo la persona"):
        sv.cerrar_solicitud(db, sol, mundo["brigadista"])
    sv.cerrar_solicitud(db, sol, mundo["solicitante"])
    assert sol.estado == m.EstadoSolicitud.CERRADA


def test_la_cadena_de_eventos_detecta_alteraciones(db, mundo):
    _, sol, e, codigo = _asignada(db, mundo)
    sv.en_camino(db, e, mundo["equipo"])
    sv.confirmar_entrega(db, e, mundo["equipo"], codigo)
    sv.cerrar_solicitud(db, sol, mundo["solicitante"])
    tipos = [ev.tipo for ev in db.scalars(select(m.EventoAuditoria).order_by(m.EventoAuditoria.id))]
    assert tipos == ["asignada", "en_camino", "entregada", "cerrada"]
    assert sv.verificar_cadena(db) == (True, None)

    segundo = db.scalars(select(m.EventoAuditoria).order_by(m.EventoAuditoria.id)).all()[1]
    db.execute(update(m.EventoAuditoria).where(m.EventoAuditoria.id == segundo.id).values(tipo="otra_cosa"))
    db.commit()
    db.expire_all()
    assert sv.verificar_cadena(db) == (False, segundo.id)


def test_la_cadena_no_guarda_datos_personales(db, mundo):
    _asignada(db, mundo)
    ev = db.scalar(select(m.EventoAuditoria))
    columnas = {c.name for c in m.EventoAuditoria.__table__.columns}
    assert columnas == {"id", "solicitud_id", "tipo", "hora", "hash_previo", "hash"}
    assert "Solicitante" not in f"{ev.tipo}{ev.hash}"
