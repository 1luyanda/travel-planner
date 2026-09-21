import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '..', '')
  const apiAuthKey = env.API_AUTH_KEY

  return {
    plugins: [react()],
    envDir: '..',
    test: {
      environment: 'node',
    },
    server: {
      // Forward /api from the Vite dev server to FastAPI. The API key is read
      // by Vite's Node process and is never exposed as a VITE_ browser variable.
      proxy: {
        '/api': {
          target: 'http://127.0.0.1:8000',
          changeOrigin: true,
          configure(proxy) {
            proxy.on('proxyReq', (proxyRequest) => {
              if (apiAuthKey) {
                proxyRequest.setHeader('X-API-Key', apiAuthKey)
              }
            })
          },
        },
      },
    },
  }
})
