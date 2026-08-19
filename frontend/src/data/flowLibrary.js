// 流程编排数据/模板库：物料、工艺模板（长/短流程）、设备模板、预建示例方案
// 这是编辑态节点画布的数据源，与现有仿真 model 解耦，便于扩展到多行业。

// ---------- 物料/原料/产物库 ----------
// carbon: 该物料单位量的隐含碳排（tCO₂/单位），用于工程估算。
// 能源类：电网电 0.5703 tCO₂/MWh（2022 年全国电力平均 CO₂ 排放因子）；副产品煤气按发热量折算。
export const MATERIALS = [
  // 原料
  { id: 'iron_ore', name: '铁矿石', cat: '原料', unit: 't', color: '#8a9a5b', carbon: 0.02 },
  { id: 'coke', name: '焦炭', cat: '原料', unit: 't', color: '#5a5a5a', carbon: 3.0 },
  { id: 'coal', name: '煤', cat: '原料', unit: 't', color: '#6a6a6a', carbon: 2.4 },
  { id: 'limestone', name: '石灰石', cat: '原料', unit: 't', color: '#c9c2a8', carbon: 0.44 },
  { id: 'scrap', name: '废钢', cat: '原料', unit: 't', color: '#6f9e74', carbon: 0.1 },
  { id: 'dri', name: '直接还原铁/热压块铁', cat: '原料', unit: 't', color: '#7d9b6a', carbon: 0.2 },
  { id: 'pig_iron', name: '生铁', cat: '原料', unit: 't', color: '#5f7d52', carbon: 1.6 },
  { id: 'ferroalloy', name: '合金', cat: '原料', unit: 't', color: '#8a7bb0', carbon: 1.5 },
  { id: 'oxygen', name: '氧气', cat: '能源', unit: 'Nm³', color: '#5b83a8', carbon: 0 },
  { id: 'water', name: '水', cat: '原料', unit: 't', color: '#4f97a0', carbon: 0 },
  { id: 'ngas', name: '天然气', cat: '能源', unit: 'Nm³', color: '#a0a0a0', carbon: 0.00216 },
  // 电力类（外购电 / 绿电 / 自发电）；process 模板的 electricity 端口即指向「外购电」
  { id: 'electricity', name: '外购电', cat: '能源', unit: 'MWh', color: '#e0b24a', carbon: 0.57 },
  { id: 'green_power', name: '绿电', cat: '能源', unit: 'MWh', color: '#3fae7a', carbon: 0.02 },
  { id: 'biomass', name: '生物质碳', cat: '能源', unit: 't', color: '#7fae5a', carbon: 0.0 },
  // 中间产物
  { id: 'sinter', name: '烧结矿', cat: '中间产物', unit: 't', color: '#9a8b5b', carbon: 0.2 },
  { id: 'pellet', name: '球团', cat: '中间产物', unit: 't', color: '#b0a060', carbon: 0.1 },
  { id: 'hot_metal', name: '铁水', cat: '中间产物', unit: 't', color: '#5f7d52', carbon: 1.6 },
  // 注：高炉渣/钢渣的"含碳"在物料平衡法里由 calculators.calc_bf/calc_bof 单独核算（渣含碳率，
  // 随渣量进入 carbon_to_slag，不计入 CO₂ 排放）；此处 carbon 仅作节点连线权重，不代表渣碳为 0。
  { id: 'bf_slag', name: '高炉渣', cat: '中间产物', unit: 't', color: '#7a7a6a', carbon: 0 },
  { id: 'pre_hm', name: '预处理铁水', cat: '中间产物', unit: 't', color: '#5f8d62', carbon: 1.6 },
  { id: 'crude_steel', name: '钢水', cat: '中间产物', unit: 't', color: '#4f9d6b', carbon: 0.1 },
  { id: 'steel_slag', name: '钢渣', cat: '中间产物', unit: 't', color: '#8a7aa0', carbon: 0 },
  { id: 'ldg', name: '转炉煤气', cat: '能源', unit: 'Nm³', color: '#7a8a5a', carbon: 0.002 },
  { id: 'conv_dust', name: '转炉尘/污泥', cat: '中间产物', unit: 't', color: '#9a9a8a', carbon: 0 },
  { id: 'refined_steel', name: '精炼钢水', cat: '中间产物', unit: 't', color: '#4fb07a', carbon: 0.05 },
  { id: 'billet', name: '连铸坯', cat: '中间产物', unit: 't', color: '#5fae7a', carbon: 0.05 },
  { id: 'steel_product', name: '钢材', cat: '中间产物', unit: 't', color: '#3f9d6b', carbon: 0.05 },
  { id: 'scale', name: '氧化铁皮', cat: '中间产物', unit: 't', color: '#a05a4a', carbon: 0 },
  // 能源/副产品
  { id: 'cog', name: '焦炉煤气', cat: '能源', unit: 'Nm³', color: '#8a9a4a', carbon: 0.002 },
  { id: 'bfg', name: '高炉煤气', cat: '能源', unit: 'Nm³', color: '#6b7a55', carbon: 0.0009 },
  { id: 'waste_heat', name: '余热', cat: '能源', unit: 'GJ', color: '#c0903e', carbon: 0 },
  { id: 'steam', name: '蒸汽', cat: '能源', unit: 't', color: '#9fb0b5', carbon: 0 },
  { id: 'self_power', name: '自发电', cat: '能源', unit: 'MWh', color: '#d4b24a', carbon: 0.18 },
  { id: 'co2', name: 'CO₂', cat: '副产品', unit: 't', color: '#c75a52', carbon: 1.0 },
  // 工辅对外输出的「驱动介质」（由鼓风机/热风炉/引风机等独立工艺产出，
  // 连到被服务工艺的输入端口，按"相同物料 id = 可连线"规则建立耦合）。
  // 这些介质自身不含碳，仅作为能量/动力传递载体。
  { id: 'blast_air', name: '鼓风(风量)', cat: '能源', unit: 'kNm³/h', color: '#5b9ac8', carbon: 0 },
  { id: 'hot_blast', name: '热风', cat: '能源', unit: '℃·kNm³/h', color: '#c8804e', carbon: 0 },
  { id: 'draft', name: '抽力', cat: '能源', unit: 'kPa', color: '#7a8ac8', carbon: 0 },
  { id: 'drive_power', name: '驱动电', cat: '能源', unit: 'MWh', color: '#e0b24a', carbon: 0.57 },
  { id: 'pulverized_coal', name: '喷吹煤粉', cat: '能源', unit: 't/h', color: '#6a6a6a', carbon: 2.4 },
  { id: 'combustion_air', name: '助燃风', cat: '能源', unit: 'kNm³/h', color: '#5b9ab0', carbon: 0 },
  { id: 'feeder_flow', name: '给料流', cat: '原料', unit: 't/h', color: '#8a9a5b', carbon: 0 },
  { id: 'cool_water', name: '冷却水', cat: '原料', unit: 't/h', color: '#4f97a0', carbon: 0 },
  { id: 'aux_steam', name: '辅助蒸汽', cat: '能源', unit: 't/h', color: '#9fb0b5', carbon: 0 },
  { id: 'electrode_power', name: '电极电', cat: '能源', unit: 'MWh', color: '#e0c24a', carbon: 0.57 },
  { id: 'oxy_supply', name: '供氧', cat: '能源', unit: 'kNm³/h', color: '#5b83c8', carbon: 0 },
]
export const MATERIAL_MAP = Object.fromEntries(MATERIALS.map((m) => [m.id, m]))
// 驱动介质族：把成对的"工辅输出口"与"被服务工艺输入口"归并到同一族，
// 保证连线时可匹配（输出 draft → 输入 draft 同 id 自然匹配；此处补充跨写法别名）。
export const MATERIAL_FAMILY = {
  sinter: 'sinter',
  hot_metal: 'hot_metal', pre_hm: 'hot_metal',
  steel: 'steel', crude_steel: 'steel', refined_steel: 'steel', billet: 'steel',
  self_power: 'power', electricity: 'power', drive_power: 'power', electrode_power: 'power', power: 'power',
  // 驱动介质自匹配族（与工辅输出口 id 一致即可连线）
  blast_air: 'blast_air', hot_blast: 'hot_blast', draft: 'draft',
  pulverized_coal: 'pulverized_coal', combustion_air: 'combustion_air',
  feeder_flow: 'feeder_flow', cool_water: 'cool_water', aux_steam: 'aux_steam',
  oxy_supply: 'oxy_supply',
}
export function materialFamily(id) { return MATERIAL_FAMILY[id] || id }
export const MATERIAL_CATS = ['原料', '中间产物', '能源', '副产品']

// 编排节点几何（FlowEditor 与 store 共用，避免放大/缩小时高度计算漂移）
export const NODE_NW = 196, NODE_HEADER = 32, NODE_PORT_Y0 = 46, NODE_GAP = 24
export function nodeHeight(n) {
  if (n.kind === 'device') return NODE_HEADER + 56
  const cnt = n.kind === 'material' ? 1 : Math.max(n.ports.in.length, n.ports.out.length, 1)
  return NODE_HEADER + (NODE_PORT_Y0 - 7) + (cnt - 1) * NODE_GAP + 16 + 12
}

// 终端产品（用于资产浏览器「产品」标签）：钢材 / 连铸坯 / 精炼钢水
export const PRODUCT_IDS = ['steel_product', 'billet', 'refined_steel']
export const PRODUCTS = PRODUCT_IDS.map((id) => MATERIAL_MAP[id]).filter(Boolean)

// ---------- 工艺模板 ----------
// efDirect: 单位主产物直接排放 tCO₂/t；efIndirect: 单位主产物间接(电)排放 tCO₂/t
// yield: 主产物/主原料 质量比；throughputParam: 决定主产物产量的参数键
// inputs/outputs: 默认端口物料（种类可在画布编辑）
export const PROCESS_TEMPLATES = [
  // —— 长流程 ——
  { type: 'sinter_plant', label: '烧结机', route: 'steel', mainIn: 'iron_ore', mainOut: 'sinter',
    efDirect: 0.20, efIndirect: 0.02, yield: 0.86,
    inputs: ['iron_ore', 'coke', 'limestone', 'draft'], outputs: ['sinter', 'bfg', 'co2'],
    params: [{ key: 'ore_rate', label: '矿量', unit: 't/h', min: 200, max: 2500, step: 50, def: 1100 },
             { key: 'fuel_rate', label: '燃料比', unit: 'kg/t', min: 20, max: 80, step: 1, def: 45 }],
    greenStrategies: [
      { id: 'sinter_hr', name: '烧结余热回收', desc: '回收烧结矿冷却废气显热，产蒸汽或发电', saving: '节电 25 kWh/t-烧结矿', carbon: 7.5, tags: ['余热'] },
      { id: 'sinter_flue_recirc', name: '烟气循环烧结', desc: '部分烧结烟气返回料层，减少烟气排放总量', saving: '减碳 8 kgCO₂/t-烧结矿', carbon: 8.0, tags: ['减排'] },
      { id: 'sinter_seal', name: '烧结机密封改造', desc: '降低台车与风箱间漏风率，提升有效风量', saving: '节电 5 kWh/t-烧结矿', carbon: 1.5, tags: ['节能'] },
      { id: 'sinter_deep_bed', name: '厚料层烧结', desc: '增加烧结料层高度至 700mm+，降低固体燃料消耗', saving: '节焦 3 kg/t-烧结矿', carbon: 6.0, tags: ['节能'] },
      { id: 'sinter_desox', name: '烧结烟气脱硫脱硝一体化', desc: '活性焦一体化脱硫脱硝，降低末端治理能耗', saving: '节电 2 kWh/t-烧结矿', carbon: 0.6, tags: ['减排'] },
    ] },
  { type: 'pelletizing', label: '球团', route: 'steel', mainIn: 'iron_ore', mainOut: 'pellet',
    efDirect: 0.10, efIndirect: 0.03, yield: 0.90,
    inputs: ['iron_ore', 'limestone', 'draft'], outputs: ['pellet', 'co2'],
    params: [{ key: 'ore_rate', label: '矿量', unit: 't/h', min: 100, max: 1200, step: 50, def: 500 },
             { key: 'fuel_rate', label: '燃料比', unit: 'kg/t', min: 5, max: 40, step: 1, def: 18 }],
    greenStrategies: [
      { id: 'pellet_grate_hr', name: '链篦机-回转窑余热回收', desc: '回收回转窑和环冷机废气余热用于干燥预热', saving: '节煤 8 kg/t-球团', carbon: 10.0, tags: ['余热'] },
      { id: 'pellet_deep_bed', name: '带式焙烧机料层加厚', desc: '增加焙烧料层厚度提升热效率', saving: '节气 5 %', carbon: 3.0, tags: ['节能'] },
      { id: 'pellet_gas_recirc', name: '球团预热废气循环', desc: '部分预热段废气返回利用，减少外排', saving: '节煤 3 kg/t-球团', carbon: 4.0, tags: ['节能'] },
    ] },
  { type: 'coke_oven', label: '焦炉', route: 'steel', mainIn: 'coal', mainOut: 'coke',
    efDirect: 0.30, efIndirect: 0.015, yield: 0.75,
    inputs: ['coal', 'combustion_air'], outputs: ['coke', 'cog', 'co2'],
    params: [{ key: 'coal_rate', label: '入炉煤', unit: 't/h', min: 100, max: 1200, step: 50, def: 475 }],
    greenStrategies: [
      { id: 'coke_cdq', name: '干熄焦(CDQ)', desc: '惰性气体冷却红焦并回收热量发电', saving: '节电 50 kWh/t-焦', carbon: 15.0, tags: ['余热'] },
      { id: 'coke_riser_hr', name: '焦炉上升管余热回收', desc: '回收荒煤气显热产蒸汽，取代管式炉', saving: '节煤 10 kg/t-焦', carbon: 12.0, tags: ['余热'] },
      { id: 'coke_flue_hr', name: '焦炉烟道气余热利用', desc: '烟道废气余热产蒸汽或预热煤料', saving: '节煤 5 kg/t-焦', carbon: 6.0, tags: ['余热'] },
      { id: 'coke_cmc', name: '煤调湿(CMC)', desc: '利用焦炉余热干燥入炉煤，降低水分提高堆密度', saving: '节煤 4 kg/t-焦', carbon: 5.0, tags: ['节能'] },
    ] },
  { type: 'blast_furnace', label: '高炉', route: 'steel', mainIn: 'sinter', mainOut: 'hot_metal',
    efDirect: 1.60, efIndirect: 0.03, yield: 0.62,
    inputs: ['sinter', 'pellet', 'coke', 'limestone', 'self_power', 'blast_air', 'hot_blast', 'pulverized_coal', 'electricity'], outputs: ['hot_metal', 'bf_slag', 'bfg', 'co2'],
    // 由独立工辅(鼓风机/热风炉/喷吹系统)经物料连线供给的驱动量，连线存在时覆盖下方手动参数
    drivenBy: { blast_air: 'wind_rate', hot_blast: 'hot_blast_temp', pulverized_coal: 'coal_inj', draft: 'draft' },
    params: [{ key: 'hot_metal', label: '铁水产量', unit: 't/h', min: 200, max: 2000, step: 50, def: 1000 },
             { key: 'coke_rate', label: '焦比', unit: 'kg/t', min: 250, max: 550, step: 5, def: 470 },
             { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 5, max: 60, step: 5, def: 30 },
             { key: 'coal_inj', label: '喷煤比', unit: 'kg/t', min: 0, max: 250, step: 5, def: 150 },
             { key: 'slag_rate', label: '渣比', unit: 'kg/t', min: 200, max: 450, step: 5, def: 300 },
             { key: 'flux', label: '熔剂比', unit: 'kg/t', min: 0, max: 150, step: 5, def: 120 },
             { key: 'wind_rate', label: '风量', unit: 'kNm³/h', min: 100, max: 900, step: 10, def: 600 },
             { key: 'hot_blast_temp', label: '热风温度', unit: '℃', min: 950, max: 1300, step: 10, def: 1250 },
             { key: 'oxygen_enrich', label: '富氧率', unit: '%', min: 0, max: 14, step: 0.5, def: 0 },
             { key: 'draft', label: '炉顶抽力(相对)', unit: '×', min: 0.5, max: 1.5, step: 0.02, def: 1.0 }],
    greenStrategies: [
      { id: 'bf_trt', name: '炉顶余压发电(TRT)', desc: '利用高炉炉顶煤气压力驱动透平发电', saving: '节电 40 kWh/t-铁水', carbon: 12.0, tags: ['余能'] },
      { id: 'bf_pci', name: '高炉富氧喷煤', desc: '提高喷煤量替代焦炭，降低焦比和碳排放', saving: '减碳 50 kgCO₂/t-铁水', carbon: 50.0, tags: ['减排'] },
      { id: 'bf_hot_stove_hr', name: '热风炉余热回收', desc: '回收热风炉烟气余热预热煤气和助燃空气', saving: '节气 8 %', carbon: 8.0, tags: ['余热'] },
      { id: 'bf_slag_hr', name: '高炉渣水淬余热回收', desc: '高炉水淬渣热水用于厂区供暖或低温发电', saving: '节标煤 15 kg/t-铁水', carbon: 6.0, tags: ['余热'] },
      { id: 'bf_dry_dedust', name: '高炉煤气干法除尘', desc: '干法布袋除尘替代湿法，节水节电', saving: '节电 5 kWh/t-铁水', carbon: 1.5, tags: ['节能'] },
      { id: 'bf_waste_plastic', name: '高炉喷吹废塑料', desc: '废塑料颗粒替代部分焦炭喷入风口', saving: '减碳 20 kgCO₂/t-铁水', carbon: 20.0, tags: ['减排'] },
    ] },
  { type: 'hot_metal_pretreat', label: '铁水预处理', route: 'steel', mainIn: 'hot_metal', mainOut: 'pre_hm',
    efDirect: 0.02, efIndirect: 0.02, yield: 0.99,
    inputs: ['hot_metal', 'oxygen'], outputs: ['pre_hm', 'co2'],
    params: [{ key: 'hm_rate', label: '铁水量', unit: 't/h', min: 200, max: 2000, step: 50, def: 1000 }],
    greenStrategies: [
      { id: 'hmpt_mg_opt', name: '铁水预处理镁基脱硫优化', desc: '优化喷吹参数降低镁粉消耗与铁损', saving: '降耗 20% 脱硫剂', carbon: 1.0, tags: ['节能'] },
      { id: 'hmpt_kr_opt', name: 'KR搅拌能效优化', desc: '优化搅拌转速和叶片结构降低电耗', saving: '节电 3 kWh/t-铁水', carbon: 0.9, tags: ['节能'] },
    ] },
  { type: 'bof', label: '转炉', route: 'steel', mainIn: 'pre_hm', mainOut: 'crude_steel',
    efDirect: 0.10, efIndirect: 0.03, yield: 0.96,
    inputs: ['pre_hm', 'scrap', 'limestone', 'oxygen'], outputs: ['crude_steel', 'steel_slag', 'ldg', 'conv_dust', 'co2'],
    params: [{ key: 'hot_metal_in', label: '铁水入炉', unit: 't/h', min: 200, max: 2000, step: 50, def: 1000 },
             { key: 'scrap', label: '废钢', unit: 't/h', min: 0, max: 600, step: 50, def: 100 },
             { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 5, max: 60, step: 5, def: 30 },
             { key: 'slag_rate', label: '渣比', unit: 'kg/t', min: 80, max: 200, step: 5, def: 120 },
             { key: 'flux', label: '熔剂比', unit: 'kg/t', min: 0, max: 150, step: 5, def: 60 }],
    greenStrategies: [
      { id: 'bof_ldg_recov', name: '转炉煤气回收(OG法)', desc: '回收转炉吹炼CO气体作为燃料气，降低外购能源', saving: '回收 0.8 GJ/t-钢', carbon: 30.0, tags: ['余能'] },
      { id: 'bof_neg_energy', name: '转炉负能炼钢', desc: '通过蒸汽回收+煤气回收实现净能量输出', saving: '节电 30 kWh/t-钢', carbon: 9.0, tags: ['节能'] },
      { id: 'bof_flue_hr', name: '转炉烟气余热回收', desc: '回收转炉烟气(1450℃)显热产蒸汽', saving: '节标煤 8 kg/t-钢', carbon: 10.0, tags: ['余热'] },
      { id: 'bof_co2_bottom', name: '转炉底吹CO₂搅拌', desc: 'CO₂替代Ar/N₂底吹搅拌，实现碳利用', saving: '减碳 5 kgCO₂/t-钢', carbon: 5.0, tags: ['减排'] },
      { id: 'bof_ladle_cover', name: '钢包加盖保温', desc: '钢包全程加盖减少钢水温降和烘烤能耗', saving: '节电 3 kWh/t-钢', carbon: 1.0, tags: ['节能'] },
    ] },
  { type: 'ladle_furnace', label: 'LF精炼', route: 'steel', mainIn: 'crude_steel', mainOut: 'refined_steel',
    efDirect: 0.0, efIndirect: 0.015, yield: 0.995,
    inputs: ['crude_steel', 'electricity'], outputs: ['refined_steel', 'co2'],
    params: [{ key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50, def: 1000 },
             { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 5, max: 60, step: 5, def: 25 }],
    greenStrategies: [
      { id: 'lf_submerged_arc', name: 'LF埋弧加热优化', desc: '优化造渣和电压档位提高电弧热效率', saving: '节电 5 kWh/t-钢', carbon: 1.5, tags: ['节能'] },
      { id: 'lf_ladle_heater', name: '钢包蓄热式烘烤', desc: '蓄热式燃烧技术回收烟气余热预热烘烤空气', saving: '节气 40 %', carbon: 2.0, tags: ['余热'] },
    ] },
  { type: 'rh_vacuum', label: 'RH精炼', route: 'steel', mainIn: 'refined_steel', mainOut: 'refined_steel',
    efDirect: 0.0, efIndirect: 0.005, yield: 0.998,
    inputs: ['refined_steel', 'electricity'], outputs: ['refined_steel', 'co2'],
    params: [{ key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50, def: 1000 },
             { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 1, max: 15, step: 1, def: 5 }],
    greenStrategies: [
      { id: 'rh_vac_vfd', name: 'RH真空泵变频调速', desc: '根据脱气阶段自动调节真空泵转速', saving: '节电 2 kWh/t-钢', carbon: 0.6, tags: ['节能'] },
      { id: 'rh_light_treat', name: 'RH轻处理工艺', desc: '减少深真空处理时间仅作成分微调', saving: '节电 1 kWh/t-钢', carbon: 0.3, tags: ['节能'] },
    ] },
  { type: 'caster', label: '连铸机', route: 'steel', mainIn: 'refined_steel', mainOut: 'billet',
    efDirect: 0.0, efIndirect: 0.01, yield: 0.97,
    inputs: ['refined_steel', 'electricity'], outputs: ['billet', 'scale'],
    params: [{ key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50, def: 1000 },
             { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 2, max: 40, step: 2, def: 15 }],
    greenStrategies: [
      { id: 'cc_hcr', name: '连铸坯热送热装(HCR)', desc: '高温连铸坯直接送入加热炉，减少加热能耗', saving: '节气 50 %', carbon: 15.0, tags: ['节能'] },
      { id: 'cc_tundish_heat', name: '中间包感应加热', desc: '等离子/感应加热精准控温降低过热度', saving: '节电 2 kWh/t-钢', carbon: 0.6, tags: ['节能'] },
      { id: 'cc_2nd_cool', name: '连铸二冷动态控制', desc: '基于实时温度模型优化各段冷却水量', saving: '节水 15 %', carbon: 0.3, tags: ['节能'] },
    ] },
  { type: 'rolling_mill', label: '热轧机', route: 'steel', mainIn: 'billet', mainOut: 'steel_product',
    efDirect: 0.02, efIndirect: 0.03, yield: 0.95,
    inputs: ['billet', 'ngas', 'electricity'], outputs: ['steel_product', 'scale', 'co2'],
    params: [{ key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50, def: 1000 },
             { key: 'ng_rate', label: '天然气', unit: 'm³/t', min: 0, max: 80, step: 2, def: 32 },
             { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 10, max: 160, step: 5, def: 80 }],
    greenStrategies: [
      { id: 'rm_regen_burner', name: '加热炉蓄热式燃烧', desc: '蓄热体交替回收烟气余热预热助燃空气', saving: '节气 30 %', carbon: 12.0, tags: ['余热'] },
      { id: 'rm_laminar_hr', name: '热轧层流冷却余热回收', desc: '回收层流冷却水余热用于供暖或预热', saving: '余热回收 1.5 GJ/t-钢', carbon: 4.0, tags: ['余热'] },
      { id: 'rm_oil_mist', name: '轧制油雾回收', desc: '油雾过滤回收减少油耗和排放', saving: '降耗 15 % 轧制油', carbon: 0.5, tags: ['减排'] },
      { id: 'rm_vfd', name: '主传动变频调速节能', desc: '主轧机传动电机变频化替代直流调速', saving: '节电 8 %', carbon: 2.5, tags: ['节能'] },
    ] },

  // —— 短流程 ——
  { type: 'eaf', label: '电炉', route: 'steel', mainIn: 'scrap', mainOut: 'crude_steel',
    efDirect: 0.05, efIndirect: 0.25, yield: 0.95,
    inputs: ['scrap', 'dri', 'pig_iron', 'electricity', 'oxygen', 'self_power', 'drive_power', 'electrode_power'], outputs: ['crude_steel', 'steel_slag', 'ldg', 'co2'],
    params: [{ key: 'scrap', label: '废钢', unit: 't/h', min: 0, max: 2000, step: 50, def: 900 },
             { key: 'dri', label: '直接还原铁', unit: 't/h', min: 0, max: 800, step: 50, def: 150 },
             { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 50, max: 700, step: 20, def: 360 }],
    greenStrategies: [
      { id: 'eaf_scrap_preheat', name: '废钢连续预热', desc: '利用电炉烟气(1200℃+)预热废钢降低电耗', saving: '节电 80 kWh/t-钢', carbon: 48.0, tags: ['余热'] },
      { id: 'eaf_foamy_slag', name: '泡沫渣操作', desc: '优化埋弧操作减少电弧热辐射损失', saving: '节电 20 kWh/t-钢', carbon: 12.0, tags: ['节能'] },
      { id: 'eaf_oxyfuel', name: '氧燃枪助熔', desc: '吹氧+喷碳加速熔化缩短冶炼周期', saving: '节电 30 kWh/t-钢', carbon: 18.0, tags: ['节能'] },
      { id: 'eaf_flue_hr', name: '电炉烟气余热回收', desc: '回收第四孔烟气余热产蒸汽', saving: '节标煤 10 kg/t-钢', carbon: 8.0, tags: ['余热'] },
      { id: 'eaf_smart_power', name: '电弧炉智能供电', desc: '基于神经网络优化各冶炼期供电曲线', saving: '节电 15 kWh/t-钢', carbon: 9.0, tags: ['节能'] },
    ] },

  // 直接还原竖炉(Midrex)：短流程上游原料制备，以天然气催化重整生成还原气(H₂+CO)将球团/块矿还原为 DRI(海绵铁)，
  // 主要消耗天然气(供热/制气)与电力(供料/循环/压缩)，是短流程供氧/供电/供气耦合的关键环节。
  { type: 'dri_midrex', label: 'DRI竖炉', route: 'steel', mainIn: 'iron_ore', mainOut: 'dri',
    efDirect: 0.60, efIndirect: 0.09, yield: 0.92,
    inputs: ['iron_ore', 'ngas', 'oxygen', 'self_power', 'drive_power'], outputs: ['dri', 'co2', 'top_gas'],
    params: [{ key: 'ore_rate', label: '矿量', unit: 't/h', min: 100, max: 800, step: 50, def: 330 },
             { key: 'dri_out', label: 'DRI产量', unit: 't/h', min: 50, max: 700, step: 50, def: 300 },
             { key: 'ng_rate', label: '天然气耗', unit: 'm³/t-DRI', min: 200, max: 400, step: 10, def: 300 },
             { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 10, max: 150, step: 5, def: 45 },
             { key: 'h2_ratio', label: 'H₂占比', unit: '%', min: 40, max: 95, step: 5, def: 55 }],
    greenStrategies: [
      { id: 'dri_h2_shift', name: '氢基还原切换', desc: '提高还原气中H₂占比，降低天然气碳强度', saving: '减碳 60 kgCO₂/t-DRI', carbon: 60.0, tags: ['减排'] },
      { id: 'dri_topgas_recirc', name: '竖炉顶气循环', desc: '净化后顶气(CO+H₂)再循环入炉，提高还原气利用率', saving: '节气 15%', carbon: 12.0, tags: ['节能'] },
      { id: 'dri_green_ng', name: '绿氢/绿电制气', desc: '以绿电电解水制氢或绿电驱动重整，降低范围二排放', saving: '减碳随绿电占比', carbon: 0, tags: ['减排'] },
      { id: 'dri_heat_recovery', name: '竖炉余热回收', desc: '回收冷却段显热与高温DRI物理热用于发电或供热', saving: '节标煤 20 kg/t-DRI', carbon: 8.0, tags: ['余热'] },
    ] },

  // —— 公用/节能减碳（保留供 3D 仿真引用，不在工艺树中展示） ——
  { type: 'gas_power', label: '煤气发电', route: 'util', mainIn: 'bfg', mainOut: 'self_power',
    efDirect: 0.0, efIndirect: 0.0, yield: 0.30,
    inputs: ['bfg', 'ldg', 'cog'], outputs: ['self_power', 'steam'],
    params: [{ key: 'gas_in', label: '煤气量', unit: 'kNm³/h', min: 50, max: 2000, step: 20, def: 600 }] },
  { type: 'waste_heat', label: '余热回收', route: 'util', mainIn: 'waste_heat', mainOut: 'self_power',
    efDirect: 0.0, efIndirect: 0.0, yield: 0.12,
    inputs: ['waste_heat'], outputs: ['self_power', 'steam'],
    params: [{ key: 'heat_in', label: '余热', unit: 'GJ/h', min: 50, max: 3000, step: 20, def: 800 }] },
  { type: 'ccs', label: '碳捕集', route: 'util', mainIn: 'co2', mainOut: null,
    efDirect: 0.0, efIndirect: 0.05, yield: 0.9,
    inputs: ['co2'], outputs: [],
    params: [{ key: 'capture', label: '捕集率', unit: '%', min: 0, max: 95, step: 5, def: 60 }] },

  // ---------- 工辅（独立工艺节点，自身不直接产碳，仅耗电并对外输出驱动介质） ----------
  // 这些原本是"挂在被服务工艺下的可调设备"，现抽成独立工艺：
  //   其"可调"是自身功率/风量等；通过物料连线(鼓风/热风/抽力/驱动电…)驱动被服务工艺参数。
  // efDirect = 0（不直接产碳）；电耗由运行参数折算为范围二排放。
  { type: 'blower', label: '鼓风机', route: 'aux', mainIn: null, mainOut: 'blast_air',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    // oxygen: 全厂供氧系统集中供氧（富氧率由供氧系统·供氧量驱动，鼓风机不再单独喷氧）
    inputs: ['oxygen'], outputs: ['blast_air'],
    // power: 配套电机功率 MW；air_rate: 实际供风量 kNm³/h；humidity: 鼓风湿度 g/Nm³（加湿/脱湿调节，影响风口热制度）
    params: [{ key: 'power', label: '电机功率', unit: 'MW', min: 10, max: 80, step: 1, def: 36 },
             { key: 'air_rate', label: '供风量', unit: 'kNm³/h', min: 100, max: 900, step: 10, def: 600 },
             { key: 'humidity', label: '鼓风湿度', unit: 'g/Nm³', min: 0, max: 30, step: 1, def: 10 },
             { key: 'pressure', label: '出口风压', unit: 'kPa', min: 200, max: 600, step: 10, def: 420 }],
    // 高炉 wind_rate 为绝对供风量（kNm³/h），与鼓风机 air_rate 同量纲，连线直接写入。
    // 与设备折算同一基准：设备设定 def 5200（m³/h）↔ 600 kNm³/h → LEGACY scale 600 → air_rate 600 kNm³/h。
    drives: { blast_air: { src: 'air_rate', dst: 'wind_rate' } },
    greenStrategies: [
      { id: 'blower_vfd', name: '鼓风机变频调速', desc: '按高炉需风量自动调节转速，避免恒速节流损耗', saving: '节电 8%', carbon: 6.0, tags: ['节能'] },
    ] },
  { type: 'hot_blast_stove', label: '热风炉', route: 'aux', mainIn: null, mainOut: 'hot_blast',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    // blast_air: 鼓风机供入的冷风（燃烧助燃风），使「鼓风机→热风炉」连线成立
    inputs: ['blast_air'], outputs: ['hot_blast'],
    // firing_rate: 燃烧煤气量 kNm³/h（计入被服务工艺碳排，本工艺不计直接碳）；
    // power: 助燃风机电机功率 MW（本工艺电耗）；blast_temp: 送风温度 ℃
    params: [{ key: 'power', label: '助燃风机功率', unit: 'MW', min: 1, max: 12, step: 0.5, def: 6 },
             { key: 'firing_rate', label: '燃烧煤气量', unit: 'kNm³/h', min: 50, max: 400, step: 10, def: 220 },
             { key: 'blast_temp', label: '送风温度', unit: '℃', min: 950, max: 1300, step: 10, def: 1250 },
             { key: 'thermal_eff', label: '热效率', unit: '%', min: 60, max: 92, step: 1, def: 80 }],
    drives: { hot_blast: { src: 'blast_temp', dst: 'hot_blast_temp' } },
    greenStrategies: [
      { id: 'hbs_preheat', name: '热风炉烟气预热', desc: '回收热风炉烟气余热预热煤气与助燃空气', saving: '节气 8%', carbon: 8.0, tags: ['余热'] },
    ] },
  { type: 'id_fan', label: '引风机', route: 'aux', mainIn: null, mainOut: 'draft',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: [], outputs: ['draft'],
    // power: 电机功率 MW；draught: 抽力 kPa
    params: [{ key: 'power', label: '电机功率', unit: 'MW', min: 2, max: 20, step: 0.5, def: 8 },
             { key: 'draught', label: '抽力', unit: 'kPa', min: 1, max: 8, step: 0.2, def: 3.5 }],
    drives: { draft: { src: 'draught', dst: 'draft' } },
    greenStrategies: [
      { id: 'idfan_vfd', name: '引风机变频调速', desc: '按系统负压自动调节变频转速', saving: '节电 10%', carbon: 3.0, tags: ['节能'] },
    ] },
  { type: 'injector', label: '喷吹系统', route: 'aux', mainIn: null, mainOut: 'pulverized_coal',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: [], outputs: ['pulverized_coal'],
    params: [{ key: 'power', label: '载气压缩机功率', unit: 'MW', min: 1, max: 15, step: 0.5, def: 7 },
             { key: 'inj_rate', label: '喷吹量', unit: 't/h', min: 0, max: 200, step: 5, def: 120 },
             { key: 'transport_air', label: '载气量', unit: 'kNm³/h', min: 0, max: 120, step: 5, def: 60 }],
    drives: { pulverized_coal: { src: 'inj_rate', dst: 'coal_inj' } },
    greenStrategies: [
      { id: 'inj_opt', name: '喷吹均匀性优化', desc: '优化分配器降低吨煤载气能耗', saving: '节电 5%', carbon: 1.5, tags: ['节能'] },
    ] },
  { type: 'combustion_blower', label: '助燃风机', route: 'aux', mainIn: null, mainOut: 'combustion_air',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: [], outputs: ['combustion_air'],
    params: [{ key: 'power', label: '电机功率', unit: 'MW', min: 1, max: 15, step: 0.5, def: 5 },
             { key: 'air_rate', label: '供风量', unit: 'kNm³/h', min: 20, max: 300, step: 10, def: 150 }],
    drives: { combustion_air: { src: 'air_rate', dst: 'combustion_air' } },
    greenStrategies: [
      { id: 'cb_vfd', name: '助燃风机变频', desc: '按燃烧需氧量自动调节供风', saving: '节电 7%', carbon: 2.0, tags: ['节能'] },
    ] },
  { type: 'drive_supply', label: '驱动供电', route: 'aux', mainIn: null, mainOut: 'drive_power',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: ['electricity'], outputs: ['drive_power'],
    params: [{ key: 'power', label: '供电功率', unit: 'MW', min: 1, max: 120, step: 1, def: 60 },
             { key: 'green_ratio', label: '绿电占比', unit: '%', min: 0, max: 100, step: 5, def: 20 }],
    drives: { drive_power: { src: 'power', dst: 'power' } },
    greenStrategies: [
      { id: 'ds_green', name: '提高绿电占比', desc: '驱动供电切换绿电降低范围二排放', saving: '降碳随绿电占比', carbon: 0, tags: ['减排'] },
    ] },
  { type: 'electrode_reg', label: '电极调节', route: 'aux', mainIn: null, mainOut: 'electrode_power',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: ['electricity'], outputs: ['electrode_power'],
    params: [{ key: 'power', label: '电极功率', unit: 'MW', min: 10, max: 200, step: 5, def: 90 },
             { key: 'current', label: '电弧电流', unit: 'kA', min: 20, max: 120, step: 2, def: 70 }],
    drives: { electrode_power: { src: 'power', dst: 'power' } },
    greenStrategies: [
      { id: 'er_smart', name: '智能电极控制', desc: '基于阻抗模型优化供电曲线降低短网损耗', saving: '节电 4%', carbon: 2.4, tags: ['节能'] },
    ] },
  { type: 'belt_conv', label: '皮带机', route: 'aux', mainIn: 'feeder_flow', mainOut: 'feeder_flow',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: ['feeder_flow'], outputs: ['feeder_flow'],
    params: [{ key: 'power', label: '电机功率', unit: 'MW', min: 0.5, max: 8, step: 0.5, def: 3 },
             { key: 'throughput', label: '输送量', unit: 't/h', min: 100, max: 5000, step: 50, def: 1500 }],
    drives: {},
    greenStrategies: [
      { id: 'bc_vfd', name: '皮带机变频', desc: '按料流自动调速减少空转', saving: '节电 12%', carbon: 2.0, tags: ['节能'] },
    ] },
  { type: 'feeder', label: '给料机', route: 'aux', mainIn: 'feeder_flow', mainOut: 'feeder_flow',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: ['feeder_flow'], outputs: ['feeder_flow'],
    params: [{ key: 'power', label: '电机功率', unit: 'MW', min: 0.2, max: 4, step: 0.2, def: 1.2 },
             { key: 'rate', label: '给料速率', unit: 't/h', min: 10, max: 2000, step: 10, def: 400 }],
    drives: {},
    greenStrategies: [] },
  { type: 'cool_pump', label: '冷却水泵', route: 'aux', mainIn: null, mainOut: 'cool_water',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: [], outputs: ['cool_water'],
    params: [{ key: 'power', label: '电机功率', unit: 'MW', min: 0.5, max: 12, step: 0.5, def: 4 },
             { key: 'flow', label: '循环水量', unit: 't/h', min: 100, max: 6000, step: 50, def: 2000 }],
    drives: {},
    greenStrategies: [
      { id: 'cp_vfd', name: '冷却水泵变频', desc: '按温差自动调节循环水量', saving: '节电 15%', carbon: 2.5, tags: ['节能'] },
    ] },
  { type: 'aux_boiler', label: '辅助锅炉', route: 'aux', mainIn: null, mainOut: 'aux_steam',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: ['ngas'], outputs: ['aux_steam'],
    params: [{ key: 'steam_rate', label: '产汽量', unit: 't/h', min: 5, max: 200, step: 5, def: 80 },
             { key: 'thermal_eff', label: '热效率', unit: '%', min: 70, max: 95, step: 1, def: 88 }],
    drives: {},
    greenStrategies: [
      { id: 'ab_hr', name: '锅炉烟道余热', desc: '回收排烟余热预热给水', saving: '节气 5%', carbon: 3.0, tags: ['余热'] },
    ] },
  { type: 'oxy_plant', label: '空分制氧', route: 'aux', mainIn: null, mainOut: 'oxy_supply',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: ['electricity'], outputs: ['oxy_supply'],
    params: [{ key: 'power', label: '电耗功率', unit: 'MW', min: 5, max: 80, step: 2, def: 40 },
             { key: 'oxygen_rate', label: '产氧量', unit: 'kNm³/h', min: 20, max: 600, step: 10, def: 260 }],
    drives: { oxy_supply: { src: 'oxygen_rate', dst: 'oxygen_enrich' } },
    greenStrategies: [
      { id: 'ox_vsa', name: '变压吸附优化', desc: '优化吸附周期降低单位氧电耗', saving: '节电 6%', carbon: 3.5, tags: ['节能'] },
    ] },
  // 全厂供氧系统（区域级空分制氧站）：向转炉、铁水预处理、电炉等集中供给工业氧气。
  // 与就地空分(oxy_plant)不同，oxy_supply 是跨工序的公用氧源，产氧量按各用氧工序规模配套。
  { type: 'oxy_supply', label: '供氧系统', route: 'aux', mainIn: null, mainOut: 'oxygen',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: ['electricity'], outputs: ['oxygen'],
    params: [{ key: 'power', label: '制氧电耗', unit: 'MW', min: 5, max: 200, step: 5, def: 80 },
             { key: 'oxygen_rate', label: '供氧量', unit: 'kNm³/h', min: 20, max: 1500, step: 20, def: 600 },
             { key: 'green_ratio', label: '绿电占比', unit: '%', min: 0, max: 100, step: 5, def: 15 }],
    drives: { oxygen: { src: 'oxygen_rate', dst: 'oxygen_enrich' } },
    greenStrategies: [
      { id: 'ox_green', name: '制氧绿电化', desc: '空分制氧为高耗电环节，切换绿电可显著降低范围二排放', saving: '降碳随绿电占比', carbon: 0, tags: ['减排'] },
    ] },
  // 全厂供电系统（供电车间/主变电站）：汇集外购电与自发电（BFG/CDQ/余热发电），
  // 统一向用电工序（高炉、电炉、精炼、连铸、轧制）供给电力，并按绿电占比抵扣范围二排放。
  { type: 'power_supply', label: '供电系统', route: 'aux', mainIn: null, mainOut: 'electricity',
    efDirect: 0.0, efIndirect: 0.0, yield: 0,
    inputs: ['electricity'], outputs: ['electricity'],
    params: [{ key: 'power', label: '供电负荷', unit: 'MW', min: 1, max: 600, step: 5, def: 200 },
             { key: 'green_ratio', label: '绿电占比', unit: '%', min: 0, max: 100, step: 5, def: 15 },
             { key: 'self_gen_ratio', label: '自发电占比', unit: '%', min: 0, max: 100, step: 5, def: 40 }],
    drives: { electricity: { src: 'power', dst: 'electricity' } },
    greenStrategies: [
      { id: 'ps_green', name: '提升绿电占比', desc: '外购电切换风电/光伏绿电降低范围二排放', saving: '降碳随绿电占比', carbon: 0, tags: ['减排'] },
      { id: 'ps_selfgen', name: '提高自发电', desc: '提升 BFG/CDQ/余热自发电比例，减少外购电', saving: '降碳随自发电占比', carbon: 0, tags: ['余热'] },
    ] },
]

// 设备可减排影响的工艺类型（用于可调设备对 efDirect 的修正）
export const PROCESS_MAP = Object.fromEntries(PROCESS_TEMPLATES.map((t) => [t.type, t]))
// 工艺分组：炼钢(长/短流程统一) + 工辅。
// 注：util(煤气发电/余热回收/碳捕集)类属节能减碳范畴，按设计统一在「策略」中展示，
// 不纳入左侧工艺资源管理树，仅保留模板供 3D 孪生与策略引用。
export const ROUTE_ORDER = { steel: '炼钢', aux: '工辅' }
export const ROUTE_GROUPS = {
  steel: PROCESS_TEMPLATES.filter((t) => t.route === 'steel'),
  // 工辅分组 = 工辅路线 + 公用/节能减碳（煤气发电/余热回收/碳捕集），保证系统现有工辅在资源管理列表中可见
  aux: PROCESS_TEMPLATES.filter((t) => t.route === 'aux' || t.route === 'util'),
}

// ---------- 设备模板 ----------
// kind: metering(计量,只读) | adjustable(可调,设定)
// setpoint: 可调设备设定范围；powerPerUnit: 单位设定值电耗(MWh)，用于估算间接排放
export const DEVICE_TEMPLATES = [
  // 计量设备（只读监测）
  { type: 'belt_scale', label: '皮带秤', kind: 'metering', unit: 't/h', measures: '物料流量', icon: 'belt', desc: '本工序的计量设备，连续称量输送带上的固体物料（矿、焦、煤、熔剂等）质量流量，其读数作为碳核算「活动数据」的主源头。' },
  { type: 'loss_in_weight', label: '失重秤', kind: 'metering', unit: 't/h', measures: '给料量', icon: 'hopper', desc: '本工序的计量设备，用于喷吹煤粉、熔剂等粉料的精确给料计量，对应喷煤比、熔剂比等单耗的实测来源。' },
  { type: 'hopper_scale', label: '料斗秤', kind: 'metering', unit: 't', measures: '批料重量', icon: 'hopper', desc: '本工序的计量设备，计量配料仓/喷吹罐的批料重量，对应焦比、喷煤比、熔剂比等单耗的实测来源。' },
  { type: 'weighbridge', label: '平台秤', kind: 'metering', unit: 't', measures: '进出厂重量', icon: 'hopper', desc: '本工序的计量设备，计量原燃料与产品的进出厂重量，用于厂界物料平衡与碳流核算。' },
  { type: 'gas_flowmeter', label: '气体流量计', kind: 'metering', unit: 'Nm³/h', measures: '煤气/空气/氧气', icon: 'pipe', desc: '本工序的计量设备，配温度/压力补偿计量高炉煤气、转炉煤气、天然气、氧气等气体体积流量，对应燃料类直接排放的「活动数据」。' },
  { type: 'liquid_flowmeter', label: '液体流量计', kind: 'metering', unit: 'm³/h', measures: '冷却水/喷吹', icon: 'pipe', desc: '本工序的计量设备，计量冷却水、喷吹介质等液体流量，支撑水耗与工艺能耗核算。' },
  { type: 'power_meter', label: '电能表', kind: 'metering', unit: 'kWh', measures: '电耗', icon: 'gauge', desc: '本工序的计量设备，分项计量工序/大电机电耗，对应范围二（外购电）间接排放的活动数据。' },
  { type: 'composition_analyzer', label: '成分分析仪', kind: 'metering', unit: '%', measures: '品位/成分', icon: 'flask', desc: '本工序的计量设备，测定矿石品位、燃料含碳率等成分，用于精化排放因子（替代默认含碳假设）。' },
  { type: 'cems', label: '烟气连续监测', kind: 'metering', unit: 'mg/m³', measures: 'CO₂/SO₂/NOx', icon: 'stack', desc: '本工序的计量设备，连续监测烟气中 CO₂/SO₂/NOx 浓度与流量，直接测得排放，作为因子法的交叉校验（点源直接监测法）。' },
  { type: 'thermo', label: '测温仪', kind: 'metering', unit: '℃', measures: '温度', icon: 'gauge', desc: '本工序的计量设备，实时监测炉膛/烟气温度，用于燃烧控制与热效率核算。' },
  // 可调设备（可设定）
  // response: 设定值→测定值 响应特性（bias: 稳态偏差率, noise: 测量噪声幅度）。设定值(SP)由
  // 操作/策略调节，经设备响应产生测定值(PV)，二者存在差异；平台核算一律以测定值为准。
  { type: 'blower', label: '鼓风机', kind: 'adjustable', unit: 'm³/h', setpoint: { min: 3000, max: 9000, def: 5200, unit: 'm³/h', label: '风量' }, extraSetpoints: [{ key: 'humidity', label: '鼓风湿度', unit: 'g/Nm³', min: 0, max: 30, def: 10, step: 1, powerPerUnit: 0 }], powerPerUnit: 0.00006, effType: 'blower', measures: '风量', response: { bias: 0.03, noise: 0.01 }, desc: '本工序的可调设备，其风量设定经碳引擎折算为鼓风电耗与间接排放；风量↑→风口燃烧带活性↑、允许更高喷煤，是减排策略的作用对象；鼓风湿度（加湿/脱湿）参与高炉热制度（TFT）计算，湿度↑→理论燃烧温度↓。' },
  { type: 'id_fan', label: '引风机', kind: 'adjustable', unit: 'm³/h', setpoint: { min: 2000, max: 8000, def: 4000, unit: 'm³/h' }, powerPerUnit: 0.00004, effType: 'none', measures: '烟气抽力', response: { bias: 0.04, noise: 0.012 }, desc: '本工序的可调设备，其设定值经碳引擎折算为运行电耗与间接排放，是减排策略的作用对象。' },
  { type: 'belt_conv', label: '皮带机', kind: 'adjustable', unit: 'm/s', setpoint: { min: 0.5, max: 4, def: 2, unit: 'm/s' }, powerPerUnit: 0.8, effType: 'feeder', measures: '带速/给料量', response: { bias: 0.02, noise: 0.008 }, desc: '本工序的可调设备，控制物料输送带速与给料量，其设定值经碳引擎折算为传动电耗与间接排放，是减排策略的作用对象。' },
  { type: 'feeder', label: '给料机', kind: 'adjustable', unit: 't/h', setpoint: { min: 10, max: 500, def: 200, unit: 't/h' }, powerPerUnit: 0.01, effType: 'feeder', measures: '给料速率', response: { bias: 0.03, noise: 0.01 }, desc: '本工序的可调设备，控制矿、燃料、熔剂等给料速率，其设定值经碳引擎折算为给料电耗与间接排放，是减排策略的作用对象。' },
  { type: 'pump', label: '泵', kind: 'adjustable', unit: 'm³/h', setpoint: { min: 10, max: 1000, def: 300, unit: 'm³/h' }, powerPerUnit: 0.002, effType: 'none', measures: '流量/扬程', response: { bias: 0.05, noise: 0.015 }, desc: '本工序的可调设备，控制流体输送流量/扬程，其设定值经碳引擎折算为泵组电耗与间接排放，是减排策略的作用对象。' },
  { type: 'valve', label: '调节阀', kind: 'adjustable', unit: '%', setpoint: { min: 0, max: 100, def: 50, unit: '%' }, powerPerUnit: 0, effType: 'none', measures: '开度', response: { bias: 0.05, noise: 0.02 }, desc: '本工序的可调设备，控制管路开度以调节介质流量，其设定值经碳引擎折算为调节能耗与间接排放，是减排策略的作用对象。' },
  { type: 'burner', label: '燃烧器', kind: 'adjustable', unit: 'ratio', setpoint: { min: 0.8, max: 1.3, def: 1.0, unit: '空燃比' }, powerPerUnit: 0, effType: 'burner', measures: '空燃比', response: { bias: 0.02, noise: 0.008 }, desc: '本工序的可调设备，其空燃比设定影响燃料完全燃烧程度，经碳引擎折算为燃料消耗与直接/间接排放，是减排策略的作用对象。' },
  { type: 'injector', label: '喷吹系统', kind: 'adjustable', unit: 'kg/h', setpoint: { min: 0, max: 300, def: 120, unit: 'kg/h' }, powerPerUnit: 0.005, effType: 'feeder', measures: '喷吹速率', response: { bias: 0.03, noise: 0.01 }, desc: '本工序的可调设备，喷吹煤粉等以顶替焦炭，其喷吹速率设定经碳引擎折算为喷吹能耗与间接排放，是减排策略的作用对象。' },
  { type: 'electrode_reg', label: '电极调节器', kind: 'adjustable', unit: 'MW', setpoint: { min: 20, max: 120, def: 70, unit: 'MW' }, powerPerUnit: 0.01, effType: 'none', measures: '电弧功率', response: { bias: 0.02, noise: 0.008 }, desc: '本工序的可调设备，控制电弧功率以调节熔化/加热强度，其设定值经碳引擎折算为电耗与间接排放，是减排策略的作用对象。' },
  { type: 'vfd', label: '变频器', kind: 'adjustable', unit: 'Hz', setpoint: { min: 0, max: 50, def: 40, unit: 'Hz' }, powerPerUnit: 0, effType: 'none', measures: '电机转速', response: { bias: 0.01, noise: 0.005 }, desc: '本工序的可调设备，通过改变电机频率调节转速，其设定值经碳引擎折算为节电效果与间接排放，是减排策略的作用对象。' },
  { type: 'oxygen_lance', label: '氧枪', kind: 'adjustable', unit: 'Nm³/h', setpoint: { min: 1000, max: 8000, def: 4000, unit: 'Nm³/h' }, powerPerUnit: 0.00002, effType: 'none', measures: '供氧强度', response: { bias: 0.02, noise: 0.008 }, desc: '本工序的可调设备，控制供氧强度以强化冶炼/富氧，其设定值经碳引擎折算为制氧能耗与间接排放，是减排策略的作用对象。' },
  { type: 'cool_pump', label: '冷却水泵', kind: 'adjustable', unit: 'm³/h', setpoint: { min: 50, max: 800, def: 300, unit: 'm³/h' }, powerPerUnit: 0.002, effType: 'none', measures: '水量/温度', response: { bias: 0.04, noise: 0.012 }, desc: '本工序的可调设备，控制冷却水量维持设备热平衡，其设定值经碳引擎折算为泵组电耗与间接排放，是减排策略的作用对象。' },
  { type: 'dedust_fan', label: '除尘风机', kind: 'adjustable', unit: 'm³/h', setpoint: { min: 1000, max: 6000, def: 3000, unit: 'm³/h' }, powerPerUnit: 0.00005, effType: 'none', measures: '风量', response: { bias: 0.03, noise: 0.01 }, desc: '本工序的可调设备，控制除尘风量维持收尘效率，其设定值经碳引擎折算为运行电耗与间接排放，是减排策略的作用对象。' },
  { type: 'waste_heat_boiler', label: '余热锅炉', kind: 'adjustable', unit: 't/h', setpoint: { min: 10, max: 300, def: 120, unit: 't/h' }, powerPerUnit: 0, effType: 'none', measures: '蒸汽产量', response: { bias: 0.03, noise: 0.01 }, desc: '本工序的可调设备，控制余热回收蒸汽产量，其设定值经碳引擎折算为余热回收量（负向排放），是减排策略的作用对象。' },
  { type: 'hot_blast_stove', label: '热风炉', kind: 'adjustable', unit: '℃', setpoint: { min: 900, max: 1300, def: 1250, unit: '℃' }, powerPerUnit: 0, effType: 'none', measures: '热风温度', response: { bias: 0.01, noise: 0.005 }, desc: '本工序的可调设备，其热风温度设定经碳引擎折算为煤气消耗与直接排放；风温↑→热效率↑、焦比↓，是减排策略的作用对象。' },
  // 全厂级工辅（供氧/供电）自身的可调设备：作为独立实体挂在工辅工艺下，
  // 供氧量/供电负荷设定对应工艺参数（oxygen_rate/power），经物料连线供给各用氧/用电工序。
  // 电耗由工辅单元参数 power 计入（compute.js 对 route:'aux' 已统一核算），此处 powerPerUnit=0 避免重复计电。
  { type: 'oxy_supply', label: '供氧系统', kind: 'adjustable', unit: 'kNm³/h', setpoint: { min: 20, max: 1500, def: 600, unit: 'kNm³/h', label: '供氧量' }, powerPerUnit: 0, effType: 'none', measures: '供氧量', response: { bias: 0.02, noise: 0.01 }, desc: '全厂供氧系统（空分制氧机组）的可调设备，供氧量设定对应供氧系统工艺参数，经连线集中供给高炉富氧鼓风、转炉吹炼、铁水预处理喷吹与精炼等用氧工序，是富氧强化冶炼减排策略的作用对象。' },
  { type: 'power_supply', label: '供电系统', kind: 'adjustable', unit: 'MW', setpoint: { min: 1, max: 600, def: 200, unit: 'MW', label: '供电负荷' }, powerPerUnit: 0, effType: 'none', measures: '供电负荷', response: { bias: 0.01, noise: 0.005 }, desc: '全厂供电系统（总降/主变电站）的可调设备，汇集外购电、自发电（BFG/CDQ/余热）与绿电统一分配，供电负荷设定对应全厂范围二电耗，是提升绿电/自发电占比减排策略的作用对象。' },
]
export const DEVICE_MAP = Object.fromEntries(DEVICE_TEMPLATES.map((d) => [d.type, d]))
export const DEVICE_GROUPS = {
  metering: DEVICE_TEMPLATES.filter((d) => d.kind === 'metering'),
  adjustable: DEVICE_TEMPLATES.filter((d) => d.kind === 'adjustable'),
}

// ---------- 设定值(SP) → 测定值(PV) 响应模型 ----------
// 可调设备存在「设定值 / 测定值」两个值：设定值由操作/策略调节，经设备响应特性
// （稳态偏差 bias + 测量噪声 noise）产生测定值，二者有差异。
// 平台仿真计算一律以设定值为准（输入框中的数字即工况值）；测定值保留用于数据建模与
// 未来真实 SCADA 场景。推导采用确定性公式（同一设定值 → 同一测定值），保证可复现、可审计。
export function applySetpointResponse(setpoint, response) {
  const sp = Number(setpoint) || 0
  if (!response) return sp
  const bias = response.bias || 0          // 稳态偏差率（执行机构/仪表固有偏差）
  const noise = response.noise || 0        // 测量噪声幅度（确定性伪随机 ±noise）
  // 确定性伪随机：sin(设定值) 的小数部分，保证同一设定值恒得同一测定值
  const t = Math.sin(sp * 127.1 + 311.7)
  const jitter = (t - Math.floor(t)) * 2 - 1   // [-1, 1)
  return sp * (1 + bias) * (1 + jitter * noise)
}
// ---------- 设备 → 碳排 耦合注册表（统一、可审计、可标定） ----------
// 集中定义"调整设备如何确定影响碳排"：每个可调设备对某工序参数的影响，由一条
// 显式耦合函数 f(设定值, 基准参数) 决定。字段见下方条目注释。
export const DEVICE_COUPLE_REGISTRY = {
  blast_furnace: {
    blower: {
      target: 'wind_rate', effect: 'reduce', source: 'mechanism',
      basis: '鼓风量正比于鼓风机风量设定；风量↑→风口燃烧带活性↑、允许更高喷煤。附加可调项「鼓风湿度」：加湿/脱湿调节鼓风含湿量，湿度↑→水分分解吸热、理论燃烧温度↓、焦比↑',
      nominal: 5200, uncertainty: '±5%',
      derive: (s) => ({ wind_rate: Math.round(Number(s) / 5200 * 600) }), // 设备设定 m³/h（def 5200）↔ 风量 kNm³/h（def 600）
      // 附加可调项联动：鼓风湿度 → 高炉鼓风含湿（TFT 热制度输入，属性面板展示）
      multi: {
        humidity: {
          target: 'blast_humidity', unit: 'g/Nm³', source: 'mechanism', uncertainty: '±5%',
          formula: '鼓风湿度(g/Nm³) = 鼓风机湿度设定',
          basis: '鼓风含湿：鼓风机加湿/脱湿装置调节出口鼓风携带的水分（g/Nm³）；水分在风口分解（C+H₂O→CO+H₂）吸热，湿度↑→理论燃烧温度（TFT）↓、焦比↑（风口热补偿需求增加）；高炉 TFT 面板直接读取该值参与焓平衡计算',
          derive: (h) => ({ blast_humidity: Math.max(0, Math.min(30, Number(h) || 0)) }),
        },
      },
    },
    oxygen_lance: {
      target: 'oxygen_enrich', effect: 'reduce', source: 'mechanism',
      basis: '供氧强度正比于氧枪流量；富氧↑→允许更高喷煤、降低焦比',
      nominal: 4000, uncertainty: '±3%',
      derive: (s) => ({ oxygen_enrich: Math.min(14, Math.max(0, 14 * (Number(s) / 4000))) }),
    },
    hot_blast_stove: {
      target: 'hot_blast_temp', effect: 'reduce', source: 'mechanism',
      basis: '热风炉拱顶温度设定直接决定进风温度；风温↑→热效率↑、焦比↓',
      nominal: 1250, uncertainty: '±1%',
      derive: (s) => ({ hot_blast_temp: Number(s) }),
    },
    injector: {
      target: 'coal_inj/coke_rate', effect: 'reduce', source: 'empirical',
      basis: '喷吹煤粉(PCI)顶替焦炭，焦比下降≈喷煤增量×1.1（经验置换比 1.0–1.2）',
      nominal: 120, uncertainty: '±15%',
      derive: (s, base) => {
        const dCoal = Number(s) - 120
        const cokeSave = dCoal * 1.1
        return {
          coal_inj: Math.max(0, (base.coal_inj || 150) + dCoal),
          coke_rate: Math.max(300, (base.coke_rate || 470) - cokeSave),
        }
      },
    },
    oxy_supply: {
      target: 'oxygen_enrich', effect: 'reduce', source: 'mechanism',
      basis: '全厂供氧集中供给高炉富氧鼓风；供氧量↑→富氧率↑→风口理论燃烧温度↑、焦比↓、产量↑',
      nominal: 600, uncertainty: '±3%',
      derive: (s) => ({ oxygen_enrich: Math.min(14, Math.max(0, 14 * (Number(s) / 600))) }),
    },
    power_supply: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      basis: '全厂供电汇集外购电与自发电；绿电/自发电占比↑→鼓风/除尘等用电范围二排放↓',
      nominal: 200, uncertainty: '±6%',
      derive: (s, base) => ({ electricity: Math.max(1, (base.electricity || 30) * (Number(s) / 200)) }),
    },
  },
  sinter_plant: {
    vfd: fanElecCoupling('vfd', 40),
    id_fan: fanElecCoupling('id_fan', 4000),
    belt_conv: feedCoupling('belt_conv', 2, 0.05),
    feeder: feedCoupling('feeder', 200, 0.05),
  },
  pelletizing: {
    vfd: fanElecCoupling('vfd', 40),
    id_fan: fanElecCoupling('id_fan', 4000),
    belt_conv: feedCoupling('belt_conv', 2, 0.04),
    feeder: feedCoupling('feeder', 200, 0.04),
  },
  coke_oven: {
    vfd: fanElecCoupling('vfd', 40),
    blower: feedCoupling('blower', 5200, 0.03),
  },
  bof: {
    oxygen_lance: {
      target: 'scrap/hot_metal_in', effect: 'reduce', source: 'empirical',
      basis: '供氧↑→可氧化更多废钢→废钢比↑、铁水入炉↓（质量守恒），减少上游焦炉排放',
      nominal: 4000, uncertainty: '±10%',
      derive: (s, base) => {
        const dO2 = (Number(s) - 4000) / 4000
        const dMass = Math.max(0, 300 * dO2) // t/h 废钢增量（经验）
        return {
          scrap: Math.max(0, (base.scrap || 900) + dMass),
          hot_metal_in: Math.max(0, (base.hot_metal_in || 7400) - dMass),
        }
      },
    },
    vfd: fanElecCoupling('vfd', 40),
    oxy_supply: {
      target: 'scrap/hot_metal_in', effect: 'reduce', source: 'empirical',
      basis: '全厂供氧集中供给转炉吹氧；供氧量↑→可氧化更多废钢→废钢比↑、铁水入炉↓，减少上游焦炉/高炉排放',
      nominal: 600, uncertainty: '±10%',
      derive: (s, base) => {
        const dO2 = (Number(s) - 600) / 600
        const dMass = Math.max(0, 400 * dO2) // t/h 废钢增量（经验）
        return {
          scrap: Math.max(0, (base.scrap || 900) + dMass),
          hot_metal_in: Math.max(0, (base.hot_metal_in || 7400) - dMass),
        }
      },
    },
    power_supply: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      basis: '全厂供电汇集外购电与自发电；绿电/自发电占比↑→转炉除尘/水处理等辅助用电范围二排放↓',
      nominal: 200, uncertainty: '±6%',
      derive: (s, base) => ({ electricity: Math.max(1, (base.electricity || 30) * (Number(s) / 200)) }),
    },
  },
  hot_metal_pretreat: {
    oxygen_lance: {
      target: 'oxygen_enrich', effect: 'reduce', source: 'mechanism',
      basis: '铁水预处理(脱硫/脱磷)需喷吹工业氧强化反应；供氧强度↑→反应更充分、处理周期缩短（富氧增量为相对空气 21% 的提升量）',
      nominal: 4000, uncertainty: '±10%',
      derive: (s) => ({ oxygen_enrich: Math.min(14, Math.max(0, 14 * (Number(s) / 4000))) }),
    },
    oxy_supply: {
      target: 'oxygen_enrich', effect: 'reduce', source: 'mechanism',
      basis: '全厂供氧集中供给铁水预处理喷吹氧气；供氧量↑→脱硫/脱磷速率↑、扒渣周期缩短（富氧增量为相对空气 21% 的提升量）',
      nominal: 600, uncertainty: '±8%',
      derive: (s) => ({ oxygen_enrich: Math.min(14, Math.max(0, 14 * (Number(s) / 600))) }),
    },
    power_supply: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      basis: '全厂供电汇集外购电与自发电；绿电/自发电占比↑→预处理扒渣/搅拌电耗范围二排放↓',
      nominal: 200, uncertainty: '±6%',
      derive: (s, base) => ({ electricity: Math.max(1, (base.electricity || 4) * (Number(s) / 200)) }),
    },
  },
  eaf: {
    electrode_reg: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      basis: '电弧功率设定影响电耗；优化调节降低吨钢电耗（约线性）',
      nominal: 70, uncertainty: '±8%',
      derive: (s, base) => ({ electricity: Math.max(60, (base.electricity || 360) * (Number(s) / 70)) }),
    },
    vfd: fanElecCoupling('vfd', 40),
    blower: fanElecCoupling('blower', 5200),
    oxy_supply: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      basis: '全厂供氧供给电炉炉门/炉盖吹氧助熔与脱碳；供氧量↑→脱碳与升温更快、电耗↓',
      nominal: 600, uncertainty: '±8%',
      derive: (s, base) => ({ electricity: Math.max(120, (base.electricity || 360) * (1 - 0.10 * (Number(s) / 600 - 1))) }),
    },
    power_supply: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      basis: '全厂供电汇集外购电与自发电；绿电/自发电占比↑→电炉冶炼电耗范围二排放↓',
      nominal: 200, uncertainty: '±6%',
      derive: (s, base) => ({ electricity: Math.max(60, (base.electricity || 360) * (Number(s) / 200)) }),
    },
  },
  ladle_furnace: {
    electrode_reg: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      nominal: 70, uncertainty: '±8%',
      basis: '电极调节优化降低精炼电耗（约线性）',
      derive: (s, base) => ({ electricity: Math.max(1, (base.electricity || 200) * (Number(s) / 70)) }),
    },
    vfd: fanElecCoupling('vfd', 40),
    power_supply: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      basis: '全厂供电汇集外购电与自发电；绿电/自发电占比↑→精炼电耗范围二排放↓',
      nominal: 200, uncertainty: '±6%',
      derive: (s, base) => ({ electricity: Math.max(1, (base.electricity || 200) * (Number(s) / 200)) }),
    },
  },
  rh_vacuum: {
    vfd: fanElecCoupling('vfd', 40),
    cool_pump: fanElecCoupling('cool_pump', 300),
    power_supply: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      basis: '全厂供电汇集外购电与自发电；绿电/自发电占比↑→真空精炼电耗范围二排放↓',
      nominal: 200, uncertainty: '±6%',
      derive: (s, base) => ({ electricity: Math.max(1, (base.electricity || 5) * (Number(s) / 200)) }),
    },
  },
  caster: {
    vfd: fanElecCoupling('vfd', 40),
    cool_pump: fanElecCoupling('cool_pump', 300),
    belt_conv: feedCoupling('belt_conv', 2, 0.02),
    power_supply: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      basis: '全厂供电汇集外购电与自发电；绿电/自发电占比↑→连铸电耗范围二排放↓',
      nominal: 200, uncertainty: '±6%',
      derive: (s, base) => ({ electricity: Math.max(1, (base.electricity || 15) * (Number(s) / 200)) }),
    },
  },
  rolling_mill: {
    burner: {
      target: 'ng_rate', effect: 'reduce', source: 'empirical',
      basis: '优化空燃比→天然气消耗降低（约 4%/单位优化）',
      nominal: 1.0, uncertainty: '±6%',
      derive: (s, base) => {
        const f = Number(s)
        return { ng_rate: Math.max(0, (base.ng_rate || 32) * (1 - 0.04 * (f - 1))) }
      },
    },
    vfd: fanElecCoupling('vfd', 40),
    cool_pump: fanElecCoupling('cool_pump', 300),
    power_supply: {
      target: 'electricity', effect: 'reduce', source: 'empirical',
      basis: '全厂供电汇集外购电与自发电；绿电/自发电占比↑→轧制电耗范围二排放↓',
      nominal: 200, uncertainty: '±6%',
      derive: (s, base) => ({ electricity: Math.max(1, (base.electricity || 80) * (Number(s) / 200)) }),
    },
  },
  waste_heat: {
    waste_heat_boiler: {
      target: 'heat_in', effect: 'reduce', source: 'mechanism',
      basis: '余热锅炉产汽量正比于回收余热量→自发电↑、外购电↓',
      nominal: 120, uncertainty: '±5%',
      derive: (s, base) => ({ heat_in: Math.max(50, (base.heat_in || 800) * (Number(s) / 120)) }),
    },
  },
  // gas_power: BFG 回收量由上游(高炉)决定，无本地可调设备驱动
  // ccs: 捕集率为策略参数，无设备驱动
}

// 运行期可注入本厂标定系数（数据驱动），覆盖默认耦合。
// 例：COUPLING_OVERRIDES['sinter_plant.vfd'] = { k: 3.0, source: 'data' }
export const COUPLING_OVERRIDES = {}

// 取某(工序,设备)的耦合定义，优先用运行期标定覆盖
export function getCoupling(processType, deviceType) {
  const reg = DEVICE_COUPLE_REGISTRY[processType]
  const base = reg && reg[deviceType]
  if (!base) return null
  const ov = COUPLING_OVERRIDES[`${processType}.${deviceType}`]
  if (!ov) return base
  const merged = { ...base, ...ov }
  // 数据驱动标定：用回归系数 (a,b,nominal) 重建 derive，避免函数无法序列化
  if (ov.a != null) merged.derive = makeCalibratedDerive(ov)
  return merged
}

// 由标定系数构造 derive（纯数据、可序列化）。
// 采用「相对比例」形式：名义设定点下推算值 = 基准参数（无跳变）；偏离按回归斜率缩放。
// secondary: 多参数耦合的次级联动，如 injector→coke_rate、bof→hot_metal_in。
export function makeCalibratedDerive(cal) {
  const target = cal.target
  const nominal = cal.nominal
  const secondary = cal.secondary || null
  return (s, base) => {
    const fittedAtNominal = cal.a + cal.b * nominal
    const fitted = cal.a + cal.b * Number(s)
    const bp = base && base[target] != null ? base[target] : fittedAtNominal
    const denom = Math.max(1e-9, fittedAtNominal)
    const val = Math.max(0, bp * (fitted / denom)) // 比例缩放：名义点=基准值，避免跳变
    const out = { [target]: val }
    if (secondary) {
      const bp2 = base && base[secondary.key] != null ? base[secondary.key] : 0
      out[secondary.key] = Math.max(0, bp2 + secondary.ratio * (val - bp))
    }
    return out
  }
}

const CALIB_LS_KEY = 'carbon_coupling_calibrations_v1'

// 应用一次数据标定（写入运行期覆盖 + 持久化到 localStorage）
export function applyCalibration(processType, deviceType, cal) {
  COUPLING_OVERRIDES[`${processType}.${deviceType}`] = { ...cal, source: 'data' }
  _persistCalibrations()
}

// 清除某耦合的标定（恢复默认经验/机理耦合）
export function clearCalibration(processType, deviceType) {
  delete COUPLING_OVERRIDES[`${processType}.${deviceType}`]
  _persistCalibrations()
}

function _persistCalibrations() {
  try {
    const data = {}
    for (const k of Object.keys(COUPLING_OVERRIDES)) {
      const v = COUPLING_OVERRIDES[k]
      if (v && v.a != null) data[k] = v
    }
    localStorage.setItem(CALIB_LS_KEY, JSON.stringify(data))
  } catch (e) { /* localStorage 不可用时静默忽略 */ }
}

// 启动时从 localStorage 恢复标定
export function loadCalibrations() {
  try {
    const raw = localStorage.getItem(CALIB_LS_KEY)
    if (!raw) return
    const data = JSON.parse(raw)
    for (const k of Object.keys(data)) COUPLING_OVERRIDES[k] = data[k]
  } catch (e) { /* 解析失败静默忽略 */ }
}

// 由一组设备(类型+设定值)推导某工序应注入的工序参数覆盖对象。
// devices: [{ type, setpoint, extraSetpoints }]，base = 该工序当前参数（相对推导，避免跳变）。
// 仅在设备类型属于该工序注册表且设定值有效时输出。
// extraSetpoints：设备附加可调项（如鼓风机「鼓风湿度」），走耦合注册表 multi 配置联动推导（如高炉鼓风含湿）。
export function deriveProcessOpParams(processType, devices, base = {}) {
  const out = {}
  const reg = DEVICE_COUPLE_REGISTRY[processType]
  if (!reg || !Array.isArray(devices)) return out
  for (const d of devices) {
    const cfg = d && getCoupling(processType, d.type)
    if (!cfg) continue
    // 仿真计算以设定值为准：设定值即操作工况（输入框中的数字），不经设备响应特性折算
    const eff = d.setpoint != null && !isNaN(Number(d.setpoint)) ? Number(d.setpoint) : null
    if (eff != null) {
      const overrides = cfg.derive(eff, base)
      if (overrides && typeof overrides === 'object') Object.assign(out, overrides)
    }
    // 附加可调项：如鼓风机鼓风湿度 → 高炉鼓风含湿（multi 配置）；基准主设定值同样以设定值为准
    if (cfg.multi && d.extraSetpoints && typeof d.extraSetpoints === 'object') {
      for (const [key, val] of Object.entries(d.extraSetpoints)) {
        const m = cfg.multi[key]
        if (!m || val == null || isNaN(Number(val))) continue
        const ov = m.derive(Number(val), eff, base)
        if (ov && typeof ov === 'object') Object.assign(out, ov)
      }
    }
  }
  return out
}

// 风机/泵类：功率 ∝ 转速³（亲和定律，机理确定），电耗随之变化
function fanElecCoupling(deviceType, nominal) {
  return {
    target: 'electricity', effect: 'reduce', source: 'mechanism',
    basis: '风机/泵功率 ∝ 转速³（亲和定律）：变频调速节电，超调则增耗',
    nominal, uncertainty: '±3%',
    derive: (s, base) => {
      const r = Math.pow(Number(s) / nominal, 3)
      const baseElec = base.electricity
      if (baseElec == null) return {}
      return { electricity: Math.max(0, baseElec * r) }
    },
  }
}

// 给料/布料设备：优化给料均匀性→燃料比下降（经验）
function feedCoupling(deviceType, nominal, k) {
  return {
    target: 'fuel_rate', effect: 'reduce', source: 'empirical',
    basis: '给料/布料均匀性改善→透气性/热效率↑→固体燃料比下降',
    nominal, uncertainty: '±10%',
    derive: (s, base) => {
      const f = Number(s) / nominal
      const baseFuel = base.fuel_rate
      if (baseFuel == null) return {}
      return { fuel_rate: Math.max(baseFuel * 0.85, baseFuel * (1 - k * (f - 1))) }
    },
  }
}

// 各工艺典型「可调设备」清单（按工艺类型给出默认配置的可调设备）。
// 这些设备是策略真正作用的可控装备（风量/带速/空燃比/电功率等），
// 与「计量设备（只读监测）」区分；进入运行时随工序一起挂载到 3D 标签与左侧设备树。
// 注：鼓风机/热风炉/引风机/喷吹系统/皮带机/给料机/电极调节器/助燃风机/冷却水泵/空分制氧等
// 「自身不产碳、只耗能并影响被服务工艺」的设备，已抽离为「工辅」独立节点
// （route:'aux'，见 PROCESS_TEMPLATES 中对应条目），不再作为挂靠在工艺下的可调设备。
// 下方仅保留尚未独立成工艺的可调设备（变频/氧枪/燃烧器/除尘风机等），保持向后兼容。
// 注意：已独立为「工辅」(route:'aux') 的设备（鼓风机/热风炉/引风机/喷吹系统…）
// 不再写在此表，也不静态并入 PROCESS_ADJUSTABLE。工辅实例与所服务工序实例的绑定
// 由编排画布中的「物料连线」决定（见 stores/sim.js linkedAuxTypesFor）：只有实际连线
// 供给某工序的工辅，才作为该工序的可调设备出现——未连线即视为未绑定、不出现在清单中。
const PROCESS_ADJUSTABLE_BASE = {
  sinter_plant: ['vfd'],
  pelletizing: ['vfd'],
  coke_oven: ['dedust_fan', 'vfd'],
  blast_furnace: ['dedust_fan', 'vfd'],
  hot_metal_pretreat: ['oxygen_lance', 'vfd'],
  bof: ['oxygen_lance', 'dedust_fan', 'vfd'],
  ladle_furnace: ['vfd'],
  rh_vacuum: ['vfd', 'pump'],
  caster: ['vfd', 'pump'],
  rolling_mill: ['burner', 'vfd'],
  eaf: ['dedust_fan', 'vfd'],
  hydrogen_bf: ['dedust_fan', 'vfd'],
  h2_dri: ['burner', 'vfd'],
  dri_midrex: ['burner', 'vfd'],
  smelting_reduction: ['vfd'],
  biochar_injection: ['vfd'],
  reheating_furnace: ['burner', 'vfd'],
}

// 工辅类型集合（独立耗能、影响被服务工艺的工序）
export const AUX_TYPES = PROCESS_TEMPLATES.filter((t) => t.route === 'aux').map((t) => t.type)

// 每个工艺的可调设备 = 基础清单（仅变频/除尘风机等非工辅设备）。
// 工辅不再按工艺类型静态并入：工辅实例与工序实例的绑定关系由编排连线动态推导，
// 见 stores/sim.js 的 linkedAuxTypesFor（连线存在才作为该工序的可调设备）。
// 工辅类型自身仍保留为可调设备（以其自身作为可调设备，工辅工艺下可见）。
export const PROCESS_ADJUSTABLE = (() => {
  const m = {}
  for (const t of PROCESS_TEMPLATES) {
    const set = new Set(PROCESS_ADJUSTABLE_BASE[t.type] || [])
    if (t.route === 'aux') set.add(t.type) // 工辅自身可调
    m[t.type] = [...set]
  }
  return Object.freeze(m)
})()

// 同类型「可调设备」在不同工艺下视为不同设备，名称带「工艺前缀」以区分。
// 例：烧结机·引风机（sinter_plant::id_fan）与 球团·引风机（pelletizing::id_fan）。
// 设备 id 本身已是 工序::类型 唯一，这里仅统一展示名，避免在资源树/属性面板重名混淆。
export function adjDeviceName(processType, deviceType) {
  const p = PROCESS_MAP[processType]
  const d = DEVICE_MAP[deviceType]
  if (!p || !d) return (d && d.label) || deviceType
  return `${p.label}·${d.label}`
}

let _idc = 0
export function uid(p) { return `${p}_${Date.now().toString(36)}${(_idc++).toString(36)}` }

// 由模板生成工艺节点（含默认端口与配比）。
// spec 为可选设备规格对象（{key, defaults, ranges, ...}，来自后端规格库）；
// 指定后节点携带 spec key，且默认参数以规格档位的 defaults 为准。
export function makeProcessNode(type, x, y, name, spec) {
  const t = PROCESS_MAP[type]
  if (!t) return null
  const params = Object.fromEntries((t.params || []).map((p) => [p.key, p.def]))
  if (spec && spec.defaults) Object.assign(params, spec.defaults)
  return {
    id: uid('n'),
    kind: 'process',
    type,
    // 默认以类型名命名；同类型多实例的序号由调用方（buildScheme/addFlowNode）按「第 2 台起编号」规则追加
    name: name || t.label,
    x, y,
    count: 1,   // 台数：>1 时自动形成小组（同设备多台）
    spec: spec && spec.key ? spec.key : '',
    params,
    recipe: (t.inputs || []).map((m) => ({ material: m, ratio: 1 })),
    ports: {
      in: (t.inputs || []).map((m) => ({ id: uid('in'), material: m })),
      out: (t.outputs || []).map((m) => ({ id: uid('out'), material: m })),
    },
    deviceBindings: [],
  }
}

export function makeDeviceNode(type, x, y, name) {
  const d = DEVICE_MAP[type]
  if (!d) return null
  const node = {
    id: uid('d'),
    kind: 'device',
    type,
    name: name || d.label,
    x, y,
    count: 1,   // 台数：>1 时自动形成小组（同设备多台）
    metering: d.kind === 'metering',
    setpoint: d.kind === 'adjustable' && d.setpoint ? d.setpoint.def : null,
    boundTo: null,
  }
  return node
}

export function makeMaterialNode(materialId, x, y) {
  const m = MATERIAL_MAP[materialId]
  if (!m) return null
  return {
    id: uid('m'),
    kind: 'material',
    type: materialId,
    name: m.name,
    x, y,
    ports: { in: [], out: [{ id: uid('out'), material: materialId }] },
  }
}

// 存量方案迁移：将旧版「挂在工艺下的可调设备(kind:'device')」转为独立的「工辅」节点。
// 映射 deviceType -> { auxType, srcKey, scale }：旧设备设定值(相对倍率)经 scale 折算为
// 独立工辅的运行参数(绝对值)，并以物料连线耦合到被服务工艺（覆盖其对应参数）。
// 这样旧方案无需手动改造即可获得"独立工艺 + 物料连线驱动"的新能力，结果逻辑一致。
const LEGACY_DEVICE_TO_AUX = {
  blower: { auxType: 'blower', srcKey: 'air_rate', scale: 600 },
  hot_blast_stove: { auxType: 'hot_blast_stove', srcKey: 'blast_temp', scale: 1250 },
  id_fan: { auxType: 'id_fan', srcKey: 'draught', scale: 3.5 },
  injector: { auxType: 'injector', srcKey: 'inj_rate', scale: 120 },
  combustion_blower: { auxType: 'combustion_blower', srcKey: 'air_rate', scale: 150 },
  electrode_reg: { auxType: 'electrode_reg', srcKey: 'power', scale: 90 },
  belt_conv: { auxType: 'belt_conv', srcKey: 'throughput', scale: 1500 },
  feeder: { auxType: 'feeder', srcKey: 'rate', scale: 400 },
  cool_pump: { auxType: 'cool_pump', srcKey: 'flow', scale: 2000 },
  aux_boiler: { auxType: 'aux_boiler', srcKey: 'steam_rate', scale: 80 },
  oxy_plant: { auxType: 'oxy_plant', srcKey: 'oxygen_rate', scale: 260 },
  drive_supply: { auxType: 'drive_supply', srcKey: 'power', scale: 60 },
}
export function migrateLegacyDevices(scheme) {
  if (!scheme || !scheme.nodes) return scheme
  const devices = (scheme.devices || []).filter((d) => d && d.kind === 'device' && !d.metering)
  if (!devices.length) return scheme
  const nodeById = Object.fromEntries(scheme.nodes.map((n) => [n.id, n]))
  const newNodes = []
  const newConns = []
  const removeIds = new Set()
  for (const d of devices) {
    const map = LEGACY_DEVICE_TO_AUX[d.type]
    if (!map) continue
    const auxT = PROCESS_MAP[map.auxType]
    if (!auxT) continue
    const target = nodeById[d.boundTo]
    if (!target || !PROCESS_MAP[target.type]) continue
    // 创建独立工辅节点
    const aux = makeProcessNode(map.auxType, d.x + 60, d.y - 40)
    if (!aux) continue
    // 旧设定值(相对倍率 0-2) -> 绝对值写入 src 参数
    const sp = (typeof d.setpoint === 'number') ? d.setpoint : 1
    aux.params = { ...aux.params, [map.srcKey]: Math.round(sp * map.scale) }
    // 附加可调项（鼓风湿度）原样带入；旧版喷氧量已移交供氧系统接管，不再随鼓风机迁移
    if (d.extraSetpoints && typeof d.extraSetpoints === 'object') {
      Object.assign(aux.params, d.extraSetpoints)
      if (aux.params.o2_inj != null) delete aux.params.o2_inj
    }
    newNodes.push(aux)
    removeIds.add(d.id)
    // 建驱动连线：工辅输出物料 -> 被绑定工艺输入端口
    const driveMat = Object.keys(auxT.drives || {})[0]
    if (driveMat && (target.ports.in || []).some((p) => p.material === driveMat)) {
      const outPort = aux.ports.out.find((p) => p.material === driveMat)
      const inPort = target.ports.in.find((p) => p.material === driveMat)
      if (outPort && inPort) {
        newConns.push({ id: uid('c'), from: aux.id, fromPort: outPort.id, to: target.id, toPort: inPort.id, material: driveMat, feedback: false })
      }
    }
  }
  if (!newNodes.length) return scheme
  scheme.nodes = scheme.nodes.filter((n) => !removeIds.has(n.id)).concat(newNodes)
  scheme.connections = (scheme.connections || []).concat(newConns)
  scheme.devices = (scheme.devices || []).filter((d) => !removeIds.has(d.id))
  return scheme
}

// 构建预建示例方案（长流程 / 短流程），自动按物料匹配连线，并生成节能反馈弧。
// 关键：示例方案自带「工辅」实例，并通过物料连线驱动被服务工艺参数，
// 保证默认流程中数据真正串联（如 鼓风机→热风炉供风、热风炉→高炉风温、驱动电源→电炉功率）。
// 自带工辅清单（按流程）：[type, 被服务工艺 type, 被服务实例序号(0起)]，连线按 drives 物料自动建立。
const SCHEME_AUX = {
  long: [
    // 一台高炉配三台热风炉（轮流换炉蓄热），每台热风炉又各配一台鼓风机供风：
    // 鼓风机 → 热风炉（冷风供燃烧），热风炉 → 高炉（热风）。多实例按序号服务各自对象。
    ['hot_blast_stove', 'blast_furnace', 0],
    ['hot_blast_stove', 'blast_furnace', 0],
    ['hot_blast_stove', 'blast_furnace', 0],
    ['blower', 'hot_blast_stove', 0],
    ['blower', 'hot_blast_stove', 1],
    ['blower', 'hot_blast_stove', 2],
    // 引风机按工序独立配备：烧结主抽风机、球团焙烧引风机各一台。
    // 烧结机与球团是独立产线，各自拥有自己的引风机，不能共用同一台。
    ['id_fan', 'sinter_plant', 0],
    ['id_fan', 'pelletizing', 0],
    ['injector', 'blast_furnace', 0],
    // 全厂供氧系统：向铁水预处理喷吹、转炉吹氧集中供氧，并集中供给高炉富氧鼓风（富氧率由供氧量驱动）
    ['oxy_supply', 'hot_metal_pretreat', 0],
    ['oxy_supply', 'bof', 0],
    ['oxy_supply', 'blower', 0],
    ['oxy_supply', 'blower', 1],
    ['oxy_supply', 'blower', 2],
    // 全厂供电系统：汇集外购电与自发电，向主要用电工序供给并承载绿电抵扣
    ['power_supply', 'blast_furnace', 0],
    ['power_supply', 'bof', 0],
    ['power_supply', 'ladle_furnace', 0],
    ['power_supply', 'rh_vacuum', 0],
    ['power_supply', 'caster', 0],
    ['power_supply', 'rolling_mill', 0],
  ],
  short: [
    // 短流程以废钢 + 直接还原铁(DRI)为双原料，细化上游 DRI 竖炉(Midrex)供热/供气/供电
    ['dri_midrex', 'eaf', 0],
    ['oxy_supply', 'eaf', 0],
    ['power_supply', 'eaf', 0],
    ['power_supply', 'dri_midrex', 0],
    ['electrode_reg', 'eaf', 0],
    ['oxy_supply', 'ladle_furnace', 0],
    ['power_supply', 'ladle_furnace', 0],
    ['oxy_supply', 'rh_vacuum', 0],
    ['power_supply', 'rh_vacuum', 0],
    ['power_supply', 'caster', 0],
    ['power_supply', 'rolling_mill', 0],
  ],
}
export function buildScheme(route) {
  const isShort = route === 'short'
  const seq = isShort
    ? ['eaf', 'ladle_furnace', 'rh_vacuum', 'caster', 'rolling_mill']
    : ['sinter_plant', 'pelletizing', 'coke_oven', 'blast_furnace', 'hot_metal_pretreat', 'bof', 'ladle_furnace', 'rh_vacuum', 'caster', 'rolling_mill']
  const nodes = []
  // 主工艺（树干）节点：先创建，位置由末尾 treeLayoutNodes 统一按「工艺树」排布
  // （主工艺沿 X 从左到右为树干、Y 居中；工辅为其分支分布在主干两侧、同一水平线）
  for (const type of seq) {
    const n = makeProcessNode(type, 0, 0)
    if (n) nodes.push(n)
  }
  const connections = []
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]))
  const byType = {}
  for (const n of nodes) (byType[n.type] = byType[n.type] || []).push(n)

  // 正向连接：每个节点的每个 in 端口，连到“之前”最后一个拥有匹配 out 物料的节点
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i]
    for (const p of n.ports.in) {
      for (let j = i - 1; j >= 0; j--) {
        const s = nodes[j]
        const sp = s.ports.out.find((o) => o.material === p.material)
        if (sp) {
          connections.push({ id: uid('c'), from: s.id, fromPort: sp.id, to: n.id, toPort: p.id, material: p.material, feedback: false })
          break
        }
      }
    }
  }
  // 工辅实例：先创建，位置由末尾 treeLayoutNodes 统一按「工艺树」排布
  // （如 鼓风机→热风炉→高炉：高炉为树干居中、热风炉在其左侧、鼓风机在热风炉左侧）。
  // spec = [type, 被服务工艺 type, 被服务实例序号(0起)]
  const auxSpec = SCHEME_AUX[isShort ? 'short' : 'long'] || []
  const auxCount = {}
  for (const spec of auxSpec) {
    const auxType = spec[0]
    const serveType = spec[1]
    const serveIndex = spec[2] || 0
    const t = PROCESS_MAP[auxType]
    const serve = byType[serveType] && byType[serveType][serveIndex]
    if (!t || !serve) continue
    auxCount[auxType] = (auxCount[auxType] || 0) + 1
    // 同类型多实例（如三台热风炉、三台鼓风机）：单台直接使用类型名，从第 2 台起按序号命名，便于区分各自服务对象
    const aux = makeProcessNode(auxType, 0, 0, auxCount[auxType] === 1 ? undefined : `${t.label}${auxCount[auxType]}`)
    if (!aux) continue
    nodes.push(aux)
    byType[auxType] = (byType[auxType] || []).concat(aux)
    // 建驱动连线：aux 输出物料 -> 被服务工艺对应输入端口（drives 中声明的物料）
    for (const mat of Object.keys(t.drives || {})) {
      const outPort = aux.ports.out.find((o) => o.material === mat)
      const inPort = serve.ports.in.find((p) => p.material === mat)
      if (outPort && inPort) {
        connections.push({ id: uid('c'), from: aux.id, fromPort: outPort.id, to: serve.id, toPort: inPort.id, material: mat, feedback: false })
      }
    }
  }
  // 小组（子编排）只用于「同一种设备重复多台」的场景：同类型工辅（如三台热风炉、三台鼓风机）
  // 自动聚为一个小组，对外输入/输出沿用该设备的物料模板；不同类型设备平铺展示，不再混编。
  const groups = []
  {
    const byAuxType = {}
    for (const n of nodes) {
      const t = PROCESS_MAP[n.type]
      if (!t || t.route !== 'aux') continue
      ;(byAuxType[n.type] = byAuxType[n.type] || []).push(n)
    }
    for (const [type, arr] of Object.entries(byAuxType)) {
      if (arr.length < 2) continue
      const gid = uid('g')
      const t = PROCESS_MAP[type]
      for (const n of arr) {
        n.groupId = gid
        n.count = arr.length   // 同类型多台：组内每台都带台数标记
      }
      // 组锚点取成员包围盒左上角，便于空组/无成员时也有稳定落位
      const minX = Math.min(...arr.map((n) => n.x))
      const minY = Math.min(...arr.map((n) => n.y))
      groups.push({
        id: gid,
        name: t.label,   // 台数以卡片上的数量徽章显示，名称不再重复拼接 ×N
        x: minX - 30,
        y: minY - 50,
        members: arr.map((n) => n.id),
        inputs: (t.inputs || []).map((m) => ({ material: m })),
        outputs: (t.outputs || []).map((m) => ({ material: m })),
      })
    }
  }
  // 反馈连接：每个 in 端口，若“之后”有节点拥有匹配 out 物料，则连为反馈弧（节能回供）。
  // 已由正向/驱动连线供料的端口不再补反馈弧，避免同一物料被重复供给
  // （如引风机 draft 只供其绑定的工序，不会同时拉给烧结机与球团）。
  // 工辅不参与回供：其输出介质是驱动源（如鼓风机 blast_air 只供其服务的热风炉），
  // 不作为反馈源，避免出现 鼓风机→高炉 之类的跨服务错误回供。
  for (let i = 0; i < nodes.length; i++) {
    const n = nodes[i]
    for (const p of n.ports.in) {
      const fed = connections.some((c) => c.to === n.id && c.toPort === p.id)
      if (fed) continue
      for (let j = nodes.length - 1; j > i; j--) {
        const s = nodes[j]
        const st = PROCESS_MAP[s.type]
        if (!st || st.route === 'aux') continue
        const sp = s.ports.out.find((o) => o.material === p.material)
        if (sp) {
          connections.push({ id: uid('c'), from: s.id, fromPort: sp.id, to: n.id, toPort: p.id, material: p.material, feedback: true })
          break
        }
      }
    }
  }
  // 工艺树排布（工艺为树干、工辅为分枝的「树状结构」）：主工艺沿 X 从左到右、Y 居中（画布中线），
  // 工辅经物料连线成为树干向「垂直方向（上下）两侧」分叉的树枝——一级分支（热风炉）在高炉上方、
  // 二级分支（鼓风机）再向上一级展开；同一父节点的多个分支沿 X 水平并排、沿 Y 上下分层，
  // 形成树干在正中间水平线、枝丫向上下两侧张开的树状形态。
  treeLayoutNodes(nodes, connections)
  return { nodes, connections, devices: [], groups, activeGroupId: null }
}

// 编排画布自动布局（横向流式网格）：
// 主工艺按拓扑序横向排列，每行 3-4 个（按画布宽度自动取 4 或 3，避免单行过长）；
// 每个主工艺的整棵工辅子树（如 热风炉→鼓风机、喷吹）排在其正下方，
// 横向并排、超出每行容量自动折行；行高按工辅行数精确计算，保证任意卡片互不重叠。
// 无连线时以类型兜底（TYPE_TARGET）、再以最近主工艺兜底。就地修改 nodes 的 x/y。
export function treeLayoutNodes(nodes, connections, opts = {}) {
  if (!Array.isArray(nodes) || !nodes.length) return
  const byId = {}
  for (const n of nodes) byId[n.id] = n
  const tplOf = (n) => (n ? PROCESS_MAP[n.type] : null)
  const isMainN = (n) => { const t = tplOf(n); return !!t && t.route !== 'aux' && t.route !== 'util' }
  const isAuxN = (n) => { const t = tplOf(n); return !!t && t.route === 'aux' }
  // 类型兜底：工辅默认服务的主工艺（无连线时使用）
  const TYPE_TARGET = {
    blower: 'blast_furnace', hot_blast_stove: 'blast_furnace', injector: 'blast_furnace',
    combustion_blower: 'blast_furnace', id_fan: 'sinter_plant',
    drive_supply: 'bof', electrode_reg: 'eaf',
    belt_conv: 'sinter_plant', feeder: 'sinter_plant', cool_pump: 'caster',
    aux_boiler: 'reheating_furnace', oxy_plant: 'bof',
  }
  const mains = nodes.filter(isMainN)
  if (!mains.length) return
  const mainIds = new Set(mains.map((n) => n.id))
  const auxSet = new Set(nodes.filter(isAuxN).map((n) => n.id))

  // 1) 主干拓扑排序：按「正向物料连线」（排除反馈弧）从左到右，形成工艺树干
  const indeg = new Map(), outg = new Map()
  for (const n of mains) { indeg.set(n.id, 0); outg.set(n.id, []) }
  for (const c of connections || []) {
    if (c.feedback) continue
    const f = byId[c.from], t = byId[c.to]
    if (!f || !t || !mainIds.has(f.id) || !mainIds.has(t.id)) continue
    outg.get(f.id).push(t.id)
    indeg.set(t.id, indeg.get(t.id) + 1)
  }
  const order = []
  const q0 = mains.filter((n) => !indeg.get(n.id))
  while (q0.length) {
    const n = q0.shift()
    order.push(n.id)
    for (const d of outg.get(n.id)) {
      indeg.set(d, indeg.get(d) - 1)
      if (indeg.get(d) === 0) q0.push(byId[d])
    }
  }
  for (const n of mains) if (!order.includes(n.id)) order.push(n.id)

  // 2) 工艺树归属：工辅 -> 父节点（主工艺或另一工辅），连线投票 + 主输出物料优先
  //    （鼓风机输出 blast_air 供热风炉 → 鼓风机挂在热风炉下，而非直接挂高炉）
  const parentOf = new Map()
  const childrenOf = new Map()
  for (const n of nodes.filter(isAuxN)) {
    const want = tplOf(n) && tplOf(n).mainOut
    let target = null, best = 0
    const votes = new Map()
    for (const c of connections || []) {
      if (c.feedback) continue
      const f = byId[c.from], t = byId[c.to]
      if (!f || !t) continue
      const fromMe = f.id === n.id, toMe = t.id === n.id
      if (!fromMe && !toMe) continue
      const other = fromMe ? t : f
      if (other.id === n.id || !(mainIds.has(other.id) || auxSet.has(other.id))) continue
      const w = want && c.material === want ? 10 : 1
      votes.set(other.id, (votes.get(other.id) || 0) + w)
    }
    for (const [id, c] of votes) if (c > best) { best = c; target = byId[id] }
    if (!target) {
      const wt = TYPE_TARGET[n.type]
      if (wt) target = mains.find((m) => m.type === wt) || null
    }
    if (!target) {
      let near = null, nd = Infinity
      for (const m of mains) {
        const d = Math.abs((m.x || 0) - (n.x || 0))
        if (d < nd) { nd = d; near = m }
      }
      target = near
    }
    if (!target) continue
    parentOf.set(n.id, target.id)
    if (!childrenOf.has(target.id)) childrenOf.set(target.id, [])
    childrenOf.get(target.id).push(n)
  }

  // 3) 一级子树归属：每个主工艺的直接工辅子树根（保持挂载顺序，如 热风炉→鼓风机）
  const subRootsOf = new Map()    // mainId -> [一级子树根 id]
  for (const m of mains) {
    subRootsOf.set(m.id, childrenOf.get(m.id) || [])
  }

  // 4) 布局（横向流式网格）：主工艺按拓扑序从左到右、每行 PER_ROW 个
  //    （画布足够宽时每行 4 个、较窄时 3 个，即「一行 3-4 个」）；
  //    每个主工艺下方排它的整棵工辅子树（BFS 展平、保持挂载顺序），横向并排、超出每行容量自动折行。
  //    行高 = 主工艺占位高 + 该行工辅最多行数 × 工辅行高，精确计算保证任意卡片互不重叠；
  //    整张图在画布内水平、垂直居中。
  const XSTEP = 264            // 横向步距（卡片宽 NODE_NW=196 + 空隙，容纳端口与连线）
  const MAIN_H = 252           // 主工艺卡片占位高（含标题/端口/碳排估算条）
  const AUX_H = 196            // 工辅卡片占位高
  const MAIN_VGAP = 112        // 主工艺卡片与其下方工辅的垂直间距
  const AUX_VGAP = 48          // 工辅行之间 / 工辅行与下一行主工艺的间距
  const edge = 60              // 画布左右留白
  const cw = (opts && opts.canvasW) || 1600
  const PER_ROW = Math.min(4, Math.max(3, Math.floor((cw - 2 * edge) / XSTEP)))
  const mainRows = []
  for (let i = 0; i < order.length; i += PER_ROW) mainRows.push(order.slice(i, i + PER_ROW))
  // 每个主工艺的工辅整树（BFS 展平）
  const auxAllOf = new Map()
  for (const m of mains) {
    const ids = []
    for (const r of subRootsOf.get(m.id) || []) {
      const qq = [r.id]
      while (qq.length) {
        const id = qq.shift()
        ids.push(id)
        for (const c of childrenOf.get(id) || []) qq.push(c.id)
      }
    }
    auxAllOf.set(m.id, ids)
  }
  // 每行总高度：主工艺占位 + 下方工辅最多行数（行内超过 PER_ROW 个自动折行）
  const rowHs = mainRows.map((row) => {
    let maxLines = 0
    for (const id of row) {
      const cnt = (auxAllOf.get(id) || []).length
      if (cnt) maxLines = Math.max(maxLines, Math.ceil(cnt / PER_ROW))
    }
    return MAIN_H + (maxLines ? MAIN_VGAP + maxLines * AUX_H + (maxLines - 1) * AUX_VGAP : 0)
  })
  // 逐行落位：主工艺与下方工辅均从行首 X 对齐铺开；垂直方向依次下移
  let yTop = 100
  mainRows.forEach((row, ri) => {
    const rw = row.length * XSTEP - (XSTEP - NODE_NW)   // 本行实际占宽（最后一个卡片不补尾距）
    let x0 = -rw / 2
    for (const id of row) {
      const n = byId[id]
      n.x = Math.round(x0)
      n.y = Math.round(yTop)
      const auxs = auxAllOf.get(id) || []
      let ax = x0, ay = yTop + MAIN_H + MAIN_VGAP
      auxs.forEach((aid, k) => {
        if (k > 0 && k % PER_ROW === 0) { ax = x0; ay += AUX_H + AUX_VGAP }
        const a = byId[aid]
        a.x = Math.round(ax)
        a.y = Math.round(ay)
        ax += XSTEP
      })
      x0 += XSTEP
    }
    yTop += rowHs[ri] + AUX_VGAP
  })
}

// 参数键 → 中文业务标签（单一来源：PROCESS_TEMPLATES 的 params）。
// 用于「耦合透明度」等场景，把英文参数键（如 wind_rate）显示为业务标签（如 风量），
// 避免在 UI 直接暴露英文键名。复合耦合目标键（如 coal_inj/coke_rate）单独补充。
export const PARAM_LABELS = (() => {
  const m = {}
  for (const p of PROCESS_TEMPLATES) {
    for (const pr of (p.params || [])) m[pr.key] = pr.label
  }
  m['coal_inj/coke_rate'] = '喷煤比 / 焦比'
  m['electricity'] = m['electricity'] || '电耗'
  return m
})()

// 取参数中文标签，未知键返回原键（兜底，正常不应触发）
export function paramLabel(key) {
  return PARAM_LABELS[key] || key
}
