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
Viabilidad técnica: el prototipo ya funciona en línea (resilis.dorelys.dev), con 338 pruebas automáticas y accesibilidad WCAG 2.2 AA. Usa software abierto y se adapta a otro territorio cambiando solo los barrios y los pesos.

Económica: el prototipo en línea consume solo US$0,10 de recursos en Railway (unos COP 400) y cuesta menos de COP 50.000 al mes con el plan base. Operarlo un mes, con soporte, capacitación, asesoría jurídica y gastos administrativos, cuesta unos COP 3,8 millones (presupuesto adjunto). Podría financiarse con las oficinas de gestión del riesgo de municipios y departamento, cooperación humanitaria y convocatorias públicas de innovación. Al ser abierto, otras ciudades pueden replicarlo sin pagar licencias.

Social: se usa desde el celular que ya tiene la gente; quien no lo tiene a mano imprime una ficha con su código. Se piden solo los datos necesarios (nombre, teléfono y, si pide ayuda, barrio), con consentimiento expreso, y cada rol ve solo lo que necesita, según la Ley 1581 de 2012. La auditoría no contiene datos personales.

Ambiental: bajo consumo de datos y menos desplazamientos y desperdicio: lo que vence primero sale primero y se agrupan las entregas.

Próximos pasos: reemplazar los datos simulados por datos oficiales por barrio, validar la prioridad con una entidad de gestión del riesgo y completar la revisión jurídica de datos personales.


PRESUPUESTO
Presupuesto de un mes de operación de Resilis, en pesos colombianos (COP). Estimación de referencia; precios sujetos a cotización.

Datos generales
| Dato | Valor |
|---|---|
| Proyecto | Resilis: priorización y seguimiento de la ayuda tras un desastre |
| Equipo | NEXUS INNOVA 4.0 |
| Institución | Corporación Universitaria Americana (Colombia) |
| Responsable | Dorelys Martinez, líder del equipo |
| Periodo | 1 mes de operación |
| Moneda y tasa | Pesos colombianos; 1 USD = COP 4.000 |
| Tarifas | Hora de trabajo técnico COP 25.000; de coordinación COP 30.000 |

1. Tecnología
| Concepto | Cálculo | Costo (COP) |
|---|---|---|
| Hospedaje en la nube (aplicación y base de datos PostgreSQL, Railway) | Uso medido: US$0,10 (memoria 0,09; procesador 0,01; red y almacenamiento 0). Con el plan base, unos US$5 al mes | 20.000 |
| Dominio | US$12 al año, prorrateado por mes | 4.000 |
| Mantenimiento y soporte técnico | 40 horas x COP 25.000 | 1.000.000 |
| Subtotal tecnología | | 1.024.000 |

2. Operación
| Concepto | Cálculo | Costo (COP) |
|---|---|---|
| Capacitación de brigadistas y organizaciones | 1 taller de 20 personas (material, refrigerios y transporte) | 600.000 |
| Fichas impresas con código | 500 fichas x COP 200 | 100.000 |
| Asesoría jurídica y de protección de datos (Ley 1581 de 2012) | parte mensual de la revisión jurídica | 400.000 |
| Validación de la prioridad con una persona experta en gestión del riesgo | 1 sesión | 500.000 |
| Subtotal operación | | 1.600.000 |

3. Gastos administrativos
| Concepto | Cálculo | Costo (COP) |
|---|---|---|
| Coordinación y gestión del proyecto | 10 horas x COP 30.000 | 300.000 |
| Contabilidad y facturación | servicio mensual | 150.000 |
| Transporte y logística de visitas | desplazamientos del equipo | 150.000 |
| Internet y datos móviles del equipo | servicio mensual | 100.000 |
| Herramientas de desarrollo y colaboración (repositorio, correo y asistente de IA) | suscripciones mensuales | 100.000 |
| Papelería e impresión | material de oficina | 50.000 |
| Subtotal gastos administrativos | | 850.000 |

Resumen del mes
| Rubro | Costo (COP) | Parte del total |
|---|---|---|
| Tecnología | 1.024.000 | 27 % |
| Operación | 1.600.000 | 42 % |
| Gastos administrativos | 850.000 | 22 % |
| Imprevistos (10 % del subtotal) | 347.400 | 9 % |
| **Total del mes** | **3.821.400** | 100 % |

Fuentes de financiación posibles: oficinas de gestión del riesgo de municipios y del departamento, cooperación humanitaria y convocatorias públicas de innovación. Como el sistema es de software abierto, cada nueva entidad solo asume el hospedaje, el soporte, la capacitación y su administración; no paga licencias.


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
