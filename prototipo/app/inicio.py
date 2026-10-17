"""Qué sigue: lo que cada rol tiene pendiente, para ponerlo arriba del inicio.

El inicio era una lista fija de tarjetas que no decía qué hacer ahora. Aquí se cuenta lo que espera a cada persona (por
ejemplo, "10 solicitudes por verificar") y se le da un enlace directo. Solo cuenta: no lleva datos de personas.
"""
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import models as m
from app import ruta as rt
from app.formato import plural


def _contar(db: Session, consulta) -> int:
    return db.scalar(select(func.count()).select_from(consulta.subquery())) or 0


def _item(texto: str, enlace: str, boton: str, urgente: bool = False) -> dict:
    return {"texto": texto, "enlace": enlace, "boton": boton, "urgente": urgente}


def que_sigue(db: Session, usuario: m.Usuario) -> list[dict]:
    rol = usuario.rol
    items: list[dict] = []

    if rol == m.Rol.SOLICITANTE:
        mias = db.scalars(select(m.Solicitud).where(
            m.Solicitud.solicitante_id == usuario.id,
            m.Solicitud.estado.in_(["registrada", "verificada", "asignada", "en_camino", "entregada"]))
            .order_by(m.Solicitud.id.desc()).limit(3)).all()
        textos = {
            "en_camino": ("Su ayuda va en camino.", "Seguir en el mapa", True),
            "asignada": ("Se asignó un equipo a su solicitud. Tenga su código a la mano.", "Ver mi código", True),
            "entregada": ("Le entregaron su ayuda. ¿Ya la recibió?", "Confirmar", False),
            "verificada": ("Verificaron su solicitud. Falta asignarle un equipo.", "Ver cómo va", False),
            "registrada": ("Su solicitud espera que alguien la verifique.", "Ver cómo va", False),
        }
        for s in mias:
            texto, boton, urgente = textos[s.estado]
            ancla = "#titulo-ruta" if s.estado == "en_camino" else ""
            items.append(_item(texto, f"/solicitudes/{s.id}{ancla}", boton, urgente))

    elif rol == m.Rol.DONANTE:
        donante = db.scalar(select(m.Donante).where(m.Donante.usuario_id == usuario.id))
        if donante is None or not db.scalar(select(m.Donacion.id).where(m.Donacion.donante_id == donante.id).limit(1)):
            items.append(_item("Todavía no ha registrado donaciones.", "/donaciones/nueva", "Registrar una donación"))
        else:
            r = rt.ruta_de_donante(db, donante)
            items.append(_item(r["texto"], "/donaciones", "Ver por dónde va", bool(r["en_camino"])))

    elif rol in (m.Rol.BRIGADISTA, m.Rol.ENTIDAD, m.Rol.ADMINISTRADOR):
        if rol in (m.Rol.BRIGADISTA, m.Rol.ENTIDAD):
            por_verificar = _contar(db, select(m.Solicitud.id).where(m.Solicitud.estado == m.EstadoSolicitud.REGISTRADA))
            sin_revisar = _contar(db, select(m.ReporteDanos.id).where(
                m.ReporteDanos.estado == "activo",
                ~select(m.Verificacion.id).where(m.Verificacion.objeto_tipo == "reporte",
                                                 m.Verificacion.objeto_id == m.ReporteDanos.id).exists()))
            if por_verificar:
                items.append(_item(f"{plural(por_verificar, 'solicitud', 'solicitudes')} por verificar.", "/verificacion",
                                   "Verificar", True))
            if sin_revisar:
                items.append(_item(f"{plural(sin_revisar, 'reporte', 'reportes')} de daños sin revisar.", "/verificacion",
                                   "Revisar reportes"))
        if rol == m.Rol.ENTIDAD:
            listas = _contar(db, select(m.Solicitud.id).where(m.Solicitud.estado == m.EstadoSolicitud.VERIFICADA))
            if listas:
                items.append(_item(f"{plural(listas, 'solicitud verificada', 'solicitudes verificadas')} esperan un plan.",
                                   "/plan", "Ir al plan", True))
        if rol in (m.Rol.ENTIDAD, m.Rol.ADMINISTRADOR):
            en_camino = _contar(db, select(m.Entrega.id).where(m.Entrega.estado == "en_camino"))
            por_salir = _contar(db, select(m.Entrega.id).where(m.Entrega.estado == "asignada"))
            if en_camino or por_salir:
                items.append(_item(f"{plural(en_camino, 'entrega')} en camino y {plural(por_salir, 'por salir', 'por salir')}.",
                                   "/recorrido", "Ver el control logístico"))
        if rol == m.Rol.ADMINISTRADOR:
            por_aprobar = _contar(db, select(m.Usuario.id).where(m.Usuario.es_organizacion.is_(True),
                                                                   m.Usuario.aprobado.is_(False)))
            if por_aprobar:
                items.append(_item(f"{plural(por_aprobar, 'organización espera', 'organizaciones esperan')} aprobación.",
                                   "/admin/usuarios", "Revisar cuentas", True))

    elif rol == m.Rol.CENTRO_ACOPIO:
        centro = db.scalar(select(m.CentroAcopio).where(m.CentroAcopio.responsable_id == usuario.id))
        if centro is None:
            items.append(_item("Su cuenta todavía no tiene un centro de acopio. Pídale al administrador que lo configure.",
                               "/recepcion", "Ver"))
        else:
            por_recibir = _contar(db, select(m.Donacion.id).where(
                m.Donacion.estado == m.EstadoDonacion.OFRECIDA, m.Donacion.monetaria.is_(False),
                (m.Donacion.centro_id == centro.id) | m.Donacion.centro_id.is_(None)))
            if por_recibir:
                items.append(_item(f"{plural(por_recibir, 'donación espera', 'donaciones esperan')} que la reciba.",
                                   "/recepcion", "Recibir", True))
            vence = _contar(db, select(m.Lote.id).where(
                m.Lote.centro_id == centro.id, m.Lote.cantidad_disponible > 0, m.Lote.vencimiento.is_not(None),
                m.Lote.vencimiento < m.ahora() + timedelta(days=7)))
            if vence:
                items.append(_item(f"{plural(vence, 'entrada', 'entradas')} del inventario vence en menos de 7 días.",
                                   "/inventario", "Ver inventario"))

    elif rol == m.Rol.EQUIPO_ENTREGA:
        en_camino = _contar(db, select(m.Entrega.id).where(m.Entrega.equipo_id == usuario.id, m.Entrega.estado == "en_camino"))
        por_salir = _contar(db, select(m.Entrega.id).where(m.Entrega.equipo_id == usuario.id, m.Entrega.estado == "asignada"))
        if en_camino or por_salir:
            partes = []
            if en_camino:
                partes.append(f"{plural(en_camino, 'entrega')} en camino")
            if por_salir:
                partes.append(f"{plural(por_salir, 'entrega')} por salir")
            items.append(_item(" y ".join(partes) + ".", "/entregas", "Ver mis entregas", True))
    return items
