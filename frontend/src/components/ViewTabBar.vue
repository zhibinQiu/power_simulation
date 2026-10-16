<template>
  <!-- 视图标签条：占据顶栏下方工具栏行（与 Ribbon 同格同高），
       首项「三维仿真」为固定标签（不可关闭），其后为已打开的功能视图标签；
       点击标签即切换窗口内容——无需先关闭当前视图，标签上的 ✕ 关闭单个窗口。 -->
  <div class="vw-tabs">
    <!-- 首项固定标签 = 主视图槽位：3D 数字孪生 ⇄ HMI人机交互屏（二者对等，切换不新增 tab） -->
    <button class="vw-tab vw-scene" :class="{ on: !store.activeViewId }" @click="store.activateView(null)"
           >
      <span class="vw-t">{{ mainTitle }}</span>
    </button>
    <button v-for="id in store.openViews" :key="id" class="vw-tab" :class="{ on: store.activeViewId === id }"
            @click="store.activateView(id)" :title="tabTip(id)">
      <span class="vw-t">{{ t(VIEW_TITLE[id] || id) }}</span>
      <!-- 未保存改动标记（VS Code 风格）：标题右侧一个 *，点击标签即可切回去在工具条保存 / Ctrl+S -->
      <i v-if="isDirty(id)" class="vw-star">*</i>
      <span class="vw-x" @click.stop="close(id)">✕</span>
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

// 有未保存改动的窗口（当前仅「流程编排」的手动保存方案会标脏）
function isDirty(id) { return id === 'flowEdit' && store.schemeDirty }
function tabTip(id) {
  const name = t(VIEW_TITLE[id] || id)
  return isDirty(id) ? name + ' · ' + t('有未保存的改动（Ctrl+S 保存）') : name
}
</script>

<style scoped>
/* 标签条：占用工具栏行（grid-area: toolbar），与 Ribbon 同高（--bar-h，行高令牌）；
   度量/字号与左栏分类 tab、底部面板页签一致，但激活态不同 —— 本条与下方工具条同底融为一体，
   不加主题色指示线（见 .vw-tab.on 与 main.css 页签激活指示的例外说明） */
.vw-tabs {
  grid-area: toolbar;
  display: flex; align-items: stretch; height: var(--bar-h);
  background: var(--panel-2); 
  border-left: 1px solid var(--border); border-right: 1px solid var(--border);
  overflow-x: auto; overflow-y: hidden; user-select: none;
}
.vw-tabs::-webkit-scrollbar { height: 0; }
.vw-tab {
  position: relative; display: inline-flex; align-items: center; gap: var(--sp-2);
  flex: 0 0 auto; max-width: 220px; height: 100%; padding: 0 var(--sp-4);
  font-family: var(--ui); font-size: var(--fs-t); color: var(--muted);
  background: transparent; border: none; border-right: 1px solid var(--border);
  cursor: pointer; white-space: nowrap; transition: background .12s, color .12s;
}
.vw-tab:hover { color: var(--text); background: var(--hover); }
/* 激活态：不加任何主题色指示条（底边/顶边均无），
   只用与工具条（.ribbon）同色的面板白 --panel 铺底 —— 选中标签与下方工具条连成一片，
   靠「底色 + 文字色 + 字重」三档中性区分，与标签条底 --panel-2 形成明暗层次 */
.vw-tab.on { color: var(--text); background: var(--panel); font-weight: 500; }
/* 已选中的标签悬停时不再叠灰（否则会与下方工具条断开，失去一体感） */
.vw-tab.on:hover { color: var(--text); background: var(--panel); }
.vw-t { overflow: hidden; text-overflow: ellipsis; }
.vw-x {
  display: inline-flex; align-items: center; justify-content: center;
  width: 16px; height: 16px; border-radius: 4px; font-size: var(--fs-s); line-height: 1;
  color: var(--muted); opacity: .7;
}
.vw-x:hover { color: #fff; background: var(--red, #e5484d); opacity: 1; }
/* 未保存标记：紧贴标题右侧，比标题字号略大以便一眼可见（不占额外宽度，✕ 位置不跳动） */
.vw-star { flex: 0 0 auto; margin-left: -2px; font-size: var(--fs-h); font-style: normal; line-height: 1; color: inherit; }
/* 固定标签（三维仿真）不带关闭按钮，左右留白与其它标签对齐 */
.vw-scene { padding: 0 var(--sp-4); }
</style>
