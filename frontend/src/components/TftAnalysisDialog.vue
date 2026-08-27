<template>
  <Teleport to="body">
    <div class="tad-mask" @mousedown.self="onClose">
      <div class="tad-dialog" ref="dialogEl" :style="dialogStyle" :class="{ dragging }">
        <!-- 标题栏（按住可拖动弹窗） -->
        <div class="tad-titlebar" @mousedown.prevent="onTitleDown">
          <span class="tad-icon">◱</span>
          <span class="tad-title">高炉数值仿真分析</span>
          <span class="tad-spacer"></span>
          <button class="tad-restore" :disabled="!restoreDirty" title="恢复打开弹窗时的高炉参数" @click.stop="onRestore">恢复仿真前</button>
          <button class="tad-close" title="关闭 (Esc)" @click="onClose">
            <svg width="14" height="14" viewBox="0 0 16 16"><path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.4" fill="none" stroke-linecap="round"/></svg>
          </button>
        </div>

        <div class="tad-body">
          <!-- 左栏：四轴曲线 + 参数设定 -->
          <div class="tad-left">
            <!-- 六轴曲线 2×3 网格（点击任一图切换当前操作轴，滑块联动） -->
            <div class="tad-grid">
              <div
                v-for="a in charts" :key="a.key"
                class="tad-cell" :class="{ on: a.key === ax.key }"
                @click="axKey = a.key"
              >
                <div class="cell-head">
                  <span class="cell-name">{{ a.label }}</span>
                  <span class="cell-val mono">{{ fmt(a.curVal) }} {{ a.unit }}<sup v-if="a.coalOxyInc > 0.5" class="cell-eff">富氧+{{ fmt(a.coalOxyInc) }}</sup></span>
                </div>
                <svg :viewBox="viewBox" preserveAspectRatio="none" @mousemove="onMove($event, a)" @mouseleave="tip = null">
                  <rect :x="pad.l" :y="y(cfg.tftHigh)" :width="W - pad.l - pad.r" :height="Math.max(0, y(cfg.tftLow) - y(cfg.tftHigh))" fill="var(--green)" opacity="0.10" />
                  <line :x1="pad.l" :x2="W - pad.r" :y1="y(cfg.tftLow)" :y2="y(cfg.tftLow)" stroke="var(--green)" stroke-dasharray="4 3" opacity="0.5" />
                  <line :x1="pad.l" :x2="W - pad.r" :y1="y(cfg.tftHigh)" :y2="y(cfg.tftHigh)" stroke="var(--green)" stroke-dasharray="4 3" opacity="0.5" />
                  <g v-for="gv in yTicks" :key="'y' + gv">
                    <line :x1="pad.l" :x2="W - pad.r" :y1="y(gv)" :y2="y(gv)" stroke="var(--border)" />
                    <text :x="pad.l - 6" :y="y(gv) + 3" text-anchor="end">{{ gv }}</text>
                  </g>
                  <g v-for="gx in a.ticks" :key="'x' + gx">
                    <line :x1="xOf(a, gx)" :x2="xOf(a, gx)" :y1="H - pad.b" :y2="H - pad.b + 4" stroke="var(--border)" />
                    <text :x="xOf(a, gx)" :y="H - pad.b + 14" text-anchor="middle">{{ fmt(gx) }}</text>
                  </g>
                  <line :x1="pad.l" :x2="pad.l" :y1="pad.t" :y2="H - pad.b" stroke="var(--border)" stroke-width="1" />
                  <line :x1="pad.l" :x2="W - pad.r" :y1="H - pad.b" :y2="H - pad.b" stroke="var(--border)" stroke-width="1" />
                  <polyline v-for="(seg, i) in a.segs" :key="i" :points="seg.pts" fill="none" :stroke="colorOf[seg.code]" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" />
                  <template v-if="a.curTft != null">
                    <line :x1="xOf(a, a.curVal)" :x2="xOf(a, a.curVal)" :y1="pad.t" :y2="H - pad.b" stroke="var(--muted)" stroke-dasharray="3 3" opacity="0.6" />
                    <circle :cx="xOf(a, a.curVal)" :cy="y(a.curTft)" r="4.5" fill="var(--panel)" :stroke="cur.status.color" stroke-width="2.4" />
                  </template>
                </svg>
                <div v-if="tip && tip.key === a.key" class="tad-tip" :style="{ left: tip.px + 'px', top: tip.py + 'px' }">
                  <div class="t1">{{ a.label }} = {{ fmt(tip.pt.x) }} {{ a.unit }}</div>
                  <div class="t2">TFT = <b>{{ tip.pt.tft.toFixed(0) }} ℃</b></div>
                  <div class="t2" v-if="tip.pt.co2 != null">CO₂ = <b>{{ tip.pt.co2.toFixed(1) }} tCO₂/h</b></div>
                </div>
              </div>
            </div>

            <!-- 参数设定（滑块 → 联动仿真） -->
            <div class="tad-setter">
              <div class="ts-head">
                <span class="ts-lbl">{{ ax.label }}</span>
                <span class="ts-val mono">
                  <template v-if="ax.key === 'coal_inj'">
                    <b>{{ fmt(effFuel.coal_inj) }}</b> {{ ax.unit }}
                    <span style="font-size:10px;color:#9aa0a6;margin-left:4px;">(设定 {{ fmt(curX) }})</span>
                  </template>
                  <template v-else>
                    <b>{{ fmt(curX) }}</b> {{ ax.unit }}
                  </template>
                </span>
                <span class="ts-badge" :class="applied ? 'ok' : 'dirty'">
                  <i class="bd-dot"></i>{{ applied ? '已应用' : '待应用' }}
                </span>
              </div>
              <!-- 喷煤比轴：可直接拖动调节（设定煤比），仍随富氧率自动联动派生增量；图上/悬停按「有效煤比」（设定 + 富氧增量）展示 -->
              <!-- X 轴固定 0~220 kg/t：富氧率提升时曲线/当前点沿轴右移，坐标刻度不动 -->
              <div v-if="ax.key === 'coal_inj'" class="ts-eff">
                <template v-if="(effFuel.coal_inj || 0) - (Number.isFinite(curX.value) ? curX.value : 0) > 0.5">
                  喷煤比可直接拖动调节（设定煤比）。设定煤比 {{ fmt(curX) }} kg/t + 富氧增量 {{ fmt((effFuel.coal_inj || 0) - (Number.isFinite(curX.value) ? curX.value : 0)) }} = 有效煤比 <b>{{ fmt(effFuel.coal_inj) }} kg/t</b>。曲线/悬停/当前点均按有效煤比展示，X 轴固定 0~220。
                </template>
                <template v-else>
                  喷煤比可直接拖动调节（设定煤比）。设定煤比 = 有效煤比 {{ fmt(effFuel.coal_inj) }} kg/t（无富氧增量）。X 轴固定 0~220。
                </template>
              </div>
              <div v-else-if="ax.key === 'coke_rate'" class="ts-eff">
                焦比可直接拖动设定（设定焦比）。设定焦比 {{ fmt(curX) }} kg/t 时，煤比保持冻结 = <b>{{ fmt(effFuel.coal_inj) }} kg/t</b>（含富氧派生 +{{ fmt(effFuel.coal_oxy_inc) }}），仅焦比变动、不反向推导煤比。TFT 与 CO₂ 随焦比直接联动。
              </div>
              <input
                class="ts-range"
                type="range"
                :min="ax.min" :max="ax.max" :step="ax.step || 1"
                v-model.number="localVal"
                :disabled="!bfUnit"
                @change="onApply"
              />
              <div class="ts-scale">
                <span class="mono">{{ fmt(ax.min) }}</span>
                <span class="mono">{{ fmt(ax.max) }}</span>
              </div>
            </div>

            <!-- 动态解读 -->
            <div class="tad-note" :class="note.kind">
              <span class="note-icon">{{ noteIcon[note.kind] }}</span>
              <span class="note-text">{{ note.text }}</span>
            </div>
          </div>

          <!-- 右栏：当前工况 + 灵敏度总览 + 策略建议 -->
          <div class="tad-right">
            <div class="tad-sec-title">当前工况</div>
            <div class="tad-cond">
              <div class="cond-main">
                <span class="cond-tft mono">{{ cur.tft.toFixed(0) }}</span>
                <span class="cond-unit">℃</span>
                <span class="cond-st" :style="{ color: cur.status.color }">
                  <i class="st-dot" :style="{ background: cur.status.color }"></i>{{ cur.status.label }}
                </span>
              </div>
              <div class="cond-grid">
                <!-- 焦比/煤比：与主流程排放链路共用同一推算真源（utils/bfFuel），随操作参数联动 -->
                <div class="cg-item"><span class="cg-k">焦比<sup>联动</sup></span><b class="mono">{{ fmt(effFuel.coke_rate) }} kg/t</b></div>
                <div class="cg-item"><span class="cg-k">喷煤比<sup v-if="effFuel.coal_oxy_inc > 0.5">富氧+{{ fmt(effFuel.coal_oxy_inc) }}</sup></span><b class="mono">{{ fmt(effFuel.coal_inj) }} kg/t</b></div>
                <div class="cg-item"><span class="cg-k">燃料比<sup>焦+煤</sup></span><b class="mono">{{ fmt((Number(effFuel.coke_rate)||0) + (Number(effFuel.coal_inj)||0)) }} kg/t</b></div>
                <div class="cg-item"><span class="cg-k">热风温度</span><b class="mono">{{ fmt(effFuel.hot_blast_temp) }} ℃</b></div>
                <div class="cg-item"><span class="cg-k">富氧率</span><b class="mono">{{ fmt(effFuel.oxygen_enrich) }} %</b></div>
              </div>
              <div class="cond-tip" style="margin-top:6px">
                燃料比 = 焦比 + 煤比。富氧↑ → 煤比 +15 kg/t·1%，焦比按煤粉成分算出的置换比 RR={{ (replacementRatio||0).toFixed(2) }} 反向联动。因 RR&lt;1，燃料比随富氧微升为正常现象；真实收益是<b>以煤代焦</b>（降成本）+ 提产。
              </div>
              <!-- CO2 排放：随配料比（焦比/喷煤比）联动同步展示（t/h 口径 = 强度 × 铁水产量） -->
              <div class="cond-co2">
                <div class="co2-main">
                  <span class="co2-k">CO₂ 排放</span>
                  <span class="co2-val mono">{{ fmt(co2.CO2_rate) }}</span>
                  <span class="co2-unit">tCO₂/h</span>
                  <span class="cond-st" :style="{ color: co2.level.color }">
                    <i class="st-dot" :style="{ background: co2.level.color }"></i>{{ co2.level.label }}
                  </span>
                </div>
                <div class="co2-grid">
                  <div class="cg-item"><span class="cg-k">铁水产量</span><b class="mono">{{ fmt(co2.hot_metal) }} t/h</b></div>
                  <div class="cg-item"><span class="cg-k">入炉碳 C_in</span><b class="mono">{{ fmt(co2.C_in) }} kg C/t</b></div>
                  <div class="cg-item"><span class="cg-k">产品扣碳 C_HM/C_slag</span><b class="mono">{{ fmt(co2.C_HM) }}/{{ fmt(co2.C_slag) }} kg C/t</b></div>
                  <div class="cg-item"><span class="cg-k">熔剂分解 CO₂</span><b class="mono">+{{ fmt(co2.CO2_flux) }} kg/t</b></div>
                  <div class="cg-item"><span class="cg-k">排放碳 C_emit</span><b class="mono">{{ fmt(co2.C_emit) }} kg C/t</b></div>
                  <div class="cg-item"><span class="cg-k">风口 / 非风口</span><b class="mono">{{ fmt(co2.CO2_rate_raceway) }} / {{ fmt(co2.CO2_rate_other) }} t/h</b></div>
                </div>
                <div class="co2-tip">{{ (co2.level && co2.level.desc) || '国标口径：CO₂ = (入炉碳AD×NCV×CC − 铁水溶碳 − 渣带碳) × 44.009/12.011 + 熔剂分解；炉尘碳计入排放。' }}</div>
              </div>
              
              <div class="cond-tip">可调参数：风温 / 富氧率 / 风量 / 喷煤比 / 焦比。风温与富氧为升温主力；喷煤以氢代碳可减碳但压低 TFT，需富氧/风温补偿。煤比偏离基准 130 kg/t 时焦比按 Δ焦比=−RR×Δ煤比 联动（RR≈0.89）；富氧每 +1% 允许多喷 15 kg/t 煤粉再联动降焦比。<b>焦比为独立设定</b>：拖动只改焦比本身，不反推煤比。</div>
            </div>

            <div class="tad-sec-title">相对基准变化 <span class="sec-sub">基准＝打开弹窗时工况</span></div>
            <div class="tad-delta" v-if="delta">
              <div class="d-row">
                <span class="d-k">焦比</span>
                <span class="d-v mono">{{ fmt(delta.coke.base) }} → {{ fmt(delta.coke.cur) }} kg/t</span>
                <span class="d-delta mono" :class="delta.coke.cls">{{ delta.coke.txt }}</span>
              </div>
              <div class="d-row">
                <span class="d-k">喷煤比</span>
                <span class="d-v mono">{{ fmt(delta.coal.base) }} → {{ fmt(delta.coal.cur) }} kg/t</span>
                <span class="d-delta mono" :class="delta.coal.cls">{{ delta.coal.txt }}</span>
              </div>
              <div class="d-row">
                <span class="d-k">CO₂强度</span>
                <span class="d-v mono">{{ fmt1(delta.co2.base) }} → {{ fmt1(delta.co2.cur) }} kg/tHM</span>
                <span class="d-delta mono" :class="delta.co2.cls">{{ delta.co2.txt }}</span>
              </div>
              <div class="d-foot">Δ 与 Δ% 均按每吨铁水折算：焦比/喷煤比 kg/tHM，CO₂ kg CO₂/tHM（不受铁水产量影响）。基准固定为打开弹窗时的工况，当前随滑块实时预览。</div>
            </div>

<!-- 炉渣碱度 R₂：随炉料配比/燃料比（含富氧置换联动）/物料详细化学成分实时联动，滑块预览同步刷新 -->
            <div class="cond-slag" v-if="slagInfo">
              <div class="co2-main">
                <span class="co2-k">炉渣碱度 R₂（CaO/SiO₂）</span>
                <span class="slag-val mono">{{ slagInfo.r2.toFixed(2) }}</span>
                <span class="cond-st" :style="{ color: slagColor }">
                  <i class="st-dot" :style="{ background: slagColor }"></i>{{ slagInfo.level.txt }}
                </span>
              </div>
              <div class="co2-main">
                <span class="co2-k">三元碱度 R₃（(CaO+MgO)/SiO₂）</span>
                <span class="slag-val mono">{{ slagInfo.r3.toFixed(2) }}</span>
                <span class="cond-st" :style="{ color: slagColor }">
                  <i class="st-dot" :style="{ background: slagColor }"></i>{{ slagInfo.r3Level.txt }}
                </span>
              </div>
              <div class="slag-grid">
                <div class="cg-item"><span class="cg-k">有效燃料量</span><b class="mono">焦 {{ slagInfo.coke.toFixed(0) }} + 煤 {{ slagInfo.coal.toFixed(0) }} kg/t</b></div>
                <div class="cg-item"><span class="cg-k">入渣 CaO</span><b class="mono">{{ slagInfo.caoTotal.toFixed(1) }} kg/t</b></div>
                <div class="cg-item"><span class="cg-k">入渣 SiO₂</span><b class="mono">{{ slagInfo.sio2Total.toFixed(1) }} kg/t</b></div>
                <div class="cg-item"><span class="cg-k">入渣 MgO</span><b class="mono">{{ slagInfo.mgoTotal.toFixed(1) }} kg/t</b></div>
                <div class="cg-item"><span class="cg-k">入渣 Al₂O₃</span><b class="mono">{{ slagInfo.al2o3Total.toFixed(1) }} kg/t</b></div>
                <div class="cg-item"><span class="cg-k">渣量估算</span><b class="mono">{{ slagInfo.slagEst.toFixed(0) }} kg/t</b></div>
                <div class="cg-item cg-wide"><span class="cg-k">炉渣氧化物成分（%）</span><b class="mono">CaO {{ slagInfo.comp.cao.toFixed(1) }} · SiO₂ {{ slagInfo.comp.sio2.toFixed(1) }} · MgO {{ slagInfo.comp.mgo.toFixed(1) }} · Al₂O₃ {{ slagInfo.comp.al2o3.toFixed(1) }}</b></div>
              </div>
              <div class="slag-tbl">
                <div class="slag-tr slag-th"><span>来源</span><span>用量</span><span>CaO</span><span>SiO₂</span><span>MgO</span><span>Al₂O₃</span></div>
                <div class="slag-tr" v-for="pt in slagInfo.parts" :key="pt.name">
                  <span>{{ pt.name }}</span><span>{{ pt.rate.toFixed(0) }}</span>
                  <span>{{ pt.cao.toFixed(1) }}</span><span>{{ pt.sio2.toFixed(1) }}</span>
                  <span>{{ pt.mgo.toFixed(1) }}</span><span>{{ pt.al2o3.toFixed(1) }}</span>
                </div>
                <div class="slag-tr slag-sum"><span>合计</span><span></span><span>{{ slagInfo.caoTotal.toFixed(1) }}</span><span>{{ slagInfo.sio2Gross.toFixed(1) }}</span><span>{{ slagInfo.mgoTotal.toFixed(1) }}</span><span>{{ slagInfo.al2o3Total.toFixed(1) }}</span></div>
                <div class="slag-tr"><span>Si 还原入铁扣减（[Si] 0.5%）</span><span></span><span></span><span class="slag-neg">−{{ slagInfo.siDeduct.toFixed(1) }}</span><span></span><span></span></div>
                <div class="slag-tr slag-sum"><span>入渣合计</span><span></span><span>{{ slagInfo.caoTotal.toFixed(1) }}</span><span>{{ slagInfo.sio2Total.toFixed(1) }}</span><span>{{ slagInfo.mgoTotal.toFixed(1) }}</span><span>{{ slagInfo.al2o3Total.toFixed(1) }}</span></div>
              </div>
              <div class="co2-tip">R₂ = ΣCaO/ΣSiO₂ = {{ slagInfo.caoTotal.toFixed(1) }} / {{ slagInfo.sio2Total.toFixed(1) }}；R₃ = (CaO+MgO)/SiO₂ = ({{ slagInfo.caoTotal.toFixed(1) }}+{{ slagInfo.mgoTotal.toFixed(1) }}) / {{ slagInfo.sio2Total.toFixed(1) }}（kg/tFe）。来源：烧结/球团/块矿脉石 + 焦炭/煤粉灰分（物料「详细化学成分 → 灰分组成」）+ 熔剂(石灰石)；MgO 主要来自熔剂与灰分、Al₂O₃ 主要来自矿脉石与煤灰；随滑块与物料成分实时联动。</div>
            </div>



            <div class="tad-sec-title">灵敏度总览</div>
            <table class="tad-table">
              <thead>
                <tr><th>操作参数</th><th>当前值</th><th>ΔTFT</th><th>ΔCO₂</th><th>趋势</th></tr>
              </thead>
              <tbody>
                <tr v-for="a in axes" :key="a.key" :class="{ on: a.key === ax.key }" @click="axKey = a.key">
                  <td class="c-name">{{ a.label }}</td>
                  <td class="mono">{{ fmt(baseParams[a.key]) }} {{ a.unit }}</td>
                  <td class="mono">{{ (axisStats[a.key] || {}).spreadText || '—' }}</td>
                  <td class="mono">{{ (axisStats[a.key] || {}).co2SpreadText || '—' }}</td>
                  <td>
                    <span class="trend" :class="(axisStats[a.key] || {}).trendCls">
                      <i class="td-dot"></i>{{ (axisStats[a.key] || {}).trend }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
            <div class="tad-ax-desc">{{ ax.hint }}</div>

            <div class="tad-sec-title">策略建议</div>
            <div class="tad-advice">
              <ul>
                <li v-for="(ad, i) in advices" :key="i" :class="'lv-' + ad.level">
                  <i class="ad-dot"></i>{{ ad.text }}
                </li>
              </ul>
            </div>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { PROCESS_MAP } from '../data/flowLibrary'
import { collectTftContext, DEFAULT_TFT_CONFIG, enrichFromFlow } from '../utils/tft'
import { collectSimContext } from '../utils/co2'
import { effFuelParams, calcReplacementRatio, BF_NOMINAL } from '../utils/bfFuel'
// 混合煤单一数据源：把用户在物料界面编辑的配煤（比例/成分）折算为 TFT/CO₂ 配置，
// 使 TFT / RR / CO₂ 随配煤联动（默认混合下数值与现状一致）。
import { makeTftConfig, makeCo2Config, compositionToFuelConfig, blendedComposition } from '../utils/coalBlend'

// 喷煤置换比（由混合煤成分经 Geerdes 公式实算，默认混合 0.89；改配煤比例/成分后实时跟随）；
// 供「燃料比」口径说明展示：Δ燃料比 = Δ煤比×(1−RR)。
const replacementRatio = computed(() => calcReplacementRatio(compositionToFuelConfig(blendedComposition(store.materialOverrides || {}))))
import { calcSlagBasicity } from '../utils/slagBasicity'

const emit = defineEmits(['close'])
const store = useSimStore()

// ---- 可分析轴配置（key 对齐高炉模板参数，附加节能语义）----
// 可操作自变量（操作员可直接设定的旋钮）：风温/纯氧流量/风量/喷煤/焦比/鼓风湿度
//  · 纯氧流量(富氧率派生)/喷煤为耦合杠杆：纯氧↑ → 派生煤比↑ → 经置换比 RR 联动降焦（富氧↑煤比↑焦比↓）。
//  · 焦比亦可作为独立可调轴（轴键映射为 coke_rate_set）：直接设定焦比，煤比冻结不动、
//    不反向推导煤比（满足「调焦比，其他项不动」的诉求）。煤-焦耦合真源仍是 bfFuelRates。
const AXIS_META = {
  hot_blast_temp: { label: '热风温度', hint: '风温↑ → 鼓风显热免费顶替焦炭放热，联动降低焦比、创造减碳空间' },
  o2_flow: { label: '纯氧流量', hint: '氧枪纯氧流量(Nm³/h)注入主风管与空气混合；富氧率由风量+纯氧流量派生——纯氧不含 N₂，富氧↑→压缩 N₂ 稀释、供氧↑，并腾出 TFT' },
  wind_rate: { label: '风量', hint: '供氧与 N2 同步变化近抵消，是产量通道，不减碳' },
  coal_inj: { label: '喷煤比', hint: '喷煤↑替代焦炭（焦比联动↓）减碳，但热解吸热 + 产 H2O 稀释使 TFT↓' },
  coke_rate: { label: '焦比', hint: '焦比↑ → 风口碳燃烧放热↑，TFT↑、CO₂排放同步↑；降焦是最直接的减碳路径。本轴为「独立设定」：仅焦比变动，煤比冻结不反推' },
  blast_humidity: {label:'鼓风湿度', hint: '湿度是炼铁环节努力减小的输入，湿度↑TFT下降，湿度↓TFT上升' }
}

// 轴入参键映射：焦比轴用 coke_rate_set（「独立设定焦比」语义，由 bfFuelRates 直接取用、煤比冻结）；
// 其余轴（含煤比轴）直接用原键。这样焦比/煤比两者都能独立表达、互不覆盖。
const axisParamKey = (key) => (key === 'coke_rate' ? 'coke_rate_set' : key)

const cfg = DEFAULT_TFT_CONFIG
// 每个小图的逻辑坐标系（CSS 以 aspect-ratio 290/200 保持同比例渲染，文字不变形）
const W = 290
const H = 200
const pad = { l: 38, r: 8, t: 16, b: 22 }
const viewBox = `0 0 ${W} ${H}`
const colorOf = { low: 'var(--red)', ok: 'var(--green)', high: 'var(--yellow)' }
const noteIcon = { ok: '✓', low: '▲', high: '▲', warn: '⚠' }
const tip = ref(null)

const tpl = PROCESS_MAP.blast_furnace
const bfUnit = computed(() => (store.model.units || []).find((u) => u.type === 'blast_furnace'))
const baseParams = computed(() => bfUnit.value?.params || {})

const axes = computed(() => {
  const tplParams = tpl?.params || []
  return tplParams
    .filter((p) => AXIS_META[p.key])
    .map((p) => ({
      key: p.key,
      label: p.label || AXIS_META[p.key].label,
      unit: p.unit || '',
      min: p.min,
      max: p.max,
      step: p.step || 1,
      def: p.def,
      hint: AXIS_META[p.key].hint,
    }))
})

const axKey = ref('hot_blast_temp')
const ax = computed(() => axes.value.find((a) => a.key === axKey.value) || axes.value[0] || { key: '', label: '', unit: '', min: 0, max: 1, step: 1 })

// 模型当前值（无系统值时用模板默认）
const modelVal = computed(() => {
  if (ax.value.key === 'coke_rate') return cokeAxisValue.value
  const v = Number(baseParams.value[ax.value.key])
  return Number.isFinite(v) ? v : (ax.value.def != null ? ax.value.def : ax.value.min)
})

// 滑块设定值：切换轴时同步模型值；拖动时本地预览，松手后写入模型
const localVal = ref(null)
watch(() => [bfUnit.value?.id, axKey.value], () => { localVal.value = modelVal.value }, { immediate: true })

// 当前工况点（跟随滑块设定值，未松手时预览）
const curX = computed(() => {
  const v = localVal.value
  return Number.isFinite(v) ? v : modelVal.value
})

// 燃料参数联动推算：与主流程排放链路（compute.js → utils/bfFuel.bfFuelRates）共用同一真源。
// 操作参数（风量/风温/富氧/抽力）存在时按经验式推算焦比/煤比；否则原样读取。
// 跟随滑块预览值 curX 实时刷新，保证弹窗燃料参数与主流程编辑态数值 1:1 对应。
const effFuel = computed(() => effFuelParams(baseParams.value, { [axisParamKey(ax.value.key)]: curX.value }, store.materialOverrides))

// 焦比轴专用「当前有效焦比」：已钉住(coke_rate_set)则取钉住值；否则取其他参数推算值(mode B)。
// 用于焦比轴滑块初值/当前点/应用判定，使「其他参数调出的焦比」与「点开焦比轴」数值连续、不跳变。
const cokeAxisValue = computed(() => {
  const set = baseParams.value.coke_rate_set
  if (set != null) return Number(set)
  const ef = effFuelParams(baseParams.value, {}, store.materialOverrides)
  return ef.coke_rate
})

// 是否已应用：滑块设定值与模型值一致
const applied = computed(() => bfUnit.value != null && Math.abs(Number(modelVal.value) - Number(curX.value)) < 1e-9)

function onApply() {
  if (!bfUnit.value) return
  // 焦比轴：写入独立钉住值 coke_rate_set（绕过模式B再推算，真正「调节焦比其他不动」）
  const key = ax.value.key === 'coke_rate' ? 'coke_rate_set' : ax.value.key
  store.setUnitParam(bfUnit.value.id, key, curX.value)
  localVal.value = curX.value
}

// ---- 恢复到仿真前 ----
// 快照：打开弹窗（组件挂载）时的完整高炉参数，作为「仿真前」基准。
// 记录全部参数（5 个可调轴 + 焦比/煤比基准），供「恢复仿真前」与「相对基准变化」共用。
const snapshot = ref(null)
watch(
  () => bfUnit.value?.id,
  (id) => {
    if (!id || snapshot.value) return
    snapshot.value = { ...baseParams.value }
  },
  { immediate: true }
)

// 是否偏离仿真前（决定「恢复仿真前」按钮可用性）
const restoreDirty = computed(() => {
  const u = bfUnit.value
  if (!u || !snapshot.value) return false
  // 焦比独立钉住值(coke_rate_set)是否被改动
  if ((snapshot.value.coke_rate_set ?? null) !== (baseParams.value.coke_rate_set ?? null)) return true
  for (const a of axes.value) {
    const sv = snapshot.value[a.key]
    const cv = Number(baseParams.value[a.key])
    if (!Number.isFinite(cv)) {
      if (Math.abs(sv - (a.def != null ? a.def : a.min)) > 1e-9) return true
      continue
    }
    if (Math.abs(sv - cv) > 1e-9) return true
  }
  // 滑块存在未应用的修改也算偏离
  if (Math.abs(Number(curX.value) - Number(modelVal.value)) > 1e-9) return true
  return false
})

// 恢复：操作参数写回快照值，滑块同步
function onRestore() {
  const u = bfUnit.value
  if (!u || !snapshot.value) return
  // 恢复焦比钉住值（快照无则回到 null，由模式B重新推算）
  store.setUnitParam(u.id, 'coke_rate_set', snapshot.value.coke_rate_set ?? null)
  for (const a of axes.value) {
    const v = snapshot.value[a.key]
    if (v == null) continue
    if (Math.abs(Number(v) - Number(baseParams.value[a.key])) > 1e-9) store.setUnitParam(u.id, a.key, v)
  }
  const svKey = snapshot.value[ax.value.key]
  if (svKey != null) localVal.value = svKey
}

// 扫描某轴时使用的「基准参数」：
//   - 仅当「富氧率是当前轴（滑块预览中）」时，煤比轴曲线用预览富氧率重算，
//     使富氧→煤粉联动实时可见（富氧越高煤粉图整体右移）。
//   - 其余情况一律用模型值——否则拖动任意滑块都会触发 5 轴全量重算，
//     curX 每帧变化 → seriesMap 反复扫描 200+ 点 → 主线程卡死、滑块拖不动。
// 该函数与 curTftOf / curEffCoalOf 共用同一规则，保证圆点始终落在对应曲线上。
function baseFor(a) {
  const usePreview = axKey.value === 'o2_flow' && a.key === 'coal_inj' && Number.isFinite(Number(curX.value))
  return usePreview ? { ...baseParams.value, oxygen_enrich: enrichFromFlow(baseParams.value.wind_rate, baseParams.value.hot_metal, curX.value, baseParams.value.blast_humidity) } : baseParams.value
}

// 扫描某轴全范围 → TFT / CO2 序列
function scanAxis(a) {
  const pts = []
  const n = Math.max(2, Math.ceil((a.max - a.min) / a.step))
  const base = baseFor(a)
  for (let i = 0; i <= n; i++) {
    const v = a.min + ((a.max - a.min) * i) / n
    try {
      const ef = effFuelParams(base, { [axisParamKey(a.key)]: v }, store.materialOverrides)
      const ctx = collectSimContext(ef, makeTftConfig(store.materialOverrides), makeCo2Config(store.materialOverrides))
      // 喷煤比轴特殊：横坐标用「有效煤比」（设定 + 富氧增量），与当前工况点同坐标系，
      // 否则富氧后曲线停在设定值 130 而当前点 175 错位、圆点不落在曲线上
      // 注：effFuelParams 返回的字段是 coal_inj（有效煤比），无 .coal 键，必须用 coal_inj
      const x = a.key === 'coal_inj' ? ef.coal_inj : v
      pts.push({ x, tft: ctx.tft, co2: ctx.co2 ? ctx.co2.CO2_rate : null })
    } catch (e) {
      pts.push({ x: v, tft: null, co2: null })
    }
  }
  return pts
}

// 每轴全范围扫描序列（缓存）：
//   - staticSeries：不依赖滑块预览的曲线（模型参数变化时自动重算）
//   - dynCoal：仅富氧率预览中时的煤比轴曲线（随富氧率滑块实时重算，只扫 1 个轴）
// 拆分后拖动滑块不会触发全量扫描，拖动才能保持流畅。
const staticSeries = computed(() => {
  const m = {}
  for (const a of axes.value) {
    if (a.key === 'coal_inj' && axKey.value === 'o2_flow') continue
    m[a.key] = scanAxis(a).filter((p) => p.tft != null)
  }
  return m
})
const dynCoal = computed(() => {
  if (axKey.value !== 'o2_flow') return null
  const a = axes.value.find((x) => x.key === 'coal_inj')
  return a ? scanAxis(a).filter((p) => p.tft != null) : null
})
const seriesMap = computed(() => {
  const m = { ...staticSeries.value }
  if (dynCoal.value) m.coal_inj = dynCoal.value
  return m
})

// 当前工况上下文（跟随滑块设定值预览）：TFT + CO2 排放同步计算
const cur = computed(() => {
  try {
    return collectSimContext(effFuelParams(baseParams.value, { [axisParamKey(ax.value.key)]: curX.value }, store.materialOverrides), makeTftConfig(store.materialOverrides), makeCo2Config(store.materialOverrides))
  } catch (e) {
    return { tft: 0, status: { code: 'err', label: '异常', color: '#8a8a8a' }, co2: { CO2_emit: 0, CO2_t: 0, CO2_rate: 0, hot_metal: 0, C_in: 0, C_HM: 0, C_slag: 0, CO2_flux: 0, C_emit: 0, CO2_rate_raceway: 0, CO2_rate_other: 0, level: { code: 'err', label: '—', color: '#8a8a8a' } } }
  }
})

// CO2 排放上下文（当前工况）
const co2 = computed(() => cur.value.co2 || {})

// ---- 炉渣二元碱度 R₂（CaO/SiO₂）：高炉专属指标 ----
// 参数取「基础参数 + 当前滑块预览值」（富氧率/喷煤比等轴实时联动，与 TFT/CO₂ 同口径），
// 物料详细化学成分覆盖读 store.materialOverrides（与工艺界面 FlowInspector 一致）。
const slagInfo = computed(() => {
  if (!bfUnit.value || bfUnit.value.type !== 'blast_furnace') return null
  try {
    const kv = ax.value && ax.value.key
    const p = kv && Number.isFinite(Number(curX.value))
      ? { ...baseParams.value, [kv]: Number(curX.value) }
      : baseParams.value
    return calcSlagBasicity(p, store.materialOverrides || {})
  } catch (e) { return null }
})
const SLAG_COLOR = { low: '#4a90d9', ok: '#89d185', high: '#e2c08d' }
const slagColor = computed(() => SLAG_COLOR[slagInfo.value?.level?.cls] || '#8a8a8a')

// ---- 相对基准变化（每吨铁水口径）----
// 基准 = 打开弹窗时（仿真前）的工况快照；当前 = 滑块预览工况。
// 回答：调了哪些参数 → 焦比/喷煤比/CO₂ 强度相对基准变了多少（Δ 与 Δ%）。
const baseCtx = computed(() => {
  if (!snapshot.value) return null
  try {
    const fuel = effFuelParams(snapshot.value, {}, store.materialOverrides)
    return { fuel, ctx: collectSimContext(fuel, makeTftConfig(store.materialOverrides), makeCo2Config(store.materialOverrides)) }
  } catch (e) {
    return null
  }
})

const delta = computed(() => {
  const b = baseCtx.value
  if (!b) return null
  const mk = (base, curV, colorable) => {
    const d = curV - base
    const pct = Math.abs(base) > 1e-9 ? (d / base) * 100 : 0
    let cls = 'flat'
    if (colorable) cls = Math.abs(d) < 1e-9 ? 'flat' : (d < 0 ? 'good' : 'bad')
    const txt = `${d > 0 ? '+' : ''}${fmt1(d)} (${pct > 0 ? '+' : ''}${pct.toFixed(1)}%)`
    return { base, cur: curV, d, pct, txt, cls }
  }
  return {
    coke: mk(b.fuel.coke_rate, effFuel.value.coke_rate, true),
    coal: mk(b.fuel.coal_inj, effFuel.value.coal_inj, false),
    co2: mk(b.ctx.co2.CO2_emit, cur.value.co2.CO2_emit, true),
  }
})

// 喷煤比轴的有效值信息（设定煤比 + 富氧派生 15×富氧率）。
// 富氧率为当前轴时用滑块预览值，使拖动富氧率时喷煤量图实时联动；否则用模型当前富氧率。
function effCoalInfo() {
  const bp = baseParams.value
  const oxy = axKey.value === 'o2_flow'
    ? enrichFromFlow(bp.wind_rate, bp.hot_metal, curX.value, bp.blast_humidity)
    : (bp.oxygen_enrich != null ? bp.oxygen_enrich : enrichFromFlow(bp.wind_rate, bp.hot_metal, bp.o2_flow, bp.blast_humidity))
  return effFuelParams(baseParams.value, { oxygen_enrich: Number.isFinite(oxy) ? oxy : 0 }, store.materialOverrides)
}

// 轴当前显示值：当前轴用滑块预览值，其他轴用模型当前值。
// 喷煤比轴特殊：始终显示「有效煤比」（设定 + 富氧派生）——富氧率提升后喷煤量图上的数值
// 必须随之增加，且与曲线/悬停/当前点同坐标系（否则用户拖动富氧率滑块时会看到喷煤量
// 「计算上增加、图上不变」，或当前点落在曲线外）。
function curValOf(a) {
  if (a.key === 'coal_inj') return effCoalInfo().coal_inj
  if (a.key === axKey.value) return curX.value
  if (a.key === 'coke_rate') return cokeAxisValue.value
  const v = Number(baseParams.value[a.key])
  return Number.isFinite(v) ? v : (a.def != null ? a.def : a.min)
}

// 轴当前工况 TFT（该轴当前值下其他参数固定时的响应）。
// 喷煤轴特殊：以「设定煤比」为入参（bfFuelRates 内部自动叠加富氧派生），
// 避免把 curValOf 返回的有效值再传入导致双重派生（如 130+37.5 再 +37.5）。
// 基准参数走 baseFor(a)，与 scanAxis 同一规则——圆点必然落在对应曲线上。
function curTftOf(a) {
  try {
    const base = baseFor(a)
    const extra = a.key === 'coal_inj'
      ? { coal_inj: axKey.value === 'coal_inj' ? curX.value : Number(baseParams.value.coal_inj) }
      : { [axisParamKey(a.key)]: curValOf(a) }
    return collectTftContext(effFuelParams(base, extra, store.materialOverrides), makeTftConfig(store.materialOverrides)).tft
  } catch (e) {
    return null
  }
}

// 与 curTftOf 同口径的「有效煤比」（同基准规则），用于煤比轴当前点 x 坐标，
// 保证圆点 x/y 严格对应同一组参数，不再出现 x=175(模型) y=TFT@185(预览) 的错位。
function curEffCoalOf(a) {
  const base = baseFor(a)
  const extra = a.key === 'coal_inj'
    ? { coal_inj: axKey.value === 'coal_inj' ? curX.value : Number(baseParams.value.coal_inj) }
    : { [axisParamKey(a.key)]: curValOf(a) }
  return effFuelParams(base, extra, store.materialOverrides).coal_inj
}

// y 轴固定绝对基准（合规带 2050~2250 居中），坐标永不缩放——
// 改动任一参数后，四图折线在固定坐标系内整体平移直接可见
const Y_BASE = { ymin: 2000, ymax: 2300 }
const yRange = computed(() => Y_BASE)
const y = (v) => pad.t + ((yRange.value.ymax - v) / (yRange.value.ymax - yRange.value.ymin)) * (H - pad.t - pad.b)

// 轴显示坐标端点。
// 喷煤比轴：固定坐标系 [0, BF_NOMINAL.coalMax=260]（有效煤比 clamp 上限），
//   ——富氧率提升时「曲线与当前点」沿固定 X 轴右移（设定 130 + 富氧 3% = 有效 175），
//   ——坐标轴刻度本身不再随富氧率平移，否则拖动富氧率时整个 X 轴漂移、滑块与图错位。
// 其余轴：固定 [a.min, a.max]。
function axisExtent(a) {
  if (a.key === 'coal_inj') {
    return { xmin: 0, xmax: BF_NOMINAL.coalMax }
  }
  return { xmin: a.min, xmax: a.max }
}

const xOf = (a, v) => {
  const { xmin, xmax } = axisExtent(a)
  const lo = Math.min(xmin, curValOf(a))
  const hi = Math.max(xmax, curValOf(a))
  return pad.l + ((v - lo) / (hi - lo)) * (W - pad.l - pad.r)
}
const xTicksOf = (a) => {
  const { xmin, xmax } = axisExtent(a)
  const lo = Math.min(xmin, curValOf(a))
  const hi = Math.max(xmax, curValOf(a))
  // 煤比轴：固定刻度 0 / 模板基准煤比 / 煤比上限(coalMax=220)，稳定可读
  if (a.key === 'coal_inj') return [0, a.def != null ? a.def : 130, BF_NOMINAL.coalMax]
  const out = []
  for (let i = 0; i <= 3; i++) out.push(lo + ((hi - lo) * i) / 3)
  return out
}

const yTicks = computed(() => {
  const { ymin, ymax } = yRange.value
  const step = Math.max(50, Math.round((ymax - ymin) / 5 / 50) * 50)
  const out = []
  for (let v = Math.ceil(ymin / step) * step; v <= ymax; v += step) out.push(v)
  return out
})

// 六轴图表数据（2×3 网格）
const charts = computed(() =>
  axes.value.map((a) => {
    const s = seriesMap.value[a.key] || []
    const segs = []
    let run = []
    let lastCode = null
    for (const p of s) {
      const code = p.tft < cfg.tftLow ? 'low' : p.tft > cfg.tftHigh ? 'high' : 'ok'
      if (code !== lastCode && run.length) { segs.push({ code: lastCode, pts: run }); run = [] }
      lastCode = code
      run.push(p)
    }
    if (run.length) segs.push({ code: lastCode, pts: run })
    return {
      ...a,
      curVal: a.key === 'coal_inj' ? curEffCoalOf(a) : curValOf(a),
      curTft: curTftOf(a),
      coalOxyInc: a.key === 'coal_inj'
        ? curEffCoalOf(a) - (axKey.value === 'coal_inj' && Number.isFinite(curX.value) ? curX.value : Number(baseParams.value.coal_inj))
        : 0,
      ticks: xTicksOf(a),
      segs: segs.map((g) => ({ code: g.code, pts: g.pts.map((p) => `${xOf(a, p.x).toFixed(1)},${y(p.tft).toFixed(1)}`).join(' ') })),
    }
  })
)

// 每轴统计（全表）
const axisStats = computed(() => {
  const out = {}
  for (const a of axes.value) {
    const pts = seriesMap.value[a.key] || []
    if (!pts.length) { out[a.key] = { spreadText: '—', co2SpreadText: '—', trend: '—', trendCls: '' }; continue }
    const mn = Math.min(...pts.map((p) => p.tft))
    const mx = Math.max(...pts.map((p) => p.tft))
    const d = pts[pts.length - 1].tft - pts[0].tft
    let trend = '近水平', trendCls = 'flat'
    if (d > 3) { trend = '升温'; trendCls = 'up' }
    else if (d < -3) { trend = '降温'; trendCls = 'down' }
    // CO2 全范围跨度（配料比等碳相关参数联动时最直观）
    const c2s = pts.map((p) => p.co2).filter((v) => v != null && Number.isFinite(v))
    const c2mn = c2s.length ? Math.min(...c2s) : null
    const c2mx = c2s.length ? Math.max(...c2s) : null
    out[a.key] = {
      spreadText: `${(mx - mn).toFixed(1)} ℃`,
      co2SpreadText: c2s.length ? `${(c2mx - c2mn).toFixed(1)} t/h` : '—',
      trend, trendCls,
    }
  }
  return out
})

// 动态解读（教学点）
const note = computed(() => {
  const st = cur.value.status
  const a = ax.value
  const s = seriesMap.value[a.key] || []
  if (!s.length) return { kind: 'warn', text: '扫描失败，请检查高炉工艺参数是否有效。' }
  const spread = Math.max(...s.map((p) => p.tft)) - Math.min(...s.map((p) => p.tft))
  const t0 = s[0].tft
  const t1 = s[s.length - 1].tft
  let text = ''
  const span = (a.max - a.min) || 1
  const slope = (t1 - t0) / span
  if (a.key === 'wind_rate' && spread < 5) {
    text = '曲线近水平：风量↑同时放大供氧与 N2 稀释，两通道抵消，TFT 对风量不敏感——风量用于调节产量，不宜作为温度/减碳调节手段。'
  } else if (a.key === 'hot_blast_temp') {
    text = `曲线${slope > 0 ? '线性上升' : '下降'}（每 +10℃ 约 TFT ${(slope * 10).toFixed(0)}℃）：热风温度直接注入鼓风显热（分子），是最便宜、零碳排放的升温手段，为联动降焦腾出减碳空间。`
  } else if (a.key === 'o2_flow') {
    text = `曲线${slope > 0 ? '上升' : '下降'}（纯氧流量↑→富氧率派生↑）：纯氧不含 N2，注入主风管压缩 N2 分母并提升供氧，同时富氧每升高约 1% 允许多喷 15 kg/t 煤粉（富氧升温 → 燃烧带容纳更多煤粉），经置换联动降焦；煤粉热解吸热会抵消部分 TFT 增益，注意纯氧由空分供给、其电耗计入间接排放。`
  } else if (a.key === 'coke_rate') {
    text = `曲线${slope > 0 ? '线性上升' : '下降'}（每 +10 kg/tFe 约 TFT ${(slope * 10).toFixed(0)}℃）：焦比是风口碳的直接来源，焦比↑ → 燃烧放热↑ → TFT↑，CO₂排放同步线性↑。降焦是最直接的减碳路径，但需风温/富氧/喷煤补偿热量缺口——本轴为独立设定，仅焦比变动、煤比冻结不反推。`
  } else if (a.key === 'coal_inj') {
    text = `曲线${slope < 0 ? '缓降' : '上升'}（每 +10 kg/tFe 约 TFT ${(slope * 10).toFixed(0)}℃）：喷煤替代焦炭可减碳，但热解吸热与产 H2O 稀释压低 TFT，需风温/富氧补偿。`
  }else if(a.key == 'blast_humidity'){
    text = `曲线${slope < 0 ? '线性上升' : '上升'}（每+1g/Nm³） TFT 约下降 ${(6).toFixed(0)}℃）：鼓风湿度上升会带来高炉内部反应H2的比例上升，可以一定程度降低直接还原度，但是收益抵不过水分解的吸热损失，因此要尽量减少。 `
  } else {
    text = `该轴全范围 TFT 变化 ${spread.toFixed(1)}℃。`
  }
  if (st.code === 'low') text += ' 注意：当前 TFT 偏低，应先升温（风温/富氧）恢复热制度，再实施减碳。'
  if (st.code === 'high') text += ' 注意：当前 TFT 偏高，本身即是减碳信号，可优先降焦比。'
  const c2 = cur.value.co2
  if (c2 && Number.isFinite(c2.CO2_rate)) {
    text += ` 当前工况 CO₂ ${c2.CO2_rate.toFixed(1)} tCO₂/h（强度 ${c2.CO2_t.toFixed(3)} t/tHM，${c2.level.label}）。`
  }
  return { kind: st.code, text }
})

// 策略建议
const advices = computed(() => {
  const st = cur.value.status
  const c2 = cur.value.co2
  const list = []
  // 碳排现状（配料比 → CO2 同步结论）
  if (c2 && Number.isFinite(c2.CO2_rate)) {
    list.push({ level: c2.level.code === 'high' ? 'w' : 'g', text: `当前 CO₂ 排放 ${c2.CO2_rate.toFixed(1)} tCO₂/h（强度 ${c2.CO2_t.toFixed(3)} t/tHM，${c2.level.label}）：排放随配料比联动——喷煤↑置换焦炭↓可减碳，TFT 回落到下限即该工况的碳排最优解。` })
  }
  if (st.code === 'low') {
    list.push({ level: 'w', text: `当前 TFT ${cur.value.tft.toFixed(0)}℃ 偏低：先恢复热制度再谈减碳——首选提升热风温度（免费显热），其次提高富氧率（压缩 N2），可少量降低喷煤比（减少热解吸热）。` })
  } else if (st.code === 'high') {
    list.push({ level: 'w', text: `当前 TFT ${cur.value.tft.toFixed(0)}℃ 偏高：本身即是减碳信号——提高喷煤比（以氢代碳、置换焦炭），必要时降低风温/富氧让 TFT 回落到合规带。` })
  } else {
    list.push({ level: 'g', text: `当前 TFT ${cur.value.tft.toFixed(0)}℃ 处于合规区间，可安全实施节能减碳。` })
  }
  list.push({ level: 'g', text: '① 风温打满：热风温度提到上限，鼓风显热免费顶替焦炭放热，焦比联动下降、创造减碳空间（成本最低、零碳排放）。' })
  list.push({ level: 'g', text: '② 用 TFT 空间换碳：提高喷煤比（置换焦炭）或提升风温/富氧联动降低焦比，TFT 随之回落，扣到下限即减碳极限。' })
  list.push({ level: 'g', text: '③ 富氧兜底：喷煤受限时，提高富氧率压缩 N2 分母，释放新一轮提煤/降焦空间。' })
  list.push({ level: 'g', text: '④ 监控闭环：全程盯 TFT 状态，达到下限即停手——TFT 下限就是该工况的碳排最优解。' })
  return list
})

// 悬停取点（每图独立）
function onMove(e, a) {
  const r = e.currentTarget.getBoundingClientRect()
  const px = e.clientX - r.left
  const py = e.clientY - r.top
  const sx = (px / r.width) * W
  const { xmin, xmax } = axisExtent(a)
  const lo = Math.min(xmin, curValOf(a))
  const hi = Math.max(xmax, curValOf(a))
  const vx = lo + ((sx - pad.l) / (W - pad.l - pad.r)) * (hi - lo)
  let best = null
  let bd = 1e9
  for (const p of (seriesMap.value[a.key] || [])) {
    const d = Math.abs(p.x - vx)
    if (d < bd) { bd = d; best = p }
  }
  if (best) tip.value = { key: a.key, px, py: py - 4, pt: best }
}

function onClose() { emit('close') }

// ---- 弹窗拖拽移动（按住标题栏拖动）----
const dialogEl = ref(null)
const dragging = ref(false)
const dialogPos = ref(null) // { x, y }：null 表示初始居中
let dragStart = null

const dialogStyle = computed(() => {
  if (!dialogPos.value) return {}
  return { left: dialogPos.value.x + 'px', top: dialogPos.value.y + 'px', transform: 'none', margin: '0' }
})

function clampDrag(x, y) {
  const el = dialogEl.value
  if (!el) return { x, y }
  const vw = window.innerWidth
  const vh = window.innerHeight
  const w = el.offsetWidth
  const h = el.offsetHeight
  x = Math.min(Math.max(x, -w + 90), vw - 90)
  y = Math.min(Math.max(y, 0), vh - 44)
  return { x, y }
}

function onTitleDown(e) {
  if (e.button !== 0) return
  if (e.target.closest('button')) return
  const el = dialogEl.value
  if (!el) return
  const start = dialogPos.value || { x: el.offsetLeft, y: el.offsetTop }
  dragStart = { mx: e.clientX, my: e.clientY, x: start.x, y: start.y }
  dragging.value = true
  window.addEventListener('mousemove', onDragMove)
  window.addEventListener('mouseup', onDragUp)
}

function onDragMove(e) {
  if (!dragStart) return
  const pos = clampDrag(dragStart.x + (e.clientX - dragStart.mx), dragStart.y + (e.clientY - dragStart.my))
  dialogPos.value = pos
}

function onDragUp() {
  dragging.value = false
  dragStart = null
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragUp)
}

onBeforeUnmount(() => {
  window.removeEventListener('mousemove', onDragMove)
  window.removeEventListener('mouseup', onDragUp)
})

// Esc 关闭
function onKey(e) { if (e.key === 'Escape') onClose() }
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))

function fmt(v) {
  if (v == null || !Number.isFinite(v)) return '—'
  return Math.abs(v) >= 100 ? v.toFixed(0) : (Number.isInteger(v) ? String(v) : v.toFixed(2))
}
function fmt1(v) {
  if (v == null || !Number.isFinite(v)) return '—'
  return v.toFixed(1)
}
</script>

<style scoped>
/* ============ 平台主题风格（背板颜色跟随全局 CSS 变量，浅色/仿真深色自适应） ============
   原 VSCode 深色色板改为平台变量：面板 var(--panel) / 次级面板 var(--panel-2)
   边框 var(--border) / 文字 var(--text) / 强调 var(--accent) / 状态色 var(--green|--yellow|--red|--orange) */
.tad-mask {
  position: fixed; inset: 0; z-index: 1200;
  background: rgba(0, 0, 0, 0.4);
  overflow: hidden;
  font-family: var(--ui);
}
.tad-dialog {
  position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
  width: 1260px; max-width: calc(100vw - 60px); height: 800px; max-height: calc(100vh - 80px);
  display: flex; flex-direction: column; overflow: hidden;
  background: var(--panel); border: 1px solid var(--border); border-radius: 4px;
  box-shadow: var(--shadow);
  color: var(--text);
}
.tad-dialog.dragging {
  box-shadow: var(--shadow), 0 0 0 1px var(--accent);
  cursor: grabbing;
}

/* ---- 标题栏 ---- */
.tad-titlebar {
  display: flex; align-items: center; gap: 9px; flex: none;
  background: var(--panel-2); padding: 0 8px 0 13px; height: 34px;
  border-bottom: 1px solid var(--border);
  cursor: move; user-select: none;
}
.tad-titlebar:active { cursor: grabbing; }
.tad-icon { color: var(--accent); font-size: 14px; }
.tad-title { font-size: 12.5px; font-weight: 600; color: var(--text); letter-spacing: 0.3px; }
.st-dot { width: 7px; height: 7px; border-radius: 50%; display: inline-block; }
.tad-spacer { flex: 1; }
.tad-restore {
  height: 26px; padding: 0 12px; border: 1px solid var(--border); background: transparent;
  color: var(--muted); border-radius: 3px; font-size: 11.5px; cursor: pointer;
  display: inline-flex; align-items: center; letter-spacing: 0.3px;
  transition: color 0.12s, border-color 0.12s, background 0.12s;
}
.tad-restore:hover:not(:disabled) { color: var(--text); border-color: var(--accent); background: var(--accent-l); }
.tad-restore:disabled { opacity: 0.4; cursor: default; }
.tad-close {
  width: 26px; height: 26px; border: none; background: transparent; color: var(--muted);
  border-radius: 3px; cursor: pointer; display: flex; align-items: center; justify-content: center;
}
.tad-close:hover { background: var(--red); color: #fff; }

/* ---- 主体：左图表区 + 右信息区 ---- */
.tad-body { flex: 1; min-height: 0; display: flex; }
.tad-left {
  flex: 1.6; min-width: 0; display: flex; flex-direction: column; gap: 9px;
  padding: 10px 12px; overflow-y: auto; background: var(--panel);
  border-right: 1px solid var(--border);
}
.tad-right {
  flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 9px;
  padding: 10px 12px; overflow-y: auto; background: var(--panel-2);
}

/* ---- 六轴曲线 2×3 网格 ---- */
.tad-grid {
  flex: none; display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}
.tad-cell {
  position: relative; background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px;
  padding: 4px 4px 2px; cursor: pointer;
  transition: border-color 0.12s, box-shadow 0.12s;
}
.tad-cell:hover { border-color: var(--accent2); }
.tad-cell.on { border-color: var(--accent); box-shadow: inset 0 0 0 1px var(--accent); }
.cell-head {
  display: flex; justify-content: space-between; align-items: baseline; gap: 6px;
  padding: 0 4px 3px; font-size: 11px;
}
.cell-name { color: #9d9d9d; font-weight: 600; white-space: nowrap; }
.tad-cell.on .cell-name { color: #5aa9ff; }
.cell-val { color: #c8c8c8; font-size: 11px; }
.cell-eff { font-size: 9px; color: var(--accent2, #5f8294); margin-left: 2px; }
.tad-cell svg { width: 100%; height: auto; aspect-ratio: 290 / 200; display: block; }
.tad-cell svg text { font-size: 9px; fill: var(--faint); }

.tad-tip {
  position: absolute; transform: translate(-50%, -100%); pointer-events: none;
  background: var(--panel-2); color: var(--text); padding: 5px 9px; border-radius: 3px;
  border: 1px solid var(--border); font-size: 11.5px; white-space: nowrap; z-index: 5;
  box-shadow: var(--shadow);
}
.tad-tip .t1 { color: var(--faint); }
.tad-tip .t2 { margin-top: 2px; }
.tad-tip b { color: var(--yellow); }

/* ---- 参数设定滑块（自定义细轨道，无原生外圈） ---- */
.tad-setter {
  flex: none; background: var(--panel-2); border: 1px solid var(--border); border-radius: 3px;
  padding: 8px 11px 6px; display: flex; flex-direction: column; gap: 1px;
}
.ts-head { display: flex; align-items: center; gap: 9px; }
.ts-lbl { font-size: 12px; font-weight: 600; color: var(--accent); }
.ts-val { font-size: 13px; color: var(--text); }
.ts-val b { font-size: 15px; color: var(--text); }
.ts-badge {
  margin-left: auto; display: inline-flex; align-items: center; gap: 5px;
  font-size: 10.5px; padding: 1px 9px; border-radius: 8px; font-weight: 600;
}
.ts-badge .bd-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.ts-badge.ok { background: rgba(46, 158, 99, .14); color: var(--green); }
.ts-badge.ok .bd-dot { background: var(--green); }
.ts-badge.dirty { background: rgba(201, 154, 46, .14); color: var(--yellow); }
.ts-badge.dirty .bd-dot { background: var(--yellow); }

/* 细轨道 + 圆点滑块（无外圈） */
.ts-range {
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 4px; margin: 7px 0 4px;
  background: var(--border); border: none; border-radius: 2px;
  outline: none; cursor: pointer;
}
.ts-range::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 13px; height: 13px; border-radius: 50%;
  background: var(--accent); border: 2px solid var(--text);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.45);
  cursor: grab; transition: background 0.12s;
}
.ts-range::-webkit-slider-thumb:hover { background: var(--accent-d); }
.ts-range::-webkit-slider-thumb:active { cursor: grabbing; }
.ts-range::-moz-range-track { height: 4px; background: var(--border); border: none; border-radius: 2px; }
.ts-range::-moz-range-thumb {
  width: 11px; height: 11px; border-radius: 50%;
  background: var(--accent); border: 2px solid var(--text);
  cursor: grab;
}
.ts-range:disabled { opacity: 0.4; cursor: not-allowed; }
.ts-range:disabled::-webkit-slider-thumb { background: #666; cursor: not-allowed; }
.ts-range:disabled::-moz-range-thumb { background: #666; cursor: not-allowed; }

.ts-scale {
  display: flex; justify-content: space-between;
  font-size: 10px; color: var(--faint); padding: 0 1px;
}

/* 喷煤比轴「设定 vs 有效」说明（富氧派生联动时避免数值误解） */
.ts-eff {
  font-size: 10.5px; line-height: 1.5; color: #9d9d9d;
  background: #1e1e1e; border: 1px solid #2e2e2e; border-radius: 2px;
  padding: 4px 8px; margin-top: 3px;
}
.ts-eff b { color: #ffd97a; }

/* ---- 动态解读（MATLAB 状态条风格） ---- */
.tad-note {
  flex: none; display: flex; gap: 7px; align-items: flex-start;
  font-size: 11.5px; line-height: 1.5; padding: 7px 10px; border-radius: 3px;
  border: 1px solid var(--border);
}
.tad-note .note-icon { font-size: 12px; font-weight: 700; line-height: 1.4; }
.tad-note.ok { background: rgba(46, 158, 99, .12); border-color: var(--green); color: var(--green); }
.tad-note.ok .note-icon { color: var(--green); }
.tad-note.low, .tad-note.high { background: rgba(192, 115, 42, .12); border-color: var(--orange); color: var(--orange); }
.tad-note.low .note-icon, .tad-note.high .note-icon { color: var(--yellow); }
.tad-note.warn { background: rgba(201, 154, 46, .12); border-color: var(--yellow); color: var(--yellow); }
.tad-note.warn .note-icon { color: var(--yellow); }

/* ---- 当前工况卡 ---- */
.tad-cond {
  flex: none; background: var(--panel); border: 1px solid var(--border); border-radius: 3px;
  padding: 7px 10px; display: flex; flex-direction: column; gap: 6px;
}
.cond-main { display: flex; align-items: baseline; gap: 6px; }
.cond-tft { font-size: 24px; font-weight: 700; color: var(--text); line-height: 1; }
.cond-unit { font-size: 12px; color: var(--faint); }
.cond-st {
  margin-left: auto; display: inline-flex; align-items: center; gap: 6px;
  font-size: 11.5px; font-weight: 600;
}
.cond-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px;
  border-top: 1px solid var(--border); padding-top: 6px;
}
.cg-item { display: flex; justify-content: space-between; gap: 6px; font-size: 11px; }
.cg-k { color: var(--faint); white-space: nowrap; }
.cg-item b { color: var(--text); font-weight: 600; }
.cond-tip {
  font-size: 10.5px; line-height: 1.5; color: var(--faint);
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 2px; padding: 5px 7px;
}

/* ---- CO2 排放卡（随配料比联动） ---- */
.cond-co2 {
  border-top: 1px solid var(--border); padding-top: 6px;
  display: flex; flex-direction: column; gap: 5px;
}
.co2-main { display: flex; align-items: baseline; gap: 6px; }
.co2-k { font-size: 10.5px; color: var(--faint); font-weight: 600; letter-spacing: 0.4px; white-space: nowrap; }
.co2-val { font-size: 20px; font-weight: 700; color: var(--text); line-height: 1; }
.co2-unit { font-size: 11px; color: var(--faint); white-space: nowrap; }
.co2-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 3px 10px;
}
.co2-tip {
  font-size: 10px; line-height: 1.45; color: #6f8f7a;
  background: #14231a; border: 1px solid #1f4d33; border-radius: 2px; padding: 4px 7px;
}

/* ---- 炉渣碱度 R₂ 卡（随炉料配比/燃料比/物料成分实时联动） ---- */
.cond-slag {
  border-top: 1px solid #2e2e2e; padding-top: 6px;
  display: flex; flex-direction: column; gap: 5px;
}
.slag-val { font-size: 20px; font-weight: 700; color: #e6e6e6; line-height: 1; }
.slag-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 3px 10px;
}
.cg-wide { grid-column: 1 / -1; }
.slag-tbl {
  display: flex; flex-direction: column; font-size: 10.5px;
  border: 1px solid #2e2e2e; border-radius: 2px; overflow: hidden;
}
.slag-tr {
  display: grid; grid-template-columns: 1.4fr 0.7fr 0.7fr 0.7fr 0.7fr 0.7fr; gap: 6px;
  padding: 3px 7px; color: #b8b8b8;
  border-bottom: 1px solid #262626;
}
.slag-tr:last-child { border-bottom: none; }
.slag-tr span:nth-child(n+2) { text-align: right; font-variant-numeric: tabular-nums; }
.slag-th { background: #2a2d2e; color: #8a8a8a; font-weight: 600; }
.slag-sum { background: #232526; color: #d4d4d4; font-weight: 600; }
.slag-neg { color: #f48771; }

/* ---- 右栏标题（MATLAB 工具条小标题风格） ---- */
.tad-sec-title {
  flex: none; font-size: 10.5px; font-weight: 600; letter-spacing: 0.5px; text-transform: uppercase;
  color: #9d9d9d; padding-bottom: 5px; border-bottom: 1px solid #3c3c3c;
}
.tad-sec-title .sec-sub {
  font-size: 10px; color: #7a7a7a; font-weight: 400; letter-spacing: 0.2px;
  text-transform: none; margin-left: 6px;
}

/* ---- 相对基准变化（每吨铁水口径） ---- */
.tad-delta {
  flex: none; background: #1e1e1e; border: 1px solid #3c3c3c; border-radius: 3px;
  padding: 6px 10px; display: flex; flex-direction: column; gap: 5px;
}
.d-row { display: flex; align-items: baseline; gap: 8px; font-size: 11px; }
.d-k { color: #8a8a8a; white-space: nowrap; width: 56px; flex: none; }
.d-v { color: #c8c8c8; flex: 1; white-space: nowrap; }
.d-delta { font-weight: 600; white-space: nowrap; }
.d-delta.good { color: #89d185; }
.d-delta.bad { color: #f48771; }
.d-delta.flat { color: #8a8a8a; }
.d-foot {
  font-size: 10px; line-height: 1.45; color: #7a7a7a;
  border-top: 1px dashed #2e2e2e; padding-top: 4px;
}

/* ---- 灵敏度表 ---- */
.tad-table { width: 100%; border-collapse: collapse; flex: none; font-size: 11px; }
.tad-table th {
  text-align: left; padding: 4px 8px; color: var(--faint); font-weight: 600;
  border-bottom: 1px solid var(--border); white-space: nowrap;
}
.tad-table td { padding: 5px 8px; border-bottom: 1px solid var(--border); color: var(--text); white-space: nowrap; }
.tad-table tbody tr { cursor: pointer; }
.tad-table tbody tr:hover { background: var(--accent-l); }
.tad-table tr.on td { background: var(--sel); color: var(--text); }
.tad-table tr.on .c-name { color: var(--accent); }
.tad-table .c-name { font-weight: 600; color: var(--accent); }
.tad-table .trend { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; }
.tad-table .td-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; }
.tad-table .trend.up { color: var(--red); }
.tad-table .trend.up .td-dot { background: var(--red); }
.tad-table .trend.down { color: var(--accent); }
.tad-table .trend.down .td-dot { background: var(--accent); }
.tad-table .trend.flat { color: var(--faint); }
.tad-table .trend.flat .td-dot { background: var(--faint); }

.tad-ax-desc {
  flex: none; font-size: 11px; line-height: 1.5; color: var(--muted);
  padding: 6px 9px; background: var(--panel); border: 1px solid var(--border); border-radius: 3px;
}

/* ---- 策略建议 ---- */
.tad-advice { flex: none; }
.tad-advice ul { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 5px; }
.tad-advice li {
  position: relative; display: flex; gap: 7px; align-items: flex-start;
  padding: 6px 9px; border-radius: 3px; font-size: 11px; line-height: 1.5;
  border: 1px solid var(--border);
}
.tad-advice .ad-dot { width: 6px; height: 6px; border-radius: 50%; margin-top: 5px; flex: none; }
.tad-advice .lv-g { background: rgba(46, 158, 99, .12); border-color: var(--green); color: var(--green); }
.tad-advice .lv-g .ad-dot { background: var(--green); }
.tad-advice .lv-w { background: rgba(192, 115, 42, .12); border-color: var(--orange); color: var(--orange); }
.tad-advice .lv-w .ad-dot { background: var(--yellow); }

.mono { font-family: var(--mono); }
</style>
