import { bfFuelRates } from './src/utils/bfFuel.js'
import { collectTftContext } from './src/utils/tft.js'
import { makeTftConfig } from './src/utils/coalBlend.js'

const base = {
  coke_rate: 410, coal_inj: 130,
  hot_blast_temp: 1250, oxygen_enrich: 0,
  wind_rate: 600, blast_humidity: 1, draft: 1,
}

function tftOf(params) {
  const ef = bfFuelRates(params)
  const full = { ...params, coke_rate: ef.coke, coal_inj: ef.coal }
  const ctx = collectTftContext(full, makeTftConfig({}))
  return { ef, tft: ctx.tft, res: ctx.res }
}

console.log('=== 轴：焦比(独立设定，煤比冻结=130) ===')
console.log('焦比  煤比  TFT(℃)  总热量  燃烧碳C_burn 煤气总量')
const cokes = [300, 330, 360, 410, 470, 530, 560]
let first = null
for (const c of cokes) {
  const { ef, tft, res } = tftOf({ ...base, coke_rate_set: c })
  if (!first) first = tft
  console.log(
    String(c).padEnd(5),
    String(ef.coal.toFixed(0)).padEnd(5),
    tft.toFixed(2).padEnd(7),
    res.sum_heat.toFixed(0).padEnd(8),
    res.C_burn.toFixed(1).padEnd(13),
    res.V_gas_total.toFixed(0),
  )
}
const tftAt = (c) => tftOf({ ...base, coke_rate_set: c }).tft
console.log(`焦比 300→560 区间 TFT 变化 = ${(tftOf({...base,coke_rate_set:560}).tft - tftOf({...base,coke_rate_set:300}).tft).toFixed(2)} ℃  (Δ260 kg/t 焦比)`)

console.log('\n=== 对比轴：富氧率(耦合，煤比↑焦比↓) ===')
console.log('富氧%  煤比  焦比  TFT(℃)  总热量  燃烧碳C_burn')
for (const o of [0, 1, 2, 3, 4, 5]) {
  const { ef, tft, res } = tftOf({ ...base, oxygen_enrich: o })
  console.log(
    String(o).padEnd(5),
    String(ef.coal.toFixed(0)).padEnd(5),
    String(ef.coke.toFixed(0)).padEnd(5),
    tft.toFixed(2).padEnd(7),
    res.sum_heat.toFixed(0).padEnd(8),
    res.C_burn.toFixed(1),
  )
}
