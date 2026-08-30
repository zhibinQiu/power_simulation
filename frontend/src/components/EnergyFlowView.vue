<template>
  <!-- ============ 能流分析视图：中间 3D 场景替换为能流桑基图 ============ -->
  <div class="ef-view">
    <!-- 关闭/返回等操作已由顶栏工具栏提供 -->
    <div class="ef-body">
      <div v-if="!hasData" class="ef-empty">
        {{ t('暂无仿真结果，请先运行一次仿真后查看能流分析。') }}
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
import { t } from '../i18n'

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
.ef-body { flex: 1 1 auto; padding: 14px; overflow: auto; }
.ef-empty { text-align: center; color: var(--muted); font-size: 12px; padding: 60px 20px; }
.ef-chart { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 10px; }
</style>
