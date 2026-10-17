"""Municipios y barrios: los datos reales de los barrios, su uso en formularios y prioridades, y el paso desde sectores."""
import pytest
from sqlalchemy import func, select

from app import models as m
from app import puntaje as pj
from app.cargas import cargar_viviendas
from app.migracion import migrar_sectores_a_barrios
from app.simulacion import generar
from app.territorio import MUNICIPIOS, corregir_nombres_municipios, leer_barrios
from tests.test_operacion import crear_usuario, entrar, mundo, salir  # noqa: F401
from tests.test_web import app_cliente, sesiones  # noqa: F401


def test_el_archivo_tiene_barrios_de_los_23_municipios():
    por_municipio = leer_barrios()
    assert set(por_municipio) == set(MUNICIPIOS) and len(MUNICIPIOS) == 23
    assert all(por_municipio[c] for c in MUNICIPIOS)
    nombres = {b["nombre"] for b in por_municipio["08001"]}
    assert {"Rebolo", "El Prado", "La Chinita"} <= nombres
    for lugares in por_municipio.values():
        assert len({x["nombre"] for x in lugares}) == len(lugares)  # sin repetidos dentro de un municipio
        assert all(10.0 < x["lat"] < 11.2 and -75.3 < x["lon"] < -74.6 for x in lugares)  # dentro del Atlántico
        assert all(x["tipo"] in ("barrio", "centro poblado") for x in lugares)


def test_los_barrios_creados_son_los_del_archivo_y_se_muestran_con_su_municipio(db):
    cargar_viviendas(db)
    generar(db, semilla=7, tipo="inundacion", municipios=["08001", "08758"])
    barrio = db.scalar(select(m.Barrio).where(m.Barrio.nombre == "Rebolo"))
    assert barrio.municipio_codigo == "08001" and barrio.tipo == "barrio"
    assert db.scalar(select(m.Barrio.etiqueta).where(m.Barrio.id == barrio.id)) == "Rebolo, Barranquilla"
    assert not db.scalars(select(m.Barrio).where(m.Barrio.nombre.like("% - Barrio %"))).all()  # ya no hay sectores


def test_los_nombres_de_municipios_quedan_con_sus_tildes(db):
    cargar_viviendas(db)
    db.get(m.Municipio, "08436").nombre = "Manat�"  # como venía en el archivo de viviendas
    db.commit()
    assert corregir_nombres_municipios(db) == 1
    assert db.get(m.Municipio, "08436").nombre == "Manatí"
    assert db.get(m.Municipio, "08606").nombre == "Repelón"
    assert corregir_nombres_municipios(db) == 0


def test_la_migracion_no_hace_nada_si_no_hay_sectores(engine):
    assert migrar_sectores_a_barrios(engine) is None


# ----------------------------------------------------------------------------- formularios y prioridades
@pytest.fixture()
def con_barrios(sesiones):
    with sesiones() as db:
        cargar_viviendas(db)
        generar(db, semilla=5, tipo="inundacion", municipios=["08001", "08758"])
        pj.recalcular(db)
    crear_usuario(sesiones, "solicitante", "3100000001")
    crear_usuario(sesiones, "entidad", "3100000004")


def test_el_formulario_agrupa_los_barrios_por_municipio(app_cliente, con_barrios):
    entrar(app_cliente, "3100000001")
    html = app_cliente.get("/solicitudes/nueva").text
    assert '<optgroup label="Barranquilla">' in html and '<optgroup label="Soledad">' in html
    assert "Rebolo" in html and "data-municipio" in html
    assert "Barrio 01" not in html


def test_prioridades_resume_por_municipio_y_filtra(app_cliente, con_barrios):
    entrar(app_cliente, "3100000004")
    todo = app_cliente.get("/prioridades").text
    assert "<h2>Municipios</h2>" in todo and "prioridades?municipio=08001" in todo and "prioridades?municipio=08758" in todo
    soledad = app_cliente.get("/prioridades?municipio=08758").text
    assert "Barrios de Soledad" in soledad
    assert "<td>Barranquilla</td>" not in soledad.split("<h2>Barrios")[1]  # la tabla de barrios solo trae Soledad
    assert app_cliente.get("/prioridades?municipio=NOEXISTE").status_code == 200  # un código raro se ignora


def test_cada_municipio_del_resumen_trae_sus_conteos(sesiones, db):
    cargar_viviendas(db)
    generar(db, semilla=5, tipo="inundacion", municipios=["08001", "08758"])
    pj.recalcular(db)
    from app.rutas.prioridades import _resumen_municipios

    filas = {r["codigo"]: r for r in _resumen_municipios(db)}
    assert set(filas) == {"08001", "08758"}
    for codigo, r in filas.items():
        n = db.scalar(select(func.count()).select_from(m.Barrio).where(m.Barrio.municipio_codigo == codigo))
        assert r["barrios"] == n and 0 <= r["promedio"] <= r["maxima"] <= 1
