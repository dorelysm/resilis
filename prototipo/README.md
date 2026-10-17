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

## Mapa (bloque 7)

`/mapa` (entidad, brigadista y administrador) dibuja los sectores con Leaflet 1.9.4, que viene incluido en `app/static/vendor/leaflet/` (sin CDN; licencia BSD en el mismo directorio). Los datos salen de `/mapa/datos.json`: un renglón por sector, **sin datos de personas**.

- **Color:** el conmutador alterna entre prioridad y confianza. Las clases son quintiles de lo que se muestra, para que haya contraste aunque los valores se parezcan. Las rampas salen de los colores del logo y el número de cada círculo tiene contraste AA sobre su color.
- **Sin reportes:** el círculo va rayado y con borde de trazos, para no confundirlo con un sector tranquilo.
- **El color no es lo único:** el número dentro del círculo es el lugar en la lista y el tamaño crece con la población. Cada círculo se enfoca con el teclado (Enter abre su ventana) y tiene una descripción completa para lectores de pantalla. La misma información está en la tabla de `/prioridades`, que el mapa enlaza.
- **Filtros:** por municipio y por aviso de información faltante. Un aviso en la página anuncia cuántos sectores se muestran.
- **Zoom:** los círculos se achican al alejar y los números aparecen al acercar.
- **Datos:** el JavaScript y los estilos de la página pesan unos 51 KB comprimidos, sin contar los mosaicos. Los mosaicos de fondo vienen de OpenStreetMap, así que sin internet se ven los círculos sobre un fondo vacío.
- **Límite:** los sectores solo tienen un punto (latitud y longitud), no un contorno; por eso son círculos y no zonas.

## Plan de asignación (bloque 6)

`/plan` (solo la entidad) propone qué lote entregar a cada solicitud verificada. **Hasta que la entidad lo aprueba no se reserva nada.**

- **Modelo (`app/optimizacion.py`):** programación lineal entera con SciPy (`milp`, HiGHS). Maximiza `suma (w/d + κ·u − λ·km) · x` con la cantidad de cada lote entregada a cada solicitud como variable entera. `w` = prioridad × (0,5 + 0,5 × confianza); `u` = urgencia de usar el lote por su vencimiento (primero en vencer, primero en salir); `km` = distancia del centro de acopio a la solicitud. Respeta el inventario, lo pedido, el tipo de recurso, el destino de las donaciones dirigidas y no usa lotes vencidos.
- **Equidad (θ):** cada solicitud de prioridad alta recibe al menos una fracción θ de lo que pide, sin pasar de su parte igual del inventario. Si no es posible, se calcula sin ella y se avisa.
- **Costo de la distancia:** se acota para que nunca haga que "no entregar" sea mejor que entregar.
- **Referencia voraz:** el plan se compara con una asignación sencilla (la más prioritaria primero) y sirve de respaldo si el solucionador falla o se pasa del tiempo (10 s).
- **Explicación:** cada línea dice la prioridad, la confianza, el vencimiento del lote, el centro y la distancia; el plan lista lo que queda sin cubrir y por qué.
- **Aprobar:** reserva el inventario y asigna un equipo con su código, por solicitud. La entidad puede cambiar el equipo de cada una o dejarla fuera. Si el inventario cambió desde que se calculó, esa solicitud se omite y se informa. Se muestran las 40 más prioritarias; las demás se aprueban con el equipo propuesto.
- **Entrega parcial:** si el inventario solo alcanza para una parte, se entrega esa parte y la solicitud vuelve a estar verificada con lo que falta.
- **Límite conocido:** la compatibilidad entre el tipo de recurso y el acceso del sector (una lancha para un sector aislado) no se modela porque los lotes no tienen ese dato. El plan solo avisa que el sector está aislado.
- **Datos de ejemplo:** con 1.047 solicitudes verificadas que piden 13.236 unidades y 9.097 disponibles, el plan se resuelve en 0,4 s y cubre un 10,1 % más de necesidad ponderada que la referencia voraz. Con inventario suficiente para todo, la mejora es mínima.

## Logo y diseño

Los originales están en `../utils/` (`logo_fondo_transparente.png` y `logo_fondo_blanco.jpeg`). `scripts/preparar_logo.py` recorta el emblema y genera las imágenes de `app/static/img/`; `scripts/colores_logo.py` extrae los colores dominantes del logo y su contraste.

| Color | Valor | Uso |
|---|---|---|
| Azul profundo | `#0D4C66` | títulos, texto de la marca, botones al pasar el cursor |
| Azul | `#055C81` | botones, enlaces y barra de navegación |
| Verde azulado | `#0DA4A0` | franja, bordes de tarjetas y línea de tiempo (nunca como texto) |
| Naranja | `#F7714A` | franja y acentos; el texto encima es oscuro |
| Verde azulado oscuro y naranja oscuro | `#046E70`, `#B8420F` | versiones oscurecidas aptas para texto y para el foco del teclado |

Los colores del logo claros (verde azulado y naranja) no tienen contraste suficiente para texto sobre blanco, por eso se usan solo en detalles gráficos. `tests/test_diseno.py` verifica el contraste AA de cada combinación y que las imágenes sean livianas (la imagen de la barra pesa unos 8 KB).

Del logo se usa solo el dibujo, sin su lema. El lema del sistema es "Decisiones inteligentes, recursos optimizados, vidas protegidas".

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
