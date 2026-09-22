<template>
  <div class="app" :class="{ 'left-collapsed': !store.leftOpen, 'right-collapsed': !store.rightOpen, 'bottom-collapsed': !store.bottomOpen, 'sim-dark': store.simMode || themeMode === 'dark', 'fullscreen-on': store.fullscreenOn }"
       :data-accent="accent"
       :style="{ '--cmd-h': store.bottomOpen ? cmdH + 'px' : '0px', '--lw': store.leftOpen ? lw + 'px' : '0px', '--rw': store.rightOpen ? rw + 'px' : '0px' }">
    <TopBar :menus="menus" ref="topBarRef" @export="onExport" @help="openDocsSite('promo')" @toggle-agent="toggleAgent" />

    <!-- 最左侧活动栏（VS Code 式）：资源管理器 / 搜索 / 场景 / 连接 -->
    <ActivityBar />
    <!-- 左侧栏：园区资产（工艺 / 设备 / 原料 / 策略）；收起时由 .left-collapsed 置列宽 0 + 裁切，实现平滑滑出。
         key 绑定「场景 id + 场景版本」：切换场景时强制重建，清空树折叠态 / 当前 tab 等本地状态，避免残留旧场景目录 -->
    <LeftSidebar :key="'ls:' + store.sceneId + ':' + store.sceneVersion" @rsz="startLeftResize" />

    <!-- 中间：主视图（3D 数字孪生 ⇄ HMI人机交互屏，二者对等、同一槽位） / 功能视图窗口（tab 化：
         流程编排、数据分析、AI群控、碳资产管理、全景碳核查、能流分析、数据源管理） -->
    <!-- SceneViewer 首次进入数字孪生视图时懒加载（three.js ~500KB 不进首屏关键路径），
         加载后保持挂载，不销毁 WebGL 上下文，切换速度与原先一致 -->
    <main class="stage">
      <!-- 主视图槽位：HMI人机交互屏与 3D 数字孪生对等，二者互斥切换且都不产生 tab -->
      <SceneViewer v-if="sceneMounted" v-show="!store.activeViewId && !store.overviewOn" />
      <DataOverview v-if="store.overviewOn" v-show="!store.activeViewId" />
      <!-- 功能视图窗口（tab 模式）：窗口内顶部为当前视图的工具栏，下方为视图内容。
           流程编排同样以窗口 + tab 形式打开（标签「流程编排」），与三维仿真 / 其它视图自由切换；
           编排草稿随编辑态保留，关闭该标签即完成编排并应用方案。 -->
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
          <div v-if="viewOpened('boxManage')" v-show="store.activeViewId === 'boxManage'" class="vw-pane flush-pane">
            <CarbonBoxView ref="boxViewRef" />
          </div>
        </div>
      </section>
    </main>

    <!-- 顶栏下方一行：tab 模式（有功能视图窗口，含流程编排）显示视图标签条，工具栏已移入对应 tab 内部；
         非 tab 模式（纯三维仿真，无打开窗口）显示原工具条 -->
    <ViewTabBar v-if="tabMode" />
    <RibbonToolbar v-else :actions="ribbonActions" />

    <!-- 右侧栏：上下文检视器；收起时由 .right-collapsed 置列宽 0 + 裁切，实现平滑滑出。
         同样按场景 key 重建：切换场景后总览档位 / 累计积分 / 展开态等本地状态一并重置 -->
    <RightInspector :key="'ri:' + store.sceneId + ':' + store.sceneVersion" @rsz="startRightResize" />

    <!-- 下侧栏：命令控制台；非数字孪生视图默认收起，可由顶栏按钮重新展开（底部状态栏始终保留） -->
    <CommandConsole :actions="twinActions" :resizing="resizing" :start-resize="startResize" ref="consoleRef" />

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
import { ref, computed, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
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
import ViewTabBar from './components/ViewTabBar.vue'
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
const SceneViewer = defineAsyncComponent(() => import('./components/SceneViewer.vue'))
const DataView = defineAsyncComponent(() => import('./components/DataView.vue'))
const CarbonAssistantView = defineAsyncComponent(() => import('./views/CarbonAssistantView.vue'))
const CarbonCalcView = defineAsyncComponent(() => import('./components/CarbonCalcView.vue'))
const EnergyFlowView = defineAsyncComponent(() => import('./components/EnergyFlowView.vue'))
const CarbonBoxView = defineAsyncComponent(() => import('./components/CarbonBoxView.vue'))
const DataOverview = defineAsyncComponent(() => import('./components/DataOverview.vue'))
const FlowEditor = defineAsyncComponent(() => import('./components/FlowEditor.vue'))

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
// 这里在动画期间给 body 打标记，两个视图据此把响应**延后到动画结束执行一次**（见
// SceneViewer.onResize / Twin2DView.onCanvasResize）；过渡时长见 main.css 的 .app 规则。
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

// 3D 场景挂载标记：首次加载后保持 true，避免卸载 WebGL 上下文（切换视图速度不受影响）
const sceneMounted = ref(false)
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
// 编排动作（载入模板 / 清空画布 / 自动布局…）前置：未进入编排则进入；已在编排但当前在其它 tab 则切回编排标签
function ensureEdit() { if (!store.editMode) store.enterEdit(); else store.activateView('flowEdit') }
function loadExample(route) { ensureEdit(); store.loadTemplate(route); pushCmd(route === 'short' ? t('已载入短流程炼钢模板。') : t('已载入长流程炼钢模板。'), 'out') }
function clearScheme() { ensureEdit(); store.clearScheme(); pushCmd(t('已清空编排画布。'), 'out') }
// 自动布局：主工艺沿水平中线成主干、工辅分列主干上下两侧（与 3D 孪生空间一致），布局后自动适配视图
function autoLayoutScheme() { ensureEdit(); store.autoLayoutScheme(); store.flowZoomFit(); pushCmd(t('已自动布局：主工艺横向排成主干，工辅分布在主干两侧。'), 'out') }
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
// tab 模式：已打开任何视图窗口（功能视图 / 流程编排）—— 顶栏下方让位给视图标签条，
// 各视图工具栏移入窗口内部（tab 下方），随 tab 切换一起变化
const tabMode = computed(() => store.openViews.length > 0)
// 关闭当前视图窗口，返回数字孪生场景（供各视图工具栏「关闭」按钮调用；
// 编排标签走 closeViewById → exitEdit，即「完成编排」并应用方案）
function closeView() {
  if (store.activeViewId) store.closeViewById(store.activeViewId)
  else if (store.editMode) store.exitEdit()
  pushCmd(t('已返回数字孪生场景。'), 'out')
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
    store.toast = t('已打开参数优化属性面板：可在面板顶部切换 遗传算法 / 粒子群 / 强化学习')
    return
  }
  const cur = store.selectedStrategyId
  store.selectStrategy(cur === id ? cur : id)
  const m = id === 'ai::seq' ? t('时序预测') : id === 'ai::clu' ? t('聚类分析') : id === 'ai::fit' ? t('数据拟合') : t('AI 模型')
  store.toast = t('已打开「') + m + t('」属性面板')
}
// AI 群控视图（AI → AI群控 / 活动栏按钮共用）：与数据分析同布局、无 tab，
// 内容区左右两栏：左「训练前测试」（滤波 → 稳态闭环控制实验）｜右「训练相关设定」（低能耗稳态寻优训练，GA/PSO/RL）
function openAiGroup() {
  store.openAiGroup()
  if (store.aiGroupOn) pushCmd(t('AI群控：请从左侧「场景」资源树拖入受控设备 —— 左栏「训练前测试」做滤波与稳态闭环测试，右栏「训练相关设定」配置算法/目标后开始训练，得到低能耗稳态最优参数。'), 'out')
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
// 顶栏菜单：打开碳资产管理窗口并切换到指定页签（market 行情 / ledger 台账）
const marketSubNav = async (id) => {
  store.openView('carbonMarket')
  await waitViewRef(marketViewRef)
  if (marketViewRef.value) marketViewRef.value.switchTab(id)
  pushCmd(t('工具 >> 双碳 >> 碳资产管理 >> ') + (id === 'market' ? t('CEA / CCER 行情') : t('企业台账与策略')) + t('。'), 'out')
}
// 顶栏「视图」菜单：打开数据源管理（能碳一体机 + 外部数据源统一接入；
// 原「数据概览 / 设备管理」两页签已合并为同一界面，对外名称为「数据源管理」）
const boxSubNav = () => {
  store.openView('boxManage')
  pushCmd(t('视图 >> 数据源管理。'), 'out')
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

/* ---------------- 经典菜单条（文件 / 仿真 / 视图 / 编辑 / 工具 / 帮助；AI 已整体并入「工具」） ---------------- */
const menus = computed(() => [
  { id: 'file', label: t('文件'), items: [
    // 「新建场景」：先选择场景类别（四大控排 / 其它），再按该类别可用资源包新建空白编排方案
    { label: t('新建场景'), act: () => { sceneFileMode.value = 'new' } },
    // 「打开场景…」：按行业分组列出场景注册表（内置包 + 已安装 .ec），选择后切换
    { label: t('打开场景…'), act: () => { sceneFileMode.value = 'open' } },
    { sep: true },
    // 「另存为场景…」：把当前场景（含当前编排方案快照）打包为可分发的 .ec 资源包
    { label: t('另存为场景…'), accel: 'Ctrl+S', act: () => { sceneFileMode.value = 'saveAs' } },
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
    // AI（原顶层「AI」菜单整体下沉到工具菜单）：数据分析 / 群控 + 知识库 / 智能体 / 技能 / 本体
    { sub: true, label: t('AI'), items: () => [
      { label: t('数据分析'), toggle: () => store.dataViewOn, act: () => store.toggleDataView() },
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
      { label: t('全景碳核查'), toggle: () => store.carbonCalcOn, run: () => store.toggleCarbonCalc() },
      { sep: true },
      { sub: true, label: t('碳资产管理'), items: () => [
        { label: t('CEA / CCER 行情'), checked: store.carbonMarketOn && marketTabOn() === 'market', run: () => marketSubNav('market') },
        { label: t('企业台账与策略'), checked: store.carbonMarketOn && marketTabOn() === 'ledger', run: () => marketSubNav('ledger') },
      ] },
    ] },
    // 能源：能流分析
    { sub: true, label: t('能源'), items: () => [
      { label: t('能流分析'), run: () => store.toggleEnergyFlow() },
    ] },
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
  // 3D 场景懒加载：默认视图即数字孪生。挂载时机刻意放在**首屏数据就绪之后**——
  // 此前在 onMounted 开头就挂载，TwinScene 的构造（渲染器/环境/地表）与 store.init、waitReady、
  // 首屏 Vue 渲染抢同一条主线程，模型刚建好又要跟着 ready/sceneRev/场景恢复连做 2~3 次全量重建，
  // 首页加载那几秒正是掉帧最明显的时候。延后挂载后场景一次成型，重建次数也降到最少。
  const mountScene = () => { sceneMounted.value = true }
  store.init()
  // 启动提示不再推入命令行（底部命令只保留用户输入交互与直接反馈，少即是多）
  // 无宣传页：初始化完成后直接进入主界面（保留已保存方案，不重建覆盖）
  await store.waitReady()
  // 自动恢复上次退出前打开的场景（随 openScene 持久化到 localStorage）；
  // 未恢复（首次启动 / 场景已卸载 / 资源包未就绪）时按默认场景走原启动流程
  const restored = await store.restoreLastScene()
  store.entered = true
  if (!restored) {
    store.refresh()
    store.sceneRev++
  }
  // 首屏数据与 UI 都已就绪，等浏览器空闲再加载 3D 场景 chunk（加载后常驻，切换视图不受影响）
  if (window.requestIdleCallback) window.requestIdleCallback(mountScene, { timeout: 1500 })
  else setTimeout(mountScene, 300)
  // 首屏渲染完成且浏览器空闲后，预取常用视图 chunk：兼顾首屏轻量与后续视图切换的响应速度
  // （defineAsyncComponent 的 loader 拉取模块后即被缓存，再次打开无需重新请求）
  const idle = window.requestIdleCallback || ((cb) => setTimeout(cb, 4000))
  idle(() => {
    import('./components/CarbonBoxView.vue')
    import('./views/CarbonAssistantView.vue')
    import('./components/DataView.vue')
    import('./views/AgentChatView.vue')
    // 右侧高频面板（选中工序的详情 / 编排属性）：已从首屏主包异步拆出，这里补一次空闲预取，
    // 保证点开时不出现等待
    import('./components/UnitCarbonDetail.vue')
    import('./components/FlowInspector.vue')
  }, { timeout: 8000 })
})
onBeforeUnmount(() => {
  if (panelAnimTimer) { clearTimeout(panelAnimTimer); panelAnimTimer = null }
  document.body.classList.remove('panel-animating')
})
</script>
