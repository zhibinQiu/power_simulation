# 钢铁节能减碳数字孪生平台

一个面向**节能与减碳仿真**的钢铁生产工艺数字孪生平台，核心设计是**实时数据接入数字孪生**与**节能、减碳双目标仿真**（节能与减碳并重，不止关注碳排放）。核心能力：

1. **自然语言策略输入** —— 用中文/英文描述节能减碳策略，系统自动解析为结构化操作。
2. **实验仿真验证** —— 在应用前，先对策略做能碳仿真，对比基线 vs 策略的能耗、排放、吨钢强度、碳利用率。
3. **能碳流分析** —— 桑基图展示「碳输入 → 各工序 → CO₂排放 / 钢中固碳 / 捕集」的碳素流（tC/h）与「能源源 → 各工序 → 产品有效能 / 余热回收 / 损失」的能流（GJ/h）。
4. **最终应用策略** —— 一键把验证过的策略落到当前流程模型。
5. **模拟数据推送** —— 后端通过 WebSocket 持续推送带噪声的实时遥测，3D 场景热力图随直播数据轻微波动（能耗与碳排联动）。

> 当前为演示版本，数据均为**模拟值**（标定参考 ISO 14404 思路，非精确冶金数据），重点体现平台机制与能流/碳流向的相对关系。

## 技术架构

```
浏览器(Vue3 组件化)
   │  REST / WebSocket
   ▼
Python(FastAPI) 后端
   ├─ nl_parser      自然语言 → 结构化操作(确定性解析，离线可用)
   ├─ carbon_engine  按工序类型注册的能碳仿真引擎(自适应)
   ├─ store          策略库(内存 + JSON 持久化)
   └─ ws /api/ws/feed 模拟遥测推送
   └─ 静态托管 frontend/dist
```

**后端自适应原理**：流程被表达为 JSON 模型（工序 + 物流 + 参数）。碳排放计算是一张「工序类型 → 算法」的注册表（`carbon_engine.RULES`）。前端/自然语言改出来的任意流程，引擎读图自动计算，**无需改框架代码**。

## 目录结构

```
simulation/
├── backend/
│   ├── app/
│   │   ├── main.py          FastAPI 主程序 + REST/WS + 静态托管
│   │   ├── models.py        数据模型(工序/流程/策略/仿真结果)
│   │   ├── carbon_engine.py 能碳仿真引擎(注册表)
│   │   ├── nl_parser.py     自然语言策略解析器
│   │   ├── presets.py       默认长流程模型 + 工序工厂
│   │   └── store.py         策略库
│   ├── requirements.txt
│   └── run.sh
└── frontend/
    ├── src/
    │   ├── api/client.js       API/WS 客户端
    │   ├── stores/sim.js       Pinia 状态(单一事实源)
    │   ├── three/scene.js      Three.js 3D 孪生场景
    │   ├── components/         SceneViewer/HudBar/StrategyInput/
    │   │                       ExperimentPanel/CarbonSankey/ProcessList/StrategyLibrary
    │   └── App.vue
    ├── vite.config.js
    └── package.json
```

## 运行方式

### 方式一：一键（后端托管前端）
```bash
# 1. 后端
cd backend && ./run.sh            # 自动建 venv 并安装依赖，监听 8000

# 2. 前端构建（另开终端）
cd frontend && npm install && npm run build

# 浏览器打开 http://127.0.0.1:8000
```

### 方式二：前后端分离开发
```bash
cd backend && ./run.sh                                  # :8000
cd frontend && npm install && npm run dev               # :5173 (API 已代理到 8000)
```

## 自然语言策略示例

- `将 1#高炉 改为 氢冶金，并应用 碳捕集`
- `1#高炉 的 焦比 降到 360，喷煤 提高 15%`
- `新增 一座 电炉，并 删除 1#高炉`
- `应用 余热回收，应用 碳捕集`

支持：改工序类型、改参数（绝对值 / 百分比 / 相对表述）、增删工序、应用技术（碳捕集 / 余热回收 / 富氢喷吹）。

## 扩展方向

- 接真实数据源：把模拟遥测替换为 PLC/SCADA(OPC-UA)、IoT 网关、MES。
- 引擎升级：按 ISO 14404 做精确物料与能量平衡，增加更多工序/节能减碳技术类型（只需在 `RULES` 注册函数）。
- 解析升级：在 `nl_parser.py` 的 `llm_parse` 扩展点接入大模型，提升复杂长句的解析能力。
- 多情景对比 / 时间轴碳流动画 / 历史趋势库。
