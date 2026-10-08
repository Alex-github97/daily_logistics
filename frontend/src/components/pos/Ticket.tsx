/**
 * Ticket de venta: lo que se entrega al cliente. Lleva emisor, resolución DIAN,
 * número, detalle con IVA discriminado, medios de pago, cambio y el CUFE.
 * Se imprime en una ventana aparte con ancho de rollo (80 mm).
 */
import { Box, Typography, Divider } from '@mui/material'
import { pesos, type Venta } from '@/api/pos'
import { aFecha } from '@/utils/fechas'

export function Ticket({ venta: v }: { venta: Venta }) {
  return (
    <Box sx={{ fontFamily: 'ui-monospace, monospace', fontSize: 12 }}>
      <Typography sx={{ fontWeight: 800, textAlign: 'center', fontFamily: 'inherit' }}>{v.emisor?.razon_social}</Typography>
      <Typography sx={{ textAlign: 'center', fontSize: 11, fontFamily: 'inherit' }}>NIT {v.emisor?.nit}{v.emisor?.direccion ? ` · ${v.emisor.direccion}` : ''}</Typography>
      {v.resolucion && <Typography sx={{ textAlign: 'center', fontSize: 10, color: 'text.secondary', fontFamily: 'inherit' }}>{v.resolucion}</Typography>}
      <Divider sx={{ my: 1 }} />
      <Typography sx={{ fontFamily: 'inherit', fontSize: 12 }}><b>Factura {v.numero}</b> · {aFecha(v.fecha).toLocaleString('es-CO')}</Typography>
      <Typography sx={{ fontFamily: 'inherit', fontSize: 11 }}>Cliente: {v.cliente_nombre}{v.cliente_documento ? ` · ${v.cliente_documento}` : ''}</Typography>
      <Typography sx={{ fontFamily: 'inherit', fontSize: 11 }}>Caja {v.caja_nombre} · {v.cajero}</Typography>
      <Divider sx={{ my: 1 }} />
      {(v.lineas ?? []).map(l => (
        <Box key={l.id} sx={{ mb: 0.5 }}>
          <div>{l.descripcion}</div>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <span>{l.cantidad} × {pesos(l.precio_unitario)}{l.descuento_pct ? ` -${l.descuento_pct}%` : ''} (IVA {l.tarifa_iva}%)</span>
            <span>{pesos(l.total)}</span>
          </Box>
        </Box>
      ))}
      <Divider sx={{ my: 1 }} />
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}><span>Base</span><span>{pesos(v.subtotal)}</span></Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between' }}><span>IVA</span><span>{pesos(v.impuestos)}</span></Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', fontWeight: 800, fontSize: 14 }}><span>TOTAL</span><span>{pesos(v.total)}</span></Box>
      {(v.pagos ?? []).map(p => (
        <Box key={p.medio} sx={{ display: 'flex', justifyContent: 'space-between' }}><span>{p.nombre}{p.referencia ? ` (${p.referencia})` : ''}</span><span>{pesos(p.monto)}</span></Box>
      ))}
      {v.recibido != null && <Box sx={{ display: 'flex', justifyContent: 'space-between' }}><span>Recibido</span><span>{pesos(v.recibido)}</span></Box>}
      {v.cambio > 0 && <Box sx={{ display: 'flex', justifyContent: 'space-between', fontWeight: 700 }}><span>Cambio</span><span>{pesos(v.cambio)}</span></Box>}
      <Divider sx={{ my: 1 }} />
      <Typography sx={{ fontFamily: 'inherit', fontSize: 9, wordBreak: 'break-all', color: 'text.secondary' }}>CUFE: {v.cufe}</Typography>
      <Typography sx={{ fontFamily: 'inherit', fontSize: 10, textAlign: 'center', mt: 1 }}>Gracias por su compra</Typography>
    </Box>
  )
}

const esc = (x: unknown) => String(x ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]!))

export function imprimirTicket(v: Venta) {
  const filas = (v.lineas ?? []).map(l => `<div>${esc(l.descripcion)}</div><div class="f"><span>${l.cantidad} x ${pesos(l.precio_unitario)}</span><span>${pesos(l.total)}</span></div>`).join('')
  const pagos = (v.pagos ?? []).map(p => `<div class="f"><span>${esc(p.nombre)}</span><span>${pesos(p.monto)}</span></div>`).join('')
  const w = window.open('', '_blank', 'width=360,height=640')
  if (!w) return
  w.document.write(`<html><head><title>${esc(v.numero)}</title><style>
    body{font-family:monospace;font-size:12px;width:72mm;margin:0 auto}.c{text-align:center}.f{display:flex;justify-content:space-between}
    hr{border:0;border-top:1px dashed #000}.t{font-weight:bold;font-size:14px}.p{font-size:9px;word-break:break-all}</style></head><body>
    <div class="c"><b>${esc(v.emisor?.razon_social)}</b><br/>NIT ${esc(v.emisor?.nit)}<br/><small>${esc(v.resolucion)}</small></div><hr/>
    <div>Factura <b>${esc(v.numero)}</b><br/>${aFecha(v.fecha).toLocaleString('es-CO')}<br/>Cliente: ${esc(v.cliente_nombre)} ${esc(v.cliente_documento)}</div><hr/>
    ${filas}<hr/><div class="f"><span>Base</span><span>${pesos(v.subtotal)}</span></div><div class="f"><span>IVA</span><span>${pesos(v.impuestos)}</span></div>
    <div class="f t"><span>TOTAL</span><span>${pesos(v.total)}</span></div>${pagos}
    ${v.cambio > 0 ? `<div class="f"><span>Cambio</span><span>${pesos(v.cambio)}</span></div>` : ''}<hr/>
    <div class="p">CUFE: ${esc(v.cufe)}</div><div class="c">Gracias por su compra</div></body></html>`)
  w.document.close(); w.focus(); w.print()
}
