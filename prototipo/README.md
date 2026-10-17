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

`app/motor.py` tiene las fórmulas (funciones puras, sin base de datos) y `app/puntaje.py` las aplica a los datos y guarda el resultado en `puntaje_barrio` y en cada solicitud. Se recalcula solo después de cada reporte, solicitud, verificación, recepción, asignación y entrega (unos 0,4 s con 600 barrios y 1.000 solicitudes).

- **Confianza de un dato:** `c = 0,35 F + 0,30 V + 0,15 A + 0,20 K` (fuente, verificación, vigencia, corroboración). Un dato desmentido vale 0.
- **Confianza de un barrio:** `C = [1 - prod(1 - c)] (1 - 0,5 D)`; sin reportes vale 0 y el barrio se ordena solo con la línea base ("hora cero") y con aviso.
- **Prioridad:** TOPSIS con cinco dimensiones para barrios y cinco criterios para solicitudes. Los pesos se ajustan en `/pesos` (entidad y administrador) y se normalizan a 100 %.
- **Accesibilidad:** no penaliza; un barrio aislado sube un poco, nunca baja.
- **Avisos:** sin reportes, desactualizado (más de 24 h), baja confianza (menos de 0,4) y reportes que se contradicen.
- **Hora de referencia:** la actual; en un evento simulado, la del último reporte, para que la demostración no "envejezca".
- **Páginas:** `/prioridades` (listas), `/prioridades/barrios/{id}` (por qué ocupa ese lugar) y `/pesos`. La asignación ya ordena por prioridad.
- `motor.ahp_pesos` (AHP: devuelve los pesos y la razón de consistencia CR, que debe ser menor que 0,1) existe y tiene pruebas, pero todavía no hay una pantalla de comparación por pares: `/pesos` recibe los pesos directamente.

## Plan por paquetes y recorrido (ajustes tras la primera prueba)

- **Plan en paquetes pequeños:** el plan se calcula completo, pero se revisa y se aprueba de a un paquete: hasta 6 entregas de un mismo municipio, de la más prioritaria a la menos, con un solo equipo, y letra y botón grandes. Cada línea dice qué, dónde, para cuántas personas y qué tan urgente, sin porcentajes. Cuánto cubre, la comparación con la referencia, lo que queda sin cubrir y los parámetros quedan plegados. "Aprobar todo de una vez" sigue existiendo, pero escondido. El plan se cierra solo cuando se resuelven todos sus paquetes. (`app/plan.py`: `armar_paquetes`, `aprobar_paquete`.)
- **Recorrido visual:** cada solicitud, donación y reporte muestra sus etapas (hecho, aquí va, falta, problema) con texto y símbolo, no solo color; al tocar una etapa se explica qué significa. Lo ven la persona que pidió la ayuda, el donante y quien reportó. `/recorrido` (entidad, brigadista y administrador) cuenta cuántas cosas hay en cada etapa, marca las que llevan más de 6 horas esperando y deja entrar a ver qué hay en cada una, sin datos personales. (`app/recorrido.py`.)

## Mapa de la ruta de una entrega

La persona que recibe (en "Mi solicitud"), quien dona (en "Mis donaciones") y el personal (en `/recorrido/solicitudes/{id}`) ven por dónde va una entrega sobre un mapa con Leaflet: centro de acopio, destino y equipo. Se actualiza solo cada 15 segundos mientras la pantalla está abierta, tiene botón "Actualizar ahora", y todo lo del mapa está escrito también en texto (`#estado-ruta`, `#lista-destinos`).

- **La posición del equipo es SIMULADA** (`app/ruta.py`): sobre la línea recta entre el centro y el destino, desde la hora en que el equipo marcó "en camino", y con el tiempo acelerado (unas 20 veces; entre 40 s y 4 min) para que se vea en una demostración. Las pantallas lo avisan. No hay GPS real; para usar posiciones reales bastaría con reemplazar `_posicion_simulada`.
- **Privacidad:** quien recibe ve el destino exacto de su solicitud y recibe un aviso en pantalla (con vibración si el teléfono lo permite) cuando el equipo está a menos de 500 m. Quien dona ve solo el barrio, con un círculo aproximado de 300 m, sin direcciones, nombres ni teléfonos. El personal ve el centro del barrio.
- **Quien pidió la ayuda** ve el seguimiento como en una app de entregas: el mapa va primero (centro, destino, el equipo con su nombre acercándose, tiempo estimado y aviso de cercanía), luego su código y el recorrido. "Mis solicitudes" trae el enlace "Seguir en el mapa".
- **Quien dona** ve su ayuda como una **zona aproximada** (cuadrícula de unos 440 m, círculo de 500 m, con el avance en pasos de 10 %), nunca la ruta ni el punto exacto.
- **Control logístico:** la entidad y el administrador ven en `/recorrido` todas las entregas en marcha en un mapa, con su equipo, y una lista escrita (de dónde a dónde, cuánto falta). Cada equipo de entrega ve el mapa de sus entregas en "Mis entregas" (plegado; sin internet no se dibuja, pero el resto de la página sigue funcionando).
- **Centros de acopio:** al crear la cuenta hay que elegir el barrio donde queda, y de ahí sale su ubicación. Si un centro quedó sin ubicación, el mapa inventa el punto de salida y lo avisa.
- **Datos:** `/solicitudes/{id}/ruta.json` (solo su dueño), `/donaciones/ruta.json` (donante), `/recorrido/solicitudes/{id}/ruta.json` (personal), `/recorrido/entregas/ruta.json` (entidad y administrador) y `/entregas/ruta.json` (equipo de entrega), sin caché.

## Mapa (bloque 7)

`/mapa` (entidad, brigadista y administrador) dibuja los barrios con Leaflet 1.9.4, que viene incluido en `app/static/vendor/leaflet/` (sin CDN; licencia BSD en el mismo directorio). Los datos salen de `/mapa/datos.json`: un renglón por barrio, **sin datos de personas**.

- **Color:** el conmutador alterna entre prioridad y confianza. Las clases son quintiles de lo que se muestra, para que haya contraste aunque los valores se parezcan. Las rampas salen de los colores del logo y el número de cada círculo tiene contraste AA sobre su color.
- **Sin reportes:** el círculo va rayado y con borde de trazos, para no confundirlo con un barrio tranquilo.
- **El color no es lo único:** el número dentro del círculo es el lugar en la lista y el tamaño crece con la población. Cada círculo se enfoca con el teclado (Enter abre su ventana) y tiene una descripción completa para lectores de pantalla. La misma información está en la tabla de `/prioridades`, que el mapa enlaza.
- **Filtros:** por municipio y por aviso de información faltante. Un aviso en la página anuncia cuántos barrios se muestran.
- **Zoom:** los círculos se achican al alejar y los números aparecen al acercar.
- **Datos:** el JavaScript y los estilos de la página pesan unos 51 KB comprimidos, sin contar los mosaicos. Los mosaicos de fondo vienen de OpenStreetMap, así que sin internet se ven los círculos sobre un fondo vacío.
- **Límite:** los barrios solo tienen un punto (latitud y longitud), no un contorno; por eso son círculos y no zonas.

## Plan de asignación (bloque 6)

`/plan` (solo la entidad) propone qué lote entregar a cada solicitud verificada. **Hasta que la entidad lo aprueba no se reserva nada.**

- **Modelo (`app/optimizacion.py`):** programación lineal entera con SciPy (`milp`, HiGHS). Maximiza `suma (w/d + κ·u − λ·km) · x` con la cantidad de cada lote entregada a cada solicitud como variable entera. `w` = prioridad × (0,5 + 0,5 × confianza); `u` = urgencia de usar el lote por su vencimiento (primero en vencer, primero en salir); `km` = distancia del centro de acopio a la solicitud. Respeta el inventario, lo pedido, el tipo de recurso, el destino de las donaciones dirigidas y no usa lotes vencidos.
- **Equidad (θ):** cada solicitud de prioridad alta recibe al menos una fracción θ de lo que pide, sin pasar de su parte igual del inventario. Si no es posible, se calcula sin ella y se avisa.
- **Costo de la distancia:** se acota para que nunca haga que "no entregar" sea mejor que entregar.
- **Referencia voraz:** el plan se compara con una asignación sencilla (la más prioritaria primero) y sirve de respaldo si el solucionador falla o se pasa del tiempo (10 s).
- **Explicación:** cada línea dice la prioridad, la confianza, el vencimiento del lote, el centro y la distancia; el plan lista lo que queda sin cubrir y por qué.
- **Aprobar:** reserva el inventario y asigna un equipo con su código, por solicitud. La entidad puede cambiar el equipo de cada una o dejarla fuera. Si el inventario cambió desde que se calculó, esa solicitud se omite y se informa. Se muestran las 40 más prioritarias; las demás se aprueban con el equipo propuesto.
- **Entrega parcial:** si el inventario solo alcanza para una parte, se entrega esa parte y la solicitud vuelve a estar verificada con lo que falta.
- **Límite conocido:** la compatibilidad entre el tipo de recurso y el acceso del barrio (una lancha para un barrio aislado) no se modela porque los lotes no tienen ese dato. El plan solo avisa que el barrio está aislado.
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

## Municipios y barrios

El territorio son los **23 municipios del Atlántico y sus barrios**. Los nombres y las coordenadas de los barrios son reales: vienen de OpenStreetMap (© colaboradores de OpenStreetMap, licencia ODbL) y están en `data/barrios_atlantico.csv` (600 lugares: 542 barrios y 58 centros poblados). Se obtuvieron con `scripts/construir_barrios.py`, que consulta la API Overpass y asigna cada lugar al municipio que lo contiene.

- **Municipios sin barrios en OpenStreetMap:** donde no hay barrios mapeados (por ejemplo Sabanalarga, Campo de la Cruz o Suan) se usan los centros poblados, y se marcan como tales. Palmar de Varela, Sabanagrande y Suan solo tienen una unidad. Para afinar un municipio basta con agregar renglones al CSV.
- **Lo que NO es real:** cuántas viviendas tiene cada barrio. La cifra oficial es por municipio (proyección 2026); el reparto entre sus barrios es simulado, de modo que la suma de los barrios coincide con el municipio. Igual son simuladas la vulnerabilidad, la amenaza y el acceso de cada barrio.
- **Pantallas:** los formularios eligen primero el municipio y luego el barrio (sin JavaScript se ve la lista completa agrupada por municipio). `/prioridades` resume cada municipio (barrio más prioritario, promedio, avisos, solicitudes por atender) y se puede filtrar por uno. Los nombres de barrio se repiten entre municipios, así que se muestran siempre como "Barrio, Municipio".
- **Cambio desde sectores:** la versión anterior dividía cada municipio en "sectores" inventados. Al arrancar sobre una base de ese esquema, `app/migracion.py` los reemplaza por barrios, una sola vez: borra lo que dependía de ellos (reportes, solicitudes, puntajes, planes, entregas, donaciones, lotes y eventos) y conserva cuentas, perfiles de donante, centros de acopio, pesos y bitácora; a las cuentas y centros solo se les quita el sector.

## Datos simulados

Genera un escenario completo y reproducible (barrios reales con viviendas simuladas ancladas en las cifras municipales, un evento, usuarios, reportes, solicitudes, donaciones e inventario, todo ficticio):

```bash
uv run python -m app.cargas                                  # antes: las viviendas deben estar cargadas
uv run python -m app.simulacion --seed 42 --tipo inundacion  # terremoto | inundacion | vendaval | deslizamiento
```

**Renovar la demostración en producción:** con `REINICIAR_DEMO=true` en el servicio, al arrancar se genera de nuevo el escenario (semilla 42, inundación). **Conserva todas las cuentas reales**, su historial, los centros de acopio que administran y los pesos que cambiaron, y vuelve a ubicarlas en su barrio (buscado por municipio y nombre). **Se niega** (sin tumbar la aplicación) si esas cuentas ya hicieron algo: solicitudes, reportes, perfiles de donante, verificaciones, entregas, planes aprobados o movimientos de inventario, porque eso podría borrarse. Todo ocurre en una sola transacción: si algo falla, queda lo anterior. Es de un solo uso: hay que quitar la variable después.

Con la misma semilla se obtienen los mismos datos. Cada ejecución borra la simulación anterior (no toca las viviendas ni los barrios del archivo). La "verdad" del escenario (el daño real de cada barrio, los reportes falsos y las solicitudes duplicadas) queda en la tabla `bitacora` (acción `simulacion_verdad`) para medir después qué tan bien se detectan.

## Simulación del ciclo completo

`uv run python scripts/simular_pipeline.py --seed 42 --tipo inundacion` recorre de punta a punta el ciclo sobre un escenario nuevo, en una base temporal que no toca ninguna real: verificación en campo (con falsas que se cuelan), recepción de donaciones, plan optimizado, aprobación, entrega con código de un solo uso (códigos equivocados y reusos rechazados, incidencias) y revisión de la cadena de auditoría y del inventario. Imprime los conteos y los tiempos. Todo es simulado: sirve para comprobar que el ciclo cierra, no para medir resultados reales.

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
