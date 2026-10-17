"""Cambio de sectores a barrios en una base ya creada con el esquema anterior.

El prototipo no usa migraciones y `create_all` no modifica tablas que ya existen, así que este paso, que corre una sola
vez al arrancar si todavía existe la tabla `sector`, hace lo mínimo:

- Borra lo que dependía de los sectores antiguos: reportes, solicitudes (con su vulnerabilidad), puntajes, planes,
  entregas, donaciones, lotes e inventario, y los eventos.
- Conserva las cuentas, los centros de acopio, los perfiles de donante, los pesos y la bitácora. A las cuentas y a los
  centros solo se les quita el sector (queda sin barrio hasta que se les asigne uno).
- Elimina la tabla `sector`. Las tablas que dependían de ella se recrean vacías con el esquema nuevo.

Solo actúa sobre PostgreSQL; en las bases de prueba (SQLite) no hay nada que migrar.
"""
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# Tablas con columnas hacia el sector antiguo (o hacia lo que se borra): se vacían y se recrean.
TABLAS_A_RECREAR = [
    "incidencia", "entrega", "movimiento_inventario", "plan_resumen", "plan_linea", "plan_asignacion",
    "vulnerabilidad", "lote", "donacion", "solicitud", "reporte_danos", "puntaje_sector",
]
OTRAS_A_VACIAR = ["verificacion", "evento_auditoria", "evento"]


def migrar_sectores_a_barrios(engine: Engine) -> dict | None:
    """Devuelve cuántos registros borró de cada tabla, o None si no había nada que migrar."""
    if engine.dialect.name != "postgresql":
        return None
    tablas = set(inspect(engine).get_table_names())
    if "sector" not in tablas:
        return None
    borrados: dict[str, int] = {}
    with engine.begin() as con:
        for t in TABLAS_A_RECREAR + OTRAS_A_VACIAR:
            if t in tablas:
                borrados[t] = con.execute(text(f'SELECT count(*) FROM "{t}"')).scalar_one()
        for t in TABLAS_A_RECREAR:
            if t in tablas:
                con.execute(text(f'DROP TABLE "{t}" CASCADE'))
        for t in OTRAS_A_VACIAR:
            if t in tablas:
                con.execute(text(f'DELETE FROM "{t}"'))
        for t in ("usuario", "centro_acopio"):
            if t in tablas:
                con.execute(text(f'ALTER TABLE "{t}" DROP COLUMN IF EXISTS sector_id'))
                con.execute(text(f'ALTER TABLE "{t}" ADD COLUMN IF NOT EXISTS barrio_id INTEGER'))
        if "peso" in tablas:
            con.execute(text("UPDATE peso SET ambito = 'barrio' WHERE ambito = 'sector'"))
        con.execute(text('DROP TABLE "sector" CASCADE'))
    return {k: v for k, v in borrados.items() if v}
