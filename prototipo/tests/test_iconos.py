"""Iconos que guían al usuario: bien formados, decorativos (acompañan siempre a un texto) y presentes en cada actividad."""
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from app import models as m
from app.iconos import ICONO_ETAPA, ICONOS, icono, icono_etapa, icono_necesidad
from tests.test_operacion import (  # noqa: F401
    app_cliente, asignar, csrf, entrar, equipo_completo, flujo_hasta_asignar, mundo, pedir, recibir_inventario, salir, sesiones,
)

RAIZ = Path(__file__).resolve().parent.parent


def test_todos_los_iconos_son_svg_validos():
    for nombre, trazos in ICONOS.items():
        svg = ET.fromstring(str(icono(nombre)))
        assert svg.tag.endswith("svg") and svg.attrib["viewBox"] == "0 0 24 24", nombre
        assert svg.attrib["aria-hidden"] == "true" and svg.attrib["focusable"] == "false", nombre  # decorativos
        assert len(list(svg)) >= 1 and "<script" not in trazos, nombre


def test_cada_tipo_de_necesidad_y_cada_etapa_tienen_icono():
    for tipo in m.TipoNecesidad:
        assert tipo.value in ICONOS, tipo
        assert f'class="icono"' in str(icono_necesidad(tipo.value))
    assert "icono" in str(icono_necesidad("desconocido"))  # un tipo nuevo cae en el icono genérico
    assert set(ICONO_ETAPA.values()) <= set(ICONOS)
    assert "<svg" in str(icono_etapa("en_camino")) and "<svg" in str(icono_etapa("no_existe"))


def test_un_nombre_de_icono_que_no_existe_falla_en_voz_alta():
    with pytest.raises(KeyError):
        icono("no_existe")


def test_las_plantillas_solo_piden_iconos_que_existen():
    pedidos = set()
    for archivo in (RAIZ / "app" / "templates").glob("*.html"):
        texto = archivo.read_text(encoding="utf-8")
        pedidos |= set(re.findall(r"icono\('([a-z_]+)'", texto))
        pedidos |= set(re.findall(r"'([a-z_]+)'\) \}\}", texto)) & set(ICONOS)
    assert pedidos and pedidos <= set(ICONOS)
    inicio = (RAIZ / "app" / "templates" / "inicio.html").read_text(encoding="utf-8")
    for nombre in re.findall(r", '([a-z_]+)'\) \}\}", inicio):  # el último argumento de cada tarjeta es su icono
        assert nombre in ICONOS, nombre


def test_cada_enlace_del_menu_lleva_su_icono_y_su_texto(app_cliente, equipo_completo):
    c = app_cliente
    for telefono, esperados in (("3100000004", ["Mapa", "Prioridades", "Recorrido", "Verificar", "Plan", "Inventario"]),
                                ("3100000005", ["Mis entregas"]), ("3100000007", ["Inventario", "Recibir donaciones"])):
        entrar(c, telefono)
        pagina = c.get("/").text
        menu = pagina[pagina.index('id="menu-principal"'):pagina.index("</nav>")]
        enlaces = re.findall(r'<a href="[^"]+">(<svg.*?</svg>)([^<]+)</a>', menu, re.S)
        assert [t for _, t in enlaces if t in esperados] == [t for t in esperados if any(t == x for _, x in enlaces)] and enlaces
        assert all(s.count("aria-hidden=\"true\"") == 1 for s, _ in enlaces)
        assert 'id="menu-boton"' in pagina and "Menú</button>" in pagina and "Salir</button>" in pagina
        salir(c)


def test_los_botones_de_las_actividades_clave_llevan_icono_sin_perder_su_texto(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    recibir_inventario(c, ids)
    pedir(c, mundo)
    entrar(c, "3100000003")
    pagina = c.get("/verificacion/solicitudes/1").text
    for texto in ("Verificada", "No se pudo verificar", "Saltar esta y ver la siguiente", "Volver a la lista"):
        assert re.search(r"<svg[^>]*aria-hidden=\"true\"[^>]*>.*?</svg>" + re.escape(texto), pagina, re.S), texto
    assert re.search(r'href="tel:[^"]*"><svg', pagina)  # llamar
    salir(c)
    entrar(c, "3100000001")
    inicio = c.get("/").text
    assert 'class="icono-redondo"' in inicio and "Pedir ayuda" in inicio and "Necesito ayuda" in inicio
    assert re.search(r'que-sigue-texto"><svg', inicio)  # el pendiente lleva icono
    # el "qué pidió" y las etapas del recorrido también
    seguimiento = c.get("/solicitudes/1").text
    assert re.search(r'class="titulo-paso"><svg', seguimiento)
    salir(c)
    entrar(c, "3100000004")
    assert re.search(r"<strong><svg[^>]*>.*?</svg>Agua", c.get("/prioridades?sin_info=si").text, re.S)


def test_ningun_icono_de_las_paginas_queda_sin_texto_al_lado(app_cliente, equipo_completo):
    """Un icono sin texto no lo entiende un lector de pantalla: todo enlace o botón con icono tiene texto además."""
    entrar(app_cliente, "3100000004")
    for ruta in ("/", "/plan", "/verificacion", "/mapa", "/recorrido"):
        pagina = app_cliente.get(ruta).text
        for abre in re.finditer(r"<(a|button)\b[^>]*>(.*?)</\1>", pagina, re.S):
            contenido = abre.group(2)
            if "<svg" in contenido:
                texto = re.sub(r"<svg.*?</svg>", "", contenido, flags=re.S)
                assert re.sub(r"<[^>]+>", "", texto).strip(), (ruta, abre.group(0)[:120])
