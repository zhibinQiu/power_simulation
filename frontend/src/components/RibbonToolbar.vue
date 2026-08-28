<template>
  <!-- 工具条（独立行：位于顶部菜单条下方、3D 视图/编排画布上方，横贯全宽，普通/编排态浅色、仿真态深色）
       按当前激活视图渲染各自工具栏：数字孪生 / 流程编排 / 工况数据分析 / CEA 行情 / 碳排核算 / 能流分析 / 能碳一体机 -->
  <div class="ribbon">
      <div class="ribbon-body">
        <!-- ============ 数字孪生（默认）：运行仿真 + 流程编排 + 视角工具 ============ -->
        <template v-if="view === 'twin'">
          <div class="rbtns">
            <button class="rbtn sim-btn" :class="{ on: store.simMode }" @click="actions.onSimToggle()"
                    :title="store.simMode ? '退出仿真' : '运行仿真'">
              <Icon :name="store.simMode ? 'stop' : 'run'" size="14"/>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" @click="actions.onResetView()" title="刷新视角：重置为园区俯瞰">
              <Icon name="target"/><span>刷新视角</span>
            </button>
            <button class="rbtn" :class="{ on: store.autoRotate }" @click="actions.toggleAuto()" title="相机自动环绕旋转">
              <Icon name="rotate"/><span>自动环视</span>
            </button>
            <button class="rbtn" :class="{ on: store.patrolOn }" @click="actions.togglePatrol()" title="虚拟巡视：机器狗沿工艺旁地面巡视完整流程">
              <Icon name="patrol"/><span>虚拟巡视</span>
            </button>
            <button class="rbtn" :class="{ on: store.fullscreenOn }" @click="store.toggleFullscreen()" title="全屏显示">
              <Icon name="fullscreen"/><span>{{ store.fullscreenOn ? '退出全屏' : '全屏' }}</span>
            </button>
          </div>
        </template>
        <!-- ============ 流程编排态：编排工具 ============ -->
        <template v-else-if="view === 'edit'">
          <div class="rbtns">
            <button class="rbtn sim-btn" :class="{ on: store.simMode }" @click="actions.onSimToggle()"
                    :title="store.simMode ? '退出仿真' : '运行仿真'">
              <Icon :name="store.simMode ? 'stop' : 'run'" size="14"/>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" :disabled="!store.canUndo" @click="store.undo()" title="撤销（Ctrl+Z）">
              <Icon name="undo"/><span>撤销</span>
            </button>
            <button class="rbtn" :disabled="!store.canRedo" @click="store.redo()" title="重做（Ctrl+Y）">
              <Icon name="redo"/><span>重做</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" @click="actions.autoLayoutScheme()" title="自动排列画布节点">
              <Icon name="grid"/><span>自动布局</span>
            </button>
            <button class="rbtn" @click="actions.flowZoomBtn(1.1)" title="放大画布">
              <Icon name="zoomIn"/><span>放大</span>
            </button>
            <button class="rbtn" @click="actions.flowZoomBtn(0.9)" title="缩小画布">
              <Icon name="zoomOut"/><span>缩小</span>
            </button>
            <button class="rbtn" @click="actions.flowFit()" title="适配全部节点">
              <Icon name="fit"/><span>适配视图</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" @click="actions.loadExample('long')" title="载入长流程炼钢模板">
              <Icon name="flow"/><span>长流程模板</span>
            </button>
            <button class="rbtn" @click="actions.loadExample('short')" title="载入短流程炼钢模板">
              <Icon name="process"/><span>短流程模板</span>
            </button>
            <button class="rbtn" @click="actions.clearScheme()" title="清空编排画布">
              <Icon name="trash"/><span>清空画布</span>
            </button>
          </div>
        </template>
        <!-- ============ 工况数据分析 ============ -->
        <template v-else-if="view === 'data'">
          <span class="ribbon-title">数据分析与策略</span>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" @click="actions.dataRefresh()" title="重新拉取工况数据">
              <Icon name="refresh"/><span>刷新数据</span>
            </button>
          </div>
          <!-- AI 分析入口已下沉到 DataView 内部视图 tab，顶部工具栏不再重复展示 -->
        </template>
        <!-- ============ CEA & CCER 行情 ============ -->
        <template v-else-if="view === 'market'">
          <!-- 页签切换已移到视图内部二级菜单，这里仅保留当前页签对应的功能 -->
          <div class="rbtns">
            <!-- 行情页签功能 -->
            <template v-if="actions.marketTabOn() === 'market'">
              <button class="rbtn" @click="actions.marketRefresh()" title="刷新行情数据">
                <Icon name="refresh"/><span>刷新行情</span>
              </button>
              <button class="rbtn" :class="{ on: actions.marketInstrument() === 'cea' }" @click="actions.marketSwitch('cea')" title="切换为 CEA 日 K 行情">
                <Icon name="compare"/><span>CEA 日K</span>
              </button>
              <button class="rbtn" :class="{ on: actions.marketInstrument() === 'ccer' }" @click="actions.marketSwitch('ccer')" title="切换为 CCER 均价行情">
                <Icon name="compare"/><span>CCER 均价</span>
              </button>
              <button class="rbtn" :class="{ on: actions.marketForecastOn() }" @click="actions.marketForecast()" title="叠加未来走势预测曲线">
                <Icon name="eye"/><span>预测叠加</span>
              </button>
            </template>
            <!-- 台账页签功能 -->
            <template v-else>
              <button class="rbtn" @click="actions.marketLedgerRefresh()" title="刷新企业台账与策略数据">
                <Icon name="refresh"/><span>刷新台账</span>
              </button>
            </template>
            <button class="rbtn" @click="actions.carbonReport()" title="生成碳资产分析报告（Markdown）">
              <Icon name="report"/><span>生成碳资产报告</span>
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
      <!-- 关闭：非数字孪生/编排态显示在最右侧，点击关闭当前视图返回数字孪生 -->
      <button v-if="view !== 'twin' && view !== 'edit'" class="rbtn close-btn" @click="actions.closeView()" title="关闭当前视图，返回数字孪生场景">
        <Icon name="close"/><span>关闭</span>
      </button>
      <!-- 亮度：点击按钮弹出滑条（仅数字孪生态显示） -->
      <div v-if="view === 'twin'" class="bright-wrap">
        <button class="rbtn" :class="{ on: showBrightness }" @click="showBrightness = !showBrightness" title="画面亮度（点击展开滑条）">
          <Icon name="brightness"/><span>亮度</span>
        </button>
        <div v-if="showBrightness" class="bright-pop">
          <div class="bp-title">画面亮度</div>
          <div class="bp-row">
            <span class="rslider-label">暗</span>
            <input type="range" class="rslider" min="0.3" max="2.5" step="0.05"
                   :value="store.brightness" @input="store.setBrightness(+($event.target.value))" />
            <span class="rslider-label">亮</span>
            <span class="rslider-val">{{ (store.brightness * 100).toFixed(0) }}%</span>
          </div>
        </div>
      </div>
    </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import Icon from './Icon.vue'

const props = defineProps({
  actions: { type: Object, required: true },
})

const store = useSimStore()
const showBrightness = ref(false)

// 当前工具栏所属视图：数字孪生 / 流程编排 / 工况数据分析 / 碳资产管理 / 碳排核算 / 能流分析 / 能碳一体机
const view = computed(() => {
  if (store.editMode) return 'edit'
  if (store.dataViewOn) return 'data'
  if (store.carbonMarketOn) return 'market'
  if (store.carbonCalcOn) return 'calc'
  if (store.energyFlowOn) return 'energy'
  if (store.boxManageOn) return 'box'
  return 'twin'
})

// 点击亮度弹层以外区域关闭
function onDocClick(e) {
  if (!e.target.closest('.bright-wrap')) showBrightness.value = false
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>

<style scoped>
/* 关闭按钮：非数字孪生/编排态视图工具栏最右侧，点击关闭当前视图返回数字孪生 */
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
.close-btn:hover { color: #e05252; background: var(--panel-3); }
</style>
