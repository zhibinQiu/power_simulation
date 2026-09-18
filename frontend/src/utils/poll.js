// 轮询统一收口：页面不可见（后台标签页 / 窗口最小化）时跳过本轮，重新可见时立即补一轮。
//
// 为什么需要：平台上同时跑着多路周期轮询（能碳一体机 3s/10s/30s、实时源 3s、
// 优化器 3s、数据概览 1s/10s…）。浏览器虽会降频后台定时器，但不会停——切到别的
// 标签后它们仍在拉取全量数据并触发整块响应式重算，前台标签因此变卡。
// 统一走这里后：后台标签零请求零渲染，切回来立刻补一轮（不必等满一个周期）。

function hidden() {
  return typeof document !== 'undefined' && document.hidden === true
}

/** 页面当前是否可见（后台标签 / 最小化时为 false）。 */
export function isPageVisible() { return !hidden() }

/**
 * 可见性感知的周期任务，语义等价于 setInterval(fn, ms)。
 * @param {Function} fn 每轮执行
 * @param {number} ms 周期（毫秒）
 * @param {{immediate?: boolean}} opts immediate=true 时立即执行第一轮
 * @returns {Function} 停止函数（在 onBeforeUnmount 里调用）
 */
export function visiblePoll(fn, ms, opts = {}) {
  let stopped = false
  let timer = null
  const run = () => { if (!stopped && !hidden()) fn() }
  const schedule = () => {
    timer = setTimeout(() => { if (stopped) return; run(); schedule() }, ms)
  }
  if (opts.immediate) run()
  schedule()

  // 重新可见：丢掉旧的等待周期，立刻补一轮并对齐新周期
  const onVis = () => {
    if (stopped || hidden()) return
    if (timer) clearTimeout(timer)
    run()
    schedule()
  }
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', onVis)
  }
  return () => {
    stopped = true
    if (timer) clearTimeout(timer)
    if (typeof document !== 'undefined') {
      document.removeEventListener('visibilitychange', onVis)
    }
  }
}
