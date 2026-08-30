<template>
  <div v-if="store.toast" class="toast-layer" :class="'tst-' + store.toastType" @click="close" role="status" aria-live="polite">
      <span class="tst-ico">
        <svg v-if="store.toastType === 'success'" viewBox="0 0 16 16" width="15" height="15"><path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>
        <svg v-else-if="store.toastType === 'warn'" viewBox="0 0 16 16" width="15" height="15"><path d="M8 3 15 14H1L8 3Z" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/><path d="M8 6.5v3.6" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/><circle cx="8" cy="12" r="1" fill="currentColor"/></svg>
        <svg v-else-if="store.toastType === 'error'" viewBox="0 0 16 16" width="15" height="15"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M5.5 5.5l5 5M10.5 5.5l-5 5" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
        <svg v-else viewBox="0 0 16 16" width="15" height="15"><circle cx="8" cy="8" r="6.5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M8 7.4v3.8M8 4.9v.3" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>
      </span>
      <span class="tst-txt">{{ store.toast }}</span>
      <button class="x-btn on-dark" :title="t('关闭提示')" @click.stop="close">×</button>
      <span class="tst-bar" :key="store.toast + store.toastType"></span>
    </div>
</template>

<script setup>
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'

const store = useSimStore()
let timer = null

watch(() => store.toast, (v) => {
  if (timer) { clearTimeout(timer); timer = null }
  if (!v) return
  timer = setTimeout(() => { store.toast = '' }, 3400)
}, { immediate: true })

function close() { store.toast = '' }
onBeforeUnmount(() => { if (timer) clearTimeout(timer) })
</script>
