import { defineStore } from "pinia";
import { api } from "../api/client";

// El identificador de esta computadora como estación operativa. En
// producción vendría de configuración local de la máquina, no de env var
// de build; placeholder simple para desarrollo.
const DEVICE_IDENTIFIER =
  import.meta.env.VITE_DEVICE_IDENTIFIER || "CAPTURA-REFORMA-L1";

export const useSessionStore = defineStore("session", {
  state: () => ({
    estacion: null,
    sesion: null,
    usuario: null,
    // Reemplazado por datos reales de GET /api/sync/estado (ver
    // actualizarEstadoSync); antes era un valor fijo que nunca cambiaba.
    estadoSync: null,
    cargando: false,
    error: null,
  }),

  getters: {
    tieneEstacionConfigurada: (state) => state.estacion !== null,
    tieneSesionActiva: (state) => state.sesion !== null,
    puedeSupervisar: (state) => state.sesion?.can_supervise === true,

    // "en_linea" | "sincronizando" | "pendientes" | "desconocido" — antes
    // de la primera respuesta de /api/sync/estado no se sabe.
    conexion: (state) => {
      if (state.estadoSync === null) return "desconocido";
      if (state.estadoSync.sincronizando > 0) return "sincronizando";
      if (state.estadoSync.pendientes > 0) return "pendientes";
      return "en_linea";
    },
  },

  actions: {
    async detectarEstacion() {
      this.cargando = true;
      this.error = null;
      try {
        const { data } = await api.get(`/estaciones/${DEVICE_IDENTIFIER}`);
        this.estacion = data;
      } catch (err) {
        this.error = "Esta computadora no está configurada como estación.";
        throw err;
      } finally {
        this.cargando = false;
      }
    },

    async iniciarSesion(username, password) {
      this.cargando = true;
      this.error = null;
      try {
        const { data } = await api.post("/estaciones/login", {
          username,
          password,
          workstation_id: this.estacion.id,
        });
        this.sesion = data;
      } catch (err) {
        this.error =
          err.response?.data?.detail || "No tienes permiso para operar esta estación.";
        throw err;
      } finally {
        this.cargando = false;
      }
    },

    async cerrarSesion() {
      if (this.sesion) {
        await api.post(`/estaciones/logout/${this.sesion.id}`);
      }
      this.sesion = null;
      this.usuario = null;
      this.estadoSync = null;
    },

    async actualizarEstadoSync() {
      if (!this.tieneSesionActiva) return;
      try {
        const { data } = await api.get("/sync/estado");
        this.estadoSync = data;
      } catch {
        // Si el backend local no responde, no hay nada más específico que
        // "desconocido" que mostrar — no es un error del usuario.
        this.estadoSync = null;
      }
    },
  },
});
