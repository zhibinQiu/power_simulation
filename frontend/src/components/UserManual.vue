<template>
  <div class="um-mask" @click.self="$emit('close')">
    <div class="um-modal" role="dialog" aria-modal="true" aria-label="使用手册">
      <div class="um-head">
        <span class="um-title">使用手册 · 操作逻辑详解</span>
        <button class="um-x" @click="$emit('close')" aria-label="关闭">×</button>
      </div>

      <div class="um-body">
        <nav class="um-toc">
          <div class="um-toc-title">目 录</div>
          <button v-for="(s, i) in sections" :key="s.id" class="um-toc-item"
                  :class="{ on: active === s.id }" @click="go(s.id)">
            <span class="um-toc-num">{{ i + 1 }}</span>{{ s.title }}
          </button>
        </nav>

        <div class="um-scroll" ref="scrollEl" @scroll="onScroll">
          <section v-for="s in sections" :key="s.id" :id="s.id" class="um-sec">
            <div class="um-md" v-html="renderMarkdown(s.body)"></div>
          </section>
          <div class="um-foot">—— 手册完 ——</div>
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
    id: 'overview',
    title: '界面总览与分区',
    body: `# 行业能碳仿真平台 · 使用手册

本手册按「操作逻辑」讲解：每一步在哪里点、点了之后会发生什么、如何退出并恢复原状。建议先通读第一章，再按章节动手操作。

## 一、界面分区

打开系统后，主界面自上而下、自左而右分为六大区域：

| 区域 | 位置 | 作用 |
| --- | --- | --- |
| 经典菜单条 | 最顶部一行 | 文件 / 仿真 / 视图 / 编辑 / 工具 / 帮助 六组下拉菜单 |
| 工具条 | 菜单条下方 | 单行按钮组，随当前模式（3D 孪生 / 编排画布）切换可用按钮（见第三章） |
| 资源管理器 | 左侧栏 | 「工艺 / 物料 / 策略」三个标签，浏览与选中资产 |
| 3D 孪生场景 | 中央 | 可视化全厂，点击工序聚焦、虚拟巡视、查看热力图 |
| 检视器 | 右侧栏 | 按当前选中对象显示总览 / 属性 / 报告等内容 |
| 命令行窗口 | 底部 | 输入自然语言、孪生控制命令，显示系统反馈日志 |

> 提示：左右两侧栏底部边缘有拖拽手柄，可按住左右拖动调整宽度，宽度会被记忆保存。

## 二、第一次使用建议流程

1. 先在左侧「工艺」中展开并点击任意工序，右侧检视器会显示该工序的属性。
2. 点击左侧「策略」标签，展开「内置」分组，点击任一策略查看说明。
3. 点击右侧该策略底部的「策略仿真」按钮，进入仿真模式体验参数对比。
4. 点击场景右上角「退出仿真」，所有修改自动恢复原状。

下面各章按区域逐一讲解操作逻辑。`,
  },
  {
    id: 'menubar',
    title: '顶栏菜单操作',
    body: `## 二、顶栏菜单操作

顶栏六个菜单点击后弹出下拉项。带灰色「禁用」状态的项当前不可用（如未运行仿真时的「停止」）。

### 文件

| 菜单项 | 操作逻辑 |
| --- | --- |
| 新建方案 | 点击后在命令行提示「已清空当前编排」，用于开始新的编排设计 |
| 打开方案… | 提示去左侧「策略」中载入已存方案（原型占位） |
| 保存方案 (Ctrl+S) | 将当前方案保存至本地工作区，命令行提示保存成功 |
| 连接数据源… | 弹出数据源配置对话框，选择实时数据来源（模拟 / WebSocket / HTTP 轮询） |
| 导出分析报告 | 若尚未运行仿真则提示「请先运行仿真」；否则打开右侧「报告面板」配置并生成报告 |
| 设置… | 打开系统设置对话框（LLM 模型与密钥配置等） |

### 仿真

| 菜单项 | 操作逻辑 |
| --- | --- |
| 运行仿真 (Ctrl+Enter) | 若已有启用的策略则按策略运行；否则重新计算全厂碳素流、能流与排放 |
| 重置仿真参数 | 重新计算并刷新全部结果，回到初始参数 |
| 应用当前情景 | 按当前选中的情景重新计算并应用到场景 |
| 高炉数值分析 (Alt+T) | 仅仿真模式下可用，打开高炉 TFT 数值分析面板（见第七章） |

### 视图

| 菜单项 | 操作逻辑 |
| --- | --- |
| 情景（子菜单） | 切换仿真情景（如钢铁、氢冶金等），勾选项为当前情景 |
| 环境（子菜单） | 切换 3D 环境主题：虚空 / 工业 / 沙漠 / 城市 / 海滩，勾选项为当前环境 |
| 刷新数据 | 立即重新拉取并刷新场景与检视器数据 |
| 自动布局工序 | 仅编排模式下可用，一键自动整理画布布局 |

### 编辑

| 菜单项 | 操作逻辑 |
| --- | --- |
| 进入流程编排 / 完成编排 | 切换「3D 场景」与「编排画布」两种工作模式（见第十章） |
| 撤销 (Ctrl+Z) / 重做 (Ctrl+Y) | 仅编排模式下可用，用于回退/重做画布操作 |
| 放大画布 / 缩小画布 / 适配视图 / 自动布局 | 仅编排模式下可用，编排画布视图控制 |
| 新建小组 / 进入子编排 / 复制小组 / 删除小组 | 仅编排模式下可用，对选中小组的分组操作 |
| 长流程示例 / 短流程示例 / 清空画布 | 仅编排模式下可用，一键载入示例流程 / 清空画布（清空不可撤销） |

### 工具

| 菜单项 | 操作逻辑 |
| --- | --- |
| 平台配置… | 打开平台配置对话框：工艺规模档位 / 设备量程 / 参数运行空间，保存后自动生效 |
| 碳素流守恒审计 | 打开守恒审计面板，核查全流程碳输入与输出的平衡（见第八章） |
| 参数优化 | 用自然语言描述优化目标，系统解析并执行（见第八章） |
| 数据校准 | 提示在右侧检视器选中设备查看实时/历史读数 |

### 帮助

| 菜单项 | 操作逻辑 |
| --- | --- |
| 使用指南 (F1) | 显示本手册 |
| 使用手册 | 打开本手册 |
| 技术文档 | 打开系统技术架构与算法详解 |
| 快捷键 | 命令行输出快捷键速查 |
| 关于本平台 | 显示版本与版权信息 |

> 操作逻辑要点：菜单项执行后大多在命令行窗口输出一条系统反馈，用于确认操作已生效。`,
  },
  {
    id: 'ribbon',
    title: '工具条操作',
    body: `## 三、工具条（单行按钮组）

工具条与菜单条配合使用，按钮随当前工作模式切换，没有标签页。

### 3D 孪生模式（默认）

| 按钮 | 操作逻辑 |
| --- | --- |
| 运行仿真 / 退出仿真 | 主开关。未进入仿真时显示「运行仿真」，点击后进入仿真模式（场景右上角出现对比浮层，所有修改仅预览）；已进入时显示「退出仿真」，点击后恢复仿真前状态 |
| 流程编排 / 完成编排 | 切换至编排画布工作模式 / 完成编排回到 3D 场景 |
| 自动环视 | 开关：开启后相机缓慢自动旋转环视全厂 |
| 虚拟巡视 | 开关：开启后部署机器狗，用 W/S/A/D 移动、Z/X 原地转向、Shift 加速，再次点击或按 Esc 退出 |
| 刷新视角 | 相机回到园区俯瞰视角 |
| 全屏 | 将场景区切换为全屏显示，Esc 退出 |
| 全景数据 | 仿真运行后可用，弹出全景数据对话框浏览全场数据 |
| 亮度 | 拖动滑杆调整场景环境光亮度 |

### 编排模式（进入流程编排后）

| 按钮 | 操作逻辑 |
| --- | --- |
| 撤销 / 重做 | 编排历史操作回退 |
| 自动布局 | 一键整理画布节点布局 |
| 放大 / 缩小 / 适配视图 | 编排画布的视图控制 |
| 长流程示例 / 短流程示例 | 一键载入示例流程 |
| 清空画布 | 删除画布全部节点连线（不可撤销，会二次确认） |

> 操作逻辑要点：工具条按钮执行后同样会在命令行给出反馈，注意观察命令行确认状态变化。`,
  },
  {
    id: 'sidebar',
    title: '左侧资源管理器',
    body: `## 四、左侧资源管理器

左侧栏三个标签：**工艺 / 物料 / 策略**。点击标签切换，点击条目即选中并联动右侧检视器。

### 工艺

- 展开「工艺」根节点，按 **长流程炼钢 / 短流程炼钢 / 节能减碳** 三个分组展示工序类型。
- 点击工序类型 → 右侧显示「工艺属性」（厂内实例及其实时数据）。
- 点击某台具体设备 → 右侧切换为「设备详情」，可调节运行设定（见第七章）。
- 点亮的圆点表示该工序/设施已部署至 3D 场景；右侧数字表示实例数量。

### 物料

- 按 **原料 / 中间产物 / 产品** 三组展示物料清单。
- 点击物料 → 右侧显示其隐含碳因子与配置信息。

### 策略

- **内置** 分组：按工艺展示绿色策略与系统预置策略。
  - 系统预置策略（图标带「已应用」圆点）：点击后右侧显示策略属性，底部有「策略仿真」按钮。
  - 工艺绿色策略（带「已启用」标签）：点击后右侧可勾选**启用 / 停用**，启用即实时参与仿真。
- **自定义（仿真保存）** 分组：仿真模式下保存的策略，可点击查看/编辑，右侧 ✕ 按钮删除。

> 操作逻辑要点：左侧所有条目都是「点击选中 → 右侧联动」模式，选中状态会高亮。`,
  },
  {
    id: 'scene',
    title: '3D 孪生场景',
    body: `## 五、3D 孪生场景

中央场景是系统的主视图，支持以下交互：

### 选中与聚焦

- **点击工序 / 设备**：选中并聚焦，右侧检视器联动显示属性。
- 按 **F** 可聚焦当前选中工序；或使用命令行 \`view top|front|side|focus\` 切换预设视角。

### 场景右上角按钮

- **保存策略**：仅仿真模式下显示。点击后在命令行提示「请在下方命令行输入策略名称后回车保存」，输入名称回车即保存到「策略 → 自定义」；输入 \`cancel\` 或 \`取消\` 可放弃。
- **退出仿真 / 进入仿真**：切换仿真模式。
- **对比浮层**：仿真模式下浮层展示「仿真前 → 当前」各工序关键指标变化，便于对比基准与策略后差异。

> 亮度调节、自动环视、虚拟巡视、全屏等按钮位于菜单条下方的工具条（见第三章）。

### 虚拟巡视（机器狗）

开启后使用键盘控制机器狗在园区行走：

| 按键 | 动作 |
| --- | --- |
| W / S | 前进 / 后退 |
| A / D | 左移 / 右移 |
| Z / X | 原地左转 / 右转 |
| Shift | 加速 |
| Esc 或再次点击「虚拟巡视」 | 退出巡视 |

> 建筑与工艺设施不可穿越，巡视时注意避让。`,
  },
  {
    id: 'inspector',
    title: '右侧检视器',
    body: `## 六、右侧检视器

检视器内容随「当前选中对象」联动，头部标题会随模式变化：

| 模式 | 出现条件 | 主要内容 |
| --- | --- | --- |
| 总览 | 未选中任何对象 | 全厂综合能耗/单位能耗/电耗、能碳流桑基图（碳素流/能流双标签）、排放最高工序（点击可跳转选中） |
| 工艺属性 | 点击左侧「工艺」工序 | 工艺类型说明、厂内实例列表、实时数据 |
| 物料 | 点击「物料」条目 | 隐含碳因子与配置 |
| 策略 | 点击「策略」条目 | 策略属性面板（见第八章） |
| 设备详情 | 点击具体设备 | 运行设定调节、衍生指标、实时/历史趋势（见第七章） |
| 报告 | 点击「文件 → 导出分析报告」或顶栏导出按钮 | 报告面板（见第十二章） |

### 总览中的交互

- 桑基图顶部可切换 **碳素流 / 能流** 两种视图。
- 点击「排放最高工序」卡片中的工序，场景自动聚焦到该工序并显示其属性。`,
  },
  {
    id: 'device',
    title: '设备属性与调节',
    body: `## 七、设备属性与调节

在左侧「工艺」树中点击某台设备，或在 3D 场景中点击设备实体，右侧进入「设备详情」。

### 运行设定

- 部分设备是**可调设备**（如高炉），显示运行设定滑块与输入框。
- 拖动滑块或输入数值即时生效；未进入仿真模式时调整会提示需要先进入仿真模式。
- 附加可调项（如鼓风机鼓风湿度）同样可直接调节。

### 高炉 TFT 面板

- 选中高炉类可调设备时，面板顶部出现 **TFT（理论燃烧温度）** 策略提示。
- 展示按当前风口参数折算的 TFT 值、判定结果（正常 / 过高 / 过低）与调节建议。
- 调节鼓风、喷煤等参数后，TFT 实时重新折算。

### 衍生指标与依据

- 展示设备运行产生的衍生指标（如热风温度、富氧率）。
- 「减碳影响依据」区块说明该设备调节影响哪些排放项（耦合透明度）。

### 趋势

- 设备详情内可查看实时遥测与历史趋势图。
- 实时数据经 WebSocket 推送，约 10 分钟环形缓冲，历史曲线随推送滚动更新。

> 操作逻辑要点：设备调节是「仿真模式」下最重要的交互——先进入仿真模式再调节，可随时退出恢复。`,
  },
  {
    id: 'strategy',
    title: '策略应用与仿真',
    body: `## 八、策略应用与仿真

系统提供三类策略，应用方式不同：

### 系统预置策略（内置）

1. 左侧「策略 → 内置」中点击目标策略（如「焦比优化」）。
2. 右侧出现策略属性面板，展示策略文本、理解的操作与预期减排效果。
3. 点击面板底部 **「策略仿真」** 按钮 → 自动进入仿真模式并解析执行该策略，场景右上角出现「对比浮层」显示基准与策略后的差异。
4. 满意后点击「保存策略」输入名称入库；或点击「退出仿真」恢复原状。

### 工艺绿色策略（内置 · 可启用）

1. 左侧「策略 → 内置」对应工艺分组下点击绿色策略。
2. 右侧面板中勾选 **启用** 开关 → 策略立即参与下一次仿真计算；再次取消勾选即停用。
3. 可在同一面板查看「所属工艺」并跳转到该工艺属性。

### 自定义策略（仿真保存）

1. 仿真模式下调整参数后，点击场景右上角「保存策略」，在命令行输入名称回车。
2. 该策略出现在左侧「策略 → 自定义」分组，带「自定义」标签。
3. 点击自定义策略 → 右侧面板可**编辑名称与数值调整**，点击「保存修改」生效，点击「策略仿真」重新加载执行。
4. 右侧 ✕ 按钮删除（需确认）。

### AI 生成策略（已支持）

- 内置策略面板、工序策略面板均提供**自然语言策略输入框**：输入如「焦比降低 5%」「喷煤提高 10%」，由 LLM 智能体（无密钥时自动回退本地引擎）解析为可执行参数操作，立即参与仿真计算。
- 解析结果展示为操作列表与置信度；无有效操作时提示重新描述。

### 仿真模式的通用规则

- **进入**：点击「运行仿真」、输入 \`/sim\` 或执行任一「策略仿真」。
- **预览**：进入后所有参数修改仅作用于预览，不改动原始方案。
- **退出**：点击「退出仿真」或输入 \`stop\`，自动恢复进入前的全部状态。
- **自然语言（仿真模式命令行）**：在命令行窗口直接输入操作指令由智能体解析为操作（规划中），敬请期待。`,
  },
  {
    id: 'sim',
    title: '仿真运行与情景',
    body: `## 九、仿真运行与情景

### 运行仿真

- 顶部「运行仿真」按钮或快捷键 **Ctrl+Enter**。
- 若已启用工艺策略 → 按策略重新计算；否则刷新全厂碳素流、能流与排放。
- 运行期间按钮变为「停止」，点击停止仿真循环。

### 情景切换

- 「视图 → 情景」子菜单选择情景，或通过命令行切换。
- 不同情景对应不同的工艺流程与排放水平（非钢铁情景当前为占位模型）。

### 重置

- 「仿真 → 重置仿真参数」重新计算回初始参数。
- 工具条「刷新视角」只复位相机，不影响仿真数据。

### 数据流说明

仿真计算链路：**设备运行参数 → 碳素流仿真引擎（后端）→ 各工序排放/能耗 → 全厂汇总 → 3D 热力图与检视器展示**。命令行会以 \`simulate >>\` 前缀输出每次计算的摘要。`,
  },
  {
    id: 'flowedit',
    title: '流程编排',
    body: `## 十、流程编排

编排模式用于拖拽式设计工艺流程图，编排完成后自动生成 3D 场景布局。

### 进入 / 退出编排

- 入口：菜单「编辑 → 进入流程编排」、工具条「流程编排」按钮或命令行 \`edit\`。
- 退出：菜单「编辑 → 完成编排」、工具条「完成编排」按钮或命令行 \`done\`。

### 画布操作

| 操作 | 方式 |
| --- | --- |
| 添加节点 | 从左侧「工艺 / 物料」中**拖拽**条目到画布（编排态下条目变为可拖拽） |
| 连接流程 | 从节点输出端口拖向另一节点输入端口画线 |
| 修改物料 | 双击节点端口弹出物料选择 |
| 右键菜单 | 右键节点或资源打开上下文菜单：选中 / 参数敏感性扫描 / 重命名 / 复制 / 删除 |
| 删除连线 | 点击选中连线后按 Del |
| 删除节点 | 点击节点右上角 ✕，或选中后按 Del |
| 重命名 / 复制节点 | 选中节点后按 F2 重命名、Ctrl+D 复制（编排模式） |
| 平移 / 缩放 | 画布空白拖拽平移，滚轮缩放 |
| 自动布局 | 工具条「自动布局」按钮一键整理布局 |
| 撤销 / 重做 | Ctrl+Z / Ctrl+Y（仅编排模式） |

### 小组与子编排

- 「编辑 → 新建小组」可将选中节点归组；组可整体拖动、复制、删除，并可「进入子编排」在组内嵌套编辑流程图。
- 小组在 3D 场景中呈现为独立布局区域。

### 示例与清空

- 工具条「长流程示例 / 短流程示例」一键载入完整示例流程。
- 「清空画布」删除画布全部内容（不可撤销，会二次确认）。

### 完成编排

点击「完成编排」回到 3D 场景，画布中的节点自动生成设施布局；此后仍可在左侧资产树中继续管理。`,
  },
  {
    id: 'cmd',
    title: '命令行窗口',
    body: `## 十一、命令行窗口

命令行是系统的「交互中枢」，输入后回车执行，反馈输出到上方日志区。

### 三种模式

| 模式 | 切换方式 | 用途 |
| --- | --- | --- |
| 聊天 | 默认 / \`/back\` 返回 | 直接输入自然语言与助手对话 |
| 代码 | \`/code\` | 以资深程序员助手身份回答编程问题 |
| 规划 | \`/plan\` | 把诉求拆解为有序可执行步骤 |

- \`/quit\`：退出当前模式回到聊天。
- \`/clear\`：清空日志区。

### 孪生控制命令（首词命中即执行）

| 命令 | 行为 |
| --- | --- |
| \`help\` | 输出全部命令说明 |
| \`run\` / \`sim\` | 运行仿真 / 进入仿真模式 |
| \`stop\` | 停止仿真 / 退出仿真模式 |
| \`reset\` | 重置相机视角 |
| \`overview\` / \`home\` | 相机回到全景 |
| \`patrol\` | 开启/关闭虚拟巡视 |
| \`view top|front|side|focus\` | 按预设视角聚焦当前选中工序 |
| \`edit\` | 进入流程编排 |
| \`done\` | 完成编排 |
| \`clear\` | 清屏 |

### 特殊流程：保存策略

仿真模式下点击场景「保存策略」后，命令行进入「等待输入名称」状态：

- 输入名称并回车 → 策略保存至「自定义」分组。
- 输入 \`cancel\` 或 \`取消\` → 放弃保存。

### 自然语言

- 聊天模式下：非命令内容直接对话。
- 仿真模式下：非命令内容交由智能体解析为仿真操作（规划中），命令行会提示规划进度。`,
  },
  {
    id: 'report',
    title: '报告生成与导出',
    body: `## 十二、报告生成与导出

### 前置条件

必须先运行过一次仿真（存在仿真数据），否则点击导出会提示「请先运行仿真」。

### 操作路径

1. 菜单「文件 → 导出分析报告」或顶栏右侧「导出」按钮（未运行仿真会提示先运行）。
2. 右侧打开「报告面板」，配置：
   - 报告标题（留空则自动拼接「策略名 · 场景」）；
   - 生成引擎：自动 / AI 生成 / 本地模板（AI 无密钥时自动回退本地模板）；
   - 分析深度：精简 / 标准 / 深入；
   - 是否包含「附录：全流程明细」表格。
3. 点击 **「生成报告」**，等待进度完成后查看。
4. 生成后可在面板内复制内容、下载 Markdown、或在**新页面打开 HTML 报告**（可打印/分享）。
5. 历史报告保存在报告列表，可再次查看或删除。

### 报告内容

报告基于当前仿真结果自动汇总：全厂能耗与碳排放总量、各工序排放分布、所应用策略的减排效果对比、优化建议（AI 引擎含数据洞察与策略评估段落）。所有数值表格由本地代码生成，保证精确可复现。`,
  },
  {
    id: 'faq',
    title: '快捷键与常见问题',
    body: `## 十三、快捷键与常见问题

### 快捷键速查

| 快捷键 | 功能 |
| --- | --- |
| Ctrl+Enter | 运行仿真 |
| Ctrl+S | 保存方案 |
| Ctrl+Z / Ctrl+Y | 撤销 / 重做（编排模式） |
| F | 聚焦当前选中的工序（3D 场景） |
| F1 | 打开使用指南（本手册） |
| Alt+T | 高炉数值分析（仅仿真模式） |
| F2 | 重命名选中节点（编排模式） |
| Ctrl+D | 复制选中节点（编排模式） |
| Del | 删除选中节点 / 连线（编排模式） |
| Esc | 关闭对话框 / 退出虚拟巡视 / 退出全屏 |

### 常见问题（Q&A）

**Q1：为什么点击导出报告提示「请先运行仿真」？**
报告需要仿真结果数据，请先按 Ctrl+Enter 或「仿真 → 运行仿真」执行一次计算。

**Q2：在设备上调节了参数，为什么退出仿真后参数又变回去了？**
这是仿真模式的预期行为——所有修改仅在预览层生效，退出时自动恢复原状。若希望保留，请在退出前点击「保存策略」将当前参数存为自定义策略。

**Q3：如何把调节好的参数保存下来复用？**
进入仿真模式 → 调节参数 → 点击场景右上角「保存策略」→ 命令行输入名称回车 → 之后在左侧「策略 → 自定义」中随时加载。

**Q4：左侧策略带「已启用」标签和带圆点的策略有什么区别？**
带「已启用」的是工艺绿色策略，通过右侧开关勾选参与计算；带圆点且可「策略仿真」的是系统预置策略，通过底部按钮测试执行。

**Q5：虚拟巡视时卡在建筑里怎么办？**
建筑与设施不可穿越，用 Z/X 原地转向换个方向即可；或再次点击「虚拟巡视」退出重进。

**Q6：命令行输入命令没反应？**
请确认首词拼写与命令表一致（如 \`view focus\` 需要先选中工序）；非命令内容会走自然语言对话，不会当作命令执行。

**Q7：想撤销编排画布上误删的节点？**
编排模式下按 Ctrl+Z 可撤销（含删除操作）；注意「清空画布」不可撤销，操作前会二次确认。

**Q8：环境切换后 3D 场景没变化？**
环境主题（虚空/工业/沙漠/城市/海滩）只影响场景背景与氛围，不影响设施与仿真数据；若画面异常可用工具条「刷新视角」复位相机。`,
  },
]

// 滚动高亮当前章节
function go(id) {
  active.value = id
  const el = scrollEl.value && scrollEl.value.querySelector('#' + id)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}
function onScroll() {
  const wrap = scrollEl.value
  if (!wrap) return
  const secs = wrap.querySelectorAll('.um-sec')
  let cur = sections[0].id
  for (const s of secs) {
    if (s.getBoundingClientRect().top - wrap.getBoundingClientRect().top < 120) cur = s.id
  }
  active.value = cur
}
onMounted(() => { active.value = sections[0].id })
onBeforeUnmount(() => {})
</script>

<style scoped>
.um-mask { position: fixed; inset: 0; background: rgba(10,16,24,.55); display: flex; align-items: center; justify-content: center; z-index: 200; backdrop-filter: blur(2px); }
.um-modal { width: 1180px; max-width: 96vw; height: 88vh; max-height: 94vh; background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
  box-shadow: 0 20px 60px rgba(0,0,0,.35); font-family: var(--ui); color: var(--text); display: flex; flex-direction: column; overflow: hidden; }
.um-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); background: var(--panel-2); flex: none; }
.um-title { font-size: 14px; font-weight: 700; letter-spacing: .5px; }
.um-x { border: none; background: transparent; font-size: 16px; line-height: 1; color: var(--muted); cursor: pointer; padding: 0 4px; }
.um-x:hover { color: var(--text); }

.um-body { display: flex; flex: 1; min-height: 0; }
.um-toc { width: 232px; flex: none; border-right: 1px solid var(--border); background: var(--panel-2); overflow-y: auto; padding: 14px 10px; }
.um-toc-title { font-size: 11px; font-weight: 700; color: var(--muted); letter-spacing: 2px; margin: 0 6px 10px; }
.um-toc-item { display: flex; align-items: center; gap: 8px; width: 100%; padding: 8px 10px; margin-bottom: 2px;
  border: none; border-radius: 6px; background: transparent; color: var(--text); font-size: 12.5px; font-family: var(--ui);
  text-align: left; cursor: pointer; line-height: 1.45; transition: background .15s; }
.um-toc-item:hover { background: var(--accent-l); }
.um-toc-item.on { background: var(--accent-l); color: var(--accent-d); font-weight: 600; }
.um-toc-num { flex: none; width: 18px; height: 18px; display: inline-flex; align-items: center; justify-content: center;
  border-radius: 4px; background: var(--panel-3); color: var(--muted); font-size: 10px; font-weight: 600; }
.um-toc-item.on .um-toc-num { background: var(--accent); color: #fff; }

.um-scroll { flex: 1; overflow-y: auto; padding: 26px 34px 40px; min-width: 0; }
.um-sec { scroll-margin-top: 8px; }
.um-md { max-width: 860px; }
.um-md :deep(h1) { font-size: 22px; font-weight: 800; margin: 0 0 14px; padding-bottom: 10px; border-bottom: 2px solid var(--accent); letter-spacing: .3px; }
.um-md :deep(h2) { font-size: 17px; font-weight: 700; margin: 30px 0 12px; color: var(--accent-d); }
.um-md :deep(h3) { font-size: 14.5px; font-weight: 700; margin: 22px 0 8px; }
.um-md :deep(p) { font-size: 13.5px; line-height: 1.85; margin: 8px 0; color: var(--text); }
.um-md :deep(ul), .um-md :deep(ol) { margin: 8px 0 8px 22px; font-size: 13.5px; line-height: 1.85; }
.um-md :deep(li) { margin: 3px 0; }
.um-md :deep(code) { background: var(--panel-3); padding: 1px 6px; border-radius: 4px; font-size: 12px; font-family: "SF Mono", Menlo, Consolas, monospace; }
.um-md :deep(pre.rp-code) { background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 14px 16px; overflow-x: auto; margin: 10px 0; }
.um-md :deep(pre.rp-code code) { background: none; padding: 0; font-size: 12px; line-height: 1.7; color: var(--accent2); white-space: pre; }
.um-md :deep(table) { border-collapse: collapse; margin: 12px 0; width: 100%; font-size: 12.5px; }
.um-md :deep(th) { background: var(--panel-3); padding: 8px 10px; text-align: left; font-weight: 600; border: 1px solid var(--border); }
.um-md :deep(td) { padding: 7px 10px; border: 1px solid var(--border); line-height: 1.6; }
.um-md :deep(blockquote) { margin: 10px 0; padding: 8px 14px; border-left: 3px solid var(--accent); background: var(--accent-l); color: var(--muted); font-size: 12.5px; line-height: 1.7; }
.um-md :deep(hr) { border: none; border-top: 1px solid var(--border); margin: 18px 0; }
.um-foot { margin-top: 30px; text-align: center; font-size: 11px; color: var(--faint); letter-spacing: 2px; }
</style>
