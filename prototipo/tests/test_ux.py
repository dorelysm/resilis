"""Mejoras de uso: horas de Colombia, menú plegable, "qué sigue" en el inicio, niveles en palabras, mapa primero y textos."""
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app import models as m
from app.formato import hora_co, iso_utc, nivel_confianza, nivel_prioridad, plural
from tests.test_operacion import (  # noqa: F401
    app_cliente, asignar, crear_usuario, csrf, entrar, equipo_completo, flujo_hasta_asignar, mundo, pedir,
    recibir_inventario, salir, sesiones, verificar,
)

RAIZ = Path(__file__).resolve().parent.parent
node = pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")


# ----------------------------------------------------------------------------- formato
def test_las_horas_se_muestran_en_hora_de_colombia():
    utc = datetime(2026, 10, 17, 4, 38, tzinfo=timezone.utc)
    assert hora_co(utc) == "16/10/2026 23:38"  # 5 horas antes, y un día antes
    assert hora_co(utc.replace(tzinfo=None)) == "16/10/2026 23:38"  # una hora sin zona se toma como UTC
    assert hora_co(utc, "%d/%m %H:%M") == "16/10 23:38" and hora_co(None) == ""
    assert iso_utc(utc.replace(tzinfo=None)) == "2026-10-17T04:38Z"


def test_plural_sin_parentesis():
    assert plural(1, "entrega") == "1 entrega" and plural(0, "entrega") == "0 entregas"
    assert plural(3, "persona afectada", "personas afectadas") == "3 personas afectadas"
    assert plural(2, "solicitud", "solicitudes") == "2 solicitudes"


def test_niveles_en_palabras():
    assert [nivel_prioridad(v) for v in (0.0, 0.32, 0.33, 0.65, 0.66, 1.0)] == ["Baja", "Baja", "Media", "Media", "Alta", "Alta"]
    assert [nivel_confianza(v) for v in (0.0, 0.39, 0.4, 0.65, 0.66)] == ["Baja", "Baja", "Media", "Media", "Alta"]
    assert nivel_prioridad(None) == "—"


def test_ninguna_plantilla_usa_plurales_con_parentesis():
    for archivo in list((RAIZ / "app" / "templates").glob("*.html")) + list((RAIZ / "app" / "static").glob("*.js")):
        texto = archivo.read_text(encoding="utf-8")
        assert not re.search(r"(entrega|persona|solicitud|barrio|reporte|evento|paquete|donaci.n|organizaci.n|d.a|entregada)\((s|es)\)", texto), archivo.name


# ----------------------------------------------------------------------------- cabecera y pie
def test_el_menu_se_pliega_en_celular_y_sin_javascript_sigue_completo(app_cliente, equipo_completo):
    c = app_cliente
    anonimo = c.get("/").text
    assert "data-plegable" not in anonimo and 'id="menu-boton"' not in anonimo  # el visitante no tiene menú que plegar
    entrar(c, "3100000004")
    pagina = c.get("/").text
    assert 'id="menu-boton"' in pagina and 'aria-controls="menu-principal"' in pagina
    assert re.search(r'id="menu-boton"[^>]*\bhidden\b', pagina)  # sin JavaScript el botón no se ve y el menú está completo
    assert 'id="menu-principal" data-plegable' in pagina and 'href="/plan"' in pagina
    assert '<span class="corto">Prototipo con datos ficticios' in pagina  # el aviso corto cabe en una línea de celular
    assert "Todas las horas son hora de Colombia." in pagina
    assert "/static/menu.js" in pagina


def test_el_css_evita_que_el_texto_oculto_ensanche_las_tablas():
    css = (RAIZ / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    assert re.search(r"\.tabla-scroll\s*\{\s*position:\s*relative", css)
    assert "max-width: 47.99rem" in css and "header nav[data-plegable]" in css


@node
def test_el_js_del_menu_es_valido():
    r = subprocess.run(["node", "--check", str(RAIZ / "app" / "static" / "menu.js")], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


# ----------------------------------------------------------------------------- horas
def test_los_recorridos_muestran_la_hora_de_colombia(app_cliente, sesiones, equipo_completo, mundo):
    pedir(app_cliente, mundo)
    with sesiones() as db:
        db.get(m.Solicitud, 1).creado_en = datetime(2026, 10, 17, 4, 38, tzinfo=timezone.utc)
        db.commit()
    entrar(app_cliente, "3100000001")
    pagina = app_cliente.get("/solicitudes/1").text
    assert "16/10 23:38" in pagina and "17/10 04:38" not in pagina
    assert 'datetime="2026-10-17T04:38Z"' in pagina  # el atributo para máquinas sigue en UTC
    assert "16/10/2026 23:38" in app_cliente.get("/solicitudes").text


# ----------------------------------------------------------------------------- qué sigue
def sigue(c, telefono):
    entrar(c, telefono)
    pagina = c.get("/").text
    salir(c)
    return pagina


def test_el_inicio_dice_que_sigue_a_cada_rol(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    vacio = sigue(c, "3100000003")
    assert "No hay nada pendiente ahora." in vacio

    recibir_inventario(c, ids)
    pedir(c, mundo)
    pedir(c, mundo, telefono="3100000002")
    brigadista = sigue(c, "3100000003")
    assert "2 solicitudes por verificar." in brigadista and 'href="/verificacion"' in brigadista
    assert brigadista.index("Ir a verificar") < brigadista.index("Enviar reporte")  # su tarea principal va primero

    solicitante = sigue(c, "3100000001")
    assert "Su solicitud espera que alguien la verifique." in solicitante

    verificar(c, 1)
    entidad = sigue(c, "3100000004")
    assert "1 solicitud por verificar." in entidad and "1 solicitud verificada esperan un plan." in entidad
    assert entidad.index("Ver el plan") < entidad.index("Enviar reporte")

    asignar(c, 1, ids["equipo"])
    solicitante = sigue(c, "3100000001")
    assert "Se asignó un equipo a su solicitud. Tenga su código a la mano." in solicitante and "Ver mi código" in solicitante
    equipo = sigue(c, "3100000005")
    assert "1 entrega por salir." in equipo and 'href="/entregas"' in equipo

    entrar(c, "3100000005")
    c.post("/entregas/1/en-camino", data={"csrf": csrf(c, "/entregas")})
    salir(c)
    solicitante = sigue(c, "3100000001")
    assert "Su ayuda va en camino." in solicitante and "/solicitudes/1#titulo-ruta" in solicitante
    assert "1 entrega en camino y 0 por salir." in sigue(c, "3100000004")


def test_el_centro_de_acopio_ve_las_donaciones_por_recibir(app_cliente, equipo_completo):
    pagina = sigue(app_cliente, "3100000007")
    assert "1 donación espera que la reciba." in pagina and 'href="/recepcion"' in pagina
    assert "Recibir donaciones" in pagina


def test_el_administrador_ve_las_organizaciones_por_aprobar(app_cliente, sesiones, equipo_completo):
    with sesiones() as db:
        db.add(m.Usuario(nombre="Parroquia", telefono="3155550001", rol="equipo_entrega", es_organizacion=True,
                         aprobado=False, ficticio=False, password_hash="x"))
        db.commit()
    assert "1 organización espera aprobación." in sigue(app_cliente, "3100000008")


# ----------------------------------------------------------------------------- niveles y mapa
def test_prioridades_dice_alta_media_o_baja_con_el_porcentaje_al_lado(app_cliente, sesiones, equipo_completo, mundo):
    flujo_hasta_asignar(app_cliente, equipo_completo, mundo)
    entrar(app_cliente, "3100000004")
    pagina = app_cliente.get("/prioridades?sin_info=si").text
    assert re.search(r'<span class="nivel nivel-(alta|media|baja)">(Alta|Media|Baja)</span> <span class="detalle-nivel">\(\d+ %\)</span>', pagina)
    assert "Conviene verificar" in pagina  # un barrio sin confianza lo dice con palabras


def test_el_mapa_pone_el_mapa_antes_que_los_filtros(app_cliente, equipo_completo):
    entrar(app_cliente, "3100000004")
    pagina = app_cliente.get("/mapa").text
    assert pagina.index('id="mapa"') < pagina.index('class="filtros-mapa') < pagina.index('id="resumen-necesidades"')
    assert 'id="filtro-tipos"' in pagina and 'id="controles"' in pagina  # los filtros siguen ahí, plegados


@node
def test_el_js_del_mapa_dice_los_niveles_en_palabras():
    guion = ("const m=require(process.argv[1]);console.log(JSON.stringify([m.nivelPrioridad(0.2),m.nivelPrioridad(0.5),m.nivelPrioridad(0.9),"
             "m.nivelConfianza(0.39),m.nivelConfianza(0.4),m.nivelConfianza(0.7),m.plural(1,'reporte','reportes'),m.plural(2,'reporte','reportes')]))")
    salida = subprocess.run(["node", "-e", guion, str(RAIZ / "app" / "static" / "mapa.js")], capture_output=True, text=True,
                            encoding="utf-8", check=True, timeout=30).stdout
    assert json.loads(salida) == ["Baja", "Media", "Alta", "Baja", "Media", "Alta", "1 reporte", "2 reportes"]


@node
def test_el_js_de_ruta_muestra_la_hora_de_colombia():
    guion = ("const r=require(process.argv[1]);console.log(JSON.stringify(r.textoActualizado('2026-10-17T04:38:09Z')))")
    salida = subprocess.run(["node", "-e", guion, str(RAIZ / "app" / "static" / "ruta.js")], capture_output=True, text=True,
                            encoding="utf-8", check=True, timeout=30).stdout
    assert json.loads(salida) == "Actualizado a las 23:38:09 (hora de Colombia)."  # 04:38 UTC son las 23:38 del día anterior
