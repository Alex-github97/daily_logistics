import { apiClient } from './client'

export interface User {
  id: number
  nombre: string
  apellido: string
  email: string
  username: string
  rol: string
  cargo?: string
  activo: boolean
  permisos: Record<string, boolean>
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
  es_operador?: boolean
  /** Módulos contratados por la empresa; `['*']` son todos. */
  modulos?: string[]
  /** Usuario del portal de un depositante (cliente del 3PL). */
  portal?: { depositante_id: number; nombre: string } | null
}

export const authApi = {
  login: (username: string, password: string) =>
    apiClient.post<LoginResponse>('/auth/login', { username, password }).then(r => r.data),

  me: () => apiClient.get<User>('/auth/me').then(r => r.data),

  changePassword: (data: { password_actual: string; password_nuevo: string }) =>
    apiClient.post('/auth/change-password', data).then(r => r.data),
}
