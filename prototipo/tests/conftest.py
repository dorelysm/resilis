import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db import Base


@pytest.fixture()
def engine():
    """Base SQLite en memoria: las pruebas no necesitan PostgreSQL ni Docker."""
    eng = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)

    @event.listens_for(eng, "connect")
    def _fk(dbapi_con, _):
        dbapi_con.execute("PRAGMA foreign_keys=ON")

    from app import models  # noqa: F401

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    with sessionmaker(bind=engine, expire_on_commit=False)() as sesion:
        yield sesion


@pytest.fixture(autouse=True)
def scrypt_barato(monkeypatch):
    """Las pruebas usan un costo de scrypt bajo para correr rápido. El formato del resumen guarda el costo,
    así que la verificación sigue siendo la real."""
    from app import seguridad

    monkeypatch.setattr(seguridad, "_N", 2**10)
