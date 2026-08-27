// 高炉炉渣碱度估算（R₂ = CaO/SiO₂，R₃ = (CaO+MgO)/SiO₂，均为入渣氧化物，kg/tFe）
// -----------------------------------------------------------------------------
// 六个 CaO/SiO₂ 来源（每吨铁水口径）：
//   1. 烧结矿脉石  = 烧结矿入炉比 × 烧结矿 CaO%/SiO₂%（物料面板「详细化学成分」）
//   2. 球团脉石    = 球团入炉比   × 球团 CaO%/SiO₂%
//   3. 块矿脉石    = 块矿入炉比   × 块矿（铁矿石）CaO%/SiO₂%
//   4. 焦炭灰分    = 有效焦比 × 焦炭灰分 A% × 灰分中 CaO%/SiO₂%（灰分组成）
//   5. 煤粉灰分    = 有效煤比 × 煤粉灰分 A% × 灰分中 CaO%/SiO₂%（灰分组成）
//   6. 熔剂(石灰石) = 熔剂比 × 石灰石 CaO%/SiO₂%
// 扣减项：Si 还原入铁水 —— [Si]≈0.5% 时消耗 SiO₂ = 1000×0.5%×60/28 ≈ 10.7 kg/t
//         （SiO₂ + 2C → Si + 2CO，硅入铁后不再存在于渣中）
// 燃料量取 bfFuelRates 有效值（含富氧派生煤比 +15/1% 与喷煤置换联动、风温/抽力节焦），
// 与主流程排放链路（compute.js）口径一致：富氧↑ → 煤比↑ → 煤灰↑ → SiO₂↑ → R₂↓。
// 成分默认值与 data/materialComp.js COMP_DEFS 一致，覆盖值读 materialOverrides。
import { bfFuelRates } from './bfFuel'
import { compValue } from '../data/materialComp'
// 混合煤单一数据源：煤粉灰分组成/灰分总量取自 N 种煤的加权混合（coalBlend），
// 使炉渣碱度随用户在物料界面编辑的配煤比例/成分实时联动；默认混合下 == 原 COMP_DEFS 值。
import { pcAshComposition } from './coalBlend.js'

// [Si] 入铁水假设（%）→ SiO₂ 扣减；高炉常规冶炼 [Si] 0.3–0.7%
const SI_IN_HM = 0.5

export function calcSlagBasicity(p = {}, overrides = {}) {
  // ---- 燃料有效量（富氧置换联动后）----
  const eff = bfFuelRates(p)
  const coke = p.coke_rate != null ? eff.coke : 0
  const coal = p.coal_inj != null ? eff.coal : 0

  // ---- 炉料结构（百分比配比 → kg/tFe，旧版绝对值参数 s_inter_ratio>100 时兼容直读）----
  // 各矿量 = 总矿量 × 配比 / Σ配比（配比未归一化也自动归一，如 78/12/10 或 40/40/20 均可）
  const burdenTotal = p.burden_total != null ? Number(p.burden_total) : 1625
  let sinter, pellet, lump
  const legacyTotal = p.sinter_ratio != null && Number(p.sinter_ratio) > 100
  if (legacyTotal) {   // 旧版绝对值方案（1270/195/160），直接沿用，不做百分比换算
    sinter = Number(p.sinter_ratio) || 0
    pellet = Number(p.pellet_ratio) || 0
    lump = Number(p.lump_ratio) || 0
  } else {
    const sp = p.sinter_pct != null ? Number(p.sinter_pct) : 78
    const pp = p.pellet_pct != null ? Number(p.pellet_pct) : 12
    const lp = p.lump_pct != null ? Number(p.lump_pct) : 10
    const pSum = sp + pp + lp
    sinter = pSum > 0 ? burdenTotal * sp / pSum : 0
    pellet = pSum > 0 ? burdenTotal * pp / pSum : 0
    lump = pSum > 0 ? burdenTotal * lp / pSum : 0
  }
  const flux = p.flux != null ? Number(p.flux) : 120

  // ---- 各来源氧化物贡献（kg/tFe）----
  const mk = (rate, matId) => ({
    cao: rate * compValue(overrides, matId, 'cao') / 100,
    sio2: rate * compValue(overrides, matId, 'sio2') / 100,
    mgo: rate * compValue(overrides, matId, 'mgo') / 100,
    al2o3: rate * compValue(overrides, matId, 'al2o3') / 100,
  })
  // 燃料灰分：用量 × 灰分总量 A% × 灰分组成 ash_*%
  const mkAsh = (rate, matId) => {
    const ash = rate * compValue(overrides, matId, 'ash') / 100
    return {
      cao: ash * compValue(overrides, matId, 'ash_cao') / 100,
      sio2: ash * compValue(overrides, matId, 'ash_sio2') / 100,
      mgo: ash * compValue(overrides, matId, 'ash_mgo') / 100,
      al2o3: ash * compValue(overrides, matId, 'ash_al2o3') / 100,
    }
  }
  // 煤粉灰分：取自混合煤加权灰分组成（coalBlend.pcAshComposition）。
  // 混合煤下，煤粉灰分总量与灰分内组成均由各煤种按占比加权得出，
  // 用户在物料界面改比例/成分即联动炉渣碱度；默认混合下 == 原 COMP_DEFS 单值。
  const pcAsh = pcAshComposition(overrides, 'pulverized_coal')
  const mkPcAsh = (rate) => {
    const ash = rate * (pcAsh.ash || 0) / 100
    return {
      cao: ash * (pcAsh.ash_cao || 0) / 100,
      sio2: ash * (pcAsh.ash_sio2 || 0) / 100,
      mgo: ash * (pcAsh.ash_mgo || 0) / 100,
      al2o3: ash * (pcAsh.ash_al2o3 || 0) / 100,
    }
  }

  const parts = [
    { name: '烧结矿', rate: sinter, ...mk(sinter, 'sinter') },
    { name: '球团', rate: pellet, ...mk(pellet, 'pellet') },
    { name: '块矿', rate: lump, ...mk(lump, 'iron_ore') },
    { name: '焦炭灰分', rate: coke, ...mkAsh(coke, 'coke') },
    { name: '煤粉灰分', rate: coal, ...mkPcAsh(coal) },
    { name: '熔剂(石灰石)', rate: flux, ...mk(flux, 'limestone') },
  ]

  const caoTotal = parts.reduce((s, x) => s + x.cao, 0)
  const sio2Gross = parts.reduce((s, x) => s + x.sio2, 0)
  const siDeduct = 1000 * (SI_IN_HM / 100) * 60 / 28     // SiO₂ → Si 入铁水扣减
  const sio2Total = Math.max(0, sio2Gross - siDeduct)
  const r2 = sio2Total > 0 ? caoTotal / sio2Total : 0

  // 渣量交叉校验估算（四大氧化物 + FeO/S 等杂项约 5%）——与节点设定渣比对比
  const mgoTotal = parts.reduce((s, x) => s + x.mgo, 0)
  const al2o3Total = parts.reduce((s, x) => s + x.al2o3, 0)
  const slagEst = (caoTotal + sio2Total + mgoTotal + al2o3Total) * 1.05

  // 炉渣氧化物成分（CaO/SiO₂/MgO/Al₂O₃ 质量分数，%）：四者之和≈100，余量为 FeO/S/CaS 等
  const sum4 = caoTotal + sio2Total + mgoTotal + al2o3Total
  const comp = sum4 > 0
    ? {
        cao: caoTotal / sum4 * 100,
        sio2: sio2Total / sum4 * 100,
        mgo: mgoTotal / sum4 * 100,
        al2o3: al2o3Total / sum4 * 100,
      }
    : { cao: 0, sio2: 0, mgo: 0, al2o3: 0 }

  // 三元碱度 R₃ = (CaO+MgO)/SiO₂：在 R₂ 基础上计入 MgO 碱性，比 R₂ 更全面地反映炉渣碱度（仍只以 SiO₂ 为酸性分母）
  const r3 = sio2Total > 0 ? (caoTotal + mgoTotal) / sio2Total : 0
  const r3Level = r3 < 1.40
    ? { txt: '偏低（参考）', cls: 'low' }
    : r3 <= 1.55
      ? { txt: '适宜区间（参考）', cls: 'ok' }
      : { txt: '偏高（参考）', cls: 'high' }

  // 适宜区间判定（国内高炉常规冶炼 R₂ 1.15–1.25）
  const level = r2 < 1.15
    ? { txt: '偏低 · 脱硫能力不足', cls: 'low' }
    : r2 <= 1.25
      ? { txt: '适宜区间', cls: 'ok' }
      : { txt: '偏高 · 渣流动性下降', cls: 'high' }

  return { r2, r3, comp, caoTotal, mgoTotal, al2o3Total, sio2Gross, sio2Total, siDeduct, slagEst, parts, coke, coal, level, r3Level, sum4 }
}
