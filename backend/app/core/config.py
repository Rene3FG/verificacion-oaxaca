from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://verificacion:verificacion@localhost:5432/verificacion"
    database_url_sync: str = "postgresql+psycopg2://verificacion:verificacion@localhost:5432/verificacion"
    redis_url: str = "redis://localhost:6379/0"

    siox_base_url: str = "https://siox.finanzasoaxaca.gob.mx/pagoTenencia"

    obd_modelo_minimo: int = 2006


settings = Settings()
