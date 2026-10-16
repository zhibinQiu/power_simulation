<template>
  <!-- 工具条（独立行：位于顶部菜单条下方、3D 视图/编排画布上方，横贯全宽，普通/编排态浅色、仿真态深色）
       按当前激活视图渲染各自工具栏：数字孪生 / 流程编排 / 工况数据分析 / CEA 行情 / 碳排核算 / 能流分析 / 能碳一体机 -->
  <div class="ribbon">
      <div class="ribbon-body">
        <!-- ============ 数字孪生（默认）：运行仿真 + 流程编排 + 视角工具 ============ -->
        <template v-if="view === 'twin'">
          <div class="rbtns">
            <button class="rbtn sim-btn" :class="{ on: store.simMode }" @click="actions.onSimToggle()"
                   >
              <Icon :name="store.simMode ? 'stop' : 'run'" size="14"/>
            </button>
            <!-- 视图切换：三维仿真 / HMI人机交互屏（企业实时运行大屏） -->
            <button class="rbtn view-switch" :class="{ on: store.overviewOn }" @click="actions.toggleOverview()"
                   >
              <Icon :name="store.overviewOn ? 'cube' : 'eye'"/><span>{{ store.overviewOn ? t('三维仿真') : t('HMI人机交互屏') }}</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <!-- 刷新视角 / 自动环视 已移至 3D 场景左侧竖排展示 -->
            <button class="rbtn" :class="{ on: store.fullscreenOn }" @click="store.toggleFullscreen()" :title="t('全屏显示')">
              <Icon name="fullscreen"/><span>{{ store.fullscreenOn ? t('退出全屏') : t('全屏') }}</span>
            </button>
          </div>
        </template>
        <!-- ============ 流程编排态：编排工具 ============ -->
        <template v-else-if="view === 'edit'">
          <!-- 仿真（运行/退出）按钮仅在三维仿真 · HMI 大屏下展示：编排画布不做仿真态切换
               （编排态要进 / 退仿真仍可用「仿真」菜单或 Ctrl+Enter） -->
          <div class="rbtns">
            <!-- 编排手动保存：改动只置「未保存」标记，点此按钮（或 Ctrl+S）才写入本地存档 + 服务端 designs/flow。
                 仿真模式下的编辑一律不落盘（退出仿真后恢复），故禁用并显式提示。
                 未保存状态不在按钮上呈现（无呼吸点 / 无状态文案），统一由「流程编排」页签标题右侧的 * 表示。 -->
            <button class="rbtn save-btn"
                    :disabled="store.simMode || !store.schemeDirty"
                    @click="actions.saveScheme()"
                    :title="store.simMode ? t('仿真模式下的改动不会保存，退出仿真后自动恢复') : t('保存编排改动（Ctrl+S，本地存档 + 服务端）')">
              <Icon name="save"/><span>{{ t('保存') }}</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" :disabled="!store.canUndo" @click="store.undo()">
              <Icon name="undo"/><span>{{ t('撤销') }}</span>
            </button>
            <button class="rbtn" :disabled="!store.canRedo" @click="store.redo()">
              <Icon name="redo"/><span>{{ t('重做') }}</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" @click="actions.autoLayoutScheme()">
              <Icon name="grid"/><span>{{ t('自动布局') }}</span>
            </button>
            <button class="rbtn" @click="actions.flowZoomBtn(1.1)" :title="t('放大画布')">
              <Icon name="zoomIn"/><span>{{ t('放大') }}</span>
            </button>
            <button class="rbtn" @click="actions.flowZoomBtn(0.9)" :title="t('缩小画布')">
              <Icon name="zoomOut"/><span>{{ t('缩小') }}</span>
            </button>
            <button class="rbtn" @click="actions.flowFit()" :title="t('适配全部节点')">
              <Icon name="fit"/><span>{{ t('适配视图') }}</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button v-if="hasTemplate('long')" class="rbtn" @click="actions.loadExample('long')">
              <Icon name="flow"/><span>{{ t('长流程模板') }}</span>
            </button>
            <button v-if="hasTemplate('short')" class="rbtn" @click="actions.loadExample('short')">
              <Icon name="process"/><span>{{ t('短流程模板') }}</span>
            </button>
            <button class="rbtn" @click="actions.clearScheme()" :title="t('清空编排画布')">
              <Icon name="trash"/><span>{{ t('清空画布') }}</span>
            </button>
          </div>
        </template>
        <!-- ============ 数据分析 ============ -->
        <template v-else-if="view === 'data'">
          <span class="ribbon-title">{{ t('数据分析') }}</span>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" @click="actions.dataRefresh()">
              <Icon name="refresh"/><span>{{ t('刷新数据') }}</span>
            </button>
          </div>
          <!-- AI 分析入口已下沉到 DataView 内部视图 tab，顶部工具栏不再重复展示 -->
        </template>
        <!-- ============ AI 群控：工具栏已下沉到 PID·EKF 控制台内部（含标题/状态/操作），顶部工具栏不再渲染 ============ -->
        <template v-else-if="view === 'group'">
        </template>
        <!-- ============ CEA & CCER 行情 ============ -->
        <template v-else-if="view === 'market'">
          <!-- 页签切换已移到视图内部二级菜单，这里仅保留当前页签对应的功能 -->
          <div class="rbtns">
            <!-- 行情页签功能 -->
            <template v-if="actions.marketTabOn() === 'market'">
              <button class="rbtn" @click="actions.marketRefresh()" :title="t('刷新行情数据')">
                <Icon name="refresh"/><span>{{ t('刷新行情') }}</span>
              </button>
              <button class="rbtn" :class="{ on: actions.marketInstrument() === 'cea' }" @click="actions.marketSwitch('cea')">
                <Icon name="compare"/><span>{{ t('CEA 日K') }}</span>
              </button>
              <button class="rbtn" :class="{ on: actions.marketInstrument() === 'ccer' }" @click="actions.marketSwitch('ccer')">
                <Icon name="compare"/><span>{{ t('CCER 均价') }}</span>
              </button>
              <button class="rbtn" :class="{ on: actions.marketForecastOn() }" @click="actions.marketForecast()">
                <Icon name="eye"/><span>{{ t('预测叠加') }}</span>
              </button>
            </template>
            <!-- 台账页签功能 -->
            <template v-else>
              <button class="rbtn" @click="actions.marketLedgerRefresh()">
                <Icon name="refresh"/><span>{{ t('刷新台账') }}</span>
              </button>
            </template>
            <button class="rbtn" @click="actions.carbonReport()">
              <Icon name="report"/><span>{{ t('生成碳资产报告') }}</span>
            </button>
          </div>
        </template>
        <!-- ============ 碳排核算 ============ -->
        <template v-else-if="view === 'calc'">
        </template>
        <!-- ============ 能流分析 ============ -->
        <template v-else-if="view === 'energy'">
        </template>
        <!-- ============ 能碳一体机管理：工具栏已下沉到视图内部，顶部工具栏不再重复展示 ============ -->
        <template v-else-if="view === 'box'">
        </template>
      </div>
    </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import Icon from './Icon.vue'
import { t } from '../i18n'

const props = defineProps({
  actions: { type: Object, required: true },
})

const store = useSimStore()

// 当前场景是否提供该模板 id：编排工具条的模板按钮据此显隐
// （非钢场景没有长/短流程，写死显示会出现「点了没反应」的按钮）
function hasTemplate(id) {
  // 优先使用已加载的包内模板；若尚未加载（异步空窗期），回退到场景元信息的 routes/defaultRoute
  const fromTemplates = (store.sceneTemplates || []).some((t) => t.id === id || t.route === id)
  if (fromTemplates) return true
  const routes = store.scenePack?.meta?.routes || store.sceneIndex?.find((s) => s.id === store.sceneId)?.routes
  return (routes || []).includes(id)
}

// 当前工具栏所属视图：流程编排 / 工况数据分析 / 碳资产管理 / 碳排核算 / 能流分析 / 能碳一体机 / 数字孪生
// 流程编排：仅当编排画布标签在前台（flowEditing）时渲染编排工具条；
// 编排态切到三维仿真 / 其它标签时按该视图渲染其工具条
const view = computed(() => {
  if (store.flowEditing) return 'edit'
  if (store.dataViewOn) return 'data'
  if (store.aiGroupOn) return 'group'
  if (store.carbonMarketOn) return 'market'
  if (store.carbonCalcOn) return 'calc'
  if (store.energyFlowOn) return 'energy'
  if (store.boxManageOn) return 'box'
  return 'twin'
})

</script>

<style scoped>
/* 关闭按钮：非数字孪生态（含流程编排）视图工具栏最右侧，点击关闭当前视图返回数字孪生 */
/* 工具条内的视图名：与面板头同级（字号 13 / 600），左右内边距与按钮组同档 */
.ribbon-title {
  flex: 0 0 auto;
  padding: 0 var(--sp-2) 0 var(--sp-3);
  font-size: var(--fs-h);
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
}
/* 视图切换按钮（三维仿真 / HMI人机交互屏）：置于仿真启动旁，选中态高亮强调。
   UI 规则：选中态背景非白色，不再绘制边框（border 透明保留占位） */
.view-switch { border: 1px solid var(--border); }
.view-switch.on { background: var(--accent); color: #fff; border-color: transparent; }
.view-switch.on:hover { background: var(--accent-d); color: #fff; }
.app.sim-dark .view-switch.on { background: var(--accent); border-color: transparent; }
.app.sim-dark .view-switch.on:hover { background: var(--accent-d); }
/* 编排「保存」按钮（手动保存）：未保存状态改由「流程编排」页签标题右侧的 * 标示，按钮本身不再做状态提示 */
</style>
