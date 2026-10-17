import re

import pytest
from sqlalchemy import select

from app import models as m
from tests.test_operacion import (  # noqa: F401
    _Revisor, app_cliente, asignar, crear_usuario, csrf, entrar, equipo_completo, mundo, pedir, recibir_inventario,
    salir, sesiones, verificar,
)


def reportar(c, mundo, telefono="3100000003", nivel="3", personas="300"):
    entrar(c, telefono)
    c.post("/reportes/nuevo", data={"barrio_id": str(mundo["barrio_id"]), "nivel_dano": nivel,
                                    "personas_afectadas": personas, "acceso": "1",
                                    "csrf": csrf(c, "/reportes/nuevo")})
    salir(c)


def test_los_formularios_actualizan_las_prioridades_solos(app_cliente, sesiones, equipo_completo, mundo):
    c = app_cliente
    assert pedir(c, mundo).status_code == 303
    with sesiones() as db:
        sol = db.get(m.Solicitud, 1)
        assert sol.prioridad is not None and sol.confianza is not None  # se calculó al registrarla
        antes = sol.confianza
    verificar(c, 1)
    with sesiones() as db:
        assert db.get(m.Solicitud, 1).confianza > antes  # verificar subió la confianza
    reportar(c, mundo)
    with sesiones() as db:
        p = db.get(m.PuntajeBarrio, mundo["barrio_id"])
        assert p.n_reportes == 1 and p.confianza > 0 and "sin_reportes" not in p.alertas


def test_permisos_de_las_paginas_de_prioridades(app_cliente, equipo_completo, mundo):
    c = app_cliente
    entrar(c, "3100000001")  # una persona que pide ayuda no ve las prioridades
    assert c.get("/prioridades").status_code == 403
    assert c.get("/pesos").status_code == 403
    salir(c)
    entrar(c, "3100000003")  # el brigadista ve, pero no cambia los pesos
    assert c.get("/prioridades").status_code == 200
    assert c.get("/pesos").status_code == 403
    assert c.post("/pesos/barrio", data={"csrf": csrf(c, "/prioridades")}).status_code == 403
    salir(c)
    entrar(c, "3100000004")  # la entidad sí
    assert c.get("/pesos").status_code == 200


def test_la_pagina_de_prioridades_muestra_barrios_y_solicitudes(app_cliente, equipo_completo, mundo):
    c = app_cliente
    pedir(c, mundo)
    reportar(c, mundo)
    entrar(c, "3100000004")
    pagina = c.get("/prioridades").text
    assert "Barrio de prueba" in pagina and "Agua</strong> · 12 litros" in pagina and "Por verificar" in pagina
    assert "Una confianza baja quiere decir que hay que verificar" in pagina
    detalle = c.get(f"/prioridades/barrios/{mundo['barrio_id']}").text
    assert "Por qué ocupa este lugar" in detalle and "Gravedad de la afectación" in detalle
    assert "no penaliza" in detalle
    assert c.get("/prioridades/barrios/9999").status_code == 404


def test_un_barrio_sin_reportes_dice_que_hay_que_verificar(app_cliente, equipo_completo, mundo):
    entrar(app_cliente, "3100000004")
    app_cliente.get("/prioridades")  # calcula la primera vez
    detalle = app_cliente.get(f"/prioridades/barrios/{mundo['barrio_id']}").text
    assert "No tiene reportes" in detalle and "Conviene enviar a alguien a verificar" in detalle


def test_cambiar_los_pesos_recalcula(app_cliente, sesiones, equipo_completo, mundo):
    c = app_cliente
    entrar(c, "3100000004")
    r = c.post("/pesos/barrio", follow_redirects=False, data={
        "barrio_gravedad": "50", "barrio_urgencia": "50", "barrio_expuestas": "0", "barrio_accesibilidad": "0",
        "barrio_recursos": "0", "csrf": csrf(c, "/pesos")})
    assert r.status_code == 303
    pagina = c.get("/pesos").text
    assert "hoy: 50 %" in pagina  # los pesos quedaron normalizados a 100 %
    with sesiones() as db:
        pesos = {p.dimension: p.valor for p in db.scalars(select(m.Peso).where(m.Peso.ambito == "barrio"))}
        assert pesos["gravedad"] == pytest.approx(0.5) and sum(pesos.values()) == pytest.approx(1.0)
        assert db.scalar(select(m.Bitacora).where(m.Bitacora.accion == "cambiar_pesos")) is not None


def test_los_pesos_no_validos_se_rechazan(app_cliente, sesiones, equipo_completo):
    c = app_cliente
    entrar(c, "3100000004")
    base = {"barrio_gravedad": "30", "barrio_urgencia": "25", "barrio_expuestas": "25", "barrio_accesibilidad": "10",
            "barrio_recursos": "10"}
    for cambio, mensaje in [({"barrio_gravedad": "abc"}, "Escriba un número"),
                            ({"barrio_gravedad": "150"}, "entre 0 y 100"),
                            ({"barrio_gravedad": "-5"}, "entre 0 y 100")]:
        r = c.post("/pesos/barrio", data={**base, **cambio, "csrf": csrf(c, "/pesos")})
        assert r.status_code == 422 and mensaje in r.text, cambio
    todos_cero = {k: "0" for k in base}
    r = c.post("/pesos/barrio", data={**todos_cero, "csrf": csrf(c, "/pesos")})
    assert r.status_code == 422 and "Al menos un peso debe ser mayor que cero" in r.text
    assert c.post("/pesos/otra_cosa", data={**base, "csrf": csrf(c, "/pesos")}).status_code == 404
    with sesiones() as db:
        assert db.scalar(select(m.Peso)) is None  # nada se guardó


def test_la_asignacion_muestra_la_prioridad_y_ordena_por_ella(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    recibir_inventario(c, ids, 500)
    pedir(c, mundo, hogar="2")      # solicitud 1
    pedir(c, mundo, hogar="2")      # solicitud 2
    with sesiones() as db:  # la 2 es más urgente y vulnerable
        s2 = db.get(m.Solicitud, 2)
        s2.urgencia = 3
        db.add(m.Vulnerabilidad(solicitud_id=2, tipo="discapacidad", descripcion_situacion="x", consentimiento=True))
        db.commit()
    verificar(c, 1)
    verificar(c, 2)
    entrar(c, "3100000004")
    pagina = c.get("/asignacion").text
    assert "Prioridad" in pagina and "confianza" in pagina
    primero = re.search(r'action="/asignacion/(\d+)"', pagina).group(1)
    assert primero == "2"  # la urgente y vulnerable aparece primero


@pytest.mark.parametrize("ruta", ["/prioridades", "/pesos", "/prioridades?todos=si"])
def test_las_paginas_de_prioridades_son_accesibles(app_cliente, equipo_completo, mundo, ruta):
    pedir(app_cliente, mundo)
    reportar(app_cliente, mundo)
    entrar(app_cliente, "3100000004")
    r = app_cliente.get(ruta)
    assert r.status_code == 200
    revisor = _Revisor()
    revisor.feed(r.text)
    assert revisor.lang == "es" and revisor.ids <= revisor.para, f"campos sin etiqueta: {revisor.ids - revisor.para}"
