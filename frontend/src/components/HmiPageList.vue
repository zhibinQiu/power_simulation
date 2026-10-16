<template>
  <div class="hpl">
    <!-- 列表区：固定高度、禁止滚动，条目超出即换页 -->
    <div ref="viewEl" class="hpl-view">
      <div class="hpl-grid" :style="gridStyle">
        <template v-for="(it, i) in pageItems" :key="i">
          <slot :item="it" :index="offset + i" />
        </template>
      </div>
      <div v-if="!items.length" class="hpl-empty">
        <slot name="empty">
          <div class="hpl-none">{{ t('暂无数据') }}</div>
        </slot>
      </div>
    </div>

    <!-- 触控换页条：仅在多页时出现（左右换页，不做上下滚动） -->
    <div v-if="pages > 1" class="hpl-bar">
      <span class="hpl-sum">{{ t('共') }} {{ items.length }} {{ t('条') }}</span>
      <button type="button" class="hpl-btn" :disabled="page <= 1" :title="t('上一页')" :aria-label="t('上一页')" @click.stop="go(page - 1)">‹</button>
      <span class="hpl-pg"><b>{{ page }}</b><em>/{{ pages }}</em></span>
      <button type="button" class="hpl-btn" :disabled="page >= pages" :title="t('下一页')" :aria-label="t('下一页')" @click.stop="go(page + 1)">›</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { t } from '../i18n'

const props = defineProps({
  items: { type: Array, default: () => [] },
  // 单元格最小宽度（px）：0 = 单列列表；>0 时按容器宽度自适应列数
  minCell: { type: Number, default: 0 },
  // 单元格（行）高度（px）：必须与行内容实际高度一致，保证不裁切、不溢出
  cellHeight: { type: Number, default: 40 },
  gap: { type: Number, default: 6 },
})

const viewEl = ref(null)
const page = ref(1)
const vw = ref(0)
const vh = ref(0)
let raf = null
let ro = null

// 容量必须按容器实测计算：HMI 内容区随屏幕尺寸/全屏切换变化，固定每页条数会溢出或留白
function measure() {
  const el = viewEl.value
  if (!el) return
  const w = el.clientWidth
  const h = el.clientHeight
  if (w !== vw.value) vw.value = w
  if (h !== vh.value) vh.value = h
}
function schedule() {
  if (raf) return
  raf = requestAnimationFrame(() => { raf = null; measure() })
}

onMounted(() => {
  measure()
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(schedule)
    ro.observe(viewEl.value)
  }
  window.addEventListener('resize', schedule)
})
onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf)
  if (ro) ro.disconnect()
  window.removeEventListener('resize', schedule)
})

const cols = computed(() => {
  if (!props.minCell || vw.value <= 0) return 1
  return Math.max(1, Math.floor((vw.value + props.gap) / (props.minCell + props.gap)))
})
// 行容量：首帧未测量（0）时先全量渲染，测量回调在同一帧内触发重算，不会闪现
const rows = computed(() => (vh.value > 0 ? Math.max(1, Math.floor((vh.value + props.gap) / (props.cellHeight + props.gap))) : 0))
const perPage = computed(() => cols.value * Math.max(1, rows.value))
const pages = computed(() => (rows.value ? Math.max(1, Math.ceil(props.items.length / perPage.value)) : 1))
const offset = computed(() => (page.value - 1) * perPage.value)
const pageItems = computed(() => (rows.value ? props.items.slice(offset.value, offset.value + perPage.value) : props.items))

const gridStyle = computed(() => ({
  gridTemplateColumns: `repeat(${cols.value}, minmax(0, 1fr))`,
  gridAutoRows: props.cellHeight + 'px',
  gap: props.gap + 'px',
}))

// 条目增减只做页码收敛（不强制回第 1 页，避免操作中被打断）
watch(pages, (n) => { if (page.value > n) page.value = n })

function go(p) {
  page.value = Math.min(pages.value, Math.max(1, p))
}
</script>

<style scoped>
.hpl { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; gap: 8px; }
/* 禁止纵向滚动：条目超出容量即换页（HMI 全局交互逻辑） */
.hpl-view { flex: 1 1 auto; min-height: 0; overflow: hidden; position: relative; }
.hpl-grid { display: grid; align-content: start; }
.hpl-empty { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; }
.hpl-none { font-size: var(--fs-md); color: var(--ov-text-3); }
.hpl-bar { flex: 0 0 auto; display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
.hpl-sum { font-size: var(--fs-sm); color: var(--ov-text-3); margin-right: auto; font-family: var(--mono); }
.hpl-btn {
  width: 52px; height: 40px; padding: 0;
  display: inline-flex; align-items: center; justify-content: center;
  background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: 0;
  color: var(--ov-text-2); font-family: inherit; font-size: var(--fs-xl); line-height: 1; cursor: pointer;
  transition: background .12s, border-color .12s, color .12s, transform .12s;
  touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.hpl-btn:active:not(:disabled) { transform: scale(0.96); }
.hpl-btn:disabled { opacity: 0.35; cursor: default; }
@media (hover: hover) { .hpl-btn:not(:disabled):hover { border-color: var(--ov-accent); color: var(--ov-accent); background: var(--ov-ac-bg); } }
.hpl-pg { min-width: 58px; text-align: center; font-family: var(--mono); font-size: var(--fs-md); color: var(--ov-text-3); }
.hpl-pg b { color: var(--ov-num); font-size: var(--fs-lg); font-weight: 800; }
.hpl-pg em { font-style: normal; }
</style>
