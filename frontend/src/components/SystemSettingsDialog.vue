<template>
  <div class="ss-mask" @click.self="$emit('close')">
    <div class="ss-modal" role="dialog" aria-modal="true" :aria-label="t('系统设置')">
      <div class="ss-head">
        <span class="ss-title">{{ t('系统设置') }}</span>
        <button class="x-btn lg" @click="$emit('close')" :aria-label="t('关闭')">×</button>
      </div>

      <div class="ss-body">
        <!-- 左侧目录 -->
        <nav class="ss-nav" :aria-label="t('设置分类')">
          <button v-for="p in pages" :key="p.id" class="ss-nav-item" :class="{ on: active === p.id }"
                  role="tab" :aria-selected="active === p.id" @click="active = p.id">
            <Icon :name="p.icon" :size="15" />
            <span>{{ t(p.label) }}</span>
          </button>
        </nav>

        <!-- 右侧内容 -->
        <div class="ss-main">
          <!-- 显示 -->
          <section v-if="active === 'display'" class="ss-page">
            <div class="ss-page-title">{{ t('显示') }}</div>
            <div class="ss-page-desc">{{ t('调整 3D 场景渲染与相机行为') }}</div>

            <!-- 界面主题（夜间模式 / 白天模式） -->
            <div class="ss-card" style="margin-bottom: 12px;">
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('界面主题') }}</div>
                  <div class="ss-desc">{{ t('夜间模式适合暗光环境，白天模式下顶栏与底栏采用亮色') }}</div>
                </div>
                <div class="ss-ctrl ss-segs">
                  <button class="ss-seg" :class="{ on: themeMode === 'light' }" @click="setThemeMode('light')">{{ t('白天模式') }}</button>
                  <button class="ss-seg" :class="{ on: themeMode === 'dark' }" @click="setThemeMode('dark')">{{ t('夜间模式') }}</button>
                </div>
              </div>
            </div>

            <!-- 系统主题色 -->
            <div class="ss-card" style="margin-bottom: 12px;">
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('系统主题色') }}</div>
                  <div class="ss-desc">{{ t('切换全局主题色（品牌黄 / 科技蓝 / 生态绿 / 中国红）') }}</div>
                </div>
                <div class="ss-ctrl ss-swatches">
                  <button v-for="a in ACCENTS" :key="a.id" class="ss-swatch" :class="{ on: accent === a.id }"
                          :style="{ '--sw': SWATCH_COLORS[a.id] }" :title="t(a.labelZh)"
                          :aria-label="t(a.labelZh)" @click="setAccent(a.id)"></button>
                </div>
              </div>
            </div>

            <!-- 系统语言 -->
            <div class="ss-card" style="margin-bottom: 12px;">
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('系统语言') }}</div>
                  <div class="ss-desc">{{ t('切换界面显示语言（简体中文 / English）') }}</div>
                </div>
                <div class="ss-ctrl ss-segs">
                  <button class="ss-seg" :class="{ on: getLang() === 'zh-CN' }" @click="setLang('zh-CN')">{{ t('简体中文') }}</button>
                  <button class="ss-seg" :class="{ on: getLang() === 'en-US' }" @click="setLang('en-US')">English</button>
                </div>
              </div>
            </div>

            <div class="ss-card">
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('画面亮度') }}</div>
                  <div class="ss-desc">{{ t('调整 3D 场景曝光（暗 0.3 ~ 2.5 亮）') }}</div>
                </div>
                <div class="ss-ctrl">
                  <input type="range" class="ss-slider" min="0.3" max="2.5" step="0.05"
                         :value="store.brightness" @input="store.setBrightness(+$event.target.value)" />
                  <span class="ss-val">{{ (store.brightness * 100).toFixed(0) }}%</span>
                </div>
              </div>
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('自动环视') }}</div>
                  <div class="ss-desc">{{ t('相机自动环绕旋转园区') }}</div>
                </div>
                <div class="ss-ctrl">
                  <button class="ss-sw" :class="{ on: store.autoRotate }" role="switch" :aria-checked="store.autoRotate"
                          @click="store.setAutoRotate(!store.autoRotate)"><i></i></button>
                </div>
              </div>
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('全屏模式') }}</div>
                  <div class="ss-desc">{{ t('隐藏菜单栏 / 工具栏 / 状态栏等全部边栏，仅保留 3D 数字孪生 / HMI人机交互屏内容区') }}</div>
                </div>
                <div class="ss-ctrl">
                  <button class="ss-sw" :class="{ on: store.fullscreenOn }" role="switch" :aria-checked="store.fullscreenOn"
                          @click="store.toggleFullscreen()"><i></i></button>
                </div>
              </div>
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('音效反馈') }}</div>
                  <div class="ss-desc">{{ t('操作成功 / 失败 / 任务完成时的声音提示（PTC 多模态反馈，开关实时生效）') }}</div>
                </div>
                <div class="ss-ctrl">
                  <button class="ss-sw" :class="{ on: soundOn }" role="switch" :aria-checked="soundOn"
                          @click="onToggleSound"><i></i></button>
                </div>
              </div>
            </div>
          </section>

          <!-- 布局 -->
          <section v-if="active === 'layout'" class="ss-page">
            <div class="ss-page-title">{{ t('布局') }}</div>
            <div class="ss-page-desc">{{ t('界面面板的显示与隐藏') }}</div>
            <div class="ss-card">
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('左侧栏（资产树）') }}</div>
                  <div class="ss-desc">{{ t('工艺 / 设备 / 原料 / 策略') }}</div>
                </div>
                <div class="ss-ctrl">
                  <button class="ss-sw" :class="{ on: store.leftOpen }" :disabled="store.fullscreenOn" role="switch"
                          :aria-checked="store.leftOpen" @click="store.toggleLeft()"><i></i></button>
                </div>
              </div>
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('右侧栏（检视器）') }}</div>
                  <div class="ss-desc">{{ t('上下文属性与数据检视') }}</div>
                </div>
                <div class="ss-ctrl">
                  <button class="ss-sw" :class="{ on: store.rightOpen }" :disabled="store.fullscreenOn" role="switch"
                          :aria-checked="store.rightOpen" @click="store.toggleRight()"><i></i></button>
                </div>
              </div>
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('底栏（命令行窗口）') }}</div>
                  <div class="ss-desc">{{ t('命令行窗口 + 状态条') }}</div>
                </div>
                <div class="ss-ctrl">
                  <button class="ss-sw" :class="{ on: store.bottomOpen }" :disabled="store.fullscreenOn" role="switch"
                          :aria-checked="store.bottomOpen" @click="store.toggleBottom()"><i></i></button>
                </div>
              </div>
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('底栏快讯') }}</div>
                  <div class="ss-desc">{{ t('状态条滚动显示市场快讯') }}</div>
                </div>
                <div class="ss-ctrl">
                  <button class="ss-sw" :class="{ on: store.newsTickerOn }" role="switch"
                          :aria-checked="store.newsTickerOn" @click="store.toggleNewsTicker()"><i></i></button>
                </div>
              </div>
              <div v-if="store.fullscreenOn" class="ss-hint">{{ t('全屏模式下布局面板已隐藏，退出全屏后恢复。') }}</div>
            </div>
          </section>

          <!-- 场景 -->
          <section v-if="active === 'scene'" class="ss-page">
            <div class="ss-page-title">{{ t('场景') }}</div>
            <div class="ss-page-desc">{{ t('数字孪生仿真场景设置') }}</div>
            <div class="ss-card">
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('仿真情景') }}</div>
                  <div class="ss-desc">{{ t('四大控排行业情景') }}</div>
                </div>
                <div class="ss-ctrl ss-segs">
                  <button v-for="s in store.scenarios" :key="s.id" class="ss-seg"
                          :class="{ on: s.id === store.scenario }" @click="store.setScenario(s.id)">{{ t(s.label) }}</button>
                </div>
              </div>
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('场景环境') }}</div>
                  <div class="ss-desc">{{ t('数字孪生外围景观') }}</div>
                </div>
                <div class="ss-ctrl ss-segs">
                  <button v-for="e in store.envModes" :key="e.id" class="ss-seg"
                          :class="{ on: e.id === store.envMode }" @click="store.setEnvMode(e.id)">{{ t(e.label) }}</button>
                </div>
              </div>
            </div>
          </section>

          <!-- 实时链路 -->
          <section v-if="active === 'link'" class="ss-page">
            <div class="ss-page-title">{{ t('实时链路') }}</div>
            <div class="ss-page-desc">{{ t('数据接入与链路状态') }}</div>
            <div class="ss-card">
              <div class="ss-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('数据源状态') }}</div>
                  <div class="ss-desc">{{ t('接入实时数据的链路状态') }}</div>
                </div>
                <div class="ss-ctrl ss-feed">
                  <span class="feed-dot" :class="'feed-' + store.feedStatus"></span>
                  <span class="ss-feed-tx">{{ feedText }}</span>
                </div>
              </div>
            </div>
          </section>

          <!-- AI 模型（LLM 配置） -->
          <section v-if="active === 'llm'" class="ss-page">
            <div class="ss-page-title">{{ t('AI 模型') }}</div>
            <div class="ss-page-desc">{{ t('语言模型（LLM）接入配置，保存后立即生效，无需重启服务') }}</div>
            <div class="ss-card">
              <div class="ss-form-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('接口地址（Base URL）') }}</div>
                  <div class="ss-desc">{{ t('OpenAI 兼容接口地址') }}</div>
                </div>
                <input v-model.trim="llmForm.baseUrl" class="ss-input" type="text" spellcheck="false"
                       :placeholder="t('例如 https://api.deepseek.com/v1')" @input="clearLlmMsg" />
              </div>
              <div class="ss-form-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('API Key') }}</div>
                  <div class="ss-desc">
                    <template v-if="llmConfig.has_api_key">{{ t('已配置，留空表示保留原 Key') }}</template>
                    <template v-else>{{ t('未配置，填写后模型功能可用') }}</template>
                  </div>
                </div>
                <input v-model="llmForm.apiKey" class="ss-input" type="password" autocomplete="off" spellcheck="false"
                       :placeholder="llmConfig.api_key_masked || t('sk-…')" @input="clearLlmMsg" />
              </div>
              <div class="ss-form-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('模型名称') }}</div>
                  <div class="ss-desc">{{ t('对话 / 策略拆解使用的模型') }}</div>
                </div>
                <input v-model.trim="llmForm.model" class="ss-input" type="text" spellcheck="false"
                       :placeholder="t('例如 deepseek-chat')" @input="clearLlmMsg" />
              </div>
            </div>

            <div v-if="llmMsg.text" class="ss-msg" :class="llmMsg.ok ? 'ok' : 'err'">
              <span>{{ llmMsg.text }}</span>
              <span v-if="llmMsg.latency != null" class="ss-msg-lat">{{ llmMsg.latency }}ms</span>
            </div>

            <div class="ss-llm-btns">
              <button class="ss-btn" :disabled="llmBusy.test" @click="testLlm">{{ llmBusy.test ? t('测试中…') : t('测试连接') }}</button>
              <button class="ss-btn primary" :disabled="llmBusy.save" @click="saveLlm">{{ llmBusy.save ? t('保存中…') : t('保存配置') }}</button>
            </div>
          </section>

          <!-- 知识库（LLM-WIKI 路径设置） -->
          <section v-if="active === 'kb'" class="ss-page">
            <div class="ss-page-title">{{ t('知识库') }}</div>
            <div class="ss-page-desc">{{ t('LLM-WIKI 式知识库根目录，保存后立即生效，无需重启服务') }}</div>
            <div class="ss-card">
              <div class="ss-form-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('知识库路径') }}</div>
                  <div class="ss-desc">
                    {{ t('文件夹即知识库，支持多级目录；文档以 Markdown 存放，PDF/Word/TXT 上传后自动解析') }}
                  </div>
                </div>
                <input v-model.trim="kbForm.rootPath" class="ss-input" type="text" spellcheck="false"
                       :placeholder="kbConfig.default_path" @input="clearKbMsg" />
              </div>
              <div v-if="kbConfig.configured" class="ss-form-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('当前生效路径') }}</div>
                  <div class="ss-desc">{{ kbConfig.root_path }}</div>
                </div>
              </div>
              <div class="ss-form-row">
                <div class="ss-info">
                  <div class="ss-name">{{ t('默认路径') }}</div>
                  <div class="ss-desc">{{ kbConfig.default_path }}</div>
                </div>
              </div>
            </div>

            <div v-if="kbMsg.text" class="ss-msg" :class="kbMsg.ok ? 'ok' : 'err'">
              <span>{{ kbMsg.text }}</span>
            </div>

            <div class="ss-llm-btns">
              <button class="ss-btn" :disabled="kbBusy" @click="resetKb">{{ t('恢复默认路径') }}</button>
              <button class="ss-btn primary" :disabled="kbBusy" @click="saveKb">{{ kbBusy ? t('保存中…') : t('保存路径') }}</button>
            </div>
          </section>
        </div>
      </div>

      <div class="ss-actions">
        <button class="ss-btn ghost" @click="resetDefaults">{{ t('恢复默认设置') }}</button>
        <span class="sp"></span>
        <button class="ss-btn primary" @click="$emit('close')">{{ t('关闭') }}</button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useSimStore } from '../stores/sim'
import Icon from './Icon.vue'
import { soundEnabled, toggleSound } from '../utils/feedback'
import { t, setLang, getLang } from '../i18n'
import { ACCENTS, accent, setAccent, themeMode, setThemeMode } from '../theme'

const store = useSimStore()
defineEmits(['close'])

// 主题色色板：色块颜色（浅色主题下的品牌主色）
const SWATCH_COLORS = {
  amber: '#F0A500',
  blue: '#2F6FED',
  green: '#2E9E6B',
  red: '#D64545',
}

// 音效反馈开关（实时生效，localStorage 持久化）
const soundOn = ref(soundEnabled())
function onToggleSound() { soundOn.value = toggleSound() }

// 左侧目录：id / 标签（翻译 key）/ 图标
const pages = [
  { id: 'display', label: '显示', icon: 'eye' },
  { id: 'layout', label: '布局', icon: 'panelLeft' },
  { id: 'scene', label: '场景', icon: 'cube' },
  { id: 'link', label: '实时链路', icon: 'flow' },
  { id: 'llm', label: 'AI 模型', icon: 'bolt' },
  { id: 'kb', label: '知识库', icon: 'database' },
]
const active = ref('display')

const feedText = computed(() => ({ open: t('已连接'), closed: t('已断开'), error: t('异常'), init: t('连接中…') }[store.feedStatus] || ''))

// ------------------------- LLM 配置 -------------------------
const llmForm = ref({ baseUrl: '', apiKey: '', model: '' })
const llmConfig = ref({ base_url: '', model: '', api_key_masked: '', has_api_key: false })
const llmMsg = ref({ text: '', ok: false, latency: null })
const llmBusy = ref({ test: false, save: false })

async function loadLlmConfig() {
  try {
    const res = await fetch('/api/settings/llm')
    const data = await res.json()
    if (data.ok && data.config) {
      llmConfig.value = data.config
      llmForm.value.baseUrl = data.config.base_url || ''
      llmForm.value.model = data.config.model || ''
      llmForm.value.apiKey = ''
    }
  } catch (e) {
    llmMsg.value = { text: t('配置读取失败：') + e, ok: false, latency: null }
  }
}

function clearLlmMsg() { llmMsg.value = { text: '', ok: false, latency: null } }

function setLlmMsg(ok, text, latency = null) { llmMsg.value = { text, ok, latency } }

async function saveLlm() {
  llmBusy.value.save = true
  try {
    const res = await fetch('/api/settings/llm', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: llmForm.value.baseUrl,
        api_key: llmForm.value.apiKey,
        model: llmForm.value.model,
      }),
    })
    const data = await res.json()
    if (data.ok && data.config) {
      llmConfig.value = data.config
      llmForm.value.apiKey = ''
      setLlmMsg(true, t('配置已保存，立即生效'))
    } else {
      setLlmMsg(false, data.detail || t('保存失败'))
    }
  } catch (e) {
    setLlmMsg(false, t('保存失败：') + e)
  } finally {
    llmBusy.value.save = false
  }
}

async function testLlm() {
  llmBusy.value.test = true
  setLlmMsg(false, '')
  try {
    const res = await fetch('/api/settings/llm/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        base_url: llmForm.value.baseUrl,
        api_key: llmForm.value.apiKey,
        model: llmForm.value.model,
      }),
    })
    const data = await res.json()
    setLlmMsg(!!data.ok, data.message || (data.ok ? t('连接成功') : t('连接失败')), data.latency_ms ?? null)
  } catch (e) {
    setLlmMsg(false, t('测试失败：') + e)
  } finally {
    llmBusy.value.test = false
  }
}

// ------------------------- 知识库路径（LLM-WIKI） -------------------------
const kbForm = ref({ rootPath: '' })
const kbConfig = ref({ root_path: '', default_path: '', configured: false })
const kbMsg = ref({ text: '', ok: false })
const kbBusy = ref(false)

async function loadKbConfig() {
  try {
    const res = await fetch('/api/settings/kb')
    const data = await res.json()
    if (data.ok && data.config) {
      kbConfig.value = data.config
      kbForm.value.rootPath = ''
    }
  } catch (e) {
    kbMsg.value = { text: t('配置读取失败：') + e, ok: false }
  }
}

function clearKbMsg() { kbMsg.value = { text: '', ok: false } }

async function saveKb() {
  kbBusy.value = true
  try {
    const res = await fetch('/api/settings/kb', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ root_path: kbForm.value.rootPath }),
    })
    const data = await res.json()
    if (data.ok && data.config) {
      kbConfig.value = data.config
      kbForm.value.rootPath = ''
      kbMsg.value = { text: t('知识库路径已保存，立即生效'), ok: true }
    } else {
      kbMsg.value = { text: data.message || data.detail || t('保存失败'), ok: false }
    }
  } catch (e) {
    kbMsg.value = { text: t('保存失败：') + e, ok: false }
  } finally {
    kbBusy.value = false
  }
}

async function resetKb() {
  kbBusy.value = true
  try {
    const res = await fetch('/api/settings/kb', { method: 'DELETE' })
    const data = await res.json()
    if (data.ok && data.config) {
      kbConfig.value = data.config
      kbForm.value.rootPath = ''
      kbMsg.value = { text: t('已恢复默认知识库路径'), ok: true }
    } else {
      kbMsg.value = { text: data.message || data.detail || t('恢复失败'), ok: false }
    }
  } catch (e) {
    kbMsg.value = { text: t('恢复失败：') + e, ok: false }
  } finally {
    kbBusy.value = false
  }
}

onMounted(() => { loadLlmConfig(); loadKbConfig() })

// 恢复默认设置：所有设置项实时生效于 store，无需保存
function resetDefaults() {
  store.setBrightness(0.95)
  store.setAutoRotate(false)
  if (store.fullscreenOn) store.toggleFullscreen()
  if (!store.leftOpen) store.toggleLeft()
  if (!store.rightOpen) store.toggleRight()
  if (!store.bottomOpen) store.toggleBottom()
  if (!store.newsTickerOn) store.toggleNewsTicker()
  store.setEnvMode('industrial')
  if (store.scenario !== 'steel') store.setScenario('steel')
  if (!soundEnabled()) { onToggleSound() } else { soundOn.value = true }
  setAccent('amber')
  setThemeMode('light')
  setLang('zh-CN')
  // LLM 配置恢复默认（清除动态配置，回退环境变量/内置默认）
  fetch('/api/settings/llm', { method: 'DELETE' })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok && data.config) {
        llmConfig.value = data.config
        llmForm.value.baseUrl = data.config.base_url || ''
        llmForm.value.model = data.config.model || ''
        llmForm.value.apiKey = ''
        setLlmMsg(true, t('配置已恢复默认'))
      }
    })
    .catch(() => {})
  // 知识库路径恢复默认
  fetch('/api/settings/kb', { method: 'DELETE' })
    .then((r) => r.json())
    .then((data) => {
      if (data.ok && data.config) {
        kbConfig.value = data.config
        kbForm.value.rootPath = ''
      }
    })
    .catch(() => {})
}
</script>

<style scoped>
.ss-mask { position: fixed; inset: 0; background: rgba(20,30,40,.42); display: flex; align-items: center; justify-content: center; z-index: 200; }
.ss-modal { width: 780px; max-width: 94vw; height: min(600px, 86vh); display: flex; flex-direction: column; background: var(--panel);
  border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 18px 50px rgba(0,0,0,.28); font-family: var(--ui); color: var(--text); }
.ss-head { display: flex; align-items: center; justify-content: space-between; padding: 12px 16px; border-bottom: 1px solid var(--border); }
.ss-title { font-size: 14px; font-weight: 700; letter-spacing: .5px; }

/* 主体：左侧目录 + 右侧内容（高度由 .ss-modal 固定，切换标签时窗口尺寸不跳动） */
.ss-body { flex: 1; min-height: 0; display: flex; }
.ss-nav { width: 168px; flex: none; display: flex; flex-direction: column; gap: 2px; padding: 10px 8px;
  background: var(--bar); border-right: 1px solid var(--border); overflow: auto; }
.ss-nav-item { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border: none; border-radius: 6px;
  background: transparent; color: var(--muted); font-size: 12px; cursor: pointer; position: relative; text-align: left; }
.ss-nav-item:hover { background: var(--panel); color: var(--text); }
.ss-nav-item.on { background: var(--accent-l); color: var(--accent-d); font-weight: 600; }
.ss-nav-item.on::before { content: ''; position: absolute; left: -8px; top: 22%; bottom: 22%; width: 3px; border-radius: 2px; background: var(--accent); }

.ss-main { flex: 1; min-width: 0; overflow: auto; padding: 16px 18px 18px; }
.ss-page-title { font-size: 15px; font-weight: 700; }
.ss-page-desc { font-size: 11px; color: var(--muted); margin: 3px 0 14px; }
.ss-card { border: 1px solid var(--border); border-radius: 6px; background: var(--bar); overflow: hidden; }
.ss-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 14px; border-bottom: 1px solid var(--border); }
.ss-row:last-child { border-bottom: none; }
.ss-info { min-width: 0; }
.ss-name { font-size: 12px; font-weight: 600; }
.ss-desc { font-size: 10px; color: var(--muted); margin-top: 2px; }
.ss-ctrl { display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
/* 滑块 */
.ss-slider { width: 150px; accent-color: var(--accent-d); cursor: pointer; }
.ss-val { font-size: 11px; color: var(--muted); min-width: 36px; text-align: right; font-variant-numeric: tabular-nums; }
/* 开关 */
.ss-sw { position: relative; width: 38px; height: 20px; border-radius: 12px; border: 1px solid var(--border); background: var(--panel); cursor: pointer; padding: 0; transition: background .15s, border-color .15s; }
.ss-sw i { position: absolute; top: 2px; left: 2px; width: 14px; height: 14px; border-radius: 50%; background: var(--faint); transition: left .15s, background .15s; }
.ss-sw.on { background: var(--accent); border-color: var(--accent-d); }
.ss-sw.on i { left: 20px; background: #fff; }
.ss-sw:disabled { opacity: .4; cursor: not-allowed; }
/* 分段选择 */
.ss-segs { display: flex; gap: 4px; flex-wrap: wrap; max-width: 320px; justify-content: flex-end; }
.ss-seg { padding: 4px 10px; border: 1px solid var(--border); border-radius: 2px; font-size: 10px; color: var(--muted); background: var(--panel); cursor: pointer; }
.ss-seg:hover { border-color: var(--accent-d); }
.ss-seg.on { background: var(--accent-l); border-color: var(--accent-d); color: var(--accent-d); font-weight: 600; }
/* 系统主题色色板 */
.ss-swatches { display: flex; gap: 9px; }
.ss-swatch { width: 26px; height: 26px; padding: 0; border-radius: 50%; background: var(--sw); border: 2px solid var(--border); cursor: pointer; position: relative; transition: transform .12s, border-color .12s, box-shadow .12s; }
.ss-swatch:hover { transform: scale(1.12); border-color: var(--text); }
.ss-swatch.on { border-color: var(--text); box-shadow: 0 0 0 2px var(--panel), 0 0 0 3.5px var(--accent); }
.ss-swatch.on::after { content: '✓'; position: absolute; inset: 0; display: grid; place-items: center; color: #fff; font-size: 13px; font-weight: 700; text-shadow: 0 1px 2px rgba(0,0,0,.55); }
/* 数据源状态 */
.ss-feed { gap: 6px; }
.ss-feed-tx { font-size: 11px; color: var(--muted); }
.ss-hint { font-size: 10px; color: var(--faint); padding: 8px 14px; border-top: 1px solid var(--border); }
/* AI 模型（LLM 配置）表单 */
.ss-form-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; padding: 12px 14px; border-bottom: 1px solid var(--border); }
.ss-form-row:last-child { border-bottom: none; }
.ss-input { width: 340px; max-width: 100%; padding: 8px 10px; border: 1px solid var(--border); border-radius: 6px; background: var(--panel); color: var(--text); font-size: 12px; font-family: var(--ui); outline: none; transition: border-color .15s; }
.ss-input:focus { border-color: var(--accent-d); }
.ss-input::placeholder { color: var(--faint); }
.ss-msg { display: flex; align-items: center; gap: 8px; margin: 10px 2px 0; padding: 8px 12px; border-radius: 6px; font-size: 11px; line-height: 1.5; }
.ss-msg.ok { background: rgba(46,160,67,.12); color: #2ea043; border: 1px solid rgba(46,160,67,.3); }
.ss-msg.err { background: rgba(248,81,73,.1); color: #f85149; border: 1px solid rgba(248,81,73,.3); }
.ss-msg-lat { margin-left: auto; font-variant-numeric: tabular-nums; }
.ss-llm-btns { display: flex; gap: 10px; margin-top: 14px; justify-content: flex-end; }
.ss-btn:disabled { opacity: .5; cursor: not-allowed; }
.ss-actions { display: flex; align-items: center; gap: 10px; padding: 12px 16px; border-top: 1px solid var(--border); }
.ss-actions .sp { flex: 1; }
.ss-btn { padding: 8px 14px; border: 1px solid var(--border); border-radius: 6px; background: var(--bar); cursor: pointer; font-size: 12px; color: var(--text); }
.ss-btn:hover { border-color: var(--accent-d); }
.ss-btn.primary { background: var(--accent); border-color: var(--accent-d); color: #fff; }
.ss-btn.primary:hover { background: var(--accent-d); }
.ss-btn.ghost { background: transparent; }
.sp { flex: 1; }
</style>
