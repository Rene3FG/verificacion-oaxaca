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
    // Distingue QUÉ falló para que el login muestre una pantalla distinta
    // en cada caso (frames `Acceso / Error — …` del Figma):
    //   "estacion_no_configurada" — GET /estaciones/{dispositivo} (404 o sin respuesta)
    //   "sin_permiso"             — login con credenciales válidas pero 403 en la estación
    //   "credenciales"            — login con usuario/contraseña incorrectos (401)
    errorTipo: null,
    // Usuario tecleado en el intento denegado por 403, para mostrarlo en la
    // pantalla de acceso denegado (el backend no lo devuelve en el error).
    usuarioDenegado: null,
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
      this.errorTipo = null;
      try {
        const { data } = await api.get(`/estaciones/${DEVICE_IDENTIFIER}`);
        this.estacion = data;
      } catch (err) {
        this.errorTipo = "estacion_no_configurada";
        this.error =
          err.response?.status === 404
            ? "Esta computadora no está configurada como estación."
            : "No se pudo consultar la configuración de esta estación. Verifica la conexión con el servidor local.";
        throw err;
      } finally {
        this.cargando = false;
      }
    },

    async iniciarSesion(username, password) {
      this.cargando = true;
      this.error = null;
      this.errorTipo = null;
      try {
        const { data } = await api.post("/estaciones/login", {
          username,
          password,
          workstation_id: this.estacion.id,
        });
        this.sesion = data;
        // El backend no expone username en StationSessionRead (solo
        // user_id, ver schemas/estacion.py) — se guarda el que el propio
        // operador tecleó para iniciar sesión, no un dato inventado.
        this.usuario = username;
      } catch (err) {
        // 403 = autenticación válida pero sin autorización sobre esta
        // estación; NO es lo mismo que un 401 de contraseña equivocada.
        const status = err.response?.status;
        this.errorTipo = status === 403 ? "sin_permiso" : "credenciales";
        this.usuarioDenegado = status === 403 ? username : null;
        this.error =
          err.response?.data?.detail || "No tienes permiso para operar esta estación.";
        throw err;
      } finally {
        this.cargando = false;
      }
    },

    // Botón "Cambiar usuario" de la pantalla de acceso denegado: vuelve al
    // formulario sin recargar y conserva la estación ya detectada.
    limpiarError() {
      this.error = null;
      this.errorTipo = null;
      this.usuarioDenegado = null;
    },

    async cerrarSesion() {
      // El backend ahora exige sesión activa para este endpoint (hallazgo
      // de seguridad de la revisión del PR #1, 2026-09-22: antes cualquiera
      // podía cerrar la sesión de otro adivinando el UUID). Si la sesión ya
      // era inválida en el servidor (usuario desactivado, ya cerrada desde
      // otra pestaña), el POST puede responder 401/404 — igual se limpia el
      // estado local, que es lo que le importa al operador frente a la
      // pantalla.
      if (this.sesion) {
        try {
          await api.post(`/estaciones/logout/${this.sesion.id}`);
        } catch {
          // Sesión ya inválida del lado del servidor: no bloquear el logout local.
        }
      }
      this.descartarSesionLocal();
    },

    // Limpia la sesión sin hablar con el servidor (el interceptor de 401 de
    // api/client.js la usa cuando el servidor ya la dio por inválida). La
    // navegación al login la hace App.vue al ver tieneSesionActiva en false.
    descartarSesionLocal() {
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
