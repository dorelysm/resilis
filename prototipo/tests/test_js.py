"""El navegador del equipo de entrega calcula la huella del código igual que el servidor (validación sin conexión)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from app.servicios import huella_codigo

JS = Path(__file__).resolve().parent.parent / "app" / "static" / "entregas.js"
pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="Node no está instalado")

CASOS = [
    ("a1b2c3d4e5f60718", "K7M29PQX"),
    ("a1b2c3d4e5f60718", "k7m2-9pqx"),   # minúsculas y guion
    ("ffffffffffffffff", " ABCD 2345 "),  # espacios
    ("0000000000000000", "ZZZZZZZZ"),
]


def _huellas_js(casos):
    guion = (
        "const m=require(process.argv[1]);const casos=JSON.parse(process.argv[2]);"
        "Promise.all(casos.map(([s,c])=>m.huella(s,c))).then(r=>console.log(JSON.stringify(r)));"
    )
    salida = subprocess.run(["node", "-e", guion, str(JS), json.dumps(casos)], capture_output=True, text=True,
                            check=True, timeout=30).stdout
    return json.loads(salida)


def test_la_huella_del_navegador_coincide_con_la_del_servidor():
    assert _huellas_js(CASOS) == [huella_codigo(sal, codigo) for sal, codigo in CASOS]


def test_la_normalizacion_ignora_guiones_espacios_y_mayusculas():
    iguales = _huellas_js([("00", "K7M29PQX"), ("00", "k7m2-9pqx"), ("00", "K7M2 9PQX")])
    assert len(set(iguales)) == 1
    assert _huellas_js([("00", "K7M29PQX"), ("01", "K7M29PQX")])[0] != _huellas_js([("00", "K7M29PQX"), ("01", "K7M29PQX")])[1]
