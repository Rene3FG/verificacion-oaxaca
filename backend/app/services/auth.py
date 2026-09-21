"""HU-119: hashing de contraseñas con bcrypt. Nada de contraseñas en texto
plano ni en logs — ni siquiera en detalle_json/motivo de AccessEvent."""

import bcrypt

MAX_PASSWORD_BYTES = 72  # límite de bcrypt


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        # bcrypt>=5 lanza ValueError con >72 bytes: una contraseña así nunca
        # pudo haberse guardado, es simplemente incorrecta (401, no 500).
        return False
