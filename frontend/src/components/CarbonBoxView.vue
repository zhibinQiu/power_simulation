<template>
  <!-- ============ 数据源管理视图（能碳一体机 + 外部数据源统一接入；云端 K3s/KubeEdge 管理、设备 CRUD、盒子接入） ============ -->
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
              <span class="cbx-tree-arrow">{{ expanded.boxes ? '▾' : '▸' }}</span> {{ t('盒子节点') }}
              <span class="cbx-tree-count">{{ topoBoxes.length }}</span>
            </div>
            <div v-show="expanded.boxes" class="cbx-tree-children">
              <div v-for="b in topoBoxes" :key="b.name" class="cbx-tree-node">
                <div class="cbx-tree-row" @click="expanded['box-' + b.name] = !expanded['box-' + b.name]">
                  <span class="cbx-tree-arrow">{{ expanded['box-' + b.name] ? '▾' : '▸' }}</span>
                  <span class="cbx-dot" :class="{ on: readyOk(b.ready) }"></span>
                  <span class="cbx-tree-label" :title="b.name">{{ boxName(b) }}</span>
                  <span class="cbx-tree-tag" :class="{ ok: readyOk(b.ready), err: b.ready === false }">{{ readyZh(b.ready) }}</span>
                </div>
                <div v-show="expanded['box-' + b.name]" class="cbx-tree-children">
                  <div v-for="d in boxDevices(b)" :key="d.name" class="cbx-tree-leaf" @click="onDevClick(d)" :title="(d._cloud ? t('云端设备（点击查看实时）') : t('待下发设备（点击编辑配置）')) + '：' + d.name + (modelOf(d) ? '（' + t('模型') + ' ' + modelOf(d) + '）' : '')">
                    <span class="cbx-dot" :class="{ on: d.state === 'online' }"></span><span class="cbx-tree-label">{{ d.name }}</span><span class="cbx-tree-tag" v-if="modelOf(d)">{{ modelOf(d) }}</span>
                  </div>
                  <div v-if="!boxDevices(b).length" class="cbx-tree-empty">{{ t('暂无设备') }}</div>
                </div>
              </div>
              <div v-if="topoUnmounted.length" class="cbx-tree-node">
                <div class="cbx-tree-row" @click="expanded.unmounted = !expanded.unmounted">
                  <span class="cbx-tree-arrow">{{ expanded.unmounted ? '▾' : '▸' }}</span>
                  <span class="cbx-tree-label">{{ t('未挂载') }}</span><span class="cbx-tree-count">{{ topoUnmounted.length }}</span>
                </div>
                <div v-show="expanded.unmounted" class="cbx-tree-children">
                  <div v-for="d in topoUnmounted" :key="d.name" class="cbx-tree-leaf" @click="openDevRealtime(d)">{{ d.name }}</div>
                </div>
              </div>
            </div>
            <div class="cbx-tree-sec" @click="expanded.models = !expanded.models">
              <span class="cbx-tree-arrow">{{ expanded.models ? '▾' : '▸' }}</span> {{ t('模型') }}
              <span class="cbx-tree-count">{{ mergedModels.length }}</span>
            </div>
            <div v-show="expanded.models" class="cbx-tree-children">
              <div v-for="m in mergedModels" :key="m.name" class="cbx-tree-leaf" @click="openEditModel(m)" :title="t('模型（点击修改点位）') + '：' + m.name">▦ {{ m.name }}<span class="cbx-tree-tag" v-if="modelPropCount(m)">{{ modelPropCount(m) }} {{ t('属性') }}</span></div>
              <div v-if="!mergedModels.length" class="cbx-tree-empty">{{ t('暂无模型') }}</div>
            </div>
            <div class="cbx-tree-sec" @click="expanded.devs = !expanded.devs">
              <span class="cbx-tree-arrow">{{ expanded.devs ? '▾' : '▸' }}</span> {{ t('设备') }}
              <span class="cbx-tree-count">{{ mergedDevices.length }}</span>
            </div>
            <div v-show="expanded.devs" class="cbx-tree-children">
              <div v-for="d in mergedDevices" :key="d.name" class="cbx-tree-leaf" @click="onDevClick(d)" :title="(d._cloud ? t('云端设备（点击查看实时）') : t('待下发设备（点击编辑配置）')) + '：' + d.name + (modelOf(d) ? '（' + t('模型') + ' ' + modelOf(d) + '）' : '')">
                <span class="cbx-dot" :class="{ on: d.state === 'online' }"></span>{{ d.name }}<span class="cbx-tree-tag" v-if="modelOf(d)">{{ modelOf(d) }}</span>
              </div>
              <div v-if="!mergedDevices.length" class="cbx-tree-empty">{{ t('暂无设备') }}</div>
            </div>
          </div>
        </div>
      </aside>
      <!-- 主编辑区（单页：通信拓扑图 + 各功能区，无 tab） -->
      <main class="cbx-main">
        <div class="cbx-editor">
          <!-- ===== 概览页 ===== -->
          <section class="cbx-page">
        <!-- 0 运行状态总览：面向非技术人员的“一眼式”健康摘要；下方所有专业区块功能均保留 -->
        <section class="cbx-hero">
          <div class="cbx-sec-head">
            <button class="cbx-caret" @click="toggleSec('overview')" :title="secFold.overview ? t('收起') : t('展开')">{{ secFold.overview ? '▾' : '▸' }}</button>
            <b class="cbx-sec-toggle" @click="toggleSec('overview')">{{ t('运行状态总览') }}</b>
          </div>
          <!-- 区块介绍：展开后显示，标题栏只留标题与操作 -->
          <div v-if="secFold.overview" class="cbx-sec-desc">{{ t('一眼式健康摘要：全绿即一切正常') }}</div>
          <div v-if="secFold.overview" class="cbx-hero-main">
            <div class="cbx-hero-verdict" :class="'tone-' + hero.tone">
              <span class="cbx-hero-ic">{{ hero.icon }}</span>
              <div class="cbx-hero-tt">
                <b>{{ hero.title }}</b>
                <p>{{ hero.desc }}</p>
              </div>
            </div>
            <button class="cbx-op cbx-xs cbx-guide-btn" @click="toggleGuide"
                    >{{ guideOpen ? t('收起指引') : t('使用指引') }}</button>
            <div class="cbx-hero-stats">
              <div class="cbx-hero-stat" :class="'tone-' + heroCloud.cls" :title="t('云端服务器连接与数据推送状态')">
                <b>{{ heroCloud.txt }}</b><span>{{ t('云端服务') }}</span>
              </div>
              <div class="cbx-hero-stat click" :class="'tone-' + heroBox.cls" @click="scrollToSec('box')" :title="t('在线盒子数 / 总数（点击查看盒子列表）')">
                <b>{{ heroBox.txt }}</b><span>{{ t('盒子在线') }}</span>
              </div>
              <div class="cbx-hero-stat click" :class="'tone-' + heroDev.cls" @click="scrollToSec('dev')" :title="t('正在上报数据的设备 / 全部设备（点击查看设备列表）')">
                <b>{{ heroDev.txt }}</b><span>{{ t('设备上传中') }}</span>
              </div>
              <div class="cbx-hero-stat" :class="'tone-' + heroMsg.cls" :title="t('近 3 秒收到的设备消息条数')">
                <b>{{ heroMsg.n }}</b><span>{{ t('实时消息') }}</span>
              </div>
            </div>
          </div>
          <!-- 使用指引：首次进入自动展开，点“知道了”后记住不再打扰 -->
          <div v-if="secFold.overview && guideOpen" class="cbx-guide">
            <div class="cbx-guide-title">
              <b>{{ t('快速使用指引') }}</b>
              <span class="cbx-guide-sub">{{ t('面向非技术人员的快速使用说明') }}</span>
              <span class="cbx-sec-spacer"></span>
              <button class="cbx-op cbx-xs" @click="closeGuide" :title="t('不再显示')">✕</button>
            </div>
            <ol class="cbx-guide-steps">
              <li>{{ t('本页管理部署在车间现场的「边缘采集盒子」：盒子负责把现场电表 / 传感器等设备的数据采集后上传到云端，再展示到这里。') }}</li>
              <li>{{ t('日常只需看顶部「运行状态」：全部为绿色说明一切正常，无需任何操作。') }}</li>
              <li>{{ t('查看某台设备的最新读数：点击左侧「设备导航」或下方「采集设备」卡片中的设备名，即可打开实时曲线。') }}</li>
              <li>{{ t('添加一台新设备：点击「＋ 设备」按提示填写即可；接入新盒子：点击「盒子接入」。') }}</li>
              <li>{{ t('「证书与密钥 / 命令执行」等区块仅供专业维护排查，日常可忽略。') }}</li>
            </ol>
            <button class="cbx-op cbx-xs" style="margin-top:8px" @click="closeGuide">{{ t('知道了，不再显示') }}</button>
          </div>
        </section>

        <!-- 云端状态全局提示（集中展示，避免下方各区块重复出现“云端不可达”tag） -->
        <div class="cbx-banner" :class="overview.cloud_source === 'degraded' ? 'warn' : 'err'"
             v-if="overview.cloud_source && overview.cloud_source !== 'live'">
          <template v-if="overview.cloud_source === 'stale'">{{ t('⚠ 云端推送已中断：当前节点/CloudCore 状态为过期缓存，非实时数据。') }}{{ overview.cloud_error }}</template>
          <template v-else-if="overview.cloud_source === 'degraded'">{{ t('⚠ 云端部分服务异常：以下云端数据可能为缓存或不完整。') }}</template>
          <template v-else>{{ t('⚠ 云端不可达：以下云端数据不可用。请检查云端服务（cloud-agent / CloudHub 10002 / MQTT 41883）。') }}</template>
          <template v-if="overview.demo_note">{{ overview.demo_note }}</template>
        </div>
        <!-- ① 数据源接入（合并自原「工具 >> 数据源…」弹窗）：能碳一体机 + 外部数据源（含模拟数据）
             统一为数据源接入视图——一体机数据经云端 Broker 订阅通道进入；外部数据（含独立模拟源）
             注册到数据中间件后由中间件转换为标准 MQTT 发布到云端 Broker；两者同 Broker 按 box
             前缀区分，共用同一条摄取管道（平台与中间件自身都不产生模拟数据） -->
        <section id="cbx-sec-sources" class="cbx-sec cbx-sec-sources">
          <div class="cbx-sec-head">
            <button class="cbx-caret" @click="toggleSec('sources')" :title="secFold.sources ? t('收起') : t('展开')">{{ secFold.sources ? '▾' : '▸' }}</button>
            <b class="cbx-sec-toggle" @click="toggleSec('sources')">🔌 {{ t('数据源接入') }}</b>
            <span class="cbx-sec-spacer"></span>
            <button class="cbx-op primary cbx-xs" @click="openAddForm()">＋ {{ t('注册外部数据源') }}</button>
          </div>
          <div v-if="secFold.sources" class="cbx-sec-desc">{{ t('能碳一体机（云端 Broker 订阅）与外部数据源统一在此接入；平台按 box 前缀自动区分一体机与外部源') }}</div>
          <div v-if="secFold.sources">

          <!-- 卡片网格：能碳一体机（默认来源）+ 各外部数据源 -->
          <div class="ds-grid">
            <!-- 能碳一体机：云端 Broker 订阅通道（平台无独立运行线程，enabled 控制是否采纳盒子数据） -->
            <div v-if="boxEntry" class="ds-card" :class="{ off: !boxSrc.enabled }">
              <div class="ds-card-hd">
                <b>{{ boxSrc.name }}</b>
                <span class="ds-tag builtin">内置</span>
                <span class="ds-tag">{{ t('云端订阅通道') }}</span>
                <span class="cbx-sec-spacer"></span>
                <label class="ds-switch" :title="boxSrc.enabled ? t('停用：盒子实时数据不再驱动仿真') : t('启用：盒子实时数据恢复驱动仿真')">
                  <input type="checkbox" :checked="boxSrc.enabled" @change="toggleSource(boxSrc, $event)" />
                  <i></i><span>{{ boxSrc.enabled ? t('启用') : t('停用') }}</span>
                </label>
              </div>
              <div class="ds-desc">{{ boxSrc.desc }}</div>
              <div class="ds-rows">
                <div class="ds-row"><span>{{ t('连接状态') }}</span>
                  <b :class="boxSt.connected ? 'ok' : 'err'">
                    {{ boxSt.connected ? '● ' + t('已连接') : (boxSt.connected === false ? '● ' + t('未连接') : '—') }}
                    <template v-if="boxSt.message_count != null"> · {{ t('累计消息') }} {{ boxSt.message_count }}</template>
                  </b>
                </div>
                <div class="ds-row"><span>{{ t('订阅端点') }}</span>
                  <!-- 注意：v-if 不可与 v-for 写在同一元素上（Vue3 中 v-if 先求值，此时 es 未定义会抛错导致整页白屏）；
                       改为 template 承载 v-for、内层元素承载 v-if -->
                  <span class="ds-endps"><template v-for="(es, ek) in boxSt.endpoints || {}" :key="ek"><i
                    v-if="es && es.enabled !== false"
                    :class="['ds-ep', ek, es.connected ? 'on' : 'off']"
                    :title="(ek === 'cloud' ? t('云端 Broker（一体机）') : t('中间件 Broker（外部数据）')) + '：' + ((es.host ? es.host + ':' + es.port : es.label || '—'))">
                    {{ ek === 'cloud' ? '☁ ' + t('云端') : '⇄ ' + t('中间件') }}
                  </i></template></span>
                </div>
                <div class="ds-row"><span>{{ t('设备读数') }}</span>
                  <b>{{ boxSt.cloud_devices ?? 0 }} {{ t('台设备') }} · {{ boxSt.readings ?? 0 }} {{ t('条读数') }} · {{ boxSt.links ?? 0 }} {{ t('个关联') }}</b>
                </div>
                <div class="ds-row" v-if="boxLastMsg"><span>{{ t('最近消息') }}</span><b class="dim">{{ boxLastMsg }}</b></div>
                <div class="ds-row" v-if="boxSt.broker_host"><span>{{ t('Broker') }}</span><b class="dim mono">{{ boxSt.broker_host }}:{{ boxSt.broker_port }}</b></div>
              </div>
              <div class="ds-ops">
                <button class="cbx-op cbx-xs" @click="openBoxConfig"
                        :title="t('配置云端 Broker 地址/账号，保存后自动热更新重连')">⚙ {{ t('云端配置') }}</button>
                <button class="cbx-op cbx-xs" @click="scrollToSec('box')"
                        >{{ t('盒子列表') }}</button>
                <span class="cbx-sec-spacer"></span>
                <button class="cbx-op cbx-xs danger" @click="removeSource(boxSrc)"
                        :title="t('删除后平台立即停止采纳盒子上报数据，可随时恢复')">🗑 {{ t('删除') }}</button>
              </div>
            </div>

            <!-- 内置源被删除后的恢复入口（内置源与外部源统一管理：可删、可恢复） -->
            <div v-else class="ds-card ds-empty" @click="restoreBox">
              <div class="ds-empty-ic">☁</div>
              <b>{{ t('能碳一体机（内置数据源）已删除') }}</b>
              <p>{{ t('删除后平台不再采纳盒子上报数据（重启也不会自动补建）。点击此处恢复该内置数据源并重新启用。') }}</p>
              <button class="cbx-op cbx-xs">＋ {{ t('恢复内置数据源') }}</button>
            </div>

            <!-- 外部数据源（含独立模拟源）：注册到中间件，转换后经平台订阅通道按前缀识别 -->
            <div v-for="s in extSources" :key="s.id" class="ds-card"
                 :class="{ off: !s.enabled, mwdown: mwChecked && !mwOnline && !s.status.running }">
              <div class="ds-card-hd">
                <b>{{ s.name }}</b>
                <span class="ds-tag">{{ s.config.adapter_label }}</span>
                <span class="ds-tag mono">{{ s.config.box }}</span>
                <span class="cbx-sec-spacer"></span>
                <label class="ds-switch" :title="s.enabled ? t('停用：中间件停止采集该数据源') : t('启用：中间件开始采集该数据源')">
                  <input type="checkbox" :checked="s.enabled" @change="toggleSource(s, $event)" />
                  <i></i><span>{{ s.enabled ? t('启用') : t('停用') }}</span>
                </label>
              </div>
              <div class="ds-desc">{{ s.config.desc || (s.status && s.status.kind === 'external' ? t('外部数据源：数据先接入能碳一体机，由一体机上行到云端 ext/#，再经云端数据中间件转换为 data/ext-* 被平台识别') : '') }}</div>
              <div class="ds-rows">
                <div class="ds-row"><span>{{ t('运行状态') }}</span>
                  <b :class="s.status.running ? 'ok' : 'err'">
                    {{ s.status.running ? '● ' + t('采集运行中') : (s.status.mw_online === false ? '● ' + t('中间件未运行') : (s.status.mw_online ? '● ' + t('采集已停止') : '● ' + t('状态未知'))) }}
                    <template v-if="s.status.received != null"> · {{ t('已收') }} {{ s.status.received }} {{ t('条') }}</template>
                  </b>
                </div>
                <div class="ds-row"><span>{{ t('平台取数') }}</span>
                  <b :class="s.status.active ? 'ok' : 'dim'">
                    {{ s.status.active ? '● ' + t('数据实时到达') : (s.status.received ? t('最近数据已停 ' + agoText(s.status.last_at)) : t('尚未收到数据')) }}
                  </b>
                </div>
                <div class="ds-row" v-if="s.status.cloud_devices != null"><span>{{ t('设备读数') }}</span>
                  <b>{{ s.status.cloud_devices }} {{ t('台设备') }}<template v-if="s.status.last_topic"> · <span class="mono dim">{{ s.status.last_topic }}</span></template></b>
                </div>
                <div class="ds-row" v-if="s.status && s.status.note"><span>{{ t('提示') }}</span><b class="note">{{ s.status.note }}</b></div>
              </div>
              <div class="ds-ops">
                <button class="cbx-op cbx-xs" @click="openEditForm(s)">✎ {{ t('编辑') }}</button>
                <button class="cbx-op cbx-xs" :disabled="s.testing" @click="testSource(s)">{{ s.testing ? t('测试中…') : '⛁ ' + t('测试') }}</button>
                <span class="cbx-sec-spacer"></span>
                <button class="cbx-op cbx-xs danger" @click="removeSource(s)">🗑 {{ t('删除') }}</button>
              </div>
            </div>

            <!-- 空态：无外部数据源时给出引导（含模拟数据注册入口） -->
            <div v-if="!extSources.length" class="ds-card ds-empty" @click="openAddForm('mqtt')">
              <div class="ds-empty-ic">⇄</div>
              <b>{{ t('尚无外部数据源') }}</b>
              <p>{{ t('外部 MQTT / 数据中台 / 模拟数据源（独立服务 sim-source）等先接入能碳一体机，由一体机上行到云端 ext/#，再经云端数据中间件转换为 data/ext-* 进入平台订阅通道。点击此处注册第一条（外部 MQTT 类型）。') }}</p>
              <button class="cbx-op cbx-xs">＋ {{ t('注册外部数据源') }}</button>
            </div>
          </div>

          <!-- 注册 / 编辑表单 -->
          <div v-if="formOpen" class="ds-form">
            <div class="cbx-form-row">
              <b class="ds-form-title">{{ extForm.id ? t('编辑外部数据源') + '：' + extForm.id : t('注册外部数据源') }}</b>
              <span class="cbx-sec-spacer"></span>
              <span class="ds-form-hint">{{ t('注册到数据中间件（type=') }}{{ extForm.adapter }}）；{{ t('模拟数据源（独立服务 sim-source）用「外部 MQTT」类型：Broker 127.0.0.1:41885，主题 steel/# 或 idc/#') }}</span>
            </div>
            <div class="cbx-form-row">
              <label>{{ t('名称') }}</label>
              <input v-model="extForm.name" class="cbx-input" style="flex:1" :placeholder="t('如 一号炉烟气在线 / 模拟产线')" />
              <label>{{ t('接入类型') }}</label>
              <select v-model="extForm.adapter" class="cbx-input" style="width:170px" @change="onAdapterChange">
                <option v-for="at in adapterTypes" :key="at.type" :value="at.type">{{ at.label }}</option>
              </select>
            </div>
            <div class="cbx-form-row">
              <label>{{ t('发布前缀') }}</label>
              <input v-model="extForm.box" class="cbx-input mono" style="flex:1" :placeholder="t('如 ext-weigh')" :title="t('小写字母/数字/连字符；平台按此前缀识别归属、启停过滤')" />
            </div>
            <div class="cbx-form-row" v-if="extForm.fields.length">
              <label>{{ t('接入参数') }}</label>
              <div class="ds-fields">
                <template v-for="f in extForm.fields" :key="f.name">
                  <div class="ds-fld" v-if="f.type === 'bool'">
                    <label class="ds-switch" :title="f.label">
                      <input type="checkbox" v-model="f.v" /><i></i><span>{{ f.label }}</span>
                    </label>
                  </div>
                  <div class="ds-fld" v-else>
                    <label :title="f.desc">{{ f.label }}<template v-if="f.required"> *</template></label>
                    <input v-if="!isJsonLike(f.type)" :type="f.type === 'password' ? 'password' : 'text'"
                           v-model="f.v" class="cbx-input" :placeholder="f.placeholder || ''" />
                    <textarea v-else v-model="f.v" rows="2" class="cbx-input mono"
                              :placeholder='f.placeholder || ((f.type === "array" || f.type === "list") ? "[\"topic1\", \"topic2\"]" : "[{…}]")'></textarea>
                    <span v-if="f.desc && f.desc !== f.label" class="ds-fld-desc">{{ f.desc }}</span>
                  </div>
                </template>
              </div>
            </div>
            <div class="cbx-form-row">
              <label>{{ t('说明') }}</label>
              <input v-model="extForm.desc" class="cbx-input" style="flex:1" />
            </div>
            <div v-if="extFormErr" class="ds-form-err">{{ extFormErr }}</div>
            <div class="cbx-form-row">
              <span class="cbx-sec-spacer"></span>
              <button class="cbx-op" @click="testForm()">{{ t('测试连接') }}</button>
              <button class="cbx-op primary" :disabled="formSaving" @click="saveForm()">
                {{ formSaving ? t('保存中…') : (extForm.id ? t('保存并同步中间件') : t('注册并保存')) }}
              </button>
              <button class="cbx-op" @click="closeForm()">{{ t('取消') }}</button>
            </div>
          </div>
          </div>
        </section>

        <!-- ② 通信拓扑图：以「设备」为单位（平台服务器 / 云端服务器 / 能碳一体机 / 现场设备 / 外部数据系统），
             服务运行在设备内部，连线只表示设备之间的通道 -->
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <button class="cbx-caret" @click="toggleSec('topo')" :title="secFold.topo ? t('收起') : t('展开')">{{ secFold.topo ? '▾' : '▸' }}</button>
            <b class="cbx-sec-toggle" @click="toggleSec('topo')">{{ t('系统连接图') }}</b>
            <span class="cbx-sec-spacer"></span>
            <button class="cbx-op cbx-xs" @click="autoLayoutTopo()" :title="t('恢复自动布局，清除所有模块的手动拖拽位置')">{{ t('自动布局') }}</button>
          </div>
          <div v-if="secFold.topo" class="cbx-sec-desc">
            {{ t('按设备划分：每张卡片是一台设备（服务器 / 一体机 / 传感器 / 外部系统），卡内列出该设备上运行的服务；连线表示设备之间的数据通道') }}
            <span class="cbx-sec-desc-extra">{{ t('拖动设备卡片可自定义布局，连线自动跟随') }}</span>
          </div>
          <div v-if="secFold.topo">
          <!-- 链路说明：能碳一体机是现场唯一接入点（下接传感器/仪表、后接外部数据系统），
               一体机把收到的数据统一上报云端服务器；外部数据在云端经中间件（云端服务器内部服务）转换后交给平台 -->
          <div class="cbx-topo-legend">
            <span class="leg"><i class="lg g"></i>{{ t('传感器链路：现场设备（传感器/仪表） —RS485/Modbus→ 能碳一体机 —MQTT data/#→ 云端服务器 → 平台服务器') }}</span>
            <span class="leg"><i class="lg b"></i>{{ t('外部数据链路：外部数据系统（PLC/数据中台/模拟源）—以太网/OPC→ 能碳一体机 —MQTT ext/#→ 云端服务器（再由云端中间件转 data/ext-*）→ 平台服务器；云边管理通道 CloudHub :10002 双向') }}</span>
            <span class="leg"><i class="lg r"></i>{{ t('平台下行：平台服务器 → 云端服务器（cloud-agent HTTP :42083，kubectl 下发 / 重启等写操作）') }}</span>
          </div>
          <div ref="topoCanvasRef" class="cbx-topo cbx-topo-canvas">
            <div class="cbx-topo-lanes">
              <!-- 设备①：平台服务器（运行工业能碳智控平台，卡内为平台自身服务） -->
              <div class="cbx-topo-lane host-lane">
                <div class="cbx-topo-lane-title">{{ t('平台服务器') }}</div>
                <div :ref="setNodeRef('d_platform')" class="cbx-topo-mod device platform">
                  <div class="cbx-topo-dev-hd">
                    <span class="cbx-topo-dev-ic">🖥</span>
                    <div class="cbx-topo-dev-meta">
                      <b class="cbx-topo-dev-title">{{ t('工业能碳智控平台') }}</b>
                      <span class="cbx-topo-dev-addr mono">{{ platformHost }}</span>
                    </div>
                    <span class="cbx-topo-mod-badge ok">{{ t('运行中') }}</span>
                  </div>
                  <div class="cbx-topo-svcs">
                    <div class="cbx-topo-svc" :title="t('平台 Web 控制台（本页）') + '\n' + platformHost + '\n' + t('点击在新标签页打开')">
                      <span class="cbx-topo-svc-dot on"></span>
                      <span class="cbx-topo-svc-name">{{ t('Web 前端') }}</span>
                      <a class="cbx-topo-svc-addr mono" :href="httpOpenUrl(platformHost, '/')" target="_blank" rel="noopener"
                         :title="t('点击在新标签页打开') + ' ' + platformHost" @click.stop>{{ platformHost }}</a>
                    </div>
                    <div class="cbx-topo-svc" :title="t('平台后端服务：设备/盒子管理、数据接入与对外 API') + '\n' + platformHost + '/api\n' + t('点击在新标签页打开')">
                      <span class="cbx-topo-svc-dot on"></span>
                      <span class="cbx-topo-svc-name">{{ t('平台后端') }}</span>
                      <a class="cbx-topo-svc-addr mono" :href="httpOpenUrl(platformHost, '/docs')" target="_blank" rel="noopener"
                         :title="t('点击在新标签页打开') + ' ' + platformHost + '/docs'" @click.stop>{{ platformHost }}</a>
                    </div>
                    <div class="cbx-topo-svc" :title="t('数据接入：订阅云端 Broker 的 data/#（一体机上报 + 中间件转换后的外部数据）') + '\n' + (brokerAddr || '—') + '\n' + t('MQTT 地址无法在浏览器直接打开')">
                      <span class="cbx-topo-svc-dot on"></span>
                      <span class="cbx-topo-svc-name">{{ t('数据接入') }}</span>
                      <span class="cbx-topo-svc-addr mono" :title="t('订阅') + ' ' + (brokerAddr || '—')">{{ brokerAddr || '—' }}</span>
                    </div>
                  </div>
                  <div class="cbx-topo-mod-ops">
                    <button class="cbx-op cbx-xs" @click="refreshAll(true)">⟳ {{ t('刷新') }}</button>
                  </div>
                </div>
              </div>
              <!-- 设备②：云端服务器（一台设备，卡内为云端运行的各项服务） -->
              <div class="cbx-topo-lane cloud-lane">
                <div class="cbx-topo-lane-title">{{ t('云端服务器') }}</div>
                <div :ref="setNodeRef('d_cloud')" class="cbx-topo-mod device cloud"
                     :class="{ down: !agentStatusOk || (overview.cloudcore && overview.cloudcore.phase !== 'Running') }">
                  <div class="cbx-topo-dev-hd">
                    <span class="cbx-topo-dev-ic">☁</span>
                    <div class="cbx-topo-dev-meta">
                      <b class="cbx-topo-dev-title" :title="t('云端服务器：CloudCore / cloud-agent / MQTT Broker / 数据中间件均运行在本机')">{{ t('云端服务器') }}</b>
                      <span class="cbx-topo-dev-addr mono">{{ cloudCfg.host || '—' }}</span>
                    </div>
                    <span class="cbx-topo-mod-badge" :class="{ ok: agentStatusOk }">{{ agentStatusOk ? t('在线') : t('离线') }}</span>
                  </div>
                  <!-- 设备内服务：均运行在本机，彼此之间为进程内/本机通信，不占用系统连接图连接线 -->
                  <div class="cbx-topo-svcs">
                    <div class="cbx-topo-svc" :title="t('云端 Broker :41883 —— 能碳一体机上报的唯一入口：传感器数据与外部数据系统数据都由一体机上报到本 Broker；外部数据先落在上行空间 ext/#，经云端数据中间件转换为 data/ext-* 后再由平台消费，按 box 前缀区分归属') + '\n' + (brokerAddr || '—') + '\n' + t('订阅') + ' ' + fmtNum(stats.subscriptions) + ' · ' + t('运行') + ' ' + fmtUptime(stats.uptime)">
                      <span class="cbx-topo-svc-dot on"></span>
                      <span class="cbx-topo-svc-name">{{ t('云端消息中心') }}</span>
                      <span class="cbx-topo-svc-addr mono" :title="brokerAddr || '—' + '\n' + t('MQTT 地址无法在浏览器直接打开')">{{ brokerAddr || '—' }}</span>
                      <span class="cbx-topo-svc-ops">
                        <button class="cbx-op cbx-tiny" :disabled="!!restartingKey" @click="restartBroker()" :title="t('重启云端 MQTT Broker（nengtan-cloud-broker systemd 服务，短暂断连后自动重连）')">{{ restartingKey === 'systemd:nengtan-cloud-broker' ? '…' : '↻' }}</button>
                      </span>
                    </div>
                    <div class="cbx-topo-svc" :class="{ off: !(overview.cloudcore && overview.cloudcore.phase === 'Running') }"
                         :title="'CloudCore · CloudHub :10002 · KubeEdge CRD' + '\n' + (cloudHubAddr || '—')">
                      <span class="cbx-topo-svc-dot" :class="{ on: overview.cloudcore && overview.cloudcore.phase === 'Running' }"></span>
                      <span class="cbx-topo-svc-name">{{ t('云边连接服务') }}</span>
                      <span class="cbx-topo-svc-addr mono" :title="'CloudHub ' + (cloudHubAddr || '—')">{{ cloudHubAddr || '—' }}</span>
                      <span class="cbx-topo-svc-ops">
                        <button class="cbx-op cbx-tiny" :disabled="!!restartingKey" @click="restartCloudcore()" :title="t('重启云端 kubeedge 命名空间下的 cloudcore 工作负载')">{{ restartingKey === 'deployment:cloudcore' ? '…' : '↻' }}</button>
                      </span>
                    </div>
                    <div class="cbx-topo-svc" :class="{ off: !agentStatusOk }" :title="'cloud-agent · HTTP :' + (cloudCfg.agent_port || 42083) + ' · Bearer' + '\n' + (agentAddr || '—') + '\n' + t('点击在新标签页打开')">
                      <span class="cbx-topo-svc-dot" :class="{ on: agentStatusOk }"></span>
                      <span class="cbx-topo-svc-name">{{ t('云端数据服务') }}</span>
                      <a class="cbx-topo-svc-addr mono" :href="httpOpenUrl(agentAddr, '/api/health')" target="_blank" rel="noopener"
                         :title="t('点击在新标签页打开') + ' ' + (agentAddr || '') + '/api/health'" @click.stop>{{ agentAddr || '—' }}</a>
                      <span class="cbx-topo-svc-ops">
                        <button class="cbx-op cbx-tiny" :disabled="!!restartingKey" @click="restartAgent()" :title="t('重启云端 cloud-agent systemd 服务（2 秒后自动拉起）')">{{ restartingKey === 'systemd:cloud-agent' ? '…' : '↻' }}</button>
                      </span>
                    </div>
                    <div class="cbx-topo-svc" :class="{ off: mwChecked && !mwOnline }"
                         :title="t('云端数据中间件：订阅云端 Broker 的上行空间 ext/#，把外部数据转换为标准主题 data/ext-* 后回写 Broker，平台按前缀识别归属；平台与中间件自身都不产生模拟数据') + '\n' + (mwAddr || '—')">
                      <span class="cbx-topo-svc-dot" :class="{ on: mwOnline }"></span>
                      <span class="cbx-topo-svc-name">{{ t('数据中间件') }}</span>
                      <a class="cbx-topo-svc-addr mono" :href="httpOpenUrl(mwAddr, '/api/health')" target="_blank" rel="noopener"
                         :title="t('点击在新标签页打开') + ' ' + (mwAddr || '') + '/api/health'" @click.stop>{{ mwAddr || '—' }}</a>
                      <span class="cbx-topo-svc-type">{{ mwOnline ? t('在线') : (mwChecked ? t('离线') : '—') }}</span>
                    </div>
                  </div>
                  <!-- 设备内部互联（本机通信，非系统级链路） -->
                  <div class="cbx-topo-inner">{{ t('本机内部：CloudCore → Broker（cloud/# 状态推送）· 中间件 ⇄ Broker（ext/# ⇄ data/ext-*）· agent 本地 kubectl') }}</div>
                  <div class="cbx-topo-mod-ops">
                    <button class="cbx-op cbx-xs" @click="openBoxConfig" :title="t('配置云端 Broker 地址/账号与 agent Token/端口，保存后自动热更新重连')">⚙ {{ t('云端配置') }}</button>
                  </div>
                </div>
              </div>
              <!-- 设备③：能碳一体机（每台一台设备，卡内为边缘运行时/采集服务/云端部署应用） -->
              <div class="cbx-topo-lane box-lane">
                <div class="cbx-topo-lane-title">{{ t('能碳一体机') }}<span class="cbx-sec-spacer"></span><button class="cbx-op cbx-xs" @click="openOnboard" :title="t('新盒子接入：生成 edgecore.yaml 配置。一体机同时承担两类接入：下接传感器/仪表、后接外部数据系统')">{{ t('盒子接入') }}</button></div>
                <div v-for="b in topoBoxes" :key="b.name" :ref="setBoxNodeRef(b.name)" class="cbx-topo-mod device box" :class="{ down: b.ready === false }">
                  <div class="cbx-topo-dev-hd">
                    <span class="cbx-topo-dev-ic">⬢</span>
                    <div class="cbx-topo-dev-meta">
                      <b class="cbx-topo-dev-title" :title="b.name">{{ boxName(b) }}</b>
                      <span class="cbx-topo-dev-addr mono" :title="b.name">{{ boxIpOf(b) || b.name }}</span>
                    </div>
                    <span class="cbx-topo-mod-badge" :class="{ ok: readyOk(b.ready), err: b.ready === false }">{{ readyZh(b.ready) }}</span>
                  </div>
                  <!-- 设备内服务 -->
                  <div class="cbx-topo-svcs">
                    <div class="cbx-topo-svc" :class="{ off: b.ready === false }"
                         :title="t('KubeEdge 边缘运行时：与云端 CloudHub 建立长连接，接收设备/应用下发并上报状态') + '\n→ ' + (cloudHubAddr || '—')">
                      <span class="cbx-topo-svc-dot" :class="{ on: b.ready !== false }"></span>
                      <span class="cbx-topo-svc-name">EdgeCore</span>
                      <span class="cbx-topo-svc-addr mono" :title="'CloudHub ' + (cloudHubAddr || '—')">→ {{ cloudHubAddr || '—' }}</span>
                      <span class="cbx-topo-svc-type">{{ t('边缘运行时') }}</span>
                    </div>
                    <div class="cbx-topo-svc" :class="{ off: b.ready === false }"
                         :title="t('设备采集服务：按协议采集传感器/仪表读数，经 DMI 与 MQTT 双通道上报（data/# 与 ext/#）') + '\n→ ' + (brokerAddr || '—')">
                      <span class="cbx-topo-svc-dot" :class="{ on: b.ready !== false }"></span>
                      <span class="cbx-topo-svc-name">box-mapper</span>
                      <span class="cbx-topo-svc-addr mono" :title="t('上报') + ' ' + (brokerAddr || '—')">→ {{ brokerAddr || '—' }}</span>
                      <span class="cbx-topo-svc-type">{{ t('采集') }}</span>
                      <span class="cbx-topo-svc-ops">
                        <button class="cbx-op cbx-tiny" :disabled="!!restartingKey || !edgeIpOk(b)" @click="restartMapper(b)" :title="edgeIpOk(b) ? t('重启该盒子上的 box-mapper systemd 服务（云端 agent 经 SSH 到边缘盒子执行 systemctl restart box-mapper）') : t('未配置盒子 IP 或探测不通，无法重启 Mapper（先点「配置」填写现场可达地址）')">{{ restartingKey === 'edge:box-mapper' ? '…' : '↻' }}</button>
                      </span>
                    </div>
                    <!-- 云端部署到本机的应用/模型（盒子周期上报 state/{box}/services） -->
                    <template v-if="b.services && b.services.length">
                      <div v-for="s in b.services" :key="s.name" class="cbx-topo-svc" :title="(s.command || '') + (s.url ? '\n' + s.url + '\n' + t('点击在新标签页打开') : '')">
                        <span class="cbx-topo-svc-dot" :class="{ on: s.running || s.status === 'running' }"></span>
                        <span class="cbx-topo-svc-name">{{ s.name }}</span>
                        <a v-if="s.url" class="cbx-topo-svc-addr mono" :href="s.url" target="_blank" rel="noopener"
                           :title="t('点击在新标签页打开') + ' ' + s.url" @click.stop>{{ urlHostPort(s.url) }}</a>
                        <span class="cbx-topo-svc-type">{{ s.type || '' }}{{ s.running === false || s.status === 'stopped' ? ' · ' + t('已停止') : '' }}</span>
                      </div>
                    </template>
                    <div v-else class="cbx-topo-svc-empty">{{ t('暂无云端部署应用') }}</div>
                  </div>
                  <!-- 一体机是本链路的汇聚点：下接传感器/仪表、后接外部数据系统，统一上行云端 -->
                  <div class="cbx-topo-inner">{{ t('本机汇聚：传感器/仪表 + 外部数据系统 → 统一 MQTT 上行云端（data/# · ext/#）') }}</div>
                  <div class="cbx-topo-inner">{{ devCountOf(b.name) }} {{ t('台待下发') }} · {{ b.source === 'mqtt' ? t('MQTT 识别') : 'K8s Agent' }}<template v-if="b.roles && b.roles !== '—'"> · {{ roleZh(b.roles) }}</template></div>
                  <div class="cbx-topo-mod-ops">
                    <button class="cbx-op cbx-xs" @click="openBoxEdgeCfg(b)" :title="t('配置盒子显示名称 / 现场可达 IP / SSH 凭据（重启 Mapper 前必须配置且探测可达）')">{{ t('配置') }}</button>
                    <button class="cbx-op cbx-xs" @click="openAppDeploy(b)" :title="t('云端部署模型/服务到盒子（经云端 Broker 命令主题下发，盒子订阅执行）')">⬇ {{ t('部署') }}</button>
                  </div>
                </div>
                <div v-if="!topoBoxes.length" class="cbx-topo-empty">{{ t('未识别到盒子节点（云端未连接）。') }}</div>
              </div>
              <!-- 设备④：现场设备（传感器/仪表，一体机下接，卡内为各台采集设备） -->
              <div class="cbx-topo-lane dev">
                <div class="cbx-topo-lane-title">{{ t('现场设备（传感器/仪表）') }}<span class="cbx-sec-spacer"></span><button class="cbx-op cbx-xs" @click="openModelCreate">＋ {{ t('模型') }}</button><button class="cbx-op cbx-xs" @click="openCreate()" :title="t('设备接入：新建采集设备并默认关联到盒子')">＋ {{ t('设备') }}</button></div>
                <div :ref="setNodeRef('d_devs')" class="cbx-topo-mod device devgroup">
                  <div class="cbx-topo-dev-hd">
                    <span class="cbx-topo-dev-ic">🛠</span>
                    <div class="cbx-topo-dev-meta">
                      <b class="cbx-topo-dev-title">{{ t('采集设备') }}</b>
                      <span class="cbx-topo-dev-addr">{{ t('边缘采集 MQTT :1883') }}</span>
                    </div>
                    <span class="cbx-topo-mod-badge ok">{{ topoAllCloudDevs.length + topoAllLocalDevs.length + topoUnmounted.length }} {{ t('台') }}</span>
                  </div>
                  <div class="cbx-topo-devlist">
                    <div v-if="topoAllCloudDevs.length" class="cbx-topo-devgroup">
                      <div class="cbx-topo-devlabel">{{ t('云端真实') }}</div>
                      <div v-for="d in topoAllCloudDevs" :key="'c' + d.name" class="cbx-topo-dev cloud" :class="{ on: d.state === 'online' }" @click="openDevRealtime(d)" :title="'Device CRD：' + d.name + (d.model ? '（' + t('模型') + ' ' + d.model + '）' : '') + t('（点击查看实时数据）')">
                        <span class="cbx-topo-dev-dot"></span>
                        <span class="cbx-topo-dev-name">{{ d.name }}</span>
                        <span class="cbx-topo-dev-addr mono" :title="devAddrOf(d) || '—'">{{ devAddrOf(d) || '—' }}</span>
                      </div>
                    </div>
                    <div v-if="topoAllLocalDevs.length" class="cbx-topo-devgroup">
                      <div class="cbx-topo-devlabel">{{ t('待下发') }}</div>
                      <div v-for="d in topoAllLocalDevs" :key="'l' + d.name" class="cbx-topo-dev pending" @click="openDevRealtime(d)" :title="t('待下发') + '：' + d.name">
                        <span class="cbx-topo-dev-dot"></span>
                        <span class="cbx-topo-dev-name">{{ d.name }}</span>
                        <span class="cbx-topo-dev-addr mono" :title="devAddrOf(d) || '—'">{{ devAddrOf(d) || '—' }}</span>
                      </div>
                    </div>
                    <div v-if="topoUnmounted.length" class="cbx-topo-devgroup">
                      <div class="cbx-topo-devlabel">{{ t('未挂载') }}</div>
                      <div v-for="d in topoUnmounted" :key="d.name" class="cbx-topo-dev pending" @click="openDevRealtime(d)" :title="t('待下发') + '：' + d.name">
                        <span class="cbx-topo-dev-dot"></span>
                        <span class="cbx-topo-dev-name">{{ d.name }}</span>
                        <span class="cbx-topo-dev-addr mono" :title="devAddrOf(d) || '—'">{{ devAddrOf(d) || '—' }}</span>
                      </div>
                    </div>
                    <div v-if="!topoAllCloudDevs.length && !topoAllLocalDevs.length && !topoUnmounted.length" class="cbx-topo-dev-empty">{{ t('暂无设备') }}</div>
                  </div>
                </div>
              </div>
              <!-- 设备⑤：外部数据系统（一体机后面一级：第三方系统 / 数据中台 / 模拟源，经网线接入一体机） -->
              <div class="cbx-topo-lane extsrc-lane">
                <div class="cbx-topo-lane-title">{{ t('外部数据系统') }}<span class="cbx-sec-spacer"></span><button class="cbx-op cbx-xs" @click="openAddForm('mqtt')" :title="t('注册外部数据源：第三方系统/数据中台经网线接入能碳一体机，由一体机上行到云端')">＋ {{ t('外部源') }}</button></div>
                <div :ref="setNodeRef('d_ext')" class="cbx-topo-mod device extsrc">
                  <div class="cbx-topo-dev-hd">
                    <span class="cbx-topo-dev-ic">🏭</span>
                    <div class="cbx-topo-dev-meta">
                      <b class="cbx-topo-dev-title" :title="t('外部数据系统：PLC / 仪表 / 数据中台 / 第三方业务系统，经网线或工业总线接入能碳一体机，是「一体机后面一级」的数据来源；演示环境由独立服务 sim-source 模拟')">{{ t('外部数据系统') }}</b>
                      <span class="cbx-topo-dev-addr">{{ t('以太网 / 串口 / OPC') }} → {{ t('一体机') }} → ext/&lt;源&gt;/#</span>
                    </div>
                    <span class="cbx-topo-mod-badge" :class="{ ok: extSources.some(s => s.enabled && s.status && s.status.active) }">{{ extSources.length }} {{ t('源') }}</span>
                  </div>
                  <div class="cbx-topo-devlist">
                    <div v-for="s in extSources" :key="s.id" class="cbx-topo-dev cloud" :class="{ on: s.status && s.status.active }" :title="s.name + '（' + s.config.box + '）' + t('：经一体机上行到云端，由数据中间件转换后进入平台') + '\n' + (extAddrOf(s) || '—')">
                      <span class="cbx-topo-dev-dot"></span>
                      <span class="cbx-topo-dev-name">{{ s.name }}</span>
                      <span class="cbx-topo-dev-addr mono" :title="extAddrOf(s) || '—'">{{ extAddrOf(s) || '—' }}</span>
                    </div>
                    <div v-if="!extSources.length" class="cbx-topo-dev-empty">{{ t('尚无外部数据源') }}</div>
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
          </div>
        </section>
        <!-- ② 资源列表：盒子 / 模型 / 设备（三列并排总览，点击行可快速跳转编辑/实时） -->
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <button class="cbx-caret" @click="toggleSec('reslist')" :title="secFold.reslist ? t('收起') : t('展开')">{{ secFold.reslist ? '▾' : '▸' }}</button>
            <b class="cbx-sec-toggle" @click="toggleSec('reslist')">{{ t('资源列表') }}</b>
            <span class="cbx-sec-hint res-hint">{{ topoBoxes.length }} {{ t('盒') }} · {{ mergedModels.length }} {{ t('模型') }} · {{ mergedDevices.length }} {{ t('设备') }}</span>
            <!-- 手动刷新：重新拉取三列数据 + 强制同步拉云端 CRD（用户主动点时才付 5s 超时代价） -->
            <button class="cbx-op cbx-xs" :disabled="resRefreshing" @click="refreshResources()"
                    :title="t('重新拉取盒子 / 模型 / 设备列表，并同步拉取云端最新 CRD 状态')">
              <span class="cbx-ref-ic" :class="{ spin: resRefreshing }">⟳</span>{{ resRefreshing ? t('刷新中…') : t('刷新') }}
            </button>
          </div>
          <div v-if="secFold.reslist" class="cbx-reslist">
            <!-- 盒子列表 -->
            <div id="cbx-res-box" class="cbx-rescol">
              <div class="cbx-rescol-head">{{ t('盒子列表') }}<span class="cbx-rescol-n">{{ topoBoxes.length }}</span></div>
              <div class="cbx-rescol-body">
                <div v-for="b in topoBoxes" :key="b.name" class="cbx-resrow" @click="openDevRealtime({ name: b.name })" :title="t('盒子节点') + '：' + b.name">
                  <span class="cbx-dot" :class="{ on: readyOk(b.ready) }"></span>
                  <span class="cbx-res-name" :title="b.name">{{ boxName(b) }}</span>
                  <span class="cbx-res-tag" :class="{ ok: readyOk(b.ready), err: b.ready === false }">{{ readyZh(b.ready) }}</span>
                  <span class="cbx-res-sub">EdgeCore<template v-if="b.version && b.version !== '—'"> v{{ b.version }}</template> · {{ devCountOf(b.name) }} {{ t('台待下发') }}</span>
                </div>
                <div v-if="!topoBoxes.length" class="cbx-res-empty">{{ t('未识别到盒子节点') }}</div>
              </div>
            </div>
            <!-- 模型列表 -->
            <div class="cbx-rescol">
              <div class="cbx-rescol-head">▦ {{ t('模型列表') }}<span class="cbx-rescol-n">{{ mergedModels.length }}</span></div>
              <div class="cbx-rescol-body">
                <div v-for="m in mergedModels" :key="m.name" class="cbx-resrow" @click="openEditModel(m)" :title="t('模型（点击修改点位）') + '：' + m.name">
                  <span class="cbx-res-name">{{ m.name }}</span>
                  <span class="cbx-res-tag ok" v-if="m._cloud">{{ t('已下发') }}</span>
                  <span class="cbx-res-tag" v-else>{{ t('未下发') }}</span>
                  <span class="cbx-res-sub"><template v-if="m.protocol">{{ m.protocol }}</template> · {{ modelPropCount(m) }} {{ t('属性') }}</span>
                </div>
                <div v-if="!mergedModels.length" class="cbx-res-empty">{{ t('暂无模型') }}</div>
              </div>
            </div>
            <!-- 设备列表 -->
            <div id="cbx-res-dev" class="cbx-rescol">
              <div class="cbx-rescol-head">◈ {{ t('设备列表') }}<span class="cbx-rescol-n">{{ mergedDevices.length }}</span>
              </div>
              <div class="cbx-rescol-body">
                <div v-for="d in mergedDevices" :key="d.name" class="cbx-resrow" @click="onDevClick(d)" :title="(d._cloud ? t('云端设备（点击查看实时）') : t('待下发设备（点击编辑配置）')) + '：' + d.name + (modelOf(d) ? '（' + t('模型') + ' ' + modelOf(d) + '）' : '')">
                  <span class="cbx-dot" :class="{ on: d.state === 'online' }"></span>
                  <span class="cbx-res-name">{{ d.name }}</span>
                  <span class="cbx-res-tag" :class="{ ok: d.state === 'online', err: d.state === 'offline' }">{{ devStateZh(d) }}</span>
                  <span class="cbx-res-sub">{{ modelOf(d) || '—' }}<template v-if="d.node"> · {{ d.node }}</template><template v-else-if="d.protocol"> · {{ d.protocol }}</template><template v-if="slaveLabelOf(d)"> · {{ t('站') }}{{ slaveLabelOf(d) }}</template></span>
                  <span class="cbx-res-ops">
                    <button class="cbx-op cbx-tiny" @click.stop="openEditDev(d)">✎ {{ t('配置') }}</button>
                    <button v-if="d._cloud" class="cbx-op cbx-tiny" @click.stop="openCloudHistory(d)" :title="t('云端时序库（TDengine）历史读数曲线')">{{ t('历史') }}</button>
                    <!-- 采集设备没有「禁用」这一档：不想采集就删除，三端配置同步清除 -->
                    <button class="cbx-op cbx-tiny danger" @click.stop="delDevice(d)" :title="t('删除该设备：平台本地配置 / 云端 CRD / 盒子取数配置三端同步清除')">🗑 {{ t('删除') }}</button>
                  </span>
                </div>
                <div v-if="!mergedDevices.length" class="cbx-res-empty">{{ t('暂无设备') }}</div>
              </div>
            </div>
          </div>
        </section>
        <!-- ③ 证书与 Token 有效期（独立区块：云端 agent 实时采集云端 CA/服务证书与共享 token） -->
        <section class="cbx-sec" v-if="(overview.certs || []).length || overview.token">
          <div class="cbx-sec-head">
            <button class="cbx-caret" @click="toggleSec('certs')" :title="secFold.certs ? t('收起') : t('展开')">{{ secFold.certs ? '▾' : '▸' }}</button>
            <b class="cbx-sec-toggle" @click="toggleSec('certs')">{{ t('证书与密钥到期提醒') }}</b>
          </div>
          <div v-if="secFold.certs" class="cbx-sec-desc">
            {{ t('仅专业维护人员查看') }}
            <span class="cbx-sec-desc-extra">{{ t('剩余不足 30 天标红提醒') }}</span>
          </div>
          <div v-if="secFold.certs" class="cbx-certlist">
            <div v-for="c in overview.certs || []" :key="c.cn" class="cbx-certrow">
              <code>{{ c.cn }}</code>
              <span class="cbx-cert-exp">{{ c.expires }}</span>
              <span class="cbx-cert-days" :class="{ warn: (c.remain_days ?? 999) < 30 }">{{ c.remain_days ?? '—' }} {{ t('天') }}</span>
            </div>
            <div v-if="overview.token" class="cbx-certrow">
              <code>token</code>
              <span class="cbx-cert-exp">{{ overview.token.expires }}</span>
              <span class="cbx-cert-days" :class="{ warn: (overview.token.remain_days ?? 999) < 30 }">{{ overview.token.remain_days ?? '—' }} {{ t('天') }}</span>
            </div>
          </div>
        </section>

        <!-- ④-2 实时消息流（云端 Broker → 本平台；默认折叠，排查链路时再展开） -->
        <section class="cbx-sec">
          <div class="cbx-sec-head">
            <button class="cbx-caret" @click="toggleSec('msglog')" :title="secFold.msglog ? t('收起') : t('展开')">{{ secFold.msglog ? '▾' : '▸' }}</button>
            <b class="cbx-sec-toggle" @click="toggleSec('msglog')">{{ t('实时消息流') }}</b>
          </div>
          <div v-if="secFold.msglog" class="cbx-sec-desc">{{ t('最近') }} {{ messages.length }} {{ t('条') }}</div>
          <div v-if="secFold.msglog" ref="msgLogRef" class="cbx-msglog">
            <div v-for="(m, i) in messages" :key="i" class="cbx-msgrow">
              <span class="cbx-msgtime">{{ fmtTime(m.t) }}</span>
              <code class="cbx-msg-topic">{{ m.topic }}</code>
              <span class="cbx-msg-payload">{{ m.payload }}</span>
            </div>
            <div v-if="!messages.length" class="cbx-empty">{{ t('暂无消息。') }}</div>
          </div>
        </section>

        <!-- ④ 命令执行：向一体机下发设备读/写/LoRaWAN 下行；原「发送指令」保留为「原始消息」子模式 -->
        <section id="cbx-sec-cmd" class="cbx-sec">
          <div class="cbx-sec-head">
            <button class="cbx-caret" @click="toggleSec('cmd')" :title="secFold.cmd ? t('收起') : t('展开')">{{ secFold.cmd ? '▾' : '▸' }}</button>
            <b class="cbx-sec-toggle" @click="toggleSec('cmd')">{{ t('命令执行') }}</b>
            <span class="cbx-sec-spacer"></span>
            <span class="cbx-tabs">
              <button v-for="m in cmdModes" :key="m.k" class="cbx-tab" :class="{ active: cmdMode === m.k }" @click="switchCmdMode(m.k)">{{ t(m.l) }}</button>
            </span>
          </div>
          <div v-if="secFold.cmd" class="cbx-sec-desc"
               :title="t('仅供专业维护：向一体机下发读/写寄存器或 LoRaWAN 下行（如新接入传感器改从站地址/量程标定），执行结果等盒子回报')"
          >{{ t('专业维护：下发读/写寄存器或 LoRaWAN 下行，结果等盒子回报') }}</div>

          <!-- 设备命令模式：选 盒子→设备→读/写 → 自动生成载荷 -->
          <div v-if="secFold.cmd && cmdMode === 'dev'" class="cbx-form">
            <div class="cbx-form-row">
              <label>{{ t('盒子') }}</label>
              <select v-model="cmdForm.box" class="cbx-input cbx-sm" @change="onCmdBoxChange">
                <option value="" disabled>{{ t('请选择盒子') }}</option>
                <option v-for="b in cmdBoxes" :key="b" :value="b">{{ boxName({ name: b }) }}</option>
              </select>
              <label>{{ t('设备') }}</label>
              <select v-model="cmdForm.device" class="cbx-input cbx-md" @change="onCmdDeviceChange">
                <option value="" disabled>{{ t('请选择设备') }}</option>
                <option v-for="d in cmdDevices" :key="d.name" :value="d.name">{{ d.name }}<template v-if="d.src">（{{ d.src }}<template v-if="d.proto"> · {{ d.proto }}</template>）</template></option>
              </select>
              <label>{{ t('操作') }}</label>
              <select v-model="cmdForm.op" class="cbx-input cbx-sm" @change="onCmdOpChange">
                <option v-for="o in cmdOpOptions" :key="o.k" :value="o.k">{{ t(o.l) }}</option>
              </select>
              <span v-if="cmdDevMeta && !cmdDevMeta.isLora && !cmdDevMeta.isModbus" class="cbx-sec-hint">{{ t('仅支持 Modbus / LoRaWAN 设备，其余协议请用「原始消息」直接调 MQTT') }}</span>
            </div>

            <!-- LoRaWAN：读=主动取数，写=自定义下行 -->
            <template v-if="cmdDevMeta && cmdDevMeta.isLora">
              <div class="cbx-form-row">
                <label>{{ t('下行内容') }}</label>
                <select v-model="cmdForm.loraKind" class="cbx-input cbx-sm" :disabled="cmdForm.op === 'read'">
                  <option value="hex">hex</option>
                  <option value="text">text</option>
                  <option value="object">object</option>
                </select>
                <input v-if="cmdForm.op === 'write'" v-model="cmdForm.loraData" class="cbx-input cbx-grow"
                       :placeholder="cmdForm.loraKind === 'hex' ? t('十六进制下行帧，如 0103020001') : (cmdForm.loraKind === 'text' ? t('文本内容') : t('JSON 对象，如 fan:1（勿带引号）'))"/>
                <template v-if="cmdForm.op === 'write'">
                  <label>{{ t('端口') }}</label><input v-model="cmdForm.fPort" class="cbx-input cbx-num" placeholder="2"/>
                </template>
                <span class="cbx-sec-hint" v-if="cmdForm.op === 'read'">{{ t('读 = 下行取数一拍（设备需填了从站号才会下行轮询）并等终端回传') }}</span>
              </div>
            </template>

            <!-- Modbus：值来源 = 已配置点位 / 任意寄存器 -->
            <template v-if="cmdDevMeta && cmdDevMeta.isModbus">
              <div class="cbx-form-row">
                <label>{{ t('寄存器') }}</label>
                <select v-model="cmdForm.refMode" class="cbx-input cbx-sm" @change="onCmdRefModeChange">
                  <option value="prop">{{ cmdForm.op === 'write' ? t('可写点') : t('采集点位') }}</option>
                  <option value="reg">{{ t('任意寄存器') }}</option>
                </select>
                <template v-if="cmdForm.refMode === 'prop' && (cmdForm.op === 'read' ? cmdDevMeta.props.length : cmdDevMeta.writes.length)">
                  <label>{{ cmdForm.op === 'read' ? t('点位') : t('可写点') }}</label>
                  <select v-model="cmdForm.prop" class="cbx-input cbx-grow" :title="cmdForm.op === 'write' ? (cmdDevMeta.writes.find((w) => w.property === cmdForm.prop) ? writePointTitle(cmdDevMeta.writes.find((w) => w.property === cmdForm.prop)) : t('选择要写入的可写点位')) : t('选择要读取的采集点位')">
                    <option v-if="cmdForm.op === 'write'" v-for="w in cmdDevMeta.writes" :key="w.property" :value="w.property" :title="writePointTitle(w)">{{ writePointLabel(w) }}</option>
                    <option v-else v-for="p in cmdDevMeta.props" :key="p.name" :value="p.name" :title="p.desc || p.name">{{ (p.desc || p.name) }}（{{ p.name }}）</option>
                  </select>
                </template>
                <template v-else-if="cmdForm.refMode === 'reg'">
                  <label>{{ t('寄存器') }}</label><input v-model="cmdForm.addr" class="cbx-input cbx-num" placeholder="0"/>
                  <template v-if="cmdForm.op === 'read'">
                    <label>{{ t('类型') }}</label>
                    <select v-model="cmdForm.dtype" class="cbx-input cbx-sm">
                      <option value="int16">int16</option><option value="uint16">uint16</option><option value="int32">int32</option><option value="uint32">uint32</option><option value="int64">int64</option><option value="uint64">uint64</option><option value="float32">float32</option>
                    </select>
                    <label>{{ t('功能码') }}</label>
                    <select v-model="cmdForm.fc" class="cbx-input cbx-mid">
                      <option value="3">3 · 保持寄存器</option><option value="4">4 · 输入寄存器</option>
                    </select>
                    <label>{{ t('倍率') }}</label><input v-model="cmdForm.scale" class="cbx-input cbx-num" :placeholder="cmdDevMeta.props[0] && cmdDevMeta.props[0].scale != null ? String(cmdDevMeta.props[0].scale) : '1'"/>
                  </template>
                  <template v-else>
                    <label>{{ t('类型') }}</label>
                    <select v-model="cmdForm.wKind" class="cbx-input cbx-sm">
                      <option value="holding">保持寄存器</option><option value="coil">线圈</option>
                    </select>
                  </template>
                </template>
                <!-- 从站号属于设备配置：命令里不另行指定（盒子按配置里配的站号下发） -->
                <span class="cbx-sec-hint">{{ t('从站号') }} {{ cmdDevMeta.slave != null && cmdDevMeta.slave !== '' ? cmdDevMeta.slave : 1 }}（{{ t('来自设备配置') }}）</span>
              </div>

              <div v-if="cmdForm.op === 'write'" class="cbx-form-row">
                <label>{{ t('写入值') }}</label>
                <input v-model="cmdForm.value" class="cbx-input cbx-mid"
                       :placeholder="cmdValuePlaceholder()"/>
                <template v-if="cmdForm.refMode === 'prop'">
                  <span v-if="writePropHint(cmdDevMeta)" class="cbx-sec-hint">{{ writePropHint(cmdDevMeta) }}</span>
                </template>
                <!-- 裸写的安全范围只来自设备配置（可写点位 / 可写属性的 min·max），
                     命令里不再填写本次上下限：未配置范围时平台拒绝下发，此处给出提示 -->
                <template v-else>
                  <span v-if="addrRangeHint()" class="cbx-sec-hint">{{ addrRangeHint() }}</span>
                  <span v-else class="cbx-sec-hint">{{ t('未配置安全范围：请先到设备配置（可写点位 / 可写属性）中设置上下限，平台拒绝无范围的设备写入') }}</span>
                </template>
              </div>
              <div v-if="cmdForm.op === 'read' && cmdForm.refMode === 'reg'" class="cbx-form-row">
                <span class="cbx-sec-hint">{{ t('读任意寄存器不依赖点位配置：适合写设定前先确认传感器寄存器内容/默认从站。') }}</span>
              </div>
            </template>

            <div class="cbx-form-row" v-if="cmdDevMeta">
              <label>{{ t('将发送') }}</label>
              <pre class="cbx-cmd-json" :title="t('自动生成载荷，可直接复制到「原始消息」手动微调')">{{ cmdPayloadText }}</pre>
              <button class="cbx-op primary" :disabled="cmdSending" @click="execCmd">{{ cmdSending ? t('发送中…') : (cmdPending ? t('等待回报…') : t('执行')) }}</button>
            </div>

            <div class="cbx-cmd-result" v-if="cmdResult" :class="{ ok: cmdResult.ok, err: cmdResult.ok === false, wait: cmdResult.ok === null }">
              <template v-if="cmdResult.ts">{{ fmtTime(cmdResult.ts) }} · </template>
              <b>{{ cmdResult.message }}</b>
              <pre v-if="cmdResult.detailText" class="cbx-cmd-json slim">{{ cmdResult.detailText }}</pre>
            </div>
          </div>

          <!-- 原始消息模式（原「发送指令」）：直接向云端 Broker 发布任意主题 -->
          <div v-else-if="secFold.cmd" class="cbx-form">
            <div class="cbx-form-row">
              <label>{{ t('主题') }}</label><input v-model="pubForm.topic" class="cbx-input cbx-md" placeholder="data/box-001/device-1"/>
              <label>{{ t('载荷') }}</label><input v-model="pubForm.payload" class="cbx-input cbx-grow" placeholder='{"device":"device-1","value":88.8}'/>
              <button class="cbx-op primary" @click="doPublish">{{ t('发布') }}</button>
            </div>
            <div class="cbx-form-row">
              <span class="cbx-sec-hint">{{ t('data/# 发布可自检一体机上报链路并在「实时消息流」看到回显；cmd/{box}/# 为盒子命令主题（盒子 mapper 需支持对应命令）') }}</span>
            </div>
          </div>

        </section>

        <!-- 数据服务接口（独立模块）：对外集成接口清单，见 DataServiceApiPanel.vue -->
        <DataServiceApiPanel />
          </section>
        </div><!-- /cbx-editor -->
      </main>
    </div><!-- /cbx-workbench -->

    <!-- 状态栏 -->
    <footer class="cbx-statusbar">
      <span class="cbx-st-item"><span class="cbx-dot" :class="{ on: overview.cloud_source === 'live' }"></span>{{ t('云端') }} {{ overview.cloud_source === 'live' ? t('在线') : (overview.cloud_source === 'stale' ? t('数据过期') : (overview.cloud_source === 'degraded' ? t('部分异常') : t('不可达'))) }}</span>
      <span class="cbx-st-item">{{ t('模型') }} {{ devices.models?.length || 0 }} · {{ t('设备') }} {{ devices.devices?.length || 0 }}</span>
      <span class="cbx-st-item">{{ t('消息') }} {{ messages.length }} {{ t('条') }}</span>
      <span class="cbx-st-grow"></span>
      <span class="cbx-st-item">{{ cloudCfg.host || '36.151.146.71' }}</span>
      <span class="cbx-st-item">3s {{ t('自动刷新') }}</span>
    </footer>

        <!-- 修改设备配置对话框（复用 create_device apply 做 upsert，本地 box_devices.json + 模型同步） -->
        <div v-if="editOpen" class="cbx-mask" @click.self="editOpen = false">
          <div class="cbx-dialog cbx-dialog-lg">
            <div class="cbx-dialog-head">
              <b>{{ editTarget === 'model' ? t('修改模型') : t('修改设备') }}：<code>{{ editForm.modelName }}</code></b>
              <button class="x-btn lg" @click="editOpen = false" :aria-label="t('关闭')">✕</button>
            </div>
            <div class="cbx-form">
              <div class="cbx-form-row">
                <label>{{ t('协议') }}</label>
                <select v-model="editForm.protocol" class="cbx-select">
                  <option value="modbus">{{ t('Modbus（RTU / TCP）') }}</option>
                  <option value="opcua">OPC-UA</option>
                  <option value="bluetooth">Bluetooth</option>
                  <option value="lora">{{ t('LoRaWAN（LoRa 网关）') }}</option>
                  <option value="cellular">{{ t('5G/4G 模块自监控') }}</option>
                </select>
              </div>
              <div class="cbx-form-row">
                <template v-if="editTarget !== 'model'">
                  <label>{{ t('模型') }}</label>
                  <select v-model="editForm.modelName" class="cbx-select" @change="onPickEditModel" :title="t('切换模型会带出该模型的协议与属性点位')">
                    <option value="" disabled>{{ t('请选择模型…') }}</option>
                    <option v-for="m in devices.models || []" :key="m.name" :value="m.name">{{ m.name }}（{{ m.protocol }} · {{ (m.properties || []).length }} {{ t('属性') }}）</option>
                  </select>
                  <button class="cbx-op cbx-xs" @click="openModelCreate" :title="t('先创建 DeviceModel 再选择')">＋ {{ t('新建模型') }}</button>
                  <label>{{ t('设备名') }}</label><input v-model="editForm.deviceName" class="cbx-input" placeholder="box-device"/>
                </template>
                <template v-else>
                  <label>{{ t('模型名') }}</label><input v-model="editForm.modelName" class="cbx-input" placeholder="box-metric-model" disabled/>
                  <span class="cbx-sec-sub">{{ t('模型为共享配置：点位变更对引用它的所有设备同时生效，无单独设备名') }}</span>
                </template>
              </div>
              <div v-if="editTarget !== 'model'" class="cbx-form-row">
                <label>{{ t('绑定流程设备') }}</label>
                <select v-model="editForm.boundDevice" class="cbx-select" style="width:300px" :title="t('从现有系统流程的设备中选择：保存后该设备的云端读数将同步到所选流程设备实例（关联制）')">
                  <option value="">{{ t('不绑定') }}</option>
                  <optgroup v-for="grp in procGroups" :key="grp.unit" :label="grp.unit">
                    <option v-for="d in grp.devices" :key="d.id" :value="d.id">{{ d.label || d.name }}（{{ d.id }}）</option>
                  </optgroup>
                </select>
                <label v-if="editForm.boundDevice" style="margin-left:10px">{{ t('换算系数') }}</label>
                <input v-if="editForm.boundDevice" v-model.number="editForm.boundFactor" type="number" step="any" class="cbx-input" style="width:90px" :title="t('云端原始读数 × 此系数 = 同步到流程设备的读数（如传感器 kg/min → t/h 填 0.06；无需换算填 1）')"/>
                <span class="cbx-sec-sub">{{ t('未选择则解除当前绑定') }}</span>
              </div>
              <div v-if="editTarget !== 'model'" class="cbx-form-row">
                <label>{{ t('绑定云端设备') }}</label>
                <select v-model="editForm.cloudDevice" class="cbx-select" style="width:300px" :title="t('选择盒子已上报、平台已识别的云端真实设备：保存后该设备的实时读数将归入此设备')">
                  <option value="">{{ t('不绑定（按设备名自动匹配）') }}</option>
                  <optgroup v-for="g in cloudUnboundGroups" :key="g.label" :label="g.label">
                    <option v-for="c in g.items" :key="c.name" :value="c.name">{{ c.name }}（{{ stateZh(c.state) }}<template v-if="c.model"> · {{ c.model }}</template>）</option>
                  </optgroup>
                </select>
                <span class="cbx-sec-sub">{{ t('未选择则按设备名自动匹配') }}</span>
              </div>
              <div class="cbx-form-row">
                <label>{{ t('命名空间') }}</label><input v-model="editForm.namespace" class="cbx-input" style="width:110px"/>
                <template v-if="editTarget !== 'model'">
                  <label>{{ t('调度节点（盒子）') }}</label>
                  <select v-model="editForm.nodeName" class="cbx-input" style="width:170px" :title="t('从识别到的盒子中选择，或保留原值')">
                    <option v-for="n in overview.nodes || []" :key="n.name" :value="n.name">{{ n.name }}（{{ readyZh(n.ready) }}）</option>
                    <option v-if="!(overview.nodes || []).some((n) => n.name === editForm.nodeName)" :value="editForm.nodeName">{{ editForm.nodeName }}（{{ t('未识别') }}）</option>
                  </select>
                  <label>{{ t('采集周期(ms)') }}</label><input v-model.number="editForm.collectCycle" type="number" class="cbx-input" style="width:100px"/>
                </template>
              </div>


              <!-- 协议通信参数（模型编辑时不涉及设备通信参数） -->
              <template v-if="editTarget !== 'model'">
              <!-- Modbus 协议参数 -->
              <template v-if="editForm.protocol === 'modbus'">
                <div class="cbx-form-row">
                  <label>{{ t('通信方式') }}</label>
                  <select v-model="editForm.comm.commType" class="cbx-select">
                    <option value="serial">{{ t('串口 RTU') }}</option>
                    <option value="tcp">TCP</option>
                  </select>
                  <label>slaveID</label><input v-model.number="editForm.comm.slaveID" type="number" class="cbx-input" style="width:70px"/>
                  <template v-if="editForm.comm.commType === 'serial'">
                    <label>{{ t('串口') }}</label><input v-model="editForm.comm.serialPort" class="cbx-input" style="width:150px"/>
                    <label>{{ t('波特率') }}</label><input v-model.number="editForm.comm.baudRate" type="number" class="cbx-input" style="width:80px"/>
                    <label>{{ t('校验') }}</label>
                    <select v-model="editForm.comm.parity" class="cbx-select"><option>none</option><option>even</option><option>odd</option></select>
                  </template>
                  <template v-else>
                    <label>IP</label><input v-model="editForm.comm.tcpIP" class="cbx-input" style="width:130px"/>
                    <label>{{ t('端口') }}</label><input v-model.number="editForm.comm.tcpPort" type="number" class="cbx-input" style="width:70px"/>
                  </template>
                </div>
              </template>
              <!-- OPC-UA 协议参数 -->
              <template v-else-if="editForm.protocol === 'opcua'">
                <div class="cbx-form-row">
                  <label>URL</label><input v-model="editForm.opcua.url" class="cbx-input" style="width:220px" placeholder="opc.tcp://127.0.0.1:4840"/>
                  <label>{{ t('用户名') }}</label><input v-model="editForm.opcua.userName" class="cbx-input" style="width:100px"/>
                  <label>{{ t('密码') }}</label><input v-model="editForm.opcua.password" class="cbx-input" style="width:100px"/>
                </div>
              </template>
              <!-- Bluetooth 协议参数 -->
              <template v-else-if="editForm.protocol === 'bluetooth'">
                <div class="cbx-form-row">
                  <label>{{ t('MAC 地址') }}</label><input v-model="editForm.bluetooth.macAddress" class="cbx-input" style="width:170px" placeholder="AA:BB:CC:DD:EE:FF"/>
                </div>
              </template>
              <!-- LoRaWAN 协议参数（盒子侧 LoRa 网关 + ChirpStack，上行走本地 mosquitto） -->
              <template v-else-if="editForm.protocol === 'lora'">
                <div class="cbx-form-row">
                  <label>Broker</label><input v-model="editForm.lora.broker" class="cbx-input" style="width:140px" placeholder="127.0.0.1"/>
                  <label>{{ t('端口') }}</label><input v-model.number="editForm.lora.port" type="number" class="cbx-input" style="width:70px"/>
                  <label>{{ t('应用ID') }}</label><input v-model="editForm.lora.applicationID" class="cbx-input" style="width:70px" placeholder="1"/>
                  <label>DevEUI</label><input v-model="editForm.lora.devEUI" class="cbx-input" style="width:160px" placeholder="0011223344556677"/>
                  <label>{{ t('从站号') }}</label><input v-model.number="editForm.lora.slaveId" type="number" min="0" max="247" class="cbx-input" style="width:70px"
                                                          :title="t('同一台 LoRa 透传 DTU 下挂多台 485 传感器时按此站号区分（如 env-temp 站2、shuitong-temp 站7）；0 = 被动上报，不下发问帧')"/>
                </div>
                <div class="cbx-form-row">
                  <span class="cbx-sec-hint">{{ t('从站号：同一台 LoRa DTU 下挂多台 485 传感器时按此区分，0 表示被动上报（下行取数与解析按该站号拼帧）') }}</span>
                </div>
                <div class="cbx-form-row">
                  <label>AppKey</label><input v-model="editForm.lora.appKey" class="cbx-input" style="width:170px"/>
                  <label>{{ t('频段') }}</label>
                  <select v-model="editForm.lora.region" class="cbx-select"><option>CN470</option><option>EU868</option><option>US915</option></select>
                  <label>{{ t('数据率') }}</label>
                  <select v-model="editForm.lora.dataRate" class="cbx-select"><option>SF7BW125</option><option>SF9BW125</option><option>SF12BW125</option></select>
                </div>
              </template>
              <!-- 5G/4G 模块自监控协议参数 -->
              <template v-else-if="editForm.protocol === 'cellular'">
                <div class="cbx-form-row">
                  <label>{{ t('AT 串口') }}</label><input v-model="editForm.cellular.serialPort" class="cbx-input" style="width:140px" placeholder="/dev/ttyUSB2"/>
                  <label>{{ t('波特率') }}</label><input v-model.number="editForm.cellular.baudRate" type="number" class="cbx-input" style="width:90px"/>
                  <label>APN</label><input v-model="editForm.cellular.apn" class="cbx-input" style="width:110px" placeholder="cmnet"/>
                  <label>{{ t('蜂窝网卡') }}</label><input v-model="editForm.cellular.iface" class="cbx-input" style="width:90px" placeholder="wwan0"/>
                </div>
              </template>

              </template>
              <!-- 属性点位：设备已绑定模型时点位由模型承载；仅模型本体或未绑模型的设备在此编辑 -->
              <template v-if="editTarget !== 'model' && editForm.modelName">
                <div class="cbx-sec-head" style="margin-top:8px">
                  <b>{{ t('属性点位') }}</b>
                  <span class="cbx-sec-sub">{{ t('已绑定模型，点位由模型承载，请在「模型」卡片中修改') }}</span>
                </div>
                <div class="cbx-form-row">
                  <span class="cbx-sec-hint"><code>{{ editForm.modelName }}</code>：{{ modelPropNames(pickedEditModelProps) || t('该模型暂无点位') }}</span>
                </div>
              </template>
              <template v-else>
              <!-- 属性点位 -->
              <div class="cbx-sec-head" style="margin-top:8px">
                <b>{{ t('属性点位') }}</b>
                <button class="cbx-op" @click="addEditProp">＋ {{ t('添加') }}</button>
              </div>
              <div v-for="(p, i) in editForm.properties" :key="i" class="cbx-prop-row">
                <input v-model="p.name" class="cbx-input" style="width:110px" :placeholder="t('属性名')"/>
                <select v-model="p.type" class="cbx-select">
                  <option v-for="tp in ['float','int','double','string','boolean']" :key="tp">{{ tp }}</option>
                </select>
                <select v-model="p.accessMode" class="cbx-select">
                  <option value="r">ReadOnly</option><option value="rw">ReadWrite</option>
                </select>
                <template v-if="editForm.protocol === 'modbus'">
                  <select v-model="p.registerType" class="cbx-select">
                    <option v-for="r in ['holdingRegister','inputRegister','coil','discreteInput']" :key="r">{{ r }}</option>
                  </select>
                  <input v-model.number="p.register" type="number" class="cbx-input" style="width:70px" :placeholder="t('寄存器')"/>
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="editForm.protocol === 'opcua'">
                  <input v-model="p.nodeID" class="cbx-input" style="width:170px" placeholder="nodeID"/>
                </template>
                <template v-else-if="editForm.protocol === 'bluetooth'">
                  <input v-model="p.characteristicUUID" class="cbx-input" style="width:170px" placeholder="characteristicUUID"/>
                </template>
                <template v-else-if="editForm.protocol === 'lora'">
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="editForm.protocol === 'cellular'">
                  <select v-model="p.kind" class="cbx-select">
                    <option v-for="k in ['signal','csq','rsrp','rsrq','sinr','iccid','imsi','imei','reg','rx_rate','tx_rate']" :key="k">{{ k }}</option>
                  </select>
                </template>
                <input v-model="p.unit" class="cbx-input" style="width:60px" :placeholder="t('单位')"/>
                <button class="x-btn danger" @click="editForm.properties.splice(i, 1)" :title="t('删除属性')">✕</button>
              </div>
              </template>

              <div class="cbx-form-row" style="margin-top:10px">
                <button class="cbx-op primary" @click="applyEditDev" :disabled="editSaving || applying" :title="t('保存到本地并立即下发云端 K3s（无需单独保存）')">{{ editSaving || applying ? t('下发中…') : t('保存并下发') }}</button>
                <button class="cbx-op" @click="dryRunEdit" :disabled="editSaving">{{ t('生成 YAML 预览') }}</button>
                <span class="cbx-sec-sub" v-if="editErr" style="color:var(--red)">{{ editErr }}</span>
                <span class="cbx-deploy-msg" :class="{ err: editErr }">{{ editMsg }}</span>
              </div>

              <div v-if="editPreview" class="cbx-preview" style="margin-top:8px">
                <div class="cbx-preview-head">
                  <b>{{ t('YAML 预览（') }}<code>{{ editPreviewMode }}</code>{{ t('）') }}</b>
                  <button class="cbx-op" @click="copyEditYaml">{{ t('复制') }}</button>
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
              <b>{{ t('实时数据：') }}<code>{{ devRtName }}</code></b>
              <span v-if="devRt" class="cbx-tag" :class="{ ok: devRt.state === 'reporting' }">{{ devRt.state === 'reporting' ? t('上报中') : t('离线') }}</span>
              <span v-if="devRt" class="cbx-sec-hint">{{ t('节点') }} {{ devRt.node }} · {{ t('模型') }} {{ devRt.model }} · {{ t('每 3s 自动刷新') }}<template v-if="devRt.lastOnlineTime"> · {{ t('最后在线') }} {{ fmtAgo(devRt.lastOnlineTime) }}</template></span>
              <button class="x-btn lg" @click="closeDevRealtime" :aria-label="t('关闭')">✕</button>
            </div>
            <div v-if="devRt && devRt.twins && devRt.twins.length" class="cbx-rt">
              <!-- 属性切换 -->
              <div class="cbx-rt-tabs">
                <button v-for="tp in devRt.twins" :key="tp.propertyName"
                        class="cbx-rt-tab" :class="{ active: rtSelProp === tp.propertyName }"
                        @click="rtSel = tp.propertyName" :title="t('切换查看') + ' ' + tp.propertyName + t('趋势')">
                  <code>{{ tp.propertyName }}</code>
                  <span class="cbx-rt-cur">{{ tp.invalid ? t('无有效数据') : fmtPrimary(tp.reported) }}</span>
                  <span class="cbx-rt-unit">{{ tp.unit }}</span>
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
                <b class="cbx-rt-curval">{{ rtCur.invalid ? t('无有效数据') : fmtPrimary(rtCur.reported) }}</b>
                <span class="cbx-rt-unit">{{ rtCur.unit }}</span>
                <span class="cbx-rt-upd">{{ t('更新于') }} {{ rtCur.timestamp ? fmtAgo(rtCur.timestamp) : '—' }} · {{ t('采样') }} {{ rtSeries.length }} {{ t('点') }}</span>
              </div>

              <!-- 全部属性一览（补充） -->
              <table class="cbx-table">
                <thead><tr><th>{{ t('属性') }}</th><th>reported（{{ t('实时值') }}）</th><th>{{ t('单位') }}</th><th>timestamp</th><th>{{ t('采样点数') }}</th></tr></thead>
                <tbody>
                  <tr v-for="tp in devRt.twins" :key="tp.propertyName">
                    <td><code>{{ tp.propertyName }}</code></td>
                    <td class="val"><span :class="{ 'cbx-invalid': tp.invalid }">{{ tp.invalid ? t('无有效数据') : fmtPrimary(tp.reported) }}</span></td>
                    <td>{{ tp.unit || '' }}</td>
                    <td>{{ tp.timestamp ? fmtAgo(tp.timestamp) : '—' }}</td>
                    <td>{{ (devRt.history[tp.propertyName] || []).length }}</td>
                  </tr>
                </tbody>
              </table>
              <p class="cbx-note">{{ t('读数双源融合：① 云端 twins（边缘 Mapper 实时同步）；② 盒子 MQTT 直报 data/#（平台订阅，时间戳更新时优先）。双源均无数据说明盒子侧采集或上报异常，可先确认概览「链路状态」cloud/crds 推送是否新鲜。盒子运行期无需 IP，数据由盒子主动上报。折线图为 3s 滑动窗口、最多 120 点；「无有效数据」多为传感器无信号或未标定。') }}</p>
            </div>
            <div v-else class="cbx-empty">{{ t('该设备暂无实时上报数据（设备可能未下发云端，或边缘未上报）。') }}</div>
          </div>
        </div>

        <!-- 盒子一键接入弹窗（工具栏「盒子接入」入口） -->
        <div v-if="onboardOpen" class="cbx-mask" @click.self="onboardOpen = false">
          <div class="cbx-dialog cbx-dialog-xl">
            <div class="cbx-dialog-head">
              <b>{{ t('盒子一键接入（自解压脚本：box-deploy 采集包 + edgecore.yaml + rootCA + token）') }}</b>
              <button class="x-btn lg" @click="onboardOpen = false" :aria-label="t('关闭')">✕</button>
            </div>
            <div class="cbx-form">
              <div class="cbx-form-row">
                <label>{{ t('盒子主机名') }}</label><input v-model="onboardForm.hostname" class="cbx-input" placeholder="edge-box"/>
                <label>{{ t('云端 CloudCore IP') }}</label><input v-model="onboardForm.cloudIP" class="cbx-input" placeholder="36.151.146.71"/>
                <label>{{ t('盒子 IP（可选，远程一键时作为直达地址）') }}</label><input v-model="onboardForm.boxIP" class="cbx-input" placeholder="172.20.186.56"/>
                <button class="cbx-op primary" :disabled="!onboardForm.cloudIP || onboardBusy" @click="doOnboard">{{ onboardBusy ? t('生成中…') : t('生成一键脚本') }}</button>
              </div>
              <p class="cbx-note">{{ t('一键脚本内置 box-deploy 采集部署包（mapper + mosquitto + 云边协同断点续传，约 18 MB），盒子执行一条') }} <code>bash onboard_box.sh</code> {{ t('即完成：① EdgeCore 接入（keadm join）→ ② rootCA / edgecore.yaml 下发 → ③ 部署包解包 → ④ config.json 自动定制（boxId / broker）→ ⑤ 一键部署 → ⑥ 链路自检。幂等，可重复执行。') }}</p>
            </div>
            <div v-if="onboardResult" class="cbx-onboard">
              <div class="cbx-kv">
                <div><span>{{ t('共享 Token') }}</span><code class="wrap">{{ onboardResult.token }}</code></div>
                <div><span>{{ t('CA 指纹') }}</span><code class="wrap">{{ onboardResult.caHash }}</code></div>
                <div v-if="onboardResult.token_expires"><span>{{ t('Token 有效期至') }}</span><b>{{ onboardResult.token_expires }}</b></div>
                <div><span>{{ t('一键脚本') }}</span><b>{{ onboardResult.script_name }} · {{ (onboardResult.script_size / 1024 / 1024).toFixed(1) }} MB</b><code class="wrap">sha256 {{ onboardResult.script_sha256 }}</code></div>
                <div v-if="onboardResult.script_generated_at"><span>{{ t('生成时间') }}</span><b>{{ onboardResult.script_generated_at }}</b></div>
              </div>
              <div class="cbx-onboard-actions">
                <button class="cbx-op primary" @click="downloadOnboardScript">⬇ {{ t('下载 onboard_box.sh') }}</button>
                <button class="cbx-op" :disabled="remoteRunning" @click="doOnboardRemote">{{ remoteRunning ? t('远程接入中…') : t('远程一键接入（云端 agent 推送执行）') }}</button>
              </div>
              <p class="cbx-note" v-if="onboardResult.script_hint">{{ onboardResult.script_hint }}</p>
              <p class="cbx-note">{{ t('远程接入前提：① 平台 ⇄ 云端 agent 已配置（总览 → 配置）；② agent config.json 已配置 edge（盒子可达地址）。盒子无直达 IP 时请下载脚本后到现场执行。') }}</p>
              <div v-if="remoteSteps.length" class="cbx-remote-steps">
                <div v-for="(s, i) in remoteSteps" :key="i" class="cbx-remote-step">
                  <b :class="s.ok ? 'ok' : 'fail'">{{ s.ok ? '✔' : '✘' }} {{ i + 1 }}. {{ s.name }}</b>
                  <pre class="cbx-code" v-if="s.detail">{{ s.detail }}</pre>
                </div>
              </div>
              <details class="cbx-details" :open="ghResult">
                <summary>{{ t('GitHub 托管（盒子现场一条 curl 命令接入，免传 18MB 脚本）') }}</summary>
                <div class="cbx-form">
                  <div class="cbx-form-row">
                    <label>GitHub owner</label><input v-model="ghForm.owner" class="cbx-input" placeholder="zhibinQiu"/>
                    <label>repo</label><input v-model="ghForm.repo" class="cbx-input" placeholder="power_simulation"/>
                    <label>{{ t('分支') }}</label><input v-model="ghForm.branch" class="cbx-input" placeholder="master"/>
                    <button class="cbx-op" :disabled="ghBusy" @click="saveGithubConfig">{{ ghBusy ? t('保存中…') : t('保存配置') }}</button>
                  </div>
                  <div class="cbx-form-row">
                    <label>{{ t('GitHub PAT（公开仓库盒子现场拉取无需验证；仅「同步写入」需要，留空沿用已保存）') }}</label>
                    <input v-model="ghForm.token" type="password" class="cbx-input" placeholder="ghp_…"/>
                    <button class="cbx-op primary" :disabled="ghBusy || !onboardForm.cloudIP" @click="syncGithub">{{ ghBusy ? t('同步中（含 13MB 部署包，约 10~30s）…') : t('同步到 GitHub') }}</button>
                    <button class="cbx-op" :disabled="ghExportBusy || !onboardForm.cloudIP" @click="exportBoxConfig">{{ ghExportBusy ? t('生成中…') : '⬇ ' + t('导出 box-config.json') }}</button>
                  </div>
                  <p class="cbx-note">{{ t('「导出 box-config.json」：现场凭此配置 + 仓库脚本即可接入（放盒子') }} <code>/opt/weight-bridge/box-config.json</code>{{ t('，命令见下方）。') }}</p>
                </div>
                <div v-if="ghResult && ghResult.ok" class="cbx-kv">
                  <div><span>{{ t('盒子现场命令（任意盒子 root 执行，自动拉部署包/证书/配置 + keadm join + 自检）') }}</span><code class="wrap">{{ ghResult.command }}</code></div>
                  <div v-if="ghResult.caHash"><span>{{ t('CA 指纹') }}</span><code class="wrap">{{ ghResult.caHash }}</code></div>
                </div>
                <div v-if="ghExport && ghExport.ok" class="cbx-kv">
                  <div><span>{{ t('现场用法（配置文件已放盒子 /opt/weight-bridge/box-config.json 时，一条命令完成接入）') }}</span><code class="wrap">curl -fsSL {{ ghLauncherUrl }} | bash</code></div>
                  <div><span>{{ t('显式指定配置路径') }}</span><code class="wrap">curl -fsSL {{ ghLauncherUrl }} | bash -s -- -c /path/box-config.json</code></div>
                  <div><span>{{ t('box-config.json 内容（保存到盒子 /opt/weight-bridge/box-config.json）') }}</span><pre class="cbx-code">{{ ghExport.content }}</pre></div>
                  <div v-if="!ghExport.token_set" class="cbx-note">{{ t('token 留空：云端未取到共享 token，不影响部署 —— 脚本自动从仓库') }} <code>onboard/token</code> {{ t('拉取，也可手工填入。') }}</div>
                </div>
                <div v-if="ghResult && ghResult.files" class="cbx-remote-steps">
                  <div v-for="(f, i) in ghResult.files" :key="i" class="cbx-remote-step">
                    <b :class="f.ok ? 'ok' : 'fail'">{{ f.ok ? '✔' : '✘' }} {{ f.path }}（{{ (f.size / 1024 / 1024).toFixed(1) }} MB）</b>
                  </div>
                </div>
                <p class="cbx-note">{{ t('托管说明：平台将「引导脚本 + box-deploy 部署包 + edgecore.yaml + rootCA + token」同步至仓库') }} <code>onboard/</code> {{ t('目录（幂等覆盖）；edgecore.yaml 由盒子端按配置自动替换，token 重签后无需重推。仓库内含共享 token 与 rootCA，公开前请评估风险。盒子现场执行') }} <code>curl -fsSL {{ ghResult ? ghResult.launcher_url : '…' }} | bash</code> {{ t('即完成接入。') }}</p>
              </details>
              <details class="cbx-details">
                <summary>{{ t('高级：edgecore.yaml') }}</summary>
                <div class="cbx-preview-head"><span></span><button class="cbx-op" @click="copyOnboard">{{ t('复制') }}</button></div>
                <pre class="cbx-code">{{ onboardResult.edgecore }}</pre>
              </details>
              <details class="cbx-details">
                <summary>{{ t('高级：手工部署命令（备选）') }}</summary>
                <pre class="cbx-code">{{ onboardResult.commands.join('\n') }}</pre>
              </details>
            </div>
          </div>
        </div>

        <!-- 新建设备弹窗（工具栏「新建设备」入口） -->
        <div v-if="createOpen" class="cbx-mask" @click.self="createOpen = false">
          <div class="cbx-dialog cbx-dialog-xl">
            <div class="cbx-dialog-head">
              <b>{{ t('新建设备') }}</b>
              <button class="x-btn lg" @click="createOpen = false" :aria-label="t('关闭')">✕</button>
            </div>
            <div class="cbx-form">
              <div class="cbx-form-row">
                <label>{{ t('协议') }}</label>
                <select v-model="form.protocol" class="cbx-select">
                  <option value="modbus">{{ t('Modbus（RTU / TCP）') }}</option>
                  <option value="opcua">OPC-UA</option>
                  <option value="bluetooth">Bluetooth</option>
                  <option value="lora">{{ t('LoRaWAN（LoRa 网关）') }}</option>
                  <option value="cellular">{{ t('5G/4G 模块自监控') }}</option>
                </select>
              </div>
              <div class="cbx-form-row">
                <label>{{ t('模型') }}</label>
                <select v-model="form.modelName" class="cbx-select" @change="onPickModel" :title="t('选择已创建的 DeviceModel 复用；留空则保存时自动创建与设备同名的模型')">
                  <option value="">{{ t('（自动创建同名模型）') }}</option>
                  <option v-for="m in devices.models || []" :key="m.name" :value="m.name">{{ m.name }}（{{ m.protocol }} · {{ (m.properties || []).length }} {{ t('属性') }}）</option>
                </select>
                <button class="cbx-op cbx-xs" @click="openModelCreate" :title="t('先创建 DeviceModel 再选择')">＋ {{ t('新建模型') }}</button>
                <label>{{ t('设备名') }}</label><input v-model="form.deviceName" class="cbx-input" placeholder="box-device"/>
              </div>
              <div class="cbx-form-row">
                <label>{{ t('绑定流程设备') }}</label>
                <select v-model="form.boundDevice" class="cbx-select" style="width:300px" :title="t('从现有系统流程的设备中选择：保存后该设备的云端读数将同步到所选流程设备实例（关联制）')">
                  <option value="">{{ t('不绑定') }}</option>
                  <optgroup v-for="grp in procGroups" :key="grp.unit" :label="grp.unit">
                    <option v-for="d in grp.devices" :key="d.id" :value="d.id">{{ d.label || d.name }}（{{ d.id }}）</option>
                  </optgroup>
                </select>
                <label v-if="form.boundDevice" style="margin-left:10px">{{ t('换算系数') }}</label>
                <input v-if="form.boundDevice" v-model.number="form.boundFactor" type="number" step="any" class="cbx-input" style="width:90px" :title="t('云端原始读数 × 此系数 = 同步到流程设备的读数（如传感器 kg/min → t/h 填 0.06；无需换算填 1）')"/>
                <span class="cbx-sec-sub">{{ t('保存后云端读数同步到该流程设备') }}</span>
              </div>
              <div class="cbx-form-row">
                <label>{{ t('绑定云端设备') }}</label>
                <select v-model="form.cloudDevice" class="cbx-select" style="width:300px" :title="t('选择盒子已上报、平台已识别的云端真实设备：保存后该设备的实时读数将归入此设备（云端身份优先于此名匹配）')" @change="onPickCloudDevice">
                  <option value="">{{ t('不绑定（按设备名自动匹配）') }}</option>
                  <optgroup v-for="g in cloudUnboundGroups" :key="g.label" :label="g.label">
                    <option v-for="c in g.items" :key="c.name" :value="c.name">{{ c.name }}（{{ stateZh(c.state) }}<template v-if="c.model"> · {{ c.model }}</template>）</option>
                  </optgroup>
                  <option v-if="!cloudUnbound.length" value="" disabled>{{ t('未识别到云端设备（盒子需已接入并上报读数）') }}</option>
                </select>
                <span class="cbx-sec-sub">{{ t('选中后自动采用该云端设备名（一键转平台设备）') }}</span>
              </div>
              <div class="cbx-form-row">
                <label>{{ t('命名空间') }}</label><input v-model="form.namespace" class="cbx-input" style="width:90px" placeholder="default"/>
                <label>{{ t('调度节点') }}</label>
                <select v-model="form.nodeName" class="cbx-input" :title="t('从识别到的盒子中选择')">
                  <option v-for="n in overview.nodes || []" :key="n.name" :value="n.name">{{ n.name }}（{{ readyZh(n.ready) }}）</option>
                </select>
                <label>{{ t('采集周期(ms)') }}</label><input v-model.number="form.collectCycle" type="number" class="cbx-input" style="width:100px"/>
              </div>

              <!-- Modbus 协议参数 -->
              <template v-if="form.protocol === 'modbus'">
                <div class="cbx-form-row">
                  <label>{{ t('通信方式') }}</label>
                  <select v-model="form.comm.commType" class="cbx-select">
                    <option value="serial">{{ t('串口 RTU') }}</option>
                    <option value="tcp">TCP</option>
                  </select>
                  <label>slaveID</label><input v-model.number="form.comm.slaveID" type="number" class="cbx-input" style="width:70px"/>
                  <template v-if="form.comm.commType === 'serial'">
                    <label>{{ t('串口') }}</label><input v-model="form.comm.serialPort" class="cbx-input" style="width:110px"/>
                    <label>{{ t('波特率') }}</label><input v-model.number="form.comm.baudRate" type="number" class="cbx-input" style="width:80px"/>
                    <label>{{ t('校验') }}</label>
                    <select v-model="form.comm.parity" class="cbx-select"><option>none</option><option>even</option><option>odd</option></select>
                  </template>
                  <template v-else>
                    <label>IP</label><input v-model="form.comm.tcpIP" class="cbx-input" style="width:120px"/>
                    <label>{{ t('端口') }}</label><input v-model.number="form.comm.tcpPort" type="number" class="cbx-input" style="width:70px"/>
                  </template>
                </div>
              </template>
              <!-- OPC-UA 协议参数 -->
              <template v-else-if="form.protocol === 'opcua'">
                <div class="cbx-form-row">
                  <label>URL</label><input v-model="form.opcua.url" class="cbx-input" style="width:200px" placeholder="opc.tcp://127.0.0.1:4840"/>
                  <label>{{ t('用户名') }}</label><input v-model="form.opcua.userName" class="cbx-input" style="width:100px"/>
                  <label>{{ t('密码') }}</label><input v-model="form.opcua.password" class="cbx-input" style="width:100px"/>
                </div>
              </template>
              <!-- Bluetooth 协议参数 -->
              <template v-else-if="form.protocol === 'bluetooth'">
                <div class="cbx-form-row">
                  <label>{{ t('MAC 地址') }}</label><input v-model="form.bluetooth.macAddress" class="cbx-input" style="width:160px" placeholder="AA:BB:CC:DD:EE:FF"/>
                </div>
              </template>
              <!-- LoRaWAN 协议参数（盒子侧 LoRa 网关 + ChirpStack，上行走本地 mosquitto） -->
              <template v-else-if="form.protocol === 'lora'">
                <div class="cbx-form-row">
                  <label>Broker</label><input v-model="form.lora.broker" class="cbx-input" style="width:130px" placeholder="127.0.0.1"/>
                  <label>{{ t('端口') }}</label><input v-model.number="form.lora.port" type="number" class="cbx-input" style="width:70px"/>
                  <label>{{ t('应用ID') }}</label><input v-model="form.lora.applicationID" class="cbx-input" style="width:70px" placeholder="1"/>
                  <label>DevEUI</label><input v-model="form.lora.devEUI" class="cbx-input" style="width:150px" placeholder="0011223344556677"/>
                  <label>{{ t('从站号') }}</label><input v-model.number="form.lora.slaveId" type="number" min="0" max="247" class="cbx-input" style="width:70px"
                                                      :title="t('同一台 LoRa 透传 DTU 下挂多台 485 传感器时按此站号区分（如 env-temp 站2、shuitong-temp 站7）；0 = 被动上报，不下发问帧')"/>
                </div>
                <div class="cbx-form-row">
                  <span class="cbx-sec-hint">{{ t('从站号：同一台 LoRa DTU 下挂多台 485 传感器时按此区分，0 表示被动上报（下行取数与解析按该站号拼帧）') }}</span>
                </div>
                <div class="cbx-form-row">
                  <label>AppKey</label><input v-model="form.lora.appKey" class="cbx-input" style="width:160px"/>
                  <label>{{ t('频段') }}</label>
                  <select v-model="form.lora.region" class="cbx-select"><option>CN470</option><option>EU868</option><option>US915</option></select>
                  <label>{{ t('数据率') }}</label>
                  <select v-model="form.lora.dataRate" class="cbx-select"><option>SF7BW125</option><option>SF9BW125</option><option>SF12BW125</option></select>
                </div>
              </template>
              <!-- 5G/4G 模块自监控协议参数 -->
              <template v-else-if="form.protocol === 'cellular'">
                <div class="cbx-form-row">
                  <label>{{ t('AT 串口') }}</label><input v-model="form.cellular.serialPort" class="cbx-input" style="width:130px" placeholder="/dev/ttyUSB2"/>
                  <label>{{ t('波特率') }}</label><input v-model.number="form.cellular.baudRate" type="number" class="cbx-input" style="width:90px"/>
                  <label>APN</label><input v-model="form.cellular.apn" class="cbx-input" style="width:100px" placeholder="cmnet"/>
                  <label>{{ t('蜂窝网卡') }}</label><input v-model="form.cellular.iface" class="cbx-input" style="width:90px" placeholder="wwan0"/>
                </div>
              </template>

              <!-- 属性点位：已绑定模型时点位由模型承载，此处不再提供编辑 -->
              <template v-if="form.modelName">
                <div class="cbx-sec-head" style="margin-top:8px">
                  <b>{{ t('属性点位') }}</b>
                  <span class="cbx-sec-sub">{{ t('已绑定模型，点位由模型承载，请在「模型」卡片中修改') }}</span>
                </div>
                <div class="cbx-form-row">
                  <span class="cbx-sec-hint"><code>{{ form.modelName }}</code>：{{ modelPropNames(pickedModelProps) || t('该模型暂无点位') }}</span>
                </div>
              </template>
              <template v-else>
              <!-- 属性点位 -->
              <div class="cbx-sec-head" style="margin-top:8px">
                <b>{{ t('属性点位') }}</b>
                <button class="cbx-op" @click="addProp">＋ {{ t('添加') }}</button>
              </div>
              <div v-for="(p, i) in form.properties" :key="i" class="cbx-prop-row">
                <input v-model="p.name" class="cbx-input" style="width:110px" :placeholder="t('属性名')"/>
                <select v-model="p.type" class="cbx-select">
                  <option v-for="tp in ['float','int','double','string','boolean']" :key="tp">{{ tp }}</option>
                </select>
                <select v-model="p.accessMode" class="cbx-select">
                  <option value="r">ReadOnly</option><option value="rw">ReadWrite</option>
                </select>
                <template v-if="form.protocol === 'modbus'">
                  <select v-model="p.registerType" class="cbx-select">
                    <option v-for="r in ['holdingRegister','inputRegister','coil','discreteInput']" :key="r">{{ r }}</option>
                  </select>
                  <input v-model.number="p.register" type="number" class="cbx-input" style="width:70px" :placeholder="t('寄存器')"/>
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="form.protocol === 'opcua'">
                  <input v-model="p.nodeID" class="cbx-input" style="width:170px" placeholder="nodeID"/>
                </template>
                <template v-else-if="form.protocol === 'bluetooth'">
                  <input v-model="p.characteristicUUID" class="cbx-input" style="width:170px" placeholder="characteristicUUID"/>
                </template>
                <template v-else-if="form.protocol === 'lora'">
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="form.protocol === 'cellular'">
                  <select v-model="p.kind" class="cbx-select">
                    <option v-for="k in ['signal','csq','rsrp','rsrq','sinr','iccid','imsi','imei','reg','rx_rate','tx_rate']" :key="k">{{ k }}</option>
                  </select>
                </template>
                <input v-model="p.unit" class="cbx-input" style="width:60px" :placeholder="t('单位')"/>
                <button class="x-btn danger" @click="form.properties.splice(i, 1)" :title="t('删除属性')">✕</button>
              </div>
              </template>

              <div class="cbx-form-row" style="margin-top:10px">
                <button class="cbx-op primary" @click="dryRun()">{{ t('生成 YAML 预览') }}</button>
                <button class="cbx-op primary" @click="applyDev()" :title="t('保存到本地 box_devices.json 并立即下发云端 K3s（无需单独保存）')">{{ t('下发到云端') }}</button>
                <span class="cbx-sec-sub" v-if="formErr" style="color:var(--red)">{{ formErr }}</span>
              </div>

              <!-- YAML 预览 -->
              <div v-if="preview" class="cbx-preview">
                <div class="cbx-preview-head">
                  <b>{{ t('YAML 预览') }}</b>
                  <button class="cbx-op" @click="copyPreview">{{ t('复制') }}</button>
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
              <b>{{ t('新建模型（DeviceModel）') }}</b>
              <span class="cbx-sec-hint">{{ t('保存后可在「设备接入」中选择该模型') }}</span>
              <button class="x-btn lg" @click="modelCreateOpen = false" :aria-label="t('关闭')">✕</button>
            </div>
            <div class="cbx-form">
              <div class="cbx-form-row">
                <label>{{ t('协议') }}</label>
                <select v-model="modelForm.protocol" class="cbx-select">
                  <option value="modbus">{{ t('Modbus（RTU / TCP）') }}</option>
                  <option value="opcua">OPC-UA</option>
                  <option value="bluetooth">Bluetooth</option>
                  <option value="lora">{{ t('LoRaWAN（LoRa 网关）') }}</option>
                  <option value="cellular">{{ t('5G/4G 模块自监控') }}</option>
                </select>
                <label>{{ t('命名空间') }}</label><input v-model="modelForm.namespace" class="cbx-input" style="width:110px" placeholder="default"/>
              </div>
              <div class="cbx-form-row">
                <label>{{ t('模型名') }}</label><input v-model="modelForm.modelName" class="cbx-input" placeholder="box-metric-model"/>
                <span class="cbx-sec-sub">{{ t('模型名 = DeviceModel CRD 的 metadata.name，设备通过它引用') }}</span>
              </div>
              <div class="cbx-sec-head" style="margin-top:8px">
                <b>{{ t('属性点位') }}</b>
                <button class="cbx-op" @click="addModelProp">＋ {{ t('添加') }}</button>
              </div>
              <div v-for="(p, i) in modelForm.properties" :key="i" class="cbx-prop-row">
                <input v-model="p.name" class="cbx-input" style="width:110px" :placeholder="t('属性名')"/>
                <select v-model="p.type" class="cbx-select">
                  <option v-for="tp in ['float','int','double','string','boolean']" :key="tp">{{ tp }}</option>
                </select>
                <select v-model="p.accessMode" class="cbx-select">
                  <option value="r">ReadOnly</option><option value="rw">ReadWrite</option>
                </select>
                <template v-if="modelForm.protocol === 'modbus'">
                  <select v-model="p.registerType" class="cbx-select">
                    <option v-for="r in ['holdingRegister','inputRegister','coil','discreteInput']" :key="r">{{ r }}</option>
                  </select>
                  <input v-model.number="p.register" type="number" class="cbx-input" style="width:70px" :placeholder="t('寄存器')"/>
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="modelForm.protocol === 'opcua'">
                  <input v-model="p.nodeID" class="cbx-input" style="width:170px" placeholder="nodeID"/>
                </template>
                <template v-else-if="modelForm.protocol === 'bluetooth'">
                  <input v-model="p.characteristicUUID" class="cbx-input" style="width:170px" placeholder="characteristicUUID"/>
                </template>
                <template v-else-if="modelForm.protocol === 'lora'">
                  <input v-model="p.scale" class="cbx-input" style="width:60px" placeholder="scale"/>
                </template>
                <template v-else-if="modelForm.protocol === 'cellular'">
                  <select v-model="p.kind" class="cbx-select">
                    <option v-for="k in ['signal','csq','rsrp','rsrq','sinr','iccid','imsi','imei','reg','rx_rate','tx_rate']" :key="k">{{ k }}</option>
                  </select>
                </template>
                <input v-model="p.unit" class="cbx-input" style="width:60px" :placeholder="t('单位')"/>
                <button class="x-btn danger" @click="modelForm.properties.splice(i, 1)" :title="t('删除属性')">✕</button>
              </div>

              <div class="cbx-form-row" style="margin-top:10px">
                <button class="cbx-op primary" @click="modelDryRun()">{{ t('生成 YAML 预览') }}</button>
                <button class="cbx-op primary" @click="applyModelForm()" :title="t('保存到本地 box_devices.json 并立即下发云端 K3s（无需单独保存）')">{{ t('下发到云端') }}</button>
                <span class="cbx-sec-sub" v-if="modelFormErr" style="color:var(--red)">{{ modelFormErr }}</span>
              </div>

              <!-- YAML 预览 -->
              <div v-if="modelPreview" class="cbx-preview">
                <div class="cbx-preview-head">
                  <b>{{ t('YAML 预览') }}</b>
                  <button class="cbx-op" @click="copyModelPreview">{{ t('复制') }}</button>
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
          <b>{{ t('云端 Broker 配置') }}</b>
          <button class="x-btn lg" @click="boxCfgOpen = false" :aria-label="t('关闭')">✕</button>
        </div>
        <div class="cbx-form">
          <div class="cbx-form-row">
            <label>{{ t('Broker 地址') }}</label><input v-model="boxCfg.host" class="cbx-input" style="flex:1" placeholder="127.0.0.1"/>
            <label>{{ t('端口') }}</label><input v-model.number="boxCfg.port" type="number" class="cbx-input" style="width:90px" placeholder="41883"/>
          </div>
          <div class="cbx-form-row">
            <label>{{ t('用户名') }}</label><input v-model="boxCfg.username" class="cbx-input" style="flex:1" :placeholder="t('可选')"/>
            <label>{{ t('密码') }}</label><input v-model="boxCfg.password" type="password" class="cbx-input" style="flex:1" :placeholder="t('可选')"/>
          </div>
          <p class="cbx-note">{{ t('保存后立即断开并按新配置重连（热更新），配置持久化到 box_config.json。') }}</p>
          <div class="cbx-form-sep">{{ t('云端 Agent（数据通道：MQTT cloud/# 推送读 + HTTP 写，替代 SSH）') }}</div>
          <div class="cbx-form-row">
            <label>{{ t('Agent 端口') }}</label><input v-model.number="boxCfg.agent_port" type="number" class="cbx-input" style="width:90px" placeholder="42083"/>
            <label>{{ t('Agent Token') }}</label><input v-model="boxCfg.agent_token" class="cbx-input" style="flex:1" :placeholder="t('与云端 install_agent.sh --token 一致')"/>
            <label>{{ t('命名空间') }}</label><input v-model="boxCfg.namespace" class="cbx-input" style="width:110px" placeholder="default"/>
          </div>
          <div class="cbx-form-hint">{{ t('云端部署 cloud-agent 后填写此处的 Token/端口（安装命令见「一键下发」区块），保存即生效：概览/CRD/日志经 MQTT 长连接实时推送，下发/删除/回写走 HTTP，全程无需 SSH。') }}</div>
          <div class="cbx-form-row">
            <button class="cbx-op primary" :disabled="boxCfgSaving" @click="saveBoxConfig">{{ boxCfgSaving ? t('保存中…') : t('保存并重连') }}</button>
            <button class="cbx-op" @click="boxCfgOpen = false">{{ t('取消') }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ==================== 盒子配置弹窗（显示名称 + IP/SSH 凭据，重启 Mapper 前置条件） ==================== -->
    <div v-if="edgeCfgOpen" class="cbx-mask" @click.self="edgeCfgOpen = false">
      <div class="cbx-dialog">
        <div class="cbx-dialog-head">
          <b>{{ t('盒子连接配置（') }}<code>{{ boxAliases[edgeCfgBox] || edgeCfgBox || '' }}</code>{{ t('）') }}</b>
          <button class="x-btn lg" @click="edgeCfgOpen = false" :aria-label="t('关闭')">✕</button>
        </div>
        <div class="cbx-form">
          <div class="cbx-form-row">
            <label>{{ t('名称') }}</label><input v-model="edgeCfg.name" class="cbx-input" style="flex:1" :placeholder="t('盒子显示名称（留空=使用云端节点名）')"/>
            <label>{{ t('节点名') }}</label><code class="cbx-input" style="flex:0 0 auto;width:auto;padding:4px 8px;font-size:10.5px;color:var(--muted)">{{ edgeCfgBox }}</code>
          </div>
          <div class="cbx-form-row">
            <label>{{ t('盒子 IP') }}</label><input v-model="edgeCfg.host" class="cbx-input" style="flex:1" :placeholder="t('现场可达地址（内网 IP / 跳板机 / frp）')"/>
            <label>{{ t('端口') }}</label><input v-model.number="edgeCfg.port" type="number" class="cbx-input" style="width:90px" placeholder="22"/>
          </div>
          <div class="cbx-form-row">
            <label>{{ t('用户名') }}</label><input v-model="edgeCfg.user" class="cbx-input" style="flex:1" placeholder="root"/>
            <label>{{ t('密码') }}</label><input v-model="edgeCfg.password" type="password" class="cbx-input" style="flex:1" :placeholder="t('SSH 密码（或填密钥）')"/>
          </div>
          <div class="cbx-form-row">
            <label>{{ t('密钥') }}</label><input v-model="edgeCfg.key" class="cbx-input" style="flex:1" :placeholder="t('/root/.ssh/id_rsa（可选）')"/>
          </div>
          <div class="cbx-form-hint">{{ t('盒子运行期无直达 IP；此处为部署/现场运维时可达地址（现场内网 / 手机热点 / frp）。') }}<br/>
            {{ t('IP 为空或 SSH 探测不通时，「重启 Mapper」等 SSH 操作将被拒绝。保存后自动探测连通性。') }}</div>
          <div class="cbx-form-row">
            <button class="cbx-op primary" :disabled="edgeCfgSaving" @click="saveEdgeCfg">{{ edgeCfgSaving ? t('保存中…') : t('保存并探测') }}</button>
            <button class="cbx-op" :disabled="edgeCfgChecking" @click="checkEdgeCfg()">{{ edgeCfgChecking ? t('探测中…') : '∿ ' + t('仅探测') }}</button>
            <span v-if="edgeCfgCheckResult" class="cbx-edge-check" :class="{ ok: edgeCfgCheckResult.reachable, bad: !edgeCfgCheckResult.reachable }">
              {{ edgeCfgCheckResult.reachable ? t('✓ 可达') : t('✗ 不可达') }}
            </span>
            <button class="cbx-op" @click="edgeCfgOpen = false">{{ t('取消') }}</button>
          </div>
        </div>
      </div>
    </div>

    <!-- ==================== 云端部署应用/模型弹窗 ==================== -->
    <div v-if="appDeployOpen" class="cbx-mask" @click.self="appDeployOpen = false">
      <div class="cbx-dialog">
        <div class="cbx-dialog-head">
          <b>{{ t('云端部署到盒子（') }}<code>{{ appDeployForm.box }}</code>{{ t('）') }}</b>
          <button class="x-btn lg" @click="appDeployOpen = false" :aria-label="t('关闭')">✕</button>
        </div>
        <div class="cbx-form">
          <div class="cbx-form-row">
            <label>{{ t('类型') }}</label>
            <select v-model="appDeployForm.type" class="cbx-input" style="width:150px">
              <option value="service">{{ t('服务（可运行进程）') }}</option>
              <option value="model">{{ t('模型（仅存储）') }}</option>
            </select>
            <label>{{ t('名称') }}</label><input v-model="appDeployForm.name" class="cbx-input" style="flex:1" :placeholder="t('如 carbon-emission-model / predict-svc')"/>
          </div>
          <div class="cbx-form-row">
            <label>{{ t('下载地址') }}</label><input v-model="appDeployForm.url" class="cbx-input" style="flex:1" :placeholder="t('https://…/model.tar.gz 或脚本 URL（盒子侧下载安装）')"/>
          </div>
          <div class="cbx-form-row" v-if="appDeployForm.type === 'service'">
            <label>{{ t('启动命令') }}</label><input v-model="appDeployForm.command" class="cbx-input" style="flex:1" :placeholder="t('如 python3 run.py（相对应用目录，可空=只安装不启动）')"/>
          </div>
          <div class="cbx-form-row" v-if="appDeployForm.type === 'service'">
            <label>{{ t('参数') }}</label><input v-model="appDeployForm.args" class="cbx-input" style="flex:1" :placeholder="t('空格分隔，如 --port 8000')"/>
            <label>{{ t('版本') }}</label><input v-model="appDeployForm.version" class="cbx-input" style="width:110px" placeholder="1.0.0"/>
          </div>
          <div class="cbx-form-hint">{{ t('指令经云端 Broker 命令主题') }} <code>cmd/{{ appDeployForm.box }}/deploy</code> {{ t('下发，盒子 mapper 订阅执行；') }}<br/>
            {{ t('执行结果回报') }} <code>state/{{ appDeployForm.box }}/deploy</code>{{ t('，运行服务周期上报到卡片。') }}</div>
          <div class="cbx-form-row">
            <button class="cbx-op primary" :disabled="appDeploySaving" @click="doAppDeploy">{{ appDeploySaving ? t('下发中…') : t('下发部署') }}</button>
            <button class="cbx-op" @click="appDeployOpen = false">{{ t('取消') }}</button>
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
import { t } from '../i18n'
import { visiblePoll } from '../utils/poll'
import DataServiceApiPanel from './DataServiceApiPanel.vue'
// 云端时序历史查询弹窗（TDengine）：异步分包，点开才加载
const CloudHistoryDialog = defineAsyncComponent(() => import('./CloudHistoryDialog.vue'))

const store = useSimStore()

// ---- 单页布局（设备配置已并入通信拓扑图，无 tab）----
const expanded = reactive({ boxes: true, models: true, devs: true, unmounted: false })
const sideTitle = t('设备导航')
const sideCount = computed(() => `${topoBoxes.value?.length || 0} ${t('盒')} · ${mergedModels.value.length} ${t('模型')} · ${mergedDevices.value.length} ${t('设备')}`)

// 合并界面：原「数据概览」+「设备管理」二合一（云端设备关联 / 边缘节点 / twins 实时值 / CloudHub 端口已移除）

// ================= 数据源接入（能碳一体机 + 外部数据源，含独立模拟源） =================
// 统一概念：一体机 = 云端 Broker 订阅通道；外部数据源（含模拟数据，由独立服务 sim-source
// 生成）= 注册到数据中间件后由中间件转换为标准 MQTT 发布，平台按 box 前缀识别归属。
// 列表/启停/状态来自 GET /api/data-sources（含中间件服务在线状态），卡片内操作转发 REST。
const sourcesResp = reactive({ sources: [], middleware: {} })
const sourcesLoading = ref(false)
const mwChecked = ref(false)          // 是否已探测过中间件（得到过确定结果）
// 数据服务接口清单已独立为单独模块：见 DataServiceApiPanel.vue（命令执行区块之后）
// 各区块折叠态（true=展开）：默认只展开常用区块，折叠区块不渲染 DOM（首屏更快）
const secFold = ref({ overview: true, sources: false, topo: false, reslist: true,
  certs: false, msglog: false, cmd: true })
function toggleSec(k) {
  secFold.value = { ...secFold.value, [k]: !secFold.value[k] }
}

const middleware = computed(() => sourcesResp.middleware || {})
const mwOnline = computed(() => !!middleware.value.online)
const boxEntry = computed(() => (sourcesResp.sources || []).find(s => s.type === 'box') || null)
const boxSrc = computed(() => boxEntry.value
  || { id: 'box', name: t('能碳一体机'), type: 'box', enabled: true, status: {} })
const boxSt = computed(() => boxSrc.value.status || {})
const boxLastMsg = computed(() => { const m = boxSt.value.last_msg; return m ? (m.topic || '') : '' })
const extSources = computed(() => (sourcesResp.sources || []).filter(s => s.type !== 'box'))

async function loadSources() {
  sourcesLoading.value = true
  try {
    const r = await api.dataSources()
    sourcesResp.sources = (r && r.sources) || []
    sourcesResp.middleware = (r && r.middleware) || {}
    mwChecked.value = true
  } catch (e) {
    mwChecked.value = true
    sourcesResp.middleware = { online: false, error: e.message || t('无法获取数据源状态') }
  } finally { sourcesLoading.value = false }
}
// 最近一条消息时间（external 状态里为 epoch 秒）→ 「X 分钟前」
function agoText(sec) {
  if (!sec) return ''
  const s = Math.max(0, Date.now() / 1000 - Number(sec))
  if (s < 5) return t('刚刚')
  if (s < 60) return t('{n} 秒前', { n: Math.round(s) })
  if (s < 3600) return t('{n} 分钟前', { n: Math.round(s / 60) })
  if (s < 86400) return t('{n} 小时前', { n: Math.round(s / 3600) })
  return t('{n} 天前', { n: Math.round(s / 86400) })
}

// ---- 接入类型与参数 schema（优先中间件注册表；离线用本地内置模板） ----
const adapterTypes = ref([
  { type: 'mqtt', label: t('外部 MQTT') },
])
// 本地字段模板（中间件不可达时的兜底 schema；形状与中间件注册表 fields 一致）
const localFieldTpls = {
  mqtt: [
    { name: 'broker.host', label: t('Broker 地址'), required: true, placeholder: '10.0.0.9' },
    { name: 'broker.port', label: t('Broker 端口'), kind: 'num', default: '1883', placeholder: '1883' },
    { name: 'broker.username', label: t('用户名（可空）') },
    { name: 'broker.password', label: t('密码（可空）'), type: 'password' },
    { name: 'topics', label: t('订阅主题'), type: 'array', required: true,
      desc: t('JSON 数组。中间件订阅外部主题后，将每条消息转投给平台（前缀化发布）') },
    { name: 'fieldMap', label: t('字段映射（可选）'), type: 'json',
      desc: t('把外部消息字段映射为平台标准字段（v/device/value/t），如 {"value":"reading"}') },
    { name: 'device', label: t('默认设备 id（可选）'),
      placeholder: t('外部消息无 device 字段时使用') },
  ],
  sim: [
    { name: 'interval', label: t('发布间隔（秒）'), kind: 'num', default: '2' },
    { name: 'devices', label: t('模拟设备（可选 JSON）'), type: 'json',
      desc: t('留空时平台将自动注入默认示例设备；格式 [{id,name,properties:[{name,base,amplitude,noise,period,unit}]}]') },
  ],
}
async function loadAdapterTypes() {
  try {
    const r = await api.middlewareTypes()
    if (r && Array.isArray(r.types) && r.types.length) {
      adapterTypes.value = r.types.map(x => ({ type: x.type, label: x.label || x.type, fields: x.fields || [] }))
    }
  } catch (e) { /* 中间件不可达：沿用本地模板 */ }
}
// 需要 JSON/列表式编辑（textarea）的字段类型（中间件注册表：json/list/number/devices/text/password）
const JSON_LIKE_TYPES = ['json', 'array', 'list', 'devices']
function isJsonLike(t) { return JSON_LIKE_TYPES.includes(t) }
function adapterFieldTpl(type) {
  const info = adapterTypes.value.find(a => a.type === type)
  const raw = (info && info.fields && info.fields.length) ? info.fields : (localFieldTpls[type] || [])
  // 中间件注册表 schema 以 key 标识字段（平台内部用 name），统一归一化
  return raw.map(f => ({ ...f, name: f.name || f.key || '' }))
}
// 取值兼容：既有扁平键（'broker.host'）也有嵌套 params（{broker:{host}}）
function fieldRaw(values, name) {
  if (!values) return undefined
  if (name in values) return values[name]
  const segs = String(name).split('.')
  let o = values
  for (let i = 0; i < segs.length; i++) {
    if (o == null || typeof o !== 'object') return undefined
    o = o[segs[i]]
  }
  return o
}
// 生成表单字段（values: 已保存 params → 打散到字段；保持跨类型切换留值）
function makeFields(type, values) {
  return adapterFieldTpl(type).map(f => {
    const key = f.name
    let v = ''
    const rawVal = fieldRaw(values, key)
    if (rawVal !== undefined) {
      v = isJsonLike(f.type)
        ? (rawVal == null ? '' : JSON.stringify(rawVal))
        : String(rawVal)
    } else if (f.default !== undefined) v = String(f.default)
    return { ...f, type: f.type || 'text', v }
  })
}

// ---- 注册 / 编辑表单 ----
const formOpen = ref(false)
const formSaving = ref(false)
const extFormErr = ref('')
const extForm = reactive({ id: '', name: '', adapter: 'mqtt', box: '', desc: '', fields: [] })
function openAddForm(prefer) {
  extForm.id = ''; extForm.name = ''; extForm.box = ''; extForm.desc = ''
  extFormErr.value = ''
  extForm.adapter = (prefer && adapterTypes.value.some(a => a.type === prefer)) ? prefer
    : ((adapterTypes.value[0] && adapterTypes.value[0].type) || 'mqtt')
  extForm.fields = makeFields(extForm.adapter)
  formOpen.value = true
}
function openEditForm(s) {
  extForm.id = s.id
  extForm.name = s.name || ''
  extForm.adapter = (s.config && s.config.adapter) || 'mqtt'
  extForm.box = (s.config && s.config.box) || ''
  extForm.desc = (s.config && s.config.desc) || ''
  extFormErr.value = ''
  extForm.fields = makeFields(extForm.adapter, (s.config && s.config.params) || {})
  formOpen.value = true
}
function closeForm() { formOpen.value = false }
function onAdapterChange() {
  const kept = {}
  for (const f of extForm.fields) kept[f.name] = f.v
  extForm.fields = makeFields(extForm.adapter, kept)
}
function validateForm() {
  extFormErr.value = ''
  extForm.box = String(extForm.box || '').trim().toLowerCase()
  if (!extForm.box) { extFormErr.value = t('请填写发布前缀（小写字母/数字/连字符，如 ext-weigh）'); return false }
  if (!/^[a-z0-9][a-z0-9-]{0,31}$/.test(extForm.box)) { extFormErr.value = t('发布前缀仅允许小写字母/数字/连字符（如 ext-weigh）'); return false }
  for (const f of extForm.fields) {
    if (f.required && !String(f.v || '').trim()) { extFormErr.value = t('请填写接入参数：') + f.label; return false }
  }
  return true
}
// 字段 → 嵌套 params（支持 broker.host 形式的点号键）
function buildParams() {
  const params = {}
  for (const f of extForm.fields) {
    if (String(f.v ?? '') === '') continue
    let val = f.v
    if (isJsonLike(f.type)) {
      // list/array 容忍非 JSON 输入（按逗号/分号/换行拆分）；json/devices 需严格 JSON
      const txt = String(f.v || '').trim()
      try {
        val = JSON.parse(txt)
      } catch (e) {
        if (f.type === 'list' || f.type === 'array') {
          val = txt.split(/[,;\n]/).map(s => s.trim()).filter(Boolean)
        } else {
          extFormErr.value = t('参数「{label}」不是合法 JSON', { label: f.label }); return null
        }
      }
    } else if (f.kind === 'num' || f.type === 'number') { val = Number(f.v) }
    const segs = String(f.name).split('.')
    let o = params
    for (let i = 0; i < segs.length - 1; i++) o = (o[segs[i]] = o[segs[i]] || {})
    o[segs[segs.length - 1]] = val
  }
  return params
}
async function saveForm() {
  if (!validateForm()) return
  const params = buildParams()
  if (params === null) return
  const config = { box: extForm.box, adapter: extForm.adapter, params, desc: extForm.desc }
  const name = (extForm.name || '').trim() || extForm.box
  formSaving.value = true
  try {
    const r = extForm.id
      ? await api.dataSourceSave(extForm.id, { name, config })
      : await api.dataSourceAdd({ name, config })
    if (!r.ok) { extFormErr.value = r.error || t('保存失败'); return }
    store.showToast(r.note || t('已保存'), 'success')
    await loadSources()
    closeForm()
  } catch (e) { extFormErr.value = e.message || String(e) }
  finally { formSaving.value = false }
}
async function toggleSource(s, ev) {
  const on = !!ev.target.checked
  const prev = s.enabled
  s.enabled = on
  try {
    const r = await api.dataSourceToggle(s.id, on)
    if (!r.ok) { s.enabled = prev; store.showToast(r.error || t('操作失败'), 'error'); return }
    store.showToast(r.note || (on ? t('已启用') : t('已停用')), 'success')
    await loadSources()
  } catch (e) { s.enabled = prev; store.showToast(t('操作失败') + '：' + (e.message || e), 'error') }
}
async function removeSource(s) {
  // 内置源与外部源统一管理、无例外：内置源删除后立即停止采纳数据，可经 restore 加回
  const msg = s.type === 'box'
    ? t('删除内置数据源「{name}」？平台将立即停止采纳盒子上报数据，可在列表中恢复。', { name: s.name })
    : t('删除外部数据源「{name}」？中间件将同步注销采集。', { name: s.name })
  if (!confirm(msg)) return
  try {
    const r = await api.dataSourceRemove(s.id)
    if (!r.ok) { store.showToast(r.error || t('删除失败'), 'error'); return }
    store.showToast(r.note || t('已删除'), 'success')
    await loadSources()
  } catch (e) { store.showToast(t('删除失败') + '：' + (e.message || e), 'error') }
}
async function restoreBox() {
  try {
    const r = await api.dataSourceRestore('box')
    if (!r.ok) { store.showToast(r.error || t('恢复失败'), 'error'); return }
    store.showToast(r.note || t('已恢复内置数据源'), 'success')
    await loadSources()
  } catch (e) { store.showToast(t('恢复失败') + '：' + (e.message || e), 'error') }
}
// 测试（表单 → 探测；卡片 → 按已保存配置探测）
async function testForm() {
  if (!validateForm()) return
  const params = buildParams()
  if (params === null) return
  const cfg = { box: extForm.box, adapter: extForm.adapter, params, target: extForm.target }
  try {
    const r = await api.dataSourceTest({ config: cfg })
    store.showToast((r.ok ? t('连通性测试通过') : t('测试失败') + '：' + ((r.message || r.error || ''))) || t('无结果'), r.ok ? 'success' : 'error')
  } catch (e) { store.showToast(t('测试失败') + '：' + (e.message || e), 'error') }
}
async function testSource(s) {
  s.testing = true
  const cfg = { box: s.config.box, adapter: s.config.adapter, params: s.config.params || {}, target: s.config.target || '' }
  try {
    const r = await api.dataSourceTest({ id: s.id, config: cfg })
    store.showToast((r.ok ? t('连通性测试通过') : t('测试失败') + '：' + ((r.message || r.error || ''))) || t('无结果'), r.ok ? 'success' : 'error')
  } catch (e) { store.showToast(t('测试失败') + '：' + (e.message || e), 'error') }
  finally { s.testing = false }
}

// ---- 轮询定时器 ----
// 快慢拆分：数据概览（链路状态/实时读数/消息流）3s，设备配置列表 30s；数据源状态并入快轮询由
// 后端聚合返回（一次 /api/data-sources 同时给出目录 + 中间件服务 + 各源运行状态），每 6s 拉一次。
// 一律走 visiblePoll：页面切到后台（别的标签/最小化）时整轮跳过，回来立即补一轮。
let stopFastPoll = null
let stopSlowPoll = null
let stopSourcesPoll = null
const startPolling = () => {
  stopPolling()
  stopFastPoll = visiblePoll(refreshFast, 3000)
  stopSlowPoll = visiblePoll(refreshSlow, 30000)
  // 数据源状态 10s 一次；区块折叠时跳过（折叠意味着用户不看，展开时补拉）
  stopSourcesPoll = visiblePoll(() => { if (secFold.value.sources) loadSources() }, 10000)
}
// 展开区块时立刻补拉其数据，避免「展开后要等下一个轮询周期才有内容」
watch(() => ({ ...secFold.value }), (now, prev) => {
  if (now.sources && !prev.sources) loadSources()
  if (now.msglog && !prev.msglog) loadMessages()
})
const stopPolling = () => {
  if (stopFastPoll) { stopFastPoll(); stopFastPoll = null }
  if (stopSlowPoll) { stopSlowPoll(); stopSlowPoll = null }
  if (stopSourcesPoll) { stopSourcesPoll(); stopSourcesPoll = null }
}
onMounted(() => {
  restoreTopoPos()
  refreshAll(); loadCloudCfg(); loadAgentStatus(); startPolling()
  loadEdgeCfgSilent()
  setupTopoLinks()
  // 数据源接入：目录 + 中间件服务状态 + 接入类型 schema（含中间件连接配置初始值）
  loadSources(); loadAdapterTypes()
  // 云端 CRD 先渲染 MQTT 推送缓存（首屏不等 agent HTTP）；仅当缓存为空时才后台补拉一次，
  // 避免开发机等 agent 不可达环境下每次进页面都同步等待 5s 超时。
  setTimeout(() => {
    if (!(cloudCrd.value.devices || []).length && !(cloudCrd.value.models || []).length) loadCloudCrd(true)
  }, 800)
  // 订阅配置变更：别人改了采集设备配置，本客户端自动同步（首次连接收到 snapshot 拿当前 rev）
  cfgWs = api.openConfigFeed(onConfigMsg)
})
onUnmounted(() => {
  stopPolling(); closeDevRealtime()
  stopTopoLinks()
  if (cfgWs) { try { cfgWs.close() } catch (e) { /* ignore */ } cfgWs = null }
  clearTimeout(cfgSyncTimer)
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
  // slaveId：LoRa 从站号——同一台 LoRa 透传 DTU 下挂多台 485 传感器时，靠它区分设备（0=被动上报，不下发问帧）
  lora: { broker: '127.0.0.1', port: 41884, applicationID: '1', devEUI: '', appKey: '', region: 'CN470', dataRate: 'SF7BW125', slaveId: 0 },
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
  // 点位复位：避免上一次选过模型后残留的点位被写进新建的同名模型
  form.properties.splice(0, form.properties.length, { name: 'value', type: 'float', accessMode: 'r', registerType: 'holdingRegister', register: 0, scale: 1, unit: '' })
  // 默认选中第一个 Ready 盒子，避免出现「未识别」选项
  const ready = (overview.value.nodes || []).find((n) => n.ready) || (overview.value.nodes || [])[0]
  if (ready) form.nodeName = ready.name
  loadLinks()
  createOpen.value = true
}
async function loadDevices() { try { devices.value = await api.boxDevices() } catch (e) {} }

// ---- 点位归属：设备绑定模型后，属性点位由模型承载（新建/配置弹窗只做只读展示）----
function modelByName(name) {
  const k = (name || '').trim()
  if (!k) return null
  return (devices.value.models || []).find((m) => m.name === k) || null
}
function modelPropNames(props) { return (props || []).map((p) => p.name || '?').join('、') }
// 新建/编辑表单当前所选模型的点位（getter 惰性求值：editForm/editTarget 在下方声明）
const pickedModelProps = computed(() => (modelByName(form.modelName) || {}).properties || [])
const pickedEditModelProps = computed(() => (editTarget.value === 'model' ? [] : (modelByName(editForm.modelName) || {}).properties || []))
// 设备请求体：已绑定模型时以模型点位为准，避免把表单残留/空点位写回共享模型
function devPayload(f, mode) {
  const p = { ...f, mode }
  const name = (f.modelName || '').trim()
  if (!name) return p   // 未绑模型：点位由表单定义（保存时自动创建与设备同名的模型）
  const m = modelByName(name)
  if (!m) throw new Error(t('模型「{name}」不存在，请刷新页面后重试', { name }))
  p.properties = (m.properties || []).map((x) => ({ ...x }))
  return p
}
// 改名冲突：目标名已被其它设备占用时禁止提交（后端同样拦截，此处即时提示，避免下发后才报错）
function renameClash(f) {
  const target = (f.deviceName || '').trim()
  const orig = (f.origName || '').trim()
  if (!orig || target === orig) return ''
  const hit = (devices.value.devices || []).find((d) => d.name === target && d.name !== orig)
  return hit ? hit.name : ''
}

// ---- 绑定平台流程设备（关联制：云端识别设备 <-> 仿真设备实例，links.json 持久化）----
// 平台仿真流程设备（store.allDevices：计量设备 + 可调设备），按工序分组供下拉选择
const procGroups = computed(() => {
  const g = {}
  for (const d of store.allDevices) {
    const k = d.unitName || d.unitType || t('其他')
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
    kind: 'signal', nodeID: '', characteristicUUID: '',
  })
}
function copyModelPreview() { navigator.clipboard?.writeText(modelPreview.value) }
async function modelDryRun() {
  modelFormErr.value = ''
  if (!modelForm.modelName.trim()) { modelFormErr.value = t('请输入模型名'); return }
  try {
    const r = await api.boxUpdateModel({ ...modelForm, mode: 'dryRun' })
    modelPreview.value = r.yamls?.model || ''
  } catch (e) { modelFormErr.value = e.message || e }
}
async function saveModel() {
  if (!modelForm.modelName.trim()) { modelFormErr.value = t('请输入模型名'); return }
  if (!(modelForm.properties || []).length) { modelFormErr.value = t('请至少添加一个属性点位'); return }
  modelFormErr.value = ''
  try {
    const r = await api.boxUpdateModel({ ...modelForm, mode: 'apply' })
    store.showToast(`${t('模型已保存')}：${modelForm.modelName}（${t('可在「设备接入」中选择')}）`, 'success')
    await loadDevices()
    modelCreateOpen.value = false
  } catch (e) { modelFormErr.value = e.message || e }
}
// 一键下发模型：保存到本地 box_devices.json 后立即下发云端 K3s（无需单独「保存」）
async function applyModelForm() {
  if (!modelForm.modelName.trim()) { modelFormErr.value = t('请输入模型名'); return }
  if (!(modelForm.properties || []).length) { modelFormErr.value = t('请至少添加一个属性点位'); return }
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
  // 在线 = 有实时数据推送（后端 data_online），注册在线(CRD state)不计；离线项 state 归一便于文案展示
  const norm = (c) => ({ ...c, state: c.data_online ? 'online' : 'offline' })
  const on = list.filter((c) => c.data_online).map(norm)
  const off = list.filter((c) => !c.data_online).map(norm)
  const groups = []
  if (on.length) groups.push({ label: t('在线'), items: on })
  if (off.length) groups.push({ label: t('离线'), items: off })
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
  return s < 90 ? `${s}s ${t('前')}` : `${Math.floor(s / 60)}m ${t('前')}`
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
      const msg = ((r.stdout && r.stdout.trim()) || r.info || t('成功'))
      store.showToast(t('已触发重启「') + label + t('」') + '：' + msg + (r.info ? ' ' + r.info : ''), 'success')
      await refreshFast()
      loadAgentStatus()
      setTimeout(() => { loadAgentStatus() }, 8000)  // 重启完成后二次刷新
    } else {
      store.showToast(t('重启「') + label + t('」失败') + '：' + ((r && (r.stderr || r.error)) || t('未知错误')), 'error')
    }
  } catch (e) {
    store.showToast(t('重启请求失败') + '：' + (e.message || e), 'error')
  } finally {
    restartingKey.value = ''
  }
}
function restartCloudcore() {
  return restartCloud(
    { kind: 'deployment', name: 'cloudcore', namespace: 'kubeedge' },
    'CloudCore',
    t('确认重启云端 kubeedge 命名空间下的 cloudcore 工作负载？') + '\n' +
    t('将触发边缘节点重新注册（约 1-2 分钟恢复在线），请确认当前无正在进行的下发操作。')
  )
}
function restartAgent() {
  return restartCloud(
    { kind: 'systemd', name: 'cloud-agent' },
    'cloud-agent',
    t('确认重启云端 cloud-agent 服务？') + '\n' +
    t('系统会在 2 秒后自动拉起（先返回结果再重启自身），期间平台约数秒无法连接云端 agent。')
  )
}
function restartBroker() {
  return restartCloud(
    { kind: 'systemd', name: 'nengtan-cloud-broker' },
    'MQTT Broker',
    t('确认重启云端 MQTT Broker（nengtan-cloud-broker）？') + '\n' +
    t('将短暂断开边缘盒子与平台的 MQTT 长连接，约数秒后自动重连，请确认当前无正在进行的下发/上报操作。')
  )
}
function restartMapper(b) {
  if (!edgeIpOk(b)) {
    store.showToast(t('未配置盒子 IP 或探测不通，无法重启 Mapper。请先点击「配置」填写现场可达地址（内网 IP / 跳板机 / frp）并保存。'), 'warn')
    return
  }
  return restartCloud(
    { kind: 'edge', name: 'box-mapper' },
    'box-mapper（' + boxName(b) + '）',
    t('确认重启边端盒子「') + boxName(b) + t('」的 box-mapper 服务？') + '\n' +
    t('云端 agent 将经 SSH 到边缘盒子执行 systemctl restart box-mapper（需已在盒子卡片「配置」中填写现场可达地址且探测通过）。') + '\n' +
    t('注意：盒子处于现场内网/无直达 IP 时云端 SSH 无法直达，该操作会失败，需现场运维重启。')
  )
}

// ---- 盒子连接配置（IP/SSH 凭据）：重启 Mapper 前置条件，IP 为空或不通则拒绝 ----
const edgeCfgOpen = ref(false)
const edgeCfgBox = ref('')
const edgeCfgSaving = ref(false)
const edgeCfgChecking = ref(false)
const edgeCfgCheckResult = ref(null)
const edgeCfg = reactive({ host: '', port: 22, user: 'root', password: '', key: '', name: '' })
// 盒子显示名称别名（原名=云端 K8s 节点名不可改；后端 box_aliases 映射 节点名->显示名）
const boxAliases = ref({})
function boxName(b) {
  return (b && (boxAliases.value[b.name] || b.name)) || ''
}
async function loadEdgeCfgSilent() {
  // 页面加载时静默拉取已保存的盒子 IP 配置与名称别名，用于「重启 Mapper」按钮的可用性判断
  try {
    const r = await api.boxEdgeConfig()
    if (r) {
      if (r.edge) {
        edgeCfg.host = r.edge.host || ''
        edgeCfg.port = r.edge.port || 22
        edgeCfg.user = r.edge.user || 'root'
        edgeCfg.password = r.edge.password || ''
        edgeCfg.key = r.edge.key || ''
      }
      if (r.aliases) boxAliases.value = r.aliases
      if (edgeCfg.host) checkEdgeCfg(true)
    }
  } catch (e) {}
}
async function openBoxEdgeCfg(b) {
  edgeCfgBox.value = b.name
  edgeCfgCheckResult.value = null
  try {
    const r = await api.boxEdgeConfig()
    if (r) {
      if (r.edge) {
        edgeCfg.host = r.edge.host || ''
        edgeCfg.port = r.edge.port || 22
        edgeCfg.user = r.edge.user || 'root'
        edgeCfg.password = r.edge.password || ''
        edgeCfg.key = r.edge.key || ''
      }
      if (r.aliases) boxAliases.value = r.aliases
    }
  } catch (e) {}
  edgeCfg.name = boxAliases.value[b.name] || ''
  edgeCfgOpen.value = true
  if (edgeCfg.host) checkEdgeCfg(true)
}
async function saveEdgeCfg() {
  edgeCfgSaving.value = true
  try {
    const r = await api.boxEdgeConfigSave({
      box: edgeCfgBox.value,
      name: (edgeCfg.name || '').trim(),
      host: (edgeCfg.host || '').trim(),
      port: Number(edgeCfg.port) || 22,
      user: (edgeCfg.user || '').trim(),
      password: edgeCfg.password || '',
      key: (edgeCfg.key || '').trim(),
    })
    if (r && r.ok !== false) {
      if (r.aliases) boxAliases.value = r.aliases
      edgeCfgCheckResult.value = (r.check && r.check.reachable != null) ? { reachable: !!r.check.reachable } : null
      store.showToast(edgeCfgCheckResult.value && edgeCfgCheckResult.value.reachable
        ? t('盒子 IP 已保存且探测可达')
        : t('盒子 IP 已保存（当前探测不可达，重启 Mapper 将被拒绝）'), edgeCfgCheckResult.value && edgeCfgCheckResult.value.reachable ? 'success' : 'warn')
      edgeCfgOpen.value = false
      loadOverview()
    } else {
      store.showToast(t('保存失败') + '：' + ((r && r.error) || t('未知错误')), 'error')
    }
  } catch (e) {
    store.showToast(t('保存失败') + '：' + (e.message || e), 'error')
  } finally { edgeCfgSaving.value = false }
}
async function checkEdgeCfg(silent = false) {
  edgeCfgChecking.value = true
  try {
    const r = await api.boxEdgeCheck((edgeCfg.host || '').trim(), Number(edgeCfg.port) || 22)
    edgeCfgCheckResult.value = { reachable: !!(r && r.reachable) }
    if (!silent) {
      store.showToast(edgeCfgCheckResult.value.reachable ? t('✓ 盒子可达') : t('✗ 盒子不可达') + '：' + ((r && r.error) || ''), edgeCfgCheckResult.value.reachable ? 'success' : 'warn')
    }
  } catch (e) {
    edgeCfgCheckResult.value = { reachable: false }
    if (!silent) store.showToast(t('探测失败') + '：' + (e.message || e), 'error')
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
  if (!name) { store.showToast(t('请填写应用名称'), 'warn'); return }
  if (!(appDeployForm.url || '').trim()) { store.showToast(t('请填写下载地址'), 'warn'); return }
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
      store.showToast(t('部署指令已下发（盒子执行后回报，卡片将显示运行服务）'), 'success')
      appDeployOpen.value = false
      setTimeout(() => { loadOverview() }, 3000)
    } else {
      store.showToast(t('下发失败') + '：' + ((r && r.error) || t('未知错误')), 'error')
    }
  } catch (e) {
    store.showToast(t('下发失败') + '：' + (e.message || e), 'error')
  } finally { appDeploySaving.value = false }
}
async function applyDevices(name = '', dryRun = false, modelName = '') {
  applying.value = true
  try {
    const r = await api.boxApplyDevices(name, dryRun, modelName)
    if (!r.ok) throw new Error((r.error || '') + (r.stderr ? ' ' + r.stderr : ''))
    const list = (r.applied || []).join('、')
    if (dryRun) store.showToast(t('预览：') + `${list}` + t('（未下发）'), 'warn')
    else store.showToast(t('下发成功') + '：' + list, 'success')
    return r
  } catch (e) {
    store.showToast(t('下发失败') + '：' + (e.message || e), 'error')
    throw e
  } finally { applying.value = false }
}
// 拓扑图设备行「⤓ 下发」：单个设备下发，失败仅 toast 提示
async function onApplyOneDev(d) {
  if (applying.value) return
  if (!confirm(t('确认将设备「') + `${d.name}` + t('」下发到云端 K3s？'))) return
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
  } catch (e) { store.showToast(t('加载配置失败') + '：' + (e.message || e), 'error') }
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
      store.showToast(t('Broker + Agent 配置已保存并热更新'), 'success')
      boxCfgOpen.value = false
      store.mqttSource = await api.realtimeSource()   // 立即刷新链路状态（含重连结果）
      await loadOverview()
    } else {
      const err = (r.status === 'fulfilled' && r.value && r.value.error) || (r.status === 'rejected' && r.reason && r.reason.message) || ''
      store.showToast(t('保存失败') + '：' + (err || t('请检查配置')), 'error')
    }
  } catch (e) { store.showToast(t('保存失败') + '：' + (e.message || e), 'error') }
  finally { boxCfgSaving.value = false }
}

function addProp() {
  form.properties.push({
    name: 'prop' + (form.properties.length + 1), type: 'float', accessMode: 'r',
    registerType: 'holdingRegister', register: 0, scale: 1, unit: '',
    kind: 'signal', nodeID: '', characteristicUUID: '',
  })
}
async function dryRun() {
  formErr.value = ''
  try {
    // 模型留空 = 自动创建与设备同名的模型（一键化：无需先建模型）
    const base = { ...form, modelName: form.modelName || form.deviceName }
    const r = await api.boxCreateDevice(devPayload(base, 'dryRun'))
    preview.value = r.yamls.model + '\n---\n' + r.yamls.device
  } catch (e) { formErr.value = e.message || e }
}
async function applyDev() {
  formErr.value = ''
  try {
    // 模型留空 = 自动创建与设备同名的模型（一键化：无需先建模型）
    const base = { ...form, modelName: form.modelName || form.deviceName }
    const r = await api.boxCreateDevice(devPayload(base, 'apply'))
    preview.value = r.yamls.model + '\n---\n' + r.yamls.device
    // 绑定流程设备：云端身份（cloudDevice || deviceName）<-> 所选流程设备（含读数换算系数）
    await syncBound(form.cloudDevice || form.deviceName, form.boundDevice, form.boundFactor != null ? form.boundFactor : 1)
    const cs = r.cloud_sync || {}
    // 保存即自动同步云端（后端已下发）
    store.showToast(`${t('设备')} ${form.deviceName} ${t('已保存')}` + (cs.ok ? t('，已同步云端') : `，${t('云端同步失败')}：${cs.error || t('未知错误')}（${t('本地已保存')}）`) + (form.boundDevice ? `，${t('已绑定流程设备')} ${form.boundDevice}${form.boundFactor !== 1 ? `（${t('读数')}×${form.boundFactor}）` : ''}` : ''), cs.ok ? 'success' : 'warn')
    await loadDevices()
  } catch (e) { formErr.value = e.message || e }
}
// 删除采集设备：三端同步清除 —— 平台本地配置 + 云端 CRD + 盒子取数配置。
// 设备没有「禁用/停用」这一档：不想采集就删除，绝不留一条 enabled=false 的停采条目
// （那样在平台上表现为「有这台设备却没有数据」，既误导又不自愈）。
async function delDevice(d) {
  const name = d.name
  if (!(await store.confirm({
    title: t('删除设备'),
    message: t('确认删除设备「') + `${name}` + t('」？三端配置（平台本地 / 云端 CRD / 盒子取数）将一并清除。'),
    okText: t('删除'), danger: true
  }))) return
  try {
    const r = await api.boxDeleteDevice('device', name, d.namespace || 'default', true, true)
    await syncBound((d.cloudDevice || name), null)   // 解除流程设备绑定，避免留悬空绑定
    const bs = (r.box_sync || {})[d.node || ''] || {}
    const cs = r.cloud || {}
    const ok = r.ok !== false && cs.ok !== false
    let msg = t('设备') + ` ${name} ` + t('已删除')
    if (!ok) msg += '：' + (cs.error || bs.error || bs.note || t('云端不可达'))
    store.showToast(msg, ok ? 'success' : 'warn')
    await loadDevices()
    await loadCloudCrd(true)
  } catch (e) { store.showToast(t('删除失败') + '：' + (e.message || e), 'error') }
}
async function copyPreview() { try { await navigator.clipboard.writeText(preview.value); store.showToast(t('YAML 已复制'), 'success') } catch (e) {} }

// ---- Tab4 盒子一键接入（自解压脚本：box-deploy 包 + edgecore.yaml + rootCA + token）----
const onboardForm = reactive({ hostname: 'edge-box', cloudIP: '36.151.146.71', boxIP: '' })
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
    store.showToast(r.ok ? t('GitHub 配置已保存') : (r.error || t('保存失败')), r.ok ? 'success' : 'error')
  } catch (e) { store.showToast(t('保存失败') + '：' + (e.message || e), 'error') }
  finally { ghBusy.value = false }
}
async function syncGithub() {
  ghBusy.value = true
  ghResult.value = null
  try {
    const r = await api.boxGithubPush(onboardForm.cloudIP)
    ghResult.value = r
    store.showToast(r.ok ? t('已同步到 GitHub：盒子现场可一条命令接入') : (t('同步失败') + '：' + (r.error || t('见文件状态'))), r.ok ? 'success' : 'error')
  } catch (e) { store.showToast(t('同步失败') + '：' + (e.message || e), 'error') }
  finally { ghBusy.value = false }
}
async function exportBoxConfig() {
  ghExportBusy.value = true
  ghExport.value = null
  try {
    const r = await api.boxConfigExport(onboardForm.cloudIP, onboardForm.hostname)
    ghExport.value = r
    store.showToast(r.ok ? t('已生成 box-config.json：复制内容保存到盒子 /opt/weight-bridge/box-config.json 即可') : (r.error || t('导出失败')), r.ok ? 'success' : 'error')
  } catch (e) { store.showToast(t('导出失败') + '：' + (e.message || e), 'error') }
  finally { ghExportBusy.value = false }
}
async function doOnboard() {
  onboardBusy.value = true
  try {
    const r = await api.boxOnboard(onboardForm.hostname, onboardForm.cloudIP, onboardForm.boxIP)
    if (!r.ok) { store.showToast(r.error || t('生成失败'), 'error'); return }
    onboardResult.value = r
    remoteSteps.value = []
  } catch (e) { store.showToast(t('生成失败') + '：' + (e.message || e), 'error') }
  finally { onboardBusy.value = false }
}
async function downloadOnboardScript() {
  try {
    const r = await api.boxOnboardScript()
    if (!r.ok) { store.showToast(r.error || t('脚本未生成'), 'error'); return }
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
    store.showToast(`${t('已下载')} ${r.script_name}（${(r.script_size / 1024 / 1024).toFixed(1)} MB）`, 'success')
  } catch (e) { store.showToast(t('下载失败') + '：' + (e.message || e), 'error') }
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
    store.showToast(r.ok ? t('远程一键接入完成：盒子已接入云端') : (t('远程一键接入失败') + '：' + (r.error || t('见步骤日志'))), r.ok ? 'success' : 'error')
  } catch (e) { store.showToast(t('远程一键接入失败') + '：' + (e.message || e), 'error') }
  finally { remoteRunning.value = false }
}
async function copyOnboard() { try { await navigator.clipboard.writeText(onboardResult.value.edgecore); store.showToast(t('edgecore.yaml 已复制'), 'success') } catch (e) {} }

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
const msgLogRef = ref(null)
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
  if (!pubForm.topic.trim()) { store.showToast(t('请先填写主题（建议 data/box-xxx/device-xxx 格式，发布后可在「实时消息流」看到回显，data/# 会同时刷新设备实时数据）'), 'warn'); return }
  try {
    const r = await api.boxPublish(pubForm.topic, pubForm.payload)
    store.showToast(r.ok
      ? (pubForm.topic.trim().startsWith('data/')
          ? t('已发布到 {topic} → 见「实时消息流」，实时数据已刷新', { topic: r.topic })
          : t('已发布到 {topic} → 见「实时消息流」', { topic: r.topic }))
      : t('发布失败') + '：' + (r.error || ''), r.ok ? 'success' : 'error')
    await loadMessages()
    nextTick(scrollMsgLog)
  } catch (e) { store.showToast(t('发布失败') + '：' + (e.message || e), 'error') }
}

async function refreshAll(force = false) {
  // force=true 才会同步 HTTP 拉云端 agent（开发机 agent 不可达时该请求要等满 5s 超时）；
  // 首屏一律走 MQTT 推送缓存，用户主动点「刷新」才强制实时拉取。
  await Promise.allSettled([loadOverview(), loadDevices(), loadRealtime(), loadMessages(), loadCloudCrd(force)])
}

// ---- ② 资源列表：手动刷新（盒子 / 模型 / 设备三列）----
// 与顶部「刷新全部」区分：只拉列表本体依赖的三份数据（总览 nodes / 本地设备定义 / 云端 CRD），
// 且 loadCloudCrd(true) 强制同步拉云端 agent —— 刚下发或刚上线的设备不需等 30s 慢轮询、MQTT 推送即刻可见。
const resRefreshing = ref(false)
async function refreshResources() {
  if (resRefreshing.value) return   // 刷新中重复点击直接忽略
  resRefreshing.value = true
  try {
    await Promise.allSettled([loadOverview(), loadDevices(), loadCloudCrd(true)])
    const summary = `${topoBoxes.value.length} ${t('盒')} · ${mergedModels.value.length} ${t('模型')} · ${mergedDevices.value.length} ${t('设备')}`
    // 云端不可达时仍用本地数据渲染成功，但降级为 warn 提示（cloudCrd.error 来自 agent 请求失败）
    store.showToast(`${t('资源列表已刷新')}：${summary}`, cloudCrd.value.error ? 'warn' : 'success')
  } catch (e) {
    store.showToast(t('刷新失败') + '：' + (e.message || e), 'error')
  } finally {
    resRefreshing.value = false
  }
}
// ---- 配置变更实时同步（服务端单一配置 → 多客户端一致显示）----
// 采集设备配置只存服务端 backend/config/box_devices.json 一份，客户端不做本地副本。
// 任一客户端改动（新建/修改设备、更新模型、下发）后后端写盘并广播 config 事件，
// 这里收到即重新拉取：其它客户端无需手动刷新（顶部刷新按钮退化为兜底手段）。
let cfgWs = null
let cfgRev = 0          // 已知的配置版本号（文件 mtime_ns），用于过滤重复事件
let cfgSyncTimer = null // 合并短时间内的连续变更（如批量下发）为一次刷新
const cfgPending = ref(false)   // 变更到达时正在编辑 → 挂起，关掉弹窗后再同步
// 正在编辑配置时不能就地刷新列表：会让弹窗里的模型/设备下拉与点位被替换，打断输入
function cfgEditing() { return createOpen.value || editOpen.value || modelCreateOpen.value }
function syncDevicesFromServer() {
  if (cfgEditing()) { cfgPending.value = true; return }
  clearTimeout(cfgSyncTimer)
  cfgSyncTimer = setTimeout(() => {
    cfgPending.value = false
    loadDevices()
    loadOverview()
  }, 300)
}
function onConfigMsg(msg) {
  if (!msg || msg.scope !== 'devices') return
  if (msg.kind === 'snapshot' || !msg.rev) { cfgRev = msg.rev || cfgRev; return }
  if (msg.rev === cfgRev) return   // 已处理过的版本（本客户端自己改动也会收到）
  cfgRev = msg.rev
  syncDevicesFromServer()
}
// 注：弹窗关闭后补做挂起同步的 watch 不能注册在这里 —— editOpen 在下方「修改设备配置」段
// 才声明（约 3378 行），在它之前求值会 TDZ「Cannot access 'editOpen' before initialization」，
// 整个 <script setup> 初始化失败即页面白屏；该 watch 注册在 editOpen 声明之后。

// 快速轮询（3s）：合并界面无页签切换，统一拉轻量数据；云端 CRD 由 30s 慢轮询承担
// 快轮询只带「实时读数 + 链路状态」；设备定义列表（loadDevices，响应较大）移入慢轮询，
// 折叠中的区块（消息流 / 云端日志）不再轮询其数据，展开时立即补拉一次
async function refreshFast() {
  const jobs = [loadOverview(), loadRealtime()]
  if (secFold.value.msglog) jobs.push(loadMessages())
  await Promise.allSettled(jobs)
}
// 慢轮询（30s，与后端 CRD 缓存对齐）：云端 CRD + 拓扑盒子状态 + Agent 状态 + 设备定义列表
async function refreshSlow() {
  await loadCloudCrd()
  loadOverview()
  loadAgentStatus()
  loadDevices()
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
// 设备在线判定（全局统一）：有实时数据推送才算在线。
// 云端设备：后端 cloud_crds 按 twins/MQTT 数据新鲜度计算 data_online → online/offline；
// 本地待下发设备：若平台 MQTT 正在上报其读数（/box/devices 的 data_online）也算在线，否则保持「待下发」。
function onlineState(d) {
  if (d._cloud) return d.data_online ? 'online' : 'offline'
  return d.data_online ? 'online' : null
}
const mergedDevices = computed(() => {
  const map = new Map()
  ;(cloudCrd.value.devices || []).forEach((d) => map.set(d.name, { ...d, _cloud: true, state: d.data_online ? 'online' : 'offline' }))
  ;(devices.value.devices || []).forEach((d) => {
    const c = map.get(d.name)
    const merged = { ...d, _cloud: !!c }
    merged.state = c ? c.state : onlineState(merged)
    map.set(d.name, merged)
  })
  return [...map.values()]
})
// 盒子下设备合并（云端真实 + 本地待下发，同名合并，云端优先带状态）
function boxDevices(b) {
  const map = new Map()
  ;(b.cloudDevices || []).forEach((d) => map.set(d.name, { ...d, _cloud: true }))
  ;(b.devices || []).forEach((d) => {
    if (!map.has(d.name)) map.set(d.name, { ...d, _cloud: false, state: d.data_online ? 'online' : null })
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
  if (d.state === 'online') return t('在线')
  if (d.state === 'offline') return t('离线')
  return t('待下发')
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
  if (isInvalidReading(v)) return t('无有效数据')
  if (v == null) return '—'
  return typeof v === 'number' ? (Math.abs(v) >= 100 ? v.toFixed(1) : v.toFixed(2)) : String(v)
}
function fmtAgo(epoch) {
  if (!epoch) return ''
  const s = Math.floor(Date.now() / 1000 - epoch)
  if (s < 60) return `${s}s ${t('前')}`
  if (s < 3600) return `${Math.floor(s / 60)}m ${t('前')}`
  return `${Math.floor(s / 3600)}h ${t('前')}`
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
  return d ? `${d}${t('天')}${h}${t('小时')}` : (h ? `${h}${t('小时')}${m}${t('分')}` : `${m}${t('分')}`)
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
    // 在线 = 有实时数据推送（后端 cloud_crds 已算 data_online，窗口 120s）；注册态(CRD state)不再冒充在线
    state: d.data_online ? 'online' : 'offline',
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
// 平台服务器地址：当前控制台访问地址（平台自身作为连接图中的一台设备）
const platformHost = (typeof window !== 'undefined' && window.location && window.location.host) || ''
// ---- 系统连接图：逐服务的实际连接地址（现场核对链路时按图索骥）----
// 'http://1.2.3.4:42084/xxx' → '1.2.3.4:42084'（去掉协议/路径，保留 host:port）
function urlHostPort(u) {
  const s = String(u || '').trim()
  if (!s) return ''
  const noProto = s.replace(/^[a-zA-Z][a-zA-Z0-9+.-]*:\/\//, '')
  return noProto.replace(/[/?#].*$/, '').replace(/^[^@]*@/, '')
}
// 服务地址跳转：拼出可在浏览器打开的 URL（沿用当前页面的协议）。
// 只有 HTTP 类服务可跳（Web 控制台 / API / 中间件 / 部署应用）；MQTT、串口类地址浏览器打不开，只展示。
function httpOpenUrl(addr, path) {
  const a = String(addr || '').trim()
  if (!a) return ''
  const p = String(path || '/')
  if (/^https?:\/\//i.test(a)) return a.replace(/\/+$/, '') + p
  const proto = (typeof location !== 'undefined' && location.protocol === 'https:') ? 'https://' : 'http://'
  return proto + a.replace(/\/+$/, '') + p
}
// 云端 Broker：概览返回订阅线程实际生效地址（权威），其次数据源状态，最后本地 Broker 配置
const brokerHost = computed(() => (overview.value.broker && overview.value.broker.host)
  || boxSt.value.broker_host || boxCfg.host || '')
const brokerPort = computed(() => (overview.value.broker && overview.value.broker.port)
  || boxSt.value.broker_port || boxCfg.port || 41883)
const brokerAddr = computed(() => (brokerHost.value ? `${brokerHost.value}:${brokerPort.value}` : ''))
// 云端主机：优先 agent 实际命中的候选地址（本地/生产可能不同），回退配置地址 → Broker 地址
const cloudHost = computed(() => (agentStatus.value && agentStatus.value.active_host)
  || (agentStatus.value && agentStatus.value.config && agentStatus.value.config.host)
  || cloudCfg.host || brokerHost.value || '')
const agentAddr = computed(() => (cloudHost.value ? `${cloudHost.value}:${cloudCfg.agent_port || 42083}` : ''))
// 云边管理通道 CloudHub（CloudCore 监听，盒子 EdgeCore 上行连它）
const cloudHubAddr = computed(() => (cloudHost.value ? `${cloudHost.value}:10002` : ''))
// 数据中间件：实际生效地址优先（候选回退结果），回退配置地址
const mwAddr = computed(() => urlHostPort(middleware.value.active_base_url || middleware.value.base_url))
// 盒子现场可达 IP（SSH/运维地址）：全局只有一份配置，多盒子时不冒领，避免标错
function boxIpOf(b) {
  if (topoBoxes.value.length !== 1) return ''
  return (edgeCfg.host || '').trim()
}
// 采集设备的接入地址（现场核对用）：Modbus 串口/TCP、OPC UA 端点、LoRa 终端 EUI+从站号、蜂窝串口
// 云端设备（CRD）本身不带协议参数，按 name / cloudDevice 反查本地配置（与 slaveLabelOf 同口径）
function devAddrOf(dev) {
  const local = (devices.value.devices || []).find((x) => x.name === dev.name || x.cloudDevice === dev.name)
  const src = local || dev
  const proto = protoOfDev(dev) || src.protocol || ''
  // 从站号是现场区分同一总线下多台设备的关键，统一附在地址后（0 表示未配置/被动上报）
  const slave = slaveLabelOf(src) || slaveLabelOf(dev)
  const sl = (slave && slave !== '0') ? t('站') + slave : ''
  if (proto === 'lora') {
    const eui = String((src.lora || {}).devEUI || '').trim()
    const short = eui ? (eui.length > 8 ? '…' + eui.slice(-6) : eui) : ''
    return [sl, short].filter(Boolean).join(' · ')
  }
  if (proto === 'opcua') return String((src.opcua || {}).url || '').trim()
  if (proto === 'modbus') {
    const c = src.comm || {}
    const link = c.commType === 'tcp'
      ? [c.tcpIP, c.tcpPort].filter((v) => v !== '' && v != null).join(':')
      : String(c.serialPort || '').trim()
    return [link, sl].filter(Boolean).join(' · ')
  }
  if (proto === 'cellular') return String((src.cellular || {}).serialPort || '').trim()
  return ''
}
// 外部数据源的接入地址：MQTT 源取 Broker 地址:端口（params 既有扁平键也有嵌套结构）
function extAddrOf(s) {
  const cfg = s && s.config ? s.config : {}
  const params = cfg.params || cfg
  const host = fieldRaw(params, 'broker.host') || (cfg.broker && cfg.broker.host) || ''
  const port = fieldRaw(params, 'broker.port') || (cfg.broker && cfg.broker.port) || ''
  return [host, port].filter((v) => v !== '' && v != null).join(':')
}
// 所有设备实际采集协议集合（去重）
const allDevProtos = computed(() => {
  const set = new Set()
  for (const d of topoAllCloudDevs.value) { const p = protoOfDev(d); if (p) set.add(p) }
  for (const d of topoAllLocalDevs.value) { if (d.protocol) set.add(d.protocol) }
  for (const d of topoUnmounted.value) { if (d.protocol) set.add(d.protocol) }
  return [...set]
})
// 从站号展示：LoRa 透传 DTU 下挂多台 485 传感器时靠从站号区分（与 Modbus 同理）；
// 云端设备没有 lora/comm 字段，需按 name / cloudDevice 反查本地配置
function slaveLabelOf(dev) {
  const local = (devices.value.devices || []).find((x) => x.name === dev.name || x.cloudDevice === dev.name)
  const src = local || dev
  const proto = protoOfDev(dev) || ''
  if (proto === 'lora') {
    const v = (src.lora || {}).slaveId
    return v != null && v !== '' ? String(v) : ''
  }
  if (proto === 'modbus') {
    const v = (src.comm || {}).slaveID
    return v != null && v !== '' ? String(v) : ''
  }
  return ''
}
function devCountOf(nodeName) {
  return (devices.value.devices || []).filter((d) => d.node === nodeName && !isDeployed(d)).length
}
// 协议反查：云端真实设备（无 protocol 字段）通过本地配置按 name / cloudDevice 匹配回真实采集协议
function protoOfDev(dev) {
  if (dev.protocol) return dev.protocol
  const local = (devices.value.devices || []).find((x) => x.name === dev.name || x.cloudDevice === dev.name)
  if (local && local.protocol) return local.protocol
  // 兜底：本地没有该设备定义时（如开发机只看到云端 CRD），按设备引用的模型反查采集协议，
  // 避免协议识别为空被误判成「不支持设备命令」。
  const mname = String(dev.model || (local && local.model) || '')
  const m = (devices.value.models || []).find((x) => x.name === mname)
  return (m && m.protocol) || ''
}
// CloudCore Pod 状态统一中文：kubectl 返回的 .status.phase / containerState 原值 → 中文
const PHASE_ZH = {
  Running: '运行中', Pending: '待启动', Succeeded: '已完成', Failed: '失败', Unknown: '未知',
  ContainerCreating: '容器创建中', CrashLoopBackOff: '启动崩溃循环',
  ImagePullBackOff: '镜像拉取失败', ErrImagePull: '镜像拉取错误', Terminating: '终止中',
}
function phaseZh(s) {
  if (!s) return t('未知')
  return t(PHASE_ZH[s]) || s
}
// K8s 节点角色统一中文：control-plane/edge/master → 中文
const ROLE_ZH = { edge: '边端', 'control-plane': '控制面', master: '控制面', worker: '工作节点', '<none>': '普通节点' }
function roleZh(r) {
  if (!r || r === '—') return '—'
  return t(ROLE_ZH[String(r).toLowerCase()]) || r
}
// 状态统一中文：online→在线 / offline→离线 / 未知
function stateZh(s) {
  if (s === 'online') return t('在线')
  if (s === 'offline') return t('离线')
  if (s === 'Ready' || s === 'ready') return t('就绪')
  if (s === 'NotReady') return t('未就绪')
  if (s === 'unknown' || !s) return t('未知')
  return s
}
// 盒子三态中文：true=就绪 / false=未就绪 / null=状态未知（云端数据过期时后端置 null，避免旧缓存冒充实时）
function readyZh(r) {
  if (r === true) return t('就绪')
  if (r === false) return t('未就绪')
  return t('状态未知')
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
const nodeRefs = {}            // 固定设备卡（平台服务器 / 云端服务器 / 现场设备 / 外部数据系统）
const boxNodeRefs = ref({})    // 动态设备卡：能碳一体机（按盒子节点名）
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
const TOPO_POS_KEY = 'cbx-topo-pos-v2'   // v2：布局单元由「模块」改为「设备卡」，旧位置作废
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
  // 连接图按「设备」建模：连线只表示设备↔设备的通道，设备内部服务之间不画线
  // （设备内部通信已在卡片内以「本机内部：…」文字说明呈现）
  const defs = []
  const P = R(nodeRefs.d_platform)
  const C = R(nodeRefs.d_cloud)
  const DEVS = R(nodeRefs.d_devs)
  const EXT = R(nodeRefs.d_ext)
  // 平台服务器 ⇄ 云端服务器：上行读取（MQTT 订阅）与下行写操作（agent HTTP）
  if (P && C) {
    defs.push({ f: P, t: C, cls: 'red', mk: 'red', both: false,
                label: t('写 · HTTP :42083'), fyOff: -0.24, tyOff: -0.36 })
    defs.push({ f: C, t: P, cls: 'green', mk: 'green', both: false,
                label: t('读 · MQTT :41883'), fyOff: 0.36, tyOff: 0.24 })
  }
  const boxCount = topoBoxes.value.length
  topoBoxes.value.forEach((box, idx) => {
    const B = R(boxNodeRefs.value[box.name])
    if (!B) return
    const spread = boxCount > 1 ? (idx - (boxCount - 1) / 2) * 0.3 : 0
    // 能碳一体机 → 云端服务器：一体机把「传感器数据（data/#）」与「外部数据系统数据（ext/#）」
    // 统一 MQTT 上行到云端（外部数据不是外部系统直发云端，必须先经一体机转发）；另一条为云边管理通道
    if (C) {
      defs.push({ f: B, t: C, cls: 'green', mk: 'green', both: false,
                  label: t('MQTT 上行 :41883 · data/# · ext/#'), fyOff: -0.3 + spread, tyOff: -0.12 + spread })
      defs.push({ f: B, t: C, cls: 'blue', mk: 'blue', both: true,
                  label: t('云边管理 :10002'), fyOff: 0.3 + spread, tyOff: 0.36 + spread })
    }
    // 现场设备（传感器/仪表）→ 能碳一体机：边缘采集（RS485 / Modbus / 以太网）
    if (DEVS) {
      defs.push({ f: DEVS, t: B, cls: 'green', mk: 'green', both: false,
                  label: t('采集 · RS485/Modbus'), fyOff: -0.2 + spread, tyOff: -0.3 + spread })
    }
    // 外部数据系统 → 能碳一体机：外部数据先接入一体机（网线/工业总线），再由一体机上行云端，
    // 因此这一段只是本地接入，不含任何云端主题
    if (EXT) {
      defs.push({ f: EXT, t: B, cls: 'blue', mk: 'blue', both: false,
                  label: t('外部数据接入 · 以太网/OPC'), fyOff: 0.2 + spread, tyOff: 0.3 + spread })
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
    text.setAttribute('font-weight', '500')
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
// 三个弹窗 open ref 至此全部声明完毕，才能注册这个 watch：编辑期间到达的配置变更先挂起，
// 弹窗全关后再补刷（不能挪到配置同步块里 —— editOpen 在此处才声明，提前求值会 TDZ
// 「Cannot access 'editOpen' before initialization」，整个 setup 抛错即页面白屏）。
watch([createOpen, editOpen, modelCreateOpen], (v) => {
  if (v.some(Boolean) || !cfgPending.value) return
  cfgPending.value = false
  loadDevices()
  loadOverview()
})
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
  lora: { broker: '127.0.0.1', port: 41884, applicationID: '1', devEUI: '', appKey: '', region: 'CN470', dataRate: 'SF7BW125', slaveId: 0 },
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
  editForm.lora.port = lora.port != null ? lora.port : 41884
  editForm.lora.applicationID = lora.applicationID || '1'
  editForm.lora.devEUI = lora.devEUI || ''
  editForm.lora.appKey = lora.appKey || ''
  editForm.lora.region = lora.region || 'CN470'
  editForm.lora.dataRate = lora.dataRate || 'SF7BW125'
  editForm.lora.slaveId = lora.slaveId != null ? lora.slaveId : 0
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
    kind: 'signal', nodeID: '', characteristicUUID: '',
  })
}
async function dryRunEdit() {
  editErr.value = false; editMsg.value = ''
  try {
    if (editTarget.value === 'model') {
      const r = await api.boxUpdateModel({ ...editForm, mode: 'dryRun' })
      editPreview.value = r.yamls.model
      editPreviewMode.value = 'dryRun'
      editMsg.value = t('已生成模型 YAML 预览（未保存、未下发）')
    } else {
      const r = await api.boxCreateDevice(devPayload(editForm, 'dryRun'))
      editPreview.value = r.yamls.model + '\n---\n' + r.yamls.device
      editPreviewMode.value = 'dryRun'
      editMsg.value = t('已生成预览（未保存、未下发）')
    }
  } catch (e) { editErr.value = true; editMsg.value = e.message || e }
}
async function saveEditModel() {
  editSaving.value = true; editErr.value = false; editMsg.value = t('保存中…')
  try {
    const r = await api.boxUpdateModel({ ...editForm, mode: 'apply' })
    const n = (r.synced_devices || []).length
    const cs = r.cloud_sync || {}
    // 保存后后端已自动下发模型 + 引用设备到云端（云端及时同步）
    let tip = t('模型已更新：{name}', { name: editForm.modelName }) + (n ? t('，同步重刷 {n} 台设备', { n }) : '')
    tip += cs.ok ? t('，已同步云端') : t('，云端同步失败：{err}（本地已保存）', { err: cs.error || t('未知错误') })
    editMsg.value = tip
    store.showToast(t('模型配置已更新：{name}', { name: editForm.modelName }) + (cs.ok ? t('，已同步云端') : t('，云端同步失败')), cs.ok ? 'success' : 'warn')
    await loadDevices()
    editOpen.value = false
  } catch (e) { editErr.value = true; editMsg.value = e.message || e }
  finally { editSaving.value = false }
}
async function saveEditDev() {
  if (editTarget.value === 'model') return saveEditModel()
  const clash = renameClash(editForm)
  if (clash) {
    editErr.value = true
    editMsg.value = t('设备名「{name}」已被其它设备占用，改名会覆盖该设备（其云端设备也会被顶替）。请先删除或改名该设备。', { name: clash })
    return
  }
  editSaving.value = true; editErr.value = false; editMsg.value = t('保存中…')
  try {
    const r = await api.boxCreateDevice(devPayload(editForm, 'apply'))
    const n = (r.synced_devices || []).filter((x) => x !== editForm.deviceName).length
    const renamedFrom = r.renamed_from || ''
    const cs = r.cloud_sync || {}
    // 绑定流程设备：云端身份（cloudDevice || deviceName）<-> 所选流程设备（含读数换算系数）；未选择则解除原绑定
    await syncBound(editForm.cloudDevice || editForm.deviceName, editForm.boundDevice, editForm.boundFactor != null ? editForm.boundFactor : 1)
    // 保存即自动同步云端（后端已下发 + 改名联动删除云端旧 CRD）
    let tip = t('已保存：{name}', { name: editForm.deviceName }) + (n ? t('，模型点位同步 {n} 台设备', { n }) : '') + (editForm.boundDevice ? t('，已绑定流程设备 {dev}{factor}', { dev: editForm.boundDevice, factor: editForm.boundFactor !== 1 ? `（${t('读数')}×${editForm.boundFactor}）` : '' }) : '')
    if (renamedFrom) tip += t('（由「{name}」改名）', { name: renamedFrom })
    if (cs.old_crd_removed === false && cs.old_crd_reason) tip += t('；{reason}', { reason: cs.old_crd_reason })
    tip += cs.ok ? t('；已同步云端') : t('；云端同步失败：{err}（本地已保存）', { err: cs.error || t('未知错误') })
    editMsg.value = tip
    store.showToast(t('设备配置已保存：{name}', { name: editForm.deviceName }) + (cs.ok ? t('，已同步云端') : t('，云端同步失败（本地已保存）')), cs.ok ? 'success' : 'warn')
    await loadDevices()
    editOpen.value = false
  } catch (e) { editErr.value = true; editMsg.value = e.message || e }
  finally { editSaving.value = false }
}
async function applyEditDev() {
  if (editTarget.value === 'model') {
    // 保存模型并下发（后端已自动同步：模型 + 引用它的所有设备一起 apply）
    editSaving.value = true; editErr.value = false; editMsg.value = t('保存并下发中…')
    try {
      const r = await api.boxUpdateModel({ ...editForm, mode: 'apply' })
      editPreview.value = ''
      const n = (r.synced_devices || []).length
      const cs = r.cloud_sync || {}
      let tip = t('模型已保存并下发：{name}', { name: editForm.modelName }) + (n ? t('（同步 {n} 台设备）', { n }) : '')
      if (!cs.ok) tip += t('；云端同步失败：{err}（本地已保存）', { err: cs.error || t('未知错误') })
      editMsg.value = tip
      store.showToast(tip, cs.ok ? 'success' : 'warn')
      await loadDevices()
      editOpen.value = false
    } catch (e) { editErr.value = true; editMsg.value = e.message || e }
    finally { editSaving.value = false }
    return
  }
  const clash = renameClash(editForm)
  if (clash) {
    editErr.value = true
    editMsg.value = t('设备名「{name}」已被其它设备占用，改名会覆盖该设备（其云端设备也会被顶替）。请先删除或改名该设备。', { name: clash })
    return
  }
  editSaving.value = true; editErr.value = false; editMsg.value = t('保存并下发中…')
  try {
    const r = await api.boxCreateDevice(devPayload(editForm, 'apply'))
    editPreview.value = ''
    const renamedFrom = r.renamed_from || ''
    const cs = r.cloud_sync || {}
    // 绑定流程设备：云端身份（cloudDevice || deviceName）<-> 所选流程设备（含读数换算系数）；未选择则解除原绑定
    await syncBound(editForm.cloudDevice || editForm.deviceName, editForm.boundDevice, editForm.boundFactor != null ? editForm.boundFactor : 1)
    // 后端已自动完成：下发新设备 + 改名联动删除云端旧 CRD（云端及时同步）
    let tip = t('已保存并下发：{name}', { name: editForm.deviceName })
    if (editForm.boundDevice) tip += t('，已绑定流程设备 {dev}{factor}', { dev: editForm.boundDevice, factor: editForm.boundFactor !== 1 ? `（${t('读数')}×${editForm.boundFactor}）` : '' })
    if (renamedFrom) tip += t('（由「{name}」改名，云端旧设备{del}）', { name: renamedFrom, del: cs.old_crd_removed ? t('已删除') : t('未删除') })
    if (cs.old_crd_removed === false && cs.old_crd_reason) tip += t('；{reason}', { reason: cs.old_crd_reason })
    if (!cs.ok) tip += t('；云端同步失败：{err}（本地已保存）', { err: cs.error || t('未知错误') })
    editMsg.value = tip
    store.showToast(tip, cs.ok ? 'success' : 'warn')
    await loadDevices()
    if (renamedFrom && renamedFrom !== editForm.deviceName) await loadCloudCrd(true)
    editOpen.value = false
  } catch (e) { editErr.value = true; editMsg.value = e.message || e }
  finally { editSaving.value = false }
}
async function copyEditYaml() {
  try { await navigator.clipboard.writeText(editPreview.value); store.showToast(t('YAML 已复制'), 'success') } catch (e) {}
}

// ---- 单设备实时数据对话框（3s 轮询，折线图展示）----
const devRtOpen = ref(false)
const devRtName = ref('')
const devRt = computed(() => rtDevices.value.find((x) => x.name === devRtName.value) || null)
const rtSel = ref('')        // 当前选中的属性
const rtHover = ref(-1)      // 悬停采样点 index
const rtChartEl = ref(null)
let stopRtPoll = null
async function refreshDevRt() {
  try { rtDevices.value = (await api.boxDevicesRealtime()).devices || [] } catch (e) {}
}
function openDevRealtime(d) {
  devRtName.value = d.name
  devRtOpen.value = true
  rtSel.value = ''
  rtHover.value = -1
  refreshDevRt()
  if (stopRtPoll) stopRtPoll()
  stopRtPoll = visiblePoll(refreshDevRt, 3000)
}
function closeDevRealtime() {
  devRtOpen.value = false
  devRtName.value = ''
  rtHover.value = -1
  if (stopRtPoll) { stopRtPoll(); stopRtPoll = null }
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
  if (!rtTwins.value.length) return t('该设备暂无上报属性')
  const n = rtSeries.value.length
  if (n === 0) return t('该属性暂无趋势数据（设备上线后开始累积）')
  return t('趋势数据不足（需至少 2 个采样点）')
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

// ---- 通俗化「运行状态总览 + 使用指引」：面向非技术人员的健康摘要（不改变任何功能与下方区块） ----
// 使用指引：首次进入自动展开，点“知道了”后用 localStorage 记住，不再打扰
const guideSeen = ref(false)
try { guideSeen.value = localStorage.getItem('cbx-guide-seen') === '1' } catch (e) {}
const guideOpen = ref(!guideSeen.value)
function toggleGuide() { guideOpen.value = !guideOpen.value }
function closeGuide() {
  guideOpen.value = false
  guideSeen.value = true
  try { localStorage.setItem('cbx-guide-seen', '1') } catch (e) {}
}
// 指标卡点击 → 平滑滚动到对应列表（sources=数据源接入区块，box/dev=资源列表）
function scrollMsgLog() {
  const el = msgLogRef.value
  if (el) el.scrollTop = el.scrollHeight
}
function scrollToSec(which) {
  // 目标区块若处于折叠态先展开，否则滚过去只看到标题
  const foldKey = which === 'sources' ? 'sources' : 'reslist'
  if (!secFold.value[foldKey]) secFold.value = { ...secFold.value, [foldKey]: true }
  nextTick(() => {
    const el = document.getElementById(which === 'box' ? 'cbx-res-box'
      : which === 'sources' ? 'cbx-sec-sources' : 'cbx-res-dev')
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

// 云端连接（live/stale/degraded/unreachable → 通俗文案）
const heroCloud = computed(() => {
  const s = overview.value.cloud_source
  if (s === 'live') return { txt: t('云端在线'), cls: 'ok' }
  if (s === 'stale') return { txt: t('数据过期'), cls: 'warn' }
  if (s === 'degraded') return { txt: t('部分异常'), cls: 'warn' }
  if (s === 'unreachable') return { txt: t('连接中断'), cls: 'err' }
  return { txt: t('检测中'), cls: 'mute' }
})
// 盒子在线统计
const heroBox = computed(() => {
  const list = topoBoxes.value
  const ok = list.filter((b) => b.ready === true).length
  const bad = list.filter((b) => b.ready === false).length
  return { n: list.length, ok, bad, txt: list.length ? ok + ' / ' + list.length : '—', cls: !list.length ? 'mute' : (bad ? 'warn' : 'ok') }
})
// 设备上传统计（online = 有实时数据推送）
const heroDev = computed(() => {
  const list = mergedDevices.value
  const on = list.filter((d) => d.state === 'online').length
  const off = list.filter((d) => d.state === 'offline').length
  return { n: list.length, on, off, txt: list.length ? on + ' / ' + list.length : '—', cls: !list.length ? 'mute' : (on ? 'ok' : (off ? 'warn' : 'mute')) }
})
// 实时消息（近端缓存条数）
const heroMsg = computed(() => ({ n: messages.value.length, cls: messages.value.length ? 'ok' : 'mute' }))
// 总体结论（优先级：云中断 > 云端降级/过期 > 盒子未就绪 > 设备离线 > 空系统 > 正常）
const hero = computed(() => {
  const cs = overview.value.cloud_source
  const loaded = !!(cs || (overview.value.nodes || []).length || overview.value.broker)
  const b = heroBox.value, d = heroDev.value
  if (!loaded) return { tone: 'mute', icon: '·', title: t('正在获取运行状态…'), desc: t('正在加载云端与设备状态，请稍候…') }
  if (cs === 'unreachable') return { tone: 'err', icon: '✕', title: t('无法连接云端服务器'), desc: t('本页显示的云端状态与设备数据可能不是最新。请先确认云端服务器是否开机、网络是否正常，必要时联系系统维护人员。') }
  if (cs === 'degraded') return { tone: 'warn', icon: '⚠', title: t('云端部分服务异常'), desc: t('云端个别服务未完全就绪，部分数据可能不完整或为缓存，一般会随系统运行自动恢复；如持续异常请联系维护人员。') }
  if (cs === 'stale') return { tone: 'warn', icon: '⚠', title: t('云端数据推送中断'), desc: t('设备状态已较长时间未更新，可能是云端服务或网络异常，请稍候；持续异常请联系系统维护人员。') }
  if (b.n && b.bad) return { tone: 'warn', icon: '⚠', title: t('有盒子未就绪'), desc: t('有 {n} 台盒子未就绪（共 {m} 台）。可点击上方「盒子在线」卡片查看「盒子列表」。', { n: b.bad, m: b.n }) }
  if (d.n && d.on === 0 && d.off > 0) return { tone: 'warn', icon: '⚠', title: t('有设备离线未上报'), desc: t('有 {n} 台设备离线未上报（共 {m} 台）。可点击上方「设备上传中」卡片查看「设备列表」。', { n: d.off, m: d.n }) }
  if (!b.n && !d.n) return { tone: 'mute', icon: '·', title: t('尚未接入设备'), desc: t('本页将展示现场盒子和设备的运行状态。请点击「＋ 设备」添加第一台采集设备，或点击「盒子接入」部署边缘盒子。') }
  const parts = [t('云端在线')]
  if (b.n) parts.push(t('{x} 台盒子就绪', { x: b.ok + '/' + b.n }))
  if (d.n) parts.push(t('{x} 台设备正在上报数据', { x: d.on + '/' + d.n }))
  return { tone: 'ok', icon: '✓', title: t('一切正常，无需操作'), desc: parts.join(' · ') + t('（约每 3 秒自动刷新）') }
})

// 关闭视图
const close = () => store.toggleBoxManage()

// 暴露给视图工具栏（RibbonToolbar）：刷新数据 / 盒子接入 / 设备接入 / 新建模型 / 关闭
defineExpose({ refreshAll, close, openOnboard, openCreate, openModelCreate })

// ---- ④ 命令执行：向一体机下发设备读/写寄存器 / LoRaWAN 下行 ----
const cmdMode = ref('dev')
const cmdModes = [
  { k: 'dev', l: '设备命令' },
  { k: 'raw', l: '原始消息' },
]
// 目标字段：refMode=prop 走已配置点位/可写点；reg=任意寄存器（调试新传感器常用）
const cmdForm = reactive({
  box: '', device: '', op: 'read', refMode: 'prop', prop: '',
  addr: '', dtype: 'uint16', fc: '3', scale: '',
  wKind: 'holding', value: '',
  loraKind: 'hex', loraData: '', fPort: '2',
})
const cmdSending = ref(false)
const cmdPending = ref(null)   // { rid, box }
const cmdResult = ref(null)    // { ok: true|false|null(超时), message, detailText, ts }
const cmdLastSent = ref('')    // 最近一次下发的「主题 + 载荷」，失败时随结果一起给出便于核对
let cmdTimer = null
function stopCmdPoll() { if (cmdTimer) { clearTimeout(cmdTimer); cmdTimer = null } }
function fmtCmdDetail(d) {
  if (d == null) return ''
  if (typeof d === 'string') return d
  try { return JSON.stringify(d, null, 2) } catch (e) { return String(d) }
}
// 外部数据源前缀（ext-*）不是能碳一体机：它由一体机接入并上行云端，不能与一体机并列显示
function isExternalBox(name) {
  return String(name || '').trim().toLowerCase().startsWith('ext-')
}
const cmdBoxes = computed(() => {
  const set = new Set()
  for (const b of topoBoxes.value) if (b.name && !isExternalBox(b.name)) set.add(b.name)
  for (const d of devices.value.devices || []) if (d.node && !isExternalBox(d.node)) set.add(d.node)
  return [...set]
})
const cmdDevices = computed(() => {
  const box = cmdForm.box
  if (!box) return []
  const map = new Map()
  for (const d of devices.value.devices || []) {
    if (String(d.node || '') !== box) continue
    const srcs = new Set(map.has(d.name) ? map.get(d.name).src : [])
    srcs.add('本地')
    map.set(d.name, { name: d.name, src: [...srcs].join('/'), proto: d.protocol || '' })
  }
  const tb = topoBoxes.value.find((b) => b.name === box)
  for (const c of (tb && tb.cloudDevices) || []) {
    const srcs = new Set(map.has(c.name) ? map.get(c.name).src : [])
    srcs.add('云端')
    map.set(c.name, { name: c.name, src: [...srcs].join('/'), proto: protoOfDev(c) })
  }
  return [...map.values()]
})
const cmdDevMeta = computed(() => {
  const name = cmdForm.device
  if (!name) return null
  const local = (devices.value.devices || []).find((d) => d.name === name) || null
  const tb = topoBoxes.value.find((b) => b.name === cmdForm.box)
  const cloud = tb ? (tb.cloudDevices.find((c) => c.name === name) || null) : null
  const proto = String((local && local.protocol) || (cloud && protoOfDev(cloud)) || '').toLowerCase()
  const isLora = ['lora', 'lorawan'].includes(proto)
  const isModbus = ['modbus', 'modbus-rtu', 'rtu', 'modbus-tcp', 'tcp'].includes(proto)
  const props = (local && Array.isArray(local.properties) ? local.properties : []).filter((x) => x && x.name)
  // 可写点位 = 设备手工配置的 writes[] + 设备模型中标为可写（accessMode=rw）的属性
  // （模型可写属性在下发盒子时会自动派生为可写点位，见后端 to_mapper_device）
  const writes = writablePointsOf(local)
  // LoRa 设备的从站号在 lora.slaveId（同一 DTU 下多台 485 传感器靠它区分），Modbus 在 comm.slaveID
  const slave = isLora ? ((local && local.lora && local.lora.slaveId) || '') : ((local && local.comm && local.comm.slaveID) || '')
  return { name, local, cloud, proto, isLora, isModbus, props, writes, slave }
})
const cmdOpOptions = computed(() => {
  const m = cmdDevMeta.value
  if (m && m.isLora) return [{ k: 'read', l: '读（下行取数）' }, { k: 'write', l: '写设定（下行）' }]
  if (m && m.isModbus) return [{ k: 'read', l: '读寄存器' }, { k: 'write', l: '写设定' }]
  return [{ k: 'read', l: '读' }, { k: 'write', l: '写设定' }]
})
// 设备可写点位：手工配置的 writes[] + 设备模型中具备可写能力（accessMode=rw）的属性。
// 模型可写属性在下发给盒子时由后端自动派生为可写点位（含换算后的原始值范围）。
function writablePointsOf(dev) {
  const out = []
  const seen = new Set()
  const propOf = (n) => ((dev && Array.isArray(dev.properties) ? dev.properties : [])
    .find((x) => x && String(x.name) === String(n)) || null)
  for (const w of (dev && Array.isArray(dev.writes) ? dev.writes : [])) {
    if (!w || !w.property) continue
    seen.add(String(w.property))
    const p = propOf(w.property)
    // 补中文名/单位：手工 writes[] 通常只写 property 与地址，界面上光看英文属性名
    // 认不出是"电压"还是"校准系数"，统一回落到同名属性（模型）的 desc/unit
    out.push({ ...w, desc: w.desc || (p && p.desc) || '', unit: w.unit || (p && p.unit) || '' })
  }
  for (const p of (dev && Array.isArray(dev.properties) ? dev.properties : [])) {
    if (!p || !p.name || p.accessMode !== 'rw' || seen.has(String(p.name))) continue
    seen.add(String(p.name))
    const coil = String(p.registerType || '').toLowerCase().includes('coil')
    out.push({
      property: p.name,
      kind: coil ? 'coil' : 'holding',
      registerAddr: Number(p.register) || 0,
      coilAddr: Number(p.register) || 0,
      scale: 1,                        // 平台写入值即工程值，无需换算
      min: (p.min != null && p.min !== '') ? Number(p.min) : undefined,
      max: (p.max != null && p.max !== '') ? Number(p.max) : undefined,
      unit: p.unit || '',
      desc: p.desc || '',
      fromModel: true,
    })
  }
  return out
}
// 可写下拉的显示文本 / 悬浮说明：显示中文点位名 + 寄存器类型地址，
// 让用户能直接认出「设定输出电压（保持寄存器0）」而不是一串英文属性名
function writePointAddr(w) {
  const isCoil = String(w.kind || 'holding') === 'coil'
  return isCoil ? (w.coilAddr ?? w.registerAddr ?? 0) : (w.registerAddr ?? 0)
}
function writePointLabel(w) {
  const isCoil = String(w.kind || 'holding') === 'coil'
  const name = w.desc || w.property
  const unit = w.unit ? ' ' + w.unit : ''
  return `${name}（${isCoil ? t('线圈') : t('保持寄存器')}${writePointAddr(w)}${unit}）`
}
function writePointTitle(w) {
  const isCoil = String(w.kind || 'holding') === 'coil'
  const r = cmdWriteRange(w.property)
  const lines = [
    `${t('属性名')}：${w.property}`,
    `${isCoil ? t('线圈') : t('保持寄存器')} #${writePointAddr(w)}`,
  ]
  if (w.desc) lines.push(w.desc)
  if (w.unit) lines.push(`${t('单位')}：${w.unit}`)
  if (r) lines.push(`${t('允许范围')} ${fmtRange(r)}（${r.source}）`)
  return lines.join('\n')
}
// 某设备某属性的可写数值范围（统一折算为工程值口径，供命令面板与上报弹窗共用）：
// 可写点位优先（其 min/max 是寄存器原始值，按 scale 换算），其次设备/模型属性的
// 工程值范围。返回 null 表示未配置范围（无限制）。
function writeRangeOfDevice(deviceName, prop) {
  // 必须读本地设备记录（含 properties / writes / model）
  const dev = ((devices.value && devices.value.devices) || []).find((x) => x && x.name === deviceName)
  if (!dev || !prop) return null
  const w = (dev.writes || []).find((x) => String(x.property) === String(prop))
  if (w) {
    const sc = Number(w.scale) || 0
    const conv = (v) => (v == null || v === '' ? null : (sc ? Number(v) / sc : Number(v)))
    const lo = conv(w.min)
    const hi = conv(w.max)
    if (lo != null || hi != null) return { min: lo, max: hi, source: t('设备可写点位') }
  }
  const p = (dev.properties || []).find((x) => String(x.name) === String(prop))
  if (p) {
    const lo = (p.min != null && p.min !== '') ? Number(p.min) : null
    const hi = (p.max != null && p.max !== '') ? Number(p.max) : null
    if (lo != null || hi != null) return { min: lo, max: hi, source: t('设备模型属性') }
  }
  // 设备属性未配置范围时回退其引用模型的同名属性（与后端 write_guard.resolve_range
  // 同口径：可写点位 > 设备属性 > 模型属性）
  const mdl = ((devices.value && devices.value.models) || []).find((x) => x && x.name === dev.model)
  const mp = mdl && (mdl.properties || []).find((x) => String(x.name) === String(prop))
  if (mp) {
    const lo = (mp.min != null && mp.min !== '') ? Number(mp.min) : null
    const hi = (mp.max != null && mp.max !== '') ? Number(mp.max) : null
    if (lo != null || hi != null) return { min: lo, max: hi, source: t('设备模型属性') }
  }
  return null
}
function cmdWriteRange(prop) {
  const m = cmdDevMeta.value
  if (!m || !prop) return null
  return writeRangeOfDevice(m.name, prop)
}
function fmtRange(r) {
  if (!r) return ''
  const lo = r.min == null ? t('不限') : r.min
  const hi = r.max == null ? t('不限') : r.max
  return `${lo} ~ ${hi}`
}
// 裸写（任意寄存器/线圈）按地址解析配置中的安全范围（寄存器原始值口径）
function addrWriteRange(addr, kind) {
  const m = cmdDevMeta.value
  if (!m || addr === '' || addr == null) return null
  const a = Number(addr)
  const coil = String(kind || 'holding').toLowerCase() === 'coil'
  const w = (m.writes || []).find((x) => {
    if ((String(x.kind || 'holding').toLowerCase() === 'coil') !== coil) return false
    const wa = coil ? (x.coilAddr ?? x.registerAddr) : x.registerAddr
    return wa != null && Number(wa) === a
  })
  if (!w || (w.min == null && w.max == null)) return null
  return {
    min: w.min == null ? null : Number(w.min),
    max: w.max == null ? null : Number(w.max),
    source: w.fromModel ? t('模型可写属性') : t('设备可写点位'),
  }
}
// 裸写行的范围提示：只在设备配置里已配置该地址范围时显示，未配置则提示去设备配置中设置
function addrRangeHint() {
  const r = addrWriteRange(cmdForm.addr, cmdForm.wKind)
  if (!r) return ''
  return `${t('允许范围')} ${fmtRange(r)}（${r.source}，${t('超出将被拒绝')}）`
}
function writePropHint(meta) {
  const w = (meta.writes || []).find((x) => x.property === cmdForm.prop)
  if (!w) return ''
  let s = t('工程值，盒子内部 ×scale 并校验 min/max')
  if (w.unit) s += '（' + w.unit + '）'
  const r = cmdWriteRange(cmdForm.prop)
  if (r) s += `，${t('允许范围')} ${fmtRange(r)}（${r.source}，${t('超出将被拒绝')}）`
  else s += `，${t('未配置上下限：可在设备配置中设置，当前不限制')}`
  return s
}
// 写入值输入框占位提示：可写点显示其允许范围，便于按范围填写
function cmdValuePlaceholder() {
  if (cmdForm.refMode !== 'prop') return cmdForm.wKind === 'coil' ? '1/0/true/false' : t('0~65535（原始寄存器值）')
  const r = cmdWriteRange(cmdForm.prop)
  return r ? fmtRange(r) : t('工程值')
}
function onCmdBoxChange() {
  cmdForm.device = ''
  cmdForm.prop = ''
  cmdResult.value = null
}
function onCmdDeviceChange() {
  cmdResult.value = null
  const m = cmdDevMeta.value
  if (!m) return
  if (cmdForm.op === 'read') cmdForm.refMode = m.props.length ? 'prop' : 'reg'
  else cmdForm.refMode = m.writes.length ? 'prop' : 'reg'
  cmdForm.prop = ''
  cmdForm.addr = ''
  cmdForm.value = ''
}
function onCmdOpChange() {
  const m = cmdDevMeta.value
  if (!m) return
  if (cmdForm.op === 'read') {
    cmdForm.refMode = m.props.length ? 'prop' : 'reg'
    if (m.isLora) cmdForm.refMode = 'reg'
  } else {
    cmdForm.refMode = (m.writes.length && !m.isLora) ? 'prop' : 'reg'
  }
  cmdForm.prop = ''
  cmdResult.value = null
}
function onCmdRefModeChange() {
  cmdForm.prop = ''
  cmdResult.value = null
}
function switchCmdMode(k) {
  stopCmdPoll()
  cmdPending.value = null
  cmdResult.value = null
  cmdMode.value = k
}
function composeCmdPayload() {
  const box = cmdForm.box
  const name = cmdForm.device
  if (!box || !name) throw new Error(t('请先选择盒子与设备'))
  const m = cmdDevMeta.value
  if (!m || (!m.isLora && !m.isModbus)) throw new Error(t('该设备协议暂不支持设备命令（仅 Modbus / LoRaWAN），请用「原始消息」直发 MQTT'))
  // 从站号（slaveId）不随命令下发：它属于设备配置，盒子按配置里的站号寻址，
  // 避免命令临时指定站号把值写到同一总线上的另一台设备。
  const base = { box, device: name }
  if (m.isLora) {
    if (cmdForm.op === 'read') return { ...base, cmd: 'read' }
    const down = { ...base, cmd: 'down' }
    if (cmdForm.fPort && cmdForm.fPort !== '') down.fPort = Number(cmdForm.fPort)
    if (cmdForm.loraKind === 'hex') {
      if (!cmdForm.loraData) throw new Error(t('请填写下行 hex（十六进制，空格自动去除）'))
      down.hex = String(cmdForm.loraData).replace(/\s+/g, '')
    } else if (cmdForm.loraKind === 'text') {
      down.text = cmdForm.loraData
    } else {
      let obj
      try { obj = JSON.parse(cmdForm.loraData || '{}') } catch (e) { throw new Error(t('object 需为合法 JSON')) }
      if (!obj || typeof obj !== 'object' || Array.isArray(obj)) throw new Error(t('object 需为 JSON 对象（将由 ChirpStack codec 编码下行）'))
      down.object = obj
    }
    return down
  }
  if (cmdForm.op === 'read') {
    const p = { ...base, cmd: 'read' }
    if (cmdForm.refMode === 'prop' && m.props.length && cmdForm.prop) {
      p.property = cmdForm.prop
    } else {
      if (cmdForm.addr === '') throw new Error(t('请填寄存器地址（从 0 起）'))
      p.addr = Number(cmdForm.addr)
      p.type = cmdForm.dtype
      p.fc = Number(cmdForm.fc)
      if (cmdForm.scale && cmdForm.scale !== '') p.scale = Number(cmdForm.scale)
    }
    return p
  }
  // write（Modbus）
  const p = { ...base, cmd: 'write' }
  if (cmdForm.refMode === 'prop' && m.writes.length && cmdForm.prop) {
    p.property = cmdForm.prop
    if (cmdForm.value === '') throw new Error(t('请填写写入值'))
    p.value = Number(cmdForm.value)
    if (!Number.isFinite(p.value)) throw new Error(t('写入值需为数值'))
    // 硬性限制（与后端同口径）：写入值必须落在模型/可写点位配置的数值范围内
    const r = cmdWriteRange(cmdForm.prop)
    if (r) {
      if (r.min != null && p.value < r.min) {
        throw new Error(t('写入值 {v} 低于下限 {min}（{src}「{p}」允许 {range}）',
          { v: p.value, min: r.min, src: r.source, p: cmdForm.prop, range: fmtRange(r) }))
      }
      if (r.max != null && p.value > r.max) {
        throw new Error(t('写入值 {v} 高于上限 {max}（{src}「{p}」允许 {range}）',
          { v: p.value, max: r.max, src: r.source, p: cmdForm.prop, range: fmtRange(r) }))
      }
    }
  } else {
    if (cmdForm.addr === '') throw new Error(t('请填寄存器地址（从 0 起）'))
    p.kind = cmdForm.wKind
    p.addr = Number(cmdForm.addr)
    if (cmdForm.wKind === 'coil') {
      const v = String(cmdForm.value || '').trim().toLowerCase()
      if (['1', 'true', 'on', 'yes'].includes(v)) p.value = 1
      else if (['0', 'false', 'off', 'no'].includes(v)) p.value = 0
      else throw new Error(t('线圈写入值需为 1/0/true/false'))
    } else {
      const v = Number(cmdForm.value)
      if (!Number.isFinite(v)) throw new Error(t('写入值需为数值（原始寄存器值）'))
      if (!Number.isInteger(v)) throw new Error(t('写保持寄存器需为整数原始值（浮点请先乘倍率取整，如 12.5V×10=125）'))
      p.value = v
      // 平台硬性限制（与后端同口径）：裸写的安全范围只认设备配置（同地址可写点位 /
      // 可写属性的 min·max），命令本身不携带上下限；未配置范围一律拒绝
      const r = addrWriteRange(cmdForm.addr, cmdForm.wKind)
      if (!r) {
        throw new Error(t('裸写寄存器缺少安全范围：请在设备配置中为该可写点位/属性设置上下限（平台拒绝无范围的设备写入，防止超限损伤设备）'))
      }
      if (r.min != null && v < r.min) throw new Error(t('写入值 {v} 低于下限 {min}（{src}）', { v, min: r.min, src: r.source }))
      if (r.max != null && v > r.max) throw new Error(t('写入值 {v} 高于上限 {max}（{src}）', { v, max: r.max, src: r.source }))
    }
  }
  return p
}
const cmdPayloadText = computed(() => {
  try { return JSON.stringify(composeCmdPayload(), null, 2) }
  catch (e) { return '// ' + (e.message || e) }
})
async function execCmd() {
  if (cmdSending.value) return
  const box = cmdForm.box
  let payload
  try { payload = composeCmdPayload() } catch (e) { store.showToast(String(e.message || e), 'warn'); return }
  const rid = 'cmd-' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8)
  payload.request_id = rid
  payload.ts = Math.floor(Date.now() / 1000)
  // 盒子应用新配置（保存设备 / 同步 LoRa 问帧）后会 restart 采集服务：重启窗口内发出的命令
  // 无人接收、执行线程也可能被一起杀掉，表现为「命令执行失败」或「无回报」。
  // 这里先探一次近期回执，命中重启窗口就提前说明，避免把重启窗口误判成链路故障。
  try {
    const st = await api.boxApps(box)
    const lastCfg = (st.events || []).filter((e) => e.cmd === 'config' && e.ts).pop()
    if (lastCfg && Date.now() / 1000 - lastCfg.ts < 20) {
      store.showToast(t('盒子刚应用新配置、正在重启采集服务（约 10s），此时下发可能无回报，建议稍后重试'), 'warn')
    }
  } catch (e) { /* 探测失败不阻断下发 */ }
  const topic = 'cmd/' + box + '/cmd'
  stopCmdPoll()
  cmdPending.value = { rid, box }
  cmdResult.value = null
  cmdLastSent.value = topic + '  ' + JSON.stringify(payload)
  cmdSending.value = true
  try {
    const r = await api.boxPublish(topic, JSON.stringify(payload))
    if (!r.ok) {
      cmdPending.value = null
      store.showToast(t('命令发送失败') + '：' + (r.error || r.note || ''), 'error')
      return
    }
    store.showToast(t('已下发 {topic}，等待盒子回报…', { topic }), 'success')
    pollCmdAck(rid, box)
  } catch (e) {
    cmdPending.value = null
    store.showToast(t('命令发送失败') + '：' + (e.message || e), 'error')
  } finally {
    cmdSending.value = false
  }
}
// 命令回报轮询：盒子经 state/{box}/cmd 回报带 request_id 的事件，平台 /box/apps 聚合返回
function pollCmdAck(rid, box) {
  const meta = cmdDevMeta.value
  const deadline = (meta && meta.isLora) ? 20000 : 12000
  const t0 = Date.now()
  const tick = async () => {
    if (!cmdPending.value || cmdPending.value.rid !== rid) return
    try {
      const r = await api.boxApps(box)
      const ev = (r.events || []).find((e) => e.request_id === rid)
      if (ev) {
        cmdPending.value = null
        // 盒子回报的具体原因（如「LoRa 设备 X 未在采集运行」「读寄存器失败: …」）必须直接可见：
        // 只显示「命令执行失败」会让人无从下手，也无法判断是现场链路问题还是平台问题
        const reason = ev.message || t('（盒子无文本回报）')
        const ok = !!ev.ok
        // 失败时把本次下发内容一并给出：便于与盒子 mapper 日志里的「收到云端命令」逐字比对
        const detail = (!ok && cmdLastSent.value)
          ? cmdLastSent.value + '\n' + fmtCmdDetail(ev.detail)
          : fmtCmdDetail(ev.detail)
        cmdResult.value = {
          ok,
          message: reason,
          detailText: detail,
          ts: ev.ts || Math.floor(Date.now() / 1000),
        }
        store.showToast(ok ? t('命令执行成功') : t('命令执行失败') + '：' + reason,
          ok ? 'success' : 'error')
        return
      }
    } catch (e) { /* 继续轮询 */ }
    if (Date.now() - t0 > deadline) {
      cmdPending.value = null
      cmdResult.value = {
        ok: null,
        message: t('超时未收到盒子回报：请确认盒子在线，且 mapper 为支持读/写/LoRa 命令的新版本（旧版会回报「未知命令」失败）'),
        detailText: '',
        ts: Math.floor(Date.now() / 1000),
      }
      return
    }
    cmdTimer = setTimeout(tick, 800)
  }
  tick()
}
// 初始/数据刷新时自动带出首个可选盒子与设备（不打断用户手动选择）
watch([cmdBoxes, cmdDevices], () => {
  if (cmdMode.value !== 'dev') return
  if (!cmdForm.box && cmdBoxes.value.length) cmdForm.box = cmdBoxes.value[0]
  const list = cmdDevices.value
  if (!cmdForm.box || !list.length) return
  if (!cmdForm.device || !list.some((d) => d.name === cmdForm.device)) {
    cmdForm.device = list[0].name
    onCmdDeviceChange()
  }
})
onUnmounted(stopCmdPoll)

</script>

<style scoped>
/* ==================== 数据源管理（原「能碳一体机管理」） · VSCode 风格统一 ==================== */
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
/* 字体层级（本视图统一标准）：层次一律由「字号 + 颜色」承担，字重只用两级 ——
   L1 区块标题 14px / 500（页面唯一的加重层）
   L2 弹窗标题、列表列头 13~13.5px / 500
   L3 卡片标题 / 分组标题 12.5~15px / 400（比正文大一号即可，不再加粗）
   L4 正文 12px / 400      L5 辅助说明 10~11px / 400（--muted / --faint）
   除 L1、L2 外一律 400：状态值靠语义色（绿/红/蓝）区分，不靠字重。 */
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
  padding: 5px 10px; font-size: 11.5px; font-weight: 400; color: var(--text);
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
/* 计数提示紧跟区块标题（默认 .cbx-sec-hint 的 margin-left:auto 会把它推到最右），右侧留给刷新按钮 */
.cbx-sec-hint.res-hint { margin-left: 6px; }
/* 刷新按钮图标：进行中匀速旋转，给出「正在拉取」的即时反馈 */
@keyframes cbx-ref-spin { to { transform: rotate(360deg); } }
.cbx-ref-ic { display: inline-block; line-height: 1; }
.cbx-ref-ic.spin { animation: cbx-ref-spin .8s linear infinite; }
.cbx-reslist { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.cbx-rescol { display: flex; flex-direction: column; min-width: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden; background: var(--panel); }
.cbx-rescol-head { display: flex; align-items: center; gap: 6px; font-size: 12.5px; font-weight: 500; color: var(--text); padding: 8px 10px; background: var(--bar, var(--panel-3)); border-bottom: 1px solid var(--border); }
.cbx-rescol-n { margin-left: auto; font-size: 10.5px; font-weight: 400; color: var(--faint); }
.cbx-rescol-body { display: flex; flex-direction: column; max-height: 248px; overflow-y: auto; }
.cbx-resrow { display: flex; align-items: center; gap: 6px; padding: 6px 10px; font-size: 12px; cursor: pointer; }
.cbx-resrow:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.cbx-resrow + .cbx-resrow { border-top: 1px dashed var(--border); }
.cbx-res-name { flex: 0 1 auto; font-size: 12.5px; font-weight: 400; color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cbx-res-tag { flex: none; font-size: 10px; padding: 0; color: var(--faint); }
.cbx-res-tag.ok { color: var(--green); }
.cbx-res-tag.err { color: var(--red); }
.cbx-res-tag.local { color: var(--accent-d); }
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
.cbx-toolbar-title { font-size: 12.5px; font-weight: 400; letter-spacing: .2px; padding-right: 4px; }
.cbx-toolbar-sep { width: 1px; height: 16px; background: var(--border); margin: 0 2px; }
.cbx-toolbar-msg { margin-left: auto; font-size: 10px; color: var(--muted); }
/* ---- 面板（VSCode 风格：方角 + 标题分隔线 + 统一标题字号） ---- */
.cbx-sec { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 10px 12px; }
.cbx-sec-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
/* L1 区块标题：全页唯一的加重层，其余层级靠字号区分 */
.cbx-sec-head b { font-size: 14px; font-weight: 500; flex: none; letter-spacing: .2px; }
/* 区块折叠：三角按钮 + 标题本身都可点；折叠时内容不渲染（v-if），首屏更轻 */
.cbx-caret { flex: none; width: 18px; height: 18px; padding: 0; line-height: 1; font-size: 11px;
  color: var(--muted); background: transparent; border: none; border-radius: 4px; cursor: pointer; }
.cbx-caret:hover { color: var(--fg, var(--text)); background: color-mix(in srgb, var(--muted) 14%, transparent); }
.cbx-sec-toggle { cursor: pointer; user-select: none; }
.cbx-sec-toggle:hover { color: var(--accent, var(--green)); }
.cbx-sec-head .cbx-op { margin-left: auto; }
.cbx-sec-head .cbx-tag { margin-left: auto; }
.cbx-sec-sub { color: var(--muted); font-size: 10px; }
.cbx-sec-hint { margin-left: auto; font-size: 10px; color: var(--muted); }
/* 区块介绍：标题栏只留标题与操作，说明文字统一放这里（展开后才渲染）*/
.cbx-sec-desc { color: var(--muted); font-size: 11px; line-height: 1.6; margin-bottom: 8px; }
.cbx-sec-desc-extra { margin-left: 8px; font-size: 10px; color: var(--faint); }
/* 字重收敛：仅侧栏列头与指引标题保留 500，其余（命令结果 / 部署步骤 / 键值）一律 400 */
.cbx-side-head b, .cbx-guide-title b { font-weight: 500; }
.cbx-deploy-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap; padding: 6px 10px; margin-bottom: 8px;
  background: var(--panel-2); border: 1px dashed var(--border); border-radius: 3px; font-size: 11px;
  position: relative; /* 作为 YAML 预览浮层的定位锚点 */
}
.cbx-deploy-title { font-size: 12.5px; font-weight: 400; color: var(--muted); flex: none; }
.cbx-deploy-msg { color: var(--green); font-size: 10.5px; max-width: 340px; word-break: break-all; }
/* ---- 输入控件（VSCode 输入框：圆角 2px + 聚焦蓝环） ---- */
.cbx-input {
  border: 1px solid var(--border); border-radius: 2px; background: var(--panel-2);
  color: var(--text); font-size: 11px; padding: 4px 8px; outline: none;
  transition: border-color .12s, box-shadow .12s;
}
.cbx-input:focus { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent); }
.cbx-input::placeholder { color: var(--faint); }
.cbx-select {
  border: 1px solid var(--border); border-radius: 2px; background: var(--panel);
  color: var(--text); font-size: 11px; padding: 3px 6px; outline: none; max-width: 240px;
  transition: border-color .12s, box-shadow .12s;
}
.cbx-select:focus { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent); }
.cbx-input.cbx-xs { width: 52px; }
.cbx-input.cbx-sm { width: 110px; }
.cbx-input.cbx-mid { width: 170px; }
.cbx-input.cbx-md { width: 230px; }
.cbx-input.cbx-grow { flex: 1 1 0; min-width: 120px; width: auto; }
.cbx-input.cbx-num { width: 68px; text-align: right; }
/* ---- 命令执行（区块④）---- */
.cbx-cmd-json {
  flex: 1; min-width: 0; max-height: 150px; overflow: auto; margin: 0;
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px;
  padding: 6px 9px; font-size: 11px; line-height: 1.55;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  color: var(--text); white-space: pre-wrap; word-break: break-all;
}
.cbx-cmd-json.slim { max-height: 110px; }
.cbx-cmd-result {
  margin-top: 8px; padding: 8px 10px; border-radius: 3px; font-size: 11px; line-height: 1.6;
  border: 1px solid var(--border); background: var(--panel-2);
}
.cbx-cmd-result.ok { color: var(--green); border-color: color-mix(in srgb, var(--green) 40%, transparent); background: color-mix(in srgb, var(--green) 8%, transparent); }
.cbx-cmd-result.err { color: var(--red); border-color: color-mix(in srgb, var(--red) 40%, transparent); background: color-mix(in srgb, var(--red) 8%, transparent); }
.cbx-cmd-result.wait { color: var(--yellow); border-color: color-mix(in srgb, var(--yellow) 40%, transparent); background: color-mix(in srgb, var(--yellow) 6%, transparent); }
.cbx-cmd-result pre { margin: 6px 0 0; }
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
  background: var(--rail, #0F172A); color: #E8ECF2;
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
  color: var(--muted); font-weight: 400; font-size: 10.5px; white-space: nowrap;
  background: var(--panel-3, var(--panel-2)); letter-spacing: .3px;
}
.cbx-table tbody tr { transition: background .1s; }
.cbx-table tbody tr:hover td { background: var(--accent-l); }
.cbx-table tbody tr:last-child td { border-bottom: none; }
.cbx-table td code {
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px;
  padding: 0 5px; font-size: 10px; color: var(--accent2);
}
.cbx-table td.val { color: var(--accent-d); font-weight: 400; font-variant-numeric: tabular-nums; }
.cbx-invalid { color: var(--yellow) !important; font-style: italic; font-weight: 400; }
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
/* ---- 通俗化：运行状态总览 + 使用指引（面向非技术人员，不影响任何功能） ---- */
.cbx-hero { background: var(--panel); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
.cbx-hero-main { display: flex; align-items: center; gap: 10px 14px; flex-wrap: wrap; }
.cbx-hero-verdict { display: flex; align-items: center; gap: 10px; flex: 1 1 280px; min-width: 240px; }
.cbx-hero-ic {
  flex: none; width: 34px; height: 34px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 16px; font-weight: 400; line-height: 1;
  background: color-mix(in srgb, var(--green) 13%, transparent); color: var(--green);
}
.cbx-hero-verdict.tone-warn .cbx-hero-ic { background: color-mix(in srgb, var(--yellow) 13%, transparent); color: var(--yellow); }
.cbx-hero-verdict.tone-err .cbx-hero-ic { background: color-mix(in srgb, var(--red) 13%, transparent); color: var(--red); }
.cbx-hero-verdict.tone-mute .cbx-hero-ic { background: color-mix(in srgb, var(--faint) 10%, transparent); color: var(--faint); }
.cbx-hero-tt { min-width: 0; }
.cbx-hero-tt b { font-size: 15px; color: var(--text); letter-spacing: .2px; }
.cbx-hero-tt p { margin: 3px 0 0; font-size: 11px; color: var(--muted); line-height: 1.6; }
.cbx-guide-btn { flex: none; }
.cbx-hero-stats { display: flex; gap: 8px; flex: none; }
.cbx-hero-stat {
  display: flex; flex-direction: column; align-items: center; gap: 2px;
  min-width: 88px; padding: 6px 10px;
  border: 1px solid var(--border); border-radius: 8px; background: var(--panel-2);
}
.cbx-hero-stat.click { cursor: pointer; transition: border-color .12s, transform .12s; }
.cbx-hero-stat.click:hover { border-color: var(--accent); transform: translateY(-1px); }
.cbx-hero-stat b { font-size: 16px; font-variant-numeric: tabular-nums; color: var(--muted); }
.cbx-hero-stat span { font-size: 10px; color: var(--muted); white-space: nowrap; }
.cbx-hero-stat.tone-ok b { color: var(--green); }
.cbx-hero-stat.tone-warn b { color: var(--yellow); }
.cbx-hero-stat.tone-err b { color: var(--red); }
.cbx-hero-stat.tone-mute b { color: var(--faint); }
.cbx-guide { margin-top: 10px; padding: 10px 12px; background: var(--panel-2); border: 1px dashed var(--accent); border-radius: 8px; }
.cbx-guide-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 500; color: var(--accent-d); margin-bottom: 6px; }
.cbx-guide-sub { font-size: 10.5px; font-weight: 400; color: var(--muted); }
.cbx-guide-steps { margin: 6px 0 0; padding-left: 20px; display: flex; flex-direction: column; gap: 5px; }
.cbx-guide-steps li { font-size: 11.5px; color: var(--text); line-height: 1.7; }
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
  font-size: 11.5px; color: var(--accent2); font-weight: 400; letter-spacing: .2px;
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
.cbx-dev-id { font-size: 12.5px; font-weight: 400; color: var(--text); }
.cbx-dev-val { color: var(--accent-d); font-weight: 400; font-variant-numeric: tabular-nums; }
.cbx-dev-fields { font-size: 9.5px; color: var(--muted); background: var(--panel); border: 1px solid var(--border); border-radius: 3px; padding: 0 6px; }
.cbx-dev-seen { font-size: 9.5px; color: var(--faint); }
.cbx-arrow { color: var(--faint); }
.cbx-local { color: var(--accent-d); font-weight: 400; }
/* ---- 表单 ---- */
.cbx-form { display: flex; flex-direction: column; gap: 8px; }
.cbx-form-row { display: flex; align-items: center; gap: 8px; font-size: 11px; flex-wrap: wrap; }
.cbx-form-row label { color: var(--muted); flex: none; }
.cbx-form-sep {
  margin: 4px 0 2px; padding: 4px 8px; font-size: 10.5px; color: var(--accent-d);
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
  color: var(--text); background: var(--panel-3); border: 1px solid transparent; border-radius: 2px;
  padding: 5px 12px; min-height: 24px; cursor: pointer; flex: 0 0 auto;
  white-space: nowrap; user-select: none;
  transition: background .12s, border-color .12s, color .12s, box-shadow .12s;
}
.cbx-op:hover:not(:disabled) { background: color-mix(in srgb, var(--panel-3) 76%, var(--text)); color: var(--text); }
.cbx-op:active:not(:disabled) { background: var(--sel); }
.cbx-op:focus-visible { outline: 1px solid var(--accent); outline-offset: 1px; }
.cbx-op:disabled { opacity: .4; cursor: not-allowed; }
.cbx-op.primary { color: var(--on-accent); background: var(--accent); border-color: transparent; font-weight: 600; }
.cbx-op.primary:hover:not(:disabled) { background: var(--accent-h); color: var(--on-accent); }
.cbx-op.danger { color: var(--red); background: transparent; border-color: transparent; }
.cbx-op.danger:hover:not(:disabled) { background: color-mix(in srgb, var(--red) 14%, transparent); color: var(--red); }
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
  background: var(--rail, #0F172A); border: 1px solid var(--border); border-radius: 4px;
  color: #D5D3CB; font-size: 10px; line-height: 1.6; padding: 10px 12px;
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
/* ---- 消息流 ---- */
/* 日志区固定白色背景（终端风格深色底已按需求移除），文字统一用深色系保证可读 */
.cbx-msglog {
  display: flex; flex-direction: column; gap: 2px;
  max-height: 220px; overflow: auto; background: #fff;
  border: 1px solid var(--border); border-radius: 3px; padding: 6px 8px;
  color: #23303d;
}
.cbx-msgrow { display: flex; align-items: center; gap: 8px; font-size: 10px; padding: 1px 4px; border-radius: 2px; color: #23303d; }
.cbx-msgrow:hover { background: rgba(0,0,0,.05); }
.cbx-msgtime { color: #8b95a1; flex: none; font-variant-numeric: tabular-nums; }
.cbx-msg-topic {
  flex: none; color: #1f6fc4; background: rgba(31,111,196,.1);
  border: 1px solid rgba(31,111,196,.28); border-radius: 3px; padding: 0 5px;
}
.cbx-msg-payload { color: #23303d; opacity: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* ---- 接入指引 ---- */
.cbx-guide-flow { display: flex; align-items: stretch; gap: 10px; margin: 8px 0; flex-wrap: wrap; }
.cbx-flow-node {
  flex: 1 1 0; min-width: 130px; text-align: center; font-size: 12.5px; font-weight: 400;
  background: var(--accent-l); border: 1px solid color-mix(in srgb, var(--accent) 25%, transparent);
  border-radius: 4px; padding: 10px 8px;
}
.cbx-flow-node span { display: block; font-size: 9.5px; color: var(--muted); font-weight: 400; margin-top: 4px; }
.cbx-flow-arrow { display: flex; align-items: center; color: var(--faint); font-size: 16px; }
/* ---- 徽章 / 标签（语义色跟随主题） ---- */
.cbx-badge {
  display: inline-block; font-size: 9.5px; border-radius: 3px; padding: 1px 6px;
  font-weight: 400; letter-spacing: .2px; vertical-align: 1px;
}
.cbx-badge.model { color: var(--yellow); background: color-mix(in srgb, var(--yellow) 12%, transparent); }
.cbx-badge.device { color: var(--accent-d); background: color-mix(in srgb, var(--accent) 12%, transparent); }
.cbx-twin-chip {
  display: inline-block; font-size: 10px; color: var(--accent-d);
  background: color-mix(in srgb, var(--accent) 10%, transparent); border-radius: 3px;
  padding: 1px 6px; margin: 1px 3px 1px 0; cursor: pointer; transition: background .1s;
}
.cbx-twin-chip:hover { background: color-mix(in srgb, var(--accent) 22%, transparent); }
.cbx-twin-chip.cbx-invalid { color: var(--red); background: color-mix(in srgb, var(--red) 10%, transparent); }
/* 云端配置设备条：内联实时读数 */
.cbx-rt-tag {
  display: inline-block; font-size: 9px; font-weight: 400; color: var(--green);
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
.cbx-dialog-head b { font-size: 13.5px; font-weight: 500; letter-spacing: .2px; }  /* L2 弹窗标题 */
.cbx-dialog-head .cbx-op { margin-left: auto; }
.cbx-dialog-head .x-btn.lg { margin-left: auto; }
/* ---- 系统连接图（以设备为单位：每台设备一张卡，卡内为运行在本设备上的服务）---- */
.cbx-topo { position: relative; }
.cbx-topo-lanes { display: flex; align-items: flex-start; gap: 26px; flex-wrap: wrap; justify-content: space-between; }
.cbx-topo-lane { display: flex; flex-direction: column; gap: 14px; flex: 0 1 158px; min-width: 0; }
.cbx-topo-lane.host-lane { flex: 0 1 186px; }
.cbx-topo-lane.cloud-lane { flex: 0 1 224px; }
.cbx-topo-lane.box-lane { flex: 0 1 208px; }
.cbx-topo-lane.dev { flex: 0 1 212px; }
.cbx-topo-lane-title {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; font-weight: 400; color: var(--text); letter-spacing: .3px; padding: 2px 2px 0;
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
.cbx-topo-legend { display: flex; flex-wrap: wrap; gap: 6px 22px; padding: 6px 10px; margin-bottom: 10px; border: 1px dashed var(--line, #2b3652); border-radius: 8px; background: rgba(255,255,255,.015); }
.cbx-topo-legend .leg { display: inline-flex; align-items: center; gap: 6px; font-size: 11.5px; color: #8a94a6; line-height: 1.7; }
.cbx-topo-legend i.lg { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.cbx-topo-legend i.g { background: var(--green); }
.cbx-topo-legend i.b { background: var(--accent); }
.cbx-topo-legend i.r { background: var(--red); }
.cbx-topo-mod::before { content: ''; position: absolute; left: 0; top: 0; bottom: 0; width: 3px; background: var(--accent); }
.cbx-topo-mod.platform::before { background: var(--accent); }
.cbx-topo-mod.agent::before { background: var(--yellow); }
.cbx-topo-mod.cloudcore::before { background: #5b8def; }
.cbx-topo-mod.broker::before { background: var(--accent2); }
.cbx-topo-mod.box::before { background: var(--green); }
.cbx-topo-mod.devgroup::before { background: var(--orange, #f59e0b); }
.cbx-topo-mod.mw::before { background: #7c5cff; }
.cbx-topo-mod.extsrc::before { background: var(--accent); }
/* 外部数据系统列（一体机后面一级），宽度与设备端列一致便于对齐 */
.cbx-topo-lane.extsrc-lane { flex: 0 1 212px; }
.cbx-topo-mod:hover { transform: translateY(-1px); box-shadow: 0 2px 6px rgba(15,23,42,.08), 0 12px 26px rgba(15,23,42,.13); }
.cbx-topo-mod.down { opacity: .75; }
.cbx-topo-mod-head { display: flex; align-items: center; gap: 6px; }
.cbx-topo-mod-name {
  font-weight: 400; font-size: 12px; color: var(--text);
  flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cbx-topo-mod-badge { flex: none; font-size: 9px; font-weight: 400; padding: 1px 6px; border-radius: 2px; color: var(--muted); border: 1px solid var(--border); letter-spacing: .2px; }
.cbx-topo-mod-badge.ok { color: var(--green); border-color: color-mix(in srgb, var(--green) 45%, var(--border)); }
.cbx-topo-mod-sub { font-size: 10px; color: var(--muted); margin-top: 4px; line-height: 1.55; }
.cbx-topo-mod-ops { display: flex; gap: 4px; margin-top: 6px; flex-wrap: wrap; }
.cbx-topo-mod-ops .cbx-op.cbx-xs { padding: 2px 7px; font-size: 9.5px; min-height: 18px; }
/* 盒子卡片：当前运行的服务/模型（云端部署，盒子周期上报） */
.cbx-topo-svcs { display: flex; flex-direction: column; gap: 2px; margin-top: 6px; max-height: 88px; overflow: auto; }
.cbx-topo-svc { display: flex; align-items: center; gap: 5px; font-size: 9.5px; background: rgba(0,0,0,.25); border-radius: 3px; padding: 2px 6px; }
.cbx-topo-svc-dot { flex: none; width: 6px; height: 6px; border-radius: 1px; background: var(--faint); }
.cbx-topo-svc-dot.on { background: var(--green); }
.cbx-topo-svc-name { color: var(--text); font-weight: 400; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* 服务连接地址（host:port / 串口 / 端点 URL）：等宽字体，过长省略，完整值见 title */
.cbx-topo-svc-addr { flex: 1 1 auto; min-width: 0; color: var(--faint); font-size: 8.5px; opacity: .9; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cbx-topo-svc-type { color: var(--faint); font-size: 8.5px; margin-left: auto; flex: none; }
.cbx-topo-svc-empty { font-size: 9.5px; color: var(--faint); padding: 2px 0; }
/* 服务地址可跳转的情况（HTTP 类）：渲染为链接，hover 下划线提示可点 */
a.cbx-topo-svc-addr { color: var(--accent2); opacity: .95; text-decoration: none; cursor: pointer; }
a.cbx-topo-svc-addr:hover { text-decoration: underline; opacity: 1; }
/* 服务行微操作（重启 Broker/CloudCore/agent/box-mapper 等） */
.cbx-topo-svc-ops { display: inline-flex; gap: 2px; flex: none; margin-left: 4px; }
.cbx-topo-svc-ops .cbx-op.cbx-tiny { padding: 0 4px; font-size: 9px; min-height: 15px; line-height: 15px; }
/* 设备内部通信说明（本机进程间通信，不占系统级连线） */
.cbx-topo-inner {
  margin-top: 6px; padding-top: 5px; border-top: 1px dashed var(--border);
  font-size: 8.5px; color: var(--faint); line-height: 1.5;
}
/* 设备卡（系统连接图的基本单元）：头部为设备标识，卡内列表为运行在该设备上的服务 */
.cbx-topo-mod.device { padding: 8px 9px; }
.cbx-topo-mod.cloud::before { background: var(--accent2); }
.cbx-topo-dev-hd { display: flex; align-items: center; gap: 6px; }
.cbx-topo-dev-ic {
  flex: none; width: 20px; height: 20px; border-radius: 4px; font-size: 11px;
  display: inline-flex; align-items: center; justify-content: center;
  background: rgba(255,255,255,.06); border: 1px solid var(--border);
}
.cbx-topo-dev-meta { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; }
.cbx-topo-dev-title {
  font-size: 12.5px; font-weight: 400; color: var(--text); letter-spacing: .2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.cbx-topo-dev-addr { font-size: 9px; color: var(--faint); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cbx-topo-mod.device .cbx-topo-svcs { max-height: 138px; gap: 3px; }
.cbx-topo-mod.device .cbx-topo-devlist { margin-left: 0; padding-left: 6px; margin-top: 6px; }
.cbx-topo-svc.off .cbx-topo-svc-name { color: var(--muted); }
.cbx-edge-check { font-size: 10px; font-weight: 400; align-self: center; padding: 2px 8px; border-radius: 4px; }
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
:global(.cbx-topo-svg-label text) { font-size: 10px; font-weight: 400; fill: var(--text); paint-order: stroke; stroke: var(--panel); stroke-width: 3px; stroke-linejoin: round; }
/* 证书与 Token 有效期（独立区块） */
.cbx-certlist { display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 6px; }
.cbx-certrow {
  display: flex; align-items: center; gap: 10px;
  padding: 7px 12px; font-size: 11px;
  border: 1px solid var(--border); border-radius: 3px; background: var(--panel-2);
}
.cbx-certrow code { color: var(--accent2); font-size: 10.5px; font-weight: 400; flex: none; }
.cbx-cert-exp { color: var(--muted); flex: 1 1 auto; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.cbx-cert-days { flex: none; color: var(--green); font-weight: 400; font-variant-numeric: tabular-nums; }
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
.cbx-topo-dev.pending { border: 1px dashed color-mix(in srgb, var(--red) 45%, transparent); padding: 1px 4px; border-radius: 3px; }
.cbx-topo-dev.pending .cbx-topo-dev-name { color: var(--orange, var(--yellow)); }
.cbx-topo-dev-dot { width: 6px; height: 6px; border-radius: 1px; background: var(--faint); flex: none; }
.cbx-topo-dev.on .cbx-topo-dev-dot { background: var(--green); }
.cbx-topo-dev-name { color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* 设备接入地址：Modbus 串口/TCP、OPC UA 端点、LoRa EUI+从站号、外部源 Broker —— 过长省略，完整值见 title */
.cbx-topo-dev-addr { flex: 1 1 auto; min-width: 0; font-size: 9px; color: var(--faint); opacity: .9; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
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
.cbx-rt-tab.active { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent); }
.cbx-rt-tab .cbx-rt-cur { font-weight: 400; color: var(--accent-d); font-variant-numeric: tabular-nums; }
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
.cbx-rt-tip-v { color: var(--accent-d); font-weight: 400; font-variant-numeric: tabular-nums; }
.cbx-rt-currow { display: flex; align-items: baseline; gap: 8px; font-size: 12px; padding: 0 2px; }
.cbx-rt-curlabel { color: var(--muted); font-size: 10px; }
.cbx-rt-curval { color: var(--accent-d); font-size: 22px; font-weight: 400; font-variant-numeric: tabular-nums; line-height: 1; }
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

/* ============ 数据源接入区块（能碳一体机 + 外部数据源） ============ */
.cbx-sec-sources { display: flex; flex-direction: column; gap: 10px; }
.ds-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 10px; }
.ds-card {
  display: flex; flex-direction: column; gap: 8px;
  border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px;
  background: var(--panel); box-shadow: 0 1px 2px rgb(0 0 0 / .06);
}
.ds-card.off { opacity: .72; }
.ds-card.mwdown { border-color: color-mix(in srgb, var(--red) 45%, var(--border)); }
.ds-card-hd { display: flex; align-items: center; gap: 6px; }
.ds-card-hd b { font-size: 15px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ds-tag { font-size: 11px; padding: 1px 7px; border-radius: 9px; color: var(--muted);
  background: color-mix(in srgb, var(--muted) 13%, transparent); white-space: nowrap; }
.ds-tag.builtin { color: var(--green); background: color-mix(in srgb, var(--green) 13%, transparent); }
.ds-tag.mono, .ds-card .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
.ds-desc { font-size: 12px; color: var(--muted); line-height: 1.5; min-height: 18px; }
.ds-rows { display: flex; flex-direction: column; gap: 5px; font-size: 12px; }
.ds-row { display: flex; align-items: baseline; gap: 8px; }
.ds-row > span:first-child { color: var(--muted); flex: 0 0 64px; }
.ds-row b { font-weight: 400; }
.ds-row b.ok { color: var(--green); }
.ds-row b.err { color: var(--red); }
.ds-row b.dim, .ds-row .dim, .ds-desc { color: var(--muted); }
.ds-row b.note { color: #b58900; font-weight: 400; }
/* 数据服务接口清单的样式随模块迁到 DataServiceApiPanel.vue（独立模块自带 scoped 样式） */
.ds-endps { display: inline-flex; gap: 6px; }
.ds-ep { font-size: 11px; padding: 1px 7px; border-radius: 9px; border: 1px solid var(--border); }
.ds-ep.on { color: var(--green); border-color: color-mix(in srgb, var(--green) 55%, var(--border)); }
.ds-ep.off { color: var(--red); border-color: color-mix(in srgb, var(--red) 45%, var(--border)); }
.ds-ops { display: flex; align-items: center; gap: 6px; margin-top: 2px; }
.cbx-op.danger { color: var(--red); border-color: transparent; }
.ds-card.ds-empty { align-items: center; text-align: center; cursor: pointer; padding: 22px 18px; border-style: dashed; }
.ds-card.ds-empty:hover { border-color: var(--accent); }
.ds-empty-ic { font-size: 30px; opacity: .5; }
.ds-card.ds-empty b { font-size: 14px; font-weight: 400; }
.ds-card.ds-empty p { font-size: 12px; color: var(--muted); margin: 4px 0 10px; }
.ds-form {
  border: 1px solid var(--accent); border-radius: 10px; padding: 10px 12px;
  background: color-mix(in srgb, var(--accent) 4%, var(--panel));
  display: flex; flex-direction: column; gap: 8px;
}
.ds-form-title { font-size: 13px; }
.ds-form-hint { font-size: 11px; color: var(--muted); }
.ds-fields { flex: 1; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 6px 14px; }
.ds-fld { display: flex; flex-direction: column; gap: 3px; }
.ds-fld label { font-size: 11px; color: var(--muted); }
.ds-fld .cbx-input, .ds-fld textarea.cbx-input { width: 100%; font-size: 12px; }
.ds-fld-desc { font-size: 11px; color: var(--muted); opacity: .85; }
.ds-form-err { color: var(--red); font-size: 12px; }
/* 开关（沿用页面风格的小型 toggle） */
.ds-switch { display: inline-flex; align-items: center; gap: 5px; cursor: pointer; font-size: 12px; user-select: none; }
.ds-switch input { display: none; }
.ds-switch i { width: 30px; height: 16px; border-radius: 9px; background: var(--border); position: relative; transition: background .15s; }
.ds-switch i::after { content: ''; position: absolute; top: 2px; left: 2px; width: 12px; height: 12px; border-radius: 50%; background: #fff; transition: left .15s; }
.ds-switch input:checked + i { background: var(--green); }
.ds-switch input:checked + i::after { left: 16px; }
.ds-switch span { color: var(--muted); }
.ds-switch input:checked + i + span { color: var(--green); }
</style>
