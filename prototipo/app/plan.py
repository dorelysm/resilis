"""Plan de asignación con los datos de la base: lo calcula, lo explica y lo ejecuta cuando la entidad lo aprueba.

Solo lo aprobado reserva inventario y asigna equipos (RF-64). Cada línea dice por qué existe y el plan lista lo que
quedó sin cubrir (RF-63).
"""
import math
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app import optimizacion as op
from app import puntaje as pj
from app import servicios as sv
from app.formato import plural
from app.models import ahora

PARAMETROS = {"kappa": op.KAPPA, "lambda": op.LAMBDA, "theta": op.THETA}
UMBRAL_ACCESO_BLOQUEADO = 0.85  # 1 - acceso: por encima de esto, el barrio se considera aislado


# ----------------------------------------------------------------------------- parámetros
def leer_parametros(db: Session) -> dict[str, float]:
    valores = dict(PARAMETROS)
    for fila in db.scalars(select(m.Peso).where(m.Peso.ambito == "plan")):
        if fila.dimension in valores:
            valores[fila.dimension] = fila.valor
    return valores


def guardar_parametros(db: Session, valores: dict[str, float], usuario: m.Usuario) -> dict[str, float]:
    existentes = {p.dimension: p for p in db.scalars(select(m.Peso).where(m.Peso.ambito == "plan"))}
    for clave, valor in valores.items():
        if clave not in PARAMETROS:
            continue
        fila = existentes.get(clave) or m.Peso(ambito="plan", dimension=clave, valor=valor)
        fila.valor, fila.actualizado_por, fila.actualizado_en = float(valor), usuario.id, ahora()
        db.add(fila)
    db.add(m.Bitacora(usuario_id=usuario.id, accion="cambiar_parametros_plan", objeto="plan",
                      detalle={k: float(v) for k, v in valores.items() if k in PARAMETROS}))
    db.flush()
    return leer_parametros(db)


# ----------------------------------------------------------------------------- utilidades
def _utc(hora: datetime | None) -> datetime | None:
    if hora is None:
        return None
    return hora.replace(tzinfo=timezone.utc) if hora.tzinfo is None else hora.astimezone(timezone.utc)


def kilometros(a: tuple[float | None, float | None], b: tuple[float | None, float | None]) -> float:
    """Distancia en línea recta (haversine). Si falta una ubicación se asume una distancia media de 5 km."""
    if None in a or None in b:
        return 5.0
    (la1, lo1), (la2, lo2) = a, b
    p1, p2 = math.radians(la1), math.radians(la2)
    d = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lo2 - lo1) / 2) ** 2
    return 6371.0 * 2 * math.asin(math.sqrt(d))


def urgencia_de_uso(vencimiento: datetime | None, ahora_: datetime) -> float:
    """u entre 0 y 1: 1 si vence ya, 0 si no vence o le queda más de 60 días."""
    v = _utc(vencimiento)
    if v is None:
        return 0.0
    dias = (v - ahora_).total_seconds() / 86400
    return float(max(0.0, min(1.0, 1.0 - dias / 60.0)))


def _texto_vencimiento(venc: datetime | None, ahora_: datetime) -> str:
    v = _utc(venc)
    if v is None:
        return "no vence"
    dias = (v - ahora_).total_seconds() / 86400
    return f"vence en {plural(round(dias), 'día', 'días')}" if dias >= 1 else "vence en menos de un día"


# ----------------------------------------------------------------------------- cálculo
def calcular_plan(db: Session, usuario: m.Usuario) -> m.PlanAsignacion | None:
    """Calcula un plan nuevo con el inventario y las solicitudes verificadas de ahora. Devuelve None si no hay
    solicitudes verificadas ni inventario. Un plan propuesto anterior queda reemplazado."""
    pj.recalcular(db)  # el plan usa prioridades y confianzas al día
    parametros = leer_parametros(db)
    ahora_ = ahora()

    solicitudes = db.scalars(select(m.Solicitud).where(m.Solicitud.estado == m.EstadoSolicitud.VERIFICADA)
                             .order_by(m.Solicitud.id)).all()
    lotes_db = []
    for lote in db.scalars(select(m.Lote).where(m.Lote.cantidad_disponible > 0).order_by(m.Lote.id)):
        v = _utc(lote.vencimiento)
        if v is None or v > ahora_:  # un producto vencido no se entrega
            lotes_db.append(lote)
    if not solicitudes or not lotes_db:
        return None

    centros = {c.id: c for c in db.scalars(select(m.CentroAcopio))}
    barrios = {s.id: s for s in db.scalars(select(m.Barrio))}

    def ubicacion_lote(lote):
        c = centros.get(lote.centro_id)
        s = barrios.get(c.barrio_id) if c and c.barrio_id else None
        return (c.lat, c.lon) if c and c.lat is not None else ((s.lat, s.lon) if s else (None, None))

    def ubicacion_sol(sol):
        s = barrios.get(sol.barrio_id)
        return (sol.lat, sol.lon) if sol.lat is not None else ((s.lat, s.lon) if s else (None, None))

    lotes = [op.Lote(l.id, l.tipo_bien, l.cantidad_disponible, urgencia_de_uso(l.vencimiento, ahora_)) for l in lotes_db]
    sols = [op.Solicitud(s.id, s.necesidad, s.cantidad,
                         max(0.01, (s.prioridad or 0.0) * (0.5 + 0.5 * (s.confianza or 0.0)))) for s in solicitudes]
    por_lote = {l.id: l for l in lotes_db}
    por_sol = {s.id: s for s in solicitudes}
    compat = {}
    for lote in lotes_db:
        for sol in solicitudes:
            if lote.tipo_bien == sol.necesidad and sv._lote_admite(lote, sol):
                compat[(lote.id, sol.id)] = kilometros(ubicacion_lote(lote), ubicacion_sol(sol))

    plan_op, referencia = op.resolver(lotes, sols, compat, parametros["kappa"], parametros["lambda"],
                                      parametros["theta"])
    x = plan_op.x

    # ---- qué equipo hace cada entrega: se reparte la carga entre los equipos que pueden entrar
    equipos = db.scalars(select(m.Usuario).where(m.Usuario.rol == m.Rol.EQUIPO_ENTREGA, m.Usuario.aprobado.is_(True),
                                                 m.Usuario.password_hash.is_not(None)).order_by(m.Usuario.id)).all()
    carga = {e.id: 0 for e in equipos}
    equipo_de: dict[int, int | None] = {}
    solicitudes_con_linea = sorted({j for (_, j) in x}, key=lambda j: -next(s.peso for s in sols if s.id == j))
    for j in solicitudes_con_linea:
        if carga:
            elegido = min(carga, key=lambda e: (carga[e], e))
            carga[elegido] += 1
            equipo_de[j] = elegido
        else:
            equipo_de[j] = None

    # ---- guardar el plan
    for anterior in db.scalars(select(m.PlanAsignacion).where(m.PlanAsignacion.estado == m.EstadoPlan.PROPUESTO)):
        anterior.estado = m.EstadoPlan.RECHAZADO
        res = db.get(m.PlanResumen, anterior.id)
        if res:
            res.datos = {**res.datos, "motivo_rechazo": "Reemplazado por un plan más nuevo"}
    evento = db.scalar(select(m.Evento).order_by(m.Evento.fecha.desc(), m.Evento.id.desc()).limit(1))
    plan = m.PlanAsignacion(evento_id=evento.id if evento else None, estado=m.EstadoPlan.PROPUESTO,
                            metodo=plan_op.metodo, necesidad_total=float(sum(s.cantidad for s in solicitudes)),
                            necesidad_cubierta=float(op.cantidad_cubierta(x)), aprobado_por=None, creado_en=ahora_)
    db.add(plan)
    db.flush()
    for (lote_id, sol_id), cantidad in sorted(x.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        sol, lote = por_sol[sol_id], por_lote[lote_id]
        centro = centros.get(lote.centro_id)
        razon = (f"Prioridad {round((sol.prioridad or 0) * 100)} %, confianza {round((sol.confianza or 0) * 100)} %. "
                 f"Lote {lote.id}: {_texto_vencimiento(lote.vencimiento, ahora_)}"
                 f"{', ' + centro.nombre if centro else ''}, a {compat[(lote_id, sol_id)]:.1f} km. "
                 f"Cubre {cantidad} de {sol.cantidad}.")
        db.add(m.PlanLinea(plan_id=plan.id, solicitud_id=sol_id, lote_id=lote_id, cantidad=cantidad,
                           equipo_id=equipo_de.get(sol_id), razon=razon))

    # ---- lo que quedó sin cubrir, y por qué
    cubierto = defaultdict(int)
    for (_, j), q in x.items():
        cubierto[j] += q
    sin_cubrir = []
    for s in solicitudes:
        falta = s.cantidad - cubierto.get(s.id, 0)
        if falta <= 0:
            continue
        hay_compatible = any(j == s.id for (_, j) in compat)
        if not hay_compatible:
            motivo = "No hay inventario compatible (de ese tipo, sin vencer y sin estar dirigido a otro destino)."
        elif cubierto.get(s.id, 0) == 0:
            motivo = "El inventario compatible se asignó a solicitudes que rinden más: mayor prioridad por unidad pedida."
        else:
            motivo = "Se cubrió una parte: el inventario compatible se agotó."
        sin_cubrir.append({"solicitud_id": s.id, "tipo": s.necesidad, "falta": falta, "motivo": motivo})
    por_tipo = {}
    for tipo in sorted({s.necesidad for s in solicitudes} | {l.tipo_bien for l in lotes_db}):
        por_tipo[tipo] = {"demanda": sum(s.cantidad for s in solicitudes if s.necesidad == tipo),
                          "disponible": sum(l.cantidad_disponible for l in lotes_db if l.tipo_bien == tipo),
                          "asignado": sum(q for (i, _), q in x.items() if por_lote[i].tipo_bien == tipo)}
    indicadores = {p.barrio_id: p.indicadores for p in db.scalars(select(m.PuntajeBarrio))}
    aislados = [s.id for s in solicitudes if s.id in cubierto and
                (indicadores.get(s.barrio_id) or {}).get("accesibilidad", 0.0) >= UMBRAL_ACCESO_BLOQUEADO]

    db.add(m.PlanResumen(plan_id=plan.id, datos={
        "parametros": parametros, "solicitudes": len(solicitudes), "lotes": len(lotes_db),
        "metodo_usado": plan_op.metodo, "estado_solucionador": plan_op.estado, "segundos": round(plan_op.segundos, 3),
        "equidad_aplicada": plan_op.equidad_aplicada, "notas": plan_op.notas,
        "cubierta_ponderada": round(op.cubierta_ponderada(x, sols), 4),
        "cubierta_ponderada_voraz": round(op.cubierta_ponderada(referencia.x, sols), 4),
        "unidades": op.cantidad_cubierta(x), "unidades_voraz": op.cantidad_cubierta(referencia.x),
        "sin_cubrir": sin_cubrir, "por_tipo": por_tipo, "acceso_bloqueado": aislados,
        "sin_equipos": not equipos, "creado_por": usuario.id,
    }))
    db.add(m.Bitacora(usuario_id=usuario.id, accion="calcular_plan", objeto=f"plan:{plan.id}",
                      detalle={"unidades": op.cantidad_cubierta(x), "metodo": plan_op.metodo}))
    db.commit()
    return plan


# ----------------------------------------------------------------------------- paquetes
TAMANO_PAQUETE = 6  # entregas por paquete: lo que una persona puede revisar de una vez


def _lineas_por_solicitud(db: Session, plan: m.PlanAsignacion) -> dict[int, list[m.PlanLinea]]:
    lineas: dict[int, list[m.PlanLinea]] = defaultdict(list)
    for linea in db.scalars(select(m.PlanLinea).where(m.PlanLinea.plan_id == plan.id).order_by(m.PlanLinea.id)):
        lineas[linea.solicitud_id].append(linea)
    return lineas


def resueltas(db: Session, plan: m.PlanAsignacion) -> set[int]:
    """Solicitudes del plan que ya se aprobaron, se omitieron o se dejaron fuera."""
    res = db.get(m.PlanResumen, plan.id)
    return set((res.datos if res else {}).get("resueltas", []))


def armar_paquetes(db: Session, plan: m.PlanAsignacion, tamano: int = TAMANO_PAQUETE) -> list[dict]:
    """Divide el plan en paquetes pequeños para revisarlos y aprobarlos de uno en uno. Cada paquete reúne solicitudes
    de un mismo municipio (un equipo puede recorrerlas juntas), de la más prioritaria a la menos, y los paquetes salen
    en orden: primero el del municipio que tiene la solicitud más prioritaria. El resultado solo depende del plan."""
    lineas = _lineas_por_solicitud(db, plan)
    hechas = resueltas(db, plan)
    barrios = {b.id: b for b in db.scalars(select(m.Barrio))}
    municipios = {mu.codigo: mu.nombre for mu in db.scalars(select(m.Municipio))}
    por_municipio: dict[str, list[m.Solicitud]] = defaultdict(list)
    for sol_id in lineas:
        sol = db.get(m.Solicitud, sol_id)
        barrio = barrios.get(sol.barrio_id)
        por_municipio[barrio.municipio_codigo if barrio else ""].append(sol)
    for sols in por_municipio.values():
        sols.sort(key=lambda x: (-(x.prioridad or 0.0), x.id))
    orden = sorted(por_municipio, key=lambda c: (-(por_municipio[c][0].prioridad or 0.0), c))
    paquetes = []
    for codigo in orden:
        sols = por_municipio[codigo]
        for i in range(0, len(sols), tamano):
            grupo = sols[i:i + tamano]
            ids = [x.id for x in grupo]
            paquetes.append({
                "municipio_codigo": codigo, "municipio": municipios.get(codigo, "Sin municipio"),
                "solicitudes": ids, "personas": sum(x.personas_hogar for x in grupo),
                "prioridad": max((x.prioridad or 0.0) for x in grupo),
                "resuelto": all(j in hechas for j in ids),
            })
    paquetes.sort(key=lambda p: (-p["prioridad"], p["municipio_codigo"], p["solicitudes"][0]))
    for n, p in enumerate(paquetes, start=1):
        p["numero"] = n
    return paquetes


def equipo_sugerido(db: Session) -> int | None:
    """El equipo de entrega aprobado con menos entregas abiertas."""
    abiertas = dict(db.execute(select(m.Entrega.equipo_id, func.count()).where(m.Entrega.estado.in_(["asignada", "en_camino"]))
                               .group_by(m.Entrega.equipo_id)).all())
    equipos = [u.id for u in db.scalars(select(m.Usuario).where(
        m.Usuario.rol == m.Rol.EQUIPO_ENTREGA, m.Usuario.aprobado.is_(True), m.Usuario.password_hash.is_not(None))
        .order_by(m.Usuario.id))]
    return min(equipos, key=lambda e: (abiertas.get(e, 0), e)) if equipos else None


# ----------------------------------------------------------------------------- aprobar y rechazar
def _ejecutar(db: Session, plan: m.PlanAsignacion, usuario: m.Usuario, secreto: str, solicitudes: list[int],
              equipos: dict[int, int], excluir: set[int]) -> dict:
    """Aprueba las solicitudes indicadas: reserva sus lotes y las asigna a un equipo, con su código. Lo que ya no se
    pueda hacer (porque el inventario cambió desde que se calculó) se omite y se informa. Anota lo resuelto en el
    resumen del plan y, cuando no queda nada pendiente, cierra el plan como aprobado."""
    lineas = _lineas_por_solicitud(db, plan)
    hechas = resueltas(db, plan)
    asignadas, omitidas, excluidas = [], [], []
    for sol_id in solicitudes:
        if sol_id not in lineas or sol_id in hechas:
            continue
        if sol_id in excluir:
            excluidas.append(sol_id)
            continue
        ls = lineas[sol_id]
        sol = db.get(m.Solicitud, sol_id)
        equipo = db.get(m.Usuario, equipos.get(sol_id) or ls[0].equipo_id or 0)
        try:
            if equipo is None:
                raise sv.ErrorNegocio("No se eligió un equipo de entrega.")
            sv.asignar_con_reservas(db, sol, equipo, usuario, secreto, [(l.lote_id, l.cantidad) for l in ls], plan.id)
            asignadas.append(sol_id)
        except sv.ErrorNegocio as e:
            omitidas.append({"solicitud_id": sol_id, "motivo": str(e)})
    res = db.get(m.PlanResumen, plan.id)
    nuevas = set(asignadas) | set(excluidas) | {o["solicitud_id"] for o in omitidas}
    todas_hechas = hechas | nuevas
    if res:
        previo = res.datos.get("resultado") or {"asignadas": [], "omitidas": [], "excluidas": []}
        res.datos = {**res.datos, "resueltas": sorted(todas_hechas),
                     "resultado": {"asignadas": previo["asignadas"] + asignadas, "omitidas": previo["omitidas"] + omitidas,
                                   "excluidas": previo["excluidas"] + excluidas}}
    if set(lineas) <= todas_hechas:
        plan.estado = m.EstadoPlan.APROBADO
        plan.aprobado_por, plan.aprobado_en = usuario.id, ahora()
    db.add(m.Bitacora(usuario_id=usuario.id, accion="aprobar_plan", objeto=f"plan:{plan.id}",
                      detalle={"asignadas": len(asignadas), "omitidas": len(omitidas), "excluidas": len(excluidas)}))
    db.commit()
    return {"asignadas": len(asignadas), "omitidas": omitidas, "excluidas": len(excluidas)}


def aprobar_plan(db: Session, plan: m.PlanAsignacion, usuario: m.Usuario, secreto: str,
                 equipos: dict[int, int] | None = None, excluir: set[int] | None = None) -> dict:
    """Aprueba todo el plan de una vez."""
    if plan.estado != m.EstadoPlan.PROPUESTO:
        raise sv.ErrorNegocio("Este plan ya fue resuelto.")
    return _ejecutar(db, plan, usuario, secreto, list(_lineas_por_solicitud(db, plan)), equipos or {}, excluir or set())


def aprobar_paquete(db: Session, plan: m.PlanAsignacion, usuario: m.Usuario, secreto: str, solicitudes: list[int],
                    equipo_id: int, excluir: set[int] | None = None) -> dict:
    """Aprueba un paquete: todas sus solicitudes salen con el mismo equipo, salvo las que se dejen fuera."""
    if plan.estado != m.EstadoPlan.PROPUESTO:
        raise sv.ErrorNegocio("Este plan ya fue resuelto.")
    paquete = next((p for p in armar_paquetes(db, plan) if p["solicitudes"] == solicitudes), None)
    if paquete is None:
        raise sv.ErrorNegocio("Ese paquete no existe en este plan. Vuelva a abrir la página del plan.")
    if paquete["resuelto"]:
        raise sv.ErrorNegocio("Ese paquete ya se resolvió.")
    return _ejecutar(db, plan, usuario, secreto, solicitudes, {j: equipo_id for j in solicitudes}, excluir or set())


def rechazar_plan(db: Session, plan: m.PlanAsignacion, usuario: m.Usuario, motivo: str = "") -> None:
    if plan.estado != m.EstadoPlan.PROPUESTO:
        raise sv.ErrorNegocio("Este plan ya fue resuelto.")
    plan.estado = m.EstadoPlan.RECHAZADO
    res = db.get(m.PlanResumen, plan.id)
    if res:
        res.datos = {**res.datos, "motivo_rechazo": motivo.strip() or "Rechazado por la entidad"}
    db.add(m.Bitacora(usuario_id=usuario.id, accion="rechazar_plan", objeto=f"plan:{plan.id}",
                      detalle={"motivo": motivo.strip()}))
    db.commit()
