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
    conexion: "en_linea",
    cargando: false,
    error: null,
  }),

  getters: {
    tieneEstacionConfigurada: (state) => state.estacion !== null,
    tieneSesionActiva: (state) => state.sesion !== null,
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
    },
  },
});
