import { describe, expect, it } from "vitest";
import { colorEstado, iconoEstado, textoEstado } from "../src/utils/estado";

// Espejo de EstadoVerificacion en backend/app/models/enums.py: si el
// backend agrega un estado y aquí no tiene etiqueta, esta prueba lo avisa.
const ESTADOS = [
  "CREADO", "DATOS_SIOX_CONSULTADOS", "DATOS_SIOX_IMPORTADOS",
  "DATOS_CAPTURADOS_MANUALMENTE", "DATOS_NORMALIZADOS",
  "INSPECCION_VISUAL_PENDIENTE", "INSPECCION_VISUAL_APROBADA",
  "INSPECCION_VISUAL_RECHAZADA", "OBD_NO_APLICA", "OBD_PENDIENTE",
  "OBD_SOLICITADO", "OBD_RECIBIDO", "LISTO_PARA_PRUEBA", "PRUEBA_CONFIGURADA",
  "PRUEBA_EN_PROCESO", "PRUEBA_FINALIZADA", "PENDIENTE_IMPRESION",
  "PENDIENTE_DE_IMPRESION_RECHAZO", "FOLIO_SOLICITADO", "FOLIO_ASIGNADO",
  "IMPRESO", "CERRADO_APROBADO", "CERRADO_RECHAZADO", "ERROR_INTEGRACION",
  "IMPRESION_FALLIDA", "FOLIO_ERROR", "CANCELADO",
];

describe("estado (HU-098/099/100)", () => {
  it.each(ESTADOS)("%s tiene etiqueta legible, ícono propio y color", (e) => {
    expect(textoEstado(e)).not.toBe(e);
    expect(iconoEstado(e)).not.toBe("mdi-help-circle-outline");
    expect(typeof colorEstado(e)).toBe("string");
  });

  it("estado desconocido o vacío no rompe", () => {
    expect(textoEstado("NUEVO_X")).toBe("NUEVO_X");
    expect(textoEstado(null)).toBe("—");
    expect(iconoEstado("NUEVO_X")).toBe("mdi-help-circle-outline");
  });

  it("errores y rechazos en rojo, aprobados en verde, proceso en ámbar", () => {
    for (const e of ["CERRADO_RECHAZADO", "FOLIO_ERROR", "IMPRESION_FALLIDA", "ERROR_INTEGRACION"])
      expect(colorEstado(e)).toBe("error");
    for (const e of ["CERRADO_APROBADO", "IMPRESO", "INSPECCION_VISUAL_APROBADA"])
      expect(colorEstado(e)).toBe("success");
    for (const e of ["PRUEBA_EN_PROCESO", "FOLIO_SOLICITADO"])
      expect(colorEstado(e)).toBe("warning");
  });
});
