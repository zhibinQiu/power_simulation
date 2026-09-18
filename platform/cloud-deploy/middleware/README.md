# 能碳数据中间件（Data Middleware）

独立于能碳平台的**数据接入转换程序**：外部数据源（协议/结构各异）由本中间件
摸清并采集后，**统一转换为标准 MQTT** 发布到「平台订阅的那个 Broker」，与能碳
一体机盒子数据走**完全同一条摄取管道**。

> **模拟数据不是中间件的能力**：模拟由独立服务 `../sim-source/`（外部系统仿真）
> 生成后经 `mqtt` 适配器接入，与真实外部源完全同构；平台与中间件自身都不产生
> 任何模拟数据。

```
外部数据源（秤站/仪表/PLC/数据中台…）经网线接入能碳一体机
        │  一体机上行原始数据 → 云端 Broker 上行空间 ext/<源>/#
模拟数据源（独立服务 sim-source，开发机）模拟同一上行：ext/steel/#、ext/idc/#
        │  中间件订阅上行空间（adapter，可扩展）
        ▼
┌───────────────────────────────┐
│  能碳数据中间件（本程序）      │
│  ├ 输出桥：标准 MQTT 发布器    │
│  └ 适配器：mqtt（内置）/ 其它  │
└───────────────────────────────┘
        │ 统一标准 MQTT（external 形态直发云端 Broker）
        ▼
平台订阅的 Broker（能碳一体机管理→配置 Broker，通常云端 41883）
        │ data/{前缀}/{device}/{device}/{prop}
        ▼
平台摄取 → 识别归属（登记前缀 ↔ 外部源条目）→ 启停过滤 → 关联驱动仿真
```

### 输出形态（唯一）

paho 直发 `output.broker`：服务器上即同机**云端 Broker(41883)**，与一体机数据同 Broker
按前缀区分；平台经云端端点订阅即可取数，无需单独订阅中间件端口
（`config/middleware.json` 已无 `subscribe` 字段）。

平台侧不订阅外部 Broker、不做协议转换：**转换只发生在中间件**。平台对某条外部
数据源的管理 = 「登记 + 启停 + 最近读数展示」，全部锚定在 box 前缀上。

---

## 一、标准接入规范（权威，平台/中间件共同遵守）

任何外部源经中间件发布的数据必须满足：

### 1. 主题（Topic）

```
data/{box}/{device}/{device}/{property}
```

- `{box}`：**发布前缀**，必须与平台「数据源」中该外部源登记的 config.box 完全
  一致（推荐 `ext-` 开头，小写字母/数字/连字符，全局唯一）。平台摄取侧按此前缀
  识别消息归属哪条外部源，并据此做启停过滤与最近读数统计。
- `{device}`：逻辑设备 id（同一条源可含多个设备）。主题第 2/3 段一致。
- `{property}`：属性名（主读数字段，如 `weight` / `temperature`）。

### 2. 载荷（Payload，UTF-8 JSON）

```json
{
  "v": 0.41,          // 数值读数（必须为 int/float；空串/NaN/布尔会被平台忽略）
  "t": 1768600000000, // 毫秒时间戳（可省；缺失时平台取到达时刻）
  "device": "scale1", // 设备 id（与主题一致，可省）
  "box": "ext-weigh", // 前缀（与主题一致，可省）
  "prop": "weight",   // 属性名（与主题一致，可省）
  "src": "external"   // 固定 "external"，标识来自数据中间件（平台按前缀识别，此字段兜底）
}
```

平台摄取侧既可按 payload 的 box 前缀定位外部源条目，也可解析 `src=external`。
为便于调试，中间件会在 payload 中携带上述完整字段。

### 3. 归属与启停语义

- 平台「数据源」列表中的外部源条目 `enabled=false` 时，摄取侧**忽略**该前缀下
  的全部消息（不识别为云端设备、不驱动仿真）；重新启用即恢复。
- 前缀未在任何条目登记的消息：不误杀，按普通数据源语义摄取（默认采纳）。

### 4. 平台登记步骤

1. 平台「数据源」→ 新增外部源：名称 + box 前缀（如 `ext-weigh`）+ 可选
   「自动关联仿真设备」（target：`{工序}::{设备实例}`，如
   `blast_furnace::belt_scale_0`，该源首条消息会把外部设备自动关联过去）。
2. 中间件配置里用**同一前缀**作为该 adapter 的 box。
3. 启用条目 → 中间件数据到达即出现在设备列表，可驱动仿真。

---

## 二、快速开始

```bash
cd platform/cloud-deploy/middleware      # 本目录（云端部署包内）
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 1) 复制并编辑配置（输出 Broker = 平台订阅的 Broker）
cp config.example.json config.json

# 2) 自检（不连 Broker，打印加载摘要）
python runner.py --config config.json --check

# 3) 前台运行（Ctrl+C 优雅退出）
python runner.py --config config.json
# 或后台：nohup python runner.py --config config.json > middleware.log 2>&1 &
```

> 中间件与平台**无任何代码/部署耦合**：只需能访问同一个 Broker。可在平台服务器、
> 云端服务器或任意可达外部源与 Broker 的主机运行。

---

## 三、配置说明

顶层：`output`（发布目标）+ `adapters`（采集任务数组）。

```json
{
  "output": {
    "broker": { "host": "127.0.0.1", "port": 41883, "username": "", "password": "" },
    "qos": 0
  },
  "log_level": "info",
  "adapters": []
}
```

### 内置适配器一：`mqtt`（外部 MQTT → 标准 MQTT）

用于外部系统本身是 MQTT、且其 Broker 与平台订阅 Broker 不同的场景（最常见）。
中间件订阅外部 Broker 的主题 → 解析数值 → 按标准规范发布到平台 Broker。

```json
{
  "id": "weigh_ext",
  "type": "mqtt",
  "name": "外部秤站",
  "enabled": true,
  "box": "ext-weigh",                    // = 平台登记的外部源前缀
  "device": "scale1",                    // 默认设备（消息无 device 字段时使用）
  "fieldMap": { "gross": "weight" },     // 可选：字段改名（输出属性名）
  "broker": { "host": "10.0.0.20", "port": 1883, "username": "", "password": "" },
  "topics": [ "factory/scale1/#" ],
  "qos": 0
}
```

采集逻辑：外部消息为 JSON 对象 → 递归展平数值字段（嵌套 `a.b` 也会展开）→
`fieldMap` 改名 → 每个数值字段作为一条属性发布。设备 id 优先取消息里的
`device`/`deviceId`/`sensor` 字段（可通过 `deviceKeys` 自定义），否则取配置的
`device`。时间优先取消息 `ts`/`time`/`timestamp`（秒或毫秒自动归一），否则取
收到时刻。字符串无法转为数值的字段会被跳过并在日志中提示（debug）。

---

## 四、扩展新适配器

外部数据形态不一定是 MQTT（HTTP 轮询、Modbus TCP、OPC UA…），此时新增一个
adapter 类即可（**平台与标准规范都不用动**）：

```python
# middleware/adapters/my_http.py
from .base import BaseAdapter

class HttpPollAdapter(BaseAdapter):
    """定时 HTTP 拉取 → 逐条 emit 读数。"""
    def start(self):
        self._stop = False
        while not self._stop and self.running:
            data = self._fetch()          # 你的采集逻辑
            self.emit_flat(data)          # 基类帮你：展平数值 → 标准发布
            time.sleep(self.cfg.get("interval", 30))

# middleware/adapters/__init__.py 注册
#   from .my_http import HttpPollAdapter
#   BUILDERS["http"] = HttpPollAdapter
```

配置里 `"type": "http"` 即可被 runner 加载。所有 adapter 最终都调
`self.emit(prop, value, ts=None)` / `self.emit_flat(obj)`，由输出桥按标准规范发布。

### 关键约定

- `box` 前缀：见「标准接入规范」第 1 节，必须与平台登记一致。
- `emit_flat`：数值字段整体发布；布尔/字符串跳过；`fieldMap` 自动套用。
- 建议低频去重：中间件不会缓存重发，值变化与否都即时发布（与真实上报一致）。

---

## 五、运行说明与运维提示

- 日志：stderr 输出 `时间 [level] [adapter] 消息`；`--check` 只加载配置不自检连接。
- 重连：paho 客户端断线自动重连（订阅/发布同连接）；输出桥连不上会持续告警，
  平台外部源状态显示「已启用，等待中间件发布数据…」即为中间件未连上/未产生数据。
- 多任务：一个中间件进程可配多个 adapter（多个外部源）；也可每源一个进程实例。
- 监控口径：中间件「活着」不保证有数据——以平台外部源卡片上的最近读数/设备数
  为准（那是摄取侧真实统计）。

---

## 六、模拟数据源接入（独立服务，默认跑在开发机）

模拟数据由**独立进程**提供（平台与中间件自身都不产生任何模拟数据）。默认在**开发机**
启动，由开发机中间件实例采集转换后并入服务器云端 Broker：

```bash
# 开发机 1：起模拟源（自带 Broker 127.0.0.1:41885）
bash platform/update.sh simsource start          # 等价于 ../sim-source/sim_source.py --config ../sim-source/config.json

# 开发机 2：本中间件用开发机配置启动（订阅 41885 的 steel/#、idc/# → 直发 36.151.146.71:41883）
python3 runner.py --config config.dev.json
```

服务器中间件（`config.json`）的 `adapters` 为空：**服务器侧不采集模拟数据**。
完整接入方法见 [`../../doc-deploy/docs/外部数据接入中间件指南.md`](../../doc-deploy/docs/外部数据接入中间件指南.md)。

在本中间件注册两条 `mqtt` 数据源即可（平台「数据源接入」页面操作，或写进 config.json）：

| 名称 | box 前缀 | Broker | 订阅主题 |
|---|---|---|---|
| 钢铁仿真数据源 | `ext-steel` | `127.0.0.1:41885` | `steel/#` |
| 机房热控数据源 | `ext-idc` | `127.0.0.1:41885` | `idc/#` |

详见 [`../sim-source/README.md`](../sim-source/README.md)。

---

## 七、服务器部署（systemd，推荐与云端 Broker 同机）

```bash
# 开发机执行：rsync 源码 → 服务器 → venv 依赖 → systemd 常驻
bash platform/cloud-deploy/middleware/deploy_middleware.sh --server root@36.151.146.71
# 服务器上本地执行（源码已就位时）：bash deploy_middleware.sh --local-only
# 日常只更新代码（配合 platform/update.sh middleware）：bash deploy_middleware.sh sync
```

- 安装目录 `/opt/nengtan-middleware`（源码在 `middleware/` 子目录，venv 在外层）；
  保持「仓库子目录包式」布局是因为 `runner.py` 需要父级可直接 import `middleware` 包。
- 服务名 `nengtan-middleware`，日志 `journalctl -u nengtan-middleware -f`；
- 管理 API `42084` 需服务器防火墙放行（UFW：`ufw allow 42084/tcp`）；
- external 形态数据直发同机 `127.0.0.1:41883`，平台经云端端点订阅，无需额外数据端口。
