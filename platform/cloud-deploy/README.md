# 能碳一体机 · 云端部署包 (cloud-deploy)

> 对应 `box-deploy`（边缘盒子部署包）的**云端侧**部署包。
> 用途：在一台新云服务器上从零部署「KubeEdge 云端控制面 + 能碳数据面 + 云端 agent」，
> 使边缘盒子（box-deploy 部署）可以接入、设备数据可以上云。
> **不含平台本身**（能碳平台 web 应用 / kubeedge-status 管理台，见第 6 章说明）。

适用环境（与 `kubeedge-console-ops.md` 手册一致）：

| 项 | 值 |
|---|---|
| 云端 OS | openEuler / CentOS / Ubuntu（systemd，root） |
| 容器运行时 | **k3s v1.30.x**（kubectl 可用，KUBECONFIG=`/etc/rancher/k3s/k3s.yaml`） |
| KubeEdge | cloudcore **v1.20.0**（手动 manifest 部署，无需 keadm） |
| 云端 IP | 默认 `172.19.134.45`（`CLOUD_IP` 可改） |
| 数据面端口 | MQTT **41883**（TCP）/ **41083**（WS）/ 仪表盘 **41500** |

> **端口规范（全局约定）**：本项目**服务端口一律使用 40000+**（如 41883/41083/41500），
> 被占用时 +1 递增避让，绝不回落到低位端口。
> 例外仅限 **KubeEdge 控制面官方保留端口 10000–10004**（CloudHub quic/https/cloudStream/websocket），
> 这是 KubeEdge 固定端口、非项目服务端口，边缘盒子 `keadm join` / `edgecore.yaml` 均按此接入，**不可迁移**。

---

## 1. 目录结构

```
cloud-deploy/
├── deploy_cloud.sh            # 云端一键部署脚本（幂等，支持子命令与自检）
├── kubeedge/                  # ── KubeEdge 云端控制面 ──
│   ├── gen_certs.sh           #   EC P-256 CA + server/stream 证书生成
│   └── cloudcore-all.yaml     #   cloudcore manifest 模板（{{CLOUD_IP}} 占位符）
├── datapath/                  # ── 能碳数据面（能碳一体机设备数据通道）──
│   ├── broker.py              #   amqtt MQTT Broker（TCP 41883 + WS 41083）
│   ├── collector.py           #   传感器数据落盘接收器（订阅 #）
│   ├── dashboard.py           #   Flask 数据仪表盘（41500）
│   ├── requirements.txt       #   数据面 Python 依赖
│   └── systemd/               #   三个 systemd 单元模板
│       ├── nengtan-cloud-broker.service
│       ├── nengtan-cloud-dashboard.service
│       └── nengtan-collector.service
└── agent/                     # ── 云端 agent（替代平台 SSH 数据通道）──
    ├── cloud_agent.py         #   零依赖 agent：MQTT 推送读 + HTTP 42083 写
    ├── install_agent.sh       #   一键安装（systemd 常驻）
    └── cloud-agent.service    #   systemd 单元（install_agent.sh 内嵌渲染）
```

## 2. 快速开始（全新云服务器）

```bash
# 0) 前提：k3s v1.30.x 已装、kubectl 可用、云端 IP 已规划
#    本机默认 IP 172.19.134.45，若不同请用环境变量覆盖
export CLOUD_IP=172.19.134.45

# 1) 完整部署（控制面 + 数据面 + agent）
sudo ./deploy_cloud.sh

# 2) 自检（不修改任何东西）
sudo ./deploy_cloud.sh --check
```

也可以分步：

```bash
sudo ./deploy_cloud.sh --control-only      # 仅 KubeEdge 控制面（cloudcore/CRD/防火墙）
sudo ./deploy_cloud.sh --datapath-only     # 仅数据面（broker/dashboard/collector + systemd）
sudo ./deploy_cloud.sh --agent-only        # 仅云端 agent（需数据面 broker 41883 已就绪）
sudo ./deploy_cloud.sh --check             # 链路自检
```

> **agent_token 说明**：完整/`--agent-only` 部署 agent 时，若 `/opt/cloud-agent/config.json`
> 已有 token 则复用（幂等），否则自动 `openssl rand -hex 24` 生成并打印。
> 该 token 需填入平台「云端 Broker 配置 → 云端 Agent → Agent Token」，
> 平台后端经 HTTP POST `http://<云端IP>:42083/api/...`（Bearer 认证）下发写操作。

## 3. 控制面做了什么（对应手册第 2 章）

1. **前置检查**：root、`kubectl` 可用、k3s 版本 ≤ 1.30（cloudcore v1.20.0 兼容上限）。
2. **生成 CA 与证书**（`kubeedge/gen_certs.sh`）：
   - CA 私钥**必须是 EC P-256**（`openssl ecparam -genkey -name prime256v1`），**绝不是 RSA**
     ——否则 cloudcore 启动报 `x509: failed to parse private key`（根因 `x509.ParseECPrivateKey`）。
   - server 证书 SAN 必须含云端 IP（`subjectAltName=IP:<CLOUD_IP>,DNS:cloudcore.kubeedge.svc`），否则边缘 mTLS 失败。
   - 证书预置在宿主机 `/etc/kubeedge`（manifest 用 hostPath 挂载，**不生成证书**）。
3. **应用 manifest**：`kubectl apply -f cloudcore-all.yaml`（渲染 `{{CLOUD_IP}}` 后）。
   - Deployment `hostNetwork: true`，cloudcore 直接监听宿主机 **10001(quic)/10002(https)/10003(cloudStream)/10004(websocket)**。
4. **Device CRD（v1beta1）**：若缺则下载 `devices_v1beta1.yaml` 并 apply（管理台依赖 v1beta1 的 `status.twins`）。
5. **防火墙**：放行 10001–10004/tcp（firewalld 优先，否则 iptables 兜底）。

> 部署后边缘盒子即可按手册第 3 章 `keadm join --cloudcore-ipport=<IP>:10002` 接入。

## 4. 数据面做了什么（对应手册 1.4）

- `broker.py`：amqtt MQTT Broker，监听 **41883（TCP）+ 41083（WS）**，允许匿名连接（平台/collector 均连它）。
- `collector.py`：订阅 `#` 的落盘接收器，把云端收到的设备数据按日写入 `/root/qzb/jianpai/data-terminal/collected/`。
- `dashboard.py`：Flask 数据仪表盘，**41500**，展示 broker 状态与最近数据。
- 三个服务注册为 systemd（`nengtan-cloud-*.service`），`enable` 开机自启 + `Restart=always`。
- Python 依赖装进 venv：`/root/qzb/jianpai/data-terminal/venv/`。

> 数据链路：边缘盒子 box-mapper/采集程序 → 云端 MQTT(41883) → 平台订阅 `data/#` 识别云端设备、同步读数；
> 同时 collector 落盘。与 cloudcore 控制面（10002/10004）相互独立。
>
> 本包附带的数据面三服务为**与线上行为一致的参考实现**；若已有参考工程
> `yunduan1/deploy_pkg/`（install.sh 一键安装的线上版本），可用环境变量
> `DATAPATH_SRC=/path/to/deploy_pkg` 让脚本优先复制参考工程源码覆盖本包默认实现。

## 5. 云端 agent 是什么

- **背景**：平台 ⇄ 云端的读数据链路已改为 **MQTT 长连接推送**（agent 本地 kubectl/openssl/ss 采集后
  按 30s/5s/3s 推 `cloud/state`/`cloud/crds`/`cloud/logs` 到云端 Broker，平台 mqtt_source 订阅解析缓存）；
  写操作（一键下发/删除/回写 twins/重启 Pod）由平台 **HTTP POST 42083**（Bearer token）打到 agent，
  agent 本地执行 `kubectl apply / delete / patch / rollout restart`。
- **不依赖 SSH**：agent 安装在云端本机（127.0.0.1 访问 kubectl），平台侧无需 root 凭据、无 22 端口暴露。
- **重启 CloudCore**：平台「云端实时日志」区块有「重启 CloudCore」按钮，调 `POST /api/restart`
  → agent 本地 `kubectl -n kubeedge rollout restart deploy/cloudcore`（滚动重启、服务不中断），
  用于 CloudCore 崩溃/卡死导致边缘级联卡死时快速恢复。

## 6. 常用运维命令

```bash
# 控制面
kubectl -n kubeedge get pods                                   # cloudcore-* Running
ss -tlnp | grep -E '1000[124]'                                 # hostNetwork 生效
kubectl -n kubeedge get secret tokensecret -o jsonpath='{.data.tokendata}' | base64 -d   # 取 24h token
# 数据面
systemctl status nengtan-cloud-broker nengtan-cloud-dashboard nengtan-collector
journalctl -u nengtan-collector --no-pager -n 20               # collector 落盘日志
tail -f /root/qzb/jianpai/data-terminal/collected/*.log         # 采集数据
# 云端 agent
systemctl status cloud-agent                                   # agent 常驻服务
journalctl -u cloud-agent --no-pager -n 20                     # agent 日志
curl -s -H "Authorization: Bearer <token>" http://127.0.0.1:42083/api/health   # 健康检查
```

## 7. 不含平台本身（本包范围之外）

| 组件 | 位置 | 说明 |
|---|---|---|
| 能碳平台（web 应用 + 管理台） | simulation 仓库（本仓库） | 平台后端订阅 `data/#` + `cloud/#`，经云端 agent（HTTP 42083）下发写操作，不在云端部署 |
| kubeedge-status 管理台 | `/opt/kubeedge-status/`（:41080） | KubeEdge 部署/管理台，部署流程见 `kubeedge-console-ops.md` 第 4 章 |

需要部署上述平台/管理台时，请按对应文档单独操作，本包不包含。

## 8. 常见问题（坑速查，详见 `kubeedge-console-ops.md` 2.9）

| 坑 | 现象 | 正确做法 |
|---|---|---|
| CA 用了 RSA | cloudcore 起不来，`x509: failed to parse private key` | 一律 `openssl ecparam -genkey -name prime256v1`（EC P-256） |
| server 证书缺 IP SAN | 边缘 mTLS：`certificate is valid for ... not <IP>` | 证书 SAN 加 `IP:<CLOUD_IP>` |
| 防火墙只放 k3s 层 | 边缘 token/CA 都对但一直 reconnect | 宿主机 firewalld/iptables 放 10001–10004；边缘 `nc -vz <IP> 10004` 验证 |
| 改 CA 后 token 失效 | 边缘 join 失败 | `kubectl delete secret tokensecret -n kubeedge` + 重启 cloudcore pod 重生成 |
| cloudStream 10003 不监听 | 不能 `kubectl logs/exec` 到边缘 pod | `gen_certs.sh --with-stream` 补 stream 证书后 `rollout restart` |
