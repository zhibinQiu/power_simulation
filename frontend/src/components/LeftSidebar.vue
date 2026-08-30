<template>
  <aside class="sidebar">
    <!-- 宽度拖拽手柄（右侧边缘） -->
    <div class="sidebar-rsz" @mousedown.prevent="emit('rsz', $event)" :title="t('拖拽调整宽度')"></div>
    <div class="sidebar-head">
      <Icon :name="headIcon" :size="15" class="head-ic" />
      <span class="ttl">{{ headTitle }}</span>
    </div>

    <!-- ======== 资源管理器面板 ======== -->
    <template v-if="store.activityView === 'explorer'">
    <!-- 三标签：工艺 / 物料 / 策略 -->
    <div class="tabbar">
      <div class="tab" :class="{ active: tab === 'process' }" @click="onTab('process')">
        <span>{{ t('工艺') }}</span>
      </div>
      <div class="tab" :class="{ active: tab === 'material' }" @click="onTab('material')">
        <span>{{ t('物料') }}</span>
      </div>
      <div class="tab" :class="{ active: tab === 'strategy' }" @click="onTab('strategy')">
        <span>{{ t('策略') }}</span>
      </div>
    </div>

    <div class="sidebar-body tree" :class="{ scrolling }" @scroll="onScroll">
      <!-- 工艺：直接展示各工艺分组（炼钢 / 工辅），点击查看属性 -->
      <div v-if="tab === 'process'">
        <div v-for="(group, key) in routeGroups" :key="key" class="tnode">
          <div class="tch sub hdr" @click="groupHasDevs(key) ? toggle('g_' + key) : (expanded['g_' + key] = true)">
            <span v-if="groupHasDevs(key)" class="twisty" :class="{ open: expanded['g_' + key] }">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </span>
            <span class="tch-tt">{{ routeLabel[key] || key }}</span>
            <span class="tch-count">{{ group.length }}</span>
          </div>
          <div class="tchildren" v-show="groupOpen(key)">
            <div v-for="nd in group" :key="nd.type" class="tnode">
              <div class="tchild leaf click" :class="{ active: processActive(nd), drag: store.editMode && !store.simMode }"
                   :id="nd.route === 'aux' ? 'tree-leaf-' + nd.type : undefined"
                   :draggable="store.editMode && !store.simMode"
                   @dragstart="onDrag($event, 'process', nd.type)"
                   @click="onProcessClick(nd)"
                   @contextmenu.prevent="onLeafContext($event, { kind: 'process', type: nd.type })">
                <span v-if="devSubItems(nd).length" class="twisty" :class="{ open: isOpen('dev_' + nd.type) }" @click.stop="toggleDev('dev_' + nd.type)">
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                </span>
                <span class="tch-dot" v-if="inScene('process', nd.type)" :title="t('已部署至场景')"></span>
                <span class="tc-tt">{{ nd.label }}</span>
              </div>
              <div class="tchildren" v-if="devSubItems(nd).length"
                   v-show="isOpen('dev_' + nd.type)">
                <div v-for="d in devSubItems(nd)" :key="d.id"
                     class="tchild leaf dev-leaf click" :class="{ active: store.deviceDetailId === d.id }"
                     @click="store.openDeviceDetail(d.id)">
                  <span class="tc-tt">{{ d.label }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 物料：直接展示 原料 / 中间产物 / 产品 三棵子树，均可下拉 -->
      <div v-else-if="tab === 'material'">
        <div v-for="g in materialTrees" :key="g.key" class="tnode">
          <div class="tch sub hdr" @click="toggle('g_mat_' + g.key)">
            <span class="twisty" :class="{ open: expanded['g_mat_' + g.key] }">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
            </span>
            <span class="tch-tt">{{ g.label }}</span>
            <span class="tch-count">{{ g.items.length }}</span>
          </div>
          <div class="tchildren" v-show="expanded['g_mat_' + g.key]">
            <div v-for="m in g.items" :key="m.id" class="tchild leaf flat click"
                 :class="{ active: store.selectedMaterialId === m.id, drag: store.editMode && !store.simMode }"
                 :draggable="store.editMode && !store.simMode"
                 @dragstart="onDrag($event, 'material', m.id)"
                 @click="store.selectMaterial(m.id)"
                 @contextmenu.prevent="onLeafContext($event, { kind: 'material', id: m.id })">
              <span class="tc-tt">{{ m.name }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 策略：直接展示 AI优化模型（系统缺省）/ 自定义（仿真模式下保存的策略）/ 工艺流程优化（各工艺策略 + 系统预置） -->
      <div v-else>

          <!-- AI优化模型：系统缺省（默认）AI 优化模型 -->
          <div class="tnode">
            <div class="tch sub hdr" @click="toggle('g_strat_ai')">
              <span class="twisty" :class="{ open: expanded.g_strat_ai }">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </span>
              <span class="tch-tt">{{ t('AI优化模型') }}</span>
              <span class="tch-count">{{ AI_MODELS.length }}</span>
            </div>
            <div class="tchildren" v-show="expanded.g_strat_ai">
              <div v-for="m in AI_MODELS" :key="m.id" class="tchild leaf flat click"
                   :class="{ active: store.selectedStrategyId === m.id }"
                   :title="t('点击查看 AI 优化模型「{name}」训练面板', { name: m.name })"
                   @click="onAiClick(m)">
                <span class="tc-tt">{{ m.name }}</span>
              </div>
            </div>
          </div>

          <!-- 自定义：仿真模式下保存的策略 -->
          <div class="tnode">
            <div class="tch sub hdr" @click="toggle('g_strat_custom')">
              <span class="twisty" :class="{ open: expanded.g_strat_custom }">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </span>
              <span class="tch-tt">{{ t('自定义（仿真保存）') }}</span>
              <span class="tch-count">{{ customStrategies.length }}</span>
            </div>
            <div class="tchildren" v-show="expanded.g_strat_custom">
              <div v-for="s in customStrategies" :key="s._key" class="tchild leaf flat click"
                   :class="{ active: store.selectedStrategyId === s.id }"
                   :title="t('点击查看策略属性（名称/数值调整可编辑，底部可「策略仿真」）')"
                   @click="onCustomClick(s)"
                   @contextmenu.prevent="onStratContext($event, s)">
                <span class="tch-dot" v-if="s.applied" :title="t('已应用')"></span>
                <span class="tc-tt">{{ s.name || t('未命名策略') }}</span>
                <span class="tc-tag saved">{{ t('自定义') }}</span>
                <button class="x-btn danger" :title="t('删除策略')" @click.stop="doRemoveStrategy(s)">✕</button>
              </div>
              <div v-if="!customStrategies.length" class="empty-hint">
                {{ t('暂无自定义策略：进入仿真模式调整参数后，点击 3D 场景右上角「保存策略」即可创建') }}
              </div>
            </div>
          </div>

          <!-- 工艺流程优化：按工艺分组展示各工艺策略（含系统预置策略，归入对应工艺）；
               工艺分组默认展开（2级策略条目直接可见），twisty 可折叠 -->
          <div class="tnode">
            <div class="tch sub hdr" @click="toggle('g_strat_builtin')">
              <span class="twisty" :class="{ open: expanded.g_strat_builtin }">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
              </span>
              <span class="tch-tt">{{ t('工艺流程优化') }}</span>
              <span class="tch-count">{{ presetStrategies.length + greenCount }}</span>
            </div>
            <div class="tchildren" v-show="expanded.g_strat_builtin">

              <!-- 工艺分组：组内 = 该工艺绿色策略 + 归入该工艺的系统预置策略（统一展示，不再区分内置/非内置） -->
              <div v-for="g in greenGroups" :key="g.type" class="tnode">
                <div class="tch sub2" @click="toggleStratGroup(g.type)">
                  <span class="twisty" :class="{ open: stratGroupOpen(g.type) }">
                    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><polyline points="9 18 15 12 9 6"/></svg>
                  </span>
                  <span class="tch-dot" v-if="inScene('process', g.type)" :title="t('该工艺已部署至场景')"></span>
                  <span class="tch-tt">{{ g.label }}</span>
                  <span class="tch-count">{{ g.items.length }}</span>
                </div>
                <div class="tchildren" v-show="stratGroupOpen(g.type)">
                  <div v-for="gs in g.items" :key="gs.id" class="tchild leaf flat click"
                       :class="{ active: gs.preset ? store.selectedStrategyId === gs.id : isGreenSelected(g, gs) }"
                       :title="gs.preset ? t('点击查看策略属性（底部「策略仿真」进入仿真模式测试）') : t('点击查看策略属性，可在右侧启用/停用')"
                       @click="gs.preset ? onPresetClick(gs) : onGreenClick(g, gs)">
                    <span class="tch-dot" v-if="gs.preset ? gs.applied : isGreenActive(g.type, gs.id)"
                          :title="gs.preset ? t('已应用') : t('已启用')"></span>
                    <span class="tc-tt">{{ gs.name }}</span>
                    <span class="tc-tag pre" v-if="!gs.preset && isGreenActive(g.type, gs.id)">{{ t('已启用') }}</span>
                  </div>
                </div>
              </div>
              <div v-if="!greenGroups.length" class="empty-hint">{{ t('暂无工艺策略') }}</div>

            </div>
          </div>
      </div>
    </div>
    </template>

    <!-- ======== 搜索面板：跨工艺/设备/物料/策略全局搜索 ======== -->
    <SearchPanel v-else-if="store.activityView === 'search'" />
    <!-- ======== 场景面板：当前编排对应场景的资源树 ======== -->
    <ScenePanel v-else-if="store.activityView === 'scene'" />
    <!-- ======== 连接面板：多数据源管理 + 传感器字段对齐 ======== -->
    <ConnectionsPanel v-else-if="store.activityView === 'connections'" />
  </aside>
</template>

<script setup>
import { reactive, ref, computed, watch, nextTick } from 'vue'
import { useSimStore, AI_MODELS } from '../stores/sim'
import { MATERIALS, PRODUCTS, ROUTE_GROUPS, PROCESS_TEMPLATES, PROCESS_ADJUSTABLE, DEVICE_MAP, PROCESS_MAP } from '../data/flowLibrary'
import Icon from './Icon.vue'
import { openContextMenu } from '../composables/contextMenu'
import SearchPanel from './SearchPanel.vue'
import ScenePanel from './ScenePanel.vue'
import ConnectionsPanel from './ConnectionsPanel.vue'
import { t } from '../i18n'

const store = useSimStore()
const emit = defineEmits(['rsz'])
// 活动栏面板头部：标题/图标随当前活动面板切换（VS Code 式）
const headMeta = {
  explorer: { title: t('资源管理器'), icon: 'open' },
  search: { title: t('搜索'), icon: 'search' },
  scene: { title: t('场景'), icon: 'scene3d' },
  connections: { title: t('连接'), icon: 'link' },
}
const headTitle = computed(() => (headMeta[store.activityView] || headMeta.explorer).title)
const headIcon = computed(() => (headMeta[store.activityView] || headMeta.explorer).icon)
// 滚动条显隐：滚动时显示，停止滚动 2s 后自动隐藏
const scrolling = ref(false)
let scrollTimer = null
function onScroll() {
  scrolling.value = true
  clearTimeout(scrollTimer)
  scrollTimer = setTimeout(() => { scrolling.value = false }, 2000)
}
// 工艺树分组：炼钢 + 工辅（鼓风机/热风炉等辅助生产工序）；
// 节能减碳措施（煤气发电/余热回收/碳捕集）统一在「策略」中展示，不进入工艺树
const routeGroups = ROUTE_GROUPS
const routeLabel = { steel: t('炼钢'), aux: t('工辅') }
// 策略分类：工艺流程优化 = 各工艺策略（含系统预置归入对应工艺）；自定义 = 仿真模式下保存的策略
// 系统预置策略 → 归入的工艺类型（与 backend presets 顺序一一对应；余热+碳捕集归节能减碳）
const PRESET_PROCESS = [
  'blast_furnace', // 氢冶金替代高炉
  'blast_furnace', // 绿氢竖炉替代
  'eaf',           // 电炉短流程
  'blast_furnace', // 焦比优化
  'waste_heat',    // 余热+碳捕集（节能减碳）
  'blast_furnace', // 熔融还原路线
]
const presetStrategies = computed(() => (store.presets || []).map((p, i) => ({
  ...p, id: p.id ?? `preset::${i}`, _key: `preset::${i}`, _src: 'preset',
  processType: PRESET_PROCESS[i] || null,
})))
const customStrategies = computed(() => (store.strategies || []).map((s) => ({ ...s, _key: `saved::${s.id}`, _src: 'saved' })))
// 工艺策略：按工艺分组 = 该工艺绿色策略 + 归入该工艺的系统预置策略（preset: true）
const greenGroups = computed(() => {
  const groups = []
  for (const t of PROCESS_TEMPLATES) {
    const items = [...(t.greenStrategies || [])]
    presetStrategies.value.forEach((p) => {
      if (p.processType === t.type) items.push({ ...p, preset: true })
    })
    if (!items.length) continue
    groups.push({ type: t.type, label: t.label, items })
  }
  return groups
})
// 绿色策略数（不含系统预置，避免与 presetStrategies.length 重复计数）
const greenCount = computed(() => greenGroups.value.reduce((s, g) => s + g.items.filter((i) => !i.preset).length, 0))
// 某工艺的绿色策略是否已启用（右侧策略属性/工艺属性面板中勾选）
function isGreenActive(processType, sid) {
  return (store.greenStrategiesFor(processType) || []).includes(sid)
}
function isGreenSelected(g, gs) {
  return store.selectedStrategyId === `green::${g.type}::${gs.id}`
}
// 物料按 原料 / 中间产物 / 产品 分三棵子树：能源类投入归入「原料」，副产品归入「中间产物」
const prodIds = new Set(PRODUCTS.map((p) => p.id))
const materialTrees = computed(() => {
  const groups = [
    { key: 'raw', label: t('原料'), items: [] },
    { key: 'mid', label: t('中间产物'), items: [] },
    { key: 'prod', label: t('产品'), items: [] },
  ]
  for (const m of MATERIALS) {
    if (prodIds.has(m.id)) groups[2].items.push(m)
    else if (m.cat === '原料' || m.cat === '能源') groups[0].items.push(m)
    else groups[1].items.push(m) // 中间产物 + 副产品
  }
  return groups
})
const tab = ref('process')

// 全厂设备按「工艺类型」归类，拆成「计量设备 / 可调设备」两组，供资源浏览器逐工艺展开。
// 已部署工序取真实设备（计量 + 合成可调）；未部署工序仍列出其「典型可调设备」，
// 使左侧资源管理器与右侧属性面板（典型可调设备）保持一致，避免有的工艺在属性中可见、左侧却没有。
const allDevices = computed(() => store.allDevices)
const devByType = computed(() => {
  const m = {}
  // 1) 已部署工序的设备（计量 + 合成可调），按工艺类型归类；详情用稳定 id
  for (const d of allDevices.value) {
    const k = d.unitType
    if (!k) continue
    if (!m[k]) m[k] = { meters: [], adjs: [], all: [] }
    const e = { ...d, devId: d.id }
    if (d.adjustable) { m[k].adjs.push(e); m[k].all.push(e) }
    else { m[k].meters.push(e); m[k].all.push(e) }
  }
  // 2) 补全每个工艺类型的「典型可调设备」（与右侧属性面板一致）
  for (const group of Object.values(routeGroups)) {
    for (const t of group) {
      const adjs = PROCESS_ADJUSTABLE[t.type] || []
      if (!adjs.length) continue
      if (!m[t.type]) m[t.type] = { meters: [], adjs: [], all: [] }
      const seen = new Set(m[t.type].adjs.map((x) => x.type))
      for (const dt of adjs) {
        if (seen.has(dt)) continue
        const tmpl = DEVICE_MAP[dt] || {}
        m[t.type].adjs.push({
          id: `tpl::${t.type}::${dt}`,
          type: dt,
          label: tmpl.label || dt,
          measures: tmpl.measures || '',
          unit: (tmpl.setpoint && tmpl.setpoint.unit) || tmpl.unit || '',
          adjustable: true,
          metering: false,
        })
        m[t.type].all.push(m[t.type].adjs[m[t.type].adjs.length - 1])
      }
    }
  }
  return m
})
// 设备子项默认折叠；twisty 点击展开/折叠（未设置的 key 视为折叠）
function isOpen(key) { return expanded[key] === true }
function toggleDev(key) { expanded[key] = !expanded[key] }
// 分组标题是否可折叠（显示下拉箭头）：分组下含工艺节点即可折叠，炼钢/工辅均为一级菜单
function groupHasDevs(key) {
  const group = routeGroups[key] || []
  return group.length > 0
}
// 分组展开状态：按 expanded 折叠/展开（炼钢/工辅均为一级菜单，点击标题展开具体工艺）
function groupOpen(key) {
  return !!expanded['g_' + key]
}
// 工艺节点下的设备子项：工辅工艺的设备子项仅是其自身，直接作为叶子展示，不再次下钻。
function devSubItems(t) {
  const list = devByType.value[t.type]
  if (!list || !list.all.length) return []
  if (t.route === 'aux') return []
  return list.all
}
// 工艺节点选中态：普通工艺按右侧选中的工艺类型高亮；
// 工辅工艺（鼓风机/热风炉…）在打开其设备详情时同样高亮，
// 使「从工序属性面板的可调设备打开」与「直接点击工辅节点」都定位到工辅分组下的对应节点
function processActive(t) {
  if (store.selectedAssetType === t.type) return true
  if (t.route !== 'aux') return false
  const dd = store.deviceDetail
  return !!(dd && dd.device && dd.device.type === t.type)
}
// 点击工艺节点：工辅优先打开其设备详情（DeviceDetail 设备详情面板，与从工序「可调设备」
// 打开的形式一致）；普通工艺无独立属性面板，跳转到该类型首个实例的实例属性面板
function onProcessClick(t) { onProcessClickFromType(t.type) }
function onProcessClickFromType(type) {
  const t = PROCESS_MAP[type]
  if (t && t.route === 'aux') {
    const devId = store.linkedAuxDeviceOf(type)
    if (devId) { store.openDeviceDetail(devId); return }
  }
  store.selectAssetType(type)
}
// 打开工辅设备详情（如从工序「可调设备」点击鼓风机）时，
// 左侧资源管理自动跳转到「工辅」分组下的对应节点：切回工艺目录、展开分组并滚动定位
watch(() => store.deviceDetailId, async (id) => {
  if (!id) return
  const dd = store.deviceDetail
  if (!dd || !dd.device || !dd.device.type) return
  const pm = PROCESS_MAP[dd.device.type]
  if (!pm || pm.route !== 'aux') return
  tab.value = 'process'
  expanded.process = true
  expanded.g_aux = true
  await nextTick()
  document.getElementById('tree-leaf-' + dd.device.type)?.scrollIntoView({ block: 'nearest' })
})

// 资源管理器展开状态：工艺默认展开到工艺级别（二级：炼钢/工辅分组及其中工艺节点），
// 工艺节点下的设备子项、物料/策略分组默认折叠（少即是多）
const expanded = reactive({
  process: false, g_steel: true, g_aux: true,
  aux: false, material: false, g_mat_raw: false, g_mat_mid: false, g_mat_prod: false,
  strategy: false, g_strat_builtin: false, g_strat_ai: false, g_strat_custom: false,
})
// 工艺/策略目录不再有右侧专属属性面板（工序顺序已下线），切换时右侧显示总览
const viewMap = { process: 'overview', aux: 'park', material: 'materials', strategy: 'overview' }

// 切换目录：非编排态时右侧同步显示该类目视图；编排态下保持右侧「编排属性」不被抢占
function onTab(key) { tab.value = key; expanded[key] = true; if (!store.editMode) store.setInspectorView(viewMap[key]) }
function toggle(key) { expanded[key] = !expanded[key] }
// 「工艺流程优化」下的工艺分组默认折叠（仅显示一级分组标题）；twisty 点击展开/折叠
function stratGroupOpen(type) { return expanded['g_strat_green_' + type] === true }
function toggleStratGroup(type) {
  const k = 'g_strat_green_' + type
  expanded[k] = !expanded[k]
}

// 点击工艺流程优化策略：打开右侧「策略属性」面板（底部「策略仿真」进入仿真模式解析测试）
function onPresetClick(s) {
  if (store.busy) return
  store.selectStrategy(s.id)
  store.toast = t('已打开工艺流程优化策略「{name}」：点击底部「策略仿真」解析应用', { name: s.name || t('未命名') })
}
// 点击 AI 优化模型：打开右侧「策略属性」训练面板（随实时数据后台定时训练、模型逐渐变优）
function onAiClick(m) {
  if (store.busy) return
  store.selectStrategy(m.id)
  store.toast = t('已打开 AI 优化模型「{name}」训练面板：可开始自动训练/训练一轮/应用最优参数', { name: m.name })
}
// 点击工艺策略（某工艺对应的绿色策略）：打开右侧「策略属性」面板（只读 + 启用/停用开关 + 查看工艺）
function onGreenClick(g, gs) {
  if (store.busy) return
  store.selectGreenStrategy(g.type, gs.id)
  store.toast = t('已打开策略「{name}」属性（所属工艺：{proc}）：可在右侧启用/停用该策略', { name: gs.name, proc: g.label })
}
// 点击自定义策略（仿真模式下保存）：打开右侧「策略属性」面板（名称/数值调整可编辑，底部「策略仿真」按钮加载）
function onCustomClick(s) {
  if (store.busy) return
  store.selectStrategy(s.id)
  store.toast = t('已打开策略「{name}」属性：可编辑名称与数值调整，点击底部「策略仿真」加载进仿真模式', { name: s.name || t('未命名') })
}
// 删除自定义策略（成功/失败反馈由 store.removeStrategy 统一给出）
async function doRemoveStrategy(s) {
  if (!(await store.confirm({ title: t('删除策略'), message: t('确认删除策略「{name}」？', { name: s.name || t('未命名') }), okText: t('删除'), danger: true }))) return
  await store.removeStrategy(s.id)
}
// 该资源是否已在当前场景（3D 孪生）中存在：工艺按产线 units 中是否已含该类型判断
function inScene(kind, type) {
  if (kind !== 'process') return false
  const units = store.model && store.model.units ? store.model.units : []
  return units.some((u) => u.type === type)
}
// 左侧仅作浏览：点击查看属性（右侧显示属性与实时数据）；
// 仅在编排态下条目可拖拽，拖入编排画布生成节点（不改动运行中的产线）。
function onDrag(e, kind, type) {
  if (!store.editMode || store.simMode) return
  e.dataTransfer.setData('application/flow-node', JSON.stringify({ kind, type }))
  e.dataTransfer.setData('text/plain', type)
  e.dataTransfer.effectAllowed = 'copy'
}
// 资源叶子右键上下文菜单：查看属性（工艺 / 原料）
function onLeafContext(e, p) {
  const items = []
  if (p.kind === 'process') {
    items.push({ label: t('查看属性'), icon: 'process', action: () => onProcessClickFromType(p.type) })
  } else if (p.kind === 'material') {
    items.push({ label: t('查看属性'), icon: 'material', action: () => store.selectMaterial(p.id) })
  }
  openContextMenu(e.clientX, e.clientY, items)
}
// 自定义策略右键：查看属性 / 删除
function onStratContext(e, s) {
  const items = [
    { label: t('查看属性'), icon: 'bolt', action: () => onCustomClick(s) },
    { sep: true },
    { label: t('删除策略'), icon: 'trash', danger: true, action: () => doRemoveStrategy(s) },
  ]
  openContextMenu(e.clientX, e.clientY, items)
}
</script>

<style scoped>
/* 面板头图标 */
.head-ic { flex: 0 0 auto; color: var(--accent2); opacity: .9; }

/* Tab 栏图标 */
.tab svg { flex: 0 0 auto; opacity: .7; }
.tab.active svg { opacity: 1; }

/* 分类计数徽章（VS Code badge：灰底圆角小数字） */
.tch-count {
  font-size: 9px; color: var(--muted); background: rgba(128,128,128,.12);
  min-width: 16px; height: 16px; padding: 0 5px; border-radius: 8px;
  font-weight: 500; line-height: 16px; text-align: center;
  flex: 0 0 auto; font-variant-numeric: tabular-nums;
}

/* 场景部署指示点 */
.tch-dot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--accent);
  flex: 0 0 auto; opacity: .85;
}

/* 设备子条目：缩进由全局 tchildren 提供 */
.dev-leaf .tc-tt { font-weight: 400; }

/* 策略分类二级分组（内置 → 工艺）：tchildren 已提供缩进，箭头自身占位；
   字号 12px、颜色 var(--text)、字重 400、字距 .08px，与工艺/物料树叶子条目（.tc-tt）完全一致，
   避免同一工艺词在三个树中字号、颜色与字重不一 */
.tch.sub2 { padding-left: 0; height: 24px; gap: 6px; }
.tch.sub2 .tch-tt { font-size: 12px; font-weight: 400; letter-spacing: .08px; color: var(--text); }
.tch.sub2 .twisty { width: 14px; opacity: .5; }

/* 策略来源标签（工艺流程优化 / 自定义） */
.tc-tag { font-size: 9px; color: #fff; padding: 1px 5px; border-radius: 4px; white-space: nowrap; flex: 0 0 auto; }
.tc-tag.pre { background: var(--accent); }
.tc-tag.saved { background: var(--green); }

/* 自定义策略条目：hover / 选中时显示删除按钮（VS Code 行内操作按钮） */
.tchild .x-btn.danger { display: none; flex: 0 0 auto; }
.tchild:hover .x-btn.danger, .tchild.active .x-btn.danger { display: inline-grid; }

/* 空列表提示 */
.empty-hint { font-size: 10px; color: var(--faint); padding: 10px 14px; line-height: 1.6; }
</style>
