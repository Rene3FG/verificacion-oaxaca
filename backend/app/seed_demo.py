"""Datos de demostración: 6 expedientes en distintos puntos del flujo,
sobre el seed normal (`python -m app.seed`), para grabar el video del
sistema sin partir de una base vacía.

Idempotente por placa: si un expediente con esa placa ya existe, se omite
por completo (no se duplica ni se actualiza).

Uso: python -m app.seed_demo
"""

import asyncio
import datetime
import uuid

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.enums import (
    EstadoVerificacion,
    FuenteDatos,
    ResultadoFinal,
    ResultadoInspeccionVisual,
    ResultadoPruebaEnum,
    TipoPrueba,
)
from app.models.inspeccion_visual import InspeccionVisual
from app.models.resultado_obd_sbd import ResultadoObdSbd
from app.models.resultado_prueba import ResultadoPrueba
from app.models.siox_consulta import EstadoSioxConsulta, SioxConsulta
from app.models.vehiculo import Vehiculo
from app.models.verificacion import Verificacion
from app.seed import TEST_USER2_ID, TEST_USER_ID

CENTRO = "reforma"


def _ahora() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


async def _existe(db, placa: str) -> bool:
    result = await db.execute(select(Verificacion).where(Verificacion.placa == placa))
    return result.scalar_one_or_none() is not None


async def _crear_vehiculo(db, **kwargs) -> Vehiculo:
    vehiculo = Vehiculo(**kwargs)
    db.add(vehiculo)
    await db.flush()
    return vehiculo


async def _crear_expediente(
    db, *, vehiculo: Vehiculo, linea_id: int, operador_id: uuid.UUID, estado, **kwargs
) -> Verificacion:
    verificacion = Verificacion(
        vehiculo_id=vehiculo.id,
        placa=vehiculo.placa,
        centro_id=CENTRO,
        linea_id=linea_id,
        operador_id=operador_id,
        estado=estado,
        **kwargs,
    )
    db.add(verificacion)
    await db.flush()
    return verificacion


async def _siox_consulta_exitosa(db, verificacion: Verificacion, vehiculo: Vehiculo) -> None:
    db.add(
        SioxConsulta(
            verificacion_id=verificacion.id,
            placa=vehiculo.placa,
            status=EstadoSioxConsulta.EXITOSA,
            response_normalized={
                "marca": vehiculo.marca,
                "linea": vehiculo.linea,
                "modelo": vehiculo.modelo,
                "tipo_vehiculo": vehiculo.tipo_vehiculo,
                "combustible": vehiculo.combustible,
            },
            consultado_por=verificacion.operador_id,
        )
    )


async def _inspeccion_aprobada(db, verificacion: Verificacion) -> None:
    db.add(
        InspeccionVisual(
            verificacion_id=verificacion.id,
            resultado=ResultadoInspeccionVisual.APROBADA,
            checklist_json={
                "luces": "bien",
                "limpiaparabrisas_claxon": "bien",
                "espejos": "bien",
                "llantas": "bien",
                "fugas": "bien",
                "escape": "bien",
                "placas": "bien",
            },
            operador_id=verificacion.operador_id,
        )
    )


async def seed_demo() -> None:
    async with SessionLocal() as db:
        creados = []

        # 1) Recién creado en línea 1, listo para consultar SIOX.
        placa = "JTP-451-A"
        if not await _existe(db, placa):
            vehiculo = await _crear_vehiculo(
                db, placa=placa, fuente_datos=FuenteDatos.MANUAL
            )
            await _crear_expediente(
                db,
                vehiculo=vehiculo,
                linea_id=1,
                operador_id=TEST_USER_ID,
                estado=EstadoVerificacion.CREADO,
            )
            creados.append(placa)

        # 2) Ya normalizado, listo para inspección visual.
        placa = "PXR-228-C"
        if not await _existe(db, placa):
            vehiculo = await _crear_vehiculo(
                db,
                placa=placa,
                marca="Volkswagen",
                linea="Jetta",
                modelo=2020,
                tipo_vehiculo="vehiculo",
                combustible="gasolina",
                fuente_datos=FuenteDatos.SIOX,
            )
            verificacion = await _crear_expediente(
                db,
                vehiculo=vehiculo,
                linea_id=1,
                operador_id=TEST_USER_ID,
                estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE,
                combustible_validado="gasolina",
            )
            await _siox_consulta_exitosa(db, verificacion, vehiculo)
            creados.append(placa)

        # 3) Inspección aprobada y OBD hecho, listo para prueba.
        placa = "GVN-091-B"
        if not await _existe(db, placa):
            vehiculo = await _crear_vehiculo(
                db,
                placa=placa,
                marca="Chevrolet",
                linea="Aveo",
                modelo=2021,
                tipo_vehiculo="vehiculo",
                combustible="gasolina",
                fuente_datos=FuenteDatos.SIOX,
            )
            verificacion = await _crear_expediente(
                db,
                vehiculo=vehiculo,
                linea_id=1,
                operador_id=TEST_USER_ID,
                estado=EstadoVerificacion.LISTO_PARA_PRUEBA,
                combustible_validado="gasolina",
            )
            await _siox_consulta_exitosa(db, verificacion, vehiculo)
            await _inspeccion_aprobada(db, verificacion)
            db.add(
                ResultadoObdSbd(
                    verificacion_id=verificacion.id,
                    aplica=True,
                    solicitado_at=_ahora(),
                    recibido_at=_ahora(),
                    resultado=ResultadoPruebaEnum.APROBADO,
                    operador_id=TEST_USER_ID,
                )
            )
            creados.append(placa)

        # 4) Prueba aprobada, esperando impresión.
        placa = "MKD-674-D"
        if not await _existe(db, placa):
            vehiculo = await _crear_vehiculo(
                db,
                placa=placa,
                marca="Nissan",
                linea="NP300",
                modelo=2018,
                tipo_vehiculo="vehiculo",
                combustible="diesel",
                fuente_datos=FuenteDatos.SIOX,
            )
            verificacion = await _crear_expediente(
                db,
                vehiculo=vehiculo,
                linea_id=1,
                operador_id=TEST_USER_ID,
                estado=EstadoVerificacion.PENDIENTE_IMPRESION,
                combustible_validado="diesel",
                tipo_prueba_final=TipoPrueba.OPACIDAD,
                resultado_final=ResultadoFinal.APROBADO,
            )
            await _siox_consulta_exitosa(db, verificacion, vehiculo)
            await _inspeccion_aprobada(db, verificacion)
            db.add(
                ResultadoObdSbd(verificacion_id=verificacion.id, aplica=False)
            )
            db.add(
                ResultadoPrueba(
                    verificacion_id=verificacion.id,
                    tipo_prueba=TipoPrueba.OPACIDAD,
                    combustible="diesel",
                    resultado=ResultadoPruebaEnum.APROBADO,
                    valores_medidos_json={"opacidad_porcentaje": 32.5},
                    limites_aplicados_json={"opacidad_maxima": 50},
                    linea_id=1,
                    operador_id=TEST_USER_ID,
                    started_at=_ahora(),
                    finished_at=_ahora(),
                )
            )
            creados.append(placa)

        # 5) Rechazado en inspección visual, esperando certificado de rechazo.
        placa = "RSC-238-F"
        if not await _existe(db, placa):
            vehiculo = await _crear_vehiculo(
                db,
                placa=placa,
                marca="Kia",
                linea="Rio",
                modelo=2017,
                tipo_vehiculo="vehiculo",
                combustible="gasolina",
                fuente_datos=FuenteDatos.SIOX,
            )
            verificacion = await _crear_expediente(
                db,
                vehiculo=vehiculo,
                linea_id=1,
                operador_id=TEST_USER_ID,
                estado=EstadoVerificacion.PENDIENTE_DE_IMPRESION_RECHAZO,
                combustible_validado="gasolina",
            )
            await _siox_consulta_exitosa(db, verificacion, vehiculo)
            db.add(
                InspeccionVisual(
                    verificacion_id=verificacion.id,
                    resultado=ResultadoInspeccionVisual.RECHAZADA,
                    checklist_json={
                        "luces": "malo",
                        "limpiaparabrisas_claxon": "bien",
                        "espejos": "bien",
                        "llantas": "bien",
                        "fugas": "bien",
                        "escape": "bien",
                        "placas": "bien",
                    },
                    causales_rechazo={"luces": "Micas rotas, luz delantera derecha fundida"},
                    operador_id=TEST_USER_ID,
                )
            )
            creados.append(placa)

        # 6) En línea 2, para intentar abrirlo desde línea 1 y que salte el 403.
        placa = "LQW-812-E"
        if not await _existe(db, placa):
            vehiculo = await _crear_vehiculo(
                db,
                placa=placa,
                marca="Chevrolet",
                linea="Spark",
                modelo=2020,
                tipo_vehiculo="vehiculo",
                combustible="gasolina",
                fuente_datos=FuenteDatos.SIOX,
            )
            verificacion = await _crear_expediente(
                db,
                vehiculo=vehiculo,
                linea_id=2,
                operador_id=TEST_USER2_ID,
                estado=EstadoVerificacion.INSPECCION_VISUAL_PENDIENTE,
                combustible_validado="gasolina",
            )
            await _siox_consulta_exitosa(db, verificacion, vehiculo)
            creados.append(placa)

        await db.commit()

    if creados:
        print(f"Seed de demo aplicado. Expedientes creados: {', '.join(creados)}")
    else:
        print("Seed de demo ya estaba aplicado, nada que crear.")


if __name__ == "__main__":
    asyncio.run(seed_demo())
