# Propuesta: alineación del flujo de inspección visual con la NOM-047

**Fecha:** 2026-10-30
**Estado:** propuesta para coordinar con René. No hay código modificado.
**Alcance:** `backend/**`, `CapturaView.vue`, `PruebaView.vue` y `AdministracionPanel.vue` son de René; este documento solo propone y no cambia nada de eso.
**Fuente:** respuesta del cliente (Luis) del 2026-10-30, tal como la reportó Sebas. No se contrastó con el documento original.

---

## 1. Respuestas del cliente que motivan la propuesta

| Punto | Respuesta | Pendiente que cierra (`docs/PENDIENTES_2026-10-20.md`) |
|---|---|---|
| 3 | Todo el proceso debe poder hacerse sin internet: captura manual sin consulta SIOX, prueba de gasolina o diésel e impresión de resultados. | B4 |
| 4 | La inspección visual se hace antes de terminar la captura. Si un componente no cumple, es rechazo directo por inspección visual, se omite la prueba de emisiones y el expediente va a resultado de rechazo para imprimir su certificado. El OBD, cuando aplica, se hace antes de la prueba de emisiones. | B7 / Q1 |
| 5 | El campo 001 del certificado es el ID del técnico. Las plantillas de sobreimpresión (Particular, Intensivo, Doble Cero) son las mismas para aprobados y rechazados, e imprimen los valores obtenidos y la potencia por norma. | B1, B9, B10(b) |

---

## 2. Diagnóstico: qué ya se cumple y qué cambia

Revisé `state_machine.py`, `inspeccion.py`, `obd.py`, `certificado.py` y las dos vistas. **Casi todo el flujo pedido ya existe**; lo que cambia es la estación y un dato del certificado.

| Requisito del cliente | Estado actual en el código | ¿Cambia? |
|---|---|---|
| Rechazo visual va directo a resultado de rechazo sin prueba de emisiones | Ya existe. `INSPECCION_VISUAL_RECHAZADA` pasa a `PENDIENTE_DE_IMPRESION_RECHAZO` en la misma petición (`inspeccion.py`, evento `rechazo_enviado_a_impresion`). Las causales quedan en `causales_rechazo` y el certificado se infiere como `RECHAZO`. | No |
| OBD antes de la prueba de emisiones | Ya existe. `INSPECCION_VISUAL_APROBADA` pasa a `OBD_NO_APLICA` u `OBD_PENDIENTE`, y de ahí a `LISTO_PARA_PRUEBA`. | No |
| La inspección visual la hace Captura, antes de terminar la captura | Hoy la registra la estación de **Prueba**. `inspeccion.py` exige `StationType.PRUEBA` en `GET /checklist` y en `POST /{id}`; `CapturaView` termina al normalizar y el checklist vive en `PruebaView`. | **Sí** |
| Operación sin internet | La cola `sync_outbox` y el servidor local ya operan sin internet; la captura manual sin SIOX y `imprimir-resultados` existen. | No (se confirma) |
| Campo 001 = ID del técnico | Hoy es el parámetro fijo `certificado_numero_equipo` (por defecto `001`), igual para todos. | **Sí** |
| Plantillas únicas para aprobados y rechazados | Hoy el rechazo usa `_LAYOUT_RECHAZO` (de `RECHAZO.doc`: sin holograma, con fecha límite). | **Por aclarar** (sección 6) |

### Equivalencia de nombres de estado

La propuesta no necesita estados nuevos. Los nombres que se manejaron al plantear el flujo equivalen a estos:

| Nombre planteado | Estado real |
|---|---|
| `CREADO` | `CREADO` |
| `CAPTURA_VEHICULO` | `DATOS_SIOX_IMPORTADOS` o `DATOS_CAPTURADOS_MANUALMENTE` (y luego `DATOS_NORMALIZADOS`) |
| `INSPECCION_VISUAL` | `INSPECCION_VISUAL_PENDIENTE` |
| `OBD_PENDIENTE` | `OBD_PENDIENTE` (o `OBD_NO_APLICA`) |
| `PRUEBA_PENDIENTE` | `LISTO_PARA_PRUEBA` |
| `RECHAZADO` / `IMPRESION_PENDIENTE` | `INSPECCION_VISUAL_RECHAZADA` y luego `PENDIENTE_DE_IMPRESION_RECHAZO` |
| Motivo "Rechazo en inspección visual" | `causales_rechazo` (puntos en MALO y observaciones) más `certificado_tipo = RECHAZO` |

---

## 3. Flujo propuesto (sin estados nuevos)

```
CAPTURA (caseta)                                  PRUEBA                         IMPRESIÓN CENTRAL
CREADO
  -> DATOS_SIOX_IMPORTADOS / DATOS_CAPTURADOS_MANUALMENTE
  -> DATOS_NORMALIZADOS (confirmar datos)
  -> INSPECCION_VISUAL_PENDIENTE
       |-- aprueba --> INSPECCION_VISUAL_APROBADA --> OBD_NO_APLICA / OBD_PENDIENTE
       |                                               -> OBD_SOLICITADO -> OBD_RECIBIDO
       |                                               -> LISTO_PARA_PRUEBA -> PRUEBA_CONFIGURADA
       |                                               -> PRUEBA_EN_PROCESO -> PRUEBA_FINALIZADA
       |                                               -> PENDIENTE_IMPRESION / PENDIENTE_DE_IMPRESION_RECHAZO
       `-- rechaza --> INSPECCION_VISUAL_RECHAZADA -> PENDIENTE_DE_IMPRESION_RECHAZO  (sin prueba de emisiones)
```

Los estados y las transiciones son los de hoy. **Lo único que cambia es qué estación registra el tramo `INSPECCION_VISUAL_PENDIENTE` → `APROBADA` o `RECHAZADA`: pasa de Prueba a Captura.**

### Dos formas de implementarlo

- **Opción A (recomendada): mover la estación, sin tocar la máquina de estados.** La inspección sigue después de normalizar, pero la hace la caseta. "Terminar la captura" pasa a significar que el expediente ya tiene la inspección aprobada. Cambia solo quién puede llamar a los endpoints y qué cola ve cada pantalla. No hay migración de datos ni expedientes en vuelo que reubicar.
- **Opción B: reordenar los estados**, de modo que la inspección ocurra antes de `DATOS_NORMALIZADOS`. Exige cambiar `ALLOWED_TRANSITIONS`, `ESTADOS_NORMALIZABLES`, `CANCELABLE_FROM`, el flujo de `/normalizar`, las colas y decidir qué hacer con los expedientes que estén en `DATOS_NORMALIZADOS` o `INSPECCION_VISUAL_PENDIENTE` al desplegar. Solo vale la pena si el cliente quiere de verdad que la inspección ocurra **antes de confirmar los datos**.

La diferencia depende de una pregunta (sección 7, pregunta 1): qué significa "terminar la captura" para el cliente.

---

## 4. Cambios sugeridos (Opción A)

### Backend (René)

| Archivo | Cambio |
|---|---|
| `app/api/routers/inspeccion.py` | En `GET /checklist` y `POST /{id}`, cambiar `requiere_estacion(StationType.PRUEBA)` por `requiere_estacion(StationType.CAPTURA)`. Para una transición gradual se puede aceptar `CAPTURA` y `PRUEBA` a la vez, como ya hace `datos-certificado`. |
| `app/api/routers/pruebas.py` y colas | Revisar que la cola de Prueba empiece en `INSPECCION_VISUAL_APROBADA`, ya que `INSPECCION_VISUAL_PENDIENTE` pasa a ser de Captura. |
| `app/api/routers/expedientes.py` | `/normalizar` sigue igual; su mensaje deja de decir "enviado a Inspección Visual en Prueba". |
| `app/services/certificado.py` | Ver sección 5 (campo 001). |
| Pruebas de backend | Ajustar `test_inspeccion.py` y las que crean la estación de Prueba para inspeccionar. |

### `CapturaView.vue` (René)

- `ESTADOS_CAPTURA` termina hoy en `DATOS_CAPTURADOS_MANUALMENTE`. Agregar `INSPECCION_VISUAL_PENDIENTE` para que el expediente siga en la lista de Captura después de confirmar los datos.
- Agregar el paso del checklist (los 8 puntos Bueno, Malo o No aplica, leídos de `GET /api/inspeccion/checklist`), con observaciones y causales como hoy en `PruebaView`.
- Con inspección aprobada, mostrar que el expediente pasa a Prueba. Con rechazo, mostrar que va directo a Impresión Central (el aviso de `CapturaView` ya sobrevive al cierre desde `0511486`, y conviene que el rechazo salga en ámbar como en `PruebaView`).
- El indicador de pasos ya tiene el paso "Inspección visual", pero con el subtítulo "Estación de Prueba". Cambiarlo a "Captura" y hacer que `pasoActual`, que hoy devuelve 1 para los estados de captura y 2 para el resto, ubique la inspección dentro de Captura.

### `PruebaView.vue` (René)

- Quitar de `ESTADOS_PRUEBA` el estado `INSPECCION_VISUAL_PENDIENTE` (se puede dejar durante la transición).
- Retirar el bloque del checklist de inspección visual, que se mueve a Captura. Quedan el OBD, la configuración y la prueba.

### Pruebas de frontend (Sebas)

- `CapturaView.test.js`: agregar el checklist (completo, aprobado, rechazado con aviso en ámbar y errores).
- `PruebaView.test.js`: mover o adaptar las 7 pruebas del bloque "Inspección visual" y las 3 del bloque de avisos que llaman a `registrarInspeccion` (inspección rechazada en la lista, inspección aprobada en el detalle y cierre del aviso con la X).

---

## 5. Campo 001 → ID del técnico

**Hoy:** `cargar_config_certificado` lee el parámetro `certificado_numero_equipo` (por defecto `001`) y `generar_pdf_certificado` lo imprime en la clave de layout `equipo_numero` de las tres copias.

**Propuesta:**

1. Agregar `clave_tecnico` (texto, opcional) a `cat_usuarios`, con su migración. No hay hoy ningún campo para eso.
2. Capturarla en el alta y la edición de usuarios (`AdministracionPanel.vue`, campo "Clave de técnico").
3. Resolver el técnico al generar la proyección del certificado, no al imprimir: tomar `operador_id` del `ResultadoPrueba` si existe y, si no (rechazo visual), el `operador_id` de `InspeccionVisual`. Guardar `tecnico_clave` en `certificate_projection_json`, que se fija una sola vez, para que una reimpresión conserve el mismo técnico.
4. En `certificado.py`, imprimir ese valor en `equipo_numero`.
5. Si el usuario no tiene clave, **decidir entre** (a) usar el parámetro actual como respaldo o (b) bloquear la impresión con un 409 que pida capturarla, igual que `campos_obligatorios_faltantes`. Recomiendo (b): imprimir un número equivocado en un certificado oficial es peor que detener la impresión.

**Nota relacionada:** con el catálogo `cat_equipos` (F4) ya existe la marca real del equipo. La marca `OBERTECH` que hoy sale del parámetro `certificado_marca_equipo` podría salir del equipo que midió. Está fuera de esta propuesta y se menciona solo para que no se pierda.

---

## 6. Plantillas únicas para aprobados y rechazados

El cliente dice que las plantillas oficiales son las mismas para aprobados y rechazados, e imprimen los valores obtenidos y la potencia por norma. Eso **no coincide** con lo implementado el 2026-10-22: `_LAYOUT_RECHAZO` sale de `RECHAZO.doc`, que el propio cliente entregó, y omite el holograma y agrega la fecha límite.

No conviene asumir cuál prevalece. Posibles lecturas:

1. `RECHAZO.doc` queda obsoleta y el rechazo imprime sobre la plantilla del tipo que corresponda.
2. Se usa la plantilla única pero conserva la fecha límite y la ausencia de holograma.
3. Solo se refiere al rechazo **por prueba de emisiones** (que sí tiene valores obtenidos y potencia), y el rechazo visual, que no tiene valores, sigue con `RECHAZO.doc`.

Un rechazo visual no tiene lecturas ni potencia que imprimir; por eso la lectura 3 parece la más coherente, pero hay que confirmarla antes de tocar `_LAYOUT_RECHAZO`.

---

## 7. Preguntas abiertas

Para el cliente, vía Luis:

1. ¿"Antes de terminar la captura" significa antes de **confirmar los datos del vehículo** (Opción B) o antes de que el expediente **salga de la caseta hacia Prueba** (Opción A)?
2. ¿Qué plantilla imprime un rechazo visual y uno por emisiones? (sección 6)
3. ¿El ID del técnico es una clave nueva por usuario o es su usuario del sistema?
4. Si la inspección visual y la prueba las hacen técnicos distintos, ¿cuál va en el campo 001?

Para René:

1. ¿Prefiere la Opción A o la B?
2. ¿La estación de Prueba debe seguir pudiendo inspeccionar durante la transición?
3. ¿Dónde se agrega `clave_tecnico`: migración propia o dentro de la próxima?

---

## 8. Efecto en la trazabilidad y las pruebas

- Las HUs de las Etapas 3 y 4 describen estados y reglas, no la estación, por lo que **no cambian de estado** en la matriz. El cambio de estación es una realineación de comportamiento (el criterio de HU-021 a HU-027 se mantiene).
- HU-070 sigue en HECHO: su criterio es el folio y el bloqueo de impresión.
- Tras implementarse, hay que actualizar las pruebas citadas en la sección 4 y la evidencia de las HUs de inspección visual.
