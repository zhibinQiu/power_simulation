import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex, tankShellTex, wallPanelTex } from './utils.js'

/** _buildCaster 极致仿真连铸机3D模型
 *  钢水罐→中间包→结晶器→二冷区喷雾→拉矫机→火焰切割
 *  水喷雾冷却效果
 *  切割火花
 *  铸坯温度渐变（液态→半固态→全固态）
 */
export default function _buildCaster(bodyMat) {
    const g = new THREE.Group()
    const L = 30; const W = 8; const D = 10; const H = 14
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })
    const neonColor = 0x00ccff


    // === 1. 钢水罐（ladle turret — 回转台） ===
    const turretBase = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.5, 3, 16), steel)
    turretBase.position.set(0, 1.5, 0); g.add(turretBase)
    const turretArm = new THREE.Mesh(new THREE.BoxGeometry(4, 0.8, 0.8), steel)
    turretArm.position.set(0, 3.5, 0); g.add(turretArm)
    // 钢水罐
    const ladle = new THREE.Mesh(new THREE.CylinderGeometry(1.8, 1.5, 5, 16),
        mat(0xa08060, { roughness: 0.45, metalness: 0.25 }))
    ladle.position.set(2.5, 7.5, 0); g.add(ladle)
    // 钢水滑动水口
    const slideGate = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.3, 0.8, 8),
        mat(0x886655, { roughness: 0.3, metalness: 0.5, emissive: 0x220000, emissiveIntensity: 0.4 }))
    slideGate.position.set(2.5, 5.0, 0); g.add(slideGate)

    // === 2. 中间包（tundish — 分配钢水） ===
    const tundish = new THREE.Mesh(new THREE.BoxGeometry(4, 1.2, 1.5),
        mat(0xa08060, { roughness: 0.45, metalness: 0.25 }))
    tundish.position.set(0, 6.5, 0); g.add(tundish)
    // 浸入式水口（SEN）— 从中间包伸入结晶器
    const sen = new THREE.Mesh(new THREE.CylinderGeometry(0.15, 0.15, 2.5, 8),
        mat(0x996644, { roughness: 0.3, metalness: 0.5, emissive: 0x220000, emissiveIntensity: 0.5 }))
    sen.position.set(-0.5, 5.2, 0); g.add(sen)

    // === 3. 结晶器（mold — 铜结晶器） ===
    const mold = new THREE.Mesh(
        new THREE.BoxGeometry(1.2, 2.0, 1.8),
        mat(0xcc8844, { roughness: 0.2, metalness: 0.7, emissive: 0x331100, emissiveIntensity: 0.3 }))
    mold.position.set(-2, 3.5, 0); g.add(mold)

    // === 4. 弧形段 + 二冷区（垂直段→弧形弯曲→水平矫直 — 弧形连铸机标志） ===
    const segCount = 8
    const internalSlabs = []

    for (let i = 0; i < segCount; i++) {
        // 铸坯从结晶器下方垂直向下→弧形弯曲→水平延伸
        const t = i / (segCount - 1)
        let segX, segY, segAng
        if (t < 0.3) {
            // 垂直段（二冷直段）
            segX = -2.0
            segY = 3.0 - t * 4.0
            segAng = 0
        } else if (t < 0.75) {
            // 弧形段（绕结晶器下方圆心转过 ~60°）
            const arcT = (t - 0.3) / 0.45
            const cx = 0.8, cy = 3.5, R = 3.0
            const ang = Math.PI / 3 * arcT
            segX = cx - R * Math.sin(ang)
            segY = cy - R * Math.cos(ang)
            segAng = ang
        } else {
            // 水平矫直段（拉矫机+切割）
            const horT = (t - 0.75) / 0.25
            segX = -1.8 + horT * 8.0
            segY = 0.6
            segAng = 0
        }
        const segThick = 0.7 - i * 0.04
        const seg = new THREE.Mesh(new THREE.BoxGeometry(2.0, segThick, 1.6),
            new THREE.MeshStandardMaterial({ roughness: 0.25, metalness: 0.1, emissive: 0xff4400, emissiveIntensity: 0.6 - i * 0.06 }))
        seg.position.set(segX, segY, 0)
        seg.rotation.z = segAng || 0
        g.add(seg)
        internalSlabs.push(seg)
    }

    // === 5. 二冷区水喷雾（冷却水 + 气雾 — 沿垂直段/弧形段分布） ===
    // 与弧形段同公式计算喷雾中心点
    function segPos(t) {
        if (t < 0.3) return { x: -2.0, y: 3.0 - t * 4.0 }
        if (t < 0.75) {
            const arcT = (t - 0.3) / 0.45
            const cx = 0.8, cy = 3.5, R = 3.0
            const ang = Math.PI / 3 * arcT
            return { x: cx - R * Math.sin(ang), y: cy - R * Math.cos(ang) }
        }
        const horT = (t - 0.75) / 0.25
        return { x: -1.8 + horT * 8.0, y: 0.6 }
    }
    const sprayPositions = []
    for (let i = 0; i < segCount - 1; i++) {
        const t = i / (segCount - 1)
        const sp = segPos(t)
        for (let s = -1; s <= 1; s += 2) {
            for (let j = 0; j < 2; j++) {
                sprayPositions.push({ x: sp.x, y: sp.y + 0.5 + j * 0.5, z: s * 1.0, idx: sprayPositions.length })
            }
        }
    }
    const sprayGroup = new THREE.Group()
    sprayGroup.name = 'casterSprays'
    for (const sp of sprayPositions) {
        const drop = new THREE.Mesh(new THREE.SphereGeometry(0.08 + Math.random() * 0.04, 4, 4),
            new THREE.MeshBasicMaterial({
                color: 0xaaddff, transparent: true, opacity: 0.4, depthWrite: false
            }))
        drop.position.set(sp.x, sp.y, sp.z)
        drop.userData.baseX = sp.x
        drop.userData.baseY = sp.y
        sprayGroup.add(drop)
    }
    g.add(sprayGroup)

    // === 6. 拉矫机（withdrawal & straightener — 水平矫直段） ===
    for (let i = 0; i < 4; i++) {
        const roll = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 1.8, 8), steel)
        roll.rotation.z = Math.PI / 2
        roll.position.set(-1.0 + i * 1.2, 1.3, 0); g.add(roll)
    }

    // === 7. 火焰切割机（torch cutting — 水平段末端） ===
    const torchHead = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.25, 0.6, 8),
        mat(0xcc8844, { roughness: 0.25, metalness: 0.6 }))
    torchHead.position.set(5.5, 1.4, 1.2); g.add(torchHead)

    // 切割火花粒子
    const sparkGroup = new THREE.Group()
    sparkGroup.name = 'casterSparks'
    for (let i = 0; i < 12; i++) {
        const spark = new THREE.Mesh(new THREE.SphereGeometry(0.06 + Math.random() * 0.06, 4, 4),
            new THREE.MeshBasicMaterial({
                color: 0xffaa44, emissive: 0xff8800, transparent: true,
                opacity: 0.8, depthWrite: false
            }))
        spark.position.set(5.5, 1.2 + Math.random() * 1, 0.5 + Math.random() * 0.5)
        sparkGroup.add(spark)
    }
    g.add(sparkGroup)

    // === 8. 铸坯穿行条（strand moving through — 水平段下方） ===
    const strand = new THREE.Mesh(new THREE.BoxGeometry(4.0, 0.6, 1.6),
        new THREE.MeshStandardMaterial({
            roughness: 0.2, metalness: 0.1, emissive: 0xff4400, emissiveIntensity: 1.5,
            transparent: true, opacity: 0.8, depthWrite: false
        }))
    strand.position.set(2.0, 0.6, 0); g.add(strand)

    // === 9. 输出辊道 ===
    for (let i = 0; i < 5; i++) {
        const rRoll = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.25, 1.8, 8), steel)
        rRoll.rotation.z = Math.PI / 2
        rRoll.position.set(7 + i * 1.5, 1.0, 0); g.add(rRoll)
    }

    // === 9.5 侧边操作走道 + 顶盖 ===
    const walkMat = mat(0x445566, { roughness: 0.45, metalness: 0.35, transparent: true, opacity: 0.5 })
    for (const s of [-1, 1]) {
        const walkway = new THREE.Mesh(new THREE.BoxGeometry(L * 0.85, 0.12, 0.7), walkMat)
        walkway.position.set(0, 4.5, s * 2.0)
        g.add(walkway)
    }
    // 顶部防溅盖
    const coverMat = mat(0x334455, { roughness: 0.5, metalness: 0.3, transparent: true, opacity: 0.35 })
    const cover = new THREE.Mesh(new THREE.BoxGeometry(L * 0.8, 0.2, 3.6), coverMat)
    cover.position.set(0, 6.0, 0)
    g.add(cover)

    // === 10. 霓虹 ===
    const casterLine = new THREE.Mesh(new THREE.BoxGeometry(L * 0.9, 0.05, 0.15),
        new THREE.MeshStandardMaterial({ color: neonColor, emissive: neonColor, emissiveIntensity: 0.5 }))
    casterLine.position.set(0, 0.3, 0); g.add(casterLine)
    const casterRing = new THREE.Mesh(new THREE.TorusGeometry(1.5, 0.1, 8, 16),
        new THREE.MeshStandardMaterial({ color: neonColor, emissive: neonColor, emissiveIntensity: 0.4, roughness: 0.2 }))
    casterRing.rotation.x = Math.PI / 2; casterRing.position.set(0, 3.5, 0); g.add(casterRing)

    // === 11. 动画钩子 ===
    g.userData.topY = 18
    g.userData.heatCenterY = 3.0
    g.userData.heatInternalH = 8.0
    g.userData.heatInternalR = 5.0

    g.userData._casterStrand = strand
    g.userData._internalSlabs = internalSlabs
    g.userData._casterSprays = sprayGroup.children.filter(c => c.material && c.material.opacity !== undefined)
    g.userData._casterSparks = sparkGroup.children

    // === 物料转变动画：液态钢水→结晶凝固→全固态铸坯 ===
    // 颜色与连线载运体一致：liquid_steel(0xff7733)→billet(0xff5522)
    const casterFlow = []
    for (let i = 0; i < segCount; i++) {
        const t = i / (segCount - 1); const colorProgress = t
        const seg = internalSlabs[i]
        const sp = segPos(t)
        const srcClr = colorProgress < 0.25 ? 0xff7733 : colorProgress < 0.5 ? 0xdd4400 : 0xcc3311
        const dstClr = colorProgress < 0.25 ? 0xdd4400 : colorProgress < 0.5 ? 0xcc3311 : 0xff5522
        casterFlow.push({
            obj: seg, phase: i * 0.12, period: 6.5,
            srcPos: new THREE.Vector3(sp.x, sp.y, 0), dstPos: new THREE.Vector3(sp.x, sp.y, 0),
            srcColor: srcClr, dstColor: dstClr,
        })
    }

    g.userData._matFlow = casterFlow
    return g
}
