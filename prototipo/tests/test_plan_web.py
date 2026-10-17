import re

import pytest
from sqlalchemy import select

from app import models as m
from tests.test_operacion import (  # noqa: F401
    _Revisor, app_cliente, crear_usuario, csrf, entrar, equipo_completo, mundo, pedir, recibir_inventario, salir,
    sesiones, verificar,
)


def preparar(c, ids, mundo, solicitudes=2, inventario=500, hogar="2"):
    recibir_inventario(c, ids, inventario)
    for _ in range(solicitudes):
        pedir(c, mundo, hogar=hogar)
    for n in range(1, solicitudes + 1):
        verificar(c, n)


def calcular(c):
    return c.post("/plan/calcular", follow_redirects=False, data={"csrf": csrf(c, "/plan")})


def test_solo_la_entidad_ve_el_plan(app_cliente, equipo_completo):
    c = app_cliente
    assert c.get("/plan", follow_redirects=False).status_code == 303  # sin sesión
    for telefono in ("3100000001", "3100000003", "3100000005", "3100000008"):  # solicitante, brigadista, equipo, admin
        entrar(c, telefono)
        assert c.get("/plan").status_code == 403, telefono
        assert c.post("/plan/calcular", data={"csrf": csrf(c, "/")}).status_code == 403
        salir(c)
    entrar(c, "3100000004")
    assert c.get("/plan").status_code == 200


def test_sin_solicitudes_verificadas_avisa(app_cliente, equipo_completo):
    c = app_cliente
    entrar(c, "3100000004")
    pagina = c.get("/plan").text
    assert "Todavía no se ha calculado ningún plan" in pagina
    r = calcular(c)
    assert r.status_code == 303
    assert "No hay nada que planear" in c.get("/plan").text


def test_calcular_mostrar_y_aprobar_el_plan(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    preparar(c, ids, mundo)
    entrar(c, "3100000004")
    assert calcular(c).status_code == 303
    pagina = c.get("/plan").text
    assert "El plan está listo" in pagina or "Plan 1" in pagina
    assert "Cubre <strong>24 de 24</strong>" in pagina  # 2 solicitudes de 2 personas x 6 litros
    assert "Asignación de referencia" in pagina and "Aprobar este paquete" in pagina
    assert "hasta entonces no se reserva nada" in pagina
    with sesiones() as db:
        assert db.scalar(select(m.Entrega)) is None  # calcular no reservó nada

    r = c.post("/plan/1/aprobar", follow_redirects=False, data={
        "csrf": csrf(c, "/plan"), "equipo_1": str(ids["equipo"]), "equipo_2": str(ids["equipo2"])})
    assert r.status_code == 303
    assert "Plan aprobado: 2 solicitud" in c.get("/plan").text
    with sesiones() as db:
        entregas = db.scalars(select(m.Entrega).order_by(m.Entrega.solicitud_id)).all()
        assert [e.equipo_id for e in entregas] == [ids["equipo"], ids["equipo2"]]
        assert db.get(m.PlanAsignacion, 1).estado == "aprobado"
        assert db.scalar(select(m.Lote.cantidad_reservada)) == 24


def test_la_entidad_puede_excluir_solicitudes_del_plan(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    preparar(c, ids, mundo)
    entrar(c, "3100000004")
    calcular(c)
    c.post("/plan/1/aprobar", data={"csrf": csrf(c, "/plan"), "excluir_2": "si", "equipo_1": str(ids["equipo"]),
                                    "equipo_2": str(ids["equipo"])})
    with sesiones() as db:
        assert db.get(m.Solicitud, 1).estado == "asignada" and db.get(m.Solicitud, 2).estado == "verificada"


def test_rechazar_el_plan_no_reserva_nada(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    preparar(c, ids, mundo)
    entrar(c, "3100000004")
    calcular(c)
    c.post("/plan/1/rechazar", data={"csrf": csrf(c, "/plan"), "motivo": "Quiero revisar a mano"})
    pagina = c.get("/plan").text
    assert "Rechazado" in pagina and "Quiero revisar a mano" in pagina and "Aprobar este paquete" not in pagina
    with sesiones() as db:
        assert db.scalar(select(m.Lote.cantidad_reservada)) == 0
    assert "ya fue resuelto" in c.post("/plan/1/rechazar", data={"csrf": csrf(c, "/plan")}, follow_redirects=True).text


def test_no_se_puede_aprobar_dos_veces_ni_sin_token(app_cliente, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    preparar(c, ids, mundo, solicitudes=1)
    entrar(c, "3100000004")
    calcular(c)
    assert c.post("/plan/1/aprobar", data={"equipo_1": "1"}).status_code == 403  # sin token CSRF
    c.post("/plan/1/aprobar", data={"csrf": csrf(c, "/plan"), "equipo_1": str(ids["equipo"])})
    pagina = c.post("/plan/1/aprobar", data={"csrf": csrf(c, "/plan")}, follow_redirects=True).text
    assert "ya fue resuelto" in pagina
    assert c.post("/plan/999/aprobar", data={"csrf": csrf(c, "/plan")}).status_code == 404


def test_cuando_falta_inventario_el_plan_dice_lo_que_queda_sin_cubrir(app_cliente, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    preparar(c, ids, mundo, solicitudes=3, inventario=20, hogar="2")  # piden 36 y hay 20
    entrar(c, "3100000004")
    calcular(c)
    pagina = c.get("/plan").text
    assert "Cubre <strong>20 de 36</strong>" in pagina and "Lo que queda sin cubrir" in pagina
    assert "Faltan" in pagina


def test_los_parametros_se_validan_y_se_guardan(app_cliente, sesiones, equipo_completo):
    c = app_cliente
    entrar(c, "3100000004")
    malo = c.post("/plan/parametros", data={"csrf": csrf(c, "/plan"), "theta": "2", "kappa": "abc", "lambda": "0.001"})
    assert malo.status_code == 422 and "entre 0 y 1" in malo.text and "Escriba un número" in malo.text
    bueno = c.post("/plan/parametros", follow_redirects=False,
                   data={"csrf": csrf(c, "/plan"), "theta": "0,5", "kappa": "0.05", "lambda": "0.002"})
    assert bueno.status_code == 303
    with sesiones() as db:
        valores = {p.dimension: p.valor for p in db.scalars(select(m.Peso).where(m.Peso.ambito == "plan"))}
        assert valores == {"theta": 0.5, "kappa": 0.05, "lambda": 0.002}


def test_la_pagina_del_plan_es_accesible(app_cliente, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    preparar(c, ids, mundo)
    entrar(c, "3100000004")
    calcular(c)
    r = c.get("/plan")
    assert r.status_code == 200
    revisor = _Revisor()
    revisor.feed(r.text)
    assert revisor.lang == "es" and revisor.ids <= revisor.para, f"campos sin etiqueta: {revisor.ids - revisor.para}"


def test_despues_de_aprobar_el_plan_la_persona_ve_su_codigo(app_cliente, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    preparar(c, ids, mundo, solicitudes=1)
    entrar(c, "3100000004")
    calcular(c)
    c.post("/plan/1/aprobar", data={"csrf": csrf(c, "/plan"), "equipo_1": str(ids["equipo"])})
    salir(c)
    entrar(c, "3100000001")
    pagina = c.get("/solicitudes/1").text
    assert re.search(r'class="codigo"[^>]*>[A-Z0-9]{4}-[A-Z0-9]{4}<', pagina) and "Equipo asignado" in pagina


def _plan_grande(c, ids, mundo, sesiones, n=45):
    recibir_inventario(c, ids, 1000)
    with sesiones() as db:
        for _ in range(n):
            db.add(m.Solicitud(solicitante_id=ids["solicitante"], creador_id=ids["solicitante"],
                               barrio_id=mundo["barrio_id"], necesidad="agua", cantidad=6, personas_hogar=1,
                               estado="verificada"))
        db.commit()
    entrar(c, "3100000004")
    calcular(c)


def test_un_plan_grande_se_divide_en_paquetes_pequenos(app_cliente, sesiones, equipo_completo, mundo):
    """Una persona en una emergencia revisa un paquete corto, no 45 solicitudes a la vez."""
    c, ids = app_cliente, equipo_completo
    _plan_grande(c, ids, mundo, sesiones)
    pagina = c.get("/plan").text
    assert pagina.count('name="excluir_') == 6  # un solo paquete abierto, de 6 entregas
    assert "Siguiente: paquete 1" in pagina and "0 de 8</strong> paquetes resueltos" in pagina
    assert "Los que siguen" in pagina and "Aprobar este paquete" in pagina
    with sesiones() as db:
        from app import plan as pl

        plan = db.get(m.PlanAsignacion, 1)
        paquetes = pl.armar_paquetes(db, plan)
        assert [len(p["solicitudes"]) for p in paquetes] == [6] * 7 + [3]
        assert sorted(j for p in paquetes for j in p["solicitudes"]) == sorted(
            l.solicitud_id for l in db.scalars(select(m.PlanLinea)).all())  # nada se pierde ni se repite


def test_aprobar_un_paquete_asigna_solo_ese_y_el_plan_sigue_abierto(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    _plan_grande(c, ids, mundo, sesiones)
    pagina = c.get("/plan").text
    solicitudes = re.search(r'name="solicitudes" value="([\d,]+)"', pagina).group(1)
    primera = solicitudes.split(",")[0]
    r = c.post("/plan/1/paquete", follow_redirects=False, data={
        "csrf": csrf(c, "/plan"), "solicitudes": solicitudes, "equipo": str(ids["equipo"]), f"excluir_{primera}": "si"})
    assert r.status_code == 303
    with sesiones() as db:
        asignadas = db.scalars(select(m.Solicitud).where(m.Solicitud.estado == "asignada")).all()
        assert len(asignadas) == 5 and int(primera) not in {s.id for s in asignadas}  # la de "dejar fuera" no sale
        assert {e.equipo_id for e in db.scalars(select(m.Entrega))} == {ids["equipo"]}  # todas con el mismo equipo
        assert db.get(m.PlanAsignacion, 1).estado == "propuesto"
    pagina = c.get("/plan").text
    assert "1 de 8</strong> paquetes resueltos" in pagina and "Siguiente: paquete 2" in pagina
    assert "Rechazar el plan" not in pagina  # ya hay entregas aprobadas: no se puede rechazar todo
    otra = c.post("/plan/1/paquete", data={"csrf": csrf(c, "/plan"), "solicitudes": solicitudes,
                                           "equipo": str(ids["equipo"])}, follow_redirects=True).text
    assert "ya se resolvió" in otra  # no se aprueba dos veces


def test_al_resolver_todos_los_paquetes_el_plan_queda_aprobado(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    _plan_grande(c, ids, mundo, sesiones, n=8)  # 2 paquetes: 6 y 2
    for _ in range(2):
        pagina = c.get("/plan").text
        solicitudes = re.search(r'name="solicitudes" value="([\d,]+)"', pagina).group(1)
        c.post("/plan/1/paquete", data={"csrf": csrf(c, "/plan"), "solicitudes": solicitudes, "equipo": str(ids["equipo"])})
    with sesiones() as db:
        plan = db.get(m.PlanAsignacion, 1)
        assert plan.estado == "aprobado" and plan.aprobado_por is not None
        assert len(db.scalars(select(m.Entrega)).all()) == 8
    assert "Este plan ya se resolvió" in c.get("/plan").text


def test_un_paquete_inventado_o_sin_equipo_se_rechaza(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    _plan_grande(c, ids, mundo, sesiones, n=8)
    inventado = c.post("/plan/1/paquete", data={"csrf": csrf(c, "/plan"), "solicitudes": "1,2", "equipo": str(ids["equipo"])},
                       follow_redirects=True).text
    assert "no existe en este plan" in inventado
    sin = c.post("/plan/1/paquete", data={"csrf": csrf(c, "/plan"), "solicitudes": "1,2,3,4,5,6"}, follow_redirects=True).text
    assert "Elija el equipo" in sin
    assert c.post("/plan/1/paquete", data={"solicitudes": "1", "equipo": "1"}).status_code == 403  # sin token CSRF
    with sesiones() as db:
        assert db.scalar(select(m.Entrega)) is None


# ----------------------------------------------------------------------------- aprobar varios paquetes y filtrar por municipio
def _con_dos_municipios(c, ids, mundo, sesiones, en_el_primero=14, en_el_segundo=8):
    """El municipio 08001 (14 solicitudes = 3 paquetes) y Soledad 08758 (8 = 2 paquetes), todas verificadas."""
    recibir_inventario(c, ids, 1000)
    with sesiones() as db:
        db.add(m.Municipio(codigo="08758", nombre="Soledad"))
        db.flush()
        otro = m.Barrio(municipio_codigo="08758", nombre="Barrio de Soledad", personas=500, viviendas=150)
        db.add(otro)
        db.flush()
        for barrio, n in ((mundo["barrio_id"], en_el_primero), (otro.id, en_el_segundo)):
            for _ in range(n):
                db.add(m.Solicitud(solicitante_id=ids["solicitante"], creador_id=ids["solicitante"], barrio_id=barrio,
                                   necesidad="agua", cantidad=6, personas_hogar=1, estado="verificada"))
        db.commit()
    entrar(c, "3100000004")
    calcular(c)


def test_aprobar_los_siguientes_paquetes_los_resuelve_en_orden_y_reparte_entre_equipos(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    _plan_grande(c, ids, mundo, sesiones, n=45)  # 8 paquetes
    pagina = c.get("/plan").text
    assert "Aprobar varios paquetes de una vez" in pagina and 'action="/plan/1/siguientes"' in pagina
    opciones = pagina.split('id="cuantos"')[1].split("</select>")[0]
    assert 'value="5"' in opciones and 'value="8"' in opciones and 'value="10"' not in opciones  # solo opciones que tienen sentido
    r = c.post("/plan/1/siguientes", follow_redirects=False, data={"csrf": csrf(c, "/plan"), "cuantos": "5"})
    assert r.status_code == 303 and r.headers["location"] == "/plan"
    assert "5 paquetes aprobados: 30 entregas asignadas" in c.get("/plan").text  # el aviso aparece una vez
    with sesiones() as db:
        entregas = db.scalars(select(m.Entrega)).all()
        assert len(entregas) == 30  # 5 paquetes de 6
        por_equipo = {}
        for e in entregas:
            por_equipo[e.equipo_id] = por_equipo.get(e.equipo_id, 0) + 1
        assert set(por_equipo) == {ids["equipo"], ids["equipo2"]} and abs(por_equipo[ids["equipo"]] - por_equipo[ids["equipo2"]]) <= 6
        assert db.get(m.PlanAsignacion, 1).estado == "propuesto"
    despues = c.get("/plan").text
    assert "5 de 8</strong> paquetes resueltos" in despues and "Siguiente: paquete 6" in despues


def test_aprobar_todos_los_pendientes_cierra_el_plan_y_no_se_repite(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    _plan_grande(c, ids, mundo, sesiones, n=14)  # 3 paquetes
    texto = c.post("/plan/1/siguientes", data={"csrf": csrf(c, "/plan"), "cuantos": "3"}, follow_redirects=True).text
    assert "3 paquetes aprobados" in texto and "14 entregas asignadas" in texto
    with sesiones() as db:
        assert db.get(m.PlanAsignacion, 1).estado == "aprobado" and len(db.scalars(select(m.Entrega)).all()) == 14
    de_nuevo = c.post("/plan/1/siguientes", data={"csrf": csrf(c, "/plan"), "cuantos": "3"}, follow_redirects=True).text
    assert "ya fue resuelto" in de_nuevo
    with sesiones() as db:
        assert len(db.scalars(select(m.Entrega)).all()) == 14


def test_el_filtro_por_municipio_solo_muestra_y_aprueba_los_de_ese_municipio(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    _con_dos_municipios(c, ids, mundo, sesiones)  # 5 paquetes: 3 de 08001 y 2 de 08758
    todo = c.get("/plan").text
    assert 'id="municipio"' in todo and "Soledad" in todo and "Barranquilla" in todo
    filtrada = c.get("/plan?municipio=08758").text
    assert "Siguiente: paquete" in filtrada and "Soledad" in filtrada.split('id="varios"')[0].split("Siguiente: paquete")[1][:80]
    assert "Quedan 2 paquetes (8 entregas)" in filtrada and 'name="municipio" value="08758"' in filtrada
    r = c.post("/plan/1/siguientes", follow_redirects=False,
               data={"csrf": csrf(c, "/plan"), "cuantos": "10", "municipio": "08758"})
    assert r.headers["location"] == "/plan?municipio=08758"
    with sesiones() as db:
        sols = {e.solicitud_id for e in db.scalars(select(m.Entrega))}
        barrios = {db.get(m.Solicitud, j).barrio_id for j in sols}
        assert len(sols) == 8 and len(barrios) == 1 and mundo["barrio_id"] not in barrios  # solo Soledad
    assert "2 de 5</strong> paquetes resueltos" in c.get("/plan").text


def test_aprobar_varios_exige_numero_valido_equipos_y_token(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    _plan_grande(c, ids, mundo, sesiones, n=14)
    for malo in ("", "0", "-1", "abc", "51", "2.5"):
        texto = c.post("/plan/1/siguientes", data={"csrf": csrf(c, "/plan"), "cuantos": malo}, follow_redirects=True).text
        assert "Elija cuántos paquetes aprobar" in texto, malo
    assert c.post("/plan/1/siguientes", data={"cuantos": "2"}).status_code == 403  # sin token
    assert c.post("/plan/99/siguientes", data={"csrf": csrf(c, "/plan"), "cuantos": "2"}).status_code == 404
    with sesiones() as db:
        assert db.scalar(select(m.Entrega)) is None
        for e in db.scalars(select(m.Usuario).where(m.Usuario.rol == m.Rol.EQUIPO_ENTREGA)):
            e.aprobado = False
        db.commit()
    sin_equipos = c.post("/plan/1/siguientes", data={"csrf": csrf(c, "/plan"), "cuantos": "2"}, follow_redirects=True).text
    assert "No hay equipos de entrega aprobados" in sin_equipos
    with sesiones() as db:
        assert db.scalar(select(m.Entrega)) is None
    salir(c)
    entrar(c, "3100000003")  # un brigadista no aprueba planes
    assert c.post("/plan/1/siguientes", data={"cuantos": "2"}).status_code == 403


def test_asignar_a_mano_ahora_cuelga_del_plan_y_no_del_menu(app_cliente, equipo_completo):
    c = app_cliente
    entrar(c, "3100000004")
    inicio = c.get("/").text
    menu = inicio[inicio.index('id="menu-principal"'):inicio.index("</nav>")]
    assert 'href="/plan"' in menu and 'href="/asignacion"' not in menu and "Asignar entregas" not in inicio
    plan = c.get("/plan").text
    assert 'href="/asignacion"' in plan and "Asignar a mano una solicitud" in plan
    manual = c.get("/asignacion").text
    assert "Asignar a mano" in manual and 'href="/plan"' in manual and "Volver al plan" in manual
