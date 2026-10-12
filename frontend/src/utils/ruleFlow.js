// ============ 规则编排 · 开始 / 结束模块与「通路」判定 ============
import { t } from '../i18n'
// 执行语义（用户约定）：只有「开始 → … → 结束」形成通路的流程才可以执行；
// 画布上没接进这条通路的模块只作展示，运行时不产生任何写入动作。
//
// 校验（能不能跑）与执行（实际跑哪些）共用同一套图算法，
// 避免出现「校验说可以跑、实际分支没走到」的不一致。

export const KIND_START = 'start'
export const KIND_END = 'end'
/** 逻辑门模块（AND / OR）：把若干条「传感读数 vs 阈值」的判定归约成一个真 / 假出口 */
export const KIND_GATE = 'gate'

/** 设备模块（可调 / 传感）—— 对应一台真实设备 */
export function isDevKind(k) { return k === 'adj' || k === 'sen' }
/** 流程端点模块（开始 / 结束）—— 不对应任何设备 */
export function isFlowKind(k) { return k === KIND_START || k === KIND_END }
/** 逻辑门模块（and / or） */
export function isGateKind(k) { return k === KIND_GATE }

// 自动布局用的尺寸估算（与 RuleFlowEditor 的渲染常量一致，仅供排版参考）
const W_IF = 300
const W_GATE = 300
const W_DEV = 208
const W_FLOW = 132
const W_LOOP = 196
const H_DEV = 84
const H_FLOW = 40
const H_LOOP = 104
function estW(n) {
  if (n.kind === 'if') return W_IF
  if (n.kind === 'gate') return W_GATE
  if (n.kind === 'loop') return W_LOOP
  return isFlowKind(n.kind) ? W_FLOW : W_DEV
}
function estH(n) {
  if (n.kind === 'if') return 30 + ((n.branches || []).length) * 46 + 28
  // 逻辑门：头部 30 + 每条条件 30 + 「+ 条件」28 + 真 / 假 两条出口各 46
  if (n.kind === 'gate') return 30 + ((n.conds || []).length) * 30 + 28 + 92
  if (n.kind === 'loop') return H_LOOP
  return isFlowKind(n.kind) ? H_FLOW : H_DEV
}

function listOf(g, key) { return Array.isArray(g && g[key]) ? g[key] : [] }
function newId(p) {
  return p + '_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5)
}
function newEdge(from, port, to) {
  return { id: 'e' + Math.random().toString(36).slice(2, 8), from, port: port || 'out', to }
}

/** 邻接表：节点 id → 下游 id[]（IF 的每条分支都算一条出边，静态判定一律视为可通行） */
function outMap(g) {
  const byId = new Set()
  for (const n of listOf(g, 'nodes')) if (n && n.id) byId.add(n.id)
  const m = new Map()
  for (const e of listOf(g, 'edges')) {
    if (!e || !byId.has(e.from) || !byId.has(e.to)) continue
    if (!m.has(e.from)) m.set(e.from, [])
    const arr = m.get(e.from)
    if (!arr.includes(e.to)) arr.push(e.to)
  }
  return m
}
/** 反向邻接：节点 id → 上游 id[] */
function inMap(g) {
  const byId = new Set()
  for (const n of listOf(g, 'nodes')) if (n && n.id) byId.add(n.id)
  const m = new Map()
  for (const e of listOf(g, 'edges')) {
    if (!e || !byId.has(e.from) || !byId.has(e.to)) continue
    if (!m.has(e.to)) m.set(e.to, [])
    const arr = m.get(e.to)
    if (!arr.includes(e.from)) arr.push(e.from)
  }
  return m
}
/** 从 seeds 出发沿 next 闭包走到底，返回访问过的 id 集合 */
function walk(seeds, next) {
  const seen = new Set()
  const st = seeds.slice()
  while (st.length) {
    const id = st.pop()
    if (seen.has(id)) continue
    seen.add(id)
    for (const t of next(id) || []) if (!seen.has(t)) st.push(t)
  }
  return seen
}

/**
 * 通路分析：
 *   starts / ends —— 端点模块 id
 *   fwd  —— 从任一「开始」可达的节点
 *   rev  —— 能走到任一「结束」的节点
 *   live —— 既从开始可达、又能走到结束的节点（= 真正会执行的那部分流程）
 *   ok   —— 是否存在「开始 → … → 结束」通路（决定能否运行）
 */
export function flowPath(g) {
  const nodes = listOf(g, 'nodes')
  const out = outMap(g)
  const inn = inMap(g)
  const starts = nodes.filter((n) => n && n.kind === KIND_START).map((n) => n.id)
  const ends = nodes.filter((n) => n && n.kind === KIND_END).map((n) => n.id)
  const fwd = walk(starts, (id) => out.get(id))
  const rev = walk(ends, (id) => inn.get(id))
  const live = new Set()
  for (const id of fwd) if (rev.has(id)) live.add(id)
  const ok = ends.some((id) => fwd.has(id))
  return { starts, ends, fwd, rev, live, ok }
}

/** 是否存在「开始 → … → 结束」通路（规则模型能否运行的判据） */
export function hasFlowPath(g) { return flowPath(g).ok }

// ============ 规则执行器（纯函数） ============
// 与通路判定同源：只有落在「开始 → … → 结束」通路上的模块才会执行。
// 画布（编辑 / 手动执行）与全局运行器（sim store，运行态策略在后台按周期跑）共用本函数，
// 避免两处各写一套执行逻辑导致「画布预览与后台执行结果不一致」。

function fmtVal(v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  const a = Math.abs(n)
  return n.toLocaleString('zh-CN', { maximumFractionDigits: a >= 1000 ? 0 : a >= 10 ? 1 : 2 })
}
function loopTimesOf(n) {
  const v = Math.round(Number(n && n.times))
  return Number.isFinite(v) ? Math.min(999, Math.max(1, v)) : 1
}
function loopGapOf(n) {
  const v = Number(n && n.gap)
  return Number.isFinite(v) ? Math.min(3600, Math.max(0, v)) : 0
}
function cmpOp(a, op, b) {
  const x = Number(a)
  const y = Number(b)
  if (!Number.isFinite(x) || !Number.isFinite(y)) return false
  switch (op) {
    case '>': return x > y
    case '>=': return x >= y
    case '<': return x < y
    case '<=': return x <= y
    case '==': return Math.abs(x - y) < 1e-9
    case '!=': return Math.abs(x - y) >= 1e-9
    default: return false
  }
}
/** 分支判定来源：显式指定 > IF 模块的上游连线 > 无 */
function srcOf(n, b, nodes, edges) {
  if (b && b.src) {
    const x = nodes.find((k) => k.id === b.src)
    if (x && x.kind !== 'if') return x
  }
  const e = edges.find((x) => x.to === n.id)
  if (!e) return null
  const s = nodes.find((x) => x.id === e.from)
  return s && s.kind !== 'if' ? s : null
}
/** 逻辑门条件来源：显式指定 > 上游连线 > 无（逻辑门不能再作为来源） */
function condOf(n, c, nodes, edges) {
  if (c && c.src) {
    const x = nodes.find((k) => k.id === c.src)
    if (x && !isGateKind(x.kind) && x.kind !== 'if') return x
  }
  const e = edges.find((x) => x.to === n.id)
  if (!e) return null
  const s = nodes.find((x) => x.id === e.from)
  return s && !isGateKind(s.kind) && s.kind !== 'if' ? s : null
}
function nodeTitle(n) {
  if (!n) return t('模块')
  if (n.label) return n.label
  if (n.kind === 'if') return t('条件判断')
  if (isGateKind(n.kind)) return `${n.op === 'or' ? 'OR' : 'AND'} · ${t('逻辑')}`
  if (n.kind === 'loop') return t('循环模块')
  if (n.kind === KIND_START) return t('开始')
  if (n.kind === KIND_END) return t('结束')
  return t('模块')
}

/**
 * 执行一遍规则图。
 * @param graph {nodes, edges}
 * @param ctx   { liveOf(devId), boundOf(node), state }
 *   state —— 跨轮次状态（循环模块的挂起轮次），由调用方持有：后台运行器存自己的一份，
 *            画布手动执行时传临时对象即可。
 * @returns { ok, acts, activeNodes:Set, activeEdges:Set, branch }
 *   acts[i].write —— true 表示需要写入设定值（可调模块），由调用方决定如何下发。
 */
export function evalFlowGraph(graph, ctx) {
  const c = ctx || {}
  const nodes = listOf(graph, 'nodes')
  const edges = listOf(graph, 'edges')
  const liveOf = typeof c.liveOf === 'function' ? c.liveOf : () => null
  const boundOf = typeof c.boundOf === 'function' ? c.boundOf : () => null
  const state = c.state || {}
  if (!Array.isArray(state.pendLoops)) state.pendLoops = []

  const fp = flowPath(graph)
  const activeNodes = new Set()
  const activeEdges = new Set()
  const acts = []
  let branch = ''
  const onBranch = (v) => { if (!branch) branch = v }

  // 没有「开始 → … → 结束」通路：整条流程不执行（也就不产生任何写入）
  if (!fp.ok) {
    state.pendLoops = []
    return { ok: false, acts, activeNodes, activeEdges, branch: '' }
  }

  function advance(e, depth, visited) {
    if (depth > 24) return
    const tgt = nodes.find((x) => x.id === e.to)
    if (!tgt || !fp.live.has(tgt.id)) return
    activeEdges.add(e.id)
    activeNodes.add(tgt.id)
    if (tgt.kind === KIND_END) return
    if (tgt.kind === 'if') { evalIf(tgt, depth, visited); return }
    if (isGateKind(tgt.kind)) { evalGate(tgt, depth, visited); return }
    if (tgt.kind === 'loop') { evalLoop(tgt, depth, visited); return }
    if (!isDevKind(tgt.kind)) return
    if (tgt.kind === 'adj') {
      const v = Number(tgt.value)
      if (Number.isFinite(v)) {
        const b = boundOf(tgt)
        const tail = b ? ` · ${t('下发')} ${b.device}.${b.prop}` : ` · ${t('仅仿真')}`
        acts.push({
          write: true, devId: tgt.devId, nodeId: tgt.id, value: v,
          txt: `${nodeTitle(tgt)} ← ${t('写入')} ${fmtVal(v)}${tgt.unit || ''}${tail}`,
        })
      }
    } else {
      acts.push({ write: false, devId: tgt.devId, nodeId: tgt.id, txt: `${nodeTitle(tgt)}（${t('仅观测，不写入')}）` })
    }
    for (const nx of edges.filter((x) => x.from === tgt.id)) advance(nx, depth + 1, visited)
  }

  function evalIf(n, depth, visited) {
    if (depth > 8 || visited.has(n.id)) return
    visited.add(n.id)
    let hit = null
    for (const b of n.branches || []) {
      if (b.type === 'else') continue
      const s = srcOf(n, b, nodes, edges)
      const v = s ? liveOf(s.devId) : null
      if (v != null && cmpOp(v, b.op, b.val)) { hit = b; break }
    }
    if (!hit) hit = (n.branches || []).find((b) => b.type === 'else') || null
    if (!hit) return
    onBranch(n.id + ':' + hit.id)
    for (const e of edges.filter((x) => x.from === n.id && x.port === hit.id)) advance(e, depth, visited)
  }

  function evalGate(n, depth, visited) {
    if (depth > 8 || visited.has(n.id)) return
    visited.add(n.id)
    const or = n.op === 'or'
    let ok = !or
    let any = false
    for (const cc of n.conds || []) {
      const s = condOf(n, cc, nodes, edges)
      const v = s ? liveOf(s.devId) : null
      if (v == null || !Number.isFinite(Number(cc.val))) continue
      any = true
      const r = cmpOp(v, cc.op, cc.val)
      if (or) { if (r) { ok = true; break } }
      else if (!r) { ok = false; break }
    }
    const hitId = ok && any ? 't' : 'f'
    onBranch(n.id + ':' + hitId)
    acts.push({ write: false, nodeId: n.id, txt: `${nodeTitle(n)} → ${hitId === 't' ? t('满足') : t('不满足')}` })
    for (const e of edges.filter((x) => x.from === n.id && x.port === hitId)) advance(e, depth, visited)
  }

  function evalLoop(n, depth, visited) {
    if (depth > 8 || visited.has(n.id)) return
    const times = loopTimesOf(n)
    const gap = loopGapOf(n)
    const seal = new Set(visited)
    seal.add(n.id)
    // 新一轮开始：清掉该模块旧的挂起轮次，避免主流程重复命中后越排越多
    state.pendLoops = state.pendLoops.filter((q) => q.nodeId !== n.id)
    for (let i = 1; i <= times; i++) {
      if (i > 1 && gap > 0) {
        state.pendLoops.push({ at: Date.now() + gap * 1000, nodeId: n.id, round: i, total: times, gap })
        break
      }
      acts.push({ write: false, nodeId: n.id, txt: `${nodeTitle(n)} · ${t('第 {i}/{n} 轮', { i, n: times })}` })
      for (const e of edges.filter((x) => x.from === n.id)) advance(e, depth + 1, new Set(seal))
    }
  }

  // ① 到期的挂起轮次（循环模块「每轮间隔 > 0」时排在之后的 tick 执行）
  const now = Date.now()
  const due = []
  const rest = []
  for (const q of state.pendLoops) {
    if (Number(q.at) <= now) due.push(q)
    else rest.push(q)
  }
  state.pendLoops = rest
  for (const q of due) {
    const n = nodes.find((x) => x.id === q.nodeId)
    if (!n || !fp.live.has(n.id)) continue
    activeNodes.add(n.id)
    acts.push({ write: false, nodeId: n.id, txt: `${nodeTitle(n)} · ${t('第 {i}/{n} 轮', { i: q.round, n: q.total })}` })
    for (const e of edges.filter((x) => x.from === n.id)) advance(e, 1, new Set([n.id]))
    if (q.round < q.total) state.pendLoops.push({ ...q, at: Date.now() + q.gap * 1000, round: q.round + 1 })
  }
  // ② 主流程：从每个「开始」出发沿通路推进
  const visited = new Set()
  for (const id of fp.starts) {
    activeNodes.add(id)
    for (const e of edges.filter((x) => x.from === id)) advance(e, 0, visited)
  }
  return { ok: true, acts, activeNodes, activeEdges, branch }
}

/**
 * 给存量编排补齐「开始 / 结束」端点，并把断开的两端自动接上：
 *   无上游的模块 ← 开始（开始只有一个出口，接第一个即可）
 *   无下游的模块 → 结束（结束可汇聚多条）
 * 返回 true 表示图被改动过（调用方据此落盘）。
 */
export function ensureFlowEnds(g) {
  if (!g) return false
  if (!Array.isArray(g.nodes)) g.nodes = []
  if (!Array.isArray(g.edges)) g.edges = []
  let changed = false

  const body = g.nodes.filter((n) => n && !isFlowKind(n.kind))
  let x0 = 40, x1 = 760, yMid = 200
  if (body.length) {
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity
    for (const n of body) {
      const nx = Number(n.x) || 0
      const ny = Number(n.y) || 0
      minX = Math.min(minX, nx); maxX = Math.max(maxX, nx + estW(n))
      minY = Math.min(minY, ny); maxY = Math.max(maxY, ny + estH(n))
    }
    // 不夹到 12：画布支持负坐标（往左 / 上自由布局），内容整体在负区间时「开始」应落在它的左侧
    x0 = minX - 180
    x1 = maxX + 180
    yMid = Math.round((minY + maxY) / 2 - H_FLOW / 2)
  }
  if (!g.nodes.some((n) => n && n.kind === KIND_START)) {
    g.nodes.push({ id: newId(KIND_START), kind: KIND_START, x: Math.round(x0), y: yMid })
    changed = true
  }
  if (!g.nodes.some((n) => n && n.kind === KIND_END)) {
    g.nodes.push({ id: newId(KIND_END), kind: KIND_END, x: Math.round(x1), y: yMid })
    changed = true
  }
  // 只在本次「补齐端点」时接一次线，已有端点的编排不动，避免反复改用户的连法
  if (!changed) return false

  const start = g.nodes.find((n) => n && n.kind === KIND_START)
  const end = g.nodes.find((n) => n && n.kind === KIND_END)
  const inn = inMap(g)
  const out = outMap(g)
  if (start) {
    const root = body.find((n) => (inn.get(n.id) || []).length === 0)
    if (root) g.edges.push(newEdge(start.id, 'out', root.id))
  }
  if (end) {
    for (const n of body) {
      if ((out.get(n.id) || []).length === 0) g.edges.push(newEdge(n.id, 'out', end.id))
    }
  }
  return true
}
