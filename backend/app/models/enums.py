import enum


class EstadoVerificacion(str, enum.Enum):
    CREADO = "CREADO"
    DATOS_SIOX_CONSULTADOS = "DATOS_SIOX_CONSULTADOS"
    DATOS_SIOX_IMPORTADOS = "DATOS_SIOX_IMPORTADOS"
    DATOS_CAPTURADOS_MANUALMENTE = "DATOS_CAPTURADOS_MANUALMENTE"
    DATOS_NORMALIZADOS = "DATOS_NORMALIZADOS"
    INSPECCION_VISUAL_PENDIENTE = "INSPECCION_VISUAL_PENDIENTE"
    INSPECCION_VISUAL_APROBADA = "INSPECCION_VISUAL_APROBADA"
    INSPECCION_VISUAL_RECHAZADA = "INSPECCION_VISUAL_RECHAZADA"
    OBD_NO_APLICA = "OBD_NO_APLICA"
    OBD_PENDIENTE = "OBD_PENDIENTE"
    OBD_SOLICITADO = "OBD_SOLICITADO"
    OBD_RECIBIDO = "OBD_RECIBIDO"
    LISTO_PARA_PRUEBA = "LISTO_PARA_PRUEBA"
    PRUEBA_CONFIGURADA = "PRUEBA_CONFIGURADA"
    PRUEBA_EN_PROCESO = "PRUEBA_EN_PROCESO"
    PRUEBA_FINALIZADA = "PRUEBA_FINALIZADA"
    PENDIENTE_IMPRESION = "PENDIENTE_IMPRESION"
    FOLIO_SOLICITADO = "FOLIO_SOLICITADO"
    FOLIO_ASIGNADO = "FOLIO_ASIGNADO"
    IMPRESO = "IMPRESO"
    CERRADO = "CERRADO"
    ERROR_INTEGRACION = "ERROR_INTEGRACION"
    IMPRESION_FALLIDA = "IMPRESION_FALLIDA"
    FOLIO_ERROR = "FOLIO_ERROR"
    CANCELADO = "CANCELADO"


class FuenteDatos(str, enum.Enum):
    SIOX = "SIOX"
    MANUAL = "MANUAL"
    CORREGIDO_OPERADOR = "CORREGIDO_OPERADOR"


class ResultadoInspeccionVisual(str, enum.Enum):
    APROBADA = "APROBADA"
    RECHAZADA = "RECHAZADA"


class TipoPrueba(str, enum.Enum):
    DINAMICA = "DINAMICA"
    ESTATICA = "ESTATICA"
    OPACIDAD = "OPACIDAD"
    ALTERNA = "ALTERNA"


class ResultadoPruebaEnum(str, enum.Enum):
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    ERROR = "ERROR"


class ResultadoFinal(str, enum.Enum):
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    PENDIENTE = "PENDIENTE"
    ERROR = "ERROR"


class EstadoPrintJob(str, enum.Enum):
    PENDIENTE = "PENDIENTE"
    PROCESANDO = "PROCESANDO"
    FOLIO_SOLICITADO = "FOLIO_SOLICITADO"
    FOLIO_ASIGNADO = "FOLIO_ASIGNADO"
    IMPRESO = "IMPRESO"
    ERROR = "ERROR"
    REINTENTO = "REINTENTO"


class TipoCertificado(str, enum.Enum):
    """Revisión Figma 2026-08-24: los 4 tipos reales de folio/certificado —
    reemplaza los nombres inventados (APROBACION/RECHAZO_VISUAL/
    RECHAZO_PRUEBA) que usaba `app.services.certificado` antes de leer el
    Developer Handoff a fondo."""

    PARTICULAR = "PARTICULAR"
    DOBLE_CERO = "DOBLE_CERO"
    INTENSIVO = "INTENSIVO"
    RECHAZO = "RECHAZO"


class EstadoFolio(str, enum.Enum):
    """Estado de un folio dentro del inventario LOCAL (ver app.models.folio).
    Reemplaza el modelo anterior de 'solicitud a sistema externo' —
    confirmado en el handoff: este sistema es la fuente de verdad del
    inventario, no hay sincronización con otro sistema."""

    DISPONIBLE = "DISPONIBLE"
    ASIGNADO = "ASIGNADO"
    IMPRESO = "IMPRESO"
    DANADO = "DANADO"
    INVALIDADO = "INVALIDADO"


class StationType(str, enum.Enum):
    CAPTURA = "captura"
    PRUEBA = "prueba"
    IMPRESION = "impresion"


class SyncStatus(str, enum.Enum):
    PENDING = "pending"
    SYNCING = "syncing"
    SYNCED = "synced"
    ERROR = "error"


class AccessEventResultado(str, enum.Enum):
    PERMITIDO = "PERMITIDO"
    DENEGADO = "DENEGADO"
