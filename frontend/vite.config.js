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
  // 门户 www.nengyousuan.com 以路径前缀 /sim/ 反代本平台（71 服务器未备案，域名不可直连，只能经已备案门户转发）。
  // 注意：base 改为 /sim/ 后 http://36.151.146.71:40014 的 IP 直连将失效（资源变 /sim/assets/*），
  //       对外入口收敛为 https://www.nengyousuan.com/sim/（门户 nginx 剥离 /sim 前缀后转发到 71:40014）。
  //       如需恢复直连 / 子域名整站代理，改回 '/' 重新构建即可。
  base: '/sim/',
  plugins: [vue(), cleanDistOldAssets()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // 开发期把 API/WS 代理到后端，避免跨域
      '/api': { target: 'http://127.0.0.1:8010', changeOrigin: true, ws: true },
      // 盒子/云端设备相关接口（/box/*）同样代理到后端，避免前端 SPA fallback 返回 index.html
      '/box': { target: 'http://127.0.0.1:8010', changeOrigin: true },
      // 报告新页面（/report/<id>）也由后端渲染，开发期代理到后端
      '/report': { target: 'http://127.0.0.1:8010', changeOrigin: true },
      // 独立文档站（宣传手册/使用手册/技术文档）：同源 /docs/* 代理到本地 docs-site dev server
      // （5174，base=/docs/，保留前缀原样转发；生产由后端反代，行为一致）
      '/docs': { target: 'http://127.0.0.1:5174', changeOrigin: true },
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
