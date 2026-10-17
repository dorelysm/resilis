"""Portada pública: descripción del proyecto, infografía del logo y fundadores."""
import re
from pathlib import Path

from app import equipo
from tests.test_operacion import _Revisor, app_cliente, entrar, equipo_completo, mundo, salir, sesiones  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent


def test_la_portada_describe_el_proyecto_en_secciones_con_indice(app_cliente):
    html = app_cliente.get("/").text
    for ancla, titulo in (("que-es", "¿Qué es Resilis?"), ("como-funciona", "Cómo funciona"), ("para-quien", "Para quién es"),
                          ("distinto", "Lo que lo distingue"), ("logo", "Qué significa nuestro logo"), ("fundadores", "Fundadores")):
        assert f'<h2 id="{ancla}">{titulo}</h2>' in html, ancla
    for ancla in ("que-es", "como-funciona", "para-quien", "logo", "fundadores"):
        assert f'href="#{ancla}"' in html  # el índice lleva a cada sección
    assert html.count("<h1") == 1 and "Después de un desastre, la ayuda llega primero a quien más la necesita" in html
    assert "23 municipios y 600 barrios" in html and "datos ficticios" in html
    assert re.search(r'href="/registro"', html) and re.search(r'href="/entrar"', html)
    # los cuatro pasos, en orden
    pasos = [html.index(f"<h3>{n}.") for n in (1, 2, 3, 4)]
    assert pasos == sorted(pasos)


def test_la_infografia_esta_en_la_portada_con_su_texto_alternativo_y_su_version_en_texto(app_cliente):
    html = app_cliente.get("/").text
    assert 'src="/static/img/infografia-logo.webp"' in html and 'width="1312" height="1199"' in html and 'loading="lazy"' in html
    assert re.search(r'<img[^>]*alt="Infografía «Significado del Logo»[^"]+"', html)
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
        assert f["nombre"] in seccion and f["rol"] in seccion
    assert equipo.INSTITUCION in seccion
    from app.web import plantillas

    gente = [{"nombre": "Ana María Pérez Gómez", "rol": "Datos", "texto": "Armó el modelo de prioridad.", "foto": ""},
             {"nombre": "Luis Rojas", "rol": "Diseño", "texto": "", "foto": "luis.webp"}]
    monkeypatch.setitem(plantillas.env.globals, "FUNDADORES", gente)
    seccion = app_cliente.get("/").text.split('id="fundadores"')[1]
    assert seccion.count('class="fundador"') == 2 and "Armó el modelo de prioridad." in seccion
    assert 'aria-hidden="true">AG<' in seccion  # sin foto: iniciales (primer nombre y último apellido)
    assert 'src="/static/img/luis.webp" alt=""' in seccion  # con foto, decorativa: el nombre ya está escrito al lado


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
    for f in equipo.FUNDADORES:
        if f["foto"]:
            archivo = RAIZ / "app" / "static" / "img" / f["foto"]
            assert archivo.exists() and archivo.stat().st_size < 100_000, f["nombre"]
