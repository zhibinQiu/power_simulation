<template>
  <!-- 视图标签条：占据顶栏下方工具栏行（与 Ribbon 同格同高），
       首项「三维仿真」为固定标签（不可关闭），其后为已打开的功能视图标签；
       点击标签即切换窗口内容——无需先关闭当前视图，标签上的 ✕ 关闭单个窗口。 -->
  <div class="vw-tabs">
    <!-- 首项固定标签 = 主视图槽位：3D 数字孪生 ⇄ HMI人机交互屏（二者对等，切换不新增 tab） -->
    <button class="vw-tab vw-scene" :class="{ on: !store.activeViewId }" @click="store.activateView(null)"
            :title="mainTitle">
      <span class="vw-t">{{ mainTitle }}</span>
    </button>
    <button v-for="id in store.openViews" :key="id" class="vw-tab" :class="{ on: store.activeViewId === id }"
            @click="store.activateView(id)" :title="t(VIEW_TITLE[id] || id)">
      <span class="vw-t">{{ t(VIEW_TITLE[id] || id) }}</span>
      <!-- 流程编排标签：方案有未保存改动时显示红点（与工具条「保存」按钮一致） -->
      <i v-if="id === 'flowEdit' && store.schemeDirty" class="vw-dot" :title="t('有未保存的修改')"></i>
      <span class="vw-x" :title="id === 'flowEdit' ? t('完成编排并关闭') : t('关闭该窗口')" @click.stop="close(id)">✕</span>
    </button>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore, VIEW_TITLE } from '../stores/sim'
import { t } from '../i18n'

const store = useSimStore()

// 主视图标签名称随当前主视图形态变化（三维仿真 / HMI人机交互屏）
const mainTitle = computed(() => (store.overviewOn ? t('HMI人机交互屏') : t('三维仿真')))

// 关闭单个窗口：关闭后由 store 自动切到相邻标签（全部关闭则回到三维仿真）
function close(id) { store.closeViewById(id) }
</script>

<style scoped>
/* 标签条：占用工具栏行（grid-area: toolbar），与 Ribbon 同高（28px），风格统一 */
.vw-tabs {
  grid-area: toolbar;
  display: flex; align-items: stretch; height: 28px;
  background: var(--panel); border-bottom: 1px solid var(--border);
  border-left: 1px solid var(--border); border-right: 1px solid var(--border);
  overflow-x: auto; overflow-y: hidden; user-select: none;
}
.vw-tabs::-webkit-scrollbar { height: 0; }
.vw-tab {
  position: relative; display: inline-flex; align-items: center; gap: 6px;
  flex: 0 0 auto; max-width: 220px; height: 100%; padding: 0 8px 0 12px;
  font-family: var(--ui); font-size: 12px; color: var(--muted);
  background: transparent; border: none; border-right: 1px solid var(--border);
  cursor: pointer; white-space: nowrap; transition: background .12s, color .12s;
}
.vw-tab:hover { color: var(--text); background: var(--panel-3); }
.vw-tab.on { color: var(--text); background: var(--panel-2); }
.vw-t { overflow: hidden; text-overflow: ellipsis; }
.vw-x {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; border-radius: 4px; font-size: 10px; line-height: 1;
  color: var(--muted); opacity: .7;
}
.vw-x:hover { color: #fff; background: var(--red, #e5484d); opacity: 1; }
/* 固定标签（三维仿真）不带关闭按钮，右侧留白与其它标签对齐 */
.vw-scene { padding-right: 14px; font-weight: 600; }
/* 未保存标记（流程编排）：与工具条保存按钮的红点同款 */
.vw-dot {
  flex: 0 0 auto; width: 7px; height: 7px; border-radius: 50%;
  background: var(--red, #e5484d);
}
</style>
