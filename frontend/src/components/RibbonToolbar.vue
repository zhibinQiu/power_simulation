<template>
  <!-- 工具条（独立行：位于顶部菜单条下方、3D 视图/编排画布上方，横贯全宽，普通/编排态浅色、仿真态深色） -->
  <div class="ribbon">
      <div class="ribbon-body">
        <div class="rbtns">
          <button class="rbtn primary" :class="{ on: store.simMode }" @click="actions.onSimToggle()">
            <Icon :name="store.simMode ? 'stop' : 'run'"/>
            <span>{{ store.simMode ? '退出仿真' : '运行仿真' }}</span>
            </button>
            <button class="rbtn primary" :class="{ on: store.editMode }" @click="actions.onToggleEdit()">
            <Icon name="pencil"/>
            <span>{{ store.editMode ? '完成编排' : '流程编排' }}</span>
          </button>
        </div>
        <!-- 非编排态：数字孪生视角工具 -->
        <template v-if="!store.editMode">
          <span class="rdiv"></span>
          <div class="rbtns">
            <button class="rbtn" :class="{ on: store.autoRotate }" @click="actions.toggleAuto()" title="相机自动环绕旋转">
              <Icon name="rotate"/><span>自动环视</span>
            </button>
            <button class="rbtn" :class="{ on: store.patrolOn }" @click="actions.togglePatrol()" title="虚拟巡视">
              <Icon name="patrol"/><span>虚拟巡视</span>
            </button>
            <button class="rbtn" @click="actions.onResetView()" title="刷新视角：重置为园区俯瞰">
              <Icon name="target"/><span>刷新视角</span>
            </button>
            <button class="rbtn" :class="{ on: store.fullscreenOn }" @click="store.toggleFullscreen()" title="全屏显示">
              <Icon name="fullscreen"/><span>{{ store.fullscreenOn ? '退出全屏' : '全屏' }}</span>
            </button>
            <button class="rbtn" :disabled="!store.resultForView" @click="$emit('panorama')" title="全景数据：多标准碳核算结果对比">
              <Icon name="panorama"/><span>全景数据</span>
            </button>
          </div>
        </template>
        <!-- 编排态：数字孪生工具替换为编排工具 -->
        <template v-else>
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
      </div>
      <!-- 亮度：点击按钮弹出滑条（仅数字孪生态显示） -->
      <div v-if="!store.editMode" class="bright-wrap">
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
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import Icon from './Icon.vue'

const props = defineProps({
  actions: { type: Object, required: true },
})
defineEmits(['panorama'])

const store = useSimStore()
const showBrightness = ref(false)

// 点击亮度弹层以外区域关闭
function onDocClick(e) {
  if (!e.target.closest('.bright-wrap')) showBrightness.value = false
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))
</script>
