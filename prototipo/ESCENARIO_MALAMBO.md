# Escenario: vendaval en Malambo

Una historia corta y controlada para recorrer el ciclo completo en una demostración. Todo lo que carga el sistema es
simulado: las personas que reportan, piden ayuda y donan son cuentas ficticias sin contraseña. Lo operan las cuentas
reales (brigadista, entidad, equipo de entrega, centro de acopio).

## Lo que ocurre (lo carga el sistema)

| Cuándo | Qué pasa |
|---|---|
| Hace 6 horas | Un vendaval golpea Malambo. El epicentro es **Juan XXIII** (el barrio con más vecinos a menos de 1,5 km). El daño es máximo ahí y baja con la distancia: cae a 1/e cada 1,1 km. |
| Primeras 5 horas | La gente reporta: más en los barrios más golpeados, con algo de ruido (reportan ciudadanos, 3 brigadistas y una entidad). Quedan sin revisar. |
| De 1 a 5,5 horas | Llegan **10 solicitudes de ayuda**: 8 para reparar viviendas (láminas, clavos y lonas); 1 de medicamentos de uso continuo perdidos en el desastre (urgencia máxima); 1 de una silla de ruedas destruida, registrada en papel por un brigadista. Los dos casos especiales llevan información de vulnerabilidad con consentimiento. Todas quedan **sin verificar**. |
| Inventario | Llegan donaciones al centro de acopio: 40 kits de reparación, 6 kits de medicamentos, 300 litros de agua, 30 kits de higiene y 120 raciones. **No hay ninguna silla de ruedas**. Queda una donación de 20 kits **ofrecida**, esperando que el centro la reciba. |

## Lo que hace cada cuenta real

1. **Brigadista** (Verificar): confirma las 10 solicitudes y, si quiere, los reportes.
2. **Centro de acopio** (Recibir donaciones): recibe los 20 kits de reparación que estaban ofrecidos.
3. **Entidad** (Prioridades y mapa): ve cómo el daño baja desde Juan XXIII. (Plan): calcula el plan. **Cubre 9 de 10**: la silla de ruedas queda "sin cubrir" porque no hay inventario compatible, y el plan lo dice. Aprueba los dos paquetes (6 y 3 entregas).
4. **Equipo de entrega** (Mis entregas): marca "en camino" y confirma cada entrega con el código.
5. **Quien recibe** (si se crea una solicitud propia): ve su código, el recorrido y el mapa de la ruta (simulada).
6. **Entidad** (Recorrido): ve cómo se vacían las etapas, y que la solicitud de la silla sigue esperando.

## Qué se demuestra

- Un evento localizado y el decaimiento del daño con la distancia, en el mapa y en las prioridades.
- La confianza de la información (reportes con ruido, barrios sin reportes).
- Casos de vulnerabilidad atendidos con prioridad y con datos sensibles protegidos.
- Un faltante real: el plan avisa lo que no puede cubrir en lugar de ocultarlo.
- Plan en paquetes pequeños, entrega con código de un solo uso, recorrido y mapa de ruta.

## Cómo se carga

En producción, con la variable `CARGAR_ESCENARIO_MALAMBO=true` (un solo uso: se quita después). Se niega si ya hay algún
evento, así que no duplica ni pisa nada. Lo escrito en `app/escenario_malambo.py`; probado de punta a punta en
`tests/test_escenario_malambo.py`.
