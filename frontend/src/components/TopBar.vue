<template>
  <!-- ============ 顶栏：经典 MATLAB 式菜单条（浅色，不作蓝色底） ============ -->
  <header class="topbar" @keydown.esc="closeMenus">
    <!-- 经典菜单条：文件 / 仿真 / 视图 / 编辑 / 工具 / 帮助（点击展开下拉，文本式，无图标，贴近 MATLAB） -->
    <nav class="menubar">
      <div v-for="m in menus" :key="m.id" class="mbar-item" :class="{ open: openMenu === m.id }"
           @click="toggleMenu(m.id)" @mouseenter="hoverMenu(m.id)">
        {{ m.label }}
        <div v-if="openMenu === m.id" class="menu-drop" @click.stop>
          <template v-for="(it, i) in m.items" :key="i">
            <template v-if="!(it.hide && it.hide())">
            <div v-if="it.sep" class="sep"></div>
            <div v-else-if="it.sub" class="mi mi-sub" @mouseenter="hoverSub(i)" @mouseleave="leaveSub(i)">
              <span class="tick"></span>
              <span class="tx">{{ it.label }}</span>
              <span class="arrow">›</span>
              <div v-if="openSub === i" class="menu-drop sub">
                <template v-for="(c, ci) in it.items()" :key="ci">
                  <template v-if="!(c.hide && c.hide())">
                  <div v-if="c.sep" class="sep"></div>
                  <div v-else-if="c.sub" class="mi mi-sub" @mouseenter="hoverSub2(ci)" @mouseleave="leaveSub2(ci)">
                    <span class="tick"></span>
                    <span class="tx">{{ c.label }}</span>
                    <span class="arrow">›</span>
                    <div v-if="openSub2 === ci" class="menu-drop sub">
                      <template v-for="(g, gi) in c.items()" :key="gi">
                        <div v-if="g.sep" class="sep"></div>
                        <div v-else class="mi" :class="{ checked: g.checked }" @click="onSubSubItem(g)">
                          <span class="tick">{{ g.checked ? '✓' : '' }}</span>
                          <span class="tx">{{ g.label }}</span>
                        </div>
                      </template>
                    </div>
                  </div>
                  <div v-else class="mi" :class="{ checked: c.checked }" @click="onSubItem(c)">
                    <span class="tick">{{ c.checked ? '✓' : '' }}</span>
                    <span class="tx">{{ c.label }}</span>
                  </div>
                  </template>
                </template>
              </div>
            </div>
            <div v-else class="mi" :class="{ disabled: it.disabled && it.disabled() }" @click="onMenuItem(m, it)">
              <span class="tick">{{ it.toggle && it.toggle() ? '✓' : '' }}</span>
              <span class="tx">{{ it.label }}</span>
              <span v-if="it.accel" class="accel">{{ it.accel }}</span>
            </div>
            </template>
          </template>
        </div>
      </div>
    </nav>

    <span class="spacer"></span>

    <!-- 顶栏右侧快捷操作（浅色图标按钮，与工具条统一） -->
    <div class="top-actions">
      <button class="tbtn" @click="$emit('export')" :title="t('导出分析报告')"><Icon name="export"/><span>{{ t('导出') }}</span></button>
      <!-- 本析智擎：右侧属性弹窗 ↔ 智能体对话界面（中间 3D 场景保持） -->
      <button class="tbtn" :class="{ on: store.agentOn }" @click="$emit('toggle-agent')"
             ><Icon name="robot"/><span>{{ t('本析智擎') }}</span></button>
      <!-- 系统时钟：原底栏右侧，已迁到顶栏（本析智擎之后、问号之前），保持 mono 字形便于快速扫读 -->
      <span class="tbtn tb-clock" :title="t('系统时间')">{{ clock }}</span>
      <button class="tbtn" @click="$emit('help')"><Icon name="help"/></button>
      <span class="tdiv"></span>
      <button class="tbtn" :class="{ on: store.leftOpen }" @click="store.toggleLeft()"><Icon name="panelLeft"/></button>
      <button class="tbtn" :class="{ on: store.rightOpen }" @click="store.toggleRight()"><Icon name="panelRight"/></button>
      <span class="tdiv"></span>
      <button class="tbtn" :class="{ on: store.bottomOpen }" @click="store.toggleBottom()"><Icon name="panelBottom"/></button>
    </div>
  </header>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import Icon from './Icon.vue'
import { t } from '../i18n'
import { useClock } from '../utils/clock.js'

defineProps({ menus: { type: Array, required: true } })
defineEmits(['export', 'help', 'toggle-agent'])

const store = useSimStore()
const clock = useClock()
const openMenu = ref(null)
const openSub = ref(null)
const openSub2 = ref(null)

// ── 子菜单悬停延迟：进入 120ms 展开、离开 200ms 收起 ──────────────────────────
// 之前 mouseenter 直接置 openSub，带来两个问题：
//   ① 下拉浮层与父项之间有 sp-1 的空隙，指针穿过空隙会先 mouseleave（立即收起）
//      再 mouseenter（立即展开），观感就是一串「一闪一闪」；
//   ② 快速沿整列菜单划过时，经过的每一项都会立刻弹出子菜单。
// 加入进出缓冲后：120ms 内就离开 → 不展开（防误触 / 防划过）；离开后 200ms 内
// 回到下拉本身 → 保持展开（穿空隙不闪）；真正离开才收。
const SUB_IN_MS = 120
const SUB_OUT_MS = 200
let subIn = null
let subOut = null
let sub2In = null
let sub2Out = null

function clearSubTimers() {
  for (const t of [subIn, subOut, sub2In, sub2Out]) if (t) clearTimeout(t)
  subIn = subOut = sub2In = sub2Out = null
}
/** 悬停二级项（工具 → AI）：延迟展开 */
function hoverSub(i) {
  if (subOut) { clearTimeout(subOut); subOut = null }   // 又回来了：取消收起
  if (subIn) clearTimeout(subIn)
  subIn = setTimeout(() => {
    subIn = null
    openSub.value = i
    openSub2.value = null   // 换了一级项：三级菜单必须收掉，否则会挂在新项下面
  }, SUB_IN_MS)
}
/** 离开二级项：延迟收起（鼠标穿过空隙移到下拉本身时不会闪） */
function leaveSub(i) {
  if (subIn) { clearTimeout(subIn); subIn = null }
  if (subOut) clearTimeout(subOut)
  subOut = setTimeout(() => {
    subOut = null
    if (openSub.value === i) { openSub.value = null; openSub2.value = null }
  }, SUB_OUT_MS)
}
/** 悬停三级项（双碳 → 碳资产管理）：同样延迟展开 */
function hoverSub2(i) {
  if (sub2Out) { clearTimeout(sub2Out); sub2Out = null }
  if (sub2In) clearTimeout(sub2In)
  sub2In = setTimeout(() => { sub2In = null; openSub2.value = i }, SUB_IN_MS)
}
function leaveSub2(i) {
  if (sub2In) { clearTimeout(sub2In); sub2In = null }
  if (sub2Out) clearTimeout(sub2Out)
  sub2Out = setTimeout(() => {
    sub2Out = null
    if (openSub2.value === i) openSub2.value = null
  }, SUB_OUT_MS)
}
/** 已展开菜单时横向移到别的菜单：立即切换并清掉延迟中的子菜单（否则 index 会串位、误展开） */
function hoverMenu(id) {
  if (!openMenu.value || openMenu.value === id) return   // 未点开菜单时悬停不自动展开（保持原交互）
  clearSubTimers()
  openMenu.value = id
  openSub.value = null
  openSub2.value = null
}

function toggleMenu(id) {
  clearSubTimers()
  openMenu.value = openMenu.value === id ? null : id
  openSub.value = null
  openSub2.value = null
}
/** 关全部：清延迟定时器，避免「点完子项 120ms 后又被定时器弹开」 */
function resetMenus() {
  clearSubTimers()
  openMenu.value = null
  openSub.value = null
  openSub2.value = null
}
function closeMenus() { resetMenus() }
function onMenuItem(m, it) {
  if (it.disabled && it.disabled()) return
  if (it.act) it.act()
  resetMenus()
}
function onSubItem(c) {
  // 兼容两种写法：act（与顶层菜单一致，如「工具 → AI」各子项）/ run（子菜单历史写法）
  if (c.act) c.act()
  else if (c.run) c.run()
  resetMenus()
}
function onSubSubItem(g) {
  // 三级子菜单同样兼容 act / run 两种写法
  if (g.act) g.act()
  else if (g.run) g.run()
  resetMenus()
}

// 点击顶栏以外区域关闭菜单
function onDocClick(e) {
  if (!e.target.closest('.topbar')) closeMenus()
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => {
  document.removeEventListener('click', onDocClick)
  clearSubTimers()   // 卸载时清掉未到期的展开/收起定时器
})

defineExpose({ closeMenus })
</script>

<style scoped>
</style>
