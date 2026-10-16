import { ref, onMounted, onBeforeUnmount } from 'vue'
import { visiblePoll } from './poll.js'

// 顶栏 / 底栏共享的系统时钟：YYYY-MM-DD HH:MM:SS，1Hz 走可见性感知轮询。
const clock = ref('')
let stopClock = null

function tick() {
  const d = new Date()
  const p = (x) => String(x).padStart(2, '0')
  clock.value = `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function useClock() {
  onMounted(() => {
    if (stopClock) return        // 单例：多组件挂载时只起一个轮询
    tick()
    stopClock = visiblePoll(tick, 1000)
  })
  onBeforeUnmount(() => {
    // 最后一个使用方卸载时才停轮询（极简：当前只有 TopBar 一处使用，到此即停）
    if (stopClock) { stopClock(); stopClock = null }
  })
  return clock
}
