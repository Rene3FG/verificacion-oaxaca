"""'Certificate Result Projection Contract v1' (revisión Figma 2026-08-24,
sección 4): genera el snapshot inmutable `certificate_projection_json` que
la capa de impresión sobreimprime — nunca desde `raw_payload`/`raw_frame`,
siempre desde `ResultadoPrueba.valores_medidos_json` (la fuente autoritativa
según el contrato).

Se genera una sola vez, antes del primer clic en Imprimir (ver
`app.api.routers.impresion.imprimir_certificado`), y se conserva sin
cambios en cada reintento técnico. Una reimpresión AUTORIZADA (folio
dañado, corrección de tipo post-impresión) vuelve a llamar a
`generar_proyeccion_certificado` con el folio/tipo nuevos — el resultado
técnico (`test_result_id`, lecturas, evaluation_result) no cambia porque
sigue viniendo de la misma fila de `ResultadoPrueba`, inmutable."""

import datetime

from app.models.enums import MetodoPrueba, TipoCertificado
from app.models.resultado_prueba import ResultadoPrueba
from app.models.verificacion import Verificacion
from app.schemas.prueba import MetodoSinMapeo, metodo_de

PROJECTION_VERSION = "v1"

# Sección 4, nota de pie: "Estado v1: mapping físico de aprobados gasolina
# y diésel incorporados." Los 3 métodos con mapping aprobado hoy.
LAYOUT_VERSION_POR_METODO = {
    MetodoPrueba.GAS_STATIC: "v1",
    MetodoPrueba.GAS_DYNAMIC: "v1",
    MetodoPrueba.DIESEL_OPACITY: "v1",
}


class LayoutSinMapeo(Exception):
    """El método no tiene layout_version aprobado — Preview/Print deben
    bloquearse por configuración (sección 4, bloque 04, regla explícita)."""


def calcular_semestre(
    fecha: datetime.date, fecha_final_prorroga: datetime.date | None = None
) -> int:
    """Sección 5 del handoff: "cálculo automático (1 ene-30 jun = 1°; 1
    jul-31 dic = 2°)". Con una prórroga activa (`fecha <=
    fecha_final_prorroga`) se fuerza Semestre 1 sin importar el mes — la
    excepción documentada explícitamente ("hasta ese día se imprime
    Semestre 1 para todos los vehículos"); no se contempla prórroga del 2º
    periodo. `fecha_final_prorroga=None` (sin prórroga vigente) es el
    comportamiento de siempre. El llamador resuelve la prórroga vigente
    (`app.services.semestre.obtener_prorroga_activa`) — esta función se
    mantiene pura, sin acceso a base de datos."""

    if fecha_final_prorroga is not None and fecha <= fecha_final_prorroga:
        return 1
    return 1 if fecha.month <= 6 else 2


def _redondear(valor: float | None, decimales: int = 2) -> float | None:
    return None if valor is None else round(valor, decimales)


def _campos_gasolina(valores_medidos: dict) -> dict:
    campos = {}
    for fase in ("ralenti", "crucero"):
        lectura = valores_medidos[fase]
        campos[fase] = {
            "hc_ppm": lectura["hc_ppm"],
            "co_pct": lectura["co_pct"],
            "co2_pct": lectura["co2_pct"],
            "co_co2_pct": _redondear(lectura["co_pct"] + lectura["co2_pct"]),
            "o2_pct": lectura["o2_pct"],
            "nox_ppm": lectura.get("nox_ppm"),
            "speed_kph": lectura.get("speed_kph"),
        }
    return campos


def _campos_diesel(valores_medidos: dict) -> dict:
    # Sección 4, bloque 04: únicamente el coeficiente de absorción entra al
    # payload de impresión — el resto (engine_temp_c, rpm_idle,
    # rpm_governed_max, aceleraciones, opacity_pct, rpm_peak) se queda como
    # evidencia en ResultadoPrueba.valores_medidos_json, no se sobreimprime.
    return {"coefficient_absorption_final_k_m1": valores_medidos["coefficient_absorption_final_k_m1"]}


def generar_proyeccion_certificado(
    verificacion: Verificacion,
    resultado_prueba: ResultadoPrueba | None,
    *,
    fecha_final_prorroga: datetime.date | None = None,
) -> dict:
    """`resultado_prueba` es `None` cuando el rechazo viene de inspección
    visual (nunca pasó por Prueba) — el contrato (sección 4) no define un
    payload de sobreimpresión para ese camino; se genera con `method`/
    `fields` vacíos, documentado como hueco del contrato, no inventado.

    `fecha_final_prorroga`: ver `calcular_semestre` — la resuelve el
    llamador (`app.services.semestre.obtener_prorroga_activa`), esta
    función no consulta la base de datos por su cuenta."""

    metodo = None
    layout_version = None
    fields: dict = {}
    test_result_id = None
    evaluation_result = None

    if resultado_prueba is not None:
        try:
            metodo = metodo_de(verificacion.tipo_prueba_final)
        except MetodoSinMapeo as exc:
            raise LayoutSinMapeo(str(exc)) from exc
        layout_version = LAYOUT_VERSION_POR_METODO.get(metodo)
        if layout_version is None:
            raise LayoutSinMapeo(
                f"El método {metodo.value} no tiene layout_version aprobado; "
                "Preview/Print quedan bloqueados por configuración."
            )
        fields = (
            _campos_diesel(resultado_prueba.valores_medidos_json)
            if metodo == MetodoPrueba.DIESEL_OPACITY
            else _campos_gasolina(resultado_prueba.valores_medidos_json)
        )
        test_result_id = str(resultado_prueba.id)
        evaluation_result = resultado_prueba.resultado.value if resultado_prueba.resultado else None
    elif verificacion.certificado_tipo == TipoCertificado.RECHAZO.value:
        evaluation_result = "RECHAZADO"

    return {
        "projection_version": PROJECTION_VERSION,
        "layout_version": layout_version,
        "certificate_type": verificacion.certificado_tipo,
        "verification_type": verificacion.tipo_prueba_final.value
        if verificacion.tipo_prueba_final
        else None,
        "test_result_id": test_result_id,
        "method": metodo.value if metodo else None,
        "semestre": calcular_semestre(
            datetime.datetime.now(datetime.timezone.utc).date(), fecha_final_prorroga
        ),
        "fields": fields,
        "evaluation_result": evaluation_result,
        "generated_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
