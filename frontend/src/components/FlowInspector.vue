<template>
  <div class="flow-insp">
    <!-- 工艺设备小组属性（优先于节点/总览） -->
    <template v-if="group">
      <CollapseSection :title="t('工艺设备小组')" tone="blue">
        <div class="card">
          <div class="kv2"><span>{{ t('名称') }}</span><input class="gname-in" :value="group.name" @input="store.renameFlowGroup(group.id, $event.target.value)" /></div>
          <div class="kv2"><span>{{ t('成员设备') }}</span><b>{{ group.members.length }} {{ t('台') }}</b></div>
        </div>
      </CollapseSection>

      <CollapseSection :title="t('成员设备（点击查看/编辑）')" tone="teal" :show-more="false">
        <div v-for="m in groupMembers" :key="m.id" class="lrow click" :class="{active: m.id===store.selectedFlowId}" @click="store.selectFlow(m.id)">
          <div class="l-stack">
            <span class="l-tt">{{ m.name }}</span>
            <span class="l-sub">{{ nodeSub(m) }}</span>
          </div>
          <span v-if="m.kind === 'process' && estOf(m.id)" class="l-trail">{{ fmt(estOf(m.id).co2) }} <span class="u">tCO₂/h</span></span>
          <button class="x-btn danger" :title="t('移出小组')" @click.stop="store.removeNodeFromGroup(m.id)">✕</button>
        </div>
        <div v-if="!groupMembers.length" class="empty">{{ t('该小组暂无成员。双击小组卡片进入子编排，从左侧拖入设备即可归入本组。') }}</div>
      </CollapseSection>

      <CollapseSection :title="t('对外输入 / 输出设定')" tone="green" :show-more="false">
      <div class="card">
        <div class="ports-col">
          <span class="pc-t">{{ t('输入（来自上游）') }}</span>
          <div v-for="(io, i) in group.inputs" :key="'gi' + i" class="gio-row">
            <select :value="io.material" @change="setGroupIo(group.id, 'inputs', i, $event.target.value)">
              <option v-for="m in MATERIALS" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
            <button class="x-btn danger" :title="t('移除')" @click="delGroupIo(group.id, 'inputs', i)">✕</button>
          </div>
          <button class="add" @click="addGroupIo(group.id, 'inputs')">＋ {{ t('输入项') }}</button>
        </div>
        <div class="ports-col">
          <span class="pc-t">{{ t('输出（到下游 / 成品）') }}</span>
          <div v-for="(io, i) in group.outputs" :key="'go' + i" class="gio-row">
            <select :value="io.material" @change="setGroupIo(group.id, 'outputs', i, $event.target.value)">
              <option v-for="m in MATERIALS" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
            <button class="x-btn danger" :title="t('移除')" @click="delGroupIo(group.id, 'outputs', i)">✕</button>
          </div>
          <button class="add" @click="addGroupIo(group.id, 'outputs')">＋ {{ t('输出项') }}</button>
        </div>
        <div class="pr-hint">{{ t('小组对外输入/输出用于外部画布连线（如热风炉+鼓风机小组对外输出热风）。双击成员卡片可修改其端口物料。') }}</div>
      </div>
      </CollapseSection>

      <button v-if="store.editMode" class="del-node" @click="store.removeFlowGroup(group.id)">{{ t('删除该小组') }}</button>
    </template>

    <!-- 未选中：方案总览 -->
    <template v-else-if="!node">
      <CollapseSection :title="t('编排方案总览')" tone="blue" :show-more="false">
      <div class="chips">
        <div class="chip2"><span>{{ t('总排放') }}</span><b>{{ fmt(totals.co2_total) }}</b><i>tCO₂/h</i></div>
        <div class="chip2"><span>{{ t('吨钢强度') }}</span><b>{{ fmt(totals.intensity) }}</b><i>kg/t</i></div>
        <div class="chip2"><span>{{ t('直接排放') }}</span><b>{{ fmt(totals.co2_direct) }}</b><i>tCO₂/h</i></div>
        <div class="chip2"><span>{{ t('间接排放') }}</span><b>{{ fmt(totals.co2_indirect) }}</b><i>tCO₂/h</i></div>
        <div class="chip2"><span>{{ t('钢产量') }}</span><b>{{ fmt(totals.steel_output) }}</b><i>t/h</i></div>
        <div class="chip2"><span>{{ t('CCUS（碳捕集利用与封存）捕集') }}</span><b>{{ fmt(totals.captured) }}</b><i>tCO₂/h</i></div>
      </div>
      </CollapseSection>

      <CollapseSection :title="t('工艺设备小组（双击进入子编排）')" tone="teal" :show-more="false">
      <div v-for="g in store.scheme.groups" :key="g.id" class="lrow click" :class="{active: g.id===store.selectedGroupId}" @click="store.selectFlowGroup(g.id)" @dblclick="store.enterGroup(g.id)">
        <div class="l-stack">
          <span class="l-tt">▦ {{ g.name }}</span>
          <span class="l-sub">{{ g.members.length }} {{ t('台设备') }}</span>
        </div>
        <span class="l-trail">{{ gOutText(g) }}</span>
      </div>
      <div v-if="!store.scheme.groups.length" class="muted-note">{{ t('尚未创建小组。点击工具条「编排 → 新建小组」，或将设备组合（如鼓风机 + 热风炉）成组。') }}</div>
      </CollapseSection>

      <CollapseSection :title="t('节点清单（点击查看/编辑）')" tone="amber" :show-more="false">
      <div v-for="n in store.scheme.nodes" :key="n.id" class="lrow click" :class="{active: n.id===store.selectedFlowId}" @click="store.selectFlow(n.id)">
        <div class="l-stack">
          <span class="l-tt">{{ n.name }}</span>
          <span class="l-sub">{{ nodeSub(n) }}</span>
        </div>
        <span class="l-trail" v-if="estOf(n.id) && n.kind === 'process'">{{ fmt(estOf(n.id).co2) }} <span class="u">tCO₂/h</span></span>
      </div>
      <div v-if="!store.scheme.nodes.length" class="empty">{{ t('画布为空，请从左侧拖入节点或载入模板。') }}</div>
      </CollapseSection>
    </template>

    <!-- 工艺节点 -->
    <template v-else-if="node.kind === 'process'">
      <!-- 从主工艺跳转而来：面板左上角返回按钮，回到来源工艺（不改变 3D 聚焦） -->
      <div v-if="store.flowBackId" class="flow-back-bar" @click="store.backFlow()" :title="t('返回跳转前的主工艺面板')">
        <span class="fb-arrow">←</span>
        <span class="fb-txt">{{ t('返回') }} {{ backFlowName }}</span>
      </div>
      <!-- ===== 1. 介绍 ===== -->
      <CollapseSection :title="t('工序 · ') + (tpl ? tpl.label : '')" tone="blue">
        <template #actions>
          <span v-if="sameTypeNodes.length > 1" class="inst-switch">
            <button class="inst-btn" :title="t('上一实例')" @click="switchInstance(-1)">‹</button>
            <span class="inst-idx">{{ typeIndex + 1 }}/{{ sameTypeNodes.length }}</span>
            <button class="inst-btn" :title="t('下一实例')" @click="switchInstance(1)">›</button>
          </span>
        </template>
      <div class="card">
        <div class="kv2"><span>{{ t('名称') }}</span><b>{{ node.name }}</b></div>
        <div class="kv2"><span>{{ t('类型') }}</span><b>{{ routeLabel }}</b></div>
        <div class="kv2"><span>{{ t('主产物') }}</span><b>{{ matName(tpl.mainOut) }}</b></div>
        <div class="kv2" v-if="specOptions.length">
          <span>{{ t('设备规格') }}</span>
          <select class="spec-sel" :value="node.spec || ''" @change="store.setFlowSpec(node.id, $event.target.value)">
            <option value="">{{ t('平台默认（标准）') }}</option>
            <option v-for="s in specOptions" :key="s.key" :value="s.key">{{ s.label }}</option>
          </select>
        </div>
        <div class="kv2" v-if="tpl.route === 'aux'">
          <span>{{ t('数量（台）') }}</span>
          <input type="number" min="1" max="9" step="1" class="spec-sel" :value="node.count || 1"
                 @change="store.setFlowCount(node.id, $event.target.value)" :title="t('大于 1 时自动形成小组（黄色描边）')" />
        </div>
        <div class="pr-hint" v-if="tpl.route === 'aux'">{{ t('台数大于 1 时自动形成小组，在编排卡片中以黄色描边表示。') }}</div>
        <div class="pr-hint" v-if="currentSpec">{{ currentSpec.desc }}</div>
      </div>
      </CollapseSection>

      <!-- ===== 2. 输入 / 输出设定（输入位置直接设置配比） ===== -->
      <CollapseSection :title="t('输入 / 输出设定')" tone="green" :show-more="false">
      <div class="card">
        <div class="ports-col">
          <span class="pc-t">{{ t('输入（来自上游 · 配比）') }}</span>
          <div v-for="(p, i) in node.ports.in" :key="p.id" class="gio-row">
            <select :value="p.material" @change="setNodePortMat('in', i, $event.target.value)">
              <option v-for="m in MATERIALS" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
            <input type="number" step="0.1" min="0" class="ratio-in"
                   :value="recipeRatioOf(p.material) != null ? recipeRatioOf(p.material) : ''"
                   placeholder="1" :title="t('输入配比（1 = 100%）')"
                   @input="setRecipeRatioForMaterial(p.material, $event.target.value)" />
            <button class="x-btn danger" :title="t('移除')" @click="delNodePort('in', i)">✕</button>
          </div>
          <button class="add" @click="addNodePort('in')">＋ {{ t('输入项') }}</button>
        </div>
        <div class="ports-col">
          <span class="pc-t">{{ t('输出（到下游 / 成品）') }}</span>
          <div v-for="(p, i) in node.ports.out" :key="p.id" class="gio-row">
            <select :value="p.material" @change="setNodePortMat('out', i, $event.target.value)">
              <option v-for="m in MATERIALS" :key="m.id" :value="m.id">{{ m.name }}</option>
            </select>
            <button class="x-btn danger" :title="t('移除')" @click="delNodePort('out', i)">✕</button>
          </div>
          <button class="add" @click="addNodePort('out')">＋ {{ t('输出项') }}</button>
        </div>
        <div class="pr-hint">{{ t('输入配比（1 = 100%）用于工艺输入物料构成与优化（如提高球团比降焦比）；每个输入/输出端口可连接多个节点，同一种类只能出现一次。') }}</div>
      </div>
      </CollapseSection>

      <CollapseSection :title="t('工艺参数设定')" tone="amber" :show-more="false">
      <div class="card">
        <!-- 该工艺本身的固定参数设定：面板直接录值（非监测值、非运行可调项、非自动计算指标） -->
        <div v-for="p in directParams" :key="p.key" class="param-row">
          <div class="pr-top">
            <span>{{ p.label }}</span>
            <span class="pr-val-wrap"><b>{{ node.params[p.key] ?? p.def }} <span class="u">{{ p.unit }}</span></b></span>
          </div>
          <input type="number" :min="p.min" :max="p.max" :step="p.step" :value="node.params[p.key] ?? p.def" class="num"
                 @input="store.setFlowParam(node.id, p.key, $event.target.value)" />
          <div class="pr-hint pr-range-row">
            <span>{{ t('范围') }}</span>
            <input type="number" class="rg-in" :value="p.min" :title="t('下限')"
                   @input="store.setFlowParamRange(node.id, p.key, { min: $event.target.value })" />
            <span class="rg-dash">–</span>
            <input type="number" class="rg-in" :value="p.max" :title="t('上限')"
                   @input="store.setFlowParamRange(node.id, p.key, { max: $event.target.value })" />
            <span class="rg-unit">{{ p.unit }}</span>
            <input type="number" class="rg-in rg-step" :value="p.step" :title="t('步长')"
                   @input="store.setFlowParamRange(node.id, p.key, { step: $event.target.value })" />
            <button v-if="hasNodeRange(p.key)" class="rg-reset" :title="t('恢复默认范围')" @click="store.resetFlowParamRange(node.id, p.key)">↺</button>
          </div>
        </div>
        <div v-if="!directParams.length" class="pr-hint">{{ t('该工艺无直接录入的参数设定。') }}</div>
      </div>
      </CollapseSection>

      <!-- ===== 炉渣二元碱度 R₂（仅高炉节点）：CaO/SiO₂ 全来源平衡 ===== -->
      <CollapseSection v-if="node.type === 'blast_furnace' && slagInfo" :title="t('炉渣碱度（CaO/SiO₂/MgO/Al₂O₃）')" tone="green" :show-more="false">
      <div class="card">
      <div class="kv2 slag-r2-row">
        <span>{{ t('二元碱度 R₂（CaO/SiO₂）') }}</span>
        <b class="slag-r2-val">{{ slagInfo.r2.toFixed(2) }}
          <span class="slag-tag" :class="slagInfo.level.cls">{{ slagInfo.level.txt }}</span>
        </b>
      </div>
      <div class="kv2 slag-r2-row">
        <span>{{ t('三元碱度 R₃（(CaO+MgO)/SiO₂）') }}</span>
        <b class="slag-r2-val">{{ slagInfo.r3.toFixed(2) }}
          <span class="slag-tag" :class="slagInfo.r3Level.cls">{{ slagInfo.r3Level.txt }}</span>
        </b>
      </div>
      <div class="kv2"><span>{{ t('适宜区间') }}</span><b>R₂ 1.15–1.25 · R₃ 1.40–1.55{{ t('（参考）') }}</b></div>
      <div class="kv2"><span>{{ t('燃料量（有效）') }}</span><b>{{ t('焦') }} {{ slagInfo.coke.toFixed(0) }} + {{ t('煤') }} {{ slagInfo.coal.toFixed(0) }} <span class="u">kg/t{{ t('（含富氧置换联动）') }}</span></b></div>
      <div class="slag-tbl-t">{{ t('入渣氧化物平衡') }}（kg/tFe）</div>
      <div class="slag-tbl">
        <div class="slag-tr slag-th"><span>{{ t('来源') }}</span><span>{{ t('用量') }}</span><span>CaO</span><span>SiO₂</span><span>MgO</span><span>Al₂O₃</span></div>
        <div class="slag-tr" v-for="pt in slagInfo.parts" :key="pt.name">
          <span>{{ pt.name }}</span><span>{{ pt.rate.toFixed(0) }}</span>
          <span>{{ pt.cao.toFixed(1) }}</span><span>{{ pt.sio2.toFixed(1) }}</span>
          <span>{{ pt.mgo.toFixed(1) }}</span><span>{{ pt.al2o3.toFixed(1) }}</span>
        </div>
        <div class="slag-tr slag-sum"><span>{{ t('合计') }}</span><span></span>
          <span>{{ slagInfo.caoTotal.toFixed(1) }}</span><span>{{ slagInfo.sio2Gross.toFixed(1) }}</span>
          <span>{{ slagInfo.mgoTotal.toFixed(1) }}</span><span>{{ slagInfo.al2o3Total.toFixed(1) }}</span>
        </div>
        <div class="slag-tr"><span>{{ t('Si 还原入铁扣减（[Si] 0.5%）') }}</span><span></span><span></span>
          <span class="slag-neg">−{{ slagInfo.siDeduct.toFixed(1) }}</span><span></span><span></span>
        </div>
        <div class="slag-tr slag-sum"><span>{{ t('入渣合计') }}</span><span></span>
          <span>{{ slagInfo.caoTotal.toFixed(1) }}</span><span>{{ slagInfo.sio2Total.toFixed(1) }}</span>
          <span>{{ slagInfo.mgoTotal.toFixed(1) }}</span><span>{{ slagInfo.al2o3Total.toFixed(1) }}</span>
        </div>
      </div>
      <div class="kv2"><span>{{ t('炉渣氧化物成分（质量分数 %）') }}</span><b>CaO {{ slagInfo.comp.cao.toFixed(1) }} · SiO₂ {{ slagInfo.comp.sio2.toFixed(1) }} · MgO {{ slagInfo.comp.mgo.toFixed(1) }} · Al₂O₃ {{ slagInfo.comp.al2o3.toFixed(1) }}</b></div>
      <div class="kv2"><span>{{ t('成分法渣量估算') }}</span><b>{{ slagInfo.slagEst.toFixed(0) }} <span class="u">kg/t{{ t('（节点设定渣比') }} {{ node.params.slag_rate ?? 300 }}{{ t('，交叉校验用）') }}</span></b></div>
      <div class="pr-hint">
        R₂ = ΣCaO / ΣSiO₂ = {{ slagInfo.caoTotal.toFixed(1) }} / {{ slagInfo.sio2Total.toFixed(1) }}；
        R₃ = (CaO+MgO)/SiO₂ = ({{ slagInfo.caoTotal.toFixed(1) }}+{{ slagInfo.mgoTotal.toFixed(1) }}) / {{ slagInfo.sio2Total.toFixed(1) }}。
        {{ t('成分来源：烧结/球团/块矿脉石 + 焦炭/煤粉灰分（物料面板「详细化学成分 → 灰分组成」）+ 熔剂(石灰石)；MgO 主要来自熔剂与灰分、Al₂O₃ 主要来自矿脉石与煤灰。炉料成分与入炉比修改后实时联动。') }}
      </div>
      </div>
      </CollapseSection>

      <button class="del-node" @click="store.removeFlowNode(node.id)">{{ t('删除该工序节点') }}</button>
    </template>

    <!-- 设备节点 -->
    <template v-else-if="node.kind === 'device'">
      <CollapseSection :title="node.metering ? t('计量设备（只读）') : t('可调设备（可设定）')" tone="blue" :show-more="false">
      <div class="card">
        <div class="kv2"><span>{{ t('名称') }}</span><b>{{ node.name }}</b></div>
        <div class="kv2"><span>{{ t('类别') }}</span><b>{{ node.metering ? t('计量·监测') : t('可调·控制') }}</b></div>
        <div class="kv2"><span>{{ t('量纲') }}</span><b>{{ devMeasures }}</b></div>
        <div class="kv2"><span>{{ t('数量（台）') }}</span>
          <input type="number" min="1" max="9" step="1" class="spec-sel" :value="node.count || 1"
                 @change="store.setFlowCount(node.id, $event.target.value)" :title="t('大于 1 时自动形成小组（黄色描边）')" />
        </div>
        <div class="pr-hint">{{ t('台数大于 1 时自动形成小组，在编排卡片中以黄色描边表示。') }}</div>
      </div>
      </CollapseSection>
      <template v-if="!node.metering">
        <CollapseSection :title="t('设定值')" tone="amber" :show-more="false">
        <div class="card">
          <div class="param-row">
            <div class="pr-top"><span>{{ t('设定') }}</span><b>{{ node.setpoint }} <span class="u">{{ dSp(node).unit }}</span></b></div>
            <input type="number" :min="dSp(node).min" :max="dSp(node).max" :step="dSp(node).step||1" class="num"
                   :value="node.setpoint" @input="store.setDeviceSetpoint(node.id, $event.target.value)" />
            <div class="pr-hint pr-range-row">
              <span>{{ t('量程') }}</span>
              <input type="number" class="rg-in" :value="dSp(node).min" :title="t('下限')"
                     @input="store.setFlowDeviceRange(node.id, { min: $event.target.value })" />
              <span class="rg-dash">–</span>
              <input type="number" class="rg-in" :value="dSp(node).max" :title="t('上限')"
                     @input="store.setFlowDeviceRange(node.id, { max: $event.target.value })" />
              <span class="rg-unit">{{ dSp(node).unit }}</span>
              <input type="number" class="rg-in rg-step" :value="dSp(node).step||1" :title="t('步长')"
                     @input="store.setFlowDeviceRange(node.id, { step: $event.target.value })" />
              <button v-if="node.range" class="rg-reset" :title="t('恢复默认量程')" @click="store.resetFlowDeviceRange(node.id)">↺</button>
            </div>
          </div>
          <!-- 附加可调项（如鼓风机鼓风湿度） -->
          <div v-for="es in dExtra(node)" :key="es.key" class="param-row">
            <div class="pr-top"><span>{{ es.label }}</span><b>{{ extraValOf(node, es.key) }} <span class="u">{{ es.unit }}</span></b></div>
            <input type="number" :min="es.min" :max="es.max" :step="es.step||1" class="num"
                   :value="extraValOf(node, es.key)" @input="store.setDeviceExtraSetpoint(node.id, es.key, $event.target.value)" />
            <div class="pr-hint">{{ t('范围') }} {{ es.min }}–{{ es.max }} {{ es.unit }}</div>
          </div>
        </div>
        </CollapseSection>
      </template>
      <CollapseSection :title="t('绑定到工序')" tone="green" :show-more="false">
      <div class="card">
        <select :value="node.boundTo || ''" @change="bindToProcess($event.target.value)">
          <option value="">{{ t('未绑定') }}</option>
          <option v-for="p in processNodes" :key="p.id" :value="p.id">{{ p.name }}</option>
        </select>
        <div class="pr-hint">{{ t('绑定后该设备纳入工序能耗与减排修正（如鼓风机/燃烧器优化可降低直接排放）。') }}</div>
      </div>
      </CollapseSection>
    </template>

    <!-- 原料源节点 -->
    <template v-else>
      <CollapseSection :title="t('原料 / 产物源')" tone="blue" :show-more="false">
      <div class="card">
        <div class="kv2"><span>{{ t('名称') }}</span><b>{{ matName(node.type) }}</b></div>
        <div class="kv2"><span>{{ t('类别') }}</span><b>{{ matCat }}</b></div>
        <div class="kv2"><span>{{ t('单位') }}</span><b>{{ matUnit }}</b></div>
        <div class="kv2"><span>{{ t('隐含碳因子') }}</span><b>{{ matCarbon }} <span class="u">tCO₂/{{ t('单位') }}</span></b></div>
      </div>
      <div class="pr-hint">{{ t('该节点作为画布中的物料输入源，从输出端口连入工艺输入端口即可指定其作为输入。') }}</div>
      <button v-if="matCompEditable" class="comp-btn" @click="store.selectMaterial(node.type)">{{ t('设置详细成分（TFe / CaO / 固定碳…）→') }}</button>
      </CollapseSection>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useSimStore } from '../stores/sim'
import { MATERIALS, MATERIAL_MAP, PROCESS_MAP, DEVICE_MAP } from '../data/flowLibrary'
import { EDITABLE_PARAMS } from '../data/processMeta'
import CollapseSection from './CollapseSection.vue'
import { calcSlagBasicity } from '../utils/slagBasicity'
import { t } from '../i18n'

const store = useSimStore()

const node = computed(() => store.selectedFlowNode)
const group = computed(() => store.selectedGroup)
const groupMembers = computed(() => {
  if (!group.value) return []
  const ids = new Set(group.value.members || [])
  return store.scheme.nodes.filter((n) => ids.has(n.id))
})
// 小组对外输出概要文本
function gOutText(g) {
  const outs = g.outputs || []
  if (!outs.length) return '—'
  return t('出: ') + outs.map((o) => matName(o.material)).join(' / ')
}
// 小组输入/输出设定编辑
function setGroupIo(gid, kind, i, mat) {
  const g = store.scheme.groups.find((x) => x.id === gid)
  if (!g) return
  const arr = JSON.parse(JSON.stringify(kind === 'inputs' ? g.inputs : g.outputs))
  if (arr[i]) arr[i].material = mat
  store.setGroupIo(gid, kind === 'inputs' ? { inputs: arr } : { outputs: arr })
}
function addGroupIo(gid, kind) {
  const g = store.scheme.groups.find((x) => x.id === gid)
  if (!g) return
  const arr = JSON.parse(JSON.stringify(kind === 'inputs' ? g.inputs : g.outputs))
  arr.push({ material: MATERIALS[0] ? MATERIALS[0].id : 'ore_iron' })
  store.setGroupIo(gid, kind === 'inputs' ? { inputs: arr } : { outputs: arr })
}
function delGroupIo(gid, kind, i) {
  const g = store.scheme.groups.find((x) => x.id === gid)
  if (!g) return
  const arr = JSON.parse(JSON.stringify(kind === 'inputs' ? g.inputs : g.outputs))
  arr.splice(i, 1)
  store.setGroupIo(gid, kind === 'inputs' ? { inputs: arr } : { outputs: arr })
}

const totals = computed(() => store.schemeTotals)
const tpl = computed(() => (node.value ? PROCESS_MAP[node.value.type] : null))

const routeLabel = computed(() => { const r = tpl.value && tpl.value.route; return r === 'aux' ? t('工辅') : t('炼钢') })
// 设备规格：该工序类型的规格档位（后端规格库），以及当前节点所选规格
const specOptions = computed(() => {
  const specs = (store.deviceLibrary && store.deviceLibrary.process_specs) || {}
  return (node.value && specs[node.value.type]) || []
})
const currentSpec = computed(() => {
  const key = node.value && node.value.spec
  return specOptions.value.find((s) => s.key === key) || null
})
// 参数范围：节点自定义范围（ranges）> 规格档位 ranges > 模板默认范围（min/max/step）
// 抽为通用函数，供本节点与上游联动节点共同使用
function effParamsOf(n, t) {
  const base = (t && t.params) || []
  const specs = (store.deviceLibrary && store.deviceLibrary.process_specs) || {}
  const sp = n ? (specs[n.type] || []).find((s) => s.key === n.spec) : null
  const ranged = sp && sp.ranges ? base.map((p) => {
    const r = sp.ranges[p.key]
    return r ? { ...p, min: r.min ?? p.min, max: r.max ?? p.max, step: r.step ?? p.step } : p
  }) : base
  // 节点级自定义范围（编排模式「工艺参数」内直接调整运行空间，随方案持久化）
  const nr = (n && n.ranges) || {}
  const withNode = ranged.map((p) => {
    const r = nr[p.key]
    return r ? { ...p, min: r.min ?? p.min, max: r.max ?? p.max, step: r.step ?? p.step } : p
  })
  // 合并展示模式元数据（mode: direct 直接录值 / aux 跳转辅助工艺 / derived 指标自动算）
  const metas = {}
  const mp = n ? EDITABLE_PARAMS[n.type] : null
  if (mp) for (const m of mp) metas[m.key] = m
  return withNode.map((p) => {
    const m = metas[p.key]
    return m ? { ...p, mode: m.mode || 'direct', auxType: m.auxType, auxNote: m.auxNote } : p
  })
}
const effParams = computed(() => effParamsOf(node.value, tpl.value))
const paramMode = (p) => p.mode || 'direct'
// 该工艺本身的固定参数设定：面板直接录值（其余 mode 如 aux/derived 不在此面板展示）
const directParams = computed(() => effParams.value.filter((p) => paramMode(p) === 'direct'))
// 返回来源工艺名（属性面板跳转来源）
const backFlowName = computed(() => {
  if (!store.flowBackId) return ''
  const b = store.scheme.nodes.find((x) => x.id === store.flowBackId)
  return b ? b.name : t('上一工艺')
})
const matName = (id) => (MATERIAL_MAP[id] && MATERIAL_MAP[id].name) || id

// ===== 输入 / 输出设定（节点端口编辑）=====
// 同一种类不能多次出现（如输入中不能出现两次煤粉）：
// 修改/添加端口物料时，同方向已存在同物料则拒绝
function setNodePortMat(dir, i, mat) {
  const n = node.value
  if (!n || !n.ports) return
  const arr = n.ports[dir] || []
  const p = arr[i]
  if (!p || p.material === mat) return
  if (arr.some((x, j) => j !== i && x.material === mat)) {
    const m = MATERIAL_MAP[mat]
    store.showToast(t('「') + (m ? m.name : mat) + t('」已在该') + (dir === 'in' ? t('输入') : t('输出')) + t('中，同一种类不能重复出现'), 'warn')
    return
  }
  store.updatePortMaterial(n.id, dir, p.id, mat)
}
function addNodePort(dir) {
  const n = node.value
  if (!n || !n.ports) return
  // 默认取该工艺模板的输入/输出主物料；无则取物料库第一项
  const t = PROCESS_MAP[n.type]
  const def = dir === 'out'
    ? ((t && t.outputs && t.outputs[0]) || (t && t.mainOut) || (MATERIALS[0] && MATERIALS[0].id))
    : ((t && t.inputs && t.inputs[0]) || (t && t.mainIn) || (MATERIALS[0] && MATERIALS[0].id))
  store.addPort(n.id, dir, def)   // store 内做同物料去重
}
function delNodePort(dir, i) {
  const n = node.value
  if (!n || !n.ports) return
  const p = (n.ports[dir] || [])[i]
  if (p) store.removePort(n.id, dir, p.id)
}
const matCat = computed(() => (MATERIAL_MAP[node.value.type] && MATERIAL_MAP[node.value.type].cat) || '—')
const matUnit = computed(() => (MATERIAL_MAP[node.value.type] && MATERIAL_MAP[node.value.type].unit) || '—')
const matCarbon = computed(() => (MATERIAL_MAP[node.value.type] && MATERIAL_MAP[node.value.type].carbon) ?? '—')
// 支持详细化学成分设定的物料（烧结矿/球团/块矿/焦炭/煤/喷吹煤粉/石灰石），点击跳转物料属性面板
const matCompEditable = computed(() => ['sinter', 'pellet', 'iron_ore', 'coke', 'coal', 'pulverized_coal', 'limestone'].includes(node.value.type))
// 高炉炉渣二元碱度（CaO/SiO₂）：随节点参数（焦比/煤比/熔剂比/炉料入炉比/富氧率）与
// 物料成分覆盖（灰分组成、矿石 CaO/SiO₂、石灰石成分）实时联动
const slagInfo = computed(() => {
  if (!node.value || node.value.type !== 'blast_furnace') return null
  return calcSlagBasicity(node.value.params || {}, store.materialOverrides || {})
})
const devIcon = (type) => (DEVICE_MAP[type] && DEVICE_MAP[type].icon) || 'gauge'
const devMeasures = computed(() => (DEVICE_MAP[node.value.type] && DEVICE_MAP[node.value.type].measures) || '—')
// 设备设定值量程：节点自定义量程（range，随方案持久化）> 设备库默认设定范围
const dSp = (d) => {
  const base = (DEVICE_MAP[d.type] && DEVICE_MAP[d.type].setpoint) || { min: 0, max: 100, step: 1, unit: '' }
  const r = (d && d.range) || {}
  return { ...base, ...r }
}
// 节点是否对该参数自定义过范围（用于显示「恢复默认」按钮）
const hasNodeRange = (k) => !!(node.value && node.value.ranges && node.value.ranges[k])
const dExtra = (d) => (DEVICE_MAP[d.type] && DEVICE_MAP[d.type].extraSetpoints) || []
const extraValOf = (d, key) => {
  if (d && d.extraSetpoints && d.extraSetpoints[key] != null) return d.extraSetpoints[key]
  const es = dExtra(d).find((x) => x.key === key)
  return es ? es.def : 0
}
const processNodes = computed(() => store.scheme.nodes.filter((n) => n.kind === 'process'))
// 同类型工艺实例（流程中可能存在多个，例如多台鼓风机/多座电炉），用于属性面板顶部实例切换
const sameTypeNodes = computed(() => {
  if (!node.value) return []
  return store.scheme.nodes.filter((n) => n.kind === 'process' && n.type === node.value.type)
})
const typeIndex = computed(() => sameTypeNodes.value.findIndex((n) => n.id === (node.value && node.value.id)))
function switchInstance(dir) {
  const arr = sameTypeNodes.value
  if (arr.length < 2 || !node.value) return
  const i = typeIndex.value
  const ni = (i + dir + arr.length) % arr.length
  store.selectFlow(arr[ni].id)
}


function estOf(id) { return store.schemeResult.nodes[id] }
function fmt(n) { return (n == null ? '—' : Number(n).toLocaleString('zh-CN', { maximumFractionDigits: 1 })) }
function nodeSub(n) {
  if (n.kind === 'material') return t('原料/产物源')
  if (n.kind === 'device') return n.metering ? t('计量·只读') : t('可调·设定')
  return (PROCESS_MAP[n.type] && PROCESS_MAP[n.type].label) || n.type
}
// 输入端口行内配比：读取 recipe 中该物料的配比（1 = 100%）
function recipeRatioOf(mat) {
  const n = node.value
  if (!n || !n.recipe) return null
  const r = n.recipe.find((x) => x.material === mat)
  return r != null ? r.ratio : null
}
// 输入端口行内配比：按物料写入 recipe（不存在则自动追加）
function setRecipeRatioForMaterial(mat, v) {
  const n = node.value
  if (!n || !v) return
  store.setRecipeRatioForMaterial(n.id, mat, v)
}
function bindToProcess(pid) {
  const n = node.value
  if (!n) return
  store.bindDeviceToProcess(n.id, pid)
}
</script>

<style scoped>
.flow-insp { display: flex; flex-direction: column; }
/* 炉渣二元碱度区块 */
.slag-r2-row b { font-size: 15px; }
.slag-r2-val { display: inline-flex; align-items: center; gap: 6px; }
.slag-tag { font-size: 10px; padding: 1px 8px; border-radius: 3px; font-weight: 400; }
.slag-tag.ok { color: var(--green, #4f9d6b); border: 1px solid rgba(79,157,107,.4); background: rgba(79,157,107,.10); }
.slag-tag.low { color: #b06a1a; border: 1px solid rgba(201,154,46,.5); background: rgba(201,154,46,.12); }
.slag-tag.high { color: #b04a3a; border: 1px solid rgba(176,74,58,.4); background: rgba(176,74,58,.10); }
.slag-tbl-t { font-size: 11px; font-weight: 500; color: var(--green, #4f9d6b); margin: 10px 0 4px; }
.slag-tbl { border: 1px solid var(--line); border-radius: 4px; overflow: hidden; }
.slag-tr { display: grid; grid-template-columns: 1.6fr 0.7fr 0.75fr 0.75fr 0.75fr 0.75fr; font-size: 11px; padding: 3px 8px; }
.slag-tr + .slag-tr { border-top: 1px solid var(--line); }
.slag-th { color: var(--muted); font-size: 10.5px; background: rgba(0,0,0,.02); }
.slag-sum { font-weight: 500; background: rgba(0,0,0,.02); }
.slag-neg { color: #b04a3a; }
.comp-btn { margin-top: 8px; width: 100%; font-size: 11px; padding: 5px 8px;
  color: var(--accent2); border: 1px solid var(--accent2); background: transparent; cursor: pointer; }
.comp-btn:hover { background: var(--accent2); color: #fff; }
.spec-sel { width: 100%; }
.recipe-row { display: flex; align-items: center; gap: 6px; margin-bottom: 7px; }
.recipe-row select, .bind-row select { flex: 1; }
.recipe-row input { width: 64px; }
.ports-col { display: block; width: 100%; }
.ports-col + .ports-col { margin-top: 10px; }
.pc-t { font-size: 10px; color: var(--accent2); font-weight: 400; display: block; margin-bottom: 4px; }
.pc { display: block; font-size: 11px; color: var(--text); padding: 2px 0; }
.pc + .pc { border-top: 1px solid var(--line); }
/* 工序标题行 + 多实例切换 */
.sec-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.inst-switch { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--muted); }
.inst-btn { width: 18px; height: 18px; line-height: 1; border: 1px solid var(--line); background: var(--panel-2); color: var(--text); border-radius: 3px; cursor: pointer; padding: 0; font-size: 12px; }
.inst-btn:hover { border-color: var(--accent-d); color: var(--accent-d); }
.inst-idx { min-width: 30px; text-align: center; }
/* 被工辅驱动的参数 */
.pr-val-wrap { display: inline-flex; align-items: center; gap: 6px; }
/* 属性面板返回条（主工艺 → 分支辅助工艺跳转后出现） */
.flow-back-bar { display: flex; align-items: center; gap: 6px; padding: 6px 10px; margin-bottom: 8px; border: 1px dashed var(--accent); border-radius: 4px; background: rgba(37, 99, 235, 0.08); cursor: pointer; user-select: none; color: var(--accent-d); font-size: 11px; font-weight: 600; }
.flow-back-bar:hover { background: rgba(37, 99, 235, 0.16); }
.fb-arrow { font-size: 14px; line-height: 1; }
/* 小组：名称行 / 输入输出设定行 */
.gname-in { width: 100%; border: 1px solid var(--line); background: var(--input, var(--bg)); color: var(--text); border-radius: 3px; padding: 2px 6px; font-size: 11px; }
.gname-in:focus { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent-l); outline: none; }
.gio-row { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.gio-row select { flex: 1; min-width: 0; }
/* 输入端口行内配比输入 */
.gio-row .ratio-in { width: 56px; flex: 0 0 auto; }
.gio-row .ratio-in::-webkit-outer-spin-button, .gio-row .ratio-in::-webkit-inner-spin-button { -webkit-appearance: none; margin: 0; }
.gio-row .ratio-in { -moz-appearance: textfield; appearance: textfield; }
.muted-note { font-size: 11px; color: var(--muted); margin-bottom: 8px; line-height: 1.6; }
/* 参数范围 / 设备量程内联编辑（编排模式内化平台配置） */
.pr-range-row { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.rg-in { width: 52px; border: 1px solid var(--line); background: var(--input, var(--bg)); color: var(--text); border-radius: 3px; padding: 1px 4px; font-size: 11px; }
.rg-in:focus { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent-l); outline: none; }
.rg-step { width: 46px; }
.rg-dash, .rg-unit { color: var(--muted); font-size: 10px; }
.rg-reset { border: 1px solid var(--line); background: var(--panel-2); color: var(--accent-d); border-radius: 3px; cursor: pointer; padding: 0 5px; font-size: 10px; line-height: 1.5; }
.rg-reset:hover { border-color: var(--accent-d); }
/* 可调分支（上游链路） */
</style>
