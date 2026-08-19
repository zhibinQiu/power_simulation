<template>
  <!-- ============ 底栏状态条 ============ -->
  <footer class="statusbar">
    <span class="st"><span class="feed-dot" :class="'feed-' + store.feedStatus"></span> 实时链路 <span class="v">{{ feedText }}</span></span>
    <span class="st">{{ store.editMode ? '编排方案' : '流程模型' }} · <span class="v">{{ store.editMode ? store.scheme.nodes.length + ' 节点' : store.model.units.length + ' 工序' }}</span> / <span class="v">{{ store.editMode ? store.scheme.connections.length + ' 连线' : store.model.flows.length + ' 物流' }}</span></span>
    <span class="st">监测点位 <span class="v">{{ deviceCount }}</span></span>
    <span class="st">可调约束 <span class="v">{{ paramCount }}</span></span>
    <span class="st spacer"></span>
    <span class="st" :class="store.strategy ? 'ok' : 'warnc'">{{ store.strategy ? '策略情景激活' : '基线情景' }}</span>
    <span class="st mono"><span class="v">{{ clock }}</span></span>
  </footer>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'

const store = useSimStore()
const clock = ref('')
let timer = null

const feedText = computed(() => ({ open: '已连接', closed: '已断开', error: '异常', init: '连接中…' }[store.feedStatus] || ''))
const deviceCount = computed(() => {
  const r = store.resultForView
  if (!r || !r.units) return 0
  return r.units.reduce((s, u) => s + (u.devices ? u.devices.length : 0), 0)
})
const paramCount = computed(() => {
  const ps = store.paramSchema
  if (!ps) return 0
  let n = 0
  for (const k in ps) { const e = ps[k]; n += (e.config ? e.config.length : 0) + (e.optim ? e.optim.length : 0) }
  return n
})

function tickClock() {
  const d = new Date(); const p = (x) => String(x).padStart(2, '0')
  clock.value = `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

onMounted(() => { tickClock(); timer = setInterval(tickClock, 1000) })
onBeforeUnmount(() => { if (timer) clearInterval(timer) })
</script>
