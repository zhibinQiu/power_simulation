import * as THREE from 'three'
import { PAL, mat, boxMesh, steelTex, tankShellTex, stackPanelTex, wallPanelTex } from './utils.js'

/** _buildBlastFurnace 极致仿真高炉3D模型
 *  炉内分层：焦炭层(黑灰)→铁矿石层(红褐)→软熔带(橙红半熔)→滴落区(焦炭骨架+铁水滴)→炉缸(铁水+炉渣分层)
 *  顶部排烟：uptake pipe + 上升管 + 荒煤气粉尘
 *  热风围管：bosh 高度环管 + 风口发光
 *  出铁口 + 出渣口
 */
export default function _buildBlastFurnace(bodyMat) {
    const g = new THREE.Group()
    const steel = mat(PAL.steel, { metalness: 0.5, roughness: 0.35 })
    const brickMat = mat(0x8a7060, { metalness: 0.05, roughness: 0.6 })
    // 无厂房框架，仅保留高炉本体与附属设备

    // 高炉主体按Y轴缩放到合适高度
    const BF_Y_SCALE = 0.7
    const mainGroup = new THREE.Group()
    mainGroup.name = 'blastFurnaceMain'

    // ========== 一、炉体钢结构外壳（半透明可透视内部） ==========
    // 炉缸区域（底部大直径圆柱）
    const hearthGeo = new THREE.CylinderGeometry(8.5, 9.0, 12, 32, 1, true)
    const hearthShell = new THREE.Mesh(hearthGeo, bodyMat)
    hearthShell.position.y = 6; hearthShell.name = 'hearthShell'; mainGroup.add(hearthShell)
    // 炉底封板
    const hearthBottom = new THREE.Mesh(new THREE.CylinderGeometry(9.0, 9.0, 0.8, 32), brickMat)
    hearthBottom.position.y = 0.4; mainGroup.add(hearthBottom)

    // 炉腹区域（上小下大锥台 — bosh）
    const boshGeo = new THREE.CylinderGeometry(6.5, 8.5, 14, 32, 1, true)
    const boshShell = new THREE.Mesh(boshGeo, bodyMat)
    boshShell.position.y = 18; boshShell.name = 'boshShell'; mainGroup.add(boshShell)

    // 炉身区域（上小下大锥台 — shaft）
    const shaftGeo = new THREE.CylinderGeometry(3.8, 6.5, 22, 32, 1, true)
    const shaftShell = new THREE.Mesh(shaftGeo, bodyMat)
    shaftShell.position.y = 35; shaftShell.name = 'shaftShell'; mainGroup.add(shaftShell)

    // 炉喉区域（圆柱 — throat）
    const throatGeo = new THREE.CylinderGeometry(3.2, 3.8, 10, 32, 1, true)
    const throatShell = new THREE.Mesh(throatGeo, bodyMat)
    throatShell.position.y = 50; throatShell.name = 'throatShell'; mainGroup.add(throatShell)

    // 炉顶封盖
    const topCap = new THREE.Mesh(new THREE.CylinderGeometry(3.5, 3.5, 0.6, 32), brickMat)
    topCap.position.y = 55.3; mainGroup.add(topCap)

    // ========== 二、炉体加强环/钢箍（视觉加强） ==========
    for (const y of [12, 24, 36, 44]) {
        const r = y === 12 ? 8.8 : y === 24 ? 6.8 : y === 36 ? 5.0 : 4.2
        const hoop = new THREE.Mesh(new THREE.TorusGeometry(r, 0.25, 8, 32), steel)
        hoop.rotation.x = Math.PI / 2; hoop.position.y = y; mainGroup.add(hoop)
    }
    // 炉喉钢箍
    const throatHoop = new THREE.Mesh(new THREE.TorusGeometry(3.5, 0.25, 8, 32), steel)
    throatHoop.rotation.x = Math.PI / 2; throatHoop.position.y = 52; mainGroup.add(throatHoop)

    // ========== 三、内部炉料分层可视化（通过半透明外壳可见） ==========
    // 3A. 炉喉：焦炭+铁矿石交替层（布钟装料 — 焦炭层/矿石层交替）
    const burdenLayerGroup = new THREE.Group()
    burdenLayerGroup.name = 'burdenLayers'
    const cokeColor = 0x3a3a3a    // 焦炭 — 深灰黑色
    const oreColor = 0x6a4030     // 铁矿石 — 红褐色
    const sinterColor = 0x5a7088  // 烧结矿 — 灰蓝
    const pelletColor = 0x4a6078  // 球团矿 — 灰蓝

    // 交替焦层/矿层（每层 ~2 单位高，5组交替，总高 ~45-54）
    let layerY = 46
    const layerPattern = [
        { color: cokeColor, h: 1.8, label: '焦炭层' },
        { color: oreColor, h: 1.5, label: '铁矿石层' },
        { color: sinterColor, h: 1.2, label: '烧结矿层' },
        { color: cokeColor, h: 1.8, label: '焦炭层' },
        { color: pelletColor, h: 1.3, label: '球团矿层' },
    ]
    for (let cycle = 0; cycle < 2; cycle++) {
        for (const l of layerPattern) {
            const r = 3.0 - (55 - layerY) * 0.06 // 越下越宽
            const layer = new THREE.Mesh(
                new THREE.CylinderGeometry(Math.max(2.5, r), Math.max(2.5, r), l.h, 24),
                mat(l.color, { roughness: 0.5, metalness: 0.08, emissive: l.color, emissiveIntensity: 0.08 })
            )
            layer.position.y = layerY
            layer.name = l.label
            burdenLayerGroup.add(layer)
            layerY -= l.h
        }
    }

    // 3B. 软熔带（黏结区）— 半熔融矿石 + 焦炭窗，温度1200-1400°C
    const cohesiveZone = new THREE.Mesh(
        new THREE.CylinderGeometry(5.0, 5.5, 10, 24),
        mat(0x8a4020, {
            roughness: 0.35, metalness: 0.1, emissive: 0x99280a, emissiveIntensity: 0.14,
            transparent: true, opacity: 0.8, depthWrite: false
        })
    )
    cohesiveZone.position.y = 30
    cohesiveZone.name = '软熔带'
    burdenLayerGroup.add(cohesiveZone)

    // 3C. 滴落区（焦炭骨架 + 铁水滴落）— 焦炭固体 + 流动铁水
    const drippingZone = new THREE.Mesh(
        new THREE.CylinderGeometry(7.0, 7.5, 10, 24),
        mat(0x4a3530, {
            roughness: 0.3, metalness: 0.15, emissive: 0x7a2c10, emissiveIntensity: 0.22,
            transparent: true, opacity: 0.7, depthWrite: false
        })
    )
    drippingZone.position.y = 20
    drippingZone.name = '滴落区'
    burdenLayerGroup.add(drippingZone)

    // 3D. 炉缸铁水 + 炉渣分层（hearth — 铁水在下，炉渣在上）
    const ironPool = new THREE.Mesh(
        new THREE.CylinderGeometry(7.5, 7.5, 4.5, 24),
        mat(0xc44e22, {
            roughness: 0.3, metalness: 0.7, emissive: 0x8f2e10, emissiveIntensity: 0.4,
            transparent: true, opacity: 0.85, depthWrite: false
        })
    )
    ironPool.position.y = 3.5
    ironPool.name = '铁水池'
    burdenLayerGroup.add(ironPool)

    const slagLayer = new THREE.Mesh(
        new THREE.CylinderGeometry(7.5, 7.5, 2.0, 24),
        mat(0x999988, {
            roughness: 0.3, metalness: 0.2, emissive: 0x332211, emissiveIntensity: 0.2,
            transparent: true, opacity: 0.6, depthWrite: false
        })
    )
    slagLayer.position.y = 6.5
    slagLayer.name = '炉渣层'
    burdenLayerGroup.add(slagLayer)

    mainGroup.add(burdenLayerGroup)

    // ========== 四、顶部装料设备 + 排烟系统 ==========
    // 旋转布料溜槽（chute）
    const chute = new THREE.Mesh(new THREE.BoxGeometry(0.6, 1.8, 0.6), steel)
    chute.position.set(0, 56.2, 0); mainGroup.add(chute)
    // 料钟（bell）
    const bell = new THREE.Mesh(new THREE.ConeGeometry(2.0, 1.8, 16), steel)
    bell.position.y = 55.8; mainGroup.add(bell)

    // 上升管（uptake pipe）— 4根，收集荒煤气
    const uptakeGroup = new THREE.Group()
    uptakeGroup.name = 'uptakePipes'
    for (let i = 0; i < 4; i++) {
        const ang = (i / 4) * Math.PI * 2
        const ur = 2.8
        const uptake = new THREE.Mesh(new THREE.CylinderGeometry(0.45, 0.55, 12, 12), steel)
        uptake.position.set(Math.cos(ang) * ur, 57, Math.sin(ang) * ur)
        uptakeGroup.add(uptake)
    }
    mainGroup.add(uptakeGroup)

    // 上升管顶部汇聚管 + 下降管
    const collectionDome = new THREE.Mesh(new THREE.SphereGeometry(2.5, 16, 12, 0, Math.PI * 2, 0, Math.PI * 0.4), steel)
    collectionDome.position.y = 63; mainGroup.add(collectionDome)
    const downComer = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.55, 10, 12), steel)
    downComer.position.set(3.5, 65, 0); mainGroup.add(downComer)

    // 除尘器（dust catcher）— 粗除尘
    const dustCatcher = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 2.8, 8, 16), brickMat)
    dustCatcher.position.set(6, 62, 0); mainGroup.add(dustCatcher)
    const dcCone = new THREE.Mesh(new THREE.ConeGeometry(2.8, 2.5, 16), steel)
    dcCone.rotation.y = Math.PI; dcCone.position.set(6, 57, 0); mainGroup.add(dcCone)

    // 排烟粒子系统（荒煤气/粉尘上升）— 从炉顶uptake管口冒出
    const smokeCount = 80
    const smokeGeo = new THREE.BufferGeometry()
    const smokePos = new Float32Array(smokeCount * 3)
    const smokeSeed = new Float32Array(smokeCount)
    for (let i = 0; i < smokeCount; i++) {
        const ang = Math.random() * Math.PI * 2
        const r = 2.5 + Math.random() * 1.5
        smokePos[i * 3] = Math.cos(ang) * r
        smokePos[i * 3 + 1] = 55 + Math.random() * 10
        smokePos[i * 3 + 2] = Math.sin(ang) * r
        smokeSeed[i] = Math.random()
    }
    smokeGeo.setAttribute('position', new THREE.BufferAttribute(smokePos, 3))
    smokeGeo.setAttribute('seed', new THREE.BufferAttribute(smokeSeed, 1))
    const smokeMat = new THREE.PointsMaterial({
        color: 0x888899, size: 1.5, transparent: true, opacity: 0.3,
        depthWrite: false, blending: THREE.NormalBlending
    })
    const smokePts = new THREE.Points(smokeGeo, smokeMat)
    smokePts.userData = { count: smokeCount, maxY: 80, isSmoke: true, speed: 6 }
    mainGroup.add(smokePts)
    // 注册到 userData 供 scene.js _stepParticles 驱动
    g.userData._bfSmoke = smokePts

    // ========== 五、热风围管 + 风口系统 ==========
    const tuyereRing = new THREE.Mesh(new THREE.TorusGeometry(6.8, 0.5, 8, 32), mat(0x886644, { metalness: 0.5, roughness: 0.35 }))
    tuyereRing.rotation.x = Math.PI / 2; tuyereRing.position.y = 14.5; mainGroup.add(tuyereRing)

    // 12个风口（tuyeres）— 高温鼓风入口
    const tuyereGroup = new THREE.Group()
    tuyereGroup.name = 'tuyeres'
    for (let i = 0; i < 12; i++) {
        const ang = (i / 12) * Math.PI * 2
        const tG = new THREE.Group()
        // 风口本体
        const tuyere = new THREE.Mesh(new THREE.CylinderGeometry(0.3, 0.4, 2.0, 8),
            mat(0xbb8844, { metalness: 0.6, roughness: 0.3 }))
        tuyere.rotation.z = Math.PI / 2
        tuyere.position.set(Math.cos(ang) * 6.6, 14.5, Math.sin(ang) * 6.6)
        tG.add(tuyere)
        // 风口前端火焰发光球
        const flare = new THREE.Mesh(
            new THREE.SphereGeometry(0.35, 8, 6),
            new THREE.MeshStandardMaterial({
                color: 0xc26530, emissive: 0xb54214, emissiveIntensity: 0.4,
                roughness: 0.25, metalness: 0.05, transparent: true, opacity: 0.75, depthWrite: false
            })
        )
        flare.position.set(Math.cos(ang) * 7.5, 14.5, Math.sin(ang) * 7.5)
        flare.name = 'tuyereFlare'
        tG.add(flare)
        tuyereGroup.add(tG)
    }
    mainGroup.add(tuyereGroup)

    // 热风主管（hot blast main）
    const blastPipe = new THREE.Mesh(new THREE.CylinderGeometry(1.0, 1.0, 12, 12),
        mat(0x885533, { metalness: 0.55, roughness: 0.3, emissive: 0x331100, emissiveIntensity: 0.3 }))
    blastPipe.rotation.z = Math.PI / 2
    blastPipe.position.set(0, 14.5, -8); mainGroup.add(blastPipe)

    // 热风炉（hot stoves）— 2座
    for (const s of [-1, 1]) {
        const stove = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 2.5, 26, 16),
            mat(0xa08870, { metalness: 0.1, roughness: 0.5 }))
        stove.position.set(s * 7, 13, -9)
        mainGroup.add(stove)
        // 热风炉拱顶
        const stoveDome = new THREE.Mesh(new THREE.SphereGeometry(2.5, 16, 12, 0, Math.PI * 2, 0, Math.PI * 0.35),
            mat(0xb09880, { metalness: 0.1, roughness: 0.5 }))
        stoveDome.position.set(s * 7, 26, -9)
        mainGroup.add(stoveDome)
    }

    // ========== 六、出铁口 + 出渣口 ==========
    // 出铁口（低标高）— 铁水流道
    const tapHoleIron = new THREE.Mesh(
        new THREE.CylinderGeometry(0.6, 0.8, 0.8, 12),
        mat(0x553322, { metalness: 0.4, roughness: 0.4, emissive: 0xcc4420, emissiveIntensity: 0.35 })
    )
    tapHoleIron.rotation.z = Math.PI / 2
    tapHoleIron.position.set(8.8, 1.8, 3); mainGroup.add(tapHoleIron)

    // 出铁沟流道
    const ironRunner = new THREE.Mesh(
        new THREE.BoxGeometry(0.6, 0.4, 4),
        mat(0x442211, { metalness: 0.3, roughness: 0.5, emissive: 0xbb3315, emissiveIntensity: 0.3 })
    )
    ironRunner.position.set(10.5, 1.2, 3); mainGroup.add(ironRunner)

    // 铁水流动体（出铁口外 — 液态铁水）
    const ironStream = new THREE.Mesh(
        new THREE.BoxGeometry(1.5, 0.3, 2.5),
        mat(0xcc4018, {
            roughness: 0.25, metalness: 0.7, emissive: 0x993210, emissiveIntensity: 0.6,
            transparent: true, opacity: 0.9, depthWrite: false
        })
    )
    ironStream.position.set(11.5, 0.7, 3); mainGroup.add(ironStream)
    ironStream.name = 'ironStream'

    // 出渣口（高标高 — 渣线上方）
    const tapHoleSlag = new THREE.Mesh(
        new THREE.CylinderGeometry(0.4, 0.5, 0.6, 12),
        mat(0x666655, { metalness: 0.2, roughness: 0.5, emissive: 0x221100, emissiveIntensity: 0.25 })
    )
    tapHoleSlag.rotation.z = -Math.PI / 2
    tapHoleSlag.position.set(-8.8, 5.5, -3); mainGroup.add(tapHoleSlag)

    // 渣沟流道
    const slagRunner = new THREE.Mesh(
        new THREE.BoxGeometry(0.5, 0.3, 3.5),
        mat(0x665544, { metalness: 0.2, roughness: 0.5, emissive: 0x111100, emissiveIntensity: 0.3 })
    )
    slagRunner.position.set(-10.5, 4.8, -3); mainGroup.add(slagRunner)

    // ========== 七、冷却壁管道（外部可见） ==========
    for (let i = 0; i < 8; i++) {
        const ang = (i / 8) * Math.PI * 2
        const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.12, 0.12, 20, 6),
            mat(0x557799, { roughness: 0.35, metalness: 0.55 }))
        pipe.position.set(Math.cos(ang) * 9.5, 28, Math.sin(ang) * 9.5)
        mainGroup.add(pipe)
    }

    // ========== 八、料车/上料系统 ==========
    // 斜桥
    const inclineBridge = new THREE.Mesh(new THREE.BoxGeometry(2, 0.8, 22), steel)
    inclineBridge.rotation.x = 0.85 * Math.PI / 2
    inclineBridge.position.set(-6, 38, 3); mainGroup.add(inclineBridge)

    // 料车轨道
    for (const s of [-0.5, 0.5]) {
        const rail = new THREE.Mesh(new THREE.CylinderGeometry(0.1, 0.1, 22, 6), steel)
        rail.rotation.x = 0.85 * Math.PI / 2; rail.rotation.z = Math.PI / 2
        rail.position.set(-6, 38, 3 + s * 1.8); mainGroup.add(rail)
    }

    // 料车（skip car）
    const skipCar = new THREE.Mesh(new THREE.BoxGeometry(2.5, 1.8, 2.5),
        mat(0x6a7a8a, { roughness: 0.4, metalness: 0.45 }))
    skipCar.position.set(-6, 38, 3)
    skipCar.name = 'skipCar'
    mainGroup.add(skipCar)

    // 料仓
    const oreBin = new THREE.Mesh(new THREE.CylinderGeometry(2.2, 2.8, 10, 16),
        mat(0x8899aa, { roughness: 0.35, metalness: 0.35 }))
    oreBin.position.set(-6, 49, 3); mainGroup.add(oreBin)

    // ========== 九、霓虹装饰 ==========
    // 炉缸霓虹环
    const bfRing1 = new THREE.Mesh(new THREE.TorusGeometry(9.2, 0.15, 8, 32),
        mat(0x42566b, { roughness: 0.55, metalness: 0.35 }))
    bfRing1.rotation.x = Math.PI / 2; bfRing1.position.set(0, 10, 0); mainGroup.add(bfRing1)

    // 炉身中部霓虹环
    const bfRing2 = new THREE.Mesh(new THREE.TorusGeometry(5.8, 0.12, 8, 32),
        mat(0x42566b, { roughness: 0.55, metalness: 0.35 }))
    bfRing2.rotation.x = Math.PI / 2; bfRing2.position.set(0, 35, 0); mainGroup.add(bfRing2)

    // ========== 十、动画钩子数据 ==========
    g.userData.topY = 68

    // 热度柱定位：整个炉体
    g.userData.heatCenterY = 30.0
    g.userData.heatInternalH = 55.0
    g.userData.heatInternalR = 7.5

    // 风口火焰材质列表（供脉动动画）
    g.userData._tuyereFlares = tuyereGroup.children
        .map(tg => tg.children.find(c => c.name === 'tuyereFlare'))
        .filter(Boolean)

    // 炉缸铁水材质（供脉动动画）
    g.userData._ironPoolMat = ironPool.material
    g.userData._slagLayerMat = slagLayer.material

    // 铁水流材质
    g.userData._ironStreamMat = ironStream.material
    g.userData._ironStreamMesh = ironStream

    // 料车上下运动钩子
    g.userData._skipCar = skipCar
    g.userData._skipBaseY = 38

    // 排烟粒子
    g.userData._bfSmoke = smokePts

    // 炉料整体下沉钩子
    g.userData._burdenLayers = burdenLayerGroup
    g.userData._burdenBaseY = 0

    // === 物料转变动画：烧结矿+球团+焦炭(多层)→高炉冶炼→铁水+炉渣 ===
    // 颜色与连线载运体一致：sinter(0x5a7088)→hot_metal(0xb05030)
    const bfFlow = []
    // 铁矿石/烧结矿 → 铁水 转变
    const hotMetalColor = 0xb05030
    const bfSinterColor = 0x5a7088

    // 炉料下降颗粒（从炉喉到炉缸）
    for (let i = 0; i < 10; i++) {
        const chunk = new THREE.Mesh(new THREE.IcosahedronGeometry(0.45 + Math.random() * 0.3, 0),
            new THREE.MeshStandardMaterial({ color: sinterColor, roughness: 0.65, metalness: 0.1 }))
        const sy = 46 + Math.random() * 12
        chunk.position.set((Math.random() - 0.5) * 5, sy, (Math.random() - 0.5) * 4)
        chunk.userData._matKind = 'burden'
        mainGroup.add(chunk)
        const dstY = i < 5 ? 15 + Math.random() * 10 : 30 + Math.random() * 12
        bfFlow.push({
            obj: chunk, kind: 'burden', phase: i * 0.1, period: 6.0,
            srcPos: new THREE.Vector3(chunk.position.x, 52, chunk.position.z),
            dstPos: new THREE.Vector3(chunk.position.x * 0.3, dstY, chunk.position.z * 0.3),
            srcColor: sinterColor, dstColor: i < 5 ? hotMetalColor : 0xff8833,
            scalePulse: 0.2,
        })
    }

    // 炉缸铁水涌动球（表示液态铁水/渣沸腾）
    const ironDrops = [[3, 2.5, 5], [3, 3.5, 7], [-3, 2.0, 4], [-4, 3.0, 6]]
    ironDrops.forEach(([ix, iy, iz], di) => {
        const drop = new THREE.Mesh(new THREE.SphereGeometry(0.4, 8, 6),
            new THREE.MeshStandardMaterial({ color: hotMetalColor, roughness: 0.1, metalness: 0.1, emissive: 0xff2200 }))
        drop.position.set(ix, iy, iz); mainGroup.add(drop)
        bfFlow.push({
            obj: drop, kind: 'iron', phase: di * 0.25, period: 3.5,
            srcPos: new THREE.Vector3(ix, iy, iz), dstPos: new THREE.Vector3(ix + 2, iy + 0.5, iz + 1),
            srcColor: hotMetalColor, dstColor: 0xb55a34, scalePulse: 0.15,
        })
    })

    // 渣层涌动球
    const slagDrops = [[2, 6.5, 5], [-2, 7.0, 4]]
    slagDrops.forEach(([sx, sy, sz], si) => {
        const sDrop = new THREE.Mesh(new THREE.SphereGeometry(0.35, 8, 6),
            new THREE.MeshStandardMaterial({ color: 0x888877, roughness: 0.3, metalness: 0.15, emissive: 0x222200 }))
        sDrop.position.set(sx, sy, sz); mainGroup.add(sDrop)
        bfFlow.push({
            obj: sDrop, kind: 'slag', phase: si * 0.4, period: 4.5,
            srcPos: new THREE.Vector3(sx, sy, sz),
            dstPos: new THREE.Vector3(sx - 2, sy + 0.3, sz - 2),
            srcColor: 0x888877, dstColor: 0x666655, scalePulse: 0.12,
        })
    })

    // 排烟上升颗粒
    for (let i = 0; i < 5; i++) {
        const smokeBall = new THREE.Mesh(new THREE.SphereGeometry(0.2 + Math.random() * 0.2, 4, 4),
            new THREE.MeshBasicMaterial({ color: 0x666666, transparent: true, opacity: 0.2, depthWrite: false }))
        smokeBall.position.set((Math.random() - 0.5) * 4, 50 + Math.random() * 5, (Math.random() - 0.5) * 4)
        mainGroup.add(smokeBall)
        bfFlow.push({
            obj: smokeBall, kind: 'smoke', phase: i * 0.2, period: 5.0,
            srcPos: new THREE.Vector3(smokeBall.position.x, 50, smokeBall.position.z),
            dstPos: new THREE.Vector3(smokeBall.position.x + (Math.random() - 0.5) * 6, 75, smokeBall.position.z + (Math.random() - 0.5) * 6),
            srcColor: 0x444444, dstColor: 0x777777, scalePulse: 0.5,
        })
    }

    // 将高炉主体加入 scene 组，并 Y 轴缩放到合适高度
    mainGroup.scale.set(1, BF_Y_SCALE, 1)
    g.add(mainGroup)

    // 同步调整 userData 中的高度值，确保热度柱、标签等与视觉缩放一致
    g.userData.topY *= BF_Y_SCALE
    g.userData.heatCenterY *= BF_Y_SCALE
    g.userData.heatInternalH *= BF_Y_SCALE
    g.userData._skipBaseY *= BF_Y_SCALE

    g.userData._matFlow = bfFlow
    return g
}
