/**
 * Utilidades de exportación compartidas para todos los módulos.
 * PDF (jsPDF + autoTable) y Excel/CSV (SheetJS). Diseñadas para recibir
 * los datos que ya se muestran en pantalla y producir un archivo homogéneo.
 */
import jsPDF from 'jspdf'
import autoTable from 'jspdf-autotable'
import * as XLSX from 'xlsx'

// Fila: cualquier objeto. Se usa `any[]` en la API pública para aceptar
// arreglos con tipos concretos (interfaces sin index signature) sin castear.
export type Fila = Record<string, unknown>

/** Normaliza un valor de celda a texto legible. */
function celda(v: unknown): string {
  if (v === null || v === undefined) return ''
  if (typeof v === 'number') return v.toLocaleString('es-CO')
  if (v instanceof Date) return v.toLocaleDateString('es-CO')
  return String(v)
}

/** Deriva columnas [{key,header}] a partir de las llaves del primer objeto. */
function columnasDesde(filas: any[]): { key: string; header: string }[] {
  if (!filas.length) return []
  return Object.keys(filas[0]).map((k) => ({
    key: k,
    header: k.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
  }))
}

export interface OpcionesExport {
  /** Nombre del archivo sin extensión. */
  archivo: string
  /** Título que se imprime arriba del PDF. */
  titulo?: string
  /** Subtítulo opcional (p. ej. filtros aplicados o fecha). */
  subtitulo?: string
  /** Columnas explícitas; si se omiten se derivan de las llaves de las filas. */
  columnas?: { key: string; header: string }[]
  /** Filas como objetos {llave: valor}. Acepta arreglos con tipos concretos. */
  filas: any[]
  /** Color de acento del encabezado de tabla (hex). Por defecto azul corporativo. */
  color?: string
}

const HOY = () => new Date().toLocaleString('es-CO')

/** Exporta a PDF con tabla. Devuelve true si generó, false si no había datos. */
export function exportarPDF(opts: OpcionesExport): boolean {
  const cols = opts.columnas?.length ? opts.columnas : columnasDesde(opts.filas)
  const doc = new jsPDF({ orientation: cols.length > 6 ? 'landscape' : 'portrait', unit: 'pt' })
  const accent = hexToRgb(opts.color || '#1E40AF')

  const marginX = 40
  let y = 46
  if (opts.titulo) {
    doc.setFontSize(16)
    doc.setTextColor(30, 41, 59)
    doc.text(opts.titulo, marginX, y)
    y += 18
  }
  doc.setFontSize(9)
  doc.setTextColor(120, 120, 120)
  if (opts.subtitulo) { doc.text(opts.subtitulo, marginX, y); y += 12 }
  doc.text(`Generado: ${HOY()}`, marginX, y)
  y += 8

  autoTable(doc, {
    startY: y + 6,
    head: [cols.map((c) => c.header)],
    body: opts.filas.map((f) => cols.map((c) => celda(f[c.key]))),
    styles: { fontSize: 8, cellPadding: 4 },
    headStyles: { fillColor: accent, textColor: [255, 255, 255], fontStyle: 'bold' },
    alternateRowStyles: { fillColor: [245, 247, 250] },
    margin: { left: marginX, right: marginX },
  })

  doc.save(`${opts.archivo}.pdf`)
  return opts.filas.length > 0
}

/** Exporta a Excel (.xlsx). Devuelve true si generó, false si no había datos. */
export function exportarExcel(opts: OpcionesExport): boolean {
  const cols = opts.columnas?.length ? opts.columnas : columnasDesde(opts.filas)
  const aoa: (string | number)[][] = [
    cols.map((c) => c.header),
    ...opts.filas.map((f) => cols.map((c) => {
      const v = f[c.key]
      return typeof v === 'number' ? v : celda(v)
    })),
  ]
  const ws = XLSX.utils.aoa_to_sheet(aoa)
  // ancho de columnas aproximado
  ws['!cols'] = cols.map((c, i) => ({
    wch: Math.min(40, Math.max(c.header.length + 2, ...aoa.map((r) => celda(r[i]).length + 2))),
  }))
  const wb = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(wb, ws, (opts.titulo || 'Datos').slice(0, 31))
  XLSX.writeFile(wb, `${opts.archivo}.xlsx`)
  return opts.filas.length > 0
}

/** Exporta a CSV. */
export function exportarCSV(opts: OpcionesExport): boolean {
  const cols = opts.columnas?.length ? opts.columnas : columnasDesde(opts.filas)
  const ws = XLSX.utils.aoa_to_sheet([
    cols.map((c) => c.header),
    ...opts.filas.map((f) => cols.map((c) => celda(f[c.key]))),
  ])
  const csv = XLSX.utils.sheet_to_csv(ws)
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${opts.archivo}.csv`
  a.click()
  URL.revokeObjectURL(url)
  return opts.filas.length > 0
}

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16)
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255]
}
