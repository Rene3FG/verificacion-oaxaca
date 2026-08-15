import apiClient from './client';

/**
 * Crea un nuevo expediente de verificación con el estado inicial correspondiente (HU-019).
 * @param {Object} payload - Datos iniciales (placa, linea_id, origen_datos).
 */
export const crearExpediente = (payload) => {
  return apiClient.post('/expedientes', payload);
};

/**
 * Obtiene el detalle completo de un expediente por su ID.
 * @param {string|number} expedienteId - ID del expediente.
 */
export const obtenerExpediente = (expedienteId) => {
  return apiClient.get(`/expedientes/${expedienteId}`);
};

/**
 * Confirma manualmente la normalización de los datos importados de SIOX.
 * Cambia el estado del expediente a DATOS_CONFIRMADOS.
 * @param {string|number} expedienteId - ID del expediente.
 * @param {Object} datosVehiculo - Datos del vehículo confirmados.
 */
export const confirmarDatosExpediente = (expedienteId, datosVehiculo) => {
  return apiClient.patch(`/expedientes/${expedienteId}/confirmar-datos`, {
    vehiculo: datosVehiculo,
    confirmado_por_operador: true,
  });
};

/**
 * Actualiza o corrige los datos del vehículo (Captura manual o corrección con auditoría) (HU-015).
 * Registra en bitácora el valor anterior y el valor nuevo por cada campo.
 * @param {string|number} expedienteId - ID del expediente.
 * @param {Object} datosVehiculo - Datos editados del vehículo.
 */
export const actualizarDatosVehiculo = (expedienteId, datosVehiculo) => {
  return apiClient.patch(`/expedientes/${expedienteId}/vehiculo`, datosVehiculo);
};  