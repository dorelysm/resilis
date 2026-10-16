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

## Cuentas y formularios (bloque 3)

Páginas: `/registro`, `/entrar`, `/reportes/nuevo`, `/solicitudes/nueva`, `/donaciones/nueva` y `/admin/usuarios`.

- **Registro público:** personas que necesitan ayuda y donantes. Exige autorización de datos. Las cuentas de brigadistas, entidades, equipos de entrega y centros de acopio las crea el administrador.
- **Primer administrador:** defina `ADMIN_TELEFONO` y `ADMIN_PASSWORD` (y opcionalmente `ADMIN_NOMBRE`) antes de arrancar. Si no hay un administrador real, se crea al iniciar. Después conviene quitar las variables. También se puede crear por línea de comandos con `uv run python -m app.usuarios --rol administrador --nombre "..." --telefono ...` (pide la contraseña sin mostrarla).
- **Seguridad:** contraseñas con scrypt y sal, sesión firmada, token CSRF en cada formulario, límite de 20 envíos por hora y usuario, y acceso por rol.
- Las cuentas simuladas no pueden entrar.

## Operación de la respuesta (bloque 4)

Flujo: donación → recepción en el centro de acopio → solicitud → verificación → asignación → código → entrega → cierre.

| Página | Quién | Para qué |
|---|---|---|
| `/recepcion`, `/inventario` | centro de acopio (inventario también la entidad) | confirmar lo recibido y ver lotes disponibles, reservados y entregados |
| `/verificacion` | brigadista, entidad | verificar o desmentir solicitudes y reportes |
| `/asignacion` | entidad | reservar inventario y asignar a un equipo de entrega (primero en vencer, primero en salir) |
| `/entregas` | equipo de entrega | ver sus entregas, marcar "en camino", validar el código, registrar incidencias |
| `/solicitudes/{id}` y `/ficha` | solicitante | seguimiento, su código de entrega y ficha para imprimir |
| `/admin/auditoria` | administrador | comprobar la cadena de eventos |

- **Código de entrega:** 8 caracteres calculados con la clave del servidor (HMAC). La base de datos solo guarda la sal y la huella (sha256). La persona lo ve en su seguimiento; el equipo nunca lo recibe, solo la huella. Sirve una vez, para el equipo asignado, vence a las 72 h y tras 5 intentos fallidos se invalida.
- **Sin conexión:** `/entregas` descarga la sal y la huella de las entregas del equipo (`/entregas/datos.json`). Sin red, el navegador valida el código comparando huellas y guarda la entrega como pendiente; al volver la señal la envía y el servidor la valida de nuevo. Reenviar una entrega ya confirmada no la duplica.
- **Service worker (`/sw.js`):** guarda la última copia de `/entregas` para poder abrirla sin red. Al salir de la sesión se borran esa copia y los datos locales. **No se pudo comprobar en el navegador integrado de la herramienta de desarrollo; probar en un Chrome o Android real.**
- **Cadena de eventos:** cada cambio de estado de una solicitud se encadena por hash con el anterior, sin datos personales.

## Prioridad y confianza (bloque 5)

`app/motor.py` tiene las fórmulas (funciones puras, sin base de datos) y `app/puntaje.py` las aplica a los datos y guarda el resultado en `puntaje_sector` y en cada solicitud. Se recalcula solo después de cada reporte, solicitud, verificación, recepción, asignación y entrega (unos 0,15 s con 153 sectores y 1.000 solicitudes).

- **Confianza de un dato:** `c = 0,35 F + 0,30 V + 0,15 A + 0,20 K` (fuente, verificación, vigencia, corroboración). Un dato desmentido vale 0.
- **Confianza de un sector:** `C = [1 - prod(1 - c)] (1 - 0,5 D)`; sin reportes vale 0 y el sector se ordena solo con la línea base ("hora cero") y con aviso.
- **Prioridad:** TOPSIS con cinco dimensiones para sectores y cinco criterios para solicitudes. Los pesos se ajustan en `/pesos` (entidad y administrador) y se normalizan a 100 %.
- **Accesibilidad:** no penaliza; un sector aislado sube un poco, nunca baja.
- **Avisos:** sin reportes, desactualizado (más de 24 h), baja confianza (menos de 0,4) y reportes que se contradicen.
- **Hora de referencia:** la actual; en un evento simulado, la del último reporte, para que la demostración no "envejezca".
- **Páginas:** `/prioridades` (listas), `/prioridades/sectores/{id}` (por qué ocupa ese lugar) y `/pesos`. La asignación ya ordena por prioridad.
- `motor.ahp_pesos` (AHP: devuelve los pesos y la razón de consistencia CR, que debe ser menor que 0,1) existe y tiene pruebas, pero todavía no hay una pantalla de comparación por pares: `/pesos` recibe los pesos directamente.

## Datos simulados

Genera un escenario completo y reproducible (sectores anclados en las viviendas reales, un evento, usuarios, reportes, solicitudes, donaciones e inventario, todo ficticio):

```bash
uv run python -m app.cargas                                  # antes: las viviendas deben estar cargadas
uv run python -m app.simulacion --seed 42 --tipo inundacion  # terremoto | inundacion | vendaval | deslizamiento
```

Con la misma semilla se obtienen los mismos datos. Cada ejecución borra la simulación anterior (no toca las viviendas). La "verdad" del escenario (el daño real de cada sector, los reportes falsos y las solicitudes duplicadas) queda en la tabla `bitacora` (acción `simulacion_verdad`) para medir después qué tan bien se detectan.

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
