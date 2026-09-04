import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 独立文档网站：开发端口 5174，预览（生产托管）端口 40183
// base=/docs/：文档站已并入平台同源访问（平台后端 /docs 反代 → 本站），
// 页面内所有资源引用一律带 /docs/ 前缀，由平台 40014 统一对外，不再直访 40184。
export default defineConfig({
  base: '/docs/',
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5174,
  },
  preview: {
    host: '127.0.0.1',
    port: 40183,
  },
})
