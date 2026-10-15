<template>
  <div class="dcl-mask" @click.self="emit('close')">
    <div class="dcl-panel">
      <div class="dcl-head">
        <span class="dcl-ic">◉</span>
        <b>{{ t('数据采集（按设备分表导出 Excel）') }}</b>
        <span class="dcl-phase" :class="phase">{{ phaseText }}</span>
        <button class="dcl-x" @click="emit('close')" :title="t('关闭（采集中关闭不会中断采集，可再次打开查看进度）')">✕</button>
      </div>

      <div class="dcl-sub">
        {{ t('采集口径：按设备真实数据返回驱动——数据源时间戳推进即记一步，不按设定周期补点；导出的 Excel 首张为汇总表，其后每台在线设备一张子表。') }}
      </div>

      <!-- ---------- ① 未开始：选时长 + 在线设备清单 ---------- -->
      <template v-if="!vm">
        <div class="dcl-form">
          <label class="dcl-fl">{{ t('采集时长') }}</label>
          <div class="dcl-durs">
            <button v-for="d in DURATIONS" :key="d.ms" class="dcl-dur"
                    :class="{ on: durationMs === d.ms }" @click="durationMs = d.ms">{{ t(d.label) }}</button>
          </div>
          <span class="dcl-hint">{{ t('到时自动停止并导出；也可随时点「停止并导出」提前结束。') }}</span>
        </div>

        <div class="dcl-sec">
          <div class="dcl-sec-head">{{ t('本次参与采集的在线设备') }}<span class="dcl-n">{{ preview.length }}</span></div>
          <div class="dcl-devs">
            <div v-for="d in preview" :key="d.name" class="dcl-devrow">
              <span class="dcl-dot on"></span>
              <span class="dcl-dname" :title="d.name">{{ d.name }}</span>
              <span class="dcl-dmeta">{{ d.model || '—' }}<template v-if="d.node"> · {{ d.node }}</template></span>
              <span class="dcl-dprops">{{ t('{n} 个点位', { n: d.props }) }}</span>
            </div>
            <div v-if="!preview.length" class="dcl-empty">
              {{ t('当前没有在线设备（无实时数据推送），无法采集。') }}
            </div>
          </div>
        </div>

        <div class="dcl-ops">
          <button class="dcl-btn primary" :disabled="!preview.length" @click="emit('start', durationMs)">
            {{ t('开始采集') }}
          </button>
          <button class="dcl-btn" @click="emit('close')">{{ t('取消') }}</button>
        </div>
      </template>

      <!-- ---------- ② / ③ 采集中 / 已结束 ---------- -->
      <template v-else>
        <div class="dcl-prog">
          <div class="dcl-bar"><i :style="{ width: pct + '%' }"></i></div>
          <div class="dcl-prog-txt">
            <span class="dcl-time">{{ fmtDuration(vm.elapsed) }} / {{ fmtDuration(vm.durationMs) }}</span>
            <span class="dcl-mid">{{ t('已记录 {n} 条', { n: vm.records }) }}</span>
            <span class="dcl-right">{{ t('在线设备 {n} 台', { n: onlineCount }) }}</span>
          </div>
        </div>

        <div v-if="vm.error" class="dcl-err">{{ vm.error }}</div>

        <div class="dcl-sec">
          <div class="dcl-sec-head">{{ t('分设备采集情况') }}<span class="dcl-n">{{ vm.devices.length }}</span></div>
          <div class="dcl-tablewrap">
            <table class="dcl-table">
              <thead>
                <tr>
                  <th class="tl">{{ t('设备') }}</th>
                  <th>{{ t('状态') }}</th>
                  <th>{{ t('步号') }}</th>
                  <th>{{ t('实测频率') }}</th>
                  <th>{{ t('平均间隔') }}</th>
                  <th>{{ t('重复推送') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="d in vm.devices" :key="d.name">
                  <td class="tl">
                    <span class="dcl-dot" :class="{ on: d.online }"></span>
                    <span class="dcl-tdname" :title="d.name">{{ d.name }}</span>
                    <span v-if="d.model || d.node" class="dcl-tdsub">{{ d.model || '—' }}<template v-if="d.node"> · {{ d.node }}</template></span>
                  </td>
                  <td :class="d.online ? 'ok' : 'err'">{{ d.online ? t('在线') : t('离线') }}</td>
                  <td class="num">{{ d.steps }}</td>
                  <td class="num">{{ d.hz ? fmtHz(d.avgGap) : '—' }}</td>
                  <td class="num">{{ d.avgGap ? fmtGap(d.avgGap) : '—' }}</td>
                  <td class="num">{{ d.dup || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <div class="dcl-tip">{{ t('「设定周期」仅为对照：现场设备的真实返回间隔常与标称周期相差数倍，故步号按真实收到的数据条数计。') }}</div>
        </div>

        <div class="dcl-file" v-if="vm.file">
          <span class="dcl-fic">⤓</span>
          <span class="dcl-fname" :title="vm.file.name">{{ vm.file.name }}</span>
          <span class="dcl-fsize">{{ kb(vm.file.size) }}</span>
          <span class="dcl-fsheets">{{ t('共 {n} 张工作表', { n: vm.file.sheets }) }}</span>
        </div>

        <div class="dcl-ops">
          <template v-if="vm.phase === 'running'">
            <button class="dcl-btn" @click="emit('stop')">{{ t('停止并导出') }}</button>
            <button class="dcl-btn ghost" @click="emit('close')">{{ t('后台继续（关闭窗口）') }}</button>
          </template>
          <template v-else>
            <button class="dcl-btn primary" :disabled="!vm.file" @click="emit('download')">
              {{ t('再次下载 Excel') }}
            </button>
            <button class="dcl-btn" @click="emit('restart', durationMs)">{{ t('重新采集') }}</button>
            <button class="dcl-btn ghost" @click="emit('close')">{{ t('关闭') }}</button>
          </template>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { t } from '../i18n'
import { fmtDuration, fmtGap, fmtHz, COLLECT_DURATION_MS } from '../utils/dataCollect'

const props = defineProps({
  // 采集进度视图模型；null = 尚未开始
  vm: { type: Object, default: null },
  // 当前在线设备预览（打开弹窗时用于展示与「开始」前的判断）
  preview: { type: Array, default: () => [] },
})
const emit = defineEmits(['start', 'stop', 'restart', 'download', 'close'])

/** 采集时长选项：默认 20 分钟（与采集内核默认一致） */
const DURATIONS = [
  { ms: 60 * 1000, label: '1 分钟' },
  { ms: 5 * 60 * 1000, label: '5 分钟' },
  { ms: 10 * 60 * 1000, label: '10 分钟' },
  { ms: COLLECT_DURATION_MS, label: '20 分钟' },
]
const durationMs = ref(COLLECT_DURATION_MS)

const pct = computed(() => {
  const v = props.vm
  if (!v || !v.durationMs) return 0
  return Math.max(0, Math.min(100, (v.elapsed / v.durationMs) * 100))
})
const onlineCount = computed(() => (props.vm ? props.vm.devices.filter((d) => d.online).length : 0))
const phaseText = computed(() => {
  const p = props.vm && props.vm.phase
  if (p === 'running') return t('采集中…')
  if (p === 'done') return t('已完成')
  if (p === 'stopped') return t('已停止')
  return t('待开始')
})
const phase = computed(() => (props.vm ? props.vm.phase : 'idle'))

function kb(n) {
  const v = Number(n) || 0
  return v >= 1024 * 1024 ? `${(v / 1024 / 1024).toFixed(1)} MB` : `${(v / 1024).toFixed(1)} KB`
}
</script>

<style scoped>
.dcl-mask {
  position: fixed; inset: 0; z-index: 320; background: rgba(0, 0, 0, .5);
  display: flex; align-items: center; justify-content: center;
}
.dcl-panel {
  width: 720px; max-width: 94vw; max-height: 88vh; overflow: auto;
  background: var(--panel); border: 1px solid var(--border); border-radius: 6px;
  padding: 14px 16px 16px; box-shadow: 0 12px 40px rgba(0, 0, 0, .4);
  display: flex; flex-direction: column; gap: 10px;
}
.dcl-head { display: flex; align-items: center; gap: 8px; padding-bottom: 10px; border-bottom: 1px solid var(--border); }
.dcl-head b { font-size: 13px; font-weight: 500; color: var(--text); letter-spacing: .2px; }
.dcl-ic { color: var(--accent); font-size: 13px; }
.dcl-phase { font-size: 11px; color: var(--faint); padding: 1px 6px; border: 1px solid var(--border); border-radius: 2px; }
.dcl-phase.running { color: var(--accent-d); border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
.dcl-phase.done { color: var(--green); border-color: color-mix(in srgb, var(--green) 40%, transparent); }
.dcl-phase.stopped { color: var(--muted); }
.dcl-x { margin-left: auto; background: none; border: none; color: var(--muted); cursor: pointer; font-size: 13px; line-height: 1; padding: 2px 4px; }
.dcl-x:hover { color: var(--text); }

.dcl-sub { font-size: 11px; line-height: 1.6; color: var(--faint); }

/* ---- 时长选择 ---- */
.dcl-form { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dcl-fl { font-size: 12px; color: var(--text); flex: none; }
.dcl-durs { display: inline-flex; gap: 4px; }
.dcl-dur {
  font-size: 11px; padding: 3px 10px; cursor: pointer; color: var(--muted);
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px;
}
.dcl-dur:hover { color: var(--text); }
.dcl-dur.on { color: var(--accent-d); border-color: color-mix(in srgb, var(--accent) 55%, transparent); background: var(--accent-l); }
.dcl-hint { font-size: 11px; color: var(--faint); }

/* ---- 设备清单 / 表格 ---- */
.dcl-sec { border: 1px solid var(--border); border-radius: 4px; overflow: hidden; }
.dcl-sec-head {
  display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text);
  padding: 7px 10px; background: var(--bar, var(--panel-2)); border-bottom: 1px solid var(--border);
}
.dcl-n { margin-left: auto; font-size: 11px; color: var(--faint); }
.dcl-devs { display: flex; flex-direction: column; max-height: 220px; overflow-y: auto; }
.dcl-devrow { display: flex; align-items: center; gap: 6px; padding: 6px 10px; font-size: 12px; }
.dcl-devrow + .dcl-devrow { border-top: 1px dashed var(--border); }
.dcl-dname { color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dcl-dmeta { flex: 1 1 auto; min-width: 0; text-align: right; font-size: 11px; color: var(--faint);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dcl-dprops { flex: none; font-size: 11px; color: var(--muted); }
.dcl-empty { padding: 16px 10px; text-align: center; font-size: 11px; color: var(--faint); }

.dcl-tablewrap { max-height: 260px; overflow: auto; }
.dcl-table { width: 100%; border-collapse: collapse; font-size: 11px; }
.dcl-table th {
  position: sticky; top: 0; z-index: 1; text-align: center; font-weight: 400; color: var(--muted);
  background: var(--panel-2); padding: 5px 6px; border-bottom: 1px solid var(--border); white-space: nowrap;
}
.dcl-table th.tl, .dcl-table td.tl { text-align: left; }
.dcl-table td { padding: 5px 6px; text-align: center; color: var(--text); border-bottom: 1px dashed var(--border); }
.dcl-table tr:last-child td { border-bottom: none; }
.dcl-table td.num { font-variant-numeric: tabular-nums; color: var(--muted); }
.dcl-table td.ok { color: var(--green); }
.dcl-table td.err { color: var(--red); }
.dcl-tdname { margin-left: 4px; }
.dcl-tdsub { margin-left: 6px; font-size: 10px; color: var(--faint); }
.dcl-tip { padding: 6px 10px; font-size: 10px; line-height: 1.6; color: var(--faint); border-top: 1px solid var(--border); background: var(--panel-2); }

/* 状态圆点：红=离线，绿=在线（与资源列表同口径） */
.dcl-dot { flex: none; width: 6px; height: 6px; border-radius: 50%; background: var(--red); display: inline-block; }
.dcl-dot.on { background: var(--green); }

/* ---- 进度 ---- */
.dcl-prog { display: flex; flex-direction: column; gap: 6px; }
.dcl-bar { height: 6px; border-radius: 3px; background: var(--panel-3); overflow: hidden; }
.dcl-bar i { display: block; height: 100%; background: var(--accent); transition: width .3s linear; }
.dcl-prog-txt { display: flex; align-items: center; gap: 12px; font-size: 11px; color: var(--muted); }
.dcl-time { font-variant-numeric: tabular-nums; color: var(--text); font-size: 12px; }
.dcl-right { margin-left: auto; }
.dcl-err { font-size: 11px; color: var(--red); }

/* ---- 产物 ---- */
.dcl-file { display: flex; align-items: center; gap: 8px; font-size: 12px; padding: 7px 10px;
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px; }
.dcl-fic { color: var(--green); }
.dcl-fname { color: var(--text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.dcl-fsize, .dcl-fsheets { flex: none; font-size: 11px; color: var(--faint); }
.dcl-fsheets { margin-left: auto; }

/* ---- 操作 ---- */
.dcl-ops { display: flex; justify-content: flex-end; gap: 8px; padding-top: 2px; }
.dcl-btn {
  font-size: 12px; padding: 5px 14px; cursor: pointer; color: var(--text);
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px;
}
.dcl-btn:hover:not(:disabled) { background: var(--panel-3); }
.dcl-btn:disabled { opacity: .5; cursor: not-allowed; }
.dcl-btn.primary {
  color: #fff; background: var(--accent); border-color: var(--accent);
}
.dcl-btn.primary:hover:not(:disabled) { background: var(--accent-h); }
.dcl-btn.ghost { color: var(--muted); border-color: transparent; background: none; }
</style>
