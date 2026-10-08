/**
 * Carga Leaflet una sola vez para toda la aplicación.
 *
 * POR QUÉ POR CDN Y NO COMO DEPENDENCIA
 * Leaflet pesa unos 150 KB entre script y estilos. Solo dos módulos usan mapa,
 * así que empaquetarlo con la aplicación se lo cobra a todos los que nunca abren
 * un mapa. Cargándolo aquí, quien no entra a esas pantallas no lo descarga.
 *
 * POR QUÉ UNA SOLA PROMESA
 * Si dos componentes piden el mapa a la vez —y en la pantalla de seguimiento eso
 * pasa: la lista y el detalle se montan juntos— se inyectarían dos etiquetas
 * `<script>` y Leaflet se cargaría dos veces, con el segundo pisando el estado
 * del primero. La promesa compartida hace que la segunda llamada espere a la
 * primera en vez de empezar de nuevo.
 */

let promesa: Promise<any> | null = null

const CSS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.css'
const JS = 'https://unpkg.com/leaflet@1.9.4/dist/leaflet.js'

export function cargarLeaflet(): Promise<any> {
  const w = window as any
  if (w.L) return Promise.resolve(w.L)
  if (promesa) return promesa

  promesa = new Promise((resolver, rechazar) => {
    if (!document.querySelector(`link[href="${CSS}"]`)) {
      const css = document.createElement('link')
      css.rel = 'stylesheet'
      css.href = CSS
      document.head.appendChild(css)
    }
    const script = document.createElement('script')
    script.src = JS
    script.async = true
    script.onload = () => resolver((window as any).L)
    script.onerror = () => {
      // Se limpia la promesa fallida para que un segundo intento —por ejemplo
      // cuando vuelve la conexión— pueda reintentar en vez de quedarse con el
      // error guardado para siempre.
      promesa = null
      rechazar(new Error('No se pudo cargar el mapa'))
    }
    document.head.appendChild(script)
  })
  return promesa
}

/** El fondo del mapa. OpenStreetMap no exige llave ni cuenta. */
export const TESELAS = 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png'
export const ATRIBUCION = '&copy; OpenStreetMap'
