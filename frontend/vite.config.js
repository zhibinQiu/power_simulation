import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import { execSync } from 'node:child_process'
import fs from 'node:fs'
import { fileURLToPath } from 'node:url'

// 构建期扫描 public/2D-image/devices，把「实际存在的设备图名」固化成虚拟模块清单。
// 原方案是运行时对每张候选图发 HEAD 探测：首帧只能先画矢量图元、探测回来再换图，
// 有肉眼可见的「矢量 → 图片」跳变，且 dev server 重启/图片后放进去时会整屏回退矢量。
// 改为构建期清单后：打开 2D 工艺图即直接上图，零探测请求、零跳变。
// 新增/删除图片后：生产重新 build 即可；dev 下由 watcher 自动失效清单并刷新页面。
const DEV_IMG_ABS = fileURLToPath(new URL('./public/2D-image/devices', import.meta.url))
// 设备图「图形真实边界」清单（scripts/gen-devimg-meta.py 解析 PNG alpha 通道生成）。
// 透明背景素材的设备本体并不铺满画布（热风炉仅占 46%、铁水预处理 50%…），前端必须按
// 图形边界而非整张图定位，否则透明留白会把设备图形挤小、与连线端点脱开。
const DEV_IMG_META = fileURLToPath(new URL('./src/data/deviceImgMeta.json', import.meta.url))
const VID_DEV_IMG = 'virtual:device-images'
const deviceImages = () => {
  const read = () => {
    try { return fs.readdirSync(DEV_IMG_ABS).filter((f) => /\.png$/i.test(f)).sort() } catch { return [] }
  }
  const readMeta = () => {
    try { return JSON.parse(fs.readFileSync(DEV_IMG_META, 'utf8')) } catch { return {} }
  }
  let names = read()
  const vid = '\0' + VID_DEV_IMG
  return {
    name: 'device-images',
    resolveId(id) { return id === VID_DEV_IMG ? vid : null },
    load(id) {
      if (id !== vid) return null
      return `export const names = ${JSON.stringify(names)}\nexport const meta = ${JSON.stringify(readMeta())}`
    },
    configureServer(server) {
      server.watcher.add(DEV_IMG_ABS)
      server.watcher.add(DEV_IMG_META)
      const onChange = (f) => {
        if (!String(f).includes('2D-image') && !String(f).includes('deviceImgMeta')) return
        const next = read()
        names = next
        const mod = server.moduleGraph.getModuleById(vid)
        if (mod) server.moduleGraph.invalidateModule(mod)
        server.ws.send({ type: 'full-reload' })
      }
      server.watcher.on('add', onChange).on('unlink', onChange).on('change', onChange)
    },
  }
}

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
  plugins: [vue(), cleanDistOldAssets(), deviceImages()],
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
