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


# X6: política mínima. Largo >= 8 lo exigen los schemas; aquí, composición y
# contraseñas triviales (lista corta de las más usadas, en minúsculas).
_COMUNES = {
    "12345678", "123456789", "1234567890", "password", "password1", "qwerty123",
    "contraseña1", "contrasena1", "abc12345", "admin123", "operador1",
    "supervisor1", "verificacion1", "oaxaca123", "11111111", "iloveyou1",
}


def validar_politica_password(password: str) -> None:
    """Lanza ValueError con el motivo si la contraseña no cumple la política."""

    if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
        raise ValueError("La contraseña debe incluir al menos una letra y un número.")
    if password.lower() in _COMUNES or len(set(password)) < 4:
        raise ValueError("La contraseña es demasiado común o predecible.")
