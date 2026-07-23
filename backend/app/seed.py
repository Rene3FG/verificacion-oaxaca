"""Datos semilla de desarrollo: estaciones y parámetros de ejemplo del
centro Reforma, tal como se describen en el documento de diseño del
proyecto (sección 'Ejemplo conceptual' / 'Entidades técnicas sugeridas').

Uso: python -m app.seed
"""

import asyncio

from sqlalchemy import select

import uuid

from app.db.session import SessionLocal
from app.models.catalogos import CatParametroSistema
from app.models.enums import StationType
from app.models.workstation import UserStationPermission, Workstation
from app.services.parametros import DEFAULTS

# Usuario de prueba para desarrollo/demo (aún no existe cat_usuarios real).
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")

WORKSTATIONS = [
    dict(
        name="CAPTURA-REFORMA-L1",
        station_type=StationType.CAPTURA,
        center_id="reforma",
        line_id=1,
        is_centralized=False,
        allowed_line_ids=[1],
        device_identifier="CAPTURA-REFORMA-L1",
    ),
    dict(
        name="PRUEBA-REFORMA-L1",
        station_type=StationType.PRUEBA,
        center_id="reforma",
        line_id=1,
        is_centralized=False,
        allowed_line_ids=[1],
        device_identifier="PRUEBA-REFORMA-L1",
    ),
    dict(
        name="CAPTURA-REFORMA-L2",
        station_type=StationType.CAPTURA,
        center_id="reforma",
        line_id=2,
        is_centralized=False,
        allowed_line_ids=[2],
        device_identifier="CAPTURA-REFORMA-L2",
    ),
    dict(
        name="PRUEBA-REFORMA-L2",
        station_type=StationType.PRUEBA,
        center_id="reforma",
        line_id=2,
        is_centralized=False,
        allowed_line_ids=[2],
        device_identifier="PRUEBA-REFORMA-L2",
    ),
    dict(
        name="IMPRESION-REFORMA-01",
        station_type=StationType.IMPRESION,
        center_id="reforma",
        line_id=None,
        is_centralized=True,
        allowed_line_ids=[1, 2],
        device_identifier="IMPRESION-REFORMA-01",
    ),
]


async def seed() -> None:
    async with SessionLocal() as db:
        for data in WORKSTATIONS:
            existing = await db.execute(
                select(Workstation).where(Workstation.name == data["name"])
            )
            if existing.scalar_one_or_none() is None:
                db.add(Workstation(**data))

        for clave, valor in DEFAULTS.items():
            existing = await db.execute(
                select(CatParametroSistema).where(CatParametroSistema.clave == clave)
            )
            if existing.scalar_one_or_none() is None:
                db.add(CatParametroSistema(clave=clave, valor=valor))

        existing_permiso = await db.execute(
            select(UserStationPermission).where(
                UserStationPermission.user_id == TEST_USER_ID,
                UserStationPermission.station_type == StationType.CAPTURA,
                UserStationPermission.center_id == "reforma",
            )
        )
        if existing_permiso.scalar_one_or_none() is None:
            db.add(
                UserStationPermission(
                    user_id=TEST_USER_ID,
                    station_type=StationType.CAPTURA,
                    center_id="reforma",
                    line_id=1,
                    can_operate=True,
                )
            )

        await db.commit()
    print("Seed aplicado.")


if __name__ == "__main__":
    asyncio.run(seed())
