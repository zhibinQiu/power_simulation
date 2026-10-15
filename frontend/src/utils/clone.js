/**
 * 统一深拷贝。
 *
 * 背景：全仓有 60+ 处裸 `JSON.parse(JSON.stringify(x))`，问题有三：
 *   - 语义不统一：Date 变字符串、undefined/函数/Map/Set 静默丢失；
 *   - 性能差：JSON 往返对大对象（仿真 baseline、编排 scheme）是热路径上的明显开销；
 *   - 无法统一替换策略（换实现要改 60 处）。
 *
 * 统一到 structuredClone（原生、保 Date/Map/Set），失败回退 JSON 往返
 * （含函数或不可克隆值时 structuredClone 会抛 DataCloneError）。
 */
export function clone(value) {
  if (value === null || typeof value !== 'object') return value
  if (typeof structuredClone === 'function') {
    try {
      return structuredClone(value)
    } catch {
      // 含函数 / Proxy / 不可克隆对象：回退 JSON 往返
    }
  }
  try {
    return JSON.parse(JSON.stringify(value))
  } catch {
    return value
  }
}

/** 深拷贝并合并补丁（常用于「复制一份再改几个字段」）。 */
export function cloneWith(value, patch) {
  const next = clone(value)
  if (patch && typeof next === 'object' && next !== null) Object.assign(next, patch)
  return next
}
