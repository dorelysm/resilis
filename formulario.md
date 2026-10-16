DESCRIPCIÓN DE LA PROBLEMÁTICA (1250 caracteres)
Describa brevemente la problemática elegida. ¿Cuáles pueden ser las principales causas? ¿Cuál es el verdadero problema a resolver? 
Tras un desastre natural (inundación, vendaval, sismo o deslizamiento), las autoridades de gestión del riesgo del Atlántico no saben con rapidez qué comunidades están más afectadas, qué necesitan primero ni dónde enviar recursos limitados. Un evento puede golpear varios municipios a la vez, como Malambo y Soledad, y desbordar a los equipos de respuesta.

El verdadero problema no es solo la falta de recursos: es convertir información dispersa, incompleta y cambiante en decisiones rápidas y justificadas, sin saber qué tan confiable es cada dato, y después garantizar que la ayuda llegue a quien la pidió. Entre las causas están la ausencia de datos previos consolidados por sector, las comunicaciones interrumpidas, los reportes sin formato común ni verificación, y la poca coordinación entre entidades.

Las consecuencias son retrasos en la ayuda, esfuerzos duplicados, ayudas que no se sabe si llegaron y comunidades vulnerables o aisladas sin atención prioritaria.

Se necesita un mecanismo accesible y económico que organice la información, priorice las necesidades, dé seguimiento a cada solicitud y funcione con baja conectividad.



DESCRIPCIÓN DE LA SOLUCIÓN (1250 caracteres)
Describa brevemente el producto/servicio y por qué lo considera una solución a la problemática elegida. ¿Por qué esta propuesta es una buena solución al problema? ¿Por qué se diferencia de otras propuestas existentes? Describa brevemente la tecnología seleccionada, el funcionamiento, las necesidades para su implementación, entre otras.
Resilis es una aplicación web, accesible desde el celular, que registra las donaciones, prioriza las necesidades y optimiza los recursos humanitarios. Cada persona que pide ayuda tiene un usuario identificado y puede indicar si es vulnerable y describir su situación. Un índice multicriterio (TOPSIS, con pesos ajustables) prioriza sectores y solicitudes y explica su decisión. Un mapa muestra la prioridad y la confianza de cada dato, y alertas señalan dónde falta información.

Los donantes registran lo que ofrecen y los centros de acopio verifican lo recibido y llevan el inventario. Con ese inventario y las solicitudes verificadas, un modelo de optimización calcula qué lote entregar a quién para cubrir la mayor necesidad posible, y la entidad aprueba el plan.

Como en una aplicación de pedidos, cada solicitud pasa por estados que el solicitante ve. Al asignarla se genera un código de un solo uso que el equipo de entrega debe recibir para confirmar la entrega, incluso sin conexión. El donante ve el estado y el destino de su donación, sin datos personales de los beneficiarios.

Se diferencia porque dice cuánto fiarse de cada dato y comprueba que la ayuda llegó. Usa Python, PostgreSQL, Leaflet y Railway, software abierto.


IMPACTO (1000 caracteres)
Describa brevemente el impacto social y/o ambiental que genera la propuesta de solución.
Impacto social: la ayuda llega primero a quienes más la necesitan y se puede comprobar que llegó. Cada persona sabe en qué estado está su solicitud, lo que da confianza en la respuesta. El código de entrega evita que la ayuda se entregue a quien no corresponde o se cobre dos veces. Las personas vulnerables (con discapacidad, adultos mayores, menores) describen su situación y reciben el recurso específico que requieren. Los sectores aislados no pierden posición por ser difíciles de alcanzar: se señalan como alerta. Los donantes ven que su ayuda llegó. Al optimizar el reparto del inventario se cubre más necesidad con los mismos recursos, se evitan esfuerzos duplicados y se puede rendir cuentas.

Impacto ambiental: al concentrar los recursos donde hacen falta se reducen los desplazamientos innecesarios y el desperdicio de suministros. El sistema consume pocos datos y funciona en la nube con software abierto.


INNOVACIÓN (1000 caracteres)
Fundamente brevemente por qué considera que esta propuesta representa una solución innovadora a la problemática seleccionada.
La priorización multicriterio en desastres está bien estudiada, pero en nuestra revisión en Scopus casi no aparecen trabajos que incorporen la confiabilidad del dato dentro de la decisión. Resilis la hace parte central: cada reporte y solicitud tiene una confianza según quién la envía, si fue verificada, qué tan reciente es y si otros la confirman. El sistema señala dónde falta información y no la confunde con ausencia de problema.

Además lleva la lógica de seguimiento de una aplicación de pedidos a la ayuda humanitaria: estados visibles para el solicitante y un código de entrega de un solo uso, verificable sin conexión, que garantiza que la ayuda llegue a quien la pidió. Une en una plataforma el registro de donaciones, la priorización de necesidades y la optimización del reparto, y combina datos oficiales del Estado, reportes ciudadanos y de brigadistas, y aprendizaje no supervisado. Es explicable, de bajo consumo de datos, accesible (WCAG AA) y de código abierto.


PRE FACTIBILIDAD ECONÓMICA, SOCIAL Y SUSTENTABILIDAD AMBIENTAL (1500 caracteres)
Describa brevemente las razones que hacen de esta propuesta una propuesta sostenible en el tiempo. Fundamente por qué considera que esta propuesta es presupuestariamente abordable, por qué es viable o aceptable socialmente 
Económica: el prototipo se construye con software abierto y se aloja en la nube, sin licencias ni equipos especializados. Los costos de operación son bajos: hospedaje, mantenimiento y capacitación de brigadistas y organizaciones. Podrían financiarse con las oficinas de gestión del riesgo de municipios y departamento y con cooperación humanitaria. Al ser abierto, otras ciudades pueden replicarlo sin pagar licencias.

Social: se usa desde el celular que ya tiene la gente, con lenguaje sencillo y accesibilidad WCAG AA. Quien no tiene celular recibe una ficha impresa con su código, y si no hay electricidad se reporta en papel. Para dar seguimiento hay que identificar a cada solicitante, por eso se piden solo los datos necesarios: nombre, teléfono y sector; el documento solo para entregas de mayor valor. Los datos de vulnerabilidad se piden con consentimiento expreso y cada rol ve solo lo que necesita, en línea con la Ley 1581 de 2012. El registro de auditoría no contiene datos personales.

Ambiental: bajo consumo de datos y menos desplazamientos innecesarios de ayuda.

Límites: hoy el prototipo usa datos simulados con identidades ficticias. Falta conseguir datos por barrio, identificar las fuentes oficiales, revisar jurídicamente el manejo de datos personales y validar los pesos con una entidad de gestión del riesgo.


PROPUESTAS QUE DESCARTARON
Enumere, en caso de haber descartado ideas, las diferentes propuestas que han analizado hasta elegir la actual y mencione brevemente el porque.
1. Basar el sistema en satélites, drones, redes sociales y sensores. Se dejó como mejora futura y opcional: el reto parte de comunicaciones caídas y el sistema debe funcionar sin depender de ellas.
2. Limitarse a un solo desastre y zona (inundación en Barranquilla; vendavales en Malambo y Soledad). Se amplió a desastres naturales del Atlántico, porque el sistema no depende del tipo de evento: solo cambian los pesos y los escenarios.
3. Un modelo opaco que entregue solo un resultado. Se prefirió un índice multicriterio explicable, para que la autoridad entienda y ajuste la decisión.
4. Bajar la prioridad de los sectores de difícil acceso. Se descartó para no dejar atrás a las comunidades más aisladas; se tratan como alerta.
5. Reportes anónimos. Se descartaron porque no permiten dar seguimiento ni verificar; todo reporte y solicitud se asocia a un usuario registrado.


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
- Estimación del número total de viviendas (ocupadas y desocupadas) 2018-2035 a nivel municipal, departamento del Atlántico (conjunto de datos abiertos, descargado el 16 de octubre de 2026).
- Registro de propiedad horizontal de Barranquilla (conjunto de datos abiertos, descargado el 16 de octubre de 2026).

Inteligencia artificial:
- Claude (Anthropic), asistente de inteligencia artificial. Se usó para organizar y redactar las ideas, clasificar los resultados de la búsqueda en Scopus, proponer el diseño del modelo y preparar los documentos de requerimientos y de este formulario. Las decisiones del proyecto y la revisión de las fuentes son del equipo.
