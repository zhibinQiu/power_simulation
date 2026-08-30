"""手动调优提醒（optimizers 提醒生成/冷却/ack）回归测试（backend）。

覆盖「时序预测等模型关闭自动化控制后反复提醒、一直响铃」的修复：
1. 提醒阈值：仅有小幅波动（< REMINDER_GAIN）不生成提醒
2. 提醒冷却：显著提升生成提醒后，冷却期内再次显著提升不生成新提醒（id 不变）
3. 冷却解除：冷却期外 + 显著提升 → 生成新提醒
4. 关闭自动化控制：重置提醒基线（不立即提醒）
5. ack：清除提醒并把基线更新为当前最优

运行：
  cd backend && python -m pytest tests/test_reminder.py -v
（纯算法单测：不依赖真实网络 / Broker）
"""
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.models import ProcessModel, Unit  # noqa: E402
from app.optimizers import REMINDER_COOLDOWN, REMINDER_GAIN, get_optimizer  # noqa: E402
from app.realtime import DEVICE_HISTORY, DEVICE_META  # noqa: E402

# 含 kind='optim' 参数的最小流程模型（风量 / 热风温度 / 富氧率）
_MODEL = ProcessModel(
    units=[
        Unit(id="bf1", type="blast_furnace", name="高炉",
             params={"wind_rate": 500.0, "hot_blast_temp": 1100.0, "oxygen_enrich": 3.0}),
    ],
    flows=[],
)


@pytest.fixture(autouse=True)
def _clean_realtime():
    orig_h = dict(DEVICE_HISTORY)
    orig_m = dict(DEVICE_META)
    DEVICE_HISTORY.clear()
    DEVICE_META.clear()
    yield
    DEVICE_HISTORY.clear()
    DEVICE_HISTORY.update(orig_h)
    DEVICE_META.clear()
    DEVICE_META.update(orig_m)


@pytest.fixture()
def seq():
    """时序预测优化器（ai::seq）：手动模式、基线 100，_train_once 可被 monkeypatch 接管。"""
    o = get_optimizer("ai::seq")
    o.setup(_MODEL, {})
    o.running = True
    o.auto_control = False
    o.reminder = None
    o.best_fitness = 100.0
    o._last_reminded = 100.0
    o._next_remind_at = 0.0
    return o


def _set_train(monkeypatch, o, best):
    monkeypatch.setattr(o, "_train_once", lambda: (best, best))


# ------------------------- 阈值：小幅波动不提醒 -------------------------

def test_reminder_small_fluctuation_ignored(monkeypatch, seq):
    """0.5% 的波动小于 REMINDER_GAIN（1.0%）→ 不生成提醒（噪声免疫）。"""
    assert REMINDER_GAIN >= 1.0
    _set_train(monkeypatch, seq, 100.0 * (1 - 0.005))  # 0.5% 提升
    seq.step()
    assert seq.reminder is None


def test_reminder_real_gain_triggers(monkeypatch, seq):
    """显著提升（≥ REMINDER_GAIN）→ 生成提醒，id 唯一、记录提升百分比。"""
    _set_train(monkeypatch, seq, 98.0)  # 2% 提升
    seq.step()
    assert seq.reminder is not None
    assert seq.reminder["best_fitness"] == 98.0
    assert seq.reminder["improvement_pct"] == pytest.approx(2.0, abs=0.01)


# ------------------------- 冷却：反复提醒根因 -------------------------

def test_reminder_cooldown_blocks_repeat(monkeypatch, seq):
    """生成提醒后，冷却期内即使再次显著提升也不生成新提醒（reminder id 不变）。"""
    _set_train(monkeypatch, seq, 98.0)
    seq.step()
    rid = seq.reminder["id"]
    assert rid is not None
    # 冷却期内再降 3%（远超阈值）→ 不刷新提醒
    _set_train(monkeypatch, seq, 95.0)
    seq.step()
    assert seq.reminder["id"] == rid
    assert seq.reminder["best_fitness"] == 98.0  # 保持首次提醒内容


def test_reminder_repeat_after_cooldown(monkeypatch, seq):
    """冷却期结束 + 显著提升 → 生成新提醒（新 id），避免提醒永久停滞。"""
    _set_train(monkeypatch, seq, 98.0)
    seq.step()
    rid = seq.reminder["id"]
    seq._next_remind_at = time.time() - 1  # 模拟冷却已结束
    _set_train(monkeypatch, seq, 96.0)
    seq.step()
    assert seq.reminder["id"] != rid
    assert seq.reminder["best_fitness"] == 96.0


# ------------------------- 关闭自动化控制 / ack -------------------------

def test_disable_auto_control_resets_baseline(monkeypatch, seq):
    """关闭自动化控制：基线重置为当前最优，_next_remind_at 清零（不立即提醒）。"""
    seq.auto_control = True
    seq.reminder = {"id": "old", "best_fitness": 98.0}
    seq.set_settings({"auto_control": False})
    assert seq.auto_control is False
    assert seq._last_reminded == seq.best_fitness
    assert seq._next_remind_at == 0.0
    # 关闭后小幅波动不生成新提醒（旧提醒保留待 ack，id 不变）
    _set_train(monkeypatch, seq, seq.best_fitness * (1 - 0.005))
    seq.step()
    assert seq.reminder == {"id": "old", "best_fitness": 98.0}


def test_ack_clears_reminder_and_updates_baseline(monkeypatch, seq):
    """ack：清除提醒、清空待下发标记，并把基线更新为当前最优。"""
    _set_train(monkeypatch, seq, 98.0)
    seq.step()
    assert seq.reminder is not None
    seq.pending_auto_apply = True
    seq.ack()
    assert seq.reminder is None
    assert seq.pending_auto_apply is False
    assert seq._last_reminded == seq.best_fitness == 98.0


def test_state_exposes_cooldown_fields(seq):
    """state() 不因新增冷却字段而报错。"""
    st = seq.state()
    assert st["auto_control"] is False
    assert "reminder" in st
