import { estadoColors } from "../plugins/vuetify";

// Texto normalizado + ícono por estado del expediente (HU-098-100).
// Único lugar donde se traduce `EstadoVerificacion` a algo legible para el
// operador — ExpedienteHeader.vue y SupervisorView.vue lo comparten en vez
// de mostrar el nombre crudo del enum o duplicar su propio mapeo.
const ESTADO_INFO = {
  CREADO: { texto: "Creado", icono: "mdi-file-plus-outline" },
  DATOS_SIOX_CONSULTADOS: { texto: "SIOX consultado", icono: "mdi-magnify" },
  DATOS_SIOX_IMPORTADOS: { texto: "Datos importados de SIOX", icono: "mdi-database-import-outline" },
  DATOS_CAPTURADOS_MANUALMENTE: { texto: "Captura manual", icono: "mdi-pencil-outline" },
  DATOS_NORMALIZADOS: { texto: "Datos normalizados", icono: "mdi-check-decagram-outline" },
  INSPECCION_VISUAL_PENDIENTE: { texto: "Inspección visual pendiente", icono: "mdi-eye-outline" },
  INSPECCION_VISUAL_APROBADA: { texto: "Inspección visual aprobada", icono: "mdi-eye-check-outline" },
  INSPECCION_VISUAL_RECHAZADA: { texto: "Inspección visual rechazada", icono: "mdi-eye-remove-outline" },
  OBD_NO_APLICA: { texto: "OBD no aplica", icono: "mdi-minus-circle-outline" },
  OBD_PENDIENTE: { texto: "OBD pendiente", icono: "mdi-chip" },
  OBD_SOLICITADO: { texto: "OBD solicitado", icono: "mdi-chip" },
  OBD_RECIBIDO: { texto: "OBD recibido", icono: "mdi-chip" },
  LISTO_PARA_PRUEBA: { texto: "Listo para prueba", icono: "mdi-clipboard-check-outline" },
  PRUEBA_CONFIGURADA: { texto: "Prueba configurada", icono: "mdi-cog-outline" },
  PRUEBA_EN_PROCESO: { texto: "Prueba en proceso", icono: "mdi-progress-clock" },
  PRUEBA_FINALIZADA: { texto: "Prueba finalizada", icono: "mdi-clipboard-check-outline" },
  PENDIENTE_IMPRESION: { texto: "Pendiente de impresión", icono: "mdi-printer-outline" },
  PENDIENTE_DE_IMPRESION_RECHAZO: { texto: "Pendiente de impresión (rechazo)", icono: "mdi-printer-off-outline" },
  FOLIO_SOLICITADO: { texto: "Folio solicitado", icono: "mdi-ticket-outline" },
  FOLIO_ASIGNADO: { texto: "Folio asignado", icono: "mdi-ticket-confirmation-outline" },
  IMPRESO: { texto: "Impreso", icono: "mdi-printer-check" },
  CERRADO_APROBADO: { texto: "Cerrado — aprobado", icono: "mdi-check-circle-outline" },
  CERRADO_RECHAZADO: { texto: "Cerrado — rechazado", icono: "mdi-close-circle-outline" },
  ERROR_INTEGRACION: { texto: "Error de integración", icono: "mdi-alert-outline" },
  IMPRESION_FALLIDA: { texto: "Impresión fallida", icono: "mdi-printer-alert" },
  FOLIO_ERROR: { texto: "Error de folio", icono: "mdi-alert-outline" },
  CANCELADO: { texto: "Cancelado", icono: "mdi-cancel" },
};

// Mapeo simplificado estado -> color semántico; ver guidelines de diseño
// (sección "Estados visuales del expediente") para el catálogo completo.
export function colorEstado(estado) {
  if (estado?.includes("RECHAZAD") || estado?.includes("ERROR") || estado?.includes("FALLIDA")) {
    return estadoColors.rechazado;
  }
  if (estado?.includes("APROBAD") || estado === "IMPRESO") {
    return estadoColors.aprobado;
  }
  if (estado?.includes("PROCESO") || estado?.includes("SOLICITADO")) {
    return estadoColors.proceso;
  }
  return estadoColors.pendiente;
}

export function textoEstado(estado) {
  return ESTADO_INFO[estado]?.texto ?? estado ?? "—";
}

export function iconoEstado(estado) {
  return ESTADO_INFO[estado]?.icono ?? "mdi-help-circle-outline";
}
