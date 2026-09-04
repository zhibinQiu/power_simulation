// 2D 工艺视图工业设备图符库（立体填色版，参考 ISA-101 + WinCC 实物风）
// 每个图标为元素描述数组，元素支持 tag/path/circle/ellipse/rect/polygon：
//   stroke: 描边色（默认 currentColor）
//   fill:   填充色（字符串、url(#id) 或 null/none）
//   sw:     描边宽
// 设计原则：立体填色 + 适度细节（端口/风口/料钟），主设备高温区用橙红渐变。

// 共享样式辅助
const S = (extra = {}) => ({ stroke: 'currentColor', sw: 1.2, fill: 'none', ...extra })
const P = (d, extra = {}) => ({ tag: 'path', d, ...S(extra) })
const C = (cx, cy, r, extra = {}) => ({ tag: 'circle', cx, cy, r, ...S(extra) })
const E = (cx, cy, rx, ry, extra = {}) => ({ tag: 'ellipse', cx, cy, rx, ry, ...S(extra) })
const R = (x, y, w, h, extra = {}) => ({ tag: 'rect', x, y, width: w, height: h, ...S(extra) })
const G = (pts, extra = {}) => ({ tag: 'polygon', pts, ...S(extra) })

// —— 主工艺（炼铁/炼钢/轧钢） ——
export const T2D_ICONS = {
  // 烧结机：长传送带 + 抽风罩 + 料层（橙红热态）
  sinter_plant: [
    R(2, 13, 20, 5, { fill: 'url(#g-metal-v)', stroke: '#5a6a78' }),          // 传送带
    R(2, 11, 20, 2, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),            // 料层
    R(4, 8, 16, 3, { fill: 'url(#g-metal-v)', stroke: '#5a6a78' }),           // 抽风罩
    R(4, 18, 1.4, 3, { fill: '#5a6a78' }),                                    // 立柱
    R(18.6, 18, 1.4, 3, { fill: '#5a6a78' }),
    C(4, 21.5, 1.1, { fill: '#3a4654', stroke: '#3a4654' }),                  // 托辊
    C(20, 21.5, 1.1, { fill: '#3a4654', stroke: '#3a4654' }),
  ],
  // 球团：倾斜圆盘造球机
  pelletizing: [
    E(12, 13, 7, 5, { fill: 'url(#g-metal-v)', stroke: '#5a6a78', transform: 'rotate(-15 12 13)' }),
    C(12, 13, 2.5, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),
    P('M16 4 h5 M19 4 v-2', { stroke: '#5a6a78' }),                            // 支架
    P('M19 4 v6', { stroke: '#5a6a78' }),
  ],
  // 焦炉：多室炉体 + 顶部煤气管道 + 烟囱
  coke_oven: [
    R(3, 9, 18, 9, { fill: 'url(#g-metal-d)', stroke: '#3a4654' }),           // 炉体
    R(5, 11, 1.4, 5, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),           // 炉门×3（热态）
    R(10, 11, 1.4, 5, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),
    R(15, 11, 1.4, 5, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),
    R(20, 11, 1.4, 5, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),
    R(2, 7, 20, 1.5, { fill: 'url(#g-metal-v)', stroke: '#5a6a78' }),         // 顶部集气
    P('M7 7 v-3 M12 7 v-3 M17 7 v-3', { stroke: '#5a6a78' }),                  // 上升管
    P('M2 6 v-2 M22 6 v-2', { stroke: '#5a6a78' }),                            // 主管
  ],
  // 高炉 BF：炉身 + 料钟 + 风口/出铁/渣（中心元素，最精细）
  blast_furnace: [
    R(7, 4, 10, 16, { fill: 'url(#g-metal-d)', stroke: '#3a4654', rx: 1 }),    // 炉身
    R(8, 14, 8, 2, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),             // 风口带
    R(11, 20, 3, 2.5, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),          // 出铁口
    C(15.5, 17, 0.9, { fill: '#fff176', stroke: '#a04018' }),                  // 渣口亮黄
    P('M5 4 h14 M5 3 l4 -2 h6 l4 2', { fill: 'url(#g-metal-v)', stroke: '#5a6a78' }), // 炉顶圈
    R(10, 0.5, 4, 1.6, { fill: 'url(#g-metal-v)', stroke: '#5a6a78', rx: 0.5 }), // 料钟
    P('M12 0.5 v-1', { stroke: '#5a6a78' }),                                   // 料钟顶
    P('M2 1 h8 M2 1 v-1 M10 0', { stroke: '#5a6a78' }),                       // 斜桥
    R(6, 22.5, 12, 1.5, { fill: 'url(#g-metal-d)', stroke: '#3a4654' }),      // 炉基
  ],
  // 铁水预处理：铁水包 + 喷枪 + 烟雾
  hot_metal_pretreat: [
    G([[6, 10], [18, 10], [16.5, 19], [7.5, 19]], { fill: 'url(#g-hot-v)', stroke: '#a04018' }),
    R(6.5, 17, 9, 1.5, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),         // 渣层
    P('M12 3 v7', { stroke: '#5a6a78', sw: 1.6 }),
    R(10.5, 10, 3, 1.4, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),      // 喷枪头
    P('M9 13.5 h-2 M13 13.5 h2', { stroke: '#5a6a78' }),                      // 喷吹
  ],
  // 转炉 BOF：梨形炉 + 氧枪 + 倾转耳轴
  bof: [
    G([[9, 3], [15, 3], [18, 5], [19, 13], [15, 21], [9, 21], [5, 13], [6, 5]], { fill: 'url(#g-hot-v)', stroke: '#a04018' }),
    R(9, 19.5, 6, 1.5, { fill: 'url(#g-hot-h)', stroke: '#7a2a10' }),          // 渣
    P('M12 1.5 v3', { stroke: '#5a6a78', sw: 1.6 }),                          // 氧枪
    R(11, 4.5, 2, 1, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),         // 氧枪头
    C(4, 13, 1.2, { fill: '#3a4654', stroke: '#3a4654' }),                     // 左耳轴
    C(20, 13, 1.2, { fill: '#3a4654', stroke: '#3a4654' }),                    // 右耳轴
  ],
  // 钢包精炼 LF：钢包 + 三电极 + 电弧
  ladle_furnace: [
    G([[6, 11], [18, 11], [17, 19], [7, 19]], { fill: 'url(#g-metal-d)', stroke: '#3a4654' }),
    R(7, 18, 10, 1.4, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),          // 钢液
    P('M8.5 11 V4 M12 11 V2 M15.5 11 V4', { stroke: '#5a6a78', sw: 1.4 }),     // 三电极
    P('M8.5 4.5 l-1.2 -1.2 M8.5 4.5 l1.2 -1.2 M15.5 4.5 l-1.2 -1.2 M15.5 4.5 l1.2 -1.2 M12 2.5 v-1.5', { stroke: '#5a6a78' }),
  ],
  // RH 真空精炼：双环真空罐 + 循环管
  rh_vacuum: [
    E(12, 5, 5, 2.2, { fill: 'url(#g-metal-d)', stroke: '#3a4654' }),         // 真空罐
    P('M8 6.5 v8 M16 6.5 v8', { stroke: '#5a6a78', sw: 1.4 }),                // 双循环管
    R(7, 14, 10, 1, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),            // 钢液
    R(8, 18, 8, 1, { fill: 'url(#g-metal-d)', stroke: '#3a4654' }),           // 底座
  ],
  // 连铸机 CCM：结晶器 + 弯曲辊 + 二次冷却
  caster: [
    R(8, 2, 8, 4, { fill: 'url(#g-metal-d)', stroke: '#3a4654', rx: 0.5 }),   // 结晶器
    R(8.5, 6, 7, 1, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),            // 钢液
    P('M11 7 v3 l-1 2 v2 l-1 2 v2 l-1 2 v2', { fill: 'none', stroke: '#a04018', sw: 1.6 }), // 铸坯
    C(8, 9, 1.1, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),             // 辊1
    C(7, 12, 1.1, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),             // 辊2
    C(6, 15, 1.1, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),             // 辊3
    C(5, 18, 1.1, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),             // 辊4
    P('M3 6 l-1 1 M3 10 l-1 1 M3 14 l-1 1 M3 18 l-1 1', { stroke: '#2c6e9e' }), // 喷淋
  ],
  // 轧机 RM：上下辊系 + 板坯
  rolling_mill: [
    E(8, 7, 4, 2.2, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),          // 上辊
    E(8, 17, 4, 2.2, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),         // 下辊
    R(13, 10, 7, 4, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),             // 板坯（热）
    P('M15 10 v4 M17.5 10 v4', { stroke: '#3a4654' }),
    R(2, 11.5, 2, 1.5, { fill: '#5a6a78' }),                                   // 机架
  ],
  // 电弧炉 EAF：炉体 + 三电极 + 出钢槽
  eaf: [
    G([[5, 9], [19, 9], [18, 16], [15, 18], [9, 18], [6, 16]], { fill: 'url(#g-hot-v)', stroke: '#a04018' }),
    R(6, 15, 12, 1.2, { fill: '#fff176', stroke: '#a04018' }),                 // 钢液
    P('M7 9 V3 M12 9 V2 M17 9 V3', { stroke: '#5a6a78', sw: 1.4 }),            // 三电极
    P('M19 13 l3 1 l-3 1 z', { fill: '#5a6a78' }),                             // 出钢槽
  ],
  // DRI 竖炉：还原竖炉 + 顶/底煤气
  dri_midrex: [
    G([[8, 3], [16, 3], [16, 8], [19, 11], [17, 20], [7, 20], [5, 11], [8, 8]], { fill: 'url(#g-metal-d)', stroke: '#3a4654' }),
    R(8, 9, 8, 1, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),
    R(6, 13, 12, 1, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),
    P('M12 3 v-1.5 M11 2 h2', { stroke: '#5a6a78' }),
  ],
  // 加热炉：长条炉 + 内部火焰
  reheating_furnace: [
    R(3, 8, 18, 10, { fill: 'url(#g-metal-d)', stroke: '#3a4654', rx: 0.6 }),
    R(3, 8, 18, 2, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),
    P('M6 13 l1 -1.5 l1 1.5 l1 -1.5 l1 1.5 l1 -1.5 l1 1.5 l1 -1.5 l1 1.5 l1 -1.5 l1 1.5', { stroke: '#ff7a30', sw: 1 }),
    R(3, 18, 18, 1, { fill: '#ff7a30', stroke: '#a04018' }),                   // 板坯出料
  ],

  // —— 公用 / 节能减碳 ——
  // 煤气发电：透平叶片 + 发电机
  gas_power: [
    C(8, 12, 4.5, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),
    P('M8 8.5 l1 3.5 l-1 3.5 l-1 -3.5 z', { fill: '#5a6a78', stroke: '#3a4654' }),
    P('M8 8.5 l-1 3.5 l1 3.5 l1 -3.5 z', { fill: '#5a6a78', stroke: '#3a4654' }),
    R(13, 9, 7, 6, { fill: 'url(#g-metal-d)', stroke: '#3a4654', rx: 0.5 }),
    P('M14.5 12 h5 M17 12 v-2 M17 12 v2', { stroke: '#3a4654' }),
  ],
  // 余热锅炉：换热器 + 烟囱
  waste_heat: [
    R(3, 6, 14, 12, { fill: 'url(#g-metal-d)', stroke: '#3a4654', rx: 0.5 }),
    P('M5 6 v12 M8 6 v12 M11 6 v12 M14 6 v12', { stroke: '#5a6a78' }),         // 换热管
    R(5, 7, 10, 1, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),
    R(5, 16, 10, 1, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),
    R(18, 4, 3, 16, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),          // 烟囱
  ],
  // 碳捕集 CCS：吸收塔 + 填料 + 料仓
  ccs: [
    G([[7, 3], [17, 3], [17, 13], [7, 13]], { fill: 'url(#g-metal-d)', stroke: '#3a4654' }),
    P('M9 4 v9 M11 4 v9 M13 4 v9 M15 4 v9', { stroke: '#5a6a78' }),            // 填料
    R(5, 14, 14, 5, { fill: 'url(#g-metal-d)', stroke: '#3a4654' }),           // 料仓
    R(7, 16, 10, 1, { fill: 'url(#g-cool-h)', stroke: '#2c6e9e' }),            // 液体
  ],

  // —— 工辅（风机/泵/炉/电） ——
  // 鼓风机：蜗壳 + 叶轮
  blower: [
    G([[4, 8], [18, 8], [20, 12], [18, 16], [4, 16], [2, 12]], { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),
    C(11, 12, 3.5, { fill: 'url(#g-metal-d)', stroke: '#3a4654' }),
    P('M11 9.5 l1 2.5 l-1 2.5 l-1 -2.5 z', { fill: '#5a6a78' }),
    P('M11 9.5 l-1 2.5 l1 2.5 l1 -2.5 z', { fill: '#5a6a78' }),
    P('M11 9.5 v5 M11 9.5 l-2.5 1.2 l2.5 1.3 l-2.5 1.3 l2.5 1.2', { stroke: '#3a4654' }),
    R(20.5, 11, 1.5, 2, { fill: '#5a6a78' }),
  ],
  // 热风炉：圆筒 + 格子砖
  hot_blast_stove: [
    G([[6, 3], [18, 3], [18, 6], [19, 8], [19, 16], [18, 18], [6, 18], [5, 16], [5, 8], [6, 6]], { fill: 'url(#g-hot-v)', stroke: '#a04018' }),
    P('M5 9 h14 M5 11 h14 M5 13 h14 M5 15 h14', { stroke: '#7a2a10' }),        // 格子
    P('M12 1.5 v1.5 M11 1.5 h2', { stroke: '#5a6a78' }),
  ],
  // 引风机：轴流风叶 + 蜗壳
  id_fan: [
    C(12, 12, 6.5, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),
    C(12, 12, 2, { fill: '#3a4654', stroke: '#3a4654' }),
    P('M12 12 l4 -3 l-1 5 z M12 12 l-4 -3 l1 5 z M12 12 l4 3 l-1 -5 z M12 12 l-4 3 l1 -5 z', { fill: '#5a6a78', stroke: '#3a4654' }),
    R(19, 11, 2, 2, { fill: '#5a6a78' }),
  ],
  // 喷吹：喷枪斜插 + 煤粉
  injector: [
    P('M2 20 L16 6', { stroke: '#5a6a78', sw: 1.8 }),
    P('M16 6 l4 -1.5 l-1.5 4 z', { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),
    C(5, 18, 0.8, { fill: 'url(#g-cool-h)', stroke: '#2c6e9e' }),
    C(8, 16, 0.8, { fill: 'url(#g-cool-h)', stroke: '#2c6e9e' }),
  ],
  // 助燃风机：离心叶轮
  combustion_blower: [
    C(11, 11, 5, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),
    C(11, 11, 1.5, { fill: '#3a4654', stroke: '#3a4654' }),
    P('M11 11 l3.5 -1.5 l-1 4 z M11 11 l-3.5 -1.5 l1 4 z M11 11 l3.5 1.5 l-1 -4 z M11 11 l-3.5 1.5 l1 -4 z', { fill: '#5a6a78' }),
    R(16, 10, 5, 2, { fill: '#5a6a78' }),
  ],
  // 驱动供电：电机 + 输出轴
  drive_supply: [
    R(3, 8, 8, 8, { fill: 'url(#g-metal-d)', stroke: '#3a4654', rx: 1 }),
    C(7, 12, 1.6, { fill: '#3a4654' }),
    R(11, 11.4, 8, 1.2, { fill: '#5a6a78' }),
    R(6, 10, 2, 4, { fill: '#5a6a78', stroke: '#3a4654' }),
  ],
  // 电极调节：电极 + 双向箭头
  electrode_reg: [
    R(11, 4, 2, 14, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),
    P('M12 4 V2 M12 18 v2', { stroke: '#3a4654', sw: 1.6 }),
    P('M9 2 l3 -1.5 l3 1.5 M9 20 l3 1.5 l3 -1.5', { stroke: '#5a6a78' }),
  ],
  // 皮带机：输送带 + 托辊
  belt_conv: [
    R(3, 9, 18, 4, { fill: 'url(#g-metal-v)', stroke: '#3a4654', rx: 0.5 }),
    P('M3 11 h18', { stroke: '#a04018' }),                                    // 料流
    C(5, 14.5, 0.9, { fill: '#3a4654' }),
    C(9, 14.5, 0.9, { fill: '#3a4654' }),
    C(13, 14.5, 0.9, { fill: '#3a4654' }),
    C(17, 14.5, 0.9, { fill: '#3a4654' }),
    C(21, 14.5, 0.9, { fill: '#3a4654' }),
  ],
  // 给料机：料斗 + 出料槽
  feeder: [
    G([[6, 3], [18, 3], [16, 9], [8, 9]], { fill: 'url(#g-metal-d)', stroke: '#3a4654' }),
    P('M8 9 l-2 7 M16 9 l2 7', { stroke: '#5a6a78', sw: 1.6 }),
    R(6, 16, 12, 1.4, { fill: '#5a6a78' }),
  ],
  // 冷却水泵：泵体 + 叶轮 + 管路
  cool_pump: [
    C(10, 12, 4.5, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),
    C(10, 12, 1.5, { fill: 'url(#g-cool-h)', stroke: '#2c6e9e' }),
    P('M10 12 l2 -1 l-1 2 z M10 12 l-2 -1 l1 2 z M10 12 l2 1 l-1 -2 z M10 12 l-2 1 l1 -2 z', { fill: '#3a4654' }),
    R(15, 11, 6, 2, { fill: '#2c6e9e', stroke: '#1f4a6e' }),
  ],
  // 辅助锅炉：炉体 + 火焰 + 烟囱
  aux_boiler: [
    R(5, 9, 12, 9, { fill: 'url(#g-metal-d)', stroke: '#3a4654', rx: 0.5 }),
    R(5, 9, 12, 1.5, { fill: 'url(#g-hot-h)', stroke: '#a04018' }),
    P('M8 13 l1 -2 l1 2 M11 13 l1 -2 l1 2 M14 13 l1 -2 l1 2', { stroke: '#ff7a30' }),
    R(19, 4, 2, 14, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),
  ],
  // 空分制氧：双精馏塔 + 连接管
  oxy_plant: [
    R(4, 4, 5, 16, { fill: 'url(#g-cool-v)', stroke: '#2c6e9e', rx: 0.6 }),
    R(15, 7, 5, 13, { fill: 'url(#g-cool-v)', stroke: '#2c6e9e', rx: 0.6 }),
    P('M9 6 h6 M9 10 h6 M9 14 h6', { stroke: '#3a4654' }),
    P('M6.5 3 v1 M17.5 6 v1', { stroke: '#5a6a78' }),
  ],
  // 供氧系统：氧瓶 + 阀门
  oxy_supply: [
    R(9, 5, 6, 14, { fill: 'url(#g-cool-v)', stroke: '#2c6e9e', rx: 1.5 }),
    R(11, 3, 2, 2, { fill: '#3a4654' }),
    C(12, 8, 1, { fill: '#3a4654' }),
    P('M12 19 v2', { stroke: '#3a4654' }),
  ],
  // 供电系统：变电站 + 母线
  power_supply: [
    G([[12, 3], [17, 20], [7, 20]], { fill: 'url(#g-cool-v)', stroke: '#2c6e9e' }),
    P('M4 12 h16 M7 12 v-3 M17 12 v-3', { stroke: '#3a4654' }),
    P('M12 12 v5 M11 17 h2', { stroke: '#3a4654' }),
  ],
  // 通用：齿轮工艺（fallback）
  default: [
    C(12, 12, 4, { fill: 'url(#g-metal-v)', stroke: '#3a4654' }),
    P('M12 5 v2.5 M12 16.5 V19 M5 12 h2.5 M16.5 12 H19', { stroke: '#3a4654', sw: 1.4 }),
    P('M7.1 7.1 l1.8 1.8 M15.1 15.1 l1.8 1.8 M16.9 7.1 l-1.8 1.8 M8.9 15.1 l-1.8 1.8', { stroke: '#3a4654' }),
  ],
}

// —— 设备图幅几何表：每个设备在 2D 图中的「占位盒」（宽×高，px）。
// 2D 图不再用统一卡片包设备，设备以平面图直接落地。
// 主工艺尺寸统一（2026-09-04 用户要求「大小一致」）：图符渲染为等比 contain
// （矢量 min(avW/22, avH/23.5)、PNG preserveAspectRatio=meet），统一盒尺寸不会拉伸
// 设备图形，只统一视觉大小；端口位置由 T2D_INOUT 图标坐标(0-22)决定，不受盒尺寸影响。
// 注：盒高在端口数多时仍自动扩展（boxH: max(h, 96+(cnt-1)*24) + KPI_H），
// 高炉（9 个入口）实际盒高 ~314 略高，属端口空间需求。
// h 为「基础高」，端口数多时自动向上扩展；主工艺底部有悬浮 KPI 再额外 +26。
export const T2D_GEOM = {
  // —— 主工艺（炼铁/炼钢/轧钢）—— 统一 330×230
  sinter_plant:      { w: 330, h: 230 },  // 烧结台车（原 395×200 宽扁）
  pelletizing:       { w: 330, h: 230 },  // 球团圆盘
  coke_oven:         { w: 330, h: 230 },  // 焦炉：多室体
  blast_furnace:     { w: 330, h: 230 },  // 高炉（原 210×300 高耸；端口多自动加高）
  hot_metal_pretreat:{ w: 330, h: 230 },  // 铁水包
  bof:               { w: 330, h: 230 },  // 转炉
  ladle_furnace:     { w: 330, h: 230 },
  rh_vacuum:         { w: 330, h: 230 },
  caster:            { w: 330, h: 230 },  // 连铸：弧形辊列
  rolling_mill:      { w: 330, h: 230 },  // 轧机
  reheating_furnace: { w: 330, h: 230 },  // （短流程）
  eaf:               { w: 330, h: 230 },  // （短流程）
  dri_midrex:        { w: 330, h: 230 },  // （短流程）
  // —— 公用 / 节能减碳 ——
  gas_power:         { w: 180, h: 155 },
  waste_heat:        { w: 180, h: 165 },
  ccs:               { w: 170, h: 185 },
  // —— 工辅 ——
  hot_blast_stove:   { w: 130, h: 195 },  // 热风炉：高圆筒（蓄热室）
  blower:            { w: 140, h: 140 },  // 鼓风机
  combustion_blower: { w: 125, h: 125 },
  id_fan:            { w: 145, h: 140 },  // 轴流引风机
  injector:          { w: 185, h: 120 },  // 喷吹：斜枪+煤粉流
  oxy_supply:        { w: 110, h: 140 },  // 供氧接口/储罐
  oxy_plant:         { w: 125, h: 180 },
  power_supply:      { w: 120, h: 150 },
  drive_supply:      { w: 135, h: 125 },
  electrode_reg:     { w: 110, h: 155 },
  belt_conv:         { w: 195, h: 110 },
  feeder:            { w: 145, h: 130 },
  cool_pump:         { w: 140, h: 130 },
  aux_boiler:        { w: 160, h: 155 },
  default:           { w: 145, h: 135 },
}

// —— 设备入出口锚点：按「行业入料特点」把每个端口放到设备图符上真实的入/出口位置
// （高炉炉顶料钟装料 / 风口带送风喷煤 / 出铁口出铁水；BOF 氧枪顶 / 炉口装料 / 耳轴出钢；
//  连铸中间包顶 / 结晶器 / 弧形辊列；热风炉蓄热室出热风；鼓风机蜗壳出口；等等）。
// 锚点用图符本地坐标系 (cx, cy ∈ 22 × 23.5，与 figOf 缩放基准一致)：
//   - cx/cy 直接落在图符画出的特征点上（料钟、风口带、出铁口、氧枪头…），图符放大后位置随之等比缩放；
//   - side 决定连线的「外接方向」：T=向上 / R=向右 / B=向下 / L=向左，stub 沿此方向外伸后再折线连接。
// 数组下标与 PROCESS_TEMPLATES[type].inputs / outputs 的物料顺序严格一一对应。
// 2D 端口出/入口径规则(用户约束):
//   - 入口(in)只能落在设备的「左 / 上 / 下」三边(L/T/B)
//   - 出口(out)只能落在设备的「右」边(R)
//   - 同边多口沿该边(cx 或 cy)均匀错开
// 数组下标与 PROCESS_TEMPLATES[type].inputs / outputs 的物料顺序严格一一对应。
export const T2D_INOUT = {
  // —— 主工艺 ——
  sinter_plant: {
    in: [
      { cx: 2,  cy: 11,   side: 'L' },  // 0: iron_ore  烧结料层左端入料
      { cx: 6,  cy: 22,   side: 'B' },  // 1: coke      焦炉回供焦粉：底部进（回流弧自下方走廊上插，与 draft 的 cx=11 错开）
      { cx: 2,  cy: 9,    side: 'L' },  // 2: limestone
      { cx: 11, cy: 22,   side: 'B' },  // 3: draft     抽风罩
    ],
    out: [
      { cx: 21, cy: 15,   side: 'R' },  // 0: sinter    烧结台车右端出料
      { cx: 21, cy: 8,    side: 'R' },  // 1: bfg       抽风罩排气（右出）
      { cx: 21, cy: 11,   side: 'R' },  // 2: co2       右出
    ],
  },
  pelletizing: {
    in: [
      { cx: 9,  cy: 6,    side: 'T' },  // 0: iron_ore
      { cx: 14, cy: 6,    side: 'T' },  // 1: limestone
      { cx: 12, cy: 18,   side: 'B' },  // 2: draft
    ],
    out: [
      { cx: 21, cy: 14,   side: 'R' },  // 0: pellet
      { cx: 21, cy: 18,   side: 'R' },  // 1: co2
    ],
  },
  coke_oven: {
    in: [
      { cx: 9,  cy: 7,    side: 'T' },  // 0: coal       顶部装煤车装煤
      { cx: 2,  cy: 13,   side: 'L' },  // 1: combustion_air
    ],
    out: [
      { cx: 21, cy: 13,   side: 'R' },  // 0: coke      推焦侧出焦
      { cx: 21, cy: 9,    side: 'R' },  // 1: cog       上升管（右出）
      { cx: 21, cy: 5,    side: 'R' },  // 2: co2       右出
    ],
  },
  blast_furnace: {
    in: [
      { cx: 1,  cy: 3,    side: 'L' },  // 0: sinter     来自主带左侧（烧结机同行相邻）→ 左壁入
      { cx: 1,  cy: 6,    side: 'L' },  // 1: pellet     同上（球团）
      { cx: 1,  cy: 13,   side: 'L' },  // 2: coke       与焦炉 out coke cy13 对齐 → 笔直横线
      { cx: 1,  cy: 9,    side: 'L' },  // 3: limestone
      { cx: 5,  cy: 19,   side: 'L' },  // 4: self_power
      { cx: 8,  cy: 15,   side: 'L' },  // 5: blast_air  风口带冷风
      { cx: 1,  cy: 17,   side: 'L' },  // 6: hot_blast  风口带热风（贴左缘、垂直错开热风与喷煤口）
      { cx: 5,  cy: 20,   side: 'L' },  // 7: pulverized_coal  风口带喷煤（与 hot_blast 错开 37px，水平并排两条线不再共 x 槽）
      { cx: 5,  cy: 21,   side: 'L' },  // 8: electricity
    ],
    out: [
      { cx: 21, cy: 21,   side: 'R' },  // 0: hot_metal  出铁口（铁水）
      { cx: 21, cy: 18,   side: 'R' },  // 1: bf_slag    渣口
      { cx: 21, cy: 6,    side: 'R' },  // 2: bfg        炉顶煤气（右出）
      { cx: 21, cy: 3,    side: 'R' },  // 3: co2        右出
    ],
  },
  hot_metal_pretreat: {
    in: [
      { cx: 1,  cy: 10,   side: 'L' },  // 0: hot_metal  高炉在左侧同行 → 左壁入
      { cx: 14, cy: 21,   side: 'B' },  // 1: oxygen     供氧系统在下方 → 底面进（喷枪）
    ],
    out: [
      { cx: 21, cy: 10,   side: 'R' },  // 0: pre_hm     右侧倒出
      { cx: 21, cy: 14,   side: 'R' },  // 1: co2        右出
    ],
  },
  bof: {
    in: [
      { cx: 1,  cy: 10,   side: 'L' },  // 0: pre_hm     铁水预处理在左侧同行、cy 与其 out 对齐 → 笔直横线
      { cx: 15, cy: 2.5,  side: 'T' },  // 1: scrap      炉口废钢
      { cx: 11, cy: 2.5,  side: 'T' },  // 2: limestone
      { cx: 14, cy: 21,   side: 'B' },  // 3: oxygen     供氧系统在下方 → 底面进
    ],
    out: [
      { cx: 21, cy: 18,   side: 'R' },  // 0: crude_steel 耳轴侧出钢
      { cx: 21, cy: 15,   side: 'R' },  // 1: steel_slag  右出
      { cx: 21, cy: 6,    side: 'R' },  // 2: ldg        罩顶 LD 煤气（右出）
      { cx: 21, cy: 9,    side: 'R' },  // 3: conv_dust  右出
      { cx: 21, cy: 3,    side: 'R' },  // 4: co2        右出
    ],
  },
  ladle_furnace: {
    in: [
      { cx: 1,  cy: 10,   side: 'L' },  // 0: crude_steel 转炉在左侧同行 → 左壁入
      { cx: 15, cy: 9,    side: 'T' },  // 1: electricity 三电极
    ],
    out: [
      { cx: 21, cy: 11,   side: 'R' },  // 0: refined_steel
      { cx: 21, cy: 15,   side: 'R' },  // 1: co2        右出
    ],
  },
  rh_vacuum: {
    in: [
      { cx: 8,  cy: 10,   side: 'L' },  // 0: refined_steel 下降管
      { cx: 12, cy: 3,    side: 'T' },  // 1: electricity  真空泵
    ],
    out: [
      { cx: 21, cy: 10,   side: 'R' },  // 0: refined_steel 上升管出钢
    ],
  },
  caster: {
    in: [
      { cx: 1,  cy: 10,   side: 'L' },  // 0: refined_steel RH 在左侧同行、cy 与其 out 对齐 → 笔直横线
      { cx: 17, cy: 1,    side: 'T' },  // 1: electricity
    ],
    out: [
      { cx: 21, cy: 12,   side: 'R' },  // 0: billet      铸坯（右出）
      { cx: 21, cy: 18,   side: 'R' },  // 1: scale       右出
    ],
  },
  rolling_mill: {
    in: [
      { cx: 2,  cy: 12,   side: 'L' },  // 0: billet      板坯入
      { cx: 11, cy: 4,    side: 'T' },  // 1: ngas        加热炉
      { cx: 17, cy: 4,    side: 'T' },  // 2: electricity
    ],
    out: [
      { cx: 21, cy: 12,   side: 'R' },  // 0: steel_product
      { cx: 21, cy: 18,   side: 'R' },  // 1: scale       右出
    ],
  },
  eaf: {
    in: [
      { cx: 6,  cy: 6,    side: 'T' },  // 0: scrap        料篮
      { cx: 9,  cy: 6,    side: 'T' },  // 1: dri
      { cx: 12, cy: 6,    side: 'T' },  // 2: pig_iron
      { cx: 12, cy: 3,    side: 'T' },  // 3: electricity  三电极
      { cx: 15, cy: 6,    side: 'T' },  // 4: oxygen       氧燃枪
      { cx: 17, cy: 6,    side: 'T' },  // 5: self_power
      { cx: 18, cy: 6,    side: 'T' },  // 6: drive_power
      { cx: 19, cy: 6,    side: 'T' },  // 7: electrode_power
    ],
    out: [
      { cx: 21, cy: 13.5, side: 'R' },  // 0: crude_steel  出钢槽
      { cx: 21, cy: 16,   side: 'R' },  // 1: steel_slag
      { cx: 21, cy: 6,    side: 'R' },  // 2: ldg          右出
      { cx: 21, cy: 3,    side: 'R' },  // 3: co2          右出
    ],
  },
  dri_midrex: {
    in: [
      { cx: 10, cy: 2,    side: 'T' },  // 0: iron_ore
      { cx: 6,  cy: 10,   side: 'L' },  // 1: ngas
      { cx: 6,  cy: 14,   side: 'L' },  // 2: oxygen
      { cx: 14, cy: 2,    side: 'T' },  // 3: self_power
      { cx: 16, cy: 2,    side: 'T' },  // 4: drive_power
    ],
    out: [
      { cx: 21, cy: 19,   side: 'R' },  // 0: dri
      { cx: 21, cy: 6,    side: 'R' },  // 1: co2          右出
      { cx: 21, cy: 3,    side: 'R' },  // 2: top_gas      右出
    ],
  },
  // —— 公用/减碳 ——
  gas_power: {
    in: [
      { cx: 3, cy: 10,    side: 'L' },  // 0: bfg
      { cx: 3, cy: 12,    side: 'L' },  // 1: ldg
      { cx: 3, cy: 14,    side: 'L' },  // 2: cog
    ],
    out: [
      { cx: 21, cy: 12,   side: 'R' },  // 0: self_power
      { cx: 21, cy: 15,   side: 'R' },  // 1: steam         右出
    ],
  },
  waste_heat: {
    in:  [{ cx: 10, cy: 5,    side: 'T' }],  // 0: waste_heat
    out: [
      { cx: 21, cy: 12,   side: 'R' },  // 0: self_power
      { cx: 21, cy: 15,   side: 'R' },  // 1: steam  烟囱侧
    ],
  },
  ccs: {
    in:  [{ cx: 12, cy: 2,    side: 'T' }],  // 0: co2
    out: [],
  },
  // —— 工辅 ——
  hot_blast_stove: {
    in:  [{ cx: 12, cy: 20,   side: 'B' }],  // 0: blast_air 蓄热室底部冷风阀
    out: [{ cx: 21, cy: 10,   side: 'R' }],  // 0: hot_blast 蓄热室侧热风出口
  },
  blower: {
    in:  [{ cx: 11, cy: 19,   side: 'B' }],  // 0: oxygen 富氧（底部进，供氧系统就在其正下方）
    out: [{ cx: 21, cy: 18,   side: 'R' }],  // 0: blast_air 蜗壳出口（右出，送下方 stove）
  },
  id_fan: {
    in:  [],
    out: [{ cx: 21, cy: 10,   side: 'R' }],  // 0: draft         右出
  },
  injector: {
    in:  [],
    out: [{ cx: 21, cy: 8,    side: 'R' }],  // 0: pulverized_coal 喷枪头（右出）
  },
  combustion_blower: {
    in:  [],
    out: [{ cx: 21, cy: 11,   side: 'R' }],  // 0: combustion_air
  },
  drive_supply: {
    in:  [{ cx: 7,  cy: 4,    side: 'T' }],  // 0: electricity
    out: [{ cx: 20, cy: 12,   side: 'R' }],  // 0: drive_power
  },
  electrode_reg: {
    in:  [{ cx: 10, cy: 2,    side: 'T' }],  // 0: electricity
    out: [{ cx: 21, cy: 10,   side: 'R' }],  // 0: electrode_power 右出
  },
  belt_conv: {
    in:  [{ cx: 12, cy: 6,    side: 'T' }],  // 0: feeder_flow
    out: [{ cx: 21, cy: 11,   side: 'R' }],  // 0: feeder_flow
  },
  feeder: {
    in:  [{ cx: 12, cy: 2,    side: 'T' }],  // 0: feeder_flow
    out: [{ cx: 20, cy: 12,   side: 'R' }],  // 0: feeder_flow
  },
  cool_pump: {
    in:  [],
    out: [{ cx: 21, cy: 12,   side: 'R' }],  // 0: cool_water
  },
  aux_boiler: {
    in:  [{ cx: 11, cy: 4,    side: 'T' }],  // 0: ngas
    out: [{ cx: 17, cy: 13,   side: 'R' }],  // 0: aux_steam
  },
  oxy_plant: {
    in:  [{ cx: 12, cy: 2,    side: 'T' }],  // 0: electricity
    out: [{ cx: 20, cy: 13,   side: 'R' }],  // 0: oxy_supply
  },
  oxy_supply: {
    in:  [{ cx: 4,  cy: 12,   side: 'L' }],  // 0: electricity
    out: [{ cx: 21, cy: 10,   side: 'R' }],  // 0: oxygen         右出
  },
  power_supply: {
    in:  [{ cx: 12, cy: 2,    side: 'T' }],  // 0: electricity
    out: [{ cx: 18, cy: 12,   side: 'R' }],  // 0: electricity
  },
  default: {
    in:  [{ cx: 5,  cy: 12,   side: 'L' }],
    out: [{ cx: 18, cy: 12,   side: 'R' }],
  },
}

// 图例清单（保留兼容）
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
