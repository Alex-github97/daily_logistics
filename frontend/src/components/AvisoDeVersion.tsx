import React from 'react'

/**
 * Avisa cuando se publicó una versión nueva mientras la aplicación estaba
 * abierta.
 *
 * POR QUÉ HACE FALTA
 * Al publicar, los archivos de la aplicación cambian de nombre. Un navegador que
 * lleva horas abierto sigue con la lista vieja, y en cuanto entra a una pantalla
 * que aún no había cargado pide un archivo que ya no existe. El resultado es una
 * pantalla de error que no tiene nada que ver con lo que la persona hizo.
 *
 * Recargar solo, sin avisar, tampoco sirve: quien está a mitad de un formulario
 * pierde lo que escribió. Por eso esto **avisa y deja decidir**, y la recarga
 * automática queda solo para cuando el fallo ya ocurrió y no hay nada que
 * perder.
 *
 * Se pregunta cada pocos minutos y solo con la pestaña visible: preguntar en
 * segundo plano a cien navegadores abiertos es tráfico que no le sirve a nadie.
 */

const CADA = 5 * 60 * 1000

export function AvisoDeVersion() {
  const [hayOtra, setHayOtra] = React.useState(false)
  const versionInicial = React.useRef<string | null>(null)

  React.useEffect(() => {
    let vivo = true

    async function mirar() {
      if (document.hidden || hayOtra) return
      try {
        // Misma base que el cliente de la API: con una ruta relativa fija, en
        // desarrollo la pregunta pasaba por un proxy distinto y fallaba.
        const base = import.meta.env.VITE_API_URL || '/api/v1'
        const r = await fetch(`${base}/health`, { cache: 'no-store' })
        if (!r.ok) return
        const { version } = await r.json()
        if (!version || !vivo) return
        if (versionInicial.current === null) {
          versionInicial.current = version
        } else if (versionInicial.current !== version) {
          setHayOtra(true)
        }
      } catch {
        // Sin conexión no se avisa de nada: el aviso es sobre una versión
        // nueva, no sobre la red.
      }
    }

    mirar()
    const id = setInterval(mirar, CADA)
    document.addEventListener('visibilitychange', mirar)
    return () => {
      vivo = false
      clearInterval(id)
      document.removeEventListener('visibilitychange', mirar)
    }
  }, [hayOtra])

  if (!hayOtra) return null

  return (
    <div style={{
      position: 'fixed', left: 16, bottom: 16, zIndex: 2000,
      display: 'flex', alignItems: 'center', gap: 14,
      background: '#0F172A', color: '#fff', borderRadius: 12,
      padding: '13px 16px', maxWidth: 420,
      boxShadow: '0 10px 34px rgba(15,23,42,.34)',
      fontFamily: 'Inter, system-ui, -apple-system, sans-serif',
    }}>
      <div style={{ fontSize: 13.5, lineHeight: 1.45 }}>
        <b>Hay una versión nueva.</b>{' '}
        <span style={{ color: '#CBD5E1' }}>
          Actualice cuando termine lo que está haciendo.
        </span>
      </div>
      <button
        onClick={() => window.location.reload()}
        style={{
          background: '#2563EB', color: '#fff', border: 'none', borderRadius: 8,
          padding: '9px 15px', fontSize: 13.5, fontWeight: 700, cursor: 'pointer',
          whiteSpace: 'nowrap', fontFamily: 'inherit',
        }}
      >
        Actualizar
      </button>
      <button
        onClick={() => setHayOtra(false)}
        aria-label="Ahora no"
        style={{
          background: 'none', border: 'none', color: '#94A3B8', cursor: 'pointer',
          fontSize: 19, lineHeight: 1, padding: 2, fontFamily: 'inherit',
        }}
      >
        ×
      </button>
    </div>
  )
}
