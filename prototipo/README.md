# Resilis: prototipo

Aplicación web (FastAPI) del prototipo de Resilis. Los requisitos están en `../Requerimientos/` y el plan de 12 horas en la sección 9.

## Requisitos
- Python 3.12 (fijado en `.python-version`) y [uv](https://docs.astral.sh/uv/)
- Docker, solo para el PostgreSQL local

## Puesta en marcha

```bash
uv sync                         # instala las dependencias
docker compose up -d            # PostgreSQL 17 local en el puerto 5440
cp .env.example .env            # variables de entorno
uv run uvicorn app.main:app --reload
```

Al arrancar, la aplicación crea las tablas que falten. **No carga datos.** La carga de las proyecciones de viviendas del Atlántico (`data/viviendas_atlantico.csv`) es explícita y todavía no se ha ejecutado:

```bash
uv run python -m app.cargas     # cuando se decida cargar los datos
```

Comprobación: <http://127.0.0.1:8000/salud>.

## Pruebas

```bash
uv run pytest -q
```

Las pruebas usan SQLite en memoria, así que no necesitan Docker.

## Estructura

| Ruta | Contenido |
|---|---|
| `app/models.py` | Esquema completo de la base de datos (22 tablas) |
| `app/cargas.py` | Carga de las proyecciones de viviendas |
| `app/main.py` | Aplicación FastAPI y ruta `/salud` |
| `data/` | Datos abiertos incluidos en el repositorio |
| `tests/` | Pruebas del esquema, de la carga y de `/salud` |

## Despliegue

`railway.json` define el comando de arranque y la comprobación de salud (`/salud`). La variable `DATABASE_URL` la entrega el servicio de PostgreSQL de Railway.

## Notas
- No se usan migraciones: `crear_tablas()` crea lo que falta. Si cambia una tabla existente hay que recrear la base de desarrollo.
- Los datos de personas son ficticios.
