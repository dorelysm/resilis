from datetime import timedelta

import pytest
from sqlalchemy import select

from app import models as m
from app import motor
from app import puntaje as pj
from app.cargas import cargar_viviendas
from app.models import ahora
from app.simulacion import generar


# ----------------------------------------------------------------------------- un mundo pequeño y controlado
@pytest.fixture()
def mini(db):
    db.add(m.Municipio(codigo="08001", nombre="Barranquilla"))
    db.flush()
    evento = m.Evento(tipo="inundacion", nombre="Evento real de prueba", fecha=ahora() - timedelta(hours=2),
                      origen=m.OrigenDato.REAL)
    db.add(evento)
    gente = {
        "ciudadano": m.Usuario(nombre="Ciudadano A", telefono="1", rol="solicitante", ficticio=False),
        "ciudadano2": m.Usuario(nombre="Ciudadano B", telefono="2", rol="solicitante", ficticio=False),
        "brigadista": m.Usuario(nombre="Brigadista", telefono="3", rol="brigadista", ficticio=False),
        "entidad": m.Usuario(nombre="Entidad", telefono="4", rol="entidad", ficticio=False),
    }
    db.add_all(gente.values())
    db.flush()
    return {"evento": evento, "gente": gente}


def barrio(db, nombre, **kw):
    s = m.Barrio(municipio_codigo="08001", nombre=nombre, personas=1000, viviendas=300,
                 amenaza_base=kw.pop("amenaza_base", 0.3), vulnerabilidad_base=kw.pop("vulnerabilidad_base", 0.3),
                 acceso_base=kw.pop("acceso_base", 1.0), **kw)
    db.add(s)
    db.flush()
    return s


def reporte(db, mini, s, autor, nivel, horas=1.0, personas=100, acceso=1.0):
    r = m.ReporteDanos(barrio_id=s.id, evento_id=mini["evento"].id, autor_id=mini["gente"][autor].id,
                       hora_evento=ahora() - timedelta(hours=horas), hora_captura=ahora() - timedelta(hours=horas),
                       nivel_dano=nivel, personas_afectadas=personas, acceso=acceso)
    db.add(r)
    db.flush()
    return r


def puntaje_de(db, s):
    return db.get(m.PuntajeBarrio, s.id)


def verificar(db, mini, obj_tipo, obj_id, resultado="verificado"):
    db.add(m.Verificacion(objeto_tipo=obj_tipo, objeto_id=obj_id, verificador_id=mini["gente"]["brigadista"].id,
                          resultado=resultado))
    db.flush()


# ----------------------------------------------------------------------------- barrios
def test_el_barrio_con_daño_grave_confirmado_supera_al_de_daño_leve_dudoso(db, mini):
    a, b = barrio(db, "A grave"), barrio(db, "B leve")
    reporte(db, mini, a, "brigadista", 3, personas=400)
    reporte(db, mini, a, "entidad", 3, personas=380)
    reporte(db, mini, b, "ciudadano", 1, personas=20)
    pj.recalcular(db, mini["evento"])
    pa, pb = puntaje_de(db, a), puntaje_de(db, b)
    assert pa.prioridad > pb.prioridad and pa.posicion == 1 and pb.posicion == 2
    assert pa.confianza > pb.confianza  # fuentes de más peso y corroborados


def test_verificar_sube_la_confianza_y_desmentir_la_anula(db, mini):
    s = barrio(db, "S")
    r = reporte(db, mini, s, "ciudadano", 2)
    pj.recalcular(db, mini["evento"])
    antes = puntaje_de(db, s).confianza
    verificar(db, mini, "reporte", r.id)
    pj.recalcular(db, mini["evento"])
    assert puntaje_de(db, s).confianza > antes

    verificar(db, mini, "reporte", r.id, "desmentido")  # la última revisión es la que vale
    pj.recalcular(db, mini["evento"])
    p = puntaje_de(db, s)
    assert db.get(m.ReporteDanos, r.id).confianza == 0.0
    assert p.confianza == 0.0 and "sin_reportes" in p.alertas and p.base_previa  # un reporte falso no cuenta


def test_sin_reportes_se_usa_la_linea_base_y_se_avisa(db, mini):
    riesgoso = barrio(db, "Riesgoso", amenaza_base=0.9, vulnerabilidad_base=0.9)
    seguro = barrio(db, "Seguro", amenaza_base=0.1, vulnerabilidad_base=0.1)
    pj.recalcular(db, mini["evento"])
    r, s = puntaje_de(db, riesgoso), puntaje_de(db, seguro)
    assert r.posicion == 1 and r.prioridad > s.prioridad  # recomienda desde la hora cero
    for p in (r, s):
        assert p.confianza == 0.0 and p.base_previa and p.alertas == ["sin_reportes"]


def test_reportes_que_se_contradicen_bajan_la_confianza_y_alertan(db, mini):
    coinciden, chocan = barrio(db, "Coinciden"), barrio(db, "Chocan")
    reporte(db, mini, coinciden, "brigadista", 2)
    reporte(db, mini, coinciden, "ciudadano", 2)
    reporte(db, mini, chocan, "brigadista", 0)
    reporte(db, mini, chocan, "ciudadano", 3)
    pj.recalcular(db, mini["evento"])
    pc, px = puntaje_de(db, coinciden), puntaje_de(db, chocan)
    assert px.dispersion > motor.UMBRAL_DISPERSION and "contradictorio" in px.alertas
    assert pc.dispersion == 0.0 and "contradictorio" not in pc.alertas
    assert px.confianza < pc.confianza


def test_un_dato_viejo_pesa_menos_en_un_evento_real(db, mini):
    reciente, viejo = barrio(db, "Reciente"), barrio(db, "Viejo")
    reporte(db, mini, reciente, "brigadista", 2, horas=1)
    reporte(db, mini, viejo, "brigadista", 2, horas=40)
    pj.recalcular(db, mini["evento"])
    assert puntaje_de(db, viejo).confianza < puntaje_de(db, reciente).confianza
    assert "desactualizado" in puntaje_de(db, viejo).alertas
    assert "desactualizado" not in puntaje_de(db, reciente).alertas


def test_la_baja_accesibilidad_no_penaliza(db, mini):
    libre, aislado = barrio(db, "Libre"), barrio(db, "Aislado")
    for s, acceso in ((libre, 1.0), (aislado, 0.0)):
        reporte(db, mini, s, "brigadista", 2, personas=100, acceso=acceso)
    pj.recalcular(db, mini["evento"])
    assert puntaje_de(db, aislado).prioridad >= puntaje_de(db, libre).prioridad  # nunca queda por debajo


def test_cada_puntaje_se_explica(db, mini):
    a, b = barrio(db, "A"), barrio(db, "B")
    reporte(db, mini, a, "brigadista", 3, personas=500)
    reporte(db, mini, b, "ciudadano", 1, personas=10)
    pj.recalcular(db, mini["evento"])
    p = puntaje_de(db, a)
    assert set(p.indicadores) == set(motor.CRITERIOS_BARRIO) == set(p.aportes)
    assert sum(p.aportes.values()) == pytest.approx(1.0, abs=0.01)
    assert p.aportes["gravedad"] > p.aportes["accesibilidad"]  # el barrio A destaca por su gravedad


# ----------------------------------------------------------------------------- solicitudes
def solicitud(db, mini, s, urgencia, hogar, quien="ciudadano", estado="verificada", vulnerable=None, horas=1.0):
    sol = m.Solicitud(solicitante_id=mini["gente"][quien].id, creador_id=mini["gente"][quien].id, barrio_id=s.id,
                      evento_id=mini["evento"].id, necesidad="agua", cantidad=hogar * 6, personas_hogar=hogar,
                      urgencia=urgencia, estado=estado, creado_en=ahora() - timedelta(hours=horas))
    db.add(sol)
    db.flush()
    if vulnerable:
        db.add(m.Vulnerabilidad(solicitud_id=sol.id, tipo=vulnerable, descripcion_situacion="x", consentimiento=True))
        db.flush()
    return sol


def test_una_solicitud_urgente_y_vulnerable_va_antes(db, mini):
    s = barrio(db, "S")
    reporte(db, mini, s, "brigadista", 2)
    tranquila = solicitud(db, mini, s, urgencia=0, hogar=2)
    urgente = solicitud(db, mini, s, urgencia=3, hogar=2, vulnerable="discapacidad")
    pj.recalcular(db, mini["evento"])
    assert urgente.prioridad > tranquila.prioridad


def test_la_espera_sube_la_posicion_de_quien_lleva_mas_tiempo(db, mini):
    s = barrio(db, "S")
    reporte(db, mini, s, "brigadista", 2)
    nueva = solicitud(db, mini, s, urgencia=1, hogar=3, horas=0.5)
    vieja = solicitud(db, mini, s, urgencia=1, hogar=3, horas=30)
    pj.recalcular(db, mini["evento"])
    assert vieja.prioridad > nueva.prioridad  # igual en todo lo demás: la que más espera va primero


def test_solo_se_recalculan_las_solicitudes_pendientes(db, mini):
    s = barrio(db, "S")
    entregada = solicitud(db, mini, s, 3, 2, estado="entregada")
    anulada = solicitud(db, mini, s, 3, 2, estado="anulada")
    pendiente = solicitud(db, mini, s, 3, 2, estado="registrada")
    pj.recalcular(db, mini["evento"])
    assert entregada.prioridad is None and anulada.prioridad is None
    assert pendiente.prioridad is not None and pendiente.confianza is not None


def test_la_solicitud_verificada_inspira_mas_confianza(db, mini):
    s = barrio(db, "S")
    a = solicitud(db, mini, s, 2, 2, estado="registrada")
    b = solicitud(db, mini, s, 2, 2, estado="registrada")
    verificar(db, mini, "solicitud", b.id)
    pj.recalcular(db, mini["evento"])
    assert b.confianza > a.confianza


def test_las_solicitudes_suben_la_urgencia_de_su_barrio(db, mini):
    con, sin = barrio(db, "Con solicitudes"), barrio(db, "Sin solicitudes")
    for s in (con, sin):
        reporte(db, mini, s, "brigadista", 2, personas=100)
    solicitud(db, mini, con, urgencia=3, hogar=4, vulnerable="menor")
    pj.recalcular(db, mini["evento"])
    assert puntaje_de(db, con).prioridad > puntaje_de(db, sin).prioridad


# ----------------------------------------------------------------------------- pesos
def test_los_pesos_se_guardan_normalizados_y_cambian_el_orden(db, mini):
    grave, aislado = barrio(db, "Grave"), barrio(db, "Aislado")
    reporte(db, mini, grave, "brigadista", 3, personas=300, acceso=1.0)
    reporte(db, mini, aislado, "brigadista", 1, personas=20, acceso=0.0)
    pj.recalcular(db, mini["evento"])
    assert puntaje_de(db, grave).posicion == 1  # con los pesos iniciales manda la gravedad

    guardado = pj.guardar_pesos(db, "barrio", {"gravedad": 0, "urgencia": 0, "expuestas": 0, "accesibilidad": 10,
                                               "recursos": 0}, mini["gente"]["entidad"])
    assert guardado["accesibilidad"] == 1.0 and sum(guardado.values()) == pytest.approx(1.0)
    pj.recalcular(db, mini["evento"])
    assert puntaje_de(db, aislado).posicion == 1  # ahora el acceso decide
    assert sum(pj.leer_pesos(db)["barrio"].values()) == pytest.approx(1.0)
    bitacora = db.scalar(select(m.Bitacora).where(m.Bitacora.accion == "cambiar_pesos"))
    assert bitacora.usuario_id == mini["gente"]["entidad"].id and bitacora.detalle["accesibilidad"] == 1.0


def test_pesos_por_defecto_si_no_hay_nada_guardado(db):
    p = pj.leer_pesos(db)
    assert p["barrio"]["gravedad"] == pytest.approx(0.30) and p["solicitud"]["urgencia"] == pytest.approx(0.30)


# ----------------------------------------------------------------------------- con el escenario simulado
@pytest.fixture()
def escenario(db):
    cargar_viviendas(db)
    generar(db, semilla=42, tipo="inundacion")
    return db


def test_el_escenario_simulado_queda_completo_y_ordenado(escenario):
    db = escenario
    resumen = pj.recalcular(db)
    puntajes = db.scalars(select(m.PuntajeBarrio).order_by(m.PuntajeBarrio.posicion)).all()
    assert resumen["barrios"] == len(puntajes) == 600
    assert [p.posicion for p in puntajes] == list(range(1, 601))
    assert all(0.0 <= p.prioridad <= 1.0 and 0.0 <= p.confianza <= 1.0 for p in puntajes)
    prioridades = [p.prioridad for p in puntajes]
    assert prioridades == sorted(prioridades, reverse=True)
    sin = [p for p in puntajes if p.n_reportes == 0]
    assert sin and all(p.confianza == 0.0 and "sin_reportes" in p.alertas for p in sin)
    assert any(p.confianza > 0 for p in puntajes)


def test_la_prioridad_sigue_al_dano_real_simulado(escenario):
    """Validación sintética: los barrios con más daño real quedan arriba, aunque los reportes tengan ruido."""
    db = escenario
    pj.recalcular(db)
    verdad = db.scalar(select(m.Bitacora.detalle).where(m.Bitacora.accion == "simulacion_verdad"))["dano"]
    puntajes = {p.barrio_id: p.prioridad for p in db.scalars(select(m.PuntajeBarrio))}
    ids = list(puntajes)
    d = [verdad[str(i)] for i in ids]
    p = [puntajes[i] for i in ids]
    from scipy.stats import spearmanr

    rho = spearmanr(d, p).statistic
    assert rho > 0.5, f"la correlación entre el daño real y la prioridad fue solo {rho:.2f}"


def test_el_escenario_simulado_no_envejece(escenario, monkeypatch):
    db = escenario
    pj.recalcular(db)
    antes = [(p.barrio_id, p.prioridad, p.confianza) for p in db.scalars(select(m.PuntajeBarrio).order_by(m.PuntajeBarrio.barrio_id))]
    monkeypatch.setattr(pj, "ahora", lambda: ahora() + timedelta(days=10))
    pj.recalcular(db)
    despues = [(p.barrio_id, p.prioridad, p.confianza) for p in db.scalars(select(m.PuntajeBarrio).order_by(m.PuntajeBarrio.barrio_id))]
    assert antes == despues


def test_recalcular_es_repetible(escenario):
    db = escenario
    pj.recalcular(db)
    uno = [p.prioridad for p in db.scalars(select(m.PuntajeBarrio).order_by(m.PuntajeBarrio.barrio_id))]
    pj.recalcular(db)
    dos = [p.prioridad for p in db.scalars(select(m.PuntajeBarrio).order_by(m.PuntajeBarrio.barrio_id))]
    assert uno == dos


def test_las_solicitudes_simuladas_quedan_priorizadas(escenario):
    db = escenario
    pj.recalcular(db)
    sols = db.scalars(select(m.Solicitud).where(m.Solicitud.estado == "registrada")).all()
    assert sols and all(s.prioridad is not None and 0 <= s.prioridad <= 1 and 0 <= s.confianza <= 1 for s in sols)
    vuln = {v.solicitud_id for v in db.scalars(select(m.Vulnerabilidad))}
    media_vuln = sum(s.prioridad for s in sols if s.id in vuln) / max(1, sum(1 for s in sols if s.id in vuln))
    media_otras = sum(s.prioridad for s in sols if s.id not in vuln) / max(1, sum(1 for s in sols if s.id not in vuln))
    assert media_vuln > media_otras  # las personas vulnerables quedan, en promedio, más arriba
