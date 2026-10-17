/* Mapa de barrios. Dibuja un marcador por barrio con Leaflet (incluido en /static/vendor/leaflet).
 *
 * - Cada barrio es un círculo que se puede enfocar con el teclado. El color es solo una ayuda: el número de
 *   adentro es el lugar en la lista, y la misma información está en la tabla de /prioridades.
 * - Los barrios sin reportes se dibujan rayados, para no confundirlos con los que están bien.
 * - Las clases de color son quintiles de los datos que se muestran, para que haya contraste aunque casi todos
 *   los valores sean parecidos.
 */
(function () {
  'use strict';

  // Rampas de claro a oscuro, sacadas del azul y el verde azulado del logo.
  var RAMPAS = {
    prioridad: ['#d6e9f0', '#9ccbdc', '#4fa3c0', '#055c81', '#0d4c66'],
    confianza: ['#ddf3f2', '#a5dedb', '#5cc2bd', '#0da4a0', '#046e70']
  };
  var CLASES = 5;
  var BORDE = '#0d4c66';

  // ---------------------------------------------------------------------------- funciones puras
  function escapar(texto) {
    return String(texto == null ? '' : texto).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function cuantiles(valores, k) {
    // Los k-1 cortes que reparten los valores en k grupos del mismo tamaño.
    var orden = valores.slice().sort(function (a, b) { return a - b; });
    var cortes = [];
    for (var i = 1; i < k; i++) {
      cortes.push(orden.length ? orden[Math.min(orden.length - 1, Math.floor(i * orden.length / k))] : 0);
    }
    return cortes;
  }

  function claseDe(valor, cortes) {
    var c = 0;
    while (c < cortes.length && valor >= cortes[c]) c++;
    return c;
  }

  function luminancia(hex) {
    var h = hex.replace('#', '');
    var canales = [0, 2, 4].map(function (i) {
      var v = parseInt(h.substr(i, 2), 16) / 255;
      return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4);
    });
    return 0.2126 * canales[0] + 0.7152 * canales[1] + 0.0722 * canales[2];
  }

  function contraste(a, b) {
    var la = luminancia(a), lb = luminancia(b);
    return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
  }

  function textoSobre(fondo) {
    return contraste(fondo, '#ffffff') >= contraste(fondo, '#1b1b1b') ? '#ffffff' : '#1b1b1b';
  }

  function tamano(personas, maximo) {
    var f = maximo > 0 ? Math.sqrt(Math.max(0, personas) / maximo) : 0;
    return Math.round(24 + 16 * f);
  }

  function escala(zoom) {
    // Con el mapa alejado hay que dibujar los círculos más chicos para que no se tapen; al acercar, crecen.
    return Math.max(0.55, Math.min(1.25, 0.55 + (zoom - 10) * 0.175));
  }

  function mostrarNumero(posicion, zoom) {
    return posicion <= 15 || (zoom >= 13 && posicion <= 99);
  }

  function tieneAviso(barrio, aviso) {
    if (!aviso) return true;
    var alertas = barrio.alertas || [];
    return aviso === 'cualquiera' ? alertas.length > 0 : alertas.indexOf(aviso) !== -1;
  }

  function filtrar(barrios, filtros) {
    return barrios.filter(function (s) {
      return (!filtros.municipio || s.codigo_municipio === filtros.municipio) && tieneAviso(s, filtros.aviso) &&
        (filtros.sinInfo !== false || conInfo(s));  // con sinInfo === false se ocultan los barrios sin reportes ni solicitudes
    });
  }

  function conInfo(barrio) {
    return (barrio.n_reportes || 0) > 0 || (barrio.n_solicitudes || 0) > 0;
  }

  function sinDatos(barrio) {
    return (barrio.alertas || []).indexOf('sin_reportes') !== -1;
  }

  function pct(valor) { return Math.round(valor * 100) + ' %'; }

  function resumen(barrio, nombresAlerta, total) {
    var partes = [barrio.nombre + ' (' + barrio.municipio + ')',
      'lugar ' + barrio.posicion + ' de ' + total,
      'prioridad ' + pct(barrio.prioridad), 'confianza ' + pct(barrio.confianza)];
    var avisos = (barrio.alertas || []).map(function (a) { return nombresAlerta[a] || a; });
    if (avisos.length) partes.push('avisos: ' + avisos.join(', '));
    return partes.join(', ');
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = { RAMPAS: RAMPAS, CLASES: CLASES, BORDE: BORDE, escapar: escapar, cuantiles: cuantiles,
      claseDe: claseDe, escala: escala, mostrarNumero: mostrarNumero, contraste: contraste, textoSobre: textoSobre, tamano: tamano, filtrar: filtrar,
      tieneAviso: tieneAviso, sinDatos: sinDatos, conInfo: conInfo, resumen: resumen };
    return;
  }

  // ---------------------------------------------------------------------------- el mapa
  var contenedor = document.getElementById('mapa');
  if (!contenedor || !window.L) return;

  var estado = document.getElementById('estado-mapa');
  var selMunicipio = document.getElementById('filtro-municipio');
  var selAviso = document.getElementById('filtro-aviso');
  var chkSinInfo = document.getElementById('ver-sin-info');
  var leyenda = document.getElementById('leyenda');
  var datos = null;
  var capa = null;
  var mapa = L.map('mapa', { keyboard: true, scrollWheelZoom: true }).setView([10.95, -74.85], 11);
  L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 18, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
  }).addTo(mapa);

  function vistaActual() {
    var marcado = document.querySelector('input[name="ver"]:checked');
    return marcado ? marcado.value : 'prioridad';
  }

  function dibujarLeyenda(vista, cortes, hayRayados) {
    var rampa = RAMPAS[vista];
    var limites = [0].concat(cortes).concat([1]);
    var filas = rampa.map(function (color, i) {
      return '<li><span class="muestra" style="background:' + color + '"></span>' +
        (vista === 'prioridad' ? 'Prioridad' : 'Confianza') + ' de ' + pct(limites[i]) + ' a ' + pct(limites[i + 1]) +
        (i === CLASES - 1 ? ' (la más alta)' : '') + '</li>';
    });
    if (hayRayados) filas.push('<li><span class="muestra muestra-rayada"></span>Sin reportes: no hay información confiable</li>');
    leyenda.innerHTML = filas.join('');
  }

  function dibujar(ajustar) {
    if (!datos) return;
    var zoom = mapa.getZoom();
    var vista = vistaActual();
    // Por defecto solo los barrios con información; si todavía no hay ninguno, se muestran todos.
    var hayInfo = datos.barrios.some(conInfo);
    var sinInfo = chkSinInfo.checked || !hayInfo;
    var visibles = filtrar(datos.barrios, { municipio: selMunicipio.value, aviso: selAviso.value, sinInfo: sinInfo });
    if (capa) mapa.removeLayer(capa);
    capa = L.layerGroup();
    var conDatos = visibles.filter(function (s) { return !sinDatos(s); });
    var cortes = cuantiles(conDatos.map(function (s) { return s[vista]; }), CLASES);
    var maxPersonas = Math.max.apply(null, visibles.map(function (s) { return s.personas; }).concat([1]));
    var puntos = [];

    visibles.forEach(function (s) {
      var rayado = sinDatos(s);
      var color = rayado ? '#ffffff' : RAMPAS[vista][claseDe(s[vista], cortes)];
      var lado = Math.round(tamano(s.personas, maxPersonas) * escala(zoom));
      var numero = mostrarNumero(s.posicion, zoom) ? s.posicion : '';
      var html = '<span class="barrio-punto' + (rayado ? ' sin-datos' : '') + '" style="width:' + lado + 'px;height:' + lado +
        'px;background:' + (rayado ? '' : color) + ';color:' + textoSobre(color) + '">' + numero + '</span>';
      var etiqueta = resumen(s, datos.alertas, datos.total) + (rayado ? '. Sin reportes.' : '');
      var marcador = L.marker([s.lat, s.lon], {
        icon: L.divIcon({ className: 'barrio-marca', html: html, iconSize: [lado, lado], iconAnchor: [lado / 2, lado / 2] }),
        keyboard: true, title: etiqueta, riseOnHover: true
      });
      marcador.bindPopup(
        '<strong>' + escapar(s.nombre) + '</strong><br>' + escapar(s.municipio) +
        '<br>Lugar ' + s.posicion + ' de ' + datos.total + '<br>Prioridad: ' + pct(s.prioridad) +
        '<br>Confianza: ' + pct(s.confianza) +
        (s.alertas.length ? '<br>Avisos: ' + escapar(s.alertas.map(function (a) { return datos.alertas[a] || a; }).join(', ')) : '') +
        '<br>' + s.n_reportes + ' reporte(s), ' + s.n_solicitudes + ' solicitud(es) abiertas' +
        '<br><a href="/prioridades/barrios/' + s.id + '">Ver por qué ocupa este lugar</a>');
      marcador.on('add', function () {
        var el = marcador.getElement();
        if (el) el.setAttribute('aria-label', etiqueta);
      });
      marcador.addTo(capa);
      puntos.push([s.lat, s.lon]);
    });
    capa.addTo(mapa);
    if (ajustar !== false && puntos.length) mapa.fitBounds(L.latLngBounds(puntos).pad(0.15), { maxZoom: 14 });
    dibujarLeyenda(vista, cortes, visibles.some(sinDatos));
    estado.textContent = visibles.length === 0
      ? 'Ningún barrio cumple con ese filtro.'
      : 'Se muestran ' + visibles.length + ' de ' + datos.total + ' barrios' +
        (sinInfo ? '.' : ' (los que tienen reportes o solicitudes). Marque la casilla para ver también los barrios sin información.');
  }

  function cargar() {
    fetch(contenedor.getAttribute('data-url'), { credentials: 'same-origin', cache: 'no-store' })
      .then(function (r) { if (!r.ok) throw new Error('http ' + r.status); return r.json(); })
      .then(function (d) {
        datos = d;
        d.municipios.forEach(function (m) {
          var op = document.createElement('option');
          op.value = m.codigo; op.textContent = m.nombre;
          selMunicipio.appendChild(op);
        });
        dibujar(true);
      })
      .catch(function () { estado.textContent = 'No se pudo cargar el mapa. Puede ver la misma información en la tabla de prioridades.'; });
  }

  document.getElementById('controles').addEventListener('change', function () { dibujar(true); });
  var pendiente = null;
  mapa.on('zoomend', function () {  // al acercar o alejar cambian el tamaño y los números, sin mover el mapa
    clearTimeout(pendiente);
    pendiente = setTimeout(function () { dibujar(false); }, 120);
  });
  cargar();
})();
