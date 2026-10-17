# Análisis de experiencia de usuario de Resilis

17 de octubre de 2026 · versión del prototipo: commit `a2a92d3` · escenario: vendaval en Malambo

## 1. Qué se revisó y cómo

- **Alcance:** los 7 roles (solicitante, donante, brigadista, entidad, centro de acopio, equipo de entrega, administrador) y el visitante sin cuenta, unas 45 vistas.
- **Pantallas:** celular (320, 375 y 390 px de ancho) y computador (1100 px).
- **Método:**
  1. Recorrido de las tareas principales de cada rol con datos del escenario de Malambo.
  2. Medición automática de cada vista: alto en pantallas, cantidad de elementos interactivos, campos, objetivos táctiles pequeños, palabras y jerga.
  3. Revisión de los textos.
  4. Prueba de desplazamiento horizontal a 320 px.
  5. Revisión de accesibilidad con axe (ya hecha: sin fallas automáticas).
  6. Heurísticas de usabilidad de Nielsen, adaptadas a una emergencia: personas estresadas, celular, señal mala y poca práctica con aplicaciones.
- **Límites:** no hubo personas usuarias reales, ni lector de pantalla real, ni un Android real. Los datos son simulados. Lo que aquí se llama problema es una hipótesis hasta probarlo con personas (sección 6).
- **Gravedad:** **Crítico** (impide o frena la tarea principal), **Alto** (la hace mucho más difícil), **Medio** (molesta o confunde), **Bajo** (pulido).

## 2. Resumen

**Lo que ya funciona bien**

1. Formularios con frases cortas, etiquetas visibles y ayuda bajo el campo.
2. Inicios de solicitante, donante, centro de acopio y equipo de entrega con una o dos acciones grandes.
3. Recepción de donaciones: una tarjeta con la cantidad ya escrita y un solo botón.
4. Mis entregas: una tarjeta por entrega, con el código a la vista, un botón claro y funcionamiento sin conexión.
5. Recorrido por etapas con texto y símbolo, no solo color.
6. Plan en paquetes pequeños, con un botón grande por paquete.
7. Estados vacíos que explican qué hacer.
8. Los mapas tienen su equivalente en texto.
9. Sin fallas automáticas de accesibilidad en 25 páginas.

**Los ocho problemas que más pesan**

| # | Problema | Gravedad |
|---|---|---|
| B1 | **Verificar** es una página de 8,9 pantallas en celular, con 722 palabras y 17 campos. Verificar 10 solicitudes cuesta unos 30 toques. | Crítico |
| T2 | Las **tablas** son el patrón principal en celular: columnas apretadas, la acción queda fuera de pantalla y hay que desplazarse de lado. | Alto |
| T3 | **Reflow roto** a 320 px en dos páginas (Verificar y el detalle de un barrio): toda la página se desplaza de lado. Incumple WCAG 1.4.10. | Alto |
| T4 | Las **horas** de los listados y recorridos salen en UTC, 5 horas adelantadas respecto a Colombia. Los mapas usan la hora del dispositivo. | Alto |
| S1 | En **Mi solicitud**, con la ayuda en camino, lo importante (dónde viene y cuál es mi código) queda abajo. El estado se repite tres veces. | Alto |
| T1 | La **cabecera** ocupa de 111 a 198 px en celular (hasta 28 % de la pantalla) y el aviso de prototipo otros 64 px. | Alto |
| E2 | Un plan de 105 paquetes exige **105 aprobaciones**. | Alto |
| S2 | **Registrarse** pide 12 campos antes de poder pedir ayuda. | Alto |

## 3. Hallazgos por rol

### Solicitante (persona que pide ayuda)

| ID | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| S1 | En Mi solicitud el mapa empieza en la posición 673 de una pantalla de 812, el código en 1297 y el recorrido en 1522 (2,5 pantallas). Hay tres mensajes que dicen lo mismo: el estado, la frase "El equipo está cerca…" y una alerta roja. El aviso de simulación ocupa un bloque más. | Medición y captura a 375 px | Alto |
| S2 | El registro tiene 12 campos (5 obligatorios, y dos listas de municipio y barrio) más "Repita la contraseña", antes de llegar a "Pedir ayuda". Pedir ayuda suma 9 campos. En total, unos 21 campos y 6 toques. | Medición | Alto |
| S3 | El formulario no pregunta qué ni cuánto en concreto. La cantidad la calcula el sistema (personas × unidad): 4 personas dan "4 kits" para reparar un techo, lo que no tiene sentido. Solo la descripción libre dice la necesidad real. | Código y formulario | Medio |
| S4 | El inicio de quien ya pidió no muestra el estado de su pedido: solo el botón "Ver solicitudes". | Captura | Medio |
| S5 | El barrio se elige en una lista de 600 con filtro por municipio. Si el barrio de la persona no está en OpenStreetMap, no hay salida ("mi barrio no aparece" o usar la ubicación). | Formulario | Medio |
| S6 | 8 objetivos táctiles de menos de 40 px en Mi solicitud (resúmenes de etapas, zoom del mapa). | Medición | Bajo |

### Donante

| ID | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| D1 | El mapa y el aviso de simulación van antes que sus donaciones. No hay un resumen de impacto ("su ayuda llegó a 3 familias en 1 barrio"). Los textos usan "1 barrio(s)" y "3 entrega(s)". | Captura | Medio |
| D2 | Una cuenta con dos perfiles de donante vería una lista vacía (solo lee el primero). Es un caso raro, pero es un fallo silencioso. | Visto al preparar la prueba | Bajo |

### Brigadista

| ID | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| B1 | Verificar mezcla una tabla de solicitudes con una tarjeta por reporte (33 en el escenario), cada una con su nota y dos botones. Son 8,9 pantallas, 722 palabras y 17 campos. Verificar una solicitud lleva 3 toques (lista, detalle, botón) y desplazarse de lado para ver "Revisar". | Medición y captura | Crítico |
| B2 | En el inicio, "Verificar", su tarea principal, es la sexta tarjeta (posición 1179, 1,5 pantallas abajo). | Medición | Alto |
| B3 | Sin enlace para llamar a la persona ni para abrir su dirección en un mapa. | Revisión | Medio |

### Entidad coordinadora

| ID | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| E1 | El inicio tiene 8 tarjetas fijas en 2,5 pantallas. "Plan" y "Asignar" quedan al final. No resume la situación ("10 por verificar, 3 listas para el plan, 1 entrega en camino"). | Medición | Alto |
| E2 | Un plan de 574 solicitudes da 105 paquetes: 105 aprobaciones, una por una. | Prueba local | Alto |
| E3 | "Asignar entregas" (una a una) y "Plan" (por paquetes) hacen casi lo mismo. Hay dos caminos para una misma tarea. | Menú | Medio |
| E4 | Prioridades tiene 4,8 pantallas y 467 palabras (municipios, barrios y solicitudes, con tablas). Mapa y Prioridades repiten información. | Medición | Medio |
| E5 | Pesos usa "dimensión" y "aportes". | Textos | Medio |

### Centro de acopio

| ID | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| C1 | Recibir es un buen ejemplo: 1 toque con la cantidad prellenada. Inventario usa tablas y la palabra "lote". | Captura | Bajo |
| C2 | Sin centro asignado, la pantalla solo dice "pida al administrador": no hay acción. Desde Cuentas no se puede asignar un centro a una cuenta existente. | Pantalla | Medio |

### Equipo de entrega

| ID | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| Q1 | Con 3 entregas, la página tiene 2,9 pantallas y 406 palabras. No se ordena por cercanía y no hay llamar ni abrir en mapa. El mapa va plegado y necesita internet. | Medición y captura | Medio |
| Q2 | Reportar que no se pudo entregar lleva dos pasos ("No se pudo entregar" y "Registrar incidencia"). | Revisión | Bajo |

### Administrador

| ID | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| A1 | La lista de cuentas no tiene búsqueda ni filtro, ni forma de editar una cuenta. Crecerá. | Revisión | Medio |
| A2 | La auditoría usa "huella", y no explica para qué sirve la cadena. | Texto | Bajo |

### Visitante

El inicio sin cuenta es claro (qué es, para quién, dos botones). La barrera real es el registro largo (S2).

## 4. Hallazgos transversales

| ID | Hallazgo | Evidencia | Gravedad |
|---|---|---|---|
| T1 | **Cabecera:** el menú se parte en 3 o 4 filas (111 px para brigadista, 155 px para administrador, 198 px para entidad a 320 px de ancho), más el aviso de prototipo de 64 px. El contenido empieza entre 175 y 260 px. | Medición | Alto |
| T2 | **Tablas en celular:** Verificar, Asignar, Prioridades, Detalle de barrio, Inventario y Auditoría. La leyenda de la tabla se desborda y el contenido se corta. | Capturas | Alto |
| T3 | **Reflow:** a 320 px, la página de Verificar mide 421 px y la del detalle de un barrio 446 px de ancho de desplazamiento. La causa es el texto oculto para lectores de pantalla, posicionado dentro de la tabla. El arreglo es de una línea de CSS. | Medición | Alto |
| T4 | **Zona horaria:** las horas hechas por el servidor (recorrido, historiales, listas) salen en UTC, 5 horas adelante. Una entrega de las 11:38 p. m. de Colombia dice "04:38". Los mapas muestran la hora del dispositivo. | Código y capturas | Alto |
| T5 | **Porcentajes:** "Prioridad 81 %", "Confianza 42 %" aparecen en listas, mapa y detalle. Para quien decide con estrés no dicen qué hacer. | Textos | Medio |
| T6 | **Jerga:** "lote", "huella", "dimensión", "aportes", "confianza", "posición simulada". | Medición de textos | Medio |
| T7 | **El inicio no dice qué sigue.** Son tarjetas fijas, sin conteos ni "lo siguiente". | Capturas | Medio |
| T8 | **Nombres del menú:** "Recorrido" (panel) frente a "Cómo va" (una solicitud). "Asignar" frente a "Plan". Una entidad ve "Mis reportes". | Menú | Medio |
| T9 | **Mapas:** en /mapa, el mapa empieza en la posición 1193 (1,5 pantallas) tras 64 palabras de introducción y los filtros. Dependen de internet. | Medición | Medio |
| T10 | **Pluralización con paréntesis:** "entrega(s)", "barrio(s)", "solicitud(es)". Suena a formulario. | Textos | Bajo |
| T11 | **Aviso de prototipo** repetido en todas las pantallas. | Capturas | Bajo |

## 5. Tiempo y esfuerzo de las tareas principales

| Tarea | Hoy | Meta |
|---|---|---|
| Pedir ayuda por primera vez | ~21 campos, 6 toques | ≤ 10 campos |
| Ver dónde viene mi ayuda | 2 toques y bajar 1,2 pantallas | 1 toque desde el inicio |
| Verificar 10 solicitudes | ~30 toques | ≤ 12 (2 por solicitud) |
| Aprobar un plan de 105 paquetes | 105 aprobaciones | ≤ 10 |
| Confirmar una entrega (equipo) | 3 toques y 8 caracteres | igual (está bien) |
| Recibir una donación (acopio) | 1 toque | igual (está bien) |
| Registrar una donación | 8 campos, 1 pantalla y media | ≤ 5 campos |

## 6. Propuestas de mejora

Ordenadas por impacto y esfuerzo. Cada una dice qué problema resuelve.

### Ya (menos de un día cada una)

1. **Corregir el reflow** con `position: relative` en las tablas con desplazamiento (T3).
2. **Mostrar toda hora en hora de Colombia** y decirlo ("hora de Colombia"), en servidor y en mapas (T4).
3. **Cabecera compacta en celular:** un botón "Menú" que despliega los enlaces, o una barra inferior con 4 accesos. El aviso de prototipo pasa a una franja delgada (T1, T11).
4. **Inicio por tarea:** ordenar las tarjetas de cada rol por su tarea principal y poner arriba un resumen "Qué sigue" con conteos: "10 solicitudes por verificar", "su ayuda está en camino" (B2, E1, S4, T7).
5. **Etiquetas en vez de porcentajes:** Alta, Media y Baja para la prioridad, y "Conviene verificar" para la confianza baja, con el número como detalle (T5).
6. **Mapa primero en /mapa:** introducción de una línea, filtros plegados (T9).
7. **Textos:** sustituir "lote", "huella", "dimensión", "aportes"; cambiar "entrega(s)" por una función de plural (T6, T10).

### Después (1 a 3 días cada una)

8. **Mi solicitud al estilo de una app de entregas:** arriba una tarjeta con el estado en grande, "llega en unos 4 min", el código en grande y el nombre del equipo; el mapa debajo; el recorrido al final. Quitar los mensajes repetidos (S1).
9. **Cola de verificación para brigadistas:** una tarjeta a la vez, con "Verificada" y "No se pudo verificar" a la vista, nota solo si desmiente, y los reportes en otra página (B1, B3). Con enlace para llamar y abrir en el mapa.
10. **Tablas como tarjetas apiladas en celular** (Verificar, Asignar, Prioridades, Inventario) (T2).
11. **Plan:** "Aprobar los siguientes 10 paquetes" y filtro por municipio; unir "Asignar" dentro del Plan como modo manual (E2, E3).
12. **Registro mínimo:** nombre, teléfono, contraseña y consentimiento. El barrio se pide al pedir ayuda. Sin "repita la contraseña" (con "mostrar contraseña") (S2).
13. **Pedir ayuda más concreto:** según el tipo, casillas de qué se necesita (por ejemplo, materiales para el techo) y una cantidad con sentido (S3).

### Más adelante (requieren decisiones)

14. **Ubicación opcional con GPS** y la opción "mi barrio no aparece" (S5).
15. **Equipo de entrega:** ordenar por cercanía, llamar, abrir la ruta en el mapa, y dos toques menos para una incidencia (Q1, Q2).
16. **Resumen de impacto para donantes** (D1).
17. **Cuentas:** buscador, edición y asignación de centro de acopio a una cuenta existente (A1, C2).
18. **Pruebas con lector de pantalla** y un modo de letra grande y alto contraste.

## 6 bis. Estado: mejoras rápidas hechas (17 de octubre de 2026)

Los siete puntos de la ola "Ya" están implementados, con pruebas (292 en total) y revisión de accesibilidad sin fallas:

| # | Mejora | Resultado medido |
|---|---|---|
| 1 | Reflow corregido (`position: relative` en las tablas con desplazamiento) | A 320 px, Verificar y el detalle de un barrio ya no se desplazan de lado (317 px de ancho de desplazamiento, antes 421 y 446) |
| 2 | Todas las horas en hora de Colombia, y el pie lo dice | Una entrega de las 23:38 ya no aparece como "04:38"; los mapas usan la misma hora |
| 3 | Cabecera compacta en celular: logo, "Menú" y "Salir" en una fila; los enlaces se despliegan debajo, uno por renglón (48 px). Aviso de prototipo de una línea | Cabecera de entidad de 198 px a 54 px; sin JavaScript el menú sigue completo |
| 4 | "Qué sigue" arriba del inicio de cada rol, con conteos y un botón directo, y tarjetas reordenadas por tarea principal | Verificar y Plan pasan de la 5.ª posición a la 1.ª y 2.ª; la entidad ve "7 solicitudes por verificar" sin entrar a ninguna página |
| 5 | Prioridad y confianza en palabras (Alta, Media, Baja) con el porcentaje al lado, y "Conviene verificar" si la confianza es baja | En listas, detalle de barrio, asignación, recorrido y globo del mapa |
| 6 | Mapa primero: una línea de introducción, el mapa y los filtros plegados | El mapa pasa de la posición 1193 a unos 355 |
| 7 | Textos: "lote", "dimensión" y "huella" sustituidos; plurales sin paréntesis ("1 entrega", "3 entregas") | Una prueba revisa que no queden plurales con paréntesis |

También está hecho el punto 9, la **cola de verificación para brigadistas**: la lista son tarjetas (sin tablas), "Verificar la siguiente solicitud" lleva a la más urgente, cada tarjeta trae teléfono, mapa y los botones "Verificada" / "No se pudo verificar" fijos al pie en el celular, y al decidir pasa sola a la siguiente (un toque por solicitud). Los reportes de daños se revisan aparte. Y se añadió un **juego de iconos propios** (SVG en línea, sin conexión) en el menú, las tarjetas de inicio, "Qué sigue", los botones clave, las etapas del recorrido y los tipos de necesidad; son decorativos y siempre van con texto. Con ello hay 310 pruebas y la revisión de accesibilidad sigue sin fallas.

El punto 8, **Mi solicitud al estilo de una app de entregas**, también está hecho: arriba una tarjeta con el estado en grande, la frase de llegada ("va en camino: faltan X km, llega en unos N min", que se actualiza sola), el código y el equipo; el mapa va después y el recorrido al final. Se quitó la repetición del estado y la alerta roja aparte (solo queda un aviso vivo para lectores de pantalla). Hay 312 pruebas.

Siguen pendientes los puntos 10 a 18 (tablas como tarjetas en Asignar, Prioridades e Inventario, "aprobar los siguientes N paquetes" y el registro mínimo, entre otros).

## 7. Cómo comprobar que mejoró

Pruebas de uso con 5 personas por rol que más pesan (solicitante, brigadista, equipo de entrega) y 2 a 3 de la entidad, con tareas guionadas:

- Pedir ayuda y encontrar su código.
- Verificar 5 solicitudes.
- Aprobar un paquete y marcar una entrega.

**Se mide:** éxito de la tarea, tiempo, toques, errores y la escala SUS (satisfacción). **Meta mínima:** 4 de cada 5 completan cada tarea sin ayuda, y verificar 5 solicitudes toma menos de 3 minutos en celular.
