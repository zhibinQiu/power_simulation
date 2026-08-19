# 行业能碳仿真平台

面向高炉炼铁的 **Web 版工业数字孪生仿真系统**：以 3D 孪生场景呈现全厂工艺，覆盖设备监测、碳素流仿真、碳排放核算、能耗计算与操作策略推荐四大能力，支持流程拖拽编排、自然语言策略生成、实时遥测与 AI 分析报告导出。

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
- **实时遥测**：WebSocket 推送设备读数（模拟数据源 / 自定义 WebSocket / HTTP 轮询三种数据源），约 10 分钟环形缓冲 + 历史趋势；
- **命令行交互中枢**：聊天 / 代码 / 规划三模式 + 孪生控制命令（run / sim / stop / patrol / view / edit …）；
- **AI 分析报告**：AI 生成或本地模板双引擎，报告标题、分析深度（精简/标准/深入）、附录表格可选，输出 Markdown + 分享页 HTML；
- **平台配置**：工艺规模档位、设备量程、参数运行空间可配置，保存后参数编辑器、设备面板与 3D 标注自动生效。

## 技术栈

| 端 | 技术 |
| --- | --- |
| 前端 | Vue 3（Composition API）+ Vite + Pinia + Three.js |
| 后端 | Python + FastAPI + Uvicorn |
| 通信 | REST API + WebSocket（`/api/ws/feed`） |
| 存储 | 内存缓存 + 本地文件（策略库、平台配置、历史报告） |

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
| `platform_config.json` | 平台可配置项覆盖：工艺规模档位 / 设备量程 / 参数运行空间（本地持久化，不提交） |
| `strategies.json` | 策略库持久化（自定义策略保存于此，不提交） |

> 运行所需 LLM 密钥：在 `backend/config/.env` 中按 `LLM_API_KEY=...`、`LLM_BASE_URL=...` 配置；未配置时策略解析与报告分析自动回退到本地确定性引擎，核心功能不受影响。

## 目录结构

```text
.
├── backend/
│   ├── app/                    # FastAPI 应用
│   │   ├── main.py             # 路由（REST + WebSocket + SPA 托管）
│   │   ├── carbon_engine.py    # 碳素流仿真引擎（RULES 注册表 + 缓存）
│   │   ├── calculators.py      # 能耗折算与排放因子计算
│   │   ├── factors.py          # 排放因子表
│   │   ├── devices.py          # 监测设备库（活动数据来源）
│   │   ├── realtime.py         # WebSocket 遥测推送 + 历史 ring buffer
│   │   ├── nl_parser.py        # 自然语言 → 策略操作（启发式引擎）
│   │   ├── llm_strategy.py     # LLM 策略解析 / 命令行对话（可选）
│   │   ├── param_schema.py     # 工序参数分级元数据
│   │   ├── platform_config.py  # 平台可配置项（规模/量程/参数空间）
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
│   │   ├── App.vue             # 主界面：顶栏菜单 / 3D 场景 / 检视器
│   │   ├── stores/             # Pinia 全局状态（sim.js 流程/仿真/实验；scan.js 扫描/审计）
│   │   ├── three/scene.js      # TwinScene 3D 场景（环境/巡检/热力图/物流动画）
│   │   ├── api/client.js       # REST / WebSocket 客户端
│   │   ├── utils/              # tft.js TFT 算法 / energy.js 能耗 / markdown.js 渲染
│   │   ├── data/               # 工序元数据、设备耦合推导、流程库
│   │   └── components/         # 界面组件（含内置「使用手册 / 技术文档」）
│   └── vite.config.js
├── cli-chat/                   # 命令行聊天辅助脚本
├── docs/                       # 设计文档（架构梳理、流程编排方案）
├── Dockerfile / docker-compose.yml
└── README.md
```

## 文档索引

- **使用手册**：应用内「帮助 → 使用手册」，按操作逻辑讲解界面分区、菜单、工具条、3D 场景、检视器、设备、策略、仿真、流程编排、命令行、报告与快捷键；
- **技术文档**：应用内「帮助 → 技术文档」，讲解系统架构、碳素流仿真引擎、碳排放核算、能耗计算、设备库、自然语言解析、LLM 智能体、TFT 算法、设备耦合、实时遥测、AI 优化模型引擎、数据契约与仿真协议；
- **`docs/` 目录**：架构与业务逻辑梳理、可编辑流程编排方案（设计期文档）。

## 常见问题

- **点击导出报告提示「请先运行仿真」**：报告依赖仿真结果，先按 `Ctrl+Enter` 运行一次；
- **调节参数退出仿真后复原**：仿真模式所有修改仅预览，退出自动恢复；需保留请先「保存策略」；
- **命令行没反应**：确认首词为命令表内命令（`help` 查看全部）；非命令内容走自然语言对话。
