<script setup>
import { docs } from '../data'
import { navigate } from '../router'
</script>

<template>
  <div class="home">
    <section class="hero">
      <h1>能碳一体机 · 文档中心</h1>
      <p>帮助您快速了解平台、上手使用，并深入技术实现。选择下方入口开始阅读。</p>
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
