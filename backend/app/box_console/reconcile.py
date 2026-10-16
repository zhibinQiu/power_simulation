"""云端 CRD 与本地设备登记表的**自动收敛**（reconcile）。

前提（与「一处配置」原则一致）：设备定义只有一份 —— `backend/config/box_devices.json`，
云端 DeviceModel/Device CRD 只是它的派生产物。因此「云端多一台 / 云端少一台」都是
**必须被自动修复的故障态**，不该等用户进界面看见漂移、再手工点「一键对齐」。

本模块周期比对两侧集合：缺的补（kubectl apply，幂等）、多的删（kubectl delete），
让云端 CRD 集合恒等于本地登记表，从而不出现 CRD-only 设备，也不出现「平台有、云端没有」。

安全边界（务必保留）：
· 只在云端 CRD 数据**新鲜**时才动作 —— 用过期缓存对账会把刚下发的设备误判成「缺失」
  而反复 apply，或把已删的误判成「仍在」；
· 云端不可达 / 缓存不新鲜 → 原样跳过，不发任何写操作（云端断连时不存在「对账」这回事）；
· 单飞：同一时刻只允许一轮收敛在跑，与人工「一键对齐」撞车时直接跳过本轮；
· 只收敛云端这条腿。盒子那条腿（采集线程重启）由显式下发负责，不做后台自动重启。
"""
from __future__ import annotations

import logging
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from .. import cloud_agent
from ._shared import _load_devices
from .cloud_ops import (CLOUD_WRITE_LOCK, _cloud_delete_crds, apply_devices_to_cloud,
                        cloud_config)

logger = logging.getLogger(__name__)

# 与人工「一键对齐」共享同一把云端写锁：抢不到说明正有人在下发，直接跳过本轮
_INIT_LOCK = threading.Lock()
_THREAD: Optional[threading.Thread] = None
_LAST: Dict[str, Any] = {"ok": True, "ran": False, "skipped": "尚未运行", "ts": 0.0}

# 默认对账周期（秒）。云端 agent 每 5s 推送一次 CRD，5 分钟足以覆盖偶发下发失败与
# 有人在云端手工 kubectl 造成的漂移；设 0（或负数）可关闭自动收敛。
DEFAULT_INTERVAL = 300.0
# 启动后首轮延迟：等服务就绪、MQTT 订阅拿到第一批 CRD 缓存再对账
FIRST_DELAY = 60.0


def _expected_names() -> Tuple[set, set]:
    """本地登记表里的期望集合：(设备名 ∪ 绑定的 cloudDevice 名, 模型名)。"""
    data = _load_devices()
    devs: set = set()
    for d in data.get("devices") or []:
        if d.get("name"):
            devs.add(str(d.get("name")))
        cid = str(d.get("cloudDevice") or "").strip()
        if cid:
            devs.add(cid)
    models = {str(m.get("name")) for m in (data.get("models") or []) if m.get("name")}
    return devs, models


def _finish(report: Dict[str, Any]) -> Dict[str, Any]:
    """记录本轮结果（供状态查询与前端展示）后返回。"""
    report["ts"] = time.time()
    report.setdefault("ran", True)
    with _INIT_LOCK:
        _LAST.clear()
        _LAST.update(report)
    return report


def last_reconcile() -> Dict[str, Any]:
    """最近一次收敛结果（含 skipped 原因），供前端展示「云端已对齐 / 跳过原因」。"""
    with _INIT_LOCK:
        return dict(_LAST)


def reconcile_cloud(reason: str = "") -> Dict[str, Any]:
    """把云端 CRD 集合收敛为与本地登记表一致；幂等，可安全反复调用。

    reason 仅用于日志区分（周期 / 手动）。返回 {ok, skipped, created, deleted, applied, checked}。
    """
    if not CLOUD_WRITE_LOCK.acquire(blocking=False):
        return {"ok": True, "skipped": "正在下发/上一轮收敛中，本轮跳过"}
    try:
        crds = cloud_agent.crds()
        if not crds.get("ok"):
            return _finish({"ok": False, "skipped": "云端 CRD 不可读（%s），跳过对账"
                            % (crds.get("error") or "agent 无缓存")})
        # 新鲜度门控：CRD 由 agent 周期推送，缓存过期说明推送中断，此时不做任何写操作
        if crds.get("_cached") and not crds.get("_cache_fresh", False):
            return _finish({"ok": False, "skipped": "云端 CRD 缓存已过期（%.0fs 前更新），跳过对账"
                            % (crds.get("_cache_age") or 0)})

        want_dev, want_model = _expected_names()
        have_dev = {str(d.get("name")) for d in (crds.get("devices") or []) if d.get("name")}
        have_model = {str(m.get("name")) for m in (crds.get("models") or []) if m.get("name")}
        missing_dev = sorted(want_dev - have_dev)
        missing_model = sorted(want_model - have_model)
        extra_dev = sorted(have_dev - want_dev)
        extra_model = sorted(have_model - want_model)

        report: Dict[str, Any] = {
            "ok": True, "applied": False, "created": [], "deleted": [], "failed": [],
            "skipped": "", "reason": reason or "periodic",
            "checked": {
                "local_devices": sorted(want_dev), "cloud_devices": sorted(have_dev),
                "local_models": sorted(want_model), "cloud_models": sorted(have_model),
            },
        }
        if not (missing_dev or missing_model or extra_dev or extra_model):
            report["skipped"] = "云端 CRD 与本地登记表已一致，无需动作"
            return _finish(report)

        # 1) 缺的补：整包 apply 幂等（含模型文档），失败要说清原因而不是静默留下漂移
        if missing_dev or missing_model:
            try:
                res = apply_devices_to_cloud()
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
            report["applied"] = True
            if res.get("ok"):
                report["created"] = (["device %s" % n for n in missing_dev]
                                     + ["model %s" % n for n in missing_model])
            else:
                report["ok"] = False
                report["failed"].append("补建云端对象失败：%s" % (res.get("error") or "unknown error"))

        # 2) 多的删：按类型分别删（设备与模型允许同名，混删会带走仍然有效的对象）
        ns = str(cloud_config().get("namespace") or "default")
        for kind, names in (("device", extra_dev), ("model", extra_model)):
            for name in names:
                try:
                    r = _cloud_delete_crds(kind, name, ns)
                except Exception as e:  # noqa: BLE001
                    r = {"ok": False, "error": str(e)}
                if r.get("ok"):
                    report["deleted"].append("%s %s" % (kind, name))
                else:
                    report["ok"] = False
                    report["failed"].append("%s %s 删除失败（%s）"
                                            % (kind, name, r.get("error") or "unknown error"))

        if report["deleted"] or report["created"]:
            logger.warning("云端 CRD 自动收敛：补建 %s、删除 %s（%s）",
                           report["created"] or "-", report["deleted"] or "-",
                           reason or "periodic")
        return _finish(report)
    except Exception as e:  # noqa: BLE001
        return _finish({"ok": False, "skipped": "", "error": "%s: %s" % (type(e).__name__, e)})
    finally:
        CLOUD_WRITE_LOCK.release()


def _interval_from_env() -> float:
    raw = str(os.environ.get("BOX_CLOUD_RECONCILE_INTERVAL") or "").strip()
    if not raw:
        return DEFAULT_INTERVAL
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_INTERVAL


def _loop(interval: float) -> None:
    time.sleep(FIRST_DELAY)
    while True:
        try:
            reconcile_cloud("periodic")
        except Exception as e:  # noqa: BLE001 - 后台线程绝不能因异常退出
            logger.warning("云端 CRD 自动收敛异常：%s", e)
        time.sleep(interval)


def start_reconciler(interval: float = 0.0) -> Optional[threading.Thread]:
    """启动云端 CRD 自动收敛后台线程（幂等：重复调用只起一个线程）。

    周期默认 300s，可用环境变量 BOX_CLOUD_RECONCILE_INTERVAL 覆盖；设为 0 关闭自动收敛。
    """
    global _THREAD
    if interval <= 0:
        interval = _interval_from_env()
    if interval <= 0:
        logger.info("云端 CRD 自动收敛已关闭（BOX_CLOUD_RECONCILE_INTERVAL<=0）")
        return None
    with _INIT_LOCK:
        if _THREAD and _THREAD.is_alive():
            return _THREAD
        _THREAD = threading.Thread(target=_loop, args=(interval,), daemon=True,
                                   name="cloud-crd-reconciler")
        _THREAD.start()
        logger.info("云端 CRD 自动收敛已启动（每 %.0fs 对账一次）", interval)
        return _THREAD


def stop_reconciler() -> None:
    """仅测试用：清空线程句柄（daemon 线程随进程退出）。"""
    global _THREAD
    with _INIT_LOCK:
        _THREAD = None
