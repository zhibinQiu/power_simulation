// 极简 XLSX 写出器（零依赖）
//
// 只为「把采集结果按设备分成多张工作表导出」这一件事服务，因此只实现 OOXML 的一个
// 最小子集，不引第三方库（本项目依赖一直保持极简）：
//   · 单元格两种类型 —— inlineStr（字符串，省掉 sharedStrings 表）与 n（数字）
//   · 三档样式 —— 默认 / 表头（加粗+浅底）/ 说明（灰字）
//   · 列宽
//   · zip：优先用浏览器原生 CompressionStream('deflate-raw')，不支持则退回 store（不压缩）
//
// 生成的都是 Excel 强制要求的部件（[Content_Types] / _rels / workbook / rels / styles /
// worksheet / docProps），保证双击打开不弹「需要修复」。

const XML_HEAD = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'

const enc = new TextEncoder()

/** XML 文本转义 + 过滤 XML 1.0 不允许的控制字符 */
function xesc(s) {
  return String(s)
    // eslint-disable-next-line no-control-regex
    .replace(/[\u0000-\u0008\u000B\u000C\u000E-\u001F]/g, '')
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}

// ---------------- zip ----------------

const CRC_TABLE = (() => {
  const t = new Uint32Array(256)
  for (let n = 0; n < 256; n++) {
    let c = n
    for (let k = 0; k < 8; k++) c = (c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1)
    t[n] = c >>> 0
  }
  return t
})()

function crc32(u8) {
  let c = 0xFFFFFFFF
  for (let i = 0; i < u8.length; i++) c = CRC_TABLE[(c ^ u8[i]) & 0xFF] ^ (c >>> 8)
  return (c ^ 0xFFFFFFFF) >>> 0
}

/** raw deflate（zip method 8 的数据体）；环境不支持时返回 null */
async function deflateRaw(u8) {
  if (typeof CompressionStream === 'undefined') return null
  try {
    const cs = new CompressionStream('deflate-raw')
    const w = cs.writable.getWriter()
    w.write(u8); w.close()
    const buf = await new Response(cs.readable).arrayBuffer()
    const out = new Uint8Array(buf)
    return out.length < u8.length ? out : null   // 压不小就退回 store
  } catch (e) {
    return null
  }
}

/** DOS 时间（zip 头要求 1980 起算） */
function dosTime(d = new Date()) {
  const y = Math.max(1980, d.getFullYear())
  return {
    time: ((d.getHours() << 11) | (d.getMinutes() << 5) | (d.getSeconds() >> 1)) & 0xFFFF,
    date: (((y - 1980) << 9) | ((d.getMonth() + 1) << 5) | d.getDate()) & 0xFFFF,
  }
}

/**
 * 打包 zip。
 * @param {Array<{name:string, data:Uint8Array}>} files
 * @returns {Promise<Uint8Array>}
 */
async function zipMake(files) {
  const { time, date } = dosTime()
  const parts = []
  const central = []
  let offset = 0

  for (const f of files) {
    const nameBytes = enc.encode(f.name)
    const raw = f.data
    const crc = crc32(raw)
    const packed = await deflateRaw(raw)
    const method = packed ? 8 : 0
    const body = packed || raw

    const lh = new Uint8Array(30 + nameBytes.length)
    const dv = new DataView(lh.buffer)
    dv.setUint32(0, 0x04034b50, true)     // local file header
    dv.setUint16(4, 20, true)             // version needed
    dv.setUint16(6, 0, true)              // flags
    dv.setUint16(8, method, true)
    dv.setUint16(10, time, true); dv.setUint16(12, date, true)
    dv.setUint32(14, crc, true)
    dv.setUint32(18, body.length, true)
    dv.setUint32(22, raw.length, true)
    dv.setUint16(26, nameBytes.length, true)
    dv.setUint16(28, 0, true)
    lh.set(nameBytes, 30)

    parts.push(lh, body)

    const cd = new Uint8Array(46 + nameBytes.length)
    const cv = new DataView(cd.buffer)
    cv.setUint32(0, 0x02014b50, true)     // central directory header
    cv.setUint16(4, 20, true)             // version made by
    cv.setUint16(6, 20, true)             // version needed
    cv.setUint16(8, 0, true)              // flags
    cv.setUint16(10, method, true)
    cv.setUint16(12, time, true); cv.setUint16(14, date, true)
    cv.setUint32(16, crc, true)
    cv.setUint32(20, body.length, true)
    cv.setUint32(24, raw.length, true)
    cv.setUint16(28, nameBytes.length, true)
    cv.setUint16(30, 0, true)             // extra len
    cv.setUint16(32, 0, true)             // comment len
    cv.setUint16(34, 0, true)             // disk number
    cv.setUint16(36, 0, true)             // internal attrs
    cv.setUint32(38, 0, true)             // external attrs
    cv.setUint32(42, offset, true)        // local header offset
    cd.set(nameBytes, 46)
    central.push(cd)

    offset += lh.length + body.length
  }

  const cdSize = central.reduce((n, c) => n + c.length, 0)
  const eocd = new Uint8Array(22)
  const ev = new DataView(eocd.buffer)
  ev.setUint32(0, 0x06054b50, true)
  ev.setUint16(4, 0, true); ev.setUint16(6, 0, true)
  ev.setUint16(8, files.length, true)
  ev.setUint16(10, files.length, true)
  ev.setUint32(12, cdSize, true)
  ev.setUint32(16, offset, true)
  ev.setUint16(20, 0, true)

  const total = offset + cdSize + eocd.length
  const out = new Uint8Array(total)
  let p = 0
  for (const b of parts) { out.set(b, p); p += b.length }
  for (const c of central) { out.set(c, p); p += c.length }
  out.set(eocd, p)
  return out
}

// ---------------- OOXML ----------------

const MIME = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'

const CONTENT_TYPES = `${XML_HEAD}
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
{sheets}
<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>`

const ROOT_RELS = `${XML_HEAD}
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>`

// counts 是数组下标 —— 样式索引用到哪个就必须存在哪个
const STYLES = `${XML_HEAD}
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<fonts count="3">
<font><sz val="11"/><color theme="1"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color theme="1"/><name val="Calibri"/></font>
<font><sz val="10"/><color rgb="FF7A828C"/><name val="Calibri"/></font>
</fonts>
<fills count="3">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="FFEDF1F7"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left/><right/><top style="thin"><color rgb="FFB7C0CC"/></top><bottom style="thin"><color rgb="FFB7C0CC"/></bottom><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="3">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="1" fillId="2" borderId="1" xfId="0" applyFont="1" applyFill="1" applyBorder="1" applyAlignment="1"><alignment vertical="center"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
<dxfs count="0"/>
</styleSheet>`

/** 0-25 → A-Z、26 → AA（列号转字母） */
function colName(i) {
  let s = ''
  let n = i + 1
  while (n > 0) {
    const r = (n - 1) % 26
    s = String.fromCharCode(65 + r) + s
    n = Math.floor((n - 1) / 26)
  }
  return s
}

/**
 * 一个工作表 → sheetN.xml
 * @param {Array<Array>} rows   每行是单元格数组；元素为 {v, s} 或裸值（字符串/数字）
 * @param {Array<number>} widths  列宽（字符数），可省略
 * @param {number} freeze         冻结前 N 行（表头/说明行），0 = 不冻结
 */
function sheetXml(rows, widths, freeze) {
  const out = [XML_HEAD,
    '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">']
  out.push('<sheetViews><sheetView workbookViewId="0">')
  if (freeze > 0) {
    out.push(`<pane ySplit="${freeze}" topLeftCell="A${freeze + 1}" activePane="bottomLeft" state="frozen"/>`
      + `<selection pane="bottomLeft" activeCell="A${freeze + 1}" sqref="A${freeze + 1}"/>`)
  }
  out.push('</sheetView></sheetViews>')
  if (widths && widths.length) {
    out.push('<cols>')
    widths.forEach((w, i) => {
      out.push(`<col min="${i + 1}" max="${i + 1}" width="${w}" customWidth="1"/>`)
    })
    out.push('</cols>')
  }
  out.push('<sheetData>')
  rows.forEach((row, ri) => {
    if (!row || !row.length) return
    const cells = []
    row.forEach((cell, ci) => {
      if (cell == null) return
      const obj = (typeof cell === 'object' && !Array.isArray(cell)) ? cell : { v: cell }
      const v = obj.v
      if (v == null || v === '') return                       // 空单元格直接不写，省体积
      const ref = colName(ci) + (ri + 1)
      const sAttr = obj.s ? ` s="${obj.s}"` : ''
      if (typeof v === 'number' && Number.isFinite(v)) {
        cells.push(`<c r="${ref}"${sAttr}><v>${v}</v></c>`)
      } else {
        cells.push(`<c r="${ref}"${sAttr} t="inlineStr"><is><t xml:space="preserve">${xesc(v)}</t></is></c>`)
      }
    })
    out.push(`<row r="${ri + 1}">${cells.join('')}</row>`)
  })
  out.push('</sheetData></worksheet>')
  return out.join('')
}

/** Excel 工作表名约束：≤31 字符、不含 : \ / ? * [ ]、首尾不能是 '、不能为空 */
export function safeSheetName(name, used) {
  let s = String(name == null ? '' : name)
    .replace(/[:\\/?*[\]]/g, '_')
    .replace(/[\r\n\t]/g, ' ')
    .replace(/^'+/, '').replace(/'+$/, '')
    .trim()
  if (!s) s = 'Sheet'
  if (s.length > 31) s = s.slice(0, 31)
  const lower = new Set((used || []).map((x) => String(x).toLowerCase()))
  if (!lower.has(s.toLowerCase())) return s
  for (let i = 2; i < 999; i++) {
    const suffix = `(${i})`
    const base = s.slice(0, 31 - suffix.length)
    const cand = base + suffix
    if (!lower.has(cand.toLowerCase())) return cand
  }
  return s.slice(0, 29) + '_' + Date.now().toString(36).slice(-2)
}

/**
 * 生成 xlsx。
 * @param {Array<{name:string, rows:Array<Array>, widths?:Array<number>, freeze?:number}>} sheets
 * @returns {Promise<Blob>}
 */
export async function buildXlsx(sheets) {
  const list = (sheets || []).filter((s) => s && Array.isArray(s.rows))
  if (!list.length) throw new Error('no sheets')

  const used = []
  const named = list.map((s) => {
    const nm = safeSheetName(s.name, used)
    used.push(nm)
    return { ...s, name: nm }
  })

  const files = []
  const push = (name, text) => files.push({ name, data: enc.encode(text) })

  let overrides = ''
  named.forEach((s, i) => {
    overrides += `<Override PartName="/xl/worksheets/sheet${i + 1}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>\n`
  })
  push('[Content_Types].xml', CONTENT_TYPES.replace('{sheets}', overrides.trim()))
  push('_rels/.rels', ROOT_RELS)

  const sheetTags = named.map((s, i) =>
    `<sheet name="${xesc(s.name)}" sheetId="${i + 1}" r:id="rId${i + 1}"/>`).join('')
  push('xl/workbook.xml', `${XML_HEAD}
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
<sheets>${sheetTags}</sheets>
</workbook>`)

  let wbRels = named.map((s, i) =>
    `<Relationship Id="rId${i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet${i + 1}.xml"/>`).join('')
  wbRels += `<Relationship Id="rId${named.length + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>`
  push('xl/_rels/workbook.xml.rels', `${XML_HEAD}
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">${wbRels}</Relationships>`)

  push('xl/styles.xml', STYLES)

  named.forEach((s, i) => push(`xl/worksheets/sheet${i + 1}.xml`, sheetXml(s.rows, s.widths, Number(s.freeze) > 0 ? Math.round(Number(s.freeze)) : 0)))

  const now = new Date().toISOString().replace(/\.\d+Z$/, 'Z')
  push('docProps/core.xml', `${XML_HEAD}
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
<dc:title>数据采集</dc:title><dc:creator>steel-carbon-twin</dc:creator>
<dcterms:created xsi:type="dcterms:W3CDTF">${now}</dcterms:created>
</cp:coreProperties>`)
  push('docProps/app.xml', `${XML_HEAD}
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
<Application>steel-carbon-twin</Application>
</Properties>`)

  const zipBytes = await zipMake(files)
  return new Blob([zipBytes], { type: MIME })
}
