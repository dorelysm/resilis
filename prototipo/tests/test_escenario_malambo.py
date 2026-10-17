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
from tests.test_web import app_cliente, sesiones  # noqa: F401


@pytest.fixture()
def malambo(db):
    cargar_viviendas(db)
    crear_barrios(db, np.random.default_rng(1), ["08433"])
    db.commit()
    return db


def test_solo_cinco_barrios_muy_cercanos_quedan_afectados_con_el_epicentro_al_centro(malambo):
    db = malambo
    barrios = list(db.scalars(select(m.Barrio)))
    epicentro = next(b for b in barrios if b.nombre == em.EPICENTRO)
    d = em.danos(barrios, epicentro)
    cerca = em.afectados(barrios, epicentro)
    assert len(cerca) == 5 and cerca[0].id == epicentro.id
    assert sum(1 for v in d.values() if v > 0) == 5  # ningún otro barrio de Malambo queda afectado
    assert d[epicentro.id] == max(d.values()) == pytest.approx(em.INTENSIDAD)
    distancias = [em._km((epicentro.lat, epicentro.lon), (b.lat, b.lon)) for b in cerca]
    assert max(distancias) < 0.4  # los cinco están a menos de 400 m del epicentro: bastante cerca
    valores = [d[b.id] for b in cerca]
    assert valores == sorted(valores, reverse=True) and valores[0] > valores[1] > 0  # baja desde el centro
    lejos = [b for b in barrios if d[b.id] == 0]
    assert len(lejos) == len(barrios) - 5


def test_carga_el_evento_los_reportes_y_las_10_solicitudes(malambo):
    db = malambo
    r = em.cargar(db)
    evento = db.scalar(select(m.Evento))
    assert evento.tipo == "vendaval" and evento.origen == "simulado" and "Malambo" in evento.nombre
    assert r["epicentro"] == em.EPICENTRO and r["solicitudes"] == 10 and len(r["afectados"]) == 5

    barrios = {b.id: b for b in db.scalars(select(m.Barrio))}
    afectados = {b.id for b in em.afectados(list(barrios.values()), next(b for b in barrios.values() if b.nombre == em.EPICENTRO))}

    reportes = db.scalars(select(m.ReporteDanos)).all()
    assert 12 <= len(reportes) <= 30  # pocos: la información cabe en una pantalla
    assert {x.barrio_id for x in reportes} == afectados  # reportes solo en Malambo y solo en los 5 barrios afectados
    assert all(barrios[x.barrio_id].municipio_codigo == "08433" for x in reportes)
    assert all(x.hora_captura >= evento.fecha for x in reportes)

    solicitudes = db.scalars(select(m.Solicitud).order_by(m.Solicitud.id)).all()
    assert len(solicitudes) == 10 and all(s.estado == "registrada" for s in solicitudes)
    assert {s.barrio_id for s in solicitudes} <= afectados  # las solicitudes salen de los barrios afectados
    por_tipo = {t: sum(1 for s in solicitudes if s.necesidad == t) for t in {s.necesidad for s in solicitudes}}
    assert por_tipo == {"abrigo_vivienda": 8, "medicamentos": 1, "otro": 1}
    assert len({s.solicitante_id for s in solicitudes}) == 10  # diez personas distintas
    epi = next(b.id for b in barrios.values() if b.nombre == em.EPICENTRO)
    assert sum(1 for s in solicitudes if s.barrio_id == epi) == 3  # el epicentro es donde más piden
    assert all(s.lat and s.lon for s in solicitudes)
    especiales = db.scalars(select(m.Vulnerabilidad).order_by(m.Vulnerabilidad.id)).all()
    assert [v.tipo for v in especiales] == ["cronica", "discapacidad"] and all(v.consentimiento for v in especiales)
    silla = next(s for s in solicitudes if s.necesidad == "otro")
    assert "silla de ruedas" in silla.descripcion and silla.fuente == "papel" and silla.creador_id != silla.solicitante_id
    assert next(s for s in solicitudes if s.necesidad == "medicamentos").urgencia == 3

    # todas las personas son ficticias y no tienen contraseña
    usuarios = db.scalars(select(m.Usuario)).all()
    assert usuarios and all(u.ficticio and u.password_hash is None for u in usuarios)
    assert db.scalar(select(func.count()).select_from(m.Verificacion)) == 0  # nada verificado: lo hace la cuenta real
    assert db.scalar(select(func.count()).select_from(m.PlanAsignacion)) == 0
    assert db.scalar(select(m.PuntajeBarrio.posicion).where(m.PuntajeBarrio.barrio_id == epi)) <= 3


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


def test_prioridades_muestra_por_defecto_solo_los_barrios_con_informacion(app_cliente, sesiones):
    from tests.test_operacion import crear_usuario, entrar

    with sesiones() as db:
        cargar_viviendas(db)
        crear_barrios(db, np.random.default_rng(1), ["08433", "08001"])
        db.commit()
        em.cargar(db)
    crear_usuario(sesiones, "entidad", "3100000004")
    entrar(app_cliente, "3100000004")
    pagina = app_cliente.get("/prioridades").text
    assert "5 barrios con información" in pagina and pagina.count("/prioridades/barrios/") == 5
    assert "Ver también los barrios sin información" in pagina
    assert "<td>Barranquilla</td>" not in pagina  # el otro municipio no aparece: no tiene reportes ni solicitudes
    nombres = [t.split("</a>")[0].split(">")[-1] for t in pagina.split("/prioridades/barrios/")[1:]]
    assert set(nombres) == {"El Edén", "El Edén II", "Villa Campo", "Los Mangos", "Cristo Rey"}  # los 5 afectados, y nada más
    assert "El Edén" in nombres[:3]  # el epicentro queda entre los primeros
    todo = app_cliente.get("/prioridades?sin_info=si").text
    assert todo.count("/prioridades/barrios/") == 25 and "Ver solo los 5 con información" in todo


def test_al_abrir_un_barrio_se_ve_el_detalle_de_sus_solicitudes(app_cliente, sesiones):
    from tests.test_operacion import crear_usuario, entrar

    with sesiones() as db:
        cargar_viviendas(db)
        crear_barrios(db, np.random.default_rng(1), ["08433"])
        db.commit()
        em.cargar(db)
        medicinas = db.scalar(select(m.Solicitud).where(m.Solicitud.necesidad == "medicamentos"))
        silla = db.scalar(select(m.Solicitud).where(m.Solicitud.necesidad == "otro"))
        ids = {"medicinas": (medicinas.barrio_id, medicinas.id), "silla": (silla.barrio_id, silla.id)}
    crear_usuario(sesiones, "entidad", "3100000004")
    entrar(app_cliente, "3100000004")

    pagina = app_cliente.get(f"/prioridades/barrios/{ids['silla'][0]}").text
    assert "Otro: Silla de ruedas estándar" in pagina and "se partió una rueda" in pagina
    assert f'/recorrido/solicitudes/{ids["silla"][1]}"' in pagina  # y desde ahí se abre su recorrido
    pagina = app_cliente.get(f"/prioridades/barrios/{ids['medicinas'][0]}").text
    assert "Medicamentos: Losartán 50 mg y metformina 850 mg" in pagina and "uso diario" in pagina
    epicentro = app_cliente.get("/prioridades").text  # el epicentro tiene sus 3 solicitudes de reparación
    barrio_epi = [t for t in epicentro.split('href="/prioridades/barrios/')[1:] if t.split("</a>")[0].endswith("El Edén")][0].split('"')[0]
    pagina = app_cliente.get(f"/prioridades/barrios/{barrio_epi}").text
    assert pagina.count("Abrigo vivienda") >= 3 and "láminas" in pagina
    for sensible in ("Teléfono", "Calle "):
        assert sensible not in pagina  # sin direcciones ni teléfonos


def test_un_centro_real_sin_ubicacion_queda_en_malambo_para_que_se_vea_la_ruta(malambo):
    db = malambo
    acopio = m.Usuario(nombre="Acopio real", telefono="3004445566", rol="centro_acopio", ficticio=False, password_hash="x")
    db.add(acopio)
    db.flush()
    centro = m.CentroAcopio(nombre="Centro real sin barrio", responsable_id=acopio.id)
    db.add(centro)
    db.commit()
    em.cargar(db)
    db.refresh(centro)
    assert centro.barrio_id and centro.lat and centro.lon
    barrios = {b.id: b for b in db.scalars(select(m.Barrio))}
    epicentro = next(b for b in barrios.values() if b.nombre == em.EPICENTRO)
    km = em._km((epicentro.lat, epicentro.lon), (centro.lat, centro.lon))
    assert 0.8 < km < 2.5 and barrios[centro.barrio_id].municipio_codigo == "08433"
    assert centro.barrio_id not in {b.id for b in em.afectados(list(barrios.values()), epicentro)}
