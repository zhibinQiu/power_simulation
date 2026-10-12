#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""编排存档（flow / agc）双向合并：把服务器那一侧的存档合并进本地。

背景（为何不能像源码那样「本地覆盖服务器」）：
  流程编排（backend/data/designs/flow.json）与 AI 群控编排（agc.json）是**用户在平台上
  编辑出来的运行期内容**，本地实例（8010）与服务器实例（40014）各写各的文件。此前
  update.sh 只做单向 rsync（本地 → 服务器整体覆盖），结果是：
    ① 在服务器上做的编排，本地看不到（本地那份是旧的）；
    ② 下一次 update.sh 又用本地旧档把服务器上的新编排整体抹掉 ——
       表现为「刚配好的附加传感 / 采集设备绑定，刷新或推送后又被还原」。

合并口径（可预测、不会静默丢档）：
  以**场景（bucket 里的顶层 key）为粒度，取 updatedAt 较新的一份**：
    · 仅服务器有的场景        → 并入本地（服务器上的新编排同步回开发机）
    · 仅本地有的场景          → 保留（随 rsync 推到服务器）
    · 两边都有                → updatedAt 大的那份胜出，另一份在写回前备份
  updatedAt 由前端每次保存时写入（Date.now()），故「谁最后编辑谁生效」，
  与前端 _pullScheme / pullDesigns 的「较新者胜出」口径完全一致。

用法：
  python3 designs_sync.py <bucket> <本地文件> <服务器文件> [--dry-run]
退出码：0 = 无变更或有变更已合并；1 = 入参/文件异常。
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import time


def _load(path: str) -> dict:
    """读取 JSON 字典；文件缺失 / 内容非字典 / 损坏一律按空字典处理（不阻断同步）。"""
    try:
        if not path or not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:  # noqa: BLE001 —— 存档损坏时按空档处理，避免整个推送流程中断
        return {}


def _ts(v: object) -> int:
    """取存档时间戳（毫秒）；缺失 / 非法按 0（最旧）处理。"""
    if isinstance(v, dict):
        try:
            return int(v.get("updatedAt") or 0)
        except (TypeError, ValueError):
            return 0
    return 0


def _fmt(ms: int) -> str:
    if not ms:
        return "无时间戳"
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ms / 1000))


def merge(local: dict, remote: dict):
    """按场景粒度合并，返回 (merged, 变更说明列表)。"""
    merged = dict(local)
    notes = []
    for scene, rv in (remote or {}).items():
        lv = local.get(scene)
        if lv is None:
            merged[scene] = rv
            notes.append(("并入本地（仅服务器有）", scene, _ts(rv)))
            continue
        rt, lt = _ts(rv), _ts(lv)
        if rt > lt:
            merged[scene] = rv
            notes.append(("采用服务器版本（较新）", scene, rt))
        elif lt > rt:
            notes.append(("保留本地版本（较新）", scene, lt))
        else:
            notes.append(("两端一致", scene, lt))
    return merged, notes


def main(argv):
    args = [a for a in argv[1:] if a != "--dry-run"]
    dry = "--dry-run" in argv[1:]
    if len(args) != 3:
        print("用法：python3 designs_sync.py <bucket> <本地文件> <服务器文件> [--dry-run]", file=sys.stderr)
        return 1
    bucket, local_path, remote_path = args
    local = _load(local_path)
    remote = _load(remote_path)
    if not remote:
        print(f"    · {bucket}：服务器存档为空或缺失 → 保持本地版本（{len(local)} 个场景）")
        return 0
    merged, notes = merge(local, remote)
    changed = merged != local
    for action, scene, ts in notes:
        print(f"    · {bucket}/{scene}：{action}（{_fmt(ts)}）")
    if not changed:
        print(f"    ✔ {bucket}：两端一致，无需合并")
        return 0
    if dry:
        print(f"    · {bucket}：dry-run，未写盘（本地 {len(local)} → {len(merged)} 个场景）")
        return 0
    if os.path.exists(local_path):
        bak = f"{local_path}.bak.{time.strftime('%Y%m%d%H%M%S')}"
        shutil.copy2(local_path, bak)
        print(f"    ↳ 合并前本地存档已备份：{os.path.basename(bak)}")
    tmp = local_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    os.replace(tmp, local_path)
    print(f"    ↳ {bucket}：已合并写入本地（{len(local)} → {len(merged)} 个场景），随后随 rsync 推到服务器")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
