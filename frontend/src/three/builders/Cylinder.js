import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex, tankShellTex } from './utils.js'

/** _buildCylinder 极致仿真钢包精炼炉(LF/RH/VD)3D模型
 *  LF: 三相电极加热 + 底吹Ar搅拌
 *  RH: 真空室 + 浸渍管 + 抽真空
 *  VD: 真空罐 + 底吹Ar
 */
export default function _buildCylinder(bodyMat) {
    const g = new THREE.Group()
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })
    const neonColor = 0x00ccff


    // === 1. 钢包（ladle — 耐火材料内衬） ===
    const ladleBody = new THREE.Mesh(new THREE.CylinderGeometry(3.5, 3.0, 7, 24), bodyMat)
    ladleBody.position.y = 3.5; g.add(ladleBody)
    // 钢包底
    const ladleBot = new THREE.Mesh(new THREE.CylinderGeometry(3.0, 3.2, 0.6, 24),
        mat(0x9a8070, { roughness: 0.5, metalness: 0.1 }))
    ladleBot.position.y = 0.3; g.add(ladleBot)
    // 钢包上沿
    const ladleRim = new THREE.Mesh(new THREE.TorusGeometry(3.5, 0.4, 8, 24), steel)
    ladleRim.rotation.x = Math.PI / 2; ladleRim.position.y = 7.0; g.add(ladleRim)

    // 钢包耳轴
    for (const s of [-1, 1]) {
        const trunnion = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 1.2, 8), steel)
        trunnion.rotation.z = Math.PI / 2; trunnion.position.set(s * 3.8, 5.5, 0); g.add(trunnion)
    }

    // === 2. 内部钢水熔池 ===
    const melt = new THREE.Mesh(
        new THREE.CylinderGeometry(2.8, 3.0, 3.0, 24),
        mat(0xff8822, {
            roughness: 0.05, metalness: 0.05, emissive: 0xcc3300, emissiveIntensity: 0.9,
            transparent: true, opacity: 0.7, depthWrite: false
        }))
    melt.position.y = 3.0; g.add(melt)
    melt.name = 'melt'

    // 渣层
    const slagOnTop = new THREE.Mesh(
        new THREE.CylinderGeometry(3.2, 3.3, 0.8, 24),
        mat(0x998877, {
            roughness: 0.3, metalness: 0.15, emissive: 0x332200, emissiveIntensity: 0.2,
            transparent: true, opacity: 0.6, depthWrite: false
        }))
    slagOnTop.position.y = 5.2; g.add(slagOnTop)
    slagOnTop.name = 'slagOnTop'

    // === 3. LF功能：三相电极 ===
    const electrodes = []
    const elecAnglesLF = [0, Math.PI * 2 / 3, Math.PI * 4 / 3]
    elecAnglesLF.forEach((ang, ei) => {
        const er = 1.3
        const ex = Math.cos(ang) * er; const ez = Math.sin(ang) * er
        const elec = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 5.0, 8),
            mat(0x444444, { roughness: 0.3, metalness: 0.15, emissive: 0x111111, emissiveIntensity: 0.15 }))
        elec.position.set(ex, 8.5, ez)
        elec.name = 'electrode'
        electrodes.push(elec); g.add(elec)
        // 电弧
        const arc = new THREE.Mesh(new THREE.SphereGeometry(0.22, 6, 4),
            new THREE.MeshStandardMaterial({
                color: 0xffffcc, emissive: 0xffaa00, emissiveIntensity: 2.0,
                roughness: 0.05, metalness: 0.05, transparent: true, opacity: 0.7, depthWrite: false
            }))
        arc.position.set(ex, 5.5, ez)
        arc.name = 'lfArc'
        electrodes.push(arc); g.add(arc)
    })
    // 电极横臂
    const armBar = new THREE.Mesh(new THREE.BoxGeometry(3.5, 0.4, 3.5), steel)
    armBar.position.y = 10.8; g.add(armBar)

    // === 4. RH功能：真空室（vacuum vessel） ===
    // 上部真空室
    const vacVessel = new THREE.Mesh(new THREE.CylinderGeometry(1.8, 1.8, 5, 16),
        mat(0x8899aa, { roughness: 0.35, metalness: 0.45, transparent: true, opacity: 0.55, depthWrite: false }))
    vacVessel.position.y = 11.0; g.add(vacVessel)
    // 顶部抽真空管道
    const vacPipe = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.5, 4, 8), steel)
    vacPipe.position.y = 14.5; g.add(vacPipe)
    // 浸渍管（snorkels — 插入钢水）
    for (const s of [-1, 1]) {
        const snorkel = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.35, 5.5, 8),
            mat(0x996644, { roughness: 0.3, metalness: 0.5 }))
        snorkel.position.set(s * 0.8, 6.0, 0); g.add(snorkel)
    }

    // === 5. 底吹氩气搅拌气泡 ===
    const arBubbles = []
    for (let i = 0; i < 10; i++) {
        const bub = new THREE.Mesh(new THREE.SphereGeometry(0.15 + Math.random() * 0.18, 4, 4),
            new THREE.MeshBasicMaterial({
                color: 0xffffff, transparent: true, opacity: 0.2 + Math.random() * 0.15, depthWrite: false
            }))
        bub.position.set((Math.random() - 0.5) * 4, Math.random() * 6, (Math.random() - 0.5) * 4)
        arBubbles.push(bub); g.add(bub)
    }

    // === 6. 合金料仓 + 加料系统 ===
    const alloyHopper = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.5, 3, 12),
        mat(0x8899aa, { roughness: 0.35, metalness: 0.4 }))
    alloyHopper.position.set(4, 11, 0); g.add(alloyHopper)
    // 加料管
    const feedPipe = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 4, 8), steel)
    feedPipe.rotation.z = 0.8
    feedPipe.position.set(3, 9, 0); g.add(feedPipe)

    // === 6.5 上部检修平台 + 安全围栏 ===
    const pfMat = mat(0x445566, { roughness: 0.45, metalness: 0.35, transparent: true, opacity: 0.5 })
    const topPlatform = new THREE.Mesh(new THREE.BoxGeometry(14, 0.2, 8), pfMat)
    topPlatform.position.set(0, 8.2, 0)
    topPlatform.receiveShadow = true
    g.add(topPlatform)
    // 栏杆柱
    for (const sx of [-1, 1]) {
        for (const sz of [-1, 1]) {
            const post = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.9, 6), steel)
            post.position.set(sx * 6.5, 8.8, sz * 3.5)
            g.add(post)
        }
    }
    // 栏杆横梁
    for (const sz of [-1, 1]) {
        const rail = new THREE.Mesh(new THREE.BoxGeometry(13, 0.06, 0.06), steel)
        rail.position.set(0, 9.2, sz * 3.5)
        g.add(rail)
    }
    for (const sx of [-1, 1]) {
        const rail = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.06, 7), steel)
        rail.position.set(sx * 6.5, 9.2, 0)
        g.add(rail)
    }

    // === 7. 霓虹 ===
    const lfRing1 = new THREE.Mesh(new THREE.TorusGeometry(3.7, 0.12, 8, 32),
        new THREE.MeshStandardMaterial({ color: neonColor, emissive: neonColor, emissiveIntensity: 0.5, roughness: 0.2 }))
    lfRing1.rotation.x = Math.PI / 2; lfRing1.position.set(0, 4.0, 0); g.add(lfRing1)

    const lfRing2 = new THREE.Mesh(new THREE.TorusGeometry(3.7, 0.12, 8, 24),
        new THREE.MeshStandardMaterial({ color: neonColor, emissive: neonColor, emissiveIntensity: 0.4, roughness: 0.2 }))
    lfRing2.rotation.x = Math.PI / 2; lfRing2.position.set(0, 6.8, 0); g.add(lfRing2)

    // === 8. 动画钩子 ===
    g.userData.topY = 20
    g.userData.heatCenterY = 3.5
    g.userData.heatInternalH = 8.0
    g.userData.heatInternalR = 3.5
    g.userData._arBubbles = arBubbles

    // === 物料转变动画：钢水(橙)→电弧加热合金→精炼钢水(亮橙) ===
    // 颜色与连线载运体一致：crude_steel(0xff8822)→refined_steel(0xffaa44)
    const lfFlow = []
    for (let i = 0; i < 5; i++) {
        const glow = new THREE.Mesh(new THREE.SphereGeometry(0.25 + Math.random() * 0.12, 6, 4),
            new THREE.MeshStandardMaterial({ roughness: 0.12, metalness: 0.08 }))
        glow.position.set((Math.random() - 0.5) * 3.5, 4.0 + Math.random() * 2.5, (Math.random() - 0.5) * 3.5)
        g.add(glow)
        lfFlow.push({
            obj: glow, phase: i * 0.2, period: 4.5,
            srcPos: new THREE.Vector3((Math.random() - 0.5) * 3, 5.0, (Math.random() - 0.5) * 3),
            dstPos: new THREE.Vector3((Math.random() - 0.5) * 2, 2.5, (Math.random() - 0.5) * 2),
            srcColor: 0xff8822, dstColor: 0xffaa44, scalePulse: 0.12,
        })
    }

    g.userData._matFlow = lfFlow
    return g
}
