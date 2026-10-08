/**
 * Botón «PDF» de los documentos del WMS (OC, recepción, orden, picking,
 * despacho, traslado). Abre el PDF en una pestaña nueva, desde donde se
 * imprime, se guarda o se envía; con `descargar` lo baja directamente.
 *
 * El PDF se pide con la sesión (el token va en la cabecera), por eso no es un
 * enlace simple: se descarga como blob y se abre su URL local.
 */
import { useState } from 'react'
import { Button, CircularProgress, IconButton, Tooltip } from '@mui/material'
import { PictureAsPdf } from '@mui/icons-material'
import toast from 'react-hot-toast'
import { apiClient } from '@/api/client'

export type DocumentoPDF = 'oc' | 'recepcion' | 'orden-salida' | 'picking' | 'despacho' | 'traslado'

export function BotonPDF({ tipo, id, etiqueta = 'PDF', icono = false, descargar = false }: {
  tipo: DocumentoPDF; id: number; etiqueta?: string; icono?: boolean; descargar?: boolean
}) {
  const [cargando, setCargando] = useState(false)
  const abrir = async (e?: React.MouseEvent) => {
    e?.stopPropagation()
    // La pestaña se abre ya (en el clic) para que el navegador no la bloquee.
    const ventana = descargar ? null : window.open('', '_blank')
    setCargando(true)
    try {
      const r = await apiClient.get(`/wms/documentos/${tipo}/${id}`, { responseType: 'blob', params: descargar ? { descargar: true } : {} })
      const url = URL.createObjectURL(new Blob([r.data], { type: 'application/pdf' }))
      if (ventana) {
        ventana.location.href = url
      } else {
        const nombre = /filename="([^"]+)"/.exec(r.headers['content-disposition'] ?? '')?.[1] ?? `${tipo}_${id}.pdf`
        const a = document.createElement('a')
        a.href = url; a.download = nombre; a.click()
      }
      setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch {
      ventana?.close()
      toast.error('No se pudo generar el PDF')
    } finally {
      setCargando(false)
    }
  }
  if (icono) {
    return (
      <Tooltip title={`${etiqueta}: abrir para imprimir o guardar`}>
        <span>
          <IconButton size="small" onClick={abrir} disabled={cargando} sx={{ color: '#DC2626' }}>
            {cargando ? <CircularProgress size={16} /> : <PictureAsPdf fontSize="small" />}
          </IconButton>
        </span>
      </Tooltip>
    )
  }
  return (
    <Button size="small" variant="outlined" onClick={abrir} disabled={cargando}
      startIcon={cargando ? <CircularProgress size={14} /> : <PictureAsPdf sx={{ color: '#DC2626' }} />}
      sx={{ textTransform: 'none', fontWeight: 700 }}>
      {etiqueta}
    </Button>
  )
}
