<template>
  <!-- ============ 底栏状态条 ============ -->
  <footer class="statusbar">
    <!-- 场景加载进度：底栏最左侧常驻位，加载场景 / 切场景 / 启动初始化时显式进度
         与 spinner，无耗时操作时隐藏（不要污染底栏，做成"故障对讲机"，平时静默）。 -->
    <span v-if="sceneLoadVisible" class="st scene-loading" :class="sceneLoadCls" :title="sceneLoadTitle">
      <span class="scene-load-ic" aria-hidden="true">
        <!-- 进行中：CSS spinner -->
        <span v-if="store.sceneLoad.active" class="scene-load-spinner"></span>
        <!-- 完成：√ 对勾 -->
        <svg v-else-if="store.sceneLoad.phase === 'ready'" viewBox="0 0 16 16" width="11" height="11">
          <path d="M3 8.5 6.5 12 13 4.5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
        <!-- 失败：✕ -->
        <svg v-else viewBox="0 0 16 16" width="11" height="11">
          <path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="2" stroke-linecap="round" fill="none"/>
        </svg>
      </span>
      <span class="scene-load-label">{{ sceneLoadLabel }}</span>
      <span v-if="store.sceneLoad.active" class="scene-load-track" aria-hidden="true">
        <span class="scene-load-fill" :style="{ width: sceneLoadPct + '%' }"></span>
      </span>
    </span>
    <!-- 快讯条：工程选择页（欢迎页）不显示，进入主界面后随开关恢复 -->
    <span v-if="store.newsTickerOn && !store.welcomeOn" class="st spacer news-ticker">
      <span class="news-scroll" v-if="newsItems.length">
        <span class="news-track" :style="{ '--news-dur': newsDur + 's' }">
          <span class="news-list">
            <span v-for="(n, i) in newsItems" :key="n.id + '-' + i" class="news-item"><span class="news-time">{{ fmtTime(n.time) }}</span>{{ n.content }}</span>
          </span>
          <span class="news-list" aria-hidden="true">
            <span v-for="(n, i) in newsItems" :key="'dup-' + n.id + '-' + i" class="news-item"><span class="news-time">{{ fmtTime(n.time) }}</span>{{ n.content }}</span>
          </span>
        </span>
      </span>
      <span v-else class="nt-empty">{{ newsError ? t('快讯暂不可用') : t('快讯加载中…') }}</span>
    </span>
    <span class="st st-notif" :class="{ open: notifOpen }" ref="notifBtn" @click="toggleNotif">
      <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2a.5.5 0 0 1 .5.5v.542a4 4 0 0 1 3.001 3.865v2.69l.852 1.421a.5.5 0 0 1-.435.744H4.082a.5.5 0 0 1-.435-.744l.852-1.42v-2.69A4 4 0 0 1 7.5 3.042V2.5A.5.5 0 0 1 8 2zm-1.16 10h2.32a2.003 2.003 0 0 1-3.868-.568l1.548.568zm3.66-.003l-.99-1.65h-3.02l-.99 1.65h4.01z"/></svg>
      <span v-if="store.unreadNotifs > 0" class="ntf-badge">{{ store.unreadNotifs > 99 ? '99+' : store.unreadNotifs }}</span>
    </span>
  </footer>

  <!-- ============ 系统通知中心（仿 VS Code） ============ -->
  <transition name="fade">
    <div v-if="notifOpen" class="notif-center" @click.stop>
      <div class="notif-head">
        <span class="ntf-title">{{ t('系统通知') }}</span>
        <span class="ntf-actions">
          <button class="ntf-btn" @click="store.markAllNotificationsRead()" :disabled="!store.notifications.length">{{ t('全部标为已读') }}</button>
          <button class="ntf-btn" @click="store.clearNotifications()" :disabled="!store.notifications.length">{{ t('清空') }}</button>
        </span>
      </div>
      <div class="notif-list" ref="listEl">
        <div v-if="!store.notifications.length" class="ntf-empty">
          <svg viewBox="0 0 16 16" aria-hidden="true"><path d="M8 2a.5.5 0 0 1 .5.5v.542a4 4 0 0 1 3.001 3.865v2.69l.852 1.421a.5.5 0 0 1-.435.744H4.082a.5.5 0 0 1-.435-.744l.852-1.42v-2.69A4 4 0 0 1 7.5 3.042V2.5A.5.5 0 0 1 8 2zm-1.16 10h2.32a2.003 2.003 0 0 1-3.868-.568l1.548.568zm3.66-.003l-.99-1.65h-3.02l-.99 1.65h4.01z"/></svg>
          <span>{{ t('暂无系统通知') }}</span>
        </div>
        <div v-for="n in sortedNotifs" :key="n.id" class="ntf-item" :class="['lv-' + n.level, { unread: !n.read }]" @click="store.markNotificationRead(n.id)">
          <span class="ntf-dot"></span>
          <div class="ntf-main">
            <div class="ntf-row">
              <span class="ntf-title2">{{ n.title }}</span>
              <span class="ntf-time">{{ fmtNotifTime(n.time) }}</span>
            </div>
            <div class="ntf-body">{{ n.body }}</div>
          </div>
          <button class="x-btn danger" :title="t('删除此通知')" @click.stop="store.removeNotification(n.id)">×</button>
        </div>
      </div>
    </div>
  </transition>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useSimStore } from '../stores/sim'
import { api } from '../api/client'
import { visiblePoll } from '../utils/poll.js'
import { t } from '../i18n'

const store = useSimStore()

// —— 场景加载进度（与 sim.sceneLoad 同源驱动）——
// 阶段推进顺序：data → design → calculate → code → ready
// 每个阶段占总 25%；给出底栏"加载条"的总进度（百分比）
const SCENE_LOAD_PHASES = ['data', 'design', 'calculate', 'code']
const SCENE_LOAD_PHASE_LABEL = {
  data: '正在加载场景数据…',
  design: '正在恢复编排方案…',
  calculate: '正在计算场景数据…',
  code: '正在加载三维引擎…',
}
// "完成"提示在 ready 后 1.6s 自动收起；其它等待时间一般不超过 2s，留点余量
const SCENE_LOAD_DONE_MS = 1600
const sceneLoadDoneAt = ref(0)
let sceneLoadDoneTimer = null
function bumpSceneLoadDone() {
  sceneLoadDoneAt.value = Date.now()
  if (sceneLoadDoneTimer) clearTimeout(sceneLoadDoneTimer)
  sceneLoadDoneTimer = setTimeout(() => { sceneLoadDoneAt.value = 0; sceneLoadDoneTimer = null }, SCENE_LOAD_DONE_MS)
}
function clearSceneLoadDone() {
  if (sceneLoadDoneTimer) { clearTimeout(sceneLoadDoneTimer); sceneLoadDoneTimer = null }
  sceneLoadDoneAt.value = 0
}
onBeforeUnmount(clearSceneLoadDone)

const sceneLoadVisible = computed(() => {
  const sl = store.sceneLoad
  if (!sl) return false
  if (sl.active) return true
  if (sl.phase === 'error') return true
  // ready 状态短暂高亮后收起（避免一直挂着 √）
  if (sl.phase === 'ready' && sl.seq > 0 && sceneLoadDoneAt.value) return true
  return false
})
const sceneLoadCls = computed(() => {
  const sl = store.sceneLoad
  if (sl.phase === 'error') return 'fail'
  if (!sl.active && sl.phase === 'ready') return 'done'
  return 'busy'
})
const sceneLoadLabel = computed(() => {
  const sl = store.sceneLoad
  if (sl.phase === 'error') return t('场景加载失败')
  if (!sl.active && sl.phase === 'ready') return t('加载完成')
  return t(SCENE_LOAD_PHASE_LABEL[sl.phase] || '正在加载场景…')
})
const sceneLoadTitle = computed(() => {
  const sl = store.sceneLoad
  if (sl.phase === 'error') return (sl.error && String(sl.error)) || t('场景加载失败')
  if (!sl.active && sl.phase === 'ready') return t('场景已就绪')
  return ''
})
const sceneLoadPct = computed(() => {
  const sl = store.sceneLoad
  const idx = SCENE_LOAD_PHASES.indexOf(sl.phase)
  if (idx < 0) return sl.phase === 'error' ? 100 : 0
  // 按阶段步进（25/50/75），末段封顶 90%：留一格给"收尾"，
  // 否则会看到"进度条已满 100% 但转圈还在转"的矛盾观感
  const total = SCENE_LOAD_PHASES.length
  return idx === total - 1 ? 90 : Math.round(((idx + 1) / total) * 100)
})
// 只在 active 翻转时动作：开始新一轮（→true）清掉残留，加载成功收尾（→false 且 ready）短暂挂 √。
// 不监听 phase：finishSceneLoad / failSceneLoad 都不自增 seq，靠 seq 变化抓不到结束时刻。
watch(() => store.sceneLoad.active, (active) => {
  if (active) clearSceneLoadDone()
  else if (store.sceneLoad.phase === 'ready') bumpSceneLoadDone()
})

// —— 市场快讯（中国煤炭交易网）——
const newsItems = ref([])
const newsError = ref(false)
const newsDur = computed(() => Math.max(60, newsItems.value.length * 18)) // 滚动周期随条数自适应（每条约 18s，慢速舒缓）
let stopNews = null

async function loadNews() {
  try {
    const r = await api.marketNews(1)
    if (r && r.ok && Array.isArray(r.items) && r.items.length) {
      newsItems.value = r.items
      newsError.value = false
    } else {
      newsItems.value = []
      newsError.value = true
    }
  } catch (_) {
    newsItems.value = []
    newsError.value = true
  }
}

function fmtTime(t) {
  const m = /^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}:\d{2})/.exec(String(t || ''))
  return m ? `${m[2]}-${m[3]} ${m[4]}` : String(t || '')
}

// —— 系统通知中心（底栏铃铛，仿 VS Code）——
const notifOpen = ref(false)
const notifBtn = ref(null)
const listEl = ref(null)
const sortedNotifs = computed(() => [...store.notifications].sort((a, b) => b.time - a.time))

function toggleNotif() {
  notifOpen.value = !notifOpen.value
  if (notifOpen.value) {
    store.markAllNotificationsRead()
    if (listEl.value) listEl.value.scrollTop = 0
  }
}
function closeNotif() { notifOpen.value = false }
function onDocClick(e) {
  if (notifBtn.value && notifBtn.value.contains(e.target)) return
  if (e.target.closest && e.target.closest('.notif-center')) return
  closeNotif()
}
function onKey(e) { if (e.key === 'Escape') closeNotif() }
function fmtNotifTime(t) {
  const d = new Date(t)
  const p = (x) => String(x).padStart(2, '0')
  return d.toDateString() === new Date().toDateString()
    ? `${p(d.getHours())}:${p(d.getMinutes())}`
    : `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 快讯轮询：欢迎页不显示快讯，也就不再请求（省一次外部抓取 + 5 分钟轮询）
function newsWanted() { return store.newsTickerOn && !store.welcomeOn }
function startNews() {
  if (stopNews || !newsWanted()) return
  loadNews()
  stopNews = visiblePoll(loadNews, 5 * 60 * 1000) // 每 5 分钟刷新一次快讯
}
function stopNewsPoll() { if (stopNews) { stopNews(); stopNews = null } }

onMounted(() => {
  // 可见性感知：后台标签不拉快讯（切回可见时立即补一轮）
  startNews()
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})
watch(newsWanted, (on) => { on ? startNews() : stopNewsPoll() })
onBeforeUnmount(() => {
  if (stopNews) { stopNews(); stopNews = null }
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})
</script>
