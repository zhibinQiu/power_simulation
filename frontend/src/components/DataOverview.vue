<template>
  <div class="data-overview" :class="['ov-' + theme, { fs: store.fullscreenOn }]" v-fit>
    <!-- 顶部工具条（各页面常驻）：不显示标题，只保留全屏工具 / 明暗切换 -->
    <header class="ov-head">
      <div class="ov-head-right">
        <!-- 全屏模式：顶部工具栏已隐藏，「三维仿真」切换与「退出全屏」入口移至内容区头部 -->
        <div v-if="store.fullscreenOn" class="ov-fs-tools">
          <button type="button" class="fs-tool-btn" @click="store.toggleOverview()">
            <Icon name="cube" :size="16" :stroke="1.6"/>
          </button>
          <button type="button" class="fs-tool-btn" :title="t('退出全屏')" @click="store.toggleFullscreen()">
            <Icon name="fullscreen" :size="16" :stroke="1.6"/>
          </button>
        </div>
        <button v-else type="button" class="fs-tool-btn" :title="t('全屏显示')" @click="store.toggleFullscreen()">
          <Icon name="fullscreen" :size="16" :stroke="1.6"/>
        </button>
        <button type="button" class="ov-theme" @click="toggleTheme" :aria-label="t('切换明暗主题')">
          <svg v-if="theme === 'dark'" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="4.5"/>
            <path d="M12 2v2.5M12 19.5V22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M2 12h2.5M19.5 12H22M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.6 6.6 0 0 0 9.8 9.8z"/>
          </svg>
        </button>
      </div>
    </header>

    <!-- 内容区：左侧页面（总览 / 明细） + 右侧实时调控建议 -->
    <div class="ov-body">
      <!-- 页面切换（一级总览 / 二级明细） -->
      <Transition name="ovpg" mode="out-in">
      <!-- ================= 一级：总览（仅汇总信息） ================= -->
      <section v-if="page === 'home'" key="home" class="ov-page">
        <!-- KPI 触控卡片行 -->
        <div class="ov-kpis">
          <button type="button" class="kpi" @click="goto('devices')">
            <div class="kpi-ring" :style="{ background: ringGradient }">
              <div class="kpi-ring-inner">
                <b data-fit>{{ healthPct }}<em>%</em></b>
                <i>{{ t('正常率') }}</i>
              </div>
            </div>
            <div class="kpi-body">
              <span class="kpi-title">{{ t('设备健康度') }}</span>
              <span class="kpi-sub"><i class="lg ok"></i>{{ statRunning }} {{ t('正常') }}<i class="lg ab"></i>{{ statAbnormal }} {{ t('异常') }}</span>
              <span class="kpi-arrow">{{ t('查看明细') }} ›</span>
            </div>
          </button>

          <button type="button" class="kpi" @click="goto('carbon')">
            <div class="kpi-ico carbon">CO₂</div>
            <div class="kpi-body">
              <span class="kpi-title">{{ t('年度碳排放') }}</span>
              <span class="kpi-num" data-fit>{{ fmtWan(carbon.yearly) }}<em> {{ t('万吨') }}</em></span>
              <span class="kpi-sub">{{ t('实时') }} {{ fmtNum(carbon.co2h) }} t/h</span>
            </div>
          </button>

          <button type="button" class="kpi" :class="{ alarm: cloudAlarm }" @click="goto('box')">
            <div class="kpi-ico box"><i></i><i></i><i></i><i></i></div>
            <div class="kpi-body">
              <span class="kpi-title">{{ t('能碳一体机') }}</span>
              <span class="kpi-num" data-fit>{{ boxOnline }}<em> / {{ boxTotal }} {{ t('节点') }}</em></span>
              <span class="kpi-sub"><i class="lg" :class="cloudAlarm ? 'ab' : 'ok'"></i>{{ t(cloudSource.label) }}</span>
            </div>
          </button>

          <button type="button" class="kpi" :class="{ alarm: alarmHigh > 0 }" @click="goto('alarms')">
            <div class="kpi-ico alarm">!</div>
            <div class="kpi-body">
              <span class="kpi-title">{{ t('报警中心') }}</span>
              <span class="kpi-num" data-fit :class="{ warn: alarmHigh + alarmMid > 0 }">{{ alarmHigh + alarmMid }}<em> {{ t('条') }}</em></span>
              <span class="kpi-sub"><i class="lg ab"></i>{{ alarmHigh }} {{ t('紧急') }}<i class="lg mid"></i>{{ alarmMid }} {{ t('一般') }}</span>
            </div>
          </button>
        </div>

        <!-- 模块化面板 -->
        <div class="ov-modules">
          <!-- 工艺设备状态（汇总） -->
          <button type="button" class="module" @click="goto('devices')">
            <div class="mod-head">
              <span class="mod-title">{{ t('工艺设备状态') }}</span>
              <span class="mod-link">{{ t('查看明细') }} ›</span>
            </div>
            <div class="mod-units">
              <div v-for="g in groups" :key="g.unitId" class="mu-row">
                <span class="mu-name" :title="g.unitName">{{ g.unitName }}</span>
                <span class="mu-dots">
                  <i v-for="d in g.devices" :key="d.id" :class="'st-' + d.state.key"></i>
                </span>
                <span class="mu-cnt ok">{{ g.runCount }}</span>
                <span class="mu-cnt ab">{{ g.abnormalCount }}</span>
                <span class="mu-cnt st">{{ g.stoppedCount }}</span>
              </div>
              <div v-if="!groups.length" class="ov-empty sm">{{ t('暂无设备数据，请先配置工艺流程并开启实时数据源') }}</div>
            </div>
            <div class="mod-bar">
              <i class="ok" :style="{ width: pct('run') + '%' }"></i>
              <i class="ab" :style="{ width: pct('abnormal') + '%' }"></i>
              <i class="st" :style="{ width: pct('stopped') + '%' }"></i>
            </div>
            <div class="mod-foot">
              <span class="lg ok"></span>{{ t('正常') }}<span class="lg ab"></span>{{ t('异常') }}<span class="lg st"></span>{{ t('停机/离线') }}
            </div>
          </button>

          <!-- 能碳一体机（汇总） -->
          <button type="button" class="module" @click="goto('box')">
            <div class="mod-head">
              <span class="mod-title">{{ t('能碳一体机') }}</span>
              <span class="mod-link">{{ t('查看明细') }} ›</span>
            </div>
            <div class="mod-cloud" :class="'cs-' + cloudSource.key">
              <i class="mc-dot"></i>{{ t('云端链路') }}：{{ t(cloudSource.label) }}
            </div>
            <div class="mod-grid">
              <div class="mg-item">
                <b data-fit>{{ boxOnline }}<em> / {{ boxTotal }}</em></b>
                <i>{{ t('盒子节点就绪') }}</i>
              </div>
              <div class="mg-item">
                <b data-fit>{{ boxDevOnline }}<em> / {{ boxDevices.length }}</em></b>
                <i>{{ t('传感器在线') }}</i>
              </div>
              <div class="mg-item">
                <b :class="{ ok: ccOk }">{{ ccText }}</b>
                <i>CloudCore</i>
              </div>
              <div class="mg-item">
                <b :class="{ ok: brokerConnected }">{{ brokerConnected ? t('已连接') : t('未连接') }}</b>
                <i>MQTT Broker</i>
              </div>
            </div>
            <div class="mod-err" v-if="cloudError">{{ cloudError }}</div>
          </button>
        </div>

        <!-- 底部报警滚动条（触控进入报警中心） -->
        <div class="ov-ticker" @click="goto('alarms')">
          <span class="tk-label" :class="{ alarm: alarmHigh > 0 }">{{ t('报警') }}</span>
          <div class="tk-scroll">
            <div class="tk-track" :class="{ idle: !tickerItems.length }">
              <span v-for="(a, i) in tickerItems" :key="i" class="tk-item" :class="'lv-' + a.level">● {{ a.msg }}</span>
            </div>
          </div>
          <span class="tk-arrow">›</span>
        </div>
      </section>

      <!-- ================= 二级：明细 ================= -->
      <section v-else key="detail" class="ov-page">
        <div class="ov-detail-head">
          <button type="button" class="ov-back" @click="back()">‹ {{ t('返回总览') }}</button>
          <span class="ov-detail-title">{{ t(pageTitle) }}</span>
          <span class="ov-detail-sp"></span>
        </div>

        <!-- ── 工艺设备状态明细（含传感器读数） ── -->
        <template v-if="page === 'devices'">
          <div class="dt-scroll">
            <div v-for="g in groups" :key="g.unitId" class="dt-unit" :class="{ alarm: g.abnormalCount > 0 }">
              <div class="dt-unit-head">
                <span class="dt-unit-name">{{ g.unitName }}</span>
                <span class="dt-unit-cnt">
                  <i class="ok">{{ g.runCount }} {{ t('正常') }}</i>
                  <i class="ab">{{ g.abnormalCount }} {{ t('异常') }}</i>
                  <i class="st">{{ g.stoppedCount }} {{ t('停机') }}</i>
                </span>
              </div>
              <div class="dt-devices">
                <div v-for="d in g.devices" :key="d.id" class="dt-dev" :class="'st-' + d.state.key">
                  <i class="dd-dot"></i>
                  <span class="dd-name" :title="d.label">{{ d.label }}</span>
                  <span class="dd-val" data-fit v-if="d.live != null">{{ fmtNum(d.live) }}<em> {{ d.unit }}</em></span>
                  <span class="dd-val na" v-else>—</span>
                  <span class="dd-st" :style="{ color: d.state.color, borderColor: d.state.color }">{{ t(d.state.label) }}</span>
                  <span class="dd-why" v-if="d.state.reason">{{ t(d.state.reason, { dev: d.state.devPct }) }}</span>
                  <span class="dd-time">{{ relTime(lastTs(d)) }}</span>
                </div>
              </div>
            </div>
            <div v-if="!groups.length" class="ov-empty">{{ t('暂无设备数据，请先配置工艺流程并开启实时数据源') }}</div>
          </div>
        </template>

        <!-- ── 碳排放明细 ── -->
        <template v-else-if="page === 'carbon'">
          <div class="dt-carbon-main">
            <span class="dcm-label">{{ t('年度总碳排放量') }}</span>
            <span class="dcm-num" data-fit>{{ fmtWan(carbon.yearly) }}<em> {{ t('万吨') }} CO₂</em></span>
            <span class="dcm-sub">{{ t('按 8000h/年折算 · 当前排放') }} {{ fmtNum(carbon.co2h) }} t/h</span>
          </div>
          <div class="dt-scopes">
            <div class="dts-row">
              <span class="dts-name">{{ t('直接排放 · Scope 1') }}</span>
              <span class="dts-val" data-fit>{{ fmtWan(carbon.directWan) }} {{ t('万吨') }}（{{ carbon.directPct.toFixed(1) }}%）</span>
              <div class="dts-bar"><i class="direct" :style="{ width: carbon.directPct + '%' }"></i></div>
            </div>
            <div class="dts-row">
              <span class="dts-name">{{ t('间接排放 · Scope 2') }}</span>
              <span class="dts-val" data-fit>{{ fmtWan(carbon.indirectWan) }} {{ t('万吨') }}（{{ carbon.indirectPct.toFixed(1) }}%）</span>
              <div class="dts-bar"><i class="indirect" :style="{ width: carbon.indirectPct + '%' }"></i></div>
            </div>
          </div>
          <div class="dt-metrics">
            <div class="dmetric"><span class="dm-k">{{ powerScene ? t('度电碳排') : t('吨钢排放强度') }}</span><b data-fit>{{ fmtNum(carbon.intensity) }}<em> {{ powerScene ? 'gCO₂/kWh' : 'kgCO₂/t' }}</em></b></div>
            <div class="dmetric"><span class="dm-k">{{ powerScene ? t('年发电量') : t('年产量') }}</span><b data-fit>{{ fmtWan(powerScene ? carbon.powerYear : carbon.steelYear) }}<em> {{ powerScene ? t('亿kWh') : t('万吨') }}</em></b></div>
            <div class="dmetric"><span class="dm-k">{{ t('碳捕集速率') }}</span><b data-fit>{{ fmtNum(carbon.captured) }}<em> t/h</em></b></div>
            <div class="dmetric"><span class="dm-k">{{ t('直接排放占比') }}</span><b data-fit>{{ carbon.directPct.toFixed(1) }}<em> %</em></b></div>
          </div>
        </template>

        <!-- ── 能碳一体机明细 ── -->
        <template v-else-if="page === 'box'">
          <div class="dt-card" :class="'cs-' + cloudSource.key">
            <div class="dt-card-title">{{ t('云端链路') }}</div>
            <div class="dt-cloud">
              <div class="dtc-item"><span class="k">{{ t('云端状态') }}</span><b :class="'cld-' + cloudSource.key">{{ t(cloudSource.label) }}</b></div>
              <div class="dtc-item"><span class="k">CloudCore</span><b :class="{ ok: ccOk }">{{ ccText }}</b></div>
              <div class="dtc-item"><span class="k">MQTT Broker</span><b :class="{ ok: brokerConnected }">{{ brokerConnected ? t('已连接') : t('未连接') }}</b></div>
              <div class="dtc-item"><span class="k">{{ t('数据刷新') }}</span><b>{{ t('约') }} {{ ovAge }}s {{ t('前') }}</b></div>
            </div>
            <div class="dtc-err" v-if="cloudError">{{ cloudError }}</div>
          </div>

          <div class="dt-card">
            <div class="dt-card-title">{{ t('盒子节点') }}（{{ boxTotal }}）</div>
            <div class="dt-nodes">
              <div v-for="n in boxNodes" :key="n.name" class="dt-node" :class="'st-' + nodeState(n).key">
                <i class="nd-dot"></i>
                <span class="nd-name" :title="n.name">{{ n.name }}</span>
                <span class="nd-st">{{ t(nodeState(n).label) }}</span>
              </div>
              <div v-if="!boxNodes.length" class="ov-empty sm">{{ t('暂无盒子节点') }}</div>
            </div>
          </div>

          <div class="dt-card">
            <div class="dt-card-title">{{ t('传感器 · 设备') }}（{{ boxDevices.length }}）</div>
            <div class="dt-sensors">
              <div v-for="d in boxDevices" :key="d.name" class="dt-sensor" :class="'st-' + devState(d).key">
                <i class="nd-dot"></i>
                <span class="nd-name" :title="d.name">{{ d.name }}</span>
                <span class="nd-model" data-fit>{{ d.model || '—' }}</span>
                <span class="nd-st">{{ t(devState(d).label) }}</span>
                <span class="nd-time" v-if="d.data_ts || d.last_seen">{{ relTime(d.data_ts || d.last_seen) }}{{ t('前') }}</span>
              </div>
              <div v-if="!boxDevices.length" class="ov-empty sm">{{ t('暂无设备，请在「能碳一体机」中配置') }}</div>
            </div>
          </div>
        </template>

        <!-- ── 报警中心 ── -->
        <template v-else-if="page === 'alarms'">
          <div class="ov-alarm-stats">
            <div class="as-item high"><b data-fit>{{ alarmHigh }}</b><i>{{ t('紧急') }}</i></div>
            <div class="as-item mid"><b data-fit>{{ alarmMid }}</b><i>{{ t('一般') }}</i></div>
            <div class="as-item low"><b data-fit>{{ alarmLow }}</b><i>{{ t('提示') }}</i></div>
            <div class="as-item total"><b data-fit>{{ alarms.length }}</b><i>{{ t('全部') }}</i></div>
          </div>
          <div class="dt-alarms">
            <div v-for="(a, i) in alarms" :key="i" class="dt-alarm" :class="'lv-' + a.level">
              <i class="al-dot"></i>
              <span class="al-src">{{ a.src }}</span>
              <span class="al-msg">{{ t(a.msg) }}</span>
              <span class="al-time">{{ fmtTime(a.ts) }}</span>
            </div>
            <div v-if="!alarms.length" class="ov-empty">
              <span class="al-ok-dot"></span>{{ t('系统运行正常，当前无报警') }}
            </div>
          </div>
        </template>
      </section>
      </Transition>

      <!-- ── 右侧：实时调控建议（操作人员据此手动调控对应设备，平台不自动下发） ── -->
      <aside class="ov-aside">
        <div class="adv-head">
          <span class="adv-title">{{ t('实时调控建议') }}</span>
        </div>
        <div class="adv-scene">{{ t(advice.sceneLabel) }}</div>
        <div class="adv-kpis">
          <div class="adv-kpi"><i>{{ t('发电') }}</i><b data-fit>{{ Math.round(advice.ops.gen) }}<em> MW</em></b></div>
          <div class="adv-kpi"><i>{{ t('入炉煤') }}</i><b data-fit>{{ advice.ops.coal.toFixed(1) }}<em> t/h</em></b></div>
          <div class="adv-kpi"><i>{{ t('厂用电率') }}</i><b data-fit>{{ advice.ops.auxRate.toFixed(2) }}<em> %</em></b></div>
          <div class="adv-kpi"><i>{{ t('发电煤耗') }}</i><b data-fit>{{ advice.ops.coalGce.toFixed(1) }}<em> gce/kWh</em></b></div>
        </div>
        <div class="adv-list">
          <article v-for="a in adviceItems" :key="a.id" class="adv-item" :class="['lv-' + a.level, { done: isDone(a) }]">
            <div class="ai-top">
              <span class="ai-lv">{{ t(levelLabel(a)) }}</span>
              <span class="ai-title">{{ t(a.title) }}</span>
            </div>
            <div class="ai-row"><span class="ai-k">{{ t('调控对象') }}</span><span class="ai-v">{{ t(a.target) }}</span></div>
            <div class="ai-cmp">
              <span class="ai-cur"><i>{{ t('当前') }}</i><b>{{ a.cur }}</b><em>{{ a.unit }}</em></span>
              <span class="ai-ar">→</span>
              <span class="ai-go"><i>{{ t('目标') }}</i><b>{{ a.goal }}</b></span>
            </div>
            <div class="ai-row act"><span class="ai-k">{{ t('操作指引') }}</span><span class="ai-v">{{ t(a.action) }}</span></div>
            <div class="ai-row gain"><span class="ai-k">{{ t('预期') }}</span><span class="ai-v">{{ t(a.gain, a.gainArgs || {}) }}</span></div>
            <button type="button" class="ai-btn" :class="{ on: isDone(a) }" @click="toggleDone(a)">{{ isDone(a) ? t('已执行') : t('标记已执行') }}</button>
          </article>
          <div v-if="!adviceItems.length" class="ov-empty sm">{{ t('当前工况平稳，暂无调控建议') }}</div>
        </div>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { api } from '../api/client'
import { t } from '../i18n'
import { themeMode } from '../theme'
import { visiblePoll } from '../utils/poll'
import { buildHmiAdvice } from '../data/hmiAdvice'
import Icon from './Icon.vue'

const store = useSimStore()

// 年运行小时（钢铁长流程：日历 8760h 扣除检修停机约 760h）
const ANNUAL_HOURS = 8000
// 数据新鲜阈值：最后一条读数距今超过该秒数即视为停机/无数据
const STALE_AFTER = 90
// 异常判定阈值：可调设备偏离设定值；计量设备偏离历史中位
const DEVIATION_SP = 0.15
const DEVIATION_MED = 0.25

// 当前时间（每秒刷新）：只驱动时钟与「数据新鲜度」这类真正需要秒级精度的展示。
const now = ref(Date.now())
// 报警条目的时间戳：取「最近一次数据刷新时刻」而非每秒的 now。
// 否则 alarms 这个含全部设备遍历的 computed 会随秒级 tick 每秒整体重算 + 重渲染
// （本页最重的一块，每秒一次纯属浪费）。报警只在数据回来时变化，语义上也更准确。
const lastRefresh = ref(Math.floor(Date.now() / 1000))
let stopClockPoll = null
let stopBoxPoll = null
let stopAdvicePoll = null

// 一体机云端数据（10s 轮询）
const boxOverview = ref(null)
const boxDevicesData = ref([])

// ---------- 明暗主题（跟随全局深色态；localStorage 只记「上次主题」，不做锁定） ----------
// 全局深色态 = 仿真模式（store.simMode）或全局夜间主题（themeMode==='dark'），
// 与 App.vue 里 .app.sim-dark 的绑定条件保持一致（不查 DOM class，避免挂载时序问题）。
const theme = ref('dark')
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  try { localStorage.setItem('data-overview-theme', theme.value) } catch (e) { /* 忽略 */ }
}
// 运行/停止仿真（或切换全局明暗）时 HMI 主题同步切换 —— 用户中途手动切换仍即时生效，
// 但下一次全局深色态变化会重新覆盖（方案 A：跟随总是生效，手动选择不做跨状态锁定）。
watch(() => (store.simMode || themeMode.value === 'dark'), (simDark) => {
  theme.value = simDark ? 'dark' : 'light'
  try { localStorage.setItem('data-overview-theme', theme.value) } catch (e) { /* 忽略 */ }
})

// ---------- 页面路由：home 一级总览 / 二级明细 ----------
const page = ref('home')
const pageTitle = computed(() => ({ devices: '工艺设备状态明细', carbon: '碳排放明细', box: '能碳一体机状态明细', alarms: '报警中心' }[page.value] || ''))
function goto(p) { page.value = p }
function back() { page.value = 'home' }

// ---------- 设备运转状态判定 ----------
function deviceState(d) {
  const h = d.history || []
  const last = h.length ? h[h.length - 1] : null
  const fresh = !!(last && now.value / 1000 - last.t < STALE_AFTER)
  if (d.live != null) {
    if (d.setpoint != null && Math.abs(d.setpoint) > 1e-9) {
      const dev = Math.abs(d.live - d.setpoint) / Math.abs(d.setpoint)
      if (dev > DEVIATION_SP) return { key: 'abnormal', label: '异常', color: 'var(--ov-ab)', reason: '偏离设定值 {dev}%', devPct: (dev * 100).toFixed(0) }
    } else if (h.length >= 5) {
      const mid = median(h.map((p) => p.v))
      if (Math.abs(mid) > 1e-9 && Math.abs(d.live - mid) / Math.abs(mid) > DEVIATION_MED) {
        return { key: 'abnormal', label: '异常', color: 'var(--ov-ab)', reason: '偏离历史正常区间' }
      }
    }
  }
  if (!fresh || (d.live == null && !h.length)) return { key: 'stopped', label: '停机', color: 'var(--ov-st)', reason: '数据超时' }
  return { key: 'run', label: '正常', color: 'var(--ov-ok)' }
}

function median(arr) {
  const a = [...arr].sort((x, y) => x - y)
  const m = Math.floor(a.length / 2)
  return a.length % 2 ? a[m] : (a[m - 1] + a[m]) / 2
}

// 工艺设备按工序分组（含状态汇总计数）
const groups = computed(() => {
  const map = new Map()
  for (const d of store.allDevices) {
    if (d.live == null && (!d.history || !d.history.length)) continue
    const st = deviceState(d)
    if (!map.has(d.unitId)) map.set(d.unitId, { unitId: d.unitId, unitName: d.unitName, devices: [] })
    map.get(d.unitId).devices.push({ ...d, state: st })
  }
  const out = Array.from(map.values())
  for (const g of out) {
    g.runCount = g.devices.filter((x) => x.state.key === 'run').length
    g.abnormalCount = g.devices.filter((x) => x.state.key === 'abnormal').length
    g.stoppedCount = g.devices.filter((x) => x.state.key === 'stopped').length
  }
  return out
})

const statDevices = computed(() => groups.value.reduce((s, g) => s + g.devices.length, 0))
const statRunning = computed(() => groups.value.reduce((s, g) => s + g.runCount, 0))
const statAbnormal = computed(() => groups.value.reduce((s, g) => s + g.abnormalCount, 0))
const statStopped = computed(() => groups.value.reduce((s, g) => s + g.stoppedCount, 0))

const healthPct = computed(() => (statDevices.value ? Math.round((statRunning.value / statDevices.value) * 100) : 0))

// 健康度环形图（conic-gradient 三段：正常/异常/停机）
const ringGradient = computed(() => {
  const t = Math.max(1, statDevices.value)
  const ok = (statRunning.value / t) * 360
  const ab = (statAbnormal.value / t) * 360
  const st = (statStopped.value / t) * 360
  if (!statDevices.value) return 'conic-gradient(var(--ov-panel-3) 0deg 360deg)'
  return `conic-gradient(var(--ov-ok) 0deg ${ok}deg, var(--ov-ab) ${ok}deg ${ok + ab}deg, var(--ov-st) ${ok + ab}deg ${ok + ab + st}deg)`
})

function pct(k) {
  const t = Math.max(1, statDevices.value)
  return ((groups.value.reduce((s, g) => s + g.devices.filter((x) => x.state.key === k).length, 0)) / t) * 100
}

// ---------- 能碳一体机状态 ----------
const cloudSource = computed(() => {
  const cs = boxOverview.value?.cloud_source
  const map = {
    live: { key: 'live', label: '云端实时' },
    stale: { key: 'stale', label: '数据过期' },
    degraded: { key: 'degraded', label: '部分异常' },
    unreachable: { key: 'unreachable', label: '云端不可达' },
  }
  return map[cs] || { key: 'unknown', label: '状态未知' }
})
const cloudError = computed(() => boxOverview.value?.cloud_error || '')
const ccText = computed(() => boxOverview.value?.cloudcore?.phase || '—')
const ccOk = computed(() => boxOverview.value?.cloudcore?.available === true)
const brokerConnected = computed(() => boxOverview.value?.broker?.connected === true)
const boxNodes = computed(() => (boxOverview.value?.nodes || []).filter((n) => n.is_edge))
const boxTotal = computed(() => boxNodes.value.length)
const boxOnline = computed(() => boxNodes.value.filter((n) => nodeState(n).key === 'run').length)
const cloudAlarm = computed(() => boxTotal.value > 0 && boxOnline.value < boxTotal.value)
const boxDevices = computed(() => boxDevicesData.value || [])
const boxDevOnline = computed(() => boxDevices.value.filter((d) => devState(d).key === 'run').length)
const ovAge = computed(() => {
  const b = boxOverview.value
  if (b?._cache_age != null) return Math.round(b._cache_age)
  if (b?._cache_ts) return Math.max(0, Math.round(now.value / 1000 - b._cache_ts))
  return '--'
})

function nodeState(n) {
  if (n.ready === true) return { key: 'run', label: '就绪' }
  if (n.ready === false) return { key: 'abnormal', label: '未就绪' }
  return { key: 'stopped', label: '状态未知' }
}
function devState(d) {
  // 在线 = 有实时数据推送（后端统一判定：CRD twins 或 MQTT data/# 双通道，120s 窗口，见 data_online）；
  // 曾上报过但停滞 → 离线；从未上报 → 未上报
  if (d.data_online === true) return { key: 'run', label: '在线' }
  const ls = d.data_ts || d.last_seen || 0
  return ls ? { key: 'stopped', label: '离线' } : { key: 'stopped', label: '未上报' }
}

// ---------- 报警汇总（一级界面只显示数量，明细在二级） ----------
const alarms = computed(() => {
  const list = []
  const push = (level, src, msg, ts) => list.push({ level, src, msg, ts })
  for (const g of groups.value) {
    for (const d of g.devices) {
      if (d.state.key === 'abnormal') push('high', `${g.unitName} · ${d.label}`, (d.state.reason || '').replace('{dev}', d.state.devPct != null ? d.state.devPct : '?'), lastTs(d))
      else if (d.state.key === 'stopped') push('mid', `${g.unitName} · ${d.label}`, '数据超时停机', lastTs(d))
    }
  }
  const ov = boxOverview.value
  const cs = cloudSource.value.key
  const stamp = lastRefresh.value
  if (cs === 'unreachable') push('high', t('能碳一体机'), cloudError.value || '云端不可达', stamp)
  else if (cs === 'degraded') push('mid', t('能碳一体机'), '云端链路部分异常', stamp)
  else if (cs === 'stale') push('low', t('能碳一体机'), '云端数据过期', stamp)
  if (ov?.cloudcore && ov.cloudcore.available === false) push('high', t('能碳一体机'), 'CloudCore 异常', stamp)
  if (ov?.broker && ov.broker.connected !== true) push('mid', t('能碳一体机'), 'MQTT Broker 未连接', stamp)
  for (const n of boxNodes.value) {
    const s = nodeState(n).key
    if (s === 'abnormal') push('high', `${t('盒子节点')} · ${n.name}`, '节点未就绪', stamp)
    else if (s === 'stopped') push('low', `${t('盒子节点')} · ${n.name}`, '状态未知', stamp)
  }
  for (const d of boxDevices.value) {
    const s = devState(d).key
    if (s === 'stopped') push('mid', `${t('传感器')} · ${d.name}`, (d.data_ts || d.last_seen) ? '长时间离线' : '未上报数据', stamp)
  }
  list.sort((a, b) => (b.ts || 0) - (a.ts || 0))
  return list
})
const alarmHigh = computed(() => alarms.value.filter((a) => a.level === 'high').length)
const alarmMid = computed(() => alarms.value.filter((a) => a.level === 'mid').length)
const alarmLow = computed(() => alarms.value.filter((a) => a.level === 'low').length)

// 底部滚动条（复制两份保证无缝循环）
const tickerItems = computed(() => {
  const base = alarms.value.slice(0, 8).map((a) => ({ ...a, msg: `${a.src}：${t(a.msg)}` }))
  if (!base.length) return [{ level: 'ok', msg: t('系统运行正常，无报警') }]
  return [...base, ...base]
})

// ---------- 年度碳排放 ----------
const carbon = computed(() => {
  // 已应用方案口径：HMI 大屏不受未保存的编排草稿影响（保存后才更新）
  const t = store.appliedTotals || {}
  const co2h = t.co2_total || 0
  const direct = t.co2_direct || 0
  const indirect = t.co2_indirect || 0
  const total = co2h + direct + indirect
  return {
    co2h, direct, indirect,
    yearly: co2h * ANNUAL_HOURS,
    directWan: (direct * ANNUAL_HOURS) / 10000,
    indirectWan: (indirect * ANNUAL_HOURS) / 10000,
    directPct: total > 0 ? (direct / total) * 100 : 0,
    indirectPct: total > 0 ? (indirect / total) * 100 : 0,
    intensity: t.intensity || 0,
    steelYear: ((t.steel_output || 0) * ANNUAL_HOURS) / 10000,
    // 火电：产量口径为发电功率(MW)，年发电量 = MW × 年运行小时 ÷ 1e5（亿 kWh）
    powerYear: ((t.steel_output || 0) * ANNUAL_HOURS) / 100000,
    captured: t.captured || 0,
  }
})

// ---------- 右侧：实时调控建议 ----------
// 开环建议：只告诉操作人员「调哪台设备、调到多少、为什么」，不自动下发设定值。
// 火电场景的产量口径是发电功率（MW）而非钢产量：强度即「度电碳排 g/kWh」
const powerScene = computed(() => store.sceneId === 'thermal-power')

// 火电场景取编排方案里的实时工序参数；其它场景以火电包出厂工况为例展示（面板标注「示例」）。
const advice = computed(() => buildHmiAdvice({
  sceneId: store.sceneId,
  units: store.sceneId === 'thermal-power' ? (store.model?.units || store.baseline?.units || []) : [],
  devices: store.allDevices,
}))
const LEVEL_LABEL = { high: '紧急', mid: '建议', low: '优化' }
function levelLabel(a) { return LEVEL_LABEL[a.level] || '建议' }

// 「已执行」标记：操作人员手动调完点一下，条目置灰排后。
// 签名带上当前值 —— 工况数值一变（说明又偏离了）标记自动失效，避免误以为一直处理完。
const doneKeys = ref(new Set())
function keyOf(a) { return `${a.id}@${a.cur}` }
function isDone(a) { return doneKeys.value.has(keyOf(a)) }
function toggleDone(a) {
  const k = keyOf(a)
  const s = new Set(doneKeys.value)
  if (s.has(k)) s.delete(k); else s.add(k)
  doneKeys.value = s
}
// 稳定化：实时读数在判据边界附近会抖动，条目忽隐忽现会让操作员无所适从。
// 每 3s 采样一次：命中累加、缺席递减，达到 2 次才上屏、连续缺席才撤下（首屏立即上屏）。
const stableHits = ref({})
function sampleAdvice(first) {
  const ids = new Set((advice.value.items || []).map((x) => x.id))
  const s = { ...stableHits.value }
  for (const id of ids) s[id] = Math.min(5, (s[id] ?? (first ? 3 : 0)) + 1)
  for (const k of Object.keys(s)) if (!ids.has(k)) s[k] = Math.max(0, (s[k] || 0) - 1)
  stableHits.value = s
}
const adviceItems = computed(() => {
  const rank = { high: 0, mid: 1, low: 2 }
  return (advice.value.items || [])
    .filter((a) => (stableHits.value[a.id] || 0) >= 2)
    .sort((x, y) => (Number(isDone(x)) - Number(isDone(y))) || ((rank[x.level] ?? 9) - (rank[y.level] ?? 9)))
})

// ---------- 数据源 / 工具函数 ----------
function lastTs(d) { const h = d.history || []; return h.length ? h[h.length - 1].t : 0 }
function relTime(ts) {
  if (!ts) return '--'
  const s = Math.max(0, Math.floor(now.value / 1000 - ts))
  if (s < 60) return `${s}s`
  if (s < 3600) return `${Math.floor(s / 60)}m`
  return `${Math.floor(s / 3600)}h`
}
function fmtTime(ts) {
  if (!ts) return '--'
  const d = new Date(ts * 1000)
  const p = (n) => String(n).padStart(2, '0')
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}
function fmtNum(v) {
  if (v == null || isNaN(v)) return '--'
  const a = Math.abs(v)
  if (a >= 1000) return v.toFixed(1)
  return v.toFixed(2)
}
function fmtWan(v) {
  if (v == null || isNaN(v)) return '--'
  return v >= 100 ? v.toFixed(1) : v.toFixed(2)
}

// ---------- 数据轮询 ----------
async function loadBox() {
  try {
    const [ov, dv] = await Promise.allSettled([api.boxOverview(), api.boxDevices()])
    if (ov.status === 'fulfilled') boxOverview.value = ov.value
    if (dv.status === 'fulfilled') boxDevicesData.value = dv.value?.devices || []
    lastRefresh.value = Math.floor(Date.now() / 1000)
  } catch (e) { /* 忽略，保持上次数据 */ }
}
onMounted(() => {
  // 主题初始值：优先「上次主题」（localStorage），否则跟随当前全局深色态（仿真模式/全局夜间主题）。
  // 后续变化由上面的 watch 接管 —— 这里是唯一的初始读取点，watch 不开 immediate，
  // 否则会把用户上次的手动选择在挂载瞬间无条件冲掉。
  let saved = null
  try { saved = localStorage.getItem('data-overview-theme') } catch (e) { /* 忽略 */ }
  if (saved === 'light' || saved === 'dark') theme.value = saved
  else theme.value = (store.simMode || themeMode.value === 'dark') ? 'dark' : 'light'
  loadBox()
  sampleAdvice(true)   // 首屏立即给出建议，不等第一次采样周期
  stopClockPoll = visiblePoll(() => { now.value = Date.now() }, 1000)
  stopBoxPoll = visiblePoll(loadBox, 10000)
  stopAdvicePoll = visiblePoll(() => sampleAdvice(false), 3000)
})
onBeforeUnmount(() => {
  if (stopClockPoll) { stopClockPoll(); stopClockPoll = null }
  if (stopBoxPoll) { stopBoxPoll(); stopBoxPoll = null }
  if (stopAdvicePoll) { stopAdvicePoll(); stopAdvicePoll = null }
})

// ---------- 数值自适应缩放（v-fit）：内容超出容器宽度时等比缩小字号，保证数字不溢出模块 ----------
function fitRoot(root) {
  let raf = null
  const measure = () => {
    raf = null
    root.querySelectorAll('[data-fit]').forEach((el) => {
      el.style.fontSize = ''
      const base = parseFloat(getComputedStyle(el).fontSize) || 16
      let size = base
      let avail = el.clientWidth
      if (avail < 1 && el.parentElement) avail = el.parentElement.clientWidth
      let guard = 0
      while (avail > 0 && el.scrollWidth > avail + 1 && size > 8 && guard++ < 12) {
        size = Math.max(8, size * avail / Math.max(1, el.scrollWidth))
        el.style.fontSize = size + 'px'
      }
    })
  }
  const schedule = () => { if (!raf) raf = requestAnimationFrame(measure) }
  let ro = null
  if (typeof ResizeObserver !== 'undefined') {
    ro = new ResizeObserver(schedule)
    ro.observe(root)
  }
  schedule()
  return { schedule, cleanup: () => { if (raf) cancelAnimationFrame(raf); if (ro) ro.disconnect() } }
}
const vFit = {
  mounted(el) {
    const api = fitRoot(el)
    el._fitSchedule = api.schedule
    el._fitCleanup = api.cleanup
  },
  updated(el) { if (el._fitSchedule) el._fitSchedule() },
  unmounted(el) { if (el._fitCleanup) el._fitCleanup() },
}
</script>

<style scoped>
/* =====================================================================
   能碳运行总览 · 工业 HMI 双主题（ANSI/ISA-101 高绩效 HMI）
   简约口径（2026-10-15 定稿）：
   - 无标题栏大标题：界面自身即入口，标题交给外层的视图标签，页面内不重复
   - 色彩克制：灰阶承担全部结构与层次；有彩色只承担「异常」语义
     —— 红 = 报警/异常（唯一强色），橙 = 警告，其余一律中性；正常态不高亮
   - 字体一致：全界面只用 --ov-fs-xl / lg / md / sm / xs 五档字号，
     字重只用 400（正文）/ 600（分组标题）/ 700（数值）；数值统一等宽字体
   - 无装饰：去掉渐变质感层、文字渐变、数字投影、毛玻璃与正常态呼吸动画
   - 圆角：HMI 内的 div 容器继承平台全局 `*{border-radius:0!important}` 直角工业风
     （div 上写的 var(--r-sm) 实际为 0，是「若全局规则放开就跟随令牌」的预期，不是 bug）；
     按钮类（.kpi/.module/.ov-back/.ai-btn）走全局按钮白名单，得到 var(--r) 6px
   ===================================================================== */
.data-overview {
  /* ----- 深色主题（默认）：VSCode 中性石墨灰，与平台深色主题同源 -----
     配色口径：中性灰阶承担全部结构与层次，有彩色只在异常时出现。 */
  --ov-bg1: #17181B;            /* 背景渐变起（中性石墨） */
  --ov-bg2: #101113;            /* 背景渐变止 */
  --ov-panel: #1F2023;          /* 卡片/面板 */
  --ov-panel-2: #26272B;        /* 次级卡片 */
  --ov-panel-3: #2F3035;        /* 三级底/输入 */
  --ov-border: rgba(255, 255, 255, .09);   /* 边框（中性发丝线） */
  --ov-border-ac: rgba(255, 255, 255, .18); /* 强调边框（中性，不用色相） */
  --ov-text: #E6E7E9;           /* 主文字（近白） */
  --ov-text-2: #A9ACB1;         /* 次要文字 */
  --ov-text-3: #85888D;         /* 弱文字 */
  --ov-faint: #65686D;          /* 更弱 */
  /* 数字统一用主文字色（不再用主题色）：数值靠字号与等宽字体区分层级，不靠颜色 */
  --ov-num: var(--ov-text);
  --ov-ok: var(--ov-text-2);   /* 正常（中性）：正常态不高亮，把注意力留给异常 */
  --ov-ab: #F26D5E;             /* 异常（报警红） */
  --ov-mid: #F0912E;            /* 一般/警告（工控橙） */
  --ov-warn: var(--ov-text-3); /* 提示（中性） */
  --ov-st: #6E7883;             /* 停机/离线（中性灰） */
  --ov-mask: rgba(255, 255, 255, 0.05);  /* 内嵌遮罩 */
  /* 语义色透明底（浅/深主题各自定义，避免 color-mix 兼容问题） */
  --ov-ok-bg: rgba(255, 255, 255, 0.07);
  --ov-ab-bg: rgba(242, 109, 94, 0.12);
  --ov-mid-bg: rgba(240, 145, 46, 0.12);
  --ov-warn-bg: rgba(255, 255, 255, 0.06);
  --ov-st-bg: rgba(110, 120, 131, 0.14);
  --ov-ab-soft: rgba(242, 109, 94, 0.08);   /* 报警脉冲弱 */
  --ov-ab-soft2: rgba(242, 109, 94, 0.18);  /* 报警脉冲强 */

  /* ----- 字体阶梯：全界面只用这 5 档字号，任何地方不写死 px -----
     xl 主数值 · lg 次级数值 · md 正文 · sm 次要说明 · xs 弱文本与单位 */
  --ov-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --ov-fs-xl: clamp(24px, 2.6vw, 34px);
  --ov-fs-lg: clamp(16px, 1.7vw, 20px);
  --ov-fs-md: 13px;
  --ov-fs-sm: 12px;
  --ov-fs-xs: 11px;

  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  /* 字体只在根上声明一次，所有子元素继承（含非全屏模式），保证全界面字体一致 */
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: var(--ov-fs-md);
  line-height: 1.5;
  /* 非全屏时顶部留足与平台工具栏的呼吸间距，全屏下恢复紧凑沉浸 */
  padding: clamp(12px, 2.2vw, 22px) clamp(12px, 2.2vw, 22px) clamp(10px, 1.6vw, 16px);
  gap: clamp(10px, 1.2vw, 14px);
}
.data-overview.fs {
  padding: clamp(8px, 1.6vw, 16px) clamp(10px, 2vw, 20px) clamp(10px, 1.6vw, 16px);
  gap: clamp(8px, 1vw, 12px);
  background: linear-gradient(180deg, var(--ov-bg1) 0%, var(--ov-bg2) 100%);
  color: var(--ov-text);
  /* 页面级禁止滚动：内容区固定一屏，任何高度下内容占满（超高部分裁剪） */
  overflow: hidden;
  touch-action: manipulation;
  -webkit-user-select: none; user-select: none;
}

/* ----- 浅色主题（冷白，与平台浅色主题一致，手动切换） ----- */
.data-overview.ov-light {
  --ov-bg1: #EEEFF1;
  --ov-bg2: #F7F8F9;
  --ov-panel: #FFFFFF;
  --ov-panel-2: #F5F6F7;
  --ov-panel-3: #EAEBED;
  --ov-border: rgba(0, 0, 0, .12);
  --ov-border-ac: rgba(0, 0, 0, .22);
  --ov-text: #1E1F22;
  --ov-text-2: #4A4D52;
  --ov-text-3: #6C6F75;
  --ov-faint: #94979D;
  --ov-num: var(--ov-text);     /* 与深色主题同口径：数值不用主题色 */
  --ov-ok: var(--ov-text-2);
  --ov-ab: #C4402F;
  --ov-mid: #C05A12;
  --ov-warn: var(--ov-text-3);
  --ov-st: #79828D;
  --ov-mask: rgba(0, 0, 0, 0.04);
  --ov-ok-bg: rgba(0, 0, 0, 0.07);
  --ov-ab-bg: rgba(196, 64, 47, 0.10);
  --ov-mid-bg: rgba(192, 90, 18, 0.10);
  --ov-warn-bg: rgba(0, 0, 0, 0.05);
  --ov-st-bg: rgba(121, 130, 141, 0.12);
  --ov-ab-soft: rgba(196, 64, 47, 0.06);
  --ov-ab-soft2: rgba(196, 64, 47, 0.14);
}

/* ================= 顶部工具条（无标题：视图名由外层标签承载） ================= */
.ov-head { display: flex; align-items: center; justify-content: flex-end; gap: 10px; position: relative; z-index: 1; }
.ov-head-right { display: flex; align-items: center; gap: 10px; flex: 0 0 auto; }

/* 全屏模式工具（头部右侧）：切换三维仿真 / 退出全屏（全屏时顶部工具栏隐藏，入口移至内容区；按钮样式见 main.css .fs-tool-btn 统一） */
.ov-fs-tools { display: inline-flex; align-items: center; gap: 6px; }

/* 明暗切换按钮 */
.ov-theme {
  display: inline-flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; padding: 0;
  background: var(--ov-panel); border: 1px solid var(--ov-border); border-radius: var(--r-sm);
  color: var(--ov-text-2); cursor: pointer;
  transition: transform .12s, border-color .12s, color .12s, background .12s;
  touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.ov-theme:active { transform: scale(0.95); }
@media (hover: hover) { .ov-theme:hover { border-color: var(--ov-border-ac); color: var(--ov-text); } }

/* ================= 页面切换动画 ================= */
/* 页面区占满头部以下全部高度：内容不足时弹性吸收，无底部空白 */
.ov-page { flex: 1 1 auto; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: clamp(8px, 1vw, 12px); position: relative; z-index: 1; }
/* 明细页空状态：弹性居中占满，避免留白 */
.ov-page > .ov-empty { flex: 1 1 auto; min-height: 0; display: flex; align-items: center; justify-content: center; }
.ovpg-enter-active, .ovpg-leave-active { transition: opacity .18s ease, transform .18s ease; }
.ovpg-enter-from { opacity: 0; transform: translateX(24px); }
.ovpg-leave-to { opacity: 0; transform: translateX(-24px); }

/* ================= 状态色编码（ISA-101：正常安静/异常高亮） ================= */
/* 状态点一律圆形：全局 `*{border-radius:0!important}` 只白名单了 [class*="dot"]，
   .lg 与工序汇总行的小方格不含 "dot" 会被直角化，这里显式补上，与 .dd-dot/.nd-dot 保持一致。 */
.lg, .mu-dots i { border-radius: 50% !important; }
.lg { display: inline-block; width: 9px; height: 9px; margin: 0 5px 0 8px; vertical-align: middle; }
.lg.ok { background: var(--ov-ok); }
.lg.ab { background: var(--ov-ab); }
.lg.mid { background: var(--ov-mid); }
.lg.st { background: var(--ov-st); }

/* ================= KPI 触控卡片 ================= */
/* HMI 全屏触控界面例外：卡片 / 模块面板按钮一律铺满父容器（全局「按钮按内容自适应、不占满父容器」规则不适用于本界面）。
   .module 显式声明 align-items:stretch，避免全局 button 规则的 align-items:center 渗入 flex column 容器，
   导致 .mod-units / .mod-grid 等子块收窄居中、指标格退化单列。
   固定尺寸的图标按钮（.fs-tool-btn / .ov-theme）与返回按钮 .ov-back 仍按内容自适应。 */
.kpi, .module { width: 100%; }
.module { align-items: stretch; justify-content: flex-start; }
.ov-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: clamp(8px, 1vw, 12px); }
.kpi {
  position: relative; display: flex; align-items: center; gap: 13px;
  min-height: 88px; padding: 13px 15px; text-align: left;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: var(--r);
  cursor: pointer; color: inherit; font-family: inherit;
  transition: transform .12s, border-color .12s, box-shadow .12s;
  touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.kpi:active { transform: scale(0.98); }
@media (hover: hover) {
  .kpi:hover { border-color: var(--ov-border-ac); }
}
.kpi.alarm { border-color: var(--ov-ab); animation: alarmPulse 1.6s ease-in-out infinite; }
@keyframes alarmPulse {
  0%, 100% { box-shadow: inset 0 0 10px var(--ov-ab-soft); }
  50% { box-shadow: inset 0 0 14px var(--ov-ab-soft2); }
}
.kpi-body { display: flex; flex-direction: column; min-width: 0; gap: 5px; }
.kpi-title { font-size: var(--ov-fs-md); font-weight: 600; color: var(--ov-text-2); letter-spacing: 1px; }
.kpi-num { font-family: var(--ov-mono); font-variant-numeric: tabular-nums; font-size: var(--ov-fs-xl); font-weight: 700; color: var(--ov-num); line-height: 1.1; }
.kpi-num em { font-style: normal; font-size: var(--ov-fs-sm); color: var(--ov-text-3); font-weight: 400; }
.kpi-num.warn { color: var(--ov-ab); }
.kpi-sub { font-size: var(--ov-fs-sm); color: var(--ov-text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-arrow { font-size: var(--ov-fs-sm); color: var(--ov-text-3); margin-top: 2px; }

/* 健康度环 */
.kpi-ring {
  flex: 0 0 auto; width: 64px; height: 64px; border-radius: 50%;
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 9px), #000 calc(100% - 8px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 9px), #000 calc(100% - 8px));
  display: flex; align-items: center; justify-content: center;
}
.kpi-ring-inner { display: flex; flex-direction: column; align-items: center; line-height: 1; }
.kpi-ring-inner b { font-family: var(--ov-mono); font-size: var(--ov-fs-lg); color: var(--ov-text); }
.kpi-ring-inner b em { font-style: normal; font-size: var(--ov-fs-xs); color: var(--ov-text-3); }
.kpi-ring-inner i { font-style: normal; font-size: var(--ov-fs-xs); color: var(--ov-text-3); margin-top: 2px; }

/* KPI 图标（中性灰底：只有「报警」才用红） */
.kpi-ico { flex: 0 0 auto; width: 50px; height: 50px; border-radius: var(--r-sm); display: flex; align-items: center; justify-content: center; font-weight: 700; font-family: var(--ov-mono); background: var(--ov-panel-2); border: 1px solid var(--ov-border); color: var(--ov-text-2); }
.kpi-ico.carbon { font-size: var(--ov-fs-md); }
.kpi-ico.box { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding: 11px; }
.kpi-ico.box i { background: var(--ov-text-3); border-radius: 2px; }
.kpi-ico.alarm { background: var(--ov-ab-bg); border: 1px solid var(--ov-ab); color: var(--ov-ab); font-size: var(--ov-fs-lg); animation: blink 1s ease-in-out infinite; }

/* ================= 模块化面板 ================= */
/* 模块区弹性占满 KPI 行与底部报警条之间的全部剩余高度（grid 行自动拉伸，面板无空白） */
.ov-modules { flex: 1 1 auto; min-height: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: clamp(8px, 1vw, 12px); }
.module {
  display: flex; flex-direction: column; gap: 10px;
  min-height: 172px; padding: 13px 15px 11px; text-align: left;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: var(--r);
  cursor: pointer; color: inherit; font-family: inherit;
  transition: transform .12s, border-color .12s;
  touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.module:active { transform: scale(0.985); }
@media (hover: hover) { .module:hover { border-color: var(--ov-border-ac); } }
.mod-head { display: flex; align-items: center; justify-content: space-between; }
.mod-title { font-size: var(--ov-fs-md); font-weight: 600; color: var(--ov-text); letter-spacing: 1px; }
.mod-title::before { content: "▍"; color: var(--ov-text-3); margin-right: 6px; }
.mod-link { font-size: var(--ov-fs-sm); color: var(--ov-text-3); }

/* 工序汇总行：弹性吸收模块内剩余高度，行数多时裁剪而非撑破 */
.mod-units { flex: 1 1 auto; min-height: 0; overflow: hidden; display: flex; flex-direction: column; gap: 6px; }
.mu-row { display: flex; align-items: center; gap: 8px; }
.mu-name { flex: 0 0 auto; max-width: 110px; font-size: var(--ov-fs-md); color: var(--ov-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mu-dots { flex: 1 1 auto; display: flex; gap: 4px; flex-wrap: wrap; min-width: 0; }
.mu-dots i { width: 9px; height: 9px; }   /* 圆角见上方「状态色编码」处的统一规则 */
/* 正常态静态不闪烁：闪烁只留给异常，避免整屏动效干扰 */
.mu-dots i.st-run { background: var(--ov-ok); }
.mu-dots i.st-abnormal { background: var(--ov-ab); animation: blink 1s ease-in-out infinite; }
.mu-dots i.st-stopped { background: var(--ov-st); }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
.mu-cnt { flex: 0 0 auto; min-width: 26px; font-family: var(--ov-mono); font-size: var(--ov-fs-md); font-weight: 700; text-align: right; }
.mu-cnt.ok { color: var(--ov-ok); } .mu-cnt.ab { color: var(--ov-ab); } .mu-cnt.st { color: var(--ov-st); }

/* 状态占比条 */
.mod-bar { display: flex; height: 7px; border-radius: var(--r-xs); overflow: hidden; background: var(--ov-mask); }
.mod-bar i { height: 100%; transition: width .5s ease; }
.mod-bar i.ok { background: var(--ov-ok); }
.mod-bar i.ab { background: var(--ov-ab); }
.mod-bar i.st { background: var(--ov-st); }
.mod-foot { display: flex; align-items: center; font-size: var(--ov-fs-sm); color: var(--ov-text-3); }
.mod-foot .lg { margin-right: 4px; }

/* 一体机模块 */
.mod-cloud { display: inline-flex; align-items: center; gap: 7px; font-size: var(--ov-fs-md); font-weight: 600; padding: 6px 11px; border-radius: var(--r-sm); border: 1px solid; width: fit-content; }
.mc-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.mod-cloud.cs-live { color: var(--ov-ok); border-color: var(--ov-border); background: var(--ov-ok-bg); }
.mod-cloud.cs-stale { color: var(--ov-mid); border-color: var(--ov-mid); background: var(--ov-mid-bg); }
.mod-cloud.cs-degraded { color: var(--ov-warn); border-color: var(--ov-warn); background: var(--ov-warn-bg); }
.mod-cloud.cs-unreachable, .mod-cloud.cs-unknown { color: var(--ov-ab); border-color: var(--ov-ab); background: var(--ov-ab-bg); }
.mod-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; }
.mg-item { display: flex; flex-direction: column; background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: var(--r-sm); padding: 8px 11px; }
.mg-item b { font-family: var(--ov-mono); font-size: var(--ov-fs-lg); font-weight: 700; color: var(--ov-text); line-height: 1.1; }
.mg-item b em { font-style: normal; font-size: var(--ov-fs-sm); color: var(--ov-text-3); font-weight: 400; }
.mg-item b.ok { color: var(--ov-ok); }
.mg-item i { font-style: normal; font-size: var(--ov-fs-sm); color: var(--ov-text-3); margin-top: 3px; }
.mod-err { font-size: var(--ov-fs-sm); color: var(--ov-ab); line-height: 1.4; }

/* ================= 底部报警滚动条 ================= */
.ov-ticker {
  display: flex; align-items: center; gap: 10px;
  background: var(--ov-panel); border: 1px solid var(--ov-border);
  border-radius: var(--r); padding: 8px 12px; min-height: 40px;
  cursor: pointer; transition: border-color .12s; touch-action: manipulation;
}
@media (hover: hover) { .ov-ticker:hover { border-color: var(--ov-border-ac); } }
.tk-label { flex: 0 0 auto; font-size: var(--ov-fs-sm); font-weight: 600; letter-spacing: 1px; color: var(--ov-text-2); padding: 2px 8px; border-right: 1px solid var(--ov-border); }
.tk-label.alarm { color: var(--ov-ab); animation: blink 1s ease-in-out infinite; }
.tk-scroll { flex: 1 1 auto; min-width: 0; overflow: hidden; }
.tk-track { display: inline-flex; white-space: nowrap; animation: tkScroll 22s linear infinite; will-change: transform; }
.tk-track.idle { animation: none; }
@keyframes tkScroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
.tk-item { font-size: var(--ov-fs-md); color: var(--ov-text-2); margin-right: 42px; }
.tk-item.lv-high { color: var(--ov-ab); }
.tk-item.lv-mid { color: var(--ov-mid); }
.tk-item.lv-low { color: var(--ov-warn); }
.tk-item.lv-ok { color: var(--ov-ok); }
.tk-arrow { flex: 0 0 auto; color: var(--ov-text-3); font-size: var(--ov-fs-md); }

/* ================= 二级页通用 ================= */
.ov-detail-head { display: flex; align-items: center; gap: 12px; }
.ov-back {
  flex: 0 0 auto; display: inline-flex; align-items: center;
  min-height: 44px; padding: 0 18px;
  background: var(--ov-panel); border: 1px solid var(--ov-border); border-radius: var(--r);
  color: var(--ov-text); font-size: var(--ov-fs-md); font-weight: 600; font-family: inherit; cursor: pointer;
  transition: transform .12s, background .12s; touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.ov-back:active { transform: scale(0.97); }
@media (hover: hover) { .ov-back:hover { background: var(--ov-panel-2); } }
.ov-detail-title { font-size: var(--ov-fs-md); font-weight: 600; letter-spacing: 1px; color: var(--ov-text); }
.ov-detail-sp { flex: 1 1 auto; }
.ov-empty { padding: 28px 10px; text-align: center; color: var(--ov-text-3); font-size: var(--ov-fs-md); }
.ov-empty.sm { padding: 12px; font-size: var(--ov-fs-sm); }

/* ================= 设备明细 ================= */
/* 工艺列表垂直滚动：工序组按内容自然高度排列（不再被均分压缩），工序多时整页可滚动，每条设备保证有完整高度显示。 */
.dt-scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto; overflow-x: hidden; display: flex; flex-direction: column; gap: clamp(8px, 1vw, 12px); padding-right: 4px; }
.dt-scroll::-webkit-scrollbar { width: 6px; }
.dt-scroll::-webkit-scrollbar-thumb { background: var(--ov-border); border-radius: 3px; }
.dt-unit {
  flex: 1 0 auto; min-height: 220px; overflow: hidden;
  display: flex; flex-direction: column;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: var(--r); padding: 11px 13px;
}
.dt-unit.alarm { border-color: var(--ov-ab); }
.dt-unit-head { flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 9px; }
.dt-unit-name { font-size: var(--ov-fs-md); font-weight: 600; color: var(--ov-text); letter-spacing: 1px; }
.dt-unit-name::before { content: "▍"; color: var(--ov-text-3); margin-right: 6px; }
.dt-unit-cnt { display: flex; gap: 10px; font-family: var(--ov-mono); font-size: var(--ov-fs-sm); }
.dt-unit-cnt i { font-style: normal; }
.dt-unit-cnt i.ok { color: var(--ov-ok); } .dt-unit-cnt i.ab { color: var(--ov-ab); } .dt-unit-cnt i.st { color: var(--ov-st); }
.dt-devices { flex: 1 1 auto; min-height: 0; overflow: visible; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 7px; align-content: start; }
.dt-dev {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: var(--r-sm); padding: 8px 10px;
}
.dt-dev.st-abnormal { border-color: var(--ov-ab); }
.dt-dev.st-stopped { opacity: 0.7; }
.dd-dot { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; }
.dt-dev.st-run .dd-dot { background: var(--ov-ok); }
.dt-dev.st-abnormal .dd-dot { background: var(--ov-ab); animation: blink 1s ease-in-out infinite; }
.dt-dev.st-stopped .dd-dot { background: var(--ov-st); }
.dd-name { flex: 0 1 auto; font-size: var(--ov-fs-md); color: var(--ov-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dd-val { flex: 0 1 auto; font-family: var(--ov-mono); font-size: var(--ov-fs-md); font-weight: 700; color: var(--ov-text); }
.dd-val em { font-style: normal; font-size: var(--ov-fs-xs); color: var(--ov-text-3); font-weight: 400; }
.dd-val.na { color: var(--ov-faint); }
.dd-st { flex: 0 0 auto; font-size: var(--ov-fs-sm); font-weight: 600; padding: 1px 9px; border-radius: var(--r-sm); border: 1px solid; background: var(--ov-mask); }
.dd-why { flex: 1 1 100%; font-size: var(--ov-fs-sm); color: var(--ov-ab); }
.dd-time { flex: 0 0 auto; font-size: var(--ov-fs-xs); color: var(--ov-faint); font-family: var(--ov-mono); }

/* ================= 碳排明细 ================= */
.dt-carbon-main {
  display: flex; flex-direction: column; align-items: center; gap: 5px;
  padding: 24px 12px;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: var(--r);
}
.dcm-label { font-size: var(--ov-fs-md); color: var(--ov-text-2); letter-spacing: 2px; }
.dcm-num { font-family: var(--ov-mono); font-size: var(--ov-fs-xl); font-weight: 700; color: var(--ov-text); line-height: 1.1; }
.dcm-num em { font-style: normal; font-size: var(--ov-fs-sm); color: var(--ov-text-3); font-weight: 400; }
.dcm-sub { font-size: var(--ov-fs-sm); color: var(--ov-text-3); font-family: var(--ov-mono); }
.dt-scopes {
  flex: 1 1 auto; min-height: 0;
  display: flex; flex-direction: column; justify-content: space-evenly; gap: 12px;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: var(--r); padding: 15px 17px;
}
.dts-row { display: grid; grid-template-columns: minmax(120px, 1fr) minmax(0, auto); gap: 6px 12px; align-items: center; }
.dts-name { font-size: var(--ov-fs-md); color: var(--ov-text-2); }
.dts-val { justify-self: end; font-family: var(--ov-mono); font-size: var(--ov-fs-md); color: var(--ov-text); }
.dts-bar { grid-column: 1 / -1; height: 9px; border-radius: var(--r-xs); background: var(--ov-mask); overflow: hidden; }
.dts-bar i { display: block; height: 100%; transition: width .6s ease; }
/* 占比条用两级中性灰区分（直接/间接），不用彩色渐变 */
.dts-bar i.direct { background: var(--ov-text-2); }
.dts-bar i.indirect { background: var(--ov-faint); }
.dt-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
.dmetric {
  display: flex; flex-direction: column; gap: 6px;
  background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: var(--r-sm); padding: 11px 13px;
}
.dm-k { font-size: var(--ov-fs-sm); color: var(--ov-text-3); }
.dmetric b { font-family: var(--ov-mono); font-size: var(--ov-fs-lg); font-weight: 700; color: var(--ov-text); }
.dmetric b em { font-style: normal; font-size: var(--ov-fs-xs); color: var(--ov-text-3); font-weight: 400; }

/* ================= 一体机明细 ================= */
/* 三张卡片弹性均分占满页面高度（首卡云端链路固定内容高度，节点/传感器卡吸收剩余） */
.dt-card {
  flex: 0 0 auto; min-height: 0;
  display: flex; flex-direction: column;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: var(--r); padding: 13px 15px;
}
.dt-card:first-child { flex: 0 0 auto; overflow: visible; }
.dt-card.cs-unreachable, .dt-card.cs-degraded { border-color: var(--ov-ab); }
.dt-card.cs-stale { border-color: var(--ov-mid); }
.dt-card-title { font-size: var(--ov-fs-md); font-weight: 600; color: var(--ov-text-2); letter-spacing: 1px; margin-bottom: 10px; padding-bottom: 7px; }
.dt-cloud { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
.dtc-item { display: flex; flex-direction: column; gap: 4px; background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: var(--r-sm); padding: 9px 11px; }
.dtc-item .k { font-size: var(--ov-fs-sm); color: var(--ov-text-3); }
.dtc-item b { font-family: var(--ov-mono); font-size: var(--ov-fs-lg); font-weight: 700; color: var(--ov-text); }
.dtc-item b.ok { color: var(--ov-ok); }
.dtc-item b.cld-live { color: var(--ov-ok); } .dtc-item b.cld-stale { color: var(--ov-mid); }
.dtc-item b.cld-degraded { color: var(--ov-warn); } .dtc-item b.cld-unreachable { color: var(--ov-ab); }
.dtc-err { margin-top: 9px; font-size: var(--ov-fs-sm); color: var(--ov-ab); line-height: 1.5; }
.dt-nodes, .dt-sensors { flex: 0 0 auto; display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 6px; }
.dt-node, .dt-sensor {
  display: flex; align-items: center; gap: 9px;
  background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: var(--r-sm); padding: 8px 11px; font-size: var(--ov-fs-md);
}
.nd-dot { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; }
.dt-node.st-run .nd-dot, .dt-sensor.st-run .nd-dot { background: var(--ov-ok); }
.dt-node.st-abnormal .nd-dot, .dt-sensor.st-abnormal .nd-dot { background: var(--ov-ab); animation: blink 1s ease-in-out infinite; }
.dt-node.st-stopped .nd-dot, .dt-sensor.st-stopped .nd-dot { background: var(--ov-st); }
.nd-name { flex: 1 1 auto; min-width: 0; color: var(--ov-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nd-model { flex: 0 1 auto; font-size: var(--ov-fs-sm); color: var(--ov-text-3); }
.nd-st { flex: 0 0 auto; font-size: var(--ov-fs-sm); font-weight: 600; padding: 2px 9px; border-radius: var(--r-sm); }
.dt-node.st-run .nd-st, .dt-sensor.st-run .nd-st { color: var(--ov-ok); background: var(--ov-ok-bg); }
.dt-node.st-abnormal .nd-st, .dt-sensor.st-abnormal .nd-st { color: var(--ov-ab); background: var(--ov-ab-bg); }
.dt-node.st-stopped .nd-st, .dt-sensor.st-stopped .nd-st { color: var(--ov-st); background: var(--ov-st-bg); }
.nd-time { flex: 0 0 auto; font-size: var(--ov-fs-xs); color: var(--ov-faint); font-family: var(--ov-mono); }

/* ================= 报警中心 ================= */
.ov-alarm-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; }
.as-item { display: flex; flex-direction: column; align-items: center; gap: 4px; background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: var(--r-sm); padding: 11px; }
.as-item b { font-family: var(--ov-mono); font-size: var(--ov-fs-xl); font-weight: 700; line-height: 1; color: var(--ov-text); }
.as-item i { font-style: normal; font-size: var(--ov-fs-sm); color: var(--ov-text-3); }
/* 只有「紧急」用红色：其余级别一律中性，避免整块统计区变彩 */
.as-item.high b { color: var(--ov-ab); }
.as-item.mid b { color: var(--ov-text-2); }
.as-item.low b { color: var(--ov-text-3); }
.dt-alarms { flex: 1 1 auto; min-height: 0; overflow: hidden; display: flex; flex-direction: column; gap: 6px; }
.dt-alarm {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-left-width: 3px; border-radius: var(--r-sm); padding: 9px 11px;
}
.dt-alarm.lv-high { border-left-color: var(--ov-ab); }
.dt-alarm.lv-mid { border-left-color: var(--ov-mid); }
.dt-alarm.lv-low { border-left-color: var(--ov-warn); }
.al-dot { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; background: var(--ov-text-3); }
.dt-alarm.lv-high .al-dot { background: var(--ov-ab); animation: blink 1s ease-in-out infinite; }
.dt-alarm.lv-mid .al-dot { background: var(--ov-text-2); }
.dt-alarm.lv-low .al-dot { background: var(--ov-text-3); }
.al-src { flex: 0 1 auto; font-size: var(--ov-fs-md); font-weight: 600; color: var(--ov-text); }
.al-msg { flex: 1 1 auto; min-width: 120px; font-size: var(--ov-fs-md); color: var(--ov-text-2); }
.al-time { flex: 0 0 auto; font-family: var(--ov-mono); font-size: var(--ov-fs-sm); color: var(--ov-faint); }
.al-ok-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: var(--ov-ok); margin-right: 8px; }

/* ================= 右侧：实时调控建议 ================= */
.ov-body { flex: 1 1 auto; min-height: 0; display: flex; gap: clamp(8px, 1vw, 12px); }
.ov-aside {
  flex: 0 0 clamp(280px, 22vw, 340px); min-width: 0;
  display: flex; flex-direction: column; gap: 8px;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: var(--r); padding: 11px 12px;
}
.adv-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.adv-title { font-size: var(--ov-fs-md); font-weight: 600; color: var(--ov-text); letter-spacing: 1px; }
.adv-title::before { content: "▍"; color: var(--ov-text-3); margin-right: 6px; }
.adv-scene { font-size: var(--ov-fs-sm); color: var(--ov-text-3); }
.adv-kpis { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 6px; }
.adv-kpi { display: flex; flex-direction: column; gap: 2px; padding: 6px 8px; background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: var(--r-sm); }
.adv-kpi i { font-style: normal; font-size: var(--ov-fs-xs); color: var(--ov-text-3); }
.adv-kpi b { font-family: var(--ov-mono); font-size: var(--ov-fs-lg); font-weight: 700; color: var(--ov-text); line-height: 1.1; }
.adv-kpi b em { font-style: normal; font-size: var(--ov-fs-xs); color: var(--ov-text-3); font-weight: 400; }
.adv-list { flex: 1 1 auto; min-height: 0; overflow-y: auto; overflow-x: hidden; display: flex; flex-direction: column; gap: 7px; padding-right: 3px; }
.adv-list::-webkit-scrollbar { width: 6px; }
.adv-list::-webkit-scrollbar-thumb { background: var(--ov-border); }
.adv-item {
  display: flex; flex-direction: column; gap: 5px;
  padding: 9px 10px; background: var(--ov-panel-2);
  border: 1px solid var(--ov-border); border-radius: var(--r-sm);
}
.adv-item.done { opacity: 0.48; }
.ai-top { display: flex; align-items: center; gap: 7px; }
.ai-lv { flex: 0 0 auto; font-size: var(--ov-fs-xs); font-weight: 600; padding: 1px 6px; border-radius: var(--r-xs); background: var(--ov-mask); color: var(--ov-text-2); }
.adv-item.lv-high .ai-lv { color: var(--ov-ab); background: var(--ov-ab-bg); }
.ai-title { flex: 1 1 auto; min-width: 0; font-size: var(--ov-fs-md); font-weight: 600; color: var(--ov-text); }
.adv-item.done .ai-title { text-decoration: line-through; }
.ai-row { display: flex; gap: 6px; font-size: var(--ov-fs-sm); line-height: 1.45; }
.ai-k { flex: 0 0 auto; color: var(--ov-text-3); }
.ai-v { flex: 1 1 auto; min-width: 0; color: var(--ov-text-2); }
.ai-row.act .ai-v { color: var(--ov-text); }
.ai-row.gain .ai-v { color: var(--ov-ok); }
.ai-cmp { display: flex; align-items: baseline; gap: 7px; font-size: var(--ov-fs-sm); }
.ai-cmp i { font-style: normal; font-size: var(--ov-fs-xs); color: var(--ov-text-3); margin-right: 3px; }
.ai-cmp b { font-family: var(--ov-mono); font-size: var(--ov-fs-md); font-weight: 700; color: var(--ov-text); }
/* 「当前值」只在紧急条目上标红，普通/优化条目保持中性 */
.adv-item.lv-high .ai-cur b { color: var(--ov-ab); }
.ai-cur em { font-style: normal; font-size: var(--ov-fs-xs); color: var(--ov-text-3); font-weight: 400; margin-left: 2px; }
.ai-go b { color: var(--ov-text-2); }
.ai-ar { color: var(--ov-text-3); font-size: var(--ov-fs-md); }
.ai-btn {
  align-self: flex-start; min-height: 40px; padding: 0 14px; margin-top: 2px;
  background: transparent; border: 1px solid var(--ov-border); border-radius: var(--r);
  color: var(--ov-text-2); font-family: inherit; font-size: var(--ov-fs-md); font-weight: 600; cursor: pointer;
  transition: transform .12s, background .12s; touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.ai-btn:active { transform: scale(0.97); }
.ai-btn.on { background: var(--ov-ok-bg); border-color: var(--ov-border-ac); color: var(--ov-text-2); }
@media (hover: hover) { .ai-btn:hover { background: var(--ov-panel-3); } }

/* 中等宽度（≤1180px）：建议栏改为置于页面下方，避免挤压左侧一屏内容 */
@media (max-width: 1180px) {
  .ov-body { flex-direction: column; }
  .ov-aside { flex: 0 0 auto; max-height: 42%; }
}

/* 小屏适配（后续放置于较小触控屏） */
@media (max-width: 720px) {
  .dt-unit-cnt { display: none; }
  .kpi { min-height: 80px; }
  .dt-devices { grid-template-columns: 1fr; }
  .mu-name { max-width: 80px; }
}

/* ================= 数值自适应缩放（data-fit 约束：单行、可收缩、溢出裁剪） ================= */
[data-fit] { min-width: 0; max-width: 100%; white-space: nowrap; overflow: hidden; }

/* 注：原先的「金属质感统一层」（面板高光渐变 + 内阴影）、标题渐变文字与数字投影
   已整体移除 —— 这些是与信息无关的装饰，层次改由背景灰阶（panel / panel-2）承担。 */
</style>
