import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex, tankShellTex, wallPanelTex } from './utils.js'

/** _buildConverter 极致仿真转炉3D模型
 *  氧枪从顶部插入 + 高压氧喷入钢水产生火花
 *  底吹气体搅动钢水
 *  炉渣层浮于钢水表面
 *  耳轴倾动机构
 *  除尘烟罩
 */
export default function _buildConverter(bodyMat) {
    const g = new THREE.Group()
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })


    // ========== 可倾动炉体（绕耳轴旋转） ==========
    // 耳轴中心高度
    const TRUNNION_Y = 3.0
    const vessel = new THREE.Group()
    vessel.position.y = TRUNNION_Y
    g.add(vessel)

    // 炉身锥体（上窄下宽）
    const bodyTop = new THREE.Mesh(new THREE.CylinderGeometry(3.0, 3.6, 4.5, 24), bodyMat)
    bodyTop.position.y = 8 - TRUNNION_Y; vessel.add(bodyTop)
    // 炉腹（最宽处 — 熔池主体）
    const bodyMid = new THREE.Mesh(new THREE.CylinderGeometry(3.6, 5.0, 5, 24), bodyMat)
    bodyMid.position.y = 3.2 - TRUNNION_Y; vessel.add(bodyMid)
    // 炉底锥形
    const bodyBot = new THREE.Mesh(new THREE.CylinderGeometry(3.5, 3.0, 2.5, 24), bodyMat)
    bodyBot.position.y = -1.5 - TRUNNION_Y; vessel.add(bodyBot)
    // 炉底封板
    const botCap = new THREE.Mesh(new THREE.CylinderGeometry(3.0, 3.2, 0.6, 24),
        mat(0x9a8070, { metalness: 0.1, roughness: 0.5 }))
    botCap.position.y = -3.0 - TRUNNION_Y; vessel.add(botCap)
    // 炉口（顶部开口）
    const bodyNeck = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 3.0, 2.5, 24), bodyMat)
    bodyNeck.position.y = 11.5 - TRUNNION_Y; vessel.add(bodyNeck)

    // 耳轴（trunnion）— 倾动轴，随炉体一起旋转
    const trunnionL = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 1.8, 12), steel)
    trunnionL.rotation.z = Math.PI / 2; trunnionL.position.set(-5.2, 0, 0); vessel.add(trunnionL)
    const trunnionR = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 1.8, 12), steel)
    trunnionR.rotation.z = Math.PI / 2; trunnionR.position.set(5.2, 0, 0); vessel.add(trunnionR)

    // ========== 固定支撑结构（不随炉体旋转） ==========
    for (const s of [-1, 1]) {
        // 回转轴承座（固定于地面支撑柱）
        const bearing = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.0, 1.8, 16), steel)
        bearing.position.set(s * 5.8, TRUNNION_Y, 0); g.add(bearing)
        // 支撑柱
        const support = new THREE.Mesh(new THREE.BoxGeometry(1.5, 8, 1.5), steel)
        support.position.set(s * 5.8, -1, 0); g.add(support)
    }

    // ========== 操作平台（多层工作平台 + 栏杆） ==========
    const platformMat = mat(0x445566, { roughness: 0.45, metalness: 0.35, transparent: true, opacity: 0.55 })
    const platformLevels = [
        { y: -1.0, w: 18, d: 12 },
        { y: 5.0, w: 16, d: 10 },
        { y: 10.0, w: 14, d: 8 },
    ]
    for (const pl of platformLevels) {
        const pf = new THREE.Mesh(new THREE.BoxGeometry(pl.w, 0.2, pl.d), platformMat)
        pf.position.set(0, pl.y, 0)
        pf.receiveShadow = true
        g.add(pf)
        // 栏杆柱（四角）
        for (const sx of [-1, 1]) {
            for (const sz of [-1, 1]) {
                const post = new THREE.Mesh(new THREE.CylinderGeometry(0.08, 0.08, 1.2, 6), steel)
                post.position.set(sx * pl.w * 0.45, pl.y + 0.7, sz * pl.d * 0.45)
                g.add(post)
            }
        }
        // 栏杆横梁
        for (const sz of [-1, 1]) {
            const rail = new THREE.Mesh(new THREE.BoxGeometry(pl.w * 0.9, 0.06, 0.06), steel)
            rail.position.set(0, pl.y + 1.2, sz * pl.d * 0.45)
            g.add(rail)
        }
        for (const sx of [-1, 1]) {
            const rail = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.06, pl.d * 0.9), steel)
            rail.position.set(sx * pl.w * 0.45, pl.y + 1.2, 0)
            g.add(rail)
        }
    }

    // 楼梯柱（连接各层平台）
    const stairPos = new THREE.Vector3(7.5, 0, 4.5)
    for (const y of [-1.0, 5.0]) {
        const stair = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 6.2, 6), steel)
        stair.position.set(stairPos.x, y + 3.1, stairPos.z)
        g.add(stair)
    }

    // 废钢料篮（位于平台上方）
    const scrapBasket = new THREE.Mesh(
        new THREE.CylinderGeometry(2.5, 2.0, 3, 14, 1, true),
        mat(0x778899, { roughness: 0.35, metalness: 0.5, transparent: true, opacity: 0.5 }))
    scrapBasket.position.set(6, 12, -3)
    g.add(scrapBasket)

    // ========== 氧枪系统（固定，从炉口插入） ==========
    // 氧枪枪体（从炉口插入炉内）
    const lancePipe = new THREE.Mesh(new THREE.CylinderGeometry(0.25, 0.25, 14, 8),
        mat(0x8899aa, { roughness: 0.3, metalness: 0.55 }))
    lancePipe.position.set(0, 16, 0); g.add(lancePipe)
    lancePipe.name = '_lancePipe'

    // 氧枪喷头（枪尖 — 多孔喷嘴）
    const lanceTip = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.22, 0.8, 8),
        mat(0xcc8844, { roughness: 0.25, metalness: 0.6, emissive: 0x331100, emissiveIntensity: 0.4 }))
    lanceTip.position.set(0, 9.0, 0); g.add(lanceTip)
    lanceTip.name = '_lanceTip'

    // 氧枪提升装置（上部）
    const lanceCarriage = new THREE.Mesh(new THREE.BoxGeometry(2.0, 1.0, 1.5), steel)
    lanceCarriage.position.set(0, 23, 0); g.add(lanceCarriage)

    // ========== 除尘烟罩（固定于炉口上方） ==========
    const hood = new THREE.Mesh(
        new THREE.CylinderGeometry(3.0, 3.5, 2.5, 24, 1, true),
        mat(0x778899, { roughness: 0.4, metalness: 0.45, transparent: true, opacity: 0.6, depthWrite: false })
    )
    hood.position.y = 13.5; g.add(hood)

    // ========== 氧枪喷吹火花粒子（氧射入钢水表面产生高温火花） ==========
    const sparkGroup = new THREE.Group()
    sparkGroup.name = 'convSparks'
    for (let i = 0; i < 20; i++) {
        const spark = new THREE.Mesh(new THREE.SphereGeometry(0.12 + Math.random() * 0.1, 4, 4),
            new THREE.MeshBasicMaterial({
                color: 0xffd27a, transparent: true,
                opacity: 0.65 + Math.random() * 0.35, depthWrite: false
            }))
        spark.position.set((Math.random() - 0.5) * 1.5, 4 + Math.random() * 5 - TRUNNION_Y, (Math.random() - 0.5) * 1.5)
        sparkGroup.add(spark)
    }
    vessel.add(sparkGroup)

    // ========== 底吹气体搅拌气泡（从炉底注入 Ar/N2） ==========
    const bottomBubbs = []
    for (let i = 0; i < 6; i++) {
        const bub = new THREE.Mesh(new THREE.SphereGeometry(0.15 + Math.random() * 0.15, 4, 4),
            new THREE.MeshBasicMaterial({
                color: 0xffffff, transparent: true, opacity: 0.25, depthWrite: false
            }))
        bub.position.set((Math.random() - 0.5) * 3.5, -2.5 + Math.random() * 3 - TRUNNION_Y, (Math.random() - 0.5) * 3.5)
        bottomBubbs.push(bub); vessel.add(bub)
    }

    // ========== 炉内钢水熔池（内部可见 — 液态钢水） ==========
    const meltPool = new THREE.Mesh(
        new THREE.CylinderGeometry(3.8, 4.2, 3.5, 24),
        mat(0xb35a28, {
            roughness: 0.2, metalness: 0.08, emissive: 0x773010, emissiveIntensity: 0.35,
            transparent: true, opacity: 0.8, depthWrite: false
        })
    )
    meltPool.position.y = 1.5 - TRUNNION_Y; vessel.add(meltPool)

    // 钢水表面涟漪（ring ripples）
    const ripples = []
    for (let i = 0; i < 3; i++) {
        const ripple = new THREE.Mesh(new THREE.TorusGeometry(1.8 + i * 1.0, 0.08, 6, 24),
            new THREE.MeshStandardMaterial({
                color: 0xffcc88, emissive: 0xcc4410, emissiveIntensity: 0.35,
                roughness: 0.1, metalness: 0.05, depthWrite: false
            }))
        ripple.rotation.x = Math.PI / 2
        ripple.position.y = 3.5 - TRUNNION_Y
        ripples.push(ripple); vessel.add(ripple)
    }

    // ========== 渣层（炉渣浮于钢水表面） ==========
    const slagLayer = new THREE.Mesh(
        new THREE.CylinderGeometry(4.1, 4.4, 0.8, 24),
        mat(0x998877, {
            roughness: 0.3, metalness: 0.15, emissive: 0x332200, emissiveIntensity: 0.2,
            transparent: true, opacity: 0.55, depthWrite: false
        })
    )
    slagLayer.position.y = 3.9 - TRUNNION_Y; vessel.add(slagLayer)

    // ========== 霓虹装饰 ==========
    // 炉体中部霓虹环
    const convRing1 = new THREE.Mesh(new THREE.TorusGeometry(5.2, 0.12, 8, 32),
        mat(0x42566b, { roughness: 0.55, metalness: 0.35 }))
    convRing1.rotation.x = Math.PI / 2; convRing1.position.set(0, 3.0 - TRUNNION_Y, 0); vessel.add(convRing1)

    // 炉口霓虹环
    const convRing2 = new THREE.Mesh(new THREE.TorusGeometry(3.2, 0.12, 8, 32),
        mat(0x42566b, { roughness: 0.55, metalness: 0.35 }))
    convRing2.rotation.x = Math.PI / 2; convRing2.position.set(0, 11.0 - TRUNNION_Y, 0); vessel.add(convRing2)

    // ========== 动画钩子数据 ==========
    g.userData.topY = 26

    // 热度柱定位
    g.userData.heatCenterY = 3.0
    g.userData.heatInternalH = 15.0
    g.userData.heatInternalR = 4.5

    // 倾动动画属性（挂在 userData 上，供 scene.js 读取）
    g.userData._converterPivot = vessel
    g.userData._converterMelt = meltPool
    g.userData._converterMeltRipples = ripples

    // 氧枪火花
    g.userData._convSparks = sparkGroup.children.filter(c => c.material && c.material.color)
    // 底吹气泡
    g.userData._convBottomBubbs = bottomBubbs
    // 渣层
    g.userData._convSlagMat = slagLayer.material

    // === 物料转变动画：铁水(橙红)→吹氧脱碳→钢水(亮橙) ===
    // 颜色与连线载运体一致：hot_metal(0xb05030)→crude_steel(0xbf6a30)
    const convFlow = []
    for (let i = 0; i < 6; i++) {
        const ang = (i / 6) * Math.PI * 2; const r = 1.6 + Math.random() * 1.5
        const drop = new THREE.Mesh(new THREE.SphereGeometry(0.25 + Math.random() * 0.15, 6, 4),
            new THREE.MeshStandardMaterial({ roughness: 0.12, metalness: 0.08 }))
        drop.position.set(Math.cos(ang) * r, 3.5 + Math.random() * 5 - TRUNNION_Y, 0 + Math.sin(ang) * r); vessel.add(drop)
        convFlow.push({
            obj: drop, phase: i * 0.16, period: 5.5,
            srcPos: new THREE.Vector3(Math.cos(ang) * r, 6.0 - TRUNNION_Y, Math.sin(ang) * r),
            dstPos: new THREE.Vector3(Math.cos(ang) * r * 0.3, 2.0 - TRUNNION_Y, Math.sin(ang) * r * 0.3),
            srcColor: 0xb05030, dstColor: 0xbf6a30, scalePulse: 0.15,
        })
    }
    // 喷吹脱碳火花（从氧枪尖端到钢水表面）
    for (let i = 0; i < 4; i++) {
        const spark = new THREE.Mesh(new THREE.SphereGeometry(0.1, 4, 4),
            new THREE.MeshBasicMaterial({ color: 0xffe2b0, transparent: true, opacity: 0.5, depthWrite: false }))
        spark.position.set((Math.random() - 0.5) * 1.2, 7 + Math.random() * 3 - TRUNNION_Y, (Math.random() - 0.5) * 1.2)
        vessel.add(spark)
        convFlow.push({
            obj: spark, kind: 'spark', phase: i * 0.25, period: 1.8,
            srcPos: new THREE.Vector3(0, 8.5 - TRUNNION_Y, 0),
            dstPos: new THREE.Vector3((Math.random() - 0.5) * 2, 3.0 - TRUNNION_Y, (Math.random() - 0.5) * 2),
            srcColor: 0xffffdd, dstColor: 0xffcc44, scalePulse: 0.5,
        })
    }

    g.userData._matFlow = convFlow
    return g
}
