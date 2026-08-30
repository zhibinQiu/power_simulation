import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex, tankShellTex } from './utils.js'

/** _buildPelletizing 极致仿真球团厂3D模型
 *  原料混合→造球盘→生球筛分→链篦机→回转窑→环冷机→成品
 *  造球盘旋转 + 生球滚动成形
 *  回转窑内火焰高温焙烧
 */
export default function _buildPelletizing(bodyMat) {
    const g = new THREE.Group()
    const L = 28; const D = 16; const H = 12
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })
    const neonColor = 0x2c6e9e

    // === 1. 造球盘（granulating disc ±45°倾斜旋转） ===
    const pelletDiscs = []
    for (const disc of [
        { x: -L * 0.38, z: -D * 0.25, angle: 0.75 },
        { x: -L * 0.38, z: D * 0.25, angle: -0.75 },
    ]) {
        const discG = new THREE.Group()
        // 盘体（cylindrical disc）
        const discBody = new THREE.Mesh(new THREE.CylinderGeometry(2.8, 2.8, 0.8, 24),
            mat(0x668899, { roughness: 0.35, metalness: 0.3 }))
        discBody.position.set(disc.x, 8, disc.z)
        discG.add(discBody)
        // 盘底加强肋
        const rib = new THREE.Mesh(new THREE.TorusGeometry(2.8, 0.2, 8, 24), steel)
        rib.position.set(disc.x, 8, disc.z)
        rib.rotation.x = Math.PI / 2
        discG.add(rib)
        // 盘内壁可见生球（绿色小球）
        for (let j = 0; j < 8; j++) {
            const gb = new THREE.Mesh(new THREE.SphereGeometry(0.18 + Math.random() * 0.12, 6, 6),
                new THREE.MeshStandardMaterial({
                    roughness: 0.4, metalness: 0.05, emissive: 0x223300, emissiveIntensity: 0.15
                }))
            gb.position.set(disc.x + (Math.random() - 0.5) * 2, 7.8 + Math.random() * 0.6, disc.z + (Math.random() - 0.5) * 2)
            discG.add(gb)
        }
        pelletDiscs.push(discG)
        g.add(discG)
    }

    // === 2. 链篦机（traveling grate — 干燥 & 预热） ===
    const grateLen = 10
    const grateBody = new THREE.Mesh(new THREE.BoxGeometry(grateLen, 1.0, D * 0.3),
        mat(0x887766, { roughness: 0.45, metalness: 0.2 }))
    grateBody.position.set(0, 4.5, 0); g.add(grateBody)
    // 预热罩（hood）
    const preheatHood = new THREE.Mesh(
        new THREE.BoxGeometry(grateLen * 0.7, 2.0, D * 0.3),
        mat(0x9a8070, { roughness: 0.4, metalness: 0.15, transparent: true, opacity: 0.6, depthWrite: false }))
    preheatHood.position.set(0, 5.5, 0); g.add(preheatHood)

    // === 3. 回转窑（rotary kiln — 高温焙烧） ===
    const kilnLen = 14
    const kiln = new THREE.Mesh(new THREE.CylinderGeometry(2.5, 2.5, kilnLen, 24),
        mat(0x996644, { roughness: 0.5, metalness: 0.1 }))
    kiln.rotation.z = Math.PI / 2
    kiln.position.set(L * 0.2, 8.0, 0); g.add(kiln)
    // 窑体加强环（tire/riding rings）
    for (let ri = -1; ri <= 1; ri += 2) {
        const tire = new THREE.Mesh(new THREE.TorusGeometry(2.6, 0.3, 8, 24), steel)
        tire.position.set(L * 0.2 + ri * kilnLen * 0.35, 8.0, 0)
        g.add(tire)
        // 支撑托轮
        for (const sr of [-1, 1]) {
            const roller = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 1.0, 8), steel)
            roller.rotation.x = Math.PI / 2
            roller.position.set(L * 0.2 + ri * kilnLen * 0.35, 4.8 + ri * 0.2, sr * 2.0)
            g.add(roller)
        }
    }
    // 窑内火焰可见（高温带）
    const kilnGlow = new THREE.Mesh(new THREE.CylinderGeometry(2.0, 2.0, kilnLen * 0.4, 16),
        new THREE.MeshStandardMaterial({
            color: 0xff6633, emissive: 0xff3300, emissiveIntensity: 1.2,
            roughness: 0.1, metalness: 0.05, transparent: true, opacity: 0.5, depthWrite: false
        }))
    kilnGlow.rotation.z = Math.PI / 2
    kilnGlow.position.set(L * 0.2, 8.0, 0); g.add(kilnGlow)
    kilnGlow.name = 'kilnGlow'

    // 窑头燃烧器
    const burner = new THREE.Mesh(new THREE.ConeGeometry(0.6, 1.5, 8),
        new THREE.MeshStandardMaterial({
            color: 0xff8833, emissive: 0xff3300, emissiveIntensity: 1.5,
            roughness: 0.1, metalness: 0.05, depthWrite: false
        }))
    burner.rotation.z = Math.PI / 2
    burner.position.set(L * 0.2 - kilnLen / 2, 8.0, 0); g.add(burner)

    // 窑尾（出料端 — 焙烧球团）
    const kilnOutlet = new THREE.Mesh(new THREE.CylinderGeometry(2.0, 2.5, 1.5, 16),
        mat(0x887766, { roughness: 0.4, metalness: 0.2 }))
    kilnOutlet.rotation.z = Math.PI / 2
    kilnOutlet.position.set(L * 0.2 + kilnLen / 2, 8.0, 0); g.add(kilnOutlet)

    // === 4. 环冷机（annular cooler — 球团冷却） ===
    const cooler = new THREE.Mesh(new THREE.TorusGeometry(3.0, 0.5, 8, 16),
        mat(0x778899, { roughness: 0.35, metalness: 0.45, transparent: true, opacity: 0.55, depthWrite: false }))
    cooler.rotation.x = Math.PI / 2
    cooler.position.set(L * 0.38, 4.0, 0); g.add(cooler)
    // 成品球团堆积
    for (let i = 0; i < 6; i++) {
        const pellet = new THREE.Mesh(new THREE.SphereGeometry(0.3 + Math.random() * 0.15, 8, 6),
            new THREE.MeshStandardMaterial({ color: 0x4a6078, roughness: 0.4, metalness: 0.1, emissive: 0x111122, emissiveIntensity: 0.1 }))
        pellet.position.set(L * 0.38 + (Math.random() - 0.5) * 3, 3.2 + Math.random() * 0.5, (Math.random() - 0.5) * 2)
        g.add(pellet)
    }

    // === 5. 霓虹 ===
    const pelRing = new THREE.Mesh(new THREE.TorusGeometry(3.2, 0.12, 8, 32),
        new THREE.MeshStandardMaterial({ color: neonColor, emissive: neonColor, emissiveIntensity: 0.22, roughness: 0.4, metalness: 0.6 }))
    pelRing.rotation.x = Math.PI / 2; pelRing.position.set(L * 0.38, 1.5, 0); g.add(pelRing)

    // === 6. 动画钩子 ===
    g.userData.topY = 20
    g.userData.heatCenterY = 8.0
    g.userData.heatInternalH = 6.0
    g.userData.heatInternalR = 3.5
    g.userData._pelletDiscs = pelletDiscs

    // === 物料转变动画：铁矿粉(深灰)→造球→球团矿(灰蓝) ===
    // 颜色与连线载运体一致：iron_ore(0x3a5058)→pellet(0x4a6078)
    const pelletFlow = []
    for (let i = 0; i < 6; i++) {
        const gBall = new THREE.Mesh(new THREE.SphereGeometry(0.22, 8, 6),
            new THREE.MeshStandardMaterial({ roughness: 0.4, metalness: 0.05 }))
        const discX = -L * 0.38; const discZ = (i < 3 ? -D * 0.25 : D * 0.25)
        gBall.position.set(discX, 8.5, discZ + (Math.random() - 0.5) * 1.5); g.add(gBall)
        pelletFlow.push({
            obj: gBall, phase: i * 0.16, period: 4.5,
            srcPos: new THREE.Vector3(discX, 8.5, gBall.position.z),
            dstPos: new THREE.Vector3(discX + 4, 6.0, gBall.position.z),
            srcColor: 0x3a5058, dstColor: 0x4a6078,
        })
    }
    // 回转窑内球团焙烧转变
    for (let i = 0; i < 3; i++) {
        const kilnP = new THREE.Mesh(new THREE.SphereGeometry(0.25, 6, 6),
            new THREE.MeshStandardMaterial({ roughness: 0.3, metalness: 0.1 }))
        kilnP.position.set(L * 0.2 - 4 + i * 3, 8.0, (Math.random() - 0.5) * 1.5)
        g.add(kilnP)
        pelletFlow.push({
            obj: kilnP, phase: i * 0.3, period: 5.0,
            srcPos: new THREE.Vector3(L * 0.2 - 6, 8.0, kilnP.position.z),
            dstPos: new THREE.Vector3(L * 0.2 + 6, 8.0, kilnP.position.z),
            srcColor: 0x4a6078, dstColor: 0xb05a36, scalePulse: 0.1,
        })
    }

    g.userData._matFlow = pelletFlow
    return g
}
