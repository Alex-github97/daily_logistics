/**
 * Paginación y exportación para los reportes en tabla.
 *
 * - `usePaginacion` + `Paginacion`: páginas de 100 filas (se puede cambiar a
 *   50, 250 o 500) para no obligar a bajar hasta el final de una lista larga.
 *   Si los datos se paginan en el servidor, se usa solo `Paginacion`.
 * - `BotonExportar`: Excel, CSV y PDF del reporte COMPLETO (no solo la página
 *   visible). `obtenerFilas` puede devolver las filas que ya están en memoria o
 *   pedirlas al servidor con los mismos filtros.
 */
import React, { useEffect, useState } from 'react'
import { Button, CircularProgress, ListItemIcon, ListItemText, Menu, MenuItem, TablePagination } from '@mui/material'
import { FileDownload, GridOn, Description, PictureAsPdf } from '@mui/icons-material'
import toast from 'react-hot-toast'
import { exportarCSV, exportarExcel, exportarPDF } from '@/utils/exportar'
import { COLOR_MODULO } from '@/config/marca'

export const POR_PAGINA = 100
const OPCIONES = [50, 100, 250, 500]

export function usePaginacion<T>(filas: T[], inicial = POR_PAGINA) {
  const [pagina, setPagina] = useState(0)
  const [porPagina, setPorPagina] = useState(inicial)
  // Si cambian los filtros y la página ya no existe, se vuelve a la primera.
  useEffect(() => { if (pagina > 0 && pagina * porPagina >= filas.length) setPagina(0) }, [filas.length, porPagina])
  return {
    pagina, porPagina, setPagina, setPorPagina,
    filasPagina: filas.slice(pagina * porPagina, pagina * porPagina + porPagina),
  }
}

export function Paginacion({ total, pagina, porPagina, onPagina, onPorPagina }: {
  total: number; pagina: number; porPagina: number
  onPagina: (p: number) => void; onPorPagina: (n: number) => void
}) {
  return (
    <TablePagination
      component="div" count={total} page={total ? Math.min(pagina, Math.max(0, Math.ceil(total / porPagina) - 1)) : 0}
      rowsPerPage={porPagina} rowsPerPageOptions={OPCIONES}
      onPageChange={(_, p) => onPagina(p)}
      onRowsPerPageChange={e => { onPorPagina(Number(e.target.value)); onPagina(0) }}
      labelRowsPerPage="Filas por página"
      labelDisplayedRows={({ from, to, count }) => `${from.toLocaleString('es-CO')}–${to.toLocaleString('es-CO')} de ${count.toLocaleString('es-CO')}`}
      getItemAriaLabel={t => (t === 'next' ? 'Página siguiente' : t === 'previous' ? 'Página anterior' : t === 'first' ? 'Primera página' : 'Última página')}
      showFirstButton showLastButton
      sx={{ borderTop: '1px solid', borderColor: 'divider', '& .MuiTablePagination-toolbar': { minHeight: 48 } }}
    />
  )
}

export interface ColumnaExport<T> { titulo: string; valor: (r: T) => string | number | null | undefined }

export function BotonExportar<T>({ titulo, archivo, columnas, obtenerFilas, subtitulo, size = 'small' }: {
  titulo: string
  /** Nombre base del archivo (se le agrega la fecha). */
  archivo: string
  columnas: ColumnaExport<T>[]
  obtenerFilas: () => T[] | Promise<T[]>
  subtitulo?: string
  size?: 'small' | 'medium'
}) {
  const [ancla, setAncla] = useState<HTMLElement | null>(null)
  const [cargando, setCargando] = useState(false)

  const exportar = async (formato: 'xlsx' | 'csv' | 'pdf') => {
    setAncla(null)
    setCargando(true)
    try {
      const filas = await obtenerFilas()
      if (!filas.length) { toast.error('No hay filas para exportar con los filtros actuales'); return }
      if (formato === 'pdf' && filas.length > 5000 &&
          !window.confirm(`El PDF tendrá ${filas.length.toLocaleString('es-CO')} filas (muchas páginas). Para este volumen Excel o CSV son más prácticos. ¿Generar el PDF de todas formas?`)) return
      const cols = columnas.map((c, i) => ({ key: `c${i}`, header: c.titulo }))
      const datos = filas.map(r => Object.fromEntries(columnas.map((c, i) => [`c${i}`, c.valor(r) ?? ''])))
      const fecha = new Date().toISOString().slice(0, 10)
      const opts = { archivo: `${archivo}_${fecha}`, titulo, subtitulo, columnas: cols, filas: datos, color: COLOR_MODULO }
      if (formato === 'xlsx') exportarExcel(opts)
      else if (formato === 'csv') exportarCSV(opts)
      else exportarPDF(opts)
      toast.success(`${titulo}: ${filas.length.toLocaleString('es-CO')} filas exportadas`)
    } catch {
      toast.error('No se pudo exportar el reporte')
    } finally {
      setCargando(false)
    }
  }

  return (
    <>
      <Button size={size} variant="outlined" disabled={cargando} onClick={e => setAncla(e.currentTarget)}
        startIcon={cargando ? <CircularProgress size={14} /> : <FileDownload sx={{ fontSize: 18 }} />}
        sx={{ textTransform: 'none', borderRadius: 2, whiteSpace: 'nowrap' }}>
        {cargando ? 'Preparando…' : 'Exportar'}
      </Button>
      <Menu anchorEl={ancla} open={!!ancla} onClose={() => setAncla(null)}>
        <MenuItem onClick={() => exportar('xlsx')}><ListItemIcon><GridOn fontSize="small" sx={{ color: '#15803D' }} /></ListItemIcon><ListItemText>Excel (.xlsx)</ListItemText></MenuItem>
        <MenuItem onClick={() => exportar('csv')}><ListItemIcon><Description fontSize="small" sx={{ color: '#0369A1' }} /></ListItemIcon><ListItemText>CSV</ListItemText></MenuItem>
        <MenuItem onClick={() => exportar('pdf')}><ListItemIcon><PictureAsPdf fontSize="small" sx={{ color: '#DC2626' }} /></ListItemIcon><ListItemText>PDF</ListItemText></MenuItem>
      </Menu>
    </>
  )
}

/** Encabezado de un reporte: título a la izquierda, acciones (exportar…) a la derecha. */
export function EncabezadoReporte({ titulo, children }: { titulo: React.ReactNode; children?: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap', marginBottom: 12 }}>
      <div>{titulo}</div>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>{children}</div>
    </div>
  )
}
