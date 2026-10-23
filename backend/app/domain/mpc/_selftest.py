# -*- coding: utf-8 -*-
"""迁移自测：平台后端 app/domain/mpc 与原始 temp_optimize_model 的结论逐项对比。

跑法：在 backend 目录下
    python <此脚本>
输出：打印对比表，末尾给出 PASS/FAIL。
"""
from __future__ import annotations

import json
import os
import sys

# backend/ 根目录：本文件位于 backend/app/domain/mpc/，上溯三层
BACKEND = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
sys.path.insert(0, BACKEND)

from app.domain.mpc import get_plan, get_status  # noqa: E402

OUT = []


def w(s=""):
    OUT.append(str(s))


def main():
    st = get_status()
    w("=" * 78)
    w("① 可用性自检（决定「能否启用」）")
    w("=" * 78)
    w(f"available={st['available']}  enabled={st['enabled']}")
    for c in st["checks"]:
        w(f"  [{'PASS' if c['ok'] else 'FAIL'}] {c['label']:<14} {c['detail']}")

    w()
    w("=" * 78)
    w("② 45 -> 39 ℃ / 12 min（应 16V→18V，0.1779 Wh，末温 39.04）")
    w("=" * 78)
    r = get_plan(45.0, 39.0, 720.0)
    for s in r["plan"]:
        w(f"  段{s['index']+1}: {s['v_fan']:g}V / {s['i_tec']:g}A  "
          f"{s['duration_s']:.0f}s  {s['T_start']:.2f} -> {s['T_end']:.2f} ℃  {s['power_w']:.3f} W")
    w(f"  末温 {r['final_T']:.2f}  电耗 {r['energy_wh']:.4f} Wh  "
      f"节省 {r['saving_pct']}%  可达={r['feasible']} 达标={r['target_ok']}")
    w(f"  纯风扇可达 {r['fan_only']['reach_T']:.2f} ℃（够={r['fan_only']['enough']}）")
    w(f"  恒档最优 {r['best_constant']}")
    w(f"  到 39 ℃ 用时：{r['time_to_target_min']}")
    for n in r["notes"]:
        w("  note: " + n)
    w(f"  轨迹点数 {len(r['traj'])}，末点 {r['traj'][-1]}")

    w()
    w("=" * 78)
    w("③ 45 -> 35 ℃ / 8 min（应不可达，差 ≈4.98 K）")
    w("=" * 78)
    r3 = get_plan(45.0, 35.0, 480.0)
    w(f"  feasible={r3['feasible']} shortfall={r3['shortfall_K']} "
      f"末温 {r3['final_T']:.2f} plan={[(s['v_fan'], s['i_tec']) for s in r3['plan']]}")
    for n in r3["notes"]:
        w("  note: " + n)

    w()
    w("=" * 78)
    w("④ 50 -> 40 ℃ / 30 min（>45 先满功率，降到 45 ℃ 后剩余时间交 DP）")
    w("=" * 78)
    r4 = get_plan(50.0, 40.0, 1800.0)
    w(f"  mode={r4['mode']}")
    w(f"  交班详情={r4['handover']}")
    for s in r4["plan"]:
        w(f"  段{s['index']+1}: {s['v_fan']:g}V / {s['i_tec']:g}A  "
          f"{s['duration_s']:.0f}s  {s['T_start']:.2f} -> {s['T_end']:.2f} ℃  {s['energy_wh']:.4f} Wh")
    w(f"  末温 {r4['final_T']:.2f}  总耗 {r4['energy_wh']:.4f} Wh  "
      f"满功率基线 {r4['baseline_wh']:.4f} Wh  节省 {r4['saving_pct']}%")
    w(f"  参考（全程 DP）：{[(s['v_fan'], s['i_tec'], round(s['duration_s'])) for s in (r4['reference_plan'] or [])]}")
    for n in r4["notes"]:
        w("  note: " + n)

    w()
    w("=" * 78)
    w("⑤ 参数非法应报中文错误")
    w("=" * 78)
    for args in [(45.0, 46.0, 600.0), (45.0, 39.0, 5.0), (45.0, 50.0, 600.0)]:
        try:
            get_plan(*args)
            w(f"  {args} -> 未报错（异常！）")
        except ValueError as e:
            w(f"  {args} -> {e}")

    txt = "\n".join(OUT)
    print(txt)
    fp = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_mpc_migration_selftest.txt")
    with open(fp, "w", encoding="utf-8") as f:
        f.write(txt)
    print(f"\n[已写入] {fp}")


if __name__ == "__main__":
    main()
