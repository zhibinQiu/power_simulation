// =============================================================
// 工艺静态元数据（业务数据层）
// -------------------------------------------------------------
// 本模块集中存放"工艺参数 / 设备类型 / 分类顺序 / 低碳技术"等
// 纯业务静态数据，与 UI 状态、交互逻辑（stores/sim.js）解耦。
// 组件与 store 均通过本模块取数，保证单一数据源、避免散落重复。
// =============================================================

// ---------- 高炉参数键分级 ----------
// 高炉：直接调参与操作杠杆两类参数键（共存，基准+增量关系）
//  - OP_PARAM_KEYS    操作杠杆（风量/热风温度/纯氧流量 o2_flow）：风温/抽力叠加 dCoke 偏移，
//                     富氧(纯氧流量)派生煤比(+15 kg/t per 1%富氧)再经喷煤置换联动焦比；
//                     富氧率 oxygen_enrich 为派生只读量（由风量+纯氧流量算出），不在此列
//  - DIRECT_PARAM_KEYS 直接工艺参数（焦比/喷煤比），作为推算基准
export const OP_PARAM_KEYS = new Set(['wind_rate', 'hot_blast_temp', 'o2_flow'])
export const DIRECT_PARAM_KEYS = new Set(['coke_rate', 'coal_inj'])

// ---------- 各工序可编辑参数（UI 元数据）：label / 单位 / 范围 / 展示模式 ----------
// key 与后端 carbon_engine 的工序参数保持一致；min/max/step 用于输入控件约束。
// 注意：此表是前端编辑器的"默认"范围；编排模式节点属性面板可自定义参数范围（随方案持久化），
// 节点自定义范围 > 设备规格档位 ranges > 此处默认范围。
// 展示模式 mode（缺省为 'direct'）：
//  - 'direct'  自身可调参数：在属性面板直接录值
//  - 'aux'     分支辅助工艺参数：面板只列出可调工艺实例，点击跳转到该工艺面板调整
//              （auxType：对应工辅工艺 type，如 blower 鼓风机 / hot_blast_stove 热风炉）
//  - 'derived' 指标参数：面板自动计算显示（只读），配置入口在 auxType 对应工艺
export const EDITABLE_PARAMS = {
  blast_furnace: [
    { key: 'hot_metal', label: '铁水产量', unit: 't/h', min: 200, max: 2000, step: 50, mode: 'direct' },
    { key: 'coke_rate', label: '焦比', unit: 'kg/t', min: 250, max: 550, step: 5, mode: 'direct' },
    { key: 'coal_inj', label: '喷煤比', unit: 'kg/t', min: 0, max: 250, step: 5, mode: 'direct' },
    { key: 'flux', label: '熔剂比', unit: 'kg/t', min: 0, max: 250, step: 5, mode: 'direct' },
    { key: 'wind_rate', label: '风量', unit: 'kNm³/h', min: 100, max: 900, step: 10, mode: 'aux', auxType: 'blower', auxNote: '由分支辅助工艺·鼓风机供风量驱动，点击实例跳转配置' },
    { key: 'hot_blast_temp', label: '热风温度', unit: '℃', min: 950, max: 1300, step: 10, mode: 'aux', auxType: 'hot_blast_stove', auxNote: '由分支辅助工艺·热风炉送风温度驱动，点击实例跳转配置' },
    { key: 'o2_flow', label: '纯氧流量', unit: 'Nm³/h', min: 0, max: 60000, step: 500, mode: 'direct', auxType: 'oxygen_lance', auxNote: '氧枪注入主风管的纯氧流量，与鼓风真实混合；富氧率由风量+纯氧流量派生（只读）' },
    { key: 'oxygen_enrich', label: '富氧率(派生)', unit: '%', min: 0, max: 14, step: 0.1, mode: 'derived', auxType: 'oxygen_lance', auxNote: '由纯氧流量与鼓风量/铁水产量物理混合算出（富氧增量，相对空气 21%），只读' },
    { key: 'blast_humidity', label: '鼓风湿度', unit: 'g/Nm³', min: 0, max: 30, step: 1, mode: 'derived', auxType: 'blower', auxNote: '由鼓风机·鼓风湿度设定驱动，水分在风口分解吸热，影响高炉热制度（TFT）' },
  ],
  hydrogen_bf: [
    { key: 'hot_metal', label: '铁水产量', unit: 't/h', min: 200, max: 2000, step: 50 },
    { key: 'h2_rate', label: '氢耗', unit: 'kg/t', min: 0, max: 200, step: 5 },
    { key: 'electricity', label: '制氢电耗', unit: 'MWh/h', min: 1000, max: 8000, step: 100 },
  ],
  bof: [
    { key: 'hot_metal_in', label: '铁水入炉', unit: 't/h', min: 200, max: 2000, step: 50 },
    { key: 'scrap', label: '废钢', unit: 't/h', min: 0, max: 600, step: 50 },
    { key: 'flux', label: '熔剂比', unit: 'kg/t', min: 0, max: 150, step: 5 },
  ],
  eaf: [
    { key: 'scrap', label: '废钢', unit: 't/h', min: 0, max: 2000, step: 50 },
    { key: 'dri', label: '直接还原铁', unit: 't/h', min: 0, max: 800, step: 50 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 50, max: 700, step: 20 },
    { key: 'electrode', label: '电极消耗', unit: 't/h', min: 0, max: 5, step: 0.5 },
  ],
  sinter_plant: [
    { key: 'ore_rate', label: '矿量', unit: 't/h', min: 200, max: 2500, step: 50 },
    { key: 'fuel_rate', label: '燃料比', unit: 'kg/t', min: 20, max: 80, step: 1 },
  ],
  coke_oven: [
    { key: 'coal_rate', label: '入炉煤', unit: 't/h', min: 100, max: 1200, step: 50 },
  ],
  ladle_furnace: [
    { key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 5, max: 60, step: 5 },
  ],
  caster: [
    { key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50 },
  ],
  rolling_mill: [
    { key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50 },
    { key: 'ng_rate', label: '天然气', unit: 'm³/t', min: 0, max: 80, step: 2 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 10, max: 200, step: 5 },
  ],
  pelletizing: [
    { key: 'ore_rate', label: '矿量', unit: 't/h', min: 100, max: 1200, step: 50 },
    { key: 'fuel_rate', label: '燃料比', unit: 'kg/t', min: 5, max: 40, step: 1 },
  ],
  reheating_furnace: [
    { key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50 },
    { key: 'ng_rate', label: '天然气', unit: 'm³/t', min: 0, max: 120, step: 2 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 2, max: 20, step: 2 },
  ],
  h2_dri: [
    { key: 'dri_out', label: '直接还原铁产量', unit: 't/h', min: 100, max: 1500, step: 50 },
    { key: 'h2_rate', label: '氢耗', unit: 'kg/t', min: 0, max: 200, step: 5 },
    { key: 'electricity', label: '制氢电耗', unit: 'MWh/h', min: 1000, max: 6000, step: 100 },
  ],
  dri_midrex: [
    { key: 'pellet_rate', label: '球团矿量', unit: 't/h', min: 100, max: 1500, step: 50 },
    { key: 'ng_rate', label: '天然气', unit: 'm³/t-DRI', min: 200, max: 400, step: 10 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 10, max: 150, step: 5 },
  ],
  smelting_reduction: [
    { key: 'ore_rate', label: '矿量', unit: 't/h', min: 100, max: 1500, step: 50 },
    { key: 'coal_rate', label: '非炼焦煤', unit: 't/h', min: 20, max: 300, step: 10 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 5, max: 80, step: 5 },
  ],
  biochar_injection: [
    { key: 'biomass_rate', label: '生物质碳', unit: 't/h', min: 0, max: 150, step: 5 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 0, max: 15, step: 1 },
  ],
  rh_vacuum: [
    { key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 1, max: 15, step: 1 },
  ],
  vd_vacuum: [
    { key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 1, max: 10, step: 1 },
  ],
  aod: [
    { key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 3, max: 30, step: 2 },
  ],
  ingot_casting: [
    { key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50 },
    { key: 'ng_rate', label: '保温燃气', unit: 'm³/t', min: 0, max: 80, step: 2 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 2, max: 20, step: 2 },
  ],
  cold_rolling: [
    { key: 'steel_in', label: '钢水量', unit: 't/h', min: 200, max: 2000, step: 50 },
    { key: 'ng_rate', label: '退火燃气', unit: 'm³/t', min: 0, max: 80, step: 2 },
    { key: 'electricity', label: '电耗', unit: 'MWh/h', min: 10, max: 200, step: 10 },
  ],
}

// ---------- 设备（工序）类型目录：label / 分类 / 3D 形状 / 业务描述 ----------
// cat 用于左侧工艺树分组，shape 用于 3D 场景构件选择，desc 用于属性面板/详情说明。
export const UNIT_TYPES = [
  // 原料准备
  { type: 'sinter_plant', label: '烧结机', cat: '原料准备', shape: 'box', desc: '本工序将铁矿粉配加熔剂和固体燃料（焦粉/煤粉）点火烧结成烧结矿，为高炉提供主要含铁炉料；其碳排放以固体燃料燃烧的直接排放为主，主抽风机等电耗为间接排放。' },
  { type: 'pelletizing', label: '球团', cat: '原料准备', shape: 'box', desc: '本工序将铁精矿配加膨润土造球，再经链篦机—回转窑焙烧成氧化球团矿，供高炉或直接还原使用；其碳排放以焙烧燃料燃烧的直接排放与造球/焙烧电耗为主。' },
  { type: 'coke_oven', label: '焦炉', cat: '原料准备', shape: 'box', desc: '本工序将洗精煤隔绝空气高温干馏为冶金焦，副产焦炉煤气（COG）；其碳排放以炼焦过程燃料消耗与挥发分逸散为主，煤的碳大部分固存于焦炭。' },
  { type: 'reheating_furnace', label: '加热炉', cat: '原料准备', shape: 'furnace', desc: '本工序将连铸坯加热至轧制温度，以高炉/转炉煤气为燃料；其碳排放以燃料燃烧的直接排放为主，是轧制工序的主要能耗与排放环节。' },
  // 炼铁
  { type: 'blast_furnace', label: '高炉', cat: '炼铁', shape: 'furnace', desc: '本工序以烧结矿/球团矿为料、焦炭为还原剂和燃料冶炼铁水，是长流程直接排放最大环节；其碳排放主要来自碳素还原、焦炭燃烧与熔剂分解。' },
  { type: 'hydrogen_bf', label: '氢冶金高炉', cat: '炼铁', shape: 'furnace', desc: '本工序以富氢气体部分替代焦炭还原冶炼铁水，碳排放显著低于传统高炉；其剩余排放来自少量焦炭与喷吹煤，是低碳冶炼的前沿路线。' },
  { type: 'h2_dri', label: '氢基竖炉', cat: '炼铁', shape: 'furnace', desc: '本工序以绿氢为还原剂直接还原铁矿制取直接还原铁（DRI），以电耗的间接排放为主，直接排放极低，是深度脱碳的炼铁路线。' },
  { type: 'dri_midrex', label: '直接还原炉', cat: '炼铁', shape: 'furnace', desc: '本工序以天然气转化的富氢重整气还原铁矿制取 DRI，供短流程电炉冶炼；其碳排放以重整过程燃料消耗为主，低于高炉-焦化路线。' },
  { type: 'smelting_reduction', label: '熔融还原', cat: '炼铁', shape: 'furnace', desc: '本工序以煤/焦为还原剂在熔融还原炉（如 COREX）中直接冶炼铁水，省去焦化与烧结工序；其碳排放以煤基还原燃烧的直接排放为主。' },
  { type: 'biochar_injection', label: '生物质喷吹', cat: '炼铁', shape: 'cylinder', desc: '本工序向高炉喷吹生物质炭替代部分化石燃料/焦炭，生物质为碳中性来源，可降低炉料净碳排放，属前沿低碳技术。' },
  // 炼钢
  { type: 'bof', label: '转炉', cat: '炼钢', shape: 'converter', desc: '本工序以高炉铁水为主、废钢为辅，顶吹/底吹氧气脱碳炼钢；其碳排放主要来自铁水降碳反应（扣除钢中固碳）与造渣熔剂分解。' },
  { type: 'eaf', label: '电炉', cat: '炼钢', shape: 'furnace', desc: '本工序以废钢/直接还原铁（DRI）为主料，电弧加热熔化冶炼；其碳排放以电弧电耗的间接排放为主，辅以天然气烧嘴与电极消耗的直接排放。' },
  // 精炼
  { type: 'ladle_furnace', label: '精炼炉', cat: '精炼', shape: 'cylinder', desc: '本工序（LF 钢包炉）对钢水进行电弧加热升温、合金化与成分微调；其碳排放以电弧加热电耗与合金/渣料消耗为主。' },
  { type: 'rh_vacuum', label: 'RH精炼', cat: '精炼', shape: 'cylinder', desc: '本工序通过真空循环脱气、脱碳与合金化精炼钢水，提升洁净度；其碳排放以真空泵与钢水升温电耗为主。' },
  { type: 'vd_vacuum', label: 'VD脱气', cat: '精炼', shape: 'cylinder', desc: '本工序在钢包内真空吹氩脱气，去除钢水中氢、氮等气体并均匀成分；其碳排放以真空系统电耗为主。' },
  { type: 'aod', label: 'AOD精炼', cat: '精炼', shape: 'converter', desc: '本工序（氩氧脱碳炉）主要用于不锈钢冶炼，通过吹氧脱碳与吹氩搅拌精炼；其碳排放以氧气/氩气消耗与升温电耗为主。' },
  // 连铸
  { type: 'caster', label: '连铸机', cat: '连铸', shape: 'slab', desc: '本工序将精炼合格钢水经结晶器连续凝固拉坯成铸坯，实现近终形一次成形；其碳排放以结晶器冷却、拉矫与切割电耗为主。' },
  { type: 'ingot_casting', label: '模铸', cat: '连铸', shape: 'box', desc: '本工序将钢水浇入钢锭模凝固成钢锭，用于特殊钢/大锻件等；其能耗低于连铸但成材率较低，碳排放以浇注与退火能耗为主。' },
  // 轧制
  { type: 'rolling_mill', label: '热轧机', cat: '轧制', shape: 'rollers', desc: '本工序将连铸坯加热后经粗轧/精轧轧制成热轧板卷/型材；其碳排放以加热炉燃料燃烧的直接排放与轧机传动电耗为主。' },
  { type: 'cold_rolling', label: '冷轧机', cat: '轧制', shape: 'rollers', desc: '本工序在常温下将热轧板卷轧制成冷轧薄板/带材，需配套酸洗、退火工序；其碳排放以退火炉燃耗与轧机电耗为主。' },
]

// ---------- 工艺分类的展示顺序（左侧工艺树 / 分组面板） ----------
export const CATEGORY_ORDER = ['原料准备', '炼铁', '炼钢', '精炼', '连铸', '轧制']

// ---------- 低碳技术列表（工序卡上的技术徽标选项） ----------
export const TECHS = [
  { tech: 'ccs', label: '碳捕集' },
  { tech: 'waste_heat', label: '余热回收' },
  { tech: 'h2_inj', label: '富氢喷吹' },
]
