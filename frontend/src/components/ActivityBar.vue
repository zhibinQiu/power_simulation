<template>
  <aside class="activitybar" role="navigation" :aria-label="t('活动栏')">
    <button
      v-for="b in buttons"
      :key="b.id"
      class="act-btn"
      :class="{ on: store.activityView === b.id }"
      :title="t(b.title)"
      :aria-label="t(b.title)"
      @click="onClick(b.id)"
    >
      <Icon :name="b.icon" :size="20" :stroke="1.5" />
      <span v-if="b.badge && b.badge() > 0" class="act-badge">{{ b.badge() }}</span>
    </button>
    <div class="act-sp"></div>
    <div class="act-bottom">
      <button class="act-btn" :title="t('收起/展开左侧栏')" :aria-label="t('收起/展开左侧栏')" @click="store.toggleLeft()">
        <Icon name="panelLeft" :size="20" :stroke="1.5" />
      </button>
    </div>
  </aside>
</template>

<script setup>
import { useSimStore } from '../stores/sim'
import Icon from './Icon.vue'
import { t } from '../i18n'

const store = useSimStore()

// 活动栏：场景 / 资源管理器 / 搜索 / 连接
const buttons = [
  { id: 'scene', icon: 'scene3d', title: '场景', badge: null },
  { id: 'explorer', icon: 'open', title: '资源管理器', badge: null },
  { id: 'search', icon: 'search', title: '搜索', badge: null },
  { id: 'connections', icon: 'link', title: '连接（数据源管理）', badge: () => (store.dataSources || []).filter((s) => s.enabled !== false).length },
]

// 点击行为（VS Code 风格）：点击当前活动按钮收起侧栏，点击其它按钮切换面板并展开
function onClick(id) {
  if (store.activityView === id) {
    store.toggleLeft()
  } else {
    store.setActivityView(id)
    if (!store.leftOpen) store.toggleLeft()
  }
}
</script>


