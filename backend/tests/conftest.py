import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.api.deps import get_db
from app.core.config import settings
from app.main import app
from app.models.enums import EstadoVerificacion, FuenteDatos, StationType
from app.models.usuario import CatUsuario
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.models.workstation import StationSession, UserStationPermission, Workstation
from app.services.auth import hash_password


@pytest_asyncio.fixture
async def db_session():
    """Sesión atada a una transacción externa que se revierte al final del
    test (patrón SAVEPOINT), para que las pruebas corran contra Postgres
    real (los modelos usan ARRAY/UUID/JSONB, no simulables en SQLite) sin
    dejar datos entre pruebas."""

    engine = create_async_engine(settings.database_url)
    connection = await engine.connect()
    outer_trans = await connection.begin()

    session = AsyncSession(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )

    try:
        yield session
    finally:
        await session.close()
        await outer_trans.rollback()
        await connection.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def client(db_session):
    async def _get_db_override():
        yield db_session

    app.dependency_overrides[get_db] = _get_db_override
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


async def crear_estacion(
    db_session: AsyncSession,
    *,
    station_type: StationType,
    center_id: str = "OAX-01",
    line_id: int | None = 1,
    is_centralized: bool = False,
    allowed_line_ids: list[int] | None = None,
    capacidad_dinamometro_kg: float | None = None,
) -> Workstation:
    estacion = Workstation(
        name=f"{station_type.value}-{uuid.uuid4().hex[:8]}",
        station_type=station_type,
        center_id=center_id,
        line_id=line_id,
        is_centralized=is_centralized,
        allowed_line_ids=allowed_line_ids,
        is_active=True,
        capacidad_dinamometro_kg=capacidad_dinamometro_kg,
    )
    db_session.add(estacion)
    await db_session.flush()
    return estacion


async def crear_usuario(
    db_session: AsyncSession,
    *,
    username: str | None = None,
    password: str = "clave-de-prueba",
    is_active: bool = True,
) -> CatUsuario:
    usuario = CatUsuario(
        username=username or f"usuario-{uuid.uuid4().hex[:8]}",
        password_hash=hash_password(password),
        nombre_completo="Usuario de prueba",
        is_active=is_active,
    )
    db_session.add(usuario)
    await db_session.flush()
    return usuario


async def crear_permiso(
    db_session: AsyncSession,
    *,
    user_id: uuid.UUID,
    station_type: StationType,
    center_id: str,
    line_id: int | None,
    can_supervise: bool = False,
) -> UserStationPermission:
    permiso = UserStationPermission(
        user_id=user_id,
        station_type=station_type,
        center_id=center_id,
        line_id=line_id,
        can_operate=True,
        can_supervise=can_supervise,
    )
    db_session.add(permiso)
    await db_session.flush()
    return permiso


async def crear_sesion_activa(
    db_session: AsyncSession, *, estacion: Workstation, user_id: uuid.UUID | None = None
) -> StationSession:
    sesion = StationSession(
        user_id=user_id or uuid.uuid4(),
        workstation_id=estacion.id,
        station_type=estacion.station_type,
        center_id=estacion.center_id,
        line_id=estacion.line_id,
        status="activa",
    )
    db_session.add(sesion)
    await db_session.flush()
    return sesion


async def crear_sesion_supervisor(
    db_session: AsyncSession,
    *,
    center_id: str = "OAX-01",
    station_type: StationType = StationType.CAPTURA,
    line_id: int | None = 1,
) -> StationSession:
    """Sesión de un usuario con can_supervise=True (ver requiere_supervisor
    en deps.py) — la estación física de login es incidental, lo que
    importa es el permiso de supervisor del usuario."""

    usuario = await crear_usuario(db_session)
    await crear_permiso(
        db_session,
        user_id=usuario.id,
        station_type=station_type,
        center_id=center_id,
        line_id=None,
        can_supervise=True,
    )
    estacion = await crear_estacion(
        db_session, station_type=station_type, center_id=center_id, line_id=line_id
    )
    return await crear_sesion_activa(db_session, estacion=estacion, user_id=usuario.id)


async def crear_expediente(
    db_session: AsyncSession,
    *,
    linea_id: int,
    centro_id: str = "OAX-01",
    estado: EstadoVerificacion = EstadoVerificacion.CREADO,
    placa: str | None = None,
    tipo_vehiculo: str | None = None,
    combustible: str | None = None,
    modelo: int | None = None,
    peso_bruto_vehicular_kg: float | None = None,
    combustible_validado: str | None = None,
    datos_certificado_completos: bool = True,
) -> Verificacion:
    """`datos_certificado_completos=True` (default) llena de una vez los
    campos de propietario/domicilio/PBV/Tracción que el certificado exige
    (sección 7 del handoff) con valores de prueba, para que las pruebas que
    no son sobre ese requisito no tengan que preocuparse por él al llegar a
    /imprimir. Pasar `False` para dejarlos en None (usado por las pruebas
    que sí ejercitan el bloqueo por datos faltantes)."""

    datos_certificado = (
        dict(
            tarjeta_circulacion="TC-0000001",
            propietario_estado="Oaxaca",
            propietario_municipio="Oaxaca de Juárez",
            propietario_codigo_postal="68000",
            propietario_colonia="Centro",
            propietario_calle="Calle Falsa",
            propietario_numero_exterior="123",
            pbv="2500",
            traccion="4x2",
        )
        if datos_certificado_completos
        else {}
    )
    vehiculo = Vehiculo(
        placa=placa or f"TST{uuid.uuid4().hex[:4].upper()}",
        fuente_datos=FuenteDatos.MANUAL,
        tipo_vehiculo=tipo_vehiculo,
        combustible=combustible,
        modelo=modelo,
        peso_bruto_vehicular_kg=peso_bruto_vehicular_kg,
        **datos_certificado,
    )
    db_session.add(vehiculo)
    await db_session.flush()

    verificacion = Verificacion(
        vehiculo_id=vehiculo.id,
        placa=vehiculo.placa,
        centro_id=centro_id,
        linea_id=linea_id,
        estado=estado,
        combustible_validado=combustible_validado,
    )
    db_session.add(verificacion)
    await db_session.flush()
    return verificacion
