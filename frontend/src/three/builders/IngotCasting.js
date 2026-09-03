import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex } from './utils.js'

/** _buildIngotCasting 极致仿真模铸3D模型
 *  下注式模铸：钢水钢包→中注管→汤道→钢锭模
 *  多个钢锭模内可见钢水凝固
 *  脱模后钢锭冷却
 */
export default function _buildIngotCasting(bodyMat) {
    const g = new THREE.Group()
    const L = 22; const D = 12; const H = 14
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })


    // === 1. 钢包（ladle） ===
    const ladle = new THREE.Mesh(new THREE.CylinderGeometry(2.5, 2.0, 5, 16),
        mat(0xa08060, { roughness: 0.45, metalness: 0.25 }))
    ladle.position.set(0, 7.0, 0); g.add(ladle)
    // 滑动水口
    const slideGate = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.3, 0.6, 8),
        mat(0x886655, { roughness: 0.3, metalness: 0.5, emissive: 0x220000, emissiveIntensity: 0.35 }))
    slideGate.position.set(0, 4.5, 0); g.add(slideGate)

    // === 2. 中注管（center runner） ===
    const centerRunner = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.5, 3.5, 8),
        mat(0x9a8070, { roughness: 0.5, metalness: 0.1 }))
    centerRunner.position.y = 2.5; g.add(centerRunner)

    // === 3. 底板 + 汤道砖（runner bricks） ===
    const runnerPlate = new THREE.Mesh(new THREE.BoxGeometry(L * 0.6, 0.4, D * 0.5),
        mat(0x8a7a6a, { roughness: 0.5, metalness: 0.1 }))
    runnerPlate.position.y = 1.0; g.add(runnerPlate)

    // === 4. 钢锭模（ingot molds — 8个排列） ===
    const moldGroup = new THREE.Group()
    moldGroup.name = 'molds'
    const moldPositions = [
        [-4, 0], [4, 0], [0, -3], [0, 3],
        [-3, -3], [-3, 3], [3, -3], [3, 3]
    ]
    const internalMolds = []
    moldPositions.forEach(([mx, mz]) => {
        // 锭模外壳
        const mold = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.5, 5, 16),
            mat(0x886655, { roughness: 0.45, metalness: 0.25 }))
        mold.position.set(mx, 3.0, mz); g.add(mold)
        // 锭模内钢水（可见）
        const steelInside = new THREE.Mesh(new THREE.CylinderGeometry(0.9, 1.1, 4.0, 16),
            new THREE.MeshStandardMaterial({
                roughness: 0.05, metalness: 0.1, emissive: 0x8a4018, emissiveIntensity: 0.7,
                transparent: true, opacity: 0.7, depthWrite: false
            }))
        steelInside.position.set(mx, 3.5, mz)
        steelInside.name = 'steelInside'
        internalMolds.push(steelInside); g.add(steelInside)
    })

    // === 5. 脱模后钢锭（冷却中） ===
    for (let i = 0; i < 4; i++) {
        const ingot = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 1.0, 4.5, 16),
            new THREE.MeshStandardMaterial({
                roughness: 0.2, metalness: 0.3, emissive: 0x662200, emissiveIntensity: 0.4
            }))
        ingot.position.set(L * 0.35, 2.5 + Math.random(), D * 0.3 * (i - 1.5))
        g.add(ingot)
    }

    // === 5.5 天车轨道 + 吊钩（overhead crane） ===
    for (const s of [-1, 1]) {
        const craneRail = new THREE.Mesh(new THREE.BoxGeometry(L * 1.05, 0.15, 0.4), steel)
        craneRail.position.set(0, H - 1.5, s * D * 0.45); g.add(craneRail)
    }
    // 天车横梁
    const craneBridge = new THREE.Mesh(new THREE.BoxGeometry(2.5, 0.5, D * 0.85), steel)
    craneBridge.position.set(0, H - 0.8, 0); g.add(craneBridge)
    // 吊钩
    const hook = new THREE.Mesh(new THREE.TorusGeometry(0.6, 0.1, 6, 12), steel)
    hook.position.set(0, H - 3, 0); g.add(hook)
    const cable = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 2.5, 6), steel)
    cable.position.set(0, H - 1.8, 0); g.add(cable)

    // === 6. 霓虹 ===
    const ingotRing = new THREE.Mesh(new THREE.TorusGeometry(2.5, 0.1, 8, 32),
        mat(0x42566b, { roughness: 0.55, metalness: 0.35 }))
    ingotRing.rotation.x = Math.PI / 2; ingotRing.position.set(0, 3.5, 0); g.add(ingotRing)

    // === 7. 动画钩子 ===
    g.userData.topY = 20
    g.userData.heatCenterY = 3.0
    g.userData.heatInternalH = 8.0
    g.userData.heatInternalR = 4.0
    g.userData._internalSlabs = internalMolds

    // === 物料转变动画：钢水→模铸凝固→钢锭 ===
    // 颜色与连线载运体一致：crude_steel(0xbf6a30)→billet(0xbf5a2e)
    const ingotFlow = []
    internalMolds.forEach((steel, i) => {
        ingotFlow.push({
            obj: steel, phase: i * 0.12, period: 7.0,
            srcPos: new THREE.Vector3(steel.position.x, 3.5, steel.position.z),
            dstPos: new THREE.Vector3(steel.position.x, 3.5, steel.position.z),
            srcColor: 0xbf6a30, dstColor: 0xbf5a2e,
        })
    })

    g.userData._matFlow = ingotFlow
    return g
}
