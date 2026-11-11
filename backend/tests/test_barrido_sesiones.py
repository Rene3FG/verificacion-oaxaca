import datetime

from app.models.enums import StationType
from app.services.sesiones_barrido import barrer_sesiones_vencidas
from tests.conftest import crear_estacion, crear_sesion_activa


async def test_barrido_expira_solo_las_vencidas(db_session):
    estacion = await crear_estacion(db_session, station_type=StationType.CAPTURA, line_id=1)
    reciente = await crear_sesion_activa(db_session, estacion=estacion)
    inactiva = await crear_sesion_activa(db_session, estacion=estacion)
    antigua = await crear_sesion_activa(db_session, estacion=estacion)
    ahora = datetime.datetime.now(datetime.timezone.utc)
    reciente.updated_at = ahora
    reciente.login_at = ahora
    inactiva.updated_at = ahora - datetime.timedelta(hours=2)
    inactiva.login_at = ahora - datetime.timedelta(hours=3)
    antigua.updated_at = ahora
    antigua.login_at = ahora - datetime.timedelta(hours=48)
    await db_session.commit()

    n = await barrer_sesiones_vencidas(db_session)
    for s in (reciente, inactiva, antigua):
        await db_session.refresh(s)

    assert n == 2
    assert reciente.status == "activa" and reciente.logout_at is None
    assert inactiva.status == "expirada" and inactiva.logout_at is not None
    assert antigua.status == "expirada"
