<template>
  <!-- ============ 能碳一体机管理视图（云端 K3s/KubeEdge 管理、设备 CRUD、盒子接入） ============ -->
  <div class="cbx-view">
    <!-- ============ VSCode 风格工作台 ============ -->
    <!-- 视图名标识栏（标题 + 云端状态）已上移到 App.vue 的 Ribbon 工具栏之上（与 TopBar 风格统一），此处仅承载工作区主体 -->
    <div class="cbx-workbench">
      <!-- 侧边栏：资源树 -->
      <aside class="cbx-sidebar">
        <div class="cbx-side-head">
          <b>{{ sideTitle }}</b>
          <span class="cbx-side-count">{{ sideCount }}</span>
        </div>
        <div class="cbx-side-body">
          <!-- 资源树：盒子节点 + 模型 + 设备（设备配置已并入通信拓扑图，无单独 tab） -->
          <div class="cbx-tree">
            <div class="cbx-tree-sec" @click="expanded.boxes = !expanded.boxes">
              <span class="cbx-tree-arrow">{{ expanded.boxes ? '▾' : '▸' }}</span> 盒子节点
              <span class="cbx-tree-count">{{ topoBoxes.length }}</span>
            </div>
            <div v-show="expanded.boxes" class="cbx-tree-children">
              <div v-for="b in topoBoxes" :key="b.name" class="cbx-tree-node">
                <div class="cbx-tree-row" @click="expanded['box-' + b.name] = !expanded['box-' + b.name]">
                  <span class="cbx-tree-arrow">{{ expanded['box-' + b.name] ? '▾' : '▸' }}</span>
                  <span class="cbx-dot" :class="{ on: readyOk(b.ready) }"></span>
                  <span class="cbx-tree-label">{{ b.name }}</span>
                  <span class="cbx-tree-tag" :class="{ ok: readyOk(b.ready), err: b.ready === false }">{{ readyZh(b.ready) }}</span>
                </div>
                <div v-show="expanded['box-' + b.name]" class="cbx-tree-children">
                  <div v-for="d in boxDevices(b)" :key="d.name" class="cbx-tree-leaf" @click="onDevClick(d)" :title="(d._cloud ? '云端设备（点击查看实时）' : '待下发设备（点击编辑配置）') + '：' + d.name + (modelOf(d) ? '（模型 ' + modelOf(d) + '）' : '')">
                    <span class="cbx-dot" :class="{ on: d.state === 'online' }"></span><span class="cbx-tree-label">{{ d.name }}</span><span class="cbx-tree-tag" v-if="modelOf(d)">{{ modelOf(d) }}</span>
                  </div>
                  <div v-if="!boxDevices(b).length" class="cbx-tree-empty">暂无设备</div>
                </div>
              </div>
              <div v-if="topoUnmounted.length" class="cbx-tree-node">
                <div class="cbx-tree-row" @click="expanded.unmounted = !expanded.unmounted">
                  <span class="cbx-tree-arrow">{{ expanded.unmounted ? '▾' : '▸' }}</span>
                  <span class="cbx-tree-label">未挂载</span><span class="cbx-tree-count">{{ topoUnmounted.length }}</span>
                </div>
                <div v-show="expanded.unmounted" class="cbx-tree-children">
                  <div v-for="d in topoUnmounted" :key="d.name" class="cbx-tree-leaf" @click="openDevRealtime(d)">{{ d.name }}</div>
                </div>
              </div>
            </div>
            <div class="cbx-tree-sec" @click="expanded.models = !expanded.models">
              <span class="cbx-tree-arrow">{{ expanded.models ? '▾' : '▸' }}</span> 模型
              <span class="cbx-tree-count">{{ mergedModels.length }}</span>
            </div>
            <div v-show="expanded.models" class="cbx-tree-children">
              <div v-for="m in mergedModels" :key="m.name" class="cbx-tree-leaf" @click="openEditModel(m)" :title="'模型（点击修改点位）：' + m.name">▦ {{ m.name }}<span class="cbx-tree-tag" v-if="modelPropCount(m)">{{ modelPropCount(m) }} 属性</span></div>
              <div v-if="!mergedModels.length" class="cbx-tree-empty">暂无模型</div>
            </div>
            <div class="cbx-tree-sec" @click="expanded.devs = !expanded.devs">
              <span class="cbx-tree-arrow">{{ expanded.devs ? '▾' : '▸' }}</span> 设备
              <span class="cbx-tree-count">{{ mergedDevices.length }}</span>
            </div>
            <div v-show="expanded.devs" class="cbx-tree-children">
              <div v-for="d in mergedDevices" :key="d.name" class="cbx-tree-leaf" @click="onDevClick(d)" :title="(d._cloud ? '云端设备（点击查看实时）' : '待下发设备（点击编辑配置）') + '：' + d.name + (modelOf(d) ? '（模型 ' + modelOf(d) + '）' : '')">
                <span class="cbx-dot" :class="{ on: d.state === 'online' }"></span>{{ d.name }}<span class="cbx-tree-tag" v-if="modelOf(d)">{{ modelOf(d) }}</span>
              </div>
              <div v-if="!mergedDevices.length" class="cbx-tree-empty">暂无设备</div>
            </div>
          </div>
        </div>
      </aside>
      <!-- 主编辑区（单页：通信拓扑图 + 各功能区，无 tab） -->
      <main class="cbx-main">
        <div class="cbx-editor">
          <!-- ===== 概览页 ===== -->
          <section class="cbx-page">
        <!-- 云端状态全局提示（集中展示，避免下方各区块重复出现“云端不可达”tag） -->
        <div class="cbx-banner" :class="overview.cloud_source === 'degraded' ? 'warn' : 'err'"
             v-if="overview.cloud_source && overview.cloud_source !== 'live'">
          <template v-if="overview.cloud_source === 'stale'">⚠ 云端推送已中断：当前节点/CloudCore 状态为过期缓存，非实时数据。{{ overview.cloud_error }}</template>
          <template v-else-if="overview.cloud_source === 'degraded'">⚠ 云端部分服务异常：以下云端数据可能为缓存或不完整。</template>
          <template v-else>⚠ 云端不可达：以下云端数据不可用。请检查云端服务（cloud-agent / CloudHub 10002 / MQTT 41883）。</template>
          <template v-if="overview.demo_note">{{ overview.demo_note }}</template>
        </div>
        <!-- ① 通信拓扑图：平台 → 云端 → 边端 → 设备端（连线标注实际协议） -->
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>通信拓扑图</b>
            <span class="cbx-sec-hint">拖动模块可自定义布局，连线自动跟随</span>
            <span class="cbx-sec-spacer"></span>
            <button class="cbx-op cbx-xs" @click="autoLayoutTopo()" title="恢复四列自动布局，清除所有模块的手动拖拽位置">自动布局</button>
          </div>
          <div ref="topoCanvasRef" class="cbx-topo cbx-topo-canvas">
            <div class="cbx-topo-lanes">
              <!-- 平台列 -->
              <div class="cbx-topo-lane">
                <div class="cbx-topo-lane-title">平台</div>
                <div :ref="setNodeRef('n_platform')" class="cbx-topo-mod platform">
                  <div class="cbx-topo-mod-head">
                    <span class="cbx-topo-mod-name">工业能碳智控平台</span>
                    <span class="cbx-topo-mod-badge ok">运行中</span>
                  </div>
                  <div class="cbx-topo-mod-sub">Web 前端 ⇄ FastAPI :8010<br/>平台服务</div>
                  <div class="cbx-topo-mod-ops">
                    <button class="cbx-op cbx-xs" @click="refreshAll()" title="刷新全部数据">⟳ 刷新</button>
                  </div>
                </div>
              </div>
              <!-- 云端列 -->
              <div class="cbx-topo-lane">
                <div class="cbx-topo-lane-title">云端<span class="cbx-sec-spacer"></span><button class="cbx-op cbx-xs" @click="openBoxConfig" title="配置云端 Broker 地址/账号与 agent Token/端口，保存后自动热更新重连">云端配置</button></div>
                <div :ref="setNodeRef('n_agent')" class="cbx-topo-mod agent" :class="{ down: !agentStatusOk }">
                  <div class="cbx-topo-mod-head">
                    <span class="cbx-topo-mod-name">cloud-agent</span>
                    <span class="cbx-topo-mod-badge" :class="{ ok: agentStatusOk }">{{ agentStatusOk ? '在线' : '离线' }}</span>
                  </div>
                  <div class="cbx-topo-mod-sub">HTTP :42083 · Bearer<br/>{{ agentStatusOk ? '已连通' : '未连通（需配置 Token）' }}</div>
                  <div class="cbx-topo-mod-ops">
                    <button class="cbx-op cbx-xs" :disabled="!!restartingKey" @click="restartAgent()" title="重启云端 cloud-agent systemd 服务（2 秒后自动拉起）">{{ restartingKey === 'systemd:cloud-agent' ? '重启中…' : '↻ 重启' }}</button>
                  </div>
                </div>
                <div :ref="setNodeRef('n_cloudcore')" class="cbx-topo-mod cloudcore" :class="{ down: overview.cloud_source !== 'live' || (overview.cloudcore && overview.cloudcore.phase !== 'Running') }">
                  <div class="cbx-topo-mod-head">
                    <span class="cbx-topo-mod-name">CloudCore</span>
                    <span class="cbx-topo-mod-badge" :class="{ ok: overview.cloudcore && overview.cloudcore.phase === 'Running' }">{{ overview.cloudcore ? phaseZh(overview.cloudcore.phase) : '—' }}</span>
                  </div>
                  <div class="cbx-topo-mod-sub">CloudHub :10002 · KubeEdge CRD<br/>{{ cloudCfg.host || '172.19.134.45' }}</div>
                  <div class="cbx-topo-mod-ops">
                    <button class="cbx-op cbx-xs" :disabled="!!restartingKey" @click="restartCloudcore()" title="重启云端 kubeedge 命名空间下的 cloudcore 工作负载">{{ restartingKey === 'deployment:cloudcore' ? '重启中…' : '↻ 重启' }}</button>
                  </div>
                </div>
                <div :ref="setNodeRef('n_broker')" class="cbx-topo-mod broker">
                  <div class="cbx-topo-mod-head">
                    <span class="cbx-topo-mod-name">MQTT Broker</span>
                    <span class="cbx-topo-mod-badge ok">运行中</span>
                  </div>
                  <div class="cbx-topo-mod-sub">TCP :41883 · WS :41083<br/>订阅 {{ fmtNum(stats.subscriptions) }} · 运行 {{ fmtUptime(stats.uptime) }}</div>
                  <div class="cbx-topo-mod-ops">
                    <button class="cbx-op cbx-xs" :disabled="!!restartingKey" @click="restartBroker()" title="重启云端 MQTT Broker（nengtan-cloud-broker systemd 服务，短暂断连后自动重连）">{{ restartingKey === 'systemd:nengtan-cloud-broker' ? '重启中…' : '↻ 重启' }}</button>
                  </div>
                </div>
              </div>
              <!-- 边端列（EdgeCore 盒子） -->
              <div class="cbx-topo-lane edge">
                <div class="cbx-topo-lane-title">边端<span class="cbx-sec-spacer"></span><button class="cbx-op cbx-xs" @click="openOnboard" title="新盒子接入：生成 edgecore.yaml 配置">盒子接入</button></div>
                <div v-for="b in topoBoxes" :key="b.name" :ref="setBoxNodeRef(b.name)" class="cbx-topo-mod box" :class="{ down: b.ready === false }">
                  <div class="cbx-topo-mod-head">
                    <span class="cbx-topo-mod-name">{{ b.name }}</span>
                    <span class="cbx-topo-mod-badge" :class="{ ok: readyOk(b.ready), err: b.ready === false }">{{ readyZh(b.ready) }}</span>
                  </div>
                  <div class="cbx-topo-mod-sub">EdgeCore<template v-if="b.version && b.version !== '—'"> · v{{ b.version }}</template><template v-if="b.roles && b.roles !== '—'"> · {{ roleZh(b.roles) }}</template><br/>edgecore MQTT :1883 · {{ b.source === 'mqtt' ? 'MQTT 识别' : 'K8s Agent' }} · {{ devCountOf(b.name) }} 台待下发</div>
                  <!-- 盒子当前运行的服务/模型（云端部署，盒子周期上报 state/{box}/services） -->
                  <div class="cbx-topo-svcs">
                    <template v-if="b.services && b.services.length">
                      <div v-for="s in b.services" :key="s.name" class="cbx-topo-svc" :title="(s.command || '') + (s.url ? '\n' + s.url : '')">
                        <span class="cbx-topo-svc-dot" :class="{ on: s.running || s.status === 'running' }"></span>
                        <span class="cbx-topo-svc-name">{{ s.name }}</span>
                        <span class="cbx-topo-svc-type">{{ s.type || '' }}{{ s.running === false || s.status === 'stopped' ? ' · 已停止' : '' }}</span>
                      </div>
                    </template>
                    <div v-else class="cbx-topo-svc-empty">暂无云端部署应用</div>
                  </div>
                  <div class="cbx-topo-mod-ops">
                    <button class="cbx-op cbx-xs" @click="openBoxEdgeCfg(b)" title="配置盒子现场可达 IP / SSH 凭据（重启 Mapper 前必须配置且探测可达）">盒子IP</button>
                    <button class="cbx-op cbx-xs" @click="openAppDeploy(b)" title="云端部署模型/服务到盒子（经云端 Broker 命令主题下发，盒子订阅执行）">⬇ 部署</button>
                    <button class="cbx-op cbx-xs" :disabled="!!restartingKey || !edgeIpOk(b)" @click="restartMapper(b)" :title="edgeIpOk(b) ? '重启该盒子上的 box-mapper systemd 服务（云端 agent 经 SSH 到边缘盒子执行 systemctl restart box-mapper）' : '未配置盒子 IP 或探测不通，无法重启 Mapper（先点「盒子IP」配置现场可达地址）'">{{ restartingKey === 'edge:box-mapper' ? '重启中…' : '↻ 重启 Mapper' }}</button>
                  </div>
                </div>
                <div v-if="!topoBoxes.length" class="cbx-topo-empty">未识别到盒子节点（云端未连接）。</div>
              </div>
              <!-- 设备端列（采集设备总览，不按盒子分组） -->
              <div class="cbx-topo-lane dev">
                <div class="cbx-topo-lane-title">设备端<span class="cbx-sec-spacer"></span><button class="cbx-op cbx-xs" @click="openModelCreate" title="新建设备模型（DeviceModel）">＋ 模型</button><button class="cbx-op cbx-xs" @click="openCreate()" title="设备接入：新建采集设备并默认关联到盒子">＋ 设备</button></div>
                <div :ref="setNodeRef('n_devs')" class="cbx-topo-mod devgroup">
                  <div class="cbx-topo-mod-head">
                    <span class="cbx-topo-mod-name">采集设备</span>
                    <span class="cbx-topo-mod-badge ok">{{ topoAllCloudDevs.length + topoAllLocalDevs.length + topoUnmounted.length }} 台</span>
                  </div>
                  <div class="cbx-topo-mod-sub">边缘采集 MQTT :1883<template v-if="allDevProtos.length"> · 协议：{{ allDevProtos.join(' · ') }}</template></div>
                  <div class="cbx-topo-devlist">
                    <div v-if="topoAllCloudDevs.length" class="cbx-topo-devgroup">
                      <div class="cbx-topo-devlabel">云端真实</div>
                      <div v-for="d in topoAllCloudDevs" :key="'c' + d.name" class="cbx-topo-dev cloud" :class="{ on: d.state === 'online' }" @click="openDevRealtime(d)" :title="'Device CRD：' + d.name + (d.model ? '（模型 ' + d.model + '）' : '') + '（点击查看实时数据）'">
                        <span class="cbx-topo-dev-dot"></span>
                        <span class="cbx-topo-dev-name">{{ d.name }}</span>
                        <span class="cbx-topo-dev-sub">{{ stateZh(d.state) }}<template v-if="protoOfDev(d)"> · {{ protoOfDev(d) }}</template><template v-if="d.model"> · {{ d.model }}</template></span>
                        <span class="cbx-topo-dev-val" :class="{ 'cbx-invalid': isInvalidReading(d.primary) }">{{ fmtPrimary(d.primary) }}</span>
                        <span class="cbx-topo-dev-ops">
                          <button class="cbx-op cbx-tiny" @click.stop="openEditDev(d)" title="编辑该设备配置">✎ 配置</button>
                        </span>
                      </div>
                    </div>
                    <div v-if="topoAllLocalDevs.length" class="cbx-topo-devgroup">
                      <div class="cbx-topo-devlabel">待下发</div>
                      <div v-for="d in topoAllLocalDevs" :key="'l' + d.name" class="cbx-topo-dev pending" @click="openDevRealtime(d)" :title="'待下发：' + d.name">
                        <span class="cbx-topo-dev-dot"></span>
                        <span class="cbx-topo-dev-name">{{ d.name }}</span>
                        <span class="cbx-topo-dev-sub">待下发<template v-if="d.protocol"> · {{ d.protocol }}</template></span>
                        <span class="cbx-topo-dev-val" :class="{ 'cbx-invalid': isInvalidReading(d.primary) }">{{ fmtPrimary(d.primary) }}</span>
                        <span class="cbx-topo-dev-ops">
                          <button class="cbx-op cbx-tiny" @click.stop="openEditDev(d)" title="编辑该设备配置">✎ 配置</button>
                          <button class="cbx-op cbx-tiny" @click.stop="onApplyOneDev(d)" :disabled="applying" title="一键下发该设备到云端 K3s（保存本地并立即下发，无需单独保存）">{{ applying ? '下发中…' : '⤓ 下发' }}</button>
                        </span>
                      </div>
                    </div>
                    <div v-if="topoUnmounted.length" class="cbx-topo-devgroup">
                      <div class="cbx-topo-devlabel">未挂载</div>
                      <div v-for="d in topoUnmounted" :key="d.name" class="cbx-topo-dev pending" @click="openDevRealtime(d)" :title="'待下发：' + d.name">
                        <span class="cbx-topo-dev-dot"></span>
                        <span class="cbx-topo-dev-name">{{ d.name }}</span>
                        <span class="cbx-topo-dev-sub"><template v-if="d.protocol">{{ d.protocol }}</template></span>
                        <span class="cbx-topo-dev-val" :class="{ 'cbx-invalid': isInvalidReading(d.primary) }">{{ fmtPrimary(d.primary) }}</span>
                      </div>
                    </div>
                    <div v-if="!topoAllCloudDevs.length && !topoAllLocalDevs.length && !topoUnmounted.length" class="cbx-topo-dev-empty">暂无设备</div>
                  </div>
                </div>
              </div>
            </div>
            <!-- 连线覆盖层：贝塞尔箭头线从源模块边缘连到目标模块边缘，标签标注协议/方法
                 （path/g 由 recalcLinks → renderTopoLinks 原生 DOM 渲染，绕开 Vue 响应式以保箭头始终可见） -->
            <svg class="cbx-topo-svg">
              <defs>
                <marker id="tarr-red" markerWidth="11" markerHeight="9" refX="8" refY="4.5" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
                  <path d="M0 0 L0 9 L9 4.5 z" fill="var(--red)"></path>
                </marker>
                <marker id="tarr-green" markerWidth="11" markerHeight="9" refX="8" refY="4.5" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
                  <path d="M0 0 L0 9 L9 4.5 z" fill="var(--green)"></path>
                </marker>
                <marker id="tarr-blue" markerWidth="11" markerHeight="9" refX="8" refY="4.5" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
                  <path d="M0 0 L0 9 L9 4.5 z" fill="var(--accent)"></path>
                </marker>
              </defs>
            </svg>
          </div>
        </section>
        <!-- ② 资源列表：盒子 / 模型 / 设备（三列并排总览，点击行可快速跳转编辑/实时） -->
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>资源列表</b>
            <span class="cbx-sec-hint">{{ topoBoxes.length }} 盒 · {{ mergedModels.length }} 模型 · {{ mergedDevices.length }} 设备</span>
          </div>
          <div class="cbx-reslist">
            <!-- 盒子列表 -->
            <div class="cbx-rescol">
              <div class="cbx-rescol-head">盒子列表<span class="cbx-rescol-n">{{ topoBoxes.length }}</span></div>
              <div class="cbx-rescol-body">
                <div v-for="b in topoBoxes" :key="b.name" class="cbx-resrow" @click="openDevRealtime({ name: b.name })" :title="'盒子节点：' + b.name">
                  <span class="cbx-dot" :class="{ on: readyOk(b.ready) }"></span>
                  <span class="cbx-res-name">{{ b.name }}</span>
                  <span class="cbx-res-tag" :class="{ ok: readyOk(b.ready), err: b.ready === false }">{{ readyZh(b.ready) }}</span>
                  <span class="cbx-res-sub">EdgeCore<template v-if="b.version && b.version !== '—'"> v{{ b.version }}</template> · {{ devCountOf(b.name) }} 台待下发</span>
                </div>
                <div v-if="!topoBoxes.length" class="cbx-res-empty">未识别到盒子节点</div>
              </div>
            </div>
            <!-- 模型列表 -->
            <div class="cbx-rescol">
              <div class="cbx-rescol-head">▦ 模型列表<span class="cbx-rescol-n">{{ mergedModels.length }}</span></div>
              <div class="cbx-rescol-body">
                <div v-for="m in mergedModels" :key="m.name" class="cbx-resrow" @click="openEditModel(m)" :title="'模型（点击修改点位）：' + m.name">
                  <span class="cbx-res-name">{{ m.name }}</span>
                  <span class="cbx-res-tag ok" v-if="m._cloud">已下发</span>
                  <span class="cbx-res-tag" v-else>未下发</span>
                  <span class="cbx-res-sub"><template v-if="m.protocol">{{ m.protocol }}</template> · {{ modelPropCount(m) }} 属性</span>
                </div>
                <div v-if="!mergedModels.length" class="cbx-res-empty">暂无模型</div>
              </div>
            </div>
            <!-- 设备列表 -->
            <div class="cbx-rescol">
              <div class="cbx-rescol-head">◈ 设备列表<span class="cbx-rescol-n">{{ mergedDevices.length }}</span></div>
              <div class="cbx-rescol-body">
                <div v-for="d in mergedDevices" :key="d.name" class="cbx-resrow" @click="onDevClick(d)" :title="(d._cloud ? '云端设备（点击查看实时）' : '待下发设备（点击编辑配置）') + '：' + d.name + (modelOf(d) ? '（模型 ' + modelOf(d) + '）' : '')">
                  <span class="cbx-dot" :class="{ on: d.state === 'online' }"></span>
                  <span class="cbx-res-name">{{ d.name }}</span>
                  <span class="cbx-res-tag" :class="{ ok: d.state === 'online', err: d.state === 'offline' }">{{ devStateZh(d) }}</span>
                  <span class="cbx-res-sub">{{ modelOf(d) || '—' }}<template v-if="d.node"> · {{ d.node }}</template><template v-else-if="d.protocol"> · {{ d.protocol }}</template></span>
                  <span class="cbx-res-ops">
                    <button class="cbx-op cbx-tiny" @click.stop="openEditDev(d)" title="编辑该设备配置">✎ 配置</button>
                    <template v-if="d._cloud">
                      <button class="cbx-op cbx-tiny" @click.stop="openCloudHistory(d)" title="云端时序库（TDengine）历史读数曲线">历史</button>
                      <button class="cbx-op cbx-tiny" @click.stop="openIngest(d)" title="手动上报 twins（回写设备状态）">⬆ 上报</button>
                      <button class="cbx-op cbx-tiny danger" @click.stop="delCloud('device', d.name, d.namespace || 'default')" title="删除云端 Device CRD">🗑 删除</button>
                    </template>
                  </span>
                </div>
                <div v-if="!mergedDevices.length" class="cbx-res-empty">暂无设备</div>
              </div>
            </div>
          </div>
        </section>
        <!-- ③ 证书与 Token 有效期（独立区块：云端 agent 实时采集云端 CA/服务证书与共享 token） -->
        <section class="cbx-sec" v-if="(overview.certs || []).length || overview.token">
          <div class="cbx-sec-head">
            <b>证书与 Token 有效期</b>
            <span class="cbx-sec-hint">云端 agent 实时采集 · 剩余不足 30 天红色告警</span>
          </div>
          <div class="cbx-certlist">
            <div v-for="c in overview.certs || []" :key="c.cn" class="cbx-certrow">
              <code>{{ c.cn }}</code>
              <span class="cbx-cert-exp">{{ c.expires }}</span>
              <span class="cbx-cert-days" :class="{ warn: (c.remain_days ?? 999) < 30 }">{{ c.remain_days ?? '—' }} 天</span>
            </div>
            <div v-if="overview.token" class="cbx-certrow">
              <code>token</code>
              <span class="cbx-cert-exp">{{ overview.token.expires }}</span>
              <span class="cbx-cert-days" :class="{ warn: (overview.token.remain_days ?? 999) < 30 }">{{ overview.token.remain_days ?? '—' }} 天</span>
            </div>
          </div>
        </section>
        <!-- ③ 实时消息流（云端 Broker → 本平台） -->
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>实时消息流</b>
            <span class="cbx-sec-sub">最近 {{ messages.length }} 条</span>
          </div>
          <div ref="msgLogRef" class="cbx-msglog">
            <div v-for="(m, i) in messages" :key="i" class="cbx-msgrow">
              <span class="cbx-msgtime">{{ fmtTime(m.t) }}</span>
              <code class="cbx-msg-topic">{{ m.topic }}</code>
              <span class="cbx-msg-payload">{{ m.payload }}</span>
            </div>
            <div v-if="!messages.length" class="cbx-empty">暂无消息。</div>
          </div>
        </section>

        <!-- ④-1 云端实时日志（agent MQTT cloud/logs 推送 → 平台 WS /api/ws/cloud 实时转发） -->
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>云端实时日志</b>
            <span class="cbx-sec-sub" :class="{ warn: cloudWsState !== 'open' }">{{ cloudWsState === 'open' ? 'WebSocket 实时推送中' : '推送未连接（轮询兜底）' }}</span>
            <span v-if="cloudLogs.cloudcore" class="cbx-sec-sub">
              {{ cloudLogs.cloudcore.name }} · {{ cloudLogs.cloudcore.ready ? '就绪' : '未就绪' }} · {{ cloudLogs.cloudcore.phase }} · 重启 {{ cloudLogs.cloudcore.restarts }} 次 · 最近 {{ (cloudLogs.lines || []).length }} 行
            </span>
            <span v-else-if="cloudLogs.error" class="cbx-sec-sub warn">{{ cloudLogs.error }}</span>
            <span v-else class="cbx-sec-sub">采集器启动中…</span>
            <span class="cbx-sec-spacer"></span>
            <button class="cbx-op cbx-xs" :disabled="!!restartingKey" @click="restartCloudcore"
                    :title="agentStatusOk ? '重启云端 cloudcore 工作负载（kubectl rollout restart）' : '需先配置并连通云端 Agent'">
              {{ restartingKey === 'deployment:cloudcore' ? '重启中…' : '重启 CloudCore' }}
            </button>
          </div>
          <div ref="cloudLogRef" class="cbx-msglog cbx-cloudlog">
            <div v-for="(l, i) in cloudLogs.lines || []" :key="i" class="cbx-msgrow">
              <span class="cbx-msgtime">{{ fmtTime(l.t) }}</span>
              <code class="cbx-cloudline">{{ l.line }}</code>
            </div>
            <div v-if="!(cloudLogs.lines || []).length" class="cbx-empty">暂无日志。</div>
          </div>
        </section>

        <!-- ④ 发测试消息（向云端 Broker 发布） -->
        <section class="cbx-sec">
          <div class="cbx-sec-head"><b>发测试消息</b></div>
          <div class="cbx-form">
            <div class="cbx-form-row">
              <label>主题</label><input v-model="pubForm.topic" class="cbx-input" style="width:260px" placeholder="data/box-001/device-1"/>
              <label>载荷</label><input v-model="pubForm.payload" class="cbx-input" style="flex:1" placeholder='{"device":"device-1","value":88.8}'/>
              <button class="cbx-op primary" @click="doPublish">发布</button>
            </div>
          </div>
        </section>
          </section>
        </div><!-- /cbx-editor -->
      </main>
    </div><!-- /cbx-workbench -->

    <!-- 状态栏 -->
    <footer class="cbx-statusbar">
      <span class="cbx-st-item"><span class="cbx-dot" :class="{ on: overview.cloud_source === 'live' }"></span>云端 {{ overview.cloud_source === 'live' ? '在线' : (overview.cloud_source === 'stale' ? '数据过期' : (overview.cloud_source === 'degraded' ? '部分异常' : '不可达')) }}</span>
      <span class="cbx-st-item">模型 {{ devices.models?.length || 0 }} · 设备 {{ devices.devices?.length || 0 }}</span>
      <span class="cbx-st-item">消息 {{ messages.length }} 条</span>
      <span class="cbx-st-grow"></span>
      <span class="cbx-st-item">{{ cloudCfg.host || '172.19.134.45' }}</span>
      <span class="cbx-st-item">3s 自动刷新</span>
    </footer>

        <!-- 手动上报 twins 弹窗（对应云端管理台「上报」：SSH kubectl patch 回写 Device.status.twins） -->
        <div v-if="ingestOpen" class="cbx-mask" @click.self="ingestOpen = false">
          <div class="cbx-dialog">
            <div class="cbx-dialog-head">
              <b>手动上报 twins：<code>{{ ingestForm.device }}</code></b>
              <button class="cbx-op danger" @click="ingestOpen = false">✕</button>
            </div>
            <div class="cbx-form">
              <div class="cbx-form-row">
                <label>命名空间</label>
                <input v-model="ingestForm.namespace" class="cbx-input" style="width:120px"/>
                <label>属性</label>
                <input v-model="ingestForm.property" class="cbx-input" style="width:140px" placeholder="weight"/>
                <label>值</label>
                <input v-model="ingestForm.value" class="cbx-input" style="width:140px" placeholder="12.5"/>
              </div>
              <div class="cbx-form-row" style="margin-top:10px">
                <button class="cbx-op primary" @click="doIngest" :disabled="ingesting">{{ ingesting ? '上报中…' : '上报' }}</button>
                <span class="cbx-deploy-msg" :class="{ err: ingestErr }">{{ ingestMsg }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- 修改设备配置对话框（复用 create_device apply 做 upsert，本地 box_devices.json + 模型同步） -->
        <div v-if="editOpen" class="cbx-mask" @click.self="editOpen = false">
          <div class="cbx-dialog cbx-dialog-lg">
            <div class="cbx-dialog-head">
              <b>{{ editTarget === 'model' ? '修改模型' : '修改设备' }}：<code>{{ editForm.modelName }}</code></b>
              <button class="cbx-op danger" @click="editOpen = false">✕</button>
            </div>
            <div class="cbx-form">
              <div class="cbx-form-row">
                <label>协议</label>
                <select v-model="editForm.protocol" class="cbx-select">
                  <option value="modbus">Modbus（RTU / TCP）</option>
                  <option value="opcua">OPC-UA</option>
                  <option value="bluetooth">Bluetooth</option>
                  <option value="lora">LoRaWAN（LoRa 网关）</option>
                  <option value="cellular">5G/4G 模块自监控</option>
                </select>
              </div>
              <div class="cbx-form-row">
                <template v-if="editTarget !== 'model'">
                  <label>模型</label>
                  <select v-model="editForm.modelName" class="cbx-select" @change="onPickEditModel" title="切换模型会带出该模型的协议与属性点位">
                    <option value="" disabled>请选择模型…</option>
                    <option v-for="m in devices.models || []" :key="m.name" :value="m.name">{{ m.name }}（{{ m.protocol }} · {{ (m.properties || []).length }} 属性）</option>
                  </select>
                  <button class="cbx-op cbx-xs" @click="openModelCreate" title="先创建 DeviceModel 再选择">＋ 新建模型</button>
                  <label>设备名</label><input v-model="editForm.deviceName" class="cbx-input" placeholder="box-device"/>
                </template>
                <template v-else>
                  <label>模型名</label><input v-model="editForm.modelName" class="cbx-input" placeholder="box-metric-model" disabled/>
                  <span class="cbx-sec-sub">模型为共享配置：点位变更对引用它的所有设备同时生效，无单独设备名</span>
                </template>
              </div>
              <div v-if="editTarget !== 'model'" class="cbx-form-row">
                <label>绑定流程设备</label>
                <select v-model="editForm.boundDevice" class="cbx-select" style="width:300px" title="从现有系统流程的设备中选择：保存后该设备的云端读数将同步到所选流程设备实例（关联制）">
                  <option value="">不绑定</option>
                  <optgroup v-for="grp in procGroups" :key="grp.unit" :label="grp.unit">
                    <option v-for="d in grp.devices" :key="d.id" :value="d.id">{{ d.label || d.name }}（{{ d.id }}）</option>
                  </optgroup>
                </select>
                <label v-if="editForm.boundDevice" style="margin-left:10px">换算系数</label>
                <input v-if="editForm.boundDevice" v-model.number="editForm.boundFactor" type="number" step="any" class="cbx-input" style="width:90px" title="云端原始读数 × 此系数 = 同步到流程设备的读数（如传感器 kg/min → t/h 填 0.06；无需换算填 1）"/>
                <span class="cbx-sec-sub">未选择则解除当前绑定</span>
              </div>
              <div v-if="editTarget !== 'model'" class="cbx-form-row">
                <label>绑定云端设备</label>
                <select v-model="editForm.cloudDevice" class="cbx-select" style="width:300px" title="选择盒子已上报、平台已识别的云端真实设备：保存后该设备的实时读数将归入此设备">
                  <option value="">不绑定（按设备名自动匹配）</option>
                  <optgroup v-for="g in cloudUnboundGroups" :key="g.label" :label="g.label">
                    <option v-for="c in g.items" :key="c.name" :value="c.name">{{ c.name }}（{{ stateZh(c.state) }}<template v-if="c.model"> · {{ c.model }}</template>）</option>
                  </optgroup>
                </select>
                <span class="cbx-sec-sub">未选择则按设备名自动匹配</span>
              </div>
              <div class="cbx-form-row">
                <label>命名空间</label><input v-model="editForm.namespace" class="cbx-input" style="width:110px"/>
                <template v-if="editTarget !== 'model'">
                  <label>调度节点（盒子）</label>
                  <select v-model="editForm.nodeName" class="cbx-input" style="width:170px" title="从识别到的盒子中选择，或保留原值">
                    <option v-for="n in overview.nodes || []" :key="n.name" :value="n.name">{{ n.name }}（{{ readyZh(n.ready) }}）</option>
                    <option v-if="!(overview.nodes || []).some((n) => n.name === editForm.nodeName)" :value="editForm.nodeName">{{ editForm.nodeName }}（未识别）</option>
                  </select>
                  <label>采集周期(ms)</label><input v-model.number="editForm.collectCycle" type="number" class="cbx-input" style="width:100px"/>
                </template>
              </div>


              <!-- 协议通信参数（模型编辑时不涉及设备通信参数） -->
              <template v-if="editTarget !== 'model'">
              <!-- Modbus 协议参数 -->
              <template v-if="editForm.protocol === 'modbus'">
                <div class="cbx-form-row">
                  <label>通信方式</label>
                  <select v-model="editForm.comm.commType" class="cbx-select">
                    <option value="serial">串口 RTU</option>
                    <option value="tcp">TCP</option>
                  </select>
                  <label>slaveID</label><input v-model.number="editForm.comm.slaveID" type="number" class="cbx-input" style="width:70px"/>
                  <template v-if="editForm.comm.commType === 'serial'">
                    <label>串口</label><input v-model="editForm.comm.serialPort" class="cbx-input" style="width:150px"/>
                    <label>波特率</label><input v-model.number="editForm.comm.baudRate" type="number" class="cbx-input" style="width:80px"/>
                    <label>校验</label>
                    <select v-model="editForm.comm.parity" class="cbx-select"><option>none</option><option>even</option><option>odd</option></select>
                  </template>
                  <template v-else>
                    <label>IP</label><input v-model="editForm.comm.tcpIP" class="cbx-input" style="width:130px"/>
                    <label>端口</label><input v-model.number="editForm.comm.tcpPort" type="number" class="cbx-input" style="width:70px"/>
                  </template>
                </div>
              </template>
              <!-- OPC-UA 协议参数 -->
              <template v-else-if="editForm.protocol === 'opcua'">
                <div class="cbx-form-row">
                  <label>URL</label><input v-model="editForm.opcua.url" class="cbx-input" style="width:220px" placeholder="opc.tcp://127.0.0.1:4840"/>
                  <label>用户名</label><input v-model="editForm.opcua.userName" class="cbx-input" style="width:100px"/>
                  <label>密码</label><input v-model="editForm.opcua.password" class="cbx-input" style="width:100px"/>
                </div>
              </template>
              <!-- Bluetooth 协议参数 -->
              <template v-else-if="editForm.protocol === 'bluetooth'">
                <div class="cbx-form-row">
                  <label>MAC 地址</label><input v-model="editForm.bluetooth.macAddress" class="cbx-input" style="width:170px" placeholder="AA:BB:CC:DD:EE:FF"/>
                </div>
              </template>
              <!-- LoRaWAN 协议参数（盒子侧 LoRa 网关 + ChirpStack，上行走本地 mosquitto） -->
              <template v-else-if="editForm.protocol === 'lora'">
                <div class="cbx-form-row">
                  <label>Broker</label><input v-model="editForm.lora.broker" class="cbx-input" style="width:140px" placeholder="127.0.0.1"/>
                  <label>端口</label><input v-model.number="editForm.lora.port" type="number" class="cbx-input" style="width:70px"/>
                  <label>应用ID</label><input v-model="editForm.lora.applicationID" class="cbx-input" style="width:70px" placeholder="1"/>
                  <label>DevEUI</label><input v-model="editForm.lora.devEUI" class="cbx-input" style="width:160px" placeholder="0011223344556677"/>
                </div>
                <div class="cbx-form-row">
                  <label>AppKey</label><input v-model="editForm.lora.appKey" class="cbx-input" style="width:170px"/>
                  <label>频段</label>
                  <select v-model="editForm.lora.region" class="cbx-select"><option>CN470</option><option>EU868</option><option>US915</option></select>
                  <label>数据率</label>
                  <select v-model="editForm.lora.dataRate" class="cbx-select"><option>SF7BW125</option><option>SF9BW125</option><option>SF12BW125</option></select>
                </div>
              </template>
              <!-- 5G/4G 模块自监控协议参数 -->
              <template v-else-if="editForm.protocol === 'cellular'">
                <div class="cbx-form-row">
                  <label>AT 串口</label><input v-model="editForm.cellular.serialPort" class="cbx-input" style="width:140px" placeholder="/dev/ttyUSB2"/>
                  <label>波特率</label><input v-model.number="editForm.cellular.baudRate" type="number" class="cbx-input" style="width:90px"/>
                  <label>APN</label><input v-model="editForm.cellular.apn" class="cbx-input" style="width:110px" placeholder="cmnet"/>
                  <label>蜂窝网卡</label><input v-model="editForm.cellular.iface" class="cbx-input" style="width:90px" placeholder="wwan0"/>
                </div>
              </template>

              </template>
              <!-- 属性点位 -->
              <div class="cbx-sec-head" style="margin-top:8px">
                <b>属性点位</b>
                <button class="cbx-op" @click="addEditProp">＋ 添加</button>
              </div>
              <div v-for="(p, i) in editForm.properties" :key="i" class="cbx-prop-row">
                <input v-model="p.name" class="cbx-input" style="width:110px" placeholder="属性名"/>
                <select v-model="p.type" class="cbx-select">
                  <option v-for="t in ['float','int','double','string','boolean']" :key="t">{{ t }}</option>
                </select>
                <select v-model="p.accessMode" class="cbx-select">
                  <option value="r">ReadOnly</option><option value="rw">ReadWrite</option>
                </select>
                <template v-if="editForm.protocol === 'modbus'">
                  <select v-model="p.registerType" class="cbx-select">
                    <option v-for="r in ['holdingRegister','inputRegister','coil','discreteInput']" :key="r">{{ r }}</option>
                  </select>
                  <input v-model.number="p.register" type="number" class="cbx-input" style="width:70px" placeholder="寄存器"/>
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="editForm.protocol === 'opcua'">
                  <input v-model="p.nodeID" class="cbx-input" style="width:170px" placeholder="nodeID"/>
                </template>
                <template v-else-if="editForm.protocol === 'bluetooth'">
                  <input v-model="p.characteristicUUID" class="cbx-input" style="width:170px" placeholder="characteristicUUID"/>
                </template>
                <template v-else-if="editForm.protocol === 'lora'">
                  <input v-model="p.payloadKey" class="cbx-input" style="width:170px" placeholder="上行JSON键 payloadKey"/>
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="editForm.protocol === 'cellular'">
                  <select v-model="p.kind" class="cbx-select">
                    <option v-for="k in ['signal','csq','rsrp','rsrq','sinr','iccid','imsi','imei','reg','rx_rate','tx_rate']" :key="k">{{ k }}</option>
                  </select>
                </template>
                <input v-model="p.unit" class="cbx-input" style="width:60px" placeholder="单位"/>
                <button class="cbx-op danger" @click="editForm.properties.splice(i, 1)">✕</button>
              </div>

              <div class="cbx-form-row" style="margin-top:10px">
                <button class="cbx-op primary" @click="applyEditDev" :disabled="editSaving || applying" title="保存到本地并立即下发云端 K3s（无需单独保存）">{{ editSaving || applying ? '下发中…' : '保存并下发' }}</button>
                <button class="cbx-op" @click="dryRunEdit" :disabled="editSaving">生成 YAML 预览</button>
                <span class="cbx-sec-sub" v-if="editErr" style="color:var(--red)">{{ editErr }}</span>
                <span class="cbx-deploy-msg" :class="{ err: editErr }">{{ editMsg }}</span>
              </div>

              <div v-if="editPreview" class="cbx-preview" style="margin-top:8px">
                <div class="cbx-preview-head">
                  <b>YAML 预览（{{ editPreviewMode }}）</b>
                  <button class="cbx-op" @click="copyEditYaml">复制</button>
                </div>
                <pre class="cbx-code">{{ editPreview }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- 设备实时数据对话框（单设备点击进入查看，3s 轮询，折线图展示） -->
        <div v-if="devRtOpen" class="cbx-mask" @click.self="closeDevRealtime">
          <div class="cbx-dialog cbx-dialog-xl">
            <div class="cbx-dialog-head">
              <b>实时数据：<code>{{ devRtName }}</code></b>
              <span v-if="devRt" class="cbx-tag" :class="{ ok: devRt.state === 'reporting' }">{{ devRt.state === 'reporting' ? '上报中' : '等待上报' }}</span>
              <span v-if="devRt" class="cbx-sec-hint">节点 {{ devRt.node }} · 模型 {{ devRt.model }} · 每 3s 自动刷新</span>
              <button class="cbx-op danger" @click="closeDevRealtime">✕</button>
            </div>
            <div v-if="devRt && devRt.twins && devRt.twins.length" class="cbx-rt">
              <!-- 属性切换 -->
              <div class="cbx-rt-tabs">
                <button v-for="t in devRt.twins" :key="t.propertyName"
                        class="cbx-rt-tab" :class="{ active: rtSelProp === t.propertyName }"
                        @click="rtSel = t.propertyName" :title="'切换查看 ' + t.propertyName + ' 趋势'">
                  <code>{{ t.propertyName }}</code>
                  <span class="cbx-rt-cur">{{ t.invalid ? '无有效数据' : fmtPrimary(t.reported) }}</span>
                  <span class="cbx-rt-unit">{{ t.unit }}</span>
                </button>
              </div>

              <!-- 主折线图（120 点滑动窗口，约 6 分钟） -->
              <div class="cbx-rt-chart" ref="rtChartEl">
                <svg v-if="rtPoints.length > 1" :viewBox="rtView" class="cbx-rt-svg"
                     @mousemove="rtHoverMove" @mouseleave="rtHover = -1" preserveAspectRatio="none">
                  <!-- 水平网格 + Y 轴刻度 -->
                  <g v-for="(tk, i) in rtYticks" :key="'y' + i">
                    <line :x1="rtPlot.x0" :x2="rtPlot.x1" :y1="tk.y" :y2="tk.y" class="cbx-grid"/>
                    <text :x="rtPlot.x0 - 8" :y="tk.y + 3" text-anchor="end" class="cbx-axis">{{ tk.label }}</text>
                  </g>
                  <!-- 垂直网格 + X 轴时间刻度 -->
                  <g v-for="(tk, i) in rtXticks" :key="'x' + i">
                    <line :x1="tk.x" :x2="tk.x" :y1="rtPlot.y0" :y2="rtPlot.y1" class="cbx-grid"/>
                    <text :x="tk.x" :y="rtPlot.y1 + 16" text-anchor="middle" class="cbx-axis">{{ tk.label }}</text>
                  </g>
                  <!-- 面积 + 折线 -->
                  <path v-if="rtArea" :d="rtArea" class="cbx-rt-area"/>
                  <polyline :points="rtLine" class="cbx-rt-line"/>
                  <!-- 悬停定位线 + 数据点 -->
                  <g v-if="rtHover >= 0 && rtHoverInfo">
                    <line :x1="rtHoverInfo.x" :x2="rtHoverInfo.x" :y1="rtPlot.y0" :y2="rtPlot.y1" class="cbx-hv-line"/>
                    <circle :cx="rtHoverInfo.x" :cy="rtHoverInfo.y" r="4" class="cbx-hv-dot"/>
                  </g>
                </svg>
                <div v-else class="cbx-rt-empty">{{ rtEmptyMsg }}</div>
                <div v-if="rtHover >= 0 && rtHoverInfo" class="cbx-rt-tip" :style="rtTipStyle">
                  <div class="cbx-rt-tip-t">{{ rtHoverInfo.time }}</div>
                  <div class="cbx-rt-tip-v">{{ rtHoverInfo.val }} <span class="cbx-rt-unit">{{ rtUnit }}</span></div>
                </div>
              </div>

              <!-- 当前读数摘要 -->
              <div v-if="rtCur" class="cbx-rt-currow">
                <span class="cbx-rt-curlabel">{{ rtSelProp }}</span>
                <b class="cbx-rt-curval">{{ rtCur.invalid ? '无有效数据' : fmtPrimary(rtCur.reported) }}</b>
                <span class="cbx-rt-unit">{{ rtCur.unit }}</span>
                <span class="cbx-rt-upd">更新于 {{ rtCur.timestamp ? fmtAgo(rtCur.timestamp) : '—' }} · 采样 {{ rtSeries.length }} 点</span>
              </div>

              <!-- 全部属性一览（补充） -->
              <table class="cbx-table">
                <thead><tr><th>属性</th><th>reported（实时值）</th><th>单位</th><th>timestamp</th><th>采样点数</th></tr></thead>
                <tbody>
                  <tr v-for="t in devRt.twins" :key="t.propertyName">
                    <td><code>{{ t.propertyName }}</code></td>
                    <td class="val"><span :class="{ 'cbx-invalid': t.invalid }">{{ t.invalid ? '无有效数据' : fmtPrimary(t.reported) }}</span></td>
                    <td>{{ t.unit || '' }}</td>
                    <td>{{ t.timestamp ? fmtAgo(t.timestamp) : '—' }}</td>
                    <td>{{ (devRt.history[t.propertyName] || []).length }}</td>
                  </tr>
                </tbody>
              </table>
              <p class="cbx-note">读数双源融合：① 云端 twins（边缘 Mapper 实时同步）；② 盒子 MQTT 直报 data/#（平台订阅，时间戳更新时优先）。双源均无数据说明盒子侧采集或上报异常，可先确认概览「链路状态」cloud/crds 推送是否新鲜。盒子运行期无需 IP，数据由盒子主动上报。折线图为 3s 滑动窗口、最多 120 点；「无有效数据」多为传感器无信号或未标定。</p>
            </div>
            <div v-else class="cbx-empty">该设备暂无实时上报数据（设备可能未下发云端，或边缘未上报）。</div>
          </div>
        </div>

        <!-- 盒子一键接入弹窗（工具栏「盒子接入」入口） -->
        <div v-if="onboardOpen" class="cbx-mask" @click.self="onboardOpen = false">
          <div class="cbx-dialog cbx-dialog-xl">
            <div class="cbx-dialog-head">
              <b>盒子一键接入（自解压脚本：box-deploy 采集包 + edgecore.yaml + rootCA + token）</b>
              <button class="cbx-op danger" @click="onboardOpen = false">✕</button>
            </div>
            <div class="cbx-form">
              <div class="cbx-form-row">
                <label>盒子主机名</label><input v-model="onboardForm.hostname" class="cbx-input" placeholder="edge-box"/>
                <label>云端 CloudCore IP</label><input v-model="onboardForm.cloudIP" class="cbx-input" placeholder="172.19.134.45"/>
                <label>盒子 IP（可选，远程一键时作为直达地址）</label><input v-model="onboardForm.boxIP" class="cbx-input" placeholder="192.168.1.20"/>
                <button class="cbx-op primary" :disabled="!onboardForm.cloudIP || onboardBusy" @click="doOnboard">{{ onboardBusy ? '生成中…' : '生成一键脚本' }}</button>
              </div>
              <p class="cbx-note">一键脚本内置 box-deploy 采集部署包（mapper + mosquitto + 云边协同断点续传，约 18 MB），盒子执行一条 <code>bash onboard_box.sh</code> 即完成：① EdgeCore 接入（keadm join）→ ② rootCA / edgecore.yaml 下发 → ③ 部署包解包 → ④ config.json 自动定制（boxId / broker）→ ⑤ 一键部署 → ⑥ 链路自检。幂等，可重复执行。</p>
            </div>
            <div v-if="onboardResult" class="cbx-onboard">
              <div class="cbx-kv">
                <div><span>共享 Token</span><code class="wrap">{{ onboardResult.token }}</code></div>
                <div><span>CA 指纹</span><code class="wrap">{{ onboardResult.caHash }}</code></div>
                <div v-if="onboardResult.token_expires"><span>Token 有效期至</span><b>{{ onboardResult.token_expires }}</b></div>
                <div><span>一键脚本</span><b>{{ onboardResult.script_name }} · {{ (onboardResult.script_size / 1024 / 1024).toFixed(1) }} MB</b><code class="wrap">sha256 {{ onboardResult.script_sha256 }}</code></div>
                <div v-if="onboardResult.script_generated_at"><span>生成时间</span><b>{{ onboardResult.script_generated_at }}</b></div>
              </div>
              <div class="cbx-onboard-actions">
                <button class="cbx-op primary" @click="downloadOnboardScript">⬇ 下载 onboard_box.sh</button>
                <button class="cbx-op" :disabled="remoteRunning" @click="doOnboardRemote">{{ remoteRunning ? '远程接入中…' : '远程一键接入（云端 agent 推送执行）' }}</button>
              </div>
              <p class="cbx-note" v-if="onboardResult.script_hint">{{ onboardResult.script_hint }}</p>
              <p class="cbx-note">远程接入前提：① 平台 ⇄ 云端 agent 已配置（总览 → 配置）；② agent config.json 已配置 edge（盒子可达地址）。盒子无直达 IP 时请下载脚本后到现场执行。</p>
              <div v-if="remoteSteps.length" class="cbx-remote-steps">
                <div v-for="(s, i) in remoteSteps" :key="i" class="cbx-remote-step">
                  <b :class="s.ok ? 'ok' : 'fail'">{{ s.ok ? '✔' : '✘' }} {{ i + 1 }}. {{ s.name }}</b>
                  <pre class="cbx-code" v-if="s.detail">{{ s.detail }}</pre>
                </div>
              </div>
              <details class="cbx-details" :open="ghResult">
                <summary>GitHub 托管（盒子现场一条 curl 命令接入，免传 18MB 脚本）</summary>
                <div class="cbx-form">
                  <div class="cbx-form-row">
                    <label>GitHub owner</label><input v-model="ghForm.owner" class="cbx-input" placeholder="zhibinQiu"/>
                    <label>repo</label><input v-model="ghForm.repo" class="cbx-input" placeholder="power_simulation"/>
                    <label>分支</label><input v-model="ghForm.branch" class="cbx-input" placeholder="master"/>
                    <button class="cbx-op" :disabled="ghBusy" @click="saveGithubConfig">{{ ghBusy ? '保存中…' : '保存配置' }}</button>
                  </div>
                  <div class="cbx-form-row">
                    <label>GitHub PAT（公开仓库盒子现场拉取无需验证；仅「同步写入」需要，留空沿用已保存）</label>
                    <input v-model="ghForm.token" type="password" class="cbx-input" placeholder="ghp_…"/>
                    <button class="cbx-op primary" :disabled="ghBusy || !onboardForm.cloudIP" @click="syncGithub">{{ ghBusy ? '同步中（含 13MB 部署包，约 10~30s）…' : '同步到 GitHub' }}</button>
                    <button class="cbx-op" :disabled="ghExportBusy || !onboardForm.cloudIP" @click="exportBoxConfig">{{ ghExportBusy ? '生成中…' : '⬇ 导出 box-config.json' }}</button>
                  </div>
                  <p class="cbx-note">「导出 box-config.json」：现场凭此配置 + 仓库脚本即可接入（放盒子 <code>/opt/weight-bridge/box-config.json</code>，命令见下方）。</p>
                </div>
                <div v-if="ghResult && ghResult.ok" class="cbx-kv">
                  <div><span>盒子现场命令（任意盒子 root 执行，自动拉部署包/证书/配置 + keadm join + 自检）</span><code class="wrap">{{ ghResult.command }}</code></div>
                  <div v-if="ghResult.caHash"><span>CA 指纹</span><code class="wrap">{{ ghResult.caHash }}</code></div>
                </div>
                <div v-if="ghExport && ghExport.ok" class="cbx-kv">
                  <div><span>现场用法（配置文件已放盒子 /opt/weight-bridge/box-config.json 时，一条命令完成接入）</span><code class="wrap">curl -fsSL {{ ghLauncherUrl }} | bash</code></div>
                  <div><span>显式指定配置路径</span><code class="wrap">curl -fsSL {{ ghLauncherUrl }} | bash -s -- -c /path/box-config.json</code></div>
                  <div><span>box-config.json 内容（保存到盒子 /opt/weight-bridge/box-config.json）</span><pre class="cbx-code">{{ ghExport.content }}</pre></div>
                  <div v-if="!ghExport.token_set" class="cbx-note">token 留空：云端未取到共享 token，不影响部署 —— 脚本自动从仓库 <code>onboard/token</code> 拉取，也可手工填入。</div>
                </div>
                <div v-if="ghResult && ghResult.files" class="cbx-remote-steps">
                  <div v-for="(f, i) in ghResult.files" :key="i" class="cbx-remote-step">
                    <b :class="f.ok ? 'ok' : 'fail'">{{ f.ok ? '✔' : '✘' }} {{ f.path }}（{{ (f.size / 1024 / 1024).toFixed(1) }} MB）</b>
                  </div>
                </div>
                <p class="cbx-note">托管说明：平台将「引导脚本 + box-deploy 部署包 + edgecore.yaml + rootCA + token」同步至仓库 <code>onboard/</code> 目录（幂等覆盖）；edgecore.yaml 由盒子端按配置自动替换，token 重签后无需重推。仓库内含共享 token 与 rootCA，公开前请评估风险。盒子现场执行 <code>curl -fsSL {{ ghResult ? ghResult.launcher_url : '…' }} | bash</code> 即完成接入。</p>
              </details>
              <details class="cbx-details">
                <summary>高级：edgecore.yaml</summary>
                <div class="cbx-preview-head"><span></span><button class="cbx-op" @click="copyOnboard">复制</button></div>
                <pre class="cbx-code">{{ onboardResult.edgecore }}</pre>
              </details>
              <details class="cbx-details">
                <summary>高级：手工部署命令（备选）</summary>
                <pre class="cbx-code">{{ onboardResult.commands.join('\n') }}</pre>
              </details>
            </div>
          </div>
        </div>

        <!-- 新建设备弹窗（工具栏「新建设备」入口） -->
        <div v-if="createOpen" class="cbx-mask" @click.self="createOpen = false">
          <div class="cbx-dialog cbx-dialog-xl">
            <div class="cbx-dialog-head">
              <b>新建设备</b>
              <button class="cbx-op danger" @click="createOpen = false">✕</button>
            </div>
            <div class="cbx-form">
              <div class="cbx-form-row">
                <label>协议</label>
                <select v-model="form.protocol" class="cbx-select">
                  <option value="modbus">Modbus（RTU / TCP）</option>
                  <option value="opcua">OPC-UA</option>
                  <option value="bluetooth">Bluetooth</option>
                  <option value="lora">LoRaWAN（LoRa 网关）</option>
                  <option value="cellular">5G/4G 模块自监控</option>
                </select>
              </div>
              <div class="cbx-form-row">
                <label>模型</label>
                <select v-model="form.modelName" class="cbx-select" @change="onPickModel" title="选择已创建的 DeviceModel 复用；留空则保存时自动创建与设备同名的模型">
                  <option value="">（自动创建同名模型）</option>
                  <option v-for="m in devices.models || []" :key="m.name" :value="m.name">{{ m.name }}（{{ m.protocol }} · {{ (m.properties || []).length }} 属性）</option>
                </select>
                <button class="cbx-op cbx-xs" @click="openModelCreate" title="先创建 DeviceModel 再选择">＋ 新建模型</button>
                <label>设备名</label><input v-model="form.deviceName" class="cbx-input" placeholder="box-device"/>
              </div>
              <div class="cbx-form-row">
                <label>绑定流程设备</label>
                <select v-model="form.boundDevice" class="cbx-select" style="width:300px" title="从现有系统流程的设备中选择：保存后该设备的云端读数将同步到所选流程设备实例（关联制）">
                  <option value="">不绑定</option>
                  <optgroup v-for="grp in procGroups" :key="grp.unit" :label="grp.unit">
                    <option v-for="d in grp.devices" :key="d.id" :value="d.id">{{ d.label || d.name }}（{{ d.id }}）</option>
                  </optgroup>
                </select>
                <label v-if="form.boundDevice" style="margin-left:10px">换算系数</label>
                <input v-if="form.boundDevice" v-model.number="form.boundFactor" type="number" step="any" class="cbx-input" style="width:90px" title="云端原始读数 × 此系数 = 同步到流程设备的读数（如传感器 kg/min → t/h 填 0.06；无需换算填 1）"/>
                <span class="cbx-sec-sub">保存后云端读数同步到该流程设备</span>
              </div>
              <div class="cbx-form-row">
                <label>绑定云端设备</label>
                <select v-model="form.cloudDevice" class="cbx-select" style="width:300px" title="选择盒子已上报、平台已识别的云端真实设备：保存后该设备的实时读数将归入此设备（云端身份优先于此名匹配）" @change="onPickCloudDevice">
                  <option value="">不绑定（按设备名自动匹配）</option>
                  <optgroup v-for="g in cloudUnboundGroups" :key="g.label" :label="g.label">
                    <option v-for="c in g.items" :key="c.name" :value="c.name">{{ c.name }}（{{ stateZh(c.state) }}<template v-if="c.model"> · {{ c.model }}</template>）</option>
                  </optgroup>
                  <option v-if="!cloudUnbound.length" value="" disabled>未识别到云端设备（盒子需已接入并上报读数）</option>
                </select>
                <span class="cbx-sec-sub">选中后自动采用该云端设备名（一键转平台设备）</span>
              </div>
              <div class="cbx-form-row">
                <label>命名空间</label><input v-model="form.namespace" class="cbx-input" style="width:90px" placeholder="default"/>
                <label>调度节点</label>
                <select v-model="form.nodeName" class="cbx-input" title="从识别到的盒子中选择">
                  <option v-for="n in overview.nodes || []" :key="n.name" :value="n.name">{{ n.name }}（{{ readyZh(n.ready) }}）</option>
                </select>
                <label>采集周期(ms)</label><input v-model.number="form.collectCycle" type="number" class="cbx-input" style="width:100px"/>
              </div>

              <!-- Modbus 协议参数 -->
              <template v-if="form.protocol === 'modbus'">
                <div class="cbx-form-row">
                  <label>通信方式</label>
                  <select v-model="form.comm.commType" class="cbx-select">
                    <option value="serial">串口 RTU</option>
                    <option value="tcp">TCP</option>
                  </select>
                  <label>slaveID</label><input v-model.number="form.comm.slaveID" type="number" class="cbx-input" style="width:70px"/>
                  <template v-if="form.comm.commType === 'serial'">
                    <label>串口</label><input v-model="form.comm.serialPort" class="cbx-input" style="width:110px"/>
                    <label>波特率</label><input v-model.number="form.comm.baudRate" type="number" class="cbx-input" style="width:80px"/>
                    <label>校验</label>
                    <select v-model="form.comm.parity" class="cbx-select"><option>none</option><option>even</option><option>odd</option></select>
                  </template>
                  <template v-else>
                    <label>IP</label><input v-model="form.comm.tcpIP" class="cbx-input" style="width:120px"/>
                    <label>端口</label><input v-model.number="form.comm.tcpPort" type="number" class="cbx-input" style="width:70px"/>
                  </template>
                </div>
              </template>
              <!-- OPC-UA 协议参数 -->
              <template v-else-if="form.protocol === 'opcua'">
                <div class="cbx-form-row">
                  <label>URL</label><input v-model="form.opcua.url" class="cbx-input" style="width:200px" placeholder="opc.tcp://127.0.0.1:4840"/>
                  <label>用户名</label><input v-model="form.opcua.userName" class="cbx-input" style="width:100px"/>
                  <label>密码</label><input v-model="form.opcua.password" class="cbx-input" style="width:100px"/>
                </div>
              </template>
              <!-- Bluetooth 协议参数 -->
              <template v-else-if="form.protocol === 'bluetooth'">
                <div class="cbx-form-row">
                  <label>MAC 地址</label><input v-model="form.bluetooth.macAddress" class="cbx-input" style="width:160px" placeholder="AA:BB:CC:DD:EE:FF"/>
                </div>
              </template>
              <!-- LoRaWAN 协议参数（盒子侧 LoRa 网关 + ChirpStack，上行走本地 mosquitto） -->
              <template v-else-if="form.protocol === 'lora'">
                <div class="cbx-form-row">
                  <label>Broker</label><input v-model="form.lora.broker" class="cbx-input" style="width:130px" placeholder="127.0.0.1"/>
                  <label>端口</label><input v-model.number="form.lora.port" type="number" class="cbx-input" style="width:70px"/>
                  <label>应用ID</label><input v-model="form.lora.applicationID" class="cbx-input" style="width:70px" placeholder="1"/>
                  <label>DevEUI</label><input v-model="form.lora.devEUI" class="cbx-input" style="width:150px" placeholder="0011223344556677"/>
                </div>
                <div class="cbx-form-row">
                  <label>AppKey</label><input v-model="form.lora.appKey" class="cbx-input" style="width:160px"/>
                  <label>频段</label>
                  <select v-model="form.lora.region" class="cbx-select"><option>CN470</option><option>EU868</option><option>US915</option></select>
                  <label>数据率</label>
                  <select v-model="form.lora.dataRate" class="cbx-select"><option>SF7BW125</option><option>SF9BW125</option><option>SF12BW125</option></select>
                </div>
              </template>
              <!-- 5G/4G 模块自监控协议参数 -->
              <template v-else-if="form.protocol === 'cellular'">
                <div class="cbx-form-row">
                  <label>AT 串口</label><input v-model="form.cellular.serialPort" class="cbx-input" style="width:130px" placeholder="/dev/ttyUSB2"/>
                  <label>波特率</label><input v-model.number="form.cellular.baudRate" type="number" class="cbx-input" style="width:90px"/>
                  <label>APN</label><input v-model="form.cellular.apn" class="cbx-input" style="width:100px" placeholder="cmnet"/>
                  <label>蜂窝网卡</label><input v-model="form.cellular.iface" class="cbx-input" style="width:90px" placeholder="wwan0"/>
                </div>
              </template>

              <!-- 属性点位 -->
              <div class="cbx-sec-head" style="margin-top:8px">
                <b>属性点位</b>
                <button class="cbx-op" @click="addProp">＋ 添加</button>
              </div>
              <div v-for="(p, i) in form.properties" :key="i" class="cbx-prop-row">
                <input v-model="p.name" class="cbx-input" style="width:110px" placeholder="属性名"/>
                <select v-model="p.type" class="cbx-select">
                  <option v-for="t in ['float','int','double','string','boolean']" :key="t">{{ t }}</option>
                </select>
                <select v-model="p.accessMode" class="cbx-select">
                  <option value="r">ReadOnly</option><option value="rw">ReadWrite</option>
                </select>
                <template v-if="form.protocol === 'modbus'">
                  <select v-model="p.registerType" class="cbx-select">
                    <option v-for="r in ['holdingRegister','inputRegister','coil','discreteInput']" :key="r">{{ r }}</option>
                  </select>
                  <input v-model.number="p.register" type="number" class="cbx-input" style="width:70px" placeholder="寄存器"/>
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="form.protocol === 'opcua'">
                  <input v-model="p.nodeID" class="cbx-input" style="width:170px" placeholder="nodeID"/>
                </template>
                <template v-else-if="form.protocol === 'bluetooth'">
                  <input v-model="p.characteristicUUID" class="cbx-input" style="width:170px" placeholder="characteristicUUID"/>
                </template>
                <template v-else-if="form.protocol === 'lora'">
                  <input v-model="p.payloadKey" class="cbx-input" style="width:170px" placeholder="上行JSON键 payloadKey"/>
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="form.protocol === 'cellular'">
                  <select v-model="p.kind" class="cbx-select">
                    <option v-for="k in ['signal','csq','rsrp','rsrq','sinr','iccid','imsi','imei','reg','rx_rate','tx_rate']" :key="k">{{ k }}</option>
                  </select>
                </template>
                <input v-model="p.unit" class="cbx-input" style="width:60px" placeholder="单位"/>
                <button class="cbx-op danger" @click="form.properties.splice(i, 1)">✕</button>
              </div>

              <div class="cbx-form-row" style="margin-top:10px">
                <button class="cbx-op primary" @click="dryRun()">生成 YAML 预览</button>
                <button class="cbx-op primary" @click="applyDev()" title="保存到本地 box_devices.json 并立即下发云端 K3s（无需单独保存）">下发到云端</button>
                <span class="cbx-sec-sub" v-if="formErr" style="color:var(--red)">{{ formErr }}</span>
              </div>

              <!-- YAML 预览 -->
              <div v-if="preview" class="cbx-preview">
                <div class="cbx-preview-head">
                  <b>YAML 预览</b>
                  <button class="cbx-op" @click="copyPreview">复制</button>
                </div>
                <pre class="cbx-code">{{ preview }}</pre>
              </div>
            </div>
          </div>
        </div>

        <!-- ==================== 新建模型弹窗（DeviceModel）：顶部工具栏「新建模型」入口 ==================== -->
        <div v-if="modelCreateOpen" class="cbx-mask" @click.self="modelCreateOpen = false">
          <div class="cbx-dialog cbx-dialog-lg">
            <div class="cbx-dialog-head">
              <b>新建模型（DeviceModel）</b>
              <span class="cbx-sec-hint">保存后可在「设备接入」中选择该模型</span>
              <button class="cbx-op danger" @click="modelCreateOpen = false">✕</button>
            </div>
            <div class="cbx-form">
              <div class="cbx-form-row">
                <label>协议</label>
                <select v-model="modelForm.protocol" class="cbx-select">
                  <option value="modbus">Modbus（RTU / TCP）</option>
                  <option value="opcua">OPC-UA</option>
                  <option value="bluetooth">Bluetooth</option>
                  <option value="lora">LoRaWAN（LoRa 网关）</option>
                  <option value="cellular">5G/4G 模块自监控</option>
                </select>
                <label>命名空间</label><input v-model="modelForm.namespace" class="cbx-input" style="width:110px" placeholder="default"/>
              </div>
              <div class="cbx-form-row">
                <label>模型名</label><input v-model="modelForm.modelName" class="cbx-input" placeholder="box-metric-model"/>
                <span class="cbx-sec-sub">模型名 = DeviceModel CRD 的 metadata.name，设备通过它引用</span>
              </div>
              <div class="cbx-sec-head" style="margin-top:8px">
                <b>属性点位</b>
                <button class="cbx-op" @click="addModelProp">＋ 添加</button>
              </div>
              <div v-for="(p, i) in modelForm.properties" :key="i" class="cbx-prop-row">
                <input v-model="p.name" class="cbx-input" style="width:110px" placeholder="属性名"/>
                <select v-model="p.type" class="cbx-select">
                  <option v-for="t in ['float','int','double','string','boolean']" :key="t">{{ t }}</option>
                </select>
                <select v-model="p.accessMode" class="cbx-select">
                  <option value="r">ReadOnly</option><option value="rw">ReadWrite</option>
                </select>
                <template v-if="modelForm.protocol === 'modbus'">
                  <select v-model="p.registerType" class="cbx-select">
                    <option v-for="r in ['holdingRegister','inputRegister','coil','discreteInput']" :key="r">{{ r }}</option>
                  </select>
                  <input v-model.number="p.register" type="number" class="cbx-input" style="width:70px" placeholder="寄存器"/>
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="modelForm.protocol === 'opcua'">
                  <input v-model="p.nodeID" class="cbx-input" style="width:170px" placeholder="nodeID"/>
                </template>
                <template v-else-if="modelForm.protocol === 'bluetooth'">
                  <input v-model="p.characteristicUUID" class="cbx-input" style="width:170px" placeholder="characteristicUUID"/>
                </template>
                <template v-else-if="modelForm.protocol === 'lora'">
                  <input v-model="p.payloadKey" class="cbx-input" style="width:170px" placeholder="上行JSON键 payloadKey"/>
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="modelForm.protocol === 'cellular'">
                  <select v-model="p.kind" class="cbx-select">
                    <option v-for="k in ['signal','csq','rsrp','rsrq','sinr','iccid','imsi','imei','reg','rx_rate','tx_rate']" :key="k">{{ k }}</option>
                  </select>
                </template>
                <input v-model="p.unit" class="cbx-input" style="width:60px" placeholder="单位"/>
                <button class="cbx-op danger" @click="modelForm.properties.splice(i, 1)">✕</button>
              </div>

              <div class="cbx-form-row" style="margin-top:10px">
                <button class="cbx-op primary" @click="modelDryRun()">生成 YAML 预览</button>
                <button class="cbx-op primary" @click="applyModelForm()" title="保存到本地 box_devices.json 并立即下发云端 K3s（无需单独保存）">下发到云端</button>
                <span class="cbx-sec-sub" v-if="modelFormErr" style="color:var(--red)">{{ modelFormErr }}</span>
              </div>

              <!-- YAML 预览 -->
              <div v-if="modelPreview" class="cbx-preview">
                <div class="cbx-preview-head">
                  <b>YAML 预览</b>
                  <button class="cbx-op" @click="copyModelPreview">复制</button>
                </div>
                <pre class="cbx-code">{{ modelPreview }}</pre>
              </div>
            </div>
          </div>
        </div>

    <!-- ==================== Broker 配置弹窗（前端配置化，免手工编辑配置文件） ==================== -->
    <div v-if="boxCfgOpen" class="cbx-mask" @click.self="boxCfgOpen = false">
      <div class="cbx-dialog">
        <div class="cbx-dialog-head">
          <b>云端 Broker 配置</b>
          <button class="cbx-op danger" @click="boxCfgOpen = false">✕</button>
        </div>
        <div class="cbx-form">
          <div class="cbx-form-row">
            <label>Broker 地址</label><input v-model="boxCfg.host" class="cbx-input" style="flex:1" placeholder="127.0.0.1"/>
            <label>端口</label><input v-model.number="boxCfg.port" type="number" class="cbx-input" style="width:90px" placeholder="41883"/>
          </div>
          <div class="cbx-form-row">
            <label>用户名</label><input v-model="boxCfg.username" class="cbx-input" style="flex:1" placeholder="可选"/>
            <label>密码</label><input v-model="boxCfg.password" type="password" class="cbx-input" style="flex:1" placeholder="可选"/>
          </div>
          <p class="cbx-note">保存后立即断开并按新配置重连（热更新），配置持久化到 box_config.json。</p>
          <div class="cbx-form-sep">云端 Agent（数据通道：MQTT cloud/# 推送读 + HTTP 写，替代 SSH）</div>
          <div class="cbx-form-row">
            <label>Agent 端口</label><input v-model.number="boxCfg.agent_port" type="number" class="cbx-input" style="width:90px" placeholder="42083"/>
            <label>Agent Token</label><input v-model="boxCfg.agent_token" class="cbx-input" style="flex:1" placeholder="与云端 install_agent.sh --token 一致"/>
            <label>命名空间</label><input v-model="boxCfg.namespace" class="cbx-input" style="width:110px" placeholder="default"/>
          </div>
          <div class="cbx-form-hint">云端部署 cloud-agent 后填写此处的 Token/端口（安装命令见「一键下发」区块），保存即生效：概览/CRD/日志经 MQTT 长连接实时推送，下发/删除/回写走 HTTP，全程无需 SSH。</div>
          <div class="cbx-form-row">
            <button class="cbx-op primary" :disabled="boxCfgSaving" @click="saveBoxConfig">{{ boxCfgSaving ? '保存中…' : '保存并重连' }}</button>
            <button class="cbx-op" @click="boxCfgOpen = false">取消</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ==================== 盒子 IP 配置弹窗（重启 Mapper 前置条件） ==================== -->
    <div v-if="edgeCfgOpen" class="cbx-mask" @click.self="edgeCfgOpen = false">
      <div class="cbx-dialog">
        <div class="cbx-dialog-head">
          <b>盒子连接配置（{{ edgeCfgBox || '' }}）</b>
          <button class="cbx-op danger" @click="edgeCfgOpen = false">✕</button>
        </div>
        <div class="cbx-form">
          <div class="cbx-form-row">
            <label>盒子 IP</label><input v-model="edgeCfg.host" class="cbx-input" style="flex:1" placeholder="现场可达地址（内网 IP / 跳板机 / frp）"/>
            <label>端口</label><input v-model.number="edgeCfg.port" type="number" class="cbx-input" style="width:90px" placeholder="22"/>
          </div>
          <div class="cbx-form-row">
            <label>用户名</label><input v-model="edgeCfg.user" class="cbx-input" style="flex:1" placeholder="root"/>
            <label>密码</label><input v-model="edgeCfg.password" type="password" class="cbx-input" style="flex:1" placeholder="SSH 密码（或填密钥）"/>
          </div>
          <div class="cbx-form-row">
            <label>密钥</label><input v-model="edgeCfg.key" class="cbx-input" style="flex:1" placeholder="/root/.ssh/id_rsa（可选）"/>
          </div>
          <div class="cbx-form-hint">盒子运行期无直达 IP；此处为部署/现场运维时可达地址（现场内网 / 手机热点 / frp）。<br/>
            IP 为空或 SSH 探测不通时，「重启 Mapper」等 SSH 操作将被拒绝。保存后自动探测连通性。</div>
          <div class="cbx-form-row">
            <button class="cbx-op primary" :disabled="edgeCfgSaving" @click="saveEdgeCfg">{{ edgeCfgSaving ? '保存中…' : '保存并探测' }}</button>
            <button class="cbx-op" :disabled="edgeCfgChecking" @click="checkEdgeCfg()">{{ edgeCfgChecking ? '探测中…' : '∿ 仅探测' }}</button>
            <span v-if="edgeCfgCheckResult" class="cbx-edge-check" :class="{ ok: edgeCfgCheckResult.reachable, bad: !edgeCfgCheckResult.reachable }">
              {{ edgeCfgCheckResult.reachable ? '✓ 可达' : '✗ 不可达' }}
            </span>
            <button class="cbx-op" @click="edgeCfgOpen = false">取消</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ==================== 云端部署应用/模型弹窗 ==================== -->
    <div v-if="appDeployOpen" class="cbx-mask" @click.self="appDeployOpen = false">
      <div class="cbx-dialog">
        <div class="cbx-dialog-head">
          <b>云端部署到盒子（{{ appDeployForm.box }}）</b>
          <button class="cbx-op danger" @click="appDeployOpen = false">✕</button>
        </div>
        <div class="cbx-form">
          <div class="cbx-form-row">
            <label>类型</label>
            <select v-model="appDeployForm.type" class="cbx-input" style="width:150px">
              <option value="service">服务（可运行进程）</option>
              <option value="model">模型（仅存储）</option>
            </select>
            <label>名称</label><input v-model="appDeployForm.name" class="cbx-input" style="flex:1" placeholder="如 carbon-emission-model / predict-svc"/>
          </div>
          <div class="cbx-form-row">
            <label>下载地址</label><input v-model="appDeployForm.url" class="cbx-input" style="flex:1" placeholder="https://…/model.tar.gz 或脚本 URL（盒子侧下载安装）"/>
          </div>
          <div class="cbx-form-row" v-if="appDeployForm.type === 'service'">
            <label>启动命令</label><input v-model="appDeployForm.command" class="cbx-input" style="flex:1" placeholder="如 python3 run.py（相对应用目录，可空=只安装不启动）"/>
          </div>
          <div class="cbx-form-row" v-if="appDeployForm.type === 'service'">
            <label>参数</label><input v-model="appDeployForm.args" class="cbx-input" style="flex:1" placeholder="空格分隔，如 --port 8000"/>
            <label>版本</label><input v-model="appDeployForm.version" class="cbx-input" style="width:110px" placeholder="1.0.0"/>
          </div>
          <div class="cbx-form-hint">指令经云端 Broker 命令主题 <code>cmd/{{ appDeployForm.box }}/deploy</code> 下发，盒子 mapper 订阅执行；<br/>
            执行结果回报 <code>state/{{ appDeployForm.box }}/deploy</code>，运行服务周期上报到卡片。</div>
          <div class="cbx-form-row">
            <button class="cbx-op primary" :disabled="appDeploySaving" @click="doAppDeploy">{{ appDeploySaving ? '下发中…' : '下发部署' }}</button>
            <button class="cbx-op" @click="appDeployOpen = false">取消</button>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- 云端时序历史查询（TDengine） -->
  <CloudHistoryDialog v-if="cloudHistoryDev" :device="cloudHistoryDev" @close="cloudHistoryDev = null" />
</template>

<script setup>
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { useSimStore } from '../stores/sim'
import { api } from '../api/client'
// 云端时序历史查询弹窗（TDengine）：异步分包，点开才加载
const CloudHistoryDialog = defineAsyncComponent(() => import('./CloudHistoryDialog.vue'))

const store = useSimStore()

// ---- 单页布局（设备配置已并入通信拓扑图，无 tab）----
const expanded = reactive({ boxes: true, models: true, devs: true, unmounted: false })
const sideTitle = '资源'
const sideCount = computed(() => `${topoBoxes.value?.length || 0} 盒 · ${mergedModels.value.length} 模型 · ${mergedDevices.value.length} 设备`)

// 合并界面：原「数据概览」+「设备管理」二合一（云端设备关联 / 边缘节点 / twins 实时值 / CloudHub 端口已移除）

// ---- 轮询定时器 ----
// 快慢拆分：数据概览（链路状态/实时读数/消息流）3s，设备配置列表 10s；按当前页签拉取，避免无谓请求
let fastTimer = null
let slowTimer = null
const startPolling = () => {
  stopPolling()
  fastTimer = setInterval(refreshFast, 3000)
  slowTimer = setInterval(refreshSlow, 30000)
}
const stopPolling = () => {
  if (fastTimer) { clearInterval(fastTimer); fastTimer = null }
  if (slowTimer) { clearInterval(slowTimer); slowTimer = null }
}
onMounted(() => {
  restoreTopoPos()
  refreshAll(); loadCloudCfg(); loadAgentStatus(); startPolling(); connectCloudFeed()
  loadEdgeCfgSilent()
  setupTopoLinks()
})
onUnmounted(() => {
  stopPolling(); closeDevRealtime(); disconnectCloudFeed()
  stopTopoLinks()
})

// ---- Tab1 数据概览 ----
const overview = ref({})
async function loadOverview() {
  try {
    overview.value = await api.boxOverview()
    // 把云端状态同步到全局 store，供 App.vue 顶部 view-banner 实时显示
    store.boxCloudSource = overview.value.cloud_source || 'unknown'
  } catch (e) {}
}
const stats = computed(() => (overview.value.broker && overview.value.broker.stats) || {})

// ---- Tab2 设备管理 ----
const devices = ref({ models: [], devices: [] })
const form = reactive({
  protocol: 'modbus',
  modelName: 'box-metric-model',
  deviceName: 'box-device',
  namespace: 'default',
  nodeName: 'edge-node',
  collectCycle: 1000,
  cloudDevice: '',   // 可选：绑定云端识别设备 id（实时匹配优先）
  boundDevice: '',   // 可选：绑定平台流程设备实例 id（关联制：云端读数同步到该仿真设备）
  boundFactor: 1,    // 绑定换算系数：云端原始读数 × factor = 流程设备读数（如 kg/min → t/h 填 0.06）
  comm: { commType: 'serial', slaveID: 1, serialPort: '/dev/ttyS0', baudRate: 9600, parity: 'none', tcpIP: '192.168.1.10', tcpPort: 502 },
  opcua: { url: 'opc.tcp://127.0.0.1:4840', userName: '', password: '' },
  bluetooth: { macAddress: 'AA:BB:CC:DD:EE:FF' },
  lora: { broker: '127.0.0.1', port: 1883, applicationID: '1', devEUI: '', appKey: '', region: 'CN470', dataRate: 'SF7BW125' },
  cellular: { serialPort: '/dev/ttyUSB2', baudRate: 115200, apn: 'cmnet', iface: 'wwan0' },
  properties: [{ name: 'value', type: 'float', accessMode: 'r', registerType: 'holdingRegister', register: 0, scale: 1, unit: '' }],
})
const preview = ref('')
const formErr = ref('')
const createOpen = ref(false)
function openCreate() {
  preview.value = ''
  formErr.value = ''
  form.boundDevice = ''
  form.boundFactor = 1
  form.cloudDevice = ''
  // 一键化：自动生成设备名与同名模型（模型留空即自动创建，无需先建模型）
  form.deviceName = 'box-dev-' + ((devices.value.devices || []).length + 1)
  form.modelName = ''
  // 默认选中第一个 Ready 盒子，避免出现「未识别」选项
  const ready = (overview.value.nodes || []).find((n) => n.ready) || (overview.value.nodes || [])[0]
  if (ready) form.nodeName = ready.name
  loadLinks()
  createOpen.value = true
}
async function loadDevices() { try { devices.value = await api.boxDevices() } catch (e) {} }

// ---- 绑定平台流程设备（关联制：云端识别设备 <-> 仿真设备实例，links.json 持久化）----
// 平台仿真流程设备（store.allDevices：计量设备 + 可调设备），按工序分组供下拉选择
const procGroups = computed(() => {
  const g = {}
  for (const d of store.allDevices) {
    const k = d.unitName || d.unitType || '其他'
    ;(g[k] = g[k] || []).push(d)
  }
  return Object.keys(g).map((k) => ({ unit: k, devices: g[k] }))
})
const boxLinks = ref([])   // [{ cloud_id, local_id }]
async function loadLinks() {
  try { boxLinks.value = (await api.boxLinks()).links || [] } catch (e) { boxLinks.value = [] }
}
// 反查：某盒子设备的云端身份（cloudDevice || name）当前绑定的流程设备 id
function boundLocalOf(d) {
  const cloudId = (d.cloudDevice || d.name || '').trim()
  if (!cloudId) return ''
  const l = boxLinks.value.find((x) => x.cloud_id === cloudId)
  return l ? l.local_id : ''
}
// 反查：某盒子设备当前绑定的读数换算系数（未配置默认 1）
function boundFactorOf(d) {
  const cloudId = (d.cloudDevice || d.name || '').trim()
  if (!cloudId) return 1
  const l = boxLinks.value.find((x) => x.cloud_id === cloudId)
  return l && l.factor != null ? l.factor : 1
}
// 同步绑定：保存/删除设备时建立或解除云端设备 <-> 流程设备关联
async function syncBound(cloudId, localId, factor = 1) {
  cloudId = (cloudId || '').trim()
  if (!cloudId) return
  try {
    if (localId) await api.linkMqttDevice(cloudId, localId, factor)
    else await api.unlinkMqttDevice(cloudId)
    await loadLinks()
  } catch (e) {}
}

// ---- 新建模型（DeviceModel）：顶部工具栏「新建模型」入口，保存后可在设备接入/修改时选择 ----
const modelCreateOpen = ref(false)
const modelPreview = ref('')
const modelFormErr = ref('')
const modelForm = reactive({
  protocol: 'modbus',
  modelName: '',
  namespace: 'default',
  properties: [{ name: 'value', type: 'float', accessMode: 'r', registerType: 'holdingRegister', register: 0, scale: 1, unit: '' }],
})
function openModelCreate() {
  modelPreview.value = ''
  modelFormErr.value = ''
  modelForm.modelName = ''
  modelForm.protocol = 'modbus'
  modelForm.namespace = 'default'
  modelForm.properties.splice(0, modelForm.properties.length, { name: 'value', type: 'float', accessMode: 'r', registerType: 'holdingRegister', register: 0, scale: 1, unit: '' })
  modelCreateOpen.value = true
}
function addModelProp() {
  modelForm.properties.push({
    name: 'prop' + (modelForm.properties.length + 1), type: 'float', accessMode: 'r',
    registerType: 'holdingRegister', register: 0, scale: 1, unit: '',
    payloadKey: '', kind: 'signal', nodeID: '', characteristicUUID: '',
  })
}
function copyModelPreview() { navigator.clipboard?.writeText(modelPreview.value) }
async function modelDryRun() {
  modelFormErr.value = ''
  if (!modelForm.modelName.trim()) { modelFormErr.value = '请输入模型名'; return }
  try {
    const r = await api.boxUpdateModel({ ...modelForm, mode: 'dryRun' })
    modelPreview.value = r.yamls?.model || ''
  } catch (e) { modelFormErr.value = e.message || e }
}
async function saveModel() {
  if (!modelForm.modelName.trim()) { modelFormErr.value = '请输入模型名'; return }
  if (!(modelForm.properties || []).length) { modelFormErr.value = '请至少添加一个属性点位'; return }
  modelFormErr.value = ''
  try {
    const r = await api.boxUpdateModel({ ...modelForm, mode: 'apply' })
    store.toast = `模型已保存：${modelForm.modelName}（可在「设备接入」中选择）`
    await loadDevices()
    modelCreateOpen.value = false
  } catch (e) { modelFormErr.value = e.message || e }
}
// 一键下发模型：保存到本地 box_devices.json 后立即下发云端 K3s（无需单独「保存」）
async function applyModelForm() {
  if (!modelForm.modelName.trim()) { modelFormErr.value = '请输入模型名'; return }
  if (!(modelForm.properties || []).length) { modelFormErr.value = '请至少添加一个属性点位'; return }
  modelFormErr.value = ''
  try {
    await api.boxUpdateModel({ ...modelForm, mode: 'apply' })
    await loadDevices()
    modelCreateOpen.value = false
    await applyDevices('', false, modelForm.modelName)
  } catch (e) { modelFormErr.value = e.message || e }
}
// 新建设备表单：选中模型后带出协议与属性点位（可微调）
function onPickModel() {
  const m = (devices.value.models || []).find((x) => x.name === form.modelName)
  if (!m) return
  form.protocol = m.protocol || form.protocol
  form.properties.splice(0, form.properties.length, ...(m.properties || []).map((p) => ({ ...p })))
}
// ---- 云端已识别设备绑定（一键转平台设备：选云端设备 → 自动采用其设备名，读数同步）----
// 未绑定其它本地设备的云端 CRD 设备列表（当前编辑设备自身持有的不视为占用）
const cloudUnbound = computed(() => {
  const taken = new Set()
  for (const d of devices.value.devices || []) {
    const cid = (d.cloudDevice || '').trim()
    if (!cid) continue
    if (d.name === editForm.deviceName) continue
    taken.add(cid)
  }
  return (cloudCrd.value.devices || []).filter((c) => c.name && !taken.has(c.name))
})
const cloudUnboundGroups = computed(() => {
  const list = cloudUnbound.value
  const on = list.filter((c) => c.state === 'online')
  const off = list.filter((c) => c.state !== 'online')
  const groups = []
  if (on.length) groups.push({ label: '在线', items: on })
  if (off.length) groups.push({ label: '离线', items: off })
  return groups
})
function onPickCloudDevice() {
  if (!form.cloudDevice) return
  // 设备名仍是自动生成占位（box-dev-N）时，直接采用云端设备名 → 一键转为平台设备
  if (/^box-dev-\d+$/.test(form.deviceName || '')) form.deviceName = form.cloudDevice
}
// 修改设备表单：切换模型同样带出协议与属性点位
function onPickEditModel() {
  const m = (devices.value.models || []).find((x) => x.name === editForm.modelName)
  if (!m) return
  editForm.protocol = m.protocol || editForm.protocol
  editForm.properties.splice(0, editForm.properties.length, ...(m.properties || []).map((p) => ({ ...p })))
}

// ---- 云端已下发 CRD（云端 agent 推送读取云端 K3s，对应云端管理台 GET /api/devices）----
const cloudCrd = ref({ models: [], devices: [], error: '' })
const crdLoading = ref(false)
async function loadCloudCrd(force = false) {
  crdLoading.value = true
  try { cloudCrd.value = await api.boxCloudCrd(force) } catch (e) { cloudCrd.value = { models: [], devices: [], error: e.message || String(e) } }
  finally { crdLoading.value = false }
}

// ---- 手动上报 twins（对应云端管理台 POST /api/devices/realtime/ingest）----
const ingestOpen = ref(false)
const ingesting = ref(false)
const ingestMsg = ref('')
const ingestErr = ref(false)
const ingestForm = reactive({ device: '', namespace: 'default', property: 'value', value: '' })
function openIngest(d) {
  ingestForm.device = d.name
  ingestForm.namespace = d.namespace || 'default'
  ingestForm.property = (d.twins && d.twins[0] && d.twins[0].propertyName) || 'value'
  ingestForm.value = ''
  ingestMsg.value = ''
  ingestErr.value = false
  ingestOpen.value = true
}
async function doIngest() {
  ingesting.value = true; ingestErr.value = false; ingestMsg.value = '上报中…'
  try {
    const r = await api.boxIngestDeviceValue(ingestForm.device, ingestForm.namespace, ingestForm.property, ingestForm.value)
    if (r.ok) {
      ingestMsg.value = `已回写云端 twins：${ingestForm.property}=${r.reported}（${r.timestamp}）`
      store.toast = ingestMsg.value
      setTimeout(() => loadCloudCrd(true), 600)
    } else {
      ingestErr.value = true
      ingestMsg.value = r.error || r.stderr || '上报失败'
    }
  } catch (e) { ingestErr.value = true; ingestMsg.value = e.message || String(e) }
  finally { ingesting.value = false }
}

// ---- 一键下发到云端 K3s（云端 agent 本地 kubectl apply，HTTP API + MQTT 数据通道，目标地址复用云端 Broker 配置）----
const cloudCfg = reactive({ host: '' })
const applying = ref(false)
async function loadCloudCfg() {
  try { Object.assign(cloudCfg, await api.boxCloudConfig()) } catch (e) {}
}
// 云端 Agent 数据通道状态（健康检查 + MQTT 推送新鲜度）
const agentStatus = ref(null)
const agentStatusOk = ref(false)
function fmtFresh(ts) {
  if (!ts) return '—'
  const s = Math.floor(Date.now() / 1000 - ts)
  return s < 90 ? `${s}s 前` : `${Math.floor(s / 60)}m 前`
}
async function loadAgentStatus() {
  try {
    const r = await api.boxCloudAgentStatus()
    agentStatus.value = r
    agentStatusOk.value = !!(r && r.ok)
  } catch (e) {}
}
const restartingKey = ref('')
async function restartCloud(payload, label, confirmText) {
  const key = (payload.kind || '') + ':' + (payload.name || '')
  if (restartingKey.value) return
  if (!confirm(confirmText)) return
  restartingKey.value = key
  try {
    const r = await api.boxCloudRestart(payload)
    if (r && r.ok) {
      const msg = ((r.stdout && r.stdout.trim()) || r.info || '成功')
      alert('已触发重启「' + label + '」：' + msg + (r.info ? '\n' + r.info : ''))
      await refreshFast()
      loadAgentStatus()
      setTimeout(() => { loadCloudLogs(); loadAgentStatus() }, 8000)  // 重启完成后二次刷新
    } else {
      alert('重启「' + label + '」失败：' + ((r && (r.stderr || r.error)) || '未知错误'))
    }
  } catch (e) {
    alert('重启请求失败：' + (e.message || e))
  } finally {
    restartingKey.value = ''
  }
}
function restartCloudcore() {
  return restartCloud(
    { kind: 'deployment', name: 'cloudcore', namespace: 'kubeedge' },
    'CloudCore',
    '确认重启云端 kubeedge 命名空间下的 cloudcore 工作负载？\n' +
    '将触发边缘节点重新注册（约 1-2 分钟恢复在线），请确认当前无正在进行的下发操作。'
  )
}
function restartAgent() {
  return restartCloud(
    { kind: 'systemd', name: 'cloud-agent' },
    'cloud-agent',
    '确认重启云端 cloud-agent 服务？\n' +
    '系统会在 2 秒后自动拉起（先返回结果再重启自身），期间平台约数秒无法连接云端 agent。'
  )
}
function restartBroker() {
  return restartCloud(
    { kind: 'systemd', name: 'nengtan-cloud-broker' },
    'MQTT Broker',
    '确认重启云端 MQTT Broker（nengtan-cloud-broker）？\n' +
    '将短暂断开边缘盒子与平台的 MQTT 长连接，约数秒后自动重连，请确认当前无正在进行的下发/上报操作。'
  )
}
function restartMapper(b) {
  if (!edgeIpOk(b)) {
    alert('未配置盒子 IP 或探测不通，无法重启 Mapper。\n请先点击「盒子IP」填写现场可达地址（内网 IP / 跳板机 / frp）并保存。')
    return
  }
  return restartCloud(
    { kind: 'edge', name: 'box-mapper' },
    'box-mapper（' + b.name + '）',
    '确认重启边端盒子「' + b.name + '」的 box-mapper 服务？\n' +
    '云端 agent 将经 SSH 到边缘盒子执行 systemctl restart box-mapper（需已在盒子卡片「盒子IP」配置现场可达地址且探测通过）。\n' +
    '注意：盒子处于现场内网/无直达 IP 时云端 SSH 无法直达，该操作会失败，需现场运维重启。'
  )
}

// ---- 盒子连接配置（IP/SSH 凭据）：重启 Mapper 前置条件，IP 为空或不通则拒绝 ----
const edgeCfgOpen = ref(false)
const edgeCfgBox = ref('')
const edgeCfgSaving = ref(false)
const edgeCfgChecking = ref(false)
const edgeCfgCheckResult = ref(null)
const edgeCfg = reactive({ host: '', port: 22, user: 'root', password: '', key: '' })
async function loadEdgeCfgSilent() {
  // 页面加载时静默拉取已保存的盒子 IP 配置，用于「重启 Mapper」按钮的可用性判断
  try {
    const r = await api.boxEdgeConfig()
    if (r && r.edge) {
      edgeCfg.host = r.edge.host || ''
      edgeCfg.port = r.edge.port || 22
      edgeCfg.user = r.edge.user || 'root'
      edgeCfg.password = r.edge.password || ''
      edgeCfg.key = r.edge.key || ''
      if (edgeCfg.host) checkEdgeCfg(true)
    }
  } catch (e) {}
}
async function openBoxEdgeCfg(b) {
  edgeCfgBox.value = b.name
  edgeCfgCheckResult.value = null
  try {
    const r = await api.boxEdgeConfig()
    if (r && r.edge) {
      edgeCfg.host = r.edge.host || ''
      edgeCfg.port = r.edge.port || 22
      edgeCfg.user = r.edge.user || 'root'
      edgeCfg.password = r.edge.password || ''
      edgeCfg.key = r.edge.key || ''
    }
  } catch (e) {}
  edgeCfgOpen.value = true
  if (edgeCfg.host) checkEdgeCfg(true)
}
async function saveEdgeCfg() {
  edgeCfgSaving.value = true
  try {
    const r = await api.boxEdgeConfigSave({
      host: (edgeCfg.host || '').trim(),
      port: Number(edgeCfg.port) || 22,
      user: (edgeCfg.user || '').trim(),
      password: edgeCfg.password || '',
      key: (edgeCfg.key || '').trim(),
    })
    if (r && r.ok !== false) {
      edgeCfgCheckResult.value = (r.check && r.check.reachable != null) ? { reachable: !!r.check.reachable } : null
      store.toast = edgeCfgCheckResult.value && edgeCfgCheckResult.value.reachable
        ? '盒子 IP 已保存且探测可达'
        : '盒子 IP 已保存（当前探测不可达，重启 Mapper 将被拒绝）'
      edgeCfgOpen.value = false
      loadOverview()
    } else {
      store.toast = '保存失败：' + ((r && r.error) || '未知错误')
    }
  } catch (e) {
    store.toast = '保存失败：' + (e.message || e)
  } finally { edgeCfgSaving.value = false }
}
async function checkEdgeCfg(silent = false) {
  edgeCfgChecking.value = true
  try {
    const r = await api.boxEdgeCheck((edgeCfg.host || '').trim(), Number(edgeCfg.port) || 22)
    edgeCfgCheckResult.value = { reachable: !!(r && r.reachable) }
    if (!silent) {
      store.toast = edgeCfgCheckResult.value.reachable ? '✓ 盒子可达' : '✗ 盒子不可达：' + ((r && r.error) || '')
    }
  } catch (e) {
    edgeCfgCheckResult.value = { reachable: false }
    if (!silent) store.toast = '探测失败：' + (e.message || e)
  } finally { edgeCfgChecking.value = false }
}
function edgeIpOk(b) {
  if (!(edgeCfg.host || '').trim()) return false
  if (edgeCfgCheckResult.value && !edgeCfgCheckResult.value.reachable) return false
  return true
}

// ---- 云端部署应用/模型到盒子（经云端 Broker 命令主题 cmd/{box}/deploy 下发） ----
const appDeployOpen = ref(false)
const appDeploySaving = ref(false)
const appDeployForm = reactive({ box: '', type: 'service', name: '', url: '', command: '', args: '', version: '1.0.0' })
function openAppDeploy(b) {
  appDeployForm.box = b.name
  appDeployForm.type = 'service'
  appDeployForm.name = ''
  appDeployForm.url = ''
  appDeployForm.command = ''
  appDeployForm.args = ''
  appDeployForm.version = '1.0.0'
  appDeployOpen.value = true
}
async function doAppDeploy() {
  const name = (appDeployForm.name || '').trim()
  if (!name) { store.toast = '请填写应用名称'; return }
  if (!(appDeployForm.url || '').trim()) { store.toast = '请填写下载地址'; return }
  appDeploySaving.value = true
  try {
    const r = await api.boxAppCmd({
      box: appDeployForm.box,
      cmd: 'deploy',
      name,
      type: appDeployForm.type,
      url: (appDeployForm.url || '').trim(),
      command: (appDeployForm.command || '').trim(),
      args: (appDeployForm.args || '').split(/\s+/).filter(Boolean),
      version: (appDeployForm.version || '1.0.0').trim(),
    })
    if (r && r.ok !== false) {
      store.toast = '部署指令已下发（盒子执行后回报，卡片将显示运行服务）'
      appDeployOpen.value = false
      setTimeout(() => { loadOverview() }, 3000)
    } else {
      store.toast = '下发失败：' + ((r && r.error) || '未知错误')
    }
  } catch (e) {
    store.toast = '下发失败：' + (e.message || e)
  } finally { appDeploySaving.value = false }
}
async function applyDevices(name = '', dryRun = false, modelName = '') {
  applying.value = true
  try {
    const r = await api.boxApplyDevices(name, dryRun, modelName)
    if (!r.ok) throw new Error((r.error || '') + (r.stderr ? ' ' + r.stderr : ''))
    const list = (r.applied || []).join('、')
    if (dryRun) store.toast = `预览：${list}（未下发）`
    else store.toast = `下发成功：${list}`
    return r
  } catch (e) {
    store.toast = '下发失败：' + (e.message || e)
    throw e
  } finally { applying.value = false }
}
// 拓扑图设备行「⤓ 下发」：单个设备下发，失败仅 toast 提示
async function onApplyOneDev(d) {
  if (applying.value) return
  if (!confirm(`确认将设备「${d.name}」下发到云端 K3s？`)) return
  try { await applyDevices(d.name) } catch (e) { /* 失败已 toast */ }
}

// ---- 云端 Broker 配置（前端配置化，免手工编辑 config/mqtt.yaml）----
const boxCfgOpen = ref(false)
const boxCfgSaving = ref(false)
const boxCfg = reactive({ host: '', port: 41883, username: '', password: '', agent_port: 42083, agent_token: '', namespace: 'default' })
async function openBoxConfig() {
  try {
    const [c, cc] = await Promise.allSettled([api.boxConfig(), api.boxCloudConfig()])
    if (c.status === 'fulfilled') {
      boxCfg.host = c.value.broker.host || ''
      boxCfg.port = c.value.broker.port || 41883
      boxCfg.username = c.value.broker.username || ''
      boxCfg.password = c.value.broker.password || ''
    }
    if (cc.status === 'fulfilled') {
      boxCfg.agent_port = cc.value.agent_port || 42083
      boxCfg.agent_token = cc.value.agent_token || ''
      boxCfg.namespace = cc.value.namespace || 'default'
    }
    boxCfgOpen.value = true
  } catch (e) { store.toast = '加载配置失败：' + (e.message || e) }
}
async function saveBoxConfig() {
  boxCfgSaving.value = true
  try {
    const [r, rc] = await Promise.allSettled([
      api.boxConfigSave({
        broker: {
          host: boxCfg.host, port: Number(boxCfg.port) || 41883,
          username: boxCfg.username, password: boxCfg.password,
        },
      }),
      api.boxCloudConfigSave({
        host: boxCfg.host,
        agent_port: Number(boxCfg.agent_port) || 42083,
        agent_token: boxCfg.agent_token,
        namespace: boxCfg.namespace || 'default',
      }),
    ])
    const ok = r.status === 'fulfilled' && r.value && r.value.ok !== false
    if (ok) {
      store.toast = 'Broker + Agent 配置已保存并热更新'
      boxCfgOpen.value = false
      store.mqttSource = await api.realtimeSource()   // 立即刷新链路状态（含重连结果）
      await loadOverview()
    } else {
      const err = (r.status === 'fulfilled' && r.value && r.value.error) || (r.status === 'rejected' && r.reason && r.reason.message) || ''
      store.toast = '保存失败：' + (err || '请检查配置')
    }
  } catch (e) { store.toast = '保存失败：' + (e.message || e) }
  finally { boxCfgSaving.value = false }
}

function addProp() {
  form.properties.push({
    name: 'prop' + (form.properties.length + 1), type: 'float', accessMode: 'r',
    registerType: 'holdingRegister', register: 0, scale: 1, unit: '',
    payloadKey: '', kind: 'signal', nodeID: '', characteristicUUID: '',
  })
}
async function dryRun() {
  formErr.value = ''
  try {
    // 模型留空 = 自动创建与设备同名的模型（一键化：无需先建模型）
    const r = await api.boxCreateDevice({ ...form, modelName: form.modelName || form.deviceName, mode: 'dryRun' })
    preview.value = r.yamls.model + '\n---\n' + r.yamls.device
  } catch (e) { formErr.value = e.message || e }
}
async function applyDev() {
  formErr.value = ''
  try {
    // 模型留空 = 自动创建与设备同名的模型（一键化：无需先建模型）
    const r = await api.boxCreateDevice({ ...form, modelName: form.modelName || form.deviceName, mode: 'apply' })
    preview.value = r.yamls.model + '\n---\n' + r.yamls.device
    // 绑定流程设备：云端身份（cloudDevice || deviceName）<-> 所选流程设备（含读数换算系数）
    await syncBound(form.cloudDevice || form.deviceName, form.boundDevice, form.boundFactor != null ? form.boundFactor : 1)
    const cs = r.cloud_sync || {}
    // 保存即自动同步云端（后端已下发）
    store.toast = `设备 ${form.deviceName} 已保存` + (cs.ok ? '，已同步云端' : `，云端同步失败：${cs.error || '未知错误'}（本地已保存）`) + (form.boundDevice ? `，已绑定流程设备 ${form.boundDevice}${form.boundFactor !== 1 ? `（读数×${form.boundFactor}）` : ''}` : '')
    await loadDevices()
  } catch (e) { formErr.value = e.message || e }
}
// 仅删除云端 CRD（对应云端管理台 /api/devices/delete；不动本地配置）
async function delCloud(kind, name, namespace) {
  const k = kind === 'devicemodel' ? 'model' : 'device'
  if (!window.confirm(`确认删除云端 CRD「${name}」？`)) return
  try {
    const r = await api.boxDeleteDevice(k, name, namespace, true, false)
    if (r.cloud && r.cloud.ok) store.toast = `云端 CRD 已删除：${name}`
    else store.toast = `删除失败：${(r.cloud && (r.cloud.stderr || r.cloud.error)) || '云端不可达'}`
    await loadCloudCrd(true)
  } catch (e) { store.toast = '删除失败：' + (e.message || e) }
}
async function copyPreview() { try { await navigator.clipboard.writeText(preview.value); store.toast = 'YAML 已复制' } catch (e) {} }

// ---- Tab4 盒子一键接入（自解压脚本：box-deploy 包 + edgecore.yaml + rootCA + token）----
const onboardForm = reactive({ hostname: 'edge-box', cloudIP: '172.19.134.45', boxIP: '' })
const onboardResult = ref(null)
const onboardOpen = ref(false)
const onboardBusy = ref(false)
const remoteRunning = ref(false)
const remoteSteps = ref([])
function openOnboard() {
  onboardResult.value = null
  remoteSteps.value = []
  if (cloudCfg.host) onboardForm.cloudIP = cloudCfg.host
  onboardOpen.value = true
  loadGithubConfig()
}

// ---- GitHub 托管（盒子现场一条 curl 命令接入）----
const ghForm = reactive({ owner: '', repo: '', branch: 'master', token: '' })
const ghResult = ref(null)
const ghBusy = ref(false)
const ghExport = ref(null)
const ghExportBusy = ref(false)
const ghLauncherUrl = computed(() => {
  if (ghResult.value && ghResult.value.launcher_url) return ghResult.value.launcher_url
  if (ghForm.owner && ghForm.repo) return `https://raw.githubusercontent.com/${ghForm.owner}/${ghForm.repo}/${ghForm.branch || 'master'}/onboard/onboard_box.sh`
  return 'https://raw.githubusercontent.com/…/onboard/onboard_box.sh'
})
async function loadGithubConfig() {
  try {
    const r = await api.boxGithubConfig()
    if (r.ok) {
      ghForm.owner = r.owner
      ghForm.repo = r.repo
      ghForm.branch = r.branch || 'master'
    }
  } catch (e) { /* 未配置时静默 */ }
}
async function saveGithubConfig() {
  ghBusy.value = true
  try {
    const r = await api.boxGithubConfigSave({ owner: ghForm.owner, repo: ghForm.repo, branch: ghForm.branch, token: ghForm.token })
    store.toast = r.ok ? 'GitHub 配置已保存' : (r.error || '保存失败')
  } catch (e) { store.toast = '保存失败：' + (e.message || e) }
  finally { ghBusy.value = false }
}
async function syncGithub() {
  ghBusy.value = true
  ghResult.value = null
  try {
    const r = await api.boxGithubPush(onboardForm.cloudIP)
    ghResult.value = r
    store.toast = r.ok ? '已同步到 GitHub：盒子现场可一条命令接入' : ('同步失败：' + (r.error || '见文件状态'))
  } catch (e) { store.toast = '同步失败：' + (e.message || e) }
  finally { ghBusy.value = false }
}
async function exportBoxConfig() {
  ghExportBusy.value = true
  ghExport.value = null
  try {
    const r = await api.boxConfigExport(onboardForm.cloudIP, onboardForm.hostname)
    ghExport.value = r
    store.toast = r.ok ? '已生成 box-config.json：复制内容保存到盒子 /opt/weight-bridge/box-config.json 即可' : (r.error || '导出失败')
  } catch (e) { store.toast = '导出失败：' + (e.message || e) }
  finally { ghExportBusy.value = false }
}
async function doOnboard() {
  onboardBusy.value = true
  try {
    const r = await api.boxOnboard(onboardForm.hostname, onboardForm.cloudIP, onboardForm.boxIP)
    if (!r.ok) { store.toast = r.error || '生成失败'; return }
    onboardResult.value = r
    remoteSteps.value = []
  } catch (e) { store.toast = '生成失败：' + (e.message || e) }
  finally { onboardBusy.value = false }
}
async function downloadOnboardScript() {
  try {
    const r = await api.boxOnboardScript()
    if (!r.ok) { store.toast = r.error || '脚本未生成'; return }
    // base64 -> Blob 落盘（脚本约 18 MB，atob 一次性可接受）
    const bin = atob(r.script_b64)
    const bytes = new Uint8Array(bin.length)
    for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i)
    const blob = new Blob([bytes], { type: 'application/x-shellscript' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = r.script_name || 'onboard_box.sh'
    document.body.appendChild(a); a.click(); a.remove()
    URL.revokeObjectURL(url)
    store.toast = `已下载 ${r.script_name}（${(r.script_size / 1024 / 1024).toFixed(1)} MB）`
  } catch (e) { store.toast = '下载失败：' + (e.message || e) }
}
async function doOnboardRemote() {
  remoteRunning.value = true
  remoteSteps.value = []
  try {
    const r = await api.boxOnboardRemote({
      hostname: onboardForm.hostname,
      cloudIP: onboardForm.cloudIP,
      boxIP: onboardForm.boxIP,
    })
    remoteSteps.value = r.steps || []
    store.toast = r.ok ? '远程一键接入完成：盒子已接入云端' : ('远程一键接入失败：' + (r.error || '见步骤日志'))
  } catch (e) { store.toast = '远程一键接入失败：' + (e.message || e) }
  finally { remoteRunning.value = false }
}
async function copyOnboard() { try { await navigator.clipboard.writeText(onboardResult.value.edgecore); store.toast = 'edgecore.yaml 已复制' } catch (e) {} }

// ---- 实时数据（并入数据概览） ----
const rtDevices = ref([])
// 当前配置（云端 CRD）设备行内联实时数据：按设备名映射 rtDevices（3s 自动刷新）
const cloudRtMap = computed(() => {
  const m = {}
  for (const r of rtDevices.value) m[r.name] = r
  return m
})
function rtOf(d) { return cloudRtMap.value[d.name] || null }
function rtTsOf(d) {
  const r = rtOf(d)
  if (!r) return 0
  let max = 0
  for (const t of r.twins || []) if ((t.timestamp || 0) > max) max = t.timestamp
  return max
}
const messages = ref([])
const pubForm = reactive({ topic: '', payload: '' })
// 云端实时日志：agent 每 3s 经 MQTT cloud/logs 推送 → 平台缓存 → WebSocket /api/ws/cloud 实时转发。
// WS 未连接时回退 HTTP 轮询兜底（读内存缓存，毫秒级）。
const cloudLogs = ref({ lines: [] })
const cloudLogRef = ref(null)
const msgLogRef = ref(null)
const cloudWsState = ref('closed')
let cloudWs = null
let cloudWsRetry = 0
// 日志总保持最新：监听 lines 引用（新日志追加 / WS 快照替换均触发），nextTick 确保 DOM 渲染后再滚到底部
watch(() => cloudLogs.value?.lines, () => {
  const el = cloudLogRef.value
  if (el) nextTick(() => { el.scrollTop = el.scrollHeight })
})
async function loadCloudLogs() {
  try {
    cloudLogs.value = await api.boxCloudLogs()
  } catch (e) {}
}
function connectCloudFeed() {
  if (cloudWs) return
  cloudWs = api.openCloudFeed((msg) => {
    cloudWsRetry = 0
    if (msg.kind === 'snapshot') {
      const d = msg.data || {}
      if (d.logs) cloudLogs.value = d.logs
    } else if (msg.kind === 'logs') {
      const d = msg.data || {}
      const cur = cloudLogs.value || { lines: [] }
      const seen = new Set((cur.lines || []).map(l => l.line))
      const fresh = (d.lines || []).filter(l => l && !seen.has(l.line))
      cloudLogs.value = {
        ok: d.ok !== undefined ? d.ok : cur.ok,
        cloudcore: d.cloudcore || cur.cloudcore,
        error: d.error || '',
        lines: [...(cur.lines || []), ...fresh].slice(-300),
        time: d.ts || Date.now() / 1000,
      }
    }
  }, (st) => {
    cloudWsState.value = st
    if (st === 'closed' || st === 'error') {
      cloudWs = null
      cloudWsRetry += 1
      setTimeout(connectCloudFeed, Math.min(3000 * cloudWsRetry, 15000))  // 断线指数回退重连
    }
  })
}
function disconnectCloudFeed() {
  if (cloudWs) { try { cloudWs.close() } catch (e) {} cloudWs = null }
}
async function loadRealtime() {
  try {
    const r = await api.boxDevicesRealtime()
    rtDevices.value = r.devices || []
  } catch (e) {}
}
async function loadMessages() {
  try {
    const r = await api.boxStats()
    messages.value = r.messages || []
  } catch (e) {}
}
function scrollMsgLog() {
  const el = msgLogRef.value
  if (el) el.scrollTop = el.scrollHeight
}
async function doPublish() {
  if (!pubForm.topic.trim()) { store.toast = '请先填写主题（建议 data/box-xxx/device-xxx 格式，发布后可在上方「实时消息流」看到回显，data/# 会同时刷新设备实时数据）'; return }
  try {
    const r = await api.boxPublish(pubForm.topic, pubForm.payload)
    store.toast = r.ok
      ? (pubForm.topic.trim().startsWith('data/')
          ? `已发布到 ${r.topic} → 见上方「实时消息流」，实时数据已刷新`
          : `已发布到 ${r.topic} → 见上方「实时消息流」`)
      : '发布失败：' + (r.error || '')
    await loadMessages()
    nextTick(scrollMsgLog)
  } catch (e) { store.toast = '发布失败：' + (e.message || e) }
}

async function refreshAll() {
  await Promise.allSettled([loadOverview(), loadDevices(), loadRealtime(), loadMessages(), loadCloudCrd(true)])
}
// 快速轮询（3s）：合并界面无页签切换，统一拉轻量数据；云端 CRD 由 30s 慢轮询承担
async function refreshFast() {
  await loadOverview(); await loadDevices(); await loadRealtime(); await loadMessages()
  if (cloudWsState.value !== 'open') await loadCloudLogs()   // WS 未连上时轮询兜底
}
// 慢轮询（30s，与后端 CRD 缓存对齐）：云端 CRD + 拓扑盒子状态 + Agent 状态
async function refreshSlow() {
  await loadCloudCrd()
  loadOverview()
  loadAgentStatus()
}

// ---- 模型/设备合并列表（本地与云端不再区分身份，同名去重为一条记录）----
// 合并规则：本地记录优先（可编辑、含点位/协议），云端同名记录补在线状态与属性计数
const mergedModels = computed(() => {
  const map = new Map()
  ;(cloudCrd.value.models || []).forEach((m) => map.set(m.name, { ...m, _cloud: true }))
  ;(devices.value.models || []).forEach((m) => {
    const c = map.get(m.name)
    map.set(m.name, { ...m, _cloud: !!c, ...(c ? { property_count: c.property_count } : {}) })
  })
  return [...map.values()]
})
const mergedDevices = computed(() => {
  const map = new Map()
  ;(cloudCrd.value.devices || []).forEach((d) => map.set(d.name, { ...d, _cloud: true }))
  ;(devices.value.devices || []).forEach((d) => {
    const c = map.get(d.name)
    map.set(d.name, { ...d, _cloud: !!c, state: c ? c.state : null })
  })
  return [...map.values()]
})
// 盒子下设备合并（云端真实 + 本地待下发，同名合并，云端优先带状态）
function boxDevices(b) {
  const map = new Map()
  ;(b.cloudDevices || []).forEach((d) => map.set(d.name, { ...d, _cloud: true, state: d.state }))
  ;(b.devices || []).forEach((d) => {
    if (!map.has(d.name)) map.set(d.name, { ...d, _cloud: false, state: null })
  })
  return [...map.values()]
}
// 展示辅助：模型名、属性数、设备状态中文
function modelOf(d) { return d.model || d.modelName || '' }
function modelPropCount(m) {
  if (m.properties && m.properties.length) return m.properties.length
  return m.property_count || 0
}
function devStateZh(d) {
  if (d.state === 'online') return '在线'
  if (d.state === 'offline') return '离线'
  return '待下发'
}
// 设备行点击：已下发云端 → 实时数据；仅本地 → 编辑配置
function onDevClick(d) {
  if (d._cloud) openDevRealtime(d)
  else openEditDev(d)
}
// 云端时序历史（TDengine）：打开历史查询弹窗（四元组从设备 node/name/twins 推导）
const cloudHistoryDev = ref(null)
function openCloudHistory(d) { cloudHistoryDev.value = d }

// ---- 格式化 / 图表 ----
// 仪表无效读数标志码（与后端 mqtt_source._INVALID_READING_VALUES 一致）
const INVALID_READING_VALUES = [-65534, 65534, -65535, 65535, -32768, 32767, -32767]
function isInvalidReading(v) {
  if (v == null || typeof v !== 'number') return false
  return INVALID_READING_VALUES.includes(v)
}
function fmtPrimary(v) {
  if (isInvalidReading(v)) return '无有效数据'
  if (v == null) return '—'
  return typeof v === 'number' ? (Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2)) : String(v)
}
function fmtAgo(epoch) {
  if (!epoch) return ''
  const s = Math.floor(Date.now() / 1000 - epoch)
  if (s < 60) return `${s}s 前`
  if (s < 3600) return `${Math.floor(s / 60)}m 前`
  return `${Math.floor(s / 3600)}h 前`
}
function fmtNum(v) {
  if (v == null) return '—'
  if (typeof v !== 'number') return String(v)
  return v >= 10000 ? (v / 10000).toFixed(1) + 'w' : String(v)
}
function fmtUptime(s) {
  if (!s && s !== 0) return '—'
  s = Number(s)
  const d = Math.floor(s / 86400)
  const h = Math.floor((s % 86400) / 3600)
  const m = Math.floor((s % 3600) / 60)
  return d ? `${d}天${h}小时` : (h ? `${h}小时${m}分` : `${m}分`)
}
function fmtTime(t) {
  if (!t) return ''
  const d = new Date(t * 1000)
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}
const sparkView = '0 0 100 24'
function sparkPoints(hist) {
  if (!hist || hist.length < 2) return ''
  const vals = hist.map((h) => h.v)
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const span = (max - min) || 1
  return vals.map((v, i) => {
    const x = (i / (vals.length - 1)) * 100
    const y = 22 - ((v - min) / span) * 20
    return `${x.toFixed(1)},${y.toFixed(1)}`
  }).join(' ')
}

// ---- Tab2 拓扑图（云端→盒子→设备）----
// 「已下发」判定以「云端 CRD」为权威（设备名存在于云端 CRD），与 MQTT 识别无关。
// MQTT 识别（mqtt_matched）只表示盒子正在上报读数，不代表已下发！
// 云端不可达时无法确认 → 返回 null（未知）。
const crdDeviceNames = computed(() => new Set((cloudCrd.value.devices || []).map((d) => d.name)))
function isDeployed(d) {
  // 本地设备名或云端识别 id（cloudDevice）存在于云端 CRD 均视为已下发：
  // 改名只改本地设备名，云端 CRD 名仍是原 cloudDevice，不能因此误判「待下发」
  if (crdDeviceNames.value.has(d.name)) return true
  if (d.cloudDevice && crdDeviceNames.value.has(d.cloudDevice)) return true
  return cloudCrd.value.error ? null : false
}
// 云端真实设备：按 Device CRD spec.nodeName 真实挂载（权威挂载关系）
// 待下发设备：本地已登记但云端无对应 CRD（未下发/下发失败/云端已删），按本地配置 node 字段挂载
const topoBoxes = computed(() => {
  const nodes = overview.value.nodes || []
  const devs = devices.value.devices || []
  const cloudDevs = (cloudCrd.value.devices || []).map((d) => ({
    ...d,
    primary: (d.twins && d.twins.length && d.twins[0].reported) || '',
  }))
  return nodes.map((n) => ({
    ...n,
    devices: devs.filter((d) => d.node === n.name && !isDeployed(d)),
    cloudDevices: cloudDevs.filter((d) => d.node === n.name),
  }))
})
const topoUnmounted = computed(() => {
  const names = new Set((overview.value.nodes || []).map((n) => n.name))
  return (devices.value.devices || []).filter((d) => !names.has(d.node) && !isDeployed(d))
})
const topoPendingCount = computed(() => (devices.value.devices || []).filter((d) => !isDeployed(d)).length)
// 设备端总览：跨盒子展平（不按盒子分组展示）
const topoAllCloudDevs = computed(() => topoBoxes.value.flatMap((b) => b.cloudDevices))
const topoAllLocalDevs = computed(() => topoBoxes.value.flatMap((b) => b.devices))
// 所有设备实际采集协议集合（去重）
const allDevProtos = computed(() => {
  const set = new Set()
  for (const d of topoAllCloudDevs.value) { const p = protoOfDev(d); if (p) set.add(p) }
  for (const d of topoAllLocalDevs.value) { if (d.protocol) set.add(d.protocol) }
  for (const d of topoUnmounted.value) { if (d.protocol) set.add(d.protocol) }
  return [...set]
})
function devCountOf(nodeName) {
  return (devices.value.devices || []).filter((d) => d.node === nodeName && !isDeployed(d)).length
}
// 协议反查：云端真实设备（无 protocol 字段）通过本地配置按 name / cloudDevice 匹配回真实采集协议
function protoOfDev(dev) {
  if (dev.protocol) return dev.protocol
  const local = (devices.value.devices || []).find((x) => x.name === dev.name || x.cloudDevice === dev.name)
  return (local && local.protocol) || ''
}
// CloudCore Pod 状态统一中文：kubectl 返回的 .status.phase / containerState 原值 → 中文
const PHASE_ZH = {
  Running: '运行中', Pending: '待启动', Succeeded: '已完成', Failed: '失败', Unknown: '未知',
  ContainerCreating: '容器创建中', CrashLoopBackOff: '启动崩溃循环',
  ImagePullBackOff: '镜像拉取失败', ErrImagePull: '镜像拉取错误', Terminating: '终止中',
}
function phaseZh(s) {
  if (!s) return '未知'
  return PHASE_ZH[s] || s
}
// K8s 节点角色统一中文：control-plane/edge/master → 中文
const ROLE_ZH = { edge: '边端', 'control-plane': '控制面', master: '控制面', worker: '工作节点', '<none>': '普通节点' }
function roleZh(r) {
  if (!r || r === '—') return '—'
  return ROLE_ZH[String(r).toLowerCase()] || r
}
// 状态统一中文：online→在线 / offline→离线 / 未知
function stateZh(s) {
  if (s === 'online') return '在线'
  if (s === 'offline') return '离线'
  if (s === 'Ready' || s === 'ready') return '就绪'
  if (s === 'NotReady') return '未就绪'
  if (s === 'unknown' || !s) return '未知'
  return s
}
// 盒子三态中文：true=就绪 / false=未就绪 / null=状态未知（云端数据过期时后端置 null，避免旧缓存冒充实时）
function readyZh(r) {
  if (r === true) return '就绪'
  if (r === false) return '未就绪'
  return '状态未知'
}
function readyOk(r) {
  return r === true
}
// 某盒子下设备的实际采集协议集合（去重，用于连线标签与设备分组动态显示）
function devProtosOf(nodeName) {
  const box = topoBoxes.value.find((b) => b.name === nodeName)
  if (!box) return []
  const set = new Set()
  for (const d of box.cloudDevices) { const p = protoOfDev(d); if (p) set.add(p) }
  for (const d of box.devices) { if (d.protocol) set.add(d.protocol) }
  return [...set]
}

// ---- 通信拓扑图连线：SVG 贝塞尔箭头线锚定到具体模块边缘，标签按实际协议/方法动态显示 ----
const topoCanvasRef = ref(null)
const nodeRefs = {}            // 固定模块（平台/agent/cloudcore/broker/设备端）
const boxNodeRefs = ref({})    // 动态盒子模块（按盒子名）
const links = ref([])          // [{id,d,cls,mk,both,label,lw,lx,ly}]
function setNodeRef(k) {
  return (el) => { if (el) { nodeRefs[k] = el; attachTopoDrag(el, k) } }
}
function setBoxNodeRef(name) {
  return (el) => { if (el) { boxNodeRefs.value[name] = el; attachTopoDrag(el, name) } }
}
// ---- 拓扑图模块手动拖动 + 自动布局 ----
// 拖拽时模块转 absolute（原位放占位块保持列内布局不跳动），松手后位置写入 topoPos 并持久化；
// 「自动布局」清除所有手动位置恢复四列 flex 布局。
const topoPos = ref({})                       // { key: {left, top} }
const TOPO_POS_KEY = 'cbx-topo-pos-v1'
let topoDrag = null                           // 当前拖拽状态

function attachTopoDrag(el, key) {
  if (!el || el.__cbxDragBound) return
  el.__cbxDragBound = true
  el.addEventListener('pointerdown', (e) => onTopoPointerDown(e, key, el))
}

function onTopoPointerDown(e, key, mod) {
  if (e.button !== 0) return
  if (restartingKey.value) return
  const canvas = topoCanvasRef.value
  if (!canvas) return
  const cRect = canvas.getBoundingClientRect()
  const mRect = mod.getBoundingClientRect()
  topoDrag = {
    key, mod, canvas,
    sx: e.clientX, sy: e.clientY,
    startLeft: mRect.left - cRect.left, startTop: mRect.top - cRect.top,
    dx: 0, dy: 0, moved: false, ph: null,
    mv: null, up: null
  }
  const mv = (ev) => onTopoDragMove(ev)
  const up = (ev) => onTopoDragEnd(ev)
  topoDrag.mv = mv; topoDrag.up = up
  window.addEventListener('pointermove', mv)
  window.addEventListener('pointerup', up)
}

function onTopoDragMove(ev) {
  const s = topoDrag
  if (!s) return
  s.dx = ev.clientX - s.sx
  s.dy = ev.clientY - s.sy
  if (!s.moved) {
    if (Math.abs(s.dx) + Math.abs(s.dy) < 4) return   // 位移阈值，避免误拖
    s.moved = true
    // 原位插入占位块，模块转绝对定位，列内其余模块不跳动
    const ph = document.createElement('div')
    ph.className = 'cbx-topo-mod-ph'
    ph.style.width = s.mod.offsetWidth + 'px'
    ph.style.height = s.mod.offsetHeight + 'px'
    s.mod.parentNode.insertBefore(ph, s.mod)
    s.ph = ph
    s.mod.style.position = 'absolute'
    s.mod.style.left = s.startLeft + 'px'
    s.mod.style.top = s.startTop + 'px'
    s.mod.style.zIndex = '50'
    s.mod.classList.add('dragging')
  }
  // 边界约束：模块始终限制在通信拓扑图（canvas）范围内，不超出面板
  const cw = s.canvas.clientWidth
  const ch = s.canvas.clientHeight
  const mw = s.mod.offsetWidth
  const mh = s.mod.offsetHeight
  const left = Math.min(Math.max(s.startLeft + s.dx, 0), Math.max(cw - mw, 0))
  const top = Math.min(Math.max(s.startTop + s.dy, 0), Math.max(ch - mh, 0))
  s.dx = left - s.startLeft
  s.dy = top - s.startTop
  s.mod.style.left = left + 'px'
  s.mod.style.top = top + 'px'
  recalcLinks()   // 连线实时跟随
}

function onTopoDragEnd(ev) {
  const s = topoDrag
  if (!s) return
  topoDrag = null
  window.removeEventListener('pointermove', s.mv)
  window.removeEventListener('pointerup', s.up)
  if (s.ph) s.ph.remove()
  if (s.moved) {
    s.mod.classList.remove('dragging')
    s.mod.style.zIndex = ''
    topoPos.value[s.key] = { left: s.startLeft + s.dx, top: s.startTop + s.dy }
    saveTopoPos()
    // 抑制本次拖拽结束时对内部按钮/设备行的误触发 click
    window.addEventListener('click', (ev2) => { ev2.preventDefault(); ev2.stopPropagation() }, { capture: true, once: true })
    recalcLinks()
  }
}

function saveTopoPos() {
  try { localStorage.setItem(TOPO_POS_KEY, JSON.stringify(topoPos.value)) } catch (e) { /* ignore */ }
}

function restoreTopoPos() {
  try {
    const canvas = topoCanvasRef.value
    if (!canvas) return
    const saved = JSON.parse(localStorage.getItem(TOPO_POS_KEY) || '{}')
    let dirty = false
    Object.keys(saved).forEach((k) => {
      const p = saved[k]
      if (typeof p.left !== 'number' || typeof p.top !== 'number') return
      const el = nodeRefs[k]
      if (!el) return
      // 边界钳制：与拖拽约束一致，模块始终限制在通信拓扑图（canvas）范围内，
      // 避免窗口缩放/更换屏幕后保存的旧位置把模块恢复到画布之外
      const left = clampCoord(p.left, el.offsetWidth, canvas.clientWidth)
      const top = clampCoord(p.top, el.offsetHeight, canvas.clientHeight)
      if (left !== p.left || top !== p.top) dirty = true
      topoPos.value[k] = { left, top }
      const ph = document.createElement('div')
      ph.className = 'cbx-topo-mod-ph'
      ph.style.width = el.offsetWidth + 'px'
      ph.style.height = el.offsetHeight + 'px'
      el.parentNode.insertBefore(ph, el)
      el.style.position = 'absolute'
      el.style.left = left + 'px'
      el.style.top = top + 'px'
    })
    if (dirty) saveTopoPos()
  } catch (e) { /* ignore */ }
}

// 坐标钳制：保证模块不超出画布边界（同拖拽时的约束）
function clampCoord(coord, modSize, canvasSize) {
  return Math.min(Math.max(coord, 0), Math.max(canvasSize - modSize, 0))
}

// 窗口/画布尺寸变化后，对已恢复为 absolute 的模块重新钳制，防止越界到通信拓扑图之外
function clampTopoPositions() {
  const canvas = topoCanvasRef.value
  if (!canvas) return
  Object.keys(topoPos.value).forEach((k) => {
    if (topoDrag && topoDrag.key === k) return   // 拖拽中已有实时约束，跳过
    const el = nodeRefs[k]
    if (!el || el.style.position !== 'absolute') return
    const left = clampCoord(topoPos.value[k].left, el.offsetWidth, canvas.clientWidth)
    const top = clampCoord(topoPos.value[k].top, el.offsetHeight, canvas.clientHeight)
    if (left !== topoPos.value[k].left || top !== topoPos.value[k].top) {
      topoPos.value[k] = { left, top }
      el.style.left = left + 'px'
      el.style.top = top + 'px'
    }
  })
}

function autoLayoutTopo() {
  topoPos.value = {}
  try { localStorage.removeItem(TOPO_POS_KEY) } catch (e) { /* ignore */ }
  document.querySelectorAll('.cbx-topo-mod-ph').forEach((el) => el.remove())
  Object.keys(nodeRefs).forEach((k) => {
    const el = nodeRefs[k]
    if (el) { el.style.position = ''; el.style.left = ''; el.style.top = ''; el.style.zIndex = ''; el.classList.remove('dragging') }
  })
  Object.keys(boxNodeRefs.value).forEach((k) => {
    const el = boxNodeRefs.value[k]
    if (el) { el.style.position = ''; el.style.left = ''; el.style.top = ''; el.style.zIndex = ''; el.classList.remove('dragging') }
  })
  recalcLinks()
}

let topoRo = null
let topoRo2 = null
function recalcLinks() {
  const canvas = topoCanvasRef.value
  if (!canvas) return
  clampTopoPositions()   // 画布尺寸变化时纠正已恢复的模块位置，防止越界
  const cRect = canvas.getBoundingClientRect()
  const R = (el) => {
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { l: r.left - cRect.left, t: r.top - cRect.top, r: r.right - cRect.left, b: r.bottom - cRect.top, w: r.width, h: r.height }
  }
  const defs = []
  const A = R(nodeRefs.n_platform)
  const AG = R(nodeRefs.n_agent)
  const CC = R(nodeRefs.n_cloudcore)
  const BK = R(nodeRefs.n_broker)
  if (A && AG) defs.push({ f: A, t: AG, cls: 'red', mk: 'red', both: false, label: '写 HTTP :42083 · Bearer' })
  if (BK && A) defs.push({ f: BK, t: A, cls: 'green', mk: 'green', both: false, label: '读 MQTT :41883 长连接' })
  if (AG && CC) defs.push({ f: AG, t: CC, cls: 'blue', mk: 'blue', both: false, label: 'kubectl 本地 apply · delete · rollout', vertical: true })
  if (CC && BK) defs.push({ f: CC, t: BK, cls: 'blue', mk: 'blue', both: false, label: 'MQTT 推送 cloud/state · crds · logs', vertical: true })
  const DEVS = R(nodeRefs.n_devs)
  const boxCount = topoBoxes.value.length
  topoBoxes.value.forEach((box, idx) => {
    const B = R(boxNodeRefs.value[box.name])
    if (!CC || !B) return
    defs.push({ f: CC, t: B, cls: 'blue', mk: 'blue', both: true, label: '双向 WebSocket :10002', fyOff: -0.42, tyOff: -0.42 })
    if (BK) defs.push({ f: B, t: BK, cls: 'green', mk: 'green', both: false, label: '上报 MQTT data/#', fyOff: 0.42, tyOff: 0.42 })
    defs.push({ f: CC, t: B, cls: 'blue', mk: 'blue', both: true, label: 'DMI DeviceTwin 同步', fyOff: 0.42, tyOff: 0.42 })
    if (DEVS) {
      // 盒子 → 设备端总览：标注该盒子的真实边缘采集协议（动态），多盒子时在模块左缘按序分散锚点
      const protos = devProtosOf(box.name)
      defs.push({
        f: B, t: DEVS, cls: 'green', mk: 'green', both: false,
        label: protos.length ? '边缘采集 MQTT :1883 · ' + protos.join(' · ') : '边缘采集 MQTT :1883',
        tyOff: boxCount > 1 ? (idx - (boxCount - 1) / 2) * 0.3 : 0,
      })
    }
  })
  links.value = defs.map((l, i) => {
    let x1, y1, x2, y2, d
    if (l.vertical) {
      x1 = l.f.l + l.f.w / 2; y1 = l.f.b
      x2 = l.t.l + l.t.w / 2; y2 = l.t.t
      const dy = Math.max(20, (y2 - y1) / 2)
      d = `M ${x1} ${y1} C ${x1} ${y1 + dy}, ${x2} ${y2 - dy}, ${x2} ${y2}`
    } else {
      const fOff = l.fyOff || 0
      const tOff = l.tyOff || 0
      if (l.f.l < l.t.l) { // 左→右：源右缘 → 目标左缘
        x1 = l.f.r; y1 = l.f.t + l.f.h * (0.5 + fOff)
        x2 = l.t.l; y2 = l.t.t + l.t.h * (0.5 + tOff)
      } else { // 右→左：源左缘 → 目标右缘
        x1 = l.f.l; y1 = l.f.t + l.f.h * (0.5 + fOff)
        x2 = l.t.r; y2 = l.t.t + l.t.h * (0.5 + tOff)
      }
      const dx = Math.max(30, Math.abs(x2 - x1) * 0.45)
      d = `M ${x1} ${y1} C ${x1 + (x2 > x1 ? dx : -dx)} ${y1}, ${x2 + (x2 > x1 ? -dx : dx)} ${y2}, ${x2} ${y2}`
    }
    const mx = (x1 + x2) / 2
    const my = (y1 + y2) / 2
    // 标签始终位于连线中点（text-anchor=middle 水平居中；+3.5 为字号 10px 基线的视觉居中补偿）
    const lx = mx
    const ly = my + 3.5
    return { id: i, d, cls: l.cls, mk: l.mk, both: l.both, label: l.label, lx, ly }
  })
  renderTopoLinks()
}
const SVG_NS = 'http://www.w3.org/2000/svg'
// 原生 DOM 渲染连线（path 箭头线 + 协议标签），不依赖 Vue 响应式，保证每次 recalcLinks 后立即可见
function renderTopoLinks() {
  const canvas = topoCanvasRef.value
  const svg = canvas ? canvas.querySelector('svg.cbx-topo-svg') : null
  if (!svg) return
  svg.querySelectorAll('.cbx-topo-svg-link, .cbx-topo-svg-label').forEach((el) => el.remove())
  // 原生 DOM 创建的 SVG 元素不会被 Vue scoped style 加上 data-v，
  // 因此把核心样式直接内联到元素上；动画与颜色仍由全局 CSS / class 兜底。
  const strokeOf = { red: 'var(--red)', green: 'var(--green)', blue: 'var(--accent)' }
  const frag = document.createDocumentFragment()
  for (const l of links.value) {
    const p = document.createElementNS(SVG_NS, 'path')
    p.setAttribute('d', l.d)
    p.setAttribute('class', 'cbx-topo-svg-link ' + l.cls)
    p.setAttribute('fill', 'none')
    p.setAttribute('stroke', strokeOf[l.cls] || strokeOf.blue)
    p.setAttribute('stroke-width', '2.2')
    p.setAttribute('stroke-linecap', 'round')
    p.setAttribute('stroke-dasharray', '7 4')
    p.setAttribute('opacity', '0.9')
    p.setAttribute('style', 'animation: cbx-topo-flow 1.6s linear infinite')
    if (l.both) p.setAttribute('marker-start', 'url(#tarr-' + l.mk + ')')
    p.setAttribute('marker-end', 'url(#tarr-' + l.mk + ')')
    frag.appendChild(p)
    const g = document.createElementNS(SVG_NS, 'g')
    g.setAttribute('class', 'cbx-topo-svg-label')
    g.setAttribute('transform', 'translate(' + l.lx + ',' + l.ly + ')')
    // 标签仅保留文字：用与面板同色的描边（paint-order）保证虚线上可读，不画背景卡片
    const text = document.createElementNS(SVG_NS, 'text')
    text.setAttribute('x', '0'); text.setAttribute('y', '11')
    text.setAttribute('text-anchor', 'middle')
    text.setAttribute('fill', 'var(--text)')
    text.setAttribute('font-size', '10px')
    text.setAttribute('font-weight', '600')
    text.setAttribute('style', 'paint-order: stroke; stroke: var(--panel); stroke-width: 3px; stroke-linejoin: round')
    text.textContent = l.label
    g.appendChild(text)
    frag.appendChild(g)
  }
  svg.appendChild(frag)
}
watch(topoBoxes, recalcLinks, { deep: true, flush: 'post' })
let topoRetryTimer = null
function setupTopoLinks() {
  // 兜底渲染：首帧模块可能未渲染、数据异步到达盒子才出现——多轮重试直到盒子模块 DOM 就位
  const tryRender = () => {
    recalcLinks()
    const canvas = topoCanvasRef.value
    const boxesReady = canvas && topoBoxes.value.length > 0
      && Object.keys(boxNodeRefs.value).length >= topoBoxes.value.length
    if (boxesReady) {
      if (typeof ResizeObserver !== 'undefined' && !topoRo) {
        topoRo = new ResizeObserver(() => recalcLinks())
        topoRo.observe(canvas)
      }
      if (typeof ResizeObserver !== 'undefined' && !topoRo2) {
        topoRo2 = new ResizeObserver(() => recalcLinks())
        Object.values(boxNodeRefs.value).forEach((el) => el && topoRo2.observe(el))
      }
      return true
    }
    return false
  }
  const retry = (round) => {
    if (tryRender()) return
    if (round >= 6) return   // 兜底约 9.4s 后放弃，后续由 watch(topoBoxes) 继续接管
    topoRetryTimer = setTimeout(() => retry(round + 1), round <= 2 ? 300 : 1800)
  }
  retry(0)
}
function stopTopoLinks() {
  if (topoRetryTimer) { clearTimeout(topoRetryTimer); topoRetryTimer = null }
  if (topoRo) { topoRo.disconnect(); topoRo = null }
  if (topoRo2) { topoRo2.disconnect(); topoRo2 = null }
}

// ---- 修改设备配置（复用 create_device apply 做 upsert，模型同步更新）----
const editOpen = ref(false)
const editTarget = ref('device')   // 'device' | 'model'：编辑对话框操作对象（模型编辑点位对全部引用设备生效）
const editSaving = ref(false)
const editErr = ref(false)
const editMsg = ref('')
const editPreview = ref('')
const editPreviewMode = ref('')
const editForm = reactive({
  protocol: 'modbus', modelName: '', deviceName: '', namespace: 'default',
  nodeName: 'edge-node', collectCycle: 1000, cloudDevice: '', boundDevice: '', boundFactor: 1, origName: '',
  comm: { commType: 'serial', slaveID: 1, serialPort: '/dev/ttyS0', baudRate: 9600, parity: 'none', tcpIP: '192.168.1.10', tcpPort: 502 },
  opcua: { url: 'opc.tcp://127.0.0.1:4840', userName: '', password: '' },
  bluetooth: { macAddress: 'AA:BB:CC:DD:EE:FF' },
  lora: { broker: '127.0.0.1', port: 1883, applicationID: '1', devEUI: '', appKey: '', region: 'CN470', dataRate: 'SF7BW125' },
  cellular: { serialPort: '/dev/ttyUSB2', baudRate: 115200, apn: 'cmnet', iface: 'wwan0' },
  properties: [],
})
async function openEditDev(d) {
  editTarget.value = 'device'
  const src = (devices.value.devices || []).find((x) => x.name === d.name) || d
  const comm = src.comm || {}
  const opcua = src.opcua || {}
  const bt = src.bluetooth || {}
  editErr.value = false
  editMsg.value = ''
  editPreview.value = ''
  editForm.protocol = src.protocol || 'modbus'
  editForm.modelName = src.model || editForm.modelName
  editForm.deviceName = src.name
  editForm.origName = src.name   // 记录原设备名，后端按此移除旧记录（支持改名）
  editForm.namespace = src.namespace || 'default'
  editForm.nodeName = src.node || 'edge-node'
  editForm.collectCycle = src.collectCycle != null ? src.collectCycle : 1000
  editForm.cloudDevice = src.cloudDevice || ''
  editForm.comm.commType = comm.commType || 'serial'
  editForm.comm.slaveID = comm.slaveID != null ? comm.slaveID : 1
  editForm.comm.serialPort = comm.serialPort || '/dev/ttyS0'
  editForm.comm.baudRate = comm.baudRate || 9600
  editForm.comm.parity = comm.parity || 'none'
  editForm.comm.tcpIP = comm.tcpIP || '192.168.1.10'
  editForm.comm.tcpPort = comm.tcpPort || 502
  editForm.opcua.url = opcua.url || 'opc.tcp://127.0.0.1:4840'
  editForm.opcua.userName = opcua.userName || ''
  editForm.opcua.password = opcua.password || ''
  editForm.bluetooth.macAddress = bt.macAddress || 'AA:BB:CC:DD:EE:FF'
  const lora = src.lora || {}
  editForm.lora.broker = lora.broker || '127.0.0.1'
  editForm.lora.port = lora.port != null ? lora.port : 1883
  editForm.lora.applicationID = lora.applicationID || '1'
  editForm.lora.devEUI = lora.devEUI || ''
  editForm.lora.appKey = lora.appKey || ''
  editForm.lora.region = lora.region || 'CN470'
  editForm.lora.dataRate = lora.dataRate || 'SF7BW125'
  const cellular = src.cellular || {}
  editForm.cellular.serialPort = cellular.serialPort || '/dev/ttyUSB2'
  editForm.cellular.baudRate = cellular.baudRate || 115200
  editForm.cellular.apn = cellular.apn || 'cmnet'
  editForm.cellular.iface = cellular.iface || 'wwan0'
  editForm.properties.splice(0, editForm.properties.length, ...(src.properties || []).map((p) => ({ ...p })))
  // 反查该设备当前绑定的流程设备（关联制）与换算系数：先刷新关联列表再回显，避免用旧值导致绑定选择丢失
  await loadLinks()
  editForm.boundDevice = boundLocalOf(src)
  editForm.boundFactor = boundFactorOf(src)
  editOpen.value = true
}
function openEditModel(m) {
  // 模型级编辑：直接修改模型点位，对引用该模型的所有设备同时生效
  const src = (devices.value.models || []).find((x) => x.name === m.name) || m
  editTarget.value = 'model'
  editErr.value = false
  editMsg.value = ''
  editPreview.value = ''
  editForm.protocol = src.protocol || 'modbus'
  editForm.modelName = src.name
  editForm.deviceName = src.name
  editForm.origName = src.name
  editForm.namespace = src.namespace || 'default'
  editForm.nodeName = 'edge-node'
  editForm.collectCycle = 1000
  editForm.cloudDevice = ''
  editForm.properties.splice(0, editForm.properties.length, ...(src.properties || []).map((p) => ({ ...p })))
  editOpen.value = true
}
function addEditProp() {
  editForm.properties.push({
    name: 'prop' + (editForm.properties.length + 1), type: 'float', accessMode: 'r',
    registerType: 'holdingRegister', register: 0, scale: 1, unit: '',
    payloadKey: '', kind: 'signal', nodeID: '', characteristicUUID: '',
  })
}
async function dryRunEdit() {
  editErr.value = false; editMsg.value = ''
  try {
    if (editTarget.value === 'model') {
      const r = await api.boxUpdateModel({ ...editForm, mode: 'dryRun' })
      editPreview.value = r.yamls.model
      editPreviewMode.value = 'dryRun'
      editMsg.value = '已生成模型 YAML 预览（未保存、未下发）'
    } else {
      const r = await api.boxCreateDevice({ ...editForm, mode: 'dryRun' })
      editPreview.value = r.yamls.model + '\n---\n' + r.yamls.device
      editPreviewMode.value = 'dryRun'
      editMsg.value = '已生成预览（未保存、未下发）'
    }
  } catch (e) { editErr.value = true; editMsg.value = e.message || e }
}
async function saveEditModel() {
  editSaving.value = true; editErr.value = false; editMsg.value = '保存中…'
  try {
    const r = await api.boxUpdateModel({ ...editForm, mode: 'apply' })
    const n = (r.synced_devices || []).length
    const cs = r.cloud_sync || {}
    // 保存后后端已自动下发模型 + 引用设备到云端（云端及时同步）
    let tip = `模型已更新：${editForm.modelName}` + (n ? `，同步重刷 ${n} 台设备` : '')
    tip += cs.ok ? '，已同步云端' : `，云端同步失败：${cs.error || '未知错误'}（本地已保存）`
    editMsg.value = tip
    store.toast = `模型配置已更新：${editForm.modelName}` + (cs.ok ? '，已同步云端' : '，云端同步失败')
    await loadDevices()
    editOpen.value = false
  } catch (e) { editErr.value = true; editMsg.value = e.message || e }
  finally { editSaving.value = false }
}
async function saveEditDev() {
  if (editTarget.value === 'model') return saveEditModel()
  editSaving.value = true; editErr.value = false; editMsg.value = '保存中…'
  try {
    const r = await api.boxCreateDevice({ ...editForm, mode: 'apply' })
    const n = (r.synced_devices || []).filter((x) => x !== editForm.deviceName).length
    const renamedFrom = r.renamed_from || ''
    const cs = r.cloud_sync || {}
    // 绑定流程设备：云端身份（cloudDevice || deviceName）<-> 所选流程设备（含读数换算系数）；未选择则解除原绑定
    await syncBound(editForm.cloudDevice || editForm.deviceName, editForm.boundDevice, editForm.boundFactor != null ? editForm.boundFactor : 1)
    // 保存即自动同步云端（后端已下发 + 改名联动删除云端旧 CRD）
    let tip = `已保存：${editForm.deviceName}` + (n ? `，模型点位同步 ${n} 台设备` : '') + (editForm.boundDevice ? `，已绑定流程设备 ${editForm.boundDevice}${editForm.boundFactor !== 1 ? `（读数×${editForm.boundFactor}）` : ''}` : '')
    if (renamedFrom) tip += `（由「${renamedFrom}」改名）`
    tip += cs.ok ? '；已同步云端' : `；云端同步失败：${cs.error || '未知错误'}（本地已保存）`
    editMsg.value = tip
    store.toast = `设备配置已保存：${editForm.deviceName}` + (cs.ok ? '，已同步云端' : '，云端同步失败（本地已保存）')
    await loadDevices()
    editOpen.value = false
  } catch (e) { editErr.value = true; editMsg.value = e.message || e }
  finally { editSaving.value = false }
}
async function applyEditDev() {
  if (editTarget.value === 'model') {
    // 保存模型并下发（后端已自动同步：模型 + 引用它的所有设备一起 apply）
    editSaving.value = true; editErr.value = false; editMsg.value = '保存并下发中…'
    try {
      const r = await api.boxUpdateModel({ ...editForm, mode: 'apply' })
      editPreview.value = ''
      const n = (r.synced_devices || []).length
      const cs = r.cloud_sync || {}
      let tip = `模型已保存并下发：${editForm.modelName}` + (n ? `（同步 ${n} 台设备）` : '')
      if (!cs.ok) tip += `；云端同步失败：${cs.error || '未知错误'}（本地已保存）`
      editMsg.value = tip
      store.toast = tip
      await loadDevices()
      editOpen.value = false
    } catch (e) { editErr.value = true; editMsg.value = e.message || e }
    finally { editSaving.value = false }
    return
  }
  editSaving.value = true; editErr.value = false; editMsg.value = '保存并下发中…'
  try {
    const r = await api.boxCreateDevice({ ...editForm, mode: 'apply' })
    editPreview.value = ''
    const renamedFrom = r.renamed_from || ''
    const cs = r.cloud_sync || {}
    // 绑定流程设备：云端身份（cloudDevice || deviceName）<-> 所选流程设备（含读数换算系数）；未选择则解除原绑定
    await syncBound(editForm.cloudDevice || editForm.deviceName, editForm.boundDevice, editForm.boundFactor != null ? editForm.boundFactor : 1)
    // 后端已自动完成：下发新设备 + 改名联动删除云端旧 CRD（云端及时同步）
    let tip = `已保存并下发：${editForm.deviceName}`
    if (editForm.boundDevice) tip += `，已绑定流程设备 ${editForm.boundDevice}${editForm.boundFactor !== 1 ? `（读数×${editForm.boundFactor}）` : ''}`
    if (renamedFrom) tip += `（由「${renamedFrom}」改名，云端旧设备${cs.ok ? '已删除' : '删除失败'}）`
    if (!cs.ok) tip += `；云端同步失败：${cs.error || '未知错误'}（本地已保存）`
    editMsg.value = tip
    store.toast = tip
    await loadDevices()
    if (renamedFrom && renamedFrom !== editForm.deviceName) await loadCloudCrd(true)
    editOpen.value = false
  } catch (e) { editErr.value = true; editMsg.value = e.message || e }
  finally { editSaving.value = false }
}
async function copyEditYaml() {
  try { await navigator.clipboard.writeText(editPreview.value); store.toast = 'YAML 已复制' } catch (e) {}
}

// ---- 单设备实时数据对话框（3s 轮询，折线图展示）----
const devRtOpen = ref(false)
const devRtName = ref('')
const devRt = computed(() => rtDevices.value.find((x) => x.name === devRtName.value) || null)
const rtSel = ref('')        // 当前选中的属性
const rtHover = ref(-1)      // 悬停采样点 index
const rtChartEl = ref(null)
let rtTimer = null
async function refreshDevRt() {
  try { rtDevices.value = (await api.boxDevicesRealtime()).devices || [] } catch (e) {}
}
function openDevRealtime(d) {
  devRtName.value = d.name
  devRtOpen.value = true
  rtSel.value = ''
  rtHover.value = -1
  refreshDevRt()
  if (rtTimer) clearInterval(rtTimer)
  rtTimer = setInterval(refreshDevRt, 3000)
}
function closeDevRealtime() {
  devRtOpen.value = false
  devRtName.value = ''
  rtHover.value = -1
  if (rtTimer) { clearInterval(rtTimer); rtTimer = null }
}

// ---- 折线图数据与坐标计算 ----
const rtTwins = computed(() => (devRt.value && devRt.value.twins) || [])
// 选中属性：优先用户选择，否则自动取第一个 twins
const rtSelProp = computed(() => {
  if (rtTwins.value.some((t) => t.propertyName === rtSel.value)) return rtSel.value
  return rtTwins.value.length ? rtTwins.value[0].propertyName : ''
})
const rtCur = computed(() => rtTwins.value.find((t) => t.propertyName === rtSelProp.value) || null)
const rtUnit = computed(() => (rtCur.value && rtCur.value.unit) || '')
// 原始历史序列（过滤空值/无效读数）
const rtSeries = computed(() => {
  const hist = (devRt.value && devRt.value.history && devRt.value.history[rtSelProp.value]) || []
  return hist.filter((h) => h.v != null && !isInvalidReading(h.v)).map((h) => ({ t: Number(h.t), v: Number(h.v) }))
})
const rtEmptyMsg = computed(() => {
  if (!rtTwins.value.length) return '该设备暂无上报属性'
  const n = rtSeries.value.length
  if (n === 0) return '该属性暂无趋势数据（设备上线后开始累积）'
  return '趋势数据不足（需至少 2 个采样点）'
})
const rtView = '0 0 900 280'
const rtPlot = { x0: 54, x1: 886, y0: 14, y1: 242 }
function rtScale() {
  const pts = rtSeries.value
  if (!pts.length) return null
  let min = Infinity, max = -Infinity
  for (const p of pts) {
    if (p.v < min) min = p.v
    if (p.v > max) max = p.v
  }
  if (!isFinite(min) || !isFinite(max)) return null
  if (min === max) { min -= 1; max += 1 }
  const pad = (max - min) * 0.12 || 1
  min -= pad; max += pad
  const { x0, x1, y0, y1 } = rtPlot
  const t0 = pts[0].t, t1 = pts[pts.length - 1].t
  const tSpan = (t1 - t0) || 1
  const X = (t) => x0 + ((t - t0) / tSpan) * (x1 - x0)
  const Y = (v) => y1 - ((v - min) / (max - min)) * (y1 - y0)
  return { pts, min, max, X, Y, t0, t1 }
}
const rtPoints = computed(() => {
  const s = rtScale()
  return s ? s.pts.map((p) => ({ x: s.X(p.t), y: s.Y(p.v), t: p.t, v: p.v })) : []
})
const rtLine = computed(() => rtPoints.value.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' '))
const rtArea = computed(() => {
  const ps = rtPoints.value
  if (ps.length < 2) return ''
  const y1 = rtPlot.y1
  return `M${ps[0].x.toFixed(1)},${y1} L${ps.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' L')} L${ps[ps.length - 1].x.toFixed(1)},${y1} Z`
})
function fmtAxisNum(v) {
  if (!isFinite(v)) return ''
  const a = Math.abs(v)
  if (a !== 0 && (a >= 1000 || a < 0.01)) return v.toExponential(1)
  return a >= 100 ? v.toFixed(0) : (a >= 1 ? v.toFixed(2) : v.toFixed(3))
}
const rtYticks = computed(() => {
  const s = rtScale()
  if (!s) return []
  const n = 4
  return Array.from({ length: n + 1 }, (_, i) => {
    const v = s.min + ((s.max - s.min) * i) / n
    return { y: s.Y(v), label: fmtAxisNum(v) }
  })
})
const rtXticks = computed(() => {
  const s = rtScale()
  if (!s) return []
  const t0 = s.t0, t1 = s.t1
  const span = t1 - t0
  const step = Math.max(1, Math.round(span / 3))
  const out = []
  for (let t = t0; t <= t1; t += step) out.push({ x: s.X(t), label: fmtTime(t) })
  const last = out[out.length - 1]
  if (!last || Math.abs(last.x - s.X(t1)) > 2) out.push({ x: s.X(t1), label: fmtTime(t1) })
  return out
})
// 悬停交互
function rtHoverMove(ev) {
  const el = rtChartEl.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  const ps = rtPoints.value
  if (ps.length < 2 || !rect.width) return
  const x = ((ev.clientX - rect.left) / rect.width) * 900
  let best = 0, bestD = Infinity
  for (let i = 0; i < ps.length; i++) {
    const d = Math.abs(ps[i].x - x)
    if (d < bestD) { bestD = d; best = i }
  }
  rtHover.value = best
}
const rtHoverInfo = computed(() => {
  const i = rtHover.value
  const ps = rtPoints.value
  if (i < 0 || !ps[i]) return null
  return { x: ps[i].x, y: ps[i].y, time: fmtTime(ps[i].t), val: fmtPrimary(ps[i].v) }
})
const rtTipStyle = computed(() => {
  const info = rtHoverInfo.value
  if (!info) return {}
  return { left: (info.x / 900) * 100 + '%', top: (info.y / 280) * 100 + '%' }
})

// 关闭视图
const close = () => store.toggleBoxManage()

// 暴露给视图工具栏（RibbonToolbar）：刷新数据 / 盒子接入 / 设备接入 / 新建模型 / 关闭
defineExpose({ refreshAll, close, openOnboard, openCreate, openModelCreate })
</script>

<style scoped>
/* ==================== 能碳一体机管理 · VSCode 风格统一 ==================== */
/* 设计令牌：所有颜色均取全局语义变量（浅色 MATLAB / 深色 sim-dark 主题自动适配），
   透明度统一用 color-mix() 生成，杜绝硬编码色值，保证两套主题观感一致。 */
.cbx-view {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  background: var(--panel-2);
  color: var(--text);
  user-select: none;
  overflow: hidden;
  font-family: var(--ui, -apple-system, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif);
  font-size: 12px; line-height: 1.5;
  -webkit-font-smoothing: antialiased; text-rendering: optimizeLegibility;
}
.cbx-view code, .cbx-view pre { font-family: var(--mono, "Cascadia Code", "JetBrains Mono", Menlo, "SF Mono", Monaco, Consolas, monospace); }
/* ---- 主体 ---- */
.cbx-body { flex: 1 1 auto; padding: 12px 14px; overflow: auto; display: flex; flex-direction: column; gap: 10px; }
.cbx-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; align-items: stretch; }

/* ==================== VSCode 工作台骨架 ==================== */
/* 视图名标识栏（标题 + 云端状态徽章）已上移到 App.vue（Ribbon 工具栏之上），
   工作台内仅承载侧边栏 + 主编辑区 + 底部状态栏 */

/* 工作台主体：侧边栏资源树 + 主编辑区 */
.cbx-workbench { display: flex; flex: 1 1 auto; min-height: 0; }
.cbx-dot { width: 6px; height: 6px; border-radius: 2px; background: var(--faint); flex: none; display: inline-block; }
.cbx-dot.on { background: var(--green); }
/* 侧边栏（Sidebar）：树形资源导航 */
.cbx-sidebar {
  display: flex; flex-direction: column; flex: none;
  width: 250px; min-width: 210px; max-width: 320px;
  background: var(--panel-2);
  border-right: 1px solid var(--border);
  overflow: hidden;
}
.cbx-side-head {
  display: flex; align-items: center; gap: 6px; flex: none;
  padding: 6px 10px; font-size: 11px; text-transform: uppercase; letter-spacing: .6px;
  color: var(--muted); border-bottom: 1px solid var(--border);
}
.cbx-side-count { margin-left: auto; font-size: 10px; color: var(--faint); font-variant-numeric: tabular-nums; }
.cbx-side-body { flex: 1 1 auto; overflow: auto; padding: 6px 0 12px; }
/* 树节点 */
.cbx-tree-sec {
  display: flex; align-items: center; gap: 5px;
  padding: 5px 10px; font-size: 11px; font-weight: 600; color: var(--text);
  cursor: pointer; user-select: none; white-space: nowrap;
}
.cbx-tree-sec:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.cbx-tree-arrow { font-size: 9px; color: var(--faint); width: 10px; flex: none; }
.cbx-tree-count { margin-left: auto; font-size: 10px; color: var(--faint); font-variant-numeric: tabular-nums; }
.cbx-tree-children { padding-left: 8px; }
.cbx-tree-node { margin: 0; }
.cbx-tree-row {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px 4px 16px; font-size: 11.5px; cursor: pointer;
  color: var(--text); white-space: nowrap;
}
.cbx-tree-row:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.cbx-tree-label { overflow: hidden; text-overflow: ellipsis; min-width: 0; }
.cbx-tree-tag {
  margin-left: auto; flex: none; font-size: 9px; padding: 0;
  color: var(--faint); white-space: nowrap;
}
.cbx-tree-tag.ok { color: var(--green); }
.cbx-tree-leaf {
  display: flex; align-items: center; gap: 5px;
  padding: 4px 10px 4px 26px; font-size: 11.5px; cursor: pointer;
  color: var(--text); white-space: nowrap;
}
.cbx-tree-leaf:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.cbx-tree-leaf .cbx-tree-label { flex: 1; }
.cbx-tree-empty { padding: 6px 26px; font-size: 10.5px; color: var(--faint); }
/* 区块头部工具按钮（flex 撑开） */
.cbx-sec-spacer { flex: 1 1 auto; }

/* 主编辑区：标签页条 + 内容 */
.cbx-main { display: flex; flex-direction: column; flex: 1 1 auto; min-width: 0; background: var(--panel-2); }
.cbx-tabs {
  display: flex; align-items: stretch; flex: none;
  height: 33px; padding: 0 6px;
  background: var(--bar, var(--panel-3));
  border-bottom: 1px solid var(--border);
  gap: 2px; overflow-x: auto;
}
.cbx-tab {
  display: flex; align-items: center; flex: none;
  padding: 0 14px; font-size: 11.5px; color: var(--muted);
  cursor: pointer; user-select: none; white-space: nowrap;
  border-top: 1px solid transparent;
  position: relative;
  transition: background .12s, color .12s;
}
.cbx-tab:hover { color: var(--text); }
.cbx-tab.active {
  background: var(--panel-2); color: var(--text);
  border-top: 2px solid var(--accent);
}
.cbx-tab-grow { flex: 1 1 auto; }
.cbx-editor { flex: 1 1 auto; overflow: hidden; position: relative; }
.cbx-page {
  position: absolute; inset: 0; overflow: auto;
  padding: 12px 14px; display: flex; flex-direction: column; gap: 10px;
}

/* ---- 资源列表（拓扑图下方：盒子 / 模型 / 设备三列并排） ---- */
.cbx-reslist { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.cbx-rescol { display: flex; flex-direction: column; min-width: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--panel-1, transparent); }
.cbx-rescol-head { display: flex; align-items: center; gap: 6px; font-size: 11.5px; font-weight: 700; color: var(--text); padding: 8px 10px; background: var(--bar, var(--panel-3)); border-bottom: 1px solid var(--border); }
.cbx-rescol-n { margin-left: auto; font-size: 10.5px; font-weight: 500; color: var(--faint); }
.cbx-rescol-body { display: flex; flex-direction: column; max-height: 248px; overflow-y: auto; }
.cbx-resrow { display: flex; align-items: center; gap: 6px; padding: 6px 10px; font-size: 12px; cursor: pointer; }
.cbx-resrow:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.cbx-resrow + .cbx-resrow { border-top: 1px dashed var(--border); }
.cbx-res-name { flex: 0 1 auto; font-weight: 600; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cbx-res-tag { flex: none; font-size: 10px; padding: 0; color: var(--faint); }
.cbx-res-tag.ok { color: var(--green); }
.cbx-res-tag.err { color: var(--red); }
.cbx-res-tag.local { color: var(--accent); }
.cbx-res-sub { flex: 1 1 auto; min-width: 0; font-size: 10.5px; color: var(--faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; text-align: right; }
.cbx-res-ops { display: inline-flex; gap: 2px; flex: none; }
.cbx-res-ops .cbx-op.cbx-tiny { padding: 1px 5px; font-size: 9px; min-height: 16px; }
.cbx-res-empty { padding: 14px 10px; font-size: 11px; color: var(--faint); text-align: center; }

/* 状态栏（Status Bar）：底部细条，左侧状态 + 右侧信息 */
.cbx-statusbar {
  display: flex; align-items: center; gap: 14px; flex: none;
  height: 24px; padding: 0 10px;
  background: var(--bar, var(--panel-3));
  border-top: 1px solid var(--border);
  font-size: 10.5px; color: var(--muted);
}
.cbx-statusbar .cbx-st-item { display: inline-flex; align-items: center; gap: 5px; white-space: nowrap; }
.cbx-statusbar .cbx-st-grow { flex: 1 1 auto; }
/* ---- 工具栏（VSCode 命令条） ---- */
.cbx-toolbar {
  display: flex; align-items: center; gap: 6px; padding: 5px 10px;
  background: var(--bar, var(--panel)); border: 1px solid var(--border); border-radius: 3px;
  flex-wrap: wrap; font-size: 11px;
}
.cbx-toolbar-title { font-size: 12px; font-weight: 600; letter-spacing: .2px; padding-right: 4px; }
.cbx-toolbar-sep { width: 1px; height: 16px; background: var(--border); margin: 0 2px; }
.cbx-toolbar-msg { margin-left: auto; font-size: 10px; color: var(--muted); }
/* ---- 面板（VSCode 风格：方角 + 标题分隔线 + 统一标题字号） ---- */
.cbx-sec { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 10px 12px; }
.cbx-sec-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
.cbx-sec-head b { font-size: 12px; font-weight: 600; flex: none; letter-spacing: .2px; }
.cbx-sec-head .cbx-op { margin-left: auto; }
.cbx-sec-head .cbx-tag { margin-left: auto; }
.cbx-sec-sub { color: var(--muted); font-size: 10px; }
.cbx-sec-hint { margin-left: auto; font-size: 10px; color: var(--muted); }
.cbx-deploy-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 6px 10px; margin-bottom: 8px;
  background: var(--panel-2); border: 1px dashed var(--border); border-radius: 3px; font-size: 11px;
  position: relative; /* 作为 YAML 预览浮层的定位锚点 */
}
.cbx-deploy-title { font-weight: 600; color: var(--muted); flex: none; }
.cbx-deploy-msg { color: var(--green); font-size: 10.5px; max-width: 340px; word-break: break-all; }
/* ---- 输入控件（VSCode 输入框：圆角 2px + 聚焦蓝环） ---- */
.cbx-input {
  border: 1px solid var(--border); border-radius: 2px; background: var(--panel-2);
  color: var(--text); font-size: 11px; padding: 4px 8px; outline: none;
  transition: border-color .12s, box-shadow .12s;
}
.cbx-input:focus { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.cbx-input::placeholder { color: var(--faint); }
.cbx-select {
  border: 1px solid var(--border); border-radius: 2px; background: var(--panel);
  color: var(--text); font-size: 11px; padding: 3px 6px; outline: none; max-width: 240px;
  transition: border-color .12s, box-shadow .12s;
}
.cbx-select:focus { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.cbx-input.cbx-xs { width: 52px; }
.cbx-input.cbx-sm { width: 110px; }
.cbx-input.cbx-md { width: 230px; }
/* ---- YAML 预览（浮层展示，不撑高模块高度；深色代码区，VSCode 编辑器观感） ---- */
.cbx-yaml-wrap {
  position: absolute; top: calc(100% + 8px); left: 0; right: 0; z-index: 30;
  display: flex; flex-direction: column;
  border: 1px solid var(--border); border-radius: 3px; overflow: hidden;
  box-shadow: 0 8px 24px color-mix(in srgb, #000 40%, transparent);
}
.cbx-yaml-head {
  display: flex; align-items: center; justify-content: space-between; padding: 6px 10px;
  background: var(--panel-3, var(--panel-2)); font-size: 11.5px; border-bottom: 1px solid var(--border);
}
.cbx-yaml-tools { display: flex; gap: 6px; }
.cbx-yaml {
  margin: 0; padding: 10px 12px; max-height: 260px; overflow: auto; flex: 1 1 auto;
  background: var(--rail, #1a212b); color: #d7e0ea;
  font: 11px/1.6 var(--mono, "Cascadia Code", Menlo, monospace); white-space: pre;
}
/* ---- 标签（VSCode badge 风格，语义色跟随主题） ---- */
.cbx-tag {
  font-size: 9.5px; color: var(--muted);
  border: 1px solid var(--border); border-radius: 2px; padding: 1px 7px; letter-spacing: .2px;
}
.cbx-tag.ok { color: var(--green); border-color: color-mix(in srgb, var(--green) 45%, var(--border)); }
.cbx-tag.warn { color: var(--yellow); border-color: color-mix(in srgb, var(--yellow) 45%, var(--border)); }
.cbx-tag.err { color: var(--red); border-color: color-mix(in srgb, var(--red) 45%, var(--border)); }
.cbx-empty-td { text-align: center; color: var(--muted); padding: 14px 0; font-size: 11px; }
/* ---- 状态横幅 ---- */
.cbx-banner {
  font-size: 11px; padding: 6px 10px; line-height: 1.6; display: flex; align-items: center; gap: 6px;
  background: var(--panel-2); border: 1px solid var(--border); border-left-width: 3px;
}
.cbx-banner.err { border-left-color: var(--red); color: var(--red); }
.cbx-banner.warn { border-left-color: var(--yellow); color: var(--yellow); }
/* ---- KV ---- */
.cbx-kv { display: flex; flex-direction: column; gap: 6px; }
.cbx-kv > div { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.cbx-kv span { color: var(--muted); width: 110px; flex: none; }
.cbx-kv code {
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px;
  padding: 1px 6px; font-size: 10px; color: var(--accent2);
}
.cbx-kv code.wrap { word-break: break-all; }
.cbx-kv b.ok { color: var(--green); }

/* ---- 表格（VSCode 树视图风格：统一行高、hover 高亮、无网格竖线） ---- */
.cbx-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.cbx-table th, .cbx-table td {
  text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border);
  vertical-align: middle; font-variant-numeric: tabular-nums;
}
.cbx-table th {
  color: var(--muted); font-weight: 600; font-size: 10px; white-space: nowrap;
  background: var(--panel-3, var(--panel-2)); letter-spacing: .3px;
}
.cbx-table tbody tr { transition: background .1s; }
.cbx-table tbody tr:hover td { background: var(--accent-l); }
.cbx-table tbody tr:last-child td { border-bottom: none; }
.cbx-table td code {
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px;
  padding: 0 5px; font-size: 10px; color: var(--accent2);
}
.cbx-table td.val { color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums; }
.cbx-invalid { color: var(--yellow) !important; font-style: italic; font-weight: 500; }
.cbx-empty-td { text-align: center; color: var(--faint); padding: 18px !important; font-size: 11px; }
/* 状态圆点：默认红色（未下发/离线），on 为绿色（在线/已下发） */
.cbx-dot {
  display: inline-block; width: 6px; height: 6px; border-radius: 2px;
  background: var(--faint); margin-right: 6px; vertical-align: 1px; flex: none;
}
.cbx-dot.on { background: var(--green); }
/* 总览页云端状态全局提示条（云端不可达/部分异常时展示一次，避免各区块重复提示） */
.cbx-banner { margin-bottom: 10px; }
.cbx-op-disabled { opacity: .55; cursor: default; }
.cbx-empty {
  font-size: 11px; color: var(--faint); background: var(--panel-2);
  border: 1px dashed var(--border); border-radius: 4px; padding: 16px; line-height: 1.7; text-align: center;
}
/* ---- 本地/云端配置：等高 + 分页（每页 5 条）+ 数据行固定等高 + 分页贴底 ----
     条目不足 5 条时不撑满高度，按实际条数高度显示 */
.cbx-dev-grid .cbx-sec { position: relative; display: flex; flex-direction: column; }
.cbx-cloud-sec { display: flex; flex-direction: column; overflow: hidden; }
.cbx-dev-grid .cbx-sec .cbx-table, .cbx-cloud-sec .cbx-table { flex: 1 1 auto; min-height: 0; margin-bottom: 0; }
.cbx-cloud-sec .cbx-empty { flex: 1 1 auto; display: flex; align-items: center; justify-content: center; margin: 0; }
/* 固定数据行高度：翻页时行高一致、模块高度稳定，内容超出行宽自动截断 */
.cbx-dev-grid .cbx-table th, .cbx-dev-grid .cbx-table td { padding: 0 10px; height: 28px; overflow: hidden; }
.cbx-dev-grid .cbx-table .cbx-empty-td { height: auto; overflow: visible; }
.cbx-pager { display: flex; align-items: center; justify-content: center; gap: 12px; padding-top: 8px; margin-top: auto; border-top: 1px dashed var(--border); flex: none; }
.cbx-pager .cbx-page-num { font-size: 10.5px; color: var(--muted); font-variant-numeric: tabular-nums; }
.cbx-pager .cbx-op:disabled { opacity: .35; cursor: not-allowed; }
/* ---- 关联管理 ---- */
.cbx-note { font-size: 10.5px; color: var(--muted); line-height: 1.7; margin-bottom: 8px; }
.cbx-note b { color: var(--text); }
.cbx-group { margin-bottom: 10px; }
.cbx-group:last-child { margin-bottom: 0; }
.cbx-group-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 6px;
  font-size: 11px; color: var(--accent2); font-weight: 600; letter-spacing: .2px;
}
.cbx-group-box { background: var(--accent-l); border-radius: 4px; padding: 1px 8px; }
.cbx-group-count { font-size: 10px; color: var(--faint); font-weight: 400; }
.cbx-row {
  display: flex; align-items: center; gap: 8px; padding: 6px 10px; border-radius: 3px;
  background: var(--panel-2); border: 1px solid var(--border); font-size: 11px; margin-bottom: 6px; flex-wrap: wrap;
  transition: border-color .12s, background .12s;
}
.cbx-row:hover { border-color: var(--muted); }
.cbx-row.linked { border-color: color-mix(in srgb, var(--green) 45%, transparent); background: color-mix(in srgb, var(--green) 8%, transparent); }
.cbx-dev { display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1 1 auto; flex-wrap: wrap; }
.cbx-dev-id { font-weight: 600; color: var(--text); }
.cbx-dev-val { color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums; }
.cbx-dev-fields { font-size: 9.5px; color: var(--muted); background: var(--panel); border: 1px solid var(--border); border-radius: 3px; padding: 0 6px; }
.cbx-dev-seen { font-size: 9.5px; color: var(--faint); }
.cbx-arrow { color: var(--faint); }
.cbx-local { color: var(--accent); font-weight: 600; }
/* ---- 表单 ---- */
.cbx-form { display: flex; flex-direction: column; gap: 8px; }
.cbx-form-row { display: flex; align-items: center; gap: 8px; font-size: 11px; flex-wrap: wrap; }
.cbx-form-row label { color: var(--muted); flex: none; }
.cbx-form-sep {
  margin: 4px 0 2px; padding: 4px 8px; font-size: 10.5px; color: var(--accent);
  background: color-mix(in srgb, var(--accent) 8%, transparent);
  border-left: 2px solid var(--accent); border-radius: 2px;
}
.cbx-form-hint { font-size: 10px; color: var(--faint); line-height: 1.5; margin: 2px 0 6px; }
.cbx-agent-bar {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap; font-size: 10.5px;
  margin: 2px 0 6px; padding: 5px 8px; border-radius: 3px;
  background: color-mix(in srgb, var(--red, #e5484d) 8%, transparent);
  border: 1px dashed color-mix(in srgb, var(--red, #e5484d) 35%, transparent);
}
.cbx-agent-bar.ok {
  background: color-mix(in srgb, var(--ok, #30a46c) 8%, transparent);
  border-color: color-mix(in srgb, var(--ok, #30a46c) 30%, transparent);
}
.cbx-prop-row {
  display: flex; align-items: center; gap: 6px; padding: 5px 8px; margin-bottom: 5px;
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px; flex-wrap: wrap;
}
/* ---- 按钮（VSCode 风格：次级 outline、主按钮 accent 底、危险按钮红、xs 小号） ---- */
.cbx-op {
  display: inline-flex; align-items: center; justify-content: center; gap: 4px;
  font-family: var(--ui, -apple-system, "Segoe UI", "PingFang SC", sans-serif);
  font-size: 11px; line-height: 1; font-weight: 400;
  color: var(--text); background: var(--panel-2);
  border: 1px solid var(--border); border-radius: 2px;
  padding: 5px 12px; min-height: 24px; cursor: pointer; flex: 0 0 auto;
  white-space: nowrap; user-select: none;
  transition: background .12s, border-color .12s, color .12s, box-shadow .12s;
}
.cbx-op:hover:not(:disabled) { background: var(--panel-3, var(--panel)); border-color: var(--muted); color: var(--text); }
.cbx-op:active:not(:disabled) { background: var(--sel); }
.cbx-op:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
.cbx-op:disabled { opacity: .4; cursor: not-allowed; }
.cbx-op.primary { color: #fff; background: var(--accent); border-color: var(--accent); font-weight: 500; }
.cbx-op.primary:hover:not(:disabled) { background: var(--accent-d); border-color: var(--accent-d); color: #fff; }
.cbx-op.danger {
  color: var(--red);
  background: color-mix(in srgb, var(--red) 8%, transparent);
  border-color: color-mix(in srgb, var(--red) 35%, transparent);
}
.cbx-op.danger:hover:not(:disabled) { background: color-mix(in srgb, var(--red) 15%, transparent); border-color: var(--red); color: var(--red); }
.cbx-op.cbx-xs { padding: 3px 8px; font-size: 10px; min-height: 20px; }
/* 图标按钮（VSCode 工具栏风格：无边框、hover 底色、线性图标居中） */
.cbx-op.cbx-ic {
  display: inline-flex; align-items: center; justify-content: center;
  width: 24px; height: 22px; padding: 0; flex: none;
  color: var(--text);
  background: transparent; border: none; border-radius: 3px;
}
.cbx-op.cbx-ic:hover:not(:disabled) { background: color-mix(in srgb, var(--text) 10%, transparent); }
.cbx-op.cbx-ic:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
.cbx-op.cbx-ic:disabled { opacity: .4; }
.cbx-op.cbx-ic .cbx-ico { font-size: 14px; line-height: 1; }
.cbx-op.danger.cbx-ic:hover:not(:disabled) { background: color-mix(in srgb, var(--red) 14%, transparent); }
/* 表格操作列连续按钮间距 */
.cbx-table td .cbx-op + .cbx-op { margin-left: 2px; }

/* ---- YAML / 代码块（深色编辑器观感） ---- */
.cbx-preview { margin-top: 10px; }
.cbx-preview-head { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.cbx-preview-head b { font-size: 11px; color: var(--muted); }
.cbx-code {
  background: var(--rail, #1a212b); border: 1px solid var(--border); border-radius: 4px;
  color: #c8d6e5; font-size: 10px; line-height: 1.6; padding: 10px 12px;
  overflow: auto; max-height: 300px; white-space: pre;
}
/* ---- 盒子一键接入 ---- */
.cbx-onboard { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }
.cbx-onboard-actions { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.cbx-remote-steps { display: flex; flex-direction: column; gap: 6px; }
.cbx-remote-step { border: 1px solid var(--border); border-radius: 4px; background: var(--panel-2); padding: 6px 10px; }
.cbx-remote-step b.ok { color: #34c759; }
.cbx-remote-step b.fail { color: #ff453a; }
.cbx-details { border: 1px solid var(--border); border-radius: 4px; background: var(--panel-2); padding: 6px 10px; }
.cbx-details summary { cursor: pointer; color: var(--muted); font-size: 11px; user-select: none; }
/* ---- 实时数据 ---- */
.cbx-twin-card {
  border: 1px solid var(--border); border-radius: 4px; background: var(--panel-2);
  margin-bottom: 10px; padding: 8px 10px;
}
.cbx-twin-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.cbx-twin-head b { font-size: 12px; }
.cbx-twin-head code { color: var(--accent2); }
.cbx-spark { width: 100px; height: 24px; }
.cbx-spark-cell { width: 110px; }
.cbx-faint { color: var(--faint); }
/* ---- 消息流（VSCode 输出面板 / 终端风格） ---- */
/* 日志区背景固定深色终端风格，文字一律用浅色（不随主题），避免亮色主题下深字深底看不清 */
.cbx-msglog {
  display: flex; flex-direction: column; gap: 2px;
  max-height: 220px; overflow: auto; background: #141a22;
  border: 1px solid var(--border); border-radius: 3px; padding: 6px 8px;
  color: #cdd5df;
}
.cbx-msgrow { display: flex; align-items: center; gap: 8px; font-size: 10px; padding: 1px 4px; border-radius: 2px; color: #cdd5df; }
.cbx-msgrow:hover { background: rgba(255,255,255,.07); }
.cbx-msgtime { color: #7f8b99; flex: none; font-variant-numeric: tabular-nums; }
.cbx-msg-topic {
  flex: none; color: #7ab8ff; background: rgba(122,184,255,.12);
  border: 1px solid rgba(122,184,255,.3); border-radius: 3px; padding: 0 5px;
}
.cbx-msg-payload { color: #cdd5df; opacity: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cbx-cloudlog { max-height: 300px; }
.cbx-cloudline {
  flex: 1; color: #e2e8f0; opacity: 1; font-family: var(--mono, ui-monospace, SFMono-Regular, Menlo, Consolas, monospace);
  white-space: pre-wrap; word-break: break-all; overflow-wrap: anywhere;
}
/* ---- 接入指引 ---- */
.cbx-guide-flow { display: flex; align-items: stretch; gap: 10px; margin: 8px 0; flex-wrap: wrap; }
.cbx-flow-node {
  flex: 1 1 0; min-width: 130px; text-align: center; font-size: 11.5px; font-weight: 600;
  background: var(--accent-l); border: 1px solid color-mix(in srgb, var(--accent) 25%, transparent);
  border-radius: 4px; padding: 10px 8px;
}
.cbx-flow-node span { display: block; font-size: 9.5px; color: var(--muted); font-weight: 400; margin-top: 4px; }
.cbx-flow-arrow { display: flex; align-items: center; color: var(--faint); font-size: 16px; }
/* ---- 徽章 / 标签（语义色跟随主题） ---- */
.cbx-badge {
  display: inline-block; font-size: 9.5px; border-radius: 3px; padding: 1px 6px;
  font-weight: 600; letter-spacing: .2px; vertical-align: 1px;
}
.cbx-badge.model { color: var(--yellow); background: color-mix(in srgb, var(--yellow) 12%, transparent); }
.cbx-badge.device { color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, transparent); }
.cbx-twin-chip {
  display: inline-block; font-size: 10px; color: var(--accent);
  background: color-mix(in srgb, var(--accent) 10%, transparent); border-radius: 3px;
  padding: 1px 6px; margin: 1px 3px 1px 0; cursor: pointer; transition: background .1s;
}
.cbx-twin-chip:hover { background: color-mix(in srgb, var(--accent) 22%, transparent); }
.cbx-twin-chip.cbx-invalid { color: var(--red); background: color-mix(in srgb, var(--red) 10%, transparent); }
/* 云端配置设备条：内联实时读数 */
.cbx-rt-tag {
  display: inline-block; font-size: 9px; font-weight: 600; color: var(--green);
  background: color-mix(in srgb, var(--green) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--green) 35%, transparent);
  border-radius: 2px; padding: 0 4px; margin: 1px 4px 1px 0; vertical-align: 1px;
}
.cbx-rt-ago { font-size: 9.5px; color: var(--muted); margin-left: 2px; }
/* ---- Broker 配置弹窗（VSCode 对话框） ---- */
.cbx-mask {
  position: fixed; inset: 0; z-index: 300; background: rgba(0,0,0,.5);
  display: flex; align-items: center; justify-content: center;
}
.cbx-dialog {
  width: 560px; max-width: 92vw; background: var(--panel);
  border: 1px solid var(--border); border-radius: 6px; padding: 14px 16px;
  box-shadow: 0 12px 40px rgba(0,0,0,.4);
}
.cbx-dialog-lg { width: 780px; max-width: 94vw; }
.cbx-dialog-xl { width: 920px; max-width: 96vw; }
.cbx-dialog-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
  padding-bottom: 10px; border-bottom: 1px solid var(--border);
}
.cbx-dialog-head b { font-size: 13px; font-weight: 600; letter-spacing: .2px; }
.cbx-dialog-head .cbx-op { margin-left: auto; }
/* ---- 通信拓扑图（平台 → 云端 → 边端 → 设备端 四列 + SVG 连线锚定模块）---- */
.cbx-topo { position: relative; }
.cbx-topo-lanes { display: flex; align-items: flex-start; gap: 26px; flex-wrap: wrap; justify-content: space-between; }
.cbx-topo-lane { display: flex; flex-direction: column; gap: 14px; flex: 0 1 158px; min-width: 0; }
.cbx-topo-lane.dev { flex: 0 1 212px; }
.cbx-topo-lane-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 11px; font-weight: 700; color: var(--text); letter-spacing: .3px; padding: 2px 2px 0;
}
.cbx-topo-lane-title .cbx-op.cbx-xs { margin-left: auto; }
/* 模块卡片：渐变背景 + 圆角 + 阴影 + 悬停浮起 + 左侧类型色条 */
.cbx-topo-mod {
  position: relative; overflow: hidden;
  background: var(--panel-2);
  border: 1px solid var(--border); border-radius: 4px; padding: 8px 9px 9px;
  box-shadow: 0 1px 2px rgba(15,23,42,.05);
  transition: transform .16s ease, box-shadow .16s ease, border-color .12s;
  cursor: grab; touch-action: none;
}
.cbx-topo-mod.dragging { cursor: grabbing; box-shadow: 0 10px 30px rgba(15,23,42,.32); }
.cbx-topo-mod-ph { visibility: hidden; }
.cbx-topo-canvas { min-height: 700px; }
.cbx-topo-mod::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--accent); }
.cbx-topo-mod.platform::before { background: var(--accent); }
.cbx-topo-mod.agent::before { background: var(--yellow); }
.cbx-topo-mod.cloudcore::before { background: #5b8def; }
.cbx-topo-mod.broker::before { background: var(--accent2); }
.cbx-topo-mod.box::before { background: var(--green); }
.cbx-topo-mod.devgroup::before { background: var(--orange, #f59e0b); }
.cbx-topo-mod:hover { transform: translateY(-1px); box-shadow: 0 2px 6px rgba(15,23,42,.08), 0 12px 26px rgba(15,23,42,.13); }
.cbx-topo-mod.down { opacity: .75; }
.cbx-topo-mod-head { display: flex; align-items: center; gap: 6px; }
.cbx-topo-mod-name {
  font-weight: 700; font-size: 11px; color: var(--text);
  flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cbx-topo-mod-badge { flex: none; font-size: 9px; font-weight: 600; padding: 1px 6px; border-radius: 2px; color: var(--muted); border: 1px solid var(--border); letter-spacing: .2px; }
.cbx-topo-mod-badge.ok { color: var(--green); border-color: color-mix(in srgb, var(--green) 45%, var(--border)); }
.cbx-topo-mod-sub { font-size: 10px; color: var(--muted); margin-top: 4px; line-height: 1.55; }
.cbx-topo-mod-ops { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
.cbx-topo-mod-ops .cbx-op.cbx-xs { padding: 2px 7px; font-size: 9.5px; min-height: 18px; }
/* 盒子卡片：当前运行的服务/模型（云端部署，盒子周期上报） */
.cbx-topo-svcs { display: flex; flex-direction: column; gap: 2px; margin-top: 6px; max-height: 88px; overflow: auto; }
.cbx-topo-svc { display: flex; align-items: center; gap: 5px; font-size: 9.5px; background: rgba(0,0,0,.25); border-radius: 3px; padding: 2px 6px; }
.cbx-topo-svc-dot { flex: none; width: 6px; height: 6px; border-radius: 1px; background: var(--faint); }
.cbx-topo-svc-dot.on { background: var(--green); }
.cbx-topo-svc-name { color: var(--text); font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cbx-topo-svc-type { color: var(--faint); font-size: 8.5px; margin-left: auto; flex: none; }
.cbx-topo-svc-empty { font-size: 9.5px; color: var(--faint); padding: 2px 0; }
.cbx-edge-check { font-size: 10px; font-weight: 700; align-self: center; padding: 2px 8px; border-radius: 4px; }
.cbx-edge-check.ok { color: var(--green); }
.cbx-edge-check.bad { color: var(--red); }
/* SVG 连线覆盖层：贝塞尔箭头线从源模块边缘连到目标模块边缘，标签标注协议/方法
   注意：path/g 由原生 DOM 创建，Vue scoped style 不会自动给它们加 data-v，
   因此这些选择器用 :global() 包裹，确保样式能命中。 */
:global(.cbx-topo-svg) { position: absolute; left: 0; top: 0; width: 100%; height: 100%; pointer-events: none; z-index: 2; overflow: visible; }
:global(.cbx-topo-svg-link) { fill: none; stroke-width: 2.2; stroke-linecap: round; stroke-dasharray: 7 4; opacity: .9; animation: cbx-topo-flow 1.6s linear infinite; }
:global(.cbx-topo-svg-link.red) { stroke: var(--red); }
:global(.cbx-topo-svg-link.green) { stroke: var(--green); }
:global(.cbx-topo-svg-link.blue) { stroke: var(--accent); }
@keyframes cbx-topo-flow { to { stroke-dashoffset: -11; } }
:global(.cbx-topo-svg-label text) { font-size: 10px; font-weight: 600; fill: var(--text); paint-order: stroke; stroke: var(--panel); stroke-width: 3px; stroke-linejoin: round; }
.cbx-topo-dev-ops { display: inline-flex; gap: 2px; margin-left: auto; flex: none; }
.cbx-topo-dev-ops .cbx-op.cbx-tiny { padding: 1px 5px; font-size: 9px; min-height: 16px; }
/* 证书与 Token 有效期（独立区块） */
.cbx-certlist { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 6px; }
.cbx-certrow {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 12px; font-size: 11px;
  border: 1px solid var(--border); border-radius: 3px; background: var(--panel-2);
}
.cbx-certrow code { color: var(--accent2); font-size: 10.5px; font-weight: 600; flex: none; }
.cbx-cert-exp { color: var(--muted); flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cbx-cert-days { flex: none; color: var(--green); font-weight: 600; font-variant-numeric: tabular-nums; }
.cbx-cert-days.warn { color: var(--red); }
.cbx-topo-box { display: flex; flex-direction: column; gap: 6px; }
.cbx-topo-devlist { border-left: 2px solid var(--border); margin-left: 12px; padding-left: 10px; display: flex; flex-direction: column; gap: 4px; }
.cbx-topo-unmounted { border-left-color: color-mix(in srgb, var(--yellow) 50%, transparent); }
.cbx-topo-devgroup { display: flex; flex-direction: column; gap: 3px; }
.cbx-topo-devlabel { font-size: 9px; color: var(--faint); margin-top: 3px; }
.cbx-topo-dev { display: flex; align-items: center; gap: 6px; font-size: 10.5px; cursor: pointer; padding: 2px 3px; border-radius: 2px; transition: background .12s; flex-wrap: wrap; row-gap: 3px; }
.cbx-topo-dev:hover { background: var(--accent-l); }
.cbx-topo-dev.cloud .cbx-topo-dev-dot { background: var(--accent); }
.cbx-topo-dev.cloud.on .cbx-topo-dev-dot { background: var(--green); }
.cbx-topo-dev.cloud .cbx-topo-dev-val { color: var(--text); }
.cbx-topo-dev-sub { font-size: 9px; color: var(--faint); }
.cbx-topo-dev.pending { border: 1px dashed color-mix(in srgb, var(--red) 45%, transparent); padding: 1px 4px; border-radius: 3px; }
.cbx-topo-dev.pending .cbx-topo-dev-name { color: var(--orange, var(--yellow)); }
.cbx-topo-dev-dot { width: 6px; height: 6px; border-radius: 1px; background: var(--faint); flex: none; }
.cbx-topo-dev.on .cbx-topo-dev-dot { background: var(--green); }
.cbx-topo-dev-name { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cbx-topo-dev-val { color: var(--accent); font-weight: 600; margin-left: auto; font-variant-numeric: tabular-nums; }
.cbx-topo-dev-empty { font-size: 10px; color: var(--faint); padding: 2px 0; }
.cbx-topo-empty { font-size: 10.5px; color: var(--faint); border: 1px dashed var(--border); border-radius: 4px; padding: 10px; }
/* ---- 实时数据折线图弹窗 ---- */
.cbx-rt { display: flex; flex-direction: column; gap: 10px; }
.cbx-rt-tabs { display: flex; gap: 6px; flex-wrap: wrap; }
.cbx-rt-tab {
  display: flex; align-items: center; gap: 6px;
  padding: 5px 10px; border: 1px solid var(--border); border-radius: 3px;
  background: var(--panel-2); cursor: pointer; font-size: 10.5px; color: var(--text);
  transition: border-color .15s, background .12s;
}
.cbx-rt-tab:hover { border-color: var(--muted); background: var(--panel-3, var(--panel)); }
.cbx-rt-tab code { color: var(--accent2); font-size: 10.5px; }
.cbx-rt-tab.active { border-color: var(--accent); box-shadow: 0 0 0 1px var(--accent); }
.cbx-rt-tab .cbx-rt-cur { font-weight: 600; color: var(--accent); font-variant-numeric: tabular-nums; }
.cbx-rt-tab .cbx-rt-unit { color: var(--faint); font-size: 9.5px; }
.cbx-rt-chart {
  position: relative; border: 1px solid var(--border); border-radius: 4px;
  background: var(--panel-2); padding: 6px 8px 0;
}
.cbx-rt-svg { width: 100%; height: auto; display: block; }
.cbx-grid { stroke: var(--border); stroke-width: 1; }
.cbx-axis { fill: var(--muted); font-size: 9.5px; }
.cbx-rt-line { stroke: var(--accent); stroke-width: 1.8; fill: none; stroke-linejoin: round; stroke-linecap: round; }
.cbx-rt-area { fill: var(--accent); opacity: .12; }
.cbx-hv-line { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 3 3; }
.cbx-hv-dot { fill: var(--accent); stroke: var(--panel); stroke-width: 2; }
.cbx-rt-empty { height: 250px; display: flex; align-items: center; justify-content: center; color: var(--faint); font-size: 11px; }
.cbx-rt-tip {
  position: absolute; transform: translate(-50%, -130%);
  background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
  padding: 4px 9px; pointer-events: none; font-size: 10px;
  box-shadow: 0 4px 14px rgba(0,0,0,.35); white-space: nowrap; z-index: 5;
}
.cbx-rt-tip-t { color: var(--muted); }
.cbx-rt-tip-v { color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums; }
.cbx-rt-currow { display: flex; align-items: baseline; gap: 8px; font-size: 12px; padding: 0 2px; }
.cbx-rt-curlabel { color: var(--muted); font-size: 10px; }
.cbx-rt-curval { color: var(--accent); font-size: 22px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1; }
.cbx-rt-unit { color: var(--muted); }
.cbx-rt-upd { color: var(--faint); font-size: 10px; margin-left: auto; }
/* ---- VSCode 风格细滚动条（覆盖全部可滚动容器） ---- */
.cbx-body::-webkit-scrollbar, .cbx-msglog::-webkit-scrollbar, .cbx-yaml::-webkit-scrollbar,
.cbx-code::-webkit-scrollbar, .cbx-onboard::-webkit-scrollbar, .cbx-rt::-webkit-scrollbar,
.cbx-topo::-webkit-scrollbar, .cbx-dialog::-webkit-scrollbar { width: 8px; height: 8px; }
.cbx-body::-webkit-scrollbar-thumb, .cbx-msglog::-webkit-scrollbar-thumb, .cbx-yaml::-webkit-scrollbar-thumb,
.cbx-code::-webkit-scrollbar-thumb, .cbx-onboard::-webkit-scrollbar-thumb, .cbx-rt::-webkit-scrollbar-thumb,
.cbx-topo::-webkit-scrollbar-thumb, .cbx-dialog::-webkit-scrollbar-thumb {
  background: var(--border); border-radius: 4px; border: 2px solid transparent; background-clip: content-box;
}
.cbx-body::-webkit-scrollbar-thumb:hover, .cbx-msglog::-webkit-scrollbar-thumb:hover, .cbx-yaml::-webkit-scrollbar-thumb:hover,
.cbx-code::-webkit-scrollbar-thumb:hover, .cbx-onboard::-webkit-scrollbar-thumb:hover, .cbx-rt::-webkit-scrollbar-thumb:hover,
.cbx-topo::-webkit-scrollbar-thumb:hover, .cbx-dialog::-webkit-scrollbar-thumb:hover {
  background: var(--muted); border: 2px solid transparent; background-clip: content-box;
}
.cbx-body::-webkit-scrollbar-track, .cbx-msglog::-webkit-scrollbar-track, .cbx-yaml::-webkit-scrollbar-track,
.cbx-code::-webkit-scrollbar-track, .cbx-onboard::-webkit-scrollbar-track, .cbx-rt::-webkit-scrollbar-track,
.cbx-topo::-webkit-scrollbar-track, .cbx-dialog::-webkit-scrollbar-track { background: transparent; }
</style>
