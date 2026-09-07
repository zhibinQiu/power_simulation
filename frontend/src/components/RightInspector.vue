<template>
  <aside class="inspector">
    <!-- 宽度拖拽手柄（左侧边缘） -->
    <div class="inspector-rsz" :class="{ dragging: rszDragging }" @mousedown.prevent="onRszStart" :title="t('拖拽调整宽度')"></div>
    <!-- 本析智擎模式：按需隐藏顶部标题栏与关闭按钮（窗口内自含工具条） -->
    <div v-if="mode !== 'agent'" class="sidebar-head">
      <span class="ttl">{{ headTitle }}</span>
      <span class="spacer"></span>
      <button v-if="mode !== 'overview' || store.selectedGroupId || store.selectedFlowId" class="x-btn" :title="t('返回总览')" @click="store.closeInspector()">✕</button>
    </div>    <div class="inspector-body" :class="{ scrolling }" @scroll="onScroll">
      <!-- 本析智擎：智能体对话界面（工具栏「本析智擎」切换，替换右侧属性弹窗，中间 3D 场景保持） -->
      <AgentChatView v-if="mode === 'agent'" />

      <!-- 报告面板（工具条「数据 → 报告 → 导出报告」，含历史报告管理） -->
      <ReportPanel v-else-if="mode === 'report'" />

      <!-- 场景/列表/左侧工艺目录点击实例：统一只用一个工序实例属性面板（能耗/碳排放/碳平衡/实时监测/可调节/核算台账/关联设备）；
           行业资源包（其它场景）按包内字典渲染通用工序属性 -->
      <OtherUnitPanel v-else-if="mode === 'unit' && store.customSceneOn" />
      <UnitCarbonDetail v-else-if="mode === 'unit'" />

      <!-- 原料属性 -->
      <MaterialInspector v-else-if="mode === 'material'" />

      <!-- 策略详情（点击左侧「策略 → 自定义」） -->
      <StrategyDetailPanel v-else-if="mode === 'strategyDetail'" />

      <!-- 编辑态：流程编排属性面板；非编辑态下点击工艺节点也展示其编排属性 -->
      <FlowInspector v-else-if="store.editMode || store.selectedFlowId" />

      <!-- 数字孪生（非编辑态）点击小组：数值展示型小组属性面板（成员工艺列表 + 实测值） -->
      <GroupDetail v-else-if="store.selectedGroupId" />

      <!-- 总览（模块可上下拖拽重排，顺序/折叠状态持久化） -->
      <template v-else-if="mode === 'overview'">
        <template v-for="sid in layout.state.order" :key="sid">
          <CollapseSection
            v-if="sid === 'plant'"
            :title="t('全厂总览')"
            tone="blue"
            drag-id="plant"
            v-model="layout.state.open[sid]"
            @drop="layout.move($event.from, $event.to, $event.position)"
          >
            <!-- 全厂总览：实时 / 日度 / 月度 / 年度 四档时段核算。
                 realtime=小时速率；日/月/年=当日/当月/当年 0 点起截止当前的累计量（速率随工况实时变化，累计按时间段积分，
                 非「当前速率 × 已过小时」；30s 结算 + 速率变化即结清上一段，跨周期自动归零）。
                 卡片分三组（产品 → 能源 → 碳排）；「产品」组仅在编排输出涉及物料库产品时显示：
                   产品：产量 / 产品收益（= 产量 × 主产品销售单价，物料属性「销售单价」可调）
                   能源：综合能耗（点开 = 燃料能耗 + 电力折标 · 同比/环比）/ 电耗 / 单位能耗 / 能源成本（= 外购用量 × 单价）
                   碳排：总排放（= 直接排放范围一 · 全国碳市场口径；点开 = 计算方式 · 同比/环比 · 碳素利用）/ 吨钢排放 / 预估碳成本 = (配额 n − 到年底外推排放 m) × 实时碳价 p；
                 外购电间接排放（范围二）在发电侧计入并承担配额，不并入钢铁企业总排——展开内仅以参考行注明，不参与核算与排行。
                 同比/环比仅在日度/月度档出现，暂无历史台账时显示「—」。 -->
            <div class="plant">
              <div class="plant-tabs" role="tablist">
                <button v-for="p in plantPeriods" :key="p.id" type="button" role="tab"
                        class="plant-tab" :class="{ on: plantPeriod === p.id }"
                        :aria-selected="plantPeriod === p.id"
                        :title="t(p.hint)" @click="plantPeriod = p.id">{{ t(p.label) }}</button>
              </div>
              <div class="plant-note">{{ periodDesc }}</div>
              <!-- 分组：产品 / 能源 / 碳排（产品→能源→碳排）。
                   「产品」组仅在「当前编排中工艺的输出涉及物料库产品」时展示：
                   资源包场景（如机房温控）无产品产出时自动隐藏该组与产品收益卡。 -->
              <template v-if="hasProduct">
                <div class="sec"><i class="dot d-prod"></i>{{ t('产品') }}</div>
                <div class="chips">
                  <div class="chip2"><span>{{ t('产量') }}</span><b>{{ fmt(period.steel) }}</b><i>{{ period.u.steel }}</i></div>
                  <div class="chip2 tog" :class="{ open: revOpen }" role="button" :title="t('点击展开产品收益计算：产量 × 销售单价（物料属性可调）')" @click="revOpen = !revOpen">
                    <span>{{ t('产品收益') }} <em class="caret">{{ revOpen ? '▾' : '▸' }}</em></span>
                    <b>{{ fmt(period.rev) }}</b><i>{{ period.u.rev }}</i>
                  </div>
                </div>
              </template>
              <div class="sec"><i class="dot d-ene"></i>{{ t('能源') }}</div>
              <div class="chips">
                <div class="chip2 tog" :class="{ open: energyOpen }" role="button" :title="t('点击展开综合能耗计算方式与同比/环比')" @click="energyOpen = !energyOpen">
                  <span>{{ t('综合能耗') }} <em class="caret">{{ energyOpen ? '▾' : '▸' }}</em></span>
                  <b>{{ fmt(period.energy) }}</b><i>{{ period.u.energy }}</i>
                </div>
                <div class="chip2"><span>{{ t('电耗') }}</span><b>{{ fmt(period.elec) }}</b><i>{{ period.u.elec }}</i></div>
                <div class="chip2"><span>{{ t('单位能耗') }}</span><b>{{ fmt(plantEnergy.intensity / 1000) }}</b><i>tce/t</i></div>
                <div class="chip2 tog" :class="{ open: costOpen }" role="button" :title="t('点击展开能源成本构成（外购用量 × 单价）')" @click="costOpen = !costOpen">
                  <span>{{ t('能源成本') }} <em class="caret">{{ costOpen ? '▾' : '▸' }}</em></span>
                  <b>{{ fmt(period.cost) }}</b><i>{{ period.u.cost }}</i>
                </div>
              </div>
              <div class="sec"><i class="dot d-co2"></i>{{ t('碳排') }}</div>
              <div class="chips">
                <div class="chip2 tog" :class="{ open: emiOpen }" role="button" :title="t('点击展开总排放（直接排放范围一 · 全国碳市场口径）计算方式、同比/环比与碳配额结余')" @click="emiOpen = !emiOpen">
                  <span>{{ t('总排放') }} <em class="caret">{{ emiOpen ? '▾' : '▸' }}</em></span>
                  <b :style="{color:co2Color}">{{ fmt(period.direct) }}</b><i>{{ period.u.co2 }}</i>
                </div>
                <div class="chip2"><span>{{ t('吨钢排放') }}</span><b :style="{color:co2Color}">{{ fmt(totals.intensity / 1000) }}</b><i>tCO₂/t</i></div>
                <div class="chip2 tog" :class="{ open: carbOpen }" role="button" :title="t('点击查看预估碳成本计算：(年配额 n − 到年底排放 m) × 实时碳价 p')" @click="carbOpen = !carbOpen">
                  <span>{{ t('预估碳成本') }} <em class="caret">{{ carbOpen ? '▾' : '▸' }}</em></span>
                  <b :class="carbEst.cls">{{ carbEst.text }}</b><i>万元/年</i>
                </div>
              </div>
              <!-- 产品收益展开：产量 × 主产品销售单价（速率口径 · 卡面随所选周期累计） -->
              <div v-if="revOpen && hasProduct" class="cost-detail rev-detail">
                <div class="cd-head">{{ t('产品收益 = 产量 × 主产品销售单价（卡面收益随所选周期累计）') }}</div>
                <div class="cd-row">
                  <span class="cd-name" style="background:#3f9d6b">{{ t('主产品') }}</span>
                  <span class="cd-qty">
                    <select class="q-in rev-sel" v-model="revMainId" :title="t('自动匹配产线终端产品，或手动指定')">
                      <option value="auto">{{ t('自动匹配（按产线终端工序）') }}</option>
                      <option v-for="p in PRODUCTS" :key="p.id" :value="p.id">{{ p.name }} · {{ fmt(revPriceOf(p.id)) }} 万元/{{ p.unit }}</option>
                    </select>
                  </span>
                  <span class="cd-amt"></span>
                </div>
                <div class="meth-line"><span class="ml">{{ t('① 产量（当前速率）') }}</span><i class="mval">{{ fmt(revQtyRate) }} t/h</i></div>
                <div class="meth-line"><span class="ml">{{ t('② 主产品销售单价') }}</span><i class="mval">{{ fmt(revSalePrice) }} 万元/t</i></div>
                <div class="meth-line"><span class="ml">{{ t('③ 收益（速率口径）= 产量 × 单价') }}</span><i class="mval">{{ fmt(revRateVal) }} 万元/h</i></div>
                <div class="cd-note">{{ t('当前主产品：{p}。自动匹配按产线终端工序（轧制 → 钢材 · 连铸 → 连铸坯 · 仅精炼/炼钢 → 精炼钢水），可手动切换；单价格为行业参考价，在「物料属性 → 销售单价」按市场行情调整后实时联动（单位：万元/t）。收益仅计终端主产品，内部中间品与副产品不重复计入。', { p: revMainMat.name }) }}</div>
              </div>
              <!-- 综合能耗展开：计算方式 + 同比 / 环比（日度/月度档） -->
              <div v-if="energyOpen" class="cost-detail energy-detail">
                <div class="cd-head">{{ t('综合能耗 = 燃料能耗 + 电力折标（速率口径 · 卡面随所选周期累计）') }}</div>
                <div class="meth-line"><span class="ml">{{ t('① 燃料能耗：各工序燃料燃烧低位发热量合计（含副产煤气自用）') }}</span><i class="mval">{{ fmt(eneFuelRate) }} GJ/h</i></div>
                <div class="meth-line"><span class="ml">{{ t('② 电力折标：外购电 × 3.6 GJ/MWh') }}</span><i class="mval">{{ fmt(eneElecRate) }} MWh/h × 3.6 = {{ fmt(eneElecGJ) }} GJ/h</i></div>
                <div class="meth-line"><span class="ml">{{ t('③ 综合能耗 = ① + ②') }}</span><i class="mval">{{ fmt(eneTotalRate) }} GJ/h</i></div>
                <div class="meth-line"><span class="ml">{{ t('④ 单位能耗（吨产品）= 综合能耗 × 0.03412 tce/GJ ÷ 产量') }}</span><i class="mval">{{ fmt(plantEnergy.intensity / 1000) }} tce/t</i></div>
                <template v-if="isCmpPeriod">
                  <div class="cmp-row">
                    <div class="chip2"><span>{{ t('同比') }}</span><b :class="dirCls(cmp.yoy)">{{ signedPct(cmp.yoy) }}</b><i>{{ t('较上年同期') }}</i></div>
                    <div class="chip2"><span>{{ t('环比') }}</span><b :class="dirCls(cmp.mom)">{{ signedPct(cmp.mom) }}</b><i>{{ t('较上一核算期') }}</i></div>
                  </div>
                  <div class="meth-line sub"><span class="ml">{{ t('同比 =（本期 − 上年同期）÷ 上年同期 · 环比 =（本期 − 上一核算期）÷ 上一核算期') }}</span></div>
                  <div class="cd-note">{{ t('同比/环比暂无历史台账数据，显示「—」；接入日/月报历史后自动启用，当前不做折算填充。') }}</div>
                </template>
              </div>
              <!-- 总排放展开：总排放 = 直接排放（范围一）· 全国碳市场口径；外购电（范围二）在发电侧计入、不计入本厂总排；+ 同比 / 环比 + 碳配额结余 -->
              <div v-if="emiOpen" class="cost-detail emi-detail">
                <div class="cd-head">{{ t('总排放（全国碳市场口径）= 直接排放（范围一）· 排放因子法') }}</div>
                <div class="meth-line"><span class="ml">{{ t('① 直接排放（范围一）= 燃料燃烧 + 工业过程（各工序求和）') }}</span><i class="mval" :style="{ color: co2Color }">{{ fmt(emiDirectRate) }} tCO₂/h</i></div>
                <div class="meth-line sub"><span class="ml">{{ t('① 明细：燃料燃烧 Σ 消耗量 × 低位发热量 × 单位热值含碳量 × 碳氧化率 × 44/12；工业过程：碳酸盐分解（石灰石 0.4395 / 白云石 0.4761 tCO₂/t）、电极消耗 3.663 tCO₂/t。焦化/烧结等中间工序燃料碳按碳流平衡转入下游不重复计入；副产煤气回收、余热发电外供做扣减。默认因子为国家/行业参考值，可在「排放因子」设置中替换。') }}</span></div>
                <div class="meth-line"><span class="ml">{{ t('② 外购电间接排放（范围二）= 外购电 × 电网平均排放因子 0.5703（发电侧排放 · 不计入企业总排放）') }}</span><i class="mval">{{ fmt(emiIndirectRate) }} tCO₂/h</i></div>
                <div class="cd-note">{{ t('全国碳市场（CEA）对钢铁企业的管控范围仅覆盖直接排放（范围一）——外购电的排放已在发电侧由电力行业承担配额，钢铁企业不重复计算，故卡面「总排放」与本处计算均不含范围二；如需按温室气体清单对外披露全口径，可在 ① 基础上另加 ②。') }}</div>
                <div class="meth-line"><span class="ml">{{ t('碳素利用：进入钢水/炉渣/捕集的碳 ÷ 输入碳') }}</span><i class="mval">{{ carbonUtilPct }}%</i></div>
                <template v-if="isCmpPeriod">
                  <div class="cmp-row">
                    <div class="chip2"><span>{{ t('同比') }}</span><b :class="dirCls(cmp.yoy)">{{ signedPct(cmp.yoy) }}</b><i>{{ t('较上年同期') }}</i></div>
                    <div class="chip2"><span>{{ t('环比') }}</span><b :class="dirCls(cmp.mom)">{{ signedPct(cmp.mom) }}</b><i>{{ t('较上一核算期') }}</i></div>
                  </div>
                  <div class="meth-line sub"><span class="ml">{{ t('同比 =（本期 − 上年同期）÷ 上年同期 · 环比 =（本期 − 上一核算期）÷ 上一核算期') }}</span></div>
                  <div class="cd-note">{{ t('同比/环比暂无历史台账数据，显示「—」；接入日/月报历史后自动启用，当前不做折算填充。') }}</div>
                </template>
                <div class="quota-bar">
                  <span class="qk">{{ t('碳配额结余') }}（{{ t('企业年配额 − 本年 CEA 直接排放') }}）</span>
                  <b :class="quotaRemain.cls">{{ quotaRemain.text }}</b>
                </div>
                <div class="cd-note">{{ t('配额为企业当年经全国碳市场免费分配及有偿购得的配额量（CEA 仅覆盖直接排放范围一，不统计外购电范围二；默认值可在下方「预估碳成本」中维护）；结余为负表示超排，需购入配额履约。') }}</div>
              </div>
              <!-- 能源成本展开：外购用量 × 单价 -->
              <div v-if="costOpen" class="cost-detail">
                <div class="cd-head">{{ t('能源成本构成 = 外购用量 × 单价（下表为小时速率 · 总卡金额随所选周期累计）') }}</div>
                <div v-for="it in costDetail" :key="it.id" class="cd-row">
                  <span class="cd-name" :style="{ background: it.color || 'var(--panel-3)' }">{{ it.name }}</span>
                  <span class="cd-qty">{{ fmt(it.qty) }} {{ it.unit }}/h × {{ fmt(it.price) }} 万元/{{ it.unit }}</span>
                  <span class="cd-amt"><b>{{ fmt(it.amt) }}</b><i>万元/h</i></span>
                </div>
                <div v-if="!costDetail.length" class="cd-row cd-empty">{{ t('当前流程无外购原燃料用量（自产/闭环），能源成本为 0。') }}</div>
                <div class="cd-note">{{ t('单价在「物料属性」中按采购合同调整后实时联动；内部中间品与副产品不重复计入。') }}</div>
              </div>
              <!-- 预估碳成本展开：计算方式 (n − m) × 实时碳价（n/m 均按 CEA 范围一直接排放），配额/碳价可维护 -->
              <div v-if="carbOpen" class="cost-detail carb-detail">
                <div class="cd-head">{{ t('预估碳成本 = (企业年配额 n − 到年底排放 m) × 实时碳价 p（n/m 均为范围一直接排放 · CEA）') }}</div>
                <div class="carb-edit">
                  <label>{{ t('企业年配额 n') }}<input class="q-in" v-model="quotaDraft" type="number" min="0" step="100000" :title="t('单位：tCO₂/年')" @change="onQuotaEdit" /></label>
                  <label>{{ t('实时碳价 p') }}<input class="q-in" v-model="priceDraft" type="number" min="0" step="0.0001" :title="t('单位：万元/tCO₂')" @change="onPriceEdit" /></label>
                </div>
                <div v-for="row in carbDetail" :key="row.k" class="cd-row">
                  <span class="cd-name" :style="{ background: row.color || 'var(--panel-3)' }">{{ row.k }}</span>
                  <span class="cd-qty">{{ row.v }}</span>
                  <span class="cd-amt"><b :class="row.cls || 'flat'">{{ row.a }}</b><i>{{ row.u }}</i></span>
                </div>
                <div class="cd-note">{{ t('m 按当前范围一直接排放速率 × 全年 8760 小时外推（即全厂维持当前运行水平到年底的 CEA 排放总量，为预测值）；n − m < 0 为超排缺口，缺口量 × 碳价即预估购碳支出；盈余则为配额结余，按碳价折算潜在交易收益。范围二（外购电）排放不纳入 CEA——其碳成本已体现于购电价且由发电企业承担配额，不重复计量。') }}</div>
              </div>
            </div>
          </CollapseSection>

          <CollapseSection
            v-else-if="sid === 'strategy' && store.strategy"
            :title="t('策略节能减碳效果')"
            tone="green"
            drag-id="strategy"
            v-model="layout.state.open[sid]"
            @drop="layout.move($event.from, $event.to, $event.position)"
          >
            <div class="strat-cmp">
              <div class="sc-item"><span>{{ t('节能量') }}</span><b class="good">{{ fmt(stratCmp.energyRed) }}</b><i>GJ/h</i></div>
              <div class="sc-item"><span>{{ t('节能率') }}</span><b class="good">{{ stratCmp.energyPct }}%</b><i>{{ t('较基线') }}</i></div>
              <div class="sc-item"><span>{{ t('减排量') }}</span><b class="good">{{ fmt(stratCmp.co2Red) }}</b><i>tCO₂/h</i></div>
              <div class="sc-item"><span>{{ t('减排率') }}</span><b class="good">{{ stratCmp.co2Pct }}%</b><i>{{ t('较基线') }}</i></div>
            </div>
          </CollapseSection>

          <CollapseSection
            v-else-if="sid === 'top'"
            :title="t('排放最高工序')"
            tone="red"
            drag-id="top"
            v-model="layout.state.open[sid]"
            @drop="layout.move($event.from, $event.to, $event.position)"
          >
            <div v-for="u in topEmitters" :key="u.id" class="lrow click te-row" :class="{active: store.selectedUnitId===u.id}" @click="store.selectUnit(u.id)">
              <div class="l-stack">
                <span class="l-tt">{{ u.name }}</span>
                <span class="l-sub">{{ typeLabel(u.type) }}</span>
                <span class="te-bar"><i :style="{ width: Math.min(100, u.share*100).toFixed(1)+'%', background: shareColor(u.share) }"></i></span>
              </div>
              <span class="l-trail" :style="{color:co2Color}">{{ fmt(u.co2_direct) }} <i class="u">tCO₂/h</i></span>
              <span class="te-pct">{{ (u.share*100).toFixed(1) }}%</span>
            </div>
          </CollapseSection>
        </template>
      </template>

      <!-- 设备属性 -->
      <DeviceDetail v-else-if="mode === 'device'" />

      <!-- 物料库（点击左侧「物料」） -->
      <template v-else-if="mode === 'materials'">
        <div class="park-sum">{{ t('共') }} {{ materialList.length }} {{ t('种物料（原料/中间产物/能源/副产品），点击查看隐含碳因子与配置。') }}</div>
        <div class="lview">
          <div v-for="m in materialList" :key="m.id" class="lrow click" :class="{active: store.selectedMaterialId===m.id}" @click="store.selectMaterial(m.id)">
            <div class="l-stack">
              <span class="l-tt">{{ m.name }}</span>
              <span class="l-sub">{{ m.cat }}</span>
            </div>
          </div>
        </div>
      </template>
    </div>
  </aside>
</template>

<script setup>
import { computed, ref, reactive, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { energyOf } from '../utils/energy'
import { useSimStore, UNIT_TYPES } from '../stores/sim'
import { MATERIALS, MATERIAL_MAP, PRODUCTS } from '../data/flowLibrary'
import { t } from '../i18n'
const AgentChatView = defineAsyncComponent(() => import('../views/AgentChatView.vue'))
import UnitCarbonDetail from './UnitCarbonDetail.vue'
import OtherUnitPanel from './OtherUnitPanel.vue'
import DeviceDetail from './DeviceDetail.vue'
import FlowInspector from './FlowInspector.vue'
import GroupDetail from './GroupDetail.vue'
import MaterialInspector from './MaterialInspector.vue'
import CollapseSection from './CollapseSection.vue'
import StrategyDetailPanel from './StrategyDetailPanel.vue'
import ReportPanel from './ReportPanel.vue'
import { useDragLayout } from '../composables/useDragSort'

/* 总览面板模块布局：顺序 + 折叠状态持久化到 localStorage（打开面板恢复上次状态）
 * v2：默认全部折叠（ISA-101 少即是多），不再继承 v1 持久化的展开状态 */
const ovLayoutKey = ref('insp-layout:overview:v2')
const layout = useDragLayout(
  ovLayoutKey,
  ['plant', 'strategy', 'top'],
  { plant: false, strategy: false, top: false },
)

/* 宽度拖拽手柄：将事件转发给 App.vue 处理（与左侧栏一致） */
const emit = defineEmits(['rsz'])
const rszDragging = ref(false)
function onRszStart(e) {
  rszDragging.value = true
  const cleanup = () => { rszDragging.value = false }
  window.addEventListener('mouseup', cleanup, { once: true })
  emit('rsz', e)
}

const store = useSimStore()
const materialList = MATERIALS

// 滚动条显隐：滚动时显示，停止滚动 2s 后自动隐藏
const scrolling = ref(false)
let scrollTimer = null
function onScroll() {
  scrolling.value = true
  clearTimeout(scrollTimer)
  scrollTimer = setTimeout(() => { scrolling.value = false }, 2000)
}

const mode = computed(() => store.inspectorMode)
const headTitle = computed(() => {
  if (mode.value === 'agent') return t('本析智擎')
  if (mode.value === 'report') return t('报告面板')
  if (mode.value === 'park') return t('园区构成')
  if (mode.value === 'materials') return t('物料库')
  if (mode.value === 'material') return t('物料属性')
  if (mode.value === 'strategyDetail') return t('策略属性')
  if (store.editMode) return t('编排属性')
  if (store.selectedGroupId) return t('小组属性')
  if (store.selectedFlowId) return t('工艺属性')
  if (mode.value === 'device') {
    const d = store.deviceDetail
    return (d && d.device && d.device.adjustable) ? t('可调设备') : t('计量设备')
  }
  return ({ overview: t('检视器 · 总览'), unit: t('工序属性') }[mode.value] || t('检视器'))
})

// ---------- 全厂总览：实时 / 日度 / 月度 / 年度 四档时段核算 ----------
// 统计口径（v2）：日/月/年 = 当日 / 当月 / 当年「0 点起截止当前」的真实累计量（墙钟自然周期，
// 与生产日报同口径）——速率 × 周期已过小时数，跨 0 点 / 月初 / 年初自动归零重计；
// realtime = 当前小时速率。成本 = 外购用量(后端 totals.purchases) × 物料单价(原料属性可调)。
const KGCE_PER_GJ = 34.12                  // 1 GJ = 34.12 kgce（与后端 factors 一致，强度兜底计算用）

const plantPeriods = [
  { id: 'realtime', label: '实时', hint: '实时：按当前小时速率展示（GJ/h · MWh/h · tCO₂/h）' },
  { id: 'day', label: '日度', hint: '日度：今日 0 点起累计（截至当前）' },
  { id: 'month', label: '月度', hint: '月度：本月 1 日 0 点起累计（截至当前）' },
  { id: 'year', label: '年度', hint: '年度：本年 1 月 1 日 0 点起累计（截至当前）' },
]
// 各档展示单位：h 级单位(实时) / 原始单位(日内累计) / 万级(月) / 万~亿级(年)
// rev 与 cost 同为金额口径：统一为万元（实时=万元/h · 日/月/年=万元）
const P_UNIT = {
  realtime: { energy: 'GJ/h', elec: 'MWh/h', co2: 'tCO₂/h', steel: 't/h', cost: '万元/h', rev: '万元/h' },
  day:      { energy: 'GJ', elec: 'MWh', co2: 'tCO₂', steel: 't', cost: '万元', rev: '万元' },
  month:    { energy: 'GJ', elec: 'MWh', co2: 'tCO₂', steel: 't', cost: '万元', rev: '万元' },
  year:     { energy: 'GJ', elec: 'MWh', co2: 'tCO₂', steel: 't', cost: '万元', rev: '万元' },
}

const plantPeriod = ref('realtime')

// 全厂实时核算：优先取 ws 遥测帧内与本次 tick 同步的 totals（后端 /api/ws/feed 已全量下发），
// 实时态不再混用静态基线（旧 bug：实时直接/间接/能耗停留在初始仿真值，与实时总量对不上）。
const totals = computed(() => {
  const fb = {
    co2_total: 0, co2_direct: 0, co2_indirect: 0, intensity: 0, steel_output: 0,
    carbon_utilization: 0, energy_total: 0, energy_intensity: 0, elec: 0, fuel_energy: 0,
    purchases: {},
  }
  const base = (store.resultForView && store.resultForView.totals) ? store.resultForView.totals : fb
  const live = store.live
  if (!live) return base
  const lt = live.totals || {}
  const pick = (k, alt) => (lt[k] != null ? lt[k] : alt)
  return {
    co2_total: pick('co2_total', live.total_co2 != null ? live.total_co2 : base.co2_total),
    co2_direct: pick('co2_direct', base.co2_direct),
    co2_indirect: pick('co2_indirect', base.co2_indirect),
    intensity: pick('intensity', live.intensity != null ? live.intensity : base.intensity),
    steel_output: pick('steel_output', live.steel_output != null ? live.steel_output : base.steel_output),
    carbon_utilization: pick('carbon_utilization', base.carbon_utilization),
    energy_total: pick('energy_total', base.energy_total),
    energy_intensity: pick('energy_intensity', base.energy_intensity),
    elec: pick('elec', base.elec),
    fuel_energy: pick('fuel_energy', base.fuel_energy),
    purchases: pick('purchases', base.purchases || {}),
  }
})
// 全厂综合能耗（节能减碳主题：先能后碳）。优先用后端 totals（实时帧已含），缺失时由工序能耗汇总反推。
const plantEnergy = computed(() => {
  const t = totals.value
  if (t && t.energy_total != null && t.energy_total > 0) {
    let intensity = t.energy_intensity
    if ((intensity == null || intensity <= 0) && (t.steel_output || 0) > 0) {
      intensity = (t.energy_total * KGCE_PER_GJ) / t.steel_output
    }
    return { total: t.energy_total, intensity: intensity || 0 }
  }
  const r = store.resultForView
  const units = (r && r.units) || []
  let total = 0
  for (const u of units) total += energyOf(u).total
  const steel = (t && t.steel_output) || 0
  return { total, intensity: steel > 0 ? (total * KGCE_PER_GJ) / steel : 0 }
})
// 全厂电耗：优先用后端 totals，缺失时由工序台账/碳素流反推汇总
const plantElec = computed(() => {
  const t = totals.value
  if (t && t.elec != null && t.elec > 0) return t.elec
  const r = store.resultForView
  const units = (r && r.units) || []
  let sum = 0
  for (const u of units) sum += energyOf(u).elec
  return sum
})

// ---------- 成本：外购用量(后端 totals.purchases) × 物料单价(原料属性可调，默认行业参考价) ----------
const priceOf = (id) => {
  const ov = store.materialOverrides && store.materialOverrides[id]
  if (ov && ov.price != null) return Number(ov.price)
  const m = MATERIAL_MAP[id]
  return (m && m.price != null) ? Number(m.price) : 0
}
const purchaseRate = computed(() => totals.value.purchases || {})
// 成本明细（小时速率）：仅列出有外购用量的物料，按金额降序
const costDetail = computed(() => {
  const rows = []
  for (const k in purchaseRate.value) {
    const qty = Number(purchaseRate.value[k]) || 0
    if (qty <= 0) continue
    const m = MATERIAL_MAP[k]
    rows.push({ id: k, name: m ? m.name : k, unit: (m && m.unit) ? m.unit : 't', color: m ? m.color : null, qty, price: priceOf(k) })
  }
  for (const r of rows) r.amt = r.qty * r.price
  rows.sort((a, b) => b.amt - a.amt)
  return rows
})
// 外购成本小时速率（万元/h；r.amt = 用量 × 单价（万元/单位））
const costRateRaw = computed(() => costDetail.value.reduce((s, r) => s + r.amt, 0))
// 成本构成明细展开开关
const costOpen = ref(false)

// ---------- 全国碳市场（CEA）：配额结余 + 预估碳成本（年度口径，跨档位展示） ----------
// CEA 核算口径 = 仅直接排放（范围一：燃料燃烧 + 工业过程）；范围二（外购电）的碳排已在发电侧由电力行业承担配额，钢铁企业不重复纳入。
const HOURS_YEAR = 8760
const emiOpen = ref(false)      // 总排放卡展开：计算方式（范围一+二全口径展示）与碳配额结余（CEA = 范围一）
const carbOpen = ref(false)     // 预估碳成本卡展开：计算明细（(n−m)×p，CEA 范围一）
const quotaDraft = ref('')
const priceDraft = ref('')
// 企业年配额 n（tCO₂/年，默认 2000 万 t）与实时碳价 p（万元/tCO₂，默认 0.01）——store 持久化，卡片/明细实时联动
const carbonQuota = computed(() => Number(store.carbonCfg.allowance) || 0)
const carbonPrice = computed(() => Number(store.carbonCfg.price) || 0)
watch(() => [store.carbonCfg.allowance, store.carbonCfg.price], ([a, p]) => {
  quotaDraft.value = a != null ? String(a) : ''
  priceDraft.value = p != null ? String(p) : ''
}, { immediate: true })
function onQuotaEdit() {
  const v = Number(quotaDraft.value)
  if (!Number.isFinite(v) || v < 0) { quotaDraft.value = String(carbonQuota.value); return }
  store.setCarbonCfg({ allowance: Math.round(v) })
}
function onPriceEdit() {
  const v = Number(priceDraft.value)
  if (!Number.isFinite(v) || v < 0) { priceDraft.value = String(carbonPrice.value); return }
  store.setCarbonCfg({ price: Math.round(v * 100) / 100 })
}
// CEA 控排速率 = 总排放速率 = 直接排放（范围一，tCO₂/h）——范围二（外购电）不计入企业排放
const co2DirectRate = computed(() => totals.value.co2_direct || 0)
// 到年底 CEA 排放 m：按当前直接排放速率 × 全年小时外推（预测值，非实际台账）
const carbM = computed(() => co2DirectRate.value * HOURS_YEAR)
// 本年 CEA 已累计排放（范围一）：优先取年度积分累计；积分未启动（首次渲染）时按当前速率 × 已过小时兜底
const carbYtd = computed(() => {
  const a = accum.year.v
  if (a && a.direct) return a.direct
  const dt = (Date.now() - periodStartAt('year')) / 3.6e6
  return co2DirectRate.value * Math.max(0, dt)
})
// 碳配额结余 = 企业年配额 − 本年 CEA 累计排放（可为负：超排）
const quotaRemain = computed(() => {
  const r = carbonQuota.value - carbYtd.value   // tCO₂
  const t2 = Math.abs(r)
  return r >= 0
    ? { text: `+${fmt(t2)} tCO₂`, cls: 'better' }
    : { text: `−${fmt(t2)} tCO₂（${t('超排')}）`, cls: 'worse' }
})
// Δ = n − m（n/m 均为 CEA 范围一）：负=超排缺口（购碳支出），正=配额盈余（可交易收益）
const carbDetail = computed(() => {
  const n = carbonQuota.value
  const m = carbM.value
  const p = carbonPrice.value
  const rate = co2DirectRate.value
  const d = n - m
  const rows = [
    { k: t('CEA 直接排放速率（范围一）'), v: `${fmt(rate)} tCO₂/h`, a: '', u: '', color: '#3f6f9d' },
    { k: t('到年底排放 m（按当前直接速率外推）'), v: `${fmt(m)} tCO₂`, a: '', u: '', color: '#b4692f' },
    { k: t('企业年配额 n'), v: `${fmt(n)} tCO₂`, a: '', u: '', color: '#3f9d6b' },
  ]
  rows.push(d < 0
    ? { k: t('超排缺口 (n−m)'), v: `${fmt(-d)} tCO₂`, a: '', u: '', color: '#c0574a' }
    : { k: t('配额盈余 (n−m)'), v: `${fmt(d)} tCO₂`, a: '', u: '', color: '#c9a33e' })
  rows.push({ k: t('实时碳价 p'), v: `${fmt(p)} 万元/tCO₂`, a: '', u: '', color: '#7a5fa8' })
  const amt = (d * p) / 1e4   // 万元（负=支出）
  rows.push({
    k: t('预估碳成本 (n−m)×p'),
    v: d < 0 ? t('超排需购碳履约') : d > 0 ? t('配额盈余可交易') : t('刚好持平'),
    a: fmt(Math.abs(amt)),
    u: d < 0 ? t('万元（支出）') : d > 0 ? t('万元（潜在收益）') : '万元',
    cls: d < 0 ? 'worse' : d > 0 ? 'better' : 'flat',
    color: '#2f6fb0',
  })
  return rows
})
// 卡片摘要：支出为正（红），配额盈余按负成本（绿）显示
const carbEst = computed(() => {
  const d = carbonQuota.value - carbM.value
  const amt = (d * carbonPrice.value) / 1e4
  if (!Number.isFinite(amt)) return { text: '—', cls: 'flat' }
  if (d === 0) return { text: '0', cls: 'flat' }
  return d < 0 ? { text: fmt(-amt), cls: 'worse' } : { text: '-' + fmt(amt), cls: 'better' }
})

// 同比/环比仅于日度/月度档展示（其余档位无同口径基期）
const isCmpPeriod = computed(() => plantPeriod.value === 'day' || plantPeriod.value === 'month')

// ---------- 产品收益：产量 × 主产品销售单价（终端产品售价见「物料属性 → 销售单价」，行业参考价可调） ----------
const revOpen = ref(false)                                  // 产品收益卡展开开关
// 「产品」组可见性：仅当当前编排中存在「输出端口物料属于物料库产品（PRODUCTS）」的工艺节点时展示。
// 资源包场景（机房温控等：产物为冷冻供水/冷风等非产品物料）自动隐藏该组与产品收益卡。
const PRODUCT_ID_SET = new Set((PRODUCTS || []).map((p) => p && p.id))
const hasProduct = computed(() => {
  const nodes = (store.scheme && store.scheme.nodes) || []
  for (const n of nodes) {
    if (!n || (n.kind && n.kind !== 'process')) continue
    const outs = (n.ports && n.ports.out) || []
    for (const p of outs) {
      const mid = typeof p === 'string' ? p : (p && p.material)
      if (mid && PRODUCT_ID_SET.has(mid)) return true
    }
  }
  return false
})
watch(hasProduct, (v) => { if (!v) revOpen.value = false })   // 无产品产出时收起收益明细
const revMainId = ref(localStorage.getItem('sim.revMain') || 'auto')
watch(revMainId, (v) => { try { localStorage.setItem('sim.revMain', v || 'auto') } catch (e) { /* 忽略 */ } })
// 产线终端工序自动匹配主产品：冷轧/热轧 → 钢材 · 连铸/模铸 → 连铸坯 · 仅炼钢/精炼 → 精炼钢水
function mainProductAuto() {
  const r = store.resultForView
  const types = new Set(((r && r.units) || []).map((u) => u.type))
  if (types.has('cold_rolling') || types.has('rolling_mill')) return 'steel_product'
  if (types.has('caster') || types.has('ingot_casting')) return 'billet'
  return 'refined_steel'
}
const revMainIdEff = computed(() => (revMainId.value && revMainId.value !== 'auto' ? revMainId.value : mainProductAuto()))
const revMainMat = computed(() => MATERIAL_MAP[revMainIdEff.value] || PRODUCTS[0])
function revPriceOf(id) {
  const ov = store.materialOverrides && store.materialOverrides[id]
  if (ov && ov.salePrice != null) return Number(ov.salePrice)
  const m = MATERIAL_MAP[id]
  if (m && m.salePrice != null) return Number(m.salePrice)
  return (m && m.price != null) ? Number(m.price) : 0
}
const revSalePrice = computed(() => revPriceOf(revMainIdEff.value))   // 万元/t
const revQtyRate = computed(() => totals.value.steel_output || 0)     // t/h（当前速率）
const revRateRaw = computed(() => revQtyRate.value * revSalePrice.value) // 万元/h（钢产量 t/h × 销售单价 万元/t）
const revRateVal = computed(() => revRateRaw.value)                   // 万元/h（速率口径展示）
// 收益随所选档位累计（金额口径统一为万元：实时=万元/h · 日/月/年=万元；累计量由收益速率连续积分得到，已为万元单位不再缩放）
const periodRev = computed(() => {
  const p = plantPeriod.value
  if (p === 'realtime') return revRateRaw.value
  const v = accum[p].v
  if (!v || v.rev == null) return 0
  return v.rev
})

// ---------- 综合能耗展开：燃料能耗 + 电力折标（速率口径 · 计算方式展示） ----------
const energyOpen = ref(false)                               // 综合能耗卡展开开关
const eneFuelRate = computed(() => totals.value.fuel_energy || 0)   // GJ/h 燃料（低位热值合计）
const eneElecRate = computed(() => plantElec.value || 0)            // MWh/h 外购电
const eneElecGJ = computed(() => eneElecRate.value * 3.6)           // 1 MWh = 3.6 GJ 电力折标
const eneTotalRate = computed(() => plantEnergy.value.total || 0)   // GJ/h 综合能耗合计

// ---------- 总排放展开构成（速率口径，总排放 = 范围一直接排放）与碳素利用 ----------
const emiDirectRate = computed(() => totals.value.co2_direct || 0)
const emiIndirectRate = computed(() => totals.value.co2_indirect || 0)   // 外购电（范围二，发电侧口径，仅参考展示）
const carbonUtilPct = computed(() => ((totals.value.carbon_utilization || 0) * 100).toFixed(1))

// ---------- 周期累计 = 速率对时间的连续积分 ----------
// 速率随运行工况/遥测实时变化，「当前速率 × 已过小时」会把全程当成一个速率而失真，
// 故按时间段积分：每 30s 或速率变化时，先把上一时间段的量按该段速率结清再切换当前速率；跨日/月/年自动归零重计。
const PERIOD_KINDS = ['day', 'month', 'year']
const ACC_KEYS = ['energy', 'elec', 'co2', 'direct', 'indirect', 'steel', 'cost', 'rev']
function mkAcc() { return { v: null, t: 0, last: null } }
const accum = reactive({ day: mkAcc(), month: mkAcc(), year: mkAcc() })
function periodStartAt(kind) {
  const n = new Date()
  return kind === 'day' ? new Date(n.getFullYear(), n.getMonth(), n.getDate()).getTime()
    : kind === 'month' ? new Date(n.getFullYear(), n.getMonth(), 1).getTime()
    : new Date(n.getFullYear(), 0, 1).getTime()
}
function rateSnap() {
  const t = totals.value
  return {
    energy: plantEnergy.value.total || 0,   // GJ/h
    elec: plantElec.value || 0,             // MWh/h
    co2: t.co2_total || 0,                  // tCO₂/h（范围一+二）
    direct: t.co2_direct || 0,              // tCO₂/h（范围一，CEA）
    indirect: t.co2_indirect || 0,          // tCO₂/h（范围二）
    steel: t.steel_output || 0,             // t/h
    cost: costRateRaw.value || 0,           // 万元/h
    rev: revRateRaw.value || 0,             // 万元/h
  }
}
// 把「截至 now」的流量积分入当日/当月/当年累计：新段以该段开始时的速率近似（30s 粒度 + 速率变化即结清）。
// 首次开账/跨周期时，从周期起点按当前速率整段补记——因此页面前端数据未到（速率为 0）时不建账，
// 等真实运行速率出现再一次性把「周期开始 → now」补入，避免整日/整月累计缺失。
function settleAccum(now) {
  const cur = rateSnap()
  for (const kind of PERIOD_KINDS) {
    const a = accum[kind]
    const st = periodStartAt(kind)
    const needOpen = !a.v || a.t < st || !a.last
    if (needOpen) {
      if (a.t < st && a.v) {                     // 跨周期：先把旧账清零，防残留
        for (const k of ACC_KEYS) a.v[k] = 0
        a.t = st
      }
      const tot = ACC_KEYS.reduce((s, k) => s + (cur[k] || 0), 0)
      if (tot <= 0) { a.t = st; a.last = cur; continue }   // 尚无实际运行速率：不建账，起点钉在周期开始，待真实速率出现后整段补记
      if (!a.v) { const v = {}; for (const k of ACC_KEYS) v[k] = 0; a.v = v }
      const dt0 = (now - Math.max(st, a.t)) / 3.6e6
      if (dt0 > 0) for (const k of ACC_KEYS) a.v[k] += (cur[k] || 0) * dt0
      a.t = now
      a.last = cur
      continue
    }
    const dt = (now - a.t) / 3.6e6
    if (dt > 0) {
      for (const k of ACC_KEYS) a.v[k] += (a.last[k] || 0) * dt
    }
    a.t = now
    a.last = cur
  }
}
// 速率变化（调参/遥测更新）先结清上一段；时间流逝由 30s tick 结算推进
watch(totals, () => settleAccum(Date.now()), { deep: true })
let _accTimer = null
onMounted(() => {
  settleAccum(Date.now())
  _accTimer = setInterval(() => settleAccum(Date.now()), 30000)
})
onBeforeUnmount(() => { if (_accTimer) clearInterval(_accTimer) })
settleAccum(Date.now())  // setup 阶段先结算一次，首帧即有累计值

// 当前档位核算：realtime = 实时速率；day/month/year = 当日/当月/当年 0 点起按实时速率连续积分的累计量
const period = computed(() => {
  const p = plantPeriod.value
  const t = totals.value
  const energy = plantEnergy.value.total || 0   // GJ/h
  const elec = plantElec.value || 0             // MWh/h
  const co2 = t.co2_total || 0
  const direct = t.co2_direct || 0
  const indirect = t.co2_indirect || 0
  const steel = t.steel_output || 0
  const costRate = costRateRaw.value            // 万元/h
  // 日/月/年累计量取消万/亿级跳变，直接以 GJ / MWh / tCO₂ / t / 万元 原始单位展示（累计量由速率连续积分得到，单位已对应）
  if (p === 'realtime') {
    return { energy, elec, co2, direct, indirect, steel, cost: costRate, rev: periodRev.value, u: P_UNIT.realtime }
  }
  const a = accum[p]
  const v = (a && a.v) || {}
  const cv = (k) => v[k] || 0
  return {
    energy: cv('energy'), elec: cv('elec'), co2: cv('co2'),
    direct: cv('direct'), indirect: cv('indirect'), steel: cv('steel'),
    cost: cv('cost'), rev: periodRev.value, u: P_UNIT[p] || P_UNIT.day,
  }
})
const periodDesc = computed(() => {
  const p = plantPeriod.value
  if (p === 'realtime') return t('口径：当前小时速率 · 综合能耗 GJ/h · 电耗 MWh/h · 总排放 tCO₂/h · 产量 t/h')
  const n = new Date()
  const pad = (x) => String(x).padStart(2, '0')
  const dayMark = `${n.getMonth() + 1}月${n.getDate()}日 ${pad(n.getHours())}:${pad(n.getMinutes())}`
  if (p === 'day') return t('累计口径：今日 0 点起至 ') + dayMark + t('（按实时速率连续积分 · 跨日自动归零）')
  if (p === 'month') return t('累计口径：本月 1 日 0 点起至 ') + dayMark + t('（按实时速率连续积分 · 跨月自动归零）')
  return t('累计口径：本年 1 月 1 日 0 点起至 ') + dayMark + t('（按实时速率连续积分）')
})

// ---------- 同比 / 环比（日度 / 月度档） ----------
// 无真实历史台账时不填数（不造假）：卡片保留、值显示「—」；接入日/月报历史后在此启用真实对比。
const cmp = computed(() => {
  if (plantPeriod.value !== 'day' && plantPeriod.value !== 'month') return null
  return { yoy: null, mom: null }
})
function signedPct(v) {
  if (v == null) return '—'
  const s = v >= 0 ? '+' : ''
  return `${s}${(v * 100).toFixed(1)}%`
}
function dirCls(v) {
  if (v == null) return 'flat'
  if (v > 0.0005) return 'worse'    // 能耗上升 → 警示色
  if (v < -0.0005) return 'better'  // 能耗下降 → 向好色
  return 'flat'
}
// 策略节能减碳效果（基线 vs 策略）：节能与减碳并重
const stratCmp = computed(() => {
  const b = store.baseline && store.baseline.totals
  const s = store.strategy && store.strategy.totals
  if (!b || !s) return { energyRed: 0, energyPct: '—', co2Red: 0, co2Pct: '—' }
  const er = (b.energy_total || 0) - (s.energy_total || 0)
  const cr = (b.co2_total || 0) - (s.co2_total || 0)
  return {
    energyRed: er,
    energyPct: b.energy_total ? (er / b.energy_total * 100).toFixed(1) : '—',
    co2Red: cr,
    co2Pct: b.co2_total ? (cr / b.co2_total * 100).toFixed(1) : '—',
  }
})

const co2Color = computed(() => {
  const v = totals.value.intensity
  if (v > 1200) return 'var(--red)'
  if (v > 600) return 'var(--yellow)'
  return 'var(--green)'
})
const topEmitters = computed(() => {
  const r = store.resultForView
  if (!r || !r.units) return []
  const total = r.units.reduce((s, u) => s + (u.co2_direct || 0), 0) || 1
  return [...r.units]
    .sort((a, b) => b.co2_direct - a.co2_direct)
    .slice(0, 4)
    .map((u) => ({ ...u, share: (u.co2_direct || 0) / total }))
})

function shareColor(p) {
  const stops = [[61, 110, 140], [201, 162, 59], [192, 86, 76]]
  const t = Math.max(0, Math.min(1, (p || 0) / 0.25))
  let c
  if (t < 0.5) c = stops[0].map((v, i) => Math.round(v + (stops[1][i] - v) * (t / 0.5)))
  else c = stops[1].map((v, i) => Math.round(v + (stops[2][i] - v) * ((t - 0.5) / 0.5)))
  return `rgb(${c[0]},${c[1]},${c[2]})`
}
function typeLabel(t) { return (UNIT_TYPES.find((x) => x.type === t) || {}).label || t }
function fmt(n) {
  if (n == null || !Number.isFinite(Number(n))) return '—'
  const v = Number(n)
  const abs = Math.abs(v)
  const d = abs >= 1e5 ? 0 : abs >= 100 ? 1 : abs >= 1 ? 2 : 3
  return v.toLocaleString('zh-CN', { maximumFractionDigits: d })
}
</script>

<style scoped>
/* .x-btn / .scope* / .park-sum 已统一定义于全局 main.css，此处不再重复 */
/* 本析智擎对话界面 absolute 铺满面板（覆盖 padding，视觉通栏） */
.inspector-body { position: relative; }
/* 总览指标卡：统一中性底色（与全局面板一致），不再按能耗/碳排区分彩色底，避免视觉杂乱；
 * 语义色仅保留在数值上（co2Color 强度警示），卡片本身一色到底 */
.te-row { align-items: flex-start; padding-top: 9px; padding-bottom: 9px; }
/* 全厂总览：实时 / 日度 / 月度 / 年度 时段切换（紧凑分段条，激活金底墨字） */
.plant-tabs {
  display: flex; gap: 2px; margin: 0 0 7px; padding: 2px;
  background: var(--panel-2); border: 1px solid var(--line); border-radius: 4px;
}
.plant-tab {
  flex: 1; min-width: 0; height: 22px; padding: 0 2px;
  border: none; background: transparent; border-radius: 3px;
  color: var(--muted); font-size: 10px; cursor: pointer;
  white-space: nowrap; transition: background .12s, color .12s;
}
.plant-tab:hover { background: var(--panel-3); color: var(--text); }
.plant-tab.on { background: var(--accent); color: var(--on-accent); font-weight: 600; }
.plant-note { font-size: 9px; line-height: 1.5; color: var(--muted); margin: 0 0 6px; }
/* 同比 / 环比 对比行（日度 / 月度档） */
.cmp-row { display: grid; grid-template-columns: 1fr 1fr; gap: 4px; margin-top: 8px; }
.cmp-row .chip2 b { font-size: 12px; font-weight: 500; }
.chip2 b.better { color: var(--green); }
.chip2 b.worse { color: var(--red); }
.chip2 b.flat { color: var(--muted); }
.plant-foot { margin-top: 6px; font-size: 9px; line-height: 1.5; color: var(--muted); }
/* 成本卡（可点击展开构成明细） */
.chip2.tog { cursor: pointer; transition: border-color .15s, background .15s; }
.chip2.tog:hover { border-color: var(--accent); }
.chip2.tog.open { border-color: var(--accent); background: var(--accent-l, rgba(95,130,148,.08)); }
.chip2.tog .caret { font-style: normal; font-size: 8px; margin-left: 2px; }
.cost-detail { margin-top: 6px; border: 1px solid var(--line); border-radius: 4px; background: var(--panel-2, rgba(0,0,0,.02)); padding: 5px 7px; }
.cd-head { font-size: 9.5px; color: var(--accent2); margin-bottom: 4px; line-height: 1.5; }
.cd-row { display: flex; align-items: baseline; gap: 6px; padding: 3px 0; font-size: 10px; }
.cd-row + .cd-row { border-top: 1px dashed var(--line); }
.cd-name { flex: 0 0 auto; font-size: 9.5px; color: #fff; border-radius: 3px; padding: 1px 5px; }
.cd-qty { flex: 1; min-width: 0; color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cd-amt { flex: 0 0 auto; text-align: right; font-variant-numeric: tabular-nums; }
.cd-amt b { font-weight: 600; }
.cd-amt i, .cd-qty i { font-style: normal; color: var(--muted); }
.cd-empty { justify-content: center; color: var(--muted); border-top: none !important; }
.cd-note { margin-top: 4px; font-size: 9px; line-height: 1.5; color: var(--muted); border-top: 1px dashed var(--line); padding-top: 4px; }
/* 总排放展开：全国碳市场核算方法（多行公式说明） */
.emi-detail .meth-line { font-size: 9.5px; line-height: 1.6; color: var(--text); padding: 2px 0; }
.quota-bar {
  display: flex; align-items: baseline; justify-content: space-between; gap: 8px;
  margin-top: 6px; padding: 5px 8px; background: var(--panel-2);
  border: 1px solid var(--line); border-radius: 4px;
}
.quota-bar .qk { font-size: 10px; color: var(--muted); }
.quota-bar b { font-size: 12px; }
/* 产品 / 能源 / 碳排 分组小标题 */
.sec { display: flex; align-items: center; gap: 5px; margin: 7px 0 3px; font-size: 9px; color: var(--muted); letter-spacing: .5px; }
.sec .dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.sec .d-prod { background: #3f9d6b; }
.sec .d-ene { background: #c9a33e; }
.sec .d-co2 { background: #c0574a; }
/* 展开区计算式行：序号标签 + 右对齐实测值（与能耗/排放展开共用） */
.meth-line { display: flex; align-items: baseline; gap: 6px; font-size: 9.5px; line-height: 1.6; color: var(--text); padding: 2px 0; }
.meth-line .ml { flex: 1; min-width: 0; }
.meth-line .mval { font-style: normal; color: var(--muted); font-variant-numeric: tabular-nums; white-space: nowrap; }
.meth-line.sub { font-size: 9px; color: var(--muted); border-top: 1px dashed var(--line); margin-top: 4px; padding-top: 4px; }
.rev-sel { width: 100%; height: 20px; }
/* 预估碳成本展开：配额/碳价维护输入 */
.carb-edit { display: flex; gap: 12px; flex-wrap: wrap; padding: 6px 0 4px; }
.carb-edit label { display: flex; align-items: center; gap: 5px; font-size: 10px; color: var(--muted); }
.q-in {
  width: 110px; height: 20px; padding: 0 6px; font-size: 11px;
  border: 1px solid var(--line); border-radius: 3px;
  background: var(--input-bg, #fff); color: var(--text);
}
.q-in:focus { outline: none; border-color: var(--accent); }
.carb-detail .cd-row b.worse { color: var(--red); font-weight: 700; }
.carb-detail .cd-row b.better { color: var(--green); font-weight: 700; }
.app.sim-dark .chip2.tog.open { background: rgba(95,130,148,.15); }
/* 直接/间接 图例：百分占比小注与色点间距 */
.scope-legend em { font-style: normal; color: var(--muted); }
.scope-legend .dot { margin-left: 0; }
.app.sim-dark .plant-tab:hover { background: #2A2E2A; color: #E2E0DA; }
.app.sim-dark .plant-tab.on { background: var(--accent); color: var(--on-accent); }
.te-bar { display: block; height: 4px; border-radius: 2px; background: var(--panel-2); overflow: hidden; margin-top: 5px; }
.te-bar > i { display: block; height: 100%; border-radius: 2px; }
.te-pct { flex: 0 0 44px; text-align: right; color: var(--muted); font-size: 10px; font-variant-numeric: tabular-nums; }
.strat-cmp { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; padding: 6px 0; }
.sc-item {
  border: 1px solid var(--line); border-radius: 4px; padding: 6px 8px;
  display: flex; flex-direction: column; gap: 2px; background: var(--panel-2, rgba(0,0,0,.03));
}
.sc-item span { font-size: 10px; color: var(--muted); }
.sc-item b { font-size: 16px; font-variant-numeric: tabular-nums; }
.sc-item b.good { color: var(--green, #2E8B57); }
.sc-item i { font-style: normal; font-size: 10px; color: var(--muted); }
</style>
