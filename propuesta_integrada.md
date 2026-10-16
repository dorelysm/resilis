# Resilis: decisiones inteligentes, recursos optimizados, vidas protegidas

**Reto:** Optimización y priorización de recursos y esfuerzos en la post-emergencia
**Ámbito:** departamento del Atlántico, Colombia. Desastres naturales en general (inundaciones, vendavales y lluvias intensas, deslizamientos, sismos). El sistema es independiente del tipo de evento: cambian los pesos y los escenarios, no la arquitectura.
**Escenario de ejemplo (formulario):** un evento que afecte a varias comunidades de Malambo y Soledad.
**Versión:** 1.1, 16 de octubre de 2026. El detalle técnico está en `Requerimientos/` y las decisiones en `ideas_consolidadas.md`.

---

## 1. Problema

Tras un evento catastrófico, la demanda de asistencia desborda a los equipos de respuesta. Hay cortes de comunicación, rutas bloqueadas e información fragmentada. Las autoridades deben decidir en minutos a quién atender primero, dónde concentrar esfuerzos y qué recursos enviar, con datos incompletos y sin saber cuánto fiarse de ellos. Después, no hay forma de saber si la ayuda llegó a quien la pidió.

## 2. Propuesta

Un **sistema que registra las donaciones, prioriza las necesidades y optimiza los recursos humanitarios**, con seguimiento de la ayuda hasta la entrega. Combina seis piezas:

1. **Línea base previa al desastre:** población, viviendas, infraestructura y vulnerabilidad por sector, con datos proyectados y **datos oficiales del Estado** sobre eventos y daños en catástrofes. Permite recomendar desde la hora cero.
2. **Reportes de daños y solicitudes de ayuda** de usuarios identificados: ciudadanos, brigadistas, organizaciones y entidades. No hay reportes anónimos.
3. **Modelo de priorización explicable** en dos niveles: el *sector* decide dónde concentrar esfuerzos y la *solicitud* decide a quién atender dentro del sector. Muestra qué tan confiable es cada dato y dónde falta información.
4. **Registro de donaciones e inventario:** los donantes registran lo que ofrecen, los centros de acopio verifican lo recibido y llevan el inventario por lote, y cada donación se puede rastrear hasta su destino sin mostrar datos personales de los beneficiarios. Las donaciones monetarias solo se registran; el sistema no procesa pagos.
5. **Optimización del reparto:** con el inventario y las solicitudes verificadas, un modelo de programación lineal entera propone qué lote entregar a quién para cubrir la mayor necesidad ponderada por prioridad y confianza, con criterio FEFO, donaciones dirigidas y equidad. La entidad aprueba el plan y siempre se explica.
6. **Seguimiento hasta la entrega, como en una aplicación de pedidos:** cada solicitud pasa por estados visibles para el solicitante, y al asignarla se genera un **código de un solo uso** que el equipo de entrega debe recibir para confirmar la entrega, incluso sin conexión.

**Diferenciador:** no solo prioriza. Dice cuánto fiarse de cada dato, señala los huecos, permite verificar y comprueba que la ayuda llegó a quien la pidió.

## 3. Usuarios y beneficiarios

- **Solicitante:** persona de la comunidad que reporta daños o pide ayuda. Si es vulnerable (discapacidad, adulto mayor, menor, embarazo, enfermedad crónica), describe su situación y su necesidad específica.
- **Brigadista:** reporta, verifica y puede entregar. Su reporte pesa más que el de una persona natural.
- **Equipo de entrega:** brigadistas y organizaciones registradas. Ven solo las entregas que les asignan.
- **Entidad coordinadora:** gestión del riesgo del distrito y los municipios, Defensa Civil, Cruz Roja. Ven todo y ajustan los pesos.
- **Donante:** registra donaciones, puede dirigirlas y ve su estado y destino.
- **Centro de acopio:** organización registrada que recibe y verifica donaciones y gestiona el inventario.
- **Administrador:** gestiona cuentas y parámetros. No ve los datos de vulnerabilidad.

## 4. Cómo funciona

### 4.1 Antes del desastre
Se consolida por sector la población, las viviendas, la infraestructura, la amenaza y la vulnerabilidad, a partir de proyecciones y de archivos abiertos de las entidades del Estado. Los eventos históricos oficiales también sirven para calibrar los escenarios simulados.

### 4.2 Durante la post-emergencia
- Los usuarios envían reportes de daños y solicitudes desde el celular. Quien no tiene celular recibe una ficha en papel; si no hay electricidad, un brigadista digitaliza el reporte después.
- Un brigadista o una entidad **verifica** la identidad y la necesidad antes de asignar.
- Los reportes oficiales entran como una fuente propia, con su peso.

### 4.3 Modelo
Un **índice multicriterio TOPSIS** con pesos ajustables, para sectores y para solicitudes.

| Dimensión de sector | Qué mide |
|---|---|
| Gravedad de la afectación | Daño a viviendas e infraestructura |
| Urgencia de la atención | Riesgo para la vida y tiempo sin atención |
| Personas expuestas y necesidades especiales | Población afectada y grupos vulnerables |
| Accesibilidad de las rutas | Estado del acceso. Se marca como alerta y **no baja la prioridad** |
| Recursos disponibles | Brecha entre necesidad y recursos presentes |
| Confiabilidad de la información | Se calcula aparte como confianza |

- **Confianza** por reporte, solicitud y sector, según la fuente, la verificación, la vigencia y la corroboración.
- **Alertas** de información faltante: sin reportes, desactualizados, de baja confianza o contradictorios.
- **Aprendizaje no supervisado** para detectar duplicados y reportes sospechosos, y de forma opcional agrupar sectores en perfiles.
- **Optimización de la asignación:** programación lineal entera con SciPy (`milp`) que reparte el inventario entre las solicitudes verificadas. Una asignación voraz sirve de comparación y de respaldo.

### 4.4 Código de entrega y registro
- Código aleatorio de un solo uso, atado al equipo asignado. El servidor guarda solo su huella con sal, por lo que el equipo puede validarlo **sin conexión**.
- Los eventos de cada solicitud se guardan en un **registro encadenado por hash**, sin datos personales, que permite auditar. Se usa en lugar de una cadena de bloques propiamente dicha (decisión confirmada por el equipo).

### 4.5 Lo que ve el usuario
Un mapa con la prioridad y la confianza, listas priorizadas de sectores y solicitudes, el detalle que explica cada posición, el estado de cada solicitud y los escenarios simulados de varios tipos de desastre.

## 5. Viabilidad técnica

- **Tecnología madura y abierta:** Python, FastAPI, PostgreSQL, Leaflet y Railway. No requiere hardware especial.
- **Funciona con datos incompletos:** la línea base cubre la hora cero y el sistema degrada con elegancia.
- **Explicable:** un índice multicriterio es comprensible para quien decide.
- **Prototipo:** plan de 12 horas con un flujo de punta a punta (solicitud, verificación, asignación, código, entrega) sobre datos simulados con identidades ficticias, anclados en las proyecciones de viviendas del Atlántico.

## 6. Limitaciones que reconocemos

- **Los datos del prototipo son simulados.** La validación es de la metodología, no una medida de precisión en un desastre real.
- **Fraude:** no hay una base oficial para verificar identidades. Defensas: verificación en campo, detección de duplicados y código atado a un equipo.
- **Privacidad:** ahora hay datos personales y sensibles. Se aplica el principio de datos mínimos, consentimiento expreso y acceso por rol (Ley 1581 de 2012). Falta una revisión jurídica antes de un uso real.
- **Sin conexión:** si dos equipos sin red reclaman el mismo código en lugares distintos no se puede evitar a distancia; por eso el código queda atado a un equipo.
- **Pesos y fórmulas** del modelo son provisionales hasta validarlos con un experto.
- **Datos por barrio y fuentes oficiales** de eventos y daños siguen por conseguir e identificar.

## 7. Impacto y sustentabilidad

- **Social:** atender primero a quienes más lo necesitan, comprobar que la ayuda llegó y rendir cuentas.
- **Operativo:** evitar duplicar esfuerzos y concentrar recursos escasos donde rinden más.
- **Sustentabilidad:** software abierto, replicable en otras ciudades, financiable por las entidades de gestión del riesgo y la cooperación humanitaria. La línea base sirve también en tiempos normales para prevención.

## 8. Ruta de implementación

1. **Piloto:** prototipo con datos simulados para el Atlántico.
2. **Validación:** pruebas con una entidad de gestión del riesgo, ajuste de pesos, revisión jurídica y revisión de la interfaz.
3. **Ampliación:** datos reales por barrio, integración con fuentes oficiales y verificación de identidad.
4. **Escalamiento:** otros municipios del Atlántico y otras ciudades de Latinoamérica.

## 9. Pendientes del equipo

Ver la sección de pendientes en `ideas_consolidadas.md`.
