// ============================================================================
// 高炉 CO2 排放计算模块 —— 前端移植版
// 与后端 Python bf_tft_v20.py §10「碳平衡法」1:1 对齐。
//
// 口径（v20 定稿）：
//   全炉碳收支: 入炉碳 C_in = 铁水溶碳 C_HM(唯一产品碳) + 排放碳 C_emit
//   排放碳     C_emit = C_in - C_HM
//   CO2 排放   = C_emit × (M_CO2 / M_C) = C_emit × 44.009/12.011  [kg CO2/tHM]
//
//   关键约定：
//     - 炉尘碳 C_dust 不再作为产品碳扣减，全部计入排放碳
//       （未燃煤粉 U 与焦粉随炉尘/煤气带出，最终仍氧化为 CO2）；
//     - 即「输入碳 - 输出碳 = 排放碳」，其中输出碳只有铁水含碳；
//     - 炉尘量/含碳参数仅作信息展示，不参与扣减；
//     - 无论 CO 在炉内是否氧化完全，离炉后均按 CO2 计（Scope1 + CO 燃烧）；
//     - 未计入石灰石熔剂分解 CO2 与焦炭/煤粉挥发分碳（仅计固定碳 FC）。
//
// 与前端 TFT 模块的关系：
//   - 燃料用量复用同一份工序参数（coke_rate / coal_inj）；
//   - 入炉碳采用后端 v20 燃料成分（焦炭固定碳 85.82%、煤粉 67.57%），
//     以保证与后端默认结果逐位一致（C_in=413.4 → CO2=1349.9 kg/tHM）；
//     若要与前端 TFT 的燃料配置（FC 0.85 / 0.72）统一，覆盖
//     co2Config.coke_carbon_pct / coal_carbon_pct 即可；
//   - 「风口/非风口路径细分」默认走后端 v20 氧驱动口径（splitFrom='backend'），
//     细分结果与后端打印一致（默认工况 908.1 / 441.8 kg CO2/tHM）；
//     需要与前端 TFT 自洽时设 splitFrom='tft' 取 calcTFT 的 C_burn。
//   - CO2 总量仅取决于 C_in 与 C_HM，与 TFT 燃烧路径模型无关。
// ============================================================================

import { collectTftContext, TFT_PARAM_DEFAULTS } from './tft.js'

// ---- 1. 固定物理常数（与后端 v20 全局常量一致）----
export const CO2_CONST = {
  M_C: 12.011,     // 碳摩尔质量 g/mol (kg/kmol)
  M_CO2: 44.009,   // CO2 摩尔质量 g/mol (kg/kmol)
  VM: 22.4,        // 标准摩尔体积 L/mol (Nm³/kmol)
  M_H2O: 18.015,   // 水摩尔质量 g/mol
  O2_AIR: 0.21,    // 空气中 O2 体积分数
  N2_AIR: 0.79,    // 空气中 N2 体积分数
}

// ---- 2. CO2 排放计算参数（与后端 v20 默认值一致）----
export const CO2_DEFAULTS = {
  hm_carbon_pct: 4.5,      // 铁水含碳 %（唯一产品碳，一般 4.0~4.8）
  dust_rate: 20.0,         // 炉尘量 kg/tHM（仅信息展示；炉尘碳计入排放，不再扣减）
  dust_carbon_pct: 30.0,   // 炉尘含碳 %（仅信息展示；炉尘碳计入排放，不再扣减）
  coke_carbon_pct: 85.82,  // 焦炭固定碳 %（与后端 v20 燃料成分一致）
  coal_carbon_pct: 67.57,  // 煤粉固定碳 %（与后端 v20 燃料成分一致）
  splitFrom: 'backend',    // 路径细分口径: 'backend' = 后端 v20 氧驱动风口碳（默认, 与后端打印一致）
                           //              'tft'     = 前端 TFT 的 C_burn（与前端 TFT 自洽）
}

function num(v, dft) {
  const n = Number(v)
  return Number.isFinite(n) ? n : dft
}

// ---- 2.5 后端 v20 氧驱动风口燃烧碳（用于 CO2 路径细分, 与后端 §2~§5 一致）----
// 后端口径: 鼓风是风口燃烧氧的唯一来源
//   O2_supply = V_B × [(1-f)(0.21(1-φ)+0.5φ) + f]        (φ=湿度水汽份额, f=富氧率)
//   供氧能烧的碳 m_C_R_O2 = O2_supply / (VM/(2·M_C))     (C + 1/2 O2 → CO)
//   燃料可烧碳上限 C_burnable = C_coke + η_coal·C_coal   (η_coal=0.68+0.045E-0.003E²)
//   实际燃烧碳 m_C_R = min(m_C_R_O2, C_burnable)
// params: 已合并默认值的工序参数 { blast_humidity, oxygen_enrich, V_B, ... }
// co2Cfg: 已合并默认值的 CO2 参数（提供 coke_carbon_pct / coal_carbon_pct）
export function calcBackendRacewayCarbon(params = {}, co2Cfg = {}) {
  const p = { ...TFT_PARAM_DEFAULTS, ...params }
  const c = { ...CO2_DEFAULTS, ...co2Cfg }
  const V_B = num(p.V_B, 1000)                       // 比风量 Nm³/tHM（后端 CLI 默认 1000）
  const phi = p.blast_humidity / 1000 * CO2_CONST.VM / CO2_CONST.M_H2O   // Nm³ H2O/Nm³ 湿空气
  const f = p.oxygen_enrich / 100
  const B_O2_air = CO2_CONST.O2_AIR * (1 - phi) + 0.5 * phi   // 湿空气中有效 O2 份额(含水分解)
  const O2_supply = V_B * ((1 - f) * B_O2_air + f)   // 鼓风供氧 Nm³/tHM
  const eta_coal = Math.min(Math.max(
    0.68 + 0.045 * p.oxygen_enrich - 0.003 * p.oxygen_enrich ** 2, 0.5), 1.0)  // 煤粉燃尽率
  const cokeRate = num(p.coke_rate, TFT_PARAM_DEFAULTS.coke_rate)
  const coalRate = num(p.coal_inj, TFT_PARAM_DEFAULTS.coal_inj)
  const C_coke = cokeRate * c.coke_carbon_pct / 100
  const C_coal = coalRate * c.coal_carbon_pct / 100
  const C_burnable = C_coke + eta_coal * C_coal      // 燃料可烧碳上限
  const m_C_R_O2 = O2_supply / (CO2_CONST.VM / (2 * CO2_CONST.M_C))
  const m_C_R = Math.min(m_C_R_O2, C_burnable)       // 实际风口燃烧碳 ★
  return {
    m_C_R, eta_coal, O2_supply, C_burnable, m_C_R_O2,
    fuel_limited: m_C_R_O2 >= C_burnable,            // true=氧充足燃料全烧; false=氧不足
  }
}

// ---- 3. 核心：CO2 排放计算（碳平衡法）----
// params  : 工序参数 { coke_rate, coal_inj, ... }（与 TFT 同源，走 TFT_PARAM_DEFAULTS 兜底）
// tftRes  : calcTFT() 的返回值（当 co2Cfg.splitFrom='tft' 时提供 C_burn 作风口燃烧碳；
//           否则不用，细分走后端氧驱动口径）
// co2Cfg  : CO2 参数覆盖 { hm_carbon_pct, coke_carbon_pct, coal_carbon_pct,
//           dust_rate, dust_carbon_pct, splitFrom }
export function calcCo2Emission(params = {}, tftRes = null, co2Cfg = {}) {
  const p = { ...TFT_PARAM_DEFAULTS, ...params }
  const c = { ...CO2_DEFAULTS, ...co2Cfg }

  // ---- 碳收支（kg C/tHM）----
  const cokeRate = num(p.coke_rate, TFT_PARAM_DEFAULTS.coke_rate)
  const coalRate = num(p.coal_inj, TFT_PARAM_DEFAULTS.coal_inj)

  const C_coke = cokeRate * c.coke_carbon_pct / 100          // 焦炭带入碳
  const C_coal = coalRate * c.coal_carbon_pct / 100          // 煤粉带入碳
  const C_in = C_coke + C_coal                               // 入炉碳（仅燃料固定碳 FC）

  const C_HM = 1000 * c.hm_carbon_pct / 100                  // 铁水溶碳（唯一产品碳）

  // ---- 排放碳 = 入炉碳 - 铁水溶碳（炉尘碳/未燃煤粉均含于其中, 计入排放）----
  const C_emit = Math.max(C_in - C_HM, 0)                    // kg C/tHM ★
  const CO2_emit = C_emit * CO2_CONST.M_CO2 / CO2_CONST.M_C  // kg CO2/tHM ★★

  // 炉尘碳（信息展示，计入排放不扣减）
  const C_dust = c.dust_rate * c.dust_carbon_pct / 100

  // ---- 路径细分（仅展示用，不改变总量）----
  // 与后端一致：产品扣减(仅铁水溶碳)优先从非风口碳池 C_other 中扣
  //   （渗碳出自未在风口燃烧的燃料碳），不足部分再扣风口燃烧碳 m_C_R。
  // 默认走后端 v20 氧驱动口径（splitFrom='backend'），与后端打印一致；
  // 需要与前端 TFT 自洽时设 splitFrom='tft'，取 tftRes.C_burn。
  const rc = c.splitFrom === 'tft' && tftRes
    ? { m_C_R: num(tftRes.C_burn, 0), eta_coal: 0, O2_supply: 0, C_burnable: 0, m_C_R_O2: 0, fuel_limited: null }
    : calcBackendRacewayCarbon(p, c)
  const m_C_R = rc.m_C_R                                    // 风口实际燃烧碳
  const C_other = Math.max(C_in - m_C_R, 0)                 // 非风口碳池
  const C_other_to_gas = Math.max(C_other - C_HM, 0)        // 非风口路径排放碳
  const C_raceway_to_gas = Math.max(C_emit - C_other_to_gas, 0) // 风口路径排放碳

  return {
    // 碳收支
    C_coke, C_coal, C_in,
    C_HM, C_dust, C_emit, CO2_emit,
    CO2_t: CO2_emit / 1000,                                  // t CO2/tHM
    // 路径细分（风口路径 / 非风口碳池）
    m_C_R, C_other,
    C_other_to_gas, C_raceway_to_gas,
    CO2_from_raceway: C_raceway_to_gas * CO2_CONST.M_CO2 / CO2_CONST.M_C,
    CO2_from_other: C_other_to_gas * CO2_CONST.M_CO2 / CO2_CONST.M_C,
    // 风口氧驱动诊断（splitFrom='backend' 时有效）
    eta_coal: rc.eta_coal, O2_supply: rc.O2_supply,
    C_burnable: rc.C_burnable, m_C_R_O2: rc.m_C_R_O2,
    fuel_limited: rc.fuel_limited,
    split_from: c.splitFrom,
    // 参数快照
    coke_rate: cokeRate, coal_inj: coalRate,
    hm_carbon_pct: c.hm_carbon_pct,
    coke_carbon_pct: c.coke_carbon_pct, coal_carbon_pct: c.coal_carbon_pct,
  }
}

// ---- 4. CO2 排放强度判定（可选，供页面徽章/建议区使用）----
// 参考: 典型高炉工序直接排放 ~1.5-2.0 t CO2/tHM（后端 v20 打印口径）
export function evalCo2Level(co2t) {
  if (co2t < 1.2) {
    return { code: 'low', label: '低碳排', color: '#3fae6a',
      desc: '排放强度低于典型水平，燃料结构/利用效率较优' }
  }
  if (co2t > 1.8) {
    return { code: 'high', label: '高碳排', color: '#e06c5a',
      desc: '排放强度高于典型水平，建议核查焦比/煤比与直接还原度' }
  }
  return { code: 'ok', label: '排放正常', color: '#e8a23d',
    desc: '排放强度处于典型高炉区间（约 1.5~2.0 t CO2/tHM）' }
}

// ---- 5. 一键汇总：TFT 上下文 + CO2 排放（前端页面直接消费）----
// 返回 { ...collectTftContext 的结果, co2: {...} }
export function collectSimContext(params = {}, tftConfig = undefined, co2Config = {}) {
  const ctx = collectTftContext(params, tftConfig)
  const co2 = calcCo2Emission(params, ctx.res, co2Config)
  co2.level = evalCo2Level(co2.CO2_t)
  return { ...ctx, co2 }
}
