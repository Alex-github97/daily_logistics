/**
 * El cliente (inquilino) al que pertenece la sesión.
 *
 * Se elige en la pantalla previa al login y se guarda aparte del token: hace
 * falta antes de autenticarse, para pedirle al servidor a qué empresa se está
 * entrando y pintar su portal.
 */
import axios from 'axios'

const API_URL = import.meta.env.VITE_API_URL || '/api/v1'
const CLAVE = 'cliente_activo'

export interface ClientePublico {
  codigo: string
  nombre: string
  logo_url?: string | null
  color?: string | null
}

export const clienteGuardado = (): ClientePublico | null => {
  try {
    const crudo = localStorage.getItem(CLAVE)
    return crudo ? (JSON.parse(crudo) as ClientePublico) : null
  } catch {
    // Un valor corrupto no debe dejar la aplicación sin arrancar: se descarta y
    // se vuelve a pedir el cliente.
    return null
  }
}

export const guardarCliente = (c: ClientePublico) =>
  localStorage.setItem(CLAVE, JSON.stringify(c))

export const olvidarCliente = () => localStorage.removeItem(CLAVE)

/** El código que viaja en la cabecera mientras no hay token. */
export const codigoCliente = (): string | null => clienteGuardado()?.codigo ?? null

/**
 * Resuelve un cliente por su código.
 *
 * Va sin el cliente de axios porque este paso ocurre antes de tener sesión, y
 * el interceptor de 401 mandaría a /login en un bucle.
 */
export const resolverCliente = (codigo: string) =>
  axios
    .get<ClientePublico>(`${API_URL}/auth/clientes/${encodeURIComponent(codigo.trim().toLowerCase())}`)
    .then(r => r.data)
