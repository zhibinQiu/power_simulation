// 工艺模型组件统一导出，按 unitId 映射到对应 builder 函数
import _buildSinterPlant from './SinterPlant.js'
import _buildPelletizing from './Pelletizing.js'
import _buildCokeOven from './CokeOven.js'
import _buildIngotCasting from './IngotCasting.js'
import _buildReheatFurnace from './ReheatFurnace.js'
import _buildPretreat from './Pretreat.js'
import _buildUtility from './Utility.js'
import _buildBlastFurnace from './BlastFurnace.js'
import _buildFurnace from './Furnace.js'
import _buildConverter from './Converter.js'
import _buildCylinder from './Cylinder.js'
import _buildCaster from './Caster.js'
import buildRollers from './Rollers.js'
import { buildAuxiliary } from './Auxiliary.js'
import { buildDataCenter } from './DataCenter.js'
import { buildThermalPower } from './ThermalPower.js'

/** unitId → builder 函数映射表 */
export const builderMap = {
  // 铁前
  sinter_plant: _buildSinterPlant,
  pelletizing: _buildPelletizing,
  coke_oven: _buildCokeOven,
  // 高炉/氢冶金/直接还原（共享炉体型造型）
  blast_furnace: _buildBlastFurnace,
  hydrogen_bf: _buildBlastFurnace,
  h2_dri: _buildBlastFurnace,
  dri_midrex: _buildBlastFurnace,
  smelting_reduction: _buildBlastFurnace,
  // 转炉/电炉
  bof: _buildConverter,
  eaf: _buildFurnace,
  aod: _buildConverter,
  // 二次精炼
  ladle_furnace: _buildCylinder,
  rh_vacuum: _buildCylinder,
  vd_vacuum: _buildCylinder,
  biochar_injection: _buildCylinder,
  // 连铸/模铸
  caster: _buildCaster,
  ingot_casting: _buildIngotCasting,
  // 轧机
  rolling_mill: buildRollers,
  cold_rolling: buildRollers,
  reheating_furnace: _buildReheatFurnace,
  // 铁水预处理
  hot_metal_pretreat: _buildPretreat,
  // 公用（煤气发电/余热/CCS）
  gas_power: _buildUtility,
  waste_heat: _buildUtility,
  ccs: _buildUtility,
  // 工辅（独立节点，经物料连线驱动被服务工艺）
  // scene.js 统一以 builder(bodyMat, anim) 方式调用，故此处按 type 包装，
  // 确保 buildAuxiliary 能拿到正确的工艺类型以分发到对应造型。
  blower: (m, a) => buildAuxiliary('blower', m, a),
  hot_blast_stove: (m, a) => buildAuxiliary('hot_blast_stove', m, a),
  id_fan: (m, a) => buildAuxiliary('id_fan', m, a),
  injector: (m, a) => buildAuxiliary('injector', m, a),
  drive_supply: (m, a) => buildAuxiliary('drive_supply', m, a),
  electrode_reg: (m, a) => buildAuxiliary('electrode_reg', m, a),
  belt_conv: (m, a) => buildAuxiliary('belt_conv', m, a),
  feeder: (m, a) => buildAuxiliary('feeder', m, a),
  cool_pump: (m, a) => buildAuxiliary('cool_pump', m, a),
  aux_boiler: (m, a) => buildAuxiliary('aux_boiler', m, a),
  oxy_plant: (m, a) => buildAuxiliary('oxy_plant', m, a),
  oxy_supply: (m, a) => buildAuxiliary('oxy_plant', m, a), // 全厂供氧系统：复用空分制氧塔造型（规模更大）
  power_supply: (m, a) => buildAuxiliary('power_supply', m, a), // 全厂供电系统：主变电站造型
  // 火电（thermal-power）：燃料制备→锅炉→汽轮机→发电 主流程 +
  // 汽水循环（凝汽/循环冷却水/给水除氧）与烟气治理（脱硝/除尘/脱硫/排烟）两侧辅助系统
  coal_handling: (m, a) => buildThermalPower('coal_handling', m, a),
  boiler: (m, a) => buildThermalPower('boiler', m, a),
  steam_turbine: (m, a) => buildThermalPower('steam_turbine', m, a),
  generator: (m, a) => buildThermalPower('generator', m, a),
  condenser: (m, a) => buildThermalPower('condenser', m, a),
  cooling_tower: (m, a) => buildThermalPower('cooling_tower', m, a),
  feedwater: (m, a) => buildThermalPower('feedwater', m, a),
  denitration: (m, a) => buildThermalPower('denitration', m, a),
  dedust: (m, a) => buildThermalPower('dedust', m, a),
  desulfurization: (m, a) => buildThermalPower('desulfurization', m, a),
  stack: (m, a) => buildThermalPower('stack', m, a),
  heat_net: (m, a) => buildThermalPower('heat_net', m, a),
  ash_handling: (m, a) => buildThermalPower('ash_handling', m, a),
  gypsum_handling: (m, a) => buildThermalPower('gypsum_handling', m, a),
  // 火电「系统内部的能源设备」：属于哪个系统就挂在哪个系统小组内，
  // 顶层聚合为该系统的大设备，双击系统进入小组子场景即可看到并调节这些辅机
  tp_mill: (m, a) => buildThermalPower('tp_mill', m, a), // 磨煤机 → 输煤制粉系统
  tp_fd_fan: (m, a) => buildThermalPower('tp_fd_fan', m, a), // 送风机 → 锅炉系统
  tp_id_fan: (m, a) => buildThermalPower('tp_id_fan', m, a), // 引风机 → 锅炉系统
  tp_pa_fan: (m, a) => buildThermalPower('tp_pa_fan', m, a), // 一次风机 → 锅炉系统
  tp_cond_pump: (m, a) => buildThermalPower('tp_cond_pump', m, a), // 凝结水泵 → 凝汽系统
  tp_circ_pump: (m, a) => buildThermalPower('tp_circ_pump', m, a), // 循环水泵 → 循环冷却水系统
  tp_feed_pump: (m, a) => buildThermalPower('tp_feed_pump', m, a), // 给水泵 → 给水除氧系统
  tp_slurry_pump: (m, a) => buildThermalPower('tp_slurry_pump', m, a), // 浆液循环泵 → 烟气脱硫系统
  tp_oxi_fan: (m, a) => buildThermalPower('tp_oxi_fan', m, a), // 氧化风机 → 烟气脱硫系统
  tp_heat_pump: (m, a) => buildThermalPower('tp_heat_pump', m, a), // 热网循环泵 → 热网换热系统
  // 机房温控（数据中心）：冷却水 / 制冷风机（半导体制冷+风扇） / 算力设备（机柜列）
  dc_chiller: (m, a) => buildDataCenter('dc_chiller', m, a),
  dc_fan_cool: (m, a) => buildDataCenter('dc_fan_cool', m, a),
  dc_it: (m, a) => buildDataCenter('dc_it', m, a),
}
