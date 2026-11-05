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


# X6-a (auditoría 2026-11-04): la lista exacta dejaba pasar `Password123`,
# `Oaxaca2026`, `Admin2026`... El patrón real es "palabra conocida + números
# o símbolos". Se quita lo que no es letra y, si lo que queda es una de estas
# palabras (o tiene menos de 3 letras), se rechaza. Además, ninguna puede
# CONTENER el nombre del sistema o del estado.
_BASES_COMUNES = {
    "password", "passw", "pass", "contrasena", "contraseña", "clave", "secreto",
    "admin", "administrador", "root", "usuario", "user", "login", "acceso",
    "qwerty", "qwertz", "asdf", "asdfgh", "zxcv", "abc", "abcd", "abcde", "abcdef",
    "welcome", "bienvenido", "hola", "test", "prueba", "demo", "temporal", "cambiar",
    "operador", "supervisor", "tecnico", "capturista", "impresion", "captura",
    "verificentro", "verificacion", "oaxaca", "mexico", "mexicano",
    "iloveyou", "teamo", "amor", "monkey", "dragon", "letmein", "football", "futbol",
    "enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto",
    "septiembre", "octubre", "noviembre", "diciembre",
}
_PROHIBIDAS_DENTRO = ("oaxaca", "verificacion", "verificación", "verificentro", "password", "contrase")

# Leetspeak básico: P4ssw0rd → password.
_LEET = str.maketrans({"4": "a", "@": "a", "3": "e", "1": "i", "!": "i", "0": "o", "5": "s", "$": "s", "7": "t"})


def _base_alfabetica(password: str) -> str:
    """Letras de la contraseña en minúsculas, deshaciendo leetspeak solo en
    medio de la palabra (los dígitos del final son el típico '2026')."""
    p = password.lower().rstrip("0123456789!@#$%&*._-+")
    p = p.lstrip("0123456789!@#$%&*._-+")
    p = p.translate(_LEET)
    return "".join(c for c in p if c.isalpha())


def validar_politica_password(password: str, *, username: str | None = None) -> None:
    """Lanza ValueError con el motivo si la contraseña no cumple la política."""

    if not (any(c.isalpha() for c in password) and any(c.isdigit() for c in password)):
        raise ValueError("La contraseña debe incluir al menos una letra y un número.")
    bajo = password.lower()
    if bajo in _COMUNES or len(set(password)) < 4:
        raise ValueError("La contraseña es demasiado común o predecible.")
    base = _base_alfabetica(password)
    if len(base) < 3 or base in _BASES_COMUNES:
        raise ValueError(
            "La contraseña es demasiado común o predecible: una palabra conocida con "
            "números al final no es suficiente."
        )
    if any(p in bajo for p in _PROHIBIDAS_DENTRO):
        raise ValueError("La contraseña no puede contener el nombre del sistema ni del estado.")
    if username and len(username) >= 4 and username.lower() in bajo:
        raise ValueError("La contraseña no puede contener el nombre de usuario.")
