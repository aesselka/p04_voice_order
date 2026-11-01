import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// VITE_API_URL задан -> /cart и /nlu проксируются на Python-бэк (без проблем с CORS)
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const target = (env.VITE_API_URL || '').replace(/\/$/, '')
  return {
    plugins: [react()],
    server: {
      port: 5173,
      host: true,
      proxy: target ? { '/cart': target, '/nlu': target } : undefined,
    },
  }
})
