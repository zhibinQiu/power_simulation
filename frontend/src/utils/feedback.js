// 即时反馈引擎（PTC Design System 多模态体验：动效 + 声音）
// 操作后提供视觉（toast/进度条）与听觉（合成音）的积极反馈。
// 声音由 Web Audio API 实时合成，无音频文件依赖；开关存 localStorage。
let _ctx = null
const SOUND_KEY = 'cb-ui-sound'

function ctx() {
  if (typeof window === 'undefined') return null
  if (!_ctx) {
    try {
      const AC = window.AudioContext || window.webkitAudioContext
      if (!AC) return null
      _ctx = new AC()
    } catch (e) { return null }
  }
  if (_ctx && _ctx.state === 'suspended') { try { _ctx.resume() } catch (e) { /* ignore */ } }
  return _ctx
}

export function soundEnabled() {
  try { return localStorage.getItem(SOUND_KEY) !== '0' } catch (e) { return true }
}
export function setSoundEnabled(on) {
  try { localStorage.setItem(SOUND_KEY, on ? '1' : '0') } catch (e) { /* ignore */ }
}
export function toggleSound() {
  const v = !soundEnabled()
  setSoundEnabled(v)
  if (v) playSound('info')
  return v
}

// 合成单个音
function tone(freq, start, dur, { type = 'sine', gain = 0.18, attack = 0.008, release = 0.06 } = {}) {
  const c = ctx()
  if (!c) return
  const t0 = c.currentTime + start
  const osc = c.createOscillator()
  const g = c.createGain()
  osc.type = type
  osc.frequency.setValueAtTime(freq, t0)
  g.gain.setValueAtTime(0, t0)
  g.gain.linearRampToValueAtTime(gain, t0 + attack)
  g.gain.setValueAtTime(gain, Math.max(t0, t0 + dur - release)) // 短音时 dur-release 可能为负，钳制到 t0 避免 AudioParam 时间非法
  g.gain.linearRampToValueAtTime(0.0001, t0 + dur)
  osc.connect(g)
  g.connect(c.destination)
  osc.start(t0)
  osc.stop(t0 + dur + 0.02)
}

// 播放类型化反馈音（与通知/消息级别一一对应）
export function playSound(type = 'info') {
  if (!soundEnabled()) return
  const t = String(type || 'info').toLowerCase()
  switch (t) {
    case 'success':
      tone(659.25, 0, 0.16, { type: 'triangle', gain: 0.2 })    // E5
      tone(987.77, 0.12, 0.24, { type: 'triangle', gain: 0.2 })  // B5 上扬 = 成功
      break
    case 'done':
      tone(523.25, 0, 0.12, { type: 'triangle', gain: 0.18 })    // C5
      tone(659.25, 0.1, 0.12, { type: 'triangle', gain: 0.18 })  // E5
      tone(783.99, 0.2, 0.22, { type: 'triangle', gain: 0.2 })   // G5 三连音 = 任务完成
      break
    case 'warn':
      tone(523.25, 0, 0.16, { type: 'sine', gain: 0.2 })         // C5
      tone(659.25, 0.18, 0.2, { type: 'sine', gain: 0.2 })       // E5 双音 = 提醒
      break
    case 'error':
      tone(392.0, 0, 0.2, { type: 'sawtooth', gain: 0.13 })      // G4
      tone(261.63, 0.16, 0.3, { type: 'sawtooth', gain: 0.13 })  // C4 下行 = 错误
      break
    case 'click':
      tone(880, 0, 0.05, { type: 'sine', gain: 0.06 })
      break
    default: // info：轻提示
      tone(659.25, 0, 0.12, { type: 'sine', gain: 0.11 })        // E5
  }
}

// 首次用户交互时预热音频上下文（浏览器自动播放策略要求先有手势）
export function primeAudio() { ctx() }
if (typeof window !== 'undefined') {
  window.addEventListener('pointerdown', primeAudio, { once: true })
}

// —— 全局点击音效（HMI：操作即反馈，所有可操作控件点击轻响）——
// 事件委托 + 捕获阶段：按钮/开关/选项卡/菜单项/折叠头等点击播轻量 tick；
// 文本输入、range 拖拽、textarea 等持续交互不响，50ms 防抖防连点爆音。
let _lastClickAt = 0
function _actionable(el) {
  if (!el || el.nodeType !== 1) return false
  if (el.closest('.ctab')) return false  // 命令行窗口页签切换不播放点击音效
  if (el.closest('input, textarea, [contenteditable="true"]')) {
    if (el.tagName === 'TEXTAREA') return false
    if (el.tagName === 'INPUT') {
      const type = (el.type || '').toLowerCase()
      if (!type || ['text', 'number', 'password', 'search', 'email', 'tel', 'url', 'range', 'date', 'time', 'hidden', 'file'].includes(type)) return false
    }
  }
  return !!el.closest(
    'button, [role="button"], [role="tab"], [role="menuitem"], [role="option"], [role="checkbox"], [role="radio"], [role="switch"], ' +
    '.tbtn, .rbtn, .btn, .tiny-btn, .pv-btn, .sw, .ss-sw, .mi, .mbar-item, .tab, .view-switch, .twin-tool-btn, ' +
    '.chead, .chp, .chip, .tag, .menu-item, .litem, .acc-head, .selrow, .kv-btn, .x-btn, .topbar-btn'
  )
}
export function enableClickSound() {
  if (typeof window === 'undefined') return
  window.addEventListener('click', (e) => {
    const el = e.target
    if (!_actionable(el)) return
    const now = Date.now()
    if (now - _lastClickAt < 50) return
    _lastClickAt = now
    playSound('click')
  }, true)
}
enableClickSound()
