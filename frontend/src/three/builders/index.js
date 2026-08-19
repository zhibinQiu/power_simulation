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
}
