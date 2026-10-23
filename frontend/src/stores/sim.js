import { defineStore } from 'pinia'
import { watch, nextTick } from 'vue'
import { t } from '../i18n'
import { visiblePoll } from '../utils/poll'
import { api, openFeed } from '../api/client'
import { buildScheme, makeProcessNode, makeDeviceNode, makeMaterialNode, PROCESS_MAP, MATERIAL_MAP, PROCESS_ADJUSTABLE, DEVICE_MAP, DEVICE_COUPLE_REGISTRY, deriveProcessOpParams, materialFamily, loadCalibrations, registerSceneMaterials, NODE_NW, NODE_HEADER, NODE_PORT_Y0, NODE_GAP, nodeHeight, PROCESS_TEMPLATES, applySetpointResponse, migrateLegacyDevices, treeLayoutNodes } from '../data/flowLibrary'
import { computeScheme } from '../flow/compute'
// 规则执行器（纯函数）：AI 群控运行态策略由本 store 的后台运行器按周期执行时用它求值
import { evalFlowGraph } from '../utils/ruleFlow'
import { PARK } from '../data/park'
// 通用附加设备库（传感器 / 可变设备，所有场景可用）：
// 与「工艺类型 → 典型可调设备」不同，附加设备是用户在某工艺节点上按需添加的，
// 存于工艺节点 node.attached[]，运行态由 store 合成 ext::节点id::attUid 设备。
import { SENSOR_MAP, ADJUSTABLE_MAP, ATTACH_MAP, attachUnit, attachDef, attachMeasureLabel, attachPowerSensor } from '../data/attachLibrary'
// 工艺静态业务数据：集中维护于独立数据模块 src/data/processMeta.js
// （业务数据与代码逻辑分离），本 store 只负责仿真状态与交互逻辑；
// 下方 re-export 保持既有组件 `import { ... } from '../stores/sim'` 兼容。
import { OP_PARAM_KEYS, DIRECT_PARAM_KEYS, EDITABLE_PARAMS, UNIT_TYPES, CATEGORY_ORDER, TECHS } from '../data/processMeta'
import { uid } from '../utils/id'
import { fmtNum } from '../utils/format'
export { OP_PARAM_KEYS, DIRECT_PARAM_KEYS, EDITABLE_PARAMS, UNIT_TYPES, CATEGORY_ORDER, TECHS }

// AI 优化模型：左侧「策略 → AI优化模型」目录（序列预测 / 强化学习 / 遗传算法 / 粒子群）。
// 随实时传感器数据持续采集，后端调度线程定时训练，模型迭代次数与最优强度逐步提升
// （属性面板轮询后端状态实时展示「逐渐变优」过程，训练结果可一键应用到流程）。
// 类别：seq = 时序预测（预测未来工况）；opt = 参数优化（决策变量 + 优化目标设定）；cluster = 聚类分析（工况识别）
export const AI_MODELS = [
  { id: 'ai::seq', category: 'seq', categoryName: '时序预测', name: '序列预测算法', tag: 'SEQ', desc: '适用于预测未来工况：内置 LSTM、LightGBM、XGBoost 与时间序列大模型（暂不实现），可设定预测目标 / 影响变量，设定最佳策略或调节变量进行仿真分析。' },
  { id: 'ai::rl', category: 'opt', categoryName: '参数优化', name: '强化学习优化策略', tag: 'RL', desc: '在线策略梯度：随实时传感器数据持续更新参数策略，先探索后利用，越训越优。' },
  { id: 'ai::ga', category: 'opt', categoryName: '参数优化', name: '遗传算法优化策略', tag: 'GA', desc: '适用于设备启停与连续参数复合的混合场景：对设备启停开关与喷煤比、焦比等连续参数组合做选择/交叉/变异，全局搜索最低碳排配置。' },
  { id: 'ai::pso', category: 'opt', categoryName: '参数优化', name: '粒子群优化策略', tag: 'PSO', desc: '适用于连续参数空间下最优解的探索：粒子在连续参数空间协同飞行，快速逼近最优运行点，适合实时在线寻优。' },
  { id: 'ai::clu', category: 'cluster', categoryName: '聚类分析', name: '聚类工况识别', tag: 'CLU', desc: '适用于历史工况的自动聚类与模式划分：内置 K-Means、DBSCAN 与层次聚类，自动识别典型运行工况（低/中/高负荷）及其占比，辅助制定分工况调节策略。' },
  { id: 'ai::fit', category: 'fit', categoryName: '数据拟合', name: '数据拟合分析', tag: 'FIT', desc: '对历史工况数据做曲线拟合建模：内置多项式 / 指数 / 对数 / 幂函数拟合，输出拟合方程与 R² 拟合优度，辅助洞察负荷趋势与关联规律。' },
  // MPC 控温优化模型：与上面几个「训练型」模型不同，它是一套**求解型**控制器
  // （灰箱一阶 RC 前向模型 + 离散档位动态规划），点击进入独立页面：
  // 先看可用性自检（能否启用），再输入「目标温度 + 到达时限」求解能耗最小档位。
  // view 字段表示点击后打开的中间区视图 id（见 VIEW_DEFS）；agc 字段表示进入该视图后落在哪个内置子页。
  // MPC 控温优化不是独立视图，而是 AI 群控模型库里的内置求解型模型（见 PidControlView 的 alg-mpc 卡片）。
  { id: 'ai::mpc', category: 'mpc', categoryName: 'MPC控制', name: 'MPC控温模型', tag: 'MPC', view: 'aiGroup', agc: 'mpc', desc: '面向控温设备的求解型控制器：前向模型用灰箱一阶 RC（时间常数、风扇/制冷片增益），决策用离散档位动态规划，在给定时限内求能耗最小的风扇电压与制冷片电流组合。集成在「AI群控 → 模型库」，与规则 / 强化学习 / 粒子群并列；「>45℃ 满功率、以下智能调控」的双模式也在该页。' },
]
export const AI_MODEL_MAP = Object.fromEntries(AI_MODELS.map((m) => [m.id, m]))

// ===== 功能视图（窗口 + tab）注册表 =====
// 中间内容区的功能视图不再「独占全屏、互斥切换」：统一以窗口形式打开，
// 顶部 tab 标签可同时挂载多个视图并自由切换（关闭某个 tab 不影响其它已打开视图）。
// id 与 openViews / activeViewId 一一对应；title 经 t() 国际化后展示在 tab 上。
export const VIEW_DEFS = [
  { id: 'flowEdit', title: '流程编排' },
  { id: 'dataView', title: '数据分析' },
  { id: 'aiGroup', title: 'AI群控' },
  { id: 'carbonMarket', title: '碳资产管理' },
  { id: 'carbonCalc', title: '全景碳核查' },
  { id: 'energyFlow', title: '能流分析' },
  // boxManage = 数据源管理（能碳一体机 + 外部数据源统一接入管理），标题对外展示为「数据源管理」
  { id: 'boxManage', title: '数据源管理' },
]
export const VIEW_IDS = VIEW_DEFS.map((v) => v.id)
export const VIEW_TITLE = Object.fromEntries(VIEW_DEFS.map((v) => [v.id, v.title]))

// 实时消息流（并入底栏「输出」）保留条数上限：现场设备每秒都有上报，超出即丢弃最旧的
const MQTT_LOG_CAP = 300
// 数据源管理设备列表轮询：_boxSrcBusy 防并发重入，_boxSrcTimer 常驻定时器
let _boxSrcBusy = false
let _boxSrcTimer = null
// 可变设备设定值「下发去重」：extId -> { v, ts }。
// 规则 / 算法每轮都会调用设定入口，若不去重会按运行周期（默认 2s）持续往盒子发 cmd 写命令，
// 形成命令风暴并反复改写现场状态。同值保持期内不再下发；失败则按较短间隔允许重试。
const _extWriteLast = {}
const _EXT_WRITE_KEEP_MS = 30000    // 下发成功后：同值 30s 内不重复下发
const _EXT_WRITE_RETRY_MS = 10000   // 下发失败后：至少 10s 才重试（避免每轮重发）
// 静默（自动执行）模式下失败提示的节流时间戳：extId -> ms
const _extWriteErrAt = {}
// ── AI 群控后台运行器 ──
// 运行态（哪个模型在跑）由服务端存档保存，换电脑 / 重开浏览器拉到运行态后就在这里恢复执行，
// 不再依赖「是否停留在编排页」——此前执行定时器挂在画布组件内，一离开编排页策略就停了。
let _agcTimer = null
let _agcModel = null      // 运行中的模型（持引用：编排改动即时生效）
let _agcState = null      // 跨轮次状态（循环模块的挂起轮次）

// ===== 附加设备（传感器 / 可变设备）合成工具 =====
// 附加设备挂在具体工艺节点 node.attached[] 上，id 均为 ext::节点id::attUid；
// 运行态由 getter 从 scheme 节点 + 对应 unit（params/实时）合成设备条目。
function _attachTpl(kind, type) {
  const m = ATTACH_MAP[kind] || {}
  return m[type] || null
}
// ===== 附加设备命名 =====
// 附加到同一工序的同类型设备可以有多个（如两台温度传感器），名称必须可区分：
// ① 默认名 = 模板类型名 + 同类型实例序号（第 2 个为「温度传感器2」），用户可在属性面板随时改名；
// ② 任何情况下保证同一工序内名称唯一 —— 重名自动追加序号（重命名的情况下也适用），
//    因为名称是设备树 / 数据分析 / 规则编排里识别该设备的唯一显示标识。
function _attachSameTypeCount(node, type) {
  return ((node && node.attached) || []).filter((a) => a && a.type === type).length
}
function _uniqueAttachName(node, base, exceptUid) {
  const b = String(base == null ? '' : base).trim()
  if (!b) return b
  const used = new Set(((node && node.attached) || [])
    .filter((a) => a && a.uid !== exceptUid)
    .map((a) => String(a.label == null ? '' : a.label).trim()))
  if (!used.has(b)) return b
  let i = 2
  while (used.has(`${b}${i}`)) i += 1
  return `${b}${i}`
}
// 默认名（未显式给名时）：类型名 + 实例序号
function _defaultAttachName(node, kind, type) {
  const tpl = _attachTpl(kind, type)
  const base = tpl ? tpl.label : String(type || '')
  const n = _attachSameTypeCount(node, type) + 1
  return n > 1 ? `${base}${n}` : base
}
// 数据源管理（能碳一体机）中的传感器设备 → 「设备名::点位名」当前读数映射
// 供附加设备 src='device' 时取值（轮询刷新 store.boxSourceDevices 即自动更新）
function _boxSrcMap(s) {
  const m = {}
  for (const d of (s.boxSourceDevices || [])) {
    const props = d.props || []
    for (const p of props) {
      if (p.value == null) continue
      const key = `${d.name}::${p.name}`
      if (m[key] == null) m[key] = { v: p.value, ts: p.ts }
      // 未指定点位时（旧数据/设备仅一个点位）取该设备第一个有值点位
      const dk = `${d.name}::`
      if (m[dk] == null) m[dk] = { v: p.value, ts: p.ts }
    }
  }
  return m
}
// 附加设备当前读数：按「数值来源」解析（只有传感器取数；可变设备的值就是其设定值，不参与取数）
//  可调设备（kind=adjustable）→ 直接返回当前设定值（deviceSetpoints 优先，其次 att.def / 模板默认），
//           与其 src 无关：可变设备只用于设定运行工况，不产生读数。
//  传感器 src = fixed → att.def（模板默认）；param → 绑定工艺节点的某数值参数；
//  sim → 以默认值为基准的随机模拟；device → 数据源管理中某传感器设备的实时读数；
//  attach → 随同一节点上某附加可调设备的设定值联动（线性过原点：读数 = 设定值 × scale.to / scale.from）。
//           典型如循环水泵变压器输出电压 → 冷却水流速 / 泵组功率：电压降则泵速↓、流速与轴功率↓，
//           传感器读数随之变化，用于观察调速调节的实际效果（能碳核算以功率型传感器的读数为依据）。
// 换算系数：源值 → 系统读数（读数 = 源值 × 系数，默认 1）。
// 系统模板的单位度量与绑定传感器/采集设备的实际度量可能不一致（如 m³/h vs L/s、W vs kW），
// 用户在编排面板按源设置系数换算；对传感器各数据源与可变设备设定值统一生效。
function _attFactor(att) {
  const f = att && att.factor != null ? Number(att.factor) : 1
  // 系数最多两位小数（超出按四舍五入取整）
  return isFinite(f) ? Math.round(f * 100) / 100 : 1
}
function _fx(v, att) {
  return v == null ? null : Math.round(Number(v) * _attFactor(att) * 1000) / 1000
}
function _attachReading(att, unit, now, srcMap, node, setpoints) {
  if (!att) return null
  const tpl = _attachTpl(att.kind, att.type)
  const def = att.def != null ? att.def
    : (tpl ? (tpl.kind === 'sensor' ? tpl.def : (tpl.setpoint && tpl.setpoint.def)) : 0)
  // 可变设备（可调设备）：值即设定值本身，不做任何取数解析
  if (tpl && tpl.kind === 'adjustable') {
    const extId = node ? `ext::${node.id}::${att.uid}` : ''
    const sp = extId && setpoints && setpoints[extId] != null ? Number(setpoints[extId]) : null
    return _fx(sp != null && isFinite(sp) ? sp : Number(def), att)
  }
  if (!att.src || att.src === 'fixed') return _fx(def, att)
  if (att.src === 'param') {
    if (!unit || !unit.params || !att.param) return null
    const v = Number(unit.params[att.param])
    return isNaN(v) ? null : _fx(v, att)
  }
  if (att.src === 'sim') {
    // 功率型传感器（kW）未给默认值时，以工序功率参数（MW → kW）为模拟基准
    const base = (attachPowerSensor(tpl) && !def)
      ? (Number((unit && unit.params && unit.params.power) || 0) * 1000)
      : (def || 0)
    const phase = String(att.uid || att.type || '').split('').reduce((a, c) => a + c.charCodeAt(0), 0)
    const w = ((now || Date.now()) / 1200) + phase
    return _fx(Math.round(base * (1 + 0.08 * Math.sin(w)) * 1000) / 1000, att)
  }
  if (att.src === 'device') {
    if (!att.device) return null
    const hit = (srcMap || {})[`${att.device}::${att.prop || ''}`]
    return hit && hit.v != null ? _fx(hit.v, att) : null
  }
  if (att.src === 'attach') {
    const ref = _attachRef(node, att)
    if (!ref) return null
    const refTpl = _attachTpl(ref.kind, ref.type)
    const refId = `ext::${node.id}::${ref.uid}`
    const sp = (setpoints && setpoints[refId] != null)
      ? Number(setpoints[refId])
      : Number(ref.def != null ? ref.def : (refTpl && refTpl.setpoint ? refTpl.setpoint.def : 0))
    if (!isFinite(sp)) return null
    const from = att.scale && Number(att.scale.from) ? Number(att.scale.from) : 0
    const to = att.scale && att.scale.to != null ? Number(att.scale.to) : def
    const v = from ? Math.round(sp * (to / from) * 1000) / 1000 : 0
    const r = tpl && tpl.range
    return _fx(r ? Math.min(r.max, Math.max(r.min, v)) : v, att)
  }
  return null
}
// 联动源：同一工艺节点上被联动的附加可调设备（att.devRef = 其 uid）
function _attachRef(node, att) {
  if (!node || !att || !att.devRef) return null
  return ((node.attached) || []).find((a) => a && a.uid === att.devRef) || null
}
// 工艺节点 → 附加设备合成（结构对齐计量/可调设备，详情面板可打开）
function _extDevice(node, unit, att, now, srcMap, setpoints) {
  const tpl = _attachTpl(att.kind, att.type)
  if (!tpl) return null
  const extId = `ext::${node.id}::${att.uid}`
  const isSensor = tpl.kind === 'sensor'
  const mUnit = isSensor ? tpl.measure.unit : tpl.setpoint.unit
  const reading = _attachReading(att, unit, now, srcMap, node, setpoints)
  const ref = att.src === 'attach' ? _attachRef(node, att) : null
  const srcNote = att.src === 'param' && att.param
    ? '　读数来源：绑定工艺参数「' + att.param + '」。'
    : (att.src === 'device' && att.device
      ? '　读数来源：数据源管理设备「' + att.device + (att.prop ? ' · ' + att.prop : '') + '」实时读数。'
      : (ref
        ? '　读数来源：随附加可变设备「' + (ref.label || ref.type) + '」设定值联动（'
          + (att.scale && att.scale.from != null ? att.scale.from : '—') + ' → '
          + (att.scale && att.scale.to != null ? att.scale.to : '—') + ' ' + mUnit + '，线性换算）。'
        : ''))
  // 取数口径：只有传感器取数（读数可来自实测设备 / 模拟 / 联动）；
  // 可变设备不取数 —— 其数值就是设定值，只用于调节运行工况，
  // 本工序的实际功率由附加的功率型传感器（电功率传感器 kW）承载并参与能碳核算。
  const rdNote = isSensor && attachPowerSensor(tpl)
    ? '　本传感器为功率量测（kW）：其读数即所属工序能碳核算的功率来源（接入数据源管理的采集设备点位即为实测功率）。'
    : (isSensor ? '' : '　设定值只调运行工况；本工序实际功率请在「传感器」中添加电功率传感器设置。')
  return {
    id: extId,
    type: att.type,
    label: att.label || tpl.label,
    unit: mUnit,
    measures: [{ key: 'val', label: isSensor ? tpl.measure.label : tpl.setpoint.label, unit: mUnit }],
    measured: reading,
    reading,
    // 读数标签 / 单位（仅传感器有读数；可变设备只有设定值）
    readingLabel: isSensor ? tpl.measure.label : null,
    readingUnit: isSensor ? tpl.measure.unit : null,
    // 功率型传感器（kW）：其读数是所属工序能碳核算的功率来源
    powerReading: isSensor && attachPowerSensor(tpl),
    metering: isSensor,
    adjustable: !isSensor,
    setpoint: !isSensor ? (att.def != null ? att.def : tpl.setpoint.def) : null,
    ext: true,
    attachKind: att.kind,
    src: att.src || 'fixed',
    param: att.param || null,
    device: att.device || null,
    prop: att.prop || null,
    devRef: att.devRef || null,
    desc: `${tpl.label}（${isSensor ? '传感器' : '可变设备'}）：${tpl.desc || ''}${rdNote}${srcNote}`,
    unitId: node.id,
    unitName: (unit && unit.name) || node.name || node.type,
    unitType: (unit && unit.type) || node.type,
  }
}

// 工序的「实测功率」（kW）：取自该工序附加的**功率型传感器**（如电功率传感器的有功功率 kW），
// 读数来自「数据源管理设备」绑定的采集设备点位（或随机模拟 / 固定值 / 随可变设备联动）。
// 可变设备不参与取数——它的值只是设定值（如变压器输出电压 V），只用于调节运行工况，
// 实际功率必须由传感器承载：这就是「能碳核算的数据来源为传感器的值」的口径。
// 只要解析出数值就参与所属工序的能碳核算（范围二折碳），无功率传感器（读数 null）时返回 null，
// 由调用方回落包内工序功率参数（出厂设定）。返回 { kW, sources, measured, simulated }。
function _attachedSensorPower(u, srcMap, now, setpoints) {
  const node = u || {}
  const atts = Array.isArray(node.attached) ? node.attached : []
  let kW = 0
  const sources = []
  for (const att of atts) {
    if (!att) continue
    const tpl = _attachTpl(att.kind, att.type)
    if (!tpl || tpl.kind !== 'sensor' || !attachPowerSensor(tpl)) continue
    const v = _attachReading(att, node, now, srcMap, node, setpoints)
    if (v == null) continue
    const n = Number(v)
    if (!isFinite(n)) continue
    kW += n
    sources.push({
      id: `ext::${node.id}::${att.uid}`,
      type: att.type,
      label: att.label || tpl.label,
      unit: 'kW',
      measured: n,
      src: att.src || 'fixed',
      device: att.device || null,
      prop: att.prop || null,
    })
  }
  if (!sources.length) return null
  return {
    kW,
    sources,
    measured: sources.some((s) => s.src === 'device'),            // 真机实测（数据源管理采集设备）
    simulated: sources.some((s) => s.src === 'sim' || s.src === 'fixed' || s.src === 'attach'),
  }
}

// 非钢场景的单位级能碳字段：同时给出两套口径，避免"侧边栏有数、孪生标签没数"。
// ① 碳引擎口径（与钢场景后端下发一致，3D 数字孪生标签 / 小组汇总标签 / 2D 视图 KPI / 排放占比着色都用它）：
//    co2_total 单位 tCO₂/h、energy_total 单位 GJ/h（1 kWh = 3.6 MJ = 0.0036 GJ）；
// ② 本场景口径（属性面板 / 编排面板用）：carbon 单位 kgCO₂/h、energy 单位 kWh/h。
// directT = 本工序范围一直接排放（tCO₂/h，由资源包字典 emissions 声明计算，未声明则为 0）；
// indirectKg = 范围二间接排放（kgCO₂/h = 功率 kW × 电网排放因子）。
function _otherUnitMetrics(powerKW, indirectKg, directT) {
  const direct = Number(directT) || 0
  const indirect = (Number(indirectKg) || 0) / 1000
  const total = direct + indirect
  return {
    carbon: total * 1000,             // kgCO₂/h（本场景口径，含直接 + 间接）
    energy: powerKW,                  // kWh/h
    prod: 1,
    unitCarbon: total * 1000,
    co2_total: total,                 // tCO₂/h（孪生标签 / 折碳汇总口径）
    co2_direct: direct,               // tCO₂/h（范围一：燃料燃烧 / 工业过程）
    co2_indirect: indirect,           // tCO₂/h（范围二：耗电折碳）
    energy_total: powerKW * 0.0036,   // GJ/h
    powerKW,                          // 实际参与折碳的功率
  }
}

// 非钢场景的工序**范围一直接排放**（tCO₂/h）：由资源包字典（dictionary.processes[].emissions）
// 声明式驱动，通用能力、不写死行业。两种声明：
//   { kind: 'fuel',      fuel: 'coal',      param: 'coal_rate' }       燃料燃烧：消耗量 × 低位发热量 × 单位热值含碳量 × 碳氧化率 × 44/12
//   { kind: 'carbonate', carbonate: 'limestone', param: 'limestone_rate' }  工业过程：消耗量 × 碳酸盐含量 × 碳酸盐排放因子
// 未声明 emissions 的工序（纯耗电工序 / 未声明的旧资源包）直接排放为 0 —— 行为与既有口径一致。
function _otherUnitDirect(u, dict, factors) {
  const defs = (dict && Array.isArray(dict.processes)) ? dict.processes : []
  const def = defs.find((p) => p && p.type === (u && u.type)) || null
  const list = (def && Array.isArray(def.emissions)) ? def.emissions : []
  const f = factors || {}
  const params = (u && u.params) || {}
  const items = []
  let t = 0
  for (const e of list) {
    if (!e || !e.param) continue
    const amount = Number(params[e.param])
    if (!isFinite(amount) || amount <= 0) continue
    if (e.kind === 'fuel') {
      const fuel = (f.fuels || {})[e.fuel]
      if (!fuel) continue
      const ox = Number(fuel.ox) || 1
      const ef = (Number(fuel.ncv) || 0) * (Number(fuel.cc) || 0) * ox * 44 / 12   // tCO₂ / 消耗单位
      const v = amount * ef
      if (!isFinite(v)) continue
      t += v
      items.push({ kind: 'fuel', label: e.label || fuel.label || e.fuel, amount, unit: fuel.unit || '', ef, co2: v })
    } else if (e.kind === 'carbonate') {
      const base = (f.carbonate || {})[e.carbonate]
      if (!base) continue
      const purity = Number(e.purity != null ? e.purity : (f.carbonate_purity != null ? f.carbonate_purity : 1)) || 1
      const v = amount * purity * (Number(base) || 0)
      if (!isFinite(v)) continue
      t += v
      items.push({ kind: 'carbonate', label: e.label || e.carbonate, amount, unit: 't/h', ef: (Number(base) || 0) * purity, co2: v })
    }
  }
  return { t, items }
}

// 由工序合成其典型"可调设备"条目（按工艺类型 PROCESS_ADJUSTABLE 给出），
// 与后端下发的"计量设备"区分；用于设备树、3D 标注与详情。id 稳定为 工序::类型。
function _adjDevice(u, dt, setpoints, extraSetpoints) {
  const tmpl = DEVICE_MAP[dt]
  if (!tmpl) return null
  const sid = `${u.id}::${dt}`
  const sp = (setpoints && setpoints[sid] != null) ? setpoints[sid] : (tmpl.setpoint ? tmpl.setpoint.def : null)
  // 附加可调项（如鼓风机鼓风湿度）：合并用户设定值，未设则取模板默认
  const esStore = (extraSetpoints && extraSetpoints[sid]) || {}
  const extraSetpointsMerged = {}
  if (tmpl.extraSetpoints && tmpl.extraSetpoints.length) {
    for (const es of tmpl.extraSetpoints) {
      extraSetpointsMerged[es.key] = (esStore[es.key] != null) ? esStore[es.key] : es.def
    }
  }
  return {
    id: sid,
    type: dt,
    label: (DEVICE_MAP[dt] ? DEVICE_MAP[dt].label : dt),
    unit: tmpl.unit,
    measures: tmpl.measures,          // 测量物理量中文说明（如「风量」）
    measured: applySetpointResponse(sp, tmpl.response),  // 测定值(PV)：保留用于数据建模/真实 SCADA 场景；当前核算与展示均以设定值为准
    deviation: (tmpl.response && tmpl.response.bias) || 0, // 稳态偏差率
    color: '#0860A8',          // 可调设备统一用钢蓝（与计量灰区分，全站单一强调色）
    metering: false,
    adjustable: true,
    setpoint: sp,              // 设定值(SP)：可调节，保存于 store.deviceSetpoints；输入框数字即当前值
    boundTo: u.id,
    reading: sp,               // 当前值=设定值（输入框中的数字即当前工况值）
    extraSetpoints: extraSetpointsMerged,
    // 让右侧属性面板（即使后端设备库未收录可调类型）也有完整说明/量程，避免空白
    desc: `${tmpl.label}：${tmpl.desc || '本工序的可调设备，其设定值经碳引擎折算为运行电耗与间接排放，是减排策略的作用对象。'}`,
    accuracy: tmpl.accuracy || '—',
    range: tmpl.range || (tmpl.setpoint ? `${tmpl.setpoint.min} – ${tmpl.setpoint.max} ${tmpl.setpoint.unit}` : '—'),
    feeds: tmpl.feeds || null,
  }
}

// 由编排连线推导「实际连接」某工序实例的工辅类型集合（含上游链路传递）。
// 工辅(route:'aux')经物料连线把自身输出物料供给工序节点输入端口，即视为已绑定；
// 未连线的工辅不视为该工序的可调设备——绑定关系由编排画布中的连线决定。
// 链路传递：沿「上游方向」递归（如 鼓风机→热风炉→高炉：高炉的可调设备同时包含
// 热风炉与鼓风机；热风炉的可调设备包含鼓风机），构成以工序为树干、工辅为分支的工艺树。
function linkedAuxTypesFor(scheme, unitId) {
  const nodes = (scheme && scheme.nodes) || []
  const conns = (scheme && scheme.connections) || []
  const nodeById = {}
  for (const n of nodes) nodeById[n.id] = n
  const out = []
  const seenTypes = new Set()
  const visitedUnits = new Set()
  const visit = (uid) => {
    if (visitedUnits.has(uid)) return // 防环：同一实例仅遍历一次
    visitedUnits.add(uid)
    for (const c of conns) {
      const f = nodeById[c.from], t = nodeById[c.to]
      if (!f || !t) continue
      const ft = PROCESS_MAP[f.type], tt = PROCESS_MAP[t.type]
      if (!ft || !tt) continue
      const m = c.material
      if (!m) continue
      // 工辅 f 的输出物料流入 uid → f 为 uid 的上游分支；继续递归 f 自身的上游（链路传递）
      if (ft.route === 'aux' && t.id === uid && (ft.outputs || []).includes(m)) {
        if (!seenTypes.has(f.type)) { seenTypes.add(f.type); out.push(f.type) }
        visit(f.id)
      }
      // 工辅 t 接收 uid 供给（物料在 t 的输出清单中，如皮带/给料输送）→ t 视为绑定 uid
      if (tt.route === 'aux' && f.id === uid && (tt.outputs || []).includes(m)) {
        if (!seenTypes.has(t.type)) { seenTypes.add(t.type); out.push(t.type) }
        visit(t.id)
      }
    }
  }
  visit(unitId)
  return out
}

// 某工序实例的可调设备类型 = 基础清单(PROCESS_ADJUSTABLE) + 实际连线供给的工辅类型（含上游链路传递）。
// 该集合依赖连线图遍历（O(节点数+连线数)），而实时消息处理中每个工序实例每条消息都会调用，
// 高频数据流下重复全图扫描开销可观。此处按「方案对象 + 节点/连线规模指纹」缓存：
// 编辑态增删节点/连线会改变规模指纹自动失效；同一方案运行期内跨消息直接命中缓存。
const _adjTypesCache = new WeakMap()
function adjustableTypesFor(scheme, unitType, unitId) {
  const set = new Set(PROCESS_ADJUSTABLE[unitType] || [])
  // 喷吹系统(喷煤量)已锁定：即使连线供给高炉也不作为可调设备合成（喷吹速率固定为工艺默认值）
  for (const dt of linkedAuxTypesFor(scheme, unitId)) if (dt !== 'injector') set.add(dt)
  return [...set]
}

// 撤销/重做：合并键 + 时间戳（模块级，避免进入响应式 state）
let _histKey = null
let _histTime = 0
const HIST_COALESCE_MS = 900
const cloneScheme = (scheme) => JSON.parse(JSON.stringify(scheme))
let _refreshTimer = null   // 刷新防抖定时器（模块级，避免进入响应式 state）
let _refreshSeq = 0       // 刷新序号：丢弃过期响应，避免旧请求覆盖新状态
let _simSnapshot = null   // 仿真模式进入时的全量快照（模块级，避免进入响应式 state）
let _schemeDirtyBound = false // 编排「改动检测」监听只绑一次（手动保存模式：只标脏，不落盘）
let _autoSetpointGuard = 0   // 「群控自动写设定值」抑制计数（>0 表示刚发生机器写入，不标脏也不写服务端，详见 _bindSchemeDirty）
// 服务端编排存档（designs/flow）的读取结果，决定「是否允许写回服务端」：
//   'ok'    —— 成功读到本场景存档（可写回）
//   'empty' —— 服务端确认本场景尚无存档（可写回：即首次初始化存档）
//   'error' —— 读取失败（接口异常 / 网络中断）或存档不可用被拒收（**禁止写回**）
// 分这三态是因为：读取失败时前端手里只有「按模板重建的默认方案」，一旦照旧落盘
// 就会把默认模板写成服务端真档，用户保存过的编排被永久抹掉 ——
// 表现为「编排莫名其妙回到默认」（历史顽疾，见 _pullScheme / openScene）。
let _designPullState = 'ok'
let _schemeAdoptChanged = false  // _adoptScheme 是否真的改过方案内容（决定是否回写服务端）
let _simPrevDirty = false     // 进入仿真前的未保存标记：仿真态编辑不落盘，退出后应回到该状态
let _simParamSnapshot = null  // 仿真进入时的参数快照（「仿真前 → 当前」变化展示用，模块级）
const _snapParams = (model) => {  // 提取各工序参数：{ unitId: { key: val } }
  const out = {}
  for (const u of (model && model.units) || []) out[u.id] = { ...(u.params || {}) }
  return out
}

export const useSimStore = defineStore('sim', {
  state: () => ({
    model: { units: [], flows: [] },
    baseline: null,
    strategy: null,
    delta: null,
    parsed: null,
    parsedText: '',
    strategyInput: '',  // 预置策略文本（点击左栏「内置 → 预置策略」时填充并自动解析）
    parsing: false,
    strategies: [],
    presets: [],
    selectedUnitId: null,
    autoRotate: false,
    brightness: 0.95,       // 画面亮度（映射到 renderer.toneMappingExposure）：默认 0.95，范围 0.3 ~ 2.5
    live: null,
    ready: false,
    entered: false,      // 欢迎页是否已进入（打开项目后置 true，进入主界面）
    busy: false,
    feedStatus: 'init',
    aboutDialog: false,   // 关于本平台弹窗开关（StatusBar / 帮助菜单 / App 共用）
    toast: '',
    toastType: 'info',    // 类型化 Toast：success / info / warn / error（ToastLayer 渲染）
    confirmDialog: { open: false, title: '', message: '', okText: '', cancelText: '', danger: false }, // 确认弹窗（ConfirmDialog 渲染）
    _confirmResolver: null, // confirm() 挂起的 Promise resolve
    scenario: 'steel',           // 当前仿真场景行业（四大控排 + 其它）：steel 钢铁(默认) / cement 水泥 / chemical 化工 / nonferrous 有色 / other 其它(资源包场景)
    processRoute: 'short',       // 当前流程：短流程(默认) / 长流程；数字孪生默认展示短流程。资源包场景下为包内模板 id（如 cool）
    // —— 工程选择（欢迎页）——
    // welcomeOn = true 表示尚未打开工程：中间内容区显示「工程选择」欢迎页（左栏保留），
    // 只有用户新建 / 打开工程后才进入主界面（本次会话内刷新不再回欢迎页，见 _loadWelcomeState）。
    welcomeOn: true,
    recentScenes: [],            // 最近打开的工程：[{ id, label, industry, ts }]，localStorage sim.recentScenes 持久化
    // —— 场景 / 资源包（.ec）状态 ——
    sceneId: 'steel',            // 当前打开的场景资源包 id（steel = 平台内置钢包）
    sceneMode: 'steel',          // 'steel' = 钢铁碳引擎场景（后端仿真全能力）；'other' = 通用资源包场景（编排 → 孪生展示，本地静态核算）
    sceneBooted: false,          // 首屏场景是否已在 init 内装载（资源包场景直接开机到位，避免先按钢铁初始化再切换）
    sceneIndex: [],              // 后端场景注册表（/api/scenes：含 meta 与 ready/package 状态）
    sceneIndexTs: 0,             // 注册表刷新代数（供 UI 观察列表变化）
    scenePack: null,             // 当前场景资源包（{ meta, resources }）
    sceneTemplates: [],          // 包内预置模板（resources.templates：编排方案快照）
    sceneCtx: null,              // 包内通用字典上下文（dictionary/factors/paramSchema…），供非钢场景资源树/属性渲染
    sceneVersion: 0,             // 场景包装载代数：切换场景后自增，触发组件按新场景重建
    sceneBusy: false,            // 场景资源包装载/切换中
    sceneLoad: { active: false, phase: 'idle', error: '', seq: 0, startedAt: 0 }, // 3D 场景从数据到首帧的加载阶段
    scenarios: [
      { id: 'steel', label: t('钢铁') },
      { id: 'cement', label: t('水泥') },
      { id: 'chemical', label: t('化工') },
      { id: 'nonferrous', label: t('有色') },
      { id: 'other', label: t('其它') },
    ],
    envMode: 'industrial',      // 场景环境：void 虚空 / industrial 工业(默认) / desert 沙漠 / city 城市 / coast 海滩
    envModes: [
      { id: 'void', label: t('虚空') },
      { id: 'industrial', label: t('工业') },
      { id: 'desert', label: t('沙漠') },
      { id: 'city', label: t('城市') },
      { id: 'coast', label: t('海滩') },
    ],
    envNonce: 0,                // 触发中间 3D 场景切换环绕环境
    sceneRev: 0,
    factors: null,            // 当前排放因子配置（燃料 NCV/CC、电网因子、碳酸盐/电极因子），null 表示用后端默认
    factorsDefault: null,      // 排放因子默认基线（init 时快照），用于编辑态估算的偏移归零，保证未编辑时基线不变
    paramSchema: null,        // 工序参数分级元数据（后端 /api/param-schema）：config/optim + 参考范围
    deviceLibrary: null,      // 内置监测设备库（后端 /api/devices）：设备类型元数据 + 各工序设备规格 + 设备规格档位库
    deviceDetailId: null,     // 当前打开详情的设备 id（3D 图点设备或工序设备列表触发）
    focusNonce: 0,         // 触发中间 3D 相机聚焦（任意选中均发起）
    focusKind: null,        // 'unit' | 'device'
    focusId: null,
    viewNonce: 0,          // 触发中间 3D 以指定视角查看工序（俯视/正视/侧视/聚焦/全景）
    viewMode: 'focus',     // 'focus' | 'front' | 'side' | 'top' | 'overview'
    viewId: null,
    // 三栏布局 & 检视器状态
    // 左侧栏默认折叠：任何界面（三维孪生 / HMI / 各功能视图窗口）进入时都不自动展开，
    // 仅由用户手动点击活动栏按钮 / 顶栏开关 / 系统设置开关时才展开（与 2D 视图进入时的收起口径一致）
    leftOpen: false,          // 左侧栏是否展开（默认折叠）
    rightOpen: false,         // 右侧栏（检视器）是否展开（默认隐藏，点选资产/设备时自动展开）
    bottomOpen: false,        // 底栏（命令行）是否展开（默认隐藏，可由状态栏/命令入口展开）
    newsTickerOn: (() => { try { return localStorage.getItem('sim.newsTickerOn') !== '0' } catch (e) { return true } })(),  // 底栏快讯是否显示（默认开，localStorage 持久化）
    fullscreenOn: false,      // 全屏模式：隐藏左/右/底栏，仅保留 3D 场景
    // ---- 功能视图窗口（tab 化）：功能视图以窗口形式开在中间内容区，可同时打开多个并切换 ----
    // openViews / activeViewId 为唯一真源：
    //   openViews    —— 已打开视图 id 列表（tab 顺序），例：['boxManage', 'carbonMarket']
    //   activeViewId —— 当前激活视图 id，null 表示显示三维仿真场景（数字孪生）
    // 各视图的 xxxOn（dataViewOn / carbonMarketOn / ...）改为由 activeViewId 派生的 getter，兼容既有读取代码。
    openViews: [],
    activeViewId: null,
    // HMI人机交互屏：与 3D 数字孪生「对等」的主视图形态（不是功能视图窗口，不开 tab），
    // 二者共用中间内容区，由工具条「三维仿真 / HMI人机交互屏」按钮切换；切到 HMI 时回到主视图槽位。
    overviewOn: false,
    // AI 群控进入前右侧系统栏的开合备份：群控内容区自含左右两栏（训练前测试 | 训练相关设定），
    // 进入时收起外部右栏腾宽度，离开群控（切视图/返回孪生/关 tab）时由 App watch activeViewId 恢复
    grpRightBackup: null,
    // AI 群控内部页：'lib' 模型库 / 'mpc' MPC 控温优化（内置求解型） / 'edit' 编排。
    // 放在 store 里是为了让左侧「MPC控温模型」条目能高亮、也能从外部直接跳到 MPC 页；
    // 真正的页面状态仍由 PidControlView 持有，这里只是镜像。
    agcPage: 'lib',
    // MPC 页跳转令牌：外部入口把 token 加一，PidControlView 收到变化（或挂载时看到非 0）就切到 mpc 页。
    // openAiGroup() 会把它清零，保证「工具 → AI → AI群控」正常进入时落在模型库。
    agcMpcToken: 0,
    boxCloudSource: 'unknown',// 能碳一体机管理：云端连接状态（live / degraded / unknown），由 CarbonBoxView 轮询后写回
    inspectorView: 'auto',    // 右侧检视器显式视图：'auto'（按选中推导）| 'park' 园区构成 | 'materials' 原料库 | 'strategy' 减排策略 | 'report' 报告面板 | 'agent' 本析智擎对话
    reportPayload: null,      // 「导出报告」请求载荷（baseline/strategy/ops/...），供右侧报告面板消费
    selectedStrategyId: null, // 左侧策略库选中的策略
    deviceHistory: {},        // 各设备历史读数序列：devId -> [{t, v}]
    deviceLive: {},           // 各设备实时读数：devId -> number
    deviceSetpoints: {},      // 可调设备设定值覆盖：devId -> number（视图态/编辑态统一存储，驱动实时读数与碳引擎折算）
    // ── AI 群控运行态 ──
    agcRunId: '',             // 正在运行的群控模型 id（空 = 无）；由服务端存档恢复，跨端一致
    agcLast: {},              // 运行器每轮结果：modelId -> { ts, ok, acts, nodes[], edges[], branch }（供画布高亮）
    deviceExtraSetpoints: {}, // 可调设备附加可调项（如鼓风机鼓风湿度）：devId -> { key: number }
    deviceMeta: {},           // 设备元数据（后端 /api/devices/history 的 meta）
    dvSources: [],            // 工况数据分析数据源：从左侧「场景」资源树拖入的设备（对象数组，跨视图保留；拖回场景即移除）
    dvSelIds: [],             // 工况数据分析中间视图当前勾选的设备 id（右侧属性面板各算法的默认输入来源）
    cluK: 0,                  // 工况数据分析「聚类分析」分组簇数（0=自动），由右侧属性面板 ai::clu 统一配置
    // AI 优化模型（GA/PSO/RL 在线训练）：后端状态缓存 id -> state，轮询刷新展示「逐渐变优」
    optimizers: {},
    optimizerPolling: false,  // 是否已在轮询（模块级 timer 防重）
    optimizerAutoApplying: {},       // id -> bool：自动化控制下发中（防并发重复下发）
    optimizerSeenReminders: {},      // id:reminderId -> true：手动调优提醒去重（仅提醒一次）
    viewResetNonce: 0,   // 触发中间 3D 场景重置视角
    patrolOn: false,      // 虚拟巡视：小机器人沿工艺旁地面巡视完整流程
    // 工艺级策略管理：每个工序可绑定独立策略（自然语言 → 解析 → 测试 → 保存 → 绑定）
    unitStrategies: {},     // { [unitId]: { enabled, text, parsed, delta, scenarioName } }
    processStrategyEnabled: {},  // { [processType]: boolean } — 在左侧工艺列表中勾选
    // 实时数据源配置（连接面板/「连接数据源」设置：能碳一体机 MQTT 云端实时 / 模拟数据）
    dataSource: { type: 'sim', url: '', interval: 1000, name: '能碳一体机' },
    // MQTT 实时数据源状态（来自 /api/realtime/source）
    mqttSource: null,
    // ---- 左侧活动栏（VS Code 式）与多数据源管理 ----
    activityView: 'scene',      // 活动面板：'explorer' 资源 | 'search' 搜索 | 'scene' 场景（默认打开「场景」；AI 群控为独立视图，不占用活动面板）
    // 左栏各面板的显示开关（面板头右侧「⋯」菜单勾选）：scene 资源管理器 / explorer 资源 / search 搜索。
    // 勾选的面板按固定顺序（资源管理器 → 资源 → 搜索）自上而下依次显示在左栏中。
    sidePanelOn: { scene: true, explorer: true, search: true },
    dataSources: [],            // 多数据源列表，每个含 { id,type,url,interval,name,enabled,mapping }
    activeDataSourceId: 'sim',  // 当前活动数据源 id（状态栏/指令区使用的活动源）
    sourceStatus: {},           // 各数据源连接状态：sourceId -> 'init'|'open'|'closed'|'error'
    lastFields: {},             // 各数据源最近一次遥测收到的外部字段：sourceId -> string[]
    // 「数据源管理」（能碳一体机管理 → 数据源管理）中的传感器设备：附加设备绑定真实读数的数据源候选
    // 结构：[{ name, model, node, protocol, state, props: [{ name, unit, value, ts, invalid }] }]，5s 轮询刷新
    boxSourceDevices: [],
    // ---- 编辑态：节点编排方案 ----
    editMode: false,        // 是否处于流程编辑态（中间区显示节点画布）
    scheme: { nodes: [], connections: [], devices: [], groups: [], activeGroupId: null }, // 流程编排方案（groups：工艺设备小组；activeGroupId：当前子编排组 id）
    // 「已应用方案」：最近一次落盘（或显式载入）的编排快照，是 3D 数字孪生 / 2D 工艺图 / KPI / 设备树
    // 等所有「非编排界面」的唯一数据源（model 由它编译而来）。
    // 编排画布里改的是 scheme（草稿），未保存前绝不影响 appliedScheme —— 即未保存的编排不会泄漏到孪生。
    // 只有 saveScheme()（保存）或显式载入项目/模板/场景时才会同步 appliedScheme 并重新编译 model。
    appliedScheme: null,
    selectedFlowId: null,   // 画布中选中的节点 id
    selectedGroupId: null,  // 画布中选中的小组 id
    flowBackId: null,       // 属性面板跳转来源工艺节点 id（主工艺→分支辅助工艺后，面板显示「返回」）
    // 编排保存状态：手动保存模式下，任何编辑只置 schemeDirty=true（不落盘），
    // 由工具条「保存」按钮 / Ctrl+S 触发 saveScheme() 才写入本地存档 + 服务端 designs/flow。
    schemeDirty: false,
    schemeSavedAt: 0,       // 最近一次手动保存时间戳（ms）
    // AI 群控编排同样为手动保存（与流程编排同一口径）：Ctrl+S 由 App.vue 统一接，
    // 这里只是个自增的「保存请求」信号 —— AI 群控视图 watch 到变化即执行自己的落库，
    // 避免 App.vue 直接持有群控组件实例（视图是懒加载的，拿不到 ref）。
    agcSaveSeq: 0,

    // ---- 编排画布视图变换（缩放/平移）：提升为单一真源，供顶栏「编排」工具条驱动 ----
    flowTf: { scale: 1, tx: 40, ty: 30 },
    flowCanvasW: 0,         // 画布像素尺寸（FlowEditor 挂载时上报，供适配视图/缩放计算）
    flowCanvasH: 0,

    // ---- 节能减碳策略：以 processType 为 key，值为该工艺已启用的策略 id 集合 ----
    activeGreenStrategies: {},   // { [processType: string]: string[] }

    // ---- 仿真模式：进入时保存全量快照，所有编辑仅预览，退出时恢复 ----
    simMode: false,        // 是否处于仿真模式
    simBaseline: null,     // 仿真前的基线结果（供右上角对比浮层，before）
    simCurrent: null,      // 仿真模式下的当前结果（供对比浮层 after；随属性/策略变化实时更新，非仿真模式恒为 null）
    simOps: [],            // 仿真模式下当前生效的策略操作集合（属性修改重算时一并携带，使 after 始终反映 参数+策略）
    simChanges: [],        // 仿真模式下的变更记录（右上角「仿真前后对比」窗口左侧展示用户改了哪些内容）
    pendingSaveStrategy: false,  // 仿真模式：等待命令行输入策略名称

    // 左侧「原料」库选中查看（属性/配置），两栏联动
    selectedMaterialId: null,   // 选中的物料库 id
    // 左侧资源面板：浏览态选中（只看属性，不改动产线）
    selectedAssetType: null,    // 选中的工艺类型（PROCESS_TEMPLATES.type）-> 仅用于左侧目录高亮；面板始终为实例面板
    materialOverrides: {},      // 物料属性覆盖：matId -> { carbon, density, moisture, composition:{...}, blend:[{id,name,ratio,comp:{...}}] }（随方案持久化）
    // 碳市场参数（localStorage 独立持久化，非随方案）：企业年度碳配额（全国碳市场分配，免费+有偿，tCO₂/年，默认 2000 万吨）与实时碳价（元/t，默认 100，可按行情维护）
    carbonCfg: (() => {
      try {
        const v = JSON.parse(localStorage.getItem('sim.carbonCfg') || 'null')
        if (v && Number.isFinite(Number(v.allowance)) && Number.isFinite(Number(v.price))) {
          // 兼容旧 localStorage（碳价原存 元/tCO₂ 口径）：万元/tCO₂ 不可能 ≥1，≥1 视为旧元口径，÷1e4
          const price = Number(v.price) >= 1 ? Number(v.price) / 1e4 : Number(v.price)
          return { allowance: Number(v.allowance), price }
        }
      } catch (e) { /* 忽略损坏的存储值，回退默认 */ }
      return { allowance: 20000000, price: 0.01 }
    })(),
    // 撤销/重做栈（仅编辑态编排方案）
    historyPast: [],        // 历史快照（每次编辑前压入上一状态）
    historyFuture: [],      // 重做快照
    // 命令行窗口日志（全局共享：App 顶栏/按钮、ReportPanel 报告进度等均可推送）
    cmdLog: [],             // [{ t, k, ts }] k: cmd|out|sys|guide|tip|warn|err|bot|sim
    // 实时消息流（MQTT：云端 Broker → 平台），由「数据源管理」采集后并入底栏「输出」页签显示
    mqttLog: [],            // [{ ts, topic, payload }]，最多 MQTT_LOG_CAP 条
    // 系统通知中心（底栏铃铛）：{ id, level: 'info'|'success'|'warn'|'error', title, body, time, read }
    notifications: [],
  }),
  getters: {
    // 视图模式：非数字孪生的功能视图激活时（数据分析 / AI 群控 / 碳资产管理 / 碳排核算 / 能流分析 / 能碳一体机），
    // 顶栏工具栏按当前视图渲染（HMI人机交互屏与数字孪生同为主视图，不计入功能视图）
    viewModeOn: (s) => !!s.activeViewId,
    // 各功能视图激活态：由 activeViewId 派生（历史布尔开关的兼容读取口，不再单独存 state）
    // 流程编排：editMode 为「编排模式是否开启」，flowEditOn 为「编排画布 tab 是否在前台」；
    // 切到三维仿真 / 其它 tab 时编排模式保持（草稿不丢），仅画布隐藏 → 用 flowEditing 判断「画布可见」
    flowEditOn: (s) => s.activeViewId === 'flowEdit',
    flowEditing: (s) => s.editMode && s.activeViewId === 'flowEdit',
    dataViewOn: (s) => s.activeViewId === 'dataView',
    aiGroupOn: (s) => s.activeViewId === 'aiGroup',
    carbonMarketOn: (s) => s.activeViewId === 'carbonMarket',
    carbonCalcOn: (s) => s.activeViewId === 'carbonCalc',
    energyFlowOn: (s) => s.activeViewId === 'energyFlow',
    boxManageOn: (s) => s.activeViewId === 'boxManage',
    // 未读系统通知数（底栏铃铛徽标）
    unreadNotifs: (s) => s.notifications.filter((n) => !n.read).length,
    // 「本析智擎」：右侧检视器当前是否为智能体对话界面
    agentOn: (s) => s.inspectorView === 'agent',
    // 场景资源包元信息（当前打开场景的 meta；注册表未加载时回退到场景本地默认）
    currentSceneMeta: (s) => s.sceneIndex.find((x) => x.id === s.sceneId) || null,
    // 非钢铁场景（机房热控等通用资源包）：编排 → 孪生展示模式
    customSceneOn: (s) => s.sceneMode !== 'steel',
    // 当前场景的「工艺」轻量模板字典（场景包内 scheme 节点 type → 模板），供非钢资源树与拖拽建节点使用
    sceneProcessDict: (s) => {
      const dict = {}
      for (const tpl of s.sceneTemplates) {
        for (const n of (tpl.scheme && tpl.scheme.nodes) || []) {
          if (n.kind !== 'process' || dict[n.type]) continue
          dict[n.type] = {
            type: n.type,
            label: (n.name || n.type).replace(/(·.+)$/, ''),   // 「冷水机组·冷源」→「冷水机组」
            name: n.name,
            params: { ...(n.params || {}) },
            ports: n.ports ? JSON.parse(JSON.stringify(n.ports)) : null,
            route: tpl.id,
          }
        }
      }
      return dict
    },
    selectedUnit: (s) => s.model.units.find((u) => u.id === s.selectedUnitId) || null,
    selectedResult: (s) => {
      if (!s.selectedUnitId || !s.baseline) return null
      return s.baseline.units.find((u) => u.id === s.selectedUnitId) || null
    },
    // 某工序实例实际连线绑定的工辅类型（由编排画布中的物料连线决定，含上游链路传递）
    // 以「已应用方案」为准：未保存的草稿连线不算实际绑定（与 model / 孪生保持一致口径）
    linkedAuxOfUnit: (s) => (unitId) => linkedAuxTypesFor(s.appliedScheme || s.scheme, unitId),
    resultForView: (s) => s.strategy || s.baseline,
    liveUnit: (s) => (id) => (s.live && s.live.units ? s.live.units.find((u) => u.id === id) : null),
    // 某工序的内置监测设备（含实时读数），来自 baseline 仿真结果附带
    devicesForUnit: (s) => (id) => {
      if (!s.baseline || !s.baseline.units) return []
      const u = s.baseline.units.find((x) => x.id === id)
      return u ? (u.devices || []) : []
    },
    // 按设备 id 在全厂范围内查找设备实例（含其所属工序）。
    // 支持"可调设备"合成 id（工序::类型）：从所属工序实时合成，保证详情可打开。
    findDevice: (s) => (devId) => {
      if (!devId) return null
      // 非部署工艺的典型可调设备（id = tpl::工序类型::设备类型）
      if (devId.startsWith('tpl::')) {
        const [, unitType, dt] = devId.split('::')
        const tmpl = DEVICE_MAP[dt]
        if (!tmpl) return null
        const sp = (s.deviceSetpoints && s.deviceSetpoints[devId] != null) ? s.deviceSetpoints[devId]
          : (tmpl.setpoint ? tmpl.setpoint.def : null)
        // 附加可调项（如鼓风机鼓风湿度）
        const esStore = (s.deviceExtraSetpoints && s.deviceExtraSetpoints[devId]) || {}
        const extraSetpoints = {}
        if (tmpl.extraSetpoints && tmpl.extraSetpoints.length) {
          for (const es of tmpl.extraSetpoints) {
            extraSetpoints[es.key] = (esStore[es.key] != null) ? esStore[es.key] : es.def
          }
        }
        return {
          device: {
            id: devId, type: dt, label: tmpl.label || dt,
            unit: tmpl.unit, measures: tmpl.measures,
            measured: applySetpointResponse(sp, tmpl.response),
            deviation: (tmpl.response && tmpl.response.bias) || 0,
            color: '#0860A8', metering: false, adjustable: true,
            setpoint: sp, extraSetpoints,
            reading: sp,
            desc: `${tmpl.label}：${tmpl.desc || '本工序的可调设备，其设定值经碳引擎折算为运行电耗与间接排放，是减排策略的作用对象。'}`,
          },
          unitId: null,
          unitName: (PROCESS_MAP[unitType] || {}).label || unitType,
          unitType,
        }
      }
      // 附加设备（传感器/可变设备）：id = ext::工艺节点id::附加uid，从工艺节点实时合成
      if (devId.startsWith('ext::')) {
        const parts = devId.split('::')
        const nid = parts[1]
        const auid = parts[2]
        // 已应用方案优先（未保存的草稿设备不应在设备树/详情里出现），
        // 但编排中刚添加、尚未保存的附加设备要能打开详情，故以 scheme 兜底。
        const node = ((s.appliedScheme && s.appliedScheme.nodes) || []).find((x) => x.id === nid)
          || ((s.scheme && s.scheme.nodes) || []).find((x) => x.id === nid)
        const att = node && (node.attached || []).find((a) => a.uid === auid)
        if (!att) return null
        const u = ((s.baseline && s.baseline.units) || []).find((x) => x.id === nid)
        const dev = _extDevice(node, u, att, Date.now(), _boxSrcMap(s), s.deviceSetpoints)
        if (!dev) return null
        return { device: dev, unitId: nid, unitName: (u && u.name) || node.name, unitType: (u && u.type) || node.type }
      }
      if (!s.baseline || !s.baseline.units) return null
      for (const u of s.baseline.units) {
        const d = (u.devices || []).find((x) => x.id === devId)
        if (d) return { device: d, unitId: u.id, unitName: u.name, unitType: u.type }
      }
      // 合成可调设备（id = 工序::类型）
      if (devId.includes('::')) {
        const [uid0, dt] = devId.split('::')
        const u = s.baseline.units.find((x) => x.id === uid0)
        if (u) {
          const ad = _adjDevice(u, dt, s.deviceSetpoints, s.deviceExtraSetpoints)
          if (ad) return { device: ad, unitId: u.id, unitName: u.name, unitType: u.type }
        }
      }
      return null
    },
    deviceDetail: (s) => (s.deviceDetailId ? s.findDevice(s.deviceDetailId) : null),
    // 某工辅类型（鼓风机/热风炉等）的设备详情 devId：
    // 优先取「实际连线绑定」的工序实例视角（工序id::工辅类型，与工序属性面板「可调设备」一致，
    // 调节设定值经 _applyDeviceOpParams 桥接为工序参数，真实生效）；
    // 未连线绑定则取该工辅实例自身（工辅自身即可调设备）；均无返回 null。
    linkedAuxDeviceOf: (s) => (auxType) => {
      const units = (s.baseline && s.baseline.units) || []
      const unitIds = new Set(units.map((u) => u.id))
      const ap = s.appliedScheme || s.scheme
      const nodes = (ap && ap.nodes) || []
      const conns = (ap && ap.connections) || []
      const nodeById = {}
      for (const n of nodes) nodeById[n.id] = n
      for (const c of conns) {
        const f = nodeById[c.from], t = nodeById[c.to]
        if (!f || !t || !c.material) continue
        const ft = PROCESS_MAP[f.type], tt = PROCESS_MAP[t.type]
        if (!ft || !tt) continue
        if (ft.route === 'aux' && f.type === auxType && (ft.outputs || []).includes(c.material) && unitIds.has(t.id)) {
          return `${t.id}::${auxType}`
        }
        if (tt.route === 'aux' && t.type === auxType && (tt.outputs || []).includes(c.material) && unitIds.has(f.id)) {
          return `${f.id}::${auxType}`
        }
      }
      const u = units.find((x) => x.type === auxType)
      return u ? `${u.id}::${auxType}` : null
    },
    // 右侧检视器模式：显式视图（flow/park/materials/overview） > 策略详情 > 物料 > 设备 > 工序实例 > 总览
    // 工艺类型无独立属性面板，点击工艺一律跳转到实例面板（selectedUnitId），故此处不再有 assetType 分支
    inspectorMode: (s) => {
      if (s.inspectorView && s.inspectorView !== 'auto') return s.inspectorView
      if (s.selectedStrategyId) return 'strategyDetail'
      if (s.selectedMaterialId) return 'material'
      if (s.deviceDetailId) return 'device'
      if (s.selectedUnitId) return 'unit'
      return 'overview'
    },
    // 左侧策略库选中的策略对象（自定义策略、内置预置策略或工艺绿色策略）
    selectedStrategy: (s) => {
      if (!s.selectedStrategyId) return null
      const c = s.strategies.find((x) => x.id === s.selectedStrategyId)
      if (c) return c
      if (typeof s.selectedStrategyId === 'string' && s.selectedStrategyId.startsWith('green::')) {
        const parts = s.selectedStrategyId.split('::')
        const pt = parts[1], sid = parts[2]
        const t = PROCESS_TEMPLATES.find((x) => x.type === pt)
        const g = t && t.greenStrategies && t.greenStrategies.find((x) => x.id === sid)
        if (g) return {
          id: s.selectedStrategyId, sid, name: g.name, description: g.desc || '',
          saving: g.saving, carbon: g.carbon, tags: g.tags || [],
          processType: pt, processLabel: t.label,
          enabled: (s.activeGreenStrategies[pt] || []).includes(sid),
          source: 'green',
        }
        return null
      }
      if (typeof s.selectedStrategyId === 'string' && s.selectedStrategyId.startsWith('preset::')) {
        const i = Number(s.selectedStrategyId.slice(7))
        const p = s.presets[i]
        if (p) return { id: s.selectedStrategyId, name: p.name || '未命名策略', description: p.text || '', raw_text: p.text || '', ops: [], applied: !!p.applied, source: 'preset' }
      }
      if (s.selectedStrategyId === 'ai::overview') {
        return { id: 'ai::overview', name: 'AI优化模型', description: '按类别浏览系统内置 AI 优化模型（时序预测 / 参数优化 / 聚类分析），点击进入对应模型的训练属性面板。', source: 'ai-list' }
      }
      if (typeof s.selectedStrategyId === 'string' && s.selectedStrategyId.startsWith('ai::')) {
        const m = AI_MODEL_MAP[s.selectedStrategyId]
        if (m) {
          // 数据拟合面板结构独立（非参数下发型模型），使用独立来源渲染
          const src = s.selectedStrategyId === 'ai::fit' ? 'ai-fit' : 'ai'
          return { id: s.selectedStrategyId, name: m.name, description: m.desc, source: src }
        }
      }
      return null
    },
    // 选中的物料库条目（来自 MATERIAL_MAP）
    selectedMaterial: (s) => (s.selectedMaterialId ? MATERIAL_MAP[s.selectedMaterialId] || null : null),
    // 全厂扁平设备列表（含实时读数/历史，供左侧设备树与总览使用），按工序分组在面板内完成。
    // 包含后端下发的"计量设备"与本系统按工艺合成的"可调设备"，并标注 metering/adjustable 区分。
    allDevices: (s) => {
      const out = []
      if (!s.baseline || !s.baseline.units) return out
      for (const u of s.baseline.units) {
        for (const d of (u.devices || [])) {
          out.push({
            ...d,
            unitId: u.id,
            unitName: u.name,
            unitType: u.type,
            live: s.deviceLive[d.id] != null ? s.deviceLive[d.id] : d.reading,
            history: s.deviceHistory[d.id] || [],
          })
        }
        // 合成该工序的可调设备：仅基础清单。鼓风机等工辅不在工艺的设备子项中列出
        // （工辅仅在「工辅」分组出现；其与工序的绑定关系在工艺属性面板中按连线展示）
        const adj = PROCESS_ADJUSTABLE[u.type] || []
        for (const dt of adj) {
          const ad = _adjDevice(u, dt, s.deviceSetpoints, s.deviceExtraSetpoints)
          if (!ad) continue
          out.push({
            ...ad,
            unitId: u.id,
            unitName: u.name,
            unitType: u.type,
            live: s.deviceLive[ad.id] != null ? s.deviceLive[ad.id] : ad.reading,
            history: s.deviceHistory[ad.id] || [],
          })
        }
      }
      // 附加设备（传感器 / 可变设备）：挂在具体工艺节点 node.attached[] 上，
      // 附加后该工艺在资源 / 设备树 / 数据分析中即出现对应设备（数值来源可按需解析）
      const srcMap = _boxSrcMap(s)
      const nowMs = Date.now()
      // 附加设备取「已应用方案」：编排中新增/改名的附加设备保存后才会进入设备树与数据分析
      for (const n of ((s.appliedScheme || s.scheme) && (s.appliedScheme || s.scheme).nodes) || []) {
        for (const att of (n.attached || [])) {
          const u = ((s.baseline && s.baseline.units) || []).find((x) => x.id === n.id)
          const dev = _extDevice(n, u, att, nowMs, srcMap, s.deviceSetpoints)
          if (!dev) continue
          out.push({
            ...dev,
            live: s.deviceLive[dev.id] != null ? s.deviceLive[dev.id] : dev.reading,
            history: s.deviceHistory[dev.id] || [],
          })
        }
      }
      return out
    },
    deviceHistoryOf: (s) => (id) => s.deviceHistory[id] || [],
    deviceLiveOf: (s) => (id) => (s.deviceLive[id] != null ? s.deviceLive[id] : null),
    // 「数据源管理」中的传感器设备（按设备分组，组内为点位）——附加设备数值来源下拉用。
    // 数据源 = 能碳一体机管理中已接入的设备（/box/devices 定义 + /box/devices/realtime 实时读数）。
    boxSourceGroups: (s) => (s.boxSourceDevices || []).map((d) => ({
      name: d.name,
      model: d.model,
      node: d.node,
      state: d.state,
      props: d.props || [],
    })),
    // 具有可写点位（writes[] / accessMode=rw）的数据源设备——编排可变设备绑定「写设定」目标下拉用
    boxWritableGroups: (s) => (s.boxSourceDevices || [])
      .filter((d) => (d.writes || []).length)
      .map((d) => ({ name: d.name, node: d.node, state: d.state, writes: d.writes })),
    // 某工艺节点可绑定的「数值来源」候选：工艺自身数值参数 + 固定值 + 模拟（供附加设备绑定下拉）
    attachSourceOptions: (s) => (nodeId) => {
      // 已应用方案优先，编排中新增（未保存）的节点以 scheme 兜底，保证编辑态下拉可用
      const node = ((s.appliedScheme && s.appliedScheme.nodes) || []).find((n) => n.id === nodeId)
        || ((s.scheme && s.scheme.nodes) || []).find((n) => n.id === nodeId)
      if (!node) return []
      const opts = [
        { value: 'sim', label: '模拟数据（缓变）' },
        { value: 'fixed', label: '固定值（模板默认）' },
      ]
      const params = node.params || {}
      const t = PROCESS_MAP[node.type]
      const plist = (t && Array.isArray(t.params)) ? t.params : []
      for (const key of Object.keys(params)) {
        const v = params[key]
        const isNum = typeof v === 'number' || (typeof v === 'string' && v !== '' && !isNaN(Number(v)))
        if (!isNum) continue
        const p = plist.find((x) => x.key === key)
        const label = (p && p.label) ? p.label : key
        opts.push({ value: 'param', param: key, label: `工艺参数：${label}（${key}）` })
      }
      return opts
    },
    // ---- 编辑态：选中节点 / 小组 / 方案估算 ----
    selectedFlowNode: (s) => s.scheme.nodes.find((n) => n.id === s.selectedFlowId) || null,
    selectedGroup: (s) => (s.selectedGroupId ? s.scheme.groups.find((g) => g.id === s.selectedGroupId) || null : null),
    schemeResult: (s) => computeScheme(s.scheme, s.factors, s.factorsDefault, s.materialOverrides),
    schemeTotals: (s) => computeScheme(s.scheme, s.factors, s.factorsDefault, s.materialOverrides).totals,
    // 「已应用方案」口径的估算总量：供 HMI 大屏等**非编排界面**使用 ——
    // 未保存的编排草稿不得改变这些界面的读数（保存后 appliedScheme 同步才会跟着变）。
    appliedTotals: (s) => computeScheme(s.appliedScheme || s.scheme, s.factors, s.factorsDefault, s.materialOverrides).totals,
    // 撤销/重做可用性
    canUndo: (s) => s.historyPast.length > 0,
    canRedo: (s) => s.historyFuture.length > 0,
  },
  actions: {
    // 命令行窗口：追加一条日志（k：cmd 命令回显 / out·sys 一般信息 / guide 引导输入 / tip 提醒 / warn·err 警告报错 / bot 聊天 / sim 仿真记录）
    pushCmd(msg, k = 'out') { this.cmdLog.push({ t: msg, k, ts: Date.now() }) },
    clearCmdLog() { this.cmdLog = []; this.mqttLog = [] },
    // 实时消息流：增量并入底栏「输出」。入参为后端返回的最近消息（按时间升序），
    // 按 ts+topic+payload 去重（轮询每 3s 一次，同一条消息会被重复拉到），避免刷屏重复行
    syncMqttLog(list) {
      if (!Array.isArray(list) || !list.length) return 0
      const seen = new Set(this.mqttLog.map((m) => `${m.ts}|${m.topic}|${m.payload}`))
      let added = 0
      for (const m of list) {
        if (!m) continue
        const ts = Number(m.t || m.ts || 0)
        const topic = String(m.topic || '')
        const payload = String(m.payload == null ? '' : m.payload)
        const key = `${ts}|${topic}|${payload}`
        if (seen.has(key)) continue
        seen.add(key)
        this.mqttLog.push({ ts, topic, payload })
        added++
      }
      if (this.mqttLog.length > MQTT_LOG_CAP) this.mqttLog.splice(0, this.mqttLog.length - MQTT_LOG_CAP)
      return added
    },
    // —— 系统通知中心（底栏铃铛）——
    // 新增一条系统通知，自动附带 toast 提示；列表最多保留 50 条
    notify(level = 'info', title = '', body = '') {
      const n = { id: uid('ntf'), level, title, body, time: Date.now(), read: false }
      this.notifications.push(n)
      if (this.notifications.length > 50) this.notifications.splice(0, this.notifications.length - 50)
      return n.id
    },
    // 类型化 Toast（ToastLayer 渲染，3.4s 自动消失）：type = success / info / warn / error
    showToast(msg, type = 'info') {
      this.toast = msg
      this.toastType = type
    },
    beginSceneLoad(phase = 'data') {
      const seq = Number(this.sceneLoad && this.sceneLoad.seq || 0) + 1
      this.sceneLoad = { active: true, phase, error: '', seq, startedAt: Date.now() }
      return seq
    },
    setSceneLoadPhase(phase, seq = null) {
      if (seq != null && seq !== this.sceneLoad.seq) return false
      if (!this.sceneLoad.active) return this.beginSceneLoad(phase)
      this.sceneLoad = { ...this.sceneLoad, active: true, phase, error: '' }
      return this.sceneLoad.seq
    },
    finishSceneLoad(seq = null) {
      if (seq != null && seq !== this.sceneLoad.seq) return false
      this.sceneLoad = { ...this.sceneLoad, active: false, phase: 'ready', error: '' }
      return true
    },
    failSceneLoad(error, seq = null) {
      if (seq != null && seq !== this.sceneLoad.seq) return false
      this.sceneLoad = { ...this.sceneLoad, active: false, phase: 'error', error: String(error || '') }
      return true
    },
    // 「保存 AI 群控编排」请求信号（Ctrl+S / 菜单）：自增即触发，由 PidControlView 监听执行。
    // 用信号而非直接调用，是因为 AI 群控视图是懒加载的，App.vue 拿不到它的实例。
    requestAgcSave() { this.agcSaveSeq++ },
    // 确认弹窗（ConfirmDialog 渲染）：返回 Promise<boolean>
    confirm({ title, message, okText = t('确定'), cancelText = t('取消'), danger = false } = {}) {
      this.confirmDialog = { open: true, title, message, okText, cancelText, danger }
      return new Promise((resolve) => { this._confirmResolver = resolve })
    },
    // ConfirmDialog 回调：确认 true / 取消 false，并解除挂起 Promise
    confirmResolve(val) {
      this.confirmDialog.open = false
      if (this._confirmResolver) {
        const r = this._confirmResolver
        this._confirmResolver = null
        r(val)
      }
    },
    markNotificationRead(id) {
      const n = this.notifications.find((x) => x.id === id)
      if (n) n.read = true
    },
    markAllNotificationsRead() { this.notifications.forEach((n) => { n.read = true }) },
    removeNotification(id) { this.notifications = this.notifications.filter((x) => x.id !== id) },
    clearNotifications() { this.notifications = [] },
    async init() {
      try {
        this._loadWelcomeState()   // 是否停在「工程选择」欢迎页 + 最近工程列表（同步，先于任何场景装载）
        if (!this.welcomeOn) this.beginSceneLoad('data')
        loadCalibrations()   // 启动即恢复本厂标定耦合（localStorage），否则用默认机理/经验系数
        this._loadDataSource() // 恢复上次设置的实时数据源（平台 MQTT 实时 / 自定义 WS / HTTP）
        this._startMqttPolling() // 定时拉取 MQTT 数据源状态（连接状态/订阅主题/最近消息）
        // 场景注册表（/api/scenes）：首屏即拉取 —— 左栏第一个模块标题、AI 群控的场景标记
        // 都要用场景**显示名**；此前只由「设置 → 场景」/「打开场景」弹窗拉取，首屏会退化成场景 id
        await this.refreshSceneIndex()
        // 「数据源管理」中的传感器设备：附加设备绑定真实读数的数据源候选（首次加载 + 常驻轮询）
        this.loadBoxSourceDevices()
        this._startBoxSourcePolling()
        const [m, presets, factors, schema, devs] = await Promise.all([
          api.presetModel(), api.presetStrategies(), api.getFactors(), api.getParamSchema(),
          api.getDevices(),
        ])
        this.model = m
        // 首屏场景：上次打开的是资源包场景（如机房温控）时，在初始化阶段**直接装载该场景**，
        // 不再先按钢铁构建默认流程再切换 —— 后者会让首屏先渲染一遍钢铁流程（用户看到「闪一下钢铁」），
        // 还会多打一次钢铁碳引擎仿真、多弹出一次钢铁「系统就绪」提示。
        const bootId = await this._bootSceneId()
        const booted = bootId ? await this.openScene(bootId) : false
        this.sceneBooted = booted
        if (!booted) {
          // 默认钢铁启动路径：_bootSceneId() 对 steel 返回 null，openScene 从未调用，
          // 资源包未装载 → 补装载包元数据（长/短流程模板等），否则编排工具条模板按钮不显示
          await this._loadScenePackMeta(this.sceneId || 'steel')
          await this._restoreSchemeSession()
        }
        if (booted) {
          // 场景包自带的排放因子 / 参数元数据 / 设备库已由 openScene 装载，缺失时才回落到平台默认
          if (this.factors == null) this.factors = factors
          if (this.factorsDefault == null) this.factorsDefault = factors
          if (!this.paramSchema) this.paramSchema = schema
          if (!this.deviceLibrary) this.deviceLibrary = devs
        } else {
          this.factors = factors   // 默认排放因子，供详情弹窗与因子配置面板使用
          this.factorsDefault = factors   // 快照默认基线，供编辑态估算偏移归零
          this.paramSchema = schema   // 工序参数分级元数据，供流程编排编辑器分组与参考范围展示
          this.deviceLibrary = devs   // 内置监测设备库，供 3D 设备标记、设备详情面板与规格档位联动
          // 设备历史只供趋势面板使用，不阻塞模型、核算和 3D 首帧。
          const historySceneId = this.sceneId
          api.getDeviceHistory().then((hist) => {
            if (this.sceneId !== historySceneId) return
            if (hist && hist.history) this.deviceHistory = hist.history
            if (hist && hist.meta) this.deviceMeta = hist.meta
          }).catch(() => {})
          this.autoLayout()        // 初次加载先按序等距自动布局，避免工艺图标重叠
        }
        this.presets = booted ? this.presets : presets   // 资源包场景无策略库（openScene 已清空）
        if (!booted) {
          this.setSceneLoadPhase('calculate')
          await this._runRefresh()
        }  // openScene 已完成资源包场景核算，避免启动时重复编译/请求
        if (!booted) this.loadStrategies().catch(() => {})
        this.ready = true
        this._bindSchemeDirty() // 编排改动检测：只置「未保存」标记，编辑内容一律不写服务端
        this._purgeLocalDesignCache() // 清理历史遗留的编排 / 群控本地副本（会以本地旧档盖住服务端真源）
        // 不做跨端自动同步：谁保存谁写入服务端，另一端刷新（打开工程 / 切场景）时才取最新，
        // 两端同时编辑同一份编排时「最后保存的覆盖之前的」（last-writer-wins）。
        // 停在欢迎页时不必播报「系统就绪」：工程尚未打开，等用户选完工程进入主界面再提示
        if (!this.welcomeOn) this.notify('success', t('系统就绪'), t('数字孪生已载入 {units} 个工序、{flows} 条物流，实时链路与优化模型已就绪。', { units: this.model.units.length, flows: this.model.flows.length }))
        this._startFeed()
        // AI 优化模型：同步训练上下文并轮询状态（后台定时训练由后端调度，前端展示「逐渐变优」）
        this.syncOptimizerContext().then(() => this.refreshOptimizers())
        this.startOptimizerPolling()
        // 收尾：非资源包场景这条路径（booted=false）此前只推进到 calculate 阶段就再没人收尾，
        // 底栏加载指示会一直停在「正在计算场景数据…」。资源包路径 openScene 已自行收尾，此处幂等。
        this.finishSceneLoad()
        return true
      } catch (e) {
        this.toast = t('初始化失败：') + e.message
        this.notify('error', t('初始化失败'), e.message)
        return false
      }
    },
    // 当前工程由三者决定，优先级：URL ?scene= > 服务端全局「最后打开的工程」 > 本机 localStorage。
    // 之所以把服务端那份提到本机之前：平台没有用户体系，官网就是所有人共用的一个工作区 ——
    // 只看 localStorage 会让「别人 / 别的浏览器在机房温控下建的策略，换台电脑就看不到」。
    _urlScene() {
      try {
        const q = new URLSearchParams(window.location.search).get('scene')
        return (q || '').trim() || ''
      } catch (e) { return '' }
    },
    _sceneReady(id) {
      if (!id) return false
      const meta = this.sceneIndex.find((x) => x.id === id)
      return !!(meta && meta.ready)
    },
    // 启动首屏场景：优先 URL / 服务端记录的工程；都没有再看本机 localStorage。
    // 仅当它是**非钢资源包且已就绪**时返回其 id；钢包 / 未安装 / 不可用时返回 null（走原钢铁默认启动）。
    // 目的：让资源包场景（机房温控等）在初始化阶段一次装载到位，避免先按钢铁初始化再切换。
    async _bootSceneId() {
      if (!this.sceneIndex.length) await this.refreshSceneIndex()
      // ① URL 指定（https://.../sim/?scene=dc-thermal）：分享 / 收藏链接直达同一个工程
      const fromUrl = this._urlScene()
      if (fromUrl) {
        if (!this._sceneReady(fromUrl)) {
          this.pushCmd(t('链接指定的场景「{id}」未就绪或不存在，已按默认场景启动。', { id: fromUrl }), 'sys')
          return null
        }
        return fromUrl
      }
      // ② 服务端全局记录：任何人最后一次打开的工程（官网为真源，所有人共用）
      try {
        const r = await api.workspaceLastScene()
        const s = (r && r.data && r.data.scene) || ''
        if (s && s !== 'steel' && s !== this.sceneId && this._sceneReady(s)) return s
      } catch (e) { /* 服务端不可用时退回本机记录 */ }
      // ③ 本机兜底
      if (this.welcomeOn) return null   // 欢迎页：等用户在工程选择里显式打开
      let last = null
      try { last = localStorage.getItem('sim.sceneId') } catch (e) { return null }
      if (!last || last === 'steel' || last === this.sceneId) return null
      const meta = this.sceneIndex.find((x) => x.id === last)
      if (!meta || !meta.ready) return null
      return last
    },
    // 补装载当前场景资源包的「展示用元数据」：scenePack / sceneTemplates / sceneCtx。
    // 默认钢铁启动路径下 _bootSceneId() 返回 null（steel 不触发 openScene），资源包从未装载，
    // sceneTemplates 恒为空 → 编排工具条的长/短流程模板按钮不显示（hasTemplate 判定失败）。
    // 这里只填元数据，不重置任何会话状态（区别于 openScene 的整场景切换）。
    async _loadScenePackMeta(sceneId) {
      try {
        const pkg = await api.getSceneResource(sceneId || this.sceneId || 'steel')
        if (!pkg || !pkg.meta) return false
        this.scenePack = pkg
        const res = pkg.resources || {}
        this.sceneTemplates = Array.isArray(res.templates) ? res.templates : []
        if (!this.sceneCtx) this.sceneCtx = res.dictionary || res.config || null
        registerSceneMaterials(this.sceneCtx)
        return true
      } catch (e) { /* 后端不可用时静默：模板按钮按 routes 兜底 */ return false }
    },
    // 恢复上次保存的编排方案（钢铁默认启动路径）：
    // 编排单一真源：只认服务端存档（本地不留存任何副本）；无存档时按默认路线构建，避免刷新后回退。
    async _restoreSchemeSession() {
      const saved = await this._pullScheme(this.sceneId || 'steel')
      if (saved) {
        this.scheme = this._adoptScheme(saved.scheme, saved.sceneId || this.sceneId)
        migrateLegacyDevices(this.scheme)   // 存量方案：旧可调设备 -> 独立工辅节点 + 驱动连线
        // 迁移：旧版炉料结构绝对值（烧结 1270/球团 195/块矿 160 kg/t）-> 百分比配比 + 总矿量
        // 识别特征：高炉节点存在 sinter_ratio 且 >100（旧绝对值）；换算保留相对比例，一次性写回并重存
        const bfNode = (this.scheme.nodes || []).find((n) => n && n.id === 'blast_furnace' && n.params)
        if (bfNode && bfNode.params.sinter_pct == null && bfNode.params.sinter_ratio != null && Number(bfNode.params.sinter_ratio) > 100) {
          const s = Number(bfNode.params.sinter_ratio) || 0
          const pe = Number(bfNode.params.pellet_ratio) || 0
          const lu = Number(bfNode.params.lump_ratio) || 0
          const tot = s + pe + lu
          if (tot > 0) {
            bfNode.params.sinter_pct = Math.round((s / tot) * 1000) / 10
            bfNode.params.pellet_pct = Math.round((pe / tot) * 1000) / 10
            bfNode.params.lump_pct = Math.round((lu / tot) * 1000) / 10
            bfNode.params.burden_total = Math.round(tot)
            delete bfNode.params.sinter_ratio
            delete bfNode.params.pellet_ratio
            delete bfNode.params.lump_ratio
            this._saveScheme()   // 旧档格式迁移：一次性换算写回存档（非用户编辑，不属于自动保存）
          }
        }
        // 迁移：彻底移除历史方案中的旧 facility 节点（旧「工辅/设施」概念已删除，仅处理存量数据）
        const kept = new Set((this.scheme.nodes || []).filter((n) => n && n.kind !== 'facility').map((n) => n.id))
        this.scheme.nodes = this.scheme.nodes.filter((n) => n && n.kind !== 'facility')
        this.scheme.connections = (this.scheme.connections || []).filter((c) => kept.has(c.from) && kept.has(c.to))
        this.processRoute = saved.route || this.processRoute
        // 同步恢复物料属性覆盖（隐含碳因子/密度/含水率/详细化学成分），旧方案无该字段时保持默认
        if (saved.materialOverrides && typeof saved.materialOverrides === 'object') {
          // 迁移：v1 之前 price/salePrice 存的是「元/单位」，统一口径后 ÷1e4 转为「万元/单位」
          if (saved._ovUnitV !== 1) {
            const migrated = {}
            for (const [id, ov] of Object.entries(saved.materialOverrides)) {
              const m = { ...ov }
              if (typeof m.price === 'number') m.price = m.price / 1e4
              if (typeof m.salePrice === 'number') m.salePrice = m.salePrice / 1e4
              migrated[id] = m
            }
            this.materialOverrides = migrated
          } else {
            this.materialOverrides = saved.materialOverrides
          }
        }
        // 同步恢复设备设定值（视图态/编辑态统一存储，驱动实时读数与碳引擎折算）
        // 附加设备（ext::节点id::attUid）不在 scheme.devices 里，其设定值/写入值只能来自存档的
        // deviceSetpoints —— 缺这一段则刷新后附加传感 / 可变设备的调节值全部回落到模板默认值。
        this._restoreSetpoints(saved)
        this._syncAppliedScheme()   // 恢复的存档即最终态：同步为已应用方案后再编译
        this.compileSchemeToModel()
        this.autoLayout()
      } else {
        // 无存档（empty）按默认长流程构建属正常；读取失败（error）必须让用户知道：
        // 否则画面看着就是「编排被重置成默认」，而线上存档其实还在。
        if (_designPullState === 'error') {
          this.pushCmd(t('服务端编排存档读取失败：当前按默认长流程显示，且不会写入服务端（线上存档未被覆盖），请刷新页面重试。'), 'sys')
        }
        this._setDefaultRoute('long')
      }
    },
    openAbout() { this.aboutDialog = true },
    closeAbout() { this.aboutDialog = false },
    // 把"合成可调设备"的设定值按 DEVICE_COUPLE_REGISTRY 推导为各工序参数，
    // 注入模型副本（不污染源 model）。设备设定值优先（实际装备工况即运行点）。
    _applyDeviceOpParams(model) {
      if (!model || !model.units) return model
      // 统一浅拷贝一层 params，避免后续传导/桥接污染源 model
      const units = model.units.map((u) => ({ ...u, params: { ...(u.params || {}) } }))
      // 1) 驱动连线传导：工辅（热风炉/鼓风机/引风机/喷吹…）自身运行参数经物料连线
      //    写入被服务工艺的目标参数（与 compileSchemeToModel 的驱动折算段一致，见 flows 段）。
      //    此前 refresh 路径缺失此步——用户在仿真中调热风炉「送风温度」等工辅参数后，
      //    不会传导到高炉 hot_blast_temp，后端读到旧风温，碳排/能耗对比自然无变化。
      // 驱动连线以「已应用方案」为准：model 由 appliedScheme 编译而来，未保存的草稿连线
      // 不能参与折算（否则保存前刷新就会按草稿驱动已生效的工序参数）。
      const src = this.appliedScheme || this.scheme
      const nodeById = Object.fromEntries((src.nodes || []).map((n) => [n.id, n]))
      const unitById = Object.fromEntries(units.map((u) => [u.id, u]))
      for (const c of (src.connections || [])) {
        const f = nodeById[c.from], t = nodeById[c.to]
        const ft = f && PROCESS_MAP[f.type]
        if (!ft || !ft.drives) continue
        const drive = ft.drives[c.material]
        if (!drive) continue
        const srcUnit = unitById[f.id], dstUnit = unitById[t.id]
        if (!srcUnit || !dstUnit) continue
        const srcVal = (srcUnit.params && srcUnit.params[drive.src] != null) ? Number(srcUnit.params[drive.src]) : null
        if (srcVal != null) {
          // 驱动连线：工辅供给绝对量直接写入同量纲目标参数（如 热风温度℃ → 高炉热风温度℃）。
          // 例外：喷吹系统 inj_rate 为绝对量(t/h) → 高炉 coal_inj 为相对量(kg/t)，按铁水产量折算
          const hm = dstUnit.params && dstUnit.params.hot_metal != null ? Number(dstUnit.params.hot_metal) : null
          let driveVal = srcVal
          if (drive.dst === 'coal_inj' && drive.src === 'inj_rate' && hm && hm > 0) driveVal = (srcVal * 1000) / hm
          dstUnit.params = { ...(dstUnit.params || {}), [drive.dst]: driveVal }
        }
      }
      // 2) 设备设定值桥接（DEVICE_COUPLE_REGISTRY）：设备设定优先（实际装备工况即运行点）
      for (let i = 0; i < units.length; i++) {
        const u = units[i]
        const reg = DEVICE_COUPLE_REGISTRY[u.type]
        if (!reg) continue
        // 工辅类设备须由编排连线绑定才桥接其设定值（未连线即未绑定、不生效）；
        // 非工辅可调设备（变频/除尘风机等）照常桥接。
        const linkedAux = new Set(linkedAuxTypesFor(src, u.id))
        const devs = Object.keys(reg)
          .filter((dt) => {
            const pm = PROCESS_MAP[dt]
            return !(pm && pm.route === 'aux') || linkedAux.has(dt)
          })
          .map((dt) => {
            const sp = this.deviceSetpoints[`${u.id}::${dt}`]
            const es = this.deviceExtraSetpoints[`${u.id}::${dt}`]
            // 计算以设定值为准：设定值即运行工况（输入框中的数字），不经设备响应特性折算
            return (sp != null || (es && Object.keys(es).length))
              ? { type: dt, setpoint: sp, extraSetpoints: es || {} }
              : null
          })
          .filter(Boolean)
        const overrides = deriveProcessOpParams(u.type, devs, u.params || {})
        if (Object.keys(overrides).length) {
          units[i] = { ...u, params: { ...(u.params || {}), ...overrides } }
        }
      }
      return { ...model, units }
    },
    // 刷新防抖：滑块/设备设定拖动会高频触发，合并为「停顿后一次」后端重算（约 280ms），
    // 本地参数/设定值已即时更新保证跟手，避免每次输入都打全量仿真请求（卡顿与时延根因）。
    async _runRefresh() {
      // 通用资源包场景（其它分组）：无后端碳引擎，走本地静态核算刷新
      if (this.sceneMode !== 'steel') {
        this._otherSceneRefresh()
        return
      }
      const seq = ++_refreshSeq
      // 仿真模式下：属性修改后连同当前生效策略一起重算，保证「仿真前后对比」after 实时反映 参数+策略
      const ops = this.simMode ? (this.simOps || []) : []
      const r = await api.simulate(this._applyDeviceOpParams(this.model), ops, this.factors)
      if (seq !== _refreshSeq) return  // 已有更新的刷新在进行，丢弃本次过期结果
      this.baseline = r.baseline
      if (this.simMode) {
        const after = ops.length ? (r.strategy || r.baseline) : r.baseline
        this.simCurrent = after ? JSON.parse(JSON.stringify(after)) : null
        // 同步 strategy/delta：仿真模式下让 3D/KPI 也实时跟随当前参数+策略，避免策略快照冻结
        this.strategy = ops.length ? (r.strategy || r.baseline) : null
        this.delta = ops.length ? (r.delta || null) : null
      }
      this._pushModelToFeed()
    },
    refresh() {
      // 通用资源包场景（其它分组）：本地静态核算，无网络请求（可频繁调用）
      if (this.sceneMode !== 'steel') {
        if (_refreshTimer) clearTimeout(_refreshTimer)
        _refreshTimer = null
        this._otherSceneRefresh()
        return
      }
      if (_refreshTimer) clearTimeout(_refreshTimer)
      _refreshTimer = setTimeout(() => { _refreshTimer = null; this._runRefresh() }, 280)
    },
    async parse(text) {
      this.parsedText = text
      this.parsing = true
      try {
        this.parsed = await api.parse(text, this.model)
      } finally {
        this.parsing = false
      }
      return this.parsed
    },
    async runExperiment() {
      if (!this.parsed || !this.parsed.ops.length) {
        this.toast = t('请先输入并解析策略')
        return
      }
      this.busy = true
      try {
        const r = await api.simulate(this._applyDeviceOpParams(this.model), this.parsed.ops, this.factors)
        this.strategy = r.strategy
        this.delta = r.delta
        if (this.simMode) {
          // 仿真模式：记录当前生效策略 ops，后续属性修改重算时一并携带，使对比 after 持续实时
          this.simOps = JSON.parse(JSON.stringify(this.parsed.ops || []))
          this.simCurrent = r.strategy ? JSON.parse(JSON.stringify(r.strategy)) : null
          this._simLog('strategy', t('策略仿真'), (this.parsedText || '').slice(0, 60) || t('应用 {n} 项操作', { n: this.parsed.ops.length }), 'exp')
        }
        this.sceneRev++   // 触发中间孪生平台随之变化（重算热力着色/CO2 占比）
      } finally {
        this.busy = false
      }
    },
    // 清除策略实验状态。silent=true：不重置 simCurrent、不记录「清除策略」——
    // 用于「应用策略 / 应用 AI 最优参数」这类参数已落地模型的场景，
    // 由调用方自行以应用后结果刷新 simCurrent，避免对比窗口出现矛盾的「清除策略」记录。
    clearExperiment(silent = false) {
      this.strategy = null
      this.delta = null
      this.simOps = []
      if (this.simMode && !silent) {
        this.simCurrent = this.baseline ? JSON.parse(JSON.stringify(this.baseline)) : null
        this._simLog('strategy', t('清除策略'), t('恢复当前参数下的基线结果'))
      }
      this.sceneRev++   // 切换回基线后，孪生平台同步恢复
    },
    // ==================== AI 优化模型（GA / PSO / RL 在线训练） ====================
    // 把当前流程（含设备桥接参数）同步为后端训练上下文；流程实质变化时后端自动重建训练任务。
    async syncOptimizerContext() {
      try {
        await api.optimizerContext(this._applyDeviceOpParams(this.model), this.factors)
      } catch (e) { /* 后端未就绪时静默，后续操作会再同步 */ }
    },
    // 拉取全部优化模型训练状态（轮询用，展示迭代/曲线/最优参数随实时数据逐渐变优）
    async refreshOptimizers() {
      try {
        const r = await api.listOptimizers()
        if (!r || !Array.isArray(r.models)) return
        const map = {}
        for (const m of r.models) map[m.id] = m
        this.optimizers = map
        // ---- 控制模式副作用：自动化控制自动下发 / 手动模式系统提醒 ----
        for (const m of r.models) {
          if (m.auto_control && m.pending_auto_apply && !this.optimizerAutoApplying[m.id]) {
            this._autoApplyOptimizer(m.id)   // 后台异步下发，不阻塞轮询
          } else if (!m.auto_control && m.reminder && m.reminder.id) {
            const rk = `${m.id}:${m.reminder.id}`
            if (!this.optimizerSeenReminders[rk]) {
              this.optimizerSeenReminders = { ...this.optimizerSeenReminders, [rk]: true }
              this.toast = t('「{model}」训练取得新进展：最优强度 {fitness} kgCO₂/t（较上版提升 {pct}%）。已生成调优提醒，可在属性面板手动应用优化参数', { model: (AI_MODEL_MAP[m.id] || {}).name || '优化模型', fitness: m.reminder.best_fitness, pct: m.reminder.improvement_pct })
              this.notify('info', t('「{model}」训练新进展', { model: (AI_MODEL_MAP[m.id] || {}).name || '优化模型' }), t('最优强度 {fitness} kgCO₂/t，较上版提升 {pct}%。可在属性面板手动应用优化参数。', { fitness: m.reminder.best_fitness, pct: m.reminder.improvement_pct }))
            }
          }
        }
      } catch (e) { /* 后端未就绪时静默，下轮重试 */ }
    },
    // 自动化控制：模型变优后自动把新版本参数下发到可调设备（一次轮询仅触发一次）
    async _autoApplyOptimizer(id) {
      if (this.optimizerAutoApplying[id]) return
      this.optimizerAutoApplying = { ...this.optimizerAutoApplying, [id]: true }
      try {
        const r = await api.applyOptimizer(id)
        if (r && r.model) {
          this.model = r.model
          this.baseline = r.sim
          this.clearExperiment()
          this.parsed = null
          this.toast = t('AI 自动化控制：已按「{model}」最新版本自动下发参数到可调设备', { model: (AI_MODEL_MAP[id] || {}).name || '优化模型' })
          this.notify('success', t('AI 自动化控制'), t('已按「{model}」最新版本自动下发参数到可调设备。', { model: (AI_MODEL_MAP[id] || {}).name || '优化模型' }))
          this.pushCmd(t('AI 自动化控制已下发：应用「{model}」版本参数（最优 {fitness} kgCO₂/t，提升 {pct}%）', { model: r.name || id, fitness: (r.best_fitness ?? 0).toFixed(2), pct: r.improvement_pct ?? 0 }), 'sim')
          this._pushModelToFeed()
          await this._runRefresh()
        }
      } catch (e) {
        this.toast = t('AI 自动化控制下发失败：') + e.message
        this.notify('error', t('AI 自动化控制下发失败'), e.message)
      }
      try { await api.ackOptimizer(id) } catch (e) { /* 忽略确认失败 */ }
      this.optimizerAutoApplying = { ...this.optimizerAutoApplying, [id]: false }
      await this.refreshOptimizers()
    },
    startOptimizerPolling(ms = 3000) {
      if (this.optimizerPolling) return
      this.optimizerPolling = true
      this._optTimer = visiblePoll(() => this.refreshOptimizers(), ms)
    },
    stopOptimizerPolling() {
      if (this._optTimer) { this._optTimer(); this._optTimer = null }
      this.optimizerPolling = false
    },
    async startOptimizer(id) {
      await this.syncOptimizerContext()   // 训练对象始终是最新流程
      try {
        const r = await api.startOptimizer(id)
        if (r) this.toast = t('已开启「{model}」自动训练：后台将随实时传感器数据定时迭代', { model: (AI_MODEL_MAP[id] || {}).name || '优化模型' })
      } catch (e) {
        this.toast = t('开启自动训练失败：') + e.message
      }
      await this.refreshOptimizers()
    },
    async stopOptimizer(id) {
      try {
        const r = await api.stopOptimizer(id)
        if (r) this.toast = t('已暂停「{model}」自动训练', { model: (AI_MODEL_MAP[id] || {}).name || '优化模型' })
      } catch (e) {
        this.toast = t('暂停训练失败：') + e.message
      }
      await this.refreshOptimizers()
    },
    async trainOptimizer(id, steps = 1) {
      try {
        await api.trainOptimizer(id, steps)
      } catch (e) {
        this.toast = t('训练失败：') + e.message
      }
      await this.refreshOptimizers()
    },
    async resetOptimizer(id) {
      await this.syncOptimizerContext()
      try {
        const r = await api.resetOptimizer(id)
        if (r) this.toast = t('「{model}」已重置', { model: (AI_MODEL_MAP[id] || {}).name || '优化模型' })
      } catch (e) {
        this.toast = t('重置失败：') + e.message
      }
      await this.refreshOptimizers()
    },
    async setOptimizerHyper(id, patch) {
      try {
        const r = await api.setOptimizerHyper(id, patch)
        if (r) this.toast = t('算法超参数已保存，下一轮训练生效')
      } catch (e) {
        this.toast = t('保存超参数失败：') + e.message
      }
      await this.refreshOptimizers()
    },
    // 应用最优参数：后端返回应用后的流程模型 + 仿真，替换当前模型并重算（仿照 applyStrategy）
    async applyOptimizer(id) {
      await this.syncOptimizerContext()   // 确保训练上下文与当前流程一致
      let r = null
      try {
        r = await api.applyOptimizer(id)
      } catch (e) {
        this.toast = t('应用最优参数失败：') + e.message
        this.notify('error', t('应用最优参数失败'), e.message)
        return
      }
      this.model = r.model
      this.baseline = r.sim
      // 仿真模式：静默清实验状态（避免误记「清除策略」），以应用后结果刷新对比 after
      this.clearExperiment(this.simMode)
      this.parsed = null
      // 仿真模式：记录应用 AI 最优参数变更，纳入仿真前后对比
      if (this.simMode) {
        this._simLog('strategy', t('应用 AI 最优参数'), (AI_MODEL_MAP[id] || {}).name || id, 'opt_' + id)
        this.simCurrent = r.sim ? JSON.parse(JSON.stringify(r.sim)) : null
      }
      this.toast = t('已将「{model}」最优参数应用到流程', { model: (AI_MODEL_MAP[id] || {}).name || '优化模型' })
      this.notify('success', t('已应用最优参数'), t('已将「{model}」最优参数应用到流程，强度 {fitness} kgCO₂/t。', { model: (AI_MODEL_MAP[id] || {}).name || '优化模型', fitness: (r.best_fitness ?? 0).toFixed(2) }))
      this.pushCmd(t('已应用 AI 优化模型「{model}」最优参数：强度 {fitness} kgCO₂/t，较初始 {pct}%', { model: r.name || id, fitness: (r.best_fitness ?? 0).toFixed(2), pct: r.improvement_pct ?? 0 }), 'sim')
      this._pushModelToFeed()
      await this._runRefresh()
      await this.refreshOptimizers()
    },
    // 保存控制与自训练设置：{ auto_control?: bool, schedule?: { interval?, window? } }
    // 注意：该入口同时被模型/聚类算法/决策变量/优化目标/拟合变量等所有设置复用，
    // 后端返回体恒带 auto_control 当前值（与本次 patch 无关），故「开启/关闭自动化控制」
    // 的提示只允许在本次确实切换 auto_control 时弹出，避免其它设置每次保存都误报造成反复弹窗。
    async setOptimizerSettings(id, patch) {
      try {
        const r = await api.setOptimizerSettings(id, patch)
        if (r && patch && Object.prototype.hasOwnProperty.call(patch, 'auto_control') && typeof r.auto_control === 'boolean') {
          this.toast = r.auto_control
            ? t('已开启「{model}」自动化控制：模型变优后自动下发参数到可调设备', { model: (AI_MODEL_MAP[id] || {}).name || '优化模型' })
            : t('已关闭「{model}」自动化控制：改为系统提醒手动调优', { model: (AI_MODEL_MAP[id] || {}).name || '优化模型' })
        }
      } catch (e) {
        this.toast = t('保存控制设置失败：') + e.message
      }
      await this.refreshOptimizers()
    },
    // 把当前最优参数保存为模型版本（仅优于当前版本才替换生效）
    async archiveOptimizer(id) {
      let r = null
      try {
        r = await api.archiveOptimizer(id)
      } catch (e) {
        this.toast = t('保存版本失败：') + e.message
        return
      }
      this.toast = r.promoted
        ? t('已保存为新版本并替换为当前版本（历史版本仍保留）')
        : t('已保存为候选版本（未超过当前版本，未替换）')
      await this.refreshOptimizers()
    },
    // 在历史模型版本间切换（旧版本保留，可随时切回）
    async switchOptimizerVersion(id, versionId) {
      try {
        await api.switchOptimizerVersion(id, versionId)
        this.toast = t('已切换模型版本')
      } catch (e) {
        this.toast = t('切换版本失败：') + e.message
      }
      await this.refreshOptimizers()
    },
    // 确认提醒：清除手动调优提醒 / 自动控制待下发标记
    async ackOptimizer(id) {
      try {
        await api.ackOptimizer(id)
      } catch (e) { /* 忽略 */ }
      await this.refreshOptimizers()
    },
    // 仿真模式变更记录：供右上角「仿真前后对比」窗口左侧展示本次改了哪些内容。
    // mergeKey：同一变更项（同设备/参数/策略）反复调整时合并为一条，只刷新为「仿真前值 → 当前值」。
    _simLog(type, label, detail, mergeKey) {
      if (!this.simMode) return
      const now = Date.now()
      const list = this.simChanges || []
      if (mergeKey) {
        const idx = list.findIndex((x) => x.mk === mergeKey)
        if (idx >= 0) {
          const updated = [...list]
          updated[idx] = { ...updated[idx], detail, ts: now }
          this.simChanges = updated
          return
        }
      }
      const item = { id: uid('sc'), type, label, detail, ts: now, mk: mergeKey || null }
      this.simChanges = [item, ...list].slice(0, 40)
    },
    async loadStrategies() {
      this.strategies = await api.listStrategies()
    },
    async saveStrategy(name) {
      if (!this.parsed || !this.parsed.ops.length) return
      await api.createStrategy(name || '未命名策略', '', this.parsedText, this.parsed.ops)
      await this.loadStrategies()
      this.toast = t('策略已保存到策略库')
    },
    async removeStrategy(sid) {
      await api.deleteStrategy(sid)
      await this.loadStrategies()
    },
    async applyStrategy(sid) {
      // 仿真模式：记录策略应用（退出仿真时恢复，见 exitSim 快照）；同一策略重复应用合并为一条
      if (this.simMode) {
        const sname = ((this.strategies || []).find((s) => s.id === sid) || {}).name || sid
        this._simLog('strategy', t('应用策略'), sname, 'apply_' + sid)
      }
      const r = await api.applyStrategy(sid, this._applyDeviceOpParams(this.model), this.factors)
      this.model = r.model
      this.baseline = r.sim
      // 仿真模式：策略参数已落地模型，直接以应用后结果刷新「仿真前后对比」after
      //（此前遗漏：应用策略后对比窗口 after 不更新，该调节内容未纳入对比计算）
      this.clearExperiment(this.simMode)
      if (this.simMode) {
        this.simOps = []   // 参数已落地，清除未落地叠加操作，避免后续重算重复应用
        this.simCurrent = r.sim ? JSON.parse(JSON.stringify(r.sim)) : null
      }
      this.parsed = null
      this._pushModelToFeed()
      this.toast = t('策略已应用到当前流程')
      this.sceneRev++
    },
    // ---- 前端手动编辑流程（后端自适应重算）----

    // 自动布局：3D 孪生顶层布局统一由 scene.js「工艺树排版」负责（主工艺为树干沿 X 从左到右、
    // 工辅分支分布在主干两侧、Z=0 同一水平线）；模型坐标由 compileSchemeToModel 从编排画布映射而来，
    // 画布同样是同一棵「工艺树」（treeLayoutNodes）。因此这里不再做蛇形重排，避免把树形坐标打散、
    // 影响小组子场景的落位；仅统一模型朝向，通过正交管道/传送带对接不同高度的进出口。
    autoLayout() {
      const us = this.model.units
      if (!us || !us.length) return
      us.forEach((u) => { u.rot = 0.0 })
    },

    setUnitParam(id, key, val) {
      const u = this.model.units.find((x) => x.id === id)
      if (!u) return
      const num = Number(val)
      if (isNaN(num)) return
      // 仿真模式：记录本次属性更改（供右上角对比窗口左侧「本次更改」展示）。
      // 同参数反复调整合并为一条，文案始终为「仿真前值 → 当前值」。
      if (this.simMode) {
        const pm = (EDITABLE_PARAMS[u.type] || []).find((p) => p.key === key)
        const uname = u.name || ((PROCESS_MAP[u.type] || {}).label || u.type)
        const pLabel = pm ? pm.label : key
        const pUnit = pm && pm.unit ? pm.unit : ''
        const prev = (_simParamSnapshot && _simParamSnapshot.params[id] && _simParamSnapshot.params[id][key])
        this._simLog('param', `${uname} · ${pLabel}`, `${fmtNum(prev)} → ${fmtNum(num)}${pUnit ? ' ' + pUnit : ''}`, `pu_${id}_${key}`)
      }
      const params = { ...u.params }
      // 操作参数(风量/风温/富氧)与直接调参(焦比/煤比)共存：
      // coke_rate/coal_inj 作为基准；风温/抽力叠加 dCoke 偏移，富氧派生煤比(+15/1%)
      // 再经喷煤置换联动焦比（见 utils/bfFuel.bfFuelRates）。
      // 不再互斥删除——两者是"基准+增量"的互补关系。
      params[key] = num
      u.params = params
      // 参数改动同步写回编排方案（草稿）：保存时 model 由方案整体重编译，
      // 不写回的话「改完参数再保存」会把这次改动冲掉（仿真模式的编辑本就不落盘，不写回）。
      // 不置 schemeDirty：属性面板调参沿用「不落盘、不标脏」的既有行为（刷新页面回到方案值），
      // 写回方案只是为了保证本次改动在后续保存方案时不被重编译冲掉。
      if (!this.simMode) {
        const n = ((this.scheme && this.scheme.nodes) || []).find((x) => x.id === id)
        if (n) n.params = { ...(n.params || {}), [key]: num }
        // 已应用方案同步写一份：非钢场景 10s 一轮的 _otherSceneRefresh 会按已应用方案重编译 model，
        // 只写草稿的话这次调参会在下一轮被冲掉。
        const an = ((this.appliedScheme && this.appliedScheme.nodes) || []).find((x) => x.id === id)
        if (an) an.params = { ...(an.params || {}), [key]: num }
      }
      this.refresh(); this.autoLayout()
    },
    // 点击场景中设备/节点（3D 模型旁小铭牌、2D 工艺图设备卡片等）：选中该工序实例并聚焦。
    // 右侧显示统一的工序实例属性面板（UnitCarbonDetail）；与 selectUnit/openDeviceDetail 一致，
    // 自动展开右栏，避免图上点选后无任何面板反馈（2026-09-09）。
    pickUnit(id) {
      this._clearBrowse()
      const u = this.model.units.find((x) => x.id === id)
      if (u && PROCESS_MAP[u.type]) this.selectedAssetType = u.type
      this.selectedMaterialId = null; this.selectedGroupId = null; this.selectedFlowId = null
      this.deviceDetailId = null
      this.selectedUnitId = id; this.inspectorView = 'auto'; this.rightOpen = true; this.requestFocus('unit', id)
    },
    // 查看/关闭监测设备详情（3D 图点设备、或工序设备列表触发）
    openDeviceDetail(devId) { this._clearBrowse(); this.selectedMaterialId = null; this.selectedGroupId = null; this.selectedFlowId = null; this.deviceDetailId = devId; this.inspectorView = 'auto'; this.rightOpen = true; this.requestFocus('device', devId) },
    // 左侧「原料」库点击 -> 右侧显示属性与配置
    selectMaterial(id) {
      this._clearBrowse()
      this.selectedMaterialId = id
      this.deviceDetailId = null
      this.selectedUnitId = null
      this.selectedFlowId = null
      this.inspectorView = 'auto'
      this.rightOpen = true
    },
    // 左侧资源面板：浏览选中（只读查看属性 / 实时数据，不修改产线）。
    // 同时清除策略选中：否则先查看策略属性后再点工艺/物料/工序/设备等时，
    // inspectorMode 中 selectedStrategyId 优先级高于其它选中，右侧面板会一直停在策略属性。
    _clearBrowse() { this.selectedAssetType = null; this.selectedStrategyId = null },
    // 点击「工艺」目录中的工序类型 -> 工艺类型无独立属性面板，直接跳转到该类型首个实例的属性面板
    selectAssetType(type) {
      this._clearBrowse()
      this.selectedAssetType = type
      this.selectedMaterialId = null
      this.deviceDetailId = null
      this.selectedGroupId = null
      this.selectedFlowId = null
      this.inspectorView = 'auto'
      this.rightOpen = true
      // 选中该类型首个实例；若该工艺尚未部署实例则回到总览
      const u = this.model.units.find((x) => x.type === type)
      this.selectedUnitId = u ? u.id : null
      if (u) this.requestFocus('unit', u.id)
    },
    // 配置物料隐含碳因子（本会话覆盖，不影响库默认）
    setMaterialCarbon(id, val) {
      const v = Number(val)
      if (isNaN(v) || v < 0) return
      // 仿真模式：记录物料隐含碳因子变更，并重算使仿真前后对比实时更新。
      // 同物料反复调整合并为一条，文案始终为「仿真前值 → 当前值」。
      if (this.simMode) {
        const ml = ((MATERIAL_MAP[id] || {}).label) || id
        let prev = _simParamSnapshot && _simParamSnapshot.materialOverrides[id] && _simParamSnapshot.materialOverrides[id].carbon
        if (prev == null) prev = (this.materialOverrides[id] || {}).carbon   // 快照缺省回退当前值
        this._simLog('factor', t('{name} · 隐含碳因子', { name: ml }), `${fmtNum(prev)} → ${fmtNum(v)} tCO₂/${(MATERIAL_MAP[id] || {}).unit || ''}`, `mc_${id}`)
      }
      this.materialOverrides = { ...this.materialOverrides, [id]: { ...(this.materialOverrides[id] || {}), carbon: v } }
      if (this.simMode) this.refresh()
    },
    // 配置物料级自定义属性（密度 / 运输排放因子 / 含水率 / 说明备注），本会话覆盖
    setMaterialAttr(id, key, val) {
      // 仿真模式：记录物料属性变更（备注仅提示已更新，避免超长文案）
      if (this.simMode) {
        const ml = ((MATERIAL_MAP[id] || {}).label) || id
        const keyLabel = ({ density: t('堆密度'), transport_ef: t('运输排放因子'), moisture: t('含水率'), note: t('备注'), price: t('采购单价'), salePrice: t('销售单价') })[key] || key
        if (key === 'note') {
          this._simLog('factor', t('{name} · 备注', { name: ml }), t('已更新'), `ma_${id}_${key}`)
        } else {
          let prev = _simParamSnapshot && _simParamSnapshot.materialOverrides[id] && _simParamSnapshot.materialOverrides[id][key]
          if (prev == null) prev = (this.materialOverrides[id] || {})[key]   // 快照缺省回退当前值
          this._simLog('factor', t('{name} · {keyLabel}', { name: ml, keyLabel }), `${fmtNum(prev)} → ${fmtNum(val)}`, `ma_${id}_${key}`)
        }
      }
      this.materialOverrides = { ...this.materialOverrides, [id]: { ...(this.materialOverrides[id] || {}), [key]: val } }
      // price/salePrice 仅前端成本·收益核算使用（成本=外购用量×单价、收入=产品产量×售价），无需后端重算
      if (this.simMode && key !== 'note' && key !== 'price' && key !== 'salePrice') this.refresh()
    },
    // 碳市场参数维护（allowance 企业年配额 tCO₂ / price 实时碳价 万元/tCO₂）：本地持久化，
    // 用于全厂总览「碳配额结余」与「预估碳成本」计算，随改随联动。
    setCarbonCfg(partial) {
      this.carbonCfg = { ...this.carbonCfg, ...partial, v: 1 }
      try { localStorage.setItem('sim.carbonCfg', JSON.stringify(this.carbonCfg)) } catch (e) { /* 忽略存储失败 */ }
    },
    // 配置物料详细化学成分（如烧结矿 TFe/FeO/CaO、焦炭固定碳/灰分等，质量分数 %），
    // 覆盖值存于 materialOverrides[id].composition，随方案持久化；仅 sinter/pellet/coke 支持。
    setMaterialComp(id, key, val) {
      const v = Number(val)
      if (isNaN(v) || v < 0) return
      const cur = (this.materialOverrides[id] || {}).composition || {}
      if (this.simMode) {
        const ml = ((MATERIAL_MAP[id] || {}).name) || id
        let prev = _simParamSnapshot && _simParamSnapshot.materialOverrides[id] && _simParamSnapshot.materialOverrides[id].composition
        prev = prev && prev[key] != null ? prev[key] : (cur[key] != null ? cur[key] : '—')
        this._simLog('factor', t('{name} · 成分 {key}', { name: ml, key }), `${fmtNum(prev)} → ${fmtNum(v)} %`, `mc_${id}_${key}`)
      }
      this.materialOverrides = { ...this.materialOverrides, [id]: { ...(this.materialOverrides[id] || {}), composition: { ...cur, [key]: v } } }
      if (this.simMode) this.refresh()
    },
    // 清除某物料的成分覆盖，恢复库默认成分
    clearMaterialComp(id) {
      const ov = this.materialOverrides[id]
      if (!ov || !ov.composition) return
      const { composition, ...rest } = ov
      this.materialOverrides = { ...this.materialOverrides, [id]: rest }
      if (this.simMode) this.refresh()
    },
    // 配置喷吹煤粉配煤混合（N 种煤）：blend = [{ id, name, ratio, comp:{...} }]。
    // 覆盖值存于 materialOverrides[id].blend，随方案持久化；coalBlend.getCoalBlend 优先读它，
    // 否则回退默认混合（无烟煤/烟煤各 50%）。TFT / 置换比 RR / CO₂ / 炉渣碱度均经此联动。
    // 调用方（MaterialInspector）负责维护数组整体（增删/改项），此处按整体写入。
    setCoalBlend(id, blend) {
      if (!Array.isArray(blend)) return
      const arr = blend.map((x) => ({
        id: x.id,
        name: x.name,
        ratio: Number(x.ratio) || 0,
        comp: { ...(x.comp || {}) },
      }))
      if (this.simMode) {
        const ml = ((MATERIAL_MAP[id] || {}).name) || id
        this._simLog('factor', t('{name} · 配煤混合', { name: ml }), t('已更新（{n} 种煤）', { n: arr.length }), `pcblend_${id}`)
      }
      this.materialOverrides = { ...this.materialOverrides, [id]: { ...(this.materialOverrides[id] || {}), blend: arr } }
      if (this.simMode) this.refresh()
    },
    // 清除喷吹煤粉配煤覆盖，恢复默认混合（无烟煤/烟煤各 50%，加权 == 原固定值）
    clearCoalBlend(id) {
      const ov = this.materialOverrides[id]
      if (!ov || !ov.blend) return
      const { blend, ...rest } = ov
      this.materialOverrides = { ...this.materialOverrides, [id]: rest }
      if (this.simMode) this.refresh()
    },
    // 配置燃料的 NCV / CC（与顶栏「因子配置」同一数据源 factors.fuels），编辑后触发后端重算
    setFuelFactor(key, field, val) {
      const v = Number(val)
      if (isNaN(v) || v < 0) return
      const fuels = { ...(this.factors && this.factors.fuels ? this.factors.fuels : {}) }
      // 仿真模式：记录燃料因子变更（供右上角对比窗口左侧展示）。
      // 同因子反复调整合并为一条，文案始终为「仿真前值 → 当前值」。
      if (this.simMode) {
        const fuelLabel = ({ coke: '焦炭', coal: '煤粉', ng: '天然气' })[key] || key
        const fieldLabel = field === 'ncv' ? '热值 NCV' : field === 'cc' ? '碳排放因子 CC' : field
        let prev = _simParamSnapshot && _simParamSnapshot.factors && _simParamSnapshot.factors.fuels && _simParamSnapshot.factors.fuels[key] && _simParamSnapshot.factors.fuels[key][field]
        if (prev == null) prev = (fuels[key] || {})[field]   // 快照缺省回退当前值
        this._simLog('factor', `${fuelLabel} · ${fieldLabel}`, `${fmtNum(prev)} → ${fmtNum(v)}`, `ff_${key}_${field}`)
      }
      fuels[key] = { ...(fuels[key] || {}), [field]: v }
      this.setFactors({ ...(this.factors || {}), fuels })
    },
    // 三栏布局控制
    // 左栏（资源管理器）依赖具体工程：未打开工程时一律不展开（覆盖活动栏 / 顶栏 / 系统设置等所有入口），
    // 只在「要展开」时拦截，收起始终放行，避免异常态下左栏关不掉。
    toggleLeft() {
      if (this.welcomeOn && !this.leftOpen) {
        this.toast = t('请先打开工程：在内容区新建或打开场景')
        return
      }
      this.leftOpen = !this.leftOpen
    },
    toggleRight() { this.rightOpen = !this.rightOpen },
    toggleBottom() { this.bottomOpen = !this.bottomOpen },
    // 「本析智擎」：顶栏按钮切换右侧检视器 ↔ 智能体对话界面（AgentChatView）
    toggleAgent() {
      if (this.inspectorView === 'agent') {
        this.inspectorView = 'auto'
      } else {
        this.inspectorView = 'agent'
        this.rightOpen = true
      }
    },
    // ---- 功能视图窗口（tab）统一开合：openViews / activeViewId 为唯一真源 ----
    // 打开视图：未打开则追加到 tab 列表并激活；已打开则仅激活（不重复开 tab）
    openView(id) {
      if (!VIEW_IDS.includes(id)) return
      // 欢迎页（未打开工程）：功能视图都依赖当前工程，先引导打开工程
      // 例外：数据源管理（boxManage）是全局配置入口，不依赖具体工程，欢迎页可直接打开
      if (this.welcomeOn && id !== 'boxManage') { this.toast = t('请先打开工程：在内容区新建或打开场景'); return }
      if (!this.openViews.includes(id)) this.openViews.push(id)
      this._activateView(id)
    },
    // 关闭视图：关闭当前激活视图时自动切到相邻 tab（优先右侧，其次左侧）；全部关闭则回到三维仿真
    closeViewById(id) {
      // 「流程编排」tab 的关闭 = 完成编排：应用方案并退出编辑态（与工具条「完成编排」一致）
      if (id === 'flowEdit' && this.editMode) { this.exitEdit(); return }
      const i = this.openViews.indexOf(id)
      if (i < 0) return
      this.openViews.splice(i, 1)
      if (this.activeViewId === id) {
        this.activeViewId = this.openViews[i] || this.openViews[i - 1] || null
      }
    },
    // 激活视图：id 为空（null）表示切回三维仿真场景；未打开则先打开
    activateView(id) {
      if (!id) { this._activateView(null); return }
      if (!this.openViews.includes(id)) { this.openView(id); return }
      this._activateView(id)
    },
    // 切换视图：当前已激活则关闭（收起该窗口），否则打开并激活
    toggleView(id) {
      if (this.activeViewId === id) this.closeViewById(id)
      else this.openView(id)
    },
    closeAllViews() {
      // 编排中：先走 exitEdit 应用方案并关闭编排 tab，避免只清列表导致编辑态残留
      if (this.editMode) this.exitEdit()
      this.openViews = []; this.activeViewId = null
      this.rightOpen = false; this.grpRightBackup = null
    },
    _activateView(id) {
      // 页面切换纪律：进入任一功能视图时，原页面的右侧属性面板自动收起（避免跨页面残留
      // 选中态与面板，保证「当前页面 = 唯一侧重点」）；回到三维主视图时再恢复收起前的状态。
      // AI 群控的「训练相关设定」已内嵌其视图右栏，同样适用此规则。
      if (id) {
        if (this.grpRightBackup == null) this.grpRightBackup = this.rightOpen
        this.rightOpen = false
      } else if (this.grpRightBackup != null) {
        this.rightOpen = this.grpRightBackup
        this.grpRightBackup = null
      }
      this.activeViewId = id
      // 数据分析 / AI群控 的数据源来自左侧「场景」资源树 → 仅把左栏定位到场景面板，
      // 不自动展开左侧（左栏只在用户手动点击活动栏 / 顶栏开关 / 系统设置时才展开）
      if (id === 'dataView' || id === 'aiGroup') this.activityView = 'scene'
    },
    // 工况数据分析：数据源增删（从左侧「场景」资源树拖入添加；拖回场景即移除）
    addDvSource(src) {
      if (!src || !src.id) return
      if (!this.dvSources.some((s) => s.id === src.id)) this.dvSources.push(src)
    },
    removeDvSource(id) {
      this.dvSources = this.dvSources.filter((s) => s.id !== id)
    },
    clearDvSources() { this.dvSources = [] },
    // 底栏快讯显示开关（localStorage 持久化，刷新后保持）
    toggleNewsTicker() {
      this.newsTickerOn = !this.newsTickerOn
      try { localStorage.setItem('sim.newsTickerOn', this.newsTickerOn ? '1' : '0') } catch (e) {}
    },
    // 以下 7 个开关统一走「窗口 + tab」开合（toolbar / 菜单 / 活动栏调用入口保持不变）
    toggleDataView() { this.toggleView('dataView') },
    toggleAiGroup() { this.toggleView('aiGroup') },
    toggleCarbonMarket() { this.toggleView('carbonMarket') },
    toggleCarbonCalc() { this.toggleView('carbonCalc') },
    toggleEnergyFlow() { this.toggleView('energyFlow') },
    toggleBoxManage() { this.toggleView('boxManage') },
    // MPC 控温优化已集成进「AI 群控」的模型库（内置求解型模型），不再是独立视图：
    // 这里只负责打开 AI 群控 + 把跳转令牌加一，由 PidControlView 切到 mpc 页。
    openAgcMpc() {
      if (this.welcomeOn) { this.toast = t('请先打开工程：在内容区新建或打开场景'); return false }
      this.activateView('aiGroup')
      this.agcMpcToken += 1
      this.rightOpen = false
      return true
    },
    // HMI人机交互屏：与 3D 数字孪生对等的主视图形态（不进 tab 列表），
    // 开启时回到主视图槽位（功能视图窗口保持打开，点其标签可再切回）
    toggleOverview() {
      if (this.welcomeOn) { this.toast = t('请先打开工程：在内容区新建或打开场景'); return }
      this.overviewOn = !this.overviewOn
      if (this.overviewOn) {
        if (this.grpRightBackup == null) this.grpRightBackup = this.rightOpen
        this.rightOpen = false
        this.activeViewId = null
      } else if (this.grpRightBackup != null) {
        this.rightOpen = this.grpRightBackup
        this.grpRightBackup = null
      }
    },
    // AI 群控视图入口（活动栏 / 顶栏 AI 菜单共用）：
    // 参数优化训练面板已内嵌于群控视图右侧栏（训练相关设定，GA/PSO/RL 顶部可切换）；
    // 打开时默认选中遗传算法（已选优化算法则保持不跳变），并保持外部右栏收起（_activateView 已处理）
    openAiGroup() {
      this.toggleAiGroup()
      if (!this.aiGroupOn) return
      // 正常从菜单进入群控：清掉 MPC 跳转令牌，落在模型库（而不是上次看的 MPC 页）
      this.agcMpcToken = 0
      this.agcPage = 'lib'
      const cur = this.selectedStrategyId
      const curOpt = /^ai::(ga|pso|rl)$/.test(String(cur || ''))
      this.selectStrategy(curOpt ? cur : 'ai::ga')
      this.rightOpen = false
      if (this.grpRightBackup == null) this.grpRightBackup = true
    },
    // 碳排核算视图 / 能流分析视图 / 能碳一体机管理视图 均复用上方 toggleXxx（tab 化开合）；
    // HMI人机交互屏不走 tab（与 3D 数字孪生对等的主视图，见 toggleOverview）
    toggleFullscreen() {
      this.fullscreenOn = !this.fullscreenOn
      if (this.fullscreenOn) {
        this.leftOpen = false
        this.rightOpen = false
        this.bottomOpen = false
      } else {
        // 退出全屏不自动展开左侧资源菜单（仅在用户手动点击时展开），保持退出前的收起状态
        this.rightOpen = false
        this.bottomOpen = false
      }
    },
    // 右侧检视器显式视图（左侧资产树/工具栏触发）：park 园区构成 / materials 原料库 / strategy 减排策略
    setInspectorView(v) { this.inspectorView = v; this.rightOpen = true },
    // 「导出报告」：缓存请求载荷并切到右侧报告面板（面板内配置参数后由用户点击「生成报告」）
    openReportPanel(payload) {
      this.reportPayload = payload
      this.reportNonce = (this.reportNonce || 0) + 1
      this.setInspectorView('report')
    },
    // 左侧策略库选中策略：打开右侧「策略详情」面板（名称 / 数值调整可编辑 + 底部「策略仿真」按钮）
    selectStrategy(sid) {
      this._clearBrowse()
      this.selectedStrategyId = sid
      this.selectedMaterialId = null
      this.deviceDetailId = null
      this.selectedUnitId = null
      this.selectedFlowId = null
      this.inspectorView = 'auto'
      this.rightOpen = true
    },
    // 左侧策略库点击工艺策略（某工艺对应的绿色策略）：打开右侧「策略属性」面板（只读 + 启用/停用 + 查看工艺）
    selectGreenStrategy(processType, sid) {
      this._clearBrowse()
      this.selectedStrategyId = `green::${processType}::${sid}`
      this.selectedMaterialId = null
      this.deviceDetailId = null
      this.selectedUnitId = null
      this.selectedFlowId = null
      this.inspectorView = 'auto'
      this.rightOpen = true
    },
    // full=true：彻底清空所有选中（不留任何面板），用于进入/退出编排、切场景等
    // 「不该残留其它面板」的场景——否则残留的策略/AI 模型选中会在 inspectorMode 里
    // 优先于 editMode，把「编排属性」顶成「策略属性」（表现：点流程编排自动弹出策略面板）。
    // 默认（面板标题栏 ✕）：AI 模型训练面板退回「模型列表（按类别）」而不是直接关掉检视器。
    closeInspector(full = false) {
      const sid = this.selectedStrategyId
      if (!full && typeof sid === 'string' && sid.startsWith('ai::') && sid !== 'ai::overview') {
        this.selectStrategy('ai::overview')
        return
      }
      this._clearBrowse(); this.deviceDetailId = null; this.selectedUnitId = null; this.selectedMaterialId = null; this.selectedStrategyId = null; this.selectedGroupId = null; this.selectedFlowId = null; this.inspectorView = 'auto'
    },
    // 切换某个工艺的某项节能减碳策略启用状态
    toggleGreenStrategy(processType, strategyId) {
      if (!this.activeGreenStrategies[processType]) {
        this.activeGreenStrategies[processType] = []
      }
      const arr = this.activeGreenStrategies[processType]
      const idx = arr.indexOf(strategyId)
      if (idx >= 0) arr.splice(idx, 1)
      else arr.push(strategyId)
    },
    // 获取某工艺已启用的策略 id 列表
    greenStrategiesFor(processType) {
      return this.activeGreenStrategies[processType] || []
    },

    // ---- 仿真模式：进入保存快照，退出恢复；仿真期间所有编辑不持久化 ----
    enterSim() {
      if (this.simMode) return
      _simPrevDirty = this.schemeDirty   // 仿真态的一切改动都不落盘，退出仿真后未保存标记应回到此值
      this.simMode = true
      // 仿真模式：数字孪生场景环境自动切换为「虚空」
      if (this.envMode !== 'void') this.setEnvMode('void')
      this.simBaseline = this.baseline ? JSON.parse(JSON.stringify(this.baseline)) : null
      this.simCurrent = this.baseline ? JSON.parse(JSON.stringify(this.baseline)) : null // 初始 after=before，无差异
      this.simOps = []
      this.simChanges = []  // 进入仿真模式：变更记录从零开始
      // 仿真前参数快照：同一项多次调整合并为一条记录，文案始终为「仿真前值 → 当前值」
      _simParamSnapshot = {
        params: _snapParams(this.model),
        deviceSetpoints: JSON.parse(JSON.stringify(this.deviceSetpoints)),
        deviceExtraSetpoints: JSON.parse(JSON.stringify(this.deviceExtraSetpoints)),
        factors: JSON.parse(JSON.stringify(this.factors)),
        materialOverrides: JSON.parse(JSON.stringify(this.materialOverrides)),
      }
      _simSnapshot = {
        model: JSON.parse(JSON.stringify(this.model)),
        scheme: JSON.parse(JSON.stringify(this.scheme)),
        baseline: JSON.parse(JSON.stringify(this.baseline)),
        activeGreenStrategies: JSON.parse(JSON.stringify(this.activeGreenStrategies)),
        deviceSetpoints: JSON.parse(JSON.stringify(this.deviceSetpoints)),
        deviceExtraSetpoints: JSON.parse(JSON.stringify(this.deviceExtraSetpoints)),
        processStrategyEnabled: JSON.parse(JSON.stringify(this.processStrategyEnabled)),
        unitStrategies: JSON.parse(JSON.stringify(this.unitStrategies)),
        materialOverrides: JSON.parse(JSON.stringify(this.materialOverrides)),
        processRoute: this.processRoute,
        strategy: JSON.parse(JSON.stringify(this.strategy)),
        delta: JSON.parse(JSON.stringify(this.delta)),
        parsed: JSON.parse(JSON.stringify(this.parsed)),
        parsedText: this.parsedText,
        factors: JSON.parse(JSON.stringify(this.factors)),
        deviceHistory: JSON.parse(JSON.stringify(this.deviceHistory)),
        deviceLive: JSON.parse(JSON.stringify(this.deviceLive)),
        deviceMeta: JSON.parse(JSON.stringify(this.deviceMeta)),
        historyPast: JSON.parse(JSON.stringify(this.historyPast)),
        historyFuture: JSON.parse(JSON.stringify(this.historyFuture)),
      }
      this.toast = t('已进入仿真模式：所有修改仅预览，退出后自动恢复')
    },
    exitSim() {
      if (!this.simMode) return
      const s = _simSnapshot
      _simSnapshot = null
      _simParamSnapshot = null
      // 退出仿真：数字孪生场景环境固定切换为「工业」
      if (this.envMode !== 'industrial') this.setEnvMode('industrial')
      this.simMode = false
      this.simBaseline = null
      this.simCurrent = null
      this.simOps = []
      this.simChanges = []
      if (s) {
        this.model = s.model
        this.scheme = s.scheme
        this.activeGreenStrategies = s.activeGreenStrategies
        this.deviceSetpoints = s.deviceSetpoints
        this.deviceExtraSetpoints = s.deviceExtraSetpoints || {}
        this.processStrategyEnabled = s.processStrategyEnabled
        this.unitStrategies = s.unitStrategies
        this.materialOverrides = s.materialOverrides
        this.processRoute = s.processRoute
        this.strategy = s.strategy
        this.delta = s.delta
        this.parsed = s.parsed
        this.parsedText = s.parsedText
        this.factors = s.factors
        this.deviceHistory = s.deviceHistory
        this.deviceLive = s.deviceLive
        this.deviceMeta = s.deviceMeta
        this.historyPast = s.historyPast
        this.historyFuture = s.historyFuture
        if (s.baseline) this.baseline = s.baseline
      }
      this.refresh()
      this.sceneRev++
      // 恢复快照会改动 scheme（触发标脏 watch）：明确还原为进入仿真前的未保存标记
      this.schemeDirty = _simPrevDirty
      nextTick(() => { this.schemeDirty = _simPrevDirty })
      this.toast = t('已退出仿真模式，恢复仿真前状态')
    },
    // 一键把当前全部参数保存为策略（供仿真模式「保存策略」按钮调用）
    async saveCurrentAsStrategy(name) {
      const sname = (name || '').trim() || '当前参数快照'
      const model = this._applyDeviceOpParams(this.model)
      const ops = []
      for (const u of (model.units || [])) {
        const editable = EDITABLE_PARAMS[u.type] || []
        for (const p of editable) {
          const v = u.params && u.params[p.key]
          if (v == null) continue
          ops.push({ action: 'set_param', target: u.name, param: p.key, value: v, mode: 'absolute', note: `${u.name} ${p.label} = ${v} ${p.unit || ''}` })
        }
        for (const t of (u.techs || [])) {
          ops.push({ action: 'apply_tech', target: u.name, tech: t, note: `${u.name} 应用技术 ${t}` })
        }
      }
      const created = await api.createStrategy(sname, `仿真模式保存的当前参数快照 · ${new Date().toLocaleString()}`, sname, ops)
      await this.loadStrategies()
      this.toast = t('策略「{name}」已保存，可在「资源 · 策略」中查看', { name: sname })
      return created
    },
    // 更新已保存策略（名称/描述/原文/操作），调 PUT /api/strategies/{sid}
    async updateStrategy(sid, patch) {
      await api.updateStrategy(sid, patch)
      await this.loadStrategies()
      this.toast = t('策略信息已更新')
    },
    // 策略详情面板「策略仿真」按钮：内置预置策略进入仿真并解析测试；自定义策略加载并应用（退出后自动恢复）
    async runStrategySimulation(sid) {
      const st = this.selectedStrategy
      if (!st) { this.toast = t('策略不存在或已删除'); return }
      if (st.source === 'preset') {
        if (!this.simMode) this.enterSim()
        this.strategyInput = st.raw_text || st.name || ''
        this.parsedText = ''
        this.parsed = null
        try {
          await this.parse(this.strategyInput)
          if (this.parsed && this.parsed.ops.length) {
            await this.runExperiment()
            this.toast = t('已对内置策略「{name}」完成仿真，可在右上角对比结果', { name: st.name })
          } else {
            this.toast = t('该内置策略解析结果为空')
          }
        } catch (e) {
          this.toast = t('内置策略仿真失败：') + (e.message || e)
        }
        return
      }
      if (!this.simMode) this.enterSim()
      try {
        await this.applyStrategy(sid)
        this.toast = t('策略「{name}」已加载到仿真模式，可实时对比', { name: st.name || '未命名' })
      } catch (e) {
        this.toast = t('策略加载失败：') + (e.message || e)
      }
    },
    // 请求在命令行输入策略名称后保存（仿真模式「保存策略」按钮）
    requestSaveStrategy() {
      this.pendingSaveStrategy = true
      this.toast = t('请在下方命令行输入策略名称后回车保存')
    },
    // 顶栏「重置视图」按钮 -> SceneViewer watch 该计数 -> scene.resetView()
    resetView() { this.viewResetNonce++ },
    // 切换场景行业（四大控排 + 其它）：实际打开场景资源包由 openScene 完成。
    //  - steel → 平台内置钢铁包；other → 「其它」分组第一个就绪资源包（如示例机房热控）
    //  - 水泥/化工/有色 → 未安装引导（对应行业 .ec 资源包安装后可在此打开）
    async setScenario(id) {
      if (id === this.scenario && id === 'steel' && this.sceneId === 'steel') return
      if (id === 'steel') { await this.openScene('steel'); return }
      if (id === 'other') {
        const meta = this._readySceneOfGroup('其它')
        if (meta) await this.openScene(meta.id)
        else this.toast = t('「其它」分组暂无已安装的资源包：请先在场景设置中「导入资源包」安装 .ec 文件（系统内置示例：算力中心热控）')
        return
      }
      const meta = this.sceneIndex.find((x) => x.id === id)
      if (meta && meta.ready) { await this.openScene(meta.id); return }
      const label = (meta && meta.label) || (this.scenarios.find((s) => s.id === id) || {}).label || id
      this.toast = t('「{label}」行业资源包尚未安装：可通过「导入资源包」安装对应 .ec 定制包后打开（当前内置：钢铁企业示例、算力中心热控示例）', { label })
    },
    // 「其它」分组下第一个就绪场景（按注册表 order 升序）
    _readySceneOfGroup(group) {
      const list = this.sceneIndex.filter((x) => String(x.industryGroup || x.industry || '').indexOf(group) >= 0 && x.ready)
      list.sort((a, b) => (a.order == null ? 99 : a.order) - (b.order == null ? 99 : b.order))
      return list[0] || null
    },
    // 刷新场景注册表（后端 /api/scenes：内置包 + 已安装 .ec 资源包）
    async refreshSceneIndex() {
      try {
        const list = await api.listScenes()
        if (Array.isArray(list)) {
          this.sceneIndex = list
          this.sceneIndexTs++
        }
      } catch (e) { /* 后端暂不可用：静默，列表为空 */ }
      return this.sceneIndex
    },
    // 打开场景资源包：卸载当前流程状态 → 装载包数据 → 重建编排方案/模型/资源视图。
    // 返回是否成功；失败不改变当前场景。
    // 一律「就地切换」，不整页刷新（此前切场景会 window.location.reload()，表现为打开场景就闪一下重刷）：
    // 资源树 / 检视器按 sceneVersion 重建、3D 按 sceneRev 重建、核算结果等会话态在下面逐项归零，
    // 功能视图 tab 与数据分析数据源（绑定的是上一场景的设备 id）在切换前清空 —— 与重载后的状态等价。
    async openScene(sceneId) {
      if (!sceneId) return false
      const sameMode = this.sceneMode === (sceneId === 'steel' ? 'steel' : 'other')
      // 仅在资源已加载时才跳过：初始 sceneId='steel'/sceneMode='steel' 时 scenePack 仍为 null，
      // 否则长/短流程模板等资源不会被填充（编排工具条模板按钮不显示）
      if (sceneId === this.sceneId && sameMode && this.scenePack && this.scenePack.meta?.id === sceneId) {
        // 资源无需重装（早退），但「打开工程」这个动作仍要成立：欢迎页必须进工作区并记入最近，
        // 否则经其它入口（如 setScenario('steel')）打开默认装载的场景同样毫无反应
        this._noteRecentScene(sceneId)
        this._markEntered()
        return true
      }
      let meta = this.sceneIndex.find((x) => x.id === sceneId)
      if (!meta) await this.refreshSceneIndex()
      meta = this.sceneIndex.find((x) => x.id === sceneId) || meta
      if (!meta) { this.toast = t('场景「{id}」不存在', { id: sceneId }); return false }
      if (!meta.ready) {
        this.toast = t('「{label}」资源包尚未就绪：请先通过「导入资源包」安装该场景的 .ec 文件', { label: meta.label || sceneId })
        return false
      }
      if (this.sceneBusy) return false
      // 先退出仿真/编排，避免在切换过程中触发旧场景的后端刷新
      if (this.simMode) this.exitSim()
      if (this.editMode) this.exitEdit()
      // 功能视图 tab（数据分析 / AI 群控 / 能碳一体机…）与数据分析数据源都绑着上一场景的设备 id，
      // 切场景前一并清空，避免新场景里还挂着旧设备卡片（重载后这些本来就是空的）。
      this.closeAllViews()
      this.clearDvSources()
      // HMI 大屏展示的也是上一场景的 KPI/报警：切场景回到三维孪生主视图
      this.overviewOn = false
      // 切换场景 = 换了一个页面：收起右侧属性面板并丢弃恢复备份，避免旧场景的选中态残留
      this.rightOpen = false
      this.grpRightBackup = null
      // 地址栏带上当前工程：刷新 / 分享链接都能直达这个场景（不触发导航，只改地址）
      try {
        const url = new URL(window.location.href)
        url.searchParams.set('scene', sceneId)
        window.history.replaceState(window.history.state, '', url)
      } catch (e) { /* 非浏览器环境忽略 */ }
      this.sceneBusy = true
      const loadSeq = this.beginSceneLoad('data')
      try {
        const pkg = await api.getSceneResource(sceneId)
        if (!pkg || !pkg.meta) throw new Error(t('资源包数据异常'))
        this.scenePack = pkg
        this.sceneId = sceneId
        const isSteel = sceneId === 'steel' || ((pkg.meta.engines || []).includes('steel-carbon'))
        this.sceneMode = isSteel ? 'steel' : 'other'
        this.scenario = isSteel ? 'steel' : 'other'
        const res = pkg.resources || {}
        this.sceneCtx = res.dictionary || res.config || null
        // 包内物料（非钢场景：机房温控的 冷却水供水/回水、机房冷风…）并入运行时物料表，
        // 供 2D/3D 管线着色与标签、编排端口、物料下拉统一解析（不覆盖钢包既有条目）。
        registerSceneMaterials(this.sceneCtx)
        this.sceneTemplates = Array.isArray(res.templates) ? res.templates : []
        if (res.factors) { this.factors = res.factors; this.factorsDefault = res.factors }
        if (res.paramSchema) this.paramSchema = res.paramSchema
        if (res.devices) this.deviceLibrary = res.devices
        const routes = Array.isArray(pkg.meta.routes) && pkg.meta.routes.length ? pkg.meta.routes : null
        const defaultRoute = pkg.meta.defaultRoute || (routes && routes[0]) || null
        // 编排方案：只认服务端存档（跨端唯一真源），无存档则按包模板构建
        this.setSceneLoadPhase('design', loadSeq)
        const saved = await this._pullScheme(sceneId)
        const pullState = _designPullState   // 'ok' 读到存档 / 'empty' 确认无存档 / 'error' 读取失败
        this.processRoute = isSteel ? ((saved && saved.route) || 'short') : (defaultRoute || 'cool')
        // 恢复的存档先补齐容器字段并按场景做口径迁移（旧口径存档升级而非整档丢弃，见 _adoptScheme）
        this.scheme = this._adoptScheme((saved && saved.scheme) ? saved.scheme : this._buildSceneScheme(this.processRoute), sceneId)
        // 子编排态不跨场景继承：否则新场景 3D 会沿用旧小组 id 走 groupScene 分支，渲染出空子场景
        this.scheme.activeGroupId = null
        // 清空跨场景会话状态（避免脏数据串场）
        // 核算结果 / 实时帧 / 策略库 / 报告 / 撤销栈一并归零，防止刷新期间短暂展示旧场景数据
        this.baseline = null
        this.live = null
        this.presets = []
        this.reportPayload = null
        this.flowBackId = null
        this.historyPast = []
        this.historyFuture = []
        this.materialOverrides = {}
        // 设备设定值随场景存档恢复（附加传感 / 可变设备的调节值只存在于 deviceSetpoints，
        // 早期版本此处直接清空 → 打开场景后所有附加设备的调节值回到模板默认）。
        this._restoreSetpoints(saved)
        this.deviceLive = {}
        this.deviceHistory = {}
        this.deviceMeta = null
        this.strategy = null
        this.delta = null
        this.parsed = null
        this.parsedText = ''
        this.simOps = []
        this.simCurrent = null
        this.strategies = []
        // ── AI 群控：群控策略属于具体的场景资源包（引用的可调 / 传感设备是本场景特有的），
        // 切场景时停掉本端执行器并清空运行态与最近一轮结果，避免把上一场景的「运行中」带过来。
        // 服务端运行器仍按各场景自己存档里的 running 继续执行（互不干扰）。
        if (this.agcRunId) this.stopAgcRule()
        this.agcRunId = ''
        this.agcLast = {}
        this.selectedUnitId = null
        this.selectedGroupId = null
        this.selectedFlowId = null
        this.deviceDetailId = null
        this.selectedMaterialId = null
        this.selectedStrategyId = null
        this.selectedAssetType = null
        this.inspectorView = 'auto'
        // 切场景是显式载入：方案即最终态，同步为已应用方案后再编译
        this._syncAppliedScheme()
        this.setSceneLoadPhase('calculate', loadSeq)
        // 非钢场景由 _otherSceneRefresh 内部编译一次；钢铁场景编译后走后端碳引擎。
        if (!isSteel) {
          this._otherSceneRefresh()
          this._pushModelToFeed()   // 新场景模型同步给实时数据源，避免继续按旧 model 下发遥测
        } else {
          this.compileSchemeToModel()
          await this._loadSteelSession()
        }
        // 落盘与否取决于服务端存档的读取结果（_designPullState）：
        //   empty —— 服务端确认本场景尚无存档：本次按模板构建的方案即初始存档，固化落盘；
        //   ok    —— 仅在采纳过程真修改了内容（旧档迁移 / 资源包结构升级）时才回写，
        //            内容没变就不写：打开场景是只读动作，不该产生会覆盖别的端存档的写；
        //   error —— **绝不落盘**：此刻手里是按模板重建的默认方案，写回去就会把用户
        //            保存过的编排永久抹掉（「编排莫名其妙回到默认」的顽疾根因）。
        if (pullState === 'error') {
          this.pushCmd(t('服务端编排存档读取失败：本场景暂按默认模板显示，且未写入服务端（线上存档未被覆盖），请刷新页面重试。'), 'sys')
        } else if (pullState === 'empty' || _schemeAdoptChanged) {
          this._saveScheme()
        }
        // sceneVersion：左右面板（资源树 / 检视器）以它为 :key 重建，清空本地折叠态/档位等残留
        this.sceneVersion++
        try { localStorage.setItem('sim.sceneId', sceneId) } catch (e) { /* localStorage 不可用时忽略 */ }
        // 记到服务端「最后打开的工程」：官网没有用户体系，这份记录所有人共用 ——
        // 换浏览器 / 换电脑进来都会落到同一个工程，不会退回默认钢包而看不到这边的策略。
        api.workspaceSetLastScene(sceneId, (meta && (meta.label || meta.name)) || '').catch(() => { /* 服务端不可用时本机兜底仍在 */ })
        // 打开工程即进入工作区：欢迎页收起、本次会话内刷新不再回欢迎页；并记入「最近」
        this._noteRecentScene(sceneId, meta)
        this._markEntered()
        // 3D 重建延后一帧：等面板按新 key 挂载、容器尺寸稳定后再 buildModel，
        // 避免 canvas 0x0 导致相机投影矩阵 NaN（与 exitEdit 的处理口径一致）
        await nextTick()
        this.sceneRev++
        const label = meta.label || pkg.meta.label || sceneId
        this.toast = t('已打开场景「{label}」', { label })
        this.pushCmd(t('已打开场景「{label}」：资源列表、编排方案与孪生模型已切换。', { label }), 'cmd')
        // 收尾：此前 openScene 从未置过 active=false，底栏加载指示会一直转圈不消失
        this.finishSceneLoad(loadSeq)
        return true
      } catch (e) {
        this.failSceneLoad(e && e.message ? e.message : String(e), loadSeq)
        this.toast = t('打开场景失败：') + e.message
        this.notify('error', t('打开场景失败'), e.message)
        return false
      } finally {
        this.sceneBusy = false
      }
    },
    // ===== 工程选择（欢迎页）=====
    // 启动判定：新会话（新标签页 / 重开浏览器）一律先停在「工程选择」欢迎页，由用户显式打开工程；
    // 已进入过工作区后本次会话内刷新（F5）不再回欢迎页（sessionStorage，关闭标签即失效）。
    _loadWelcomeState() {
      let entered = false
      try { entered = sessionStorage.getItem('sim.entered') === '1' } catch (e) { /* 隐私模式下忽略 */ }
      this.welcomeOn = !entered
      this.entered = entered
      try {
        const raw = localStorage.getItem('sim.recentScenes')
        const arr = raw ? JSON.parse(raw) : []
        if (Array.isArray(arr)) this.recentScenes = arr.filter((x) => x && x.id).slice(0, 12)
      } catch (e) { /* 存档损坏：按空列表处理 */ }
    },
    // 进入工作区：欢迎页 → 主界面（打开 / 新建工程后调用）
    _markEntered() {
      this.welcomeOn = false
      this.entered = true
      try { sessionStorage.setItem('sim.entered', '1') } catch (e) { /* 忽略 */ }
    },
    // 记入「最近打开的工程」（最新在前，去重，最多 12 条）
    _noteRecentScene(sceneId, meta) {
      if (!sceneId) return
      const m = meta || this.sceneIndex.find((x) => x.id === sceneId) || null
      const pm = this.scenePack && this.scenePack.meta ? this.scenePack.meta : null
      const label = (m && (m.label || m.name || m.industry)) || (pm && (pm.label || pm.name)) || sceneId
      const industry = (m && (m.industryGroup || m.industry)) || (pm && pm.industry) || ''
      const list = this.recentScenes.filter((x) => x.id !== sceneId)
      list.unshift({ id: sceneId, label, industry, ts: Date.now() })
      this.recentScenes = list.slice(0, 12)
      try { localStorage.setItem('sim.recentScenes', JSON.stringify(this.recentScenes)) } catch (e) { /* 忽略 */ }
    },
    // 从「最近」列表移除一项（欢迎页行尾 ✕；只影响记录，不删资源包）
    removeRecentScene(id) {
      if (!id) return
      this.recentScenes = this.recentScenes.filter((x) => x.id !== id)
      try { localStorage.setItem('sim.recentScenes', JSON.stringify(this.recentScenes)) } catch (e) { /* 忽略 */ }
    },
    // 欢迎页「打开工程」：目标已是当前场景时无需重新装载（openScene 会早退），直接进工作区。
    // 返回是否成功；失败（资源包未就绪 / 不存在）保持停留在工程选择页。
    async openProjectScene(sceneId) {
      if (!sceneId) return false
      if (sceneId === this.sceneId) {
        this._noteRecentScene(sceneId)
        this._markEntered()
        return true
      }
      return await this.openScene(sceneId)
    },
    // 返回「工程选择」欢迎页（当前工程保持装载，再打开即回到原工程）
    backToWelcome() {
      if (this.simMode) this.exitSim()
      if (this.editMode) this.exitEdit()
      this.welcomeOn = true
      this.entered = false
      try { sessionStorage.removeItem('sim.entered') } catch (e) { /* 忽略 */ }
    },
    // 启动恢复：自动打开上次退出前打开的场景（localStorage sim.sceneId，随 openScene 写入）。
    // 场景已卸载 / 资源包未就绪时保持默认场景并给出提示，不阻断启动流程。
    async restoreLastScene() {
      // 欢迎页：保留在「工程选择」，不自动恢复上个场景（否则就绕过了欢迎页）
      if (this.welcomeOn) return false
      // 已在 init 内首屏装载（资源包场景直接开机到位）：不再二次打开，
      // 避免重复刷新与 3D 场景重建（也是「先闪一下钢铁」的另一半开销）。
      if (this.sceneBooted) return true
      let last = null
      try { last = localStorage.getItem('sim.sceneId') } catch (e) { return false }
      if (!last || last === this.sceneId) return false
      if (!this.sceneIndex.length) await this.refreshSceneIndex()
      const meta = this.sceneIndex.find((x) => x.id === last)
      if (!meta) {
        this.pushCmd(t('上次打开的场景「{id}」已不存在，已按默认场景启动。', { id: last }), 'sys')
        return false
      }
      if (!meta.ready) {
        this.pushCmd(t('上次打开的场景「{label}」资源包未就绪，已按默认场景启动：请在「设置 → 场景」导入该场景的 .ec 资源包。', { label: meta.label || last }), 'sys')
        return false
      }
      const ok = await this.openScene(last)
      if (ok) this.pushCmd(t('已自动恢复上次打开的场景「{label}」。', { label: meta.label || last }), 'sys')
      return ok
    },
    // 钢铁场景会话：装载策略库 + 走后端碳引擎仿真
    async _loadSteelSession() {
      this.loadStrategies().catch(() => {})
      await this._runRefresh()
    },
    // 按流程路线/包模板构建编排方案（steel 走 flowLibrary buildScheme；其它场景走包内模板快照）
    _buildSceneScheme(route) {
      if (this.sceneMode === 'steel' || this.sceneId === 'steel') {
        return buildScheme(route === 'long' ? 'long' : 'short')
      }
      const tpl = this.sceneTemplates.find((x) => x.id === route || x.route === route) || this.sceneTemplates[0]
      if (!tpl || !tpl.scheme) return { nodes: [], connections: [], devices: [], groups: [], activeGroupId: null }
      const s = JSON.parse(JSON.stringify(tpl.scheme))
      if (!s.groups) s.groups = []
      if (!s.devices) s.devices = []
      if (s.activeGroupId == null) s.activeGroupId = null
      return s
    },
    // 非钢场景本地静态刷新：耗能设备功率（MW）× 电网排放因子 → 范围二折碳（kgCO₂/h）。
    // 功率口径：本工序附加的**功率型传感器**读数（如有功功率 kW，可来自数据源管理实测设备 /
    // 模拟值 / 随可变设备联动）优先；未添加功率传感器时回落包内工序功率参数（出厂设定）。
    // 可变设备的设定值只调工况，不参与折碳。
    // 不请求后端碳引擎（steel-carbon 仅识别标准工艺类型），供孪生/KPI/属性面板展示。
    _otherSceneRefresh() {
      this.compileSchemeToModel()
      const gridKg = this._gridFactorKg()
      const date = new Date().toISOString()
      const srcMap = _boxSrcMap(this)
      const now = Date.now()
      const totals0 = {}
      const prevT = (this.baseline && this.baseline.totals) || {}
      for (const k of Object.keys(prevT)) totals0[k] = 0
      const dict = this.sceneCtx || null
      const units = (this.model.units || []).map((u) => {
        const packKW = (Number((u.params && u.params.power != null) ? u.params.power : 0) || 0) * 1000   // 包模板功率以 MW 计
        const meas = _attachedSensorPower(u, srcMap, now, this.deviceSetpoints)
        const powerKW = meas ? meas.kW : packKW
        const indirectKg = powerKW * gridKg     // kgCO₂/h（范围二）
        const direct = _otherUnitDirect(u, dict, this.factors)   // tCO₂/h（范围一，按包内 emissions 声明）
        return {
          ...u,
          // 注意：不把功率来源传感器塞进 u.devices —— 这些附加设备已由 allDevices 的
          // attached[] 分支合成为设备（id 相同），重复列出会造成设备树重复与详情定位歧义。
          devices: [],
          ..._otherUnitMetrics(powerKW, indirectKg, direct.t),
          directItems: direct.items,            // 直接排放构成（燃料 / 过程），供属性面板展示
          packPowerKW: packKW,  // 包内功率参数（出厂设定）
          powerMeasured: !!(meas && meas.measured),    // 实测功率（数据源绑定的采集设备）
          powerSimulated: !!(meas && meas.simulated),  // 模拟/固定值来源
          powerSources: meas ? meas.sources : [],
        }
      })
      const carbonTotal = units.reduce((a, u) => a + (u.carbon || 0), 0)
      const energyTotal = units.reduce((a, u) => a + (u.energy || 0), 0)
      const directTotal = units.reduce((a, u) => a + (u.co2_direct || 0), 0)
      const indirectTotal = units.reduce((a, u) => a + (u.co2_indirect || 0), 0)
      this.baseline = {
        units,
        flows: this.model.flows,
        totals: {
          ...totals0,
          carbon: carbonTotal,                  // kgCO₂/h（本场景口径，直接 + 间接）
          energy: energyTotal,                  // kWh/h
          // 碳引擎口径（全厂总览 KPI）：范围一 = 包内声明的燃料燃烧 / 工业过程排放；
          // 范围二 = 耗电折碳（未声明直接排放的场景则全部为范围二，与旧口径一致）
          co2_total: directTotal + indirectTotal,   // tCO₂/h
          co2_direct: directTotal,                  // 范围一（燃料燃烧 / 脱硫过程等）
          co2_indirect: indirectTotal,              // 范围二（外购电 / 厂用电折碳）
          energy_total: energyTotal * 0.0036,   // GJ/h
          elec: energyTotal / 1000,             // MWh/h
        },
        date,
        meta: {},
      }
      this.strategy = null
      this.delta = null
    },
    // 实时折碳轻量重算：不重编译模型、不清策略库，仅用当前实时读数（含附加功率型传感器的实测功率）
    // 刷新 baseline.units 的功率 / 碳排与总量。由遥测馈送（1 Hz）在非钢场景调用，
    // 使「实测功率」一旦有值就能在孪生 / KPI / 属性面板的折碳上即时体现（口径与 _otherSceneRefresh 一致）。
    _otherSceneRecarbon() {
      if (this.sceneMode === 'steel' || this.sceneId === 'steel') return
      if (!this.baseline || !Array.isArray(this.baseline.units) || !this.model || !Array.isArray(this.model.units)) return
      const gridKg = this._gridFactorKg()
      const srcMap = _boxSrcMap(this)
      const now = Date.now()
      const prevMap = new Map(this.baseline.units.map((u) => [u.id, u]))
      const dict = this.sceneCtx || null
      const units = this.model.units.map((mu) => {
        const prev = prevMap.get(mu.id) || {}
        const packKW = (Number((mu.params && mu.params.power != null) ? mu.params.power : 0) || 0) * 1000
        const meas = _attachedSensorPower(mu, srcMap, now, this.deviceSetpoints)
        const powerKW = meas ? meas.kW : packKW
        const indirectKg = powerKW * gridKg
        const direct = _otherUnitDirect(mu, dict, this.factors)
        return {
          ...prev,
          ..._otherUnitMetrics(powerKW, indirectKg, direct.t),
          directItems: direct.items,
          packPowerKW: packKW,
          powerMeasured: !!(meas && meas.measured),
          powerSimulated: !!(meas && meas.simulated),
          powerSources: meas ? meas.sources : [],
        }
      })
      const carbonTotal = units.reduce((a, u) => a + (u.carbon || 0), 0)
      const energyTotal = units.reduce((a, u) => a + (u.energy || 0), 0)
      const directTotal = units.reduce((a, u) => a + (u.co2_direct || 0), 0)
      const indirectTotal = units.reduce((a, u) => a + (u.co2_indirect || 0), 0)
      this.baseline = {
        ...this.baseline,
        units,
        totals: {
          ...(this.baseline.totals || {}),
          carbon: carbonTotal,
          energy: energyTotal,
          co2_total: directTotal + indirectTotal,
          co2_direct: directTotal,
          co2_indirect: indirectTotal,
          energy_total: energyTotal * 0.0036,
          elec: energyTotal / 1000,
        },
      }
    },
    // 电网排放因子（kgCO₂/kWh）：兼容钢包 factors.electricity.grid 与通用资源包 factors.grid_ef / factors.grid（tCO₂/MWh，数值上与 kgCO₂/kWh 同量）
    _gridFactorKg() {
      const f = this.factors || {}
      if (f.electricity && Number(f.electricity.grid)) return Number(f.electricity.grid)
      if (Number(f.grid_ef)) return Number(f.grid_ef)
      if (Number(f.grid)) return Number(f.grid)
      return 0.5703
    },
    // 切换核心孪生外围环绕环境（森林/城市/沙漠/海岸），触发中间 3D 场景重建
    setEnvMode(id) {
      if (id === this.envMode) return
      this.envMode = id
      this.envNonce++
    },
    // ---- 左侧活动栏面板切换 ----
    setActivityView(v) { this.activityView = v },
    // ---- 左栏面板显隐（面板头「⋯」菜单勾选）：全关时左栏为空，故调用方至少保留一个 ----
    toggleSidePanel(id) {
      if (!this.sidePanelOn || !(id in this.sidePanelOn)) return
      this.sidePanelOn[id] = !this.sidePanelOn[id]
    },
    setSidePanel(id, on) {
      if (!this.sidePanelOn || !(id in this.sidePanelOn)) return
      this.sidePanelOn[id] = !!on
    },
    // ---- 多数据源管理（连接面板 / 数据源对话框共用） ----
    // 新建数据源（返回新 id，供表单跳转）
    addDataSource(ds) {
      const id = (ds && ds.id) || 'src_' + Date.now()
      const src = Object.assign({ id, type: 'sim', url: '', interval: 1000, name: '新建数据源', enabled: true, mapping: {} }, ds, { id })
      const { cleaned, dropped } = this._stripBindingConflicts(id, src.mapping)
      src.mapping = cleaned
      if (dropped) this.showToast(t('已跳过 {n} 个与其它数据源冲突的设备映射：同一设备只能绑定一个数据源', { n: dropped }), 'warn')
      this.dataSources.push(src)
      this.activeDataSourceId = id
      this.dataSource = src
      this._saveDataSource()
      this._connectFeed()
      return id
    },
    // 更新数据源（连接参数 / 字段对齐映射变化即重连）
    updateDataSource(id, patch) {
      const idx = this.dataSources.findIndex((s) => s.id === id)
      if (idx < 0) return
      let next = { ...this.dataSources[idx], ...patch, id }
      if (patch.mapping) {
        const { cleaned, dropped } = this._stripBindingConflicts(id, next.mapping)
        next = { ...next, mapping: cleaned }
        if (dropped) this.showToast(t('已跳过 {n} 个与其它数据源冲突的设备映射：同一设备只能绑定一个数据源', { n: dropped }), 'warn')
      }
      this.dataSources[idx] = next
      if (this.activeDataSourceId === id) this.dataSource = next
      this._saveDataSource()
      this._connectFeed()
    },
    removeDataSource(id) {
      if (id === 'sim') { this.toast = t('平台内置的「能碳一体机」数据源不可删除'); return }
      const idx = this.dataSources.findIndex((s) => s.id === id)
      if (idx < 0) return
      this.dataSources.splice(idx, 1)
      if (this.activeDataSourceId === id) {
        const next = this.dataSources.find((s) => s.enabled) || this.dataSources[0] || null
        this.activeDataSourceId = next ? next.id : 'sim'
        this.dataSource = next
      }
      this._saveDataSource()
      this._connectFeed()
    },
    // 切换「活动」数据源（多个源并存时仅指定活动源驱动状态栏等展示）
    setActiveDataSource(id) {
      const src = this.dataSources.find((s) => s.id === id)
      if (!src) return
      this.activeDataSourceId = id
      this.dataSource = src
      this._saveDataSource()
    },
    // 启用/停用数据源（停用即断开其连接）
    toggleDataSource(id) {
      const src = this.dataSources.find((s) => s.id === id)
      if (!src) return
      src.enabled = !src.enabled
      if (!src.enabled && this.activeDataSourceId === id) {
        const next = this.dataSources.find((s) => s.enabled) || this.dataSources[0]
        this.activeDataSourceId = next ? next.id : 'sim'
        this.dataSource = next
      }
      this._saveDataSource()
      this._connectFeed()
    },
    // 同一设备只能绑定一个数据源：返回除 exceptId 之外、已把该内部设备 id 映射为读数的数据源名称；未绑定返回 null
    isDeviceBoundByOther(deviceId, exceptId) {
      for (const s of this.dataSources || []) {
        if (s.id === exceptId) continue
        const m = s.mapping || {}
        if (Object.values(m).includes(deviceId)) return s.name || s.id
      }
      return null
    },
    // 剔除与其它数据源冲突 / 本数据源内重复的映射项（同一内部设备只能被一个数据源绑定一次）
    _stripBindingConflicts(id, mapping) {
      const cleaned = {}
      const seen = new Set()
      let dropped = 0
      for (const [ext, int] of Object.entries(mapping || {})) {
        if (!int || seen.has(int)) { dropped++; continue }
        if (this.isDeviceBoundByOther(int, id)) { dropped++; continue }
        seen.add(int)
        cleaned[ext] = int
      }
      return { cleaned, dropped }
    },
    _saveDataSource() {
      try { localStorage.setItem('sim_data_sources', JSON.stringify(this.dataSources)) } catch (e) {}
    },
    _loadDataSource() {
      // 新版：多数据源列表（localStorage 'sim_data_sources'）
      try {
        const raw = localStorage.getItem('sim_data_sources')
        if (raw) {
          const arr = JSON.parse(raw)
          if (Array.isArray(arr) && arr.length) {
            this.dataSources = arr.map((s) => Object.assign({ id: 'sim', type: 'sim', url: '', interval: 1000, name: '数据源', enabled: true, mapping: {} }, s))
          }
        }
      } catch (e) {}
      // 迁移旧版单源存储（localStorage 'sim_data_source'）
      if (!this.dataSources.length) {
        try {
          const old = localStorage.getItem('sim_data_source')
          if (old) {
            const d = JSON.parse(old)
            if (d && d.type) {
              d.id = 'sim'; d.enabled = d.enabled !== false; d.mapping = d.mapping || {}
              this.dataSources = [d]
            }
          }
        } catch (e) {}
      }
      if (!this.dataSources.length) {
        // 默认连接：平台 MQTT 实时订阅（能碳一体机/中间件发布链路）。数据源接入与启停的统一管理
        // 在「能碳一体机管理 → 数据源接入」区块（数据源目录 config/data_sources.json，含中间件接入的
        // 外部数据与模拟数据）；此处仅为「仿真驱动连接」的工作副本。
        this.dataSources = [
          { id: 'sim', type: 'sim', url: '', interval: 1000, name: '能碳一体机', enabled: true, mapping: {} },
        ]
      }
      // v3 精简：保留既有的能碳一体机数据源（与外部 MQTT 订阅 + 字段绑定同通道）。
      // 移除 ws/http 等自定义类型与多余实例（若有），固定 id=type，规范化名称。
      const v3Canonical = []
      for (const s of this.dataSources || []) {
        if (!s || s.type !== 'sim') continue
        const c = v3Canonical.find((x) => x.type === s.type)
        if (c) {
          c.mapping = { ...(s.mapping || {}), ...(c.mapping || {}) }
          if (s.enabled) c.enabled = true
          if (s.interval) c.interval = s.interval
        } else {
          v3Canonical.push({ ...s, id: s.type })
        }
      }
      if (!v3Canonical.some((s) => s.type === 'sim')) {
        v3Canonical.unshift({ id: 'sim', type: 'sim', url: '', interval: 1000, name: '能碳一体机', enabled: true, mapping: {} })
      }
      for (const s of v3Canonical) {
        if (s.type === 'sim' && (!s.name || s.name === 'Mqtt 实时数据' || s.name.indexOf('Mqtt') === 0)) s.name = '能碳一体机'
      }
      this.dataSources = v3Canonical
      this._saveDataSource()
      const active = this.dataSources.find((s) => s.id === this.activeDataSourceId)
        || this.dataSources.find((s) => s.enabled) || this.dataSources[0]
      this.activeDataSourceId = active.id
      this.dataSource = active
    },
    // 发起相机聚焦请求（左栏或 3D 点击选中任意要素时调用）
    requestFocus(kind, id) { this.focusKind = kind; this.focusId = id; this.focusNonce++ },
    viewUnit(id, mode = 'focus') { this.viewId = id; this.viewMode = mode; this.viewNonce++ },
    selectUnit(id) { this._clearBrowse(); this.selectedMaterialId = null; this.selectedGroupId = null; this.selectedFlowId = null; this.deviceDetailId = null; this.selectedUnitId = id; this.inspectorView = 'auto'; this.rightOpen = true; this.requestFocus('unit', id) },
    setAutoRotate(v) { this.autoRotate = v },
    setBrightness(v) { this.brightness = v },
    // ---- 工艺级策略管理 ----
    // 为指定工序设置策略文本
    setUnitStrategyText(unitId, text) {
      if (!this.unitStrategies[unitId]) this.unitStrategies[unitId] = { enabled: true, text: '', parsed: null, delta: null, scenarioName: '' }
      this.unitStrategies[unitId].text = text
    },
    // 为指定工序解析并运行策略实验
    async runUnitStrategy(unitId) {
      const us = this.unitStrategies[unitId]
      if (!us || !us.text) { this.toast = t('请先输入策略文本'); return }
      this.parsing = true
      try {
        const parsed = await api.parse(us.text, this.model)
        us.parsed = parsed
        this.parsed = parsed
        this.parsedText = us.text
      } finally { this.parsing = false }
      if (!us.parsed || !us.parsed.ops.length) { this.toast = t('策略解析无有效操作'); return }
      this.busy = true
      try {
        const r = await api.simulate(this._applyDeviceOpParams(this.model), us.parsed.ops, this.factors)
        us.delta = r.delta
        this.delta = r.delta
        this.strategy = r.strategy
        if (this.simMode) {
          this.simOps = JSON.parse(JSON.stringify(us.parsed.ops || []))
          this.simCurrent = r.strategy ? JSON.parse(JSON.stringify(r.strategy)) : null
          const uname = (this.model.units.find((x) => x.id === unitId) || {}).name || unitId
          this._simLog('strategy', t('{name} · 工序策略', { name: uname }), (us.text || '').slice(0, 60), `us_${unitId}`)
        }
        this.sceneRev++
      } finally { this.busy = false }
      this.toast = t('策略仿真测试完成，可查看对比结果。')
    },
    // 保存策略并绑定到工序
    async saveUnitStrategy(unitId, name) {
      const us = this.unitStrategies[unitId]
      if (!us || !us.parsed || !us.parsed.ops.length) { this.toast = t('暂无有效的策略可保存'); return }
      const sname = name || (us.text ? us.text.slice(0, 30) : '未命名策略')
      await api.createStrategy(sname, '', us.text, us.parsed.ops)
      await this.loadStrategies()
      this.unitStrategies[unitId].scenarioName = sname
      this.toast = t('策略已保存并绑定到当前工序')
    },
    // 运行所有已启用的工序策略
    async runAllEnabledStrategies() {
      const enabled = Object.entries(this.unitStrategies).filter(([, v]) => v.enabled && v.parsed)
      if (!enabled.length) { this.toast = t('没有已启用的策略可运行'); return }
      this.busy = true
      try {
        const allOps = enabled.flatMap(([, v]) => v.parsed ? v.parsed.ops : [])
        const r = await api.simulate(this._applyDeviceOpParams(this.model), allOps, this.factors)
        this.strategy = r.strategy
        this.delta = r.delta
        if (this.simMode) {
          this.simOps = JSON.parse(JSON.stringify(allOps || []))
          this.simCurrent = r.strategy ? JSON.parse(JSON.stringify(r.strategy)) : null
          this._simLog('strategy', t('运行全部策略'), t('已启用 {n} 个工序策略', { n: enabled.length }), 'all')
        }
        this.sceneRev++
      } finally { this.busy = false; }
      this.toast = t('已运行 {n} 个工序策略', { n: enabled.length })
    },
    // 获取工序策略状态（供组件查询）
    getUnitStrategy(unitId) { return this.unitStrategies[unitId] || null },
    // 虚拟巡视开关：以一个小机器人视角沿工艺旁地面巡视完整流程；开启时关闭自动环视
    togglePatrol() {
      this.patrolOn = !this.patrolOn
      if (this.patrolOn && this.autoRotate) this.autoRotate = false
    },
    // 更新排放因子配置并重新仿真（null 表示恢复后端默认）
    setFactors(factors) {
      this.factors = factors
      this.refresh()
    },
    // ---- 编辑态：撤销 / 重做 ----
    // 在每次会改变 scheme 的编辑「之前」调用：把当前方案快照压入 past，清空 future。
    // key 相同且在合并窗口内的连续编辑（如拖动节点、滑动滑块）只保留首个快照，合成一步。
    _histCapture(key) {
      const now = Date.now()
      if (_histKey === key && now - _histTime < HIST_COALESCE_MS) { _histTime = now; return }
      this.historyPast.push(cloneScheme(this.scheme))
      if (this.historyPast.length > 200) this.historyPast.shift()
      this.historyFuture = []
      _histKey = key
      _histTime = now
    },
    _restore(scheme) {
      this.scheme = scheme
      if (this.selectedFlowId && !this.scheme.nodes.find((n) => n.id === this.selectedFlowId)) this.selectedFlowId = null
      // 返回目标工艺失效（被删除/重建）则清空
      if (this.flowBackId && !this.scheme.nodes.find((n) => n.id === this.flowBackId)) this.flowBackId = null
      // 小组相关选中态校验：节点被删/移出组后，若选中的小组不再存在则清空
      if (this.selectedGroupId && !this.scheme.groups.find((g) => g.id === this.selectedGroupId)) this.selectedGroupId = null
      if (this.scheme.activeGroupId && !this.scheme.groups.find((g) => g.id === this.scheme.activeGroupId)) this.scheme.activeGroupId = null
    },
    undo() {
      if (!this.historyPast.length) return
      this.historyFuture.unshift(cloneScheme(this.scheme))
      this._restore(this.historyPast.pop())
      _histKey = null
    },
    redo() {
      if (!this.historyFuture.length) return
      this.historyPast.push(cloneScheme(this.scheme))
      this._restore(this.historyFuture.shift())
      _histKey = null
    },
    // ---- 编辑态：流程编排 ----
    enterEdit() {
      // 欢迎页（未打开工程）：编排画布属于具体工程，先引导打开工程
      if (this.welcomeOn) { this.toast = t('请先打开工程：在内容区新建或打开场景'); return }
      this.editMode = true
      // 彻底清空右侧选中（含策略 / AI 模型），避免残留选中项把编排属性顶成策略属性：
      // 面板一律由用户在画布上点击节点（selectFlow）时才弹出，进入编排不自动开任何面板
      this.closeInspector(true)
      // 不再强制展开右栏：用户收起过则保持收起，点击画布节点时 selectFlow 会自行展开
      // 方案是单一真源：不重新从孪生模型反向编译，保持上次完成编排时的确切状态。
      // 若方案为空（首次进入），以当前路线构建默认方案。
      if (!this.scheme || !this.scheme.nodes || this.scheme.nodes.length === 0) {
        const route = this.processRoute || 'short'
        this.scheme = this._buildSceneScheme(route)
        // 首次进入编排、方案为空时以默认方案兜底：这属于「显式载入」而非编辑，同步为已应用方案
        this._syncAppliedScheme()
        // 重建 scheme 会触发 _bindSchemeDirty 的 deep watch 把 schemeDirty 置 true，
        // 但用户此时并未做任何编辑，应显式恢复为未保存状态 false
        this.schemeDirty = false
        nextTick(() => { this.schemeDirty = false })
      }
      if (!this.appliedScheme) this._syncAppliedScheme()   // 兜底：已应用快照缺失时以当前方案为基准
      // 保证小组容器字段存在（存量方案/旧 localStorage 可能缺失）
      if (!this.scheme.groups) this.scheme.groups = []
      if (this.scheme.activeGroupId == null) this.scheme.activeGroupId = null
      this.selectedFlowId = null
      this.selectedGroupId = null
      // 进入编辑态从顶层画布开始（不在某个小组子编排内）
      this.scheme.activeGroupId = null
      // 进入编辑态时清空历史，以当前方案为基准
      this.historyPast = []
      this.historyFuture = []
      _histKey = null
      // 触发 3D 计量设备标签重新布局（进入/退出编辑流程均重排，确保位置与计数正确）
      this.sceneRev++
      // 编排以 tab 窗口形式打开：进入编排即开一个「流程编排」标签并激活，
      // 可自由切到三维仿真 / 其它视图标签查看，再切回继续编排（草稿不丢），关闭标签即完成编排
      this.openView('flowEdit')
    },
    exitEdit() {
      // 退出编排**不应用**未保存的草稿：3D 孪生 / KPI / 设备树仍显示上次保存的方案。
      // 编排改动生效的唯一出口是 saveScheme()（保存）→ _applyScheme()，见 appliedScheme 说明。
      this.scheme.activeGroupId = null   // 退出编排后 3D 孪生回到顶层场景
      if (this.appliedScheme) this.appliedScheme.activeGroupId = null
      // 先置非编辑态再关 tab：closeViewById('flowEdit') 依赖此标志区分「完成编排」与「普通关闭」
      this.editMode = false
      // 退出编排后右侧「编排属性」面板失去承载对象：彻底清空选中（回到总览），
      // 避免画布最后点选的节点继续占着右栏（此前表现：退出编排后右侧仍停在编排属性面板）。
      // 放在 closeViewById 之前，让切到相邻 tab（如 AI 群控）时备份到的是编排态的右栏状态
      // 「本析智擎」是用户显式切换的右侧模式（非编排属性），退出编排不应把它一起关掉
      const keepAgent = this.inspectorView === 'agent'
      this.closeInspector(true)
      if (keepAgent) this.inspectorView = 'agent'
      this.closeViewById('flowEdit')
      // 收起右栏：编排态下右栏专为编排属性服务，退出后不留空面板占位；
      // 后续点选任意工序 / 设备 / 物料时由各自的 select* 自动重新展开
      this.rightOpen = keepAgent
      // 手动保存：完成编排（关闭编排标签）不再自动落盘，有未保存改动时明确提示
      // 未保存的改动也不会应用到孪生 —— 孪生仍显示上次保存的方案，保存后才按新编排更新
      if (this.schemeDirty) this.showToast(t('编排改动尚未保存：数字孪生仍显示上次保存的方案，点工具条「保存」后生效'), 'warn')
      else this.toast = t('已应用编排方案，刷新孪生视图')
      // sceneRev 的触发由 SceneViewer 的 flowEditing watch 统一管理，
      // 确保 DOM 可见 + resize 完成后再 rebuildScene，避免 canvas 0x0 导致相机投影矩阵 NaN
    },

    loadTemplate(route) {
      // 先确认当前场景确有该模板：此前找不到会静默 fallback 到本场景第一个模板，
      // 还把 processRoute 改成该场景并不存在的 id（如机房温控下载入 'long'），
      // toast 却仍报「已载入长流程炼钢模板」——表现为「点了模板没变化」。
      const tpl = (this.sceneTemplates || []).find((x) => x.id === route || x.route === route)
      if (!tpl) {
        this.showToast(t('当前场景没有该模板'), 'warn')
        return false
      }
      this._histCapture('tmpl_' + uid('h'))
      this.processRoute = route
      this.scheme = this._buildSceneScheme(route)
      // 保证模板方案的 group 容器字段齐全（buildScheme 返回的 groups/activeGroupId）
      if (!this.scheme.groups) this.scheme.groups = []
      if (this.scheme.activeGroupId == null) this.scheme.activeGroupId = null
      this.selectedFlowId = null
      this.selectedGroupId = null
      this._markDirty()      // 载入模板属于编辑：只置未保存标记，由「保存」按钮落盘
      // 路线不再写 localStorage：流程路线与编排同属一份服务端存档，本地不留副本（单一真源）
      // 载入模板是编辑动作：不重编译 model，孪生 / 设备树 / KPI 仍显示旧模板，
      // 点「保存」后由 _applyScheme() 统一重编译（否则未保存的换模板会直接改掉孪生）。
      // 编排模式下载入模板后自动适配视图：新方案分行排布，让画布尽量占满屏幕
      if (this.editMode) this.flowZoomFit()
      // 用实际命中的模板名，不再按 route 猜（非钢场景也有自己的模板名）
      this.toast = t('已载入模板「{name}」', { name: tpl.label || tpl.id || route })
      return true
    },
    // 手动保存：编排唯一落盘入口（工具条「保存」按钮 / Ctrl+S）。
    // 本地存档 + 服务端 designs/flow 一次写入；未保存前刷新页面，改动按设计丢弃。
    // 保存同时是「编排生效」的时刻：把当前方案固化为已应用方案并重编译 model，
    // 3D 数字孪生 / 2D 工艺图 / KPI / 设备树自此才切换到新编排（未保存前一律保持旧方案）。
    async saveScheme() {
      if (this.simMode) { this.showToast(t('仿真模式下的改动不会保存，退出仿真后自动恢复'), 'warn'); return false }
      // 上次读取服务端存档失败时，保存前先重拉一次：服务端其实有档而本端画面是默认模板的话，
      // 这一保存就会把线上真档盖成默认 —— 直接拦下并让用户刷新载入真档再改。
      if (_designPullState === 'error') {
        const remote = await this._pullScheme(this.sceneId || 'steel')
        if (remote) {
          this.showToast(t('服务端存在该场景的编排存档：请刷新页面载入后再编辑，避免覆盖线上方案'), 'error')
          return false
        }
      }
      if (!this._saveScheme()) return false   // 服务端存档不可写（读取失败）：已提示原因，不谎报「已保存」
      this._applyScheme()
      this.showToast(t('编排已保存'), 'success')
      return true
    },
    // 编排改动检测（替代原自动保存）：
    // 任何场景（钢铁 / 资源包）下的编辑（增删节点、连线、参数、设备设定、物料覆盖）只置
    // schemeDirty，由工具条「保存」按钮呈现「未保存」并落盘；此处绝不写入任何存档。
    _bindSchemeDirty() {
      if (_schemeDirtyBound) return
      _schemeDirtyBound = true
      watch(
        () => [this.scheme, this.processRoute, this.materialOverrides, this.deviceSetpoints, this.deviceExtraSetpoints],
        () => {
          // 群控策略每轮自动写设定值也会进这里（deviceSetpoints 变更）—— **必须跳过**：
          // 那会把本端手里这份 scheme 每 800ms 整档 PUT 上去，而 flow 桶是整档覆盖写，
          // 于是任何一个持有旧 scheme 的客户端（另一个浏览器 / 标签页）就能把别人刚加的
          // 附加传感设备整片抹掉 —— 表现为「一运行 AI 群控，编排就被还原」。
          if (_autoSetpointGuard > 0) return
          this.schemeDirty = true
        },
        { deep: true },
      )
      // 手动保存的配套保护：有未保存改动时关闭 / 刷新页面给浏览器原生二次确认（仿真态编辑本就不落盘，不提示）
      window.addEventListener('beforeunload', (e) => {
        if (!this.schemeDirty || this.simMode) return
        e.preventDefault()
        e.returnValue = ''
      })
    },
    // 标记「有未保存改动」：编辑类操作显式调用，避免只靠 watch 时的时序歧义
    _markDirty() { this.schemeDirty = true },

    // ── 跨端同步：一律不做 ────────────────────────────────────────────────────
    // 编排的唯一真源仍是服务端 designs/flow，但**不再有任何定时推 / 拉**：
    //   · 编辑不写服务端（只置 schemeDirty，等用户点「保存」）；
    //   · 也不轮询拉其它端的改动（否则本端画面会被另一端悄悄改写）；
    // 谁保存谁写入服务端，另一端刷新页面 / 打开工程 / 切场景（_pullScheme）时才取到最新。
    // 两端同时编辑同一份编排 → 最后保存的那一版覆盖之前的（last-writer-wins），不做合并。
    // 「文件 → 另存为场景…」：把当前场景（默认含当前编排方案快照）打包为可分发的 .ec 资源包下载。
    // 导出包为非内置分发包，重新导入后即回到当前编排态。
    async exportSceneAsPackage({ label, industry, version, vendor, product, withScheme = true } = {}) {
      const payload = {
        scene_id: this.sceneId,
        meta: { label: label || undefined, industry: industry || undefined },
        package: { version: version || undefined, vendor: vendor || undefined, product: product || undefined },
        templates: withScheme
          ? [{ id: 'current', route: this.processRoute, name: label || t('当前编排方案'), scheme: JSON.parse(JSON.stringify(this.scheme)) }]
          : undefined,
      }
      const { blob, filename } = await api.exportSceneBlob(payload)
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename || `${this.sceneId}.ec`
      document.body.appendChild(a)
      a.click()
      a.remove()
      setTimeout(() => URL.revokeObjectURL(url), 4000)
      return filename
    },
    // 恢复设备设定值：scheme.devices 里的 setpoint（工艺可调设备）+ 存档里的 deviceSetpoints。
    // 附加设备（ext::节点id::attUid，附加传感 / 可变设备）不在 scheme.devices 中，其调节值
    // 只存在于 deviceSetpoints —— 必须与方案一并存取，否则刷新后一律回落到模板默认值。
    _restoreSetpoints(saved) {
      const sps = {}
      const esps = {}
      for (const d of (this.scheme.devices || [])) {
        if (d && d.id && d.setpoint != null) sps[d.id] = d.setpoint
        if (d && d.id && d.extraSetpoints && typeof d.extraSetpoints === 'object') esps[d.id] = d.extraSetpoints
      }
      const s2 = saved && typeof saved.deviceSetpoints === 'object' && saved.deviceSetpoints ? saved.deviceSetpoints : {}
      const e2 = saved && typeof saved.deviceExtraSetpoints === 'object' && saved.deviceExtraSetpoints ? saved.deviceExtraSetpoints : {}
      this.deviceSetpoints = { ...sps, ...s2 }
      this.deviceExtraSetpoints = { ...esps, ...e2 }
    },
    // 落盘当前编排方案「载荷」：编排 + 路由 + 物料覆盖 + 设备设定值是一份整体档案，
    // 任何一侧单独写都会把另一侧的字段抹成空（flow 桶按场景整档存），故统一由这里产出。
    _schemePayload() {
      return {
        sceneId: this.sceneId || 'steel',   // 编排方案所属场景包：切场景不串档
        route: this.processRoute,
        scheme: this.scheme,
        materialOverrides: this.materialOverrides,
        // 设备设定值随方案持久化：附加传感 / 可变设备的调节值只存在于此（不在 scheme.devices 内）
        deviceSetpoints: this.deviceSetpoints,
        deviceExtraSetpoints: this.deviceExtraSetpoints,
        _ovUnitV: 1,   // 价格口径标记：v1 起 price/salePrice 统一为「万元/单位」（旧版存的是元/单位）
        updatedAt: Date.now(),   // 存档时间戳：服务端/本地两份冲突时取较新的一份
      }
    },
    // 落盘当前编排方案（手动保存 / 场景切换 / 旧档迁移时调用）：
    // 本地 localStorage + 服务端 designs/flow，使刷新后保持最后一次保存的编排结果。
    _saveScheme() {
      if (this.simMode) return   // 仿真模式：一切编辑不持久化
      // 服务端存档没读成功（接口异常 / 存档被拒收）时**绝不落盘**：
      // 此刻内存里的方案是按包模板重建的默认编排，写回去就把用户保存过的编排永久抹掉了。
      if (_designPullState === 'error') {
        this.showToast(t('服务端编排未能读取，已阻止写入以免覆盖线上存档：请刷新页面重试'), 'error')
        return false
      }
      const payload = this._schemePayload()
      // 服务端存档 backend/data/designs/flow.json 是跨端真源（不随代码推送同步）。
      // 手动保存为显式动作，这里直接 PUT（不再防抖）。整档覆盖写：这一版即成为服务端最新，
      // 后保存的端覆盖先保存的端（last-writer-wins）。
      // 失败必须让用户看见：此前 catch 静默，用户以为「已保存」，刷新后回到默认编排。
      try {
        const send = () => api.designSave('flow', payload.sceneId, payload)
        send().catch(() => {
          // 一次重试：偶发网络抖动不至于丢掉用户这次保存
          send().catch(() => {
            this.schemeSavedAt = 0
            this.showToast(t('编排保存失败：服务端未写入，请检查网络后重试'), 'error')
          })
        })
      } catch (e) {
        this.schemeSavedAt = 0
        this.showToast(t('编排保存失败：服务端未写入，请检查网络后重试'), 'error')
        return false
      }
      this.schemeDirty = false
      this.schemeSavedAt = Date.now()
      // 兜底：保存前若刚改过 scheme，深度 watch 的回调会在其后触发并重标脏 —— 这里再清一次
      nextTick(() => { this.schemeDirty = false })
      return true
    },
    // 从服务端取回本场景的编排存档：**服务端为准**（服务器实例是编排的权威侧）。
    // 只要服务端有该场景的存档就无条件采用 —— 本地 localStorage 仅作离线兜底，
    // 不再按 updatedAt 比对（否则本地那份较新的旧档会盖住服务器上的编排，两端永远不同步）。
    // 返回值与「读取结果」分开：结果写进模块级 _designPullState（ok / empty / error），
    // 调用方据此决定能否落盘（详见 _saveScheme 与 openScene 的守卫）。
    async _pullScheme(sceneId) {
      const sid = sceneId || this.sceneId || 'steel'
      let r = null
      try {
        r = await api.designBucket('flow')
      } catch (e) {
        // 一次重试：编排存档读取失败代价极大（会用默认模板重建并可能覆盖真档）
        try { r = await api.designBucket('flow') } catch (e2) { _designPullState = 'error'; return null }
      }
      const remote = (r && r.data) ? r.data[sid] : null
      if (!remote) { _designPullState = 'empty'; return null }
      // 存档存在但被判为不可用（结构损坏 / 场景不匹配）：同样按「不确定」处理，禁止回写
      if (!this._schemeAccepted(remote, sid)) { _designPullState = 'error'; return null }
      _designPullState = 'ok'
      return remote
    },
    // 本地兜底存档已废止（2026-10-14）：编排的唯一真源是服务端 designs/flow，**浏览器不再留存任何
    // 编排副本**（历史遗留的 'sim.scheme' / 'sim.scheme::<scene>' 键由 _purgeLocalDesignCache 清理）。
    // 服务端拉不到就是没有存档，按包模板重新构建 —— 避免本地旧档盖住服务端的新版本造成两端不一致。
    _loadScheme() { return null },
    // 一次性清理：历史上留在浏览器的编排 / 群控副本（它们会盖住服务端真源，是两端不一致的元凶）
    _purgeLocalDesignCache() {
      try {
        const drop = []
        for (let i = 0; i < localStorage.length; i++) {
          const k = localStorage.key(i)
          if (!k) continue
          if (k === 'sim.scheme' || k.startsWith('sim.scheme::') || k === 'sim.processRoute'
            || k.startsWith('nengtan.agc')) drop.push(k)
        }
        for (const k of drop) localStorage.removeItem(k)
      } catch (e) { /* localStorage 不可用时忽略 */ }
    },
    // 编排存档可用性校验：结构完整性 + 场景隔离。
    // 说明：此处**只做能否恢复的结构判定**，不做业务口径判定 —— 机房温控曾经在这里按
    // 「必须包含某某附加设备 / 节点类型必须在白名单内」判定旧口径存档并整档丢弃，结果把用户
    // 主动删除某个传感器、或新增自定义节点的合法编排也误判为旧档，刷新后方案被重建并覆盖存档
    // （表现为「场景被莫名其妙重置」）。旧口径一律改为恢复后就地迁移（见 _migrateDcScheme）。
    _schemeAccepted(d, sceneId) {
      try {
        if (!d || !d.scheme || !Array.isArray(d.scheme.nodes) || d.scheme.nodes.length === 0) return false
        // 编排方案随场景包隔离：只恢复与当前打开场景匹配的存档。
        // 无 sceneId 标记的旧存档一律归属默认钢场景 —— 否则打开火电 / 机房温控等新场景时，
        // 会把那份无标记的钢方案当成「本场景存档」恢复，表现为切了场景但画布还是钢铁流程
        // （且方案随后被存成该场景的存档，越修越乱）。
        const sid = sceneId || this.sceneId || 'steel'
        if (d.sceneId && d.sceneId !== sid) return false
        if (!d.sceneId && sid !== 'steel') return false
        // 内容归属校验：只比对 sceneId 挡不住「别的场景的画布被存成了本场景存档」这类脏档
        // （切换场景的瞬间旧画布尚未重建就被存下 → 火电存档里存的是钢铁流程，之后每次打开
        // 火电都恢复成钢铁画布）。判定必须弱：只有**全部工序类型都不属于本场景包**时才拒绝，
        // 免得把用户删掉传感器 / 新增节点的合法编排也误判为脏档（历史教训，见上）。
        return this._schemeTypesMatch(d.scheme, sid)
      } catch (e) { return false }
    },
    // 方案里的工序类型是否属于当前场景包：非钢场景才校验，钢场景与包未就绪时不校验。
    _schemeTypesMatch(scheme, sceneId) {
      const sid = sceneId || this.sceneId || 'steel'
      if (sid === 'steel') return true
      const allow = new Set()
      for (const t of (this.sceneTemplates || [])) {
        for (const n of ((t && t.scheme && t.scheme.nodes) || [])) if (n && n.type) allow.add(n.type)
      }
      for (const p of ((this.sceneCtx && this.sceneCtx.processes) || [])) if (p && p.type) allow.add(p.type)
      if (!allow.size) return true     // 包尚未装载：不做判定，交由 openScene 按模板重建
      const types = ((scheme && scheme.nodes) || []).map((n) => n && n.type).filter(Boolean)
      if (!types.length) return true
      return types.some((t) => allow.has(t))
    },
    // 采纳一份编排方案：补齐容器字段 + 按场景做口径迁移。init 恢复与 openScene 装载共用，
    // 保证两条路径的兜底与迁移口径一致。
    _adoptScheme(scheme, sceneId) {
      const s = scheme || { nodes: [], connections: [], devices: [], groups: [], activeGroupId: null }
      // 记录「采纳过程是否真的改动过内容」：openScene 依此决定要不要回写服务端 ——
      // 内容没变就不写（打开场景是只读动作，不该产生会覆盖别的端存档的写）。
      _schemeAdoptChanged = false
      const _before = JSON.stringify(s)
      if (!s.groups) s.groups = []
      if (s.activeGroupId == null) s.activeGroupId = null
      // 非钢场景模板方案没有 devices 字段，补齐为数组——否则 setDeviceSetpoint 等
      // 一律按 scheme.devices.find 访问会抛 TypeError，导致设定值写入后 _saveScheme/refresh 中断
      if (!s.devices) s.devices = []
      if ((sceneId || this.sceneId) === 'dc-thermal') this._migrateDcScheme(s)
      this._mergeTemplateStructure(s, sceneId)
      _schemeAdoptChanged = _before !== JSON.stringify(s)
      return s
    },
    // 资源包模板结构升级：**增量补齐**模板新增的节点 / 小组 / 连线到已有存档。
    // 场景包扩展时（例如给火电各系统新增「系统内部的能源设备」并把系统升级为小组），
    // 老存档里没有这些新结构；整档按模板重建会连用户的编排一起丢掉，故只补缺失项，
    // 已有的节点 / 连线 / 用户改过的参数一律保持原样。模板侧以 scheme.structRev 标记结构版本。
    _mergeTemplateStructure(s, sceneId) {
      try {
        const sid = sceneId || this.sceneId || 'steel'
        if (sid === 'steel') return s
        const route = this.processRoute || s.route
        const list = this.sceneTemplates || []
        const tpl = list.find((x) => x && (!route || (x.route || x.id) === route)) || list[0]
        const ts = tpl && tpl.scheme
        if (!ts || !Array.isArray(ts.nodes)) return s
        const rev = Number(ts.structRev || 0)
        if (rev <= Number(s.structRev || 0)) return s
        if (!Array.isArray(s.nodes)) s.nodes = []
        if (!Array.isArray(s.connections)) s.connections = []
        if (!Array.isArray(s.groups)) s.groups = []
        const have = new Set(s.nodes.map((n) => n && n.id).filter(Boolean))
        let added = 0
        // 1) 补齐模板新增节点（含参数与附加设备），插在其所属系统节点之后
        for (const n of ts.nodes) {
          if (!n || have.has(n.id)) continue
          const copy = JSON.parse(JSON.stringify(n))
          const gid = copy.groupId
          let at = -1
          if (gid) {
            const g = (ts.groups || []).find((x) => x && x.id === gid)
            const owner = g && g.members && g.members.length ? g.members[0] : null
            if (owner) at = s.nodes.findIndex((x) => x && x.id === owner)
          }
          if (at >= 0) s.nodes.splice(at + 1, 0, copy)
          else s.nodes.push(copy)
          have.add(copy.id)
          added++
        }
        // 2) 补齐小组：新增的小组直接补入；已存在的小组按模板补齐成员
        const gmap = new Map(s.groups.map((g) => [g && g.id, g]))
        for (const g of (ts.groups || [])) {
          if (!g || !g.id) continue
          const cur = gmap.get(g.id)
          if (!cur) { s.groups.push(JSON.parse(JSON.stringify(g))); continue }
          const mem = new Set(cur.members || [])
          for (const m of (g.members || [])) mem.add(m)
          cur.members = Array.from(mem)
        }
        // 3) 补齐模板层新增的物料连线
        const cids = new Set(s.connections.map((c) => c && c.id).filter(Boolean))
        for (const c of (ts.connections || [])) {
          if (!c || cids.has(c.id)) continue
          s.connections.push(JSON.parse(JSON.stringify(c)))
        }
        // 4) 已存在的节点补齐 groupId（系统节点升级为小组容器）
        for (const tn of ts.nodes) {
          if (!tn || !tn.groupId) continue
          const cur = s.nodes.find((n) => n && n.id === tn.id)
          if (cur && !cur.groupId) cur.groupId = tn.groupId
        }
        s.structRev = rev
        if (added > 0) {
          this.pushCmd(t('资源包已升级：补齐 {n} 个新增对象（进入对应系统小组可查看）', { n: added }), 'cmd')
        }
      } catch (e) { /* 结构升级失败不影响方案恢复 */ }
      return s
    },
    // 机房温控（dc-thermal）旧口径存档就地升级（不丢弃用户编排）。
    // 2026-09-21 改版：① 水侧 + 风侧开式，删除「机房回风」回路；② 制冷风机的「半导体制冷电源」
    // 由通用可变电源 variable_psu（0~66000 V）改为专用 TEC 电源 tec_psu（0~60 V）；③ 冷却水的
    // 「循环水泵变频器」frequency_converter（Hz）改为「循环水泵变压器」pump_transformer（输出电压 V）。
    // 旧存档沿用旧类型会让详情面板量程 / 默认值与折碳口径对不上，但为此整档重建会连用户的
    // 节点、连线、命名一起丢掉 —— 故改为保留编排、只升级类型与量程。
    _migrateDcScheme(scheme) {
      // 旧附加设备类型 → 新类型
      const ATT_MAP = { variable_psu: 'tec_psu', frequency_converter: 'pump_transformer' }
      // 旧介质 → 新介质（已删除的「机房回风」）
      const MAT_MAP = { hot_air: 'cold_air', room_air: 'cold_air', return_air: 'cold_air' }
      const nodes = (scheme && Array.isArray(scheme.nodes)) ? scheme.nodes : []
      let changed = false
      for (const n of nodes) {
        if (!n) continue
        const ports = [].concat((n.ports && n.ports.in) || [], (n.ports && n.ports.out) || [])
        for (const p of ports) {
          if (p && MAT_MAP[p.material]) { p.material = MAT_MAP[p.material]; changed = true }
        }
        for (const a of (n.attached || [])) {
          const nt = a && ATT_MAP[a.type]
          if (!nt) continue
          const tpl = _attachTpl(a.kind || 'adjustable', nt)
          a.type = nt
          if (tpl) {
            if (tpl.label) a.label = tpl.label
            // 量程 / 默认值随新类型走：旧类型（0~66000 V、Hz）与新口径完全不同，留旧值会带偏详情面板
            a.def = tpl.kind === 'sensor' ? tpl.def : (tpl.setpoint ? tpl.setpoint.def : a.def)
            if (tpl.range) a.range = { ...tpl.range }
            if (tpl.scale) a.scale = { ...tpl.scale }
            a.src = tpl.kind === 'sensor' ? 'sim' : 'fixed'
          }
          changed = true
        }
      }
      // 介质迁移后可能出现重复连线（旧回风回路与新冷风回路同端点），按 端点+介质 去重
      const seen = new Set()
      const conns = []
      for (const c of (scheme.connections || [])) {
        if (!c) continue
        if (MAT_MAP[c.material]) { c.material = MAT_MAP[c.material]; changed = true }
        const k = `${c.from}>${c.to}:${c.material}`
        if (seen.has(k)) { changed = true; continue }
        seen.add(k)
        conns.push(c)
      }
      scheme.connections = conns
      return changed
    },
    // 以指定流程示例方案直接编译为 3D 模型（含工辅连线 + 统一布局），
    // 用于首屏默认流程（短流程）。与 exitEdit 的「完成编排」走同一套编译/布局逻辑，保证两模式一致。
    _setDefaultRoute(route) {
      this.scheme = buildScheme(route)
      this._syncAppliedScheme()
      this.compileSchemeToModel()
      this.autoLayout()
    },
    // 欢迎页打开项目：按流程路线（long 长流程 / short 短流程）重建方案并进入主界面
    openProject(route) {
      if (this.editMode) this.exitEdit()
      this.processRoute = route
      this.scheme = buildScheme(route)
      if (!this.scheme.groups) this.scheme.groups = []
      if (this.scheme.activeGroupId == null) this.scheme.activeGroupId = null
      this.deviceSetpoints = {}          // 新项目不带旧项目的设备设定
      this.deviceExtraSetpoints = {}
      this.selectedUnitId = null
      this._markDirty()                  // 新建项目属于编辑：只置未保存标记
      // 打开项目是显式载入（非编排编辑）：新方案立即生效，同步为已应用方案
      this._syncAppliedScheme()
      this.compileSchemeToModel()
      this.autoLayout()
      this.refresh()
      this.sceneRev++                    // 触发 3D 孪生按新方案重建
      this.entered = true
      const label = route === 'short' ? t('钢铁企业 · 短流程') : t('钢铁企业 · 长流程')
      this.toast = t('已打开项目：{label}', { label })
      this.pushCmd(t('已打开项目：{label}，已按全流程重建数字孪生。', { label }), 'cmd')
    },
    // 等待初始化完成（欢迎页进入前兜底，避免 init 未就绪时操作方案）
    async waitReady() {
      if (this.ready) return
      await new Promise((resolve) => {
        const iv = setInterval(() => {
          if (this.ready) { clearInterval(iv); resolve() }
        }, 80)
      })
    },
    // 仿真模式下流程结构已锁定：结构编辑不参与仿真前后对比，直接拒绝并提示
    //（仿真模式只预览参数/策略类调节；流程结构调整请先退出仿真再编排）
    _simEditBlocked() {
      if (!this.simMode) return false
      this.toast = t('仿真模式下流程结构已锁定：请先退出仿真再编排流程')
      return true
    },
    clearScheme() {
      if (this._simEditBlocked()) return
      this._histCapture('clear_' + uid('h'))
      this.scheme = { nodes: [], connections: [], devices: [], groups: [], activeGroupId: null }
      this.selectedFlowId = null
      this.selectedGroupId = null
      this._markDirty()      // 清空画布属于编辑：只置未保存标记
    },
    // 从左栏拖入创建节点（kind: process|device|material）
    // ===== 附加设备（传感器 / 可变设备）：绑定 / 解除 / 数值来源 =====
    // 在某工艺节点上添加一个附加设备（kind: sensor / adjustable，type 取附加库模板 type），
    // 实例存入工艺节点 node.attached[]（随方案持久化）；运行态 id 合成为 ext::节点id::attUid，
    // 在资源 / 设备树 / 数据分析中即出现相应设备。
    // name 为可选业务名称（如「1号泵出水温度」）；不传则按「类型名 + 实例序号」自动命名，
    // 且自动保证与同工序内其它附加设备不重名。
    addAttachToNode(nodeId, kind, type, name) {
      const node = this.scheme.nodes.find((n) => n.id === nodeId)
      if (!node) return null
      const tpl = _attachTpl(kind, type)
      if (!tpl) return null
      const att = {
        uid: uid('a'),
        kind,
        type,
        label: _uniqueAttachName(node, String(name == null ? '' : name).trim() || _defaultAttachName(node, kind, type)),
        // 传感器默认数值来源「随机模拟值」（可在属性面板切换为固定值 / 数据源设备 / 工艺参数 / 随可变设备联动）；
        // 可变设备不取数 —— 其数值就是设定值（只调运行工况），故固定为 'fixed' 且不显示数据源下拉。
        src: tpl.kind === 'sensor' ? 'sim' : 'fixed',
        param: null,       // src=param 时绑定的工艺数值参数 key
        device: null,      // src=device 时绑定的数据源管理设备名
        prop: null,        // src=device 时绑定的设备点位名
        def: tpl.kind === 'sensor' ? tpl.def : (tpl.setpoint ? tpl.setpoint.def : null),
      }
      if (!node.attached) node.attached = []
      node.attached.push(att)
      this._histCapture('att_' + nodeId + uid('h'))
      this._markDirty()
      return att
    },
    removeAttachFromNode(nodeId, uidToRemove) {
      const node = this.scheme.nodes.find((n) => n.id === nodeId)
      if (!node || !Array.isArray(node.attached)) return
      const i = node.attached.findIndex((a) => a.uid === uidToRemove)
      if (i < 0) return
      node.attached.splice(i, 1)
      this._histCapture('det_' + nodeId + uid('h'))
      this._markDirty()
      const extId = `ext::${nodeId}::${uidToRemove}`
      if (this.deviceDetailId === extId) this.deviceDetailId = null
    },
    // 重命名附加设备：名称随方案持久化，设备树 / 详情面板 / 规则编排 / 数据分析都以它作为显示标识。
    // 留空则回落为该类型的默认名；与同工序内其它附加设备重名时自动追加序号。
    // silent = true 用于输入框边打边预览（不逐字记撤销历史），失焦提交时才正式进历史。
    renameAttach(nodeId, uidToRename, name, silent) {
      const node = this.scheme.nodes.find((n) => n.id === nodeId)
      const att = node && Array.isArray(node.attached) ? node.attached.find((a) => a.uid === uidToRename) : null
      if (!att) return ''
      const tpl = _attachTpl(att.kind, att.type)
      const next = String(name == null ? '' : name).trim()
      att.label = _uniqueAttachName(node, next || (tpl ? tpl.label : att.type), uidToRename)
      if (!silent) this._histCapture('rnm_' + nodeId + uid('h'))
      this._markDirty()
      return att.label
    },
    // 设置附加设备的数值来源：
    //   { src: 'fixed' }                      固定值（模板默认）
    //   { src: 'sim' }                        随机模拟值
    //   { src: 'param', param }               工艺参数
    //   { src: 'device', device, prop }       数据源管理中的传感器设备点位实时读数
    //   { src: 'attach', devRef }             随同节点某附加可调设备的设定值联动（读数 = 设定值 × scale.to/scale.from）
    setAttachSource(nodeId, uidToSet, patch) {
      const node = this.scheme.nodes.find((n) => n.id === nodeId)
      const att = node && Array.isArray(node.attached) ? node.attached.find((a) => a.uid === uidToSet) : null
      if (!att) return
      if (patch && patch.src) att.src = patch.src
      if (patch && 'param' in patch) att.param = patch.param
      if (patch && 'device' in patch) att.device = patch.device
      if (patch && 'prop' in patch) att.prop = patch.prop
      if (patch && 'devRef' in patch) { att.devRef = patch.devRef; att.scale = null }
      if (patch && patch.scale) att.scale = patch.scale
      if (patch && 'def' in patch) att.def = patch.def
      // 首次切到「随附加可调设备联动」时按当下「设定值 → 读数」定标：绑定瞬间读数不变，之后随设定值线性变化
      if (att.src === 'attach' && (!att.scale || !Number(att.scale.from))) {
        const ref = _attachRef(node, att)
        const refTpl = ref ? _attachTpl(ref.kind, ref.type) : null
        const refId = ref ? `ext::${nodeId}::${ref.uid}` : null
        const refSp = ref
          ? Number(this.deviceSetpoints[refId] != null ? this.deviceSetpoints[refId]
            : (ref.def != null ? ref.def : (refTpl && refTpl.setpoint ? refTpl.setpoint.def : 0)))
          : 0
        const tpl = _attachTpl(att.kind, att.type)
        const toVal = att.def != null ? att.def : (tpl ? tpl.def : 0)
        att.scale = { from: Number.isFinite(refSp) && refSp ? refSp : 1, to: Number(toVal) || 0 }
      }
      this._histCapture('src_' + nodeId + uid('h'))
      this._markDirty()
      // 绑定变更立即生效：清掉该附加设备的陈旧遥测，让各界面 liveOf 落到现算读数
      // （否则 deviceLive 里绑定前按 sim/fixed 合成的旧值会永久遮蔽新绑定）
      const extId = `ext::${nodeId}::${uidToSet}`
      delete this.deviceLive[extId]
      delete this.deviceHistory[extId]
      this._sampleAttachedDevices(Date.now() / 1000)
    },
    // 切换「随附加可调设备联动」的定标基准（设定值锚点 → 读数锚点）：便于按额定工况重新标定
    setAttachLinkScale(nodeId, uidToSet, from, to) {
      const node = this.scheme.nodes.find((n) => n.id === nodeId)
      const att = node && Array.isArray(node.attached) ? node.attached.find((a) => a.uid === uidToSet) : null
      if (!att) return
      const f = Number(from)
      const v = Number(to)
      att.scale = { from: Number.isFinite(f) && f ? f : 1, to: Number.isFinite(v) ? v : 0 }
      this._histCapture('sc_' + nodeId + uid('h'))
      this._markDirty()
    },
    // 设置附加设备换算系数：读数 = 源值 × 系数（默认 1），
    // 用于系统模板单位与绑定传感器/采集设备实际度量不一致时的换算
    setAttachFactor(nodeId, uidToSet, factor, silent) {
      const node = this.scheme.nodes.find((n) => n.id === nodeId)
      const att = node && Array.isArray(node.attached) ? node.attached.find((a) => a.uid === uidToSet) : null
      if (!att) return
      const f = Number(factor)
      // 最多支持小数点后两位
      att.factor = isFinite(f) ? Math.round(f * 100) / 100 : 1
      // silent=输入过程实时预览：不记撤销历史（避免每个按键一条），失焦提交时才记
      if (!silent) this._histCapture('fx_' + nodeId + uid('h'))
      this._markDirty()
      this._sampleAttachedDevices(Date.now() / 1000)
    },
    // 按 extId（ext::节点id::attUid）反查附加设备与其节点
    _attachByExtId(extId) {
      const m = /^ext::(.+)::([^:]+)$/.exec(extId || '')
      if (!m) return null
      const node = (this.scheme.nodes || []).find((n) => n.id === m[1])
      const att = node && Array.isArray(node.attached) ? node.attached.find((a) => a.uid === m[2]) : null
      return att ? { node, att } : null
    },
    // 可变设备已绑定数据源设备的可写点位时，把设定值经 cmd/{box}/cmd 下发写入
    async writeAttachBound(extId, value) {
      const hit = this._attachByExtId(extId)
      if (!hit) return { ok: false, error: 'attach not found' }
      const { att } = hit
      if (att.src !== 'device' || !att.device || !att.prop) return { ok: false, error: 'unbound' }
      const v = Number(value)
      if (!isFinite(v)) return { ok: false, error: t('写入值需为数值') }
      const dev = (this.boxSourceDevices || []).find((d) => d.name === att.device)
      const box = dev && dev.node
      if (!box) return { ok: false, error: t('数据源设备无归属盒子') }
      const payload = {
        box, device: att.device, cmd: 'write', property: att.prop, value: v,
        request_id: 'att-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 6),
        ts: Math.floor(Date.now() / 1000),
      }
      try {
        const r = await api.boxPublish('cmd/' + box + '/cmd', JSON.stringify(payload))
        return r && r.ok ? { ok: true } : { ok: false, error: (r && (r.error || r.note)) || t('命令发送失败') }
      } catch (e) {
        return { ok: false, error: String((e && e.message) || e) }
      }
    },
    // 可变设备已绑定的可写点位（数值来源 = 数据源设备 且已选设备 + 点位），未绑定返回 null。
    // 编排面板据此提示「运行会真实下发」，规则执行也据此决定是否发 cmd 写命令。
    boundWriteOf(id) {
      const hit = String(id || '').indexOf('ext::') === 0 ? this._attachByExtId(id) : null
      const att = hit && hit.att
      if (!att || att.src !== 'device' || !att.device || !att.prop) return null
      return { device: att.device, prop: att.prop, box: this._boxOfDevice(att.device) }
    },
    _boxOfDevice(name) {
      const d = (this.boxSourceDevices || []).find((x) => x.name === name)
      return d ? (d.node || '') : ''
    },
    // 写入成功的乐观回写：把已确认落盘的设定值立刻回填到该数据源设备的点位读数上
    // （等下一轮采集上报才刷新会有数十秒空窗，期间界面显示旧值，容易被误判为「没下发」）
    applyWrittenPoint(deviceName, prop, value) {
      const list = this.boxSourceDevices || []
      const idx = list.findIndex((d) => d && d.name === deviceName)
      if (idx < 0) return
      const d = list[idx]
      const v = Number(value)
      if (!isFinite(v)) return
      const props = (d.props || []).map((p) => (p && p.name === prop
        ? { ...p, value: v, ts: Date.now() / 1000, invalid: false }
        : p))
      const next = list.slice()
      next[idx] = { ...d, props }
      this.boxSourceDevices = next
      // 绑定该点位的附加设备读数同步刷新
      try { this._sampleAttachedDevices(Date.now() / 1000) } catch (e) { /* 编排未就绪时忽略 */ }
    },
    // ─────────── AI 群控运行器 ───────────
    // 规则模型的执行从画布组件上移到 store：运行态存在服务端存档里，换电脑 / 重开浏览器拉到
    // running 就在这里恢复执行；页面切到哪、有没有打开编排页都不影响策略继续下发。
    // 持有模型对象本身 —— 运行中改编排下一轮即按新编排执行（热更新）。
    startAgcRule(model) {
      const m = model
      if (!m || !m.id || m.alg !== 'rule') return
      if (this.agcRunId === m.id) return
      if (this.agcRunId) this.stopAgcRule()      // 同时只允许一个策略在运行
      this.agcRunId = m.id
      _agcModel = m
      _agcState = { pendLoops: [] }
      this._agcTick()
      _agcTimer = setInterval(() => this._agcTick(), Math.max(1, Number(m.period) || 2) * 1000)
    },
    stopAgcRule(id) {
      if (id && this.agcRunId && this.agcRunId !== id) return
      if (_agcTimer) { clearInterval(_agcTimer); _agcTimer = null }
      _agcModel = null
      _agcState = null
      this.agcRunId = ''
    },
    _agcTick() {
      const m = _agcModel
      if (!m || !m.graph) return
      const r = evalFlowGraph(m.graph, {
        liveOf: (id) => this._agcLiveOf(id),
        boundOf: (n) => (n && n.kind === 'adj' ? this.boundWriteOf(n.devId) : null),
        state: _agcState || (_agcState = { pendLoops: [] }),
      })
      for (const a of r.acts) {
        // 命中即写：既更新平台内部设定值，也把已绑定数据源可写点位的设备真实下发
        if (a.write) this.setExtSetpoint(a.devId, a.value, { silent: true })
      }
      this.agcLast = {
        ...(this.agcLast || {}),
        [m.id]: {
          ts: Date.now(),
          ok: r.ok,
          acts: r.acts,
          nodes: Array.from(r.activeNodes || []),
          edges: Array.from(r.activeEdges || []),
          branch: r.branch || '',
        },
      }
    },
    _agcLiveOf(id) {
      const lv = this.deviceLiveOf(id)
      if (lv != null && Number.isFinite(Number(lv))) return Number(lv)
      const h = this.deviceHistoryOf(id)
      if (h && h.length && Number.isFinite(Number(h[h.length - 1].v))) return Number(h[h.length - 1].v)
      return null
    },
    // 可变设备设定值统一入口（编排面板 / AI 群控规则执行共用）：
    // 先本地设定，若已绑定数据源设备的可写点位则自动下发写入（失败只提示，不回滚本地设定）。
    // opts.silent —— 规则 / 算法自动执行时用：不弹成功 toast，失败提示按 60s 节流。
    // opts.force  —— 跳过去重强制下发（手动点击时用）。
    // opts.localOnly —— 只改平台内设定值、不下发到现场设备（编排编辑态：改完要等点「运行」才生效）。
    setExtSetpoint(extId, value, opts) {
      this.setDeviceSetpoint(extId, value, opts)
      if (opts && opts.localOnly) return
      const bound = this.boundWriteOf(extId)
      if (!bound) return
      const v = Number(value)
      if (!isFinite(v)) return
      const silent = !!(opts && opts.silent)
      const force = !!(opts && opts.force)
      const now = Date.now()
      const last = _extWriteLast[extId]
      // 去重：同值在保持期内不再下发（规则每轮都会走到这里，不去重就是命令风暴）
      if (!force && last && last.v === v) {
        const keep = last.ok ? _EXT_WRITE_KEEP_MS : _EXT_WRITE_RETRY_MS
        if (now - last.ts < keep) return
      }
      _extWriteLast[extId] = { v, ts: now, ok: true }
      this.writeAttachBound(extId, value).then((r) => {
        const ok = !!(r && r.ok)
        _extWriteLast[extId] = { v, ts: Date.now(), ok }
        if (ok) {
          // 回执确认写入成功 → 立即回填读数：采集上报有周期（数十秒），不回填的话
          // 界面会长时间停在旧值，表现为「明明下发成功，界面上还是旧值 / 像没下发」
          this.applyWrittenPoint(bound.device, bound.prop, v)
          if (!silent) {
            this.showToast(t('已下发写点位 {dev} · {prop} = {v}', { dev: bound.device, prop: bound.prop, v }), 'success')
          }
          return
        }
        const err = (r && r.error) || ''
        if (!silent) { this.showToast(t('写点位下发失败') + '：' + err, 'error'); return }
        // 静默（规则自动执行）：同一设备同一错误 60s 内只提示一次，避免每轮刷屏
        const prev = _extWriteErrAt[extId]
        if (prev && Date.now() - prev < 60000) return
        _extWriteErrAt[extId] = Date.now()
        this.showToast(`${bound.device}.${bound.prop} ${t('写点位下发失败')}：${err}`, 'error')
      })
    },
    // 加载「数据源管理」中的传感器设备（设备定义 + 实时读数），供附加设备绑定真实数据源
    async loadBoxSourceDevices() {
      if (_boxSrcBusy) return
      _boxSrcBusy = true
      try {
        const [defs, rt] = await Promise.all([api.boxDevices(), api.boxDevicesRealtime()])
        const rtMap = {}
        for (const d of ((rt && rt.devices) || [])) rtMap[d.name] = d
        // 设备自身未存点位时回退到其模型的点位定义（模型承载点位语义）
        const modelProps = {}
        for (const m of ((defs && defs.models) || [])) modelProps[m.name] = m.properties || []
        const defList = (defs && defs.devices) || []
        // 定义为空时（异常场景）以实时接口的设备为准，保证下拉不为空
        const base = defList.length ? defList : ((rt && rt.devices) || []).map((d) => ({
          name: d.name, model: d.model, node: d.node, properties: [],
        }))
        this.boxSourceDevices = base.map((d) => {
          const r = rtMap[d.name] || {}
          const tw = {}
          for (const t of (r.twins || [])) tw[t.propertyName] = t
          const propDefs = (d.properties || []).length
            ? d.properties
            : (modelProps[d.model] || []).length
              ? modelProps[d.model]
              : (r.twins || []).map((t) => ({ name: t.propertyName, unit: t.unit }))
          const props = propDefs.map((p) => {
            const t = tw[p.name] || {}
            const raw = t.reported
            const v = (raw != null && raw !== '') ? Number(raw) : null
            return {
              name: p.name,
              unit: t.unit || p.unit || '',
              value: (v != null && !isNaN(v) && !t.invalid) ? v : null,
              ts: t.timestamp || null,
              invalid: !!t.invalid,
            }
          })
          // 无点位定义的旧设备：回退到该设备的实时主读数（list_devices 的 primary）
          if (!props.length && d.primary != null && d.primary !== '') {
            const pv = Number(d.primary)
            props = [{ name: 'primary', unit: '', value: isNaN(pv) ? null : pv, ts: null, invalid: false }]
          }
          // 可写点位 = 设备手工配置的 writes[] + 点位定义中具备可写能力（accessMode=rw）的属性
          // （与数据源管理命令面板同口径；供编排可变设备绑定「写设定」目标）
          const wseen = new Set()
          const writes = []
          for (const w of (d.writes || [])) {
            if (!w || !w.property || wseen.has(String(w.property))) continue
            wseen.add(String(w.property))
            const pd = propDefs.find((p) => p && String(p.name) === String(w.property)) || {}
            writes.push({
              property: w.property,
              unit: w.unit || pd.unit || '',
              min: w.min != null ? w.min : (pd.min != null ? pd.min : null),
              max: w.max != null ? w.max : (pd.max != null ? pd.max : null),
            })
          }
          for (const p of propDefs) {
            if (!p || !p.name || p.accessMode !== 'rw' || wseen.has(String(p.name))) continue
            wseen.add(String(p.name))
            writes.push({ property: p.name, unit: p.unit || '', min: p.min != null ? p.min : null, max: p.max != null ? p.max : null })
          }
          return {
            name: d.name,
            model: d.model || '',
            node: d.node || '',
            protocol: d.protocol || '',
            state: r.state || 'offline',
            props,
            writes,
          }
        })
      } catch (e) {
        // 后端不可达时保留上一次结果，不打断编排交互
      } finally {
        _boxSrcBusy = false
        // 读数刷新后立即补采样附加设备：AI 群控等界面读 deviceLive，
        // 绑定采集设备的传感器无需等下一帧遥测即可生效
        try { this._sampleAttachedDevices(Date.now() / 1000) } catch (e) { /* 编排未就绪时忽略 */ }
        // 非钢场景：读数刷新后按「实测功率」重算折碳（工序附加的电功率传感器绑定的
        // 采集设备有功功率随之进入能碳计算，10s 一轮与数据源刷新同步）。
        if (this.sceneMode !== 'steel') {
          try { this._otherSceneRefresh() } catch (e) { /* 编排未就绪时忽略 */ }
        }
      }
    },
    // 常驻轮询：数据源管理设备列表与其读数（10s），保证附加设备绑定的真实读数持续更新
    _startBoxSourcePolling(ms = 10000) {
      if (_boxSrcTimer) return
      // 可见性感知：后台标签不拉（该轮询常驻不停，否则切走后仍在每 10s 拉全量设备+读数）
      _boxSrcTimer = visiblePoll(() => this.loadBoxSourceDevices(), ms)
    },
    // 编排面板打开时即时拉一次（下拉里立刻能看到最新设备与读数）
    startBoxSourcePolling() { this.loadBoxSourceDevices() },
    stopBoxSourcePolling() { /* 轮询常驻，无需停止 */ },

    addFlowNode(kind, type, x, y) {
      if (this._simEditBlocked()) return null
      this._clearBrowse()               // 拖入后右侧切到节点属性，而非资源浏览属性
      this.inspectorView = 'auto'
      this._histCapture('add_' + uid('h'))
      let node = null
      if (kind === 'process') {
        // 同类型节点：仅 1 台直接使用类型名，从第 2 台起按序号命名（热风炉、热风炉2…），与 buildScheme 多实例命名一致
        const t = PROCESS_MAP[type]
        if (t || this.sceneMode === 'steel') {
          const count = this.scheme.nodes.filter((n) => n.kind === 'process' && n.type === type).length + 1
          node = makeProcessNode(type, x, y, count > 1 && t ? `${t.label}${count}` : undefined)
        } else {
          // 通用资源包场景（其它分组）：以包内模板节点的参数/端口创建该工艺节点
          const count = this.scheme.nodes.filter((n) => n.kind === 'process' && n.type === type).length + 1
          const d = this.sceneProcessDict[type]
          if (d && count > 1 && d.label) node = this._makeSceneProcessNode(type, x, y, `${d.label}${count}`)
          else node = this._makeSceneProcessNode(type, x, y)
        }
      } else if (kind === 'device') node = makeDeviceNode(type, x, y)
      else if (kind === 'material') node = makeMaterialNode(type, x, y)
      if (!node) return
      // 处于小组子编排时，新节点自动归入当前组
      if (this.scheme.activeGroupId) {
        node.groupId = this.scheme.activeGroupId
        const grp = this.scheme.groups.find((g) => g.id === this.scheme.activeGroupId)
        if (grp && !grp.members.includes(node.id)) grp.members.push(node.id)
      }
      this.scheme.nodes.push(node)
      this.selectedFlowId = node.id
      if (kind === 'device') this.scheme.devices.push(node)
      return node.id
    },
    // 通用资源包场景下按包内模板创建工艺节点（无钢字典语义：参数/端口取自包模板快照）
    _makeSceneProcessNode(type, x, y, name) {
      const d = this.sceneProcessDict[type]
      if (!d) return null
      const inMs = (d.ports && Array.isArray(d.ports.in)) ? d.ports.in : []
      const outMs = (d.ports && Array.isArray(d.ports.out)) ? d.ports.out : []
      return {
        id: uid('n'),
        kind: 'process',
        type,
        name: name || d.name || d.label || type,
        x, y,
        count: 1,
        spec: '',
        params: { ...(d.params || {}) },
        recipe: inMs.map((p) => ({ material: p.material || p.id, ratio: 1 })),
        ports: {
          in: inMs.map((p) => ({ id: uid('in'), material: p.material || p.id })),
          out: outMs.map((p) => ({ id: uid('out'), material: p.material || p.id })),
        },
        deviceBindings: [],
        attached: [],
      }
    },
    moveFlowNode(id, x, y) {
      this._histCapture('move_' + id)   // 同节点拖动在合并窗口内合成一步
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (n) { n.x = x; n.y = y }
    },
    // 拖动小组：整体平移全部成员节点（保持组内相对位置）；空组只移动组锚点
    moveFlowGroup(id, dx, dy) {
      this._histCapture('moveg_' + id)   // 同组拖动在合并窗口内合成一步
      const g = this.scheme.groups.find((x) => x.id === id)
      if (!g) return
      const mem = this.scheme.nodes.filter((n) => n.groupId === id)
      if (!mem.length) { g.x += dx; g.y += dy; return }
      for (const n of mem) { n.x += dx; n.y += dy }
    },
    removeFlowNode(id) {
      if (this._simEditBlocked()) return
      this._histCapture('del_' + uid('h'))
      this.scheme.nodes = this.scheme.nodes.filter((n) => n.id !== id)
      this.scheme.connections = this.scheme.connections.filter((c) => c.from !== id && c.to !== id)
      this.scheme.devices = this.scheme.devices.filter((d) => d.id !== id)
      if (this.selectedFlowId === id) this.selectedFlowId = null
      // 从所属小组的成员列表中同步移除
      for (const g of this.scheme.groups) {
        if (g.members && g.members.includes(id)) g.members = g.members.filter((m) => m !== id)
      }
    },
    // ---- 工艺设备小组（子编排）：数据模型与动作 ----
    // 新建小组（默认放入当前画布空白处，返回 group id）
    addFlowGroup(name, x, y) {
      this._histCapture('addgrp_' + uid('h'))
      const g = {
        id: uid('g'),
        name: name || '新小组',
        x: x != null ? x : 100 + (this.scheme.groups.length % 5) * 40,
        y: y != null ? y : 100 + (this.scheme.groups.length % 5) * 40,
        members: [],
        inputs: [],    // 对外输入设定：{ material, label }
        outputs: [],   // 对外输出设定：{ material, label }
      }
      this.scheme.groups.push(g)
      this.selectedGroupId = g.id
      this.selectedFlowId = null
      return g.id
    },
    removeFlowGroup(id) {
      this._histCapture('rmgrp_' + uid('h'))
      this.scheme.groups = this.scheme.groups.filter((g) => g.id !== id)
      // 成员节点退回顶层（不删除节点本身）
      for (const n of this.scheme.nodes) {
        if (n.groupId === id) n.groupId = null
      }
      if (this.scheme.activeGroupId === id) this.scheme.activeGroupId = null
      if (this.selectedGroupId === id) this.selectedGroupId = null
      this.selectedFlowId = null
    },
    renameFlowGroup(id, name) {
      this._histCapture('rngrp_' + id)
      const g = this.scheme.groups.find((x) => x.id === id)
      if (g && name) g.name = name
    },
    selectFlowGroup(id) {
      this._clearBrowse()
      this.selectedMaterialId = null
      this.selectedFlowId = null
      this.selectedUnitId = null
      this.deviceDetailId = null
      this.selectedGroupId = id
      this.inspectorView = 'auto'
      this.rightOpen = true
    },
    // 进入小组子编排：编辑态下画布仅渲染该组成员节点；
    // 非编辑态（数字孪生）下 3D 场景直接进入该小组的子场景（成员展开为独立工序模型）
    enterGroup(id) {
      const g = this.scheme.groups.find((x) => x.id === id)
      if (!g) return
      this.scheme.activeGroupId = id
      if (this.appliedScheme) this.appliedScheme.activeGroupId = id   // 3D 小组子场景按已应用方案同步
      this.selectedFlowId = null
      this.selectedUnitId = null
      this.deviceDetailId = null
      this._clearBrowse()
      this.inspectorView = 'auto'
      if (this.editMode) {
        this.selectedGroupId = null
      } else {
        this.selectedGroupId = id      // 右侧面板展示小组属性（成员工艺列表 + 实测值）
        this.rightOpen = true
        this.sceneRev++                // 触发 3D 场景按小组子场景模式重建
      }
    },
    // 退出小组子编排，返回顶层：编辑态返回顶层画布，非编辑态 3D 返回顶层场景
    exitGroup() {
      if (!this.scheme.activeGroupId) return
      this.scheme.activeGroupId = null
      if (this.appliedScheme) this.appliedScheme.activeGroupId = null
      this.selectedFlowId = null
      this.selectedUnitId = null
      this.deviceDetailId = null
      this._clearBrowse()
      this.inspectorView = 'auto'
      if (this.editMode) {
        this.selectedGroupId = null
      } else {
        this.sceneRev++                // 触发 3D 场景重建回顶层
      }
    },
    // 设定小组对外输入/输出（外部画布连线使用）：io = { inputs?: [...], outputs?: [...] }
    setGroupIo(id, io) {
      this._histCapture('grpio_' + id)
      const g = this.scheme.groups.find((x) => x.id === id)
      if (!g) return
      if (io && Array.isArray(io.inputs)) g.inputs = io.inputs
      if (io && Array.isArray(io.outputs)) g.outputs = io.outputs
    },
    addNodeToGroup(nodeId, groupId) {
      this._histCapture('gtom_' + nodeId)
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      const g = this.scheme.groups.find((x) => x.id === groupId)
      if (!n || !g) return
      // 从旧组移出
      if (n.groupId && n.groupId !== groupId) {
        const old = this.scheme.groups.find((x) => x.id === n.groupId)
        if (old && old.members) old.members = old.members.filter((m) => m !== nodeId)
      }
      n.groupId = groupId
      if (!g.members) g.members = []
      if (!g.members.includes(nodeId)) g.members.push(nodeId)
    },
    removeNodeFromGroup(nodeId) {
      this._histCapture('gfrom_' + nodeId)
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      if (!n || !n.groupId) return
      const g = this.scheme.groups.find((x) => x.id === n.groupId)
      if (g && g.members) g.members = g.members.filter((m) => m !== nodeId)
      n.groupId = null
    },
    // 复制小组：连同全部成员节点与组内连线一起复制（供工具条/右键复用），返回新组 id
    duplicateFlowGroup(id) {
      const g = this.scheme.groups.find((x) => x.id === id)
      if (!g) return null
      this._histCapture('dupg_' + id)
      const dx = 34, dy = 34
      const newId = this.addFlowGroup((g.name || '小组') + ' 副本', (g.x || 100) + dx, (g.y || 100) + dy)
      if (!newId) return null
      const idMap = {}
      for (const mid of (g.members || [])) {
        const n = this.scheme.nodes.find((x) => x.id === mid)
        if (!n) continue
        const nid = this.addFlowNode(n.kind, n.type, n.x + dx, n.y + dy)
        if (!nid) continue
        const nn = this.scheme.nodes.find((x) => x.id === nid)
        if (nn) {
          if (n.params) nn.params = { ...n.params }
          if (n.recipe) nn.recipe = JSON.parse(JSON.stringify(n.recipe))
          if (n.spec) nn.spec = n.spec
        }
        this.addNodeToGroup(nid, newId)
        idMap[mid] = nid
      }
      // 组内成员节点之间的连线一并复制
      for (const c of this.scheme.connections) {
        if (idMap[c.from] && idMap[c.to]) {
          this.addConnection(idMap[c.from], c.fromPort, idMap[c.to], c.toPort, c.material, c.feedback)
        }
      }
      const ng = this.scheme.groups.find((x) => x.id === newId)
      if (ng) {
        ng.inputs = JSON.parse(JSON.stringify(g.inputs || []))
        ng.outputs = JSON.parse(JSON.stringify(g.outputs || []))
      }
      this.selectedGroupId = newId
      this.selectedFlowId = null
      return newId
    },
    // 端口连线（支持多输入/多输出/反馈）；同一输入口仅保留一条连接。
    // 类型约束：输出端口物料必须与输入端口物料匹配（同族即匹配），否则拒绝连线。
    addConnection(from, fromPort, to, toPort, material, feedback = false) {
      if (this._simEditBlocked()) return false
      if (from === to) return false
      const fn = this.scheme.nodes.find((n) => n.id === from)
      const tn = this.scheme.nodes.find((n) => n.id === to)
      if (!fn || !tn) return false
      const fp = (fn.ports && fn.ports.out || []).find((p) => p.id === fromPort)
      const tp = (tn.ports && tn.ports.in || []).find((p) => p.id === toPort)
      if (!fp || !tp) return false
      // 核心约束：输出类型必须对应输入类型才能连线（同物料族视为匹配）
      if (materialFamily(fp.material) !== materialFamily(tp.material)) return false
      this._histCapture('conn_' + uid('h'))
      const dup = this.scheme.connections.find((c) => c.from === from && c.fromPort === fromPort && c.to === to && c.toPort === toPort)
      if (dup) return false
      // 每个输入/输出端口可对应多个节点（多源供一、一源多供）；
      // 仅完全相同的「源-端口→目标-端口」连接视为重复，不重复添加
      this.scheme.connections.push({ id: uid('c'), from, fromPort, to, toPort, material, feedback })
      return true
    },
    removeConnection(id) {
      if (this._simEditBlocked()) return
      this._histCapture('rmconn_' + uid('h'))
      this.scheme.connections = this.scheme.connections.filter((c) => c.id !== id)
    },
    updatePortMaterial(nodeId, dir, portId, material) {
      if (this._simEditBlocked()) return
      this._histCapture('pm_' + nodeId + dir + portId)
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      if (!n || !n.ports) return
      const port = n.ports[dir].find((p) => p.id === portId)
      if (port) port.material = material
    },
    addPort(nodeId, dir, material) {
      this._histCapture('ap_' + uid('h'))
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      if (!n || !n.ports) return
      const arr = n.ports[dir] || []
      // 同一种类不能多次出现（如输入中不能出现两次煤粉）：同方向同物料端口去重
      if (arr.some((p) => p.material === material)) {
        const m = MATERIAL_MAP[material]
        this.toast = t('「{name}」已在该{direction}中，同一种类不能重复添加', { name: m ? m.name : material, direction: dir === 'in' ? t('输入') : t('输出') })
        return
      }
      arr.push({ id: uid(dir === 'in' ? 'in' : 'out'), material })
    },
    // 设置工艺/工辅/设备的台数：>1 自动形成小组（同设备多台），=1 解散仅含自身的自动小组
    setFlowCount(id, count) {
      this._histCapture('cnt_' + id)
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (!n || (n.kind !== 'process' && n.kind !== 'device')) return
      const c = Math.min(9, Math.max(1, Math.round(Number(count) || 1)))
      n.count = c
      if (c > 1) {
        let g = this.scheme.groups.find((x) => x.members && x.members.includes(id))
        if (!g) {
          const t = PROCESS_MAP[n.type]
          const label = (t && t.label) || n.name || '设备'
          g = {
            id: uid('g'),
            name: label,   // 台数以卡片上的数量徽章显示，名称不再重复拼接 ×N
            x: n.x - 30,
            y: n.y - 60,
            members: [id],
            inputs: (t && t.inputs || []).map((m) => ({ material: m })),
            outputs: (t && t.outputs || []).map((m) => ({ material: m })),
          }
          this.scheme.groups.push(g)
        }
        if (n.groupId && n.groupId !== g.id) {
          const old = this.scheme.groups.find((x) => x.id === n.groupId)
          if (old && old.members) old.members = old.members.filter((m) => m !== id)
        }
        n.groupId = g.id
        if (!g.members.includes(id)) g.members.push(id)
        const t = PROCESS_MAP[n.type]
        g.name = `${(t && t.label) || n.name || '设备'}`
      } else {
        const g = this.scheme.groups.find((x) => x.members && x.members.includes(id))
        if (g) {
          g.members = g.members.filter((m) => m !== id)
          n.groupId = null
          if (!g.members.length) {
            this.scheme.groups = this.scheme.groups.filter((x) => x.id !== g.id)
            if (this.scheme.activeGroupId === g.id) this.scheme.activeGroupId = null
          }
        }
      }
    },
    removePort(nodeId, dir, portId) {
      this._histCapture('rp_' + uid('h'))
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      if (!n || !n.ports) return
      n.ports[dir] = n.ports[dir].filter((p) => p.id !== portId)
      this.scheme.connections = this.scheme.connections.filter((c) => !(c.from === nodeId && c.fromPort === portId) && !(c.to === nodeId && c.toPort === portId))
    },
    selectFlow(id) { this._clearBrowse(); this.selectedMaterialId = null; this.selectedUnitId = null; this.deviceDetailId = null; this.selectedFlowId = id; this.selectedGroupId = null; this.flowBackId = null; this.inspectorView = 'auto'; this.rightOpen = true },
    // 跳转到某工艺节点面板（用于主工艺 → 分支辅助工艺），记录返回目标；
    // 仅切换属性面板，不触发 3D 场景聚焦（数字孪生聚焦对象保持不变）
    jumpToFlow(id, backId) { this.selectFlow(id); this.flowBackId = backId || null },
    // 属性面板左上角「返回」：回到跳转来源的主工艺面板
    backFlow() {
      const backId = this.flowBackId
      this.flowBackId = null
      if (backId && this.scheme.nodes.find((n) => n.id === backId)) this.selectFlow(backId)
    },
    setFlowParam(id, key, val) {
      this._histCapture('fp_' + id + key)   // 同参数滑动在合并窗口内合成一步
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (n) n.params = { ...n.params, [key]: Number(val) }
      // 非钢场景：工序参数即核算输入（如锅炉入炉煤量、脱硫石灰石耗量直接决定范围一排放），
      // 改动后立即按新参数重算折碳（_otherSceneRefresh 内部会先重编译模型）。
      if (this.sceneMode !== 'steel' && this.sceneId !== 'steel') this._otherSceneRefresh()
    },
    // 切换工序节点的设备规格（如高炉 1000/2000/3200m³ 档位）：
    // 重置节点默认参数为该规格 defaults，并同步刷新估算结果
    setFlowSpec(id, specKey) {
      this._histCapture('spec_' + id + (specKey || 'std'))
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (!n) return
      n.spec = specKey || ''
      const specs = (this.deviceLibrary && this.deviceLibrary.process_specs) || {}
      const list = specs[n.type] || []
      const sp = list.find((s) => s.key === specKey)
      if (sp && sp.defaults) {
        n.params = { ...n.params, ...sp.defaults }   // 规格默认参数覆盖，未涉及的参数保留
      } else {
        // 切回平台默认规格：重置为模板默认值
        const t = PROCESS_MAP[n.type]
        if (t) n.params = { ...Object.fromEntries((t.params || []).map((p) => [p.key, p.def])) }
      }
      this._markDirty()
    },
    // ---- 节点级参数范围 / 设备量程（内化「平台配置」为编排模式工艺属性，随方案持久化）----
    setFlowParamRange(id, key, patch) {
      this._histCapture('fr_' + id + key)
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (!n) return
      const num = (v) => (v === '' || v == null ? undefined : Number(v))
      const next = {}
      for (const k of ['min', 'max', 'step']) {
        const v = num(patch[k])
        if (v !== undefined) next[k] = v
      }
      if (!Object.keys(next).length) return
      const cur = (n.ranges && n.ranges[key]) || {}
      n.ranges = { ...(n.ranges || {}), [key]: { ...cur, ...next } }
      this._markDirty()
    },
    resetFlowParamRange(id, key) {
      this._histCapture('fr_' + id + key)
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (!n || !n.ranges) return
      const next = { ...n.ranges }
      delete next[key]
      if (Object.keys(next).length) n.ranges = next
      else delete n.ranges
      this._markDirty()
    },
    setFlowDeviceRange(id, patch) {
      this._histCapture('dr_' + id)
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (!n) return
      const num = (v) => (v === '' || v == null ? undefined : Number(v))
      const next = {}
      for (const k of ['min', 'max', 'step']) {
        const v = num(patch[k])
        if (v !== undefined) next[k] = v
      }
      if (!Object.keys(next).length) return
      n.range = { ...(n.range || {}), ...next }
      this._markDirty()
    },
    resetFlowDeviceRange(id) {
      this._histCapture('dr_' + id)
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (n && n.range) delete n.range
      this._markDirty()
    },
    setFlowRecipeRatio(id, idx, ratio) {
      this._histCapture('rr_' + id + idx)
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (n && n.recipe[idx]) n.recipe[idx].ratio = Number(ratio)
    },
    // 配比物料种类更改（右侧检视器）
    setRecipeMaterial(nodeId, idx, mat) {
      this._histCapture('rm_' + nodeId + idx)
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      if (n && n.recipe[idx]) n.recipe[idx].material = mat
    },
    addRecipeRow(nodeId) {
      this._histCapture('addrecipe_' + uid('h'))
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      if (n) n.recipe.push({ material: 'coke', ratio: 1 })
    },
    delRecipeRow(nodeId, idx) {
      this._histCapture('delrecipe_' + uid('h'))
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      if (n) n.recipe.splice(idx, 1)
    },
    // 按物料设置配比（输入端口行内直接编辑）：不存在该物料项则自动追加
    setRecipeRatioForMaterial(nodeId, material, ratio) {
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      if (!n) return
      const v = Number(ratio)
      if (!(v >= 0)) return
      this._histCapture('rrm_' + nodeId + material)
      const r = n.recipe.find((x) => x.material === material)
      if (r) r.ratio = v
      else n.recipe.push({ material, ratio: v })
      this._markDirty()
    },
    bindDevice(nodeId, deviceId) {
      this._histCapture('bd_' + uid('h'))
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      const d = this.scheme.devices.find((x) => x.id === deviceId)
      if (n && d) { d.boundTo = nodeId; if (!n.deviceBindings.includes(deviceId)) n.deviceBindings.push(deviceId) }
    },
    unbindDevice(nodeId, deviceId) {
      this._histCapture('ubd_' + uid('h'))
      const n = this.scheme.nodes.find((x) => x.id === nodeId)
      const d = this.scheme.devices.find((x) => x.id === deviceId)
      if (n) n.deviceBindings = n.deviceBindings.filter((x) => x !== deviceId)
      if (d) d.boundTo = null
    },
    bindDeviceToProcess(deviceId, pid) {
      this._histCapture('bdtp_' + uid('h'))
      const d = this.scheme.devices.find((x) => x.id === deviceId)
      if (!d) return
      const p = pid ? this.scheme.nodes.find((x) => x.id === pid) : null
      d.boundTo = pid || null
      if (p && !p.deviceBindings.includes(deviceId)) p.deviceBindings.push(deviceId)
    },
    // opts.silent —— AI 群控规则每一轮的自动写（非用户操作）：只改本端运行值，
    //   **既不置脏、也不推服务端**（由 _bindSchemeDirty 的 _autoSetpointGuard 兜住）。
    //   否则每轮都整档覆盖 flow，会把别人刚加的附加传感 / 编排改动抹掉。
    setDeviceSetpoint(deviceId, val, opts) {
      const _auto = !!(opts && opts.silent)
      if (_auto) _autoSetpointGuard++
      try {
        this._setDeviceSetpointInner(deviceId, val)
      } finally {
        // 计数在宏任务里回滚：Vue 的 watch（pre flush）是微任务，一定先于此处执行
        if (_auto) setTimeout(() => { _autoSetpointGuard = Math.max(0, _autoSetpointGuard - 1) }, 0)
      }
    },
    _setDeviceSetpointInner(deviceId, val) {
      this._histCapture('ds_' + deviceId)   // 同设备设定滑动在合并窗口内合成一步
      const v = Number(val)
      // 仿真模式：记录本次设备设定变更（供右上角对比窗口左侧展示）。
      // 同设备反复调整合并为一条，文案始终为「仿真前值 → 当前值」。
      if (this.simMode) {
        const d = this.scheme.devices.find((x) => x.id === deviceId)
        const tmpl = d ? DEVICE_MAP[d.type] : null
        const dl = d ? (tmpl ? tmpl.label : (d.name || deviceId)) : deviceId
        const mm = d ? (tmpl && tmpl.measures ? (Array.isArray(tmpl.measures) ? tmpl.measures.join('/') : tmpl.measures) : (d.name || '设定值')) : '设定值'
        const spUnit = tmpl && tmpl.setpoint ? tmpl.setpoint.unit : ''
        let prev = _simParamSnapshot && _simParamSnapshot.deviceSetpoints[deviceId]
        if (prev == null && tmpl && tmpl.setpoint) prev = tmpl.setpoint.def   // 快照缺省回退模板默认值
        this._simLog('setpoint', dl, `${mm} ${fmtNum(prev)} → ${fmtNum(v)}${spUnit ? ' ' + spUnit : ''}`, 'ds_' + deviceId)
      }
      // 统一存储：视图态与编辑态共用 deviceSetpoints，驱动实时读数与碳引擎折算
      this.deviceSetpoints = { ...this.deviceSetpoints, [deviceId]: v }
      const d = this.scheme.devices.find((x) => x.id === deviceId)
      if (d) d.setpoint = v
      else {
        // 附加可变设备（ext::节点id::attUid）：设定值同时写回方案中的附加设备实例，
        // 使「只导出 / 同步 scheme」的场景（另存为资源包、旧存档恢复）也不会丢调节值。
        const hit = String(deviceId || '').indexOf('ext::') === 0 ? this._attachByExtId(deviceId) : null
        if (hit && hit.att && hit.att.kind === 'adjustable') hit.att.def = v
      }
      // 设备设定值现已桥接为高炉操作参数，需重算让后端权威仿真与 3D 热力同步
      this._markDirty()      // 设定值随方案保存：手动保存模式下只置未保存标记
      this.refresh()
    },
    // 附加可调项设定（如鼓风机鼓风湿度）：devId + 可调项 key -> 数值
    setDeviceExtraSetpoint(deviceId, key, val) {
      this._histCapture('des_' + deviceId)   // 同设备附加设定滑动在合并窗口内合成一步
      const v = Number(val)
      // 仿真模式：记录附加可调项变更（如鼓风机鼓风湿度）。
      // 同设备同项反复调整合并为一条，文案始终为「仿真前值 → 当前值」。
      if (this.simMode) {
        const d = this.scheme.devices.find((x) => x.id === deviceId)
        const tmpl = d ? DEVICE_MAP[d.type] : null
        const dl = d ? (tmpl ? tmpl.label : (d.name || deviceId)) : deviceId
        const esCfg = tmpl && tmpl.extraSetpoints ? tmpl.extraSetpoints.find((e) => e.key === key) : null
        const esLabel = esCfg ? esCfg.label : key
        const esUnit = esCfg && esCfg.unit ? esCfg.unit : ''
        let prev = _simParamSnapshot && _simParamSnapshot.deviceExtraSetpoints[deviceId] && _simParamSnapshot.deviceExtraSetpoints[deviceId][key]
        if (prev == null && esCfg) prev = esCfg.def   // 快照缺省回退模板默认值
        this._simLog('setpoint', dl, `${esLabel} ${fmtNum(prev)} → ${fmtNum(v)}${esUnit ? ' ' + esUnit : ''}`, `des_${deviceId}_${key}`)
      }
      const cur = this.deviceExtraSetpoints[deviceId] || {}
      this.deviceExtraSetpoints = { ...this.deviceExtraSetpoints, [deviceId]: { ...cur, [key]: v } }
      const d = this.scheme.devices.find((x) => x.id === deviceId)
      if (d) d.extraSetpoints = { ...(d.extraSetpoints || {}), [key]: v }
      // 附加可调项（鼓风湿度）同样桥接为高炉操作参数（鼓风含湿），需重算同步
      this._markDirty()      // 设定值随方案保存：手动保存模式下只置未保存标记
      this.refresh()
    },
    // ---- 编排画布视图变换（缩放/适配），单一真源，由顶栏「编排」工具条与画布滚轮共用 ----
    setFlowCanvasSize(w, h) { this.flowCanvasW = w; this.flowCanvasH = h },
    // 以 (anchorX, anchorY) 为锚点缩放；不传则用画布中心。返回新的缩放比例。
    flowZoom(f, anchorX, anchorY) {
      const ns = Math.min(2, Math.max(0.3, this.flowTf.scale * f))
      const cx = (anchorX != null) ? anchorX : this.flowCanvasW / 2
      const cy = (anchorY != null) ? anchorY : this.flowCanvasH / 2
      this.flowTf.tx = cx - (cx - this.flowTf.tx) * (ns / this.flowTf.scale)
      this.flowTf.ty = cy - (cy - this.flowTf.ty) * (ns / this.flowTf.scale)
      this.flowTf.scale = ns
      return ns
    },
    // 小组卡片包围盒（画布坐标）：与 FlowEditor.groupBox 一致——位置沿用成员节点包围盒
    // 左上角（保证连线锚点稳定），尺寸与普通工艺节点一致（按端口数量自适应高度）。
    _groupBox(g) {
      const mems = (this.scheme.nodes || []).filter((n) => g.members && g.members.includes(n.id))
      let x, y
      if (mems.length) {
        x = Math.min(...mems.map((n) => n.x)) - 22
        y = Math.min(...mems.map((n) => n.y)) - 48
      } else {
        x = (g.x || 0) - 22
        y = (g.y || 0) - 26
      }
      const cntOf = (dir) => {
        const m = mems[0]
        const arr = (m && m.ports && m.ports[dir]) || []
        if (arr.length) return arr.length
        return ((dir === 'in' ? g.inputs : g.outputs) || []).length
      }
      const cnt = Math.max(cntOf('in'), cntOf('out'), 1)
      const h = NODE_HEADER + (NODE_PORT_Y0 - 7) + (cnt - 1) * NODE_GAP + 16 + 8
      return { x, y, w: NODE_NW, h }
    },
    // 适配视图：把所有可见内容（普通节点 + 折叠后的小组卡片）缩放居中显示，
    // 尽量占满画布（缩小边距、放大上限放宽），大小适中；小组子编排按组成员适配。
    flowZoomFit() {
      const cw = this.flowCanvasW || 900, ch = this.flowCanvasH || 640
      let minX = 1e9, minY = 1e9, maxX = -1e9, maxY = -1e9
      const expand = (x0, y0, w, h) => {
        minX = Math.min(minX, x0); minY = Math.min(minY, y0)
        maxX = Math.max(maxX, x0 + w); maxY = Math.max(maxY, y0 + h)
      }
      const nodes = this.scheme.nodes || []
      if (this.scheme.activeGroupId) {
        const g = this.scheme.groups.find((x) => x.id === this.scheme.activeGroupId)
        const ids = new Set((g && g.members) || [])
        for (const n of nodes) if (ids.has(n.id)) expand(n.x, n.y, NODE_NW, nodeHeight(n))
      } else {
        for (const n of nodes) if (!n.groupId) expand(n.x, n.y, NODE_NW, nodeHeight(n))
        for (const g of this.scheme.groups || []) {
          const b = this._groupBox(g)
          if (b) expand(b.x, b.y, b.w, b.h)
        }
      }
      if (!isFinite(minX) || !isFinite(maxX)) return this.flowTf.scale
      const bw = Math.max(200, maxX - minX + 60), bh = Math.max(160, maxY - minY + 60)
      const s = Math.min(2, Math.max(0.3, Math.min(cw / bw, ch / bh)))
      this.flowTf.scale = s
      this.flowTf.tx = (cw - (maxX - minX) * s) / 2 - minX * s
      this.flowTf.ty = (ch - (maxY - minY) * s) / 2 - minY * s
      return s
    },
    // 画布「自动布局」也纳入撤销（工艺树重排节点位置）
    // 横向流式网格：主工艺每行 3-4 个横向排列，工辅排在各自主工艺正下方，卡片互不重叠。
    autoLayoutScheme() {
      this._histCapture('autolayout_' + uid('h'))
      treeLayoutNodes(this.scheme.nodes, this.scheme.connections, {
        canvasW: this.flowCanvasW || 0,
        canvasH: this.flowCanvasH || 0,
      })
    },
    // 将「已应用方案」固化：把当前 scheme 深拷贝为 appliedScheme。
    // 仅在「编排已保存」或「显式载入项目 / 模板 / 场景」时调用 —— 这两类时刻 scheme 即最终态，
    // 之后 3D 孪生 / 2D 工艺图 / KPI / 设备树都以它为基准编译，未保存的草稿不会泄漏过去。
    _syncAppliedScheme() {
      this.appliedScheme = JSON.parse(JSON.stringify(this.scheme || { nodes: [], connections: [], devices: [], groups: [], activeGroupId: null }))
    },
    // 应用当前编排方案：同步已应用快照 → 重编译 model → 重布局 → 重算 → 触发 3D 重建。
    // 这是「编排改动反映到孪生」的唯一出口（保存时调用），编排过程中的编辑一律不调用它。
    _applyScheme() {
      this._syncAppliedScheme()
      this.compileSchemeToModel()
      this.autoLayout()
      this.refresh()
      this.sceneRev++     // 3D 孪生按新方案重建（编辑态下由 SceneViewer 的 flowEditing watch 兜底）
    },
    // 将编排方案编译为现有仿真 model（工序=工艺节点，物流=连接），供 3D 孪生重绘
    // 注意：后端碳引擎仅识别标准工艺类型，故"公用/节能"节点(煤气发电/余热/CCUS)不纳入 3D 仿真，
    // 其减碳作用在编辑态前端估算中已计入。
    // 编译源恒为 **已应用方案 appliedScheme**（而非正在编辑的 scheme 草稿）：
    // 编排未保存时 model 必须保持上次保存的样子，否则 3D 孪生 / KPI 会被未保存的草稿改掉。
    compileSchemeToModel() {
      const src = this.appliedScheme || this.scheme
      // 通用资源包场景（其它分组）：包内 scheme 直译为单位模型（无钢字典语义）
      if (this.sceneMode !== 'steel') return this._compileOtherScheme(src)
      const procs = src.nodes.filter((n) => n.kind === 'process' && PROCESS_MAP[n.type] && PROCESS_MAP[n.type].route !== 'util')
      const procIds = new Set(procs.map((n) => n.id))
      const units = procs.map((n) => ({
        id: n.id,
        type: n.type,
        name: n.name,
        params: { ...n.params },
        techs: Array.isArray(n.techs) ? n.techs : [],
        spec: n.spec || '',
        groupId: n.groupId || null,   // 所属工艺设备小组（3D 底座着色/点击组信息用）
        enabled: true,
        rot: 0,
        x: Math.round((n.x - 400) / 40),
        z: Math.round((n.y - 300) / 40),
      }))
      // 保留原模型中“公用/节能”类工序（煤气发电/余热/CCUS 等），其不参与标准碳引擎，
      // 但应随流程一起保留，避免进入/退出编辑态时被丢弃。
      const prevUtil = (this.model.units || []).filter((u) => {
        const t = PROCESS_MAP[u.type]; return t && t.route === 'util'
      })
      for (const u of prevUtil) {
        if (!units.find((x) => x.id === u.id)) {
          units.push({ ...u, techs: Array.isArray(u.techs) ? u.techs : [], enabled: true })
        }
      }
      // 工艺间连线按「物料匹配」校验：连接物料必须由源工艺产出、且为目标工艺所需，
      // 过滤掉冗余/错误的连线（如 烧结机→球团、球团→焦炉 这类没有对应物料流的边），
      // 保证 3D 孪生只绘制真实存在的物料管道。
      const nodeById = Object.fromEntries((src.nodes || []).map((n) => [n.id, n]))
      const flowOk = (c) => {
        const f = nodeById[c.from], t = nodeById[c.to]
        const ft = f && PROCESS_MAP[f.type], tt = t && PROCESS_MAP[t.type]
        if (!ft || !tt) return false
        const m = c.material
        return !!m && (ft.outputs || []).includes(m) && (tt.inputs || []).includes(m)
      }
      const flows = (src.connections || [])
        .filter((c) => procIds.has(c.from) && procIds.has(c.to) && flowOk(c))
        .map((c) => ({ id: c.id, from_unit: c.from, to_unit: c.to, material: c.material, rate: 1000 }))
      // 驱动连线折算：工辅（鼓风机/热风炉/引风机…）经物料连线把自身运行参数
      // 写入被服务工艺的目标参数（如 鼓风量→高炉 wind_rate、热风→hot_blast_temp）。
      // 连线存在时覆盖被服务工艺原手动参数（以实际驱动工况为准）。
      // 工辅自身编译为独立 Unit（route='aux'），仅耗电、不直接产碳，由后端能源 calc 处理。
      const unitById = Object.fromEntries(units.map((u) => [u.id, u]))
      for (const c of flows) {
        const f = nodeById[c.from], t = nodeById[c.to]
        const ft = f && PROCESS_MAP[f.type]
        if (!ft || !ft.drives) continue
        const drive = ft.drives[c.material]
        if (!drive) continue
        const srcUnit = unitById[f.id], dstUnit = unitById[t.id]
        if (!srcUnit || !dstUnit) continue
        const srcVal = (srcUnit.params && srcUnit.params[drive.src] != null) ? Number(srcUnit.params[drive.src]) : null
        if (srcVal != null) {
          // 驱动连线：工辅供给绝对量直接写入同量纲目标参数（如 鼓风量 kNm³/h → 高炉风量 kNm³/h）。
          // 例外：喷吹系统 inj_rate 为绝对量(t/h) → 高炉 coal_inj 为相对量(kg/t)，按铁水产量折算
          const hm = dstUnit.params && dstUnit.params.hot_metal != null ? Number(dstUnit.params.hot_metal) : null
          let driveVal = srcVal
          if (drive.dst === 'coal_inj' && drive.src === 'inj_rate' && hm && hm > 0) driveVal = (srcVal * 1000) / hm
          dstUnit.params = { ...(dstUnit.params || {}), [drive.dst]: driveVal }
        }
      }
      // 标记工辅 Unit，供后端/前端识别（不影响其它工艺）
      for (const u of units) {
        const t = PROCESS_MAP[u.type]
        if (t && t.route === 'aux') { u.route = 'aux'; u.energy_only = true }
      }
      this.model = {
        units,
        flows,
        // 小组元信息（id/name），供 3D 数字孪生以聚合模型方式呈现小组
        groups: (src.groups || []).map((g) => ({ id: g.id, name: g.name || '设备小组' })),
      }
    },

    // 通用资源包场景（其它分组）编译：包内 scheme 直译为 3D 单位模型。
    // 所有工艺节点按模板坐标排布、连线全保留（包模板连线可信，手工连线画布已校验端口）；
    // 不依赖钢流程字典（PROCESS_MAP）与后端碳引擎；附加传感器/可变设备随 unit 携带。
    // 主/辅归属来自包字典的 route（'main' 主流程 / 'aux' 辅助系统）与 auxGroup
    // （辅助系统分组，如火电的 water 汽水循环 / flue 烟气治理），供 3D 场景把辅助流程
    // 排到主流程两侧（与钢铁「工辅在两侧」同一套布局口径，见 scene.js _layoutProcessUnits）。
    _compileOtherScheme(srcOverride) {
      const src = srcOverride || this.appliedScheme || this.scheme
      const nodes = (src && src.nodes) || []
      const conns = (src && src.connections) || []
      const procSet = new Set(nodes.filter((n) => n.kind === 'process').map((n) => n.id))
      const dictProcs = (this.sceneCtx && Array.isArray(this.sceneCtx.processes)) ? this.sceneCtx.processes : []
      const dictOf = (type) => dictProcs.find((p) => p && p.type === type) || null
      // 工序名以**包字典为准**（字典是包内权威定义）：包升级改名后，已存档的 scheme
      // （localStorage / 服务端 designs）不会拖着旧名不放；模板里带路线差异后缀的名字
      // （如「汽轮机系统（抽凝式）」）以字典名为前缀，予以保留。
      const nameOf = (n, dp) => {
        const dn = (dp && dp.name) || ''
        const sn = n.name || n.type
        if (!dn || sn === dn) return sn
        return sn.indexOf(dn) === 0 ? sn : dn
      }
      const units = nodes.filter((n) => n.kind === 'process').map((n) => {
        const dp = dictOf(n.type)
        return {
        id: n.id,
        type: n.type,
        name: nameOf(n, dp),
        params: { ...(n.params || {}) },
        techs: Array.isArray(n.techs) ? n.techs : [],
        spec: n.spec || '',
        groupId: n.groupId || null,
        enabled: n.enabled !== false,
        rot: n.rot || 0,
        route: (dp && dp.route) || 'main',
        auxGroup: (dp && dp.auxGroup) || '',
        attached: Array.isArray(n.attached) ? n.attached.map((x) => ({ ...x })) : [],
        x: Math.round(((n.x != null ? n.x : 0) - 400) / 40),
        z: Math.round(((n.y != null ? n.y : 0) - 300) / 40),
      }
      })
      const flows = conns
        .filter((c) => procSet.has(c.from) && procSet.has(c.to))
        .map((c) => ({ id: c.id, from_unit: c.from, to_unit: c.to, material: c.material, rate: c.rate || 1000 }))
      this.model = {
        units,
        flows,
        groups: (src.groups || []).map((g) => ({ id: g.id, name: g.name || '设备小组' })),
      }
    },

    // ---- 实时数据源（平台 MQTT 实时 / 自定义 WebSocket / HTTP 轮询，支持多源并存）----
    _startFeed() { this._connectFeed() },
    // MQTT 数据源状态轮询：连接状态 / 订阅主题 / 最近消息
    _startMqttPolling() {
      if (this._mqttTimer) return
      const poll = () => {
        api.realtimeSource().then((s) => { this.mqttSource = s }).catch(() => {})
      }
      poll()
      this._mqttTimer = visiblePoll(poll, 3000)
    },
    // 云端设备 <-> 仿真设备实例关联：仅关联后云端读数才同步到对应设备实例
    async linkMqttDevice(cloudId, localId) {
      await api.linkMqttDevice(cloudId, localId)
      this.mqttSource = await api.realtimeSource()   // 重新拉取完整状态（含关联表与云端设备）
      this.toast = t('已关联：{cloud} → {local}，数据开始同步', { cloud: cloudId, local: localId })
    },
    async unlinkMqttDevice(cloudId) {
      await api.unlinkMqttDevice(cloudId)
      this.mqttSource = await api.realtimeSource()
      this.toast = t('已解除关联：{cloud}，数据停止同步', { cloud: cloudId })
    },
    _connectFeed() {
      // 关闭旧连接（各数据源的 WebSocket 或 HTTP 轮询定时器）
      for (const c of this._conns || []) { try { c.close && c.close() } catch (e) {} }
      this._conns = []
      this.sourceStatus = {}
      // 仅连接启用的数据源；若全部停用/为空，则保底回落到能碳一体机 MQTT 数据源
      let sources = (this.dataSources || []).filter((s) => s.enabled !== false)
      if (!sources.length) {
        const sim = { id: 'sim', type: 'sim', url: '', interval: 1000, name: '能碳一体机', enabled: true, mapping: {} }
        this.dataSources = [sim]
        this.activeDataSourceId = 'sim'
        this.dataSource = sim
        this._saveDataSource()
        sources = [sim]
      }
      if (!this.dataSource) {
        this.dataSource = sources.find((s) => s.id === this.activeDataSourceId) || sources[0]
      }
      for (const ds of sources) {
        this.sourceStatus[ds.id || 'sim'] = 'init'
        const conn = this._connectOne(ds)
        if (conn) this._conns.push(conn)
      }
      this._refreshFeedStatus()
      this._pushModelToFeed()
    },
    // 建立单个数据源连接（ws：平台 Mqtt 实时/自定义 WebSocket；http：按 interval 轮询 JSON）
    _connectOne(ds) {
      const sid = ds.id || 'sim'
      const onMsg = (msg) => this._onFeedMsg(ds, msg)
      const onStatus = (st) => { this.sourceStatus[sid] = st; this._refreshFeedStatus() }
      if (ds.type === 'http') {
        let alive = true
        let timer = null
        const tick = async () => {
          if (!alive) return
          try {
            const r = await fetch(ds.url, { headers: { Accept: 'application/json' } })
            if (!r.ok) throw new Error('HTTP ' + r.status)
            onMsg(await r.json())
            if (this.sourceStatus[sid] !== 'open') this.sourceStatus[sid] = 'open'
          } catch (e) { this.sourceStatus[sid] = 'error' }
          if (alive) timer = setTimeout(tick, Math.max(500, ds.interval || 1000))
        }
        tick()
        return { close: () => { alive = false; clearTimeout(timer) } }
      }
      // WebSocket：平台 Mqtt 实时数据（默认 /api/ws/feed）或自定义 url
      const url = ds.type === 'ws' && ds.url ? ds.url : undefined
      const ws = openFeed(onMsg, onStatus, url)
      return { ws, close: () => { try { ws.close() } catch (e) {} } }
    },
    // 遥测消息落地：应用该数据源的「字段对齐映射」把外部字段名翻译为场景内传感器/设备 id
    _onFeedMsg(ds, msg) {
      if (!msg) return
      const src = msg
      if (!src || !src.devices) return
      this.live = src
      const now = Date.now() / 1000
      const mapping = (ds && ds.mapping) || {}
      // 记录该数据源最近一次收到的外部字段 id（供「连接」面板做字段对齐）；字段集合未变化时跳过，避免无谓的响应式更新
      if (ds) {
        const sid = ds.id || 'sim'
        const fields = Array.from(new Set(src.devices.map((d) => d.id)))
        const prev = this.lastFields[sid]
        if (!prev || prev.length !== fields.length || prev.some((f, i) => f !== fields[i])) {
          this.lastFields = { ...this.lastFields, [sid]: fields }
        }
      }
      for (const d of src.devices) {
        // 字段对齐：若 mapping 配置了「外部字段 -> 内部传感器 id」，读数落入内部传感器；
        // 未配置的字段沿用自身 id（平台 Mqtt 数据源的字段即内部 id，天然对齐）
        const internalId = mapping[d.id] || d.id
        this.deviceLive[internalId] = d.reading
        const buf = this.deviceHistory[internalId] || (this.deviceHistory[internalId] = [])
        buf.push({ t: now, v: d.reading })
        // 超限批量截断（保留 600 点 ≈ 10 分钟@1Hz），避免逐点 splice 的重复搬移开销
        if (buf.length > 900) buf.splice(0, buf.length - 600)
      }
      // 可调设备由前端合成、后端不推送其读数：按当前设定值补采样（设定值即工况值，输入框数字即当前值）
      const baseUnits = (this.baseline && this.baseline.units) || []
      for (const u of baseUnits) {
        for (const dt of adjustableTypesFor(this.scheme, u.type, u.id)) {
          const did = `${u.id}::${dt}`
          const tpl = DEVICE_MAP[dt]
          const sp = (this.deviceSetpoints && this.deviceSetpoints[did] != null)
            ? this.deviceSetpoints[did]
            : (tpl && tpl.setpoint ? tpl.setpoint.def : null)
          if (sp == null) continue
          this.deviceLive[did] = sp
          const buf = this.deviceHistory[did] || (this.deviceHistory[did] = [])
          buf.push({ t: now, v: sp })
          if (buf.length > 900) buf.splice(0, buf.length - 600)
        }
      }
      // 附加设备（挂 node.attached[] 上的传感器 / 可变设备）同样由前端合成、后端不推送读数：
      // 一并补采样。「随附加可调设备联动」的传感器（如冷却水流速随循环水泵变压器输出电压变化）
      // 读数会随时间进入历史，数据分析 / 趋势曲线里就能直接看出「调压 → 流速」的变化过程。
      this._sampleAttachedDevices(now)
      // 非钢场景：附加可调设备的实时数据（实测功率 kW）参与折碳 → 随遥测刷新基线碳排（轻量重算，钢场景自动跳过）
      this._otherSceneRecarbon()
    },
    // 附加设备（挂 node.attached[] 上的传感器 / 可变设备）由前端合成、后端不推送读数：
    // 统一在此补采样进 deviceLive/deviceHistory。遥测帧与「数据源管理」10s 轮询都会调用，
    // 读数缺失（采集设备离线/点位暂无值）时删除陈旧键，避免旧值遮蔽现算兜底。
    _sampleAttachedDevices(now) {
      const baseUnits = (this.baseline && this.baseline.units) || []
      const setpoints = this.deviceSetpoints || {}
      const srcMap = _boxSrcMap(this)
      const ms = Date.now()
      for (const n of (this.scheme.nodes || [])) {
        const u = baseUnits.find((x) => x.id === n.id)
        for (const att of (n.attached || [])) {
          const dev = _extDevice(n, u, att, ms, srcMap, setpoints)
          if (!dev) continue
          if (dev.reading == null) {
            delete this.deviceLive[dev.id]
            continue
          }
          this.deviceLive[dev.id] = dev.reading
          const buf = this.deviceHistory[dev.id] || (this.deviceHistory[dev.id] = [])
          buf.push({ t: now, v: dev.reading })
          if (buf.length > 900) buf.splice(0, buf.length - 600)
        }
      }
    },
    _refreshFeedStatus() {
      const sts = Object.values(this.sourceStatus)
      let next
      if (!sts.length) next = 'init'
      else next = sts.includes('open') ? 'open'
        : (sts.includes('init') ? 'init'
          : (sts.includes('error') ? 'error' : 'closed'))
      const prev = this.feedStatus
      if (next !== prev) {
        this.feedStatus = next
        // 链路状态变化通知（跳过初始连接阶段的 init 过渡，防抖 1.5s 避免 open/init 抖动刷屏）
        if (prev !== 'init' && next !== 'init') {
          clearTimeout(this._feedNotifTimer)
          this._feedNotifTimer = setTimeout(() => {
            if (this.feedStatus !== next) return
            if (next === 'open') this.notify('success', t('实时链路已恢复'), t('实时数据链路已重新连接，工况数据持续更新。'))
            else if (next === 'error') this.notify('error', t('实时链路异常'), t('实时数据链路异常，请检查数据源配置。'))
            else if (next === 'closed') this.notify('warn', t('实时链路已断开'), t('实时数据链路已断开，仿真将基于最近一次数据继续运行。'))
          }, 1500)
        }
      }
    },
    _pushModelToFeed() {
      for (const c of this._conns || []) {
        if (c.ws && c.ws.readyState === 1) {
          try { c.ws.send(JSON.stringify({ type: 'model', model: this.model })) } catch (e) {}
        }
      }
    },
  },
})
