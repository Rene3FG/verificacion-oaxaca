from pydantic import BaseModel, Field


class ParametroRead(BaseModel):
    clave: str
    valor: str
    descripcion: str
    origen: str  # "catalogo" (fila real en cat_parametros_sistema) | "default" (solo DEFAULTS, sin fila todavía)


class ParametroUpdate(BaseModel):
    valor: str = Field(min_length=1, max_length=200)
