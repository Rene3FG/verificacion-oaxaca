import axios from 'axios';
import { useAuthStore } from '@/stores/authStore';

// Crear la instancia global de Axios
const apiClient = axios.create({
  // Utiliza la variable de entorno de Vite o por defecto '/api/v1' (gestionada por el proxy de Vite)
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: {
    'Content-Type': 'application/json',
    'Accept': 'application/json',
  },
  timeout: 15000, // Timeout de 15 segundos para consultas externas como SIOX
});

/**
 * Interceptor de Solicitud (Request)
 * Se ejecuta antes de que cada petición salga hacia el servidor FastAPI.
 */
apiClient.interceptors.request.use(
  (config) => {
    // Acceder al store de autenticación de Pinia
    const authStore = useAuthStore();

    // 1. Inyectar Token JWT de Sesión Operativa si existe
    if (authStore.token) {
      config.headers.Authorization = `Bearer ${authStore.token}`;
    }

    // 2. Inyectar la Estación Física activa (ej. 'CAPTURA-REFORMA-L1')
    // Requerido por el backend para validar la sesión física y línea autorizada
    const stationIdentifier =
      authStore.stationIdentifier || import.meta.env.VITE_DEVICE_IDENTIFIER;

    if (stationIdentifier) {
      config.headers['X-Station-Identifier'] = stationIdentifier;
    }

    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

/**
 * Interceptor de Respuesta (Response)
 * Se ejecuta al recibir cualquier respuesta del backend.
 */
apiClient.interceptors.response.use(
  (response) => {
    // Retornar la respuesta directamente si fue exitosa (2xx)
    return response;
  },
  (error) => {
    const authStore = useAuthStore();

    if (error.response) {
      const { status, data } = error.response;

      // 401 Unauthorized / 403 Forbidden: Token inválido, sesión expirada o estación no autorizada
      if (status === 401 || status === 403) {
        console.warn(`[API Auth Error ${status}]: ${data?.detail || 'Acceso no autorizado'}`);
        // Cerrar sesión local y redirigir al login
        authStore.logout();
      }
    } else if (error.request) {
      // Error de red o servidor backend apagado
      console.error('[API Network Error]: No se recibió respuesta del backend FastAPI.');
    }

    return Promise.reject(error);
  }
);

export default apiClient;