<template>
  <div class="td-mask" @click.self="$emit('close')">
    <div class="td-modal" role="dialog" aria-modal="true" aria-label="技术文档">
      <div class="td-head">
        <span class="td-title">技术文档 · 系统技术架构与算法详解</span>
        <button class="td-x" @click="$emit('close')" aria-label="关闭">×</button>
      </div>

      <div class="td-body">
        <nav class="td-toc">
          <div class="td-toc-title">目 录</div>
          <button v-for="(s, i) in sections" :key="s.id" class="td-toc-item"
                  :class="{ on: active === s.id }" @click="go(s.id)">
            <span class="td-toc-num">{{ i + 1 }}</span>{{ s.title }}
          </button>
        </nav>

        <div class="td-scroll" ref="scrollEl" @scroll="onScroll">
          <section v-for="s in sections" :key="s.id" :id="s.id" class="td-sec">
            <div class="td-md" v-html="renderMarkdown(s.body)"></div>
          </section>
          <div class="td-foot">—— 文档完 ——</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { renderMarkdown } from '../utils/markdown'

const emit = defineEmits(['close'])
const scrollEl = ref(null)
const active = ref('')

const sections = [
  {
    id: 'arch',
    title: '系统技术架构',
    body: `# 行业能碳仿真平台 · 技术文档

本平台是面向高炉炼铁的数字孪生仿真系统，覆盖设备监控、碳素流仿真、碳排放核算与操作策略推荐四大能力。

## 一、总体架构

系统采用「前端可视化 + 后端计算引擎」的前后端分离架构：

| 层级 | 技术栈 | 职责 |
| --- | --- | --- |
| 前端 | Vue 3（Composition API）+ Vite + Pinia + Three.js | 3D 场景渲染、流程编排、实时遥测、策略提示 |
| 后端 | Python + FastAPI + Uvicorn | 碳素流仿真、碳排放核算、策略解析、报告生成 |
| 通信 | REST API + WebSocket | 实时遥测下发、仿真结果回传 |
| 存储 | 内存缓存 + 本地文件（报告存储） | 仿真缓存、策略库、历史报告 |

## 二、目录结构

\`\`\`text
frontend/src/
  ├─ App.vue              # 主界面：顶栏菜单 / 活动栏 / 状态栏 / 3D 场景 / 检视器
  ├─ stores/sim.js        # Pinia 全局状态（流程、仿真、实验、撤销重做、活动栏/数据源/视图开关）
  ├─ stores/scan.js       # 参数扫描与守恒审计状态
  ├─ utils/               # tft.js TFT算法 / energy.js 能耗 / markdown.js 渲染
  ├─ data/flowLibrary.js  # 设备耦合推导 deriveProcessOpParams
  ├─ three/scene.js       # TwinScene 3D 场景（环境/巡检/热力图/物流动画）
  ├─ api/client.js        # REST / WebSocket 客户端
  ├─ composables/         # useGlobalShortcuts 全局快捷键 / contextMenu 上下文菜单
  └─ components/          # 界面组件（见「前端可视化与交互」章节完整清单）

backend/
  ├─ app/
  │  ├─ main.py              # FastAPI 路由（REST + WebSocket + SPA 托管）
  │  ├─ carbon_engine.py     # 碳素流仿真引擎（RULES 注册表 + 缓存）
  │  ├─ calculators.py       # 能耗折算与排放因子计算
  │  ├─ factors.py           # 排放因子表
  │  ├─ devices.py           # 监测设备库（活动数据来源）
  │  ├─ realtime.py          # WebSocket 遥测推送 + 历史 ring buffer
  │  ├─ nl_parser.py         # 自然语言 → 策略操作（启发式）
  │  ├─ llm_strategy.py      # LLM 策略解析/对话（可选，无 Key 自动回退）
  │  ├─ param_schema.py      # 工序参数分级元数据
  │  ├─ carbon_market.py     # 碳市场行情服务（CEA/CCER 拉取 + TTL 缓存 + 价格预测）
  │  ├─ market_news.py       # 市场快讯服务（中国煤炭交易网爬取 + TTL 缓存）
  │  ├─ report.py            # AI 报告生成（骨架本地 + 分析 LLM）
  │  ├─ report_store.py      # 历史报告持久化
  │  ├─ md_render.py         # Markdown → HTML 分享页渲染
  │  ├─ presets.py           # 默认流程模型与示例策略
  │  ├─ optimizers.py        # AI 优化模型引擎（GA/PSO/RL 在线训练 + 版本管理）
  │  ├─ specs.py             # 设备规格档位
  │  ├─ store.py             # 策略持久化
  │  └─ models.py            # 前后端数据契约（Pydantic）
  ├─ config/                 # 统一配置目录：requirements.txt / run.sh / .env（LLM 密钥，不入库）/ strategies.json
  └─ data/reports/           # 历史报告输出

## 三、数据流

\`\`\`
设备遥测(WS) ──► 前端状态(Pinia) ──► 设备耦合推导(deriveProcessOpParams)
      │                                       │
      └──► 3D 场景 / 检视器 ◄── 仿真结果 ──► 后端碳素流引擎 / 碳排核算
                                                │
                                                └──► TFT 焓平衡 → 策略提示
\`\`\`

核心设计原则：**前端负责交互与可视化，后端负责守恒计算；所有设备调节均先走耦合推导再进入仿真，保证操作前后参数自洽。**`,
  },
  {
    id: 'carbon-flow',
    title: '碳素流仿真引擎',
    body: `## 碳素流仿真引擎

后端 \`carbon_engine.py\` 采用**设备级物料平衡**方法，通过规则注册表（RULES）驱动，逐设备核算碳素流与排放。

## 一、规则注册表机制

系统将所有核算规则集中注册，按「工序类型 → 计算函数」组织：

\`\`\`js
RULES: {
  sinter_plant:  烧结机核算（矿/燃料碳入 → CO2 排放 + 烧结矿带碳）
  blast_furnace: 高炉核算（焦炭/喷煤碳入 → 铁水渗碳 + 煤气带碳 + CO2）
  bof:           转炉核算（铁水碳 → 钢水固碳 + 炉气 CO2）
  ...
}
\`\`\`

每个工序的核算都遵循统一输出契约 \`UnitResult\`：
- \`carbon_in\`：tC/h 入炉碳；
- \`carbon_to_co2\`：tC/h 以 CO2 排出（燃烧 + 分解）；
- \`carbon_to_steel\`：tC/h 固结于钢（扣除项）；
- \`carbon_captured\`：tC/h 被捕集（CCS，碳捕集与封存，扣减项）；
- \`breakdown\`：核算明细台账（每项含 qty / basis / formula / co2）。

## 二、核算边界与守恒

- **总碳守恒**：入炉碳（焦炭 + 喷煤 + 炉料）恒等于 出铁碳 + 炉渣碳 + 炉顶煤气碳 + 捕集碳；
- **设备输入输出**：每个设备节点只允许「入口碳 = 出口碳 ± 变化量」，保证流经可追踪；
- **排放统计**：按范围一（燃烧/工艺/分解直接排放）与范围二（外购电间接排放）分类，汇总得到整炉碳排放强度（kgCO₂/t）；
- **碳利用率** \`carbon_utilization\`：固碳量 / 输入碳，用于衡量碳的利用效率。

## 三、缓存与性能

- 设备参数采用 **LRU（最近最少使用）缓存**（\`cached_simulate\`）：相同输入不重复计算，连续重复仿真（前端轮询/防抖后请求）命中缓存；
- 诊断端点 \`GET /api/cache/stats\` 返回缓存命中率；
- 计算粒度到设备级，支持单设备调节后快速重算（增量刷新）。

## 四、能耗输出（先能后碳）

引擎在碳核算之外同步输出能耗字段，遵循「先能后碳」主题：
- \`elec\`：MWh/h 电耗（外购电）；
- \`fuel_energy\`：GJ/h 燃料能耗（燃料燃烧低位热值之和）；
- \`energy_total\`：GJ/h 综合能耗（燃料 + 电折标，1 MWh = 3.6 GJ）；
- \`energy_intensity\`：kgce/t 单位产品综合能耗（综合能耗 × 34.12 / 主产物产量）。`,
  },
  {
    id: 'co2',
    title: '碳排放核算方法',
    body: `## 碳排放核算方法

依据 **GB/T 32151.5《钢铁生产企业温室气体排放核算方法与报告指南》** 与 **GHG Protocol**，采用**物料平衡法 + 排放因子法**相结合，活动数据来自监测设备，因子可配置。

## 一、排放源分类与范围

| 排放源 | 归属 | 说明 | 计算方法 |
| --- | --- | --- | --- |
| 燃料燃烧排放 | 范围一（直接） | 焦炭、煤粉、煤气、重油燃烧 | 活动数据 × 单位热值 × 含碳率 × 3.667 |
| 原材料分解排放 | 范围一（直接） | 石灰石/白云石分解 | 碳酸盐量 × 化学计量 |
| 工艺排放 | 范围一（直接） | 铁水渗碳、炉渣带走碳 | 产出量 × 含碳率 |
| 间接排放 | 范围二（间接） | 外购电力/热力 | 购入量 × 电网排放因子 |
| 扣减项 | 减排 | CCS（碳捕集与封存）捕集、余热回收、富氢替代 | 实际捕集/回收量扣减 |

## 二、碳排放台账（LedgerItem）

每个工序的排放结果附带**核算明细台账** \`breakdown\`，把「用了什么、因子多少、贡献多少 CO₂」逐项讲清楚：

\`\`\`text
item:    焦炭（入炉）
qty:     3360 t/h
basis:   NCV（低位发热量） 28.435 GJ/t × CC（单位热值含碳量） 0.0295 tC/GJ × 3.667
formula: 3360 × 28.435 × 0.0295 × 3.667 = 10331 tCO₂/h
co2:     10331
scope:   direct
\`\`\`

该结构使**每一个数字都可追溯**，满足审计与报告要求。

## 三、排放因子体系

默认因子表 \`factors.py\` 提供：
- **燃料参数**：NCV（低位发热量）、CC（单位热值含碳量）——焦炭、煤粉、天然气、BFG（高炉煤气）等；
- **电网因子**：外购电力排放因子；
- **碳酸盐/电极因子**：石灰石分解、电极消耗；
- 前端「数据」面板可查看因子表，仿真请求可携带自定义 \`factors\` 覆盖默认值。

## 四、技术修正项

- **CCS（碳捕集与封存）**：炉顶煤气中 CO₂ 捕集量从总排放中扣除；
- **余热回收**：回收热量折抵燃料燃烧排放；
- **富氢喷吹**：氢替代部分碳，降低碳素消耗，按氢还原份额折算减排量。

平台在右侧检视器 / 分析报告中展示各分项碳流占比与排放强度趋势。`,
  },
  {
    id: 'energy',
    title: '能耗计算（先能后碳）',
    body: `## 能耗计算（先能后碳）

节能减碳主题下平台遵循「**先能后碳**」：先核算能耗，再核算碳排放。能耗计算与后端 \`factors._energy_of\` 同源，前端 \`utils/energy.js\` 保持实现一致。

## 一、能耗构成

| 项目 | 单位 | 来源 |
| --- | --- | --- |
| 电耗 elec | MWh/h | 外购电力（智能电表活动数据） |
| 燃料能耗 fuel_energy | GJ/h | 燃料燃烧低位热值之和 |
| 综合能耗 energy_total | GJ/h | 燃料 + 电折标（1 MWh = 3.6 GJ） |
| 能耗强度 energy_intensity | kgce/t | 综合能耗 × 34.12 / 主产物产量 |

## 二、折标系数

\`\`\`js
// frontend/src/utils/energy.js
const CC_FUEL = { coke: 0.0295, coal: 0.0262, ng: 0.0153 }  // tC/GJ
const GJ_PER_MWH = 3.6     // 电折热
const KGCE_PER_GJ = 34.12  // 热折标煤（kgce/GJ）

// 由碳素流反推燃料能耗（当后端未直接返回时）：
fuel = carbon_by_fuel[k] / CC_FUEL[k]   // GJ/h
total = fuel + elec × 3.6
intensity = steel > 0 ? total × 34.12 / steel : 0
\`\`\`

前端优先采用后端返回的 \`energy_total / elec / fuel_energy / energy_intensity\` 字段；缺失时由台账 + 碳素流反推，保证离线与在线结果一致。

## 三、典型工艺能耗参考

- 高炉：燃料能耗占绝对主导（焦炭 + 喷煤），电耗为辅；
- 电炉（EAF，电弧炉）：电耗主导，燃料极少；
- 氢基直接还原：氢燃料能耗 + 电耗混合。`,
  },
  {
    id: 'devices',
    title: '监测设备库与活动数据',
    body: `## 监测设备库与活动数据

碳排放是**因变量**，由「活动数据（自变量）× 排放因子（系数）」算出。活动数据来自现场监测设备。

## 一、设备类型库（DEVICE_LIBRARY）

平台内置 8 类标准监测设备：

| 设备 | 测量对象 | 用途 |
| --- | --- | --- |
| 皮带秤 belt_scale | 固体质量流量 t/h | 矿、焦、煤、烧结矿等，碳核算「活动数据」主源头 |
| 失重秤 loss_in_weight | 粉料/喷吹质量 t/h | 高炉喷吹煤粉、熔剂精确给料 |
| 料斗秤 hopper_scale | 批料质量 t/批 | 焦比、喷煤比、熔剂比单耗实测 |
| 钢水/铸坯秤 weigher | 产品/半产品质量 t/h | 钢中固碳扣减与产量统计 |
| 气体流量计 gas_flowmeter | 气体体积流量 m³/h | BFG（高炉煤气）/LDG（转炉煤气）/天然气/氧气，燃料类直接排放活动数据 |
| 智能电表 power_meter | 电功率 MWh/h | 范围二（外购电）间接排放 |
| 成分分析仪 composition_analyzer | 物料成分/品位 | 精化排放因子（替代默认 CC 假设） |
| CEMS（烟气连续排放监测系统） cems | CO₂ 浓度×流量 | 点源直接监测法，因子法交叉校验 |

## 二、工序设备规格（_UNIT_DEVICE_SPECS）

每个工序按工艺挂载一组设备实例，每台设备声明：
- \`dev\`：设备类型；\`mount\`：3D 图挂载方位（feed/fuel/power/control）；
- \`measured\`：实测量中文说明；\`feeds\`：喂给引擎的输入/公式说明。

例如烧结机挂载：智能电表·主抽（喂 \`electricity\`）、成分分析仪·烧结矿（精化因子）。

## 三、检测设备去重原则

检测设备（只读监测）与**可调设备**（设定值 SP→测定值 PV）各有分工。若某检测设备监测的物理量恰为同工序可调设备的测定值，则该检测设备**不再内置**，避免双源数据冲突。平台仿真计算统一以可调设备**设定值为准**（输入框中的数字即工况值），测定值仅保留用于数据建模与真实 SCADA（数据采集与监视控制系统）场景。已去除的冗余检测设备包括：

- 烧结 / 球团 / 焦化的**皮带秤**（物料/燃料流量）→ 由 皮带机、给料机 的测定值覆盖；
- 高炉的**失重秤·喷吹煤**（喷吹煤粉量）→ 由 喷吹系统 的喷吹速率覆盖；
- 电炉 / 精炼炉的**智能电表**（电弧加热电耗）→ 由 电极调节器 的电弧功率覆盖。

保留的检测设备监测的均非可调设备测定值：气体流量计（煤气/天然气产量）、钢水秤/铁水秤（产量）、料斗秤（熔剂）、成分分析仪、CEMS（烟气连续排放监测系统），以及无电极调节器工序（烧结主抽/造球辊/炼焦/鼓风除尘/吹炼/电解制氢/结晶拉矫/轧制/压球压缩）的智能电表等。

## 四、模拟读数生成

\`compute_device_readings\` 依据工序活动数据生成模拟读数（\`reading\` 字段随仿真结果下发）。**接入真实工厂时，只需将该函数替换为读取 SCADA（数据采集与监视控制系统）/ EMS（能源管理系统）实测值**，其余管线不动。`,
  },
  {
    id: 'nlp',
    title: '自然语言策略解析',
    body: `## 自然语言策略解析

后端 \`nl_parser.py\` 将用户用自然语言描述的操作目标解析为**可执行的策略参数调整**，支持**双引擎**：LLM 引擎优先（需 API Key），失败自动回退确定性启发式引擎。

## 一、解析流程

\`\`\`
自然语言 ──► 分词/关键词匹配（LLM 或启发式）──► 操作拆解(5类) ──► 约束校验
      ──► ParsedOp 列表 ──► apply_ops 应用到流程 ──► 仿真对比
\`\`\`

## 二、五类操作（ParsedOp.action）

| 操作 | 语义 | 示例 |
| --- | --- | --- |
| replace_type | 工序换型 | 「高炉 改为 氢冶金」 |
| add_unit | 新增工序 | 「新增 一座 电炉」 |
| remove_unit | 删除工序 | 「删除 高炉」 |
| set_param | 修改参数 | 「焦比 降到 360」「喷煤 提高 15%」（absolute / relative 两种模式） |
| apply_tech | 应用技术 | 「应用 碳捕集」「应用 余热回收」 |

每条操作附带 \`note\`（给人看的自然语言描述）与 \`mode\`（absolute=绝对 / relative=相对百分比）。

## 三、关键词体系

- **工序关键词** UNIT_KEYWORDS：烧结机、高炉、转炉、电炉、氢基直接还原、熔融还原等 20 种；
- **参数关键词** PARAM_KEYWORDS：焦比、喷煤比、富氧率、热风温度、风量、矿比等 18 项；
- **技术关键词** TECH_KEYWORDS：碳捕集（ccs）、余热回收（waste_heat）、富氢喷吹（h2_inj）。

## 四、置信度

\`\`\`python
confidence = min(1.0, 0.4 + 0.15 × 操作数)
\`\`\`

识别到 1 个操作置信度 0.55，4 个以上即 1.0；无法解析时返回 warnings 提示，不下发空策略。

## 五、约束校验

解析结果必须通过设备可调域与耦合一致性校验后方可下发执行，防止出现「降温却提风温」等矛盾策略。`,
  },
  {
    id: 'llm',
    title: 'LLM 智能体与 AI 报告',
    body: `## LLM 智能体与 AI 报告

平台在核心守恒计算**绝不依赖大模型**的前提下，用 LLM 增强两处**分析类**能力：策略解析与报告解读。

## 一、LLM 策略解析（llm_strategy.py）

- \`llm_parse\`：用结构化 Prompt 让 LLM 把自然语言拆解为 \`ParsedOp\` 列表；
- 无 API Key / 超时 / 输出异常 → **自动回退启发式引擎**（nl_parser），保证离线可用；
- 返回 \`engine: "llm" | "heuristic"\` 标记实际使用的引擎。

## 二、AI 报告生成（report.py）——双引擎架构

\`\`\`python
_ENGINE_LLM = "llm"        # LLM 分析段落
_ENGINE_TEMPLATE = "template"  # 确定性模板回退
\`\`\`

**核心原则：报告骨架与所有数值表格由本地代码生成（数字精确、可复现、无幻觉）；执行摘要 / 数据洞察 / 策略效果评估 / 优化建议等分析段落由 LLM 基于给定数据撰写。**

- LLM 只负责「解读与建议」，不参与数字计算；
- 无 Key / 超时 / 输出异常时自动回退确定性文案。

## 三、报告生成流程（异步任务）

1. 前端提交 \`POST /api/report\`（baseline / strategy / 参数配置）；
2. 后端**后台线程**执行，按段回调进度（\`progress_cb\`）；
3. 前端轮询 \`GET /api/report/task/{id}\` 获取 \`{done, progress, stage, result}\`；
4. 完成后写入历史库（\`report_store\`），返回分享 URL。

## 四、报告配置项

| 配置 | 取值 | 说明 |
| --- | --- | --- |
| engine | auto / llm / template | 分析段落引擎 |
| depth | brief / standard / deep | 详细程度分级 |
| with_appendix | true/false | 是否含「附录：全流程明细」 |
| title | 自定义 | 空则自动拼接「策略名 · 场景」 |

## 五、报告分享页

\`GET /report/{rid}\` 将历史报告 Markdown 渲染为**独立 HTML 分享页**（新标签页查看/打印），可分享给他人审阅。`,
  },
  {
    id: 'tft',
    title: 'TFT 理论燃烧温度算法',
    body: `## TFT 理论燃烧温度焓平衡算法（含讲解实例）

TFT（Theoretical Flame Temperature，理论燃烧温度）是高炉风口回旋区燃烧热状态的量化指标。本平台采用**焓平衡 + 氧限制**方法计算，支持焦炭、喷煤、重油、煤气等固/液/气多燃料混合燃烧场景。

## 一、物理模型与边界假设

在风口回旋区，鼓风中的氧与燃料在高温下发生**缺氧不完全燃烧**，主要产物为 CO 与 H2O：

- 碳的燃烧为 **C → CO**（非 C → CO2），每 kgC 放出 **9.79 MJ** 热量；
- 氢的燃烧为 **H → H2O**，每 kgH 放出 **120 MJ** 热量；
- 缺氧环境下氢并非全部燃烧，仅按比例 \`hCombRatio\`（默认 0.6）燃烧，其余氢以 H2 形式进入炉缸煤气；
- 燃料中原生 CO 不参与二次燃烧；
- **鼓风氧是燃烧耗氧的唯一来源**，燃料碳氢超出鼓风氧供给能力的部分视为未燃，不计放热与产气（避免 TFT 虚高）。

## 二、算法常量（TFT_CONST）

\`\`\`js
const TFT_CONST = {
  Q_C_CO: 9.79,      // C→CO 燃烧热 MJ/kgC
  Q_H_H2O: 120,      // H→H2O 燃烧热 MJ/kgH
  V_CO_PER_C: 1.867, // C→CO 产气系数 Nm³/kgC（1 kgC = 83.33 molC → 1.867 Nm³CO）
  V_H2O_PER_H: 11.2, // H→H2O 产气系数 Nm³/kgH（1 kgH = 0.5 kmolH2 → 11.2 Nm³H2O）
  Q_CH4: 35.88,      // CH4 燃烧热 MJ/Nm³
  Q_C2H6: 63.74,     // C2H6 燃烧热 MJ/Nm³
}
\`\`\`

## 三、默认工况参数（TFT_PARAM_DEFAULTS）

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| hot_blast_temp | 1250 ℃ | 热风温度 |
| wind_rate | 600 kNm³/h | 风量（绝对供风量） |
| oxygen_enrich | 0 % | 富氧率（富氧增量） |
| hot_metal | 8000 t/h | 铁水产量 |
| coke_rate | 360 kg/tFe | 焦比 |
| coal_inj | 150 kg/tFe | 喷煤比 |

工况标定：物理比风量基准 = blastNominal / metalNominal（默认 40000 / 40 = **1000 Nm³/tFe**，行业典型值）。

其中 **40 tFe/h 是归一化标定基准**，仅用于把鼓风量换算成"每吨铁"的比风量，并非系统产量；系统实际产量为 8000 t/h。TFT 为温度指标，只取决于比风量、富氧率、风温、燃料配比等每吨铁的相对量，与产量绝对值无关，故讲解实例直接取标定基准 40 tFe/h 手算，与系统 8000 t/h 工况为同一比风量、同一结果。

## 四、焓平衡方程与变量说明

TFT 的物理意义：假设风口燃烧放出的热量**全部**用于加热生成的炉腹煤气（无散热、无对外做功），煤气所能达到的温度。这是热力学第一定律 Q = m·cp·ΔT 的反推——把煤气视作从 0℃ 被加热到 TFT，故 ΔT = TFT：

\`\`\`
TFT = Q_total_in / (V_gas_total × cp)
\`\`\`

| 变量 | 中文含义 | 单位 | 计算来源 |
| --- | --- | --- | --- |
| TFT | 理论燃烧温度：燃烧放热全部转化为煤气显热时煤气能达到的温度 | ℃ | Q_total_in ÷ (V_gas_total × cp) |
| Q_total_in | 风口回旋区总收入热（鼓风显热 + 燃烧放热） | MJ/tFe | Q_sensible_air + Q_combustion |
| V_gas_total | 炉腹煤气总量（CO + H2O + H2 + 惰性组分 + 鼓风 N2） | Nm³/tFe | V_CO + V_H2O + V_H2 + V_inert + V_N2_blast（见本节分母构成） |
| cp | 炉腹煤气定压比热：1 Nm³ 煤气升温 1℃ 所需热量 | MJ/(Nm³·℃) | 默认 0.0015，可随煤气组分微调 |

**分子（收入热）各项：**

| 变量 | 中文含义 | 单位 | 计算来源 |
| --- | --- | --- | --- |
| Q_sensible_air | 鼓风显热：热风本身携带的物理热，随鼓风带入炉内 | MJ/tFe | B × cpAir × t_blast |
| B | 比风量：每吨铁水对应的鼓风量，是整条计算链路的"脊柱" | Nm³/tFe | 标定基准 1000 × wind_rate/600（风量 kNm³/h，600 = 相对 1.0） |
| cpAir | 鼓风（空气）定压比热 | MJ/(Nm³·℃) | 默认 0.0013 |
| t_blast | 热风温度（对应系统参数 hot_blast_temp） | ℃ | 默认 1250 |
| Q_combustion | 燃料燃烧净放热 = 碳燃烧放热 + 氢燃烧放热 - 热解吸热 + 气体燃料放热 | MJ/tFe | C_burn×9.79 + H_total×120×hCombRatio - decomp_heat + Q_gas_fuel |
| C_burn | 实际燃烧的碳量（受鼓风氧限制，见 §五） | kgC/tFe | min(C_total, C_burnable) |
| H_total | 固/液燃料带入的氢总量 | kgH/tFe | Σ(用量 × 含氢率) |
| hCombRatio | 氢的燃烧比例：缺氧下仅部分氢烧成 H2O，其余以 H2 直接进炉腹煤气 | 无量纲 | 默认 0.6 |
| decomp_heat | 燃料热解吸热：喷吹燃料入炉先分解吸热 | MJ/tFe | Σ(用量 × 单位热解吸热) |
| Q_gas_fuel | 气体燃料（如焦炉煤气）燃烧放热，无气体燃料时为 0 | MJ/tFe | Σ(组分体积 × 组分燃烧热) |

**分母（炉腹煤气）构成：**

| 变量 | 中文含义 | 单位 | 计算来源 |
| --- | --- | --- | --- |
| V_CO | 燃烧生成的 CO 量 | Nm³/tFe | V_CO_solid × burnRatio + V_CO_gas |
| V_H2O | 燃烧生成的 H2O 量 | Nm³/tFe | V_H2O_solid × hCombRatio + V_H2O_gas |
| V_H2 | 未燃烧的 H2 量（直接进炉腹煤气） | Nm³/tFe | V_H2O_solid × (1 - hCombRatio) |
| V_inert | 燃料自带的 N2、CO2 等惰性组分 | Nm³/tFe | Σ(燃料惰性组分 × 用量) |
| V_N2_blast | 鼓风带入的 N2（占空气约 79%，不燃烧但同样被加热） | Nm³/tFe | B × N2_blow |

## 五、燃烧份额：鼓风氧限制

碳能烧多少**不由燃料决定，而由鼓风氧决定**。鼓风是回旋区唯一的氧源：氧先供氢燃烧，剩余氧再供碳燃烧，超出氧供给能力的碳视为未燃（不计放热、不计产气）：

\`\`\`
V_O2_blast = B × O2_blow                         // 鼓风总氧，Nm³/tFe
O2_for_H = 0.5 × V_H2O_solid × hCombRatio        // 氢燃烧耗氧
O2_for_C_avail = max(0, V_O2_blast - O2_for_H)   // 剩余氧供碳
C_burnable = O2_for_C_avail / 0.9333             // 氧可支撑的碳燃烧量，kgC/tFe
C_burn = min(C_total, C_burnable)                // 实际燃烧碳
burnRatio = C_burn / C_total                     // 碳燃烧份额
\`\`\`

| 变量 | 中文含义 | 单位 | 计算来源 |
| --- | --- | --- | --- |
| O2_blow | 鼓风绝对氧浓度 = 空气氧 21% + 富氧增量 | 体积分数 | 0.21 + 0.01 × wO |
| wO | 富氧率：相对空气 21% 的提升量（系统口径） | % | 默认 0，范围 0~14 |
| N2_blow | 鼓风氮气浓度（惰性，不燃烧但被加热吸热） | 体积分数 | 1 - O2_blow |
| V_O2_blast | 每吨铁的鼓风总氧量 | Nm³/tFe | B × O2_blow |
| V_H2O_solid | 固/液燃料氢若全部燃烧的理论 H2O 产气 | Nm³/tFe | 11.2 × H_total |
| O2_for_H | 氢按 hCombRatio 燃烧所消耗的氧 | Nm³/tFe | 0.5 × V_H2O_solid × hCombRatio |
| O2_for_C_avail | 扣除氢耗氧后、可供碳燃烧的剩余氧 | Nm³/tFe | max(0, V_O2_blast - O2_for_H) |
| 0.9333 | 每 kgC 燃烧成 CO 的耗氧量（1 kgC = 83.33 mol，需 41.67 mol O2） | Nm³ O2/kgC | 常数 |
| C_burnable | 鼓风氧最多能支撑燃烧的碳量 | kgC/tFe | O2_for_C_avail ÷ 0.9333 |
| C_total | 固/液燃料总碳（焦炭碳 + 煤粉碳） | kgC/tFe | Σ(用量 × 含碳率) |
| C_burn | 实际燃烧碳量（总碳与氧能力的较小者） | kgC/tFe | min(C_total, C_burnable) |
| burnRatio | 碳燃烧份额：实际燃烧碳占总碳的比例 | 无量纲 | C_burn ÷ C_total |

每 kgC 生成 1.867 Nm³ CO 需耗 0.9333 Nm³ O2；每 kgH 燃烧成 H2O 需耗 0.5 Nm³ O2 / Nm³ H2O。

## 六、比风量在计算中的作用：同时控制分子与分母

比风量 B（Nm³/tFe）即"每吨铁的送风强度"，从两个方向同时影响 TFT：

| 通道 | 机制 | 对 TFT 的影响 |
| --- | --- | --- |
| 供氧（分子） | B 越大 → V_O2_blast 越大 → 可烧碳越多 → 燃烧放热越多 | 升温 |
| N2 稀释（分母） | B 越大 → V_N2_blast 越大 → 惰性 N2 吸热越多 → 煤气总量越大 | 降温 |

不富氧时两条通道几乎相互抵消（风量翻倍，供氧与 N2 同步翻倍，碳/氮比值不变），所以 **TFT 对风量不敏感，风量主要用于调节产量**；真正有效调节 TFT 的手段是**富氧率**（提高氧浓度、压缩 N2 占比）与**风温**（直接增大鼓风显热）。讲解实例中 V_N2_blast = 790 Nm³/tFe 占煤气总量 1238.4 的 64%，正是这一作用的直观体现。

## 七、为什么焦炭/煤粉的"燃烧率"不影响 TFT

### 1. 概念澄清

"燃烧率"（燃尽率）指燃料中真正在风口燃烧的比例。真实高炉中二者差异很大：

| 燃料 | 风口燃烧率（典型值） | 未燃部分去向 |
| --- | --- | --- |
| 焦炭 | 仅 25%~40% | 进入炉缸：渗碳（铁水含碳 ~4.5%）、死焦层骨架、渣铁界面反应 |
| 喷吹煤粉 | 90%+（要求高燃尽率） | 少量未燃煤粉，量很小 |

### 2. 当前系统模型：合并总碳池，统一受氧限制

系统不区分焦/煤各自的燃烧率，把所有燃料碳合并为总碳 C_total，再统一取 C_burn = min(C_total, C_burnable)。只要 C_burnable < C_total（本例 202.1 < 414），实际燃烧碳就完全由鼓风氧钉死，与焦/煤如何分配无关。

### 3. 数学证明：燃料分配在分子分母中被约掉

把 TFT 分子分母中所有燃料相关项展开：

| 项 | 公式 | 展开后 | 结论 |
| --- | --- | --- | --- |
| 碳燃烧放热（分子） | C_burn × 9.79 | = 202.1 × 9.79 | 只依赖总量 C_burn |
| CO 产气（分母） | V_CO_solid × burnRatio | = 1.867 × C_total × (C_burn/C_total) = **1.867 × C_burn** | C_total 被约掉，只依赖 C_burn |
| H2O + H2 产气（分母） | V_H2O_solid×hc + V_H2O_solid×(1-hc) | = V_H2O_solid = 11.2 × H_total | hc 被自身抵消，只依赖总量 |
| N2（分母） | B × N2_blow | — | 与燃料无关 |

所以 TFT 的分子分母中，**燃料相关项全部只出现 C_burn 与 H_total 两个总量**：C_burn 被氧钉死、H_total 是焦煤加权成分——"这 202.1 kgC 里焦炭占多少、煤粉占多少"在数学上被约掉了。

### 4. 若显式引入独立燃烧率，会发生什么

假设给焦炭设 35%、煤粉设 92%（行业典型值）：

\`\`\`
可燃烧碳 = 306×0.35 + 108×0.92 = 206.5 kgC/tFe ＞ 氧能力 202.1
C_burn = min(C_total, ...) 仍取氧能力 202.1 → TFT 不变
\`\`\`

只有当组合后"可燃烧碳"低于氧能力时才生效：

\`\`\`
若焦炭率压到 20%：可燃烧碳 = 306×0.20 + 108×0.92 = 160.6 ＜ 202.1 → 供碳不足，TFT 下降
\`\`\`

### 5. 为什么真实高炉也适用"氧限制"模型

真实高炉稳态恰好运行在氧限制边界附近：煤粉 90%+ 燃尽率 + 焦炭 25~40% 燃烧率，两者合计刚好"喂饱"鼓风氧（≈206.5 ≈ 202.1）。这就是行业用"氧限制 + 部分燃烧"模型即可很好预测 TFT 的原因——高炉稳态本身就是一个被氧喂饱的系统。

### 6. 什么情况下必须显式考虑燃烧率

| 场景 | 原因 |
| --- | --- |
| 炉缸碳平衡 | 未燃焦炭（本例占 51.2%）的去向——渗碳、死焦层消耗，直接影响碳素流 |
| 炉顶煤气成分 | 焦/煤燃烧率影响 CO/CO2 比 → 间接还原度、煤气热值（BFG 发电量） |
| 喷煤极限 | 提高喷煤比时煤粉燃尽率下降才是限制喷煤量的关键 |

## 八、热状态判定规则

| 状态 | 判定条件 | 含义 | 处置方向 |
| --- | --- | --- | --- |
| 正常 | tftLow ≤ TFT ≤ tftHigh | 热制度稳定 | 维持 |
| TFT 偏低 | TFT < tftLow（默认 2050℃） | 燃烧能量不足、炉温偏凉 | 升温 |
| TFT 偏高 | TFT > tftHigh（默认 2250℃） | 风口过热、炉况热过载 | 降温 |

阈值 \`tftLow/tftHigh\` 可随炉役与冶炼品种配置。

## 九、讲解实例（手算推演）

**工况设定**：热风温度 1250℃，风量 600 kNm³/h（= 相对 1.0），富氧率 0%（无富氧），铁水产量 40 tFe/h（手算标定基准，见上节说明）；焦比 360 kg/tFe，喷煤比 150 kg/tFe。

| 燃料 | 固定碳 FC | 氢 H | 热解吸热 | 用量 |
| --- | --- | --- | --- | --- |
| 焦炭 | 0.85 | 0.001 | 0 | 360 kg/tFe |
| 喷吹煤粉 | 0.72 | 0.04 | 0.35 MJ/kg | 150 kg/tFe |

**第 1 步 · 比风量与鼓风氧**

\`\`\`
QB = 1.0 × 40000 = 40000 Nm³/h
PFe = 40 tFe/h
B = 40000 / 40 = 1000 Nm³/tFe
O2_blow = 0.21
N2_blow = 0.79
V_O2_blast = 1000 × 0.21 = 210 Nm³/tFe
\`\`\`

**第 2 步 · 燃料碳氢总量与理论产气**

\`\`\`
C_total = 360×0.85 + 150×0.72 = 306 + 108 = 414 kgC/tFe
H_total = 360×0.001 + 150×0.04 = 0.36 + 6.0 = 6.36 kgH/tFe
decomp_heat = 0 + 150×0.35 = 52.5 MJ/tFe
V_CO_solid = 1.867 × 414 = 772.9 Nm³/tFe
V_H2O_solid = 11.2 × 6.36 = 71.2 Nm³/tFe
\`\`\`

**第 3 步 · 鼓风氧限制下的实际燃烧碳**

\`\`\`
O2_for_H = 0.5 × 71.2 × 0.6 = 21.36 Nm³/tFe
O2_for_C_avail = 210 - 21.36 = 188.64 Nm³/tFe
C_burnable = 188.64 / 0.9333 = 202.1 kgC/tFe
C_burn = min(414, 202.1) = 202.1 kgC/tFe
burnRatio = 202.1 / 414 = 0.488（仅约 48.8% 的碳实际燃烧）
\`\`\`

**第 4 步 · 放热与产气**

\`\`\`
Q_sensible_air = 1000 × 0.0013 × 1250 = 1625 MJ/tFe
Q_combustion = 202.1×9.79 + 6.36×120×0.6 - 52.5
             = 1978.6 + 457.9 - 52.5 = 2384.0 MJ/tFe
V_CO = 772.9 × 0.488 = 377.2 Nm³/tFe
V_H2O = 71.2 × 0.6 = 42.7 Nm³/tFe
V_H2 = 71.2 × 0.4 = 28.5 Nm³/tFe
V_N2_blast = 1000 × 0.79 = 790.0 Nm³/tFe
V_gas_total = 377.2 + 42.7 + 28.5 + 790.0 = 1238.4 Nm³/tFe
\`\`\`

**第 5 步 · 计算 TFT 并判定**

\`\`\`
Q_total_in = 1625 + 2384.0 = 4009.0 MJ/tFe
TFT = 4009.0 / (1238.4 × 0.0015) = 4009.0 / 1.8576 ≈ 2158 ℃
\`\`\`

**判定**：2050 ≤ 2158 ≤ 2250 → **热制度正常**，无需调整。

**引申 · 若 TFT 偏低如何操作**：平台通过设备调节预览逐项探测（风温 +30℃、风量设定 +520 m³/h（约 +60 kNm³/h）、喷煤量 ±20 kg/h 等），保留使 TFT 升高的调节作为建议——例如提高热风温度可同时增大鼓风显热并提升燃烧温度，是降温工况下的首选升温手段。

## 十、TFT 约束下的节能减碳策略

### 1. 本质：TFT 是约束，减碳是目标

节能减碳不是"随便降燃料"，而是**在 TFT 钉在合规区间（2050~2250℃）的前提下，最小化每吨铁水的碳投入**。TFT 是约束条件（硬边界），减碳是目标函数，二者通过四个可调旋钮联动：

\`\`\`
TFT = (鼓风显热 + 燃烧放热 - 热解吸热) / (煤气总量 × cp)
        ↑热风         ↑焦/煤/油              ↑N2 稀释
\`\`\`

### 2. 四大旋钮：作用与减碳逻辑

| 旋钮 | 对 TFT 的影响 | 减碳逻辑 |
| --- | --- | --- |
| 热风炉·风温 ↑ | 鼓风显热↑ → TFT ↑ | 不直接减碳，但**免费热量顶替焦炭燃烧放热**：风温每 +50℃ 可降焦比 8~12 kg/tFe |
| 鼓风机·富氧 ↑ | 分母 N2↓ + 供氧↑ → TFT ↑↑ | 压缩惰性 N2、提高单位风量燃烧能力，为降焦比/提喷煤腾出 TFT 空间（富氧耗电，需权衡间接排放） |
| 喷吹·喷煤比 ↑ | 热解吸热 + 产 H2O 稀释 → TFT ↓ | 煤粉碳含量（0.72）< 焦炭（0.85），替代焦炭大幅降焦比，**最大减排杠杆** |
| 鼓风机·风量 ↑ | 供氧与 N2 同步变化，近抵消 | 产量通道，TFT 基本不变，减碳贡献小 |

### 3. 标准减碳操作路径（四步）

**第 1 步 · 风温打满**：热风温度提到上限，鼓风显热↑ → TFT↑，**创造减碳空间**（成本最低、零碳排放的升温手段）。

**第 2 步 · 用 TFT 空间换碳**：空间出现后降焦比——焦比每降 10 kg/tFe ≈ 少投入 8.5 kg 焦炭碳 ≈ 减排 31 kgCO2/tFe（×3.667）；同时增喷煤比替代等热量焦炭。两项措施都会使 TFT 回落，正好消耗第 1 步的空间——**每项减碳措施都从分子扣热量，扣到 TFT = tftLow 就是减碳极限**。

**第 3 步 · 富氧兜底**：焦比压到下限、喷煤受 TFT 限制上不去时，提富氧率压缩 N2 分母 → TFT 回升 → 释放新一轮降焦/提煤空间（富氧的代价是制氧电耗，是否划算看电价与焦炭价差）。

**第 4 步 · 监控闭环**：全程盯 TFT 状态——偏低 → 提风温/提富氧/降喷煤；正常 → 继续试探性降焦比；偏高 → 本身即是减碳信号，优先降焦比。

### 4. 为什么 TFT 下限是减碳的天然护栏

利用燃烧份额的氧限制特性：焦比降太多时，燃料总碳 C_total 低于鼓风氧能力 C_burnable，供碳不足，TFT 会直线下跌至阈值以下——**TFT 下限就是减碳的物理底线，炉况自行拦截，无需人为设指标**。

### 5. 平台实现

「高炉数值分析」面板对每个可调参数做全范围扫描，绘制 TFT 响应曲线（含合规区间带与当前工况点），直观展示：风温曲线线性上升、富氧曲线加速上升、风量曲线近水平（供氧/N2 抵消）、焦比曲线近水平（氧限制钉死 C_burn，降焦比零温度代价）、喷煤曲线缓降（热解吸热 + 稀释）。结合 TFT_DEVICE_PROBES 设备探测与后端 carbon_engine 碳素流核算，每次调整可同时看到 TFT 与 CO2 变化，形成"温度合规 + 碳减排"双目标闭环。`,
  },
  {
    id: 'coupling',
    title: '设备耦合参数推导',
    body: `## 设备耦合参数推导

设备调节不能孤立生效——改变鼓风机风量会牵动热风炉风温、喷吹系统喷煤等上下游工序参数。前端 \`flowLibrary.js\` 中的 \`deriveProcessOpParams\` 负责**从设备设定反推全局工序参数**，保证仿真自洽。

## 一、推导语义

\`\`\`js
deriveProcessOpParams(unitType, devices, baseParams) → overrides
\`\`\`

- 输入：工序类型、设备调节列表（类型 + 设定值）、当前工序参数；
- 输出：受影响的工序参数覆盖集（如 hot_blast_temp、wind_rate、oxygen_enrich 等）。

## 二、典型耦合关系

| 设备调节 | 影响工序参数 | 说明 |
| --- | --- | --- |
| 热风炉 · 风温 | hot_blast_temp | 直接决定鼓风显热 |
| 鼓风机 · 风量 | wind_rate | 改变比风量，影响 TFT 与煤气量 |
| 鼓风机 · 鼓风湿度 | blast_humidity | 鼓风含湿（加湿/脱湿）参与水分分解吸热，湿度↑→TFT↓、焦比↑ |
| 喷吹系统 · 喷煤量 | coal_inj | 增加燃料量，但受鼓风氧限制 |

## 三、TFT 设备探测（TFT_DEVICE_PROBES）

TFT 策略模块通过**设备级探测**评估每个可调设备的调节效果：

\`\`\`js
const TFT_DEVICE_PROBES = [
  { type: 'hot_blast_stove', label: '热风炉·风温',   step: 30,  unit: '℃' },
  { type: 'blower',           label: '鼓风机·风量',   step: 520, unit: 'm³/h' },
  { type: 'blower',           label: '鼓风机·鼓风湿度', step: 1, unit: 'g/Nm³', extraKey: 'humidity', def: 10 },
  { type: 'injector',         label: '喷吹系统·喷煤量', step: 20, unit: 'kg/h' },
]
\`\`\`

对每个设备按 step 试探调节，经 \`deriveProcessOpParams\` 折算后重新计算 TFT，保留使热状态回到正常区间且 ΔTFT 最大的调节作为推荐。

## 四、设备建议与系统建议

- \`buildDeviceTftAdvices\`：针对单个设备的调节建议（含 ΔTFT 预测）；
- \`buildSystemTftAdvices\`：全局视角（正常时提示维持现状）；
- 两类建议均标注方向（升温 ↑ / 降温 ↓ / 维持 ✓）与调节量。

## 五、实时参数折算

\`buildRealtimeTftParams\` 将「工序基础参数 + 当前实际设备设定（含附加可调项）」折算为 TFT 实时计算参数，与系统 \`refresh()\` 的折算语义一致——**拖动可调设备滑块后，TFT 面板与仿真结果实时一致**。`,
  },
  {
    id: 'telemetry',
    title: '实时遥测系统',
    body: `## 实时遥测系统

后端 \`realtime.py\` 负责 WebSocket 长连接推送与监测设备历史时序（内存 ring buffer）。

## 一、架构

| 组件 | 职责 |
| --- | --- |
| FeedManager | 维护当前活跃 WebSocket 连接集合 |
| DEVICE_HISTORY | 每台设备最近读数的内存环形缓冲（**600 点 ≈ 10 分钟**，1Hz 采样） |
| ws_feed | 客户端连接后每秒推送带噪声的实时遥测帧 |
| seed_history | 流程变更/启动时回填设备历史基线，保证首屏即有趋势数据 |

## 二、WebSocket 协议

\`\`\`json
// 客户端 → 服务端（设定当前流程）
{ "type": "model", "model": { "units": [...], "flows": [...] } }

// 服务端 → 客户端（每秒一帧）
{
  "devices": [{ "id", "unit_id", "label", "type", "reading", "unit" }, ...],
  "units": [...]
}
\`\`\`

- 客户端发送 \`type:'model'\` 设定流程后，服务端重新 \`seed_history\` 并基于该流程持续推送；
- 流程变更 → 自动重建设备历史基线。

## 三、模拟噪声

\`\`\`python
def _noise(v, pct=0.04):
    return max(0.0, v * (1 + random.uniform(-pct, pct)))
\`\`\`

- 实时帧：基准读数 ×（1 ± 4%）随机抖动，模拟真实仪表抖动；
- 历史回填（seed）：×（1 ± 5%）抖动生成 180 秒趋势；
- 读数由**活动数据**算出基准值，再叠加时间噪声。

## 四、历史查询

前端「数据 → 设备历史」图表数据来自 \`DEVICE_HISTORY\`（或 \`GET /api/devices/history\`），展示每台设备近 10 分钟趋势。

## 五、数据源支持

平台支持三种数据源（文件 → 连接数据源…）：
1. **Mqtt 实时**：默认数据源，后端订阅云端 MQTT Broker（Broker 配置前端化：能碳一体机管理 → 总览 → 配置 Broker；参照参考项目 yunduan1 数据链路：边缘盒子（能碳一体机）eKuiper → Broker \`data/#\` 等主题）获取真实设备读数，不生成模拟数据；读数同步采用**关联制**（视图 → 能碳一体机管理）：自动识别云端设备并按盒子分组，须与仿真设备实例手动关联后（\`config/links.json\`）才同步到该设备实例；
2. **自定义 WebSocket**：外部系统推送（接入真实工厂时使用）；
3. **HTTP 轮询**：REST 拉取。

### 能碳一体机管理台 API（参照参考项目 yunduan1 console + dashboard）

| 接口 | 返回要点 |
| --- | --- |
| GET /api/box/overview | 概览：\`{ broker:{connected,stats($SYS 真实统计)}, cloudcore(仿真演示), nodes(识别到的盒子), ports(CloudHub 10001-10004), certs, token }\` |
| GET /api/box/devices | \`{ models[], devices[], cloud_devices }\`（DeviceModel/Device 列表 + 云端识别设备，本地持久化 \`config/box_devices.json\`） |
| POST /api/box/devices | 创建设备/模型：\`mode=dryRun\` 返回三协议（Modbus/OPC-UA/Bluetooth）YAML 预览；\`mode=apply\` 保存到模拟集群；body 含 protocol/modelName/deviceName/nodeName/properties/comm/opcua/bluetooth |
| POST /api/box/devices/delete | 删除：\`{kind: device\|model\|both, name, namespace}\` |
| GET /api/box/devices/realtime | \`{ devices:[{name,state,lastOnlineTime,twins:[{propertyName,reported,observedDesired,timestamp,unit}],history}] }\`，reported 读数一律来自 MQTT 链路 |
| POST /api/box/nodes/onboard | 盒子接入：\`{hostname,cloudIP,boxIP}\` → \`{edgecore, token, caHash, commands}\`（模板 \`config/edgecore.template.yaml\`，token/caHash 仿真演示） |
| GET /api/box/stats | \`{ stats, messages }\`：Broker $SYS 统计 + 最近 100 条实时消息流 |
| POST /api/box/publish | 发测试消息：\`{topic, payload}\`，向云端 Broker 发布（实时仪表盘调试） |
  `,
  },
  {
    id: 'contract',
    title: '数据契约模型',
    body: `## 数据契约模型

所有前后端交互的数据契约集中在 \`backend/app/models.py\`（Pydantic），保证类型一致、前后端可校验。

## 一、流程模型

| 模型 | 字段 | 说明 |
| --- | --- | --- |
| Unit | id / type / name / x / z / rot / enabled / params / techs | 工序节点（位置、参数、已应用技术） |
| Flow | id / from_unit / to_unit / material / rate | 物流连线（hot_metal/scrap/steel/dri） |
| ProcessModel | units / flows | 完整流程 |

## 二、策略解析

| 模型 | 说明 |
| --- | --- |
| ParsedOp | 单条操作：action / target / param / value / mode(absolute\|relative) / tech / note |
| ParseResult | raw_text / understood / ops / confidence / warnings / engine(llm\|heuristic) |

## 三、仿真结果

| 模型 | 说明 |
| --- | --- |
| LedgerItem | 碳排放台账项：item / qty / qty_unit / basis / formula / co2 / scope(direct\|indirect) |
| UnitResult | 单工序结果：co2_direct/indirect/total、carbon_in/to_co2/to_steel/captured、heat(0~1 热力图)、能耗字段、breakdown 台账、devices 监测设备 |
| SimTotals | 全厂汇总：co2_total、carbon_utilization、steel_output、intensity(kgCO₂/t)、energy 字段 |
| SankeyNode / SankeyLink | 桑基图数据：燃料源 → 工序 → 去向，链路值为 tC/h |
| SimResult | totals / units / sankey |

## 四、策略与请求

| 模型 | 说明 |
| --- | --- |
| Strategy | 已保存策略：id / name / description / raw_text / ops / applied |
| ParseRequest | 解析请求：text + 当前模型 |
| SimulateRequest | 仿真请求：model + 可选 ops（策略操作）+ factors（自定义因子） |
| SimulateResponse | 仿真响应：baseline + 可选 strategy（策略后）+ delta（前后差值） |
| ReportRequest | 报告请求：baseline/strategy/engine/depth/with_appendix 等 |

## 五、delta 结构（策略对比）

\`\`\`json
{
  "co2_total": -312.5,          // tCO₂/h 差值
  "co2_direct": -298.1,
  "co2_indirect": -14.4,
  "intensity": -8.3,            // kgCO₂/t
  "carbon_utilization": 0.0184,
  "steel_output": 0.0,
  "co2_reduction_pct": 12.6     // 减排百分比
}
\`\`\`

## 六、扫描 / 审计 / 优化器请求

以下端点使用 \`dict\` 请求体（不经 Pydantic），由后端按需读取：

| 端点 | 请求体字段 |
| --- | --- |
| POST /api/scan | param / mode(center\|range\|sweep) / range / density / keep_ratio / exclude_self |
| POST /api/audit | model（流程）+ 可选 ops |
| POST /api/optimizers/context | model + factors（训练上下文） |
| PUT /api/optimizers/{oid}/settings | auto_control / schedule{enabled,interval_h,start,end} / samples |
| POST /api/optimizers/{oid}/train | steps（训练步数） |

## 七、碳市场 / 快讯契约

| 模型 | 说明 |
| --- | --- |
| Quote | \`{ t, price/close, change_pct, source }\`；CEA / CCER 各一组 |
| MarketQuotes | \`{ ok, simulated, queried_at, cea, ccer, cea_monthly[], daily_count, intraday }\` |
| ChartPoint | \`{ t, open?, high?, low?, close, volume? }\`（K 线）或 \`{ t, price/close }\`（折线） |
| ChartSeries | \`{ ok, instrument, kind, title, unit, source_name, source_page, queried_at, points[] }\` |
| ForecastPoint | \`{ t, price, high, low }\`（high/low = ±1.65σ 置信带）；ForecastSeries 含 method/confidence/slope/base_date/history_tail/forecast[] |
| NewsItem | \`{ id, time, content, tags[], views }\`；返回 \`{ ok, items[], source, source_name, queried_at }\`，ok=false 表示抓取失败 |
`,
  },
  {
    id: 'protocol',
    title: '仿真协议与接口',
    body: `## 仿真协议与接口

## 一、REST API（后端 FastAPI）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | /api/health | 健康检查 |
| GET | /api/cache/stats | 仿真缓存命中率（诊断） |
| GET | /api/model/preset | 默认流程模型 |
| GET | /api/presets/strategies | 内置示例策略（一键体验） |
| GET | /api/factors | 默认排放因子表 |
| GET | /api/param-schema | 工序参数分级元数据（config/optim、label、单位、参考范围） |
| GET | /api/devices | 内置监测设备库（设备元数据 + 工序规格 + 设备规格档位库） |
| GET | /api/devices/history | 设备历史时序（内存环形缓冲） |
| POST | /api/parse | 自然语言 → 策略操作（LLM/启发式双引擎） |
| POST | /api/simulate | 仿真（baseline + 可选策略对比 delta） |
| POST | /api/apply | 直接对流程应用一组操作 |
| POST | /api/strategies | 创建策略；GET/PUT/DELETE /api/strategies/{id}；POST /api/strategies/{id}/apply 应用策略 |
| POST | /api/scan | 单工序参数敏感性扫描（扫参区间 / 密度 / 保留比例） |
| POST | /api/audit | 全流程碳素流守恒审计（碳输入 = 排 CO₂ + 固钢 + 入渣 + 捕集 + 产品携出） |
| POST | /api/optimizers/context | 同步 AI 优化训练上下文（当前流程 + 因子，供优化器建模） |
| GET | /api/optimizers | 优化模型列表与训练状态（迭代/曲线/最优参数摘要） |
| GET | /api/optimizers/{oid} | 单个优化器详情（训练轨迹/超参/版本/建议/提醒） |
| POST | /api/optimizers/{oid}/start | 开启自动训练（后台随实时数据定时迭代） |
| POST | /api/optimizers/{oid}/stop | 停止自动训练 |
| POST | /api/optimizers/{oid}/train | 手动训练 N 步（steps 参数） |
| POST | /api/optimizers/{oid}/reset | 重置模型权重 |
| PUT | /api/optimizers/{oid}/hyper | 保存算法超参数（GA/PSO/RL） |
| POST | /api/optimizers/{oid}/apply | 应用最优参数到流程（best → 可调设备） |
| PUT | /api/optimizers/{oid}/settings | 更新控制与自训练设置（自动化控制/频率/时段/样本量） |
| POST | /api/optimizers/{oid}/archive | 手动存档当前模型版本 |
| POST | /api/optimizers/{oid}/switch | 切换到历史版本 |
| POST | /api/optimizers/{oid}/ack | 确认调优提醒（清除未读标记） |
| POST | /api/report | 创建报告生成任务（后台线程） |
| GET | /api/report/task/{id} | 轮询报告进度（done/progress/stage/result） |
| GET | /api/reports | 历史报告列表（倒序） |
| GET | /api/report/{rid} | 单个历史报告详情（Markdown 原文） |
| DELETE | /api/reports/{rid} | 删除历史报告 |
| POST | /api/chat | 命令行窗口自然语言对话（LLM，无 Key 兜底提示） |
| GET | /api/carbon-market/quotes | 碳市场实时报价（CEA/CCER 最新价 + 涨跌幅 + 月聚合，60s 缓存） |
| GET | /api/carbon-market/chart?instrument=cea\|ccer | 图表序列：CEA 日K线 / CCER 成交均价折线（60s 缓存） |
| GET | /api/carbon-market/forecast?instrument=cea\|ccer&days=10 | 价格预测：线性回归外推 + ±1.65σ 置信带 |
| GET | /api/market-news | 市场快讯列表（中国煤炭交易网抓取 + 60s 缓存，失败返回 ok=false 与空列表） |
| GET | /report/{rid} | 报告分享页（独立 HTML，新标签查看/打印） |

## 二、WebSocket 遥测

- 路径：\`/api/ws/feed\`；
- 协议见「实时遥测系统」章节；
- 支持 Mqtt 实时（默认，后端订阅云端 MQTT Broker 获取真实读数）、自定义 WebSocket、HTTP 轮询三种数据源（文件 → 连接数据源…）。

## 三、SPA 托管

后端以 **Catch-all 路由**托管前端构建产物：
- 存在真实静态文件（模型/解码器等）时直接返回，避免全部回退 index.html；
- 其余路径回退到 SPA 入口，保证前端路由（若有）可刷新直达。

## 四、报告导出

平台支持将当前工况的碳流、碳排、TFT 状态汇总导出为 Markdown 分析报告，并渲染为可分享的 HTML 页面（文件 → 导出分析报告）。`,
  },
  {
    id: 'carbon-market',
    title: '碳市场行情服务',
    body: `## 碳市场行情服务

后端 \`carbon_market.py\` 提供 CEA（全国碳市场配额）与 CCER（自愿减排量）两类碳资产的行情数据服务：实时报价、K 线/折线序列、价格预测，供前端「碳市场视图」与底部状态栏使用。

## 一、数据来源与降级策略

- **CEA**：从上海环境能源交易所公开行情页解析（日 K 序列 + 最新价 + 月聚合）；
- **CCER**：优先从全国温室气体自愿减排交易系统（北京绿色交易所）日行情列表拉取，失败回退碳中和网整理的历史表 + 最新报价解析；
- 任一环节失败（网络不可用 / 超时 / 解析失败）时，自动回退到**内置模拟行情**（按分钟确定性随机游走生成，保证轮询时数值持续变化），并在响应中标注来源 \`simulated\`，前端据此显示「模拟」徽标；
- 全接口采用 **60 秒 TTL 缓存**（\`_TtlCache\` + 线程锁）：首次请求后缓存 60 秒，期间请求直接命中缓存，避免高频打外网。

## 二、API 契约

| 接口 | 返回要点 |
| --- | --- |
| GET /api/carbon-market/quotes | \`{ ok, simulated, queried_at, cea, ccer, cea_monthly[], daily_count, intraday }\`；cea/ccer 含 \`t\`/价格/\`change_pct\`（涨跌幅）/来源；\`simulated\` 标识是否模拟数据 |
| GET /api/carbon-market/chart?instrument=cea\|ccer&kind=daily | \`{ ok, instrument, kind, title, unit, source_name, source_page, queried_at, points[] }\`；CEA 返回日K线（t/开/高/低/收/量），CCER 返回成交均价折线；无外网时生成模拟序列兜底 |
| GET /api/carbon-market/forecast?instrument=cea\|ccer&days=10 | \`{ ok, instrument, days, method, confidence, slope, base_date, source_name, history_tail[], forecast[] }\`；forecast 中每点带 \`t/price/high/low\`（high/low 为 ±1.65σ 置信带），days 默认 10，上限 30 |

## 三、预测算法（forecast_series）

- 取最近 **90 个历史点**做最小二乘线性回归 \\(y = a + b\\,x\\)（\`_ols\`），\\(b\\) 即价格趋势斜率；
- 残差标准差 \\(s=\\sqrt{\\sum r_i^2/(n-2)}\\)，置信带带宽按 \\(1.65\\,s\\,\\sqrt{1+i/n}\\) 随外推天数 \\(i\\) 递增（约 90% 置信）；
- 未来日期按历史平均间隔推进并跳过周六/周日（\`_next_trade_date\`）；
- 该算法定位为**趋势参考**而非精确预测；前端在图上以虚线（预测线）与阴影带（high/low 区间）呈现。

## 四、前端集成

- \`CarbonMarketView.vue\`：行情卡片（CEA 最新价/涨跌幅/成交量/今开/最高/最低/昨收 + CCER 最新均价/成交量/基准参考）、CEA 蜡烛图（30 日 OHLCV）与 CCER 折线页签切换、预测叠加与置信带（±1.65σ）；15 秒轮询，断开自动停止；「实时数据 / 模拟行情」徽标来自 quotes.simulated；
- \`StatusBar.vue\`：底部滚动播报快讯摘要（与「市场快讯服务」联动），鼠标悬停暂停滚动。`,
  },
  {
    id: 'market-news',
    title: '市场快讯服务',
    body: `## 市场快讯服务

后端 \`market_news.py\` 定时从**中国煤炭交易网「市场快讯」栏目**抓取行业资讯（煤炭 / 碳市场相关动态），转换为结构化的快讯列表供前端展示。

## 一、抓取与缓存

- 首次请求时发起抓取，成功后缓存 **60 秒（TTL）**（\`_TtlCache\` + 线程锁），期间后续请求直接返回缓存，避免频繁请求外网；
- 编码兼容 UTF-8 / GBK，请求带浏览器 UA 头；失败（网络不可用 / 目标页结构变化 / 超时）时返回 \`ok=false\` 与空列表，前端显示「快讯暂不可用」，不阻断其它功能；
- 返回字段：\`ok\`（是否成功）、\`items\`（快讯数组，含 \`id\` / \`time\` / \`content\` / \`tags\` / \`views\`）、\`source\` / \`source_name\`（来源标识与名称）、\`queried_at\`（查询时间）。

## 二、API 契约

| 接口 | 返回要点 |
| --- | --- |
| GET /api/market-news?page=1 | \`{ ok, items: [{ id, time, content, tags, views }], source, source_name, queried_at }\`；page 默认 1 |

## 三、前端集成

- \`StatusBar.vue\`：左侧「市场快讯」滚动条持续轮播（每条约 18s 滚动周期，自适应条数），鼠标悬停暂停滚动；每 5 分钟自动刷新一次；
- 快讯的显隐由系统设置「布局」页签「快讯滚动条」开关控制（\`newsTickerOn\`，存于 Pinia）；
- 快讯与碳市场视图相互独立：快讯常驻状态栏，碳市场视图需「视图 → 碳市场」打开。`,
  },
  {
    id: 'optimizer',
    title: 'AI 优化模型引擎',
    body: `## AI 优化模型引擎

后端 \`optimizers.py\` 提供三套在线自学习优化模型（**遗传算法 GA / 粒子群 PSO / 强化学习 RL**），随流程运行与实时传感器数据后台持续训练，输出碳强度最优的设备参数建议，并支持版本管理与自动化控制。

## 一、模型架构

| 组件 | 职责 |
| --- | --- |
| OptimizerBase | 优化器基类：归一化状态、适应度求值、训练循环、版本/提醒管理 |
| GeneticOptimizer | 遗传算法（GA）：选择 / 交叉 / 变异算子 |
| ParticleSwarmOptimizer | 粒子群（PSO）：惯性权重 + 个体/全局最优引导 |
| RLQOptimizer | 强化学习（Q-Learning 表）：以离散动作 Q 表驱动寻优 |
| TrainingScheduler | 后台调度线程：按配置频率定时迭代全部活跃优化器 |

## 二、优化空间与上下文

- 优化目标是 **单位产品碳强度（kgCO₂/t）** 最小化；
- 可优化参数来自 \`/api/optimizers/context\` 同步的当前流程模型（各工序可调设备参数）与排放因子；
- 状态输入为**归一化实时遥测读数**（映射到 [0,1] 区间），保证跨设备可比；
- 适应度（fitness）= 基于当前流程计算出的碳强度，训练越久越接近流程最优参数组合。

## 三、训练与更新机制

- **自动训练**：\`POST /api/optimizers/{oid}/start\` 开启后，后台 \`TrainingScheduler\` 按自训练设置（频率/时段/样本量）随实时数据定时迭代；
- **手动训练**：\`POST /api/optimizers/{oid}/train\` 单步推进，便于观察收敛过程；
- 每次取得更优解即记录**最优参数建议**与**强度提升百分比**，前端轮询 \`GET /api/optimizers\` 展示「模型逐渐变优」。

## 四、控制模式与提醒

- **自动化控制**（\`settings.auto_control\` 开启）：模型变优后由后端直接下发最优参数到可调设备，命令行输出应用日志；
- **手动模式**：仅生成调优提醒（reminder），在策略属性面板确认（ack）后可手动应用（apply）；
- 提醒包含最优强度、较上版提升百分比，按需展示。

## 五、版本管理

- 每次取得阶段性更优解自动存档版本（含超参数、权重、最优参数、时间）；
- 手动存档 \`POST /api/optimizers/{oid}/archive\`、切换历史版本 \`POST /api/optimizers/{oid}/switch\`、重置权重 \`POST /api/optimizers/{oid}/reset\`；
- 超参数（GA/PSO/RL 各自模板）经 \`PUT /api/optimizers/{oid}/hyper\` 持久化。

## 六、数据契约

优化器 API 使用 \`dict\` 请求体（不经 Pydantic），主要字段：
\`\`\`json
// settings
{ "auto_control": true, "schedule": { "enabled": true, "interval_h": 1, "start": "09:00", "end": "18:00" }, "samples": 60 }
// train
{ "steps": 5 }
\`\`\`
状态响应（GET /api/optimizers/{oid}）包含：\`status / iteration / best_fitness / best_params / history(曲线) / versions / reminder / hyper / settings\`。`,
  },
  {
    id: 'viz',
    title: '前端可视化与交互',
    body: `## 前端可视化与交互

## 一、3D 场景（three/scene.js · TwinScene）

基于 Three.js 构建的数字孪生场景：

- **工序模型库 UNIT_META**：烧结机、球团、焦炉、高炉、转炉、电炉、精炼炉、连铸机、热轧机等 20+ 种工艺，按实际规模差异化缩放（高炉巨大、转炉中等、精炼偏小）；
- **赛博朋克材质工厂**：高金属感、低粗糙度、蓝黑基底；
- **环境模式 ENV**：五种可切换场景——void 赛博虚空（深空背景 + 霓虹网格）、industrial 工业（厂房与管道剪影）、desert 沙漠、city 城市（远景建筑群）、coast 海滩（水面 + 椰树），各有独立天空渐变、地表色与雾效；
- **平台地坪与网格**：随环境模式切换配色与霓虹网格（void 模式）；
- **聚焦/选中高亮**：点击工序聚焦相机并高亮唯一标签与选中环，\`focus\`/框架视图（\`frameAll\`）一键复位。

## 二、虚拟巡视（四足巡检机器狗）

场景内置可操控的巡检机器狗（第一人称 / 第三人称跟随视角）：

| 项 | 值 | 说明 |
| --- | --- | --- |
| PATROL_SPEED | 26 世界单位/秒 | 行走速度，按住 Shift 加速 |
| PATROL_TURN | 1.6 rad/s | 原地旋转角速度（≈92°/s） |
| PATROL_RADIUS | 3.2 | 碰撞半径（含步幅余量） |
| PATROL_CAM_BACK / UP / AHEAD | 22 / 12 / 30 | 第三人称相机后撤/高度/前置 |

- 支持 **XZ 平面刚体碰撞**（AABB 障碍清单，\`_patrolSolids\`）与厂区可行走边界；
- 步态动画随移动/转向驱动；**编排新增/删除工艺时会同步刷新刚体清单**，避免撞上「空气墙」；
- 巡视中切换环境模式同样生效。

## 三、热力图与物流动画

- **热力图 heat layers**：按 \`UnitResult.heat\`（0~1）为工序外壳着色，直观呈现各工序热负荷/排放强弱；
- **物流动画 flows**：物流连线上的粒子/进度动画，展示 hot_metal / scrap / steel / dri 的流向与速率；
- 热风炉等容器类工序支持外壳半透明显示内部结构。

## 四、Pinia 全局状态（stores/sim.js）

- 流程编排：工序/物流的增删改、撤销重做（history）、方案保存；
- 仿真状态：baseline / strategy / delta、实验对比（同时仿真多方案）；
- 策略：解析结果、已保存策略、应用状态；
- 设备：实时遥测读数、历史趋势、设备设定（滑块）；
- 环境模式与巡视模式状态、3D 聚焦目标。

## 五、桑基图（碳流可视化）

仿真结果生成 Sankey 图数据（燃料源 → 工序 → 去向，链路值 tC/h），可视化展示碳素流分配、固碳与捕集去向。

## 六、分析类面板

| 面板 | 入口 | 说明 |
| --- | --- | --- |
| 参数敏感性扫描（SensitivityDialog） | 画布节点 / 左侧策略库工序右键 → 参数敏感性扫描 | 对单工序指定参数扫参，生成敏感性曲线与建议调节方向（POST /api/scan） |
| 碳素流守恒审计 | 工具菜单 → 碳素流守恒审计 | 逐工序核算碳输入/输出五项平衡，输出偏差与守恒率（POST /api/audit） |
| 高炉数值分析（TftAnalysisDialog） | 仿真菜单 → 高炉数值分析（Alt+T） | 全厂高炉 TFT 数值总览、鼓风/喷煤调参推演，复用 utils/tft.js 焓平衡 |
| 参数范围/设备量程内化 | 编排模式工序/设备节点属性面板 | 节点属性面板直接编辑参数运行空间（min/max/step）与设备量程，随方案持久化，无需全局配置（优先级：节点自定义 > 设备规格 ranges > 默认） |
| AI 优化模型（策略详情面板） | 左侧「策略 → AI优化模型」点击模型 | GA/PSO/RL 在线训练面板：状态/迭代/曲线/最优参数建议，支持训练控制、应用最优参数、版本管理与提醒确认（/api/optimizers/*） |
| 数据视图（DataView） | 视图菜单 → 数据 | 全屏传感器历史数据表格：设备页签 + 实时读数/均值/峰值/谷值/超限状态 + 时序表格 |
| 碳市场行情（CarbonMarketView） | 视图菜单 → 碳市场 | 行情卡片 + CEA 蜡烛图 / CCER 折线 + 线性回归预测与置信带；15s 轮询，详情见「碳市场行情服务」章节 |
| 数据校准（CalibrationWizard） | 工具菜单 → 数据校准 | 选择设备 → 输入标准/读数标定点 → 线性回归拟合校准曲线 → 预览误差 → 应用/重置（校准系数持久化） |

## 七、系统级 UI 组件（欢迎页 / 活动栏 / 状态栏）

面向整体工作台的壳层组件，承载模式选择、面板切换与全局信息展示：

| 组件 | 职责 |
| --- | --- |
| WelcomeScreen | 启动欢迎页：展示平台功能特性与能力链路，选择项目模板（钢铁长流程 / 短流程）进入系统 |
| ActivityBar | 类 VS Code 活动栏：资源管理器 / 搜索 / 场景 / 连接 四个入口，切换左侧面板 |
| StatusBar | 底部状态栏：实时链路状态、工序/物流计数、监测点位、市场快讯滚动（点击弹详情）、策略情景、时钟与通知 |
| SearchPanel | 全局搜索：按名称模糊匹配工序 / 物料 / 策略 / 设备，点击结果联动检视器、资源管理器与 3D 聚焦 |
| ScenePanel | 场景控制：环境主题切换、显示图层开关（网格/轴向/标签/连线/热力图）、视角工具 |
| ConnectionsPanel | 连接面板：三种数据源（模拟/WebSocket/HTTP）运行状态展示与在线启停，入口直达数据源配置 |
| CarbonBoxView | 能碳一体机管理（视图 → 能碳一体机管理）：集成参考项目 yunduan1 全部能力，六页签——总览（Broker $SYS 统计 + 节点/CloudCore/证书，仿真演示）、设备管理（DeviceModel/Device 三协议 CRUD + YAML 生成，config/box_devices.json）、设备关联（云端设备 ↔ 仿真设备实例，config/links.json）、盒子接入（edgecore.yaml 模板渲染 + token/caHash + 部署命令）、实时数据（twins 真实读数 + 趋势 + 消息流 + 发测试消息）、接入指引（eKuiper 规则 / 盒子采集 / 部署包 / 诊断工具） |

## 八、数据源管理与系统设置

- **DataSourceDialog**（文件 → 连接数据源…）：配置三种实时数据来源——Mqtt 实时（默认，读数来自后端 MQTT 订阅，Broker 在「能碳一体机管理」视图前端配置）、WebSocket（ws:// 服务器）、HTTP 轮询（REST 接口）；每项支持启停、采样间隔与「测试连接」；配置持久化到本地，重启自动应用；
- **SystemSettingsDialog**（文件 → 设置…）：按页签分组——布局（面板显隐）、场景（仿真情景 / 环境）、实时链路（数据源启停）、LLM（模型名 / API 密钥 / API 地址，可选，未配置自动回退本地规则与本地模板报告）；
- 两种对话框状态存于 Pinia（\`showDataSource\` / \`showSettings\`），数据源配置与连接面板共享同一状态源。

## 九、命令行窗口（CommandConsole）

底部命令行为交互中枢：聊天 / 代码 / 规划三模式 + 孪生控制命令（run/sim/stop/reset/overview/home/patrol/view/edit/done/clear），走 \`POST /api/chat\`；内置策略与工序策略的自然语言输入则走 \`POST /api/parse\`（LLM 优先、启发式回退）。`,
  },
]

function go(id) {
  const el = document.getElementById(id)
  if (!el || !scrollEl.value) return
  active.value = id
  scrollEl.value.scrollTo({ top: el.offsetTop - 8, behavior: 'smooth' })
}

function onScroll() {
  const sc = scrollEl.value
  if (!sc) return
  const pos = sc.scrollTop + 60
  let cur = sections[0].id
  for (const s of sections) {
    const el = document.getElementById(s.id)
    if (el && el.offsetTop <= pos) cur = s.id
  }
  active.value = cur
}

onMounted(() => { active.value = sections[0].id })
</script>

<style scoped>
.td-mask { position: fixed; inset: 0; background: rgba(10,16,24,.55); display: flex; align-items: center; justify-content: center; z-index: 200; backdrop-filter: blur(2px); }
.td-modal { width: 1180px; max-width: 96vw; height: 88vh; max-height: 94vh; background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  box-shadow: 0 20px 60px rgba(0,0,0,.35); font-family: var(--ui); color: var(--text); display: flex; flex-direction: column; overflow: hidden; }
.td-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--panel-2); flex: none; }
.td-title { font-size: 14px; font-weight: 700; letter-spacing: .5px; }
.td-x { border: none; background: transparent; font-size: 16px; line-height: 1; color: var(--muted); cursor: pointer; padding: 0 4px; }
.td-x:hover { color: var(--text); }

.td-body { display: flex; flex: 1; min-height: 0; }
.td-toc { width: 232px; flex: none; border-right: 1px solid var(--border); background: var(--panel-2); overflow-y: auto; padding: 14px 10px; }
.td-toc-title { font-size: 11px; font-weight: 700; color: var(--muted); letter-spacing: 2px; margin: 0 6px 10px; }
.td-toc-item { display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px 10px; margin-bottom: 2px;
  border: none; border-radius: 6px; background: transparent; color: var(--text); font-size: 12.5px; font-family: var(--ui);
  text-align: left; cursor: pointer; line-height: 1.45; transition: background .15s; }
.td-toc-item:hover { background: var(--accent-l); }
.td-toc-item.on { background: var(--accent-l); color: var(--accent-d); font-weight: 600; }
.td-toc-num { flex: none; width: 18px; height: 18px; display: inline-flex; align-items: center; justify-content: center;
  border-radius: 4px; background: var(--panel-3); color: var(--muted); font-size: 10px; font-weight: 600; }
.td-toc-item.on .td-toc-num { background: var(--accent); color: #fff; }

.td-scroll { flex: 1; overflow-y: auto; padding: 26px 34px 40px; min-width: 0; }
.td-sec { scroll-margin-top: 8px; }
.td-md { max-width: 860px; }
.td-md :deep(h1) { font-size: 22px; font-weight: 800; margin: 0 0 14px; padding-bottom: 10px; border-bottom: 2px solid var(--accent); letter-spacing: .3px; }
.td-md :deep(h2) { font-size: 17px; font-weight: 700; margin: 30px 0 12px; color: var(--accent-d); }
.td-md :deep(h3) { font-size: 14.5px; font-weight: 700; margin: 22px 0 8px; }
.td-md :deep(p) { font-size: 13.5px; line-height: 1.85; margin: 8px 0; color: var(--text); }
.td-md :deep(ul), .td-md :deep(ol) { margin: 8px 0 8px 22px; font-size: 13.5px; line-height: 1.85; }
.td-md :deep(li) { margin: 3px 0; }
.td-md :deep(code) { background: var(--panel-3); padding: 1px 6px; border-radius: 4px; font-size: 12px; font-family: "SF Mono", Menlo, Consolas, monospace; }
.td-md :deep(pre.rp-code) { background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; overflow-x: auto; margin: 10px 0; }
.td-md :deep(pre.rp-code code) { background: none; padding: 0; font-size: 12px; line-height: 1.7; color: var(--accent2); white-space: pre; }
.td-md :deep(table) { border-collapse: collapse; margin: 12px 0; width: 100%; font-size: 12.5px; }
.td-md :deep(th) { background: var(--panel-3); padding: 8px 10px; text-align: left; font-weight: 600; border: 1px solid var(--border); }
.td-md :deep(td) { padding: 7px 10px; border: 1px solid var(--border); line-height: 1.6; }
.td-md :deep(blockquote) { margin: 10px 0; padding: 8px 14px; border-left: 3px solid var(--accent); background: var(--accent-l); color: var(--muted); font-size: 12.5px; line-height: 1.7; }
.td-md :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 18px 0; }
.td-foot { margin-top: 30px; text-align: center; font-size: 11px; color: var(--faint); letter-spacing: 2px; }
</style>
