import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex } from './utils.js'

/** buildRollers 极致仿真轧机3D模型
 *  加热坯→除鳞→粗轧→精轧→层流冷却→卷取
 *  轧辊间可见红热钢坯逐道次变薄变长
 *  冷却水幕效果
 */
export default function buildRollers(bodyMat) {
    const g = new THREE.Group()
    const L = 30; const D = 6; const H = 12
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })


    // === 1. 轧机机架（粗轧R1→R2→精轧F1-F6） ===
    const standCount = 7
    const standPositions = []
    const workRolls = []
    for (let i = 0; i < standCount; i++) {
        const sx = -L * 0.4 + i * (L * 0.65 / (standCount - 1))
        standPositions.push(sx)

        const housingH = 2.8 - i * 0.1
        // 牌坊（mill housing）
        for (const s of [-1, 1]) {
            const housing = new THREE.Mesh(new THREE.BoxGeometry(1.0, housingH, 0.6), steel)
            housing.position.set(sx, housingH / 2 + 2.0, s * 0.9); g.add(housing)
        }
        // 工作辊+支撑辊
        const rollR = 0.3 + i * 0.02
        const wr = new THREE.Mesh(new THREE.CylinderGeometry(rollR, rollR, 1.8, 12), steel)
        wr.rotation.z = Math.PI / 2
        wr.position.set(sx, 2.2, 0); g.add(wr)
        workRolls.push(wr)
        const br = new THREE.Mesh(new THREE.CylinderGeometry(0.5 + i * 0.03, 0.5 + i * 0.03, 1.8, 12), steel)
        br.rotation.z = Math.PI / 2
        br.position.set(sx, 3.0, 0); g.add(br)
        workRolls.push(br)
        // 压下螺丝
        const screw = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 1.5, 8), steel)
        screw.position.set(sx, 4.2, 0); g.add(screw)
    }

    // === 2. 除鳞箱（descaling box — 高压水除鳞） ===
    const descaleBox = new THREE.Mesh(new THREE.BoxGeometry(1.5, 1.5, 2.5),
        mat(0x667788, { roughness: 0.4, metalness: 0.5, transparent: true, opacity: 0.5 }))
    descaleBox.position.set(-L * 0.42, 3.5, 0); g.add(descaleBox)

    // === 3. 主传动电机 ===
    for (let i = 0; i < standCount; i++) {
        const motor = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.8, 1.5, 12), steel)
        motor.rotation.z = Math.PI / 2
        motor.position.set(standPositions[i], 2.2, 1.8); g.add(motor)
    }

    // === 4. 轧件（slab/plate — 粗→精逐步变薄） ===
    // 粗轧坯
    const roughSlab = new THREE.Mesh(new THREE.BoxGeometry(4, 0.8, 1.6),
        new THREE.MeshStandardMaterial({
            roughness: 0.2, metalness: 0.1, emissive: 0xbf5a2e, emissiveIntensity: 0.5,
            transparent: true, opacity: 0.7, depthWrite: false
        }))
    roughSlab.position.set(standPositions[0], 2.0, 0); g.add(roughSlab)
    roughSlab.name = 'roughSlab'

    // 精轧带钢
    const finalStrip = new THREE.Mesh(new THREE.BoxGeometry(4, 0.15, 1.2),
        new THREE.MeshStandardMaterial({
            roughness: 0.15, metalness: 0.15, emissive: 0xa0502c, emissiveIntensity: 0.4,
            transparent: true, opacity: 0.6, depthWrite: false
        }))
    finalStrip.position.set(standPositions[standCount - 1], 1.8, 0); g.add(finalStrip)
    finalStrip.name = 'finalStrip'

    // === 5. 层流冷却系统（laminar cooling） ===
    const coolingLen = 6
    const coolingX = standPositions[standCount - 1] + 3
    // 冷却水箱
    const waterBox = new THREE.Mesh(new THREE.BoxGeometry(coolingLen, 0.8, 2.5),
        mat(0x557799, { roughness: 0.3, metalness: 0.5, transparent: true, opacity: 0.35 }))
    waterBox.position.set(coolingX, 3.0, 0); g.add(waterBox)
    // 水帘喷嘴
    for (let i = 0; i < 8; i++) {
        const nx = coolingX - coolingLen / 2 + i * (coolingLen / 7)
        const waterJet = new THREE.Mesh(new THREE.CylinderGeometry(0.05, 0.08, 1.2, 6),
            new THREE.MeshBasicMaterial({
                color: 0xcfdce6, transparent: true, opacity: 0.35, depthWrite: false
            }))
        waterJet.position.set(nx, 2.5, 0); g.add(waterJet)
    }

    // === 6. 卷取机（downcoiler） ===
    const coilerBase = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.8, 2.0, 16), steel)
    coilerBase.position.set(L * 0.42, 1.0, 0); g.add(coilerBase)
    // 卷取轴
    const coilerSpindle = new THREE.Mesh(new THREE.CylinderGeometry(0.6, 0.6, 1.8, 8), steel)
    coilerSpindle.rotation.z = Math.PI / 2
    coilerSpindle.position.set(L * 0.42, 1.5, 0); g.add(coilerSpindle)
    // 钢卷（coil）
    const coil = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.2, 1.5, 24),
        new THREE.MeshStandardMaterial({
            roughness: 0.2, metalness: 0.25, emissive: 0x662200, emissiveIntensity: 0.3,
            transparent: true, opacity: 0.6, depthWrite: false
        }))
    coil.rotation.z = Math.PI / 2
    coil.position.set(L * 0.42, 1.5, 0); g.add(coil)

    // === 7. 轧线霓虹 ===
    const rollLine = new THREE.Mesh(new THREE.BoxGeometry(L * 0.85, 0.04, 0.12),
        mat(0x42566b, { roughness: 0.55, metalness: 0.35 }))
    rollLine.position.set(0, 1.0, 0); g.add(rollLine)

    // === 7.5 辊道传送台 ===
    const rollTables = []
    for (let i = 0; i < standCount - 1; i++) {
        const midX = (standPositions[i] + standPositions[i + 1]) / 2
        const table = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 1.6, 6), steel)
        table.rotation.z = Math.PI / 2
        table.position.set(midX, 1.2, 0)
        g.add(table)
        rollTables.push(table)
    }
    // 侧边操作走道
    const walkMat = mat(0x445566, { roughness: 0.45, metalness: 0.35, transparent: true, opacity: 0.5 })
    const walkLen = L * 0.85
    for (const s of [-1, 1]) {
        const walkway = new THREE.Mesh(new THREE.BoxGeometry(walkLen, 0.15, 0.8), walkMat)
        walkway.position.set(0, 5.5, s * 2.2)
        g.add(walkway)
    }

    // === 8. 动画钩子 ===
    g.userData.topY = 16
    g.userData.heatCenterY = 2.5
    g.userData.heatInternalH = 6.0
    g.userData.heatInternalR = 3.0
    // 轧辊/辊道/卷取轴旋转（供 scene.js rollers 动画驱动）
    g.userData._rollers = rollTables.concat(workRolls)

    // === 物料转变动画：连铸坯(橙红)→热轧→钢材(暗红) ===
    const rollFlow = []
    for (let i = 0; i < 4; i++) {
        const px = -L * 0.38 + i * (L * 0.6 / 3)
        const thin = 0.8 - i * 0.2
        const bar = new THREE.Mesh(new THREE.BoxGeometry(2.5, 0.7 * thin, 1.6),
            new THREE.MeshStandardMaterial({ roughness: 0.25, metalness: 0.1 }))
        bar.position.set(px, 2.2, 0); g.add(bar)
        rollFlow.push({
            obj: bar, phase: i * 0.25, period: 4.5,
            srcPos: new THREE.Vector3(-L * 0.42, 2.2, 0),
            dstPos: new THREE.Vector3(L * 0.42, 2.0, 0),
            srcColor: 0xc0764a, dstColor: 0xa0502c, scalePulse: 0.08,
        })
    }

    g.userData._matFlow = rollFlow
    return g
}
