// 附加设备资源库（所有场景可用的通用资源树，供工艺节点在编排属性面板中添加）：
//   「传感」= 工艺可附加的通用传感器 —— 每个传感器仅携带一个感知数值（measure 单感知量）；
//            传感器是唯一的取数对象：读数可来自固定值 / 随机模拟 / 数据源管理的实测设备 / 随可变设备联动。
//            其中「电功率传感器」（kW）是工序能碳核算的功率来源。
//   「调节」= 工艺可附加的可调设备 —— 只有设定值、不取数（设定值只用于调节运行工况，如变频/调压）。
//            它的实际功率不由自己给出：要核算功率就另外添加电功率传感器（数据源可设为随本设备联动）。
// 绑定方式与「工艺类型 → 典型可调设备」一致，但挂在具体工艺节点（scheme node.attached[]）上：
// 默认方案不含任何附加设备，因此钢铁企业默认传感设备保持不变；
// 用户在某工艺节点上添加后，该工艺在场景菜单 / 资源管理器 / 数据分析中即出现相应设备。
// 附加设备 id 均为  ext::节点id::attUid（由 store 合成，详情可打开、设定值随方案持久化）。

export const SENSOR_TEMPLATES = [
  { type: 'temp_sensor', kind: 'sensor', label: '温度传感器', unit: '℃',
    measure: { label: '温度', unit: '℃' }, range: { min: -40, max: 1800 }, def: 150,
    accuracy: '±0.5 ℃',
    desc: '热电偶 / 热电阻测温，用于监测工艺物料、烟气或环境温度，仅一个感知数值（温度）。接入实时数据源后读数即来自真实传感器。' },
  { type: 'humidity_sensor', kind: 'sensor', label: '湿度传感器', unit: '%RH',
    measure: { label: '相对湿度', unit: '%RH' }, range: { min: 0, max: 100 }, def: 45,
    accuracy: '±2 %RH',
    desc: '电容式 / 电阻式湿度传感，用于干燥、存储等环节环境湿度监测。' },
  { type: 'weight_sensor', kind: 'sensor', label: '称重传感器', unit: 'kg',
    measure: { label: '物料重量', unit: 'kg' }, range: { min: 0, max: 50000 }, def: 1200,
    accuracy: '±0.1 %',
    desc: '平台秤 / 料斗秤称重传感，附加于上料、成品等工序可实时感知物料重量，仅一个感知数值（重量）。' },
  { type: 'water_flow_sensor', kind: 'sensor', label: '水流量传感器', unit: 'm³/h',
    measure: { label: '水流量', unit: 'm³/h' }, range: { min: 0, max: 2000 }, def: 150,
    accuracy: '±0.5 %',
    desc: '电磁 / 超声波流量计，用于监测循环水、净环水等工艺水流量，仅一个感知数值（水流量）。' },
  { type: 'water_speed_sensor', kind: 'sensor', label: '水流速传感器', unit: 'm/s',
    measure: { label: '水流速', unit: 'm/s' }, range: { min: 0, max: 10 }, def: 2.2,
    accuracy: '±0.1 m/s',
    desc: '电磁 / 超声波流速计（或由流量计读数 ÷ 管截面换算），用于监测循环水、净环水管内流速；把数据源设为「随附加可调设备联动」后可随循环水泵变压器（或变频器）的设定值线性变化，是泵组调速效果最直接的观测量。' },
  { type: 'gas_flow_sensor', kind: 'sensor', label: '气体流量传感器', unit: 'm³/h',
    measure: { label: '气体流量', unit: 'm³/h' }, range: { min: 0, max: 100000 }, def: 8000,
    accuracy: '±1 %',
    desc: '涡街 / 差压式气体流量计，用于煤气、压缩空气等气体介质流量监测。' },
  { type: 'wind_speed_sensor', kind: 'sensor', label: '风流速传感器', unit: 'm/s',
    measure: { label: '风流速', unit: 'm/s' }, range: { min: 0, max: 60 }, def: 8.5,
    accuracy: '±0.3 m/s',
    desc: '皮托管 / 热式风速仪，用于风管、烟道内气流速度监测，仅一个感知数值（风流速）。' },
  { type: 'air_flow_sensor', kind: 'sensor', label: '风量传感器', unit: 'm³/min',
    measure: { label: '风量', unit: 'm³/min' }, range: { min: 0, max: 30000 }, def: 420,
    accuracy: '±2 %',
    desc: '用于鼓风 / 引风系统风量监测，是燃烧与通风工况的重要感知量。' },
  { type: 'pressure_sensor', kind: 'sensor', label: '压力传感器', unit: 'kPa',
    measure: { label: '压力', unit: 'kPa' }, range: { min: 0, max: 2500 }, def: 220,
    accuracy: '±0.25 %FS',
    desc: '压力变送器，用于介质管道、炉膛等压力监测，仅一个感知数值（压力）。' },
  { type: 'current_sensor', kind: 'sensor', label: '电流传感器', unit: 'A',
    measure: { label: '电流', unit: 'A' }, range: { min: 0, max: 5000 }, def: 120,
    accuracy: '±0.5 %',
    desc: '电流互感器 / 霍尔电流传感，用于电动机、变压器等用电回路电流监测。' },
  { type: 'voltage_sensor', kind: 'sensor', label: '电压传感器', unit: 'V',
    measure: { label: '电压', unit: 'V' }, range: { min: 0, max: 66000 }, def: 380,
    accuracy: '±0.5 %',
    desc: '电压变送器，用于配电回路电压监测，仅一个感知数值（电压）。' },
  { type: 'liquid_level_sensor', kind: 'sensor', label: '液位传感器', unit: 'm',
    measure: { label: '液位', unit: 'm' }, range: { min: 0, max: 30 }, def: 3.5,
    accuracy: '±0.5 %FS',
    desc: '雷达 / 静压式液位计，用于水池、水箱、油罐等液位监测。' },
  { type: 'speed_sensor', kind: 'sensor', label: '转速传感器', unit: 'r/min',
    measure: { label: '转速', unit: 'r/min' }, range: { min: 0, max: 10000 }, def: 1450,
    accuracy: '±1 r/min',
    desc: '光电 / 磁电转速传感，用于电动机、风机、水泵等旋转设备转速监测。' },
  { type: 'vibration_sensor', kind: 'sensor', label: '振动传感器', unit: 'mm/s',
    measure: { label: '振动速度', unit: 'mm/s' }, range: { min: 0, max: 50 }, def: 2.5,
    accuracy: '±0.2 mm/s',
    desc: '加速度计 / 速度型振动传感，用于旋转机械健康状态监测。' },
  { type: 'o2_sensor', kind: 'sensor', label: '氧含量传感器', unit: '%',
    measure: { label: '含氧量', unit: '%' }, range: { min: 0, max: 100 }, def: 20.9,
    accuracy: '±1 %',
    desc: '氧化锆 / 电化学氧传感，用于烟气或环境含氧量监测，仅一个感知数值（含氧量）。' },
  { type: 'co_sensor', kind: 'sensor', label: '一氧化碳浓度传感器', unit: 'ppm',
    measure: { label: 'CO 浓度', unit: 'ppm' }, range: { min: 0, max: 10000 }, def: 30,
    accuracy: '±5 ppm',
    desc: '红外 / 电化学 CO 传感，用于煤气泄漏预警与烟气 CO 监测。' },
  { type: 'power_sensor', kind: 'sensor', label: '电功率传感器', unit: 'kW',
    measure: { label: '有功功率', unit: 'kW' }, range: { min: 0, max: 500000 }, def: 2600,
    accuracy: '±0.5 %',
    desc: '功率变送器 / 智能电表模块，用于工序用电负荷监测（有功功率），仅一个感知数值。**功率型传感器是工序能碳核算的功率来源**：附加到某工序后，该传感器的读数（数据源管理设备的实测点位 / 模拟值 / 随可变设备联动）即取代包内功率参数参与折碳；工序要按实际功率核算，就在这里添加并设置数据源。' },
  { type: 'dust_sensor', kind: 'sensor', label: '粉尘浓度传感器', unit: 'mg/m³',
    measure: { label: '粉尘浓度', unit: 'mg/m³' }, range: { min: 0, max: 500 }, def: 15,
    accuracy: '±2 mg/m³',
    desc: '光散射 / β 射线粉尘仪，用于产尘工序除尘效果与环境粉尘浓度监测。' },
]

export const ADJUSTABLE_TEMPLATES = [
  { type: 'transformer', kind: 'adjustable', label: '变压器', unit: 'kV',
    setpoint: { label: '输出电压', unit: 'kV', min: 6, max: 35, step: 0.5, def: 10 },
    desc: '厂区电力变压器（6~35 kV），可调输出电压档位。附加到工序后可通过设定值调节供电电压，是模拟用电工况的调节手段。' },
  { type: 'frequency_converter', kind: 'adjustable', label: '变频器', unit: 'Hz',
    setpoint: { label: '输出频率', unit: 'Hz', min: 0, max: 60, step: 0.1, def: 40 },
    desc: '通用变频调速装置，调节电机 / 风机 / 泵的输出频率（0~60 Hz），设定值即当前运行工况。' },
  // 循环水泵等泵组的专用变压器：只有一个量 —— 设定值 = 输出电压（V）。
  // 可变设备的值只用于「设定运行工况」，不做取数、不参与折碳；该泵组的实际有功功率要在
  // 「传感器」里添加电功率传感器并设置数据源（可设为随本设备联动），由传感器读数参与能碳核算。
  { type: 'pump_transformer', kind: 'adjustable', label: '循环水泵变压器', unit: 'V',
    setpoint: { label: '输出电压', unit: 'V', min: 0, max: 660, step: 5, def: 380 },
    desc: '循环水泵（泵组）专用变压器，0~660 V 输出电压可调：电压↑ → 泵转速 / 流量↑、轴功率↑（泵类相似定律 P ∝ n³），是水系统降温强度与减排策略的作用对象。设定值只调运行工况，不直接参与折碳：本工序的实际有功功率请在「传感器」中添加电功率传感器（数据源可设为「随本设备联动」，电压↑ 则功率↑），核算以该传感器读数为依据。' },
  { type: 'rectifier', kind: 'adjustable', label: '整流器', unit: 'V',
    setpoint: { label: '直流输出电压', unit: 'V', min: 0, max: 1200, step: 10, def: 400 },
    desc: '可控硅整流装置，输出直流电压可调，用于直流传动等调节场景。' },
  { type: 'stabilizer', kind: 'adjustable', label: '稳压器', unit: 'V',
    setpoint: { label: '稳压输出', unit: 'V', min: 300, max: 500, step: 1, def: 380 },
    desc: '自动稳压装置，将配电电压稳定在设定输出值附近，调节后可改变工艺供电质量。' },
  { type: 'electric_valve', kind: 'adjustable', label: '电动调节阀', unit: '%',
    setpoint: { label: '阀门开度', unit: '%', min: 0, max: 100, step: 1, def: 60 },
    desc: '电动执行器驱动调节阀，阀门开度 0~100% 可调，用于水、气等介质流量调节。' },
  { type: 'damper_actuator', kind: 'adjustable', label: '风门执行器', unit: '%',
    setpoint: { label: '风门开度', unit: '%', min: 0, max: 100, step: 1, def: 70 },
    desc: '风道风门执行机构，风门开度 0~100% 可调，用于鼓风 / 引风风量调节。' },
  { type: 'variable_psu', kind: 'adjustable', label: '可变电源', unit: 'V',
    setpoint: { label: '输出电压', unit: 'V', min: 0, max: 66000, step: 10, def: 10000 },
    desc: '可编程可变电源，输出电压档位可调，用于配电 / 电解等环节的可变工况模拟。' },
  { type: 'tec_psu', kind: 'adjustable', label: '半导体制冷电源', unit: 'V',
    setpoint: { label: '制冷片供电电压', unit: 'V', min: 0, max: 60, step: 1, def: 48 },
    desc: '半导体制冷片（TEC）专用直流电源，输出电压 0~60 V 连续可调：电压↑ → 制冷功率↑（P ≈ U²/R）同时耗电与散热负荷↑，是机房温控降温强度与减排策略的作用对象。设定值只调运行工况，不直接参与折碳：本工序的实际有功功率请在「传感器」中添加电功率传感器（数据源可设为「随本设备联动」，电压↑ 则功率↑），核算以该传感器读数为依据。' },
]

export const SENSOR_MAP = Object.fromEntries(SENSOR_TEMPLATES.map((x) => [x.type, x]))
export const ADJUSTABLE_MAP = Object.fromEntries(ADJUSTABLE_TEMPLATES.map((x) => [x.type, x]))
// kind -> 模板映射（kind: sensor / adjustable）
export const ATTACH_MAP = { sensor: SENSOR_MAP, adjustable: ADJUSTABLE_MAP }
export const ALL_ATTACH = [...SENSOR_TEMPLATES, ...ADJUSTABLE_TEMPLATES]

// 供 LeftSidebar「传感器 / 可变设备」两棵资源树与 FlowInspector 添加下拉使用
export const ATTACH_GROUPS = [
  { key: 'sensor', label: '传感器', items: SENSOR_TEMPLATES },
  { key: 'adjustable', label: '可变设备', items: ADJUSTABLE_TEMPLATES },
]

// 附加设备模板的显示单位 / 默认感知数值 / 感知量标签
export function attachUnit(t) {
  return t.kind === 'sensor' ? t.measure.unit : t.setpoint.unit
}
export function attachDef(t) {
  return t.kind === 'sensor' ? t.def : t.setpoint.def
}
export function attachMeasureLabel(t) {
  return t.kind === 'sensor' ? t.measure.label : t.setpoint.label
}
// 功率型传感器（感知量单位为 kW，如电功率传感器的有功功率）：
// 这类传感器附加到工序后，其读数即该工序能碳核算的功率来源（取代包内功率参数）。
// 可变设备不参与取数——它的值只是设定值，只用于调节运行工况。
export function attachPowerSensor(t) {
  return !!(t && t.kind === 'sensor' && t.measure && t.measure.unit === 'kW')
}
