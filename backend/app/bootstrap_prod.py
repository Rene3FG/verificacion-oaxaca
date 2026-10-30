"""Datos de arranque de un verificentro nuevo (D5): parámetros, límites de
NOM-041/045, estaciones por línea y el primer supervisor. A diferencia de
`app.seed` no crea usuarios ni expedientes de demostración.

Uso (la contraseña va en la variable, nunca en argumentos):
    BOOTSTRAP_PASSWORD=... python -m app.bootstrap_prod \
        --centro reforma --lineas 2 --usuario admin --nombre "Administrador"

Idempotente: lo que ya existe se conserva (no cambia contraseñas).
En producción: docker compose -f docker-compose.prod.yml --env-file .env.prod \
    exec -e BOOTSTRAP_PASSWORD=... backend python -m app.bootstrap_prod ...
"""

import argparse
import asyncio
import os
import sys

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.catalogos import CatParametroSistema
from app.models.enums import StationType
from app.models.usuario import CatUsuario
from app.models.workstation import UserStationPermission, Workstation
from app.seed_limites_nom041 import cargar_limites_nom041
from app.seed_limites_nom045 import cargar_limites_nom045
from app.services.auth import hash_password, validar_politica_password
from app.services.parametros import DEFAULTS


def _estaciones(centro: str, lineas: int) -> list[dict]:
    sufijo = centro.upper()
    estaciones = []
    for n in range(1, lineas + 1):
        for tipo, prefijo in ((StationType.CAPTURA, "CAPTURA"), (StationType.PRUEBA, "PRUEBA")):
            nombre = f"{prefijo}-{sufijo}-L{n}"
            estaciones.append(
                dict(name=nombre, station_type=tipo, center_id=centro, line_id=n,
                     is_centralized=False, allowed_line_ids=[n], device_identifier=nombre)
            )
    nombre = f"IMPRESION-{sufijo}-01"
    estaciones.append(
        dict(name=nombre, station_type=StationType.IMPRESION, center_id=centro,
             line_id=None, is_centralized=True,
             allowed_line_ids=list(range(1, lineas + 1)), device_identifier=nombre)
    )
    return estaciones


async def bootstrap(centro: str, lineas: int, usuario: str, nombre: str, password: str) -> None:
    async with SessionLocal() as db:
        for data in _estaciones(centro, lineas):
            if (await db.execute(select(Workstation).where(Workstation.name == data["name"]))).scalar_one_or_none() is None:
                db.add(Workstation(**data))
        for clave, valor in DEFAULTS.items():
            if (await db.execute(select(CatParametroSistema).where(CatParametroSistema.clave == clave))).scalar_one_or_none() is None:
                db.add(CatParametroSistema(clave=clave, valor=valor))

        user = (await db.execute(select(CatUsuario).where(CatUsuario.username == usuario))).scalar_one_or_none()
        if user is None:
            user = CatUsuario(username=usuario, password_hash=hash_password(password),
                              nombre_completo=nombre, is_active=True)
            db.add(user)
            await db.flush()
        # Supervisor del centro: line_id=None = todas las líneas. Un permiso por
        # tipo de estación para que pueda iniciar sesión en cualquiera.
        for tipo in StationType:
            if (await db.execute(select(UserStationPermission).where(
                UserStationPermission.user_id == user.id,
                UserStationPermission.station_type == tipo,
                UserStationPermission.center_id == centro,
            ))).scalar_one_or_none() is None:
                db.add(UserStationPermission(user_id=user.id, station_type=tipo, center_id=centro,
                                             line_id=None, can_operate=True, can_supervise=True))
        await db.commit()

    await cargar_limites_nom041()
    await cargar_limites_nom045()
    print(f"Arranque aplicado: centro={centro}, {lineas} línea(s), supervisor={usuario}.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--centro", required=True)
    p.add_argument("--lineas", type=int, required=True)
    p.add_argument("--usuario", required=True)
    p.add_argument("--nombre", default="Administrador")
    a = p.parse_args()
    password = os.environ.get("BOOTSTRAP_PASSWORD", "")
    try:
        if len(password) < 8:
            raise ValueError("Defina BOOTSTRAP_PASSWORD (mínimo 8 caracteres).")
        validar_politica_password(password)
    except ValueError as exc:
        sys.exit(str(exc))
    if a.lineas < 1:
        sys.exit("--lineas debe ser al menos 1.")
    asyncio.run(bootstrap(a.centro, a.lineas, a.usuario, a.nombre, password))


if __name__ == "__main__":
    main()
