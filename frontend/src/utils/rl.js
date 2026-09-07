// 轻量 PPO（近端策略优化）实现：MLP 策略/价值网络 + Adam + GAE(λ)。
// 纯 JS、零依赖，默认网络 4→16→16→3（约 800 参数），可直接在浏览器主线程毫秒级训练。
//
// 面向「动态整定 PID 参数」的连续动作场景（与 PidControlView 配套）：
//   状态 s = [T̂, e, Δe, d̂]  —— 全部来自 EKF 的纯净估计（含传感器测不到的热扰动 d̂）
//   动作 a = [a_p, a_i, a_d] —— 对数空间增量，映射为 K = K₀ · exp(clip(a))
//   奖励 r = −(w₁|e| + w₂|Δe| + w₃·超调 + w₄·功耗)，功耗项倒逼节能
//
// 说明：这里只提供「智能体 + 优化器」，环境（过程仿真、奖励计算）由调用方实现。

const LOG2PI = 0.9189385332046727

/** 标准正态采样（Box–Muller） */
export function randn() {
  let u = 0, v = 0
  while (u === 0) u = Math.random()
  while (v === 0) v = Math.random()
  return Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v)
}

function zeros(n) { return new Float64Array(n) }

/**
 * 全连接 MLP（隐藏层 tanh，输出层线性），支持手写反向传播。
 * sizes 例：[4, 16, 16, 3]
 */
export function createMlp(sizes, seed = 1) {
  let s = seed >>> 0 || 1
  const rnd = () => {
    s = (s * 1103515245 + 12345) & 0x7fffffff
    return (s / 0x7fffffff) * 2 - 1
  }
  const layers = []
  for (let l = 0; l < sizes.length - 1; l++) {
    const nIn = sizes[l], nOut = sizes[l + 1]
    const W = new Float64Array(nIn * nOut)
    const b = zeros(nOut)
    const sc = Math.sqrt(2 / (nIn + nOut))
    for (let i = 0; i < W.length; i++) W[i] = rnd() * sc
    layers.push({
      nIn, nOut, W, b,
      dW: zeros(nIn * nOut), db: zeros(nOut),
      tanh: l < sizes.length - 2, // 最后一层线性输出
    })
  }

  function forward(x, cache) {
    cache.length = 0
    let cur = x
    for (const L of layers) {
      const z = new Float64Array(L.nOut)
      for (let o = 0; o < L.nOut; o++) {
        let v = L.b[o]
        for (let i = 0; i < L.nIn; i++) v += L.W[i * L.nOut + o] * cur[i]
        z[o] = v
      }
      const a = new Float64Array(L.nOut)
      for (let o = 0; o < L.nOut; o++) a[o] = L.tanh ? Math.tanh(z[o]) : z[o]
      cache.push({ x: cur, a, L })
      cur = a
    }
    return cur
  }

  /** 反向传播：dOut = dL/d(output)，梯度累加到各层 dW/db，返回 dL/dx */
  function backward(dOut, cache) {
    let dz = dOut
    for (let li = layers.length - 1; li >= 0; li--) {
      const c = cache[li]
      const L = c.L
      const d = new Float64Array(L.nOut)
      for (let o = 0; o < L.nOut; o++) d[o] = L.tanh ? dz[o] * (1 - c.a[o] * c.a[o]) : dz[o]
      for (let i = 0; i < L.nIn; i++) {
        const xi = c.x[i]
        for (let o = 0; o < L.nOut; o++) L.dW[i * L.nOut + o] += d[o] * xi
      }
      for (let o = 0; o < L.nOut; o++) L.db[o] += d[o]
      const dx = new Float64Array(L.nIn)
      for (let i = 0; i < L.nIn; i++) {
        let v = 0
        for (let o = 0; o < L.nOut; o++) v += L.W[i * L.nOut + o] * d[o]
        dx[i] = v
      }
      dz = dx
    }
  }

  return {
    layers,
    forward,
    backward,
    zeroGrad() { for (const L of layers) { L.dW.fill(0); L.db.fill(0) } },
    params() { return layers.map((L) => L.W).concat(layers.map((L) => L.b)) },
    grads() { return layers.map((L) => L.dW).concat(layers.map((L) => L.db)) },
  }
}

/** Adam 优化器（就地更新传入的参数数组，梯度需调用方自行归一化） */
export function createAdam(paramLists, lr = 3e-3, b1 = 0.9, b2 = 0.999, eps = 1e-8) {
  const m = paramLists.map((p) => new Float64Array(p.length))
  const v = paramLists.map((p) => new Float64Array(p.length))
  let t = 0
  return {
    step(gradLists) {
      t++
      const c1 = 1 - Math.pow(b1, t)
      const c2 = 1 - Math.pow(b2, t)
      for (let k = 0; k < paramLists.length; k++) {
        const p = paramLists[k], g = gradLists[k]
        if (!g) continue
        for (let i = 0; i < p.length; i++) {
          m[k][i] = b1 * m[k][i] + (1 - b1) * g[i]
          v[k][i] = b2 * v[k][i] + (1 - b2) * g[i] * g[i]
          const mh = m[k][i] / c1
          const vh = v[k][i] / c2
          p[i] -= lr * mh / (Math.sqrt(vh) + eps) // 最小化损失 → 梯度下降
        }
      }
    },
  }
}

/** 零均值单位方差标准化（优势归一化，稳定 PPO 更新） */
export function standardize(x) {
  const n = x.length
  if (!n) return x
  let mu = 0
  for (let i = 0; i < n; i++) mu += x[i]
  mu /= n
  let va = 0
  for (let i = 0; i < n; i++) va += (x[i] - mu) * (x[i] - mu)
  va /= n
  const sd = Math.sqrt(va) || 1
  const out = new Float64Array(n)
  for (let i = 0; i < n; i++) out[i] = (x[i] - mu) / sd
  return out
}

/** GAE(λ) 优势与回报 */
export function computeGae(rews, vals, lastVal, gamma = 0.99, lam = 0.95) {
  const n = rews.length
  const adv = new Float64Array(n)
  const ret = new Float64Array(n)
  let g = 0
  for (let i = n - 1; i >= 0; i--) {
    const nv = i === n - 1 ? lastVal : vals[i + 1]
    const delta = rews[i] + gamma * nv - vals[i]
    g = delta + gamma * lam * g
    adv[i] = g
    ret[i] = g + vals[i]
  }
  return { adv, ret }
}

/**
 * PPO 智能体：高斯策略（可学习 log σ）+ 状态价值网络
 * @returns {{ act, value, update, sigma }}
 */
export function createPpoAgent({
  sDim = 4, aDim = 3, hidden = 16, lr = 3e-3, sigma0 = 0.4,
} = {}) {
  const actor = createMlp([sDim, hidden, hidden, aDim], 12345)
  const critic = createMlp([sDim, hidden, hidden, 1], 54321)
  const logStd = new Float64Array(aDim).fill(Math.log(sigma0))
  const dLogStd = new Float64Array(aDim)
  const LOGS_LO = Math.log(0.02)   // 探索幅度下限
  const LOGS_HI = Math.log(1.2)    // 探索幅度上限

  const actorParams = [...actor.params(), logStd]
  const actorOpt = createAdam(actorParams, lr)
  const criticOpt = createAdam(critic.params(), lr)

  /** 采样动作：返回 { a, logp, cache, mean }（deterministic 时用均值动作） */
  function act(s, deterministic = false) {
    const cache = []
    const mean = actor.forward(s, cache)
    const a = new Float64Array(aDim)
    let logp = 0
    for (let k = 0; k < aDim; k++) {
      const sd = Math.exp(logStd[k])
      const v = deterministic ? mean[k] : mean[k] + sd * randn()
      a[k] = v
      const z = (v - mean[k]) / sd
      logp += -0.5 * z * z - logStd[k] - LOG2PI
    }
    return { a, logp, cache, mean }
  }

  function value(s) {
    return critic.forward(s, [])[0]
  }

  /**
   * PPO 更新：裁剪 surrogate + 价值损失 + 熵奖励
   * trans: [{ s, a, logp, adv, ret }]
   */
  function update(trans, {
    clip = 0.2, epochs = 4, entCoef = 0.01, vfCoef = 0.5, batchSize = 64,
  } = {}) {
    const n = trans.length
    if (!n) return { lossP: 0, lossV: 0 }
    const idx = new Array(n)
    for (let i = 0; i < n; i++) idx[i] = i
    let lossP = 0, lossV = 0

    for (let e = 0; e < epochs; e++) {
      for (let i = n - 1; i > 0; i--) {
        const j = Math.floor(Math.random() * (i + 1))
        const t = idx[i]; idx[i] = idx[j]; idx[j] = t
      }
      for (let st = 0; st < n; st += batchSize) {
        const mb = idx.slice(st, st + batchSize)
        actor.zeroGrad()
        critic.zeroGrad()
        dLogStd.fill(0)
        for (const i of mb) {
          const tr = trans[i]
          // —— 策略梯度 ——
          const cache = []
          const mean = actor.forward(tr.s, cache)
          let logp = 0
          const zs = new Float64Array(aDim)
          for (let k = 0; k < aDim; k++) {
            const sd = Math.exp(logStd[k])
            const z = (tr.a[k] - mean[k]) / sd
            zs[k] = z
            logp += -0.5 * z * z - logStd[k] - LOG2PI
          }
          const ratio = Math.exp(Math.max(-20, Math.min(20, logp - tr.logp)))
          const A = tr.adv
          const clipped = A >= 0 ? Math.min(ratio, 1 + clip) * A : Math.max(ratio, 1 - clip) * A
          const useClip = (A >= 0 && ratio > 1 + clip) || (A < 0 && ratio < 1 - clip)
          const g = useClip ? 0 : A            // d(min)/dlogπ = g，损失取负 → dL/dlogπ = -g
          lossP += -(useClip ? clipped : ratio * A)
          const dOut = new Float64Array(aDim)
          for (let k = 0; k < aDim; k++) {
            const sd = Math.exp(logStd[k])
            dOut[k] = -g * (zs[k] / sd)        // dL/dmean
            dLogStd[k] += -g * (zs[k] * zs[k] - 1) // dL/dlogσ
            dLogStd[k] += -entCoef             // 熵奖励
          }
          actor.backward(dOut, cache)

          // —— 价值梯度 ——
          const cc = []
          const v = critic.forward(tr.s, cc)[0]
          lossV += (v - tr.ret) * (v - tr.ret)
          critic.backward(new Float64Array([2 * vfCoef * (v - tr.ret)]), cc)
        }
        const sc = 1 / mb.length
        const gA = actor.grads()
        const gC = critic.grads()
        for (const g of gA) for (let i = 0; i < g.length; i++) g[i] *= sc
        for (const g of gC) for (let i = 0; i < g.length; i++) g[i] *= sc
        for (let k = 0; k < aDim; k++) dLogStd[k] *= sc
        actorOpt.step([...gA, dLogStd])
        criticOpt.step(gC)
        for (let k = 0; k < aDim; k++) {
          if (logStd[k] < LOGS_LO) logStd[k] = LOGS_LO
          if (logStd[k] > LOGS_HI) logStd[k] = LOGS_HI
        }
      }
    }
    return { lossP: lossP / (n * epochs), lossV: lossV / (n * epochs) }
  }

  return {
    act,
    value,
    update,
    aDim,
    /** 当前探索幅度（σ） */
    sigma() { return Array.from(logStd).map((v) => Math.exp(v)) },
  }
}
