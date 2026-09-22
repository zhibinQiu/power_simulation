// 2D 工艺视图「程序化设备图形库」（替代此前的 41MB 设备 PNG 素材）
//
// 背景：原方案为每台设备贴一张 2048² 的 PNG（18 张共 41MB），首屏要下载几十 MB 图片、
// 且换图必须离线跑 scripts/gen-devimg-meta.py 解析 alpha 外接框，图片与温度标注的坐标
// 全靠人工标定，极易错位。这里改为**用代码画设备**：零图片请求、随缩放松鼠清晰（矢量）、
// 图形与温度分区同源（高炉轮廓由同一份数据驱动，天然对齐）。
//
// 伪 3D 是怎么做出来的（每个构件都遵循同一套光照约定，光源在左上）：
//   1. 横向渐变模拟圆柱 —— g-cyl：左暗 → 中偏左最亮 → 右暗，任何竖直筒体一填就有体积感；
//   2. 顶面用更亮的斜向渐变 g-top + 左上高光椭圆，与侧壁形成明暗交替；
//   3. 底部一律压一条暗色椭圆（筒底/落地阴影），设备「踩在地上」而不是浮空；
//   4. 统一 feDropShadow 投影 + 底部接地模糊阴影，相邻设备之间有层次；
//   5. 热态部位（炉缸/钢液/风口带）用径向热核渐变，暗示内部高温。
//
// 坐标系：每个图形自带 viewBox（FIG_GEOM[type] = {w, h}），图形按自己最舒服的比例绘制，
// 渲染时由 Twin2DView 等比 contain 到节点的图带里（viewBox + preserveAspectRatio），
// 因此「图形真实边界」永远等于显示盒，连线端点贴边不需要任何外部标定数据。
//
// 元素结构与既有的 data/twin2dIcons.js 保持同构（{tag, ...attrs}），渲染器通用：
//   path / circle / ellipse / rect / polygon；额外支持 filter / opacity（用于阴影与高光）。

const EDGE = '#33404c'          // 统一描边（设备轮廓）
// 关于投影（重要性能约定）：**元素一律不带 filter**，投影由渲染器在整组上施加一次
// （DeviceFigure.vue 的根 <g filter="url(#f-fig)">）。
// 早期版本每个填充元素都挂一个 feDropShadow —— 单台高炉 28 元素里 17 个带滤镜，
// 全图合计 300+ 个滤镜实例：SVG 滤镜要为每个元素单独离屏渲染再合成，而 2D 视图里
// 每条管线都有常驻的 animateMotion 箭头动画，**每帧都会触发这些滤镜重新栅格化**，
// 拖拽/缩放直接掉帧。改成「一组一次」后滤镜实例数降到「设备台数」量级，观感不变。

// 渐变/填充常量（定义在 Twin2DView 的 <defs> 中）
const F = {
  cyl: 'url(#g-cyl)',           // 金属圆柱（横向明暗）
  cylHot: 'url(#g-cyl-hot)',    // 热态圆柱
  box: 'url(#g-box)',           // 箱体/炉墙（左上亮右下暗）
  boxHot: 'url(#g-box-hot)',
  top: 'url(#g-top)',           // 顶面/封头
  molten: 'url(#g-molten)',     // 钢液/铁水
  hearth: 'url(#g-hearth)',     // 炉膛热核（径向）
  cool: 'url(#g-cool-v)',       // 冷介质（水/蒸汽/氧）
  dark: '#4b5866',
}

// ------------------------------ 基础构件 ------------------------------
const rect = (x, y, w, h, fill, extra = {}) =>
  ({ tag: 'rect', x, y, width: w, height: h, fill, stroke: EDGE, sw: 0.85, ...extra })
const path = (d, fill = 'none', extra = {}) =>
  ({ tag: 'path', d, fill, stroke: EDGE, sw: 0.85, ...extra })
const circ = (cx, cy, r, fill, extra = {}) =>
  ({ tag: 'circle', cx, cy, r, fill, stroke: EDGE, sw: 0.85, ...extra })
const ell = (cx, cy, rx, ry, fill, extra = {}) =>
  ({ tag: 'ellipse', cx, cy, rx, ry, fill, stroke: EDGE, sw: 0.85, ...extra })
const poly = (pts, fill, extra = {}) =>
  ({ tag: 'polygon', pts, fill, stroke: EDGE, sw: 0.85, ...extra })

/** 接地柔影：让设备不浮空 —— 伪 3D 里最便宜也最有效的一笔。
 *  用**径向渐变**（g-ground）而不是 feGaussianBlur：中心浓、边缘淡的椭圆与模糊后的
 *  效果几乎无差别，但不需要每帧栅格化滤镜，交互帧率差别很大。 */
const ground = (cx, y, rx, ry = Math.max(0.35, rx * 0.3), op = 0.3) =>
  ({ tag: 'ellipse', cx, cy: y, rx, ry, fill: 'url(#g-ground)', opacity: op, stroke: 'none' })

/** 圆柱体（左暗-中亮-右暗渐变 + 底暗弧 + 顶封头 + 高光）：炉体/罐体/塔器的通用骨架 */
function cyl(cx, y0, y1, rx, ry = Math.max(0.4, rx * 0.26), opt = {}) {
  const body = `M${cx - rx} ${y0} V${y1} A${rx} ${ry} 0 0 0 ${cx + rx} ${y1} V${y0} Z`
  return [
    { tag: 'ellipse', cx, cy: y1, rx, ry, fill: F.dark, stroke: 'none' },        // 筒底暗面
    { tag: 'path', d: body, fill: opt.fill || F.cyl, stroke: 'none' },           // 侧壁（渐变）
    { tag: 'path', d: body, fill: 'none', stroke: EDGE, sw: 0.9 },
    ell(cx, y0, rx, ry, opt.top || F.top),                                       // 顶封头
    { tag: 'ellipse', cx: cx - rx * 0.34, cy: y0 + ry * 0.12, rx: rx * 0.4, ry: ry * 0.5,
      fill: '#ffffff', opacity: 0.4, stroke: 'none' },                            // 左上高光
  ]
}

/** 锥台（上小下大或反之）：高炉炉身/炉腹、料斗、钢包罐体 */
function cone(cx, y0, y1, r0, r1, opt = {}) {
  const ry0 = Math.max(0.35, r0 * 0.26)
  const ry1 = Math.max(0.35, r1 * 0.26)
  const d = `M${cx - r0} ${y0} L${cx - r1} ${y1} A${r1} ${ry1} 0 0 0 ${cx + r1} ${y1} L${cx + r0} ${y0} Z`
  return [
    { tag: 'path', d, fill: opt.fill || F.cyl, stroke: 'none' },
    { tag: 'path', d, fill: 'none', stroke: EDGE, sw: 0.9 },
    ...(opt.topEllipse === false ? [] : [
      ell(cx, y0, r0, ry0, opt.top || F.top),
      { tag: 'ellipse', cx: cx - r0 * 0.34, cy: y0 + ry0 * 0.12, rx: r0 * 0.4, ry: ry0 * 0.5,
        fill: '#ffffff', opacity: 0.38, stroke: 'none' },
    ]),
  ]
}

/** 辊子（连铸/轧机）：径向渐变 + 左上高光，成排时立刻有圆柱阵列的立体感 */
const roll = (cx, cy, r, fill = 'url(#g-roll)') => [
  circ(cx, cy, r, fill),
  { tag: 'circle', cx: cx - r * 0.3, cy: cy - r * 0.32, r: r * 0.42, fill: '#ffffff', opacity: 0.42, stroke: 'none' },
]

/** 风扇叶轮（弯掠桨叶）：叶根收窄、外缘沿圆周扫掠并带桨距角，n=5 即一台风扇/风机叶轮。
 *  与 roll 同为一组构件（返回元素数组），供机房温控「制冷风机」等需要「仿真风扇」造型的设备复用。 */
function fanBlades(cx, cy, r, n = 5) {
  const q = (v) => Math.round(v * 100) / 100
  const out = []
  for (let i = 0; i < n; i++) {
    const t = (i / n) * Math.PI * 2
    const at = (rad, ang) => [q(cx + Math.cos(ang) * rad), q(cy + Math.sin(ang) * rad)]
    const [x0, y0] = at(r * 0.3, t)              // 叶根
    const [xm, ym] = at(r * 0.74, t + 0.1)       // 前缘控制点（前掠）
    const [x1, y1] = at(r, t + 0.44)             // 叶尖前缘
    const [x2, y2] = at(r, t + 0.98)             // 叶尖后缘
    const [xm2, ym2] = at(r * 0.46, t + 0.8)     // 后缘控制点
    out.push({
      tag: 'path',
      d: `M${x0} ${y0} Q${xm} ${ym} ${x1} ${y1} A${q(r)} ${q(r)} 0 0 1 ${x2} ${y2} Q${xm2} ${ym2} ${x0} ${y0} Z`,
      fill: 'url(#g-cyl)', stroke: EDGE, sw: 0.55, opacity: 0.95,
    })
  }
  return out
}

/** 三电极（电弧炉 / 钢包精炼）：立柱 + 横臂 + 电极 + 弧光 */
function electrodes(xs, yTop, yBottom, opt = {}) {
  const out = []
  out.push(rect(xs[0] - 1.2, yTop - 0.8, (xs[xs.length - 1] - xs[0]) + 2.4, 0.9, F.box))  // 横臂
  for (const x of xs) {
    out.push({ tag: 'rect', x: x - 0.42, y: yTop, width: 0.84, height: yBottom - yTop, fill: '#5b6875', stroke: EDGE, sw: 0.7 })
    out.push({ tag: 'circle', cx: x, cy: yBottom + 0.3, r: 0.62, fill: 'url(#g-hearth)', opacity: 0.95, stroke: 'none' })
  }
  if (opt.arc !== false) {
    out.push({ tag: 'path', d: `M${xs[0]} ${yBottom + 0.9} L${xs[1] + 0.3} ${yBottom + 0.2} L${xs[2]} ${yBottom + 0.9}`,
      fill: 'none', stroke: '#ffe9a8', sw: 1.1, opacity: 0.95 })
  }
  return out
}

/** 烟囱/放散管（带顶部蒸汽） */
const stack = (x, y0, y1, w) => [
  cone(x, y0, y1, w, w * 1.15, { topEllipse: false }),
  // 烟囱口冒出的烟气：同样用径向渐变代替模糊（见 ground 注释）
  { tag: 'ellipse', cx: x, cy: y0 - 0.6, rx: w * 1.5, ry: 0.8, fill: 'url(#g-puff)', opacity: 0.6, stroke: 'none' },
]

// ------------------------------ 设备图形 ------------------------------
// 每个条目：{ vb: [w, h], els: [...] }（图形在自己的 viewBox 内绘制）
// flat(Infinity)：构件（cyl/cone/stack/electrodes…）各自返回元素数组，组合时会出现多层嵌套，
// 必须彻底拍平 —— 只 flat 一层会让数组混进 els，渲染时整个构件静默消失（踩过：烟囱不显示）。
const fig = (w, h, ...els) => ({ vb: [w, h], els: els.flat(Infinity) })

export const T2D_FIGURES = {
  // —— 高炉：炉喉/炉身/炉腰/炉腹/炉缸/炉基六段锥台，逐段填圆柱渐变 ——
  blast_furnace: fig(24, 23,
    ground(12, 21.8, 6.2),
    rect(6.6, 19, 10.8, 2.2, F.box),                                    // 炉基
    cone(12, 15.4, 19.2, 3.4, 3.9, { fill: F.cylHot }),                 // 炉缸（热）
    cone(12, 12.6, 15.6, 4.0, 3.4),                                     // 炉腹（上宽下窄）
    cone(12, 11.2, 12.8, 4.1, 4.0),                                     // 炉腰（最宽）
    cone(12, 4.4, 11.4, 2.5, 4.1),                                      // 炉身（下宽上窄）
    cone(12, 2.8, 4.6, 2.0, 2.5, { topEllipse: false }),                 // 炉喉
    rect(10.2, 1.2, 3.6, 1.4, F.box),                                   // 装料钟
    { tag: 'path', d: 'M12 1.2 V0.2', fill: 'none', stroke: EDGE, sw: 0.9 },
    // 热风围管 + 风口（左右各一支，接到风口带）
    { tag: 'path', d: 'M4.2 6.2 V16 M19.8 6.2 V16 M4.2 16 H8.2 M15.8 16 H19.8', fill: 'none', stroke: '#5b6875', sw: 1.1 },
    ...[8.4, 10.4, 13.6, 15.6].map((x) => circ(x, 13.4, 0.52, 'url(#g-hearth)', { sw: 0.6 })),
    rect(11.1, 17.2, 1.8, 1.3, 'url(#g-molten)', { sw: 0.6 }),          // 出铁口
  ),

  // —— 热风炉：细高蓄热室圆筒 + 拱顶 + 燃烧口 ——
  hot_blast_stove: fig(15, 24,
    ground(7.5, 22.9, 4.2),
    rect(3.4, 20.6, 8.2, 2, F.box),
    cyl(7.5, 5.4, 20.8, 3.3, 1.1),
    { tag: 'path', d: 'M4.2 5.6 A3.3 3.3 0 0 1 10.8 5.6 Z', fill: F.top, stroke: EDGE, sw: 0.9 },
    ...[8, 12, 16].map((y) => ({ tag: 'path', d: `M4.2 ${y} H10.8`, fill: 'none', stroke: '#6c7a88', sw: 0.6, opacity: 0.8 })),
    rect(6.6, 2.2, 1.8, 3.4, F.box),                                     // 顶部烟囱
    { tag: 'path', d: 'M10.8 19.2 h2.6 v1.6 h-2.6 z', fill: 'url(#g-hearth)', stroke: EDGE, sw: 0.7 },
  ),

  // —— DRI 竖炉：上部圆柱炉身 + 下部锥体排料 ——
  dri_midrex: fig(18, 24,
    ground(9, 22.8, 5),
    rect(4.4, 20.2, 9.2, 2.2, F.box),
    cone(9, 13.6, 20.4, 3.6, 2.6, { fill: F.cylHot }),
    cyl(9, 4.6, 13.8, 3.6, 1.2),
    { tag: 'path', d: 'M5.4 4.8 A3.6 3.6 0 0 1 12.6 4.8 Z', fill: F.top, stroke: EDGE, sw: 0.9 },
    rect(7.8, 1.4, 2.4, 2.6, F.box),                                     // 顶部加料口
    { tag: 'path', d: 'M2.6 8.4 V14.6 M15.4 8.4 V14.6', fill: 'none', stroke: '#5b6875', sw: 1 },
    ...[9, 12.2].map((y) => ({ tag: 'path', d: `M5.4 ${y} H12.6`, fill: 'none', stroke: '#6c7a88', sw: 0.6, opacity: 0.8 })),
  ),

  // —— 转炉：梨形炉体 + 氧枪 + 两侧耳轴 + 炉口火焰 ——
  bof: fig(20, 22,
    ground(10, 21.4, 5.6),
    poly([[7.2, 4.6], [12.8, 4.6], [16.4, 9.4], [16.8, 16], [13.2, 20.2], [6.8, 20.2], [3.2, 16], [3.6, 9.4]], 'url(#g-cyl-hot)'),
    { tag: 'path', d: 'M7.2 4.6 H12.8', fill: 'none', stroke: EDGE, sw: 1.2 },
    ell(10, 4.6, 2.8, 0.9, 'url(#g-molten)', { sw: 0.7 }),               // 炉口钢液面
    { tag: 'ellipse', cx: 10, cy: 4.6, rx: 3.2, ry: 1.1, fill: 'none', stroke: '#8a97a5', sw: 0.8 },
    { tag: 'path', d: 'M10 0.6 V3.6', fill: 'none', stroke: '#5b6875', sw: 1.4 },  // 氧枪
    rect(9.1, 3.4, 1.8, 1.2, F.box),
    circ(2.2, 13, 1.3, F.box),                                           // 耳轴
    circ(17.8, 13, 1.3, F.box),
    { tag: 'path', d: 'M10 1.4 l-1 -1.6 M10 1.4 l1 -1.6', fill: 'none', stroke: '#ffb04a', sw: 0.9, opacity: 0.9 },
  ),

  // —— 电弧炉：椭球炉壳 + 三电极 + 出钢槽 ——
  eaf: fig(24, 20,
    ground(12, 19.4, 7.4),
    { tag: 'path', d: 'M3.4 8 A12 8 0 0 0 20.6 8 Z', fill: 'url(#g-cyl-hot)', stroke: EDGE, sw: 0.9 },
    ell(12, 8, 8.6, 1.9, 'url(#g-molten)', { sw: 0.8 }),                 // 熔池
    { tag: 'path', d: 'M4.6 7.4 H19.4', fill: 'none', stroke: EDGE, sw: 1 },
    electrodes([8.2, 12, 15.8], 2.4, 6.4),
    poly([[20.6, 9.4], [23.4, 11.2], [20.6, 13]], F.box),                // 出钢槽
    rect(2.6, 15.6, 18.8, 1.8, F.box),                                   // 炉基座
  ),

  // —— 钢包精炼 LF：锥形钢包 + 三电极 + 钢液面 ——
  ladle_furnace: fig(20, 22,
    ground(10, 21.4, 5.4),
    cone(10, 10.4, 20.4, 4.4, 3.2),
    ell(10, 10.4, 4.4, 1.3, 'url(#g-molten)', { sw: 0.8 }),              // 钢液面
    electrodes([6.6, 10, 13.4], 2.6, 9.2),
    { tag: 'path', d: 'M4.4 12.6 L15.6 12.6', fill: 'none', stroke: '#6c7a88', sw: 0.6, opacity: 0.7 },
    rect(3.2, 20.2, 13.6, 1.2, F.box),
  ),

  // —— RH 真空精炼：上部真空罐 + 双浸渍管 + 下部钢包 ——
  rh_vacuum: fig(20, 22,
    ground(10, 21.6, 5.4),
    cone(10, 15.6, 20.4, 4.4, 3.2),                                      // 钢包
    ell(10, 15.6, 4.4, 1.3, 'url(#g-molten)', { sw: 0.8 }),
    { tag: 'path', d: 'M7.4 2.2 V13.2 M12.6 2.2 V13.2', fill: 'none', stroke: '#5b6875', sw: 1.5 }, // 双循环管
    cyl(10, 1.4, 5.6, 4.2, 1.3),                                         // 真空罐
    { tag: 'path', d: 'M13 3.6 h4.2 v1.2 h-4.2 z', fill: F.box, stroke: EDGE, sw: 0.7 },  // 抽真空口
    rect(3.6, 20.2, 12.8, 1.2, F.box),
  ),

  // —— 铁水预处理：鱼雷罐 + 喷枪 + 渣层 ——
  hot_metal_pretreat: fig(20, 22,
    ground(10, 21.4, 5.6),
    cone(10, 9.6, 20.2, 4.6, 3.4, { fill: F.cylHot }),
    ell(10, 9.6, 4.6, 1.4, 'url(#g-molten)', { sw: 0.8 }),
    { tag: 'path', d: 'M5.6 12.4 H14.4', fill: 'none', stroke: '#8f6b3a', sw: 1.1, opacity: 0.9 }, // 渣层
    { tag: 'path', d: 'M10 1.2 V8.6', fill: 'none', stroke: '#5b6875', sw: 1.5 },                   // 喷枪
    rect(8.8, 8.2, 2.4, 1.2, F.box),
    circ(2.6, 19.4, 1.5, F.dark),                                        // 走行轮
    circ(17.4, 19.4, 1.5, F.dark),
    rect(3.2, 20.2, 13.6, 1.2, F.box),
  ),

  // —— 连铸机：结晶器 + 扇形段辊列 + 弧形铸坯 ——
  caster: fig(22, 24,
    ground(11, 23.2, 6.4),
    rect(7.4, 1.8, 7.6, 3.6, F.box),                                     // 结晶器
    ell(11, 2.1, 3.8, 0.8, 'url(#g-molten)', { sw: 0.7 }),
    { tag: 'path', d: 'M11 5.6 C11 9.4 9.4 11.4 8 13.2 C6.6 15 5.8 17.2 5.6 19.4',
      fill: 'none', stroke: 'url(#g-molten)', sw: 2.2 },                  // 铸坯（热）
    ...[[9.2, 7.4], [8.4, 10.2], [7.4, 13], [6.6, 15.8], [6.0, 18.4]].map(([x, y]) => roll(x, y, 1.15)),
    ...[[13.4, 7.4], [14.2, 10.2], [15.2, 13], [16, 15.8], [16.6, 18.4]].map(([x, y]) => roll(x, y, 1.15)),
    { tag: 'path', d: 'M3.4 8.6 l-1.4 0.8 M3.4 12 l-1.4 0.8 M3.4 15.4 l-1.4 0.8', fill: 'none', stroke: '#7ec1ec', sw: 0.8 },  // 二冷喷淋
    rect(3.6, 20.4, 15, 1.6, F.box),
  ),

  // —— 轧机：上下工作辊 + 热轧带 + 机架 ——
  rolling_mill: fig(24, 16,
    ground(12, 15.4, 8),
    rect(1.6, 3, 2.2, 10, F.box),                                        // 机架立柱
    rect(20.2, 3, 2.2, 10, F.box),
    roll(7.6, 6.4, 2.6),
    roll(7.6, 11.6, 2.6),
    rect(10.4, 8, 10.2, 2.2, 'url(#g-molten)', { sw: 0.7 }),             // 轧件（热）
    { tag: 'path', d: 'M12.6 8 V10.2 M15 8 V10.2 M17.4 8 V10.2', fill: 'none', stroke: '#7a2f12', sw: 0.6, opacity: 0.7 },
    rect(4.4, 1.6, 15.2, 1.4, F.box),                                    // 上横梁
    rect(4.4, 13.4, 15.2, 1.4, F.box),
  ),

  // —— 加热炉：长炉体 + 烧嘴 + 炉内坯料 ——
  reheating_furnace: fig(24, 14,
    ground(12, 13.6, 8.6),
    rect(1.8, 3.4, 20.4, 8.6, 'url(#g-box-hot)'),
    ...[5, 9, 13, 17].map((x) => rect(x - 0.9, 1.6, 1.8, 1.8, F.box)),   // 顶部烧嘴
    ...[4.6, 9.4, 14.2, 19].map((x) => circ(x, 8, 0.8, 'url(#g-hearth)', { sw: 0.6 })),
    { tag: 'path', d: 'M3.4 9.6 H20.6', fill: 'none', stroke: '#6c7a88', sw: 0.7, opacity: 0.8 },
    rect(1.2, 11.8, 21.6, 1.6, F.box),
  ),

  // —— 烧结机：长台车 + 点火罩 + 风箱 ——
  sinter_plant: fig(24, 13,
    ground(12, 12.6, 9),
    rect(1.6, 6.6, 20.8, 2.6, F.box),                                    // 台车
    rect(1.6, 5.6, 20.8, 1.1, 'url(#g-molten)', { sw: 0.6 }),            // 料层（红热）
    rect(4.2, 2.4, 15.6, 3, 'url(#g-box-hot)'),                          // 点火罩
    ...[4.6, 8.2, 11.8, 15.4, 19].map((x) => rect(x - 0.7, 9.2, 1.4, 2.4, F.box)), // 风箱支腿
    ...[4.6, 12, 19.4].map((x) => circ(x, 11.9, 0.9, F.dark)),           // 托辊
    rect(2.2, 0.8, 2.6, 1.6, F.box),                                     // 头部罩
  ),

  // —— 球团：回转窑（倾斜筒体）+ 窑头窑尾 ——
  pelletizing: fig(24, 14,
    ground(12, 13.4, 8.6),
    cone(11.4, 3.6, 10.6, 2.4, 3.2, { fill: F.cylHot }),                 // 窑体（倾斜由 x 偏移表现）
    { tag: 'path', d: 'M8.2 4 H14.6', fill: 'none', stroke: EDGE, sw: 0.9 },
    ...[5.2, 8.4, 11.6, 14.8].map((x) => circ(x, 11.4, 1, F.dark)),      // 支承托轮
    rect(15.6, 4.4, 4.4, 5.4, F.box),                                    // 窑头罩
    rect(1.4, 1.6, 3.4, 2.6, F.box),                                     // 窑尾烟囱
    { tag: 'ellipse', cx: 3.1, cy: 1.2, rx: 2, ry: 0.9, fill: 'url(#g-puff)', opacity: 0.65, stroke: 'none' },
  ),

  // —— 焦炉：多室炉体 + 上升管 + 集气管 ——
  coke_oven: fig(24, 14,
    ground(12, 13.6, 8.8),
    rect(2, 5.2, 20, 7, 'url(#g-box-hot)'),
    ...[4, 7.4, 10.8, 14.2, 17.6].map((x) => rect(x, 7, 1.6, 3.6, 'url(#g-molten)', { sw: 0.6 })), // 炉门（热）
    rect(1.4, 3.4, 21.2, 1.6, F.box),                                    // 炉顶集气管
    ...[4.6, 8.6, 12.6, 16.6].map((x) => ({ tag: 'path', d: `M${x} 5.2 V3.4`, fill: 'none', stroke: '#5b6875', sw: 0.9 })),
    stack(20.6, 0.6, 3.4, 0.9),
    rect(1.4, 12.2, 21.2, 1.2, F.box),
  ),

  // —— 连铸以外：连轧/冷轧（辊系更密、无热辐射） ——
  cold_rolling_mill: fig(24, 16,
    ground(12, 15.4, 8),
    rect(1.6, 3, 2.2, 10, F.box),
    rect(20.2, 3, 2.2, 10, F.box),
    ...[[6.4, 5.4], [6.4, 10.6], [10.6, 5.4], [10.6, 10.6], [14.8, 5.4], [14.8, 10.6]].map(([x, y]) => roll(x, y, 1.9)),
    rect(3.8, 8, 16.4, 1.2, 'url(#g-cyl)', { sw: 0.6 }),                 // 冷态带钢
    rect(4.4, 1.6, 15.2, 1.4, F.box),
    rect(4.4, 13.4, 15.2, 1.4, F.box),
  ),

  // —— 煤气发电：燃机箱体 + 发电机 + 烟囱 ——
  gas_power: fig(20, 16,
    ground(10, 15.4, 6.6),
    rect(1.6, 6.4, 9.4, 6.6, F.box),                                     // 燃机
    cyl(11.8, 7.4, 12.6, 3.6, 1.2),                                      // 发电机
    { tag: 'path', d: 'M11 9.6 H15.4', fill: 'none', stroke: '#6c7a88', sw: 0.7, opacity: 0.8 },
    stack(3.4, 1.2, 6.4, 1.2),
    rect(1.2, 13, 17.6, 1.8, F.box),
  ),

  // —— 余热锅炉：塔体 + 汽包 ——
  waste_heat: fig(18, 18,
    ground(9, 17.4, 5.4),
    cyl(9, 3.2, 15.4, 3.6, 1.3),
    cyl(12.8, 6.4, 11.4, 1.7, 0.7),                                      // 汽包
    { tag: 'path', d: 'M5.4 8.4 H12.6 M5.4 11.6 H12.6', fill: 'none', stroke: '#6c7a88', sw: 0.7, opacity: 0.8 },
    { tag: 'path', d: 'M2.6 16.2 H15.4', fill: 'none', stroke: EDGE, sw: 0.8 },
    rect(3.4, 15.2, 11.2, 1.6, F.box),
  ),

  // —— CCUS：吸收塔 + 再生塔（双塔） ——
  ccs: fig(20, 20,
    ground(10, 19.4, 6.6),
    cyl(5.6, 4.2, 17.6, 2.6, 1),                                         // 吸收塔
    cyl(13.6, 2.6, 17.6, 2.4, 0.9),                                      // 再生塔
    { tag: 'path', d: 'M5.6 4.6 H13.4', fill: 'none', stroke: '#5b6875', sw: 1.1 },   // 连接管
    ...[8.4, 12.4].map((y) => ({ tag: 'path', d: `M3 ${y} H8.2 M11.2 ${y} H16`, fill: 'none', stroke: '#6c7a88', sw: 0.6, opacity: 0.8 })),
    rect(1.8, 17.4, 16.4, 1.6, F.box),
  ),

  // —— 鼓风机 / 助燃风机：蜗壳 + 叶轮 + 电机 ——
  blower: fig(17, 15,
    ground(8.5, 14.4, 5.4),
    circ(6.4, 7.4, 4.2, 'url(#g-cyl)'),                                  // 蜗壳
    circ(6.4, 7.4, 1.5, F.dark, { sw: 0.7 }),
    ...[0, 60, 120, 180, 240, 300].map((a) => {
      const r = 3.1
      const t = (a * Math.PI) / 180
      return { tag: 'path', d: `M${6.4 + Math.cos(t) * 1.5} ${7.4 + Math.sin(t) * 1.5} L${6.4 + Math.cos(t + 0.5) * r} ${7.4 + Math.sin(t + 0.5) * r}`,
        fill: 'none', stroke: '#6c7a88', sw: 0.7, opacity: 0.9 }
    }),
    rect(10.4, 5.6, 5.2, 3.8, F.box),                                    // 电机
    rect(1.6, 11.6, 14.4, 2, F.box),
  ),
  combustion_blower: fig(15, 13,
    ground(7.5, 12.4, 4.6),
    circ(5.6, 6.4, 3.6, 'url(#g-cyl)'),
    circ(5.6, 6.4, 1.2, F.dark, { sw: 0.6 }),
    rect(9.2, 4.8, 4.4, 3.2, F.box),
    rect(1.4, 9.8, 12.4, 1.8, F.box),
  ),

  // —— 引风机：轴流筒 + 机翼叶片 ——
  id_fan: fig(17, 15,
    ground(8.5, 14.4, 5.6),
    rect(2.2, 4.2, 12.6, 5.6, F.cyl),                                    // 风筒
    ell(2.2, 8, 1.2, 2.8, F.dark, { sw: 0.8 }),
    ell(14.8, 8, 1.2, 2.8, F.top, { sw: 0.8 }),
    circ(8.5, 8, 2.4, F.dark, { sw: 0.7 }),
    ...[0, 120, 240].map((a) => {
      const t = (a * Math.PI) / 180
      return { tag: 'ellipse', cx: 8.5 + Math.cos(t) * 1.2, cy: 8 + Math.sin(t) * 1.2, rx: 1.5, ry: 0.5,
        fill: '#aab6c2', opacity: 0.9, stroke: 'none', transform: `rotate(${a} ${8.5 + Math.cos(t) * 1.2} ${8 + Math.sin(t) * 1.2})` }
    }),
    rect(5.6, 11.4, 5.8, 2.2, F.box),
  ),

  // —— 喷吹系统：煤粉罐 + 喷枪 + 分配器 ——
  injector: fig(20, 13,
    ground(10, 12.4, 6.4),
    cone(5.8, 2.6, 9.4, 2.6, 2.0),                                       // 喷吹罐
    { tag: 'path', d: 'M8.4 6.2 L17.4 10', fill: 'none', stroke: '#5b6875', sw: 1.4 },   // 喷枪
    poly([[16.6, 9.2], [19.4, 10.6], [16.6, 12]], F.box),
    rect(9.6, 8.4, 3.6, 1.4, F.box),                                      // 分配器
    ...[3.4, 8.2].map((x) => rect(x - 0.7, 9.4, 1.4, 2.2, F.box)),       // 支腿
    rect(2.4, 11.4, 15.2, 1.2, F.box),
  ),

  // —— 电极调节：立柱 + 横臂 ——
  electrode_reg: fig(15, 16,
    ground(7.5, 15.4, 4.6),
    rect(3.2, 1.6, 2.2, 12.4, F.box),                                    // 立柱
    rect(5.4, 5.4, 8, 1.2, F.box),                                       // 横臂
    rect(11.6, 6.6, 1.4, 6.4, '#5b6875', { sw: 0.7 }),                   // 电极
    circ(12.3, 13.4, 0.8, 'url(#g-hearth)', { sw: 0.5 }),
    rect(2.4, 13.8, 10.4, 1.4, F.box),
  ),

  // —— 变压器/供电：箱体 + 套管 + 散热片 ——
  power_supply: fig(17, 15,
    ground(8.5, 14.4, 5.6),
    rect(2.2, 5.2, 12.6, 7.4, F.box),
    ...[5, 8.5, 12].map((x) => rect(x - 0.6, 3, 1.2, 2.2, F.cyl)),       // 高压套管
    ...[4, 6.4, 8.8, 11.2].map((x) => ({ tag: 'path', d: `M${x} 6.4 V11.4`, fill: 'none', stroke: '#6c7a88', sw: 0.6, opacity: 0.8 })),
    rect(1.4, 12.6, 14.2, 1.4, F.box),
  ),
  drive_supply: fig(17, 15,
    ground(8.5, 14.4, 5.6),
    rect(2.2, 4.6, 12.6, 8, F.box),
    rect(4.4, 2.4, 8.2, 2.2, F.cyl),
    ...[4.6, 8.5, 12.4].map((x) => circ(x, 8.6, 1.3, F.dark, { sw: 0.6 })),
    rect(1.4, 12.6, 14.2, 1.4, F.box),
  ),

  // —— 皮带机：输送带 + 托辊 + 头部滚筒 ——
  belt_conv: fig(24, 10,
    ground(12, 9.6, 8.4),
    { tag: 'path', d: 'M2.6 3.4 H20.4 A1.6 1.6 0 0 1 20.4 6.6 H2.6 A1.6 1.6 0 0 1 2.6 3.4 Z', fill: F.cyl, stroke: EDGE, sw: 0.9 },
    ...[5, 8.4, 11.8, 15.2, 18.6].map((x) => circ(x, 7.4, 0.9, F.dark, { sw: 0.6 })),
    rect(4.4, 7.4, 0.9, 2.2, F.box),
    rect(18, 7.4, 0.9, 2.2, F.box),
  ),

  // —— 给料机：料斗 + 振动槽 ——
  feeder: fig(18, 13,
    ground(9, 12.4, 5.6),
    poly([[3.4, 1.6], [14.6, 1.6], [12, 6.4], [6, 6.4]], F.box),         // 料斗
    { tag: 'path', d: 'M5.4 6.8 H12.6 L16.6 9.4 H2.4 Z', fill: F.cyl, stroke: EDGE, sw: 0.9 }, // 振动槽
    ...[4.2, 8.4, 12.6].map((x) => rect(x - 0.6, 9.6, 1.2, 2, F.box)),
    rect(1.8, 11.4, 14.4, 1.2, F.box),
  ),

  // —— 冷却水泵：泵壳 + 电机 ——
  cool_pump: fig(15, 14,
    ground(7.5, 13.4, 4.8),
    circ(4.8, 6.6, 3.4, F.cyl),
    circ(4.8, 6.6, 1.2, F.dark, { sw: 0.6 }),
    { tag: 'path', d: 'M1.4 6.6 h-0.6 M8.2 6.6 V3.4 h2.4', fill: 'none', stroke: '#7ec1ec', sw: 1.2 },
    rect(8.2, 4.8, 5.4, 3.6, F.box),                                     // 电机
    rect(1.4, 10.4, 12.2, 1.8, F.box),
  ),

  // —— 辅助锅炉：筒体 + 烟囱 ——
  aux_boiler: fig(17, 18,
    ground(8.5, 17.4, 5.4),
    cyl(8.5, 5.4, 15.4, 3.6, 1.3),
    ...[8, 11].map((y) => ({ tag: 'path', d: `M4.9 ${y} H12.1`, fill: 'none', stroke: '#6c7a88', sw: 0.7, opacity: 0.8 })),
    stack(12.4, 1.4, 5.4, 1),
    circ(8.5, 9.4, 1.7, 'url(#g-hearth)', { sw: 0.6 }),                  // 炉门/观火孔
    rect(3.2, 15.2, 10.6, 1.6, F.box),
  ),

  // —— 制氧/供氧：空分塔 + 氧气储罐 ——
  oxy_plant: fig(18, 19,
    ground(9, 18.4, 6),
    cyl(6.2, 3.4, 16.4, 2.8, 1.1),                                       // 空分塔
    cyl(12.8, 6.4, 16.4, 2.2, 0.9),                                      // 氧储罐
    { tag: 'path', d: 'M8.6 7.4 H11.2', fill: 'none', stroke: '#7ec1ec', sw: 1.1 },
    { tag: 'path', d: 'M3.4 10.6 H9 M3.4 13.6 H9', fill: 'none', stroke: '#6c7a88', sw: 0.6, opacity: 0.8 },
    rect(2.2, 16.2, 13.6, 1.6, F.box),
  ),
  oxy_supply: fig(18, 19,
    ground(9, 18.4, 5.6),
    cyl(9, 4.4, 16.4, 3.2, 1.2),
    { tag: 'path', d: 'M9 4.4 V1.8', fill: 'none', stroke: '#7ec1ec', sw: 1.2 },
    ...[7.6, 11, 14].map((y) => ({ tag: 'path', d: `M5.8 ${y} H12.2`, fill: 'none', stroke: '#6c7a88', sw: 0.6, opacity: 0.8 })),
    rect(4.4, 16.2, 9.2, 1.6, F.box),
  ),

  // —— 机房温控①：冷却水（循环水系统：水箱 + 循环水泵，暖色层表示回水温度上升） ——
  dc_chiller: fig(18, 15,
    ground(9, 14.5, 5.8),
    rect(1.6, 12.4, 15.0, 1.6, F.box),                                    // 设备底座
    cyl(12.0, 3.0, 12.2, 2.9, 1.0),                                       // 循环水箱
    { tag: 'path', d: 'M9.5 4.5 H14.5', fill: 'none', stroke: '#d4803a', sw: 0.9, opacity: 0.6 },   // 上层回水（吸热后偏热）
    { tag: 'path', d: 'M9.5 6.6 H14.5 M9.5 9.4 H14.5', fill: 'none', stroke: '#7ec1ec', sw: 0.6, opacity: 0.7 },
    rect(1.8, 9.6, 4.4, 2.6, F.box),                                      // 泵底座
    circ(3.9, 8.2, 2.5, F.cyl),                                           // 循环水泵
    circ(3.9, 8.2, 0.95, F.dark, { sw: 0.6 }),                            // 泵轮毂
    rect(6.6, 7.0, 2.2, 2.6, F.box),                                      // 电机
    { tag: 'path', d: 'M9.1 10.6 H3.9', fill: 'none', stroke: '#7ec1ec', sw: 1.1 },                 // 泵 → 水箱
    { tag: 'path', d: 'M13.6 3.0 V0.7', fill: 'none', stroke: '#3b9ee0', sw: 1.3 },                 // 冷却水供水（去制冷风机）
    { tag: 'path', d: 'M10.4 3.0 V0.7', fill: 'none', stroke: '#d4803a', sw: 1.3 },                 // 冷却水回水（来自制冷风机）
  ),

  // —— 机房温控②：制冷风机（半导体制冷片 + 风扇：风筒 + 5 片桨叶 + 水冷头散热） ——
  dc_fan_cool: fig(18, 17,
    ground(9, 16.4, 6.2),
    rect(2.2, 14.4, 13.6, 1.7, F.box),                                    // 底座
    rect(7.4, 12.0, 3.2, 2.5, F.box),                                     // 支腿
    circ(9, 8.0, 5.6, F.cyl),                                             // 风筒外框
    circ(9, 8.0, 4.7, '#2b3540', { sw: 0.7 }),                            // 风道内腔（暗）
    ...fanBlades(9, 8.0, 4.4),                                            // 5 片弯掠桨叶
    circ(9, 8.0, 1.25, F.dark, { sw: 0.7 }),                              // 叶轮轮毂
    circ(9, 8.0, 5.15, 'none', { stroke: '#a9b8c4', sw: 0.5, opacity: 0.5 }),   // 护网外圈
    circ(9, 8.0, 3.05, 'none', { stroke: '#a9b8c4', sw: 0.45, opacity: 0.4 }),  // 护网内圈
    { tag: 'path', d: 'M4.0 8 H14 M9 3.1 V13', fill: 'none', stroke: '#a9b8c4', sw: 0.4, opacity: 0.35 },
    rect(3.4, 0.7, 3.4, 2.1, F.box),                                      // 水冷头（接制冷片热端）
    rect(7.2, 1.1, 3.6, 1.5, '#d6dbe1', { sw: 0.8 }),                     // 半导体制冷片
    ...[7.9, 8.7, 9.5, 10.3].map((x) => ({ tag: 'path', d: `M${x} 2.6 V3.4`, fill: 'none', stroke: '#8b98a6', sw: 0.4, opacity: 0.9 })),
    { tag: 'path', d: 'M6.8 1.75 H7.2', fill: 'none', stroke: '#5b6875', sw: 1.1 },
    { tag: 'path', d: 'M3.4 1.5 H0.5', fill: 'none', stroke: '#3b9ee0', sw: 1.3 },     // 冷却水供水
    { tag: 'path', d: 'M3.4 2.5 H0.8', fill: 'none', stroke: '#d4803a', sw: 1.3 },     // 冷却水回水
  ),

  // —— 机房温控③：算力设备（机柜列：服务器插槽 + 指示灯） ——
  dc_it: fig(16, 18,
    ground(8, 17.4, 5.4),
    rect(0.9, 16.8, 14.2, 1.4, F.box),                                    // 底座
    rect(2.0, 1.2, 12.0, 15.6, F.box),                                    // 机柜柜体
    rect(2.8, 2.0, 10.4, 14.0, '#2b3540', { sw: 0.7 }),                   // 前面板（暗）
    ...[0, 1, 2, 3, 4, 5, 6, 7].map((i) => rect(3.3, 2.7 + i * 1.7, 8.2, 1.15, F.cyl)),   // 服务器插槽
    ...[0, 1, 2, 3, 4, 5, 6, 7].map((i) => ({
      tag: 'circle', cx: 12.2, cy: 3.25 + i * 1.7, r: 0.22,
      fill: i % 3 === 0 ? '#5fe08a' : '#4bb6e8', stroke: 'none',
    })),                                                                  // 运行指示灯
    { tag: 'path', d: 'M9.8 1.2 H13.4', fill: 'none', stroke: '#6c7a88', sw: 0.5, opacity: 0.8 },
  ),

  // —— 兜底：通用罐体（未覆盖的设备类型不至于变成空白） ——
  default: fig(20, 20,
    ground(10, 19.2, 5.6),
    cyl(10, 4.4, 17.4, 4.2, 1.4),
    { tag: 'path', d: 'M5.8 9.2 H14.2 M5.8 13 H14.2', fill: 'none', stroke: '#6c7a88', sw: 0.7, opacity: 0.8 },
    rect(3.6, 17.2, 12.8, 1.6, F.box),
  ),
}

// 别名：部分类型共用同一图形
T2D_FIGURES.cold_rolling = T2D_FIGURES.cold_rolling_mill
T2D_FIGURES.hot_rolling = T2D_FIGURES.rolling_mill
T2D_FIGURES.sinter = T2D_FIGURES.sinter_plant
T2D_FIGURES.pellet = T2D_FIGURES.pelletizing
T2D_FIGURES.coke = T2D_FIGURES.coke_oven
T2D_FIGURES.stove = T2D_FIGURES.hot_blast_stove
T2D_FIGURES.eaf_furnace = T2D_FIGURES.eaf
T2D_FIGURES.lf = T2D_FIGURES.ladle_furnace
T2D_FIGURES.rh = T2D_FIGURES.rh_vacuum
T2D_FIGURES.dri = T2D_FIGURES.dri_midrex
T2D_FIGURES.mill = T2D_FIGURES.rolling_mill
T2D_FIGURES.fan = T2D_FIGURES.id_fan
T2D_FIGURES.pump = T2D_FIGURES.cool_pump
T2D_FIGURES.boiler = T2D_FIGURES.aux_boiler
T2D_FIGURES.oxygen = T2D_FIGURES.oxy_supply

/** 取设备图形：未登记的类型回退 default（不会出现空白节点） */
export function figureOf(type) {
  return T2D_FIGURES[type] || T2D_FIGURES.default
}

/** 图形自身宽高比（供 Twin2DView 计算显示盒；图形真实边界 == 显示盒，无需外部标定） */
export function figureAspect(type) {
  const [w, h] = figureOf(type).vb
  return w / h
}

// ------------------------------ 高炉内腔轮廓（归一化 0~1） ------------------------------
// 温度分区叠加层与炉体图形**共用这一份数据**：y=0 炉喉顶、y=1 炉基底，
// x 为相对图形宽度的比例。这样两者永远对齐 —— 不再有「换图后坐标错位」的问题
// （旧方案 PROF 是 PNG 像素坐标，换图必须重新逐行标定）。
export const BF_PROFILE = [
  [0.000, 0.408, 0.592], [0.060, 0.394, 0.606], [0.115, 0.383, 0.617],
  [0.175, 0.372, 0.628], [0.240, 0.360, 0.640], [0.300, 0.348, 0.652],
  [0.360, 0.333, 0.667], [0.420, 0.317, 0.683], [0.473, 0.300, 0.700],
  [0.487, 0.283, 0.717],                                                  // 炉身→炉腰（最宽）
  [0.520, 0.282, 0.718], [0.548, 0.288, 0.712],                           // 炉腰
  [0.575, 0.300, 0.700], [0.610, 0.317, 0.683],                           // 炉腹（收口）
  [0.672, 0.333, 0.667], [0.700, 0.342, 0.658],                           // 风口带
  [0.730, 0.350, 0.650], [0.790, 0.354, 0.646],                           // 炉缸
  [0.860, 0.354, 0.646], [0.915, 0.300, 0.700], [1.000, 0.290, 0.710],    // 炉基
]
export const BF_ZONES = [
  { key: 'throat', y0: 0.000, y1: 0.090, cur: 200 },
  { key: 'shaft', y0: 0.090, y1: 0.470, cur: 800 },
  { key: 'belly', y0: 0.470, y1: 0.545, cur: 1200 },
  { key: 'bosh', y0: 0.545, y1: 0.650, cur: 1450 },
  { key: 'tuyere', y0: 0.650, y1: 0.720, cur: 2350 },
  { key: 'hearth', y0: 0.720, y1: 0.880, cur: 1500 },
  { key: 'base', y0: 0.880, y1: 1.000, cur: null },
]
/** 给定归一化 y，线性插值出内腔左右边界（0~1） */
export function bfProfAt(y) {
  const P = BF_PROFILE
  if (y <= P[0][0]) return [P[0][1], P[0][2]]
  const last = P[P.length - 1]
  if (y >= last[0]) return [last[1], last[2]]
  for (let i = 0; i < P.length - 1; i++) {
    const [ay, al, ar] = P[i]
    const [by, bl, br] = P[i + 1]
    if (y >= ay && y <= by) {
      const t = by === ay ? 0 : (y - ay) / (by - ay)
      return [al + (bl - al) * t, ar + (br - ar) * t]
    }
  }
  return [P[0][1], P[0][2]]
}
