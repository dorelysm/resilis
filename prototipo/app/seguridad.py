"""Contraseñas y protección CSRF. Solo usa la biblioteca estándar."""
import hashlib
import hmac
import os
import secrets

_N, _R, _P = 2**14, 8, 1


def hash_password(password: str) -> str:
    """Resumen con sal (scrypt). Formato: scrypt$N$r$p$sal$resumen."""
    sal = os.urandom(16)
    h = hashlib.scrypt(password.encode(), salt=sal, n=_N, r=_R, p=_P, dklen=32)
    return f"scrypt${_N}${_R}${_P}${sal.hex()}${h.hex()}"


def verificar_password(password: str, almacenado: str | None) -> bool:
    if not almacenado:
        return False
    try:
        _, n, r, p, sal, esperado = almacenado.split("$")
        h = hashlib.scrypt(password.encode(), salt=bytes.fromhex(sal), n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(h.hex(), esperado)


def token_csrf(sesion: dict) -> str:
    """Un token por sesión, que los formularios envían de vuelta."""
    if "csrf" not in sesion:
        sesion["csrf"] = secrets.token_urlsafe(24)
    return sesion["csrf"]


def csrf_valido(sesion: dict, enviado: str | None) -> bool:
    return bool(enviado) and hmac.compare_digest(sesion.get("csrf", ""), enviado)
