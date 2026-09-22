<template>
  <!-- 数据服务接口（独立模块）：对外集成用的接口清单（历史/实时数据查询 + 指令下发），
       数据来自 GET /api/data-sources/integration，接口地址随部署自动拼接，无需配置。 -->
  <section id="cbx-sec-apis" class="cbx-sec">
    <div class="cbx-sec-head">
      <button class="cbx-caret" @click="toggle" :title="open ? t('收起') : t('展开')">{{ open ? '▾' : '▸' }}</button>
      <b class="cbx-sec-toggle" @click="toggle">{{ t('数据服务接口') }}</b>
      <span class="cbx-sec-spacer"></span>
      <span v-if="baseUrl" class="cbx-sec-sub mono">{{ baseUrl }}</span>
      <button class="cbx-op cbx-xs" :disabled="loading" @click="load">↻ {{ t('刷新') }}</button>
    </div>

    <div v-if="open" class="cbx-sec-desc">{{ t('历史/实时数据查询与指令下发的对外接口清单（含调用示例，供第三方系统集成）') }}</div>

    <div v-if="open" class="ds-catalog">
      <div v-if="loading && !groups.length" class="cbx-sec-sub">{{ t('加载中…') }}</div>
      <div v-else-if="err" class="cbx-sec-sub ds-api-err">{{ t('接口清单加载失败') }}：{{ err }}</div>
      <div v-else-if="!groups.length" class="cbx-sec-sub">{{ t('暂无接口清单') }}</div>
      <div v-for="g in groups" :key="g.id" class="ds-api-group">
        <div class="ds-api-ghd">
          <b>{{ g.name }}</b>
          <span class="cbx-sec-sub">{{ g.desc }}</span>
        </div>
        <div v-for="it in (g.items || [])" :key="it.path" class="ds-api-item">
          <div class="ds-api-hd">
            <span class="ds-api-m" :class="it.method.toLowerCase()">{{ it.method }}</span>
            <span class="ds-api-path mono">{{ it.path }}</span>
            <span class="cbx-sec-spacer"></span>
            <button class="cbx-op cbx-xs" :title="t('复制调用示例')" @click="copyApiCall(it)">{{ t('复制') }}</button>
          </div>
          <div class="cbx-sec-sub">{{ it.desc }}</div>
          <div class="ds-api-body mono">{{ it.url }}</div>
          <div v-if="(it.params || []).length" class="ds-api-params">
            <span v-for="p in it.params" :key="p.name" class="ds-api-p mono" :class="{ req: p.required }">
              {{ p.name }}{{ p.required ? '*' : '' }}：{{ p.desc }}
            </span>
          </div>
          <div v-else-if="it.body" class="ds-api-body mono">{{ JSON.stringify(it.body) }}</div>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { api } from '../api/client'
import { useSimStore } from '../stores/sim'
import { t } from '../i18n'

const store = useSimStore()
const open = ref(true)          // 独立模块默认展开：接口清单是集成查阅入口，藏起来没人找得到
const loading = ref(false)
const err = ref('')             // 加载失败原因：空态必须给出可操作的提示，不能只写「暂无接口清单」
const baseUrl = ref('')
const groups = ref([])

async function load() {
  loading.value = true
  err.value = ''
  try {
    const r = await api.dataSourceCatalog()
    baseUrl.value = (r && r.base_url) || ''
    groups.value = (r && r.groups) || []
    if (!groups.value.length) err.value = t('接口返回为空')
  } catch (e) {
    // 失败必须留下痕迹：否则面板永远显示「暂无接口清单」，看不出是接口没通还是真没数据
    groups.value = []
    err.value = String((e && e.message) || e || t('未知错误'))
  } finally {
    loading.value = false
  }
}
function toggle() {
  open.value = !open.value
  // 每次展开都重新拉取：接口是自描述常量（极轻），且能自动走出「上次失败后一直空白」的状态
  if (open.value) load()
}
// 复制一条可直接执行的调用示例到剪贴板（GET 为完整 URL，POST 为 curl）
async function copyApiCall(it) {
  const cmd = it.method === 'GET'
    ? it.url
    : `curl -X ${it.method} '${it.url}' -H 'Content-Type: application/json' -d '${JSON.stringify(it.body || {})}`
  try {
    await navigator.clipboard.writeText(cmd)
    store.notify('success', t('已复制调用示例'), cmd)
  } catch (e) {
    if (window.prompt) window.prompt(t('复制失败，请手动复制'), cmd)
  }
}

onMounted(() => { if (open.value) load() })
</script>

<style scoped>
/* 独立模块自带样式：CarbonBoxView 的 .cbx-* 是 scoped，子组件拿不到，这里按同一口径复制一份 */
.cbx-sec { background: var(--panel); border: 1px solid var(--border); border-radius: 4px; padding: 10px 12px; }
.cbx-sec-head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; padding-bottom: 8px; border-bottom: 1px solid var(--border); }
/* 与 CarbonBoxView 同一字体层级：仅区块标题 500/14px，其余一律 400 靠字号区分 */
.cbx-sec-head b { font-size: 14px; font-weight: 500; flex: none; letter-spacing: .2px; }
.cbx-caret { flex: none; width: 18px; height: 18px; padding: 0; line-height: 1; font-size: 11px;
  color: var(--muted); background: transparent; border: none; border-radius: 4px; cursor: pointer; }
.cbx-caret:hover { color: var(--fg, var(--text)); background: color-mix(in srgb, var(--muted) 14%, transparent); }
.cbx-sec-toggle { cursor: pointer; user-select: none; }
.cbx-sec-toggle:hover { color: var(--accent, var(--green)); }
.cbx-sec-sub { color: var(--muted); font-size: 10px; }
.cbx-sec-spacer { flex: 1 1 auto; }
.cbx-sec-desc { color: var(--muted); font-size: 11px; line-height: 1.6; margin-bottom: 8px; }
.cbx-op {
  display: inline-flex; align-items: center; justify-content: center; gap: 4px;
  font-family: var(--ui, -apple-system, "Segoe UI", "PingFang SC", sans-serif);
  font-size: 11px; min-height: 22px; padding: 3px 9px; cursor: pointer;
  color: var(--text); background: var(--panel-2, var(--panel)); border: 1px solid var(--border); border-radius: 4px;
}
.cbx-op:hover:not(:disabled) { background: var(--panel-3, var(--panel)); border-color: var(--muted); color: var(--text); }
.cbx-op:disabled { opacity: .4; cursor: not-allowed; }
.cbx-op.cbx-xs { padding: 3px 8px; font-size: 10px; min-height: 20px; }

.ds-catalog { display: flex; flex-direction: column; gap: 8px; }
.ds-api-err { color: var(--red); }
.ds-api-group { display: flex; flex-direction: column; gap: 6px;
  border-top: 1px solid var(--border); padding-top: 6px; }
.ds-api-group:first-of-type { border-top: none; padding-top: 0; }
.ds-api-ghd { display: flex; align-items: center; gap: 6px; font-size: 13px; }
.ds-api-item { display: flex; flex-direction: column; gap: 4px; padding: 4px 0 4px 8px;
  border-left: 2px solid color-mix(in srgb, var(--accent, var(--green)) 35%, transparent); }
.ds-api-hd { display: flex; align-items: center; gap: 6px; }
.ds-api-m { font-size: 10px; font-weight: 400; padding: 1px 5px; border-radius: 4px;
  color: var(--fg, var(--text)); background: color-mix(in srgb, var(--muted) 16%, transparent); }
.ds-api-m.get { color: var(--green); background: color-mix(in srgb, var(--green) 16%, transparent); }
.ds-api-m.post { color: var(--accent, var(--blue)); background: color-mix(in srgb, var(--accent, var(--blue)) 16%, transparent); }
.ds-api-path { font-size: 12.5px; font-weight: 400; }
.ds-api-ghd b { font-weight: 400; font-size: 13px; }
.ds-api-params { display: flex; flex-wrap: wrap; gap: 4px 10px; font-size: 11px; color: var(--muted); }
.ds-api-p.req { color: var(--fg, var(--text)); }
.ds-api-body { font-size: 11px; color: var(--muted); white-space: pre-wrap; word-break: break-all;
  padding: 3px 6px; border-radius: 5px; background: color-mix(in srgb, var(--muted) 10%, transparent); }
</style>
