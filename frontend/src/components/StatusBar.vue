<template>
  <!-- ============ 底栏状态条 ============ -->
  <footer class="statusbar">
    <span v-if="!store.license.activated" class="st lic-warn" @click="store.openAbout()"
          :title="t('产品未激活，点击在「关于本平台」中激活')">
      <span class="lic-tri">⚠</span> {{ t('产品未激活') }}
    </span>
    <span class="st"><span class="feed-dot" :class="'feed-' + store.feedStatus"></span> {{ t('实时链路') }} <span class="v">{{ feedText }}</span></span>
    <span v-if="store.newsTickerOn" class="st spacer news-ticker" :title="t('市场快讯 · 中国煤炭交易网（ctctc.cn）')">
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
    <span class="st mono"><span class="v">{{ clock }}</span></span>
    <span class="st st-notif" :class="{ open: notifOpen }" ref="notifBtn" @click="toggleNotif" :title="t('系统通知')">
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
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { api } from '../api/client'
import { t } from '../i18n'

const store = useSimStore()
const clock = ref('')
let timer = null

// —— 市场快讯（中国煤炭交易网）——
const newsItems = ref([])
const newsError = ref(false)
const newsDur = computed(() => Math.max(60, newsItems.value.length * 18)) // 滚动周期随条数自适应（每条约 18s，慢速舒缓）
let newsTimer = null

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

const feedText = computed(() => ({ open: t('已连接'), closed: t('已断开'), error: t('异常'), init: t('连接中…') }[store.feedStatus] || ''))

function tickClock() {
  const d = new Date(); const p = (x) => String(x).padStart(2, '0')
  clock.value = `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
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

onMounted(() => {
  tickClock(); timer = setInterval(tickClock, 1000)
  loadNews(); newsTimer = setInterval(loadNews, 5 * 60 * 1000) // 每 5 分钟刷新一次快讯
  document.addEventListener('click', onDocClick)
  document.addEventListener('keydown', onKey)
})
onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (newsTimer) clearInterval(newsTimer)
  document.removeEventListener('click', onDocClick)
  document.removeEventListener('keydown', onKey)
})
</script>
