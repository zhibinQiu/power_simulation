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
/* 遮罩层：本组件 teleport 到 body，因此**必须**自己铺满视口并居中 ——
   少了这段，.cd-mask 会以 position:static 排在 body 内容流末尾（视口之外），
   用户点「删除」后弹窗就在屏幕下方看不见，表现为「点了没反应」。 */
.cd-mask { position: fixed; inset: 0; z-index: 300; display: flex; align-items: center;
  justify-content: center; padding: var(--sp-4); background: rgba(0, 0, 0, .42);
  animation: cd-mask-in var(--dur) var(--ease); }
@keyframes cd-mask-in { from { opacity: 0 } to { opacity: 1 } }

/* 确认对话框 = 全平台「确认 / 取消」形态样板：
   弹窗 --r-lg 圆角 + 玻璃阴影；标题 L1(--fs-dialog)/600；正文 L4(--fs-body)/1.7/次要色；
   底部按钮「取消（次级）在左 → 确认（主色）或删除（危险）在最右」，弹窗档 28px 等宽。 */
.cd-modal { width: 420px; max-width: 92vw; background: var(--panel); border: 1px solid var(--border);
  border-radius: var(--r-lg); box-shadow: var(--glass-shadow-lg); font-family: var(--ui); color: var(--text);
  padding: 0; overflow: hidden; }
.cd-head { background: var(--head-bg);
 display: flex; align-items: center; justify-content: space-between; gap: var(--sp-3);
  padding: 0 var(--pad-x); height: 46px;  }
.cd-title { font-size: var(--fs-dialog); font-weight: var(--fw-t); letter-spacing: .2px; }
.cd-body { padding: var(--sp-5) var(--pad-x); font-size: var(--fs-body); line-height: 1.7; color: var(--muted); word-break: break-word;
  white-space: pre-wrap; }
.cd-foot { display: flex; justify-content: flex-end; align-items: center; gap: var(--sp-3); padding: var(--sp-3) var(--pad-x) var(--pad-x); }
.cd-btn { min-width: var(--btn-min-w); min-height: var(--btn-h-lg); padding: 0 var(--btn-pad-x-lg);
  font-size: var(--fs-body); font-family: var(--ui); font-weight: 500; line-height: 1; border-radius: var(--r);
  display: inline-flex; align-items: center; justify-content: center; gap: var(--sp-2);
  cursor: pointer; color: var(--text); background: var(--btn-bg); border: 1px solid transparent;
  transition: background var(--dur) var(--ease), color var(--dur) var(--ease),
              box-shadow var(--dur) var(--ease), transform var(--dur-fast) var(--ease); }
.cd-btn:hover { background: var(--btn-bg-hover); box-shadow: var(--shadow); }
.cd-btn:active { transform: translateY(1px); }
.cd-btn.primary { color: var(--on-accent); background: var(--accent); font-weight: 600; }
.cd-btn.primary:hover { background: var(--accent-h); color: var(--on-accent); box-shadow: 0 2px 8px color-mix(in srgb, var(--accent) 32%, transparent); }
.cd-btn.primary:active { background: var(--accent-d); }
.cd-btn.primary.danger { background: var(--red); color: #fff; }
.cd-btn.primary.danger:hover { background: color-mix(in srgb, var(--red) 86%, #000); color: #fff; box-shadow: 0 2px 8px color-mix(in srgb, var(--red) 30%, transparent); }

.cd-fade-enter-active, .cd-fade-leave-active { transition: opacity var(--dur) var(--ease); }
.cd-fade-enter-active .cd-modal, .cd-fade-leave-active .cd-modal { transition: transform var(--dur-slow) var(--ease-out), opacity var(--dur) var(--ease); }
.cd-fade-enter-from, .cd-fade-leave-to { opacity: 0; }
.cd-fade-enter-from .cd-modal, .cd-fade-leave-to .cd-modal { transform: translateY(6px) scale(.985); opacity: 0; }
</style>
