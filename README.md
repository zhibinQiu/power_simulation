# 工业能碳智控平台

面向流程工业的 **Web 版工业数字孪生与能碳智控系统**：以 3D 孪生场景呈现全厂工艺，覆盖设备监测、碳素流仿真、碳排放核算、能耗计算与操作策略推荐四大能力，支持流程拖拽编排、自然语言策略生成、实时遥测与 AI 分析报告导出；配套**软硬一体的能碳一体机**，依托自研**云边协同**系统，支持设备模型快速建立与下发、AI 模型远程部署与盒子傻瓜式接入。

## 功能特性

- **3D 数字孪生场景**：20+ 种工艺工序模型，五种环境主题（虚空 / 工业 / 沙漠 / 城市 / 海滩），工序选中聚焦、热力图着色、物流粒子动画；
- **虚拟巡视**：场景内置四足巡检机器狗（第一/第三人称视角），W/S/A/D 移动、Z/X 转向、Shift 加速，带厂区碰撞；
- **碳素流仿真引擎**：后端按设备级物料平衡逐工序核算碳素流与排放，支持「先能后碳」能耗折算与碳排放核算；
- **自然语言策略解析**：LLM 优先、启发式回退的双引擎，把「焦比降低 5%」之类的目标解析为可执行参数操作；
- **流程编排**：拖拽式设计工艺流程图（节点/连线/小组/子编排），完成后自动生成 3D 场景布局；
- **策略管理**：系统预置策略、工艺绿色策略（可启用）、自定义策略三类，仿真模式实时对比基准与策略后差异；
- **参数扫描与守恒审计**：单工序参数敏感性分析、全流程碳素流守恒审计（碳输入 = 排 CO₂ + 固钢 + 入渣 + 捕集 + 产品携出）；
- **AI 优化模型**：内置强化学习（RL）/ 遗传算法（GA）/ 粒子群（PSO）三套在线自学习模型，随实时数据后台持续训练，输出碳强度最优的设备参数建议，支持自动化控制、版本管理与调优提醒；
- **数据视图**：全屏传感器历史数据表格（实时读数 / 均值 / 峰值 / 谷值 / 超限状态），替代 3D 场景快速核对全场数据；
- **碳市场实时行情**：内置「碳市场」视图，实时展示 CEA（全国碳市场配额）日K线蜡烛图与 CCER（自愿减排量）成交均价折线图，叠加线性回归走势预测与置信带，15 秒自动刷新；
- **市场快讯**：底部状态栏滚动播报中国煤炭交易网「市场快讯」（60 秒缓存，前端 5 分钟刷新），鼠标悬停暂停滚动以便细读；
- **实时遥测**：WebSocket 推送设备读数（默认「Mqtt 实时」数据源：后端订阅云端 MQTT Broker 获取真实读数，不生成模拟数据；亦支持自定义 WebSocket / HTTP 轮询），约 10 分钟环形缓冲 + 历史趋势；读数同步采用**关联制**：云端识别设备（能碳一体机盒子下）须在「视图 → 能碳一体机管理」中与仿真设备实例手动关联后才同步；
- **能碳一体机管理**（视图 → 能碳一体机管理）：集成参考项目 yunduan1 全部能力，六页签——总览（云端 Broker $SYS 实时统计 + 边缘节点 + CloudCore/证书演示）、设备管理（KubeEdge DeviceModel/Device 五协议 CRUD + YAML 生成，`config/box_devices.json`）、设备关联（云端设备 ↔ 仿真设备实例，`config/links.json`）、盒子接入（edgecore.yaml 模板渲染 + token/caHash + 部署命令，`config/edgecore.template.yaml`）、实时数据（Device.twins 真实读数 + 趋势 + 消息流 + 发测试消息）、接入指引（盒子采集 mapper / 部署包 / 诊断工具）；总体架构：云端（172.19.134.45）K3s 轻量 K8s + KubeEdge CloudCore 作为唯一控制平面；盒子边缘仅安装 EdgeCore（不部署 k3s-server，无本地控制平面），经 CloudHub 10002 端口长连接云端，边缘运行 Pod / mosquitto / box-mapper；
- **命令行交互中枢**：聊天 / 代码 / 规划三模式 + 孪生控制命令（run / sim / stop / patrol / view / edit …）；
- **AI 分析报告**：AI 生成或本地模板双引擎，报告标题、分析深度（精简/标准/深入）、附录表格可选，输出 Markdown + 分享页 HTML；
- **工艺属性内化配置**：参数运行空间（min/max/step）、设备量程、设备规格档位均在编排模式节点属性面板中直接调整，随方案持久化（节点自定义范围 > 设备规格 ranges > 默认范围），无独立全局配置入口；
- **欢迎页与活动栏**：启动欢迎页选择工作模式；类 VS Code 活动栏（资源管理器 / 搜索 / 场景 / 连接）快速切换左侧面板；
- **全局搜索**：按名称模糊搜索工序、物料、策略与设备，一键选中并联动检视器与 3D 聚焦；
- **连接管理**：连接面板集中展示各数据链路（模拟 / WebSocket / HTTP）的运行状态，可在线启停；
- **数据校准**：校准向导对监测设备的量程与系数进行可视化标定，标定结果即时应用于实时读数换算。

## 技术栈

| 端 | 技术 |
| --- | --- |
| 前端 | Vue 3（Composition API）+ Vite + Pinia + Three.js |
| 后端 | Python + FastAPI + Uvicorn |
| 通信 | REST API + WebSocket（`/api/ws/feed`） |
| 存储 | 内存缓存 + 本地文件（策略库、历史报告） |

## 快速开始

### 后端

```bash
cd backend
./config/run.sh        # 自动创建 .venv、安装依赖、启动 127.0.0.1:8010
```

若已手动建好虚拟环境：

```bash
cd backend
python3 -m venv .venv
./.venv/bin/pip install -r config/requirements.txt
./.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

### 前端

```bash
cd frontend
npm install
npm run dev            # 开发服务器，代理 /api 与 /api/ws 到后端
```

### 构建

```bash
cd frontend
npx vite build         # 产物输出至 dist/，由后端 Catch-all 路由托管
```

### Docker（可选）

根目录提供 `Dockerfile` 与 `docker-compose.yml`（应用源码以卷挂载，LLM 密钥等环境变量由 compose 注入）。

## 配置说明

所有后端配置文件统一放在 `backend/config/`：

| 文件 | 说明 |
| --- | --- |
| `requirements.txt` | Python 依赖清单 |
| `run.sh` | 后端启动脚本（自动建 venv + 安装依赖 + 启动 uvicorn） |
| `.env` | LLM 密钥等本地环境配置（**不提交版本库**） |
| `strategies.json` | 策略库持久化（自定义策略保存于此，不提交） |

> 运行所需 LLM 密钥：在 `backend/config/.env` 中按 `LLM_API_KEY=...`、`LLM_BASE_URL=...` 配置；未配置时策略解析与报告分析自动回退到本地确定性引擎，核心功能不受影响。

## 目录结构

```text
.
├── backend/
│   ├── app/                    # FastAPI 应用
│   │   ├── main.py             # 组合根（装配各业务域路由 + 核心仿真 REST + SPA 托管）
│   │   ├── api/                # 业务域路由模块（按业务域独立，便于迁移）
│   │   │   ├── box_router.py           # 能碳一体机管理（/api/box/*、/api/realtime/*）
│   │   │   ├── carbon_assets_router.py # 碳资产管理（碳市场行情/报告任务/报告分享页）
│   │   │   └── carbon_assistant.py     # 碳资产助手（报告生成 + 控排履约 + 碳合规）
│   │   ├── carbon_engine.py    # 碳素流仿真引擎（RULES 注册表 + 缓存）
│   │   ├── calculators.py      # 能耗折算与排放因子计算
│   │   ├── factors.py          # 排放因子表
│   │   ├── devices.py          # 监测设备库（活动数据来源）
│   │   ├── realtime.py         # WebSocket 遥测推送 + 历史 ring buffer
│   │   ├── nl_parser.py        # 自然语言 → 策略操作（启发式引擎）
│   │   ├── llm_strategy.py     # LLM 策略解析 / 命令行对话（可选）
│   │   ├── param_schema.py     # 工序参数分级元数据
│   │   ├── carbon_market.py    # 碳市场行情服务（CEA/CCER 行情拉取 + 缓存 + 预测）
│   │   ├── market_news.py      # 市场快讯服务（中国煤炭交易网爬取 + TTL 缓存）
│   │   ├── report.py           # AI 报告生成（骨架本地 + 分析 LLM）
│   │   ├── report_store.py     # 历史报告持久化
│   │   ├── md_render.py        # Markdown → HTML 分享页渲染
│   │   ├── presets.py          # 默认流程模型与示例策略
│   │   ├── optimizers.py       # AI 优化模型引擎（GA/PSO/RL 在线训练 + 版本管理）
│   │   ├── specs.py            # 设备规格档位
│   │   ├── store.py            # 策略持久化
│   │   └── models.py           # 前后端数据契约（Pydantic）
│   ├── config/                 # 统一配置目录（依赖/启动/密钥/本地覆盖）
│   └── data/reports/           # 历史报告输出
├── frontend/
│   ├── src/
│   │   ├── App.vue             # 主界面：顶栏菜单 / 活动栏 / 状态栏 / 3D 场景 / 检视器
│   │   ├── stores/             # Pinia 全局状态（sim.js 流程/仿真/实验；scan.js 扫描/审计）
│   │   ├── three/scene.js      # TwinScene 3D 场景（环境/巡检/热力图/物流动画）
│   │   ├── api/client.js       # REST / WebSocket 客户端
│   │   ├── utils/              # tft.js TFT 算法 / energy.js 能耗 / markdown.js 渲染
│   │   ├── data/               # 工序元数据、设备耦合推导、流程库
│   │   └── components/         # 界面组件（含内置「使用手册 / 技术文档」）
│   │       ├── WelcomeScreen.vue        # 启动欢迎页（模式选择）
│   │       ├── ActivityBar.vue          # 活动栏（资源管理器/搜索/场景/连接）
│   │       ├── StatusBar.vue            # 状态栏（遥测状态 + 市场快讯滚动）
│   │       ├── CarbonMarketView.vue     # 碳市场行情视图（K线/折线/预测）
│   │       ├── SearchPanel.vue          # 全局搜索面板
│   │       ├── ScenePanel.vue           # 场景控制面板
│   │       ├── ConnectionsPanel.vue     # 数据链路连接面板
│   │       ├── DataSourceDialog.vue     # 数据源配置（模拟/WebSocket/HTTP）
│   │       ├── SystemSettingsDialog.vue # 系统设置（布局/场景/链路/LLM）
│   │       ├── CalibrationWizard.vue    # 设备数据校准向导
│   │       ├── EnergySankey.vue         # 能流桑基图
│   │       ├── CarbonSankey.vue         # 碳流桑基图
│   │       └── ...                      # 其余界面组件（含「使用手册 / 技术文档」）
│   └── vite.config.js
├── cli-chat/                   # 命令行聊天辅助脚本
├── docs/                       # 设计文档（架构梳理、流程编排方案）
├── Dockerfile / docker-compose.yml
└── README.md
```

## 文档索引

- **使用手册**：应用内「帮助 → 使用手册」，按操作逻辑讲解界面分区、菜单、工具条、3D 场景、检视器、设备、策略、仿真、流程编排、命令行、碳市场、报告与快捷键；
- **技术文档**：应用内「帮助 → 技术文档」，讲解系统架构、碳素流仿真引擎、碳排放核算、能耗计算、设备库、自然语言解析、LLM 智能体、TFT 算法、设备耦合、实时遥测、数据契约、仿真协议、碳市场行情与市场快讯服务；
- **`docs/` 目录**：架构与业务逻辑梳理、可编辑流程编排方案（设计期文档）。

## 常见问题

- **点击导出报告提示「请先运行仿真」**：报告依赖仿真结果，先按 `Ctrl+Enter` 运行一次；
- **调节参数退出仿真后复原**：仿真模式所有修改仅预览，退出自动恢复；需保留请先「保存策略」；
- **命令行没反应**：确认首词为命令表内命令（`help` 查看全部）；非命令内容走自然语言对话；
- **碳市场无数据**：行情与快讯依赖外网数据源，断网时自动回退为内置模拟数据并在界面提示「模拟数据」，不影响其余功能；
- **找不到某个工序/策略**：点击左侧活动栏「搜索」图标打开全局搜索，输入名称即可定位并联动 3D 聚焦。
