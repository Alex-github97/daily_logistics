import { createTheme, alpha } from '@mui/material/styles'

import { ACENTO, ESTADO, PALETA, SUPERFICIE } from '@/config/marca'
// `primary` de MUI tiñe botones, foco, enlaces y selección: es el color de lo
// pulsable, no el de la marca. Por eso lleva el acento y no el tinta — con el
// tinta, un botón primario y un texto normal se veían iguales.
const PRIMARY      = ACENTO.base
const PRIMARY_DARK = ACENTO.profundo
const PRIMARY_LIGHT = ACENTO.vapor
const BACKGROUND   = SUPERFICIE.contenido
const DARK         = PALETA.abismo
const SIDEBAR      = SUPERFICIE.barra
const SURFACE      = SUPERFICIE.tarjeta
const TEXT         = PALETA.tinta

/** Rampa de elevación completa (25 niveles) — sombras suaves en capas,
 *  estilo "soft-ui" moderno (ambiente + contacto). */
const ELEV = (y: number, blur: number, a1: number, a2: number) =>
  `0 ${y}px ${blur}px -${Math.round(y / 2)}px rgba(15,23,42,${a1}), 0 ${Math.max(1, Math.round(y / 3))}px ${Math.round(blur / 3)}px -1px rgba(15,23,42,${a2})`

const shadows = [
  'none',
  '0 1px 2px rgba(15,23,42,0.05)',
  '0 1px 3px rgba(15,23,42,0.07), 0 1px 2px rgba(15,23,42,0.04)',
  ELEV(3, 8, 0.07, 0.04),
  ELEV(4, 10, 0.08, 0.04),
  ELEV(6, 14, 0.08, 0.05),
  ELEV(8, 18, 0.09, 0.05),
  ELEV(10, 22, 0.09, 0.05),
  ELEV(12, 26, 0.10, 0.05),
  ELEV(14, 30, 0.10, 0.06),
  ELEV(16, 34, 0.11, 0.06),
  ELEV(18, 38, 0.11, 0.06),
  ELEV(20, 42, 0.12, 0.06),
  ELEV(22, 46, 0.12, 0.07),
  ELEV(24, 50, 0.13, 0.07),
  ELEV(26, 54, 0.13, 0.07),
  ELEV(28, 58, 0.14, 0.07),
  ELEV(30, 62, 0.14, 0.08),
  ELEV(32, 66, 0.15, 0.08),
  ELEV(34, 70, 0.15, 0.08),
  ELEV(36, 74, 0.16, 0.08),
  ELEV(38, 78, 0.16, 0.09),
  ELEV(40, 82, 0.17, 0.09),
  ELEV(42, 86, 0.17, 0.09),
  '0 24px 64px rgba(15,23,42,0.18), 0 8px 24px rgba(15,23,42,0.10)',
] as any

export const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: PRIMARY,
      dark: PRIMARY_DARK,
      light: PRIMARY_LIGHT,
      contrastText: '#FFFFFF',
    },
    secondary: {
      main: DARK,
      contrastText: '#FFFFFF',
    },
    background: {
      default: BACKGROUND,
      paper: SURFACE,
    },
    text: {
      primary: TEXT,
      secondary: PALETA.grafito,
    },
    divider: SUPERFICIE.divisor,
    // Los estados van a los colores que significan algo. `success` estaba
    // atado al color primario, así que un mensaje de éxito salía del color de
    // la marca en vez de verde.
    success: { main: ESTADO.exito },
    error:   { main: ESTADO.peligro },
    warning: { main: ESTADO.alerta },
    info:    { main: ESTADO.informacion },
  },
  typography: {
    fontFamily: '"Plus Jakarta Sans", "Helvetica Neue", Arial, sans-serif',
    h1: { fontWeight: 800, fontSize: '2.25rem',  color: DARK, letterSpacing: '-0.025em' },
    h2: { fontWeight: 800, fontSize: '1.875rem', color: DARK, letterSpacing: '-0.02em' },
    h3: { fontWeight: 700, fontSize: '1.5rem',   color: DARK, letterSpacing: '-0.015em' },
    h4: { fontWeight: 700, fontSize: '1.25rem',  color: DARK, letterSpacing: '-0.01em' },
    h5: { fontWeight: 700, fontSize: '1.1rem',   color: TEXT, letterSpacing: '-0.01em' },
    h6: { fontWeight: 600, fontSize: '1rem',     color: TEXT },
    subtitle1: { fontWeight: 500, color: TEXT },
    body1: { color: TEXT, lineHeight: 1.6 },
    body2: { color: '#64748B', lineHeight: 1.5 },
    caption: { color: '#94A3B8', letterSpacing: '0.02em' },
    button: { textTransform: 'none' as const, fontWeight: 600 },
  },
  shape: { borderRadius: 12 },
  shadows,
  components: {
    // ── Botones ──────────────────────────────────────────────────────────────
    MuiButton: {
      defaultProps: { disableElevation: false },
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          borderRadius: 10,
          padding: '8px 18px',
          fontSize: '0.875rem',
          transition: 'transform 0.15s cubic-bezier(0.4,0,0.2,1), box-shadow 0.2s ease, background-color 0.2s ease, border-color 0.2s ease',
          '&:focus-visible': {
            outline: 'none',
            boxShadow: `0 0 0 3px ${alpha(PRIMARY, 0.35)}`,
          },
          '&:active': { transform: 'scale(0.985)' },
        },
        contained: {
          boxShadow: '0 1px 2px rgba(15,23,42,0.20), inset 0 1px 0 rgba(255,255,255,0.18)',
          '&:hover': {
            boxShadow: '0 6px 16px -4px rgba(15,23,42,0.35), inset 0 1px 0 rgba(255,255,255,0.18)',
            transform: 'translateY(-1px)',
          },
          '&:active': { transform: 'translateY(0) scale(0.985)' },
        },
        containedPrimary: {
          backgroundImage: `linear-gradient(180deg, ${PRIMARY_LIGHT}26 0%, transparent 55%)`,
          '&:hover': { boxShadow: `0 6px 18px -4px ${alpha(PRIMARY, 0.55)}, inset 0 1px 0 rgba(255,255,255,0.2)` },
        },
        outlined: {
          borderColor: '#E2E8F0',
          backgroundColor: '#FFFFFF',
          '&:hover': {
            borderColor: PRIMARY,
            backgroundColor: alpha(PRIMARY, 0.04),
            transform: 'translateY(-1px)',
            boxShadow: '0 4px 10px -4px rgba(15,23,42,0.15)',
          },
        },
        text: {
          '&:hover': { backgroundColor: alpha(PRIMARY, 0.06) },
        },
        sizeSmall: { padding: '5px 12px', borderRadius: 9 },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          transition: 'transform 0.15s ease, background-color 0.15s ease, color 0.15s ease',
          '&:hover': { transform: 'scale(1.08)' },
          '&:active': { transform: 'scale(0.95)' },
        },
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          borderRadius: 10,
          borderColor: '#E2E8F0',
          color: '#64748B',
          transition: 'all 0.18s ease',
          '&.Mui-selected': {
            backgroundColor: alpha(PRIMARY, 0.10),
            color: PRIMARY_DARK,
            fontWeight: 700,
            '&:hover': { backgroundColor: alpha(PRIMARY, 0.16) },
          },
        },
      },
    },
    // ── Superficies ─────────────────────────────────────────────────────────
    MuiPaper: {
      styleOverrides: {
        rounded: { borderRadius: 14 },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          boxShadow: '0 1px 3px rgba(15,23,42,0.05), 0 0 0 1px rgba(15,23,42,0.045)',
          border: 'none',
          transition: 'box-shadow 0.25s cubic-bezier(0.4,0,0.2,1), transform 0.25s cubic-bezier(0.4,0,0.2,1)',
          '&:hover': {
            boxShadow: '0 12px 32px -8px rgba(15,23,42,0.14), 0 0 0 1px rgba(15,23,42,0.045)',
            transform: 'translateY(-2px)',
          },
        },
      },
    },
    // ── Tabs ─────────────────────────────────────────────────────────────────
    MuiTabs: {
      styleOverrides: {
        root: { minHeight: 42 },
        indicator: {
          height: 3,
          borderRadius: '3px 3px 0 0',
          background: `linear-gradient(90deg, ${PRIMARY}, ${PRIMARY_LIGHT})`,
        },
      },
    },
    MuiTab: {
      styleOverrides: {
        root: {
          textTransform: 'none',
          fontWeight: 600,
          fontSize: '0.85rem',
          minHeight: 42,
          borderRadius: '10px 10px 0 0',
          transition: 'color 0.18s ease, background-color 0.18s ease',
          '&:hover': { backgroundColor: 'rgba(15,23,42,0.035)' },
        },
      },
    },
    // ── Chips / badges ───────────────────────────────────────────────────────
    MuiChip: {
      styleOverrides: {
        root: {
          fontWeight: 600,
          borderRadius: 8,
          fontSize: '0.75rem',
          transition: 'transform 0.15s ease, box-shadow 0.15s ease',
        },
        clickable: {
          '&:hover': { transform: 'translateY(-1px)', boxShadow: '0 3px 8px -2px rgba(15,23,42,0.2)' },
        },
        sizeSmall: { height: 22 },
      },
    },
    // ── Tablas ───────────────────────────────────────────────────────────────
    MuiTableHead: {
      styleOverrides: {
        root: {
          '& .MuiTableCell-head': {
            backgroundColor: '#F8FAFC',
            fontWeight: 700,
            fontSize: '0.7rem',
            textTransform: 'uppercase',
            letterSpacing: '0.07em',
            color: '#94A3B8',
            borderBottom: '1px solid #E2E8F0',
            padding: '10px 16px',
            whiteSpace: 'nowrap',
          },
        },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          transition: 'background-color 0.12s ease, box-shadow 0.12s ease',
          '&:hover': {
            backgroundColor: alpha(PRIMARY, 0.035),
            // acento lateral tipo panel de instrumentos
            boxShadow: `inset 2.5px 0 0 ${alpha(PRIMARY, 0.45)}`,
          },
          '&:last-child td': { border: 0 },
          '&.Mui-selected': {
            backgroundColor: alpha(PRIMARY, 0.07),
            boxShadow: `inset 2.5px 0 0 ${PRIMARY}`,
            '&:hover': { backgroundColor: alpha(PRIMARY, 0.10) },
          },
        },
        head: {
          '&:hover': { backgroundColor: 'transparent', boxShadow: 'none' },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: {
          borderColor: '#F1F5F9',
          padding: '12px 16px',
          fontSize: '0.875rem',
          // dígitos de ancho fijo: las columnas numéricas quedan alineadas
          fontVariantNumeric: 'tabular-nums',
        },
      },
    },
    // ── Navegación lateral / listas ─────────────────────────────────────────
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          transition: 'background-color 0.15s ease, color 0.15s ease, transform 0.15s ease',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          backgroundColor: SIDEBAR,
          color: '#FFFFFF',
          borderRight: 'none',
        },
      },
    },
    // ── Feedback ────────────────────────────────────────────────────────────
    MuiLinearProgress: {
      styleOverrides: {
        root: { borderRadius: 99, height: 6, backgroundColor: '#EEF2F6' },
        bar: { borderRadius: 99 },
        barColorPrimary: {
          background: `linear-gradient(90deg, ${PRIMARY_DARK}, ${PRIMARY} 60%, ${PRIMARY_LIGHT})`,
        },
      },
    },
    MuiSkeleton: {
      defaultProps: { animation: 'wave' },
      styleOverrides: {
        root: { borderRadius: 8, backgroundColor: 'rgba(15,23,42,0.06)' },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: 12,
          fontWeight: 500,
          fontSize: '0.845rem',
          alignItems: 'center',
        },
        standardSuccess: { backgroundColor: '#F0FDF4', color: '#166534', border: '1px solid #BBF7D0' },
        standardError:   { backgroundColor: '#FEF2F2', color: '#991B1B', border: '1px solid #FECACA' },
        standardWarning: { backgroundColor: '#FFFBEB', color: '#92400E', border: '1px solid #FDE68A' },
        standardInfo:    { backgroundColor: '#EFF6FF', color: '#1E40AF', border: '1px solid #BFDBFE' },
      },
    },
    MuiBadge: {
      styleOverrides: {
        badge: { fontWeight: 700, boxShadow: '0 0 0 2px #FFFFFF' },
      },
    },
    // ── Formularios ─────────────────────────────────────────────────────────
    MuiTextField: {
      styleOverrides: {
        root: {
          '& .MuiOutlinedInput-root': {
            borderRadius: 10,
            fontSize: '0.9rem',
            backgroundColor: '#FFFFFF',
            transition: 'box-shadow 0.18s ease, background-color 0.18s ease',
            '&.Mui-focused': {
              boxShadow: `0 0 0 3.5px ${alpha(PRIMARY, 0.14)}`,
              '& fieldset': { borderColor: PRIMARY, borderWidth: 1.5 },
            },
            '& fieldset': { borderColor: '#E2E8F0', transition: 'border-color 0.18s ease' },
            '&:hover fieldset': { borderColor: '#B8C4D2' },
          },
        },
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: { fontSize: '0.875rem', color: '#64748B' },
      },
    },
    MuiSwitch: {
      styleOverrides: {
        root: {
          width: 42,
          height: 24,
          padding: 0,
          margin: 8,
          '& .MuiSwitch-switchBase': {
            padding: 0,
            margin: 2,
            transitionDuration: '250ms',
            '&.Mui-checked': {
              transform: 'translateX(18px)',
              color: '#FFF',
              '& + .MuiSwitch-track': {
                backgroundColor: PRIMARY,
                opacity: 1,
                border: 0,
              },
            },
          },
          '& .MuiSwitch-thumb': {
            boxSizing: 'border-box',
            width: 20,
            height: 20,
            boxShadow: '0 2px 4px rgba(15,23,42,0.2)',
          },
          '& .MuiSwitch-track': {
            borderRadius: 13,
            backgroundColor: '#CBD5E1',
            opacity: 1,
            transition: 'background-color 250ms',
          },
        },
      },
    },
    // ── Overlays ────────────────────────────────────────────────────────────
    // Sin backdrop-filter a propósito: desenfocar el viewport completo obliga al
    // compositor a rasterizar y convolucionar toda la pantalla en cada apertura,
    // lo que hacía que abrir cualquier diálogo o menú se sintiera trabado. El
    // oscurecido da la misma separación visual con costo cero.
    MuiBackdrop: {
      styleOverrides: {
        root: {
          '&:not(.MuiBackdrop-invisible)': {
            backgroundColor: 'rgba(10,15,28,0.55)',
          },
        },
      },
    },
    MuiDialog: {
      styleOverrides: {
        paper: {
          borderRadius: 22,
          boxShadow: '0 32px 80px rgba(8,12,24,0.35), 0 8px 24px rgba(8,12,24,0.18), 0 0 0 1px rgba(255,255,255,0.55) inset',
          animation: 'dialogIn 0.34s cubic-bezier(0.34,1.4,0.64,1)',
          '@keyframes dialogIn': {
            from: { opacity: 0, transform: 'translateY(18px) scale(0.96)' },
            to:   { opacity: 1, transform: 'translateY(0) scale(1)' },
          },
        },
      },
    },
    MuiDialogTitle: {
      styleOverrides: {
        root: { fontWeight: 700, letterSpacing: '-0.01em' },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          borderRadius: 12,
          backgroundColor: '#FFFFFF',
          boxShadow: '0 16px 40px -8px rgba(15,23,42,0.22), 0 0 0 1px rgba(15,23,42,0.05)',
          marginTop: 4,
        },
        list: { padding: '6px' },
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          borderRadius: 8,
          fontSize: '0.875rem',
          padding: '7px 12px',
          transition: 'background-color 0.12s ease',
          '&:hover': { backgroundColor: 'rgba(15,23,42,0.045)' },
          '&.Mui-selected': {
            backgroundColor: alpha(PRIMARY, 0.10),
            fontWeight: 600,
            '&:hover': { backgroundColor: alpha(PRIMARY, 0.15) },
          },
        },
      },
    },
    MuiPopover: {
      styleOverrides: {
        paper: {
          borderRadius: 12,
          backgroundColor: '#FFFFFF',
          boxShadow: '0 16px 40px -8px rgba(15,23,42,0.22), 0 0 0 1px rgba(15,23,42,0.05)',
        },
      },
    },
    MuiAutocomplete: {
      styleOverrides: {
        paper: {
          borderRadius: 12,
          backgroundColor: '#FFFFFF',
          boxShadow: '0 16px 40px -8px rgba(15,23,42,0.22), 0 0 0 1px rgba(15,23,42,0.05)',
        },
        option: {
          borderRadius: 8,
          margin: '2px 6px',
          fontSize: '0.875rem',
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          boxShadow: 'none',
        },
      },
    },
    MuiDivider: {
      styleOverrides: {
        root: { borderColor: '#F1F5F9' },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          borderRadius: 8,
          fontSize: '0.75rem',
          fontWeight: 500,
          backgroundColor: 'rgba(15,23,42,0.96)',
          padding: '6px 10px',
          boxShadow: '0 8px 24px -6px rgba(15,23,42,0.4)',
        },
        arrow: { color: 'rgba(15,23,42,0.94)' },
      },
    },
  },
})

export const STATUS_COLORS: Record<string, { bg: string; color: string; border: string; label: string }> = {
  DISPONIBLE:        { bg: '#F0FDF4', color: '#16A34A', border: '#BBF7D0', label: 'Disponible' },
  EN_INVENTARIO:     { bg: '#EFF6FF', color: '#2563EB', border: '#BFDBFE', label: 'En Inventario' },
  EN_TRANSITO:       { bg: '#FFFBEB', color: '#D97706', border: '#FDE68A', label: 'En Tránsito' },
  CARGADA:           { bg: '#FFFBEB', color: '#B45309', border: '#FCD34D', label: 'Cargada' },
  EN_CLIENTE:        { bg: '#F5F3FF', color: '#7C3AED', border: '#DDD6FE', label: 'En Cliente' },
  PENDIENTE_RETORNO: { bg: '#FFF7ED', color: '#EA580C', border: '#FED7AA', label: 'Pend. Retorno' },
  EN_REPARACION:     { bg: '#FEFCE8', color: '#CA8A04', border: '#FEF08A', label: 'En Reparación' },
  DANADA:            { bg: '#FEF2F2', color: '#DC2626', border: '#FECACA', label: 'Dañada' },
  FALTANTE:          { bg: '#FFF7ED', color: '#C2410C', border: '#FED7AA', label: 'Faltante' },
  PERDIDA:           { bg: '#FDF2F8', color: '#DB2777', border: '#FBCFE8', label: 'Perdida' },
  BAJA:              { bg: '#F8FAFC', color: '#64748B', border: '#E2E8F0', label: 'Baja' },
  DISPOSICION_FINAL: { bg: '#F8FAFC', color: '#64748B', border: '#E2E8F0', label: 'Disp. Final' },
}
