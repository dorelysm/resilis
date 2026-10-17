"""Configuración de la aplicación, leída de variables de entorno o de un archivo .env."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # En local se usa el PostgreSQL de docker-compose (puerto 5440).
    # En Railway la variable DATABASE_URL la entrega el servicio de PostgreSQL.
    database_url: str = "postgresql+psycopg://resilis:resilis@localhost:5440/resilis"
    secret_key: str = "cambiar-en-produccion"
    entorno: str = "desarrollo"
    # Si es verdadero y la base no tiene barrios, carga las viviendas y genera un escenario simulado al arrancar.
    sembrar_demo: bool = False
    # Si es verdadero, renueva el escenario simulado al arrancar, conservando a los administradores. Se niega si hay
    # otras cuentas reales. Es de un solo uso: conviene quitarla después, o cada arranque volvería a renovarlo.
    reiniciar_demo: bool = False
    # Si es verdadero, al arrancar BORRA todos los datos (reportes, solicitudes, donaciones, inventario, planes...) y deja
    # solo las cuentas reales. Es de un solo uso: hay que quitarla después, o cada arranque volvería a borrar.
    limpiar_datos: bool = False
    # Si es verdadero, al arrancar carga el escenario guionado del vendaval en Malambo (evento, reportes, 10 solicitudes e
    # inventario). Se niega si ya hay algún evento. Es de un solo uso: conviene quitarla después.
    cargar_escenario_malambo: bool = False
    # Si es verdadero, al arrancar imprime en los registros las cuentas reales (sin contraseñas ni teléfonos completos).
    # Es de un solo uso: conviene quitarla después.
    listar_cuentas: bool = False
    # Para crear el primer administrador al arrancar (solo si todavía no existe uno). Después conviene quitarlas.
    admin_nombre: str = "Administrador"
    admin_telefono: str = ""
    admin_password: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()


def normalizar_url(url: str) -> str:
    """Railway entrega URLs 'postgresql://' o 'postgres://'; SQLAlchemy con psycopg 3 necesita el prefijo del driver."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    return url
