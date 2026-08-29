// Formato de fecha/hora compartido por las vistas de estación (Captura,
// Prueba, Impresión) — antes vivía duplicado dentro de ImpresionView.vue.
export function formatearFecha(iso) {
  if (!iso) return null;
  return new Date(iso).toLocaleString("es-MX", {
    dateStyle: "short",
    timeStyle: "short",
  });
}
