/**
 * Plantilla descargable y cargue masivo desde Excel, para cualquier catálogo.
 *
 * El archivo se lee acá, en el navegador, y al servidor van filas ya
 * estructuradas: así no hay que subir archivos ni manejar temporales, y el
 * servidor se dedica a validar, que es lo que solo él puede hacer.
 *
 * La plantilla lleva una fila de ejemplo y una hoja de instrucciones. Suena
 * excesivo hasta que alguien llena la columna equivocada con doscientas filas.
 */
import { useRef, useState } from 'react'
import {
  Box, Button, Dialog, DialogTitle, DialogContent, DialogActions,
  Stack, Alert, Table, TableBody, TableCell, TableHead, TableRow, Chip,
  LinearProgress, Tooltip,
} from '@mui/material'
import { CloudDownload, CloudUpload } from '@mui/icons-material'
import * as XLSX from 'xlsx'
import toast from 'react-hot-toast'
import { PALETA, ESTADO } from '@/config/marca'

export interface ColumnaPlantilla {
  clave: string
  titulo: string
  requerida?: boolean
  ayuda?: string
  ejemplo?: string
}

export interface ResultadoImportacion {
  creados: number
  omitidos: number
  total: number
  errores: { fila: number; motivo: string }[]
}

/** Quita acentos y espacios para poder comparar encabezados sin exigir exactitud. */
const normalizar = (s: string) =>
  String(s ?? '').trim().toLowerCase()
    // ̀–ͯ es el bloque de tildes y diéresis que deja `normalize`.
    .normalize('NFD').replace(/[̀-ͯ]/g, '')

export function descargarPlantilla(
  nombreArchivo: string, titulo: string, columnas: ColumnaPlantilla[],
) {
  const encabezados = columnas.map(c => c.titulo + (c.requerida ? ' *' : ''))
  const ejemplo = columnas.map(c => c.ejemplo ?? '')

  const hoja = XLSX.utils.aoa_to_sheet([encabezados, ejemplo])
  // Ancho suficiente para que los títulos no salgan cortados al abrir.
  hoja['!cols'] = columnas.map(c => ({ wch: Math.max(16, c.titulo.length + 6) }))

  const libro = XLSX.utils.book_new()
  XLSX.utils.book_append_sheet(libro, hoja, 'Datos')

  const instrucciones = [
    [titulo],
    [],
    ['Cómo llenar este archivo'],
    ['1. Escriba una fila por registro, debajo de los encabezados.'],
    ['2. Borre la fila de ejemplo antes de cargar el archivo.'],
    ['3. Las columnas marcadas con * son obligatorias.'],
    ['4. No cambie los encabezados ni el orden de las columnas.'],
    ['5. Lo que ya exista se omite: puede volver a cargar el archivo corregido.'],
    [],
    ['Columna', 'Obligatoria', 'Qué va aquí'],
    ...columnas.map(c => [c.titulo, c.requerida ? 'Sí' : 'No', c.ayuda ?? '']),
  ]
  const hojaAyuda = XLSX.utils.aoa_to_sheet(instrucciones)
  hojaAyuda['!cols'] = [{ wch: 26 }, { wch: 12 }, { wch: 70 }]
  XLSX.utils.book_append_sheet(libro, hojaAyuda, 'Instrucciones')

  XLSX.writeFile(libro, `${nombreArchivo}.xlsx`)
}

/** Lee el archivo y devuelve las filas con las claves que espera el servidor. */
async function leerArchivo(
  archivo: File, columnas: ColumnaPlantilla[],
): Promise<Record<string, unknown>[]> {
  const datos = await archivo.arrayBuffer()
  const libro = XLSX.read(datos, { type: 'array' })
  const hoja = libro.Sheets[libro.SheetNames[0]]
  if (!hoja) throw new Error('El archivo no tiene ninguna hoja con datos')

  const crudas = XLSX.utils.sheet_to_json<Record<string, unknown>>(hoja, { defval: '' })

  // El encabezado se compara sin acentos, sin mayúsculas y sin el asterisco de
  // obligatorio, porque nadie lo escribe exactamente igual.
  const porEncabezado = new Map<string, string>()
  for (const c of columnas) porEncabezado.set(normalizar(c.titulo), c.clave)

  const filas = crudas.map(cruda => {
    const fila: Record<string, unknown> = {}
    for (const [encabezado, valor] of Object.entries(cruda)) {
      const clave = porEncabezado.get(normalizar(encabezado).replace(/\s*\*$/, ''))
      if (clave) fila[clave] = valor
    }
    return fila
  })

  // Las filas totalmente vacías son las que Excel deja debajo de los datos.
  return filas.filter(f => Object.values(f).some(v => String(v ?? '').trim() !== ''))
}

export function CargueMasivo({
  titulo, nombreArchivo, columnas, color = PALETA.tinta, onImportar, onListo, compacto = false,
}: {
  titulo: string
  nombreArchivo: string
  columnas: ColumnaPlantilla[]
  color?: string
  /** Envía las filas al servidor y devuelve su informe. */
  onImportar: (filas: Record<string, unknown>[]) => Promise<ResultadoImportacion>
  /** Se llama cuando algo se creó, para refrescar la lista de atrás. */
  onListo?: () => void
  compacto?: boolean
}) {
  const entrada = useRef<HTMLInputElement>(null)
  const [cargando, setCargando] = useState(false)
  const [resultado, setResultado] = useState<ResultadoImportacion | null>(null)

  const elegir = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const archivo = e.target.files?.[0]
    // Se limpia siempre: sin esto, volver a elegir el mismo archivo no dispara
    // el evento y parece que el botón dejó de funcionar.
    e.target.value = ''
    if (!archivo) return

    setCargando(true)
    try {
      const filas = await leerArchivo(archivo, columnas)
      if (filas.length === 0) {
        toast.error('El archivo no tiene filas con datos')
        return
      }
      const r = await onImportar(filas)
      setResultado(r)
      if (r.creados > 0) onListo?.()
    } catch (err: any) {
      toast.error(err?.response?.data?.detail ?? err?.message ?? 'No se pudo leer el archivo')
    } finally {
      setCargando(false)
    }
  }

  return (
    <>
      <Stack direction="row" spacing={compacto ? 0.5 : 1}>
        <Tooltip title="Descargar una plantilla de Excel con las columnas de este catálogo">
          <Button
            size="small" variant="outlined" startIcon={<CloudDownload />}
            onClick={() => descargarPlantilla(nombreArchivo, titulo, columnas)}
            sx={{ textTransform: 'none', fontWeight: 600, borderColor: color, color }}
          >
            {compacto ? 'Plantilla' : 'Descargar plantilla'}
          </Button>
        </Tooltip>
        <Tooltip title="Cargar un archivo de Excel con varios registros a la vez">
          <Button
            size="small" variant="contained" startIcon={<CloudUpload />}
            onClick={() => entrada.current?.click()} disabled={cargando}
            sx={{ textTransform: 'none', fontWeight: 700, bgcolor: color }}
          >
            {cargando ? 'Cargando…' : (compacto ? 'Cargar' : 'Cargar Excel')}
          </Button>
        </Tooltip>
        <input
          ref={entrada} type="file" hidden accept=".xlsx,.xls,.csv" onChange={elegir}
        />
      </Stack>
      {cargando && <LinearProgress sx={{ mt: 1, borderRadius: 99 }} />}

      <Dialog open={!!resultado} onClose={() => setResultado(null)} maxWidth="sm" fullWidth>
        <DialogTitle sx={{ fontWeight: 700 }}>Resultado del cargue</DialogTitle>
        <DialogContent>
          <Stack direction="row" spacing={1} mb={2} flexWrap="wrap" useFlexGap>
            <Chip label={`${resultado?.creados ?? 0} creados`} sx={{
              fontWeight: 700, bgcolor: `${ESTADO.exito}1A`, color: ESTADO.exito,
            }} />
            {(resultado?.omitidos ?? 0) > 0 && (
              <Chip label={`${resultado?.omitidos} ya existían`} sx={{
                fontWeight: 700, bgcolor: `${PALETA.acero}26`, color: PALETA.grafito,
              }} />
            )}
            {(resultado?.errores.length ?? 0) > 0 && (
              <Chip label={`${resultado?.errores.length} con error`} sx={{
                fontWeight: 700, bgcolor: `${ESTADO.peligro}1A`, color: ESTADO.peligro,
              }} />
            )}
            <Chip label={`${resultado?.total ?? 0} filas leídas`} variant="outlined" />
          </Stack>

          {resultado?.errores.length ? (
            <>
              <Alert severity="warning" sx={{ mb: 2 }}>
                Lo demás sí quedó cargado. Corrija solo estas filas y vuelva a subir
                el archivo: lo que ya existe se omite, no se duplica.
              </Alert>
              <Box sx={{ maxHeight: 300, overflow: 'auto' }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow>
                      <TableCell sx={{ fontWeight: 700, width: 90 }}>FILA</TableCell>
                      <TableCell sx={{ fontWeight: 700 }}>QUÉ PASÓ</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {resultado.errores.map((e, i) => (
                      <TableRow key={i}>
                        <TableCell sx={{ fontWeight: 700, fontVariantNumeric: 'tabular-nums' }}>
                          {e.fila}
                        </TableCell>
                        <TableCell sx={{ color: PALETA.grafito }}>{e.motivo}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            </>
          ) : (
            <Alert severity="success">
              El archivo se cargó completo, sin filas con problemas.
            </Alert>
          )}
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={() => setResultado(null)} variant="contained"
            sx={{ textTransform: 'none' }}>
            Cerrar
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
