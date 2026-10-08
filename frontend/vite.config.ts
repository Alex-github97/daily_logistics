import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import os from 'os'

// Daily Logistics corre en su propio puerto (5180) y habla con su propio
// backend (8100 en el host, `backend:8000` dentro de Docker). No comparte nada
// con control-inventarios.
const API_TARGET = process.env.API_TARGET || 'http://localhost:8100'

function getLanIP(): string {
  if (process.env.HOST_IP) return process.env.HOST_IP
  for (const iface of Object.values(os.networkInterfaces())) {
    for (const net of iface ?? []) {
      if (net.family === 'IPv4' && !net.internal) return net.address
    }
  }
  return ''
}

export default defineConfig({
  plugins: [
    react(),
    {
      name: 'lan-ip',
      configureServer(server) {
        server.middlewares.use('/server-ip', (_req, res) => {
          res.setHeader('Content-Type', 'application/json')
          res.end(JSON.stringify({ ip: getLanIP() }))
        })
      },
    },
  ],
  resolve: {
    alias: { '@': path.resolve(__dirname, './src') },
  },
  server: {
    host: '0.0.0.0',
    port: 5180,
    strictPort: true,
    watch: { usePolling: true, interval: 1000 },
    proxy: {
      '/api': {
        target: API_TARGET,
        changeOrigin: true,
        headers: { Origin: 'http://localhost:5180' },
      },
    },
  },
  build: {
    rollupOptions: {
      input: {
        main: path.resolve(__dirname, 'index.html'),
        admin: path.resolve(__dirname, 'admin.html'),
      },
    },
  },
})
