// 管道材料流速解析：给 2D 工艺流程图的物料管道标注「材料流动的速率」。
//
// 数据全部由后端下发，前端只做「材料 → 计量点」映射，不生成、不模拟任何数值：
//   ① 实时遥测   store.deviceLive[devId]            ← WebSocket /api/ws/feed 推送的设备读数
//      （设备须先在「能碳一体机管理」与云端设备建立关联；未关联的设备后端不推送，即无实时值）
//   ② 仿真读数   baseline.units[].devices[].reading ← /api/simulate 返回，由后端
//      compute_device_readings 依据工序活动数据算出；①无值时兜底，保证画面不空
//   ③ 工辅工况参数 鼓风机/热风炉/引风机/供氧系统等工辅工艺在现场没有流量计，
//      取其自身运行参数（供风量/喷煤量/供氧量/抽力…），该参数即当前工况值
//
// 解析顺序：规则表逐条尝试，命中即返回 ——
//   专属计量设备直读（现场实时量测优先） → 合计计量设备 × 配比分摊 → 上游同料流管道复用
//   → 源工序工况参数 → 上游工序主产物产量（兜底，见 outFallback）
// 全部落空时返回 null，画面上该管道只显示材料名、不显示数值。
//
// 返回：{ value, unit, src: 'live' | 'sim' | 'param' | 'calc' | 'out', note } | null
//   src 用于区分数值来源（live 为现场实时读数，其余为回退值），供画面弱化显示。

import { MATERIAL_MAP, PROCESS_MAP } from '../data/flowLibrary'

const num = (v) => {
  if (v == null || v === '' || isNaN(Number(v))) return null
  return Number(v)
}
const matUnit = (m) => (MATERIAL_MAP[m] || {}).unit || ''

// 高炉炉料配比参数：合计皮带秤只测「总入炉矿量」，按配比归一到单料种。
const BURDEN_SHARE_KEYS = ['sinter_pct', 'pellet_pct', 'lump_pct']

// 具名计算式：现场无计量点、但后端有其活动数据口径的物料，按后端同一公式折算。
// 与 backend/app/devices.py compute_device_readings 的对应分支保持一致。
const CALC = {
  // 烧结机/球团燃料量（t/h）= 矿量 × 燃料比(kg/t) / 1000
  fuel_of_ore: (p) => {
    const o = num(p.ore_rate), f = num(p.fuel_rate)
    return o != null && f != null ? (o * f) / 1000 : null
  },
}

// —— 材料 → 速率解析规则表 ——
//   at   'from' | 'to'  取源工序还是去向工序的设备
//   dev  设备类型（后端 devices.py / 前端 DEVICE_TEMPLATES 的类型键）
//   kw   设备 label 关键字（同类型多台时区分，如皮带秤的「炉料」与「焦炭」）
//   share 合计计量设备的分摊参数（在 at 指定的工序 params 中，按 Σ 归一后分摊）
//   para 源工序的参数键（工辅介质：无现场流量计，取运行工况值）
//   cal  具名计算式键（见 CALC）
//   upstream 候选上游材料（沿管道反向复用上游管道的速率，如 预处理铁水 ← 铁水）
export const PIPE_RATE_RULES = {
  // —— 金属主产物：产出工序的计量设备；读数为 0（未接入/参数缺失）时依次回退 ——
  hot_metal: [{ at: 'from', dev: 'weigher' }, { para: 'hot_metal', unit: 't/h' }],
  pig_iron: [{ at: 'from', dev: 'weigher' }],
  crude_steel: [{ at: 'from', dev: 'weigher' }, { upstream: ['hot_metal', 'pre_hm'] }],
  // 精炼钢水/连铸坯：同一股钢流穿过 LF→RH→连铸，物理上就是一个流量。
  // 但 LF/RH 的「钢水秤」读数其实是各自工序的**入炉设定参数**(steel_in)回显，与上游/下游都对不上
  // （长流程 LF/RH 默认 1000、转炉出钢 385、连铸 350），直接采信会在图上出现 350→1000→350 的跳变。
  // 口径：现场实时量测 > 上游同料流管道 > 本工序设定值回显。
  refined_steel: [{ at: 'from', dev: 'weigher', liveOnly: true }, { upstream: ['refined_steel', 'crude_steel'] },
    { at: 'from', dev: 'weigher' }, { at: 'to', dev: 'weigher' }],
  billet: [{ at: 'from', dev: 'weigher', liveOnly: true }, { upstream: ['refined_steel'] },
    { at: 'from', dev: 'weigher' }, { at: 'to', dev: 'weigher' }],
  steel: [{ at: 'from', dev: 'weigher' }],
  steel_product: [{ at: 'from', dev: 'weigher' }, { upstream: ['billet'] }],
  dri: [{ at: 'from', dev: 'belt_scale' }, { at: 'from', dev: 'weigher' }],

  // —— 预处理铁水：复用上游铁水计量（预处理工序无独立计量设备）——
  pre_hm: [{ upstream: ['hot_metal', 'pre_hm'] }, { at: 'to', dev: 'weigher' }],

  // —— 炉料：高炉合计皮带秤 × 炉料配比分摊 ——
  sinter: [{ at: 'to', dev: 'belt_scale', kw: '炉料', share: 'sinter_pct' }],
  pellet: [{ at: 'to', dev: 'belt_scale', kw: '炉料', share: 'pellet_pct' }],
  iron_ore: [{ at: 'to', dev: 'belt_scale', kw: '炉料', share: 'lump_pct' }],

  // —— 燃料 / 熔剂 / 金属料 ——
  // 焦炭有两路去向：入高炉走「皮带秤·焦炭」；回供烧结机走烧结机燃料量折算（该工序无皮带秤）
  coke: [{ at: 'to', dev: 'belt_scale', kw: '焦炭' }, { at: 'to', dev: 'belt_scale' }, { at: 'to', cal: 'fuel_of_ore', unit: 't/h' }],
  limestone: [{ at: 'to', dev: 'hopper_scale' }],
  scrap: [{ at: 'to', dev: 'weigher' }],
  electrode: [{ at: 'to', dev: 'loss_in_weight' }],

  // —— 副产煤气：产出工序气体流量计 ——
  bfg: [{ at: 'from', dev: 'gas_flowmeter' }],
  ldg: [{ at: 'from', dev: 'gas_flowmeter' }],
  cog: [{ at: 'from', dev: 'gas_flowmeter' }],

  // —— 工辅介质：源工辅的运行参数（现场无流量计）——
  blast_air: [{ para: 'air_rate', unit: 'kNm³/h' }],
  combustion_air: [{ para: 'air_rate', unit: 'kNm³/h' }],
  hot_blast: [{ upstream: ['blast_air'] }, { para: 'blast_temp', unit: '℃' }],
  draft: [{ para: 'draught', unit: 'kPa' }],
  oxy_supply: [{ para: 'oxygen_rate', unit: 'kNm³/h' }],
  oxygen: [{ para: 'oxygen_rate', unit: 'kNm³/h' }, { at: 'from', dev: 'oxygen_lance' }],
  pulverized_coal: [{ para: 'inj_rate', unit: 't/h' }, { at: 'from', dev: 'injector' }],
  cool_water: [{ para: 'flow', unit: 't/h' }],
  aux_steam: [{ para: 'steam_rate', unit: 't/h' }],
  drive_power: [{ para: 'power', unit: 'MW' }],
  electrode_power: [{ para: 'power', unit: 'MW' }],
  electricity: [{ para: 'power', unit: 'MW' }, { at: 'from', dev: 'power_meter' }],
  self_power: [{ at: 'from', dev: 'power_meter' }],
  feeder_flow: [{ para: 'rate', unit: 't/h' }, { para: 'throughput', unit: 't/h' }],

  // —— 示例机房温控（dc-thermal）：冷却水侧装有水流速计，供水 / 回水两条水管道直读该流速计。
  //    流速传感器的数据源默认设为「随循环水泵变压器联动」，因此管道标注会随变压器输出电压（设定值）变化，
  //    是水泵调压调速效果最直观的观测量。——
  //    回水管道的量测点在去向工序（冷却水）上，故取 at:'to'。
  cool_water_supply: [{ at: 'from', dev: 'water_speed_sensor' }],
  cool_water_return: [{ at: 'to', dev: 'water_speed_sensor' }],
}

// 单条规则的求值。命中返回速率对象，未命中返回 null（交由下一条规则继续尝试）。
// 计量设备读数为 0 视为无效量测（设备尚未接入实时数据、或该工序参数字段缺失导致后端读数为 0），
// 继续尝试下一条规则，避免在图上显示出无意义的「0 t/h」。
function evalRule(st, conn, ctx) {
  if (st.dev) {
    const unitId = st.at === 'to' ? conn.to : conn.from
    const devs = ctx.devices(unitId)
    const d = devs.find((x) => x.type === st.dev && (!st.kw || String(x.label || '').includes(st.kw)))
    if (!d) return null
    const live = num(ctx.live(d.id))
    // liveOnly：只要现场实时读数，不看仿真回显值 —— 用于「同一股料流」上，
    // 让真实量测压过上下游工序各自的设定参数。
    if (st.liveOnly && live == null) return null
    let v = live != null ? live : num(d.reading)
    if (v == null || v === 0) return null
    // 合计计量设备：只测总量（如「皮带秤·炉料」= 总入炉矿量），按配比归一到本料种
    if (st.share) {
      const p = (ctx.unit(unitId) || {}).params || {}
      const tot = BURDEN_SHARE_KEYS.reduce((a, k) => a + (num(p[k]) || 0), 0)
      const pct = num(p[st.share])
      if (!tot || pct == null) return null
      v = (v * pct) / tot
    }
    return { value: v, unit: d.unit || st.unit || matUnit(conn.material), src: live != null ? 'live' : 'sim' }
  }
  if (st.para) {
    const p = (ctx.unit(conn.from) || {}).params || {}
    const v = num(p[st.para])
    if (v == null) return null
    return { value: v, unit: st.unit || matUnit(conn.material), src: 'param' }
  }
  if (st.cal) {
    const p = (ctx.unit(st.at === 'from' ? conn.from : conn.to) || {}).params || {}
    const v = CALC[st.cal] ? CALC[st.cal](p) : null
    if (v == null || v === 0) return null
    return { value: v, unit: st.unit || matUnit(conn.material), src: 'calc' }
  }
  if (st.upstream) {
    const up = ctx.upstream(st.upstream)
    return up ? { ...up, note: '同上游管道' } : null
  }
  return null
}

// 兜底口径：上游工序的「主产物产量」（后端 UnitResult.steel_output，t/h）——
// 该字段是后端按工序活动数据算出的主产物量（烧结矿/焦炭/铁水/钢水/DRI/钢材），
// 语义恰是「这条管道里流过的、由上游产出的物料」。
// 仅在该物料确由上游工序产出、且量纲为质量流量时适用：避免把外部来料（如外购石灰石）
// 或非质量量纲介质（供风 kNm³/h、电 MW）误标成上游产量。
function outFallback(conn, ctx) {
  if (matUnit(conn.material) !== 't/h') return null
  const f = ctx.unit(conn.from)
  const outs = (f && PROCESS_MAP[f.type] && PROCESS_MAP[f.type].outputs) || []
  if (!outs.includes(conn.material)) return null
  const v = num(ctx.out(conn.from))
  if (v == null || v === 0) return null
  return { value: v, unit: 't/h', src: 'out', note: '上游工序产量' }
}

// 解析一条管道的材料流速；ctx 由调用方（2D 视图）注入，见文件头的 getter 契约。
export function resolvePipeRate(conn, ctx) {
  const steps = PIPE_RATE_RULES[conn.material]
  if (steps) {
    for (const st of steps) {
      const r = evalRule(st, conn, ctx)
      if (r) return r
    }
  }
  return outFallback(conn, ctx)
}

// 速率数值格式化：≥100 取整（t/h 级流量不需要小数），≥10 一位小数，更小两位小数
export function formatRate(v) {
  const n = Math.abs(v)
  if (n >= 100) return v.toFixed(0)
  if (n >= 10) return v.toFixed(1)
  return v.toFixed(2)
}
