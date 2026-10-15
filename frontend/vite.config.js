import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'

// 注：原 device-images 插件（构建期扫描 public/2D-image/devices 生成图片清单 + alpha 边界元数据）
// 已于 2026-09-17 移除 —— 2D 工艺设备图改为**程序化 SVG 绘制**（src/data/twin2dFigures.js），
// 不再有 41MB 的 PNG 素材，也不需要离线跑 scripts/gen-devimg-meta.py 标定边界坐标。

// 构建前清理 dist 中上一次的旧产物（仅保留 public 复制内容与 index.html），
// 避免产物无限累积导致 dist 膨胀（此前累积达 305MB/740 文件）。
// 用 shell find 而非 fs.rmSync：本机 IDE 的 safe-delete 钩子会拦截 vite 内部批量删除。
// API 代理目标（可被 VITE_API_TARGET 覆盖，见下方 server.proxy）：默认直接打到官网 —— 它是唯一数据源。
const API_TARGET = process.env.VITE_API_TARGET || 'https://www.nengyousuan.com'
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
      // 单一数据源：编排 / AI 群控 / 工程等所有后台数据只有云端那一份，本地 dev server 也一样读它。
      // 否则本地读写的是 backend/data/designs/*.json（本机副本），与官网各存各的，两地计数对不上。
      // 需要离线调试本地后端时，用 `VITE_API_TARGET=http://127.0.0.1:8010 npm run dev` 切回去。
      '/api': { target: API_TARGET, changeOrigin: true, ws: true },
      // 盒子/云端设备相关接口（/box/*）同样走同一份后端
      '/box': { target: API_TARGET, changeOrigin: true },
      // 报告新页面（/report/<id>）也由后端渲染
      '/report': { target: API_TARGET, changeOrigin: true },
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
    // 分包：把体积大且不常变的第三方库拆成「稳定的 vendor chunk」——
    //   · 浏览器可并行下载多个文件（比一个大文件更快），静态资源已 gzip + immutable 强缓存；
    //   · 业务代码发版变动时这些 vendor 的 hash 不变，老用户无需重复下载。
    // three（3D 孪生）与 echarts/zrender（AI 对话图表）都是进入对应功能才加载，不占首屏关键路径。
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (!id.includes('node_modules')) return undefined
          if (id.includes('/three/')) return 'three'
          if (id.includes('/echarts/') || id.includes('/zrender/')) return 'echarts'
          if (id.includes('/vue/') || id.includes('/@vue/') || id.includes('/pinia/')) return 'vue-vendor'
          return undefined
        },
      },
    },
  },
})
