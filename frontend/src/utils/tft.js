// ============================================================================
// 高炉多燃料通用 TFT（理论燃烧温度）焓平衡算法 —— 前端策略提示模块
// 与后端 Python calc_tft_enthalpy_full 逻辑完全对齐，覆盖固/液/气三类风口燃料。
//
// 用途：针对高炉可调设备（鼓风机·风量/湿度、热风炉·风温、喷吹系统·喷煤）的操作策略提示：
//   1) 实时计算当前工况 TFT 并判定热状态（正常 / 偏低 / 偏高）；
//   2) 预览设备调节对 TFT 的影响方向与幅度（走设备耦合推导，与系统 refresh 一致）；
//   3) 依据算法真值给出可执行的操作建议。
//
// 文档依据：《高炉多燃料通用TFT计算算法介绍》（焓平衡，缺氧不完全燃烧）
//
// 更新：cp（炉腹煤气平均比热容）从固定常数 0.0015 改为基于实际煤气组分与
//       温度的加权平均比热容（gas_mean_cp 多项式），迭代求解 TFT。
// ============================================================================

import { deriveProcessOpParams } from '../data/flowLibrary.js'

// ---- 1. 固定物理常数（文档 §9.3：热力学基准）----
export const TFT_CONST = {
  Q_C_CO: 9.79,          // C→CO 燃烧热 MJ/kgC
  Q_H_H2O: 120,          // H→H2O 燃烧热 MJ/kgH
  V_CO_PER_C: 1.867,     // 固体/液体燃料 C→CO 产气系数 Nm³/kgC（1 kgC = 83.33 molC → 83.33 molCO = 1.867 Nm³）
  V_H2O_PER_H: 11.2,     // 固体/液体燃料 H→H2O 产气系数 Nm³/kgH（1 kgH = 0.5 kmolH2 → 0.5 kmolH2O = 11.2 Nm³）
  Q_CH4: 35.88,          // CH4 燃烧热 MJ/Nm³
  Q_C2H6: 63.74,         // C2H6 燃烧热 MJ/Nm³
  Q_H2: 10.80,           // H2 燃烧热 MJ/Nm³
}

// ---- 1.1 气体平均比热容多项式系数（文档 §9.3：热力学基准）----
// gas_mean_cp(gas_type, T) = a + b*T + c*T² + d*T³  [kJ/(Nm³·℃)]
// 表示气体在 0~T ℃ 范围内的平均比热容，用于焓 = V·cp_mean·T 计算。
// 系数与后端 Python gas_mean_cp 完全一致。
export const GAS_CP_COEFFICIENTS = {
  CO:  [1.2993, 1.068e-4, -2.93e-8,  4.11e-12],
  N2:  [1.2987, 9.65e-5,  -2.35e-8,  3.30e-12],
  H2:  [1.2783, 6.12e-5,  -1.03e-8,  1.18e-12],
  O2:  [1.3065, 1.59e-4,  -4.03e-8,  5.59e-12],
  air: [1.2987, 1.05e-4,  -2.69e-8,  3.78e-12],
  H2O: [1.4935, 9.82e-5,  -2.08e-8,  2.67e-12],
  CO2: [1.6602, 3.49e-4,  -8.42e-8,  1.04e-11],
}

// 计算气体在 0~T ℃ 范围内的平均比热容 kJ/(Nm³·℃)
// 与后端 Python gas_mean_cp 完全对齐
export function gasMeanCp(gasType, T) {
  const coeffs = GAS_CP_COEFFICIENTS[gasType] || GAS_CP_COEFFICIENTS.air
  const [a, b, c, d] = coeffs
  return a + b * T + c * T * T + d * T * T * T
}

// 计算炉腹煤气混合物在 0~T ℃ 范围内的组分加权平均比热容
// gasVolumes: { V_CO, V_H2O, V_H2, V_N2, V_CO2 }  各组分体积 Nm³/tFe
// 返回值单位: MJ/(Nm³·℃)（内部 kJ→MJ 除以 1000）
export function calcBoshGasCp(gasVolumes, T) {
  const { V_CO = 0, V_H2O = 0, V_H2 = 0, V_N2 = 0, V_CO2 = 0 } = gasVolumes
  const total = V_CO + V_H2O + V_H2 + V_N2 + V_CO2
  if (!(total > 0)) return 0.0015 // 兜底：退回固定常数
  const cp_kJ = (
    V_CO  * gasMeanCp('CO',  T) +
    V_H2O * gasMeanCp('H2O', T) +
    V_H2  * gasMeanCp('H2',  T) +
    V_N2  * gasMeanCp('N2',  T) +
    V_CO2 * gasMeanCp('CO2', T)
  ) / total
  return cp_kJ / 1000 // kJ→MJ
}

// 由「风量 / 铁水产量 / 纯氧流量」反推派生富氧率(%)（与 collectTftInputs 同一物理混合模型）
// 供 bfFuel 煤比联动、TFT 弹窗氧轴预览等处由 o2_flow 反算 富氧率% 使用。
export function enrichFromFlow(wind, hotMetal, o2flow, humidity = 0) {
  const w = Number(wind) || 0, hm = Number(hotMetal) || 0, o2 = Number(o2flow) || 0
  const H = Math.max(0, Math.min(30, Number(humidity) || 0))
  if (!(hm > 0) || !(w > 0)) return 0
  const B_air = (w * 1000) / hm
  const h2oVolFrac = H * 1.244 / 1000
  const dry_air = Math.max(0, B_air * (1 - h2oVolFrac)) // 与 collectTftInputs 一致：O₂ 占比按干空气基底（湿分不供 O₂/N₂）
  const B_o2 = o2 / hm   // o2 单位 Nm³/h，已是绝对流量，无需 ×1000
  const O2_frac = (dry_air * 0.21 + B_o2) / Math.max(1e-9, dry_air + B_o2)
  return Math.max(0, (O2_frac - 0.21) * 100)
}

// 系统工序参数兜底默认值（从系统取不到该参数时使用；数值与系统模板 PROCESS_TEMPLATES 一致）
export const TFT_PARAM_DEFAULTS = {
  hot_blast_temp: 1200,   // 热风温度 ℃
  wind_rate: 1000,         // 风量 kNm³/h（绝对供风量）
  oxygen_enrich: 2,       // 富氧率（富氧增量，相对空气 21%）%
  blast_humidity: 15,     // 鼓风湿度 g/Nm³（鼓风机加湿/脱湿后的鼓风含湿，供氧系统富氧不改变湿度）
  hot_metal: 200,        // 铁水产量 t/h（系统实际值）
  coke_rate: 340,         // 焦比 kg/tFe
  coal_inj: 180,          // 喷煤比 kg/tFe
}

// ---- 2. 可配置超参数（文档 §9.1：后台可配置 / 人工微调，物理基准不变）----
//  cp              ：炉腹煤气定压比热容 MJ/(Nm³·℃)，【已弃用为常数】改为温度相关加权计算；
//                    此字段保留为迭代失败时的兜底回退值。
//  cpAir           ：鼓风（空气）定压比热容 MJ/(Nm³·℃)，【已弃用为常数】改为 gasMeanCp('air', tg)；
//                    此字段保留为迭代失败时的兜底回退值。
//  useTempDependentCp：是否启用温度相关比热容计算（默认 true）。
//                    false 时退回使用 cp / cpAir 固定常数（用于对比验证）。
//  hCombRatio      ：缺氧不完全燃烧下氢的燃烧比例（其余氢以 H2 进入炉缸煤气）
//  tftLow/tftHigh  ：TFT 合规判定区间 ℃，默认 2050~2250，可随炉役/冶炼品种配置
//  useElementCarbon：false=常规模式(基于固定碳FC) / true=高精度模式(基于元素碳Celem)
//  比风量口径（2026-08 变更）：比风量 B = 鼓风量(wind_rate, kNm³/h) ÷ 铁水产量(hot_metal, t/h)，换算为 Nm³/tFe（×1000）。
//                   TFT 现随铁水产量变化：相同鼓风量下产量越低 → 比风量越大 → TFT 越高（反之亦然）。
//  blastNominal / metalNominal：【已弃用】原用于推导物理比风量基准，现不再驱动 B，保留字段以兼容既有配置结构。
//  鼓风量自洽：QB = 产量 × 比风量 = hot_metal × B = wind_rate（kNm³/h → Nm³/h），与输入鼓风量一致。
//  fuels           ：各燃料基础参数（换煤种/油品/燃气组分时可微调）；enabled 控制是否参与计算；
//                    rateKey 表示用量取自哪个系统工序参数；无对应参数时用 rate 注入
export const DEFAULT_TFT_CONFIG = {
  cp: 0.0015,
  cpAir: 0.0013,
  useTempDependentCp: true,
  hCombRatio: 0.6,
  tftLow: 2050,
  tftHigh: 2250,
  useElementCarbon: false,
  blastNominal: 40000,
  metalNominal: 40,
  fuels: {
    coke: {
      enabled: true, fuel_type: 'solid', name: '焦炭', rateKey: 'coke_rate',
      FC: 0.85, Celem: 0.87, H: 0.001, decomp_heat: 0.0,
    },
    pulverized_coal: {
      enabled: true, fuel_type: 'solid', name: '喷吹煤粉', rateKey: 'coal_inj',
      FC: 0.81, Celem: 0.83, H: 0.04, decomp_heat: 0.35, Ash:0.10, H2O: 0.05
    },
    heavy_oil: {
      enabled: false, fuel_type: 'liquid', name: '重油', rate: 20,
      C: 0.86, H: 0.11, O: 0.02, decomp_heat: 0.50,
    },
    coke_oven_gas: {
      enabled: false, fuel_type: 'gas', name: '焦炉煤气', rate: 12,
      CO: 0.06, H2: 0.54, CH4: 0.25, C2H6: 0.02, CO2: 0.08, N2: 0.04, H2O: 0.01, decomp_heat: 0.0,
    },
  },
}

function num(v, dft) {
  const n = Number(v)
  return Number.isFinite(n) ? n : dft
}

// 构建参与计算的燃料列表：用量取自系统工序参数（rateKey），基础参数取自可配置超参数
export function buildFuelList(params, config = DEFAULT_TFT_CONFIG) {
  const fuels = []
  const f = config.fuels || {}
  const pushSolid = (key, fallbackRate, extra) => {
    const c = f[key]
    if (!c || c.enabled === false) return
    fuels.push({
      fuel_type: 'solid',
      name: c.name || key,
      rate: num(params[c.rateKey], num(c.rate, fallbackRate)),
      FC: c.FC, Celem: c.Celem, H: c.H, decomp_heat: num(c.decomp_heat, 0),
    })
  }
  pushSolid('coke', TFT_PARAM_DEFAULTS.coke_rate)
  pushSolid('pulverized_coal', TFT_PARAM_DEFAULTS.coal_inj)

  const oil = f.heavy_oil
  if (oil && oil.enabled) {
    fuels.push({
      fuel_type: 'liquid', name: oil.name || '重油', rate: num(oil.rate, 0),
      C: oil.C, H: oil.H, O: oil.O, decomp_heat: num(oil.decomp_heat, 0),
    })
  }
  const gas = f.coke_oven_gas
  if (gas && gas.enabled) {
    fuels.push({
      fuel_type: 'gas', name: gas.name || '焦炉煤气', rate: num(gas.rate, 0),
      CO: gas.CO, H2: gas.H2, CH4: gas.CH4, C2H6: gas.C2H6,
      CO2: gas.CO2, N2: gas.N2, H2O: gas.H2O, decomp_heat: num(gas.decomp_heat, 0),
    })
  }
  return fuels
}

// 采集基础工况：风温 / 鼓风量 / 产量 / 富氧率 / 鼓风湿度 → 比风量、鼓风氧氮占比、显热
export function collectTftInputs(params = {}, config = DEFAULT_TFT_CONFIG) {
  const p = { ...TFT_PARAM_DEFAULTS, ...params }
  const tg = num(p.hot_blast_temp, TFT_PARAM_DEFAULTS.hot_blast_temp)
  const wind = num(p.wind_rate, TFT_PARAM_DEFAULTS.wind_rate)
  const hotMetal = num(p.hot_metal, TFT_PARAM_DEFAULTS.hot_metal)
  // 比风量 = 鼓风量 / 铁水产量（用户指定口径：以实际供风总量 ÷ 实际铁水产量得到每吨铁送风量）
  //   wind_rate：鼓风量，绝对供风量 kNm³/h（鼓风机供给的空气）
  //   hot_metal：铁水产量 t/h（系统实际值）
  //   单位换算：B_air [Nm³/tFe] = wind_rate[kNm³/h] × 1000 ÷ hot_metal[t/h]
  // 富氧以「纯氧流量」o2_flow[Nm³/h]（氧枪/空分供给）注入主风管，与空气真实混合：
  //   纯氧不含 N₂，故 N₂ 体积只来自空气、恒为 B_air×0.79；O₂ 体积 = 空气O₂ + 纯O₂；
  //   富氧率(派生%) = 混合鼓风含氧% − 21%，由风量+纯氧流量实时算出（o2_flow 缺省时由旧
  //   oxygen_enrich 反算，兼容存量工况）。修正了旧模型「富氧时把 N₂ 体积按比例压低」的近似。
  const B_air = (wind * 1000) / Math.max(1, hotMetal)         // 空气比风量 Nm³/tFe（鼓风机供给）
  const B = B_air                                              // 兼容下游：B 现指空气比风量
  const PFe = hotMetal                                         // 铁水产量 t/h（系统实际值）

  // 鼓风湿度（g/Nm³）：先算（供 O₂/N₂ 体积切分与显热），水分在风口分解吸热、消耗碳并增加煤气量
  const H = Math.max(0, Math.min(30, num(p.blast_humidity, TFT_PARAM_DEFAULTS.blast_humidity)))
  const h2oVolFrac = H * 1.244 / 1000       // 每 Nm³ 鼓风含水蒸气体积 Nm³（1 kg H2O ≈ 1.244 Nm³）
  const dry_air = Math.max(0, B_air * (1 - h2oVolFrac)) // 干空气比风量 Nm³/tFe（湿分不供氧、不产热，仅携显热）
  const m_h2o = B_air * H / 1000             // 鼓风水分 kg/tFe
  const Q_h2o_decomp = m_h2o * 10.8          // 水分分解吸热 MJ/tFe（C+H₂O→CO+H₂ 约 10.8 MJ/kg H2O）

  // 纯氧流量 → 纯氧比风量（与空气同样以每吨铁计）；缺省时由存量 oxygen_enrich(%) 反算
  const o2raw = p.o2_flow != null ? Number(p.o2_flow) : null
  let B_o2
  if (o2raw != null && Number.isFinite(o2raw)) {
    B_o2 = Math.max(0, o2raw) / Math.max(1, hotMetal)   // 纯氧比风量 Nm³/tFe（o2_flow 单位 Nm³/h，已是绝对流量，无需 ×1000）
  } else {
    const wO_legacy = Math.min(14, Math.max(0, num(p.oxygen_enrich, TFT_PARAM_DEFAULTS.oxygen_enrich)))
    B_o2 = dry_air * (0.01 * wO_legacy) / Math.max(1e-6, 0.79 - 0.01 * wO_legacy)
  }
  // 供 calcTFT 使用：V_O2 = dry_air·O2_blow = dry_air·0.21 + B_o2；V_N2 = dry_air·N2_blow = dry_air·0.79
  //   （N₂ 只来自空气，富氧时绝不减少——这是相对旧模型的关键修正）
  const O2_blow = 0.21 + B_o2 / Math.max(1e-9, dry_air)
  const N2_blow = 0.79
  // 派生富氧率（%）：混合鼓风含氧% − 21%
  const O2_frac = (dry_air * 0.21 + B_o2) / Math.max(1e-9, dry_air + B_o2)
  const oxygen_enrich = Math.max(0, (O2_frac - 0.21) * 100)
  const wO = oxygen_enrich
  const QB = PFe * (B_air + B_o2)                            // 总鼓风量（空气+纯氧）Nm³/h

  // 鼓风显热：空气与纯氧均被热风炉加热至风温 tg，统一计入（温度相关空气平均比热容）
  const useTD = config.useTempDependentCp !== false
  const cpAir = useTD
    ? gasMeanCp('air', tg) / 1000
    : num(config.cpAir, 0.0013)
  const Q_sensible_air = (dry_air + B_o2) * cpAir * tg          // MJ/tFe（空气+纯氧 显热）
  const fuel_list = buildFuelList(p, config)
  return { tg, wind, QB, PFe, hot_metal: hotMetal, B, wO, o2_flow: o2raw, oxygen_enrich, O2_blow, N2_blow, cpAir, Q_sensible_air, blast_humidity: H, dry_air, m_h2o, Q_h2o_decomp, fuel_list }
}

// ---- 3. 核心算法：与 Python calc_tft_enthalpy_full 完全对齐 ----
// 边界假设：风口回旋区缺氧不完全燃烧，烃类产物为 CO + H2O，燃料原生 CO 不参与二次燃烧。
// 氧限制：鼓风氧是燃烧耗氧的唯一来源，燃料碳氢中超出鼓风氧供给能力的部分视为未燃，
//         不计入放热与产气（避免 TFT 虚高，如全部碳按 1.867 Nm³/kgC 产气时总量被高估）。
//
// 【更新】炉腹煤气比热容 cp 从固定常数改为组分加权 + 温度相关多项式：
//   TFT = Q_total_in / (V_gas_total · cp_bosh(TFT))
//   cp_bosh(T) = Σ(Vi · gasMeanCp(gas_i, T)) / V_gas_total   [MJ/(Nm³·℃)]
//   由于 cp 依赖 TFT（循环依赖），采用不动点迭代求解，通常 5~10 次收敛。
export function calcTFT(inputs, config = DEFAULT_TFT_CONFIG) {
  const { B, O2_blow, N2_blow, Q_sensible_air, fuel_list, dry_air = B, m_h2o = 0, Q_h2o_decomp = 0 } = inputs
  if (!(B > 0)) throw new Error('比风量异常：生铁产量/鼓风量无效，无法计算')

  const useElem = !!config.useElementCarbon
  const hc = num(config.hCombRatio, 0.6)   // 缺氧下氢的部分燃烧比例（其余 H2 入炉缸煤气）

  let C_total = 0            // 固/液燃料碳 kg/tFe
  let H_total = 0            // 固/液燃料氢 kg/tFe
  let decomp_heat = 0        // 燃料热解吸热 MJ/tFe
  let gas_heat = 0           // 气体燃料放热 MJ/tFe
  let V_CO_solid = 0         // 固/液燃料 C→CO 理论产气 Nm³/tFe
  let V_H2O_solid = 0        // 固/液燃料 H→H2O 理论产气 Nm³/tFe
  let V_CO_gas = 0
  let V_H2O_gas = 0
  let V_CO2_fuel = 0         // 燃料自带 CO2 Nm³/tFe（单独追踪用于 cp 加权）
  let V_N2_fuel = 0          // 燃料自带 N2 Nm³/tFe（单独追踪用于 cp 加权）

  for (const fuel of fuel_list) {
    const ft = fuel.fuel_type
    if (ft === 'solid' || ft === 'liquid') {
      // 固/液燃料：元素 C/H（液体）或固定碳/元素碳（固体）参与燃烧，产气按经验系数
      const rate = fuel.rate
      const c = useElem && fuel.Celem != null ? fuel.Celem : (fuel.C != null ? fuel.C : fuel.FC)
      const h = fuel.H || 0
      C_total += rate * c
      H_total += rate * h
      decomp_heat += rate * num(fuel.decomp_heat, 0)
      V_CO_solid += TFT_CONST.V_CO_PER_C * rate * c
      V_H2O_solid += TFT_CONST.V_H2O_PER_H * rate * h
    } else if (ft === 'gas') {
      // 气体燃料按组分独立核算；可燃组分放热，惰性组分直接并入煤气
      const v = fuel.rate
      gas_heat += fuel.CH4 * v * TFT_CONST.Q_CH4 + fuel.C2H6 * v * TFT_CONST.Q_C2H6
        + fuel.H2 * v * TFT_CONST.Q_H2 - v * fuel.decomp_heat
      // 烃裂解：CH4→CO+2H2O；C2H6→2CO+3H2O；H2→H2O；原生 CO 保留
      V_CO_gas += fuel.CH4 * v * 1.0 + fuel.C2H6 * v * 2.0 + fuel.CO * v
      V_H2O_gas += fuel.CH4 * v * 2.0 + fuel.C2H6 * v * 3.0 + fuel.H2 * v * 1.0 + fuel.H2O * v
      // 惰性组分 CO2、N2 分别追踪（不再合并为 V_inert）
      V_CO2_fuel += fuel.CO2 * v
      V_N2_fuel += fuel.N2 * v
    } else {
      throw new Error(`不支持的燃料类型：${ft}`)
    }
  }

  // ---- 风口碳受鼓风氧限制 ----
  // 鼓风氧 Nm³/tFe：干风量 dry_air × O2_blow（湿分 H2O 不供氧，仅携显热）。
  // 氢按 hc 比例烧成 H2O（每 Nm³ H2O 耗 0.5 Nm³ O2，即每 kgH 耗 5.6 Nm³ O2）；
  // 剩余氧供碳 C→CO（每 kgC 生成 1.867 Nm³ CO 耗 0.9333 Nm³ O2），
  // 超出鼓风氧供给能力的碳视为未燃，不计放热与产气。
  // 鼓风水分（C+H₂O→CO+H₂）：每 kg H2O 消耗 0.667 kg C，该部分碳不参与 C→CO 燃烧放热，
  // 但产气 CO/H2 由下方 V_h2o_prod_* 单独计入，总产气口径保持一致。
  const V_O2_blast = dry_air * O2_blow
  const O2_for_H = 0.5 * V_H2O_solid * hc
  const O2_for_C_avail = Math.max(0, V_O2_blast - O2_for_H)
  const C_burnable = O2_for_C_avail / 0.9333
  const C_h2o = m_h2o * 0.667
  const C_eff = Math.max(0, C_total - C_h2o)
  const C_burn = Math.min(C_eff, C_burnable)
  const burnRatio = C_total > 0 ? C_burn / C_total : 0

  // 放热（按实际燃烧份额）：C→CO + 氢部分燃烧 H→H2O - 热解吸热 + 气体放热 - 水分分解吸热
  const sum_heat = C_burn * TFT_CONST.Q_C_CO + H_total * TFT_CONST.Q_H_H2O * hc - decomp_heat + gas_heat - Q_h2o_decomp

  // 产气：CO/H2O 按燃烧份额；水煤气 CO/H2 单独计入；未燃 H2 与惰性组分直接并入炉腹煤气
  const V_h2o_prod_CO = m_h2o * 1.244       // 水煤气反应 CO 产气 Nm³/tFe（每 kg H2O 产 1.244 Nm³）
  const V_h2o_prod_H2 = m_h2o * 1.244       // 水煤气反应 H2 产气 Nm³/tFe（每 kg H2O 产 1.244 Nm³）
  const sum_VCO = V_CO_solid * burnRatio + V_CO_gas + V_h2o_prod_CO
  const sum_VH2O = V_H2O_solid * hc + V_H2O_gas
  const sum_VH2 = V_H2O_solid * (1 - hc) + V_h2o_prod_H2
  const V_N2_blast = dry_air * N2_blow
  const V_N2_total = V_N2_blast + V_N2_fuel   // 鼓风氮 + 燃料氮
  const V_inert = V_CO2_fuel + V_N2_fuel       // 兼容旧字段（CO2+N2 合计）
  const V_gas_total = sum_VCO + sum_VH2O + sum_VH2 + V_CO2_fuel + V_N2_fuel + V_N2_blast
  if (!(V_gas_total > 0)) throw new Error('炉腹煤气总量异常，不能≤0')

  const Q_total_in = Q_sensible_air + sum_heat

  // ---- TFT 求解：组分加权温度相关 cp 不动点迭代 ----
  //   TFT = Q_total_in / (V_gas_total · cp_bosh(TFT))
  //   cp_bosh(T) = Σ(Vi · gasMeanCp(gas_i, T)) / V_gas_total / 1000  [MJ/(Nm³·℃)]
  //   迭代收敛条件：|ΔT| < 1℃，最多 30 次（|f'|≈0.05，收敛极快）
  const useTD = config.useTempDependentCp !== false
  let TFT, cp_eff
  if (useTD) {
    const gasVolumes = { V_CO: sum_VCO, V_H2O: sum_VH2O, V_H2: sum_VH2, V_N2: V_N2_total, V_CO2: V_CO2_fuel }
    let T_guess = 2000  // 初始猜测值（TFT 典型区间 2050~2250）
    cp_eff = num(config.cp, 0.0015) // 兜底
    for (let i = 0; i < 30; i++) {
      cp_eff = calcBoshGasCp(gasVolumes, T_guess)
      const T_new = Q_total_in / (V_gas_total * cp_eff)
      if (Math.abs(T_new - T_guess) < 1) { T_guess = T_new; break }
      T_guess = T_guess + (T_new - T_guess) * 0.5 // 阻尼因子 0.5，保证收敛稳定性
    }
    TFT = Q_total_in / (V_gas_total * cp_eff)
  } else {
    // 兼容模式：使用固定常数 cp（用于对比验证）
    cp_eff = num(config.cp, 0.0015)
    TFT = Q_total_in / (V_gas_total * cp_eff)
  }

  return {
    TFT, sum_heat, sum_VCO, sum_VH2O, sum_VH2, sum_Vinert: V_inert,
    V_N2_blast, V_N2_fuel, V_CO2_fuel, V_gas_total,
    Q_sensible_air, Q_total_in,
    C_total, C_burn, V_O2_blast,
    blast_humidity: inputs.blast_humidity, dry_air, m_h2o, C_h2o, Q_h2o_decomp,
    cp_eff, // 实际使用的炉腹煤气平均比热容 MJ/(Nm³·℃)
    cp_air: inputs.cpAir, // 实际使用的鼓风平均比热容 MJ/(Nm³·℃)
  }
}

// ---- 4. 热状态判定（文档 §6：TFT 阈值判定规则）----
export function evalTftStatus(tft, config = DEFAULT_TFT_CONFIG) {
  if (tft < config.tftLow) {
    return { code: 'low', label: 'TFT 偏低', color: '#e06c5a',
      desc: '风口燃烧能量不足，易出现燃料燃烧不完全、炉温偏凉' }
  }
  if (tft > config.tftHigh) {
    return { code: 'high', label: 'TFT 偏高', color: '#e8a23d',
      desc: '风口燃烧过热，易造成设备损耗、炉况热过载' }
  }
  return { code: 'ok', label: '热制度正常', color: '#3fae6a',
    desc: '炉内热制度稳定，燃料燃烧状态良好' }
}

// 汇总当前工况 TFT 上下文（输入 + 计算分解 + 状态）
export function collectTftContext(params = {}, config = DEFAULT_TFT_CONFIG) {
  const inputs = collectTftInputs(params, config)
  const res = calcTFT(inputs, config)
  const status = evalTftStatus(res.TFT, config)
  return { inputs, res, status, tft: res.TFT, config }
}

// ---- 5. 设备调节预览 ----
// 模拟「将指定设备设定改为 setpoint/extraSetpoints」后工序参数耦合推导的结果，
// 与系统 refresh 中 deriveProcessOpParams(u.type, devs, u.params) 语义一致。
export function previewDeviceChange(unitType, deviceType, setpoint, extraSetpoints, baseParams, config = DEFAULT_TFT_CONFIG) {
  const base = baseParams || {}
  const devices = [{ type: deviceType, setpoint, extraSetpoints: extraSetpoints || {} }]
  const overrides = deriveProcessOpParams(unitType, devices, base)
  const newParams = { ...base, ...overrides }
  const cur = calcTFT(collectTftInputs(base, config), config)
  const pre = calcTFT(collectTftInputs(newParams, config), config)
  return { current: cur.TFT, preview: pre.TFT, delta: pre.TFT - cur.TFT, newParams }
}

// 高炉热制度相关可调设备：探测步长（用于生成操作建议）
// 注：喷吹系统(喷煤量)已锁定不可调，不再列入探测
export const TFT_DEVICE_PROBES = [
  { type: 'hot_blast_stove', label: '热风炉·风温', step: 30, unit: '℃' },
  { type: 'blower', label: '鼓风机·风量', step: 520, unit: 'm³/h' },
  { type: 'blower', label: '鼓风机·鼓风湿度', step: 1, unit: 'g/Nm³', extraKey: 'humidity', def: 10 },
]

// 从工序参数反推设备当前设定（设备设定缺失时兜底）；overrides 可用实际设定值覆盖（如当前选中的设备）
export function inferDeviceSetpoints(params = {}, config = DEFAULT_TFT_CONFIG, overrides = {}) {
  const p = { ...TFT_PARAM_DEFAULTS, ...params }
  const wind = num(p.wind_rate, TFT_PARAM_DEFAULTS.wind_rate)
  const setpoints = {
    hot_blast_stove: num(p.hot_blast_temp, 1250),
    blower: wind * 5200 / 600,         // 风量 kNm³/h（def 600）→ 设备设定 m³/h（def 5200）
    blower_humidity: 10,               // 鼓风湿度名义基准 g/Nm³
    injector: 120,                     // 喷煤速率名义基准 kg/h
  }
  if (overrides.hot_blast_stove != null) setpoints.hot_blast_stove = num(overrides.hot_blast_stove, 1250)
  if (overrides.blower != null) setpoints.blower = num(overrides.blower, 5200)
  if (overrides.blower_humidity != null) setpoints.blower_humidity = num(overrides.blower_humidity, 10)
  if (overrides.injector != null) setpoints.injector = num(overrides.injector, 120)
  return setpoints
}

// ---- 6. 操作建议：算法驱动（不硬编码方向）----
// 探测单个探针(设备+方向步长)对 TFT 的真实影响，返回符合目标方向的操作条目。
// wantCool=true(偏高需降温) → 只保留 delta<0 的操作；wantCool=false(偏低需升温) → 只保留 delta>0 的操作。
function probeDeviceAdvice(pr, params, config, wantCool, sp) {
  const target = wantCool ? -1 : 1
  let curSet, extra = {}
  if (pr.extraKey) {
    const skey = `blower_${pr.extraKey}` // 如 blower_humidity
    curSet = sp[skey] != null ? sp[skey] : (pr.def != null ? pr.def : 0)
    extra = { [pr.extraKey]: curSet }
  } else {
    curSet = sp[pr.type] != null ? sp[pr.type] : (pr.type === 'blower' ? sp.blower : 120)
  }
  const out = []
  for (const [dir, sgn] of [['提高', 1], ['降低', -1]]) {
    const ns = curSet + sgn * pr.step
    if (ns <= 0) continue
    try {
      const prev = previewDeviceChange('blast_furnace', pr.type, ns, extra, params, config)
      if (Math.sign(prev.delta) === target) {
        out.push({
          device: pr.type, label: pr.label, dir, delta: prev.delta,
          text: `建议${dir}${pr.label}（±${pr.step}${pr.unit || ''}）`,
          deltaLabel: `TFT ${prev.delta >= 0 ? '↑' : '↓'} ${Math.abs(prev.delta).toFixed(0)}℃`,
        })
      }
    } catch (e) { /* 跳过异常探测 */ }
  }
  return out
}

// 单设备建议：仅针对指定设备类型生成（设备属性面板用，只保留当前设备的调节影响与建议）
export function buildDeviceTftAdvices(deviceType, params = {}, config = DEFAULT_TFT_CONFIG, deviceSetpoints = {}) {
  const ctx = collectTftContext(params, config)
  if (ctx.status.code === 'ok') {
    return [{
      device: deviceType, label: '', dir: '✓',
      text: '当前热制度稳定（TFT 在正常区间内），可维持当前设备设定。', deltaLabel: '', delta: 0,
    }]
  }
  const wantCool = ctx.status.code === 'high'
  const sp = inferDeviceSetpoints(params, config, deviceSetpoints)
  const advices = []
  for (const pr of TFT_DEVICE_PROBES.filter((p) => p.type === deviceType)) {
    advices.push(...probeDeviceAdvice(pr, params, config, wantCool, sp))
  }
  if (!advices.length) {
    advices.push({
      device: deviceType, label: '', dir: '!',
      text: '该设备在当前范围内对 TFT 影响有限，建议核查其他可调设备或燃料配比（焦比/喷煤比）。',
      deltaLabel: '', delta: 0,
    })
  }
  return advices
}

// 系统级完整建议：对全部热制度可调设备逐个生成符合方向的建议（工序属性面板用，系统分析）
export function buildSystemTftAdvices(params = {}, config = DEFAULT_TFT_CONFIG, deviceSetpoints = {}) {
  const ctx = collectTftContext(params, config)
  if (ctx.status.code === 'ok') {
    return [{
      device: 'all', label: '全部设备', dir: '✓',
      text: '当前热制度稳定（TFT 在正常区间内），全部可调设备可维持现有设定。', deltaLabel: '', delta: 0,
    }]
  }
  const wantCool = ctx.status.code === 'high'
  const sp = inferDeviceSetpoints(params, config, deviceSetpoints)
  const advices = []
  for (const pr of TFT_DEVICE_PROBES) {
    advices.push(...probeDeviceAdvice(pr, params, config, wantCool, sp))
  }
  if (!advices.length) {
    advices.push({
      device: 'all', label: '全部设备', dir: '!',
      text: '常规可调设备在当前范围内对 TFT 影响有限，建议核查燃料配比（焦比/喷煤比）或参数标定。',
      deltaLabel: '', delta: 0,
    })
  }
  return advices
}

// ---- 7. 实时参数折算：设备设定 → 工序参数 ----
// 将「工序基础参数 + 当前实际设备设定（含附加可调项）」折算为 TFT 实时计算参数。
// 与系统 refresh 的折算语义一致（deriveProcessOpParams），保证拖动可调设备滑块后
// TFT 数值、状态徽章与操作建议实时联动。
// setpointMap: { deviceType: number | { setpoint, extraSetpoints } }
export function buildRealtimeTftParams(unitType, baseParams = {}, setpointMap = {}) {
  const devs = Object.entries(setpointMap || {})
    .filter(([, v]) => v != null)
    .map(([type, v]) => {
      const vv = typeof v === 'object' && v !== null ? v : { setpoint: v }
      return { type, setpoint: vv.setpoint, extraSetpoints: vv.extraSetpoints || {} }
    })
  const overrides = deriveProcessOpParams(unitType, devs, baseParams) || {}
  return { ...(baseParams || {}), ...overrides }
}
