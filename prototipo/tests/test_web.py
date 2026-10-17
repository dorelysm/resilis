import re
from html.parser import HTMLParser

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app import main
from app.cargas import cargar_viviendas
from app.db import get_db
from app.models import (
    Donacion, Donante, Evento, Municipio, ReporteDanos, Rol, Barrio, Solicitud, Usuario, Vulnerabilidad, ahora,
)
from app.seguridad import hash_password, verificar_password

CLAVE = "clave-de-prueba-123"


@pytest.fixture()
def sesiones(engine):
    return sessionmaker(bind=engine, expire_on_commit=False)


@pytest.fixture()
def mundo(sesiones):
    """Un municipio, un barrio y un evento."""
    with sesiones() as db:
        db.add(Municipio(codigo="08001", nombre="Barranquilla"))
        db.flush()
        s = Barrio(municipio_codigo="08001", nombre="Barrio de prueba", personas=1000, viviendas=300)
        db.add(s)
        db.add(Evento(tipo="inundacion", nombre="Evento de prueba"))
        db.commit()
        return {"barrio_id": s.id}


@pytest.fixture()
def app_cliente(sesiones, monkeypatch):
    def _db():
        with sesiones() as s:
            yield s

    main.app.dependency_overrides[get_db] = _db
    monkeypatch.setattr(main, "crear_tablas", lambda: None)
    with TestClient(main.app) as c:
        yield c
    main.app.dependency_overrides.clear()


def crear_usuario(sesiones, rol, telefono, **extra):
    with sesiones() as db:
        u = Usuario(nombre=f"Usuario {rol}", telefono=telefono, rol=rol, password_hash=hash_password(CLAVE),
                    consentimiento_datos=True, consentimiento_fecha=ahora(), ficticio=False, **extra)
        db.add(u)
        db.commit()
        return u.id


def csrf(c, url):
    r = c.get(url)
    return re.search(r'name="csrf" value="([^"]+)"', r.text).group(1)


def entrar(c, telefono, clave=CLAVE):
    return c.post("/entrar", data={"telefono": telefono, "password": clave, "csrf": csrf(c, "/entrar")},
                  follow_redirects=False)


def registrar(c, mundo, **cambios):
    datos = {"nombre": "María Prueba", "telefono": "3001112233", "barrio_id": str(mundo["barrio_id"]),
             "tipo_cuenta": "solicitante", "password": CLAVE, "password2": CLAVE, "consentimiento": "si"}
    datos.update(cambios)
    datos["csrf"] = csrf(c, "/registro")
    return c.post("/registro", data=datos, follow_redirects=False)


# ----------------------------------------------------------------------------- seguridad básica
def test_la_contrasena_no_se_guarda_en_claro():
    h = hash_password(CLAVE)
    assert CLAVE not in h and h.startswith("scrypt$")
    assert verificar_password(CLAVE, h) and not verificar_password("otra", h)
    assert not verificar_password(CLAVE, None)


def test_un_envio_sin_token_csrf_se_rechaza(app_cliente):
    r = app_cliente.post("/entrar", data={"telefono": "1", "password": "x"})
    assert r.status_code == 403


def test_el_primer_administrador_se_crea_una_sola_vez(sesiones, monkeypatch):
    from app.config import Settings

    ajustes = Settings(admin_telefono="3207778899", admin_password="clave-larga-123", admin_nombre="Admin Uno")
    monkeypatch.setattr(main, "get_settings", lambda: ajustes)
    monkeypatch.setattr(main, "SessionLocal", sesiones)
    main.crear_primer_admin()
    main.crear_primer_admin()  # la segunda vez no duplica
    with sesiones() as db:
        admins = db.scalars(select(Usuario).where(Usuario.rol == Rol.ADMINISTRADOR)).all()
        assert len(admins) == 1 and verificar_password("clave-larga-123", admins[0].password_hash)


def test_la_siembra_de_demostracion_no_borra_nada_y_no_se_repite(sesiones, monkeypatch):
    monkeypatch.setattr(main, "SessionLocal", sesiones)
    with sesiones() as db:  # una cuenta real que ya existía
        db.add(Usuario(nombre="Persona Real", telefono="3001112233", rol=Rol.SOLICITANTE, ficticio=False,
                       password_hash=hash_password(CLAVE)))
        db.commit()
    main.sembrar_demo()
    with sesiones() as db:
        barrios = db.scalar(select(func.count()).select_from(Barrio))
        assert barrios > 100 and db.scalar(select(func.count()).select_from(Municipio)) == 23
        assert db.scalar(select(Usuario.nombre).where(Usuario.ficticio.is_(False))) == "Persona Real"
        solicitudes = db.scalar(select(func.count()).select_from(Solicitud))
    main.sembrar_demo()  # ya hay barrios: no hace nada
    with sesiones() as db:
        assert db.scalar(select(func.count()).select_from(Barrio)) == barrios
        assert db.scalar(select(func.count()).select_from(Solicitud)) == solicitudes


def test_sin_variables_no_se_crea_administrador(sesiones, monkeypatch):
    from app.config import Settings

    monkeypatch.setattr(main, "get_settings", lambda: Settings(admin_telefono="", admin_password=""))
    monkeypatch.setattr(main, "SessionLocal", sesiones)
    main.crear_primer_admin()
    with sesiones() as db:
        assert db.scalar(select(func.count()).select_from(Usuario)) == 0


# ----------------------------------------------------------------------------- registro y entrada
def test_registro_exige_consentimiento(app_cliente, mundo, sesiones):
    r = registrar(app_cliente, mundo, consentimiento="")
    assert r.status_code == 422 and "autorizar el uso de sus datos" in r.text
    with sesiones() as db:
        assert db.scalar(select(func.count()).select_from(Usuario)) == 0


def test_registro_correcto_inicia_sesion(app_cliente, mundo, sesiones):
    r = registrar(app_cliente, mundo)
    assert r.status_code == 303
    assert app_cliente.get("/solicitudes").status_code == 200  # ya hay sesión
    with sesiones() as db:
        u = db.scalar(select(Usuario))
        assert u.rol == Rol.SOLICITANTE and u.consentimiento_datos and u.password_hash != CLAVE


def test_registro_rechaza_telefono_repetido_y_clave_corta(app_cliente, mundo):
    assert registrar(app_cliente, mundo).status_code == 303
    app_cliente.post("/salir", data={"csrf": csrf(app_cliente, "/")})
    r = registrar(app_cliente, mundo)
    assert r.status_code == 422 and "Ya existe una cuenta" in r.text
    r = registrar(app_cliente, mundo, telefono="3009998877", password="corta", password2="corta")
    assert r.status_code == 422 and "al menos 8 caracteres" in r.text


def test_solicitante_exige_barrio_pero_donante_no(app_cliente, mundo, sesiones):
    assert registrar(app_cliente, mundo, barrio_id="").status_code == 422
    r = registrar(app_cliente, mundo, barrio_id="", tipo_cuenta="donante", tipo_donante="empresa")
    assert r.status_code == 303
    with sesiones() as db:
        assert db.scalar(select(Donante.tipo)) == "empresa"


def test_entrar_con_error_no_revela_si_el_telefono_existe(app_cliente, sesiones):
    crear_usuario(sesiones, Rol.SOLICITANTE, "3001234567")
    mala = entrar(app_cliente, "3001234567", "incorrecta")
    inexistente = entrar(app_cliente, "3999999999", "incorrecta")
    assert mala.status_code == inexistente.status_code == 401
    assert "no son correctos" in mala.text and "no son correctos" in inexistente.text
    assert entrar(app_cliente, "3001234567").status_code == 303


def test_las_cuentas_simuladas_no_pueden_entrar(app_cliente, sesiones):
    with sesiones() as db:
        db.add(Usuario(nombre="Sim", telefono="9990000001", rol=Rol.SOLICITANTE, ficticio=True))
        db.commit()
    assert entrar(app_cliente, "9990000001").status_code == 401


# ----------------------------------------------------------------------------- roles
def test_sin_sesion_redirige_a_entrar(app_cliente):
    r = app_cliente.get("/reportes/nuevo", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/entrar"


def test_cada_rol_solo_ve_lo_suyo(app_cliente, sesiones):
    crear_usuario(sesiones, Rol.SOLICITANTE, "3000000001")
    entrar(app_cliente, "3000000001")
    assert app_cliente.get("/admin/usuarios").status_code == 403
    assert app_cliente.get("/donaciones/nueva").status_code == 403
    assert app_cliente.get("/solicitudes/nueva").status_code == 200


def test_el_administrador_crea_cuentas_y_aprueba_organizaciones(app_cliente, sesiones):
    crear_usuario(sesiones, Rol.ADMINISTRADOR, "3000000002")
    entrar(app_cliente, "3000000002")
    r = app_cliente.post("/admin/usuarios", follow_redirects=False, data={
        "nombre": "Organización Ayuda", "telefono": "3112223344", "rol": "equipo_entrega", "es_organizacion": "si",
        "password": CLAVE, "csrf": csrf(app_cliente, "/admin/usuarios")})
    assert r.status_code == 303
    with sesiones() as db:
        org = db.scalar(select(Usuario).where(Usuario.telefono == "3112223344"))
        assert org.aprobado is False
    app_cliente.post("/salir", data={"csrf": csrf(app_cliente, "/")})
    assert entrar(app_cliente, "3112223344").status_code == 403  # aún no aprobada

    entrar(app_cliente, "3000000002")
    app_cliente.post(f"/admin/usuarios/{org.id}/aprobar", data={"csrf": csrf(app_cliente, "/admin/usuarios")})
    app_cliente.post("/salir", data={"csrf": csrf(app_cliente, "/")})
    assert entrar(app_cliente, "3112223344").status_code == 303


# ----------------------------------------------------------------------------- formularios
def test_reporte_de_danos(app_cliente, mundo, sesiones):
    crear_usuario(sesiones, Rol.BRIGADISTA, "3000000003")
    entrar(app_cliente, "3000000003")
    malo = app_cliente.post("/reportes/nuevo", data={"csrf": csrf(app_cliente, "/reportes/nuevo")})
    assert malo.status_code == 422
    r = app_cliente.post("/reportes/nuevo", follow_redirects=False, data={
        "barrio_id": str(mundo["barrio_id"]), "nivel_dano": "2", "personas_afectadas": "40", "acceso": "0.5",
        "csrf": csrf(app_cliente, "/reportes/nuevo")})
    assert r.status_code == 303
    with sesiones() as db:
        rep = db.scalar(select(ReporteDanos))
        assert (rep.nivel_dano, rep.personas_afectadas, rep.acceso, rep.fuente) == (2, 40, 0.5, "app")
        assert rep.hora_captura is not None and rep.hora_evento is not None


def test_solicitud_sencilla(app_cliente, mundo, sesiones):
    crear_usuario(sesiones, Rol.SOLICITANTE, "3000000004")
    entrar(app_cliente, "3000000004")
    r = app_cliente.post("/solicitudes/nueva", follow_redirects=False, data={
        "barrio_id": str(mundo["barrio_id"]), "necesidad": "agua", "personas_hogar": "4", "urgencia": "2",
        "descripcion": "No hay agua potable desde ayer.", "direccion": "Calle 10 # 5-20",
        "csrf": csrf(app_cliente, "/solicitudes/nueva")})
    assert r.status_code == 303
    with sesiones() as db:
        s = db.scalar(select(Solicitud))
        assert (s.estado, s.cantidad, s.urgencia) == ("registrada", 24, 2)  # 4 personas x 6 litros
        assert s.evento_id is not None and db.scalar(select(func.count()).select_from(Vulnerabilidad)) == 0
    assert "Agua para 4 persona" in app_cliente.get("/solicitudes").text


def _datos_vulnerable(mundo, **cambios):
    d = {"barrio_id": str(mundo["barrio_id"]), "necesidad": "medicamentos", "personas_hogar": "2", "urgencia": "3",
         "descripcion": "Necesita su medicina.", "direccion": "Carrera 4 # 3-2", "vulnerable": "si",
         "vuln_tipo": "cronica", "vuln_descripcion": "Persona diabética sin insulina.",
         "vuln_necesidad": "Insulina"}
    d.update(cambios)
    return d


def test_la_vulnerabilidad_exige_consentimiento_expreso(app_cliente, mundo, sesiones):
    crear_usuario(sesiones, Rol.SOLICITANTE, "3000000005")
    entrar(app_cliente, "3000000005")
    sin = app_cliente.post("/solicitudes/nueva", data={
        **_datos_vulnerable(mundo), "csrf": csrf(app_cliente, "/solicitudes/nueva")})
    assert sin.status_code == 422 and "autorización expresa" in sin.text
    with sesiones() as db:
        assert db.scalar(select(func.count()).select_from(Solicitud)) == 0  # no se guarda nada

    con = app_cliente.post("/solicitudes/nueva", follow_redirects=False, data={
        **_datos_vulnerable(mundo), "vuln_consentimiento": "si", "csrf": csrf(app_cliente, "/solicitudes/nueva")})
    assert con.status_code == 303
    with sesiones() as db:
        v = db.scalar(select(Vulnerabilidad))
        assert v.tipo == "cronica" and v.consentimiento and v.necesidad_especifica == "Insulina"


def test_donaciones_en_especie_y_en_dinero(app_cliente, mundo):
    registrar(app_cliente, mundo, telefono="3225556677", tipo_cuenta="donante", barrio_id="")
    r = app_cliente.post("/donaciones/nueva", follow_redirects=False, data={
        "forma": "especie", "tipo_bien": "alimentos", "cantidad": "50", "estado_producto": "nuevo",
        "destino": "tipo", "csrf": csrf(app_cliente, "/donaciones/nueva")})
    assert r.status_code == 303
    r = app_cliente.post("/donaciones/nueva", follow_redirects=False, data={
        "forma": "monetaria", "monto": "150000", "destino": "ninguno", "csrf": csrf(app_cliente, "/donaciones/nueva")})
    assert r.status_code == 303
    malo = app_cliente.post("/donaciones/nueva", data={"forma": "especie", "cantidad": "0",
                                                       "csrf": csrf(app_cliente, "/donaciones/nueva")})
    assert malo.status_code == 422
    pagina = app_cliente.get("/donaciones").text
    assert "50 raciones de alimentos" in pagina and "$150.000" in pagina


def test_hay_un_limite_de_envios_por_hora(app_cliente, mundo, sesiones):
    crear_usuario(sesiones, Rol.BRIGADISTA, "3000000006")
    entrar(app_cliente, "3000000006")
    datos = {"barrio_id": str(mundo["barrio_id"]), "nivel_dano": "1", "personas_afectadas": "1", "acceso": "1"}
    codigos = [app_cliente.post("/reportes/nuevo", follow_redirects=False,
                                data={**datos, "csrf": csrf(app_cliente, "/reportes/nuevo")}).status_code
               for _ in range(21)]
    assert codigos[:20] == [303] * 20 and codigos[20] == 429


# ----------------------------------------------------------------------------- accesibilidad
class _Revisor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids, self.para, self.lang, self.salto, self.sin_nombre = set(), set(), None, False, []

    def handle_starttag(self, tag, a):
        a = dict(a)
        if tag == "html":
            self.lang = a.get("lang")
        if tag == "a" and a.get("class") == "salto":
            self.salto = True
        if tag in ("input", "select", "textarea") and a.get("type") != "hidden" and "id" in a:
            self.ids.add(a["id"])
        if tag == "label" and "for" in a:
            self.para.add(a["for"])


@pytest.mark.parametrize("ruta", ["/registro", "/entrar"])
def test_formularios_publicos_son_accesibles(app_cliente, ruta):
    revisor = _Revisor()
    revisor.feed(app_cliente.get(ruta).text)
    assert revisor.lang == "es" and revisor.salto
    assert revisor.ids and revisor.ids <= revisor.para, f"campos sin etiqueta: {revisor.ids - revisor.para}"


@pytest.mark.parametrize("ruta,rol,telefono", [
    ("/reportes/nuevo", Rol.BRIGADISTA, "3010000001"), ("/solicitudes/nueva", Rol.SOLICITANTE, "3010000002"),
    ("/donaciones/nueva", Rol.DONANTE, "3010000003"), ("/admin/usuarios", Rol.ADMINISTRADOR, "3010000004"),
])
def test_formularios_internos_son_accesibles(app_cliente, sesiones, ruta, rol, telefono):
    crear_usuario(sesiones, rol, telefono)
    entrar(app_cliente, telefono)
    revisor = _Revisor()
    revisor.feed(app_cliente.get(ruta).text)
    assert revisor.ids <= revisor.para, f"campos sin etiqueta: {revisor.ids - revisor.para}"


def test_renovar_la_demostracion_conserva_al_administrador(sesiones, monkeypatch, capsys):
    monkeypatch.setattr(main, "SessionLocal", sesiones)
    with sesiones() as db:
        cargar_viviendas(db)
        db.add(Usuario(nombre="Admin Real", telefono="3001112233", rol=Rol.ADMINISTRADOR, ficticio=False,
                       password_hash=hash_password(CLAVE)))
        db.commit()
    main.reiniciar_demo()
    assert "DEMO renovada" in capsys.readouterr().out
    with sesiones() as db:
        assert db.scalar(select(func.count()).select_from(Barrio)) > 100
        assert db.scalar(select(Usuario.nombre).where(Usuario.ficticio.is_(False))) == "Admin Real"
    main.reiniciar_demo()  # se puede repetir: vuelve a generar lo mismo (semilla fija)
    with sesiones() as db:
        assert db.scalar(select(func.count()).select_from(Barrio)) > 100


def test_renovar_la_demostracion_conserva_cuentas_sin_datos_y_se_niega_si_ya_hicieron_algo(sesiones, monkeypatch, capsys):
    monkeypatch.setattr(main, "SessionLocal", sesiones)
    with sesiones() as db:
        cargar_viviendas(db)
        db.add(Municipio(codigo="99999", nombre="Prueba")) if db.get(Municipio, "99999") is None else None
        db.flush()
        barrio = Barrio(municipio_codigo="08001", nombre="Barrio real de prueba")
        db.add(barrio)
        db.flush()
        persona = Usuario(nombre="Persona Real", telefono="3009998877", rol=Rol.SOLICITANTE, ficticio=False,
                          barrio_id=barrio.id)
        db.add(persona)
        db.commit()
        persona_id = persona.id
    main.reiniciar_demo()  # la cuenta existe pero no ha hecho nada: se conserva y la simulación se renueva
    assert "DEMO renovada" in capsys.readouterr().out
    with sesiones() as db:
        assert db.get(Usuario, persona_id) is not None and db.scalar(select(func.count()).select_from(Barrio)) > 100
        db.add(Solicitud(solicitante_id=persona_id, creador_id=persona_id,
                         barrio_id=db.scalar(select(Barrio.id).limit(1)), necesidad="agua", cantidad=6))
        db.commit()
        antes = db.scalar(select(func.count()).select_from(Barrio))
    main.reiniciar_demo()  # ahora sí hizo algo: se niega, sin tumbar la aplicación
    salida = capsys.readouterr().out
    assert "DEMO no renovada" in salida and "solicitudes" in salida
    with sesiones() as db:
        assert db.scalar(select(func.count()).select_from(Barrio)) == antes
