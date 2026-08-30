<template>
  <teleport to="body">
    <transition name="cd-fade">
      <div v-if="store.confirmDialog.open" class="cd-mask" @click.self="resolve(false)">
        <div class="cd-modal" role="dialog" aria-modal="true" :aria-label="store.confirmDialog.title">
          <div class="cd-head">
            <span class="cd-title">{{ store.confirmDialog.title }}</span>
            <button class="x-btn lg" @click="resolve(false)" :aria-label="t('关闭')">✕</button>
          </div>
          <div class="cd-body">{{ store.confirmDialog.message }}</div>
          <div class="cd-foot">
            <button class="cd-btn" @click="resolve(false)">{{ store.confirmDialog.cancelText }}</button>
            <button class="cd-btn primary" :class="{ danger: store.confirmDialog.danger }" @click="resolve(true)">
              {{ store.confirmDialog.okText }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { onBeforeUnmount, onMounted } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'

const store = useSimStore()

// 关闭弹窗：确认返回 true，取消/遮罩/Esc 返回 false，并回调挂起的 Promise
function resolve(val) { store.confirmResolve(val) }

function onKey(e) {
  if (!store.confirmDialog.open) return
  if (e.key === 'Escape') resolve(false)
  else if (e.key === 'Enter') resolve(true)
}

onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
.cd-mask { position: fixed; inset: 0; background: rgba(20,30,40,.42); display: flex;
  align-items: center; justify-content: center; z-index: 300; }
.cd-modal { width: 400px; max-width: 92vw; background: var(--panel); border: 1px solid var(--border);
  border-radius: 4px; box-shadow: 0 18px 50px rgba(0,0,0,.3); font-family: var(--ui); color: var(--text);
  padding: 0; overflow: hidden; }
.cd-head { display: flex; align-items: center; justify-content: space-between;
  padding: 12px 14px 10px; border-bottom: 1px solid var(--border); }
.cd-title { font-size: 14px; font-weight: 700; letter-spacing: .5px; }
.cd-body { padding: 18px 16px; font-size: 12.5px; line-height: 1.7; color: var(--muted); word-break: break-word;
  white-space: pre-wrap; }
.cd-foot { display: flex; justify-content: flex-end; gap: 8px; padding: 0 14px 14px; }
.cd-btn { min-width: 84px; padding: 7px 0; font-size: 12.5px; font-family: var(--ui); border-radius: 4px;
  cursor: pointer; color: var(--text); background: var(--panel-2); border: 1px solid var(--border); }
.cd-btn:hover { border-color: var(--accent-d); }
.cd-btn.primary { color: #fff; background: var(--accent); border-color: var(--accent); }
.cd-btn.primary:hover { background: var(--accent-d); border-color: var(--accent-d); }
.cd-btn.primary.danger { background: var(--red); border-color: var(--red); }
.cd-btn.primary.danger:hover { background: #b0352c; border-color: #b0352c; }

.cd-fade-enter-active, .cd-fade-leave-active { transition: opacity .14s ease; }
.cd-fade-enter-active .cd-modal, .cd-fade-leave-active .cd-modal { transition: transform .14s ease; }
.cd-fade-enter-from, .cd-fade-leave-to { opacity: 0; }
.cd-fade-enter-from .cd-modal, .cd-fade-leave-to .cd-modal { transform: scale(.94); }
</style>
