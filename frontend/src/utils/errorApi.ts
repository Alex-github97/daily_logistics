/**
 * Traduce el error de una llamada a la API en algo que el usuario pueda leer y,
 * sobre todo, accionar.
 *
 * Antes cada pantalla hacía `e?.response?.data?.detail ?? 'No se pudo guardar'`,
 * y el mensaje genérico salía justo cuando más se necesitaba el detalle: en los
 * errores 500 y en los de validación, donde `detail` no es un texto.
 */

/** Un error de validación de FastAPI: detail es una lista de fallas por campo. */
interface FallaValidacion {
  loc?: (string | number)[]
  msg?: string
}

const nombreCampo = (loc?: (string | number)[]): string => {
  if (!loc || loc.length === 0) return ''
  // El primer nivel es "body" o "query"; lo que importa es lo que sigue.
  const partes = loc.filter(p => p !== 'body' && p !== 'query' && p !== 'path')
  return partes.join(' → ')
}

export function mensajeDeError(e: any, respaldo = 'No se pudo completar la operación'): string {
  const status = e?.response?.status
  const detail = e?.response?.data?.detail

  // Caso normal: el backend explica qué pasó.
  if (typeof detail === 'string' && detail.trim()) return detail

  // Validación de FastAPI: se arma "campo: mensaje" por cada falla.
  if (Array.isArray(detail) && detail.length > 0) {
    return detail
      .map((f: FallaValidacion) => {
        const campo = nombreCampo(f.loc)
        return campo ? `${campo}: ${f.msg ?? 'dato inválido'}` : (f.msg ?? 'dato inválido')
      })
      .join(' · ')
  }

  // Sin respuesta: el servidor no contestó.
  if (e?.request && !e?.response) {
    return 'No hubo respuesta del servidor. Revise su conexión e intente de nuevo.'
  }

  // Con estado pero sin detalle: al menos se dice qué tipo de problema es, para
  // que quien reporte sepa si es suyo o del servidor.
  if (status === 500) {
    return 'Error interno del servidor al procesar la solicitud. '
      + 'Quedó registrado en el log; repórtelo si se repite.'
  }
  if (status === 401 || status === 403) return 'No tiene permisos para esta operación.'
  if (status === 404) return 'El registro ya no existe. Actualice la pantalla.'
  if (status === 409) return 'La operación choca con el estado actual del registro.'
  if (status) return `${respaldo} (HTTP ${status})`

  return e?.message || respaldo
}
