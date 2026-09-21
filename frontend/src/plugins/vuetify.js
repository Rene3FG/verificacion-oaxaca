import "@mdi/font/css/materialdesignicons.css";
import "vuetify/styles";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";
import { es } from "vuetify/locale";

// Escala de guinda institucional — extraída de Figma "01 — Foundations"
// (sección 13 del handoff). Portada desde `frontend-impresion-central`
// (Sebastián), donde ya está validada contra el Figma — no reextraída de
// cero aquí. "Regla de marca" del propio Figma: el guinda #9D2449 (600)
// identifica acciones/jerarquía/marca; los estados operativos (éxito/
// advertencia/error/información) son independientes, no se derivan de
// esta escala — ver `estadoColors`/`colors` abajo.
export const guinda = {
  50: "#FDF3F6",
  100: "#F9E0E8",
  200: "#F1BDCE",
  300: "#E58BA7",
  400: "#D2577E",
  500: "#B93661",
  600: "#9D2449",
  700: "#7F1D3B",
  800: "#641831",
  900: "#491226",
  950: "#2D0A17",
};

// Colores semánticos por estado, según Figma "01 — Foundations" (mismo
// origen que `guinda`). Los nombres de estado del sistema (pendiente,
// consultado, proceso, aprobado, rechazado, error, impreso) se mapean a
// los 4 tokens semánticos del design system: éxito, advertencia, error,
// información. `pendiente`/`consultado` no tienen tono propio en el
// Figma — se quedan en gris/azul neutro hasta que el diseño defina uno.
export const estadoColors = {
  pendiente: "grey",
  consultado: "info",
  proceso: "warning",
  aprobado: "success",
  rechazado: "error",
  error: "error",
  impreso: "success",
};

export default createVuetify({
  locale: { locale: "es", fallback: "es", messages: { es } },
  components,
  directives,
  theme: {
    defaultTheme: "verificentrosOaxaca",
    themes: {
      verificentrosOaxaca: {
        dark: false,
        colors: {
          primary: guinda[600],
          "primary-darken-1": guinda[700],
          secondary: guinda[400],
          "secondary-darken-1": guinda[500],
          success: "#16824B",
          "on-success": "#FFFFFF",
          warning: "#A66300",
          "on-warning": "#FFFFFF",
          error: "#C52B3A",
          "on-error": "#FFFFFF",
          info: "#2563EB",
          "on-info": "#FFFFFF",
          background: "#FFFFFF",
          surface: "#FFFFFF",
        },
        variables: {
          "success-bg": "#ECFDF3",
          "warning-bg": "#FFF8E6",
          "error-bg": "#FFF1F2",
          "info-bg": "#EFF6FF",
        },
      },
    },
  },
});
