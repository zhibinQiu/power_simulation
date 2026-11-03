<template>
  <teleport to="body">
    <transition name="ssd-fade">
      <div v-if="store.saveStrategyDialog.open" class="ssd-mask" @click.self="close">
        <div class="ssd-modal" role="dialog" aria-modal="true" :aria-label="t('保存策略')">
          <div class="ssd-head">
            <span class="ssd-title">{{ t('保存策略') }}</span>
            <button class="x-btn lg" :aria-label="t('关闭')" @click="close">✕</button>
          </div>
          <div class="ssd-body">
            <div class="ssd-hint">
              {{ t('保存当前场景全部工序参数（含附加传感器与可变设备设定值），保存后可在左侧「资源 · 策略 · 自定义（仿真保存）」中查看与应用。') }}
            </div>
            <label class="ssd-label" for="ssd-name">{{ t('策略名称') }}</label>
            <input id="ssd-name" ref="inputEl" v-model="store.saveStrategyDialog.name" class="ssd-input"
                   type="text" maxlength="40" autocomplete="off" spellcheck="false"
                   :placeholder="t('例如：高炉降焦比方案')" @keydown.enter="onEnter" />
            <div v-if="store.saveStrategyDialog.error" class="ssd-err">{{ store.saveStrategyDialog.error }}</div>
          </div>
          <div class="ssd-foot">
            <button class="ssd-btn" :disabled="store.saveStrategyDialog.saving" @click="close">{{ t('取消') }}</button>
            <button class="ssd-btn primary" :disabled="!canSubmit || store.saveStrategyDialog.saving" @click="ok">
              {{ store.saveStrategyDialog.saving ? t('保存中...') : t('确定') }}
            </button>
          </div>
        </div>
      </div>
    </transition>
  </teleport>
</template>

<script setup>
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'

const store = useSimStore()
const inputEl = ref(null)

// 名称去空格后非空才可提交：空名策略在左栏只会显示「未命名策略」，用户难以再找回
const canSubmit = computed(() => !!(store.saveStrategyDialog.name || '').trim())

function close() { store.closeSaveStrategyDialog() }
function ok() { if (canSubmit.value) store.commitSaveStrategy() }
// 回车提交：中文输入法上屏的 Enter（isComposing / keyCode 229）不能当作提交，
// 否则拼音选词时会把还没输完的名字直接存成策略
function onEnter(e) {
  if (e.isComposing || e.keyCode === 229) return
  e.preventDefault()
  // 关键：吞掉这次回车，别让它继续冒泡到 window 上的 ConfirmDialog ——
  // 同名确认框是在本回调里同步打开的，若任其冒泡，ConfirmDialog 会把同一个回车当成「确认」，
  // 表现为「弹了同名确认又立刻自动点掉、直接存了第二份」。
  e.stopPropagation()
  ok()
}

// 打开即聚焦输入框并全选默认名，用户可直接改名或回车保存
watch(() => store.saveStrategyDialog.open, async (open) => {
  if (!open) return
  await nextTick()
  const el = inputEl.value
  if (!el) return
  el.focus()
  el.select()
})

// Esc 关闭（保存中的请求不打断，closeSaveStrategyDialog 内部已拦截）
function onKey(e) {
  if (!store.saveStrategyDialog.open) return
  if (e.key === 'Escape') { e.preventDefault(); close() }
}
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
/* 遮罩：本组件 teleport 到 body，必须自己铺满视口并居中（同 ConfirmDialog 的样板） */
.ssd-mask {
  position: fixed; inset: 0; z-index: 300; display: flex; align-items: center; justify-content: center;
  padding: var(--sp-4); background: rgba(0, 0, 0, .42);
  animation: ssd-mask-in var(--dur) var(--ease);
}
@keyframes ssd-mask-in { from { opacity: 0 } to { opacity: 1 } }

.ssd-modal {
  width: 460px; max-width: 92vw; background: var(--panel); border: 1px solid var(--border);
  border-radius: var(--r-lg); box-shadow: var(--glass-shadow-lg); color: var(--text);
  font-family: var(--ui); overflow: hidden;
}
.ssd-head {
  display: flex; align-items: center; justify-content: space-between; gap: var(--sp-3);
  height: 46px; padding: 0 var(--pad-x); background: var(--head-bg);
}
.ssd-title { font-size: var(--fs-dialog); font-weight: var(--fw-t); letter-spacing: .2px; }
.ssd-body { padding: var(--sp-5) var(--pad-x) var(--sp-4); }
.ssd-hint { font-size: var(--fs-s); line-height: 1.7; color: var(--muted); margin-bottom: var(--sp-4); }
.ssd-label { display: block; font-size: var(--fs-s); color: var(--muted); margin-bottom: 6px; }
.ssd-input {
  width: 100%; height: 30px; padding: 0 10px; font-family: var(--ui); font-size: var(--fs-body);
  color: var(--text); background: var(--input); border: 1px solid var(--border); border-radius: var(--r);
}
.ssd-input:focus { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent-l); background: var(--input); color: var(--text); }
.ssd-err { margin-top: 8px; font-size: var(--fs-s); color: var(--red); line-height: 1.6; word-break: break-word; }
.ssd-foot {
  display: flex; justify-content: flex-end; align-items: center; gap: var(--sp-3);
  padding: var(--sp-3) var(--pad-x) var(--pad-x);
}
.ssd-btn {
  min-width: var(--btn-min-w); min-height: var(--btn-h-lg); padding: 0 var(--btn-pad-x-lg);
  display: inline-flex; align-items: center; justify-content: center;
  font-family: var(--ui); font-size: var(--fs-body); font-weight: 500; line-height: 1;
  color: var(--text); background: var(--btn-bg); border: 1px solid transparent; border-radius: var(--r);
  cursor: pointer; transition: background var(--dur) var(--ease), color var(--dur) var(--ease);
}
.ssd-btn:hover:not(:disabled) { background: var(--btn-bg-hover); box-shadow: var(--shadow); }
.ssd-btn:disabled { opacity: .55; cursor: not-allowed; }
.ssd-btn.primary { color: var(--on-accent); background: var(--accent); font-weight: 600; }
.ssd-btn.primary:hover:not(:disabled) { background: var(--accent-h); color: var(--on-accent); }
.ssd-btn.primary:active:not(:disabled) { background: var(--accent-d); }

.ssd-fade-enter-active, .ssd-fade-leave-active { transition: opacity var(--dur) var(--ease); }
.ssd-fade-enter-active .ssd-modal, .ssd-fade-leave-active .ssd-modal {
  transition: transform var(--dur-slow) var(--ease-out), opacity var(--dur) var(--ease);
}
.ssd-fade-enter-from, .ssd-fade-leave-to { opacity: 0; }
.ssd-fade-enter-from .ssd-modal, .ssd-fade-leave-to .ssd-modal { transform: translateY(6px) scale(.985); opacity: 0; }
</style>
