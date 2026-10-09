import React, { useEffect, useRef } from 'react'
import { Box, Typography } from '@mui/material'
import { cargarLeaflet, TESELAS, ATRIBUCION } from './leaflet'

export interface PuntoMapa {
  lat: number
  lng: number
  etiqueta?: string
}

interface Props {
  /** Qué se dibuja en la posición actual. Un vehículo cuando se sigue un viaje. */
  marcaActual?: 'punto' | 'camion'
  /** Cuánto lleva recorrido, de 0 a 100. Se pinta sobre el mapa. */
  avancePct?: number
  origen?: PuntoMapa | null
  destino?: PuntoMapa | null
  /** El rastro recorrido, en orden. Se dibuja como línea continua. */
  recorrido?: PuntoMapa[]
  /** Dónde está ahora. Es el punto que se resalta. */
  actual?: PuntoMapa | null
  /** Entregas intermedias, en orden (las direcciones de compra). */
  paradas?: (PuntoMapa & { numero?: number; hecha?: boolean })[]
  altura?: number | string
  color?: string
}

/**
 * El mapa de un viaje: de dónde salió, por dónde va y a dónde llega.
 *
 * QUÉ DIBUJA Y QUÉ NO
 * La línea es el rastro de posiciones que reportó el vehículo, no la ruta
 * calculada por carretera. Son cosas distintas y conviene no confundirlas: unir
 * dos reportes de GPS con una recta no dice por dónde pasó el camión entre uno y
 * otro. Se dibuja lo que se sabe —los puntos reportados— y nada más; pintar una
 * ruta trazada sobre la malla vial sugeriría una precisión que este dato no
 * tiene.
 *
 * CUANDO NO HAY COORDENADAS
 * No se dibuja un mapa vacío del mundo: se dice que no hay posición. Un mapa
 * centrado en el océano es peor que ningún mapa, porque parece que el vehículo
 * está ahí.
 */
// El camión que marca dónde va el vehículo. Va como SVG en línea y no como
// imagen porque tiene que heredar el color del viaje y verse nítido en
// cualquier pantalla; una imagen de mapa de bits se ve borrosa al acercarse.
const CAMION = (color: string) => `
<div style="position:relative;width:42px;height:42px">
  <div style="position:absolute;inset:0;border-radius:50%;
              background:${color};opacity:.22;animation:latido 2s infinite"></div>
  <div style="position:absolute;inset:5px;border-radius:50%;background:${color};
              border:3px solid #fff;box-shadow:0 2px 8px rgba(15,23,42,.45);
              display:grid;place-items:center">
    <svg width="18" height="18" viewBox="0 0 24 24" fill="#fff">
      <path d="M3 6a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v2h2.6a1 1 0 0 1 .8.4l2.4 3.2
               a1 1 0 0 1 .2.6V16a1 1 0 0 1-1 1h-1.2a2.8 2.8 0 0 0-5.6 0H9.8
               a2.8 2.8 0 0 0-5.6 0H4a1 1 0 0 1-1-1V6Zm12 4v2.5h4.4L17.4 10H15Z"/>
      <circle cx="7" cy="17.5" r="1.8"/><circle cx="17" cy="17.5" r="1.8"/>
    </svg>
  </div>
</div>`

export function MapaSeguimiento({
  origen, destino, recorrido = [], actual, paradas = [],
  altura = 340, color = '#2563EB',
  marcaActual = 'punto', avancePct,
}: Props) {
  const contenedor = useRef<HTMLDivElement>(null)
  const mapa = useRef<any>(null)
  const capa = useRef<any>(null)
  const [error, setError] = React.useState(false)

  const puntos = [
    ...(origen ? [origen] : []),
    ...recorrido,
    ...(actual ? [actual] : []),
    ...paradas,
    ...(destino ? [destino] : []),
  ].filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lng))

  useEffect(() => {
    let cancelado = false
    if (!puntos.length) return

    cargarLeaflet().then((L) => {
      if (cancelado || !contenedor.current) return

      if (!mapa.current) {
        mapa.current = L.map(contenedor.current, {
          scrollWheelZoom: false,   // la rueda es para desplazar la página
          zoomControl: true,
        }).setView([4.6, -74.08], 5)
        L.tileLayer(TESELAS, { attribution: ATRIBUCION, maxZoom: 19 })
          .addTo(mapa.current)
      }
      const m = mapa.current
      if (capa.current) { m.removeLayer(capa.current); capa.current = null }

      const grupo = L.layerGroup()

      // La ruta prevista (bodega → entregas → destino), tenue y punteada: es el
      // orden de las paradas, no el camino por carretera.
      const prevista = [...(origen ? [origen] : []), ...paradas, ...(destino ? [destino] : [])]
        .filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lng)).map(p => [p.lat, p.lng])
      if (prevista.length > 1) {
        grupo.addLayer(L.polyline(prevista, { color: '#4F46E5', weight: 3, opacity: 0.55, dashArray: '7 7' }))
      }

      const trazo = [...(origen ? [origen] : []), ...recorrido,
                     ...(actual ? [actual] : [])]
        .filter(p => Number.isFinite(p.lat) && Number.isFinite(p.lng))
        .map(p => [p.lat, p.lng])
      if (trazo.length > 1) {
        grupo.addLayer(L.polyline(trazo, {
          color, weight: 4, opacity: 0.85,
        }))
      }
      // Lo que falta por recorrer va punteado: es una estimación, no un rastro.
      if (actual && destino) {
        grupo.addLayer(L.polyline([[actual.lat, actual.lng],
                                   [destino.lat, destino.lng]], {
          color, weight: 3, opacity: 0.35, dashArray: '6 8',
        }))
      }

      paradas.forEach((p, i) => {
        const fondo = p.hecha ? '#16A34A' : '#fff', tinta = p.hecha ? '#fff' : '#0F172A'
        grupo.addLayer(L.marker([p.lat, p.lng], {
          icon: L.divIcon({
            className: 'marca-vehiculo', iconSize: [24, 24], iconAnchor: [12, 12],
            html: `<div style="width:24px;height:24px;border-radius:50%;background:${fondo};color:${tinta};border:2px solid #F59E0B;
                    display:grid;place-items:center;font:700 11px Inter,Arial;box-shadow:0 1px 4px rgba(15,23,42,.35)">${p.numero ?? i + 1}</div>`,
          }),
        }).bindPopup(`Entrega ${p.numero ?? i + 1}: ${p.etiqueta ?? ''}`))
      })
      const pin = (p: PuntoMapa, fondo: string, letra: string, titulo: string) => {
        grupo.addLayer(L.marker([p.lat, p.lng], {
          zIndexOffset: 500,
          icon: L.divIcon({
            className: 'marca-vehiculo', iconSize: [30, 40], iconAnchor: [15, 39], tooltipAnchor: [0, -34],
            html: `<svg width="30" height="40" viewBox="0 0 30 40" style="filter:drop-shadow(0 2px 3px rgba(15,23,42,.35))">
              <path d="M15 1C7.3 1 1 7.2 1 14.9 1 25.3 15 39 15 39s14-13.7 14-24.1C29 7.2 22.7 1 15 1Z" fill="${fondo}" stroke="#fff" stroke-width="2"/>
              <text x="15" y="19.5" text-anchor="middle" font-family="Inter,Arial" font-weight="800" font-size="12" fill="#fff">${letra}</text></svg>`,
          }),
        }).bindTooltip(`${titulo}${p.etiqueta ? ` · ${(p.etiqueta.split(' · ').pop() ?? '').slice(0, 38)}` : ''}`, { permanent: true, direction: 'top', className: 'rotulo-mapa' })
          .bindPopup(`${titulo}: ${p.etiqueta ?? ''}`))
      }
      if (origen) pin(origen, '#16A34A', 'O', 'Origen')
      if (destino) pin(destino, '#DC2626', 'D', 'Destino')
      if (actual) {
        const marca = marcaActual === 'camion'
          ? L.marker([actual.lat, actual.lng], {
              icon: L.divIcon({
                html: CAMION(color), className: 'marca-vehiculo',
                iconSize: [42, 42], iconAnchor: [21, 21],
              }),
              // Por encima del trazo, o la línea le pasa por encima al camión.
              zIndexOffset: 1000,
            })
          : L.circleMarker([actual.lat, actual.lng], {
              radius: 10, color: '#fff', weight: 3,
              fillColor: color, fillOpacity: 1,
            })
        grupo.addLayer(marca.bindPopup(
          actual.etiqueta ?? 'Última posición reportada'))
      }

      grupo.addTo(m)
      capa.current = grupo
      try {
        m.fitBounds(puntos.map(p => [p.lat, p.lng]), { padding: [34, 34] })
      } catch { /* un solo punto: se queda con la vista por omisión */ }
      // El mapa se monta dentro de un panel que puede estar creciendo todavía;
      // sin esto queda con el tamaño que tenía el contenedor al inicio y las
      // teselas salen cortadas.
      setTimeout(() => m.invalidateSize(), 140)
    }).catch(() => { if (!cancelado) setError(true) })

    return () => { cancelado = true }
  }, [JSON.stringify(puntos), color, marcaActual])

  useEffect(() => () => {
    if (mapa.current) { mapa.current.remove(); mapa.current = null }
  }, [])

  if (!puntos.length || error) {
    return (
      <Box sx={{
        height: altura, borderRadius: '12px', display: 'grid',
        placeItems: 'center', bgcolor: '#0F172A', color: '#94A3B8',
        border: '1px solid rgba(148,163,184,.25)', px: 3, textAlign: 'center',
      }}>
        <Typography sx={{ fontSize: 13 }}>
          {error
            ? 'No se pudo cargar el mapa. Revise la conexión.'
            : 'Este viaje aún no tiene puntos en el mapa: el origen (la bodega) y el destino (la dirección de compra) se ubican solos en unos minutos.'}
        </Typography>
      </Box>
    )
  }

  return (
    <Box>
      <Box ref={contenedor} sx={{
        height: altura, width: '100%',
        borderRadius: avancePct == null ? '12px' : '12px 12px 0 0',
        overflow: 'hidden', border: '1px solid rgba(148,163,184,.25)',
        bgcolor: '#EEF2F6',
        // Leaflet pone sus controles en z-index 1000 y se montan encima de los
        // diálogos de MUI. Bajarlos dentro del contenedor lo evita.
        '& .leaflet-pane, & .leaflet-control': { zIndex: 1 },
        '& .marca-vehiculo': { background: 'none', border: 'none' },
        '& .rotulo-mapa': { fontSize: 11, fontWeight: 700, py: 0.25, px: 0.75, borderRadius: 1, boxShadow: '0 1px 3px rgba(15,23,42,.25)' },
        '@keyframes latido': {
          '0%':   { transform: 'scale(.85)', opacity: .35 },
          '70%':  { transform: 'scale(1.5)', opacity: 0 },
          '100%': { transform: 'scale(.85)', opacity: 0 },
        },
      }} />

      {avancePct != null && (
        // La barra va pegada al mapa y no suelta más abajo: el avance y la
        // posición son el mismo dato contado de dos formas, y separarlos obliga
        // a mirar en dos sitios para entender uno solo.
        <Box sx={{
          border: '1px solid rgba(148,163,184,.25)', borderTop: 'none',
          borderRadius: '0 0 12px 12px', px: 2, py: 1.5,
          bgcolor: 'rgba(255,255,255,.06)',
        }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: .75 }}>
            <Typography sx={{ fontSize: 12, color: '#94A3B8' }}>
              {origen?.etiqueta ?? 'Origen'}
            </Typography>
            <Typography sx={{ fontSize: 12.5, fontWeight: 800, color }}>
              {Math.round(avancePct)}% del trayecto
            </Typography>
            <Typography sx={{ fontSize: 12, color: '#94A3B8' }}>
              {destino?.etiqueta ?? 'Destino'}
            </Typography>
          </Box>
          <Box sx={{ position: 'relative', height: 8, borderRadius: 4,
                     bgcolor: 'rgba(148,163,184,.25)' }}>
            <Box sx={{
              height: '100%', borderRadius: 4, bgcolor: color,
              width: `${Math.max(0, Math.min(100, avancePct))}%`,
              transition: 'width .4s ease',
            }} />
          </Box>
        </Box>
      )}
    </Box>
  )
}
