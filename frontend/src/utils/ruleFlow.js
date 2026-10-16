// ============ 规则编排 · 开始模块与「通路」判定 ============
import { t } from '../i18n'
// 执行语义（用户约定）：只有与「开始」连通的模块才会被执行；
// 画布上没接进这条通路的模块只作展示，运行时不产生任何写入动作。
// 「结束」模块已取消：卡片不再要求接下游（条件卡片除外，它的每条分支仍要有走向）。
//
// 校验（能不能跑）与执行（实际跑哪些）共用同一套图算法，
// 避免出现「校验说可以跑、实际分支没走到」的不一致。

export const KIND_START = 'start'
/** 已取消的「结束」端点：只用于识别并清理存量编排，新编排不再产生 */
export const KIND_END = 'end'

/** 设备模块（可调 / 传感）—— 对应一台真实设备 */
export function isDevKind(k) { return k === 'adj' || k === 'sen' }
/** 流程端点模块（开始）—— 不对应任何设备 */
export function isFlowKind(k) { return k === KIND_START }

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
  return n.kind === KIND_START || n.kind === KIND_END ? W_FLOW : W_DEV
}
function estH(n) {
  // 头部 30 + 每条分支（首行 46 + 追加条件行每行 30）+ 底部「+ elif」28
  if (n.kind === 'if') return 30 + ((n.branches || []).reduce((s, b) => s + branchH(b), 0)) + 28
  if (n.kind === 'loop') return H_LOOP
  return n.kind === KIND_START || n.kind === KIND_END ? H_FLOW : H_DEV
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
 * 通路分析（结束模块已取消，通路口径 = 与「开始」连通）：
 *   starts —— 「开始」模块 id
 *   fwd    —— 从任一「开始」可达的节点（含开始自身）
 *   live   —— 同 fwd：与「开始」连通的那部分，才是运行时会走到的
 *   lost   —— 与「开始」之间没有通路的模块 id（孤立卡片，运行时不执行）
 *   ok     —— 有「开始」、有卡片、且没有孤立卡片（决定能否运行）
 */
export function flowPath(g) {
  const nodes = listOf(g, 'nodes')
  const out = outMap(g)
  const starts = nodes.filter((n) => n && n.kind === KIND_START).map((n) => n.id)
  const fwd = walk(starts, (id) => out.get(id))
  // 「卡片」= 除流程端点（开始）以外的模块；遗留的「结束」节点不计入孤立判定（由迁移清理）
  const cards = nodes.filter((n) => n && n.id && n.kind !== KIND_START && n.kind !== KIND_END)
  const lost = cards.filter((n) => !fwd.has(n.id)).map((n) => n.id)
  const ok = starts.length > 0 && cards.length > 0 && lost.length === 0
  return { starts, fwd, live: fwd, lost, ok }
}

/** 每张卡片都与「开始」连通（规则模型能否运行的判据） */
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

  function advance(e, depth, visited) {
    if (depth > 24) return
    const tgt = nodes.find((x) => x.id === e.to)
    if (!tgt || !fp.live.has(tgt.id)) return
    activeEdges.add(e.id)
    activeNodes.add(tgt.id)
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
  return { ok: fp.ok, acts, activeNodes, activeEdges, branch }
}

/** 清理已取消的「结束」端点及其连线（就地删，兼容响应式数组） */
function stripEnds(g) {
  const ends = new Set()
  for (const n of listOf(g, 'nodes')) if (n && n.kind === KIND_END && n.id) ends.add(n.id)
  if (!ends.size) return false
  for (let i = g.nodes.length - 1; i >= 0; i--) {
    const n = g.nodes[i]
    if (n && n.kind === KIND_END) g.nodes.splice(i, 1)
  }
  for (let i = g.edges.length - 1; i >= 0; i--) {
    const e = g.edges[i]
    if (e && (ends.has(e.from) || ends.has(e.to))) g.edges.splice(i, 1)
  }
  return true
}

/**
 * 存量迁移 + 端点补齐（幂等）：
 *   ① 删除已取消的「结束」端点及其连线（老编排里它只是个标记，去掉后链路照旧）；
 *   ② 没有「开始」时补一个（落在内容左侧）；
 *   ③ 把没有上游的卡片接到「开始」—— 出口可连多个下游，散落的卡片一律并列挂在开始之后。
 * 新口径下「卡片必须与开始连通」，这样迁移完的旧编排立刻就是可运行状态。
 * 返回 true 表示图被改动过（调用方据此落盘）。
 */
export function ensureFlowStart(g) {
  if (!g) return false
  if (!Array.isArray(g.nodes)) g.nodes = []
  if (!Array.isArray(g.edges)) g.edges = []
  const n0 = g.nodes.length + g.edges.length
  stripEnds(g)

  const body = g.nodes.filter((n) => n && n.kind !== KIND_START)
  let x0 = 40, yMid = 200
  if (body.length) {
    let minX = Infinity, minY = Infinity, maxY = -Infinity
    for (const n of body) {
      const nx = Number(n.x) || 0
      const ny = Number(n.y) || 0
      minX = Math.min(minX, nx)
      minY = Math.min(minY, ny); maxY = Math.max(maxY, ny + estH(n))
    }
    // 不夹到 12：画布支持负坐标（往左 / 上自由布局），内容整体在负区间时「开始」应落在它的左侧
    x0 = minX - 180
    yMid = Math.round((minY + maxY) / 2 - H_FLOW / 2)
  }
  let added = false
  if (!g.nodes.some((n) => n && n.kind === KIND_START)) {
    g.nodes.push({ id: newId(KIND_START), kind: KIND_START, x: Math.round(x0), y: yMid })
    added = true
  }
  // 只在这次「补齐端点」时接一次线：已有「开始」的编排一律不动，
  // 否则用户刻意留出的未连通卡片会被悄悄接上，校验就永远提示不出来了。
  if (added) {
    const start = g.nodes.find((n) => n && n.kind === KIND_START)
    const inn = inMap(g)
    if (start) {
      for (const n of body) {
        if (!(inn.get(n.id) || []).length) g.edges.push(newEdge(start.id, 'out', n.id))
      }
    }
  }
  return g.nodes.length + g.edges.length !== n0
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
