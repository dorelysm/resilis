def sub(p, pares):
    t = open(p, encoding='utf-8').read()
    for a, b in pares:
        assert a in t, (p, a[:90])
        t = t.replace(a, b, 1)
    open(p, 'w', encoding='utf-8', newline='\n').write(t)


# ---------------- Python
sub('app/rutas/plan.py', [
    ('''    texto = f"Plan aprobado: {r['asignadas']} solicitud(es) asignadas, cada una con su código de entrega."''',
     '''    texto = f"Plan aprobado: {plural(r['asignadas'], 'solicitud asignada', 'solicitudes asignadas')}, cada una con su código de entrega."'''),
    ('''    texto = f"Paquete aprobado: {r['asignadas']} entrega(s) asignadas, cada una con su código."''',
     '''    texto = f"Paquete aprobado: {plural(r['asignadas'], 'entrega asignada', 'entregas asignadas')}, cada una con su código."'''),
    ('from app.config import get_settings\n', 'from app.config import get_settings\nfrom app.formato import plural\n'),
])
sub('app/plan.py', [
    ('''    return f"vence en {dias:.0f} día(s)" if dias >= 1 else "vence en menos de un día"''',
     '''    return f"vence en {plural(round(dias), 'día', 'días')}" if dias >= 1 else "vence en menos de un día"'''),
    ('from app.models import ahora\n', 'from app.formato import plural\nfrom app.models import ahora\n'),
])
sub('app/recorrido.py', [
    ('''f"Daño nivel {rep.nivel_dano} · {rep.personas_afectadas} persona(s)"''',
     '''f"Daño nivel {rep.nivel_dano} · {plural(rep.personas_afectadas, 'persona', 'personas')}"'''),
    ('from app import models as m\n', 'from app import models as m\nfrom app.formato import plural\n'),
])
sub('app/ruta.py', [
    ('''    texto = (f"Su ayuda va a {total} entrega(s) en {len(lista)} barrio(s): "
             f"{sum(d['entregadas'] for d in lista)} entregada(s), {sum(d['en_camino'] for d in lista)} en camino."''',
     '''    texto = (f"Su ayuda va a {plural(total, 'entrega', 'entregas')} en {plural(len(lista), 'barrio', 'barrios')}: "
             f"{plural(sum(d['entregadas'] for d in lista), 'entregada', 'entregadas')}, "
             f"{sum(d['en_camino'] for d in lista)} en camino."'''),
    ('''f"{sum(1 for f in filas if f['etapa'] == 'asignada')} por salir, {entregadas} entregada(s).")}''',
     '''f"{sum(1 for f in filas if f['etapa'] == 'asignada')} por salir, {plural(entregadas, 'entregada', 'entregadas')}.")}'''),
    ('from app import models as m\n', 'from app import models as m\nfrom app.formato import plural\n'),
])

# ---------------- JavaScript
sub('app/static/ruta.js', [
    ("    if (d.entregadas) partes.push(d.entregadas + ' entregada(s)');",
     "    if (d.entregadas) partes.push(d.entregadas + (d.entregadas === 1 ? ' entregada' : ' entregadas'));"),
])
sub('app/static/mapa.js', [
    ("'<br>' + s.n_reportes + ' reporte(s), ' + s.n_solicitudes + ' solicitud(es) abiertas' + listaNecesidades(s, tipos) +",
     "'<br>' + plural(s.n_reportes, 'reporte', 'reportes') + ', ' + plural(s.n_solicitudes, 'solicitud abierta', 'solicitudes abiertas') + listaNecesidades(s, tipos) +"),
    ("  function pct(valor) { return Math.round(valor * 100) + ' %'; }\n",
     "  function pct(valor) { return Math.round(valor * 100) + ' %'; }\n\n"
     "  function plural(n, singular, plurales) { return n + ' ' + (n === 1 ? singular : plurales); }\n"),
    ("conInfo: conInfo,", "conInfo: conInfo, plural: plural,"),
])
print('ok')
