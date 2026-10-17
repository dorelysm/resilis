import math

import pytest

from app import motor as mo


# ----------------------------------------------------------------------------- confianza
def test_vigencia_y_corroboracion():
    assert mo.vigencia(0) == 1.0
    assert mo.vigencia(12) == pytest.approx(math.exp(-1))
    assert mo.vigencia(-5) == 1.0  # un dato "del futuro" no vale más que uno nuevo
    assert mo.corroboracion(0) == 0.0
    assert mo.corroboracion(2) == pytest.approx(1 - math.exp(-1))
    assert mo.corroboracion(10) > mo.corroboracion(3) > mo.corroboracion(1)


def test_confianza_de_un_dato_sigue_la_formula():
    # c = 0,35 F + 0,30 V + 0,15 A + 0,20 K
    esperado = 0.35 * 0.9 + 0.30 * 1.0 + 0.15 * math.exp(-0.5) + 0.20 * (1 - math.exp(-1))
    assert mo.confianza_dato(0.9, "verificado", 6, 2) == pytest.approx(esperado)


def test_un_reporte_verificado_pesa_mas_que_uno_igual_sin_verificar():
    sin = mo.confianza_dato(0.4, "sin_verificar", 3, 0)
    con = mo.confianza_dato(0.4, "verificado", 3, 0)
    assert con > sin
    assert con - sin == pytest.approx(0.30 * (1.0 - 0.4))


def test_un_brigadista_pesa_mas_que_un_ciudadano():
    ciudadano = mo.confianza_dato(mo.FUENTE["solicitante"], "sin_verificar", 2, 0)
    brigadista = mo.confianza_dato(mo.FUENTE["brigadista"], "sin_verificar", 2, 0)
    assert brigadista > ciudadano


def test_un_dato_desmentido_vale_cero():
    assert mo.confianza_dato(0.95, "desmentido", 0, 10) == 0.0


def test_los_pesos_de_confianza_son_configurables():
    solo_fuente = {"fuente": 1.0, "verificacion": 0.0, "vigencia": 0.0, "corroboracion": 0.0}
    assert mo.confianza_dato(0.7, "sin_verificar", 99, 0, pesos=solo_fuente) == pytest.approx(0.7)


def test_la_confianza_siempre_esta_entre_cero_y_uno():
    for f in (0, 0.4, 1):
        for v in mo.VERIFICACION:
            for h in (0, 5, 500):
                for n in (0, 3, 50):
                    assert 0.0 <= mo.confianza_dato(f, v, h, n) <= 1.0


def test_confianza_del_barrio():
    assert mo.confianza_barrio([], 0.0) == 0.0  # sin reportes no hay confianza
    un_reporte = mo.confianza_barrio([0.5], 0.0)
    assert un_reporte == pytest.approx(0.5)
    assert mo.confianza_barrio([0.5, 0.5], 0.0) == pytest.approx(0.75)  # varios reportes se refuerzan
    assert mo.confianza_barrio([0.5, 0.5], 1.0) == pytest.approx(0.75 * 0.5)  # la contradicción la reduce a la mitad
    assert mo.confianza_barrio([0.5, 0.5, 0.5], 0.0) > mo.confianza_barrio([0.5, 0.5], 0.0)


def test_dispersion():
    assert mo.dispersion([]) == 0.0 and mo.dispersion([2]) == 0.0
    assert mo.dispersion([2, 2, 2]) == 0.0  # todos coinciden
    assert mo.dispersion([0, 3]) == pytest.approx(1.0)  # extremos opuestos: contradicción máxima
    assert 0 < mo.dispersion([1, 2, 3]) < 1


# ----------------------------------------------------------------------------- TOPSIS
def test_topsis_coincide_con_un_calculo_a_mano():
    # A=(1,0), B=(0,1), C=(1,1), pesos 0,5/0,5: P = 0,5 / 0,5 / 1,0 (ver el cálculo en la documentación)
    r = mo.topsis([[1, 0], [0, 1], [1, 1]], ["a", "b"], {"a": 0.5, "b": 0.5})
    assert r.prioridad == pytest.approx([0.5, 0.5, 1.0])


def test_topsis_un_ejemplo_conocido():
    """4 alternativas y 3 criterios. A3 es la mejor o empata en todo, y A2 la peor: el orden debe ser A3, A4, A1, A2."""
    m = [[250, 16, 12], [200, 16, 8], [300, 32, 16], [275, 32, 8]]
    r = mo.topsis(m, ["x", "y", "z"], {"x": 0.3, "y": 0.4, "z": 0.3})
    orden = sorted(range(4), key=lambda i: -r.prioridad[i])
    assert orden == [2, 3, 0, 1]
    assert all(0 <= p <= 1 for p in r.prioridad)
    assert r.prioridad[2] == max(r.prioridad)


def test_topsis_mas_es_mas_prioridad():
    r = mo.topsis([[1.0], [2.0], [3.0]], ["g"], {"g": 1.0})
    assert r.prioridad[0] < r.prioridad[1] < r.prioridad[2]
    assert r.prioridad[2] == pytest.approx(1.0) and r.prioridad[0] == pytest.approx(0.0)


def test_topsis_pesos_distintos_cambian_el_orden():
    m = [[10, 1], [1, 10]]
    a = mo.topsis(m, ["g", "u"], {"g": 0.9, "u": 0.1}).prioridad
    b = mo.topsis(m, ["g", "u"], {"g": 0.1, "u": 0.9}).prioridad
    assert a[0] > a[1] and b[1] > b[0]


def test_topsis_aportes_suman_uno_y_explican_la_posicion():
    r = mo.topsis([[4, 0], [1, 3]], ["g", "u"], {"g": 0.5, "u": 0.5})
    for aporte in r.aportes:
        assert sum(aporte.values()) == pytest.approx(1.0)
    assert r.aportes[0]["g"] > r.aportes[0]["u"]  # la primera alternativa debe su puntaje a "g"
    assert r.aportes[1]["u"] > r.aportes[1]["g"]


def test_topsis_casos_borde():
    assert mo.topsis([], ["a"], {"a": 1}).prioridad == []
    assert mo.topsis([[0, 0], [0, 0]], ["a", "b"], {"a": 1, "b": 1}).prioridad == [0.0, 0.0]  # todo en cero
    assert mo.topsis([[2, 2], [2, 2]], ["a", "b"], {"a": 1, "b": 1}).prioridad == [0.0, 0.0]  # todos iguales
    assert mo.topsis([[5, 0], [3, 0]], ["a", "b"], {"a": 1, "b": 1}).prioridad[0] > 0.9  # una columna vacía no rompe


def test_normalizar_pesos():
    assert mo.normalizar_pesos({"a": 3, "b": 1}, ["a", "b"]) == {"a": 0.75, "b": 0.25}
    assert mo.normalizar_pesos({"a": 0, "b": 0}, ["a", "b"]) == {"a": 0.5, "b": 0.5}
    assert mo.normalizar_pesos({"a": -5, "b": 2}, ["a", "b"]) == {"a": 0.0, "b": 1.0}  # un peso negativo no cuenta
    assert mo.normalizar_pesos({"a": 1}, ["a", "b"]) == {"a": 1.0, "b": 0.0}  # lo que falta vale 0


# ----------------------------------------------------------------------------- AHP
def test_ahp_con_una_matriz_consistente():
    pesos = [0.5, 0.3, 0.2]
    w, cr = mo.ahp_pesos(mo.matriz_desde_pesos(pesos))
    assert w == pytest.approx(pesos, abs=1e-6) and cr == pytest.approx(0.0, abs=1e-6)


def test_ahp_ejemplo_de_saaty():
    # Matriz 3x3 con una pequeña inconsistencia: CR debe ser bajo (< 0,1) y los pesos, razonables
    m = [[1, 3, 5], [1 / 3, 1, 3], [1 / 5, 1 / 3, 1]]
    w, cr = mo.ahp_pesos(m)
    assert sum(w) == pytest.approx(1.0) and w[0] > w[1] > w[2]
    assert 0 < cr < 0.1


def test_ahp_rechaza_matrices_inconsistentes_y_mal_formadas():
    incoherente = [[1, 9, 1 / 9], [1 / 9, 1, 9], [9, 1 / 9, 1]]  # A>B, B>C y C>A: un ciclo
    _, cr = mo.ahp_pesos(incoherente)
    assert cr > 0.1
    with pytest.raises(ValueError, match="recíproca"):
        mo.ahp_pesos([[1, 2], [2, 1]])
    with pytest.raises(ValueError, match="cuadrada"):
        mo.ahp_pesos([[1, 2, 3], [1, 2, 3]])
