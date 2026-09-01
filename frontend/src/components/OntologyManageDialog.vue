<template>
  <div class="om-mask" @click.self="$emit('close')">
    <div class="om-modal" role="dialog" aria-modal="true" :aria-label="t('本体定义')">
      <div class="om-head">
        <span class="om-title">🧬 {{ t('本体定义') }}</span>
        <span class="om-sub">{{ t('领域语义层：智能体先补全问题，再从概念/关系/规则推理，判断能否直接回答或需要技能') }}</span>
        <button class="x-btn lg" @click="$emit('close')" :aria-label="t('关闭')">×</button>
      </div>

      <div class="om-tabs">
        <button v-for="tab in tabs" :key="tab.id" class="om-tab" :class="{ on: active === tab.id }"
                @click="active = tab.id">{{ tab.label }}</button>
        <span class="om-flex"></span>
        <button class="om-tab om-reset" @click="resetOntology">{{ t('重置为内置本体') }}</button>
      </div>

      <!-- 概念 -->
      <div v-if="active === 'concepts'" class="om-body">
        <aside class="om-list">
          <div class="om-list-head">
            <span>{{ t('概念') }} ({{ concepts.length }})</span>
            <button class="om-add" @click="newConcept">＋</button>
          </div>
          <button v-for="c in concepts" :key="c.id" class="om-item" :class="{ on: curC && curC.id === c.id }"
                  @click="selectConcept(c)">
            <em class="om-cat" :style="{ background: catColor(c.category) }"></em>
            <span class="om-item-name">{{ c.name }}</span>
            <em v-if="c.builtin" class="om-badge">内置</em>
          </button>
        </aside>
        <section v-if="curC" class="om-editor">
          <div class="om-field"><label>{{ t('名称') }}</label><input v-model="curC.name" class="om-input" /></div>
          <div class="om-field"><label>{{ t('类别') }}</label>
            <select v-model="curC.category" class="om-input">
              <option v-for="ct in CATS" :key="ct" :value="ct">{{ ct }}</option>
            </select>
          </div>
          <div class="om-field"><label>{{ t('描述') }}</label><textarea v-model="curC.description" class="om-input om-ta" rows="3"></textarea></div>
          <div class="om-field"><label>{{ t('别名（逗号分隔）') }}</label><input v-model="aliasText" class="om-input" /></div>
          <div class="om-field"><label>{{ t('触发关键词（逗号分隔）') }}</label><input v-model="kwText" class="om-input" /></div>
          <div class="om-actions">
            <button v-if="!curC.builtin" class="om-btn om-danger" @click="delConcept">🗑 {{ t('删除') }}</button>
            <span class="om-flex"></span>
            <button class="om-btn" @click="saveConcept">{{ t('保存') }}</button>
          </div>
        </section>
        <section v-else class="om-editor om-empty">{{ t('选择或新建概念') }}</section>
      </div>

      <!-- 关系 -->
      <div v-else-if="active === 'relations'" class="om-body">
        <aside class="om-list">
          <div class="om-list-head"><span>{{ t('关系') }} ({{ relations.length }})</span><button class="om-add" @click="newRelation">＋</button></div>
          <button v-for="r in relations" :key="r.id" class="om-item" :class="{ on: curR && curR.id === r.id }" @click="selectRelation(r)">
            <span class="om-item-name">{{ r.source_name || r.source }} <b class="om-rel">{{ r.type }}</b> {{ r.target_name || r.target }}</span>
            <em v-if="r.builtin" class="om-badge">内置</em>
          </button>
        </aside>
        <section v-if="curR" class="om-editor">
          <div class="om-field"><label>{{ t('源概念') }}</label>
            <select v-model="curR.source" class="om-input">
              <option v-for="c in concepts" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>
          <div class="om-field"><label>{{ t('关系类型') }}</label>
            <input v-model="curR.type" class="om-input" list="rel-types" />
            <datalist id="rel-types"><option v-for="rt in REL_TYPES" :key="rt" :value="rt" /></datalist>
          </div>
          <div class="om-field"><label>{{ t('目标概念') }}</label>
            <select v-model="curR.target" class="om-input">
              <option v-for="c in concepts" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
          </div>
          <div class="om-field"><label>{{ t('描述') }}</label><textarea v-model="curR.description" class="om-input om-ta" rows="2"></textarea></div>
          <div class="om-actions">
            <button v-if="!curR.builtin" class="om-btn om-danger" @click="delRelation">🗑 {{ t('删除') }}</button>
            <span class="om-flex"></span>
            <button class="om-btn" @click="saveRelation">{{ t('保存') }}</button>
          </div>
        </section>
        <section v-else class="om-editor om-empty">{{ t('选择或新建关系') }}</section>
      </div>

      <!-- 规则 -->
      <div v-else-if="active === 'rules'" class="om-body">
        <aside class="om-list">
          <div class="om-list-head"><span>{{ t('规则') }} ({{ rules.length }})</span><button class="om-add" @click="newRule">＋</button></div>
          <button v-for="r in rules" :key="r.id" class="om-item" :class="{ on: curRule && curRule.id === r.id }" @click="selectRule(r)">
            <span class="om-item-name">{{ r.name }}</span>
            <em v-if="r.can_answer" class="om-badge om-answer">可答</em>
            <em v-if="r.builtin" class="om-badge">内置</em>
          </button>
        </aside>
        <section v-if="curRule" class="om-editor">
          <div class="om-field"><label>{{ t('规则名') }}</label><input v-model="curRule.name" class="om-input" /></div>
          <div class="om-field"><label>{{ t('描述') }}</label><textarea v-model="curRule.description" class="om-input om-ta" rows="3"></textarea></div>
          <div class="om-field"><label>{{ t('触发关键词（逗号分隔）') }}</label><input v-model="ruleKwText" class="om-input" /></div>
          <div class="om-field"><label>{{ t('适用问题模式') }}</label><textarea v-model="curRule.if_question" class="om-input om-ta" rows="2"></textarea></div>
          <div class="om-field"><label>{{ t('结论') }}</label><textarea v-model="curRule.conclusion" class="om-input om-ta" rows="2"></textarea></div>
          <div class="om-field"><label>{{ t('直接回答模板') }}</label><textarea v-model="curRule.answer_template" class="om-input om-ta" rows="4"></textarea></div>
          <div class="om-field"><label class="om-check">
            <input type="checkbox" v-model="curRule.can_answer" /> {{ t('命中时可基于本体直接回答') }}
          </label></div>
          <div class="om-actions">
            <button v-if="!curRule.builtin" class="om-btn om-danger" @click="delRule">🗑 {{ t('删除') }}</button>
            <span class="om-flex"></span>
            <button class="om-btn" @click="saveRule">{{ t('保存') }}</button>
          </div>
        </section>
        <section v-else class="om-editor om-empty">{{ t('选择或新建规则') }}</section>
      </div>

      <!-- 语义图可视化 -->
      <div v-else class="om-body om-graph-body">
        <div class="om-legend">
          <span v-for="ct in CATS" :key="ct" class="om-lg-item">
            <i :style="{ background: catColor(ct) }"></i>{{ ct }}
          </span>
          <span class="om-flex"></span>
          <span class="om-hint">{{ t('拖拽节点调整布局 · 滚轮缩放 · 空白拖动平移') }}</span>
          <button class="om-btn" @click="autoLayout">{{ t('自动布局') }}</button>
        </div>
        <svg ref="svgEl" class="om-svg" :viewBox="viewBox" @mousedown="onPanStart" @mousemove="onPanMove" @mouseup="onPanEnd" @wheel.prevent="onWheel">
          <g :transform="`translate(${pan.x},${pan.y}) scale(${zoom})`">
            <g v-for="e in edges" :key="e.id">
              <line class="om-edge" :x1="nodeX(e.source)" :y1="nodeY(e.source)" :x2="nodeX(e.target)" :y2="nodeY(e.target)"
                    :class="{ sel: selEdge && selEdge.id === e.id }" @click.stop="selEdge = e" />
              <text class="om-edge-label" :x="mid(e.source, e.target, 0.5, 0)" :y="mid(e.source, e.target, 0.5, 1)" @click.stop="selEdge = e">{{ e.type }}</text>
            </g>
            <g v-for="n in nodes" :key="n.id" class="om-node"
               :transform="`translate(${pos(n.id).x},${pos(n.id).y})`"
               @mousedown.stop="onNodeDown($event, n)">
              <circle r="22" :fill="catColor(n.category)" :class="{ sel: selNode && selNode.id === n.id }" />
              <text class="om-node-name" :y="34">{{ n.name }}</text>
            </g>
          </g>
        </svg>
        <div v-if="selNode" class="om-node-info">
          <b>{{ selNode.name }}</b>
          <span v-if="selNode.description" class="om-node-desc">{{ selNode.description }}</span>
          <div v-if="nodeRelations(selNode.id).length" class="om-node-rels">
            <span v-for="r in nodeRelations(selNode.id)" :key="r.id" class="om-rel-chip" @click="selEdge = r">
              {{ r.source_name || r.source }} <b>{{ r.type }}</b> {{ r.target_name || r.target }}
            </span>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import { t } from '../i18n'
import { api } from '../api/client'
const CATS = ['工序', '设备', '物料', '指标', '能源', '排放', '其他']
const REL_TYPES = ['属于', '包含', '消耗', '产出', '排放', '影响', '等价于', '相关']

const tabs = [
  { id: 'concepts', label: '🧬 ' + t('概念') },
  { id: 'relations', label: '🔗 ' + t('关系') },
  { id: 'rules', label: '📐 ' + t('规则') },
  { id: 'graph', label: '🕸 ' + t('语义图') },
]
const active = ref('concepts')
const concepts = ref([])
const relations = ref([])
const rules = ref([])
const curC = ref(null)
const curR = ref(null)
const curRule = ref(null)

const aliasText = computed({ get: () => (curC.value?.aliases || []).join('，'), set: v => { if (curC.value) curC.value.aliases = v.split(/[,，]/).map(s => s.trim()).filter(Boolean) } })
const kwText = computed({ get: () => (curC.value?.keywords || []).join('，'), set: v => { if (curC.value) curC.value.keywords = v.split(/[,，]/).map(s => s.trim()).filter(Boolean) } })
const ruleKwText = computed({ get: () => (curRule.value?.keywords || []).join('，'), set: v => { if (curRule.value) curRule.value.keywords = v.split(/[,，]/).map(s => s.trim()).filter(Boolean) } })

async function loadAll() {
  const r = await api.get('/ontology')
  concepts.value = r.concepts || []
  relations.value = r.relations || []
  rules.value = r.rules || []
  // 同步图数据
  nodes.value = concepts.value.map(c => ({ id: c.id, name: c.name, category: c.category, description: c.description }))
  edges.value = relations.value
  if (!layoutReady.value) autoLayout()
  layoutReady.value = true
}

// ---------------- CRUD ----------------
function selectConcept(c) { curC.value = JSON.parse(JSON.stringify(c)) }
function newConcept() { curC.value = { id: '', name: '', category: '其他', description: '', aliases: [], keywords: [], builtin: false } }
async function saveConcept() {
  if (!curC.value.name.trim()) { alert(t('请填写概念名')); return }
  const body = { name: curC.value.name, category: curC.value.category, description: curC.value.description, aliases: curC.value.aliases || [], keywords: curC.value.keywords || [] }
  if (curC.value.id) await api.put(`/ontology/concepts/${curC.value.id}`, body)
  else await api.post('/ontology/concepts', body)
  loadAll()
}
async function delConcept() {
  if (!confirm(t('删除概念将同时删除其相关关系，确定？'))) return
  await api.del(`/ontology/concepts/${curC.value.id}`)
  curC.value = null
  loadAll()
}
function selectRelation(r) { curR.value = JSON.parse(JSON.stringify(r)) }
function newRelation() {
  curR.value = { id: '', source: concepts.value[0]?.id || '', target: concepts.value[1]?.id || concepts.value[0]?.id || '', type: '相关', description: '', builtin: false }
}
async function saveRelation() {
  if (!curR.value.source || !curR.value.target) { alert(t('请选择源/目标概念')); return }
  const body = { source: curR.value.source, target: curR.value.target, type: curR.value.type || '相关', description: curR.value.description || '' }
  if (curR.value.id) await api.put(`/ontology/relations/${curR.value.id}`, body)
  else await api.post('/ontology/relations', body)
  loadAll()
}
async function delRelation() {
  if (!confirm(t('确定删除该关系？'))) return
  await api.del(`/ontology/relations/${curR.value.id}`)
  curR.value = null
  loadAll()
}
function selectRule(r) { curRule.value = JSON.parse(JSON.stringify(r)) }
function newRule() {
  curRule.value = { id: '', name: '', description: '', keywords: [], if_question: '', conclusion: '', answer_template: '', can_answer: false, builtin: false }
}
async function saveRule() {
  if (!curRule.value.name.trim()) { alert(t('请填写规则名')); return }
  const body = { name: curRule.value.name, description: curRule.value.description || '', keywords: curRule.value.keywords || [], if_question: curRule.value.if_question || '', conclusion: curRule.value.conclusion || '', answer_template: curRule.value.answer_template || '', can_answer: !!curRule.value.can_answer }
  if (curRule.value.id) await api.put(`/ontology/rules/${curRule.value.id}`, body)
  else await api.post('/ontology/rules', body)
  loadAll()
}
async function delRule() {
  if (!confirm(t('确定删除该规则？'))) return
  await api.del(`/ontology/rules/${curRule.value.id}`)
  curRule.value = null
  loadAll()
}
async function resetOntology() {
  if (!confirm(t('将清除全部自定义内容并恢复内置本体，确定？'))) return
  await api.post('/ontology/reset', {})
  curC.value = curR.value = curRule.value = null
  loadAll()
}

// ---------------- 语义图可视化 ----------------
const nodes = ref([])
const edges = ref([])
const posMap = reactive({})
const layoutReady = ref(false)
const selNode = ref(null)
const selEdge = ref(null)
const zoom = ref(1)
const pan = reactive({ x: 40, y: 30 })
const svgEl = ref(null)
const dragging = ref(null)
const panning = ref(false)
const lastPt = reactive({ x: 0, y: 0 })

function catColor(cat) {
  const m = { '工序': '#f59e0b', '设备': '#3b82f6', '物料': '#10b981', '指标': '#ef4444', '能源': '#8b5cf6', '排放': '#64748b', '其他': '#94a3b8' }
  return m[cat] || '#94a3b8'
}
function pos(id) { return posMap[id] || { x: 0, y: 0 } }
function nodeX(id) { return pos(id).x }
function nodeY(id) { return pos(id).y }
function mid(s, t, fx, fy) {
  const a = pos(s), b = pos(t)
  return { x: (a.x + b.x) / 2, y: (a.y + b.y) / 2 }
}
function autoLayout() {
  const cols = CATS.length
  const byCat = {}
  nodes.value.forEach(n => { (byCat[n.category] = byCat[n.category] || []).push(n.id) })
  CATS.forEach((cat, ci) => {
    const ids = byCat[cat] || []
    ids.forEach((id, ri) => {
      posMap[id] = { x: ci * 190 + 100, y: ri * 130 + 90 }
    })
  })
  // 无类别归属的概念兜底
  nodes.value.forEach(n => { if (!posMap[n.id]) posMap[n.id] = { x: 100 + Math.random() * 400, y: 100 + Math.random() * 300 } })
}
function onNodeDown(e, n) {
  dragging.value = n
  lastPt.x = e.clientX; lastPt.y = e.clientY
  selNode.value = n; selEdge.value = null
  e.preventDefault()
}
function onPanStart(e) {
  panning.value = true
  lastPt.x = e.clientX; lastPt.y = e.clientY
}
function onPanMove(e) {
  if (dragging.value) {
    const dx = (e.clientX - lastPt.x) / zoom.value
    const dy = (e.clientY - lastPt.y) / zoom.value
    lastPt.x = e.clientX; lastPt.y = e.clientY
    const p = pos(dragging.value.id); p.x += dx; p.y += dy
    return
  }
  if (panning.value) {
    pan.x += e.clientX - lastPt.x
    pan.y += e.clientY - lastPt.y
    lastPt.x = e.clientX; lastPt.y = e.clientY
  }
}
function onPanEnd() { dragging.value = null; panning.value = false }
function onWheel(e) {
  const factor = e.deltaY < 0 ? 1.1 : 0.9
  zoom.value = Math.min(2.5, Math.max(0.4, zoom.value * factor))
}
function nodeRelations(id) {
  return edges.value.filter(r => r.source === id || r.target === id)
}
const viewBox = computed(() => `0 0 ${CATS.length * 190 + 200} 760`)
onMounted(loadAll)
</script>

<style scoped>
.om-mask { position: fixed; inset: 0; background: rgba(16,24,34,.5); z-index: 300; display: flex; align-items: center; justify-content: center; }
.om-modal { width: 980px; max-width: 96vw; height: 82vh; background: var(--panel); color: var(--text); border-radius: 6px; border: 1px solid var(--border); display: flex; flex-direction: column; box-shadow: 0 18px 50px rgba(0,0,0,.35); overflow: hidden; }
.om-head { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-bottom: 1px solid var(--border); background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 6%, var(--panel)), var(--panel)); }
.om-title { font-weight: 700; font-size: 15px; letter-spacing: 1px; }
.om-sub { flex: 1; color: var(--faint); font-size: 12px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.om-tabs { display: flex; align-items: center; gap: 4px; padding: 8px 14px 0; border-bottom: 1px solid var(--border); }
.om-tab { padding: 8px 14px; border: none; background: none; color: var(--faint); cursor: pointer; font-size: 13px; border-bottom: 2px solid transparent; }
.om-tab.on { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }
.om-tab.om-reset { margin-left: auto; color: #e5484d; }
.om-flex { flex: 1; }
.om-body { flex: 1; display: flex; min-height: 0; }
.om-list { width: 320px; border-right: 1px solid var(--border); overflow: auto; padding: 10px; display: flex; flex-direction: column; gap: 4px; }
.om-list-head { display: flex; align-items: center; justify-content: space-between; font-size: 12.5px; color: var(--faint); padding: 4px 6px; }
.om-add { width: 24px; height: 24px; border-radius: 4px; border: 1px solid var(--border); background: var(--panel-2); color: var(--accent); cursor: pointer; }
.om-add:hover { border-color: var(--accent); }
.om-item { display: flex; align-items: center; gap: 8px; padding: 7px 9px; border: 1px solid transparent; border-radius: 6px; background: none; color: var(--text); cursor: pointer; font-size: 12.5px; text-align: left; }
.om-item:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.om-item.on { background: color-mix(in srgb, var(--accent) 14%, transparent); border-color: color-mix(in srgb, var(--accent) 45%, transparent); }
.om-cat { width: 8px; height: 8px; border-radius: 50%; flex: none; }
.om-item-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.om-rel { color: var(--accent); font-weight: 600; }
.om-badge { font-style: normal; font-size: 9.5px; color: var(--faint); border: 1px solid var(--border); border-radius: 4px; padding: 0 4px; }
.om-badge.om-answer { color: #10b981; border-color: #10b981; }
.om-editor { flex: 1; overflow: auto; padding: 16px 20px; }
.om-empty { display: flex; align-items: center; justify-content: center; color: var(--faint); font-size: 13px; }
.om-field { margin-bottom: 12px; }
.om-field label { display: block; font-size: 12.5px; font-weight: 600; margin-bottom: 5px; color: var(--text); }
.om-input { width: 100%; padding: 7px 10px; border: 1px solid var(--border); border-radius: 4px; background: var(--panel-2); color: var(--text); font-size: 13px; }
.om-input:focus { outline: none; border-color: var(--accent); }
/* 下拉选择框：全局 select 固定 height:22px 且 box-sizing:border-box，与 om-input 的 7px 垂直 padding 叠加后内容区仅剩约 6px，13px 文本被压扁裁切；改为高度自适应并保留右侧箭头空间 */
select.om-input {
  height: auto;
  line-height: 1.4;
  padding: 7px 26px 7px 10px;
  background-position: calc(100% - 14px) center, calc(100% - 10px) center;
}
.om-ta { resize: vertical; font-family: inherit; line-height: 1.5; }
.om-check { display: flex; align-items: center; gap: 8px; font-weight: 400 !important; cursor: pointer; }
.om-actions { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.om-btn { padding: 7px 16px; border-radius: 4px; border: 1px solid var(--border); background: var(--panel-2); color: var(--text); cursor: pointer; font-size: 12.5px; transition: all .15s; }
.om-btn:hover { border-color: var(--accent); color: var(--accent); }
.om-danger:hover { border-color: #e5484d; color: #e5484d; }
.om-graph-body { flex-direction: column; position: relative; }
.om-legend { display: flex; align-items: center; gap: 12px; padding: 8px 14px; border-bottom: 1px solid var(--border); flex-wrap: wrap; }
.om-lg-item { display: inline-flex; align-items: center; gap: 5px; font-size: 11.5px; color: var(--faint); }
.om-lg-item i { width: 10px; height: 10px; border-radius: 50%; display: inline-block; }
.om-hint { font-size: 11px; color: var(--faint); }
.om-svg { flex: 1; width: 100%; cursor: grab; background:
  radial-gradient(circle at 1px 1px, color-mix(in srgb, var(--faint) 14%, transparent) 1px, transparent 0) 0 0 / 22px 22px; }
.om-svg:active { cursor: grabbing; }
.om-edge { stroke: color-mix(in srgb, var(--faint) 45%, transparent); stroke-width: 1.2; }
.om-edge.sel { stroke: var(--accent); stroke-width: 2; }
.om-edge-label { font-size: 9.5px; fill: var(--faint); text-anchor: middle; pointer-events: none; }
.om-node { cursor: grab; }
.om-node circle { stroke: var(--panel); stroke-width: 2; opacity: .92; }
.om-node circle.sel { stroke: var(--accent); stroke-width: 3; }
.om-node-name { font-size: 11px; fill: var(--text); text-anchor: middle; pointer-events: none; }
.om-node-info { position: absolute; left: 16px; bottom: 14px; max-width: 480px; background: var(--panel); border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; font-size: 12.5px; box-shadow: 0 8px 24px rgba(0,0,0,.2); }
.om-node-desc { display: block; color: var(--faint); margin-top: 4px; }
.om-node-rels { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.om-rel-chip { font-size: 11px; padding: 3px 8px; border-radius: 4px; background: var(--panel-2); border: 1px solid var(--border); cursor: pointer; }
.om-rel-chip:hover { border-color: var(--accent); }
.om-rel-chip b { color: var(--accent); }
</style>
