import "@mdi/font/css/materialdesignicons.css";
import "vuetify/styles";
import { createVuetify } from "vuetify";
import * as components from "vuetify/components";
import * as directives from "vuetify/directives";

// Colores semánticos por estado, según guidelines de diseño del proyecto:
// pendiente gris, en proceso ámbar, aprobado verde, rechazado/error rojo.
export const estadoColors = {
  pendiente: "grey",
  consultado: "blue",
  proceso: "amber",
  aprobado: "green",
  rechazado: "red",
  error: "red",
  impreso: "green",
};

export default createVuetify({
  components,
  directives,
  theme: {
    defaultTheme: "light",
  },
});
