# 边缘盒子一键部署包 (box-deploy)

把「标准 KubeEdge DMI 多协议链路」的部署固化为一个可重复执行的部署包：
**仪表/DCS → mapper(纯 Python, 多协议并行) → dmi.sock → edgecore → CloudHub → 云端 K3s → Device.status.twins**

mapper 单进程支持五类设备**并行采集**（v1.3.0），后续接新设备只需在 `config.json` 加一段配置：

| 协议 | 接入方式 | 适用场景 |
|---|---|---|
| `modbus-rtu` | RS485 串口（termios 直驱） | 称重仪表、电表、压力/温度变送器 |
| `modbus-tcp` | 以太网（MBAP + 0x03） | 国产 DCS（中控/和利时）、PLC、网关 |
| `opcua` | 以太网（asyncua，需 wheel） | 国际 DCS（西门子 PCS7/霍尼韦尔/ABB）、SCADA 数据平台 |
| `lora` | 无线 LoRaWAN（ChirpStack → 本地 mosquitto） | LoRa 无线传感器（温湿度/气体等） |
| `cellular` | 5G/4G 模块 AT 口 + 蜂窝接口计数 | 模块信号/ICCID/注册态/上下行速率自监控 |

> 统一协议注册名：KubeEdge edgecore 按 `Device.spec.protocol.protocolName` 匹配 mapper 注册名，
> 本包统一注册 **`nengtan-iot`**，平台生成的任何协议 YAML 的 protocolName 也都是它，
> 因此新增协议/设备无需改 mapper 代码。

**v1.3.0 关键能力**：

| 能力 | 说明 |
|---|---|
| 实时双源直报 | 每次读数同时走 DMI twins（主链路）与 MQTT `data/#`（独立直报，paho 自动重连），任一通道可用平台即可拿到实时数据 |
| 全自动自愈 | DMI 健康检查周期性重注册，edgecore/CloudHub 重启、dmi.sock 重建后自动恢复（盒子运行期无 IP、无法远程运维，不依赖人工） |
| 云边协同断点续传 | 断连读数落本地 SQLite（上限 20 万条），恢复后 MQTT 带真实时间戳回填历史 + DMI 补最新值，成功才删缓存 |
| 补传守护线程 | 与设备采集线程解耦：即使采集线程因设备故障持续失败，只要云边恢复，历史缓存仍由守护线程自动补传上云 |
| 应用/模型部署 | 订阅 `cmd/{box}/#` 命令主题，支持云端下发 model（仅存储）/ service（下载并后台拉起）部署与启停/卸载/列表，结果回报 `state/{box}/deploy`，运行清单持久化于 manifest.json |

## 目录结构

```
box-deploy/
├── deploy_box.sh          # 一键部署脚本 (幂等, 支持子命令与自检)
├── mapper/                # DMI mapper 源文件 (box_mapper.py + 生成的 gRPC 代码)
│   └── config.json        # 可编辑配置模板 (多设备多协议 + MQTT 双源 + 应用部署)
├── mosquitto/             # 盒子本地 MQTT Broker 配置
│   ├── mosquitto.conf     # 端口 1883, 禁止匿名, ACL
│   ├── mosquitto.acl      # 含 $hw/# 规则 (MQTT 规范 # 不匹配 $ 前缀)
│   └── passwd             # 预生成账号: admin(hy@2025@) / user01
├── wheels/                # 离线 arm64 wheel (grpcio/protobuf/typing_extensions/
│                         #  paho-mqtt/asyncua 及依赖, 盒子无外网可用)
└── Dockerfile.mapper      # 可选: 容器化 mapper 镜像 (构建后盒子免装依赖)
```

## 用法 (在盒子上执行)

```bash
# 完整部署 (依赖 + mapper + mosquitto + systemd)
./deploy_box.sh

# 或按需
./deploy_box.sh --deps-only       # 仅装 Python 依赖 (含 asyncua)
./deploy_box.sh --mapper-only     # 仅部署 mapper + systemd
./deploy_box.sh --mosquitto-only  # 仅部署 mosquitto
./deploy_box.sh --check           # 链路自检 (只读, 含协议清单)
```

脚本幂等：重复执行安全；已存在的 `config.json` 会保留（改配置不丢）。
部署产物：
- mapper 程序 → `/opt/weight-bridge/dmi/`
- 可编辑配置 → `/opt/weight-bridge/config.json`
- mosquitto → `/opt/weight-bridge/mosquitto/`（ctr 容器 `nengtan-mosquitto`，监听 1883）
- systemd → `box-mapper.service`
- 云下发应用/模型 → `/opt/box-apps/`（含 `manifest.json` 运行清单、`logs/`，可 `apps.dir` 改路径）

## 新盒子接入完整流程（与平台「盒子一键接入」弹窗联动）

**方式 A（推荐，GitHub 托管，零搬运）**：平台「盒子接入 → GitHub 托管」把接入资产
（轻量引导脚本 + box-deploy 包 + edgecore.yaml + rootCA + token）同步到你的 GitHub 仓库
`onboard/` 目录（幂等覆盖），盒子现场**一条 curl 命令**完成全部接入（幂等，可重跑）：

```bash
# 盒子 root 下执行（任意有外网的盒子；自动拉取部署包/证书/配置 + keadm join + 自检）
curl -fsSL https://raw.githubusercontent.com/<owner>/<repo>/<branch>/onboard/onboard_box.sh | bash
```

**现场只有一份配置文件（无平台、无源码）**：平台「盒子接入 → GitHub 托管 → ⬇ 导出
box-config.json」，把导出的配置保存到盒子 `/opt/weight-bridge/box-config.json`，然后执行
同一条命令即可 —— 引导脚本自动读取该配置（`boxId`/`cloudIP` 必填；`token` 留空时自动从
仓库拉取；`repo`/`branch` 可覆盖为镜像仓库），全部参数不再依赖脚本内置值。

> 详细接入流程、box-config.json 字段表、现场命令全集与注意事项，统一见平台内
> **「帮助 → 技术文档 → 盒子一键接入（GitHub 托管 · 配置驱动）」** 章节。

**方式 B（离线/内网，自解压脚本）**：平台「盒子接入」生成**自解压一键脚本 `onboard_box.sh`**
（内嵌 box-deploy 部署包 tar.gz + edgecore.yaml + rootCA.crt + token，约 18 MB），
下载后放到盒子，**一条命令**完成全部接入：

```bash
# 盒子 root 下执行（现场 U 盘/局域网传脚本，或平台「远程一键接入」推送到盒子）
bash onboard_box.sh
```

脚本自动完成：
1. **① EdgeCore 基础接入**：edgecore 未运行且有 keadm → `keadm join --cloudcore-ipport=<云IP>:10000 --token=<token> --kubeedge-version=v1.20.0 --with-edge-core`；已接入自动跳过
2. **② 配置下发**：内嵌 rootCA 写 `/etc/kubeedge/ca/rootCA.crt`（云端 agent 拉取；不可达时降级 `scp` 兜底），覆盖 `/etc/kubeedge/config/edgecore.yaml`（模板渲染），`systemctl restart edgecore.service`
3. **③ 部署包解包**：内嵌 base64 解出到 `/opt/weight-bridge/box-deploy/`（无需手工 scp 上传）
4. **④ config.json 自动定制**：首次生成时自动设 `mqtt.boxId=<盒子主机名>`、`mqtt.broker.host=<云IP>:41883`（已有 config.json 保留不动）
5. **⑤ 一键部署**：`./deploy_box.sh`（幂等：依赖离线安装 + mapper + mosquitto + systemd）
6. **⑥ 链路自检**：`./deploy_box.sh --check`

平台另提供**「🚀 远程一键接入」**：云端 agent 经 SSH 把脚本推送到盒子并执行（无需现场操作），
前提是云端 agent `config.json` 已配置 edge（盒子可达地址）；盒子无直达 IP 时云端无法 SSH 直达，改用下载脚本现场执行。

> 手工五步（备选）：
> ① `keadm join` → ② 拉 rootCA + 覆盖 edgecore.yaml + restart → ③ 云端建 Device（平台「设备管理」一键下发）→
> ④ `scp -r platform/box-deploy root@<盒子IP>:/opt/weight-bridge/box-deploy` + `./deploy_box.sh` + 定制 config.json → ⑤ 云端 `kubectl annotate device <name> sync=$(date +%s) --overwrite` 触发路由，`kubectl get device <name> -o json | grep reported` 看到读数即通。

> 云边协同：mapper 上报失败时读数落本地 SQLite（`/opt/weight-bridge/twin_cache.db`，上限 20 万条），连接恢复后先按真实时间戳 MQTT 补传（`data/<box>/<device>/...`，平台回填折线图缺口）再 DMI 补最新值，成功才删缓存——断连数据不丢。

## config.json 多协议配置

`devices` 数组每项一个设备，字段按协议取；同一盒子可混插多协议并行采集：

```jsonc
{
  "mapperName": "nengtan-multi-mapper",
  "protocol": "nengtan-iot",            // 统一协议注册名, 勿改
  "cache": { "db": "/opt/weight-bridge/twin_cache.db", "max": 200000, "flushBatch": 100 },
  "mqtt": { "enabled": true, "boxId": "box-nt001",
            "broker": { "host": "36.151.146.71", "port": 41883, "username": "", "password": "" },
            "cmdTopic": "cmd/{box}/#", "cmdAckTopic": "state/{box}/deploy",
            "servicesTopic": "state/{box}/services" },
  "apps": { "dir": "/opt/box-apps" },        // 云端下发应用/模型的安装根目录 (默认即此)
  "devices": [
    { "name": "weight_scale_001",       // 须与云端 Device 名一致
      "namespace": "default",
      "protocol": "modbus-rtu",         // 1) RS485 串口
      "interval": 1.0,
      "serial":  { "port": "/dev/ttyUSB4", "baudrate": 9600, "databits": 8, "parity": "N", "stopbits": 1 },
      "modbus":  { "slaveId": 1, "byteOrder": "2143" },
      "points":  [ { "property": "weight", "registerAddr": 0, "registerCount": 2, "type": "float32", "scale": 1.0 } ] },
    { "name": "dcs_energy_001",
      "namespace": "default",
      "protocol": "modbus-tcp",         // 2) 以太网 Modbus TCP
      "interval": 2.0,
      "tcp":     { "host": "192.168.1.10", "port": 502, "timeout": 3.0 },
      "modbus":  { "slaveId": 1, "byteOrder": "1234" },
      "points":  [ { "property": "power",   "registerAddr": 0,  "registerCount": 2, "type": "float32", "scale": 1.0 },
                   { "property": "flow_gas","registerAddr": 10, "registerCount": 2, "type": "float32", "scale": 0.1 } ] },
    { "name": "dcs_opcua_001",
      "namespace": "default",
      "protocol": "opcua",              // 3) 以太网 OPC-UA (需 asyncua wheel)
      "interval": 3.0,
      "opcua":   { "url": "opc.tcp://192.168.1.20:4840", "username": "", "password": "", "securityMode": "None" },
      "points":  [ { "property": "blast_temp", "nodeId": "ns=2;s=BlastFurnace.Temp", "scale": 1.0 },
                   { "property": "coal_flow",  "nodeId": "ns=2;s=BlastFurnace.CoalFlow", "scale": 1.0 } ] }
  ]
}
```

字段速查：

| 字段 | 适用协议 | 说明 |
|---|---|---|
| `serial.*` | modbus-rtu | 串口参数（port/baudrate/databits/parity/stopbits） |
| `tcp.*` | modbus-tcp | host/port/timeout，默认 502 |
| `modbus.slaveId` | 两种 Modbus | 从站地址（DCS 侧要对应） |
| `modbus.byteOrder` | 两种 Modbus | float32 字节序：`2143`（AB CD）/ `1234` / `4321` / `3412`，以仪表手册为准 |
| `points[].registerAddr/registerCount` | 两种 Modbus | 保持寄存器地址与寄存器数（float32=2 个寄存器） |
| `points[].type` | 两种 Modbus | float32 / int16 / uint16 / int32 / uint32 / int64 / uint64 |
| `opcua.*` | opcua | `url` 为 DCS 的 `opc.tcp://IP:4840`，用户名密码按需 |
| `points[].nodeId` | opcua | OPC-UA 节点标识，如 `ns=2;s=BlastFurnace.Temp`（用 UA Expert 浏览） |
| `lora.broker/port` | lora | 盒子本地 mosquitto（ChirpStack 应用上行推送目标），默认 `127.0.0.1:1883` |
| `lora.applicationID/devEUI` | lora | ChirpStack 应用 ID 与节点 DevEUI（LoRaWAN 入网后生成） |
| `points[].payloadKey` | lora | 上行 JSON 里该点位的键，支持 `a.b.c` 嵌套路径（对应平台表单 payloadKey） |
| `cellular.serialPort/baudRate` | cellular | 5G/4G 模块 AT 口（移远通常 `/dev/ttyUSB2`，115200） |
| `cellular.apn` | cellular | 运营商 APN（如 cmnet），拨号用，不影响采集 |
| `cellular.iface` | cellular | 蜂窝网卡名（默认 `wwan0`），用于上下行速率差分统计 |
| `points[].kind` | cellular | 点位类型：signal/csq/rsrp/rsrq/sinr/iccid/imsi/imei/reg/rx_rate/tx_rate |
| `points[].scale` | 全部 | 原始值缩放系数（如仪表量程换算） |
| `mqtt.boxId` | 全部 | 盒子标识，用于 `data/{box}/...` 实时数据、`cmd/{box}/#` 命令、`state/{box}/...` 状态主题 |
| `mqtt.cmdTopic/cmdAckTopic/servicesTopic` | 全部 | 命令订阅 / 部署结果回报 / 服务状态上报主题（默认如上，一般勿改） |
| `apps.dir` | 全部 | 云下发应用/模型安装根目录，默认 `/opt/box-apps`（也可环境变量 `APP_ROOT` 覆盖） |

## LoRa 无线传感器接入

LoRa 与 DCS/仪表不同：它走**无线 LoRaWAN**，盒子侧需一个 LoRa 网关把无线转以太网/MQTT，再进 mapper。两种形态：

**形态 A（推荐，标准 LoRaWAN）**
```
LoRa 传感器 --LoRaWAN 射频--> 盒子 SX1302/SX1261 网关板（USB/SPI 内置）
  --> ChirpStack（盒子上运行，可容器化）--> 本地 mosquitto
  --> mapper LoraReader 订阅 application/{appID}/device/{devEUI}/event/up
  --> payloadKey 提取 --> DMI twins --> 云端
```
- config.json 的 `devices` 里配 `"protocol": "lora"` + `lora.broker/applicationID/devEUI` + 每点位 `payloadKey`
- 平台建设备时协议选 **LoRaWAN（LoRa 网关）**，填 DevEUI/AppKey 与点位上行键
- 依赖：盒子上跑 ChirpStack（PostgreSQL+Redis+网关桥），离线镜像放 `platform/box-deploy/` 可选提供；mapper 本身只需 paho-mqtt（已有）

**形态 B（串口透传，LoRa 当无线 RS485）**
- LoRa 节点以**透传模式**组网，网关串口收到的就是传感器 Modbus 帧 → 直接把网关当一台 Modbus-RTU 从站配 `"protocol": "modbus-rtu"`，**无需新协议**
- 适合低成本点对点（不建 LoRaWAN 服务器），平台选 Modbus 协议即可

## 5G/4G 模块自监控

5G 模块（RM500Q/FM150 等）既是**上行回传链路**，也可当一台"设备"纳入统一管理，采集信号质量/ICCID/注册态/上下行速率，用于现场信号弱告警与回传质量监控：

```
5G 模块（USB/M.2 内置）--AT 口 /dev/ttyUSB2--> mapper CellularReader
  --> AT+CSQ / AT+QENG="servingcell" / AT+ICCID / AT+CEREG?
  --> /proc/net/dev wwan0 计数差分算上下行速率
  --> DMI twins --> 云端
```
- config.json 的 `devices` 里配 `"protocol": "cellular"` + `cellular.serialPort/apn/iface` + 每点位 `kind`
- 平台建设备时协议选 **5G/4G 模块自监控**，点位类型下拉选 signal/rsrp/rsrq/sinr/iccid/imsi/imei/reg/rx_rate/tx_rate
- 注意：`iccid/imsi/imei` 为字符串值，走 twins 字符串上报（已兼容）；`signal` 为 CSQ 原始值 0-31，`rsrp/rsrq/sinr` 需模块支持 `AT+QENG="servingcell"`（移远/广和通主流模块均支持），不支持时该点位跳过不阻塞

## 云端下发应用/模型部署（v1.3.0）

盒子运行期无直达 IP，现场无法登录运维，但应用/模型可以**由云端通过 MQTT 命令远程下发**。mapper 订阅 `cmd/{box}/#`（默认，`mqtt.cmdTopic` 可配），解析 JSON 指令执行并回报结果：

```
平台(MQTT 41883) --publish--> cmd/{box}/deploy {cmd, name, type, url, ...}
mapper 下载/解压/拉起 --publish state/{box}/deploy--> 平台（request_id 关联, 带 ok/message/detail）
mapper 周期(30s) --publish state/{box}/services--> 平台（运行服务清单, 盒子卡片展示）
```

**支持的命令**（`cmd` 字段，`deploy` 别名 `install`，`remove` 别名 `uninstall`）：

| 命令 | 指令载荷 | 行为 |
|---|---|---|
| `deploy` / `install` | `{cmd, name, type, url, version?, command?, args?}` | 下载并安装；`type=model` 仅存储不启动；`type=service` 配了 `command` 则后台拉起（记录 pid） |
| `start` | `{cmd, name}` | 启动已安装的 service（model 无操作） |
| `stop` | `{cmd, name}` | 停止运行中的 service |
| `remove` / `uninstall` | `{cmd, name}` | 停止并删除应用目录与清单项 |
| `restart` | `{cmd, name}` | 停止后重新拉起 service |
| `list` / `services` | `{}` | 回报当前应用清单（detail.services） |

**部署细节**：
- `url` 指向可下载的模型/服务包（HTTP(S) 直链）：`.tar.gz` / `.zip` 自动解压到 `/opt/box-apps/<name>/`，单文件则原样存放（可执行文件自动 `chmod +x`）
- `type=service` 时 `command` 为启动命令（如 `python3 app.py`，解压包内可相对路径），`args` 为参数数组；进程由 `nohup` 拉起、pid 记录，退出自动重启
- 运行清单持久化于 `/opt/box-apps/manifest.json`（含 name/type/version/url/status），**盒子重启后仍可 start/stop/remove 管理**
- 应用名仅限 `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`；安装目录 `apps.dir` 可配，默认 `/opt/box-apps`；服务日志在 `/opt/box-apps/logs/`

**平台侧**：云端命令由 platform 发起（MQTT publish 到 `cmd/{box}/deploy`），`state/{box}/deploy` 回报经 `cloud-agent`/`mqtt_source` 回填，盒子上报的 `state/{box}/services` 用于「能碳一体机管理」盒子卡片展示已部署应用与运行状态。

## 接线后如何接一台新设备

1. 云端 `kubectl apply -f` DeviceModel/Device YAML（平台「能碳一体机管理 → 创建设备」生成，协议选 Modbus TCP / OPC-UA；或参考本仓库 `platform/box-deploy/mapper/config.json` 模板）
2. 盒子改 `/opt/weight-bridge/config.json` 的 `devices` 数组：
   - `name` 与云端 Device 一致，`points[].property` 与 DeviceModel 属性一致
   - Modbus：按 DCS 点表填 `registerAddr / registerCount / type / byteOrder / scale`，`slaveId` 与 DCS 从站一致
   - OPC-UA：用 UA Expert 连 DCS 服务器浏览出 `nodeId`，填入 `points[].nodeId`
3. `systemctl restart box-mapper`
4. 云端触发一次 Device 更新（`kubectl annotate device <name> -n default sync=$(date +%s) --overwrite`），edgecore 即把该设备路由到本 mapper
5. 云端 `kubectl get device <name> -o json | grep reported` 看到读数即链路通

> DCS 对接现场要点：盒子采集口（eth1）与 DCS 工控网段隔离，不得暴露外网；mapper 对 DCS 只读点位，严禁写。

## 改 mosquitto 密码

```bash
ctr -n k8s.io run --rm --net-host <mosq镜像> mosq-passwd \
  /usr/bin/mosquitto_passwd -b /tmp/passwd <用户> <新密码>
cp /tmp/passwd /opt/weight-bridge/mosquitto/passwd
chmod 644 /opt/weight-bridge/mosquitto/passwd   # 关键: 容器内以 uid=1883 运行, 600 读不到
systemctl restart 或重启 nengtan-mosquitto 容器
```

## 容器化 (可选, 盒子免装 Python 依赖)

```bash
# 本机构建并推送 arm64 镜像到内网 registry
docker buildx build --platform linux/arm64 \
  -t 220.154.128.231:5000/nengtan-multi-mapper:1.3.0 \
  -f Dockerfile.mapper . --push

# 盒子一行启动 (需先在盒子上有 config.json 与 dmi.sock)
ctr -n k8s.io run --detach --net-host \
  --mount type=bind,src=/opt/weight-bridge/config.json,dst=/opt/nengtan/config.json \
  --mount type=bind,src=/etc/kubeedge/dmi.sock,dst=/etc/kubeedge/dmi.sock \
  --mount type=bind,src=/dev/ttyUSB4,dst=/dev/ttyUSB4 \
  --mount type=bind,src=/opt/box-apps,dst=/opt/box-apps \
  220.154.128.231:5000/nengtan-multi-mapper:1.3.0
```

## 常见故障

| 现象 | 原因 | 处理 |
|---|---|---|
| mapper 日志 `waiting for dmi.sock` | edgecore 未启 DMI 或未运行 | `grep -A1 dmi /etc/kubeedge/config/edgecore.yaml` 确认 enable |
| 云端 twins 空 | 设备未注册进 dtcontext | 云端 annotate 触发 Device 更新，见「接新设备」第 4 步 |
| opcua 设备日志 `未安装 asyncua` | asyncua wheel 未装 | `./deploy_box.sh --deps-only` 重装；确认 `wheels/asyncua*.whl` 在包内 |
| OPC-UA 连接超时 | DCS 4840 未开放 / 网段不通 | 盒子 `nc -zv <DCS-IP> 4840`，联系 DCS 厂商开 OPC-UA Server |
| modbus-tcp 报 `事务 ID 不匹配` | DCS 网关并发限制 | 增大 `interval`，或换 OPC-UA 订阅 |
| mosquitto 容器起不来 | passwd 权限 600 | `chmod 644 .../passwd` + `chmod 777 .../data .../log` |
| mapper 报 `does not support converting to any` | KubeEdge v1.20 DMI 转换 bug | 设备 configData 保持简单结构，避免嵌套 map |
| `$hw` topic 发布失败 | topic 被 shell 当变量展开 | 用脚本文件或单引号包裹，勿让 `$` 进 shell 变量 |
| 云端部署回报 `下载/安装失败` | url 盒子不可达 / 包格式不支持 | 确认 url 盒子能 `curl -I` 到（公网或内网直链），仅支持 tar.gz/zip/单文件 |
| 部署回报 `应用名非法` | name 含中文/空格等 | 应用名限 `[A-Za-z0-9._-]`，1-64 字符 |
| 云端 `state/{box}/deploy` 收不到回报 | MQTT 通道未就绪 | mapper 日志看 `MQTT 未就绪，命令回报丢弃`；确认云端 Broker 41883 与 `mqtt.boxId` 一致 |
