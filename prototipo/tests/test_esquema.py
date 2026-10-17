import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.cargas import cargar_viviendas
from app.models import (
    CentroAcopio,
    Donacion,
    Donante,
    Lote,
    Municipio,
    Barrio,
    Solicitud,
    Usuario,
    ViviendaProyeccion,
    Vulnerabilidad,
)


def test_carga_viviendas(db):
    resumen = cargar_viviendas(db)
    assert resumen["municipios"] == 23
    assert resumen["proyecciones"] == 23 * 3 * 18  # 23 municipios x 3 áreas x años 2018-2035
    barranquilla = db.scalar(
        select(ViviendaProyeccion.viviendas).where(
            ViviendaProyeccion.municipio_codigo == "08001",
            ViviendaProyeccion.area == "Total",
            ViviendaProyeccion.anio == 2026,
        )
    )
    assert barranquilla == 439319  # '439.319' en el archivo


def test_carga_es_idempotente(db):
    cargar_viviendas(db)
    assert cargar_viviendas(db) == {"municipios": 0, "proyecciones": 0}
    assert db.scalar(select(func.count()).select_from(Municipio)) == 23


def _crear_base(db):
    db.add(Municipio(codigo="08001", nombre="Barranquilla"))
    db.flush()
    barrio = Barrio(municipio_codigo="08001", nombre="Barrio de prueba")
    persona = Usuario(nombre="Persona Ficticia", telefono="3000000000", rol="solicitante")
    db.add_all([barrio, persona])
    db.flush()
    return barrio, persona


def test_vulnerabilidad_exige_consentimiento(db):
    barrio, persona = _crear_base(db)
    sol = Solicitud(solicitante_id=persona.id, creador_id=persona.id, barrio_id=barrio.id, necesidad="agua")
    db.add(sol)
    db.flush()
    db.add(Vulnerabilidad(solicitud_id=sol.id, tipo="discapacidad", descripcion_situacion="x", consentimiento=False))
    with pytest.raises(IntegrityError):
        db.flush()


def test_lote_conserva_el_inventario(db):
    barrio, persona = _crear_base(db)
    centro = CentroAcopio(nombre="Centro de prueba", barrio_id=barrio.id)
    donante = Donante(nombre="Donante Ficticio", tipo="persona")
    db.add_all([centro, donante])
    db.flush()
    don = Donacion(donante_id=donante.id, centro_id=centro.id, tipo_bien="agua", cantidad=100)
    db.add(don)
    db.flush()
    ok = Lote(
        donacion_id=don.id, centro_id=centro.id, tipo_bien="agua",
        cantidad_recibida=100, cantidad_disponible=70, cantidad_reservada=20, cantidad_entregada=10,
    )
    db.add(ok)
    db.flush()  # suma 100: permitido

    descuadrado = Lote(
        donacion_id=don.id, centro_id=centro.id, tipo_bien="agua",
        cantidad_recibida=100, cantidad_disponible=70, cantidad_reservada=20, cantidad_entregada=20,
    )
    db.add(descuadrado)
    with pytest.raises(IntegrityError):  # suma 110: el saldo no cuadra
        db.flush()
