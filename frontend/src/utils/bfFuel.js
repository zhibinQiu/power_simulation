// ============================================================================
// 高炉「操作参数 + 喷煤置换 → 焦比/煤比」耦合推算（前后端唯一真源）
// ----------------------------------------------------------------------------
// 与后端 calculators._bf_effective_fuel 1:1 对齐，供三条链路共用：
//   1) 编辑态主流程估算    flow/compute.js      （燃料燃烧 + 国标式直接排放）
//   2) 高炉 TFT 分析弹窗   components/TftAnalysisDialog.vue（TFT 基准 + CO₂ 展示）
//   3) 后端精确重算        calculators.calc_bf  （Python 侧同式）
//
// 口径：
//   - 喷煤置换（无条件，节点定义了煤比即生效）：
//       喷吹煤粉按置换比顶替焦炭：Δ焦比 = −RR × (有效煤比 − 名义基准煤比 175)。
//       RR 由煤粉成分（Celem/H/H2O/Ash，取自 tft.js pulverized_coal）经
//       Geerdes 公式实时算出（当前 ≈ 0.89，Celem 0.83），换煤种后自动跟随。
//   - 富氧为「派生煤比」通道（不再直接节焦）：
//       每 +1% 富氧允许多喷 15 kg/t 煤粉（富氧升温 → 燃烧带容纳更多煤粉；实测出处：
//       北大先锋·山西某钢厂 0→4% 富氧，煤比 120→170 kg/t，原 ≈12.5，当前按 15 配置），
//       有效煤比 = 设定煤比 + 15×富氧率，再经喷煤置换联动降低焦比。
//   - 操作参数（wind_rate / hot_blast_temp / draft 任一存在）：
//       以节点焦比/煤比为基准，按相对「名义工况」（风量 600 kNm³/h / 风温 1250℃ /
//       抽力 1.0）的偏离叠加扰动推算（风温/抽力直接节焦）。
//   - 风量为产量通道：提高铁水产量但单位焦比不变，不参与焦比/煤比推算。
//   - 设定煤比原样读取（滑块/输入值即基准），不再做「总燃料比守恒」补偿——
//     焦比降低由置换比显式驱动。
// ============================================================================

import { DEFAULT_TFT_CONFIG, enrichFromFlow } from './tft.js'
import { PROCESS_MAP } from '../data/flowLibrary.js'
// 混合煤单一数据源：喷吹煤粉建模为 N 种煤的加权混合。
// 默认混合（无烟煤/烟煤各 50%）加权后 == 原 tft.js 固定值，故「默认混合」下 RR 仍为 0.89，
// 与迁移前完全一致；用户在物料界面改比例/成分后，RR 经混合煤成分实时重算。
import { DEFAULT_PC_FUEL_CONFIG, compositionToFuelConfig, blendedComposition } from './coalBlend.js'

// 名义工况基准（与后端 calculators._bf_effective_fuel 常量一致）
// 「模板=基准，自动跟随」：基准煤比/风温动态读取 flowLibrary 模板默认值——
//  - 基准煤比 = 高炉模板 coal_inj def（当前 130，改模板后前端自动跟随）
//  - 基准风温 = 高炉模板 hot_blast_temp 默认（当前 1200，改模板后自动跟随；与高炉默认风温对齐使默认工况无扰动）
// 效果：模板默认工况下无扰动（前端显示 = 模板值）；偏离模板（拖煤比/调风温/富氧）才联动。
const _templateDef = (type, key) => {
  const t = PROCESS_MAP[type]
  const p = t && t.params && t.params.find((x) => x.key === key)
  return p && p.def != null ? p.def : null
}
export const BF_NOMINAL = {
  wind: 600,        // 风量基准 kNm³/h = 相对 1.0 倍
  temp: _templateDef('blast_furnace', 'hot_blast_temp') ?? 1250,  // 风温扰动基准 ℃（= 高炉模板 hot_blast_temp 默认 1200，与默认风温对齐 → 默认工况无扰动、焦比锚点=显示值）
  o2air: 21,        // 空气氧含量基准 %
  coal: _templateDef('blast_furnace', 'coal_inj') ?? 175,  // 基准煤比 kg/tFe（= 高炉模板 coal_inj def，喷煤置换零点）
  cokeMin: 300,     // 焦比夹取下限 kg/tFe
  cokeMax: 560,     // 焦比夹取上限 kg/tFe
  coalMax: 220,     // 煤比夹取上限 kg/tFe（与模板 coal_inj.max=220 对齐：基准煤比设定上限即物理上限，富氧派生有效煤比不再超出）
  oxyCoal: 15,    // 每 1% 富氧允许多喷煤粉 kg/tFe（富氧派生煤比系数，实测出处见文件头注释）
}

// 喷煤置换比（Geerdes 公式，The Coal Handbook [17.11]）：
//   RR% = 2·C% + 2.5·H% − 2·H₂O% + 0.9·Ash% − 86
// C/H 取元素分析（Celem/H），H₂O/Ash 取收到基工业分析；成分取自混合煤（coalBlend）加权值，
// 换煤种/改比例后 RR 自动跟随。默认混合（Celem 0.83 / H 0.04 / H2O 0.05 / Ash 0.10）→ 0.89。
// 注：RR < 1 时 Δ燃料比 = Δ煤比×(1−RR) > 0，即富氧/增煤后「燃料比微升」属正常工程现象，
//     富氧的真实收益是提产 + 以煤代焦（降焦比、降成本），而非降燃料比。
export function calcReplacementRatio(pc) {
  const f = pc || DEFAULT_PC_FUEL_CONFIG || {}
  const c = f.Celem != null ? f.Celem : 0.83
  const h = f.H != null ? f.H : 0.04
  const m = f.H2O != null ? f.H2O : 0.05
  const a = f.Ash != null ? f.Ash : 0.10
  return (2 * c * 100 + 2.5 * h * 100 - 2 * m * 100 + 0.9 * a * 100 - 86) / 100
}

// 模块级默认 RR（默认混合煤，RR≈0.89）——不传 overrides 时（如旧调用）保持现状。
const RR = calcReplacementRatio()

export function bfFuelRates(p = {}, overrides = null) {
  // 混合煤口径：传入 materialOverrides 时，用混合煤加权成分实算 RR；
  // 否则回退模块级默认 RR（默认混合，0.89），保持迁移中性。
  const rr = overrides ? calcReplacementRatio(compositionToFuelConfig(blendedComposition(overrides))) : RR
  // 基准焦比：参数 coke_rate 表征「名义工况（煤比=基准煤比、无操作扰动）下的焦比」，
  // 作为耦合锚点；设定煤比/操作参数引起的焦比偏移均叠加其上。
  const anchorCoke = p.coke_rate != null ? p.coke_rate : 470
  const coal0 = p.coal_inj // 可能 undefined：节点未定义喷煤时不应用置换耦合
  const wind = p.wind_rate, tB = p.hot_blast_temp, draft = p.draft
  // 富氧率：优先由纯氧流量 o2_flow（设备 knob）按物理混合反算；缺省时回退原 oxygen_enrich 参数（兼容存量工况）
  const o2 = p.o2_flow != null
    ? enrichFromFlow(p.wind_rate, p.hot_metal, p.o2_flow, p.blast_humidity)
    : (p.oxygen_enrich != null ? p.oxygen_enrich : 0)
  const hasOp = wind != null || tB != null || o2 != null || draft != null
  const coalOxy = o2 != null ? BF_NOMINAL.oxyCoal * o2 : 0

  // 操作扰动项（风温/抽力对焦炭的偏移，与煤比无关，共用）：
  // 风量(wind_rate)是产量通道——提高产量但单位焦比不变，故不参与焦比/煤比推算；
  // 富氧不再直接节焦——其作用已通过「派生煤比 +15/1% → 喷煤置换 → 焦比联动」体现。
  let dCokeOp = 0
  if (hasOp) {
    const tempF = tB != null ? tB / BF_NOMINAL.temp : 1.0
    const draftF = draft != null ? draft : 1.0
    // 风温↑/抽力↑ → 焦比下降（敏感性系数经验取值，与后端 d_coke 完全一致）
    dCokeOp = -250 * (tempF - 1) - 30 * (draftF - 1)
  }

  const coalBase = coal0 != null ? Math.max(0, Math.min(BF_NOMINAL.coalMax, coal0)) : null
  const coal = coalBase != null
    ? Math.max(0, Math.min(BF_NOMINAL.coalMax, coalBase + coalOxy))
    : 150

  // 模式 A：焦比作为独立可调轴（由调用方显式传 coke_rate_set 触发）。
  //   直接取设定焦比，煤比保持冻结（= 基础 coal_inj + 富氧派生），不随焦比反推——
  //   即「调节焦比，其他项不动」。氧/煤耦合（富氧↑→煤比↑、焦比↓）由模式 B 负责，不受影响。
  const setCoke = p.coke_rate_set != null ? p.coke_rate_set : null
  if (setCoke != null) {
    const coke = Math.max(BF_NOMINAL.cokeMin, Math.min(BF_NOMINAL.cokeMax, setCoke))
    return { coke, coal, coalBase, coalOxy, oxygen_enrich: o2 }
  }

  // 模式 B（默认）：焦比由喷煤置换 + 操作扰动派生。
  // 焦比 = 基准焦比 + 喷煤置换(−RR·Δ煤比) + 操作扰动
  // 喷煤置换：Δ焦比 = −RR × (有效煤比 − 名义基准煤比)。有效煤比（含富氧增量）偏离基准
  // 越多焦比反向联动；无煤比参数（节点未定义喷煤）时不耦合。
  const dCoke = coalBase != null ? -rr * (coal - BF_NOMINAL.coal) : 0
  const coke = Math.max(BF_NOMINAL.cokeMin, Math.min(BF_NOMINAL.cokeMax, anchorCoke + dCoke + dCokeOp))
  // 煤比返回有效值（设定煤比 + 富氧增量），供排放链路/TFT 直接消费；
  // coalBase 为设定值（clamp 后），coalOxy 为富氧增量，供界面拆分展示。
  return { coke, coal, coalBase, coalOxy, oxygen_enrich: o2 }
}

// 便捷：把「操作参数 + 额外覆盖(如扫描轴取值)」折算为含推算焦比/煤比的完整参数集。
// 用途：TFT 弹窗/设备面板计算 TFT 与 CO₂ 时，先经此函数注入推算后的燃料用量，
//       保证与主流程排放链路（compute.js bfFuelRates）取值一致。
// 例：effFuelParams(baseParams, { coal_inj: 200 })
//     → { ...baseParams, coal_inj: 200, coke_rate: 推算值 }
// 附加字段（供界面拆分展示）：
//   coal_inj_base —— 设定煤比（clamp 后，不含富氧增量）
//   coal_oxy_inc  —— 富氧派生煤比增量（= 15 × 富氧率，0 表示无富氧）
export function effFuelParams(base = {}, extra = {}, overrides = null) {
  const merged = { ...base, ...extra }
  const { coke, coal, coalBase, coalOxy, oxygen_enrich } = bfFuelRates(merged, overrides)
  return { ...merged, coke_rate: coke, coal_inj: coal, coal_inj_base: coalBase, coal_oxy_inc: coalOxy, oxygen_enrich }
}
