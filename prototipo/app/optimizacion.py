"""Plan de asignación de recursos (bloque 6). Núcleo matemático: no toca la base de datos.

Problema (sección 5.5 del documento de requerimientos). Con lotes i (cantidad disponible s_i) y solicitudes j
(cantidad pedida d_j), la variable x_ij es la cantidad del lote i que se entrega a la solicitud j (entera):

    maximizar   suma_ij ( w_j / d_j  +  kappa * u_i  -  lambda * c_ij ) * x_ij
    sujeto a    suma_j x_ij <= s_i        (no se entrega más de lo que hay)
                suma_i x_ij <= d_j        (no se entrega más de lo que se pidió)
                x_ij = 0 si el lote no sirve para esa solicitud (tipo, destino, vencimiento)
                suma_i x_ij >= theta * d_j  para las solicitudes de mayor prioridad (equidad)

w_j es el peso de la solicitud (su prioridad moderada por su confianza), u_i la urgencia de usar el lote por su
vencimiento (primero en vencer, primero en salir) y c_ij el costo de llevarlo (kilómetros).
Se resuelve con programación lineal entera (SciPy, HiGHS). Si no se logra, se usa la asignación voraz de referencia.
"""
import math
import time
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_array

KAPPA = 0.02  # peso del vencimiento (provisional)
LAMBDA = 0.0005  # costo por kilómetro (provisional)
THETA = 0.3  # fracción mínima que se cubre de las solicitudes de prioridad alta (provisional)
LIMITE_SEGUNDOS = 10.0


@dataclass
class Lote:
    id: int
    tipo: str
    disponible: int
    urgencia_uso: float = 0.0  # u_i entre 0 y 1: 1 = vence ya


@dataclass
class Solicitud:
    id: int
    tipo: str
    demanda: int
    peso: float  # w_j


@dataclass
class Resultado:
    x: dict[tuple[int, int], int]  # (lote, solicitud) -> cantidad
    metodo: str  # "optimizado" o "voraz"
    estado: str  # explicación del resultado del solucionador
    segundos: float = 0.0
    equidad_aplicada: bool = False
    notas: list[str] = field(default_factory=list)


def utilidad_unitaria(sol: Solicitud, lote: Lote, km: float, kappa: float, lam: float) -> float:
    return sol.peso / sol.demanda + kappa * lote.urgencia_uso - lam * km


def lambda_efectivo(solicitudes: list[Solicitud], compat: dict[tuple[int, int], float], lam: float) -> float:
    """El costo de la distancia puede inclinar la elección entre lotes, pero nunca debe volver "no entregar" mejor
    que entregar: se acota para que, en el peor caso, el costo sea la mitad de lo que rinde la unidad menos rentable."""
    if not compat or not solicitudes:
        return lam
    menor = min(s.peso / s.demanda for s in solicitudes)
    lejos = max(compat.values())
    return min(lam, 0.5 * menor / lejos) if lejos > 0 else lam


def cubierta_ponderada(x: dict[tuple[int, int], int], solicitudes: list[Solicitud]) -> float:
    """La medida con que se comparan los planes: suma de w_j por la fracción de cada solicitud que se cubre."""
    por_sol: dict[int, int] = {}
    for (_, j), q in x.items():
        por_sol[j] = por_sol.get(j, 0) + q
    return float(sum(s.peso * min(1.0, por_sol.get(s.id, 0) / s.demanda) for s in solicitudes))


def cantidad_cubierta(x: dict[tuple[int, int], int]) -> int:
    return int(sum(x.values()))


def _alta_prioridad(solicitudes: list[Solicitud]) -> set[int]:
    """Las solicitudes cuyo peso supera el promedio de las de su mismo tipo de necesidad."""
    altas: set[int] = set()
    por_tipo: dict[str, list[Solicitud]] = {}
    for s in solicitudes:
        por_tipo.setdefault(s.tipo, []).append(s)
    for grupo in por_tipo.values():
        media = sum(s.peso for s in grupo) / len(grupo)
        altas |= {s.id for s in grupo if s.peso > media}
    return altas


def _minimos_equidad(lotes, solicitudes, compat, theta) -> dict[int, int]:
    """Cantidad mínima que debe recibir cada solicitud de prioridad alta: la fracción theta de lo que pide, sin pasar
    de lo que alcanza a su alcance y sin pasar de su parte igual del inventario de ese tipo. Así una solicitud
    enorme no se queda con toda la cuota de equidad, y la suma de los mínimos nunca supera lo que hay."""
    if theta <= 0:
        return {}
    por_lote = {l.id: l for l in lotes}
    altas_ids = _alta_prioridad(solicitudes)
    minimos: dict[int, int] = {}
    for tipo in {s.tipo for s in solicitudes}:
        altas = [s for s in solicitudes if s.tipo == tipo and s.id in altas_ids]
        if not altas:
            continue
        cuota = sum(l.disponible for l in lotes if l.tipo == tipo) // len(altas)
        for s in altas:
            alcanzable = sum(por_lote[i].disponible for (i, j) in compat if j == s.id)
            m = min(math.floor(theta * s.demanda), alcanzable, cuota)
            if m > 0:
                minimos[s.id] = m
    return minimos


def resolver_optimo(lotes: list[Lote], solicitudes: list[Solicitud], compat: dict[tuple[int, int], float],
                    kappa: float = KAPPA, lam: float = LAMBDA, theta: float = THETA,
                    limite: float = LIMITE_SEGUNDOS) -> Resultado:
    """compat: (lote, solicitud) -> kilómetros, solo para los pares que sirven."""
    inicio = time.perf_counter()
    if not compat:
        return Resultado({}, "optimizado", "No hay lotes que sirvan para ninguna solicitud.", 0.0)
    por_lote = {l.id: l for l in lotes}
    por_sol = {s.id: s for s in solicitudes}
    lam_original, lam = lam, lambda_efectivo(solicitudes, compat, lam)
    pares = sorted(compat)
    n = len(pares)
    c = np.array([-utilidad_unitaria(por_sol[j], por_lote[i], compat[(i, j)], kappa, lam) for i, j in pares])
    ub = np.array([min(por_lote[i].disponible, por_sol[j].demanda) for i, j in pares], dtype=float)

    def modelo(minimos: dict[int, int]):
        filas, cols, vals, lo, hi = [], [], [], [], []
        r = 0
        for i in sorted({i for i, _ in pares}):  # suma_j x_ij <= s_i
            for k, (pi, _) in enumerate(pares):
                if pi == i:
                    filas.append(r); cols.append(k); vals.append(1.0)
            lo.append(0.0); hi.append(float(por_lote[i].disponible)); r += 1
        for j in sorted({j for _, j in pares}):  # minimo_j <= suma_i x_ij <= d_j
            for k, (_, pj) in enumerate(pares):
                if pj == j:
                    filas.append(r); cols.append(k); vals.append(1.0)
            lo.append(float(minimos.get(j, 0))); hi.append(float(por_sol[j].demanda)); r += 1
        a = coo_array((vals, (filas, cols)), shape=(r, n)).tocsr()
        return milp(c, constraints=LinearConstraint(a, lo, hi), integrality=np.ones(n), bounds=Bounds(0, ub),
                    options={"time_limit": float(limite), "presolve": True})

    minimos = _minimos_equidad(lotes, solicitudes, compat, theta)
    notas: list[str] = []
    if lam < lam_original:
        notas.append("El costo de la distancia se redujo para que no impida entregar a las solicitudes de menor peso.")
    equidad = bool(minimos)
    res = modelo(minimos)
    if res.status == 2 and minimos:  # la equidad volvió imposible el problema: se resuelve sin ella
        notas.append("No se pudo garantizar la cobertura mínima de las solicitudes de prioridad alta; se calculó sin ella.")
        equidad = False
        res = modelo({})
    segundos = time.perf_counter() - inicio
    if res.x is None:
        mensajes = {1: "se acabó el tiempo sin encontrar una solución", 2: "el problema no tiene solución",
                    3: "el problema no está acotado"}
        return Resultado({}, "optimizado", mensajes.get(res.status, "el solucionador no encontró solución"), segundos,
                         notas=notas)
    x = {pares[k]: int(round(v)) for k, v in enumerate(res.x) if round(v) > 0}
    estado = "óptimo" if res.status == 0 else "mejor solución encontrada dentro del tiempo límite"
    return Resultado(x, "optimizado", estado, segundos, equidad, notas)


def resolver_voraz(lotes: list[Lote], solicitudes: list[Solicitud], compat: dict[tuple[int, int], float],
                   kappa: float = KAPPA, lam: float = LAMBDA) -> Resultado:
    """Referencia: recorre las solicitudes de mayor a menor peso y cubre cada una con los lotes de mayor utilidad
    (primero los que vencen antes y están más cerca) hasta cubrirla o agotar el inventario."""
    inicio = time.perf_counter()
    lam = lambda_efectivo(solicitudes, compat, lam)
    queda = {l.id: l.disponible for l in lotes}
    por_lote = {l.id: l for l in lotes}
    x: dict[tuple[int, int], int] = {}
    for s in sorted(solicitudes, key=lambda s: (-s.peso, s.id)):
        falta = s.demanda
        opciones = sorted((i for (i, j) in compat if j == s.id),
                          key=lambda i: (-utilidad_unitaria(s, por_lote[i], compat[(i, s.id)], kappa, lam), i))
        for i in opciones:
            if falta == 0:
                break
            tomar = min(falta, queda[i])
            if tomar > 0:
                x[(i, s.id)] = x.get((i, s.id), 0) + tomar
                queda[i] -= tomar
                falta -= tomar
    return Resultado(x, "voraz", "asignación de referencia", time.perf_counter() - inicio)


def resolver(lotes, solicitudes, compat, kappa=KAPPA, lam=LAMBDA, theta=THETA, limite=LIMITE_SEGUNDOS) -> tuple[Resultado, Resultado]:
    """Devuelve (plan, referencia). El plan es el optimizado; si el solucionador no logra nada, es el voraz."""
    voraz = resolver_voraz(lotes, solicitudes, compat, kappa, lam)
    try:
        optimo = resolver_optimo(lotes, solicitudes, compat, kappa, lam, theta, limite)
    except Exception as e:  # un fallo del solucionador no debe dejar sin plan
        optimo = Resultado({}, "optimizado", f"error del solucionador: {e}")
    if not optimo.x and voraz.x:
        voraz.notas.append(f"Se usó la asignación de referencia porque el solucionador falló ({optimo.estado}).")
        return voraz, voraz
    return optimo, voraz
