"""三端配置一致性 + 统一下发链路回归测试。

设计约束（本文件锁定的就是这几条）：
  1. 设备只有一份定义（本地 backend/config/box_devices.json），云端 CRD 与盒子
     config.json 都由它派生 —— 不存在「本地设备」与「云端设备」两套配置各改各的；
  2. 一次下发覆盖整条链路：本地期望配置 → 云端 DeviceModel/Device → 盒子 config.json，
     且盒子写盘后在**运行期**立即生效（不依赖 systemctl 重启）；
  3. 「已下发 = 已生效」：盒子必须回报生效配置指纹，平台比对相等才算下发成功；
     历史上「写盘成功但重启没生效」正是磁盘与内存分叉、平台显示有设备而盒子没采集。

平台侧与盒子侧的指纹算法必须完全一致（_CONFIG_FP_KEYS 同序同字段），
本文件直接加载真实 box_mapper.py 做交叉验证，防止两边算法各自演化。

运行：cd backend && python -m pytest tests/test_box_config_consistency.py -v
"""
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app import mqtt_source  # noqa: E402
from app.box_console import cloud_ops as co  # noqa: E402
from app.box_console import devices as bd  # noqa: E402

MAPPER = BACKEND.parent / "platform" / "box-deploy" / "mapper" / "box_mapper.py"


# ---------------------------------------------------------------------------
# 加载真实 box_mapper.py（开发机无 grpc / api_pb2，用占位模块满足 import）
# ---------------------------------------------------------------------------
class _AutoModule(types.ModuleType):
    """任何未定义属性自动返回同名占位类（满足 pb/pb_grpc 的模块级引用）。"""

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        cls = type(name, (object,), {})
        setattr(self, name, cls)
        return cls


def _stub_modules():
    def mod(name, cls=_AutoModule, **attrs):
        m = cls(name)
        for k, v in attrs.items():
            setattr(m, k, v)
        sys.modules[name] = m
        return m

    if "grpc" not in sys.modules:
        grpc = mod("grpc", cls=types.ModuleType)
        grpc.insecure_channel = lambda *a, **k: None
        grpc.server = lambda *a, **k: None
        grpc.RpcError = type("RpcError", (Exception,), {})
        mod("api_pb2")
        mod("api_pb2_grpc")
        google = mod("google", cls=types.ModuleType)
        google.protobuf = mod("google.protobuf", cls=types.ModuleType)
        mod("google.protobuf.any_pb2")
        mod("google.protobuf.wrappers_pb2")


_CFG_DIR = Path(tempfile.mkdtemp(prefix="nengtan-mapper-cfg-"))
_CFG_FILE = _CFG_DIR / "config.json"
# 模块导入即执行 current_devices()（devices 不能为空，否则 SystemExit），先落一份最小配置
_CFG_FILE.write_text(json.dumps({
    "dmiSocket": "/tmp/nengtan-dmi.sock",
    "devices": [{
        "name": "probe", "protocol": "modbus-tcp",
        "tcp": {"host": "127.0.0.1", "port": 502},
        "points": [{"property": "v", "registerAddr": 0, "registerCount": 1,
                    "type": "int16", "scale": 1}],
    }],
}, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(scope="module")
def bm():
    """盒子 mapper 模块（真实源码，交叉验证指纹算法与运行期生效行为）。"""
    _stub_modules()
    os.environ["CONFIG_PATH"] = str(_CFG_FILE)
    spec = importlib.util.spec_from_file_location("box_mapper_consistency_under_test", str(MAPPER))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------------------------------------------------------------------------
# 设备定义（唯一来源）：本地 box_devices.json 的形态
# ---------------------------------------------------------------------------
def _modbus_dev(name, slave, node="nt001", register=0):
    return {
        "name": name, "namespace": "default", "model": name + "-model", "node": node,
        "protocol": "modbus-rtu", "collectCycle": 1000,
        "comm": {"commType": "serial", "slaveID": slave, "serialPort": "/dev/ttyS0",
                 "baudRate": 9600, "parity": "none", "dataBits": 8, "stopBits": 1},
        "properties": [{"name": "v", "type": "int", "register": register, "limit": 1,
                        "scale": 0.1}],
    }


def _lora_dev(name, slave, dev_eui="0011223344556677"):
    return {
        "name": name, "namespace": "default", "model": name + "-model", "node": "nt001",
        "protocol": "lora", "collectCycle": 30000,
        "lora": {"devEUI": dev_eui, "slaveId": slave,
                 "downlink": {"enabled": True, "mode": "poll", "fPort": 10, "timeout": 5}},
        "properties": [{"name": "v", "type": "int", "register": 0, "limit": 1, "scale": 0.1}],
    }


def _local(names=("weight-1", "power-1")):
    pool = {
        "weight-1": _modbus_dev("weight-1", 1),
        "power-1": _modbus_dev("power-1", 2),
        "temp-1": _lora_dev("temp-1", 2),
        "humid-1": _lora_dev("humid-1", 3),
    }
    return {"models": [], "devices": [pool[n] for n in names]}


@pytest.fixture
def local_only(monkeypatch):
    """只钉住本地期望配置，断开一切网络/缓存依赖。"""
    monkeypatch.setattr(bd, "_load_devices", lambda: _local())


# ---------------------------------------------------------------------------
# ① 指纹算法两端一致（平台期望配置 vs 盒子生效配置）
# ---------------------------------------------------------------------------
def test_fingerprint_identical_on_both_ends(bm, local_only):
    """同一份配置在平台与盒子算出的指纹必须相同，否则回执校验永远失败。"""
    mapper_devs = bd._expected_mapper_devs()
    assert bd.mapper_config_fingerprint(mapper_devs) == bm.config_fingerprint(mapper_devs)


def test_fingerprint_survives_json_roundtrip(bm, local_only):
    """指纹只依赖配置内容：经 JSON 序列化（MQTT 下发的真实路径）后不变。"""
    mapper_devs = bd._expected_mapper_devs()
    payload = json.loads(json.dumps(mapper_devs, ensure_ascii=False))
    assert bd.mapper_config_fingerprint(payload) == bm.config_fingerprint(mapper_devs)


def test_fingerprint_changes_when_config_changes(bm, local_only):
    """配置一变指纹必变 —— 否则平台上「改了点位」会被误判为「盒子已生效」。"""
    before = bd.mapper_config_fingerprint(bd._expected_mapper_devs())
    changed = [dict(d) for d in bd._expected_mapper_devs()]
    changed[0] = dict(changed[0], interval=99.0)
    assert bd.mapper_config_fingerprint(changed) != before


# ---------------------------------------------------------------------------
# ② 盒子侧：下发后写盘 + 运行期立即生效（内存与磁盘同源）
# ---------------------------------------------------------------------------
def test_apply_config_takes_effect_at_runtime(bm, tmp_path):
    """下发配置后：内存生效配置 == 磁盘 == 平台期望，且版本号递增（线程据此重建）。"""
    bm.CONFIG_PATH = str(tmp_path / "config.json")
    with open(bm.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"devices": [{
            "name": "old", "protocol": "modbus-tcp",
            "tcp": {"host": "127.0.0.1", "port": 502},
            "points": [{"property": "v", "registerAddr": 0, "registerCount": 1,
                        "type": "int16", "scale": 1}],
        }]}, f, ensure_ascii=False)
    bm.reload_runtime_config()
    ver_before = bm.config_version()

    expected = bd._expected_mapper_devs()
    ok, message, detail = bm._apply_config_cmd(
        {"cmd": "config", "devices": expected, "replace": True})
    assert ok is True, message
    # 运行期生效（不依赖重启）：内存设备清单与磁盘一致，指纹与平台期望一致
    assert [d["name"] for d in bm.current_devices()] == [d["name"] for d in expected]
    assert detail["fingerprint"] == bd.mapper_config_fingerprint(expected)
    assert bm.config_state()["fingerprint"] == bd.mapper_config_fingerprint(expected)
    assert bm.config_version() > ver_before
    on_disk = json.loads(Path(bm.CONFIG_PATH).read_text(encoding="utf-8"))
    assert [d["name"] for d in on_disk["devices"]] == [d["name"] for d in expected]


def test_disabled_device_stays_in_config_but_not_collected(bm, tmp_path):
    """enabled=false 设备留在配置里（指纹口径含 enabled）但不进采集线程列表。"""
    bm.CONFIG_PATH = str(tmp_path / "config.json")
    with open(bm.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"devices": [{
            "name": "seed", "protocol": "modbus-tcp",
            "tcp": {"host": "127.0.0.1", "port": 502},
            "points": [{"property": "v", "registerAddr": 0, "registerCount": 1,
                        "type": "int16", "scale": 1}],
        }]}, f, ensure_ascii=False)
    bm.reload_runtime_config()

    devs = [dict(d, enabled=False) for d in bd._expected_mapper_devs()]
    ok, message, _ = bm._apply_config_cmd({"cmd": "config", "devices": devs, "replace": True})
    assert ok is True, message
    assert bm.current_devices() == []                      # 不采集
    st = bm.config_state()
    assert st["disabled"] == [d["name"] for d in devs]      # 但配置里保留
    assert st["configDeviceCount"] == len(devs)
    assert st["fingerprint"] == bd.mapper_config_fingerprint(devs)


def test_config_state_reports_served_names_for_merged_dtu(bm, tmp_path, monkeypatch):
    """合并后的 DTU 条目必须把「实际服务的平台设备名」一并回报（否则平台误判盒子缺设备）。"""
    monkeypatch.setattr(bd, "_load_devices", lambda: _local(("temp-1", "humid-1")))
    bm.CONFIG_PATH = str(tmp_path / "config.json")
    with open(bm.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"devices": [{
            "name": "seed", "protocol": "modbus-tcp",
            "tcp": {"host": "127.0.0.1", "port": 502},
            "points": [{"property": "v", "registerAddr": 0, "registerCount": 1,
                        "type": "int16", "scale": 1}],
        }]}, f, ensure_ascii=False)
    bm.reload_runtime_config()
    expected = bd._expected_mapper_devs()
    assert len(expected) == 1 and len(expected[0]["lora"]["polls"]) == 2
    ok, message, _ = bm._apply_config_cmd({"cmd": "config", "devices": expected, "replace": True})
    assert ok is True, message
    st = bm.config_state()
    assert st["deviceNames"] == ["humid-1", "temp-1"]
    assert st["devices"][0]["served"] == ["temp-1", "humid-1"]
    assert st["deviceCount"] == 1        # 1 条采集条目
    assert st["configDeviceCount"] == 1


def test_config_get_returns_runtime_not_disk_snapshot(bm, tmp_path):
    """config_get 必须返回运行期生效配置：平台读到的就是盒子此刻真正在采集的东西。"""
    bm.CONFIG_PATH = str(tmp_path / "config.json")
    with open(bm.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"devices": [{
            "name": "seed", "protocol": "modbus-tcp",
            "tcp": {"host": "127.0.0.1", "port": 502},
            "points": [{"property": "v", "registerAddr": 0, "registerCount": 1,
                        "type": "int16", "scale": 1}],
        }]}, f, ensure_ascii=False)
    bm.reload_runtime_config()
    expected = bd._expected_mapper_devs()
    bm._apply_config_cmd({"cmd": "config", "devices": expected, "replace": True})
    # 磁盘被外部改回旧内容：运行期配置不应跟着变（避免「文件变了但采集没变」的假象）
    with open(bm.CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump({"devices": [{"name": "stale", "protocol": "modbus-tcp",
                                "tcp": {"host": "127.0.0.1", "port": 502},
                                "points": []}]}, f, ensure_ascii=False)
    assert [d["name"] for d in bm.current_config()["devices"]] == \
        [d["name"] for d in expected]


# ---------------------------------------------------------------------------
# ③ 平台侧：统一下发（本地 → 云端 → 盒子）与三端一致性体检
# ---------------------------------------------------------------------------
def test_push_payload_carries_expected_fingerprint(monkeypatch, local_only):
    """下发载荷必须带「期望指纹」并等回执：没有指纹就无法证明盒子按新配置在跑。"""
    sent = {}

    def fake_publish(topic, payload):
        sent["topic"], sent["payload"] = topic, payload
        return {"ok": True}

    waited = {}

    def fake_wait(box, fingerprint, timeout=8.0):
        waited.update(box=box, fingerprint=fingerprint, timeout=timeout)
        return {"ok": True, "fingerprint": fingerprint, "state": {"version": 3}}

    monkeypatch.setattr(mqtt_source, "publish", fake_publish)
    monkeypatch.setattr(mqtt_source, "wait_box_config", fake_wait)

    res = bd.push_devices_to_box(replace=True, wait_ack=True)
    assert res["ok"] is True
    assert sent["topic"] == "cmd/nt001/config"           # 盒子标识取自设备 node
    assert sent["payload"]["replace"] is True
    exp_fp = bd.mapper_config_fingerprint(bd._expected_mapper_devs())
    assert sent["payload"]["fingerprint"] == exp_fp
    assert waited == {"box": "nt001", "fingerprint": exp_fp, "timeout": 8.0}
    assert res["applied"] is True                        # 拿到回执才算已生效


def test_push_without_ack_reports_not_applied(monkeypatch, local_only):
    """盒子没回执（离线 / mapper 未升级）时不得谎报生效。"""
    monkeypatch.setattr(mqtt_source, "publish", lambda topic, payload: {"ok": True})
    monkeypatch.setattr(mqtt_source, "wait_box_config",
                        lambda box, fp, timeout=8.0: {"ok": False, "state": {},
                                                      "error": "未在 8.0s 内收到回执"})
    res = bd.push_devices_to_box(replace=True, wait_ack=True)
    assert res["ok"] is True and res["applied"] is False
    assert "回执" in res["hint"]


def _crds(*names, ok=True):
    return {"ok": ok, "error": "" if ok else "云端 agent 暂无缓存", "models": [],
            "devices": [{"name": n} for n in names]}


def test_consistency_detects_box_drift(monkeypatch, local_only):
    """盒子少了设备 → 一致性体检必须指出来（配置漂移可见）。"""
    monkeypatch.setattr(bd.cloud_agent, "crds", lambda force=False: _crds())
    monkeypatch.setattr(mqtt_source, "box_config_state", lambda box: {})
    st = bd.consistency("nt001")
    assert st["aligned"] is False
    assert st["missing_in_box"] == ["power-1", "weight-1"]
    assert st["missing_in_cloud"] == ["power-1", "weight-1"]
    assert st["fingerprint"]["match"] is False


def test_consistency_cloud_unreadable_is_unknown_not_missing(monkeypatch, local_only):
    """云端读不到时是「未知」而不是「云端缺 N 台」—— 不能把问题指到错误的方向。"""
    monkeypatch.setattr(bd.cloud_agent, "crds", lambda force=False: _crds(ok=False))
    monkeypatch.setattr(mqtt_source, "box_config_state", lambda box: {})
    st = bd.consistency("nt001")
    assert st["cloud_state"]["known"] is False
    assert st["missing_in_cloud"] == [] and st["extra_in_cloud"] == []
    assert st["aligned"] is False
    assert "云端 CRD 暂不可读" in st["note"]


def test_consistency_aligned_when_three_ends_match(monkeypatch, local_only):
    """三端同名 + 盒子指纹一致 + 回执新鲜 → 判定已对齐。"""
    import time
    expected = bd._expected_mapper_devs()
    fp = bd.mapper_config_fingerprint(expected)
    names = [d["name"] for d in expected]
    monkeypatch.setattr(bd.cloud_agent, "crds", lambda force=False: _crds(*names))
    monkeypatch.setattr(mqtt_source, "box_config_state", lambda box: {
        "fingerprint": fp, "version": 7, "last_seen": time.time(),
        "deviceNames": names, "devices": [{"name": n} for n in names],
    })
    st = bd.consistency("nt001")
    assert st["aligned"] is True, st
    assert st["fingerprint"]["match"] is True
    assert st["box_state"]["fresh"] is True
    assert st["note"] == ""


def test_consistency_uses_served_names_for_merged_dtu(monkeypatch, local_only):
    """多从站 DTU：盒子一条配置条目服务多台平台设备，不得因「条目名不同」误报缺失。"""
    import time
    monkeypatch.setattr(bd, "_load_devices", lambda: _local(("temp-1", "humid-1")))
    expected = bd._expected_mapper_devs()
    fp = bd.mapper_config_fingerprint(expected)
    # 两台传感器在同一个 devEUI 上被合并成 1 条配置条目，条目名只取第一台
    assert len(expected) == 1
    monkeypatch.setattr(bd.cloud_agent, "crds", lambda force=False: _crds("temp-1", "humid-1"))
    monkeypatch.setattr(mqtt_source, "box_config_state", lambda box: {
        "fingerprint": fp, "last_seen": time.time(),
        "deviceNames": ["temp-1", "humid-1"],
        "devices": [{"name": "temp-1"}],
    })
    st = bd.consistency("nt001")
    assert st["local"] == ["humid-1", "temp-1"]
    assert st["box_devices"] == ["humid-1", "temp-1"]
    assert st["missing_in_box"] == [] and st["aligned"] is True


def test_consistency_flags_stale_box_report(monkeypatch, local_only):
    """盒子回执过旧（>600s）同样算漂移：现场可能已被手工改过或进程没重启。"""
    import time
    expected = bd._expected_mapper_devs()
    fp = bd.mapper_config_fingerprint(expected)
    names = [d["name"] for d in expected]
    monkeypatch.setattr(bd.cloud_agent, "crds", lambda force=False: _crds(*names))
    monkeypatch.setattr(mqtt_source, "box_config_state", lambda box: {
        "fingerprint": fp, "last_seen": time.time() - 3600,
        "deviceNames": names, "devices": [{"name": n} for n in names],
    })
    st = bd.consistency("nt001")
    assert st["aligned"] is False
    assert st["box_state"]["fresh"] is False
    assert st["fingerprint"]["match"] is True     # 指纹对得上，但回执不新鲜
    assert "回执已过期" in st["note"]


def test_deploy_derives_both_ends_from_one_config(monkeypatch, local_only):
    """一键对齐：云端与盒子两条腿的同源性 —— 都从本地那份设备定义派生。"""
    calls = {}

    def fake_cloud(**kwargs):
        calls["cloud"] = kwargs or {}
        return {"ok": True, "applied": ["m"]}

    def fake_push(box="", names=None, replace=False, dry_run=False,
                  wait_ack=False, ack_timeout=8.0):
        calls["push"] = {"box": box, "names": names, "replace": replace, "wait_ack": wait_ack}
        # 盒子收到的内容 = 与一致性校验同一份产物（唯一转换路径）
        calls["push_fp"] = bd.mapper_config_fingerprint(bd._expected_mapper_devs(names))
        return {"ok": True, "applied": True}

    monkeypatch.setattr(bd, "apply_devices_to_cloud", fake_cloud)
    monkeypatch.setattr(bd, "push_devices_to_box", fake_push)
    monkeypatch.setattr(bd, "consistency", lambda box="": {"ok": True, "aligned": True, "note": ""})
    waited = {}

    def fake_wait_cloud(names, timeout=6.0):
        waited.update(names=names, timeout=timeout)
        return True

    monkeypatch.setattr(bd, "_wait_cloud_devices", fake_wait_cloud)

    res = bd.deploy_devices("nt001")
    # 云端腿也要等收敛：apply 成功 ≠ 平台立刻从 CRD 缓存里看到
    assert waited["names"] == ["weight-1", "power-1"]
    assert res["steps"]["cloud"]["converged"] is True
    assert res["ok"] is True
    assert calls["push"] == {"box": "nt001", "names": None, "replace": True, "wait_ack": True}
    assert calls["push_fp"] == bd.mapper_config_fingerprint(bd._expected_mapper_devs())
    assert res["fingerprint"] == calls["push_fp"]
    assert res["note"] == "三端已对齐"


def test_partial_push_with_replace_is_rejected(local_only):
    """整包替换 + 部分设备 = 把盒子其余设备清空，必须直接拒绝而不是照做。"""
    with pytest.raises(ValueError) as ei:
        bd.push_devices_to_box(box="nt001", names=["weight-1"], replace=True)
    assert "部分设备" in str(ei.value)


def test_deploy_has_no_partial_mode(local_only):
    """统一下发没有「只下发某几台」的口径：签名里就不该有这个开关。"""
    import inspect
    sig = inspect.signature(bd.deploy_devices)
    assert "names" not in sig.parameters


def test_wait_cloud_devices_reads_cache_only(monkeypatch):
    """云端收敛等待只读本地缓存（force=False）：不能为了等回执而对 agent 狂发 HTTP。"""
    seen = []

    def fake_crds(force=False):
        seen.append(force)
        return {"ok": True, "devices": [{"name": "a"}]}

    monkeypatch.setattr(bd.cloud_agent, "crds", fake_crds)
    assert bd._wait_cloud_devices(["a"], timeout=0.5) is True
    assert bd._wait_cloud_devices(["a", "b"], timeout=0.6) is False
    assert set(seen) == {False}


def test_wait_cloud_devices_tolerates_unreachable_cloud(monkeypatch):
    """云端不可读时不得抛异常（一致性报告会说明原因），等不到就返回 False。"""
    monkeypatch.setattr(bd.cloud_agent, "crds", lambda force=False: {"ok": False,
                                                                    "error": "无缓存"})
    assert bd._wait_cloud_devices(["a"], timeout=0.5) is False
    assert bd._wait_cloud_devices([], timeout=0.5) is True   # 无期望设备 → 无需等待


def test_deploy_fails_when_box_push_fails(monkeypatch, local_only):
    """盒子没推成功就不能算成功（云端成功只算一半）。"""
    monkeypatch.setattr(bd, "apply_devices_to_cloud", lambda **kw: {"ok": True})
    monkeypatch.setattr(bd, "_wait_cloud_devices", lambda names, timeout=6.0: True)
    monkeypatch.setattr(bd, "push_devices_to_box",
                        lambda **kw: {"ok": False, "error": "盒子离线"})
    monkeypatch.setattr(bd, "consistency", lambda box="": {"ok": True, "aligned": False,
                                                           "note": "存在配置漂移"})
    res = bd.deploy_devices("nt001")
    assert res["ok"] is False
    assert res["steps"]["box"]["error"] == "盒子离线"


def test_auto_push_waits_for_ack(monkeypatch, local_only):
    """保存即下发：自动推送同样要等生效回执，且回执缺失时如实提示。"""
    seen = {}

    def fake_push(**kwargs):
        seen.update(kwargs)
        return {"ok": True, "applied": False}

    monkeypatch.setattr(bd, "push_devices_to_box", fake_push)
    res = bd.auto_push_box_after_apply(affected_devs=[_modbus_dev("weight-1", 1)])
    assert seen.get("wait_ack") is True and seen.get("replace") is True
    assert seen.get("box") == "nt001"
    assert res["ok"] is True and res["skipped"] is False
    assert "未收到盒子生效回执" in res["note"]


def test_no_box_associated_is_reported_not_faked(monkeypatch):
    """设备没挂到真实盒子（ext-* 外部数据源 / 占位节点）时如实告知未推送。"""
    ext = dict(_lora_dev("ext-sim-1", 0), node="ext-steel")
    monkeypatch.setattr(bd, "_load_devices", lambda: {"models": [], "devices": [ext]})
    res = bd.auto_push_box_after_apply(affected_devs=[ext])
    assert res["ok"] is False and res["skipped"] is True
    assert "未关联一体机盒子" in res["note"]


# ---------------------------------------------------------------------------
# ⑦ 云端 CRD 由「唯一定义」现算：本地改了 → 云端必然跟着改
#
# 现场缺陷：本地配置里 flow_meter 有点位、设备与模型的 yaml 字段却是空串（历史副本），
# 下发时读这份副本 → 设备被静默跳过 → 「云端怎么点都缺这台设备」。
# 副本只是派生产物：可能为空、可能过期，绝不能让它决定下发的完整性。
# ---------------------------------------------------------------------------
from app.domain.box import device_yaml as yd  # noqa: E402


def _local_with_models(names=("weight-1", "power-1")):
    """本地定义：设备 + 各自的模型（点位一致，与真实保存路径的产物同形）。"""
    data = _local(names)
    data["models"] = [
        {"name": d["name"] + "-model", "namespace": "default", "protocol": d["protocol"],
         "properties": [dict(p) for p in d["properties"]]}
        for d in data["devices"]
    ]
    return data


def test_refresh_fills_empty_yaml_copy():
    """副本为空（历史数据）→ 现算补全，而不是让这台设备从云端消失。"""
    data = _local_with_models()
    for m in data["models"]:
        m["yaml"] = ""
    for d in data["devices"]:
        d["yaml"] = ""
    res = yd.refresh_device_yaml(data)
    assert res["failed"] == []
    assert sorted(res["changed"]) == ["device/power-1", "device/weight-1",
                                      "model/power-1-model", "model/weight-1-model"]
    for d in data["devices"]:
        assert "kind: Device" in d["yaml"] and d["name"] in d["yaml"]
    for m in data["models"]:
        assert "kind: DeviceModel" in m["yaml"] and m["name"] in m["yaml"]


def test_refresh_recomputes_stale_yaml_copy():
    """副本过期（模型点位改过、副本没跟上）→ 用定义覆盖，而不是继续下发旧点位。"""
    data = _local_with_models()
    yd.refresh_device_yaml(data)                       # 先让副本都到位
    data["devices"][0]["yaml"] = "apiVersion: v1\nkind: Device\nmetadata:\n  name: 过期副本\n"
    res = yd.refresh_device_yaml(data)
    assert "过期副本" not in data["devices"][0]["yaml"]
    assert 'name: "weight-1"' in data["devices"][0]["yaml"]
    # 只重写真正过期的那台（没差异的设备不该被标记，否则每次下发都全量重写文件）
    assert res["changed"] == ["device/weight-1"]


def test_refresh_is_idempotent():
    """连算两次第二次无变化 —— 否则每次下发都无谓重写配置文件。"""
    data = _local_with_models()
    yd.refresh_device_yaml(data)
    assert yd.refresh_device_yaml(data)["changed"] == []


def test_dispatch_and_save_paths_derive_identical_yaml():
    """下发前的现算 == 保存设备时的生成：两条路共用一套入参拼装，不会分叉。"""
    data = _local_with_models()
    for d in data["devices"]:
        d.pop("yaml", None)
    yd.refresh_device_yaml(data)
    models = {m["name"]: m for m in data["models"]}
    for d in data["devices"]:
        props = models[d["model"]]["properties"]
        again = yd.generate_device_yaml(yd.device_yaml_sample(d, properties=props))["device"]
        assert d["yaml"] == again
        # 保存路径（模型点位变更后重刷引用设备）走的是同一个拼装函数
        copy_data = {"devices": [dict(d, yaml="旧内容")]}
        changed = bd._regenerate_devices_for_model(copy_data, d["model"], props, d["protocol"])
        assert changed == [d["name"]]
        assert copy_data["devices"][0]["yaml"] == d["yaml"]


def test_apply_to_cloud_never_silently_skips_device(monkeypatch):
    """副本为空也必须下发（本地定义里有它，云端就必须有它），且下发内容含真实点位。"""
    data = _local_with_models()
    for m in data["models"]:
        m["yaml"] = ""
    for d in data["devices"]:
        d["yaml"] = ""
    sent = {}

    def fake_apply(payload, *a, **k):
        sent["payload"] = payload
        return {"ok": True, "rc": 0, "stdout": "device created", "stderr": ""}

    monkeypatch.setattr(co, "_load_devices", lambda: data)
    monkeypatch.setattr(co, "_save_devices", lambda d: None)
    monkeypatch.setattr(co.cloud_agent, "apply", fake_apply)

    res = co.apply_devices_to_cloud()
    assert res["ok"] is True
    assert res["missing"] == []
    assert sorted(res["applied"]) == ["power-1-model + power-1", "weight-1-model + weight-1"]
    for name in ("weight-1", "power-1"):
        assert "kind: Device\n" in sent["payload"]
        assert 'name: "%s"' % name in sent["payload"]          # 设备 CRD
        assert "kind: DeviceModel" in sent["payload"]
        assert 'name: "%s-model"' % name in sent["payload"]    # 模型 CRD
    # 点位确实进了下发内容（不是只有空壳文档）
    assert "register: HoldingRegister" in sent["payload"]
    # 副本已按定义补全并落盘（下次不再重算）
    assert all(d["yaml"] for d in data["devices"])
    assert data["devices"][0]["yaml"] == yd.generate_device_yaml(
        yd.device_yaml_sample(data["devices"][0],
                              properties=data["models"][0]["properties"]))["device"]


def test_apply_to_cloud_reports_render_failure_not_silence(monkeypatch):
    """渲染确实失败时要报出来（缺失清单带原因），而不是少下发一台还不吭声。"""
    data = _local_with_models()
    monkeypatch.setattr(co, "_load_devices", lambda: data)
    monkeypatch.setattr(co, "_save_devices", lambda d: None)
    monkeypatch.setattr(co.cloud_agent, "apply",
                        lambda payload, *a, **k: {"ok": True, "rc": 0})

    def boom(p):
        raise ValueError("协议渲染器故障")

    monkeypatch.setattr(yd, "generate_device_yaml", boom)
    res = co.apply_devices_to_cloud()
    assert res["ok"] is False
    assert "协议渲染器故障" in res["error"]
    assert "weight-1" in res["error"] and "power-1" in res["error"]


# ---------------------------------------------------------------------------
# ⑦ 规范化改名后云端旧名对象必须清掉（否则云端永远多一台，对齐不了）
# ---------------------------------------------------------------------------
def _deploy_stubs(monkeypatch, renamed):
    """桩住两条腿与体检，只观测「改名清理」这一段行为。"""
    calls = {"deleted": []}

    monkeypatch.setattr(bd, "_normalize_definition",
                        lambda: {"renamed": renamed, "error": ""})
    monkeypatch.setattr(bd, "apply_devices_to_cloud", lambda **kw: {"ok": True})
    monkeypatch.setattr(bd, "_wait_cloud_devices", lambda names, timeout=6.0: True)
    monkeypatch.setattr(bd, "push_devices_to_box", lambda **kw: {"ok": True})
    monkeypatch.setattr(bd, "consistency",
                        lambda box="": {"ok": True, "aligned": True, "note": ""})
    monkeypatch.setattr(bd, "cloud_config", lambda: {"namespace": "default"})

    def fake_delete(kind, name, ns):
        calls["deleted"].append((kind, name, ns))
        return {"ok": True, "deleted": [kind]}

    monkeypatch.setattr(bd, "_cloud_delete_crds", fake_delete)
    return calls


def test_renamed_invalid_old_name_is_not_reported_as_failed(monkeypatch, local_only):
    """改名后旧名不合法 → 云端压根建不出这个对象，无需删除，更不能报成「未清理」吓人。

    真实场景（flow_meter→flow-meter）走的正是这条：规范化只会把「不合法」改成「合法」，
    所以旧名永远进不了 kubectl，云端不会有残留对象，一致性报告也不会出现 extra_in_cloud。
    """
    renamed = {"models": {}, "devices": {"flow_meter": "flow-meter"}}
    calls = _deploy_stubs(monkeypatch, renamed)
    res = bd.deploy_devices("nt001")
    assert calls["deleted"] == []                          # 不向云端发非法名的删除请求
    assert res["steps"]["cloud_pruned"]["skipped"] == ["device flow_meter"]
    assert res["steps"]["cloud_pruned"]["failed"] == []
    assert "未清理" not in res["note"]
    assert "flow_meter→flow-meter" in res["note"]           # 改名本身要如实告知


def test_prune_deletes_old_valid_name_by_its_own_kind(monkeypatch, local_only):
    """旧名合法时确实去删（防御未来规则放宽），且按类型删：设备与模型同名不能 both。"""
    renamed = {"models": {"old-name": "new-model"},
               "devices": {"old-name": "new-name"}}
    calls = _deploy_stubs(monkeypatch, renamed)
    res = bd.deploy_devices("nt001")
    assert calls["deleted"] == [("device", "old-name", "default"),
                                ("model", "old-name", "default")]
    assert all(k in ("device", "model") for k, _, _ in calls["deleted"])   # 绝不出现 both
    assert res["steps"]["cloud_pruned"]["removed"] == ["device old-name", "model old-name"]


def test_prune_failure_is_reported_not_silent(monkeypatch, local_only):
    """云端删不掉（不可达）时要如实说清要手工处理哪些，不能悄悄留下漂移。"""
    renamed = {"models": {}, "devices": {"legacy-dev": "legacy-dev-2"}}
    _deploy_stubs(monkeypatch, renamed)
    monkeypatch.setattr(bd, "_cloud_delete_crds",
                        lambda kind, name, ns: {"ok": False, "error": "agent 不可达"})
    res = bd.deploy_devices("nt001")
    assert res["steps"]["cloud_pruned"]["failed"] == ["device legacy-dev"]
    assert "未清理" in res["note"]


def test_no_rename_never_touches_cloud_objects(monkeypatch, local_only):
    """没改名就不该有任何删除动作（下发是幂等加/改，不是删除）。"""
    calls = _deploy_stubs(monkeypatch, {"models": {}, "devices": {}})
    res = bd.deploy_devices("nt001")
    assert calls["deleted"] == []
    assert "cloud_pruned" not in res["steps"]


def test_deploy_prunes_crd_only_orphans(monkeypatch, local_only):
    """云端有、本地定义里没有的 CRD-only 对象（历史遗留 / 云端手工 kubectl 建的）必须清掉。

    设备定义只有本地一份：留着孤儿就是「平台列表里没有、现场却可能在采数」，
    一致性报告的 extra_in_cloud 也永远消不掉。
    """
    calls = _deploy_stubs(monkeypatch, {"models": {}, "devices": {}})
    monkeypatch.setattr(bd.cloud_agent, "crds", lambda: {
        "ok": True,
        "devices": [{"name": "weight-1"}, {"name": "power-1"},
                    {"name": "temp-1"}, {"name": "humid-1"},
                    {"name": "ghost-dev"}],          # 本地定义里没有的孤儿
        "models": [{"name": "ghost-model"}],
    })
    res = bd.deploy_devices("nt001")
    # 云端多出的全部清掉（本地定义默认只有 weight-1 / power-1，其余连同 ghost 都是孤儿）
    assert ("device", "ghost-dev", "default") in calls["deleted"]
    assert ("model", "ghost-model", "default") in calls["deleted"]
    assert ("device", "temp-1", "default") in calls["deleted"]
    assert ("device", "humid-1", "default") in calls["deleted"]
    # 本地定义里的对象一个都不许动
    assert not [c for c in calls["deleted"] if c[1] in ("weight-1", "power-1")]
    assert "ghost-dev" in "、".join(res["steps"]["cloud_pruned"]["removed"])


def test_deploy_keeps_name_bound_via_cloud_device(monkeypatch):
    """改名后云端 CRD 仍是旧名（设备靠 cloudDevice 绑定）时，不能把它当孤儿删掉。"""
    data = {"models": [], "devices": [{"name": "new-name", "cloudDevice": "old-crd-name",
                                       "node": "nt001"}]}
    monkeypatch.setattr(bd, "_load_devices", lambda: data)
    monkeypatch.setattr(bd, "_expected_mapper_devs", lambda: list(data["devices"]))
    calls = _deploy_stubs(monkeypatch, {"models": {}, "devices": {}})
    monkeypatch.setattr(bd.cloud_agent, "crds", lambda: {
        "ok": True, "devices": [{"name": "old-crd-name"}], "models": []})
    res = bd.deploy_devices("nt001")
    assert calls["deleted"] == []
    assert "cloud_pruned" not in res["steps"]
