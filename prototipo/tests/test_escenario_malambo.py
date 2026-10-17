"""Escenario guionado: vendaval en Malambo, de la carga al cierre del ciclo."""
import numpy as np
import pytest
from sqlalchemy import func, select

from app import escenario_malambo as em
from app import models as m
from app import plan as pl
from app import servicios as sv
from app.cargas import cargar_viviendas
from app.config import get_settings
from app.simulacion import crear_barrios


@pytest.fixture()
def malambo(db):
    cargar_viviendas(db)
    crear_barrios(db, np.random.default_rng(1), ["08433"])
    db.commit()
    return db


def test_el_dano_baja_con_la_distancia_desde_el_epicentro(malambo):
    db = malambo
    barrios = list(db.scalars(select(m.Barrio)))
    epicentro = next(b for b in barrios if b.nombre == em.EPICENTRO)
    d = em.danos(barrios, epicentro)
    assert d[epicentro.id] == max(d.values()) == pytest.approx(em.INTENSIDAD)
    por_distancia = sorted(barrios, key=lambda b: em._km((epicentro.lat, epicentro.lon), (b.lat, b.lon)))
    valores = [d[b.id] for b in por_distancia]
    assert valores == sorted(valores, reverse=True)  # nunca sube al alejarse
    assert valores[-1] < 0.1 and valores[0] > 0.8  # de casi todo a casi nada


def test_carga_el_evento_los_reportes_y_las_10_solicitudes(malambo):
    db = malambo
    r = em.cargar(db)
    evento = db.scalar(select(m.Evento))
    assert evento.tipo == "vendaval" and evento.origen == "simulado" and "Malambo" in evento.nombre
    assert r["epicentro"] == em.EPICENTRO and r["solicitudes"] == 10

    solicitudes = db.scalars(select(m.Solicitud).order_by(m.Solicitud.id)).all()
    assert len(solicitudes) == 10 and all(s.estado == "registrada" for s in solicitudes)
    por_tipo = {t: sum(1 for s in solicitudes if s.necesidad == t) for t in {s.necesidad for s in solicitudes}}
    assert por_tipo == {"abrigo_vivienda": 8, "medicamentos": 1, "otro": 1}
    assert len({s.solicitante_id for s in solicitudes}) == 10  # diez personas distintas
    assert all(s.barrio_id and s.lat and s.lon for s in solicitudes)
    especiales = db.scalars(select(m.Vulnerabilidad).order_by(m.Vulnerabilidad.id)).all()
    assert [v.tipo for v in especiales] == ["cronica", "discapacidad"] and all(v.consentimiento for v in especiales)
    silla = next(s for s in solicitudes if s.necesidad == "otro")
    assert "silla de ruedas" in silla.descripcion and silla.fuente == "papel" and silla.creador_id != silla.solicitante_id
    assert next(s for s in solicitudes if s.necesidad == "medicamentos").urgencia == 3

    reportes = db.scalars(select(m.ReporteDanos)).all()
    assert len(reportes) >= 15
    barrios = {b.id: b for b in db.scalars(select(m.Barrio))}
    epicentro = next(b for b in barrios.values() if b.nombre == em.EPICENTRO)

    def lejania(rep):
        b = barrios[rep.barrio_id]
        return em._km((epicentro.lat, epicentro.lon), (b.lat, b.lon))

    cerca = [x.nivel_dano for x in reportes if lejania(x) < 1.2]
    lejos = [x.nivel_dano for x in reportes if lejania(x) > 1.8]
    assert cerca and lejos and np.mean(cerca) > np.mean(lejos) + 1  # lo reportan con menos daño mientras más lejos
    assert all(x.hora_captura >= evento.fecha for x in reportes)

    # todas las personas son ficticias y no tienen contraseña
    usuarios = db.scalars(select(m.Usuario)).all()
    assert usuarios and all(u.ficticio and u.password_hash is None for u in usuarios)
    assert db.scalar(select(func.count()).select_from(m.Verificacion)) == 0  # nada verificado: lo hace la cuenta real
    assert db.scalar(select(func.count()).select_from(m.PlanAsignacion)) == 0
    assert db.scalar(select(m.PuntajeBarrio.posicion).where(
        m.PuntajeBarrio.barrio_id == epicentro.id)) <= 3  # el epicentro queda entre los primeros de la lista


def test_el_inventario_alcanza_para_casi_todo_menos_la_silla(malambo):
    db = malambo
    em.cargar(db)
    lotes = db.scalars(select(m.Lote)).all()
    total = {}
    for lote in lotes:
        total[lote.tipo_bien] = total.get(lote.tipo_bien, 0) + lote.cantidad_disponible
    assert total["abrigo_vivienda"] == 40 and total["medicamentos"] == 6 and "otro" not in total
    pendientes = db.scalars(select(m.Donacion).where(m.Donacion.estado == "ofrecida")).all()
    assert len(pendientes) == 1 and pendientes[0].tipo_bien == "abrigo_vivienda" and pendientes[0].cantidad == 20


def test_solo_se_carga_sobre_una_base_sin_eventos(malambo):
    em.cargar(malambo)
    antes = malambo.scalar(select(func.count()).select_from(m.Solicitud))
    with pytest.raises(RuntimeError, match="Ya hay un evento"):
        em.cargar(malambo)
    assert malambo.scalar(select(func.count()).select_from(m.Solicitud)) == antes


def test_el_ciclo_completo_cubre_9_de_10_y_avisa_de_la_silla(malambo):
    """Verificación, plan por paquetes, entregas con código y cierre, sobre el escenario cargado."""
    db = malambo
    em.cargar(db)
    secreto = get_settings().secret_key
    brigadista = db.scalar(select(m.Usuario).where(m.Usuario.rol == "brigadista"))
    entidad = db.scalar(select(m.Usuario).where(m.Usuario.rol == "entidad"))
    for sol in db.scalars(select(m.Solicitud).order_by(m.Solicitud.id)).all():
        sv.verificar_solicitud(db, sol, brigadista, "verificado", "Verificada en campo.")

    plan = pl.calcular_plan(db, entidad)
    datos = db.get(m.PlanResumen, plan.id).datos
    solicitudes_del_plan = {l.solicitud_id for l in db.scalars(select(m.PlanLinea))}
    assert len(solicitudes_del_plan) == 9
    silla = db.scalar(select(m.Solicitud).where(m.Solicitud.necesidad == "otro"))
    assert silla.id not in solicitudes_del_plan
    sin = {s["solicitud_id"]: s for s in datos["sin_cubrir"]}
    assert set(sin) == {silla.id} and "No hay inventario compatible" in sin[silla.id]["motivo"]

    equipo = m.Usuario(nombre="Equipo", telefono="3009998888", rol="equipo_entrega", ficticio=False, password_hash="x")
    db.add(equipo)
    db.commit()
    paquetes = pl.armar_paquetes(db, plan)
    assert len(paquetes) == 2  # 9 entregas en un solo municipio: un paquete de 6 y uno de 3
    for paq in paquetes:
        pl.aprobar_paquete(db, plan, entidad, secreto, paq["solicitudes"], equipo.id)
    assert db.get(m.PlanAsignacion, plan.id).estado == "aprobado"

    for entrega in db.scalars(select(m.Entrega)).all():
        sv.en_camino(db, entrega, equipo)
        sv.confirmar_entrega(db, entrega, equipo, sv.codigo_para(secreto, entrega.id, entrega.codigo_sal))
        sol = db.get(m.Solicitud, entrega.solicitud_id)
        sv.cerrar_solicitud(db, sol, db.get(m.Usuario, sol.solicitante_id))
    estados = dict(db.execute(select(m.Solicitud.estado, func.count()).group_by(m.Solicitud.estado)).all())
    assert estados == {"cerrada": 9, "verificada": 1}  # la silla sigue esperando
    assert sv.verificar_cadena(db)[0]
