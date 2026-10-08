/**
 * Códigos de barras (Code 128) y etiquetas imprimibles.
 *
 * Code 128 admite letras, números y guiones, así que el SKU de cada nivel
 * (BEB-000012, BEB-000012-CJ) se imprime tal cual. Un EAN-13 del fabricante
 * también se imprime en Code 128: cualquier lector lo lee igual.
 */
import { useEffect, useRef } from 'react'
import JsBarcode from 'jsbarcode'

const OPCIONES = { format: 'CODE128', displayValue: true, font: 'monospace', fontSize: 14, margin: 6 }

export function CodigoBarras({ valor, alto = 60, ancho = 1.8 }: { valor: string; alto?: number; ancho?: number }) {
  const ref = useRef<SVGSVGElement>(null)
  useEffect(() => {
    if (!ref.current || !valor) return
    try {
      JsBarcode(ref.current, valor, { ...OPCIONES, height: alto, width: ancho })
    } catch {
      // Un valor que Code 128 no admite: se deja el SVG vacío en vez de romper la pantalla.
    }
  }, [valor, alto, ancho])
  return <svg ref={ref} style={{ maxWidth: '100%' }} />
}

export interface Etiqueta {
  nombre: string
  sku: string
  nivel: string          // "Unidad", "Caja", …
  contiene?: string | null
  codigo: string
}

function svgDe(codigo: string): string {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg')
  try {
    JsBarcode(svg, codigo, { ...OPCIONES, height: 48, width: 1.6, fontSize: 12, margin: 0 })
  } catch {
    return `<div style="color:#b91c1c">Código no imprimible: ${codigo}</div>`
  }
  return new XMLSerializer().serializeToString(svg)
}

const escapar = (t: string) => t.replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]!))

/**
 * Abre una ventana con las etiquetas listas para imprimir (una cuadrícula de
 * 60 × 40 mm, que funciona en hoja carta y en impresoras de etiquetas).
 */
export function imprimirEtiquetas(etiquetas: Etiqueta[], copias = 1) {
  const lista = etiquetas.flatMap(e => Array.from({ length: Math.max(1, copias) }, () => e))
  const ventana = window.open('', '_blank', 'width=900,height=700')
  if (!ventana) {
    alert('El navegador bloqueó la ventana de impresión. Permita las ventanas emergentes para este sitio.')
    return
  }
  const cuerpo = lista.map(e => `
    <div class="et">
      <div class="nom">${escapar(e.nombre)}</div>
      <div class="meta"><b>${escapar(e.nivel)}</b>${e.contiene ? ` · ${escapar(e.contiene)}` : ''}</div>
      <div class="cb">${svgDe(e.codigo)}</div>
      <div class="sku">SKU ${escapar(e.sku)}</div>
    </div>`).join('')
  ventana.document.write(`<!doctype html><html lang="es"><head><meta charset="utf-8"/>
    <title>Etiquetas · Daily Logistics</title>
    <style>
      @page { margin: 8mm; }
      * { box-sizing: border-box; }
      body { margin: 0; font-family: "Segoe UI", Arial, sans-serif; color: #0B1120; }
      .barra { padding: 10px 14px; background: #0B1120; color: #fff; display: flex; gap: 12px; align-items: center; }
      .barra button { background: #4F46E5; color: #fff; border: 0; border-radius: 8px; padding: 8px 16px; font-weight: 700; cursor: pointer; }
      .hoja { display: flex; flex-wrap: wrap; gap: 3mm; padding: 4mm; }
      .et { width: 60mm; height: 40mm; border: 1px dashed #94A3B8; border-radius: 2mm; padding: 2mm 3mm;
            display: flex; flex-direction: column; justify-content: space-between; page-break-inside: avoid; overflow: hidden; }
      .nom { font-weight: 700; font-size: 9pt; line-height: 1.15; max-height: 2.4em; overflow: hidden; }
      .meta { font-size: 7.5pt; color: #475569; }
      .cb { text-align: center; } .cb svg { max-width: 100%; height: 17mm; }
      .sku { font-size: 7pt; color: #475569; text-align: right; }
      @media print { .barra { display: none; } .et { border-color: #CBD5E1; } }
    </style></head><body>
    <div class="barra"><b>${lista.length} etiqueta(s)</b><button onclick="window.print()">Imprimir</button></div>
    <div class="hoja">${cuerpo}</div>
    <script>setTimeout(function(){ window.print() }, 350)</script>
    </body></html>`)
  ventana.document.close()
}
