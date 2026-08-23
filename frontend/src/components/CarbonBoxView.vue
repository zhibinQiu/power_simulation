<template>
  <!-- ============ 能碳一体机管理视图（参照参考项目 yunduan1 console + dashboard 全部功能） ============ -->
  <div class="cbx-view">
    <!-- 页签导航 / 关闭 / 刷新等操作已由顶栏工具栏提供 -->
    <div class="cbx-body">
      <!-- ==================== Tab1 总览 ==================== -->
      <template v-if="tab === 'overview'">
        <div class="cbx-grid-2">
          <!-- MQTT 数据链路状态 -->
          <section class="cbx-sec">
            <div class="cbx-sec-head">
              <b>云端数据链路</b>
              <button class="cbx-op" @click="openBoxConfig" title="前端配置化：修改云端 Broker 地址/账号/订阅主题，保存后自动热更新重连（免手工编辑配置文件）">配置 Broker</button>
            </div>
            <div class="cbx-sec-sub">后端订阅云端 MQTT Broker 获取真实设备读数（前端配置，不再生成模拟数据）</div>
            <div class="cbx-mqtt" :class="{ on: mqttConnected }">
              <div class="cbx-mqtt-head">
                <span class="cbx-mqtt-title">Mqtt 实时数据源</span>
                <span class="cbx-mqtt-status" :class="{ on: mqttConnected }">{{ mqttStatusText }}</span>
              </div>
              <div class="cbx-mqtt-row">
                <span>Broker</span>
                <code>{{ mqttBroker }}</code>
                <template v-if="store.mqttSource">
                  <span class="cbx-sep">·</span>
                  <span>已收 {{ store.mqttSource.message_count || 0 }} 条</span>
                </template>
              </div>
              <div class="cbx-mqtt-row" v-if="mqttTopics.length">
                <span>订阅</span>
                <code v-for="t in mqttTopics" :key="t">{{ t }}</code>
              </div>
              <div v-if="mqttRecentMsg" class="cbx-mqtt-msg">
                <span>最近消息</span>
                <code class="cbx-mqtt-topic">{{ mqttRecentMsg.topic }}</code>
                <div class="cbx-mqtt-payload">{{ mqttRecentMsg.payload }}</div>
              </div>
            </div>
          </section>

          <!-- Broker 实时统计（$SYS，真实） -->
          <section class="cbx-sec">
            <div class="cbx-sec-head">
              <b>云端 Broker 统计</b>
              <span class="cbx-sec-sub">来自 $SYS/broker/# 实时统计</span>
            </div>
            <div class="cbx-stats">
              <div class="cbx-stat"><span>在线客户端</span><b>{{ stats.clients_connected ?? '—' }}</b></div>
              <div class="cbx-stat"><span>历史峰值</span><b>{{ stats.clients_max ?? '—' }}</b></div>
              <div class="cbx-stat"><span>累计接收</span><b>{{ fmtNum(stats.broker_recv) }}</b></div>
              <div class="cbx-stat"><span>累计发送</span><b>{{ fmtNum(stats.broker_sent) }}</b></div>
              <div class="cbx-stat"><span>订阅数</span><b>{{ fmtNum(stats.subscriptions) }}</b></div>
              <div class="cbx-stat"><span>Broker 版本</span><b>{{ stats.version || '—' }}</b></div>
              <div class="cbx-stat"><span>运行时长</span><b>{{ fmtUptime(stats.uptime) }}</b></div>
              <div class="cbx-stat"><span>本平台已收</span><b>{{ fmtNum(stats.panel_recv) }}</b></div>
            </div>
          </section>

          <!-- cloudcore 状态（仿真演示） -->
          <section class="cbx-sec">
            <div class="cbx-sec-head">
              <b>CloudCore（云端边缘管理核心）</b>
              <span class="cbx-tag demo" v-if="overview.cloudcore && overview.cloudcore.demo">仿真演示</span>
            </div>
            <div class="cbx-kv" v-if="overview.cloudcore">
              <div><span>Pod</span><code>{{ overview.cloudcore.name }}</code></div>
              <div><span>Phase</span><b class="ok">{{ overview.cloudcore.phase }}</b></div>
              <div><span>Restarts</span><b>{{ overview.cloudcore.restarts }}</b></div>
              <div><span>Node</span><code>{{ overview.cloudcore.node }}</code></div>
              <div><span>Pod IP</span><code>{{ overview.cloudcore.podIP }}</code></div>
            </div>
          </section>

          <!-- 边缘节点（盒子，真实识别） -->
          <section class="cbx-sec">
            <div class="cbx-sec-head">
              <b>边缘节点（识别到的盒子）</b>
              <span class="cbx-sec-hint">{{ overview.nodes?.length || 0 }} 个</span>
            </div>
            <table class="cbx-table">
              <thead><tr><th>节点</th><th>就绪</th><th>角色</th><th>版本</th><th>最后上报</th></tr></thead>
              <tbody>
                <tr v-for="n in overview.nodes || []" :key="n.name">
                  <td><code>{{ n.name }}</code></td>
                  <td><span class="cbx-dot" :class="{ on: n.ready }"></span>{{ n.ready ? 'Ready' : 'NotReady' }}</td>
                  <td>{{ n.roles }}</td>
                  <td>{{ n.version }}</td>
                  <td>{{ n.age }}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <!-- CloudHub 端口（仿真演示） -->
          <section class="cbx-sec">
            <div class="cbx-sec-head">
              <b>CloudHub 端口</b>
              <span class="cbx-tag demo" v-if="overview.ports?.[0]?.demo">仿真演示</span>
            </div>
            <table class="cbx-table">
              <thead><tr><th>端口</th><th>协议</th><th>服务</th></tr></thead>
              <tbody>
                <tr v-for="p in overview.ports || []" :key="p.port">
                  <td><code>{{ p.port }}</code></td>
                  <td>{{ p.proto }}</td>
                  <td>{{ p.svc }}</td>
                </tr>
              </tbody>
            </table>
          </section>

          <!-- 证书 / Token（仿真演示） -->
          <section class="cbx-sec">
            <div class="cbx-sec-head">
              <b>证书与 Token 有效期</b>
              <span class="cbx-tag demo" v-if="overview.certs?.[0]?.demo">仿真演示</span>
            </div>
            <table class="cbx-table">
              <thead><tr><th>证书</th><th>过期时间</th><th>剩余天数</th></tr></thead>
              <tbody>
                <tr v-for="c in overview.certs || []" :key="c.cn">
                  <td><code>{{ c.cn }}</code></td>
                  <td>{{ c.expires }}</td>
                  <td>{{ c.remain_days }}</td>
                </tr>
                <tr v-if="overview.token">
                  <td><code>token</code></td>
                  <td>{{ overview.token.expires }}</td>
                  <td>{{ overview.token.remain_days }}</td>
                </tr>
              </tbody>
            </table>
          </section>
        </div>
        <p class="cbx-note" v-if="overview.demo_note">⚠ {{ overview.demo_note }}</p>
      </template>

      <!-- ==================== Tab2 设备管理 ==================== -->
      <template v-else-if="tab === 'devices'">
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>DeviceModel / Device（KubeEdge 设备模型与实例，本地模拟集群）</b>
            <span class="cbx-sec-hint">{{ devices.models?.length || 0 }} 模型 · {{ devices.devices?.length || 0 }} 设备</span>
          </div>
          <table class="cbx-table">
            <thead><tr><th>类型</th><th>名称</th><th>命名空间</th><th>协议</th><th>节点</th><th>属性</th><th>状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="m in devices.models || []" :key="'m' + m.name">
                <td><span class="cbx-badge model">模型</span></td>
                <td><code>{{ m.name }}</code></td>
                <td>{{ m.namespace }}</td>
                <td>{{ m.protocol }}</td>
                <td>—</td>
                <td>{{ m.properties?.length || 0 }}</td>
                <td>—</td>
                <td>
                  <button class="cbx-op danger" @click="delDev('model', m.name)">删除</button>
                </td>
              </tr>
              <tr v-for="d in devices.devices || []" :key="'d' + d.name">
                <td><span class="cbx-badge device">设备</span></td>
                <td><code>{{ d.name }}</code></td>
                <td>{{ d.namespace }}</td>
                <td>{{ d.protocol }}</td>
                <td>{{ d.node }}</td>
                <td>{{ d.properties?.length || 0 }}</td>
                <td>
                  <span class="cbx-dot" :class="{ on: d.cloud_matched }"></span>
                  {{ d.cloud_matched ? 'reporting' : 'pending' }}
                </td>
                <td>
                  <button class="cbx-op danger" @click="delDev('device', d.name)">删除</button>
                </td>
              </tr>
              <tr v-if="!devices.models?.length && !devices.devices?.length">
                <td colspan="8" class="cbx-empty-td">尚未创建设备。在下方表单新建 DeviceModel + Device。</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>新建设备</b>
            <span class="cbx-sec-sub">三协议 YAML 生成（Modbus / OPC-UA / Bluetooth），dryRun 预览后 apply</span>
          </div>
          <div class="cbx-form">
            <div class="cbx-form-row">
              <label>协议</label>
              <select v-model="form.protocol" class="cbx-select">
                <option value="modbus">Modbus（RTU / TCP）</option>
                <option value="opcua">OPC-UA</option>
                <option value="bluetooth">Bluetooth</option>
              </select>
            </div>
            <div class="cbx-form-row">
              <label>模型名</label><input v-model="form.modelName" class="cbx-input" placeholder="box-metric-model"/>
              <label>设备名</label><input v-model="form.deviceName" class="cbx-input" placeholder="box-device"/>
            </div>
            <div class="cbx-form-row">
              <label>命名空间</label><input v-model="form.namespace" class="cbx-input" style="width:90px" placeholder="default"/>
              <label>调度节点</label><input v-model="form.nodeName" class="cbx-input" placeholder="edge-node"/>
              <label>采集周期(ms)</label><input v-model.number="form.collectCycle" type="number" class="cbx-input" style="width:100px"/>
            </div>
            <div class="cbx-form-row">
              <label>绑定云端设备</label>
              <select v-model="form.cloudDevice" class="cbx-select" style="flex:1" title="实时匹配优先按此 id 绑定云端识别设备；留空则按设备名匹配">
                <option value="">不绑定（按设备名匹配）</option>
                <option v-for="cd in cloudDevicesList" :key="cd.id" :value="cd.id">{{ cd.id }}（{{ cd.box }}）</option>
              </select>
              <label>从设备库导入</label>
              <select v-model="libPick" class="cbx-select" style="flex:1" title="从仿真系统设备库（devices.py：皮带秤/电表/流量计等）导入模板，自动填充属性点位与 IP">
                <option value="">选择工序设备…</option>
                <option v-for="l in libOptions" :key="l.type" :value="l.type">{{ l.label }}</option>
              </select>
              <button class="cbx-op" :disabled="!libPick" @click="importFromLibrary">导入模板</button>
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
            <template v-else>
              <div class="cbx-form-row">
                <label>MAC 地址</label><input v-model="form.bluetooth.macAddress" class="cbx-input" style="width:160px" placeholder="AA:BB:CC:DD:EE:FF"/>
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
              <template v-else>
                <input v-model="p.characteristicUUID" class="cbx-input" style="width:170px" placeholder="characteristicUUID"/>
              </template>
              <input v-model="p.unit" class="cbx-input" style="width:60px" placeholder="单位"/>
              <button class="cbx-op danger" @click="form.properties.splice(i, 1)">✕</button>
            </div>

            <div class="cbx-form-row" style="margin-top:10px">
              <button class="cbx-op primary" @click="dryRun()">生成 YAML 预览</button>
              <button class="cbx-op primary" @click="applyDev()">应用到集群</button>
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
        </section>

        <!-- 云端识别设备实时表（真实读数） -->
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>云端识别设备（真实读数）</b>
            <span class="cbx-sec-hint">{{ Object.keys(cloudDevicesMap).length }} 台</span>
          </div>
          <table class="cbx-table">
            <thead><tr><th>设备 id</th><th>盒子</th><th>主读数</th><th>字段</th><th>最后上报</th></tr></thead>
            <tbody>
              <tr v-for="cd in cloudDevicesList" :key="cd.id">
                <td><code>{{ cd.id }}</code></td>
                <td>{{ cd.box }}</td>
                <td class="val">{{ fmtPrimary(cd.primary) }}</td>
                <td>{{ (cd.fields || []).join(', ') }}</td>
                <td>{{ fmtAgo(cd.last_seen) }}</td>
              </tr>
              <tr v-if="!cloudDevicesList.length">
                <td colspan="5" class="cbx-empty-td">尚未识别到云端设备。</td>
              </tr>
            </tbody>
          </table>
        </section>
      </template>

      <!-- ==================== Tab3 设备关联 ==================== -->
      <template v-else-if="tab === 'links'">
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>云端设备关联</b>
            <span class="cbx-sec-hint" v-if="cloudDevices.length">已识别 {{ cloudDevices.length }} 台 · 已关联 {{ links.length }} 台</span>
          </div>
          <p class="cbx-note">
            云端识别设备（能碳一体机盒子下的设备，自动发现自 MQTT 消息）需与<b>仿真系统中的设备实例</b>手动关联后，
            其读数才会同步到该设备实例；未关联的设备不同步。
          </p>
          <div v-if="!cloudDevices.length" class="cbx-empty">
            尚未识别到云端设备：Broker 有消息上报后，这里会按盒子分组列出识别到的设备，供你手动关联。
            <template v-if="!mqttConnected">（当前 MQTT 未连接，请先确保 Broker 可达）</template>
          </div>
          <div v-for="(group, box) in boxGroups" :key="box" class="cbx-group">
            <div class="cbx-group-head">
              <span class="cbx-group-box">{{ box }}</span>
              <span class="cbx-group-count">{{ group.length }} 台</span>
            </div>
            <div v-for="cd in group" :key="cd.id" class="cbx-row" :class="{ linked: linkOf(cd.id) }">
              <div class="cbx-dev">
                <span class="cbx-dev-id" :title="'topic: ' + (cd.topic || '')">{{ cd.id }}</span>
                <span class="cbx-dev-val">{{ fmtPrimary(cd.primary) }}</span>
                <span class="cbx-dev-fields" v-if="cd.fields && cd.fields.length" :title="cd.fields.join(', ')">
                  字段 {{ cd.fields.length }}
                </span>
                <span class="cbx-dev-seen">↑ {{ fmtAgo(cd.last_seen) }}</span>
              </div>
              <template v-if="linkOf(cd.id)">
                <span class="cbx-arrow">→</span>
                <span class="cbx-local">{{ localLabel(linkOf(cd.id)) }}</span>
                <button class="cbx-op danger" @click="unlink(cd.id)" title="解除关联，数据停止同步">解除关联</button>
              </template>
              <template v-else>
                <span class="cbx-arrow">→</span>
                <select v-model="pendingLink[cd.id]" class="cbx-select" title="选择要同步到哪个仿真设备实例">
                  <option value="">选择设备实例…</option>
                  <option v-for="d in deviceOptions" :key="d.id" :value="d.id">{{ d.label }}</option>
                </select>
                <button class="cbx-op" :disabled="!pendingLink[cd.id]" @click="link(cd.id)">关联</button>
              </template>
            </div>
          </div>
        </section>
      </template>

      <!-- ==================== Tab4 盒子接入 ==================== -->
      <template v-else-if="tab === 'onboard'">
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>盒子接入（生成 edgecore.yaml + token + caHash + 部署命令）</b>
            <span class="cbx-sec-sub">参照 yunduan1 console 盒子接入向导</span>
          </div>
          <div class="cbx-form">
            <div class="cbx-form-row">
              <label>盒子主机名</label><input v-model="onboardForm.hostname" class="cbx-input" placeholder="edge-box"/>
              <label>云端 CloudCore IP</label><input v-model="onboardForm.cloudIP" class="cbx-input" placeholder="10.0.0.10"/>
              <label>盒子 IP</label><input v-model="onboardForm.boxIP" class="cbx-input" placeholder="192.168.1.20"/>
              <button class="cbx-op primary" :disabled="!onboardForm.cloudIP" @click="doOnboard">生成接入配置</button>
            </div>
          </div>
          <div v-if="onboardResult" class="cbx-onboard">
            <div class="cbx-kv">
              <div><span>共享 Token</span><code class="wrap">{{ onboardResult.token }}</code></div>
              <div><span>CA 指纹</span><code class="wrap">{{ onboardResult.caHash }}</code></div>
            </div>
            <div class="cbx-preview-head"><b>edgecore.yaml</b><button class="cbx-op" @click="copyOnboard">复制</button></div>
            <pre class="cbx-code">{{ onboardResult.edgecore }}</pre>
            <div class="cbx-preview-head"><b>部署命令</b></div>
            <pre class="cbx-code">{{ onboardResult.commands.join('\n') }}</pre>
            <p class="cbx-note" v-if="onboardResult.demo_note">⚠ {{ onboardResult.demo_note }}</p>
          </div>
        </section>
      </template>

      <!-- ==================== Tab5 实时数据 ==================== -->
      <template v-else-if="tab === 'realtime'">
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>Device.status.twins 实时上报值</b>
            <span class="cbx-sec-hint">{{ rtDevices.length }} 台设备 · 读数一律来自 MQTT 链路</span>
          </div>
          <div v-if="!rtDevices.length" class="cbx-empty">尚无已配置设备：请先在「设备管理」页签创建设备。</div>
          <div v-for="dev in rtDevices" :key="dev.name" class="cbx-twin-card">
            <div class="cbx-twin-head">
              <b><code>{{ dev.name }}</code></b>
              <span class="cbx-tag" :class="{ ok: dev.state === 'reporting' }">{{ dev.state }}</span>
              <span class="cbx-sec-hint">节点 {{ dev.node }} · 模型 {{ dev.model }} · 最后在线 {{ dev.lastOnlineTime ? fmtAgo(dev.lastOnlineTime) : '—' }}</span>
            </div>
            <table class="cbx-table">
              <thead><tr><th>属性</th><th>reported（实时值）</th><th>observedDesired</th><th>单位</th><th>timestamp</th><th>趋势</th></tr></thead>
              <tbody>
                <tr v-for="t in dev.twins" :key="t.propertyName">
                  <td><code>{{ t.propertyName }}</code></td>
                  <td class="val">{{ fmtPrimary(t.reported) }}</td>
                  <td>{{ t.observedDesired ?? '—' }}</td>
                  <td>{{ t.unit || '' }}</td>
                  <td>{{ t.timestamp ? fmtAgo(t.timestamp) : '—' }}</td>
                  <td class="cbx-spark-cell"><svg v-if="(dev.history[t.propertyName] || []).length > 1" :viewBox="sparkView" class="cbx-spark">
                    <polyline :points="sparkPoints(dev.history[t.propertyName])" fill="none" stroke="var(--accent)" stroke-width="1.5"/>
                  </svg><span v-else class="cbx-faint">—</span></td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <b>实时消息流（云端 Broker → 本平台）</b>
            <span class="cbx-sec-hint">{{ messages.length }} 条（最近 100）</span>
          </div>
          <div class="cbx-msglog">
            <div v-for="(m, i) in messages" :key="i" class="cbx-msgrow">
              <span class="cbx-msgtime">{{ fmtTime(m.t) }}</span>
              <code class="cbx-msg-topic">{{ m.topic }}</code>
              <span class="cbx-msg-payload">{{ m.payload }}</span>
            </div>
            <div v-if="!messages.length" class="cbx-empty">暂无消息。</div>
          </div>
        </section>

        <!-- 发测试消息（实时仪表盘调试） -->
        <section class="cbx-sec">
          <div class="cbx-sec-head"><b>发测试消息（向云端 Broker 发布）</b></div>
          <div class="cbx-form">
            <div class="cbx-form-row">
              <label>主题</label><input v-model="pubForm.topic" class="cbx-input" style="width:260px" placeholder="data/box-001/device-1"/>
              <label>载荷</label><input v-model="pubForm.payload" class="cbx-input" style="flex:1" placeholder='{"device":"device-1","value":88.8}'/>
              <button class="cbx-op primary" @click="doPublish">发布</button>
            </div>
          </div>
        </section>
      </template>

      <!-- ==================== Tab6 接入指引 ==================== -->
      <template v-else>
        <section class="cbx-sec">
          <div class="cbx-sec-head"><b>数据链路总览</b></div>
          <div class="cbx-guide-flow">
            <div class="cbx-flow-node">边缘盒子<br/><span>eKuiper 采集<br/>Modbus / OPC-UA / BT</span></div>
            <div class="cbx-flow-arrow">→</div>
            <div class="cbx-flow-node">云端 MQTT Broker<br/><span>自建 Broker<br/>TCP 41883</span></div>
            <div class="cbx-flow-arrow">→</div>
            <div class="cbx-flow-node">本平台<br/><span>订阅 data/#<br/>识别设备 / 关联后同步</span></div>
          </div>
          <p class="cbx-note">
            数据链路参照参考项目 yunduan1：边缘盒子 eKuiper（Modbus 采集）→ 云端 MQTT Broker → 本平台订阅获取真实设备读数。
            <b>本平台不再生成模拟数据</b>；云端设备需与仿真设备实例关联后读数才同步。
          </p>
        </section>

        <section class="cbx-sec">
          <div class="cbx-sec-head"><b>边缘盒子侧采集（kubeedge_modbus_mapper.py）</b></div>
          <pre class="cbx-code"># 盒子侧采集程序（参考项目 yunduan1/weight_bridge/kubeedge_modbus_mapper.py）
# 负责：Modbus RTU 轮询传感器 → 更新 Device.status.twins → 边缘 mqtt 上报云端
关键步骤：
1. 读取设备配置（slaveID / 寄存器地址 / scale / swap）
2. 定时读取各寄存器原始值并换算工程量
3. 构造 twins 更新消息（property / value / timestamp）上报云端
4. 云端 eKuiper 规则将 twins 转发到 MQTT Broker（见 REPOINT_EKUIPER.md）</pre>
        </section>

        <section class="cbx-sec">
          <div class="cbx-sec-head"><b>eKuiper 转发规则（REPOINT_EKUIPER.md）</b></div>
          <pre class="cbx-code">-- 在 eKuiper 中创建转发规则：订阅边缘设备数据，重发布到云端 Broker
CREATE STREAM sensor_stream () WITH (
  DATASOURCE = "devices/#",
  FORMAT = "JSON"
);
-- 规则：透传上报数据到 data/&lt;box&gt;/&lt;device&gt; 主题（本平台按此主题识别云端设备）</pre>
        </section>

        <section class="cbx-sec">
          <div class="cbx-sec-head"><b>部署包与数据落盘</b></div>
          <pre class="cbx-code"># 参考项目 yunduan1/deploy_pkg：
#  - broker.yaml：云端 MQTT Broker 配置（amqtt，TCP 41883 / WS 41083）
#  - collect_sensor_data.py：传感器数据落盘 sensor_data/YYYY-MM-DD.jsonl（按天归档）
#  - install.sh / sync.sh：部署与同步脚本
# 本平台后端通过该 Broker 订阅实时读数（Broker 配置前端化：本视图 → 总览 → 配置 Broker）。</pre>
        </section>

        <section class="cbx-sec">
          <div class="cbx-sec-head"><b>诊断工具</b></div>
          <pre class="cbx-code"># 参考项目 yunduan1：
#  - watch_cloud.py：监控云端 Broker 消息（默认订阅 #，过滤 $SYS）
#  - test_pubsub.py：MQTT 发布/订阅自测
#  - dashboard.py：实时仪表盘（Broker 统计 + 消息流 + 发测试消息）
# 上述功能已集成到本视图：总览（Broker 统计）、实时数据（消息流 + 发测试消息）。</pre>
        </section>
      </template>
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
          <div class="cbx-form-row">
            <label>订阅主题</label><input v-model="boxCfg.topics" class="cbx-input" style="flex:1" placeholder="data/# （逗号分隔多个）"/>
          </div>
          <div class="cbx-form-row" style="align-items:flex-start">
            <label>静态映射<br/><span style="font-weight:400;font-size:9.5px;color:var(--dim)">JSON：字段→平台设备id</span></label>
            <textarea v-model="boxCfg.mapping" rows="3" class="cbx-input" style="flex:1;font-family:ui-monospace,monospace;font-size:10.5px" placeholder='{"meter_1":"coke_dry_quench::stack_scale"}'></textarea>
          </div>
          <p class="cbx-note">
            保存后立即断开并按新配置重连（热更新），配置持久化到 box_config.json，无需手工编辑配置文件。
            默认值参考项目 yunduan1 broker.yaml（TCP 41883 / WS 41083）；密码为占位符时保留原密码。
          </p>
          <div class="cbx-form-row">
            <button class="cbx-op primary" :disabled="boxCfgSaving" @click="saveBoxConfig">{{ boxCfgSaving ? '保存中…' : '保存并重连' }}</button>
            <button class="cbx-op" @click="boxCfgOpen = false">取消</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, reactive, ref } from 'vue'
import { useSimStore } from '../stores/sim'
import { api } from '../api/client'

const store = useSimStore()

const tabs = [
  { id: 'overview', label: '总览' },
  { id: 'devices', label: '设备管理' },
  { id: 'links', label: '设备关联' },
  { id: 'onboard', label: '盒子接入' },
  { id: 'realtime', label: '实时数据' },
  { id: 'guide', label: '接入指引' },
]
const tab = ref('overview')

// ---- 轮询定时器 ----
// 快慢拆分：实时数据（总览/实时数据页签）3s，设备配置列表 10s；按当前页签拉取，避免无谓请求
let fastTimer = null
let slowTimer = null
const startPolling = () => {
  stopPolling()
  fastTimer = setInterval(refreshFast, 3000)
  slowTimer = setInterval(loadDevices, 10000)
}
const stopPolling = () => {
  if (fastTimer) { clearInterval(fastTimer); fastTimer = null }
  if (slowTimer) { clearInterval(slowTimer); slowTimer = null }
}
onMounted(() => { refreshAll(); loadDeviceLibrary(); startPolling() })
onUnmounted(stopPolling)

// ---- MQTT 链路状态（store.mqttSource 由 store 每 3s 轮询）----
const mqttConnected = computed(() => !!(store.mqttSource && store.mqttSource.connected))
const mqttStatusText = computed(() => {
  const s = store.mqttSource
  if (!s) return '获取中…'
  if (s.connected) return '已连接'
  return s.last_error ? '异常' : '未连接'
})
const mqttBroker = computed(() => {
  const s = store.mqttSource
  return s ? `${s.broker_host}:${s.broker_port}` : '—'
})
const mqttTopics = computed(() => (store.mqttSource && store.mqttSource.topics) || [])
const mqttRecentMsg = computed(() => {
  const s = store.mqttSource
  const recs = s && s.recent_messages
  return recs && recs.length ? recs[recs.length - 1] : null
})

// ---- 云端设备识别 + 关联表 ----
const cloudDevices = computed(() => (store.mqttSource && store.mqttSource.cloud_devices) || [])
const links = computed(() => (store.mqttSource && store.mqttSource.links) || [])
const linkMap = computed(() => {
  const m = {}
  for (const l of links.value) m[l.cloud_id] = l.local_id
  return m
})
const cloudDevicesMap = computed(() => {
  const m = {}
  for (const cd of cloudDevices.value) m[cd.id] = cd
  return m
})
const cloudDevicesList = computed(() => cloudDevices.value.slice().sort((a, b) => (b.last_seen || 0) - (a.last_seen || 0)))
const boxGroups = computed(() => {
  const groups = {}
  for (const cd of cloudDevices.value) {
    const box = cd.box || '未分组'
    if (!groups[box]) groups[box] = []
    groups[box].push(cd)
  }
  return groups
})
const deviceOptions = computed(() =>
  store.allDevices.map((d) => ({
    id: d.id,
    label: `${d.label} · ${d.unitName || d.unitType || ''}${d.unit ? ' (' + d.unit + ')' : ''}`,
  }))
)
const pendingLink = reactive({})
function linkOf(cloudId) { return linkMap.value[cloudId] || '' }
async function link(cloudId) {
  const localId = pendingLink[cloudId]
  if (!localId) return
  try {
    await store.linkMqttDevice(cloudId, localId)
    pendingLink[cloudId] = ''
  } catch (e) {
    store.toast = '关联失败：' + (e.message || e)
  }
}
async function unlink(cloudId) {
  if (!window.confirm(`确认解除云端设备「${cloudId}」的关联？解除后数据停止同步。`)) return
  try {
    await store.unlinkMqttDevice(cloudId)
  } catch (e) {
    store.toast = '解除关联失败：' + (e.message || e)
  }
}
function localLabel(localId) {
  const d = store.allDevices.find((x) => x.id === localId)
  return d ? `${d.label} · ${d.unitName || ''}` : localId
}

// ---- Tab1 总览 ----
const overview = ref({})
async function loadOverview() {
  try { overview.value = await api.boxOverview() } catch (e) {}
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
  comm: { commType: 'serial', slaveID: 1, serialPort: '/dev/ttyS0', baudRate: 9600, parity: 'none', tcpIP: '192.168.1.10', tcpPort: 502 },
  opcua: { url: 'opc.tcp://127.0.0.1:4840', userName: '', password: '' },
  bluetooth: { macAddress: 'AA:BB:CC:DD:EE:FF' },
  properties: [{ name: 'value', type: 'float', accessMode: 'r', registerType: 'holdingRegister', register: 0, scale: 1, unit: '' }],
})
const preview = ref('')
const formErr = ref('')
async function loadDevices() { try { devices.value = await api.boxDevices() } catch (e) {} }

// ---- 从仿真设备库导入模板（迁移项目已有设备配置 devices.py：皮带秤/电表/流量计等）----
const LIB_TEMPLATES = {
  belt_scale: { label: '皮带秤', props: [['weight', 't', 0], ['flow', 't/h', 1]] },
  loss_in_weight: { label: '失重秤', props: [['weight', 't', 0], ['flow', 't/h', 1]] },
  hopper_scale: { label: '料斗秤', props: [['weight', 't', 0]] },
  weigher: { label: '轨道衡', props: [['weight', 't', 0]] },
  gas_flowmeter: { label: '气体流量计', props: [['flow', 'm³/h', 0]] },
  power_meter: { label: '智能电表', props: [['power', 'MWh/h', 0], ['voltage', 'V', 1], ['current', 'A', 2]] },
  composition_analyzer: { label: '成分分析仪', props: [['pct', '%', 0]] },
  cems: { label: 'CEMS 在线监测', props: [['so2', 'mg/m³', 0], ['nox', 'mg/m³', 1], ['dust', 'mg/m³', 2]] },
}
const libOptions = ref([])
const libPick = ref('')
async function loadDeviceLibrary() {
  try {
    const r = await api.getDevices()
    const lib = r.library || []
    libOptions.value = lib
      .map((d) => ({ type: d.type, label: (LIB_TEMPLATES[d.type] || {}).label || d.label || d.type }))
      .filter((x) => LIB_TEMPLATES[x.type])
  } catch (e) {}
}
function importFromLibrary() {
  const tpl = LIB_TEMPLATES[libPick.value]
  if (!tpl) return
  form.modelName = `${libPick.value}-model`
  form.deviceName = `${libPick.value}-01`
  form.desc = tpl.label
  form.comm.commType = 'tcp'
  form.comm.tcpIP = '192.168.1.10'
  form.comm.tcpPort = 502
  form.comm.slaveID = 1
  form.properties = tpl.props.map(([name, unit, reg]) => ({
    name, type: 'float', accessMode: 'r',
    registerType: 'holdingRegister', register: reg, scale: 1, unit,
    desc: `${tpl.label}·${name}`,
  }))
  store.toast = `已导入设备库模板：${tpl.label}（模型 ${form.modelName} / 设备 ${form.deviceName}）`
}

// ---- 云端 Broker 配置（前端配置化，免手工编辑 config/mqtt.yaml）----
const boxCfgOpen = ref(false)
const boxCfgSaving = ref(false)
const boxCfg = reactive({ host: '', port: 41883, username: '', password: '', topics: '', mapping: '{}' })
async function openBoxConfig() {
  try {
    const c = await api.boxConfig()
    boxCfg.host = c.broker.host || ''
    boxCfg.port = c.broker.port || 41883
    boxCfg.username = c.broker.username || ''
    boxCfg.password = c.broker.password || ''
    boxCfg.topics = (c.topics || []).join(', ')
    boxCfg.mapping = JSON.stringify(c.mapping || {}, null, 2)
    boxCfgOpen.value = true
  } catch (e) { store.toast = '加载配置失败：' + (e.message || e) }
}
async function saveBoxConfig() {
  boxCfgSaving.value = true
  try {
    const topics = boxCfg.topics.split(',').map((s) => s.trim()).filter(Boolean)
    let mapping = {}
    try { mapping = boxCfg.mapping.trim() ? JSON.parse(boxCfg.mapping) : {} } catch (err) { store.toast = '静态映射 JSON 格式错误'; return }
    const r = await api.boxConfigSave({
      broker: {
        host: boxCfg.host, port: Number(boxCfg.port) || 41883,
        username: boxCfg.username, password: boxCfg.password,
      },
      topics,
      mapping,
    })
    if (r.ok) {
      store.toast = 'Broker 配置已保存并热更新'
      boxCfgOpen.value = false
      store.mqttSource = await api.realtimeSource()   // 立即刷新链路状态（含重连结果）
      await loadOverview()
    } else {
      store.toast = '保存失败：' + (r.error || '')
    }
  } catch (e) { store.toast = '保存失败：' + (e.message || e) }
  finally { boxCfgSaving.value = false }
}

function addProp() {
  form.properties.push({
    name: 'prop' + (form.properties.length + 1), type: 'float', accessMode: 'r',
    registerType: 'holdingRegister', register: 0, scale: 1, unit: '',
  })
}
async function dryRun() {
  formErr.value = ''
  try {
    const r = await api.boxCreateDevice({ ...form, mode: 'dryRun' })
    preview.value = r.yamls.model + '\n---\n' + r.yamls.device
  } catch (e) { formErr.value = e.message || e }
}
async function applyDev() {
  formErr.value = ''
  try {
    const r = await api.boxCreateDevice({ ...form, mode: 'apply' })
    preview.value = r.yamls.model + '\n---\n' + r.yamls.device
    store.toast = `设备 ${form.deviceName} 已应用到集群`
    await loadDevices()
  } catch (e) { formErr.value = e.message || e }
}
async function delDev(kind, name) {
  if (!window.confirm(`确认删除${kind === 'model' ? '模型' : '设备'}「${name}」？`)) return
  try {
    const r = await api.boxDeleteDevice(kind, name)
    store.toast = `已删除：${(r.removed.devices || []).concat(r.removed.models || []).join(', ') || '无'}`
    await loadDevices()
  } catch (e) { store.toast = '删除失败：' + (e.message || e) }
}
async function copyPreview() { try { await navigator.clipboard.writeText(preview.value); store.toast = 'YAML 已复制' } catch (e) {} }

// ---- Tab4 盒子接入（预填参考项目 yunduan1 默认 IP，可改）----
const onboardForm = reactive({ hostname: 'edge-box', cloudIP: '10.0.0.10', boxIP: '192.168.1.20' })
const onboardResult = ref(null)
async function doOnboard() {
  try {
    onboardResult.value = await api.boxOnboard(onboardForm.hostname, onboardForm.cloudIP, onboardForm.boxIP)
  } catch (e) { store.toast = '生成失败：' + (e.message || e) }
}
async function copyOnboard() { try { await navigator.clipboard.writeText(onboardResult.value.edgecore); store.toast = 'edgecore.yaml 已复制' } catch (e) {} }

// ---- Tab5 实时数据 ----
const rtDevices = ref([])
const messages = ref([])
const pubForm = reactive({ topic: '', payload: '' })
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
async function doPublish() {
  try {
    const r = await api.boxPublish(pubForm.topic, pubForm.payload)
    store.toast = r.ok ? `已发布到 ${r.topic}` : '发布失败：' + (r.error || '')
    await loadMessages()
  } catch (e) { store.toast = '发布失败：' + (e.message || e) }
}

async function refreshAll() {
  await Promise.allSettled([loadOverview(), loadDevices(), loadRealtime(), loadMessages()])
}
// 快速轮询：按当前页签只拉取需要的数据，减少无效请求
async function refreshFast() {
  const t = tab.value
  if (t === 'overview') await loadOverview()
  else if (t === 'devices') await loadDevices()
  else if (t === 'realtime') { await loadRealtime(); await loadMessages() }
}

// ---- 格式化 / 图表 ----
function fmtPrimary(v) {
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

// 关闭视图
const close = () => store.toggleBoxManage()
function switchTab(id) {
  tab.value = id
  // 切页签后立即刷新对应数据，不等下一次轮询
  if (id === 'overview') loadOverview()
  else if (id === 'devices') { loadDevices(); loadDeviceLibrary() }
  else if (id === 'realtime') { loadRealtime(); loadMessages() }
}

// 暴露给视图工具栏（RibbonToolbar）：刷新数据 / 切换页签 / 当前页签
defineExpose({ refreshAll, switchTab, close, tab })
</script>

<style scoped>
.cbx-view {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  background: var(--panel-2);
  color: var(--text);
  user-select: none;
  overflow: hidden;
}
/* ---- 主体（页签导航 / 关闭 / 刷新等操作已由顶栏工具栏提供） ---- */
.cbx-body { flex: 1 1 auto; padding: 14px; overflow: auto; display: flex; flex-direction: column; gap: 14px; }
.cbx-grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.cbx-sec { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
.cbx-sec-head { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.cbx-sec-head b { font-size: 12.5px; font-weight: 600; }
.cbx-sec-sub { color: var(--muted); font-size: 10.5px; }
.cbx-sec-hint { margin-left: auto; font-size: 10.5px; color: var(--muted); }
.cbx-tag { font-size: 9.5px; color: var(--muted); background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 0 7px; }
.cbx-tag.ok { color: #2e8b57; background: rgba(58,157,93,.12); border-color: rgba(58,157,93,.35); }
.cbx-tag.demo { color: #c7a14b; background: rgba(199,161,75,.12); border-color: rgba(199,161,75,.35); }

/* ---- MQTT 状态 ---- */
.cbx-mqtt {
  border: 1px solid var(--border); border-radius: 6px; background: var(--panel-2);
  padding: 8px 10px; display: flex; flex-direction: column; gap: 5px;
}
.cbx-mqtt.on { border-color: rgba(58,157,93,.5); background: rgba(58,157,93,.06); }
.cbx-mqtt-head { display: flex; align-items: center; gap: 8px; }
.cbx-mqtt-title { font-size: 11.5px; font-weight: 600; color: var(--text); }
.cbx-mqtt-status {
  margin-left: auto; font-size: 10px; padding: 1px 8px; border-radius: 8px;
  color: var(--muted); background: var(--panel); border: 1px solid var(--border);
}
.cbx-mqtt-status.on { color: #2e8b57; background: rgba(58,157,93,.12); border-color: rgba(58,157,93,.35); }
.cbx-mqtt-row { display: flex; align-items: center; gap: 6px; font-size: 10.5px; color: var(--muted); flex-wrap: wrap; }
.cbx-mqtt-row code {
  background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
  padding: 1px 6px; font-size: 10px; color: var(--accent2);
}
.cbx-mqtt-msg { display: flex; align-items: flex-start; gap: 6px; font-size: 10px; color: var(--muted); flex-direction: column; }
.cbx-mqtt-msg .cbx-mqtt-topic { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 1px 6px; color: var(--accent2); }
.cbx-mqtt-payload {
  width: 100%; max-height: 56px; overflow: hidden; font-size: 10px; line-height: 1.5;
  color: var(--faint); background: var(--panel); border-radius: 4px; padding: 4px 6px;
  word-break: break-all; font-family: var(--mono, ui-monospace, monospace);
}
.cbx-sep { color: var(--border); }

/* ---- 统计卡片 ---- */
.cbx-stats { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
.cbx-stat {
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px;
  padding: 8px 10px; display: flex; flex-direction: column; gap: 4px;
}
.cbx-stat span { font-size: 10px; color: var(--muted); }
.cbx-stat b { font-size: 16px; font-weight: 600; color: var(--accent2); font-variant-numeric: tabular-nums; }

/* ---- KV ---- */
.cbx-kv { display: flex; flex-direction: column; gap: 6px; }
.cbx-kv > div { display: flex; align-items: center; gap: 8px; font-size: 11px; }
.cbx-kv span { color: var(--muted); width: 110px; flex: none; }
.cbx-kv code {
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px;
  padding: 1px 6px; font-size: 10px; color: var(--accent2);
}
.cbx-kv code.wrap { word-break: break-all; }
.cbx-kv b.ok { color: #2e8b57; }

/* ---- 表格 ---- */
.cbx-table { width: 100%; border-collapse: collapse; font-size: 10.5px; }
.cbx-table th, .cbx-table td {
  text-align: left; padding: 5px 8px; border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.cbx-table th { color: var(--muted); font-weight: 500; font-size: 10px; background: var(--panel-2); }
.cbx-table td code {
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px;
  padding: 0 5px; font-size: 10px; color: var(--accent2);
}
.cbx-table td.val { color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums; }
.cbx-empty-td { text-align: center; color: var(--faint); padding: 18px !important; }
.cbx-dot {
  display: inline-block; width: 7px; height: 7px; border-radius: 50%;
  background: #d9534f; margin-right: 5px; vertical-align: middle;
}
.cbx-dot.on { background: #3a9d5d; }

/* ---- 关联管理 ---- */
.cbx-note { font-size: 10.5px; color: var(--muted); line-height: 1.7; margin-bottom: 8px; }
.cbx-note b { color: var(--text); }
.cbx-empty {
  font-size: 11px; color: var(--faint); background: var(--panel-2);
  border: 1px dashed var(--border); border-radius: 6px; padding: 16px; line-height: 1.7; text-align: center;
}
.cbx-group { margin-bottom: 10px; }
.cbx-group:last-child { margin-bottom: 0; }
.cbx-group-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 5px;
  font-size: 11px; color: var(--accent2); font-weight: 600;
}
.cbx-group-box { background: var(--accent-l); border-radius: 8px; padding: 1px 8px; }
.cbx-group-count { font-size: 10px; color: var(--faint); font-weight: 400; }
.cbx-row {
  display: flex; align-items: center; gap: 8px; padding: 6px 8px; border-radius: 6px;
  background: var(--panel-2); border: 1px solid var(--border); font-size: 11px; margin-bottom: 5px; flex-wrap: wrap;
}
.cbx-row.linked { border-color: rgba(58,157,93,.45); background: rgba(58,157,93,.08); }
.cbx-dev { display: flex; align-items: center; gap: 8px; min-width: 0; flex: 1 1 auto; flex-wrap: wrap; }
.cbx-dev-id { font-weight: 600; color: var(--text); font-family: var(--mono, ui-monospace, monospace); }
.cbx-dev-val { color: var(--accent); font-weight: 600; font-variant-numeric: tabular-nums; }
.cbx-dev-fields { font-size: 9.5px; color: var(--muted); background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 0 6px; }
.cbx-dev-seen { font-size: 9.5px; color: var(--faint); }
.cbx-arrow { color: var(--faint); }
.cbx-local { color: var(--accent); font-weight: 600; }

/* ---- 表单 ---- */
.cbx-form { display: flex; flex-direction: column; gap: 8px; }
.cbx-form-row { display: flex; align-items: center; gap: 8px; font-size: 11px; flex-wrap: wrap; }
.cbx-form-row label { color: var(--muted); flex: none; }
.cbx-input {
  border: 1px solid var(--border); border-radius: 5px; background: var(--panel-2);
  color: var(--text); font-size: 11px; padding: 4px 7px; outline: none;
}
.cbx-input:focus { border-color: var(--accent); }
.cbx-select {
  border: 1px solid var(--border); border-radius: 5px; background: var(--panel);
  color: var(--text); font-size: 11px; padding: 3px 6px; outline: none; max-width: 240px;
}
.cbx-select:focus { border-color: var(--accent); }
.cbx-prop-row {
  display: flex; align-items: center; gap: 6px; padding: 5px 8px; margin-bottom: 5px;
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; flex-wrap: wrap;
}
.cbx-op {
  font-size: 10.5px; color: var(--accent); background: var(--accent-l);
  border: 1px solid var(--accent-l); border-radius: 5px; padding: 3px 12px; cursor: pointer;
  transition: all .15s; flex: 0 0 auto;
}
.cbx-op:hover:not(:disabled) { border-color: var(--accent); }
.cbx-op:disabled { opacity: .4; cursor: not-allowed; }
.cbx-op.danger { color: #d9534f; background: rgba(217,83,79,.08); border-color: rgba(217,83,79,.25); }
.cbx-op.danger:hover { background: rgba(217,83,79,.16); border-color: #d9534f; }
.cbx-op.primary { color: #fff; background: var(--accent); border-color: var(--accent); }
.cbx-op.primary:hover:not(:disabled) { filter: brightness(1.1); }

/* ---- YAML / 代码块 ---- */
.cbx-preview { margin-top: 10px; }
.cbx-preview-head { display: flex; align-items: center; gap: 8px; margin-bottom: 5px; }
.cbx-preview-head b { font-size: 11px; color: var(--muted); }
.cbx-code {
  background: #0d1420; border: 1px solid var(--border); border-radius: 6px;
  color: #b8d4f0; font-size: 10px; line-height: 1.6; padding: 10px 12px;
  overflow: auto; max-height: 300px; white-space: pre;
  font-family: var(--mono, ui-monospace, monospace);
}

/* ---- 盒子接入 ---- */
.cbx-onboard { margin-top: 12px; display: flex; flex-direction: column; gap: 8px; }

/* ---- 实时数据 ---- */
.cbx-twin-card {
  border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2);
  margin-bottom: 10px; padding: 8px 10px;
}
.cbx-twin-head { display: flex; align-items: center; gap: 10px; margin-bottom: 6px; }
.cbx-twin-head b { font-size: 12px; }
.cbx-twin-head code { color: var(--accent2); }
.cbx-spark { width: 100px; height: 24px; }
.cbx-spark-cell { width: 110px; }
.cbx-faint { color: var(--faint); }

/* ---- 消息流 ---- */
.cbx-msglog {
  display: flex; flex-direction: column; gap: 3px;
  max-height: 240px; overflow: auto; background: var(--panel-2);
  border: 1px solid var(--border); border-radius: 6px; padding: 6px;
}
.cbx-msgrow { display: flex; align-items: center; gap: 8px; font-size: 10px; }
.cbx-msgtime { color: var(--faint); flex: none; font-variant-numeric: tabular-nums; }
.cbx-msg-topic {
  flex: none; color: var(--accent2); background: var(--panel);
  border: 1px solid var(--border); border-radius: 4px; padding: 0 5px;
}
.cbx-msg-payload { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

/* ---- 接入指引 ---- */
.cbx-guide-flow { display: flex; align-items: stretch; gap: 10px; margin: 8px 0; flex-wrap: wrap; }
.cbx-flow-node {
  flex: 1 1 0; min-width: 130px; text-align: center; font-size: 11.5px; font-weight: 600;
  background: var(--accent-l); border: 1px solid var(--accent-l); border-radius: 8px; padding: 10px 8px;
}
.cbx-flow-node span { display: block; font-size: 9.5px; color: var(--muted); font-weight: 400; margin-top: 4px; }
.cbx-flow-arrow { display: flex; align-items: center; color: var(--faint); font-size: 16px; }

.cbx-badge { font-size: 9.5px; border-radius: 4px; padding: 0 6px; }
.cbx-badge.model { color: #c7a14b; background: rgba(199,161,75,.12); }
.cbx-badge.device { color: #5aa2e0; background: rgba(90,162,224,.12); }

/* ---- Broker 配置弹窗 ---- */
.cbx-mask {
  position: fixed; inset: 0; z-index: 300; background: rgba(0,0,0,.45);
  display: flex; align-items: center; justify-content: center;
}
.cbx-dialog {
  width: 560px; max-width: 92vw; background: var(--panel);
  border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px;
  box-shadow: 0 12px 40px rgba(0,0,0,.4);
}
.cbx-dialog-head { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.cbx-dialog-head b { font-size: 13px; font-weight: 600; }
.cbx-dialog-head .cbx-op { margin-left: auto; }
</style>
