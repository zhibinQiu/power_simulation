// 工业能碳智控平台 · 3D 场景管理器（原生 three.js）。
// 统一工程透视线框风格：设备外壳半透明 + 描边，内部可见；
// 容器类工序（高炉/转炉/电炉/精炼/连铸/加热炉）内按高度生成「温度分层」热力色带，
// 管道内以物料色流态呈现内容。面向 AI 数字孪生，强调「看清内部状态」。
// 碳排放「足迹」光斑 = 该工序碳排放占全厂比例（钢蓝->暗金->砖红，与图例一致）。
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { PARK } from '../data/park'
import { MATERIAL_MAP, PROCESS_MAP } from '../data/flowLibrary'
import { builderMap } from './builders/index.js'

// 赛博朋克工业科技蓝调色板（深邃虚空背景 + 霓虹蓝/青/紫/品红/橙发光）
const PAL = {
  terrain: 0x050810,    // 虚空近黑（比旧版暗3档）
  platform: 0x0c1424,  // 暗蓝黑金属基座
  road: 0x080c18,      // 近黑底
  lane: 0x00e5ff,      // 高亮霓虹青车道线
  grass: 0x081020,     // 近黑绿化
  wall: 0x141e30,      // 暗蓝灰厂房墙
  roof: 0x1a2538,      // 深蓝灰屋面
  steel: 0x2a4060,     // 科技蓝钢结构
  glass: 0x1080a0,     // 青蓝玻璃
  accent: 0x00d4ff,    // 霓虹青蓝强调色
  accent2: 0xe030f0,   // 霓虹品红辅助强调（更饱和）
  neonCyan: 0x00ffff,  // 高亮霓虹青（全饱和）
  neonBlue: 0x0088ff,  // 霓虹蓝
  neonPurple: 0x9933ff,// 霓虹紫（更亮）
  neonMagenta: 0xff00aa,// 新增：霓虹品红
  neonOrange: 0xff6600,// 新增：霓虹橙（工业熔融感）
  base: 0x0c1828,      // 暗蓝金属设备基础
  stack: 0x1a2538,     // 深蓝灰烟囱
  stackBand: 0x00e5ff, // 霓虹青环带
}

// 物料运输意象注册表：按 flow.material 区分「模型 + 运动风格」。
// molten=熔体（铁水/钢水）发光流动；granular=散料（烧结矿/焦炭/矿石等）翻滚；
// slab=板坯/钢材刚体滑移；chunk=废钢等不规则块翻滚。_default 兜底未知物料。
// 物料运输意象注册表：按 flow.material 区分「模型 + 运输媒介」。
// 状态映射（由 style 推导）：molten/liquid -> 液体（走「流槽」）；gas -> 气体（走「管道」）；granular/chunk/slab -> 固体（走「传送带」）。
const MAT_VIS = {
  // 熔体（液体）：铁水 / 钢水 —— 走「流槽」（低饱和工业熔融金属橙红，非霓虹）
  hot_metal:     { style: 'molten', color: 0xb05030, emissive: 0x7c2e16, emi: 0.45 },
  pre_hm:        { style: 'molten', color: 0xb55a34, emissive: 0x803318, emi: 0.45 },
  steel:         { style: 'molten', color: 0xbf6a30, emissive: 0x8a4018, emi: 0.45 },
  crude_steel:   { style: 'molten', color: 0xbf6a30, emissive: 0x8a4018, emi: 0.45 },
  refined_steel: { style: 'molten', color: 0xc67a3c, emissive: 0x94501c, emi: 0.45 },
  water:         { style: 'liquid', color: 0x3a6e8f },
  // 散料（固体）：走「传送带」（提亮配色，避免暗场发黑）
  sinter:        { style: 'granular', color: 0x7d93ab },
  pellet:        { style: 'granular', color: 0x6f8aa6 },
  coke:          { style: 'granular', color: 0x4a4660 },
  limestone:     { style: 'granular', color: 0x8696a6 },
  iron_ore:      { style: 'granular', color: 0x5c5c7a },
  coal:          { style: 'granular', color: 0x2e2e44 },
  dri:           { style: 'granular', color: 0x7a8aa0 },
  // 不规则块（固体）：废钢
  scrap:         { style: 'chunk', color: 0x5a6a80 },
  // 板坯 / 钢材
  billet:        { style: 'slab', color: 0xbf5a2e, emissive: 0x80301a, emi: 0.40 },
  steel_product: { style: 'slab', color: 0x5f7690 },
  // 气体：走「管道」（低饱和工业气流色）
  ldg:           { style: 'gas', color: 0x3f8f7a },
  cog:           { style: 'gas', color: 0x5a9a8f },
  bfg:           { style: 'gas', color: 0x4a8a80 },
  oxygen:        { style: 'gas', color: 0x3a7aa0 },
  ngas:          { style: 'gas', color: 0x7a6f95 },
  co2:           { style: 'gas', color: 0xa05a4c },
  _default:      { style: 'chunk', color: 0x5a6a80 },
}

// 核心孪生外围「环绕环境」配置（与项目无关的装饰景观，可手动切换，避免核心场景像半成品）。
// 每种模式各自定义地表色、天空渐变、大气雾；地表起伏在 setEnvironment 中按模式生成。
const ENV = {
  void: {
    ground: 0x050810,   // 赛博虚空：近黑深空（比旧版暗3档，营造深邃感）
    sky: ['#020408', '#061020', '#0c1830'],  // 三层渐变：天顶近黑 → 中段深蓝 → 地平线暗蓝
    fog: { color: 0x0c1830, near: 800, far: 4200 },  // 更浓更远的雾（增强纵深）
    water: null,
  },
  desert: {
    ground: 0xeaddc5,   // 浅沙色
    sky: ['#ffffff', '#f7efd8', '#ede0c8'],   // 暖色浅亮
    fog: { color: 0xf3e9d8, near: 1600, far: 5000 },
    water: null,
  },
  city: {
    ground: 0xdce3ea,   // 浅灰蓝
    sky: ['#ffffff', '#eef3f8', '#e1e9f2'],
    fog: { color: 0xeaf0f5, near: 1500, far: 4800 },
    water: null,
  },
  coast: {
    ground: 0xddecef,   // 浅海沙
    sky: ['#ffffff', '#eff8fb', '#e1f2f7'],
    fog: { color: 0xe8f4f8, near: 1400, far: 4600 },
    water: null,
  },
  industrial: {
    ground: 0xe8eaec,   // VS Code 浅色风格：明亮浅灰地坪（与系统浅灰 UI 协调）
    sky: ['#ffffff', '#f6f8fa', '#e9edf1'],  // 明亮冷白天幕：干净浅色制图背景，不压抑
    fog: null,  // 工业孪生不启用大气雾：去掉雾避免远景泛白、画面灰蒙，保证设备边缘锐利清晰
    water: null,
  },
}

const UNIT_META = {
  sinter_plant: { label: '烧结机', shape: 'sinter' },
  pelletizing: { label: '球团', shape: 'pellet' },
  coke_oven: { label: '焦炉', shape: 'coke' },
  reheating_furnace: { label: '加热炉', shape: 'reheat' },
  hot_metal_pretreat: { label: '铁水预处理', shape: 'pretreat' },
  blast_furnace: { label: '高炉', shape: 'furnace' },
  hydrogen_bf: { label: '氢冶金', shape: 'furnace' },
  h2_dri: { label: '氢基竖炉', shape: 'furnace' },
  dri_midrex: { label: '直接还原炉', shape: 'furnace' },
  smelting_reduction: { label: '熔融还原', shape: 'furnace' },
  biochar_injection: { label: '生物质喷吹', shape: 'cylinder' },
  bof: { label: '转炉', shape: 'converter' },
  eaf: { label: '电炉', shape: 'furnace' },
  ladle_furnace: { label: '精炼炉', shape: 'cylinder' },
  rh_vacuum: { label: 'RH精炼', shape: 'cylinder' },
  vd_vacuum: { label: 'VD脱气', shape: 'cylinder' },
  aod: { label: 'AOD精炼', shape: 'converter' },
  caster: { label: '连铸机', shape: 'slab' },
  ingot_casting: { label: '模铸', shape: 'ingot' },
  rolling_mill: { label: '热轧机', shape: 'rollers' },
  cold_rolling: { label: '冷轧机', shape: 'rollers' },
  gas_power: { label: '煤气发电', shape: 'utility' },
  waste_heat: { label: '余热回收', shape: 'utility' },
  ccs: { label: '碳捕集', shape: 'utility' },
  oxy_supply: { label: '供氧系统', shape: 'utility' },
  power_supply: { label: '供电系统', shape: 'utility' },
}

const SCALE = 1 // 世界单位 = 米（示意）
const UNIT_SCALE = 2.4  // 工艺本体整体放大系数（用户要求模型更大、更醒目）
const GROUP_SCENE_GAIN = 1.6  // 小组子场景（groupScene）成员模型再放大系数：进入小组后模型更大更醒目

// 赛博朋克材质工厂（高金属感、低粗糙度、蓝黑基底的工业科技质感）
function mat(color, o = {}) {
  return new THREE.MeshStandardMaterial(Object.assign({ color, roughness: 0.48, metalness: 0.42 }, o))
}

// 快速创建 BoxGeometry + 指定材质 Mesh 的便捷方法
function boxMesh(w, h, d, material) {
  return new THREE.Mesh(new THREE.BoxGeometry(w, h, d), material)
}

// ---------------- 工序小铭牌（模型旁只显示工序名，数据改由点击弹窗展示） ----------------
// 画布按「逻辑尺寸 × LABEL_SS」超采样绘制，再由 sRGB 纹理下采样呈现，保证文字锐利。
const LABEL_W = 165             // 逻辑宽（绘制坐标系）
const LABEL_H = 46              // 逻辑高（单行小铭牌）
const UNIT_LABEL_H = 64         // 工艺标签逻辑高（两行：工序名 + 实时能耗/碳排）
const LABEL_SS = 4              // 超采样倍率（清晰度关键：4x 保证远处放大 5.2x 后文字仍锐利）
const LABEL_PARENT_REF = 4.6    // 工艺标签世界尺寸基准：工艺模型父级缩放代表值，所有标签以此为统一大小
const LABEL_AUX_GAIN = 0.72     // 工辅/小组标签相对工艺标签的小一号系数（0.85→0.72 再小一号）
const LABEL_SCALE = 6.5         // 世界坐标下的铭牌宽度：工序标签与管道/轨道连接标签统一尺寸
const LABEL_ASPECT = LABEL_H / LABEL_W
const LABEL_FOCUS_GAIN = 1.2    // 聚焦时的放大倍率
const LABEL_FONT = '"PingFang SC","Microsoft YaHei",-apple-system,sans-serif'
const LABEL_NUM_FONT = '"SF Mono","Roboto Mono",Consolas,"Courier New","PingFang SC",sans-serif'

function _fmtMetric(v) {
  if (v == null || Number.isNaN(Number(v))) return '—'
  return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 1 })
}

// 标签底板：light=true 时绘制 VS Code 浅色扁平卡片（白底/浅灰边框/聚焦蓝描边）；
// 否则绘制深色毛玻璃铭牌（半透明面板、亚光边框、聚焦时蓝色辉光）。
// 简约风：无名称左侧竖线、无选中态上方横线，仅以边框/描边区分选中。
// h 为可选卡片高度（工艺标签为两行 UNIT_LABEL_H，其余保持单行 LABEL_H）
function _drawLabelCard(ctx, focused, role, slim, main, light, h = LABEL_H) {
  const W = LABEL_W, H = h
  const r = 9

  ctx.save()

  if (light) {
    // ===== VS Code 浅色卡片 =====
    // 柔和投影（浅色下用淡灰，不喧宾夺主）
    ctx.shadowColor = focused ? 'rgba(0,94,148,0.30)' : 'rgba(0,0,0,0.12)'
    ctx.shadowBlur = focused ? 10 : 5
    ctx.shadowOffsetX = 0
    ctx.shadowOffsetY = focused ? 0 : 1

    // 白底（聚焦时淡蓝底）
    ctx.beginPath()
    _roundRect(ctx, 1, 1, W - 2, H - 2, r)
    ctx.fillStyle = focused ? 'rgba(226,240,253,0.97)' : 'rgba(255,255,255,0.97)'
    ctx.fill()

    ctx.restore()

    // 边框：聚焦 = 强调蓝 2px；普通 = 细浅灰（简约 VS Code 风，无装饰条）
    ctx.beginPath()
    _roundRect(ctx, 1, 1, W - 2, H - 2, r)
    ctx.strokeStyle = focused ? 'rgba(0,94,148,0.9)' : 'rgba(214,219,225,1)'
    ctx.lineWidth = focused ? 2 : 1
    ctx.stroke()
    return
  }

  // ===== 深色毛玻璃铭牌（赛博/默认模式） =====
  // 柔和投影/辉光：聚焦时蓝色外发光，普通时暗色投影增加层次
  ctx.shadowColor = focused ? 'rgba(0,168,255,0.55)' : 'rgba(0,0,0,0.35)'
  ctx.shadowBlur = focused ? 14 : 8
  ctx.shadowOffsetX = 0
  ctx.shadowOffsetY = focused ? 0 : 2

  // 深色半透明面板底色（聚焦时亮度略高、更不透明）
  ctx.beginPath()
  _roundRect(ctx, 1, 1, W - 2, H - 2, r)
  ctx.fillStyle = focused ? 'rgba(32,40,52,0.92)' : 'rgba(22,26,34,0.88)'
  ctx.fill()

  ctx.restore()

  // 边框：聚焦 = 蓝色辉光边框；普通 = 微透明白边（简约风，无顶部横线/左侧竖线）
  ctx.beginPath()
  _roundRect(ctx, 1, 1, W - 2, H - 2, r)
  ctx.strokeStyle = focused ? 'rgba(0,168,255,0.85)' : 'rgba(255,255,255,0.14)'
  ctx.lineWidth = focused ? 2 : 1
  ctx.stroke()
}

// 轧辊表面条纹纹理（缓存复用）
let _rollerTexCache = null
function _rollerTex() {
  if (_rollerTexCache) return _rollerTexCache
  const c = document.createElement('canvas')
  c.width = c.height = 64
  const ctx = c.getContext('2d')
  ctx.fillStyle = '#8b95a1'
  ctx.fillRect(0, 0, 64, 64)
  ctx.fillStyle = '#586070'
  for (let i = -64; i < 64; i += 14) ctx.fillRect(i, 0, 7, 64)
  const t = new THREE.CanvasTexture(c)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.repeat.set(1, 3)
  _rollerTexCache = t
  return t
}

// ============== 工业级程序化贴图库（缓存复用，对齐参考图风格）==============

// 工具：生成带 noise 的 canvas 纹理，返回已设置 sRGB + RepeatWrapping 的 CanvasTexture
function _makeCanvasTex(w, h, draw, repeat = null) {
  const c = document.createElement('canvas')
  c.width = w; c.height = h
  const ctx = c.getContext('2d')
  draw(ctx, w, h)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.anisotropy = 4
  if (repeat) t.repeat.set(repeat[0] || 1, repeat[1] || 1)
  return t
}

// —— 真实密集草地 ——（高密度像素级草叶模拟，远超噪点贴图的自然感）
let _grassTexCache = null
function _grassTex() {
  if (_grassTexCache) return _grassTexCache
  const SZ = 1024
  const t = _makeCanvasTex(SZ, SZ, (ctx, w, h) => {
    // 底层：沉稳的泥土/腐殖质底色
    ctx.fillStyle = '#5c6e40'
    ctx.fillRect(0, 0, w, h)

    // 像素级密集草叶：逐像素写入不同的绿色调，模拟成千上万草叶交错
    const img = ctx.getImageData(0, 0, w, h)
    const d = img.data
    // 随机种子产生"草叶流"——沿微小方向的连续像素，模拟单株草叶的走势
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        const idx = (y * w + x) * 4
        // 每像素随机选择草叶颜色：深绿/中绿/浅绿/黄绿/枯草，形成密集交错感
        const rn = Math.random()
        let rv, gv, bv
        if (rn < 0.28) {
          // 深绿草叶（基部/阴影草）
          rv = 58 + Math.random() * 14; gv = 102 + Math.random() * 18; bv = 38 + Math.random() * 10
        } else if (rn < 0.52) {
          // 中绿草叶（主体草）
          rv = 74 + Math.random() * 16; gv = 126 + Math.random() * 20; bv = 48 + Math.random() * 12
        } else if (rn < 0.70) {
          // 亮绿草叶（新草/草尖）
          rv = 96 + Math.random() * 18; gv = 148 + Math.random() * 22; bv = 56 + Math.random() * 14
        } else if (rn < 0.83) {
          // 黄绿草叶（半枯/阳光照射）
          rv = 120 + Math.random() * 20; gv = 148 + Math.random() * 20; bv = 62 + Math.random() * 16
        } else if (rn < 0.92) {
          // 枯草/干草
          rv = 155 + Math.random() * 25; gv = 142 + Math.random() * 20; bv = 72 + Math.random() * 18
        } else {
          // 浅干草/近乎土色
          rv = 150 + Math.random() * 30; gv = 132 + Math.random() * 28; bv = 82 + Math.random() * 22
        }
        d[idx] = rv
        d[idx + 1] = gv
        d[idx + 2] = bv
        d[idx + 3] = 255
      }
    }
    ctx.putImageData(img, 0, 0)

    // 微小草丛细节：额外叠加细短草叶簇（多个 1-2px 纵向笔画）
    for (let i = 0; i < 60000; i++) {
      const cx = Math.floor(Math.random() * w)
      const cy = Math.floor(Math.random() * h)
      const bladeH = 2 + Math.floor(Math.random() * 12)
      const alpha = 0.06 + Math.random() * 0.14
      const shade = Math.random() < 0.5
      const r = 100 + Math.random() * 50
      const g = 130 + Math.random() * 50
      const b = 40 + Math.random() * 20
      ctx.strokeStyle = shade
        ? `rgba(${Math.floor(r * 0.55)},${Math.floor(g * 0.55)},${Math.floor(b * 0.55)},${alpha})`
        : `rgba(${r},${g},${b},${alpha})`
      ctx.lineWidth = 0.6 + Math.random() * 1.0
      ctx.beginPath()
      const sway = (Math.random() - 0.5) * 2.5
      ctx.moveTo(cx, cy)
      ctx.lineTo(cx + sway, cy - bladeH)
      ctx.stroke()
    }

    // 极少量微小野花（白色/浅黄点缀，仅在局部出现）
    for (let i = 0; i < 900; i++) {
      const fx = Math.random() * w
      const fy = Math.random() * h
      const alpha = 0.12 + Math.random() * 0.18
      ctx.fillStyle = Math.random() < 0.5
        ? `rgba(248,248,225,${alpha})`
        : `rgba(255,245,160,${alpha})`
      ctx.beginPath()
      ctx.arc(fx, fy, 0.7 + Math.random() * 0.8, 0, Math.PI * 2)
      ctx.fill()
    }
  }, [24, 24])
  _grassTexCache = t
  return t
}

// —— 沙漠地表（暖色沙砾，细颗粒噪点 + 风蚀纹理）——
let _desertTexCache = null
function _desertTex() {
  if (_desertTexCache) return _desertTexCache
  const SZ = 1024
  const t = _makeCanvasTex(SZ, SZ, (ctx, w, h) => {
    // 基底：暖沙色
    ctx.fillStyle = '#d4b896'
    ctx.fillRect(0, 0, w, h)
    // 细颗粒噪点
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = 0.85 + Math.random() * 0.3
      img.data[i] = Math.min(255, img.data[i] * n)
      img.data[i + 1] = Math.min(255, img.data[i + 1] * n)
      img.data[i + 2] = Math.min(255, img.data[i + 2] * n)
    }
    ctx.putImageData(img, 0, 0)
    // 风蚀纹理：浅色条纹
    ctx.globalAlpha = 0.12
    for (let i = 0; i < 40; i++) {
      const y = Math.random() * h
      const len = 80 + Math.random() * 300
      const grad = ctx.createLinearGradient(0, y, len, y)
      grad.addColorStop(0, '#e8d8c0')
      grad.addColorStop(1, 'rgba(232,216,192,0)')
      ctx.fillStyle = grad
      ctx.fillRect(Math.random() * w, y - 1, len, 2 + Math.random() * 3)
    }
    ctx.globalAlpha = 1
  }, [16, 16])
  _desertTexCache = t
  return t
}

// —— 城市地表（水泥/沥青灰调，细微路面纹理）——
let _cityTexCache = null
function _cityTex() {
  if (_cityTexCache) return _cityTexCache
  const SZ = 1024
  const t = _makeCanvasTex(SZ, SZ, (ctx, w, h) => {
    ctx.fillStyle = '#9ea8b4'
    ctx.fillRect(0, 0, w, h)
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = 0.88 + Math.random() * 0.24
      img.data[i] = Math.min(255, img.data[i] * n)
      img.data[i + 1] = Math.min(255, img.data[i + 1] * n)
      img.data[i + 2] = Math.min(255, img.data[i + 2] * n)
    }
    ctx.putImageData(img, 0, 0)
    // 细微路面开裂纹理
    ctx.globalAlpha = 0.06
    ctx.strokeStyle = '#6e7884'
    ctx.lineWidth = 0.5
    for (let i = 0; i < 20; i++) {
      ctx.beginPath()
      ctx.moveTo(Math.random() * w, Math.random() * h)
      ctx.lineTo(Math.random() * w, Math.random() * h)
      ctx.stroke()
    }
    ctx.globalAlpha = 1
  }, [16, 16])
  _cityTexCache = t
  return t
}

// —— 工业地表（深钢灰混凝土，规整分格缝 + 低对比颗粒 + 浇筑色差 + 刮痕：干净严谨的厂区地坪）——
let _industrialTexCache = null
function _industrialTex() {
  if (_industrialTexCache) return _industrialTexCache
  const SZ = 1024
  const t = _makeCanvasTex(SZ, SZ, (ctx, w, h) => {
    // 基底：VS Code 风格浅灰地坪（干净、明亮、与浅色 UI 协调）
    ctx.fillStyle = '#e3e6ea'
    ctx.fillRect(0, 0, w, h)

    const img = ctx.getImageData(0, 0, w, h)
    const d = img.data

    // 第 1 层：极细颗粒噪声（弱化到几乎不可见，保持干净质感）
    for (let i = 0; i < d.length; i += 4) {
      const n = 0.975 + Math.random() * 0.05
      d[i] = Math.min(255, d[i] * n)
      d[i + 1] = Math.min(255, d[i + 1] * n)
      d[i + 2] = Math.min(255, d[i + 2] * n)
    }

    // 第 2 层：大面积极淡色差斑块（低频噪声，弱化到几乎不可见）
    for (let i = 0; i < 20; i++) {
      const cx = Math.random() * w
      const cy = Math.random() * h
      const r = 90 + Math.random() * 180
      const shade = 0.97 + Math.random() * 0.06
      const y0 = Math.max(0, Math.floor(cy - r))
      const y1 = Math.min(h, Math.ceil(cy + r))
      const x0 = Math.max(0, Math.floor(cx - r))
      const x1 = Math.min(w, Math.ceil(cx + r))
      for (let y = y0; y < y1; y++) {
        for (let x = x0; x < x1; x++) {
          const dx = x - cx, dy = y - cy
          const dist = Math.sqrt(dx * dx + dy * dy) / r
          if (dist >= 1) continue
          const idx = (y * w + x) * 4
          const falloff = 1 - dist * dist
          const m = (0.99 + shade * 0.01 * falloff)
          d[idx] = Math.min(255, d[idx] * m)
          d[idx + 1] = Math.min(255, d[idx + 1] * m)
          d[idx + 2] = Math.min(255, d[idx + 2] * m)
        }
      }
    }
    ctx.putImageData(img, 0, 0)

    // 规整分格缝：8×8 等分施工缝（极淡浅灰，体现秩序而不抢设备视觉）
    ctx.strokeStyle = 'rgba(158,168,180,0.28)'
    ctx.lineWidth = 2
    ctx.beginPath()
    for (let i = 1; i < 8; i++) {
      const p = (w / 8) * i
      ctx.moveTo(p, 0); ctx.lineTo(p, h)
      ctx.moveTo(0, p); ctx.lineTo(w, p)
    }
    ctx.stroke()
  }, [16, 16])
  _industrialTexCache = t
  return t
}

// —— 海滩地表（浅米白沙色，湿润斑块）——
let _coastTexCache = null
function _coastTex() {
  if (_coastTexCache) return _coastTexCache
  const SZ = 1024
  const t = _makeCanvasTex(SZ, SZ, (ctx, w, h) => {
    ctx.fillStyle = '#e6dfd2'
    ctx.fillRect(0, 0, w, h)
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = 0.88 + Math.random() * 0.24
      img.data[i] = Math.min(255, img.data[i] * n)
      img.data[i + 1] = Math.min(255, img.data[i + 1] * n)
      img.data[i + 2] = Math.min(255, img.data[i + 2] * n)
    }
    ctx.putImageData(img, 0, 0)
    // 湿润潮汐斑块
    ctx.globalAlpha = 0.08
    for (let i = 0; i < 12; i++) {
      const cx = Math.random() * w, cy = Math.random() * h
      const grad = ctx.createRadialGradient(cx, cy, 10, cx, cy, 60 + Math.random() * 80)
      grad.addColorStop(0, '#c8d4d8')
      grad.addColorStop(1, 'rgba(200,212,216,0)')
      ctx.fillStyle = grad
      ctx.fillRect(cx - 80, cy - 80, 160, 160)
    }
    ctx.globalAlpha = 1
  }, [16, 16])
  _coastTexCache = t
  return t
}

// —— 工业厂房外墙（钢蓝灰彩钢板，竖向波纹瓦楞）——
let _wallPanelTexCache = null
function _wallPanelTex() {
  if (_wallPanelTexCache) return _wallPanelTexCache
  const t = _makeCanvasTex(512, 256, (ctx, w, h) => {
    ctx.fillStyle = '#aab6c2'
    ctx.fillRect(0, 0, w, h)
    // 竖向波纹（亮暗相间）
    const ribs = 14
    for (let i = 0; i < ribs; i++) {
      const x = (i + 0.5) * (w / ribs)
      const half = (w / ribs) * 0.5
      const g = ctx.createLinearGradient(x - half, 0, x + half, 0)
      g.addColorStop(0, 'rgba(255,255,255,0.18)')
      g.addColorStop(0.5, 'rgba(255,255,255,0)')
      g.addColorStop(1, 'rgba(0,0,0,0.18)')
      ctx.fillStyle = g
      ctx.fillRect(x - half, 0, half * 2, h)
    }
    // 横向接缝（每 h / 4 一道）
    for (let y = 0; y < h; y += h / 4) {
      ctx.fillStyle = 'rgba(0,0,0,0.20)'
      ctx.fillRect(0, y, w, 2)
    }
    // 细微噪点
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 14
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
  }, [1, 1])
  _wallPanelTexCache = t
  return t
}

// —— 工业厂房屋面（深灰屋面 + 横向接缝）——
let _roofPanelTexCache = null
function _roofPanelTex() {
  if (_roofPanelTexCache) return _roofPanelTexCache
  const t = _makeCanvasTex(512, 256, (ctx, w, h) => {
    ctx.fillStyle = '#6a727a'
    ctx.fillRect(0, 0, w, h)
    // 横向接缝
    for (let y = 0; y < h; y += 32) {
      ctx.fillStyle = 'rgba(0,0,0,0.30)'
      ctx.fillRect(0, y, w, 2)
    }
    // 锈渍
    for (let i = 0; i < 18; i++) {
      const x = Math.random() * w, y = Math.random() * h, r = 8 + Math.random() * 30
      const g = ctx.createRadialGradient(x, y, 0, x, y, r)
      g.addColorStop(0, 'rgba(120,72,48,0.20)')
      g.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g
      ctx.fillRect(x - r, y - r, r * 2, r * 2)
    }
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 12
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
  }, [1, 1])
  _roofPanelTexCache = t
  return t
}

// —— 烟囱/筒体竖向条纹（混凝土+涂装分节）——
let _stackPanelTexCache = null
function _stackPanelTex() {
  if (_stackPanelTexCache) return _stackPanelTexCache
  const t = _makeCanvasTex(256, 512, (ctx, w, h) => {
    // 红白相间（参考图标志色）
    const segH = 64
    for (let y = 0; y < h; y += segH) {
      ctx.fillStyle = (y / segH) % 2 === 0 ? '#d8d2c4' : '#a6423a'
      ctx.fillRect(0, y, w, segH)
    }
    // 白色分段的轻微阴影渐变（圆柱光照感）
    const gv = ctx.createLinearGradient(0, 0, w, 0)
    gv.addColorStop(0, 'rgba(0,0,0,0.30)')
    gv.addColorStop(0.5, 'rgba(0,0,0,0)')
    gv.addColorStop(1, 'rgba(255,255,255,0.10)')
    ctx.fillStyle = gv
    ctx.fillRect(0, 0, w, h)
    // 噪点
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 14
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
  }, [1, 1])
  _stackPanelTexCache = t
  return t
}

// —— 储罐/筒体金属面板（横向带加强筋的圆柱面贴图）——
let _tankShellTexCache = null
function _tankShellTex() {
  if (_tankShellTexCache) return _tankShellTexCache
  const t = _makeCanvasTex(512, 256, (ctx, w, h) => {
    ctx.fillStyle = '#c9cfd4'
    ctx.fillRect(0, 0, w, h)
    // 横向加强筋（每 ~40px 一道）
    for (let y = 0; y < h; y += 40) {
      ctx.fillStyle = 'rgba(60,70,80,0.40)'
      ctx.fillRect(0, y, w, 3)
      ctx.fillStyle = 'rgba(255,255,255,0.20)'
      ctx.fillRect(0, y + 3, w, 1)
    }
    // 整体光照（顶亮底暗）
    const gv = ctx.createLinearGradient(0, 0, w, 0)
    gv.addColorStop(0, 'rgba(0,0,0,0.30)')
    gv.addColorStop(0.4, 'rgba(0,0,0,0)')
    gv.addColorStop(0.6, 'rgba(0,0,0,0)')
    gv.addColorStop(1, 'rgba(0,0,0,0.30)')
    ctx.fillStyle = gv
    ctx.fillRect(0, 0, w, h)
    // 锈蚀/污渍
    for (let i = 0; i < 16; i++) {
      const x = Math.random() * w, y = Math.random() * h, r = 10 + Math.random() * 26
      const g = ctx.createRadialGradient(x, y, 0, x, y, r)
      g.addColorStop(0, 'rgba(140,80,52,0.22)')
      g.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g
      ctx.fillRect(x - r, y - r, r * 2, r * 2)
    }
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 10
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
  }, [2, 1])
  _tankShellTexCache = t
  return t
}

// —— 集装箱波纹（侧面竖向瓦楞 + 标志色）——
let _containerTexCache = null
function _containerTex(color = '#3b6da0') {
  const key = `${_containerTexCache}_${color}`
  // 简单缓存：每次都新建但用单色字段
  const t = _makeCanvasTex(256, 256, (ctx, w, h) => {
    ctx.fillStyle = color
    ctx.fillRect(0, 0, w, h)
    const ribs = 12
    for (let i = 0; i < ribs; i++) {
      const x = (i + 0.5) * (w / ribs)
      const half = (w / ribs) * 0.5
      const g = ctx.createLinearGradient(x - half, 0, x + half, 0)
      g.addColorStop(0, 'rgba(255,255,255,0.15)')
      g.addColorStop(0.5, 'rgba(255,255,255,0)')
      g.addColorStop(1, 'rgba(0,0,0,0.20)')
      ctx.fillStyle = g
      ctx.fillRect(x - half, 0, half * 2, h)
    }
    // 门把手条 + 小窗
    ctx.fillStyle = 'rgba(0,0,0,0.32)'
    ctx.fillRect(20, 30, 6, h - 60)
    ctx.fillRect(w - 26, 30, 6, h - 60)
    ctx.fillStyle = 'rgba(255,255,255,0.10)'
    ctx.fillRect(0, 30, w, 4)
    ctx.fillRect(0, h - 34, w, 4)
    // 编号
    ctx.fillStyle = '#fff'
    ctx.font = 'bold 38px sans-serif'
    ctx.textAlign = 'center'
    ctx.fillText('CN·' + (1000 + Math.floor(Math.random() * 8999)), w / 2, h / 2 + 14)
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 12
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
  }, [1, 1])
  return t
}

// —— 钢筋/钢架结构（参考图大量钢灰色钢架）——
let _steelTexCache = null
function _steelTex() {
  if (_steelTexCache) return _steelTexCache
  const t = _makeCanvasTex(256, 256, (ctx, w, h) => {
    ctx.fillStyle = '#6b7680'
    ctx.fillRect(0, 0, w, h)
    // 锈斑
    for (let i = 0; i < 14; i++) {
      const x = Math.random() * w, y = Math.random() * h, r = 6 + Math.random() * 22
      const g = ctx.createRadialGradient(x, y, 0, x, y, r)
      g.addColorStop(0, 'rgba(150,90,60,0.25)')
      g.addColorStop(1, 'rgba(0,0,0,0)')
      ctx.fillStyle = g
      ctx.fillRect(x - r, y - r, r * 2, r * 2)
    }
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 16
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
  }, [1, 1])
  _steelTexCache = t
  return t
}

// —— 沥青道路 ——（深灰沥青 + 虚线车道线）
let _asphaltTexCache = null
function _asphaltTex() {
  if (_asphaltTexCache) return _asphaltTexCache
  const t = _makeCanvasTex(512, 512, (ctx, w, h) => {
    ctx.fillStyle = '#4a4d52'
    ctx.fillRect(0, 0, w, h)
    // 噪点骨料
    const img = ctx.getImageData(0, 0, w, h)
    for (let i = 0; i < img.data.length; i += 4) {
      const n = (Math.random() - 0.5) * 22
      img.data[i] = Math.max(0, Math.min(255, img.data[i] + n))
      img.data[i + 1] = Math.max(0, Math.min(255, img.data[i + 1] + n))
      img.data[i + 2] = Math.max(0, Math.min(255, img.data[i + 2] + n))
    }
    ctx.putImageData(img, 0, 0)
    // 虚线车道线
    ctx.fillStyle = '#f0d864'
    for (let y = 0; y < h; y += 56) {
      ctx.fillRect(w / 2 - 4, y + 12, 8, 28)
    }
  }, [4, 4])
  _asphaltTexCache = t
  return t
}

// —— 山影天空纹理（远处山脉剪影，叠加在天空盒底部）——
let _mountainSkyCache = null
function _mountainSkySkyTex() {
  if (_mountainSkyCache) return _mountainSkyCache
  const c = document.createElement('canvas')
  c.width = 16; c.height = 256
  const ctx = c.getContext('2d')
  // 天顶
  const g = ctx.createLinearGradient(0, 0, 0, 256)
  g.addColorStop(0.0, '#4a8ec5')   // 天顶钢蓝
  g.addColorStop(0.55, '#a8d2e8')  // 中段
  g.addColorStop(0.85, '#e6efe8')  // 接近地平线（变暖白）
  g.addColorStop(1.0, '#d6d0c6')   // 地平线（暖灰，对应远处山脚）
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 16, 256)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  _mountainSkyCache = t
  return t
}

// 碳排放「足迹」柔光贴图（白色径向渐变，可被材质 color 染色），用于工序下方低饱和光斑
let _footTexCache = null
function _footTex() {
  if (_footTexCache) return _footTexCache
  const c = document.createElement('canvas')
  c.width = c.height = 128
  const ctx = c.getContext('2d')
  const g = ctx.createRadialGradient(64, 64, 4, 64, 64, 62)
  g.addColorStop(0, 'rgba(255,255,255,0.95)')
  g.addColorStop(0.55, 'rgba(255,255,255,0.45)')
  g.addColorStop(1, 'rgba(255,255,255,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, 128, 128)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  _footTexCache = t
  return t
}

// 圆角矩形路径（供画布绘制复用：工序标签药丸等）
function _roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath()
  ctx.moveTo(x + r, y)
  ctx.arcTo(x + w, y, x + w, y + h, r)
  ctx.arcTo(x + w, y + h, x, y + h, r)
  ctx.arcTo(x, y + h, x, y, r)
  ctx.arcTo(x, y, x + w, y, r)
  ctx.closePath()
}

// 数值短格式化（小组标签汇总能耗/碳排展示）：大数加 k/M 后缀，保留 1~2 位有效数字
function fmtShort(v) {
  if (v == null || isNaN(v)) return '—'
  const a = Math.abs(v)
  if (a >= 1e6) return (v / 1e6).toFixed(a >= 1e7 ? 0 : 1) + 'M'
  if (a >= 1e3) return (v / 1e3).toFixed(a >= 1e4 ? 0 : 1) + 'k'
  if (a >= 1) return v.toFixed(a >= 10 ? 0 : 1)
  if (a >= 0.01) return v.toFixed(2)
  return v.toFixed(3)
}


// 碳排放占比 → 工业色阶（钢蓝 → 琥珀 → 砖红，与右侧「排放占比」图例一致）
const SHARE_SCALE_MAX = 0.25
const _SHARE_STOPS = [
  [61, 110, 140],    // 钢蓝（低占比）
  [201, 162, 59],    // 琥珀（中占比）
  [192, 86, 76],     // 砖红（高占比）
]
function _lerpStop(a, b, t) {
  return [
    Math.round(a[0] + (b[0] - a[0]) * t),
    Math.round(a[1] + (b[1] - a[1]) * t),
    Math.round(a[2] + (b[2] - a[2]) * t),
  ]
}
function emissionColor(share) {
  const t = Math.max(0, Math.min(1, (share || 0) / SHARE_SCALE_MAX))
  let c
  if (t < 0.5) c = _lerpStop(_SHARE_STOPS[0], _SHARE_STOPS[1], t / 0.5)
  else c = _lerpStop(_SHARE_STOPS[1], _SHARE_STOPS[2], (t - 0.5) / 0.5)
  return new THREE.Color(c[0] / 255, c[1] / 255, c[2] / 255)
}
function emissionCss(share) {
  const t = Math.max(0, Math.min(1, (share || 0) / SHARE_SCALE_MAX))
  let c
  if (t < 0.5) c = _lerpStop(_SHARE_STOPS[0], _SHARE_STOPS[1], t / 0.5)
  else c = _lerpStop(_SHARE_STOPS[1], _SHARE_STOPS[2], (t - 0.5) / 0.5)
  return `rgb(${c[0]},${c[1]},${c[2]})`
}

// —— 连廊/路径构建共享资源（模块级常量，一次创建全场景复用）——
// 各工艺 IO 端口：模型空间 Y（乘 yStretch×scale 换算世界）与 XZ 偏移（乘 scale）
const IO_Y_DEFS = {
  blast_furnace: { inY: 55, outY: 4 },
  eaf: { inY: 12, outY: 3 }, furnace: { inY: 12, outY: 3 },
  bof: { inY: 14, outY: 2 }, converter: { inY: 14, outY: 2 },
  ladle_furnace: { inY: 10, outY: 3 }, rh_vacuum: { inY: 10, outY: 3 }, cylinder: { inY: 10, outY: 3 },
  caster: { inY: 12, outY: 3 }, slab_caster: { inY: 12, outY: 3 },
  rolling_mill: { inY: 4, outY: 4 },
  sinter_plant: { inY: 9, outY: 3 }, pelletizing: { inY: 9, outY: 3 },
  coke_oven: { inY: 14, outY: 3 },
  hot_metal_pretreat: { inY: 7, outY: 2 }, ingot_casting: { inY: 15, outY: 2 },
  reheating_furnace: { inY: 5, outY: 5 },
  gas_power: { inY: 6, outY: 6 }, waste_heat: { inY: 6, outY: 6 }, ccs: { inY: 6, outY: 6 },
  oxy_supply: { inY: 6, outY: 6 }
}
const Y_STRETCH_DEFS = {
  blast_furnace: 1.0, eaf: 1.4, furnace: 1.4, bof: 1.4, converter: 1.4,
  ladle_furnace: 1.35, rh_vacuum: 1.35, cylinder: 1.35,
  caster: 1.45, slab_caster: 1.45, rolling_mill: 1.45,
  sinter_plant: 1.4, pelletizing: 1.4, coke_oven: 1.4,
  hot_metal_pretreat: 1.5, ingot_casting: 1.45,
  reheating_furnace: 1.5, gas_power: 1.3, waste_heat: 1.3, ccs: 1.3, oxy_supply: 1.3
}
const SCALE_DEFS = {
  blast_furnace: 4.0, eaf: 5.0, furnace: 5.0, bof: 5.0, converter: 5.0,
  ladle_furnace: 4.6, rh_vacuum: 4.6, cylinder: 4.6,
  caster: 4.6, slab_caster: 4.6, rolling_mill: 4.6,
  sinter_plant: 4.6, pelletizing: 4.6, coke_oven: 4.6,
  hot_metal_pretreat: 4.2, ingot_casting: 4.2,
  reheating_furnace: 4.2, gas_power: 3.8, waste_heat: 3.5, ccs: 3.5, oxy_supply: 3.8
}
// 各工艺 IO 端口在模型空间的 XZ 偏移（反映实际出铁口/兑铁口/铸坯出口等真实位置）
const PORT_OFFSET_DEFS = {
  blast_furnace:    { outX:  15, outZ: 0,  inX:   0, inZ: 0 },  // 出铁口右侧；装料口顶部中心
  bof:              { outX:   8, outZ: 3,  inX:   0, inZ: 0 },  // 出钢口右下侧；兑铁口顶部
  converter:        { outX:   8, outZ: 3,  inX:   0, inZ: 0 },
  eaf:              { outX:   8, outZ: 2,  inX:   0, inZ: 0 },  // 出钢口右下侧
  furnace:          { outX:   8, outZ: 2,  inX:   0, inZ: 0 },
  ladle_furnace:    { outX:   5, outZ: 0,  inX:   0, inZ: 0 },  // 精炼钢包底部出口
  rh_vacuum:        { outX:   5, outZ: 0,  inX:   0, inZ: 0 },
  cylinder:         { outX:   5, outZ: 0,  inX:   0, inZ: 0 },
  caster:           { outX:  13, outZ: 0,  inX:   0, inZ: 0 },  // 铸坯出口水平右侧；中间包顶部入
  slab_caster:      { outX:  13, outZ: 0,  inX:   0, inZ: 0 },
  rolling_mill:     { outX:  13, outZ: 0,  inX: -13, inZ: 0 },  // 水平贯通：从左入右出
  sinter_plant:     { outX:  10, outZ: 0,  inX:  -9, inZ: 0 },  // 入口：矿槽端（左）；出口：筛分/成品带（右）
  pelletizing:      { outX:  10, outZ: 0,  inX: -10, inZ: 0 },  // 入口：造球盘端（左）；出口：环冷机/成品（右）
  coke_oven:        { outX:  10, outZ: 0,  inX:   0, inZ: 0 },
  hot_metal_pretreat:{ outX:   5, outZ: 0,  inX:   0, inZ: 0 },
  ingot_casting:    { outX:   6, outZ: 0,  inX:   0, inZ: 0 },
  reheating_furnace:{ outX:   8, outZ: 0,  inX:  -8, inZ: 0 },
  gas_power:        { outX:   5, outZ: 0,  inX:  -5, inZ: 0 },
  waste_heat:       { outX:   5, outZ: 0,  inX:  -5, inZ: 0 },
  ccs:              { outX:   5, outZ: 0,  inX:  -5, inZ: 0 },
  oxy_supply:       { outX:   5, outZ: 0,  inX:  -5, inZ: 0 }
}

// 共享单位几何体：所有连廊段/法兰共用一个几何体，通过 Mesh.scale 适配长度，
// 避免每段新建几何体；userData.__shared 标记使 dispose 时跳过，全局复用不释放
const GEO_UNIT_BOX = new THREE.BoxGeometry(1, 1, 1)
const GEO_UNIT_CYL = new THREE.CylinderGeometry(1, 1, 1, 12, 1, true)
const GEO_UNIT_CYL_IN = new THREE.CylinderGeometry(1, 1, 1, 10, 1, true)
const GEO_TORUS = new THREE.TorusGeometry(2.45, 0.26, 8, 14)
const GEO_UNIT_ICO = new THREE.IcosahedronGeometry(1, 1)
GEO_UNIT_BOX.userData.__shared = GEO_UNIT_CYL.userData.__shared =
  GEO_UNIT_CYL_IN.userData.__shared = GEO_TORUS.userData.__shared =
  GEO_UNIT_ICO.userData.__shared = true

const VEC_UP = new THREE.Vector3(0, 1, 0)
const VEC_X = new THREE.Vector3(1, 0, 0)
const PIPE_R = 2.05  // 气体管道外半径（内壁发光层半径 = PIPE_R - 0.3）

export class TwinScene {
  constructor(container, opts = {}) {
    this.container = container
    this.envMode = opts.envMode || 'void'
    this.unitGroups = new Map()
    this.groupModels = new Map()   // 小组 gid → 小组聚合模型（供 focusGroup 直接定位，不依赖成员 id）
    this.deviceMap = new Map()
    this._edgeMaterials = []   // 各工艺外壳描边材质（随场景明暗切换颜色）
    this.flows = []
    this.clock = new THREE.Clock()
    this.autoRotate = false
    this.onSelectUnit = null
    this.onFocusGroup = null    // 单击小组标签/成员 → 聚焦（相机+选中），由宿主绑定
    this.onSelectGroup = null   // 双击小组标签/成员 → 进入小组子场景回调（组 id），由宿主绑定
    this.onSelectDevice = null
    this._focus = null
    this.focusedId = null          // 当前聚焦/选中的工序（用于同步高亮其唯一标签与选中环）
    this.focusedFlowId = null      // 当前聚焦的管道连线标签
    this._ray = new THREE.Raycaster()
    this._suppressPick = false
    this._parkSpan = null
    this.environment = null
    this.terrain = null
    this.water = null
    this._waterBase = null
    this._coastWater = null
    this._waveAmp = 0.5
    this._raf = null
    this._lastFrame = null
    this._init()
  }

  _createRenderer() {
    const configs = [
      { antialias: true, logarithmicDepthBuffer: true, failIfMajorPerformanceCaveat: false },
      { antialias: true, failIfMajorPerformanceCaveat: false },
      { antialias: false, failIfMajorPerformanceCaveat: false, powerPreference: 'low-power' },
    ]
    let lastErr = null
    for (const cfg of configs) {
      try {
        const r = new THREE.WebGLRenderer(cfg)
        return r
      } catch (e) {
        lastErr = e
        console.warn('[twin] WebGLRenderer 创建失败（配置:', JSON.stringify(cfg), '）：', e)
      }
    }
    throw lastErr || new Error('无法创建 WebGL 渲染器')
  }

  // 渲染分辨率自适应：
  // - 常规屏幕/窗口用满 devicePixelRatio（上限 2），Retina 等高分屏按物理像素 1:1 渲染，
  //   画面锐利、无插值放大发虚；低 DPR 屏为 1，不额外消耗。
  // - 仅当渲染像素面积超过约 500 万（≈4K 全屏 ×DPR2 以上）时降级到 1.5，
  //   避免超大视口下显存/填充率爆炸。
  // - 带滞回（hysteresis）：同屏拖动窗口时像素面积会在 500 万阈值附近来回浮动，
  //   若每次都重算会让 pixel ratio 在 1.5 ↔ 2.0 之间反复跳变（canvas 物理尺寸突变、
  //   重建绘制缓冲），肉眼可见闪烁。因此同屏下仅当目标与当前档位差 ≥0.6（即档位
  //   真正变化）才切换；跨屏拖动（devicePixelRatio 变化）时立即跟随新档位。
  _pickPixelRatio() {
    const dpr = window.devicePixelRatio || 1
    const w = this.container.clientWidth || window.innerWidth
    const h = this.container.clientHeight || window.innerHeight
    const target = (w * h * dpr * dpr > 5e6) ? Math.min(dpr, 1.5) : Math.min(dpr, 2)
    // 跨屏拖动（DPR 变化）：直接采用新档位
    if (this._dpr !== dpr) return target
    // 同屏窗口拖动：档位差 < 0.6 时维持当前值，消除阈值边界抖动
    if (this._pr !== undefined && Math.abs(target - this._pr) < 0.6) return this._pr
    return target
  }

  _init() {
    const w = this.container.clientWidth || window.innerWidth
    const h = this.container.clientHeight || window.innerHeight
    this._cw = w
    this._ch = h
    this.scene = new THREE.Scene()
    this.scene.background = new THREE.Color(0xeef2f6)

    this.camera = new THREE.PerspectiveCamera(48, w / h, 1.0, 10000)
    this.camera.position.set(0, 460, 205)   // 厂区正前方，高位远距离俯瞰完整园区

    this.renderer = this._createRenderer()
    const pr = this._pickPixelRatio()
    this._pr = pr
    this._dpr = window.devicePixelRatio || 1
    this.renderer.setPixelRatio(pr)
    this.renderer.setSize(w, h)
    this.renderer.outputColorSpace = THREE.SRGBColorSpace
    // 工业摄影风 - 略压高光 + 强对比，使金属/墙面更具写实质感（参考图风格）
    this.renderer.toneMapping = THREE.ACESFilmicToneMapping
    this.renderer.toneMappingExposure = 0.95
    this.renderer.shadowMap.enabled = true
    // 柔和阴影：PCFSoftShadowMap 多采样，阴影边缘平滑无颗粒感（现代 GPU 开销可忽略）
    this.renderer.shadowMap.type = THREE.PCFSoftShadowMap
    this.container.appendChild(this.renderer.domElement)

    this.controls = new OrbitControls(this.camera, this.renderer.domElement)
    this.controls.enableDamping = true
    this.controls.dampingFactor = 0.08
    this.controls.target.set(0, 20, 0)
    // 交互状态标记：拖拽旋转/缩放时全帧率渲染（画面流畅锐利），静止时降帧省电
    this._interacting = false
    this.controls.addEventListener('start', () => { this._interacting = true })
    this.controls.addEventListener('end', () => { this._interacting = false })
    // 灯光：建好并保存引用，颜色/强度在 setEnvironment 中按场景（虚空暗色 / 其他亮色）动态切换
    this._initLights()

    this._initGround()
    this.setEnvironment(this.envMode || 'city')

    this.root = new THREE.Group()
    this.scene.add(this.root)

    this._animate = this._animate.bind(this)
    this._raf = requestAnimationFrame(this._animate)
    // window resize 同样走 RAF 节流：拖动窗口时 resize 事件高频触发，避免
    // 每事件直接调用 resize() 造成重复 setSize/setPixelRatio 而闪烁
    this._onWinResize = () => {
      if (this._resizeRaf) return
      this._resizeRaf = requestAnimationFrame(() => { this._resizeRaf = null; this.resize() })
    }
    window.addEventListener('resize', this._onWinResize)
    this.renderer.domElement.addEventListener('click', (e) => this._onPick(e))
    this.renderer.domElement.addEventListener('dblclick', (e) => this._onDblPick(e))
  }

  // 建立全部灯光并保存引用（颜色/强度在 _applyThemeColors 中按场景切换）
  _initLights() {
    this._ambient = new THREE.AmbientLight(0xffffff, 0.55)
    this.scene.add(this._ambient)

    this._hemi = new THREE.HemisphereLight(0xffffff, 0xdde5ed, 0.55)
    this.scene.add(this._hemi)

    this._keySE = new THREE.DirectionalLight(0xffffff, 1.1)
    this._keySE.position.set(140, 180, 100)
    this._keySE.castShadow = true
    // 低端机优化：阴影贴图 2048→1024，显存占用与阴影渲染带宽减少 4 倍
    this._keySE.shadow.mapSize.set(1024, 1024)
    this._keySE.shadow.camera.near = 5
    this._keySE.shadow.camera.far = 900
    this._keySE.shadow.camera.left = -360
    this._keySE.shadow.camera.right = 360
    this._keySE.shadow.camera.top = 320
    this._keySE.shadow.camera.bottom = -280
    this._keySE.shadow.camera.updateProjectionMatrix()
    this._keySE.shadow.bias = -0.0004
    this._keySE.shadow.normalBias = 0.03
    this.scene.add(this._keySE)

    this._keySW = new THREE.DirectionalLight(0xf5f7fa, 0.55)
    this._keySW.position.set(-120, 120, -80)
    this._keySW.castShadow = false
    this.scene.add(this._keySW)

    this._fillN = new THREE.DirectionalLight(0xffffff, 0.35)
    this._fillN.position.set(40, 80, -120)
    this.scene.add(this._fillN)

    // 虚空赛博朋克霓虹点光（五色：蓝/青/靛蓝/亮青 + 品红/橙，仅虚空场景启用）
    this._neon = []
    const neonDefs = [
      { c: 0x2a7bff, p: [-260, 165, 100], r: 1400 },   // 蓝
      { c: 0x18d0ff, p: [260, 125, -130], r: 1400 },   // 青
      { c: 0x3a6bff, p: [80, 185, -200], r: 1400 },    // 靛蓝
      { c: 0x45e6ff, p: [-90, 145, 210], r: 1400 },    // 亮青
      { c: 0xe030f0, p: [-180, 130, -180], r: 1200 },  // 品红（新增）
      { c: 0xff6600, p: [200, 160, 150], r: 1200 },     // 橙（新增——工业熔融感）
    ]
    for (const d of neonDefs) {
      const l = new THREE.PointLight(d.c, 0.0, d.r, 2)
      l.position.set(d.p[0], d.p[1], d.p[2])
      l.visible = false
      this.scene.add(l)
      this._neon.push(l)
    }
  }

  setPaused(v) {
    if (this._paused === v) return
    this._paused = v
    if (!v) {
      this._lastFrame = null
      if (!this._raf) this._raf = requestAnimationFrame(this._animate)
    }
  }

  _onPick(ev) { this._pickAt(ev, false) }
  _onDblPick(ev) { this._pickAt(ev, true) }

  _pickAt(ev, isDbl) {
    if (this._suppressPick) { this._suppressPick = false; return }  // 设施拖拽结束，吞掉误触发的拾取
    const rect = this.renderer.domElement.getBoundingClientRect()
    const mx = ((ev.clientX - rect.left) / rect.width) * 2 - 1
    const my = -((ev.clientY - rect.top) / rect.height) * 2 + 1
    this._ray.setFromCamera({ x: mx, y: my }, this.camera)
    // 先解析命中对象上的「可点击标识」：标签（工序/连接）优先于几何体
    const hits = this._ray.intersectObjects(this.root.children, true)
    for (const h of hits) {
      let o = h.object
      while (o) {
        const ud = o.userData
        if (ud && ud.kind === 'unit') {
          // 顶层模式：组内单元单击 → 聚焦小组（相机+选中）；双击 → 进入小组子场景。
          // 组场景模式：小组内成员已展开，点击成员直接查看该工序。
          if (!this.groupScene && ud.groupId) {
            if (isDbl) { this.onSelectGroup && this.onSelectGroup(ud.groupId); return }
            if (this.onFocusGroup) { this.onFocusGroup(ud.groupId); return }
            if (this.onSelectGroup) { this.onSelectGroup(ud.groupId); return }   // 宿主未绑聚焦回调时退回进入小组
            return
          }
          // 点击工序铭牌 → 弹出该工艺数据（附上铭牌屏幕坐标，供前端弹窗定位）
          const pos = h.object && h.object.isSprite ? this._spriteScreenPos(h.object) : null
          this.onSelectUnit && this.onSelectUnit(ud.unitId, pos); return
        }
        if (ud && ud.kind === 'flow') { this.onSelectFlow && this.onSelectFlow(ud.flowId); return }        // 点击连接标签 → 聚焦连接
        if (ud && ud.deviceId) { this.onSelectDevice && this.onSelectDevice(ud.deviceId); return }          // 设备本体仍可点击
        // 工艺本体不再触发聚焦（已由标签承担），其余无标识的构件直接忽略
        o = o.parent
      }
    }
    // 未命中任何可点击对象（点击空白/地面）：通知前端（如关闭数据弹窗）
    if (this.onMiss) this.onMiss()
  }

  // 把标签精灵的世界坐标投影到画布像素坐标，供前端数据弹窗定位
  _spriteScreenPos(spr) {
    const v = new THREE.Vector3()
    spr.getWorldPosition(v)
    v.project(this.camera)
    if (v.z > 1 || v.z < -1) return null
    const rect = this.renderer.domElement.getBoundingClientRect()
    return {
      x: (v.x * 0.5 + 0.5) * rect.width,
      y: (-v.y * 0.5 + 0.5) * rect.height,
    }
  }

  // 地表高度场：沙丘起伏（正弦叠加），供地形置换使用
  // 工业场景完全平坦（干净严谨的厂区地坪），其余模式保留自然起伏
  _groundHeight(x, z, mode) {
    if (mode === 'industrial') return -0.2
    const d = Math.hypot(x, z)
    const flatR = 1500
    if (d <= flatR) return -0.2
    const t = Math.min(1, (d - flatR) / 2600)
    const ramp = t * t
    const dune = Math.sin(x * 0.0011 + 0.6) * Math.cos(z * 0.0013 - 0.4) * 0.5
      + Math.sin((x - z) * 0.0009 + 1.2) * 0.5
    return -0.2 + ramp * (6 + 26 * (0.5 + 0.5 * dune))
  }

  _initGround() {
    const HALF = this._computeLayoutBounds()
    this._buildPlatform(HALF.hx, HALF.hz)
  }

  // 根据当前工艺布局计算所需平台半尺寸（含底座外扩 + 呼吸空间）
  // 自动布局后以实际工艺位置为准，让圆角地坪紧贴工艺外轮廓，视觉上更开阔舒展。
  _computeLayoutBounds() {
    const us = this._unitWorld
    if (!us || !us.length) {
      const ext = 1.55
      return { hx: PARK.halfX * ext, hz: PARK.halfZ * ext }
    }
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity
    for (const u of us) {
      minX = Math.min(minX, u.x); maxX = Math.max(maxX, u.x)
      minZ = Math.min(minZ, u.z); maxZ = Math.max(maxZ, u.z)
    }
    // 底座 BoxGeometry(28) × 最大缩放 5.0 → 半宽 70；额外加 50 呼吸空间。
    // 小组子场景：成员放大 GROUP_SCENE_GAIN 倍但底座缩小（半宽 8），平台保持紧凑（呼吸空间减半）
    const pad = this.groupScene ? (16 * 5 * GROUP_SCENE_GAIN) / 2 + 25 : 70 + 50
    const hx = Math.max(Math.abs(minX), Math.abs(maxX)) + pad
    const hz = Math.max(Math.abs(minZ), Math.abs(maxZ)) + pad
    // 兜底最小值（避免工艺太少时平台过小；组场景平台更小更紧凑）
    const minHx = this.groupScene ? 90 : 180, minHz = this.groupScene ? 80 : 150
    return { hx: Math.max(hx, minHx), hz: Math.max(hz, minHz) }
  }

  // 按给定半尺寸重建整个平台（销毁旧几何并新建圆角矩形 + 网格线）
  _buildPlatform(halfX, halfZ) {
    // 先销毁旧平台
    if (this.platformGroup) {
      this._disposeTree(this.platformGroup)
      this.scene.remove(this.platformGroup)
      this.platformGroup = null
    }
    // 重置虚空灯塔/反重力光束动画引用（旧材质已随平台 dispose）
    this._voidLampBeacons = []
    this._voidLampLights = []
    this._voidBeams = []
    this._platformHalfX = halfX
    this._platformHalfZ = halfZ

    const g = new THREE.Group()
    const pw = halfX * 2, pd = halfZ * 2
    const cornerR = Math.min(halfX, halfZ) * 0.35

    // 圆角矩形截面 → ExtrudeGeometry 挤出厚度
    const shape = new THREE.Shape()
    const r = cornerR
    shape.moveTo(-halfX + r, -halfZ)
    shape.lineTo(halfX - r, -halfZ)
    shape.quadraticCurveTo(halfX, -halfZ, halfX, -halfZ + r)
    shape.lineTo(halfX, halfZ - r)
    shape.quadraticCurveTo(halfX, halfZ, halfX - r, halfZ)
    shape.lineTo(-halfX + r, halfZ)
    shape.quadraticCurveTo(-halfX, halfZ, -halfX, halfZ - r)
    shape.lineTo(-halfX, -halfZ + r)
    shape.quadraticCurveTo(-halfX, -halfZ, -halfX + r, -halfZ)

    const industrial = this.envMode === 'industrial'
    const baseMat = new THREE.MeshStandardMaterial({
      color: industrial ? 0xffffff : 0xf4f7fa,
      roughness: industrial ? 0.92 : 0.85,
      metalness: 0,
      map: industrial ? _industrialTex() : null,
      emissive: 0x181818,
      emissiveIntensity: industrial ? 0.04 : 0.12
    })
    const baseGeo = new THREE.ExtrudeGeometry(shape, { steps: 1, depth: 8.0, bevelEnabled: false })
    baseGeo.rotateX(-Math.PI / 2)
    baseGeo.translate(0, -4.0, 0)
    const base = new THREE.Mesh(baseGeo, baseMat)
    base.position.y = -4.5
    base.receiveShadow = true
    // 虚空模式：去掉厚重的圆角矩形实体底座（8m 厚块观感像笨重"地面底座"），
    // 工艺设备直接悬浮于虚空，背景氛围由 _applyVoidStage 营造
    if (this.envMode !== 'void') {
      g.add(base)
      this.platformBaseMat = baseMat
    } else {
      this.platformBaseMat = null
      baseGeo.dispose()
      baseMat.dispose()
    }

    // 平台顶面安全警示线：沿圆角矩形内缘一圈浅蓝灰（VS Code 克制的界面边线）
    if (this.envMode !== 'void') {
      const lineW = Math.max(1.0, Math.min(halfX, halfZ) * 0.02)
      const ro = Math.max(0, cornerR - lineW * 0.5)
      const ri = Math.max(0, cornerR - lineW * 1.5)
      const outer = new THREE.Shape()
      outer.moveTo(-halfX + ro, -halfZ)
      outer.lineTo(halfX - ro, -halfZ)
      outer.quadraticCurveTo(halfX, -halfZ, halfX, -halfZ + ro)
      outer.lineTo(halfX, halfZ - ro)
      outer.quadraticCurveTo(halfX, halfZ, halfX - ro, halfZ)
      outer.lineTo(-halfX + ro, halfZ)
      outer.quadraticCurveTo(-halfX, halfZ, -halfX, halfZ - ro)
      outer.lineTo(-halfX, -halfZ + ro)
      outer.quadraticCurveTo(-halfX, -halfZ, -halfX + ro, -halfZ)
      const inner = new THREE.Path()
      inner.moveTo(-halfX + lineW, -halfZ + ri)
      inner.lineTo(-halfX + lineW, halfZ - ri)
      inner.quadraticCurveTo(-halfX + lineW, halfZ - lineW, -halfX + ri, halfZ - lineW)
      inner.lineTo(halfX - ri, halfZ - lineW)
      inner.quadraticCurveTo(halfX - lineW, halfZ - lineW, halfX - lineW, halfZ - ri)
      inner.lineTo(halfX - lineW, -halfZ + ri)
      inner.quadraticCurveTo(halfX - lineW, -halfZ + lineW, halfX - ri, -halfZ + lineW)
      inner.lineTo(-halfX + ri, -halfZ + lineW)
      inner.quadraticCurveTo(-halfX + lineW, -halfZ + lineW, -halfX + lineW, -halfZ + ri)
      outer.holes.push(inner)
      const safetyGeo = new THREE.ShapeGeometry(outer)
      const safetyMat = new THREE.MeshBasicMaterial({
        color: 0x9fb3c4,
        transparent: true,
        opacity: 0.55,
        depthWrite: false,
        polygonOffset: true,
        polygonOffsetFactor: -1
      })
      const safety = new THREE.Mesh(safetyGeo, safetyMat)
      safety.rotation.x = -Math.PI / 2
      safety.position.y = -0.42
      g.add(safety)
      this.platformEdgeMat = safetyMat
    } else {
      this.platformEdgeMat = null
    }

    // 淡灰参考网格（仅非虚空场景；虚空模式不铺任何地面网格/地坪，工艺设备直接悬浮）
    if (this.envMode !== 'void') {
      const gridStep = 40
      const gridMat = new THREE.MeshBasicMaterial({ color: 0xa9b6c2, transparent: true, opacity: 0.22, depthWrite: false })
      this.platformGridMat = gridMat
      for (let x = -pw / 2; x <= pw / 2; x += gridStep) {
        const line = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.03, pd), gridMat)
        line.position.set(x, -0.48, 0); g.add(line)
      }
      for (let z = -pd / 2; z <= pd / 2; z += gridStep) {
        const line = new THREE.Mesh(new THREE.BoxGeometry(pw, 0.03, 0.05), gridMat)
        line.position.set(0, -0.48, z); g.add(line)
      }
    }

    // 虚空模式：不铺任何地坪/纹理/网格，工艺设备直接悬浮于虚空

    this.platformSideGroup = null

    g.name = 'schematicPlatform'
    this.platformGroup = g
    this.scene.add(g)
  }


  // 竖直渐变天幕贴图（按环绕环境模式切换配色：天顶 -> 中景 -> 地平线）
  _makeSkyTex(stops) {
    const c = document.createElement('canvas')
    c.width = 16; c.height = 256
    const ctx = c.getContext('2d')
    const grad = ctx.createLinearGradient(0, 0, 0, 256)
    grad.addColorStop(0.0, stops[0])
    grad.addColorStop(0.5, stops[1])
    grad.addColorStop(1.0, stops[2])
    ctx.fillStyle = grad
    ctx.fillRect(0, 0, 16, 256)
    const tex = new THREE.CanvasTexture(c)
    tex.colorSpace = THREE.SRGBColorSpace
    return tex
  }

  // 核心孪生之外的「环绕景观」：与项目无关、可手动切换（森林/城市/沙漠/海岸），
  // 用 InstancedMesh 与程序化造型高密度低成本生成，经大气雾自然没入天幕，
  // 切换场景环境（虚空 / 沙漠 / 城市 / 海岸），拆除旧环境并重建
  setEnvironment(mode) {
    mode = mode || this.envMode || 'void'
    this._teardownEnvironment()
    const changed = (mode !== this.envMode)
    this.envMode = mode
    const cfg = ENV[mode] || ENV.void
    this._waveAmp = cfg.waveAmp || 0.5
    // 虚空场景拉远相机远裁剪面，容纳地平线霓虹太阳与远景粒子；其余场景保持紧凑远平面
    this.camera.far = (mode === 'void') ? 6000 : 10000
    this.camera.updateProjectionMatrix()
    // 环境切换时重建平台：虚空 = 工业地坪 + 主干道 + 四角灯塔；其他 = 干净浅色平台
    if (changed && this._platformHalfX && this._platformHalfZ) {
      this._buildPlatform(this._platformHalfX, this._platformHalfZ)
    }
    // 平台地坪 / 灯光 / 设备描边按场景配色（虚空暗色赛博朋克，其余干净浅色）
    this._applyThemeColors(mode)

    // 虚空模式：不建远郊地表/装饰，仅设置深空背景+暗雾+粒子场
    if (mode === 'void') {
      this._applyVoidStage()
      return
    }

    this.environment = new THREE.Group()
    this.environment.name = 'surround-environment'

    this._buildTerrain(mode)
    this._buildDeco(mode)
    this._applyAtmosphere(mode)
    this.scene.add(this.environment)
  }

  // 按场景切换平台地坪、灯光与设备描边配色：
  // 虚空 = 暗色赛博朋克（深空背景 + 霓虹网格 + 紫蓝点光 + 亮青描边）；
  // 其余场景 = 干净浅色（保证半透明设备与内部热量/管道可见）。
  _applyThemeColors(mode) {
    const dark = (mode === 'void')
    const pm = this.platformBaseMat, gm = this.platformGridMat
    if (dark) {
      // ===== 极致赛博朋克灯光：强对比冷暖双色 + 高动态范围 =====
      if (pm) { pm.color.set(0x0a1020); pm.roughness = 0.28; pm.metalness = 0.6; pm.emissive.set(0x0a1525); pm.emissiveIntensity = 0.55; pm.map = null; pm.needsUpdate = true }
      if (gm) { gm.color.set(0x00e5ff); gm.opacity = 0.45; gm.blending = THREE.AdditiveBlending; gm.needsUpdate = true }
      if (this.platformEdgeMat) { this.platformEdgeMat.color.set(0x00ffff); this.platformEdgeMat.opacity = 0.9 }
      // 设备/组合底座：暗色赛博底座
      if (this._pedestalMats) this._pedestalMats.forEach((m) => { if (m) { m.color.set(0x0a1020); m.roughness = 0.28; m.metalness = 0.6; m.map = null; m.needsUpdate = true } })
      if (this._pedestalEdgeMats) this._pedestalEdgeMats.forEach((m) => { if (m) { m.color.set(0x00ffff); m.opacity = 0.9 } })
      if (this._groupEdgeMats) this._groupEdgeMats.forEach((m) => { if (m) { m.color.set(0x00ffff); m.opacity = 0.9 } })
      // 环境光：深蓝（不是白光——赛博朋克世界没有自然日光）
      this._ambient.color.set(0x2040a0); this._ambient.intensity = 2.0
      // 半球光：天青 + 地深蓝
      this._hemi.color.set(0x0080e0); this._hemi.groundColor.set(0x040810); this._hemi.intensity = 1.3
      // 主方向光：冷钢蓝（从右上方投射，制造强烈明暗对比）
      this._keySE.color.set(0xa0c8ff); this._keySE.intensity = 4.2
      // 副方向光：淡品红补光（左侧，冷-暖对比）
      this._keySW.color.set(0xd0a0f0); this._keySW.intensity = 1.2
      // 补光：霓虹青（填充阴影区）
      this._fillN.color.set(0x00ccff); this._fillN.intensity = 1.4
      // 霓虹点光源（六色全开，更高强度）
      if (this._neon) {
        this._neon.forEach((l) => { l.visible = true })
        this._neon[0].intensity = 4.5   // 蓝（主）
        this._neon[1].intensity = 3.8   // 青
        this._neon[2].intensity = 4.0   // 靛蓝
        this._neon[3].intensity = 3.2   // 亮青
        if (this._neon[4]) this._neon[4].intensity = 2.8   // 品红
        if (this._neon[5]) this._neon[5].intensity = 2.4   // 橙
      }
      if (this._edgeMaterials) this._edgeMaterials.forEach((m) => { m.color.set(0x00ffff); m.opacity = 0.92 })
      if (!this._hasUserBrightness) this.renderer.toneMappingExposure = 1.65   // 高曝光让霓虹"爆"出来
    } else if (mode === 'industrial') {
      // ===== MATLAB 工业风：浅灰混凝土平台 + 细蓝描边 + 均匀明亮照明（与浅色系统 UI 协调） =====
      if (pm) {
        pm.color.set(0xffffff); pm.roughness = 0.92; pm.metalness = 0.05
        pm.map = _industrialTex()
        pm.emissive.set(0xe9edf2); pm.emissiveIntensity = 0.0
        pm.needsUpdate = true
      }
      if (gm) { gm.color.set(0xa9b6c2); gm.opacity = 0.22; gm.blending = THREE.NormalBlending; gm.needsUpdate = true }
      // 平台边缘安全警示线：浅蓝灰（VS Code 克制边线）
      if (this.platformEdgeMat) { this.platformEdgeMat.color.set(0x9fb3c4); this.platformEdgeMat.opacity = 0.55 }
      // 设备/组合底座：白底 + 浅灰工业地坪纹理（与厂区地面统一）
      if (this._pedestalMats) this._pedestalMats.forEach((m) => {
        if (!m) return
        m.color.set(0xffffff); m.roughness = 0.92; m.metalness = 0.12
        m.map = _industrialTex()
        m.emissive.set(0xe9edf2); m.emissiveIntensity = 0.0
        m.needsUpdate = true
      })
      // 底座顶面安全基准线：浅蓝灰
      if (this._pedestalEdgeMats) this._pedestalEdgeMats.forEach((m) => { if (m) { m.color.set(0x9fb3c4); m.opacity = 0.55 } })
      if (this._groupEdgeMats) this._groupEdgeMats.forEach((m) => { if (m) { m.color.set(0x9fb3c4); m.opacity = 0.55 } })
      // 环境光：明亮冷白（均匀照明，保证设备清晰）
      this._ambient.color.set(0xf4f7fa); this._ambient.intensity = 1.0
      // 半球光：冷白天 + 浅灰地面（浅色地反光，MATLAB 明亮制图感）
      this._hemi.color.set(0xe8f0f8); this._hemi.groundColor.set(0xe6eaee); this._hemi.intensity = 0.85
      // 主方向光：纯白（塑造结构与轮廓）
      this._keySE.color.set(0xffffff); this._keySE.intensity = 1.7
      // 副方向光：浅蓝白（冷色填充，塑造体积感）
      this._keySW.color.set(0xe0e9f2); this._keySW.intensity = 0.7
      // 补光：淡蓝（柔化阴影）
      this._fillN.color.set(0xd7e2ec); this._fillN.intensity = 0.55
      // 工业场景不启用霓虹点光（保持克制沉稳）
      if (this._neon) this._neon.forEach((l) => { l.visible = false })
      // 描边：信息蓝（与系统 UI 强调色一致）
      if (this._edgeMaterials) this._edgeMaterials.forEach((m) => { m.color.set(0x0072bd); m.opacity = 0.6 })
      if (!this._hasUserBrightness) this.renderer.toneMappingExposure = 1.0
    } else {
      if (pm) { pm.color.set(0xf0f3f7); pm.roughness = 0.85; pm.metalness = 0; pm.emissive.set(0x181818); pm.emissiveIntensity = 0.12; pm.map = null; pm.needsUpdate = true }
      if (gm) { gm.color.set(0xbbc8d4); gm.opacity = 0.25; gm.blending = THREE.NormalBlending; gm.needsUpdate = true }
      if (this.platformEdgeMat) { this.platformEdgeMat.color.set(0x9aaab8); this.platformEdgeMat.opacity = 0.45 }
      if (this._pedestalMats) this._pedestalMats.forEach((m) => { if (m) { m.color.set(0xf4f7fa); m.roughness = 0.9; m.metalness = 0; m.map = null; m.needsUpdate = true } })
      if (this._pedestalEdgeMats) this._pedestalEdgeMats.forEach((m) => { if (m) { m.color.set(0x9aaab8); m.opacity = 0.45 } })
      if (this._groupEdgeMats) this._groupEdgeMats.forEach((m) => { if (m) { m.color.set(0x9aaab8); m.opacity = 0.45 } })
      this._ambient.color.set(0xffffff); this._ambient.intensity = 0.75
      this._hemi.color.set(0xffffff); this._hemi.groundColor.set(0xe8edf4); this._hemi.intensity = 0.7
      this._keySE.color.set(0xffffff); this._keySE.intensity = 1.4
      this._keySW.color.set(0xf8fafc); this._keySW.intensity = 0.7
      this._fillN.color.set(0xffffff); this._fillN.intensity = 0.45
      if (this._neon) this._neon.forEach((l) => { l.visible = false })
      if (this._edgeMaterials) this._edgeMaterials.forEach((m) => { m.color.set(0x24323f); m.opacity = 0.65 })
      if (!this._hasUserBrightness) this.renderer.toneMappingExposure = 0.95
    }
  }

  // 虚空场景应用：近黑深空背景（纯净深邃、无星点）+ 半透明悬空地台
  _applyVoidStage() {
    const cfg = ENV.void
    // 深空近黑背景
    this.scene.background = new THREE.Color(0x02040a)
    // 不使用雾
    this.scene.fog = null
    // 清理残留星空（虚空场景不再展示星点背景）
    const stars = this.scene.getObjectByName('voidStars')
    if (stars) { this.scene.remove(stars); this._disposeTree(stars) }
    // 半透明地台已存在则跳过重建
    if (!this.scene.getObjectByName('voidGround')) {
      this.scene.add(this._makeVoidGround())
    }
  }

  // 半透明赛博地台：径向渐变贴图（中心较实、边缘淡出），悬浮于厂区下方，
  // 仅作地坪、不含任何圆环/网格/装饰，延续虚空场景"极简纯净"的调性
  _makeVoidGround() {
    const size = 512
    const c = document.createElement('canvas')
    c.width = c.height = size
    const ctx = c.getContext('2d')
    const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
    // 深蓝黑半透明，中心略实、向外淡出，营造悬空全息地台感
    g.addColorStop(0.0, 'rgba(22,44,78,0.55)')
    g.addColorStop(0.45, 'rgba(14,30,56,0.42)')
    g.addColorStop(0.80, 'rgba(9,20,40,0.20)')
    g.addColorStop(1.0, 'rgba(6,14,30,0.0)')
    ctx.fillStyle = g
    ctx.fillRect(0, 0, size, size)
    const tex = new THREE.CanvasTexture(c)
    tex.colorSpace = THREE.SRGBColorSpace

    const geo = new THREE.PlaneGeometry(2600, 2600)
    const mat = new THREE.MeshBasicMaterial({
      map: tex, transparent: true, opacity: 0.9,
      depthWrite: false, side: THREE.DoubleSide,
    })
    const mesh = new THREE.Mesh(geo, mat)
    mesh.rotation.x = -Math.PI / 2
    // 置于厂区下方（设备基座在 y≈0，地台略低以避免穿模）
    mesh.position.y = -1.5
    mesh.name = 'voidGround'
    return mesh
  }

  // 拆除上一次环绕环境（地表 + 装饰 + 水面），释放几何/材质/贴图
  _teardownEnvironment() {
    if (this.environment) {
      this._disposeTree(this.environment)
      this.scene.remove(this.environment)
      this.environment = null
    }
    if (this.terrain) {
      if (this.terrain.geometry) this.terrain.geometry.dispose()
      if (this.terrain.material) this.terrain.material.dispose()
      this.scene.remove(this.terrain)
      this.terrain = null
    }
    this.water = null
    this._waterBase = null
    this._coastWater = null
    // 兜底清理虚空星空（正常流程已不再生成，防止历史残留）
    const vs = this.scene.getObjectByName('voidStars')
    if (vs) { this.scene.remove(vs); this._disposeTree(vs) }
    // 清理虚空半透明地台
    const vg = this.scene.getObjectByName('voidGround')
    if (vg) { this.scene.remove(vg); this._disposeTree(vg) }
  }

  // 按模式重建远郊地表（置换大平面），颜色/起伏由 ENV 与 _groundHeight 控制
  _buildTerrain(mode) {
    const cfg = ENV[mode] || ENV.desert
    // 低端机优化：地形细分 200→128，顶点数从 40401 降至 16641，远郊低频起伏视觉无差别，显存占用减少约 60%
    const geo = new THREE.PlaneGeometry(8000, 8000, 128, 128)
    const pos = geo.attributes.position
    for (let i = 0; i < pos.count; i++) {
      const lx = pos.getX(i), ly = pos.getY(i)
      // 平面局部 (x,y) -> 世界 (x,-y)；局部 z 经旋转后成为世界高度 y
      pos.setZ(i, this._groundHeight(lx, -ly, mode))
    }
    geo.computeVertexNormals()
    // 按场景环境选择地表纹理
    let tex, roughness
    if (mode === 'desert') {
      tex = _desertTex().clone()
      roughness = 0.95
    } else if (mode === 'city') {
      tex = _cityTex().clone()
      roughness = 0.85
    } else if (mode === 'coast') {
      tex = _coastTex().clone()
      roughness = 0.88
    } else if (mode === 'industrial') {
      tex = _industrialTex().clone()
      roughness = 0.9
    } else {
      tex = _grassTex().clone()
      roughness = 0.92
    }
    tex.repeat.set(36, 36)
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping
    tex.colorSpace = THREE.SRGBColorSpace
    const terrainMat = new THREE.MeshStandardMaterial({
      map: tex,
      color: new THREE.Color(0xffffff),
      roughness,
      metalness: 0.0,
    })
    const terrain = new THREE.Mesh(geo, terrainMat)
    terrain.rotation.x = -Math.PI / 2
    terrain.receiveShadow = true
    this.terrain = terrain
    this.scene.add(terrain)
  }

  // 设置场景底色与大气雾（不同景观不同氛围）
  _applyAtmosphere(mode) {
    const cfg = ENV[mode] || ENV.desert
    this.scene.background = new THREE.Color(cfg.sky[2])
    if (cfg.fog) this.scene.fog = new THREE.Fog(cfg.fog.color, cfg.fog.near, cfg.fog.far)
    else this.scene.fog = null
  }

  // 构建各场景装饰元素（沙漠仙人掌/岩石、城市建筑群、海滩椰树水面）
  _buildDeco(mode) {
    if (!this.environment) return
    if (mode === 'desert') {
      this._makeDesertDeco()
    } else if (mode === 'city') {
      this._makeCityDeco()
    } else if (mode === 'coast') {
      this._makeCoastDeco()
    }
    // 工业场景：远景装饰已按要求全部移除（烟囱列/冷却塔/罐区/精馏塔/筒仓/龙门吊/管廊）
  }

  // —— 沙漠装饰：仙人掌 + 风化岩石 ——
  _makeDesertDeco() {
    const g = new THREE.Group(); g.name = 'desert-deco'
    const rng = (s, e) => s + Math.random() * (e - s)
    const avoidR = 400  // 厂区周围空地
    const cactusMat = new THREE.MeshStandardMaterial({ color: 0x4a6e3a, roughness: 0.85, metalness: 0 })
    const rockMat = new THREE.MeshStandardMaterial({ color: 0xb8a088, roughness: 0.95, metalness: 0.05 })
    // 仙人掌：圆柱 + 顶部小球
    for (let i = 0; i < 50; i++) {
      let x, z
      do { x = rng(-2200, 2200); z = rng(-2200, 2200) } while (Math.hypot(x, z) < avoidR)
      const h = rng(8, 22)
      const cactusGrp = new THREE.Group()
      cactusGrp.position.set(x, 0.1, z)
      // 主干
      const trunk = new THREE.Mesh(new THREE.CylinderGeometry(rng(0.8, 1.5), rng(1.0, 1.8), h, 6), cactusMat)
      trunk.position.y = h / 2; cactusGrp.add(trunk)
      // 分支
      if (Math.random() > 0.35) {
        const b1 = new THREE.Mesh(new THREE.CylinderGeometry(rng(0.4, 0.7), rng(0.5, 0.9), h * 0.45, 6), cactusMat)
        b1.position.y = h * 0.55; b1.position.x = 2; b1.rotation.z = 1.2; cactusGrp.add(b1)
      }
      g.add(cactusGrp)
    }
    // 风化岩石：球体变体
    for (let i = 0; i < 35; i++) {
      let x, z
      do { x = rng(-2500, 2500); z = rng(-2500, 2500) } while (Math.hypot(x, z) < avoidR)
      const sr = rng(2, 7)
      const rock = new THREE.Mesh(
        new THREE.SphereGeometry(sr, 5, 4), rockMat)
      rock.position.set(x, sr * 0.5, z)
      rock.scale.set(rng(0.6, 1.4), rng(0.3, 0.8), rng(0.6, 1.4))
      rock.rotation.set(rng(0, Math.PI), rng(0, Math.PI), 0)
      g.add(rock)
    }
    this.environment.add(g)
  }

  // —— 城市装饰：远景建筑群（高低不同的矩形塔楼）——
  _makeCityDeco() {
    const g = new THREE.Group(); g.name = 'city-deco'
    const rng = (s, e) => s + Math.random() * (e - s)
    const avoidR = 450
    const bMat = new THREE.MeshStandardMaterial({ color: 0xd0d7e0, roughness: 0.75, metalness: 0.15 })
    const bMatGlass = new THREE.MeshStandardMaterial({ color: 0xa0c8e0, roughness: 0.2, metalness: 0.7 })
    for (let i = 0; i < 60; i++) {
      let x, z
      do { x = rng(-2800, 2800); z = rng(-2800, 2800) } while (Math.hypot(x, z) < avoidR)
      const bw = rng(10, 30), bd = rng(10, 30), bh = rng(30, 120)
      const bld = new THREE.Group()
      bld.position.set(x, 0.1, z)
      // 主楼体（远景建筑不投射阴影，降低阴影渲染负载）
      const body = new THREE.Mesh(new THREE.BoxGeometry(bw, bh, bd), bMat)
      body.position.y = bh / 2; bld.add(body)
      // 窗户带（玻璃色横向条纹）
      const stripes = Math.floor(bh / rng(12, 20))
      for (let s = 0; s < stripes; s++) {
        const y = s * (bh / stripes) + bh / stripes / 2
        const win = new THREE.Mesh(new THREE.BoxGeometry(bw + 0.3, bh / stripes * 0.4, bd + 0.3), bMatGlass)
        win.position.y = y; bld.add(win)
      }
      g.add(bld)
    }
    this.environment.add(g)
  }

  // —— 海滩装饰：水面 + 椰子树 ——
  _makeCoastDeco() {
    const g = new THREE.Group(); g.name = 'coast-deco'
    const rng = (s, e) => s + Math.random() * (e - s)
    const avoidR = 420

    // —— 大面积海面（半透明蓝绿，带波光起伏）——
    // 低端机优化：细分 100→48，顶点数从 10201 降至 2401，每帧波动计算量减少 76%，视觉效果几乎无差别
    const waterGeo = new THREE.PlaneGeometry(7000, 7000, 48, 48)
    const waterMat = new THREE.MeshStandardMaterial({
      color: 0x3a8aaa, roughness: 0.15, metalness: 0.3,
      transparent: true, opacity: 0.7, side: THREE.DoubleSide, depthWrite: false,
    })
    const water = new THREE.Mesh(waterGeo, waterMat)
    water.rotation.x = -Math.PI / 2
    water.position.y = -3.5
    water.name = 'coast-water'
    water.receiveShadow = true
    g.add(water)
    // 保存水面引用用于波动动画
    this._coastWater = water

    // 椰子树：棕色弯曲树干 + 绿色圆盘叶冠
    const trunkMat = new THREE.MeshStandardMaterial({ color: 0x8b6914, roughness: 0.9, metalness: 0 })
    const leafMat = new THREE.MeshStandardMaterial({ color: 0x3a8030, roughness: 0.8, metalness: 0 })
    for (let i = 0; i < 25; i++) {
      let x, z
      do { x = rng(-2000, 2000); z = rng(-2000, 2000) } while (Math.hypot(x, z) < avoidR)
      const palm = new THREE.Group()
      palm.position.set(x, 0.1, z)
      // 弯曲树干（分段小圆柱模拟曲线）
      const segCount = 6, totalH = rng(14, 26)
      let prevY = 0, prevAngle = 0
      for (let s = 0; s < segCount; s++) {
        const segH = totalH / segCount
        const seg = new THREE.Mesh(new THREE.CylinderGeometry(0.5 + s * 0.05, 0.5 + (s + 1) * 0.05, segH, 6), trunkMat)
        seg.position.y = prevY + segH / 2
        const bend = s * 0.08
        seg.rotation.z = bend
        seg.position.x = Math.sin(bend) * segH * 0.3
        palm.add(seg)
        prevY += segH
        prevAngle = bend
      }
      // 叶冠：多层放射状圆盘
      const crownY = totalH + 1
      const crownGrp = new THREE.Group()
      crownGrp.position.y = crownY
      for (let l = 0; l < 5; l++) {
        const leaf = new THREE.Mesh(new THREE.ConeGeometry(rng(2, 4.5), rng(0.4, 0.8), 6), leafMat)
        leaf.rotation.z = Math.PI / 2
        leaf.rotation.y = (l / 5) * Math.PI * 2 + rng(-0.2, 0.2)
        leaf.position.x = Math.cos(leaf.rotation.y) * 1.2
        leaf.position.z = Math.sin(leaf.rotation.y) * 1.2
        crownGrp.add(leaf)
      }
      const crownCenter = new THREE.Mesh(new THREE.SphereGeometry(0.6, 5, 4), leafMat)
      crownGrp.add(crownCenter)
      palm.add(crownGrp)
      g.add(palm)
    }
    this.environment.add(g)
  }

  // ========== 烧结机：带式抽风烧结 + 点火炉 + 环冷机 ==========

  // ========== 球团：回转窑（核心）+ 链篦机 + 环冷机 + 造球盘 ==========

  // ========== 焦炉：炭化室电池组 + 熄焦塔 + 烟囱 ==========

  // ========== 模铸：浇注平台 + 钢锭模（发光钢水）+ 天车 ==========

  // ========== 加热炉：隧道式炉体 + 进/出料炽热辊道 ==========

  // ========== 铁水预处理：鱼雷罐脱硫站 ==========

  // ========== 工辅工艺（煤气发电/余热回收/CCS）：汽轮机 + 冷却塔 ==========


  _disposeTree(obj) {
    obj.traverse((o) => {
      // 共享单位几何体带 __shared 标记，全局复用，跳过释放
      if (o.geometry && !o.geometry.userData.__shared) o.geometry.dispose()
      if (o.material) {
        const mats = Array.isArray(o.material) ? o.material : [o.material]
        mats.forEach((m) => {
          if (m.userData && m.userData.__shared) return
          if (m.map && m.map !== _footTexCache) m.map.dispose()
          m.dispose()
        })
      }
    })
  }

  _disposeGroup(obj) {
    this._disposeTree(obj)
  }

  _enableShadow(obj) {
    obj.traverse((o) => { if (o.isMesh) o.castShadow = true })
  }

  // —— 示意模式：温度 → 颜色色阶（蓝→青→绿→黄→橙→红→白热）——
  _tempColor(tC) {
    const STOPS = [
      [40, [43, 108, 176]],
      [200, [44, 122, 123]],
      [500, [56, 161, 105]],
      [800, [214, 158, 46]],
      [1100, [221, 107, 32]],
      [1400, [229, 62, 62]],
      [1800, [245, 101, 101]],
      [2200, [253, 154, 154]],
    ]
    tC = Math.max(40, Math.min(2200, tC))
    for (let i = 0; i < STOPS.length - 1; i++) {
      const [a, ca] = STOPS[i], [b, cb] = STOPS[i + 1]
      if (tC <= b) {
        const k = (tC - a) / (b - a)
        return new THREE.Color(
          (ca[0] + (cb[0] - ca[0]) * k) / 255,
          (ca[1] + (cb[1] - ca[1]) * k) / 255,
          (ca[2] + (cb[2] - ca[2]) * k) / 255,
        )
      }
    }
    const last = STOPS[STOPS.length - 1][1]
    return new THREE.Color(last[0] / 255, last[1] / 255, last[2] / 255)
  }

  // 工程线框外壳：描边 + 调整 renderOrder 让内部热量分层优先绘制
  _schematicizeBody(body) {
    const lineMat = new THREE.LineBasicMaterial({ color: 0x24323f, transparent: true, opacity: 0.65 })
    if (!this._edgeMaterials) this._edgeMaterials = []
    this._edgeMaterials.push(lineMat)
    body.traverse((o) => {
      if (!o.isMesh) return
      o.renderOrder = 0
      try {
        const eg = new THREE.EdgesGeometry(o.geometry, 28)
        const lines = new THREE.LineSegments(eg, lineMat)
        o.add(lines)
      } catch (e) { /* 个别几何不支持边线，跳过 */ }
    })
  }

  // 容器类工序内部「温度分层」可视化（热态色柱约束于炉/罐内部）
  _addHeatLayers(body, unit, res) {
    const type = unit.type
    const meta = UNIT_META[type] || {}
    const isContainer = type === 'blast_furnace' || meta.shape === 'furnace' ||
      meta.shape === 'converter' || meta.shape === 'cylinder' || meta.shape === 'slab'
    if (!isContainer) return null

    // 热度柱中心Y偏移 + 高度 + 半径均由 builder 通过 userData 传入，确保不超出设备壳体
    const vesselCY = body.userData.heatCenterY != null ? body.userData.heatCenterY : 0
    const topY = body.userData.heatInternalH || (body.userData.topY || 16)
    const radius = body.userData.heatInternalR || this._heatRadius(type, meta.shape)
    const slices = 16
    const group = new THREE.Group()
    group.name = 'heat-layers'
    group.position.set(0, vesselCY - topY / 2, 0)

    // 内部热态色柱（随高度分层着色）
    const mats = []
    for (let i = 0; i < slices; i++) {
      const y0 = (i / slices) * topY
      const y1 = ((i + 1) / slices) * topY
      const h = (i + 0.5) / slices
      const tC = this._tempProfile(type, meta.shape, h, res)
      const col = this._tempColor(tC)
      const geo = new THREE.CylinderGeometry(radius, radius, (y1 - y0) * 0.94, 12, 1, true)
      const m = new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.5, side: THREE.DoubleSide, depthWrite: false })
      const mesh = new THREE.Mesh(geo, m)
      mesh.position.y = (y0 + y1) / 2
      mesh.renderOrder = 2
      group.add(mesh)
      mats.push({ mat: m })
    }
    body.add(group)

    // 侧旁温度标尺
    const legend = new THREE.Group()
    legend.name = 'heat-legend'
    legend.position.set(0, vesselCY - topY / 2, 0)
    const lx = radius + 2.4
    const lmats = []
    for (let i = 0; i < slices; i++) {
      const y0 = (i / slices) * topY, y1 = ((i + 1) / slices) * topY
      const h = (i + 0.5) / slices
      const tC = this._tempProfile(type, meta.shape, h, res)
      const m = new THREE.MeshBasicMaterial({ color: this._tempColor(tC), transparent: true, opacity: 0.92, side: THREE.DoubleSide })
      const bar = new THREE.Mesh(new THREE.BoxGeometry(1.0, (y1 - y0) * 0.96, 1.0), m)
      bar.position.set(lx, (y0 + y1) / 2, 0)
      bar.renderOrder = 2
      legend.add(bar)
      lmats.push(m)
    }
    body.add(legend)

    return {
      group, legend, mats, lmats,
      heat: (res && res.heat != null) ? res.heat : 0.6,
      tick(t) {
        const pulse = 0.9 + 0.1 * Math.sin(t * 3 + group.id)
        const baseOp = 0.5 * (0.7 + 0.3 * (this.heat || 0.6))
        for (const it of mats) it.mat.opacity = baseOp * pulse
      },
      update(nres) { if (nres && nres.heat != null) this.heat = nres.heat },
    }
  }

  _heatRadius(type, shape) {
    if (type === 'blast_furnace') return 2.6
    if (shape === 'converter') return 3.0
    if (shape === 'cylinder') return 3.0
    if (shape === 'slab') return 3.0
    return 3.4
  }

  // 温度剖面（℃）：按工序类型与归一化高度 h（0=底,1=顶）给出示意温度；
  // 若遥测提供端点 res.bottomTemp/res.topTemp，则以其覆盖剖面端点（预留后端真实数据接口）。
  _tempProfile(type, shape, h, res) {
    let tBot, tTop
    if (type === 'blast_furnace') { tBot = 2000; tTop = 200 }
    else if (type === 'caster' || shape === 'slab') { tBot = 1100; tTop = 1530 }
    else if (shape === 'converter') { tBot = 1550; tTop = 1620 }
    else if (shape === 'cylinder') { tBot = 1500; tTop = 1560 }
    else { tBot = 900; tTop = 1250 } // 通用熔炉/加热炉
    if (res && res.bottomTemp != null) tBot = res.bottomTemp
    if (res && res.topTemp != null) tTop = res.topTemp
    const k = Math.max(0, Math.min(1, h))
    if (type === 'blast_furnace') return tTop + (tBot - tTop) * Math.pow(1 - k, 1.4)
    return tBot + (tTop - tBot) * k
  }


  // ---------------- 构建模型 ----------------
  // opts.groupScene：3D 小组子场景模式 —— 仅渲染该小组成员（每个成员展开为独立工序模型），
  // 并绘制组内连线；顶层模式（缺省）则维持小组聚合为“一台大设备”的呈现。
  buildModel(model, results, opts = {}) {
    if (!model || !model.units) return
    this._clearModel()
    this._edgeMaterials = []   // 重置外壳描边材质列表（切换场景时按明暗重新着色）
    this.model = model
    this.results = results
    this.groupScene = opts.groupScene || null
    const isGS = !!this.groupScene
    // 组场景模式：仅渲染该小组成员；顶层模式渲染全部单元。
    // 顶层模式浅拷贝 units 后应用「工艺树自动布局」：主工艺为树干沿 X 从左到右（Z=0 居中），
    // 工辅为其分支分布在主干两侧、Z 全部 = 0（与主干同一水平线，无前后偏移，
    // 接入主工艺的管道即水平直线、路径最短）；仅影响 3D 渲染坐标，不污染 store/model 的原始数据。
    const viewUnits = isGS
      ? model.units.filter((u) => u.groupId === this.groupScene).map((u) => ({ ...u, groupId: null }))
      : model.units.map((u) => ({ ...u }))
    // 进入小组子场景：成员展开为独立模型，按网格均匀分布（互不重叠、排版整齐），
    // 不依赖工艺树布局（否则纯工辅小组会因无主工艺节点而直接 return，导致成员挤在原点）。
    if (isGS) this._layoutGroupGrid(viewUnits)
    else this._layoutProcessUnits(viewUnits, model.flows || [])
    const byId = {}
    viewUnits.forEach((u) => (byId[u.id] = u))

    this._unitWorld = viewUnits.map((u) => ({ x: u.x * SCALE, z: (u.z || 0) * SCALE }))

    const unitsRes = (results && results.units) || []
    const totalCo2 = unitsRes.reduce((s, u) => s + (u.co2_total || 0), 0) || 1
    const shareOf = (res) => (res ? (res.co2_total || 0) / totalCo2 : 0)

    // 小组元信息索引（compileSchemeToModel 输出的 groups: [{id, name}]）
    this._groupMeta = new Map()
    if (model.groups) for (const g of model.groups) this._groupMeta.set(g.id, { id: g.id, name: g.name || '设备小组' })

    // 独立单元逐个渲染；顶层模式下小组成员按组聚合为“一台大设备”呈现，
    // 组场景模式下成员全部展开为独立工序模型（进入小组子场景）
    const grouped = new Map()   // groupId -> Unit[]
    for (const u of viewUnits) {
      if (!isGS && u.groupId) {
        let arr = grouped.get(u.groupId)
        if (!arr) { arr = []; grouped.set(u.groupId, arr) }
        arr.push(u)
        continue
      }
      const res = (results && results.units && results.units.find((r) => r.id === u.id)) || null
      const grp = this._makeUnit(u, res, this._unitRole(u, model.flows), shareOf(res))
      this.unitGroups.set(u.id, grp)
      this.root.add(grp.group)
    }
    for (const [gid, members] of grouped) {
      const reses = members.map((u) => (results && results.units && results.units.find((r) => r.id === u.id)) || null)
      const grp = this._makeGroupModel(gid, members, reses, shareOf)
      this.groupModels.set(gid, grp)
      for (const u of members) this.unitGroups.set(u.id, grp)
      this.root.add(grp.group)
    }
    this._makeFlows(model.flows, byId)
    // 主流程地面导向线（仅顶层厂区场景）：强化“原料→炼铁→炼钢→连铸→轧钢”的生产主线走向
    if (!isGS) this._addMainFlowGuide()

    // 按实际工艺布局自动调整地坪尺寸（圆角平台紧贴工艺外轮廓）
    const bounds = this._computeLayoutBounds()
    if (Math.abs(bounds.hx - (this._platformHalfX || 0)) > 1 || Math.abs(bounds.hz - (this._platformHalfZ || 0)) > 1) {
      this._buildPlatform(bounds.hx, bounds.hz)
      this._applyThemeColors(this.envMode)
    }

    if (!this._firstFramed) {
      this._firstFramed = true
      this.resetView()
    }
  }

  /** 工艺自动布局（仅顶层模式）：按「工艺树」结构排版 —— 先左后右、工艺为树干。
   *  主工艺（炼铁/炼钢主流程）按物料流向沿 X 轴从左到右排成一条树干主线（Z=0 居中）；
   *  工辅工艺（鼓风/热风/制氧/水泵等，route==='aux'）成为树干的分支，分布在主干工艺的
   *  左右两侧：每个主工艺的一级子树（如 热风炉→鼓风机、喷吹）按子树大小贪心平衡分配左右，
   *  子树内部沿该方向逐级水平展开、子节点紧邻父节点（接入路径最短）。
   *  所有工艺节点处于同一水平线（Z 全部 = 0，无前后偏移），符合「每个工艺的入口在同一高度、
   *  水平 360° 均可接入」——工辅→主工艺的管道即水平直线，不产生多余路径。
   *  同一小组(groupId)的设备合并为一个布局节点参与排序。
   *  就地修改传入 units 的 x/z（调用方已浅拷贝，不影响 model 原始数据）。
   */
  _layoutProcessUnits(units, flows) {
    if (!Array.isArray(units) || !units.length) return
    const isMainU = (u) => u.route !== 'aux' && u.route !== 'util'
    const isAuxU = (u) => u.route === 'aux'
    // —— 主工艺典型先后顺序（钢铁长/短流程，用于拓扑排序同层/孤立节点微调）——
    const TYPE_PRIORITY = {
      sinter_plant: 1, pelletizing: 2, coke_oven: 3,
      blast_furnace: 10, hydrogen_bf: 10, h2_dri: 10, dri_midrex: 11, smelting_reduction: 12, biochar_injection: 13,
      hot_metal_pretreat: 20,
      bof: 30, eaf: 31,
      ladle_furnace: 40, aod: 41, vd_vacuum: 42, rh_vacuum: 43,
      caster: 50, ingot_casting: 51,
      reheating_furnace: 60, rolling_mill: 61, cold_rolling: 62
    }
    const prioOfType = (t) => (TYPE_PRIORITY[t] != null ? TYPE_PRIORITY[t] : 999)
    // —— 工辅默认服务的主工艺（无连线时的兜底绑定；有连线时以实际连线为准）——
    const TYPE_TARGET = {
      blower: 'blast_furnace', hot_blast_stove: 'blast_furnace', injector: 'blast_furnace',
      combustion_blower: 'blast_furnace', id_fan: 'sinter_plant',
      drive_supply: 'bof', electrode_reg: 'eaf',
      belt_conv: 'sinter_plant', feeder: 'sinter_plant', cool_pump: 'caster',
      aux_boiler: 'reheating_furnace', oxy_plant: 'bof'
    }

    // 1) 布局节点：独立单元 = 单节点；同组(groupId)单元 = 组节点（顶层聚合为一台大设备）
    const nodes = []
    const unitNode = new Map()
    const gmap = new Map()
    for (const u of units) {
      if (u.groupId) {
        let n = gmap.get(u.groupId)
        if (!n) { n = { id: 'g:' + u.groupId, groupId: u.groupId, members: [] }; gmap.set(u.groupId, n) }
        n.members.push(u)
      } else {
        const n = { id: u.id, unit: u }
        nodes.push(n)
        unitNode.set(u.id, n)
      }
    }
    for (const n of gmap.values()) { nodes.push(n); for (const m of n.members) unitNode.set(m.id, n) }

    const nodeIsMain = (n) => (n.members ? n.members.some(isMainU) : isMainU(n.unit))
    const nodeType = (n) => {
      if (n.members) {
        const ms = n.members.filter(isMainU).sort((a, b) => prioOfType(a.type) - prioOfType(b.type))
        return (ms.length ? ms[0] : n.members[0]).type
      }
      return n.unit.type
    }
    const nodePrio = (n) => prioOfType(nodeType(n))
    const mainNodes = nodes.filter(nodeIsMain)
    if (!mainNodes.length) return

    // 2) 主节点拓扑排序（只统计主节点之间的物料连接）
    const nodeById = new Map(nodes.map((n) => [n.id, n]))
    const indeg = new Map(), outg = new Map()
    for (const n of mainNodes) { indeg.set(n.id, 0); outg.set(n.id, []) }
    const mainSet = new Set(mainNodes.map((n) => n.id))
    for (const f of flows || []) {
      const a = unitNode.get(f.from_unit), b = unitNode.get(f.to_unit)
      if (!a || !b || a.id === b.id) continue
      if (!mainSet.has(a.id) || !mainSet.has(b.id)) continue
      outg.get(a.id).push(b.id)
      indeg.set(b.id, indeg.get(b.id) + 1)
    }
    const order = []
    const queue = mainNodes.filter((n) => !indeg.get(n.id)).sort((x, y) => nodePrio(x) - nodePrio(y))
    while (queue.length) {
      const n = queue.shift()
      order.push(n.id)
      for (const d of outg.get(n.id)) {
        indeg.set(d, indeg.get(d) - 1)
        if (indeg.get(d) === 0) {
          const dn = nodeById.get(d)
          let i = 0
          while (i < queue.length && nodePrio(queue[i]) <= nodePrio(dn)) i++
          queue.splice(i, 0, dn)
        }
      }
    }
    for (const n of mainNodes) if (!order.includes(n.id)) order.push(n.id)

    // 3) 构建「工艺树」：主工艺为树干，工辅经物料连线成为其分支；工辅还可再挂工辅
    //    （如 鼓风机→热风炉→高炉：高炉为树干、热风炉为一级分支、鼓风机为二级分支）。
    //    parentOf/childrenOf 由实际连线推导，无连线时以类型兜底、再以最近主工艺兜底。
    const auxNodes = nodes.filter((n) => !nodeIsMain(n))
    const auxSet = new Set(auxNodes.map((n) => n.id))
    const mainById = new Map(mainNodes.map((n) => [n.id, n]))
    const parentOf = new Map()
    const childrenOf = new Map()
    if (auxNodes.length) {
      // 工辅主输出物料（如鼓风机→blast_air、热风炉→hot_blast）：连线优先权依据
      const mainOutOf = (n) => { const t = PROCESS_MAP[nodeType(n)]; return t ? t.mainOut : null }
      for (const n of auxNodes) {
        // 3.1 实际连线投票：工辅的输出物料供给哪个工序节点（主工艺或另一工辅），
        //     就挂到哪个节点下；优先主输出物料的连线（避免余量外送连线干扰链式归属）
        const want = mainOutOf(n)
        let target = null, best = 0
        const votes = new Map()
        for (const f of flows || []) {
          const fromAux = n.members ? n.members.some((m) => m.id === f.from_unit) : n.id === f.from_unit
          const toAux = n.members ? n.members.some((m) => m.id === f.to_unit) : n.id === f.to_unit
          if (!fromAux && !toAux) continue
          const other = unitNode.get(fromAux ? f.to_unit : f.from_unit)
          if (!other || other.id === n.id) continue
          if (!(mainById.has(other.id) || auxSet.has(other.id))) continue
          const weight = want && f.material && f.material === want ? 10 : 1
          votes.set(other.id, (votes.get(other.id) || 0) + weight)
        }
        for (const [id, c] of votes) if (c > best) { best = c; target = nodeById.get(id) }
        // 3.2 类型兜底（如鼓风机 → 高炉）
        if (!target) {
          const wantT = TYPE_TARGET[nodeType(n)]
          if (wantT) target = mainNodes.find((m) => nodeType(m) === wantT || (m.members && m.members.some((u) => u.type === wantT))) || null
        }
        // 3.3 原始位置最近的相邻主工艺
        if (!target) {
          let near = null, nd = Infinity
          const ox = n.members ? n.members[0].x : n.unit.x
          const oz = n.members ? (n.members[0].z || 0) : (n.unit.z || 0)
          for (const m of mainNodes) {
            const mx = m.members ? m.members[0].x : m.unit.x
            const mz = m.members ? (m.members[0].z || 0) : (m.unit.z || 0)
            const d = (mx - ox) ** 2 + (mz - oz) ** 2
            if (d < nd) { nd = d; near = m }
          }
          target = near
        }
        if (!target) continue
        parentOf.set(n.id, target.id)
        if (!childrenOf.has(target.id)) childrenOf.set(target.id, [])
        childrenOf.get(target.id).push(n)
      }
    }
    // 3.4 子树信息：每个主工艺的一级子树（大小=节点总数、层数=根起最大深度）。
    //     子树是「工辅→主工艺」接入的最短链路单位（如 热风炉→鼓风机、喷吹）。
    const subtreeInfo = new Map()
    const subRootsOf = new Map()
    for (const m of mainNodes) {
      const roots = childrenOf.get(m.id) || []
      subRootsOf.set(m.id, roots)
      for (const r of roots) {
        let size = 0, maxD = 0
        const qq = [{ id: r.id, d: 1 }]
        while (qq.length) {
          const { id, d } = qq.shift()
          size++; if (d > maxD) maxD = d
          for (const c of childrenOf.get(id) || []) qq.push({ id: c.id, d: d + 1 })
        }
        subtreeInfo.set(r.id, { size, depth: maxD })
      }
    }
    // 3.5 左右平衡分配：一级子树按大小降序，贪心放到「累计槽位少」的一侧
    //     （两侧总宽尽量均衡），形成「辅助工艺在主干工艺的两侧」。
    const sidesOf = new Map()
    const spanOf = new Map()
    for (const m of mainNodes) {
      const roots = subRootsOf.get(m.id) || []
      const items = roots.map((r) => ({ id: r.id, size: subtreeInfo.get(r.id).size }))
      items.sort((a, b) => b.size - a.size)
      const sides = { '-1': [], '1': [] }
      let ls = 0, rs = 0
      for (const it of items) {
        if (ls <= rs) { sides['-1'].push(it.id); ls += it.size }
        else { sides['1'].push(it.id); rs += it.size }
      }
      sidesOf.set(m.id, sides)
      spanOf.set(m.id, { left: ls, right: rs })
    }

    // 4) 主节点沿 X 轴排布（原料在左、成品在右），Z=0 居中；相邻主干间距 =
    //    净距 + 前一主工艺分支水平铺开宽 + 后一主工艺分支水平铺开宽，保证分支不被相邻主干遮挡。
    const nMain = order.length
    const BSTEP = 160, HW = 80, MARGIN = 40
    const mainX = new Map()
    let cursor = HW
    order.forEach((id, i) => {
      if (i > 0) {
        const prev = order[i - 1]
        cursor += (spanOf.get(prev)?.right || 0) * BSTEP + (spanOf.get(id)?.left || 0) * BSTEP + MARGIN + 2 * HW
      }
      mainX.set(id, cursor)
    })
    // 整体居中：以全部主工艺左右两侧分支外沿的包围盒取中
    let lmin = Infinity, rmax = -Infinity
    order.forEach((id) => {
      const lx = mainX.get(id) - (spanOf.get(id)?.left || 0) * BSTEP - HW
      const rx = mainX.get(id) + (spanOf.get(id)?.right || 0) * BSTEP + HW
      if (lx < lmin) lmin = lx
      if (rx > rmax) rmax = rx
    })
    const shift = -(lmin + rmax) / 2
    order.forEach((id) => mainX.set(id, mainX.get(id) + shift))

    // 5) 落位：独立主节点直接放主线；主组内主工艺成员沿 Z 并列、辅成员置于两侧。
    const Z_STEP = 175, MEMBER_Z = 64
    for (const n of mainNodes) {
      const x = mainX.get(n.id)
      if (!n.members) { n.unit.x = x; n.unit.z = 0; continue }
      const ms = n.members.filter(isMainU)
      const as = n.members.filter(isAuxU)
      ms.forEach((u, i) => { u.x = x; u.z = (i - (ms.length - 1) / 2) * MEMBER_Z })
      as.forEach((u, i) => { const s = i % 2 === 0 ? 1 : -1; const r = Math.floor(i / 2); u.x = x; u.z = s * (Z_STEP + r * Z_STEP) })
    }

    // 6) 工辅/全辅组按「工艺树」落位（树状结构）：工辅分布在主干工艺「垂直方向（前/后，即 Z 轴）两侧」、
    //    Y 保持同一水平高度（不悬空）——形成树干沿 X 水平铺开、枝丫向前后（Z）张开的树状；
    //    一级子树分配到前/后两侧，子树内部按「树深度 d」分层：第 d 层节点 z = 主工艺 z + 方向×(d+1)×ZSTEP，
    //    根节点紧贴主干正前/正后，同层兄弟沿 X 水平并排（sideH），子节点相对父节点向该侧递进一层。
    const ZSTEP = 150            // 垂直（Z，前后）分层步距：树的每一层深度
    const COLSTEP3 = 150         // 同层兄弟/子树沿 X 水平铺开步距
    for (const m of mainNodes) {
      const px = mainX.get(m.id)
      const sides = sidesOf.get(m.id)
      for (const dirKey of ['-1', '1']) {
        const sideV = dirKey === '-1' ? -1 : 1   // 垂直方向：前(-1, 朝观察者)/后(+1)
        const sideH = sideV                       // 同侧水平外扩方向：前侧向左(-1)、后侧向右(+1)
        let colCursor = 0
        for (const rootId of sides[dirKey]) {
          // BFS 收集各深度层节点
          const levelNodes = new Map()
          let maxW = 0
          const qq = [{ id: rootId, d: 0 }]
          while (qq.length) {
            const { id, d } = qq.shift()
            if (!levelNodes.has(d)) levelNodes.set(d, [])
            levelNodes.get(d).push(id)
            if (levelNodes.get(d).length > maxW) maxW = levelNodes.get(d).length
            for (const ch of childrenOf.get(id) || []) qq.push({ id: ch.id, d: d + 1 })
          }
          for (const [d, ids] of levelNodes) {
            ids.forEach((id, idx) => {
              const cz = sideV * (d + 1) * ZSTEP
              // 根节点(d=0)紧贴主干正前/正后；不同根子树沿该侧水平方向错开（colCursor 留一列间隔），
              // 更深层同层兄弟同样沿 X 铺开 —— 保证同一侧多个根/兄弟互不重叠
              const cx = px + sideH * (colCursor + idx) * COLSTEP3
              const c = nodeById.get(id)
              if (c.members) {
                // 全辅组：组中心位于分支落位点（Z=cz，水平沿 X 错开），成员在 X-Z 平面网格展开
                const cols = Math.max(1, Math.ceil(Math.sqrt(c.members.length)))
                const rows = Math.max(1, Math.ceil(c.members.length / cols))
                c.members.forEach((u, i) => {
                  const col = i % cols
                  const row = Math.floor(i / cols)
                  u.x = cx + (col - (cols - 1) / 2) * 95
                  u.z = cz + (row - (rows - 1) / 2) * 110
                })
              } else {
                c.unit.x = cx
                c.unit.z = cz
              }
            })
          }
          colCursor += maxW + 1   // 不同子树在水平方向留一列间隔
        }
      }
    }

    // 7) 记录主流程从左到右的顺序，供地面导向线绘制（强化原料→炼铁→炼钢→连铸→轧钢的线路感）
    //    同时携带节点名称：小组取组名、独立单元取工艺名，用于流程节点名牌
    this._mainSeq = order.map((id) => {
      const n = nodeById.get(id)
      let name = '工序'
      if (n && n.members) {
        const gMeta = this._groupMeta ? this._groupMeta.get(n.groupId) : null
        name = (gMeta && gMeta.name) || (n.members[0] && UNIT_META[n.members[0].type] ? UNIT_META[n.members[0].type].label : '')
      } else if (n && n.unit) {
        name = (UNIT_META[n.unit.type] && UNIT_META[n.unit.type].label) || n.unit.name || ''
      }
      return { id, x: mainX.get(id) || 0, name: String(name || '工序') }
    })
  }

  // 进入小组子场景的成员网格布局：所有成员（主/辅）展开为独立模型，
  // 按方阵网格均匀分布、互不重叠，并居中于原点，供 _makeUnit 与 _makeFlows 使用。
  _layoutGroupGrid(units) {
    if (!Array.isArray(units) || !units.length) return
    const n = units.length
    const cols = Math.max(1, Math.ceil(Math.sqrt(n)))
    const rows = Math.max(1, Math.ceil(n / cols))
    const XS = 120  // 列间距
    const ZS = 110  // 行间距
    units.forEach((u, i) => {
      const col = i % cols
      const row = Math.floor(i / cols)
      u.x = (col - (cols - 1) / 2) * XS
      u.z = (row - (rows - 1) / 2) * ZS
    })
  }

  // 主流程地面导向线：沿主工艺中心线在地坪上方绘制一条发光“钢带”，
  // 并标注流向箭头，让领导/客户一眼看清整条生产主线与走向。
  // 采用“宽底+亮芯+高亮箭头”三层结构，确保在浅色/深色地坪上都清晰可见。
  _addMainFlowGuide() {
    if (this._guideGroup) {
      this._disposeTree(this._guideGroup)
      this.root.remove(this._guideGroup)
      this._guideGroup = null
    }
    const seq = this._mainSeq
    if (!seq || seq.length < 2) return
    const y = 3.2
    const pts = seq.map((p) => new THREE.Vector3(p.x * SCALE, y, 0))
    const curve = new THREE.CatmullRomCurve3(pts)
    const segs = Math.max(24, seq.length * 12)
    const guide = new THREE.Group()

    // 底层宽带：MATLAB 蓝半透明光晕
    const glow = new THREE.Mesh(
      new THREE.TubeGeometry(curve, segs, 3.6, 8, false),
      new THREE.MeshBasicMaterial({ color: 0x0072bd, transparent: true, opacity: 0.22, depthWrite: false })
    )
    glow.renderOrder = 4
    guide.add(glow)

    // 核心亮线：MATLAB 蓝，更细、更不透明
    const core = new THREE.Mesh(
      new THREE.TubeGeometry(curve, segs, 1.3, 8, false),
      new THREE.MeshBasicMaterial({ color: 0x0072bd, transparent: true, opacity: 0.85, depthWrite: false })
    )
    core.renderOrder = 5
    guide.add(core)

    // 沿线箭头：MATLAB 深蓝，指示流向（朝 +X：原料在左、成品在右）
    for (let i = 0; i < seq.length - 1; i++) {
      const a = new THREE.Vector3(seq[i].x * SCALE, y, 0)
      const b = new THREE.Vector3(seq[i + 1].x * SCALE, y, 0)
      for (let k = 0.35; k <= 0.85; k += 0.25) {
        const p = a.clone().lerp(b, k)
        const cone = new THREE.Mesh(
          new THREE.ConeGeometry(3.8, 8, 8),
          new THREE.MeshBasicMaterial({ color: 0x005a93, transparent: true, opacity: 0.9, depthWrite: false })
        )
        cone.position.copy(p)
        cone.rotation.z = -Math.PI / 2
        cone.renderOrder = 5
        guide.add(cone)
      }
    }

    // 工序节点站台：每个小组/工序在流程线上"成站"——
    // 地面发光圆盘标记节点位置，侧前方悬浮编号名牌（01/02/03 + 工序名），
    // 让领导一眼看清主线经过哪些工序段、顺序如何。
    seq.forEach((p, i) => {
      const mark = new THREE.Group()
      mark.position.set(p.x * SCALE, 0, 0)
      // 地面标记圆盘（站点，MATLAB 蓝描边）
      const disc = new THREE.Mesh(
        new THREE.RingGeometry(22, 30, 48),
        new THREE.MeshBasicMaterial({ color: 0x0072bd, transparent: true, opacity: 0.4, side: THREE.DoubleSide, depthWrite: false })
      )
      disc.rotation.x = -Math.PI / 2
      disc.position.y = 3.35
      disc.renderOrder = 4
      mark.add(disc)
      const discFill = new THREE.Mesh(
        new THREE.CircleGeometry(26, 48),
        new THREE.MeshBasicMaterial({ color: 0x0072bd, transparent: true, opacity: 0.10, depthWrite: false })
      )
      discFill.rotation.x = -Math.PI / 2
      discFill.position.y = 3.3
      discFill.renderOrder = 4
      mark.add(discFill)
      // 工序已有单元标签，不再重复显示流程名牌，仅保留地面发光圆盘站点标记
      guide.add(mark)
    })

    this._guideGroup = guide
    this.root.add(guide)
  }

  _unitRole(unit, flows) {
    const hasUp = flows.some((f) => f.to_unit === unit.id)
    const hasDown = flows.some((f) => f.from_unit === unit.id)
    if (!hasUp && !hasDown) return 'iso'
    if (!hasUp) return 'start'
    if (!hasDown) return 'end'
    return 'mid'
  }

  _makeUnit(unit, res, role, share) {
    const meta = UNIT_META[unit.type] || { label: unit.name, shape: 'box' }
    const group = new THREE.Group()
    group.position.set(unit.x * SCALE, 2.5, (unit.z || 0) * SCALE) // 落于厂区地坪之上（地坪顶 y=-0.5，提升量抵消建造器负向基准）
    // 各工艺按实际规模差异化缩放 —— 高炉巨大、转炉/电炉中等、精炼/辅助偏小；
    // 小组子场景（groupScene）模式下整体再放大 GROUP_SCENE_GAIN 倍，成员模型更大更醒目
    const SCALE_MAP = {
      blast_furnace: 4.0, eaf: 5.0, furnace: 5.0, bof: 5.0, converter: 5.0,
      ladle_furnace: 4.6, rh_vacuum: 4.6, cylinder: 4.6,
      caster: 4.6, slab_caster: 4.6, rolling_mill: 4.6,
      sinter_plant: 4.6, pelletizing: 4.6, coke_oven: 4.6,
      hot_metal_pretreat: 4.2, ingot_casting: 4.2,
      reheating_furnace: 4.2, gas_power: 3.8, waste_heat: 3.5, ccs: 3.5, oxy_supply: 3.8, power_supply: 3.8
    }
    // 进入小组子场景后，成员模型大小与普通工艺保持一致（不再整体放大 GROUP_SCENE_GAIN 倍）
    const gsGain = 1
    group.scale.setScalar((SCALE_MAP[unit.type] || UNIT_SCALE) * gsGain)
    const scale = (SCALE_MAP[unit.type] || UNIT_SCALE) * gsGain
    const col = emissionColor(share)
    const co2Css = emissionCss(share)

    let body, bodyMat, bodyMats
    const anim = { rollers: [], slab: null, flame: null }
    const shape = meta.shape
    // 实心外壳，不透明；industrial 浅色模式下加深主体色以提高对比度
    const isLight = this.envMode === 'industrial'
    bodyMat = mat(isLight ? 0x5a6e80 : 0x7a8ea0, { metalness: 0.15, roughness: 0.5, transparent: false, opacity: 1.0, depthWrite: true })
    bodyMats = [bodyMat]
    const builder = builderMap[unit.type]
    if (builder) {
      body = builder(bodyMat, anim)
    } else {
      body = new THREE.Mesh(new THREE.BoxGeometry(20, 14, 16), bodyMat)
      body.userData.topY = 7
    }
    if (body.userData.topY == null) body.userData.topY = 16

    // 工艺模型Y轴拉伸（高炉除外），使各装置更具规模感
    const Y_STRETCH = {
      blast_furnace: 1.0, // 高炉不额外拉伸
      eaf: 1.4, furnace: 1.4, bof: 1.4, converter: 1.4,
      ladle_furnace: 1.35, rh_vacuum: 1.35, cylinder: 1.35,
      caster: 1.45, slab_caster: 1.45, rolling_mill: 1.45,
      sinter_plant: 1.4, pelletizing: 1.4, coke_oven: 1.4,
      hot_metal_pretreat: 1.5, ingot_casting: 1.45,
      reheating_furnace: 1.5, gas_power: 1.3, waste_heat: 1.3, ccs: 1.3, oxy_supply: 1.3, power_supply: 1.3
    }
    const yStretch = Y_STRETCH[unit.type] || 1.0
    if (yStretch !== 1.0) {
      body.scale.y = yStretch
      body.userData.topY *= yStretch
      if (body.userData.heatCenterY != null) body.userData.heatCenterY *= yStretch
      if (body.userData.heatInternalH != null) body.userData.heatInternalH *= yStretch
    }

    // 各工艺的原料输入/产品输出位置（模型空间Y坐标，反映实际生产高度差）
    const IO_Y = {
      // 高炉：固料从炉顶料钟入（高），铁水/炉渣从底部出铁口出（低）
      blast_furnace: { inY: 55, outY: 4 },
      // 电弧炉：废钢从炉顶加料，钢水从下方出钢口出
      eaf: { inY: 12, outY: 3 }, furnace: { inY: 12, outY: 3 },
      // 转炉：铁水从顶部兑入，钢水从底部出钢口出
      bof: { inY: 14, outY: 2 }, converter: { inY: 14, outY: 2 },
      // LF/RH/VD精炼：钢水从顶部注入，精炼后从底部出
      ladle_furnace: { inY: 10, outY: 3 }, rh_vacuum: { inY: 10, outY: 3 }, cylinder: { inY: 10, outY: 3 },
      // 连铸机：钢水从中间包（高）注入，铸坯从底部拉出
      caster: { inY: 12, outY: 3 }, slab_caster: { inY: 12, outY: 3 },
      // 轧机：板坯水平进、水平出（相近高度）
      rolling_mill: { inY: 4, outY: 4 },
      // 烧结机/球团：原料从上方布料，烧结矿/球团从下方排出
      sinter_plant: { inY: 9, outY: 3 }, pelletizing: { inY: 9, outY: 3 },
      // 焦炉：煤从顶部装煤车装入，焦炭从推焦侧推出
      coke_oven: { inY: 14, outY: 3 },
      // 铁水预处理：铁水从上方注入，处理后从下方倒出
      hot_metal_pretreat: { inY: 7, outY: 2 },
      // 模铸：钢水从上方浇注，钢锭在底部成型
      ingot_casting: { inY: 15, outY: 2 },
      // 加热炉：板坯从中间高度进/出
      reheating_furnace: { inY: 5, outY: 5 },
      // 工辅工艺：管线中位进/出
      gas_power: { inY: 6, outY: 6 }, waste_heat: { inY: 6, outY: 6 }, ccs: { inY: 6, outY: 6 }
    }
    const io = IO_Y[unit.type] || { inY: 10, outY: 4 }

    group.add(body)

    // 工艺本体底部对齐底座顶面（局部 y=0 → 世界 y=2.5）：
    // 部分模型（如转炉炉底锥/炉底封板、连铸机底部辊道等）几何底部在局部负Y，
    // 经整体缩放后会穿透底座，统一按包围盒整体提升，保证所有工艺模型都落在底座之上。
    let lift = 0
    {
      group.updateMatrixWorld(true)
      const box = new THREE.Box3().setFromObject(body)
      const minLocal = (box.min.y - group.position.y) / group.scale.y
      if (Number.isFinite(minLocal) && minLocal < 0.01) lift = -minLocal + 0.01
    }
    if (lift > 0.001) body.position.y = lift

    // 底座：不跟随模型旋转，始终贴地平放。
    // 世界高度恒为 3：顶面贴合模型底部（世界 y=2.5），底面贴地坪（世界 y≈-0.5），
    // 任何缩放下的工艺模型底部都精确坐在底座顶面上，不再悬空或穿底。
    // 工业场景：深灰钢 + 混凝土纹理底座（与厂区地坪统一），顶部加一圈安全基准线；
    // 其余场景：底座浅色统一（组内成员不再单独渲染，小组以琥珀色大底座聚合模型呈现，见 _makeGroupModel）
    const industrial = this.envMode === 'industrial'
    const pedestalMat = new THREE.MeshStandardMaterial({
      color: industrial ? 0xffffff : 0xf4f7fa,
      roughness: industrial ? 0.92 : 0.9,
      metalness: industrial ? 0.12 : 0,
      map: industrial ? _industrialTex() : null
    })
    const pedestalH = 3 / scale
    // 进入小组子场景：成员模型与普通工艺保持一致的尺寸与外观，底座半宽统一为 14（明显底座，不缩小）
    const pedestalHalf = 14
    const pedestal = new THREE.Mesh(new THREE.BoxGeometry(pedestalHalf * 2, pedestalH, pedestalHalf * 2), pedestalMat)
    pedestal.position.y = -pedestalH / 2
    pedestal.receiveShadow = true; pedestal.castShadow = true
    group.add(pedestal)
    if (!this._pedestalMats) this._pedestalMats = []
    this._pedestalMats.push(pedestalMat)

    // 工业底座顶面安全基准线：一圈低饱和工业黄细线，标识设备安装边界（非工业场景不显示）
    if (industrial) {
      const lineW = Math.max(0.8, pedestalHalf * 0.06)
      const edgeMat = new THREE.MeshBasicMaterial({ color: 0xb08a2e, transparent: true, opacity: 0.9 })
      const eGeoX = new THREE.BoxGeometry(pedestalHalf * 2 - lineW * 2, 0.16 / scale, lineW)
      const e1 = new THREE.Mesh(eGeoX, edgeMat)
      e1.position.set(0, 0.08 / scale, pedestalHalf - lineW / 2)
      group.add(e1)
      const e2 = e1.clone(); e2.position.z = -pedestalHalf + lineW / 2; group.add(e2)
      const eGeoZ = new THREE.BoxGeometry(lineW, 0.16 / scale, pedestalHalf * 2 - lineW * 2)
      const e3 = new THREE.Mesh(eGeoZ, edgeMat)
      e3.position.set(pedestalHalf - lineW / 2, 0.08 / scale, 0)
      group.add(e3)
      const e4 = e3.clone(); e4.position.x = -pedestalHalf + lineW / 2; group.add(e4)
      if (!this._pedestalEdgeMats) this._pedestalEdgeMats = []
      this._pedestalEdgeMats.push(edgeMat)
    }

    // 内部温度分层可视化
    const heatLayers = this._addHeatLayers(body, unit, res)

    // 去掉了碳足迹光斑与地坪圆环，代之以设备悬浮于厂区基座上。
    // 燃烧特效（熔炉类）：炉前跳动火焰 + 暖色辉光脉动
    if (shape === 'furnace') {
      anim.flame = this._makeFlame(res ? res.heat : 0)
      anim.flame.position.y += lift
      group.add(anim.flame)
      const glow = new THREE.PointLight(0xff6a1e, 0.0, 70, 2)
      glow.position.set(0, body.userData.topY * 0.4 + lift, 5)
      group.add(glow)
      anim.glow = glow
      anim.glowBase = 1.6 + (res && res.heat ? res.heat : 0.4) * 2.0
      anim.glowMats = bodyMats.slice()
    }

    // 各工艺动画钩子：从 userData 提取构造器中预置的动画数据
    const ud = body.userData
    if (ud._rollers && ud._rollers.length) {
      anim.rollers = ud._rollers // 加热炉辊道 / 球团窑托轮 等旋转部件
    }
    if (ud._chargeGlow && ud._chargeGlow.length) {
      // 加热炉进/出料口炽热脉动
      anim.glowMats = (anim.glowMats || []).concat(ud._chargeGlow)
      if (!anim.glow) {
        anim.glow = new THREE.PointLight(0xff6622, 0.0, 60, 2)
        anim.glow.position.set(0, body.userData.topY * 0.5 + lift, 5)
        group.add(anim.glow)
        anim.glowBase = 1.2
      }
    }
    if (ud._igniterFlame) {
      // 烧结机点火炉火焰（复用flame动画系统）
      if (!anim.flame) {
        anim.flame = new THREE.Group()
        group.add(anim.flame)
      }
      anim.flame.add(ud._igniterFlame)
    }
    if (ud._steamPuff) {
      // 焦炉熄焦蒸汽云脉动
      if (!anim.glowMats) anim.glowMats = []
      anim.glowMats.push(ud._steamPuff.material)
      if (!anim.glow) { anim.glowBase = 0.6 }
    }
    if (ud._converterPivot) {
      // 转炉倾动摇炉动画
      anim.converterPivot = ud._converterPivot
      anim.converterMelt = ud._converterMelt || null
      anim.converterMeltRipples = ud._converterMeltRipples || []
      anim.converterTilt = 0
      anim._convSparks = ud._convSparks || []
      anim._convBottomBubbs = ud._convBottomBubbs || []
      anim._convSlagMat = ud._convSlagMat || null
    }
    if (ud._furnaceElectrodes) {
      // 电炉电极升降 + 电弧脉动动画
      anim.furnaceElectrodes = ud._furnaceElectrodes
    }
    if (ud._arBubbles && ud._arBubbles.length) {
      // LF精炼底吹氩气气泡上升动画
      anim.arBubbles = ud._arBubbles
    }
    if (ud._matFlow && ud._matFlow.length) {
      // 物料转变动画：原料进→工艺处理→产品出
      anim.matFlow = ud._matFlow
    }
    if (ud._casterStrand) { anim.casterStrand = ud._casterStrand }
    if (ud._pelletDiscs && ud._pelletDiscs.length) { anim.pelletDiscs = ud._pelletDiscs }
    if (ud._internalSlabs && ud._internalSlabs.length) { anim.internalSlabs = ud._internalSlabs }

    // 唯一标签（角色 + 名称 + 先能后碳；碳数字按其排放占比着色）
    const label = this._makeLabel(unit.name, res ? res.co2_total : null, res ? res.energy_total : null, role, co2Css)
    // 工艺/工辅标签样式统一、大小一致：同一两行卡片布局、同一悬浮位置，main 仅标记主工艺层级
    const isMain = unit.route !== 'aux' && unit.route !== 'util'
    // 工序标签悬浮在设备顶部正上方（与管道/轨道连接标签的悬浮位置形式一致）
    label.position.set(0, (body.userData.topY || 0) + 5.5, 0)
    label.userData.unitId = unit.id
    label.userData.kind = 'unit'   // 可由 3D 标签直接点击聚焦（替代点击工艺本体）
    label.userData.labelObj.main = isMain
    // 创建时统一绘制（工艺/工辅一致），_key 置空以让 main 标志生效
    label.userData.labelObj._key = null
    this._drawLabel(label.userData.labelObj)
    group.add(label)

    // 选中高亮环：悬浮式圆环替代原来的地面光斑选中标记
    const ring = new THREE.Mesh(
      new THREE.RingGeometry(14, 16, 64),
      new THREE.MeshBasicMaterial({ color: 0x7fc8e6, side: THREE.DoubleSide, transparent: true, opacity: 0, depthWrite: false }),
    )
    ring.rotation.x = -Math.PI / 2
    ring.position.y = body.userData.topY * 0.1
    ring.renderOrder = 3
    group.add(ring)

    // 烟囱羽流已移除（用户要求去掉雾团）

    // 统一开启阴影：遍历所有子网格，使设备投射并接收阴影
    body.traverse((child) => {
      if (child.isMesh) {
        child.castShadow = true
        child.receiveShadow = true
      }
    })

    group.userData = {
      unitId: unit.id, unitType: unit.type, route: unit.route || null,
      groupId: unit.groupId || null, body, bodyMat, bodyMats, label, labelObj: label.userData.labelObj, ring,
      topY: body.userData.topY, share: share || 0, shareCss: co2Css,
      ioY: { in: io.inY * yStretch, out: io.outY * yStretch },   // 模型空间输入/输出口高度
      yStretch,   // Y轴拉伸系数
      lift,       // 本体相对底座顶面的提升量（局部），用于管道连接点等世界定位
      flame: anim.flame, glow: anim.glow, glowMats: anim.glowMats, glowBase: anim.glowBase,
      rollers: anim.rollers, slab: anim.slab, slabT: 0, plume: null,
      converterPivot: anim.converterPivot, converterMelt: anim.converterMelt,
      converterMeltRipples: anim.converterMeltRipples, converterTilt: anim.converterTilt,
      _convSparks: anim._convSparks, _convBottomBubbs: anim._convBottomBubbs, _convSlagMat: anim._convSlagMat,
      furnaceElectrodes: anim.furnaceElectrodes,
      arBubbles: anim.arBubbles,
      matFlow: anim.matFlow,
      casterStrand: anim.casterStrand,
      pelletDiscs: anim.pelletDiscs,
      internalSlabs: anim.internalSlabs,
      heatLayers,   // 示意模式：温度分层可视化句柄（含 tick() 脉动与 update() 刷新）
    }
    // 透传 builder 预置的所有 _ 前缀动画钩子（高炉/电炉/连铸/焦炉/烧结/精炼/预处理/加热炉专属动画）
    // 避免遗漏字段导致专属动画失效
    for (const k of Object.keys(ud)) {
      if (k.startsWith('_') && group.userData[k] === undefined) {
        group.userData[k] = ud[k]
      }
    }
    return { group, ...group.userData }
  }

  // ---- 设备小组聚合模型：整组在数字孪生中以“一台大设备”呈现 ----
  // 顶层小组：与普通工艺保持一致的尺寸与外观（不再聚合为大底座设备），仅以标签「组名 ×N」标识。
  // 模型取小组代表性成员、按普通单元尺寸渲染；点击即选中整个小组（保留进入小组功能）。
  _makeGroupModel(gid, members, reses, shareOf) {
    const gMeta = this._groupMeta ? (this._groupMeta.get(gid) || { name: '设备小组' }) : { name: '设备小组' }
    const gname = String(gMeta.name || '设备小组').slice(0, 14)
    const n = members.length

    // 1) 组中心 = 成员包围盒中心（世界坐标，SCALE=1）
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity
    for (const u of members) {
      const z = u.z || 0
      if (u.x < minX) minX = u.x
      if (u.x > maxX) maxX = u.x
      if (z < minZ) minZ = z
      if (z > maxZ) maxZ = z
    }
    const cx = (minX + maxX) / 2, cz = (minZ + maxZ) / 2

    // 2) 代表性成员：取主工艺（route 非 aux/util），否则取首个成员
    const rep = members.find((u) => u.route !== 'aux' && u.route !== 'util') || members[0]
    const repRes = (reses && reses[members.indexOf(rep)]) || null

    // 3) 复用标准单元模型（与普通工艺完全一致的大小与外观），临时以独立单元身份渲染。
    //    注意：组本身是一个容器，其世界位置(group.position)已设为组中心(cx,cz)；
    //    因此代表成员必须以「组中心为局部原点」渲染(x:0,z:0)，否则本体世界坐标会变成
    //    (cx + rep.x, cz + rep.z) —— 与组中心(cx,cz)双重偏移、远离平台，导致管道锚点(centerX/centerZ)
    //    与实际模型错位、看起来"没连上线路"。
    const built = this._makeUnit({ ...rep, groupId: null, x: 0, z: 0 }, repRes, 'mid', 0)
    const body = built.body
    body.traverse((child) => {
      if (child.isMesh) {
        child.userData.kind = 'unit'
        child.userData.groupId = gid   // 点击模型即选中整个小组
      }
    })
    // 移除代表性成员的自带标签（避免与普通工艺标签重复），改用「组名 ×N」标签
    if (built.label) built.group.remove(built.label)
    if (built.ring) built.ring.userData = { kind: 'unit', groupId: gid }

    const group = new THREE.Group()
    group.position.set(cx, 0, cz)
    group.add(built.group)

    // 4) 组标签：组名 + 「×N」倍数 + 汇总能耗/碳排
    const co2 = reses.reduce((s, r) => s + (r ? r.co2_total || 0 : 0), 0)
    const en = reses.reduce((s, r) => s + (r ? r.energy_total || 0 : 0), 0)
    const label = this._makeGroupLabel(gname, n, reses.some((r) => r) ? co2 : null, reses.some((r) => r) ? en : null)
    label.position.set(0, built.topY + 12, 0)
    label.userData.kind = 'unit'
    label.userData.groupId = gid
    // _makeGroupLabel 已自行完成绘制；标注为组标签，便于实时刷新时走 _drawGroupLabel
    label.userData.labelObj.isGroup = true
    group.add(label)

    // 5) 管道连接用统一 IO 高度（世界坐标，与代表成员一致，汇聚到组中心）
    const io = this._ioHeights(rep.type, built.lift)

    group.userData = {
      unitId: null,
      groupId: gid,
      body,
      isGroup: true,
      groupName: gMeta.name,
      memberIds: members.map((u) => u.id),
      memberUnits: members,
      countByType: null,
      label, labelObj: label.userData.labelObj, ring: built.ring,
      topY: built.topY + 12, lift: built.lift, yStretch: built.yStretch,
      ioY: io,
      centerX: cx, centerZ: cz,
      share: 0, shareCss: '#e86850',
    }
    return { group, ...group.userData }
  }

  // 小组标签：组名 + 「×N」倍数 + 汇总能耗/碳排（尺寸与普通工艺标签一致，两行布局）
  _makeGroupLabel(name, count, co2, energy) {
    const canvas = document.createElement('canvas')
    canvas.width = LABEL_W * LABEL_SS
    canvas.height = UNIT_LABEL_H * LABEL_SS
    const ctx = canvas.getContext('2d')
    const tex = new THREE.CanvasTexture(canvas)
    tex.colorSpace = THREE.SRGBColorSpace
    tex.minFilter = THREE.LinearFilter
    tex.magFilter = THREE.LinearFilter
    tex.generateMipmaps = false
    const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false, depthWrite: false }))
    spr.scale.set(LABEL_SCALE, LABEL_SCALE * (UNIT_LABEL_H / LABEL_W), 1)
    spr.renderOrder = 11
    const obj = { canvas, ctx, tex, sprite: spr, name, count, co2, energy, isGroup: true, _key: null }
    spr.userData.labelObj = obj
    this._drawGroupLabel(obj, co2, energy)
    return spr
  }

  // 绘制/重绘小组标签（供 _makeGroupLabel 与实时刷新 _refreshGroupLabels 复用）
  _drawGroupLabel(obj, co2, energy) {
    const { ctx, tex } = obj
    const name = obj.name
    const count = obj.count
    const key = [name, count, co2, energy, this.envMode].join('|')
    if (obj._key === key) return
    obj._key = key
    obj.co2 = co2; obj.energy = energy
    ctx.setTransform(LABEL_SS, 0, 0, LABEL_SS, 0, 0)
    ctx.clearRect(0, 0, LABEL_W, UNIT_LABEL_H)

    const light = this.envMode === 'industrial'
    // 背景卡片（与工艺标签同高同款：工业浅色 / 其余深色毛玻璃）
    _roundRect(ctx, 1, 1, LABEL_W - 2, UNIT_LABEL_H - 2, 9)
    if (light) {
      ctx.fillStyle = 'rgba(255,255,255,0.97)'
      ctx.fill()
      ctx.lineWidth = 1
      ctx.strokeStyle = 'rgba(214,219,225,1)'
      ctx.stroke()
    } else {
      ctx.fillStyle = 'rgba(20,28,38,0.82)'
      ctx.fill()
      ctx.lineWidth = 1
      ctx.strokeStyle = 'rgba(120,150,180,0.35)'
      ctx.stroke()
    }

    // 第一行：组名 + 「×N」倍数徽章（蓝灰，系统强调色），右侧「点击 ▸」提示
    ctx.textBaseline = 'middle'
    ctx.textAlign = 'left'
    let x = 14
    ctx.font = `bold 16px ${LABEL_FONT}`
    ctx.fillStyle = light ? '#1f2733' : 'rgba(255,255,255,0.95)'
    const nameW = LABEL_W - 30 - 64   // 预留 ×N 徽章与「点击 ▸」空间
    let nm = name
    if (ctx.measureText(nm).width > nameW) {
      while (nm.length > 1 && ctx.measureText(nm + '…').width > nameW) nm = nm.slice(0, -1)
      nm += '…'
    }
    ctx.fillText(nm, x, 21)
    x += ctx.measureText(nm).width + 6

    const tagText = `×${count}`
    ctx.font = `bold 14px ${LABEL_FONT}`
    const tw = ctx.measureText(tagText).width
    const padX = 6
    _roundRect(ctx, x, 21 - 11, tw + padX * 2, 22, 7)
    ctx.fillStyle = 'rgba(0,75,118,0.12)'
    ctx.fill()
    ctx.fillStyle = '#005E94'
    ctx.fillText(tagText, x + padX, 21 + 1)

    // 右侧「点击 ▸」提示（可交互暗示）
    ctx.textAlign = 'right'
    ctx.font = `600 11px ${LABEL_FONT}`
    ctx.fillStyle = light ? '#005E94' : '#6ecfff'
    ctx.fillText('点击 ▸', LABEL_W - 13, 21)

    // 第二行：汇总能耗 ⚡ 左对齐 / 碳排 ☁ 右对齐（与工艺标签一致）
    ctx.textAlign = 'left'
    ctx.font = `600 14px ${LABEL_FONT}`
    ctx.fillStyle = light ? '#5a6472' : 'rgba(170,190,210,0.95)'
    const enStr = energy != null ? fmtShort(energy) : '—'
    ctx.fillText('⚡ ' + enStr, 14, 46)
    ctx.textAlign = 'right'
    const co2Str = co2 != null ? fmtShort(co2) : '—'
    ctx.fillStyle = light ? '#005E94' : '#6ecfff'
    ctx.fillText('☁ ' + co2Str, LABEL_W - 15, 46)

    tex.needsUpdate = true
  }

  // —— 各类工艺本体的程序化工业造型（浅灰哑光涂装 + 深蓝灰钢构 + 企业蓝点缀）——






  // 每个工序有且仅有一个标签（工序名 + 先能后碳）。聚焦时只改变其样式与尺寸，不再另建卡片，
  // 避免此前「常驻名称标签 + 聚焦 HUD 卡片」同时出现造成的重影。
  _makeLabel(name, co2, energy, role, co2Css) {
    const canvas = document.createElement('canvas')
    canvas.width = LABEL_W * LABEL_SS
    canvas.height = UNIT_LABEL_H * LABEL_SS
    const ctx = canvas.getContext('2d')
    ctx.setTransform(LABEL_SS, 0, 0, LABEL_SS, 0, 0)   // 之后统一按逻辑坐标绘制
    const tex = new THREE.CanvasTexture(canvas)
    tex.colorSpace = THREE.SRGBColorSpace   // 与渲染器输出一致，避免文字发灰、色块偏暗
    tex.anisotropy = this._maxAniso()
    tex.minFilter = THREE.LinearFilter      // 关闭 mipmap 链，远处文字不被过度模糊
    tex.magFilter = THREE.LinearFilter
    tex.generateMipmaps = false
    const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }))
    spr.scale.set(LABEL_SCALE, LABEL_SCALE * (UNIT_LABEL_H / LABEL_W), 1)
    spr.renderOrder = 12
    const obj = { canvas, ctx, tex, sprite: spr, name, role, co2Css, focused: false }
    this._drawLabel(obj, co2, energy, role, co2Css)
    spr.userData.labelObj = obj
    return spr
  }

  // 低端机优化：各向异性过滤 8→4，纹理采样带宽减半，远距离斜视时差异在工业场景中几乎不可见
  _maxAniso() {
    try { return Math.min(8, this.renderer.capabilities.getMaxAnisotropy()) } catch (e) { return 2 }
  }

  // 传 undefined 的字段表示「沿用上次值」，便于实时帧只刷新变化的指标。
  // 工艺标签两行布局：第一行工序名 + 角色色点，第二行实时能耗 ⚡ / 碳排 ☁（先能后碳），无需点击即可直接查看。
  _drawLabel(obj, co2, energy, role, co2Css) {
    if (obj && obj.isGroup) { this._drawGroupLabel(obj, energy != null ? energy : obj.energy, co2 != null ? co2 : obj.co2); return }
    const { ctx, tex } = obj
    if (role !== undefined) obj.role = role
    if (co2Css !== undefined) obj.co2Css = co2Css
    if (co2 !== undefined) obj.co2 = co2
    if (energy !== undefined) obj.energy = energy
    const c = obj.co2
    const e = obj.energy
    const focused = !!obj.focused
    const key = [obj.name, obj.role, focused, obj.main === true, c, e, obj.co2Css, this.envMode].join('|')
    if (obj._key === key) return
    obj._key = key
    // industrial 模式（VS Code 浅色环境）：与管道标签（_drawFlowLabel）样式一致——
    // 白底浅灰卡片、无角色圆点/彩色侧条，左侧深色工序名，下方数据行
    const light = this.envMode === 'industrial'

    ctx.clearRect(0, 0, LABEL_W, UNIT_LABEL_H)

    if (light) {
      _drawLabelCard(ctx, focused, undefined, undefined, undefined, true, UNIT_LABEL_H)
      ctx.textBaseline = 'middle'
      // 工序名（深色，与管道标签物料名同款；过长自动截断）
      ctx.textAlign = 'left'
      ctx.font = `bold 16px ${LABEL_FONT}`
      ctx.fillStyle = focused ? '#004B76' : '#1C1C1C'
      const maxNameW = LABEL_W - 30
      let text = obj.name
      if (ctx.measureText(text).width > maxNameW) {
        while (text.length > 1 && ctx.measureText(text + '…').width > maxNameW) text = text.slice(0, -1)
        text += '…'
      }
      ctx.fillText(text, 15, 21)
      // 第二行：实时能耗 ⚡ 左对齐 / 碳排 ☁ 右对齐（碳排按排放占比着色，长数字也不会重叠）
      ctx.font = `600 14px ${LABEL_FONT}`
      ctx.fillStyle = '#5a6472'
      ctx.fillText('⚡ ' + fmtShort(e), 15, 46)
      ctx.textAlign = 'right'
      ctx.fillStyle = obj.co2Css || '#005E94'
      ctx.fillText('☁ ' + fmtShort(c), LABEL_W - 15, 46)
      ctx.shadowBlur = 0; ctx.shadowOffsetY = 0
      tex.needsUpdate = true
      return
    }

    // ===== 深色毛玻璃铭牌（非 industrial 场景：虚空/沙漠/城市/海滩） =====
    _drawLabelCard(ctx, focused, obj.role, true, obj.main, false, UNIT_LABEL_H)

    ctx.textBaseline = 'middle'

    // 角色色点（霓虹色，与深色底板强对比）：工艺/工辅统一中性灰蓝，仅起点/终点/隔离保留语义色
    const roleColor = obj.role === 'start' ? '#3ddc84'
      : obj.role === 'end' ? '#00a8ff'
      : obj.role === 'iso' ? '#ffcc3d'
      : '#7a93a6'
    ctx.fillStyle = roleColor
    ctx.beginPath()
    ctx.arc(17, 21, 3.4, 0, Math.PI * 2)
    ctx.fill()

    // 工序名（高亮文字，过长自动截断）
    ctx.textAlign = 'left'
    ctx.font = `bold 16px ${LABEL_FONT}`
    ctx.fillStyle = focused ? '#ffffff' : 'rgba(255,255,255,0.92)'
    const maxNameW = LABEL_W - 30 - 10
    let text = obj.name
    if (ctx.measureText(text).width > maxNameW) {
      while (text.length > 1 && ctx.measureText(text + '…').width > maxNameW) text = text.slice(0, -1)
      text += '…'
    }
    ctx.fillText(text, 30, 21)

    // 第二行：实时能耗 ⚡ 左对齐 / 碳排 ☁ 右对齐（碳排按排放占比着色，长数字也不会重叠）
    ctx.font = `600 14px ${LABEL_FONT}`
    ctx.fillStyle = 'rgba(170,190,210,0.95)'
    ctx.fillText('⚡ ' + fmtShort(e), 30, 46)
    ctx.textAlign = 'right'
    ctx.fillStyle = obj.co2Css || 'rgba(170,190,210,0.95)'
    ctx.fillText('☁ ' + fmtShort(c), LABEL_W - 15, 46)

    ctx.shadowBlur = 0; ctx.shadowOffsetY = 0
    tex.needsUpdate = true
  }

  _makeParticles(count, color, size, isSmoke = false, colH = 14) {
    const geo = new THREE.BufferGeometry()
    const pos = new Float32Array(count * 3)
    const seed = new Float32Array(count)
    for (let i = 0; i < count; i++) {
      pos[i * 3] = (Math.random() - 0.5) * 3
      pos[i * 3 + 1] = Math.random() * colH
      pos[i * 3 + 2] = (Math.random() - 0.5) * 3
      seed[i] = Math.random()
    }
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geo.setAttribute('seed', new THREE.BufferAttribute(seed, 1))
    const matp = new THREE.PointsMaterial({
      color, size, transparent: true, opacity: 0.5,
      depthWrite: false, blending: isSmoke ? THREE.NormalBlending : THREE.AdditiveBlending,
    })
    const pts = new THREE.Points(geo, matp)
    pts.userData = { count, isSmoke, maxY: colH }
    return pts
  }

  // 燃烧火焰：炉前一个跳动的火把（外焰+内焰），Additive 混合，无需额外灯光
  _makeFlame(heat) {
    const g = new THREE.Group()
    const col = heat > 0.5 ? 0xff3b1e : 0xff8a1e
    const cone = new THREE.Mesh(
      new THREE.ConeGeometry(1.4, 4, 12),
      new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.82, blending: THREE.AdditiveBlending, depthWrite: false }),
    )
    cone.position.y = 2
    g.add(cone)
    const inner = new THREE.Mesh(
      new THREE.ConeGeometry(0.7, 2.2, 8),
      new THREE.MeshBasicMaterial({ color: 0xffe08a, transparent: true, opacity: 0.92, blending: THREE.AdditiveBlending, depthWrite: false }),
    )
    inner.position.y = 1.1
    g.add(inner)
    g.position.set(0, 1.4, 5)
    g.userData = { cone, inner }
    return g
  }

  // 物料运输意象：按物料 id 区分「模型 + 运动风格」，替代原先统一的黄色小球。
  // molten/liquid=熔体/液体（走流槽）；granular/chunk/slab=固体（走传送带）；gas=气体（走管道）。
  _makeMaterialCarrier(materialId) {
    const V = MAT_VIS[materialId] || MAT_VIS._default
    const style = V.style
    if (style === 'molten') {
      const m = new THREE.Mesh(
        new THREE.SphereGeometry(1.3, 12, 9),
        mat(V.color, { emissive: V.emissive, emissiveIntensity: V.emi, roughness: 0.3, metalness: 0.1 }),
      )
      m.scale.set(1.6, 0.6, 1.2) // 扁液滴，匹配加宽流槽
      return { obj: m, mat: m.material, emi: V.emi, anim: 'molten' }
    }
    if (style === 'liquid') {
      const m = new THREE.Mesh(
        new THREE.SphereGeometry(1.2, 12, 9),
        mat(V.color, { roughness: 0.2, metalness: 0.0, transparent: true, opacity: 0.85 }),
      )
      m.scale.set(1.5, 0.6, 1.2)
      return { obj: m, mat: m.material, emi: 0, anim: 'liquid' }
    }
    if (style === 'slab') {
      const m = new THREE.Mesh(
        new THREE.BoxGeometry(4.5, 0.75, 2.4),
        mat(V.color, V.emissive != null
          ? { emissive: V.emissive, emissiveIntensity: V.emi, roughness: 0.5, metalness: 0.35 }
          : { roughness: 0.6, metalness: 0.45 }),
      )
      return { obj: m, mat: m.material, emi: V.emi || 0, anim: 'slab' }
    }
    if (style === 'chunk') {
      const g = new THREE.Group()
      for (let i = 0; i < 5; i++) {
        const s = 0.6 + Math.random() * 0.6
        const b = new THREE.Mesh(new THREE.BoxGeometry(s, s * (0.6 + Math.random() * 0.6), s), mat(V.color, { roughness: 0.55, metalness: 0.5 }))
        b.position.set((Math.random() - 0.5) * 2.4, (Math.random() - 0.5) * 1.2, (Math.random() - 0.5) * 1.8)
        b.rotation.set(Math.random() * 3, Math.random() * 3, Math.random() * 3)
        g.add(b)
      }
      return { obj: g, mat: null, emi: 0, anim: 'chunk' }
    }
    if (style === 'gas') {
      // 气体：一小簇半透明气泡，在管道内穿行（加粗管道配更大气泡簇）
      const g = new THREE.Group()
      for (let i = 0; i < 6; i++) {
        const r = 0.6 + Math.random() * 0.4
        const b = new THREE.Mesh(
          new THREE.SphereGeometry(r, 8, 6),
          new THREE.MeshStandardMaterial({ color: V.color, transparent: true, opacity: 0.5, roughness: 0.4, emissive: V.color, emissiveIntensity: 0.25 }),
        )
        b.position.set((Math.random() - 0.5) * 2.8, (Math.random() - 0.5) * 1.2, (Math.random() - 0.5) * 1.2)
        g.add(b)
      }
      return { obj: g, mat: null, emi: 0, anim: 'gas' }
    }
    // granular（散料）：一小簇不规则颗粒，匹配加宽传送带
    const g = new THREE.Group()
    for (let i = 0; i < 8; i++) {
      const r = 0.5 + Math.random() * 0.25
      const p = new THREE.Mesh(new THREE.IcosahedronGeometry(r, 0), mat(V.color, { roughness: 0.95, metalness: 0.05 }))
      p.position.set((Math.random() - 0.5) * 3.0, (Math.random() - 0.5) * 1.2, (Math.random() - 0.5) * 2.0)
      g.add(p)
    }
    return { obj: g, mat: null, emi: 0, anim: 'granular' }
  }

  // 释放一组对象（几何 + 材质），避免重建流程时 GPU 资源堆积。
  _disposeGroup(g) {
    g.traverse((o) => {
      if (o.geometry) o.geometry.dispose()
      if (o.material) {
        const ms = Array.isArray(o.material) ? o.material : [o.material]
        ms.forEach((m) => { if (m.map) m.map.dispose(); m.dispose() })
      }
    })
  }

  // 文字标签（精灵，始终朝向相机）：显示物料名 + 运输速度。
  // 工艺间连接标签：与工序标签保持一致的蓝调铭牌 + 两行指标（先主后碳），
  // 仅标题/副标题语义不同——工序为「名称 + 角色」，连接为「物料名 + 速度」。
  _makeFlowLabel(name, hexColor, rate, carbon, speed) {
    const canvas = document.createElement('canvas')
    canvas.width = LABEL_W * LABEL_SS
    canvas.height = LABEL_H * LABEL_SS
    const ctx = canvas.getContext('2d')
    ctx.setTransform(LABEL_SS, 0, 0, LABEL_SS, 0, 0)
    const tex = new THREE.CanvasTexture(canvas)
    tex.colorSpace = THREE.SRGBColorSpace
    tex.anisotropy = this._maxAniso()
    tex.minFilter = THREE.LinearFilter
    tex.magFilter = THREE.LinearFilter
    tex.generateMipmaps = false
    const spr = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthTest: false }))
    spr.scale.set(LABEL_SCALE, LABEL_SCALE * LABEL_ASPECT, 1)   // 与工序标签统一尺寸
    spr.renderOrder = 12
    this._drawFlowLabel(ctx, tex, name, hexColor, rate, carbon, speed)
    return spr
  }

  _drawFlowLabel(ctx, tex, name, color, rate, carbon, speed) {
    ctx.clearRect(0, 0, LABEL_W, LABEL_H)
    const light = this.envMode === 'industrial'
    _drawLabelCard(ctx, false, undefined, undefined, undefined, light)

    ctx.textBaseline = 'middle'

    // 物料名（与工序标签一致：浅色场景深色文字、深色场景白色文字）
    ctx.textAlign = 'left'
    ctx.font = `bold 16px ${LABEL_FONT}`
    ctx.fillStyle = light ? '#1C1C1C' : 'rgba(255,255,255,0.92)'
    ctx.fillText(name, 15, LABEL_H / 2)

    // 运输速度（浅色场景 MATLAB 蓝小字；深色场景亮青，与工序标签「点击 ▸」同款）
    ctx.textAlign = 'right'
    ctx.font = `600 11px ${LABEL_FONT}`
    ctx.fillStyle = light ? (color || '#005E94') : '#6ecfff'
    ctx.fillText(speed + ' m/s', LABEL_W - 15, LABEL_H / 2)

    ctx.shadowBlur = 0; ctx.shadowOffsetY = 0
    tex.needsUpdate = true
  }

  // 计算某类工艺在世界空间中的输入/输出口高度（含Y拉伸与整体缩放 + 本体底部提升量）。
  // 端口定义（IO_Y_DEFS / Y_STRETCH_DEFS / SCALE_DEFS / PORT_OFFSET_DEFS）为模块级常量。
  _ioHeights(type, lift = 0) {
    const io = IO_Y_DEFS[type] || { inY: 10, outY: 4 }
    const ys = Y_STRETCH_DEFS[type] || 1.0
    // 小组子场景成员整体放大 GROUP_SCENE_GAIN 倍，端口高度/偏移同步放大，管道端点才能贴合放大后的模型
    const s = (SCALE_DEFS[type] || UNIT_SCALE) * (this.groupScene ? GROUP_SCENE_GAIN : 1)
    const po = PORT_OFFSET_DEFS[type] || { outX: 8, outZ: 0, inX: 0, inZ: 0 }

    // 2.5 为 _makeUnit 中 group.position.y（位于厂区地坪之上）；lift 为本体底部提升量（局部），乘 s 换算到世界
    return {
      inY:  2.5 + io.inY  * ys * s + lift * s,
      outY: 2.5 + io.outY * ys * s + lift * s,
      inX:  po.inX  * s,  inZ:  po.inZ  * s,   // 模型空间 * 整体缩放 → 局部空间偏移
      outX: po.outX * s,  outZ: po.outZ * s
    }
  }
  _makeFlows(flows, byId) {
    this.flows = []
    // 重建前先释放上一版所有连廊对象（媒介 + 载运体 + 标签）
    if (this._flowGroup) { this._disposeGroup(this._flowGroup); this.root.remove(this._flowGroup) }
    this._flowGroup = new THREE.Group()
    this.root.add(this._flowGroup)
    // 分段构建复用的临时对象（避免每段/每 flow 重复分配向量/矩阵/四元数）
    const _v1 = new THREE.Vector3(), _v2 = new THREE.Vector3(), _v3 = new THREE.Vector3()
    const _v4 = new THREE.Vector3(), _v5 = new THREE.Vector3()
    const _m4 = new THREE.Matrix4(), _q = new THREE.Quaternion()
    // 端口尽量使用工艺 PORT_OFFSET 定义的真实出入口位置（源出口 / 目标入口）。
    // 交界处只限制高度：在出入口高度的水平面上，水平角度/方向均可自由切换（正交滑出/滑入）。
    // 高度原则：水平段高度 H 由目标入口位置决定（= 入口高度 + 汇聚层差），源端滑出后
    //           通过立管调整到位。
    // 路径：源出口 → 出口高度水平面滑出(仅X/Z) → 源端立管(沿Y, 高度按目标入口设定)
    //       → 水平段(正交最短L形, 仅X/Z) → 目标端立管(沿Y 弯折到入口高度)
    //       → 入口高度水平面上滑入汇聚。
    // 多条线路可能交叉/共享同一入口 → 不同水平段高度（垂直分层）区分，最后在目标入口处弯折汇聚。
    // 每段只改变一个坐标轴，绝对不产生斜线。
    // 组场景模式：仅绘制组内成员之间的连线（成员已展开为独立模型，呈现小组内部工艺关系）；
    // 顶层模式：合并小组对外连线（同一小组 → 同一目标(节点/小组) 的同物料流合并为一条，
    // 小组作为一个整体对外连线，如 3 台热风炉各自送热风到高炉 → 只画一条热风主管，
    // 速率取合并前各条之和，其余字段沿用组内第一条）。
    if (this.groupScene) {
      flows = flows.filter((f) => {
        const ma = byId[f.from_unit], mb = byId[f.to_unit]
        // 子场景：绘制所有两端都位于该小组展开成员集合内的连线（成员间关系）。
        // 注意：进入小组时成员 groupId 已置空，不能再用 groupId 判断归属。
        return ma && mb
      })
    } else {
      const merged = []
      const mergedSeen = new Map()
      for (const f of flows) {
        const ma = byId[f.from_unit], mb = byId[f.to_unit]
        if (!ma || !mb) continue
        const gma = this.unitGroups.get(ma.id), gmb = this.unitGroups.get(mb.id)
        // 组内连线：聚合模型已体现内部工艺关系，不参与绘制、也无须合并
        if (gma && gmb && gma.isGroup && gmb.isGroup && gma.groupId === gmb.groupId) continue
        const keyA = (gma && gma.isGroup) ? gma.groupId : ma.id
        const keyB = (gmb && gmb.isGroup) ? gmb.groupId : mb.id
        const key = keyA + '\u0000' + keyB + '\u0000' + f.material
        const hit = mergedSeen.get(key)
        if (hit) { hit.rate += f.rate || 0; continue }
        const copy = { ...f }
        mergedSeen.set(key, copy)
        merged.push(copy)
      }
      flows = merged
    }
    const lanes = []
    flows.forEach((f) => {
      const a = byId[f.from_unit], b = byId[f.to_unit]
      if (!a || !b) return
      const ga = this.unitGroups.get(a.id)
      const gb = this.unitGroups.get(b.id)
      // 组内连线：聚合模型已体现内部工艺关系，不再单独绘制管道
      if (ga && gb && ga.isGroup && gb.isGroup && ga.groupId === gb.groupId) return
      // 组成员端口统一锚定到组模型中心与组统一 IO 高度
      const ioA = (ga && ga.isGroup) ? ga.ioY : this._ioHeights(a.type, (ga && ga.lift) || 0)
      const ioB = (gb && gb.isGroup) ? gb.ioY : this._ioHeights(b.type, (gb && gb.lift) || 0)
      const rotA = a.rot || 0, rotB = b.rot || 0
      const cosA = Math.cos(rotA), sinA = Math.sin(rotA)
      const cosB = Math.cos(rotB), sinB = Math.sin(rotB)
      const ax = (ga && ga.isGroup) ? ga.centerX : a.x
      const az = (ga && ga.isGroup) ? ga.centerZ : (a.z || 0)
      const bx = (gb && gb.isGroup) ? gb.centerX : b.x
      const bz = (gb && gb.isGroup) ? gb.centerZ : (b.z || 0)
      // 源工艺输出口：PORT_OFFSET 固定位置（模型上的真实出口，角度不可换）
      const pa = new THREE.Vector3(
        ax + ioA.outX * cosA - ioA.outZ * sinA,
        ioA.outY,
        az + ioA.outX * sinA + ioA.outZ * cosA
      )
      // 目标工艺输入口：PORT_OFFSET 固定位置（模型上的真实入口）
      const pb = new THREE.Vector3(
        bx + ioB.inX * cosB - ioB.inZ * sinB,
        ioB.inY,
        bz + ioB.inX * sinB + ioB.inZ * cosB
      )
      lanes.push({ f, pa, pb })
    })

    // 目标口相近（<30 米，通常是共享同一入口）的线路聚为一组：
    // 1) 分配不同水平段高度（垂直分层），避免多线在目标段及可能重叠的水平段相互碰撞；
    // 2) 入口高度水平面上沿 X 轴向错开接入点，多根立管并排不重叠，最后都滑入入口汇聚；
    // 3) 两条等长 L 形（先X后Z / 先Z后X）交替拐角，进一步减少同层路径重叠。
    const CLUSTER_TOL = 30
    const LAYER_GAP = 9   // 每层水平段高度差（米），保证重叠路径在垂直方向明显分开
    const IN_GAP = 7      // 入口高度水平面上接入点的轴向错开间距（米）
    const tgtGroups = []
    for (const L of lanes) {
      let tg = tgtGroups.find((g) => g.pt.distanceToSquared(L.pb) < CLUSTER_TOL * CLUSTER_TOL)
      if (!tg) { tg = { pt: L.pb.clone(), items: [] }; tgtGroups.push(tg) }
      tg.items.push(L)
    }
    for (const g of tgtGroups) {
      g.items.forEach((L, i) => {
        // 对称分层：组内中间层恰为入口高度，其余逐层抬高/降低，彼此高度差 = LAYER_GAP
        L.yLayer = (i - (g.items.length - 1) / 2) * LAYER_GAP
        // 接入点轴向错开量（沿 X 方向，入口高度水平面上滑入）
        L.inOff = (i - (g.items.length - 1) / 2) * IN_GAP
        L.cornerFirst = (i % 2 === 0) ? 'X' : 'Z'
      })
    }

    // 源口相近（<30 米，通常是共享同一出口）的线路：出口位置尽量固定，但可在出口高度
    // 水平面上沿「连线切线的正交主轴」并排错开起点（只改变一个坐标轴，保持正交无斜线），
    // 避免多根立管/管道起点完全重叠
    const SRC_TOL = 30, OUT_GAP = 8
    const srcGroups = []
    for (const L of lanes) {
      let sg = srcGroups.find((g) => g.pt.distanceToSquared(L.pa) < SRC_TOL * SRC_TOL)
      if (!sg) { sg = { pt: L.pa.clone(), items: [] }; srcGroups.push(sg) }
      sg.items.push(L)
    }
    for (const g of srcGroups) {
      g.items.forEach((L, i) => {
        const ddx = L.pb.x - L.pa.x, ddz = L.pb.z - L.pa.z
        const off = (i - (g.items.length - 1) / 2) * OUT_GAP
        // 切线 = (-ddz, ddx)，取绝对值较大的坐标轴作为错开轴（只变一个轴）
        if (Math.abs(ddz) >= Math.abs(ddx)) {
          L.pa = new THREE.Vector3(L.pa.x - Math.sign(ddz) * off, L.pa.y, L.pa.z)
        } else {
          L.pa = new THREE.Vector3(L.pa.x, L.pa.y, L.pa.z + Math.sign(ddx) * off)
        }
      })
    }

    lanes.forEach((L) => {
      const { pa, pb } = L
      // 水平段高度 = 目标入口高度 + 层差（多条线路汇聚/可能交叉时用不同高度区分）
      const H = pb.y + (L.yLayer || 0)
      const V = MAT_VIS[L.f.material] || MAT_VIS._default
      const state = (V.style === 'gas') ? 'gas' : (V.style === 'molten' || V.style === 'liquid') ? 'liquid' : 'solid'

      // 本 flow 的媒介材质：各段复用同一组（避免每段重复创建材质对象）
      const isLightFlow = this.envMode === 'industrial'
      let pipeMat, innerMat, beltMat, railMat, troughMat, liquidMat, ringMat
      if (state === 'gas') {
        // 浅色/深色环境均保持通透明亮的玻璃管质感（提高不透明度与自发光，降低金属度避免暗场发黑）
        pipeMat = mat(V.color, { roughness: 0.35, metalness: 0.2, transparent: true, opacity: isLightFlow ? 0.62 : 0.5, side: THREE.DoubleSide, depthWrite: false, emissive: V.color, emissiveIntensity: isLightFlow ? 0.3 : 0.6 })
        innerMat = new THREE.MeshStandardMaterial({ color: V.color, emissive: V.color, emissiveIntensity: isLightFlow ? 0.8 : 0.6, roughness: 0.5, metalness: 0.1, transparent: true, opacity: isLightFlow ? 0.42 : 0.3, side: THREE.BackSide, depthWrite: false })
        ringMat = mat(isLightFlow ? 0x5a6e80 : V.color, { roughness: 0.35, metalness: 0.4 })
      } else if (state === 'solid') {
        // 传送带提亮（深色环境下原为近黑，现用中灰带蓝，避免暗场发黑）
        beltMat = mat(isLightFlow ? 0x4a515a : 0x39404a, { roughness: 0.85, metalness: 0.15 })
        railMat = mat(isLightFlow ? 0x7d8ba0 : V.color, { roughness: 0.5, metalness: 0.2 })
      } else {
        troughMat = mat(isLightFlow ? 0x8a7a6c : 0x6b5648, { roughness: 0.9 })
        liquidMat = mat(V.color, V.emissive != null
          ? { emissive: V.emissive, emissiveIntensity: V.emi * (isLightFlow ? 1.0 : 0.7), roughness: 0.3, metalness: 0.1 }
          : { roughness: 0.2, transparent: true, opacity: 0.8 })
      }

      // 最短正交路径：源端立管（沿Y）→ 水平段（曼哈顿最短，仅沿X/Z）→ 目标端立管（沿Y）
      // → 入口高度水平面上滑入汇聚。水平段总长 = |dx| + |dz|，即正交最短。
      const wp = [pa.clone()]
      // 源端水平滑出：在出口高度水平面上沿「朝向目标的主轴」滑出 SLIDE_OUT（水平角度自由切换），
      // 再从滑出点立管到水平段高度 H；每段只改变一个坐标轴，绝无斜线。
      const ax0 = pb.x - pa.x, az0 = pb.z - pa.z
      const SLIDE_OUT = 12
      const useX = Math.abs(ax0) >= Math.abs(az0)
      const ex = useX ? pa.x + Math.sign(ax0 || 1) * SLIDE_OUT : pa.x
      const ez = useX ? pa.z : pa.z + Math.sign(az0 || 1) * SLIDE_OUT
      if (Math.abs(ex - pa.x) > 0.5 || Math.abs(ez - pa.z) > 0.5) wp.push(new THREE.Vector3(ex, pa.y, ez))
      // 源端立管：从滑出点把管道高度调整到水平段高度 H（交界处只限制高度）
      if (Math.abs(H - pa.y) > 0.5) wp.push(new THREE.Vector3(ex, H, ez))
      // 目标侧接入点：入口高度水平面上沿 X 轴向错开的位置（其正上方 H 处为水平段终点）
      const jxB = pb.x + (L.inOff || 0), jzB = pb.z
      const ax = jxB - ex, az = jzB - ez
      if (Math.abs(az) < 0.5) {
        // 同一排：直接沿 X
        wp.push(new THREE.Vector3(jxB, H, ez))
      } else if (Math.abs(ax) < 0.5) {
        // 同一列：直接沿 Z
        wp.push(new THREE.Vector3(ex, H, jzB))
      } else if (L.cornerFirst === 'Z') {
        // L形：先沿 Z 后沿 X（与先X后Z等长，交替使用减少同层重叠）
        wp.push(new THREE.Vector3(ex, H, jzB))
        wp.push(new THREE.Vector3(jxB, H, jzB))
      } else {
        // L形：先沿 X 后沿 Z
        wp.push(new THREE.Vector3(jxB, H, ez))
        wp.push(new THREE.Vector3(jxB, H, jzB))
      }
      // 目标端立管：水平段高度 H 弯折到入口高度（在目标入口处弯折）
      if (Math.abs(H - pb.y) > 0.5) wp.push(new THREE.Vector3(jxB, pb.y, jzB))
      // 入口高度水平面上滑入汇聚：水平接入目标入口
      if (Math.abs(jxB - pb.x) > 0.5 || Math.abs(jzB - pb.z) > 0.5) wp.push(pb.clone())

        // 折线路径预计算：载运体沿分段直线运动，与传送带/流槽/管道的逐段直线构建完全一致，
        // 避免 CatmullRom 在弯头处切角导致物料悬浮于带面或穿入带面（复用临时向量，总长顺带累加）
        const segLens = [], yDirs = []
        let totalLen = 0
        for (let si = 0; si < wp.length - 1; si++) {
          _v1.subVectors(wp[si + 1], wp[si])
          const sLen = _v1.length()
          segLens.push(sLen)
          totalLen += sLen
          _v2.copy(_v1).normalize()
          _v3.crossVectors(_v2, VEC_UP)
          if (_v3.lengthSq() < 1e-6) _v3.crossVectors(_v2, VEC_X)
          _v3.normalize()
          yDirs.push(_v5.crossVectors(_v3, _v2).normalize().clone())
        }

        // --- 分段直线运输媒介（管道/传送带/流槽，根据物料种类自动选择）---
        // 每段沿两个路径点之间的直线构建，3D对齐（含Y坡度），确保载运体始终在媒介内。
        // 各段共享单位几何体（Mesh.scale 适配长度）+ 本 flow 复用材质，避免每段新建几何体/材质。
        for (let si = 0; si < wp.length - 1; si++) {
          const segFrom = wp[si], segTo = wp[si + 1]
          _v1.subVectors(segTo, segFrom)
          const segLen = _v1.length()
          if (segLen < 1.0) continue
          _v2.addVectors(segFrom, segTo).multiplyScalar(0.5)   // segMid
          _v3.copy(_v1).normalize()                            // segDir
          // 构建3D对齐基矩阵：local X 对齐 segDir，local Y 尽量朝上
          _v4.crossVectors(_v3, VEC_UP)                        // zDir
          // 若 segDir 近乎垂直（平行于 up），交叉积接近零，换用备用方向
          if (_v4.lengthSq() < 1e-6) _v4.crossVectors(_v3, VEC_X)
          _v4.normalize()
          _v5.crossVectors(_v4, _v3).normalize()               // yDir
          _m4.makeBasis(_v3, _v5, _v4)

          if (state === 'gas') {
            // 气体：半透明管道（CylinderGeometry 沿 local Y 轴，需映射到 segDir）
            _q.setFromUnitVectors(VEC_UP, _v3)
            const segGrp = new THREE.Group()
            segGrp.position.copy(_v2)
            segGrp.setRotationFromQuaternion(_q)
            const pMesh = new THREE.Mesh(GEO_UNIT_CYL, pipeMat)
            pMesh.scale.set(PIPE_R, segLen, PIPE_R)
            segGrp.add(pMesh)
            // 内壁辉光
            const iMesh = new THREE.Mesh(GEO_UNIT_CYL_IN, innerMat)
            iMesh.scale.set(PIPE_R - 0.3, segLen, PIPE_R - 0.3)
            segGrp.add(iMesh)
            this._flowGroup.add(segGrp)
          } else if (state === 'solid') {
            // 固体：宽传送带（BoxGeometry，local X 沿 segDir，local Y 保持朝上）
            const segGrp = new THREE.Group()
            segGrp.position.copy(_v2)
            segGrp.setRotationFromMatrix(_m4)
            // 带面（local: 中心在原点，X=segLen, Y=0.9高, Z=5.0宽）
            const bMesh = new THREE.Mesh(GEO_UNIT_BOX, beltMat)
            bMesh.scale.set(segLen, 0.9, 5.0)
            segGrp.add(bMesh)
            // 侧轨（物料色标识，local Y+0.6, local Z±2.7）
            for (const s of [-1, 1]) {
              const rail = new THREE.Mesh(GEO_UNIT_BOX, railMat)
              rail.scale.set(segLen, 0.6, 0.5)
              rail.position.set(0, 0.6, s * 2.7)
              segGrp.add(rail)
            }
            this._flowGroup.add(segGrp)
          } else {
            // 液体/熔体：流槽（耐材U型槽 + 液面，local X 沿 segDir）
            const segGrp = new THREE.Group()
            segGrp.position.copy(_v2)
            segGrp.setRotationFromMatrix(_m4)
            // 槽底
            const bMesh = new THREE.Mesh(GEO_UNIT_BOX, troughMat)
            bMesh.scale.set(segLen, 0.8, 4.0)
            segGrp.add(bMesh)
            // 侧壁（local Y+0.8, local Z±2.1）
            for (const s of [-1, 1]) {
              const wall = new THREE.Mesh(GEO_UNIT_BOX, troughMat)
              wall.scale.set(segLen, 1.6, 0.4)
              wall.position.set(0, 0.8, s * 2.1)
              segGrp.add(wall)
            }
            // 液面（local Y+0.75）
            const lMesh = new THREE.Mesh(GEO_UNIT_BOX, liquidMat)
            lMesh.scale.set(segLen, 0.6, 3.4)
            lMesh.position.set(0, 0.75, 0)
            segGrp.add(lMesh)
            this._flowGroup.add(segGrp)
          }
        }

        // 气体管道法兰环（分布在各段端点和转折点，共享单位圆环几何体）
        if (state === 'gas') {
          for (let pi = 0; pi < wp.length; pi++) {
            const pt = wp[pi]
            const fring = new THREE.Mesh(GEO_TORUS, ringMat)
            fring.position.copy(pt)
            this._flowGroup.add(fring)
            // 转折点（非端点）加球形弯头连接件：让立管↔水平段转角圆润、不再是生硬直角
            if (pi > 0 && pi < wp.length - 1) {
              const joint = new THREE.Mesh(GEO_UNIT_ICO, ringMat)
              joint.scale.setScalar(PIPE_R * 1.15)
              joint.position.copy(pt)
              this._flowGroup.add(joint)
            }
          }
        } else {
          // 传送带/流槽：在转折点加转角墩座，视觉上承托物料转向
          for (let pi = 1; pi < wp.length - 1; pi++) {
            const pt = wp[pi]
            const pad = new THREE.Mesh(GEO_UNIT_BOX, state === 'solid' ? beltMat : troughMat)
            pad.scale.set(8.5, 2.2, 7.0)
            pad.position.set(pt.x, pt.y, pt.z)
            this._flowGroup.add(pad)
          }
        }

        // --- 物料载运体 ---
        const carrier = this._makeMaterialCarrier(L.f.material)
        this._flowGroup.add(carrier.obj)

        // 速度与标签
        const rate = L.f.rate || 0
        const norm = Math.min(rate, 14000) / 14000
        const vm = (0.6 + norm * 2.6).toFixed(1)
        const speed = 0.09 + norm * 0.20
        const name = (MATERIAL_MAP[L.f.material] && MATERIAL_MAP[L.f.material].name) || L.f.material
        const mCarbon = (MATERIAL_MAP[L.f.material] && MATERIAL_MAP[L.f.material].carbon) || 0
        const flowCo2 = rate * mCarbon
        const label = this._makeFlowLabel(name, V.color, rate, flowCo2, vm)
        // 标签置于折线中点正上方（与传送带/管道/流槽位置一致）
        let hDist = totalLen * 0.5
        let hsi = 0
        while (hsi < segLens.length - 1 && hDist > segLens[hsi]) { hDist -= segLens[hsi]; hsi++ }
        const hu = segLens[hsi] > 0 ? Math.min(hDist / segLens[hsi], 1) : 0
        const midPt = new THREE.Vector3().lerpVectors(wp[hsi], wp[hsi + 1], hu)
        label.position.set(midPt.x, midPt.y + 5.5, midPt.z)
        label.userData = { kind: 'flow', flowId: L.f.id }
        this._flowGroup.add(label)

        // 载运体垂直偏移：根据运输媒介类型决定
        // gas 管道中心=0 | solid 传送带面=0.45 + 载运体半径0.35=0.8 | liquid 流槽液面=0.75
        const carrierOffset = state === 'gas' ? 0 : state === 'solid' ? 0.8 : 0.75
        this.flows.push({
          totalLen, carrierOffset, flowId: L.f.id,
          obj: carrier.obj, mat: carrier.mat, emi: carrier.emi, anim: carrier.anim,
          label, t: Math.random(), phase: Math.random() * 6.28, speed,
          from: pa.clone(), to: pb.clone(),              // 连线端点，用于聚焦定位
          y: midPt.y, labelY: midPt.y + 5.5,             // 折线中点Y 及 标签世界Y
          wp, segLens, yDirs,                            // 折线路径（载运体沿折线移动，紧贴媒介）
        })
      })
  }

  // ---------------- 更新 ----------------
  // 汇总小组成员在某结果列表中的能耗/碳排（组标签统一显示组内汇总值）
  _sumGroupRes(g, list) {
    let co2 = 0, en = 0
    for (const id of g.memberIds) {
      const r = list.find((x) => x.id === id)
      if (r) { co2 += r.co2_total || 0; en += r.energy_total || 0 }
    }
    return { co2, en }
  }

  // 刷新所有组标签的汇总数值（组聚合模型在数字孪生中只显示一个汇总标签）
  _refreshGroupLabels(totalCo2) {
    this.unitGroups.forEach((g) => {
      if (!g || !g.isGroup || !g.labelObj) return
      const s = this._sumGroupRes(g, (this.results && this.results.units) || [])
      const share = totalCo2 ? s.co2 / totalCo2 : 0
      g.share = share
      g.shareCss = emissionCss(share)
      this._drawLabel(g.labelObj, s.co2, s.en, undefined, g.shareCss)
    })
  }

  updateHeat(results) {
    if (!results || !results.units) return
    this.results = results
    const totalCo2 = results.units.reduce((s, u) => s + (u.co2_total || 0), 0) || 1
    results.units.forEach((r) => {
      const g = this.unitGroups.get(r.id)
      if (!g || g.isGroup) return
      const share = (r.co2_total || 0) / totalCo2
      g.share = share
      g.shareCss = emissionCss(share)
      const c = emissionColor(share)
      // (悬浮场景无碳环/足迹，仅更新标签与热度层)
      if (g.labelObj) this._drawLabel(g.labelObj, r.co2_total, r.energy_total, undefined, g.shareCss)
      // 示意模式：热量分层随实时遥测刷新热度强度
      if (g.heatLayers) g.heatLayers.update(r)
    })
    this._refreshGroupLabels(totalCo2)
  }

  updateLive(live) {
    if (!live || !live.units) return
    live.units.forEach((u) => {
      const g = this.unitGroups.get(u.id)
      if (g && !g.isGroup && g.labelObj) this._drawLabel(g.labelObj, u.co2_total, u.energy_total, undefined, g.shareCss)
    })
    this._refreshGroupLabels()
  }

  // 更新工序标签中的策略优化后碳排（优化前 → 优化后 对比）
  updateStrategyDeltas(strategyResult) {
    if (!strategyResult || !strategyResult.units) return
    strategyResult.units.forEach((su) => {
      const g = this.unitGroups.get(su.id)
      if (!g || !g.labelObj || g.isGroup) return
      // 从 resultForView/baseline 取原始值作为对比
      const base = this.results ? this.results.units.find(r => r.id === su.id) : null
      if (base) {
        g.labelObj.strategyCo2 = su.co2_total
        g.labelObj.co2 = base.co2_total
        g.labelObj.energy = base.energy_total
        this._drawLabel(g.labelObj, base.co2_total, base.energy_total, undefined, g.shareCss)
      }
    })
    // 组汇总：策略后 = 组内成员策略值之和，策略前 = 组内成员基线值之和
    const baseUnits = this.results ? this.results.units : []
    this.unitGroups.forEach((g) => {
      if (!g || !g.isGroup || !g.labelObj) return
      let sco2 = 0
      const bases = []
      for (const id of g.memberIds) {
        const s = strategyResult.units.find((x) => x.id === id)
        if (s) sco2 += s.co2_total || 0
        const b = baseUnits.find((x) => x.id === id)
        if (b) bases.push(b)
      }
      if (!bases.length) return
      const bco2 = bases.reduce((s, b) => s + (b.co2_total || 0), 0)
      const ben = bases.reduce((s, b) => s + (b.energy_total || 0), 0)
      g.labelObj.strategyCo2 = sco2
      g.labelObj.co2 = bco2
      g.labelObj.energy = ben
      this._drawLabel(g.labelObj, bco2, ben, undefined, g.shareCss)
    })
  }

  // 清除所有工序标签上的策略对比数据

  setSelected(id) {
    this._setFocus(id)
  }

  // 聚焦/选中某工序时：点亮选中环，并把该工序的唯一标签切到高亮态（放大 + 亮描边）
  _setFocus(id) {
    this.focusedId = id || null
    this.unitGroups.forEach((g, key) => {
      // 普通单元按 key 命中；小组整体：聚焦 gid 时组内任一条目都点亮同一个小组的选中环与组标签
      let on = key === this.focusedId
      if (!on && g.isGroup && g.groupId === this.focusedId) on = true
      if (g.ring) g.ring.material.opacity = on ? 0.95 : 0
      const lo = g.labelObj
      if (!lo || lo.focused === on) return
      lo.focused = on
      this._drawLabel(lo)
    })
  }

  setAutoRotate(v) { this.autoRotate = v; this.controls.autoRotate = v; this.controls.autoRotateSpeed = 1.0 }

  // 亮度调节：映射到 ACESFilmic toneMappingExposure（范围 0.3 ~ 2.5）
  setBrightness(b) { this.renderer.toneMappingExposure = b; this._hasUserBrightness = true }

  resetView() { this.playResetOrbit() }

  // 计算「俯瞰全厂」相机机位与视点：基于实际工序包围盒（而非固定厂界）
  _frameAll() {
    const cam = this.camera
    const gs = !!this.groupScene
    // 小组子场景：成员放大后更高（最高约 170），取景留白更小、高度上限更高
    let minX = -PARK.halfX, maxX = PARK.halfX, minZ = -PARK.halfZ, maxZ = PARK.halfZ, maxY = gs ? 170 : 60
    const us = this._unitWorld
    if (us && us.length) {
      minX = Infinity; maxX = -Infinity; minZ = Infinity; maxZ = -Infinity
      for (const u of us) {
        minX = Math.min(minX, u.x); maxX = Math.max(maxX, u.x)
        minZ = Math.min(minZ, u.z); maxZ = Math.max(maxZ, u.z)
      }
      const padX = gs ? 34 : 72, padZ = gs ? 28 : 58
      minX -= padX; maxX += padX; minZ -= padZ; maxZ += padZ
      maxY = gs ? 170 : 76
    }
    const cx = (minX + maxX) / 2
    const cz = (minZ + maxZ) / 2
    const extX = (maxX - minX) / 2
    const extZ = (maxZ - minZ) / 2
    const vfov = (cam.fov || 48) * Math.PI / 180
    const aspect = cam.aspect || (16 / 9)
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect)
    const fit = (half, fov) => (half / Math.tan(fov / 2)) * 1.28
    let dist = Math.max(fit(extX, hfov), fit(extZ, vfov), fit(maxY * 0.42, vfov))
    dist = Math.max(dist, gs ? 120 : 250)
    const elev = THREE.MathUtils.degToRad(34)
    const dir = new THREE.Vector3(0, Math.sin(elev), Math.cos(elev)).normalize()
    const tgt = new THREE.Vector3(cx, maxY * 0.12, cz)
    const pos = tgt.clone().add(dir.multiplyScalar(dist))
    return { pos, tgt, dist }
  }

  // 重置视角：不绕厂区旋转一周，直接平滑过渡到最终俯瞰机位
  playResetOrbit() {
    this._focus = null
    this._intro = null
    const f = this._frameAll()
    const center = f.tgt.clone()
    const gs = !!this.groupScene

    // 最终机位：使用经调试确定的固定相机参数（用户手动调整到满意视角）。
    // 顶层场景直接用该组坐标；小组子场景仍用角度计算避免错位。
    let resetTgt, resetPos
    if (!gs) {
      // 调试确定的合适机位：左后方、低位、俯视流程
      resetPos = new THREE.Vector3(-1317.7, 176.1, 743.9)
      resetTgt = new THREE.Vector3(-360.1, 130.3, -451.0)
    } else {
      // 小组子场景：沿用角度计算
      const elev = THREE.MathUtils.degToRad(30)
      const azim = THREE.MathUtils.degToRad(75)
      const resetDist = Math.max(f.dist * 0.6, 70)
      const dir45 = new THREE.Vector3(
        -Math.cos(azim) * Math.cos(elev),
        Math.sin(elev),
        Math.cos(azim) * Math.cos(elev),
      ).normalize()
      const bMaxY = 170
      resetTgt = new THREE.Vector3(center.x, bMaxY * 0.3, center.z)
      resetPos = resetTgt.clone().add(dir45.multiplyScalar(resetDist))
    }

    this._tweenCamera(resetPos, resetTgt, 1.2)
  }

  // 镜头从园区高空斜俯视逐步推入「全景俯瞰」视角
  playIntro() {
    this._focus = null
    this.controls.enabled = false
    const f = this._frameAll()
    const cx = f.tgt.x
    const dist = f.dist
    const startPos = new THREE.Vector3(cx, dist * 0.72 + 60, dist * 1.2)
    const startTgt = new THREE.Vector3(cx, 30, f.tgt.z)
    this._intro = { fromPos: startPos, toPos: f.pos, fromTgt: startTgt, toTgt: f.tgt, t: 0, dur: 2.6 }
    this.camera.position.copy(startPos)
    this.controls.target.copy(startTgt)
    this.camera.lookAt(startTgt)
  }
  _stepIntro(dt) {
    const f = this._intro
    f.t += dt / f.dur
    const k = Math.min(1, f.t)
    const e = k < 0.5 ? 4 * k * k * k : 1 - Math.pow(-2 * k + 2, 3) / 2
    this.camera.position.lerpVectors(f.fromPos, f.toPos, e)
    this.controls.target.lerpVectors(f.fromTgt, f.toTgt, e)
    this.camera.lookAt(this.controls.target)
    if (k >= 1) { this._intro = null; this.controls.enabled = true; this.controls.update() }
  }

  _tweenCamera(toPos, toTgt, dur = 0.9) {
    this._focus = {
      fromPos: this.camera.position.clone(),
      toPos: toPos.clone(),
      fromTgt: this.controls.target.clone(),
      toTgt: toTgt.clone(),
      t: 0, dur,
    }
    this.controls.enabled = false
  }

  // 视角工具条：以工序本体为焦点切换相机（聚焦 / 正视 / 侧视 / 俯视 / 全景）
  viewUnit(id, mode) {
    const g = this.unitGroups.get(id)
    if (!g) return
    const v = new THREE.Vector3()
    g.group.getWorldPosition(v)
    const gs = g.group.scale ? g.group.scale.y : UNIT_SCALE
    const midY = v.y + (g.lift || 0) * gs + Math.min((g.topY || 8) * UNIT_SCALE * 0.5, 22)
    // 工序前侧（+Z 朝向主干道/相机），与信息塔原位置一致，作为视角锚点
    const S = new THREE.Vector3(v.x, midY, v.z + 26)
    if (mode === 'overview') {
      const f = this._frameAll()
      this._tweenCamera(f.pos, f.tgt, 1.2)
      return
    }
    if (mode === 'top') {
      this._tweenCamera(new THREE.Vector3(S.x, S.y + 100, S.z + 0.01), S, 0.9)
      return
    }
    if (mode === 'side') {
      this._tweenCamera(new THREE.Vector3(S.x + 50, S.y + 8, S.z + 25), S, 0.9)
      return
    }
    if (mode === 'front') {
      this._tweenCamera(new THREE.Vector3(S.x, S.y + 8, S.z + 55), S, 0.9)
      return
    }
    // 聚焦：框住整台设备（适度距离），而非贴脸看信息屏
    this.focusUnit(id)
  }

  focusOn(target, focusDist = 45) {
    const fromPos = this.camera.position.clone()
    const fromTgt = this.controls.target.clone()
    const dir = fromPos.clone().sub(fromTgt)
    if (dir.lengthSq() < 1e-4) dir.set(0, 0.5, 1)
    dir.normalize()
    const toPos = target.clone().add(dir.multiplyScalar(focusDist))
    toPos.y = Math.max(toPos.y, target.y + 16)
    this._focus = {
      fromPos, toPos,
      fromTgt, toTgt: target.clone(),
      t: 0, dur: 0.7,
    }
    this.controls.enabled = false
  }

  focusUnit(id) {
    const g = this.unitGroups.get(id)
    if (!g) return
    this.focusedFlowId = null               // 切到工序时清除管道聚焦
    const body = g.body || g.group
    g.group.updateWorldMatrix(true, true)
    const box = new THREE.Box3().setFromObject(body)
    const center = box.getCenter(new THREE.Vector3())
    const size = box.getSize(new THREE.Vector3())
    const hx = Math.max(size.x, size.z) * 0.5
    const hy = size.y * 0.5
    const cam = this.camera
    const aspect = cam.aspect || 1
    const vfov = (cam.fov || 48) * Math.PI / 180
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect)
    const fit = (half, fov) => (half / Math.tan(fov / 2)) * 1.14
    let dist = Math.max(fit(hx, hfov), fit(hy, vfov)) * 2.8 + 85
    dist = Math.min(Math.max(dist, 90), 260)
    // 聚焦目标设为标签位置（工序上方），而非工艺几何体中心
    const labelWorld = new THREE.Vector3(0, (g.topY || 0) + 4 + (g.lift || 0), 0)
    g.group.localToWorld(labelWorld)
    this.focusOn(labelWorld, dist)
    this._setFocus(id)
  }

  // 将相机平滑过渡到「当前场景全景」机位（基于实际渲染单元的包围盒）。
  // 3D 小组子场景进入时使用：适配小组布局；返回顶层时由 resetView 播放全景动画。
  focusScene() {
    const f = this._frameAll()
    if (!f) return
    this._focus = null
    this._intro = null
    this.controls.enabled = false
    this._tweenCamera(f.pos, f.tgt, 0.9)
  }

  // 点击小组标签/底座/成员模型 → 相机平滑聚焦到整组（与工序聚焦一致，框住组聚合模型）
  focusGroup(gid) {
    const g = this.groupModels.get(gid)
    if (!g) return
    this.focusedFlowId = null               // 切到小组时清除管道聚焦
    const body = g.body || g.group
    g.group.updateWorldMatrix(true, true)
    const box = new THREE.Box3().setFromObject(body)
    const size = box.getSize(new THREE.Vector3())
    const hx = Math.max(size.x, size.z) * 0.5
    const hy = size.y * 0.5
    const cam = this.camera
    const aspect = cam.aspect || 1
    const vfov = (cam.fov || 48) * Math.PI / 180
    const hfov = 2 * Math.atan(Math.tan(vfov / 2) * aspect)
    const fit = (half, fov) => (half / Math.tan(fov / 2)) * 1.14
    let dist = Math.max(fit(hx, hfov), fit(hy, vfov)) * 2.8 + 85
    dist = Math.min(Math.max(dist, 90), 260)
    // 聚焦到组标签位置（组顶上方），与工序聚焦行为一致
    const labelWorld = new THREE.Vector3(0, (g.topY || 0) + 4, 0)
    g.group.localToWorld(labelWorld)
    this.focusOn(labelWorld, dist)
    this._setFocus(gid)
  }

  // 设备聚焦：优先定位「设备本体」位置。
  // 可调设备（工辅设备）在 3D 场景中以工辅工艺实例 / 小组聚合模型呈现，传入的合成 id 形式：
  //   - unitId::auxType   （工辅实例自身，或「绑定工序实例::工辅类型」视角）
  //   - tpl::unitType::devType（非部署工艺的模板设备）
  // 相机应聚焦到该工辅类型在场景中的实例本体，而不是其绑定工序的整体位置。
  focusDevice(id) {
    const grp = this.deviceMap.get(id)
    if (grp) {
      const v = new THREE.Vector3()
      grp.getWorldPosition(v)
      this.focusOn(v, 30)
      return
    }
    const parts = id.split('::')
    if (parts.length >= 2) {
      // 非部署工艺模板设备：聚焦该工艺类型在场景中的首个已部署实例
      if (parts[0] === 'tpl' && parts.length === 3) {
        const g = this._findUnitByType(parts[1])
        if (g) this.focusUnit(g.id)
        return
      }
      const unitId = parts[0]
      const auxType = parts[1]
      // unitId 本身就是该工辅类型的实例（未连线绑定路径）→ 直接聚焦该实例
      const gu = this.unitGroups.get(unitId)
      if (gu && gu.unitType === auxType) { this.focusUnit(unitId); return }
      // 否则聚焦该工辅类型在场景中的实例本体（设备实际所在位置）
      const g = this._findUnitByType(auxType)
      if (g) { this.focusUnit(g.id); return }
      // 兜底：聚焦绑定工序实例
      this.focusUnit(unitId)
      return
    }
    this.focusUnit(id)
  }

  // 查找场景中指定工艺类型的首个已部署实例（含小组聚合模型：成员包含该类型的组模型）
  _findUnitByType(type) {
    for (const [uid, g] of this.unitGroups) {
      if (g.unitType === type) return { id: uid }
      if (g.memberUnits && g.memberUnits.some((u) => u.type === type)) return { id: uid }
    }
    return null
  }

  // 点击工艺间连接标签 → 将相机平滑聚焦到标签位置（连线中点上方）
  focusFlow(id) {
    const fl = (this.flows || []).find((x) => x.flowId === id)
    if (!fl) return
    this.focusedFlowId = id
    const mid = fl.from.clone().add(fl.to).multiplyScalar(0.5)
    mid.y = fl.labelY || fl.y             // 聚焦到标签高度，可以更好看到标签内容
    const len = fl.to.clone().sub(fl.from).length()
    const dist = Math.max(45, Math.min(len * 0.55 + 42, 120))
    this.focusOn(mid, dist)
  }

  _stepFocus(dt) {
    const f = this._focus
    f.t += dt / f.dur
    const k = Math.min(1, f.t)
    const e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2
    this.camera.position.lerpVectors(f.fromPos, f.toPos, e)
    this.controls.target.lerpVectors(f.fromTgt, f.toTgt, e)
    this.camera.lookAt(this.controls.target)
    if (k >= 1) { this._focus = null; this.controls.enabled = true; this.focusedFlowId = null }
  }

  // ---------------- 动画 ----------------
  _animate() {
    if (this._paused) { this._raf = null; return }
    this._raf = requestAnimationFrame(this._animate)
    const now = performance.now()
    if (this._lastFrame == null) this._lastFrame = now
    const elapsed = now - this._lastFrame
    // 拖拽/聚焦/漫游/入场动画期间全帧率（≈60fps）保证画面流畅锐利；静止时 30fps 降低功耗
    const active = this._interacting || this._intro || this._focus
    if (elapsed < (active ? 16 : 33)) return
    const dt = Math.min(0.05, elapsed / 1000)
    this._lastFrame = now
    const t = now / 1000

    this.unitGroups.forEach((g) => {
      const phase = g.group.position.x
      if (g.flame && g.flame.userData && g.flame.userData.cone) {
        const fk = 0.72 + 0.36 * Math.sin(t * 11 + phase) + 0.12 * Math.sin(t * 19 + phase * 1.7)
        g.flame.userData.cone.scale.set(0.9 + 0.1 * Math.sin(t * 13 + phase), fk, 0.9 + 0.1 * Math.cos(t * 12 + phase))
        g.flame.userData.cone.material.opacity = 0.55 + 0.3 * Math.abs(Math.sin(t * 9 + phase))
        g.flame.userData.inner.scale.set(1, 0.82 + 0.32 * Math.sin(t * 15 + phase), 1)
      }
      if (g.rollers) g.rollers.forEach((rg, i) => { rg.rotation.z -= dt * (1.6 + i * 0.05) })
      if (g.slab) {
        g.slabT = (g.slabT + dt * 0.35) % 1
        g.slab.position.x = -12 + g.slabT * 24
        const heatK = 0.7 + 0.3 * Math.sin(t * 4 + phase)
        g.slab.material.emissiveIntensity = 1.1 + heatK * 0.6
      }
      // LF精炼氩气底吹气泡（上升+膨胀+消失→循环）
      if (g.arBubbles) {
        const bubs = g.arBubbles
        for (let i = 0; i < bubs.length; i++) {
          const b = bubs[i]
          const bphase = ((t * 0.4 + i * 1.5) % 4) // 4秒循环
          b.visible = bphase < 3.0 // 3秒可见
          if (b.visible) {
            b.position.y = 0.5 + bphase * 1.8 // 从罐底上升到钢水表面
            const s = 0.15 + bphase * 0.3
            b.scale.setScalar(s)
            b.material.opacity = 0.35 * (1 - bphase / 3.0) * (0.7 + 0.3 * Math.sin(bphase * 5))
          }
        }
      }
      // 电炉电极升降 + 电弧脉动（模拟熔化→精炼周期）
      if (g.furnaceElectrodes) {
        const electrodes = g.furnaceElectrodes
        for (let i = 0; i < electrodes.length; i++) {
          const e = electrodes[i]
          // 电极升降（微幅上下，模拟自动调节弧长）
          const elecOffset = 0.4 * Math.sin(t * 2.5 + i * 2.1) + 0.25 * Math.sin(t * 4.2 + i)
          e.group.position.y = e.baseUY + elecOffset
          // 电弧尖端发光脉动（模拟弧光）
          if (e.tip && e.tip.material) {
            const arcPulse = 1.6 + 0.7 * Math.sin(t * 9 + i * 3) + 0.3 * Math.sin(t * 17 + i)
            e.tip.material.emissiveIntensity = 2.5 * arcPulse
            // 颜色在蓝白之间交替（复用临时 Color，避免每帧分配）
            const hue = 0.55 + 0.04 * Math.sin(t * 6 + i)
            const arcCol = this._arcTmpC || (this._arcTmpC = new THREE.Color())
            arcCol.setHSL(hue, 0.9, 0.7 + 0.2 * Math.sin(t * 11 + i))
            e.tip.material.emissive = arcCol
          }
          // 夹持器微震
          if (e.clamp) {
            e.clamp.position.x += 0.02 * Math.sin(t * 20 + i) * dt
          }
        }
      }
      // 转炉倾动摇炉：模拟装料→吹炼→出钢循环（周期约 18 秒）
      if (g.converterPivot) {
        // 主倾动：正弦摆动模拟吹炼周期，[-0.35, +0.45] rad 范围
        const tiltCycle = Math.sin(t * 0.35 + phase * 0.02) // 慢周期
        const targetTilt = tiltCycle * 0.4
        g.converterTilt += (targetTilt - g.converterTilt) * dt * 1.1 // 平滑跟随
        g.converterPivot.rotation.x = g.converterTilt // 转炉绕耳轴倾动

        // 物料随动：钢水发射强度脉动 + 表面涟漪旋转
        if (g.converterMelt) {
          const meltPulse = 1.0 + 0.18 * Math.sin(t * 7 + phase) + 0.08 * Math.sin(t * 13 + phase * 1.3)
          g.converterMelt.material.emissiveIntensity = 1.2 * meltPulse
        }
        if (g.converterMeltRipples) {
          for (let i = 0; i < g.converterMeltRipples.length; i++) {
            const r = g.converterMeltRipples[i]
            r.rotation.z += dt * (0.4 + i * 0.15)
            r.rotation.x += dt * 0.15
            const rp = 0.6 + 0.2 * Math.sin(t * (9 + i) + phase)
            r.material.emissiveIntensity = 0.7 * rp
          }
        }
      }
      if (g.glow && g.glowMats) {
        const gk = 0.78 + 0.22 * Math.sin(t * 6.5 + phase) + 0.08 * Math.sin(t * 13 + phase * 1.3)
        g.glow.intensity = (g.glowBase || 2) * gk
        const emInt = 0.16 * gk
        for (const m of g.glowMats) {
          if ('emissive' in m) { m.emissive.setHex(0xff5a1e); m.emissiveIntensity = emInt }
        }
      }
      if (g.plume) this._stepParticles(g.plume, dt, 5, true)
      if (g.heatLayers) g.heatLayers.tick(t, dt)
      // 连铸铸坯穿行动画（沿水平矫直段 -1.8→6.2 循环推移）
      if (g.casterStrand) {
        const castT = (t * 0.22 + phase * 0.01) % 1
        g.casterStrand.position.x = -1.8 + castT * 8.0
        const castGlow = 0.9 + 0.3 * Math.sin(t * 5 + phase)
        g.casterStrand.material.emissiveIntensity = 1.2 + castGlow * 0.4
        g.casterStrand.material.emissive.setHex(castT > 0.7 ? 0xff8822 : 0xff4400)
      }
      // 球团造球盘：旋转 + 生球成形
      if (g.pelletDiscs) {
        g.pelletDiscs.forEach((disc, di) => {
          disc.rotation.y += dt * (0.8 + di * 0.15)
          disc.children.forEach(c => {
            if (c.material && c.material.emissiveIntensity !== undefined)
              c.material.emissiveIntensity = 0.3 + 0.15 * Math.sin(t * 3 + di)
          })
        })
      }
      // 加热炉内钢坯：温度脉动发光
      if (g.internalSlabs) {
        g.internalSlabs.forEach((slab, si) => {
          const puls = 0.7 + 0.3 * Math.sin(t * 4.5 + si * 2 + phase)
          slab.material.emissiveIntensity = (0.6 + si * 0.15) * puls
        })
      }
      // === 高炉(BlastFurnace)专属动画 ===
      // 排烟粒子上升（从炉顶uptake管口冒出荒煤气/粉尘）
      if (g._bfSmoke) this._stepParticles(g._bfSmoke, dt, 6, true)
      // 风口火焰脉动（tuyere flame flicker）
      if (g._tuyereFlares) {
        g._tuyereFlares.forEach((flare, fi) => {
          const fiPulse = 0.6 + 0.4 * Math.abs(Math.sin(t * 12 + fi * 0.7 + phase))
          flare.material.emissiveIntensity = 1.5 * fiPulse
          flare.material.opacity = 0.4 + 0.3 * fiPulse
          flare.scale.setScalar(0.8 + 0.4 * fiPulse)
        })
      }
      // 炉缸铁水池脉动（液态铁水涌动光泽）
      if (g._ironPoolMat) {
        g._ironPoolMat.emissiveIntensity = 0.75 + 0.25 * Math.abs(Math.sin(t * 5 + phase))
      }
      // 炉渣层脉动
      if (g._slagLayerMat) {
        g._slagLayerMat.emissiveIntensity = 0.15 + 0.1 * Math.abs(Math.sin(t * 6 + phase * 1.2))
      }
      // 出铁口铁水流脉动
      if (g._ironStreamMat) {
        g._ironStreamMat.emissiveIntensity = 1.1 + 0.4 * Math.abs(Math.sin(t * 8 + phase))
      }
      // 炉料整体缓慢下沉（模拟炉料下降过程 — 慢周期循环）
      if (g._burdenLayers) {
        const descentSpeed = 0.15 // 下降速度
        g._burdenLayers.position.y = (g._burdenLayers.position.y - dt * descentSpeed + 40) % 40 - 40
      }
      // 料车上下运动（skip car — 装料→提升→卸料→返回）
      if (g._skipCar) {
        const skipCycle = (t * 0.22 + phase * 0.01) % 1
        const skipY = skipCycle < 0.45
          ? g._skipBaseY + (skipCycle / 0.45) * 28 // 上行
          : g._skipBaseY + 28 - ((skipCycle - 0.45) / 0.55) * 28 // 下行
        g._skipCar.position.y = skipY
        g._skipCar.position.z = 3 + Math.sin(skipCycle * Math.PI) * 1.5
      }
      // === 电炉(Furnace/EAF)专属动画 ===
      // 电极电弧闪烁（电弧炉三相电极）
      if (g._eafArcs) {
        g._eafArcs.forEach((arc, ai) => {
          const arcFlicker = 0.4 + 0.6 * Math.abs(Math.sin(t * 18 + ai * 1.2 + phase * 0.7))
          arc.material.emissiveIntensity = 2.5 * arcFlicker
          arc.scale.setScalar(0.6 + 0.5 * arcFlicker)
        })
      }
      // 电炉熔池脉动
      if (g._eafPoolMat) {
        g._eafPoolMat.emissiveIntensity = 0.7 + 0.3 * Math.abs(Math.sin(t * 6 + phase))
      }
      // 电炉渣层脉动
      if (g._eafSlagMat) {
        g._eafSlagMat.emissiveIntensity = 0.2 + 0.15 * Math.abs(Math.sin(t * 7 + phase))
      }
      // === 转炉(Converter)专属动画 ===
      // 氧枪喷吹火花（高压氧射入钢水表面）
      if (g._convSparks) {
        g._convSparks.forEach((spark, si) => {
          const sparkFlicker = 0.3 + 0.7 * Math.abs(Math.sin(t * 22 + si * 2 + phase))
          spark.material.emissiveIntensity = 3.0 * sparkFlicker
          spark.scale.setScalar(0.5 + 1.5 * sparkFlicker)
          spark.position.y = 5.0 + Math.sin(t * 15 + si) * 0.8
          spark.position.x += Math.cos(t * 14 + si * 0.7) * dt * 1.5
        })
      }
      // 转炉底吹气泡
      if (g._convBottomBubbs) {
        g._convBottomBubbs.forEach((bub, bi) => {
          bub.position.y = -2.5 + (t * 3 + bi * 0.5) % 10 * 0.9
          bub.position.x += Math.sin(t * 6 + bi) * dt * 0.5
          bub.material.opacity = 0.2 + 0.3 * (1 - (bub.position.y + 2.5) / 9)
        })
      }
      // 转炉渣层
      if (g._convSlagMat) {
        g._convSlagMat.emissiveIntensity = 0.25 + 0.2 * Math.abs(Math.sin(t * 6 + phase))
      }
      // === 连铸机(Caster)专属动画 ===
      // 二冷区水喷雾（冷却水沿铸坯表面滴落，贴合垂直段/弧形段/水平段）
      if (g._casterSprays) {
        g._casterSprays.forEach((spray, si) => {
          const by = spray.userData.baseY
          if (by !== undefined) {
            const fall = (t * 3.2 + si * 0.13 + phase * 0.01) % 1
            spray.position.y = by - fall * 0.9
          }
          spray.material.opacity = 0.25 + 0.35 * Math.random()
        })
      }
      // 切割火花
      if (g._casterSparks) {
        g._casterSparks.forEach((spark, si) => {
          spark.position.x += (Math.random() - 0.5) * dt * 6
          spark.position.y += dt * 3
          spark.position.z += (Math.random() - 0.5) * dt * 2
          spark.material.emissiveIntensity = 2.0 + Math.random() * 2.0
          if (spark.position.y > 3.5) { spark.position.y = 1.2; spark.position.x = 5.5; spark.position.z = 1.2 }
        })
      }
      // === 焦炉(CokeOven)专属动画 ===
      // 推焦红焦脉动
      if (g._cokeGlowMats) {
        g._cokeGlowMats.forEach((cm, ci) => {
          cm.emissiveIntensity = 0.5 + 0.3 * Math.abs(Math.sin(t * 8 + ci + phase))
        })
      }
      // 炉门火焰
      if (g._cokeDoorFlares) {
        g._cokeDoorFlares.forEach((fl, fi) => {
          fl.material.emissiveIntensity = 1.2 + 0.8 * Math.abs(Math.sin(t * 14 + fi + phase))
          fl.scale.y = 0.5 + 0.3 * Math.abs(Math.sin(t * 10 + fi))
        })
      }
      // === 烧结(SinterPlant)专属动画 ===
      // 点火炉火焰
      if (g._sinterIgniters) {
        g._sinterIgniters.forEach((ign, ii) => {
          ign.material.emissiveIntensity = 1.8 + 1.2 * Math.abs(Math.sin(t * 16 + ii))
          ign.scale.setScalar(0.7 + 0.6 * Math.abs(Math.sin(t * 12 + ii)))
        })
      }
      // === 钢包精炼(LF/RH/VD)专属动画 ===
      // 底吹氩气搅拌气泡上浮
      if (g._arBubbles) {
        g._arBubbles.forEach((bub, bi) => {
          bub.position.y += dt * 2.5
          bub.position.x += Math.sin(t * 8 + bi * 0.7) * dt * 0.8
          bub.position.z += Math.cos(t * 7 + bi * 0.5) * dt * 0.8
          if (bub.position.y > 7) { bub.position.y = 0.5; bub.position.x = (Math.random() - 0.5) * 4; bub.position.z = (Math.random() - 0.5) * 4 }
          bub.material.opacity = 0.15 + 0.2 * (1 - (bub.position.y - 0.5) / 6.5)
        })
      }
      // === 铁水预处理(Pretreat)专属动画 ===
      // 脱硫剂喷吹颗粒注入
      if (g._pretreatSpray) {
        g._pretreatSpray.forEach((p, pi) => {
          // 低端机优化：目标点复用常量，避免每帧 new THREE.Vector3
          p.position.x += (0 - p.position.x) * dt
          p.position.y += (2.8 - p.position.y) * dt * 0.8
          p.position.z += (0 - p.position.z) * dt
          if (p.position.y < 1.5) {
            p.position.set(2.2, 5.0 + Math.random() * 1.0, -2.2 + (Math.random() - 0.5) * 1.5)
          }
          p.rotation.x += dt * 6
          p.rotation.y += dt * 5
        })
      }
      // === 加热炉(ReheatFurnace)专属动画 ===
      // 炉顶烧嘴火焰脉动
      if (g._reheatBurners) {
        g._reheatBurners.forEach((fl, fi) => {
          fl.material.emissiveIntensity = 1.2 + 0.8 * Math.abs(Math.sin(t * 14 + fi + phase))
          fl.scale.y = 0.6 + 0.4 * Math.abs(Math.sin(t * 10 + fi))
        })
      }
      // 物料转变动画：原料进→工艺处理→产品出
      if (g.matFlow) this._stepMaterialFlow(g.matFlow, t, dt)
      // === 工辅专属动画 ===
      // 旋转机械（鼓风机/引风机/驱动电源）：叶轮持续旋转
      if (g._fanBlades) {
        const sp = (g._fanPhase || 1.0)
        g._fanBlades.rotation.x += dt * 3.4 * sp
      }
      // 燃烧炉塔（热风炉/辅助锅炉）：炉内火焰脉动
      if (g._hbsFlames) {
        g._hbsFlames.forEach((fl, fi) => {
          const p = Math.abs(Math.sin(t * 11 + fi * 1.7 + phase))
          fl.material.emissiveIntensity = 1.4 + 1.1 * p
          fl.scale.y = 0.7 + 0.5 * p
        })
      }
      // 皮带机：托辊旋转 + 物料随带前进循环
      if (g._beltRoll) {
        g._beltRoll.rollers.forEach((rg, i) => { rg.rotation.y += dt * (1.8 + i * 0.1) })
        const bn = g._beltRoll.chunks.length
        g._beltRoll.chunks.forEach((c, i) => {
          let x = c.position.x + dt * 6
          if (x > 9) x = -9
          c.position.x = x
        })
      }
      // 冷却水泵：叶轮旋转
      if (g._pumpRotors) {
        g._pumpRotors.forEach((v) => { v.rotation.z += dt * 4 })
      }
      // 电极调节器：电极微幅升降 + 弧光脉动
      if (g._elecRegs) {
        g._elecRegs.forEach((e, i) => {
          e.group.position.y = e.baseUY + 0.3 * Math.sin(t * 2.5 + i * 2.1)
          if (e.tip && e.tip.material) e.tip.material.emissiveIntensity = 2.5 * (1.6 + 0.7 * Math.sin(t * 9 + i * 3))
        })
      }
      // 喷吹系统/给料机：料流颗粒沿管前进循环
      if (g._injectorPuffs) {
        g._injectorPuffs.forEach((p) => {
          p.position.x += dt * 7
          if (p.position.x > 16) p.position.x = 8
          p.material.opacity = 0.5 + 0.4 * Math.sin(t * 6 + p.position.x)
        })
      }
      // 制氧机：精馏塔冷态微光呼吸
      if (g._oxyTowers) {
        g._oxyTowers.forEach((tow, i) => {
          if (tow.material && 'emissiveIntensity' in tow.material) {
            tow.material.emissiveIntensity = 0.12 + 0.06 * Math.sin(t * 1.5 + i)
          }
        })
      }
      // 供电系统：电流脉冲沿输电导线流动（铁塔 → 变压器）
      if (g._powerPulses) {
        g._powerPulses.forEach((p) => {
          p._t = (p._t + dt * 0.5) % 1
          const u = (p._t + p._off) % 1
          p.position.lerpVectors(p._from, p._to, u)
          p.material.emissiveIntensity = 1.6 + 1.6 * Math.sin(u * Math.PI)
        })
      }
    })
    this.flows.forEach((f) => {
      f.t = (f.t + dt * f.speed) % 1
      const base = f._tmp || (f._tmp = new THREE.Vector3())
      // 载运体沿折线路径移动：与传送带/流槽/管道的分段直线构建完全一致，
      // 弯头处紧贴带面/液面/管道，避免 CatmullRom 切角造成的悬浮或穿入
      if (f.wp && f.wp.length > 1) {
        let target = f.t * f.totalLen
        let si = 0
        const nSeg = f.wp.length - 1
        while (si < nSeg - 1 && target > f.segLens[si]) { target -= f.segLens[si]; si++ }
        const sLen = f.segLens[si]
        const u = sLen > 0 ? Math.min(target / sLen, 1) : 0
        base.lerpVectors(f.wp[si], f.wp[si + 1], u)
        // 沿该段法向（带面/液面向上方向）偏移，贴合媒介表面；水平段即世界 Y 向上
        if (f.yDirs && f.yDirs[si]) {
          base.addScaledVector(f.yDirs[si], f.carrierOffset != null ? f.carrierOffset : 1.5)
        } else {
          base.y += (f.carrierOffset != null ? f.carrierOffset : 1.5)
        }
      } else {
        base.lerpVectors(f.from, f.to, f.t)
        base.y += (f.carrierOffset != null ? f.carrierOffset : 1.5)
      }
      f.obj.position.copy(base)
      if (f.anim === 'molten' || f.anim === 'liquid') {
        // 熔体/液体：贴槽轻微起伏 + 自转 + 发光脉动
        f.obj.position.y += Math.sin(t * 3 + f.phase) * 0.12
        f.obj.rotation.y += dt * 0.6
        if (f.mat && f.emi) f.mat.emissiveIntensity = f.emi * (1 + 0.16 * Math.sin(t * 9 + f.phase))
      } else if (f.anim === 'granular') {
        // 散料：翻滚
        f.obj.rotation.x += dt * 1.6
        f.obj.rotation.z += dt * 1.1
      } else if (f.anim === 'chunk') {
        // 不规则块：慢翻滚
        f.obj.rotation.y += dt * 0.9
        f.obj.rotation.x += dt * 0.4
      } else if (f.anim === 'slab') {
        // 板坯：刚体滑移 + 热态发光脉动
        f.obj.rotation.y += dt * 0.35
        if (f.mat && f.emi) f.mat.emissiveIntensity = f.emi * (1 + 0.12 * Math.sin(t * 5 + f.phase))
      } else if (f.anim === 'gas') {
        // 气体：气泡在管道内翻涌
        f.obj.rotation.y += dt * 1.0
        f.obj.position.y += Math.sin(t * 4 + f.phase) * 0.08
      }
    })
    // 水面波动（森林湖面 / 海岸海面）：基于初始顶点做正弦叠加，重算法线保持反射
    if (this.water) {
      const arr = this.water.geometry.attributes.position.array
      const base = this._waterBase
      const amp = this._waveAmp || 0.5
      for (let i = 0; i < arr.length; i += 3) {
        const bx = base[i], bz = base[i + 2]
        arr[i + 1] = Math.sin(bx * 0.02 + t * 0.9) * amp + Math.cos(bz * 0.025 + t * 0.7) * amp
      }
      this.water.geometry.attributes.position.needsUpdate = true
      this.water.geometry.computeVertexNormals()
    }
    // 海岸水面轻缓波动（隔帧更新：低频正弦动画 15fps 与 30fps 视觉几乎无差别，CPU 减半）
    if (this._coastWater && this._coastWater.geometry) {
      this._waveFrame = (this._waveFrame || 0) + 1
      if (this._waveFrame % 2 === 0) {
        const arr = this._coastWater.geometry.attributes.position.array
        for (let i = 0; i < arr.length; i += 3) {
          const bx = arr[i], bz = arr[i + 2]
          arr[i + 1] = Math.sin(bx * 0.008 + t * 0.5) * 0.6 + Math.cos(bz * 0.01 + t * 0.4) * 0.5
        }
        this._coastWater.geometry.attributes.position.needsUpdate = true
        this._coastWater.geometry.computeVertexNormals()
      }
    }
    // 虚空灯塔：顶部红色警示灯脉动 + 灯头照明强度呼吸
    if (this.envMode === 'void' && this._voidLampBeacons) {
      for (let i = 0; i < this._voidLampBeacons.length; i++) {
        const bm = this._voidLampBeacons[i]
        if (bm) bm.opacity = 0.5 + 0.45 * Math.sin(t * 2.4 + i * 1.57)
      }
      if (this._voidLampLights) {
        this._voidLampLights.forEach((l, i) => {
          l.intensity = 0.45 + 0.15 * Math.sin(t * 1.2 + i * 1.3)
        })
      }
    }
    // 反重力悬浮光束：青色锥形光柱呼吸脉动（内亮层与外晕层反向错相，增强体积感）
    if (this.envMode === 'void' && this._voidBeams) {
      for (let i = 0; i < this._voidBeams.length; i++) {
        const pair = this._voidBeams[i]
        if (!pair) continue
        if (pair[0]) pair[0].opacity = 0.13 + 0.07 * Math.sin(t * 1.4 + i * 0.8)
        if (pair[1]) pair[1].opacity = 0.05 + 0.03 * Math.sin(t * 1.4 + i * 0.8 + 1.2)
      }
    }
    // 平台四角节点 + 边框霓虹脉动
    if (this.platformGroup) {
      const children = this.platformGroup.children
      for (const c of children) {
        if (c.material) {
          if (c.material.emissiveIntensity !== undefined) {
            c.material.emissiveIntensity = 1.3 + 0.5 * Math.sin(t * 1.8 + (c.position.x + c.position.z) * 0.05)
          } else if (c.material.color && c.material.color.getHex() === 0x00aadd) {
            c.material.opacity = 0.55 + 0.2 * Math.sin(t * 2.2)
          }
        }
      }
      // 网格线微弱呼吸
      const gridOpacity = 0.28 + 0.1 * Math.sin(t * 1.6)
      for (const c of children) {
        if (c.material && c.material.color && c.material.color.getHex() === 0x003366) {
          c.material.opacity = gridOpacity
        }
      }
    }
    if (this._focus) {
      this._stepFocus(dt)
    } else if (this._intro) {
      this._stepIntro(dt)
    } else {
      this.controls.update()
    }
    this._clampCamera()
    this._updateLabelScales()
    this.renderer.render(this.scene, this.camera)
  }

  _clampCamera() {
    // 仅限制摄像机不低于地面，其他方向自由移动
    if (this.camera.position.y < 1.5) this.camera.position.y = 1.5
  }

  // 动态缩放所有标签，保持屏幕上的显示大小恒定（不受摄像机距离影响）
  _updateLabelScales() {
    const camPos = this.camera.position
    // 低端机优化：复用临时向量，避免每帧 new THREE.Vector3 造成 GC 压力
    const amp = this._labelAmp || (this._labelAmp = new THREE.Vector3())
    const REF = 35          // 距摄像机此距离内使用基准尺寸
    const MAX_FACTOR = 5.2  // 最大放大倍数：汇报视角仍要清晰识别主工艺名称
    // 工序标签：与管道/轨道连接标签完全一致的展示形式——恒定显示、无悬浮动画、同尺寸同缩放
    const parentScale = this._labelParentScale || (this._labelParentScale = new THREE.Vector3())
    this.unitGroups.forEach((g) => {
      const lo = g.labelObj
      if (!lo || !lo.sprite) return
      lo.sprite.getWorldPosition(amp)
      const dist = Math.max(1, amp.distanceTo(camPos))
      const factor = Math.min(dist / REF, MAX_FACTOR)
      lo.sprite.material.opacity = 1
      const sf = LABEL_SCALE * factor * (lo.focused ? LABEL_FOCUS_GAIN : 1)
      // 世界尺寸基准：工艺标签 = sf × LABEL_PARENT_REF；工辅/小组标签在此基础上小一号（× LABEL_AUX_GAIN）。
      // 再除以各自父级世界缩放换算为局部 scale（工艺模型父级 4~5、工辅 3.5~3.8、小组外层 1），
      // 归一化后消除继承父级缩放造成的尺寸差异，且三类标签呈现明确的层级大小关系。
      const ps = lo.sprite.parent ? lo.sprite.parent.getWorldScale(parentScale) : parentScale.set(1, 1, 1)
      const base = sf * LABEL_PARENT_REF * (lo.isGroup || lo.main !== true ? LABEL_AUX_GAIN : 1)
      lo.sprite.scale.set(base / ps.x, (base * (UNIT_LABEL_H / LABEL_W)) / ps.y, 1)
    })

    // 工艺间连接线标签
    if (this._flowGroup) {
      this._flowGroup.children.forEach((spr) => {
        if (!spr.isSprite || !spr.userData || spr.userData.kind !== 'flow') return
        spr.getWorldPosition(amp)
        const dist = Math.max(1, amp.distanceTo(camPos))
        const factor = Math.min(dist / REF, MAX_FACTOR)
        const focused = this.focusedFlowId && spr.userData.flowId === this.focusedFlowId
        const gain = focused ? LABEL_FOCUS_GAIN : 1
        const sf = LABEL_SCALE * factor * gain
        spr.scale.set(sf, sf * LABEL_ASPECT, 1)
      })
    }
  }

  _stepParticles(pts, dt, speed, isSmoke) {
    if (!pts) return
    const pos = pts.geometry.attributes.position
    const arr = pos.array
    const n = pts.userData.count
    const maxY = pts.userData.maxY || 14
    for (let i = 0; i < n; i++) {
      arr[i * 3 + 1] += dt * speed * (isSmoke ? 0.6 : 1)
      arr[i * 3] += Math.sin((arr[i * 3 + 1] + i) * 0.5) * dt * 0.4
      if (arr[i * 3 + 1] > maxY) {
        arr[i * 3 + 1] = 0
        arr[i * 3] = (Math.random() - 0.5) * 3
      }
    }
    pos.needsUpdate = true
  }

  /** 物料转变动画：原料→工艺→产物 的可视化流 */
  _stepMaterialFlow(flows, t, dt) {
    if (!flows || !flows.length) return
    flows.forEach((mf) => {
      if (!mf.obj || !mf.obj.material) return
      const period = mf.period || 4.0
      let p = ((t / period + (mf.phase || 0)) % 1)
      if (mf.pingPong && p > 0.5) p = 1 - p
      // 位置插值
      if (mf.srcPos && mf.dstPos) {
        mf.obj.position.lerpVectors(mf.srcPos, mf.dstPos, p)
      }
      // 沿Y轴上下浮动
      if (mf.floatAmp) {
        mf.obj.position.y += Math.sin(p * Math.PI * 2 + mf.phase) * mf.floatAmp
      }
      // 颜色渐变：原料色→产物色（复用 Color 对象避免每帧分配，减轻 GC 压力）
      if (mf.srcColor && mf.dstColor) {
        if (!mf._c0) { mf._c0 = new THREE.Color(mf.srcColor); mf._c1 = new THREE.Color(mf.dstColor) }
        const c = this._mfTmpC || (this._mfTmpC = new THREE.Color())
        c.lerpColors(mf._c0, mf._c1, p)
        mf.obj.material.color.copy(c)
        if (mf.obj.material.emissive) {
          mf.obj.material.emissive.copy(c).multiplyScalar(0.3 + 0.35 * Math.sin(p * Math.PI))
        }
        mf.obj.material.emissiveIntensity = 0.3 + 0.4 * Math.sin(p * Math.PI)
      }
      // 大小脉动
      if (mf.scalePulse) {
        const s = 1.0 + mf.scalePulse * Math.sin(p * Math.PI)
        mf.obj.scale.setScalar(s)
      }
      // 旋转
      if (mf.rotAxis) {
        mf.obj.rotateOnAxis(mf.rotAxis, dt * (mf.rotSpeed || 1.5))
      }
    })
  }

  resize() {
    const w = this.container.clientWidth || window.innerWidth
    const h = this.container.clientHeight || window.innerHeight
    // 防御：canvas display:none 时容器尺寸为 0，不可设置投影矩阵（会导致 NaN）
    if (w <= 0 || h <= 0) return
    // 同尺寸短路：拖拽面板期间 ResizeObserver 可能以相同尺寸重复触发，
    // 跳过重复 setSize 可避免 canvas 反复重建导致的画面闪烁
    if (w === this._cw && h === this._ch) return
    this._cw = w
    this._ch = h
    this.camera.aspect = w / h
    this.camera.updateProjectionMatrix()
    // 仅当 pixel ratio 档位变化（如跨屏 DPR 变化）时才重建绘制缓冲；
    // 窗口拖动时同屏 pixel ratio 恒定，只更新画布尺寸即可，避免画面闪烁
    const pr = this._pickPixelRatio()
    if (pr !== this._pr) {
      this._pr = pr
      this.renderer.setPixelRatio(pr)
    }
    this.renderer.setSize(w, h)
  }

  _clearModel() {
    while (this.root.children.length) {
      const c = this.root.children.pop()
      this._disposeTree(c)
      this.root.remove(c)
    }
    this.unitGroups.clear()
    this.groupModels.clear()
    this.deviceMap.clear()
    this.flows = []
    this.focusedId = null
    this.focusedFlowId = null
    this.groupScene = null
    // 底座材质引用随模型销毁清空，避免数组残留
    this._pedestalMats = []
    this._pedestalEdgeMats = []
    this._groupEdgeMats = []
  }

  dispose() {
    cancelAnimationFrame(this._raf)
    this._raf = null
    if (this._resizeRaf) { cancelAnimationFrame(this._resizeRaf); this._resizeRaf = null }
    if (this._onWinResize) window.removeEventListener('resize', this._onWinResize)
    this._clearModel()
    this._teardownEnvironment()
    this.controls.dispose()
    this.renderer.dispose()
    if (this.renderer.domElement.parentNode) this.renderer.domElement.parentNode.removeChild(this.renderer.domElement)
  }
}
