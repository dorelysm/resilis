/* Acorta la lista de barrios al municipio elegido. Sin JavaScript la lista sigue completa, agrupada por municipio. */
document.querySelectorAll('[data-filtro-barrio]').forEach(function (bloque) {
  var municipio = bloque.querySelector('[data-municipio]');
  var barrio = bloque.nextElementSibling && bloque.nextElementSibling.querySelector('select');
  if (!municipio || !barrio) return;

  function filtrar() {
    var elegido = municipio.value;
    barrio.querySelectorAll('optgroup').forEach(function (grupo) {
      var coincide = !elegido || grupo.label === elegido;
      grupo.hidden = !coincide;
      grupo.disabled = !coincide;
    });
    var actual = barrio.options[barrio.selectedIndex];
    if (actual && actual.parentElement.tagName === 'OPTGROUP' && actual.parentElement.disabled) barrio.value = '';
  }

  // Si ya hay un barrio elegido (formulario con errores), se muestra su municipio.
  var inicial = barrio.options[barrio.selectedIndex];
  if (inicial && inicial.parentElement.tagName === 'OPTGROUP') municipio.value = inicial.parentElement.label;
  municipio.addEventListener('change', filtrar);
  filtrar();
});
