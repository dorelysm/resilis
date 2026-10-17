import numpy as np
import pytest

from app import optimizacion as op
from app.optimizacion import Lote, Solicitud


def todo_compatible(lotes, solicitudes, km=0.0):
    return {(l.id, s.id): km for l in lotes for s in solicitudes if l.tipo == s.tipo}


def cantidades(res, solicitud_id):
    return sum(q for (_, j), q in res.x.items() if j == solicitud_id)


def usado(res, lote_id):
    return sum(q for (i, _), q in res.x.items() if i == lote_id)


# ----------------------------------------------------------------------------- restricciones
def test_nunca_se_entrega_mas_de_lo_que_hay_ni_de_lo_que_se_pidio():
    rng = np.random.default_rng(7)
    for _ in range(25):
        lotes = [Lote(i, "agua", int(rng.integers(5, 60)), float(rng.random())) for i in range(1, 5)]
        sols = [Solicitud(j, "agua", int(rng.integers(3, 40)), float(rng.random())) for j in range(1, 12)]
        res, _ = op.resolver(lotes, sols, todo_compatible(lotes, sols, km=3.0))
        assert all(isinstance(q, int) and q > 0 for q in res.x.values())
        for l in lotes:
            assert usado(res, l.id) <= l.disponible
        for s in sols:
            assert cantidades(res, s.id) <= s.demanda


def test_solo_se_usan_pares_compatibles():
    lotes = [Lote(1, "agua", 50), Lote(2, "agua", 50)]
    sols = [Solicitud(1, "agua", 20, 0.9), Solicitud(2, "agua", 20, 0.9)]
    compat = {(1, 1): 1.0, (2, 2): 1.0}  # el lote 1 solo sirve a la solicitud 1, y el 2 a la 2
    res, _ = op.resolver(lotes, sols, compat)
    assert set(res.x) <= set(compat) and cantidades(res, 1) == 20 and cantidades(res, 2) == 20


def test_sin_pares_compatibles_no_hay_plan():
    res = op.resolver_optimo([Lote(1, "agua", 10)], [Solicitud(1, "alimentos", 5, 0.5)], {})
    assert res.x == {} and "No hay lotes" in res.estado


# ----------------------------------------------------------------------------- el óptimo supera a la referencia
def test_el_plan_optimizado_cubre_mas_que_la_asignacion_voraz():
    """Con 10 unidades: la voraz las gasta en la solicitud de mayor peso, aunque pida mucho; el óptimo
    cubre primero las pequeñas, que dan más por unidad."""
    lotes = [Lote(1, "agua", 10)]
    sols = [Solicitud(1, "agua", 10, 0.9), Solicitud(2, "agua", 2, 0.8), Solicitud(3, "agua", 2, 0.7)]
    compat = todo_compatible(lotes, sols)
    optimo = op.resolver_optimo(lotes, sols, compat, kappa=0, lam=0, theta=0)
    voraz = op.resolver_voraz(lotes, sols, compat, kappa=0, lam=0)
    assert op.cubierta_ponderada(optimo.x, sols) > op.cubierta_ponderada(voraz.x, sols) + 0.5
    assert cantidades(optimo, 2) == 2 and cantidades(optimo, 3) == 2  # las dos pequeñas, completas
    assert cantidades(voraz, 1) == 10  # la voraz se la lleva toda


def test_el_optimo_nunca_es_peor_que_la_referencia():
    rng = np.random.default_rng(11)
    for _ in range(30):
        lotes = [Lote(i, "agua", int(rng.integers(5, 50)), float(rng.random())) for i in range(1, 4)]
        sols = [Solicitud(j, "agua", int(rng.integers(2, 30)), float(rng.random())) for j in range(1, 10)]
        compat = {k: float(rng.uniform(0, 15)) for k in todo_compatible(lotes, sols)}
        optimo = op.resolver_optimo(lotes, sols, compat, theta=0)
        voraz = op.resolver_voraz(lotes, sols, compat)
        valor = lambda r: sum(op.utilidad_unitaria(next(s for s in sols if s.id == j), next(l for l in lotes if l.id == i),
                                                    compat[(i, j)], op.KAPPA, op.LAMBDA) * q for (i, j), q in r.x.items())
        assert valor(optimo) >= valor(voraz) - 1e-6


def test_si_alcanza_para_todos_se_cubre_todo():
    lotes = [Lote(1, "agua", 100)]
    sols = [Solicitud(j, "agua", 10, 0.5) for j in range(1, 6)]
    res, _ = op.resolver(lotes, sols, todo_compatible(lotes, sols))
    assert all(cantidades(res, s.id) == 10 for s in sols) and res.estado == "óptimo"


# ----------------------------------------------------------------------------- equidad, vencimiento y distancia
def test_la_equidad_da_algo_a_todas_las_solicitudes_de_prioridad_alta():
    """Por unidad rinde más cubrir lo pequeño, así que sin equidad una solicitud grande de prioridad alta se queda
    sin nada. Con la equidad, cada una de las de prioridad alta recibe al menos su mínimo."""
    lotes = [Lote(1, "agua", 30)]
    sols = [Solicitud(1, "agua", 200, 0.95), Solicitud(2, "agua", 20, 0.9), Solicitud(3, "agua", 20, 0.9),
            Solicitud(4, "agua", 20, 0.05), Solicitud(5, "agua", 20, 0.05)]
    compat = todo_compatible(lotes, sols)
    sin = op.resolver_optimo(lotes, sols, compat, kappa=0, lam=0, theta=0)
    con = op.resolver_optimo(lotes, sols, compat, kappa=0, lam=0, theta=0.4)
    assert cantidades(sin, 1) == 0  # sin equidad, la grande no recibe nada
    assert con.equidad_aplicada
    # mínimos: 40 % de lo que pide, sin pasar de su parte igual del inventario (30 / 3 = 10)
    assert cantidades(con, 1) >= 10 and cantidades(con, 2) >= 8 and cantidades(con, 3) >= 8
    assert sum(cantidades(con, j) for j in (4, 5)) == 0  # las de prioridad baja no desplazan a las altas


def test_la_equidad_nunca_hace_imposible_el_plan():
    lotes = [Lote(1, "agua", 5)]  # casi no hay inventario
    sols = [Solicitud(j, "agua", 100, 0.9) for j in range(1, 8)]
    res = op.resolver_optimo(lotes, sols, todo_compatible(lotes, sols), theta=0.9)
    assert res.x and sum(res.x.values()) == 5


def test_primero_en_vencer_primero_en_salir():
    lotes = [Lote(1, "alimentos", 10, urgencia_uso=0.0), Lote(2, "alimentos", 10, urgencia_uso=1.0)]
    sols = [Solicitud(1, "alimentos", 10, 0.5)]
    res = op.resolver_optimo(lotes, sols, todo_compatible(lotes, sols), kappa=0.05, lam=0, theta=0)
    assert usado(res, 2) == 10 and usado(res, 1) == 0  # sale el que vence primero


def test_se_prefiere_el_lote_mas_cercano():
    lotes = [Lote(1, "agua", 10), Lote(2, "agua", 10)]
    sols = [Solicitud(1, "agua", 10, 0.5)]
    compat = {(1, 1): 25.0, (2, 1): 2.0}
    res = op.resolver_optimo(lotes, sols, compat, kappa=0, lam=0.001, theta=0)
    assert usado(res, 2) == 10 and usado(res, 1) == 0


def test_la_confianza_baja_reduce_el_peso_pero_no_lo_anula():
    """w = P (0,5 + 0,5 C): con la misma prioridad, la de más confianza recibe primero cuando el inventario escasea."""
    lotes = [Lote(1, "agua", 10)]
    P = 0.8
    firme = Solicitud(1, "agua", 10, P * (0.5 + 0.5 * 1.0))
    dudosa = Solicitud(2, "agua", 10, P * (0.5 + 0.5 * 0.1))
    res = op.resolver_optimo(lotes, [firme, dudosa], todo_compatible(lotes, [firme, dudosa]), kappa=0, lam=0, theta=0)
    assert cantidades(res, 1) == 10 and cantidades(res, 2) == 0
    assert dudosa.peso > 0  # no se anula


# ----------------------------------------------------------------------------- la referencia voraz
def test_la_asignacion_voraz_respeta_los_limites():
    lotes = [Lote(1, "agua", 15), Lote(2, "agua", 5)]
    sols = [Solicitud(1, "agua", 12, 0.9), Solicitud(2, "agua", 12, 0.5)]
    res = op.resolver_voraz(lotes, sols, todo_compatible(lotes, sols))
    assert cantidades(res, 1) == 12 and cantidades(res, 2) == 8  # la de mayor peso primero; el resto, hasta agotar
    assert usado(res, 1) + usado(res, 2) == 20


def test_si_el_solucionador_falla_se_usa_la_referencia(monkeypatch):
    lotes = [Lote(1, "agua", 20)]
    sols = [Solicitud(1, "agua", 10, 0.5)]

    def roto(*a, **k):
        raise RuntimeError("falla simulada")

    monkeypatch.setattr(op, "resolver_optimo", roto)
    plan, ref = op.resolver(lotes, sols, todo_compatible(lotes, sols))
    assert plan.metodo == "voraz" and cantidades(plan, 1) == 10 and any("falló" in n for n in plan.notas)


def test_el_plan_es_repetible_y_rapido():
    rng = np.random.default_rng(3)
    lotes = [Lote(i, "agua", int(rng.integers(50, 300)), float(rng.random())) for i in range(1, 9)]
    sols = [Solicitud(j, "agua", int(rng.integers(5, 60)), float(rng.random())) for j in range(1, 301)]
    compat = {k: float(rng.uniform(0, 20)) for k in todo_compatible(lotes, sols)}
    a = op.resolver_optimo(lotes, sols, compat)
    b = op.resolver_optimo(lotes, sols, compat)
    assert a.x == b.x and a.segundos < 10 and a.estado in ("óptimo", "mejor solución encontrada dentro del tiempo límite")


def test_el_costo_de_distancia_nunca_impide_entregar():
    """Con una distancia grande y un peso pequeño, el costo sin límite haría que "no entregar" saliera ganando."""
    lotes = [Lote(1, "agua", 10)]
    sols = [Solicitud(1, "agua", 10, 0.01)]
    compat = {(1, 1): 50.0}
    res = op.resolver_optimo(lotes, sols, compat, kappa=0, lam=0.01, theta=0)
    assert cantidades(res, 1) == 10 and any("costo de la distancia" in n for n in res.notas)
    assert cantidades(op.resolver_voraz(lotes, sols, compat, kappa=0, lam=0.01), 1) == 10
    assert op.lambda_efectivo(sols, compat, 0.01) < 0.01
    assert op.lambda_efectivo(sols, {}, 0.01) == 0.01  # sin pares no hay nada que acotar
