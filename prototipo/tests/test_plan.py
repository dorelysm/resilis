from datetime import timedelta

import pytest
from sqlalchemy import func, select

from app import models as m
from app import plan as pl
from app import servicios as sv
from app.models import ahora
from tests.test_servicios import SECRETO, donar, mundo, pedir, usuario  # noqa: F401


@pytest.fixture()
def listo(db, mundo):
    """El mundo de las pruebas de servicios, con los equipos de entrega en condiciones de entrar (con contraseña)."""
    for clave in ("equipo", "equipo2"):
        mundo[clave].password_hash = "x"
    db.flush()
    return mundo


def hacer_plan(db, mundo):
    return pl.calcular_plan(db, mundo["entidad"])


def lineas(db, plan):
    return db.scalars(select(m.PlanLinea).where(m.PlanLinea.plan_id == plan.id).order_by(m.PlanLinea.id)).all()


def resumen(db, plan):
    return db.get(m.PlanResumen, plan.id).datos


# ----------------------------------------------------------------------------- cálculo
def test_sin_solicitudes_verificadas_o_sin_inventario_no_hay_plan(db, listo):
    assert hacer_plan(db, listo) is None
    donar(db, listo, 50)
    assert hacer_plan(db, listo) is None  # hay inventario pero ninguna solicitud verificada
    pedir(db, listo, estado=m.EstadoSolicitud.REGISTRADA)
    assert hacer_plan(db, listo) is None  # la solicitud todavía no está verificada


def test_el_plan_cubre_las_solicitudes_verificadas_y_se_explica(db, listo):
    donar(db, listo, 100)
    a, b = pedir(db, listo, cantidad=30), pedir(db, listo, cantidad=20)
    pedir(db, listo, cantidad=10, estado=m.EstadoSolicitud.REGISTRADA)  # esta no entra
    plan = hacer_plan(db, listo)
    assert plan.estado == m.EstadoPlan.PROPUESTO and plan.necesidad_total == 50 and plan.necesidad_cubierta == 50
    ls = lineas(db, plan)
    assert {l.solicitud_id for l in ls} == {a.id, b.id}
    assert all("Prioridad" in l.razon and "Lote" in l.razon and "km" in l.razon and "Cubre" in l.razon for l in ls)
    r = resumen(db, plan)
    assert r["estado_solucionador"] == "óptimo" and r["sin_cubrir"] == []
    assert r["cubierta_ponderada"] >= r["cubierta_ponderada_voraz"] - 1e-9


def test_el_plan_no_pasa_del_inventario_y_dice_lo_que_falta(db, listo):
    donar(db, listo, 25)
    for c in (20, 20, 20):
        pedir(db, listo, cantidad=c)
    plan = hacer_plan(db, listo)
    assert plan.necesidad_cubierta == 25 and plan.necesidad_total == 60
    r = resumen(db, plan)
    assert sum(x["falta"] for x in r["sin_cubrir"]) == 35 and all(x["motivo"] for x in r["sin_cubrir"])
    assert r["por_tipo"]["agua"] == {"demanda": 60, "disponible": 25, "asignado": 25}
    usado = sum(l.cantidad for l in lineas(db, plan))
    assert usado == 25


def test_no_se_planea_con_lotes_vencidos_ni_con_los_dirigidos_a_otro_destino(db, listo):
    donar(db, listo, 100, dias=-1)  # vencido
    donar(db, listo, 100, destino_sector_id=listo["otro"].id)  # dirigido a otro sector
    sol = pedir(db, listo, cantidad=10)  # la solicitud es del sector 1
    vacio = hacer_plan(db, listo)  # hay inventario, pero ninguno sirve: el plan no asigna nada y dice por qué
    assert lineas(db, vacio) == [] and vacio.necesidad_cubierta == 0
    sin = resumen(db, vacio)["sin_cubrir"]
    assert sin[0]["solicitud_id"] == sol.id and "No hay inventario compatible" in sin[0]["motivo"]
    general = donar(db, listo, 10)
    plan = hacer_plan(db, listo)
    assert {l.lote_id for l in lineas(db, plan)} == {general.id}


def test_los_equipos_se_reparten_la_carga(db, listo):
    donar(db, listo, 500)
    for _ in range(4):
        pedir(db, listo, cantidad=10)
    plan = hacer_plan(db, listo)
    por_equipo = {}
    for l in lineas(db, plan):
        por_equipo[l.equipo_id] = por_equipo.get(l.equipo_id, 0) + 1
    assert sorted(por_equipo.values()) == [2, 2]


def test_sin_equipos_que_puedan_entrar_el_plan_lo_avisa(db, mundo):
    donar(db, mundo, 100)
    pedir(db, mundo, cantidad=10)
    plan = hacer_plan(db, mundo)  # los equipos del mundo no tienen contraseña: no pueden entrar
    assert resumen(db, plan)["sin_equipos"] is True and all(l.equipo_id is None for l in lineas(db, plan))


def test_un_plan_nuevo_reemplaza_al_anterior(db, listo):
    donar(db, listo, 100)
    pedir(db, listo, cantidad=10)
    primero = hacer_plan(db, listo)
    segundo = hacer_plan(db, listo)
    db.refresh(primero)
    assert primero.estado == m.EstadoPlan.RECHAZADO and "Reemplazado" in resumen(db, primero)["motivo_rechazo"]
    assert segundo.estado == m.EstadoPlan.PROPUESTO


def test_calcular_el_plan_no_reserva_nada(db, listo):
    lote = donar(db, listo, 100)
    sol = pedir(db, listo, cantidad=30)
    hacer_plan(db, listo)
    db.refresh(lote)
    assert (lote.cantidad_disponible, lote.cantidad_reservada) == (100, 0) and sol.estado == "verificada"
    assert db.scalar(select(func.count()).select_from(m.Entrega)) == 0  # solo lo aprobado reserva


# ----------------------------------------------------------------------------- aprobación
def test_aprobar_el_plan_reserva_asigna_y_genera_codigos(db, listo):
    lote = donar(db, listo, 100)
    a, b = pedir(db, listo, cantidad=30), pedir(db, listo, cantidad=20)
    plan = hacer_plan(db, listo)
    r = pl.aprobar_plan(db, plan, listo["entidad"], SECRETO)
    assert r["asignadas"] == 2 and r["omitidas"] == []
    db.refresh(lote)
    assert (lote.cantidad_disponible, lote.cantidad_reservada) == (50, 50)
    assert a.estado == b.estado == m.EstadoSolicitud.ASIGNADA
    entregas = db.scalars(select(m.Entrega)).all()
    assert len(entregas) == 2 and all(e.estado_codigo == "activo" and e.codigo_hash for e in entregas)
    assert plan.estado == m.EstadoPlan.APROBADO and plan.aprobado_por == listo["entidad"].id
    assert resumen(db, plan)["resultado"]["asignadas"] == sorted([a.id, b.id])
    movimientos = db.scalars(select(m.MovimientoInventario).where(m.MovimientoInventario.tipo == "reserva")).all()
    assert {mv.plan_id for mv in movimientos} == {plan.id}
    with pytest.raises(sv.ErrorNegocio, match="ya fue resuelto"):
        pl.aprobar_plan(db, plan, listo["entidad"], SECRETO)


def test_se_puede_excluir_una_solicitud_y_cambiar_su_equipo(db, listo):
    donar(db, listo, 100)
    a, b = pedir(db, listo, cantidad=10), pedir(db, listo, cantidad=10)
    plan = hacer_plan(db, listo)
    pl.aprobar_plan(db, plan, listo["entidad"], SECRETO, equipos={a.id: listo["equipo2"].id}, excluir={b.id})
    assert a.estado == m.EstadoSolicitud.ASIGNADA and b.estado == m.EstadoSolicitud.VERIFICADA
    assert sv.entrega_activa(db, a.id).equipo_id == listo["equipo2"].id
    assert sv.entrega_activa(db, b.id) is None
    assert resumen(db, plan)["resultado"]["excluidas"] == [b.id]


def test_si_el_inventario_cambio_se_omite_lo_que_ya_no_se_puede(db, listo):
    lote = donar(db, listo, 40)
    a, b = pedir(db, listo, cantidad=30), pedir(db, listo, cantidad=10)
    plan = hacer_plan(db, listo)
    assert plan.necesidad_cubierta == 40
    lote.cantidad_disponible -= 25  # otra entrega manual consumió inventario después de calcular el plan
    lote.cantidad_reservada += 25
    db.flush()
    r = pl.aprobar_plan(db, plan, listo["entidad"], SECRETO)
    assert r["asignadas"] + len(r["omitidas"]) == 2 and len(r["omitidas"]) >= 1
    assert "ya no tiene" in r["omitidas"][0]["motivo"]
    db.refresh(lote)
    assert lote.cantidad_disponible >= 0 and lote.cantidad_disponible + lote.cantidad_reservada == 40  # nada se rompe


def test_una_entrega_parcial_deja_pendiente_el_resto(db, listo):
    """Si el inventario solo alcanza para una parte, se entrega esa parte y la solicitud sigue abierta."""
    lote = donar(db, listo, 20)
    sol = pedir(db, listo, cantidad=30)
    plan = hacer_plan(db, listo)
    assert plan.necesidad_cubierta == 20
    pl.aprobar_plan(db, plan, listo["entidad"], SECRETO)
    e = sv.entrega_activa(db, sol.id)
    sv.confirmar_entrega(db, e, listo["equipo"], sv.codigo_para(SECRETO, e.id, e.codigo_sal)) if e.equipo_id == listo["equipo"].id \
        else sv.confirmar_entrega(db, e, listo["equipo2"], sv.codigo_para(SECRETO, e.id, e.codigo_sal))
    db.refresh(lote)
    assert lote.cantidad_entregada == 20 and lote.cantidad_reservada == 0
    assert sol.estado == m.EstadoSolicitud.VERIFICADA and sol.cantidad == 10  # faltan 10
    tipos = [ev.tipo for ev in db.scalars(select(m.EventoAuditoria).order_by(m.EventoAuditoria.id))]
    assert "entrega_parcial" in tipos and "entregada" not in tipos
    # con una donación nueva se puede completar
    donar(db, listo, 50)
    plan2 = hacer_plan(db, listo)
    assert plan2.necesidad_cubierta == 10


def test_rechazar_el_plan_no_toca_el_inventario(db, listo):
    lote = donar(db, listo, 100)
    sol = pedir(db, listo, cantidad=30)
    plan = hacer_plan(db, listo)
    pl.rechazar_plan(db, plan, listo["entidad"], "Prefiero revisarlo a mano")
    db.refresh(lote)
    assert plan.estado == m.EstadoPlan.RECHAZADO and (lote.cantidad_disponible, lote.cantidad_reservada) == (100, 0)
    assert sol.estado == m.EstadoSolicitud.VERIFICADA and "Prefiero" in resumen(db, plan)["motivo_rechazo"]
    with pytest.raises(sv.ErrorNegocio, match="ya fue resuelto"):
        pl.rechazar_plan(db, plan, listo["entidad"])


def test_el_inventario_siempre_cuadra_despues_de_aprobar_planes(db, listo):
    """Varios planes seguidos, con entregas y una incidencia: los saldos de cada lote nunca se descuadran."""
    lotes = [donar(db, listo, 60, dias=3), donar(db, listo, 80), donar(db, listo, 40, dias=30)]
    for c in (25, 40, 30, 55, 15):
        pedir(db, listo, cantidad=c)
    plan = hacer_plan(db, listo)
    pl.aprobar_plan(db, plan, listo["entidad"], SECRETO)
    entregas = db.scalars(select(m.Entrega)).all()
    equipos = {listo["equipo"].id: listo["equipo"], listo["equipo2"].id: listo["equipo2"]}
    sv.registrar_incidencia(db, entregas[0], equipos[entregas[0].equipo_id], "no_encontrada", "")
    for e in entregas[1:]:
        sv.confirmar_entrega(db, e, equipos[e.equipo_id], sv.codigo_para(SECRETO, e.id, e.codigo_sal))
    for lote in lotes:
        db.refresh(lote)
        assert lote.cantidad_disponible + lote.cantidad_reservada + lote.cantidad_entregada == lote.cantidad_recibida
        assert min(lote.cantidad_disponible, lote.cantidad_reservada, lote.cantidad_entregada) >= 0


def test_el_primero_en_vencer_sale_primero_en_el_plan(db, listo):
    tarde = donar(db, listo, 50, dias=200)
    pronto = donar(db, listo, 50, dias=2)
    pedir(db, listo, cantidad=40)
    plan = hacer_plan(db, listo)
    assert {l.lote_id for l in lineas(db, plan)} == {pronto.id}
    assert tarde.id not in {l.lote_id for l in lineas(db, plan)}


# ----------------------------------------------------------------------------- parámetros y utilidades
def test_los_parametros_se_guardan_y_cambian_el_plan(db, listo):
    assert pl.leer_parametros(db)["theta"] == pytest.approx(0.3)
    guardados = pl.guardar_parametros(db, {"theta": 0.6, "kappa": 0.1, "no_existe": 5}, listo["entidad"])
    assert guardados["theta"] == pytest.approx(0.6) and "no_existe" not in guardados
    donar(db, listo, 10)
    pedir(db, listo, cantidad=10)
    plan = hacer_plan(db, listo)
    assert resumen(db, plan)["parametros"]["theta"] == pytest.approx(0.6)
    assert db.scalar(select(m.Bitacora).where(m.Bitacora.accion == "cambiar_parametros_plan")) is not None


def test_distancia_en_kilometros():
    # Barranquilla - Soledad: unos 6 km en línea recta
    assert 5.0 < pl.kilometros((10.9685, -74.7813), (10.9184, -74.7646)) < 7.5
    assert pl.kilometros((10.9, -74.8), (10.9, -74.8)) == pytest.approx(0.0, abs=1e-9)
    assert pl.kilometros((None, None), (10.9, -74.8)) == 5.0  # sin ubicación: distancia media


def test_urgencia_de_uso_por_vencimiento():
    ahora_ = ahora()
    assert pl.urgencia_de_uso(None, ahora_) == 0.0
    assert pl.urgencia_de_uso(ahora_ - timedelta(days=1), ahora_) == 1.0
    assert pl.urgencia_de_uso(ahora_ + timedelta(days=90), ahora_) == 0.0
    cerca, lejos = pl.urgencia_de_uso(ahora_ + timedelta(days=5), ahora_), pl.urgencia_de_uso(ahora_ + timedelta(days=40), ahora_)
    assert 0 < lejos < cerca < 1
