<template>
  <!-- 工具条（独立行：位于顶部菜单条下方、3D 视图/编排画布上方，横贯全宽，普通/编排态浅色、仿真态深色）
       按当前激活视图渲染各自工具栏：数字孪生 / 流程编排 / 监测数据 / CEA 行情 / 碳排核算 / 能流分析 / 能碳一体机 -->
  <div class="ribbon">
      <div class="ribbon-body">
        <!-- ============ 数字孪生（默认）：运行仿真 + 流程编排 + 视角工具 ============ -->
        <template v-if="view === 'twin'">
          <div class="rbtns">
            <button class="rbtn primary" :class="{ on: store.simMode }" @click="actions.onSimToggle()">
              <Icon :name="store.simMode ? 'stop' : 'run'"/>
              <span>{{ store.simMode ? '退出仿真' : '运行仿真' }}</span>
            </button>
            <button class="rbtn primary" @click="actions.onToggleEdit()">
              <Icon name="pencil"/>
              <span>流程编排</span>
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
            <button class="rbtn primary" :class="{ on: store.simMode }" @click="actions.onSimToggle()">
              <Icon :name="store.simMode ? 'stop' : 'run'"/>
              <span>{{ store.simMode ? '退出仿真' : '运行仿真' }}</span>
            </button>
            <button class="rbtn primary" :class="{ on: store.editMode }" @click="actions.onToggleEdit()">
              <Icon name="pencil"/>
              <span>完成编排</span>
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
            <button class="rbtn" @click="actions.loadExample('long')" title="载入长流程炼钢示例">
              <Icon name="flow"/><span>长流程示例</span>
            </button>
            <button class="rbtn" @click="actions.loadExample('short')" title="载入短流程炼钢示例">
              <Icon name="process"/><span>短流程示例</span>
            </button>
            <button class="rbtn" @click="actions.clearScheme()" title="清空编排画布">
              <Icon name="trash"/><span>清空画布</span>
            </button>
          </div>
        </template>
        <!-- ============ 监测数据查看 ============ -->
        <template v-else-if="view === 'data'">
          <div class="rbtns">
            <button class="rbtn primary" @click="actions.closeView()" title="关闭当前视图，返回数字孪生场景">
              <Icon name="scene3d"/><span>返回数字孪生</span>
            </button>
            <button class="rbtn" @click="actions.dataRefresh()" title="重新拉取监测数据">
              <Icon name="refresh"/><span>刷新数据</span>
            </button>
            <button class="rbtn" :class="{ on: store.fullscreenOn }" @click="store.toggleFullscreen()" title="全屏显示">
              <Icon name="fullscreen"/><span>{{ store.fullscreenOn ? '退出全屏' : '全屏' }}</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <span class="rbtn-label">监测数据查看</span>
        </template>
        <!-- ============ CEA & CCER 行情 ============ -->
        <template v-else-if="view === 'market'">
          <div class="rbtns">
            <button class="rbtn primary" @click="actions.closeView()" title="关闭当前视图，返回数字孪生场景">
              <Icon name="scene3d"/><span>返回数字孪生</span>
            </button>
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
            <button class="rbtn" :class="{ on: store.fullscreenOn }" @click="store.toggleFullscreen()" title="全屏显示">
              <Icon name="fullscreen"/><span>{{ store.fullscreenOn ? '退出全屏' : '全屏' }}</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <span class="rbtn-label">CEA &amp; CCER 行情</span>
        </template>
        <!-- ============ 碳排核算 ============ -->
        <template v-else-if="view === 'calc'">
          <div class="rbtns">
            <button class="rbtn primary" @click="actions.closeView()" title="关闭当前视图，返回数字孪生场景">
              <Icon name="scene3d"/><span>返回数字孪生</span>
            </button>
            <button class="rbtn" :class="{ on: store.fullscreenOn }" @click="store.toggleFullscreen()" title="全屏显示">
              <Icon name="fullscreen"/><span>{{ store.fullscreenOn ? '退出全屏' : '全屏' }}</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <span class="rbtn-label">碳排核算</span>
        </template>
        <!-- ============ 能流分析 ============ -->
        <template v-else-if="view === 'energy'">
          <div class="rbtns">
            <button class="rbtn primary" @click="actions.closeView()" title="关闭当前视图，返回数字孪生场景">
              <Icon name="scene3d"/><span>返回数字孪生</span>
            </button>
            <button class="rbtn" :class="{ on: store.fullscreenOn }" @click="store.toggleFullscreen()" title="全屏显示">
              <Icon name="fullscreen"/><span>{{ store.fullscreenOn ? '退出全屏' : '全屏' }}</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <span class="rbtn-label">能流分析</span>
        </template>
        <!-- ============ 能碳一体机管理 ============ -->
        <template v-else-if="view === 'box'">
          <div class="rbtns">
            <button class="rbtn primary" @click="actions.closeView()" title="关闭当前视图，返回数字孪生场景">
              <Icon name="scene3d"/><span>返回数字孪生</span>
            </button>
            <button class="rbtn" @click="actions.boxRefresh()" title="重新拉取能碳一体机数据">
              <Icon name="refresh"/><span>刷新数据</span>
            </button>
            <button class="rbtn" :class="{ on: store.fullscreenOn }" @click="store.toggleFullscreen()" title="全屏显示">
              <Icon name="fullscreen"/><span>{{ store.fullscreenOn ? '退出全屏' : '全屏' }}</span>
            </button>
          </div>
          <span class="rdiv"></span>
          <div class="rbtns">
            <button v-for="t in boxTabs" :key="t.id" class="rbtn" :class="{ on: actions.boxTabOn() === t.id }"
                    @click="actions.boxSwitchTab(t.id)">{{ t.label }}</button>
          </div>
          <span class="rdiv"></span>
          <span class="rbtn-label">能碳一体机管理</span>
        </template>
      </div>
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

// 能碳一体机管理页签（与 CarbonBoxView 内部保持一致）
const boxTabs = [
  { id: 'overview', label: '总览' },
  { id: 'devices', label: '设备管理' },
  { id: 'links', label: '设备关联' },
  { id: 'onboard', label: '盒子接入' },
  { id: 'realtime', label: '实时数据' },
  { id: 'guide', label: '接入指引' },
]

// 当前工具栏所属视图：数字孪生 / 流程编排 / 监测数据 / CEA 行情 / 碳排核算 / 能流分析 / 能碳一体机
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
/* 视图名标签：数字孪生以外各视图工具栏右侧的当前视图名称 */
.rbtn-label {
  display: inline-flex; align-items: center;
  height: 24px; padding: 0 10px; margin-left: 4px;
  border-left: 1px solid var(--line);
  font-size: 12px; letter-spacing: 1px;
  color: var(--muted); user-select: none;
  white-space: nowrap;
}
</style>
