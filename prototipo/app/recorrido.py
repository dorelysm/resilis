"""Recorrido de cada cosa que entra al sistema: reportes, solicitudes y donaciones.

Todo lo que ocurre sigue un camino de etapas. Aquí se calcula en qué etapa va cada cosa, desde cuándo, y cuántas hay en
cada una (para ver dónde se acumula el trabajo). No contiene datos personales: solo estados, horas y cantidades.
"""
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app.solicitud_info import adjuntar_detalles

HECHO, ACTUAL, PENDIENTE, PROBLEMA = "hecho", "actual", "pendiente", "problema"
HORAS_ESPERA_LARGA = 6.0  # una etapa con algo esperando más que esto se marca como posible cuello de botella

ESTADO_TEXTO = {HECHO: "Listo", ACTUAL: "Aquí va", PENDIENTE: "Falta", PROBLEMA: "Problema"}


def _utc(hora: datetime | None) -> datetime | None:
    return hora.replace(tzinfo=timezone.utc) if hora is not None and hora.tzinfo is None else hora


def _horas_desde(hora: datetime | None, ahora: datetime | None = None) -> float | None:
    hora = _utc(hora)
    if hora is None:
        return None
    return max(0.0, ((ahora or m.ahora()) - hora).total_seconds() / 3600)


def _paso(clave: str, titulo: str, ayuda: str, estado: str, hora: datetime | None = None, nota: str = "") -> dict:
    return {"clave": clave, "titulo": titulo, "ayuda": ayuda, "estado": estado, "estado_texto": ESTADO_TEXTO[estado],
            "hora": hora, "nota": nota}


def _marcar_actual(pasos: list[dict]) -> list[dict]:
    """El primer paso que falta es el que 'va ahora', salvo que el recorrido ya terminó o tuvo un problema."""
    if any(p["estado"] in (PROBLEMA, ACTUAL) for p in pasos):
        return pasos
    for p in pasos:
        if p["estado"] == PENDIENTE:
            p["estado"], p["estado_texto"] = ACTUAL, ESTADO_TEXTO[ACTUAL]
            break
    return pasos


# ----------------------------------------------------------------------------- solicitud
ORDEN_SOLICITUD = [m.EstadoSolicitud.REGISTRADA, m.EstadoSolicitud.VERIFICADA, m.EstadoSolicitud.ASIGNADA,
                   m.EstadoSolicitud.EN_CAMINO, m.EstadoSolicitud.ENTREGADA, m.EstadoSolicitud.CERRADA]


def pasos_solicitud(db: Session, sol: m.Solicitud, mostrar_equipo: bool = True) -> list[dict]:
    eventos = db.scalars(select(m.EventoAuditoria).where(m.EventoAuditoria.solicitud_id == sol.id)
                         .order_by(m.EventoAuditoria.id)).all()
    ultimo = {}
    for e in eventos:
        ultimo[e.tipo] = e.hora
    rango = ORDEN_SOLICITUD.index(sol.estado) if sol.estado in ORDEN_SOLICITUD else -1
    anulada = sol.estado == m.EstadoSolicitud.ANULADA

    equipo = ""
    entrega = db.scalar(select(m.Entrega).where(m.Entrega.solicitud_id == sol.id).order_by(m.Entrega.id.desc()).limit(1))
    if mostrar_equipo and entrega is not None:
        usuario = db.get(m.Usuario, entrega.equipo_id)
        equipo = f"Equipo: {usuario.nombre}." if usuario else ""

    def estado_de(indice: int) -> str:
        return HECHO if rango >= indice else PENDIENTE

    pasos = [
        _paso("registrada", "Pedido registrado", "La solicitud quedó guardada y entró a la lista de prioridades.",
              HECHO, sol.creado_en),
        _paso("verificada", "Verificada", "Una persona en campo confirmó que la necesidad es real.",
              PROBLEMA if anulada and "desmentida" in ultimo else estado_de(1), ultimo.get("verificada") or ultimo.get("desmentida"),
              "No se pudo verificar." if anulada and "desmentida" in ultimo else ""),
        _paso("asignada", "Equipo asignado", "Se reservó la ayuda y un equipo de entrega la va a llevar.",
              estado_de(2), ultimo.get("asignada"), equipo),
        _paso("en_camino", "En camino", "El equipo salió hacia la dirección.", estado_de(3), ultimo.get("en_camino")),
        _paso("entregada", "Entregada", "El equipo entregó la ayuda y comprobó el código de entrega.",
              estado_de(4), ultimo.get("entregada") or ultimo.get("entrega_parcial"),
              "Fue una entrega parcial: el resto llega cuando haya inventario." if "entrega_parcial" in ultimo and rango < 4 else ""),
        _paso("cerrada", "Recibida y confirmada", "La persona confirmó que recibió la ayuda.", estado_de(5), ultimo.get("cerrada")),
    ]
    if anulada and "desmentida" not in ultimo:
        pasos[1]["estado"], pasos[1]["estado_texto"], pasos[1]["nota"] = PROBLEMA, ESTADO_TEXTO[PROBLEMA], "La solicitud se anuló."
    if sol.estado == m.EstadoSolicitud.EN_CAMINO:  # el equipo va en camino: ese paso está pasando, no terminó
        pasos[3]["estado"], pasos[3]["estado_texto"] = ACTUAL, ESTADO_TEXTO[ACTUAL]
    incidencia = ultimo.get("incidencia")
    if incidencia and (ultimo.get("asignada") is None or _utc(incidencia) >= _utc(ultimo["asignada"])) and rango < 3:
        pasos[2]["nota"] = "La entrega anterior no se pudo hacer; se asignará de nuevo."
    return _marcar_actual(pasos)


# ----------------------------------------------------------------------------- donación
def pasos_donacion(db: Session, don: m.Donacion) -> list[dict]:
    lotes = db.scalars(select(m.Lote).where(m.Lote.donacion_id == don.id)).all()
    recibida = sum(l.cantidad_recibida for l in lotes)
    reservada = sum(l.cantidad_reservada for l in lotes)
    entregada = sum(l.cantidad_entregada for l in lotes)
    hora_recepcion = None
    if lotes:
        hora_recepcion = db.scalar(select(func.min(m.MovimientoInventario.hora)).where(
            m.MovimientoInventario.lote_id.in_([l.id for l in lotes]), m.MovimientoInventario.tipo == "recepcion"))
    en_centro = don.estado != m.EstadoDonacion.OFRECIDA
    if don.monetaria:
        return _marcar_actual([
            _paso("ofrecida", "Ofrecida", "La donación quedó registrada.", HECHO, don.creado_en),
            _paso("recibida", "Recibida", "La entidad dejó constancia de que la recibió. Resilis no procesa pagos.",
                  HECHO if en_centro else PENDIENTE),
        ])
    unidad = don.unidad
    return _marcar_actual([
        _paso("ofrecida", "Ofrecida", "La donación quedó registrada y un centro de acopio la espera.", HECHO, don.creado_en),
        _paso("recibida", "Recibida en el centro", "El centro de acopio recibió y contó lo que llegó.",
              HECHO if en_centro else PENDIENTE, hora_recepcion,
              f"Llegaron {recibida} {unidad}." if recibida else ""),
        _paso("inventario", "En el inventario", "Ya cuenta como ayuda disponible para repartir.",
              HECHO if lotes else PENDIENTE, hora_recepcion),
        _paso("reservada", "Reservada para entregas", "El plan aprobado apartó esta ayuda para solicitudes concretas.",
              HECHO if reservada or entregada else PENDIENTE, None,
              f"{reservada + entregada} de {recibida} {unidad} ya tienen destino." if reservada or entregada else ""),
        _paso("entregada", "Entregada", "La ayuda llegó a las personas.", HECHO if entregada and entregada >= recibida else PENDIENTE,
              None, f"{entregada} de {recibida} {unidad} ya se entregaron." if entregada else ""),
    ])


# ----------------------------------------------------------------------------- reporte
def pasos_reporte(db: Session, rep: m.ReporteDanos) -> list[dict]:
    revision = db.scalar(select(m.Verificacion).where(m.Verificacion.objeto_tipo == "reporte",
                                                      m.Verificacion.objeto_id == rep.id).order_by(m.Verificacion.id.desc()).limit(1))
    desmentido = revision is not None and revision.resultado == "desmentido"
    anulado = rep.estado != "activo"
    posicion = db.scalar(select(m.PuntajeBarrio.posicion).where(m.PuntajeBarrio.barrio_id == rep.barrio_id))
    total = db.scalar(select(func.count()).select_from(m.PuntajeBarrio)) or 0
    cuenta = not desmentido and not anulado
    return _marcar_actual([
        _paso("enviado", "Reporte enviado", "El reporte quedó guardado.", HECHO, rep.hora_captura),
        _paso("revisado", "Revisado en campo", "Alguien lo confirmó o lo desmintió. Si nadie lo revisa, igual cuenta, con menos peso.",
              PROBLEMA if desmentido else (HECHO if revision else PENDIENTE), revision.hora if revision else None,
              "Se desmintió: ya no cuenta." if desmentido else ""),
        _paso("prioridad", "Cuenta para la prioridad", "El barrio sube o baja en la lista según lo que reportan.",
              PROBLEMA if anulado and not desmentido else (HECHO if cuenta else PENDIENTE), None,
              f"El barrio va en el lugar {posicion} de {total}." if cuenta and posicion else
              ("El reporte se anuló." if anulado and not desmentido else "")),
    ])


# ----------------------------------------------------------------------------- panel
ETAPAS = {
    "solicitud": [
        ("registrada", "Registradas", "Esperan que alguien las verifique."),
        ("verificada", "Verificadas", "Esperan entrar a un plan y tener equipo."),
        ("asignada", "Con equipo", "Tienen equipo y código; el equipo aún no sale."),
        ("en_camino", "En camino", "El equipo va hacia la dirección."),
        ("entregada", "Entregadas", "Se entregaron; falta que la persona confirme."),
        ("cerrada", "Confirmadas", "La persona confirmó que recibió la ayuda."),
    ],
    "donacion": [
        ("ofrecida", "Ofrecidas", "Esperan que un centro de acopio las reciba."),
        ("recibida", "Recibidas", "El centro las recibió (o es dinero con constancia)."),
        ("en_inventario", "En inventario", "Disponibles para repartir."),
        ("asignada", "Con destino", "Reservadas para solicitudes."),
        ("entregada", "Entregadas", "Ya llegaron a las personas."),
    ],
    "reporte": [
        ("sin_revisar", "Sin revisar", "Cuentan, con menos peso, hasta que alguien los revise."),
        ("verificado", "Verificados", "Confirmados en campo."),
        ("desmentido", "Desmentidos", "No cuentan."),
        ("anulado", "Anulados", "Se retiraron."),
    ],
}
TITULOS = {"solicitud": "Solicitudes de ayuda", "donacion": "Donaciones", "reporte": "Reportes de daños"}


def _fila_etapa(clave, titulo, ayuda, cantidad, espera_horas):
    return {"clave": clave, "titulo": titulo, "ayuda": ayuda, "cantidad": cantidad, "espera_horas": espera_horas,
            "espera_larga": espera_horas is not None and espera_horas >= HORAS_ESPERA_LARGA}


def _desde_cuando_solicitudes(db: Session) -> dict[int, datetime]:
    """Desde cuándo está cada solicitud en su etapa actual: la hora de su último evento (o de su registro)."""
    ultimo = dict(db.execute(select(m.EventoAuditoria.solicitud_id, func.max(m.EventoAuditoria.hora))
                             .where(m.EventoAuditoria.solicitud_id.is_not(None),
                                    m.EventoAuditoria.tipo != "codigo_incorrecto")
                             .group_by(m.EventoAuditoria.solicitud_id)).all())
    return ultimo


def panel(db: Session) -> list[dict]:
    """Para cada recorrido, cuántas cosas hay en cada etapa y cuánto lleva esperando la más antigua."""
    ahora = m.ahora()
    resultado = []

    # solicitudes
    desde = _desde_cuando_solicitudes(db)
    cuentas: dict[str, int] = {}
    esperas: dict[str, float] = {}
    for sol_id, estado, creado in db.execute(select(m.Solicitud.id, m.Solicitud.estado, m.Solicitud.creado_en)).all():
        cuentas[estado] = cuentas.get(estado, 0) + 1
        horas = _horas_desde(desde.get(sol_id) or creado, ahora)
        if estado in ("registrada", "verificada", "asignada", "en_camino", "entregada") and horas is not None:
            esperas[estado] = max(esperas.get(estado, 0.0), horas)
    etapas = [_fila_etapa(c, t, a, cuentas.get(c, 0), esperas.get(c)) for c, t, a in ETAPAS["solicitud"]]
    resultado.append({"tipo": "solicitud", "titulo": TITULOS["solicitud"], "etapas": etapas,
                      "aparte": [{"titulo": "Anuladas", "cantidad": cuentas.get("anulada", 0)}]})

    # donaciones (solo ayuda en especie para el recorrido; el dinero cuenta como recibida)
    por_estado = dict(db.execute(select(m.Donacion.estado, func.count()).group_by(m.Donacion.estado)).all())
    etapas = [_fila_etapa(c, t, a, por_estado.get(c, 0), None) for c, t, a in ETAPAS["donacion"]]
    resultado.append({"tipo": "donacion", "titulo": TITULOS["donacion"], "etapas": etapas, "aparte": []})

    # reportes
    revisados = {}
    for objeto_id, resultado_ in db.execute(select(m.Verificacion.objeto_id, m.Verificacion.resultado)
                                            .where(m.Verificacion.objeto_tipo == "reporte").order_by(m.Verificacion.id)).all():
        revisados[objeto_id] = resultado_
    cuentas_r = {"sin_revisar": 0, "verificado": 0, "desmentido": 0, "anulado": 0}
    espera_r = None
    for rep_id, estado, captura in db.execute(select(m.ReporteDanos.id, m.ReporteDanos.estado, m.ReporteDanos.hora_captura)).all():
        r = revisados.get(rep_id)
        etapa = "anulado" if estado != "activo" and r != "desmentido" else {"verificado": "verificado", "desmentido": "desmentido"}.get(r, "sin_revisar")
        cuentas_r[etapa] += 1
        if etapa == "sin_revisar":
            h = _horas_desde(captura, ahora)
            espera_r = h if espera_r is None else max(espera_r, h)
    etapas = [_fila_etapa(c, t, a, cuentas_r[c], espera_r if c == "sin_revisar" else None) for c, t, a in ETAPAS["reporte"]]
    resultado.append({"tipo": "reporte", "titulo": TITULOS["reporte"], "etapas": etapas, "aparte": []})
    return resultado


def elementos_de_etapa(db: Session, tipo: str, etapa: str, limite: int = 25) -> list[dict]:
    """Lo que hay en una etapa, de lo que más lleva esperando a lo que menos. Solo datos no personales."""
    ahora = m.ahora()
    filas: list[dict] = []
    if tipo == "solicitud" and etapa in {c for c, *_ in ETAPAS["solicitud"]} | {"anulada"}:
        desde = _desde_cuando_solicitudes(db)
        consulta = db.execute(select(m.Solicitud, m.Barrio.etiqueta).join(m.Barrio, m.Barrio.id == m.Solicitud.barrio_id)
                              .where(m.Solicitud.estado == etapa)).all()
        adjuntar_detalles(db, [sol for sol, _ in consulta])
        for sol, barrio in consulta:
            filas.append({"titulo": f"{sol.necesidad.replace('_', ' ').capitalize()}{': ' + sol.especifica if sol.especifica else ''} · {sol.cantidad}",
                          "detalle": sol.descripcion or "", "lugar": barrio,
                          "horas": _horas_desde(desde.get(sol.id) or sol.creado_en, ahora),
                          "enlace": f"/recorrido/solicitudes/{sol.id}", "id": sol.id})
    elif tipo == "donacion" and etapa in {c for c, *_ in ETAPAS["donacion"]}:
        for don in db.scalars(select(m.Donacion).where(m.Donacion.estado == etapa)):
            que = f"Dinero (constancia)" if don.monetaria else f"{don.tipo_bien.replace('_', ' ').capitalize()} · {don.cantidad} {don.unidad}"
            filas.append({"titulo": que, "lugar": "", "horas": _horas_desde(don.creado_en, ahora), "enlace": "", "id": don.id})
    elif tipo == "reporte" and etapa in {c for c, *_ in ETAPAS["reporte"]}:
        revisados = {}
        for objeto_id, r in db.execute(select(m.Verificacion.objeto_id, m.Verificacion.resultado)
                                       .where(m.Verificacion.objeto_tipo == "reporte").order_by(m.Verificacion.id)).all():
            revisados[objeto_id] = r
        for rep, barrio in db.execute(select(m.ReporteDanos, m.Barrio.etiqueta).join(m.Barrio, m.Barrio.id == m.ReporteDanos.barrio_id)):
            r = revisados.get(rep.id)
            et = "anulado" if rep.estado != "activo" and r != "desmentido" else {"verificado": "verificado", "desmentido": "desmentido"}.get(r, "sin_revisar")
            if et == etapa:
                filas.append({"titulo": f"Daño nivel {rep.nivel_dano} · {rep.personas_afectadas} persona(s)", "lugar": barrio,
                              "horas": _horas_desde(rep.hora_captura, ahora), "enlace": "", "id": rep.id})
    filas.sort(key=lambda f: -(f["horas"] or 0))
    return filas[:limite]
