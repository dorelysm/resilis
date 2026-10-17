"""Recorrido: el camino de cada solicitud, donación y reporte, y el panel de etapas."""
from datetime import timedelta

import pytest
from sqlalchemy import select

from app import models as m
from app import recorrido as rc
from tests.test_operacion import (  # noqa: F401
    _Revisor, app_cliente, asignar, csrf, entrar, equipo_completo, flujo_hasta_asignar, mundo, pedir,
    recibir_inventario, salir, sesiones, verificar,
)


def estados(pasos):
    return {p["clave"]: p["estado"] for p in pasos}


def test_una_solicitud_recien_hecha_va_en_la_verificacion(app_cliente, sesiones, equipo_completo, mundo):
    pedir(app_cliente, mundo)
    with sesiones() as db:
        pasos = rc.pasos_solicitud(db, db.get(m.Solicitud, 1))
    assert estados(pasos) == {"registrada": "hecho", "verificada": "actual", "asignada": "pendiente",
                              "en_camino": "pendiente", "entregada": "pendiente", "cerrada": "pendiente"}
    assert pasos[0]["hora"] is not None


def test_el_recorrido_avanza_hasta_asignada_y_dice_el_equipo(app_cliente, sesiones, equipo_completo, mundo):
    flujo_hasta_asignar(app_cliente, equipo_completo, mundo)
    with sesiones() as db:
        sol = db.get(m.Solicitud, 1)
        pasos = rc.pasos_solicitud(db, sol)
        sin_equipo = rc.pasos_solicitud(db, sol, mostrar_equipo=False)
    assert estados(pasos)["verificada"] == "hecho" and estados(pasos)["asignada"] == "hecho"
    assert estados(pasos)["en_camino"] == "actual"
    assert pasos[2]["nota"].startswith("Equipo:") and sin_equipo[2]["nota"] == ""


def test_una_solicitud_desmentida_muestra_el_problema(app_cliente, sesiones, equipo_completo, mundo):
    pedir(app_cliente, mundo)
    verificar(app_cliente, 1, resultado="desmentido", nota="No hay nadie en esa casa")
    with sesiones() as db:
        pasos = rc.pasos_solicitud(db, db.get(m.Solicitud, 1))
    assert estados(pasos)["verificada"] == "problema" and pasos[1]["nota"] == "No se pudo verificar."
    assert "actual" not in estados(pasos).values()  # no hay "siguiente": el camino terminó


def test_una_donacion_pasa_de_ofrecida_a_en_inventario(app_cliente, sesiones, equipo_completo, mundo):
    ids = equipo_completo
    with sesiones() as db:
        antes = rc.pasos_donacion(db, db.get(m.Donacion, ids["donacion"]))
    assert estados(antes)["ofrecida"] == "hecho" and estados(antes)["recibida"] == "actual"
    recibir_inventario(app_cliente, ids, 100)
    with sesiones() as db:
        pasos = rc.pasos_donacion(db, db.get(m.Donacion, ids["donacion"]))
    assert estados(pasos)["inventario"] == "hecho" and estados(pasos)["reservada"] == "actual"
    assert pasos[1]["nota"].startswith("Llegaron 100")


def test_un_reporte_desmentido_ya_no_cuenta(app_cliente, sesiones, equipo_completo, mundo):
    with sesiones() as db:
        autor = db.scalar(select(m.Usuario).where(m.Usuario.rol == "solicitante"))
        evento = m.Evento(tipo="inundacion", nombre="Prueba")
        db.add(evento)
        db.flush()
        rep = m.ReporteDanos(barrio_id=mundo["barrio_id"], evento_id=evento.id, autor_id=autor.id,
                             hora_evento=m.ahora(), nivel_dano=2)
        db.add(rep)
        db.flush()
        sin_revisar = rc.pasos_reporte(db, rep)
        db.add(m.Verificacion(objeto_tipo="reporte", objeto_id=rep.id, verificador_id=autor.id, resultado="desmentido"))
        db.flush()
        desmentido = rc.pasos_reporte(db, rep)
    assert estados(sin_revisar)["revisado"] == "actual" and estados(sin_revisar)["prioridad"] == "hecho"
    assert estados(desmentido)["revisado"] == "problema" and estados(desmentido)["prioridad"] == "pendiente"


def test_el_panel_cuenta_cada_etapa_y_marca_la_espera_larga(app_cliente, sesiones, equipo_completo, mundo):
    ids = equipo_completo
    recibir_inventario(app_cliente, ids)
    for _ in range(3):
        pedir(app_cliente, mundo)
    verificar(app_cliente, 1)
    with sesiones() as db:  # la solicitud 2 lleva 10 horas sin que nadie la verifique
        db.get(m.Solicitud, 2).creado_en = m.ahora() - timedelta(hours=10)
        db.commit()
        panel = {r["tipo"]: r for r in rc.panel(db)}
        cuentas = {e["clave"]: e for e in panel["solicitud"]["etapas"]}
        assert cuentas["registrada"]["cantidad"] == 2 and cuentas["verificada"]["cantidad"] == 1
        assert cuentas["registrada"]["espera_larga"] and cuentas["registrada"]["espera_horas"] >= 10
        assert not cuentas["verificada"]["espera_larga"]
        assert sum(e["cantidad"] for e in panel["solicitud"]["etapas"]) + panel["solicitud"]["aparte"][0]["cantidad"] == 3
        donaciones = {e["clave"]: e["cantidad"] for e in panel["donacion"]["etapas"]}
        assert donaciones["en_inventario"] == 1 and donaciones["ofrecida"] == 0


def test_solo_quienes_deciden_ven_el_panel(app_cliente, sesiones, equipo_completo, mundo):
    c = app_cliente
    flujo_hasta_asignar(c, equipo_completo, mundo)
    assert c.get("/recorrido", follow_redirects=False).status_code == 303
    for tel in ("3100000001", "3100000005", "3100000007"):  # solicitante, equipo de entrega, centro de acopio
        entrar(c, tel)
        assert c.get("/recorrido").status_code == 403 and c.get("/recorrido/solicitudes/1").status_code == 403, tel
        salir(c)
    for tel in ("3100000004", "3100000003", "3100000008"):  # entidad, brigadista, administrador
        entrar(c, tel)
        assert c.get("/recorrido").status_code == 200, tel
        salir(c)


def test_tocar_una_etapa_muestra_lo_que_hay_y_no_datos_personales(app_cliente, sesiones, equipo_completo, mundo):
    c = app_cliente
    flujo_hasta_asignar(c, equipo_completo, mundo)
    entrar(c, "3100000004")
    pagina = c.get("/recorrido?tipo=solicitud&etapa=asignada").text
    assert "Solicitudes de ayuda: Con equipo" in pagina and "/recorrido/solicitudes/1" in pagina
    assert "Usuario solicitante" not in pagina.split('id="lista"')[1].split("<footer>")[0]  # ni el nombre de la persona
    assert "Elija una etapa" in c.get("/recorrido").text
    assert "Elija una etapa" in c.get("/recorrido?tipo=inventado&etapa=x").text  # un valor raro se ignora
    detalle = c.get("/recorrido/solicitudes/1").text
    assert "Recorrido de la solicitud 1" in detalle and "Equipo asignado" in detalle and "3100000001" not in detalle
    assert c.get("/recorrido/solicitudes/999").status_code == 404


def test_las_paginas_del_recorrido_son_accesibles(app_cliente, sesiones, equipo_completo, mundo):
    c = app_cliente
    flujo_hasta_asignar(c, equipo_completo, mundo)
    entrar(c, "3100000004")
    for ruta in ("/recorrido", "/recorrido?tipo=solicitud&etapa=asignada", "/recorrido/solicitudes/1"):
        r = c.get(ruta)
        revisor = _Revisor()
        revisor.feed(r.text)
        assert r.status_code == 200 and revisor.lang == "es" and revisor.ids <= revisor.para, ruta
        assert 'aria-label="Recorrido' in r.text or "etapas" in r.text
    salir(c)
    entrar(c, "3100000001")  # la persona ve su propio recorrido en su página
    assert 'aria-current="step"' in c.get("/solicitudes/1").text
