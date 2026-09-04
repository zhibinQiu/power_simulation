import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 独立文档网站：开发端口 5174，预览（生产托管）端口 40183
export default defineConfig({
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
