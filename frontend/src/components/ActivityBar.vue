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

// 活动栏：场景 / 资源管理器 / 搜索 / 流程编排 / 数据源管理 / AI 群控
// 流程编排 / 数据源管理 / AI 群控为中间内容区的功能视图（非左栏面板），
// 其 on 态与开关注册在按钮的 view 字段（模板据此高亮）
const buttons = [
  { id: 'scene', icon: 'scene3d', title: '场景', badge: null },
  { id: 'explorer', icon: 'open', title: '资源管理器', badge: null },
  { id: 'search', icon: 'search', title: '搜索', badge: null },
  // 流程编排：以「流程编排」标签窗口打开，高亮取 flowEditing（编辑态 + 画布在前台），
  // 切到其它标签时编辑态保留（草稿不丢）但按钮不高亮
  { id: 'flowEdit', icon: 'flow', title: '流程编排', badge: null, view: 'flowEditing' },
  { id: 'boxManage', icon: 'database', title: '数据源管理', badge: null, view: 'boxManageOn' },
  { id: 'aiGroup', icon: 'ai', title: 'AI群控', badge: null, view: 'aiGroupOn' },
]

// 点击行为（VS Code 风格）：点击当前活动按钮收起侧栏，点击其它按钮切换面板并展开
function onClick(id) {
  // 流程编排：进入 / 回到编排画布；已停在画布时再次点击即「完成编排」（应用方案并退出编辑态）
  if (id === 'flowEdit') {
    if (store.flowEditing) store.exitEdit()
    else if (store.editMode) store.activateView('flowEdit')
    else store.enterEdit()
    return
  }
  // 数据源管理：能碳一体机 + 外部数据源的统一接入管理（中间内容区独立视图，再点一次关闭）
  if (id === 'boxManage') { store.toggleView(id); return }
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


