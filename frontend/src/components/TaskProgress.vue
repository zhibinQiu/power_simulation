<template>
  <div v-if="store.task" class="task-progress" :class="'tp-' + store.task.status" role="progressbar" aria-valuemin="0" aria-valuemax="100" :aria-valuenow="store.task.pct">
      <div class="tp-head">
        <span class="tp-dot" :class="{ done: store.task.status === 'done', fail: store.task.status === 'fail' }">
          <svg v-if="store.task.status === 'done'" viewBox="0 0 16 16" width="12" height="12"><path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <svg v-else-if="store.task.status === 'fail'" viewBox="0 0 16 16" width="12" height="12"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>
        </span>
        <span class="tp-label">{{ store.task.label }}</span>
        <span class="tp-pct">{{ pctText }}</span>
      </div>
      <div class="tp-track">
        <div class="tp-fill" :style="{ width: store.task.pct + '%' }"></div>
      </div>
    </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'

const store = useSimStore()
const pctText = computed(() => {
  const task = store.task
  if (!task) return ''
  if (task.status === 'done') return t('完成')
  if (task.status === 'fail') return t('失败')
  return task.pct + '%'
})
</script>
