"""Las personas del equipo que aparecen en la sección de fundadores de la portada.

Para agregar a alguien, se añade un diccionario a la lista. `foto` es opcional (nombre de un archivo en
/static/img/); sin foto se muestran las iniciales. `texto` es opcional: una frase sobre lo que aportó.
"""
NOMBRE_EQUIPO = "NEXUS INNOVA 4.0"
INSTITUCION = "Corporación Universitaria Americana"
PAIS = "Colombia"

FUNDADORES = [
    {"nombre": "Dorelys Martinez", "rol": "Líder del equipo", "texto": "", "foto": "fundador-dorelys-martinez.webp"},
]


MENTORES = [
    {"nombre": "Abril Isabel García Caro", "rol": "Mentora del equipo", "texto": "", "foto": "mentora-abril-isabel-garcia-caro.webp"},
]


def iniciales(nombre: str) -> str:
    partes = [p for p in nombre.split() if p]
    if len(partes) > 1:
        partes = [partes[0], partes[-1]]
    return "".join(p[0] for p in partes).upper()
