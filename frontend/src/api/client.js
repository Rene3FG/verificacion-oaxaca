import axios from "axios";
import { useSessionStore } from "../stores/session";

export const api = axios.create({
  baseURL: "/api",
});

// El backend nunca acepta linea_id/usuario_id del cliente: los resuelve de
// la sesión vía X-Session-Id (app.api.deps.get_current_session).
api.interceptors.request.use((config) => {
  const session = useSessionStore();
  if (session.sesion?.id) {
    config.headers["X-Session-Id"] = session.sesion.id;
  }
  return config;
});

// Hallazgos QA-E2E-01/02 (auditoría de Sebastián, 2026-10-08):
// - 401 en cualquier ruta protegida = la sesión ya no vale en el servidor
//   (cerrada, expirada, usuario desactivado). Se limpia el estado local y
//   App.vue regresa al login; no se llama de nuevo a /logout.
// - FastAPI devuelve `detail` como arreglo en errores de validación (422).
//   Se convierte a texto aquí para que ninguna vista pinte JSON crudo en
//   su v-alert.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    const url = error.config?.url || "";
    if (status === 401 && !url.startsWith("/estaciones/login")) {
      useSessionStore().descartarSesionLocal();
    }
    const data = error.response?.data;
    if (data && Array.isArray(data.detail)) {
      data.detail = data.detail
        .map((d) => (typeof d === "string" ? d : d?.msg))
        .filter(Boolean)
        .map((msg) => msg.replace(/^Value error, /, ""))
        .join(". ") || "Datos inválidos.";
    }
    return Promise.reject(error);
  },
);
