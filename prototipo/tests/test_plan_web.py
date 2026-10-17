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
