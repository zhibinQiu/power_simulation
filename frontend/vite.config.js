import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { execSync } from 'node:child_process'

// 构建前清理 dist 中上一次的旧产物（仅保留 public 复制内容与 index.html），
// 避免产物无限累积导致 dist 膨胀（此前累积达 305MB/740 文件）。
// 用 shell find 而非 fs.rmSync：本机 IDE 的 safe-delete 钩子会拦截 vite 内部批量删除。
const cleanDistOldAssets = () => ({
  name: 'clean-dist-old-assets',
  apply: 'build',
  buildStart() {
    try { execSync('find dist -type f ! -name "index.html" -delete; find dist -type d -empty -delete') } catch { /* 目录不存在时忽略 */ }
  },
})

export default defineConfig({
  base: '/',
  plugins: [vue(), cleanDistOldAssets()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // 开发期把 API/WS 代理到后端，避免跨域
      '/api': { target: 'http://127.0.0.1:8010', changeOrigin: true, ws: true },
      // 报告新页面（/report/<id>）也由后端渲染，开发期代理到后端
      '/report': { target: 'http://127.0.0.1:8010', changeOrigin: true },
    },
  },
  build: {
    outDir: 'dist',
    chunkSizeWarningLimit: 1500,
    // 旧产物由 clean-dist-old-assets 插件在构建前清理（emptyOutDir 在本机被 safe-delete 拦截）
    emptyOutDir: false,
    // 分包：vue/pinia 与 three 单独成 chunk，利于浏览器长缓存 + 并行加载，减少首屏 IO 等待
    rollupOptions: {
      output: {
        manualChunks: {
          'vue-vendor': ['vue', 'pinia'],
          'three': ['three'],
        },
      },
    },
  },
})
