import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex } from './utils.js'

/** _buildUtility 极致仿真公用设施3D模型
 *  燃气发电：燃气轮机 + 余热锅炉 + 汽轮机 + 发电机
 *  余热回收：换热器 + 烟囱
 *  CCS：碳捕集吸收塔 + 再生塔
 */
export default function _buildUtility(bodyMat) {
    const g = new THREE.Group()
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })
    const neonColor = 0x2c6e9e


    // === 1. 燃气轮机（gas turbine） ===
    const gtBody = new THREE.Mesh(new THREE.CylinderGeometry(1.8, 2.2, 6, 16), steel)
    gtBody.position.set(-6, 3.0, 0); g.add(gtBody)
    // 进气口
    const airIntake = new THREE.Mesh(
        new THREE.CylinderGeometry(1.5, 2.0, 1.5, 16, 1, true),
        mat(0x667788, { roughness: 0.4, metalness: 0.5, transparent: true, opacity: 0.5 }))
    airIntake.position.set(-6, 6.5, 0); g.add(airIntake)
    // 燃烧室
    const combustor = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.2, 2.5, 12),
        mat(0xcc8844, { roughness: 0.25, metalness: 0.55, emissive: 0x331100, emissiveIntensity: 0.4 }))
    combustor.position.set(-6, 6.0, 0); g.add(combustor)
    // 透平段（高温燃气通过）
    const turbineSection = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.8, 3, 16),
        mat(0xaa7744, { roughness: 0.2, metalness: 0.6, emissive: 0x441100, emissiveIntensity: 0.45 }))
    turbineSection.position.set(-6, 1.2, 0); g.add(turbineSection)

    // === 2. 余热锅炉（HRSG — 立式管壳） ===
    const hrsg = new THREE.Mesh(new THREE.CylinderGeometry(2.0, 2.2, 12, 16),
        mat(0xa09080, { roughness: 0.45, metalness: 0.15 }))
    hrsg.position.set(2, 6.0, 0); g.add(hrsg)
    // 锅炉管束（内部可见管）
    for (let i = 0; i < 5; i++) {
        const tube = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 10, 6),
            mat(0x667788, { roughness: 0.3, metalness: 0.55 }))
        tube.position.set(2 + (i - 2) * 0.6, 6.0, 0); g.add(tube)
    }

    // === 3. 蒸汽轮机 + 发电机 ===
    const stBody = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.5, 5, 12), steel)
    stBody.position.set(8, 3.0, 0); g.add(stBody)
    // 发电机
    const generator = new THREE.Mesh(new THREE.BoxGeometry(2.0, 2.5, 2.0), steel)
    generator.position.set(11, 2.5, 0); g.add(generator)
    // 发电机冷却风扇
    const fanCone = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.5, 1.5, 12, 1, true),
        mat(0x668899, { roughness: 0.35, metalness: 0.5, transparent: true, opacity: 0.4 }))
    fanCone.position.set(12.5, 2.5, 0); g.add(fanCone)
    // 输电线路
    const powerLine = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 4, 6), steel)
    powerLine.position.set(11, 5.0, 0); g.add(powerLine)

    // === 4. CCS碳捕集系统 ===
    // 吸收塔（absorber）
    const absorber = new THREE.Mesh(new THREE.CylinderGeometry(1.8, 2.0, 10, 16),
        mat(0x8899aa, { roughness: 0.35, metalness: 0.4 }))
    absorber.position.set(-6, 8, -4); g.add(absorber)
    // 塔内有可见填料层
    for (let i = 0; i < 3; i++) {
        const packing = new THREE.Mesh(new THREE.BoxGeometry(2.8, 0.8, 2.8),
            mat(0xaabbcc, { roughness: 0.5, metalness: 0.15, transparent: true, opacity: 0.3 }))
        packing.position.set(-6, 5 + i * 2.5, -4); g.add(packing)
    }
    // 再生塔（regenerator）
    const regenerator = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.8, 8, 16),
        mat(0x998877, { roughness: 0.35, metalness: 0.35 }))
    regenerator.position.set(0, 7, -4); g.add(regenerator)

    // === 5. 烟囱（emission stack） ===
    const emissionStack = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 1.0, 18, 12),
        mat(0xd0b0a0, { roughness: 0.5, metalness: 0.1 }))
    emissionStack.position.set(4, 9, -4); g.add(emissionStack)

    // === 6. 冷却塔 ===
    const coolingTower = new THREE.Mesh(
        new THREE.CylinderGeometry(2.5, 3.5, 8, 24, 1, true),
        mat(0xaabbcc, { roughness: 0.4, metalness: 0.15, transparent: true, opacity: 0.5 }))
    coolingTower.position.set(-10, 4, -3); g.add(coolingTower)

    // === 7. 管道系统 ===
    for (let i = 0; i < 5; i++) {
        const pipeLen = 3 + Math.random() * 4
        const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, pipeLen, 8),
            mat(i % 2 === 0 ? PAL.blue : PAL.orange, { roughness: 0.3, metalness: 0.5 }))
        pipe.position.set(-3 + i * 3, 2.0 + (i % 2) * 1.5, 2 + (i % 3) * 0.5)
        g.add(pipe)
    }
    // 管廊桥架（cable tray / pipe rack）
    const rackMat = mat(0x556677, { roughness: 0.4, metalness: 0.4 })
    for (let ry = 8; ry <= 18; ry += 3) {
        const rack = new THREE.Mesh(new THREE.BoxGeometry(20, 0.12, 1.2), rackMat)
        rack.position.set(0, ry, -1.5)
        g.add(rack)
    }
    // 管道桥架立柱
    for (let rx = -8; rx <= 8; rx += 4) {
        const rackCol = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 18, 6), steel)
        rackCol.position.set(rx, 9, -1.5)
        g.add(rackCol)
    }

    // === 8. 霓虹 ===
    const utilRing = new THREE.Mesh(new THREE.TorusGeometry(8, 0.1, 8, 32),
        new THREE.MeshStandardMaterial({ color: neonColor, emissive: neonColor, emissiveIntensity: 0.22, roughness: 0.4, metalness: 0.6 }))
    utilRing.rotation.x = Math.PI / 2; utilRing.position.set(0, 1.0, 0); g.add(utilRing)

    // === 9. 动画钩子 ===
    g.userData.topY = 28
    g.userData.heatCenterY = 3.0
    g.userData.heatInternalH = 15.0
    g.userData.heatInternalR = 6.0

    // === 物料转变动画：能源→蒸汽/电力 ===
    const utilFlow = []
    // 蒸汽上升粒子
    for (let i = 0; i < 8; i++) {
        const stm = new THREE.Mesh(new THREE.SphereGeometry(0.2 + Math.random() * 0.15, 4, 4),
            new THREE.MeshBasicMaterial({
                color: 0xffffff, transparent: true, opacity: 0.15, depthWrite: false
            }))
        stm.position.set(2, 8 + Math.random() * 8, (Math.random() - 0.5) * 2)
        g.add(stm)
        utilFlow.push({
            obj: stm, phase: i * 0.12, period: 4.0,
            srcPos: new THREE.Vector3(2, 10, stm.position.z),
            dstPos: new THREE.Vector3(2, 20, stm.position.z),
            srcColor: 0xffffcc, dstColor: 0xccddff, scalePulse: 0.4,
        })
    }

    g.userData._matFlow = utilFlow
    return g
}
