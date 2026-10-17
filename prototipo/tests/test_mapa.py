import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from app import models as m
from app import puntaje as pj
from app.cargas import cargar_viviendas
from app.simulacion import generar
from tests.test_operacion import _Revisor, crear_usuario, csrf, entrar, mundo, salir  # noqa: F401
from tests.test_web import app_cliente, sesiones  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent
JS = RAIZ / "app" / "static" / "mapa.js"
node = pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")


@pytest.fixture()
def con_barrios(sesiones):
    """Un escenario simulado pequeño con puntajes calculados, y cuentas de cada rol que ve el mapa."""
    with sesiones() as db:
        cargar_viviendas(db)
        generar(db, semilla=5, tipo="inundacion", municipios=["08001", "08758"])
        pj.recalcular(db)
    for rol, tel in (("entidad", "3100000004"), ("brigadista", "3100000003"), ("administrador", "3100000008"),
                     ("solicitante", "3100000001"), ("equipo_entrega", "3100000005")):
        crear_usuario(sesiones, rol, tel)


# ----------------------------------------------------------------------------- servidor
def test_solo_ven_el_mapa_quienes_deciden(app_cliente, con_barrios):
    c = app_cliente
    assert c.get("/mapa", follow_redirects=False).status_code == 303
    assert c.get("/mapa/datos.json", follow_redirects=False).status_code == 303
    for tel in ("3100000001", "3100000005"):  # solicitante y equipo de entrega
        entrar(c, tel)
        assert c.get("/mapa").status_code == 403 and c.get("/mapa/datos.json").status_code == 403
        salir(c)
    for tel in ("3100000004", "3100000003", "3100000008"):  # entidad, brigadista, administrador
        entrar(c, tel)
        assert c.get("/mapa").status_code == 200 and c.get("/mapa/datos.json").status_code == 200, tel
        salir(c)


def test_los_datos_del_mapa_son_los_justos_y_sin_datos_personales(app_cliente, con_barrios, sesiones):
    entrar(app_cliente, "3100000004")
    r = app_cliente.get("/mapa/datos.json")
    d = r.json()
    assert r.headers["cache-control"] == "no-store"
    assert d["total"] == len(d["barrios"]) > 10
    assert {x["municipio"] for x in d["barrios"]} == {"Barranquilla", "Soledad"}
    assert {mu["codigo"] for mu in d["municipios"]} == {"08001", "08758"}
    campos = {"id", "nombre", "municipio", "codigo_municipio", "lat", "lon", "personas", "prioridad", "posicion",
              "confianza", "alertas", "n_reportes", "n_solicitudes", "base_previa", "necesidades"}
    assert all(set(x) == campos for x in d["barrios"])
    assert [x["posicion"] for x in d["barrios"]] == list(range(1, d["total"] + 1))  # vienen en orden de prioridad
    assert all(0 <= x["prioridad"] <= 1 and 0 <= x["confianza"] <= 1 for x in d["barrios"])
    assert all(isinstance(x["alertas"], list) for x in d["barrios"])
    with sesiones() as db:  # nada de lo que aparece es un nombre, teléfono o documento de una persona
        gente = db.scalars(select(m.Usuario)).all()
        texto = r.text
        assert all(u.nombre not in texto and u.telefono not in texto for u in gente)


def test_los_barrios_sin_reportes_se_marcan(app_cliente, con_barrios):
    entrar(app_cliente, "3100000004")
    barrios = app_cliente.get("/mapa/datos.json").json()["barrios"]
    sin = [s for s in barrios if "sin_reportes" in s["alertas"]]
    assert sin and all(s["confianza"] == 0.0 and s["n_reportes"] == 0 for s in sin)
    assert any(s["n_reportes"] > 0 and s["confianza"] > 0 for s in barrios)


def test_sin_puntajes_el_mapa_los_calcula(app_cliente, sesiones):
    with sesiones() as db:
        cargar_viviendas(db)
        generar(db, semilla=6, tipo="vendaval", municipios=["08001"])  # sin recalcular
    crear_usuario(sesiones, "entidad", "3100000004")
    entrar(app_cliente, "3100000004")
    assert app_cliente.get("/mapa/datos.json").json()["total"] > 5


def test_la_pagina_del_mapa_es_accesible(app_cliente, con_barrios):
    entrar(app_cliente, "3100000004")
    html = app_cliente.get("/mapa").text
    revisor = _Revisor()
    revisor.feed(html)
    assert revisor.lang == "es" and revisor.ids <= revisor.para, f"campos sin etiqueta: {revisor.ids - revisor.para}"
    assert "<legend>Qué mostrar con el color</legend>" in html  # el grupo de opciones tiene nombre
    assert 'role="region" aria-label="Mapa de los barrios' in html and 'aria-live="polite"' in html
    assert "<noscript>" in html and 'href="/prioridades"' in html  # alternativa sin mapa: la tabla
    assert "/static/vendor/leaflet/leaflet.js" in html and "unpkg" not in html and "cdn" not in html.lower()


def test_leaflet_viene_incluido_con_su_licencia():
    carpeta = RAIZ / "app" / "static" / "vendor" / "leaflet"
    assert (carpeta / "leaflet.js").stat().st_size > 100_000 and (carpeta / "leaflet.css").exists()
    assert "BSD 2-Clause" in (carpeta / "LICENSE").read_text(encoding="utf-8")
    assert "1.9.4" in (carpeta / "leaflet.js").read_text(encoding="utf-8")[:200]
    assert (carpeta / "images" / "layers.png").exists()  # lo que el CSS pide, para que no haya errores 404


def test_los_archivos_del_mapa_se_sirven(app_cliente):
    for ruta, tipo in (("/static/vendor/leaflet/leaflet.js", "javascript"), ("/static/vendor/leaflet/leaflet.css", "css"),
                       ("/static/mapa.js", "javascript"), ("/static/vendor/leaflet/images/layers.png", "image/png")):
        r = app_cliente.get(ruta)
        assert r.status_code == 200 and tipo in r.headers["content-type"], ruta


def test_la_primera_carga_del_mapa_es_liviana():
    """RNF-03: sin contar los mosaicos del mapa de fondo, la página pesa poco comprimida."""
    import gzip

    archivos = [RAIZ / "app" / "static" / "vendor" / "leaflet" / n for n in ("leaflet.js", "leaflet.css")]
    archivos += [RAIZ / "app" / "static" / "mapa.js", RAIZ / "app" / "static" / "estilo.css"]
    comprimido = sum(len(gzip.compress(a.read_bytes())) for a in archivos)
    assert comprimido < 75 * 1024, f"{comprimido / 1024:.0f} KB comprimidos"


# ----------------------------------------------------------------------------- el JavaScript, sin navegador
def _js(expresion: str):
    guion = f"const m = require(process.argv[1]); console.log(JSON.stringify({expresion}));"
    salida = subprocess.run(["node", "-e", guion, str(JS)], capture_output=True, text=True, encoding="utf-8", check=True, timeout=30).stdout
    return json.loads(salida)


@node
def test_cuantiles_reparten_en_grupos_parejos():
    assert _js("m.cuantiles([1,2,3,4,5,6,7,8,9,10], 5)") == [3, 5, 7, 9]
    assert _js("m.cuantiles([], 5)") == [0, 0, 0, 0]
    clases = _js("[1,2,3,4,5,6,7,8,9,10].map(v => m.claseDe(v, m.cuantiles([1,2,3,4,5,6,7,8,9,10], 5)))")
    assert clases == [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
    assert _js("m.claseDe(-5, [3,5,7,9])") == 0 and _js("m.claseDe(99, [3,5,7,9])") == 4


@node
def test_las_clases_sirven_cuando_casi_todos_los_valores_son_iguales():
    # Con valores muy parecidos las clases no deben salirse del rango de la rampa
    clases = _js("[0.5,0.5,0.5,0.5,0.9].map(v => m.claseDe(v, m.cuantiles([0.5,0.5,0.5,0.5,0.9], 5)))")
    assert all(0 <= c <= 4 for c in clases) and clases[-1] == 4


@node
def test_el_texto_dentro_de_cada_color_tiene_contraste_suficiente():
    """El número del círculo se lee sobre cualquier color de las dos rampas (AA: 4,5 a 1) y el borde se ve (3 a 1)."""
    for rampa in ("prioridad", "confianza"):
        colores = _js(f"m.RAMPAS.{rampa}")
        assert len(colores) == 5
        for color in colores:
            texto = _js(f"m.textoSobre('{color}')")
            assert _js(f"m.contraste('{color}', '{texto}')") >= 4.5, (rampa, color)
            assert _js(f"m.contraste('{color}', '#ffffff')") >= 1.0
    assert _js("m.contraste(m.BORDE, '#ffffff')") >= 3.0
    assert _js("m.contraste('#ffffff', '#ffffff')") == 1.0


@node
def test_las_rampas_van_de_claro_a_oscuro():
    for rampa in ("prioridad", "confianza"):
        con_negro = _js(f"m.RAMPAS.{rampa}.map(c => m.contraste(c, '#000000'))")  # más contraste con negro = más claro
        assert con_negro == sorted(con_negro, reverse=True), rampa


@node
def test_filtrar_por_municipio_y_por_aviso():
    barrios = [
        {"id": 1, "codigo_municipio": "A", "alertas": []},
        {"id": 2, "codigo_municipio": "A", "alertas": ["sin_reportes"]},
        {"id": 3, "codigo_municipio": "B", "alertas": ["baja_confianza", "contradictorio"]},
    ]
    base = f"const S = {json.dumps(barrios)};"
    def ids(filtro):
        guion = f"{base} const m = require(process.argv[1]); console.log(JSON.stringify(m.filtrar(S, {filtro}).map(s => s.id)));"
        return json.loads(subprocess.run(["node", "-e", guion, str(JS)], capture_output=True, text=True, encoding="utf-8", check=True).stdout)

    assert ids("{municipio: '', aviso: ''}") == [1, 2, 3]
    assert ids("{municipio: 'A', aviso: ''}") == [1, 2]
    assert ids("{municipio: '', aviso: 'cualquiera'}") == [2, 3]
    assert ids("{municipio: '', aviso: 'contradictorio'}") == [3]
    assert ids("{municipio: 'A', aviso: 'baja_confianza'}") == []


@node
def test_el_texto_que_va_en_el_mapa_se_escapa():
    """Los nombres se insertan en ventanitas HTML: nada de lo que traigan los datos debe poder ejecutarse."""
    assert _js("""m.escapar('<img src=x onerror="alert(1)"> & \\'')""") == \
        "&lt;img src=x onerror=&quot;alert(1)&quot;&gt; &amp; &#39;"
    assert _js("m.escapar(null)") == "" and _js("m.escapar(12)") == "12"


@node
def test_tamano_de_los_circulos_y_descripcion_para_lectores_de_pantalla():
    assert _js("m.tamano(0, 1000)") == 24 and _js("m.tamano(1000, 1000)") == 40
    assert _js("m.tamano(250, 1000)") < _js("m.tamano(900, 1000)")
    assert _js("m.tamano(5, 0)") == 24  # sin máximo no se rompe
    s = {"nombre": "Soledad - Barrio 04", "municipio": "Soledad", "posicion": 3, "prioridad": 0.82, "confianza": 0.41,
         "alertas": ["baja_confianza"]}
    texto = _js(f"m.resumen({json.dumps(s)}, {{baja_confianza: 'La información es poco confiable'}}, 153)")
    assert "Soledad - Barrio 04" in texto and "lugar 3 de 153" in texto and "prioridad 82 %" in texto
    assert "confianza 41 %" in texto and "La información es poco confiable" in texto
    assert _js(f"m.sinDatos({json.dumps({'alertas': ['sin_reportes']})})") is True
    assert _js(f"m.sinDatos({json.dumps({'alertas': []})})") is False


@node
def test_los_circulos_se_achican_al_alejar_y_los_numeros_aparecen_al_acercar():
    assert _js("m.escala(8)") == 0.55 and _js("m.escala(16)") == 1.25  # topes
    escalas = _js("[10, 11, 12, 13, 14].map(z => m.escala(z))")
    assert escalas == sorted(escalas) and len(set(escalas)) == 5
    assert _js("m.mostrarNumero(3, 9)") is True and _js("m.mostrarNumero(40, 9)") is False  # lejos: solo los primeros
    assert _js("m.mostrarNumero(40, 13)") is True and _js("m.mostrarNumero(150, 15)") is False  # cerca, hasta el 99


@node
def test_por_defecto_el_mapa_oculta_los_barrios_sin_reportes_ni_solicitudes():
    barrios = [
        {"id": 1, "codigo_municipio": "A", "alertas": [], "n_reportes": 3, "n_solicitudes": 0},
        {"id": 2, "codigo_municipio": "A", "alertas": ["sin_reportes"], "n_reportes": 0, "n_solicitudes": 2},  # solo pidieron ayuda
        {"id": 3, "codigo_municipio": "B", "alertas": ["sin_reportes"], "n_reportes": 0, "n_solicitudes": 0},
    ]
    base = f"const S = {json.dumps(barrios)};"

    def ids(filtro):
        guion = f"{base} const m = require(process.argv[1]); console.log(JSON.stringify(m.filtrar(S, {filtro}).map(s => s.id)));"
        return json.loads(subprocess.run(["node", "-e", guion, str(JS)], capture_output=True, text=True, encoding="utf-8", check=True).stdout)

    assert ids("{municipio: '', aviso: '', sinInfo: false}") == [1, 2]   # con información: reportes o solicitudes
    assert ids("{municipio: '', aviso: '', sinInfo: true}") == [1, 2, 3]  # con la casilla marcada se ven todos
    assert ids("{municipio: '', aviso: ''}") == [1, 2, 3]                 # sin la opción, nada cambia


def test_el_mapa_trae_las_necesidades_por_barrio_sin_datos_personales(app_cliente, con_barrios, sesiones):
    """Qué piden en cada barrio: tipo, lo específico, cantidad y descripción; nunca el punto de la vivienda ni quién lo pidió."""
    with sesiones() as db:
        barrio = db.scalar(select(m.Barrio).where(m.Barrio.municipio_codigo == "08001").limit(1))
        persona = db.scalar(select(m.Usuario).where(m.Usuario.rol == "solicitante"))
        sol = m.Solicitud(solicitante_id=persona.id, creador_id=persona.id, barrio_id=barrio.id, necesidad="otro", cantidad=1,
                          descripcion="Mi silla de ruedas quedó destruida con el vendaval. " + "x" * 300, urgencia=2,
                          direccion="Calle 99 # 88-77", lat=10.12345, lon=-74.98765, estado="verificada")
        db.add(sol)
        db.flush()
        db.add(m.Vulnerabilidad(solicitud_id=sol.id, tipo="discapacidad", descripcion_situacion="Movilidad reducida",
                                necesidad_especifica="Silla de ruedas estándar", consentimiento=True))
        cerrada = m.Solicitud(solicitante_id=persona.id, creador_id=persona.id, barrio_id=barrio.id, necesidad="agua",
                              cantidad=5, estado="cerrada")
        db.add(cerrada)
        db.commit()
        barrio_id = barrio.id
    entrar(app_cliente, "3100000004")
    r = app_cliente.get("/mapa/datos.json")
    d = r.json()
    assert {t["clave"] for t in d["tipos"]} == {"alimentos", "agua", "medicamentos", "higiene", "abrigo_vivienda", "otro"}
    ns = next(b for b in d["barrios"] if b["id"] == barrio_id)["necesidades"]
    assert len(ns) == 1  # la solicitud cerrada ya no es una necesidad abierta
    n = ns[0]
    assert set(n) == {"id", "tipo", "especifica", "cantidad", "unidad", "urgencia", "estado", "descripcion"}
    assert (n["tipo"], n["especifica"], n["cantidad"], n["unidad"]) == ("otro", "Silla de ruedas estándar", 1, "unidades")
    assert n["descripcion"].startswith("Mi silla de ruedas") and n["descripcion"].endswith("…") and len(n["descripcion"]) <= 160
    for secreto in ("Calle 99", "10.12345", "-74.98765", "Movilidad reducida", "direccion", "solicitante_id"):
        assert secreto not in r.text, secreto


def test_la_pagina_del_mapa_trae_el_filtro_y_el_resumen_de_necesidades(app_cliente, con_barrios):
    entrar(app_cliente, "3100000004")
    pagina = app_cliente.get("/mapa").text
    assert 'id="filtro-tipos"' in pagina and 'id="resumen-necesidades"' in pagina and "Qué se necesita" in pagina


@node
def test_el_js_filtra_y_resume_las_necesidades():
    barrios = [
        {"id": 1, "codigo_municipio": "A", "alertas": [], "necesidades": [
            {"tipo": "agua", "especifica": "", "cantidad": 12, "unidad": "litros", "descripcion": "Sin agua potable"},
            {"tipo": "otro", "especifica": "Silla de ruedas", "cantidad": 1, "unidad": "unidades", "descripcion": "Se dañó"}]},
        {"id": 2, "codigo_municipio": "A", "alertas": [], "necesidades": [
            {"tipo": "agua", "especifica": "", "cantidad": 6, "unidad": "litros", "descripcion": ""}]},
        {"id": 3, "codigo_municipio": "A", "alertas": [], "necesidades": []},
    ]
    nombres = {"agua": "Agua", "otro": "Otro"}
    base = f"const S = {json.dumps(barrios)}; const N = {json.dumps(nombres)}; const m = require(process.argv[1]);"

    def js(expr):
        guion = f"{base} console.log(JSON.stringify({expr}));"
        return json.loads(subprocess.run(["node", "-e", guion, str(JS)], capture_output=True, text=True, encoding="utf-8",
                                         check=True).stdout)

    assert js("m.filtrar(S, {tipos: ['otro']}).map(s => s.id)") == [1]            # solo donde piden lo elegido
    assert js("m.filtrar(S, {tipos: ['agua']}).map(s => s.id)") == [1, 2]
    assert js("m.filtrar(S, {tipos: []}).map(s => s.id)") == [1, 2, 3]            # sin marcar, todos
    assert js("m.filtrar(S, {tipos: ['agua', 'otro']}).map(s => s.id)") == [1, 2]
    assert js("m.resumenNecesidades(S, [], N)") == ["Agua: 2 solicitudes, 18 litros", "Otro: 1 solicitud, 1 unidades"]
    assert js("m.resumenNecesidades(S, ['otro'], N)") == ["Otro: 1 solicitud, 1 unidades"]
    assert js("m.lineaNecesidad(S[0].necesidades[1], N)") == "Otro: Silla de ruedas · 1 unidades — «Se dañó»"
    assert js("m.lineaNecesidad(S[1].necesidades[0], N)") == "Agua · 6 litros"
