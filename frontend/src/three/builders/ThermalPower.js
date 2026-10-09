// 火电（thermal-power）场景 3D 工艺模型构建器
// 覆盖（工序按「系统」口径，与包字典/模板一致）：输煤制粉 / 锅炉 / 汽轮机 / 发电 /
//       凝汽 / 循环冷却水 / 给水除氧 / 烟气脱硝 / 烟气除尘 / 烟气脱硫 / 排烟 / 热网换热
//
// 造型取自真实电厂总平面与设备外形（双曲线冷却塔、汽包锅炉、卧式凝汽器、喷淋吸收塔…），
// 每个设备都带**专属动画**：旋转机械（磨煤机/转子/泵叶轮）、燃烧火焰脉动、蒸汽与烟羽上升、
// 喷淋液滴下落、催化剂层微光、振打清灰、循环水与热网介质流向等。
//
// 动画口径：统一以 group.userData._tpTick = [fn(t, dt, phase)] 自描述，由 scene.js 动画循环
// 逐帧调用（一处接入，新增设备不必再改 scene.js 动画分支）。
import * as THREE from 'three'
import { mat, boxMesh } from './utils.js'

// —— 常用色板（工业涂装）——
const C = {
  concrete: 0x8d949c,   // 混凝土基座
  steel: 0x5a6a7a,      // 钢构/机架
  dark: 0x39434e,       // 暗部/底座
  shell: 0x9aa5ae,      // 设备外壳（保温铝皮）
  shellBlue: 0x6f8296,  // 带涂装的外壳
  pipeWater: 0x3b9ee0,  // 冷水/给水（蓝）
  pipeWarm: 0xd4803a,   // 回水/热水（橙）
  pipeSteam: 0xc9d6e0,  // 蒸汽/主汽（银白）
  pipeFlue: 0x7d858d,   // 烟气（灰）
  coal: 0x2b2b30,       // 原煤/煤粉
  fire: 0xff7a2a,       // 火焰
  slurry: 0xd9d3c0,     // 石灰石浆液
  gypsum: 0xe6e2d3,     // 石膏
  elec: 0xf0c419,       // 电气/电流（黄）
  hand: 0xc8ccd0,       // 栏杆/格栅
}

// 共享几何：粒子/小构件量大，复用同一份几何体（dispose 时跳过，见 scene.js）
const SPH = new THREE.SphereGeometry(1, 8, 6)
SPH.userData.__shared = true

/** 圆柱便捷构造（上下半径可不等，用于锥筒/喇叭口） */
function cylMesh(rt, rb, h, m, seg = 18) {
  return new THREE.Mesh(new THREE.CylinderGeometry(rt, rb, h, seg), m)
}

/** 混凝土基座（所有设备共用的落地平台） */
function addBase(g, w = 22, d = 16, y = 0.4) {
  const pad = boxMesh(w + 3, 0.4, d + 3, mat(C.dark, { roughness: 0.95 }))
  pad.position.y = 0.2
  g.add(pad)
  const b = boxMesh(w, 0.8, d, mat(C.concrete, { roughness: 0.92 }))
  b.position.y = 0.8
  g.add(b)
  return 0.8
}

/** 钢构立柱（电厂厂房/塔架的支撑柱） */
function addColumns(g, xs, zs, h, y0 = 1.2, t = 0.7) {
  const m = mat(C.steel, { metalness: 0.55, roughness: 0.45 })
  for (const x of xs) for (const z of zs) {
    const c = boxMesh(t, h, t, m)
    c.position.set(x, y0 + h / 2, z)
    g.add(c)
  }
}

/** 检修平台（环绕设备的格栅走道 + 栏杆） */
function addPlatform(g, w, d, y, h = 0.35) {
  const p = boxMesh(w, h, d, mat(C.hand, { metalness: 0.4, roughness: 0.6 }))
  p.position.y = y
  g.add(p)
  const railMat = mat(C.hand, { metalness: 0.5, roughness: 0.5 })
  const rw = w, rd = d
  ;[[0, rd / 2, rw, 0.16], [0, -rd / 2, rw, 0.16]].forEach(([x, z, len]) => {
    const r = boxMesh(len, 0.16, 0.16, railMat)
    r.position.set(x, y + 1.1, z)
    g.add(r)
  })
  ;[[rw / 2, 0, rd], [-rw / 2, 0, rd]].forEach(([x, z, len]) => {
    const r = boxMesh(0.16, 0.16, len, railMat)
    r.position.set(x, y + 1.1, z)
    g.add(r)
  })
  return p
}

/** 管段：沿 axis 轴的圆柱（水管/汽管/烟道） */
function addPipe(g, r, len, axis, pos, m) {
  const p = cylMesh(r, r, len, m, 14)
  if (axis === 'x') p.rotation.z = Math.PI / 2
  else if (axis === 'z') p.rotation.x = Math.PI / 2
  p.position.set(pos[0], pos[1], pos[2])
  g.add(p)
  return p
}

/** 电机（带散热筋的工业电机，轴向沿 X） */
function addMotor(g, x, y, z, r = 1.8, len = 4.4) {
  const m = cylMesh(r, r, len, mat(0x4a5d72, { metalness: 0.5, roughness: 0.4 }), 16)
  m.rotation.z = Math.PI / 2
  m.position.set(x, y, z)
  g.add(m)
  for (let i = -1; i <= 1; i++) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(r + 0.06, 0.1, 6, 16), mat(0x3a4a5c))
    ring.rotation.y = Math.PI / 2
    ring.position.set(x + i * (len / 3), y, z)
    g.add(ring)
  }
  return m
}

/** 粒子组：n 个共享球几何的柔光团（蒸汽/烟羽/液滴/粉尘），各自独立材质以便独立淡出 */
function addPuffs(g, n, r, color, opacity) {
  const arr = []
  for (let i = 0; i < n; i++) {
    const m = new THREE.Mesh(SPH, mat(color, {
      transparent: true, opacity, roughness: 1, metalness: 0, depthWrite: false,
    }))
    m.scale.setScalar(r)
    g.add(m)
    arr.push(m)
  }
  return arr
}

/* ============================ 1. 输煤与制粉 ============================ */
// 煤堆 + 输煤皮带廊（托辊转动、煤块随带前进）+ 中速磨煤机（筒体旋转）+ 煤粉管道
function buildCoalHandling(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 26, 16)
  // 原煤堆（锥形料堆，两堆）
  const coalMat = mat(C.coal, { roughness: 0.95, metalness: 0.05 })
  ;[[-9, -2, 4.4], [-6.5, 2.6, 3.4]].forEach(([x, z, r]) => {
    const pile = cylMesh(0.4, r, r * 0.9, coalMat, 14)
    pile.position.set(x, y0 + r * 0.45, z)
    g.add(pile)
  })
  // 输煤皮带廊（倾斜桁架，从煤堆升向磨煤机）
  const gallery = boxMesh(20, 1.6, 4.2, mat(C.steel, { metalness: 0.5, roughness: 0.45 }))
  gallery.position.set(2, y0 + 7.4, -2)
  gallery.rotation.z = -0.24
  g.add(gallery)
  // 廊道支腿
  ;[-6, 6].forEach((dx) => {
    const leg = boxMesh(0.8, 7.0, 0.8, mat(C.steel, { metalness: 0.5 }))
    leg.position.set(2 + dx, y0 + 3.5, -2)
    g.add(leg)
  })
  // 皮带托辊（沿廊道均布，持续旋转）
  const rollers = []
  for (let i = 0; i < 7; i++) {
    const u = (i / 6 - 0.5)
    const r = cylMesh(0.52, 0.52, 3.6, mat(0x39434e, { metalness: 0.4 }), 12)
    r.rotation.x = Math.PI / 2
    r.position.set(2 + u * 18, y0 + 7.4 - u * 18 * 0.24 + 1.3, -2)
    g.add(r)
    rollers.push(r)
  }
  // 皮带上的煤块（随带前进，到头回卷）
  const chunks = []
  for (let i = 0; i < 10; i++) {
    const c = boxMesh(1.1, 0.7, 1.0, coalMat)
    c.position.set(-7 + i * 1.9, y0 + 8.9, -2)
    g.add(c)
    chunks.push(c)
  }
  // 中速磨煤机（立式筒体 + 磨盘 + 电机 + 出粉管）
  const millY = y0 + 4.6
  const mill = cylMesh(3.2, 3.6, 6.4, bodyMat, 20)
  mill.position.set(9, millY, 3)
  g.add(mill)
  const millCap = cylMesh(1.6, 3.2, 1.8, mat(C.shellBlue, { metalness: 0.45 }), 20)
  millCap.position.set(9, millY + 4.1, 3)
  g.add(millCap)
  addMotor(g, 9, millY - 3.6, 3, 1.5, 3.4)
  // 磨盘（旋转部件）
  const disc = cylMesh(2.6, 2.6, 0.5, mat(0x5c6672, { metalness: 0.6, roughness: 0.35 }), 18)
  disc.position.set(9, millY - 2.4, 3)
  g.add(disc)
  // 出粉管（去锅炉燃烧器）
  addPipe(g, 0.55, 7.0, 'y', [9, millY + 7.4, 3], mat(C.coal, { roughness: 0.9 }))
  addPipe(g, 0.55, 6.0, 'x', [12.0, millY + 10.6, 3], mat(C.coal, { roughness: 0.9 }))
  // 给煤机（小箱体，位于煤堆与磨之间）
  const feeder = boxMesh(4.4, 3.0, 3.6, mat(C.shellBlue, { metalness: 0.4 }))
  feeder.position.set(0.5, y0 + 2.3, 3)
  g.add(feeder)

  g.userData.topY = 20
  g.userData._tpTick = [
    (t, dt) => {
      rollers.forEach((r, i) => { r.rotation.y += dt * (2.2 + i * 0.05) })
      for (const c of chunks) {
        c.position.x += dt * 3.6
        if (c.position.x > 11) c.position.x = -8
        c.position.y = y0 + 8.7 + (c.position.x - 2) * (-0.24)   // 与廊道同坡，煤块始终贴在带面上
        c.rotation.z = -0.24
      }
      disc.rotation.y += dt * 2.6
    },
  ]
  return g
}

/* ============================ 2. 锅炉 ============================ */
// 炉膛（钢架 + 炉墙）+ 汽包 + 四角燃烧器火焰 + 过热器 + 主蒸汽管 + 上升蒸汽
function buildBoiler(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 20, 16)
  const H = 24
  // 炉膛本体（水冷壁炉墙，带保温铝皮外壳）
  const furnace = boxMesh(12, H, 11, bodyMat)
  furnace.position.y = y0 + H / 2
  g.add(furnace)
  // 炉膛钢架（四角立柱 + 顶部横梁）
  addColumns(g, [-6.4, 6.4], [-5.8, 5.8], H + 2, y0, 0.8)
  const topBeam = boxMesh(14.4, 0.8, 12.8, mat(C.steel, { metalness: 0.55 }))
  topBeam.position.y = y0 + H + 2
  g.add(topBeam)
  // 炉膛中部环带（燃烧器区域，深色以示燃烧区）
  const belt = boxMesh(12.4, 4.2, 11.4, mat(0x4a3b33, { roughness: 0.8 }))
  belt.position.y = y0 + 6.5
  g.add(belt)
  // 四角燃烧器 + 火焰（脉动）
  const flames = []
  const burnerMat = mat(0x3a4149, { metalness: 0.6, roughness: 0.4 })
  const bpos = [[-6.6, 0], [6.6, 0], [0, -6.0], [0, 6.0]]
  for (const [x, z] of bpos) {
    const b = cylMesh(0.9, 0.9, 2.4, burnerMat, 12)
    b.rotation.z = Math.PI / 2
    if (z !== 0) b.rotation.x = Math.PI / 2
    b.position.set(x, y0 + 6.5, z)
    g.add(b)
    const fm = mat(C.fire, { emissive: 0xff3c00, emissiveIntensity: 1.6, transparent: true, opacity: 0.9 })
    const fl = cylMesh(0.05, 0.85, 2.6, fm, 10)
    fl.position.set(x * 0.55, y0 + 6.5, z * 0.55)
    if (x !== 0) fl.rotation.z = -Math.sign(x) * Math.PI / 2
    else fl.rotation.x = Math.sign(z) * Math.PI / 2
    g.add(fl)
    flames.push(fl)
  }
  // 汽包（顶部横置圆筒，锅炉标志件）
  const drum = cylMesh(2.2, 2.2, 13, mat(0xa9b3bc, { metalness: 0.55, roughness: 0.35 }), 22)
  drum.rotation.z = Math.PI / 2
  drum.position.set(0, y0 + H + 4.2, 0)
  g.add(drum)
  // 汽包水位（水面微动）
  const level = boxMesh(11.5, 0.3, 3.0, mat(0x2f7fb0, { emissive: 0x1d5f86, emissiveIntensity: 0.6 }))
  level.position.set(0, y0 + H + 3.9, 0)
  g.add(level)
  // 过热器管束（炉膛上部横排细管）
  for (let i = 0; i < 6; i++) {
    const tube = cylMesh(0.22, 0.22, 11.4, mat(0x8e9aa6, { metalness: 0.6 }), 8)
    tube.rotation.z = Math.PI / 2
    tube.position.set(0, y0 + H - 3.5 + i * 0.9, -2.4 + (i % 2) * 4.8)
    g.add(tube)
  }
  // 主蒸汽管（去汽轮机，顶部引出）+ 给水管（省煤器入口）
  addPipe(g, 0.7, 9.0, 'x', [9.5, y0 + H + 4.2, 0], mat(C.pipeSteam, { metalness: 0.6, roughness: 0.3 }))
  addPipe(g, 0.6, 7.0, 'x', [-9.0, y0 + 3.2, 3.6], mat(C.pipeWater, { metalness: 0.55 }))
  // 检修平台（两层）
  addPlatform(g, 14.5, 13, y0 + 11.5)
  addPlatform(g, 14.5, 13, y0 + H + 1.5)
  // 蒸汽上升（炉顶逸散）
  const steam = addPuffs(g, 7, 1.5, 0xeef4f8, 0.32)
  steam.forEach((s, i) => { s.position.set(-3 + i, y0 + H + 6, -1 + (i % 3)) })

  g.userData.topY = y0 + H + 9
  g.userData._tpTick = [
    (t, dt) => {
      flames.forEach((fl, i) => {
        const p = Math.abs(Math.sin(t * 12 + i * 1.7))
        fl.material.emissiveIntensity = 1.2 + 1.3 * p
        fl.scale.y = 0.7 + 0.5 * p
      })
      level.position.y = y0 + H + 3.9 + 0.18 * Math.sin(t * 1.6)
      steam.forEach((s, i) => {
        s.position.y += dt * (1.6 + i * 0.12)
        s.position.x += Math.sin(t * 0.9 + i) * dt * 0.6
        const k = (s.position.y - (y0 + H + 6)) / 9
        s.scale.setScalar(1.5 + k * 2.4)
        s.material.opacity = Math.max(0, 0.34 * (1 - k))
        if (s.position.y > y0 + H + 15) {
          s.position.y = y0 + H + 6
          s.scale.setScalar(1.5)
        }
      })
    },
  ]
  return g
}

/* ============================ 3. 汽轮机 ============================ */
// 高/中/低压缸三段渐扩 + 贯穿转子（高速旋转）+ 排汽口
function buildTurbine(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 26, 14)
  const cy = y0 + 4.6
  // 三段缸体（高压缸细、中压缸中、低压缸粗，沿 X 串联）
  const casings = [
    { x: -8.5, r: 2.0, len: 6.0 },
    { x: -1.5, r: 2.7, len: 7.0 },
    { x: 6.5, r: 3.9, len: 9.0 },
  ]
  for (const c of casings) {
    const shell = cylMesh(c.r, c.r, c.len, bodyMat, 24)
    shell.rotation.z = Math.PI / 2
    shell.position.set(c.x, cy, 0)
    g.add(shell)
    // 缸体法兰环（分段接缝）
    for (const s of [-1, 1]) {
      const fl = new THREE.Mesh(new THREE.TorusGeometry(c.r + 0.12, 0.22, 6, 22), mat(0x6f7c89, { metalness: 0.6 }))
      fl.rotation.y = Math.PI / 2
      fl.position.set(c.x + s * (c.len / 2), cy, 0)
      g.add(fl)
    }
  }
  // 转子（贯穿三缸，高速旋转）+ 各级叶轮
  const rotor = new THREE.Group()
  rotor.position.set(0, cy, 0)
  const shaft = cylMesh(0.55, 0.55, 26, mat(0xb9c2cb, { metalness: 0.85, roughness: 0.22 }), 14)
  shaft.rotation.z = Math.PI / 2
  rotor.add(shaft)
  casings.forEach((c, ci) => {
    for (let i = 0; i < 4; i++) {
      const blade = cylMesh(c.r * 0.82, c.r * 0.82, 0.28, mat(0xcfd6dd, { metalness: 0.8, roughness: 0.25 }), 20)
      blade.rotation.z = Math.PI / 2
      blade.position.set(c.x - c.len / 2 + 1.2 + i * (c.len - 2.4) / 3, 0, 0)
      rotor.add(blade)
    }
  })
  g.add(rotor)
  // 排汽口（低压缸下方，去凝汽器）
  const exhaust = cylMesh(3.6, 2.6, 3.4, mat(C.shellBlue, { metalness: 0.45 }), 20)
  exhaust.position.set(6.5, cy - 3.6, 0)
  g.add(exhaust)
  // 主汽进汽管（左上进）+ 抽汽口
  addPipe(g, 0.75, 6.0, 'x', [-13.5, cy + 1.6, 0], mat(C.pipeSteam, { metalness: 0.6, roughness: 0.3 }))
  addPipe(g, 0.5, 4.0, 'y', [-1.5, cy + 4.4, 0], mat(C.pipeSteam, { metalness: 0.6 }))
  // 轴承座 + 基座
  ;[-8.5, 6.5].forEach((x) => {
    const ped = boxMesh(2.2, 3.0, 3.4, mat(C.dark, { roughness: 0.8 }))
    ped.position.set(x + (x < 0 ? -4 : 5.6), y0 + 1.5, 0)
    g.add(ped)
  })
  // 缸体保温层微光（热态）
  const glow = mat(0xff8a4a, { emissive: 0xff5a1e, emissiveIntensity: 0.18, transparent: true, opacity: 0.25 })
  const glowShell = cylMesh(4.0, 4.0, 9.2, glow, 20)
  glowShell.rotation.z = Math.PI / 2
  glowShell.position.set(6.5, cy, 0)
  g.add(glowShell)

  g.userData.topY = cy + 8
  g.userData._tpTick = [
    (t, dt) => {
      rotor.rotation.x += dt * 9.5   // 3000 r/min 意象：高速旋转
      glow.emissiveIntensity = 0.14 + 0.06 * Math.abs(Math.sin(t * 3))   // 缸体热态微光
    },
  ]
  return g
}

/* ============================ 4. 发电机 ============================ */
// 机体 + 端盖 + 转子（旋转）+ 出线套管与电流 + 主变压器
function buildGenerator(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 26, 14)
  const cy = y0 + 4.8
  // 机体（横置大圆筒 + 两端端盖）
  const body = cylMesh(3.6, 3.6, 14, bodyMat, 26)
  body.rotation.z = Math.PI / 2
  body.position.set(-3, cy, 0)
  g.add(body)
  ;[-10, 4].forEach((x) => {
    const cap = cylMesh(3.7, 3.2, 1.2, mat(0x7c8894, { metalness: 0.6, roughness: 0.35 }), 26)
    cap.rotation.z = Math.PI / 2
    cap.position.set(x, cy, 0)
    g.add(cap)
  })
  // 转子（旋转，端部可见）
  const rotor = new THREE.Group()
  rotor.position.set(-3, cy, 0)
  const shaft = cylMesh(0.7, 0.7, 17, mat(0xc3ccd4, { metalness: 0.85, roughness: 0.22 }), 14)
  shaft.rotation.z = Math.PI / 2
  rotor.add(shaft)
  for (let i = 0; i < 5; i++) {
    const pole = boxMesh(1.4, 0.5, 4.6, mat(0xb8642c, { metalness: 0.55, roughness: 0.45 }))
    pole.position.set(-5 + i * 2.4, 0, 0)
    rotor.add(pole)
  }
  g.add(rotor)
  // 顶部氢冷却器
  const cooler = boxMesh(9.0, 2.2, 4.6, mat(0x6f8296, { metalness: 0.5 }))
  cooler.position.set(-3, cy + 4.6, 0)
  g.add(cooler)
  // 出线套管（三相，竖立瓷套 + 电流指示）
  const insulMat = mat(0xcfd6dd, { roughness: 0.5, metalness: 0.1 })
  const lamps = []
  for (let i = 0; i < 3; i++) {
    const x = 8.5, z = -3 + i * 3
    for (let k = 0; k < 4; k++) {
      const sk = cylMesh(0.85, 0.85, 0.55, insulMat, 12)
      sk.position.set(x, cy + 1.2 + k * 0.85, z)
      g.add(sk)
    }
    const lamp = new THREE.Mesh(SPH, mat(C.elec, { emissive: 0xffb300, emissiveIntensity: 1.4 }))
    lamp.scale.setScalar(0.5)
    lamp.position.set(x, cy + 5.0, z)
    g.add(lamp)
    lamps.push(lamp)
  }
  // 封闭母线（从套管到主变）
  addPipe(g, 0.42, 8.0, 'z', [8.5, cy + 5.0, 0], mat(0x9aa5ae, { metalness: 0.6 }))
  // 主变压器（箱体 + 散热片 + 高压套管）
  const trafo = boxMesh(7.0, 6.0, 8.0, mat(0x5d6b78, { metalness: 0.5, roughness: 0.45 }))
  trafo.position.set(13.5, y0 + 3.2, 0)
  g.add(trafo)
  for (let i = 0; i < 6; i++) {
    const fin = boxMesh(0.5, 5.0, 7.4, mat(0x6d7b88, { metalness: 0.5 }))
    fin.position.set(13.5 + (i % 2 ? 3.7 : -3.7), y0 + 3.2, 0)
    g.add(fin)
  }
  for (let i = 0; i < 3; i++) {
    const bush = cylMesh(0.45, 0.45, 3.4, insulMat, 10)
    bush.position.set(13.5, y0 + 7.8, -2.4 + i * 2.4)
    g.add(bush)
  }
  g.userData.topY = cy + 8
  g.userData._tpTick = [
    (t, dt) => {
      rotor.rotation.x += dt * 9.5
      lamps.forEach((l, i) => {
        l.material.emissiveIntensity = 0.9 + 0.9 * Math.abs(Math.sin(t * 2.4 + i * 2.1))
      })
    },
  ]
  return g
}

/* ============================ 5. 凝汽器 ============================ */
// 卧式壳体 + 喉部（接乏汽）+ 管束端盖 + 循环水进出管 + 热井水位 + 凝结水滴
function buildCondenser(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 22, 14)
  const cy = y0 + 4.2
  // 壳体（横置圆筒）
  const shell = cylMesh(3.8, 3.8, 15, bodyMat, 24)
  shell.rotation.z = Math.PI / 2
  shell.position.set(0, cy, 0)
  g.add(shell)
  // 两端端盖（管束板，带圈）
  ;[-7.6, 7.6].forEach((x) => {
    const head = cylMesh(3.9, 3.4, 1.2, mat(0x74808d, { metalness: 0.55, roughness: 0.4 }), 24)
    head.rotation.z = Math.PI / 2
    head.position.set(x, cy, 0)
    g.add(head)
    for (let i = 0; i < 2; i++) {
      const ring = new THREE.Mesh(new THREE.TorusGeometry(1.6 + i * 1.2, 0.16, 6, 20), mat(0x5b6672, { metalness: 0.6 }))
      ring.rotation.y = Math.PI / 2
      ring.position.set(x + (x < 0 ? -0.7 : 0.7), cy, 0)
      g.add(ring)
    }
  })
  // 喉部（上方接汽轮机排汽，梯形扩口）
  const throat = cylMesh(4.6, 2.6, 3.6, mat(C.shellBlue, { metalness: 0.45 }), 20)
  throat.position.set(0, cy + 4.2, 0)
  g.add(throat)
  // 热井（底部集水箱 + 水位）
  const hotwell = boxMesh(13, 2.4, 5.4, mat(0x5a6674, { metalness: 0.45 }))
  hotwell.position.set(0, y0 + 1.2, 0)
  g.add(hotwell)
  const water = boxMesh(12.6, 0.4, 5.0, mat(0x2f7fb0, { emissive: 0x1d5f86, emissiveIntensity: 0.5, transparent: true, opacity: 0.8 }))
  water.position.set(0, y0 + 2.1, 0)
  g.add(water)
  // 循环水进出管（蓝进 / 橙回）
  addPipe(g, 0.62, 6.0, 'z', [-7.6, cy, 4.4], mat(C.pipeWater, { metalness: 0.55 }))
  addPipe(g, 0.62, 6.0, 'z', [7.6, cy, 4.4], mat(C.pipeWarm, { metalness: 0.55 }))
  // 循环水流动颗粒（沿壳体方向循环）
  const drops = addPuffs(g, 6, 0.42, 0x5fc4f5, 0.5)
  drops.forEach((d, i) => { d.position.set(-7 + i * 2.8, cy - 0.6, 3.4) })
  // 凝结水滴（从喉部落入热井）
  const conds = addPuffs(g, 5, 0.3, 0xbfe4f7, 0.55)
  conds.forEach((d, i) => { d.position.set(-4 + i * 2, cy + 2.4 - i * 0.6, 0) })

  g.userData.topY = cy + 8
  g.userData._tpTick = [
    (t, dt) => {
      water.position.y = y0 + 2.1 + 0.08 * Math.sin(t * 2.2)
      drops.forEach((d) => {
        d.position.x += dt * 5.2
        if (d.position.x > 7.5) d.position.x = -7.5
        d.material.opacity = 0.35 + 0.25 * Math.abs(Math.sin(t * 8 + d.position.x))
      })
      conds.forEach((d, i) => {
        d.position.y -= dt * (2.2 + i * 0.2)
        if (d.position.y < y0 + 2.2) d.position.y = cy + 2.4
        d.material.opacity = 0.25 + 0.35 * ((d.position.y - y0 - 2.2) / 5)
      })
    },
  ]
  return g
}

/* ============================ 6. 冷却塔与循环水泵 ============================ */
// 双曲线自然通风冷却塔（斜支柱 + 塔筒 + 填料 + 水池）+ 循环水泵 + 塔顶羽流
function buildCoolingTower(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 24, 24)
  const H = 17
  // 双曲线塔筒：r(y) = rThroat * sqrt(1 + ((y - yT)/c)^2)
  const pts = []
  const rThroat = 4.4, yT = H * 0.78, c = 9.0, rMax = 9.0
  for (let i = 0; i <= 16; i++) {
    const y = (i / 16) * H
    let r = rThroat * Math.sqrt(1 + ((y - yT) / c) ** 2)
    if (r > rMax) r = rMax
    pts.push(new THREE.Vector2(r, y))
  }
  const shellMat = mat(0xb9c1c8, { roughness: 0.85, metalness: 0.05, side: THREE.DoubleSide })
  const tower = new THREE.Mesh(new THREE.LatheGeometry(pts, 40), shellMat)
  tower.position.y = y0 + 5.2
  g.add(tower)
  // 塔顶环梁
  const ring = new THREE.Mesh(new THREE.TorusGeometry(rThroat * Math.sqrt(1 + ((H - yT) / c) ** 2) + 0.05, 0.28, 8, 40), mat(0x9aa5ae, { roughness: 0.7 }))
  ring.rotation.x = Math.PI / 2
  ring.position.y = y0 + 5.2 + H
  g.add(ring)
  // 斜支柱（V 形，塔筒底部支撑）
  const legMat = mat(C.concrete, { roughness: 0.9 })
  for (let i = 0; i < 10; i++) {
    const a = (i / 10) * Math.PI * 2
    const leg = cylMesh(0.42, 0.5, 5.6, legMat, 8)
    leg.position.set(Math.cos(a) * 7.4, y0 + 2.6, Math.sin(a) * 7.4)
    leg.rotation.z = -Math.cos(a) * 0.28
    leg.rotation.x = Math.sin(a) * 0.28
    g.add(leg)
  }
  // 填料层（塔内淋水填料，半透明环）
  const fill = cylMesh(7.6, 7.6, 1.4, mat(0x6b7a86, { transparent: true, opacity: 0.45, roughness: 0.9 }), 28)
  fill.position.y = y0 + 6.6
  g.add(fill)
  // 集水池（圆盘 + 水面）
  const basin = cylMesh(9.6, 9.6, 1.4, mat(C.concrete, { roughness: 0.9 }), 32)
  basin.position.y = y0 + 0.7
  g.add(basin)
  const pool = cylMesh(9.0, 9.0, 0.3, mat(0x2f7fb0, { transparent: true, opacity: 0.75, emissive: 0x1d5f86, emissiveIntensity: 0.35 }), 32)
  pool.position.y = y0 + 1.5
  g.add(pool)
  // 循环水泵房（塔旁：泵体 + 电机）
  const ph = y0 + 1.6
  const pump = cylMesh(1.9, 1.9, 2.4, mat(0x5a6a7a, { metalness: 0.55, roughness: 0.35 }), 18)
  pump.rotation.z = Math.PI / 2
  pump.position.set(11.5, ph, 6.5)
  g.add(pump)
  addMotor(g, 14.6, ph, 6.5, 1.5, 3.6)
  // 循环水进出管（蓝供 / 橙回）
  addPipe(g, 0.6, 9.0, 'x', [7.0, ph + 0.2, 6.5], mat(C.pipeWater, { metalness: 0.55 }))
  addPipe(g, 0.6, 9.0, 'x', [7.0, ph + 2.4, 6.5], mat(C.pipeWarm, { metalness: 0.55 }))
  // 泵叶轮
  const imp = new THREE.Group()
  imp.position.set(11.5, ph, 6.5)
  for (let i = 0; i < 5; i++) {
    const b2 = boxMesh(0.2, 1.5, 0.5, mat(0xc3ccd4, { metalness: 0.8, roughness: 0.25 }))
    b2.position.y = 0.75
    const wrap = new THREE.Group()
    wrap.add(b2)
    wrap.rotation.z = (i / 5) * Math.PI * 2
    imp.add(wrap)
  }
  imp.rotation.y = Math.PI / 2
  g.add(imp)
  // 塔顶羽流（白色水汽团上升扩散）
  const plume = addPuffs(g, 9, 2.0, 0xf2f7fa, 0.34)
  plume.forEach((p, i) => { p.position.set((Math.random() - 0.5) * 3, y0 + 5.2 + H + i * 1.2, (Math.random() - 0.5) * 3) })

  g.userData.topY = y0 + 5.2 + H + 14
  g.userData._tpTick = [
    (t, dt) => {
      imp.rotation.z += dt * 4.2
      pool.material.opacity = 0.7 + 0.08 * Math.sin(t * 1.8)
      plume.forEach((p, i) => {
        p.position.y += dt * (2.0 + i * 0.1)
        p.position.x += Math.sin(t * 0.6 + i) * dt * 0.9
        const k = (p.position.y - (y0 + 5.2 + H)) / 14
        p.scale.setScalar(2.0 + k * 3.2)
        p.material.opacity = Math.max(0, 0.34 * (1 - k))
        if (p.position.y > y0 + 5.2 + H + 14) {
          p.position.set((Math.random() - 0.5) * 3, y0 + 5.2 + H, (Math.random() - 0.5) * 3)
          p.scale.setScalar(2.0)
        }
      })
    },
  ]
  return g
}

/* ============================ 7. 给水与除氧 ============================ */
// 除氧器（卧式筒 + 除氧塔头）+ 给水泵（叶轮旋转）+ 高压加热器 + 汽水管道
function buildFeedwater(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 24, 14)
  const cy = y0 + 5.4
  // 除氧器水箱（卧式大圆筒）
  const tank = cylMesh(3.0, 3.0, 13, bodyMat, 24)
  tank.rotation.z = Math.PI / 2
  tank.position.set(-3.5, cy, 0)
  g.add(tank)
  // 除氧塔头（竖立小塔，顶部）
  const head = cylMesh(1.5, 1.8, 4.4, mat(0x8f9aa6, { metalness: 0.5 }), 18)
  head.position.set(-6.5, cy + 3.2, 0)
  g.add(head)
  // 水位
  const lvl = boxMesh(12.0, 0.35, 3.4, mat(0x2f7fb0, { emissive: 0x1d5f86, emissiveIntensity: 0.5, transparent: true, opacity: 0.8 }))
  lvl.position.set(-3.5, cy - 1.2, 0)
  g.add(lvl)
  // 除氧器排气（冒汽）
  const vents = addPuffs(g, 5, 0.55, 0xeef4f8, 0.3)
  vents.forEach((v, i) => { v.position.set(-6.5, cy + 5.6 + i * 0.8, 0) })
  // 高压加热器（两台竖式换热器）
  ;[[3.5, 0], [6.5, 0]].forEach(([x, z], i) => {
    const h = cylMesh(1.5, 1.5, 8.0, mat(C.shellBlue, { metalness: 0.5, roughness: 0.4 }), 18)
    h.position.set(x, y0 + 4.2, z)
    g.add(h)
    const capTop = cylMesh(1.7, 1.5, 0.7, mat(0x74808d, { metalness: 0.55 }), 18)
    capTop.position.set(x, y0 + 8.4, z)
    g.add(capTop)
  })
  // 电动给水泵（泵体 + 电机，叶轮旋转）
  const py = y0 + 2.0
  const pump = cylMesh(1.8, 1.8, 2.6, mat(0x5a6a7a, { metalness: 0.55, roughness: 0.35 }), 18)
  pump.rotation.z = Math.PI / 2
  pump.position.set(11.0, py, 0)
  g.add(pump)
  addMotor(g, 14.0, py, 0, 1.6, 3.8)
  const imp = new THREE.Group()
  imp.position.set(11.0, py, 0)
  for (let i = 0; i < 5; i++) {
    const b2 = boxMesh(0.2, 1.4, 0.5, mat(0xc3ccd4, { metalness: 0.8, roughness: 0.25 }))
    b2.position.y = 0.7
    const wrap = new THREE.Group()
    wrap.add(b2)
    wrap.rotation.z = (i / 5) * Math.PI * 2
    imp.add(wrap)
  }
  imp.rotation.y = Math.PI / 2
  g.add(imp)
  // 给水管道（蓝：去锅炉省煤器）+ 凝结水来管
  addPipe(g, 0.6, 10.0, 'x', [6.0, py + 3.2, 0], mat(C.pipeWater, { metalness: 0.55 }))
  addPipe(g, 0.55, 8.0, 'x', [-10.0, py + 1.2, 3.4], mat(0x7ec1ec, { metalness: 0.5 }))

  g.userData.topY = cy + 9
  g.userData._tpTick = [
    (t, dt) => {
      imp.rotation.z += dt * 4.6
      lvl.position.y = cy - 1.2 + 0.1 * Math.sin(t * 2)
      vents.forEach((v, i) => {
        v.position.y += dt * (1.3 + i * 0.1)
        const k = (v.position.y - (cy + 5.6)) / 7
        v.scale.setScalar(0.55 + k * 1.6)
        v.material.opacity = Math.max(0, 0.32 * (1 - k))
        if (v.position.y > cy + 12.6) { v.position.y = cy + 5.6; v.scale.setScalar(0.55) }
      })
    },
  ]
  return g
}

/* ============================ 8. 脱硝 SCR ============================ */
// 反应器竖井（半透明可见催化剂层）+ 进出口烟道 + 喷氨格栅 + 烟气下行 + 催化剂微光
function buildDenitration(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 18, 14)
  const H = 16
  // 反应器竖井（外壳半透明，便于看到内部催化剂层）
  const shellMat = mat(0x7f8b96, { metalness: 0.4, roughness: 0.55, transparent: true, opacity: 0.62 })
  const shaft = boxMesh(9.5, H, 9.5, shellMat)
  shaft.position.y = y0 + H / 2
  g.add(shaft)
  // 钢架
  addColumns(g, [-5.2, 5.2], [-5.2, 5.2], H + 1.5, y0, 0.65)
  // 催化剂层（三层，层间发光表示反应活性）
  const layers = []
  for (let i = 0; i < 3; i++) {
    const lm = mat(0x4b5f74, { emissive: 0x2b6f9e, emissiveIntensity: 0.55, roughness: 0.7, metalness: 0.3 })
    const layer = boxMesh(8.0, 1.5, 8.0, lm)
    layer.position.y = y0 + 4.0 + i * 4.2
    g.add(layer)
    // 层内蜂窝格栅
    for (let k = 0; k < 4; k++) {
      const cell = boxMesh(7.6, 0.3, 1.5, mat(0x2f3d4c, { roughness: 0.85 }))
      cell.position.set(0, y0 + 4.0 + i * 4.2, -3 + k * 2)
      g.add(cell)
    }
    layers.push(layer)
  }
  // 顶部入口烟道（弯头）+ 底部出口烟道
  addPipe(g, 1.5, 7.0, 'x', [-8.5, y0 + H - 1.5, 0], mat(C.pipeFlue, { metalness: 0.45, roughness: 0.6 }))
  addPipe(g, 1.5, 6.0, 'y', [-11.5, y0 + H - 4.5, 0], mat(C.pipeFlue, { metalness: 0.45, roughness: 0.6 }))
  addPipe(g, 1.5, 7.0, 'x', [8.6, y0 + 2.2, 0], mat(C.pipeFlue, { metalness: 0.45, roughness: 0.6 }))
  // 喷氨格栅（顶部横管 + 喷嘴）
  const grid = addPipe(g, 0.35, 9.0, 'z', [0, y0 + H - 3.0, 0], mat(0xa9b3bc, { metalness: 0.6 }))
  for (let i = 0; i < 4; i++) {
    const noz = cylMesh(0.12, 0.28, 0.7, mat(0x8b98a6, { metalness: 0.6 }), 8)
    noz.position.set(0, y0 + H - 3.5, -3 + i * 2)
    g.add(noz)
  }
  // 烟气颗粒（自上而下穿过催化剂层）
  const smoke = addPuffs(g, 7, 1.1, 0xb9c0c7, 0.28)
  smoke.forEach((s, i) => { s.position.set((Math.random() - 0.5) * 5, y0 + H - 2 - i * 1.8, (Math.random() - 0.5) * 5) })
  // 氨雾（喷氨格栅喷出）
  const nh3 = addPuffs(g, 4, 0.4, 0xd8e8f0, 0.3)
  nh3.forEach((s, i) => { s.position.set(-2 + i, y0 + H - 4.0, -2 + i * 0.8) })

  g.userData.topY = y0 + H + 3
  g.userData._tpTick = [
    (t, dt) => {
      layers.forEach((l, i) => {
        l.material.emissiveIntensity = 0.4 + 0.3 * Math.abs(Math.sin(t * 2.2 + i * 1.3))
      })
      smoke.forEach((s) => {
        s.position.y -= dt * 3.0
        if (s.position.y < y0 + 1.5) s.position.y = y0 + H - 2
        s.material.opacity = 0.16 + 0.18 * Math.abs(Math.sin(t * 4 + s.position.y))
      })
      nh3.forEach((s, i) => {
        s.position.y -= dt * 1.6
        s.scale.setScalar(0.4 + 0.5 * Math.abs(Math.sin(t * 3 + i)))
        if (s.position.y < y0 + H - 8) s.position.y = y0 + H - 4.0
      })
      grid.rotation.x += dt * 0.2
    },
  ]
  return g
}

/* ============================ 9. 除尘（电除尘/布袋） ============================ */
// 箱体 + 进出喇叭口 + 灰斗 + 内部极板（振打清灰）+ 粉尘下落
function buildDedust(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 24, 14)
  const cy = y0 + 6.6
  // 箱体（半透明外壳，可见内部极板）
  const shellMat = mat(0x77828d, { metalness: 0.4, roughness: 0.55, transparent: true, opacity: 0.6 })
  const box = boxMesh(16, 8.0, 10, shellMat)
  box.position.y = cy
  g.add(box)
  // 进/出口喇叭
  const inlet = cylMesh(4.6, 2.2, 4.0, mat(C.pipeFlue, { metalness: 0.45, roughness: 0.6 }), 20)
  inlet.rotation.z = Math.PI / 2
  inlet.position.set(-10.0, cy, 0)
  g.add(inlet)
  const outlet = cylMesh(2.2, 4.6, 4.0, mat(C.pipeFlue, { metalness: 0.45, roughness: 0.6 }), 20)
  outlet.rotation.z = Math.PI / 2
  outlet.position.set(10.0, cy, 0)
  g.add(outlet)
  // 内部极板/滤袋阵列（竖直悬挂）
  const plates = []
  for (let i = 0; i < 7; i++) {
    const p = boxMesh(0.22, 6.4, 8.4, mat(0x9aa5ae, { metalness: 0.5, roughness: 0.5 }))
    p.position.set(-6 + i * 2.0, cy - 0.4, 0)
    g.add(p)
    plates.push(p)
  }
  // 振打锤（顶部，周期上下敲击）
  const hammer = boxMesh(1.6, 1.0, 1.6, mat(0x5c6672, { metalness: 0.6 }))
  hammer.position.set(-4.5, cy + 5.2, 0)
  g.add(hammer)
  // 灰斗（三只倒锥 + 卸灰阀）
  const hoppers = []
  for (let i = 0; i < 3; i++) {
    const hx = -5.5 + i * 5.5
    const hop = cylMesh(2.6, 0.5, 4.4, mat(0x6d7885, { metalness: 0.45, roughness: 0.55 }), 16)
    hop.position.set(hx, y0 + 2.6, 0)
    g.add(hop)
    const valve = boxMesh(1.6, 0.8, 1.6, mat(0x47525d, { metalness: 0.5 }))
    valve.position.set(hx, y0 + 0.6, 0)
    g.add(valve)
    // 灰斗料位（发光指示积灰）
    const lvl = cylMesh(1.6, 0.5, 1.2, mat(0xa89a86, { emissive: 0x6b5a3a, emissiveIntensity: 0.35, transparent: true, opacity: 0.8 }), 14)
    lvl.position.set(hx, y0 + 3.2, 0)
    g.add(lvl)
    hoppers.push(lvl)
  }
  // 粉尘颗粒（从极板落入灰斗）
  const dust = addPuffs(g, 8, 0.34, 0xa89a86, 0.35)
  dust.forEach((d, i) => { d.position.set(-6 + (i % 7) * 2.0, cy - 2 - Math.random() * 4, -3 + (i % 4) * 2) })

  g.userData.topY = cy + 8
  g.userData._tpTick = [
    (t, dt) => {
      // 振打：锤体周期下落敲击，极板同步微振
      const beat = Math.sin(t * 1.6)
      hammer.position.y = cy + 5.2 - 0.9 * Math.max(0, beat)
      plates.forEach((p, i) => {
        p.position.y = cy - 0.4 + 0.06 * Math.sin(t * 9 + i) * Math.max(0, beat)
      })
      hoppers.forEach((h, i) => {
        h.material.emissiveIntensity = 0.25 + 0.2 * Math.abs(Math.sin(t * 1.2 + i))
      })
      dust.forEach((d, i) => {
        d.position.y -= dt * (1.6 + (i % 3) * 0.3)
        if (d.position.y < y0 + 2.8) d.position.y = cy - 2
        d.material.opacity = 0.15 + 0.3 * ((d.position.y - y0 - 2.8) / 8)
      })
    },
  ]
  return g
}

/* ============================ 10. 脱硫吸收塔（石灰石-石膏法） ============================ */
// 塔体 + 三层喷淋（液滴下落）+ 浆液池（搅拌器旋转）+ 氧化风 + 烟道 + 石膏排出
function buildDesulfurization(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 20, 18)
  const H = 19
  // 塔体（立式圆筒）
  const tower = cylMesh(4.6, 4.6, H, bodyMat, 28)
  tower.position.y = y0 + H / 2 + 1.0
  g.add(tower)
  // 锥形塔底（浆液池）
  const cone = cylMesh(4.6, 3.0, 3.4, mat(0x6d7885, { metalness: 0.45, roughness: 0.55 }), 28)
  cone.position.y = y0 + 1.7
  g.add(cone)
  // 浆液液面（半透明，缓慢波动）
  const slurry = cylMesh(4.3, 4.3, 0.35, mat(C.slurry, { transparent: true, opacity: 0.8, roughness: 0.9 }), 28)
  slurry.position.y = y0 + 5.2
  g.add(slurry)
  // 喷淋层（三层环管 + 喷嘴）
  const sprays = []
  for (let i = 0; i < 3; i++) {
    const y = y0 + 8.5 + i * 3.2
    const ring = new THREE.Mesh(new THREE.TorusGeometry(4.0, 0.22, 6, 26), mat(0x9aa5ae, { metalness: 0.6 }))
    ring.rotation.x = Math.PI / 2
    ring.position.y = y
    g.add(ring)
    for (let k = 0; k < 6; k++) {
      const a = (k / 6) * Math.PI * 2
      const noz = cylMesh(0.1, 0.3, 0.6, mat(0x8b98a6, { metalness: 0.6 }), 8)
      noz.position.set(Math.cos(a) * 4.0, y - 0.5, Math.sin(a) * 4.0)
      g.add(noz)
    }
    // 每层喷淋液滴
    const drops = addPuffs(g, 5, 0.32, 0xd9d3c0, 0.5)
    drops.forEach((d, k) => {
      const a = (k / 5) * Math.PI * 2
      d.position.set(Math.cos(a) * 3.2, y - 1.2 - k * 0.5, Math.sin(a) * 3.2)
    })
    sprays.push(drops)
  }
  // 氧化风管（插入浆液池）
  addPipe(g, 0.35, 8.0, 'x', [7.0, y0 + 4.0, 4.5], mat(0x8b98a6, { metalness: 0.55 }))
  // 进出口烟道（下部进、顶部出）
  addPipe(g, 1.5, 7.0, 'x', [-8.0, y0 + 7.0, 0], mat(C.pipeFlue, { metalness: 0.45, roughness: 0.6 }))
  addPipe(g, 1.4, 8.0, 'x', [8.4, y0 + H - 1.0, 0], mat(0xa8b2ba, { metalness: 0.45, roughness: 0.55 }))
  // 石膏排出泵
  const py = y0 + 1.8
  const pump = cylMesh(1.5, 1.5, 2.2, mat(0x5a6a7a, { metalness: 0.55, roughness: 0.35 }), 16)
  pump.rotation.z = Math.PI / 2
  pump.position.set(10.5, py, 5.5)
  g.add(pump)
  addMotor(g, 13.2, py, 5.5, 1.3, 3.2)
  // 侧进式搅拌器（桨叶旋转）
  const stir = new THREE.Group()
  stir.position.set(-4.2, y0 + 4.4, 0)
  for (let i = 0; i < 4; i++) {
    const b2 = boxMesh(0.18, 1.2, 0.5, mat(0xc3ccd4, { metalness: 0.8, roughness: 0.25 }))
    b2.position.y = 0.6
    const wrap = new THREE.Group()
    wrap.add(b2)
    wrap.rotation.z = (i / 4) * Math.PI * 2
    stir.add(wrap)
  }
  stir.rotation.z = Math.PI / 2
  g.add(stir)
  // 塔顶除雾器 + 净烟气出口
  const demister = cylMesh(4.4, 4.4, 1.2, mat(0xb9c1c8, { transparent: true, opacity: 0.5, roughness: 0.85 }), 26)
  demister.position.y = y0 + H + 0.2
  g.add(demister)

  g.userData.topY = y0 + H + 4
  g.userData._tpTick = [
    (t, dt) => {
      stir.rotation.y += dt * 3.4
      slurry.position.y = y0 + 5.2 + 0.12 * Math.sin(t * 1.5)
      sprays.forEach((drops, li) => {
        drops.forEach((d, i) => {
          d.position.y -= dt * (2.4 + i * 0.15)
          if (d.position.y < y0 + 5.4) d.position.y = y0 + 8.5 + li * 3.2 - 1.2
          d.material.opacity = 0.25 + 0.3 * Math.abs(Math.sin(t * 5 + i + li))
        })
      })
    },
  ]
  return g
}

/* ============================ 11. 烟囱 ============================ */
// 钢筋混凝土外筒（锥筒 + 红白航标环）+ 航空障碍灯闪烁 + 爬梯 + 顶部烟羽
function buildStack(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 16, 16)
  const H = 28
  // 筒身（下粗上细，混凝土外筒）
  const shell = cylMesh(2.9, 4.6, H, mat(0xb0b8bf, { roughness: 0.85, metalness: 0.05 }), 30)
  shell.position.y = y0 + H / 2
  g.add(shell)
  // 红白航标环
  for (let i = 0; i < 4; i++) {
    const y = y0 + H - 2 - i * 6
    const r = 2.9 + (4.6 - 2.9) * (1 - (y - y0) / H)
    const band = new THREE.Mesh(new THREE.TorusGeometry(r, 0.24, 6, 30), mat(i % 2 ? 0xc4463a : 0xe8ecf0, { roughness: 0.8 }))
    band.rotation.x = Math.PI / 2
    band.position.y = y
    g.add(band)
  }
  // 顶部平台 + 航空障碍灯（红色闪烁）
  const topR = 3.1
  const plat = new THREE.Mesh(new THREE.TorusGeometry(topR + 0.5, 0.2, 6, 30), mat(C.hand, { metalness: 0.5 }))
  plat.rotation.x = Math.PI / 2
  plat.position.y = y0 + H
  g.add(plat)
  const lampMat = mat(0xff3b30, { emissive: 0xff2010, emissiveIntensity: 2.0 })
  const lamp = new THREE.Mesh(SPH, lampMat)
  lamp.scale.setScalar(0.55)
  lamp.position.y = y0 + H + 1.0
  g.add(lamp)
  // 爬梯（竖梯 + 横档）
  const ladder = boxMesh(0.5, H - 2, 0.2, mat(0x8b98a6, { metalness: 0.5 }))
  ladder.position.set(0, y0 + H / 2, 4.5)
  g.add(ladder)
  for (let i = 0; i < 14; i++) {
    const rung = boxMesh(1.3, 0.14, 0.14, mat(0x8b98a6, { metalness: 0.5 }))
    rung.position.set(0, y0 + 2 + i * 1.9, 4.5)
    g.add(rung)
  }
  // 底部烟道接口（净烟气进入）
  addPipe(g, 1.4, 7.0, 'x', [-7.4, y0 + 3.4, 0], mat(0xa8b2ba, { metalness: 0.45, roughness: 0.55 }))
  // 烟羽（白烟团上升扩散）
  const plume = addPuffs(g, 8, 1.8, 0xeaf0f4, 0.3)
  plume.forEach((p, i) => {
    p.position.set((Math.random() - 0.5) * 2, y0 + H + 1.6 + i * 1.6, (Math.random() - 0.5) * 2)
  })

  g.userData.topY = y0 + H + 16
  g.userData._tpTick = [
    (t, dt) => {
      lamp.material.emissiveIntensity = 0.6 + 2.2 * Math.pow(Math.max(0, Math.sin(t * 2.2)), 6)
      plume.forEach((p, i) => {
        p.position.y += dt * (2.4 + i * 0.1)
        p.position.x += Math.sin(t * 0.5 + i) * dt * 1.2
        const k = (p.position.y - (y0 + H + 1.6)) / 16
        p.scale.setScalar(1.8 + k * 3.6)
        p.material.opacity = Math.max(0, 0.3 * (1 - k))
        if (p.position.y > y0 + H + 17) {
          p.position.set((Math.random() - 0.5) * 2, y0 + H + 1.6, (Math.random() - 0.5) * 2)
          p.scale.setScalar(1.8)
        }
      })
    },
  ]
  return g
}

/* ============================ 12. 热网换热站（热电联产） ============================ */
// 板式换热器组 + 热网循环泵（2 台）+ 供/回水管（红/蓝）+ 水箱
function buildHeatNet(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 24, 14)
  // 板式换热器（多层板片 + 两端夹紧板）
  const plateMat = mat(0x9aa5ae, { metalness: 0.55, roughness: 0.4 })
  for (let i = 0; i < 12; i++) {
    const p = boxMesh(0.28, 5.2, 6.0, plateMat)
    p.position.set(-8 + i * 0.62, y0 + 3.4, 0)
    g.add(p)
  }
  ;[-8.6, -0.4].forEach((x) => {
    const clamp = boxMesh(0.9, 6.2, 6.6, mat(0x4f5c68, { metalness: 0.5, roughness: 0.5 }))
    clamp.position.set(x, y0 + 3.4, 0)
    g.add(clamp)
  })
  // 换热器接管（供/回）
  addPipe(g, 0.5, 4.0, 'y', [-8.6, y0 + 7.0, 1.8], mat(0xd0453a, { metalness: 0.5 }))
  addPipe(g, 0.5, 4.0, 'y', [-0.4, y0 + 7.0, -1.8], mat(0x3b7fd0, { metalness: 0.5 }))
  // 热网循环泵（两台，叶轮旋转）
  const pumps = []
  for (let i = 0; i < 2; i++) {
    const px = 3.5 + i * 6.5
    const py = y0 + 2.2
    const body = cylMesh(1.7, 1.7, 2.4, mat(0x5a6a7a, { metalness: 0.55, roughness: 0.35 }), 18)
    body.rotation.z = Math.PI / 2
    body.position.set(px, py, 0)
    g.add(body)
    addMotor(g, px + 2.8, py, 0, 1.4, 3.4)
    const imp = new THREE.Group()
    imp.position.set(px, py, 0)
    for (let k = 0; k < 5; k++) {
      const b2 = boxMesh(0.18, 1.3, 0.5, mat(0xc3ccd4, { metalness: 0.8, roughness: 0.25 }))
      b2.position.y = 0.65
      const wrap = new THREE.Group()
      wrap.add(b2)
      wrap.rotation.z = (k / 5) * Math.PI * 2
      imp.add(wrap)
    }
    imp.rotation.y = Math.PI / 2
    g.add(imp)
    pumps.push(imp)
  }
  // 供/回水总管（红供 / 蓝回）+ 流向颗粒
  addPipe(g, 0.6, 14.0, 'x', [0, y0 + 8.6, 2.6], mat(0xd0453a, { metalness: 0.5 }))
  addPipe(g, 0.6, 14.0, 'x', [0, y0 + 8.6, -2.6], mat(0x3b7fd0, { metalness: 0.5 }))
  const hot = addPuffs(g, 5, 0.35, 0xff8a72, 0.5)
  hot.forEach((d, i) => { d.position.set(-6 + i * 3, y0 + 8.6, 2.6) })
  const cold = addPuffs(g, 5, 0.35, 0x7ec1ec, 0.5)
  cold.forEach((d, i) => { d.position.set(6 - i * 3, y0 + 8.6, -2.6) })
  // 补水箱
  const tank = cylMesh(2.2, 2.2, 4.4, bodyMat, 18)
  tank.position.set(11.0, y0 + 3.0, -4.0)
  g.add(tank)

  g.userData.topY = y0 + 13
  g.userData._tpTick = [
    (t, dt) => {
      pumps.forEach((imp, i) => { imp.rotation.z += dt * (4.0 + i * 0.4) })
      hot.forEach((d) => {
        d.position.x += dt * 4.4
        if (d.position.x > 7) d.position.x = -7
        d.material.opacity = 0.3 + 0.3 * Math.abs(Math.sin(t * 7 + d.position.x))
      })
      cold.forEach((d) => {
        d.position.x -= dt * 4.4
        if (d.position.x < -7) d.position.x = 7
        d.material.opacity = 0.3 + 0.3 * Math.abs(Math.sin(t * 7 + d.position.x))
      })
    },
  ]
  return g
}

/* ============================ 12. 除灰渣系统（底渣 + 飞灰 → 灰库） ============================ */
// 渣仓/捞渣机（左侧底渣）+ 气力输灰管与气化风机（中部）+ 灰库筒仓与卸料装车（右侧飞灰）
function buildAshHandling(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 28, 16)
  // —— 渣仓：倒锥斗 + 筒身（湿式底渣）
  const slagMat = mat(0x5f5a52, { metalness: 0.35, roughness: 0.7 })
  const hopper = cylMesh(3.2, 0.9, 4.6, slagMat, 18)
  hopper.position.set(-9.5, y0 + 2.6, 0)
  g.add(hopper)
  const slagBin = cylMesh(3.2, 3.2, 5.4, mat(0x6b665e, { metalness: 0.4, roughness: 0.6 }), 18)
  slagBin.position.set(-9.5, y0 + 7.6, 0)
  g.add(slagBin)
  // —— 刮板捞渣机（斜置槽 + 循环刮板）
  const trough = boxMesh(7.5, 0.7, 2.6, mat(0x4c545e, { metalness: 0.5, roughness: 0.5 }))
  trough.position.set(-9.5, y0 + 0.9, 3.6)
  trough.rotation.x = -0.14
  g.add(trough)
  const flights = []
  for (let i = 0; i < 4; i++) {
    const fl = boxMesh(0.3, 0.9, 2.2, mat(0x9aa5ae, { metalness: 0.6, roughness: 0.35 }))
    fl.position.set(-12.5 + i * 2.0, y0 + 1.5, 3.6)
    g.add(fl)
    flights.push(fl)
  }
  // —— 气力输灰管 + 气化风机（飞灰由除尘器气力输送入灰库）
  addPipe(g, 0.55, 12.0, 'x', [-4.0, y0 + 4.2, -3.2], mat(0x8a939c, { metalness: 0.6, roughness: 0.4 }))
  const blower = cylMesh(1.2, 1.2, 2.0, mat(0x5a6a7a, { metalness: 0.55 }), 14)
  blower.rotation.z = Math.PI / 2
  blower.position.set(-10.2, y0 + 4.2, -3.2)
  g.add(blower)
  addMotor(g, -12.4, y0 + 4.2, -3.2, 1.0, 2.4)
  // —— 灰库筒仓：锥底 + 筒身 + 顶盖 + 库顶布袋除尘器
  const silo = cylMesh(5.0, 5.0, 12.0, bodyMat, 24)
  silo.position.set(6.0, y0 + 6.8, 0)
  g.add(silo)
  const cone = cylMesh(5.0, 1.1, 4.2, mat(0x6f6a62, { metalness: 0.4, roughness: 0.65 }), 24)
  cone.position.set(6.0, y0 + 2.1, 0)
  g.add(cone)
  const roof = cylMesh(5.4, 5.0, 1.0, mat(0x8a939c, { metalness: 0.5 }), 24)
  roof.position.set(6.0, y0 + 13.3, 0)
  g.add(roof)
  const bagFilter = boxMesh(3.0, 2.2, 3.0, mat(0x77828d, { metalness: 0.45, roughness: 0.55, transparent: true, opacity: 0.85 }))
  bagFilter.position.set(6.0, y0 + 15.2, 0)
  g.add(bagFilter)
  // 库内料位（发光面，随料位起伏）
  const level = cylMesh(4.7, 2.4, 3.0, mat(0xa89a86, { emissive: 0x5a4a2a, emissiveIntensity: 0.3, transparent: true, opacity: 0.75 }), 22)
  level.position.set(6.0, y0 + 4.4, 0)
  g.add(level)
  // 卸料口 + 干灰散装头（装车外运综合利用）
  addPipe(g, 0.5, 3.2, 'y', [6.0, y0 + 0.6, 0], mat(0x6d7885, { metalness: 0.5 }))
  const spout = cylMesh(1.4, 0.9, 1.8, mat(0x9aa5ae, { metalness: 0.55 }), 14)
  spout.position.set(6.0, y0 - 1.4, 0)
  g.add(spout)
  // 输灰管内的飞灰颗粒
  const ash = addPuffs(g, 10, 0.3, 0xb0a596, 0.4)
  ash.forEach((d, i) => { d.position.set(-9 + i * 1.6, y0 + 4.2, -3.2) })

  g.userData.topY = y0 + 17
  g.userData._tpTick = [
    (t, dt) => {
      flights.forEach((fl) => {
        fl.position.x += dt * 2.2
        if (fl.position.x > -6.2) fl.position.x = -12.5
      })
      ash.forEach((d) => {
        d.position.x += dt * 5.0
        if (d.position.x > 5.4) d.position.x = -9.8
        d.material.opacity = 0.2 + 0.35 * Math.abs(Math.sin(t * 6 + d.position.x))
      })
      level.material.emissiveIntensity = 0.22 + 0.18 * Math.abs(Math.sin(t * 0.9))
    },
  ]
  return g
}

/* ============================ 13. 石膏脱水系统（石膏浆液 → 成品石膏） ============================ */
// 旋流器组（浓缩）+ 真空皮带脱水机（脱水成饼）+ 石膏库（成品堆存外售）
function buildGypsum(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 26, 14)
  // —— 石膏旋流器组（3 只：上筒 + 下锥）
  const cycMat = mat(0x8f9aa4, { metalness: 0.45, roughness: 0.5 })
  const cyclones = []
  for (let i = 0; i < 3; i++) {
    const x = -9 + i * 3.4
    const up = cylMesh(1.6, 1.6, 3.2, cycMat, 16)
    up.position.set(x, y0 + 6.4, 0)
    g.add(up)
    const cone = cylMesh(1.6, 0.35, 3.4, cycMat, 16)
    cone.position.set(x, y0 + 3.1, 0)
    g.add(cone)
    cyclones.push(cone)
  }
  // 进料总管（石膏浆液自吸收塔排出泵来）
  addPipe(g, 0.5, 10.0, 'x', [-6.5, y0 + 9.2, 0], mat(0xb8b09a, { metalness: 0.35, roughness: 0.6 }))
  // —— 真空皮带脱水机：皮带 + 托辊 + 真空盒 + 驱动辊
  const belt = boxMesh(15.0, 0.5, 4.0, mat(0x4f5c68, { metalness: 0.5, roughness: 0.5 }))
  belt.position.set(3.0, y0 + 4.6, 0)
  g.add(belt)
  const rollers = []
  for (let i = 0; i < 6; i++) {
    const r = cylMesh(0.55, 0.55, 4.2, mat(0x9aa5ae, { metalness: 0.6, roughness: 0.35 }), 12)
    r.rotation.x = Math.PI / 2
    r.position.set(-3.5 + i * 2.6, y0 + 4.0, 0)
    g.add(r)
    rollers.push(r)
  }
  const drive = cylMesh(1.3, 1.3, 4.4, mat(0x5a6a7a, { metalness: 0.55 }), 14)
  drive.rotation.x = Math.PI / 2
  drive.position.set(10.4, y0 + 4.6, 0)
  g.add(drive)
  rollers.push(drive)
  addMotor(g, 12.6, y0 + 4.6, 0, 1.2, 3.0)
  const vacBox = boxMesh(12.0, 1.0, 3.2, mat(0x6d7885, { metalness: 0.5, roughness: 0.5 }))
  vacBox.position.set(3.0, y0 + 3.2, 0)
  g.add(vacBox)
  // 皮带上的石膏滤饼（随皮带右移至成品端）
  const cakes = []
  for (let i = 0; i < 7; i++) {
    const c = boxMesh(1.5, 0.7, 3.2, mat(0xe8e2d0, { roughness: 0.85, metalness: 0.05 }))
    c.position.set(-3.6 + i * 2.2, y0 + 5.2, 0)
    g.add(c)
    cakes.push(c)
  }
  // —— 石膏库：挡墙 + 成品料堆（外售作建材原料）
  const wall = boxMesh(9.0, 2.4, 0.8, mat(0x7a746a, { roughness: 0.8 }))
  wall.position.set(3.0, y0 + 1.4, 4.6)
  g.add(wall)
  const pile = cylMesh(1.0, 4.4, 2.2, mat(0xded8c6, { roughness: 0.9, metalness: 0.02 }), 20)
  pile.position.set(3.0, y0 + 1.2, 0.4)
  g.add(pile)
  // 旋流器底流（浓浆落向皮带）的液滴
  const drops = addPuffs(g, 6, 0.26, 0xd8d2be, 0.45)
  drops.forEach((d, i) => { d.position.set(-9 + (i % 3) * 3.4, y0 + 1.8 - (i % 2) * 0.6, 0) })

  g.userData.topY = y0 + 12
  g.userData._tpTick = [
    (t, dt) => {
      rollers.forEach((r, i) => { r.rotation.z += dt * (3.0 + i * 0.2) })
      cakes.forEach((c) => {
        c.position.x += dt * 2.4
        if (c.position.x > 10.6) c.position.x = -4.2
      })
      cyclones.forEach((c, i) => {
        c.rotation.y += dt * (0.8 + i * 0.1)
      })
      drops.forEach((d, i) => {
        d.position.y -= dt * 2.2
        if (d.position.y < y0 + 1.0) d.position.y = y0 + 2.4
        d.material.opacity = 0.2 + 0.35 * Math.abs(Math.sin(t * 8 + i))
      })
      pile.scale.y = 1 + 0.06 * Math.sin(t * 0.7)
    },
  ]
  return g
}

/* ============================ 14. 系统内部设备：中速磨煤机 ============================ */
// 挂在「输煤制粉系统」小组内：立式磨筒体 + 旋转磨盘与磨辊 + 主电机 + 一次风入口 + 煤粉出口管
function buildMill(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 18, 14)
  const body = cylMesh(3.8, 4.4, 8.0, bodyMat, 20)
  body.position.set(0, y0 + 5.4, 0)
  g.add(body)
  // 上部锥形分离帽（粗粉回落再磨）
  const cap = cylMesh(1.7, 3.8, 3.2, mat(C.shellBlue, { metalness: 0.45 }), 20)
  cap.position.set(0, y0 + 11.0, 0)
  g.add(cap)
  // 煤粉出口管（去炉膛燃烧器）
  addPipe(g, 0.62, 5.6, 'y', [0, y0 + 14.6, 0], mat(C.coal, { roughness: 0.9 }))
  addPipe(g, 0.62, 7.0, 'x', [3.4, y0 + 17.4, 0], mat(C.coal, { roughness: 0.9 }))
  // 一次风入口（热风/冷风混合后自下部进入，起干燥与输送作用）
  addPipe(g, 0.85, 7.0, 'x', [-6.2, y0 + 2.6, 0], mat(C.pipeSteam))
  // 磨盘（水平旋转）
  const disc = cylMesh(3.1, 3.1, 0.7, mat(0x5c6672, { metalness: 0.6, roughness: 0.35 }), 18)
  disc.position.set(0, y0 + 2.0, 0)
  g.add(disc)
  // 磨辊（三只，绕磨盘公转）
  const rollers = []
  for (let i = 0; i < 3; i++) {
    const rg = new THREE.Group()
    rg.position.set(0, y0 + 3.2, 0)
    const r = cylMesh(1.15, 1.15, 1.6, mat(0xc3ccd4, { metalness: 0.75, roughness: 0.28 }), 14)
    r.rotation.z = Math.PI / 2
    r.position.set(2.0, 0, 0)
    rg.add(r)
    rg.rotation.y = (i / 3) * Math.PI * 2
    g.add(rg)
    rollers.push(rg)
  }
  // 主电机（底部侧面）+ 检修平台
  addMotor(g, 6.4, y0 + 2.2, 0, 1.7, 4.6)
  addPlatform(g, 15, 10, y0 + 9.6)
  g.userData.topY = y0 + 19
  g.userData._tpTick = [
    (t, dt) => {
      disc.rotation.y += dt * 2.8
      rollers.forEach((rg, i) => { rg.rotation.y += dt * (1.4 + i * 0.1) })
    },
  ]
  return g
}

/* ============================ 15. 系统内部设备：风机（送/引/一次/氧化） ============================ */
// 挂在所属系统小组内：蜗壳 + 进风喇叭口 + 出口扩散箱与风管 + 电机 + 高速旋转叶轮
function buildFanUnit(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 20, 14)
  const volMat = mat(C.shell, { metalness: 0.42, roughness: 0.5 })
  const volute = cylMesh(4.8, 4.8, 4.2, volMat, 22)
  volute.rotation.z = Math.PI / 2
  volute.position.set(1.6, y0 + 5.4, 0)
  g.add(volute)
  // 进风喇叭口（大口朝 -X）
  const inlet = cylMesh(1.8, 3.2, 3.2, mat(C.steel, { metalness: 0.5 }), 18)
  inlet.rotation.z = Math.PI / 2
  inlet.position.set(-3.6, y0 + 5.4, 0)
  g.add(inlet)
  // 出口扩散箱 + 风管
  const outlet = boxMesh(4.8, 3.6, 3.8, volMat)
  outlet.position.set(3.4, y0 + 10.2, 0)
  g.add(outlet)
  addPipe(g, 1.5, 6.0, 'y', [3.4, y0 + 14.0, 0], mat(C.pipeFlue))
  // 电机（右侧，轴沿 X）
  addMotor(g, 8.6, y0 + 5.4, 0, 1.9, 4.8)
  // 叶轮：Group 绕 X 自转（叶片绕轴均布）
  const impG = new THREE.Group()
  impG.position.set(-2.4, y0 + 5.4, 0)
  const hub = cylMesh(1.0, 1.0, 1.4, mat(0x4a5d72, { metalness: 0.6 }), 12)
  hub.rotation.z = Math.PI / 2
  impG.add(hub)
  for (let k = 0; k < 6; k++) {
    const b = boxMesh(0.22, 2.6, 0.9, mat(0xc3ccd4, { metalness: 0.8, roughness: 0.25 }))
    b.position.y = 1.5
    const wrap = new THREE.Group()
    wrap.add(b)
    wrap.rotation.x = (k / 6) * Math.PI * 2
    impG.add(wrap)
  }
  g.add(impG)
  // 气流粒子（沿 +X 穿过机体）
  const air = addPuffs(g, 6, 0.44, 0xbcd8ea, 0.4)
  air.forEach((d, i) => { d.position.set(-8 + i * 2.4, y0 + 5.4 + (i % 2 ? 1.2 : -1.2), 0) })
  g.userData.topY = y0 + 17
  g.userData._tpTick = [
    (t, dt) => {
      impG.rotation.x += dt * 9.0
      air.forEach((d, i) => {
        d.position.x += dt * 5.2
        if (d.position.x > 5) d.position.x = -8
        d.material.opacity = 0.25 + 0.3 * Math.abs(Math.sin(t * 6 + i))
      })
    },
  ]
  return g
}

/* ============================ 16. 系统内部设备：泵（给水/循环水/凝结水/浆液/热网） ============================ */
// 挂在所属系统小组内：泵壳 + 吸入管 + 排出管（竖直→水平）+ 电机与联轴器 + 叶轮
function buildPumpUnit(bodyMat) {
  const g = new THREE.Group()
  const y0 = addBase(g, 18, 12)
  const pm = mat(C.shellBlue, { metalness: 0.45, roughness: 0.4 })
  const casing = cylMesh(3.5, 3.5, 5.4, pm, 18)
  casing.position.set(3.0, y0 + 3.8, 0)
  g.add(casing)
  // 吸入侧短管 + 吸入总管（水平 -X）
  const inlet = cylMesh(1.5, 1.5, 2.4, mat(C.steel, { metalness: 0.5 }), 14)
  inlet.rotation.z = Math.PI / 2
  inlet.position.set(0.2, y0 + 3.8, 0)
  g.add(inlet)
  addPipe(g, 1.35, 7.0, 'x', [-4.0, y0 + 3.8, 0], mat(C.pipeWater))
  // 排出管（竖直上升后水平送出）
  addPipe(g, 1.25, 6.0, 'y', [3.0, y0 + 8.6, 0], mat(C.pipeWater))
  addPipe(g, 1.25, 5.0, 'x', [5.4, y0 + 11.4, 0], mat(C.pipeWater))
  // 电机 + 联轴器
  addMotor(g, -5.4, y0 + 3.8, 0, 1.8, 5.0)
  const coup = cylMesh(1.05, 1.05, 1.8, mat(C.dark), 12)
  coup.rotation.z = Math.PI / 2
  coup.position.set(-1.6, y0 + 3.8, 0)
  g.add(coup)
  // 叶轮（Group 绕 X 自转）
  const impG = new THREE.Group()
  impG.position.set(6.0, y0 + 3.8, 0)
  const hub = cylMesh(1.1, 1.1, 0.9, mat(0x4a5d72, { metalness: 0.6 }), 12)
  hub.rotation.z = Math.PI / 2
  impG.add(hub)
  for (let k = 0; k < 5; k++) {
    const b = boxMesh(0.2, 1.9, 0.7, mat(0xc3ccd4, { metalness: 0.8, roughness: 0.25 }))
    b.position.y = 1.1
    const wrap = new THREE.Group()
    wrap.add(b)
    wrap.rotation.x = (k / 5) * Math.PI * 2
    impG.add(wrap)
  }
  g.add(impG)
  // 介质流向粒子（吸入 → 排出上升）
  const flow = addPuffs(g, 5, 0.4, 0x5fb2ea, 0.45)
  flow.forEach((d, i) => { d.position.set(-7 + i * 2.6, y0 + 3.8, 0) })
  g.userData.topY = y0 + 13
  g.userData._tpTick = [
    (t, dt) => {
      impG.rotation.x += dt * 7.5
      flow.forEach((d, i) => {
        d.position.x += dt * 4.6
        if (d.position.x > 5.5) d.position.x = -7
        d.material.opacity = 0.25 + 0.3 * Math.abs(Math.sin(t * 6 + i))
      })
    },
  ]
  return g
}

/** 火电工序统一入口（scene.js 以 builder(bodyMat, anim) 调用，故按 type 包装） */
export function buildThermalPower(type, bodyMat) {
  switch (type) {
    case 'coal_handling': return buildCoalHandling(bodyMat)
    case 'boiler': return buildBoiler(bodyMat)
    case 'steam_turbine': return buildTurbine(bodyMat)
    case 'generator': return buildGenerator(bodyMat)
    case 'condenser': return buildCondenser(bodyMat)
    case 'cooling_tower': return buildCoolingTower(bodyMat)
    case 'feedwater': return buildFeedwater(bodyMat)
    case 'denitration': return buildDenitration(bodyMat)
    case 'dedust': return buildDedust(bodyMat)
    case 'desulfurization': return buildDesulfurization(bodyMat)
    case 'stack': return buildStack(bodyMat)
    case 'heat_net': return buildHeatNet(bodyMat)
    case 'ash_handling': return buildAshHandling(bodyMat)
    case 'gypsum_handling': return buildGypsum(bodyMat)
    // —— 系统内部的可调能源设备（挂在所属系统小组内，进入小组子场景可见）——
    case 'tp_mill': return buildMill(bodyMat)
    case 'tp_fd_fan': case 'tp_id_fan': case 'tp_pa_fan': case 'tp_oxi_fan': return buildFanUnit(bodyMat)
    case 'tp_feed_pump': case 'tp_circ_pump': case 'tp_cond_pump': return buildPumpUnit(bodyMat)
    case 'tp_slurry_pump': case 'tp_heat_pump': return buildPumpUnit(bodyMat)
    default: return buildBoiler(bodyMat)
  }
}

export default buildThermalPower
