"""Flujo completo por la web: donación, recepción, solicitud, verificación, asignación, código y entrega."""
import json
import re

import pytest
from sqlalchemy import select

from app import models as m
from app import servicios as sv
from app.config import get_settings
from tests.test_web import (  # noqa: F401  (los fixtures se registran al importarlos)
    CLAVE, _Revisor, app_cliente, crear_usuario, csrf, entrar, mundo, sesiones,
)


def salir(c):
    c.post("/salir", data={"csrf": csrf(c, "/")})


@pytest.fixture()
def equipo_completo(sesiones, mundo):
    """Cuentas de cada rol, un centro de acopio y un donante con una donación de 100 litros por recibir."""
    ids = {
        "solicitante": crear_usuario(sesiones, m.Rol.SOLICITANTE, "3100000001", barrio_id=mundo["barrio_id"]),
        "otro": crear_usuario(sesiones, m.Rol.SOLICITANTE, "3100000002", barrio_id=mundo["barrio_id"]),
        "brigadista": crear_usuario(sesiones, m.Rol.BRIGADISTA, "3100000003"),
        "entidad": crear_usuario(sesiones, m.Rol.ENTIDAD, "3100000004"),
        "equipo": crear_usuario(sesiones, m.Rol.EQUIPO_ENTREGA, "3100000005"),
        "equipo2": crear_usuario(sesiones, m.Rol.EQUIPO_ENTREGA, "3100000006"),
        "acopio": crear_usuario(sesiones, m.Rol.CENTRO_ACOPIO, "3100000007"),
        "admin": crear_usuario(sesiones, m.Rol.ADMINISTRADOR, "3100000008"),
    }
    with sesiones() as db:
        db.add(m.CentroAcopio(nombre="Centro de prueba", barrio_id=mundo["barrio_id"], responsable_id=ids["acopio"]))
        d = m.Donante(nombre="Donante de prueba", tipo="persona")
        db.add(d)
        db.flush()
        don = m.Donacion(donante_id=d.id, tipo_bien="agua", cantidad=100, unidad="litros")
        db.add(don)
        db.commit()
        ids["donacion"] = don.id
    return ids


def recibir_inventario(c, ids, cantidad=100):
    entrar(c, "3100000007")
    r = c.post(f"/recepcion/{ids['donacion']}", follow_redirects=False,
               data={"cantidad": str(cantidad), "estado_producto": "nuevo", "csrf": csrf(c, "/recepcion")})
    salir(c)
    return r


def pedir(c, mundo, telefono="3100000001", hogar="2"):
    entrar(c, telefono)
    r = c.post("/solicitudes/nueva", follow_redirects=False, data={
        "barrio_id": str(mundo["barrio_id"]), "necesidad": "agua", "personas_hogar": hogar, "urgencia": "2",
        "descripcion": "No tenemos agua potable.", "direccion": "Calle 1 # 2-3", "csrf": csrf(c, "/solicitudes/nueva")})
    salir(c)
    return r


def verificar(c, sol_id, telefono="3100000003", resultado="verificado", nota="Comprobado en la vivienda"):
    entrar(c, telefono)
    r = c.post(f"/verificacion/solicitudes/{sol_id}", follow_redirects=False,
               data={"resultado": resultado, "nota": nota, "csrf": csrf(c, f"/verificacion/solicitudes/{sol_id}")})
    salir(c)
    return r


def asignar(c, sol_id, equipo_id):
    entrar(c, "3100000004")
    r = c.post(f"/asignacion/{sol_id}", follow_redirects=False,
               data={"equipo_id": str(equipo_id), "csrf": csrf(c, "/asignacion")})
    salir(c)
    return r


def codigo_visible(c, sol_id, telefono="3100000001"):
    entrar(c, telefono)
    html = c.get(f"/solicitudes/{sol_id}").text
    salir(c)
    hallado = re.search(r'class="codigo"[^>]*>([A-Z0-9]{4}-[A-Z0-9]{4})<', html)
    return hallado.group(1) if hallado else None


def flujo_hasta_asignar(c, ids, mundo):
    recibir_inventario(c, ids)
    pedir(c, mundo)
    verificar(c, 1)
    return asignar(c, 1, ids["equipo"])


# ----------------------------------------------------------------------------- flujo completo
def test_flujo_completo_hasta_cerrar(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    assert recibir_inventario(c, ids).status_code == 303
    with sesiones() as db:
        lote = db.scalar(select(m.Lote))
        assert (lote.cantidad_recibida, lote.cantidad_disponible) == (100, 100)

    assert pedir(c, mundo).status_code == 303
    assert verificar(c, 1).status_code == 303
    assert asignar(c, 1, ids["equipo"]).status_code == 303
    with sesiones() as db:
        lote, sol = db.scalar(select(m.Lote)), db.get(m.Solicitud, 1)
        assert (lote.cantidad_disponible, lote.cantidad_reservada) == (88, 12)  # 2 personas x 6 litros
        assert sol.estado == "asignada"

    codigo = codigo_visible(c, 1)
    assert codigo, "la persona debe ver su código"

    # El equipo ve a quién entregar, pero el código no aparece en ningún lado de su pantalla ni de su JSON
    entrar(c, "3100000005")
    pagina = c.get("/entregas").text
    assert "Calle 1 # 2-3" in pagina and codigo not in pagina and codigo.replace("-", "") not in pagina
    datos = c.get("/entregas/datos.json")
    assert datos.status_code == 200 and codigo.replace("-", "") not in datos.text
    entrega = datos.json()["entregas"][0]
    assert sv.huella_codigo(entrega["sal"], codigo) == entrega["huella"]  # lo que valida el teléfono sin conexión

    c.post("/entregas/1/en-camino", data={"csrf": csrf(c, "/entregas")})
    mal = c.post("/entregas/1/confirmar", data={"codigo": "ZZZZ-ZZZZ", "csrf": csrf(c, "/entregas")})
    assert "no es correcto" in mal.text
    bien = c.post("/entregas/1/confirmar", data={"codigo": codigo.lower(), "csrf": csrf(c, "/entregas")})
    assert "Entrega confirmada" in bien.text
    salir(c)
    with sesiones() as db:
        lote, sol = db.scalar(select(m.Lote)), db.get(m.Solicitud, 1)
        assert (lote.cantidad_disponible, lote.cantidad_reservada, lote.cantidad_entregada) == (88, 0, 12)
        assert sol.estado == "entregada"

    entrar(c, "3100000001")
    assert "Sí, ya la recibí" in c.get("/solicitudes/1").text
    c.post("/solicitudes/1/confirmar", data={"csrf": csrf(c, "/solicitudes/1")})
    salir(c)
    with sesiones() as db:
        assert db.get(m.Solicitud, 1).estado == "cerrada"

    entrar(c, "3100000008")  # la cadena de eventos queda íntegra
    assert "La cadena está íntegra" in c.get("/admin/auditoria").text


def test_el_solicitante_ve_el_seguimiento_y_solo_el_suyo(app_cliente, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    flujo_hasta_asignar(c, ids, mundo)
    entrar(c, "3100000001")
    pagina = c.get("/solicitudes/1").text
    assert "Verificaron su solicitud" in pagina and "Se asignó un equipo" in pagina
    assert "Su código de entrega" in pagina and c.get("/solicitudes/1/ficha").status_code == 200
    salir(c)
    entrar(c, "3100000002")  # otra persona no puede ver la solicitud ajena
    assert c.get("/solicitudes/1").status_code == 404


# ----------------------------------------------------------------------------- permisos
def test_permisos_por_rol(app_cliente, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    flujo_hasta_asignar(c, ids, mundo)
    entrar(c, "3100000001")
    for ruta in ("/verificacion", "/asignacion", "/inventario", "/recepcion", "/entregas", "/entregas/datos.json"):
        assert c.get(ruta).status_code == 403, ruta
    salir(c)
    entrar(c, "3100000003")  # un brigadista verifica, pero no asigna
    assert c.get("/verificacion").status_code == 200 and c.get("/asignacion").status_code == 403
    salir(c)
    entrar(c, "3100000006")  # otro equipo no puede tocar una entrega ajena
    assert c.post("/entregas/1/confirmar", data={"codigo": "AAAAAAAA", "csrf": csrf(c, "/entregas")}).status_code == 404
    assert c.get("/entregas/datos.json").json()["entregas"] == []


def test_no_se_asigna_sin_inventario(app_cliente, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    pedir(c, mundo)
    verificar(c, 1)
    entrar(c, "3100000004")
    pagina = c.get("/asignacion").text
    assert "no alcanza" in pagina
    r = c.post("/asignacion/1", data={"equipo_id": str(ids["equipo"]), "csrf": csrf(c, "/asignacion")})
    assert "No hay inventario suficiente" in r.text


def test_desmentir_exige_motivo_y_anula(app_cliente, sesiones, equipo_completo, mundo):
    c = app_cliente
    pedir(c, mundo)
    entrar(c, "3100000003")
    r = c.post("/verificacion/solicitudes/1", data={"resultado": "desmentido", "nota": "",
                                                    "csrf": csrf(c, "/verificacion/solicitudes/1")})
    assert "escriba el motivo" in r.text
    salir(c)
    verificar(c, 1, resultado="desmentido", nota="La dirección no existe")
    with sesiones() as db:
        assert db.get(m.Solicitud, 1).estado == "anulada"


# ----------------------------------------------------------------------------- uso sin conexión
def _sincronizar(c, entregas):
    token = re.search(r'name="csrf" content="([^"]+)"', c.get("/entregas").text).group(1)
    return c.post("/entregas/sincronizar", content=json.dumps({"entregas": entregas}),
                  headers={"Content-Type": "application/json", "X-CSRF-Token": token})


def test_sincronizar_entregas_hechas_sin_conexion(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    flujo_hasta_asignar(c, ids, mundo)
    codigo = codigo_visible(c, 1)
    entrar(c, "3100000005")

    assert _sincronizar(c, [{"id": 1, "codigo": "MALO-MALO"}]).json()["resultados"][0]["ok"] is False
    ok = _sincronizar(c, [{"id": 1, "codigo": codigo.replace("-", "")}]).json()["resultados"][0]
    assert ok["ok"] is True and ok["repetida"] is False
    repetido = _sincronizar(c, [{"id": 1, "codigo": codigo}]).json()["resultados"][0]  # reintento tras perder la red
    assert repetido["ok"] is True and repetido["repetida"] is True
    with sesiones() as db:
        assert db.scalar(select(m.Lote.cantidad_entregada)) == 12  # no se descontó dos veces
    ajena = _sincronizar(c, [{"id": 999, "codigo": codigo}]).json()["resultados"][0]
    assert ajena["ok"] is False


def test_sincronizar_exige_token_y_formato(app_cliente, equipo_completo):
    c = app_cliente
    entrar(c, "3100000005")
    sin_token = c.post("/entregas/sincronizar", content=json.dumps({"entregas": []}),
                       headers={"Content-Type": "application/json"})
    assert sin_token.status_code == 403
    assert _sincronizar(c, "no es una lista").status_code == 400


def test_incidencia_libera_y_se_puede_reasignar(app_cliente, sesiones, equipo_completo, mundo):
    c, ids = app_cliente, equipo_completo
    flujo_hasta_asignar(c, ids, mundo)
    primero = codigo_visible(c, 1)
    entrar(c, "3100000005")
    c.post("/entregas/1/incidencia", data={"tipo": "no_encontrada", "nota": "No estaba",
                                           "csrf": csrf(c, "/entregas")})
    salir(c)
    with sesiones() as db:
        assert db.scalar(select(m.Lote.cantidad_disponible)) == 100  # se liberó lo reservado
        assert db.get(m.Solicitud, 1).estado == "verificada"
    asignar(c, 1, ids["equipo2"])
    nuevo = codigo_visible(c, 1)
    assert nuevo and nuevo != primero
    entrar(c, "3100000005")  # el equipo anterior ya no ve la entrega
    assert c.get("/entregas/datos.json").json()["entregas"] == []


def test_el_service_worker_se_sirve_desde_la_raiz(app_cliente):
    r = app_cliente.get("/sw.js")
    assert r.status_code == 200 and r.headers["service-worker-allowed"] == "/"


# ----------------------------------------------------------------------------- administración y accesibilidad
def test_el_administrador_crea_un_centro_de_acopio_con_su_inventario(app_cliente, sesiones, equipo_completo):
    c = app_cliente
    entrar(c, "3100000008")
    c.post("/admin/usuarios", data={"nombre": "Parroquia Central", "telefono": "3155550000", "rol": "centro_acopio",
                                    "password": CLAVE, "csrf": csrf(c, "/admin/usuarios")})
    with sesiones() as db:
        resp = db.scalar(select(m.Usuario).where(m.Usuario.telefono == "3155550000"))
        assert db.scalar(select(m.CentroAcopio).where(m.CentroAcopio.responsable_id == resp.id)) is not None


@pytest.mark.parametrize("ruta,telefono", [
    ("/verificacion", "3100000003"), ("/verificacion/solicitudes/1", "3100000003"), ("/recepcion", "3100000007"),
    ("/inventario", "3100000007"), ("/asignacion", "3100000004"), ("/entregas", "3100000005"),
    ("/solicitudes/1", "3100000001"), ("/admin/auditoria", "3100000008"),
])
def test_paginas_de_operacion_son_accesibles(app_cliente, equipo_completo, mundo, ruta, telefono):
    flujo_hasta_asignar(app_cliente, equipo_completo, mundo)
    entrar(app_cliente, telefono)
    r = app_cliente.get(ruta)
    assert r.status_code == 200
    revisor = _Revisor()
    revisor.feed(r.text)
    assert revisor.lang == "es" and revisor.ids <= revisor.para, f"campos sin etiqueta: {revisor.ids - revisor.para}"
