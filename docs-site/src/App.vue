<script setup>
import { computed } from 'vue'
import { route, routeQuery, navigate } from './router'
import { docs } from './data'
import HomePage from './views/HomePage.vue'
import DocPage from './views/DocPage.vue'

const isHome = computed(() => route.value === '/' || route.value === '')
const currentDoc = computed(() => docs.find((d) => d.path === route.value))
const backHref = computed(() => routeQuery.value.from || '')
</script>

<template>
  <div class="site">
    <header class="topbar">
      <div class="brand" @click="navigate('/')">
        <span class="brand-badge">能碳</span>
        <span class="brand-name">能碳一体机 · 文档中心</span>
      </div>
      <nav class="nav">
        <a
          v-for="d in docs"
          :key="d.key"
          :class="{ active: currentDoc && currentDoc.key === d.key }"
          :href="d.path"
          @click.prevent="navigate(d.path)"
        >{{ d.nav }}</a>
      </nav>
      <a v-if="backHref" class="back-platform" :href="backHref">返回平台</a>
      <a v-else class="back-platform" href="#/" @click.prevent="navigate('/')">首页</a>
    </header>

    <main class="main">
      <HomePage v-if="isHome" />
      <DocPage v-else-if="currentDoc" :doc="currentDoc" />
      <div v-else class="notfound">
        <h2>页面不存在</h2>
        <a href="#/" @click.prevent="navigate('/')">返回首页</a>
      </div>
    </main>

    <footer class="foot">能碳一体机 · 文档中心 · v2.0.0</footer>
  </div>
</template>
