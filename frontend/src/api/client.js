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
