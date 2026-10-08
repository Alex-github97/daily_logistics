import React from 'react'

/**
 * Lo que ve una persona cuando algo se rompe.
 *
 * QUÉ ESTABA MAL ANTES
 * Una consola negra con la pila de llamadas en rojo. Eso es una pantalla de
 * quien programa, no de quien trabaja: al cliente no le dice qué hacer, le dice
 * que el producto está roto, y encima le enseña nombres de archivos internos.
 *
 * QUÉ HACE ESTA
 * Tres cosas, en este orden de importancia:
 *
 *   1. Se recupera sola cuando puede. La causa más común en producción no es un
 *      error de programación: es que se publicó una versión nueva mientras la
 *      persona tenía la aplicación abierta, y el navegador pide un archivo que
 *      ya cambió de nombre. Eso no hay que mostrarlo: hay que recargar. Con un
 *      seguro para no entrar en un ciclo de recargas si el fallo es otro.
 *
 *   2. Cuando no puede, ofrece salidas. Reintentar, volver, ir al inicio. Una
 *      pantalla de error sin un botón deja a la persona con una sola opción:
 *      cerrar y llamar por teléfono.
 *
 *   3. Deja constancia. El fallo se reporta solo, con la ruta, el navegador y la
 *      pila. Sin eso, uno se entera de los errores cuando un cliente se queja, y
 *      solo de los que se molestan en quejarse.
 *
 * El detalle técnico no desaparece: queda plegado, con un botón para copiarlo.
 * Es lo que hace falta para atender el caso, y no lo primero que se ve.
 */

const CLAVE_RECARGA = 'tw_recarga_por_version'

/** Los fallos que se arreglan solos recargando. */
export function esVersionCaducada(e: unknown): boolean {
  const texto = String((e as Error)?.message ?? e ?? '')
  return (
    /Failed to fetch dynamically imported module/i.test(texto) ||
    /error loading dynamically imported module/i.test(texto) ||
    /Importing a module script failed/i.test(texto) ||
    /ChunkLoadError/i.test(texto) ||
    /Loading chunk \d+ failed/i.test(texto)
  )
}

/**
 * Recarga una sola vez ante un archivo caducado.
 *
 * El seguro importa: si el archivo de verdad no existe —un despliegue a medias,
 * por ejemplo— recargar en bucle deja el navegador girando para siempre y sin
 * decir nada. Una vez, y si vuelve a fallar, se muestra la pantalla.
 */
export function recargarSiEsVersionCaducada(e: unknown): boolean {
  if (!esVersionCaducada(e)) return false
  try {
    if (sessionStorage.getItem(CLAVE_RECARGA)) return false
    sessionStorage.setItem(CLAVE_RECARGA, '1')
  } catch {
    return false   // sin almacenamiento no hay seguro, y sin seguro no se recarga
  }
  window.location.reload()
  return true
}

/** Se limpia cuando la aplicación arranca bien: el problema ya pasó. */
export function marcarArranqueCorrecto(): void {
  try { sessionStorage.removeItem(CLAVE_RECARGA) } catch { /* da igual */ }
}

/** Deja constancia del fallo en el servidor. Nunca estorba: si falla, calla. */
export async function reportarFallo(e: Error, referencia: string): Promise<void> {
  try {
    await fetch('/api/v1/plataforma/fallo-interfaz', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(localStorage.getItem('access_token')
          ? { Authorization: `Bearer ${localStorage.getItem('access_token')}` }
          : {}),
      },
      body: JSON.stringify({
        referencia,
        mensaje: String(e?.message ?? e).slice(0, 500),
        pila: String(e?.stack ?? '').slice(0, 4000),
        ruta: window.location.pathname + window.location.search,
        navegador: navigator.userAgent.slice(0, 300),
        cliente: localStorage.getItem('cliente_activo'),
      }),
      // Que el reporte no bloquee el pintado de la pantalla.
      keepalive: true,
    })
  } catch { /* si no se puede reportar, la persona igual ve su pantalla */ }
}

/** Un código corto que la persona pueda dictar por teléfono. */
function nuevaReferencia(): string {
  const letras = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'   // sin I, O, 0, 1
  let r = ''
  for (let i = 0; i < 6; i++) {
    r += letras[Math.floor(Math.random() * letras.length)]
  }
  return r
}

export function FalloDeLaAplicacion({ error }: { error: Error }) {
  const [verDetalle, setVerDetalle] = React.useState(false)
  const [copiado, setCopiado] = React.useState(false)
  const referencia = React.useMemo(nuevaReferencia, [])

  React.useEffect(() => { reportarFallo(error, referencia) }, [error, referencia])

  const detalle = [
    `Referencia: ${referencia}`,
    `Ruta: ${window.location.pathname}`,
    `Mensaje: ${error?.message}`,
    '',
    error?.stack ?? '',
  ].join('\n')

  const copiar = () => {
    navigator.clipboard?.writeText(detalle)
      .then(() => { setCopiado(true); setTimeout(() => setCopiado(false), 2200) })
      .catch(() => { /* sin portapapeles, el texto está a la vista igual */ })
  }

  const boton: React.CSSProperties = {
    padding: '11px 20px', borderRadius: 10, fontSize: 14.5, fontWeight: 600,
    cursor: 'pointer', border: '1px solid #D5DAE3', background: '#fff',
    color: '#334155', fontFamily: 'inherit',
  }
  const principal: React.CSSProperties = {
    ...boton, background: '#2563EB', color: '#fff', border: '1px solid #2563EB',
  }

  return (
    <div style={{
      minHeight: '100vh', display: 'grid', placeItems: 'center',
      background: '#F5F7FA', padding: 24,
      fontFamily: 'Inter, system-ui, -apple-system, "Segoe UI", sans-serif',
      color: '#0F172A',
    }}>
      <div style={{ maxWidth: 560, width: '100%', textAlign: 'center' }}>
        <div style={{
          fontSize: 13, letterSpacing: 3, fontWeight: 800, color: '#94A3B8',
          marginBottom: 28,
        }}>
          TITTANWARE
        </div>

        <div style={{
          width: 62, height: 62, borderRadius: '50%', margin: '0 auto 20px',
          background: '#FEF3C7', display: 'grid', placeItems: 'center',
        }}>
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none"
               stroke="#D97706" strokeWidth="2" strokeLinecap="round">
            <path d="M12 9v4" /><path d="M12 17h.01" />
            <path d="M10.3 3.6 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.6a2 2 0 0 0-3.4 0z" />
          </svg>
        </div>

        <h1 style={{ fontSize: 23, fontWeight: 800, margin: '0 0 12px' }}>
          Esta pantalla no se pudo mostrar
        </h1>
        <p style={{ fontSize: 14, color: '#64748B', margin: '0 0 26px' }}>
          Ya quedó reportado con la referencia{' '}
          <b style={{ fontFamily: 'ui-monospace, monospace', color: '#0F172A' }}>
            {referencia}
          </b>. Si necesita escribirnos, menciónela.
        </p>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'center',
                      flexWrap: 'wrap', marginBottom: 22 }}>
          <button style={principal} onClick={() => window.location.reload()}>
            Volver a intentar
          </button>
          <button style={boton} onClick={() => window.history.back()}>
            Volver atrás
          </button>
          <button style={boton} onClick={() => { window.location.href = '/' }}>
            Ir al inicio
          </button>
        </div>

        <button
          onClick={() => setVerDetalle(v => !v)}
          style={{ ...boton, border: 'none', background: 'none', color: '#64748B',
                   fontSize: 13.5, padding: 6 }}
        >
          {verDetalle ? 'Ocultar el detalle técnico' : 'Ver el detalle técnico'}
        </button>

        {verDetalle && (
          <div style={{ marginTop: 12, textAlign: 'left' }}>
            <pre style={{
              background: '#0F172A', color: '#CBD5E1', borderRadius: 10,
              padding: 16, fontSize: 11.5, lineHeight: 1.55, overflow: 'auto',
              maxHeight: 260, margin: 0,
              fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
            }}>{detalle}</pre>
            <button style={{ ...boton, marginTop: 10, fontSize: 13 }} onClick={copiar}>
              {copiado ? 'Copiado' : 'Copiar para soporte'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}
