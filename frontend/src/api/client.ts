import { mensajeDeError } from '@/utils/errorApi'
import axios, { AxiosInstance, InternalAxiosRequestConfig } from 'axios'
import { codigoCliente } from './cliente'

const API_URL = import.meta.env.VITE_API_URL || '/api/v1'

export const apiClient: AxiosInstance = axios.create({
  baseURL: API_URL,
  timeout: 30000,
  // Sin `Content-Type` fijo. Poniendolo aqui, TODA peticion sale como JSON,
  // incluidas las que llevan un archivo: el navegador ya no puede escribir
  // `multipart/form-data` con su separador y el servidor no sabe leer el
  // cuerpo. Axios pone `application/json` solo cuando el cuerpo es un objeto,
  // que es lo que se quiere.
  headers: {},
})

apiClient.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  // El cliente viaja hasta que hay token: el login lo necesita para saber en
  // qué empresa buscar al usuario. Después manda el token, que lo lleva firmado.
  const cliente = codigoCliente()
  if (cliente) {
    config.headers['X-Cliente'] = cliente
  }
  return config
})

/**
 * Marca una petición como «un 401 acá no significa que la sesión murió».
 *
 * El interceptor de abajo saca al usuario al login ante cualquier 401, que es lo
 * correcto cuando el token caducó y lo desastroso cuando el 401 viene de una
 * comprobación de negocio: al escribir mal un PIN en la terminal de planta, el
 * operario no recibía un aviso, se le cerraba la sesión entera.
 *
 * Úsese así:  api.post(ruta, datos, { ...sinCerrarSesion })
 */
export const sinCerrarSesion = { headers: { 'X-Sesion-Propia': '1' } }

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    // Un error de validación de FastAPI trae `detail` como LISTA de objetos. Más
    // de veinte pantallas hacen `toast.error(e.response.data.detail ?? '…')`, y
    // React revienta al pintar un objeto: la pantalla entera se caía por un campo
    // vacío. Se convierte acá, una vez, en el texto legible; la lista original
    // queda en `detalle_campos` para los formularios que marcan campo por campo.
    const datos = error.response?.data
    if (datos && Array.isArray(datos.detail)) {
      datos.detalle_campos = datos.detail
      datos.detail = mensajeDeError(error)
    }
    const propia = error.config?.headers?.['X-Sesion-Propia'] === '1'
    if (error.response?.status === 401 && !propia) {
      // Limpiar todo el estado de auth (token suelto + estado Zustand persistido)
      localStorage.removeItem('access_token')
      localStorage.removeItem('auth-storage')
      // El cliente elegido se conserva: la sesión caducó, pero sigue siendo la
      // misma empresa y volver a escribir su código en cada expiración sobra.
      window.location.href = '/login'
    }
    return Promise.reject(error)
  }
)
