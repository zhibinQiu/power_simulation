"""AI 群控「条件」内的 AND / OR（条件的内部组件，不再是独立模块）。

与前端 utils/ruleFlow.js 同源：
  · 一条 IF 分支 = 一组比较（b.conds），相邻两条之间由 join 连接（join='or' → 或者，其余 → 并且）；
  · AND 优先于 OR 归约：「x<20 或 x≥25 且 x<50」= x<20 OR (x≥25 AND x<50)；
  · 任一条件取不到有效读数 / 阈值不合法 → 整条分支不命中；
  · 旧编排的 AND / OR 逻辑门（kind='gate'）在服务端仍可执行（前端载入时会升级，服务端兼容未升级的存档）。
"""
import pytest

from app.domain.scene import agc_runner


def _graph(branch):
    return {
        "nodes": [
            {"id": "st", "kind": "start", "x": 0, "y": 0},
            {"id": "sen", "kind": "sen", "devId": "S1", "label": "x", "x": 200, "y": 0},
            {"id": "if1", "kind": "if", "x": 400, "y": 0,
             "branches": [branch, {"id": "b2", "type": "else"}]},
            {"id": "ad1", "kind": "adj", "devId": "A1", "label": "pump", "value": 24, "x": 700, "y": 0},
            {"id": "en", "kind": "end", "x": 900, "y": 0},
        ],
        "edges": [
            {"id": "e1", "from": "st", "port": "out", "to": "sen"},
            {"id": "e2", "from": "sen", "port": "out", "to": "if1"},
            {"id": "e3", "from": "if1", "port": "b1", "to": "ad1"},
            {"id": "e4", "from": "ad1", "port": "out", "to": "en"},
        ],
    }


def _hit(g, v):
    r = agc_runner._eval_graph(g, lambda dev: v if dev == "S1" else None, {})
    return any(a.get("write") for a in r.get("acts") or [])


BAND = {
    "id": "b1", "type": "if",
    "conds": [
        {"id": "c1", "src": "sen", "op": ">=", "val": 25, "join": "and"},
        {"id": "c2", "src": "sen", "op": "<", "val": 50, "join": "and"},
    ],
}


@pytest.mark.parametrize("value,expect", [(25, True), (30, True), (49.9, True), (24.9, False), (50, False)])
def test_and_range(value, expect):
    assert _hit(_graph(BAND), value) is expect


def test_and_precedes_or():
    # x < 20 或 (25 ≤ x < 50)
    branch = {
        "id": "b1", "type": "if",
        "conds": [
            {"id": "c1", "src": "sen", "op": "<", "val": 20, "join": "and"},
            {"id": "c2", "src": "sen", "op": ">=", "val": 25, "join": "or"},
            {"id": "c3", "src": "sen", "op": "<", "val": 50, "join": "and"},
        ],
    }
    assert _hit(_graph(branch), 10) is True     # x < 20
    assert _hit(_graph(branch), 30) is True     # 25 ≤ x < 50
    assert _hit(_graph(branch), 60) is False    # 两边都不成立
    assert _hit(_graph(branch), 22) is False    # OR 的前后两「组」都不成立


def test_legacy_single_condition_still_works():
    branch = {"id": "b1", "type": "if", "src": "sen", "op": ">=", "val": 50}
    assert _hit(_graph(branch), 55) is True
    assert _hit(_graph(branch), 40) is False


def test_unusable_condition_falls_to_else():
    # ① 指向不存在的设备 → 该条回落的上游也没有读数 → 整条分支不命中
    g = {
        "nodes": [
            {"id": "st", "kind": "start", "x": 0, "y": 0},
            {"id": "if1", "kind": "if", "x": 400, "y": 0,
             "branches": [{"id": "b1", "type": "if",
                           "conds": [{"id": "c1", "src": "ghost", "op": ">=", "val": 0}]},
                          {"id": "b2", "type": "else"}]},
            {"id": "en", "kind": "end", "x": 900, "y": 0},
        ],
        "edges": [
            {"id": "e1", "from": "st", "port": "out", "to": "if1"},
            {"id": "e2", "from": "if1", "port": "b1", "to": "en"},
        ],
    }
    r = agc_runner._eval_graph(g, lambda dev: None, {})
    assert not any(a.get("write") for a in r.get("acts") or [])
    # ② 阈值未填（非数值）→ 同样不命中
    assert _hit(_graph({"id": "b1", "type": "if",
                        "conds": [{"id": "c1", "src": "sen", "op": ">=", "val": None}]}), 30) is False


def test_legacy_gate_still_evaluated():
    # 前端载入时会把 gate 升级成 if；服务端对尚未升级的旧存档保持可执行
    g = _graph(None)
    g["nodes"][2] = {
        "id": "g1", "kind": "gate", "op": "and", "x": 400, "y": 0,
        "conds": [{"id": "c1", "src": "sen", "op": ">=", "val": 25},
                  {"id": "c2", "src": "sen", "op": "<", "val": 50}],
    }
    g["edges"][1] = {"id": "e2", "from": "sen", "port": "out", "to": "g1"}
    g["edges"][2] = {"id": "e3", "from": "g1", "port": "t", "to": "ad1"}
    assert _hit(g, 30) is True
    assert _hit(g, 60) is False
