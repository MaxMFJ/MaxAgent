#!/usr/bin/env node
/**
 * 静态文件服务，无 Host 检查，供 Tunnel 代理使用
 */
import { createServer } from 'http'
import { readFileSync, existsSync, statSync } from 'fs'
import { join, extname } from 'path'
import { fileURLToPath } from 'url'

const __dirname = fileURLToPath(new URL('.', import.meta.url))
const DIST = join(__dirname, '..', 'dist')
const PORT = 4180

const MIME = {
  '.html': 'text/html',
  '.js': 'application/javascript',
  '.css': 'text/css',
  '.json': 'application/json',
  '.ico': 'image/x-icon',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.woff2': 'font/woff2',
}

function serveFile(res, filePath) {
  const ext = extname(filePath)
  const mime = MIME[ext] || 'application/octet-stream'
  res.writeHead(200, { 'Content-Type': mime })
  res.end(readFileSync(filePath))
}

const server = createServer((req, res) => {
  let path = req.url?.split('?')[0] || '/'
  if (path === '/') path = '/index.html'
  let file = join(DIST, path)

  if (!file.startsWith(DIST)) {
    file = join(DIST, 'index.html')
  }

  if (!existsSync(file)) {
    const index = join(DIST, 'index.html')
    if (existsSync(index)) {
      serveFile(res, index)
      return
    }
    res.writeHead(404).end('Not Found')
    return
  }

  const stat = statSync(file)
  if (stat.isDirectory()) {
    file = join(file, 'index.html')
    if (!existsSync(file)) {
      res.writeHead(404).end('Not Found')
      return
    }
  }

  serveFile(res, file)
})

server.listen(PORT, '0.0.0.0', () => {
  console.log(`Preview: http://localhost:${PORT}`)
})
