/* Menú plegable en celular. Sin JavaScript el menú se ve completo, como siempre.
 * En pantallas angostas aparece un botón "Menú" que muestra u oculta los enlaces; en pantallas anchas no hay botón. */
(function () {
  'use strict';
  var boton = document.getElementById('menu-boton');
  var menu = document.getElementById('menu-principal');
  if (!boton || !menu || !menu.hasAttribute('data-plegable') || !window.matchMedia) return;
  var angosta = window.matchMedia('(max-width: 47.99rem)');

  function poner(abierto) {
    menu.hidden = !abierto;
    boton.setAttribute('aria-expanded', abierto ? 'true' : 'false');
  }

  function ajustar() {
    if (angosta.matches) { boton.hidden = false; poner(false); }
    else { boton.hidden = true; poner(true); }
  }

  boton.addEventListener('click', function () { poner(menu.hidden); });
  // Escape cierra el menú y devuelve el foco al botón.
  menu.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && angosta.matches && !menu.hidden) { poner(false); boton.focus(); }
  });
  if (angosta.addEventListener) angosta.addEventListener('change', ajustar); else angosta.addListener(ajustar);
  ajustar();
})();
