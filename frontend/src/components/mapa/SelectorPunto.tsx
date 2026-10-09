import { useEffect, useRef } from 'react'
import { Box } from '@mui/material'
import { cargarLeaflet, TESELAS, ATRIBUCION } from './leaflet'

export interface Punto { lat: number; lng: number }

const PIN = (color: string) => `
<svg width="30" height="40" viewBox="0 0 30 40" style="filter:drop-shadow(0 2px 3px rgba(15,23,42,.35))">
  <path d="M15 1C7.3 1 1 7.2 1 14.9 1 25.3 15 39 15 39s14-13.7 14-24.1C29 7.2 22.7 1 15 1Z" fill="${color}" stroke="#fff" stroke-width="2"/>
  <circle cx="15" cy="15" r="5.2" fill="#fff"/>
</svg>`

/**
 * Mapa para fijar un punto: clic en el mapa o arrastrar el pin. Se usa para
 * ubicar la bodega cuando la dirección no basta (parques industriales, vías
 * sin nomenclatura) y para corregir lo que propone el buscador.
 */
export function SelectorPunto({ punto, onCambio, altura = 230, color = '#16A34A' }: {
  punto: Punto | null; onCambio: (p: Punto) => void; altura?: number; color?: string
}) {
  const caja = useRef<HTMLDivElement>(null)
  const mapa = useRef<any>(null)
  const marca = useRef<any>(null)
  const avisar = useRef(onCambio)
  avisar.current = onCambio
  const redondo = (ll: { lat: number; lng: number }) => ({ lat: +ll.lat.toFixed(6), lng: +ll.lng.toFixed(6) })

  useEffect(() => {
    let cancelado = false
    cargarLeaflet().then(L => {
      if (cancelado || !caja.current) return
      if (!mapa.current) {
        mapa.current = L.map(caja.current, { scrollWheelZoom: true })
          .setView(punto ? [punto.lat, punto.lng] : [4.6, -74.08], punto ? 16 : 5)
        L.tileLayer(TESELAS, { attribution: ATRIBUCION, maxZoom: 19 }).addTo(mapa.current)
        mapa.current.on('click', (e: any) => avisar.current(redondo(e.latlng)))
        setTimeout(() => mapa.current?.invalidateSize(), 200)
      }
      const m = mapa.current
      if (!punto) return
      if (!marca.current) {
        marca.current = L.marker([punto.lat, punto.lng], {
          draggable: true,
          icon: L.divIcon({ html: PIN(color), className: 'pin-selector', iconSize: [30, 40], iconAnchor: [15, 39] }),
        }).addTo(m)
        marca.current.on('dragend', () => avisar.current(redondo(marca.current.getLatLng())))
        m.setView([punto.lat, punto.lng], Math.max(m.getZoom(), 16))
      } else {
        marca.current.setLatLng([punto.lat, punto.lng])
        if (!m.getBounds().pad(-0.1).contains([punto.lat, punto.lng])) m.setView([punto.lat, punto.lng], Math.max(m.getZoom(), 15))
      }
    })
    return () => { cancelado = true }
  }, [punto?.lat, punto?.lng, color])

  useEffect(() => () => { mapa.current?.remove(); mapa.current = null; marca.current = null }, [])

  return (
    <Box ref={caja} sx={{
      height: altura, width: '100%', borderRadius: 2, overflow: 'hidden', border: '1px solid', borderColor: 'divider', bgcolor: '#EEF2F6',
      cursor: 'crosshair', '& .leaflet-pane, & .leaflet-control': { zIndex: 1 }, '& .pin-selector': { background: 'none', border: 'none' },
    }} />
  )
}
