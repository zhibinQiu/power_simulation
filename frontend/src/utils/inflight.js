/**
 * 在途请求合并（In-flight deduplication）。
 *
 * 背景：同一个加载函数常被多路触发源同时调用——例如 /api/box/overview 同时被
 * 3s 快轮询、30s 慢轮询、配置变更事件、手动刷新按钮调用，在 30s 边界上快/慢轮询
 * 必然落在同一 tick，同一份数据被请求两次；而 overview 是含云端状态的重接口。
 *
 * 语义：上一次调用尚未完成时，后续调用**共享同一个 Promise**，不再重复发请求。
 * 与「缓存」的区别：不按 TTL 复用旧结果（会读到过期数据），只合并并发的重复请求，
 * 请求完成后立即释放，下一次照常发起。
 *
 * 用法：
 *   const loadOverview = inflight(async () => { ... })
 */
export function inflight(fn) {
  let pending = null
  return function inflightWrapped(...args) {
    if (pending) return pending
    const self = this
    pending = Promise.resolve()
      .then(() => fn.apply(self, args))
      .finally(() => { pending = null })
    return pending
  }
}

/**
 * 节流版：在途合并 + 最小间隔（窗口内的重复调用直接复用上次结果，不发请求）。
 * 用于「多个组件几乎同时挂载都去拉同一份数据」这类场景（如各面板都拉设备清单）。
 *
 * 注意：会返回窗口内的**旧结果**，只适用于变化不频繁、允许短暂陈旧的数据。
 */
export function throttleAsync(fn, minIntervalMs = 1000) {
  let pending = null
  let lastDone = 0
  let lastResult = null
  return async function throttled(...args) {
    const now = Date.now()
    if (pending) return pending
    if (now - lastDone < minIntervalMs && lastResult !== null) return lastResult
    const self = this
    pending = Promise.resolve()
      .then(() => fn.apply(self, args))
      .then((r) => { lastResult = r; lastDone = Date.now(); return r })
      .finally(() => { pending = null })
    return pending
  }
}
