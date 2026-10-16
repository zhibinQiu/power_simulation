// 浏览器下载工具（统一实现，供各视图 / store 复用，避免各处重复写 createObjectURL + a.click）

/**
 * 触发浏览器下载。
 * @param {Blob} blob 文件内容
 * @param {string} filename 文件名（含扩展名）
 */
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename || 'download'
  document.body.appendChild(a)
  a.click()
  a.remove()
  // 延迟释放：部分浏览器在 click 后仍会读取 blob URL
  setTimeout(() => URL.revokeObjectURL(url), 4000)
}

/**
 * 把文本内容作为文件下载。
 * @param {string} text 文本内容
 * @param {string} filename 文件名
 * @param {string} [mime='text/plain;charset=utf-8'] MIME 类型
 */
export function downloadText(text, filename, mime = 'text/plain;charset=utf-8') {
  downloadBlob(new Blob([text], { type: mime }), filename)
}

/**
 * base64 字符串 → Blob（用于后端返回 base64 的二进制下载）。
 * @param {string} b64 base64 内容（不含 data: 前缀）
 * @param {string} [mime='application/octet-stream'] MIME 类型
 */
export function b64ToBlob(b64, mime = 'application/octet-stream') {
  const bin = atob(b64)
  const bytes = new Uint8Array(bin.length)
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
  return new Blob([bytes], { type: mime })
}
