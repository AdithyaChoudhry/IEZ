import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'
import { execSync } from 'child_process'

// The version shown in the app comes from the git history of the build: V3.<number of commits> and the commit id.
function appVersion(): string {
  const git = (args: string) => execSync(`git ${args}`, { cwd: __dirname, stdio: ['ignore', 'pipe', 'ignore'] }).toString().trim()
  try {
    return `V3.${git('rev-list --count HEAD')} (${git('rev-parse --short HEAD')})`
  } catch {
    return 'V3' // no git history available where the app is built
  }
}

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
  define: { __APP_VERSION__: JSON.stringify(appVersion()) },
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  server: {
    port: 3000,
    proxy: {
      '/api': {
        target: process.env.VITE_API_PROXY || 'http://localhost:8000',
        changeOrigin: true,
      },
      '/ws': {
        target: process.env.VITE_WS_PROXY || 'ws://localhost:8000',
        ws: true,
      },
    },
  },
})
