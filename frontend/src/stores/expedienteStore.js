import { defineStore } from 'pinia';
import {
  consultarSioxByPlaca,
  obtenerHistorialSiox,
  reintentarSiox,
} from '@/api/sioxApi';
import {
  crearExpediente,
  obtenerExpediente,
  confirmarDatosExpediente,
  actualizarDatosVehiculo,
} from '@/api/expedientesApi';

export const useExpedienteStore = defineStore('expediente', {
  state: () => ({
    // Objeto central del expediente de verificación activo
    expedienteActual: null,

    // Datos del vehículo obtenidos desde SIOX
    sioxData: null,

    // Estado de la consulta SIOX: 'IDLE' | 'LOADING' | 'FOUND' | 'NOT_FOUND' | 'ERROR'
    sioxStatus: 'IDLE',

    // Historial de consultas SIOX registradas para este expediente
    sioxHistorial: [],

    // Mensajes de error u operativos
    errorMessage: '',

    // Banderas de control de interfaz
    datosConfirmadosManual: false,
    modoCapturaManual: false,
    loading: false,
  }),

  getters: {
    // Retorna true si SIOX entregó datos válidos
    tieneSioxValido: (state) => state.sioxStatus === 'FOUND' && state.sioxData !== null,

    // Retorna true si el expediente fue confirmado y puede pasar a Inspección Visual
    listoParaVisual: (state) =>
      state.expedienteActual !== null && state.datosConfirmadosManual,
  },

  actions: {
    /**
     * Paso 1: Consultar la placa en SIOX e iniciar el expediente (HU-010, HU-011, HU-019)
     * @param {string} placa - Placa capturada por el operador.
     */
    async buscarPlacaSiox(placa) {
      this.sioxStatus = 'LOADING';
      this.errorMessage = '';
      this.sioxData = null;
      this.datosConfirmadosManual = false;
      this.modoCapturaManual = false;

      try {
        // 1. Consultar el servicio SIOX
        const response = await consultarSioxByPlaca(placa);
        const result = response.data;

        if (result && result.encontrado) {
          this.sioxData = result.vehiculo;
          this.sioxStatus = 'FOUND';

          // 2. Iniciar o enlazar el expediente en el backend en estado CREADO
          const expResponse = await crearExpediente({
            placa: placa.toUpperCase().trim(),
            origen_datos: 'SIOX',
            vehiculo_siox: result.vehiculo,
          });
          this.expedienteActual = expResponse.data;
        } else {
          this.sioxStatus = 'NOT_FOUND';
          this.errorMessage =
            'No se encontraron registros de la placa en SIOX. Se habilita la captura manual.';
          this.modoCapturaManual = true;
        }
      } catch (error) {
        this.sioxStatus = 'ERROR';
        this.errorMessage =
          error.response?.data?.detail ||
          'Error al comunicar con el servicio SIOX. Intente de nuevo o inicie captura manual.';
        this.modoCapturaManual = true;
      }
    },

    /**
     * Paso 2: Confirmar manualmente la normalización de datos importados de SIOX (Regla de Negocio)
     */
    async confirmarNormalizacionSiox() {
      if (!this.expedienteActual || !this.sioxData) return;

      this.loading = true;
      this.errorMessage = '';

      try {
        const response = await confirmarDatosExpediente(
          this.expedienteActual.id,
          this.sioxData
        );
        this.expedienteActual = response.data;
        this.datosConfirmadosManual = true;
      } catch (error) {
        this.errorMessage =
          error.response?.data?.detail ||
          'Error al confirmar la normalización de datos SIOX.';
        throw error;
      } finally {
        this.loading = false;
      }
    },

    /**
     * Paso alternativo: Guardar/actualizar datos ingresados manualmente (HU-015, HU-016)
     * @param {Object} datosVehiculo - Datos completos del vehículo capturados en el formulario.
     */
    async guardarCapturaManual(datosVehiculo) {
      this.loading = true;
      this.errorMessage = '';

      try {
        // Si no existe expediente aún (ej. SIOX falló), crearlo primero en modo MANUAL
        if (!this.expedienteActual) {
          const expResponse = await crearExpediente({
            placa: datosVehiculo.placa.toUpperCase().trim(),
            origen_datos: 'MANUAL',
          });
          this.expedienteActual = expResponse.data;
        }

        // Actualizar datos del vehículo con registro de auditoría en backend
        const response = await actualizarDatosVehiculo(
          this.expedienteActual.id,
          datosVehiculo
        );

        this.expedienteActual = response.data;
        this.datosConfirmadosManual = true;
      } catch (error) {
        this.errorMessage =
          error.response?.data?.detail ||
          'Error al guardar los datos manuales del vehículo.';
        throw error;
      } finally {
        this.loading = false;
      }
    },

    /**
     * Reejecutar la consulta a SIOX para un expediente existente (HU-014)
     */
    async reintentarConsulta() {
      if (!this.expedienteActual) return;

      this.sioxStatus = 'LOADING';
      this.errorMessage = '';

      try {
        const response = await reintentarSiox(this.expedienteActual.id);
        if (response.data && response.data.encontrado) {
          this.sioxData = response.data.vehiculo;
          this.sioxStatus = 'FOUND';
        } else {
          this.sioxStatus = 'NOT_FOUND';
          this.errorMessage = 'Reintento completado: la placa no fue encontrada en SIOX.';
        }
        await this.cargarHistorial();
      } catch (error) {
        this.sioxStatus = 'ERROR';
        this.errorMessage =
          error.response?.data?.detail || 'Error al reintentar la consulta en SIOX.';
      }
    },

    /**
     * Cargar el historial de consultas SIOX asociadas al expediente (HU-013)
     */
    async cargarHistorial() {
      if (!this.expedienteActual) return;

      try {
        const response = await obtenerHistorialSiox(this.expedienteActual.id);
        this.sioxHistorial = response.data || [];
      } catch (error) {
        console.error('Error al cargar historial SIOX:', error);
      }
    },

    /**
     * Cargar un expediente existente por su ID
     * @param {string|number} expedienteId 
     */
    async cargarExpediente(expedienteId) {
      this.loading = true;
      try {
        const response = await obtenerExpediente(expedienteId);
        this.expedienteActual = response.data;
      } catch (error) {
        this.errorMessage = 'No se pudo cargar el expediente solicitado.';
      } finally {
        this.loading = false;
      }
    },

    /**
     * Limpiar el estado para iniciar la atención de un nuevo vehículo
     */
    limpiarEstado() {
      this.expedienteActual = null;
      this.sioxData = null;
      this.sioxStatus = 'IDLE';
      this.sioxHistorial = [];
      this.errorMessage = '';
      this.datosConfirmadosManual = false;
      this.modoCapturaManual = false;
      this.loading = false;
    },
  },
});