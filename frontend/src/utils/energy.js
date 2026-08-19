// 单工序能耗推导（与后端 factors._energy_of 同源，保证前后端一致）。
// 节能减碳主题：先能后碳。优先用后端返回字段；缺失时由台账 + 碳素流反推。
const CC_FUEL = { coke: 0.0295, coal: 0.0262, ng: 0.0153 }
const GJ_PER_MWH = 3.6
const KGCE_PER_GJ = 34.12

export function energyOf(r) {
  if (!r) return { elec: 0, fuel: 0, total: 0, intensity: 0 }
  if (r.energy_total != null || r.elec != null) {
    return {
      elec: r.elec || 0,
      fuel: r.fuel_energy || 0,
      total: r.energy_total || 0,
      intensity: r.energy_intensity || 0,
    }
  }
  let elec = 0
  for (const it of (r.breakdown || [])) if (it.qty_unit === 'MWh/h') elec += it.qty || 0
  const cbf = r.carbon_by_fuel || {}
  let fuel = 0
  for (const k in cbf) if (CC_FUEL[k]) fuel += cbf[k] / CC_FUEL[k]
  const total = fuel + elec * GJ_PER_MWH
  const steel = r.steel_output || 0
  const intensity = steel > 0 ? (total * KGCE_PER_GJ) / steel : 0
  return { elec, fuel, total, intensity }
}
