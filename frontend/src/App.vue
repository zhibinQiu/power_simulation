<template>
  <div class="app" :class="{ 'left-collapsed': !store.leftOpen, 'right-collapsed': !store.rightOpen, 'bottom-collapsed': !store.bottomOpen, 'sim-dark': store.simMode, 'view-immersive': store.viewModeOn }"
       :style="{ '--cmd-h': store.bottomOpen ? cmdH + 'px' : '0px', '--lw': store.leftOpen ? lw + 'px' : '0px', '--rw': store.rightOpen ? rw + 'px' : '0px' }">
    <TopBar :menus="menus" ref="topBarRef" @export="onExport" @help="openPromo" />

    <!-- 最左侧活动栏（VS Code 式）：资源管理器 / 搜索 / 场景 / 连接 -->
    <ActivityBar />
    <!-- 左侧栏：园区资产（工艺 / 设备 / 原料 / 策略）；非数字孪生视图默认收起，可由顶栏按钮 / 活动栏重新展开 -->
    <LeftSidebar v-show="store.leftOpen" @rsz="startLeftResize" />

    <!-- 中间：仿真数字孪生（仿真态） / 流程编排画布（编辑态） / 传感器数据视图 / 碳市场视图 / 碳排核算视图 / 能流分析视图 / 能碳一体机管理 -->
    <!-- SceneViewer 始终挂载，不销毁 WebGL 上下文，大幅提升切换速度并避免重建空白 -->
    <main class="stage">
      <SceneViewer v-show="!store.editMode && !store.dataViewOn && !store.carbonMarketOn && !store.carbonCalcOn && !store.energyFlowOn && !store.boxManageOn" />
      <DataView v-if="store.dataViewOn && !store.editMode" ref="dataViewRef" />
      <CarbonAssistantView v-if="store.carbonMarketOn && !store.editMode" ref="marketViewRef" />
      <CarbonCalcView v-if="store.carbonCalcOn && !store.editMode" />
      <EnergyFlowView v-if="store.energyFlowOn && !store.editMode" />
      <CarbonBoxView v-if="store.boxManageOn && !store.editMode" ref="boxViewRef" />
      <FlowEditor v-if="store.editMode" />
    </main>

    <!-- 视图名标识栏：仅在能碳一体机管理视图下显示，承载标题与实时云端状态徽章
         （与 TopBar / Ribbon 风格统一，位于中间舞台之上） -->
    <div v-if="store.boxManageOn" class="view-banner">
      <div class="vb-left">
        <span class="vb-logo">◈</span>
        <b class="vb-title">能碳一体机管理</b>
        <span class="vb-chip" :class="store.boxCloudSource === 'live' ? 'ok' : (store.boxCloudSource === 'degraded' ? 'warn' : 'err')">
          <span class="vb-dot" :class="{ on: store.boxCloudSource === 'live' }"></span>
          {{ store.boxCloudSource === 'live' ? '云端在线' : (store.boxCloudSource === 'stale' ? '云端数据过期' : (store.boxCloudSource === 'degraded' ? '云端部分异常' : '云端不可达')) }}
        </span>
      </div>
      <div class="vb-right">
        <span class="vb-hint">云端 {{ store.boxCloudSource === 'live' ? '在线' : (store.boxCloudSource === 'stale' ? '推送中断·旧缓存' : (store.boxCloudSource === 'degraded' ? '部分异常' : '不可达')) }} · 3s 刷新</span>
        <button class="vb-close" @click="closeView" title="关闭能碳一体机管理，返回数字孪生场景">✕ 关闭</button>
      </div>
    </div>

    <RibbonToolbar v-show="!store.boxManageOn" :actions="ribbonActions" />

    <!-- 右侧栏：上下文检视器；非数字孪生视图默认收起，可由顶栏按钮重新展开 -->
    <RightInspector v-show="store.rightOpen" @rsz="startRightResize" />

    <!-- 下侧栏：命令控制台；非数字孪生视图默认收起，可由顶栏按钮重新展开（底部状态栏始终保留） -->
    <CommandConsole v-show="store.bottomOpen" :actions="twinActions" :resizing="resizing" :start-resize="startResize" ref="consoleRef" />

    <StatusBar />

    <DataSourceDialog v-if="showDataSource" @close="showDataSource = false" />
    <SystemSettingsDialog v-if="showSettings" @close="showSettings = false" />
    <TechDocs v-if="showTechDocs" @close="showTechDocs = false" />
    <UserManual v-if="showManual" @close="showManual = false" />
    <PromoManual v-if="showPromo" @close="showPromo = false" />
    <AboutDialog v-if="showAbout" @close="showAbout = false" />
    <TftAnalysisDialog v-if="showTftAnalysis" @close="showTftAnalysis = false" />
    <ContextMenu />
    <SensitivityDialog />
  </div>
</template>

<script setup>
import { ref, onMounted, defineAsyncComponent } from 'vue'
import { useSimStore } from './stores/sim'
import TopBar from './components/TopBar.vue'
import RibbonToolbar from './components/RibbonToolbar.vue'
import CommandConsole from './components/CommandConsole.vue'
import StatusBar from './components/StatusBar.vue'
import LeftSidebar from './components/LeftSidebar.vue'
import ActivityBar from './components/ActivityBar.vue'
import RightInspector from './components/RightInspector.vue'
import SceneViewer from './components/SceneViewer.vue'
import { usePanelSizes } from './composables/usePanelSizes'
import { useGlobalShortcuts } from './composables/useGlobalShortcuts'
import { openAuditDialog } from './stores/scan'

// 对话框类组件按需懒加载：首屏不加载其代码，打开时才请求，降低首包体积与内存占用
const DataSourceDialog = defineAsyncComponent(() => import('./components/DataSourceDialog.vue'))
const SystemSettingsDialog = defineAsyncComponent(() => import('./components/SystemSettingsDialog.vue'))
const TechDocs = defineAsyncComponent(() => import('./components/TechDocs.vue'))
const UserManual = defineAsyncComponent(() => import('./components/UserManual.vue'))
const PromoManual = defineAsyncComponent(() => import('./components/PromoManual.vue'))
const AboutDialog = defineAsyncComponent(() => import('./components/AboutDialog.vue'))
const TftAnalysisDialog = defineAsyncComponent(() => import('./components/TftAnalysisDialog.vue'))
const ContextMenu = defineAsyncComponent(() => import('./components/ContextMenu.vue'))
const SensitivityDialog = defineAsyncComponent(() => import('./components/SensitivityDialog.vue'))

// 视图类组件同样按需懒加载：CarbonBoxView（能碳一体机管理）等体量巨大（数千行），
// 首屏同步打包会让 index 主包高达 600+KB；改为进入对应视图时才加载，首屏只保留
// SceneViewer/LeftSidebar/RightInspector 等数字孪生核心组件，显著降低首屏加载与内存占用。
const DataView = defineAsyncComponent(() => import('./components/DataView.vue'))
const CarbonAssistantView = defineAsyncComponent(() => import('./views/CarbonAssistantView.vue'))
const CarbonCalcView = defineAsyncComponent(() => import('./components/CarbonCalcView.vue'))
const EnergyFlowView = defineAsyncComponent(() => import('./components/EnergyFlowView.vue'))
const CarbonBoxView = defineAsyncComponent(() => import('./components/CarbonBoxView.vue'))
const FlowEditor = defineAsyncComponent(() => import('./components/FlowEditor.vue'))

// 等待视图组件挂载完成：懒加载组件首次打开需异步加载代码，ref 可能延迟可用
function waitViewRef(r, timeout = 6000) {
  if (r.value) return Promise.resolve(true)
  return new Promise((resolve) => {
    const t0 = Date.now()
    const iv = setInterval(() => {
      if (r.value) { clearInterval(iv); resolve(true) }
      else if (Date.now() - t0 > timeout) { clearInterval(iv); resolve(false) }
    }, 80)
  })
}

const store = useSimStore()
const topBarRef = ref(null)
const consoleRef = ref(null)
// 视图组件引用：供各视图工具栏（RibbonToolbar）调用其内部动作（刷新行情 / 刷新数据等）
const dataViewRef = ref(null)
const marketViewRef = ref(null)
const boxViewRef = ref(null)

const showDataSource = ref(false)
const showSettings = ref(false)
const showTechDocs = ref(false)
const showManual = ref(false)
const showPromo = ref(false)
const showAbout = ref(false)
const showTftAnalysis = ref(false)

const { lw, rw, cmdH, resizing, startLeftResize, startRightResize, startResize } = usePanelSizes()

/* ---------------- 动作 ---------------- */
function pushCmd(t, k = 'out') { store.pushCmd(t, k) }
function onRun() {
  const hasStrategies = Object.values(store.unitStrategies).some(s => s.enabled)
  if (hasStrategies) store.runAllEnabledStrategies()
  else store.refresh()
  pushCmd('simulate >> 重新运行仿真，已刷新全厂碳素流、能流与排放。', 'cmd')
}
function onSimToggle() {
  if (store.simMode) {
    store.exitSim()
    pushCmd('已退出仿真模式，数字孪生环境已切换为工业。', 'tip')
  } else {
    store.enterSim()
    pushCmd('已进入仿真模式：所有修改仅预览，退出后自动恢复。仿真模式下可直接输入自然语言指令（如“降低焦比 10%”），由智能体解析并应用（规划中）。', 'guide')
    consoleRef.value && consoleRef.value.focusInput()
  }
}
function onResetParams() { store.refresh(); pushCmd('已重置仿真参数并重新计算。', 'out') }
function onRefresh() { store.resetView(); store.refresh(); pushCmd('已重置视角并同步数据。', 'cmd') }
function onResetView() { store.resetView(); pushCmd('视图 >> 相机视角已重置为园区俯瞰。', 'cmd') }
function toggleAuto() { store.setAutoRotate(!store.autoRotate); pushCmd('自动环视 ' + (store.autoRotate ? '开启' : '关闭') + '。', 'out') }
function togglePatrol() {
  store.togglePatrol()
  pushCmd(store.patrolOn ? '视图 >> 虚拟巡视：机器狗已部署，W/S/A/D 移动、Z/X 原地转向、Shift 加速；建筑与工艺不可穿越。' : '视图 >> 虚拟巡视已结束。', 'cmd')
}
function focusSel(mode) {
  if (!store.selectedUnitId) { pushCmd('未选中工序：请先在左侧资产树或 3D 孪生中点选工序。', 'warn'); return }
  store.viewUnit(store.selectedUnitId, mode)
  const map = { top: '俯视', front: '正视', side: '侧视', focus: '聚焦', overview: '全景' }
  pushCmd(`视图 >> ${map[mode] || mode}（${store.selectedUnitId}）。`, 'cmd')
}
function onOverview() {
  store.viewUnit('__overview__', 'overview')
  pushCmd('视图 >> 已切换到全场景俯瞰视角。', 'cmd')
}
function onAutoLayout() {
  store.autoLayout()
  store.refresh()
  store.sceneRev++
  pushCmd('视图 >> 已重新自动布局工序。', 'cmd')
}
function onToggleEdit() { if (store.editMode) store.exitEdit(); else store.enterEdit(); pushCmd(store.editMode ? '已退出流程编排。' : '进入流程编排：可从左侧「资源管理器」拖拽条目到画布，节点参数在右侧编排属性中调整。', store.editMode ? 'out' : 'guide') }
function ensureEdit() { if (!store.editMode) store.enterEdit() }
function loadExample(route) { ensureEdit(); store.loadTemplate(route); pushCmd(route === 'short' ? '已载入短流程炼钢示例。' : '已载入长流程炼钢示例。', 'out') }
function clearScheme() { ensureEdit(); store.clearScheme(); pushCmd('已清空编排画布。', 'out') }
function autoLayoutScheme() { ensureEdit(); store.autoLayoutScheme(); pushCmd('已自动布局编排节点：主工艺横向排列（一行 3-4 个），工辅排在各自主工艺下方，互不重叠。', 'out') }
function addGroupBtn() { ensureEdit(); const id = store.addFlowGroup(); pushCmd(id ? '已新建小组，可将设备拖入其中。' : '新建小组失败。', 'out') }
function duplicateGroupBtn() { ensureEdit(); const id = store.duplicateFlowGroup(store.selectedGroupId); if (id) pushCmd('已复制小组。', 'out') }
function flowZoomBtn(f) { store.flowZoom(f) }
function flowFit() { store.flowZoomFit() }
function onEnvChange(e) { store.setEnvMode(e.target.value); pushCmd(`外围景观 → ${store.envModes.find((m) => m.id === store.envMode)?.label || store.envMode}。`, 'cmd') }
// 导出 AI 分析报告：基线数据分析 + 使用的策略 + 策略前后对比，由后端大模型生成 Markdown
function onExport() {
  if (!store.baseline) { pushCmd('暂无仿真数据：请先运行仿真或应用情景后再导出报告。', 'tip'); store.toast = '请先运行仿真再导出报告'; return }
  const sel = store.selectedStrategy
  store.openReportPanel({
    baseline: store.baseline,
    strategy: store.strategy,
    strategy_name: sel?.name || (store.parsed ? '自定义策略' : ''),
    strategy_text: store.parsedText || sel?.raw_text || sel?.description || '',
    ops: store.parsed?.ops || sel?.ops || [],
    understood: store.parsed?.understood || [],
    scenario: store.scenarios.find((s) => s.id === store.scenario)?.label || store.scenario,
  })
  pushCmd('已打开右侧报告面板：请配置标题、引擎与分析深度后点击「生成报告」。', 'guide')
}
function openPromo() { showPromo.value = true }
function onAbout() { showAbout.value = true }

// 关闭当前视图，返回数字孪生场景（供各视图工具栏「返回数字孪生」按钮调用）
function closeView() {
  if (store.dataViewOn) store.toggleDataView()
  else if (store.carbonMarketOn) store.toggleCarbonMarket()
  else if (store.carbonCalcOn) store.toggleCarbonCalc()
  else if (store.energyFlowOn) store.toggleEnergyFlow()
  else if (store.boxManageOn) store.toggleBoxManage()
  pushCmd('已返回数字孪生场景。', 'out')
}
// 监测数据视图：重新拉取历史数据（DataView 暴露的 refresh）
async function dataRefresh() { await waitViewRef(dataViewRef); if (dataViewRef.value?.refresh) dataViewRef.value.refresh() }
// 碳资产管理视图：刷新行情（CarbonAssistantView 暴露的 loadAll）
async function marketRefresh() { await waitViewRef(marketViewRef); if (marketViewRef.value?.loadAll) marketViewRef.value.loadAll() }
// 碳资产管理视图：切换品种（CEA / CCER）与预测叠加开关（CarbonAssistantView 暴露）
const marketSwitch = async (v) => { await waitViewRef(marketViewRef); if (marketViewRef.value) marketViewRef.value.switchInstrument(v) }
const marketForecast = async () => { await waitViewRef(marketViewRef); if (marketViewRef.value) marketViewRef.value.toggleForecast() }
// 碳资产管理视图：打开报告生成侧边栏（CarbonAssistantView 暴露的 openReport）
const carbonReport = async () => { await waitViewRef(marketViewRef); if (marketViewRef.value?.openReport) marketViewRef.value.openReport() }
// 状态以函数形式传入工具栏，避免普通对象内的 computed 不自动解包；函数在工具栏渲染时求值并建立响应式依赖
const marketInstrument = () => marketViewRef.value?.instrument || 'cea'
const marketForecastOn = () => !!(marketViewRef.value?.forecastOn)
// 碳资产管理视图：当前页签（market / ledger），供顶栏「视图」二级菜单勾选与工具栏区分行情/台账功能
const marketTabOn = () => marketViewRef.value?.tab || 'market'
// 顶栏「视图」二级菜单：打开碳资产管理并切换到指定页签（market 行情 / ledger 台账）
const marketSubNav = async (id) => {
  if (!store.carbonMarketOn) store.toggleCarbonMarket()
  await waitViewRef(marketViewRef)
  if (marketViewRef.value) marketViewRef.value.switchTab(id)
  pushCmd(`视图 >> 碳资产管理 >> ${id === 'market' ? 'CEA / CCER 行情' : '企业台账与策略'}。`, 'cmd')
}
// 顶栏「视图」菜单：打开能碳一体机管理（原数据概览/设备管理两页签已合并为一界面）
const boxSubNav = () => {
  if (!store.boxManageOn) store.toggleBoxManage()
  pushCmd('视图 >> 能碳一体机管理。', 'cmd')
}
// 碳资产管理视图：刷新企业台账（CarbonAssistantView 暴露的 refreshLedger，转发到台账面板 loadAll）
const marketLedgerRefresh = async () => { await waitViewRef(marketViewRef); if (marketViewRef.value?.refreshLedger) marketViewRef.value.refreshLedger() }

// 供命令窗口调用的孪生控制动作
const twinActions = { onSimToggle, onResetView, onOverview, togglePatrol, focusSel, onToggleEdit }
// 供工具条调用的动作
const ribbonActions = { onSimToggle, onToggleEdit, toggleAuto, togglePatrol, onResetView, autoLayoutScheme, flowZoomBtn, flowFit, loadExample, clearScheme, closeView, dataRefresh, marketRefresh, marketSwitch, marketForecast, marketLedgerRefresh, carbonReport, marketInstrument, marketForecastOn, marketTabOn }

/* ---------------- 经典菜单条（文件 / 仿真 / 视图 / 编辑 / 工具 / 帮助） ---------------- */
const menus = [
  { id: 'file', label: '文件', items: [
    { label: '新建方案', act: () => pushCmd('新建方案：已清空当前编排（原型占位）。','out') },
    { label: '打开方案…', act: () => pushCmd('打开方案：请在左侧「策略」中载入已存方案（原型占位）。','guide') },
    { sep: true },
    { label: '保存方案', accel: 'Ctrl+S', act: () => pushCmd('方案已保存至本地工作区。','out') },
    { label: '连接数据源…', act: () => { showDataSource.value = true } },
    { label: '导出分析报告', act: onExport },
    { sep: true },
    { label: '设置…', act: () => { showSettings.value = true } },
  ] },
  { id: 'sim', label: '仿真', items: [
    { label: '运行仿真', accel: 'Ctrl+Enter', act: onRun },
    { sep: true },
    { label: '重置仿真参数', act: onResetParams },
    { label: '应用当前情景', act: () => { store.refresh(); pushCmd('已应用当前仿真情景并重新计算。','cmd') } },
    { sep: true },
    { label: '参数优化', act: () => pushCmd('参数优化：切换至「数据」工具条 → 策略生成，使用自然语言描述目标。','guide') },
    { label: '数据校准', act: () => pushCmd('数据校准：在右侧检视器选中设备查看实时/历史读数。','guide') },
  ] },
  { id: 'view', label: '视图', items: [
    { sub: true, label: '数字孪生', items: () => [
      { sub: true, label: '环境', items: () => store.envModes.map(e => ({ id: e.id, label: e.label, checked: e.id === store.envMode, run: () => onEnvChange({ target: { value: e.id } }) })) },
    ] },
    { sub: true, label: '碳资产管理', items: () => [
      { label: 'CEA / CCER 行情', checked: store.carbonMarketOn && marketTabOn() === 'market', run: () => marketSubNav('market') },
      { label: '企业台账与策略', checked: store.carbonMarketOn && marketTabOn() === 'ledger', run: () => marketSubNav('ledger') },
    ] },
    { label: '能碳一体机管理', toggle: () => store.boxManageOn, act: () => boxSubNav() },
  ] },
  { id: 'data', label: '数据', items: [
    { label: '监测数据查看', toggle: () => store.dataViewOn, act: () => store.toggleDataView() },
  ] },
  { id: 'edit', label: '编辑', items: [
    { label: store.editMode ? '完成编排' : '进入流程编排', act: onToggleEdit },
    { sep: true },
    { label: '撤销', accel: 'Ctrl+Z', disabled: () => !store.canUndo, act: () => store.undo() },
    { label: '重做', accel: 'Ctrl+Y', disabled: () => !store.canRedo, act: () => store.redo() },
    { sep: true, hide: () => !store.editMode },
    { label: '放大画布', hide: () => !store.editMode, act: () => flowZoomBtn(1.1) },
    { label: '缩小画布', hide: () => !store.editMode, act: () => flowZoomBtn(0.9) },
    { label: '适配视图', hide: () => !store.editMode, act: () => flowFit() },
    { label: '自动布局', hide: () => !store.editMode, act: () => autoLayoutScheme() },
    { sep: true, hide: () => !store.editMode },
    { label: '新建小组', hide: () => !store.editMode, act: () => addGroupBtn() },
    { label: '复制小组', hide: () => !store.editMode, disabled: () => !store.selectedGroupId, act: () => duplicateGroupBtn() },
    { label: '删除小组', hide: () => !store.editMode, disabled: () => !store.selectedGroupId, act: () => store.removeFlowGroup(store.selectedGroupId) },
    { sep: true, hide: () => !store.editMode },
    { label: '长流程示例', hide: () => !store.editMode, act: () => loadExample('long') },
    { label: '短流程示例', hide: () => !store.editMode, act: () => loadExample('short') },
    { label: '清空画布', hide: () => !store.editMode, act: () => clearScheme() },
  ] },
  { id: 'tools', label: '工具', items: [
    { sub: true, label: '低碳', items: () => [
      { label: '碳素流守恒审计', run: () => openAuditDialog() },
      { label: '全景碳核查', run: () => store.toggleCarbonCalc() },
    ] },
    { sub: true, label: '能源', items: () => [
      { label: '能流分析', run: () => store.toggleEnergyFlow() },
    ] },
  ] },
  { id: 'help', label: '帮助', items: [
    { label: '宣传手册', accel: 'F1', act: () => { showPromo.value = true } },
    { label: '使用手册', act: () => { showManual.value = true } },
    { label: '技术文档', act: () => { showTechDocs.value = true } },
    { label: '快捷键', act: () => pushCmd('快捷键：Ctrl+Enter 运行 · Ctrl+Z 撤销 · Ctrl+Y 重做 · F 聚焦选中工序 · 右键节点/资源打开上下文菜单（选中/参数扫描/重命名/复制/删除）· 编排态 F2 重命名、Ctrl+D 复制节点、Del 删除。','out') },
    { sep: true },
    { label: '关于本平台', act: onAbout },
  ] },
]

useGlobalShortcuts({
  store, onRun, focusSel,
  onMenuEsc: () => topBarRef.value && topBarRef.value.closeMenus(),
  onTftAnalysis: () => {
    if (store.simMode) showTftAnalysis.value = true
    else store.toast = '高炉数值分析仅限仿真模式使用：请先开启仿真模式'
  },
})

onMounted(async () => {
  store.init()
  store.pushCmd('工业能碳智控平台已就绪。输入 help 查看命令，或直接点击顶栏与工具条操作。', 'guide')
  store.pushCmd('提示：左侧资产树选工序，中间 3D 点击聚焦，右栏检视器看属性。', 'guide')
  // 无宣传页：初始化完成后直接进入主界面（保留已保存方案，不重建覆盖）
  await store.waitReady()
  if (!store.entered) {
    store.entered = true
    store.refresh()
    store.sceneRev++
  }
  // 首屏渲染完成且浏览器空闲后，预取常用视图 chunk：兼顾首屏轻量与后续视图切换的响应速度
  // （defineAsyncComponent 的 loader 拉取模块后即被缓存，再次打开无需重新请求）
  const idle = window.requestIdleCallback || ((cb) => setTimeout(cb, 4000))
  idle(() => {
    import('./components/CarbonBoxView.vue')
    import('./views/CarbonAssistantView.vue')
    import('./components/DataView.vue')
  }, { timeout: 8000 })
})
</script>
