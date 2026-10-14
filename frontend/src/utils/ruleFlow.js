// ============ 规则编排 · 开始 / 结束模块与「通路」判定 ============
import { t } from '../i18n'
// 执行语义（用户约定）：只有「开始 → … → 结束」形成通路的流程才可以执行；
// 画布上没接进这条通路的模块只作展示，运行时不产生任何写入动作。
//
// 校验（能不能跑）与执行（实际跑哪些）共用同一套图算法，
// 避免出现「校验说可以跑、实际分支没走到」的不一致。

export const KIND_START = 'start'
export const KIND_END = 'end'

/** 设备模块（可调 / 传感）—— 对应一台真实设备 */
export function isDevKind(k) { return k === 'adj' || k === 'sen' }
/** 流程端点模块（开始 / 结束）—— 不对应任何设备 */
export function isFlowKind(k) { return k === KIND_START || k === KIND_END }

// 自动布局用的尺寸估算（与 RuleFlowEditor 的渲染常量一致，仅供排版参考）
const W_IF = 300
const W_DEV = 208
const W_FLOW = 132
const W_LOOP = 196
const H_DEV = 84
const H_FLOW = 40
const H_LOOP = 104
function estW(n) {
  if (n.kind === 'if') return W_IF
  if (n.kind === 'loop') return W_LOOP
  return isFlowKind(n.kind) ? W_FLOW : W_DEV
}
function estH(n) {
  // 头部 30 + 每条分支（首行 46 + 追加条件行每行 30）+ 底部「+ elif」28
  if (n.kind === 'if') return 30 + ((n.branches || []).reduce((s, b) => s + branchH(b), 0)) + 28
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
/** 分支判定来源：显式指定 > IF 模块的上游连线 > 无（传入的是单条条件或旧式单比较的分支） */
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

/**
 * 分支内的条件组：一条或多条「传感读数 vs 阈值」的比较，相邻两条之间由 join 连接：
 *   join = 'and' —— 并且（AND）；join = 'or' —— 或者（OR）；首条的 join 无意义。
 * 旧编排（AND / OR 曾是独立模块，IF 分支只有单一比较）里没有 conds 字段，
 * 这里把它兜底成「一条条件」，读写两端统一按数组处理。
 */
export function branchConds(b) {
  const cs = Array.isArray(b && b.conds) ? b.conds.filter((c) => c && typeof c === 'object') : []
  if (cs.length) return cs
  return [{ id: (b && b.id) || 'c0', src: (b && b.src) || '', op: (b && b.op) || '>', val: Number(b && b.val) || 0 }]
}
/** 分支渲染高度：首行 46 + 每多一条条件行 30（与 RuleFlowEditor 的 IF_BR / IF_ROW 一致） */
export function branchH(b) {
  return 46 + Math.max(0, branchConds(b).length - 1) * 30
}
/**
 * 分支是否成立：把若干条比较按「AND 优先于 OR」归约，例如
 *   x ≥ 25 并且 x < 50             → x ≥ 25 AND x < 50
 *   x < 20 或者 x ≥ 25 并且 x < 50 → x < 20 OR (x ≥ 25 AND x < 50)
 * pick(cond) 给出单条比较的真假（来源缺失、阈值未填应返回 false）。
 */
export function evalBranch(b, pick) {
  const cs = branchConds(b)
  let grp = true      // 当前 AND 组的累计值
  let or = false      // 已归约过的 OR 结果
  let any = false
  for (let i = 0; i < cs.length; i++) {
    const r = !!pick(cs[i])
    if (i > 0 && String(cs[i].join) === 'or') { or = or || grp; grp = r }
    else grp = grp && r
    any = true
  }
  return any ? (or || grp) : false
}
function nodeTitle(n) {
  if (!n) return t('模块')
  if (n.label) return n.label
  if (n.kind === 'if') return t('条件判断')
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
      // 一条分支 = 一组条件（多条时用并且 / 或者连接），整组的真假决定该分支是否命中
      if (evalBranch(b, (c) => {
        const s = srcOf(n, c, nodes, edges)
        const v = s ? liveOf(s.devId) : null
        return v != null && Number.isFinite(Number(c.val)) && cmpOp(v, c.op, c.val)
      })) { hit = b; break }
    }
    if (!hit) hit = (n.branches || []).find((b) => b.type === 'else') || null
    if (!hit) return
    onBranch(n.id + ':' + hit.id)
    for (const e of edges.filter((x) => x.from === n.id && x.port === hit.id)) advance(e, depth, visited)
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

// ============ 存量升级 ============
function newCondId() {
  return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5)
}
/**
 * 把「AND / OR 独立模块」时代的编排升级成「AND / OR 是条件内部连接词」的新形态：
 *   ① kind = 'gate' 的逻辑门 → 一个「条件判断」节点：原来的一组条件收进 if 分支内部
 *      （原来的 AND/OR 变成各条之间的 join），TRUE / FALSE 两个出口转为 if / else 分支，
 *      节点 id 保持不变，连线只需把端口 port 换成对应分支 id。
 *   ② 旧式单比较分支（src / op / val 写在分支上）→ 收成 conds 数组里的第一条。
 * 返回的 true 表示图被改写过（调用方据此落盘）。幂等，可重复调用。
 */
export function upgradeBranches(g) {
  if (!g) return false
  const ns = listOf(g, 'nodes')
  const es = listOf(g, 'edges')
  let changed = false
  for (const n of ns) {
    if (!n || n.kind !== 'gate') continue
    const op = n.op === 'or' ? 'or' : 'and'
    const old = Array.isArray(n.conds) ? n.conds.filter((c) => c && typeof c === 'object') : []
    const cs = old.map((c, i) => ({
      id: newCondId(), src: String(c.src || ''), op: c.op || '>',
      val: Number(c.val) || 0, join: i > 0 && op === 'or' ? 'or' : 'and',
    }))
    if (!cs.length) cs.push({ id: newCondId(), src: '', op: '>', val: 0, join: 'and' })
    // id 沿用模块 id + 出口后缀：连线与位置都不动，只是端口名换成分支 id
    const tId = n.id + '_t'
    const fId = n.id + '_f'
    n.kind = 'if'
    n.branches = [
      { id: tId, type: 'if', conds: cs },
      { id: fId, type: 'else' },
    ]
    delete n.conds
    delete n.op
    for (const e of es) if (e.from === n.id) e.port = e.port === 'f' ? fId : tId
    changed = true
  }
  for (const n of ns) {
    if (!n || n.kind !== 'if') continue
    for (const b of listOf(n, 'branches')) {
      if (!b || b.type === 'else') continue
      if (Array.isArray(b.conds) && b.conds.length) continue
      b.conds = [{ id: newCondId(), src: String(b.src || ''), op: b.op || '>', val: Number(b.val) || 0, join: 'and' }]
      delete b.src
      delete b.op
      delete b.val
      changed = true
    }
  }
  return changed
}
