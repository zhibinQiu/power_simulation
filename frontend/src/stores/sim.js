import { defineStore } from 'pinia'
import { api, openFeed } from '../api/client'
import { buildScheme, makeProcessNode, makeDeviceNode, makeMaterialNode, PROCESS_MAP, MATERIAL_MAP, PROCESS_ADJUSTABLE, DEVICE_MAP, DEVICE_COUPLE_REGISTRY, deriveProcessOpParams, materialFamily, loadCalibrations, NODE_NW, NODE_HEADER, NODE_PORT_Y0, NODE_GAP, nodeHeight, PROCESS_TEMPLATES, applySetpointResponse, migrateLegacyDevices, treeLayoutNodes } from '../data/flowLibrary'
import { computeScheme } from '../flow/compute'
import { PARK } from '../data/park'
// 工艺静态业务数据：集中维护于独立数据模块 src/data/processMeta.js
// （业务数据与代码逻辑分离），本 store 只负责仿真状态与交互逻辑；
// 下方 re-export 保持既有组件 `import { ... } from '../stores/sim'` 兼容。
import { OP_PARAM_KEYS, DIRECT_PARAM_KEYS, EDITABLE_PARAMS, UNIT_TYPES, CATEGORY_ORDER, TECHS } from '../data/processMeta'
export { OP_PARAM_KEYS, DIRECT_PARAM_KEYS, EDITABLE_PARAMS, UNIT_TYPES, CATEGORY_ORDER, TECHS }

// AI 优化模型：左侧「策略 → AI优化模型」目录（强化学习 / 遗传算法 / 粒子群）。
// 随实时传感器数据持续采集，后端调度线程定时训练，模型迭代次数与最优强度逐步提升
// （属性面板轮询后端状态实时展示「逐渐变优」过程，训练结果可一键应用到流程）。
export const AI_MODELS = [
  { id: 'ai::rl', name: '强化学习优化', tag: 'RL', desc: '在线策略梯度：随实时传感器数据持续更新参数策略，先探索后利用，越训越优。' },
  { id: 'ai::ga', name: '遗传算法优化', tag: 'GA', desc: '种群进化寻优：对喷煤比、焦比、废钢比等关键工艺参数组合做选择/交叉/变异，全局搜索最低碳排配置。' },
  { id: 'ai::pso', name: '粒子群优化', tag: 'PSO', desc: '群体智能寻优：粒子在参数空间协同飞行，快速逼近最优运行点，适合实时在线寻优。' },
]
export const AI_MODEL_MAP = Object.fromEntries(AI_MODELS.map((m) => [m.id, m]))

let _idc = 0
const uid = (p) => `${p}_${Date.now().toString(36)}${(_idc++).toString(36)}`
// 数值展示：保留 2 位小数并去掉末尾多余的 0
const fmtNum = (v) => (v == null || isNaN(v) ? '—' : Number(v).toFixed(2).replace(/\.?0+$/, ''))

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

// 某工序实例的可调设备类型 = 基础清单(PROCESS_ADJUSTABLE) + 实际连线供给的工辅类型（含上游链路传递）
function adjustableTypesFor(scheme, unitType, unitId) {
  const set = new Set(PROCESS_ADJUSTABLE[unitType] || [])
  for (const dt of linkedAuxTypesFor(scheme, unitId)) set.add(dt)
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
    toast: '',
    scenario: 'steel',           // 当前仿真场景（四大控排）：steel 钢铁(默认) / cement 水泥 / chemical 化工 / nonferrous 有色
    processRoute: 'short',       // 当前流程：short 短流程(默认) / long 长流程；数字孪生默认展示短流程
    scenarios: [
      { id: 'steel', label: '钢铁' },
      { id: 'cement', label: '水泥' },
      { id: 'chemical', label: '化工' },
      { id: 'nonferrous', label: '有色' },
    ],
    envMode: 'industrial',      // 场景环境：void 虚空 / industrial 工业(默认) / desert 沙漠 / city 城市 / coast 海滩
    envModes: [
      { id: 'void', label: '虚空' },
      { id: 'industrial', label: '工业' },
      { id: 'desert', label: '沙漠' },
      { id: 'city', label: '城市' },
      { id: 'coast', label: '海滩' },
    ],
    envNonce: 0,                // 触发中间 3D 场景切换环绕环境
    sceneRev: 0,
    factors: null,            // 当前排放因子配置（燃料 NCV/CC、电网因子、碳酸盐/电极因子），null 表示用后端默认
    factorsDefault: null,      // 排放因子默认基线（init 时快照），用于编辑态估算的偏移归零，保证未编辑时基线不变
    paramSchema: null,        // 工序参数分级元数据（后端 /api/param-schema）：config/optim + 参考范围
    deviceLibrary: null,      // 内置监测设备库（后端 /api/devices）：设备类型元数据 + 各工序设备规格
    platformConfig: null,     // 平台可配置项（工艺规模档位/设备量程/参数运行空间），后端持久化
    deviceDetailId: null,     // 当前打开详情的设备 id（3D 图点设备或工序设备列表触发）
    focusNonce: 0,         // 触发中间 3D 相机聚焦（任意选中均发起）
    focusKind: null,        // 'unit' | 'device'
    focusId: null,
    viewNonce: 0,          // 触发中间 3D 以指定视角查看工序（俯视/正视/侧视/聚焦/全景）
    viewMode: 'focus',     // 'focus' | 'front' | 'side' | 'top' | 'overview'
    viewId: null,
    // 三栏布局 & 检视器状态
    leftOpen: true,           // 左侧栏是否展开
    rightOpen: true,          // 右侧栏（检视器）是否展开
    bottomOpen: true,
    newsTickerOn: (() => { try { return localStorage.getItem('sim.newsTickerOn') !== '0' } catch (e) { return true } })(),  // 底栏快讯是否显示（默认开，localStorage 持久化）
    fullscreenOn: false,      // 全屏模式：隐藏左/右/底栏，仅保留 3D 场景
    dataViewOn: false,        // 数据视图：中间 3D 场景替换为传感器历史数据表格（顶栏「视图 → 数据视图」切换）
    carbonMarketOn: false,    // 碳市场视图：中间 3D 场景替换为碳市场实时行情（顶栏「视图 → 碳市场」切换）
    inspectorView: 'auto',    // 右侧检视器显式视图：'auto'（按选中推导）| 'park' 园区构成 | 'materials' 原料库 | 'strategy' 减排策略 | 'report' 报告面板         // 底栏（命令行窗口 + 状态条）是否展开
    reportPayload: null,      // 「导出报告」请求载荷（baseline/strategy/ops/...），供右侧报告面板消费
    selectedStrategyId: null, // 左侧策略库选中的策略
    deviceHistory: {},        // 各设备历史读数序列：devId -> [{t, v}]
    deviceLive: {},           // 各设备实时读数：devId -> number
    deviceSetpoints: {},      // 可调设备设定值覆盖：devId -> number（视图态/编辑态统一存储，驱动实时读数与碳引擎折算）
    deviceExtraSetpoints: {}, // 可调设备附加可调项（如鼓风机鼓风湿度）：devId -> { key: number }
    deviceMeta: {},           // 设备元数据（后端 /api/devices/history 的 meta）
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
    // 实时数据源配置（文件菜单「连接数据源」设置，支持内置模拟/自定义WebSocket/HTTP轮询）
    dataSource: { type: 'sim', url: '', interval: 1000, name: '内置模拟数据' },
    // ---- 左侧活动栏（VS Code 式）与多数据源管理 ----
    activityView: 'explorer',   // 活动面板：'explorer' 资源 | 'search' 搜索 | 'scene' 场景 | 'connections' 连接
    dataSources: [],            // 多数据源列表，每个含 { id,type,url,interval,name,enabled,mapping }
    activeDataSourceId: 'sim',  // 当前活动数据源 id（状态栏/指令区使用的活动源）
    sourceStatus: {},           // 各数据源连接状态：sourceId -> 'init'|'open'|'closed'|'error'
    lastFields: {},             // 各数据源最近一次遥测收到的外部字段：sourceId -> string[]
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
    materialOverrides: {},      // 物料隐含碳因子覆盖：matId -> { carbon }（本会话内）
    // 撤销/重做栈（仅编辑态编排方案）
    historyPast: [],        // 历史快照（每次编辑前压入上一状态）
    historyFuture: [],      // 重做快照
    // 命令行窗口日志（全局共享：App 顶栏/按钮、ReportPanel 报告进度等均可推送）
    cmdLog: [],             // [{ t, k }] k: cmd|out|sys|guide|tip|warn|err|bot|sim
    // 系统通知中心（底栏铃铛）：{ id, level: 'info'|'success'|'warn'|'error', title, body, time, read }
    notifications: [],
  }),
  getters: {
    // 未读系统通知数（底栏铃铛徽标）
    unreadNotifs: (s) => s.notifications.filter((n) => !n.read).length,
    selectedUnit: (s) => s.model.units.find((u) => u.id === s.selectedUnitId) || null,
    selectedResult: (s) => {
      if (!s.selectedUnitId || !s.baseline) return null
      return s.baseline.units.find((u) => u.id === s.selectedUnitId) || null
    },
    // 某工序实例实际连线绑定的工辅类型（由编排画布中的物料连线决定，含上游链路传递）
    linkedAuxOfUnit: (s) => (unitId) => linkedAuxTypesFor(s.scheme, unitId),
    resultForView: (s) => s.strategy || s.baseline,
    liveUnit: (s) => (id) => (s.live && s.live.units ? s.live.units.find((u) => u.id === id) : null),
    // 某工序的内置监测设备（含模拟读数），来自 baseline 仿真结果附带
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
      if (typeof s.selectedStrategyId === 'string' && s.selectedStrategyId.startsWith('ai::')) {
        const m = AI_MODEL_MAP[s.selectedStrategyId]
        if (m) return { id: s.selectedStrategyId, name: m.name, description: m.desc, source: 'ai' }
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
      return out
    },
    deviceHistoryOf: (s) => (id) => s.deviceHistory[id] || [],
    deviceLiveOf: (s) => (id) => (s.deviceLive[id] != null ? s.deviceLive[id] : null),
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
    pushCmd(t, k = 'out') { this.cmdLog.push({ t, k }) },
    clearCmdLog() { this.cmdLog = [] },
    // —— 系统通知中心（底栏铃铛）——
    // 新增一条系统通知，自动附带 toast 提示；列表最多保留 50 条
    notify(level = 'info', title = '', body = '') {
      const n = { id: uid('ntf'), level, title, body, time: Date.now(), read: false }
      this.notifications.push(n)
      if (this.notifications.length > 50) this.notifications.splice(0, this.notifications.length - 50)
      return n.id
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
        this._loadDataSource() // 恢复上次设置的实时数据源（内置模拟/自定义WS/HTTP）
        const [m, presets, factors, schema, devs, hist, pcfg] = await Promise.all([
          api.presetModel(), api.presetStrategies(), api.getFactors(), api.getParamSchema(),
          api.getDevices(), api.getDeviceHistory(), api.getPlatformConfig(),
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
          // 迁移：彻底移除历史方案中的旧 facility 节点（旧「工辅/设施」概念已删除，仅处理存量数据）
          const kept = new Set((this.scheme.nodes || []).filter((n) => n && n.kind !== 'facility').map((n) => n.id))
          this.scheme.nodes = this.scheme.nodes.filter((n) => n && n.kind !== 'facility')
          this.scheme.connections = (this.scheme.connections || []).filter((c) => kept.has(c.from) && kept.has(c.to))
          this.processRoute = saved.route || this.processRoute
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
        this.deviceLibrary = devs   // 内置监测设备库，供 3D 设备标记与设备详情面板使用
        this.platformConfig = pcfg  // 平台可配置项（工艺规模档位/设备量程/参数运行空间）
        // 设备历史时序（首屏即带趋势）
        if (hist && hist.history) this.deviceHistory = hist.history
        if (hist && hist.meta) this.deviceMeta = hist.meta
        this.autoLayout()        // 初次加载先按序等距自动布局，避免工艺图标重叠
        this.presets = presets
        await this._runRefresh()  // 首屏立即重算（不走防抖），保证 KPI 就绪
        await this.loadStrategies()
        this.ready = true
        this.notify('success', '系统就绪', `数字孪生已载入 ${this.model.units.length} 个工序、${this.model.flows.length} 条物流，实时链路与优化模型已就绪。`)
        this._startFeed()
        // AI 优化模型：同步训练上下文并轮询状态（后台定时训练由后端调度，前端展示「逐渐变优」）
        this.syncOptimizerContext().then(() => this.refreshOptimizers())
        this.startOptimizerPolling()
      } catch (e) {
        this.toast = '初始化失败：' + e.message
        this.notify('error', '初始化失败', e.message)
      }
    },
    // 把"合成可调设备"的设定值按 DEVICE_COUPLE_REGISTRY 推导为各工序参数，
    // 注入模型副本（不污染源 model）。设备设定值优先（实际装备工况即运行点）。
    _applyDeviceOpParams(model) {
      if (!model || !model.units) return model
      const units = model.units.map((u) => {
        const reg = DEVICE_COUPLE_REGISTRY[u.type]
        if (!reg) return u
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
        if (!Object.keys(overrides).length) return u
        return { ...u, params: { ...(u.params || {}), ...overrides } }
      })
      return { ...model, units }
    },
    // 刷新防抖：滑块/设备设定拖动会高频触发，合并为「停顿后一次」后端重算（约 280ms），
    // 本地参数/设定值已即时更新保证跟手，避免每次输入都打全量仿真请求（卡顿与时延根因）。
    async _runRefresh() {
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
        this.toast = '请先输入并解析策略'
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
          this._simLog('strategy', '策略仿真', (this.parsedText || '').slice(0, 60) || `应用 ${this.parsed.ops.length} 项操作`, 'exp')
        }
        this.sceneRev++   // 触发中间孪生平台随之变化（重算热力着色/CO2 占比）
      } finally {
        this.busy = false
      }
    },
    clearExperiment() {
      this.strategy = null
      this.delta = null
      this.simOps = []
      if (this.simMode) {
        this.simCurrent = this.baseline ? JSON.parse(JSON.stringify(this.baseline)) : null
        this._simLog('strategy', '清除策略', '恢复当前参数下的基线结果')
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
              this.toast = `「${(AI_MODEL_MAP[m.id] || {}).name || '优化模型'}」训练取得新进展：最优强度 ${m.reminder.best_fitness} kgCO₂/t（较上版提升 ${m.reminder.improvement_pct}%）。已生成调优提醒，可在属性面板手动应用优化参数`
              this.notify('info', `「${(AI_MODEL_MAP[m.id] || {}).name || '优化模型'}」训练新进展`, `最优强度 ${m.reminder.best_fitness} kgCO₂/t，较上版提升 ${m.reminder.improvement_pct}%。可在属性面板手动应用优化参数。`)
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
          this.toast = `AI 自动化控制：已按「${(AI_MODEL_MAP[id] || {}).name || '优化模型'}」最新版本自动下发参数到可调设备`
          this.notify('success', 'AI 自动化控制', `已按「${(AI_MODEL_MAP[id] || {}).name || '优化模型'}」最新版本自动下发参数到可调设备。`)
          this.pushCmd(`AI 自动化控制已下发：应用「${r.name || id}」版本参数（最优 ${(r.best_fitness ?? 0).toFixed(2)} kgCO₂/t，提升 ${r.improvement_pct ?? 0}%）`, 'sim')
          this._pushModelToFeed()
          await this._runRefresh()
        }
      } catch (e) {
        this.toast = 'AI 自动化控制下发失败：' + e.message
        this.notify('error', 'AI 自动化控制下发失败', e.message)
      }
      try { await api.ackOptimizer(id) } catch (e) { /* 忽略确认失败 */ }
      this.optimizerAutoApplying = { ...this.optimizerAutoApplying, [id]: false }
      await this.refreshOptimizers()
    },
    startOptimizerPolling(ms = 3000) {
      if (this.optimizerPolling) return
      this.optimizerPolling = true
      this._optTimer = setInterval(() => this.refreshOptimizers(), ms)
    },
    stopOptimizerPolling() {
      if (this._optTimer) { clearInterval(this._optTimer); this._optTimer = null }
      this.optimizerPolling = false
    },
    async startOptimizer(id) {
      await this.syncOptimizerContext()   // 训练对象始终是最新流程
      try {
        const r = await api.startOptimizer(id)
        if (r) this.toast = `已开启「${(AI_MODEL_MAP[id] || {}).name || '优化模型'}」自动训练：后台将随实时传感器数据定时迭代`
      } catch (e) {
        this.toast = '开启自动训练失败：' + e.message
      }
      await this.refreshOptimizers()
    },
    async stopOptimizer(id) {
      try {
        const r = await api.stopOptimizer(id)
        if (r) this.toast = `已暂停「${(AI_MODEL_MAP[id] || {}).name || '优化模型'}」自动训练`
      } catch (e) {
        this.toast = '暂停训练失败：' + e.message
      }
      await this.refreshOptimizers()
    },
    async trainOptimizer(id, steps = 1) {
      try {
        await api.trainOptimizer(id, steps)
      } catch (e) {
        this.toast = '训练失败：' + e.message
      }
      await this.refreshOptimizers()
    },
    async resetOptimizer(id) {
      await this.syncOptimizerContext()
      try {
        const r = await api.resetOptimizer(id)
        if (r) this.toast = `「${(AI_MODEL_MAP[id] || {}).name || '优化模型'}」已重置`
      } catch (e) {
        this.toast = '重置失败：' + e.message
      }
      await this.refreshOptimizers()
    },
    async setOptimizerHyper(id, patch) {
      try {
        const r = await api.setOptimizerHyper(id, patch)
        if (r) this.toast = '算法超参数已保存，下一轮训练生效'
      } catch (e) {
        this.toast = '保存超参数失败：' + e.message
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
        this.toast = '应用最优参数失败：' + e.message
        this.notify('error', '应用最优参数失败', e.message)
        return
      }
      this.model = r.model
      this.baseline = r.sim
      this.clearExperiment()
      this.parsed = null
      this.toast = `已将「${(AI_MODEL_MAP[id] || {}).name || '优化模型'}」最优参数应用到流程`
      this.notify('success', '已应用最优参数', `已将「${(AI_MODEL_MAP[id] || {}).name || '优化模型'}」最优参数应用到流程，强度 ${(r.best_fitness ?? 0).toFixed(2)} kgCO₂/t。`)
      this.pushCmd(`已应用 AI 优化模型「${r.name || id}」最优参数：强度 ${(r.best_fitness ?? 0).toFixed(2)} kgCO₂/t，较初始 ${r.improvement_pct ?? 0}%`, 'sim')
      this._pushModelToFeed()
      await this._runRefresh()
      await this.refreshOptimizers()
    },
    // 保存控制与自训练设置：{ auto_control?: bool, schedule?: { interval?, window? } }
    async setOptimizerSettings(id, patch) {
      try {
        const r = await api.setOptimizerSettings(id, patch)
        if (r && typeof r.auto_control === 'boolean') {
          this.toast = r.auto_control
            ? `已开启「${(AI_MODEL_MAP[id] || {}).name || '优化模型'}」自动化控制：模型变优后自动下发参数到可调设备`
            : `已关闭「${(AI_MODEL_MAP[id] || {}).name || '优化模型'}」自动化控制：改为系统提醒手动调优`
        }
      } catch (e) {
        this.toast = '保存控制设置失败：' + e.message
      }
      await this.refreshOptimizers()
    },
    // 把当前最优参数保存为模型版本（仅优于当前版本才替换生效）
    async archiveOptimizer(id) {
      let r = null
      try {
        r = await api.archiveOptimizer(id)
      } catch (e) {
        this.toast = '保存版本失败：' + e.message
        return
      }
      this.toast = r.promoted
        ? '已保存为新版本并替换为当前版本（历史版本仍保留）'
        : '已保存为候选版本（未超过当前版本，未替换）'
      await this.refreshOptimizers()
    },
    // 在历史模型版本间切换（旧版本保留，可随时切回）
    async switchOptimizerVersion(id, versionId) {
      try {
        await api.switchOptimizerVersion(id, versionId)
        this.toast = '已切换模型版本'
      } catch (e) {
        this.toast = '切换版本失败：' + e.message
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
    // ---- 平台可配置项（工艺规模档位/设备量程/参数运行空间）----
    async reloadPlatformConfig() {
      this.platformConfig = await api.getPlatformConfig()
      // 配置影响参数范围与设备量程：同步重拉 schema / 设备库，保证编辑器与设备面板使用新范围
      const [schema, devs] = await Promise.all([api.getParamSchema(), api.getDevices()])
      this.paramSchema = schema
      this.deviceLibrary = devs
    },
    async savePlatformConfig(cfg) {
      await api.savePlatformConfig(cfg)
      this.toast = '平台配置已保存，参数范围与设备量程已同步更新'
      await this.reloadPlatformConfig()
    },
    async resetPlatformConfig() {
      await api.resetPlatformConfig()
      this.toast = '平台配置已恢复出厂默认'
      await this.reloadPlatformConfig()
    },
    async saveStrategy(name) {
      if (!this.parsed || !this.parsed.ops.length) return
      await api.createStrategy(name || '未命名策略', '', this.parsedText, this.parsed.ops)
      await this.loadStrategies()
      this.toast = '策略已保存到策略库'
    },
    async removeStrategy(sid) {
      await api.deleteStrategy(sid)
      await this.loadStrategies()
    },
    async applyStrategy(sid) {
      // 仿真模式：记录策略应用（退出仿真时恢复，见 exitSim 快照）；同一策略重复应用合并为一条
      if (this.simMode) {
        const sname = ((this.strategies || []).find((s) => s.id === sid) || {}).name || sid
        this._simLog('strategy', '应用策略', sname, 'apply_' + sid)
      }
      const r = await api.applyStrategy(sid, this._applyDeviceOpParams(this.model), this.factors)
      this.model = r.model
      this.baseline = r.sim
      this.clearExperiment()
      this.parsed = null
      this._pushModelToFeed()
      this.toast = '策略已应用到当前流程'
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
      // 两模式互斥：操作/设备参数(wind_rate/hot_blast_temp/oxygen_enrich) 与
      // 直接调参(coke_rate/coal_inj) 最后被谁设置，谁生效。
      if (OP_PARAM_KEYS.has(key)) {
        DIRECT_PARAM_KEYS.forEach((k) => delete params[k])
      } else if (DIRECT_PARAM_KEYS.has(key)) {
        OP_PARAM_KEYS.forEach((k) => delete params[k])
      }
      params[key] = num
      u.params = params
      this.refresh(); this.autoLayout()
    },
    // 点击 3D 场景中模型旁的小铭牌：选中该工序实例并聚焦（右侧显示统一的工序实例属性面板）。
    // 无论从场景、左侧工艺目录还是列表点击，同一实例都只对应同一个实例属性面板。
    pickUnit(id) {
      this._clearBrowse()
      const u = this.model.units.find((x) => x.id === id)
      if (u && PROCESS_MAP[u.type]) this.selectedAssetType = u.type
      this.selectedMaterialId = null; this.selectedGroupId = null; this.selectedFlowId = null
      this.deviceDetailId = null
      this.selectedUnitId = id; this.inspectorView = 'auto'; this.requestFocus('unit', id)
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
        this._simLog('factor', `${ml} · 隐含碳因子`, `${fmtNum(prev)} → ${fmtNum(v)} tCO₂/${(MATERIAL_MAP[id] || {}).unit || ''}`, `mc_${id}`)
      }
      this.materialOverrides = { ...this.materialOverrides, [id]: { ...(this.materialOverrides[id] || {}), carbon: v } }
      if (this.simMode) this.refresh()
    },
    // 配置物料级自定义属性（密度 / 运输排放因子 / 含水率 / 说明备注），本会话覆盖
    setMaterialAttr(id, key, val) {
      // 仿真模式：记录物料属性变更（备注仅提示已更新，避免超长文案）
      if (this.simMode) {
        const ml = ((MATERIAL_MAP[id] || {}).label) || id
        const keyLabel = ({ density: '堆密度', transport_ef: '运输排放因子', moisture: '含水率', note: '备注' })[key] || key
        if (key === 'note') {
          this._simLog('factor', `${ml} · 备注`, '已更新', `ma_${id}_${key}`)
        } else {
          let prev = _simParamSnapshot && _simParamSnapshot.materialOverrides[id] && _simParamSnapshot.materialOverrides[id][key]
          if (prev == null) prev = (this.materialOverrides[id] || {})[key]   // 快照缺省回退当前值
          this._simLog('factor', `${ml} · ${keyLabel}`, `${fmtNum(prev)} → ${fmtNum(val)}`, `ma_${id}_${key}`)
        }
      }
      this.materialOverrides = { ...this.materialOverrides, [id]: { ...(this.materialOverrides[id] || {}), [key]: val } }
      if (this.simMode && key !== 'note') this.refresh()
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
    // 底栏快讯显示开关（localStorage 持久化，刷新后保持）
    toggleNewsTicker() {
      this.newsTickerOn = !this.newsTickerOn
      try { localStorage.setItem('sim.newsTickerOn', this.newsTickerOn ? '1' : '0') } catch (e) {}
    },
    // 数据视图：中间 3D 场景 ↔ 传感器历史数据表格（顶栏「视图 → 数据视图」切换）
    toggleDataView() {
      this.dataViewOn = !this.dataViewOn
      if (this.dataViewOn) this.carbonMarketOn = false
    },
    // 碳市场视图：中间 3D 场景 ↔ 碳市场实时行情（顶栏「视图 → 碳市场」切换）
    toggleCarbonMarket() {
      this.carbonMarketOn = !this.carbonMarketOn
      if (this.carbonMarketOn) this.dataViewOn = false
    },
    toggleFullscreen() {
      this.fullscreenOn = !this.fullscreenOn
      if (this.fullscreenOn) {
        this.leftOpen = false
        this.rightOpen = false
        this.bottomOpen = false
      } else {
        this.leftOpen = true
        this.rightOpen = true
        this.bottomOpen = true
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
    closeInspector() { this._clearBrowse(); this.deviceDetailId = null; this.selectedUnitId = null; this.selectedMaterialId = null; this.selectedStrategyId = null; this.selectedGroupId = null; this.selectedFlowId = null; this.inspectorView = 'auto' },
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
      this.toast = '已进入仿真模式：所有修改仅预览，退出后自动恢复'
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
      this.toast = '已退出仿真模式，恢复仿真前状态'
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
      this.toast = `策略「${sname}」已保存，可在策略资源管理中查看`
      return created
    },
    // 更新已保存策略（名称/描述/原文/操作），调 PUT /api/strategies/{sid}
    async updateStrategy(sid, patch) {
      await api.updateStrategy(sid, patch)
      await this.loadStrategies()
      this.toast = '策略信息已更新'
    },
    // 策略详情面板「策略仿真」按钮：内置预置策略进入仿真并解析测试；自定义策略加载并应用（退出后自动恢复）
    async runStrategySimulation(sid) {
      const st = this.selectedStrategy
      if (!st) { this.toast = '策略不存在或已删除'; return }
      if (st.source === 'preset') {
        if (!this.simMode) this.enterSim()
        this.strategyInput = st.raw_text || st.name || ''
        this.parsedText = ''
        this.parsed = null
        try {
          await this.parse(this.strategyInput)
          if (this.parsed && this.parsed.ops.length) {
            await this.runExperiment()
            this.toast = `已对内置策略「${st.name}」完成仿真测试，可在右上角对比仿真结果`
          } else {
            this.toast = '该内置策略解析结果为空'
          }
        } catch (e) {
          this.toast = '内置策略仿真失败：' + (e.message || e)
        }
        return
      }
      if (!this.simMode) this.enterSim()
      try {
        await this.applyStrategy(sid)
        this.toast = `策略「${st.name || '未命名'}」已加载到仿真模式，可实时对比`
      } catch (e) {
        this.toast = '策略加载失败：' + (e.message || e)
      }
    },
    // 请求在命令行输入策略名称后保存（仿真模式「保存策略」按钮）
    requestSaveStrategy() {
      this.pendingSaveStrategy = true
      this.toast = '请在下方命令行输入策略名称后回车保存'
    },
    // 顶栏「重置视图」按钮 -> SceneViewer watch 该计数 -> scene.resetView()
    resetView() { this.viewResetNonce++ },
    // 切换仿真场景（四大控排）；非钢铁场景当前仅占位（模型建设中）
    setScenario(id) {
      if (id === this.scenario) return
      this.scenario = id
      if (id !== 'steel') this.toast = '该控排场景模型建设中，当前仅「钢铁」可用'
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
      const next = { ...this.dataSources[idx], ...patch, id }
      this.dataSources[idx] = next
      if (this.activeDataSourceId === id) this.dataSource = next
      this._saveDataSource()
      this._connectFeed()
    },
    removeDataSource(id) {
      if (id === 'sim') { this.toast = '内置模拟数据源不可删除'; return }
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
        this.dataSources = [{ id: 'sim', type: 'sim', url: '', interval: 1000, name: '内置模拟数据', enabled: true, mapping: {} }]
      }
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
      if (!us || !us.text) { this.toast = '请先输入策略文本'; return }
      this.parsing = true
      try {
        const parsed = await api.parse(us.text, this.model)
        us.parsed = parsed
        this.parsed = parsed
        this.parsedText = us.text
      } finally { this.parsing = false }
      if (!us.parsed || !us.parsed.ops.length) { this.toast = '策略解析无有效操作'; return }
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
          this._simLog('strategy', `${uname} · 工序策略`, (us.text || '').slice(0, 60), `us_${unitId}`)
        }
        this.sceneRev++
      } finally { this.busy = false }
      this.toast = '策略仿真测试完成，可查看对比结果。'
    },
    // 保存策略并绑定到工序
    async saveUnitStrategy(unitId, name) {
      const us = this.unitStrategies[unitId]
      if (!us || !us.parsed || !us.parsed.ops.length) { this.toast = '暂无有效的策略可保存'; return }
      const sname = name || (us.text ? us.text.slice(0, 30) : '未命名策略')
      await api.createStrategy(sname, '', us.text, us.parsed.ops)
      await this.loadStrategies()
      this.unitStrategies[unitId].scenarioName = sname
      this.toast = '策略已保存并绑定到当前工序'
    },
    // 运行所有已启用的工序策略
    async runAllEnabledStrategies() {
      const enabled = Object.entries(this.unitStrategies).filter(([, v]) => v.enabled && v.parsed)
      if (!enabled.length) { this.toast = '没有已启用的策略可运行'; return }
      this.busy = true
      try {
        const allOps = enabled.flatMap(([, v]) => v.parsed ? v.parsed.ops : [])
        const r = await api.simulate(this._applyDeviceOpParams(this.model), allOps, this.factors)
        this.strategy = r.strategy
        this.delta = r.delta
        if (this.simMode) {
          this.simOps = JSON.parse(JSON.stringify(allOps || []))
          this.simCurrent = r.strategy ? JSON.parse(JSON.stringify(r.strategy)) : null
          this._simLog('strategy', '运行全部策略', `已启用 ${enabled.length} 个工序策略`, 'all')
        }
        this.sceneRev++
      } finally { this.busy = false; }
      this.toast = `已运行 ${enabled.length} 个工序策略`
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
        this.scheme = buildScheme(route)
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
    },
    exitEdit() {
      this.compileSchemeToModel()
      this.autoLayout()
      this.refresh()
      this.scheme.activeGroupId = null   // 退出编排后 3D 孪生回到顶层场景
      this.editMode = false
      this.toast = '已应用编排方案，刷新孪生视图'
      this._saveScheme()   // 持久化编排结果，刷新后保持最后一次编排状态
      // sceneRev 的触发由 SceneViewer 的 editMode watch 统一管理，
      // 确保 DOM 可见 + resize 完成后再 rebuildScene，避免 canvas 0x0 导致相机投影矩阵 NaN
    },

    loadTemplate(route) {
      this._histCapture('tmpl_' + uid('h'))
      this.processRoute = route
      this.scheme = buildScheme(route)
      // 保证模板方案的 group 容器字段齐全（buildScheme 返回的 groups/activeGroupId）
      if (!this.scheme.groups) this.scheme.groups = []
      if (this.scheme.activeGroupId == null) this.scheme.activeGroupId = null
      this.selectedFlowId = null
      this.selectedGroupId = null
      try { localStorage.setItem('sim.processRoute', route) } catch (e) {}
      this._saveScheme()   // 持久化当前模板方案，刷新后保持
      // 编排模式下载入模板后自动适配视图：新方案分行排布，让画布尽量占满屏幕
      if (this.editMode) this.flowZoomFit()
      this.toast = route === 'short' ? '已载入短流程炼钢示例' : '已载入长流程炼钢示例'
    },
    // 持久化当前编排方案：完成编排（exitEdit）、载入模板、清空画布、调节设备设定值时写入，
    // 使刷新后保持最后一次编排结果，而不是回退到默认流程。
    _saveScheme() {
      if (this.simMode) return   // 仿真模式：一切编辑不持久化
      try {
        localStorage.setItem('sim.scheme', JSON.stringify({
          route: this.processRoute,
          scheme: this.scheme,
        }))
      } catch (e) { /* localStorage 不可用时静默忽略 */ }
    },
    _loadScheme() {
      try {
        const raw = localStorage.getItem('sim.scheme')
        if (!raw) return null
        const d = JSON.parse(raw)
        if (!d || !d.scheme || !Array.isArray(d.scheme.nodes) || d.scheme.nodes.length === 0) return null
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
      const label = route === 'short' ? '钢铁企业 · 短流程' : '钢铁企业 · 长流程'
      this.toast = '已打开项目：' + label
      this.pushCmd('已打开项目：' + label + '，已按全流程重建数字孪生。', 'cmd')
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
    clearScheme() {
      this._histCapture('clear_' + uid('h'))
      this.scheme = { nodes: [], connections: [], devices: [], groups: [], activeGroupId: null }
      this.selectedFlowId = null
      this.selectedGroupId = null
      this._saveScheme()   // 持久化清空结果（空方案刷新后按流程路线重建默认，避免回退到旧方案）
    },
    // 从左栏拖入创建节点（kind: process|device|material）
    addFlowNode(kind, type, x, y) {
      this._clearBrowse()               // 拖入后右侧切到节点属性，而非资源浏览属性
      this.inspectorView = 'auto'
      this._histCapture('add_' + uid('h'))
      let node = null
      if (kind === 'process') {
        // 同类型节点：仅 1 台直接使用类型名，从第 2 台起按序号命名（热风炉、热风炉2…），与 buildScheme 多实例命名一致
        const t = PROCESS_MAP[type]
        const count = this.scheme.nodes.filter((n) => n.kind === 'process' && n.type === type).length + 1
        node = makeProcessNode(type, x, y, count > 1 && t ? `${t.label}${count}` : undefined)
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
      this._histCapture('rmconn_' + uid('h'))
      this.scheme.connections = this.scheme.connections.filter((c) => c.id !== id)
    },
    updatePortMaterial(nodeId, dir, portId, material) {
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
        this.toast = `「${m ? m.name : material}」已在该${dir === 'in' ? '输入' : '输出'}中，同一种类不能重复添加`
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
      const specs = (this.platformConfig && this.platformConfig.process_specs) || {}
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
          // 驱动连线：工辅供给绝对量直接写入同量纲目标参数（如 鼓风量 kNm³/h → 高炉风量 kNm³/h）
          dstUnit.params = { ...(dstUnit.params || {}), [drive.dst]: srcVal }
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

    // ---- 实时数据源（内置模拟 / 自定义 WebSocket / HTTP 轮询，支持多源并存）----
    _startFeed() { this._connectFeed() },
    _connectFeed() {
      // 关闭旧连接（各数据源的 WebSocket 或 HTTP 轮询定时器）
      for (const c of this._conns || []) { try { c.close && c.close() } catch (e) {} }
      this._conns = []
      this.sourceStatus = {}
      // 仅连接启用的数据源；若全部停用/为空，则保底回落到内置模拟源
      let sources = (this.dataSources || []).filter((s) => s.enabled !== false)
      if (!sources.length) {
        const sim = { id: 'sim', type: 'sim', url: '', interval: 1000, name: '内置模拟数据', enabled: true, mapping: {} }
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
    // 建立单个数据源连接（ws：内置模拟/自定义 WebSocket；http：按 interval 轮询 JSON）
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
      // WebSocket：内置模拟（默认 /api/ws/feed）或自定义 url
      const url = ds.type === 'ws' && ds.url ? ds.url : undefined
      const ws = openFeed(onMsg, onStatus, url)
      return { ws, close: () => { try { ws.close() } catch (e) {} } }
    },
    // 遥测消息落地：应用该数据源的「字段对齐映射」把外部字段名翻译为场景内传感器/设备 id
    _onFeedMsg(ds, msg) {
      if (!msg) return
      const src = msg.type === 'telemetry' ? msg : msg
      if (!src || !src.devices) return
      this.live = src
      const now = Date.now() / 1000
      const mapping = (ds && ds.mapping) || {}
      // 记录该数据源最近一次收到的外部字段 id（供「连接」面板做字段对齐）
      if (ds) {
        const sid = ds.id || 'sim'
        const fields = src.devices.map((d) => d.id)
        this.lastFields = { ...this.lastFields, [sid]: Array.from(new Set(fields)) }
      }
      for (const d of src.devices) {
        // 字段对齐：若 mapping 配置了「外部字段 -> 内部传感器 id」，读数落入内部传感器；
        // 未配置的字段沿用自身 id（内置模拟源字段本身就是内部 id，天然对齐）
        const internalId = mapping[d.id] || d.id
        this.deviceLive[internalId] = d.reading
        const buf = this.deviceHistory[internalId] || (this.deviceHistory[internalId] = [])
        buf.push({ t: now, v: d.reading })
        if (buf.length > 600) buf.splice(0, buf.length - 600)
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
          if (buf.length > 600) buf.splice(0, buf.length - 600)
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
            if (next === 'open') this.notify('success', '实时链路已恢复', '实时数据链路已重新连接，监测数据持续更新。')
            else if (next === 'error') this.notify('error', '实时链路异常', '实时数据链路异常，请检查数据源配置。')
            else if (next === 'closed') this.notify('warn', '实时链路已断开', '实时数据链路已断开，仿真将基于最近一次数据继续运行。')
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
