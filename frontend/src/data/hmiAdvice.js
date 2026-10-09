// =====================================================================
// HMI 人机交互屏 · 实时调控建议引擎
// ---------------------------------------------------------------------
// 用途：把「当前工况（工序参数 + 实时读数）」翻译成一条条**人工可执行**的
//       调控指令，供操作人员在 DCS / 现场手动调节对应设备。此处只做「开环
//       建议」，不自动下发、不写设定值。
//
// 当前实现：火电流程（thermal-power · 660MW 超超临界）一组规则。
//   - 平台打开了火电场景 → 取编排方案里的实时工序参数；
//   - 未打开火电场景    → 用包内出厂工况（TP_BASELINE）为例展示，面板标注「示例」。
// 后续接入其它行业时，在此文件按 sceneId 分派新的规则集即可，UI 无需改动。
//
// 规则口径与量化系数均来自场景包：
//   grid_ef 0.5703 tCO₂/MWh、原煤 NCV 20.9 GJ/t、标煤 29.27 GJ/tce、
//   单位热值含碳量 0.0262 tC/GJ、碳氧化率 0.98、石灰石 0.4395 tCO₂/t（纯度 90%）。
// =====================================================================

// 火电流程出厂工况（与 backend/data/scenes/thermal-power/model.json 一致）
export const TP_BASELINE = [
  { id: 'ch1', type: 'coal_handling', name: '输煤与制粉', params: { power: 3.2 } },
  { id: 'bo1', type: 'boiler', name: '锅炉', params: { coal_rate: 235, power: 12 } },
  { id: 'st1', type: 'steam_turbine', name: '汽轮机', params: { steam_rate: 1900, power: 0.3 } },
  { id: 'gn1', type: 'generator', name: '发电机', params: { output: 660, power: 0.2 } },
  { id: 'cd1', type: 'condenser', name: '凝汽器', params: { power: 0.5 } },
  { id: 'ct1', type: 'cooling_tower', name: '冷却塔与循环水泵', params: { power: 4.5 } },
  { id: 'fw1', type: 'feedwater', name: '给水与除氧', params: { power: 14 } },
  { id: 'dn1', type: 'denitration', name: '脱硝（SCR）', params: { reagent_rate: 0.6, power: 0.8 } },
  { id: 'du1', type: 'dedust', name: '除尘', params: { power: 1.6 } },
  { id: 'ds1', type: 'desulfurization', name: '脱硫', params: { limestone_rate: 8, power: 6.5 } },
  { id: 'sk1', type: 'stack', name: '烟囱', params: { power: 0.1 } },
]

// ---------- 量化系数 ----------
const GRID_EF = 0.5703            // tCO₂/MWh（电网因子，厂用电折间接排放）
const NCV_COAL = 20.9             // GJ/t（入炉煤低位发热量）
const NCV_STD = 29.27             // GJ/tce（标准煤）
const COAL_EF = NCV_COAL * 0.0262 * 0.98 * (44 / 12)   // tCO₂/t 原煤 ≈ 1.968
const LIME_PURITY = 0.9
const LIME_EF = 0.4395            // tCO₂/t 纯碳酸钙

// ---------- 判据阈值（660MW 超超临界典型运行区间） ----------
const AUX_RATE_TARGET = 6.5       // 厂用电率目标上限 %
const FEED_PUMP_SHARE = 0.30      // 给水泵占厂用电比例超过此值即提示
const COAL_GCE_MIN = 265          // 发电标准煤耗合理下限 gce/kWh
const COAL_GCE_MAX = 288          // 发电标准煤耗合理上限 gce/kWh
const STEAM_RATE_MAX = 3.05       // 汽耗率上限 kg/kWh
const REAGENT_MAX = 0.5           // 脱硝还原剂 kg/MWh
const LIME_MIN = 8                // 石灰石耗量下限 kg/MWh
const LIME_MAX = 14               // 石灰石耗量上限 kg/MWh
const O2_MAX = 4.5                // 排烟含氧量上限 %
const STACK_TEMP_MAX = 120        // 排烟温度上限 ℃
const MS_TEMP_TARGET = 600        // 主蒸汽温度额定值 ℃（超超临界）
const MS_TEMP_BAND = 4            // 主蒸汽温度允许偏差 ±℃
const BACK_PRESS_MAX = 6          // 凝汽器背压上限 kPa（设计 5 kPa）

function num(v, d = 0) {
  const n = Number(v)
  return Number.isFinite(n) ? n : d
}
function unitMap(units) {
  const m = {}
  for (const u of units || []) {
    if (u && u.type && !m[u.type]) m[u.type] = u
  }
  return m
}
function pv(u, key, d = 0) {
  return num(u && u.params ? u.params[key] : undefined, d)
}
// 实时读数优先：采集设备已绑定时用实测值，但只接受与出厂工况同量级的值（防止张冠李戴）
function blend(base, live) {
  if (live == null || !Number.isFinite(live) || live <= 0) return base
  if (base > 0 && (live < base * 0.2 || live > base * 5)) return base
  return live
}
// 按设备名 / id 匹配实时读数（火电场景下工序附加了采集设备时才命中）
// opt: { unit  RegExp 单位过滤（如 /℃/，避免把功率/电流当成温度）
//        exclude RegExp[] 排除项（如排烟温度要排除脱硝入口烟温） }
function findDev(devices, regs, opt = {}) {
  const { unit = null, exclude = null } = opt
  for (const d of devices || []) {
    if (d.live == null) continue
    const s = `${d.label || ''} ${d.id || ''} ${d.name || ''}`
    if (exclude && exclude.some((r) => r.test(s))) continue
    if (unit && !(d.unit && unit.test(String(d.unit)))) continue
    if (!regs.some((r) => r.test(s))) continue
    return d
  }
  return null
}
function pickLive(devices, regs, opt = {}) {
  const d = findDev(devices, regs, opt)
  return d ? num(d.live, NaN) : null
}
function firstLive(...vals) {
  for (const v of vals) if (v != null && Number.isFinite(v)) return v
  return null
}
// 工序辅机功率：优先采用绑定的电功率传感器实测值（kW → MW），否则用包参数
function auxMW(u, devices) {
  const base = pv(u, 'power')
  const d = findDev((devices || []).filter((x) => x.unitId === u.id), [/电功率|有功|功率|power/], { unit: /kW|MW/ })
  if (!d) return base
  const v = num(d.live, NaN)
  if (!Number.isFinite(v)) return base
  return blend(base, /kW/i.test(String(d.unit || '')) ? v / 1000 : v)
}

/**
 * 火电流程调控建议。
 * @param {Array}  units   工序数组（含 params：output / coal_rate / steam_rate / power / reagent_rate / limestone_rate）
 * @param {Array}  devices 实时设备（含 live），用于排烟氧量 / 排烟温度等实测判据
 * @returns {{items: Array, ops: Object}}
 */
export function buildThermalAdvice(units = [], devices = []) {
  const u = unitMap(units)
  const items = []

  const gen = blend(pv(u.generator, 'output'), pickLive(devices, [/发电功率|发电机|output/], { exclude: [/温度|电流|电压/] }))
  const coal = blend(pv(u.boiler, 'coal_rate'), pickLive(devices, [/入炉煤|给煤|煤量|coal/], { exclude: [/温度|电量/] }))
  // 厂用电：逐工序取实测电功率（kW）换算，未绑定采集设备的工序回落到包参数
  const aux = (units || []).reduce((s, x) => s + auxMW(x, devices), 0)
  if (!(gen > 0) || !(coal > 0)) return { items, ops: { gen, coal, aux, auxRate: 0, coalGce: 0 } }

  const auxRate = (aux / gen) * 100
  // 发电标准煤耗 gce/kWh = 入炉煤量 × 折标系数 ÷ 发电量
  const gcePerT = NCV_COAL / NCV_STD
  const coalGce = (coal * 1e6 * gcePerT) / (gen * 1e3)

  // ① 厂用电率：优先动循环水泵（P ∝ n³，变频收益最大）与浆液循环泵
  if (auxRate > AUX_RATE_TARGET) {
    const cut = ((auxRate - AUX_RATE_TARGET) / 100) * gen
    items.push({
      id: 'aux-power',
      level: 'high',
      title: '厂用电率高于目标值',
      target: '循环水泵 · 冷却塔与循环水泵；浆液循环泵 · 脱硫',
      cur: auxRate.toFixed(2),
      unit: '%',
      goal: `≤ ${AUX_RATE_TARGET.toFixed(2)} %`,
      action: '在 DCS 上将循环水泵变频器由 45 Hz 降至 42 Hz（流量约 -7%、轴功率约 -20%），并按吸收塔出口 SO₂ 停运一台浆液循环泵',
      gain: '预计厂用电 -{cut} MW · 间接排放 -{co2} tCO₂/h',
      gainArgs: { cut: cut.toFixed(2), co2: (cut * GRID_EF).toFixed(2) },
    })
  }

  // ② 电动给水泵：厂用电第一大户，优先汽泵改造 / 降低给水压力定值
  const fw = pv(u.feedwater, 'power')
  if (fw > 0 && aux > 0 && fw / aux > FEED_PUMP_SHARE) {
    const goal = fw * 0.6
    const cut = fw - goal
    items.push({
      id: 'feed-pump',
      level: 'mid',
      title: '电动给水泵电耗占比偏高',
      target: '电动给水泵 · 给水与除氧',
      cur: fw.toFixed(1),
      unit: 'MW',
      goal: `≤ ${goal.toFixed(1)} MW（占厂用电 ${((goal / aux) * 100).toFixed(0)}%）`,
      action: '在 DCS 上投入汽动给水泵运行（汽源取再热冷段），电动泵转备用；无汽泵时按负荷曲线下调给水压力定值 0.3 MPa',
      gain: '预计厂用电 -{cut} MW · 间接排放 -{co2} tCO₂/h',
      gainArgs: { cut: cut.toFixed(1), co2: (cut * GRID_EF).toFixed(2) },
    })
  }

  // ③ 发电标准煤耗：高于先进值 → 燃烧调整；低于典型值 → 先怀疑燃料计量与煤质
  if (coalGce > COAL_GCE_MAX || coalGce < COAL_GCE_MIN) {
    const high = coalGce > COAL_GCE_MAX
    // 煤耗每降 1 gce/kWh 对应原煤量与直接排放
    const dCoal = (gen * 1e3 * 1e-6) / gcePerT
    const dCo2 = dCoal * COAL_EF
    items.push({
      id: 'coal-rate',
      level: high ? 'high' : 'mid',
      title: high ? '发电标准煤耗高于先进值' : '发电标准煤耗低于典型值，建议校核燃料计量',
      target: high ? '燃烧调整与吹灰 · 锅炉' : '给煤机皮带秤 · 输煤与制粉；入炉煤采制化',
      cur: coalGce.toFixed(1),
      unit: 'gce/kWh',
      goal: `${COAL_GCE_MIN} ~ ${COAL_GCE_MAX}`,
      action: high
        ? '按省煤器出口氧量 3.2%~3.8% 优化配风与磨煤机组合，加强受热面吹灰，维持主汽 25 MPa / 600 ℃'
        : '核对给煤机皮带秤检定记录与入炉煤低位发热量化验单：计量或煤质偏差会使排放核算的活动数据系统性低估',
      gain: high
        ? '煤耗每降 1 gce/kWh，入炉煤约 -{d} t/h、直接排放 -{c} tCO₂/h'
        : '消除活动数据偏差，保证碳排放核算与配额履约数据可信',
      gainArgs: { d: dCoal.toFixed(2), c: dCo2.toFixed(2) },
    })
  }

  // ④ 汽耗率
  const steam = pv(u.steam_turbine, 'steam_rate')
  if (steam > 0) {
    const sr = (steam * 1e3) / (gen * 1e3)
    if (sr > STEAM_RATE_MAX) {
      items.push({
        id: 'steam-rate',
        level: 'mid',
        title: '汽耗率高于设计值',
        target: '回热系统与通流部分 · 汽轮机',
        cur: sr.toFixed(2),
        unit: 'kg/kWh',
        goal: `≤ ${STEAM_RATE_MAX.toFixed(2)}`,
        action: '检查高加 / 低加端差与轴封漏汽，维持主汽 25 MPa / 600 ℃、背压 5 kPa',
        gain: '汽耗率每降 0.1 kg/kWh，发电煤耗约降 3 gce/kWh',
        gainArgs: {},
      })
    }
  }

  // ⑤ 脱硝还原剂（按单位发电量口径，避免不同机组容量不可比）
  const reagent = pv(u.denitration, 'reagent_rate')
  if (reagent > 0) {
    const per = (reagent * 1e3) / gen
    if (per > REAGENT_MAX) {
      const goal = (REAGENT_MAX * gen) / 1e3
      items.push({
        id: 'reagent',
        level: 'low',
        title: '脱硝还原剂耗量偏高',
        target: '喷氨格栅 · 脱硝（SCR）',
        cur: per.toFixed(2),
        unit: 'kg/MWh',
        goal: `≤ ${REAGENT_MAX.toFixed(2)}（约 ${goal.toFixed(2)} t/h）`,
        action: '按 SCR 出口 NOx 与氨逃逸（≤ 3 ppm）分区优化喷氨，先调两侧偏高分区',
        gain: '预计还原剂 -{d} t/h，氨逃逸下降可减轻空预器堵塞与引风机电耗',
        gainArgs: { d: (reagent - goal).toFixed(2) },
      })
    }
  }

  // ⑥ 脱硫石灰石（过程排放源：碳酸盐分解）
  const lime = pv(u.desulfurization, 'limestone_rate')
  if (lime > 0) {
    const per = (lime * 1e3) / gen
    if (per > LIME_MAX || per < LIME_MIN) {
      const high = per > LIME_MAX
      const unitEf = LIME_PURITY * LIME_EF
      items.push({
        id: 'limestone',
        level: 'low',
        title: high ? '脱硫石灰石耗量偏高（钙硫比偏大）' : '脱硫石灰石耗量偏低，建议校核脱硫效率',
        target: '石灰石浆液制备与供浆泵 · 脱硫',
        cur: per.toFixed(1),
        unit: 'kg/MWh',
        goal: `${LIME_MIN} ~ ${LIME_MAX}`,
        action: high
          ? '按吸收塔出口 SO₂ 与浆液 pH（5.4~5.8）下调供浆量，钙硫比控制在 1.03 以内'
          : '校核吸收塔出口 SO₂、浆液 pH 与氧化风量，确认脱硫效率与石膏品质',
        gain: '石灰石耗量每降 1 t/h，过程排放 -{c} tCO₂/h',
        gainArgs: { c: unitEf.toFixed(2) },
      })
    }
  }

  // ⑦ 实时判据：排烟含氧量（省煤器出口 / 锅炉侧；净烟气氧量受脱硫漏风干扰，排除）
  const o2 = firstLive(
    pickLive(devices, [/氧量分析仪|省煤器.*氧|bo_o2/], { unit: /%/, exclude: [/净烟气/] }),
    pickLive(devices, [/氧量|含氧|o2|oxygen/], { unit: /%/, exclude: [/净烟气|sk/] })
  )
  if (o2 != null && Number.isFinite(o2) && o2 > O2_MAX) {
    items.push({
      id: 'flue-o2',
      level: 'mid',
      title: '排烟含氧量偏高，排烟损失偏大',
      target: '送风机动叶 / 二次风门 · 锅炉',
      cur: o2.toFixed(1),
      unit: '%',
      goal: '3.2 ~ 3.8 %',
      action: '在 DCS 上关小送风机动叶、降低总风量，维持省煤器出口氧量 3.2%~3.8%',
      gain: '氧量每降 1 个百分点，锅炉效率约提升 0.3 个百分点，风机电耗同步下降',
      gainArgs: {},
    })
  }

  // ⑧ 实时判据：排烟温度（空预器出口；脱硝入口烟温 350 ℃ 属设计值，必须排除）
  const tt = pickLive(devices, [/排烟温度|排烟/], { unit: /℃/, exclude: [/脱硝|入口/] })
  if (tt != null && Number.isFinite(tt) && tt > STACK_TEMP_MAX) {
    items.push({
      id: 'stack-temp',
      level: 'mid',
      title: '排烟温度偏高，受热面积灰或空预器漏风',
      target: '吹灰系统与空预器 · 锅炉',
      cur: tt.toFixed(1),
      unit: '℃',
      goal: `≤ ${STACK_TEMP_MAX} ℃`,
      action: '加强受热面吹灰（先投炉膛与屏区），检查空预器漏风与蓄热元件积灰',
      gain: '排烟温度每降 10 ℃，发电煤耗约降 1.5 gce/kWh',
      gainArgs: {},
    })
  }

  // ⑨ 实时判据：主蒸汽温度（偏离额定 600 ℃ 直接影响热耗与管壁安全）
  const msT = pickLive(devices, [/主蒸汽温度|主汽温/], { unit: /℃/ })
  if (msT != null && Number.isFinite(msT) && Math.abs(msT - MS_TEMP_TARGET) > MS_TEMP_BAND) {
    const high = msT > MS_TEMP_TARGET
    items.push({
      id: 'ms-temp',
      level: high ? 'high' : 'mid',
      title: high ? '主蒸汽温度高于额定值' : '主蒸汽温度低于额定值',
      target: '过热器减温水调节阀 · 锅炉',
      cur: msT.toFixed(1),
      unit: '℃',
      goal: `${MS_TEMP_TARGET} ± ${MS_TEMP_BAND}`,
      action: high
        ? '在 DCS 上开大一级 / 二级减温水调节阀，同时检查燃尽风与火焰中心，防止过热器管壁超温'
        : '在 DCS 上关小减温水调节阀并上摆燃烧器摆角，汽温偏低会使机组热耗上升并增加末级叶片水蚀',
      gain: '汽温每偏差 10 ℃，发电煤耗约变化 1.2 gce/kWh',
      gainArgs: {},
    })
  }

  // ⑩ 实时判据：凝汽器背压（真空度直接决定汽轮机热耗）
  const bp = pickLive(devices, [/背压|真空/], { unit: /kPa/ })
  if (bp != null && Number.isFinite(bp) && bp > BACK_PRESS_MAX) {
    items.push({
      id: 'back-pressure',
      level: 'mid',
      title: '凝汽器背压高于设计值',
      target: '循环水泵 / 真空系统 · 凝汽器',
      cur: bp.toFixed(2),
      unit: 'kPa',
      goal: `≤ ${BACK_PRESS_MAX.toFixed(2)}`,
      action: '在 DCS 上增开一台循环水泵（或提高循环水泵变频），并检查真空系统严密性与凝汽器管束结垢',
      gain: '背压每降 1 kPa，机组热耗约降 1.0%、发电煤耗约降 2.5 gce/kWh',
      gainArgs: {},
    })
  }

  return {
    items,
    ops: { gen, coal, aux, auxRate, coalGce, steam },
  }
}

/**
 * HMI 右侧面板统一入口（按场景分派规则集；目前仅火电）。
 * @param {String} sceneId 当前场景 id
 * @param {Array}  units   当前场景工序（含实时参数）
 * @param {Array}  devices 实时设备读数
 */
export function buildHmiAdvice({ sceneId = '', units = [], devices = [] } = {}) {
  const isThermal = sceneId === 'thermal-power'
  const useUnits = isThermal && units && units.length ? units : TP_BASELINE
  const r = buildThermalAdvice(useUnits, isThermal ? devices : [])
  // 未打开火电场景时按包内出厂工况示例展示，UI 会标注「示例」
  return {
    sceneLabel: '火电流程 · 660MW 超超临界机组',
    sample: !isThermal,
    items: r.items,
    ops: r.ops,
  }
}
