// 工辅 3D 模型构建器
// 覆盖：blower 鼓风机 / hot_blast_stove 热风炉 / id_fan 引风机 / injector 喷吹系统 /
//       drive_supply 驱动电源 / electrode_reg 电极调节器 / belt_conv 皮带机 /
//       feeder 给料机 / cool_pump 冷却水泵 / aux_boiler 辅助锅炉 / oxy_plant 制氧机
// 按设备形态分四类造型：旋转机械 / 燃烧炉塔 / 输送给料 / 空分制气。
// 动画钩子统一以 _ 前缀挂到 userData，由 scene.js 动画循环消费。
import * as THREE from 'three'
import { mat, boxMesh, tankShellTex, steelTex, wallPanelTex } from './utils.js'

// 机电设备通用底座（混凝土墩 + 钢格栅）
function addSkid(group, w = 18, d = 13) {
  const base = boxMesh(w, 0.8, d, mat(0x202737, { roughness: 0.9 }))
  base.position.y = 0.4
  group.add(base)
  const pad = boxMesh(w + 2, 0.3, d + 2, mat(0x161d2c, { roughness: 1 }))
  pad.position.y = 0.15
  group.add(pad)
}

// 电机（带散热筋的蓝色圆柱）
function addMotor(group, x, y, z, len = 5) {
  const m = new THREE.Mesh(new THREE.CylinderGeometry(2.4, 2.4, len, 20), mat(0x1f6f8b, { metalness: 0.5 }))
  m.rotation.z = Math.PI / 2
  m.position.set(x, y, z)
  group.add(m)
  // 散热筋
  for (let i = -1; i <= 1; i++) {
    const ring = new THREE.Mesh(new THREE.TorusGeometry(2.45, 0.12, 6, 20), mat(0x0d3a48))
    ring.rotation.y = Math.PI / 2
    ring.position.set(x + i * (len / 3), y, z)
    group.add(ring)
  }
  return m
}

// 旋转机械造型（鼓风机 / 引风机 / 驱动电源） —— 蜗壳 + 叶轮 + 电机
function buildRotatingMachine(type, bodyMat, anim) {
  const g = new THREE.Group()
  addSkid(g, 20, 14)
  const cx = 0, cy = 6, cz = 0
  // 蜗壳（喇叭形进气）
  const volute = new THREE.Mesh(new THREE.CylinderGeometry(6, 6.5, 5, 28), bodyMat)
  volute.position.set(cx - 4, cy, cz)
  g.add(volute)
  // 进气口（喇叭）
  const inlet = new THREE.Mesh(new THREE.CylinderGeometry(3.4, 5, 4, 24), mat(0x2a3a55, { metalness: 0.5 }))
  inlet.rotation.z = Math.PI / 2
  inlet.position.set(cx - 9, cy, cz)
  g.add(inlet)
  // 出风口（方形短管，指向上方/侧面）
  const outlet = boxMesh(5, 4, 5, mat(0x2a3a55, { metalness: 0.5 }))
  outlet.position.set(cx - 1, cy + 5, cz)
  g.add(outlet)
  // 叶轮（透明旋转件，透视蜗壳内）
  const blades = new THREE.Group()
  const hub = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.2, 1.6, 16), mat(0x0d3a48, { metalness: 0.7 }))
  hub.rotation.z = Math.PI / 2
  blades.add(hub)
  const bMat = mat(0x4fd0e0, { metalness: 0.6, emissive: 0x0a3a44, emissiveIntensity: 0.4, transparent: true, opacity: 0.78 })
  for (let i = 0; i < 9; i++) {
    const b = new THREE.Mesh(new THREE.BoxGeometry(0.8, 5.2, 1.6), bMat)
    const a = (i / 9) * Math.PI * 2
    b.position.set(Math.cos(a) * 2.8, Math.sin(a) * 2.8, 0)
    b.rotation.z = a
    blades.add(b)
  }
  blades.rotation.y = Math.PI / 2
  blades.position.set(cx - 4, cy, cz)
  g.add(blades)
  // 电机（侧面）
  const motor = addMotor(g, cx + 7, cy, cz, 6)
  // 主轴（连接电机与叶轮）
  const shaft = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 9, 12), mat(0x33425c, { metalness: 0.6 }))
  shaft.rotation.z = Math.PI / 2
  shaft.position.set(cx - 0.5, cy, cz)
  g.add(shaft)
  g.userData.topY = cy + 7
  g.userData._fanBlades = blades
  g.userData._fanPhase = type === 'id_fan' ? 2.0 : 1.0 // 引风机反向略快
  return g
}

// 燃烧炉塔造型（热风炉 / 辅助锅炉） —— 高瘦燃烧塔 + 热风围管 + 燃烧脉动
function buildStove(type, bodyMat, anim) {
  const g = new THREE.Group()
  addSkid(g, 16, 16)
  const cy = 8
  // 炉体（高瘦圆柱，红白间隔涂装）
  const shell = new THREE.Mesh(
    new THREE.CylinderGeometry(5, 5.4, 18, 28),
    new THREE.MeshStandardMaterial({ map: tankShellTex(), roughness: 0.5, metalness: 0.4, color: 0xeaeef2 }),
  )
  shell.position.set(0, cy, 0)
  g.add(shell)
  // 拱顶
  const dome = new THREE.Mesh(new THREE.SphereGeometry(5, 24, 16, 0, Math.PI * 2, 0, Math.PI / 2), bodyMat)
  dome.position.set(0, cy + 9, 0)
  g.add(dome)
  // 热风围管（环绕下部的环形管）
  const ring = new THREE.Mesh(new THREE.TorusGeometry(6.2, 1.1, 10, 28), mat(0xc0563a, { metalness: 0.6 }))
  ring.rotation.x = Math.PI / 2
  ring.position.set(0, cy - 6, 0)
  g.add(ring)
  // 燃烧器（侧面小箱）
  const burner = boxMesh(3, 3, 4, mat(0x8a3a2a, { metalness: 0.6 }))
  burner.position.set(5.5, cy - 2, 0)
  g.add(burner)
  // 燃烧脉动发光体（炉内）
  const flames = []
  for (let i = 0; i < 3; i++) {
    const fl = new THREE.Mesh(
      new THREE.ConeGeometry(1.2, 3.4, 12),
      new THREE.MeshStandardMaterial({ color: 0xff6a1e, emissive: 0xff5a1e, emissiveIntensity: 2, transparent: true, opacity: 0.9 }),
    )
    fl.position.set((i - 1) * 2, cy + 4 + i * 0.3, 1.5)
    g.add(fl)
    flames.push(fl)
  }
  // 辅助锅炉：加一根细烟囱
  if (type === 'aux_boiler') {
    const stack = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 1.3, 12, 16), mat(0x9aa4ad, { metalness: 0.5 }))
    stack.position.set(-4, cy + 8, -2)
    g.add(stack)
  }
  g.userData.topY = cy + 9
  g.userData._hbsFlames = flames
  return g
}

// 输送/给料造型（喷吹 / 皮带机 / 给料机 / 冷却水泵 / 电极调节器）
function buildConveyor(type, bodyMat, anim) {
  const g = new THREE.Group()
  addSkid(g, 22, 12)
  const cy = 5
  if (type === 'belt_conv') {
    // 皮带机：上下托辊 + 循环皮带 + 料流
    const frame = boxMesh(20, 1.5, 6, mat(0x2a3a55, { metalness: 0.5 }))
    frame.position.set(0, cy, 0)
    g.add(frame)
    const rollers = []
    for (let i = -1; i <= 1; i += 2) {
      const r = new THREE.Mesh(new THREE.CylinderGeometry(2, 2, 6.2, 16), mat(0x556070, { map: steelTex(), metalness: 0.7 }))
      r.rotation.x = Math.PI / 2
      r.position.set(i * 9, cy + 1, 0)
      g.add(r)
      rollers.push(r)
    }
    // 皮带（薄环带，用长条 box 模拟，带贴图滚动感）
    const belt = boxMesh(19, 0.5, 6.4, new THREE.MeshStandardMaterial({ color: 0x14181f, roughness: 0.85 }))
    belt.position.set(0, cy + 2.1, 0)
    g.add(belt)
    // 皮带机上的物料（小块）
    const beltRoll = []
    for (let i = 0; i < 6; i++) {
      const chunk = new THREE.Mesh(new THREE.BoxGeometry(1.2, 0.8, 1.2), mat(0x9c7a4a, { roughness: 1 }))
      chunk.position.set(-8 + i * 3, cy + 2.8, 0)
      g.add(chunk)
      beltRoll.push(chunk)
    }
    g.userData.topY = cy + 3.5
    g.userData._beltRoll = { rollers, chunks: beltRoll }
  } else if (type === 'cool_pump') {
    // 冷却水泵：泵壳 + 电机 + 循环水管
    const pump = new THREE.Mesh(new THREE.SphereGeometry(3.4, 18, 14), bodyMat)
    pump.scale.y = 1.2
    pump.position.set(-3, cy, 0)
    g.add(pump)
    const motor = addMotor(g, 4, cy, 0, 6)
    const pipe = new THREE.Mesh(new THREE.TorusGeometry(3.5, 0.8, 10, 20, Math.PI), mat(0x3a6a8a, { metalness: 0.6 }))
    pipe.position.set(-3, cy, 3.5)
    g.add(pipe)
    const rotors = []
    for (let i = 0; i < 6; i++) {
      const v = new THREE.Mesh(new THREE.BoxGeometry(0.5, 2.6, 0.8), mat(0x4fd0e0, { transparent: true, opacity: 0.8, emissive: 0x0a3a44, emissiveIntensity: 0.4 }))
      const a = (i / 6) * Math.PI * 2
      v.position.set(-3 + Math.cos(a) * 1.4, cy + Math.sin(a) * 1.4, 0)
      v.rotation.z = a
      g.add(v)
      rotors.push(v)
    }
    g.userData.topY = cy + 4
    g.userData._pumpRotors = rotors
  } else if (type === 'electrode_reg') {
    // 电极调节器：立柱 + 横臂 + 三根电极（升降脉动）
    const col = new THREE.Mesh(new THREE.BoxGeometry(2, 16, 2), mat(0x2a3a55, { metalness: 0.6 }))
    col.position.set(0, cy + 4, -5)
    g.add(col)
    const arm = boxMesh(10, 1.2, 1.2, mat(0x2a3a55, { metalness: 0.6 }))
    arm.position.set(0, cy + 11, -2)
    g.add(arm)
    const elec = []
    for (let i = -1; i <= 1; i++) {
      const e = new THREE.Group()
      const rod = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 12, 12), mat(0x101418, { metalness: 0.7 }))
      rod.position.y = cy + 5
      e.add(rod)
      const tip = new THREE.Mesh(new THREE.SphereGeometry(0.9, 12, 10), new THREE.MeshStandardMaterial({ color: 0x66ccff, emissive: 0x3399ff, emissiveIntensity: 2 }))
      tip.position.y = cy - 1
      e.add(tip)
      e.position.x = i * 3
      g.add(e)
      elec.push({ group: e, baseUY: cy + 5, tip })
    }
    g.userData.topY = cy + 12
    g.userData._elecRegs = elec
  } else {
    // injector 喷吹系统 / feeder 给料机：料罐 + 喷吹管 + 脉动料流
    const tank = new THREE.Mesh(new THREE.CylinderGeometry(3.5, 3.8, 9, 20), new THREE.MeshStandardMaterial({ map: tankShellTex(), color: 0xeaeef2, roughness: 0.5, metalness: 0.4 }))
    tank.position.set(-3, cy + 3, 0)
    g.add(tank)
    const cone = new THREE.Mesh(new THREE.ConeGeometry(3.5, 3, 20), bodyMat)
    cone.position.set(-3, cy - 2, 0)
    g.add(cone)
    const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 0.7, 12, 12), mat(0x3a6a8a, { metalness: 0.6 }))
    pipe.rotation.z = Math.PI / 2
    pipe.position.set(4, cy + 3, 0)
    g.add(pipe)
    // 脉动颗粒（喷吹）
    const puffs = []
    for (let i = 0; i < 5; i++) {
      const p = new THREE.Mesh(new THREE.SphereGeometry(0.5, 8, 6), new THREE.MeshStandardMaterial({ color: 0x222222, emissive: 0x111111, transparent: true, opacity: 0.7 }))
      p.position.set(8 + i * 2, cy + 3, 0)
      g.add(p)
      puffs.push(p)
    }
    g.userData.topY = cy + 8
    g.userData._injectorPuffs = puffs
  }
  return g
}

// 供电系统（全厂主变电站）造型 —— 主变压器 + 高压套管 + 散热片 + 配电楼 + 输电铁塔 + 电流脉冲
function buildPowerStation(type, bodyMat, anim) {
  const g = new THREE.Group()
  addSkid(g, 24, 17)
  const cy = 5
  // 主变压器（中央大型箱体）
  const trafo = new THREE.Mesh(new THREE.BoxGeometry(10, 8, 8), mat(0x3d4f63, { metalness: 0.5, roughness: 0.45 }))
  trafo.position.set(-2, cy + 4, 0)
  g.add(trafo)
  // 散热片（两侧波纹散热器）
  for (const s of [-1, 1]) {
    for (let i = 0; i < 3; i++) {
      const fin = boxMesh(0.9, 5.5, 5.5, mat(0x2d3d50, { metalness: 0.55 }))
      fin.position.set(-2 + s * 5.6, cy + 4, (i - 1) * 2.4)
      g.add(fin)
    }
  }
  // 变压器油枕（顶部横筒）
  const conservator = new THREE.Mesh(new THREE.CylinderGeometry(1.1, 1.1, 7, 12), mat(0x556070, { metalness: 0.6 }))
  conservator.rotation.z = Math.PI / 2
  conservator.position.set(-2, cy + 8.6, 0)
  g.add(conservator)
  // 高压套管（顶部斜插 3 根绝缘子）
  for (let i = -1; i <= 1; i++) {
    const bush = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.6, 4.4, 10), mat(0x9aa4ad, { metalness: 0.45 }))
    bush.rotation.z = 0.28
    bush.position.set(-2 + i * 2.6, cy + 8.4, 0)
    g.add(bush)
  }
  // 配电楼（低压侧，带发光窗户）
  const house = boxMesh(8, 6.5, 6, mat(0x6a7a8a, { metalness: 0.2, roughness: 0.75 }))
  house.position.set(5.5, cy + 3.25, 0)
  g.add(house)
  for (let i = -1; i <= 1; i++) {
    const win = boxMesh(1.8, 1.6, 0.3, new THREE.MeshStandardMaterial({ color: 0x1a2f42, emissive: 0x66ccff, emissiveIntensity: 0.6 }))
    win.position.set(5.5 + i * 2.6, cy + 4.6, 3.2)
    g.add(win)
  }
  // 输电铁塔（后侧高塔，双回路横担 + 避雷针）
  const tower = new THREE.Group()
  const legMat = mat(0x44515f, { metalness: 0.6, roughness: 0.5 })
  for (let i = -1; i <= 1; i += 2) {
    const leg = new THREE.Mesh(new THREE.BoxGeometry(0.9, 17, 0.9), legMat)
    leg.position.set(i * 3.2, cy + 9, -5)
    tower.add(leg)
  }
  for (let i = 0; i < 3; i++) {
    const bar = boxMesh(9.2, 0.8, 0.8, legMat)
    bar.position.set(0, cy + 5 + i * 5, -5)
    tower.add(bar)
  }
  const spike = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.5, 3.4, 8), mat(0x8a94a0, { metalness: 0.6 }))
  spike.position.set(0, cy + 17, -5)
  tower.add(spike)
  g.add(tower)
  // 输电导线（铁塔顶 → 变压器顶，3 相斜拉线）
  const fromTop = new THREE.Vector3(-4.5, cy + 12.5, -4)
  const UP = new THREE.Vector3(0, 1, 0)
  for (let i = -1; i <= 1; i++) {
    const p1 = new THREE.Vector3(1.5 + i * 2.2, cy + 9, 0.5)
    const dir = new THREE.Vector3().subVectors(p1, fromTop)
    const len = dir.length()
    const w = new THREE.Mesh(new THREE.CylinderGeometry(0.14, 0.14, len, 6), new THREE.MeshBasicMaterial({ color: 0x3a4a5a, transparent: true, opacity: 0.6 }))
    w.position.copy(fromTop).addScaledVector(dir, 0.5)
    w.quaternion.setFromUnitVectors(UP, dir.clone().normalize())
    g.add(w)
  }
  // 电流脉冲（发光球沿导线流动）
  const pulses = []
  for (let i = -1; i <= 1; i++) {
    const from = new THREE.Vector3(-4.5, cy + 12.5, -4)
    const to = new THREE.Vector3(1.5 + i * 2.2, cy + 9, 0.5)
    const p = new THREE.Mesh(new THREE.SphereGeometry(0.5, 10, 8), new THREE.MeshStandardMaterial({ color: 0x99ddff, emissive: 0x3399ff, emissiveIntensity: 2.2 }))
    p.position.copy(from)
    p._from = from
    p._to = to
    p._off = (i + 1) * 0.34
    p._t = 0
    g.add(p)
    pulses.push(p)
  }
  g.userData.topY = cy + 18
  g.userData._powerPulses = pulses
  return g
}

// 空分制气造型（制氧机） —— 多座并排精馏塔 + 冷箱
function buildTowerPlant(type, bodyMat, anim) {
  const g = new THREE.Group()
  addSkid(g, 22, 16)
  const cy = 7
  const towers = []
  for (let i = -1; i <= 1; i++) {
    const h = 16 + (i === 0 ? 4 : 0)
    const t = new THREE.Mesh(
      new THREE.CylinderGeometry(2.6, 2.8, h, 20),
      new THREE.MeshStandardMaterial({ color: 0xcdd6de, roughness: 0.4, metalness: 0.55 }),
    )
    t.position.set(i * 6.5, cy + h / 2 - cy + 0, 0)
    t.position.y = 0.8 + h / 2
    g.add(t)
    towers.push(t)
  }
  // 冷箱（主换热，蓝色发光体）
  const coldBox = boxMesh(8, 10, 6, new THREE.MeshStandardMaterial({ color: 0x1f6f8b, metalness: 0.5, emissive: 0x0a3a44, emissiveIntensity: 0.3 }))
  coldBox.position.set(0, 6, -5)
  g.add(coldBox)
  // 连接管道
  const pipe = new THREE.Mesh(new THREE.TorusGeometry(7, 0.6, 8, 24), mat(0x8a94a0, { metalness: 0.6 }))
  pipe.rotation.x = Math.PI / 2
  pipe.position.set(0, cy, 0)
  g.add(pipe)
  g.userData.topY = 0.8 + 20 + 2
  g.userData._oxyTowers = towers
  return g
}

const DISPATCH = {
  blower: buildRotatingMachine,
  id_fan: buildRotatingMachine,
  drive_supply: buildRotatingMachine,
  hot_blast_stove: buildStove,
  aux_boiler: buildStove,
  injector: buildConveyor,
  belt_conv: buildConveyor,
  feeder: buildConveyor,
  cool_pump: buildConveyor,
  electrode_reg: buildConveyor,
  oxy_plant: buildTowerPlant,
  power_supply: buildPowerStation,
}

export function buildAuxiliary(type, bodyMat, anim = {}) {
  const fn = DISPATCH[type] || buildRotatingMachine
  return fn(type, bodyMat, anim)
}
