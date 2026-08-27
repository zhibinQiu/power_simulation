// 轻量 Markdown 渲染（标题/表格/列表/引用/代码块/粗体/斜体/行内代码/分隔线）
// 零依赖，输出已 HTML 转义，防注入。与平台前端实现保持一致。

export function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

function inline(s) {
  let t = escapeHtml(s)
  t = t.replace(/`([^`]+)`/g, (m, c) => '<code>' + c + '</code>')
  t = t.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
  t = t.replace(/\*([^*]+)\*/g, '<em>$1</em>')
  return t
}

export function renderMarkdown(src, opts = {}) {
  const headingIds = !!(opts && opts.headingIds)
  const lines = String(src || '').split('\n')
  const out = []
  let i = 0
  let hid = 0
  const isTableRow = (l) => /^\s*\|.*\|\s*$/.test(l)
  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()
    if (!trimmed) { i++; continue }

    if (trimmed.startsWith('```')) {
      const buf = []
      i++
      while (i < lines.length && !lines[i].trim().startsWith('```')) { buf.push(lines[i]); i++ }
      i++
      out.push('<pre class="rp-code"><code>' + escapeHtml(buf.join('\n')) + '</code></pre>')
      continue
    }

    if (isTableRow(trimmed)) {
      const rows = []
      while (i < lines.length && isTableRow(lines[i].trim())) { rows.push(lines[i].trim()); i++ }
      if (rows.length >= 2) {
        const header = rows[0].split('|').slice(1, -1).map((x) => x.trim())
        const body = rows.slice(2).map((r) => r.split('|').slice(1, -1).map((x) => x.trim()))
        out.push(
          '<table><thead><tr>' + header.map((h) => '<th>' + inline(h) + '</th>').join('') + '</tr></thead><tbody>' +
          body.map((r) => '<tr>' + r.map((c) => '<td>' + inline(c) + '</td>').join('') + '</tr>').join('') +
          '</tbody></table>',
        )
      } else {
        out.push('<p>' + inline(rows[0]) + '</p>')
        i -= rows.length - 1
      }
      continue
    }

    if (/^#{1,4}\s/.test(trimmed)) {
      const level = trimmed.match(/^#+/)[0].length
      hid += 1
      const idAttr = headingIds ? ' id="md-h-' + hid + '"' : ''
      out.push('<h' + level + idAttr + '>' + inline(trimmed.replace(/^#+\s*/, '')) + '</h' + level + '>')
      i++
      continue
    }

    if (/^(-{3,}|\*{3,})$/.test(trimmed)) { out.push('<hr/>'); i++; continue }

    if (/^>\s?/.test(trimmed)) {
      const buf = []
      while (i < lines.length && /^\s*>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^\s*>\s?/, '')); i++ }
      out.push('<blockquote>' + buf.map((b) => inline(b)).join('<br/>') + '</blockquote>')
      continue
    }

    if (/^\s*[-*]\s/.test(trimmed) || /^\s*\d+\.\s/.test(trimmed)) {
      const ordered = /^\s*\d+\.\s/.test(trimmed)
      const items = []
      while (i < lines.length && (ordered ? /^\s*\d+\.\s/.test(lines[i]) : /^\s*[-*]\s/.test(lines[i]))) {
        items.push(inline(lines[i].replace(/^\s*\d+\.\s/, '').replace(/^\s*[-*]\s/, '')))
        i++
      }
      const tag = ordered ? 'ol' : 'ul'
      out.push('<' + tag + '>' + items.map((it) => '<li>' + it + '</li>').join('') + '</' + tag + '>')
      continue
    }

    out.push('<p>' + inline(trimmed) + '</p>')
    i++
  }
  return out.join('\n')
}

// 解析 Markdown 标题生成目录（与 renderMarkdown 的 headingIds 锚点编号一致）
export function parseToc(src) {
  const toc = []
  let hid = 0
  for (const line of String(src || '').split('\n')) {
    const m = line.trim().match(/^(#{1,4})\s+(.*)$/)
    if (!m) continue
    hid += 1
    toc.push({ level: m[1].length, text: m[2].replace(/[*`]/g, '').trim(), id: 'md-h-' + hid })
  }
  return toc
}
