<template>
  <aside class="activitybar" role="navigation" :aria-label="t('活动栏')">
    <button
      v-for="b in buttons"
      :key="b.id"
      class="act-btn"
      :class="{ on: b.view ? store[b.view] : store.activityView === b.id }"
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

// 活动栏：场景 / 资源管理器 / 搜索 / AI 群控
// AI 群控为独立视图（非左栏面板），其 on 态与开关注册在按钮的 view 字段（模板据此高亮）
const buttons = [
  { id: 'scene', icon: 'scene3d', title: '场景', badge: null },
  { id: 'explorer', icon: 'open', title: '资源管理器', badge: null },
  { id: 'search', icon: 'search', title: '搜索', badge: null },
  { id: 'aiGroup', icon: 'ai', title: 'AI群控', badge: null, view: 'aiGroupOn' },
]

// 点击行为（VS Code 风格）：点击当前活动按钮收起侧栏，点击其它按钮切换面板并展开
function onClick(id) {
  // AI 群控：打开独立群控视图（自动展开左侧「场景」树供拖入受控设备）；已打开时再次点击关闭返回孪生
  if (id === 'aiGroup') {
    if (store.aiGroupOn) { store.toggleAiGroup(); return }
    store.openAiGroup()
    store.pushCmd(t('AI群控：从左侧「场景」资源树拖入受控设备 —— 左栏「训练前测试」（滤波→稳态）验证滤波与闭环稳定，右栏「训练相关设定」训练低能耗稳态最优参数。'), 'out')
    return
  }
  if (store.activityView === id) {
    store.toggleLeft()
  } else {
    store.setActivityView(id)
    if (!store.leftOpen) store.toggleLeft()
  }
}
</script>


