// ============================================================================
// 高炉正向一体化计算引擎（纯前端 JS 版）
// ----------------------------------------------------------------------------
// 移植自 TFT 模型目录 theoretical_calculation.py 的 calc_forward / 
// calc_material_balance / calc_heat_balance / calc_tft（论文 §3.1 式3-1~3-26、
// §3.2 第一种热平衡、回旋区 TFT），与 Python 版逐式对齐。
//
// 用法（前端可编辑参数面板的纯前端计算源）：
//   import { forwardCalc, forwardDefaults } from '../utils/bfForward.js'
//   const result = forwardCalc({ coke_rate: 340, V_B: 1121, ... })
//   const defaults = forwardDefaults()
//
// 返回结构（与平台 BfForwardDialog 结果展示一一对应）：
//   { inputs, material, reduction, heat, co2, diagnostics }
//
// 直接还原度 r_d 由碳平衡二分反推（不再作为输入）；Fe/碳/质量残差为一致性诊断。
// ============================================================================

// ---- 1. 物理化学常数（与 Python 版一致）----
export const BF_CONST = {
  VM: 22.4,          // 标准摩尔体积 L/mol
  M_C: 12.011, M_O2: 32.00, M_H2O: 18.015, M_H2: 2.016, M_N2: 28.014,
  M_CO: 28.010, M_CO2: 44.010, M_Fe: 55.845, M_FeO: 71.844, M_Fe2O3: 159.687,
  M_SiO2: 60.084, M_MnO: 70.937, M_MnO2: 86.937, M_CaO: 56.077, M_MgO: 40.304,
  M_Al2O3: 101.961, M_Ti: 47.867, M_CaS: 72.143, M_S: 32.065, M_Si: 28.086,
  M_Mn: 54.938, M_P: 30.974,
  O2_AIR: 0.21, N2_AIR: 0.79,
  // 热化学常数
  Q_C_TO_CO: 9215.0,        // C + 1/2 O2 -> CO  kJ/kg(C)
  Q_H2O_DECOMP: 10800.0,    // H2O 分解 kJ/Nm3(H2O)
  Q_SLAG_FORM: 1594.4,      // CaO + SiO2 -> CaSiO3  kJ/kg(CaO)
  Q_DESULF: 21000.0,        // 脱硫 kJ/kg(S)
  Q_DIRECT_FE_KMOL: 152000.0, Q_DIRECT_SI_KMOL: 620000.0,
  Q_DIRECT_TI_KMOL: 944000.0, Q_DIRECT_MN_KMOL: 274000.0, Q_DIRECT_P_KMOL: 920000.0,
  Q_CO_OXID: 283000.0 / 22.4,   // CO + 1/2 O2 -> CO2  kJ/Nm3(CO)
  Q_H2_OXID: 241800.0 / 22.4,   // H2 + 1/2 O2 -> H2O  kJ/Nm3(H2)
}

const { VM, M_C, M_O2, M_H2O, M_H2, M_N2, M_CO, M_CO2, M_Fe, M_FeO, M_Fe2O3,
  M_SiO2, M_MnO, M_MnO2, M_Ti, M_Si, M_Mn, M_P, M_S, N2_AIR,
  Q_C_TO_CO, Q_H2O_DECOMP, Q_SLAG_FORM, Q_DESULF,
  Q_DIRECT_FE_KMOL, Q_DIRECT_SI_KMOL, Q_DIRECT_TI_KMOL, Q_DIRECT_MN_KMOL, Q_DIRECT_P_KMOL,
  Q_CO_OXID, Q_H2_OXID } = BF_CONST

const Q_C_TO_CO_KMOL = Q_C_TO_CO * M_C
const Q_FEO_DECOMP_DIR = (Q_DIRECT_FE_KMOL + Q_C_TO_CO_KMOL) / M_Fe
const Q_FEO_DECOMP_IND = (283000.0 - 13100.0) / M_Fe
const Q_FEO_DECOMP_H2 = (241800.0 + 30100.0) / VM
const Q_FE2O3_DECOMP = (283000.0 - 2800.0) / M_Fe2O3
const Q_SIO2_DECOMP = (Q_DIRECT_SI_KMOL + 2 * Q_C_TO_CO_KMOL) / M_Si
const Q_TIO2_DECOMP = (Q_DIRECT_TI_KMOL + 2 * Q_C_TO_CO_KMOL) / M_Ti
const Q_MNO_DECOMP = (Q_DIRECT_MN_KMOL + Q_C_TO_CO_KMOL) / M_Mn
const Q_P2O5_DECOMP = (Q_DIRECT_P_KMOL + 2.5 * Q_C_TO_CO_KMOL) / M_P

// ---- 2. 气体平均比热容（0~T ℃, kJ/(Nm3·℃) 多项式，与 Python gas_mean_cp 一致）----
const GAS_CP_COEFFS = {
  CO: [1.2993, 1.068e-4, -2.93e-8, 4.11e-12],
  N2: [1.2987, 9.65e-5, -2.35e-8, 3.30e-12],
  H2: [1.2783, 6.12e-5, -1.03e-8, 1.18e-12],
  O2: [1.3065, 1.59e-4, -4.03e-8, 5.59e-12],
  air: [1.2987, 1.05e-4, -2.69e-8, 3.78e-12],
  H2O: [1.4935, 9.82e-5, -2.08e-8, 2.67e-12],
  CO2: [1.6602, 3.49e-4, -8.42e-8, 1.04e-11],
}
export function gasMeanCp(gasType, T) {
  const [a, b, c, d] = GAS_CP_COEFFS[gasType] || GAS_CP_COEFFS.air
  return a + b * T + c * T * T + d * T * T * T
}

// ---- 3. 默认输入（后端默认值，前端可修改；与 materialComp.js def 值一致）----
export function defaultInputs() {
  return {
    sinter: { Fe: 57.5, FeO: 8.5, CaO: 10.5, SiO2: 5.2, MgO: 2.0, Al2O3: 1.6,
              S: 0.02, TiO2: 0.30, MnO2: 0.475, P: 0.05, LOI: 0.5 },
    pellet: { Fe: 63.5, FeO: 0.8, CaO: 1.2, SiO2: 4.5, MgO: 0.8, Al2O3: 0.8,
              S: 0.005, TiO2: 0.30, MnO2: 0.396, P: 0.03, LOI: 0.2 },
    lump: { Fe: 62.0, FeO: 0.5, CaO: 0.2, SiO2: 5.5, MgO: 0.3, Al2O3: 2.5,
            S: 0.03, TiO2: 0.20, MnO2: 0.317, P: 0.05, LOI: 1.0 },
    coke: { FC: 86.0, VM: 1.2, Ash: 12.5, H2O: 0.0,
            Ash_CaO: 0.4375, Ash_SiO2: 5.875, Ash_MgO: 0.15, Ash_Al2O3: 4.0,
            Ash_Fe: 0.875, Ash_MnO2: 0.0, Ash_S: 0.70 },
    coal: { FC: 75.0, VM: 10.0, Ash: 10.0, H2O: 5.0,
            Ash_CaO: 0.50, Ash_SiO2: 4.40, Ash_MgO: 0.15, Ash_Al2O3: 2.80,
            Ash_Fe: 0.90, Ash_MnO2: 0.0, Ash_S: 0.50 },
    dust: { TFe: 42.0, C: 16.0, CaO: 10.0, SiO2: 8.0, MgO: 2.0, Al2O3: 3.0,
            S: 0.5, MnO2: 0.0 },
    iron: { Fe: 94.5, C: 4.5, Si: 0.50, Ti: 0.10, S: 0.04, Mn: 0.40, P: 0.12 },
    slag: { R: 1.15, eta_Fe: 0.9975, eta_Mn: 0.75 },
    proc: {
      blast_temp: 1150.0, blast_humidity: 10.0, oxygen_enrich: 3.0, natural_gas: 0.0,
      rd: 0.45, eta_H2: 0.40,
      T_top: 200.0, T_pig: 1500.0, T_dust: 200.0, T_slag: 1500.0,
      coke_temp: 1500.0, coal_temp: 25.0,
      cp_coke: 1.488, cp_coal: 1.0, coal_decomp_heat: 1200.0, rd0: 0.40,
    },
  }
}

// ---- 4. 核心：物料平衡（式3-1 ~ 3-26）----
function fe2o3Of(ore) {
  if (ore.Fe2O3 > 0) return ore.Fe2O3
  const feFromFeo = ore.FeO * M_Fe / M_FeO
  const c = (ore.Fe - feFromFeo) * M_Fe2O3 / (2 * M_Fe)
  return (c <= 100) ? Math.max(c, 0.0) : 0.0
}

export function calcMaterialBalance(inputs, opts = {}) {
  // inputs: { sinter, pellet, lump, coke, coal, dust, iron, slag, proc }
  // opts:   { coke_rate, coal_rate, ore_mix, ore_total_override, V_B_override, m_MI, mat_MI }
  const { sinter, pellet, lump, coke, coal, dust, iron, slag, proc } = inputs
  const cokeRate = opts.coke_rate ?? 340.0
  const coalRate = opts.coal_rate ?? 180.0
  const oreMix = opts.ore_mix ?? [0.62, 0.314, 0.066]
  const mMI = opts.m_MI ?? 0.0
  const matMI = opts.mat_MI ?? null

  const res = {
    m_Pig: 1000.0, m_Coke: cokeRate, m_Coal: coalRate, m_Dust: 15.0, m_MI: mMI,
  }

  const _s = oreMix[0] + oreMix[1] + oreMix[2]
  const rSin = oreMix[0] / _s, rPel = oreMix[1] / _s, rLump = oreMix[2] / _s

  const sinterFe2O3 = fe2o3Of(sinter)
  const pelletFe2O3 = fe2o3Of(pellet)
  const lumpFe2O3 = fe2o3Of(lump)
  const matMIFe2O3 = matMI ? fe2o3Of(matMI) : 0.0

  // ---- 式(3-1) Fe 平衡 ----
  const FePig = (iron.Fe / 100.0) * 1000.0
  const FeToSlag = FePig * (1.0 - slag.eta_Fe) / slag.eta_Fe
  const FeToDust = res.m_Dust * dust.TFe / 100.0
  const FeFromFuel = (cokeRate * (coke.Ash_Fe || 0) / 100.0 + coalRate * (coal.Ash_Fe || 0) / 100.0)
  const FeTarget = FePig / slag.eta_Fe + FeToDust
  const FeFromMI = matMI ? (mMI * matMI.Fe / 100.0) : 0.0
  const FeBlend = (rSin * sinter.Fe + rPel * pellet.Fe + rLump * lump.Fe) / 100.0

  let oreTotal
  if (opts.ore_total_override != null) {
    oreTotal = Math.max(opts.ore_total_override, 0.0)
  } else {
    oreTotal = FeBlend > 0 ? Math.max((FeTarget - FeFromFuel - FeFromMI) / FeBlend, 0.0) : 0.0
  }
  res.oreTotal = oreTotal
  res.m_Sin = oreTotal * rSin
  res.m_Pel = oreTotal * rPel
  res.m_Lump = oreTotal * rLump

  // ---- 式(3-2) 碱度 ----
  const CaOIn = ((res.m_Sin * sinter.CaO + res.m_Pel * pellet.CaO + res.m_Lump * lump.CaO +
                  res.m_Coke * coke.Ash_CaO + res.m_Coal * coal.Ash_CaO - res.m_Dust * dust.CaO) / 100.0
                 + (matMI ? (mMI * matMI.CaO / 100.0) : 0.0))
  const SiO2In = ((res.m_Sin * sinter.SiO2 + res.m_Pel * pellet.SiO2 + res.m_Lump * lump.SiO2 +
                   res.m_Coke * coke.Ash_SiO2 + res.m_Coal * coal.Ash_SiO2 - res.m_Dust * dust.SiO2) / 100.0
                  + (matMI ? (mMI * matMI.SiO2 / 100.0) : 0.0)
                  - (iron.Si / 100.0) * 1000.0 * M_SiO2 / M_Si
                  - (iron.Ti / 100.0) * 1000.0 * M_SiO2 / M_Ti)
  res.R_calc = SiO2In > 0 ? CaOIn / SiO2In : 0.0

  // ---- 式(3-3)~(3-6) 渣量骨干 ----
  res.m_CaO_slag = CaOIn
  res.m_MgO_slag = ((res.m_Sin * sinter.MgO + res.m_Pel * pellet.MgO + res.m_Lump * lump.MgO +
                     res.m_Coke * coke.Ash_MgO + res.m_Coal * coal.Ash_MgO - res.m_Dust * dust.MgO) / 100.0
                    + (matMI ? (mMI * matMI.MgO / 100.0) : 0.0))
  res.m_Al2O3_slag = ((res.m_Sin * sinter.Al2O3 + res.m_Pel * pellet.Al2O3 + res.m_Lump * lump.Al2O3 +
                       res.m_Coke * coke.Ash_Al2O3 + res.m_Coal * coal.Ash_Al2O3 - res.m_Dust * dust.Al2O3) / 100.0
                      + (matMI ? (mMI * matMI.Al2O3 / 100.0) : 0.0))
  res.m_SiO2_slag = SiO2In

  // ---- 式(3-7)~(3-9) MnO / FeO / S ----
  res.m_MnO_slag = (iron.Mn / 100.0 * 1000.0 * (71.0 / 55.0)
                    * (1.0 - slag.eta_Mn) / slag.eta_Mn)
  res.m_FeO_slag = FePig * (72.0 / 56.0) * (1.0 - slag.eta_Fe) / slag.eta_Fe

  const SInTotal = ((res.m_Sin * sinter.S + res.m_Pel * pellet.S + res.m_Lump * lump.S +
                     res.m_Coke * coke.Ash_S + res.m_Coal * coal.Ash_S) / 100.0
                    + (matMI ? (mMI * matMI.S / 100.0) : 0.0))
  const SToPig = (iron.S / 100.0) * 1000.0
  const SToDust = res.m_Dust * dust.S / 100.0
  res.S_in = SInTotal; res.S_to_pig = SToPig; res.S_to_dust = SToDust
  res.m_S_slag = Math.max(2.0 * (SInTotal / 2.0 * 0.95 - SToPig - SToDust / 2.0), 0.0)

  // ---- 式(3-10) 总渣量 ----
  res.m_Slag = (res.m_CaO_slag + res.m_MgO_slag + res.m_Al2O3_slag + res.m_SiO2_slag +
                res.m_MnO_slag + res.m_FeO_slag + 0.5 * res.m_S_slag)

  // ---- 式(3-11) 直接还原耗碳 ----
  res.m_C_dFe = (iron.Fe / 100.0) * 1000.0 * proc.rd * M_C / M_Fe
  res.m_C_dSi = (iron.Si / 100.0) * 1000.0 * 2.0 * M_C / M_Si
  res.m_C_dTi = (iron.Ti / 100.0) * 1000.0 * 2.0 * M_C / M_Ti
  res.m_C_dMn = (iron.Mn / 100.0) * 1000.0 * M_C / M_Mn
  res.m_C_dP = (iron.P / 100.0) * 1000.0 * 5.0 * M_C / (2.0 * M_P)
  res.m_C_dS = res.m_S_slag * M_C / M_S
  res.m_C_Pig = (iron.C / 100.0) * 1000.0
  res.C_to_dust = res.m_Dust * dust.C / 100.0
  res.m_C_coke_in = cokeRate * coke.FC / 100.0
  res.m_C_coal_in = coalRate * coal.FC / 100.0
  const mC_R_carbon = (res.m_C_coke_in + res.m_C_coal_in - res.m_C_dFe - res.m_C_dSi -
                       res.m_C_dTi - res.m_C_dMn - res.m_C_dP - res.m_C_dS - res.m_C_Pig - res.C_to_dust)
  res.m_C_R = mC_R_carbon

  // ---- 式(3-12) B_O2 ----
  const phi = proc.blast_humidity / 1000.0 * VM / M_H2O
  const f = proc.oxygen_enrich / 100.0
  res.B_O2 = 0.21 * (1.0 - phi) + 0.5 * phi
  const BO2Total = (1.0 - f) * res.B_O2 + f

  // ---- 式(3-13) V_O2-R / 式(3-14) V_O2-Fuel ----
  res.V_O2_R = (res.m_C_R / 24.0) * VM + 2.0 * (proc.natural_gas || 0.0)
  if (coal.O2 > 0 || coal.H2O_in > 0) {
    const mO2Coal = coalRate * (coal.O2 || 0) / 100.0
    const mH2OCoal = coalRate * (coal.H2O_in || 0) / 100.0
    res.V_O2_Fuel = ((mO2Coal + mH2OCoal * (16.0 / 18.0)) / M_O2 * VM)
  } else {
    res.V_O2_Fuel = 0.0
  }

  // ---- 式(3-15) V_B（override 时由鼓风反推 m_C-R）----
  if (opts.V_B_override != null && opts.V_B_override > 0) {
    res.V_B = opts.V_B_override
    res.m_C_R = (res.V_B * BO2Total + res.V_O2_Fuel) * 24.0 / VM - 2.0 * (proc.natural_gas || 0.0)
    res.V_O2_R = res.m_C_R / 24.0 * VM + 2.0 * (proc.natural_gas || 0.0)
    res._V_B_pinned = true
    res._carbon_resid = mC_R_carbon - res.m_C_R
  } else {
    res.V_B = (res.V_O2_R - res.V_O2_Fuel) / BO2Total
    res.m_C_R = mC_R_carbon
    res._V_B_pinned = false
    res._carbon_resid = 0.0
  }

  // ---- 式(3-18) V(CO2)_Fe2O3 准备 ----
  const mFe2O3Sin = res.m_Sin * sinterFe2O3 / 100.0
  const mFe2O3Pel = res.m_Pel * pelletFe2O3 / 100.0
  const mFe2O3Lump = res.m_Lump * lumpFe2O3 / 100.0
  const mFe2O3MI = matMI ? (mMI * matMIFe2O3 / 100.0) : 0.0
  const mFe2O3Dust = res.m_Dust * dust.TFe / 100.0 * M_Fe2O3 / (2.0 * M_Fe)
  const mMnO2Sin = res.m_Sin * sinter.MnO2 / 100.0
  const mMnO2Pel = res.m_Pel * pellet.MnO2 / 100.0
  const mMnO2Lump = res.m_Lump * lump.MnO2 / 100.0
  const mMnO2MI = matMI ? (mMI * matMI.MnO2 / 100.0) : 0.0
  const mMnO2Dust = res.m_Dust * dust.MnO2 / 100.0

  res.V_CO2_Fe2O3 = (
    ((mFe2O3Sin + mFe2O3Pel) / M_Fe2O3 + (mFe2O3Lump + mFe2O3MI - mFe2O3Dust) / M_Fe2O3 +
     (mMnO2Sin + mMnO2Pel) / M_MnO2 + (mMnO2Lump + mMnO2MI - mMnO2Dust) / M_MnO2) * VM
  )

  // ---- 式(3-20) r_d 经验式 ----
  const Tb = proc.blast_temp
  const phiH2O = proc.blast_humidity / 1000.0
  const xLamHat = (proc.natural_gas || 0.0) + coalRate / 1000.0
  const Cbar = (coal.FC / 100.0) / M_C
  const Hbar = ((coal.Vol_H2 || 0) / 100.0) / M_H2
  const lam = 0.2 * Cbar + 0.9 * Hbar
  let rdCalc = (proc.rd0 * (10.0 ** (-lam * xLamHat)) * (0.684 + 0.01 * (Tb ** 0.5))
                / (0.96 + 4.0 * phiH2O))
  rdCalc = Math.max(Math.min(rdCalc, 1.0), 0.0)
  res.rd_calc = rdCalc

  // ---- 式(3-19) V(CO2)_Fe ----
  const rIdH2 = proc.eta_H2
  res.V_CO2_Fe = (1.0 - proc.rd - rIdH2) * FePig / M_Fe * VM
  res.m_Fe2O3_net = mFe2O3Sin + mFe2O3Pel + mFe2O3Lump - mFe2O3Dust
  res.Fe_indirect = FePig * (1.0 - proc.rd)
  res.Fe_direct = FePig * proc.rd
  res.V_CO2_indirect = res.V_CO2_Fe2O3 + res.V_CO2_Fe

  // ---- 式(3-21) V(CO2)_Vol / 式(3-17) V(CO2)_Top ----
  res.V_CO2_Vol = (cokeRate * (coke.Vol_CO2 || 0) / 100.0 / M_CO2 * VM +
                   coalRate * (coal.Vol_CO2 || 0) / 100.0 / M_CO2 * VM)
  res.CO2_top = res.V_CO2_Fe2O3 + res.V_CO2_Fe + res.V_CO2_Vol

  // ---- 式(3-22) V(CO)_Top ----
  res.V_CO_raceway = res.m_C_R / M_C * VM
  res.V_CO_direct = (res.m_C_dFe + res.m_C_dSi + res.m_C_dTi + res.m_C_dMn + res.m_C_dP) / M_C * VM
  res.V_CO_Vol = (cokeRate * (coke.Vol_CO || 0) / 100.0 / M_CO * VM +
                  coalRate * (coal.Vol_CO || 0) / 100.0 / M_CO * VM)
  res.CO_top = Math.max(res.V_CO_raceway + res.V_CO_direct + res.V_CO_Vol - res.V_CO2_Fe2O3 - res.V_CO2_Fe, 0.0)

  // ---- 式(3-24) V(H2) 入炉 / 式(3-23) V(H2)_Top / 式(3-25) V(H2O)_Top ----
  const VH2Total = ((res.V_B * phi + cokeRate * (coke.Vol_H2 || 0) / 100.0 +
                     cokeRate * (coke.Vol_CH4 || 0) / 100.0 * (4.0 / 16.0) +
                     coalRate * (coal.Vol_H2 || 0) / 100.0 +
                     coalRate * (coal.H2O_in || 0) / 100.0 * (2.0 / 18.0)) / 2.0 * VM
                    + (proc.natural_gas || 0.0) / 2.0)
  res.V_H2_total = VH2Total
  res.V_H2_reacted = VH2Total * rIdH2
  res.H2_top = VH2Total * (1.0 - rIdH2)
  res.H2O_top = VH2Total * rIdH2

  // ---- 式(3-26) V(N2)_Top / 式(3-16) V_Top ----
  res.N2_top = (res.V_B * (1.0 - phi) * (1.0 - res.B_O2) +
                cokeRate * (coke.Vol_N2 || 0) / 100.0 / M_N2 * VM +
                coalRate * (coal.Vol_N2 || 0) / 100.0 / M_N2 * VM)
  res.V_Top = res.CO2_top + res.CO_top + res.H2_top + res.H2O_top + res.N2_top

  // ---- (5) 物料平衡表 ----
  const VO2Blast = res.V_B * BO2Total
  const VN2Blast = res.V_B * (1.0 - f) * (1.0 - phi) * N2_AIR
  const VH2OBlast = res.V_B * (1.0 - f) * phi
  res.mass_in_blast = (VO2Blast * M_O2 + VN2Blast * M_N2 + VH2OBlast * M_H2O) / VM
  res.mass_out_gas = (res.CO2_top * M_CO2 + res.CO_top * M_CO + res.H2O_top * M_H2O +
                      res.H2_top * M_H2 + res.N2_top * M_N2) / VM
  res.mass_in_blend = res.m_Sin + res.m_Pel + res.m_Lump + res.m_MI
  res.mass_in_fuel = res.m_Coke + res.m_Coal
  res.mass_in = res.mass_in_blend + res.mass_in_fuel + res.mass_in_blast
  res.mass_out_pig = res.m_Pig
  res.mass_out_slag = res.m_Slag
  res.mass_out_dust = res.m_Dust
  res.mass_out = res.mass_out_pig + res.mass_out_slag + res.mass_out_dust + res.mass_out_gas
  res.error = res.mass_out > 0 ? Math.abs(res.mass_in - res.mass_out) / res.mass_out * 100.0 : 0.0

  return res
}

// ---- 5. 热平衡（§3.2 第一种热平衡）----
export function calcHeatBalance(mb, inputs) {
  const { proc, iron, coal, slag } = inputs
  const hb = {}

  hb.Q_CR = mb.m_C_R * Q_C_TO_CO
  const mCdTotal = mb.m_C_dFe + mb.m_C_dSi + mb.m_C_dTi + mb.m_C_dMn + mb.m_C_dP + mb.m_C_dS
  hb.Q_Cd = mCdTotal * Q_C_TO_CO
  hb.Q_CO_oxid = mb.V_CO2_indirect * Q_CO_OXID
  hb.Q_H2_oxid = mb.V_H2_reacted * Q_H2_OXID

  const phi = proc.blast_humidity / 1000.0 * VM / M_H2O
  const f = proc.oxygen_enrich / 100.0
  const VH2OBlast = mb.V_B * (1.0 - f) * phi
  const cpBlast = gasMeanCp('air', proc.blast_temp)
  const cpH2Ov = gasMeanCp('H2O', proc.blast_temp)
  hb.Q_BR_sensible = mb.V_B * (1.0 - f) * cpBlast * proc.blast_temp + VH2OBlast * cpH2Ov * proc.blast_temp
  hb.Q_BR_moisture = Q_H2O_DECOMP * VH2OBlast
  hb.Q_BR = hb.Q_BR_sensible - hb.Q_BR_moisture
  hb.Q_slag_form = mb.m_CaO_slag * Q_SLAG_FORM

  hb.Q_in_total = hb.Q_CR + hb.Q_Cd + hb.Q_CO_oxid + hb.Q_H2_oxid + hb.Q_BR + hb.Q_slag_form

  hb.Q_d_Fe2O3 = mb.m_Fe2O3_net * Q_FE2O3_DECOMP
  hb.Q_d_Fe_dir = mb.Fe_direct * Q_FEO_DECOMP_DIR
  hb.Q_d_Fe_ind = mb.Fe_indirect * Q_FEO_DECOMP_IND
  hb.Q_d_Fe_H2 = mb.V_H2_reacted * Q_FEO_DECOMP_H2
  hb.Q_d_Si = (iron.Si / 100.0) * 1000.0 * Q_SIO2_DECOMP
  hb.Q_d_Ti = (iron.Ti / 100.0) * 1000.0 * Q_TIO2_DECOMP
  hb.Q_d_Mn = (iron.Mn / 100.0) * 1000.0 * Q_MNO_DECOMP
  hb.Q_d_P = (iron.P / 100.0) * 1000.0 * Q_P2O5_DECOMP
  hb.Q_d_S = mb.S_to_pig * Q_DESULF + mb.m_C_dS * Q_C_TO_CO

  hb.Q_Coal = mb.m_Coal * proc.coal_decomp_heat
  hb.Q_Slag = mb.m_Slag * 1.85 * proc.T_slag
  hb.Q_Pig = mb.m_Pig * 1.10 * proc.T_pig

  const cpCO2 = gasMeanCp('CO2', proc.T_top), cpCO = gasMeanCp('CO', proc.T_top)
  const cpH2O = gasMeanCp('H2O', proc.T_top), cpH2 = gasMeanCp('H2', proc.T_top)
  const cpN2 = gasMeanCp('N2', proc.T_top)
  const cpTop = mb.V_Top > 0
    ? (mb.CO2_top * cpCO2 + mb.CO_top * cpCO + mb.H2O_top * cpH2O + mb.H2_top * cpH2 + mb.N2_top * cpN2) / mb.V_Top
    : 1.3
  hb.Q_Top = mb.V_Top * cpTop * proc.T_top
  hb.Q_Dust = mb.m_Dust * 1.0 * proc.T_dust

  const QOutKnown = (hb.Q_d_Fe2O3 + hb.Q_d_Fe_dir + hb.Q_d_Fe_ind + hb.Q_d_Fe_H2 +
                     hb.Q_d_Si + hb.Q_d_Ti + hb.Q_d_Mn + hb.Q_d_P + hb.Q_d_S +
                     hb.Q_Coal + hb.Q_Slag + hb.Q_Pig + hb.Q_Top + hb.Q_Dust)
  hb.Q_loss = Math.max(hb.Q_in_total - QOutKnown, 0.0)
  hb.Q_out_total = QOutKnown + hb.Q_loss
  return hb
}

// ---- 6. TFT（回旋区局部热平衡）----
export function calcTft(mb, hb, inputs, cokeRate, coalRate, cokeFc, coalFc) {
  const { proc } = inputs
  const phi = proc.blast_humidity / 1000.0 * VM / M_H2O
  const f = proc.oxygen_enrich / 100.0
  const tft = {}

  tft.V_CO_race = mb.m_C_R / M_C * VM
  tft.V_N2_race = mb.V_B * (1.0 - f) * (1.0 - phi) * N2_AIR
  tft.V_H2_race = mb.V_B * (1.0 - f) * phi
  tft.V_gas_race = tft.V_CO_race + tft.V_N2_race + tft.V_H2_race

  tft.CO_pct = tft.V_gas_race > 0 ? tft.V_CO_race / tft.V_gas_race * 100 : 0
  tft.N2_pct = tft.V_gas_race > 0 ? tft.V_N2_race / tft.V_gas_race * 100 : 0
  tft.H2_pct = tft.V_gas_race > 0 ? tft.V_H2_race / tft.V_gas_race * 100 : 0

  tft.Q1_combust = hb.Q_CR
  tft.Q2_blast = hb.Q_BR_sensible

  const mCCoke = cokeRate * cokeFc / 100.0
  const mCCoal = coalRate * coalFc / 100.0
  const mCTotal = mCCoke + mCCoal
  const cokeCFrac = mCTotal > 0 ? mCCoke / mCTotal : 0
  const coalCFrac = mCTotal > 0 ? mCCoal / mCTotal : 0
  tft.Q3_charge = (cokeCFrac * proc.cp_coke * proc.coke_temp + coalCFrac * proc.cp_coal * proc.coal_temp) * mCTotal

  tft.Q4_moisture = hb.Q_BR_moisture
  tft.Q5_coal = hb.Q_Coal
  tft.Q_net = tft.Q1_combust + tft.Q2_blast + tft.Q3_charge - tft.Q4_moisture - tft.Q5_coal

  let TGuess = 2400.0
  let TCalc = TGuess
  const maxIter = 20, tolerance = 5.0
  for (let i = 0; i < maxIter; i++) {
    const cp = (tft.V_CO_race * gasMeanCp('CO', TGuess) +
                tft.V_N2_race * gasMeanCp('N2', TGuess) +
                tft.V_H2_race * gasMeanCp('H2', TGuess)) / tft.V_gas_race
    tft.cp_gas = cp
    TCalc = tft.Q_net / (tft.V_gas_race * cp)
    if (Math.abs(TCalc - TGuess) < tolerance) {
      tft.TFT = TCalc
      tft.iterations = i + 1
      return tft
    }
    TGuess = TCalc
    tft.iterations = i + 1
  }
  tft.TFT = TCalc
  return tft
}

// ---- 7. 前向一体化计算入口（用户给定配料+鼓风 → 全部派生结果）----
export function forwardCalc(req = {}) {
  const d = defaultInputs()
  const inputs = {
    sinter: { ...d.sinter, ...(req.sinter || {}) },
    pellet: { ...d.pellet, ...(req.pellet || {}) },
    lump: { ...d.lump, ...(req.lump || {}) },
    coke: d.coke, coal: d.coal, dust: d.dust, iron: d.iron, slag: d.slag,
    proc: { ...d.proc },
  }
  // 平台字段名 → 引擎字段名
  const oreFields = { tfe: 'Fe', feo: 'FeO', cao: 'CaO', sio2: 'SiO2', mgo: 'MgO',
                      al2o3: 'Al2O3', s: 'S', p: 'P', loi: 'LOI', mn: 'MnO2', tio2: 'TiO2' }
  for (const key of ['sinter', 'pellet', 'lump']) {
    const ov = req[key] || {}
    for (const [plat, eng] of Object.entries(oreFields)) {
      if (ov[plat] != null) inputs[key][eng] = ov[plat] === 'mn' ? ov[plat] * 1.5825 : ov[plat]
    }
  }

  const cokeRate = req.coke_rate ?? 340.0
  const coalRate = req.coal_rate ?? 180.0
  const V_B = req.V_B ?? 1121.0
  const O2flow = req.O2_flow ?? 28.36
  const proc = inputs.proc
  proc.blast_temp = req.blast_temp ?? proc.blast_temp
  proc.blast_humidity = req.blast_humidity ?? proc.blast_humidity
  proc.eta_H2 = req.eta_H2 ?? proc.eta_H2

  // 由 O2_flow 与 V_B 反推富氧率 f
  const phi = proc.blast_humidity / 1000.0 * VM / M_H2O
  const Vdry = (1.0 - phi) > 0 ? V_B * (1.0 - phi) : V_B
  const f = Vdry > 0 ? O2flow / Vdry : 0.0
  const O2RatePct = f * 100.0
  proc.oxygen_enrich = O2RatePct

  // 矿量：未给时按 Fe 平衡闭合配比 62/31.4/6.6
  let mSin, mPel, mLump
  if (req.m_sin != null && req.m_pel != null && req.m_lump != null) {
    mSin = req.m_sin; mPel = req.m_pel; mLump = req.m_lump
  } else {
    const FePig = (inputs.iron.Fe / 100.0) * 1000.0
    const FeToDust = 15.0 * inputs.dust.TFe / 100.0
    const FeTarget = FePig / inputs.slag.eta_Fe + FeToDust
    const FeFromFuel = (cokeRate * (inputs.coke.Ash_Fe || 0) + coalRate * (inputs.coal.Ash_Fe || 0)) / 100.0
    const FeBlend = (0.62 * inputs.sinter.Fe + 0.314 * inputs.pellet.Fe + 0.066 * inputs.lump.Fe) / 100.0
    const oreTotal = FeBlend > 0 ? (FeTarget - FeFromFuel) / FeBlend : 0.0
    mSin = oreTotal * 0.62; mPel = oreTotal * 0.314; mLump = oreTotal * 0.066
  }

  const oreTotal = Math.max(mSin + mPel + mLump, 0.0)
  const oreMix = oreTotal > 0 ? [mSin, mPel, mLump] : [0.62, 0.314, 0.066]

  const mbAt = (rd) => {
    const pp = { ...inputs.proc, rd: Math.max(Math.min(rd, 1.0), 0.0) }
    return calcMaterialBalance({ ...inputs, proc: pp }, {
      coke_rate: cokeRate, coal_rate: coalRate,
      ore_mix: oreMix, ore_total_override: oreTotal, V_B_override: V_B,
    })
  }
  const carbonResid = (rd) => mbAt(rd)._carbon_resid

  // 二分反推 r_d：使碳平衡残差 → 0
  let rdLo = 0.0, rdHi = 1.0
  let fLo = carbonResid(rdLo), fHi = carbonResid(rdHi)
  let rdSolved = null
  if (fLo * fHi <= 0.0) {
    for (let i = 0; i < 50; i++) {
      const rdMid = 0.5 * (rdLo + rdHi)
      const fMid = carbonResid(rdMid)
      if (Math.abs(fMid) < 0.05) { rdSolved = rdMid; break }
      if (fLo * fMid < 0.0) { rdHi = rdMid; fHi = fMid } else { rdLo = rdMid; fLo = fMid }
    }
    if (rdSolved == null) rdSolved = 0.5 * (rdLo + rdHi)
  }
  const rd = rdSolved != null ? rdSolved : inputs.proc.rd
  const mb = mbAt(rd)
  const carbonResidVal = mb._carbon_resid

  // Fe 平衡诊断
  const FePig = (inputs.iron.Fe / 100.0) * 1000.0
  const FeToDust = mb.m_Dust * inputs.dust.TFe / 100.0
  const FeTarget = FePig / inputs.slag.eta_Fe + FeToDust
  const FeFromFuel = (cokeRate * (inputs.coke.Ash_Fe || 0) + coalRate * (inputs.coal.Ash_Fe || 0)) / 100.0
  const FeBlend = (mSin * inputs.sinter.Fe + mPel * inputs.pellet.Fe + mLump * inputs.lump.Fe) / 100.0
  const FeIn = FeBlend + FeFromFuel
  const FeResid = FeIn - FeTarget

  const hb = calcHeatBalance(mb, inputs)
  const tft = calcTft(mb, hb, inputs, cokeRate, coalRate, inputs.coke.FC, inputs.coal.FC)

  // CO2 指标
  const CIn = mb.m_C_coke_in + mb.m_C_coal_in
  const CO2Direct = mb.CO2_top * M_CO2 / VM
  const CO2Potential = CIn * 44.011 / 12.011
  const etaCO = (mb.CO2_top + mb.CO_top) > 0 ? mb.CO2_top / (mb.CO2_top + mb.CO_top) * 100.0 : 0

  return {
    inputs: {
      m_sin: mSin, m_pel: mPel, m_lump: mLump,
      coke_rate: cokeRate, coal_rate: coalRate,
      V_B, O2_flow: O2flow,
      blast_temp: proc.blast_temp, blast_humidity: proc.blast_humidity,
      eta_H2: proc.eta_H2, oxygen_enrich_pct: O2RatePct, f,
    },
    material: {
      m_sinter: mb.m_Sin, m_pellet: mb.m_Pel, m_lump: mb.m_Lump,
      ore_total: mb.oreTotal, m_coke: mb.m_Coke, m_coal: mb.m_Coal,
      m_dust: mb.m_Dust, m_pig: mb.m_Pig,
      m_slag: mb.m_Slag,
      slag_cao: mb.m_CaO_slag, slag_sio2: mb.m_SiO2_slag,
      slag_mgo: mb.m_MgO_slag, slag_al2o3: mb.m_Al2O3_slag,
      slag_mno: mb.m_MnO_slag, slag_feo: mb.m_FeO_slag,
      basicity_R: mb.R_calc,
      V_B: mb.V_B, B_O2: mb.B_O2, m_C_R: mb.m_C_R,
      topgas_co2: mb.CO2_top, topgas_co: mb.CO_top, topgas_h2: mb.H2_top,
      topgas_h2o: mb.H2O_top, topgas_n2: mb.N2_top, V_top: mb.V_Top,
      C_in_coke: mb.m_C_coke_in, C_in_coal: mb.m_C_coal_in,
      C_dFe: mb.m_C_dFe, C_dSi: mb.m_C_dSi, C_dTi: mb.m_C_dTi,
      C_dMn: mb.m_C_dMn, C_dP: mb.m_C_dP, C_dS: mb.m_C_dS,
      C_pig: mb.m_C_Pig, C_to_dust: mb.C_to_dust,
      mass_in_blend: mb.mass_in_blend, mass_in_fuel: mb.mass_in_fuel,
      mass_in_blast: mb.mass_in_blast, mass_in: mb.mass_in,
      mass_out_pig: mb.mass_out_pig, mass_out_slag: mb.mass_out_slag,
      mass_out_dust: mb.mass_out_dust, mass_out_gas: mb.mass_out_gas,
      mass_out: mb.mass_out, mass_error_pct: mb.error,
    },
    reduction: {
      r_d: rd, r_d_carbon_balance: rd,
      rd_calc_empirical: mb.rd_calc, eta_H2: proc.eta_H2,
      Fe_indirect: mb.Fe_indirect, Fe_direct: mb.Fe_direct,
    },
    heat: { Q_in_total: hb.Q_in_total, Q_out_total: hb.Q_out_total, TFT: tft.TFT },
    co2: {
      CO2_direct: CO2Direct, CO2_potential: CO2Potential, C_in: CIn, eta_CO: etaCO,
    },
    diagnostics: {
      Fe_resid: FeResid, Fe_in: FeIn, Fe_target: FeTarget,
      carbon_resid: carbonResidVal, mass_err_pct: mb.error,
      fe_closed: Math.abs(FeResid) < 0.5,
      carbon_closed: Math.abs(carbonResidVal) < 1.0,
      note: 'r_d 由碳平衡反推（不再作为输入）；Fe/碳/质量残差为一致性诊断',
    },
  }
}

// ---- 8. 默认值（前端面板初始化）----
export function forwardDefaults() {
  const d = defaultInputs()
  const oreOut = (o) => ({
    tfe: o.Fe, feo: o.FeO, cao: o.CaO, sio2: o.SiO2, mgo: o.MgO, al2o3: o.Al2O3,
    s: o.S, p: o.P, loi: o.LOI, mn: +(o.MnO2 / 1.5825).toFixed(4), tio2: o.TiO2,
  })
  return {
    coke_rate: 340.0, coal_rate: 180.0, V_B: 1121.0, O2_flow: 28.36,
    blast_temp: d.proc.blast_temp, blast_humidity: d.proc.blast_humidity,
    eta_H2: d.proc.eta_H2, rd: null,
    m_sin: null, m_pel: null, m_lump: null,
    sinter: oreOut(d.sinter), pellet: oreOut(d.pellet), lump: oreOut(d.lump),
  }
}
