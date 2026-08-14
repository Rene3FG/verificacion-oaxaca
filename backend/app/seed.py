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
from app.models.usuario import CatUsuario
from app.models.workstation import UserStationPermission, Workstation
from app.services.auth import hash_password
from app.services.parametros import DEFAULTS

# Usuario de prueba para desarrollo/demo. HU-119: ahora respaldado por una
# fila real en cat_usuarios (antes cualquier UUID servía como user_id).
TEST_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
TEST_USERNAME = "operador1"
TEST_PASSWORD = "operador1"  # noqa: S105 - solo desarrollo/demo

# Supervisor de prueba: line_id=None en el permiso = todas las líneas del
# centro (HU-001).
TEST_SUPERVISOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
TEST_SUPERVISOR_USERNAME = "supervisor1"
TEST_SUPERVISOR_PASSWORD = "supervisor1"  # noqa: S105 - solo desarrollo/demo

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

        if await db.get(CatUsuario, TEST_USER_ID) is None:
            db.add(
                CatUsuario(
                    id=TEST_USER_ID,
                    username=TEST_USERNAME,
                    password_hash=hash_password(TEST_PASSWORD),
                    nombre_completo="Operador de prueba",
                    is_active=True,
                )
            )
        if await db.get(CatUsuario, TEST_SUPERVISOR_ID) is None:
            db.add(
                CatUsuario(
                    id=TEST_SUPERVISOR_ID,
                    username=TEST_SUPERVISOR_USERNAME,
                    password_hash=hash_password(TEST_SUPERVISOR_PASSWORD),
                    nombre_completo="Supervisor de prueba",
                    is_active=True,
                )
            )

        permisos_operador = [
            dict(station_type=StationType.CAPTURA, line_id=1),
            dict(station_type=StationType.PRUEBA, line_id=1),
            dict(station_type=StationType.IMPRESION, line_id=None),
        ]
        for permiso in permisos_operador:
            existing_permiso = await db.execute(
                select(UserStationPermission).where(
                    UserStationPermission.user_id == TEST_USER_ID,
                    UserStationPermission.station_type == permiso["station_type"],
                    UserStationPermission.center_id == "reforma",
                )
            )
            if existing_permiso.scalar_one_or_none() is None:
                db.add(
                    UserStationPermission(
                        user_id=TEST_USER_ID,
                        center_id="reforma",
                        can_operate=True,
                        **permiso,
                    )
                )

        existing_permiso_supervisor = await db.execute(
            select(UserStationPermission).where(
                UserStationPermission.user_id == TEST_SUPERVISOR_ID,
                UserStationPermission.center_id == "reforma",
            )
        )
        if existing_permiso_supervisor.scalar_one_or_none() is None:
            db.add(
                UserStationPermission(
                    user_id=TEST_SUPERVISOR_ID,
                    station_type=StationType.CAPTURA,
                    center_id="reforma",
                    line_id=None,
                    can_operate=True,
                    can_supervise=True,
                )
            )

        await db.commit()
    print("Seed aplicado.")


if __name__ == "__main__":
    asyncio.run(seed())
