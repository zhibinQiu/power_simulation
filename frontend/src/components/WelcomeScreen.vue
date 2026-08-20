<template>
  <div class="welcome-mask">
    <div class="welcome">

      <!-- ===== Hero 品牌区（VSCode 欢迎页风格） ===== -->
      <div class="ws-hero">
        <div class="ws-logo">
          <svg viewBox="0 0 24 24" fill="none">
            <circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.5" />
            <path d="M9 12.5 L11 14.5 L15 10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            <path d="M12 3.5 V6 M12 18 V20.5 M3.5 12 H6 M18 12 H20.5" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" />
          </svg>
        </div>
        <h1 class="ws-title">行业能碳仿真平台</h1>
        <p class="ws-sub">面向流程工业的全要素数字孪生与能碳管理平台</p>
        <button class="btn-start" :class="{ loading: entering }" @click="go">
          <svg v-if="!entering" viewBox="0 0 24 24" fill="none">
            <path d="M4 8 H20 A1 1 0 0 1 21 9 V19 A1 1 0 0 1 20 20 H4 A1 1 0 0 1 3 19 V6 A1 1 0 0 1 4 5 H9 L11 8" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" />
          </svg>
          <template v-if="!entering">进入系统</template>
          <template v-else><span class="spin"></span>正在初始化仿真引擎…</template>
        </button>
      </div>

      <!-- ===== 内容网格 ===== -->
      <div class="ws-grid">

        <!-- 左列：功能特性 / 平台能力 -->
        <section class="ws-col">
          <h2 class="ws-sec-title">功能特性</h2>
          <ul class="ws-list">
            <li v-for="f in feats" :key="f.t" class="ws-item">
              <span class="ws-ic" v-html="f.svg"></span>
              <div class="ws-tx">
                <b>{{ f.t }}</b>
                <span>{{ f.d }}</span>
              </div>
            </li>
          </ul>

          <h2 class="ws-sec-title" style="margin-top: 18px">平台能力</h2>
          <div class="ws-flow">
            <span>工艺建模</span><i>→</i><span>能碳核算</span><i>→</i><span>情景推演</span><i>→</i><span>策略寻优</span>
          </div>
        </section>

        <!-- 右列：最近（项目） -->
        <section class="ws-col">
          <h2 class="ws-sec-title">
            最近
            <span class="ws-hint" v-if="hint">{{ hint }}</span>
          </h2>
          <ul class="ws-list">
            <li
              v-for="p in projects"
              :key="p.id"
              class="ws-item ws-proj"
              :class="{ sel: selected === p.id, plan: p.status === 'plan' }"
              @click="pick(p)"
            >
              <span class="ws-ic" :style="{ color: p.status === 'ready' ? p.color : 'var(--faint)' }">
                <svg viewBox="0 0 24 24" fill="none">
                  <path d="M3 7 A2 2 0 0 1 5 5 H9 L11 7.5 H19 A2 2 0 0 1 21 9.5 V17 A2 2 0 0 1 19 19 H5 A2 2 0 0 1 3 17 Z" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" />
                  <path d="M3 10 H21" stroke="currentColor" stroke-width="1.2" />
                </svg>
              </span>
              <div class="ws-tx">
                <b>{{ p.name }} <em v-if="p.tag" :style="{ color: p.color }">{{ p.tag }}</em></b>
                <span>{{ p.desc }}</span>
              </div>
              <div class="ws-right">
                <span v-if="p.status === 'ready'" class="ws-meta">{{ p.units }} 道工序</span>
                <span v-else class="ws-meta plan">规划中</span>
                <span v-if="p.status === 'ready'" class="ws-open" :style="{ color: p.color }">
                  <svg viewBox="0 0 24 24" fill="none">
                    <path d="M13 5 H19 V11 M19 5 L10 14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" />
                    <path d="M19 13 V18 A2 2 0 0 1 17 20 H6 A2 2 0 0 1 4 18 V7 A2 2 0 0 1 6 5 H11" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" />
                  </svg>
                </span>
              </div>
            </li>
          </ul>
        </section>

      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, onUnmounted } from 'vue'

/* ---------------- 特性 ---------------- */
const feats = [
  {
    t: '3D 数字孪生',
    d: '工艺 / 设备 / 物料全要素三维可视化，实时数据联动',
    svg: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3 L21 8 V16 L12 21 L3 16 V8 Z" stroke="currentColor" stroke-width="1.5"/><path d="M12 11 L21 6 M12 11 L3 6 M12 11 L12 20" stroke="currentColor" stroke-width="1.1"/></svg>',
  },
  {
    t: '能碳核算',
    d: '全流程碳素流 / 能流自动核算，排放因子分级配置',
    svg: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.5"/><path d="M12 6 V12 L16 14" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><path d="M4 4 L8 8 M20 4 L16 8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  },
  {
    t: 'AI 策略寻优',
    d: '自然语言驱动情景推演，智能体解析并生成减排方案',
    svg: '<svg viewBox="0 0 24 24" fill="none"><rect x="4" y="4" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="14" y="4" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/><rect x="4" y="14" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.5"/><path d="M17 17 L20 20" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  },
  {
    t: '实时监测预警',
    d: '传感设备接入、标定耦合与异常预警，数据驱动决策',
    svg: '<svg viewBox="0 0 24 24" fill="none"><path d="M3 13 L7 9 L11 13 L17 6 L21 10" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 21 H21" stroke="currentColor" stroke-width="1.5" stroke-linecap="round"/><circle cx="19" cy="17" r="2" stroke="currentColor" stroke-width="1.5"/></svg>',
  },
]

/* ---------------- 项目 ---------------- */
const projects = [
  {
    id: 'steel-long', route: 'long', status: 'ready', color: '#0072BD',
    name: '钢铁企业 · 长流程', tag: '推荐',
    desc: '烧结 → 球团 → 焦化 → 高炉 → 转炉 → 精炼 → 连铸 → 轧钢',
    units: 10,
  },
  {
    id: 'steel-short', route: 'short', status: 'ready', color: '#2E9E63',
    name: '钢铁企业 · 短流程', tag: '低碳',
    desc: '电弧炉 → 精炼 → 连铸 → 轧钢，废钢短流程低碳冶炼',
    units: 5,
  },
  { id: 'cement', status: 'plan', color: '#8AA0B8', name: '水泥企业', desc: '新型干法水泥窑炉线', units: 0 },
  { id: 'chemical', status: 'plan', color: '#8AA0B8', name: '化工企业', desc: '石化化工装置线', units: 0 },
  { id: 'nonferrous', status: 'plan', color: '#8AA0B8', name: '有色企业', desc: '铜铝冶炼生产线', units: 0 },
]

const selected = ref('steel-long')
const entering = ref(false)
const hint = ref('')
let hintTimer = null
const emit = defineEmits(['open'])

function pick(p) {
  if (entering.value) return
  if (p.status !== 'ready') {
    hint.value = `${p.name}项目规划中，即将上线`
    clearTimeout(hintTimer)
    hintTimer = setTimeout(() => { hint.value = '' }, 2600)
    return
  }
  selected.value = p.id
  hint.value = ''
}

async function go() {
  if (entering.value) return
  const p = projects.find((x) => x.id === selected.value)
  if (!p || p.status !== 'ready') return
  entering.value = true
  hint.value = ''
  emit('open', p.route)
}

onUnmounted(() => {
  clearTimeout(hintTimer)
})
</script>

<style scoped>
/* ===== 遮罩：非全屏，半透明模糊，露出背后主界面 ===== */
.welcome-mask {
  position: fixed; inset: 0; z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  background: rgba(0, 0, 0, .4);
  backdrop-filter: blur(3px);
  -webkit-backdrop-filter: blur(3px);
  padding: 32px;
}

/* ===== 对话框主体：VSCode 欢迎页风格 ===== */
.welcome {
  width: min(940px, 100%);
  max-height: calc(100vh - 64px);
  overflow-y: auto;
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 6px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, .4);
  font-family: var(--ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif);
  font-size: 12px;
  user-select: none;
  animation: pop .25s cubic-bezier(.2, .9, .3, 1.05) both;
}
@keyframes pop { from { opacity: 0; transform: translateY(10px) scale(.99) } to { opacity: 1; transform: none } }
.welcome::-webkit-scrollbar { width: 8px; }
.welcome::-webkit-scrollbar-thumb { background: var(--border); border-radius: 4px; }

/* ===== Hero 品牌区 ===== */
.ws-hero {
  padding: 26px 40px 20px;
  text-align: center;
  border-bottom: 1px solid var(--border);
}
.ws-logo {
  width: 52px; height: 52px; margin: 0 auto 12px;
  color: var(--accent);
}
.ws-logo svg { width: 100%; height: 100%; }
.ws-title {
  margin: 0 0 6px;
  font-size: 26px; font-weight: 600; letter-spacing: .5px;
  color: var(--text);
}
.ws-sub { margin: 0 0 18px; font-size: 12px; color: var(--muted); }

.btn-start {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 8px 26px;
  font-size: 13px; font-weight: 500; letter-spacing: .5px; color: #fff;
  background: var(--accent);
  border: 1px solid var(--accent-d); border-radius: 3px;
  cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .15);
  transition: filter .12s;
}
.btn-start svg { width: 15px; height: 15px; }
.btn-start:hover { filter: brightness(1.12); }
.btn-start:active { filter: brightness(.94); }
.btn-start.loading { cursor: wait; opacity: .85; }
.spin { width: 12px; height: 12px; border-radius: 50%; border: 2px solid rgba(255, 255, 255, .35); border-top-color: #fff; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg) } }

/* ===== 内容网格 ===== */
.ws-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 40px;
  padding: 20px 40px 28px;
}
@media (max-width: 780px) {
  .ws-grid { grid-template-columns: 1fr; gap: 24px; }
}

.ws-sec-title {
  display: flex; align-items: baseline; gap: 8px;
  margin: 0 0 10px;
  font-size: 11px; font-weight: 600; letter-spacing: 1.6px; text-transform: uppercase;
  color: var(--faint);
}
.ws-hint { font-size: 10px; letter-spacing: 0; text-transform: none; color: var(--yellow); }

.ws-list { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 2px; }
.ws-item {
  display: flex; align-items: flex-start; gap: 10px;
  padding: 6px 8px; border-radius: 4px;
}
.ws-ic { width: 17px; height: 17px; flex: none; margin-top: 2px; color: var(--accent); }
.ws-ic svg { width: 100%; height: 100%; }
.ws-tx { flex: 1; min-width: 0; }
.ws-tx b { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; font-size: 12.5px; font-weight: 500; color: var(--text); }
.ws-tx b em { font-style: normal; font-size: 8.5px; font-weight: 500; border: 1px solid currentColor; border-radius: 2px; padding: 0 4px; line-height: 1.5; }
.ws-tx span { display: block; font-size: 10.5px; line-height: 1.55; color: var(--muted); margin-top: 2px; }

/* —— 项目行（VSCode 最近列表交互） —— */
.ws-proj { cursor: pointer; border-radius: 4px; transition: background .1s; }
.ws-proj:hover { background: color-mix(in srgb, var(--text) 6%, transparent); }
.ws-proj.sel { background: var(--accent-l); }
.ws-proj.plan { opacity: .45; cursor: not-allowed; }
.ws-proj.plan:hover { background: transparent; }
.ws-right { display: flex; align-items: center; gap: 6px; flex: none; margin-top: 2px; }
.ws-meta { font-family: var(--mono, Menlo, monospace); font-size: 9px; color: var(--faint); }
.ws-meta.plan { font-family: var(--ui, -apple-system, 'Segoe UI', 'PingFang SC', sans-serif); border: 1px dashed var(--border); border-radius: 3px; padding: 0 6px; }
.ws-open { display: none; width: 15px; height: 15px; }
.ws-open svg { width: 100%; height: 100%; }
.ws-proj:not(.plan):hover .ws-meta { display: none; }
.ws-proj:not(.plan):hover .ws-open { display: block; }

/* —— 平台能力流程 —— */
.ws-flow {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 10px;
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px;
}
.ws-flow span {
  font-size: 10px; color: var(--text);
  padding: 2px 8px;
  background: var(--panel); border: 1px solid var(--border); border-radius: 3px;
}
.ws-flow i { font-style: normal; font-size: 10px; color: var(--accent); }

/* ===== 响应式 ===== */
@media (max-width: 640px) {
  .welcome-mask { padding: 16px; }
  .ws-hero { padding: 20px 20px 16px; }
  .ws-grid { padding: 16px 20px 22px; }
}
</style>
