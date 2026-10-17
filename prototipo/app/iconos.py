"""Iconos para guiar al usuario con las actividades.

Son dibujos SVG propios y sencillos (trazo de 2 px sobre una cuadrícula de 24), sin librerías ni imágenes aparte, así que
pesan casi nada y funcionan sin conexión. Siempre acompañan a un texto: son decorativos (`aria-hidden`), para reconocer
una actividad de un vistazo; nunca son lo único que dice qué hace un botón o un enlace.
"""
from markupsafe import Markup

ICONOS = {
    # navegación y actividades
    "inicio": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M10 20v-6h4v6"/>',
    "ayuda": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="3.5"/><path d="M5.6 5.6l3.9 3.9M14.5 14.5l3.9 3.9M18.4 5.6l-3.9 3.9M9.5 14.5l-3.9 3.9"/>',
    "solicitudes": '<path d="M8 6h12M8 12h12M8 18h12"/><circle cx="4" cy="6" r="1"/><circle cx="4" cy="12" r="1"/><circle cx="4" cy="18" r="1"/>',
    "aviso": '<path d="M12 3l10 18H2z"/><path d="M12 10v5"/><path d="M12 18v.01"/>',
    "reportes": '<rect x="6" y="4" width="12" height="17" rx="2"/><path d="M9 4h6v3H9z"/><path d="M9 12h6M9 16h4"/>',
    "mapa": '<path d="M12 21s7-6.2 7-12a7 7 0 10-14 0c0 5.8 7 12 7 12z"/><circle cx="12" cy="9" r="2.5"/>',
    "prioridades": '<path d="M5 20V10M12 20V4M19 20v-7"/>',
    "recorrido": '<circle cx="6" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><path d="M8.5 18H15a3 3 0 000-6H9a3 3 0 010-6h6.5"/>',
    "verificar": '<path d="M12 3l8 3v6c0 4.5-3.2 8-8 9-4.8-1-8-4.5-8-9V6z"/><path d="M8.5 12l2.5 2.5L15.5 10"/>',
    "plan": '<rect x="5" y="4" width="14" height="17" rx="2"/><path d="M9 4h6v3H9z"/><path d="M8.5 14l2 2 4-4"/>',
    "equipos": '<circle cx="9" cy="8" r="3"/><path d="M3 20c0-3.3 2.7-6 6-6s6 2.7 6 6"/><circle cx="17" cy="9" r="2.4"/><path d="M16 14.2c2.9.3 5 2.6 5 5.8"/>',
    "inventario": '<path d="M3 7l9-4 9 4v10l-9 4-9-4z"/><path d="M3 7l9 4 9-4M12 11v10"/>',
    "recibir": '<path d="M4 12v7h16v-7"/><path d="M12 4v10M8 10l4 4 4-4"/>',
    "entregas": '<path d="M2 6h11v10H2z"/><path d="M13 9h4l4 3v4h-8z"/><circle cx="7" cy="18" r="2"/><circle cx="17" cy="18" r="2"/>',
    "donar": '<rect x="3" y="9" width="18" height="12" rx="1"/><path d="M12 9v12M3 13h18"/><path d="M12 9c-3 0-5-1-5-3a2 2 0 013-1.5C11 5.5 12 9 12 9zM12 9c3 0 5-1 5-3a2 2 0 00-3-1.5C13 5.5 12 9 12 9z"/>',
    "donaciones": '<path d="M12 20s-8-5-8-11a4.5 4.5 0 018-2.7A4.5 4.5 0 0120 9c0 6-8 11-8 11z"/>',
    "cuentas": '<circle cx="12" cy="8" r="4"/><path d="M4 21c0-4.4 3.6-8 8-8s8 3.6 8 8"/>',
    "auditoria": '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 118 0v3"/>',
    "salir": '<path d="M9 4H5v16h4"/><path d="M16 8l4 4-4 4M20 12H9"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    # acciones
    "llamar": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 005 5L15 13l5 2v4a2 2 0 01-2 2A16 16 0 013 6a2 2 0 012-2z"/>',
    "reloj": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "check": '<path d="M5 12.5l4.5 4.5L19 7.5"/>',
    "equis": '<path d="M6 6l12 12M18 6L6 18"/>',
    "saltar": '<path d="M5 5l9 7-9 7z"/><path d="M18 5v14"/>',
    "volver": '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    "registrada": '<path d="M7 3h7l4 4v14H7z"/><path d="M14 3v4h4M10 12h5M10 16h5"/>',
    # qué se necesita
    "agua": '<path d="M12 3s6 6.5 6 11a6 6 0 01-12 0c0-4.5 6-11 6-11z"/>',
    "alimentos": '<path d="M7 3v8M5 3v5a2 2 0 004 0V3M7 11v10M17 3c-2 2-3 5-3 8h3v10"/>',
    "medicamentos": '<path d="M9 3h6v6h6v6h-6v6H9v-6H3V9h6z"/>',
    "higiene": '<path d="M9 3h6v4H9z"/><path d="M7 7h10v14H7z"/><path d="M10 13h4"/>',
    "abrigo_vivienda": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M9 20v-5h6v5"/>',
    "otro": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5"/><path d="M12 8v.01"/>',
}

# Qué icono lleva cada etapa del recorrido
ICONO_ETAPA = {
    "registrada": "registrada", "verificada": "verificar", "asignada": "equipos", "en_camino": "entregas",
    "entregada": "inventario", "cerrada": "donaciones", "ofrecida": "donar", "recibida": "recibir",
    "inventario": "inventario", "reservada": "plan", "enviado": "aviso", "revisado": "verificar",
    "prioridad": "prioridades",
}


def icono(nombre: str, clase: str = "") -> Markup:
    """El icono como SVG en línea. Falla si el nombre no existe, para no dejar huecos sin darse cuenta."""
    clases = ("icono " + clase).strip()
    return Markup(f'<svg class="{clases}" viewBox="0 0 24 24" aria-hidden="true" focusable="false">{ICONOS[nombre]}</svg>')


def icono_etapa(clave: str) -> Markup:
    return icono(ICONO_ETAPA.get(clave, "otro"))


def icono_necesidad(tipo: str) -> Markup:
    return icono(tipo if tipo in ICONOS else "otro")
