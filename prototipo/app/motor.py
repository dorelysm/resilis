"""Motor de prioridad y confianza (bloque 5). Funciones puras: no tocan la base de datos.

Fórmulas del documento de requerimientos, sección 5:
- Confianza de un reporte o solicitud (RM-09):  c = 0,35 F + 0,30 V + 0,15 A + 0,20 K
- Confianza de un sector (RM-10):               C = [1 - prod(1 - c)] (1 - 0,5 D)
- Prioridad (RM-01 a RM-05):                    TOPSIS con pesos ajustables
- Pesos (RM-06):                                AHP con razón de consistencia
"""
import math
from dataclasses import dataclass, field

import numpy as np

# ----------------------------------------------------------------------------- parámetros (RM-11: configurables)
PESOS_CONFIANZA = {"fuente": 0.35, "verificacion": 0.30, "vigencia": 0.15, "corroboracion": 0.20}
FUENTE = {  # peso de la fuente F según quién envía el dato
    "solicitante": 0.40, "brigadista": 0.90, "equipo_entrega": 0.90, "entidad": 0.95, "estado": 0.85,
    "organizacion": 0.70,
}
VERIFICACION = {"verificado": 1.0, "sin_verificar": 0.4, "desmentido": 0.0}
TAU_HORAS = 12.0  # vigencia: A = exp(-horas / tau)
UMBRAL_CONFIANZA = 0.4  # alerta si la confianza del sector es menor
UMBRAL_DISPERSION = 0.5  # alerta si los reportes se contradicen más que esto

CRITERIOS_SECTOR = ["gravedad", "urgencia", "expuestas", "accesibilidad", "recursos"]
CRITERIOS_SOLICITUD = ["urgencia", "vulnerabilidad", "personas_hogar", "tiempo_espera", "prioridad_sector"]
ETIQUETAS = {
    "gravedad": "Gravedad de la afectación", "urgencia": "Urgencia de la atención",
    "expuestas": "Personas expuestas y necesidades especiales", "accesibilidad": "Accesibilidad de las rutas",
    "recursos": "Recursos disponibles", "vulnerabilidad": "Vulnerabilidad", "personas_hogar": "Personas en el hogar",
    "tiempo_espera": "Tiempo de espera", "prioridad_sector": "Prioridad del sector",
}


# ----------------------------------------------------------------------------- confianza
def vigencia(horas: float, tau: float = TAU_HORAS) -> float:
    """A = e^(-t/tau). Un dato recién llegado vale 1 y pierde valor con las horas."""
    return math.exp(-max(0.0, horas) / tau)


def corroboracion(n_que_coinciden: int) -> float:
    """K = 1 - e^(-n/2): cuántos otros reportes independientes coinciden."""
    return 1.0 - math.exp(-max(0, n_que_coinciden) / 2.0)


def confianza_dato(fuente: float, verificacion: str, horas: float, coinciden: int,
                   pesos: dict[str, float] | None = None, tau: float = TAU_HORAS) -> float:
    """Confianza c de un reporte o de una solicitud. Un dato desmentido vale 0, pase lo que pase."""
    if verificacion == "desmentido":
        return 0.0
    p = pesos or PESOS_CONFIANZA
    c = (p["fuente"] * fuente + p["verificacion"] * VERIFICACION[verificacion]
         + p["vigencia"] * vigencia(horas, tau) + p["corroboracion"] * corroboracion(coinciden))
    return float(min(1.0, max(0.0, c)))


def dispersion(niveles: list[float], maximo: float = 3.0) -> float:
    """D entre 0 y 1: qué tanto se contradicen los reportes. Con un solo reporte no hay contradicción."""
    if len(niveles) < 2:
        return 0.0
    return float(min(1.0, np.std(niveles) / (maximo / 2.0)))


def confianza_sector(confianzas: list[float], disp: float) -> float:
    """C = [1 - prod(1 - c)] (1 - 0,5 D). Varios reportes independientes se refuerzan; si no hay, C = 0."""
    if not confianzas:
        return 0.0
    juntos = 1.0 - math.prod(1.0 - c for c in confianzas)
    return float(juntos * (1.0 - 0.5 * disp))


# ----------------------------------------------------------------------------- TOPSIS
@dataclass
class ResultadoTopsis:
    prioridad: list[float]  # P entre 0 y 1, en el orden de las alternativas
    aportes: list[dict[str, float]] = field(default_factory=list)  # parte de cada criterio en el puntaje


def normalizar_pesos(pesos: dict[str, float], criterios: list[str]) -> dict[str, float]:
    """Deja los pesos en [0, 1] y con suma 1. Si todos son cero, reparte por igual."""
    crudos = {c: max(0.0, float(pesos.get(c, 0.0))) for c in criterios}
    total = sum(crudos.values())
    if total <= 0:
        return {c: 1.0 / len(criterios) for c in criterios}
    return {c: v / total for c, v in crudos.items()}


def topsis(matriz: list[list[float]], criterios: list[str], pesos: dict[str, float]) -> ResultadoTopsis:
    """TOPSIS con todos los criterios de beneficio (más es más prioridad).

    1. Normaliza por vector: r_ij = x_ij / raíz(suma_i x_ij^2).
    2. Pondera: v_ij = w_j r_ij.
    3. Ideal A+ (máximo de cada columna) y anti-ideal A- (mínimo).
    4. P_i = D-_i / (D+_i + D-_i).
    """
    if not matriz:
        return ResultadoTopsis([], [])
    x = np.asarray(matriz, dtype=float)
    w = np.array([normalizar_pesos(pesos, criterios)[c] for c in criterios])
    norma = np.sqrt((x**2).sum(axis=0))
    norma[norma == 0] = 1.0  # una columna de ceros no aporta nada
    v = (x / norma) * w
    ideal, anti = v.max(axis=0), v.min(axis=0)
    d_mas = np.sqrt(((v - ideal) ** 2).sum(axis=1))
    d_menos = np.sqrt(((v - anti) ** 2).sum(axis=1))
    denom = d_mas + d_menos
    p = np.where(denom > 0, d_menos / np.where(denom > 0, denom, 1.0), 0.0)  # si todos son iguales, P = 0
    suma = v.sum(axis=1)
    aportes = [
        {c: float(v[i, j] / suma[i]) if suma[i] > 0 else 0.0 for j, c in enumerate(criterios)}
        for i in range(len(x))
    ]
    return ResultadoTopsis([float(t) for t in p], aportes)


# ----------------------------------------------------------------------------- AHP (RM-06)
ALEATORIO_SAATY = {1: 0.0, 2: 0.0, 3: 0.58, 4: 0.90, 5: 1.12, 6: 1.24, 7: 1.32, 8: 1.41, 9: 1.45, 10: 1.49}


def ahp_pesos(matriz: list[list[float]]) -> tuple[list[float], float]:
    """Pesos (vector propio principal) y razón de consistencia CR de una matriz de comparación por pares.
    Se exige CR < 0,1 para aceptar la matriz."""
    a = np.asarray(matriz, dtype=float)
    n = a.shape[0]
    if a.shape != (n, n) or n < 1:
        raise ValueError("La matriz debe ser cuadrada.")
    if not np.allclose(a * a.T, 1.0, atol=1e-6):
        raise ValueError("La matriz debe ser recíproca: a_ij = 1 / a_ji.")
    valores, vectores = np.linalg.eig(a)
    k = int(np.argmax(valores.real))
    w = np.abs(vectores[:, k].real)
    w = w / w.sum()
    if n <= 2:
        return [float(t) for t in w], 0.0
    ci = (valores[k].real - n) / (n - 1)
    return [float(t) for t in w], float(max(0.0, ci) / ALEATORIO_SAATY[min(n, 10)])


def matriz_desde_pesos(pesos: list[float]) -> list[list[float]]:
    """La matriz perfectamente consistente que corresponde a unos pesos dados (a_ij = w_i / w_j)."""
    return [[wi / wj for wj in pesos] for wi in pesos]
