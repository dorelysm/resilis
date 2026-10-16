from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.db import get_db
from app.main import app


def test_salud(engine, monkeypatch):
    """La ruta /salud responde y ve los municipios cargados, usando SQLite en memoria."""
    from app import main
    from app.cargas import cargar_viviendas

    sesiones = sessionmaker(bind=engine, expire_on_commit=False)
    with sesiones() as db:
        cargar_viviendas(db)

    def _db():
        with sesiones() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(main, "crear_tablas", lambda: None)
    try:
        with TestClient(app) as cliente:
            r = cliente.get("/salud")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    assert r.json() == {"estado": "ok", "base_de_datos": "ok", "municipios": 23}
