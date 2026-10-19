from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://verificacion:verificacion@localhost:5432/verificacion"
    database_url_sync: str = "postgresql+psycopg2://verificacion:verificacion@localhost:5432/verificacion"
    redis_url: str = "redis://localhost:6379/0"

    siox_base_url: str = "https://siox.finanzasoaxaca.gob.mx/pagoTenencia"

    # Supuesto (2026-09-29): el central expone un endpoint HTTP idempotente por
    # `id`. Vacío = sin central configurado (enviar_uno_a_central lanza).
    central_sync_url: str = ""
    central_sync_token: str = ""
    central_sync_timeout_s: float = 10.0
    # HU-107: cada cuántos segundos el servidor local intenta enviar pendientes
    # solo. 0 o sin central_sync_url = apagado (queda el POST /api/sync/procesar).
    sync_auto_intervalo_s: float = 30.0

    obd_modelo_minimo: int = 2006

    # Equipment Integration Contract v1 (ver app/services/equipo_gateway.py):
    # "manual" = sin gateway, el operador captura las lecturas; "simulador" =
    # gateway en memoria para QA/demo. Nunca "simulador" en producción.
    equipo_gateway_modo: str = "manual"
    equipo_simulador_escenario: str = "APROBADO"


settings = Settings()
