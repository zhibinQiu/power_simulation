<template>
  <!-- ============ 顶栏：经典 MATLAB 式菜单条（浅色，不作蓝色底） ============ -->
  <header class="topbar" @keydown.esc="closeMenus">
    <div class="brand"><span class="lg"></span>行业能碳仿真平台</div>

    <!-- 经典菜单条：文件 / 仿真 / 视图 / 编辑 / 工具 / 帮助（点击展开下拉，文本式，无图标，贴近 MATLAB） -->
    <nav class="menubar">
      <div v-for="m in menus" :key="m.id" class="mbar-item" :class="{ open: openMenu === m.id }"
           @click="toggleMenu(m.id)" @mouseenter="openMenu ? (openMenu = m.id) : null">
        {{ m.label }}
        <div v-if="openMenu === m.id" class="menu-drop" @click.stop>
          <template v-for="(it, i) in m.items" :key="i">
            <template v-if="!(it.hide && it.hide())">
            <div v-if="it.sep" class="sep"></div>
            <div v-else-if="it.sub" class="mi mi-sub" @mouseenter="openSub = i" @mouseleave="openSub = null">
              <span class="tx">{{ it.label }}</span>
              <span class="arrow">›</span>
              <div v-if="openSub === i" class="menu-drop sub">
                <template v-for="(c, ci) in it.items()" :key="ci">
                  <div v-if="c.sep" class="sep"></div>
                  <div v-else class="mi" :class="{ checked: c.checked }" @click="onSubItem(c)">
                    <span class="tick">{{ c.checked ? '✓' : '' }}</span>
                    <span class="tx">{{ c.label }}</span>
                  </div>
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
      <button class="tbtn" @click="$emit('export')" title="导出分析报告"><Icon name="export"/><span>导出</span></button>
      <button class="tbtn" @click="$emit('help')" title="使用指南 (F1)"><Icon name="help"/></button>
      <span class="tdiv"></span>
      <button class="tbtn" :class="{ on: store.leftOpen }" :title="store.leftOpen ? '收起左侧栏' : '展开左侧栏'" @click="store.toggleLeft()"><Icon name="panelLeft"/></button>
      <button class="tbtn" :class="{ on: store.rightOpen }" :title="store.rightOpen ? '收起右侧栏' : '展开右侧栏'" @click="store.toggleRight()"><Icon name="panelRight"/></button>
      <span class="tdiv"></span>
      <button class="tbtn" :class="{ on: store.bottomOpen }" :title="store.bottomOpen ? '收起命令行窗口' : '展开命令行窗口'" @click="store.toggleBottom()"><Icon name="panelBottom"/></button>
    </div>
  </header>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import Icon from './Icon.vue'

defineProps({ menus: { type: Array, required: true } })
defineEmits(['export', 'help'])

const store = useSimStore()
const openMenu = ref(null)
const openSub = ref(null)

function toggleMenu(id) { openMenu.value = openMenu.value === id ? null : id; openSub.value = null }
function closeMenus() { openMenu.value = null; openSub.value = null }
function onMenuItem(m, it) {
  if (it.disabled && it.disabled()) return
  if (it.act) it.act()
  openMenu.value = null; openSub.value = null
}
function onSubItem(c) {
  if (c.run) c.run()
  openMenu.value = null; openSub.value = null
}

// 点击顶栏以外区域关闭菜单
function onDocClick(e) {
  if (!e.target.closest('.topbar')) closeMenus()
}
onMounted(() => document.addEventListener('click', onDocClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

defineExpose({ closeMenus })
</script>
