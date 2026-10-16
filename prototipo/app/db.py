"""Conexión a la base de datos."""
from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings, normalizar_url


class Base(DeclarativeBase):
    pass


def crear_engine(url: str | None = None):
    url = normalizar_url(url or get_settings().database_url)
    return create_engine(url, pool_pre_ping=True)


engine = crear_engine()
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    """Dependencia de FastAPI: una sesión por petición."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def crear_tablas(bind=None) -> None:
    """Crea todas las tablas. Para el prototipo no se usan migraciones."""
    from app import models  # noqa: F401  (registra las tablas en Base.metadata)

    Base.metadata.create_all(bind or engine)
