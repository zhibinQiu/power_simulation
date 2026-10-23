<template>
  <div class="app" :class="{ 'left-collapsed': !store.leftOpen, 'right-collapsed': !store.rightOpen, 'bottom-collapsed': !store.bottomOpen, 'sim-dark': store.simMode || themeMode === 'dark', 'fullscreen-on': store.fullscreenOn, 'welcome-on': store.welcomeOn }"
       :data-accent="accent"
       :style="{ '--cmd-h': store.bottomOpen ? cmdH + 'px' : '0px', '--lw': store.leftOpen ? lw + 'px' : '0px', '--rw': store.rightOpen ? rw + 'px' : '0px' }">
    <TopBar :menus="menus" ref="topBarRef" @export="onExport" @help="openDocsSite('promo')" @toggle-agent="toggleAgent" />

    <!-- 最左侧活动栏（VS Code 式）：资源管理器（左栏入口） / 资源管理 / 搜索 / 连接 -->
    <ActivityBar @preload-view="preloadView" />
    <!-- 左侧栏：园区资产（工艺 / 设备 / 原料 / 策略）；收起时由 .left-collapsed 置列宽 0 + 裁切，实现平滑滑出。
         key 绑定「场景 id + 场景版本」：切换场景时强制重建，清空树折叠态 / 当前 tab 等本地状态，避免残留旧场景目录 -->
    <LeftSidebar :key="'ls:' + store.sceneId + ':' + store.sceneVersion" :dragging="lResizing" @rsz="startLeftResize" />

    <!-- 中间：主视图（3D 数字孪生 ⇄ HMI人机交互屏，二者对等、同一槽位） / 功能视图窗口（tab 化：
         流程编排、数据分析、AI群控、碳资产管理、全景碳核查、能流分析、数据源管理） -->
    <!-- SceneViewer 首次进入数字孪生视图时懒加载（three.js ~500KB 不进首屏关键路径），
         加载后保持挂载，不销毁 WebGL 上下文，切换速度与原先一致 -->
    <main class="stage">
      <!-- 工程选择（欢迎页）：启动后先停在这里，左栏保留，内容区做工程选择；
           打开 / 新建工程后由 store.welcomeOn = false 进入主界面。 -->
      <WelcomeView v-if="store.welcomeOn && store.activeViewId !== 'boxManage'" @new-scene="sceneFileMode = 'new'" @open-scene="sceneFileMode = 'open'" />
      <template v-else-if="!store.welcomeOn">
      <!-- 主视图槽位：HMI人机交互屏与 3D 数字孪生对等，二者互斥切换且都不产生 tab -->
      <SceneViewer v-if="sceneMounted" v-show="!store.activeViewId && !store.overviewOn" />
      <DataOverview v-if="store.overviewOn" v-show="!store.activeViewId" />
      </template>
      <!-- 功能视图窗口（tab 模式）：窗口内顶部为当前视图的工具栏，下方为视图内容。
           流程编排同样以窗口 + tab 形式打开（标签「流程编排」），与三维仿真 / 其它视图自由切换；
           编排草稿随编辑态保留，关闭该标签即完成编排并应用方案。
           数据源管理属全局配置入口，在欢迎页也可直接打开，故视图窗口与欢迎页解耦，
           在非欢迎页场景（有 tab 时）保持铺满中间内容区原有布局。 -->
      <section v-if="store.openViews.length || store.editMode" class="view-window" :class="{ 'on-scene': !store.activeViewId }">
        <!-- AI 群控（PID·EKF 控制台）顶部工具栏已移除：控制台自身含标题与操作，无需 35px 工具行 -->
        <RibbonToolbar v-if="!store.aiGroupOn" :actions="ribbonActions" />
        <div class="vw-body">
          <div v-if="store.editMode" v-show="store.activeViewId === 'flowEdit'" class="vw-pane flow-pane">
            <FlowEditor />
          </div>
          <div v-if="viewOpened('dataView')" v-show="store.activeViewId === 'dataView'" class="vw-pane">
            <DataView variant="analysis" ref="dataViewRef" />
          </div>
          <div v-if="viewOpened('aiGroup')" v-show="store.activeViewId === 'aiGroup'" class="vw-pane flush-pane">
            <DataView variant="group" ref="groupViewRef" />
          </div>
          <div v-if="viewOpened('carbonMarket')" v-show="store.activeViewId === 'carbonMarket'" class="vw-pane">
            <CarbonAssistantView ref="marketViewRef" />
          </div>
          <div v-if="viewOpened('carbonCalc')" v-show="store.activeViewId === 'carbonCalc'" class="vw-pane">
            <CarbonCalcView />
          </div>
          <div v-if="viewOpened('energyFlow')" v-show="store.activeViewId === 'energyFlow'" class="vw-pane">
            <EnergyFlowView />
          </div>
          <!-- 数据源管理：打开过即常驻挂载（v-show 隐藏），关闭 tab 不销毁，避免每次进入都重新拉一遍数据 -->
          <div v-if="boxMounted" v-show="store.activeViewId === 'boxManage'" class="vw-pane flush-pane">
            <CarbonBoxView ref="boxViewRef" />
          </div>
        </div>
      </section>
    </main>

    <!-- 顶栏下方一行：tab 模式（有功能视图窗口，含流程编排）显示视图标签条，工具栏已移入对应 tab 内部；
         非 tab 模式（纯三维仿真，无打开窗口）显示原工具条。欢迎页（未打开工程）无工具条，
         但数据源管理可在欢迎页直接打开，此时仍需标签条（否则无法退出该视图）。 -->
    <template v-if="!store.welcomeOn || store.activeViewId === 'boxManage'">
      <ViewTabBar v-if="tabMode" />
      <RibbonToolbar v-else :actions="ribbonActions" />
    </template>

    <!-- 右侧栏：上下文检视器；收起时由 .right-collapsed 置列宽 0 + 裁切，实现平滑滑出。
         同样按场景 key 重建：切换场景后总览档位 / 累计积分 / 展开态等本地状态一并重置 -->
    <RightInspector v-if="!store.welcomeOn" :key="'ri:' + store.sceneId + ':' + store.sceneVersion" @rsz="startRightResize" />

    <!-- 下侧栏：命令控制台；非数字孪生视图默认收起，可由顶栏按钮重新展开（底部状态栏始终保留） -->
    <CommandConsole v-if="!store.welcomeOn" :actions="twinActions" :resizing="resizing" :start-resize="startResize" ref="consoleRef" />

    <StatusBar />

    <SystemSettingsDialog v-if="showSettings" @close="showSettings = false" />
    <SceneFileDialog v-if="sceneFileMode" :mode="sceneFileMode" @close="sceneFileMode = ''" @settings="sceneFileMode = ''; showSettings = true" />
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
import { ref, computed, watch, watchEffect, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { useSimStore } from './stores/sim'
import { t } from './i18n'
import { accent, themeMode } from './theme'
import { lazyDialog, lazyView } from './utils/asyncComp'
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
import ViewTabBar from './components/ViewTabBar.vue'
import WelcomeView from './components/WelcomeView.vue'
import { usePanelSizes } from './composables/usePanelSizes'
import { useGlobalShortcuts } from './composables/useGlobalShortcuts'
import { openAuditDialog } from './stores/audit'

// 对话框类组件按需懒加载：首屏不加载其代码，打开时才请求，降低首包体积与内存占用
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
// 场景文件对话框（文件 → 新建场景 / 打开场景 / 另存为场景）
const SceneFileDialog = defineAsyncComponent(() => import('./components/SceneFileDialog.vue'))

// 视图类组件同样按需懒加载：CarbonBoxView（数据源管理）等体量巨大（数千行），
// 首屏同步打包会让 index 主包高达 600+KB；改为进入对应视图时才加载，首屏只保留
// SceneViewer/LeftSidebar/RightInspector 等数字孪生核心组件，显著降低首屏加载与内存占用。
// 3D 数字孪生场景：three.js（~500KB）+ 场景构建代码体积巨大，改为异步加载。
// 首次进入数字孪生视图（默认即此视图）时才开始加载，加载后保持挂载，
// 不销毁 WebGL 上下文（切换视图速度与原先一致）；首屏只渲染 UI 框架，不阻塞。
function cachedLoader(factory) {
  let pending = null
  return () => {
    if (!pending) pending = factory().catch((error) => { pending = null; throw error })
    return pending
  }
}

const loadSceneViewer = cachedLoader(() => import('./components/SceneViewer.vue'))
const loadDataView = cachedLoader(() => import('./components/DataView.vue'))
const loadCarbonAssistant = cachedLoader(() => import('./views/CarbonAssistantView.vue'))
const loadCarbonCalc = cachedLoader(() => import('./components/CarbonCalcView.vue'))
const loadEnergyFlow = cachedLoader(() => import('./components/EnergyFlowView.vue'))
const loadCarbonBox = cachedLoader(() => import('./components/CarbonBoxView.vue'))
const loadDataOverview = cachedLoader(() => import('./components/DataOverview.vue'))
const loadFlowEditor = cachedLoader(() => import('./components/FlowEditor.vue'))

const SceneViewer = lazyView(loadSceneViewer, { label: t('三维仿真'), delay: 0 })
const DataView = lazyView(loadDataView, { label: t('数据分析') })
const CarbonAssistantView = lazyView(loadCarbonAssistant, { label: t('碳资产管理') })
const CarbonCalcView = lazyView(loadCarbonCalc, { label: t('全景碳核查') })
const EnergyFlowView = lazyView(loadEnergyFlow, { label: t('能流分析') })
const CarbonBoxView = lazyView(loadCarbonBox, { label: t('数据源管理') })
const DataOverview = lazyView(loadDataOverview, { label: t('HMI人机交互屏') })
const FlowEditor = lazyView(loadFlowEditor, { label: t('流程编排'), delay: 0 })

// 等待视图组件挂载完成：懒加载组件首次打开需异步加载代码，ref 可能延迟可用。
// 用 watch 等 ref 由 null 变为组件实例，而不是 setInterval 每 80ms 轮询一次
// （6s 超时 = 最多 75 次无意义的定时器唤醒，且每次都要读一遍响应式 ref）。
function waitViewRef(r, timeout = 6000) {
  if (r.value) return Promise.resolve(true)
  return new Promise((resolve) => {
    let settled = false
    const finish = (v) => {
      if (settled) return
      settled = true
      stopWatch()
      clearTimeout(timer)
      resolve(v)
    }
    const stopWatch = watch(r, (v) => { if (v) finish(true) })
    const timer = setTimeout(() => finish(false), timeout)
  })
}

const store = useSimStore()
// AI 群控：离开（切换其它视图 / 返回孪生 / 关闭 tab）时恢复进入前的右侧系统栏开合状态
// （训练面板已内嵌群控右栏，进入时由 store 备份并收起外部右栏，见 _activateView / openAiGroup）
watch(() => store.activeViewId, (n, o) => {
  if (o === 'aiGroup' && n !== 'aiGroup' && store.grpRightBackup != null) {
    store.rightOpen = store.grpRightBackup
    store.grpRightBackup = null
  }
})
// —— 面板开合动画标记（供重组件延后昂贵响应）——
// .app 的 grid 列宽过渡（220ms）会让中间舞台宽度**每帧**变化，而数字孪生视图对尺寸变化的
// 响应极贵：3D 要重建 WebGL 绘制缓冲（renderer.setSize），2D 要重新适配整幅 SVG 视图并持续
// 重绘流向动画。每帧各来一次 → 开合侧栏时明显掉帧（实测 2D 下 p95 帧间隔 150~880ms）。
// 这里在动画期间给 body 打标记，两个视图据此把昂贵响应**延后到动画结束执行一次**：
// 3D 每帧只同步投影宽高比、绘制缓冲延后（见 SceneViewer.onResize），2D 冻结图层、
// 只改 transform（见 Twin2DView.onCanvasResize）；过渡时长见 main.css 的 .app 规则。
const PANEL_ANIM_MS = 260   // 略大于 CSS 过渡 .22s，确保覆盖最后一帧
let panelAnimTimer = null
function markPanelAnim() {
  // 用户偏好「减少动效」时 .app 无过渡，宽度一次到位，不需要延后
  if (window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches) return
  document.body.classList.add('panel-animating')
  clearTimeout(panelAnimTimer)
  panelAnimTimer = setTimeout(() => {
    document.body.classList.remove('panel-animating')
    panelAnimTimer = null
  }, PANEL_ANIM_MS)
}
watch(() => [store.leftOpen, store.rightOpen, store.bottomOpen], () => markPanelAnim())

// 深色模式同步到 body：高炉数值仿真弹窗等对话框用 <Teleport to="body"> 渲染，
// 不在 .app 作用域内，拿不到 .app.sim-dark 上那套深色变量（只会继承 :root 的浅色），
// 表现为「深色界面里弹出白色弹窗」。把同一状态挂到 body，让弹窗与主界面同主题。
watchEffect(() => {
  if (typeof document === 'undefined') return
  document.body.classList.toggle('sim-dark', !!store.simMode || themeMode.value === 'dark')
})

// 3D 场景首次加载后保持挂载，避免切视图时反复销毁 WebGL 上下文。
const sceneMounted = ref(false)
function preloadSceneViewer() {
  if (!store.sceneLoad.active) store.beginSceneLoad('code')
  return loadSceneViewer().catch((error) => {
    store.failSceneLoad(error && error.message ? error.message : String(error))
    throw error
  })
}
const viewLoaders = {
  flowEdit: loadFlowEditor,
  dataView: loadDataView,
  aiGroup: loadDataView,
  carbonMarket: loadCarbonAssistant,
  carbonCalc: loadCarbonCalc,
  energyFlow: loadEnergyFlow,
  boxManage: loadCarbonBox,
  overview: loadDataOverview,
}
function preloadView(id) {
  const loader = viewLoaders[id]
  if (loader) loader().catch(() => {})
}
function preloadWorkspaceCore() {
  preloadSceneViewer().catch(() => {})
  loadFlowEditor().catch(() => {})
}
function mountSceneNow() {
  if (sceneMounted.value) return
  preloadSceneViewer().catch(() => {})
  sceneMounted.value = true
}
function scheduleCommonViewPreload() {
  const run = () => {
    loadDataView().catch(() => {})
    loadCarbonAssistant().catch(() => {})
    loadCarbonCalc().catch(() => {})
    loadEnergyFlow().catch(() => {})
    loadCarbonBox().catch(() => {})
    loadDataOverview().catch(() => {})
    import('./views/AgentChatView.vue').catch(() => {})
    import('./components/UnitCarbonDetail.vue').catch(() => {})
    import('./components/FlowInspector.vue').catch(() => {})
  }
  if (window.requestIdleCallback) window.requestIdleCallback(run, { timeout: 2000 })
  else setTimeout(run, 600)
}
// 欢迎页 → 主界面时挂载 3D；场景装载一开始即预取代码，与资源请求并行。
let stopWelcomeWatch = null
let stopSceneBusyWatch = null
const topBarRef = ref(null)
const consoleRef = ref(null)
// 视图组件引用：供各视图工具栏（RibbonToolbar）调用其内部动作（刷新行情 / 刷新数据等）
const dataViewRef = ref(null)
const groupViewRef = ref(null)   // AI 群控（DataView 的 group 形态，与数据分析各自独立实例）
const marketViewRef = ref(null)
const boxViewRef = ref(null)

const showSettings = ref(false)
const showTftAnalysis = ref(false)
const showKnowledgeManage = ref(false)
const showAgentManage = ref(false)
const showSkillManage = ref(false)
const showOntologyManage = ref(false)
// 场景文件对话框模式：'' 关闭 | 'new' 新建场景 | 'open' 打开场景 | 'saveAs' 另存为场景
const sceneFileMode = ref('')

const { lw, rw, cmdH, lResizing, resizing, startLeftResize, startRightResize, startResize } = usePanelSizes()

/* ---------------- 动作 ---------------- */
function pushCmd(t, k = 'out') { store.pushCmd(t, k) }
function onRun() {
  const hasStrategies = Object.values(store.unitStrategies).some(s => s.enabled)
  if (hasStrategies) store.runAllEnabledStrategies()
  else store.refresh()
}
function onSimToggle() {
  if (store.simMode) store.exitSim()
  else {
    store.enterSim()
    consoleRef.value && consoleRef.value.focusInput()
  }
}
// 操作结果由界面本身呈现（视图变化 / 数据刷新 / 面板打开），命令行只在「失败或需要警示」时播报，
// 避免把控制台变成复述操作的流水账
function onResetParams() { store.refresh() }
function onRefresh() { store.resetView(); store.refresh() }
function onResetView() { store.resetView() }
function toggleAuto() { store.setAutoRotate(!store.autoRotate) }
function focusSel(mode) {
  if (!store.selectedUnitId) { pushCmd(t('未选中工序：请先在左侧资产树或 3D 孪生中点选工序。'), 'warn'); return }
  store.viewUnit(store.selectedUnitId, mode)
}
function onOverview() { store.viewUnit('__overview__', 'overview') }
function onAutoLayout() { store.autoLayout(); store.refresh(); store.sceneRev++ }
function onToggleEdit() { preloadView('flowEdit'); if (store.editMode) store.exitEdit(); else store.enterEdit() }
// 编排动作（载入模板 / 清空画布 / 自动布局…）前置：未进入编排则进入；已在编排但当前在其它 tab 则切回编排标签
function ensureEdit() { preloadView('flowEdit'); if (!store.editMode) store.enterEdit(); else store.activateView('flowEdit') }
// 当前场景是否提供该模板 id（编排菜单据此决定模板项显隐）
function hasTemplate(id) {
  const fromTemplates = (store.sceneTemplates || []).some((t) => t.id === id || t.route === id)
  if (fromTemplates) return true
  const routes = store.scenePack?.meta?.routes || store.sceneIndex?.find((s) => s.id === store.sceneId)?.routes
  return (routes || []).includes(id)
}
function loadExample(route) { ensureEdit(); store.loadTemplate(route) }
function clearScheme() { ensureEdit(); store.clearScheme() }
// 编排手动保存：改动只反映在编排画布（草稿），点「保存」才写入本地存档 + 服务端 designs/flow，
// 并同步为已应用方案 —— 3D 数字孪生 / 2D 工艺图 / KPI 自此才切换到新的编排内容
function saveScheme() {
  // AI 群控编排同样是手动保存：Ctrl+S 落在群控视图上时转发给它（由其自行落库 agc 桶）
  if (store.activeViewId === 'aiGroup') { store.requestAgcSave(); return }
  if (!store.editMode) { store.showToast(t('编排保存仅在流程编排模式下可用'), 'info'); return }
  store.saveScheme()
}
// 自动布局：主工艺沿水平中线成主干、工辅分列主干上下两侧（与 3D 孪生空间一致），布局后自动适配视图
function autoLayoutScheme() { ensureEdit(); store.autoLayoutScheme(); store.flowZoomFit() }
function addGroupBtn() { ensureEdit(); if (!store.addFlowGroup()) store.toast = t('新建小组失败。') }
function duplicateGroupBtn() { ensureEdit(); store.duplicateFlowGroup(store.selectedGroupId) }
function flowZoomBtn(f) { store.flowZoom(f) }
function flowFit() { store.flowZoomFit() }
function onEnvChange(e) { store.setEnvMode(e.target.value) }
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
}
// 打开独立文档网站（宣传手册 / 使用手册 / 技术文档）：文档站已并入平台【同源】访问，
// 统一入口为 /docs/#/<page>（页面路径 /docs/ + hash 路由）：
//   - 开发态：vite dev 把 /docs 代理到本地 docs-site dev server（127.0.0.1:5174）
//   - 生产态：平台后端把 /docs 反代到 docs-site 容器
// 同源跳转无需额外端口（40184 不再对外开放），且 window.open 同步执行于用户手势栈内，
// 不会被浏览器弹窗拦截。
function openDocsSite(page = '') {
  const target = page ? '/#/' + page : '/#/'
  window.open(`${location.origin}/docs${target}`, '_blank')
}
function onAbout() { store.openAbout() }

// 功能视图是否已打开（窗口已挂载）：用于决定视图组件是否创建（关闭的窗口才销毁组件）
const viewOpened = (id) => store.openViews.includes(id)
// 「数据源管理」：一旦打开过就保持挂载，关闭 tab 只隐藏不销毁。
// 该视图首屏要拉设备清单 / 云端 CRD / agent 状态 / 数据源目录等多路数据（云端不可达时还要等满超时），
// 销毁重建会让每次进入都重新加载一遍；组件内部在未激活时会停掉轮询与观察器，隐藏期间零请求。
const boxMounted = ref(false)
watch(() => store.openViews.includes('boxManage'), (on) => { if (on) boxMounted.value = true }, { immediate: true })
// tab 模式：已打开任何视图窗口（功能视图 / 流程编排）—— 顶栏下方让位给视图标签条，
// 各视图工具栏移入窗口内部（tab 下方），随 tab 切换一起变化
const tabMode = computed(() => store.openViews.length > 0)
// 关闭当前视图窗口，返回数字孪生场景（供各视图工具栏「关闭」按钮调用；
// 编排标签走 closeViewById → exitEdit，即「完成编排」并应用方案）
function closeView() {
  if (store.activeViewId) store.closeViewById(store.activeViewId)
  else if (store.editMode) store.exitEdit()
}
// 工况数据分析 / AI群控：重新拉取历史数据（DataView 暴露的 refresh，按当前激活窗口取对应实例）
async function dataRefresh() {
  const r = store.activeViewId === 'aiGroup' ? groupViewRef : dataViewRef
  await waitViewRef(r)
  if (r.value?.refresh) r.value.refresh()
}
// 工况数据分析视图：AI 分析按钮 —— 打开右侧对应属性面板（时序预测 / 参数优化 / 聚类分析 / 数据拟合）。
// 与左侧资源树点击 AI 模型行为一致（selectStrategy → 右侧 strategyDetail）；参数优化为集中面板（GA/PSO/RL 面板内切换）。
function openAiModel(id) {
  if (id === 'ai::opt') {
    // 参数优化集中面板：已打开某个参数优化算法时保持不跳变，否则默认遗传算法（面板顶部可切换 遗传算法 / 粒子群 / 强化学习）
    const cur = store.selectedStrategyId
    const curOpt = /^ai::(ga|pso|rl)$/.test(String(cur || ''))
    store.selectStrategy(curOpt ? cur : 'ai::ga')
    return
  }
  const cur = store.selectedStrategyId
  store.selectStrategy(cur === id ? cur : id)
}
// AI 群控视图（AI → AI群控 / 活动栏按钮共用）：与数据分析同布局、无 tab，
// 内容区左右两栏：左「训练前测试」（滤波 → 稳态闭环控制实验）｜右「训练相关设定」（低能耗稳态寻优训练，GA/PSO/RL）
function openAiGroup() { preloadView('aiGroup'); store.openAiGroup() }
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
// 顶栏菜单：打开碳资产管理窗口并切换到指定页签（market 行情 / ledger 台账）
const marketSubNav = async (id) => {
  preloadView('carbonMarket')
  store.openView('carbonMarket')
  await waitViewRef(marketViewRef)
  if (marketViewRef.value) marketViewRef.value.switchTab(id)
}
// 顶栏「视图」菜单：打开数据源管理（能碳一体机 + 外部数据源统一接入；
// 原「数据概览 / 设备管理」两页签已合并为同一界面，对外名称为「数据源管理」）
const boxSubNav = () => { preloadView('boxManage'); store.openView('boxManage') }
// 碳资产管理视图：刷新企业台账（CarbonAssistantView 暴露的 refreshLedger，转发到台账面板 loadAll）
const marketLedgerRefresh = async () => { await waitViewRef(marketViewRef); if (marketViewRef.value?.refreshLedger) marketViewRef.value.refreshLedger() }
// 工具栏「三维仿真/HMI人机交互屏」切换：中间 3D 场景 ↔ 企业实时运行 HMI 大屏
function toggleOverview() { preloadView('overview'); store.toggleOverview() }
// 工具栏「本析智擎」切换：右侧属性弹窗 ↔ 智能体对话界面（中间 3D 场景保持）
function toggleAgent() { store.toggleAgent() }

// 供命令窗口调用的孪生控制动作
const twinActions = { onSimToggle, onResetView, onOverview, focusSel, onToggleEdit }
// 供工具条调用的动作
const ribbonActions = { onSimToggle, onToggleEdit, toggleAuto, onResetView, toggleOverview, toggleAgent, saveScheme, autoLayoutScheme, flowZoomBtn, flowFit, loadExample, clearScheme, closeView, dataRefresh, openAiModel, marketRefresh, marketSwitch, marketForecast, marketLedgerRefresh, carbonReport, marketInstrument, marketForecastOn, marketTabOn }

/* ---------------- 经典菜单条（文件 / 仿真 / 视图 / 编辑 / 工具 / 帮助；AI 已整体并入「工具」） ---------------- */
const menus = computed(() => [
  { id: 'file', label: t('文件'), items: [
    // 「新建场景」：先选择场景类别（四大控排 / 其它），再按该类别可用资源包新建空白编排方案
    { label: t('新建场景'), act: () => { sceneFileMode.value = 'new' } },
    // 「打开场景…」：按行业分组列出场景注册表（内置包 + 已安装 .ec），选择后切换
    { label: t('打开场景…'), act: () => { sceneFileMode.value = 'open' } },
    // 「返回工程选择」：退回启动时的工程选择欢迎页（当前工程保持装载，再打开即回到原工程）
    { label: t('返回工程选择'), act: () => store.backToWelcome() },
    { sep: true },
    // 「另存为场景…」：把当前场景（含当前编排方案快照）打包为可分发的 .ec 资源包
    { label: t('另存为场景…'), accel: 'Ctrl+Shift+S', act: () => { sceneFileMode.value = 'saveAs' } },
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
    // HMI人机交互屏：与 3D 数字孪生对等的主视图形态（同槽位切换，不开 tab）
    { label: t('HMI人机交互屏'), toggle: () => store.overviewOn, act: () => toggleOverview() },
    { label: t('数据源管理'), toggle: () => store.boxManageOn, act: () => boxSubNav() },
  ] },
  { id: 'edit', label: t('编辑'), items: [
    { label: store.editMode ? t('完成编排') : t('进入流程编排'), act: onToggleEdit },
    // 编排为手动保存：改动不会自动落盘，此处与工具条「保存」按钮同源（Ctrl+S）
    { label: t('保存编排'), accel: 'Ctrl+S', hide: () => !store.editMode, disabled: () => !store.schemeDirty, act: () => saveScheme() },
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
    // 模板项按「当前场景实际有哪些模板」显隐：非钢场景（如机房温控）没有长/短流程，
    // 此前写死显示，点了会静默载入本场景第一个模板并弹出「已载入长流程炼钢模板」的误导提示
    { label: t('长流程模板'), hide: () => !store.editMode || !hasTemplate('long'), act: () => loadExample('long') },
    { label: t('短流程模板'), hide: () => !store.editMode || !hasTemplate('short'), act: () => loadExample('short') },
    { label: t('清空画布'), hide: () => !store.editMode, act: () => clearScheme() },
  ] },
  { id: 'tools', label: t('工具'), items: [
    // AI（原顶层「AI」菜单整体下沉到工具菜单）：数据分析 / 群控 + 知识库 / 智能体 / 技能 / 本体
    { sub: true, label: t('AI'), items: () => [
      { label: t('数据分析'), toggle: () => store.dataViewOn, act: () => { preloadView('dataView'); store.toggleDataView() } },
      // MPC 控温优化已集成进 AI 群控的模型库（内置求解型模型），不再单列菜单项
      { label: t('AI群控'), toggle: () => store.aiGroupOn, act: () => openAiGroup() },
      { sep: true },
      { label: t('行业知识库'), act: () => { showKnowledgeManage.value = true } },
      { sep: true },
      { label: t('智能体管理'), act: () => { showAgentManage.value = true } },
      { label: t('智能体技能'), act: () => { showSkillManage.value = true } },
      { label: t('本体定义'), act: () => { showOntologyManage.value = true } },
    ] },
    // 双碳：碳素流审计 / 全景碳核查 / 碳资产管理
    { sub: true, label: t('双碳'), items: () => [
      { label: t('碳素流守恒审计'), run: () => openAuditDialog() },
      { label: t('全景碳核查'), toggle: () => store.carbonCalcOn, run: () => { preloadView('carbonCalc'); store.toggleCarbonCalc() } },
      { sep: true },
      { sub: true, label: t('碳资产管理'), items: () => [
        { label: t('CEA / CCER 行情'), checked: store.carbonMarketOn && marketTabOn() === 'market', run: () => marketSubNav('market') },
        { label: t('企业台账与策略'), checked: store.carbonMarketOn && marketTabOn() === 'ledger', run: () => marketSubNav('ledger') },
      ] },
    ] },
    // 能源：能流分析
    { sub: true, label: t('能源'), items: () => [
      { label: t('能流分析'), run: () => { preloadView('energyFlow'); store.toggleEnergyFlow() } },
    ] },
  ] },
  { id: 'help', label: t('帮助'), items: [
    { label: t('宣传手册'), accel: 'F1', act: () => openDocsSite('promo') },
    { label: t('使用手册'), act: () => openDocsSite('manual') },
    { label: t('技术文档'), act: () => openDocsSite('tech') },
    { label: t('快捷键'), act: () => pushCmd(t('快捷键：Ctrl+Enter 运行 · Ctrl+S 保存编排（手动保存） · Ctrl+Shift+S 另存为场景 · Ctrl+Z 撤销 · Ctrl+Y 重做 · F 聚焦工序 · 编排态 F2 重命名、Ctrl+D 复制、Del 删除 · 右键节点打开菜单。'),'out') },
    { sep: true },
    { label: t('关于本平台'), act: onAbout },
  ] },
])

useGlobalShortcuts({
  store, onSimToggle, focusSel,
  onSaveScheme: saveScheme,
  onSaveAsScene: () => { sceneFileMode.value = 'saveAs' },
  onMenuEsc: () => topBarRef.value && topBarRef.value.closeMenus(),
  onTftAnalysis: () => {
    if (store.simMode) showTftAnalysis.value = true
    else store.showToast(t('高炉数值分析仅限仿真模式使用：请先开启仿真模式'), 'warn')
  },
})

onMounted(async () => {
  const initPromise = store.init()
  // _loadWelcomeState 在 init 的第一个 await 前同步完成：已进入工作区时立即并行下载 3D 与编排分片。
  if (!store.welcomeOn) preloadWorkspaceCore()
  stopSceneBusyWatch = watch(() => store.sceneBusy, (busy) => {
    if (busy) preloadWorkspaceCore()
  }, { flush: 'sync' })

  const initialized = await initPromise
  if (!initialized || !store.ready) {
    store.failSceneLoad(store.toast || t('初始化失败'))
    return
  }
  if (!store.welcomeOn) {
    const restored = await store.restoreLastScene()
    store.entered = true
    if (!restored) {
      store.refresh()
      store.sceneRev++
    }
    mountSceneNow()
    scheduleCommonViewPreload()
  }
  stopWelcomeWatch = watch(() => store.welcomeOn, (on) => {
    if (on) return
    preloadWorkspaceCore()
    mountSceneNow()
    scheduleCommonViewPreload()
  })
})
onBeforeUnmount(() => {
  if (panelAnimTimer) { clearTimeout(panelAnimTimer); panelAnimTimer = null }
  if (stopWelcomeWatch) { stopWelcomeWatch(); stopWelcomeWatch = null }
  if (stopSceneBusyWatch) { stopSceneBusyWatch(); stopSceneBusyWatch = null }
  document.body.classList.remove('panel-animating', 'sim-dark')
})
</script>
