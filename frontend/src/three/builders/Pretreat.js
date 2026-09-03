import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex, tankShellTex } from './utils.js'

/** _buildPretreat 极致仿真铁水预处理3D模型
 *  鱼雷罐车(Torpedo ladle) → 喷枪喷吹脱硫/脱磷剂
 *  喷吹颗粒注入可视化
 *  脱硫渣层浮于铁水表面
 */
export default function _buildPretreat(bodyMat) {
    const g = new THREE.Group()
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })


    // === 1. 鱼雷罐车 ===
    // 罐体（torpedo ladle — 水平放置的梨形容器）
    const torpedoBody = new THREE.Mesh(new THREE.CylinderGeometry(2.8, 2.0, 8, 24), bodyMat)
    torpedoBody.rotation.z = Math.PI / 2
    torpedoBody.position.y = 3.0; g.add(torpedoBody)
    // 罐口（铁水进出口）
    const torpedoMouth = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.4, 1.2, 16), bodyMat)
    torpedoMouth.position.y = 5.8; g.add(torpedoMouth)
    // 耳轴支撑
    for (const s of [-1, 1]) {
        const support = new THREE.Mesh(new THREE.BoxGeometry(1.5, 3.0, 1.5), steel)
        support.position.set(s * 4.5, 1.5, 0); g.add(support)
        const bearing = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 0.8, 8), steel)
        bearing.rotation.z = Math.PI / 2; bearing.position.set(s * 3.8, 3.0, 0); g.add(bearing)
    }
    // 轨道台车
    const car = new THREE.Mesh(new THREE.BoxGeometry(3.5, 0.6, 6), steel)
    car.position.set(0, 0.3, 0); g.add(car)
    // 铁轨
    for (const s of [-1, 1]) {
        const rail = new THREE.Mesh(new THREE.BoxGeometry(20, 0.15, 0.2), steel)
        rail.position.set(0, 0.1, s * 2); g.add(rail)
    }

    // === 2. 内部铁水 ===
    const ironMelt = new THREE.Mesh(
        new THREE.CylinderGeometry(2.0, 2.3, 5.5, 24),
        mat(0xc05a30, {
            roughness: 0.15, metalness: 0.05, emissive: 0x8a3010, emissiveIntensity: 0.5,
            transparent: true, opacity: 0.75, depthWrite: false
        }))
    ironMelt.rotation.z = Math.PI / 2
    ironMelt.position.y = 2.8; g.add(ironMelt)
    ironMelt.name = 'ironMelt'

    // === 3. 喷枪系统（injection lance） ===
    // 喷枪架
    const lanceFrame = new THREE.Mesh(new THREE.BoxGeometry(0.8, 6, 0.8), steel)
    lanceFrame.position.set(2.2, 6, -2.2); g.add(lanceFrame)
    // 喷枪本体
    const injectLance = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 5, 8),
        mat(0x8899aa, { roughness: 0.3, metalness: 0.55 }))
    injectLance.position.set(2.2, 4.0, -2.2); g.add(injectLance)
    injectLance.name = 'injectLance'
    // 喷枪头
    const lanceHead = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.18, 0.4, 8),
        mat(0xcc6633, { roughness: 0.25, metalness: 0.5, emissive: 0x220000, emissiveIntensity: 0.3 }))
    lanceHead.position.set(2.2, 2.0, -2.2); g.add(lanceHead)

    // === 4. 脱硫剂喷吹颗粒（注入铁水） ===
    const sprayParticles = []
    for (let i = 0; i < 15; i++) {
        const p = new THREE.Mesh(new THREE.DodecahedronGeometry(0.1 + Math.random() * 0.1, 0),
            new THREE.MeshStandardMaterial({
                roughness: 0.4, metalness: 0.2, emissive: 0x111100, emissiveIntensity: 0.1
            }))
        p.position.set(2.2, 1.5 + Math.random() * 4.0, -2.2 + (Math.random() - 0.5) * 1.5)
        sprayParticles.push(p); g.add(p)
    }

    // === 5. 脱硫渣层（浮于铁水表面） ===
    const slagFloat = new THREE.Mesh(
        new THREE.CylinderGeometry(2.5, 2.7, 0.7, 24),
        mat(0x888877, {
            roughness: 0.35, metalness: 0.2, emissive: 0x221100, emissiveIntensity: 0.15,
            transparent: true, opacity: 0.55, depthWrite: false
        }))
    slagFloat.rotation.z = Math.PI / 2
    slagFloat.position.y = 5.0; g.add(slagFloat)
    slagFloat.name = 'slagFloat'

    // === 5.5 脱硫剂储罐 ===
    const agentTank = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.8, 4, 12),
        mat(0x8899aa, { roughness: 0.35, metalness: 0.4 }))
    agentTank.position.set(4.5, 7.5, -2.2); g.add(agentTank)
    // 储罐到喷枪的管道
    const agentPipe = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 4, 6), steel)
    agentPipe.rotation.z = 0.9
    agentPipe.position.set(3.2, 5, -2.2)
    g.add(agentPipe)

    // === 6. 烟罩 ===
    const fumeHood = new THREE.Mesh(
        new THREE.CylinderGeometry(2.5, 3.5, 2.0, 24, 1, true),
        mat(0x778899, { roughness: 0.4, metalness: 0.45, transparent: true, opacity: 0.45, depthWrite: false }))
    fumeHood.position.y = 8.5; g.add(fumeHood)

    // === 6.5 两侧操作走道 ===
    const walkMat = mat(0x445566, { roughness: 0.45, metalness: 0.35, transparent: true, opacity: 0.5 })
    for (const s of [-1, 1]) {
        const walkway = new THREE.Mesh(new THREE.BoxGeometry(18, 0.12, 0.7), walkMat)
        walkway.position.set(0, 5.0, s * 4.5)
        g.add(walkway)
    }

    // === 7. 霓虹 ===
    const pretRing = new THREE.Mesh(new THREE.TorusGeometry(2.5, 0.1, 8, 24),
        mat(0x42566b, { roughness: 0.55, metalness: 0.35 }))
    pretRing.rotation.y = Math.PI / 2; pretRing.position.set(0, 5.5, 0); g.add(pretRing)

    // === 8. 动画钩子 ===
    g.userData.topY = 14
    g.userData.heatCenterY = 3.0
    g.userData.heatInternalH = 6.0
    g.userData.heatInternalR = 3.0
    g.userData._pretreatSpray = sprayParticles

    // === 物料转变动画：铁水(橙红)→喷吹脱硫→纯净铁水(亮橙)+渣层(灰) ===
    // 颜色与连线载运体一致：hot_metal(0xb05030)→pretreated_hot_metal(0xb55a34)
    const pretreatFlow = []
    const ironGlow = new THREE.Mesh(new THREE.SphereGeometry(0.5, 8, 6),
        new THREE.MeshStandardMaterial({ roughness: 0.12, metalness: 0.08 }))
    ironGlow.position.set(0, 2.8, 0); g.add(ironGlow)
    pretreatFlow.push({
        obj: ironGlow, phase: 0, period: 5.5,
        srcPos: new THREE.Vector3(0, 2.8, 0), dstPos: new THREE.Vector3(0, 2.8, 0),
        srcColor: 0xb05030, dstColor: 0xb55a34, scalePulse: 0.15,
    })
    // 喷枪注入脱硫剂
    for (let i = 0; i < 5; i++) {
        const spray = new THREE.Mesh(new THREE.DodecahedronGeometry(0.12, 0),
            new THREE.MeshStandardMaterial({ roughness: 0.4, metalness: 0.2 }))
        spray.position.set(2.2, 5.0, -2.2); g.add(spray)
        pretreatFlow.push({
            obj: spray, phase: i * 0.2, period: 3.5,
            srcPos: new THREE.Vector3(2.2, 6.0, -2.2),
            dstPos: new THREE.Vector3(0, 2.8, 0),
            srcColor: 0xcccccc, dstColor: 0x999999, scalePulse: 0.3,
        })
    }

    g.userData._matFlow = pretreatFlow
    return g
}
