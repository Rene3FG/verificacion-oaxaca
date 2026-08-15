import apiClient from './client';

/**
 * Consulta la información de un vehículo en el sistema SIOX por su placa.
 * @param {string} placa - Placa del vehículo a consultar.
 */
export const consultarSioxByPlaca = (placa) => {
  return apiClient.get('/siox/consultar', {
    params: { placa: placa.toUpperCase().trim() }
  });
};

/**
 * Obtiene el historial completo de consultas SIOX realizadas para un expediente.
 * @param {string|number} expedienteId - ID del expediente de verificación.
 */
export const obtenerHistorialSiox = (expedienteId) => {
  return apiClient.get(`/siox/expedientes/${expedienteId}/historial`);
};

/**
 * Reejecuta la consulta a SIOX para un expediente existente (HU-014).
 * @param {string|number} expedienteId - ID del expediente.
 */
export const reintentarSiox = (expedienteId) => {
  return apiClient.post(`/siox/expedientes/${expedienteId}/reintentar`);
};