"""能碳一体机 · 云端数据仪表盘 (nengtan-cloud-dashboard)。

Flask 服务，端口 41500（全局端口规范 40000+）。
功能：
    - GET /           仪表盘主页：broker 连接状态 + 最近收到的数据（读 collector 落盘目录）
    - GET /api/health 健康检查 JSON

systemd: nengtan-cloud-dashboard.service
"""
from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

from flask import Flask, jsonify, render_template_string

PORT = int(os.getenv("DASHBOARD_PORT", "41500"))
OUT_DIR = Path(os.getenv("OUT_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "collected")))

app = Flask(__name__)

PAGE = """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <title>能碳一体机 · 云端数据仪表盘</title>
  <style>
    body{font-family:system-ui,sans-serif;margin:2rem;background:#f5f7fa;color:#222}
    h1{font-size:1.4rem}.card{background:#fff;border:1px solid #e3e6ea;border-radius:8px;padding:1rem;margin:1rem 0}
    table{border-collapse:collapse;width:100%;font-size:.85rem}
    th,td{border:1px solid #e3e6ea;padding:.4rem .6rem;text-align:left}
    th{background:#f0f2f5}.badge{padding:.15rem .5rem;border-radius:10px;font-size:.75rem}
    .ok{background:#d4f7dc;color:#146c2e}.down{background:#fde2e2;color:#a12}
  </style>
</head>
<body>
  <h1>能碳一体机 · 云端数据仪表盘</h1>
  <div class="card"><b>服务状态</b>
    <table>
      <tr><th>MQTT Broker (41883)</th><td><span class="badge {{ 'ok' if broker_ok else 'down' }}">{{ '在线' if broker_ok else '离线' }}</span></td></tr>
      <tr><th>采集器落盘目录</th><td>{{ out_dir }}</td></tr>
      <tr><th>今日文件</th><td>{{ today_file or '(暂无)' }}</td></tr>
      <tr><th>最近数据条数</th><td>{{ total }}</td></tr>
    </table>
  </div>
  <div class="card"><b>最近数据</b>
    <table>
      <tr><th>时间</th><th>主题</th><th>payload</th></tr>
      {% for r in rows %}<tr><td>{{ r.ts }}</td><td>{{ r.topic }}</td><td>{{ r.payload }}</td></tr>{% endfor %}
    </table>
  </div>
</body>
</html>
"""


def _recent_rows(limit: int = 20) -> tuple[list[dict], str, int]:
    files = sorted(OUT_DIR.glob("*.log")) if OUT_DIR.exists() else []
    today_str = date.today().isoformat()
    today_name = ""
    rows: list[dict] = []
    total = 0
    for fp in reversed(files):
        name = fp.name
        if name.startswith(today_str) and not today_name:
            today_name = name
        try:
            lines = fp.read_text(encoding="utf-8").strip().splitlines()
        except OSError:
            continue
        total += len(lines)
        for line in reversed(lines[-limit:]):
            try:
                rows.append(json.loads(line))
            except (json.JSONDecodeError, TypeError):
                continue
        if len(rows) >= limit:
            break
    return rows[:limit], today_name, total


@app.get("/")
def index():
    rows, today_name, total = _recent_rows()
    # broker 在线与否以 collector 是否在跑 + 近期是否有数据为准，此处用落盘目录存在性兜底
    broker_ok = OUT_DIR.exists() and any(OUT_DIR.glob("*.log"))
    return render_template_string(
        PAGE,
        broker_ok=broker_ok,
        out_dir=str(OUT_DIR),
        today_file=today_name,
        total=total,
        rows=rows,
    )


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "port": PORT, "out_dir": str(OUT_DIR)})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
