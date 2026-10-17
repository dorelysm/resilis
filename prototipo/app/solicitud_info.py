"""Qué pidió cada solicitud, para mostrarlo completo en las listas del personal.

Una lista que dice solo "Otro (1)" no deja entender la necesidad. Aquí se agrega a cada solicitud, antes de pintarla,
lo específico que pidió (por ejemplo "Silla de ruedas" o los medicamentos que necesita). La descripción que escribió la
persona ya está en la solicitud. De la información de vulnerabilidad solo se usa lo que necesita en especial, no la
descripción de su situación.
"""
from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m


def adjuntar_detalles(db: Session, solicitudes: Iterable[m.Solicitud]) -> None:
    """Pone en cada solicitud `especifica`: lo que necesita en especial, o "" si no hay nada especial."""
    solicitudes = [s for s in solicitudes if s is not None]
    if not solicitudes:
        return
    especifica = dict(db.execute(select(m.Vulnerabilidad.solicitud_id, m.Vulnerabilidad.necesidad_especifica)
                                 .where(m.Vulnerabilidad.solicitud_id.in_([s.id for s in solicitudes]))).all())
    for s in solicitudes:
        s.especifica = (especifica.get(s.id) or "").strip()
