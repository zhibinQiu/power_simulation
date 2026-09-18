"""统一数据源接入（app/data_sources/）测试用例（backend）。

用户诉求：能碳一体机接入 / 外部数据源 都是「一种数据源接入」，平台把它们作为同一种
可管理对象（统一目录 config/data_sources.json + 统一启停 + 统一状态），全部汇入同一条
摄取管道；外部数据（含模拟数据）的采集执行方是**数据中间件**——平台登记即注册到
中间件，中间件采集并转换为标准 MQTT 发布到云端 Broker，平台按 box 前缀识别归属。

验证重点：
- ① 目录默认仅含 box（一体机）内置源，external 一律经中间件注册；
- ② 注册/修改/启停/删除 均同步到中间件，中间件失败时不落本地（状态一致）；
- ③ 摄取侧按 box 前缀识别归属 external，按条目 enabled 过滤、累计最近读数；
- ④ 模拟数据不是平台/中间件的内置能力：由独立服务 sim-source 生成后经 `mqtt`
  适配器接入（adapter 仅支持 mqtt，历史 sim 类型已移除）。

中间件用内存假实现（_FakeMiddleware）替换，测试不依赖真实中间件进程。
"""
import json
import os
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import data_sources, mqtt_source  # noqa: E402
from app import middleware_client  # noqa: E402
from app.data_sources import config as ds_config  # noqa: E402
from app.data_sources import external as ext_mod  # noqa: E402
from app.mqtt_source.ingest import _record_message  # noqa: E402

DS_PATH = ds_config.CONFIG_PATH


# ---------------------------------------------------------------------------
# 内存假中间件（替代真实 HTTP 管理 API）
# ---------------------------------------------------------------------------
class _FakeMiddleware:
    """中间件管理 API 的最小内存实现（含校验/启停/测试语义）。"""

    def __init__(self):
        self.sources = {}
        self.online = True
        self.running = set()      # 正在采集的 id

    def _fail(self, msg):
        raise middleware_client.MiddlewareError(msg)

    def status(self, force=False):
        if not self.online:
            return {"enabled": True, "online": False, "error": "无法连接中间件服务（模拟离线）",
                    "detail": {}, "sources": 0, "types": []}
        return {"enabled": True, "online": True, "error": "", "sources": len(self.sources),
                "types": ["mqtt"],
                "detail": {"broker": {"running": False, "mode": "external"},
                           "bridge": {"mode": "external"}}}

    def list_sources(self):
        if not self.online:
            self._fail("无法连接中间件服务（模拟离线）")
        return [dict(s) for s in self.sources.values()]

    def get_source(self, sid):
        if not self.online:
            return None
        s = self.sources.get(str(sid))
        return dict(s) if s else None

    def add_source(self, cfg):
        if not self.online:
            self._fail("无法连接中间件服务（模拟离线）")
        sid = str(cfg.get("id") or "")
        box = str(cfg.get("box") or "").lower()
        if not box:
            self._fail("发布前缀（box）不能为空")
        for k, s in self.sources.items():
            if k == sid:
                self._fail(f"数据源 id「{sid}」已存在")
            if str(s.get("box")) == box:
                self._fail(f"前缀「{box}」已被数据源占用")
        item = dict(cfg)
        if item.get("enabled"):
            self.running.add(sid)
        self.sources[sid] = item
        return dict(item)

    def update_source(self, sid, patch):
        if not self.online:
            self._fail("无法连接中间件服务（模拟离线）")
        if sid not in self.sources:
            self._fail(f"数据源不存在：{sid}")
        merged = dict(self.sources[sid])
        merged.update({k: v for k, v in (patch or {}).items() if k != "id"})
        self.sources[sid] = merged
        if merged.get("enabled"):
            self.running.add(str(sid))
        else:
            self.running.discard(str(sid))
        return dict(merged)

    def set_enabled(self, sid, enabled):
        return self.update_source(sid, {"enabled": bool(enabled)})

    def remove_source(self, sid):
        if sid in self.sources or self.online:
            self.sources.pop(str(sid), None)
            self.running.discard(str(sid))

    def test_source(self, cfg):
        if not self.online:
            self._fail("无法连接中间件服务（模拟离线）")
        if str(cfg.get("type")) == "mqtt":
            b = cfg.get("broker") or {}
            if not b.get("host"):
                return {"ok": False, "message": "broker.host 不能为空"}
            if int(b.get("port") or 0) == 1:     # 约定：端口 1 = 不可达
                return {"ok": False, "message": "连接超时"}
        return {"ok": True, "message": "连通性测试通过"}

    def types(self, force=False):
        # 适配器类型仅 mqtt（模拟数据由独立服务生成后经 mqtt 接入）
        return [{"type": "mqtt", "label": "外部 MQTT", "desc": "", "fields": []}]

    def snapshot_status(self, sid):
        return {"id": sid, "running": sid in self.running, "readings": 0,
                "skipped": 0, "errors": 0, "last_at": None, "last_prop": None,
                "last_error": ""}


class _FakeMsg:
    def __init__(self, topic, payload_bytes):
        self.topic = topic
        self.payload = payload_bytes


def _box_payload(device, value, box="nt001"):
    """真实盒子格式（box 前缀不在 external 目录）：归属 box 数据源。"""
    return json.dumps({"v": value, "t": int(time.time() * 1000),
                       "device": device, "box": box})


def _ext_payload(device, value, box="ext-x"):
    """中间件标准发布格式（box 前缀对应 external 条目 config.box）。"""
    return json.dumps({"v": value, "t": int(time.time() * 1000),
                       "device": device, "box": box, "src": "external"})


def _register_ext(name="外部秤站", box="ext-x", enabled=False, adapter="mqtt"):
    r = data_sources.add_external(name=name, enabled=enabled,
                                  config={"box": box, "adapter": adapter})
    sid = next(s["id"] for s in r["sources"] if s["name"] == name)
    return sid


@pytest.fixture
def fake_mw(monkeypatch):
    """替换 middleware_client 全部 HTTP 方法为内存假实现。"""
    fm = _FakeMiddleware()
    for name in ("status", "list_sources", "get_source", "add_source", "update_source",
                 "set_enabled", "remove_source", "test_source", "types"):
        monkeypatch.setattr(middleware_client, name, getattr(fm, name))
    # 数据源状态需要中间件侧 running 信息：包装 get_source 附带 status
    raw_get = fm.get_source

    def _get_with_status(sid):
        s = raw_get(sid)
        if s is None:
            return None
        return {**s, "status": fm.snapshot_status(str(sid))}

    monkeypatch.setattr(middleware_client, "get_source", _get_with_status)
    raw_list = fm.list_sources

    def _list_with_status():
        return [{**s, "status": fm.snapshot_status(str(s.get("id")))} for s in raw_list()]

    monkeypatch.setattr(middleware_client, "list_sources", _list_with_status)
    return fm


@pytest.fixture(autouse=True)
def clean_state():
    """备份/恢复 data_sources.json，清空运行时状态与缓存。"""
    baks = {}
    for p in (DS_PATH,):
        if os.path.exists(p):
            with open(p, "r", encoding="utf-8") as f:
                baks[p] = f.read()
    _reset_runtime()
    yield
    _reset_runtime()
    for p, text in baks.items():
        with open(p, "w", encoding="utf-8") as f:
            f.write(text)


def _reset_runtime():
    ds_config._current = None
    data_sources.reset_cache()          # 目录视图 / 信号目录 / 中间件读缓存一并失效
    with mqtt_source._LOCK:
        mqtt_source.CLOUD_DEVICES.clear()
        mqtt_source.READINGS.clear()
        mqtt_source._LINKS.clear()
        mqtt_source._LINKS_REV.clear()
        mqtt_source._LINKS_FACTOR.clear()
        mqtt_source._EXT_STATS.clear()


# ---------------------------------------------------------------------------
# 一、统一目录
# ---------------------------------------------------------------------------
class TestCatalog:
    def test_default_has_box_only(self):
        types = {s.get("type") for s in ds_config.public_sources(force=True)}
        assert "box" in types
        assert "sim" not in types          # 内置模拟源已移除（模拟由独立服务经 mqtt 接入）

    def test_upsert_and_remove_roundtrip(self):
        src = ds_config.default_external("外部秤站")
        ds_config.upsert_source(src)
        assert ds_config.find_source(src["id"], force=True)["name"] == "外部秤站"
        assert ds_config.remove_source(src["id"]) is True
        assert ds_config.find_source(src["id"], force=True) is None

    def test_box_source_enabled_default(self):
        assert ds_config.is_source_enabled("box", max_age=0) is True

    def test_middleware_config_defaults(self):
        cfg = middleware_client.public_config()
        assert cfg["base_url"] and cfg["timeout"] >= 1.0   # 只保留服务地址/超时（中间件自身不跑 Broker）


# ---------------------------------------------------------------------------
# 二、统一列表与状态形状
# ---------------------------------------------------------------------------
class TestListing:
    def test_list_shape(self, fake_mw):
        r = data_sources.list_sources(force=True)
        assert r["ok"] is True
        assert any(s["type"] == "box" for s in r["sources"])
        for s in r["sources"]:
            assert s["id"] and s["label"] and s["status"] is not None

    def test_box_status_from_subscriber(self, fake_mw):
        box = next(s for s in data_sources.list_sources(force=True)["sources"]
                   if s["type"] == "box")
        assert "connected" in box["status"] and "message_count" in box["status"]
        assert "broker_host" in box["status"]

    def test_toggle_box_updates_catalog(self, fake_mw):
        data_sources.toggle("box", False)
        box = next(s for s in data_sources.list_sources(force=True)["sources"]
                   if s["type"] == "box")
        assert box["enabled"] is False

    def test_list_includes_middleware_status(self, fake_mw):
        r = data_sources.list_sources(force=True)
        assert r["middleware"]["online"] is True


# ---------------------------------------------------------------------------
# 三、box 停用 → 摄取过滤（真实盒子消息被忽略）
# ---------------------------------------------------------------------------
class TestBoxFiltering:
    def test_box_ingested_when_enabled(self):
        topic = "data/nt001/chengzhong/chengzhong/weight"
        _record_message(_FakeMsg(topic, _box_payload("chengzhong", 0.41).encode("utf-8")))
        assert mqtt_source.CLOUD_DEVICES.get("chengzhong") is not None

    def test_box_ignored_when_disabled(self):
        data_sources.toggle("box", False)
        topic = "data/nt001/chengzhong/chengzhong/weight"
        _record_message(_FakeMsg(topic, _box_payload("chengzhong", 0.41).encode("utf-8")))
        assert mqtt_source.CLOUD_DEVICES.get("chengzhong") is None

    def test_mw_message_not_treated_as_box(self):
        """中间件消息（无登记前缀）不误判为盒子数据：仍按普通语义摄取不丢数据。"""
        data_sources.toggle("box", False)
        topic = "data/ext-y/other/other/weight"
        _record_message(_FakeMsg(topic, _ext_payload("other", 5.0, box="ext-y").encode("utf-8")))
        assert mqtt_source.CLOUD_DEVICES.get("other") is not None


# ---------------------------------------------------------------------------
# 四、外部数据源（注册到中间件）：校验 / 同步 / 启停过滤 / 状态统计
# ---------------------------------------------------------------------------
class TestExternal:
    def test_validate_requires_box(self):
        with pytest.raises(ValueError):
            ext_mod.validate_external_config({}, "ext_x")

    def test_validate_rejects_reserved_box(self):
        for reserved in ("box", "platform", "local"):
            with pytest.raises(ValueError):
                ext_mod.validate_external_config({"box": reserved}, "ext_x")

    def test_validate_rejects_bad_chars(self):
        with pytest.raises(ValueError):
            ext_mod.validate_external_config({"box": "Ext_X!"}, "ext_x")

    def test_validate_rejects_unknown_adapter(self):
        with pytest.raises(ValueError):
            ext_mod.validate_external_config({"box": "ext-x", "adapter": "opcua"}, "ext_x")

    def test_validate_rejects_removed_sim_adapter(self):
        """历史 sim 适配器已移除：模拟数据由独立服务生成后经 mqtt 接入。"""
        with pytest.raises(ValueError) as ei:
            ext_mod.validate_external_config({"box": "ext-sim", "adapter": "sim"}, "ext_x")
        assert "不支持的接入类型" in str(ei.value)

    def test_validate_rejects_duplicate_prefix(self, fake_mw):
        _register_ext(name="A", box="ext-x")
        with pytest.raises(ValueError) as ei:
            data_sources.add_external(name="B", config={"box": "ext-x"})
        assert "已被数据源" in str(ei.value)

    def test_normalize_shape(self):
        cfg = ext_mod.normalize_external_config(
            {"box": "Ext-Weigh ", "target": "blast_furnace::belt_scale_0",
             "desc": "外部秤站", "adapter": "mqtt",
             "params": {"broker": {"host": "x"}, "topics": ["a/#"]}}, "ext_ab12")
        assert cfg["box"] == "ext-weigh"
        # 历史 target「自动关联仿真设备」已取消：不再作为登记字段返回
        assert "target" not in cfg
        # 采集参数归入 params（注册到中间件），不散落在顶层
        assert cfg["params"]["broker"] == {"host": "x"}
        assert "topics" not in cfg

    # ---- 与中间件的同步语义 ----

    def test_register_syncs_to_middleware(self, fake_mw):
        sid = _register_ext(name="外部秤站", box="ext-x")
        assert sid in fake_mw.sources                       # 中间件已注册
        assert fake_mw.sources[sid]["box"] == "ext-x"
        assert ds_config.find_source(sid, force=True) is not None   # 本地已登记

    def test_middleware_payload_flattens_params(self, fake_mw):
        sid = _register_ext(name="外部 MQTT", box="ext-mq", adapter="mqtt")
        data_sources.save(sid, config={
            "box": "ext-mq", "adapter": "mqtt",
            "params": {"broker": {"host": "10.0.0.9", "port": 1883}, "topics": ["f/#"]},
        })
        mw = fake_mw.sources[sid]
        assert mw["broker"]["host"] == "10.0.0.9"     # params 平铺进中间件请求体
        assert mw["topics"] == ["f/#"]

    def test_register_failed_when_middleware_offline(self, fake_mw):
        """中间件不可达：注册失败，且本地不落盘（避免状态不一致）。"""
        fake_mw.online = False
        with pytest.raises(Exception):
            data_sources.add_external(name="离线源", config={"box": "ext-off"})
        assert not any(s.get("name") == "离线源"
                       for s in ds_config.public_sources(force=True))

    def test_save_syncs_and_toggle_middleware(self, fake_mw):
        sid = _register_ext(enabled=False)
        data_sources.toggle(sid, True)
        assert fake_mw.sources[sid]["enabled"] is True
        assert sid in fake_mw.running                 # 中间件开始采集
        data_sources.toggle(sid, False)
        assert sid not in fake_mw.running

    def test_remove_deregisters_from_middleware(self, fake_mw):
        sid = _register_ext()
        data_sources.remove(sid)
        assert sid not in fake_mw.sources
        assert ds_config.find_source(sid, force=True) is None

    def test_remove_builtin_and_restore(self, fake_mw):
        """统一管理无例外：内置 box 同样可删除（删除即停止采纳数据），并可原样加回。"""
        data_sources.remove("box")
        assert ds_config.find_source("box", force=True) is None
        assert "box" in ds_config.builtin_removed_ids()
        assert ds_config.is_source_enabled("box", max_age=0) is False      # 删除后立即停止采纳
        r = data_sources.restore_builtin("box")
        assert r["ok"] is True and any(s["id"] == "box" for s in r["sources"])
        assert ds_config.find_source("box", force=True) is not None
        assert "box" not in ds_config.builtin_removed_ids()
        assert ds_config.is_source_enabled("box", max_age=0) is True

    def test_start_keeps_removed_builtin_out(self, fake_mw):
        """start() 尊重用户删除：进程重启不会把已删除的内置 box 又补建回来。"""
        data_sources.remove("box")
        data_sources.start()
        assert ds_config.find_source("box", force=True) is None

    def test_status_merges_middleware_runtime(self, fake_mw):
        """状态 = 中间件采集状态 + 平台摄取统计。"""
        sid = _register_ext(enabled=True)
        st = ext_mod.status_of(sid)
        assert st["running"] is True          # 中间件在采集
        assert st["mw_online"] is True
        assert st["received"] == 0            # 平台还没收到数据
        assert "等待首条数据" in st["note"]

    def test_status_marks_middleware_offline(self, fake_mw):
        sid = _register_ext(enabled=True)
        fake_mw.online = False
        st = ext_mod.status_of(sid)
        assert st["mw_online"] is False
        assert "中间件服务不可达" in st["note"]

    def test_test_config_forwards_to_middleware(self, fake_mw):
        ok = data_sources.test_config({"box": "ext-t", "adapter": "mqtt",
                                       "params": {"broker": {"host": "10.0.0.9", "port": 1883},
                                                  "topics": ["a/#"]}})
        assert ok["ok"] is True
        bad = data_sources.test_config({"box": "ext-t", "adapter": "mqtt",
                                        "params": {"broker": {"host": "127.0.0.1", "port": 1},
                                                   "topics": ["a"]}})
        assert bad["ok"] is False

    # ---- 摄取侧归属识别与启停过滤 ----

    def test_ext_ingested_when_enabled(self, fake_mw):
        _register_ext(enabled=True)
        topic = "data/ext-x/meter1/meter1/weight"
        _record_message(_FakeMsg(topic, _ext_payload("meter1", 12.3).encode("utf-8")))
        cd = mqtt_source.CLOUD_DEVICES.get("meter1")
        assert cd is not None and cd["box"] == "ext-x"
        assert cd.get("primary") == 12.3

    def test_ext_ignored_when_disabled(self, fake_mw):
        _register_ext(enabled=False)
        topic = "data/ext-x/meter1/meter1/weight"
        _record_message(_FakeMsg(topic, _ext_payload("meter1", 12.3).encode("utf-8")))
        assert mqtt_source.CLOUD_DEVICES.get("meter1") is None

    def test_ext_ingest_independent_of_box_source(self, fake_mw):
        data_sources.toggle("box", False)
        _register_ext(enabled=True)
        topic = "data/ext-x/meter1/meter1/weight"
        _record_message(_FakeMsg(topic, _ext_payload("meter1", 12.3).encode("utf-8")))
        assert mqtt_source.CLOUD_DEVICES.get("meter1") is not None

    def test_other_box_prefixes_unaffected_by_ext_disable(self, fake_mw):
        _register_ext(enabled=False)
        topic = "data/nt001/chengzhong/chengzhong/weight"
        _record_message(_FakeMsg(topic, _box_payload("chengzhong", 0.41).encode("utf-8")))
        assert mqtt_source.CLOUD_DEVICES.get("chengzhong") is not None

    def test_ext_status_counts_ingested(self, fake_mw):
        sid = _register_ext(enabled=True)
        _record_message(_FakeMsg("data/ext-x/meter1/meter1/weight",
                                 _ext_payload("meter1", 12.3).encode("utf-8")))
        _record_message(_FakeMsg("data/ext-x/meter2/meter2/temp",
                                 _ext_payload("meter2", 36.5).encode("utf-8")))
        st = ext_mod.status_of(sid)
        assert st["received"] == 2
        assert st["cloud_devices"] == 2
        assert st["last_msg"]["topic"] == "data/ext-x/meter2/meter2/temp"
        assert st["box"] == "ext-x"

    def test_ext_status_after_remove_clean(self, fake_mw):
        sid = _register_ext(enabled=True)
        _record_message(_FakeMsg("data/ext-x/meter1/meter1/weight",
                                 _ext_payload("meter1", 12.3).encode("utf-8")))
        data_sources.remove(sid)
        assert ds_config.external_by_box("ext-x", max_age=0) is None
        with mqtt_source._LOCK:
            assert "ext-x" not in mqtt_source._EXT_STATS

    def test_ext_no_auto_link(self, fake_mw):
        """自动关联已取消：收到外部消息不应自动建立仿真设备关联（关联一律手动）。"""
        _register_ext(enabled=True)
        _record_message(_FakeMsg("data/ext-x/meter1/meter1/weight",
                                 _ext_payload("meter1", 12.3).encode("utf-8")))
        with mqtt_source._LOCK:
            assert "meter1" not in mqtt_source._LINKS

    def test_list_contains_external(self, fake_mw):
        sid = _register_ext(enabled=True)
        kinds = {s["id"]: s for s in data_sources.list_sources(force=True)["sources"]}
        assert kinds[sid]["type"] == "external"
        assert kinds[sid]["config"]["adapter"] == "mqtt"
        assert kinds[sid]["config"]["adapter_label"] == "外部 MQTT"


# ---------------------------------------------------------------------------
# 六、与中间件对账同步（sync_with_middleware）
# ---------------------------------------------------------------------------
class TestSync:
    def test_sync_re_registers_missing(self, fake_mw):
        sid = _register_ext(enabled=True)
        fake_mw.sources.pop(sid)               # 模拟中间件被重建，注册丢失
        res = data_sources.sync_with_middleware()
        # 目录里可能还有其它已登记的外部源（如开发机的模拟源），故只断言本次目标已补注册
        assert res["ok"] is True and res["registered"] >= 1
        assert sid in fake_mw.sources
        assert sid in fake_mw.sources

    def test_sync_reports_offline(self, fake_mw):
        fake_mw.online = False
        res = data_sources.sync_with_middleware()
        assert res["ok"] is False and res["online"] is False


# ---------------------------------------------------------------------------
# 七、可绑定信号目录（signal_catalog：编排模式「附加传感/可变设备」绑定实测值）
# ---------------------------------------------------------------------------
class TestSignalCatalog:
    """按数据源分组列出设备及其**全部数值**：一台设备多值须逐条列出。"""

    @staticmethod
    def _put(cloud_id, box, fields, last_seen=None):
        with mqtt_source._LOCK:
            mqtt_source.CLOUD_DEVICES[cloud_id] = {
                "id": cloud_id, "box": box, "topic": f"data/{box}/{cloud_id}",
                "last_seen": last_seen or time.time(), "fields": dict(fields),
                "primary": list(fields.values())[0] if fields else None,
            }

    def test_empty_catalog_has_no_devices(self):
        cat = data_sources.signal_catalog()
        assert cat["ok"] is True
        assert all(not s["devices"] for s in cat["sources"])

    def test_multi_value_device_lists_every_field(self):
        """一台设备上报多个值：每个值都要作为可绑定信号列出（key 唯一）。"""
        self._put("chengzhong", "nt001", {"weight": 0.41, "temp": 36.5})
        cat = data_sources.signal_catalog()
        box_src = next(s for s in cat["sources"] if s["id"] == "box")
        dev = next(d for d in box_src["devices"] if d["id"] == "chengzhong")
        fields = [v["field"] for v in dev["values"]]
        assert set(fields) == {"weight", "temp"}
        # key 形如 box/device/field，前端凭 key 绑定并取实时读数
        assert {v["key"] for v in dev["values"]} == {"nt001/chengzhong/weight",
                                                     "nt001/chengzhong/temp"}
        assert next(v for v in dev["values"] if v["field"] == "weight")["value"] == 0.41

    def test_external_device_grouped_by_its_source(self, fake_mw):
        """外部源设备按 box 前缀归属到自己的数据源条目，不混进「能碳一体机」。"""
        # 前缀必须唯一：本机目录已登记 ext-steel/idc，测试用独立前缀
        sid = _register_ext(name="外部信号源", box="ext-sigtest", enabled=True)
        self._put("bf1", "ext-sigtest", {"temp": 1250.0})
        cat = data_sources.signal_catalog()
        ext = next(s for s in cat["sources"] if s["id"] == sid)
        assert [d["id"] for d in ext["devices"]] == ["bf1"]
        assert ext["devices"][0]["box"] == "ext-sigtest"
        box_src = next(s for s in cat["sources"] if s["id"] == "box")
        assert [d["id"] for d in box_src["devices"]] == []


# ---------------------------------------------------------------------------
# 八、性能护栏（轻量化）：一轮轮询只打一次中间件、写后即时失效、目录零拷贝只读
# ---------------------------------------------------------------------------
class TestReadCaching:
    def test_one_middleware_http_per_listing(self, monkeypatch):
        """一轮数据源列表查询只调用中间件一次（原先 list_sources + health 各一次）。"""
        calls = {"n": 0}

        def _list():
            calls["n"] += 1
            return [{"id": "x1", "name": "x", "status": {"running": True}}]

        monkeypatch.setattr(middleware_client, "list_sources", _list)
        data_sources.reset_cache()
        for _ in range(3):                       # 模拟前端 6s 轮询连打三次
            r = data_sources.list_sources()
            assert r["middleware"]["online"] is True
        assert calls["n"] == 1                   # 快照窗口内复用同一次 HTTP

    def test_snapshot_force_refreshes(self, monkeypatch):
        """force=True（写操作后）必须真正刷新，不吃缓存。"""
        calls = {"n": 0}

        def _list():
            calls["n"] += 1
            return []

        monkeypatch.setattr(middleware_client, "list_sources", _list)
        data_sources.reset_cache()
        data_sources.list_sources()
        data_sources.list_sources(force=True)
        assert calls["n"] == 2

    def test_write_invalidates_cache(self, fake_mw):
        """写操作后缓存立即失效：增删启停后列表即时反映，无需等待 TTL。"""
        data_sources.list_sources()                       # 先填充快照缓存
        sid = _register_ext(name="缓存校验源", box="ext-cachetest", enabled=True)
        assert sid in [s["id"] for s in data_sources.list_sources()["sources"]]
        data_sources.remove(sid)
        assert sid not in [s["id"] for s in data_sources.list_sources()["sources"]]

    def test_entries_shared_public_sources_copied(self):
        """目录契约：内部只读零拷贝（entries/entry），对外可改的走副本（public_sources）。"""
        assert ds_config.entries() is ds_config.entries()
        assert ds_config.entry("box") is ds_config.entry("box")
        copy = ds_config.public_sources()
        copy[0]["name"] = "被改坏的名字"
        assert ds_config.entry("box")["name"] != "被改坏的名字"
