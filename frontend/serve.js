// 零依赖前端静态服务 + /api 反向代理到后端 8010（ESM 版）
// 用于本环境替代会崩溃的 vite dev/preview
import http from 'node:http'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const ROOT = path.join(__dirname, 'dist')
const API_TARGET = { host: '127.0.0.1', port: 8010 }
const PORT = Number(process.env.FRONT_PORT || 8080)

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.map': 'application/json; charset=utf-8',
}

function serveStatic(req, res) {
  let urlPath = decodeURIComponent(req.url.split('?')[0])
  let filePath = path.join(ROOT, urlPath)
  if (!filePath.startsWith(ROOT)) { res.writeHead(403); return res.end('forbidden') }
  fs.stat(filePath, (err, stat) => {
    if (err || stat.isDirectory()) filePath = path.join(ROOT, 'index.html')
    fs.readFile(filePath, (e, buf) => {
      if (e) { res.writeHead(404); return res.end('not found') }
      const ext = path.extname(filePath).toLowerCase()
      res.writeHead(200, { 'Content-Type': MIME[ext] || 'application/octet-stream' })
      res.end(buf)
    })
  })
}

function proxyApi(req, res) {
  const options = {
    host: API_TARGET.host,
    port: API_TARGET.port,
    path: req.url,
    method: req.method,
    headers: { ...req.headers, host: `${API_TARGET.host}:${API_TARGET.port}` },
  }
  const proxy = http.request(options, (apiRes) => {
    res.writeHead(apiRes.statusCode, apiRes.headers)
    apiRes.pipe(res)
  })
  proxy.on('error', (e) => {
    res.writeHead(502, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ ok: false, error: 'backend unreachable: ' + e.message }))
  })
  req.pipe(proxy)
}

const server = http.createServer((req, res) => {
  if (req.url.startsWith('/api')) return proxyApi(req, res)
  return serveStatic(req, res)
})
server.listen(PORT, '127.0.0.1', () => {
  console.log(`[frontend] serving ${ROOT} on http://127.0.0.1:${PORT}  (proxy /api -> ${API_TARGET.host}:${API_TARGET.port})`)
})
