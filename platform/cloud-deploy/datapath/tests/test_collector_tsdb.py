"""云端 collector 时序库写入回归测试（子表命名不变量）。

锁定的约束（正是现场踩过的坑）：
  超表子表名必须是「box/device/instance/property 四元组」的一一映射。
  历史实现把名字里的 `-` 折成 `_` 再拼子表名，`flow-meter` 与 `flow_meter` 于是共用
  一张子表；TDengine 对已存在的子表会忽略 USING 的 TAGS 子句，读数被静默写进旧 tag，
  设备改名后平台按新设备名查历史永远为空——数据一直在写却查不到，最难排查的一类故障。

运行：cd platform/cloud-deploy/datapath && python -m pytest tests -v
"""
import importlib.util
import re
import sys
from pathlib import Path

import pytest

DATAPATH = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(DATAPATH))


def _load_collector():
    """按文件路径加载 collector.py（同名模块可能与别的组件冲突，不走 import 语句）。"""
    spec = importlib.util.spec_from_file_location("nengtan_collector", DATAPATH / "collector.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def col():
    return _load_collector()


def test_subtable_name_is_injective_over_dash_and_underscore(col):
    """设备名 flow-meter 与 flow_meter 必须落到不同子表——折叠会串数据。"""
    a = col._subtable_name("nt001", "flow-meter", "flow-meter", "flow_rate")
    b = col._subtable_name("nt001", "flow_meter", "flow_meter", "flow_rate")
    assert a != b


def test_subtable_name_quoted_and_dash_preserved(col):
    """含中划线的名字用反引号引用且原样保留（TDengine 允许引用名含中划线）。"""
    name = col._subtable_name("nt001", "flow-meter", "flow-meter", "flow_total")
    assert name == "`t_nt001_flow-meter_flow-meter_flow_total`"
    assert name.startswith("`") and name.endswith("`")


def test_subtable_name_strips_backtick_and_newline(col):
    """主题来自 MQTT，不能把反引号/换行拼进 SQL 标识符（防注入）。"""
    name = col._subtable_name("nt0`01", "de\nvice", "inst`ance", "prop")
    assert name.count("`") == 2                    # 只有首尾两个引用符
    assert "\n" not in name and "de vice" not in name


def test_subtable_name_is_stable_for_same_tuple(col):
    """同一四元组多次调用结果一致，否则每批都会新建子表。"""
    args = ("nt001", "shuibeng-power", "shuibeng-power", "power")
    assert col._subtable_name(*args) == col._subtable_name(*args)


def test_ts_flush_inserts_into_quoted_subtable_with_matching_tags(col, monkeypatch):
    """落库语句：子表名与 TAGS 必须同源（同一次调用的四元组），tag 保留中划线。"""
    sent = []

    class _Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"code":0}'

    def fake_urlopen(req, timeout=None):
        sent.append(req.data.decode("utf-8"))
        return _Resp()

    monkeypatch.setattr(col, "TSDB_ENABLED", True)
    monkeypatch.setattr(col.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(col, "_TS_BUF", __import__("collections").deque())
    col._ts_record("data/nt001/flow-meter/flow-meter/flow_total", b'{"flow_total":2.44}')
    col._ts_flush()

    assert len(sent) == 1
    sql = sent[0]
    assert "INSERT INTO `t_nt001_flow-meter_flow-meter_flow_total` USING" in sql
    assert "TAGS('nt001','flow-meter','flow-meter','flow_total')" in sql
    assert re.search(r"VALUES \(\d+,2\.44\)", sql)   # 读数进了 VALUES（JSON 载荷按属性名取值）
