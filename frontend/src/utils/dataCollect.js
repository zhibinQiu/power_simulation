// 数据采集内核（「数据源管理 › 资源列表 › 数据采集」按钮的实际执行体）
//
// 需求：点「数据采集」→ 对当前**在线**设备发起一次采集，固定采 20 分钟，产出文件需体现
// 「当前采集的时间 / 当前采集的频率步数 / 当前采集的数值」，并**按设备分成不同的工作表**导出
// （产物是 .xlsx，见 buildCollectSheets + utils/xlsx.js）。
//
// 采集口径：**以设备真实的数据返回为驱动（edge-triggered），不按设定周期硬造时刻表。**
// 现场实测：设备标称 collectCycle 与实际返回间隔可以差十倍以上（实测 1s 标的设备真实约 3.07s、
// 5s 标的设备真实 8.6~21.7s 且间隔不均），还夹着 40~130ms 的重复推送突发。因此：
//   · 唯一的「记一步」触发条件 = 该设备**数据源时间戳向前推进**（快照的 lastOnlineTime，
//     缺失时取 twins[].timestamp 的最大值）。时间戳不动就说明设备这一步没吐新数据，不记。
//   · 步号 = 该设备在本次采集窗口内**真实收到的数据条数**（不再是 duration ÷ cycle 的理论值）。
//   · 记录时刻写**数据源时间戳**（设备侧真实返回时刻），另存接收时刻（平台侧收到时刻）便于算链路延迟。
//   · 实测频率由真实间隔算出（瞬时 1000/间隔 + 整段均值），设定周期只作为对照列。
//   · 完全没有数据源时间戳时降级为「读数变化驱动」，并在标记列写明是推定时点。
//
// 取数函数由外部注入（fetchSnapshot），本模块不碰 api/store/Vue，可用 node 直接回归。
// 记录为**长表**：一个 (设备, 测点, 步号) 一行；导出时按设备拆表，另附一张汇总表。

/** 每个设备的采集时长：20 分钟 */
export const COLLECT_DURATION_MS = 20 * 60 * 1000
/** 轮询与判重节拍。500ms ≤ 实测最小真实间隔（~3s）的 1/6，足以无漏地捕获每一次真实返回 */
export const COLLECT_TICK_MS = 500
/** 设备未配置 collectCycle 时的兜底周期（与后端 devices.py 默认值一致，仅作对照列） */
export const DEFAULT_CYCLE_MS = 1000
/** 数据源时间戳推进间隔小于此值 → 判为「同一批数据的重复推送」（实测夹带 40~130ms 突发） */
export const DUP_GAP_MS = 200

/** 毫秒 → mm:ss */
export function fmtDuration(ms) {
  const s = Math.max(0, Math.round((Number(ms) || 0) / 1000))
  const mm = Math.floor(s / 60), ss = s % 60
  return `${String(mm).padStart(2, '0')}:${String(ss).padStart(2, '0')}`
}

/** 周期(ms) → 采集频率文本（Hz，最多 3 位小数，去掉尾随 0）。传实测平均间隔即得实测频率 */
export function fmtHz(cycleMs) {
  const c = Number(cycleMs)
  if (!(c > 0)) return '—'
  const hz = 1000 / c
  return `${String(Number(hz.toFixed(3)))} Hz`
}

/** 真实间隔(ms) → 可读文本：3.07 s / 860 ms */
export function fmtGap(ms) {
  const v = Number(ms)
  if (!(v > 0)) return '—'
  return v >= 1000 ? `${(v / 1000).toFixed(2)} s` : `${Math.round(v)} ms`
}

/** 本地时刻：'YYYY-MM-DD HH:mm:ss.SSS' */
export function fmtStamp(ms) {
  const d = new Date(Number(ms) || 0)
  const p = (n, w = 2) => String(n).padStart(w, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} `
    + `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}.${p(d.getMilliseconds(), 3)}`
}

/** 采集文件名：数据采集_20260921_103045.xlsx */
export function collectFileName(startMs) {
  const d = new Date(Number(startMs) || Date.now())
  const p = (n) => String(n).padStart(2, '0')
  return `数据采集_${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}`
    + `_${p(d.getHours())}${p(d.getMinutes())}${p(d.getSeconds())}.xlsx`
}

/** 明细列（14 列，各工作表结构一致）。下标 2/7/8/9/10/11 写为数字，可直接求和/画图 */
const SHEET_COLS = ['采集日期', '采集时间', '数据源时间戳(ms)', '设备名称', '设备模型', '所属节点', '测点属性',
  '设定周期(ms)', '实测间隔(ms)', '实测频率(Hz)', '频率步号', '数值', '单位', '标记']
/** 列宽（字符数，中文按 2 计） */
const SHEET_WIDTHS = [12, 14, 17, 20, 20, 14, 18, 12, 13, 13, 10, 14, 9, 20]
/** 需要写成数字（可求和/画图）的列下标 */
const NUM_COLS = new Set([2, 7, 8, 9, 10, 11])

/** 值 → 数字或原样字符串 */
function numOrText(v) {
  if (v == null || v === '') return ''
  if (typeof v === 'number') return Number.isFinite(v) ? v : ''
  const s = String(v).trim()
  return s !== '' && Number.isFinite(Number(s)) ? Number(s) : s
}

/** 一条采集记录 → 一行 14 列 */
function recordRow(r) {
  const stamp = fmtStamp(r.ts)
  const [date, time] = stamp.split(' ')
  const gapHz = r.gap > 0 ? Number((1000 / r.gap).toFixed(4)) : ''
  const vals = [
    date, time, r.ts, r.dev, r.model, r.node, r.prop,
    r.cycleMs, r.gap || '', gapHz, r.step,
    r.value == null ? '' : r.value, r.unit || '', r.mark || '',
  ]
  return vals.map((v, i) => (NUM_COLS.has(i) ? numOrText(v) : v))
}

/** 设备聚合统计（UI / 说明行共用）：平均实测间隔、实测频率、间隔区间、重复推送数 */
export function deviceStats(d) {
  const gaps = (d && d.gaps) || []
  const real = gaps.filter((g) => g > 0 && g >= DUP_GAP_MS)
  const sum = real.reduce((a, b) => a + b, 0)
  const avgGap = real.length ? sum / real.length : 0
  return {
    steps: (d && d.steps) || 0,
    samples: gaps.length,
    avgGap,
    hz: avgGap > 0 ? 1000 / avgGap : 0,
    minGap: real.length ? Math.min(...real) : 0,
    maxGap: real.length ? Math.max(...real) : 0,
    dup: (d && d.dup) || 0,
    firstGap: (d && d.firstGap) || 0,
    cycleMs: (d && d.cycleMs) || 0,
    lastTs: (d && d.lastTs) || 0,
    mode: (d && d.mode) || 'ts',
  }
}

/** 统计 → 一行中文描述，如「实测平均间隔 3.07 s（0.326 Hz）· 区间 3.02~3.12 s · 重复推送 2 条」 */
export function fmtStatsLine(d) {
  const s = deviceStats(d)
  if (!s.steps) return '未收到数据'
  const parts = [`实测平均间隔 ${fmtGap(s.avgGap)}（${fmtHz(s.avgGap)}）`]
  if (s.minGap && s.maxGap && s.minGap !== s.maxGap) parts.push(`区间 ${fmtGap(s.minGap)}~${fmtGap(s.maxGap)}`)
  if (s.firstGap > 0) parts.push(`首条距上次返回 ${fmtGap(s.firstGap)}`)
  parts.push(`设定周期 ${s.cycleMs} ms`)
  if (s.dup) parts.push(`重复推送 ${s.dup} 条`)
  if (s.mode === 'value') parts.push('无数据源时间戳，按读数变化推定')
  return parts.join(' · ')
}

/**
 * 采集明细 → 工作表数组（xlsx 用）：第 1 张为汇总，其后每台设备一张。
 *
 * 各表结构一致：第 1 行说明、第 2 行表头、第 3 行起数据 —— 便于把单张设备表直接
 * 复制出去用，也便于在汇总表上直接做透视。
 *
 * @param {Array}  records createCollector 产出的记录数组
 * @param {Object} [meta]  附加信息（起始/结束时刻、时长、在线设备数、设备统计）
 * @returns {Array<{name:string, rows:Array, widths:Array<number>}>}
 */
export function buildCollectSheets(records, meta = {}) {
  const list = Array.isArray(records) ? records : []
  const devs = []
  const byDev = new Map()
  for (const r of list) {
    const k = r.dev || '未命名设备'
    if (!byDev.has(k)) { byDev.set(k, []); devs.push(k) }
    byDev.get(k).push(r)
  }
  const statMap = new Map(((meta.devices || [])).map((d) => [d.name, d]))

  const sheets = []
  if (meta.startedAt) {
    sheets.push({
      name: '汇总',
      widths: SHEET_WIDTHS,
      freeze: 2,
      rows: [
        [{ v: `数据采集 起始 ${fmtStamp(meta.startedAt)} 结束 ${fmtStamp(meta.endedAt)} `
          + `时长 ${fmtDuration(meta.durationMs)} 在线设备 ${meta.deviceCount || devs.length} 台 `
          + `记录 ${list.length} 条 —— 采集口径：按设备真实数据返回驱动（数据源时间戳推进即记一步，`
          + `不按设定周期补点）；「实测间隔/实测频率」由相邻两次真实返回算出，「设定周期」仅为对照。`, s: 2 }],
        SHEET_COLS.map((h) => ({ v: h, s: 1 })),
        ...list.map(recordRow),
      ],
    })
  }

  for (const name of devs) {
    const rs = byDev.get(name)
    const d0 = rs[0] || {}
    const st = statMap.get(name)
    sheets.push({
      name,
      widths: SHEET_WIDTHS,
      freeze: 2,
      rows: [
        [{ v: `设备 ${name} · 模型 ${d0.model || '—'} · 节点 ${d0.node || '—'} · `
          + `真实收到 ${rs.length} 条（${(st ? st.steps : d0.step) || d0.step} 步 × ${new Set(rs.map((r) => r.prop)).size} 测点）· `
          + `${st ? fmtStatsLine(st) : `设定周期 ${d0.cycleMs} ms`} · `
          + `首条 ${fmtStamp(d0.ts)} · 末条 ${fmtStamp((rs[rs.length - 1] || {}).ts)}`, s: 2 }],
        SHEET_COLS.map((h) => ({ v: h, s: 1 })),
        ...rs.map(recordRow),
      ],
    })
  }
  return sheets
}

/** 采集明细 → 说明文本（弹窗/提示用，不含表格） */
export function collectSummary(records, meta = {}) {
  const n = Array.isArray(records) ? records.length : 0
  const devs = new Set((records || []).map((r) => r.dev))
  return `${devs.size} 台设备 · ${n} 条记录`
}

/** epoch 秒（后端单位）→ 毫秒；已是毫秒的大数原样返回；无效返回 0 */
function toMs(v) {
  const n = Number(v)
  if (!Number.isFinite(n) || n <= 0) return 0
  return Math.round(n > 1e11 ? n : n * 1000)
}

/** 快照条目 → 该设备的数据源时间戳(ms)：优先设备级 lastOnlineTime，缺失时取 twins 最大 timestamp */
function srcTsOf(r) {
  if (!r) return 0
  const dev = toMs(r.lastOnlineTime)
  if (dev) return dev
  let max = 0
  for (const t of (r.twins || [])) {
    const v = toMs(t.timestamp)
    if (v > max) max = v
  }
  return max
}

/** 快照条目 → 读数签名（无数据源时间戳时用它判断是否有新数据） */
function sigOf(r) {
  return ((r && r.twins) || []).map((t) => `${t.propertyName}=${t.reported == null ? '' : t.reported}`).join('|')
}

/**
 * 创建一次采集任务。
 *
 * @param {Object}   o
 * @param {Function} o.fetchSnapshot  取一次快照：() => Promise<{devices:[...]}>（后端 /box/devices/realtime 结构）
 * @param {Array}    o.devices        参与采集的在线设备 [{ name, model, node, cycleMs }]
 * @param {number}   [o.durationMs]   采集时长，默认 20 分钟
 * @param {number}   [o.tickMs]       节拍，默认 500ms
 * @param {number}   [o.dupGapMs]     判重阈值，默认 200ms
 * @param {Function} [o.onUpdate]     每拍回调（含最新 state，供界面渲染）
 * @param {Function} [o.onFinish]     到时/被停后回调（reason: 'done' | 'stopped'）
 * @param {Function} [o.now]          时钟注入（测试用）
 * @returns {{ start:Function, stop:Function, state:Object, getState:Function }}
 */
export function createCollector(o = {}) {
  const {
    fetchSnapshot,
    devices = [],
    durationMs = COLLECT_DURATION_MS,
    tickMs = COLLECT_TICK_MS,
    dupGapMs = DUP_GAP_MS,
    onUpdate = () => {},
    onFinish = () => {},
    now = () => Date.now(),
  } = o

  const state = {
    running: false,
    finished: false,
    startedAt: 0,
    endedAt: 0,
    elapsed: 0,
    durationMs,
    ticks: 0,
    error: '',
    baselineReady: false,   // 首帧只作基线（避免把采集开始前的旧数据算进来）
    devices: [],
    records: [],
  }
  let timer = null
  let fetching = false

  function initDevices() {
    state.devices = devices.map((d) => ({
      name: d.name,
      model: d.model || '',
      node: d.node || '',
      // 设定周期：仅作对照列，不再用于计步
      cycleMs: Number(d.cycleMs) > 0 ? Math.round(Number(d.cycleMs)) : DEFAULT_CYCLE_MS,
      steps: 0,          // 真实收到的数据步数（= 数据源时间戳推进次数）
      gaps: [],          // 每次推进与上一次的真实间隔(ms)，首条为 0
      firstGap: 0,       // 首条距采集窗口外那次返回的间隔(ms)，只写进说明行，不参与统计
      dup: 0,            // 落入判重阈值的重复推送条数
      mode: 'ts',        // 'ts' = 数据源时间戳驱动；'value' = 无时间戳，按读数变化推定
      online: true,
      props: [],         // 最近一次快照的 twins（含读数/单位）
      tsBase: 0,         // 数据源时间戳水位线(ms)：0 = 尚未建立；只有越过它才算新数据
      baseSigSet: false, // 降级模式（无时间戳）下读数基线是否已建立
      lastTs: 0,         // 最近一条记录的时刻(ms)
      lastRecvAt: 0,     // 最近一次收到新数据的本地时刻(ms)
      lastSig: '',       // 最近一次读数签名（降级模式用）
      lastValue: null,
      lastUnit: '',
    }))
  }

  /** 快照 → 设备索引 */
  function mapOf(snap) {
    const map = new Map()
    for (const d of ((snap && snap.devices) || [])) map.set(d.name, d)
    return map
  }

  /**
   * 首帧基线：登记设备当前的数据源时间戳水位线，**不产记录**。
   * 采集开始前设备最后返回的那一笔属于窗口之外，只用来定水位线。
   */
  function applyBaseline(snap, at) {
    const map = mapOf(snap)
    for (const d of state.devices) {
      const r = map.get(d.name)
      if (!r) { d.online = false; continue }
      d.props = Array.isArray(r.twins) ? r.twins : []
      d.lastSig = sigOf(r)
      const ts = srcTsOf(r)
      d.tsBase = ts            // ts=0 表示该设备当前无可用时间戳，待后续帧出现时按 first 处理
      d.mode = ts ? 'ts' : 'value'
      d.lastTs = ts
      d.lastRecvAt = at
    }
    state.baselineReady = true
  }

  /**
   * 把快照合并进设备态：**仅当数据源时间戳越过水位线**（或降级模式下读数变化）时记一步。
   * 时间戳不动 = 该设备这一步没吐新数据 → 不补点、不硬造。
   * @returns {number} 本拍新记录的步数
   */
  function applySnapshot(snap, at) {
    const map = mapOf(snap)
    let fresh = 0
    for (const d of state.devices) {
      const r = map.get(d.name)
      if (!r) { d.online = false; continue }
      d.online = r.state === 'reporting' || d.online
      d.props = Array.isArray(r.twins) ? r.twins : []

      const ts = srcTsOf(r)
      const sig = sigOf(r)
      let isNew = false
      let mark = ''
      if (ts) {
        const first = d.tsBase === 0
        if (first || ts > d.tsBase) {
          // 首次拿到水位线时，若该数据早于采集开始（设备最后返回在窗口外）则只定线、不记；
          // 否则它本身就是采集期内的一次真实返回，照记。
          const stale = first && ts < state.startedAt
          d.tsBase = ts
          if (d.mode !== 'ts') { d.mode = 'ts'; if (!stale) mark = '恢复时间戳驱动' }
          if (!stale) isNew = true
        }
      } else {
        // 降级：该设备快照里没有可用时间戳 → 读数变化即视为新数据（时点按接收时刻推定）
        d.mode = 'value'
        if (!d.baseSigSet) { d.baseSigSet = true; d.lastSig = sig }
        else if (sig !== d.lastSig) { isNew = true; mark = '无源时间戳·按读数变化推定时点' }
      }

      if (isNew) {
        const ptTs = ts || at
        const rawGap = d.lastTs ? ptTs - d.lastTs : 0
        // 首条记录参照的是采集窗口之外的上一次返回 → 「实测间隔/实测频率」列留空，
        // 保证列口径与统计口径一致（该间隔单独记在 firstGap，只写进说明行）
        const firstRec = d.steps === 0
        if (firstRec) d.firstGap = rawGap
        const gap = firstRec ? 0 : rawGap
        const isDup = gap > 0 && gap < dupGapMs
        if (isDup) { d.dup += 1; mark = mark ? `${mark}，重复推送` : '重复推送（同一批数据）' }
        else if (gap > 0) d.gaps.push(gap)

        d.steps += 1
        d.lastTs = ptTs
        d.lastRecvAt = at
        d.lastSig = sig
        const props = d.props.length ? d.props : [{ propertyName: '', reported: null, unit: '' }]
        const first = props.find((p) => !p.invalid && p.reported != null) || props[0]
        d.lastValue = first ? first.reported : null
        d.lastUnit = (first && first.unit) || ''
        for (const p of props) {
          state.records.push({
            dev: d.name,
            model: d.model,
            node: d.node,
            prop: p.propertyName || '',
            unit: p.unit || '',
            cycleMs: d.cycleMs,   // 设定周期（对照列）
            step: d.steps,        // 真实步号
            ts: ptTs,             // 数据源时间戳（设备侧真实返回时刻）
            recvAt: at,           // 接收时刻（平台侧收到时刻）
            gap: isDup ? gap : (gap > 0 ? gap : 0),
            mark,
            value: p.reported == null || p.invalid ? null : p.reported,
          })
        }
        fresh += 1
      }
    }
    return fresh
  }

  async function tick() {
    if (!state.running) return
    const at = now()
    state.elapsed = Math.min(durationMs, at - state.startedAt)
    state.ticks += 1
    if (fetchSnapshot && !fetching) {
      fetching = true
      try {
        const snap = await fetchSnapshot()
        if (!state.baselineReady) applyBaseline(snap, at)
        else applySnapshot(snap, at)
      } catch (e) { state.error = String((e && e.message) || e) } finally { fetching = false }
    }
    if (state.elapsed >= durationMs) { finish('done'); return }
    onUpdate(state)
  }

  function finish(reason) {
    if (!state.running) return
    state.running = false
    state.finished = reason === 'done'
    state.elapsed = reason === 'done' ? durationMs : Math.min(durationMs, now() - state.startedAt)
    state.endedAt = state.startedAt + state.elapsed
    // 真实驱动无需「补足末尾整步」：设备没返回就没有那一步
    if (timer) { clearInterval(timer); timer = null }
    onUpdate(state)
    onFinish(state, reason)
  }

  return {
    state,
    getState: () => state,
    start() {
      if (state.running) return state
      initDevices()
      state.running = true
      state.finished = false
      state.baselineReady = false
      state.records = []
      state.error = ''
      state.ticks = 0
      state.startedAt = now()
      state.elapsed = 0
      state.endedAt = 0
      onUpdate(state)
      timer = setInterval(tick, tickMs)
      tick()
      return state
    },
    stop() { finish('stopped') },
  }
}
