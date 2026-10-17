/* Tablas como tarjetas en celular. Cada celda lleva el nombre de su columna (data-etiqueta) y, en pantallas angostas,
 * la CSS apila cada fila como una tarjeta. Sin JavaScript queda la tabla con desplazamiento de siempre. */
(function () {
  'use strict';

  // Devuelve el nombre de cada columna según el encabezado (colspan incluido).
  function etiquetas(tabla) {
    var fila = tabla.querySelector('thead tr');
    if (!fila) return [];
    var lista = [];
    Array.prototype.forEach.call(fila.children, function (th) {
      var n = parseInt(th.getAttribute('colspan') || '1', 10) || 1;
      for (var i = 0; i < n; i++) lista.push((th.textContent || '').trim());
    });
    return lista;
  }

  function apilar(tabla) {
    var nombres = etiquetas(tabla);
    if (!nombres.length) return false;
    Array.prototype.forEach.call(tabla.querySelectorAll('tbody tr'), function (fila) {
      Array.prototype.forEach.call(fila.children, function (celda, i) {
        if (celda.tagName === 'TD' && nombres[i]) celda.setAttribute('data-etiqueta', nombres[i]);
      });
    });
    tabla.classList.add('tabla-apilada');
    return true;
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { etiquetas: etiquetas, apilar: apilar };
  if (typeof document === 'undefined') return;
  Array.prototype.forEach.call(document.querySelectorAll('.tabla-scroll table'), apilar);
})();
