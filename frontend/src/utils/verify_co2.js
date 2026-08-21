// ============================================================================
// Node 验证脚本：前端 co2.js 与后端 bf_tft_v20.py 默认工况逐项对齐
// 后端 v20 基准（默认参数）:
//   C_in = 413.4 kg C/tHM | C_HM = 45.0 | C_emit = 368.4 | CO2 = 1349.9 kg/tHM
// ============================================================================
import { collectSimContext, calcCo2Emission, CO2_DEFAULTS } from './src/utils/co2.js'

// 与后端 v20 CLI 默认一致的工况（后端 blast-temp 默认 1150，CO2 不依赖风温）
const params = {
  hot_blast_temp: 1150,
  wind_rate: 1000,
  oxygen_enrich: 2,
  blast_humidity: 15,
  hot_metal: 200,
  coke_rate: 340,
  coal_inj: 180,
}

const ctx = collectSimContext(params)
const co2 = ctx.co2
const r = ctx.res

const pass = (name, got, want, tol = 0.05) => {
  const ok = Math.abs(got - want) <= tol
  console.log(`  ${ok ? '✅' : '❌'} ${name}: got=${got.toFixed(2)}  want=${want}`)
  return ok
}

console.log('=' .repeat(64))
console.log('  前端 TFT + CO2 集成验证（collectSimContext）')
console.log('=' .repeat(64))

console.log('\n[ TFT ]')
console.log(`  TFT = ${r.TFT.toFixed(1)} ℃ | cp_eff = ${r.cp_eff.toFixed(5)} MJ/(Nm³·℃)`)
console.log(`  Q_total_in = ${r.Q_total_in.toFixed(1)} MJ/tFe | V_gas_total = ${r.V_gas_total.toFixed(1)} Nm³/tFe`)
console.log(`  热状态: ${ctx.status.label} (${ctx.status.desc})`)

console.log('\n[ CO2 排放（碳平衡法, 与后端 v20 对齐）]')
console.log(`  焦炭碳 C_coke = 340 × ${CO2_DEFAULTS.coke_carbon_pct}% = ${co2.C_coke.toFixed(1)} kg C/tHM`)
console.log(`  煤粉碳 C_coal = 180 × ${CO2_DEFAULTS.coal_carbon_pct}% = ${co2.C_coal.toFixed(1)} kg C/tHM`)
console.log(`  入炉碳 C_in   = ${co2.C_in.toFixed(1)} kg C/tHM`)
console.log(`  铁水溶碳 C_HM = 1000 × ${CO2_DEFAULTS.hm_carbon_pct}% = ${co2.C_HM.toFixed(1)} kg C/tHM (唯一产品碳)`)
console.log(`  排放碳 C_emit = ${co2.C_emit.toFixed(1)} kg C/tHM`)
console.log(`  CO2 排放      = ${co2.CO2_emit.toFixed(1)} kg CO2/tHM = ${co2.CO2_t.toFixed(3)} t CO2/tHM`)
console.log(`  路径细分(backend口径): 风口 ${co2.CO2_from_raceway.toFixed(1)} | 非风口碳池 ${co2.CO2_from_other.toFixed(1)} kg CO2/tHM`)
console.log(`    m_C_R=${co2.m_C_R.toFixed(1)} kg C/tHM | η_coal=${co2.eta_coal.toFixed(3)} | O2_supply=${co2.O2_supply.toFixed(1)} Nm³/tHM | ${co2.fuel_limited ? '氧充足,燃料全烧' : '氧不足,燃料未烧完'}`)
console.log(`  排放强度判定: ${co2.level.label} (${co2.level.desc})`)

console.log('\n[ 逐项断言（容差 ±0.05, 细分 ±0.1）]')
let allOk = true
allOk = pass('C_in  = 413.4', co2.C_in, 413.4) && allOk
allOk = pass('C_HM  = 45.0 ', co2.C_HM, 45.0) && allOk
allOk = pass('C_emit= 368.4', co2.C_emit, 368.4) && allOk
allOk = pass('CO2   = 1349.9', co2.CO2_emit, 1349.9) && allOk
allOk = pass('CO2_raceway = 908.1', co2.CO2_from_raceway, 908.1, 0.1) && allOk
allOk = pass('CO2_other   = 441.8', co2.CO2_from_other, 441.8, 0.1) && allOk
// 恒等式自检
const ident = Math.abs(co2.C_emit - (co2.C_in - co2.C_HM)) < 1e-9
const splitSum = Math.abs((co2.CO2_from_raceway + co2.CO2_from_other) - co2.CO2_emit) < 0.2
allOk = ident && splitSum && allOk
console.log(`  ${ident ? '✅' : '❌'} 碳平衡恒等式 C_emit = C_in - C_HM`)
console.log(`  ${splitSum ? '✅' : '❌'} 细分和 = 总量 (908.1 + 441.8 = 1349.9)`)

// 灵敏度快照（顺带验证参数驱动）
console.log('\n[ 参数驱动快照 ]')
for (const [k, v] of [['coal_inj', 200], ['coke_rate', 320], ['hm_carbon_pct_override', 4.8]]) {
  if (k === 'hm_carbon_pct_override') {
    const c2 = calcCo2Emission(params, ctx.res, { hm_carbon_pct: v })
    console.log(`  铁水含碳 4.8% → CO2 = ${c2.CO2_emit.toFixed(1)} kg/tHM (C_emit=${c2.C_emit.toFixed(1)})`)
  } else {
    const c2 = calcCo2Emission({ ...params, [k]: v }, ctx.res)
    console.log(`  ${k}=${v} → CO2 = ${c2.CO2_emit.toFixed(1)} kg/tHM (C_in=${c2.C_in.toFixed(1)})`)
  }
}

// 替代口径演示: splitFrom='tft'（与前端 TFT 的 C_burn 自洽）
const cTft = calcCo2Emission(params, ctx.res, { splitFrom: 'tft' })
console.log('\n[ 替代口径 splitFrom=\'tft\' ]')
console.log(`  用前端 TFT C_burn=${cTft.m_C_R.toFixed(1)} kg C/tFe → 风口 ${cTft.CO2_from_raceway.toFixed(1)} | 非风口 ${cTft.CO2_from_other.toFixed(1)} kg CO2/tHM`)
console.log(`  （总量不变: ${cTft.CO2_emit.toFixed(1)} kg CO2/tHM; 仅细分口径不同）`)

console.log('\n' + ('=' .repeat(64)))
console.log(allOk ? '  ✅ 全部断言通过：前端 CO2 与后端 v20 基准一致' : '  ❌ 存在不一致，请检查')
console.log('=' .repeat(64))
process.exit(allOk ? 0 : 1)
