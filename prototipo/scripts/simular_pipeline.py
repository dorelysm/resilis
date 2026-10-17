"""Simula de punta a punta el ciclo de la respuesta sobre un escenario generado, en una base temporal (SQLite en
memoria): verificación en campo, recepción de donaciones, prioridad, plan optimizado, aprobación, entrega con código
de un solo uso, incidencias y revisión de la cadena de auditoría. No toca ninguna base real.

Uso:  uv run python scripts/simular_pipeline.py --seed 42 --tipo inundacion
"""
import argparse
import sys
import time
from pathlib import Path

import numpy as np
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import models as m  # noqa: E402
from app import plan as pl  # noqa: E402
from app import servicios as sv  # noqa: E402
from app.cargas import cargar_viviendas  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import Base  # noqa: E402
from app.simulacion import generar  # noqa: E402


def main(semilla: int, tipo: str) -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    rng = np.random.default_rng(semilla + 1000)
    secreto = get_settings().secret_key
    t = {}

    def paso(nombre, inicio):
        t[nombre] = round(time.perf_counter() - inicio, 2)

    inicio = time.perf_counter()
    cargar_viviendas(db)
    esc = generar(db, semilla=semilla, tipo=tipo)
    paso("generar escenario", inicio)
    verdad = db.scalar(select(m.Bitacora.detalle).where(m.Bitacora.accion == "simulacion_verdad"))
    falsas = set(verdad["solicitudes_falsas"])
    brigadista = db.scalars(select(m.Usuario).where(m.Usuario.rol == m.Rol.BRIGADISTA)).first()
    entidad = db.scalars(select(m.Usuario).where(m.Usuario.rol == m.Rol.ENTIDAD)).first()

    # 1. Verificación en campo: un brigadista revisa las solicitudes registradas. Detecta el 85 % de las falsas.
    inicio = time.perf_counter()
    registradas = db.scalars(select(m.Solicitud).where(m.Solicitud.estado == m.EstadoSolicitud.REGISTRADA)
                             .order_by(m.Solicitud.prioridad.desc().nullslast(), m.Solicitud.id)).all()
    ya_verificadas = db.scalar(select(func.count()).select_from(m.Solicitud)
                               .where(m.Solicitud.estado == m.EstadoSolicitud.VERIFICADA))
    desmentidas = falsas_coladas = 0
    for sol in registradas[: int(len(registradas) * 0.7)]:  # alcanza a revisar el 70 %
        if sol.id in falsas and rng.random() < 0.85:
            sv.verificar_solicitud(db, sol, brigadista, "desmentido", "No se encontró a nadie en esa dirección.")
            desmentidas += 1
        else:
            sv.verificar_solicitud(db, sol, brigadista, "verificado", "Verificada en campo.")
            falsas_coladas += sol.id in falsas
    paso("verificación", inicio)

    # 2. Los centros reciben las donaciones que seguían solo ofrecidas.
    inicio = time.perf_counter()
    recibidas = 0
    for don in db.scalars(select(m.Donacion).where(m.Donacion.estado == m.EstadoDonacion.OFRECIDA,
                                                   m.Donacion.monetaria.is_(False))).all():
        centro = db.get(m.CentroAcopio, don.centro_id)
        if centro is None:
            continue
        sv.recibir_donacion(db, don, centro, db.get(m.Usuario, centro.responsable_id), don.cantidad,
                            don.estado_producto, don.vencimiento)
        recibidas += 1
    paso("recepción", inicio)

    # 3. Plan optimizado.
    inicio = time.perf_counter()
    plan = pl.calcular_plan(db, entidad)
    paso("plan", inicio)
    if plan is None:
        print("No hay solicitudes verificadas o inventario: no hay plan.")
        return
    datos = db.get(m.PlanResumen, plan.id).datos
    total_inv = db.scalar(select(func.sum(m.Lote.cantidad_disponible)))

    # 4. Aprobación y reserva.
    inicio = time.perf_counter()
    equipos = [u.id for u in db.scalars(select(m.Usuario).where(
        m.Usuario.rol == m.Rol.EQUIPO_ENTREGA, m.Usuario.aprobado.is_(True)).order_by(m.Usuario.id))]
    sol_ids = list(dict.fromkeys(l.solicitud_id for l in db.scalars(select(m.PlanLinea).where(m.PlanLinea.plan_id == plan.id))))
    reparto = {sid: equipos[i % len(equipos)] for i, sid in enumerate(sol_ids)}  # la entidad reparte entre los equipos
    resultado = pl.aprobar_plan(db, plan, entidad, secreto, equipos=reparto)
    paso("aprobación", inicio)
    entregas = db.scalars(select(m.Entrega)).all()

    # 5. Entrega con código de un solo uso. El 12 % tiene incidencia (no se encontró a la persona).
    inicio = time.perf_counter()
    entregadas = incidencias = rechazos = reusos_bloqueados = 0
    for e in entregas:
        equipo = db.get(m.Usuario, e.equipo_id)
        sv.en_camino(db, e, equipo)
        if rng.random() < 0.12:
            sv.registrar_incidencia(db, e, equipo, "no_encontrada", "Nadie respondió en la dirección.")
            incidencias += 1
            continue
        try:  # un código equivocado no debe entregar
            sv.confirmar_entrega(db, e, equipo, "ZZZZ-ZZZZ")
        except sv.ErrorNegocio:
            rechazos += 1
        codigo = sv.codigo_para(secreto, e.id, e.codigo_sal)
        sv.confirmar_entrega(db, e, equipo, codigo)
        entregadas += 1
        db.refresh(e)
        try:  # el código ya usado no debe servir para otra entrega distinta ni invalidar la anterior
            otra = next((x for x in entregas if x.id != e.id and x.estado_codigo == m.EstadoCodigo.ACTIVO
                         and x.equipo_id == e.equipo_id), None)
            if otra is not None:
                sv.confirmar_entrega(db, otra, db.get(m.Usuario, otra.equipo_id), codigo)
        except sv.ErrorNegocio:
            reusos_bloqueados += 1
    paso("entregas", inicio)

    # 6. Revisión de cadena y del inventario.
    ok_cadena, roto = sv.verificar_cadena(db)
    lotes = db.scalars(select(m.Lote)).all()
    inventario_ok = all(l.cantidad_disponible + l.cantidad_reservada + l.cantidad_entregada == l.cantidad_recibida
                        for l in lotes)
    estados = dict(db.execute(select(m.Solicitud.estado, func.count()).group_by(m.Solicitud.estado)).all())
    pr = db.execute(select(m.Solicitud.estado, func.avg(m.Solicitud.prioridad)).group_by(m.Solicitud.estado)).all()

    print(f"Escenario: {esc['barrios']} barrios, {esc['solicitudes']} solicitudes, {esc['lotes']} lotes ({tipo}, semilla {semilla})")
    print(f"Verificación: {ya_verificadas} ya verificadas; el brigadista revisó {int(len(registradas) * 0.7)} de {len(registradas)} registradas "
          f"({desmentidas} falsas desmentidas, {falsas_coladas} falsas que se colaron)")
    print(f"Recepción: {recibidas} donaciones ofrecidas pasaron al inventario (disponible antes del plan: {total_inv})")
    print(f"Plan: método {plan.metodo}, cubre {datos.get('cubierta_ponderada', '?')} (voraz: {datos.get('cubierta_ponderada_voraz', '?')}); "
          f"necesidad cubierta {plan.necesidad_cubierta:.0f} de {plan.necesidad_total:.0f}")
    print(f"Aprobación: {resultado['asignadas']} solicitudes asignadas, {len(resultado['omitidas'])} omitidas"
          + (f" (ej.: {resultado['omitidas'][0]['motivo']})" if resultado['omitidas'] else ""))
    print(f"Entregas: {entregadas} confirmadas con su código, {incidencias} con incidencia, "
          f"{rechazos} códigos equivocados rechazados, {reusos_bloqueados} reusos de código bloqueados")
    print(f"Estados finales: {estados}")
    print("Prioridad media por estado: " + ", ".join(f"{e}={p:.2f}" for e, p in pr if p is not None))
    print(f"Cadena de auditoría íntegra: {ok_cadena}" + ("" if ok_cadena else f" (se rompe en {roto})"))
    print(f"Inventario consistente (disponible + reservada + entregada = recibida): {inventario_ok}")
    print("Tiempos (s): " + ", ".join(f"{k} {v}" for k, v in t.items()))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--tipo", default="inundacion", choices=["terremoto", "inundacion", "vendaval", "deslizamiento"])
    a = ap.parse_args()
    main(a.seed, a.tipo)
