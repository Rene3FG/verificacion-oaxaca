import "@mdi/font/css/materialdesignicons.css";
import "vuetify/styles";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";

// Escala de guinda institucional — extraída de Figma "01 — Foundations"
// (sección 13 del handoff, 2026-09-07). No inventar valores intermedios:
// si hace falta un paso que no está aquí, confirmar con el Figma real.
export const guinda = {
  50: "#FDF3F6",
  100: "#F9E0E8",
  200: "#F1BDCE",
  300: "#E58BA7",
  400: "#D2577E",
  500: "#B93661",
  600: "#9D2449",
  700: "#7F1D3B",
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
          warning: "#B45309",
          "on-warning": "#FFFFFF",
          error: guinda[700],
          "on-error": "#FFFFFF",
          info: "#1D4ED8",
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
