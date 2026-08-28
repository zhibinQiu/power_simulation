<template>
  <div class="ab-mask" @click.self="onClose">
    <div class="ab-modal" role="dialog" aria-modal="true" aria-label="关于本平台">
      <div class="ab-head">
        <span class="ab-title">关于本平台</span>
        <button class="ab-x" @click="onClose" aria-label="关闭">×</button>
      </div>

      <div class="ab-logo">
        <img src="/favicon.png" alt="工业能碳智控平台" />
      </div>

      <div class="ab-name">工业能碳智控平台</div>
      <div class="ab-sub">Web 版工业数字孪生仿真系统</div>
      <div class="ab-sub">面向高炉炼铁的能碳仿真与优化平台</div>
      <div class="ab-ver">版本 v0.1.0</div>

      <div class="ab-divider"></div>

      <!-- 平台激活（内嵌）：未激活时展示激活码输入，激活后展示授权信息 -->
      <div class="lic-status" :class="activated ? 'on' : 'off'">
        <span class="lic-badge">{{ activated ? '已激活' : '未激活' }}</span>
        <span class="lic-desc">
          {{ activated
            ? `本机已授权，激活时间 ${activatedAt}`
            : '产品未激活，请输入激活码完成激活。' }}
        </span>
      </div>

      <div v-if="!activated" class="lic-row">
        <label>激活码</label>
        <div class="lic-input-wrap">
          <span class="lic-prefix">NENG-</span>
          <input ref="inp" class="lic-input" placeholder="XXXX-XXXX-XXXX-XXXX"
                 :value="hexCode" @input="onInput" @keyup.enter="doActivate"
                 :disabled="busy" spellcheck="false" autocomplete="off" />
        </div>
        <button class="lic-go" @click="doActivate" :disabled="busy || !hexCode">
          {{ busy ? '激活中…' : '激 活' }}
        </button>
      </div>

      <div v-if="!activated" class="lic-tip">激活码由厂商提供，与当前机器指纹绑定；激活前不影响平台查看，激活后解锁完整授权。</div>

      <div v-if="msg" class="lic-msg" :class="msgOk ? 'ok' : 'err'">{{ msg }}</div>

      <div class="ab-divider"></div>
      <div class="ab-copy">© 2026 haiyisoftware · 保留所有权利</div>

      <div class="ab-foot">
        <button class="ab-ok" @click="onClose">确 定</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onMounted, ref } from 'vue'
import { useSimStore } from '../stores/sim'

const store = useSimStore()
// 用户只输入 16 位十六进制（前缀 NENG- 固定显示，粘贴时自动剥离），避免前缀逐字符输入的歧义
const hexCode = ref('')
const busy = ref(false)
const msg = ref('')
const msgOk = ref(false)
const inp = ref(null)

const activated = computed(() => !!store.license.activated)
// 后端返回 snake_case（activated_at），此处双兼容
const activatedAt = computed(() => {
  const t = store.license.activated_at || store.license.activatedAt || ''
  return t ? String(t).slice(0, 16).replace('T', ' ') : ''
})

// hex 输入自动格式化为 XXXX-XXXX-XXXX-XXXX（大写；粘贴完整激活码时剥离 NENG- 前缀）
function onInput(e) {
  const hex = e.target.value.toUpperCase()
    .replace(/^NENG-?/, '')
    .replace(/[^0-9A-F]/g, '')
  const parts = hex.match(/.{1,4}/g) || []
  e.target.value = parts.join('-')
  hexCode.value = parts.join('-')
}

async function doActivate() {
  if (!hexCode.value || busy.value) return
  busy.value = true
  msg.value = ''
  msgOk.value = false
  try {
    const r = await store.activatePlatform('NENG-' + hexCode.value)
    if (r && r.ok) {
      msgOk.value = true
      msg.value = r.message || '激活成功'
      hexCode.value = ''
    } else {
      msg.value = (r && r.message) || '激活失败，请检查激活码后重试'
    }
  } catch (e) {
    msg.value = '激活失败：' + (e.message || '网络异常')
  } finally {
    busy.value = false
  }
}

function onClose() { store.closeAbout() }

onMounted(() => {
  nextTick(() => { if (!activated.value && inp.value) inp.value.focus() })
})
</script>

<style scoped>
.ab-mask { position: fixed; inset: 0; background: rgba(20,30,40,.42); display: flex; align-items: center; justify-content: center; z-index: 200; }
.ab-modal { width: 440px; max-width: 92vw; background: var(--panel); border: 1px solid var(--border);
  border-radius: 4px; box-shadow: 0 18px 50px rgba(0,0,0,.3); font-family: var(--ui); color: var(--text);
  padding: 18px 30px 22px; display: flex; flex-direction: column; align-items: center; text-align: center; }

.ab-head { width: 100%; display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.ab-title { font-size: 15px; font-weight: 700; letter-spacing: 1px; }
.ab-x { width: 24px; height: 24px; border: none; background: transparent; color: var(--muted);
  font-size: 16px; line-height: 1; cursor: pointer; border-radius: 4px; }
.ab-x:hover { background: var(--panel-2); color: var(--text); }

.ab-logo { width: 72px; height: 72px; border-radius: 6px; overflow: hidden; border: 1px solid var(--border);
  box-shadow: 0 6px 18px rgba(0,0,0,.18); display: flex; align-items: center; justify-content: center;
  background: var(--panel-2); }
.ab-logo img { width: 100%; height: 100%; object-fit: cover; }

.ab-name { margin-top: 14px; font-size: 19px; font-weight: 700; letter-spacing: 1.5px; }
.ab-sub { margin-top: 5px; font-size: 12px; line-height: 1.6; color: var(--muted); }
.ab-ver { margin-top: 12px; font-size: 12px; color: var(--accent); font-family: var(--mono); }

.ab-divider { margin-top: 16px; width: 100%; border-top: 1px solid var(--border); }
.ab-copy { margin-top: 12px; font-size: 12px; color: var(--faint); font-family: var(--mono); letter-spacing: .3px; }

/* —— 平台激活区域（与平台整体风格统一） —— */
.lic-status { width: 100%; display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 9px 12px;
  border-radius: 6px; border: 1px solid var(--border); background: var(--panel-2); text-align: left; }
.lic-status.on { border-color: color-mix(in srgb, var(--green) 40%, var(--border)); }
.lic-status.off { border-color: color-mix(in srgb, var(--red) 40%, var(--border)); }
.lic-badge { flex: none; font-size: 11px; font-weight: 600; padding: 2px 10px; border-radius: 2px; }
.lic-status.on .lic-badge { color: var(--green); background: rgba(46,158,99,.12); }
.lic-status.off .lic-badge { color: var(--red); background: rgba(209,75,75,.12); }
.lic-desc { font-size: 12px; color: var(--muted); line-height: 1.5; }

.lic-row { width: 100%; display: flex; align-items: center; gap: 8px; margin-top: 14px; }
.lic-row label { flex: none; font-size: 12px; color: var(--muted); width: 44px; text-align: left; }
.lic-input-wrap { flex: 1; min-width: 0; display: flex; align-items: center; background: var(--panel-2);
  border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.lic-input-wrap:focus-within { border-color: var(--accent);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 18%, transparent); }
.lic-prefix { flex: none; padding: 0 0 0 10px; font-size: 13px; font-family: var(--mono);
  letter-spacing: 1px; color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, var(--panel-2));
  align-self: stretch; display: flex; align-items: center; }
.lic-input { flex: 1; min-width: 0; padding: 8px 10px; font-size: 13px; font-family: var(--mono);
  letter-spacing: 1px; color: var(--text); background: transparent; border: none; outline: none; }
.lic-input:focus { box-shadow: none; }
.lic-input:disabled { opacity: .6; }
.lic-go { flex: none; min-width: 72px; padding: 8px 0; font-size: 13px; font-family: var(--ui); border-radius: 4px;
  cursor: pointer; color: #fff; background: var(--accent); border: 1px solid var(--accent); }
.lic-go:hover:not(:disabled) { background: var(--accent-d); border-color: var(--accent-d); }
.lic-go:disabled { opacity: .5; cursor: not-allowed; }

.lic-tip { width: 100%; margin-top: 10px; font-size: 11px; color: var(--faint); line-height: 1.6; text-align: left; }

.lic-msg { width: 100%; margin-top: 10px; font-size: 12px; line-height: 1.5; padding: 8px 10px; border-radius: 4px; }
.lic-msg.ok { color: var(--green); background: rgba(46,158,99,.10); }
.lic-msg.err { color: var(--red); background: rgba(209,75,75,.10); }

.ab-foot { margin-top: 18px; width: 100%; display: flex; justify-content: flex-end; }
.ab-ok { min-width: 96px; padding: 7px 0; font-size: 13px; font-family: var(--ui); border-radius: 4px; cursor: pointer;
  color: var(--accent); background: transparent; border: 1px solid var(--accent); }
.ab-ok:hover { color: #fff; background: var(--accent); border-color: var(--accent); }
</style>
