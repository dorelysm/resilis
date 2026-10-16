"""Calcula con los datos de la base la confianza y la prioridad de cada sector y de cada solicitud (bloque 5).

Para cada reporte y solicitud: confianza c (fuente, verificación, vigencia y corroboración).
Para cada sector: confianza C, dispersión D, las cinco dimensiones, la prioridad P (TOPSIS) y las alertas
de información faltante. Para cada solicitud pendiente: prioridad P con sus cinco criterios.

La hora de referencia es la actual, salvo en un evento simulado: ahí es la del último reporte recibido, para que
un escenario de demostración no "envejezca" mientras se muestra. La vigencia de un reporte se mide desde que se
recibió (no desde la hora del evento): un reporte hecho hace una hora sobre algo ocurrido ayer es información fresca.
"""
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app import motor
from app.models import ahora

ALERTAS = {
    "sin_reportes": "No tiene reportes",
    "desactualizado": "Su último reporte es muy antiguo",
    "baja_confianza": "La información es poco confiable",
    "contradictorio": "Los reportes se contradicen",
}
PESO_VULNERABILIDAD = {"discapacidad": 0.8, "adulto_mayor": 0.7, "menor": 0.7, "embarazo": 0.8, "cronica": 0.8,
                       "otra": 0.5}
ESTADOS_PENDIENTES = (m.EstadoSolicitud.REGISTRADA, m.EstadoSolicitud.VERIFICADA)
ESTADOS_ABIERTOS = ESTADOS_PENDIENTES + (m.EstadoSolicitud.ASIGNADA, m.EstadoSolicitud.EN_CAMINO)
HORAS_ESPERA_MAXIMA = 48.0  # a partir de aquí, esperar más ya no sube la urgencia del sector


# ----------------------------------------------------------------------------- pesos
def pesos_por_defecto() -> dict[str, dict[str, float]]:
    from app.simulacion import PESOS_INICIALES

    return {ambito: dict(dims) for ambito, dims in PESOS_INICIALES.items()}


def leer_pesos(db: Session) -> dict[str, dict[str, float]]:
    """Pesos vigentes (los de la base; los que falten usan los iniciales), siempre con suma 1 por ámbito."""
    pesos = pesos_por_defecto()
    for fila in db.scalars(select(m.Peso)):
        if fila.ambito in pesos:
            pesos[fila.ambito][fila.dimension] = fila.valor
    pesos["sector"] = motor.normalizar_pesos(pesos["sector"], motor.CRITERIOS_SECTOR)
    pesos["solicitud"] = motor.normalizar_pesos(pesos["solicitud"], motor.CRITERIOS_SOLICITUD)
    return pesos


def guardar_pesos(db: Session, ambito: str, valores: dict[str, float], usuario: m.Usuario | None) -> dict[str, float]:
    criterios = motor.CRITERIOS_SECTOR if ambito == "sector" else motor.CRITERIOS_SOLICITUD
    normalizados = motor.normalizar_pesos(valores, criterios)
    existentes = {p.dimension: p for p in db.scalars(select(m.Peso).where(m.Peso.ambito == ambito))}
    for dim, valor in normalizados.items():
        fila = existentes.get(dim) or m.Peso(ambito=ambito, dimension=dim, valor=valor)
        fila.valor, fila.actualizado_por, fila.actualizado_en = valor, usuario.id if usuario else None, ahora()
        db.add(fila)
    db.add(m.Bitacora(usuario_id=usuario.id if usuario else None, accion="cambiar_pesos", objeto=ambito,
                      detalle={k: round(v, 4) for k, v in normalizados.items()}))
    db.flush()
    return normalizados


# ----------------------------------------------------------------------------- utilidades
def _utc(hora: datetime | None) -> datetime | None:
    if hora is None:
        return None
    return hora.replace(tzinfo=timezone.utc) if hora.tzinfo is None else hora.astimezone(timezone.utc)


def _horas(desde: datetime | None, hasta: datetime) -> float:
    d = _utc(desde)
    return max(0.0, (hasta - d).total_seconds() / 3600.0) if d else 0.0


def referencia(db: Session, evento: m.Evento | None) -> datetime:
    if evento is not None and evento.origen == m.OrigenDato.SIMULADO:
        ultimo = db.scalar(select(m.ReporteDanos.hora_captura).where(m.ReporteDanos.evento_id == evento.id)
                           .order_by(m.ReporteDanos.hora_captura.desc()).limit(1))
        return max(_utc(ultimo), _utc(evento.fecha)) if ultimo is not None else _utc(evento.fecha)
    return ahora()


def _fuente(rol: str | None, fuente: str, es_organizacion: bool = False) -> float:
    if fuente == m.FuenteReporte.ESTADO:
        return motor.FUENTE["estado"]
    if rol == m.Rol.EQUIPO_ENTREGA and es_organizacion:
        return motor.FUENTE["organizacion"]
    return motor.FUENTE.get(rol or "solicitante", motor.FUENTE["solicitante"])


# ----------------------------------------------------------------------------- cálculo
def recalcular(db: Session, evento: m.Evento | None = None) -> dict:
    """Recalcula todo para el evento más reciente. Devuelve un resumen. Hace commit."""
    evento = evento or db.scalar(select(m.Evento).order_by(m.Evento.fecha.desc(), m.Evento.id.desc()).limit(1))
    sectores = list(db.scalars(select(m.Sector).order_by(m.Sector.id)))
    if not sectores:
        return {"sectores": 0, "solicitudes": 0}
    pesos = leer_pesos(db)
    ahora_ = referencia(db, evento)
    usuarios = {u.id: u for u in db.scalars(select(m.Usuario))}

    verif: dict[tuple[str, int], str] = {}
    for v in db.scalars(select(m.Verificacion).order_by(m.Verificacion.id)):
        verif[(v.objeto_tipo, v.objeto_id)] = v.resultado  # vale la última revisión
    hora_verif: dict[int, datetime] = {}
    for v in db.scalars(select(m.Verificacion).where(m.Verificacion.objeto_tipo == "solicitud")):
        hora_verif[v.objeto_id] = v.hora

    # ---- reportes: confianza de cada uno
    reportes = list(db.scalars(select(m.ReporteDanos).where(m.ReporteDanos.estado == "activo")
                               .where(m.ReporteDanos.evento_id == evento.id if evento else True)))
    por_sector: dict[int, list[m.ReporteDanos]] = defaultdict(list)
    for r in reportes:
        por_sector[r.sector_id].append(r)
    for rs in por_sector.values():
        for r in rs:
            autor = usuarios.get(r.autor_id)
            coinciden = len({o.autor_id for o in rs if o is not r and o.autor_id != r.autor_id
                             and abs(o.nivel_dano - r.nivel_dano) <= 1})
            estado_v = {"verificado": "verificado", "desmentido": "desmentido"}.get(verif.get(("reporte", r.id)),
                                                                                   "sin_verificar")
            r.confianza = motor.confianza_dato(
                _fuente(autor.rol if autor else None, r.fuente, bool(autor and autor.es_organizacion)),
                estado_v, _horas(r.hora_captura, ahora_), coinciden)  # vigencia: cuánto hace que se recibió el dato

    # ---- solicitudes de cada sector
    solicitudes = list(db.scalars(select(m.Solicitud).where(m.Solicitud.estado.in_(ESTADOS_ABIERTOS))))
    sol_por_sector: dict[int, list[m.Solicitud]] = defaultdict(list)
    for s in solicitudes:
        sol_por_sector[s.sector_id].append(s)
    vulnerables = {v.solicitud_id: v for v in db.scalars(select(m.Vulnerabilidad))}

    # ---- inventario disponible por sector (centros de acopio ubicados en él)
    inventario: dict[int, int] = defaultdict(int)
    centros = {c.id: c for c in db.scalars(select(m.CentroAcopio))}
    for lote in db.scalars(select(m.Lote).where(m.Lote.cantidad_disponible > 0)):
        centro = centros.get(lote.centro_id)
        if centro and centro.sector_id:
            inventario[centro.sector_id] += lote.cantidad_disponible

    # ---- indicadores de cada sector (0 a 1)
    filas, datos = [], []
    for s in sectores:
        rs = [r for r in por_sector.get(s.id, []) if r.confianza and r.confianza > 0]  # los desmentidos no cuentan
        confs = [r.confianza for r in rs]
        niveles = [r.nivel_dano for r in rs]
        disp = motor.dispersion(niveles)
        c_sector = motor.confianza_sector(confs, disp)
        sols = sol_por_sector.get(s.id, [])
        base_previa = not rs

        if rs:
            w = np.array(confs)
            dano = float(np.average([n / 3.0 for n in niveles], weights=w))
            afectadas = float(np.average([r.personas_afectadas for r in rs], weights=w))
            acceso = float(np.average([r.acceso for r in rs], weights=w))
            gravedad = 0.7 * dano + 0.3 * min(1.0, afectadas / max(1, s.personas))
        else:  # hora cero: sin reportes se parte de la línea base, y con poco peso
            gravedad = 0.5 * (0.5 * s.amenaza_base + 0.5 * s.vulnerabilidad_base)
            afectadas, acceso = 0.0, s.acceso_base
        vuln_sol = sum(1 for x in sols if x.id in vulnerables)
        max_urg = max((x.urgencia / 3.0 for x in sols), default=0.0)
        espera = max((_horas(x.creado_en, ahora_) for x in sols), default=0.0)
        urgencia = 0.8 * max(max_urg, 0.5 * gravedad) + 0.2 * min(1.0, espera / HORAS_ESPERA_MAXIMA)
        demanda = sum(x.cantidad for x in sols)
        brecha = 0.0 if demanda == 0 else 1.0 - min(1.0, inventario.get(s.id, 0) / demanda)
        expuestas = afectadas + 3.0 * vuln_sol + sum(x.personas_hogar for x in sols) * 0.5
        # La accesibilidad NO penaliza: un sector aislado sube un poco (riesgo de olvido), nunca baja.
        filas.append([gravedad, urgencia, expuestas, 1.0 - acceso, brecha])
        horas_ult = min((_horas(r.hora_captura, ahora_) for r in rs), default=None)  # antigüedad del último reporte
        alertas = []
        if not rs:  # sin reportes, o todos desmentidos
            alertas.append("sin_reportes")
        else:
            if horas_ult > 2 * motor.TAU_HORAS:
                alertas.append("desactualizado")
            if c_sector < motor.UMBRAL_CONFIANZA:
                alertas.append("baja_confianza")
            if disp > motor.UMBRAL_DISPERSION:
                alertas.append("contradictorio")
        datos.append((s, c_sector, disp, len(rs), len(sols), horas_ult, base_previa, alertas))

    resultado = motor.topsis(filas, motor.CRITERIOS_SECTOR, pesos["sector"])
    orden = sorted(range(len(sectores)), key=lambda i: (-resultado.prioridad[i], sectores[i].id))
    posicion = {sectores[i].id: n + 1 for n, i in enumerate(orden)}
    prioridad_sector = {sectores[i].id: resultado.prioridad[i] for i in range(len(sectores))}

    existentes = {p.sector_id: p for p in db.scalars(select(m.PuntajeSector))}
    for i, (s, c_s, disp, n_rep, n_sol, horas_ult, base_previa, alertas) in enumerate(datos):
        p = existentes.get(s.id) or m.PuntajeSector(sector_id=s.id)
        p.evento_id = evento.id if evento else None
        p.prioridad, p.posicion = round(resultado.prioridad[i], 6), posicion[s.id]
        p.confianza, p.dispersion = round(c_s, 6), round(disp, 6)
        p.n_reportes, p.n_solicitudes, p.horas_ultimo_reporte, p.base_previa = n_rep, n_sol, horas_ult, base_previa
        p.indicadores = {c: round(float(filas[i][j]), 4) for j, c in enumerate(motor.CRITERIOS_SECTOR)}
        p.aportes = {c: round(v, 4) for c, v in resultado.aportes[i].items()}
        p.alertas = alertas
        p.calculado_en = ahora()
        db.add(p)

    # ---- prioridad y confianza de cada solicitud pendiente
    pendientes = [s for s in solicitudes if s.estado in ESTADOS_PENDIENTES]
    for sol in pendientes:
        creador = usuarios.get(sol.creador_id)
        v_sol = {"verificado": "verificado", "desmentido": "desmentido"}.get(verif.get(("solicitud", sol.id)),
                                                                           "sin_verificar")
        ultima = hora_verif.get(sol.id) or sol.creado_en
        coinciden = sum(1 for r in por_sector.get(sol.sector_id, []) if r.nivel_dano >= 1)
        sol.confianza = round(motor.confianza_dato(
            _fuente(creador.rol if creador else None, sol.fuente, bool(creador and creador.es_organizacion)),
            v_sol, _horas(ultima, ahora_), min(coinciden, 10)), 6)
    filas_s = []
    for sol in pendientes:
        v = vulnerables.get(sol.id)
        filas_s.append([sol.urgencia / 3.0, PESO_VULNERABILIDAD.get(v.tipo, 0.5) if v else 0.0, float(sol.personas_hogar),
                        _horas(sol.creado_en, ahora_), prioridad_sector.get(sol.sector_id, 0.0)])
    res_s = motor.topsis(filas_s, motor.CRITERIOS_SOLICITUD, pesos["solicitud"])
    for sol, p in zip(pendientes, res_s.prioridad):
        sol.prioridad = round(p, 6)
    db.commit()
    return {"sectores": len(sectores), "solicitudes": len(pendientes), "evento_id": evento.id if evento else None,
            "referencia": ahora_.isoformat()}
