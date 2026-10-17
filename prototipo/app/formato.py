"""Formato de lo que se muestra: horas de Colombia, plurales y niveles (Alta, Media, Baja) en lugar de porcentajes.

Las horas se guardan en UTC. Colombia no cambia de hora en el año (UTC-5), así que basta un desfase fijo, sin depender de
una base de zonas horarias que no siempre está instalada.
"""
from datetime import datetime, timedelta, timezone

COLOMBIA = timezone(timedelta(hours=-5), "COT")


def hora_co(valor: datetime | None, formato: str = "%d/%m/%Y %H:%M") -> str:
    """La hora en Colombia. Una hora sin zona se toma como UTC, que es como se guarda."""
    if valor is None:
        return ""
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(COLOMBIA).strftime(formato)


def iso_utc(valor: datetime | None) -> str:
    """La hora en formato máquina (UTC), para el atributo datetime de <time>."""
    if valor is None:
        return ""
    if valor.tzinfo is None:
        valor = valor.replace(tzinfo=timezone.utc)
    return valor.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%MZ")


def plural(n: int | float, singular: str, plural_: str | None = None) -> str:
    """'1 entrega', '3 entregas'. Sin paréntesis tipo 'entrega(s)'."""
    return f"{n} {singular if n == 1 else (plural_ or singular + 's')}"


# Cortes de los niveles. La confianza baja (menos de 0,4) es la misma que dispara el aviso de información faltante.
CORTES_PRIORIDAD = (0.33, 0.66)
CORTES_CONFIANZA = (0.4, 0.66)


def _nivel(valor: float | None, cortes: tuple[float, float]) -> str:
    if valor is None:
        return "—"
    return "Alta" if valor >= cortes[1] else "Media" if valor >= cortes[0] else "Baja"


def nivel_prioridad(valor: float | None) -> str:
    return _nivel(valor, CORTES_PRIORIDAD)


def nivel_confianza(valor: float | None) -> str:
    return _nivel(valor, CORTES_CONFIANZA)
