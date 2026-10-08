/**
 * Página móvil sin autenticación — se accede desde un celular vía código QR.
 * Escanea códigos con la cámara del celular y los envía al backend.
 */
import React, { useState, useRef, useEffect, useCallback } from 'react'
import { BrowserMultiFormatReader } from '@zxing/browser'

const API_BASE = '/api/v1'
const PRIMARY = '#1A1A1A'
const DARK    = '#0D1117'

interface Item { code: string; ok: boolean }

export default function ScannerMovil() {
  const params    = new URLSearchParams(window.location.search)
  const sessionId = params.get('session') ?? ''

  const [items,        setItems]        = useState<Item[]>([])
  const [status,       setStatus]       = useState<'idle' | 'scanning' | 'error'>('idle')
  const [errorMsg,     setErrorMsg]     = useState('')
  const [flashGreen,   setFlashGreen]   = useState(false)
  const [flashRed,     setFlashRed]     = useState(false)

  const videoRef    = useRef<HTMLVideoElement>(null)
  const controlsRef = useRef<any>(null)
  const lastCodeRef = useRef('')

  const sendCode = useCallback(async (code: string) => {
    try {
      const res = await fetch(`${API_BASE}/scan-sessions/${sessionId}/code`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code }),
      })
      if (res.ok) {
        setItems(prev => [{ code, ok: true }, ...prev].slice(0, 50))
        setFlashGreen(true)
        setTimeout(() => setFlashGreen(false), 500)
      } else {
        setItems(prev => [{ code, ok: false }, ...prev].slice(0, 50))
        setFlashRed(true)
        setTimeout(() => setFlashRed(false), 500)
      }
    } catch {
      setFlashRed(true)
      setTimeout(() => setFlashRed(false), 500)
    }
  }, [sessionId])

  const startCamera = useCallback(async () => {
    if (!sessionId) { setErrorMsg('URL inválida — falta el parámetro de sesión'); setStatus('error'); return }
    setStatus('scanning'); setErrorMsg('')
    try {
      const reader   = new BrowserMultiFormatReader()
      const controls = await reader.decodeFromVideoDevice(
        undefined,
        videoRef.current!,
        (result: any) => {
          if (!result) return
          const val = result.getText?.()?.trim()
          if (!val || val === lastCodeRef.current) return
          lastCodeRef.current = val
          setTimeout(() => { lastCodeRef.current = '' }, 2400)
          sendCode(val)
        }
      )
      controlsRef.current = controls
    } catch (err: any) {
      setStatus('error')
      setErrorMsg(
        err?.name === 'NotAllowedError'
          ? 'Permiso de cámara denegado — revisa la configuración de tu navegador'
          : 'No se pudo iniciar la cámara del celular'
      )
    }
  }, [sessionId, sendCode])

  useEffect(() => {
    return () => {
      try { controlsRef.current?.stop() } catch { /**/ }
    }
  }, [])

  // ── Pantalla de inicio ────────────────────────────────────────────────────
  if (status === 'idle') {
    return (
      <div style={{
        minHeight: '100dvh', background: DARK,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '32px 24px', gap: 24, fontFamily: 'system-ui, sans-serif',
      }}>
        <div style={{ textAlign: 'center' }}>
          <div style={{ fontSize: 56, marginBottom: 8 }}>📦</div>
          <h1 style={{ color: '#F1F5F9', fontSize: 22, fontWeight: 800, margin: 0, letterSpacing: '-0.03em' }}>
            Escáner de Estibas
          </h1>
          <p style={{ color: '#64748B', fontSize: 14, margin: '8px 0 0' }}>
            Escanea códigos con la cámara de tu celular
          </p>
        </div>

        {!sessionId && (
          <div style={{ background: '#1E293B', border: '1px solid #EF4444', borderRadius: 12,
            padding: '16px 20px', color: '#FCA5A5', fontSize: 14, textAlign: 'center' }}>
            URL inválida — abre esta página desde el código QR
          </div>
        )}

        <button
          onClick={startCamera}
          disabled={!sessionId}
          style={{
            background: sessionId ? PRIMARY : '#334155',
            color: '#FFF', border: 'none', borderRadius: 16,
            padding: '18px 48px', fontSize: 18, fontWeight: 800, cursor: sessionId ? 'pointer' : 'not-allowed',
            width: '100%', maxWidth: 320, letterSpacing: '-0.01em',
            boxShadow: sessionId ? `0 0 32px rgba(79, 70, 229, 0.35)` : 'none',
          }}>
          Iniciar cámara
        </button>

        <p style={{ color: '#475569', fontSize: 12, textAlign: 'center', maxWidth: 280 }}>
          Al presionar, se pedirá acceso a la cámara del celular. Cada código que escanees se enviará automáticamente.
        </p>
      </div>
    )
  }

  // ── Error ─────────────────────────────────────────────────────────────────
  if (status === 'error') {
    return (
      <div style={{
        minHeight: '100dvh', background: DARK,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        padding: '32px 24px', gap: 20, fontFamily: 'system-ui, sans-serif',
      }}>
        <div style={{ fontSize: 48 }}>⚠️</div>
        <p style={{ color: '#FCA5A5', fontSize: 16, textAlign: 'center', maxWidth: 300 }}>{errorMsg}</p>
        <button onClick={() => setStatus('idle')}
          style={{ background: '#334155', color: '#F1F5F9', border: 'none',
            borderRadius: 12, padding: '14px 32px', fontSize: 15, fontWeight: 700, cursor: 'pointer' }}>
          Volver
        </button>
      </div>
    )
  }

  // ── Escáner activo ────────────────────────────────────────────────────────
  const okCount = items.filter(i => i.ok).length

  return (
    <div style={{
      minHeight: '100dvh', background: DARK,
      display: 'flex', flexDirection: 'column',
      fontFamily: 'system-ui, sans-serif', overflow: 'hidden',
    }}>
      {/* Flash de detección */}
      <div style={{
        position: 'fixed', inset: 0, pointerEvents: 'none', zIndex: 999,
        background: flashGreen ? 'rgba(79, 70, 229, 0.22)' : flashRed ? 'rgba(239,68,68,0.22)' : 'transparent',
        transition: 'background 0.08s ease',
      }} />

      {/* Header */}
      <div style={{
        background: '#111827', borderBottom: '1px solid #1E293B',
        padding: '12px 16px', display: 'flex', alignItems: 'center',
        justifyContent: 'space-between', flexShrink: 0,
      }}>
        <div>
          <div style={{ color: '#F1F5F9', fontWeight: 800, fontSize: 16 }}>Escáner activo</div>
          <div style={{ color: PRIMARY, fontSize: 12, fontWeight: 600 }}>
            {okCount} código{okCount !== 1 ? 's' : ''} enviado{okCount !== 1 ? 's' : ''}
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <div style={{
            width: 8, height: 8, borderRadius: '50%', background: '#EF4444',
            animation: 'blink 1.2s ease-in-out infinite',
          }} />
          <span style={{ color: '#94A3B8', fontSize: 12, fontWeight: 600 }}>EN VIVO</span>
        </div>
      </div>

      {/* Video */}
      <div style={{ position: 'relative', background: '#000', flexShrink: 0 }}>
        <video ref={videoRef} playsInline muted autoPlay
          style={{ width: '100%', maxHeight: '55dvh', objectFit: 'cover', display: 'block' }} />

        {/* Guía de encuadre */}
        <div style={{
          position: 'absolute', inset: 0, display: 'flex',
          alignItems: 'center', justifyContent: 'center', pointerEvents: 'none',
        }}>
          <div style={{
            width: '65%', maxWidth: 260, aspectRatio: '4/3',
            border: `2px solid ${flashGreen ? PRIMARY : 'rgba(255,255,255,0.45)'}`,
            borderRadius: 8, position: 'relative',
            boxShadow: flashGreen ? `0 0 32px rgba(79, 70, 229, 0.6)` : 'none',
            transition: 'border-color 0.1s, box-shadow 0.1s',
          }}>
            {/* Animación línea de escaneo */}
            <div style={{
              position: 'absolute', left: 8, right: 8, height: 2,
              background: `linear-gradient(90deg, transparent, ${PRIMARY}, transparent)`,
              animation: 'scanline 1.6s ease-in-out infinite',
            }} />
            {/* Esquinas */}
            {[
              { top:-2,left:-2,borderTop:`3px solid ${PRIMARY}`,borderLeft:`3px solid ${PRIMARY}`,borderRadius:'4px 0 0 0' },
              { top:-2,right:-2,borderTop:`3px solid ${PRIMARY}`,borderRight:`3px solid ${PRIMARY}`,borderRadius:'0 4px 0 0' },
              { bottom:-2,left:-2,borderBottom:`3px solid ${PRIMARY}`,borderLeft:`3px solid ${PRIMARY}`,borderRadius:'0 0 0 4px' },
              { bottom:-2,right:-2,borderBottom:`3px solid ${PRIMARY}`,borderRight:`3px solid ${PRIMARY}`,borderRadius:'0 0 4px 0' },
            ].map((s, i) => (
              <div key={i} style={{ position:'absolute', width:22, height:22, ...s }} />
            ))}
          </div>
          <div style={{
            position: 'absolute', bottom: 10, left: 0, right: 0,
            textAlign: 'center', color: 'rgba(255,255,255,0.6)',
            fontSize: 12, textShadow: '0 1px 3px rgba(0,0,0,0.8)',
          }}>
            Centra el código en el recuadro
          </div>
        </div>
      </div>

      {/* Lista de escaneados */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {items.length === 0 ? (
          <div style={{ padding: '32px 20px', textAlign: 'center', color: '#475569' }}>
            <div style={{ fontSize: 36, marginBottom: 8 }}>🎯</div>
            <div style={{ fontSize: 14 }}>Apunta la cámara a un código para comenzar</div>
          </div>
        ) : (
          items.map((item, i) => (
            <div key={i} style={{
              padding: '10px 16px',
              borderBottom: '1px solid #1E293B',
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <div style={{
                width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                background: item.ok ? 'rgba(79, 70, 229, 0.15)' : 'rgba(239,68,68,0.15)',
                border: `1.5px solid ${item.ok ? PRIMARY : '#EF4444'}`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 13,
              }}>
                {item.ok ? '✓' : '✗'}
              </div>
              <span style={{
                color: item.ok ? '#E2E8F0' : '#94A3B8',
                fontFamily: 'monospace', fontSize: 14, fontWeight: 700,
                flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {item.code}
              </span>
              {i === 0 && item.ok && (
                <span style={{ color: PRIMARY, fontSize: 11, fontWeight: 700 }}>ENVIADO</span>
              )}
            </div>
          ))
        )}
      </div>

      {/* CSS keyframes */}
      <style>{`
        @keyframes blink { 0%,100% { opacity:1 } 50% { opacity:0.15 } }
        @keyframes scanline {
          0%   { top: 10%; opacity: 0 }
          10%  { opacity: 1 }
          90%  { opacity: 1 }
          100% { top: 90%; opacity: 0 }
        }
      `}</style>
    </div>
  )
}
