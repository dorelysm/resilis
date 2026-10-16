/* Al salir, borra los datos guardados en este dispositivo (copias de la página de entregas y códigos). */
document.addEventListener('submit', function (e) {
  if (e.target.getAttribute('action') !== '/salir') return;
  try {
    ['resilis_entregas', 'resilis_pendientes', 'resilis_intentos'].forEach(function (k) { localStorage.removeItem(k); });
    if (window.caches) caches.delete('resilis-v1');
  } catch (err) { /* nada que borrar */ }
});
