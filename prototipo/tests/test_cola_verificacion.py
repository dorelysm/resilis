"""Cola de verificación para brigadistas: una solicitud a la vez, un toque por solicitud."""
import re

import pytest
from sqlalchemy import select

from app import models as m
from tests.test_operacion import (  # noqa: F401
    _Revisor, app_cliente, crear_usuario, csrf, entrar, equipo_completo, mundo, pedir, salir, sesiones,
)

BRIGADISTA = "3100000003"


@pytest.fixture()
def con_cinco(app_cliente, sesiones, equipo_completo, mundo):
    """Cinco solicitudes sin verificar; la 3 es la más urgente y la 5 la menos."""
    for _ in range(5):
        pedir(app_cliente, mundo)
    with sesiones() as db:
        barrio = db.get(m.Barrio, mundo["barrio_id"])
        barrio.lat, barrio.lon = 10.96, -74.80  # con ubicación, la tarjeta ofrece abrir el mapa
        db.get(m.Solicitud, 3).urgencia = 3
        db.get(m.Solicitud, 5).urgencia = 0
        db.commit()
    entrar(app_cliente, BRIGADISTA)
    return app_cliente


def verificar(c, sol_id, resultado="verificado", nota=""):
    return c.post(f"/verificacion/solicitudes/{sol_id}", follow_redirects=False,
                  data={"resultado": resultado, "nota": nota, "csrf": csrf(c, f"/verificacion/solicitudes/{sol_id}")})


def test_la_lista_son_tarjetas_con_un_boton_para_empezar(con_cinco):
    pagina = con_cinco.get("/verificacion").text
    assert "<table" not in pagina  # nada de tablas con desplazamiento lateral en el celular
    assert "5 solicitudes</strong> y <strong>0 reportes</strong>" in pagina
    assert 'href="/verificacion/siguiente"' in pagina and "Verificar la siguiente solicitud" in pagina
    assert pagina.count('class="cola-item"') == 5 and "No se pudo" not in pagina
    assert pagina.index('href="/verificacion/solicitudes/3"') < pagina.index('href="/verificacion/solicitudes/1"')  # la urgente primero


def test_siguiente_lleva_a_la_mas_urgente_y_permite_saltar_dando_la_vuelta(con_cinco):
    c = con_cinco
    assert c.get("/verificacion/siguiente", follow_redirects=False).headers["location"] == "/verificacion/solicitudes/3"
    # saltar la 3 lleva a la que sigue en el orden (1, 2, 4, 5), y saltar la última vuelve a la primera
    assert c.get("/verificacion/siguiente?despues=3", follow_redirects=False).headers["location"] == "/verificacion/solicitudes/1"
    assert c.get("/verificacion/siguiente?despues=1", follow_redirects=False).headers["location"] == "/verificacion/solicitudes/2"
    assert c.get("/verificacion/siguiente?despues=5", follow_redirects=False).headers["location"] == "/verificacion/solicitudes/3"
    assert c.get("/verificacion/siguiente?despues=999", follow_redirects=False).headers["location"] == "/verificacion/solicitudes/3"


def test_la_tarjeta_trae_lo_que_hace_falta_en_una_pantalla(con_cinco):
    pagina = con_cinco.get("/verificacion/solicitudes/3").text
    assert "Faltan <strong>5 solicitudes</strong> por verificar" in pagina
    assert 'href="tel:' in pagina and "toque para llamar" in pagina
    assert "https://www.openstreetmap.org/?mlat=" in pagina and "Abrir en el mapa" in pagina
    assert pagina.index('value="verificado"') < pagina.index('value="desmentido"')  # primero el camino feliz
    assert re.search(r'<details class="nota-verificar">', pagina)  # la nota va plegada
    assert "Saltar esta y ver la siguiente" in pagina and "/verificacion/siguiente?despues=3" in pagina
    abierta = con_cinco.get("/verificacion/solicitudes/3?motivo=1").text
    assert re.search(r'<details class="nota-verificar" open>', abierta)


def test_verificar_lleva_solo_a_la_siguiente_con_un_toque_por_solicitud(con_cinco, sesiones):
    c = con_cinco
    visitadas = []
    sol = 3
    for _ in range(5):
        visitadas.append(sol)
        r = verificar(c, sol)
        assert r.status_code == 303 and r.headers["location"] == "/verificacion/siguiente"
        sig = c.get("/verificacion/siguiente", follow_redirects=False)
        if sig.headers["location"] == "/verificacion":
            break
        sol = int(sig.headers["location"].rsplit("/", 1)[1])
    assert visitadas == [3, 1, 2, 4, 5]  # las cinco, en orden de urgencia, sin volver a la lista en medio
    with sesiones() as db:
        assert {s.estado for s in db.scalars(select(m.Solicitud))} == {"verificada"}
    final = c.get("/verificacion/siguiente", follow_redirects=True).text
    assert "No quedan solicitudes por verificar" in final and "No hay solicitudes pendientes de verificar" in final


def test_no_se_puede_desmentir_sin_motivo_y_la_nota_queda_abierta(con_cinco, sesiones):
    c = con_cinco
    r = verificar(c, 3, resultado="desmentido", nota="")
    assert r.status_code == 303 and r.headers["location"] == "/verificacion/solicitudes/3?motivo=1"
    pagina = c.get(r.headers["location"]).text
    assert "motivo" in pagina.lower() and re.search(r'<details class="nota-verificar" open>', pagina)
    with sesiones() as db:
        assert db.get(m.Solicitud, 3).estado == "registrada"
    assert verificar(c, 3, resultado="desmentido", nota="No hay nadie en esa casa").headers["location"] == "/verificacion/siguiente"
    with sesiones() as db:
        assert db.get(m.Solicitud, 3).estado == "anulada"


def test_una_solicitud_ya_revisada_no_ofrece_los_botones(con_cinco):
    c = con_cinco
    verificar(c, 3)
    pagina = c.get("/verificacion/solicitudes/3").text
    assert "ya fue revisada" in pagina and 'value="verificado"' not in pagina and "Ir a la siguiente solicitud" in pagina


def test_los_reportes_van_aparte_y_se_revisan_de_a_uno(con_cinco, sesiones):
    c = con_cinco
    with sesiones() as db:
        evento = db.scalar(select(m.Evento))
        autor = db.scalar(select(m.Usuario).where(m.Usuario.rol == "solicitante"))
        for nivel in (1, 3):
            db.add(m.ReporteDanos(barrio_id=1, evento_id=evento.id, autor_id=autor.id, hora_evento=m.ahora(), nivel_dano=nivel))
        db.commit()
    hub = c.get("/verificacion").text
    assert "<strong>2 reportes</strong>" in hub and 'href="/verificacion/reportes"' in hub
    assert "Confirmar" not in hub  # los botones de reportes ya no llenan la lista de solicitudes
    pagina = c.get("/verificacion/reportes").text
    assert pagina.count('class="cola-item"') == 2 and "2 reportes sin revisar" in pagina
    r = c.post("/verificacion/reportes/1", follow_redirects=False,
               data={"resultado": "verificado", "nota": "", "csrf": csrf(c, "/verificacion/reportes")})
    assert r.status_code == 303 and r.headers["location"] == "/verificacion/reportes"
    assert c.get("/verificacion/reportes").text.count('class="cola-item"') == 1
    verificar_todo = c.post("/verificacion/reportes/2", data={"resultado": "desmentido", "nota": "No es cierto",
                                                              "csrf": csrf(c, "/verificacion/reportes")}, follow_redirects=True).text
    assert "No hay reportes pendientes" in verificar_todo


def test_solo_brigadistas_y_entidades_entran_a_la_cola(con_cinco):
    c = con_cinco
    salir(c)
    for tel in ("3100000001", "3100000005", "3100000007"):  # solicitante, equipo, centro de acopio
        entrar(c, tel)
        for ruta in ("/verificacion", "/verificacion/siguiente", "/verificacion/reportes"):
            assert c.get(ruta, follow_redirects=False).status_code == 403, (tel, ruta)
        salir(c)
    entrar(c, "3100000004")  # la entidad también verifica
    assert c.get("/verificacion/siguiente", follow_redirects=False).headers["location"] == "/verificacion/solicitudes/3"


@pytest.mark.parametrize("ruta", ["/verificacion", "/verificacion/solicitudes/3", "/verificacion/reportes"])
def test_las_paginas_de_la_cola_son_accesibles(con_cinco, ruta):
    r = con_cinco.get(ruta)
    revisor = _Revisor()
    revisor.feed(r.text)
    assert r.status_code == 200 and revisor.lang == "es" and revisor.ids <= revisor.para, f"campos sin etiqueta: {revisor.ids - revisor.para}"
