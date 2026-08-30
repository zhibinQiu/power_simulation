<template>
  <div class="area-scene">
    <div ref="host" v-show="!view2D" class="scene-host"></div>
    <Twin2DView v-if="view2D" class="scene-host"/>

    <!-- 左上角工具组（图标按钮）：2D/3D 切换 / 亮度 / 刷新视角 / 自动环视 -->
    <div v-if="!store.editMode" class="twin-left-tools" :style="{ top: store.scheme.activeGroupId ? '58px' : '12px' }">
      <button type="button" class="twin-tool-btn" :class="{ on: view2D }" @click="toggleView2D()" :title="view2D ? t('切换到 3D 数字孪生视图') : t('切换到 2D 工艺流程图（ISA-101 人机界面）')">
        <Icon :name="view2D ? 'scene3d' : 'front'"/>
      </button>
      <button type="button" class="twin-tool-btn" :class="{ on: showBrightness }" @click.stop="showBrightness = !showBrightness" :title="t('画面亮度（点击展开滑条）')">
        <Icon name="brightness"/>
      </button>
      <button type="button" class="twin-tool-btn" @click="store.resetView()" :title="t('刷新视角：重置为园区俯瞰')">
        <Icon name="target"/>
      </button>
      <button type="button" class="twin-tool-btn" :class="{ on: store.autoRotate }" @click="store.setAutoRotate(!store.autoRotate)" :title="t('相机自动环绕旋转')">
        <Icon name="rotate"/>
      </button>
      <div v-if="showBrightness" class="twin-bright-pop" @click.stop>
        <div class="twin-bp-title">{{ t('画面亮度') }}</div>
        <div class="twin-bp-row">
          <span class="twin-bp-label">{{ t('暗') }}</span>
          <input type="range" class="twin-bp-range" min="0.3" max="2.5" step="0.05"
                 :value="store.brightness" @input="store.setBrightness(+($event.target.value))" />
          <span class="twin-bp-label">{{ t('亮') }}</span>
          <span class="twin-bp-val">{{ (store.brightness * 100).toFixed(0) }}%</span>
        </div>
      </div>
    </div>

    <!-- 3D 小组子场景：左上角返回顶层浮层（非编辑态下点击小组标签进入） -->
    <div v-if="!store.editMode && store.scheme.activeGroupId" class="group-scene-bar">
      <button type="button" class="gs-back" @click="store.exitGroup()">{{ t('← 返回顶层') }}</button>
      <span class="gs-title">▦ {{ groupSceneName }}</span>
    </div>

    <!-- 全屏模式浮动工具（右上角）：全屏时顶栏/工具栏已隐藏，「HMI人机交互屏」切换与「退出全屏」入口移至内容区 -->
    <div v-if="store.fullscreenOn" class="twin-fs-tools">
      <button type="button" class="fs-tool-btn" :title="t('切换到 HMI人机交互屏')" @click="store.toggleOverview()">
        <Icon name="eye" :size="16" :stroke="1.6"/>
      </button>
      <button type="button" class="fs-tool-btn" :title="t('退出全屏')" @click="store.toggleFullscreen()">
        <Icon name="fullscreen" :size="16" :stroke="1.6"/>
      </button>
    </div>

    <!-- 点击 3D 场景中模型旁的小铭牌 → 右侧统一展示该工序实例的属性面板（无浮窗冗余） -->

    <div v-if="!ok" class="scene-fallback">
      <div class="fb-title">{{ t('3D 场景无法初始化') }}</div>
      <div class="fb-msg">{{ lastErr || t('当前环境不支持 WebGL，无法渲染 3D 场景。') }}</div>
      <div class="fb-hint">{{ t('请使用支持 WebGL 的现代浏览器（Chrome / Edge / Firefox），并确认未禁用“硬件加速”。') }}</div>
      <button class="fb-retry" type="button" @click="retry">{{ t('重试') }}</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { t } from '../i18n'
import { useSimStore } from '../stores/sim'
import { TwinScene } from '../three/scene'
import Icon from './Icon.vue'
import Twin2DView from './Twin2DView.vue'

const store = useSimStore()
const host = ref(null)
const ok = ref(true)
const lastErr = ref('')
const view2D = ref(false)
let scene = null
let ro = null
let introDone = false

// 2D/3D 视图切换：2D 视图是全新画布（独立工艺流程图），切换时暂停/恢复 3D 渲染循环
function toggleView2D() {
  view2D.value = !view2D.value
  if (!scene) return
  scene.setPaused(view2D.value || store.editMode || document.hidden)
  if (!view2D.value) {
    // 从 2D 返回 3D：canvas 刚恢复可见，等布局完成后重建场景避免 0 尺寸 NaN
    nextTick(() => { if (scene) { scene.resize(); scene.setPaused(store.editMode || document.hidden) } })
  }
}

function rebuildScene() {
  if (!scene || !store.ready || !store.model || !store.model.units || !store.model.units.length) return
  try {
    // 非编辑态下若处于某小组子场景（activeGroupId），3D 场景以该小组子场景模式重建
    const gid = (!store.editMode && store.scheme.activeGroupId) ? store.scheme.activeGroupId : null
    scene.buildModel(store.model, store.resultForView, gid ? { groupScene: gid } : undefined)
    scene.setAutoRotate(store.autoRotate)
  } catch (e) {
    console.error('buildModel failed:', e)
    ok.value = false
    lastErr.value = (e && e.message) ? e.message : String(e)
  }
}

function initScene() {
  try {
    scene = new TwinScene(host.value, { envMode: store.envMode })
    ok.value = true
    lastErr.value = ''
    // dev 模式暴露场景实例，便于自动化验证/截图（生产构建不包含）
    if (import.meta.env.DEV) window.__twinScene = scene
    // 点击模型旁的小铭牌 → 选中该工序实例，右侧统一显示实例属性面板
    scene.onSelectUnit = (id) => { store.pickUnit(id) }
    scene.onMiss = () => {}   // 点击场景空白：无浮窗需关闭
    // 单击小组标签/底座：聚焦（相机平滑移动到小组 + 右侧展示小组信息）
    scene.onFocusGroup = (gid) => { store.selectFlowGroup(gid); scene.focusGroup(gid) }
    // 双击小组标签/底座：进入该小组的 3D 子场景（成员展开为独立工序模型）
    scene.onSelectGroup = (gid) => { store.enterGroup(gid) }
    scene.onSelectDevice = (devId) => store.openDeviceDetail(devId)
    scene.onSelectFlow = (flowId) => { store.selectFlow(flowId); scene.focusFlow(flowId) }
    window.addEventListener('resize', onResize)
    // 容器尺寸变化（如收缩/展开左右侧栏导致中间区变宽）也要重设画布
    ro = new ResizeObserver(() => onResize())
    ro.observe(host.value)
    rebuildScene()
  } catch (e) {
    console.error('3D init failed:', e)
    ok.value = false
    lastErr.value = (e && e.message) ? e.message : String(e)
  }
}

function retry() {
  if (scene) { scene.dispose(); scene = null }
  ok.value = true
  lastErr.value = ''
  initScene()
}

onMounted(() => {
  initScene()
})

let resizeRaf = null
function onResize() {
  if (resizeRaf) return
  resizeRaf = requestAnimationFrame(() => {
    scene && scene.resize()
    resizeRaf = null
  })
}

watch(() => store.ready, () => { if (store.ready) rebuildScene() })
// 编辑态下 canvas 隐藏，避免在 0x0 尺寸下重建导致相机投影矩阵 NaN；退出编辑态由 editMode watch 统一重建
watch(() => store.sceneRev, () => { if (!store.editMode) rebuildScene() })

// 3D 小组子场景：进入/退出时同步视角（进入适配小组布局，返回播放全景动画）
watch(() => store.scheme.activeGroupId, (gid) => {
  if (!scene || store.editMode) return
  if (gid) scene.focusScene()
  else scene.resetView()
})
const groupSceneName = computed(() => {
  const g = (store.scheme.groups || []).find((x) => x.id === store.scheme.activeGroupId)
  return g ? g.name : t('设备小组')
})

watch(() => store.resultForView, (r) => {
  if (scene && r && r.units) scene.updateHeat(r)
})

// 策略仿真结果 → 更新 3D 标签显示优化前/优化后
watch(() => store.strategy, (r) => {
  if (scene && r && r.units) scene.updateStrategyDeltas(r)
})
// 仿真模式下实时当前结果变化（属性修改/策略使用）→ 同步更新 3D 标签
watch(() => store.simCurrent, (r) => {
  if (scene && r && r.units) scene.updateStrategyDeltas(r)
})

// 页面隐藏时暂停渲染循环，减少后台 CPU/GPU 占用；恢复可见或离开编排态时继续
function onVis() { if (scene) scene.setPaused(view2D.value || store.editMode || document.hidden) }
document.addEventListener('visibilitychange', onVis)

watch(() => store.editMode, async (v) => {
  if (!scene) return
  scene.setPaused(view2D.value || v || document.hidden)
  if (!v) {
    // 从编排态退出：canvas 刚从 display:none 变为可见，需要等 DOM 布局完成、
    // resize 恢复渲染器尺寸后，再重建 3D 场景。
    // 否则 canvas 尺寸为 0x0 时 rebuildScene 会导致相机投影矩阵 NaN 而黑屏。
    await nextTick()
    if (!scene) return
    scene.resize()
    rebuildScene()
  }
})
watch(() => store.selectedUnitId, (id) => { scene && scene.setSelected(id) })
watch(() => store.autoRotate, (v) => { scene && scene.setAutoRotate(v) })
watch(() => store.brightness, (v) => { scene && scene.setBrightness(v) })

// 顶栏「重置视图」按钮：重置 3D 相机视角
watch(() => store.viewResetNonce, () => { if (scene) scene.resetView() })

// 顶栏「环境」切换：虚空 / 沙漠等场景环境
watch(() => store.envNonce, () => { if (scene) scene.setEnvironment(store.envMode) })

// 任意选中（左栏点击 或 3D 点击）→ 相机平滑聚焦拉近到该要素
watch(() => store.focusNonce, () => {
  if (!scene) return
  if (store.focusKind === 'device') scene.focusDevice(store.focusId)
  else if (store.focusKind === 'unit') scene.focusUnit(store.focusId)
})

// 工具条/菜单「俯视/正视/侧视/聚焦/全景」→ 相机以指定视角查看选中工序
watch(() => store.viewNonce, () => {
  if (!scene || !store.viewId) return
  scene.viewUnit(store.viewId, store.viewMode)
})
watch(() => store.live, (l) => { scene && scene.updateLive(l) })

onBeforeUnmount(() => {
  document.removeEventListener('visibilitychange', onVis)
  document.removeEventListener('click', onBrightDocClick)
  window.removeEventListener('resize', onResize)
  if (ro) { ro.disconnect(); ro = null }
  if (scene) scene.dispose()
})

// 亮度弹层：点击外部关闭
const showBrightness = ref(false)
function onBrightDocClick(e) {
  if (showBrightness.value && !e.target.closest('.twin-left-tools')) showBrightness.value = false
}
onMounted(() => document.addEventListener('click', onBrightDocClick))
</script>

<style scoped>
/* 上下分屏：上部数字孪生 3D 场景，下部仿真前后对比面板 */
.area-scene { position: absolute; inset: 0; display: flex; flex-direction: column; }
/* 3D 场景占满剩余空间，对比面板按内容自适应高度 */
.scene-host { position: relative; flex: 1 1 0; min-height: 0; }

/* 左上角工具组 · 图标按钮竖排（亮度 / 刷新视角 / 自动环视） */
.twin-left-tools {
  position: absolute; left: 12px; z-index: 6; transition: top .15s;
  display: flex; flex-direction: column; gap: 6px;
}
.twin-tool-btn {
  display: flex; align-items: center; justify-content: center;
  width: 30px; height: 30px; padding: 0;
  background: var(--panel);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  cursor: pointer; color: var(--text);
  box-shadow: var(--shadow);
  transition: background .12s, color .12s, transform .12s;
}
/* UI 规则：hover/选中态背景非白色，不再绘制边框（border 透明保留占位） */
.twin-tool-btn:hover { background: var(--panel-2); color: var(--accent-d); border-color: transparent; }
.twin-tool-btn:active { transform: translateY(0); }
.twin-tool-btn.on { background: var(--accent); color: #fff; border-color: transparent; }
.twin-tool-btn.on:hover { background: var(--accent-d); color: #fff; }
.app.sim-dark .twin-tool-btn { background: var(--panel); border-color: var(--border); color: var(--text); box-shadow: var(--shadow); }
.app.sim-dark .twin-tool-btn:hover { background: var(--panel-3); color: #fff; border-color: transparent; }
.app.sim-dark .twin-tool-btn.on { background: var(--accent); color: #fff; border-color: transparent; }
.twin-bright-pop {
  position: absolute; top: 0; left: calc(100% + 8px); min-width: 190px; z-index: 90;
  background: var(--panel); color: var(--text); border: 1px solid var(--border); border-radius: var(--radius);
  box-shadow: var(--shadow); padding: 9px 11px;
}
.twin-bright-pop .twin-bp-title { font-size: 10px; color: var(--muted); letter-spacing: .5px; margin-bottom: 8px; }
.twin-bright-pop .twin-bp-row { display: flex; align-items: center; gap: 6px; }
.twin-bright-pop .twin-bp-range { flex: 1; min-width: 0; height: 4px; margin: 0; cursor: pointer; accent-color: var(--accent-d); }
.twin-bright-pop .twin-bp-label { font-size: 9px; color: var(--faint); flex: 0 0 auto; }
.twin-bright-pop .twin-bp-val { font-size: 10px; color: var(--muted); min-width: 30px; text-align: right; }
.app.sim-dark .twin-bright-pop { background: rgba(30, 33, 30, 0.95); border-color: rgba(255, 255, 255, 0.12); }
.app.sim-dark .twin-bright-pop .twin-bp-title { color: #A6A49C; }
.app.sim-dark .twin-bright-pop .twin-bp-label { color: #75746C; }
.app.sim-dark .twin-bright-pop .twin-bp-val { color: #C6C4BC; }

/* 3D 小组子场景 · 左上角返回顶层浮层（工具栏在场景外部独立成行，不再遮挡，恢复默认左上角位置） */
.group-scene-bar { position: absolute; top: 12px; left: 12px; z-index: 6; display: flex; align-items: center; gap: 10px; background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); padding: 6px 10px; box-shadow: var(--shadow); }
.gs-back {
  display: inline-flex; align-items: center; gap: 5px; height: 24px; padding: 0 9px;
  background: transparent; border: 1px solid var(--border); border-radius: var(--radius);
  cursor: pointer; color: var(--text); font-size: 11px; font-weight: 600; font-family: var(--ui);
  line-height: 1; white-space: nowrap;
  transition: background .1s, color .1s, border-color .1s;
}
.gs-back:hover { background: var(--panel-3); color: var(--text); border-color: var(--accent-d); }
.gs-back:active { background: var(--sel); }
.gs-title { font-size: 12px; font-weight: 600; color: var(--text); }

/* 全屏模式浮动工具（右上角）：切换 HMI人机交互屏 / 退出全屏（全屏时工具栏隐藏，入口移至内容区；按钮样式见 main.css .fs-tool-btn 统一） */
.twin-fs-tools {
  position: absolute; top: 12px; right: 12px; z-index: 30;
  display: flex; align-items: center; gap: 8px;
}
</style>
