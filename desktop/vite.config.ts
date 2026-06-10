import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
    },
  },
  clearScreen: false,
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    watch: {
      ignored: ["**/src-tauri/**"],
    },
  },
  build: {
    rolldownOptions: {
      input: "index.html",
      output: {
        codeSplitting: {
          groups: [
            { name: "react-vendor", test: /node_modules[\\/](react|react-dom|scheduler)[\\/]/, priority: 100 },
            { name: "monaco-editor", test: /node_modules[\\/](@monaco-editor|monaco-editor)[\\/]/, priority: 90 },
            { name: "charting", test: /node_modules[\\/](echarts|echarts-for-react|zrender)[\\/]/, priority: 80 },
            { name: "react-flow", test: /node_modules[\\/]@xyflow[\\/]/, priority: 70 },
            { name: "vendor", test: /node_modules[\\/]/, maxSize: 350 * 1024, priority: 10 },
          ],
        },
      },
    },
  },
})
