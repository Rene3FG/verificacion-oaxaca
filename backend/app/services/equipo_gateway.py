"""Equipment Integration Contract v1 (Figma, `04 — Flows & Handoff`).

El backend no habla el protocolo del fabricante: abre una corrida con un
Equipment Gateway local (OPEN_SESSION + START), consulta su estado
(GET_STATUS / READ_DATA, que trae los DATA_EVENT recibidos) y la detiene
(STOP). Al hardware solo viaja el `test_run_id` y el método; placa, NIV o
el id del expediente nunca salen de aquí.

Modos (`settings.equipo_gateway_modo`):
- `manual` (default): sin gateway. El operador captura las lecturas como
  hasta ahora; ningún endpoint de equipo fabrica datos.
- `simulador`: `SimuladorGateway`, en memoria, para QA y demo mientras no
  exista el adaptador del proveedor. El avance de la corrida se calcula
  con el reloj (no hay tareas en segundo plano), así que las pruebas lo
  controlan inyectando `reloj`.

El adaptador real (HTTP/serial del proveedor) implementa la misma interfaz
`EquipmentGateway`; `get_equipment_gateway` es el único punto a cambiar.
"""

import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Callable, Protocol

from app.core.config import settings
from app.models.enums import MetodoPrueba


class EstadoEquipo(str, enum.Enum):
    """HU-041: estados visibles del equipo."""

    DESCONECTADO = "DESCONECTADO"
    CONECTANDO = "CONECTANDO"
    CONECTADO = "CONECTADO"
    CALIBRANDO = "CALIBRANDO"
    LISTO = "LISTO"
    PRUEBA_EN_PROCESO = "PRUEBA_EN_PROCESO"
    LECTURA_RECIBIDA = "LECTURA_RECIBIDA"
    FINALIZADA = "FINALIZADA"
    ERROR = "ERROR"


class EscenarioSimulador(str, enum.Enum):
    APROBADO = "APROBADO"
    RECHAZADO = "RECHAZADO"
    FALLA = "FALLA"


class CorridaNoEncontrada(Exception):
    """El gateway no conoce el test_run_id (p. ej. se reinició)."""


@dataclass
class Corrida:
    test_run_id: uuid.UUID
    metodo: MetodoPrueba
    estado: EstadoEquipo
    # DATA_EVENT recibidos, en orden: {"fase", "parametros", "t_s"}.
    lecturas: list[dict] = field(default_factory=list)
    # Payload normalizado (shape de app.schemas.prueba) solo en FINALIZADA.
    resultado: dict | None = None
    mensaje_tecnico: str | None = None

    def a_dict(self) -> dict:
        return {
            "test_run_id": str(self.test_run_id),
            "metodo": self.metodo.value,
            "estado": self.estado.value,
            "lecturas": self.lecturas,
            "resultado": self.resultado,
            "mensaje_tecnico": self.mensaje_tecnico,
        }


class EquipmentGateway(Protocol):
    modo: str

    async def get_status(self, estacion_id: uuid.UUID) -> tuple[EstadoEquipo, str | None]: ...

    async def open_session(
        self,
        estacion_id: uuid.UUID,
        test_run_id: uuid.UUID,
        metodo: MetodoPrueba,
        escenario: EscenarioSimulador | None = None,
    ) -> Corrida: ...

    async def read_data(self, test_run_id: uuid.UUID) -> Corrida: ...

    async def stop(self, test_run_id: uuid.UUID) -> None: ...


# --- Simulador -----------------------------------------------------------

# Segundos desde START. Conexión y calibración antes de medir, como un
# analizador real (cero/span).
_T_CONECTADO = 1.0
_T_CALIBRANDO = 2.0
_T_MIDIENDO = 4.0

# Lecturas por fase: (t_s, parámetros). La última muestra de cada fase es
# la que entra al resultado. APROBADO cae dentro de NOM-041/045 vigentes
# en el catálogo; RECHAZADO excede HC/CO (gasolina) o K (diésel).
_GASOLINA = {
    EscenarioSimulador.APROBADO: {"hc_ppm": 48, "co_pct": 0.21, "co2_pct": 14.6, "o2_pct": 0.4,
                                  "nox_ppm": 310, "lambda_factor": 1.01},
    EscenarioSimulador.RECHAZADO: {"hc_ppm": 420, "co_pct": 2.9, "co2_pct": 12.4, "o2_pct": 1.2,
                                   "nox_ppm": 900, "lambda_factor": 1.03},
}
_DIESEL_K = {EscenarioSimulador.APROBADO: 0.82, EscenarioSimulador.RECHAZADO: 2.74}

_T_FALLA = _T_MIDIENDO + 2.5
_MENSAJE_FALLA = "Sin DATA_EVENT del analizador en 2 s (timeout de comunicación)"


def _programa_gasolina(metodo: MetodoPrueba, escenario: EscenarioSimulador) -> list[dict]:
    base = _GASOLINA[escenario]
    eventos = []
    for i, (fase, velocidad) in enumerate((("ralenti", 24.0), ("crucero", 40.0))):
        for j, factor in enumerate((1.12, 1.05, 1.0)):
            # Solo los contaminantes se estabilizan; CO2 y lambda quedan fijos
            # para que CO+CO2 no salga del rango de dilución a mitad de fase.
            parametros = {k: round(v * factor, 3) if k in ("hc_ppm", "co_pct", "nox_ppm") else v
                          for k, v in base.items()}
            if metodo == MetodoPrueba.GAS_DYNAMIC:
                parametros["speed_kph"] = velocidad
            eventos.append({"fase": fase, "parametros": parametros,
                            "t_s": _T_MIDIENDO + i * 3.0 + j})
    return eventos


def _programa_diesel(escenario: EscenarioSimulador) -> list[dict]:
    k = _DIESEL_K[escenario]
    return [
        {"fase": f"aceleracion_{n}",
         "parametros": {"k_m1": round(k * f, 2), "opacity_pct": round(k * f * 15.5, 1),
                        "rpm_peak": 2950 + 40 * n},
         "t_s": _T_MIDIENDO + 2.0 * (n - 1)}
        for n, f in ((1, 1.04), (2, 0.98), (3, 0.99))
    ]


def _resultado(metodo: MetodoPrueba, eventos: list[dict]) -> dict:
    if metodo == MetodoPrueba.DIESEL_OPACITY:
        ks = [e["parametros"]["k_m1"] for e in eventos]
        # NOM-045: el coeficiente final es el promedio de las aceleraciones.
        return {
            "coefficient_absorption_final_k_m1": round(sum(ks) / len(ks), 2),
            "opacity_pct": eventos[-1]["parametros"]["opacity_pct"],
            "engine_temp_c": 88.0,
            "rpm_idle": 720.0,
            "rpm_governed_max": 3000.0,
            "rpm_peak": float(max(e["parametros"]["rpm_peak"] for e in eventos)),
            "aceleraciones": [e["parametros"] for e in eventos],
        }
    ultima = {e["fase"]: e["parametros"] for e in eventos}
    return {"ralenti": ultima["ralenti"], "crucero": ultima["crucero"]}


@dataclass
class _CorridaSimulada:
    estacion_id: uuid.UUID
    metodo: MetodoPrueba
    escenario: EscenarioSimulador
    inicio: float
    programa: list[dict]
    detenida: bool = False


class SimuladorGateway:
    modo = "simulador"

    def __init__(
        self,
        escenario: EscenarioSimulador = EscenarioSimulador.APROBADO,
        reloj: Callable[[], float] = time.monotonic,
    ):
        self.escenario = escenario
        self.reloj = reloj
        self._corridas: dict[uuid.UUID, _CorridaSimulada] = {}

    async def get_status(self, estacion_id: uuid.UUID) -> tuple[EstadoEquipo, str | None]:
        for run_id, c in self._corridas.items():
            if c.estacion_id == estacion_id and not c.detenida:
                corrida = await self.read_data(run_id)
                if corrida.estado not in (EstadoEquipo.FINALIZADA, EstadoEquipo.ERROR):
                    return corrida.estado, None
        return EstadoEquipo.LISTO, None

    async def open_session(self, estacion_id, test_run_id, metodo, escenario=None) -> Corrida:
        escenario = escenario or self.escenario
        if escenario == EscenarioSimulador.FALLA:
            programa = (_programa_diesel(EscenarioSimulador.APROBADO)
                        if metodo == MetodoPrueba.DIESEL_OPACITY
                        else _programa_gasolina(metodo, EscenarioSimulador.APROBADO))
            programa = [e for e in programa if e["t_s"] < _T_FALLA]
        elif metodo == MetodoPrueba.DIESEL_OPACITY:
            programa = _programa_diesel(escenario)
        else:
            programa = _programa_gasolina(metodo, escenario)
        # Una corrida nueva en la misma estación sustituye a la anterior.
        for c in self._corridas.values():
            if c.estacion_id == estacion_id:
                c.detenida = True
        self._corridas[test_run_id] = _CorridaSimulada(
            estacion_id, metodo, escenario, self.reloj(), programa
        )
        return await self.read_data(test_run_id)

    async def read_data(self, test_run_id: uuid.UUID) -> Corrida:
        c = self._corridas.get(test_run_id)
        if c is None:
            raise CorridaNoEncontrada(str(test_run_id))
        t = self.reloj() - c.inicio
        recibidas = [e for e in c.programa if e["t_s"] <= t]
        corrida = Corrida(test_run_id, c.metodo, EstadoEquipo.CONECTANDO, lecturas=recibidas)

        if c.detenida:
            corrida.estado = EstadoEquipo.DESCONECTADO
            corrida.mensaje_tecnico = "Corrida detenida (STOP)"
        elif c.escenario == EscenarioSimulador.FALLA and t >= _T_FALLA:
            corrida.estado = EstadoEquipo.ERROR
            corrida.mensaje_tecnico = _MENSAJE_FALLA
        elif c.escenario != EscenarioSimulador.FALLA and len(recibidas) == len(c.programa):
            corrida.estado = EstadoEquipo.FINALIZADA
            corrida.resultado = _resultado(c.metodo, recibidas)
        elif recibidas:
            # Medio segundo después de cada DATA_EVENT se muestra como
            # "lectura recibida"; el resto del tiempo, "prueba en proceso".
            reciente = t - recibidas[-1]["t_s"] < 0.5
            corrida.estado = (EstadoEquipo.LECTURA_RECIBIDA if reciente
                              else EstadoEquipo.PRUEBA_EN_PROCESO)
        elif t >= _T_MIDIENDO:
            corrida.estado = EstadoEquipo.PRUEBA_EN_PROCESO
        elif t >= _T_CALIBRANDO:
            corrida.estado = EstadoEquipo.CALIBRANDO
        elif t >= _T_CONECTADO:
            corrida.estado = EstadoEquipo.CONECTADO
        return corrida

    async def stop(self, test_run_id: uuid.UUID) -> None:
        c = self._corridas.get(test_run_id)
        if c is not None:
            c.detenida = True


_simulador: SimuladorGateway | None = None


def get_equipment_gateway() -> EquipmentGateway | None:
    """Dependencia de FastAPI. `None` = la línea opera en captura manual."""

    global _simulador
    if settings.equipo_gateway_modo != "simulador":
        return None
    if _simulador is None:
        _simulador = SimuladorGateway(EscenarioSimulador(settings.equipo_simulador_escenario))
    return _simulador
