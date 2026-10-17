"""Portada pública: descripción del proyecto, infografía del logo y fundadores."""
import re
from pathlib import Path

from app import equipo
from tests.test_operacion import _Revisor, app_cliente, entrar, equipo_completo, mundo, salir, sesiones  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent


def test_la_portada_describe_el_proyecto_en_secciones_con_indice(app_cliente):
    html = app_cliente.get("/").text
    for ancla, titulo in (("reto", "El reto"), ("que-es", "¿Qué es Resilis?"), ("como-funciona", "Cómo funciona"), ("para-quien", "Para quién es"),
                          ("distinto", "Lo que lo distingue"), ("logo", "Qué significa nuestro logo"), ("fundadores", "Fundadores y Mentoría")):
        assert f'<h2 id="{ancla}">{titulo}</h2>' in html, ancla
    for ancla in ("reto", "que-es", "como-funciona", "para-quien", "logo", "fundadores"):
        assert f'href="#{ancla}"' in html  # el índice lleva a cada sección
    assert html.count("<h1") == 1 and "Después de un desastre, la ayuda llega primero a quien más la necesita" in html
    assert "23 municipios y 600 barrios" in html and "datos ficticios" in html
    assert re.search(r'href="/registro"', html) and re.search(r'href="/entrar"', html)
    # los cuatro pasos, en orden
    pasos = [html.index(f"<h3>{n}.") for n in (1, 2, 3, 4)]
    assert pasos == sorted(pasos)


def test_la_infografia_esta_en_la_portada_con_su_texto_alternativo_y_su_version_en_texto(app_cliente):
    html = app_cliente.get("/").text
    assert 'src="/static/img/infografia-logo.webp"' in html and 'width="763" height="680"' in html and 'loading="lazy"' in html
    assert re.search(r'<img[^>]*alt="Infografía «Resilis: significado de cada parte del logo»[^"]+"', html)
    assert "Ver la infografía en tamaño completo" in html
    texto = html.split("Leer el significado como texto")[1].split("</details>")[0]
    for clave in ("Figura humana superior", "Cerebro con circuitos", "Línea del electrocardiograma", "Azul oscuro",
                  "Verde turquesa", "Naranja", "Blanco", "Inteligencia que conecta"):
        assert clave in texto, clave  # lo que dice la imagen también está como texto
    r = app_cliente.get("/static/img/infografia-logo.webp")
    assert r.status_code == 200 and r.headers["content-type"] == "image/webp"
    assert len(r.content) < 400_000  # liviana para el celular (el original pesa 2,2 MB)


def test_la_seccion_de_fundadores_sale_de_la_lista_del_equipo(app_cliente, monkeypatch):
    html = app_cliente.get("/").text
    seccion = html.split('id="fundadores"')[1]
    for f in equipo.FUNDADORES:
        assert f["nombre"] in seccion and f["rol"] in seccion  # un rol en blanco no deja una línea vacía:
    assert seccion.count('class="rol"') == sum(1 for f in equipo.FUNDADORES + equipo.MENTORES if f["rol"])
    assert f'src="/static/img/{equipo.FOTO_EQUIPO}" alt="{equipo.FOTO_EQUIPO_DESCRIPCION}"' in seccion
    assert equipo.INSTITUCION in seccion
    assert equipo.NOMBRE_EQUIPO == "NEXUS INNOVA 4.0" and equipo.PAIS == "Colombia" and equipo.INSTITUCION == "Corporación Universitaria Americana"
    assert f"el equipo {equipo.NOMBRE_EQUIPO}, de la {equipo.INSTITUCION} ({equipo.PAIS})" in seccion
    assert "<h3>Mentoría</h3>" in seccion and "Abril Isabel García Caro" in seccion and "Mentora del equipo" in seccion
    assert seccion.index("<h3>Fundadores</h3>") < seccion.index("<h3>Mentoría</h3>")
    from app.web import plantillas

    gente = [{"nombre": "Ana María Pérez Gómez", "rol": "Datos", "texto": "Armó el modelo de prioridad.", "foto": ""},
             {"nombre": "Luis Rojas", "rol": "Diseño", "texto": "", "foto": "luis.webp"}]
    monkeypatch.setitem(plantillas.env.globals, "FUNDADORES", gente)
    seccion = app_cliente.get("/").text.split('id="fundadores"')[1]
    assert seccion.count('class="fundador"') == 2 + len(equipo.MENTORES) and "Armó el modelo de prioridad." in seccion
    assert 'aria-hidden="true">AG<' in seccion  # sin foto: iniciales (primer nombre y último apellido)
    assert 'src="/static/img/luis.webp" alt=""' in seccion  # con foto, decorativa: el nombre ya está escrito al lado


def test_el_equipo_completo_aparece_con_sus_nombres():
    nombres = [f["nombre"] for f in equipo.FUNDADORES]
    assert nombres == ["Dorelys Martinez", "Adriana Barrios Paez", "Carmela Miranda Gutierrez", "Evelin Gómez Vergara",
                       "Maritza Domínguez Cervantes", "Leandro Rodríguez Polo"]
    assert (RAIZ / "app" / "static" / "img" / equipo.FOTO_EQUIPO).stat().st_size < 150_000


def test_iniciales():
    assert equipo.iniciales("Dorelys Martinez") == "DM" and equipo.iniciales("Ana María Pérez Gómez") == "AG"
    assert equipo.iniciales("Madonna") == "M" and equipo.iniciales("  ") == ""


def test_la_portada_solo_se_ve_sin_sesion_y_el_inicio_con_sesion_no_cambia(app_cliente, equipo_completo):
    c = app_cliente
    assert 'id="fundadores"' in c.get("/").text
    entrar(c, "3100000001")
    inicio = c.get("/").text
    assert 'id="fundadores"' not in inicio and "Qué sigue" in inicio and "Pedir ayuda" in inicio
    salir(c)


def test_la_portada_es_accesible(app_cliente):
    r = app_cliente.get("/")
    revisor = _Revisor()
    revisor.feed(r.text)
    assert r.status_code == 200 and revisor.lang == "es" and revisor.ids <= revisor.para
    ids = re.findall(r'\sid="([^"]+)"', r.text)
    assert len(ids) == len(set(ids))  # ningún id repetido: las anclas y aria-labelledby dependen de eso
    for ref in re.findall(r'aria-labelledby="([^"]+)"', r.text):
        assert ref in ids, ref
    # un icono nunca va solo: todos son decorativos
    assert all('aria-hidden="true"' in s for s in re.findall(r'<svg[^>]*>', r.text))
    assert "infografia-logo" in (RAIZ / "app" / "templates" / "inicio.html").read_text(encoding="utf-8")


def test_toda_foto_de_fundador_existe_y_es_liviana():
    for f in equipo.FUNDADORES + equipo.MENTORES:
        if f["foto"]:
            archivo = RAIZ / "app" / "static" / "img" / f["foto"]
            assert archivo.exists() and archivo.stat().st_size < 100_000, f["nombre"]


# ----------------------------------------------------------------------------- barra de secciones
import json
import shutil
import subprocess

import pytest

INDICE_JS = RAIZ / "app" / "static" / "indice.js"


def test_la_barra_de_secciones_son_pildoras_con_icono_y_texto_que_llevan_a_secciones_que_existen(app_cliente):
    html = app_cliente.get("/").text
    barra = html.split('<nav class="indice-portada"')[1].split("</nav>")[0]
    enlaces = re.findall(r'<li><a href="#([a-z-]+)">(<svg.*?</svg>)([^<]+)</a></li>', barra, re.S)
    assert [t for _, _, t in enlaces] == ["El reto", "Qué es", "Cómo funciona", "Para quién", "Nuestro logo", "Equipo"]
    assert all(s.count('aria-hidden="true"') == 1 for _, s, _ in enlaces)  # el icono es decorativo y el texto va siempre
    for ancla, _, _ in enlaces:
        assert f'id="{ancla}"' in html, ancla
    assert 'src="/static/indice.js" defer' in html and "<ul>" in barra  # lista real, para lectores de pantalla
    assert app_cliente.get("/static/indice.js").status_code == 200


def test_la_css_de_la_barra_la_deja_fija_deslizable_y_con_blancos_tactiles_amplios():
    css = (RAIZ / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
    bloque = css[css.index("/* Barra de secciones de la portada"):]
    assert "position: sticky; top: 0" in bloque and "overflow-x: auto" in bloque
    assert "min-height: 2.75rem" in bloque  # 44 px: objetivo táctil
    assert 'a[aria-current="location"]' in bloque and ".bloque > h2 { scroll-margin-top" in bloque  # el ancla no queda tapada
    assert "prefers-reduced-motion: no-preference" in bloque  # el desplazamiento suave respeta la preferencia


@pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")
def test_el_js_elige_la_ultima_seccion_que_ya_paso_la_linea_de_lectura():
    guion = ("const r=require(process.argv[1]);"
             "const s=[{id:'a',top:-500},{id:'b',top:-20},{id:'c',top:300}];"
             "console.log(JSON.stringify([r.activa(s,100), r.activa([{id:'a',top:400}],100), r.activa([],100), r.activa(s,1000)]))")
    salida = subprocess.run(["node", "-e", guion, str(INDICE_JS)], capture_output=True, text=True, encoding="utf-8",
                            check=True, timeout=30).stdout
    assert json.loads(salida) == ["b", None, None, "c"]  # arriba de todo no hay ninguna activa; al final, la última


# ----------------------------------------------------------------------------- página «Cómo funciona»
def test_la_portada_enlaza_a_la_explicacion_detallada(app_cliente):
    html = app_cliente.get("/").text
    seccion = html.split('id="como-funciona"')[1].split("</section>")[0]
    assert 'href="/como-funciona"' in seccion and "Ver más" in seccion


def test_la_explicacion_es_publica_y_cubre_todo_el_recorrido(app_cliente, equipo_completo):
    c = app_cliente
    r = c.get("/como-funciona")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    html = r.text
    assert html.count("<h1") == 1 and "Cómo funciona Resilis" in html
    anclas = re.findall(r'<li><a href="#([a-z-]+)">', html.split('aria-label="Contenido de esta página"')[1].split("</nav>")[0])
    assert len(anclas) == 13
    for ancla in anclas:  # cada entrada del índice lleva a una sección que existe, con su título
        assert re.search(rf'<h2 id="{ancla}">\d+\. ', html), ancla
    for clave in ("TOPSIS", "Gravedad de la afectación: 30 %", "Urgencia: 30 %", "La fuente</strong> (35 %)",
                  "programación lineal entera", "paquetes pequeños", "código de un solo uso", "sin conexión",
                  "Ley 1581", "simulada", "Lo que todavía no hace"):
        assert clave in html, clave
    for rol in ("Persona que necesita ayuda", "Donante", "Brigadista", "Entidad coordinadora", "Centro de acopio",
                "Equipo de entrega", "Administrador"):
        assert rol in html, rol
    # logueado: lleva a su inicio en vez de pedir crear cuenta
    entrar(c, "3100000001")
    dentro = c.get("/como-funciona").text
    assert "Ir a mi inicio" in dentro and "Crear cuenta" not in dentro.split('class="cierre"')[1]
    salir(c)
    fuera = c.get("/como-funciona").text.split('class="cierre"')[1]
    assert 'href="/registro"' in fuera and 'href="/entrar"' in fuera


def test_los_numeros_de_la_explicacion_coinciden_con_los_del_sistema():
    """Si cambian los pesos iniciales en el código, esta página no puede seguir diciendo lo de antes."""
    from app.simulacion import PESOS_INICIALES

    html = (RAIZ / "app" / "templates" / "como_funciona.html").read_text(encoding="utf-8")
    nombres = {"gravedad": "Gravedad de la afectación", "urgencia": "Urgencia de la atención",
               "expuestas": "Personas expuestas y necesidades especiales", "accesibilidad": "Accesibilidad de las rutas",
               "recursos": "Recursos disponibles"}
    for clave, texto in nombres.items():
        assert f"{texto}: {round(PESOS_INICIALES['barrio'][clave] * 100)} %" in html, clave
    solicitud = {"urgencia": "Urgencia", "vulnerabilidad": "Vulnerabilidad de quien pide", "personas_hogar": "Personas en el hogar",
                 "tiempo_espera": "Tiempo de espera", "prioridad_barrio": "Prioridad de su barrio"}
    for clave, texto in solicitud.items():
        assert f"{texto}: {round(PESOS_INICIALES['solicitud'][clave] * 100)} %" in html, clave
    for clave, texto in {"fuente": "La fuente", "verificacion": "La verificación", "corroboracion": "La corroboración", "vigencia": "La vigencia"}.items():
        assert f"<strong>{texto}</strong> ({round(PESOS_INICIALES['confianza'][clave] * 100)} %)" in html, clave
    from app.plan import TAMANO_PAQUETE

    assert f"hasta {TAMANO_PAQUETE} entregas del mismo municipio" in html


def test_la_explicacion_es_accesible(app_cliente):
    r = app_cliente.get("/como-funciona")
    revisor = _Revisor()
    revisor.feed(r.text)
    assert revisor.lang == "es" and revisor.ids <= revisor.para
    ids = re.findall(r'\sid="([^"]+)"', r.text)
    assert len(ids) == len(set(ids))
    for ref in re.findall(r'aria-labelledby="([^"]+)"', r.text):
        assert ref in ids, ref
    assert all('aria-hidden="true"' in s for s in re.findall(r"<svg[^>]*>", r.text))


def test_la_portada_explica_el_reto_y_como_responde_el_proyecto(app_cliente):
    html = app_cliente.get("/").text
    seccion = html.split('<h2 id="reto">')[1].split("</section>")[0]
    assert "Optimización y priorización de recursos y esfuerzos en la post-emergencia" in seccion
    assert "Rally Latinoamericano de Innovación 2026" in seccion and "16 y el 17 de octubre de 2026" in seccion
    for pregunta in ("¿A quién atender primero?", "¿Dónde concentrar los esfuerzos?", "¿Qué recursos asignar?"):
        assert pregunta in seccion  # las tres decisiones que plantea el reto, cada una con su respuesta
    assert html.index('id="reto"') < html.index('id="que-es"')  # el contexto va antes que la descripción
