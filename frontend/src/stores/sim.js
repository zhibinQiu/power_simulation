import { defineStore } from 'pinia'
import { watch, nextTick } from 'vue'
import { t } from '../i18n'
import { visiblePoll } from '../utils/poll'
import { api, openFeed } from '../api/client'
import { buildScheme, makeProcessNode, makeDeviceNode, makeMaterialNode, PROCESS_MAP, MATERIAL_MAP, PROCESS_ADJUSTABLE, DEVICE_MAP, DEVICE_COUPLE_REGISTRY, deriveProcessOpParams, materialFamily, loadCalibrations, registerSceneMaterials, NODE_NW, NODE_HEADER, NODE_PORT_Y0, NODE_GAP, nodeHeight, PROCESS_TEMPLATES, applySetpointResponse, migrateLegacyDevices, treeLayoutNodes } from '../data/flowLibrary'
import { computeScheme } from '../flow/compute'
import { PARK } from '../data/park'
// 通用附加设备库（传感器 / 可变设备，所有场景可用）：
// 与「工艺类型 → 典型可调设备」不同，附加设备是用户在某工艺节点上按需添加的，
// 存于工艺节点 node.attached[]，运行态由 store 合成 ext::节点id::attUid 设备。
import { SENSOR_MAP, ADJUSTABLE_MAP, ATTACH_MAP, attachUnit, attachDef, attachMeasureLabel, attachPowerSensor } from '../data/attachLibrary'
// 工艺静态业务数据：集中维护于独立数据模块 src/data/processMeta.js
// （业务数据与代码逻辑分离），本 store 只负责仿真状态与交互逻辑；
// 下方 re-export 保持既有组件 `import { ... } from '../stores/sim'` 兼容。
import { OP_PARAM_KEYS, DIRECT_PARAM_KEYS, EDITABLE_PARAMS, UNIT_TYPES, CATEGORY_ORDER, TECHS } from '../data/processMeta'
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

let _idc = 0
const uid = (p) => `${p}_${Date.now().toString(36)}${(_idc++).toString(36)}`
// 数据源管理设备列表轮询：_boxSrcBusy 防并发重入，_boxSrcTimer 常驻定时器
let _boxSrcBusy = false
let _boxSrcTimer = null
// 数值展示：保留 2 位小数并去掉末尾多余的 0
const fmtNum = (v) => (v == null || isNaN(v) ? '—' : Number(v).toFixed(2).replace(/\.?0+$/, ''))

// ===== 附加设备（传感器 / 可变设备）合成工具 =====
// 附加设备挂在具体工艺节点 node.attached[] 上，id 均为 ext::节点id::attUid；
// 运行态由 getter 从 scheme 节点 + 对应 unit（params/实时）合成设备条目。
function _attachTpl(kind, type) {
  const m = ATTACH_MAP[kind] || {}
  return m[type] || null
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
function _otherUnitMetrics(powerKW, carbonKg) {
  return {
    carbon: carbonKg,                 // kgCO₂/h（本场景口径）
    energy: powerKW,                  // kWh/h
    prod: 1,
    unitCarbon: carbonKg,
    co2_total: carbonKg / 1000,       // tCO₂/h（孪生标签 / 折碳汇总口径）
    energy_total: powerKW * 0.0036,   // GJ/h
    powerKW,                          // 实际参与折碳的功率
  }
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
    // 平台激活状态（后端 /api/license/*）：未激活时状态栏提示「产品未激活」
    license: { activated: false, machineId: '', boundMachine: '', activatedAt: '', checked: false },
    aboutDialog: false,   // 关于本平台弹窗开关（内嵌平台激活；StatusBar / 帮助菜单 / App 共用）
    toast: '',
    toastType: 'info',    // 类型化 Toast：success / info / warn / error（ToastLayer 渲染）
    confirmDialog: { open: false, title: '', message: '', okText: '', cancelText: '', danger: false }, // 确认弹窗（ConfirmDialog 渲染）
    _confirmResolver: null, // confirm() 挂起的 Promise resolve
    scenario: 'steel',           // 当前仿真场景行业（四大控排 + 其它）：steel 钢铁(默认) / cement 水泥 / chemical 化工 / nonferrous 有色 / other 其它(资源包场景)
    processRoute: 'short',       // 当前流程：短流程(默认) / 长流程；数字孪生默认展示短流程。资源包场景下为包内模板 id（如 cool）
    // —— 场景 / 资源包（.ec）状态 ——
    sceneId: 'steel',            // 当前打开的场景资源包 id（steel = 平台内置钢包）
    sceneMode: 'steel',          // 'steel' = 钢铁碳引擎场景（后端仿真全能力）；'other' = 通用资源包场景（编排 → 孪生展示，本地静态核算）
    sceneIndex: [],              // 后端场景注册表（/api/scenes：含 meta 与 ready/package 状态）
    sceneIndexTs: 0,             // 注册表刷新代数（供 UI 观察列表变化）
    scenePack: null,             // 当前场景资源包（{ meta, resources }）
    sceneTemplates: [],          // 包内预置模板（resources.templates：编排方案快照）
    sceneCtx: null,              // 包内通用字典上下文（dictionary/factors/paramSchema…），供非钢场景资源树/属性渲染
    sceneVersion: 0,             // 场景包装载代数：切换场景后自增，触发组件按新场景重建
    sceneBusy: false,            // 场景资源包装载/切换中
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
    leftOpen: true,           // 左侧栏是否展开
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
    boxCloudSource: 'unknown',// 能碳一体机管理：云端连接状态（live / degraded / unknown），由 CarbonBoxView 轮询后写回
    inspectorView: 'auto',    // 右侧检视器显式视图：'auto'（按选中推导）| 'park' 园区构成 | 'materials' 原料库 | 'strategy' 减排策略 | 'report' 报告面板 | 'agent' 本析智擎对话
    reportPayload: null,      // 「导出报告」请求载荷（baseline/strategy/ops/...），供右侧报告面板消费
    selectedStrategyId: null, // 左侧策略库选中的策略
    deviceHistory: {},        // 各设备历史读数序列：devId -> [{t, v}]
    deviceLive: {},           // 各设备实时读数：devId -> number
    deviceSetpoints: {},      // 可调设备设定值覆盖：devId -> number（视图态/编辑态统一存储，驱动实时读数与碳引擎折算）
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
    activityView: 'explorer',   // 活动面板：'explorer' 资源 | 'search' 搜索 | 'scene' 场景（AI 群控为独立视图，不占用活动面板）
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
    selectedFlowId: null,   // 画布中选中的节点 id
    selectedGroupId: null,  // 画布中选中的小组 id
    flowBackId: null,       // 属性面板跳转来源工艺节点 id（主工艺→分支辅助工艺后，面板显示「返回」）

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
    // 左侧资源管理器：浏览态选中（只看属性，不改动产线）
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
    cmdLog: [],             // [{ t, k }] k: cmd|out|sys|guide|tip|warn|err|bot|sim
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
    linkedAuxOfUnit: (s) => (unitId) => linkedAuxTypesFor(s.scheme, unitId),
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
        const node = ((s.scheme && s.scheme.nodes) || []).find((x) => x.id === nid)
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
      const nodes = (s.scheme && s.scheme.nodes) || []
      const conns = (s.scheme && s.scheme.connections) || []
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
      // 附加后该工艺在资源管理器 / 设备树 / 数据分析中即出现对应设备（数值来源可按需解析）
      const srcMap = _boxSrcMap(s)
      const nowMs = Date.now()
      for (const n of (s.scheme && s.scheme.nodes) || []) {
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
      const node = ((s.scheme && s.scheme.nodes) || []).find((n) => n.id === nodeId)
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
    // 撤销/重做可用性
    canUndo: (s) => s.historyPast.length > 0,
    canRedo: (s) => s.historyFuture.length > 0,
  },
  actions: {
    // 命令行窗口：追加一条日志（k：cmd 命令回显 / out·sys 一般信息 / guide 引导输入 / tip 提醒 / warn·err 警告报错 / bot 聊天 / sim 仿真记录）
    pushCmd(msg, k = 'out') { this.cmdLog.push({ t: msg, k }) },
    clearCmdLog() { this.cmdLog = [] },
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
        loadCalibrations()   // 启动即恢复本厂标定耦合（localStorage），否则用默认机理/经验系数
        this._loadDataSource() // 恢复上次设置的实时数据源（平台 MQTT 实时 / 自定义 WS / HTTP）
        this._startMqttPolling() // 定时拉取 MQTT 数据源状态（连接状态/订阅主题/最近消息）
        // 「数据源管理」中的传感器设备：附加设备绑定真实读数的数据源候选（首次加载 + 常驻轮询）
        this.loadBoxSourceDevices()
        this._startBoxSourcePolling()
        this.fetchLicense() // 查询平台激活状态（后台加载，不阻塞主流程）
        const [m, presets, factors, schema, devs, hist] = await Promise.all([
          api.presetModel(), api.presetStrategies(), api.getFactors(), api.getParamSchema(),
          api.getDevices(), api.getDeviceHistory(),
        ])
        this.model = m
        // 优先恢复上次保存的编排方案（exitEdit/loadTemplate 等已持久化）；
        // 若存在则直接恢复并编译（含设备设定值），否则按上次流程路线构建默认方案，避免刷新后回退
        const saved = this._loadScheme()
        if (saved) {
          this.scheme = saved.scheme
          // 旧版本持久化方案可能缺少小组容器字段，补齐避免访问报错
          if (!this.scheme.groups) this.scheme.groups = []
          if (this.scheme.activeGroupId == null) this.scheme.activeGroupId = null
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
              this._saveScheme()
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
          const sps = {}
          const esps = {}
          for (const d of (this.scheme.devices || [])) {
            if (d && d.id && d.setpoint != null) sps[d.id] = d.setpoint
            if (d && d.id && d.extraSetpoints && typeof d.extraSetpoints === 'object') esps[d.id] = d.extraSetpoints
          }
          this.deviceSetpoints = sps
          this.deviceExtraSetpoints = esps
          this.compileSchemeToModel()
          this.autoLayout()
        } else {
          const savedRoute = (() => { try { return localStorage.getItem('sim.processRoute') } catch (e) { return null } })()
          this._setDefaultRoute(savedRoute || 'long')
        }
        this.factors = factors   // 默认排放因子，供详情弹窗与因子配置面板使用
        this.factorsDefault = factors   // 快照默认基线，供编辑态估算偏移归零
        this.paramSchema = schema   // 工序参数分级元数据，供流程编排编辑器分组与参考范围展示
        this.deviceLibrary = devs   // 内置监测设备库，供 3D 设备标记、设备详情面板与规格档位联动
        // 设备历史时序（首屏即带趋势）
        if (hist && hist.history) this.deviceHistory = hist.history
        if (hist && hist.meta) this.deviceMeta = hist.meta
        this.autoLayout()        // 初次加载先按序等距自动布局，避免工艺图标重叠
        this.presets = presets
        await this._runRefresh()  // 首屏立即重算（不走防抖），保证 KPI 就绪
        await this.loadStrategies()
        this.ready = true
        this._bindAutosave()   // 编排编辑自动保存（任何场景通用）
        this.notify('success', t('系统就绪'), t('数字孪生已载入 {units} 个工序、{flows} 条物流，实时链路与优化模型已就绪。', { units: this.model.units.length, flows: this.model.flows.length }))
        this._startFeed()
        // AI 优化模型：同步训练上下文并轮询状态（后台定时训练由后端调度，前端展示「逐渐变优」）
        this.syncOptimizerContext().then(() => this.refreshOptimizers())
        this.startOptimizerPolling()
      } catch (e) {
        this.toast = t('初始化失败：') + e.message
        this.notify('error', t('初始化失败'), e.message)
      }
    },
    // ---------- 平台激活 ----------
    async fetchLicense() {
      try {
        const st = await api.licenseStatus()
        this.license = { ...st, checked: true }
      } catch (e) {
        this.license = { activated: false, machineId: '', boundMachine: '', activatedAt: '', checked: true }
      }
    },
    // 提交激活码；返回 { ok, activated, message }，失败时 message 可直接展示
    async activatePlatform(code) {
      const r = await api.licenseActivate(code)
      if (r && r.ok && r.status) this.license = { ...r.status, activated: true, checked: true }
      return r
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
      const nodeById = Object.fromEntries((this.scheme.nodes || []).map((n) => [n.id, n]))
      const unitById = Object.fromEntries(units.map((u) => [u.id, u]))
      for (const c of (this.scheme.connections || [])) {
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
        const linkedAux = new Set(linkedAuxTypesFor(this.scheme, u.id))
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
    // 左侧资源管理器：浏览选中（只读查看属性 / 实时数据，不修改产线）。
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
    toggleLeft() { this.leftOpen = !this.leftOpen },
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
      if (!id) { this.activeViewId = null; return }
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
    },
    _activateView(id) {
      // AI 群控：内容区改为「训练前测试 | 训练相关设定」左右两栏，训练属性面板已内嵌右栏 → 进入时备份并收起外部系统右栏
      if (id === 'aiGroup') {
        if (this.grpRightBackup == null) this.grpRightBackup = this.rightOpen
        this.rightOpen = false
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
    // HMI人机交互屏：与 3D 数字孪生对等的主视图形态（不进 tab 列表），
    // 开启时回到主视图槽位（功能视图窗口保持打开，点其标签可再切回）
    toggleOverview() {
      this.overviewOn = !this.overviewOn
      if (this.overviewOn) this.activeViewId = null
    },
    // AI 群控视图入口（活动栏 / 顶栏 AI 菜单共用）：
    // 参数优化训练面板已内嵌于群控视图右侧栏（训练相关设定，GA/PSO/RL 顶部可切换）；
    // 打开时默认选中遗传算法（已选优化算法则保持不跳变），并保持外部右栏收起（_activateView 已处理）
    openAiGroup() {
      this.toggleAiGroup()
      if (!this.aiGroupOn) return
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
    closeInspector() {
      // 关闭 AI 模型训练面板时退回「模型列表（按类别）」面板，而不是直接关闭检视器
      const sid = this.selectedStrategyId
      if (typeof sid === 'string' && sid.startsWith('ai::') && sid !== 'ai::overview') {
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
      this.toast = t('策略「{name}」已保存，可在策略资源管理中查看', { name: sname })
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
        else this.toast = t('「其它」分组暂无已安装的资源包：请先在场景设置中「导入资源包」安装 .ec 文件（系统内置示例：机房热控）')
        return
      }
      const meta = this.sceneIndex.find((x) => x.id === id)
      if (meta && meta.ready) { await this.openScene(meta.id); return }
      const label = (meta && meta.label) || (this.scenarios.find((s) => s.id === id) || {}).label || id
      this.toast = t('「{label}」行业资源包尚未安装：可通过「导入资源包」安装对应 .ec 定制包后打开（当前内置：钢铁、机房热控示例）', { label })
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
    async openScene(sceneId) {
      if (!sceneId) return false
      const sameMode = this.sceneMode === (sceneId === 'steel' ? 'steel' : 'other')
      if (sceneId === this.sceneId && sameMode) return true
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
      this.sceneBusy = true
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
        // 编排方案：优先恢复本场景本地存档，否则按包模板构建
        const saved = this._loadScheme()
        this.processRoute = isSteel ? ((saved && saved.route) || 'short') : (defaultRoute || 'cool')
        this.scheme = (saved && saved.scheme) ? saved.scheme : this._buildSceneScheme(this.processRoute)
        if (!this.scheme.groups) this.scheme.groups = []
        // 非钢场景模板方案没有 devices 字段，补齐为数组——否则 setDeviceSetpoint 等
        // 一律按 scheme.devices.find 访问会抛 TypeError，导致设定值写入后 _saveScheme/refresh 中断
        if (!this.scheme.devices) this.scheme.devices = []
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
        this.deviceSetpoints = {}
        this.deviceExtraSetpoints = {}
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
        this.selectedUnitId = null
        this.selectedGroupId = null
        this.selectedFlowId = null
        this.deviceDetailId = null
        this.selectedMaterialId = null
        this.selectedStrategyId = null
        this.selectedAssetType = null
        this.inspectorView = 'auto'
        // 编译模型并按场景模式刷新（其它场景走本地静态核算，不请求钢铁碳引擎）
        this.compileSchemeToModel()
        if (!isSteel) {
          this._otherSceneRefresh()
          this._pushModelToFeed()   // 新场景模型同步给实时数据源，避免继续按旧 model 下发遥测
        } else {
          await this._loadSteelSession()
        }
        this._saveScheme()
        // sceneVersion：左右面板（资源树 / 检视器）以它为 :key 重建，清空本地折叠态/档位等残留
        this.sceneVersion++
        try { localStorage.setItem('sim.sceneId', sceneId) } catch (e) { /* localStorage 不可用时忽略 */ }
        // 3D 重建延后一帧：等面板按新 key 挂载、容器尺寸稳定后再 buildModel，
        // 避免 canvas 0x0 导致相机投影矩阵 NaN（与 exitEdit 的处理口径一致）
        await nextTick()
        this.sceneRev++
        const label = meta.label || pkg.meta.label || sceneId
        this.toast = t('已打开场景「{label}」', { label })
        this.pushCmd(t('已打开场景「{label}」：资源列表、编排方案与孪生模型已切换。', { label }), 'cmd')
        return true
      } catch (e) {
        this.toast = t('打开场景失败：') + e.message
        this.notify('error', t('打开场景失败'), e.message)
        return false
      } finally {
        this.sceneBusy = false
      }
    },
    // 启动恢复：自动打开上次退出前打开的场景（localStorage sim.sceneId，随 openScene 写入）。
    // 场景已卸载 / 资源包未就绪时保持默认场景并给出提示，不阻断启动流程。
    async restoreLastScene() {
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
      const units = (this.model.units || []).map((u) => {
        const packKW = (Number((u.params && u.params.power != null) ? u.params.power : 0) || 0) * 1000   // 包模板功率以 MW 计
        const meas = _attachedSensorPower(u, srcMap, now, this.deviceSetpoints)
        const powerKW = meas ? meas.kW : packKW
        const carbonKg = powerKW * gridKg       // kgCO₂/h（范围二）
        return {
          ...u,
          // 注意：不把功率来源传感器塞进 u.devices —— 这些附加设备已由 allDevices 的
          // attached[] 分支合成为设备（id 相同），重复列出会造成设备树重复与详情定位歧义。
          devices: [],
          ..._otherUnitMetrics(powerKW, carbonKg),
          packPowerKW: packKW,  // 包内功率参数（出厂设定）
          powerMeasured: !!(meas && meas.measured),    // 实测功率（数据源绑定的采集设备）
          powerSimulated: !!(meas && meas.simulated),  // 模拟/固定值来源
          powerSources: meas ? meas.sources : [],
        }
      })
      const carbonTotal = units.reduce((a, u) => a + (u.carbon || 0), 0)
      const energyTotal = units.reduce((a, u) => a + (u.energy || 0), 0)
      this.baseline = {
        units,
        flows: this.model.flows,
        totals: {
          ...totals0,
          carbon: carbonTotal,                  // kgCO₂/h（本场景口径）
          energy: energyTotal,                  // kWh/h
          // 碳引擎口径（全厂总览 KPI）：非钢场景用电全部为外购电 → 只有范围二
          co2_total: carbonTotal / 1000,        // tCO₂/h
          co2_direct: 0,                        // 无直接排放
          co2_indirect: carbonTotal / 1000,     // 外购电（范围二）
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
      const units = this.model.units.map((mu) => {
        const prev = prevMap.get(mu.id) || {}
        const packKW = (Number((mu.params && mu.params.power != null) ? mu.params.power : 0) || 0) * 1000
        const meas = _attachedSensorPower(mu, srcMap, now, this.deviceSetpoints)
        const powerKW = meas ? meas.kW : packKW
        const carbonKg = powerKW * gridKg
        return {
          ...prev,
          ..._otherUnitMetrics(powerKW, carbonKg),
          packPowerKW: packKW,
          powerMeasured: !!(meas && meas.measured),
          powerSimulated: !!(meas && meas.simulated),
          powerSources: meas ? meas.sources : [],
        }
      })
      const carbonTotal = units.reduce((a, u) => a + (u.carbon || 0), 0)
      const energyTotal = units.reduce((a, u) => a + (u.energy || 0), 0)
      this.baseline = {
        ...this.baseline,
        units,
        totals: {
          ...(this.baseline.totals || {}),
          carbon: carbonTotal,
          energy: energyTotal,
          co2_total: carbonTotal / 1000,
          co2_direct: 0,
          co2_indirect: carbonTotal / 1000,
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
      this.editMode = true
      this.closeInspector()
      this.rightOpen = true
      // 方案是单一真源：不重新从孪生模型反向编译，保持上次完成编排时的确切状态。
      // 若方案为空（首次进入），以当前路线构建默认方案。
      if (!this.scheme || !this.scheme.nodes || this.scheme.nodes.length === 0) {
        const route = this.processRoute || 'short'
        this.scheme = this._buildSceneScheme(route)
      }
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
      this.compileSchemeToModel()
      this.autoLayout()
      this.refresh()
      this.scheme.activeGroupId = null   // 退出编排后 3D 孪生回到顶层场景
      // 先置非编辑态再关 tab：closeViewById('flowEdit') 依赖此标志区分「完成编排」与「普通关闭」
      this.editMode = false
      this.closeViewById('flowEdit')
      this.toast = t('已应用编排方案，刷新孪生视图')
      this._saveScheme()   // 持久化编排结果，刷新后保持最后一次编排状态
      // sceneRev 的触发由 SceneViewer 的 flowEditing watch 统一管理，
      // 确保 DOM 可见 + resize 完成后再 rebuildScene，避免 canvas 0x0 导致相机投影矩阵 NaN
    },

    loadTemplate(route) {
      this._histCapture('tmpl_' + uid('h'))
      this.processRoute = route
      this.scheme = this._buildSceneScheme(route)
      // 保证模板方案的 group 容器字段齐全（buildScheme 返回的 groups/activeGroupId）
      if (!this.scheme.groups) this.scheme.groups = []
      if (this.scheme.activeGroupId == null) this.scheme.activeGroupId = null
      this.selectedFlowId = null
      this.selectedGroupId = null
      try { localStorage.setItem('sim.processRoute', route) } catch (e) {}
      this._saveScheme()   // 持久化当前模板方案，刷新后保持
      // 切模板后必须重编译模型并重算（与 openProject 对齐）：否则 model / baseline 仍挂着
      // 旧模板的工艺节点 id，而新方案节点 id 已更换 —— 管道速率、设备树、KPI 会整片取不到值。
      this.compileSchemeToModel()
      this.autoLayout()
      this.refresh()
      this.sceneRev++
      // 编排模式下载入模板后自动适配视图：新方案分行排布，让画布尽量占满屏幕
      if (this.editMode) this.flowZoomFit()
      this.toast = route === 'short' ? t('已载入短流程炼钢模板') : t('已载入长流程炼钢模板')
    },
    // 编排自动保存：任何场景（钢铁 / 资源包）下的编辑（增删节点、连线、参数、设备设定、物料覆盖）
    // 均防抖 400ms 写入本地存档，下次打开（刷新页面或切换场景后切回）自动恢复最后一次编排结果。
    _bindAutosave() {
      if (this._autosaveBound) return
      this._autosaveBound = true
      let timer = null
      watch(
        () => [this.scheme, this.processRoute, this.materialOverrides, this.deviceSetpoints, this.deviceExtraSetpoints],
        () => {
          clearTimeout(timer)
          timer = setTimeout(() => this._saveScheme(), 400)
        },
        { deep: true },
      )
    },
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
    // 持久化当前编排方案：完成编排（exitEdit）、载入模板、清空画布、调节设备设定值时写入，
    // 使刷新后保持最后一次编排结果，而不是回退到默认流程。
    _saveScheme() {
      if (this.simMode) return   // 仿真模式：一切编辑不持久化
      try {
        localStorage.setItem('sim.scheme', JSON.stringify({
          sceneId: this.sceneId || 'steel',   // 编排方案所属场景包：切场景不串档
          route: this.processRoute,
          scheme: this.scheme,
          materialOverrides: this.materialOverrides,
          _ovUnitV: 1,   // 价格口径标记：v1 起 price/salePrice 统一为「万元/单位」（旧版存的是元/单位）
        }))
      } catch (e) { /* localStorage 不可用时静默忽略 */ }
    },
    _loadScheme() {
      try {
        const raw = localStorage.getItem('sim.scheme')
        if (!raw) return null
        const d = JSON.parse(raw)
        if (!d || !d.scheme || !Array.isArray(d.scheme.nodes) || d.scheme.nodes.length === 0) return null
        // 编排方案随场景包隔离：只恢复与当前打开场景匹配的存档（旧版无 sceneId 视为钢包存档）
        const sid = this.sceneId || 'steel'
        if (d.sceneId && d.sceneId !== sid) return null
        // 机房温控包 2026-09-21 口径变更（水侧 + 风侧开式，无机房回风；变频器 → 变压器）：
        // 存档里若出现不在新口径内的工序类型或物料（含已删除的「机房回风」hot_air 介质与回风回路）、
        // 旧的可调设备类型，说明是旧版编排方案 —— 丢弃存档改按新模板重建，否则刷新后仍看到旧流程，
        // 误以为资源包没更新。
        if (sid === 'dc-thermal') {
          const DC_TYPES = ['dc_chiller', 'dc_fan_cool', 'dc_it']
          const DC_MATS = ['cool_water_supply', 'cool_water_return', 'cold_air']
          const badNode = d.scheme.nodes.some((n) => {
            if (!n || DC_TYPES.indexOf(n.type) < 0) return true
            const ports = (n.ports && n.ports.in ? n.ports.in : []).concat(n.ports && n.ports.out ? n.ports.out : [])
            return ports.some((p) => p && DC_MATS.indexOf(p.material) < 0)
          })
          const badConn = (d.scheme.connections || []).some((c) => c && DC_MATS.indexOf(c.material) < 0)
          // 附加设备口径三次变更：① 制冷风机的「半导体制冷电源」由通用可变电源（variable_psu，
          // 0~66000 V / 步长 10）改为专用 TEC 电源（tec_psu，0~60 V）；② 冷却水的「循环水泵变频器」
          // （frequency_converter，Hz）改为「循环水泵变压器」（pump_transformer，设定值=输出电压 V）；
          // ③ 折碳功率口径改为「传感器承载」——可变设备只留设定值、不再声明实时数据（有功功率），
          // 实际功率由本工序附加的电功率传感器（power_sensor，kW）给出（可绑定数据源实测、
          // 也可随可变设备联动）。旧存档沿用旧类型会让详情面板量程/默认值与折碳口径都对不上，按旧存档丢弃重建。
          const OLD_ATT = ['variable_psu', 'frequency_converter']
          const someAtt = (fn) => d.scheme.nodes.some((n) => ((n && n.attached) || []).some(fn))
          const badAtt = someAtt((a) => a && OLD_ATT.indexOf(a.type) >= 0)
          // 冷却水侧「冷却水流速传感器」（随循环水泵变压器设定值联动）与「循环水泵变压器」、
          // 以及水侧 / 风侧各一个「电功率传感器」（折碳功率来源）缺一即视为旧存档，
          // 保证刷新后直接看到「变压器调工况 → 功率传感器随动 → 实测值进入折碳」的完整链路。
          const missFlow = !someAtt((a) => a && a.type === 'water_speed_sensor')
          const missPump = !someAtt((a) => a && a.type === 'pump_transformer')
          const missPower = !someAtt((a) => a && a.type === 'power_sensor')
          if (badNode || badConn || badAtt || missFlow || missPump || missPower) return null
        }
        return d
      } catch (e) { return null }
    },
    // 以指定流程示例方案直接编译为 3D 模型（含工辅连线 + 统一布局），
    // 用于首屏默认流程（短流程）。与 exitEdit 的「完成编排」走同一套编译/布局逻辑，保证两模式一致。
    _setDefaultRoute(route) {
      this.scheme = buildScheme(route)
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
      this._saveScheme()                 // 持久化项目路线，刷新后保持
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
      this._saveScheme()   // 持久化清空结果（空方案刷新后按流程路线重建默认，避免回退到旧方案）
    },
    // 从左栏拖入创建节点（kind: process|device|material）
    // ===== 附加设备（传感器 / 可变设备）：绑定 / 解除 / 数值来源 =====
    // 在某工艺节点上添加一个附加设备（kind: sensor / adjustable，type 取附加库模板 type），
    // 实例存入工艺节点 node.attached[]（随方案持久化）；运行态 id 合成为 ext::节点id::attUid，
    // 在资源管理器 / 设备树 / 数据分析中即出现相应设备。
    addAttachToNode(nodeId, kind, type) {
      const node = this.scheme.nodes.find((n) => n.id === nodeId)
      if (!node) return null
      const tpl = _attachTpl(kind, type)
      if (!tpl) return null
      const att = {
        uid: uid('a'),
        kind,
        type,
        label: tpl.label,
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
      this._saveScheme()
      return att
    },
    removeAttachFromNode(nodeId, uidToRemove) {
      const node = this.scheme.nodes.find((n) => n.id === nodeId)
      if (!node || !Array.isArray(node.attached)) return
      const i = node.attached.findIndex((a) => a.uid === uidToRemove)
      if (i < 0) return
      node.attached.splice(i, 1)
      this._histCapture('det_' + nodeId + uid('h'))
      this._saveScheme()
      const extId = `ext::${nodeId}::${uidToRemove}`
      if (this.deviceDetailId === extId) this.deviceDetailId = null
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
      this._saveScheme()
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
      this._saveScheme()
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
      this._saveScheme()
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
    // 可变设备设定值统一入口（编排面板 / AI 群控共用）：
    // 先本地设定，若已绑定数据源设备的可写点位则自动下发写入（失败只提示，不回滚本地设定）
    setExtSetpoint(extId, value) {
      this.setDeviceSetpoint(extId, value)
      const hit = this._attachByExtId(extId)
      if (!hit || hit.att.src !== 'device' || !hit.att.device || !hit.att.prop) return
      const { att } = hit
      this.writeAttachBound(extId, value).then((r) => {
        if (r && r.ok) {
          this.showToast(t('已下发写点位 {dev} · {prop} = {v}', { dev: att.device, prop: att.prop, v: value }), 'success')
        } else {
          this.showToast(t('写点位下发失败') + '：' + ((r && r.error) || ''), 'error')
        }
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
      this._saveScheme()
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
      this._saveScheme()
    },
    resetFlowParamRange(id, key) {
      this._histCapture('fr_' + id + key)
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (!n || !n.ranges) return
      const next = { ...n.ranges }
      delete next[key]
      if (Object.keys(next).length) n.ranges = next
      else delete n.ranges
      this._saveScheme()
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
      this._saveScheme()
    },
    resetFlowDeviceRange(id) {
      this._histCapture('dr_' + id)
      const n = this.scheme.nodes.find((x) => x.id === id)
      if (n && n.range) delete n.range
      this._saveScheme()
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
      this._saveScheme()
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
    setDeviceSetpoint(deviceId, val) {
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
      // 设备设定值现已桥接为高炉操作参数，需重算让后端权威仿真与 3D 热力同步
      this._saveScheme()   // 设定值随方案持久化，刷新后不丢失
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
      this._saveScheme()   // 设定值随方案持久化，刷新后不丢失
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
      const h = NODE_HEADER + (NODE_PORT_Y0 - 7) + (cnt - 1) * NODE_GAP + 16 + 12
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
    // 将编排方案编译为现有仿真 model（工序=工艺节点，物流=连接），供 3D 孪生重绘
    // 注意：后端碳引擎仅识别标准工艺类型，故"公用/节能"节点(煤气发电/余热/CCUS)不纳入 3D 仿真，
    // 其减碳作用在编辑态前端估算中已计入。
    compileSchemeToModel() {
      // 通用资源包场景（其它分组）：包内 scheme 直译为单位模型（无钢字典语义）
      if (this.sceneMode !== 'steel') return this._compileOtherScheme()
      const procs = this.scheme.nodes.filter((n) => n.kind === 'process' && PROCESS_MAP[n.type] && PROCESS_MAP[n.type].route !== 'util')
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
      const nodeById = Object.fromEntries((this.scheme.nodes || []).map((n) => [n.id, n]))
      const flowOk = (c) => {
        const f = nodeById[c.from], t = nodeById[c.to]
        const ft = f && PROCESS_MAP[f.type], tt = t && PROCESS_MAP[t.type]
        if (!ft || !tt) return false
        const m = c.material
        return !!m && (ft.outputs || []).includes(m) && (tt.inputs || []).includes(m)
      }
      const flows = this.scheme.connections
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
        groups: (this.scheme.groups || []).map((g) => ({ id: g.id, name: g.name || '设备小组' })),
      }
    },

    // 通用资源包场景（其它分组）编译：包内 scheme 直译为 3D 单位模型。
    // 所有工艺节点按模板坐标排布、连线全保留（包模板连线可信，手工连线画布已校验端口）；
    // 不依赖钢流程字典（PROCESS_MAP）与后端碳引擎；附加传感器/可变设备随 unit 携带。
    _compileOtherScheme() {
      const nodes = (this.scheme && this.scheme.nodes) || []
      const conns = (this.scheme && this.scheme.connections) || []
      const procSet = new Set(nodes.filter((n) => n.kind === 'process').map((n) => n.id))
      const units = nodes.filter((n) => n.kind === 'process').map((n) => ({
        id: n.id,
        type: n.type,
        name: n.name || n.type,
        params: { ...(n.params || {}) },
        techs: Array.isArray(n.techs) ? n.techs : [],
        spec: n.spec || '',
        groupId: n.groupId || null,
        enabled: n.enabled !== false,
        rot: n.rot || 0,
        attached: Array.isArray(n.attached) ? n.attached.map((x) => ({ ...x })) : [],
        x: Math.round(((n.x != null ? n.x : 0) - 400) / 40),
        z: Math.round(((n.y != null ? n.y : 0) - 300) / 40),
      }))
      const flows = conns
        .filter((c) => procSet.has(c.from) && procSet.has(c.to))
        .map((c) => ({ id: c.id, from_unit: c.from, to_unit: c.to, material: c.material, rate: c.rate || 1000 }))
      this.model = {
        units,
        flows,
        groups: (this.scheme.groups || []).map((g) => ({ id: g.id, name: g.name || '设备小组' })),
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
