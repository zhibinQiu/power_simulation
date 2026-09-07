# 独立模拟数据源（外部系统仿真服务）

一个**独立于能碳平台项目**的模拟数据源：自带私有 MQTT Broker，周期生成
**钢铁仿真**与**机房热控**两类数据，模拟一个真实外部业务系统，由**数据中间件**
经 `mqtt` 适配器订阅后转换为平台标准数据。

```
┌── 模拟数据源（本服务 · 独立进程 · 纯标准库 · 零依赖）──────────────────┐
│ ① 外部数据系统：私有 Broker 127.0.0.1:41885                          │
│    生成 steel/<设备>/telemetry、idc/<设备>/telemetry（外部系统原生主题）│
│ ② 一体机上行器 BoxUplink（模拟能碳一体机）：                          │
│    订阅上述原生主题 → 上报云端 Broker(41883) 上行空间 ext/<源>/#       │
└───────────────────────────┬─────────────────────────────────────────┘
                            ▼  云端数据中间件订阅 ext/# 并转换
        标准数据 data/ext-steel/… 、data/ext-idc/…（仍发回 41883）
                            ▼
              平台按前缀识别归属外部源（ext-steel / ext-idc）
```

> **真实链路对照**：① 对应现场的第三方系统（PLC / 仪表 / 数据中台，经网线接入能碳一体机），
> ② 对应**能碳一体机**本身——外部数据是「一体机后面一级」，由一体机采集后统一上报云端。
> 本服务在同一进程内把这两段都模拟出来，因此能完整复现生产链路。

> **平台自身不产生任何模拟数据**：模拟只存在于本进程。停掉本服务，模拟数据即消失，
> 与真实外部系统行为一致（中间件/平台都不内置任何模拟生成器）。

## 1. 数据内容

| 数据源 | box 前缀 | 外部系统原生主题 | 一体机上行后 | 周期 | 设备与测点 |
|---|---|---|---|---|---|
| 钢铁仿真 | `ext-steel` | `steel/…` | `ext/steel/…` | 2s | 1#高炉（热风温度/鼓风量/炉顶压力/铁水温度/焦比/喷煤量）、1#转炉（氧气流量/钢水温度/碳含量/废钢比）、1#烧结机（机速/点火温度/废气温度）、自备电厂（有功功率/蒸汽流量/锅炉压力） |
| 机房热控 | `ext-idc` | `idc/…` | `ext/idc/…` | 3s | 机房A（送/回风温度/湿度/机柜功率/IT 负载）、冷冻水系统（供/回水温度/流量/COP）、空调机组（风机频率/压缩机负载/出风温度）、室外环境（室外温湿度/PUE） |

> 两段主题对应真实链路：外部数据系统按**自己的原生主题**发布（`steel/…`、`idc/…`），
> 能碳一体机（本服务的 `uplink` 上行器模拟）采集后**改写到上行空间**上报
> （`ext/steel/…`、`ext/idc/…`），云端中间件订阅上行空间转换为标准主题
> `data/ext-steel/…`、`data/ext-idc/…` 后平台才消费。
> 关闭上行（配置 `uplink.enabled=false`）即退化为「只有外部系统、没有一体机」的形态。

消息体（常见外部系统 JSON 形态，设备 id 由消息携带，一个主题可承载多测点）：

```json
{"device": "blast_furnace", "hot_blast_temp": 1153.42, "blast_volume": 3210.5, "...": 0}
```

数值模型：`基准 base + 正弦波动(amplitude/period) + 缓慢日漂移 + 有界噪声`，
曲线连续可读；改 `config.json` 即可调整测点、量级与周期。

## 2. 启动（默认在**开发机**）

模拟数据属于开发/演示用途，默认在开发机启动（不占服务器资源）：数据经**开发机中间件实例**
（`middleware/config.dev.json`，订阅本机 41885）转换后直发服务器云端 Broker(41883)，
生产与开发平台都能看到，服务器中间件不采集模拟数据。

```bash
# 推荐（统一入口）
bash platform/update.sh simsource start      # 后台启动（日志 /tmp/nengtan-sim-source.log）
bash platform/update.sh simsource status    # restart / stop / logs / check

# 等价直跑（前台，Ctrl+C 停止）
python3 sim_source.py --config config.json
python3 sim_source.py --config config.json --check          # 自检：打印数据源清单后退出
python3 sim_source.py --config config.json --port 41886     # 覆盖 Broker 端口
```

配套（开发机另开一个终端）：

```bash
cd platform/cloud-deploy/middleware && python3 runner.py --config config.dev.json
```

零第三方依赖（Python 3.8+ 标准库即可）。端口遵循项目规范（一律 40000+，默认 41885）。

## 3. 服务器部署（可选，systemd）

```bash
bash platform/update.sh simsource --server root@36.151.146.71 deploy   # 安装为 systemd 服务
bash platform/update.sh simsource --server root@36.151.146.71 status
# 手工方式等价：
mkdir -p /opt/nengtan-sim-source && cp sim_source.py config.json /opt/nengtan-sim-source/
cp systemd/nengtan-sim-source.service /etc/systemd/system/
systemctl daemon-reload && systemctl enable --now nengtan-sim-source
journalctl -u nengtan-sim-source -f
```

Broker 默认只监听 `127.0.0.1:41885`（仅同机中间件订阅，无需防火墙放行）。

## 4. 接入数据中间件

在平台「能碳一体机与数据源 → 数据源接入」注册两条 **外部 MQTT** 数据源
（中间件按配置订阅本服务的私有 Broker）：

| 项 | 钢铁仿真 | 机房热控 |
|---|---|---|
| 名称 | 钢铁仿真数据源 | 机房热控数据源 |
| 外部源前缀(box) | `ext-steel` | `ext-idc` |
| Broker | `127.0.0.1:41885` | `127.0.0.1:41885` |
| 订阅主题 | `steel/#` | `idc/#` |

中间件收到 JSON 后自动展平（`device` 字段作设备 id，其余数值字段逐条作测点），
按标准主题 `data/{box}/{device}/{device}/{property}` 发布到云端 Broker(41883)，
平台按 `ext-*` 前缀归属为外部数据源。

## 5. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 平台没有模拟数据 | 本服务未启动，或中间件两条 mqtt 数据源未启用；`systemctl status nengtan-sim-source` |
| Broker 端口占用 | 启动时报错 → 换端口 `--port 41886`（同时改中间件数据源配置） |
| 中间件报「外部 Broker 连接失败」 | 中间件与模拟源不在同机：把数据源 Broker 地址改为模拟源所在主机 IP，并放行该端口 |
| 数据一直不变 | 检查配置里 `amplitude/noise` 是否为 0 |
