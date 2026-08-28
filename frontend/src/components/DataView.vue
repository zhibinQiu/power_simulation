<template>
  <!-- ============ 数据分析与策略（视图 → 数据分析与策略；数据源从左侧「场景」资源树拖入，右侧策略面板联动） ============ -->
  <div class="data-view" :class="{ drop: dragOver }"
       @dragover="onDragOver" @dragleave="onDragLeave" @drop="onDrop">
    <!-- 左侧：数据源（从左侧「场景」资源树拖入，可多选） -->
    <div class="dv-sheets">
      <div class="dv-src-tip">{{ source === 'local' ? '场景设备 · 从左侧资源树拖入数据源' : '云端时序库（TDengine）' }}</div>
      <div class="dv-sel-bar">
        <button @click="selectAll" :disabled="!sheetDevs.length">全选</button>
        <button @click="clearSel" :disabled="!selIds.length">清空</button>
        <span class="dv-sel-count" :class="{ on: selIds.length >= 2 }">已选 {{ selIds.length }} 台</span>
      </div>
      <!-- 空态：拖拽引导（本地模式从左侧场景资源树拖入；云端模式列出时序设备） -->
      <div v-if="!sheetDevs.length" class="dv-drop-hint">
        <template v-if="source === 'local'">
          <svg class="dv-drop-ico" width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
          <p class="dv-drop-t1">将左侧「场景」资源树中的<br />设备拖拽到此处作为数据源</p>
          <p class="dv-drop-t2">拖入后可点击多选（同图对比 / 聚类分析）；<br />不需要时可直接拖回左侧场景移除</p>
        </template>
        <template v-else>
          <p class="dv-drop-t1">暂无云端时序设备</p>
        </template>
      </div>
      <div class="dv-sheet" :class="{ active: d.id === curId, sel: selIds.includes(d.id) }"
           v-for="d in sheetDevs" :key="d.id"
           :draggable="source === 'local'"
           :title="`${d.label || d.id} · ${d.unitName || ''} · 点击选中/取消 · 拖回场景可移除`"
           @click="toggleSel(d.id)"
           @dragstart="onSheetDragStart($event, d)" @dragend="onSheetDragEnd">
        <input type="checkbox" class="sh-cb" :checked="selIds.includes(d.id)" @click.stop="toggleSel(d.id)" />
        <span class="sh-icon" :style="{ background: d.color || '#0072BD' }"></span>
        <span class="sh-body">
          <span class="sh-top">
            <span class="sh-name">{{ d.label || d.id }}</span>
            <span class="sh-live">{{ fmt(liveOf(d)) }}</span>
          </span>
          <span class="sh-unit">{{ d.unitName || d.unitType || '' }}</span>
        </span>
        <button v-if="source === 'local'" class="sh-del" title="移出数据源" @click.stop="removeSource(d.id)">×</button>
      </div>
      <div v-if="source === 'local' && sheetDevs.length" class="dv-clear-all" @click="clearSources">
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6"/></svg>
        清空全部数据源
      </div>
    </div>

    <!-- 右侧：信息条 + 历史数据表格 -->
    <div class="dv-main">
      <!-- 表格上方统计行：设备名、属性选择已移至左侧面板，这里仅保留时间段选择 -->
      <div class="dv-stats">
        <!-- 时间段选择（快捷范围 + 自定义起止） -->
        <div class="dv-time" title="选择时间段">
          <button v-for="r in timeQuick" :key="r.v" class="dv-tq"
                  :class="{ on: !customMode && rangeQuick === r.v }" @click="setRange(r.v)">{{ r.label }}</button>
          <button class="dv-tq" :class="{ on: customMode }" @click="customMode = !customMode">自定义</button>
          <template v-if="customMode">
            <input type="datetime-local" class="dv-ti" v-model="customStart" @change="applyCustom" />
            <span class="dv-t-sep">→</span>
            <input type="datetime-local" class="dv-ti" v-model="customEnd" @change="applyCustom" />
            <button class="dv-tq" @click="clearCustom">清除</button>
          </template>
        </div>
      </div>

      <!-- 视图切换 tab（统一工具栏） -->
      <div class="dv-view-bar">
        <button class="dv-mode" :class="{ on: viewMode === 'chart' }" @click="goChart">原始数据</button>
        <button class="dv-mode" :class="{ on: viewMode === 'seq' }" @click="goSeq">时序预测</button>
        <button class="dv-mode" :class="{ on: viewMode === 'cluster' }" :disabled="selDevs.length < 2"
                title="多选 ≥2 台设备后可用" @click="goCluster">聚类分析</button>
        <button class="dv-mode" :class="{ on: viewMode === 'fit' }"
                title="联动右侧「数据拟合」策略，显示拟合方程与曲线" @click="goFit">数据拟合</button>
        <button class="dv-mode" :class="{ on: viewMode === 'opt' }"
                title="联动右侧「参数优化」策略，显示优化进度与最优参数" @click="goOpt">参数优化</button>
      </div>

      <!-- 中间：原始数据视图（含折线图、同图对比、历史列表切换） -->
      <div class="dv-chart-wrap" v-if="viewMode === 'chart'">
        <div class="dv-chart-toolbar">
          <span class="dv-chart-title">原始数据 · {{ selDevs.length }} 台设备</span>
          <div class="dv-chart-actions">
            <div v-if="selDevs.length >= 2" class="dv-mode-switch mini">
              <button class="dv-mode" :class="{ on: compareMode === 'normalized' }" @click="compareMode = 'normalized'">归一化 (%)</button>
              <button class="dv-mode" :class="{ on: compareMode === 'raw' }" @click="compareMode = 'raw'">原始值</button>
            </div>
            <button class="dv-mode" :class="{ on: chartOverlay === 'list' }" @click="toggleListOverlay">{{ chartOverlay === 'list' ? '图表' : '列表' }}</button>
          </div>
        </div>
        <div class="dv-chart-body">
          <div v-if="chartOverlay === 'list'" class="dv-list-overlay">
            <div v-for="d in selDevs" :key="d.id" class="dv-list-section">
              <div class="dv-list-head"><span class="dv-dot" :style="{ background: d.color || colorFor(d.id) }"></span>{{ d.label || d.name || d.id }}</div>
              <table class="dv-table">
                <thead>
                  <tr>
                    <th class="idx">#</th>
                    <th>时间</th>
                    <th class="num">读数<em v-if="d.unitName || d.unit"> ({{ d.unitName || d.unit }})</em></th>
                    <th class="num">变化量</th>
                    <th>状态</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(r, i) in listRowsOf(d)" :key="r.t">
                    <td class="idx">{{ i + 1 }}</td>
                    <td class="mono">{{ fmtTime(r.t) }}</td>
                    <td class="num mono">{{ fmt(r.v) }}</td>
                    <td class="num mono" :class="deltaCls(listDelta(r, d))">{{ deltaTxt(listDelta(r, d)) }}</td>
                    <td><span class="badge" :class="statusClsFor(r.v, d)">{{ statusTextFor(r.v, d) }}</span></td>
                  </tr>
                  <tr v-if="!listRowsOf(d).length">
                    <td class="empty" colspan="5">
                      <span v-if="cloudBusy">云端历史查询中…</span>
                      <span v-else-if="cloudErr">{{ cloudErr }}</span>
                      <span v-else-if="source === 'cloud'">该时间范围内无云端数据</span>
                      <span v-else-if="rangeEmpty">所选时间段内无数据</span>
                      <span v-else>暂无历史数据</span>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-if="!selDevs.length" class="dv-chart-empty">请勾选左侧设备</div>
          </div>
          <template v-else>
            <TrendChart v-if="selDevs.length === 1 && chartRows.length"
                        :data="chartRows" :color="curDev.color || '#0072BD'"
                        :height="0" :grid="true" :axis="true" />
            <MultiTrendChart v-else-if="selDevs.length >= 2 && compareSeries.length"
                             :series="compareSeries" :mode="compareMode" :height="0" :axis="true" />
            <div v-else class="dv-chart-empty">
              <span v-if="cloudBusy">云端历史查询中…</span>
              <span v-else-if="cloudErr">{{ cloudErr }}</span>
              <span v-else-if="source === 'cloud' && !sheetDevs.length">暂无云端时序设备</span>
              <span v-else-if="source === 'cloud'">该时间范围内无云端数据</span>
              <span v-else-if="rangeEmpty">所选时间段内无数据</span>
              <span v-else>暂无历史数据</span>
            </div>
            <div class="dv-chart-stats" v-if="chartStats.length">
              <div v-for="s in chartStats" :key="s.id" class="dv-stat-card" :style="{ '--c': s.color }">
                <div class="dv-stat-title">{{ s.name }}<em v-if="s.unit">({{ s.unit }})</em></div>
                <div class="dv-stat-line"><span>实时</span><b>{{ fmt(s.last) }}</b></div>
                <div class="dv-stat-line"><span>采样</span><b>{{ s.count }}</b></div>
                <div class="dv-stat-line"><span>均值</span><b>{{ fmt(s.avg) }}</b></div>
                <div class="dv-stat-line"><span>峰值</span><b>{{ fmt(s.max) }}</b></div>
                <div class="dv-stat-line"><span>谷值</span><b>{{ fmt(s.min) }}</b></div>
              </div>
            </div>
          </template>
        </div>
        <div class="dv-chart-foot" v-if="(chartRows.length || compareSeries.length) && chartOverlay !== 'list'">
          <span v-if="selDevs.length === 1">区间 {{ fmtTime(chartRows[0].t) }} → {{ fmtTime(chartRows[chartRows.length - 1].t) }} · 采样 {{ chartRows.length }} 点</span>
          <span v-else>说明：归一化模式把各设备 min-max 缩放到 0~100%，消除量纲差异以便对比趋势形态；原始值模式按各设备真实量纲同图。</span>
        </div>
      </div>

      <!-- 中间：时序预测（单设备，联动右侧「时序预测」策略） -->
      <div class="dv-chart-wrap" v-else-if="viewMode === 'seq'">
        <div class="dv-compare-bar">
          <span class="dv-compare-title">时序预测 · {{ curDev.label || curDev.id || '-' }}</span>
          <span class="dv-sub">预测未来 {{ seqForecastN }} 步趋势</span>
        </div>
        <div class="dv-compare-chart">
          <TrendChart v-if="seqRows.length" :data="seqRows" :color="curDev.color || '#0072BD'" :height="0" :grid="true" :axis="true" />
          <div v-else class="dv-chart-empty">
            <span v-if="cloudBusy">云端历史查询中…</span>
            <span v-else-if="cloudErr">{{ cloudErr }}</span>
            <span v-else-if="source === 'cloud' && !sheetDevs.length">暂无云端时序设备</span>
            <span v-else-if="source === 'cloud'">该时间范围内无云端数据</span>
            <span v-else-if="rangeEmpty">所选时间段内无数据</span>
            <span v-else>暂无历史数据</span>
          </div>
        </div>
        <div class="dv-chart-foot" v-if="seqRows.length">
          <span>区间 {{ fmtTime(seqRows[0].t) }} → {{ fmtTime(seqRows[seqRows.length - 1].t) }}</span>
          <span>采样 {{ seqRows.length }} 点（含预测）</span>
        </div>
      </div>

      <!-- 中间：聚类分析（多设备，联动右侧「聚类分析」策略） -->
      <div class="dv-chart-wrap" v-else-if="viewMode === 'cluster'">
        <div class="dv-compare-bar">
          <span class="dv-compare-title">聚类分析 · {{ selDevs.length }} 台设备</span>
          <span class="dv-sub">簇数 {{ clusterK ? clusterK + ' 组' : '自动' }}（配置见右侧属性面板）</span>
        </div>
        <div v-if="clusterBusy" class="dv-chart-empty">聚类分析中…</div>
        <div v-else-if="clusterErr" class="dv-chart-empty">{{ clusterErr }}</div>
        <div v-else-if="clusterRes" class="dv-cluster-body">
          <div class="dv-cluster-meta">
            <span>设备 {{ clusterRes.n }} 台</span>
            <span>分组 {{ clusterRes.k }} 组</span>
            <span>轮廓系数 <b class="dv-sil" :class="silCls(clusterRes.silhouette)">{{ clusterRes.silhouette }}</b></span>
            <span class="dv-cluster-note">{{ clusterRes.notes }}</span>
          </div>
          <div v-for="c in clusterRes.clusters" :key="c.cluster" class="dv-cluster-card">
            <div class="dv-cluster-head">
              <span class="dv-cluster-tag">组 {{ c.cluster + 1 }}</span>
              <span class="dv-cluster-size">{{ c.size }} 台</span>
              <span class="dv-cluster-summary">{{ c.summary }}</span>
            </div>
            <div class="dv-cluster-devs">
              <span v-for="d in c.devices" :key="d.id" class="dv-chip" :style="{ '--c': colorFor(d.id) }">
                {{ d.label }}<em v-if="d.unit">（{{ d.unit }}）</em>
              </span>
            </div>
            <div class="dv-cluster-chart">
              <MultiTrendChart :series="clusterSeriesOf(c)" mode="normalized" :height="150" :axis="true" />
            </div>
            <table class="dv-cluster-feat">
              <thead>
                <tr>
                  <th>设备</th>
                  <th v-for="f in clusterRes.feature_names" :key="f">{{ clusterRes.feature_labels[f] }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="d in c.devices" :key="d.id">
                  <td>{{ d.label }}</td>
                  <td v-for="f in clusterRes.feature_names" :key="f" class="mono">{{ clusterRes.features[d.id][f] }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>
        <div v-else class="dv-chart-empty">请多选 ≥2 台设备（进入本视图后自动执行聚类分析）</div>
      </div>

      <!-- 中间：数据拟合（联动右侧「数据拟合」策略 ai::fit，显示拟合方程与曲线） -->
      <div class="dv-chart-wrap" v-else-if="viewMode === 'fit'">
        <div class="dv-compare-bar">
          <span class="dv-compare-title">数据拟合 · 策略联动</span>
          <span v-if="fitSt" class="dv-link-tag">ai::fit{{ fitRes ? ' · ' + fitRes.method_label : ' · 未训练' }}</span>
        </div>
        <div v-if="!fitSt" class="dv-chart-empty">
          未选择「数据拟合」策略：请在右侧属性面板点击「数据拟合」，训练后此处显示拟合方程与曲线
        </div>
        <div v-else-if="!fitRes" class="dv-chart-empty">
          拟合模型尚未训练：请在右侧属性面板点击「开始训练」
        </div>
        <div v-else class="dv-fit-body">
          <div class="dv-cluster-meta">
            <span>方法 <b>{{ fitRes.method_label }}</b></span>
            <span>样本 <b>{{ fitRes.n }}</b> 点</span>
            <span>拟合优度 R² <b class="dv-sil" :class="silCls(fitRes.r2)">{{ fitRes.r2 }}</b></span>
            <span class="dv-cluster-note">{{ fitTargetLabel }}</span>
          </div>
          <div class="dv-fit-eq">拟合方程 <code>{{ fitRes.equation }}</code></div>
          <svg v-if="fitSvg" class="dv-chart-svg" :viewBox="fitSvg.viewBox">
            <g class="dv-axis">
              <line :x1="fitSvg.PL" :y1="fitSvg.Y0" :x2="fitSvg.W - fitSvg.PR" :y2="fitSvg.Y0" />
              <line :x1="fitSvg.PL" :y1="fitSvg.Y0" :x2="fitSvg.PL" :y2="fitSvg.PT" />
              <g v-for="t in fitSvg.yTicks" :key="t.y">
                <line class="dv-grid" :x1="fitSvg.PL" :y1="t.y" :x2="fitSvg.W - fitSvg.PR" :y2="t.y" />
                <text class="dv-tick" :x="fitSvg.PL - 6" :y="t.y + 3" text-anchor="end">{{ t.label }}</text>
              </g>
              <g v-for="t in fitSvg.xTicks" :key="t.x">
                <text class="dv-tick" :x="t.x" :y="fitSvg.H - 10" text-anchor="middle">{{ t.label }}</text>
              </g>
            </g>
            <path v-if="fitSvg.realPath" class="dv-fit-real" :d="fitSvg.realPath" fill="none" />
            <path v-if="fitSvg.extPath" class="dv-fit-ext" :d="fitSvg.extPath" fill="none" />
            <circle v-for="p in fitSvg.actual" :key="p.x" class="dv-fit-dot" :cx="p.x" :cy="p.y" r="2.4" />
            <text v-if="fitSvg.hasExt" class="dv-tick" :x="fitSvg.W - fitSvg.PR - 4" :y="fitSvg.PT + 2" text-anchor="end">
              虚线为外推预测段
            </text>
          </svg>
        </div>
      </div>

      <!-- 中间：参数优化（联动右侧「参数优化」策略 ai::ga/pso/rl，显示优化进度与最优参数） -->
      <div class="dv-chart-wrap" v-else>
        <div class="dv-compare-bar">
          <span class="dv-compare-title">参数优化 · 策略联动</span>
          <span v-if="optSt" class="dv-link-tag">{{ optIdLabel }} · {{ optSt.running ? '优化中' : '就绪' }}</span>
        </div>
        <div v-if="!optSt" class="dv-chart-empty">
          未选择「参数优化」策略：请在右侧属性面板点击「参数优化」并开始训练
        </div>
        <template v-else>
          <div class="dv-cluster-meta">
            <span>优化目标 <b>{{ optObjLabel }}</b></span>
            <span>迭代 <b>{{ optSt.iteration || 0 }}</b></span>
            <span>最优值 <b>{{ fmtOpt(optSt.best_fitness) }} {{ optSt.objective_unit }}</b></span>
            <span v-if="optSt.improvement_pct != null">
              较初始 <b class="dv-sil" :class="silCls(optSt.improvement_pct)">{{ optSt.improvement_pct }}%</b>
            </span>
          </div>
          <div v-if="optHist.length >= 2" class="dv-opt-body">
            <div class="dv-opt-sub">最优目标值收敛曲线（迭代 → 目标值）</div>
            <svg class="dv-chart-svg" :viewBox="optSvg.viewBox">
              <g class="dv-axis">
                <line :x1="optSvg.PL" :y1="optSvg.Y0" :x2="optSvg.W - optSvg.PR" :y2="optSvg.Y0" />
                <line :x1="optSvg.PL" :y1="optSvg.Y0" :x2="optSvg.PL" :y2="optSvg.PT" />
                <g v-for="t in optSvg.yTicks" :key="t.y">
                  <line class="dv-grid" :x1="optSvg.PL" :y1="t.y" :x2="optSvg.W - optSvg.PR" :y2="t.y" />
                  <text class="dv-tick" :x="optSvg.PL - 6" :y="t.y + 3" text-anchor="end">{{ t.label }}</text>
                </g>
                <g v-for="t in optSvg.xTicks" :key="t.x">
                  <text class="dv-tick" :x="t.x" :y="optSvg.H - 10" text-anchor="middle">{{ t.label }}</text>
                </g>
              </g>
              <path class="dv-opt-line" :d="optSvg.line" fill="none" />
              <circle v-for="p in optSvg.pts" :key="p.x" class="dv-opt-dot" :cx="p.x" :cy="p.y" r="2.2" />
            </svg>
          </div>
          <table v-if="optSt.best_params && optSt.best_params.length" class="dv-cluster-feat dv-opt-tbl">
            <thead>
              <tr>
                <th>参数</th>
                <th>当前值</th>
                <th>初始值</th>
                <th>变化</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in optSt.best_params" :key="p.dkey || (p.unit_id + ':' + p.key)">
                <td>{{ p.unit_label }} · {{ p.label }}<em v-if="p.unit">（{{ p.unit }}）</em></td>
                <td class="mono">{{ fmtOpt(p.value) }}</td>
                <td class="mono">{{ fmtOpt(p.initial) }}</td>
                <td class="mono" :class="p.delta >= 0 ? 'dv-delta-up' : 'dv-delta-dn'">{{ fmtOpt(p.delta) }}</td>
              </tr>
            </tbody>
          </table>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted } from 'vue'
import { useSimStore } from '../stores/sim'
import { api } from '../api/client'
import TrendChart from './TrendChart.vue'
import MultiTrendChart from './MultiTrendChart.vue'

const store = useSimStore()
const curId = ref(null)
const viewMode = ref('chart')   // 'chart' 原始数据（含列表切换、同图对比） / 'seq' 时序预测 / 'cluster' 聚类分析 / 'fit' 数据拟合(策略联动) / 'opt' 参数优化(策略联动)
const chartOverlay = ref('chart') // 'chart' 图表 / 'list' 列表（仅在 viewMode === 'chart' 时生效）
const source = ref('local')    // 'local' 场景设备 / 'cloud' 云端时序库（TDengine）

// ==================== 设备多选 ====================
const selIds = ref([])         // 多选设备 id 集合（同图对比 / 聚类分析使用）
// 同步中间视图勾选 → store，供右侧属性面板作为算法输入默认值
watch(selIds, (v) => { store.dvSelIds = [...v] }, { deep: true })
function toggleSel(id) {
  const i = selIds.value.indexOf(id)
  if (i >= 0) selIds.value.splice(i, 1)
  else selIds.value.push(id)
  curId.value = id
}
function selectAll() { selIds.value = sheetDevs.value.map((d) => d.id) }
function clearSel() { selIds.value = [] }
const selDevs = computed(() => sheetDevs.value.filter((d) => selIds.value.includes(d.id)))

// ==================== 时间段选择（本地/云端通用） ====================
const timeQuick = [
  { v: '10m', label: '10分钟' },
  { v: '30m', label: '30分钟' },
  { v: '1h', label: '1小时' },
  { v: '6h', label: '6小时' },
  { v: '24h', label: '24小时' },
  { v: '7d', label: '7天' },
  { v: 'all', label: '全部' },
]
const RANGE_HOURS = { '10m': 1 / 6, '30m': 0.5, '1h': 1, '6h': 6, '24h': 24, '7d': 168, 'all': null }
const rangeQuick = ref('all')
const customMode = ref(false)
const customStart = ref('')    // 'YYYY-MM-DDTHH:mm'（本地时区）
const customEnd = ref('')
const setRange = (v) => { rangeQuick.value = v; customMode.value = false }
const applyCustom = () => { customMode.value = true }
const clearCustom = () => { customStart.value = ''; customEnd.value = ''; customMode.value = false; rangeQuick.value = 'all' }
const toEpochSec = (s) => {
  if (!s) return null
  const t = new Date(s).getTime()
  return isNaN(t) ? null : t / 1000
}
// 时间段窗口 [startSec, endSec]（null 表示不限制）
const timeWindow = computed(() => {
  if (customMode.value) return [toEpochSec(customStart.value), toEpochSec(customEnd.value)]
  const h = RANGE_HOURS[rangeQuick.value]
  if (!h) return [null, null]
  const end = Date.now() / 1000
  return [end - h * 3600, end]
})
const rangeEmpty = computed(() => {
  const [s, e] = timeWindow.value
  return !(s == null && e == null)
})

// 按时间段过滤历史序列（秒级时间戳）
const histOf = (d) => {
  if (!d || !d.id) return []
  const h = source.value === 'cloud' ? cloudHistOf(d) : (store.deviceHistory[d.id] || [])
  const [s, e] = timeWindow.value
  if (s == null && e == null) return h
  return h.filter((p) => (s == null || p.t >= s) && (e == null || p.t <= e))
}

// ==================== 云端时序库（TDengine） ====================
// 盒子 MQTT data/{box}/{device}/{instance}/{property} → 云端 collector 自动写入
// TDengine → agent /api/history 降采样 → 平台转发 → 本视图拉取
const cloudDevs = ref([])      // 云端设备列表（/box/devices/realtime）
const cloudSel = ref({})       // device name -> 当前选中属性
const cloudHist = ref({})      // device name -> [{ t(秒), v }]
const cloudErr = ref('')
const cloudBusy = ref(false)

// 云端设备必须挂在盒子（node）且有 twins 属性，才能映射 data/{box}/{device}/{instance}/{property}
const cloudDevicesOf = computed(() =>
  cloudDevs.value
    .filter((d) => d.node && d.name && (d.twins || []).length)
    .map((d) => {
      const u = ((d.twins || [])[0] || {}).unit || ''
      return { ...d, id: d.name, unit: u, unitName: u, unitType: '云端时序', color: '#10A37F' }
    })
)
// 属性清单：云端 DeviceModel 的 twins.propertyName（映射 data/{box}/{device}/{instance}/{property}）
const cloudPropsOf = (d) => {
  if (!d) return []
  return [...new Set((d.twins || [])
    .map((t) => t && t.propertyName)
    .filter((x) => x && String(x).trim()))]
}
const cloudSelOf = (d) => (d && d.name ? (cloudSel.value[d.name] || cloudPropsOf(d)[0] || '') : '')
const cloudHistOf = (d) => (d && d.name ? (cloudHist.value[d.name] || []) : [])

// 进入云端时序模式：拉取云端设备列表，并自动加载当前设备历史
async function enterCloud() {
  source.value = 'cloud'
  if (!cloudDevs.value.length) await loadCloudDevices()
  // 设备列表变化会触发 watch(sheetDevs) 自动选中第一个并加载历史
  if (curDev.value && curDev.value.id) await loadCloudHist(curDev.value)
}

async function loadCloudDevices() {
  cloudBusy.value = true
  cloudErr.value = ''
  try {
    const r = await api.boxDevicesRealtime()
    cloudDevs.value = (r && r.devices) || []
    if (!cloudDevs.value.length) cloudErr.value = '云端未返回设备（cloud-agent 未部署或云端不可达）'
  } catch (e) {
    cloudErr.value = (e && e.message) ? e.message : String(e)
  } finally {
    cloudBusy.value = false
  }
}

// 从云端 TDengine 拉取指定设备/属性/时间段的历史（agent 降采样）
async function loadCloudHist(d) {
  if (!d || !d.name || !d.node) return
  const prop = (cloudSel.value[d.name] || cloudPropsOf(d)[0] || '').trim()
  if (!prop) {
    cloudHist.value[d.name] = []
    return
  }
  const [s, e] = timeWindow.value
  const end = e != null ? e * 1000 : Date.now()
  const start = s != null ? s * 1000 : end - 24 * 3600 * 1000
  cloudBusy.value = true
  cloudErr.value = ''
  try {
    const r = await api.cloudTsdbHistory({
      box: d.node, device: d.name, instance: d.name, property: prop,
      start, end, points: 600,
    })
    if (!r || r.ok === false) {
      cloudHist.value[d.name] = []
      cloudErr.value = (r && r.error) || '云端查询失败'
    } else {
      // agent 返回毫秒时间戳，统一转 epoch 秒与本视图 fmtTime 对齐；
      // 兼容毫秒/秒/数字字符串，非法时间戳丢弃（修复时间全为 1970-01-01）
      cloudHist.value[d.name] = (r.series || [])
        .map((p) => {
          const t = tsToSec(p.t)
          return t == null ? null : { t, v: p.v }
        })
        .filter(Boolean)
      if (!cloudHist.value[d.name].length) cloudErr.value = ''
    }
  } catch (e) {
    cloudHist.value[d.name] = []
    cloudErr.value = (e && e.message) ? e.message : String(e)
  } finally {
    cloudBusy.value = false
  }
}

function onCloudProp(e) {
  if (!curDev.value || !curDev.value.name) return
  cloudSel.value[curDev.value.name] = e.target.value
  loadCloudHist(curDev.value)
}

// 当前视图需要数据的设备集合（对比/聚类为多选集合，其余为当前设备）
function curIdsForView() {
  if (viewMode.value === 'cluster') return selIds.value
  return curDev.value && curDev.value.id ? [curDev.value.id] : []
}

// 列表视图：单个设备的历史时间序列（折线图的表格版）
function listRowsOf(d) {
  if (!d || !d.id) return []
  return [...histOf(d)].reverse()
}
function listDelta(r, d) {
  const rows = listRowsOf(d)
  const i = rows.findIndex((x) => x.t === r.t)
  if (i < 0 || i >= rows.length - 1) return null
  const prev = rows[i + 1]
  if (r.v == null || prev.v == null) return null
  return r.v - prev.v
}
function rangeBoundsOf(dev) {
  const s = (dev && dev.range) || ''
  const m = s.match(/(-?[\d.]+)\s*[–-]\s*(-?[\d.]+)/)
  if (!m) return null
  return { min: parseFloat(m[1]), max: parseFloat(m[2]) }
}
function statusTextFor(v, dev) {
  if (v == null) return '—'
  const rb = rangeBoundsOf(dev)
  if (!rb) return '正常'
  if (v < rb.min || v > rb.max) return '超限'
  return '正常'
}
function statusClsFor(v, dev) {
  return statusTextFor(v, dev) === '超限' ? 'warn' : 'ok'
}

// 时序预测：历史数据 + 简单外推预测（策略 ai::seq 联动）
const seqRows = computed(() => {
  const dev = curDev.value
  if (!dev || !dev.id) return []
  const hist = histOf(dev).filter((r) => r.v != null)
  if (!hist.length) return []
  const last = hist[hist.length - 1]
  const prev = hist.length > 1 ? hist[hist.length - 2] : last
  const step = last.t - prev.t || 5
  const slope = hist.length > 1 ? (last.v - hist[0].v) / (hist.length - 1) : 0
  const rows = [...hist]
  let v = last.v
  for (let i = 1; i <= 24; i++) {
    v += slope
    rows.push({ t: last.t + i * step, v: Math.round(v * 100) / 100, forecast: true })
  }
  return rows
})
const seqForecastN = computed(() => seqRows.value.filter((r) => r.forecast).length)

// 云端模式：并行拉取多台设备历史（去重）
async function ensureCloudHist(ids) {
  const uniq = [...new Set((ids || []).filter(Boolean))]
  if (!uniq.length) return
  await Promise.all(uniq.map((id) => {
    const d = sheetDevs.value.find((x) => x.id === id)
    return d ? loadCloudHist(d) : Promise.resolve()
  }))
}

// 云端模式切换设备/时间范围时自动拉取历史
// 注意：curDev 在本文件靠后声明，watch(curDev) 必须放在 curDev 声明之后（见 curDev 定义处），
// 否则 const 的 TDZ（暂时性死区）会在 setup 阶段抛 Cannot access 'curDev' before initialization。
watch(timeWindow, () => {
  if (source.value === 'cloud') ensureCloudHist(curIdsForView())
})

// ==================== 同图趋势对比 ====================
const compareMode = ref('normalized')   // 'normalized' 归一化 / 'raw' 原始值
const PALETTE = ['#0072BD', '#E07B39', '#3AA655', '#9B59B6', '#C0392B', '#16A085', '#D35400', '#2980B9', '#8E44AD', '#27AE60']
const colorFor = (id) => {
  const i = selDevs.value.findIndex((d) => d.id === id)
  return PALETTE[(i < 0 ? 0 : i) % PALETTE.length]
}
const compareSeries = computed(() => selDevs.value.map((d) => ({
  id: d.id,
  label: d.label || d.id,
  color: colorFor(d.id),
  unit: d.unitName || d.unit || '',
  pts: histOf(d),
})))
function openStrategyPanel(id) {
  // 与 App.vue openAiModel 行为一致：打开右侧对应 AI 属性面板
  if (id === 'ai::opt') {
    const cur = store.selectedStrategyId
    const curOpt = /^ai::(ga|pso|rl)$/.test(String(cur || ''))
    store.selectStrategy(curOpt ? cur : 'ai::ga')
    return
  }
  store.selectStrategy(id)
}
function goChart() {
  viewMode.value = 'chart'
  chartOverlay.value = 'chart'
}
function goSeq() {
  viewMode.value = 'seq'
  chartOverlay.value = 'chart'
  openStrategyPanel('ai::seq')
}
function goCluster() {
  viewMode.value = 'cluster'
  openStrategyPanel('ai::clu')
  if (!clusterRes.value && selDevs.value.length >= 2) runCluster()
}
function goFit() {
  viewMode.value = 'fit'
  openStrategyPanel('ai::fit')
}
function goOpt() {
  viewMode.value = 'opt'
  openStrategyPanel('ai::opt')
}
function toggleListOverlay() {
  chartOverlay.value = chartOverlay.value === 'list' ? 'chart' : 'list'
}

// 多设备列表与图表叠加统计
function statusFor(v, dev) {
  if (v == null) return { cls: 'warn', text: '无数据' }
  if (dev && dev.min != null && v < dev.min) return { cls: 'warn', text: '下限报警' }
  if (dev && dev.max != null && v > dev.max) return { cls: 'warn', text: '上限报警' }
  return { cls: 'ok', text: '正常' }
}
const multiRows = computed(() => selDevs.value.map((d) => {
  const pts = histOf(d).filter((p) => p.v != null)
  const v = pts.length ? pts[pts.length - 1].v : null
  const prev = pts.length > 1 ? pts[pts.length - 2].v : null
  const dv = v != null && prev != null ? v - prev : null
  const st = statusFor(v, d)
  return {
    id: d.id,
    name: d.label || d.name || d.id,
    color: colorFor(d.id),
    unit: d.unitName || d.unit || '',
    v,
    deltaCls: deltaCls(dv),
    deltaText: deltaTxt(dv),
    statusCls: st.cls,
    statusText: st.text,
  }
}))
const chartStats = computed(() => selDevs.value.map((d) => {
  const pts = histOf(d).filter((p) => p.v != null).map((p) => p.v)
  const count = pts.length
  const last = count ? pts[count - 1] : null
  const avg = count ? pts.reduce((a, b) => a + b, 0) / count : null
  const max = count ? Math.max(...pts) : null
  const min = count ? Math.min(...pts) : null
  return {
    id: d.id,
    name: d.label || d.name || d.id,
    unit: d.unitName || d.unit || '',
    color: colorFor(d.id),
    last,
    count,
    avg,
    max,
    min,
  }
}))

// ==================== 聚类分析 ====================
// 簇数配置统一由右侧属性面板（ai::clu）设置，此处只读 store.cluK（0 = 后端自动选 k）
const clusterK = computed(() => store.cluK || 0)
const clusterBusy = ref(false)
const clusterErr = ref('')
const clusterRes = ref(null)

async function runCluster() {
  if (selDevs.value.length < 2) return
  clusterBusy.value = true
  clusterErr.value = ''
  try {
    if (source.value === 'cloud') await ensureCloudHist(selIds.value)
    const payload = selDevs.value.map((d) => ({
      id: d.id,
      label: d.label || d.id,
      unit: d.unitName || d.unit || '',
      series: histOf(d).slice(-600).map((p) => ({ t: p.t, v: p.v })),
    }))
    const r = await api.clusterDevices(payload, clusterK.value || null)
    if (r && r.ok) clusterRes.value = r
    else clusterErr.value = (r && r.error) || '聚类分析失败'
  } catch (e) {
    clusterErr.value = (e && e.message) ? e.message : String(e)
  } finally {
    clusterBusy.value = false
  }
}
const clusterSeriesOf = (c) => (c.devices || []).map((d) => {
  const dev = sheetDevs.value.find((x) => x.id === d.id)
  return {
    id: d.id,
    label: d.label || d.id,
    color: colorFor(d.id),
    unit: d.unit || '',
    pts: histOf(dev),
  }
})
const silCls = (v) => (v >= 0.5 ? 'good' : (v >= 0.25 ? 'mid' : 'low'))

// 进入对比/聚类视图前确保云端多设备历史已加载
watch(viewMode, (m) => {
  if (source.value === 'cloud' && m === 'cluster') ensureCloudHist(selIds.value)
})

// 右侧属性面板修改「分组簇数」→ 聚类视图自动重新分析
watch(clusterK, () => {
  if (viewMode.value === 'cluster' && selDevs.value.length >= 2 && !clusterBusy.value) runCluster()
})

// 聚类视图下勾选设备变化 → 自动重新分析（配置与操作统一在右侧属性面板，中间仅展示结果）
watch(selIds, () => {
  if (viewMode.value === 'cluster' && selDevs.value.length >= 2 && !clusterBusy.value) runCluster()
}, { deep: true })

// ==================== 策略联动：数据拟合（ai::fit） / 参数优化（ai::ga/pso/rl） ====================
// 右侧属性面板选中策略后，本数据区自动切换对应视图；数据来自 store.optimizers（每 3s 轮询刷新）
const STRAT_OPT_RE = /^ai::(ga|pso|rl)$/
const fitSt = computed(() => store.optimizers['ai::fit'] || null)
const fitRes = computed(() => (fitSt.value && fitSt.value.fit) || null)
const fitCurve = computed(() => (fitSt.value && Array.isArray(fitSt.value.curve) ? fitSt.value.curve : []))
const fitTargetLabel = computed(() => {
  const st = fitSt.value
  if (!st) return ''
  if (Array.isArray(st.targets)) {
    const t = st.targets.find((x) => x.id === st.target)
    if (t) return `拟合对象：${t.label}`
  }
  return st.target || ''
})

// 拟合曲线 SVG（实线 = 实测段，虚线 = 外推预测段；圆点 = 实际采样）
const fmtAxis = (v) => {
  if (v == null || !isFinite(v)) return ''
  const a = Math.abs(v)
  if (a >= 1e4) return (v / 1e4).toFixed(1) + '万'
  if (a >= 1e3) return (v / 1e3).toFixed(1) + 'k'
  if (a >= 100) return v.toFixed(0)
  if (a >= 1) return v.toFixed(1)
  return v.toExponential(1)
}
const fitSvg = computed(() => {
  const pts = fitCurve.value
  if (!pts.length) return null
  const W = 880, H = 260, PL = 52, PR = 18, PT = 26, PB = 34
  const xs = pts.map((p) => p.x)
  const vals = pts.filter((p) => p.y != null).map((p) => p.y)
    .concat(pts.map((p) => p.yfit).filter((v) => v != null))
  const x0 = Math.min(...xs), x1 = Math.max(...xs)
  let y0 = Math.min(...vals), y1 = Math.max(...vals)
  if (!(y1 > y0)) { y0 -= 1; y1 += 1 }
  const dx = (x1 - x0) || 1, dy = (y1 - y0) || 1
  const X = (x) => PL + ((x - x0) / dx) * (W - PL - PR)
  const Y = (y) => H - PB - ((y - y0) / dy) * (H - PT - PB)
  const firstExt = pts.findIndex((p) => p.y == null)  // 外推预测起点
  const realPts = (firstExt < 0 ? pts : pts.slice(0, firstExt)).filter((p) => p.yfit != null)
  const extPts = firstExt >= 0 ? pts.slice(firstExt).filter((p) => p.yfit != null) : []
  const path = (arr) => arr.map((p, i) => `${i ? 'L' : 'M'}${X(p.x).toFixed(1)},${Y(p.yfit).toFixed(1)}`).join(' ')
  const yTicks = []
  for (let i = 0; i <= 4; i++) {
    const v = y0 + (dy * i) / 4
    yTicks.push({ y: Y(v).toFixed(1), label: fmtAxis(v) })
  }
  const xTicks = []
  const xStepN = Math.min(6, pts.length)
  for (let i = 0; i <= xStepN; i++) {
    const xi = x0 + (dx * i) / xStepN
    xTicks.push({ x: X(xi).toFixed(1), label: `${Math.round(xi)}` })
  }
  return {
    W, H, PL, PR, PT, PB, viewBox: `0 0 ${W} ${H}`,
    Y0: Y(y0).toFixed(1),
    realPath: path(realPts), extPath: path(extPts),
    actual: pts.filter((p) => p.y != null).map((p) => ({ x: X(p.x).toFixed(1), y: Y(p.y).toFixed(1) })),
    yTicks, xTicks, hasExt: extPts.length >= 2,
  }
})

// 参数优化视图
const optSt = computed(() =>
  STRAT_OPT_RE.test(store.selectedStrategyId || '') ? (store.optimizers[store.selectedStrategyId] || null) : null)
const optHist = computed(() => (optSt.value && Array.isArray(optSt.value.history) ? optSt.value.history : []))
const optIdLabel = computed(() => {
  const id = store.selectedStrategyId || ''
  return id === 'ai::ga' ? '遗传算法' : id === 'ai::pso' ? '粒子群' : id === 'ai::rl' ? '强化学习' : id
})
const optObjLabel = computed(() => {
  const st = optSt.value
  if (!st) return ''
  const o = (st.objectives || []).find((x) => x.key === st.objective)
  return o ? o.label : (st.objective || '')
})
const fmtOpt = (v) => (v == null || isNaN(v) ? '—' : Number(v).toFixed(4).replace(/\.?0+$/, ''))
const optSvg = computed(() => {
  const h = optHist.value
  if (h.length < 2) return null
  const W = 880, H = 200, PL = 52, PR = 18, PT = 20, PB = 30
  const y0 = Math.min(...h), y1 = Math.max(...h)
  const ySpan = (y1 - y0) || (Math.abs(y0) * 0.1 + 1)
  const Y = (v) => H - PB - ((v - y0) / ySpan) * (H - PT - PB)
  const X = (i) => PL + (i / (h.length - 1)) * (W - PL - PR)
  const yTicks = []
  for (let i = 0; i <= 4; i++) {
    const v = y0 + (ySpan * i) / 4
    yTicks.push({ y: Y(v).toFixed(1), label: fmtAxis(v) })
  }
  const xTicks = []
  for (let i = 0; i <= 4; i++) {
    const idx = Math.round((i / 4) * (h.length - 1))
    xTicks.push({ x: X(idx).toFixed(1), label: `#${idx + 1}` })
  }
  return {
    W, H, PL, PR, PT, viewBox: `0 0 ${W} ${H}`,
    Y0: Y(y0).toFixed(1),
    line: h.map((v, i) => `${i ? 'L' : 'M'}${X(i).toFixed(1)},${Y(v).toFixed(1)}`).join(' '),
    pts: h.map((v, i) => ({ x: X(i).toFixed(1), y: Y(v).toFixed(1) })),
    yTicks, xTicks,
  }
})

// 右侧属性面板选中策略 → 数据区自动跟随（聚类 / 预测趋势 / 拟合 / 参数优化）
function syncStrategyMode(id) {
  if (id === 'ai::clu') {
    viewMode.value = 'cluster'
    if (selDevs.value.length >= 2) runCluster()
  } else if (id === 'ai::seq') {
    viewMode.value = 'seq'
    chartOverlay.value = 'chart'
  } else if (id === 'ai::fit') {
    viewMode.value = 'fit'
  } else if (STRAT_OPT_RE.test(id || '')) {
    viewMode.value = 'opt'
  }
}
watch(() => store.selectedStrategyId, (id) => {
  if (!store.dataViewOn) return
  syncStrategyMode(id)
})

// 关闭数据视图，返回数字孪生
const close = () => store.toggleDataView()

// 重新拉取设备历史数据（供视图工具栏「刷新数据」按钮调用）
async function refresh() {
  try {
    if (source.value === 'cloud') {
      await loadCloudDevices()
      await ensureCloudHist(curIdsForView())
      return
    }
    const hist = await api.getDeviceHistory()
    if (hist && hist.history) store.deviceHistory = hist.history
    ensureLocalHist()   // 后端/MQTT 无上报数据时生成模拟历史兜底，保证本地演示可用
  } catch (e) { console.warn('刷新工况数据失败：', e) }
}

// ==================== 本地模式：历史数据兜底 ====================
// 后端实时通道（realtime.py / mqtt_source.py）仅保留 MQTT 真实上报的读数，
// 未连接云端或暂无上报时 DEVICE_HISTORY 为空 → 拖入设备后表格/曲线恒为「暂无历史数据」。
// 此处对拖入设备生成一段模拟历史序列（基线=实时读数/出厂读数 + 周期性波动 + 噪声，
// 5s 采样 × 120 点 ≈ 最近 10 分钟，与本地内存缓冲口径一致）；仅在该设备原本无任何
// 历史点时生效，真实数据流（MQTT/WS 推送）到位后不覆盖。
function ensureLocalHist() {
  if (source.value !== 'local') return
  const devs = sheetDevs.value
  if (!devs.length) return
  const now = Date.now() / 1000
  const STEP = 5
  const N = 120
  for (const d of devs) {
    const buf = store.deviceHistory[d.id]
    if (buf && buf.length) continue
    const base = store.deviceLiveOf(d.id) != null ? store.deviceLiveOf(d.id) : (d.reading != null ? d.reading : 50)
    const amp = Math.max(Math.abs(base) * 0.04, 0.5)
    const seed = (d.id || '').length + 1
    const pts = []
    for (let i = 0; i < N; i++) {
      const t = now - (N - 1 - i) * STEP
      const wave = amp * Math.sin(i / 9 + seed) + amp * 0.5 * Math.sin(i / 3.1 + seed * 1.7)
      const noise = (Math.random() - 0.5) * amp * 0.5
      pts.push({ t, v: Math.round((base + wave + noise) * 100) / 100 })
    }
    store.deviceHistory[d.id] = pts
  }
}

// 本地模式：数据源为从左侧「场景」资源树拖入的设备（存于 store，跨视图保留；拖回场景即移除）；云端模式用云端时序设备
const sources = computed(() => store.dvSources)
const sheetDevs = computed(() => {
  if (source.value === 'cloud') return cloudDevicesOf.value
  return sources.value
})

// ==================== 本地数据源：从左侧「场景」资源树拖入（整个区域均可拖放） ====================
const dragOver = ref(false)
function onDragOver(e) {
  e.preventDefault()
  if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  dragOver.value = true
}
function onDragLeave(e) {
  // 鼠标在子元素间移动也会触发 dragleave，仅当真正离开容器时才清除高亮
  if (e.currentTarget && e.relatedTarget && e.currentTarget.contains(e.relatedTarget)) return
  dragOver.value = false
}
function onDrop(e) {
  e.preventDefault()
  dragOver.value = false
  try {
    const raw = e.dataTransfer.getData('application/x-dv-device')
    if (!raw) return
    const src = JSON.parse(raw)
    if (!src || !src.id) return
    if (sources.value.some((s) => s.id === src.id)) {
      // 已存在：直接设为当前并选中
      if (!selIds.value.includes(src.id)) selIds.value.push(src.id)
      curId.value = src.id
      return
    }
    store.addDvSource(src)
    selIds.value.push(src.id)
    curId.value = src.id
    ensureLocalHist()   // 无真实上报数据时立即生成模拟历史，拖入即可见
  } catch (err) { console.warn('拖入数据源解析失败：', err) }
}
function removeSource(id) { store.removeDvSource(id) }
function clearSources() { store.clearDvSources() }

// sheet 拖回场景：从数据源列表拖回左侧「场景」资源树即移出数据源
function onSheetDragStart(e, d) {
  if (!e.dataTransfer || source.value !== 'local') return
  e.dataTransfer.effectAllowed = 'move'
  e.dataTransfer.setData('application/x-dv-device', JSON.stringify({ ...d, _back: true }))
  e.dataTransfer.setData('application/x-dv-remove', '1')
  e.dataTransfer.setData('text/plain', d.label || d.id)
}
function onSheetDragEnd() { dragOver.value = false }

const curDev = computed(() => {
  const devs = sheetDevs.value
  if (!devs.length) return {}
  return devs.find((d) => d.id === curId.value) || devs[0]
})

// 当前选中传感器切换时跟随
watch(sheetDevs, (devs) => {
  const ids = new Set(devs.map((d) => d.id))
  // 数据源被移除（× 按钮 / 拖回场景）后同步清理多选与当前设备
  if (selIds.value.length) selIds.value = selIds.value.filter((x) => ids.has(x))
  if (!curId.value || !ids.has(curId.value)) {
    curId.value = devs.length ? devs[0].id : null
  }
}, { immediate: true })

// 云端模式切换当前设备时自动拉取历史（必须位于 curDev 声明之后）
watch(curDev, (d) => {
  if (source.value === 'cloud' && d && d.id) loadCloudHist(d)
})

// 当前传感器历史序列（倒序：最新在上，贴近实时监控）
const rows = computed(() => [...histOf(curDev.value)].reverse())

// 折线图序列（正序：时间从左到右；过滤空值避免断点）
const chartRows = computed(() => [...histOf(curDev.value)].filter((r) => r.v != null))

const curLive = computed(() => {
  const dev = curDev.value
  if (!dev || dev.id == null) return null
  if (source.value === 'cloud') {
    const prop = cloudSel.value[dev.name] || cloudPropsOf(dev)[0]
    const tw = prop ? (dev.twins || []).find((x) => x.propertyName === prop) : null
    if (tw && tw.reported != null && !tw.invalid) return tw.reported
    const h = cloudHistOf(dev)
    return h.length ? h[h.length - 1].v : null
  }
  // 与左侧 liveOf 保持一致：无实时读数时回退到设备出厂读数，避免显示 '—'
  return store.deviceLiveOf(dev.id) != null ? store.deviceLiveOf(dev.id) : (dev.reading != null ? dev.reading : null)
})
const liveOf = (d) => {
  if (source.value === 'cloud') {
    const prop = cloudSel.value[d.name] || cloudPropsOf(d)[0]
    const tw = prop ? (d.twins || []).find((x) => x.propertyName === prop) : null
    if (tw && tw.reported != null && !tw.invalid) return tw.reported
    const h = cloudHistOf(d)
    return h.length ? h[h.length - 1].v : null
  }
  return store.deviceLiveOf(d.id) != null ? store.deviceLiveOf(d.id) : d.reading
}

const fmt = (v) => (v == null || isNaN(v) ? '—' : Number(v).toFixed(2).replace(/\.?0+$/, ''))

const avg = computed(() => {
  const a = rows.value.filter((r) => r.v != null)
  if (!a.length) return null
  return a.reduce((s, r) => s + r.v, 0) / a.length
})
const max = computed(() => {
  const a = rows.value.filter((r) => r.v != null)
  return a.length ? Math.max(...a.map((r) => r.v)) : null
})
const min = computed(() => {
  const a = rows.value.filter((r) => r.v != null)
  return a.length ? Math.min(...a.map((r) => r.v)) : null
})

// TDengine/agent 时间戳 -> epoch 秒：兼容毫秒（≈1.7e12）、秒（≈1.7e9）与数字字符串；
// 非法/零值时间戳返回 null（避免上游字段缺失导致显示 1970-01-01）
const tsToSec = (v) => {
  if (v == null || v === '') return null
  const n = Number(v)
  if (!Number.isFinite(n) || n <= 0) return null
  return n >= 1e12 ? n / 1000 : n
}

// 时间戳（epoch 秒）-> 本地时间字符串；无效时间戳显示 '--'
function fmtTime(t) {
  const n = Number(t)
  if (!Number.isFinite(n) || n <= 0) return '--'
  const d = new Date(n * 1000)
  const p = (x) => String(x).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

// 与上一采样点的差值
const delta = (r, i) => {
  if (i >= rows.value.length - 1) return null
  const prev = rows.value[i + 1]
  if (r.v == null || prev.v == null) return null
  return r.v - prev.v
}
const deltaTxt = (d) => (d == null ? '—' : `${d >= 0 ? '+' : ''}${fmt(d)}`)
const deltaCls = (d) => (d == null ? '' : (d > 0 ? 'up' : (d < 0 ? 'down' : '')))

// 状态：解析量程字符串（如 "100–1000 m³/h"）判断是否超限
const rangeBounds = computed(() => {
  const s = (curDev.value && curDev.value.range) || ''
  const m = s.match(/(-?[\d.]+)\s*[–-]\s*(-?[\d.]+)/)
  if (!m) return null
  return { min: parseFloat(m[1]), max: parseFloat(m[2]) }
})
const statusText = (v) => {
  if (v == null) return '—'
  const rb = rangeBounds.value
  if (!rb) return '正常'
  if (v < rb.min || v > rb.max) return '超限'
  return '正常'
}
const statusCls = (v) => (statusText(v) === '超限' ? 'warn' : 'ok')

onMounted(() => {
  // 已选中 AI 策略时，打开视图即联动到对应数据区（聚类 / 预测趋势 / 拟合 / 参数优化）
  syncStrategyMode(store.selectedStrategyId)
  // 拉取一次本地历史，保证拖入数据源后立即可查看
  refresh()
})

defineExpose({ close, refresh })
</script>

<style scoped>
.data-view {
  position: absolute; inset: 0;
  display: flex; flex-direction: row;
  background: var(--panel-2);
  color: var(--text);
  user-select: none;
}
/* ---- 右侧主区域（统计行 + 表格） ---- */
.dv-main { display: flex; flex-direction: column; flex: 1 1 auto; min-width: 0; }
/* ---- 表格上方统计行（关闭/刷新等操作已由顶栏工具栏提供） ---- */
.dv-stats {
  display: flex; align-items: center; gap: 12px;
  padding: 7px 14px;
  background: var(--bar);
  border-bottom: 1px solid var(--border);
  flex: 0 0 auto;
  color: var(--muted); font-size: 11px;
  flex-wrap: wrap;
}
.dv-stats b { color: var(--text); font-family: var(--mono); margin-left: 2px; }
/* .dv-dot 仍用于列表标题 */
.dv-dot { width: 6px; height: 6px; border-radius: 2px; flex: 0 0 auto; }
.dv-sub { color: var(--muted); font-size: 11px; }
.dv-live2 { display: flex; align-items: baseline; gap: 4px; margin-left: auto; }
.dv-live-v { font-size: 16px; font-weight: 500; color: var(--accent); font-family: var(--mono); }
/* ---- 数据源切换（场景设备 / 云端时序） ---- */
.dv-source { display: flex; flex: 0 0 auto; border: 1px solid var(--border); border-radius: 5px; overflow: hidden; background: var(--panel); }
.dv-src { padding: 2px 10px; font-size: 11px; line-height: 16px; color: var(--muted); background: transparent; border: none; cursor: pointer; }
.dv-src + .dv-src { border-left: 1px solid var(--border); }
.dv-src:hover { color: var(--text); }
.dv-src.on { background: var(--accent-l); color: var(--accent-d); font-weight: 500; }
/* ---- 时间段选择 ---- */
.dv-time { display: flex; align-items: center; gap: 4px; flex: 0 0 auto; border: 1px solid var(--border); border-radius: 5px; padding: 1px 4px; background: var(--panel); }
.dv-tq { padding: 2px 6px; font-size: 11px; line-height: 16px; color: var(--muted); background: transparent; border: none; cursor: pointer; border-radius: 3px; }
.dv-tq:hover { color: var(--text); }
.dv-tq.on { background: var(--accent-l); color: var(--accent-d); font-weight: 500; }
.dv-ti {
  padding: 1px 4px; font-size: 11px; color: var(--text);
  background: var(--panel-3); border: 1px solid var(--border); border-radius: 4px;
  font-family: var(--mono);
}
.dv-t-sep { color: var(--faint); }
/* ---- 列表 / 折线图 / 对比 / 聚类 切换 ---- */
.dv-mode-switch { display: flex; flex: 0 0 auto; border: 1px solid var(--border); border-radius: 5px; overflow: hidden; background: var(--panel); }
.dv-mode { padding: 2px 10px; font-size: 11px; line-height: 16px; color: var(--muted); background: transparent; border: none; cursor: pointer; }
.dv-mode + .dv-mode { border-left: 1px solid var(--border); }
.dv-mode:hover:not(:disabled) { color: var(--text); }
.dv-mode.on { background: var(--accent-l); color: var(--accent-d); font-weight: 500; }
.dv-mode:disabled { opacity: .4; cursor: not-allowed; }
/* ---- 视图切换 tab（统一工具栏） ---- */
.dv-view-bar { flex: 0 0 auto; display: flex; align-items: center; gap: 6px; padding: 10px 12px 0; }
/* ---- 折线图 / 聚类 公共容器 ---- */
.dv-chart-wrap { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; padding: 12px 16px 6px; background: var(--panel); }
.dv-chart-toolbar { flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; padding-bottom: 8px; }
.dv-chart-title { font-size: 12px; color: var(--text); font-weight: 500; }
.dv-chart-actions { display: flex; align-items: center; gap: 8px; }
.dv-chart-actions .dv-mode-switch.mini { gap: 2px; }
.dv-chart-actions .dv-mode-switch.mini .dv-mode { border-radius: 4px; padding: 2px 8px; font-size: 10px; }
.dv-chart-body { flex: 1 1 auto; min-height: 0; position: relative; display: flex; flex-direction: column; }
.dv-chart-body :deep(.trend) { flex: 1 1 auto; min-height: 0; }
.dv-chart-body :deep(.multi-trend) { height: 100%; display: flex; flex-direction: column; }
.dv-chart-body :deep(.cv) { flex: 1 1 auto; }
.dv-chart-empty { flex: 1; display: grid; place-items: center; color: var(--faint); font-size: 12px; }
.dv-chart-foot { display: flex; align-items: center; gap: 16px; padding: 6px 2px 0; color: var(--muted); font-size: 11px; font-family: var(--mono); }
/* ---- 折线图统计卡片（叠加在图表右上角） ---- */
.dv-chart-stats {
  position: absolute; top: 10px; right: 10px;
  display: flex; flex-direction: column; gap: 6px;
  max-width: 170px; max-height: calc(100% - 20px); overflow-y: auto;
  z-index: 5;
  pointer-events: none;
}
.dv-stat-card {
  background: color-mix(in srgb, var(--panel-2) 90%, transparent);
  border: 1px solid var(--border); border-left: 3px solid var(--c);
  border-radius: 5px; padding: 5px 8px;
  font-size: 11px; color: var(--muted);
  backdrop-filter: blur(2px);
}
.dv-stat-title { margin-bottom: 3px; color: var(--text); font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dv-stat-title em { font-style: normal; margin-left: 3px; color: var(--faint); font-weight: 400; }
.dv-stat-line { display: flex; justify-content: space-between; gap: 10px; }
.dv-stat-line b { color: var(--text); font-weight: 600; font-family: var(--mono); }
/* ---- 折线图内列表切换 ---- */
.dv-list-overlay { flex: 1 1 auto; min-height: 0; overflow: auto; }
.dv-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; margin-right: 6px; }
/* ---- 聚类 / 拟合 / 优化 顶部工具条（复用原同图对比样式） ---- */
.dv-compare-bar { display: flex; align-items: center; gap: 12px; flex: 0 0 auto; padding-bottom: 6px; }
.dv-compare-title { font-size: 12px; color: var(--text); font-weight: 500; }
.dv-compare-chart { flex: 1 1 auto; min-height: 0; }
.dv-compare-chart :deep(.multi-trend) { height: 100%; display: flex; flex-direction: column; }
.dv-compare-chart :deep(.cv) { flex: 1 1 auto; }
/* ---- 聚类分析 ---- */
.dv-cluster-body { flex: 1 1 auto; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 12px; padding-right: 4px; }
.dv-cluster-meta { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; color: var(--muted); font-size: 11px; }
.dv-sil { font-family: var(--mono); font-size: 13px; }
.dv-sil.good { color: var(--green); }
.dv-sil.mid { color: var(--accent); }
.dv-sil.low { color: var(--red); }
.dv-cluster-note { color: var(--faint); font-size: 10px; }
.dv-cluster-card {
  border: 1px solid var(--border); border-radius: 6px;
  background: var(--panel-2); padding: 8px 10px;
  display: flex; flex-direction: column; gap: 6px;
}
.dv-cluster-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.dv-cluster-tag {
  padding: 1px 9px; border-radius: 9px; font-size: 11px; font-weight: 600;
  color: #fff; background: var(--accent);
}
.dv-cluster-size { color: var(--muted); font-size: 11px; }
.dv-cluster-summary { color: var(--text); font-size: 11px; }
.dv-cluster-devs { display: flex; flex-wrap: wrap; gap: 4px; }
.dv-chip {
  padding: 1px 7px; border-radius: 2px; font-size: 11px;
  color: var(--text); background: color-mix(in srgb, var(--c) 10%, transparent);
  border: 1px solid color-mix(in srgb, var(--c) 40%, transparent);
}
.dv-chip em { font-style: normal; color: var(--muted); }
.dv-cluster-chart { flex: 0 0 auto; }
.dv-cluster-feat { width: 100%; border-collapse: collapse; font-size: 11px; margin-top: 2px; }
.dv-cluster-feat th, .dv-cluster-feat td {
  padding: 3px 8px; border-bottom: 1px solid var(--line);
  text-align: right; white-space: nowrap;
}
.dv-cluster-feat th:first-child, .dv-cluster-feat td:first-child { text-align: left; }
.dv-cluster-feat th { color: var(--muted); font-weight: 500; background: var(--panel-3); }
.dv-cluster-feat .mono { font-family: var(--mono); color: var(--text); }
/* ---- 表格 ---- */
.dv-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.dv-table th, .dv-table td {
  padding: 5px 12px; border-bottom: 1px solid var(--line);
  text-align: left; white-space: nowrap;
}
.dv-table th {
  position: sticky; top: 0; z-index: 2;
  background: var(--panel-3); color: var(--muted);
  font-weight: 500; font-size: 11px;
  border-bottom: 1px solid var(--border);
}
.dv-table th em { font-style: normal; color: var(--faint); }
.dv-table .idx { width: 46px; color: var(--faint); text-align: right; }
.dv-table .num { text-align: right; }
.dv-table .mono { font-family: var(--mono); }
.dv-table tbody tr:hover { background: var(--accent-l); }
.dv-table .up { color: var(--red); }
.dv-table .down { color: var(--green); }
.dv-table .empty { text-align: center; color: var(--faint); padding: 40px 0; }
.badge {
  display: inline-block; padding: 0 5px; border-radius: 2px;
  font-size: 11px; line-height: 16px;
}
.badge.ok { color: var(--green); }
.badge.warn { color: var(--red); }
/* ---- 左侧 Excel 风格 sheet 页（垂直排列，可多选） ---- */
.dv-sheets {
  display: flex; flex-direction: column; gap: 2px;
  width: 176px; flex: 0 0 auto;
  padding: 6px 6px;
  background: var(--bar-d);
  border-right: 1px solid var(--border);
  overflow-y: auto;
}
.dv-src-tip {
  flex: 0 0 auto;
  padding: 4px 10px 6px;
  color: var(--faint); font-size: 10px;
  text-align: center;
  border-bottom: 1px dashed var(--line);
  margin-bottom: 4px;
}
.dv-sel-bar {
  flex: 0 0 auto;
  display: flex; align-items: center; gap: 4px;
  padding: 2px 2px 6px;
}
.dv-sel-bar button {
  padding: 1px 8px; font-size: 11px; line-height: 16px;
  color: var(--muted); background: var(--panel);
  border: 1px solid var(--border); border-radius: 4px; cursor: pointer;
}
.dv-sel-bar button:hover:not(:disabled) { color: var(--text); }
.dv-sel-bar button:disabled { opacity: .4; cursor: not-allowed; }
.dv-sel-count { margin-left: auto; font-size: 11px; color: var(--faint); }
.dv-sel-count.on { color: var(--accent); font-weight: 600; }
.dv-sheet {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 8px;
  min-width: 0;
  background: var(--panel-2);
  border: 1px solid var(--border);
  border-left: none;
  border-radius: 0 6px 6px 0;
  cursor: pointer;
  color: var(--muted);
  position: relative;
}
.dv-sheet:hover { background: var(--panel); color: var(--text); }
.dv-sheet.active {
  background: var(--panel);
  color: var(--text);
  box-shadow: inset 3px 0 0 var(--accent);
}
.dv-sheet.sel { box-shadow: inset 3px 0 0 var(--accent), inset 0 0 0 1px var(--accent); }
.dv-sheet .sh-cb {
  flex: 0 0 auto; width: 14px; height: 14px; margin: 0; padding: 0; box-sizing: border-box;
  accent-color: var(--accent); cursor: pointer;
}
.dv-sheet[draggable='true'] { cursor: grab; }
.dv-sheet[draggable='true']:active { cursor: grabbing; }
.dv-sheet .sh-icon { width: 8px; height: 8px; border-radius: 50%; flex: 0 0 auto; }
.dv-sheet .sh-body { flex: 1 1 auto; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.dv-sheet .sh-top { display: flex; align-items: baseline; gap: 6px; min-width: 0; }
.dv-sheet .sh-name { flex: 1 1 auto; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dv-sheet .sh-live { font-family: var(--mono); font-size: 11px; color: var(--faint); flex: 0 0 auto; }
.dv-sheet.active .sh-live { color: var(--accent); }
.dv-sheet .sh-unit {
  color: var(--faint); font-size: 10px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
/* ---- 拖入式数据源：整个区域可拖放，悬停高亮 / 空态引导 / 删除 / 清空 ---- */
.data-view.drop {
  outline: 2px dashed var(--accent);
  outline-offset: -2px;
  background: color-mix(in srgb, var(--accent) 5%, var(--panel-2));
}
.dv-drop-hint {
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  padding: 26px 10px; margin-top: 4px;
  color: var(--faint); text-align: center;
  border: 1px dashed var(--line); border-radius: 6px;
}
.dv-drop-ico { color: var(--accent); opacity: .75; }
.dv-drop-t1 { font-size: 11px; line-height: 1.55; color: var(--muted); }
.dv-drop-t2 { font-size: 10px; color: var(--faint); }
/* 右侧表格空态的大拖拽引导 */
.dv-empty-drag {
  display: inline-flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 34px 20px;
  color: var(--muted);
}
.dv-empty-drag b { font-size: 13px; font-weight: 600; color: var(--text); }
.dv-empty-drag em { font-style: normal; font-size: 11px; color: var(--faint); }
.dv-sheet .sh-del {
  flex: 0 0 auto; width: 16px; height: 16px;
  display: none; align-items: center; justify-content: center;
  border: none; background: transparent; color: var(--faint);
  font-size: 13px; line-height: 1; border-radius: 3px; cursor: pointer;
}
.dv-sheet:hover .sh-del { display: flex; }
.dv-sheet .sh-del:hover { color: var(--red); background: rgba(209,75,75,.12); }
.dv-clear-all {
  display: flex; align-items: center; justify-content: center; gap: 5px;
  margin-top: 6px; padding: 5px 0;
  color: var(--faint); font-size: 10px; cursor: pointer;
  border-top: 1px dashed var(--line);
}
.dv-clear-all:hover { color: var(--red); }
/* ---- 策略联动：数据拟合 / 参数优化 ---- */
.dv-link-tag {
  flex: 0 0 auto; padding: 1px 8px; border-radius: 9px;
  font-size: 10px; color: var(--accent-d); background: var(--accent-l);
}
.dv-fit-body, .dv-opt-body { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; gap: 8px; overflow: auto; }
.dv-fit-eq {
  flex: 0 0 auto; padding: 6px 10px;
  font-size: 12px; color: var(--text);
  background: var(--panel-3); border: 1px solid var(--border); border-radius: 5px;
}
.dv-fit-eq code {
  font-family: var(--mono); color: var(--accent);
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 4px;
  padding: 1px 6px; margin-left: 4px; font-size: 12px;
}
.dv-chart-svg { flex: 1 1 auto; width: 100%; min-height: 120px; }
.dv-axis line { stroke: var(--line); stroke-width: 1; }
.dv-grid { stroke: var(--line); stroke-width: 1; stroke-dasharray: 3 3; opacity: .6; }
.dv-tick { fill: var(--faint); font-size: 10px; font-family: var(--mono); }
.dv-fit-real { stroke: var(--accent); stroke-width: 1.8; }
.dv-fit-ext { stroke: var(--red); stroke-width: 1.5; stroke-dasharray: 5 4; opacity: .85; }
.dv-fit-dot { fill: var(--accent); opacity: .85; }
.dv-opt-sub { flex: 0 0 auto; font-size: 11px; color: var(--muted); }
.dv-opt-line { stroke: var(--accent); stroke-width: 1.6; }
.dv-opt-dot { fill: var(--accent); }
.dv-opt-tbl { margin-top: 4px; }
.dv-opt-tbl th, .dv-opt-tbl td { padding: 4px 8px; }
.dv-opt-tbl em { font-style: normal; color: var(--faint); font-size: 10px; }
.dv-delta-up { color: var(--red); }
.dv-delta-dn { color: var(--green); }
</style>
