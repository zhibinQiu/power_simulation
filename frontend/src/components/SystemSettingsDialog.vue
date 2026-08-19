<template>
  <div class="ss-mask" @click.self="$emit('close')">
    <div class="ss-modal" role="dialog" aria-modal="true" aria-label="系统设置">
      <div class="ss-head">
        <span class="ss-title">系统设置</span>
        <button class="ss-x" @click="$emit('close')" aria-label="关闭">×</button>
      </div>

      <div class="ss-body">
        <!-- 显示 -->
        <section class="ss-sec">
          <div class="ss-sec-title">显示</div>
          <div class="ss-row">
            <div class="ss-info">
              <div class="ss-name">画面亮度</div>
              <div class="ss-desc">调整 3D 场景曝光（暗 0.3 ~ 2.5 亮）</div>
            </div>
            <div class="ss-ctrl">
              <input type="range" class="ss-slider" min="0.3" max="2.5" step="0.05"
                     :value="store.brightness" @input="store.setBrightness(+$event.target.value)" />
              <span class="ss-val">{{ (store.brightness * 100).toFixed(0) }}%</span>
            </div>
          </div>
          <div class="ss-row">
            <div class="ss-info">
              <div class="ss-name">自动环视</div>
              <div class="ss-desc">相机自动环绕旋转园区</div>
            </div>
            <div class="ss-ctrl">
              <button class="ss-sw" :class="{ on: store.autoRotate }" role="switch" :aria-checked="store.autoRotate"
                      @click="store.setAutoRotate(!store.autoRotate)"><i></i></button>
            </div>
          </div>
          <div class="ss-row">
            <div class="ss-info">
              <div class="ss-name">虚拟巡视</div>
              <div class="ss-desc">机器狗沿工艺旁地面巡视完整流程</div>
            </div>
            <div class="ss-ctrl">
              <button class="ss-sw" :class="{ on: store.patrolOn }" role="switch" :aria-checked="store.patrolOn"
                      @click="store.togglePatrol()"><i></i></button>
            </div>
          </div>
          <div class="ss-row">
            <div class="ss-info">
              <div class="ss-name">全屏模式</div>
              <div class="ss-desc">隐藏左 / 右 / 底栏，仅保留 3D 场景</div>
            </div>
            <div class="ss-ctrl">
              <button class="ss-sw" :class="{ on: store.fullscreenOn }" role="switch" :aria-checked="store.fullscreenOn"
                      @click="store.toggleFullscreen()"><i></i></button>
            </div>
          </div>
        </section>

        <!-- 布局 -->
        <section class="ss-sec">
          <div class="ss-sec-title">布局</div>
          <div class="ss-row">
            <div class="ss-info">
              <div class="ss-name">左侧栏（资产树）</div>
              <div class="ss-desc">工艺 / 设备 / 原料 / 策略</div>
            </div>
            <div class="ss-ctrl">
              <button class="ss-sw" :class="{ on: store.leftOpen }" :disabled="store.fullscreenOn" role="switch"
                      :aria-checked="store.leftOpen" @click="store.toggleLeft()"><i></i></button>
            </div>
          </div>
          <div class="ss-row">
            <div class="ss-info">
              <div class="ss-name">右侧栏（检视器）</div>
              <div class="ss-desc">上下文属性与数据检视</div>
            </div>
            <div class="ss-ctrl">
              <button class="ss-sw" :class="{ on: store.rightOpen }" :disabled="store.fullscreenOn" role="switch"
                      :aria-checked="store.rightOpen" @click="store.toggleRight()"><i></i></button>
            </div>
          </div>
          <div class="ss-row">
            <div class="ss-info">
              <div class="ss-name">底栏（命令行窗口）</div>
              <div class="ss-desc">命令行窗口 + 状态条</div>
            </div>
            <div class="ss-ctrl">
              <button class="ss-sw" :class="{ on: store.bottomOpen }" :disabled="store.fullscreenOn" role="switch"
                      :aria-checked="store.bottomOpen" @click="store.toggleBottom()"><i></i></button>
            </div>
          </div>
          <div v-if="store.fullscreenOn" class="ss-hint">全屏模式下布局面板已隐藏，退出全屏后恢复。</div>
        </section>

        <!-- 场景 -->
        <section class="ss-sec">
          <div class="ss-sec-title">场景</div>
          <div class="ss-row">
            <div class="ss-info">
              <div class="ss-name">仿真情景</div>
              <div class="ss-desc">四大控排行业情景</div>
            </div>
            <div class="ss-ctrl ss-segs">
              <button v-for="s in store.scenarios" :key="s.id" class="ss-seg"
                      :class="{ on: s.id === store.scenario }" @click="store.setScenario(s.id)">{{ s.label }}</button>
            </div>
          </div>
          <div class="ss-row">
            <div class="ss-info">
              <div class="ss-name">场景环境</div>
              <div class="ss-desc">数字孪生外围景观</div>
            </div>
            <div class="ss-ctrl ss-segs">
              <button v-for="e in store.envModes" :key="e.id" class="ss-seg"
                      :class="{ on: e.id === store.envMode }" @click="store.setEnvMode(e.id)">{{ e.label }}</button>
            </div>
          </div>
        </section>

        <!-- 实时链路 -->
        <section class="ss-sec">
          <div class="ss-sec-title">实时链路</div>
          <div class="ss-row">
            <div class="ss-info">
              <div class="ss-name">数据源状态</div>
              <div class="ss-desc">接入实时数据的链路状态</div>
            </div>
            <div class="ss-ctrl ss-feed">
              <span class="feed-dot" :class="'feed-' + store.feedStatus"></span>
              <span class="ss-feed-tx">{{ feedText }}</span>
            </div>
          </div>
        </section>
      </div>

      <div class="ss-actions">
        <button class="ss-btn ghost" @click="resetDefaults">恢复默认设置</button>
        <span class="sp"></span>
        <button class="ss-btn primary" @click="$emit('close')">关闭</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'

const store = useSimStore()
defineEmits(['close'])

const feedText = computed(() => ({ open: '已连接', closed: '已断开', error: '异常', init: '连接中…' }[store.feedStatus] || ''))

// 恢复默认设置：所有设置项实时生效于 store，无需保存
function resetDefaults() {
  store.setBrightness(0.95)
  store.setAutoRotate(false)
  if (store.patrolOn) store.togglePatrol()
  if (store.fullscreenOn) store.toggleFullscreen()
  if (!store.leftOpen) store.toggleLeft()
  if (!store.rightOpen) store.toggleRight()
  if (!store.bottomOpen) store.toggleBottom()
  store.setEnvMode('industrial')
  if (store.scenario !== 'steel') store.setScenario('steel')
}
</script>

<style scoped>
.ss-mask { position: fixed; inset: 0; background: rgba(20,30,40,.42); display: flex; align-items: center; justify-content: center; z-index: 200; }
.ss-modal { width: 620px; max-width: 94vw; max-height: 88vh; display: flex; flex-direction: column; background: var(--panel);
  border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 18px 50px rgba(0,0,0,.28); font-family: var(--ui); color: var(--text); }
.ss-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 14px; border-bottom: 1px solid var(--border); }
.ss-title { font-size: 14px; font-weight: 700; }
.ss-x { border: none; background: transparent; font-size: 14px; line-height: 1; color: var(--muted); cursor: pointer; padding: 0 4px; }
.ss-x:hover { color: var(--text); }
.ss-body { padding: 12px 14px 14px; overflow: auto; display: flex; flex-direction: column; gap: 14px; }
.ss-sec { border: 1px solid var(--border); border-radius: 6px; background: var(--bar); padding: 4px 0; overflow: hidden; }
.ss-sec-title { font-size: 11px; font-weight: 700; color: var(--muted); padding: 8px 12px 6px; border-bottom: 1px solid var(--border); background: var(--bar); }
.ss-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 9px 12px; border-bottom: 1px solid var(--border); }
.ss-row:last-child { border-bottom: none; }
.ss-info { min-width: 0; }
.ss-name { font-size: 12px; font-weight: 600; }
.ss-desc { font-size: 10px; color: var(--muted); margin-top: 2px; }
.ss-ctrl { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
/* 滑块 */
.ss-slider { width: 150px; accent-color: var(--accent); cursor: pointer; }
.ss-val { font-size: 11px; color: var(--muted); min-width: 36px; text-align: right; font-variant-numeric: tabular-nums; }
/* 开关 */
.ss-sw { position: relative; width: 38px; height: 20px; border-radius: 12px; border: 1px solid var(--border); background: var(--panel); cursor: pointer; padding: 0; transition: background .15s, border-color .15s; }
.ss-sw i { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: var(--faint); transition: left .15s, background .15s; }
.ss-sw.on { background: var(--accent); border-color: var(--accent); }
.ss-sw.on i { left: 20px; background: #fff; }
.ss-sw:disabled { opacity: .4; cursor: not-allowed; }
/* 分段选择 */
.ss-segs { display: flex; gap: 4px; flex-wrap: wrap; max-width: 320px; justify-content: flex-end; }
.ss-seg { padding: 4px 10px; border: 1px solid var(--border); border-radius: 12px; font-size: 10px; color: var(--muted); background: var(--panel); cursor: pointer; }
.ss-seg:hover { border-color: var(--accent); }
.ss-seg.on { background: var(--accent-l); border-color: var(--accent); color: var(--accent-d); font-weight: 600; }
/* 数据源状态 */
.ss-feed { gap: 6px; }
.ss-feed-tx { font-size: 11px; color: var(--muted); }
.ss-hint { font-size: 10px; color: var(--faint); padding: 6px 12px; }
.ss-actions { display: flex; align-items: center; gap: 10px; padding: 12px 14px; border-top: 1px solid var(--border); }
.ss-actions .sp { flex: 1; }
.ss-btn { padding: 8px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bar); cursor: pointer; font-size: 12px; color: var(--text); }
.ss-btn:hover { border-color: var(--accent); }
.ss-btn.primary { background: var(--accent); border-color: var(--accent); color: #fff; }
.ss-btn.primary:hover { background: var(--accent-d); }
.ss-btn.ghost { background: transparent; }
.sp { flex: 1; }
</style>
