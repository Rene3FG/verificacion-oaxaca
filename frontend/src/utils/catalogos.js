// Catálogos de solo lectura (`/api/catalogos/*`): entidades y municipios de
// INEGI — el certificado convierte esos nombres a clave (Mpio. 67, Estado 20),
// así que conviene elegirlos de la lista — y las clasificaciones de
// carrocería de la Tabla 1 de potencia del dinamómetro. Se piden una sola vez
// por sesión del navegador y se comparten entre vistas.
import { reactive, ref } from "vue";

import { api } from "../api/client";

const entidades = ref([]);
const municipiosOaxaca = ref([]);
const carrocerias = ref([]);
let carga = null;

export function useCatalogos() {
  if (!carga) {
    carga = Promise.all([
      api.get("/catalogos/entidades"),
      api.get("/catalogos/municipios"),
      api.get("/catalogos/carrocerias"),
    ])
      .then(([e, m, c]) => {
        entidades.value = e.data.map((x) => x.nombre);
        municipiosOaxaca.value = m.data.map((x) => x.nombre);
        carrocerias.value = c.data.map((x) => ({ value: x.clave, title: x.nombre }));
      })
      .catch(() => {
        // Sin catálogo los campos siguen aceptando texto libre; se reintenta
        // en la siguiente vista que lo pida.
        carga = null;
      });
  }
  return { entidades, municipiosOaxaca, carrocerias };
}

// Vacío también cuenta como Oaxaca: el sistema opera ahí.
export function esOaxaca(estado) {
  const texto = (estado || "").trim().toUpperCase();
  return !texto || texto === "OAXACA" || texto === "20";
}

// Municipios sugeridos según el estado capturado (catálogo INEGI de las 32
// entidades). Oaxaca ya viene en la carga inicial; los demás se piden la
// primera vez que se eligen. Un estado que el backend no reconoce (422) queda
// sin sugerencias y no se vuelve a pedir: el campo sigue aceptando texto libre.
const municipiosPorEntidad = reactive({});

export function municipiosDe(estado) {
  if (esOaxaca(estado)) return municipiosOaxaca.value;
  const clave = estado.trim().toUpperCase();
  if (!(clave in municipiosPorEntidad)) {
    municipiosPorEntidad[clave] = [];
    api
      .get("/catalogos/municipios", { params: { entidad: estado.trim() } })
      .then(({ data }) => {
        municipiosPorEntidad[clave] = data.map((x) => x.nombre);
      })
      .catch(() => {});
  }
  return municipiosPorEntidad[clave];
}

// v-model.number deja "" en un campo numérico vacío; el backend espera null.
export function limpiarPayload(form) {
  return Object.fromEntries(
    Object.entries(form).map(([k, v]) => [k, v === "" ? null : v])
  );
}
