from app.models.catalogos import (
    CatalogoSimple,
    CatEstadoVerificacion,
    CatParametroSistema,
)
from app.models.event_log import EventLog
from app.models.folio_assignment import FolioAssignment
from app.models.folio_request import FolioRequest
from app.models.inspeccion_visual import InspeccionVisual
from app.models.integration_log import IntegrationLog
from app.models.print_job import PrintJob
from app.models.resultado_obd_sbd import ResultadoObdSbd
from app.models.resultado_prueba import ResultadoPrueba
from app.models.siox_consulta import SioxConsulta
from app.models.sync_outbox import SyncOutbox
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.models.workstation import StationSession, UserStationPermission, Workstation

__all__ = [
    "CatalogoSimple",
    "CatEstadoVerificacion",
    "CatParametroSistema",
    "EventLog",
    "FolioAssignment",
    "FolioRequest",
    "InspeccionVisual",
    "IntegrationLog",
    "PrintJob",
    "ResultadoObdSbd",
    "ResultadoPrueba",
    "SioxConsulta",
    "SyncOutbox",
    "Vehiculo",
    "Verificacion",
    "StationSession",
    "UserStationPermission",
    "Workstation",
]
