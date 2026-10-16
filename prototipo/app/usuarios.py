"""Crea una cuenta desde la línea de comandos (para el primer administrador y para pruebas).

Uso:  uv run python -m app.usuarios --rol administrador --nombre "Nombre Apellido" --telefono 3001234567
La contraseña se pide por teclado y no se muestra.
"""
import argparse
import getpass

from sqlalchemy import select

from app.db import SessionLocal, crear_tablas
from app.models import Rol, Usuario, ahora
from app.seguridad import hash_password
from app.web import solo_digitos


def main() -> None:
    ap = argparse.ArgumentParser(description="Crea una cuenta.")
    ap.add_argument("--rol", required=True, choices=[r.value for r in Rol])
    ap.add_argument("--nombre", required=True)
    ap.add_argument("--telefono", required=True)
    args = ap.parse_args()
    tel = solo_digitos(args.telefono)
    password = getpass.getpass("Contraseña (mínimo 8 caracteres): ")
    if len(password) < 8 or password != getpass.getpass("Repita la contraseña: "):
        raise SystemExit("La contraseña es muy corta o no coincide.")
    crear_tablas()
    with SessionLocal() as db:
        if db.scalar(select(Usuario.id).where(Usuario.telefono == tel, Usuario.password_hash.is_not(None))):
            raise SystemExit("Ya existe una cuenta con ese teléfono.")
        db.add(Usuario(nombre=args.nombre, telefono=tel, rol=args.rol, password_hash=hash_password(password),
                       consentimiento_datos=True, consentimiento_fecha=ahora(), ficticio=False))
        db.commit()
    print("Cuenta creada.")


if __name__ == "__main__":
    main()
