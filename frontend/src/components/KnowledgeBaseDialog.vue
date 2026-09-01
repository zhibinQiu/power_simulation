<template>
  <div class="kb-mask" @click.self="close">
    <div class="kb-modal" role="dialog" aria-modal="true" :aria-label="t('行业知识库')">
      <!-- 顶部：标题 + 统计 + 搜索 + 关闭 -->
      <div class="kb-head">
        <div class="kb-title">{{ t('行业知识库') }}</div>
        <div class="kb-stats">
          <span class="kb-stat">{{ t('文件夹') }} <b>{{ stats.folders }}</b></span>
          <span class="kb-stat">{{ t('文档') }} <b>{{ stats.docs }}</b></span>
          <span class="kb-stat">{{ t('内容') }} <b>{{ formatChars(stats.chars) }}</b></span>
        </div>
        <div class="kb-search">
          <input v-model="q" class="kb-search-input" :placeholder="t('搜索文档标题与全文…')"
                 @keyup.enter="doSearch" @input="onSearchInput" />
          <button v-if="q" class="kb-search-clear" @click="clearSearch" :title="t('清除搜索')">×</button>
        </div>
        <button class="x-btn lg" @click="close" :aria-label="t('关闭')">×</button>
      </div>

      <div class="kb-body">
        <!-- 左侧：文件夹树（多级） -->
        <aside class="kb-side">
          <div class="kb-side-head">
            <span>{{ t('目录') }}</span>
            <button class="kb-mini" @click="onNewFolder('/')" :title="t('在根目录新建文件夹')">＋</button>
          </div>
          <div class="kb-tree">
            <div class="kb-node" :class="{ active: current === '/' }" @click="selectFolder('/')">
              <span class="kb-twist" @click.stop="toggle('/')">{{ expanded.has('/') ? '▾' : '▸' }}</span>
              <span class="kb-folder-ico">▤</span>
              <span class="kb-node-name">{{ t('全部文档') }}</span>
              <span class="kb-node-ops">
                <button class="kb-mini" @click.stop="onNewFolder('/')" :title="t('新建文件夹')">＋</button>
              </span>
            </div>
            <div v-for="ch in rootChildren" :key="ch.path" class="kb-branch">
              <FolderNode :node="ch" :depth="1" :expanded="expanded" :current="current"
                          @select="selectFolder" @toggle="toggle" @new-folder="onNewFolder"
                          @rename-folder="onRenameFolder" @remove-folder="onRemoveFolder" />
            </div>
            <div v-if="!loading && (!tree || (!tree.children || tree.children.length === 0))" class="kb-empty-side">
              {{ t('暂无文件夹，点击上方 ＋ 新建') }}
            </div>
          </div>
          <div class="kb-side-tip">
            <span class="kb-tip-llm">LLM-WIKI</span>
            <span>{{ t('Markdown 文件夹即知识库，多级目录，无需权限') }}</span>
          </div>
        </aside>

        <!-- 右侧：文档列表 -->
        <main class="kb-main">
          <div v-if="!searching" class="kb-main-head">
            <div class="kb-crumb" :title="current">{{ t('当前目录') }}：{{ current === '/' ? t('全部文档') : current }}</div>
            <div class="kb-actions">
              <button class="kb-btn" @click="onNewFolder(current)">{{ t('新建文件夹') }}</button>
              <button class="kb-btn primary" @click="triggerUpload">{{ t('上传文档') }}</button>
            </div>
          </div>
          <div v-else class="kb-main-head">
            <div class="kb-crumb">{{ t('搜索结果') }}：{{ q }}（{{ results.length }}）</div>
            <button class="kb-btn" @click="clearSearch">{{ t('返回目录') }}</button>
          </div>

          <!-- 拖拽上传区 -->
          <div v-if="!searching" class="kb-drop" :class="{ over: dragOver }" @dragover.prevent="dragOver = true"
               @dragleave.prevent="dragOver = false" @drop.prevent="onDrop">
            <span>{{ t('拖拽 PDF / Word / TXT / MD 到此处上传，或点击「上传文档」') }}</span>
          </div>

          <!-- 新建/重命名内联输入条 -->
          <div v-if="editing" class="kb-editbar">
            <input v-model="editValue" class="kb-edit-input" :placeholder="editPlaceholder" ref="editInput"
                   @keyup.enter="doEdit" @keyup.esc="editing = null" />
            <button class="kb-btn primary" @click="doEdit">{{ t('保存') }}</button>
            <button class="kb-btn" @click="editing = null">{{ t('取消') }}</button>
          </div>

          <!-- 文档列表 -->
          <div v-if="loading" class="kb-loading">{{ t('加载中…') }}</div>
          <div v-else-if="docs.length === 0" class="kb-empty">
            {{ searching ? t('未找到匹配的文档') : t('当前目录为空，上传文档或新建子文件夹开始知识积累') }}
          </div>
          <div v-else class="kb-docs">
            <div v-for="d in docs" :key="d.id" class="kb-doc" :class="{ searching }">
              <span class="kb-ext" :class="'e' + extClass(d.ext)">{{ extLabel(d.ext) }}</span>
              <div class="kb-doc-main" @click="searching ? viewDoc(d) : null">
                <div class="kb-doc-title" :title="d.title">{{ d.title }}</div>
                <div class="kb-doc-meta">
                  <span>{{ formatSize(d.size) }}</span>
                  <span v-if="d.chars">· {{ formatChars(d.chars) }}</span>
                  <span>· {{ formatTime(d.updated_at) }}</span>
                  <span v-if="d.original && d.original !== d.title + d.ext" class="kb-doc-orig" :title="d.original">{{ t('原文件') }}：{{ d.original }}</span>
                </div>
                <div v-if="searching" class="kb-snippet">{{ d._snippet }}</div>
              </div>
              <div class="kb-doc-ops">
                <button class="kb-mini" @click="viewDoc(d)" :title="t('查看内容')">👁</button>
                <button v-if="d.raw" class="kb-mini" @click="downloadDoc(d)" :title="t('下载原文件')">⤓</button>
                <button class="kb-mini" @click="onRenameDoc(d)" :title="t('重命名')">✎</button>
                <button class="kb-mini danger" @click="onRemoveDoc(d)" :title="t('删除')">✕</button>
              </div>
            </div>
          </div>
        </main>
      </div>
    </div>

    <!-- 文档内容查看层 -->
    <div v-if="viewShow" class="kb-view-mask" @click.self="viewShow = false">
      <div class="kb-view">
        <div class="kb-view-head">
          <div class="kb-view-title">
            <span class="kb-ext" :class="'e' + extClass(viewDocData ? viewDocData.ext : '')">{{ extLabel(viewDocData ? viewDocData.ext : '') }}</span>
            <span>{{ viewTitle }}</span>
          </div>
          <div class="kb-view-ops">
            <a v-if="viewDocData && viewDocData.raw" class="kb-btn" :href="api.kbRawUrl(viewDocData.id)" target="_blank" rel="noopener">{{ t('下载原文件') }}</a>
            <button class="kb-btn" @click="viewShow = false">{{ t('关闭') }}</button>
          </div>
        </div>
        <div class="kb-view-body" v-html="viewHtml"></div>
      </div>
    </div>

    <!-- 隐藏文件选择 -->
    <input ref="fileInput" type="file" class="kb-file" accept=".pdf,.doc,.docx,.txt,.md"
           @change="onFileChange" />
  </div>
</template>

<script setup>
import { computed, h, nextTick, onMounted, ref } from 'vue'
import { useSimStore } from '../stores/sim'
import { api } from '../api/client'
import { t } from '../i18n'

const store = useSimStore()
const emit = defineEmits(['close'])

const loading = ref(false)
const tree = ref(null)
const stats = ref({ folders: 0, docs: 0, chars: 0 })
const expanded = ref(new Set(['/']))
const current = ref('/')
const q = ref('')
const searching = ref(false)
const results = ref([])
const dragOver = ref(false)

// 编辑状态：新建文件夹 / 重命名文件夹 / 重命名文档
const editing = ref(null) // { mode, target }
const editValue = ref('')
const editInput = ref(null)
const editPlaceholder = computed(() => {
  if (!editing.value) return ''
  if (editing.value.mode === 'createFolder') return t('输入新文件夹名称')
  if (editing.value.mode === 'renameFolder') return t('输入新文件夹名称')
  return t('输入新文档名称')
})

// 文档查看
const viewShow = ref(false)
const viewTitle = ref('')
const viewDocData = ref(null)
const viewContent = ref('')
const viewHtml = ref('')

// ---------- 树工具 ----------
function findNode(node, path) {
  if (!node) return null
  if ((node.path || '/') === (path || '/')) return node
  for (const c of node.children || []) {
    const hit = findNode(c, path)
    if (hit) return hit
  }
  return null
}
const rootChildren = computed(() => (tree.value && tree.value.children) || [])
const docs = computed(() => {
  if (searching.value) return results.value.map(r => ({ ...r.doc, _snippet: r.snippet || '' }))
  const n = findNode(tree.value, current.value)
  return n ? n.docs : []
})
function toggle(path) {
  const s = new Set(expanded.value)
  s.has(path) ? s.delete(path) : s.add(path)
  expanded.value = s
}
function selectFolder(path) {
  current.value = path || '/'
}

// ---------- 数据加载 ----------
async function refresh() {
  loading.value = true
  try {
    const r = await api.kbTree()
    if (r && r.ok) {
      tree.value = r.tree
      stats.value = r.stats || stats.value
      if (!findNode(tree.value, current.value)) current.value = '/'
    } else {
      store.showToast((r && r.error) || t('知识库加载失败'), 'error')
    }
  } catch (e) {
    store.showToast(t('知识库加载失败：{msg}', { msg: e.message || '' }), 'error')
  } finally {
    loading.value = false
  }
}

// ---------- 文件夹操作 ----------
function onNewFolder(parent) {
  if (editing.value) return
  editing.value = { mode: 'createFolder', target: parent || current.value }
  editValue.value = ''
  nextTick(() => editInput.value && editInput.value.focus())
}
function onRenameFolder(node) {
  if (editing.value) return
  editing.value = { mode: 'renameFolder', target: node }
  editValue.value = node.name
  nextTick(() => editInput.value && editInput.value.focus())
}
async function onRemoveFolder(node) {
  const yes = await store.confirm({
    title: t('删除文件夹'),
    message: t('确定删除文件夹「{name}」吗？其内 {n} 个子文件夹与文档将一并删除，且不可恢复。',
      { name: node.name, n: (node.children || []).length + (node.docs || []).length }),
    okText: t('删除'), danger: true,
  })
  if (!yes) return
  try {
    const r = await api.kbDeleteFolder(node.path)
    if (r && r.ok) {
      store.showToast(t('已删除文件夹「{name}」', { name: node.name }), 'success')
      if (current.value === node.path || current.value.startsWith(node.path + '/')) current.value = '/'
      await refresh()
    } else {
      store.showToast((r && r.error) || t('删除失败'), 'error')
    }
  } catch (e) {
    store.showToast(t('删除失败：{msg}', { msg: e.message || '' }), 'error')
  }
}

// ---------- 文档操作 ----------
const fileInput = ref(null)
function triggerUpload() { fileInput.value && fileInput.value.click() }
function onFileChange(e) {
  const f = e.target.files && e.target.files[0]
  if (f) uploadFile(f)
  e.target.value = ''
}
function onDrop(e) {
  dragOver.value = false
  const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]
  if (f) uploadFile(f)
}
async function uploadFile(file) {
  if (!file) return
  const ext = (file.name.split('.').pop() || '').toLowerCase()
  if (!['pdf', 'doc', 'docx', 'txt', 'md', 'markdown'].includes(ext)) {
    store.showToast(t('不支持的格式，仅支持 PDF / Word / TXT / Markdown'), 'warn')
    return
  }
  const toast = t('正在上传并解析「{name}」…', { name: file.name })
  store.showToast(toast, 'info')
  try {
    const r = await api.kbUpload(file, current.value)
    if (r && r.ok) {
      store.showToast(t('已上传「{name}」并解析为 Markdown', { name: file.name }), 'success')
      await refresh()
    } else {
      store.showToast((r && r.error) || t('上传失败'), 'error')
    }
  } catch (e) {
    store.showToast(t('上传失败：{msg}', { msg: e.message || '' }), 'error')
  }
}
function onRenameDoc(doc) {
  if (editing.value) return
  editing.value = { mode: 'renameDoc', target: doc }
  editValue.value = doc.title
  nextTick(() => editInput.value && editInput.value.focus())
}
async function onRemoveDoc(doc) {
  const yes = await store.confirm({
    title: t('删除文档'),
    message: t('确定删除文档「{name}」吗？其解析内容与原始文件将一并删除。', { name: doc.title }),
    okText: t('删除'), danger: true,
  })
  if (!yes) return
  try {
    const r = await api.kbDeleteDoc(doc.id)
    if (r && r.ok) {
      store.showToast(t('已删除「{name}」', { name: doc.title }), 'success')
      await refresh()
    } else {
      store.showToast((r && r.error) || t('删除失败'), 'error')
    }
  } catch (e) {
    store.showToast(t('删除失败：{msg}', { msg: e.message || '' }), 'error')
  }
}

// ---------- 通用编辑提交 ----------
async function doEdit() {
  if (!editing.value) return
  const name = editValue.value.trim()
  const mode = editing.value.mode
  const target = editing.value.target
  if (!name) { store.showToast(t('名称不能为空'), 'warn'); return }
  try {
    let r
    if (mode === 'createFolder') {
      r = await api.kbCreateFolder(name, target === '/' ? '' : target)
    } else if (mode === 'renameFolder') {
      r = await api.kbRenameFolder(target.path, name)
    } else {
      r = await api.kbRenameDoc(target.id, name)
    }
    if (r && r.ok) {
      store.showToast(t('保存成功'), 'success')
      if (mode === 'renameFolder' && (current.value === target.path || current.value.startsWith(target.path + '/'))) {
        current.value = r.path || current.value
      }
      await refresh()
    } else {
      store.showToast((r && r.error) || t('保存失败'), 'error')
    }
  } catch (e) {
    store.showToast(t('保存失败：{msg}', { msg: e.message || '' }), 'error')
  } finally {
    editing.value = null
  }
}

// ---------- 查看内容 ----------
async function viewDoc(doc) {
  try {
    const r = await api.kbDocContent(doc.id)
    if (r && r.ok) {
      viewDocData.value = r.doc
      viewTitle.value = r.doc.title
      viewContent.value = r.content || ''
      viewHtml.value = md2html(viewContent.value)
      viewShow.value = true
    } else {
      store.showToast((r && r.error) || t('读取文档失败'), 'error')
    }
  } catch (e) {
    store.showToast(t('读取文档失败：{msg}', { msg: e.message || '' }), 'error')
  }
}
function downloadDoc(doc) {
  window.open(api.kbRawUrl(doc.id), '_blank', 'noopener')
}

// ---------- 搜索 ----------
async function doSearch() {
  const kw = q.value.trim()
  if (!kw) { clearSearch(); return }
  searching.value = true
  loading.value = true
  results.value = []
  try {
    const r = await api.kbSearch(kw)
    if (r && r.ok) {
      results.value = r.results || []
      if (results.value.length === 0) store.showToast(t('未找到匹配文档'), 'info')
    } else {
      store.showToast((r && r.error) || t('搜索失败'), 'error')
    }
  } catch (e) {
    store.showToast(t('搜索失败：{msg}', { msg: e.message || '' }), 'error')
  } finally {
    loading.value = false
  }
}
function onSearchInput() {
  if (!q.value.trim()) clearSearch()
}
function clearSearch() {
  q.value = ''
  searching.value = false
  results.value = []
}

// ---------- 格式化 / 图标 ----------
function formatSize(bytes) {
  if (!bytes && bytes !== 0) return ''
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(2) + ' MB'
}
function formatChars(n) {
  if (!n && n !== 0) return ''
  if (n < 1000) return n + ' 字'
  return (n / 1000).toFixed(1) + 'k 字'
}
function formatTime(iso) {
  if (!iso) return ''
  return String(iso).slice(0, 16).replace('T', ' ')
}
function extLabel(ext) {
  return String(ext || '').replace('.', '').toUpperCase() || 'TXT'
}
function extClass(ext) {
  const e = String(ext || '').toLowerCase()
  if (e === '.pdf') return 'pdf'
  if (e === '.doc' || e === '.docx') return 'doc'
  if (e === '.md' || e === '.markdown') return 'md'
  return 'txt'
}

// ---------- 轻量 Markdown -> HTML ----------
function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
}
function md2html(md) {
  if (!md) return '<div class="kb-md-empty">（空文档）</div>'
  const lines = String(md).split(/\r?\n/)
  const out = []
  let inCode = false
  let codeBuf = []
  let inList = false
  const flushList = () => { if (inList) { out.push('</ul>'); inList = false } }
  for (const raw of lines) {
    if (/^```/.test(raw)) {
      if (inCode) {
        out.push('<pre class="kb-md-code">' + esc(codeBuf.join('\n')) + '</pre>')
        codeBuf = []
        inCode = false
      } else {
        flushList()
        inCode = true
      }
      continue
    }
    if (inCode) { codeBuf.push(raw); continue }
    const t1 = raw.trim()
    if (!t1) { flushList(); out.push(''); continue }
    const h = t1.match(/^(#{1,6})\s+(.*)$/)
    if (h) {
      flushList()
      const lv = h[1].length
      out.push(`<h${lv} class="kb-md-h kb-md-h${lv}">${esc(h[2])}</h${lv}>`)
      continue
    }
    if (/^[-*]\s+/.test(t1)) {
      if (!inList) { out.push('<ul class="kb-md-ul">'); inList = true }
      out.push('<li>' + esc(t1.replace(/^[-*]\s+/, '')) + '</li>')
      continue
    }
    if (/^\d+[.、]\s+/.test(t1)) {
      flushList()
      out.push('<div class="kb-md-line">' + esc(t1) + '</div>')
      continue
    }
    flushList()
    // 行内加粗 / 代码
    let line = esc(t1)
    line = line.replace(/\*\*(.+?)\*\*/g, '<b>$1</b>').replace(/`([^`]+)`/g, '<code>$1</code>')
    out.push('<div class="kb-md-p">' + line + '</div>')
  }
  if (inCode) out.push('<pre class="kb-md-code">' + esc(codeBuf.join('\n')) + '</pre>')
  flushList()
  return out.join('\n')
}

// ---------- 文件夹树节点（递归组件） ----------
// 注意：必须用 render 函数而非字符串 template —— 项目 Vue 为 runtime-only 构建
// （vue.runtime.esm-bundler.js，无模板编译器），字符串 template 会编译失败导致节点渲染为空。
const FolderNode = {
  name: 'FolderNode',
  props: { node: Object, depth: Number, expanded: Object, current: String },
  emits: ['select', 'toggle', 'new-folder', 'rename-folder', 'remove-folder'],
  render() {
    const { node, depth, expanded, current } = this
    const hasChildren = !!(node.children && node.children.length)
    const open = !!expanded.has(node.path)
    const emit = (event, arg) => this.$emit(event, arg)
    return h('div', [
      h('div', {
        class: ['kb-node', { active: current === node.path }],
        style: { paddingLeft: depth * 14 + 'px' },
        onClick: () => emit('select', node.path),
      }, [
        h('span', {
          class: 'kb-twist',
          onClick: (e) => { e.stopPropagation(); emit('toggle', node.path) },
        }, hasChildren ? (open ? '▾' : '▸') : '·'),
        h('span', { class: 'kb-folder-ico' }, '▤'),
        h('span', { class: 'kb-node-name' }, node.name),
        h('span', { class: 'kb-node-count' }, node.docs.length || ''),
        h('span', { class: 'kb-node-ops' }, [
          h('button', { class: 'kb-mini', title: '新建子文件夹', onClick: (e) => { e.stopPropagation(); emit('new-folder', node.path) } }, '＋'),
          h('button', { class: 'kb-mini', title: '重命名', onClick: (e) => { e.stopPropagation(); emit('rename-folder', node) } }, '✎'),
          h('button', { class: 'kb-mini danger', title: '删除', onClick: (e) => { e.stopPropagation(); emit('remove-folder', node) } }, '✕'),
        ]),
      ]),
      open && hasChildren
        ? h('div', { class: 'kb-branch' },
            (node.children || []).map((c) => h('div', { key: c.path, class: 'kb-branch' }, [
              h(FolderNode, {
                node: c,
                depth: depth + 1,
                expanded,
                current,
                onSelect: (p) => emit('select', p),
                onToggle: (p) => emit('toggle', p),
                onNewFolder: (p) => emit('new-folder', p),
                onRenameFolder: (n) => emit('rename-folder', n),
                onRemoveFolder: (n) => emit('remove-folder', n),
              }),
            ]))
          )
        : null,
    ])
  },
}
function close() { emit('close') }

onMounted(refresh)
</script>

<style scoped>
.kb-mask { position: fixed; inset: 0; background: rgba(16,24,34,.5); display: flex; align-items: center; justify-content: center; z-index: 300; }
.kb-modal { width: 980px; max-width: 96vw; height: 660px; max-height: 92vh; background: var(--panel);
  border: 1px solid var(--border); border-radius: 6px; box-shadow: 0 20px 60px rgba(0,0,0,.35);
  display: flex; flex-direction: column; overflow: hidden; color: var(--text); font-family: var(--ui); }

/* —— 头部 —— */
.kb-head { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, color-mix(in srgb, var(--accent) 6%, var(--panel)), var(--panel)); }
.kb-title { font-size: 15px; font-weight: 700; letter-spacing: 1px; flex: none; }
.kb-stats { display: flex; gap: 10px; flex: none; font-size: 11px; color: var(--muted); }
.kb-stat b { color: var(--accent-d); font-family: var(--mono); font-weight: 600; }
.kb-search { flex: 1; min-width: 120px; max-width: 260px; position: relative; }
.kb-search-input { width: 100%; padding: 6px 26px 6px 10px; font-size: 12px; color: var(--text);
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px; outline: none; }
.kb-search-input:focus { border-color: var(--accent-d); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 18%, transparent); }
.kb-search-clear { position: absolute; right: 4px; top: 50%; transform: translateY(-50%); background: none;
  border: none; color: var(--faint); font-size: 14px; cursor: pointer; padding: 0 4px; }

/* —— 主体 —— */
.kb-body { flex: 1; display: flex; min-height: 0; }

/* 左侧文件夹树 */
.kb-side { width: 240px; flex: none; border-right: 1px solid var(--border); display: flex; flex-direction: column; min-height: 0; background: var(--panel-2); }
.kb-side-head { display: flex; align-items: center; justify-content: space-between; padding: 8px 10px;
  font-size: 12px; color: var(--muted); border-bottom: 1px solid var(--border); }
.kb-tree { flex: 1; overflow-y: auto; padding: 6px 4px; }
.kb-node { display: flex; align-items: center; gap: 4px; padding: 5px 8px; border-radius: 4px; cursor: pointer;
  font-size: 13px; color: var(--text); }
.kb-node:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); }
.kb-node.active { background: color-mix(in srgb, var(--accent) 18%, transparent); color: var(--accent-d); font-weight: 600; }
.kb-twist { width: 14px; flex: none; font-size: 11px; color: var(--faint); text-align: center; user-select: none; }
.kb-folder-ico { flex: none; color: #d9a441; font-size: 13px; }
.kb-node-name { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-node-count { flex: none; font-size: 10px; color: var(--faint); font-family: var(--mono); }
.kb-node-ops { flex: none; display: none; gap: 2px; }
.kb-node:hover .kb-node-ops { display: flex; }
.kb-empty-side { padding: 18px 12px; font-size: 12px; color: var(--faint); text-align: center; }
.kb-side-tip { padding: 8px 10px; border-top: 1px solid var(--border); font-size: 11px; color: var(--faint); line-height: 1.5; }
.kb-tip-llm { color: var(--accent-d); font-family: var(--mono); font-weight: 600; letter-spacing: .5px; margin-right: 4px; }

/* 右侧文档区 */
.kb-main { flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0; }
.kb-main-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 14px; border-bottom: 1px solid var(--border); }
.kb-crumb { font-size: 12px; color: var(--muted); min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-actions { display: flex; gap: 8px; flex: none; }
.kb-drop { margin: 10px 14px 0; padding: 12px; border: 1px dashed var(--border); border-radius: 4px; font-size: 12px;
  color: var(--faint); text-align: center; cursor: pointer; transition: all .15s; }
.kb-drop:hover, .kb-drop.over { border-color: var(--accent-d); color: var(--accent-d); background: color-mix(in srgb, var(--accent) 6%, transparent); }
.kb-editbar { display: flex; gap: 8px; padding: 8px 14px; border-bottom: 1px solid var(--border); background: color-mix(in srgb, var(--accent) 5%, var(--panel)); }
.kb-edit-input { flex: 1; min-width: 0; padding: 6px 10px; font-size: 13px; color: var(--text); background: var(--panel-2);
  border: 1px solid var(--accent-d); border-radius: 4px; outline: none; }
.kb-docs { flex: 1; overflow-y: auto; padding: 8px 10px 14px; }
.kb-loading, .kb-empty { flex: 1; display: flex; align-items: center; justify-content: center; font-size: 13px; color: var(--faint); padding: 30px; }

/* 文档行 */
.kb-doc { display: flex; align-items: center; gap: 10px; padding: 8px 10px; border-radius: 4px; }
.kb-doc:hover { background: color-mix(in srgb, var(--accent) 8%, transparent); }
.kb-doc.searching { cursor: pointer; }
.kb-ext { flex: none; width: 40px; text-align: center; font-size: 10px; font-weight: 700; font-family: var(--mono);
  padding: 3px 0; border-radius: 3px; letter-spacing: .5px; }
.kb-ext.epdf { color: #d9484f; background: rgba(217,72,79,.12); }
.kb-ext.edoc { color: #2f6fdb; background: rgba(47,111,219,.12); }
.kb-ext.etxt { color: #2f8f5b; background: rgba(47,143,91,.12); }
.kb-ext.emd { color: #b8873a; background: rgba(184,135,58,.14); }
.kb-doc-main { flex: 1; min-width: 0; }
.kb-doc-title { font-size: 13px; font-weight: 600; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-doc-meta { display: flex; gap: 6px; margin-top: 2px; font-size: 11px; color: var(--faint); flex-wrap: wrap; }
.kb-doc-orig { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 220px; }
.kb-snippet { margin-top: 3px; font-size: 12px; color: var(--muted); line-height: 1.5; max-height: 40px; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
.kb-doc-ops { flex: none; display: none; gap: 2px; }
.kb-doc:hover .kb-doc-ops { display: flex; }

/* 通用小按钮 */
.kb-mini { width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; font-size: 12px;
  color: var(--muted); background: transparent; border: none; border-radius: 3px; cursor: pointer; padding: 0; }
.kb-mini:hover { color: var(--accent-d); background: color-mix(in srgb, var(--accent) 12%, transparent); }
.kb-mini.danger:hover { color: var(--red); background: rgba(188,59,48,.10); }
.kb-btn { padding: 6px 14px; font-size: 12px; font-family: var(--ui); border-radius: 4px; cursor: pointer;
  color: var(--text); background: var(--panel-2); border: 1px solid var(--border); text-decoration: none; display: inline-flex; align-items: center; }
.kb-btn:hover { border-color: var(--accent); color: var(--accent-d); }
.kb-btn.primary { color: #fff; background: var(--accent); border-color: var(--accent); }
.kb-btn.primary:hover { background: var(--accent-d); border-color: var(--accent-d); color: #fff; }

/* 查看层 */
.kb-view-mask { position: fixed; inset: 0; background: rgba(12,18,26,.55); display: flex; align-items: center; justify-content: center; z-index: 310; }
.kb-view { width: 760px; max-width: 94vw; height: 620px; max-height: 90vh; background: var(--panel);
  border: 1px solid var(--border); border-radius: 6px; box-shadow: 0 20px 60px rgba(0,0,0,.4);
  display: flex; flex-direction: column; overflow: hidden; }
.kb-view-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 10px 14px; border-bottom: 1px solid var(--border); }
.kb-view-title { display: flex; align-items: center; gap: 8px; font-size: 14px; font-weight: 600; min-width: 0; }
.kb-view-title span:last-child { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.kb-view-ops { display: flex; gap: 8px; flex: none; }
.kb-view-body { flex: 1; overflow-y: auto; padding: 16px 20px; font-size: 13px; line-height: 1.7; color: var(--text); }
.kb-md-h1 { font-size: 20px; margin: 14px 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--border); }
.kb-md-h2 { font-size: 17px; margin: 12px 0 6px; }
.kb-md-h3 { font-size: 15px; margin: 10px 0 4px; }
.kb-md-h4, .kb-md-h5, .kb-md-h6 { font-size: 13px; margin: 8px 0 4px; }
.kb-md-p { margin: 6px 0; }
.kb-md-ul { margin: 6px 0; padding-left: 20px; }
.kb-md-ul li { margin: 3px 0; }
.kb-md-code { background: var(--panel-2); border: 1px solid var(--border); border-radius: 4px; padding: 10px 12px;
  font-family: var(--mono); font-size: 12px; overflow-x: auto; white-space: pre; margin: 8px 0; }
.kb-md-line { margin: 5px 0; }
.kb-md-empty { color: var(--faint); text-align: center; padding: 40px 0; }

.kb-file { display: none; }
</style>
