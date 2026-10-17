/* Mapa de la ruta de una entrega (Leaflet, incluido en /static/vendor/leaflet).
 *
 * Dos modos, según data-modo del contenedor #mapa-ruta:
 *   - "solicitud": la persona que recibe ve el centro de acopio, su destino y el equipo que se acerca.
 *   - "donante":   quien dona ve los centros, los barrios donde llegó su ayuda (con un círculo aproximado) y los equipos en camino.
 * La posición del equipo es SIMULADA (el servidor lo dice y la pantalla lo avisa). Todo lo que se ve en el mapa
 * también está escrito en #estado-ruta (y en #lista-destinos para quien dona): el mapa no es la única forma de enterarse.
 * Se actualiza cada 15 segundos solo mientras la pantalla está a la vista.
 */
(function () {
  'use strict';

  var INTERVALO_MS = 15000;

  function escapar(texto) {
    return String(texto == null ? '' : texto).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  // Una línea por barrio para la lista de quien dona: lo mismo que dice el mapa, en texto.
  function lineaDestino(d) {
    var partes = [];
    if (d.entregadas) partes.push(d.entregadas + ' entregada(s)');
    if (d.en_camino) partes.push(d.en_camino + ' en camino');
    var otras = d.entregas - d.entregadas - d.en_camino;
    if (otras > 0) partes.push(otras + ' por salir');
    return d.barrio + ': ' + partes.join(', ') + '.';
  }

  // Una línea por entrega para el control logístico: lo mismo que dice el mapa, en texto.
  function lineaEntrega(e) {
    var quien = e.equipo || 'Equipo';
    var desde = e.origen ? e.origen.nombre : 'el centro';
    var hacia = e.destino ? e.destino.nombre : 'el destino';
    var estado = e.etapa === 'en_camino'
      ? 'en camino, faltan ' + (e.restante_km != null ? String(e.restante_km).replace('.', ',') : '?') + ' km' + (e.cerca ? ' (ya está cerca)' : '')
      : 'por salir';
    return quien + ': de ' + desde + ' a ' + hacia + ', ' + estado + '.';
  }

  function textoActualizado(iso) {
    var d = new Date(iso);
    if (isNaN(d.getTime())) return '';
    var dos = function (n) { return (n < 10 ? '0' : '') + n; };
    return 'Actualizado a las ' + dos(d.getHours()) + ':' + dos(d.getMinutes()) + ':' + dos(d.getSeconds()) + '.';
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { escapar: escapar, lineaDestino: lineaDestino, lineaEntrega: lineaEntrega, textoActualizado: textoActualizado };
    return;
  }

  var contenedor = document.getElementById('mapa-ruta');
  if (!contenedor || !window.L) return;

  var modo = contenedor.getAttribute('data-modo');
  var listaEntregas = document.getElementById('lista-entregas');
  var url = contenedor.getAttribute('data-url');
  var estado = document.getElementById('estado-ruta');
  var aviso = document.getElementById('aviso-cerca');
  var lista = document.getElementById('lista-destinos');
  var mapa = L.map('mapa-ruta', { keyboard: true, scrollWheelZoom: false }).setView([10.95, -74.85], 11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(mapa);

  var capa = L.layerGroup().addTo(mapa);
  var equipo = null;          // marcador del equipo (modo solicitud), para moverlo sin redibujar todo
  var yaAvisoCerca = false;
  var temporizador = null;
  var ajustado = false;

  function pin(clase, texto, titulo) {
    return L.divIcon({
      className: 'pin-ruta',
      html: '<span class="pin ' + clase + '"><span class="pin-punto" aria-hidden="true"></span>' + escapar(texto) + '</span>',
      iconSize: null
    });
  }

  function marcador(lat, lon, clase, texto, titulo) {
    return L.marker([lat, lon], { icon: pin(clase, texto), title: titulo || texto, keyboard: true, alt: titulo || texto });
  }

  function dibujarSolicitud(d) {
    capa.clearLayers();
    equipo = null;
    var puntos = [];
    if (d.origen) {
      marcador(d.origen.lat, d.origen.lon, 'pin-origen', 'Sale de aquí', 'Centro de acopio: ' + d.origen.nombre).addTo(capa);
      puntos.push([d.origen.lat, d.origen.lon]);
    }
    if (d.destino) {
      marcador(d.destino.lat, d.destino.lon, 'pin-destino', 'Destino', 'Destino: ' + d.destino.nombre).addTo(capa);
      puntos.push([d.destino.lat, d.destino.lon]);
    }
    if (d.origen && d.destino) {
      L.polyline([[d.origen.lat, d.origen.lon], [d.destino.lat, d.destino.lon]], { color: '#055c81', weight: 3, dashArray: '8 8' }).addTo(capa);
    }
    if (d.posicion && d.etapa === 'en_camino') {
      equipo = marcador(d.posicion.lat, d.posicion.lon, 'pin-equipo', 'Equipo', 'Posición simulada del equipo de entrega').addTo(capa);
    }
    if (!ajustado && puntos.length) {
      mapa.fitBounds(L.latLngBounds(puntos).pad(0.3), { maxZoom: 15 });
      ajustado = true;
    }
  }

  function dibujarDonante(d) {
    capa.clearLayers();
    var puntos = [];
    d.origenes.forEach(function (o) {
      marcador(o.lat, o.lon, 'pin-origen', 'Centro', 'Centro de acopio: ' + o.nombre).addTo(capa);
      puntos.push([o.lat, o.lon]);
    });
    d.destinos.forEach(function (b) {
      L.circle([b.lat, b.lon], { radius: b.radio_m, color: '#046e70', weight: 2, fillColor: '#0da4a0', fillOpacity: 0.3 })
        .bindTooltip(escapar(lineaDestino(b))).addTo(capa);
      puntos.push([b.lat, b.lon]);
    });
    d.en_camino.forEach(function (e) {
      // Una zona aproximada que se va moviendo, no un punto: quien dona no necesita ver la ruta exacta.
      L.circle([e.lat, e.lon], { radius: e.radio_m, color: '#0d4c66', weight: 2, dashArray: '6 6', fillColor: '#055c81', fillOpacity: 0.25 })
        .bindTooltip(escapar('Entrega en camino hacia ' + e.hacia + ': zona aproximada, ' + e.avance + ' % del trayecto (simulado)')).addTo(capa);
    });
    if (!ajustado && puntos.length) {
      mapa.fitBounds(L.latLngBounds(puntos).pad(0.2), { maxZoom: 14 });
      ajustado = true;
    }
    if (lista) {
      lista.innerHTML = d.destinos.length
        ? d.destinos.map(function (b) { return '<li>' + escapar(lineaDestino(b)) + '</li>'; }).join('')
        : '<li>Todavía no hay entregas hechas con su donación.</li>';
    }
  }

  // Control logístico: todas las entregas en marcha, cada una con su equipo, su ruta y dónde va.
  function dibujarLogistica(d) {
    capa.clearLayers();
    var puntos = [];
    d.entregas.forEach(function (e) {
      if (e.origen) { marcador(e.origen.lat, e.origen.lon, 'pin-origen', 'Centro', 'Centro de acopio: ' + e.origen.nombre).addTo(capa); puntos.push([e.origen.lat, e.origen.lon]); }
      if (e.destino) { marcador(e.destino.lat, e.destino.lon, 'pin-destino', e.destino.nombre, 'Destino: ' + e.destino.nombre).addTo(capa); puntos.push([e.destino.lat, e.destino.lon]); }
      if (e.origen && e.destino) L.polyline([[e.origen.lat, e.origen.lon], [e.destino.lat, e.destino.lon]], { color: '#055c81', weight: 2, dashArray: '8 8' }).addTo(capa);
      if (e.posicion && e.etapa === 'en_camino') {
        marcador(e.posicion.lat, e.posicion.lon, 'pin-equipo', e.equipo || 'Equipo', (e.equipo || 'Equipo') + ' (posición simulada)').addTo(capa);
      }
    });
    if (!ajustado && puntos.length) { mapa.fitBounds(L.latLngBounds(puntos).pad(0.2), { maxZoom: 16 }); ajustado = true; }
    if (listaEntregas) {
      listaEntregas.innerHTML = d.entregas.length
        ? d.entregas.map(function (e) { return '<li>' + escapar(lineaEntrega(e)) + '</li>'; }).join('')
        : '<li>No hay entregas en marcha.</li>';
    }
  }

  function aplicar(d) {
    if (modo === 'donante') dibujarDonante(d); else if (modo === 'logistica') dibujarLogistica(d); else dibujarSolicitud(d);
    estado.textContent = (modo === 'logistica' ? d.texto : d.texto) + ' ' + textoActualizado(d.actualizado);
    if (modo === 'solicitud' && d.cerca && !yaAvisoCerca && aviso) {
      yaAvisoCerca = true;
      aviso.hidden = false;
      aviso.textContent = 'El equipo está cerca. Tenga a la mano su código de entrega.';
      if (navigator.vibrate) navigator.vibrate(200);
    }
    // Cuando ya se entregó, no hace falta seguir preguntando.
    if (modo === 'solicitud' && d.etapa === 'entregada') detener();
  }

  function cargar() {
    fetch(url, { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
      .then(aplicar)
      .catch(function () {
        estado.textContent = 'No se pudo actualizar el mapa. Se muestra lo último que se alcanzó a ver; se intentará de nuevo en unos segundos.';
      });
  }

  function iniciar() {
    if (temporizador) return;
    cargar();
    temporizador = setInterval(cargar, INTERVALO_MS);
  }

  function detener() {
    if (temporizador) { clearInterval(temporizador); temporizador = null; }
  }

  document.addEventListener('visibilitychange', function () {
    if (document.visibilityState === 'visible') iniciar(); else detener();
  });
  var boton = document.getElementById('actualizar-ruta');
  if (boton) boton.addEventListener('click', cargar);
  if (document.visibilityState === 'visible') iniciar();
})();
