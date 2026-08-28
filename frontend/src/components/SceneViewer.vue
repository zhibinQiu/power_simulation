<template>
  <div class="area-scene">
    <div ref="host" class="scene-host"></div>

    <!-- 3D 小组子场景：左上角返回顶层浮层（非编辑态下点击小组标签进入） -->
    <div v-if="!store.editMode && store.scheme.activeGroupId" class="group-scene-bar">
      <button type="button" class="gs-back" @click="store.exitGroup()">← 返回顶层</button>
      <span class="gs-title">▦ {{ groupSceneName }}</span>
    </div>

    <!-- 仿真模式：右上角实时显示仿真前后能源/碳排放对比（大卡片 · 细粒度分组 + 可视化） -->
    <div v-if="store.simMode && store.simBaseline" class="sim-compare" :class="{ 'sc-folded': scFolded }">
      <div class="sc-head">
        <span class="sc-title">仿真前后对比</span>
        <span class="sc-badge">仿真模式</span>
        <button class="sc-fold" type="button" @click="scFolded = !scFolded" :title="scFolded ? '展开' : '收起'">{{ scFolded ? '▸' : '▾' }}</button>
      </div>

      <template v-if="!scFolded">
        <!-- 左右两栏对比：碳排放 | 能耗（本次更改明细已由命令行窗口实时输出） -->
        <div class="sc-cols" v-if="compareRows.length">
          <div class="sc-col" v-for="g in compareRows" :key="g.key">
            <div class="sc-gname">{{ g.name }}</div>
            <div class="sc-row" v-for="r in g.rows" :key="r.key">
              <div class="sc-r1">
                <span class="sc-name" :title="r.name">{{ r.name }}</span>
                <span class="sc-fv">
                  <i>{{ r.beforeText }}</i><em>→</em><b>{{ r.afterText }}</b><small>{{ r.u }}</small>
                </span>
                <span class="sc-delta" :class="r.cls">{{ r.arrow }} {{ r.deltaText }}</span>
              </div>
              <!-- 重叠对比条：灰=优化前底，彩=优化后从同一起点覆盖，差值=露出的灰尾（减少）或超出的彩段（增加） -->
              <div class="sc-bar">
                <div class="sc-bar-before" :title="'优化前 ' + r.beforeText + ' ' + r.u" :style="{ width: r.beforePct + '%' }"></div>
                <div class="sc-bar-after" :class="r.cls" :title="'优化后 ' + r.afterText + ' ' + r.u" :style="{ width: r.afterPct + '%' }"></div>
              </div>
            </div>
          </div>
        </div>
        <div class="sc-empty" v-else>尚未执行前后对比：点击左侧策略，在属性面板使用「策略仿真」测试</div>
      </template>

      <button class="sc-save" type="button" @click="store.requestSaveStrategy()">保存策略</button>
    </div>

    <!-- 点击 3D 场景中模型旁的小铭牌 → 右侧统一展示该工序实例的属性面板（无浮窗冗余） -->

    <div v-if="!ok" class="scene-fallback">
      <div class="fb-title">3D 场景无法初始化</div>
      <div class="fb-msg">{{ lastErr || '当前环境不支持 WebGL，无法渲染 3D 场景。' }}</div>
      <div class="fb-hint">请使用支持 WebGL 的现代浏览器（Chrome / Edge / Firefox），并确认未禁用“硬件加速”。</div>
      <button class="fb-retry" type="button" @click="retry">重试</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch, nextTick } from 'vue'
import { useSimStore } from '../stores/sim'
import { TwinScene } from '../three/scene'

const store = useSimStore()
const host = ref(null)
const ok = ref(true)
const lastErr = ref('')
let scene = null
let ro = null
let introDone = false

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

// 仿真模式：右上角仿真前后能源/碳排放对比（simBaseline 为进入仿真时的快照）
const scFolded = ref(false)

// 兼容字段取值：前端估算结果用 energy，后端完整结果用 energy_total
function pick(o, ...keys) {
  if (!o) return null
  for (const k of keys) { const v = o[k]; if (v != null && !isNaN(v)) return v }
  return null
}
const fmt1 = (n) => (n == null ? '—' : Number(n).toFixed(1))
// 千分位格式化：大数更易读（如 1,234.5）
const fmtN = (n) => (n == null ? '—' : Number(n).toLocaleString('zh-CN', { minimumFractionDigits: 1, maximumFractionDigits: 1 }))
const fmtPct = (p) => ((p > 0 ? '+' : '') + p.toFixed(1) + '%')
// 基线 vs 当前是否发生实质变化（未应用策略时兜底引导判断）
function hasDelta(b, c) {
  for (const k of ['co2_total', 'energy_total', 'energy', 'intensity']) {
    if (b[k] != null && c[k] != null && Math.abs(b[k] - c[k]) > 1e-9) return true
  }
  return false
}

// 分组对比：仅碳排放 / 能耗 两组，左右两栏展示，每行含重叠对比条 + 变化徽章
const compareRows = computed(() => {
  const base = store.simBaseline && store.simBaseline.totals
  if (!base) return []
  const cur = (store.simCurrent && store.simCurrent.totals)
    || (store.strategy && store.strategy.totals)
    || (store.resultForView && store.resultForView.totals) || null
  if (!cur) return []
  if (!store.simCurrent && !store.strategy && !hasDelta(base, cur)) return []  // 尚无对比内容 → 显示引导

  const defs = [
    { key: 'co2', name: '碳排放', rows: [
      { key: 'co2_total', name: '总排放量', a: pick(base, 'co2_total'), b: pick(cur, 'co2_total'), u: 'tCO₂/h', dir: 'down' },
      { key: 'co2_direct', name: '直接排放(范围一)', a: pick(base, 'co2_direct'), b: pick(cur, 'co2_direct'), u: 'tCO₂/h', dir: 'down' },
      { key: 'co2_indirect', name: '间接排放(范围二)', a: pick(base, 'co2_indirect'), b: pick(cur, 'co2_indirect'), u: 'tCO₂/h', dir: 'down' },
      { key: 'intensity', name: '吨钢碳排放强度', a: pick(base, 'intensity'), b: pick(cur, 'intensity'), u: 'kgCO₂/t', dir: 'down' },
    ] },
    { key: 'energy', name: '能耗', rows: [
      { key: 'energy_total', name: '综合能耗', a: pick(base, 'energy_total', 'energy'), b: pick(cur, 'energy_total', 'energy'), u: 'GJ/h', dir: 'down' },
      { key: 'energy_intensity', name: '单位产品综合能耗', a: pick(base, 'energy_intensity'), b: pick(cur, 'energy_intensity'), u: 'kgce/t', dir: 'down' },
      { key: 'elec', name: '电耗', a: pick(base, 'elec'), b: pick(cur, 'elec'), u: 'MWh/h', dir: 'down' },
      { key: 'fuel_energy', name: '燃料能耗', a: pick(base, 'fuel_energy'), b: pick(cur, 'fuel_energy'), u: 'GJ/h', dir: 'down' },
    ] },
  ]

  return defs.map((g) => ({
    key: g.key, name: g.name,
    rows: g.rows
      .filter((r) => r.a != null && r.b != null)
      .map((r) => {
        const d = r.b - r.a
        const maxV = Math.max(Math.abs(r.a), Math.abs(r.b), 1e-9)
        const beforePct = Math.max(2, (Math.abs(r.a) / maxV) * 100)
        const afterPct = Math.max(2, (Math.abs(r.b) / maxV) * 100)
        const relPct = r.a !== 0 ? (d / r.a) * 100 : null
        const good = r.dir === 'up' ? d >= 0 : r.dir === 'down' ? d <= 0 : true
        const cls = r.dir === 'neutral' ? 'neu' : (good ? 'good' : 'bad')
        const num = (n) => (r.pct100 ? n * 100 : n)
        return {
          ...r,
          beforeText: fmtN(num(r.a)), afterText: fmtN(num(r.b)), d,
          arrow: d > 1e-9 ? '▲' : d < -1e-9 ? '▼' : '–',
          deltaText: r.pct100 ? fmtPct(num(d))
            : (r.dir === 'neutral' ? fmt1(d)
              : (relPct == null ? fmt1(d) : fmtPct(relPct))),
          cls, beforePct, afterPct,
        }
      }),
  })).filter((g) => g.rows.length)
})

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
  return g ? g.name : '设备小组'
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
function onVis() { if (scene) scene.setPaused(store.editMode || document.hidden) }
document.addEventListener('visibilitychange', onVis)

watch(() => store.editMode, async (v) => {
  if (!scene) return
  scene.setPaused(v || document.hidden)
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
watch(() => store.patrolOn, (v) => { scene && scene.setPatrol(v) })

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
  window.removeEventListener('resize', onResize)
  if (ro) { ro.disconnect(); ro = null }
  if (scene) scene.dispose()
})
</script>

<style scoped>
/* 上下分屏：上部数字孪生 3D 场景，下部仿真前后对比面板 */
.area-scene { position: absolute; inset: 0; display: flex; flex-direction: column; }
/* 3D 场景占满剩余空间，对比面板按内容自适应高度 */
.scene-host { position: relative; flex: 1 1 0; min-height: 0; }

/* 3D 小组子场景 · 左上角返回顶层浮层（工具栏在场景外部独立成行，不再遮挡，恢复默认左上角位置） */
.group-scene-bar { position: absolute; top: 12px; left: 12px; z-index: 6; display: flex; align-items: center; gap: 10px; background: rgba(255, 255, 255, 0.72); border: 1px solid rgba(0, 114, 189, 0.2); border-radius: 4px; padding: 6px 10px; backdrop-filter: blur(6px); }
.gs-back {
  display: inline-flex; align-items: center; gap: 5px; height: 24px; padding: 0 9px;
  background: transparent; border: 1px solid var(--border); border-radius: 4px;
  cursor: pointer; color: var(--text); font-size: 11px; font-weight: 600; font-family: var(--ui);
  line-height: 1; white-space: nowrap;
  transition: background .1s, color .1s, border-color .1s;
}
.gs-back:hover { background: var(--panel-3); color: var(--text); border-color: var(--accent); }
.gs-back:active { background: var(--sel); }
.gs-title { font-size: 12px; font-weight: 600; color: #23374D; }

/* 仿真模式 · 右上角悬浮对比窗口（毛玻璃透明，宽度 400px，悬浮在 3D 场景上部右侧） */
.sim-compare {
  position: absolute; top: 12px; right: 12px; z-index: 5;
  width: 400px; max-width: calc(100% - 24px);
  max-height: calc(100% - 24px);
  overflow-y: auto;
  background: rgba(255, 255, 255, 0.72);
  -webkit-backdrop-filter: blur(10px) saturate(1.3);
  backdrop-filter: blur(10px) saturate(1.3);
  border: 1px solid rgba(15, 23, 42, 0.10);
  border-radius: 4px;
  box-shadow: 0 6px 24px rgba(15, 23, 42, 0.14);
  padding: 10px 12px;
  color: #1c1c1c;
}
.sim-compare.sc-folded { height: auto; max-height: none; }
.sim-compare::-webkit-scrollbar { width: 4px; }
.sim-compare::-webkit-scrollbar-thumb { background: #c9ced4; border-radius: 2px; }
.sc-head { position: sticky; top: -10px; background: rgba(255, 255, 255, 0.84); z-index: 1; display: flex; align-items: center; gap: 8px; margin-bottom: 9px; padding-top: 10px; }
.sc-title { font-size: 12px; font-weight: 700; color: #1c1c1c; flex: 1; }
.sc-badge { font-size: 9px; color: #2E9E63; border: 1px solid rgba(46,158,99,.45); border-radius: 20px; padding: 1px 7px; white-space: nowrap; }
.sc-fold { display: inline-flex; align-items: center; justify-content: center; width: 18px; height: 18px; padding: 0; background: #f2f4f6; border: 1px solid #dde2e7; border-radius: 4px; cursor: pointer; color: #4a5560; font-size: 10px; line-height: 1; }
.sc-fold:hover { background: #e6eaee; color: #1c1c1c; }

/* 左右两栏对比：碳排放 | 能耗 */
.sc-cols { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; align-items: start; margin-top: 2px; }
.sc-col { background: rgba(248, 250, 251, 0.6); border: 1px solid #e8edf2; border-radius: 8px; padding: 8px 9px 6px; min-width: 0; }
.sc-gname { font-size: 10px; font-weight: 700; color: #0072BD; margin-bottom: 6px; padding-bottom: 5px; border-bottom: 1px solid #e8edf2; }
.sc-row { margin-bottom: 7px; }
/* 窄窗口下每行两行布局：第一行名称（省略号），第二行 数值 → 数值 + 变化徽章 */
.sc-r1 { display: flex; flex-wrap: wrap; align-items: center; gap: 3px 6px; font-size: 10.5px; }
.sc-name { color: #6a6a6a; flex: 1 1 100%; min-width: 0; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.sc-fv { flex: 1 1 auto; min-width: 0; display: inline-flex; align-items: center; gap: 4px; color: #4a4a4a; font-size: 10px; white-space: nowrap; font-variant-numeric: tabular-nums; }
.sc-fv i { font-style: normal; color: #8a8f96; }
.sc-fv em { font-style: normal; color: #c9ced4; }
.sc-fv b { font-weight: 600; color: #1c1c1c; }
.sc-fv small { color: #8a8f96; }
.sc-delta { flex: 0 0 auto; font-size: 10px; font-weight: 700; font-variant-numeric: tabular-nums; }
.sc-delta.good { color: #2E9E63; }
.sc-delta.bad { color: #D14B4B; }
.sc-delta.neu { color: #4a5560; }
/* 重叠对比条：单轨，灰=优化前全宽底，彩=优化后从同一起点覆盖；露出的灰尾=减少量，超出的彩段=增加量 */
.sc-bar { position: relative; height: 8px; border-radius: 4px; background: #eef1f4; margin-top: 4px; }
.sc-bar-before, .sc-bar-after { position: absolute; left: 0; top: 0; height: 100%; border-radius: 4px; transition: width .3s ease; }
.sc-bar-before { background: #cdd2d8; }
.sc-bar-after.good { background: #2E9E63; }
.sc-bar-after.bad { background: #D14B4B; }
.sc-bar-after.neu { background: #0072BD; }

.sc-empty { font-size: 10.5px; color: #8a8f96; line-height: 1.5; padding: 4px 0 2px; }
.sc-save { margin-top: 10px; width: 100%; padding: 6px 0; font-size: 11px; font-weight: 600; color: #ffffff; background: #0072BD; border: none; border-radius: 6px; cursor: pointer; }
.sc-save:hover { background: #005A93; }

/* ===== 仿真模式（sim-dark）· 对比窗口 VS Code 深色风格 ===== */
.app.sim-dark .sim-compare { background: rgba(22, 27, 34, 0.78); border-color: rgba(255, 255, 255, 0.07); box-shadow: 0 6px 24px rgba(0, 0, 0, 0.45); color: var(--text); }
.app.sim-dark .sim-compare::-webkit-scrollbar-thumb { background: #2F3A49; }
.app.sim-dark .sc-head { background: rgba(22, 27, 34, 0.84); }
.app.sim-dark .sc-title { color: var(--text); }
.app.sim-dark .sc-badge { color: var(--green); border-color: rgba(62, 207, 142, .45); }
.app.sim-dark .sc-fold { background: var(--panel-3); border-color: var(--border); color: var(--muted); }
.app.sim-dark .sc-fold:hover { background: #2C3644; color: var(--text); }
.app.sim-dark .sc-col { background: rgba(29, 36, 46, 0.55); border-color: rgba(255, 255, 255, 0.06); }
.app.sim-dark .sc-gname { color: var(--accent); border-bottom-color: var(--border); }
.app.sim-dark .sc-name { color: var(--muted); }
.app.sim-dark .sc-fv { color: var(--text); }
.app.sim-dark .sc-fv i { color: var(--faint); }
.app.sim-dark .sc-fv em { color: #3A4656; }
.app.sim-dark .sc-fv b { color: var(--text); }
.app.sim-dark .sc-fv small { color: var(--faint); }
.app.sim-dark .sc-delta.good { color: var(--green); }
.app.sim-dark .sc-delta.bad { color: var(--red); }
.app.sim-dark .sc-delta.neu { color: var(--muted); }
.app.sim-dark .sc-bar { background: var(--rail); }
.app.sim-dark .sc-bar-before { background: #39424F; }
.app.sim-dark .sc-bar-after.good { background: var(--green); }
.app.sim-dark .sc-bar-after.bad { background: var(--red); }
.app.sim-dark .sc-bar-after.neu { background: var(--accent); }
.app.sim-dark .sc-empty { color: var(--faint); }
.app.sim-dark .sc-save { background: var(--accent); }
.app.sim-dark .sc-save:hover { background: var(--accent-d); }
</style>
