<template>
  <!-- 工具条（独立行：位于顶部菜单条下方、3D 视图/编排画布上方，横贯全宽，普通/编排态浅色、仿真态深色）
       按当前激活视图渲染各自工具栏：数字孪生 / 流程编排 / 工况数据分析 / CEA 行情 / 碳排核算 / 能流分析 / 能碳一体机 -->
  <div class="ribbon">
      <div class="ribbon-body">
        <!-- ============ 数字孪生（默认）：运行仿真 + 流程编排 + 视角工具 ============ -->
        <template v-if="view === 'twin'">
          <div class="rbtns">
            <button class="rbtn sim-btn" :class="{ on: store.simMode }" @click="actions.onSimToggle()"
                    :title="store.simMode ? t('退出仿真') : t('运行仿真')">
              <Icon :name="store.simMode ? 'stop' : 'run'" size="14"/>
            </button>
            <!-- 视图切换：三维仿真 / HMI人机交互屏（企业实时运行大屏） -->
            <button class="rbtn view-switch" :class="{ on: store.overviewOn }" @click="actions.toggleOverview()"
                    :title="store.overviewOn ? t('切换到三维仿真场景') : t('切换到HMI人机交互屏（企业实时运行情况）')">
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
          <div class="rbtns">
            <button class="rbtn sim-btn" :class="{ on: store.simMode }" @click="actions.onSimToggle()"
                    :title="store.simMode ? t('退出仿真') : t('运行仿真')">
              <Icon :name="store.simMode ? 'stop' : 'run'" size="14"/>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn save-btn" :class="{ on: store.schemeDirty }" :disabled="store.simMode"
                    @click="actions.saveFlow()" :title="t('保存编排方案并生效（应用到孪生场景与仿真计算）')">
              <Icon name="save"/><span>{{ t('保存') }}</span><i v-if="store.schemeDirty" class="dirty-dot" :title="t('有未保存的修改')"></i>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" :disabled="!store.canUndo" @click="store.undo()" :title="t('撤销（Ctrl+Z）')">
              <Icon name="undo"/><span>{{ t('撤销') }}</span>
            </button>
            <button class="rbtn" :disabled="!store.canRedo" @click="store.redo()" :title="t('重做（Ctrl+Y）')">
              <Icon name="redo"/><span>{{ t('重做') }}</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" @click="actions.autoLayoutScheme()" :title="t('自动排列画布节点')">
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
            <button class="rbtn" @click="actions.loadExample('long')" :title="t('载入长流程炼钢模板')">
              <Icon name="flow"/><span>{{ t('长流程模板') }}</span>
            </button>
            <button class="rbtn" @click="actions.loadExample('short')" :title="t('载入短流程炼钢模板')">
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
            <button class="rbtn" @click="actions.dataRefresh()" :title="t('重新拉取工况数据')">
              <Icon name="refresh"/><span>{{ t('刷新数据') }}</span>
            </button>
          </div>
          <!-- AI 分析入口已下沉到 DataView 内部视图 tab，顶部工具栏不再重复展示 -->
        </template>
        <!-- ============ AI 群控：与数据分析同布局，仅参数优化（无 tab，训练控制/进度在右侧面板与中间内容区） ============ -->
        <template v-else-if="view === 'group'">
          <span class="ribbon-title">{{ t('AI群控') }}</span>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" @click="actions.dataRefresh()" :title="t('重新拉取工况数据')">
              <Icon name="refresh"/><span>{{ t('刷新数据') }}</span>
            </button>
          </div>
          <!-- 参数优化（遗传算法 / 粒子群 / 强化学习）训练控制统一在右侧属性面板，中间内容区实时展示收敛进度与最优参数 -->
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
              <button class="rbtn" :class="{ on: actions.marketInstrument() === 'cea' }" @click="actions.marketSwitch('cea')" :title="t('切换为 CEA 日 K 行情')">
                <Icon name="compare"/><span>{{ t('CEA 日K') }}</span>
              </button>
              <button class="rbtn" :class="{ on: actions.marketInstrument() === 'ccer' }" @click="actions.marketSwitch('ccer')" :title="t('切换为 CCER 均价行情')">
                <Icon name="compare"/><span>{{ t('CCER 均价') }}</span>
              </button>
              <button class="rbtn" :class="{ on: actions.marketForecastOn() }" @click="actions.marketForecast()" :title="t('叠加未来走势预测曲线')">
                <Icon name="eye"/><span>{{ t('预测叠加') }}</span>
              </button>
            </template>
            <!-- 台账页签功能 -->
            <template v-else>
              <button class="rbtn" @click="actions.marketLedgerRefresh()" :title="t('刷新企业台账与策略数据')">
                <Icon name="refresh"/><span>{{ t('刷新台账') }}</span>
              </button>
            </template>
            <button class="rbtn" @click="actions.carbonReport()" :title="t('生成碳资产分析报告（Markdown）')">
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
      <!-- 关闭：非数字孪生态（含流程编排）显示在最右侧，点击关闭当前视图返回数字孪生 -->
      <button v-if="view !== 'twin'" class="rbtn close-btn" @click="actions.closeView()" :title="t('关闭当前视图，返回数字孪生场景')">
        <Icon name="close"/><span>{{ t('关闭') }}</span>
      </button>
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

// 当前工具栏所属视图：数字孪生 / 流程编排 / 工况数据分析 / 碳资产管理 / 碳排核算 / 能流分析 / 能碳一体机
const view = computed(() => {
  if (store.editMode) return 'edit'
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
.ribbon-title {
  flex: 0 0 auto;
  padding: 0 4px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: var(--text);
  white-space: nowrap;
}
.close-btn {
  flex: 0 0 auto; margin-left: auto; padding: 0 12px;
  color: var(--muted); white-space: nowrap;
}
.close-btn:hover { color: var(--red); background: var(--panel-3); }
/* 视图切换按钮（三维仿真 / HMI人机交互屏）：置于仿真启动旁，选中态高亮强调。
   UI 规则：选中态背景非白色，不再绘制边框（border 透明保留占位） */
.view-switch { border: 1px solid var(--border); }
.view-switch.on { background: var(--accent); color: #fff; border-color: transparent; }
.view-switch.on:hover { background: var(--accent-d); color: #fff; }
.app.sim-dark .view-switch.on { background: var(--accent); border-color: transparent; }
.app.sim-dark .view-switch.on:hover { background: var(--accent-d); }
/* 编排模式「保存」按钮：有未保存修改时 accent 高亮提示，未保存红点常显 */
.save-btn { border: 1px solid var(--border); }
.save-btn.on { background: var(--accent); color: #fff; border-color: transparent; }
.save-btn.on:hover { background: var(--accent-d); color: #fff; }
.app.sim-dark .save-btn.on { background: var(--accent); border-color: transparent; }
.app.sim-dark .save-btn.on:hover { background: var(--accent-d); }
.save-btn:disabled { opacity: 0.55; cursor: not-allowed; }
.dirty-dot {
  display: inline-block; width: 7px; height: 7px; margin-left: 5px;
  border-radius: 50%; background: var(--red, #e5484d);
  box-shadow: 0 0 0 1.5px #fff;
}
</style>
