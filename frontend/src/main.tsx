import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'
import './i18n'
import {
  FalloDeLaAplicacion, marcarArranqueCorrecto, recargarSiEsVersionCaducada,
} from './components/FalloDeLaAplicacion'
import { AvisoDeVersion } from './components/AvisoDeVersion'

/**
 * La última red antes de que el cliente vea una pantalla rota.
 *
 * Antes de mostrar nada, intenta recuperarse: si el fallo es que se publicó una
 * versión nueva y el navegador quedó pidiendo un archivo con el nombre viejo,
 * recargar lo resuelve y no hay error que contar. Solo cuando eso no aplica se
 * pinta la pantalla de fallo, que es del producto y no una consola.
 */
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null }

  static getDerivedStateFromError(e: Error) {
    // Se intenta la recarga aquí, antes de pintar: si va a recargar, no tiene
    // sentido mostrarle al usuario un error del que se recupera solo.
    if (recargarSiEsVersionCaducada(e)) return { error: null }
    return { error: e }
  }

  render() {
    if (this.state.error) return <FalloDeLaAplicacion error={this.state.error} />
    return this.props.children
  }
}

// Los errores de una promesa sin capturar no llegan al límite de React. El caso
// que importa es el mismo: una pantalla que se carga sola y cuyo archivo ya no
// existe tras publicar.
window.addEventListener('unhandledrejection', (e) => {
  recargarSiEsVersionCaducada(e.reason)
})

// Si la aplicación llegó a montar, el problema —si lo hubo— ya pasó: se suelta
// el seguro para que una recarga futura vuelva a estar disponible.
marcarArranqueCorrecto()

ReactDOM.createRoot(document.getElementById('root')!).render(
  <ErrorBoundary>
    <App />
    <AvisoDeVersion />
  </ErrorBoundary>,
)
