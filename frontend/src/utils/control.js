// 控制与滤波算法工具：PID 控制器 + 在线卡尔曼滤波（一维 EKF 常见形态，标量测量）。
// 均为纯函数/闭包实现，不依赖 Vue，可单测。
//
// —— 在线卡尔曼滤波 ——
// 模型：状态 = 被滤值 x（随机游走），测量 z = x + v。
//   预测：P⁻ = P + q·dt（q：过程噪声方差，每单位时间值漂移的不确定度）
//   更新：K = P⁻/(P⁻+r)；x += K(z−x)；P = (1−K)·P⁻
// q/r 单位与测量同尺度平方；q 越小越平滑（滞后越大），r 越小越跟手（越粗糙）。

/** 高斯噪声（Box–Muller） */
export function gauss() {
  let u = 0, v = 0
  while (u === 0) u = Math.random()
  while (v === 0) v = Math.random()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
}

/** 创建在线卡尔曼滤波器实例 */
export function createKalman(opts = {}) {
  let x = null // 滤波值
  let P = 0 // 估计方差
  let lastT = null
  const cfg = { q: 0.01, r: 1, ...opts }

  const reset = (o = null) => {
    if (o) Object.assign(cfg, o)
    x = null; P = 0; lastT = null
  }
  const set = (o) => Object.assign(cfg, o)

  /**
   * 输入一个新观测。t 为 epoch 秒/毫秒均可（只取差值），首次调用直接初始化。
   * 返回 { x: 滤波值, k: 卡尔曼增益, p: 后验方差 }
   */
  const step = (z, t, o = null) => {
    if (o) Object.assign(cfg, o)
    if (z == null || !Number.isFinite(z)) return { x, k: 0, p: P }
    if (x == null) {
      x = z; P = 1; lastT = t == null ? 0 : t
      return { x, k: 1, p: P }
    }
    const dt = t == null || lastT == null ? 1 : Math.max(0.05, Math.min(120, t - lastT))
    P += cfg.q * dt // 预测：方差随时间发散（过程噪声驱动）
    const K = P / (P + cfg.r) // 更新：卡尔曼增益
    x += K * (z - x)
    P = (1 - K) * P
    lastT = t
    return { x, k: K, p: P }
  }

  return { step, reset, set, get x() { return x } }
}

/**
 * 对一段完整序列离线/批量滤波（与在线 step 同模型）。
 * pts: [{t, v}]（正序）；返回 [{t, v}]（滤后）。v 为空值的点跳过并重置状态。
 */
export function kalmanSmooth(pts, opts = {}) {
  const kf = createKalman(opts)
  const out = []
  if (!Array.isArray(pts)) return out
  for (const p of pts) {
    if (p.v == null || !Number.isFinite(p.v)) { kf.reset(); continue }
    kf.step(p.v, p.t)
    out.push({ t: p.t, v: kf.x })
  }
  return out
}

/**
 * 二维扩展卡尔曼（增广状态）：x = [T, d]
 *   T：被估量（观测量真值，如温度）的滤波值 T̂
 *   d：传感器测不到的未建模扰动（如机房热扰动）d̂，按随机游走建模
 * 过程模型（离散一阶）：T⁺ = a·T + b·u + c + d；d⁺ = d；观测：z = T + v
 * 有在线辨识的过程模型时传入 (a,b,c)；无模型时退化 a=1,b=0,c=0（常值 + 扰动估计）。
 * 返回 { t: T̂, d: d̂, k: [K0, K1] }
 */
export function createEkf2(opts = {}) {
  const cfg = { a: 1, b: 0, c: 0, qT: 0.01, qd: 0.001, r: 1, ...opts }
  let T = null
  let d = 0
  let p00 = 0, p01 = 0, p10 = 0, p11 = 0
  let init = false

  const reset = (o = null) => {
    if (o) Object.assign(cfg, o)
    T = null; d = 0; p00 = p01 = p10 = p11 = 0; init = false
  }
  const set = (o) => Object.assign(cfg, o)

  const step = (z, u = 0, o = null) => {
    if (o) Object.assign(cfg, o)
    if (z == null || !Number.isFinite(z)) return { t: T, d, k: [0, 0] }
    if (!init) {
      T = z; d = 0
      p00 = cfg.r; p01 = 0; p10 = 0; p11 = Math.max(cfg.qd * 10, 1e-6)
      init = true
      return { t: T, d, k: [1, 0] }
    }
    const { a, b, c, qT, qd, r } = cfg
    // —— 预测：x⁻ = f(x, u)，F = [[a,1],[0,1]] ——
    const tPre = a * T + b * (Number(u) || 0) + c + d
    const dPre = d
    // P⁻ = F·P·Fᵗ + Q
    const fp00 = a * p00 + p10, fp01 = a * p01 + p11
    const fp10 = p10, fp11 = p11
    const m00 = fp00 * a + fp01 + qT
    const m01 = fp01
    const m10 = a * p10 + p11
    const m11 = p11 + qd

    // —— 更新：H = [1, 0] ——
    const S = m00 + r
    if (!(Math.abs(S) > 1e-18)) return { t: tPre, d: dPre, k: [0, 0] }
    const k0 = m00 / S
    const k1 = m10 / S
    const innov = z - tPre
    T = tPre + k0 * innov
    d = dPre + k1 * innov
    // P⁺ = (I − K·H)·P⁻
    const n00 = (1 - k0) * m00
    const n01 = (1 - k0) * m01
    const n10 = -k1 * m00 + m10
    const n11 = -k1 * m01 + m11
    // 对称化，避免数值漂移
    p00 = n00; p11 = n11
    p01 = p10 = (n01 + n10) / 2
    return { t: T, d, k: [k0, k1] }
  }

  return { step, reset, set, get t() { return T }, get d() { return d } }
}

// —— PID 控制器（位置式 + 积分抗饱和） ——
// u = kp·e + ki·∫e·dt + kd·de/dt，输出夹在 [min, max]。
// 抗饱和：输出饱和时冻结积分累加（conditional integration），避免 windup。
export function createPid(opts = {}) {
  let cfg = {
    kp: 1, ki: 0.05, kd: 0, min: -Infinity, max: Infinity,
    ...opts,
  }
  let eInt = 0
  let ePrev = null
  let u = 0

  const set = (o) => { cfg = { ...cfg, ...o } }
  const reset = () => { eInt = 0; ePrev = null; u = 0 }

  /**
   * 单步计算。dt 秒。返回 { u, e, p, i, d, saturated }
   */
  const step = (sp, meas, dt = 1) => {
    const dts = dt > 0 ? dt : 1
    const e = sp - meas
    const eD = ePrev == null ? 0 : (e - ePrev) / dts
    const iLimit = Math.abs(cfg.ki) > 1e-12
      ? (cfg.max - cfg.min) / Math.abs(cfg.ki) * 1.5 // 积分钳制：满积分约等于输出满量程
      : 0
    eInt += e * dts
    if (iLimit > 0 && eInt > iLimit) eInt = iLimit
    if (iLimit > 0 && eInt < -iLimit) eInt = -iLimit

    let out = cfg.kp * e + cfg.ki * eInt + cfg.kd * eD
    let saturated = false
    if (out > cfg.max) { out = cfg.max; saturated = true }
    else if (out < cfg.min) { out = cfg.min; saturated = true }
    // 条件积分：饱和且误差同向时冻结积分，避免过冲
    if (saturated && Math.sign(e) === Math.sign(out)) {
      eInt -= e * dts
    }
    u = out
    ePrev = e
    return { u, e, p: cfg.kp * e, i: cfg.ki * eInt, d: cfg.kd * eD, saturated }
  }

  return { step, set, reset, get cfg() { return cfg }, get out() { return u }, get ePrev() { return ePrev } }
}
