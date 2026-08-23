<template>
  <div class="app" :class="{ 'left-collapsed': !store.leftOpen || store.viewModeOn, 'right-collapsed': !store.rightOpen || store.viewModeOn, 'bottom-collapsed': !store.bottomOpen || store.viewModeOn, 'sim-dark': store.simMode, 'view-immersive': store.viewModeOn }"
       :style="{ '--cmd-h': (store.bottomOpen && !store.viewModeOn) ? cmdH + 'px' : '0px', '--lw': (store.leftOpen && !store.viewModeOn) ? lw + 'px' : '0px', '--rw': (store.rightOpen && !store.viewModeOn) ? rw + 'px' : '0px' }">
    <TopBar :menus="menus" ref="topBarRef" @export="onExport" @help="openPromo" />

    <!-- 最左侧活动栏（VS Code 式）：资源管理器 / 搜索 / 场景 / 连接 -->
    <ActivityBar />
    <!-- 左侧栏：园区资产（工艺 / 设备 / 原料 / 策略）；非数字孪生视图沉浸模式隐藏 -->
    <LeftSidebar v-show="!store.viewModeOn" @rsz="startLeftResize" />

    <!-- 中间：仿真数字孪生（仿真态） / 流程编排画布（编辑态） / 传感器数据视图 / 碳市场视图 / 碳排核算视图 / 能流分析视图 / 能碳一体机管理 -->
    <!-- SceneViewer 始终挂载，不销毁 WebGL 上下文，大幅提升切换速度并避免重建空白 -->
    <main class="stage">
      <SceneViewer v-show="!store.editMode && !store.dataViewOn && !store.carbonMarketOn && !store.carbonCalcOn && !store.energyFlowOn && !store.boxManageOn" />
      <DataView v-if="store.dataViewOn && !store.editMode" ref="dataViewRef" />
      <CarbonMarketView v-if="store.carbonMarketOn && !store.editMode" ref="marketViewRef" />
      <CarbonCalcView v-if="store.carbonCalcOn && !store.editMode" />
      <EnergyFlowView v-if="store.energyFlowOn && !store.editMode" />
      <CarbonBoxView v-if="store.boxManageOn && !store.editMode" ref="boxViewRef" />
      <FlowEditor v-if="store.editMode" />
    </main>

    <RibbonToolbar :actions="ribbonActions" />

    <!-- 右侧栏：上下文检视器；非数字孪生视图沉浸模式隐藏 -->
    <RightInspector v-show="!store.viewModeOn" @rsz="startRightResize" />

    <!-- 下侧栏：命令控制台 + 状态条；非数字孪生视图沉浸模式隐藏 -->
    <CommandConsole v-show="!store.viewModeOn" :actions="twinActions" :resizing="resizing" :start-resize="startResize" ref="consoleRef" />

    <StatusBar v-show="!store.viewModeOn" />

    <DataSourceDialog v-if="showDataSource" @close="showDataSource = false" />
    <SystemSettingsDialog v-if="showSettings" @close="showSettings = false" />
    <TechDocs v-if="showTechDocs" @close="showTechDocs = false" />
    <UserManual v-if="showManual" @close="showManual = false" />
    <PromoManual v-if="showPromo" @close="showPromo = false" />
    <AboutDialog v-if="showAbout" @close="showAbout = false" />
    <TftAnalysisDialog v-if="showTftAnalysis" @close="showTftAnalysis = false" />
    <ContextMenu />
    <SensitivityDialog />

    <!-- 欢迎页：进入前覆盖主界面，选择项目后进入数字孪生 -->
    <WelcomeScreen v-if="!store.entered" @open="onOpenProject" />
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
import WelcomeScreen from './components/WelcomeScreen.vue'
import DataView from './components/DataView.vue'
import CarbonMarketView from './components/CarbonMarketView.vue'
import CarbonCalcView from './components/CarbonCalcView.vue'
import EnergyFlowView from './components/EnergyFlowView.vue'
import CarbonBoxView from './components/CarbonBoxView.vue'
import FlowEditor from './components/FlowEditor.vue'
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
function dataRefresh() { if (dataViewRef.value && dataViewRef.value.refresh) dataViewRef.value.refresh() }
// CEA 行情视图：刷新行情（CarbonMarketView 暴露的 loadAll）
function marketRefresh() { if (marketViewRef.value && marketViewRef.value.loadAll) marketViewRef.value.loadAll() }
// 能碳一体机视图：刷新概览 / 设备 / 实时数据（CarbonBoxView 暴露的 refreshAll）
function boxRefresh() { if (boxViewRef.value && boxViewRef.value.refreshAll) boxViewRef.value.refreshAll() }
// CEA 行情视图：切换品种（CEA / CCER）与预测叠加开关（CarbonMarketView 暴露）
const marketSwitch = (v) => { if (marketViewRef.value) marketViewRef.value.switchInstrument(v) }
const marketForecast = () => { if (marketViewRef.value) marketViewRef.value.toggleForecast() }
// 状态以函数形式传入工具栏，避免普通对象内的 computed 不自动解包；函数在工具栏渲染时求值并建立响应式依赖
const marketInstrument = () => marketViewRef.value?.instrument || 'cea'
const marketForecastOn = () => !!(marketViewRef.value?.forecastOn)
// 能碳一体机视图：切换页签（CarbonBoxView 暴露的 switchTab）与当前页签
const boxSwitchTab = (id) => { if (boxViewRef.value) boxViewRef.value.switchTab(id) }
const boxTabOn = () => boxViewRef.value?.tab || 'overview'

// 供命令窗口调用的孪生控制动作
const twinActions = { onSimToggle, onResetView, onOverview, togglePatrol, focusSel, onToggleEdit }
// 供工具条调用的动作
const ribbonActions = { onSimToggle, onToggleEdit, toggleAuto, togglePatrol, onResetView, autoLayoutScheme, flowZoomBtn, flowFit, loadExample, clearScheme, closeView, dataRefresh, marketRefresh, boxRefresh, marketSwitch, marketForecast, marketInstrument, marketForecastOn, boxSwitchTab, boxTabOn }

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
    { label: '高炉数值分析', accel: 'Alt+T', act: () => {
      if (store.simMode) showTftAnalysis.value = true
      else store.toast = '高炉数值分析仅限仿真模式使用：请先开启仿真模式'
    } },
    { label: '参数优化', act: () => pushCmd('参数优化：切换至「数据」工具条 → 策略生成，使用自然语言描述目标。','guide') },
    { label: '数据校准', act: () => pushCmd('数据校准：在右侧检视器选中设备查看实时/历史读数。','guide') },
  ] },
  { id: 'view', label: '视图', items: [
    { sub: true, label: '数字孪生', items: () => [
      { sub: true, label: '环境', items: () => store.envModes.map(e => ({ id: e.id, label: e.label, checked: e.id === store.envMode, run: () => onEnvChange({ target: { value: e.id } }) })) },
    ] },
    { sep: true },
    { label: '监测数据查看', toggle: () => store.dataViewOn, act: () => store.toggleDataView() },
    { label: 'CEA&CCER行情', toggle: () => store.carbonMarketOn, act: () => store.toggleCarbonMarket() },
    { label: '能碳一体机管理', toggle: () => store.boxManageOn, act: () => store.toggleBoxManage() },
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
})

onMounted(() => {
  store.init()
  store.pushCmd('行业能碳仿真平台已就绪。输入 help 查看命令，或直接点击顶栏与工具条操作。', 'guide')
  store.pushCmd('提示：左侧资产树选工序，中间 3D 点击聚焦，右栏检视器看属性。', 'guide')
})

// 欢迎页选择项目后进入：等待初始化完成，再按所选流程路线打开项目
async function onOpenProject(route) {
  await store.waitReady()
  store.openProject(route)
}
</script>
