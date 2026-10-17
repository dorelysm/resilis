import numpy as np
import pytest
from sqlalchemy import func, select

from app import models as m
from app.cargas import cargar_viviendas
from app.simulacion import MUNICIPIOS, generar


@pytest.fixture()
def base(db):
    cargar_viviendas(db)
    return db


def _huella(db):
    """Resumen comparable de lo generado, para verificar que se repite con la misma semilla."""
    return (
        [(s.nombre, s.viviendas, s.personas, s.vulnerabilidad_base) for s in db.scalars(select(m.Sector).order_by(m.Sector.id))],
        [(r.sector_id, r.nivel_dano, r.personas_afectadas) for r in db.scalars(select(m.ReporteDanos).order_by(m.ReporteDanos.id))],
        [(s.necesidad, s.cantidad, s.urgencia) for s in db.scalars(select(m.Solicitud).order_by(m.Solicitud.id))],
        [(lote.tipo_bien, lote.cantidad_recibida) for lote in db.scalars(select(m.Lote).order_by(m.Lote.id))],
    )


def test_misma_semilla_mismos_datos(engine):
    from sqlalchemy.orm import sessionmaker

    huellas = []
    for _ in range(2):
        with sessionmaker(bind=engine, expire_on_commit=False)() as db:
            cargar_viviendas(db)
            generar(db, semilla=7, tipo="vendaval")
            huellas.append(_huella(db))
    assert huellas[0] == huellas[1]


def test_semillas_distintas_dan_datos_distintos(base):
    generar(base, semilla=1, tipo="inundacion")
    a = _huella(base)
    generar(base, semilla=2, tipo="inundacion")
    assert a != _huella(base)


def test_las_viviendas_de_los_sectores_suman_la_cifra_municipal(base):
    generar(base, semilla=3, tipo="terremoto")
    for codigo in MUNICIPIOS:
        real = base.scalar(select(m.ViviendaProyeccion.viviendas).where(
            m.ViviendaProyeccion.municipio_codigo == codigo, m.ViviendaProyeccion.area == "Cabecera",
            m.ViviendaProyeccion.anio == 2026))
        simulado = base.scalar(select(func.sum(m.Sector.viviendas)).where(m.Sector.municipio_codigo == codigo))
        assert simulado == real, codigo


def test_todo_lo_personal_es_ficticio(base):
    generar(base, semilla=4, tipo="inundacion")
    usuarios = base.scalars(select(m.Usuario)).all()
    assert usuarios and all(u.ficticio for u in usuarios)
    assert all(u.telefono.startswith("999") for u in usuarios)  # no son celulares colombianos válidos
    assert all(u.documento is None or u.documento.startswith("SIM-") for u in usuarios)
    assert all(u.consentimiento_datos for u in usuarios)


def test_las_vulnerabilidades_tienen_consentimiento(base):
    generar(base, semilla=5, tipo="deslizamiento")
    vulnerables = base.scalars(select(m.Vulnerabilidad)).all()
    assert vulnerables and all(v.consentimiento for v in vulnerables)


def test_el_inventario_cuadra_y_deja_movimientos(base):
    resumen = generar(base, semilla=6, tipo="inundacion")
    lotes = base.scalars(select(m.Lote)).all()
    assert len(lotes) == resumen["lotes"] > 0
    for lote in lotes:
        assert (lote.cantidad_disponible + lote.cantidad_reservada + lote.cantidad_entregada
                == lote.cantidad_recibida)
    movimientos = base.scalar(select(func.count()).select_from(m.MovimientoInventario))
    assert movimientos == len(lotes)


def test_hay_sectores_sin_reportes_y_desordenes_conocidos(base):
    """La simulación deja información faltante, duplicados y falsos, para que el modelo los detecte."""
    generar(base, semilla=8, tipo="inundacion")
    con_reporte = {r for (r,) in base.execute(select(m.ReporteDanos.sector_id).distinct())}
    todos = {s for (s,) in base.execute(select(m.Sector.id))}
    assert todos - con_reporte, "debe haber sectores sin ningún reporte"
    verdad = base.scalar(select(m.Bitacora.detalle).where(m.Bitacora.accion == "simulacion_verdad"))
    assert verdad["duplicadas"] and verdad["reportes_falsos"]


def _correlacion(base, tipo, semilla, otra):
    generar(base, semilla=semilla, tipo=tipo)
    verdad = base.scalar(select(m.Bitacora.detalle).where(m.Bitacora.accion == "simulacion_verdad"))["dano"]
    ev = base.scalar(select(m.Evento))
    sectores = base.scalars(select(m.Sector)).all()
    d = np.array([verdad[str(s.id)] for s in sectores])
    x = np.array(otra(sectores, ev))
    return float(np.corrcoef(d, x)[0, 1])


def test_cada_tipo_de_evento_tiene_su_patron(base):
    # Terremoto: el daño baja al alejarse del foco
    dist = lambda ss, ev: [np.hypot(s.lat - ev.zona["lat"], s.lon - ev.zona["lon"]) for s in ss]
    assert _correlacion(base, "terremoto", 11, dist) < -0.4
    # Inundación: el daño sigue a la amenaza de base (zonas bajas)
    assert _correlacion(base, "inundacion", 12, lambda ss, ev: [s.amenaza_base for s in ss]) > 0.6
    # Deslizamiento: localizado; muchos sectores casi sin daño
    generar(base, semilla=13, tipo="deslizamiento")
    verdad = base.scalar(select(m.Bitacora.detalle).where(m.Bitacora.accion == "simulacion_verdad"))["dano"]
    assert np.median(list(verdad.values())) < 0.1


def test_reiniciar_deja_el_sistema_como_al_inicio(base):
    generar(base, semilla=9, tipo="vendaval")
    generar(base, semilla=9, tipo="vendaval")  # reinicia por defecto: no se acumulan datos
    assert base.scalar(select(func.count()).select_from(m.Evento)) == 1
    assert base.scalar(select(func.count()).select_from(m.Municipio)) == 23  # lo real no se toca


def test_no_reinicia_si_hay_cuentas_reales(base):
    generar(base, semilla=10, tipo="inundacion")
    base.add(m.Usuario(nombre="Persona Real", telefono="3001112233", rol="solicitante", ficticio=False))
    base.commit()
    with pytest.raises(RuntimeError, match="cuentas reales"):
        generar(base, semilla=10, tipo="inundacion")  # reiniciar=True por defecto
    assert base.scalar(select(func.count()).select_from(m.Usuario).where(m.Usuario.ficticio.is_(False))) == 1


def test_sin_viviendas_cargadas_avisa(db):
    with pytest.raises(RuntimeError, match="app.cargas"):
        generar(db, semilla=1)


def test_reiniciar_borra_tambien_lo_calculado(base):
    """Los puntajes y los planes dependen de los sectores y las solicitudes: al reiniciar deben borrarse con ellos."""
    from app import plan as pl
    from app import puntaje as pj

    generar(base, semilla=21, tipo="inundacion")
    pj.recalcular(base)
    entidad = base.scalar(select(m.Usuario).where(m.Usuario.rol == "entidad"))
    assert pl.calcular_plan(base, entidad) is not None
    assert base.scalar(select(func.count()).select_from(m.PuntajeSector)) > 0
    generar(base, semilla=22, tipo="vendaval")  # reinicia por defecto: no debe chocar con las claves foráneas
    assert base.scalar(select(func.count()).select_from(m.PlanAsignacion)) == 0
    assert base.scalar(select(func.count()).select_from(m.PuntajeSector)) == 0


def _admin_real(db, telefono="3001112233"):
    admin = m.Usuario(nombre="Admin Real", telefono=telefono, rol="administrador", ficticio=False,
                      password_hash="hash-de-prueba")
    db.add(admin)
    db.flush()
    db.add(m.Bitacora(usuario_id=admin.id, accion="crear_usuario", objeto="usuario:99"))
    db.commit()
    return admin


def test_regenerar_conserva_la_cuenta_del_administrador_real(base):
    generar(base, semilla=31, tipo="inundacion")
    admin = _admin_real(base)
    viejos = {u.id for u in base.scalars(select(m.Usuario).where(m.Usuario.ficticio.is_(True)))}
    generar(base, semilla=32, tipo="vendaval", conservar_cuentas=True)
    assert base.get(m.Usuario, admin.id) is not None and base.get(m.Usuario, admin.id).password_hash == "hash-de-prueba"
    nuevos = {u.id for u in base.scalars(select(m.Usuario).where(m.Usuario.ficticio.is_(True)))}
    assert nuevos and not (viejos & nuevos)  # los simulados son otros
    assert base.scalar(select(func.count()).select_from(m.Evento)) == 1
    assert base.scalar(select(m.Bitacora).where(m.Bitacora.usuario_id == admin.id)) is not None  # su historial sigue
    assert base.scalar(select(func.count()).select_from(m.Municipio)) == 23  # lo real no se toca


def test_regenerar_conserva_todas_las_cuentas_reales_que_todavia_no_hicieron_nada(base):
    """Una entidad, un equipo y un centro de acopio creados por el administrador, sin datos todavía: se conservan,
    vuelven a quedar en su sector (buscado por nombre) y el centro de acopio real sigue existiendo."""
    generar(base, semilla=41, tipo="inundacion")
    sector = base.scalar(select(m.Sector).where(m.Sector.nombre == "Soledad - Sector 03"))
    admin = _admin_real(base)
    entidad = m.Usuario(nombre="Entidad Real", telefono="3002223344", rol="entidad", ficticio=False, password_hash="x")
    acopio = m.Usuario(nombre="Acopio Real", telefono="3003334455", rol="centro_acopio", ficticio=False,
                       password_hash="x", sector_id=sector.id)
    base.add_all([entidad, acopio])
    base.flush()
    centro = m.CentroAcopio(nombre="Centro de acopio de Acopio Real", sector_id=sector.id, responsable_id=acopio.id)
    base.add(centro)
    ajustado = base.scalar(select(m.Peso).where(m.Peso.ambito == "sector", m.Peso.dimension == "gravedad"))
    ajustado.valor, ajustado.actualizado_por = 0.6, entidad.id  # la entidad cambió este peso
    base.commit()
    ids = {u.id for u in (admin, entidad, acopio)}

    generar(base, semilla=42, tipo="inundacion", conservar_cuentas=True)
    base.expire_all()
    assert {u.id for u in base.scalars(select(m.Usuario).where(m.Usuario.ficticio.is_(False)))} == ids
    nuevo = base.scalar(select(m.Sector).where(m.Sector.nombre == "Soledad - Sector 03"))
    assert base.get(m.Usuario, acopio.id).sector_id == nuevo.id  # reubicado por nombre
    assert base.get(m.CentroAcopio, centro.id).sector_id == nuevo.id and base.get(m.CentroAcopio, centro.id).responsable_id == acopio.id
    otros = base.scalars(select(m.CentroAcopio).where(m.CentroAcopio.id != centro.id)).all()
    assert otros and all(c.responsable_id != acopio.id for c in otros)  # los demás son los simulados nuevos
    peso = base.scalar(select(m.Peso).where(m.Peso.ambito == "sector", m.Peso.dimension == "gravedad"))
    assert peso.valor == 0.6 and peso.actualizado_por == entidad.id  # el ajuste de la entidad no se pierde
    assert base.scalar(select(func.count()).select_from(m.Peso).where(m.Peso.ambito == "sector",
                                                                       m.Peso.dimension == "gravedad")) == 1


def test_regenerar_se_niega_si_las_cuentas_reales_ya_tienen_datos_y_no_borra_nada(base):
    generar(base, semilla=33, tipo="inundacion")
    _admin_real(base)
    sector = base.scalar(select(m.Sector))
    persona = m.Usuario(nombre="Persona Real", telefono="3009998877", rol="solicitante", ficticio=False,
                        sector_id=sector.id)
    base.add(persona)
    base.flush()
    base.add(m.Solicitud(solicitante_id=persona.id, creador_id=persona.id, sector_id=sector.id, necesidad="agua",
                         cantidad=6))
    base.commit()
    eventos = base.scalar(select(func.count()).select_from(m.Evento))
    sectores = base.scalar(select(func.count()).select_from(m.Sector))
    with pytest.raises(RuntimeError, match="ya tienen datos.*solicitudes"):
        generar(base, semilla=34, tipo="vendaval", conservar_cuentas=True)
    base.rollback()
    assert base.scalar(select(func.count()).select_from(m.Evento)) == eventos
    assert base.scalar(select(func.count()).select_from(m.Sector)) == sectores
    assert base.get(m.Usuario, persona.id) is not None


def test_sin_la_opcion_un_administrador_real_tambien_bloquea(base):
    generar(base, semilla=35, tipo="inundacion")
    _admin_real(base)
    with pytest.raises(RuntimeError, match="cuentas reales"):
        generar(base, semilla=36, tipo="inundacion")  # el permiso para conservar administradores es explícito


def test_si_regenerar_falla_a_la_mitad_no_se_pierde_lo_anterior(base):
    """Todo ocurre en una sola transacción: si algo falla, al deshacerla queda el escenario anterior."""
    generar(base, semilla=37, tipo="inundacion")
    _admin_real(base)
    antes = base.scalar(select(func.count()).select_from(m.Solicitud))
    with pytest.raises(KeyError):
        generar(base, semilla=38, tipo="inundacion", municipios=["99999"], conservar_cuentas=True)
    base.rollback()
    assert base.scalar(select(func.count()).select_from(m.Solicitud)) == antes > 0
