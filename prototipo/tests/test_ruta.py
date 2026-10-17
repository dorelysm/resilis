"""Mapa de la ruta de una entrega: posición simulada, privacidad según quién mira y permisos."""
import json
import re
import shutil
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from app import models as m
from app import ruta as rt
from tests.test_operacion import (  # noqa: F401
    _Revisor, app_cliente, asignar, crear_usuario, csrf, entrar, equipo_completo, flujo_hasta_asignar, mundo, pedir,
    recibir_inventario, salir, sesiones,
)

JS = Path(__file__).resolve().parent.parent / "app" / "static" / "ruta.js"
node = pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")


@pytest.fixture()
def con_ruta(app_cliente, sesiones, equipo_completo, mundo):
    """Una solicitud asignada: el centro de acopio está a unos 8 km del barrio y la vivienda a unos metros de su centro."""
    with sesiones() as db:
        barrio = db.get(m.Barrio, mundo["barrio_id"])
        barrio.lat, barrio.lon = 10.9600, -74.8000
        centro = db.scalar(select(m.CentroAcopio))
        centro.lat, centro.lon = 10.9000, -74.8500
        donante = db.scalar(select(m.Donante))
        donante.usuario_id = crear_usuario(sesiones, m.Rol.DONANTE, "3100000009")
        db.commit()
    flujo_hasta_asignar(app_cliente, equipo_completo, mundo)
    with sesiones() as db:
        sol = db.get(m.Solicitud, 1)
        sol.lat, sol.lon = 10.9605, -74.8005
        db.commit()
    return app_cliente


def salir_en_camino(c):
    entrar(c, "3100000005")
    c.post("/entregas/1/en-camino", data={"csrf": csrf(c, "/entregas")})
    salir(c)


def salida_del_equipo(db):
    return db.scalar(select(m.EventoAuditoria.hora).where(m.EventoAuditoria.tipo == "en_camino"))


def test_antes_de_salir_el_equipo_esta_en_el_centro(con_ruta, sesiones):
    with sesiones() as db:
        r = rt.ruta_de_solicitud(db, db.get(m.Solicitud, 1), exacta=True)
    assert r["etapa"] == "asignada" and r["progreso"] == 0.0 and r["eta_segundos"] is None
    assert (r["posicion"]["lat"], r["posicion"]["lon"]) == (10.9, -74.85)
    assert r["origen"]["nombre"] == "Centro de prueba" and "todavía no ha salido" in r["texto"]
    assert r["simulada"] is True and "simulada" in r["aviso"]


def test_el_equipo_avanza_en_linea_recta_y_llega(con_ruta, sesiones):
    salir_en_camino(con_ruta)
    with sesiones() as db:
        salida = salida_del_equipo(db)
        sol = db.get(m.Solicitud, 1)
        duracion = rt.duracion_demo(rt.kilometros((10.9, -74.85), (10.9605, -74.8005)))
        medio = rt.ruta_de_solicitud(db, sol, True, ahora=salida + timedelta(seconds=duracion / 2))
        llego = rt.ruta_de_solicitud(db, sol, True, ahora=salida + timedelta(seconds=duracion + 5))
    assert medio["etapa"] == "en_camino" and 0.45 < medio["progreso"] < 0.55
    assert 10.92 < medio["posicion"]["lat"] < 10.94 and "va en camino" in medio["texto"] and not medio["cerca"]
    assert medio["restante_km"] < medio["km"] and 0 < medio["eta_segundos"] < duracion
    assert llego["progreso"] == 1.0 and llego["cerca"] and "llegó" in llego["texto"]
    assert (llego["posicion"]["lat"], llego["posicion"]["lon"]) == pytest.approx((10.9605, -74.8005))


def test_avisa_cuando_el_equipo_esta_cerca(con_ruta, sesiones):
    salir_en_camino(con_ruta)
    with sesiones() as db:
        salida = salida_del_equipo(db)
        km = rt.kilometros((10.9, -74.85), (10.9605, -74.8005))
        duracion = rt.duracion_demo(km)
        # Cuando faltan 0,4 km: progreso = 1 - 0,4 / km
        cerca = rt.ruta_de_solicitud(db, db.get(m.Solicitud, 1), True, ahora=salida + timedelta(seconds=duracion * (1 - 0.4 / km)))
        lejos = rt.ruta_de_solicitud(db, db.get(m.Solicitud, 1), True, ahora=salida + timedelta(seconds=duracion * 0.3))
    assert cerca["cerca"] and "código de entrega" in cerca["texto"] and not lejos["cerca"]


def test_sin_entrega_el_mapa_lo_dice(app_cliente, sesiones, equipo_completo, mundo):
    pedir(app_cliente, mundo)
    with sesiones() as db:
        r = rt.ruta_de_solicitud(db, db.get(m.Solicitud, 1), exacta=True)
    assert r["etapa"] == "sin_entrega" and r["posicion"] is None and "Todavía no hay una entrega" in r["texto"]


def test_la_persona_ve_su_destino_exacto_y_el_personal_solo_el_barrio(con_ruta, sesiones):
    with sesiones() as db:
        sol = db.get(m.Solicitud, 1)
        propia = rt.ruta_de_solicitud(db, sol, exacta=True)
        personal = rt.ruta_de_solicitud(db, sol, exacta=False)
    assert (propia["destino"]["lat"], propia["destino"]["lon"]) == (10.9605, -74.8005) and propia["destino"]["nombre"] == "Su dirección"
    assert (personal["destino"]["lat"], personal["destino"]["lon"]) == (10.96, -74.8) and "Barrio de prueba" in personal["destino"]["nombre"]


def test_el_donante_ve_barrios_con_circulo_y_no_personas(con_ruta, sesiones):
    salir_en_camino(con_ruta)
    entrar(con_ruta, "3100000009")
    r = con_ruta.get("/donaciones/ruta.json")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    d = r.json()
    assert len(d["origenes"]) == 1 and d["origenes"][0]["nombre"] == "Centro de prueba"
    assert len(d["destinos"]) == 1
    destino = d["destinos"][0]
    assert destino["radio_m"] == 300 and destino["en_camino"] == 1 and "Barrio de prueba" in destino["barrio"]
    assert (destino["lat"], destino["lon"]) == (10.96, -74.8)  # el centro del barrio, no la vivienda (10.9605, -74.8005)
    texto = r.text
    for secreto in ("10.9605", "-74.8005", "Calle 1", "3100000001", "solicitante", "solicitud_id", "nombre_persona"):
        assert secreto not in texto, secreto
    assert len(d["en_camino"]) == 1 and d["en_camino"][0]["hacia"].startswith("Barrio de prueba")
    assert "1 entrega en 1 barrio" in d["texto"]


def test_un_donante_sin_entregas_ve_el_mapa_vacio(con_ruta, sesiones):
    with sesiones() as db:
        otro = crear_usuario(sesiones, m.Rol.DONANTE, "3100000010")
        db.add(m.Donante(usuario_id=otro, nombre="Otro donante", tipo="persona"))
        db.commit()
    entrar(con_ruta, "3100000010")
    d = con_ruta.get("/donaciones/ruta.json").json()
    assert d["destinos"] == [] and d["origenes"] == [] and "Todavía no hay entregas" in d["texto"]


def test_permisos_de_los_datos_de_ruta(con_ruta):
    c = con_ruta
    assert c.get("/solicitudes/1/ruta.json", follow_redirects=False).status_code == 303  # sin sesión
    entrar(c, "3100000002")  # otra persona: no es su solicitud
    assert c.get("/solicitudes/1/ruta.json").status_code == 404
    salir(c)
    entrar(c, "3100000001")
    assert c.get("/solicitudes/1/ruta.json").status_code == 200
    assert c.get("/recorrido/solicitudes/1/ruta.json").status_code == 403  # eso es del personal
    assert c.get("/donaciones/ruta.json").status_code == 403
    salir(c)
    entrar(c, "3100000004")
    assert c.get("/recorrido/solicitudes/1/ruta.json").status_code == 200
    assert c.get("/recorrido/solicitudes/999/ruta.json").status_code == 404
    assert c.get("/solicitudes/1/ruta.json").status_code == 403
    salir(c)
    entrar(c, "3100000005")  # el equipo de entrega no ve mapas de ruta por esta vía
    assert c.get("/donaciones/ruta.json").status_code == 403


def test_las_paginas_traen_el_mapa_y_avisan_que_es_simulado(con_ruta):
    c = con_ruta
    entrar(c, "3100000001")
    pagina = c.get("/solicitudes/1").text
    assert 'id="mapa-ruta"' in pagina and 'data-url="/solicitudes/1/ruta.json"' in pagina
    assert "Ruta simulada para la demostración" in pagina and 'id="estado-ruta"' in pagina and 'role="alert"' not in pagina
    revisor = _Revisor()
    revisor.feed(pagina)
    assert revisor.ids <= revisor.para
    salir(c)
    entrar(c, "3100000009")
    pagina = c.get("/donaciones").text
    assert 'data-modo="donante"' in pagina and 'id="lista-destinos"' in pagina and "Dónde llegó su ayuda" in pagina
    salir(c)
    entrar(c, "3100000004")
    assert 'data-url="/recorrido/solicitudes/1/ruta.json"' in c.get("/recorrido/solicitudes/1").text


def test_una_solicitud_sin_asignar_no_muestra_mapa(app_cliente, equipo_completo, mundo):
    pedir(app_cliente, mundo)
    entrar(app_cliente, "3100000001")
    assert 'id="mapa-ruta"' not in app_cliente.get("/solicitudes/1").text


@node
def test_el_js_describe_los_destinos_en_texto():
    guion = ("const r=require(process.argv[1]);"
             "console.log(JSON.stringify([r.lineaDestino({barrio:'Rebolo, Barranquilla',entregas:4,entregadas:1,en_camino:2}),"
             "r.lineaDestino({barrio:'X',entregas:1,entregadas:0,en_camino:0}),r.escapar('<b>&\"'),"
             "r.textoActualizado('2026-10-16T08:05:09Z').startsWith('Actualizado a las '),r.textoActualizado('no es fecha')]))")
    salida = subprocess.run(["node", "-e", guion, str(JS)], capture_output=True, text=True, encoding="utf-8", check=True,
                            timeout=30).stdout
    a, b, c, d, e = json.loads(salida)
    assert a == "Rebolo, Barranquilla: 1 entregada, 2 en camino, 1 por salir."
    assert b == "X: 1 por salir." and c == "&lt;b&gt;&amp;&quot;" and d is True and e == ""


def test_mientras_el_equipo_va_en_camino_ese_paso_esta_en_curso(con_ruta, sesiones):
    from app import recorrido as rc

    salir_en_camino(con_ruta)
    with sesiones() as db:
        pasos = {p["clave"]: p["estado"] for p in rc.pasos_solicitud(db, db.get(m.Solicitud, 1))}
    assert pasos["asignada"] == "hecho" and pasos["en_camino"] == "actual" and pasos["entregada"] == "pendiente"


def test_si_el_centro_no_tiene_ubicacion_la_ruta_usa_un_origen_simulado_y_lo_avisa(app_cliente, sesiones, equipo_completo, mundo):
    """El centro de la demo creado sin barrio no puede dejar al mapa sin dibujar: se inventa el punto de salida y se dice."""
    with sesiones() as db:
        barrio = db.get(m.Barrio, mundo["barrio_id"])
        barrio.lat, barrio.lon = 10.96, -74.80
        centro = db.scalar(select(m.CentroAcopio))
        centro.barrio_id, centro.lat, centro.lon = None, None, None  # el centro de acopio queda sin ubicación
        db.commit()
    flujo_hasta_asignar(app_cliente, equipo_completo, mundo)
    salir_en_camino(app_cliente)
    entrar(app_cliente, "3100000001")
    d = app_cliente.get("/solicitudes/1/ruta.json").json()
    assert d["etapa"] == "en_camino" and d["origen_simulado"] is True and d["origen"] and d["posicion"]
    assert "no tiene ubicación" in d["aviso"] and 1.5 < d["km"] < 2.5
    assert d["equipo"] == "Usuario equipo_entrega" and "El equipo Usuario equipo_entrega" in d["texto"]  # como en una app de entregas


def test_la_entidad_lleva_el_control_logistico_de_todas_las_entregas(con_ruta, sesiones):
    c = con_ruta
    salir_en_camino(c)
    entrar(c, "3100000004")
    r = c.get("/recorrido/entregas/ruta.json")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    d = r.json()
    assert len(d["entregas"]) == 1 and d["resumen"] == {"por_salir": 0, "en_camino": 1, "entregadas": 0}
    e = d["entregas"][0]
    assert e["etapa"] == "en_camino" and e["equipo"] and e["origen"]["nombre"] == "Centro de prueba" and e["posicion"]
    assert (e["destino"]["lat"], e["destino"]["lon"]) == (10.96, -74.8)  # el centro del barrio, no la vivienda
    assert "10.9605" not in r.text and "Calle 1" not in r.text and "3100000001" not in r.text
    pagina = c.get("/recorrido").text
    assert 'data-url="/recorrido/entregas/ruta.json"' in pagina and 'id="lista-entregas"' in pagina
    salir(c)
    entrar(c, "3100000003")  # el brigadista ve el recorrido, pero el control logístico es de la entidad
    assert c.get("/recorrido/entregas/ruta.json").status_code == 403
    assert "ruta.json" not in c.get("/recorrido").text.replace("/recorrido/solicitudes", "")
    salir(c)
    for tel in ("3100000001", "3100000005", "3100000007"):
        entrar(c, tel)
        assert c.get("/recorrido/entregas/ruta.json").status_code == 403, tel
        salir(c)


def test_el_equipo_ve_el_mapa_de_sus_entregas_y_solo_las_suyas(con_ruta, sesiones):
    c = con_ruta
    salir_en_camino(c)
    entrar(c, "3100000005")  # el equipo al que se asignó
    r = c.get("/entregas/ruta.json")
    d = r.json()
    assert r.status_code == 200 and len(d["entregas"]) == 1
    assert (d["entregas"][0]["destino"]["lat"], d["entregas"][0]["destino"]["lon"]) == (10.9605, -74.8005)  # su destino exacto
    assert 'data-url="/entregas/ruta.json"' in c.get("/entregas").text
    salir(c)
    entrar(c, "3100000006")  # otro equipo: no ve entregas ajenas
    assert c.get("/entregas/ruta.json").json()["entregas"] == []
    salir(c)
    entrar(c, "3100000004")
    assert c.get("/entregas/ruta.json").status_code == 403  # esto es del equipo; la entidad usa el control logístico


def test_el_donante_ve_la_zona_aproximada_y_no_la_posicion_exacta(con_ruta, sesiones):
    c = con_ruta
    salir_en_camino(c)
    with sesiones() as db:
        salida = salida_del_equipo(db)
        donante = db.scalar(select(m.Donante))
        medio = rt.duracion_demo(rt.kilometros((10.9, -74.85), (10.96, -74.8))) / 2
        d = rt.ruta_de_donante(db, donante, ahora=salida + timedelta(seconds=medio))
        exacta = rt.ruta_de_solicitud(db, db.get(m.Solicitud, 1), True, ahora=salida + timedelta(seconds=medio))["posicion"]
    zona = d["en_camino"][0]
    assert zona["radio_m"] == 500 and zona["avance"] % 10 == 0 and 30 <= zona["avance"] <= 70
    assert round(zona["lat"] / 0.004) * 0.004 == pytest.approx(zona["lat"], abs=1e-4)  # en la cuadrícula de ~440 m
    assert abs(zona["lat"] - exacta["lat"]) < 0.0025 and (zona["lat"], zona["lon"]) != (exacta["lat"], exacta["lon"])
    assert set(zona) == {"hacia", "lat", "lon", "radio_m", "avance"}


def test_el_seguimiento_de_quien_pidio_empieza_por_el_estado_y_el_codigo(con_ruta):
    c = con_ruta
    salir_en_camino(c)
    entrar(c, "3100000001")
    pagina = c.get("/solicitudes/1").text
    assert pagina.index("Su código de entrega") < pagina.index('id="mapa-ruta"') < pagina.index("Recorrido de mi solicitud")
    lista = c.get("/solicitudes").text
    assert "Seguir en el mapa" in lista and "/solicitudes/1#titulo-ruta" in lista


@node
def test_el_js_describe_cada_entrega_en_texto():
    guion = ("const r=require(process.argv[1]);"
             "console.log(JSON.stringify([r.lineaEntrega({equipo:'Equipo Norte',origen:{nombre:'Acopio central'},destino:{nombre:'El Edén, Malambo'},etapa:'en_camino',restante_km:1.25,cerca:false}),"
             "r.lineaEntrega({equipo:null,origen:null,destino:null,etapa:'asignada'}),"
             "r.lineaEntrega({equipo:'E',origen:{nombre:'A'},destino:{nombre:'B'},etapa:'en_camino',restante_km:0.3,cerca:true})]))")
    salida = subprocess.run(["node", "-e", guion, str(JS)], capture_output=True, text=True, encoding="utf-8", check=True,
                            timeout=30).stdout
    a, b, c = json.loads(salida)
    assert a == "Equipo Norte: de Acopio central a El Edén, Malambo, en camino, faltan 1,25 km."
    assert b == "Equipo: de el centro a el destino, por salir."
    assert c == "E: de A a B, en camino, faltan 0,3 km (ya está cerca)."


def test_mi_solicitud_pone_el_estado_el_codigo_y_un_solo_mensaje_arriba(con_ruta):
    c = con_ruta
    entrar(c, "3100000001")
    pagina = c.get("/solicitudes/1").text
    assert "Un equipo ya tiene su pedido" in pagina and "Todavía no ha salido" in pagina  # la ruta ya está asignada
    assert re.search(r'<h1 id="titulo-estado">', pagina) and pagina.count("<h1") == 1 and "Estado:" not in pagina
    salir(c)
    salir_en_camino(c)
    entrar(c, "3100000001")
    pagina = c.get("/solicitudes/1").text
    assert "Su ayuda va en camino" in pagina and 'class="tarjeta-estado estado-en_camino"' in pagina
    assert pagina.index("titulo-estado") < pagina.index('id="eta-vivo"') < pagina.index("Su código de entrega") < pagina.index('id="mapa-ruta"')
    assert re.search(r'class="codigo"[^>]*>[A-Z0-9]{4}-[A-Z0-9]{4}<', pagina)
    assert 'id="eta-vivo" class="estado-eta" role="status" aria-live="polite"' in pagina
    assert 'id="estado-ruta" class="estado-ruta estado-ruta-menor"' in pagina and pagina.count('aria-live="polite"') == 1  # un solo aviso vivo
    assert pagina.count("Ruta simulada para la demostración") == 1


def test_el_js_pone_el_mensaje_de_la_ruta_en_la_tarjeta_y_marca_cuando_esta_cerca():
    texto = JS.read_text(encoding="utf-8")
    assert "getElementById('eta-vivo')" in texto and "classList.add('cerca')" in texto and "aviso-cerca" not in texto
