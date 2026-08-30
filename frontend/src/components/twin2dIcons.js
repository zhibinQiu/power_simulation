// 2D 工艺视图标准工业图符库（24×24 线性符号，参考西门子 WinCC / ISA 风格）
// 每个图标为元素描述数组，由 Twin2DView 渲染为 SVG；stroke 继承 currentColor（与状态色联动）。
// 设计原则：单线条、几何化、克制装饰——符合 ISA-101 信息清晰优先。

const C = { stroke: 'currentColor', sw: 1.5, lc: 'round', lj: 'round', fill: 'none' }
const P = (d) => ({ tag: 'path', d, ...C })
const CIRC = (cx, cy, r) => ({ tag: 'circle', cx, cy, r, stroke: 'currentColor', sw: 1.5, fill: 'none' })
const ELL = (cx, cy, rx, ry) => ({ tag: 'ellipse', cx, cy, rx, ry, stroke: 'currentColor', sw: 1.5, fill: 'none' })
const RECT = (x, y, w, h, rx) => ({ tag: 'rect', x, y, width: w, height: h, rx: rx || 0, stroke: 'currentColor', sw: 1.5, fill: 'none' })

export const T2D_ICONS = {
  // —— 主工艺（炼铁/炼钢/轧钢） ——
  sinter_plant: /* 烧结机：台车 + 点火罩 + 料层 */ [
    P('M5 11 h14 M5 11 v6 h14 v-6'),
    P('M7 17 v2 M12 17 v2 M17 17 v2'),
    P('M8 11 v-3 M16 11 v-3 M8 8 h8'),
    P('M11 8 l1 2 1 -2'),
  ],
  pelletizing: /* 球团：倾斜圆盘造球机 */ [
    CIRC(12, 13, 7),
    P('M7.5 8.5 L16.5 17.5'),
    P('M11 13 h2 M12 12 v2'),
    P('M16 5 h5 M18 5 v-2'),
  ],
  coke_oven: /* 焦炉：多室竖炉 + 烟囱 */ [
    P('M4 8 v10 h16 v-10'),
    P('M4 8 h16 M9.3 8 v10 M14.6 8 v10'),
    P('M6 6 v-2 M10 6 v-2 M14 6 v-2 M18 6 v-2'),
  ],
  blast_furnace: /* 高炉 BF：炉身 + 料钟 + 风口/出铁 */ [
    P('M9 3 h6 M9 3 v2 h-2 v5 a5 5 0 0 0 -2 4 h14 a5 5 0 0 0 -2 -4 V5 h-2 V3'),
    P('M7.5 10 h9 M5.5 16 h13'),
    P('M12 17 v3'),
  ],
  hot_metal_pretreat: /* 铁水预处理：铁水包 + 喷枪 */ [
    P('M7 9 h10 l-2 8 H9 z'),
    P('M12 3 v6 M9.5 9 h5'),
    P('M9.5 13 h5 M10 13 v-1.5 M14 13 v-1.5'),
  ],
  bof: /* 转炉 BOF：梨形容器 + 氧枪 + 倾转轴 */ [
    P('M9.5 3 h5 M9.5 3 v3 q-4 4 -3 9 a6 6 0 0 0 11 0 q1 -5 -3 -9 V3'),
    P('M12 1 v4'),
    P('M5.5 13 h3 M15.5 13 h3'),
  ],
  ladle_furnace: /* 钢包精炼 LF：钢包 + 三电极 */ [
    P('M7 11 h10 l-1.5 7 h-7 z'),
    P('M8.5 11 V6 M12 11 V4 M15.5 11 V6'),
    P('M8.5 6 h-1.5 M15.5 6 h1.5 M12 4 v-1.5'),
  ],
  rh_vacuum: /* RH 真空精炼：真空罐 + 双循环管 */ [
    ELL(12, 4.5, 5.5, 2.5),
    P('M8.5 6 v8 M15.5 6 v8 M8.5 14 h7'),
    P('M9 6 v4 h6 M9 10 h6 M12 10 v2'),
    P('M12 17 v2'),
  ],
  caster: /* 连铸机 CCM：结晶器 + 拉坯辊 + 铸坯 */ [
    P('M8 3 h8 v5 h-8 z'),
    P('M12 8 v8'),
    CIRC(8.5, 12.5, 1.2),
    CIRC(15.5, 12.5, 1.2),
    P('M10.5 18 h3'),
  ],
  rolling_mill: /* 热轧机 RM：双辊 + 板坯 */ [
    ELL(8.5, 7, 4, 2.6),
    ELL(8.5, 17, 4, 2.6),
    P('M13 10 h7 v4 h-7'),
    P('M15 10 v4 M17.5 10 v4'),
  ],
  eaf: /* 电弧炉 EAF：炉体 + 三电极 */ [
    P('M6 10 h12 v4 h-12 z'),
    P('M8 14 v4 h8 v-4'),
    P('M8 6 v4 M12 4.5 v5.5 M16 6 v4'),
  ],
  dri_midrex: /* DRI 竖炉（Midrex）：还原竖炉 + 煤气 */ [
    P('M8 3 h8 M8 3 v9 l-2.5 8 h9 l-2.5 -8 V3'),
    P('M7.5 9 h9 M6 13.5 h12'),
    P('M12 3 v-1.5 M11 2.5 h2'),
  ],
  reheating_furnace: /* 加热炉：长条形炉 + 火焰 */ [
    P('M4 8 h16 v8 h-16 z M4 8 h16'),
    P('M8 12 l1 -2 1 2 M12 12 l1 -2 1 2 M16 12 l1 -2 1 2'),
  ],

  // —— 公用 / 节能减碳 ——
  gas_power: /* 煤气发电：透平 + 发电机 */ [
    CIRC(9, 12, 5),
    P('M9 8.5 v7 M6.5 10.5 l5 3 M6.5 13.5 l5 -3'),
    P('M14 12 h6 M17 12 v-2 M17 12 v2'),
  ],
  waste_heat: /* 余热回收：换热器 + 波纹管 */ [
    P('M4 7 h16 M4 17 h16'),
    P('M5.5 7 v10 M12 7 q-2 2.5 0 5 q2 2.5 0 5 M18.5 7 v10'),
    P('M20 10 h2 M20 14 h2'),
  ],
  ccs: /* 碳捕集：吸收塔 + 填料 + 液体 */ [
    P('M7 3 h10 v10 h-10 z'),
    P('M7 7 h10 M9 3 v4 M12 3 v4 M15 3 v4'),
    P('M5 13 h14 v5 h-14 z'),
    P('M8 15.5 h8'),
  ],

  // —— 工辅（风机/泵/炉/电） ——
  blower: /* 鼓风机：蜗壳 + 叶轮 */ [
    CIRC(10.5, 12, 6),
    P('M10.5 8.5 v7 M8 10.5 l5 3 M8 13.5 l5 -3'),
    P('M16.5 12 h4 M17.5 10 v4'),
  ],
  hot_blast_stove: /* 热风炉：圆筒 + 格子砖 + 顶 */ [
    P('M7 4 h10 v14 h-10 z M7 4 q5 3 10 0'),
    P('M7 8 h10 M9 4 v4 M12 4 v4 M15 4 v4 M9 12 h6'),
    P('M10 16 h4 M12 16 v2'),
  ],
  id_fan: /* 引风机：轴流叶片 */ [
    CIRC(12, 12, 6.5),
    P('M12 8.5 a4.5 4.5 0 0 1 3.2 5.9 M12 15.5 a4.5 4.5 0 0 1 -3.2 -5.9'),
    P('M12 6 v2.5 M12 15.5 V18'),
  ],
  injector: /* 喷吹系统：喷枪斜插 + 料流 */ [
    P('M3 18 L14 7'),
    P('M14 7 l3.5 -1 -1 3.5 z'),
    P('M6.5 14.5 h-2 M10 11 h-2'),
  ],
  combustion_blower: /* 助燃风机：离心叶轮 */ [
    CIRC(11, 11, 5),
    P('M11 8 a3.5 3.5 0 0 1 2.6 4.3 M11 14 a3.5 3.5 0 0 1 -2.6 -4.3'),
    P('M16 11 h5 M16 11 v-2.5'),
  ],
  drive_supply: /* 驱动供电：电机 + 输出轴 */ [
    RECT(3, 8.5, 9, 7, 1.5),
    P('M12 12 h8 M17 9 v6'),
    P('M6.5 11.5 h2'),
  ],
  electrode_reg: /* 电极调节：电极 + 双向箭头 */ [
    P('M11 4 h2 v16 h-2 z'),
    P('M12 4 V2 M12 22 v-2'),
    P('M8 2 l4 -2 4 2 M8 22 l4 2 4 -2'),
  ],
  belt_conv: /* 皮带机：输送带 + 托辊 */ [
    P('M3 10 h18 M3 10 v4 h18 v-4'),
    P('M8 10 v4 M13 10 v4 M18 10 v4'),
    CIRC(3, 10, 1.2),
    CIRC(21, 10, 1.2),
  ],
  feeder: /* 给料机：料斗 + 出料槽 */ [
    P('M7 4 h10 l-2 6 h-6 z'),
    P('M9 10 l-3 7 M15 10 l3 7'),
    P('M7 14 h10'),
  ],
  cool_pump: /* 冷却水泵：泵体 + 叶轮 + 管路 */ [
    CIRC(11, 12, 5),
    P('M11 9.5 v5 M9.2 10.8 l3.6 2.4 M9.2 13.2 l3.6 -2.4'),
    P('M16 12 h4 M18 9.5 v5'),
  ],
  aux_boiler: /* 辅助锅炉：炉体 + 火焰 + 烟囱 */ [
    P('M6 8 h12 v9 h-12 z'),
    P('M10 8 v-3 h4 v3'),
    P('M8 15 l1 -2 1 2 1 -2 1 2'),
    P('M6 13 h12'),
  ],
  oxy_plant: /* 空分制氧：双精馏塔 + 连接管 */ [
    P('M5 4 h4 v15 h-4 z M15 7 h4 v12 h-4 z'),
    P('M5 7 h4 M15 10 h4 M9 10 h6'),
  ],
  oxy_supply: /* 供氧系统：氧瓶 + 阀门 */ [
    RECT(9, 4, 6, 16, 3),
    P('M12 4 v-2 M10.5 2 h3'),
    P('M11.5 8 h1'),
  ],
  power_supply: /* 供电系统：变电站 + 母线 */ [
    P('M12 3 l5 17 H7 z'),
    P('M4 12 h16 M7 12 v-3 M17 12 v-3'),
    P('M12 12 v5'),
  ],
  default: /* 通用：齿轮工艺 */ [
    CIRC(12, 12, 4),
    P('M12 5 v2.5 M12 16.5 V19 M5 12 h2.5 M16.5 12 H19'),
    P('M7.1 7.1 l1.8 1.8 M15.1 15.1 l1.8 1.8 M16.9 7.1 l-1.8 1.8 M8.9 15.1 l-1.8 1.8'),
  ],
}

// 2D 视图图例中展示的工艺图标清单（主工艺 + 代表性工辅）
export const T2D_LEGEND = [
  { type: 'sinter_plant', label: '烧结机' },
  { type: 'coke_oven', label: '焦炉' },
  { type: 'blast_furnace', label: '高炉' },
  { type: 'bof', label: '转炉' },
  { type: 'caster', label: '连铸机' },
  { type: 'rolling_mill', label: '热轧机' },
  { type: 'blower', label: '鼓风机' },
  { type: 'cool_pump', label: '冷却水泵' },
]
