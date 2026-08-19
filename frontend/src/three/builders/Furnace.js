import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex, tankShellTex, wallPanelTex } from './utils.js'

/** _buildFurnace 极致仿真电弧炉(EAF)3D模型
 *  三相电极电弧加热废钢
 *  熔池钢水 + 渣层浮于表面
 *  炉体倾动出钢
 *  炉顶旋开加料
 */
export default function _buildFurnace(bodyMat) {
    const g = new THREE.Group()
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })
    const neonColor = 0x00ccff


    // === 1. 炉体 ===
    // 炉壳（下部球形炉底 + 上部圆柱炉壁）
    const shellLower = new THREE.Mesh(new THREE.CylinderGeometry(4.5, 5.5, 5.5, 24), bodyMat)
    shellLower.position.y = 2.0; g.add(shellLower)
    const shellUpper = new THREE.Mesh(new THREE.CylinderGeometry(4.5, 4.5, 3.5, 24, 1, true), bodyMat)
    shellUpper.position.y = 6.5; g.add(shellUpper)
    // 炉底耐火材料内衬
    const bottomLining = new THREE.Mesh(new THREE.SphereGeometry(5.5, 24, 16, 0, Math.PI * 2, 0, Math.PI * 0.5),
        mat(0xb0a090, { roughness: 0.5, metalness: 0.05 }))
    bottomLining.position.y = 2.0; g.add(bottomLining)
    // 炉顶（旋转水冷炉盖）
    const roof = new THREE.Mesh(new THREE.CylinderGeometry(4.5, 4.8, 1.2, 24),
        mat(0x778899, { roughness: 0.35, metalness: 0.5, transparent: true, opacity: 0.7, depthWrite: false }))
    roof.position.y = 9.0; g.add(roof)
    // 水冷壁面板
    const roofPanel = new THREE.Mesh(
        new THREE.CylinderGeometry(4.7, 4.7, 1.5, 24, 1, true),
        mat(0x667788, { roughness: 0.4, metalness: 0.5, transparent: true, opacity: 0.5, depthWrite: false }))
    roofPanel.position.y = 9.0; g.add(roofPanel)

    // === 2. 三相电极系统 ===
    // 电极柱（三根石墨电极，三角形排列）
    const electrodeGroup = new THREE.Group()
    electrodeGroup.name = 'electrodes'
    const elecAngles = [0, Math.PI * 2 / 3, Math.PI * 4 / 3]
    const arcFlares = []
    const eafElectrodes = []
    elecAngles.forEach((ang, ei) => {
        const er = 1.6
        const ex = Math.cos(ang) * er
        const ez = Math.sin(ang) * er

        // 单根电极升降组（scene.js 电极升降动画驱动其 position.y）
        const elGroup = new THREE.Group()
        elGroup.position.set(ex, 0, ez)
        electrodeGroup.add(elGroup)

        // 电极柱
        const electrode = new THREE.Mesh(new THREE.CylinderGeometry(0.35, 0.35, 6.0, 8),
            mat(0x333333, { roughness: 0.3, metalness: 0.15, emissive: 0x111111, emissiveIntensity: 0.2 }))
        electrode.position.y = 11
        electrode.name = 'electrode'
        elGroup.add(electrode)

        // 电极夹持器
        const holder = new THREE.Mesh(new THREE.BoxGeometry(0.8, 0.5, 0.8), steel)
        holder.position.y = 12
        elGroup.add(holder)

        // 电弧火焰（电极尖端 — 高温等离子弧）
        const arc = new THREE.Mesh(new THREE.SphereGeometry(0.4, 8, 6),
            new THREE.MeshStandardMaterial({
                color: 0xffffcc, emissive: 0xffffff, emissiveIntensity: 3.0,
                roughness: 0.05, metalness: 0.05, transparent: true,
                opacity: 0.8, depthWrite: false
            }))
        arc.position.set(0, 5.0, 0)
        arc.name = 'arcFlare'
        arcFlares.push(arc)
        elGroup.add(arc)

        // 电极动画钩子：group 升降 + tip 弧光 + clamp 夹持器微震
        eafElectrodes.push({ group: elGroup, tip: arc, clamp: holder, baseUY: 0 })
    })
    g.add(electrodeGroup)

    // 电极横臂支撑结构
    const armSupport = new THREE.Mesh(new THREE.BoxGeometry(4, 0.4, 4), steel)
    armSupport.position.y = 13; g.add(armSupport)

    // === 3. 炉内熔池（液态钢水） ===
    const meltPool = new THREE.Mesh(
        new THREE.CylinderGeometry(3.5, 4.2, 2.5, 24),
        mat(0xff8822, {
            roughness: 0.05, metalness: 0.05, emissive: 0xcc3300, emissiveIntensity: 0.8,
            transparent: true, opacity: 0.75, depthWrite: false
        })
    )
    meltPool.position.y = 2.0; g.add(meltPool)

    // 渣层（炉渣浮于钢水表面 — 泡沫渣）
    const slagLayer = new THREE.Mesh(
        new THREE.CylinderGeometry(4.0, 4.3, 1.0, 24),
        mat(0x998877, {
            roughness: 0.3, metalness: 0.15, emissive: 0x332200, emissiveIntensity: 0.25,
            transparent: true, opacity: 0.55, depthWrite: false
        })
    )
    slagLayer.position.y = 3.8; g.add(slagLayer)

    // 渣层气泡（泡沫渣中的气孔）
    for (let i = 0; i < 8; i++) {
        const foamBub = new THREE.Mesh(new THREE.SphereGeometry(0.2 + Math.random() * 0.25, 4, 4),
            new THREE.MeshBasicMaterial({
                color: 0xccaa66, transparent: true, opacity: 0.3, depthWrite: false
            }))
        foamBub.position.set((Math.random() - 0.5) * 7, 3.8 + Math.random() * 1.0, (Math.random() - 0.5) * 7)
        g.add(foamBub)
    }

    // === 4. 出钢槽 (tap spout) ===
    const tapSpout = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.6, 0.4, 8),
        mat(0x665544, { roughness: 0.4, metalness: 0.3, emissive: 0x331100, emissiveIntensity: 0.3 }))
    tapSpout.rotation.x = Math.PI / 2
    tapSpout.position.set(3.0, 1.5, 5.2); g.add(tapSpout)

    // 出钢槽流道
    const tapRunner = new THREE.Mesh(new THREE.BoxGeometry(0.5, 0.3, 2.0),
        mat(0x554433, { roughness: 0.4, metalness: 0.3, emissive: 0x331100, emissiveIntensity: 0.3 }))
    tapRunner.position.set(3.0, 1.2, 6.5); g.add(tapRunner)

    // === 5. 除尘烟道 ===
    // 炉顶直接排烟（第4孔）
    const fumeDuct = new THREE.Mesh(new THREE.CylinderGeometry(1.2, 1.3, 4, 12),
        mat(0x667788, { roughness: 0.35, metalness: 0.5 }))
    fumeDuct.position.set(2.5, 14, 0); fumeDuct.rotation.z = -0.7; g.add(fumeDuct)
    // 屋顶罩
    const canopyHood = new THREE.Mesh(
        new THREE.CylinderGeometry(3.5, 4.5, 2.5, 24, 1, true),
        mat(0x778899, { roughness: 0.4, metalness: 0.45, transparent: true, opacity: 0.5, depthWrite: false }))
    canopyHood.position.y = 17; g.add(canopyHood)

    // === 6. 钢包车区域 ===
    const ladleCar = new THREE.Mesh(new THREE.BoxGeometry(2, 1, 2), steel)
    ladleCar.position.set(3.5, 0.5, 7.5); g.add(ladleCar)

    // === 7. 霓虹装饰 ===
    const eafRing = new THREE.Mesh(new THREE.TorusGeometry(5.7, 0.15, 8, 32),
        new THREE.MeshStandardMaterial({ color: neonColor, emissive: neonColor, emissiveIntensity: 0.5, roughness: 0.2 }))
    eafRing.rotation.x = Math.PI / 2; eafRing.position.set(0, 4.5, 0); g.add(eafRing)

    const eafRing2 = new THREE.Mesh(new THREE.TorusGeometry(4.8, 0.12, 8, 32),
        new THREE.MeshStandardMaterial({ color: neonColor, emissive: neonColor, emissiveIntensity: 0.4, roughness: 0.2 }))
    eafRing2.rotation.x = Math.PI / 2; eafRing2.position.set(0, 8.0, 0); g.add(eafRing2)

    // === 7.5 检修平台（2层） ===
    const pfMat = mat(0x445566, { roughness: 0.45, metalness: 0.35, transparent: true, opacity: 0.5 })
    const platformLevels = [{ y: 3.5, w: 12, d: 9 }, { y: 9.5, w: 10, d: 8 }]
    for (const pl of platformLevels) {
        const pf = new THREE.Mesh(new THREE.BoxGeometry(pl.w, 0.18, pl.d), pfMat)
        pf.position.set(0, pl.y, 0); pf.receiveShadow = true; g.add(pf)
        for (const sx of [-1, 1]) {
            for (const sz of [-1, 1]) {
                const post = new THREE.Mesh(new THREE.CylinderGeometry(0.06, 0.06, 0.9, 6), steel)
                post.position.set(sx * pl.w * 0.42, pl.y + 0.55, sz * pl.d * 0.4)
                g.add(post)
            }
        }
    }

    // === 8. 动画钩子 ===
    g.userData.topY = 20
    g.userData.heatCenterY = 3.0
    g.userData.heatInternalH = 10.0
    g.userData.heatInternalR = 5.0

    g.userData._eafArcs = arcFlares
    g.userData._eafPoolMat = meltPool.material
    g.userData._eafSlagMat = slagLayer.material

    // === 物料转变动画：废钢(灰块)→电弧熔化→液态钢水(橙红) ===
    // 颜色与连线载运体一致：scrap(0x8899aa)→crude_steel(0xff8822)
    const eafFlow = []
    for (let i = 0; i < 8; i++) {
        const ang = (i / 8) * Math.PI * 2; const r = 1.8 + Math.random() * 2.0
        const scrap = new THREE.Mesh(new THREE.IcosahedronGeometry(0.3 + Math.random() * 0.3, 0),
            new THREE.MeshStandardMaterial({ roughness: 0.3, metalness: 0.3 }))
        scrap.position.set(Math.cos(ang) * r, 3.5 + Math.random() * 3, Math.sin(ang) * r); g.add(scrap)
        eafFlow.push({
            obj: scrap, phase: i * 0.12, period: 7.5,
            srcPos: new THREE.Vector3(Math.cos(ang) * r, 6.0, Math.sin(ang) * r),
            dstPos: new THREE.Vector3(Math.cos(ang) * r * 0.2, 2.0, Math.sin(ang) * r * 0.2),
            srcColor: 0x8899aa, dstColor: 0xff8822, scalePulse: 0.18,
        })
    }
    // 渣层分离颗粒
    for (let i = 0; i < 3; i++) {
        const slagP = new THREE.Mesh(new THREE.DodecahedronGeometry(0.25, 0),
            new THREE.MeshStandardMaterial({ roughness: 0.4, metalness: 0.2 }))
        slagP.position.set((Math.random() - 0.5) * 5, 4.5, (Math.random() - 0.5) * 5)
        g.add(slagP)
        eafFlow.push({
            obj: slagP, kind: 'slag', phase: i * 0.25, period: 5.0,
            srcPos: new THREE.Vector3(slagP.position.x, 2.5, slagP.position.z),
            dstPos: new THREE.Vector3(slagP.position.x, 4.8, slagP.position.z),
            srcColor: 0xff7733, dstColor: 0x998877, scalePulse: 0.2,
        })
    }

    g.userData._matFlow = eafFlow
    g.userData._furnaceElectrodes = eafElectrodes
    return g
}
