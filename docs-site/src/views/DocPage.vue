<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { renderMarkdown } from '../utils/markdown'

const props = defineProps({
  doc: { type: Object, required: true },
})

const scrollEl = ref(null)
const active = ref('')
const showTop = ref(false)

const flatToc = computed(() =>
  props.doc.sections.map((s, i) => ({ id: s.id, title: s.title, no: i + 1 })),
)
const secNo = computed(() => {
  const m = new Map(props.doc.sections.map((s, i) => [s.id, i + 1]))
  return (id) => m.get(id) || ''
})

function go(id) {
  active.value = id
  const el = document.getElementById(id)
  if (el && scrollEl.value) {
    scrollEl.value.scrollTo({ top: el.offsetTop - 20, behavior: 'smooth' })
  }
}

function onScroll() {
  const el = scrollEl.value
  if (!el) return
  showTop.value = el.scrollTop > 400
  let cur = props.doc.sections.length ? props.doc.sections[0].id : ''
  for (const s of props.doc.sections) {
    const node = document.getElementById(s.id)
    if (node && node.offsetTop <= el.scrollTop + 140) cur = s.id
  }
  if (cur !== active.value) active.value = cur
}

function toTop() {
  if (scrollEl.value) scrollEl.value.scrollTo({ top: 0, behavior: 'smooth' })
}

function reset() {
  active.value = props.doc.sections.length ? props.doc.sections[0].id : ''
  showTop.value = false
  if (scrollEl.value) scrollEl.value.scrollTop = 0
}

watch(
  () => props.doc,
  () => {
    nextTick(reset)
  },
)

onMounted(reset)
onBeforeUnmount(() => {})
</script>

<template>
  <div class="doc" :style="{ '--accent': doc.accent }">
    <aside class="toc">
      <div class="toc-title">{{ doc.nav }}</div>
      <div class="toc-list">
        <a
          v-for="t in flatToc"
          :key="t.id"
          :class="{ active: active === t.id }"
          @click.prevent="go(t.id)"
        >
          <span class="toc-no">{{ t.no }}</span>{{ t.title }}
        </a>
      </div>
    </aside>

    <div ref="scrollEl" class="doc-scroll" @scroll.passive="onScroll">
      <div class="doc-body">
        <header class="doc-head">
          <h1>{{ doc.nav }}</h1>
        </header>
        <section
          v-for="s in doc.sections"
          :key="s.id"
          :id="s.id"
          class="doc-section"
        >
          <h2 class="sec-title">
            <span class="sec-badge">{{ secNo(s.id) }}</span>{{ s.title }}
          </h2>
          <div class="doc-md" v-html="renderMarkdown(s.body)"></div>
        </section>
        <footer class="doc-end">—— {{ doc.nav }} 完 ——</footer>
      </div>
      <button v-show="showTop" class="to-top" @click="toTop">回到顶部</button>
    </div>
  </div>
</template>
