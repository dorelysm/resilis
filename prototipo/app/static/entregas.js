/* Entregas del equipo de entrega: valida el código sin conexión y sincroniza después.
 *
 * El servidor entrega, solo para las entregas del equipo, la sal y la huella (sha256 de "sal:código").
 * Si no hay red, el dispositivo compara la huella del código escrito con la guardada. Al recuperar la
 * conexión envía las entregas confirmadas y el servidor vuelve a validar cada código.
 */
(function () {
  'use strict';

  var CLAVE_ENTREGAS = 'resilis_entregas';
  var CLAVE_PENDIENTES = 'resilis_pendientes';
  var CLAVE_INTENTOS = 'resilis_intentos';
  var MAX_INTENTOS = 5;

  function normalizar(texto) {
    return (texto || '').toUpperCase().replace(/[^A-Z0-9]/g, '');
  }

  function huella(sal, codigo) {
    var datos = new TextEncoder().encode(sal + ':' + normalizar(codigo));
    return crypto.subtle.digest('SHA-256', datos).then(function (h) {
      return Array.from(new Uint8Array(h)).map(function (b) {
        return b.toString(16).padStart(2, '0');
      }).join('');
    });
  }

  // Para probar la función en Node, sin navegador.
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { normalizar: normalizar, huella: huella };
    return;
  }

  function leer(clave, porDefecto) {
    try { return JSON.parse(localStorage.getItem(clave)) || porDefecto; } catch (e) { return porDefecto; }
  }
  function guardar(clave, valor) {
    try { localStorage.setItem(clave, JSON.stringify(valor)); } catch (e) { /* sin almacenamiento */ }
  }

  var aviso = document.getElementById('estado-sync');
  function decir(texto, esError) {
    if (!aviso) return;
    aviso.textContent = texto;
    aviso.hidden = !texto;
    aviso.className = esError ? 'mensaje mensaje-error' : 'mensaje';
    aviso.setAttribute('role', esError ? 'alert' : 'status');
  }

  function token() {
    var meta = document.querySelector('meta[name="csrf"]');
    return meta ? meta.content : '';
  }

  function descargarDatos() {
    return fetch('/entregas/datos.json', { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (d) { if (d) guardar(CLAVE_ENTREGAS, d.entregas); })
      .catch(function () { /* sin red: se usan los datos guardados */ });
  }

  function enviar(lista) {
    return fetch('/entregas/sincronizar', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token() },
      body: JSON.stringify({ entregas: lista })
    }).then(function (r) {
      if (!r.ok) throw new Error('http ' + r.status);
      return r.json();
    });
  }

  function sincronizar() {
    var pendientes = leer(CLAVE_PENDIENTES, []);
    if (!pendientes.length || !navigator.onLine) return Promise.resolve();
    return enviar(pendientes).then(function (resp) {
      var resueltos = {};
      var errores = [];
      resp.resultados.forEach(function (res) {
        resueltos[res.id] = true;  // aceptada, o rechazada de forma definitiva
        if (!res.ok) errores.push(res.mensaje);
      });
      guardar(CLAVE_PENDIENTES, pendientes.filter(function (p) { return !resueltos[p.id]; }));
      if (errores.length) {
        decir('Se enviaron las entregas, pero el servidor rechazó ' + errores.length + ': ' + errores.join(' '), true);
      } else {
        decir('Las entregas confirmadas sin conexión ya se enviaron.', false);
        setTimeout(function () { location.reload(); }, 1500);
      }
    }).catch(function () { /* se reintenta cuando vuelva la conexión */ });
  }

  function confirmarSinConexion(id, codigo) {
    var entrega = leer(CLAVE_ENTREGAS, []).filter(function (e) { return e.id === id; })[0];
    if (!entrega) {
      decir('Este teléfono no tiene los datos de esta entrega. Conéctese una vez para descargarlos.', true);
      return Promise.resolve();
    }
    var intentos = leer(CLAVE_INTENTOS, {});
    if ((intentos[id] || 0) >= MAX_INTENTOS) {
      decir('Demasiados intentos con un código incorrecto. Conéctese para que la entidad vuelva a asignar la entrega.', true);
      return Promise.resolve();
    }
    if (entrega.vence && new Date(entrega.vence) <= new Date()) {
      decir('El código venció. La solicitud debe asignarse de nuevo.', true);
      return Promise.resolve();
    }
    return huella(entrega.sal, codigo).then(function (h) {
      if (h !== entrega.huella) {
        intentos[id] = (intentos[id] || 0) + 1;
        guardar(CLAVE_INTENTOS, intentos);
        decir('El código no es correcto. Revise que sea el que tiene la persona.', true);
        return;
      }
      var pendientes = leer(CLAVE_PENDIENTES, []).filter(function (p) { return p.id !== id; });
      pendientes.push({ id: id, codigo: normalizar(codigo) });
      guardar(CLAVE_PENDIENTES, pendientes);
      decir('Entrega confirmada en este teléfono. Se enviará cuando haya conexión.', false);
      var tarjeta = document.getElementById('entrega-' + id);
      if (tarjeta) tarjeta.setAttribute('data-confirmada-local', 'si');
    });
  }

  function alEnviarFormulario(evento) {
    var form = evento.target;
    if (!form.classList.contains('js-confirmar')) return;
    evento.preventDefault();
    var id = parseInt(form.getAttribute('data-entrega'), 10);
    var codigo = form.querySelector('input[name="codigo"]').value;
    if (!window.crypto || !crypto.subtle) {
      form.submit();  // sin funciones de cifrado en el navegador: la validación queda para el servidor
      return;
    }
    if (!navigator.onLine) { confirmarSinConexion(id, codigo); return; }
    enviar([{ id: id, codigo: codigo }]).then(function (resp) {
      var res = resp.resultados[0];
      if (res.ok) {
        decir('Entrega confirmada. Gracias.', false);
        setTimeout(function () { location.reload(); }, 800);
      } else {
        decir(res.mensaje, true);
      }
    }).catch(function () { confirmarSinConexion(id, codigo); });
  }

  document.addEventListener('submit', alEnviarFormulario);
  window.addEventListener('online', function () { descargarDatos().then(sincronizar); });
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('/sw.js').catch(function () {});
  if (navigator.onLine) descargarDatos().then(sincronizar);
})();
