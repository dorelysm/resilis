# Seguridad

Resilis maneja información sensible de personas afectadas por desastres, así que tomamos en serio los reportes de seguridad.

## Cómo reportar una vulnerabilidad

**Por favor no abra una incidencia pública.** Use el reporte privado de GitHub: pestaña **Security**, opción **Report a vulnerability** de este repositorio. Incluya:

- Una descripción del problema y su impacto.
- Los pasos para reproducirlo.
- La versión o el commit donde lo observó.

Responderemos en un plazo razonable e informaremos cuando esté corregido.

## Alcance

Es un **prototipo con datos ficticios**, pero el código se escribió pensando en un uso real. Nos interesan especialmente los reportes sobre:

- Acceso a datos de otra persona o a funciones de otro rol.
- Falsificación o reutilización del código de entrega.
- Alteración del registro de auditoría sin que se detecte.
- Inyección de código, XSS, CSRF o problemas de sesión.

## Qué ya está implementado

Contraseñas con scrypt y sal, sesión firmada, token CSRF en cada formulario, control de acceso por rol, límite de envíos, código de entrega de un solo uso guardado solo como huella con sal, y registro de auditoría encadenado por hash sin datos personales.
