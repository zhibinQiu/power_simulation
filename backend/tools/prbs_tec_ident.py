#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""TEC 制冷片热系统辨识 —— 多电平 PRBS 开环激励数据采集脚本。

【用途】
    为 TEC（半导体制冷片）热系统辨识采集时序数据：由脚本按 5 电平 PRBS 主动改变
    制冷片「设定电流」，同步记录实际电流、输出电压、实时功率与四路温度，逐条追加写入 CSV。

【重要：开环激励，不做闭环控制】
    本脚本只负责「按 PRBS 序列给定电流 + 采样记录」，**不根据任何温度反馈调整电流**。
    水温高不降电流、水温低不升电流；读到的温度只用于记录与画图，绝不参与决策。
    （闭环控制会破坏输入与扰动独立的假设，使辨识结果有偏。）

【采集前必须固定的硬件条件（否则数据不可用）】
    1. 风扇转速恒定：热端散热风扇固定转速/固定 PWM，实验全程不得变化；
    2. 气路固定：风道、进出风口开度、散热片与风扇相对位置全程不变；
    3. 水杯水量固定：目标水杯水量（液位）全程不变，不加水、不蒸发补水、不搅拌；
    4. 冷却水侧固定：冷却水流量/水泵档位恒定（shuitong_temp 是热端边界条件，
       流量变化相当于给系统加了一个未测量的输入扰动）；
    5. 环境尽量稳定：门窗关闭、避免空调启停与日照直射（env_temp 用于事后检查
       环境漂移，若波动过大需重做实验）；
    6. 实验开始前系统应已处于稳态（建议先以 0A 或中间电平预热/预冷 10~30 min，
       可用 --warmup 参数在正式采集前静默等待）；
    7. 制冷片电源须工作在【恒流模式】：脚本初始化阶段自动写 work_mode=1 恒流、
       电压上限 24V、电流 0A，并置位输出开关（output_on=1，每次启动都做，且回读
       校验、最多重试 3 次；确认不了直接中止——输出关着时电流恒为 0A，跑满 83 分钟
       才发现数据作废代价太大）。若电源停在恒压模式，current_set 只是
       「限流上限」，电流不会跟随 PRBS，整段数据作废（可用 --no-init 跳过初始化）。
       ★ 关于「恒流下如何让电压最大」：恒流模式下电压【由负载决定】，电源只输出
         「刚好把电流顶到设定值」所需的电压（V = I·R_TEC + 塞贝克反电动势，实测
         5A 时约 9.2V），所以恒流时无法、也不需要让电压保持 24V。恒流下电压唯一
         要做的就是【把电压上限拉满】（voltage_set = 24V，脚本默认已如此），
         保证电流环不被限压卡住；一旦实际电压顶到上限，电流会掉下来跟不上设定
         （脚本对这种情况会告警）。真要电压恒定 24V，那必须切恒压模式，但那样
         current_set 退化成限流上限、PRBS 激励失效——两者不可兼得。

【激励信号】
    - 5 电平 PRBS：GF(5) 上的最大长度序列（m-sequence），电平 0..4 均匀映射到
      0 / 1.25 / 2.5 / 3.75 / 5 A。m-sequence 的 n 元组在一个周期内遍历所有非零
      组合，天然满足持续激励（PE）条件；
    - 每个电平最少保持 HOLD 个采样周期（默认 5 × 5s = 25s），保证温度有响应时间；
    - 序列总采样点默认 1000 个（200 个电平符号 × 5），≥ 800 要求；
      1000 × 5s ≈ 83 min。

【数据通道（对接能碳平台 / 一体机 nt001）】
    写设定：POST {platform}/api/box/publish
            {topic: "cmd/{box}/cmd",
             payload: '{"box":"nt001","cmd":"write","device":"zhileng-power",
                        "property":"current_set","value":2.5,"request_id":"..."}'}
            盒子 mapper 订阅 cmd/{box}/#，按点位 scale 换算成寄存器原始值写入保持寄存器。
    读数据：GET  {platform}/api/box/devices/realtime
            → devices[].twins[].{propertyName, reported, timestamp}
            （云端 CRD twins 主链路 + MQTT data/# 兜底）

【CSV】
    表头：t,current_set,current,power,voltage,shuitong_temp,servers_temp,env_temp,
          zhileng_temp,temp_age,temp_new
    t 为从实验开始计时的秒数（0, 5, 10, ...）；缺测写空（pandas 读作 NaN）。
    power 为制冷片实时功率（W，来自 zhileng-power 的 power 点位，输入寄存器 3、
    scale 0.01），与 current 同拍读取——功率是热流的直接来源，做热系统辨识时
    可用它核算 TEC 实际注入/抽走的热量（P = I·V，含塞贝克效应与内阻发热）。
    voltage 为实际输出电压（V，输入寄存器 0、scale 0.01），恒流模式下由负载决定、
    不是设定值；用它判断电流环有没有被电压上限卡住（接近 24V 即为限压），
    并与 current 相乘复核 power 是否自洽。
    zhileng_temp 为【冷端】风口温度：电流越大冷端越冷，出风温度越低（增益为负）。

【测量滞后（LoRa 温度）及其处理 —— 必读】
    四路温度都是 LoRa 终端，更新周期约 15s，而平台实时接口只返回「最近一次上行」
    的值：读数的真实时刻比本拍名义采样时刻早 0~15s 且随机抖动。若直接把该值记在
    名义时刻 t 上，等于给输出通道加了一个随机纯延迟，辨识出的模型会有偏。脚本按
    三条口径处理，并在 CSV 末尾给出两列辅助信息（temp_age / temp_new）：
      1) temp_age（秒）= 本拍四路读数里最大的 age。用「t - temp_age」即可还原读数
         的真实时刻，把随机滞后补偿掉（辨识时用它重建时间轴，别直接用 t）；
      2) temp_new（0/1）= 本拍是否有通道拿到了新上行。温度 15s 更新而采样 5s 时，
         约 2/3 的行是上拍旧值（零阶保持），只取 temp_new=1 的行即得到无重复序列；
      3) age 超过 --max-age（默认 45s）的陈旧读数按【缺测】写空——现场应答率不足时
         age 可达数分钟，把这种值写进 CSV 等于伪造动态轨迹，必须丢弃后插值。

【用法】
    # 1) 只生成并自检序列（不接触硬件，推荐先跑一次）
    python3 backend/tools/prbs_tec_ident.py --plan-only

    # 2) 空跑验证流程（模拟硬件，不写真实设备）
    python3 backend/tools/prbs_tec_ident.py --dry-run --symbols 6 --ts 1 --out /tmp/dry.csv

    # 3) 正式采集（默认 1000 点 / 83 min）
    python3 backend/tools/prbs_tec_ident.py --out tec_prbs_run1.csv

    # 4) 指定服务器上的平台实例
    python3 backend/tools/prbs_tec_ident.py --platform http://36.151.146.71:40014

    运行时 Ctrl+C 会安全停机（电流置 0A）后再退出，已采数据不丢。
仅依赖 Python 3 标准库，无需安装任何第三方包。
"""

from __future__ import annotations

import argparse
import csv
import datetime as _dt
import itertools
import json
import math
import os
import random
import sys
import time
import urllib.error
import urllib.request
import uuid

# ---------------------------------------------------------------------------
# 一、默认配置（均可用命令行覆盖）
# ---------------------------------------------------------------------------

# ---- 平台 / 一体机 ----
PLATFORM = "http://127.0.0.1:8010"   # 本地开发实例；生产用 http://36.151.146.71:40014
BOX = "nt001"                        # 能碳一体机节点名（盒子 MQTT_BOX）
HTTP_TIMEOUT = 10.0                  # 单次 HTTP 超时（秒）

# ---- 操纵变量：TEC 制冷片电源 ----
PSU_DEVICE = "zhileng-power"         # 制冷片电源（24V/5A 数控电源，485 从站地址 3）
                                     #
                                     # ★ 2026-09-22 实测校准（恒流通道可用，操纵变量用电流）：
                                     #   3.0A→2.99A/6.75V、2.0A→2.02A/4.99V、4.0A→3.97A/9.21V
                                     #   误差 <1.5%，8s 内到位。
                                     # ★ 踩过的坑（勿复现）：设备复位后 485 地址会回到出厂值 3，
                                     #   若配置里仍是 1，写入会「显示成功但回读不变」，
                                     #   表现极像「HR1/HR6 不认写入」，实为地址不匹配。
                                     #   遇到写入无效时【先核对 slaveID】，别急着改寄存器语义。
PSU_PROP_SET = "current_set"         # 可写点位：设定输出电流（保持寄存器 1，0~500 → 0~5.00A）
PSU_PROP_FB = "current"              # 只读点位：实际输出电流（输入寄存器 1，scale 0.01）
PSU_PROP_POWER = "power"             # 只读点位：实际输出功率（输入寄存器 3，scale 0.01，单位 W）
PSU_PROP_VFB = "voltage"             # 只读点位：实际输出电压（输入寄存器 0，scale 0.01，单位 V）
                                     #   ★ 恒流模式下电压【由负载决定】，不是设定值：
                                     #     V = I·R_TEC + 塞贝克反电动势（实测 5A 时仅约 9.2V）。
                                     #     「让电压保持 24V 最大」在恒流下物理上做不到 —— 电源
                                     #     在恒流环里只会输出「刚好把电流顶到设定值」的电压；
                                     #     恒流模式唯一能做的是把 voltage_set 上限拉满到 24V，
                                     #     保证电流环不被限压卡住（电压顶到上限时电流会掉下来）。
LIMIT_V_RATIO = 0.98                 # 实际电压 ≥ 该比例 × 电压上限 → 判定「顶到限压」
PSU_PROP_ON = "output_on"            # 线圈 0：输出开关（设完电流必须置位才有输出）
                                     # ★ 每次启动都必须确保它为 1：输出关着 → 电流恒为 0A，
                                     #   整段 PRBS 全是废数据。且必须【回读校验】——这台电源
                                     #   出现过「写入返回成功但回读不变」（485 地址不匹配），
                                     #   只看写返回码会漏判。
OUTPUT_ON_RETRY = 3                  # 输出开关置 1 的最大尝试次数（每次都回读校验）
OUTPUT_ON_WAIT = 2.0                 # 置位后等待平台刷新再回读的时间（秒）
PSU_PROP_MODE = "work_mode"          # 保持寄存器 6：通讯选择模式下的工作模式
                                     #   0=恒压 1=恒流 2=恒压恒流 3=通讯选择
                                     # ★ 必须工作在恒流（1，或 2）模式，current_set 才是真正的
                                     #   操纵变量；恒压模式下它只是「限流上限」，电流不会跟随 PRBS
PSU_PROP_VSET = "voltage_set"        # 保持寄存器 0：设定输出电压上限（0~2400 → 0~24.00V）
                                     #   恒流模式下作为电压上限，给到 24V 才不会限制 5A 输出
PSU_WORK_MODE = 1                    # 默认恒流模式
PSU_VOLTAGE = 24.0                   # 默认电压上限 24V（TEC 实际压降由负载决定）

# ---- 被测量：四路温度（均为 LoRa 温度终端，属性名 temperature）----
TEMP_CHANNELS = [                    # (CSV 列名, 设备名, 属性名, 中文说明)
    ("shuitong_temp", "shuitong-temp", "temperature", "TEC 热端冷却水温度"),
    ("servers_temp", "servers-temp", "temperature", "目标水杯水温"),
    ("env_temp", "env-temp", "temperature", "环境室温（参考基准）"),
    # 风口温度：TEC 冷端散热片吹出的冷风温度，电流越大冷端越冷、出风温度越低（增益为负）。
    # 与 servers-temp 共用同一台 DR206 终端（站2/站7），
    # 由主设备 servers-temp 一主多从代采，读数周期与 servers-temp 同步。
    ("zhileng_temp", "zhileng-temp", "temperature", "冷端风口温度"),
]

# ---- 激励参数 ----
I_MIN, I_MAX = 0.0, 5.0              # 电流硬限幅（A），对应数控电源 0~5.00A
N_LEVELS = 5                         # 多电平 PRBS 电平数
LEVELS = [I_MIN + (I_MAX - I_MIN) * i / (N_LEVELS - 1) for i in range(N_LEVELS)]  # 0/1.25/2.5/3.75/5
TS = 5.0                             # 采样周期（秒）
HOLD = 5                             # 每个电平最少保持的采样周期数（5 × 5s = 25s）
N_SYMBOLS = 200                      # 电平符号数 → 200 × 5 = 1000 个采样点
MIN_SAMPLES = 800                    # 题目要求的序列长度下限
SETTLE = 3.0                         # 输出设定后等待稳定的时间（秒），必须 < TS
WARMUP = 0.0                         # 正式采集前的静默等待（秒），建议 600~1800

# ---- 持续激励（PE）自检 ----
PE_ORDER = 10                        # 检验 PE 的阶次（≥ 待辨识模型的阶次），按「输入更新率」计
PE_COND_LIMIT = 50.0                 # 符号级信息矩阵条件数上限（m-sequence 一般 < 10）
PE_COND_LIMIT_HOLD = 500.0           # 采样级（含 hold 展宽）条件数上限；展宽会带来相关性，
                                     # 只要满秩且条件数有界（≪1e12）即认为数值上可辨识

# ---- 异常保护 ----
MAX_WRITE_RETRY = 3                  # 单次写设定失败重试次数
MAX_CONSEC_WRITE_ERR = 3             # 连续写失败达此数 → 安全停机
MAX_CONSEC_MISSING = 20              # 连续温度缺测达此数 → 安全停机（数据已无意义）
STALE_SEC = 90.0                     # 功率读数新鲜度阈值（老化超时仅告警）
TEMP_UPDATE_SEC = 15.0               # LoRa 温度终端实测更新周期（s）= 平台 collectCycle 15s，
                                     # 一主多从串行问帧，实测四路 age 稳定 9~37s
MAX_SAMPLE_AGE = 45.0                # 温度读数新鲜度硬门控（s）：age 超此值按【缺测】写空，
                                     # 不再把数分钟前的陈旧值当作本拍观测写进 CSV
                                     # （env-temp 应答率低时 age 可达 300s+，旧值当新值写
                                     #  会让辨识出的动态完全失真）
FB_TOL = 1.0                         # 设定电流与实际电流偏差告警阈值（A）
P_SANE_MAX = 200.0                   # 功率合理性上限（W）：电源 24V×5A=120W，超此值视为异常读数
MAX_CONSEC_POWER_MISSING = 20        # 连续功率缺测达此数 → 告警（功率不参与停机判定）


class SafetyError(RuntimeError):
    """安全相关异常：触发后脚本会把电流置 0A 再退出。"""


# ---------------------------------------------------------------------------
# 二、多电平 PRBS 序列生成（GF(5) 上的 m-sequence）
# ---------------------------------------------------------------------------

def _gf5_step(state, coeffs, p=5):
    """线性反馈移位寄存器一步递推：s[k] = Σ coeffs[i]·s[k-1-i] (mod p)。

    state 为 (s[k-1], s[k-2], ..., s[k-n])，递推后返回新状态；末位系数非零时
    该映射可逆（状态图由纯循环构成），因此一定会在 5^n-1 步内回到初态。
    """
    nxt = sum(c * s for c, s in zip(coeffs, state)) % p
    return (nxt,) + state[:-1]


def _gf5_period(coeffs, n, p=5):
    """返回从非零初态出发的状态循环长度；等于 p^n-1 即说明多项式是本原多项式。"""
    init = (1,) + (0,) * (n - 1)
    s, steps = init, 0
    for _ in range(p ** n - 1):
        s = _gf5_step(s, coeffs, p)
        steps += 1
        if s == init:
            return steps
    return None


def find_primitive_coeffs(n, p=5):
    """确定性搜索 GF(p) 上 n 次本原多项式的系数 (a1..an)。

    判据：从初态 (1,0,...,0) 出发的循环长度恰为 p^n-1（此时全部非零状态被遍历，
    序列即为最大长度序列，具有理想自相关 → 满足持续激励条件）。
    末位系数必须非零（否则递推不可逆，状态会收敛到 0）。
    """
    for coeffs in itertools.product(range(p), repeat=n):
        if coeffs[-1] == 0:
            continue
        if _gf5_period(coeffs, n, p) == p ** n - 1:
            return coeffs
    raise RuntimeError("未找到 GF(%d) 上的 %d 次本原多项式" % (p, n))


def gf5_msequence(n, coeffs, length, p=5):
    """生成 GF(p) 最大长度序列，返回 length 个 0..p-1 的电平符号。"""
    period = p ** n - 1
    if length > period:
        # 超过一个周期时按周期重复（统计特性不变，仍满足 PE）
        reps = int(math.ceil(length / period))
    else:
        reps = 1
    out, s = [], (1,) + (0,) * (n - 1)
    for _ in range(reps * period):
        out.append(s[0])          # 输出 = 寄存器首级
        s = _gf5_step(s, coeffs, p)
        if len(out) >= length:
            break
    return out


def build_prbs(n_symbols=N_SYMBOLS, n_levels=N_LEVELS, hold=HOLD):
    """生成「电平符号序列」并展开为逐采样点的电流设定序列。

    返回 (u, symbols, meta)：
      u        —— 长度 n_symbols*hold 的逐采样点设定电流（A），已按 hold 展宽；
      symbols  —— 电平符号序列（0..n_levels-1）；
      meta     —— 供打印/存档的元信息。
    """
    # 寄存器阶数：取满足 p^n-1 >= n_symbols 的最小 n（保证用到的是完整周期的一段）
    n = 1
    while n_levels ** n - 1 < n_symbols:
        n += 1
    coeffs = find_primitive_coeffs(n, p=n_levels)
    symbols = gf5_msequence(n, coeffs, n_symbols, p=n_levels)

    # 电平符号 → 电流（均匀划分 0 / 1.25 / 2.5 / 3.75 / 5 A），并做 0~5A 限幅
    amps = [clamp_current(LEVELS[s]) for s in symbols]

    # 展宽：每个电平保持 hold 个采样周期（最小驻留时间 = hold × Ts）
    u = []
    for a in amps:
        u.extend([a] * hold)

    meta = {
        "register_len": n,
        "coeffs": coeffs,
        "period": n_levels ** n - 1,
        "levels": [round(x, 4) for x in LEVELS],
        "n_symbols": len(symbols),
        "hold": hold,
        "n_samples": len(u),
        "duration_sec": len(u) * TS,
        "min_dwell_sec": hold * TS,
    }
    return u, symbols, meta


def clamp_voltage(v):
    """电压上限限幅：0~24V（数控电源量程）。"""
    v = float(v)
    return min(max(v, 0.0), 24.0)


def clamp_current(a):
    """电流硬限幅：任何情况下输出电流不得超出 0~5A。"""
    a = float(a)
    if a < I_MIN:
        return I_MIN
    if a > I_MAX:
        return I_MAX
    return a


# ---------------------------------------------------------------------------
# 三、持续激励（PE）自检：信息矩阵满秩且条件数有界
# ---------------------------------------------------------------------------

def _mat_rank(a, tol=1e-9):
    """高斯消元（部分选主元）求矩阵秩。"""
    m = [row[:] for row in a]
    n, k, rank = len(m), len(m[0]), 0
    for col in range(k):
        piv = max(range(rank, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < tol:
            continue
        m[rank], m[piv] = m[piv], m[rank]
        pv = m[rank][col]
        for r in range(n):
            if r != rank and abs(m[r][col]) > tol:
                f = m[r][col] / pv
                for c in range(col, k):
                    m[r][c] -= f * m[rank][c]
        rank += 1
        if rank == n:
            break
    return rank


def _solve(a, b):
    """解线性方程组 A x = b（高斯消元 + 部分选主元）。"""
    n = len(a)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(m[r][col]))
        if abs(m[piv][col]) < 1e-12:
            raise ZeroDivisionError("矩阵奇异，无法求解（说明输入激励不足）")
        m[col], m[piv] = m[piv], m[col]
        pv = m[col][col]
        for r in range(n):
            if r != col:
                f = m[r][col] / pv
                if f:
                    for c in range(col, n + 1):
                        m[r][c] -= f * m[col][c]
    return [m[i][n] / m[i][i] for i in range(n)]


def _cond_number(a, iters=200):
    """对称正定矩阵条件数 λmax/λmin（幂迭代 + 反幂迭代，纯标准库实现）。"""
    n = len(a)

    def mul(v):
        return [sum(a[i][j] * v[j] for j in range(n)) for i in range(n)]

    # λmax：幂迭代
    v = [1.0 / math.sqrt(n)] * n
    lam = 0.0
    for _ in range(iters):
        w = mul(v)
        nrm = math.sqrt(sum(x * x for x in w))
        if nrm < 1e-300:
            return float("inf")
        v = [x / nrm for x in w]
        lam = nrm
    lam_max = lam
    # λmin：反幂迭代（每步解一次 A x = v）
    lam_min = float("inf")
    try:
        v = [1.0 / math.sqrt(n)] * n
        for _ in range(60):
            x = _solve(a, v)
            nrm = math.sqrt(sum(t * t for t in x))
            if nrm < 1e-300:
                return float("inf")
            v = [t / nrm for t in x]
            lam_min = 1.0 / nrm
    except ZeroDivisionError:
        return float("inf")
    if lam_min <= 0:
        return float("inf")
    return lam_max / lam_min


def check_pe(u, order=PE_ORDER, cond_limit=PE_COND_LIMIT):
    """持续激励检验。

    构造回归向量 φ(k) = [1, u(k-1), ..., u(k-order)]（含常数项，对应带偏置的 ARX 模型），
    信息矩阵 R = (1/N)·Σ φφᵀ：
      - 满秩（秩 = order+1）⇒ 输入是 order 阶持续激励，最小二乘正规方程有唯一解；
      - 条件数有界 ⇒ 数值上可解。
    由于输入恒为正（0~5A，均值约 2.5A），常数项与各滞后项天然共线，含常数项的
    条件数会被均值放大；因此另算一份「去均值后」的激励协方差条件数 cond_cent，
    它才是衡量激励信号本身好坏的指标（PRBS 理想值接近 1~3）。

    注意：激励在 hold 个采样周期内保持不变，采样级回归量之间存在强相关性，
    所以符号级（输入更新率）用严格阈值，采样级只要求满秩 + 条件数有界。
    """
    n = len(u)
    if n <= order + 2:
        return {"ok": False, "reason": "序列太短，无法检验 %d 阶 PE" % order}
    # 含常数项的回归矩阵
    rows = [[1.0] + [u[k - i] for i in range(1, order + 1)] for k in range(order, n)]
    size = order + 1
    cnt = len(rows)
    R = [[sum(r[i] * r[j] for r in rows) / cnt for j in range(size)] for i in range(size)]
    rank = _mat_rank(R)
    cond = _cond_number(R)
    # 去均值后的激励协方差（只含 u 的各阶滞后）
    ur = [[u[k - i] for i in range(1, order + 1)] for k in range(order, n)]
    mean = [sum(r[j] for r in ur) / cnt for j in range(order)]
    Rc = [[sum((r[i] - mean[i]) * (r[j] - mean[j]) for r in ur) / cnt
           for j in range(order)] for i in range(order)]
    cond_cent = _cond_number(Rc)
    ok = (rank == size) and (cond_cent < cond_limit) and (cond < 1e8)
    return {"ok": ok, "rank": rank, "expected_rank": size, "cond": cond,
            "cond_cent": cond_cent, "order": order, "n_rows": cnt}


def seq_stats(u, symbols):
    """序列统计：各电平出现次数、切换次数、平均驻留、是否覆盖全部电平。"""
    counts = {lvl: 0 for lvl in LEVELS}
    for a in u:
        counts[a] = counts.get(a, 0) + 1
    switches = sum(1 for i in range(1, len(u)) if u[i] != u[i - 1])
    return {
        "level_counts": {round(k, 3): v for k, v in counts.items()},
        "all_levels_used": all(counts.get(l, 0) > 0 for l in LEVELS),
        "switches": switches,
        "avg_dwell_sec": (len(u) / switches * TS) if switches else float("inf"),
    }


# ---------------------------------------------------------------------------
# 四、硬件 IO：能碳平台通道 / 空跑模拟通道
# ---------------------------------------------------------------------------

class PlatformIO:
    """经能碳平台读写一体机 nt001 上的真实设备（HTTP → 云端 Broker → 盒子 mapper）。"""

    def __init__(self, base=PLATFORM, box=BOX, timeout=HTTP_TIMEOUT):
        self.base = base.rstrip("/")
        self.box = box
        self.timeout = timeout

    # ---- HTTP 基础 ----
    def _http(self, path, data=None):
        url = self.base + path
        body = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(
            url, data=body, method="POST" if body else "GET",
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    # ---- 写：下发设定电流 ----
    def write_point(self, device, prop, value):
        """写设备点位（cmd/{box}/cmd），value 为工程值（A），盒子按 scale 换算写寄存器。"""
        payload = json.dumps({
            "box": self.box,
            "cmd": "write",
            "device": device,
            "property": prop,
            "value": round(float(value), 4),
            "request_id": uuid.uuid4().hex[:12],
        }, ensure_ascii=False)
        return self._http("/api/box/publish",
                          {"topic": "cmd/%s/cmd" % self.box, "payload": payload})

    def set_current(self, amps):
        amps = clamp_current(amps)
        return self.write_point(PSU_DEVICE, PSU_PROP_SET, amps)

    def output_on(self):
        """打开电源输出（线圈 0）；电流设定写完后必须置位才有实际输出。"""
        return self.write_point(PSU_DEVICE, PSU_PROP_ON, 1)

    def read_psu(self):
        """读电源点位，返回 {属性名: 值}；读不到（平台异常/设备离线）返回空 dict。"""
        try:
            return {k: v[0] for k, v in (self.read_all().get(PSU_DEVICE) or {}).items()}
        except Exception:  # noqa: BLE001
            return {}

    def ensure_output_on(self):
        """把输出开关置 1 并【回读校验】，确认不了就抛异常中止。

        为什么不能只写不校验：电源曾出现「写入返回成功但回读不变」（485 地址不匹配），
        且现场掉电/复位后输出会自己关掉。输出关着时电流恒为 0A、PRBS 激励完全没进系统，
        跑满 83 分钟才发现数据作废的代价太大，所以宁可开跑前失败。
        """
        for attempt in range(1, OUTPUT_ON_RETRY + 1):
            try:
                self.output_on()
            except Exception as e:  # noqa: BLE001
                log("置位输出开关失败(%d/%d)：%s" % (attempt, OUTPUT_ON_RETRY, e))
            time.sleep(OUTPUT_ON_WAIT)
            on = self.read_psu().get(PSU_PROP_ON)
            if on is None:
                # 点位不在实时数据里（平台未采集该属性），无法校验，按写入成功处理
                log("提示：实时数据里没有 %s 点位，无法回读校验输出开关（按写入成功处理）"
                    % PSU_PROP_ON)
                return True
            if on >= 1:
                log("输出开关已确认置位：%s=%.0f" % (PSU_PROP_ON, on))
                return True
            log("输出开关回读仍为 %.0f，重试置位(%d/%d)" % (on, attempt, OUTPUT_ON_RETRY))
        raise SafetyError("连续 %d 次置位后输出开关仍未打开（%s 未变 1），"
                          "请检查 485 从站地址与接线后再跑" % (OUTPUT_ON_RETRY, PSU_PROP_ON))

    def init_psu(self, mode=PSU_WORK_MODE, voltage=PSU_VOLTAGE):
        """实验前初始化制冷片电源：恒流模式 → 电压上限 → 电流置 0 → 使能输出（带校验）。"""
        self.write_point(PSU_DEVICE, PSU_PROP_MODE, int(mode))
        self.write_point(PSU_DEVICE, PSU_PROP_VSET, clamp_voltage(voltage))
        self.write_point(PSU_DEVICE, PSU_PROP_SET, 0.0)
        return self.ensure_output_on()

    # ---- 读：实时读数 ----
    def raw_realtime(self):
        """原始实时数据（含设备 online 状态），供采集前预检用。"""
        return self._http("/api/box/devices/realtime")

    def read_all(self):
        """返回 {设备名: {属性名: (值, 时间戳)} }，值无效/缺失的属性不出现。"""
        data = self._http("/api/box/devices/realtime")
        out = {}
        for d in data.get("devices", []):
            fields = {}
            for tw in d.get("twins", []):
                if tw.get("invalid"):
                    continue
                v = tw.get("reported")
                if v is None:
                    continue
                try:
                    fields[tw.get("propertyName")] = (float(v), tw.get("timestamp"))
                except (TypeError, ValueError):
                    continue
            out[d.get("name")] = fields
        return out


class SimIO:
    """空跑模拟通道（--dry-run）：一阶热模型 + 测量噪声，接口与 PlatformIO 一致。

    用途：在不动真实硬件的前提下验证脚本时序、CSV 与 PRBS 逻辑。
    """
    def __init__(self):
        self.on = False            # 输出开关（模拟），ensure_output_on 后置 True
        self.i_set = 0.0
        self.t_env = 25.0
        self.t_cup = 25.0     # 目标水杯水温
        self.t_water = 24.0   # 热端冷却水温度
        self.t_feng = 25.0    # 风口温度（冷端散热片出风）
        self._noise = random.Random(20260922)

    def set_current(self, amps):
        self.i_set = clamp_current(amps)
        return {"ok": True}

    def output_on(self):
        self.on = True
        return {"ok": True}

    def ensure_output_on(self):
        self.on = True
        log("输出开关已确认置位：%s=1（空跑模拟）" % PSU_PROP_ON)
        return True

    def init_psu(self, mode=PSU_WORK_MODE, voltage=PSU_VOLTAGE):
        self.i_set = 0.0
        return self.ensure_output_on()

    def read_all(self):
        # 注：仅用于空跑，真实采集请用 PlatformIO
        # 水杯水温：制冷电流越大越冷（一阶惯性，tau ≈ 240s，静态增益 -2.0 ℃/A）
        self.t_cup += (TS / 240.0) * (self.t_env - 2.0 * self.i_set - self.t_cup)
        # 热端冷却水：电流越大越热（tau ≈ 120s，静态增益 +1.2 ℃/A）
        self.t_water += (TS / 120.0) * (self.t_env + 1.2 * self.i_set - self.t_water)
        # 风口温度：冷端出风，电流越大冷端越冷、出风越凉（静态增益为负，-1.5 ℃/A）；
        # 风道热容远小于水杯，响应比水温快（tau ≈ 60s）
        self.t_feng += (TS / 60.0) * (self.t_env - 1.5 * self.i_set - self.t_feng)
        self.t_env += self._noise.uniform(-0.01, 0.01)
        now = time.time()
        n = lambda: self._noise.uniform(-0.05, 0.05)
        # 功率：P = I·V_te，V_te 随电流上升（内阻 + 塞贝克反电动势），5A 时约 40W
        i_act = max(0.0, self.i_set + n())
        v_te = 2.0 + 1.2 * i_act
        p_act = max(0.0, i_act * v_te + self._noise.uniform(-0.2, 0.2))
        return {
            PSU_DEVICE: {PSU_PROP_FB: (i_act, now), PSU_PROP_POWER: (p_act, now),
                         PSU_PROP_VFB: (v_te + self._noise.uniform(-0.02, 0.02), now),
                         PSU_PROP_ON: (1.0 if self.on else 0.0, now)},
            "shuitong-temp": {"temperature": (self.t_water + n(), now)},
            "servers-temp": {"temperature": (self.t_cup + n(), now)},
            "env-temp": {"temperature": (self.t_env + n(), now)},
            "zhileng-temp": {"temperature": (self.t_feng + n(), now)},
        }


# ---------------------------------------------------------------------------
# 五、主流程
# ---------------------------------------------------------------------------

def _fmt(v):
    """CSV 数值格式化：None（缺测）→ 空；去掉多余的尾随 0（1.250 → 1.25）。"""
    if v is None:
        return ""
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-9:
            return str(int(round(v)))
        return ("%.4f" % v).rstrip("0").rstrip(".")
    return str(v)


def log(msg):
    print("[%s] %s" % (_dt.datetime.now().strftime("%H:%M:%S"), msg), flush=True)


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="TEC 制冷片热系统辨识：多电平 PRBS 开环激励数据采集",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--platform", default=PLATFORM, help="能碳平台地址")
    p.add_argument("--box", default=BOX, help="能碳一体机节点名")
    p.add_argument("--out", default=None, help="CSV 输出路径（默认 tec_prbs_<时间戳>.csv）")
    p.add_argument("--symbols", type=int, default=N_SYMBOLS, help="PRBS 电平符号数")
    p.add_argument("--ts", type=float, default=TS, help="采样周期（秒）")
    p.add_argument("--hold", type=int, default=HOLD, help="每个电平保持的采样周期数")
    p.add_argument("--settle", type=float, default=SETTLE, help="输出后等待稳定的时间（秒）")
    p.add_argument("--max-age", type=float, default=MAX_SAMPLE_AGE,
                   help="温度读数新鲜度硬门控（秒）：age 超过此值按缺测写空，"
                        "建议取温度更新周期的 2~3 倍")
    p.add_argument("--warmup", type=float, default=WARMUP, help="采集前静默等待（秒）")
    p.add_argument("--pe-order", type=int, default=PE_ORDER, help="PE 检验阶次")
    p.add_argument("--dry-run", action="store_true", help="空跑（模拟硬件，不写真实设备）")
    p.add_argument("--plan-only", action="store_true", help="只生成并自检序列，不采集")
    p.add_argument("--work-mode", type=int, default=PSU_WORK_MODE,
                   help="电源工作模式：0=恒压 1=恒流 2=恒压恒流（辨识电流通道必须用 1 或 2）")
    p.add_argument("--voltage", type=float, default=PSU_VOLTAGE,
                   help="电压上限（V），恒流模式下仅作上限，需高于 TEC 实际压降")
    p.add_argument("--no-init", action="store_true",
                   help="跳过实验前的电源初始化（恒流模式/电压上限/电流归零）；"
                        "无论是否加这个参数，启动都会把输出开关置 1 并回读校验")
    return p.parse_args(argv)


def preflight(io):
    """采集前预检：确认平台上看得到制冷片电源与三路温度设备，并打印当前读数。

    设备名对不上（改名/节点配错）时直接在开跑前失败，避免跑 80 分钟拿到空 CSV。
    """
    need = [PSU_DEVICE] + [c[1] for c in TEMP_CHANNELS]
    data = io.raw_realtime()
    devs = {d.get("name"): d for d in data.get("devices", [])}
    miss = [n for n in need if n not in devs]
    if miss:
        raise SafetyError("平台实时数据里找不到设备 %s（请检查 --platform/--box 与设备名）" % miss)
    for name in need:
        d = devs[name]
        vals = {tw.get("propertyName"): tw.get("reported") for tw in d.get("twins", [])}
        log("预检 %-14s state=%-9s %s" % (name, d.get("state"), vals))
    # 功率点位缺失不会导致采集中断，但 CSV 的 power 列会全空，提前告知
    psu_props = {tw.get("propertyName") for tw in devs[PSU_DEVICE].get("twins", [])}
    for _p in (PSU_PROP_POWER, PSU_PROP_VFB):
        if _p not in psu_props:
            log("警告：%s 上没有 %s 点位，CSV 的 %s 列将全为空" % (PSU_DEVICE, _p, _p))


def print_hardware_notice():
    log("=" * 72)
    log("采集前请确认硬件已固定（全程不得变动）：")
    log("  1) 风扇转速恒定（固定转速/固定 PWM）")
    log("  2) 气路固定（风道、进出风口开度、散热片位置不变）")
    log("  3) 水杯水量固定（不加水、不补水、不搅拌）")
    log("  4) 冷却水流量/水泵档位恒定")
    log("  5) 环境稳定（关门窗、避免空调启停与日照）")
    log("  6) 系统已处于稳态（可用 --warmup 先静默等待）")
    log("本脚本为开环激励：不根据任何温度反馈调整电流。")
    log("=" * 72)


def sample_temps(snap, prev_ts, now, max_age=MAX_SAMPLE_AGE):
    """从实时快照里取四路温度，并给出本拍的「滞后量」与「是否有新值」。

    返回 (vals, missing, age_max, has_new)：
      vals      {列名: 温度}——缺测或陈旧被丢弃的通道为 None；
      missing   无效通道数（缺测 + 陈旧丢弃）；
      age_max   四路里最大的读数 age（秒），None 表示一路都没读到；
      has_new   本拍是否有任一通道的时间戳相比上一拍发生变化（拿到新上行）。
      prev_ts   由调用方持有并在各拍间传递，用于判定「是否新值」。

    ★ 滞后处理的三条口径（详见文件头【测量滞后（LoRa 温度）及其处理】）：
      1) 平台返回的是最近一次上行值，其真实时刻 = twin 的 timestamp，比本拍名义
         采样时刻早 0~一个更新周期且随机抖动 → CSV 记 age，辨识时用 (t - age)
         还原真实时刻，消除随机纯延迟；
      2) 采样快于更新时多数行是上拍旧值 → 用 timestamp 变化与否标记 has_new，
         供辨识阶段重采样（只取新值行）；
      3) age 超过 max_age 的陈旧读数按缺测丢弃，绝不写入 —— 现场应答率不足时
         age 可达数分钟，写入即伪造动态轨迹。
    """
    vals, ages, missing, has_new = {}, [], 0, False
    for col, dev, prop, desc in TEMP_CHANNELS:
        got = (snap.get(dev) or {}).get(prop)
        if got is None:
            vals[col] = None
            missing += 1
            continue
        value, ts = got[0], got[1]
        age = (now - ts) if ts else None
        if age is not None:
            ages.append(age)
            if ts != prev_ts.get(col):
                has_new = True
            prev_ts[col] = ts
            if age > max_age:
                vals[col] = None
                missing += 1
                log("陈旧读数丢弃：%s(%s) age=%.0fs > %.0fs，按缺测处理"
                    % (col, desc, age, max_age))
                continue
        vals[col] = value
    return vals, missing, (max(ages) if ages else None), has_new


def main(argv=None):
    args = parse_args(argv)

    # 全局参数允许命令行覆盖（模块级常量被多处引用，这里做一次回填）
    global TS, SETTLE, MAX_SAMPLE_AGE
    TS = args.ts
    SETTLE = args.settle
    MAX_SAMPLE_AGE = args.max_age
    if SETTLE >= TS:
        raise SystemExit("参数错误：--settle(%.1fs) 必须小于采样周期 --ts(%.1fs)" % (SETTLE, TS))
    if args.hold < 1:
        raise SystemExit("参数错误：--hold 必须 >= 1")
    if MAX_SAMPLE_AGE < TEMP_UPDATE_SEC:
        log("警告：--max-age(%.0fs) 小于温度更新周期(%.0fs)，正常读数也会被判缺测"
            % (MAX_SAMPLE_AGE, TEMP_UPDATE_SEC))
    if TS < TEMP_UPDATE_SEC:
        log("提示：采样周期 Ts=%.1fs 快于温度更新周期 %.0fs，约 %.0f%% 的温度行会是上拍旧值"
            % (TS, TEMP_UPDATE_SEC, 100.0 * (1.0 - TS / TEMP_UPDATE_SEC)))
        log("      CSV 已记录 temp_age/temp_new：辨识时用 (t - temp_age) 还原读数真实时刻，"
            "或只取 temp_new=1 的行重采样")

    # ---- 1) 生成 PRBS 序列并自检 ----
    u, symbols, meta = build_prbs(n_symbols=args.symbols, n_levels=N_LEVELS, hold=args.hold)
    if len(u) < MIN_SAMPLES:
        log("警告：采样点 %d < 要求的 %d，请增大 --symbols 或 --hold" % (len(u), MIN_SAMPLES))
    st = seq_stats(u, symbols)
    # PE 检验 ①：符号级（输入每 hold×Ts 才更新一次，这是真正的激励自由度所在）
    amp_symbols = [clamp_current(LEVELS[s]) for s in symbols]
    pe_sym = check_pe(amp_symbols, args.pe_order, PE_COND_LIMIT)
    # PE 检验 ②：采样级（展宽后回归量相关，条件数天然偏大，只要求满秩且有界）
    pe = check_pe(u, args.pe_order, PE_COND_LIMIT_HOLD)
    pe_ok = bool(pe_sym["ok"] and pe["ok"])

    log("PRBS 序列：GF(%d) m-sequence，寄存器阶数 n=%d，系数=%s，周期=%d"
        % (N_LEVELS, meta["register_len"], meta["coeffs"], meta["period"]))
    log("电平档位(A)：%s ；符号数=%d，每符号保持 %d 个采样点（最小驻留 %.0fs）"
        % (meta["levels"], meta["n_symbols"], meta["hold"], meta["min_dwell_sec"]))
    log("采样周期 Ts=%.1fs，采样点=%d，总时长=%.1f min"
        % (TS, meta["n_samples"], meta["duration_sec"] / 60.0))
    log("电平分布：%s ；覆盖全部电平=%s ；切换次数=%d，平均驻留=%.1fs"
        % (st["level_counts"], st["all_levels_used"], st["switches"], st["avg_dwell_sec"]))
    log("（电平计数不完全均衡是截取完整周期 %d 个符号中的 %d 个所致，不影响 PE）"
        % (meta["period"], meta["n_symbols"]))
    # 序列太短时 check_pe 走 early-return（只有 ok/reason，没有 order），用 get 兜底
    log("PE 检验① 符号级（%d 阶，输入更新率 %.0fs）：rank=%d/%d，cond(去均值)=%.2f → %s%s"
        % (pe_sym.get("order", args.pe_order), meta["min_dwell_sec"], pe_sym.get("rank", -1),
           pe_sym.get("expected_rank", -1), pe_sym.get("cond_cent", float("inf")),
           "满足持续激励" if pe_sym["ok"] else "不满足！",
           "" if pe_sym["ok"] else "（%s）" % pe_sym.get("reason", "")))
    log("PE 检验② 采样级（%d 阶，Ts=%.1fs，电平保持带来相关性）：rank=%d/%d，"
        "cond(去均值)=%.1f，cond(含常数项)=%.1f → %s%s"
        % (pe.get("order", args.pe_order), TS, pe.get("rank", -1), pe.get("expected_rank", -1),
           pe.get("cond_cent", float("inf")), pe.get("cond", float("inf")),
           "满足持续激励" if pe["ok"] else "不满足！",
           "" if pe["ok"] else "（%s）" % pe.get("reason", "")))
    if not pe_ok:
        raise SystemExit("激励信号不满足 PE 条件，请增大 --symbols 或降低 --pe-order 后重试")
    if not st["all_levels_used"]:
        log("警告：序列未覆盖全部 5 个电平（可能 --symbols 过小）")

    if args.plan_only:
        print_hardware_notice()
        log("plan-only 模式：仅生成并自检序列，未接触硬件。")
        return 0

    # ---- 2) 打开 CSV ----
    out_path = args.out or ("tec_prbs_%s.csv" % _dt.datetime.now().strftime("%Y%m%d_%H%M%S"))
    out_dir = os.path.dirname(os.path.abspath(out_path))
    if out_dir and not os.path.isdir(out_dir):
        os.makedirs(out_dir, exist_ok=True)
    f = open(out_path, "w", newline="", encoding="utf-8")
    writer = csv.writer(f)
    writer.writerow(["t", "current_set", "current", "power", "voltage",
                     "shuitong_temp", "servers_temp", "env_temp", "zhileng_temp",
                     "temp_age", "temp_new"])
    f.flush()
    os.fsync(f.fileno())
    log("CSV 已创建：%s" % os.path.abspath(out_path))

    # ---- 3) 硬件通道 ----
    io = SimIO() if args.dry_run else PlatformIO(args.platform, args.box)
    if args.dry_run:
        log("空跑模式（--dry-run）：使用模拟热模型，不会写入真实设备")

    print_hardware_notice()

    consec_write_err = 0
    consec_missing = 0
    consec_power_missing = 0
    last_set = None
    prev_temp_ts = {}          # 上一拍各路温度的读数时间戳，用于判定「是否新值」
    exit_code = 0

    def safe_shutdown(reason=""):
        """安全停机：电流置 0A 后关闭文件。任何异常退出路径都必须走这里。"""
        try:
            io.set_current(0.0)
            log("安全停机：设定电流已置 0A")
        except Exception as e:  # noqa: BLE001
            log("安全停机失败（请手动确认电源输出）：%s" % e)
        try:
            f.flush()
            os.fsync(f.fileno())
            f.close()
        except Exception:  # noqa: BLE001
            pass
        log("已采集数据保存在：%s %s" % (os.path.abspath(out_path), reason))

    try:
        # ---- 4) 实验前：预检 + 使能输出 + 静默等待 ----
        if not args.dry_run:
            preflight(io)
        if not args.no_init:
            # 顺序：切恒流模式 → 电压上限 → 电流归零 → 使能输出
            # （恒压模式下 current_set 只是限流值，激励不会生效，必须切恒流）
            io.init_psu(args.work_mode, args.voltage)
            log("电源已初始化：work_mode=%d（%s），电压上限=%.2fV，电流=0A，输出使能"
                % (args.work_mode, {0: "恒压", 1: "恒流", 2: "恒压恒流"}.get(args.work_mode, "?"),
                   clamp_voltage(args.voltage)))
            if args.work_mode == 0:
                log("警告：work_mode=0 为恒压模式，current_set 只是限流上限，PRBS 激励不会生效！")
        else:
            # --no-init 只是跳过「模式/电压/电流」的初始化，输出开关仍必须开：
            # 关着的话电流恒为 0A，PRBS 根本没进系统，整段数据作废。
            io.ensure_output_on()
            log("--no-init：已跳过模式/电压/电流初始化，但仍强制确认输出开关=1")
        if args.warmup > 0:
            log("静默等待 %.0fs 让系统进入稳态（电流保持当前值）..." % args.warmup)
            time.sleep(args.warmup)

        t0 = time.time()
        log("开始采集：%d 点 × %.1fs，预计 %.1f 分钟"
            % (len(u), TS, len(u) * TS / 60.0))

        # ---- 5) 主循环：按 5s 节拍输出激励 + 采样记录 ----
        for k, set_a in enumerate(u):
            tick = t0 + k * TS                      # 本采样时刻的绝对时间
            now = time.time()
            if now < tick:                          # 对齐到节拍
                time.sleep(tick - now)
            elif now > tick + 0.5 * TS:
                # 读数/写设定耗时超过一个采样周期：CSV 里 t 仍是名义时刻，需警惕时间轴失真
                log("警告：实际节拍落后计划 %.1fs（第 %d 拍），请检查读数耗时" % (now - tick, k))

            # ① 按 PRBS 输出设定电流（只在电平变化时下发，减少无效写寄存器）
            if last_set is None or abs(set_a - last_set) > 1e-9:
                ok_write = False
                for attempt in range(1, MAX_WRITE_RETRY + 1):
                    try:
                        io.set_current(set_a)
                        ok_write = True
                        break
                    except Exception as e:  # noqa: BLE001
                        log("写设定电流失败(%d/%d)：%s" % (attempt, MAX_WRITE_RETRY, e))
                        time.sleep(1.0)
                if ok_write:
                    consec_write_err = 0
                else:
                    consec_write_err += 1
                    if consec_write_err >= MAX_CONSEC_WRITE_ERR:
                        raise SafetyError("连续 %d 次写设定失败" % consec_write_err)
                last_set = set_a

            # ② 等待稳定后再读数（每个采样点在周期内的相位保持一致）
            time.sleep(max(0.0, tick + SETTLE - time.time()))

            # ③ 读取实际电流、实时功率与三路温度
            try:
                snap = io.read_all()
            except Exception as e:  # noqa: BLE001
                snap = {}
                log("读数失败：%s" % e)

            psu = snap.get(PSU_DEVICE, {})
            fb = psu.get(PSU_PROP_FB)
            current = fb[0] if fb else None
            if current is not None and abs(current - set_a) > FB_TOL:
                log("警告：实际电流 %.2fA 与设定 %.2fA 偏差 > %.1fA"
                    % (current, set_a, FB_TOL))

            # 实时功率（W）：与电流同拍读自同一设备，缺测/异常只告警不中断
            pw = psu.get(PSU_PROP_POWER)
            power = pw[0] if pw else None
            if power is None:
                consec_power_missing += 1
                if consec_power_missing == MAX_CONSEC_POWER_MISSING:
                    log("警告：连续 %d 拍读不到功率（power 点位无数据）" % consec_power_missing)
            else:
                consec_power_missing = 0
                age = (time.time() - pw[1]) if pw[1] else None
                if age is not None and age > STALE_SEC:
                    log("警告：功率读数已老化 %.0fs，可能并非本拍实测值" % age)
                if power < 0 or power > P_SANE_MAX:
                    log("警告：功率读数 %.2fW 超出合理区间 0~%.0fW" % (power, P_SANE_MAX))

            # 实际输出电压（V）：恒流模式下由负载决定，不是设定值。
            # 用途是判断电流环有没有被电压上限卡住——顶到上限就意味着电流跟不上设定。
            vfb = psu.get(PSU_PROP_VFB)
            voltage = vfb[0] if vfb else None
            v_limit = clamp_voltage(args.voltage)
            if voltage is not None and v_limit > 0 and voltage >= LIMIT_V_RATIO * v_limit:
                log("警告：实际电压 %.2fV 已顶到电压上限 %.2fV（恒流环被限压，电流将跟不上设定）"
                    % (voltage, v_limit))

            # 读数时刻 = 名义采样时刻 tick + SETTLE，age 以真实读数时刻计算，
            # 这样 CSV 里的 (t - temp_age) 就是读数的真实时刻（名义 t 记 k*Ts）。
            temps, missing, temp_age, temp_new = \
                sample_temps(snap, prev_temp_ts, time.time(), MAX_SAMPLE_AGE)
            if missing:
                consec_missing += 1
                log("警告：本拍缺测 %d 路温度（连续 %d 拍）" % (missing, consec_missing))
                if consec_missing >= MAX_CONSEC_MISSING:
                    raise SafetyError("连续 %d 拍温度缺测，数据已不可用" % consec_missing)
            else:
                consec_missing = 0

            # ④ 记录本条样本（t 为从实验开始计时的秒数）
            row = [_fmt(k * TS), _fmt(set_a), _fmt(current), _fmt(power), _fmt(voltage)] + \
                  [_fmt(temps[c]) for c, _, _, _ in TEMP_CHANNELS] + \
                  ["" if temp_age is None else "%.1f" % temp_age, 1 if temp_new else 0]
            writer.writerow(row)
            f.flush()
            os.fsync(f.fileno())   # 立即落盘，断电/异常退出也不丢已采数据

            if k % 10 == 0 or k == len(u) - 1:
                done = (k + 1) * TS
                log("进度 %d/%d（%.0f/%.0f min）| set=%.2fA cur=%s V=%s P=%sW | "
                    "水杯=%s 冷却水=%s 环境=%s 风口=%s | age=%s 新值=%d"
                    % (k + 1, len(u), done / 60.0, len(u) * TS / 60.0, set_a,
                       _fmt(current), _fmt(voltage), _fmt(power), _fmt(temps["servers_temp"]),
                       _fmt(temps["shuitong_temp"]), _fmt(temps["env_temp"]),
                       _fmt(temps["zhileng_temp"]),
                       "-" if temp_age is None else "%.0fs" % temp_age, temp_new))

        log("采集完成：共 %d 条样本" % len(u))

    except KeyboardInterrupt:
        log("收到 Ctrl+C，正在安全停机...")
        exit_code = 130
    except SafetyError as e:
        log("触发异常保护：%s" % e)
        exit_code = 2
    except Exception as e:  # noqa: BLE001
        log("未预期错误：%r" % e)
        exit_code = 1
    finally:
        safe_shutdown()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
