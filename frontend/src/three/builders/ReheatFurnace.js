import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex } from './utils.js'

/** _buildReheatFurnace 极致仿真步进式加热炉3D模型
 *  冷坯/热坯装料 → 预热段 → 加热段 → 均热段 → 出钢
 *  炉内可见燃烧火焰
 *  炉顶烧嘴脉动发光
 *  步进梁步进运动
 */
export default function _buildReheatFurnace(bodyMat) {
    const g = new THREE.Group()
    const L = 22; const D = 10; const H = 10
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })
    const neonColor = 0x2c6e9e


    // === 1. 炉体（长条形步进式加热炉：装料端→预热→加热→均热→出料端） ===
    const furnaceBody = new THREE.Mesh(new THREE.BoxGeometry(L * 0.8, 2.0, D * 0.6),
        mat(0x9a8070, { roughness: 0.45, metalness: 0.15 }))
    furnaceBody.position.y = 2.6; g.add(furnaceBody)
    // 炉顶（带拱形感的两段式炉顶）
    const roofArch = new THREE.Mesh(new THREE.BoxGeometry(L * 0.8, 0.7, D * 0.6),
        mat(0xb0a090, { roughness: 0.5, metalness: 0.1, transparent: true, opacity: 0.55 }))
    roofArch.position.y = 3.9; g.add(roofArch)
    // 炉体分段（预热段/加热段/均热段 分隔线）
    for (let i = 0; i < 2; i++) {
        const line = new THREE.Mesh(new THREE.BoxGeometry(0.15, 2.0, D * 0.62),
            mat(0x776655, { roughness: 0.5, metalness: 0.2 }))
        line.position.set(-L * 0.12 + i * L * 0.24, 2.6, 0); g.add(line)
    }

    // === 2. 炉内钢坯（双排 + 步进梁承载 — 预热→加热→均热 三段温区） ===
    const internalSlabs = []
    const slabCount = 6
    const stepBeams = []
    for (let i = 0; i < slabCount; i++) {
        const slabX = -L * 0.35 + i * (L * 0.7 / (slabCount - 1))
        for (const sz of [-0.8, 0.8]) {
            const slab = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.4, 1.2),
                new THREE.MeshStandardMaterial({
                    roughness: 0.2, metalness: 0.1, emissive: 0xbf5a2e, emissiveIntensity: 0.3 + i * 0.1
                }))
            slab.position.set(slabX, 3.35, sz); g.add(slab)
            slab.name = i < 2 ? 'coldSlab' : i >= 4 ? 'soakingSlab' : 'heatingSlab'
            internalSlabs.push(slab)
        }
        // 步进梁（水冷滑轨，托举钢坯）
        const beam = new THREE.Mesh(new THREE.BoxGeometry(2.0, 0.18, 0.18),
            mat(0x667788, { roughness: 0.3, metalness: 0.6 }))
        beam.position.set(slabX, 3.05, 0); g.add(beam)
        stepBeams.push(beam)
    }

    // === 3. 炉顶烧嘴（roof burners — 布置在均热段/加热段） ===
    const burnerGroup = new THREE.Group()
    burnerGroup.name = 'roofBurners'
    for (let i = 3; i < slabCount; i++) {
        const bx = -L * 0.35 + i * (L * 0.7 / (slabCount - 1))
        for (const s of [-1, 1]) {
            const burner = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.3, 0.6, 8),
                mat(0x996644, { roughness: 0.3, metalness: 0.5, emissive: 0x331100, emissiveIntensity: 0.6 }))
            burner.position.set(bx, 4.5, s * D * 0.2)
            burnerGroup.add(burner)
            // 火焰锥
            const flame = new THREE.Mesh(new THREE.ConeGeometry(0.2, 0.8, 8),
                new THREE.MeshStandardMaterial({
                    color: 0xff8844, emissive: 0xcc3a00, emissiveIntensity: 0.8,
                    roughness: 0.3, metalness: 0.05, transparent: true, opacity: 0.55, depthWrite: false
                }))
            flame.rotation.x = Math.PI
            flame.position.set(bx, 4.0, s * D * 0.2)
            burnerGroup.add(flame)
        }
    }
    g.add(burnerGroup)
    // 收集烧嘴材料引用用于脉动动画
    const burnerFlames = []
    burnerGroup.children.forEach(c => { if (c.material && c.material.emissiveIntensity > 1) burnerFlames.push(c) })

    // === 4. 炉门（装料端+出料端） ===
    for (const s of [-1, 1]) {
        const doorX = s * L * 0.41
        const door = new THREE.Mesh(new THREE.BoxGeometry(0.3, 2.5, D * 0.6),
            mat(0x665544, { roughness: 0.35, metalness: 0.5, emissive: 0x331100, emissiveIntensity: 0.2 }))
        door.position.set(doorX, 2.5, 0); g.add(door)
        // 炉门内可见火焰
        const doorFlare = new THREE.Mesh(new THREE.BoxGeometry(0.15, 2.0, D * 0.4),
            new THREE.MeshStandardMaterial({
                color: 0xff8844, emissive: 0xcc3a00, emissiveIntensity: 0.8,
                transparent: true, opacity: 0.55, depthWrite: false
            }))
        doorFlare.position.set(doorX, 2.5, 0); g.add(doorFlare)
    }

    // === 5. 烟道（烟囱） ===
    const stack = new THREE.Mesh(new THREE.CylinderGeometry(0.8, 1.1, 10, 12),
        mat(0xcca080, { roughness: 0.5, metalness: 0.1 }))
    stack.position.set(L * 0.45, 5, D * 0.35); g.add(stack)

    // === 6. 进料/出料辊道 ===
    for (const s of [-1, 1]) {
        for (let i = 0; i < 3; i++) {
            const roll = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.25, 1.8, 8), steel)
            roll.rotation.z = Math.PI / 2
            roll.position.set(s * (L * 0.42 + i * 1.5), 2.5, 0); g.add(roll)
        }
    }

    // === 7. 霓虹 ===
    const reheatRing = new THREE.Mesh(new THREE.TorusGeometry(L * 0.42, 0.12, 8, 32),
        new THREE.MeshStandardMaterial({ color: neonColor, emissive: neonColor, emissiveIntensity: 0.22, roughness: 0.4, metalness: 0.6 }))
    reheatRing.rotation.x = Math.PI / 2; reheatRing.position.set(0, 2.0, 0); g.add(reheatRing)

    // === 8. 动画钩子 ===
    g.userData.topY = 16
    g.userData.heatCenterY = 3.0
    g.userData.heatInternalH = 4.0
    g.userData.heatInternalR = D * 0.3
    g.userData._internalSlabs = internalSlabs
    g.userData._reheatBurners = burnerFlames
    g.userData._reheatDoorFlares = []

    // === 物料转变动画：冷坯→加热→热坯 ===
    // billet→hot_billet: 0xbf5a2e→0xc67a3c
    const heatFlow = []
    for (let i = 0; i < slabCount; i++) {
        const slab = internalSlabs[i]
        heatFlow.push({
            obj: slab, phase: i * 0.16, period: 6.5,
            srcPos: new THREE.Vector3(slab.position.x, 3.3, 0),
            dstPos: new THREE.Vector3(slab.position.x, 3.3, 0),
            srcColor: i < 2 ? 0x666666 : i < 4 ? 0xbf5a2e : 0xb55a34,
            dstColor: i < 2 ? 0xbf5a2e : i < 4 ? 0xb55a34 : 0xc67a3c,
            scalePulse: 0.12,
        })
    }

    g.userData._matFlow = heatFlow
    return g
}
