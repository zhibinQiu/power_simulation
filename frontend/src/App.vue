<template>
  <div class="app" :class="{ 'left-collapsed': !store.leftOpen, 'right-collapsed': !store.rightOpen, 'bottom-collapsed': !store.bottomOpen, 'sim-dark': store.simMode || themeMode === 'dark', 'view-immersive': store.viewModeOn, 'fullscreen-on': store.fullscreenOn }"
       :data-accent="accent"
       :style="{ '--cmd-h': store.bottomOpen ? cmdH + 'px' : '0px', '--lw': store.leftOpen ? lw + 'px' : '0px', '--rw': store.rightOpen ? rw + 'px' : '0px' }">
    <TopBar :menus="menus" ref="topBarRef" @export="onExport" @help="openDocsSite('promo')" @toggle-agent="toggleAgent" />

    <!-- 最左侧活动栏（VS Code 式）：资源管理器 / 搜索 / 场景 / 连接 -->
    <ActivityBar />
    <!-- 左侧栏：园区资产（工艺 / 设备 / 原料 / 策略）；收起时由 .left-collapsed 置列宽 0 + 裁切，实现平滑滑出 -->
    <LeftSidebar @rsz="startLeftResize" />

    <!-- 中间：仿真数字孪生（仿真态） / 流程编排画布（编辑态） / 传感器数据视图 / 碳市场视图 / 碳排核算视图 / 能流分析视图 / 能碳一体机管理 / HMI人机交互屏 -->
    <!-- SceneViewer 首次进入数字孪生视图时懒加载（three.js ~500KB 不进首屏关键路径），
         加载后保持挂载，不销毁 WebGL 上下文，切换速度与原先一致 -->
    <main class="stage">
      <SceneViewer v-if="sceneMounted" v-show="!store.editMode && !store.dataViewOn && !store.carbonMarketOn && !store.carbonCalcOn && !store.energyFlowOn && !store.boxManageOn && !store.overviewOn" />
      <DataView v-if="store.dataViewOn && !store.editMode" ref="dataViewRef" />
      <CarbonAssistantView v-if="store.carbonMarketOn && !store.editMode" ref="marketViewRef" />
      <CarbonCalcView v-if="store.carbonCalcOn && !store.editMode" />
      <EnergyFlowView v-if="store.energyFlowOn && !store.editMode" />
      <CarbonBoxView v-if="store.boxManageOn && !store.editMode" ref="boxViewRef" />
      <DataOverview v-if="store.overviewOn && !store.editMode" />
      <FlowEditor v-if="store.editMode" />
    </main>

    <!-- 视图名标识栏：在能碳一体机管理 / 碳资产管理视图下显示，承载标题（与 TopBar / Ribbon 风格统一，位于中间舞台之上） -->
    <div v-if="store.boxManageOn || store.carbonMarketOn" class="view-banner">
      <div class="vb-left">
        <b class="vb-title">{{ store.boxManageOn ? t('能碳一体机管理') : t('碳资产管理') }}</b>
      </div>
      <div class="vb-right">
        <span v-if="store.carbonMarketOn" class="vb-market-tabs">
          <button class="vb-tab" :class="{ on: marketTabOn() === 'market' }" @click="marketSubNav('market')">CEA / CCER 行情</button>
          <button class="vb-tab" :class="{ on: marketTabOn() === 'ledger' }" @click="marketSubNav('ledger')">{{ t('企业台账与策略') }}</button>
        </span>
        <button v-if="store.carbonMarketOn && marketTabOn() === 'market'" class="vb-close" @click="marketRefresh">↻ {{ t('刷新行情') }}</button>
        <button v-if="store.carbonMarketOn && marketTabOn() === 'ledger'" class="vb-close" @click="marketLedgerRefresh">↻ {{ t('刷新台账') }}</button>
        <button v-if="store.carbonMarketOn" class="vb-close" @click="carbonReport">📄 {{ t('生成报告') }}</button>
        <button class="vb-close" @click="closeView" :title="t('关闭当前视图，返回数字孪生场景')">✕ {{ t('关闭') }}</button>
      </div>
    </div>

    <RibbonToolbar v-show="!store.boxManageOn && !store.carbonMarketOn" :actions="ribbonActions" />

    <!-- 右侧栏：上下文检视器；收起时由 .right-collapsed 置列宽 0 + 裁切，实现平滑滑出 -->
    <RightInspector @rsz="startRightResize" />

    <!-- 下侧栏：命令控制台；非数字孪生视图默认收起，可由顶栏按钮重新展开（底部状态栏始终保留） -->
    <CommandConsole :actions="twinActions" :resizing="resizing" :start-resize="startResize" ref="consoleRef" />

    <StatusBar />

    <DataSourceDialog v-if="showDataSource" @close="showDataSource = false" />
    <SystemSettingsDialog v-if="showSettings" @close="showSettings = false" />
    <AboutDialog v-if="store.aboutDialog" />
    <TftAnalysisDialog v-if="showTftAnalysis" @close="showTftAnalysis = false" />
    <!-- AI 管理对话框：知识库 / 智能体 / 技能 / 本体（语义层） -->
    <KnowledgeManageDialog v-if="showKnowledgeManage" @close="showKnowledgeManage = false" />
    <AgentManageDialog v-if="showAgentManage" @close="showAgentManage = false" />
    <SkillManageDialog v-if="showSkillManage" @close="showSkillManage = false" />
    <OntologyManageDialog v-if="showOntologyManage" @close="showOntologyManage = false" />
    <ContextMenu />
    <ConservationAuditDialog />
    <!-- 全局即时反馈层：类型化 Toast（视觉+听觉）与任务进度条（进度可视化） -->
    <ToastLayer />
    <TaskProgress />
    <!-- 全局统一确认弹窗 -->
    <ConfirmDialog />
  </div>
</template>

<script setup>
import { ref, computed, onMounted, defineAsyncComponent } from 'vue'
import { useSimStore } from './stores/sim'
import { t } from './i18n'
import { accent, themeMode } from './theme'
import { lazyDialog } from './utils/asyncComp'
import ToastLayer from './components/ToastLayer.vue'
import TaskProgress from './components/TaskProgress.vue'
import ConfirmDialog from './components/ConfirmDialog.vue'
import TopBar from './components/TopBar.vue'
import RibbonToolbar from './components/RibbonToolbar.vue'
import CommandConsole from './components/CommandConsole.vue'
import StatusBar from './components/StatusBar.vue'
import LeftSidebar from './components/LeftSidebar.vue'
import ActivityBar from './components/ActivityBar.vue'
import RightInspector from './components/RightInspector.vue'
import { usePanelSizes } from './composables/usePanelSizes'
import { useGlobalShortcuts } from './composables/useGlobalShortcuts'
import { openAuditDialog } from './stores/audit'

// 对话框类组件按需懒加载：首屏不加载其代码，打开时才请求，降低首包体积与内存占用
const DataSourceDialog = defineAsyncComponent(() => import('./components/DataSourceDialog.vue'))
const SystemSettingsDialog = defineAsyncComponent(() => import('./components/SystemSettingsDialog.vue'))
const AboutDialog = defineAsyncComponent(() => import('./components/AboutDialog.vue'))
const KnowledgeManageDialog = defineAsyncComponent(() => import('./components/KnowledgeBaseDialog.vue'))
const AgentManageDialog = defineAsyncComponent(() => import('./components/AgentManageDialog.vue'))
const SkillManageDialog = defineAsyncComponent(() => import('./components/SkillManageDialog.vue'))
const OntologyManageDialog = defineAsyncComponent(() => import('./components/OntologyManageDialog.vue'))
// 高炉数值仿真弹窗：lazyDialog 提供加载占位/失败重试/错误提示，避免偶发加载失败时打不开
const TftAnalysisDialog = lazyDialog(() => import('./components/TftAnalysisDialog.vue'))
const ContextMenu = defineAsyncComponent(() => import('./components/ContextMenu.vue'))
const ConservationAuditDialog = defineAsyncComponent(() => import('./components/ConservationAuditDialog.vue'))

// 视图类组件同样按需懒加载：CarbonBoxView（能碳一体机管理）等体量巨大（数千行），
// 首屏同步打包会让 index 主包高达 600+KB；改为进入对应视图时才加载，首屏只保留
// SceneViewer/LeftSidebar/RightInspector 等数字孪生核心组件，显著降低首屏加载与内存占用。
// 3D 数字孪生场景：three.js（~500KB）+ 场景构建代码体积巨大，改为异步加载。
// 首次进入数字孪生视图（默认即此视图）时才开始加载，加载后保持挂载，
// 不销毁 WebGL 上下文（切换视图速度与原先一致）；首屏只渲染 UI 框架，不阻塞。
const SceneViewer = defineAsyncComponent(() => import('./components/SceneViewer.vue'))
const DataView = defineAsyncComponent(() => import('./components/DataView.vue'))
const CarbonAssistantView = defineAsyncComponent(() => import('./views/CarbonAssistantView.vue'))
const CarbonCalcView = defineAsyncComponent(() => import('./components/CarbonCalcView.vue'))
const EnergyFlowView = defineAsyncComponent(() => import('./components/EnergyFlowView.vue'))
const CarbonBoxView = defineAsyncComponent(() => import('./components/CarbonBoxView.vue'))
const DataOverview = defineAsyncComponent(() => import('./components/DataOverview.vue'))
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
// 3D 场景挂载标记：首次加载后保持 true，避免卸载 WebGL 上下文（切换视图速度不受影响）
const sceneMounted = ref(false)
const topBarRef = ref(null)
const consoleRef = ref(null)
// 视图组件引用：供各视图工具栏（RibbonToolbar）调用其内部动作（刷新行情 / 刷新数据等）
const dataViewRef = ref(null)
const marketViewRef = ref(null)
const boxViewRef = ref(null)

const showDataSource = ref(false)
const showSettings = ref(false)
const showTftAnalysis = ref(false)
const showKnowledgeManage = ref(false)
const showAgentManage = ref(false)
const showSkillManage = ref(false)
const showOntologyManage = ref(false)

const { lw, rw, cmdH, resizing, startLeftResize, startRightResize, startResize } = usePanelSizes()

/* ---------------- 动作 ---------------- */
function pushCmd(t, k = 'out') { store.pushCmd(t, k) }
function onRun() {
  const hasStrategies = Object.values(store.unitStrategies).some(s => s.enabled)
  if (hasStrategies) store.runAllEnabledStrategies()
  else store.refresh()
  pushCmd(t('simulate >> 重新运行仿真，已刷新全厂碳素流、能流与排放。'), 'out')
}
function onSimToggle() {
  if (store.simMode) store.exitSim()
  else {
    store.enterSim()
    consoleRef.value && consoleRef.value.focusInput()
  }
}
function onResetParams() { store.refresh(); pushCmd(t('已重置仿真参数并重新计算。'), 'out') }
function onRefresh() { store.resetView(); store.refresh(); pushCmd(t('已重置视角并同步数据。'), 'out') }
function onResetView() { store.resetView(); pushCmd(t('视图 >> 相机视角已重置为园区俯瞰。'), 'out') }
function toggleAuto() { store.setAutoRotate(!store.autoRotate); pushCmd(t('自动环视 ') + (store.autoRotate ? t('开启') : t('关闭')) + t('。'), 'out') }
function focusSel(mode) {
  if (!store.selectedUnitId) { pushCmd(t('未选中工序：请先在左侧资产树或 3D 孪生中点选工序。'), 'warn'); return }
  store.viewUnit(store.selectedUnitId, mode)
  const map = { top: t('俯视'), front: t('正视'), side: t('侧视'), focus: t('聚焦'), overview: t('全景') }
  pushCmd(t('视图 >> ') + (map[mode] || mode) + t('（') + store.selectedUnitId + t('）。'), 'out')
}
function onOverview() {
  store.viewUnit('__overview__', 'overview')
  pushCmd(t('视图 >> 已切换到全场景俯瞰视角。'), 'out')
}
function onAutoLayout() {
  store.autoLayout()
  store.refresh()
  store.sceneRev++
  pushCmd(t('视图 >> 已重新自动布局工序。'), 'out')
}
function onToggleEdit() { if (store.editMode) store.exitEdit(); else store.enterEdit(); pushCmd(store.editMode ? t('已退出流程编排。') : t('进入流程编排：可从左侧「资源管理器」拖拽条目到画布，节点参数在右侧编排属性中调整。'), 'out') }
// 保存编排方案并生效：编辑（参数/设定值/配方/连线等）仅在画布草稿中，点击保存后统一应用并持久化
function saveFlow() { store.saveScheme(); pushCmd(t('已保存编排方案并生效（应用到孪生场景与仿真计算）。'), 'out') }
function ensureEdit() { if (!store.editMode) store.enterEdit() }
function loadExample(route) { ensureEdit(); store.loadTemplate(route); pushCmd(route === 'short' ? t('已载入短流程炼钢模板。') : t('已载入长流程炼钢模板。'), 'out') }
function clearScheme() { ensureEdit(); store.clearScheme(); pushCmd(t('已清空编排画布。'), 'out') }
function autoLayoutScheme() { ensureEdit(); store.autoLayoutScheme(); pushCmd(t('已自动布局：主工艺横向排列，工辅位于其下方。'), 'out') }
function addGroupBtn() { ensureEdit(); const id = store.addFlowGroup(); pushCmd(id ? t('已新建小组，可将设备拖入其中。') : t('新建小组失败。'), 'out') }
function duplicateGroupBtn() { ensureEdit(); const id = store.duplicateFlowGroup(store.selectedGroupId); if (id) pushCmd(t('已复制小组。'), 'out') }
function flowZoomBtn(f) { store.flowZoom(f) }
function flowFit() { store.flowZoomFit() }
function onEnvChange(e) { store.setEnvMode(e.target.value); pushCmd(t('外围景观 → ') + (store.envModes.find((m) => m.id === store.envMode)?.label || store.envMode) + t('。'), 'out') }
// 导出 AI 分析报告：基线数据分析 + 使用的策略 + 策略前后对比，由后端大模型生成 Markdown
function onExport() {
  if (!store.baseline) { pushCmd(t('暂无可导出数据：请先运行仿真或应用情景。'), 'tip'); store.showToast(t('请先运行仿真再导出报告'), 'warn'); return }
  const sel = store.selectedStrategy
  store.openReportPanel({
    baseline: store.baseline,
    strategy: store.strategy,
    strategy_name: sel?.name || (store.parsed ? t('自定义策略') : ''),
    strategy_text: store.parsedText || sel?.raw_text || sel?.description || '',
    ops: store.parsed?.ops || sel?.ops || [],
    understood: store.parsed?.understood || [],
    scenario: store.scenarios.find((s) => s.id === store.scenario)?.label || store.scenario,
  })
  pushCmd(t('已打开右侧报告面板：请配置标题、引擎与分析深度后点击「生成报告」。'), 'out')
}
// 打开独立文档网站（宣传手册 / 使用手册 / 技术文档已脱离平台，作为独立服务跳转）
// 文档站经云端 frp 隧道暴露公网（36.151.146.71:40183），跳转链接固定使用公网地址。
function openDocsSite(page = '') {
  const target = page ? '/#/' + page : '/#/'
  const open = (host) => {
    const port = import.meta.env.DEV ? 5174 : 40183
    window.open(`http://${host}:${port}${target}`, '_blank')
  }
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), 4000)
  fetch('/api/help/site', { signal: ctrl.signal })
    .then((r) => (r.ok ? r.json() : null))
    .then((data) => {
      if (data && data.host) return open(data.host)
      throw new Error('no host')
    })
    .catch(() => {
      // 后端接口不可用时：直接回退公网文档站入口（frp 隧道）
      open('36.151.146.71')
    })
    .finally(() => clearTimeout(timer))
}
function onAbout() { store.openAbout() }

// 关闭当前视图，返回数字孪生场景（供各视图工具栏「返回数字孪生」按钮调用；流程编排态直接完成编排并退出）
function closeView() {
  if (store.editMode) store.exitEdit()
  else if (store.dataViewOn) store.toggleDataView()
  else if (store.carbonMarketOn) store.toggleCarbonMarket()
  else if (store.carbonCalcOn) store.toggleCarbonCalc()
  else if (store.energyFlowOn) store.toggleEnergyFlow()
  else if (store.boxManageOn) store.toggleBoxManage()
  else if (store.overviewOn) store.toggleOverview()
  pushCmd(t('已返回数字孪生场景。'), 'out')
}
// 工况数据分析视图：重新拉取历史数据（DataView 暴露的 refresh）
async function dataRefresh() { await waitViewRef(dataViewRef); if (dataViewRef.value?.refresh) dataViewRef.value.refresh() }
// 工况数据分析视图：AI 分析按钮 —— 打开右侧对应属性面板（时序预测 / 参数优化 / 聚类分析 / 数据拟合）。
// 与左侧资源树点击 AI 模型行为一致（selectStrategy → 右侧 strategyDetail）；参数优化为集中面板（GA/PSO/RL 面板内切换）。
function openAiModel(id) {
  if (id === 'ai::opt') {
    // 参数优化集中面板：已打开某个参数优化算法时保持不跳变，否则默认遗传算法（面板顶部可切换 遗传算法 / 粒子群 / 强化学习）
    const cur = store.selectedStrategyId
    const curOpt = /^ai::(ga|pso|rl)$/.test(String(cur || ''))
    store.selectStrategy(curOpt ? cur : 'ai::ga')
    store.toast = t('已打开参数优化属性面板：可在面板顶部切换 遗传算法 / 粒子群 / 强化学习')
    return
  }
  const cur = store.selectedStrategyId
  store.selectStrategy(cur === id ? cur : id)
  const m = id === 'ai::seq' ? t('时序预测') : id === 'ai::clu' ? t('聚类分析') : id === 'ai::fit' ? t('数据拟合') : t('AI 模型')
  store.toast = t('已打开「') + m + t('」属性面板')
}
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
  pushCmd(t('视图 >> 碳资产管理 >> ') + (id === 'market' ? t('CEA / CCER 行情') : t('企业台账与策略')) + t('。'), 'out')
}
// 顶栏「视图」菜单：打开能碳一体机管理（原数据概览/设备管理两页签已合并为一界面）
const boxSubNav = () => {
  if (!store.boxManageOn) store.toggleBoxManage()
  pushCmd(t('视图 >> 能碳一体机管理。'), 'out')
}
// 碳资产管理视图：刷新企业台账（CarbonAssistantView 暴露的 refreshLedger，转发到台账面板 loadAll）
const marketLedgerRefresh = async () => { await waitViewRef(marketViewRef); if (marketViewRef.value?.refreshLedger) marketViewRef.value.refreshLedger() }
// 工具栏「三维仿真/HMI人机交互屏」切换：中间 3D 场景 ↔ 企业实时运行 HMI 大屏
function toggleOverview() {
  store.toggleOverview()
  pushCmd(store.overviewOn ? t('视图 >> HMI人机交互屏：企业各工艺设备实时运行情况大屏。') : t('视图 >> 已返回三维仿真场景。'), 'out')
}
// 工具栏「本析智擎」切换：右侧属性弹窗 ↔ 智能体对话界面（中间 3D 场景保持）
function toggleAgent() {
  store.toggleAgent()
  pushCmd(store.agentOn ? t('工具 >> 本析智擎：右侧属性面板已切换为智能体对话界面。') : t('工具 >> 已关闭本析智擎，右侧恢复属性面板。'), 'out')
}

// 供命令窗口调用的孪生控制动作
const twinActions = { onSimToggle, onResetView, onOverview, focusSel, onToggleEdit }
// 供工具条调用的动作
const ribbonActions = { onSimToggle, onToggleEdit, saveFlow, toggleAuto, onResetView, toggleOverview, toggleAgent, autoLayoutScheme, flowZoomBtn, flowFit, loadExample, clearScheme, closeView, dataRefresh, openAiModel, marketRefresh, marketSwitch, marketForecast, marketLedgerRefresh, carbonReport, marketInstrument, marketForecastOn, marketTabOn }

/* ---------------- 经典菜单条（文件 / 仿真 / 视图 / 编辑 / 工具 / 帮助） ---------------- */
const menus = computed(() => [
  { id: 'file', label: t('文件'), items: [
    { label: t('新建方案'), act: async () => {
      const saved = await store.confirm({ title: t('新建方案'), message: t('是否保存当前方案？保存完成后将清空编排。'), okText: t('保存并新建'), cancelText: t('不保存，新建') })
      if (saved && !(await store.saveSchemeToFile())) return   // 放弃保存则中止新建
      ensureEdit(); store.clearScheme()
      pushCmd(saved ? t('新建方案：已保存当前方案并清空编排。') : t('新建方案：未保存当前方案，已清空编排。'), 'out')
    } },
    { label: t('打开方案…'), act: async () => {
      if (store.scheme.nodes.length) {
        const saved = await store.confirm({ title: t('打开方案'), message: t('当前方案存在工艺编排，是否先保存当前方案？'), okText: t('保存并继续'), cancelText: t('不保存，继续') })
        if (saved && !(await store.saveSchemeToFile())) return   // 放弃保存则中止打开
      }
      await store.loadSchemeFromFile()
    } },
    { sep: true },
    { label: t('保存方案'), accel: 'Ctrl+S', act: () => { store.saveSchemeToFile() } },
    { sep: true },
    { label: t('设置…'), act: () => { showSettings.value = true } },
  ] },
  { id: 'sim', label: t('仿真'), items: [
    { label: t('运行仿真'), accel: 'Ctrl+Enter', act: onSimToggle },
    { sep: true },
    { label: t('重置仿真参数'), act: onResetParams },
    { label: t('应用当前情景'), act: () => { store.refresh(); pushCmd(t('已应用当前仿真情景并重新计算。'),'out') } },
    { sep: true },
    { label: t('参数优化'), act: () => pushCmd(t('参数优化：切换至「数据」工具条 → 策略生成，使用自然语言描述目标。'),'out') },
    { label: t('数据校准'), act: () => pushCmd(t('数据校准：在右侧检视器选中设备查看实时/历史读数。'),'out') },
  ] },
  { id: 'view', label: t('视图'), items: [
    { sub: true, label: t('数字孪生'), items: () => [
      { sub: true, label: t('环境'), items: () => store.envModes.map(e => ({ id: e.id, label: t(e.label), checked: e.id === store.envMode, run: () => onEnvChange({ target: { value: e.id } }) })) },
    ] },
    { sub: true, label: t('碳资产管理'), items: () => [
      { label: t('CEA / CCER 行情'), checked: store.carbonMarketOn && marketTabOn() === 'market', run: () => marketSubNav('market') },
      { label: t('企业台账与策略'), checked: store.carbonMarketOn && marketTabOn() === 'ledger', run: () => marketSubNav('ledger') },
    ] },
    { label: t('能碳一体机管理'), toggle: () => store.boxManageOn, act: () => boxSubNav() },
  ] },
  { id: 'edit', label: t('编辑'), items: [
    { label: store.editMode ? t('完成编排') : t('进入流程编排'), act: onToggleEdit },
    { label: t('保存编排并生效'), hide: () => !store.editMode, act: saveFlow },
    { sep: true },
    { label: t('撤销'), accel: 'Ctrl+Z', disabled: () => !store.canUndo, act: () => store.undo() },
    { label: t('重做'), accel: 'Ctrl+Y', disabled: () => !store.canRedo, act: () => store.redo() },
    { sep: true, hide: () => !store.editMode },
    { label: t('放大画布'), hide: () => !store.editMode, act: () => flowZoomBtn(1.1) },
    { label: t('缩小画布'), hide: () => !store.editMode, act: () => flowZoomBtn(0.9) },
    { label: t('适配视图'), hide: () => !store.editMode, act: () => flowFit() },
    { label: t('自动布局'), hide: () => !store.editMode, act: () => autoLayoutScheme() },
    { sep: true, hide: () => !store.editMode },
    { label: t('新建小组'), hide: () => !store.editMode, act: () => addGroupBtn() },
    { label: t('复制小组'), hide: () => !store.editMode, disabled: () => !store.selectedGroupId, act: () => duplicateGroupBtn() },
    { label: t('删除小组'), hide: () => !store.editMode, disabled: () => !store.selectedGroupId, act: () => store.removeFlowGroup(store.selectedGroupId) },
    { sep: true, hide: () => !store.editMode },
    { label: t('长流程模板'), hide: () => !store.editMode, act: () => loadExample('long') },
    { label: t('短流程模板'), hide: () => !store.editMode, act: () => loadExample('short') },
    { label: t('清空画布'), hide: () => !store.editMode, act: () => clearScheme() },
  ] },
  { id: 'tools', label: t('工具'), items: [
    { label: t('连接数据源…'), act: () => { showDataSource.value = true } },
    { sep: true },
    { sub: true, label: t('低碳'), items: () => [
      { label: t('碳素流守恒审计'), run: () => openAuditDialog() },
      { label: t('全景碳核查'), run: () => store.toggleCarbonCalc() },
    ] },
    { sub: true, label: t('能源'), items: () => [
      { label: t('能流分析'), run: () => store.toggleEnergyFlow() },
    ] },
  ] },
  { id: 'ai', label: t('AI'), items: [
    { label: t('数据分析与策略'), toggle: () => store.dataViewOn, act: () => store.toggleDataView() },
    { sep: true },
    { label: t('行业知识库'), act: () => { showKnowledgeManage.value = true } },
    { sep: true },
    { label: t('智能体管理'), act: () => { showAgentManage.value = true } },
    { label: t('智能体技能'), act: () => { showSkillManage.value = true } },
    { label: t('本体定义'), act: () => { showOntologyManage.value = true } },
  ] },
  { id: 'help', label: t('帮助'), items: [
    { label: t('宣传手册'), accel: 'F1', act: () => openDocsSite('promo') },
    { label: t('使用手册'), act: () => openDocsSite('manual') },
    { label: t('技术文档'), act: () => openDocsSite('tech') },
    { label: t('快捷键'), act: () => pushCmd(t('快捷键：Ctrl+Enter 运行 · Ctrl+Z 撤销 · Ctrl+Y 重做 · F 聚焦工序 · 编排态 F2 重命名、Ctrl+D 复制、Del 删除 · 右键节点打开菜单。'),'out') },
    { sep: true },
    { label: t('关于本平台'), act: onAbout },
  ] },
])

useGlobalShortcuts({
  store, onSimToggle, focusSel,
  onMenuEsc: () => topBarRef.value && topBarRef.value.closeMenus(),
  onTftAnalysis: () => {
    if (store.simMode) showTftAnalysis.value = true
    else store.showToast(t('高炉数值分析仅限仿真模式使用：请先开启仿真模式'), 'warn')
  },
})

onMounted(async () => {
  // 3D 场景懒加载：默认视图即数字孪生，待首屏 UI（顶栏/侧栏/控制台）渲染完成、
  // 浏览器空闲后立即加载场景 chunk；加载后常驻挂载，切换视图速度不受影响
  const mountScene = () => { sceneMounted.value = true }
  if (window.requestIdleCallback) window.requestIdleCallback(mountScene, { timeout: 1500 })
  else setTimeout(mountScene, 300)
  store.init()
  // 启动提示不再推入命令行（底部命令只保留用户输入交互与直接反馈，少即是多）
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
    import('./views/AgentChatView.vue')
  }, { timeout: 8000 })
})
</script>
