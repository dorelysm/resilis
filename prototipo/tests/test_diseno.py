"""El diseño sale del logo y debe seguir cumpliendo el nivel AA de WCAG (RNF-01) y el límite de datos (RNF-03)."""
import re
import sys
from pathlib import Path

import pytest

from tests.test_web import app_cliente, sesiones  # noqa: F401

RAIZ = Path(__file__).resolve().parent.parent
CSS = (RAIZ / "app" / "static" / "estilo.css").read_text(encoding="utf-8")
sys.path.insert(0, str(RAIZ / "scripts"))
from colores_logo import contraste  # noqa: E402


def variables() -> dict[str, tuple[int, int, int]]:
    bloque = re.search(r":root\s*\{(.*?)\n\}", CSS, re.S).group(1)
    return {n: tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
            for n, h in re.findall(r"--([a-z-]+):\s*#([0-9a-fA-F]{6})", bloque)}


V = variables()

# (primer plano, fondo, mínimo): 4,5 para texto y 3 para bordes y detalles gráficos que hay que distinguir
PARES = [
    ("texto", "fondo", 4.5), ("texto", "tinte-azul", 4.5), ("texto-suave", "fondo", 4.5),
    ("azul", "fondo", 4.5), ("azul", "tinte-azul", 4.5), ("azul-profundo", "fondo", 4.5),
    ("azul-profundo", "tinte-teal", 4.5), ("teal-oscuro", "fondo", 4.5), ("teal-oscuro", "tinte-teal", 4.5),
    ("naranja-oscuro", "fondo", 4.5), ("aviso-texto", "tinte-naranja", 4.5),
    ("error", "fondo", 4.5), ("texto-error", "tinte-error", 4.5),
    ("fondo", "azul", 4.5), ("fondo", "azul-profundo", 4.5),  # texto blanco de botones
    ("texto", "naranja", 4.5),  # texto oscuro sobre el naranja del logo
    ("borde", "fondo", 3.0), ("teal", "fondo", 3.0), ("naranja-oscuro", "tinte-azul", 3.0),  # bordes y foco
]


@pytest.mark.parametrize("fg,bg,minimo", PARES)
def test_los_colores_cumplen_el_contraste(fg, bg, minimo):
    c = contraste(V[fg], V[bg])
    assert c >= minimo, f"{fg} sobre {bg}: {c:.2f}, se pedía {minimo}"


def test_la_paleta_viene_del_logo():
    """Los cuatro colores base son los dominantes que se extrajeron del logo (con tolerancia por el redondeo)."""
    logo = {"azul-profundo": (0x0D, 0x4C, 0x66), "azul": (0x05, 0x5C, 0x81), "teal": (0x0D, 0xA4, 0xA0),
            "naranja": (0xF7, 0x71, 0x4A)}
    for nombre, rgb in logo.items():
        assert V[nombre] == rgb, nombre


def test_el_texto_nunca_usa_el_teal_ni_el_naranja_claros():
    """El teal y el naranja del logo no tienen contraste suficiente sobre blanco: solo van en detalles gráficos."""
    for color in ("teal", "naranja"):
        reglas = [m for m in re.findall(r"([^{}]+)\{([^}]*)\}", CSS) if re.search(rf"[^-]color:\s*var\(--{color}\)", m[1])]
        assert not reglas, f"se usa --{color} como color de texto en: {[r[0].strip() for r in reglas]}"


def test_las_imagenes_existen_y_son_livianas():
    img = RAIZ / "app" / "static" / "img"
    limites = {"emblema-barra.webp": 15, "emblema-grande.webp": 60, "favicon-32.png": 5, "favicon.ico": 5,
               "emblema-ficha.png": 40, "apple-touch-icon.png": 40, "icono-192.png": 60}
    for nombre, kb in limites.items():
        peso = (img / nombre).stat().st_size / 1024
        assert peso <= kb, f"{nombre} pesa {peso:.1f} KB (máximo {kb})"
    assert (img / "emblema-barra.webp").stat().st_size < 15 * 1024  # la barra se carga en todas las páginas


def test_la_barra_muestra_el_logo_y_el_nombre(app_cliente):
    html = app_cliente.get("/entrar").text
    assert 'class="marca"' in html and "/static/img/emblema-barra.webp" in html
    assert re.search(r'<img src="/static/img/emblema-barra\.webp" alt="" width="\d+" height="\d+">', html)
    assert "<span>Resilis</span>" in html  # el nombre visible hace que la imagen sea decorativa (alt vacío)
    assert 'rel="icon"' in html and 'rel="apple-touch-icon"' in html and 'name="theme-color"' in html


def test_el_icono_de_la_pestana_se_sirve(app_cliente):
    r = app_cliente.get("/favicon.ico")
    assert r.status_code == 200 and r.headers["content-type"] == "image/x-icon" and r.content[:4] == b"\x00\x00\x01\x00"
    tipos = {"emblema-barra.webp": "image/webp", "emblema-grande.webp": "image/webp", "favicon-32.png": "image/png",
             "apple-touch-icon.png": "image/png"}
    for ruta, tipo in tipos.items():
        r = app_cliente.get(f"/static/img/{ruta}")
        assert r.status_code == 200 and r.headers["content-type"] == tipo, (ruta, r.headers["content-type"])


def test_la_portada_usa_el_lema_elegido_y_no_el_del_logo(app_cliente):
    html = app_cliente.get("/").text
    assert "Decisiones inteligentes, recursos optimizados, vidas protegidas" in html
    assert "emblema-grande.webp" in html
    # El logo original trae otro lema; se recortó solo el dibujo y ese texto no aparece en el sistema
    # Solo la infografía de la portada lo cita, explicando el significado del logo; ninguna otra pantalla lo usa
    for archivo in (RAIZ / "app" / "templates").glob("*.html"):
        if archivo.name != "inicio.html":
            assert "Inteligencia que conecta" not in archivo.read_text(encoding="utf-8"), archivo.name
    assert "Inteligencia que conecta" not in html.split('id="logo"')[0]  # el lema de la portada sigue siendo el elegido


def test_la_ficha_para_imprimir_lleva_el_emblema():
    """La ficha se imprime: usa el PNG, que no depende de que la impresora o el navegador lean WebP."""
    plantilla = (RAIZ / "app" / "templates" / "ficha.html").read_text(encoding="utf-8")
    assert "emblema-ficha.png" in plantilla and (RAIZ / "app" / "static" / "img" / "emblema-ficha.png").exists()


def test_las_tablas_que_se_desplazan_se_pueden_usar_con_teclado():
    """axe: una región con desplazamiento debe poder enfocarse (tabindex) y tener nombre."""
    from pathlib import Path

    for ruta in (Path(__file__).resolve().parent.parent / "app" / "templates").glob("*.html"):
        for linea in ruta.read_text(encoding="utf-8").splitlines():
            if 'class="tabla-scroll"' in linea:
                assert 'tabindex="0"' in linea and 'role="region"' in linea and "aria-label=" in linea, ruta.name
