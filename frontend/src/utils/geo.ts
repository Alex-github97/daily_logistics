/**
 * Distancias sobre la superficie de la Tierra, y avance de un viaje.
 *
 * POR QUÉ EL AVANCE SE MIDE POR DISTANCIA Y NO POR TIEMPO
 * Son dos cosas distintas y mostrarlas como si fueran la misma produce
 * contradicciones que el usuario ve de inmediato: un viaje que lleva más horas
 * de las previstas da 100% por reloj, mientras el camión aparece a mitad de
 * camino en el mapa. La barra decía «completado» y el mapa decía «va por la
 * mitad», sobre la misma pantalla.
 *
 * El avance es cuánto se ha recorrido. El retraso es un dato aparte y se dice
 * aparte. Mezclarlos en una sola cifra es lo que rompía la lectura.
 */

const R = 6371   // radio de la Tierra en kilómetros

const rad = (g: number) => (g * Math.PI) / 180

/** Distancia en kilómetros entre dos coordenadas, sobre la esfera. */
export function distanciaKm(
  aLat: number, aLng: number, bLat: number, bLng: number,
): number {
  const dLat = rad(bLat - aLat)
  const dLng = rad(bLng - aLng)
  const h = Math.sin(dLat / 2) ** 2
    + Math.cos(rad(aLat)) * Math.cos(rad(bLat)) * Math.sin(dLng / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

export interface Coordenada { lat: number; lng: number }

/**
 * Qué porcentaje del trayecto lleva recorrido, según la última posición.
 *
 * Se mide como la distancia recorrida sobre la distancia total en línea recta
 * entre origen y destino. Es una aproximación —el camión va por carretera, no en
 * línea recta— pero es **la misma aproximación que dibuja el mapa**, y esa
 * coherencia es lo que importa: si la barra y el mapa se calculan distinto, uno
 * de los dos siempre parecerá equivocado.
 *
 * Devuelve `null` cuando falta alguna coordenada. Un `0` en ese caso diría «no
 * ha avanzado», que es una afirmación; `null` dice «no se sabe», que es la
 * verdad.
 */
export function avanceSobreRuta(
  origen?: Coordenada | null,
  actual?: Coordenada | null,
  destino?: Coordenada | null,
): number | null {
  if (!origen || !actual || !destino) return null
  const total = distanciaKm(origen.lat, origen.lng, destino.lat, destino.lng)
  if (total < 0.05) return null            // origen y destino en el mismo punto
  const recorrido = distanciaKm(origen.lat, origen.lng, actual.lat, actual.lng)
  return Math.max(0, Math.min(100, (recorrido / total) * 100))
}

/**
 * Cuánto lleva de retraso sobre la hora prevista, en minutos.
 *
 * Positivo significa retraso. Va aparte del avance a propósito: un viaje puede
 * ir al 40% del camino y con tres horas de retraso, y las dos cosas hay que
 * poder leerlas por separado para decidir qué hacer.
 */
export function retrasoMinutos(previstaISO?: string | null): number {
  if (!previstaISO) return 0
  const prevista = Date.parse(previstaISO)
  if (!Number.isFinite(prevista)) return 0
  return Math.round((Date.now() - prevista) / 60000)
}

/** «2 h 15 min», para decir un retraso sin obligar a dividir de cabeza. */
export function duracionLegible(minutos: number): string {
  const m = Math.abs(Math.round(minutos))
  if (m < 60) return `${m} min`
  const horas = Math.floor(m / 60)
  const resto = m % 60
  if (horas < 24) return resto ? `${horas} h ${resto} min` : `${horas} h`
  const dias = Math.floor(horas / 24)
  return `${dias} d ${horas % 24} h`
}
