DESCRIPCIÓN DE LA PROBLEMÁTICA (1250 caracteres)
Describa brevemente la problemática elegida. ¿Cuáles pueden ser las principales causas? ¿Cuál es el verdadero problema a resolver? 
Tras un desastre natural (inundación, vendaval, sismo o deslizamiento), las autoridades de gestión del riesgo del Atlántico no saben con rapidez qué comunidades están más afectadas, qué necesitan primero ni dónde enviar recursos limitados. Un evento puede golpear varios municipios a la vez, como Malambo y Soledad, y desbordar a los equipos de respuesta.

El verdadero problema no es solo la falta de recursos: es convertir información dispersa, incompleta y cambiante en decisiones rápidas y justificadas, sin saber qué tan confiable es cada dato, y después garantizar que la ayuda llegue a quien la pidió. Entre las causas están la ausencia de datos previos consolidados por barrio, las comunicaciones interrumpidas, los reportes sin formato común ni verificación, y la poca coordinación entre entidades.

Las consecuencias son retrasos en la ayuda, esfuerzos duplicados, ayudas que no se sabe si llegaron y comunidades vulnerables o aisladas sin atención prioritaria.

Se necesita un mecanismo accesible y económico que organice la información, priorice las necesidades, dé seguimiento a cada solicitud y funcione con baja conectividad.



DESCRIPCIÓN DE LA SOLUCIÓN (1250 caracteres)
Describa brevemente el producto/servicio y por qué lo considera una solución a la problemática elegida. ¿Por qué esta propuesta es una buena solución al problema? ¿Por qué se diferencia de otras propuestas existentes? Describa brevemente la tecnología seleccionada, el funcionamiento, las necesidades para su implementación, entre otras.
Resilis es una aplicación web, usable desde el celular, que ayuda a decidir a quién atender primero tras un desastre y comprueba que la ayuda llegó. Un brigadista o una entidad verifica cada solicitud desde una cola, una tarjeta a la vez. Un índice multicriterio (TOPSIS) calcula la prioridad de 600 barrios de 23 municipios del Atlántico y de cada solicitud, con la confianza del dato, y la explica. Un mapa muestra prioridad, confianza y necesidades por barrio, y alertas señalan dónde falta información.

Los donantes registran lo que ofrecen y los centros de acopio confirman lo recibido y llevan el inventario. Con él y las solicitudes verificadas, un modelo de optimización arma un plan que cubre la mayor necesidad. La entidad lo aprueba por paquetes de hasta 6 entregas; hasta entonces no se reserva nada.

Al aprobar se genera un código de un solo uso que el equipo debe recibir para confirmar la entrega, incluso sin conexión. Quien pidió sigue su ayuda en un mapa; el donante ve por dónde va su donación sin datos de quien recibe. Cada paso queda en un registro encadenado por hash.

Se diferencia porque dice cuánto fiarse de cada dato y comprueba la entrega. Usa Python, PostgreSQL, SciPy y Leaflet en Railway, software abierto.


IMPACTO (1000 caracteres)
Describa brevemente el impacto social y/o ambiental que genera la propuesta de solución.
Impacto social: la ayuda llega primero a quienes más la necesitan y se puede comprobar que llegó. Cada persona sabe en qué estado está su solicitud y por dónde viene su ayuda. El código de entrega evita que la ayuda se entregue a quien no corresponde o se cobre dos veces. Las personas vulnerables (con discapacidad, adultos mayores, menores) describen su situación y su necesidad específica, como un medicamento o una silla de ruedas. Los barrios aislados no pierden posición por ser difíciles de alcanzar: su prioridad no baja y se marcan como alerta. Al optimizar el reparto del inventario se cubre más necesidad con los mismos recursos, se evitan esfuerzos duplicados y se puede rendir cuentas.

Impacto ambiental: al concentrar los recursos donde hacen falta y agrupar las entregas por municipio se reducen los desplazamientos innecesarios y el desperdicio de suministros: lo que vence antes sale primero. El sistema consume pocos datos y funciona en la nube con software abierto.


INNOVACIÓN (1000 caracteres)
Fundamente brevemente por qué considera que esta propuesta representa una solución innovadora a la problemática seleccionada.
La priorización multicriterio en desastres está bien estudiada, pero en nuestra revisión en Scopus casi no aparecen trabajos que incorporen la confiabilidad del dato dentro de la decisión. Resilis la hace parte central: cada reporte y solicitud tiene una confianza según quién la envía, si fue verificada, qué tan reciente es y si otros la confirman. El sistema señala dónde falta información y no la confunde con ausencia de problema.

Además lleva la lógica de seguimiento de una aplicación de pedidos a la ayuda humanitaria: estados visibles y un mapa de la entrega para quien pidió, y un código de un solo uso, verificable sin conexión, que garantiza que la ayuda llegue a quien la pidió. Une en una plataforma el registro de donaciones, la priorización de necesidades y la optimización del reparto. Combina datos oficiales del Estado con reportes ciudadanos y de brigadistas. Es explicable, de bajo consumo de datos, accesible (WCAG 2.2 AA) y auditable.


PRE FACTIBILIDAD ECONÓMICA, SOCIAL Y SUSTENTABILIDAD AMBIENTAL (1500 caracteres)
Describa brevemente las razones que hacen de esta propuesta una propuesta sostenible en el tiempo. Fundamente por qué considera que esta propuesta es presupuestariamente abordable, por qué es viable o aceptable socialmente 
Económica: el prototipo se construye con software abierto y se aloja en la nube, sin licencias ni equipos especializados. Los costos de operación son bajos: hospedaje, mantenimiento y capacitación de brigadistas y organizaciones. Podrían financiarse con las oficinas de gestión del riesgo de municipios y departamento y con cooperación humanitaria. Al ser abierto, otras ciudades pueden replicarlo sin pagar licencias.

Social: se usa desde el celular que ya tiene la gente, con lenguaje sencillo y accesibilidad WCAG 2.2 AA. Quien no tiene celular a mano puede imprimir una ficha con su código de entrega. Para dar seguimiento hay que identificar a cada solicitante, por eso se piden solo los datos necesarios: nombre, teléfono y barrio (este último solo si pide ayuda); el documento solo para entregas de mayor valor. Los datos de vulnerabilidad se piden con consentimiento expreso y cada rol ve solo lo que necesita, en línea con la Ley 1581 de 2012. El registro de auditoría no contiene datos personales.

Ambiental: bajo consumo de datos y menos desplazamientos innecesarios de ayuda.

Límites: el prototipo usa datos simulados con identidades ficticias, y la ruta del equipo en el mapa es simulada. Falta conseguir datos oficiales por barrio, revisar jurídicamente el manejo de datos personales, validar los pesos con una entidad de gestión del riesgo y agregar la detección automática de duplicados y reportes sospechosos.


PROPUESTAS QUE DESCARTARON
Enumere, en caso de haber descartado ideas, las diferentes propuestas que han analizado hasta elegir la actual y mencione brevemente el porque.
1. Basar el sistema en satélites, drones, redes sociales y sensores. Se dejó como mejora futura y opcional: el reto parte de comunicaciones caídas y el sistema debe funcionar sin depender de ellas.
2. Limitarse a un solo desastre y zona (inundación en Barranquilla; vendavales en Malambo y Soledad). Se amplió a desastres naturales del Atlántico, porque el sistema no depende del tipo de evento: solo cambian los pesos y los escenarios.
3. Un modelo opaco que entregue solo un resultado. Se prefirió un índice multicriterio explicable, para que la autoridad entienda y ajuste la decisión.
4. Bajar la prioridad de los barrios de difícil acceso. Se descartó para no dejar atrás a las comunidades más aisladas; su prioridad no baja y se tratan como alerta.
5. Reportes anónimos. Se descartaron porque no permiten dar seguimiento ni verificar; todo reporte y solicitud se asocia a un usuario registrado.
6. Dividir el territorio en sectores. Se cambió por los municipios y sus barrios, que la gente reconoce y que permiten ubicar con más precisión dónde está la necesidad.
7. Una cadena de bloques (blockchain) para la trazabilidad. Se prefirió un registro encadenado por hash en la base de datos: detecta cualquier alteración con menos complejidad y costo.
8. Aprobar de una vez un plan con cientos de entregas. Era demasiada información para una persona; el plan se divide en paquetes de hasta 6 entregas del mismo municipio, que se revisan y aprueban de a uno o varios.


REFERENCIAS
Escriba aquí todas las fuentes de información que consultaron y de las que obtuvieron información para construir su propuesta incluyendo las relacionadas a la inteligencia artificial.
Literatura (búsqueda en Scopus, 16 de octubre de 2026):
- Sahin, G. et al. (2023). Prioritization of Post-Disaster Needs Using the Fuzzy AHP Method. Turk Deprem Arastirma Dergisi, 5, 314-330. doi:10.46464/tdad.1371581
- Chakraborty, A. y Joshi, P.K. (2016). Mapping disaster vulnerability in India using analytical hierarchy process. Geomatics, Natural Hazards and Risk, 7, 308-325. doi:10.1080/19475705.2014.897656
- Suarez, A.M. y Clarke, K.C. (2022). A geographical and content-based approach to prioritize relevant and reliable tweets for emergency management. Cartography and Geographic Information Science, 49, 443-463. doi:10.1080/15230406.2022.2081257
- Fan, C. et al. (2020). Spatial biases in crowdsourced data: social media content attention concentrates on populous areas in disasters. Computers, Environment and Urban Systems, 83. doi:10.1016/j.compenvurbsys.2020.101514
- Eckhardt, D. y Leiras, A. (2018). A review of required features for a disaster response system on top of a multi-criteria decision: a Brazilian perspective. Production, 28. doi:10.1590/0103-6513.20180007
- Montefalcon, M.D. et al. (2021). IRespondPH: a mobile and web-based application for post disaster needs assessment and response in the Philippines. ACM International Conference Proceeding Series, 54-61. doi:10.1145/3485768.3485784
- Hasani, S. y Aktas, E. (2016). Using simulation gaming to validate a mathematical modeling platform for resource allocation in disasters. Proceedings of the Operational Research Society Simulation Workshop 2016, 72-80.
- Albahri, A.S. et al. (2024). A systematic review of trustworthy artificial intelligence applications in natural disasters. Computers and Electrical Engineering, 118. doi:10.1016/j.compeleceng.2024.109409
- Grass, E. et al. (2023). A machine learning approach to deal with ambiguity in the humanitarian decision-making. Production and Operations Management, 32, 2956-2974. doi:10.1111/poms.14018
- Reynard, D. y Shirgaokar, M. (2019). Harnessing the power of machine learning: can Twitter data be useful in guiding resource allocation decisions during a natural disaster? Transportation Research Part D, 77, 449-463. doi:10.1016/j.trd.2019.03.002

Datos:
- Estimación del número total de viviendas (ocupadas y desocupadas) 2018-2035 a nivel municipal, departamento del Atlántico (conjunto de datos abiertos, descargado el 16 de octubre de 2026). Se usó para repartir las viviendas del prototipo entre los barrios.
- Límites y nombres de los 23 municipios y de 600 barrios y centros poblados del Atlántico: © colaboradores de OpenStreetMap, licencia ODbL. Los mapas del sitio usan teselas de OpenStreetMap.
- Registro de propiedad horizontal de Barranquilla (conjunto de datos abiertos, descargado el 16 de octubre de 2026). Se consultó; no se incorporó al prototipo.

Inteligencia artificial:
- Claude (Anthropic), asistente de inteligencia artificial, incluido Claude Code. Se usó para organizar y redactar las ideas, clasificar los resultados de la búsqueda en Scopus, proponer el diseño del modelo, programar y probar el prototipo y preparar los documentos de requerimientos y de este formulario. Las decisiones del proyecto y la revisión de las fuentes son del equipo.
