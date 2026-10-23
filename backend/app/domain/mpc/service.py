"""服务层：模型可用性自检（能否启用）+ 目标温度/时限 -> 动作计划。

对外只有三个入口（api/mpc_router.py 直接转调）：
    get_status()   —— 依赖是否齐全、参数是否合规、功率公式与实测是否吻合、
                      求解器自检是否通过 => 得出「能否启用」的结论
    set_enabled()  —— 启用 / 停用（写 backend/data/mpc_state.json，重启后保持）
    get_plan()     —— 给定当前温度、目标温度、时限，输出可达性 + 分段动作 + 预测轨迹

「能不能启用」不是一个人为开关前的装饰：四项自检任一不过就返回 available=False，
前端据此禁用启用按钮并列出原因，避免在参数/依赖不成立时给出看起来正常的计划。
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
from typing import Dict, List, Optional

from app.core.config import DATA_DIR

from . import decision_log as DL
from . import params as P
from .energy_model import Action, build_action_set, check_against_measured
from .solver import SolverConfig, fan_only_is_enough, solve
from .thermal_model import ThermalParams

_STATE_PATH = os.path.join(DATA_DIR, "mpc_state.json")
#: 规划轨迹输出步长 [s]：与采集/反馈周期一致
TRAJ_DT = 15.0


# --------------------------------------------------------------------------
# 状态持久化
# --------------------------------------------------------------------------
def _read_state() -> dict:
    try:
        with open(_STATE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _write_state(data: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = _STATE_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, _STATE_PATH)


# --------------------------------------------------------------------------
# 自检
# --------------------------------------------------------------------------
def _check_deps() -> tuple:
    """运行环境自检：本模块**不依赖任何第三方包**。

    求解器是纯 Python 实现（档位 × 温度网格上的二维递推），不需要 numpy ——
    平台后端原先也没有 numpy 依赖，若为了一个线性插值去装科学计算栈，换台机器
    部署就会像之前那样抛 `No module named 'numpy'`。这里只校验 Python 版本，
    numpy 存在与否都不影响结果。
    """
    v = sys.version_info
    if v < (3, 8):
        return False, f"Python {v.major}.{v.minor} 过低（需 ≥3.8）"
    extra = ""
    try:                       # 仅作信息展示：装了 numpy 也不会被用到
        import numpy  # noqa: F401
        extra = f"；检测到 numpy {numpy.__version__}（本实现不依赖）"
    except Exception:
        pass
    return True, f"纯 Python 实现，无第三方依赖（Python {v.major}.{v.minor}.{v.micro}）{extra}"


def _check_params() -> tuple:
    p = ThermalParams()
    problems = []
    if not (p.tau_s > 0):
        problems.append("tau 必须为正")
    if not (p.k_v < 0):
        problems.append("风扇增益 k_v 必须为负（电压升高应降温）")
    if not (p.b0 > 0):
        problems.append("自由平衡温度 b0 必须为正")
    if not (0 < P.TOL_K < 0.5):
        problems.append("终端容差越界")
    if not (P.MIN_HOLD_S > 0):
        problems.append("最小保持时长必须为正")
    if not P.FAN_V_ACTIONS or not P.TEC_I_ACTIONS:
        problems.append("动作档位表为空")
    if problems:
        return False, "；".join(problems)
    return True, (f"tau={p.tau_s:.0f}s, b0={p.b0:.2f}℃, k_v={p.k_v:+.3f}K/V, "
                  f"k_i={P.K_I_LIN:+.3f}K/A(0~3A)")


def _check_power() -> tuple:
    """功率公式 vs 实测档位。

    风扇看绝对偏差（低档相对误差能到 8%，但绝对值始终 <0.04 W）；
    制冷片看「相对 ≤5% 且绝对 ≤0.6 W」—— 逐档最大偏差在 2.25 A（+4.8%，0.57 W），
    整体 RMSE 0.328 W，这是拟合精度而非物理漂移（漂移是 TEC_P_REL_TOL=2%）。
    """
    worst_abs = 0.0
    worst_rel = 0.0
    fail = []
    for r in check_against_measured():
        err = r["p_model"] - r["p_meas"]
        if r["dev"] == "fan":
            worst_abs = max(worst_abs, abs(err))
            if abs(err) > P.FAN_FIT_ABS_TOL:
                fail.append(f"风扇 {r['level']:g}V 偏差 {err:+.3f} W")
        else:
            worst_rel = max(worst_rel, abs(r["rel_err"]))
            if abs(r["rel_err"]) > P.TEC_FIT_REL_TOL or abs(err) > P.TEC_FIT_ABS_TOL:
                fail.append(f"制冷片 {r['level']:g}A 偏差 {err:+.3f} W（{r['rel_err']*100:+.1f}%）")
    if fail:
        return False, "；".join(fail)
    return True, (f"风扇最大绝对偏差 {worst_abs:.3f} W，"
                  f"制冷片最大相对偏差 {worst_rel*100:.1f}%")


def _check_solver() -> tuple:
    """跑三个已知场景，验证求解器可用、结论与标定一致、耗时满足实时性。

    时间预算按**纯 Python 实现**定：单段 ≈ A·G = 40 × ~5600 ≈ 22 万次内循环，
    实测 50~110 ms/段（60 min 视界的 12 段约 0.5 s）。控制周期 15 s，
    故预算取 2 s —— 允许慢机器，又能挡住「求解器被改成指数级」这类退化。
    历史上这里写死 200 ms，是 numpy 向量化时期的数字；换成纯 Python 后会误判
    「超实时预算」，把可用模型标成不可启用（页面表现为红色「不可启用」）。
    """
    cases = [
        (45.0, 39.0, 720.0),    # 可达（16V→18V）
        (45.0, 40.0, 600.0),    # 可达（15V→16V）
        (45.0, 35.0, 480.0),    # 不可达（差 ~4.98 K）
    ]
    got = []
    t0 = time.perf_counter()
    for tn, tt, h in cases:
        r = solve(tn, tt, h, P.TENV_DEFAULT, P.TWATER_DEFAULT)
        got.append(r)
    ms = (time.perf_counter() - t0) * 1000.0 / len(cases)
    if not got[0].ok or not got[1].ok:
        return False, "求解器未能在已知可达场景给出达标解"
    if got[2].ok:
        return False, "求解器把已知不可达场景判成可达（模型参数可能被改坏）"
    budget_ms = 2000.0
    if ms > budget_ms:
        return False, f"单次求解 {ms:.0f} ms，超实时预算 {budget_ms:.0f} ms"
    return True, (f"三场景结论一致，单次求解 ≈{ms:.0f} ms"
                  f"（15 s 周期裕度 {15000/ms:.0f}×）")


def _availability_light() -> bool:
    """规划路径用的轻量可用性判定：只跑廉价的三项（依赖 / 参数 / 功率公式）。

    不跑「求解器自检」—— 本次请求本身就在求解，求解失败会以异常/不达标暴露出来。
    早先 get_plan 里直接调 get_status()，于是每点一次「求解」都额外跑 3 次已知场景，
    实测把一次 12 min 决策从 ~350 ms 拖到 ~1175 ms，纯属重复劳动。
    """
    for fn in (_check_deps, _check_params, _check_power):
        try:
            ok, _ = fn()
        except Exception:  # noqa: BLE001
            return False
        if not ok:
            return False
    return True


def _run_checks() -> List[dict]:
    specs = [
        ("deps", "运行依赖", True, _check_deps),
        ("params", "标称参数", True, _check_params),
        ("power", "功率函数 vs 实测", True, _check_power),
        ("solver", "求解器自检", True, _check_solver),
    ]
    out = []
    for key, label, required, fn in specs:
        try:
            ok, detail = fn()
        except Exception as e:  # noqa: BLE001 —— 自检本身不允许抛异常
            ok, detail = False, f"自检异常：{e}"
        out.append({"key": key, "label": label, "ok": bool(ok),
                    "required": required, "detail": detail})
    return out


def get_status() -> dict:
    """模型状态：能否启用 + 参数与档位一览 + 自检明细。"""
    checks = _run_checks()
    available = all(c["ok"] for c in checks if c["required"])
    st = _read_state()
    enabled = bool(st.get("enabled")) and available
    return {
        "ok": True,
        "model": {
            "name": P.MODEL_NAME,
            "version": P.MODEL_VERSION,
            "source": "simulate_model/temp_optimize_model（灰箱 RC + 离散档位 DP）",
            "solver": "动态规划（分段常数，最小保持 300 s）",
        },
        "available": available,
        "enabled": enabled,
        "enabled_saved": bool(st.get("enabled")),
        "enabled_at": st.get("enabled_at"),
        "checks": checks,
        "params": {
            "tau_s": ThermalParams().tau_s,
            "b0": P.B0,
            "tenv_ref": P.TENV_REF,
            "k_v": P.K_V,
            "k_i_lin": P.K_I_LIN,
            "min_hold_s": P.MIN_HOLD_S,
            "tol_K": P.TOL_K,
            "full_power": {"v_fan": P.FULL_V, "i_tec": P.FULL_I},
        },
        "levels": {
            "fan_v": list(P.FAN_V_ACTIONS),
            "tec_i": list(P.TEC_I_ACTIONS),
            "tec_blacklist": list(P.TEC_I_BLACKLIST),
            "allow_5a": P.ALLOW_5A,
        },
        "power_fn": {
            "fan": "P = 0.002812·V² + 0.004292·V",
            "tec": "P = 2.0693·I² + 0.8562·I",
        },
        "limits": {
            "t_now": [P.T_NOW_MIN, P.T_NOW_MAX],
            "t_target": [P.T_TARGET_MIN, P.T_TARGET_MAX],
            "horizon_s": [P.HORIZON_MIN_S, P.HORIZON_MAX_S],
            "model_domain": [P.T_LO, P.T_HI],
        },
        "mode_switch": {"enter": P.T_FULL_ENTER, "exit": P.T_FULL_EXIT},
        # 动作字段 -> 设备点位（页面展示「下发到哪」，也便于现场核对配置）
        "mapping": _mapping_dict(),
        "note": ("MPC 控温模型只做「给定目标温度与时限的能耗最优档位求解」；"
                 "5 A 档默认禁用（多 34.8 W 无可测降温）。"),
    }


def set_enabled(enabled: bool) -> dict:
    """启用 / 停用模型。仅在自检全通过时允许启用。"""
    st = get_status()
    if enabled and not st["available"]:
        bad = [c["label"] + "：" + c["detail"] for c in st["checks"] if not c["ok"]]
        return {"ok": False, "error": "模型自检未通过，无法启用：" + "；".join(bad)}
    data = _read_state()
    data["enabled"] = bool(enabled)
    data["enabled_at"] = time.strftime("%Y-%m-%d %H:%M:%S") if enabled else None
    _write_state(data)
    DL.write("enable" if enabled else "disable",
             "启用 MPC 控温模型" if enabled else "停用 MPC 控温模型",
             ["求解结果可以下发到现场控制回路" if enabled else "求解仍可用，但不再视为已下发状态"])
    return {"ok": True, "enabled": bool(enabled), "status": get_status()}


# --------------------------------------------------------------------------
# 下发（把计划中的某一段真正写到设备点位上）
# --------------------------------------------------------------------------
def apply_step(v_fan: float, i_tec: float, hold_s: Optional[float] = None,
               index: Optional[int] = None, note: str = "",
               dry_run: bool = False) -> dict:
    """把一组 (v_fan, i_tec) 下发到风扇电源 / 制冷片电源。

    两道闸门，缺一不可：
      ① 模型自检必须通过（参数/功率公式/求解器都成立，否则档位本身就不可信）；
      ② 必须已启用（启用 = 现场确认可以干预设备，这是唯一的开关式确认）。

    真正的写点位在 actuator 里：风扇恒压写 voltage_set，制冷片恒流写 current_set，
    并自动补齐 work_mode / output_on 这两个「不置位就等于没输出」的前置点位。

    dry_run=True 时只校验 + 组装载荷，不发 MQTT（现场联调先核对点位与取值）。
    """
    from . import actuator as AC

    if not _availability_light():
        return {"ok": False, "error": "模型自检未通过，拒绝下发（档位依据不成立）"}
    if not bool(_read_state().get("enabled")):
        return {"ok": False,
                "error": "模型尚未启用：请先点右上角「启用该模型」，启用后才允许下发到设备"}

    try:
        res = AC.apply(float(v_fan), float(i_tec), force=True,
                       hold_s=None if hold_s is None else float(hold_s), note=note,
                       dry_run=dry_run)
    except AC.ActuatorError as e:
        return {"ok": False, "error": str(e)}

    res["index"] = index
    res["hold_s"] = hold_s
    return res


def stop_output(reason: str = "手动停止", dry_run: bool = False) -> dict:
    """两路输出归零（先断输出再清设定）。停止不受「是否启用」限制。"""
    from . import actuator as AC

    try:
        return AC.stop(reason=reason, dry_run=dry_run)
    except AC.ActuatorError as e:
        return {"ok": False, "error": str(e)}


def _mapping_dict() -> dict:
    """动作字段 -> 设备点位的映射（页面展示 / 排查用）。"""
    from . import actuator as AC

    return {
        "v_fan": {"device": AC.FAN_DEV, "property": AC.FAN_V_PROP,
                  "mode": {"property": AC.FAN_MODE_PROP, "value": AC.FAN_MODE_CV,
                           "label": "恒压"},
                  "on": AC.FAN_ON_PROP, "range": [AC.FAN_V_MIN, AC.FAN_V_MAX], "unit": "V"},
        "i_tec": {"device": AC.TEC_DEV, "property": AC.TEC_I_PROP,
                  "mode": {"property": AC.TEC_MODE_PROP, "value": AC.TEC_MODE_CC,
                           "label": "恒流"},
                  "on": AC.TEC_ON_PROP, "range": [AC.TEC_I_MIN, AC.TEC_I_MAX], "unit": "A"},
    }


def get_mapping() -> dict:
    """对外暴露的映射查询（与 status.mapping 同一份内容）。"""
    return _mapping_dict()


# --------------------------------------------------------------------------
# 规划
# --------------------------------------------------------------------------
def _validate(t_now: float, t_target: float, horizon_s: float,
              tenv: float, twater: float) -> None:
    def bad(msg):
        raise ValueError(msg)

    if not (P.T_NOW_MIN <= t_now <= P.T_NOW_MAX):
        bad(f"当前温度需在 {P.T_NOW_MIN:.0f}~{P.T_NOW_MAX:.0f} ℃ 之间")
    if not (P.T_TARGET_MIN <= t_target <= P.T_TARGET_MAX):
        bad(f"目标温度需在 {P.T_TARGET_MIN:.0f}~{P.T_TARGET_MAX:.0f} ℃ 之间"
            f"（上限 {P.T_TARGET_MAX} 是因为预测模型只到 45 ℃）")
    if t_target >= t_now - 0.01:
        bad("目标温度必须低于当前温度：本模型只求解降温（制冷片不加热）")
    if not (P.HORIZON_MIN_S <= horizon_s <= P.HORIZON_MAX_S):
        bad(f"时限需在 {P.HORIZON_MIN_S/60:.0f}~{P.HORIZON_MAX_S/60:.0f} min 之间")
    if not (-10.0 <= tenv <= 45.0):
        bad("室温需在 -10~45 ℃ 之间")
    if not (0.0 <= twater <= 60.0):
        bad("水温需在 0~60 ℃ 之间")


def _traj_points(plan: List[dict], t_now: float, p: ThermalParams,
                 tenv: float, twater: float) -> List[dict]:
    """把分段常数计划展开成 15 s 网格的轨迹点（供前端折线图）。

    段内用真实一阶 RC 逐点推进（不要按两端线性细分）：段长 360 s 时弦与指数段的
    最大偏差约 0.07 K，画面会变成一条假直线，看不出「先快后慢」的降温特征。
    """
    pts = [{"t_s": 0.0, "T": round(t_now, 3)}]
    t_acc = 0.0
    t_cur = float(t_now)
    for seg in plan:
        a = Action(float(seg["v_fan"]), float(seg["i_tec"]))
        dur = float(seg["duration_s"])
        n = max(1, int(round(dur / TRAJ_DT)))
        dt = dur / n
        for k in range(1, n + 1):
            t_cur = p.advance(t_cur, a, dt, tenv, twater)
            pts.append({"t_s": round(t_acc + k * dt, 1), "T": round(t_cur, 3)})
        t_acc += dur
    return pts


def _constant_alternatives(t_now: float, t_target: float, horizon_s: float,
                           tenv: float, twater: float,
                           p: ThermalParams) -> List[dict]:
    """全程恒定单动作的对比表（现场最容易执行，也是 DP 解的校验基线）。"""
    rows = []
    for a in build_action_set(include_5a=P.ALLOW_5A):
        tend = p.advance(t_now, a, horizon_s, tenv, twater)
        rows.append({
            "v_fan": a.v_fan, "i_tec": a.i_tec, "power_w": round(a.power, 3),
            "final_T": round(tend, 2),
            "energy_wh": round(a.power * horizon_s / 3600.0, 4),
            "ok": bool(tend <= t_target + P.TOL_K),
        })
    rows.sort(key=lambda r: (not r["ok"], r["energy_wh"]))
    return rows[: P.ALT_TOP_N]


def _fmt_seg(i: int, seg: dict) -> str:
    return (f"段{i + 1} 下发 {seg['v_fan']:g} V / {seg['i_tec']:g} A，保持 {seg['duration_s']:.0f} s："
            f"{seg['T_start']:.2f} → {seg['T_end']:.2f} ℃"
            f"（{seg['power_w']:.3f} W，{seg['energy_wh']:.4f} Wh）")


def _decision_lines(*, t_now: float, t_target: float, horizon_s: float,
                    tenv: float, twater: float, alpha: float, tss_req: float,
                    tss_min: float, feasible: bool, shortfall: float,
                    mode: str, plan: List[dict], final_t: float,
                    energy_wh: float, baseline_wh: float, ms: float,
                    n_seg: int, seg_len: float, n_act: int,
                    handover: Optional[dict] = None,
                    reference: Optional[List[dict]] = None) -> List[str]:
    """把一次决策展开成人读的流水（页面「决策日志」与 mpc.log 共用同一份文本）。"""
    if mode == "handover" and handover:
        strategy = (f"策略：分段规则命中 —— 当前 {t_now:.2f} ℃ > {handover['threshold_C']:g} ℃，"
                    f"先满功率 {P.FULL_V:g} V / {P.FULL_I:g} A 降到该阈值"
                    f"（{handover['t_s']:.0f} s ≈ {handover['t_min']:.2f} min），"
                    f"剩余 {handover['remaining_s']:.0f} s 交由智能调控重解"
                    f"（目标 {t_target:.2f} ℃，{handover['phase2_segments']} 段 × "
                    f"{handover['phase2_seg_s']:.0f} s）")
    elif mode == "full_power":
        strategy = ("策略：当前温度 >45 ℃ 且剩余时间不足一个调度段，整段满功率直通")
    else:
        strategy = (f"策略：智能调控（离散档位 DP，{n_act} 档 × {n_seg} 段 × {seg_len:.0f} s）")
    lines = [
        f"收到反馈 T={t_now:.2f} ℃（室温 {tenv:.1f} / 水温 {twater:.1f}）→ "
        f"目标 {t_target:.2f} ℃ / {horizon_s / 60.0:.1f} min",
        f"可行性：α={alpha:.3f}，需执行器稳态 ≤{tss_req:.2f} ℃；满功率下限 {tss_min:.2f} ℃ → "
        + (f"余量 {tss_req - tss_min:.2f} K，可达"
           if feasible else f"差 {shortfall:.2f} K，不可达"),
        strategy,
    ]
    for i, seg in enumerate(plan):
        lines.append(_fmt_seg(i, seg))
    ok = final_t <= t_target + P.TOL_K
    saving = (1.0 - energy_wh / baseline_wh) * 100.0 if baseline_wh > 0 else float("nan")
    lines.append(f"结果：末温 {final_t:.2f} ℃（{'达标' if ok else '未达标'}）｜"
                 f"总耗 {energy_wh:.4f} Wh，较满功率 {baseline_wh:.3f} Wh 省 {saving:.1f}%｜"
                 f"决策耗时 {ms:.0f} ms（含恒定档位枚举）")
    if mode == "handover" and reference:
        lines.append("参考（若不分段、全程交给 DP，它会给出的解）：" + "，".join(
            f"{s['v_fan']:g}V/{s['i_tec']:g}A×{s['duration_s']:.0f}s" for s in reference))
    return lines


def get_plan(
    t_now: float,
    t_target: float,
    horizon_s: float,
    tenv: Optional[float] = None,
    twater: Optional[float] = None,
    t_max: Optional[float] = None,
) -> dict:
    """目标温度 + 时限 -> 可达性、能耗最优分段动作、预测轨迹。"""
    tenv = P.TENV_DEFAULT if tenv is None else float(tenv)
    twater = P.TWATER_DEFAULT if twater is None else float(twater)
    t_start = time.perf_counter()
    try:
        _validate(float(t_now), float(t_target), float(horizon_s), tenv, twater)
    except ValueError as e:
        # 被拒的请求同样留痕：现场最常见的问题就是「目标温度填得比当前温度还高」
        DL.write("reject", f"拒绝：{t_now:.1f} → {t_target:.1f} ℃ / {horizon_s / 60.0:.1f} min",
                 [f"收到反馈 T={t_now:.2f} ℃（室温 {tenv:.1f} / 水温 {twater:.1f}）→ "
                  f"目标 {t_target:.2f} ℃ / {horizon_s / 60.0:.1f} min",
                  f"参数不合法，未求解：{e}"],
                 extra={"t_now": t_now, "t_target": t_target, "horizon_s": horizon_s})
        raise

    p = ThermalParams()
    cfg = SolverConfig()
    available = _availability_light()
    enabled = bool(_read_state().get("enabled")) and available
    st = {"available": available, "enabled": enabled}

    # ---- ① 可行性（解析式，先于优化） ----------------------------------
    alpha = 1.0 - math.exp(-horizon_s / p.tau_s)
    tss_req = t_now - (t_now - t_target) / alpha
    tss_min = p.steady_state(Action(P.FULL_V, P.FULL_I), tenv, twater)
    shortfall = max(0.0, (tss_min - tss_req) * alpha)
    feasible = shortfall <= cfg.tol_K

    # ---- ② 模式：>45 ℃ 先满功率，降到 45 ℃ 后把「剩余时间」交给智能调控 ----
    # 旧行为是「整段满功率跑完时限」，50 ℃/30 min 会一路压到 33.4 ℃、耗 11.42 Wh，
    # 而目标只是 40 ℃ —— 规则只看安全、不看时限，等于白烧电。
    # 现在：满功率 → 到 45 ℃ 交班 → 用「剩余时间 + 当前目标」重解一次 DP。
    full_mode = t_now > P.T_FULL_ENTER
    handover = None
    if full_mode:
        a_full = Action(P.FULL_V, P.FULL_I)
        # 纯 DP 在全时限上的解只作参考（对比「先满功率」多花/少花多少电）
        r_ref = solve(t_now, t_target, horizon_s, tenv, twater, p, cfg, t_max=t_max)
        plan_ref = [s.as_dict(i) for i, s in enumerate(r_ref.plan)]
        t_hand = p.time_to(t_now, a_full, P.T_FULL_ENTER, tenv, twater)
        # 剩余不足 60 s 就没必要再解一次（DP 段长也不可能小于一个采样周期）
        if t_hand is None or t_hand >= horizon_s - 60.0:
            tend = p.advance(t_now, a_full, horizon_s, tenv, twater)
            plan = [{"index": 0, "v_fan": a_full.v_fan, "i_tec": a_full.i_tec,
                     "power_w": round(a_full.power, 3), "duration_s": round(horizon_s, 1),
                     "T_start": round(t_now, 3), "T_end": round(tend, 3),
                     "energy_wh": round(a_full.power * horizon_s / 3600.0, 5)}]
            final_t = tend
            energy_wh = a_full.power * horizon_s / 3600.0
            baseline_wh = energy_wh
            mode = "full_power"
        else:
            remain = horizon_s - t_hand
            r2 = solve(P.T_FULL_ENTER, t_target, remain, tenv, twater, p, cfg, t_max=t_max)
            tend1 = p.advance(t_now, a_full, t_hand, tenv, twater)
            e1 = a_full.power * t_hand / 3600.0
            plan = [{"index": 0, "v_fan": a_full.v_fan, "i_tec": a_full.i_tec,
                     "power_w": round(a_full.power, 3), "duration_s": round(t_hand, 1),
                     "T_start": round(t_now, 3), "T_end": round(tend1, 3),
                     "energy_wh": round(e1, 5)}]
            for i, s in enumerate(r2.plan):
                plan.append(s.as_dict(i + 1))
            final_t = r2.final_T
            energy_wh = e1 + r2.energy_wh
            baseline_wh = a_full.power * horizon_s / 3600.0
            mode = "handover"
            handover = {
                "threshold_C": P.T_FULL_ENTER,
                "t_s": round(t_hand, 1),
                "t_min": round(t_hand / 60.0, 2),
                "remaining_s": round(remain, 1),
                "remaining_min": round(remain / 60.0, 2),
                "phase1_energy_wh": round(e1, 4),
                "phase2_segments": len(r2.plan),
                "phase2_seg_s": round(remain / max(1, len(r2.plan)), 1),
            }
        reference = plan_ref
    else:
        r = solve(t_now, t_target, horizon_s, tenv, twater, p, cfg, t_max=t_max)
        plan = [s.as_dict(i) for i, s in enumerate(r.plan)]
        final_t = r.final_T
        energy_wh = r.energy_wh
        baseline_wh = r.baseline_wh
        reference = None
        mode = "smart"

    # ---- ③ 纯风扇够不够（决策的阈值型本质） -----------------------------
    enough, fan_reach, margin = fan_only_is_enough(t_now, t_target, horizon_s,
                                                   tenv, twater, p)
    alt = _constant_alternatives(t_now, t_target, horizon_s, tenv, twater, p)
    best_alt = next((a for a in alt if a["ok"]), None)

    # ---- ④ 各档恒定动作到达目标所需时间 ---------------------------------
    def _t_reach(a: Action):
        t = p.time_to(t_now, a, t_target, tenv, twater)
        return None if t is None else round(t / 60.0, 2)

    time_to = {
        "fan24": _t_reach(Action(P.FULL_V, 0.0)),
        "fan24_tec3": _t_reach(Action(P.FULL_V, P.FULL_I)),
        "fan20": _t_reach(Action(20.0, 0.0)),
    }

    # ---- ⑤ 说明与告警 ---------------------------------------------------
    notes: List[str] = []
    if mode == "handover" and handover:
        notes.append(
            f"当前温度 {t_now:.1f} ℃ 超过 {P.T_FULL_ENTER:g} ℃ 的安全阈值："
            f"前 {handover['t_min']:.2f} min 强制满功率（{P.FULL_V:g} V / {P.FULL_I:g} A），"
            f"降到 {P.T_FULL_ENTER:g} ℃ 后剩余 {handover['remaining_min']:.2f} min "
            f"由智能调控按目标 {t_target:.1f} ℃ 重解，不再全程满功率。")
    elif mode == "full_power":
        notes.append(
            f"当前温度 {t_now:.1f} ℃ 超过 {P.T_FULL_ENTER:g} ℃，但降回该阈值后剩余时间不足 60 s，"
            f"无法再排一个调度段，本次整段满功率（{P.FULL_V:g} V / {P.FULL_I:g} A）。")
    if not feasible:
        notes.append(f"目标在时限内不可达：还差 {shortfall:.2f} K，"
                     f"执行器满功率稳态只能到 {tss_min:.2f} ℃，需要稳态 ≤ {tss_req:.2f} ℃。")
    if feasible and not enough:
        notes.append("纯风扇 24 V 不足以在时限内达标，计划里需要用到制冷片。")
    if feasible and enough:
        notes.append("纯 24 V 风扇即可达标，最优解不应开制冷片"
                     f"（风扇 1.6 W 级，制冷片 2.25 A 即 11.8 W 级）。")
    if t_target < P.T_LO:
        notes.append(f"目标 {t_target:.1f} ℃ 低于模型实测支撑下限 {P.T_LO:g} ℃，"
                     "结论属于外推（一阶 RC 在低温段会低估所需冷量）。")
    if t_target > P.T_HI:
        notes.append(f"目标 {t_target:.1f} ℃ 高于模型定义域上限 {P.T_HI:g} ℃。")

    # ---- ⑥ 决策日志：把「收到什么 → 怎么判 → 下发什么」写成一条流水 ----------
    ms = (time.perf_counter() - t_start) * 1000.0
    n_seg = max(1, int(horizon_s // cfg.min_hold_s))
    seg_len = horizon_s / n_seg
    n_act = len(build_action_set(include_5a=cfg.allow_5a))
    lines = _decision_lines(
        t_now=t_now, t_target=t_target, horizon_s=horizon_s, tenv=tenv, twater=twater,
        alpha=alpha, tss_req=tss_req, tss_min=tss_min, feasible=feasible,
        shortfall=shortfall, mode=mode, plan=plan, final_t=final_t,
        energy_wh=energy_wh, baseline_wh=baseline_wh, ms=ms,
        n_seg=n_seg, seg_len=seg_len, n_act=n_act,
        handover=handover, reference=reference,
    )
    rec = DL.write("plan", f"{t_now:.1f} → {t_target:.1f} ℃ / {horizon_s / 60.0:.1f} min",
                   lines,
                   extra={"mode": mode,
                          "feasible": bool(feasible),
                          "energy_wh": round(energy_wh, 4),
                          "final_T": round(final_t, 3),
                          "elapsed_ms": round(ms, 1)})

    return {
        "ok": True,
        "request": {
            "t_now": round(t_now, 2), "t_target": round(t_target, 2),
            "horizon_s": round(horizon_s, 1), "horizon_min": round(horizon_s / 60.0, 2),
            "tenv": round(tenv, 2), "twater": round(twater, 2),
            "delta_T": round(t_now - t_target, 2),
        },
        "model": {"name": P.MODEL_NAME, "version": P.MODEL_VERSION,
                  "available": st["available"], "enabled": st["enabled"]},
        "mode": mode,
        "handover": handover,
        "feasible": bool(feasible),
        "shortfall_K": round(shortfall, 3),
        "feasibility": {
            "alpha": round(alpha, 4),
            "Tss_req": round(tss_req, 2),
            "Tss_min": round(tss_min, 2),
            "message": ("可达" if feasible else f"不可达，差 {shortfall:.2f} K"),
        },
        "plan": plan,
        "reference_plan": reference,
        "final_T": round(final_t, 3),
        "target_ok": bool(final_t <= t_target + cfg.tol_K),
        "energy_wh": round(energy_wh, 4),
        "baseline_wh": round(baseline_wh, 4),
        "saving_pct": round((1 - energy_wh / baseline_wh) * 100, 1) if baseline_wh > 0 else None,
        "traj": _traj_points(plan, t_now, p, tenv, twater),
        "fan_only": {"reach_T": round(fan_reach, 2), "enough": bool(enough),
                     "margin_K": round(margin, 2), "v_fan": P.FULL_V},
        "alternatives": alt,
        "best_constant": best_alt,
        "time_to_target_min": time_to,
        "notes": notes,
        "elapsed_ms": round(ms, 1),
        # 本次决策的日志记录（页面直接追加到「决策日志」面板，无需再拉一次接口）
        "log": rec,
    }
