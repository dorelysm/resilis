"""Las personas del equipo que aparecen en la sección de fundadores de la portada.

Para agregar a alguien, se añade un diccionario a la lista. `foto` es opcional (nombre de un archivo en
/static/img/); sin foto se muestran las iniciales. `texto` es opcional: una frase sobre lo que aportó.
"""
NOMBRE_EQUIPO = "NEXUS INNOVA 4.0"
INSTITUCION = "Corporación Universitaria Americana"
PAIS = "Colombia"

FUNDADORES = [
    {"nombre": "Dorelys Martinez", "rol": "Líder del equipo", "texto": "", "foto": "fundador-dorelys-martinez.webp"},
    {"nombre": "Adriana Barrios Paez", "rol": "", "texto": "", "foto": "fundador-adriana-barrios-paez.webp"},
    {"nombre": "Carmela Miranda Gutierrez", "rol": "", "texto": "", "foto": "fundador-carmela-miranda-gutierrez.webp"},
    {"nombre": "Evelin Gómez Vergara", "rol": "", "texto": "", "foto": "fundador-evelin-gomez-vergara.webp"},
    {"nombre": "Maritza Domínguez Cervantes", "rol": "", "texto": "", "foto": "fundador-maritza-dominguez-cervantes.webp"},
    {"nombre": "Leandro Rodríguez Polo", "rol": "", "texto": "", "foto": "fundador-leandro-rodriguez-polo.webp"},
    {"nombre": "Stefania De La Cruz", "rol": "", "texto": "", "foto": "fundador-stefania-de-la-cruz.webp"},
]

# Foto del equipo reunido (archivo en /static/img/) y su descripción para lectores de pantalla.
FOTO_EQUIPO = "equipo-nexus-innova.webp"
FOTO_EQUIPO_DESCRIPCION = "Las siete personas fundadoras del equipo NEXUS INNOVA 4.0, de pie junto al logo de Resilis."


MENTORES = [
    {"nombre": "Abril Isabel García Caro", "rol": "Mentora del equipo", "texto": "", "foto": "mentora-abril-isabel-garcia-caro.webp"},
]


def iniciales(nombre: str) -> str:
    partes = [p for p in nombre.split() if p]
    if len(partes) > 1:
        partes = [partes[0], partes[-1]]
    return "".join(p[0] for p in partes).upper()
