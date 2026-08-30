<template>
  <div class="data-overview" :class="'ov-' + theme" v-fit>
    <!-- 顶部状态栏（各页面常驻） -->
    <header class="ov-head">
      <div class="ov-title">
        <span class="ov-title-text">{{ t('HMI人机交互屏') }}</span>
      </div>
      <div class="ov-head-right">
        <!-- 全屏模式：顶部工具栏已隐藏，「三维仿真」切换与「退出全屏」入口移至内容区头部 -->
        <div v-if="store.fullscreenOn" class="ov-fs-tools">
          <button type="button" class="fs-tool-btn" :title="t('切换到 3D 数字孪生')" @click="store.toggleOverview()">
            <Icon name="cube" :size="16" :stroke="1.6"/>
          </button>
          <button type="button" class="fs-tool-btn" :title="t('退出全屏')" @click="store.toggleFullscreen()">
            <Icon name="fullscreen" :size="16" :stroke="1.6"/>
          </button>
        </div>
        <button type="button" class="ov-theme" :title="theme === 'dark' ? t('切换为浅色') : t('切换为深色')" @click="toggleTheme" :aria-label="t('切换明暗主题')">
          <svg v-if="theme === 'dark'" viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <circle cx="12" cy="12" r="4.5"/>
            <path d="M12 2v2.5M12 19.5V22M4.9 4.9l1.8 1.8M17.3 17.3l1.8 1.8M2 12h2.5M19.5 12H22M4.9 19.1l1.8-1.8M17.3 6.7l1.8-1.8"/>
          </svg>
          <svg v-else viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.6 6.6 0 0 0 9.8 9.8z"/>
          </svg>
        </button>
        <span class="ov-clock">{{ clockText }}</span>
      </div>
    </header>

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
            <div class="dmetric"><span class="dm-k">{{ t('吨钢排放强度') }}</span><b data-fit>{{ fmtNum(carbon.intensity) }}<em> kgCO₂/t</em></b></div>
            <div class="dmetric"><span class="dm-k">{{ t('年产量') }}</span><b data-fit>{{ fmtWan(carbon.steelYear) }}<em> {{ t('万吨') }}</em></b></div>
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
                <span class="nd-time" v-if="d.last_seen">{{ relTime(d.last_seen) }}{{ t('前') }}</span>
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
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { api } from '../api/client'
import { t } from '../i18n'
import Icon from './Icon.vue'

const store = useSimStore()

// 年运行小时（钢铁长流程：日历 8760h 扣除检修停机约 760h）
const ANNUAL_HOURS = 8000
// 数据新鲜阈值：最后一条读数距今超过该秒数即视为停机/无数据
const STALE_AFTER = 90
// 异常判定阈值：可调设备偏离设定值；计量设备偏离历史中位
const DEVIATION_SP = 0.15
const DEVIATION_MED = 0.25

// 当前时间（每秒刷新）
const now = ref(Date.now())
let timer = null

// 一体机云端数据（10s 轮询）
const boxOverview = ref(null)
const boxDevicesData = ref([])

// ---------- 明暗主题（localStorage 记忆，默认跟随全局仿真模式） ----------
const theme = ref('dark')
function toggleTheme() {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  try { localStorage.setItem('data-overview-theme', theme.value) } catch (e) { /* 忽略 */ }
}

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
  if (d.mqtt_matched === true) {
    const ls = d.last_seen || 0
    const fresh = now.value / 1000 - ls < 120
    return fresh ? { key: 'run', label: '在线' } : { key: 'stopped', label: '离线' }
  }
  return { key: 'stopped', label: '未上报' }
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
  if (cs === 'unreachable') push('high', t('能碳一体机'), cloudError.value || '云端不可达', now.value / 1000)
  else if (cs === 'degraded') push('mid', t('能碳一体机'), '云端链路部分异常', now.value / 1000)
  else if (cs === 'stale') push('low', t('能碳一体机'), '云端数据过期', now.value / 1000)
  if (ov?.cloudcore && ov.cloudcore.available === false) push('high', t('能碳一体机'), 'CloudCore 异常', now.value / 1000)
  if (ov?.broker && ov.broker.connected !== true) push('mid', t('能碳一体机'), 'MQTT Broker 未连接', now.value / 1000)
  for (const n of boxNodes.value) {
    const s = nodeState(n).key
    if (s === 'abnormal') push('high', `${t('盒子节点')} · ${n.name}`, '节点未就绪', now.value / 1000)
    else if (s === 'stopped') push('low', `${t('盒子节点')} · ${n.name}`, '状态未知', now.value / 1000)
  }
  for (const d of boxDevices.value) {
    const s = devState(d).key
    if (s === 'stopped') push('mid', `${t('传感器')} · ${d.name}`, d.mqtt_matched ? '长时间离线' : '未上报数据', now.value / 1000)
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
  const t = store.schemeTotals || {}
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
    captured: t.captured || 0,
  }
})

// ---------- 数据源 / 工具函数 ----------
const clockText = computed(() => {
  const d = new Date(now.value)
  const p = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
})

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
  } catch (e) { /* 忽略，保持上次数据 */ }
}
let boxTimer = null

onMounted(() => {
  // 主题：优先用户记忆，否则跟随全局仿真模式（.app.sim-dark）
  let saved = null
  try { saved = localStorage.getItem('data-overview-theme') } catch (e) { /* 忽略 */ }
  if (saved === 'light' || saved === 'dark') theme.value = saved
  else theme.value = document.querySelector('.app')?.classList.contains('sim-dark') ? 'dark' : 'light'
  loadBox()
  timer = setInterval(() => { now.value = Date.now() }, 1000)
  boxTimer = setInterval(loadBox, 10000)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (boxTimer) clearInterval(boxTimer)
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
   依据 ISA-101.01 与西门子 WinCC 配色规范设计：
   - 中性炭黑底（不偏蓝）+ 低饱和灰阶文字，信息青蓝为强调/操作色（去品牌黄）
   - 颜色仅承担语义：绿=正常 · 红=报警 · 橙=警告 · 蓝=提示 · 灰=停机
   - 明暗双主题，全部颜色走 CSS 变量；正常安静、异常才高亮（情境感知）
   - 直角硬边工业风（无圆角），正文 ≥ 12px、弱文本 ≥ 11px、触控目标 ≥ 40px
   ===================================================================== */
.data-overview {
  /* ----- 深色主题（默认）：冷蓝黑金属风，与平台深色主题（#0F172A 系 + 科技蓝）一致 ----- */
  --ov-bg1: #0C1424;            /* 背景渐变起（冷蓝黑） */
  --ov-bg2: #0A101E;            /* 背景渐变止（冷蓝黑） */
  --ov-panel: #131C2E;          /* 卡片/面板（冷蓝黑） */
  --ov-panel-2: #1A2438;        /* 次级卡片 */
  --ov-panel-3: #233048;        /* 三级底/输入 */
  --ov-border: #32435F;         /* 边框（冷蓝灰） */
  --ov-border-ac: rgba(96, 165, 250, 0.38);  /* 强调边框（科技蓝） */
  --ov-text: #EAF0FA;           /* 主文字（冷白） */
  --ov-text-2: #A8B6CC;         /* 次要文字 */
  --ov-text-3: #8291AC;         /* 弱文字 */
  --ov-faint: #64738E;          /* 更弱 */
  --ov-accent: #4DA3FF;         /* 强调/操作色（平台科技蓝 #2563EB 亮化） */
  --ov-accent-soft: rgba(77, 163, 255, 0.12);   /* 强调浅底 */
  --ov-num: #7EC8FF;            /* 数字高亮（亮科技蓝） */
  --ov-ok: #34D399;             /* 正常（工控绿） */
  --ov-ab: #F26D5E;             /* 异常（报警红） */
  --ov-mid: #F0912E;            /* 一般/警告（工控橙） */
  --ov-warn: #5AA9E6;           /* 提示（信息蓝） */
  --ov-st: #6E7883;             /* 停机/离线（中性灰） */
  --ov-mask: rgba(255, 255, 255, 0.05);  /* 内嵌遮罩 */
  /* 语义色透明底（浅/深主题各自定义，避免 color-mix 兼容问题） */
  --ov-ok-bg: rgba(52, 211, 153, 0.12);
  --ov-ab-bg: rgba(242, 109, 94, 0.12);
  --ov-mid-bg: rgba(240, 145, 46, 0.12);
  --ov-warn-bg: rgba(90, 169, 230, 0.12);
  --ov-st-bg: rgba(110, 120, 131, 0.14);
  --ov-ac-bg: rgba(77, 163, 255, 0.16);
  --ov-ab-soft: rgba(242, 109, 94, 0.08);   /* 报警脉冲弱 */
  --ov-ab-soft2: rgba(242, 109, 94, 0.18);  /* 报警脉冲强 */
  /* 金属质感：面板顶部冷蓝高光线 + 微渐变 */
  --ov-meta: linear-gradient(180deg, rgba(205, 228, 255, 0.06), rgba(205, 228, 255, 0) 48%);

  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  padding: clamp(8px, 1.6vw, 16px) clamp(10px, 2vw, 20px) clamp(10px, 1.6vw, 16px);
  gap: clamp(8px, 1vw, 12px);
  background:
    radial-gradient(120% 85% at 50% -12%, rgba(77, 163, 255, 0.13), transparent 55%),
    linear-gradient(180deg, var(--ov-bg1) 0%, var(--ov-bg2) 100%);
  color: var(--ov-text);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 13px;
  line-height: 1.5;
  /* 页面级禁止滚动：内容区固定一屏，任何高度下内容占满（超高部分裁剪） */
  overflow: hidden;
  touch-action: manipulation;
  -webkit-user-select: none; user-select: none;
}

/* ----- 浅色主题（冷白，科技蓝强调，与平台浅色主题一致，手动切换） ----- */
.data-overview.ov-light {
  --ov-bg1: #EEF1F6;
  --ov-bg2: #F6F8FB;
  --ov-panel: #FFFFFF;
  --ov-panel-2: #F1F4F9;
  --ov-panel-3: #E4E9F2;
  --ov-border: #C7D0DE;
  --ov-border-ac: rgba(37, 99, 235, 0.35);
  --ov-text: #1C2433;
  --ov-text-2: #3F4A5E;
  --ov-text-3: #626F85;
  --ov-faint: #8B96A8;
  --ov-accent: #2563EB;
  --ov-accent-soft: rgba(37, 99, 235, 0.10);
  --ov-num: #1D6FD8;
  --ov-ok: #1E8E5A;
  --ov-ab: #C4402F;
  --ov-mid: #C05A12;
  --ov-warn: #2E6DA4;
  --ov-st: #79828D;
  --ov-mask: rgba(28, 36, 51, 0.04);
  --ov-ok-bg: rgba(30, 142, 90, 0.10);
  --ov-ab-bg: rgba(196, 64, 47, 0.10);
  --ov-mid-bg: rgba(192, 90, 18, 0.10);
  --ov-warn-bg: rgba(46, 109, 164, 0.10);
  --ov-st-bg: rgba(121, 130, 141, 0.12);
  --ov-ac-bg: rgba(37, 99, 235, 0.12);
  --ov-ab-soft: rgba(196, 64, 47, 0.06);
  --ov-ab-soft2: rgba(196, 64, 47, 0.14);
  --ov-meta: linear-gradient(180deg, rgba(255, 255, 255, 0.75), rgba(255, 255, 255, 0) 50%);
}

/* ================= 顶部状态栏 ================= */
.ov-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; position: relative; z-index: 1; }
.ov-title { display: flex; align-items: center; gap: 10px; min-width: 0; }
@keyframes breathe { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .35; transform: scale(.75); } }
.ov-title-text { font-size: clamp(15px, 1.8vw, 20px); font-weight: 700; letter-spacing: 2px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ov-head-right { display: flex; align-items: center; gap: 10px; flex: 0 0 auto; }
.ov-clock { font-family: ui-monospace, monospace; font-size: clamp(12px, 1.4vw, 15px); color: var(--ov-num); letter-spacing: 1px; }

/* 全屏模式工具（头部右侧）：切换三维仿真 / 退出全屏（全屏时顶部工具栏隐藏，入口移至内容区；按钮样式见 main.css .fs-tool-btn 统一） */
.ov-fs-tools { display: inline-flex; align-items: center; gap: 6px; }

/* 明暗切换按钮 */
.ov-theme {
  display: inline-flex; align-items: center; justify-content: center;
  width: 40px; height: 40px; padding: 0;
  background: var(--ov-panel); border: 1px solid var(--ov-border); border-radius: 0;
  color: var(--ov-text-2); cursor: pointer;
  transition: transform .12s, border-color .12s, color .12s, background .12s;
  touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.ov-theme:active { transform: scale(0.95); }
@media (hover: hover) { .ov-theme:hover { border-color: var(--ov-accent); color: var(--ov-accent); } }

/* ================= 页面切换动画 ================= */
/* 页面区占满头部以下全部高度：内容不足时弹性吸收，无底部空白 */
.ov-page { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; gap: clamp(8px, 1vw, 12px); position: relative; z-index: 1; }
/* 明细页空状态：弹性居中占满，避免留白 */
.ov-page > .ov-empty { flex: 1 1 auto; min-height: 0; display: flex; align-items: center; justify-content: center; }
.ovpg-enter-active, .ovpg-leave-active { transition: opacity .18s ease, transform .18s ease; }
.ovpg-enter-from { opacity: 0; transform: translateX(24px); }
.ovpg-leave-to { opacity: 0; transform: translateX(-24px); }

/* ================= 状态色编码（ISA-101：正常安静/异常高亮） ================= */
.lg { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin: 0 5px 0 8px; vertical-align: middle; }
.lg.ok { background: var(--ov-ok); }
.lg.ab { background: var(--ov-ab); }
.lg.mid { background: var(--ov-mid); }
.lg.st { background: var(--ov-st); }

/* ================= KPI 触控卡片 ================= */
.ov-kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: clamp(8px, 1vw, 12px); }
.kpi {
  position: relative; display: flex; align-items: center; gap: 13px;
  min-height: 88px; padding: 13px 15px; text-align: left;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: 0;
  cursor: pointer; color: inherit; font-family: inherit;
  transition: transform .12s, border-color .12s, box-shadow .12s;
  touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.kpi:active { transform: scale(0.98); }
@media (hover: hover) {
  .kpi:hover { border-color: var(--ov-border-ac); box-shadow: 0 2px 10px rgba(0, 0, 0, 0.10); }
}
.ov-light .kpi:hover { box-shadow: 0 2px 10px rgba(0, 0, 0, 0.08); }
.kpi.alarm { border-color: var(--ov-ab); animation: alarmPulse 1.6s ease-in-out infinite; }
@keyframes alarmPulse {
  0%, 100% { box-shadow: inset 0 0 10px var(--ov-ab-soft); }
  50% { box-shadow: inset 0 0 14px var(--ov-ab-soft2); }
}
.kpi-body { display: flex; flex-direction: column; min-width: 0; gap: 5px; }
.kpi-title { font-size: 13px; font-weight: 600; color: var(--ov-text-2); letter-spacing: 1.5px; }
.kpi-num { font-family: var(--head), ui-monospace, monospace; font-variant-numeric: tabular-nums; font-size: clamp(24px, 2.4vw, 32px); font-weight: 800; color: var(--ov-num); line-height: 1.1; }
.kpi-num em { font-style: normal; font-size: 13px; color: var(--ov-text-3); font-weight: 500; }
.kpi-num.warn { color: var(--ov-ab); }
.kpi-sub { font-size: 12px; color: var(--ov-text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.kpi-arrow { font-size: 12px; color: var(--ov-accent); margin-top: 2px; }

/* 健康度环 */
.kpi-ring {
  flex: 0 0 auto; width: 64px; height: 64px; border-radius: 50%;
  -webkit-mask: radial-gradient(farthest-side, transparent calc(100% - 9px), #000 calc(100% - 8px));
  mask: radial-gradient(farthest-side, transparent calc(100% - 9px), #000 calc(100% - 8px));
  display: flex; align-items: center; justify-content: center;
}
.kpi-ring-inner { display: flex; flex-direction: column; align-items: center; line-height: 1; }
.kpi-ring-inner b { font-family: ui-monospace, monospace; font-size: 18px; color: var(--ov-text); }
.kpi-ring-inner b em { font-style: normal; font-size: 11px; color: var(--ov-text-3); }
.kpi-ring-inner i { font-style: normal; font-size: 11px; color: var(--ov-text-3); margin-top: 2px; }

/* KPI 图标 */
.kpi-ico { flex: 0 0 auto; width: 50px; height: 50px; border-radius: 0; display: flex; align-items: center; justify-content: center; font-weight: 800; font-family: ui-monospace, monospace; }
.kpi-ico.carbon { background: var(--ov-mid-bg); color: var(--ov-mid); border: 1px solid var(--ov-mid); font-size: 15px; }
.kpi-ico.box { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding: 11px; background: var(--ov-accent-soft); border: 1px solid var(--ov-border-ac); }
.kpi-ico.box i { background: var(--ov-accent); border-radius: 0; }
.kpi-ico.alarm { background: var(--ov-ab-bg); border: 1px solid var(--ov-ab); color: var(--ov-ab); font-size: 24px; animation: alarmPulse 1.6s ease-in-out infinite; }

/* ================= 模块化面板 ================= */
/* 模块区弹性占满 KPI 行与底部报警条之间的全部剩余高度（grid 行自动拉伸，面板无空白） */
.ov-modules { flex: 1 1 auto; min-height: 0; display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: clamp(8px, 1vw, 12px); }
.module {
  display: flex; flex-direction: column; gap: 10px;
  min-height: 172px; padding: 13px 15px 11px; text-align: left;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: 0;
  cursor: pointer; color: inherit; font-family: inherit;
  transition: transform .12s, border-color .12s, box-shadow .12s;
  touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.module:active { transform: scale(0.985); }
@media (hover: hover) { .module:hover { border-color: var(--ov-border-ac); box-shadow: 0 2px 10px rgba(0, 0, 0, 0.10); } }
.mod-head { display: flex; align-items: center; justify-content: space-between; }
.mod-title { font-size: 15px; font-weight: 700; color: var(--ov-text); letter-spacing: 1px; }
.mod-title::before { content: "▍"; color: var(--ov-accent); margin-right: 6px; }
.mod-link { font-size: 12px; color: var(--ov-accent); }

/* 工序汇总行：弹性吸收模块内剩余高度，行数多时裁剪而非撑破 */
.mod-units { flex: 1 1 auto; min-height: 0; overflow: hidden; display: flex; flex-direction: column; gap: 6px; }
.mu-row { display: flex; align-items: center; gap: 8px; }
.mu-name { flex: 0 0 auto; max-width: 110px; font-size: 13px; color: var(--ov-text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mu-dots { flex: 1 1 auto; display: flex; gap: 4px; flex-wrap: wrap; min-width: 0; }
.mu-dots i { width: 10px; height: 10px; border-radius: 0; }
.mu-dots i.st-run { background: var(--ov-ok); animation: breathe 2.4s ease-in-out infinite; }
.mu-dots i.st-abnormal { background: var(--ov-ab); animation: blink 1s ease-in-out infinite; }
.mu-dots i.st-stopped { background: var(--ov-st); }
@keyframes blink { 0%, 100% { opacity: 1; } 50% { opacity: .35; } }
.mu-cnt { flex: 0 0 auto; min-width: 26px; font-family: ui-monospace, monospace; font-size: 13px; font-weight: 700; text-align: right; }
.mu-cnt.ok { color: var(--ov-ok); } .mu-cnt.ab { color: var(--ov-ab); } .mu-cnt.st { color: var(--ov-st); }

/* 状态占比条 */
.mod-bar { display: flex; height: 7px; border-radius: 0; overflow: hidden; background: var(--ov-mask); }
.mod-bar i { height: 100%; transition: width .5s ease; }
.mod-bar i.ok { background: var(--ov-ok); }
.mod-bar i.ab { background: var(--ov-ab); }
.mod-bar i.st { background: var(--ov-st); }
.mod-foot { display: flex; align-items: center; font-size: 12px; color: var(--ov-text-3); }
.mod-foot .lg { margin-right: 4px; }

/* 一体机模块 */
.mod-cloud { display: inline-flex; align-items: center; gap: 7px; font-size: 13px; font-weight: 700; padding: 6px 11px; border-radius: 0; border: 1px solid; width: fit-content; }
.mc-dot { width: 8px; height: 8px; border-radius: 50%; background: currentColor; }
.mod-cloud.cs-live { color: var(--ov-ok); border-color: var(--ov-ok); background: var(--ov-ok-bg); }
.mod-cloud.cs-stale { color: var(--ov-mid); border-color: var(--ov-mid); background: var(--ov-mid-bg); }
.mod-cloud.cs-degraded { color: var(--ov-warn); border-color: var(--ov-warn); background: var(--ov-warn-bg); }
.mod-cloud.cs-unreachable, .mod-cloud.cs-unknown { color: var(--ov-ab); border-color: var(--ov-ab); background: var(--ov-ab-bg); animation: alarmPulse 1.6s ease-in-out infinite; }
.mod-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 8px; }
.mg-item { display: flex; flex-direction: column; background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: 0; padding: 8px 11px; }
.mg-item b { font-family: ui-monospace, monospace; font-size: 19px; font-weight: 800; color: var(--ov-text); line-height: 1.1; }
.mg-item b em { font-style: normal; font-size: 13px; color: var(--ov-text-3); font-weight: 600; }
.mg-item b.ok { color: var(--ov-ok); }
.mg-item i { font-style: normal; font-size: 12px; color: var(--ov-text-3); margin-top: 3px; }
.mod-err { font-size: 12px; color: var(--ov-ab); line-height: 1.4; }

/* ================= 底部报警滚动条 ================= */
.ov-ticker {
  display: flex; align-items: center; gap: 10px;
  background: var(--ov-panel); border: 1px solid var(--ov-border);
  border-radius: 0; padding: 8px 12px; min-height: 40px;
  cursor: pointer; transition: border-color .12s; touch-action: manipulation;
}
@media (hover: hover) { .ov-ticker:hover { border-color: var(--ov-border-ac); } }
.tk-label { flex: 0 0 auto; font-size: 12px; font-weight: 800; letter-spacing: 1px; color: var(--ov-accent); padding: 2px 8px; border-right: 1px solid var(--ov-border); }
.tk-label.alarm { color: var(--ov-ab); animation: blink 1s ease-in-out infinite; }
.tk-scroll { flex: 1 1 auto; min-width: 0; overflow: hidden; }
.tk-track { display: inline-flex; white-space: nowrap; animation: tkScroll 22s linear infinite; will-change: transform; }
.tk-track.idle { animation: none; }
@keyframes tkScroll { 0% { transform: translateX(0); } 100% { transform: translateX(-50%); } }
.tk-item { font-size: 13px; color: var(--ov-text-2); margin-right: 42px; }
.tk-item.lv-high { color: var(--ov-ab); }
.tk-item.lv-mid { color: var(--ov-mid); }
.tk-item.lv-low { color: var(--ov-warn); }
.tk-item.lv-ok { color: var(--ov-ok); }
.tk-arrow { flex: 0 0 auto; color: var(--ov-accent); font-size: 16px; }

/* ================= 二级页通用 ================= */
.ov-detail-head { display: flex; align-items: center; gap: 12px; }
.ov-back {
  flex: 0 0 auto; display: inline-flex; align-items: center;
  min-height: 44px; padding: 0 18px;
  background: var(--ov-accent-soft); border: 1px solid var(--ov-border-ac); border-radius: 0;
  color: var(--ov-accent); font-size: 14px; font-weight: 700; font-family: inherit; cursor: pointer;
  transition: transform .12s, background .12s; touch-action: manipulation; -webkit-tap-highlight-color: transparent;
}
.ov-back:active { transform: scale(0.97); }
@media (hover: hover) { .ov-back:hover { background: var(--ov-ac-bg); } }
.ov-detail-title { font-size: clamp(15px, 1.6vw, 19px); font-weight: 700; letter-spacing: 1px; color: var(--ov-text); }
.ov-detail-sp { flex: 1 1 auto; }
.ov-empty { padding: 28px 10px; text-align: center; color: var(--ov-text-3); font-size: 13px; }
.ov-empty.sm { padding: 12px; font-size: 12px; }

/* ================= 设备明细 ================= */
/* 工艺列表垂直滚动：工序组按内容自然高度排列（不再被均分压缩），工序多时整页可滚动，每条设备保证有完整高度显示。 */
.dt-scroll { flex: 1 1 auto; min-height: 0; overflow-y: auto; overflow-x: hidden; display: flex; flex-direction: column; gap: clamp(8px, 1vw, 12px); padding-right: 4px; }
.dt-scroll::-webkit-scrollbar { width: 6px; }
.dt-scroll::-webkit-scrollbar-thumb { background: var(--ov-border); border-radius: 3px; }
.dt-unit {
  flex: 1 0 auto; min-height: 220px; overflow: hidden;
  display: flex; flex-direction: column;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: 0; padding: 11px 13px;
}
.dt-unit.alarm { border-color: var(--ov-ab); }
.dt-unit-head { flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 9px; }
.dt-unit-name { font-size: 15px; font-weight: 700; color: var(--ov-text); letter-spacing: 1px; }
.dt-unit-name::before { content: "▍"; color: var(--ov-accent); margin-right: 6px; }
.dt-unit-cnt { display: flex; gap: 10px; font-family: ui-monospace, monospace; font-size: 12px; }
.dt-unit-cnt i { font-style: normal; }
.dt-unit-cnt i.ok { color: var(--ov-ok); } .dt-unit-cnt i.ab { color: var(--ov-ab); } .dt-unit-cnt i.st { color: var(--ov-st); }
.dt-devices { flex: 1 1 auto; min-height: 0; overflow: visible; display: grid; grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 7px; align-content: start; }
.dt-dev {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: 0; padding: 8px 10px;
}
.dt-dev.st-abnormal { border-color: var(--ov-ab); }
.dt-dev.st-stopped { opacity: 0.7; }
.dd-dot { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; }
.dt-dev.st-run .dd-dot { background: var(--ov-ok); animation: breathe 2.4s ease-in-out infinite; }
.dt-dev.st-abnormal .dd-dot { background: var(--ov-ab); animation: blink 1s ease-in-out infinite; }
.dt-dev.st-stopped .dd-dot { background: var(--ov-st); }
.dd-name { flex: 0 1 auto; font-size: 13px; color: var(--ov-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dd-val { flex: 0 1 auto; font-family: ui-monospace, monospace; font-size: 14px; font-weight: 700; color: var(--ov-num); }
.dd-val em { font-style: normal; font-size: 11px; color: var(--ov-text-3); font-weight: 500; }
.dd-val.na { color: var(--ov-faint); }
.dd-st { flex: 0 0 auto; font-size: 12px; font-weight: 700; padding: 1px 9px; border-radius: 0; border: 1px solid; background: var(--ov-mask); }
.dd-why { flex: 1 1 100%; font-size: 12px; color: var(--ov-ab); }
.dd-time { flex: 0 0 auto; font-size: 11px; color: var(--ov-faint); font-family: ui-monospace, monospace; }

/* ================= 碳排明细 ================= */
.dt-carbon-main {
  display: flex; flex-direction: column; align-items: center; gap: 5px;
  padding: 24px 12px;
  background: var(--ov-panel);
  border: 1px solid var(--ov-mid); border-radius: 0;
}
.dcm-label { font-size: 13px; color: var(--ov-text-2); letter-spacing: 2px; }
.dcm-num { font-family: ui-monospace, monospace; font-size: clamp(36px, 5vw, 56px); font-weight: 800; color: var(--ov-mid); line-height: 1.1; }
.dcm-num em { font-style: normal; font-size: 16px; color: var(--ov-text-3); font-weight: 500; }
.dcm-sub { font-size: 12px; color: var(--ov-text-3); font-family: ui-monospace, monospace; }
.dt-scopes {
  flex: 1 1 auto; min-height: 0;
  display: flex; flex-direction: column; justify-content: space-evenly; gap: 12px;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: 0; padding: 15px 17px;
}
.dts-row { display: grid; grid-template-columns: minmax(120px, 1fr) minmax(0, auto); gap: 6px 12px; align-items: center; }
.dts-name { font-size: 13px; color: var(--ov-text-2); }
.dts-val { justify-self: end; font-family: ui-monospace, monospace; font-size: 13px; color: var(--ov-text); }
.dts-bar { grid-column: 1 / -1; height: 9px; border-radius: 0; background: var(--ov-mask); overflow: hidden; }
.dts-bar i { display: block; height: 100%; border-radius: 0; transition: width .6s ease; }
.dts-bar i.direct { background: linear-gradient(90deg, var(--ov-warn), var(--ov-mid)); }
.dts-bar i.indirect { background: linear-gradient(90deg, var(--ov-accent), var(--ov-num)); }
.dt-metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
.dmetric {
  display: flex; flex-direction: column; gap: 6px;
  background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: 0; padding: 11px 13px;
}
.dm-k { font-size: 12px; color: var(--ov-text-3); }
.dmetric b { font-family: ui-monospace, monospace; font-size: 20px; font-weight: 800; color: var(--ov-text); }
.dmetric b em { font-style: normal; font-size: 11px; color: var(--ov-text-3); font-weight: 500; }

/* ================= 一体机明细 ================= */
/* 三张卡片弹性均分占满页面高度（首卡云端链路固定内容高度，节点/传感器卡吸收剩余） */
.dt-card {
  flex: 1 1 0; min-height: 0; overflow: hidden;
  display: flex; flex-direction: column;
  background: var(--ov-panel);
  border: 1px solid var(--ov-border); border-radius: 6px; padding: 13px 15px;
}
.dt-card:first-child { flex: 0 0 auto; overflow: visible; }
.dt-card.cs-unreachable, .dt-card.cs-degraded { border-color: var(--ov-ab); }
.dt-card.cs-stale { border-color: var(--ov-mid); }
.dt-card-title { font-size: 13px; color: var(--ov-text-2); letter-spacing: 1.5px; margin-bottom: 10px; border-bottom: 1px dashed var(--ov-border); padding-bottom: 7px; }
.dt-cloud { display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 8px; }
.dtc-item { display: flex; flex-direction: column; gap: 4px; background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: 4px; padding: 9px 11px; }
.dtc-item .k { font-size: 12px; color: var(--ov-text-3); }
.dtc-item b { font-family: ui-monospace, monospace; font-size: 15px; font-weight: 700; color: var(--ov-text); }
.dtc-item b.ok { color: var(--ov-ok); }
.dtc-item b.cld-live { color: var(--ov-ok); } .dtc-item b.cld-stale { color: var(--ov-mid); }
.dtc-item b.cld-degraded { color: var(--ov-warn); } .dtc-item b.cld-unreachable { color: var(--ov-ab); }
.dtc-err { margin-top: 9px; font-size: 12px; color: var(--ov-ab); line-height: 1.5; }
.dt-nodes, .dt-sensors { flex: 1 1 auto; min-height: 0; overflow: hidden; display: flex; flex-direction: column; gap: 6px; }
.dt-node, .dt-sensor {
  display: flex; align-items: center; gap: 9px;
  background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: 4px; padding: 8px 11px; font-size: 13px;
}
.nd-dot { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; }
.dt-node.st-run .nd-dot, .dt-sensor.st-run .nd-dot { background: var(--ov-ok); animation: breathe 2.4s ease-in-out infinite; }
.dt-node.st-abnormal .nd-dot, .dt-sensor.st-abnormal .nd-dot { background: var(--ov-ab); animation: blink 1s ease-in-out infinite; }
.dt-node.st-stopped .nd-dot, .dt-sensor.st-stopped .nd-dot { background: var(--ov-st); }
.nd-name { flex: 1 1 auto; min-width: 0; color: var(--ov-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.nd-model { flex: 0 1 auto; font-size: 12px; color: var(--ov-text-3); }
.nd-st { flex: 0 0 auto; font-size: 12px; font-weight: 700; padding: 2px 9px; border-radius: 9px; }
.dt-node.st-run .nd-st, .dt-sensor.st-run .nd-st { color: var(--ov-ok); background: var(--ov-ok-bg); }
.dt-node.st-abnormal .nd-st, .dt-sensor.st-abnormal .nd-st { color: var(--ov-ab); background: var(--ov-ab-bg); }
.dt-node.st-stopped .nd-st, .dt-sensor.st-stopped .nd-st { color: var(--ov-st); background: var(--ov-st-bg); }
.nd-time { flex: 0 0 auto; font-size: 11px; color: var(--ov-faint); font-family: ui-monospace, monospace; }

/* ================= 报警中心 ================= */
.ov-alarm-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); gap: 8px; }
.as-item { display: flex; flex-direction: column; align-items: center; gap: 4px; background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-radius: 5px; padding: 11px; }
.as-item b { font-family: ui-monospace, monospace; font-size: 28px; font-weight: 800; line-height: 1; }
.as-item i { font-style: normal; font-size: 12px; color: var(--ov-text-3); }
.as-item.high b { color: var(--ov-ab); }
.as-item.mid b { color: var(--ov-mid); }
.as-item.low b { color: var(--ov-warn); }
.as-item.total b { color: var(--ov-num); }
.dt-alarms { flex: 1 1 auto; min-height: 0; overflow: hidden; display: flex; flex-direction: column; gap: 6px; }
.dt-alarm {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  background: var(--ov-panel-2); border: 1px solid var(--ov-border); border-left-width: 4px; border-radius: 4px; padding: 9px 11px;
}
.dt-alarm.lv-high { border-left-color: var(--ov-ab); }
.dt-alarm.lv-mid { border-left-color: var(--ov-mid); }
.dt-alarm.lv-low { border-left-color: var(--ov-warn); }
.al-dot { flex: 0 0 auto; width: 8px; height: 8px; border-radius: 50%; background: var(--ov-ab); }
.dt-alarm.lv-high .al-dot { background: var(--ov-ab); animation: blink 1s ease-in-out infinite; }
.dt-alarm.lv-mid .al-dot { background: var(--ov-mid); }
.dt-alarm.lv-low .al-dot { background: var(--ov-warn); }
.al-src { flex: 0 1 auto; font-size: 13px; font-weight: 600; color: var(--ov-text); }
.al-msg { flex: 1 1 auto; min-width: 120px; font-size: 13px; color: var(--ov-text-2); }
.al-time { flex: 0 0 auto; font-family: ui-monospace, monospace; font-size: 12px; color: var(--ov-faint); }
.al-ok-dot { display: inline-block; width: 9px; height: 9px; border-radius: 50%; background: var(--ov-ok); margin-right: 8px; animation: breathe 2s ease-in-out infinite; }

/* 小屏适配（后续放置于较小触控屏） */
@media (max-width: 720px) {
  .dt-unit-cnt { display: none; }
  .kpi { min-height: 80px; }
  .dt-devices { grid-template-columns: 1fr; }
  .mu-name { max-width: 80px; }
}

/* ================= 数值自适应缩放（data-fit 约束：单行、可收缩、溢出裁剪） ================= */
[data-fit] { min-width: 0; max-width: 100%; white-space: nowrap; overflow: hidden; }

/* ================= 金属质感统一层（冷蓝高光渐变 + 顶部高光线，与平台冷色系一致） ================= */
.data-overview .kpi,
.data-overview .module,
.data-overview .ov-ticker,
.data-overview .dt-unit,
.data-overview .dt-carbon-main,
.data-overview .dt-scopes,
.data-overview .dt-card,
.data-overview .dt-alarm,
.data-overview .mg-item,
.data-overview .dmetric,
.data-overview .dtc-item,
.data-overview .dt-dev,
.data-overview .dt-node,
.data-overview .dt-sensor,
.data-overview .as-item {
  background-image: var(--ov-meta);
  box-shadow: inset 0 1px 0 rgba(208, 230, 255, 0.07), 0 1px 3px rgba(0, 0, 0, 0.22);
}
.data-overview.ov-light .kpi,
.data-overview.ov-light .module,
.data-overview.ov-light .ov-ticker,
.data-overview.ov-light .dt-unit,
.data-overview.ov-light .dt-carbon-main,
.data-overview.ov-light .dt-scopes,
.data-overview.ov-light .dt-card,
.data-overview.ov-light .dt-alarm,
.data-overview.ov-light .mg-item,
.data-overview.ov-light .dmetric,
.data-overview.ov-light .dtc-item,
.data-overview.ov-light .dt-dev,
.data-overview.ov-light .dt-node,
.data-overview.ov-light .dt-sensor,
.data-overview.ov-light .as-item {
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.8), 0 1px 2px rgba(15, 23, 42, 0.06);
}

/* 标题金属渐变文字（深色主题；浅色主题恢复普通文字色） */
.data-overview .ov-title-text:not(.sub) {
  background: linear-gradient(180deg, #F2F7FF 0%, #9FC0EE 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.data-overview.ov-light .ov-title-text:not(.sub) { background: none; color: var(--ov-text); }

/* 数字金属高光（深色主题：上亮下影，增强屏幕可读性） */
.data-overview .kpi-num,
.data-overview .dcm-num,
.data-overview .dmetric b,
.data-overview .mg-item b,
.data-overview .dd-val,
.data-overview .dts-val,
.data-overview .dtc-item b,
.data-overview .as-item b,
.data-overview .kpi-ring-inner b {
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.06), 0 1px 3px rgba(0, 0, 0, 0.35);
}
.data-overview.ov-light .kpi-num,
.data-overview.ov-light .dcm-num,
.data-overview.ov-light .dmetric b,
.data-overview.ov-light .mg-item b,
.data-overview.ov-light .dd-val,
.data-overview.ov-light .dts-val,
.data-overview.ov-light .dtc-item b,
.data-overview.ov-light .as-item b,
.data-overview.ov-light .kpi-ring-inner b {
  text-shadow: none;
}
</style>
