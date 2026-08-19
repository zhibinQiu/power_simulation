import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex, tankShellTex } from './utils.js'

/** _buildCokeOven 极致仿真焦炉3D模型
 *  顶装煤 → 炭化室高温干馏 → 推焦机推出红热焦炭
 *  炉门可见火焰
 *  化产回收管道（荒煤气 → 化产品）
 *  熄焦塔/干熄焦
 */
export default function _buildCokeOven(bodyMat) {
    const g = new THREE.Group()
    const L = 28; const D = 14; const H = 12
    const steel = mat(PAL.steel, { metalness: 0.55, roughness: 0.35 })
    const neonColor = 0x00ccff


    // === 1. 焦炉本体（多孔炭化室 + 燃烧室交替） ===
    const ovenBody = new THREE.Mesh(new THREE.BoxGeometry(L * 0.7, 5.5, D * 0.8), bodyMat)
    ovenBody.position.y = 4.0; g.add(ovenBody)
    // 炉顶
    const ovenTop = new THREE.Mesh(new THREE.BoxGeometry(L * 0.72, 1.0, D * 0.82), bodyMat)
    ovenTop.position.y = 7.2; g.add(ovenTop)

    // 炭化室分隔（垂直条纹）
    for (let i = 0; i < 7; i++) {
        const px = -L * 0.33 + i * (L * 0.66 / 6)
        const div = new THREE.Mesh(new THREE.BoxGeometry(0.15, 5.5, D * 0.8),
            mat(0x9a8070, { roughness: 0.5, metalness: 0.1 }))
        div.position.set(px, 4.0, 0); g.add(div)
    }

    // === 2. 炭化室炉门（一排炉门 + 炉门火焰 — 焦炉最醒目标志） ===
    const doorFlares = []
    const CHAMBER_N = 8
    for (let i = 0; i < CHAMBER_N; i++) {
        const doorX = -L * 0.31 + i * (L * 0.62 / (CHAMBER_N - 1))
        // 炉门（深色门框，正面朝向 z 两侧）
        for (const s of [-1, 1]) {
            const doorFrame = new THREE.Mesh(new THREE.BoxGeometry(2.0, 4.2, 0.3),
                mat(0x554433, { roughness: 0.4, metalness: 0.45 }))
            doorFrame.position.set(doorX, 3.8, s * D * 0.42); g.add(doorFrame)
        }
        // 炉门内可见火焰（橙黄，每孔门上端渗火）
        const doorFlare = new THREE.Mesh(new THREE.BoxGeometry(1.4, 1.6, 0.15),
            new THREE.MeshStandardMaterial({
                color: 0xff8844, emissive: 0xff4400, emissiveIntensity: 1.5,
                transparent: true, opacity: 0.6, depthWrite: false
            }))
        doorFlare.position.set(doorX, 3.0, D * 0.44); g.add(doorFlare)
        doorFlares.push(doorFlare)
    }

    // === 3. 顶装煤系统 ===
    // 装煤车轨道
    const coalTrack = new THREE.Mesh(new THREE.BoxGeometry(L * 0.75, 0.1, 0.2), steel)
    coalTrack.position.set(0, 8.0, -D * 0.42); g.add(coalTrack)
    const coalTrack2 = new THREE.Mesh(new THREE.BoxGeometry(L * 0.75, 0.1, 0.2), steel)
    coalTrack2.position.set(0, 8.0, D * 0.42); g.add(coalTrack2)

    // 装煤车（charging car）
    const coalCar = new THREE.Mesh(new THREE.BoxGeometry(3, 1.5, D * 0.85),
        mat(0x778899, { roughness: 0.4, metalness: 0.45 }))
    coalCar.position.set(0, 9.2, 0); g.add(coalCar)
    coalCar.name = 'coalCar'

    // 煤仓（coal bunker）
    const coalBunker = new THREE.Mesh(new THREE.CylinderGeometry(2.5, 3.0, 6, 16), steel)
    coalBunker.position.set(0, 14, 0); g.add(coalBunker)

    // === 4. 推焦机（pusher machine） ===
    const pusher = new THREE.Mesh(new THREE.BoxGeometry(2.5, 3, D * 0.5), steel)
    pusher.position.set(-L * 0.36 - 2, 3, 0); g.add(pusher)
    // 推焦杆
    const pusherRod = new THREE.Mesh(new THREE.CylinderGeometry(0.4, 0.4, 8, 8), steel)
    pusherRod.rotation.z = Math.PI / 2
    pusherRod.position.set(-L * 0.36 + 3, 3.0, 0); g.add(pusherRod)

    // 红焦推出（在推焦侧出口）— 炽热焦炭块
    const pushedCoke = []
    for (let i = 0; i < 5; i++) {
        const coke = new THREE.Mesh(new THREE.BoxGeometry(1.0 + Math.random() * 0.4, 0.6 + Math.random() * 0.3, 0.8 + Math.random() * 0.4),
            new THREE.MeshStandardMaterial({
                roughness: 0.2, metalness: 0.2, emissive: 0xff4400, emissiveIntensity: 0.6
            }))
        coke.position.set(L * 0.36 + 2 + Math.random() * 3, 1.0 + Math.random(), (Math.random() - 0.5) * D * 0.5)
        g.add(coke)
        pushedCoke.push(coke)
    }

    // === 5. 拦焦车 + 熄焦车 ===
    // 拦焦车
    const guideCar = new THREE.Mesh(new THREE.BoxGeometry(2.5, 3, D * 0.5), steel)
    guideCar.position.set(L * 0.36 + 2, 3, 0); g.add(guideCar)
    // 熄焦车（quench car）
    const quenchCar = new THREE.Mesh(new THREE.BoxGeometry(4, 1.5, 3), steel)
    quenchCar.position.set(L * 0.36 + 5, 1.0, 0); g.add(quenchCar)

    // === 6. 化产回收管道系统 ===
    // 荒煤气上升管（从炭化室顶部引出）
    for (let i = 0; i < 6; i++) {
        const px = -L * 0.3 + i * (L * 0.6 / 5)
        const gasPipe = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.25, 3, 8), steel)
        gasPipe.position.set(px, 9.0, -D * 0.35); g.add(gasPipe)
    }
    // 集气管（collecting main）
    const collectMain = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, L * 0.65, 8), steel)
    collectMain.rotation.z = Math.PI / 2
    collectMain.position.set(0, 10.5, -D * 0.35); g.add(collectMain)
    // 初冷器（primary cooler）— 管壳式换热器
    const cooler = new THREE.Mesh(new THREE.CylinderGeometry(1.5, 1.8, 6, 12), steel)
    cooler.position.set(L * 0.4, 10.5, -D * 0.35); g.add(cooler)

    // === 7. 烟囱（off-gas stack） ===
    const stack = new THREE.Mesh(new THREE.CylinderGeometry(0.7, 1.0, 18, 12),
        mat(0xcca080, { roughness: 0.5, metalness: 0.1 }))
    stack.position.set(L * 0.42, 9, -D * 0.35); g.add(stack)

    // === 8. 霓虹装饰 ===
    const cokeRing1 = new THREE.Mesh(new THREE.TorusGeometry(L * 0.4, 0.12, 8, 32),
        new THREE.MeshStandardMaterial({ color: neonColor, emissive: neonColor, emissiveIntensity: 0.4, roughness: 0.2 }))
    cokeRing1.rotation.x = Math.PI / 2; cokeRing1.position.set(0, 1.2, 0); g.add(cokeRing1)

    // === 9. 动画钩子 ===
    g.userData.topY = 22
    g.userData.heatCenterY = 4.0
    g.userData.heatInternalH = 8.0
    g.userData.heatInternalR = D * 0.4

    g.userData._cokeGlowMats = pushedCoke.map(c => c.material)
    g.userData._cokeDoorFlares = doorFlares

    // === 物料转变动画：煤→干馏→焦炭(红热→灰黑冷却) ===
    // 颜色与连线载运体一致：coke(0x5a5a5a)
    const cokeFlow = []
    for (let i = 0; i < 6; i++) {
        const coke = new THREE.Mesh(new THREE.BoxGeometry(0.7 + Math.random() * 0.3, 0.5 + Math.random() * 0.2, 0.6 + Math.random() * 0.3),
            new THREE.MeshStandardMaterial({ roughness: 0.3, metalness: 0.15 }))
        coke.position.set(L * 0.36, 1.8 + Math.random(), (Math.random() - 0.5) * D * 0.4); g.add(coke)
        cokeFlow.push({
            obj: coke, phase: i * 0.16, period: 5.5,
            srcPos: new THREE.Vector3(L * 0.32, 4.0, 0),
            dstPos: new THREE.Vector3(L * 0.42, 1.0, -D * 0.35),
            srcColor: 0xff4411, dstColor: 0x5a5a5a, scalePulse: 0.1,
        })
    }

    g.userData._matFlow = cokeFlow
    return g
}
