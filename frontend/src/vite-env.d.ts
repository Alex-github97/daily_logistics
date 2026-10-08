/// <reference types="vite/client" />

/**
 * Tipos de las variables de entorno de Vite.
 *
 * Sin esta declaración, cada `import.meta.env` daba un error de tipos —los dos
 * que ya arrastraba el proyecto en client.ts y movimientos.ts—, aunque en
 * ejecución funcionara.
 */
interface ImportMetaEnv {
  readonly VITE_API_URL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
