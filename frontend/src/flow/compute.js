// 方案工程估算：物料平衡 + 经验碳因子。反馈边（自发电）抵扣外购电。
// 用于编辑态右栏预估、顶栏 KPI；退出编辑时由后端 simulate 做精确重算。
//
// 实时联动：此处接入「排放因子配置」(factors.fuels 的 NCV/CC) 与物料隐含碳因子
// (materialOverrides 中的外购电/绿电/自发电)，使编辑态右栏碳排预估随因子改动即时变化。
import { PROCESS_MAP, DEVICE_MAP, DEVICE_COUPLE_REGISTRY, deriveProcessOpParams } from '../data/flowLibrary'

// 默认电力碳因子（无覆盖/无 factors 时的回退，与 MATERIAL_MAP 隐含因子一致）
const DEF_GRID = 0.5703   // 外购电 tCO₂/MWh（2022 年全国电力平均 CO₂ 排放因子）
const DEF_SELF = 0.18     // 自发电 tCO₂/MWh
const DEF_GREEN = 0.02    // 绿电 tCO₂/MWh

// 各工艺主产物质量（t/h 或 MWh/h 能源），按模板参数估算
function outMassOf(node) {
  const p = node.params || {}
  const t = PROCESS_MAP[node.type]
  if (!t) return 0
  switch (node.type) {
    case 'sinter_plant': return (p.ore_rate || 0) * t.yield
    case 'pelletizing': return (p.ore_rate || 0) * t.yield
    case 'coke_oven': return (p.coal_rate || 0) * t.yield
    case 'blast_furnace': return p.hot_metal || 0
    case 'hot_metal_pretreat': return p.hm_rate || 0
    case 'bof': return (p.hot_metal_in || 0) * t.yield
    case 'ladle_furnace': return (p.steel_in || 0) * t.yield
    case 'rh_vacuum': return (p.steel_in || 0) * t.yield
    case 'caster': return (p.steel_in || 0) * t.yield
    case 'rolling_mill': return (p.steel_in || 0) * t.yield
    case 'eaf': return ((p.scrap || 0) + (p.dri || 0)) * t.yield
    case 'gas_power': return (p.gas_in || 0) * 3.0   // kNm³/h → MWh/h 近似
    case 'waste_heat': return (p.heat_in || 0) * 0.278 // GJ/h → MWh/h
    case 'ccs': return 0
    default: {
      const k = (t.params && t.params[0] && t.params[0].key) || null
      return k ? (p[k] || 0) * (t.yield || 1) : 0
    }
  }
}

// 燃料燃烧排放（tCO₂/h）：依据工艺参数估算燃料用量 × NCV × CC × 3.667。
// fuels 来自 factors.fuels（含 ncv / cc / unit）。用于让 NCV/CC 改动实时影响估算。
function fuelCombustion(node, fuels) {
  if (!fuels) return 0
  const p = node.params || {}
  const om = outMassOf(node)
  const I = (key) => {
    const f = fuels[key]
    if (!f || f.ncv == null || f.cc == null) return 0
    return f.ncv * f.cc * 3.667   // tCO₂/燃料单位（固体= t，气体= 万Nm³）
  }
  let c = 0
  switch (node.type) {
    case 'blast_furnace': {
      // 操作参数(风量/风温/富氧/抽力) → 焦比/煤比，与后端 calc_bf 一致；否则直接调参
      let coke = p.coke_rate != null ? p.coke_rate : 470
      let coal = p.coal_inj != null ? p.coal_inj : 150
      const wind = p.wind_rate, tB = p.hot_blast_temp, o2 = p.oxygen_enrich, draft = p.draft
      if (wind != null || tB != null || o2 != null || draft != null) {
        const windF = wind != null ? wind : 1.0
        const tempF = tB != null ? tB / 1250 : 1.0
        const oxyF = o2 != null ? 1.0 + o2 / 21 : 1.0
        const draftF = draft != null ? draft : 1.0
        const dCoke = -150 * (windF - 1) - 250 * (tempF - 1) - 90 * (oxyF - 1) - 30 * (draftF - 1)
        coke = Math.max(300, Math.min(560, coke + dCoke))
        const total = (p.coke_rate != null ? p.coke_rate : 470) + (p.coal_inj != null ? p.coal_inj : 150)
          - 20 * (windF - 1) - 15 * (tempF - 1) - 10 * (oxyF - 1) - 8 * (draftF - 1)
        coal = Math.max(0, Math.min(260, total - coke))
      }
      c += om * coke / 1000 * I('coke')
      c += om * coal / 1000 * I('coal')
      break
    }
    case 'coke_oven':
      c += (p.coal_rate || 0) * I('coal')   // 入炉煤 t/h
      break
    case 'sinter_plant':
    case 'pelletizing':
      c += (p.ore_rate || 0) * (p.fuel_rate || 0) / 1000 * I('coal')  // 固体燃料 t/h
      break
    case 'rolling_mill':
    case 'reheating_furnace':
      // 天然气 m³/t → 万Nm³/h
      c += (p.steel_in || 0) * (p.ng_rate || 0) / 10000 * I('ng')
      break
    default:
      break
  }
  return c
}

// 该工序是否接入绿电（画布中存在指向它的 green_power 物料连线）
function isGreenPowered(nodeId, scheme) {
  if (!scheme || !scheme.connections) return false
  return scheme.connections.some((c) => c.to === nodeId && c.material === 'green_power')
}

const num = (v, d) => (v == null || isNaN(Number(v)) ? d : Number(v))

export function computeScheme(scheme, factors, factorsDefault, overrides) {
  const nodes = scheme.nodes || []
  const devices = scheme.devices || []
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]))
  const result = { nodes: {}, totals: { co2_total: 0, co2_direct: 0, co2_indirect: 0, energy: 0, steel_output: 0, intensity: 0, captured: 0 } }

  // 电力碳因子（实时）：外购电/绿电/自发电优先取物料覆盖值，其次 factors.grid_ef，再回退默认值
  const ov = overrides || {}
  const gridFactor = num(ov.electricity != null ? ov.electricity.carbon : null, num(factors && factors.grid_ef != null ? factors.grid_ef : null, DEF_GRID))
  const selfFactor = num(ov.self_power != null ? ov.self_power.carbon : null, DEF_SELF)
  const greenFactor = num(ov.green_power != null ? ov.green_power.carbon : null, DEF_GREEN)

  // 燃料因子：编辑态用实时值，默认态用 factorsDefault（保证未编辑时基线不变）
  const liveFuels = factors && factors.fuels ? factors.fuels : null
  const defFuels = (factorsDefault && factorsDefault.fuels) ? factorsDefault.fuels
    : (liveFuels || null)   // 缺省默认时退化为实时值（偏移为 0，不影响基线）

  let totalDirect = 0
  let totalElec = 0       // 工艺外购/绿电需求（MWh/h）
  let greenElec = 0       // 其中由绿电直供的部分
  let producedPower = 0  // 自发电（MWh/h）
  let deviceEnergy = 0   // 设备电耗（MWh/h）
  let steelOut = 0
  let captured = 0

  // 设备节点：电耗 + 对绑定工艺的减排修正
  const deviceSavings = {} // processNodeId -> 减排系数（仅未建模设备的通用 5% 软假设）
  const deviceOpParams = {} // processNodeId -> 由注册表推导的工序参数覆盖（真实耦合）
  const nodeById = Object.fromEntries(nodes.map((n) => [n.id, n]))
  // 工辅驱动连线折算：鼓风机→高炉(wind_rate)、热风炉→(hot_blast_temp) 等。
  // 连线存在时，工辅自身的运行参数写入被服务工艺目标参数（与 compileSchemeToModel 一致）。
  const driveOpParams = {}
  for (const c of (scheme.connections || [])) {
    const f = nodeById[c.from], t = nodeById[c.to]
    if (!f || !t) continue
    const ft = PROCESS_MAP[f.type]
    if (!ft || ft.route !== 'aux' || !ft.drives) continue
    const drive = ft.drives[c.material]
    if (!drive) continue
    const srcVal = (f.params && f.params[drive.src] != null) ? Number(f.params[drive.src]) : null
    if (srcVal == null) continue
    // 驱动连线：工辅供给绝对量直接写入同量纲目标参数（如 鼓风量 kNm³/h → 高炉风量 kNm³/h）
    driveOpParams[c.to] = Object.assign(driveOpParams[c.to] || {}, { [drive.dst]: srcVal })
  }
  for (const d of devices) {
    if (d.kind === 'device' && d.metering) continue
    const dt = DEVICE_MAP[d.type]
    if (!dt) continue
    if (dt.setpoint && d.setpoint != null && dt.powerPerUnit) {
      deviceEnergy += Math.abs(d.setpoint) * dt.powerPerUnit
    }
    // 附加可调项（如鼓风机喷氧量）同样计入运行电耗
    if (dt.extraSetpoints && d.extraSetpoints && typeof d.extraSetpoints === 'object') {
      for (const es of dt.extraSetpoints) {
        const v = d.extraSetpoints[es.key]
        if (v != null && es.powerPerUnit) deviceEnergy += Math.abs(Number(v)) * es.powerPerUnit
      }
    }
    if (!d.boundTo) continue
    const node = nodeById[d.boundTo]
    if (!node) continue
    // 注册表已建模的设备 -> 推导工序参数覆盖（不走通用 5%，避免双重核算）
    const reg = DEVICE_COUPLE_REGISTRY[node.type]
    if (reg && reg[d.type] && d.setpoint != null) {
      const ov = deriveProcessOpParams(node.type, [{ type: d.type, setpoint: d.setpoint, extraSetpoints: d.extraSetpoints || {} }], node.params || {})
      deviceOpParams[d.boundTo] = Object.assign(deviceOpParams[d.boundTo] || {}, ov)
      continue
    }
    if (dt.effType && dt.effType !== 'none') {
      deviceSavings[d.boundTo] = Math.min(deviceSavings[d.boundTo] || 0, 0.05) // 最多降 5% 直接排放
    }
  }

  for (const n of nodes) {
    const t = PROCESS_MAP[n.type]
    if (!t) { result.nodes[n.id] = { co2: 0, energy: 0, outMass: 0, heat: 0 }; continue }
    // 工辅：自身不产碳，仅耗电（由各设备功率参数折算为范围二电耗）。
    // 其"驱动介质"输出经连线折算到被服务工艺参数，自身不计入钢产量/直接排放。
    if (t.route === 'aux') {
      const p = n.params || {}
      // 工辅电耗 = 电机功率(MW)；其它字段为被服务工艺运行工况，碳在本工艺不计
      let power = (typeof p.power === 'number') ? p.power : 0
      // 绿电占比抵扣外购电（仅 drive_supply 等带 green_ratio 者生效）
      if (typeof p.green_ratio === 'number') power = power * (1 - p.green_ratio / 100)
      deviceEnergy += power
      result.nodes[n.id] = { co2: power * gridFactor, energy: power, outMass: 0, heat: 0, aux: true }
      continue
    }
    // 设备推导的操作参数注入（被绑定的高炉等）+ 工辅驱动连线折算，驱动 calc_bf 操作模式
    const mergedParams = { ...n.params, ...(deviceOpParams[n.id] || {}), ...(driveOpParams[n.id] || {}) }
    const effNode = (deviceOpParams[n.id] || driveOpParams[n.id]) ? { ...n, params: mergedParams } : n
    const outMass = outMassOf(effNode)
    let efDirect = t.efDirect
    if (deviceSavings[n.id]) efDirect *= (1 - deviceSavings[n.id])

    // 直接排放 = 经验直接排放 + (编辑态燃料燃烧 − 默认燃料燃烧)，未编辑时偏移为 0
    const editedC = fuelCombustion(effNode, liveFuels)
    const defaultC = fuelCombustion(effNode, defFuels)
    let direct = outMass * efDirect + (editedC - defaultC)
    if (direct < 0) direct = 0

    // 间接（电）：该工序是否接入绿电决定采用绿电/外购电因子
    let elec = 0
    if (n.params && n.params.electricity != null) elec = n.params.electricity
    else elec = outMass * t.efIndirect

    const green = isGreenPowered(n.id, scheme)
    const ef = green ? greenFactor : gridFactor

    if (n.type === 'gas_power' || n.type === 'waste_heat') {
      producedPower += outMass // outMass 即自发电 MWh/h
    } else if (n.type === 'ccs') {
      // 捕集来自上游 CO₂：估算为直接排放中可捕集部分
      const cap = (n.params.capture || 0) / 100
      const capturedNow = totalDirect * cap * 0.6 // 取已累计直接排放的 cap*60%
      captured += capturedNow
    } else {
      totalDirect += direct
      totalElec += elec
      if (green) greenElec += elec
      if (t.mainOut === 'steel_product' || t.mainOut === 'billet') steelOut += outMass
    }
    result.nodes[n.id] = {
      co2: direct + elec * ef,
      energy: elec,
      outMass,
      heat: outMass * (efDirect + t.efIndirect),
    }
  }

  // 汇总：自发电 + 绿电直供 抵扣外购电
  const gridUsed = Math.max(0, totalElec - producedPower - greenElec)
  const indirect = gridUsed * gridFactor + greenElec * greenFactor + producedPower * selfFactor + deviceEnergy
  let co2 = totalDirect + indirect - captured
  if (co2 < 0) co2 = 0

  result.totals.co2_total = co2
  result.totals.co2_direct = totalDirect
  result.totals.co2_indirect = indirect
  result.totals.energy = totalElec + deviceEnergy
  result.totals.steel_output = steelOut
  result.totals.intensity = steelOut > 0 ? (co2 / steelOut) * 1000 : 0
  result.totals.captured = captured
  return result
}
