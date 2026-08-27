<template>
  <div class="lp-root">
    <!-- ===== 背景：网格 + 辉光 ===== -->
    <div class="lp-bg"></div>
    <div class="lp-glow g1"></div>
    <div class="lp-glow g2"></div>
    <div class="lp-grid-v"></div>

    <!-- ===== 顶部导航 ===== -->
    <header class="lp-nav">
      <div class="lp-brand">
        <div class="lp-logo">
          <svg viewBox="0 0 24 24" fill="none">
            <path d="M12 2.5 L20.5 7 V17 L12 21.5 L3.5 17 V7 Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/>
            <path d="M12 8.5 L16.5 11 V16 L12 18.5 L7.5 16 V11 Z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/>
            <path d="M12 2.5 V6 M12 18.5 V21.5 M12 6 V8.5 M12 16 V18.5" stroke="currentColor" stroke-width="0.9" stroke-linecap="round"/>
            <path d="M5.5 4 L3.5 2.5 M18.5 4 L20.5 2.5" stroke="currentColor" stroke-width="0.9" stroke-linecap="round"/>
          </svg>
        </div>
        <div class="lp-brand-tx">
          <b>工业能碳智控平台</b>
          <span>INDUSTRIAL ENERGY&nbsp;&amp;&nbsp;CARBON CONTROL PLATFORM</span>
        </div>
      </div>
      <nav class="lp-menu">
        <a href="#caps">核心能力</a>
        <a href="#arch">云边协同</a>
        <a href="#enter">进入系统</a>
      </nav>
      <button class="lp-enter-btn" @click="goToEnter">进入系统<span class="lp-arr">→</span></button>
    </header>

    <!-- ===== 主内容（可滚动） ===== -->
    <main class="lp-main">

      <!-- ================= Hero ================= -->
      <section class="lp-hero">
        <div class="lp-hero-l">
          <div class="lp-tagline"><i></i>懂能 · 懂碳 · 懂市场</div>
          <h1 class="lp-title">工业能碳智控平台</h1>
          <p class="lp-sub">
            面向流程工业的全要素数字孪生与能碳智控系统，依托<b>自研云边协同</b>架构，
            <b>软硬一体</b>的能碳一体机开箱即用 —— 设备模型秒级建立下发、AI 模型远程部署、盒子现场傻瓜式接入，
            一站式云端管理平台掌控全局。
          </p>
          <div class="lp-cta">
            <button class="btn-primary" @click="goToEnter">进入系统</button>
            <button class="btn-ghost" @click="goToCaps">了解核心能力</button>
          </div>
          <div class="lp-stats">
            <div class="lp-stat"><b>软硬一体</b><span>能碳一体机开箱即用</span></div>
            <div class="lp-stat"><b>&lt; 10 分钟</b><span>现场傻瓜式接入</span></div>
            <div class="lp-stat"><b>3s</b><span>云端数据刷新</span></div>
            <div class="lp-stat"><b>双通道</b><span>遥测回传不中断</span></div>
          </div>
        </div>
        <div class="lp-hero-r">
          <!-- 云边协同抽象图 -->
          <div class="lp-arch-art">
            <div class="aa-cloud">
              <span class="aa-chip tag">自研云边协同系统</span>
              <div class="aa-node cloud-core">
                <i class="aa-ic">
                  <svg viewBox="0 0 24 24" fill="none"><path d="M7 18 A4.5 4.5 0 0 1 6.5 9 A5.5 5.5 0 0 1 17 8.5 A4 4 0 0 1 17.5 16.5 Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/></svg>
                </i>
                <b>云端控制平面</b>
                <span>K3s · KubeEdge CloudCore</span>
              </div>
              <div class="aa-node cloud-agent">
                <i class="aa-ic">
                  <svg viewBox="0 0 24 24" fill="none"><path d="M4 7 H20 V17 H4 Z" stroke="currentColor" stroke-width="1.4" stroke-linejoin="round"/><path d="M8 11 H16 M8 14 H13" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
                </i>
                <b>cloud-agent 数据代理</b>
                <span>MQTT Broker · REST API 下发</span>
              </div>
            </div>
            <div class="aa-link">
              <div class="aa-beam"></div>
              <span>CloudHub · 10002 长连接</span>
              <span class="aa-up">▲ 实时遥测 MQTT data/#</span>
              <span class="aa-down">▼ 模型/设备下发 API</span>
            </div>
            <div class="aa-edge">
              <div class="aa-node box">
                <i class="aa-ic">
                  <svg viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="13" rx="1.5" stroke="currentColor" stroke-width="1.4"/><path d="M3 8 H21 M12 8 V17 M8 17 H16" stroke="currentColor" stroke-width="1.2"/><path d="M7 11 H10 M14 14 H17" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>
                </i>
                <b>能碳一体机 · 边缘侧</b>
                <span>EdgeCore · box-mapper · mosquitto</span>
              </div>
              <div class="aa-edge-sub">
                <span class="aa-chip">AI 模型</span>
                <span class="aa-chip">设备模型</span>
                <span class="aa-chip">五协议采集</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <!-- ================= 核心能力 ================= -->
      <section id="caps" class="lp-section">
        <div class="lp-sec-head">
          <h2 class="lp-sec-title"><i>01</i>核心能力</h2>
          <span class="lp-sec-en">CORE CAPABILITIES</span>
        </div>
        <div class="lp-cards">
          <div v-for="c in caps" :key="c.t" class="lp-card">
            <div class="lp-card-ic" v-html="c.svg"></div>
            <b>{{ c.t }}</b>
            <span>{{ c.d }}</span>
            <ul class="lp-card-pts">
              <li v-for="p in c.pts" :key="p">{{ p }}</li>
            </ul>
          </div>
        </div>
      </section>

      <!-- ================= 云边协同架构 ================= -->
      <section id="arch" class="lp-section">
        <div class="lp-sec-head">
          <h2 class="lp-sec-title"><i>02</i>云边协同 · 系统架构</h2>
          <span class="lp-sec-en">CLOUD-EDGE COLLABORATION</span>
        </div>
        <div class="lp-arch">
          <div class="arch-side cloud">
            <div class="arch-side-tag">云 端 · 唯一控制平面</div>
            <div class="arch-row" v-for="r in cloudRows" :key="r.t">
              <span class="arch-row-ic">{{ r.ic }}</span>
              <div class="arch-row-tx"><b>{{ r.t }}</b><span>{{ r.d }}</span></div>
            </div>
          </div>
          <div class="arch-mid">
            <div class="arch-beams">
              <div class="beam down"><span>▼</span>模型 / 配置 / 指令下发</div>
              <div class="beam up"><span>▲</span>实时遥测 · 状态上报</div>
            </div>
            <div class="arch-mid-chip">CloudHub : 10002 安全长连接</div>
          </div>
          <div class="arch-side edge">
            <div class="arch-side-tag">边 缘 · 能碳一体机</div>
            <div class="arch-row" v-for="r in edgeRows" :key="r.t">
              <span class="arch-row-ic">{{ r.ic }}</span>
              <div class="arch-row-tx"><b>{{ r.t }}</b><span>{{ r.d }}</span></div>
            </div>
          </div>
        </div>
      </section>

      <!-- ================= 数字化能力横条 ================= -->
      <section class="lp-capbar">
        <div class="capbar-item" v-for="c in digitals" :key="c">
          <i class="capbar-dot"></i>{{ c }}
        </div>
      </section>

      <!-- ================= 进入系统 ================= -->
      <section id="enter" class="lp-section lp-enter">
        <div class="lp-sec-head">
          <h2 class="lp-sec-title"><i>03</i>进入系统</h2>
          <span class="lp-sec-en">LAUNCH WORKSPACE</span>
        </div>
        <p class="lp-enter-tip">选择仿真项目进入数字孪生工作台（更多行业模板持续上线）</p>
        <div class="lp-projects">
          <div
            v-for="p in projects" :key="p.id"
            class="lp-proj" :class="{ sel: selected === p.id, plan: p.status !== 'ready' }"
            @click="pick(p)"
          >
            <div class="lp-proj-head">
              <span class="lp-proj-dot" :style="{ background: p.color }"></span>
              <b>{{ p.name }}</b>
              <em v-if="p.tag" :style="{ color: p.color }">{{ p.tag }}</em>
              <span v-if="p.status === 'ready'" class="lp-proj-meta">{{ p.units }} 道工序</span>
              <span v-else class="lp-proj-meta plan">规划中</span>
            </div>
            <p>{{ p.desc }}</p>
            <div class="lp-proj-foot">
              <span v-if="p.status === 'ready' && selected === p.id" class="lp-check">已选择 ✓</span>
              <span v-else-if="p.status === 'ready' && selected !== p.id" class="lp-pick">点击选择</span>
            </div>
          </div>
        </div>
        <div class="lp-enter-bar">
          <span class="lp-hint" :class="{ show: hint }">{{ hint || '已选择：' + (projects.find(p => p.id === selected)?.name || '') }}</span>
          <button class="btn-primary big" :class="{ loading: entering }" @click="go">
            <span v-if="!entering">启动数字孪生工作台</span>
            <span v-else><i class="spin"></i>正在初始化仿真引擎…</span>
          </button>
        </div>
      </section>
    </main>

    <footer class="lp-foot">
      <span>工业能碳智控平台</span>
      <i>·</i>
      <span>软硬一体 · 云边协同 · 智控未来</span>
      <i>·</i>
      <span>© 2026 haiyisoftware</span>
    </footer>
  </div>
</template>

<script setup>
import { ref } from 'vue'

/* ---------------- 核心能力卡片 ---------------- */
const caps = [
  {
    t: '自研云边协同系统',
    d: '云端 K3s + KubeEdge CloudCore 作为唯一控制平面，边缘 EdgeCore 经 CloudHub 安全长连，控制下发与数据回传双通道毫秒级。',
    pts: ['控制面统一云端管理', '数据双通道实时回传', '断线自动重连自愈'],
    svg: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 10 H20 A1.5 1.5 0 0 1 21.5 11.5 V18 A1.5 1.5 0 0 1 20 19.5 H4 A1.5 1.5 0 0 1 2.5 18 V8 A1.5 1.5 0 0 1 4 6.5 H9 L11 9 H20 A1.5 1.5 0 0 1 21.5 10.5 V11.5" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M7 15 H9 M15 15 H17" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
  },
  {
    t: '软硬一体 · 能碳一体机',
    d: '工业级整机软硬件深度定制，开箱即用、部署即上云。硬件采集、边缘计算与云端管控一体交付，无需现场拼装调试。',
    pts: ['工业级硬件预装预调', '开箱即用免配置', '软硬件一体化交付'],
    svg: '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="3" width="18" height="13" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M3 7.5 H21 M12 7.5 V16 M8.5 16 H15.5" stroke="currentColor" stroke-width="1.1"/><path d="M7 10.5 H10 M14 13.5 H17" stroke="currentColor" stroke-width="1.1" stroke-linecap="round"/><path d="M8 20 H16 M12 16 V20" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  },
  {
    t: '快速设备模型建立与下发',
    d: '基于 KubeEdge DeviceModel / Device 五协议设备模型可视化 CRUD，YAML 一键生成、秒级下发到边缘，即建即用。',
    pts: ['五协议设备模型 CRUD', 'YAML 模板一键生成', '模型下发即建即用'],
    svg: '<svg viewBox="0 0 24 24" fill="none"><rect x="4" y="4" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.3"/><rect x="13" y="4" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.3"/><rect x="4" y="13" width="7" height="7" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M13 16.5 H20 M16.5 13 V20" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
  },
  {
    t: '远程下发 AI 模型',
    d: 'AI 优化模型 / 采集程序支持云端远程一键下发与版本管理，边缘免现场、免登录，模型更新全程自动化。',
    pts: ['云端远程部署模型', '版本管理与回滚', '采集程序远程升级'],
    svg: '<svg viewBox="0 0 24 24" fill="none"><rect x="3" y="4" width="18" height="11" rx="1.5" stroke="currentColor" stroke-width="1.3"/><path d="M3 9 H21" stroke="currentColor" stroke-width="1.1"/><path d="M6 6.5 H8 M10 6.5 H12" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/><path d="M12 15 V18 M8 18 H16 M5 20 H19" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/><path d="M17.5 6 L20 6 M20 6 V4 M20 6 L22 6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  },
  {
    t: '傻瓜式部署盒子',
    d: 'edgecore 模板渲染 + token / caHash 自动生成，现场一条命令完成接入，约 10 分钟上线，无需专业运维。',
    pts: ['部署包自动生成', '一条命令接入', '无专业运维要求'],
    svg: '<svg viewBox="0 0 24 24" fill="none"><path d="M12 3 L21 8 V16 L12 21 L3 16 V8 Z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/><path d="M12 8 L16.5 10.5 V15.5 L12 18 L7.5 15.5 V10.5 Z" stroke="currentColor" stroke-width="1.1" stroke-linejoin="round"/><path d="M12 3 V6 M12 18 V21" stroke="currentColor" stroke-width="1" stroke-linecap="round"/></svg>',
  },
  {
    t: '完善的管理平台',
    d: '设备管理、关联映射、实时数据、消息流追踪、健康诊断一站式云端管控，设备上云即可远程运营。',
    pts: ['设备全生命周期管理', '实时数据与消息流', '健康诊断与告警'],
    svg: '<svg viewBox="0 0 24 24" fill="none"><path d="M4 13 H8 L10 7 L13 16 L15 11 L17 13 H20" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M3 4 H21 M4 4 V19 A1 1 0 0 0 5 20 H19 A1 1 0 0 0 20 19 V4" stroke="currentColor" stroke-width="1.2" stroke-linecap="round"/></svg>',
  },
]

/* ---------------- 云边协同架构 ---------------- */
const cloudRows = [
  { ic: '☁', t: 'K3s + KubeEdge CloudCore', d: '云端唯一控制平面，设备模型 / twins / 证书统一管理' },
  { ic: '⇄', t: 'cloud-agent 数据代理', d: '本地采集云端状态，经 MQTT 长连接毫秒级推送平台' },
  { ic: '▲', t: 'MQTT Broker 消息总线', d: 'data/# 实时遥测 · state / crds / logs 周期上报' },
  { ic: '▶', t: 'REST API 下发通道', d: '模型下发 / 配置同步 / 指令控制，云端直达边缘' },
]
const edgeRows = [
  { ic: '▦', t: 'EdgeCore 边缘节点', d: '经 CloudHub 10002 端口与云端保持安全长连接' },
  { ic: '◈', t: 'box-mapper 采集引擎', d: 'DMI twins + MQTT 双源实时上报，断线补传自愈' },
  { ic: '◆', t: 'AI 模型运行时', d: '本地推理执行，支持云端远程更新与版本管理' },
  { ic: '┿', t: '五协议设备接入', d: 'Modbus / OPC-UA / MQTT 等协议，物联设备即插即采' },
]

/* ---------------- 数字化能力横条 ---------------- */
const digitals = [
  '3D 数字孪生',
  '碳素流 / 能流核算',
  '情景推演与策略寻优',
  '碳市场实时行情',
  '实时遥测与预警',
  'AI 分析报告',
]

/* ---------------- 项目选择（进入系统） ---------------- */
const projects = [
  {
    id: 'steel-long', route: 'long', status: 'ready', color: '#3DA5FF',
    name: '钢铁企业 · 长流程', tag: '推荐',
    desc: '烧结 → 球团 → 焦化 → 高炉 → 转炉 → 精炼 → 连铸 → 轧钢',
    units: 10,
  },
  {
    id: 'steel-short', route: 'short', status: 'ready', color: '#3ECF8E',
    name: '钢铁企业 · 短流程', tag: '低碳',
    desc: '电弧炉 → 精炼 → 连铸 → 轧钢，废钢短流程低碳冶炼',
    units: 5,
  },
  { id: 'cement', status: 'plan', color: '#6B7683', name: '水泥企业', desc: '新型干法水泥窑炉线', units: 0 },
  { id: 'chemical', status: 'plan', color: '#6B7683', name: '化工企业', desc: '石化化工装置线', units: 0 },
  { id: 'nonferrous', status: 'plan', color: '#6B7683', name: '有色企业', desc: '铜铝冶炼生产线', units: 0 },
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

function go() {
  if (entering.value) return
  const p = projects.find((x) => x.id === selected.value)
  if (!p || p.status !== 'ready') return
  entering.value = true
  hint.value = ''
  emit('open', p.route)
}

function goToEnter() {
  document.querySelector('#enter')?.scrollIntoView({ behavior: 'smooth' })
}
function goToCaps() {
  document.querySelector('#caps')?.scrollIntoView({ behavior: 'smooth' })
}
</script>

<style scoped>
/* ================= 根容器：全屏深色工业风 ================= */
.lp-root {
  position: fixed; inset: 0; z-index: 1000;
  display: flex; flex-direction: column;
  background: radial-gradient(1200px 600px at 15% -10%, #12233A 0%, #0B111A 55%) , #0B111A;
  color: #E6EDF3;
  font-family: var(--ui, -apple-system, 'Segoe UI', 'PingFang SC', 'Microsoft YaHei', sans-serif);
  overflow: hidden;
}

/* 网格背景 */
.lp-bg {
  position: absolute; inset: 0; pointer-events: none;
  background-image:
    linear-gradient(rgba(80, 120, 170, .07) 1px, transparent 1px),
    linear-gradient(90deg, rgba(80, 120, 170, .07) 1px, transparent 1px);
  background-size: 44px 44px;
  mask-image: radial-gradient(ellipse 90% 70% at 50% 30%, #000 40%, transparent 100%);
  -webkit-mask-image: radial-gradient(ellipse 90% 70% at 50% 30%, #000 40%, transparent 100%);
}
.lp-glow { position: absolute; border-radius: 50%; filter: blur(90px); pointer-events: none; }
.lp-glow.g1 { width: 520px; height: 520px; top: -180px; left: 8%; background: rgba(47, 134, 204, .16); }
.lp-glow.g2 { width: 420px; height: 420px; bottom: -160px; right: 4%; background: rgba(56, 184, 208, .10); }

/* ================= 顶部导航 ================= */
.lp-nav {
  position: relative; z-index: 3;
  display: flex; align-items: center; gap: 28px;
  padding: 14px 40px;
  border-bottom: 1px solid rgba(90, 130, 180, .22);
  background: rgba(11, 17, 26, .72);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.lp-brand { display: flex; align-items: center; gap: 12px; }
.lp-logo {
  width: 38px; height: 38px; color: #3DA5FF;
  filter: drop-shadow(0 0 10px rgba(61, 165, 255, .5));
}
.lp-logo svg { width: 100%; height: 100%; }
.lp-brand-tx b { display: block; font-size: 16px; font-weight: 600; letter-spacing: 1px; }
.lp-brand-tx span { display: block; font-size: 8.5px; letter-spacing: 1.6px; color: #5F7A99; margin-top: 2px; }
.lp-menu { display: flex; gap: 22px; margin-left: auto; }
.lp-menu a {
  color: #93A1B3; font-size: 13px; text-decoration: none;
  padding: 4px 2px; border-bottom: 2px solid transparent; transition: color .15s, border-color .15s;
}
.lp-menu a:hover { color: #E6EDF3; border-color: #3DA5FF; }
.lp-enter-btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 7px 18px; font-size: 13px; color: #fff;
  background: linear-gradient(180deg, #3DA5FF, #2F86CC);
  border: 1px solid #5CB2FF; border-radius: 3px; cursor: pointer;
  box-shadow: 0 2px 10px rgba(61, 165, 255, .35);
  transition: filter .15s;
}
.lp-enter-btn:hover { filter: brightness(1.12); }
.lp-arr { font-size: 14px; }

/* ================= 主内容 ================= */
.lp-main {
  position: relative; z-index: 2;
  flex: 1; overflow-y: auto; overflow-x: hidden;
  scroll-behavior: smooth;
}
.lp-main::-webkit-scrollbar { width: 10px; }
.lp-main::-webkit-scrollbar-thumb { background: #2A3B52; border-radius: 5px; }

/* ================= Hero ================= */
.lp-hero {
  display: grid; grid-template-columns: 1.15fr 1fr; gap: 40px;
  padding: 64px 72px 56px; align-items: center;
  max-width: 1360px; margin: 0 auto;
}
.lp-tagline {
  display: inline-flex; align-items: center; gap: 10px;
  font-size: 12px; letter-spacing: 2px; color: #5FC9E0;
  padding: 5px 14px; border: 1px solid rgba(95, 201, 224, .35); border-radius: 20px;
  background: rgba(95, 201, 224, .08); margin-bottom: 20px;
}
.lp-tagline i { width: 6px; height: 6px; border-radius: 50%; background: #38B8D0; box-shadow: 0 0 8px #38B8D0; }
.lp-title {
  margin: 0 0 16px;
  font-size: 44px; font-weight: 700; letter-spacing: 2px; line-height: 1.15;
  background: linear-gradient(92deg, #FFFFFF 20%, #8FC7F0 70%, #38B8D0 100%);
  -webkit-background-clip: text; background-clip: text; color: transparent;
}
.lp-sub { margin: 0 0 28px; font-size: 14.5px; line-height: 1.9; color: #A9B7C9; max-width: 560px; }
.lp-sub b { color: #5FC9E0; font-weight: 600; }
.lp-cta { display: flex; gap: 14px; margin-bottom: 34px; }
.btn-primary {
  display: inline-flex; align-items: center; justify-content: center; gap: 8px;
  padding: 11px 30px; font-size: 14px; font-weight: 500; letter-spacing: 1px; color: #fff;
  background: linear-gradient(180deg, #3DA5FF, #2F86CC);
  border: 1px solid #5CB2FF; border-radius: 3px; cursor: pointer;
  box-shadow: 0 4px 18px rgba(61, 165, 255, .4);
  transition: filter .15s, transform .1s;
}
.btn-primary:hover { filter: brightness(1.12); }
.btn-primary:active { transform: translateY(1px); }
.btn-primary.big { padding: 13px 40px; font-size: 15px; }
.btn-primary.loading { cursor: wait; opacity: .9; }
.btn-ghost {
  padding: 11px 26px; font-size: 14px; color: #A9B7C9;
  background: rgba(20, 32, 48, .6); border: 1px solid #2E4260; border-radius: 3px; cursor: pointer;
  transition: border-color .15s, color .15s;
}
.btn-ghost:hover { border-color: #3DA5FF; color: #E6EDF3; }
.spin { display: inline-block; width: 13px; height: 13px; margin-right: 6px; border-radius: 50%; border: 2px solid rgba(255,255,255,.35); border-top-color: #fff; animation: lp-spin .7s linear infinite; vertical-align: -2px; }
@keyframes lp-spin { to { transform: rotate(360deg) } }

.lp-stats {
  display: grid; grid-template-columns: repeat(4, auto); gap: 0;
  border: 1px solid rgba(90, 130, 180, .25); border-radius: 4px;
  background: rgba(13, 21, 33, .6); max-width: 560px;
}
.lp-stat { padding: 14px 22px; border-right: 1px solid rgba(90, 130, 180, .2); }
.lp-stat:last-child { border-right: none; }
.lp-stat b { display: block; font-size: 18px; font-weight: 600; color: #5FC9E0; letter-spacing: .5px; }
.lp-stat span { display: block; font-size: 10.5px; color: #7A8CA3; margin-top: 3px; }

/* Hero 右侧：云边协同抽象图 */
.lp-hero-r { position: relative; }
.lp-arch-art {
  border: 1px solid rgba(90, 130, 180, .3); border-radius: 8px;
  background: linear-gradient(180deg, rgba(16, 26, 40, .85), rgba(10, 17, 27, .85));
  padding: 22px 22px 18px;
  box-shadow: 0 12px 40px rgba(0, 0, 0, .45);
}
.aa-cloud { position: relative; }
.aa-node {
  display: flex; flex-direction: column; align-items: center; gap: 5px;
  padding: 14px 10px; border-radius: 6px; text-align: center;
  border: 1px solid rgba(90, 130, 180, .35);
  background: rgba(61, 165, 255, .06);
}
.aa-node b { font-size: 13px; font-weight: 600; }
.aa-node span { font-size: 10px; color: #7A8CA3; }
.aa-ic { width: 26px; height: 26px; color: #3DA5FF; }
.aa-ic svg { width: 100%; height: 100%; }
.cloud-core { margin-bottom: 12px; }
.aa-chip {
  display: inline-block; font-size: 9.5px; padding: 2px 8px; border-radius: 10px;
  border: 1px solid rgba(95, 201, 224, .4); color: #5FC9E0;
  background: rgba(95, 201, 224, .08);
}
.aa-cloud > .aa-chip.tag { position: absolute; top: -11px; right: 10px; }
.aa-link {
  display: flex; flex-direction: column; align-items: center; gap: 4px;
  padding: 14px 0; position: relative;
}
.aa-beam { width: 2px; height: 46px; background: linear-gradient(180deg, #3DA5FF, #38B8D0); box-shadow: 0 0 12px rgba(61, 165, 255, .8); }
.aa-link > span { font-size: 9px; color: #7A8CA3; letter-spacing: .5px; }
.aa-link .aa-up { color: #3ECF8E; }
.aa-link .aa-down { color: #3DA5FF; }
.aa-edge { position: relative; }
.aa-edge .box { border-color: rgba(62, 207, 142, .4); background: rgba(62, 207, 142, .06); }
.aa-edge .box .aa-ic { color: #3ECF8E; }
.aa-edge-sub { display: flex; justify-content: center; gap: 8px; margin-top: 12px; }

/* ================= Section 通用 ================= */
.lp-section { max-width: 1280px; margin: 0 auto; padding: 56px 40px 12px; }
.lp-sec-head { display: flex; align-items: baseline; gap: 14px; margin-bottom: 26px; }
.lp-sec-title {
  margin: 0; font-size: 24px; font-weight: 600; letter-spacing: 1px;
  display: flex; align-items: center; gap: 12px;
}
.lp-sec-title i {
  font-style: normal; font-size: 12px; font-weight: 600; letter-spacing: 1px;
  color: #3DA5FF; border: 1px solid rgba(61, 165, 255, .5); border-radius: 3px;
  padding: 3px 7px;
}
.lp-sec-en { font-size: 10px; letter-spacing: 2.4px; color: #4A5F7C; }

/* ================= 核心能力卡片 ================= */
.lp-cards {
  display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px;
}
.lp-card {
  padding: 22px 20px 18px;
  border: 1px solid rgba(90, 130, 180, .22); border-radius: 6px;
  background: linear-gradient(180deg, rgba(17, 27, 42, .9), rgba(12, 20, 32, .9));
  transition: border-color .2s, transform .2s, box-shadow .2s;
}
.lp-card:hover {
  border-color: rgba(61, 165, 255, .6);
  transform: translateY(-3px);
  box-shadow: 0 10px 30px rgba(0, 0, 0, .4);
}
.lp-card-ic { width: 34px; height: 34px; color: #3DA5FF; margin-bottom: 12px; }
.lp-card-ic svg { width: 100%; height: 100%; }
.lp-card > b { display: block; font-size: 15px; font-weight: 600; margin-bottom: 8px; }
.lp-card > span { display: block; font-size: 12px; line-height: 1.75; color: #93A1B3; min-height: 62px; }
.lp-card-pts { list-style: none; margin: 12px 0 0; padding: 12px 0 0; border-top: 1px dashed rgba(90, 130, 180, .25); }
.lp-card-pts li {
  position: relative; font-size: 11px; color: #7A8CA3; padding: 3px 0 3px 16px;
}
.lp-card-pts li::before {
  content: ''; position: absolute; left: 2px; top: 9px;
  width: 5px; height: 5px; transform: rotate(45deg);
  background: #3DA5FF; border-radius: 1px;
}

/* ================= 云边协同架构 ================= */
.lp-arch {
  display: grid; grid-template-columns: 1fr 220px 1fr; gap: 18px; align-items: stretch;
}
.arch-side {
  border: 1px solid rgba(90, 130, 180, .25); border-radius: 6px;
  background: rgba(14, 22, 35, .8); padding: 16px;
}
.arch-side.cloud { border-color: rgba(61, 165, 255, .4); }
.arch-side.edge { border-color: rgba(62, 207, 142, .4); }
.arch-side-tag {
  font-size: 11px; letter-spacing: 1.5px; font-weight: 600;
  padding-bottom: 12px; margin-bottom: 8px;
  border-bottom: 1px solid rgba(90, 130, 180, .25);
  color: #5FC9E0;
}
.arch-side.edge .arch-side-tag { color: #3ECF8E; }
.arch-row { display: flex; align-items: flex-start; gap: 12px; padding: 10px 4px; }
.arch-row + .arch-row { border-top: 1px dashed rgba(90, 130, 180, .18); }
.arch-row-ic {
  flex: none; width: 26px; height: 26px; display: flex; align-items: center; justify-content: center;
  font-size: 13px; color: #3DA5FF;
  border: 1px solid rgba(61, 165, 255, .4); border-radius: 4px; background: rgba(61, 165, 255, .08);
}
.arch-side.edge .arch-row-ic { color: #3ECF8E; border-color: rgba(62, 207, 142, .4); background: rgba(62, 207, 142, .08); }
.arch-row-tx b { display: block; font-size: 12.5px; font-weight: 600; }
.arch-row-tx span { display: block; font-size: 10.5px; line-height: 1.6; color: #7A8CA3; margin-top: 3px; }

.arch-mid { display: flex; flex-direction: column; justify-content: center; align-items: center; gap: 16px; }
.arch-beams { display: flex; flex-direction: column; gap: 14px; width: 100%; }
.beam {
  display: flex; align-items: center; justify-content: center; gap: 8px;
  font-size: 11px; color: #A9B7C9;
  padding: 8px 10px; border: 1px dashed rgba(90, 130, 180, .35); border-radius: 4px;
  background: rgba(14, 22, 35, .6);
}
.beam span { font-size: 10px; }
.beam.down span { color: #3DA5FF; }
.beam.up span { color: #3ECF8E; }
.arch-mid-chip {
  font-size: 10px; letter-spacing: 1px; color: #5FC9E0;
  border: 1px solid rgba(95, 201, 224, .35); border-radius: 14px;
  padding: 4px 12px; background: rgba(95, 201, 224, .07); white-space: nowrap;
}

/* ================= 数字化能力横条 ================= */
.lp-capbar {
  max-width: 1280px; margin: 46px auto 0; padding: 0 40px;
  display: flex; flex-wrap: wrap; gap: 10px; justify-content: center;
}
.capbar-item {
  display: inline-flex; align-items: center; gap: 8px;
  font-size: 12px; color: #A9B7C9;
  border: 1px solid rgba(90, 130, 180, .25); border-radius: 20px;
  padding: 7px 16px; background: rgba(14, 22, 35, .7);
}
.capbar-dot { width: 6px; height: 6px; border-radius: 50%; background: #3DA5FF; box-shadow: 0 0 6px #3DA5FF; }

/* ================= 进入系统 ================= */
.lp-enter { padding-bottom: 48px; }
.lp-enter-tip { margin: 0 0 20px; font-size: 12.5px; color: #7A8CA3; }
.lp-projects {
  display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px;
  margin-bottom: 30px;
}
.lp-proj {
  padding: 16px 18px; border-radius: 6px; cursor: pointer;
  border: 1px solid rgba(90, 130, 180, .25);
  background: rgba(14, 22, 35, .75);
  transition: border-color .15s, transform .15s, box-shadow .15s;
}
.lp-proj.sel { border-color: #3DA5FF; box-shadow: 0 0 0 1px rgba(61, 165, 255, .5), 0 8px 24px rgba(0, 0, 0, .35); }
.lp-proj.plan { opacity: .42; cursor: not-allowed; }
.lp-proj-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.lp-proj-dot { width: 8px; height: 8px; border-radius: 50%; box-shadow: 0 0 8px currentColor; }
.lp-proj-head b { font-size: 14px; font-weight: 600; }
.lp-proj-head em { font-style: normal; font-size: 9px; border: 1px solid currentColor; border-radius: 2px; padding: 0 5px; line-height: 1.6; }
.lp-proj-meta { margin-left: auto; font-size: 9.5px; color: #5F7A99; font-family: var(--mono, Menlo, monospace); }
.lp-proj-meta.plan { font-family: var(--ui, sans-serif); border: 1px dashed #3A4C66; border-radius: 3px; padding: 0 6px; }
.lp-proj p { margin: 10px 0 12px; font-size: 11.5px; line-height: 1.6; color: #7A8CA3; }
.lp-proj-foot { display: flex; justify-content: flex-end; min-height: 16px; }
.lp-check { font-size: 11px; color: #3ECF8E; }
.lp-pick { font-size: 11px; color: #5F7A99; }
.lp-proj.sel .lp-pick { display: none; }
.lp-proj .lp-check { display: none; }
.lp-proj.sel .lp-check { display: inline; }

.lp-enter-bar { display: flex; align-items: center; justify-content: center; gap: 24px; }
.lp-hint { font-size: 12px; color: #3ECF8E; min-height: 18px; transition: opacity .2s; }

/* ================= 页脚 ================= */
.lp-foot {
  position: relative; z-index: 2;
  display: flex; align-items: center; justify-content: center; gap: 12px;
  padding: 16px; font-size: 11px; color: #4A5F7C;
  border-top: 1px solid rgba(90, 130, 180, .18);
  background: rgba(11, 17, 26, .8);
}
.lp-foot i { font-style: normal; color: #2A3B52; }

/* ================= 响应式 ================= */
@media (max-width: 1080px) {
  .lp-hero { grid-template-columns: 1fr; padding: 44px 40px 40px; }
  .lp-arch { grid-template-columns: 1fr; }
  .arch-mid { flex-direction: row; }
  .lp-cards { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 720px) {
  .lp-nav { padding: 12px 20px; gap: 14px; }
  .lp-menu { display: none; }
  .lp-hero { padding: 32px 20px 28px; }
  .lp-title { font-size: 30px; }
  .lp-stats { grid-template-columns: repeat(2, 1fr); }
  .lp-stat { border-bottom: 1px solid rgba(90, 130, 180, .2); }
  .lp-cards { grid-template-columns: 1fr; }
  .lp-section { padding: 40px 20px 8px; }
  .lp-capbar { padding: 0 20px; }
}
</style>
