// AI 群控：算法/场景/目标的「声明式注册表」+ 统一闭环仿真与在线控制器。
//
// 设计原则
//  1) 场景无关：把「机房热控」抽象成控制回路（CV 被控量 / MV 调节量 / DV 扰动观测量 / MON 监视量），
//     不再在算法里写死温度、水泵、T_amb 等语义；换场景只换变量映射与物理先验。
//  2) 算法无关：所有寻优算法（GA/PSO/模式搜索/SAC）都跑在同一个闭环仿真器上、用同一套代价项，
//     因此不同算法的结果可直接比较；新增算法只需往 ALGORITHMS 注册一份「超参 schema + 状态机」。
//  3) 超参全暴露：每个超参带默认值/范围/单位/说明，UI 由 schema 渲染，不存在藏在代码里的魔法数。
//  4) 归一化固定：状态/动作都用「固定的物理区间」做 min-max，不再用实时值做基准（避免策略输入分布漂移）。
//  5) 分层时序明确：SAC 外环按 sacDt 决策，PID 内环按 dt 跟踪；两者可分别配置。
//
// 本模块不依赖 Vue，可单测。

import { createRng, createSacAgent, agentFromSnapshot, SAC_DEFAULTS } from './rl'
import { createPid, createEkf3 } from './control'

// ───────────────────────────── 通用工具 ─────────────────────────────

export const clamp = (v, lo, hi) => (v < lo ? lo : v > hi ? hi : v)
export const clamp01 = (v) => clamp(v, 0, 1)
export const num = (v, d = 0) => (Number.isFinite(Number(v)) ? Number(v) : d)
/** 安全取区间（保证 hi > lo） */
export function span(lo, hi, minSpan = 1e-9) {
  const a = num(lo, 0), b = num(hi, 1)
  return b - a > minSpan ? { lo: a, hi: b } : { lo: Math.min(a, b), hi: Math.min(a, b) + minSpan }
}
/** 归一化到 0~1（越界允许小幅外推，便于策略感知越界） */
export function norm01(v, lo, hi) {
  const s = span(lo, hi)
  return clamp((num(v, s.lo) - s.lo) / (s.hi - s.lo), -1, 2)
}
export function denorm01(n, lo, hi) {
  const s = span(lo, hi)
  return s.lo + clamp01(n) * (s.hi - s.lo)
}

// ─────────────────────── 变量角色 / 场景模板 ───────────────────────

/** 回路内变量的角色定义（换场景只改映射，不改算法） */
export const VAR_ROLES = [
  { id: 'cv', label: '被控量 CV', short: 'CV', desc: '被调节的目标量，算法要把它稳定在目标值附近' },
  { id: 'mv', label: '调节量 MV', short: 'MV', desc: '算法实际下发的执行量（阀位/频率/功率/流量设定）' },
  { id: 'dv', label: '扰动观测量 DV', short: 'DV', desc: '可选：与负载相关的可测环境量，供 EKF 观测扰动状态' },
  { id: 'mon', label: '监视量 MON', short: 'MON', desc: '只看不控，用于展示与告警' },
]

/**
 * 场景模板：只给默认物理先验与两类约束的初值，变量绑定仍由用户在界面上完成。
 *  adj：可调约束（硬）——执行器量程与速率能力
 *  obs：观测约束（软）——对观测设备的期望区间，逐条带权重
 */
export const SCENARIO_TEMPLATES = [
  {
    id: 'dc-thermal',
    label: '机房热控',
    desc: '冷冻水/风机转速 → 机房温度；负载扰动由 IT 功耗驱动，安全方向为「不许超温」',
    hints: { powerExp: 3, gainSign: -1, tauHint: 90, cvUnit: '℃', mvUnit: '%', cvLo: 18, cvHi: 32, mvLo: 0, mvHi: 100 },
    adj: { lo: 0, hi: 100, rateMax: 8, minStep: 0 },
    obs: [
      { id: 'cv-hi', var: 'cv', dir: 'high', hi: 27, weight: 2, label: '超温上限' },
      { id: 'cv-lo', var: 'cv', dir: 'low', lo: 18, weight: 1, label: '低温下限' },
    ],
  },
  {
    id: 'steel-draft',
    label: '钢铁过程·风量给料',
    desc: '风机频率/给料量 → 炉温或料位；调节量增大使被控量上升，安全方向为双边区间',
    hints: { powerExp: 3, gainSign: 1, tauHint: 150, cvUnit: '', mvUnit: 'Hz', cvLo: 0, cvHi: 100, mvLo: 0, mvHi: 50 },
    adj: { lo: 0, hi: 50, rateMax: 5, minStep: 0 },
    obs: [{ id: 'cv-band', var: 'cv', dir: 'band', lo: 30, hi: 70, weight: 1, label: '工艺允许区间' }],
  },
  {
    id: 'pump-flow',
    label: '泵阀·流量压力',
    desc: '泵频率/阀位 → 流量或压力；阀位开度与流量近似线性，功耗按开度一次方计',
    hints: { powerExp: 1, gainSign: 1, tauHint: 30, cvUnit: '', mvUnit: '%', cvLo: 0, cvHi: 120, mvLo: 0, mvHi: 100 },
    adj: { lo: 0, hi: 100, rateMax: 10, minStep: 0 },
    obs: [{ id: 'cv-hi', var: 'cv', dir: 'high', hi: 110, weight: 1, label: '压力上限' }],
  },
  {
    id: 'custom', label: '自定义', desc: '完全自定义变量映射与物理先验',
    hints: { powerExp: 2, gainSign: 0, tauHint: 60, cvUnit: '', mvUnit: '', cvLo: 0, cvHi: 100, mvLo: 0, mvHi: 100 },
    adj: { lo: 0, hi: 100, rateMax: 0, minStep: 0 },
    obs: [],
  },
]

export const templateById = (id) => SCENARIO_TEMPLATES.find((s) => s.id === id) || SCENARIO_TEMPLATES[0]

// ─────────────────────── 目标项（奖励/代价）注册表 ───────────────────────

/**
 * 统一目标项：奖励 r = −Σ wᵢ·termᵢ，寻优算法最小化同一 cost = Σ wᵢ·termᵢ。
 * 因此「奖励项」与「目标项」是同一份注册表，只是符号不同 —— 避免 RL 与 GA/PSO 目标不一致。
 * term 均为无量纲归一化量，权重才有可比性。
 */
export const OBJECTIVE_TERMS = [
  { id: 'track', label: '跟踪误差', def: 1, min: 0, max: 30, step: 0.05, desc: '|CV − 目标值| / 量程，反映贴合目标的程度（最核心项）' },
  { id: 'overshoot', label: '超调', def: 0.6, min: 0, max: 30, step: 0.05, desc: '越过目标值方向的偏差 / 量程，抑制过冲' },
  { id: 'power', label: '能耗', def: 0.35, min: 0, max: 30, step: 0.05, desc: '(开度归一化)^幂次，按场景选择风机立方律 / 阀门线性律' },
  { id: 'move', label: '调节量变化', def: 0.08, min: 0, max: 30, step: 0.01, desc: '|ΔMV| / 量程，抑制执行器频繁动作' },
  { id: 'jitter', label: '调节量抖动', def: 0.02, min: 0, max: 30, step: 0.005, desc: '|Δ²MV| / 量程，抑制高频抖动' },
  { id: 'spChg', label: '设定值变化', def: 0.05, min: 0, max: 30, step: 0.01, desc: '|Δ内环设定| / 量程，抑制设定值来回跳变' },
  { id: 'safety', label: '观测约束越界', def: 1, min: 0, max: 60, step: 0.05, desc: '【软约束】各观测约束越界幅度（按各自量程归一化、按各自权重加权）之和；此处为总权重倍数，单条权重在「观测约束」表中逐条设定' },
  { id: 'viol', label: '可调约束违反', def: 8, min: 0, max: 200, step: 0.5, desc: '【硬约束】执行量被量程/速率/最小步长裁剪掉的幅度（归一化）。启动段短暂非 0 属正常；稳态持续非 0 说明整定过激进或速率上限过严' },
]

export const defaultWeights = () => {
  const w = {}
  for (const t of OBJECTIVE_TERMS) w[t.id] = t.def
  return w
}

/**
 * 计算单步目标项（训练与在线运行共用同一实现，保证口径一致）。
 * @param {object} c { e, scale, un, unPrev, unPrev2, sp, spPrev, safety, viol, dirSign, powerExp }
 *   safety：观测约束的加权越界量（已归一化，由 obsPenalty 给出）
 *   viol  ：可调约束的违反量（已归一化，由 applyAdjLimit 给出）
 */
export function termsOf(c) {
  const sc = Math.max(Math.abs(num(c.scale, 1)), 1e-9)
  const un = clamp01(num(c.un, 0))
  const unPrev = num(c.unPrev, un)
  const unPrev2 = num(c.unPrev2, unPrev)
  const e = num(c.e, 0)
  const dir = num(c.dirSign, 0)
  return {
    track: Math.abs(e) / sc,
    overshoot: dir === 0 ? 0 : Math.max(0, e * dir) / sc,
    power: Math.pow(un, Math.max(0.2, num(c.powerExp, 3))),
    move: Math.abs(un - unPrev),
    jitter: Math.abs(un - 2 * unPrev + unPrev2),
    spChg: Math.abs(num(c.sp, 0) - num(c.spPrev, num(c.sp, 0))) / sc,
    safety: Math.max(0, num(c.safety, num(c.over, 0) / sc)),
    viol: Math.max(0, num(c.viol, 0)),
  }
}

/** cost = Σ wᵢ·termᵢ（奖励 r = −cost） */
export function costOf(weights, t) {
  let s = 0
  for (const k in t) s += num(weights && weights[k], 0) * t[k]
  return s
}

// ─────────────────────── 约束（两类，分别设定） ───────────────────────
//
// ① 可调约束（硬）：作用在「可调设备」的输出量上，必须无条件满足 —— 输出裁剪 + 速率限幅 + 最小步长。
//    违反量（viol）是「控制器想要、但设备给不出」的幅度（归一化），只用于兜底惩罚与诊断：
//    · 启动段 / 大扰动段短暂非 0 属正常（执行器物理上追不上），此时会顺带冻结 PID 积分；
//    · 稳态持续非 0 说明整定过于激进或速率上限过严，属配置问题，不靠惩罚项去「学」。
// ② 观测约束（软）：作用在「观测设备」的量上（被控量 CV / 扰动观测量 DV / 监视量 MON），
//    每条约束自带方向、阈值与权重，越界幅度按各自量程归一化后加权求和，计入代价（不裁剪任何输出）。

/** 可调约束字段（硬约束，逐项对应一个执行器） */
export const ADJ_LIMIT_FIELDS = [
  { key: 'lo', label: '下限', def: 0, desc: '执行量允许的最小值（硬性裁剪）' },
  { key: 'hi', label: '上限', def: 100, desc: '执行量允许的最大值（硬性裁剪）' },
  { key: 'rateMax', label: '最大变化速率', def: 0, desc: '单位时间允许的最大变化量；0 = 不限速' },
  { key: 'minStep', label: '最小有效步长', def: 0, desc: '小于该值的调节量视为不动（防执行器抖动）；0 = 不启用' },
]

/** 由回路配置推导可调约束（兼容只填了 uLo/uHi/uRateMax 的老配置） */
export function adjLimitOf(loop) {
  const l = loop || {}
  const a = l.adj || {}
  return {
    lo: num(a.lo, num(l.uLo, 0)),
    hi: num(a.hi, num(l.uHi, 100)),
    rateMax: num(a.rateMax, num(l.uRateMax, 0)),
    minStep: num(a.minStep, 0),
  }
}

/**
 * 施加硬约束（可调设备）：把「控制器想要的量」夹到设备允许范围内。
 * @returns {{u:number, viol:number}} viol 为归一化违反量（兜底惩罚用）
 */
export function applyAdjLimit(lim, uWant, uPrev, dt, scale) {
  const sc = Math.max(num(scale, 1), 1e-9)
  const hi = num(lim && lim.hi, Infinity), lo = num(lim && lim.lo, -Infinity)
  let u = num(uWant, uPrev)
  let viol = 0
  if (u > hi) { viol += (u - hi) / sc; u = hi } else if (u < lo) { viol += (lo - u) / sc; u = lo }
  const rm = num(lim && lim.rateMax, 0)
  if (rm > 0) {
    const d = rm * Math.max(num(dt, 0), 1e-9)
    if (u > uPrev + d) { viol += (u - uPrev - d) / sc; u = uPrev + d }
    else if (u < uPrev - d) { viol += (uPrev - d - u) / sc; u = uPrev - d }
  }
  const ms = num(lim && lim.minStep, 0)
  if (ms > 0 && Math.abs(u - uPrev) < ms) u = uPrev
  return { u, viol }
}

/** 观测约束方向 */
export const OBS_DIRS = [
  { value: 'high', label: '不高于上限' },
  { value: 'low', label: '不低于下限' },
  { value: 'band', label: '保持在区间内' },
  { value: 'none', label: '不约束' },
]

/** 观测约束可绑定的量（软约束对象） */
export const OBS_VARS = [
  { value: 'cv', label: '被控量 CV' },
  { value: 'dv', label: '扰动观测量 DV' },
  { value: 'mon', label: '监视量 MON' },
]

/** 单条观测约束的越界量（按该量的量程归一化，≥0） */
export function obsOver(limit, value, scale) {
  const d = (limit && limit.dir) || 'none'
  const v = num(value, 0)
  const hi = num(limit && limit.hi, Infinity), lo = num(limit && limit.lo, -Infinity)
  let over = 0
  if (d === 'high') over = Math.max(0, v - hi)
  else if (d === 'low') over = Math.max(0, lo - v)
  else if (d === 'band') over = Math.max(0, v - hi) + Math.max(0, lo - v)
  return over / Math.max(num(scale, 1), 1e-9)
}

/**
 * 观测约束总惩罚（软约束）：Σ wᵢ·overᵢ，并给出最严重的一条（用于诊断/告警）。
 * @param {Array} limits  [{ id, var:'cv'|'dv'|'mon', dir, lo, hi, weight }]
 * @param {object} values { cv, dv, mon }
 * @param {object} scales { cv, dv, mon } 各量的量程（用于归一化）
 */
export function obsPenalty(limits, values, scales) {
  let total = 0, worst = 0, worstId = null
  for (const l of limits || []) {
    const v = values ? values[l.var] : null
    if (v == null || !Number.isFinite(Number(v))) continue // 该量本轮不可得 → 跳过（如无 DV 场景）
    const o = obsOver(l, v, scales && scales[l.var])
    const w = num(l.weight, 0)
    total += w * o
    if (w * o > worst) { worst = w * o; worstId = l.id }
  }
  return { total, worst, worstId }
}

/** 由回路配置推导观测约束（兼容只填了 safe:{dir,hi,lo} 的老配置） */
export function obsLimitsOf(loop) {
  const l = loop || {}
  if (Array.isArray(l.obs)) return l.obs
  const s = l.safe || {}
  const dir = s.dir || 'none'
  if (dir === 'none') return []
  return [{ id: 'cv-safe', var: 'cv', dir, lo: num(s.lo, -Infinity), hi: num(s.hi, Infinity), weight: 1, label: '被控量安全区间' }]
}

// ───────────────────────────── 动作布局 ─────────────────────────────

/**
 * 增益边界：保持基准增益的符号（反向作用回路增益为负，如「开度↑→温度↓」）。
 * base=0 表示该参数不参与寻优，退化为固定 0。
 */
export function gainBound(base, coefLo, coefHi) {
  const b = num(base, 0)
  if (Math.abs(b) < 1e-12) return [0, 0]
  const a = b * num(coefLo, 0.2), c = b * num(coefHi, 5)
  return [Math.min(a, c), Math.max(a, c)]
}

/** 智能体动作 ∈ [-1,1] → 物理值（动作空间统一归一化，各维探索幅度才可比） */
export const denormAct = (a, lo, hi) => denorm01((clamp(num(a, 0), -1, 1) + 1) / 2, lo, hi)

/**
 * 智能体动作 → 控制量的解包方式（可扩展：换算法/换控制结构只需加一条）。
 * 动作 a ∈ [-1,1]^dim；ctx: { sp, bounds }，bounds 由同一条目的 bounds() 生成。
 * 注意：u_set 是「被控量的目标值」，量程必须取 CV 区间（yLo~yHi），不是 MV 量程。
 */
export const ACTION_LAYOUTS = [
  {
    id: 'pid_set_gains',
    label: '内环设定值 + PID 增益',
    dim: 4,
    fields: ['内环设定 u_set', '比例增益 Kp', '积分增益 Ki', '微分增益 Kd'],
    unpack: (a, ctx) => {
      const b = ctx.bounds
      return { uSet: denormAct(a[0], b[0][0], b[0][1]), kp: denormAct(a[1], b[1][0], b[1][1]), ki: denormAct(a[2], b[2][0], b[2][1]), kd: denormAct(a[3], b[3][0], b[3][1]) }
    },
    bounds: (ctx) => [
      [ctx.yLo, ctx.yHi],
      gainBound(ctx.base.kp, ctx.coefLo, ctx.coefHi),
      gainBound(ctx.base.ki, ctx.coefLo, ctx.coefHi),
      gainBound(ctx.base.kd, ctx.coefLo, ctx.coefHi),
    ],
  },
  {
    id: 'pid_gains',
    label: '仅 PID 增益（内环设定固定为目标值）',
    dim: 3,
    fields: ['比例增益 Kp', '积分增益 Ki', '微分增益 Kd'],
    unpack: (a, ctx) => {
      const b = ctx.bounds
      return { uSet: ctx.sp, kp: denormAct(a[0], b[0][0], b[0][1]), ki: denormAct(a[1], b[1][0], b[1][1]), kd: denormAct(a[2], b[2][0], b[2][1]) }
    },
    bounds: (ctx) => [
      gainBound(ctx.base.kp, ctx.coefLo, ctx.coefHi),
      gainBound(ctx.base.ki, ctx.coefLo, ctx.coefHi),
      gainBound(ctx.base.kd, ctx.coefLo, ctx.coefHi),
    ],
  },
]
export const layoutById = (id) => ACTION_LAYOUTS.find((l) => l.id === id) || ACTION_LAYOUTS[0]

/** 由回路配置生成动作物理边界（u_set 用 CV 区间，增益用基准整定 × 倍率区间） */
export function actionBoundsOf(layoutId, ctx) {
  return layoutById(layoutId).bounds({
    sp: num(ctx.sp, 0),
    yLo: num(ctx.yLo, 0), yHi: num(ctx.yHi, 100),
    uLo: num(ctx.uLo, 0), uHi: num(ctx.uHi, 100),
    base: ctx.base || { kp: 1, ki: 0.05, kd: 0 },
    coefLo: num(ctx.coefLo, 0.2), coefHi: num(ctx.coefHi, 5),
  })
}

// ─────────────────────── 状态构成（可配置） ───────────────────────

/** 状态分量注册表：默认全开，可关掉以降低维度（换场景/换算法时按需裁剪） */
export const STATE_PARTS = [
  { key: 'y', label: 'ŷ 滤波被控量', def: true, desc: 'EKF 输出的被控量真值估计，归一化到量程' },
  { key: 'u', label: 'u 调节量', def: true, desc: '当前 MV 归一化开度' },
  { key: 'w', label: 'ŵ 环境态', def: true, desc: 'EKF 估计的环境侧状态（换热/回水/环境温度）' },
  { key: 'dv', label: 'DV 扰动观测量', def: true, desc: '可测扰动归一化值（前馈信息）' },
  { key: 'd', label: 'd̂ 扰动估计', def: true, desc: 'EKF 估计的未建模负载扰动' },
  { key: 'p', label: 'P 能耗', def: true, desc: '开度幂次归一化后的能耗指标' },
  { key: 'sp', label: 'SP 目标值', def: true, desc: '过程目标值归一化（跟踪任务必须保留）' },
  { key: 'uset', label: '内环设定', def: false, desc: '当前内环设定值（级联结构下可作为反馈）' },
]

export const defaultStateSpec = () => {
  const s = {}
  for (const p of STATE_PARTS) s[p.key] = p.def
  return s
}
/** 状态分量对应的超参 key（UI 上用开关暴露，schema 驱动） */
export const stateParamKey = (k) => 'st' + k.charAt(0).toUpperCase() + k.slice(1)
export const stateDimOf = (spec) => STATE_PARTS.reduce((n, p) => n + (spec && spec[p.key] ? 1 : 0), 0)

/**
 * 构造归一化状态向量。所有归一化基准都是**固定物理区间**（不随实时值漂移）。
 * @param {object} spec  { y,u,w,dv,d,p,sp,uset }
 * @param {object} v     { y,u,w,dv,d,sp,uSet,yLo,yHi,uLo,uHi,dvLo,dvHi,powerExp,agentDScale }
 */
export function stateVector(spec, v) {
  const out = []
  const yn = norm01(v.y, v.yLo, v.yHi)
  if (spec.y) out.push(yn)
  if (spec.u) out.push(norm01(v.u, v.uLo, v.uHi))
  if (spec.w) out.push(norm01(v.w, v.yLo, v.yHi))
  if (spec.dv) out.push(norm01(v.dv, v.dvLo, v.dvHi))
  if (spec.d) {
    const half = (span(v.yLo, v.yHi).hi - span(v.yLo, v.yHi).lo) * Math.max(0.05, num(v.dScale, 1))
    out.push(clamp(num(v.d, 0) / half, -2, 2))
  }
  if (spec.p) out.push(Math.pow(clamp01(norm01(v.u, v.uLo, v.uHi)), Math.max(0.2, num(v.powerExp, 3))))
  if (spec.sp) out.push(norm01(v.sp, v.yLo, v.yHi))
  if (spec.uset) out.push(norm01(v.uSet, v.uLo, v.uHi))
  return out
}

// ───────────────────────── 算法注册表 + 超参 schema ─────────────────────────

const P = (key, label, def, o = {}) => ({ key, label, def, type: 'num', ...o })
const G = {
  decision: '决策变量',
  pop: '种群与迭代',
  net: '网络结构',
  opt: '优化器',
  temp: '温度与探索',
  replay: '经验回放',
  budget: '训练预算',
  env: '训练工况（扰动场景）',
}

// 决策变量 = 相对「基准整定」的有符号倍率，所有算法（含 SAC 的动作边界）共用同一搜索空间，
// 因此 GA/PSO/HC/SAC 的结果可直接比较；允许负值以支持反向作用回路或增益符号翻转。
const COEF_LO = P('coefLo', '倍率下限', 0.2, { min: -20, max: 1, step: 0.05, group: G.decision, desc: '决策变量下界：基准整定 × 该值；负值表示允许翻转增益符号' })
const COEF_HI = P('coefHi', '倍率上限', 5, { min: 1, max: 50, step: 0.1, group: G.decision, desc: '决策变量上界：基准整定 × 该值' })

/** 训练工况（所有算法共用同一套扰动场景，保证代价可比） */
const ENV_PARAMS = [
  P('episodes', '每代工况数', 4, { min: 1, max: 32, step: 1, int: true, group: G.env, desc: '每个工况随机初值/扰动，用于评估鲁棒性；SAC 直接用这些工况做 rollout' }),
  P('horizonTau', '单工况时长（×时间常数）', 6, { min: 1, max: 30, step: 0.5, group: G.env, desc: '仿真时长 = 该倍数 × 对象时间常数 τ，保证进入稳态' }),
  P('dSeed', '随机种子', 7, { min: 0, max: 999999, step: 1, int: true, group: G.env, desc: '固定种子 → 训练/评估可复现；改种子得到另一组工况' }),
  P('dInitPct', '初值偏离（%量程）', 8, { min: 0, max: 50, step: 1, group: G.env, desc: '工况起始 CV 相对目标值的随机偏离幅度' }),
  P('dNoisePct', '测量噪声（%量程）', 0.4, { min: 0, max: 10, step: 0.1, group: G.env, desc: 'CV 测量噪声标准差，考察滤波与鲁棒性' }),
  P('dLoadPct', '负载扰动（%量程）', 12, { min: 0, max: 60, step: 1, group: G.env, desc: '随机负载扰动的幅度（一阶低通后的稳态幅值）' }),
  P('dLoadTau', '扰动时间常数（s）', 45, { min: 1, max: 600, step: 1, group: G.env, desc: '负载扰动的相关时间，越大越接近持续偏置' }),
  P('dDvLink', 'DV 可观测比例', 0.7, { min: 0, max: 1, step: 0.05, group: G.env, desc: '负载扰动中被 DV 测到的比例：1=完全可前馈观测，0=纯不可测扰动（考察 EKF 的作用）' }),
  P('dSpStepPct', '目标值阶跃（%量程）', 6, { min: 0, max: 40, step: 1, group: G.env, desc: '工况中途的目标值阶跃幅度，用于训练跟踪能力；0 = 不做阶跃' }),
  P('dTermOnViol', '硬约束越限即终止', false, { type: 'bool', group: G.env, desc: '开启后越限工况提前结束并计入终值惩罚（更强调安全，但样本变少）' }),
]

/** 训练预算 */
const BUDGET_PARAMS = [
  P('maxGen', '最大迭代代数', 30, { min: 1, max: 500, step: 1, int: true, group: G.budget, desc: '代数上限（种群算法=进化代数；SAC=一轮 rollout+更新）' }),
  P('dt', '内环 PID 周期 dt（s）', 0.1, { min: 0.01, max: 5, step: 0.01, group: G.budget, desc: 'PID 内环执行周期，训练仿真与在线运行使用同一值' }),
]

/** SAC 专属 */
const SAC_PARAMS = [
  P('sacDt', '外环决策周期（s）', 1, { min: 0.05, max: 30, step: 0.05, group: G.budget, desc: 'SAC 决策周期；与 dt 共同决定每个决策步包含的内环步数' }),
  P('lrActor', '策略学习率', SAC_DEFAULTS.lrActor, { min: 1e-5, max: 0.05, step: 1e-4, group: G.opt, desc: '策略网络 Adam 学习率（含 log σ）' }),
  P('lrCritic', 'Q 网络学习率', SAC_DEFAULTS.lrCritic, { min: 1e-5, max: 0.05, step: 1e-4, group: G.opt, desc: '双 Q 网络 Adam 学习率' }),
  P('lrAlpha', '温度 α 学习率', SAC_DEFAULTS.lrAlpha, { min: 1e-6, max: 0.05, step: 1e-4, group: G.opt, desc: '自动温度调节时 log α 的学习率' }),
  P('gamma', '折扣因子 γ', SAC_DEFAULTS.gamma, { min: 0.5, max: 0.9999, step: 0.001, group: G.opt, desc: '有效视野 ≈ 1/(1−γ) 个决策步，应覆盖对象时间常数' }),
  P('tau', '目标网络软更新 τ', SAC_DEFAULTS.tau, { min: 0.0001, max: 0.2, step: 0.0005, group: G.opt, desc: 'θ̄ ← τθ + (1−τ)θ̄，越小目标越稳、学习越慢' }),
  P('batchSize', '小批量 batch', SAC_DEFAULTS.batchSize, { min: 8, max: 512, step: 8, int: true, group: G.opt, desc: '每次更新采样的转移数' }),
  P('updatesPerGen', '每代更新次数', 40, { min: 1, max: 2000, step: 1, int: true, group: G.opt, desc: '每代（每批 rollout）执行的梯度步数；数据/更新比决定学习速度' }),
  P('gradClip', '梯度裁剪范数', 0, { min: 0, max: 100, step: 1, group: G.opt, desc: '全局梯度 L2 裁剪阈值，0 = 不裁剪' }),
  P('alpha', '初始温度 α', SAC_DEFAULTS.alpha, { min: 1e-4, max: 5, step: 0.01, group: G.temp, desc: '熵项权重；越大越鼓励探索' }),
  P('alphaAuto', 'α 自动调节', SAC_DEFAULTS.alphaAuto, { type: 'bool', group: G.temp, desc: '按目标熵自动调节 α（最大熵 SAC）' }),
  P('entropyRatio', '目标熵系数', 1, { min: 0.05, max: 3, step: 0.05, group: G.temp, desc: '目标熵 H̄ = −系数 × 动作维数；<1 表示鼓励更确定的策略' }),
  P('alphaMin', 'α 下限', SAC_DEFAULTS.alphaMin, { min: 1e-8, max: 1, step: 1e-4, group: G.temp, desc: '自动调节时的 α 下界' }),
  P('alphaMax', 'α 上限', SAC_DEFAULTS.alphaMax, { min: 0.01, max: 20, step: 0.01, group: G.temp, desc: '自动调节时的 α 上界' }),
  P('sigma0', '初始探索 σ', SAC_DEFAULTS.sigma0, { min: 0.01, max: 2, step: 0.01, group: G.temp, desc: '策略标准差初值（tanh 前空间）' }),
  P('logStdMin', 'σ 下限', SAC_DEFAULTS.logStdMin, { min: 0.001, max: 1, step: 0.005, group: G.temp, desc: '探索幅度下界，防止策略过早确定' }),
  P('logStdMax', 'σ 上限', SAC_DEFAULTS.logStdMax, { min: 0.05, max: 5, step: 0.05, group: G.temp, desc: '探索幅度上界，防止动作长期饱和' }),
  P('hidden1', '隐藏层 1 宽度', SAC_DEFAULTS.hidden[0], { min: 4, max: 256, step: 4, int: true, group: G.net, desc: '策略与 Q 网络共用同一宽度配置' }),
  P('hidden2', '隐藏层 2 宽度', SAC_DEFAULTS.hidden[1], { min: 0, max: 256, step: 4, int: true, group: G.net, desc: '0 = 单隐藏层' }),
  P('actorOutGain', '策略输出层增益', SAC_DEFAULTS.actorOutGain, { min: 0.001, max: 2, step: 0.001, group: G.net, desc: '输出层权重缩放，过大会使 tanh 饱和、梯度消失' }),
  P('replayCap', '回放容量', SAC_DEFAULTS.replayCap, { min: 1000, max: 2000000, step: 1000, int: true, group: G.replay, desc: '经验回放环形缓冲容量（转移条数）' }),
  P('rewardScale', '奖励缩放 κ', SAC_DEFAULTS.rewardScale, { min: 0.001, max: 100, step: 0.01, group: G.replay, desc: 'Q 目标中的奖励缩放；影响 Q 量级与 α 的相对强度' }),
  P('rewardAccum', '奖励聚合', 'sum', { type: 'select', group: G.replay, options: [{ value: 'sum', label: '决策周期内累加' }, { value: 'mean', label: '决策周期内取均值' }], desc: '一个决策步内多个内环步的代价如何聚合成一个奖励' }),
  P('clearReplay', '每代清空回放', false, { type: 'bool', group: G.replay, desc: '开启后每代只学最新工况（快速适应），关闭则长期记忆（更稳）' }),
  {
    key: 'layout', label: '动作布局', def: 'pid_set_gains', type: 'select', group: G.net,
    options: ACTION_LAYOUTS.map((l) => ({ value: l.id, label: l.label })),
    desc: '智能体输出的物理含义；决定动作维度',
  },
  // 状态构成（换场景/换算法时按需裁剪状态维度）
  ...STATE_PARTS.map((pt) => ({
    key: stateParamKey(pt.key), label: '状态·' + pt.label, def: pt.def, type: 'bool', group: G.net, desc: pt.desc,
  })),
]

/** GA */
const GA_PARAMS = [
  P('popSize', '种群规模', 24, { min: 4, max: 300, step: 1, int: true, group: G.pop, desc: '每代个体数（决策变量 = 回路数 × 3 个 PID 参数）' }),
  P('elite', '精英保留数', 2, { min: 0, max: 40, step: 1, int: true, group: G.pop, desc: '直接进入下一代的当前最优个体数' }),
  P('pc', '交叉概率', 0.85, { min: 0, max: 1, step: 0.01, group: G.pop, desc: '算术交叉概率' }),
  P('pm', '变异概率', 0.15, { min: 0, max: 1, step: 0.01, group: G.pop, desc: '每个基因的变异概率' }),
  P('mutSigma', '变异强度', 0.18, { min: 0.001, max: 1, step: 0.005, group: G.pop, desc: '高斯变异标准差（占搜索区间比例）' }),
  P('tournament', '锦标赛规模', 3, { min: 2, max: 12, step: 1, int: true, group: G.pop, desc: '选择压力：越大收敛越快、越易早熟' }),
]

/** PSO */
const PSO_PARAMS = [
  P('swarm', '粒子数', 24, { min: 4, max: 300, step: 1, int: true, group: G.pop, desc: '每代粒子数（决策变量 = 回路数 × 3）' }),
  P('w', '惯性权重 w', 0.72, { min: 0, max: 1.2, step: 0.01, group: G.pop, desc: '速度惯性；大 → 全局探索，小 → 局部收敛' }),
  P('c1', '个体学习 c1', 1.5, { min: 0, max: 4, step: 0.05, group: G.pop, desc: '向自身历史最优的吸引强度' }),
  P('c2', '群体学习 c2', 1.5, { min: 0, max: 4, step: 0.05, group: G.pop, desc: '向群体最优的吸引强度' }),
  P('vMaxRatio', '速度上限比例', 0.2, { min: 0.01, max: 1, step: 0.01, group: G.pop, desc: '单步最大位移占搜索区间比例，防止飞出' }),
]

/** 模式搜索（爬山 + 步长收缩 + 重启） */
const HC_PARAMS = [
  P('step0', '初始步长', 0.3, { min: 0.001, max: 1, step: 0.005, group: G.pop, desc: '相对搜索区间的初始探测步长' }),
  P('shrink', '步长收缩率', 0.6, { min: 0.1, max: 0.99, step: 0.01, group: G.pop, desc: '连续未改进时步长乘以该系数' }),
  P('restartAfter', '重启阈值', 6, { min: 1, max: 50, step: 1, int: true, group: G.pop, desc: '连续未改进代数达到该值时随机重启' }),
  P('stepMin', '最小步长', 0.01, { min: 0.0001, max: 0.5, step: 0.001, group: G.pop, desc: '步长下限，达到即视为收敛' }),
]

export const ALGORITHMS = [
  {
    id: 'ga', label: '遗传算法 GA', kind: 'population',
    desc: '实数编码 + 精英保留 + 算术交叉 + 高斯变异，对决策变量（各回路 PID 参数）并行搜索。适合目标函数非凸、无需梯度。',
    params: [...GA_PARAMS, COEF_LO, COEF_HI, ...BUDGET_PARAMS, ...ENV_PARAMS],
  },
  {
    id: 'pso', label: '粒子群 PSO', kind: 'population',
    desc: '标准惯性权重 PSO，个体最优/群体最优双吸引。收敛快于 GA，但易早熟，可配合重启策略使用。',
    params: [...PSO_PARAMS, COEF_LO, COEF_HI, ...BUDGET_PARAMS, ...ENV_PARAMS],
  },
  {
    id: 'hc', label: '模式搜索 HC', kind: 'population',
    desc: '爬山/模式搜索：逐维探测 + 步长收缩 + 随机重启。评估次数少、结果稳定，适合作为对照基线。',
    params: [...HC_PARAMS, COEF_LO, COEF_HI, ...BUDGET_PARAMS, ...ENV_PARAMS],
  },
  {
    id: 'sac', label: '强化学习 SAC', kind: 'rl',
    desc: '最大熵离线 Actor-Critic：外环输出「内环设定值 + PID 增益」，内环 PID 跟踪、EKF 估计扰动。纯 JS 实现，可在浏览器直接训练。',
    params: [...SAC_PARAMS, COEF_LO, COEF_HI, ...BUDGET_PARAMS, ...ENV_PARAMS],
  },
]

export const algById = (id) => ALGORITHMS.find((a) => a.id === id) || ALGORITHMS[0]

/** 某算法的默认超参对象 */
export function defaultParams(algId) {
  const o = {}
  for (const p of algById(algId).params) o[p.key] = p.def
  return o
}

/** 合并默认值 + 覆盖值（并做类型归一化） */
export function mergeParams(algId, overrides) {
  const base = defaultParams(algId)
  const src = overrides || {}
  for (const p of algById(algId).params) {
    if (src[p.key] === undefined || src[p.key] === null || src[p.key] === '') continue
    base[p.key] = p.type === 'bool' ? !!src[p.key] : p.type === 'select' ? src[p.key] : num(src[p.key], p.def)
  }
  return base
}

/** 按 schema 分组，便于 UI 折叠渲染 */
export function paramsByGroup(algId) {
  const groups = []
  for (const p of algById(algId).params) {
    const g = p.group || '其他'
    let it = groups.find((x) => x.name === g)
    if (!it) { it = { name: g, items: [] }; groups.push(it) }
    it.items.push(p)
  }
  return groups
}

/** 决策变量（有符号倍率）→ PID 参数 */
export function gainsOf(base, coef) {
  return {
    kp: num(base.kp, 0) * num(coef[0], 1),
    ki: num(base.ki, 0) * num(coef[1], 1),
    kd: num(base.kd, 0) * num(coef[2], 1),
  }
}

/** 决策变量搜索区间（倍率模式下为 [coefLo, coefHi]；绝对值模式由调用方给量程） */
export function coefBounds(p) {
  const lo = num(p.coefLo, 0.2), hi = Math.max(num(p.coefHi, 5), lo * 1.01)
  return { lo, hi }
}

// ───────────────────────── 过程模型：辨识 / 先验 ─────────────────────────

/**
 * 由历史数据最小二乘辨识一阶离散模型 y[k+1] = a·y[k] + b·u[k] + c。
 * 说明：闭环数据辨识存在偏差（输入与噪声相关），因此同时给出 R² 与激励度供人工判断；
 * R² 过低或输入无激励时调用方应回退到先验模型。
 * @returns {{a,b,c,dt,tau,G,r2,n,excited}|null}
 */
export function identifyFirstOrder(uArr, yArr, dt) {
  const n = Math.min(uArr.length, yArr.length)
  if (n < 12) return null
  // 正规方程 M·θ = v，θ = [a, b, c]
  let s00 = 0, s01 = 0, s02 = 0, s11 = 0, s12 = 0, s22 = 0, v0 = 0, v1 = 0, v2 = 0
  let uMin = Infinity, uMax = -Infinity, yMin = Infinity, yMax = -Infinity
  for (let k = 0; k < n - 1; k++) {
    const y0 = num(yArr[k]), u0 = num(uArr[k]), y1 = num(yArr[k + 1])
    if (!Number.isFinite(y0) || !Number.isFinite(u0) || !Number.isFinite(y1)) continue
    s00 += y0 * y0; s01 += y0 * u0; s02 += y0
    s11 += u0 * u0; s12 += u0; s22 += 1
    v0 += y0 * y1; v1 += u0 * y1; v2 += y1
    if (u0 < uMin) uMin = u0
    if (u0 > uMax) uMax = u0
    if (y0 < yMin) yMin = y0
    if (y0 > yMax) yMax = y0
  }
  const M = [[s00, s01, s02], [s01, s11, s12], [s02, s12, s22]]
  const rhs = [v0, v1, v2]
  // 3×3 高斯消元
  const A = M.map((r, i) => r.concat([rhs[i]]))
  for (let c = 0; c < 3; c++) {
    let piv = c
    for (let r = c + 1; r < 3; r++) if (Math.abs(A[r][c]) > Math.abs(A[piv][c])) piv = r
    if (Math.abs(A[piv][c]) < 1e-12) return null
    const tmp = A[c]; A[c] = A[piv]; A[piv] = tmp
    const d = A[c][c]
    for (let j = c; j < 4; j++) A[c][j] /= d
    for (let r = 0; r < 3; r++) {
      if (r === c) continue
      const f = A[r][c]
      if (f === 0) continue
      for (let j = c; j < 4; j++) A[r][j] -= f * A[c][j]
    }
  }
  const a = A[0][3], b = A[1][3], c0 = A[2][3]
  if (![a, b, c0].every((v) => Number.isFinite(v))) return null
  if (!(a > 0.001 && a < 0.99999)) return null
  if (Math.abs(b) < 1e-12) return null
  // 拟合优度
  let sse = 0, sst = 0, yBar = 0
  let m = 0
  for (let k = 0; k < n - 1; k++) { yBar += num(yArr[k + 1]); m++ }
  yBar = m ? yBar / m : 0
  for (let k = 0; k < n - 1; k++) {
    const pred = a * num(yArr[k]) + b * num(uArr[k]) + c0
    const e = num(yArr[k + 1]) - pred
    sse += e * e
    const d = num(yArr[k + 1]) - yBar
    sst += d * d
  }
  const r2 = sst > 1e-12 ? 1 - sse / sst : 0
  const uSpan = uMax - uMin
  const ySpan = yMax - yMin
  const excited = uSpan > Math.max(1e-9, ySpan) * 0.02
  const dts = num(dt, 1) > 0 ? num(dt, 1) : 1
  const tau = -dts / Math.log(a)
  const G = b / (1 - a)
  return { a, b, c: c0, dt: dts, tau, G, r2, n: m, excited, uSpan, ySpan }
}

/**
 * 先验一阶模型（无历史数据或辨识不可信时使用）。
 * 令 (y0, u0) 为平衡点，并假设 MV 全量程变化能把 CV 拉动 gainRatio 倍量程。
 */
export function priorModel({ y0, u0, yLo, yHi, uLo, uHi, tau, dt, gainSign = 0, gainRatio = 0.8 }) {
  const ys = span(yLo, yHi), us = span(uLo, uHi)
  const dts = num(dt, 0.1) > 0 ? num(dt, 0.1) : 0.1
  const t = Math.max(num(tau, 60), dts * 1.5)
  const a = Math.exp(-dts / t)
  const sign = num(gainSign, 0) === 0 ? 1 : Math.sign(num(gainSign, 1))
  const G = sign * Math.max(0.05, num(gainRatio, 0.8)) * (ys.hi - ys.lo) / Math.max(us.hi - us.lo, 1e-9)
  const b = G * (1 - a)
  const c = num(y0, ys.lo) - a * num(y0, ys.lo) - b * num(u0, us.lo)
  return { a, b, c, dt: dts, tau: t, G, r2: 0, n: 0, excited: false, prior: true }
}

export const modelStep = (m, y, u) => num(m.a, 1) * num(y, 0) + num(m.b, 0) * num(u, 0) + num(m.c, 0)

// ───────────────────────── 扰动场景（训练工况） ─────────────────────────

export const DEFAULT_DISTURB = {
  episodes: 4, horizonTau: 6, seed: 7, initPct: 8, noisePct: 0.4,
  loadPct: 12, loadTau: 45, dvLink: 0.7, spStepPct: 6, termOnViol: false,
}

/** 从超参对象提取扰动场景 */
export function disturbSpecOf(p, tau) {
  const hz = num(p.horizonTau, DEFAULT_DISTURB.horizonTau)
  return {
    episodes: Math.max(1, Math.round(num(p.episodes, 4))),
    steps: Math.max(20, Math.round(hz * Math.max(num(tau, 60), 1) / Math.max(num(p.dt, 0.1), 0.01))),
    seed: num(p.dSeed, 7),
    initPct: num(p.dInitPct, 8),
    noisePct: num(p.dNoisePct, 0.4),
    loadPct: num(p.dLoadPct, 12),
    loadTau: num(p.dLoadTau, 45),
    dvLink: clamp01(num(p.dDvLink, 0.7)),
    spStepPct: num(p.dSpStepPct, 6),
    termOnViol: !!p.dTermOnViol,
  }
}

/**
 * 生成一条工况的扰动序列（负载 + 目标值阶跃）。
 * 负载 = 一阶低通噪声；DV 观测量由 dvLink 决定能看到多少负载。
 * 工况自带 noiseSeed：同一工况的测量噪声可复现 → 个体适应度确定，进化过程无评估噪声。
 */
export function makeScenario({ spec, rng, dt, yScale, uScale, noiseSeed = 1 }) {
  const steps = Math.max(1, spec.steps)
  const load = new Float64Array(steps)
  const alpha = clamp(dt / Math.max(num(spec.loadTau, 45), dt), 0, 1)
  let lp = 0
  for (let k = 0; k < steps; k++) {
    lp += alpha * (rng.normal() - lp)
    load[k] = (num(spec.loadPct, 0) / 100) * yScale * lp
  }
  const initOff = (num(spec.initPct, 0) / 100) * yScale * rng.normal()
  const spStep = (num(spec.spStepPct, 0) / 100) * yScale * (rng.next() < 0.5 ? -1 : 1)
  const spAt = Math.floor(steps * (0.3 + 0.4 * rng.next()))
  const u0Jit = (rng.next() - 0.5) * 0.1 * uScale
  return { load, initOff, spStep, spAt, u0Jit, noise: (num(spec.noisePct, 0) / 100) * yScale, noiseSeed }
}

/** 生成一整套工况（确定性）：同一 (seed + offset) 永远得到同一组工况 */
export function makeScenList(spec, { dt, yScale, uScale, seedOffset = 0 } = {}) {
  const list = []
  for (let i = 0; i < Math.max(1, spec.episodes); i++) {
    const s = num(spec.seed, 7) + i * 7919 + num(seedOffset, 0) * 104729
    const rng = createRng(s)
    list.push(makeScenario({ spec, rng, dt, yScale, uScale, noiseSeed: s + 31 }))
  }
  return list
}

// ───────────────────────── 统一闭环仿真器 ─────────────────────────

/**
 * 单工况闭环仿真（所有算法共用）。
 *
 * @param {object} o
 * @param {object} o.model    一阶过程模型 {a,b,c,dt}
 * @param {object} o.loop     回路配置 { sp, yLo,yHi, uLo,uHi, dvLo,dvHi, dirSign, powerExp,
 *                                       uRateMax, safe:{dir,hi,lo}, ekf:{...}, dScale }
 * @param {object} o.weights  目标项权重
 * @param {object} o.gains    固定 PID 增益（种群算法）或 null
 * @param {object} o.agent    SAC 智能体（rl 算法）或 null
 * @param {object} o.agentCfg { layout, spec, bounds, rewardScale, rewardAccum, train, learn }
 * @param {object} o.scen     工况 { load, initOff, spStep, spAt, u0Jit, noise }
 * @param {object} o.t        { dt, sacDt, steps, u0, y0 }
 * @param {object} [o.rec]    采集数组（可选，训练时不采集以提速）
 */
export function simulateEpisode(o) {
  const { model, loop, weights, scen } = o
  const t = o.t
  const dt = Math.max(num(t.dt, 0.1), 1e-3)
  const sacDt = Math.max(num(t.sacDt, 1), dt)
  const decEvery = Math.max(1, Math.round(sacDt / dt))
  const steps = Math.max(1, Math.round(t.steps))
  const agent = o.agent || null
  const agentCfg = o.agentCfg || {}
  const layout = layoutById(agentCfg.layout || 'pid_set_gains')
  const spec = agentCfg.spec || defaultStateSpec()
  const ys = span(loop.yLo, loop.yHi)
  const us = span(loop.uLo, loop.uHi)
  const yScale = ys.hi - ys.lo
  const uScale = Math.max(us.hi - us.lo, 1e-9)
  const spBase = num(loop.sp, (ys.lo + ys.hi) / 2)
  // 测量噪声由工况自带的种子决定 → 同一工况可复现（适应度无评估噪声）
  const rng = createRng(scen.noiseSeed != null ? scen.noiseSeed : num(o.seed, 1))
  // 两类约束：可调（硬，作用在 MV 上）/ 观测（软，作用在 CV·DV·MON 上）
  const adj = adjLimitOf(loop)
  const obsL = obsLimitsOf(loop)
  const scales = {
    cv: yScale,
    dv: Math.max(num(loop.dvHi, 1) - num(loop.dvLo, 0), 1e-9),
    mon: Math.max(num(loop.monHi, 100) - num(loop.monLo, 0), 1e-9),
  }

  const gains0 = o.gains || { kp: 1, ki: 0.05, kd: 0 }
  // 动作边界必须用与 createAgentFor / 在线控制器同一个「基准整定」：
  // 智能体输出的倍率只有在同一基准下解码，训练 / 评估 / 落地三处才指向同一物理增益。
  // 若这里退回单位基准，同一动作会解出符号相反（如 Kp 变正）的增益，闭环直接跑飞。
  const baseGains = o.base || loop.base || gains0
  const aBounds = layout.bounds({
    sp: spBase, yLo: ys.lo, yHi: ys.hi, uLo: us.lo, uHi: us.hi, base: baseGains,
    coefLo: agentCfg.coefLo, coefHi: agentCfg.coefHi,
  })
  let pid = createPid({ ...gains0, min: us.lo, max: us.hi })
  let ekf = createEkf3({ ...(loop.ekf || {}), a: model.a, b: model.b, c: model.c })

  let y = clamp(spBase + scen.initOff, ys.lo - yScale, ys.hi + yScale)
  let u = clamp(num(t.u0, (us.lo + us.hi) / 2) + scen.u0Jit, us.lo, us.hi)
  // 超调方向：默认按「背离起始偏差」的方向自动判定（起始偏高 → 向下超调）
  const ovDir = num(loop.dirSign, 0) !== 0
    ? Math.sign(num(loop.dirSign, 1))
    : (-Math.sign(y - spBase) || 0)
  let uSet = spBase
  let uSetPrev = spBase
  let adjHold = false // 上一拍是否被速率限幅拦住（拦住则冻结积分）
  let sp = spBase
  let un = clamp01(norm01(u, us.lo, us.hi))
  let unPrev = un, unPrev2 = un
  let costSum = 0, costAll = 0, decCount = 0, violAll = 0, overAll = 0, energy = 0
  let iae = 0, ise = 0, maxErr = 0, maxOver = 0
  let ssErr = 0, ssN = 0
  let settleAt = -1
  let yHat = null, dHat = 0, wHat = null
  const acts = []
  const pending = [] // 一个决策周期内的代价
  let prevState = null, prevAct = null
  let lastDecStep = -1e9
  let terminated = false
  let stepsDone = 0

  for (let k = 0; k < steps; k++) {
    if (k === scen.spAt) sp = spBase + scen.spStep
    // —— 测量（含噪声）——
    const yMeas = y + rng.normal() * scen.noise
    const dvTrue = loop.hasDv ? num(loop.dv0, 0) + scen.load[k] * clamp01(num(loop.dvLink, 0)) / Math.max(0.05, num(loop.dvScale, 1)) : null
    const dvMeas = dvTrue == null ? null : dvTrue + rng.normal() * scen.noise * 0.3

    // —— 是否到达决策周期：先决策，再执行内环 ——
    const decide = k === 0 || (k - lastDecStep) >= decEvery
    let actInfo = null
    if (decide) {
      if (prevState && agent && agentCfg.learn) {
        const r = (agentCfg.rewardAccum === 'mean' ? costSum / Math.max(pending.length, 1) : costSum)
        agent.remember(prevState, prevAct, -r, stateVector(spec, {
          y: yHat == null ? yMeas : yHat, u, w: wHat == null ? y : wHat, dv: dvMeas, d: dHat,
          sp, uSet, yLo: ys.lo, yHi: ys.hi, uLo: us.lo, uHi: us.hi, dvLo: loop.dvLo, dvHi: loop.dvHi,
          powerExp: loop.powerExp, dScale: loop.dScale,
        }), false)
      }
      if (agent) {
        const s = stateVector(spec, {
          y: yHat == null ? yMeas : yHat, u, w: wHat == null ? y : wHat, dv: dvMeas, d: dHat,
          sp, uSet, yLo: ys.lo, yHi: ys.hi, uLo: us.lo, uHi: us.hi, dvLo: loop.dvLo, dvHi: loop.dvHi,
          powerExp: loop.powerExp, dScale: loop.dScale,
        })
        const out = agent.act(s, !agentCfg.train)
        const un2 = layout.unpack(out.a, { sp, bounds: aBounds })
        // 内环设定值属于「被控量的目标」，必须裁到 CV 量程（不能按动作边界第 0 项裁，
        // 在 pid_gains 布局下第 0 项是 Kp 的边界）
        uSet = clamp(num(un2.uSet, sp), ys.lo, ys.hi)
        pid.set({ kp: num(un2.kp, gains0.kp), ki: num(un2.ki, gains0.ki), kd: num(un2.kd, gains0.kd) })
        prevState = s
        prevAct = out.a
        actInfo = { ...un2, logp: out.logp }
      }
      costSum = 0
      pending.length = 0
      lastDecStep = k
      decCount++
    }

    // —— 内环 PID → 施加「可调约束（硬）」 ——
    const yRef = yHat == null ? yMeas : yHat
    // 无扰同步：投入（首拍）与每次换增益后，让控制器输出从当前实际执行量出发。
    // 否则积分项从 0 起步，首拍就会要求把执行量从当前开度猛拉到「零误差对应输出」，
    // 必然撞上速率限幅（可调约束违反）并污染代价；换增益时同理会造成执行量跳变。
    if (k === 0 || (decide && agent)) pid.trim(u, uSet - yRef)
    const pr = pid.step(uSet, yRef, dt, { hold: adjHold })
    const ap = applyAdjLimit(adj, pr.u, u, dt, uScale)
    const uCmd = ap.u
    adjHold = ap.viol > 0 // 设备没跟上 → 下一拍冻结积分

    // —— 目标项 / 代价（与在线运行同一实现，保证训练-落地口径一致）——
    // 观测约束（软）：CV/DV/MON 越界按各自量程归一化、按各自权重加权
    const op = obsPenalty(obsL, { cv: y, dv: dvMeas, mon: loop.mon }, scales)
    const terms = termsOf({
      e: y - sp, scale: yScale, un: norm01(uCmd, us.lo, us.hi), unPrev, unPrev2,
      sp: uSet, spPrev: uSetPrev, safety: op.total, viol: ap.viol,
      dirSign: ovDir, powerExp: loop.powerExp,
    })
    const cost = costOf(weights, terms)
    costSum += cost
    costAll += cost
    pending.push(cost)
    violAll += terms.viol
    overAll += op.total
    energy += terms.power * dt
    iae += Math.abs(y - sp) * dt
    ise += (y - sp) * (y - sp) * dt
    maxErr = Math.max(maxErr, Math.abs(y - sp))
    maxOver = Math.max(maxOver, op.total)
    unPrev2 = unPrev
    unPrev = clamp01(norm01(uCmd, us.lo, us.hi))
    uSetPrev = uSet

    // —— 过程推进 ——
    u = uCmd
    const yNext = modelStep(model, y, u) + scen.load[k]
    y = clamp(yNext, ys.lo - 4 * yScale, ys.hi + 4 * yScale)

    // —— EKF（用滤波后的量做闭环反馈，同时提供 d̂ / ŵ 给策略）——
    const r = ekf.step(yMeas, u, dvMeas, { un: norm01(u, us.lo, us.hi) })
    yHat = r.y == null ? yMeas : r.y
    dHat = num(r.d, 0)
    wHat = r.w == null ? y : r.w

    // —— 稳态误差（后 20% 窗口）——
    if (k > steps * 0.8) { ssErr += Math.abs(y - sp); ssN++ }
    // —— 调节时间：进入 ±2% 量程带并保持 ——
    if (settleAt < 0 && k > 5 && Math.abs(y - sp) <= 0.02 * yScale) settleAt = k
    else if (settleAt >= 0 && Math.abs(y - sp) > 0.02 * yScale) settleAt = -1

    if (o.rec) {
      o.rec.push({
        t: k * dt, y, yMeas, yHat, u, uSet, sp, dv: dvMeas, d: dHat, w: wHat,
        cost, terms, act: actInfo,
      })
    }
    if (actInfo) acts.push({ t: k * dt, ...actInfo })
    stepsDone = k + 1

    if (scen.termOnViol && op.total > 0) { terminated = true; break }
  }

  // 收尾：把最后一个决策周期的转移写入回放（时间截断型终止不置 done，保留自举）
  if (agent && agentCfg.learn && prevState) {
    const r = (agentCfg.rewardAccum === 'mean' ? costSum / Math.max(pending.length, 1) : costSum)
    agent.remember(prevState, prevAct, -r, stateVector(spec, {
      y: yHat == null ? y : yHat, u, w: wHat == null ? y : wHat, dv: null, d: dHat,
      sp, uSet, yLo: ys.lo, yHi: ys.hi, uLo: us.lo, uHi: us.hi, dvLo: loop.dvLo, dvHi: loop.dvHi,
      powerExp: loop.powerExp, dScale: loop.dScale,
    }), terminated)
  }

  const nSteps = Math.max(1, stepsDone)
  return {
    cost: costAll / nSteps,
    costSum: costAll,
    metrics: {
      cost: costAll / nSteps,
      iae: iae / nSteps,
      ise: ise / nSteps,
      maxErr, maxOver, overshoot: maxOver / yScale,
      ssErr: ssN ? ssErr / ssN : 0,
      settle: settleAt < 0 ? NaN : settleAt * dt,
      energy, viol: violAll / nSteps,
      safeRatio: overAll / nSteps,
      dec: decCount,
    },
    acts,
    terminated,
    steps: nSteps,
  }
}


/**
 * 多工况评估（GA/PSO/HC 的个体适应度，或 SAC 的确定性策略评估）。
 * 同一工况集合 → 不同算法结果可直接比较。
 */
export function evaluateLoop(o) {
  const { scenList } = o
  let cost = 0
  const met = { cost: 0, iae: 0, ise: 0, maxErr: 0, overshoot: 0, ssErr: 0, settle: 0, energy: 0, viol: 0, safeRatio: 0 }
  let n = 0, settleN = 0
  const runs = []
  // 评估一律使用确定性策略 + 不学习（GA/PSO/HC 传 gains；SAC 传 agent）
  const agentCfg = { ...(o.agentCfg || {}), train: false, learn: false }
  for (const sc of scenList) {
    const res = simulateEpisode({ ...o, scen: sc, agentCfg, rec: null })
    runs.push(res)
    cost += res.cost
    n++
    for (const k in met) {
      if (k === 'settle') { if (Number.isFinite(res.metrics.settle)) { met.settle += res.metrics.settle; settleN++ } }
      else met[k] += num(res.metrics[k], 0)
    }
  }
  for (const k in met) met[k] = k === 'settle' ? (settleN ? met.settle / settleN : NaN) : met[k] / Math.max(n, 1)
  return { cost: cost / Math.max(n, 1), metrics: met, runs }
}

// ───────────────────────── 在线自适应控制器 ─────────────────────────

/**
 * 在线分层控制器：EKF（估计）→ SAC（按 sacDt 决策）→ PID（按 dt 跟踪）。
 * 与训练用仿真器共用 termsOf/costOf 与归一化口径，保证「训练-落地」一致。
 */
export function createAdaptiveController(o = {}) {
  const S = {
    dt: num(o.dt, 0.1),
    sacDt: num(o.sacDt, 1),
    model: o.model || { a: 1, b: 0, c: 0 },
    norm: o.norm || { yLo: 0, yHi: 100, uLo: 0, uHi: 100, dvLo: 0, dvHi: 1 },
    sp: num(o.sp, 0),
    weights: o.weights || {},
    powerExp: num(o.powerExp, 3),
    dScale: num(o.dScale, 1),
    dirSign: num(o.dirSign, 0),
    safe: o.safe || { dir: 'none' },
    uRateMax: num(o.uRateMax, 0),
    ekf: o.ekf || {},
    pidCfg: o.pidCfg || { kp: 1, ki: 0.05, kd: 0 },
    layout: o.layout || 'pid_set_gains',
    spec: o.spec || defaultStateSpec(),
    agent: o.agent || null,
    // 动作解码基准：缺省取内环基准整定（pidCfg），保证与智能体动作边界同源
    base: o.base || o.pidCfg || { kp: 1, ki: 0.05, kd: 0 },
    coefLo: num(o.coefLo, 0.2),
    coefHi: num(o.coefHi, 5),
    hasDv: !!o.hasDv,
    // 两类约束：可调（硬）/ 观测（软）
    adj: o.adj || adjLimitOf(o),
    obs: o.obs || obsLimitsOf(o),
    monHi: num(o.monHi, 100),
    monLo: num(o.monLo, 0),
    mon: Number.isFinite(Number(o.mon)) ? Number(o.mon) : null,
  }
  let pid = createPid({ ...S.pidCfg, min: S.norm.uLo, max: S.norm.uHi })
  let ekf = createEkf3({ ...S.ekf, a: S.model.a, b: S.model.b, c: S.model.c })
  let u = num(o.u0, (S.norm.uLo + S.norm.uHi) / 2)
  let unPrev = clamp01(norm01(u, S.norm.uLo, S.norm.uHi))
  let unPrev2 = unPrev
  let uSet = S.sp
  let spPrev = S.sp
  let tAcc = 0
  let costAcc = 0, nAcc = 0
  let costSum = 0, innerN = 0
  let prevState = null, prevAct = null
  let act = { uSet: S.sp, kp: S.pidCfg.kp, ki: S.pidCfg.ki, kd: S.pidCfg.kd }
  let last = null
  let learning = false
  let started = false // 是否已跑过至少一拍（首拍做无扰投入）
  let adjHold = false // 上一拍是否被速率限幅拦住（拦住则冻结积分）

  const layout = () => layoutById(S.layout)
  const ys = () => span(S.norm.yLo, S.norm.yHi)
  const us = () => span(S.norm.uLo, S.norm.uHi)
  /** 各观测量的量程（用于观测约束归一化） */
  const scalesOf = () => {
    const y0 = ys()
    return {
      cv: y0.hi - y0.lo,
      dv: Math.max(num(S.norm.dvHi, 1) - num(S.norm.dvLo, 0), 1e-9),
      mon: Math.max(num(S.monHi, 100) - num(S.monLo, 0), 1e-9),
    }
  }

  function buildState(v) {
    const y = ys(), uu = us()
    return stateVector(S.spec, {
      y: v.y, u, w: v.w, dv: v.dv, d: v.d, sp: S.sp, uSet,
      yLo: y.lo, yHi: y.hi, uLo: uu.lo, uHi: uu.hi, dvLo: S.norm.dvLo, dvHi: S.norm.dvHi,
      powerExp: S.powerExp, dScale: S.dScale,
    })
  }

  /** 每 dt 调用一次；y 为 CV 原始测量，dv 为扰动观测量（可空） */
  function step({ y: yRaw, dv = null, dt = S.dt } = {}) {
    const dts = num(dt, S.dt) > 0 ? num(dt, S.dt) : S.dt
    const uu = us(), y0 = ys()
    const r = ekf.step(yRaw, u, S.hasDv ? dv : null, { un: norm01(u, uu.lo, uu.hi) })
    const yHat = r.y == null ? num(yRaw, 0) : r.y
    const dHat = num(r.d, 0)
    const wHat = r.w == null ? yHat : r.w

    tAcc += dts
    let decided = false
    if (tAcc >= S.sacDt - 1e-9) {
      tAcc = 0
      decided = true
      const s = buildState({ y: yHat, w: wHat, dv, d: dHat })
      if (S.agent && learning && prevState) {
        const rr = costSum
        S.agent.remember(prevState, prevAct, -rr, s, false)
      }
      if (S.agent) {
        const out = S.agent.act(s, !learning)
        const yy = ys()
        const bd = layout().bounds({ sp: S.sp, yLo: yy.lo, yHi: yy.hi, uLo: uu.lo, uHi: uu.hi, base: S.base, coefLo: S.coefLo, coefHi: S.coefHi })
        const un = layout().unpack(out.a, { sp: S.sp, bounds: bd })
        // 内环设定值裁到 CV 量程（bd[0] 在 pid_gains 布局下是 Kp 的边界，不能当设定值区间用）
        uSet = clamp(num(un.uSet, S.sp), yy.lo, yy.hi)
        pid.set({ kp: num(un.kp, S.base.kp), ki: num(un.ki, S.base.ki), kd: num(un.kd, S.base.kd) })
        act = { ...un, logp: out.logp }
        prevState = s
        prevAct = out.a
      }
      costSum = 0
      innerN = 0
    }

    // —— 内环 PID → 施加「可调约束（硬）」 ——
    // 无扰同步：投入（首拍）与每次换增益后，输出从当前实际执行量出发（与仿真器同口径）
    if (!started || (decided && S.agent)) pid.trim(u, uSet - yHat)
    const pr = pid.step(uSet, yHat, dts, { hold: adjHold })
    const ap = applyAdjLimit(S.adj, pr.u, u, dts, uu.hi - uu.lo)
    const uCmd = ap.u
    adjHold = ap.viol > 0 // 设备没跟上 → 下一拍冻结积分

    // —— 目标项（观测约束为软约束，按各自权重加权）——
    const yScale = y0.hi - y0.lo
    const op = obsPenalty(S.obs, { cv: num(yRaw, yHat), dv, mon: S.mon }, scalesOf())
    const terms = termsOf({
      e: num(yRaw, yHat) - S.sp, scale: yScale, un: norm01(uCmd, uu.lo, uu.hi), unPrev, unPrev2,
      sp: uSet, spPrev, safety: op.total, viol: ap.viol, dirSign: S.dirSign, powerExp: S.powerExp,
    })
    const cost = costOf(S.weights, terms)
    costAcc += cost; nAcc++
    costSum += cost; innerN++
    unPrev2 = unPrev
    unPrev = clamp01(norm01(uCmd, uu.lo, uu.hi))
    spPrev = uSet
    u = uCmd

    last = {
      u: uCmd, uSet, yRaw, yHat, dHat, wHat, sp: S.sp, decided, cost, terms,
      pid: { ...pid.cfg }, act: decided ? act : null, saturated: !!pr.saturated,
    }
    started = true
    return last
  }

  return {
    step,
    /** 切换智能体（应用模型版本时调用） */
    setAgent(a) { S.agent = a || null; prevState = null; prevAct = null; costSum = 0 },
    /** 是否处于学习模式（true=采样噪声探索并写入回放；false=确定性执行） */
    setLearning(v) { learning = !!v },
    setModel(m) { if (!m) return; S.model = m; ekf.set({ a: m.a, b: m.b, c: m.c }) },
    setSp(v) { S.sp = num(v, S.sp) },
    setWeights(w) { S.weights = w || {} },
    setNorm(n) { if (n) Object.assign(S.norm, n) },
    /** 更新可调约束（硬）：量程/速率/最小步长 */
    setAdj(a) { if (a) Object.assign(S.adj, a) },
    /** 更新观测约束（软）：整表替换 */
    setObs(list) { S.obs = Array.isArray(list) ? list : [] },
    /** 更新监视量当前值（用于监视量上的观测约束） */
    setMon(v) { S.mon = Number.isFinite(Number(v)) ? Number(v) : null },
    setPidBase(b) { S.base = b || S.base },
    setPid(c) { pid.set(c || {}) },
    reset(o2 = {}) {
      pid = createPid({ ...S.pidCfg, min: S.norm.uLo, max: S.norm.uHi })
      ekf = createEkf3({ ...S.ekf, a: S.model.a, b: S.model.b, c: S.model.c })
      prevState = null; prevAct = null; costSum = 0; innerN = 0; costAcc = 0; nAcc = 0
      uSet = S.sp
      started = false
      if (o2.u0 != null) { u = num(o2.u0, u); unPrev = clamp01(norm01(u, S.norm.uLo, S.norm.uHi)); unPrev2 = unPrev }
    },
    get u() { return u },
    get uSet() { return uSet },
    get pidCfg() { return { ...pid.cfg } },
    last() { return last },
    /** 运行期平均代价（用于 KPI） */
    avgCost() { return nAcc ? costAcc / nAcc : 0 },
  }
}

// ───────────────────────── 寻优状态机（GA / PSO / HC） ─────────────────────────

const randVec = (D, lo, hi, rng) => Array.from({ length: D }, () => rng.uniform(lo, hi))

export function createSearchState(algId, p, D, rng) {
  const { lo, hi } = coefBounds(p)
  if (algId === 'pso') {
    const N = Math.max(4, Math.round(num(p.swarm, 24)))
    const pop = Array.from({ length: N }, () => randVec(D, lo, hi, rng))
    const vel = Array.from({ length: N }, () => randVec(D, -(hi - lo) * 0.1, (hi - lo) * 0.1, rng))
    return { pop, vel, pbest: pop.map((x) => x.slice()), pbestCost: new Array(N).fill(Infinity), gbest: null, gbestCost: Infinity }
  }
  if (algId === 'hc') {
    return { pop: [randVec(D, lo, hi, rng)], step: num(p.step0, 0.3), stall: 0, gbest: null, gbestCost: Infinity }
  }
  const N = Math.max(4, Math.round(num(p.popSize, 24)))
  return { pop: Array.from({ length: N }, () => randVec(D, lo, hi, rng)), gbest: null, gbestCost: Infinity }
}

/**
 * 依据本代代价推进一代。
 * @returns {{meanCost, bestCost, bestCoef, diversity, note}}
 */
export function searchNext(algId, st, p, costs, D, rng) {
  const { lo, hi } = coefBounds(p)
  const rng2 = span(lo, hi)
  const range = rng2.hi - rng2.lo
  const meanCost = costs.reduce((s, v) => s + num(v, 1e9), 0) / Math.max(costs.length, 1)
  let bi = 0
  for (let i = 1; i < costs.length; i++) if (num(costs[i], 1e9) < num(costs[bi], 1e9)) bi = i
  let note = ''

  if (algId === 'ga') {
    const N = st.pop.length
    const elite = clamp(Math.round(num(p.elite, 2)), 0, Math.floor(N / 2))
    const order = st.pop.map((_, i) => i).sort((a, b) => num(costs[a], 1e9) - num(costs[b], 1e9))
    const next = []
    for (let i = 0; i < elite; i++) next.push(st.pop[order[i]].slice())
    const pick = () => {
      const k = Math.max(2, Math.round(num(p.tournament, 3)))
      let best = rng.int(N)
      for (let i = 1; i < k; i++) { const c = rng.int(N); if (num(costs[c], 1e9) < num(costs[best], 1e9)) best = c }
      return st.pop[best]
    }
    const pc = clamp01(num(p.pc, 0.85))
    const pm = clamp01(num(p.pm, 0.15))
    const sg = num(p.mutSigma, 0.18) * range
    while (next.length < N) {
      const pa = pick(), pb = pick()
      const child = new Array(D)
      for (let j = 0; j < D; j++) {
        // 算术交叉（单权重凸组合）+ 逐基因高斯变异
        const b = rng.next()
        let v = rng.next() < pc ? b * pa[j] + (1 - b) * pb[j] : (rng.next() < 0.5 ? pa[j] : pb[j])
        if (rng.next() < pm) v += rng.normal() * sg
        child[j] = clamp(v, lo, hi)
      }
      next.push(child)
    }
    st.pop = next
  } else if (algId === 'pso') {
    const w = num(p.w, 0.72), c1 = num(p.c1, 1.5), c2 = num(p.c2, 1.5)
    const vMax = num(p.vMaxRatio, 0.2) * range
    if (st.gbest == null || num(costs[bi]) < st.gbestCost) { st.gbest = st.pop[bi].slice(); st.gbestCost = num(costs[bi]) }
    for (let i = 0; i < st.pop.length; i++) {
      if (num(costs[i]) < st.pbestCost[i]) { st.pbestCost[i] = num(costs[i]); st.pbest[i] = st.pop[i].slice() }
      for (let j = 0; j < D; j++) {
        st.vel[i][j] = w * st.vel[i][j]
          + c1 * rng.next() * (st.pbest[i][j] - st.pop[i][j])
          + c2 * rng.next() * (st.gbest[j] - st.pop[i][j])
        st.vel[i][j] = clamp(st.vel[i][j], -vMax, vMax)
        st.pop[i][j] = clamp(st.pop[i][j] + st.vel[i][j], lo, hi)
      }
    }
  } else {
    // 模式搜索：以当前最优点为中心逐维探测，未改进则收缩步长，长期停滞则重启
    const cur = st.pop[0]
    const improved = num(costs[0]) < st.bestCostSeen - 1e-12
    if (improved || st.bestCostSeen === undefined) {
      st.bestCostSeen = num(costs[0])
      st.curBest = cur.slice()
      st.stall = 0
    } else {
      st.stall = num(st.stall, 0) + 1
      st.step = Math.max(num(p.stepMin, 0.01), st.step * num(p.shrink, 0.6))
    }
    if (st.stall >= Math.round(num(p.restartAfter, 6))) {
      st.pop[0] = randVec(D, lo, hi, rng)
      st.step = num(p.step0, 0.3)
      st.stall = 0
      note = '步长停滞，随机重启'
    } else {
      const base = (st.curBest || cur).slice()
      const dir = rng.next() < 0.5 ? -1 : 1
      const j = rng.int(D)
      base[j] = clamp(base[j] + dir * st.step * range, lo, hi)
      st.pop[0] = base
    }
  }

  let bc = Infinity, bv = null
  if (algId === 'pso' && st.gbest) { bc = st.gbestCost; bv = st.gbest.slice() }
  else {
    for (let i = 0; i < st.pop.length; i++) if (num(costs[i], 1e9) < bc) { bc = num(costs[i], 1e9); bv = st.pop[i].slice() }
  }
  if (bv && (st.gbest == null || bc < st.gbestCost)) { st.gbest = bv.slice(); st.gbestCost = bc }
  // 多样性：各维标准差的均值 / 区间宽度
  let div = 0
  if (st.pop.length > 1) {
    for (let j = 0; j < D; j++) {
      const arr = st.pop.map((v) => v[j])
      const mu = arr.reduce((s, v) => s + v, 0) / arr.length
      div += Math.sqrt(arr.reduce((s, v) => s + (v - mu) * (v - mu), 0) / arr.length)
    }
    div /= Math.max(D * range, 1e-9)
  }
  return { meanCost, bestCost: st.gbestCost, bestCoef: st.gbest ? st.gbest.slice() : (bv || []), diversity: div, note }
}

// ───────────────────────── SAC 智能体工厂 ─────────────────────────

/**
 * 按超参与回路配置创建 SAC 智能体（含动作布局、状态构成、动作边界）。
 * @returns {{agent, layout, spec, sDim, aDim, bounds}}
 */
export function createAgentFor(p, loops, rng) {
  const layout = layoutById(p.layout)
  const spec = {}
  for (const part of STATE_PARTS) {
    const key = stateParamKey(part.key)
    spec[part.key] = p[key] === undefined ? part.def : !!p[key]
  }
  const sDim = Math.max(1, stateDimOf(spec))
  const aDim = layout.dim
  // 动作物理边界按「回路 0」的配置生成（多回路时各回路分别生成，见 actionBoundsOf）
  const l0 = loops[0] || {}
  const ys = span(l0.yLo, l0.yHi), us = span(l0.uLo, l0.uHi)
  const { lo, hi } = coefBounds(p)
  const bounds = layout.bounds({
    sp: num(l0.sp, (ys.lo + ys.hi) / 2), yLo: ys.lo, yHi: ys.hi, uLo: us.lo, uHi: us.hi,
    base: l0.base || { kp: 1, ki: 0.05, kd: 0 }, coefLo: lo, coefHi: hi,
  })
  const hidden2 = Math.round(num(p.hidden2, 24))
  const hidden = hidden2 > 0 ? [Math.round(num(p.hidden1, 24)), hidden2] : [Math.round(num(p.hidden1, 24))]
  const agent = createSacAgent({
    sDim, aDim, hidden,
    lrActor: p.lrActor, lrCritic: p.lrCritic, lrAlpha: p.lrAlpha,
    gamma: p.gamma, tau: p.tau,
    alpha: p.alpha, alphaAuto: !!p.alphaAuto, entropyRatio: p.entropyRatio,
    alphaMin: p.alphaMin, alphaMax: p.alphaMax,
    sigma0: p.sigma0, logStdMin: p.logStdMin, logStdMax: p.logStdMax,
    rewardScale: p.rewardScale, batchSize: p.batchSize, replayCap: p.replayCap,
    gradClip: p.gradClip, actorOutGain: p.actorOutGain,
    // 动作空间统一为 [-1,1]，物理量程由 layout.unpack + bounds 负责，保证各维探索幅度可比
    actionLow: new Array(aDim).fill(-1),
    actionHigh: new Array(aDim).fill(1),
    rng,
  })
  return { agent, layout, spec, sDim, aDim, bounds }
}

export { createRng, createSacAgent, agentFromSnapshot, SAC_DEFAULTS }
