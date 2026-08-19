<template>
  <div class="welcome-mask">
    <div class="welcome">
      <!-- ===== 主体：左简介 / 右打开项目 ===== -->
      <div class="w-body">
        <!-- 左侧 -->
        <section class="w-left">
          <h1 class="title">欢迎使用<br /><span>行业能碳仿真平台</span></h1>
          <p class="sub">面向流程工业的全要素数字孪生与能碳管理平台，覆盖工艺建模、碳素流 / 能流核算、情景推演与减排策略寻优全链路。</p>

          <div class="feats">
            <div class="feat" v-for="f in feats" :key="f.t">
              <div class="feat-ic" v-html="f.svg"></div>
              <div class="feat-tx">
                <b>{{ f.t }}</b>
                <span>{{ f.d }}</span>
              </div>
            </div>
          </div>

          <div class="about">
            <h3>平台能力</h3>
            <p>面向钢铁、水泥、化工、有色等流程工业，提供覆盖"工艺建模 → 能碳核算 → 情景推演 → 策略寻优"全链路的数字孪生与能碳管理能力，助力企业节能降碳决策。</p>
            <div class="about-flow">
              <span>工艺建模</span><i>→</i><span>能碳核算</span><i>→</i><span>情景推演</span><i>→</i><span>策略寻优</span>
            </div>
          </div>
        </section>

        <!-- 右侧 -->
        <section class="w-right">
          <div class="proj-head">
            <h2>打开项目</h2>
            <span class="hint" v-if="hint">{{ hint }}</span>
          </div>

          <div class="proj-list">
            <div
              v-for="p in projects"
              :key="p.id"
              class="proj"
              :class="{ sel: selected === p.id, plan: p.status === 'plan' }"
              @click="pick(p)"
            >
              <span class="proj-dot" :style="{ background: p.status === 'ready' ? p.color : 'var(--border)' }"></span>
              <div class="proj-mid">
                <div class="proj-name">
                  {{ p.name }}
                  <em v-if="p.tag" :style="{ color: p.color }">{{ p.tag }}</em>
                </div>
                <div class="proj-desc">{{ p.desc }}</div>
              </div>
              <template v-if="p.status === 'ready'">
                <span class="units">{{ p.units }} 道工序</span>
              </template>
              <span v-else class="plan-badge">规划中</span>
            </div>
          </div>

          <div class="enter-zone">
            <button class="enter" :class="{ loading: entering }" @click="go">
              <template v-if="!entering">进入系统</template>
              <template v-else><span class="spin"></span>正在初始化仿真引擎…</template>
            </button>
            <p class="enter-hint"><i></i>默认项目：钢铁企业 · 长流程（BF-BOF）</p>
          </div>
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
    svg: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3 L21 8 V16 L12 21 L3 16 V8 Z" stroke="currentColor" stroke-width="1.6"/><path d="M12 11 L21 6 M12 11 L3 6 M12 11 L12 20" stroke="currentColor" stroke-width="1.2"/></svg>',
  },
  {
    t: '能碳核算',
    d: '全流程碳素流 / 能流自动核算，排放因子分级配置',
    svg: '<svg viewBox="0 0 24 24" fill="none"><circle cx="12" cy="12" r="8" stroke="currentColor" stroke-width="1.6"/><path d="M12 6 V12 L16 14" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><path d="M4 4 L8 8 M20 4 L16 8" stroke="currentColor" stroke-width="1.4" stroke-linecap="round"/></svg>',
  },
  {
    t: 'AI 策略寻优',
    d: '自然语言驱动情景推演，智能体解析并生成减排方案',
    svg: '<svg viewBox="0 0 24 24" fill="none"><rect x="4" y="4" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.6"/><rect x="14" y="4" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.6"/><rect x="4" y="14" width="6" height="6" rx="1.5" stroke="currentColor" stroke-width="1.6"/><path d="M17 17 L20 20" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  },
  {
    t: '实时监测预警',
    d: '传感设备接入、标定耦合与异常预警，数据驱动决策',
    svg: '<svg viewBox="0 0 24 24" fill="none"><path d="M3 13 L7 9 L11 13 L17 6 L21 10" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 21 H21" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/><circle cx="19" cy="17" r="2" stroke="currentColor" stroke-width="1.6"/></svg>',
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
  background: rgba(0, 0, 0, .32);
  backdrop-filter: blur(2px);
  -webkit-backdrop-filter: blur(2px);
  padding: 32px;
}

/* ===== 对话框主体：系统面板风格（跟随全局 CSS 变量，深色仿真模式自动适配） ===== */
.welcome {
  width: min(980px, 100%);
  max-height: calc(100vh - 64px);
  display: flex; flex-direction: column;
  background: var(--panel);
  color: var(--text);
  border: 1px solid var(--border);
  border-radius: 8px;
  box-shadow: 0 18px 50px rgba(0, 0, 0, .35);
  font-family: var(--ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif);
  font-size: 12px;
  overflow: hidden;
  user-select: none;
  animation: pop .28s cubic-bezier(.2, .9, .3, 1.1) both;
}
@keyframes pop { from { opacity: 0; transform: translateY(14px) scale(.985) } to { opacity: 1; transform: none } }

/* ===== 主体两栏 ===== */
.w-body {
  flex: 1; min-height: 0;
  display: grid; grid-template-columns: minmax(0, .85fr) minmax(0, 1.15fr);
  gap: 20px;
  padding: 20px 22px;
}
.w-left, .w-right { display: flex; flex-direction: column; min-width: 0; }

/* —— 左侧 —— */
.title { margin: 0 0 10px; font-size: 22px; line-height: 1.25; font-weight: 700; color: var(--text); letter-spacing: .5px; }
.title span { color: var(--accent); }
.sub { margin: 0 0 14px; font-size: 11.5px; line-height: 1.8; color: var(--muted); }
.feats { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 14px; }
.feat {
  display: flex; gap: 9px; align-items: flex-start;
  background: var(--panel-2); border: 1px solid var(--border);
  border-radius: 5px; padding: 9px 10px;
}
.feat:hover { border-color: var(--accent); background: var(--accent-l); transition: all .15s; }
.feat-ic { width: 24px; height: 24px; flex: none; color: var(--accent); }
.feat-ic svg { width: 100%; height: 100%; }
.feat-tx b { display: block; font-size: 11.5px; font-weight: 600; color: var(--text); margin-bottom: 2px; }
.feat-tx span { display: block; font-size: 10px; line-height: 1.55; color: var(--muted); }
.about { background: var(--panel-2); border: 1px solid var(--border); border-radius: 5px; padding: 10px 12px; }
.about h3 { margin: 0 0 6px; font-size: 11.5px; font-weight: 600; color: var(--accent); letter-spacing: 1px; }
.about p { margin: 0 0 8px; font-size: 10.5px; line-height: 1.7; color: var(--muted); }
.about-flow {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  padding: 6px 8px; background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
}
.about-flow span { font-size: 9.5px; color: var(--text); padding: 2px 7px; background: var(--accent-l); border: 1px solid var(--border); border-radius: 3px; }
.about-flow i { font-style: normal; font-size: 10px; color: var(--accent); }

/* —— 右侧 —— */
.w-right { gap: 10px; }
.proj-head { display: flex; align-items: baseline; gap: 10px; }
.proj-head h2 { margin: 0; font-size: 14px; font-weight: 600; color: var(--text); }
.proj-head .hint { font-size: 10.5px; color: var(--yellow); }
.proj-list {
  flex: 1; min-height: 0; overflow-y: auto;
  display: flex; flex-direction: column; gap: 5px;
  padding: 4px;
}
.proj-list::-webkit-scrollbar { width: 5px; }
.proj-list::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }
.proj {
  display: flex; align-items: center; gap: 10px;
  padding: 9px 12px; border-radius: 6px; cursor: pointer;
  background: var(--panel);
  border: 1px solid transparent;
  transition: background .1s;
}
.proj:hover { background: var(--panel-2); }
.proj.sel { background: var(--accent-l); border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }
.proj.plan { opacity: .45; cursor: not-allowed; }
.proj.plan:hover { background: var(--panel); }
.proj-dot { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.proj-mid { flex: 1; min-width: 0; }
.proj-name { font-size: 12.5px; font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 6px; }
.proj-name em { font-style: normal; font-size: 8.5px; border: 1px solid currentColor; border-radius: 2px; padding: 0 4px; line-height: 1.4; }
.proj-desc { font-size: 10px; color: var(--faint); line-height: 1.5; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.units { font-family: var(--mono, Menlo, monospace); font-size: 9px; color: var(--faint); flex: none; }
.plan-badge { font-size: 9px; color: var(--faint); border: 1px dashed var(--border); border-radius: 3px; padding: 1px 7px; flex: none; }

.enter-zone { flex: none; }
.enter {
  width: 100%; padding: 10px 16px;
  display: flex; align-items: center; justify-content: center; gap: 8px;
  font-size: 12.5px; font-weight: 600; letter-spacing: 1.5px; color: #fff;
  background: linear-gradient(180deg, var(--accent), var(--accent-d));
  border: 1px solid var(--accent-d); border-radius: 4px; cursor: pointer;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, .18);
  transition: filter .15s, box-shadow .15s;
}
.enter:hover { filter: brightness(1.1); box-shadow: 0 3px 10px color-mix(in srgb, var(--accent) 45%, transparent); }
.enter:active { filter: brightness(.95); }
.enter:hover { filter: brightness(1.06); }
.enter.loading { cursor: wait; opacity: .85; }
.spin { width: 13px; height: 13px; border-radius: 50%; border: 2px solid rgba(255, 255, 255, .35); border-top-color: #fff; animation: spin .7s linear infinite; }
@keyframes spin { to { transform: rotate(360deg) } }
.enter-hint { margin: 8px 0 0; display: flex; align-items: center; gap: 6px; font-size: 10px; color: var(--faint); }
.enter-hint i { width: 5px; height: 5px; border-radius: 50%; background: var(--green); }

/* ===== 响应式 ===== */
@media (max-width: 860px) {
  .w-body { grid-template-columns: 1fr; overflow-y: auto; }
  .welcome { max-height: calc(100vh - 32px); }
  .welcome-mask { padding: 16px; }
}
</style>
