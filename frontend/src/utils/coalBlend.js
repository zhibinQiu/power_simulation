// ============================================================================
// 喷吹煤粉配煤混合（可扩展 N 种煤）—— 单一数据源 + 加权计算
// ----------------------------------------------------------------------------
// 现实中的 PCI 喷吹煤粉是多种煤（无烟煤 / 烟煤 / 其他）按一定比例混合磨制的。
// 本模块把"喷吹煤粉"建模为 N 种煤的加权混合：
//   - 每种煤含「占比(ratio) + 成分(comp)」；
//   - 有效成分 = Σ(ratio_i × comp_i)   （质量分数加权，ratio 自动归一化到和为 1）；
//   - 有效成分再换算为 TFT/置换比/CO₂/炉渣碱度所需的参数。
//
// 默认混合（50% 无烟煤 + 50% 烟煤）加权后 == 原 tft.js / slagBasicity 写死值，
// 因此「从无混合 → 用默认混合」在数值上完全中性，不会改动既有仿真结果；
// 用户一旦在物料界面改比例或成分，仿真即联动（TFT / RR / CO₂ / 碱度同时生效）。
// ============================================================================

import { DEFAULT_TFT_CONFIG } from './tft.js'
import { CO2_DEFAULTS } from './co2.js'

// 默认配煤：无烟煤(高固定碳/低氢) + 烟煤(低固定碳/高氢)，各 50%。
// 加权后：fc=81, c=83, h=4, ash=10, h2o=5, decomp=0.35, carbon_pct=69.95, 灰分组成=原默认值，
// 与迁移前 tft.js 固定值(FC 0.81/Celem 0.83/H 0.04/Ash 0.10/H2O 0.05/decomp 0.35) 逐位一致。
// （注意：无烟煤 fc=86、烟煤 fc=76 → 加权 81，对应 TFT 用的固定碳 FC=0.81）
export const DEFAULT_PC_BLEND = [
  {
    id: 'anthracite', name: '无烟煤', ratio: 0.8,
    comp: {
      c: 88, h: 2.5, fc: 86, ash: 8.5, h2o: 3, decomp: 0.28, carbon_pct: 69.95,
      ash_cao: 4, ash_sio2: 46, ash_al2o3: 30, ash_mgo: 1.2, ash_fe2o3: 8, ash_base: 1.0, ash_so3: 2.0,
    },
  },
  {
    id: 'bituminous', name: '烟煤', ratio: 0.2,
    comp: {
      c: 78, h: 5.5, fc: 76, ash: 11.5, h2o: 7, decomp: 0.42, carbon_pct: 69.95,
      ash_cao: 6, ash_sio2: 42, ash_al2o3: 26, ash_mgo: 1.8, ash_fe2o3: 10, ash_base: 1.5, ash_so3: 2.4,
    },
  },
]

// 成分键集合（用于加权）。
const COMP_KEYS = [
  'c', 'h', 'fc', 'ash', 'h2o', 'decomp', 'carbon_pct',
  'ash_cao', 'ash_sio2', 'ash_al2o3', 'ash_mgo', 'ash_fe2o3', 'ash_base', 'ash_so3',
]

// 读取当前混合：优先取 materialOverrides[id].blend（用户在物料界面编辑后的），否则默认混合。
export function getCoalBlend(overrides, matId = 'pulverized_coal') {
  const ov = overrides && overrides[matId]
  if (ov && Array.isArray(ov.blend) && ov.blend.length) return ov.blend
  return DEFAULT_PC_BLEND
}

// 归一化占比到和为 1（任一占比 ≤0 视为 0；全 0 时退化为等权）。
export function normalizeBlend(blend) {
  const sum = blend.reduce((s, x) => s + (Number(x.ratio) || 0), 0)
  if (!(sum > 0)) {
    const n = blend.length || 1
    return blend.map((x) => ({ ...x, ratio: 1 / n }))
  }
  return blend.map((x) => ({ ...x, ratio: (Number(x.ratio) || 0) / sum }))
}

// 加权有效成分（质量分数 %），供 TFT / 碱度 / CO₂ 使用。
export function blendedComposition(overrides, matId = 'pulverized_coal') {
  const blend = normalizeBlend(getCoalBlend(overrides, matId))
  const out = {}
  for (const k of COMP_KEYS) {
    out[k] = blend.reduce((s, x) => s + (Number(x.comp && x.comp[k]) || 0) * x.ratio, 0)
  }
  return out
}

// 加权成分（%）→ tft fuels.pulverized_coal 配置（分数制）。
export function compositionToFuelConfig(comp) {
  return {
    enabled: true,
    fuel_type: 'solid',
    name: '喷吹煤粉',
    rateKey: 'coal_inj',
    FC: (comp.fc || 0) / 100,
    Celem: (comp.c || 0) / 100,
    H: (comp.h || 0) / 100,
    Ash: (comp.ash || 0) / 100,
    H2O: (comp.h2o || 0) / 100,
    decomp_heat: comp.decomp || 0,
  }
}

// TFT 配置：注入混合煤燃料参数（默认或用户在物料界面覆盖）。
export function makeTftConfig(overrides) {
  const comp = blendedComposition(overrides)
  const fuels = { ...DEFAULT_TFT_CONFIG.fuels, pulverized_coal: compositionToFuelConfig(comp) }
  return { ...DEFAULT_TFT_CONFIG, fuels }
}

// CO₂ 配置：注入混合煤等效碳含量（NCV×CC）。
export function makeCo2Config(overrides) {
  const comp = blendedComposition(overrides)
  return { ...CO2_DEFAULTS, coal_carbon_pct: comp.carbon_pct || CO2_DEFAULTS.coal_carbon_pct }
}

// 炉渣碱度用的煤灰组成（加权 %），与 slagBasicity 现有字段对齐。
export function pcAshComposition(overrides, matId = 'pulverized_coal') {
  const comp = blendedComposition(overrides, matId)
  return {
    ash: comp.ash,
    ash_cao: comp.ash_cao, ash_sio2: comp.ash_sio2, ash_al2o3: comp.ash_al2o3,
    ash_mgo: comp.ash_mgo, ash_fe2o3: comp.ash_fe2o3, ash_base: comp.ash_base, ash_so3: comp.ash_so3,
  }
}

// 混合煤燃料配置（分数制），供 bfFuel 置换比默认口径使用（避免与物料界面脱节）。
export const DEFAULT_PC_FUEL_CONFIG = compositionToFuelConfig(blendedComposition({}))
