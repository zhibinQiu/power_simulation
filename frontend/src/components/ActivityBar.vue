<template>
  <aside class="activitybar" role="navigation" :aria-label="t('活动栏')">
    <button
      v-for="b in buttons"
      :key="b.id"
      class="act-btn"
      :class="{ on: b.view ? store[b.view] : false }"
      :title="t(b.title)"
      :aria-label="t(b.title)"
      @click="onClick(b.id)"
    >
      <Icon :name="b.icon" :size="20" :stroke="1.5" />
      <span v-if="b.badge && b.badge() > 0" class="act-badge">{{ b.badge() }}</span>
    </button>
  </aside>
</template>

<script setup>
import { useSimStore } from '../stores/sim'
import Icon from './Icon.vue'
import { t } from '../i18n'

const store = useSimStore()

// 活动栏：资源管理器 / 流程编排 / 数据源管理 / AI 群控
// 左栏三块内容（资源管理器 / 资源 / 搜索）的显隐已移到左栏面板头右侧「⋯」菜单，
// 这里不再重复放置「资源 / 搜索」两个按钮；「资源管理器」按钮只负责展开/收起左栏。
// 流程编排 / 数据源管理 / AI 群控为中间内容区的功能视图（非左栏面板），
// 其 on 态与开关注册在按钮的 view 字段（模板据此高亮）
const buttons = [
  { id: 'scene', icon: 'scene3d', title: '资源管理器', badge: null, view: 'leftOpen' },
  // 流程编排：以「流程编排」标签窗口打开，高亮取 flowEditing（编辑态 + 画布在前台），
  // 切到其它标签时编辑态保留（草稿不丢）但按钮不高亮
  { id: 'flowEdit', icon: 'flow', title: '流程编排', badge: null, view: 'flowEditing' },
  { id: 'boxManage', icon: 'database', title: '数据源管理', badge: null, view: 'boxManageOn' },
  { id: 'aiGroup', icon: 'ai', title: 'AI群控', badge: null, view: 'aiGroupOn' },
]

// 点击行为（VS Code 风格）：点击当前活动按钮收起侧栏，点击其它按钮切换面板并展开
function onClick(id) {
  // 欢迎页（未打开工程）：功能视图 / 编排 / 资源管理器都依赖具体工程，一律拒绝并提示先打开工程
  if (store.welcomeOn) {
    store.toast = t('请先打开工程：在内容区新建或打开场景')
    return
  }
  // 流程编排：进入 / 回到编排画布；已停在画布时再次点击即「完成编排」（应用方案并退出编辑态）
  if (id === 'flowEdit') {
    if (store.flowEditing) store.exitEdit()
    else if (store.editMode) store.activateView('flowEdit')
    else store.enterEdit()
    return
  }
  // 数据源管理：能碳一体机 + 外部数据源的统一接入管理（中间内容区独立视图，再点一次关闭）
  if (id === 'boxManage') { store.toggleView(id); return }
  // AI 群控：打开独立群控视图（自动展开左侧「资源管理器」树供拖入受控设备）；已打开时再次点击关闭返回孪生
  if (id === 'aiGroup') {
    if (store.aiGroupOn) { store.toggleAiGroup(); return }
    store.openAiGroup()
    store.pushCmd(t('AI群控：从左侧「资源管理器」拖入受控设备。左栏验证滤波与闭环稳定，右栏训练低能耗稳态参数。'), 'out')
    return
  }
  // 资源管理器（左栏）：展开 / 收起左栏；若「资源管理器」面板已被取消勾选则先勾上再展开
  if (id === 'scene') {
    store.setSidePanel('scene', true)
    store.toggleLeft()
  }
}
</script>


