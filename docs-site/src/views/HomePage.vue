<script setup>
import { docs } from '../data'
import { navigate } from '../router'

const vision = [
  {
    key: 'save',
    title: '低耗能',
    desc: 'AI 算法调度持续挖掘日常运行中的节能空间：焦比怎么调、喷煤配多少、工序能耗怎么平衡，一遍遍仿真寻优，花小钱、办大事，让每一度电、每一吨燃料都物尽其用。',
  },
  {
    key: 'low-carbon',
    title: '低碳',
    desc: '碳素流仿真与碳排放核算双引擎，从"算得清"到"降得下"：每一次仿真同步算出能耗、碳排与成本，帮助企业以可承受的代价走向深度减排。',
  },
  {
    key: 'earth',
    title: '保护地球',
    desc: '面向钢铁、水泥、化工、有色等全国碳市场重点控排行业及更多高耗能行业，让每一家控排企业都拥有一双智慧的眼睛和一颗 AI 的大脑，让节能减碳变得简单、确定、看得见，共同守护我们的绿色家园。',
  },
]

const techs = [
  { name: '3D 数字孪生', desc: '20+ 工序模型，热力图着色与物流粒子动画' },
  { name: '云边协同', desc: 'KubeEdge 云边一体，能碳一体机一条命令接入' },
  { name: '碳素流仿真引擎', desc: '设备级物料平衡，先能后碳双重核算' },
  { name: 'AI 优化模型引擎', desc: 'GA / PSO / RL / 时序预测 / 聚类五套在线模型' },
  { name: 'LLM 智能体', desc: '自然语言策略解析、AI 报告与知识库' },
  { name: '碳市场行情', desc: 'CEA / CCER 实时行情与价格趋势预测' },
  { name: '实时遥测', desc: 'WebSocket + MQTT 云端 Broker 真实读数' },
  { name: '时序数据库', desc: 'TDengine 云端存储与历史曲线降采样' },
]
</script>

<template>
  <div class="home">
    <section class="hero">
      <h1>工业能碳智控平台 <span class="hero-ver">v2.0.0</span></h1>
      <p>懂能、懂碳、懂市场的工业级智能平台，为每一家控排企业的节能降碳而生。</p>
    </section>

    <section class="vision">
      <h2 class="block-title">平台愿景</h2>
      <p class="block-sub">低耗能 · 低碳 · 保护地球 —— 让节能减碳从「拼投入」走向「拼智慧」</p>
      <div class="vision-grid">
        <div v-for="v in vision" :key="v.key" class="vision-card">
          <span class="vision-tag">{{ v.title }}</span>
          <p>{{ v.desc }}</p>
        </div>
      </div>
    </section>

    <section class="tech">
      <h2 class="block-title">前沿技术</h2>
      <p class="block-sub">以最新数字化技术，赋能企业能碳管理全流程</p>
      <div class="tech-grid">
        <div v-for="t in techs" :key="t.name" class="tech-item">
          <h3>{{ t.name }}</h3>
          <p>{{ t.desc }}</p>
        </div>
      </div>
    </section>

    <section class="cards">
      <div
        v-for="(d, i) in docs"
        :key="d.key"
        class="card"
        :style="{ '--accent': d.accent }"
        @click="navigate(d.path)"
      >
        <div class="card-num">{{ String(i + 1).padStart(2, '0') }}</div>
        <h2>{{ d.nav }}</h2>
        <p>{{ d.desc }}</p>
        <span class="card-go">开始阅读 →</span>
      </div>
    </section>
  </div>
</template>
