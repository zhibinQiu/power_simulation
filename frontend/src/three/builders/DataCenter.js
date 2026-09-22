// 机房温控（数据中心）3D 模型构建器
// 覆盖：dc_chiller 冷却水（水箱+循环水泵） / dc_fan_cool 制冷风机（半导体制冷+风扇） /
//       dc_it 算力设备（机柜列）
// 动画钩子沿用 _ 前缀挂 userData（_fanBlades），由 scene.js 动画循环消费。
import * as THREE from 'three'
import { mat, boxMesh } from './utils.js'

// 机电设备通用底座（混凝土墩 + 钢格栅），与工辅设备保持同一套基座
function addSkid(group, w = 20, d = 14) {
  const base = boxMesh(w, 0.8, d, mat(0x202737, { roughness: 0.9 }))
  base.position.y = 0.4
  group.add(base)
  const pad = boxMesh(w + 2, 0.3, d + 2, mat(0x161d2c, { roughness: 1 }))
  pad.position.y = 0.15
  group.add(pad)
}

// 电机（带散热筋的工业涂装电机），轴向沿 X
function addMotor(group, x, y, z, len = 5) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 2.2, len, 20), mat(0x4a5d72, { metalness: 0.5, roughness: 0.4 }))
  m.rotation.z = Math.PI / 2
  m.position.set(x, y, z)
  group.add(m)
  for (let i = -1; i <= 1; i++) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(2.26, 0.11, 6, 20), mat(0x3a4a5c))
    ring.rotation.y = Math.PI / 2
    ring.position.set(x + i * (len / 3), y, z)
    group.add(ring)
  }
  return m
}

// 管段（沿指定轴），用于水管/风管
function addPipe(group, r, len, axis, pos, material) {
  const p = new THREE.Mesh(new THREE.CylinderGeometry(r, r, len, 16), material)
  if (axis === 'x') p.rotation.z = Math.PI / 2
  else if (axis === 'z') p.rotation.x = Math.PI / 2
  p.position.set(pos[0], pos[1], pos[2])
  group.add(p)
  return p
}

/* ========== 第一部分：冷却水（循环水系统：水箱 + 循环水泵） ========== */
function buildCoolingWater(bodyMat) {
  const g = new THREE.Group()
  addSkid(g, 20, 14)
  // 循环水箱（立式圆筒 + 顶盖）
  const tank = new THREE.Mesh(new THREE.CylinderGeometry(4.4, 4.4, 9.6, 28), bodyMat)
  tank.position.set(4.0, 5.8, 0)
  g.add(tank)
  const cap = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 4.4, 1.8, 24), mat(0x2c3a4c, { metalness: 0.4 }))
  cap.position.set(4.0, 11.5, 0)
  g.add(cap)
  // 上层回水偏热（暖色环）/ 下层低温水（冷色环）：一眼看出"回水温度上升"
  const warm = new THREE.Mesh(new THREE.TorusGeometry(4.46, 0.16, 6, 28), mat(0xd4803a, { emissive: 0x7a3a10, emissiveIntensity: 0.5 }))
  warm.rotation.x = Math.PI / 2
  warm.position.set(4.0, 9.3, 0)
  g.add(warm)
  const cold = new THREE.Mesh(new THREE.TorusGeometry(4.46, 0.16, 6, 28), mat(0x3b9ee0, { emissive: 0x1d6f9e, emissiveIntensity: 0.5 }))
  cold.rotation.x = Math.PI / 2
  cold.position.set(4.0, 3.4, 0)
  g.add(cold)
  // 循环水泵（泵体 + 电机）
  const pump = new THREE.Mesh(new THREE.CylinderGeometry(2.1, 2.1, 2.6, 22), mat(0x5a6a7a, { metalness: 0.5, roughness: 0.35 }))
  pump.rotation.z = Math.PI / 2
  pump.position.set(-4.4, 3.6, 0)
  g.add(pump)
  addMotor(g, -8.2, 3.6, 0, 4.4)
  addPipe(g, 0.42, 4.2, 'x', [-1.2, 3.6, 0], mat(0x7ec1ec, { metalness: 0.45, roughness: 0.4 }))
  // 出水（供水，蓝：去制冷风机给半导体制冷片散热）
  addPipe(g, 0.44, 6.4, 'y', [2.2, 6.6, 0], mat(0x3b9ee0, { metalness: 0.45, roughness: 0.4 }))
  addPipe(g, 0.44, 4.6, 'z', [2.2, 9.8, 2.6], mat(0x3b9ee0, { metalness: 0.45, roughness: 0.4 }))
  // 回水（橙：从制冷风机带回温度升高的循环水）
  addPipe(g, 0.44, 6.0, 'y', [7.2, 6.4, 0], mat(0xd4803a, { metalness: 0.45, roughness: 0.4 }))
  addPipe(g, 0.44, 4.6, 'z', [7.2, 9.4, 2.6], mat(0xd4803a, { metalness: 0.45, roughness: 0.4 }))
  g.userData.topY = 12.6
  return g
}

/* ========== 第二部分：制冷风机（半导体制冷片 + 风扇送风） ========== */
function buildCoolingFan(bodyMat) {
  const g = new THREE.Group()
  addSkid(g, 20, 14)
  const cy = 8.0
  // 风筒（轴流风道，轴线沿 X，开口圆筒）
  const duct = new THREE.Mesh(new THREE.CylinderGeometry(6.0, 6.2, 6.4, 32, 1, true), bodyMat)
  duct.rotation.z = Math.PI / 2
  duct.position.set(0, cy, 0)
  g.add(duct)
  // 风筒两端法兰圈
  ;[3.2, -3.2].forEach((x) => {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(6.05, 0.3, 8, 32), mat(0x5d6b7a, { metalness: 0.6, roughness: 0.35 }))
    ring.rotation.y = Math.PI / 2
    ring.position.set(x, cy, 0)
    g.add(ring)
  })
  // 出风侧护网（同心圈 + 十字筋）
  ;[2.4, 4.4].forEach((r) => {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(r, 0.1, 6, 28), mat(0x9fb0bd, { metalness: 0.5, roughness: 0.5 }))
    ring.rotation.y = Math.PI / 2
    ring.position.set(3.3, cy, 0)
    g.add(ring)
  })
  const spokeY = boxMesh(0.14, 12.2, 0.14, mat(0x9fb0bd, { metalness: 0.5 }))
  spokeY.position.set(3.3, cy, 0)
  g.add(spokeY)
  const spokeZ = boxMesh(0.14, 0.14, 12.2, mat(0x9fb0bd, { metalness: 0.5 }))
  spokeZ.position.set(3.3, cy, 0)
  g.add(spokeZ)
  // 扇叶（5 片带桨距角的叶片 + 轮毂）—— _fanBlades 由 scene.js 持续旋转（rotation.x）
  const blades = new THREE.Group()
  blades.rotation.y = Math.PI / 2
  blades.position.set(0.6, cy, 0)
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(1.3, 1.3, 1.9, 20), mat(0x46566a, { metalness: 0.6, roughness: 0.35 }))
  hub.rotation.z = Math.PI / 2
  blades.add(hub)
  const bladeMat = mat(0x7d8b99, { metalness: 0.55, roughness: 0.34, side: THREE.DoubleSide })
  for (let i = 0; i < 5; i++) {
    const wrap = new THREE.Group()
    const b = new THREE.Mesh(new THREE.BoxGeometry(1.25, 4.5, 0.32), bladeMat)
    b.position.y = 3.05
    b.rotation.y = 0.52 // 桨距角：叶片迎风倾斜，像真风扇
    wrap.add(b)
    wrap.rotation.z = (i / 5) * Math.PI * 2
    blades.add(wrap)
  }
  g.add(blades)
  g.userData._fanBlades = blades
  g.userData._fanPhase = 1.5
  // 驱动电机（后侧）
  addMotor(g, -7.6, cy, 0, 4.6)
  // 半导体制冷片（TEC）：冷端贴风道顶部，热端走循环水
  const tec = boxMesh(6.6, 1.3, 4.4, mat(0xd6dbe1, { metalness: 0.25, roughness: 0.55 }))
  tec.position.set(0, cy + 6.6, 0)
  g.add(tec)
  for (let i = -2; i <= 2; i++) {
    const fin = boxMesh(0.28, 1.1, 3.8, mat(0x8b98a6, { metalness: 0.5, roughness: 0.45 }))
    fin.position.set(i * 1.3, cy + 7.6, 0)
    g.add(fin)
  }
  // 水冷头（把制冷片热端热量交给循环水）+ 供/回水管
  const block = boxMesh(4.4, 2.6, 4.8, mat(0x39627f, { metalness: 0.6, roughness: 0.35 }))
  block.position.set(0, cy + 8.6, 0)
  g.add(block)
  addPipe(g, 0.42, 6.6, 'z', [1.2, cy + 8.6, 5.0], mat(0x3b9ee0, { metalness: 0.45, roughness: 0.4 }))
  addPipe(g, 0.42, 6.6, 'z', [-1.2, cy + 8.6, 5.0], mat(0xd4803a, { metalness: 0.45, roughness: 0.4 }))
  // 支腿（风筒落在底座上）
  ;[-4.8, 4.8].forEach((x) => {
    const leg = boxMesh(1.4, 1.6, 4.4, mat(0x2b3540, { roughness: 0.75 }))
    leg.position.set(x, 1.6, 0)
    g.add(leg)
  })
  g.userData.topY = cy + 10.4
  return g
}

/* ========== 第三部分：算力设备（机柜列） ========== */
function buildServerRacks(bodyMat) {
  const g = new THREE.Group()
  addSkid(g, 22, 14)
  const ledGreen = mat(0x5fe08a, { emissive: 0x2f9f5f, emissiveIntensity: 1.0 })
  const ledBlue = mat(0x4bb6e8, { emissive: 0x1f6f9e, emissiveIntensity: 0.9 })
  for (let i = 0; i < 3; i++) {
    const x = -7 + i * 7
    const rack = boxMesh(6, 14, 8, bodyMat)
    rack.position.set(x, 7.4, 0)
    g.add(rack)
    // 前面板（暗色）+ 服务器插槽 + 指示灯
    const face = boxMesh(5.5, 12.8, 0.3, mat(0x252f3a, { roughness: 0.6 }))
    face.position.set(x, 7.4, 4.1)
    g.add(face)
    for (let k = 0; k < 9; k++) {
      const y = 2.1 + k * 1.32
      const slot = boxMesh(4.7, 0.85, 0.34, mat(0x516276, { metalness: 0.5, roughness: 0.4 }))
      slot.position.set(x, y, 4.3)
      g.add(slot)
      const led = new THREE.Mesh(new THREE.SphereGeometry(0.16, 8, 6), k % 3 === 0 ? ledGreen : ledBlue)
      led.position.set(x + 2.15, y, 4.45)
      g.add(led)
    }
    // 顶部出风栅
    for (let k = 0; k < 3; k++) {
      const grill = boxMesh(5.0, 0.28, 0.5, mat(0x3d4b59))
      grill.position.set(x, 14.5, -2.4 + k * 2.4)
      g.add(grill)
    }
  }
  g.userData.topY = 15.2
  return g
}

/** 机房温控三部分统一入口（scene.js 以 builder(bodyMat, anim) 调用，故按 type 包装） */
export function buildDataCenter(type, bodyMat) {
  if (type === 'dc_chiller') return buildCoolingWater(bodyMat)
  if (type === 'dc_fan_cool') return buildCoolingFan(bodyMat)
  return buildServerRacks(bodyMat)
}

export default buildDataCenter
