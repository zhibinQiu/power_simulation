/**
 * 统一本地 id 生成。
 *
 * 背景：uid / newId / nid / 内联 Date.now().toString(36) 五套实现散落各处，
 * 有的不带前缀、有的不保证进程内唯一（同一毫秒内连点会撞 id）。
 * 统一为「前缀 + 毫秒时间戳(base36) + 进程内自增序号(base36)」，
 * 保证同一会话内绝不重复，且从 id 本身可读出类型。
 */
let _seq = 0

/** 生成唯一 id：uid('node') -> "node_m1x2k3p4_1" */
export function uid(prefix = 'id') {
  return `${prefix}_${Date.now().toString(36)}${(_seq++).toString(36)}`
}

/** 生成带随机后缀的 id（跨会话也要唯一时用，如导出资源包、临时上传名）。 */
export function uuid(prefix = 'id') {
  const rand = Math.random().toString(36).slice(2, 8)
  return `${prefix}_${Date.now().toString(36)}${rand}`
}
