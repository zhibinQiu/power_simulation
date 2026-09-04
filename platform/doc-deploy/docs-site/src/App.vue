<script setup>
import { computed, onMounted, ref } from 'vue'
import { route, routeQuery, navigate } from './router'
import { docs } from './data'
import HomePage from './views/HomePage.vue'
import DocPage from './views/DocPage.vue'

const isHome = computed(() => route.value === '/' || route.value === '')
const currentDoc = computed(() => docs.find((d) => d.path === route.value))
const backHref = computed(() => routeQuery.value.from || '')

// 明暗模式：默认浅色，记忆在 localStorage；与平台 frontend 一致支持夜间（冷蓝黑）
const dark = ref(false)
const KEY = 'docs-site-dark'
function applyDark(v) {
  dark.value = v
  document.body.classList.toggle('dark', v)
}
function toggleDark() {
  applyDark(!dark.value)
  localStorage.setItem(KEY, dark.value ? '1' : '0')
}
onMounted(() => {
  const saved = localStorage.getItem(KEY)
  if (saved) applyDark(saved === '1')
})
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
      <button class="theme-toggle" :title="dark ? '切换到日间模式' : '切换到夜间模式'" @click="toggleDark">
        <svg v-if="dark" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round">
          <circle cx="8" cy="8" r="3.2" />
          <path d="M8 1.5v2M8 12.5v2M1.5 8h2M12.5 8h2M3.4 3.4l1.4 1.4M11.2 11.2l1.4 1.4M12.6 3.4l-1.4 1.4M4.8 11.2l-1.4 1.4" />
        </svg>
        <svg v-else viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M13.5 9.2A5.6 5.6 0 0 1 6.8 2.5a5.6 5.6 0 1 0 6.7 6.7Z" />
        </svg>
        <span>{{ dark ? '日间' : '夜间' }}</span>
      </button>
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

    <footer class="foot">能碳一体机 · 文档中心 · v2.1.0</footer>
  </div>
</template>
