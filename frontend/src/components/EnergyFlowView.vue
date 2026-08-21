<template>
  <!-- ============ 能流分析视图：中间 3D 场景替换为能流桑基图 ============ -->
  <div class="ef-view">
    <!-- 顶部工具条 -->
    <div class="ef-toolbar">
      <div class="ef-title">
        <svg class="ef-title-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>
        <b>能流分析</b>
        <span class="ef-sub">能流桑基图 · 能源流向可视化</span>
      </div>
      <button class="ef-close" title="关闭能流分析，返回数字孪生" @click="close">✕</button>
    </div>

    <div class="ef-body">
      <div v-if="!hasData" class="ef-empty">
        暂无仿真结果，请先运行一次仿真后查看能流分析。
      </div>
      <div v-else class="ef-chart">
        <EnergySankey />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import EnergySankey from './EnergySankey.vue'
import { useSimStore } from '../stores/sim'

const store = useSimStore()
const hasData = computed(() => !!(store.resultForView && store.resultForView.sankey_energy && store.resultForView.sankey_energy.nodes && store.resultForView.sankey_energy.nodes.length))

// 关闭能流分析视图，返回数字孪生
const close = () => store.toggleEnergyFlow()
</script>

<style scoped>
.ef-view {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  background: var(--panel-2);
  color: var(--text);
  user-select: none;
}
/* ---- 顶部工具条 ---- */
.ef-toolbar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 8px 14px;
  background: var(--bar);
  border-bottom: 1px solid var(--border);
  flex: 0 0 auto;
}
.ef-title { display: flex; align-items: center; gap: 8px; min-width: 0; }
.ef-title b { font-size: 13px; font-weight: 600; }
.ef-title-icon { width: 16px; height: 16px; color: var(--accent2); flex: none; }
.ef-sub { color: var(--muted); font-size: 11px; margin-left: 2px; white-space: nowrap; }
.ef-close {
  display: flex; align-items: center; justify-content: center;
  width: 24px; height: 24px;
  border: 1px solid var(--border); border-radius: 4px;
  background: transparent; color: var(--muted);
  font-size: 12px; cursor: pointer; flex: 0 0 auto;
}
.ef-close:hover { color: var(--red); border-color: var(--red); background: rgba(209, 75, 75, .1); }

.ef-body { flex: 1 1 auto; padding: 14px; overflow: auto; }
.ef-empty { text-align: center; color: var(--muted); font-size: 12px; padding: 60px 20px; }
.ef-chart { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 10px; }
</style>
