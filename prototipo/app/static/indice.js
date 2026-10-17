/* Índice de la portada: marca con aria-current la sección que se está leyendo y deja visible su botón en la barra.
 * Sin JavaScript la barra funciona igual, solo que sin ese resaltado. */
(function () {
  'use strict';

  // Devuelve el id de la sección activa: la última cuyo borde superior ya pasó la línea de lectura.
  function activa(secciones, linea) {
    var elegida = null;
    for (var i = 0; i < secciones.length; i++) {
      if (secciones[i].top <= linea) elegida = secciones[i].id;
    }
    return elegida;
  }

  if (typeof module !== 'undefined' && module.exports) module.exports = { activa: activa };
  if (typeof document === 'undefined') return;

  var barra = document.querySelector('.indice-portada');
  if (!barra) return;
  var enlaces = Array.prototype.slice.call(barra.querySelectorAll('a[href^="#"]'));
  var ids = enlaces.map(function (a) { return a.getAttribute('href').slice(1); });
  var carril = barra.querySelector('ul') || barra;   // la lista es lo que se desliza en celular
  var actual = null;
  var pendiente = false;

  function marcar() {
    pendiente = false;
    var linea = barra.getBoundingClientRect().bottom + 24;
    var posiciones = ids.map(function (id) {
      var el = document.getElementById(id);
      return { id: id, top: el ? el.getBoundingClientRect().top : Infinity };
    });
    var id = activa(posiciones, linea);
    if (id === actual) return;
    actual = id;
    enlaces.forEach(function (a) {
      if (a.getAttribute('href') === '#' + id) {
        a.setAttribute('aria-current', 'location');
        // En celular la barra se desliza: se lleva el botón activo a la vista, sin mover la página.
        if (carril.scrollWidth > carril.clientWidth) {
          var caja = a.getBoundingClientRect(), marco = carril.getBoundingClientRect();
          carril.scrollLeft += caja.left - marco.left - (marco.width - caja.width) / 2;
        }
      } else {
        a.removeAttribute('aria-current');
      }
    });
  }

  function pedir() {
    if (!pendiente) { pendiente = true; window.requestAnimationFrame(marcar); }
  }

  window.addEventListener('scroll', pedir, { passive: true });
  window.addEventListener('resize', pedir);
  marcar();
})();
