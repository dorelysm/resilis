# Ideas consolidadas: Resilis

**Proyecto:** Resilis. Sistema inteligente de resiliencia y priorización de recursos humanitarios en situaciones de post-emergencia.
**Lema:** "Decisiones inteligentes, recursos optimizados, vidas protegidas". (Descartado: "Inteligencia que conecta, innovación que salva vidas", de `ideas.md`.)
**Reto:** Optimización y priorización de recursos y esfuerzos en la post-emergencia ([reto.md](reto.md)).

Este documento reúne `propuesta.md`, `ideas.md` y las decisiones tomadas en la conversación. Los originales no se modificaron.

---

## 1. Qué es el sistema

Una herramienta de apoyo a la decisión para las autoridades y organismos que coordinan la respuesta a un desastre. Les ayuda a decidir con rapidez a quién atender primero, dónde concentrar esfuerzos y qué recursos asignar, y justifica cada decisión.

Piezas principales:
- **Mapa** para visualizar afectaciones.
- **Modelo matemático** para priorizar necesidades.
- **Base de datos** para ubicar a las personas y conocer la vulnerabilidad de cada zona.
- **Entrevistas post-emergencia** que alimentan el modelo con las necesidades del momento.
- **Análisis de datos y machine learning** para predecir necesidades y mejorar la asignación.

## 2. Datos que necesita

### Base (antes del desastre)
- Datos demográficos, dirección de vivienda, trabajo y otros necesarios para ubicar a las personas.
- Datos de infraestructura y vulnerabilidad de las zonas.
- Datos históricos de desastres.

### Durante la post-emergencia
- Entrevistas con las personas sobre sus necesidades del momento: alimentación, vivienda, reubicación, salud.
- Datos para optimizar la distribución de recursos y esfuerzos.

### Fuentes complementarias
Satélite, drones, redes sociales, sensores, geolocalización, clima, geología, hidrología, sismología, vulcanología y meteorología.

**Decisión de alcance:** estas fuentes pasan a ser **opcionales y de escalabilidad futura**. El reto parte de comunicaciones cortadas e información fragmentada, así que el sistema no puede depender de ellas para operar. Sirven para subir o bajar la confianza de un sector.

### Datos reales disponibles hoy
- `REGISTRO_DE_PROPIEDAD_HORIZONTAL_BARRANQUILLA`: unas 2.400 edificaciones con dirección, barrio y localidad. Es de Barranquilla, fuera del escenario de ejemplo; sirve como modelo de formato.
- `Estimación del número total de viviendas 2018-2035`: por municipio del Atlántico.
- **Límite:** el registro no incluye asentamientos informales, que suelen ser los más vulnerables.

## 3. Dimensiones de priorización

1. Gravedad de la afectación.
2. Urgencia de la atención.
3. Personas expuestas y necesidades especiales.
4. Accesibilidad de las rutas.
5. Recursos humanitarios disponibles.
6. Confiabilidad de la información recibida.

## 4. Lo que el sistema debe permitir

- Tomar decisiones informadas basadas en datos.
- Señalar la falta de información.
- Permitir la verificación de la información.
- Mostrar la confianza en la información recibida.
- Generar escenarios de posibles afectaciones.

**Diferenciador:** no solo prioriza. Dice cuánto fiarse de cada dato, señala los huecos, permite verificar y da seguimiento a cada solicitud hasta la entrega. Un reporte sin confirmar pesa menos que uno confirmado por una brigada.

## 5. Modelo: dos capas que se complementan

| Capa | Papel | Características |
|---|---|---|
| **Índice multicriterio** (tipo AHP o TOPSIS) | Da la prioridad por sector | Explicable, con pesos ajustables por la autoridad. La decisión sigue siendo humana |
| **Aprendizaje no supervisado** | Descubre perfiles de sectores, detecta anomalías y alimenta el nivel de confianza | Se puede probar con datos simulados |
| **Aprendizaje supervisado** (segunda fase) | Predice necesidades de personas e infraestructura | Requiere datos reales acumulados, que hoy no existen |

La propuesta original planteaba machine learning como núcleo. Se ajustó porque para entrenarlo no hay datos hoy, y el prototipo no debe depender de eso.

## 6. Validación con datos simulados y aprendizaje no supervisado

**Estado:** idea aclarada, sin implementar.

### Decisión
Es viable simular datos para probar un modelo no supervisado. Sirve como **validación sintética de la metodología**, no como validación del modelo en un desastre real.

### Qué demuestra
- **Pipeline de punta a punta:** entra la data, se procesa y sale la agrupación. Respalda la viabilidad técnica.
- **Recuperación de estructura conocida:** se siembran grupos de sectores (por ejemplo crítico aislado, muchos vulnerables con ruta buena, leve) y se mide si el algoritmo los reencuentra (ARI, silhouette).
- **Robustez ante datos imperfectos:** se simulan ruido, valores faltantes y reportes contradictorios, y se mide cuánto se degrada el resultado. Conecta con la confianza y los datos faltantes.
- **Detección de anomalías:** un reporte que no encaja con sus vecinos es una señal de posible dato falso.

### Qué NO demuestra
- Que el modelo funcione en un desastre real: los datos salen de nuestros supuestos, así que el argumento es circular.
- Que un grupo signifique prioridad: el no supervisado agrupa por similitud y alguien debe interpretar qué grupo es más urgente.

**Cómo comunicarlo:** en el reporte y el video decir "validación sintética de la metodología". No presentarlo como evidencia de precisión.

### Cómo hacerlo creíble
1. **Anclar lo simulado en datos reales.** Usar las proyecciones de viviendas del Atlántico (Malambo y Soledad) y, cuando se consigan, datos de barrios; simular solo lo que no existe: daños y necesidades.
2. **Basar las distribuciones en literatura o datos abiertos** (curvas de daño por tipo de vivienda, reportes históricos de vendavales, lluvias e inundaciones en el Atlántico). Citarlo en `referencias.bib`.
3. **Variar los supuestos.** Generar varios escenarios y comprobar que las conclusiones no dependen de un número en particular.

### Algoritmos considerados
| Algoritmo | Uso |
|---|---|
| K-means / GMM | Agrupar sectores en perfiles. GMM entrega probabilidades de pertenencia, útil para la confianza |
| DBSCAN | Zonas críticas espaciales |
| Isolation Forest / LOF | Reportes sospechosos o anómalos |
| PCA / UMAP | Visualizar los grupos |

## 7. Seguimiento de la ayuda (cambio de alcance)

**Estado:** decidido el 16 de octubre de 2026. Detalle en `Requerimientos/` (versión 1.1).

La idea pasa de priorizar sectores a **dar seguimiento a cada persona que pide ayuda hasta que la recibe**, con una lógica parecida a una aplicación de pedidos.

### Qué cambia
- **Identificación:** cada solicitante tiene un usuario. Obligatorios: nombre, teléfono y sector. El documento es opcional, y obligatorio solo para entregas de mayor valor (por definir qué significa "mayor valor").
- **Vulnerabilidad:** si la persona es vulnerable, se registra el tipo y una descripción de la situación, con consentimiento expreso. Sirve para dirigir el recurso específico que necesita.
- **Sin reportes anónimos:** todo reporte y toda solicitud se asocian a un usuario registrado.
- **Roles:** solicitante, brigadista, equipo de entrega (brigadistas y organizaciones registradas), entidad coordinadora y administrador.
- **Estados de una solicitud:** registrada, verificada, asignada, en camino, entregada, cerrada, con incidencias.
- **Código de entrega:** se genera al asignar la solicitud. El equipo de entrega debe recibirlo de la persona para confirmar la entrega. Funciona **sin conexión** y es de un solo uso, atado al equipo asignado.
- **Dos niveles de priorización:** el sector decide *dónde concentrar esfuerzos*; la solicitud decide *a quién atender dentro del sector*.
- **Datos oficiales del Estado:** se incorporan archivos abiertos de eventos y reportes de daños en catástrofes, para completar la línea base, calibrar la simulación y mostrar reportes oficiales como una fuente propia. Las fuentes concretas están por identificar.

### Sobre "código blockchain"
Se propone, en su lugar, un **código aleatorio de un solo uso** (el servidor guarda solo su huella con sal) y un **registro de eventos encadenado por hash**, sin red distribuida. Razones: el sistema ya tiene un coordinador de confianza, debe funcionar sin conexión, una cadena pública guardaría datos de forma inmutable y chocaría con el derecho a corregir o suprimir datos (Ley 1581 de 2012), y es mucho más sencillo de construir en 12 horas. **Confirmado por el equipo.**

### Riesgos conocidos
- **Fraude:** sin una base oficial de identidad, alguien puede pedir ayuda con una identidad falsa. Defensas: verificación en campo, detección de duplicados y código atado a un equipo.
- **Dos equipos sin conexión** podrían reclamar el mismo código; por eso queda atado a un solo equipo.
- **Privacidad:** ahora hay datos personales y sensibles. El prototipo usa identidades ficticias y se necesita revisión jurídica antes de un uso real.
- **Tiempo:** el alcance creció. Se recortaron a opcionales la agrupación en perfiles y los escenarios "qué pasaría si"; el resto se hace en versión mínima.

### Tres funciones centrales (ajuste de alcance)
Decidido el 16 de octubre de 2026. La solución debe:
1. **Registrar las donaciones:** donantes, donaciones en especie y monetarias (solo registro, sin procesar pagos), recepción verificada en centros de acopio, inventario por lote y trazabilidad hasta el destino. El donante ve el estado y el destino de lo que dio, sin datos personales de los beneficiarios. Puede dirigir su donación.
2. **Priorizar las necesidades:** sectores y solicitudes individuales, con confianza y alertas de información faltante.
3. **Optimizar los recursos humanitarios:** un modelo de programación lineal entera reparte los lotes del inventario entre las solicitudes verificadas para cubrir la mayor necesidad ponderada por prioridad y confianza, con FEFO (primero en vencer, primero en salir), donaciones dirigidas, equidad y costo de transporte. La entidad aprueba el plan, y siempre se explica. Una asignación voraz sirve de comparación y de respaldo.

Nuevos roles: **donante** y **centro de acopio**. Parámetros del modelo (pesos, `kappa`, `lambda`, equidad) provisionales.

---

## 8. Decisiones tomadas

- El sistema funciona con **línea base previa** y se actualiza con reportes, para operar en la hora cero.
- Las fuentes complementarias son **opcionales**.
- El núcleo es el **índice multicriterio explicable**. El machine learning lo complementa.
- Ámbito: **departamento del Atlántico, desastres naturales en general**. El sistema no depende del tipo de evento; cambian los pesos y los escenarios.
- Escenario de ejemplo (formulario): **vendavales o lluvias intensas en Malambo y Soledad**.
- La validación con datos simulados se presenta como **validación de la metodología**.
- Lema: **"Decisiones inteligentes, recursos optimizados, vidas protegidas"**.
- Pesos: un perfil general fijo y ajustable. Accesibilidad como alerta, sin penalizar. Sin cifras de rendimiento.
- **Seguimiento de cada solicitud hasta la entrega**, con usuarios identificados, sin reportes anónimos y con código de entrega de un solo uso que funciona sin conexión (sección 7).
- Entregan brigadistas y organizaciones registradas.
- Se incorporan **datos oficiales del Estado** sobre eventos y daños.

## 9. Pendientes

- [x] Lema elegido.
- [ ] Confirmar el nombre Resilis.
- [x] Ámbito y escenario definidos.
- [x] Problemática y demás secciones de `formulario.md` redactadas dentro de sus límites.
- [x] `referencias.bib` con 24 referencias preseleccionadas (falta leerlas y completar 3 DOI).
- [x] Documento de requerimientos en LaTeX, versión 1.2 (`Requerimientos/`), con donaciones y optimización.
- [ ] Confirmar: donaciones monetarias solo como registro, y si el donante puede ocultar su nombre en vistas públicas.
- [ ] Definir quién gestiona los centros de acopio.
- [ ] Conseguir datos de barrios y viviendas del Atlántico.
- [ ] Identificar las fuentes oficiales de eventos y daños (UNGRD, IDEAM, Servicio Geológico Colombiano, DANE, datos abiertos).
- [x] Confirmado: código de un solo uso con registro encadenado por hash, sin cadena de bloques real.
- [ ] Definir qué es una entrega "de mayor valor", la vigencia del código y la política de conservación de datos.
- [ ] Revisión jurídica del manejo de datos personales y sensibles.
- [ ] Validar con al menos un actor de gestión del riesgo.
- [ ] Construir el prototipo (plan de 12 horas en el documento de requerimientos).
- [ ] Guion del video de 2 minutos y reporte de sustentabilidad e impacto social. (`Entregables/Reporte_Pautado_Rally_2026.docx` está vacío; se ignora.)

---

## Documentos relacionados
- Propuesta desarrollada: [propuesta_integrada.md](propuesta_integrada.md)
- Reto: [reto.md](reto.md)
