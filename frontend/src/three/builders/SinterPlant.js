import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex, tankShellTex } from './utils.js'

/** _buildSinterPlant 极致仿真烧结机3D模型
 *  矿槽→混合→布料→台车→点火炉→烧结→破碎→冷却→筛分
 *  台车上烧结料可见燃烧前沿
 *  点火炉火焰
 *  抽风管道 + 除尘
 */
export default function _buildSinterPlant(bodyMat) {
    const g = new THREE.Group()
    const L = 24; const D = 10; const H = 8
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })


    // === 1. 矿槽 + 布料系统 ===
    // 矿槽
    const oreBunker = new THREE.Mesh(new THREE.CylinderGeometry(2.5, 3.5, 6, 16),
        mat(0x8899aa, { roughness: 0.35, metalness: 0.35 }))
    oreBunker.position.set(-L * 0.38, 8.0, 0); g.add(oreBunker)
    // 圆辊布料机
    const drumFeeder = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 0.8, D * 0.6, 12), steel)
    drumFeeder.rotation.x = Math.PI / 2
    drumFeeder.position.set(-L * 0.3, 5.5, 0); g.add(drumFeeder)

    // === 2. 台车系统（sinter strand） ===
    const strandLen = 16
    const palletY = 3.5
    // 台车框架（带侧档板）
    for (const s of [-1, 1]) {
        const sideWall = new THREE.Mesh(new THREE.BoxGeometry(strandLen, 0.8, 0.4), steel)
        sideWall.position.set(0, palletY + 0.4, s * D * 0.3); g.add(sideWall)
    }
    // 底部轨道
    const trackL = new THREE.Mesh(new THREE.BoxGeometry(strandLen, 0.2, 0.3), steel)
    trackL.position.set(0, palletY - 0.5, D * 0.3); g.add(trackL)
    const trackR = new THREE.Mesh(new THREE.BoxGeometry(strandLen, 0.2, 0.3), steel)
    trackR.position.set(0, palletY - 0.5, -D * 0.3); g.add(trackR)

    // 台车炉篦（可见层）— 烧结料层
    const bedMesh = new THREE.Mesh(new THREE.BoxGeometry(strandLen, 0.35, D * 0.5),
        mat(0x5a4a3a, { roughness: 0.6, metalness: 0.05 }))
    bedMesh.position.set(0, palletY + 0.15, 0); g.add(bedMesh)

    // 燃烧前沿（烧结料层中的高温熔融带 — 从上向下移动）
    const burnFront = new THREE.Mesh(new THREE.BoxGeometry(strandLen, 0.15, D * 0.5),
        new THREE.MeshStandardMaterial({
            color: 0xcc5528, emissive: 0xbb3a10, emissiveIntensity: 0.45,
            roughness: 0.2, metalness: 0.05, transparent: true, opacity: 0.7, depthWrite: false
        }))
    burnFront.position.set(0, palletY + 0.3, 0); g.add(burnFront)
    burnFront.name = 'burnFront'

    // === 3. 点火炉（ignition furnace — 台车头部上方） ===
    const ignitorBody = new THREE.Mesh(new THREE.BoxGeometry(3.0, 1.5, D * 0.55),
        mat(0x9a8070, { roughness: 0.45, metalness: 0.15 }))
    ignitorBody.position.set(-strandLen / 2 + 1, palletY + 1.2, 0); g.add(ignitorBody)

    // 点火火焰喷嘴（分布在整个宽度上）
    const igniters = []
    for (let i = 0; i < 6; i++) {
        const nx = -strandLen / 2 + 1 + (i - 2.5) * 0.8
        const flame = new THREE.Mesh(new THREE.ConeGeometry(0.25, 0.8, 8),
            new THREE.MeshStandardMaterial({
                color: 0xb56530, emissive: 0xa03c10, emissiveIntensity: 0.55,
                roughness: 0.25, metalness: 0.05, transparent: true, opacity: 0.65, depthWrite: false
            }))
        flame.rotation.x = -Math.PI / 2
        flame.position.set(nx, palletY + 0.6, (Math.random() - 0.5) * D * 0.4)
        igniters.push(flame); g.add(flame)
    }

    // === 4. 主轴传动装置 ===
    const driveMotor = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.2, 2.5, 16), steel)
    driveMotor.rotation.z = Math.PI / 2
    driveMotor.position.set(-strandLen / 2 - 1, palletY, 0); g.add(driveMotor)

    // === 5. 抽风系统（draft fans — 负压抽风） ===
    // 风箱（wind box — 台车下方收集烧结废气）
    for (let i = 0; i < 4; i++) {
        const bx = -strandLen / 2 + 2 + i * 4
        const windBox = new THREE.Mesh(new THREE.BoxGeometry(3.5, 1.5, D * 0.4),
            mat(0x667788, { roughness: 0.35, metalness: 0.5, transparent: true, opacity: 0.4 }))
        windBox.position.set(bx, palletY - 1.2, 0); g.add(windBox)
    }
    // 主抽风机管道
    const mainDuct = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.6, 10, 12), steel)
    mainDuct.rotation.z = Math.PI / 2
    mainDuct.position.set(strandLen / 2, palletY - 1.2, 0); g.add(mainDuct)

    // === 6. 破碎 + 冷却 ===
    // 单辊破碎机
    const crusher = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.6, D * 0.5, 8), steel)
    crusher.rotation.x = Math.PI / 2
    crusher.position.set(strandLen / 2 + 1, palletY - 0.3, 0); g.add(crusher)
    // 成品筛
    const screen = new THREE.Mesh(new THREE.BoxGeometry(3.0, 0.3, D * 0.5),
        mat(0x8899aa, { roughness: 0.35, metalness: 0.4, transparent: true, opacity: 0.5 }))
    screen.position.set(strandLen / 2 + 2.5, palletY - 1.0, 0); g.add(screen)

    // === 7. 电除尘器 ===
    const esp = new THREE.Mesh(new THREE.BoxGeometry(4, 3, D * 0.4),
        mat(0x778899, { roughness: 0.4, metalness: 0.45 }))
    esp.position.set(strandLen / 2 + 3, palletY + 3, D * 0.55); g.add(esp)

    // === 7.5 排气烟囱 + 成品输送带 ===
    const chimney = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.7, 10, 12), steel)
    chimney.position.set(strandLen / 2 + 4, palletY + 9, D * 0.6); g.add(chimney)
    // 烟囱顶部霓虹环
    const chimneyRing = new THREE.Mesh(new THREE.TorusGeometry(0.8, 0.1, 6, 16),
        mat(0x42566b, { roughness: 0.55, metalness: 0.35 }))
    chimneyRing.position.set(strandLen / 2 + 4, palletY + 14, D * 0.6); g.add(chimneyRing)
    // 成品输送带（连到筛分出口）
    const beltMat = mat(0x3a3a3a, { roughness: 0.6, metalness: 0.1 })
    const belt = new THREE.Mesh(new THREE.BoxGeometry(8, 0.15, 1.0), beltMat)
    belt.position.set(strandLen / 2 + 6, palletY - 1.5, 0); g.add(belt)
    // 输送带支架
    for (let bx = strandLen / 2 + 3; bx <= strandLen / 2 + 9; bx += 2) {
        const bs = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 1.0, 6), steel)
        bs.position.set(bx, palletY - 2.2, 0)
        g.add(bs)
    }

    // === 8. 霓虹装饰 ===
    const sinterRing = new THREE.Mesh(new THREE.TorusGeometry(strandLen * 0.5, 0.12, 8, 32),
        mat(0x42566b, { roughness: 0.55, metalness: 0.35 }))
    sinterRing.rotation.x = Math.PI / 2; sinterRing.position.set(0, 2.0, 0); g.add(sinterRing)

    // === 9. 动画钩子 ===
    g.userData.topY = 18
    g.userData.heatCenterY = palletY
    g.userData.heatInternalH = 4.0
    g.userData.heatInternalR = D * 0.35

    g.userData._sinterIgniters = igniters

    // === 物料转变动画：铁矿粉(深灰)→烧结→烧结矿(灰蓝) ===
    // 颜色与连线载运体一致：iron_ore(0x3a5058)→sinter(0x5a7088)
    const sinterFlow = []
    for (let i = 0; i < 10; i++) {
        const p = i / 10; const px = -strandLen * 0.45 + p * strandLen * 0.9
        const grain = new THREE.Mesh(new THREE.DodecahedronGeometry(0.25 + Math.random() * 0.15, 0),
            new THREE.MeshStandardMaterial({ roughness: 0.6, metalness: 0.1 }))
        grain.position.set(px, palletY + 0.5, (Math.random() - 0.5) * D * 0.3); g.add(grain)
        sinterFlow.push({
            obj: grain, phase: i * 0.1, period: 6.5,
            srcPos: new THREE.Vector3(px, palletY + 0.5, grain.position.z),
            dstPos: new THREE.Vector3(px + 2, palletY + 0.5, grain.position.z),
            srcColor: 0x3a5058, dstColor: 0x5a7088,
        })
    }

    g.userData._matFlow = sinterFlow
    return g
}
