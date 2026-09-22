<!-- ============ AI 群控（AGC）============
     两级结构：
       ① 模型库 —— 以卡片形式列出所有已设计的算法模型，支持新建（规则 / 强化学习 / 粒子群）
       ② 编排   —— 进入某个模型后：左栏自上而下为「可调设备 → 传感设备」（可拖入画布），
                   右栏为该算法自己的编排体，右上角「运行」即按编排的算法执行。
     运行时不做整页的实时观测图表，改为点击左侧 / 画布 / 编排条上的任意模块查看它的实时值。
     规则：可调（橙）· 传感（青）· 条件（紫），只有可调模块可以设定数值。 -->
<template>
  <div class="agc">
    <!-- ══════════ ① 模型库 ══════════ -->
    <section v-if="page === 'lib'" class="agc-lib">
      <p class="lib-tip">{{ t('每个模型是一套独立的群控算法：新建后进入编排，编排完成点右上角「运行」即按该算法执行；运行中点击任意模块可查看实时值。') }}</p>

      <div class="lib-grid">
        <article v-for="m in designs" :key="m.id" class="mcard" :class="['alg-' + m.alg, { live: isRunning(m.id) }]" @click="enter(m)">
          <div class="mc-top">
            <span class="mc-ic">{{ algIco(m.alg) }}</span>
            <span class="mc-nm">{{ m.name }}</span>
            <span class="mc-tg" :class="m.alg">{{ algLabel(m.alg) }}</span>
          </div>
          <div class="mc-bd">
            <div v-for="s in statOf(m)" :key="s.k" class="mc-st"><em>{{ s.k }}</em><b class="mono">{{ s.v }}</b></div>
          </div>
          <div class="mc-ft">
            <span class="mono dim">{{ shortTs(m.ts) }}</span>
            <span class="mc-ops">
              <button class="lk" @click.stop="renameModel(m)">{{ t('重命名') }}</button>
              <button class="lk" @click.stop="dupModel(m)">{{ t('复制') }}</button>
              <button class="lk danger" @click.stop="delModel(m)">{{ t('删除') }}</button>
            </span>
          </div>
          <i v-if="isRunning(m.id)" class="mc-live">{{ t('运行中') }}</i>
        </article>

        <button class="mcard new" @click="openNew">
          <span class="plus">+</span>
          <span class="nt">{{ t('新建模型') }}</span>
          <span class="nd">{{ t('规则 / 强化学习 / 粒子群') }}</span>
        </button>
      </div>

      <div v-if="!designs.length" class="lib-empty">
        <p class="t1">{{ t('还没有算法模型') }}</p>
        <p class="t2">{{ t('点击「+ 新建模型」，选择规则 / 强化学习 / 粒子群，即可进入编排。') }}</p>
      </div>
    </section>

    <!-- ══════════ ② 编排 ══════════ -->
    <div v-else-if="cur" class="agc-edit">
      <div class="ed-top">
        <button class="btn ghost" @click="back">{{ '← ' + t('模型库') }}</button>
        <b class="ed-nm">{{ cur.name }}</b>
        <span class="mc-tg" :class="cur.alg">{{ algLabel(cur.alg) }}</span>
        <span class="hd-sp"></span>
        <span class="ed-st" :class="{ on: running }"><i class="dot"></i>{{ runStateTxt }}</span>
        <template v-if="cur.alg === 'rule'">
          <em class="lb2">{{ t('周期') }}</em>
          <select v-model.number="cur.period" class="sel xs" :disabled="running">
            <option :value="1">1s</option>
            <option :value="2">2s</option>
            <option :value="5">5s</option>
            <option :value="10">10s</option>
          </select>
        </template>
        <button class="btn" :class="running ? 'stop' : 'primary'" :disabled="!canRun" :title="runTip" @click="toggleRun">
          {{ running ? t('停止') : t('运行') }}
        </button>
      </div>

      <div class="ed-bd">
        <!-- ─────── 左栏 ─────── -->
        <aside class="agc-aside">
          <div class="agc-hd">
            <span class="hd-sub mono">{{ selAdj.length }}{{ t('可调') }} · {{ selSen.length }}{{ t('传感') }}</span>
            <span class="hd-sp"></span>
            <span class="hd-sub">{{ t('勾选即在右侧编排画布生成模块') }}</span>
          </div>

          <!-- ① 可调设备 -->
          <section class="pnl">
            <div class="pnl-hd" @click="fold.adj = !fold.adj">
              <i class="caret" :class="{ on: !fold.adj }">▸</i>
              <span class="ph-t">{{ t('① 可调设备') }}</span>
              <em class="cnt mono">{{ selAdj.length }}/{{ adjList.length }}</em>
              <span class="hd-ops">
                <button class="lk" @click.stop="pickAllAdj">{{ t('全选') }}</button>
                <button class="lk" @click.stop="clearAdj">{{ t('清空') }}</button>
              </span>
            </div>
            <div v-show="!fold.adj" class="pnl-bd">
              <p v-if="isRule" class="emp drag-tip">{{ t('规则控制：勾选即在右侧规则画布生成模块（可调可设定数值）。') }}</p>
              <p v-if="!adjList.length" class="emp">{{ t('当前场景没有可调设备（可调设备才能作为被控对象）。') }}</p>
              <div v-for="d in adjList" :key="d.id" class="dev" :class="{ on: has(selAdj, d.id) }">
                <div class="dev-hd" @click="toggle(selAdj, d.id)">
                  <span class="cbx"><i v-if="has(selAdj, d.id)">✓</i></span>
                  <span class="nm">{{ d.label }}<em>{{ d.unitName }}</em></span>
                  <b class="mono val">{{ fmt(curSp(d.id)) }}<i>{{ spUnit(d.id) }}</i></b>
                  <span v-if="boundSensors(d.id).length" class="tag pid" :title="t('已绑定传感设备，由 PID 自动调控')">PID</span>
                </div>
                <div v-if="has(selAdj, d.id)" class="dev-bd">
                  <div class="sp-row">
                    <input class="rng" type="range" :min="spMin(d.id)" :max="spMax(d.id)" :step="spStepV(d.id)"
                           :value="curSp(d.id)" :disabled="autoCtl(d.id)" @input="onSpSlide(d.id, $event)" />
                    <input class="num" type="number" :value="curSp(d.id)" :step="spStepV(d.id)"
                           :disabled="autoCtl(d.id)" @change="onSpNum(d.id, $event)" />
                    <i class="u">{{ spUnit(d.id) }}</i>
                  </div>
                  <div class="meta">
                    <span>{{ t('量程') }} <b class="mono">{{ fmt(spMin(d.id)) }} ~ {{ fmt(spMax(d.id)) }}</b></span>
                    <span v-if="autoCtl(d.id)" class="tag on">{{ t('PID 自动调控中') }}</span>
                    <span v-else class="tag">{{ t('手动设定') }}</span>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- ② 传感设备 -->
          <section class="pnl">
            <div class="pnl-hd" @click="fold.sen = !fold.sen">
              <i class="caret" :class="{ on: !fold.sen }">▸</i>
              <span class="ph-t">{{ t('② 传感设备') }}</span>
              <em class="cnt mono">{{ selSen.length }}/{{ senList.length }}</em>
              <span class="hd-ops">
                <button class="lk" @click.stop="pickAllSen">{{ t('全选') }}</button>
                <button class="lk" @click.stop="clearSen">{{ t('清空') }}</button>
              </span>
            </div>
            <div v-show="!fold.sen" class="pnl-bd">
              <p v-if="isRule" class="emp drag-tip">{{ t('规则控制：勾选即在右侧规则画布生成传感模块，作为条件判定的输入。') }}</p>
              <p v-if="!senList.length" class="emp">{{ t('当前场景没有传感设备。') }}</p>
              <div v-for="s in senList" :key="s.id" class="dev" :class="{ on: has(selSen, s.id) }">
                <div class="dev-hd" @click="toggle(selSen, s.id)">
                  <span class="cbx"><i v-if="has(selSen, s.id)">✓</i></span>
                  <span class="nm">{{ s.label }}<em>{{ s.unitName }}</em></span>
                  <b class="mono val">{{ fmt(liveOf(s.id)) }}<i>{{ s.unit || '' }}</i></b>
                </div>
                <div v-if="has(selSen, s.id)" class="dev-bd">
                  <div class="row">
                    <em>{{ t('绑定可调设备') }}</em>
                    <select :value="bindOf[s.id] || ''" @change="setBind(s.id, $event.target.value)">
                      <option value="">{{ t('未绑定（只显示读数）') }}</option>
                      <option v-for="a in adjList" :key="a.id" :value="a.id">{{ a.label }} · {{ a.unitName }}</option>
                    </select>
                  </div>
                  <template v-if="bindOf[s.id] && isLoopSensor(s.id)">
                    <div class="row">
                      <em>{{ t('目标值') }}</em>
                      <input class="num" type="number" :value="targetOf(s.id)" :step="spStepS(s.id)" @change="setTarget(s.id, $event.target.value)" />
                      <i class="u">{{ s.unit || '' }}</i>
                    </div>
                    <div class="row st">
                      <span class="kv"><em>{{ t('观测') }}</em><b class="mono raw">{{ fmt(lastRawOf(s.id)) }}</b></span>
                      <span class="kv"><em>{{ t('滤波后') }}</em><b class="mono ekf">{{ fmt(lastEkfOf(s.id)) }}</b></span>
                      <span class="badge" :class="badgeCls(s.id)">{{ badgeTxt(s.id) }}</span>
                    </div>
                  </template>
                  <div v-else-if="bindOf[s.id]" class="row rd">
                    <em>{{ t('实时读数') }}</em>
                    <b class="mono">{{ fmt(liveOf(s.id)) }}</b><i class="u">{{ s.unit || '' }}</i>
                    <span class="hintx">{{ t('辅助观测（该可调设备已有主控传感设备）') }}</span>
                  </div>
                  <div v-else class="row rd">
                    <em>{{ t('实时读数') }}</em>
                    <b class="mono">{{ fmt(liveOf(s.id)) }}</b><i class="u">{{ s.unit || '' }}</i>
                    <span class="hintx">{{ t('未绑定：仅显示实时读数') }}</span>
                  </div>
                </div>
              </div>
            </div>
          </section>
        </aside>

        <!-- ─────── 右栏：该算法的编排体 ─────── -->
        <main class="agc-main">
          <!-- 规则：可编排画布（点选画布卡片，实时值直接显示在卡片下方） -->
          <section v-if="isRule" class="card rg">
            <div class="card-hd">
              <span class="ct">{{ t('规则编排') }}</span>
              <span class="cs">{{ t('可调 / 传感 → if-elif-else → 下游模块设置') }}</span>
              <span class="ch-ops mono">
                <span class="lg-i adj">■ {{ t('可调') }}</span>
                <span class="lg-i sen">■ {{ t('传感') }}</span>
                <span class="lg-i ifn">■ {{ t('条件') }}</span>
              </span>
            </div>
            <RuleFlowEditor :key="cur.id" class="rf-fill" :graph="cur.graph" :running="running" :period="cur.period"
                            @canvas-change="syncSelFromGraph" />
          </section>

          <!-- 强化学习：训练控制台 + 奖励 + 版本 -->
          <template v-else-if="cur.alg === 'rl'">
            <section class="card">
              <div class="card-hd">
                <span class="ct">{{ t('训练控制台') }}</span>
                <span class="cs mono">{{ loops.length }} {{ t('回路') }} · {{ t('决策维度') }} {{ loops.length * 4 }}</span>
                <span class="ch-ops">
                  <select v-model.number="runHz" class="sel xs" :disabled="sampling">
                    <option :value="1">1s</option>
                    <option :value="0.5">2s</option>
                    <option :value="0.2">5s</option>
                  </select>
                  <button class="btn" :class="{ primary: !sampling, stop: sampling }" @click="toggleSample">
                    {{ sampling ? t('停止采集') : t('开始采集') }}
                  </button>
                  <span class="tstate" :class="{ on: trainBusy }"><i class="dot"></i>{{ trainStateTxt }}</span>
                </span>
              </div>
              <div class="bar">
                <button class="btn primary" :disabled="trainBusy || !canTrain" @click="startTrain">{{ t('开始训练') }}</button>
                <button class="btn stop" :disabled="!trainBusy" @click="stopTrain">{{ t('停止') }}</button>
                <label class="chk" :title="t('对观测做滤波后再作为控制/训练输入')">
                  <input type="checkbox" v-model="useFilter" />{{ t('滤波') }}
                </label>
                <label class="chk" :title="t('由 PID 自动调节可调设备设定值（关闭则保持手动设定）')">
                  <input type="checkbox" v-model="ctlOn" />{{ t('调控 PID') }}
                </label>
                <button class="btn ghost" @click="fold.hp = !fold.hp">{{ t('超参数') }}{{ fold.hp ? ' ▸' : ' ▾' }}</button>
              </div>
              <div class="hp" v-show="!fold.hp">
                <div class="hp-row">
                  <label class="f"><em>{{ t('迭代轮次') }}</em><input class="num w56" type="number" min="5" max="300" step="5" v-model.number="maxIter" :disabled="trainBusy" /></label>
                  <label class="f"><em>{{ t('学习率') }} lr</em><input class="num w56" type="number" step="0.001" min="0" v-model.number="ppoLr" :disabled="trainBusy" /></label>
                  <label class="f"><em>{{ t('裁剪') }} ε</em><input class="num w56" type="number" step="0.05" min="0" max="1" v-model.number="ppoClip" :disabled="trainBusy" /></label>
                  <label class="f"><em>{{ t('折扣') }} γ</em><input class="num w56" type="number" step="0.01" min="0" max="1" v-model.number="ppoGamma" :disabled="trainBusy" /></label>
                  <label class="f"><em>GAE λ</em><input class="num w56" type="number" step="0.01" min="0" max="1" v-model.number="ppoLam" :disabled="trainBusy" /></label>
                  <label class="f"><em>{{ t('熵系数') }}</em><input class="num w56" type="number" step="0.005" min="0" v-model.number="ppoEnt" :disabled="trainBusy" /></label>
                  <label class="f"><em>{{ t('更新轮次') }} K</em><input class="num w56" type="number" step="1" min="1" v-model.number="ppoK" :disabled="trainBusy" /></label>
                  <label class="f"><em>{{ t('每轮轨迹') }}</em><input class="num w56" type="number" step="1" min="1" v-model.number="ppoEps" :disabled="trainBusy" /></label>
                  <label class="f"><em>{{ t('探索') }} σ₀</em><input class="num w56" type="number" step="0.05" min="0" v-model.number="ppoSig" :disabled="trainBusy" /></label>
                  <label class="f"><em>{{ t('环境扰动') }} d</em><input class="num w56" type="number" step="0.5" min="0" v-model.number="distPct" :disabled="trainBusy" /><i class="u">%</i></label>
                  <label class="f" :title="t('训练时对辨识出的模型参数施加随机扰动，避免策略过拟合模型误差')"><em>{{ t('模型不确定度') }}</em><input class="num w56" type="number" step="1" min="0" max="50" v-model.number="modelPct" :disabled="trainBusy" /><i class="u">%</i></label>
                  <label class="f" :title="t('无足够数据时使用的保守纯滞后估计（秒），现场可按经验填写')"><em>{{ t('先验滞后') }} θ₀</em><input class="num w56" type="number" step="1" min="0" max="600" v-model.number="priTheta" :disabled="trainBusy" /><i class="u">s</i></label>
                </div>
                <div class="hp-row obj">
                  <span class="lb">{{ t('奖励') }} r = −( w₁|e| + w₂|Δe| + w₃·{{ t('超调') }} + w₄·{{ t('功耗') }} )</span>
                  <label class="f"><em>w₁ {{ t('误差') }}</em><input class="num w56" type="number" step="0.1" min="0" v-model.number="rwErr" :disabled="trainBusy" /></label>
                  <label class="f"><em>w₂ {{ t('波动') }}</em><input class="num w56" type="number" step="0.05" min="0" v-model.number="rwDe" :disabled="trainBusy" /></label>
                  <label class="f"><em>w₃ {{ t('超调') }}</em><input class="num w56" type="number" step="0.1" min="0" v-model.number="rwOv" :disabled="trainBusy" /></label>
                  <label class="f"><em>w₄ {{ t('功耗') }}</em><input class="num w56" type="number" step="0.1" min="0" v-model.number="rwPow" :disabled="trainBusy" /></label>
                </div>
              </div>
              <div class="bar mv">
                <em class="lb2">{{ t('模型版本') }}</em>
                <select v-model="activeVer" class="sel" :disabled="!versions.length">
                  <option v-for="v in versions" :key="v.id" :value="v.id">{{ v.name }} · {{ shortTs(v.ts) }} · r {{ fmtSmall(v.reward) }}</option>
                </select>
                <button class="btn" :disabled="!activeVer || !hasVer(activeVer)" @click="applyVer(activeVer)">{{ t('应用版本') }}</button>
                <button class="btn ghost" :disabled="!activeVer || !hasVer(activeVer)" @click="delVer(activeVer)">{{ t('删除') }}</button>
                <span class="sep"></span>
                <em class="lb2">{{ t('自动训练') }}</em>
                <select v-model="autoMode" class="sel xs">
                  <option value="off">{{ t('关闭') }}</option>
                  <option value="1h">{{ t('每 1 小时') }}</option>
                  <option value="6h">{{ t('每 6 小时') }}</option>
                  <option value="daily">{{ t('每天') }}</option>
                </select>
                <input v-if="autoMode === 'daily'" class="num tm" type="time" v-model="autoAt" />
                <span class="nx">{{ nextAutoTxt }}</span>
              </div>
            </section>

            <section class="card grow">
              <div class="card-hd">
                <span class="ct">{{ t('训练奖励') }}</span>
                <span class="cs">{{ t('每轮迭代的平均回合奖励（越大越好）') }}</span>
                <span class="ch-ops mono">
                  <b class="rw">{{ fmtSmall(lastReward) }}</b>
                  <span class="dim">/ {{ t('最佳') }} <b class="best">{{ fmtSmall(bestReward) }}</b></span>
                  <span v-if="baseReward != null" class="dim">· {{ t('基线') }} {{ fmtSmall(baseReward) }}</span>
                </span>
              </div>
              <div class="rw-wrap">
                <svg v-if="rwPath" class="rw-svg" :viewBox="`0 0 ${RW.W} ${RW.H}`" preserveAspectRatio="none">
                  <line v-for="y in RW.GRID" :key="'g' + y" class="grid" :x1="0" :x2="RW.W" :y1="y" :y2="y" />
                  <line v-if="baseY != null" class="base" :x1="0" :x2="RW.W" :y1="baseY" :y2="baseY" />
                  <polyline class="cv" :points="rwPath" />
                </svg>
                <div v-else class="cempty sm">
                  <p class="t1">{{ t('尚未训练') }}</p>
                  <p class="t2">{{ t('绑定传感设备与可调设备形成回路后，点击「运行」，这里显示奖励随迭代的变化。') }}</p>
                </div>
                <div class="rw-ax" v-if="rwPath">
                  <span>1</span><span>{{ t('迭代') }} {{ curve.length }}</span>
                </div>
              </div>
            </section>

            <section class="card">
              <div class="card-hd">
                <span class="ct">{{ t('模型版本') }}</span>
                <span class="cs">{{ t('每轮训练自动存为新版本，可随时回退应用') }}</span>
              </div>
              <div class="vtb">
                <div class="vtr hd">
                  <span>{{ t('版本') }}</span><span>{{ t('时间') }}</span><span>{{ t('算法') }}</span>
                  <span>{{ t('迭代') }}</span><span>{{ t('奖励') }}</span><span>{{ t('状态') }}</span>
                </div>
                <div v-if="!versions.length" class="vempty">{{ t('暂无模型版本') }}</div>
                <div v-for="v in versions" :key="v.id" class="vtr" :class="{ on: v.id === activeVer, cur: v.id === curVerId }"
                     @click="activeVer = v.id">
                  <span class="mono">{{ v.name }}</span>
                  <span class="mono dim">{{ fullTs(v.ts) }}</span>
                  <span>{{ v.alg }}</span>
                  <span class="mono">{{ v.iters }}</span>
                  <span class="mono rw">{{ fmtSmall(v.reward) }}</span>
                  <span v-if="v.id === curVerId" class="tag on">{{ t('已应用') }}</span>
                  <span v-else class="tag">{{ t('历史') }}</span>
                </div>
              </div>
              <div class="vdim" v-if="activeVerObj">
                <div class="vdim-h">{{ t('版本') }} {{ activeVerObj.name }} · {{ t('输出（动作）') }}</div>
                <div class="vrow" v-for="(d, i) in activeVerObj.dims" :key="i">
                  <span class="rn">{{ i + 1 }}</span>
                  <span class="rl">{{ d.adjLabel }} ← {{ d.senLabel }}</span>
                  <span class="rp mono">Δu {{ fmtSmall(d.du) }} · Kp {{ fmtSmall(d.kp) }} · Ki {{ fmtSmall(d.ki) }} · Kd {{ fmtSmall(d.kd) }}</span>
                </div>
              </div>
            </section>
          </template>

          <!-- 粒子群：在线寻优 -->
          <template v-else>
            <section class="card">
              <div class="card-hd">
                <span class="ct">{{ t('粒子群编排') }}</span>
                <span class="cs">{{ t('优化变量（可调设备）→ 目标（传感设备趋近目标值）') }}</span>
              </div>
              <PsoTuner :cfg="cur.pso" :running="running" @update:running="onPsoRun" />
            </section>
          </template>

        </main>
      </div>
    </div>

    <!-- ══════════ 新建模型 ══════════ -->
    <div v-if="newOpen" class="mk-mask">
      <div class="mk-dlg">
        <div class="mk-hd">
          <b>{{ t('新建模型') }}</b>
          <button class="mk-x" @click="newOpen = false">✕</button>
        </div>
        <div class="mk-bd">
          <label class="mk-f">
            <em>{{ t('模型名称') }}</em>
            <input class="mk-in" v-model.trim="newName" :placeholder="t('例如：冷却水分段调控')" @keyup.enter="createModel" />
          </label>
          <div class="mk-t">{{ t('算法类型') }}</div>
          <div class="mk-types">
            <button v-for="a in ALG_TYPES" :key="a.id" class="mk-tp" :class="[a.id, { on: newAlg === a.id }]" @click="newAlg = a.id">
              <i class="tp-ic">{{ a.ico }}</i>
              <b>{{ a.label }}</b>
              <span>{{ a.desc }}</span>
            </button>
          </div>
        </div>
        <div class="mk-ft">
          <button class="btn ghost" @click="newOpen = false">{{ t('取消') }}</button>
          <button class="btn primary" @click="createModel">{{ t('新建并进入编排') }}</button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import { createPid, createEkf2 } from '../utils/control'
import { createPpoAgent, computeGae, standardize, randn } from '../utils/rl'
import { DEVICE_MAP } from '../data/flowLibrary'
// 附加可调设备（变频器 / 半导体制冷电源…）不在工艺可调设备表内，量程兜底取通用附加设备库
import { ADJUSTABLE_MAP } from '../data/attachLibrary'
import RuleFlowEditor from './RuleFlowEditor.vue'
import PsoTuner from './PsoTuner.vue'
import { t } from '../i18n'

const store = useSimStore()

const props = defineProps({
  devices: { type: Array, default: () => [] },
  curId: { type: String, default: null },
})

// ==================== 设备候选 ====================
// 可调设备 = 被控对象（可写设定值）；传感设备 = 观测来源（只读）
const all = computed(() => store.allDevices || [])
const adjList = computed(() => all.value.filter((d) => d.adjustable))
const senList = computed(() => all.value.filter((d) => !d.adjustable))

function findInfo(id) {
  if (!id) return null
  try { return store.findDevice(id) || null } catch (e) { return null }
}
function findDev(id) {
  const i = findInfo(id)
  return i ? i.device : null
}
/** 设定值量程（来自设备模板）；附加可调设备（ext::…）取通用附加设备库 */
function spCfg(id) {
  const d = findDev(id)
  if (!d) return null
  const tmpl = d.type ? DEVICE_MAP[d.type] : null
  if (tmpl && tmpl.setpoint) return tmpl.setpoint
  const at = d.type ? ADJUSTABLE_MAP[d.type] : null
  return (at && at.setpoint) || null
}
function spMin(id) { const c = spCfg(id); return c ? Number(c.min) : 0 }
function spMax(id) { const c = spCfg(id); return c ? Number(c.max) : 100 }
function spDef(id) { const c = spCfg(id); return c ? Number(c.def) : 0 }
function spUnit(id) { const c = spCfg(id); return (c && (c.unit || c.label)) || '' }
function spStepV(id) {
  const r = spMax(id) - spMin(id)
  if (r >= 1000) return 10
  if (r >= 100) return 1
  if (r >= 10) return 0.1
  return 0.01
}
function spStepS(id) {
  const v = Math.abs(Number(liveOf(id)) || 1)
  if (v >= 1000) return 10
  if (v >= 100) return 1
  if (v >= 10) return 0.5
  return 0.1
}
/** 当前设定值（store 覆盖 → 设备实例 → 模板默认） */
function curSp(id) {
  const d = findDev(id)
  if (!d) return null
  if (store.deviceSetpoints[id] != null) return Number(store.deviceSetpoints[id])
  if (d.setpoint != null && Number.isFinite(Number(d.setpoint))) return Number(d.setpoint)
  return spDef(id)
}
function setSp(id, v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return
  // 统一入口：本地设定；编排中已绑定数据源设备可写点位的可变设备会自动下发写入
  store.setExtSetpoint(id, Math.min(spMax(id), Math.max(spMin(id), n)))
}
/** 滑杆 / 数字框直调设定值（PID 自动调控时控件已禁用） */
function onSpSlide(id, e) { setSp(id, e.target.value) }
function onSpNum(id, e) { setSp(id, e.target.value) }
/** 实时读数：live → 历史末点 → 设备字段 */
function liveOf(id) {
  if (!id) return null
  const lv = store.deviceLiveOf(id)
  if (lv != null) return Number(lv)
  const h = store.deviceHistoryOf(id)
  if (h && h.length) return Number(h[h.length - 1].v)
  const d = findDev(id)
  if (d && d.live != null) return Number(d.live)
  if (d && d.reading != null) return Number(d.reading)
  return null
}
function devName(id) { const d = findDev(id); return d ? (d.label || d.id) : (id || '—') }

// ==================== 选择 / 绑定 ====================
const selAdj = ref([])                 // 已选可调设备 id
const selSen = ref([])                 // 已选传感设备 id
const bindOf = reactive({})            // 传感设备 id -> 可调设备 id（'' = 未绑定）
const spOf = reactive({})              // 传感设备 id -> 目标值（PID 设定）
const fold = reactive({ adj: false, sen: false, alg: false, hp: true })

function has(arr, id) { return arr.includes(id) }
function toggle(arr, id) {
  const i = arr.indexOf(id)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(id)
  applySelToGraph()   // 勾选变化 → 编排画布同步生成 / 移除模块
}
function pickAllAdj() { selAdj.value = adjList.value.map((d) => d.id); applySelToGraph() }
function clearAdj() { selAdj.value = []; applySelToGraph() }
function pickAllSen() { selSen.value = senList.value.map((d) => d.id); applySelToGraph() }
function clearSen() { selSen.value = []; applySelToGraph() }

// ─────────── 左栏勾选 ⇄ 规则画布模块 ───────────
// 规则编排不再靠拖拽：左栏勾选的设备自动成为画布上的模块，取消勾选即移除（含其连线）。
// 反向：画布里新增（工具条 / 复制粘贴）或删除模块时，画布上报 canvas-change，左栏勾选随之同步。
function mkDevNode(kind, devId) {
  const d = findDev(devId) || {}
  const ns = (cur.value && cur.value.graph && cur.value.graph.nodes) || []
  const y0 = 40
  let y = y0
  for (const n of ns) if (n.kind === kind) y = Math.max(y, (Number(n.y) || 0) + 108)
  if (y > 1500) y = y0 + (ns.filter((n) => n.kind === kind).length % 12) * 108
  return {
    id: kind + '_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 5),
    kind,
    devId,
    label: d.label || devName(devId),
    unit: kind === 'adj' ? (spUnit(devId) || d.unit || '') : (d.unit || ''),
    unitName: d.unitName || '',
    value: kind === 'adj' ? Number(curSp(devId) != null ? curSp(devId) : 0) : null,
    x: kind === 'sen' ? 48 : 600,
    y,
  }
}
/** 勾选 → 画布：补齐缺失模块，移除未勾选的模块 */
function applySelToGraph() {
  const m = cur.value
  if (!m || m.alg !== 'rule') return
  const g = m.graph
  if (!g.nodes) g.nodes = []
  if (!g.edges) g.edges = []
  for (const id of selAdj.value) {
    if (!g.nodes.some((n) => n.devId === id)) g.nodes.push(mkDevNode('adj', id))
  }
  for (const id of selSen.value) {
    if (!g.nodes.some((n) => n.devId === id)) g.nodes.push(mkDevNode('sen', id))
  }
  for (let i = g.nodes.length - 1; i >= 0; i--) {
    const n = g.nodes[i]
    if (n.kind !== 'adj' && n.kind !== 'sen') continue
    const set = n.kind === 'adj' ? selAdj.value : selSen.value
    if (set.includes(n.devId)) continue
    g.nodes.splice(i, 1)
    for (let k = g.edges.length - 1; k >= 0; k--) {
      if (g.edges[k].from === n.id || g.edges[k].to === n.id) g.edges.splice(k, 1)
    }
    for (const x of g.nodes) {
      if (x.kind !== 'if') continue
      for (const b of (x.branches || [])) if (b.src === n.id) b.src = ''
    }
  }
}
/** 画布 → 勾选：画布上增删模块（含撤销/重做）后，左栏勾选状态跟随 */
function syncSelFromGraph() {
  const m = cur.value
  if (!m || m.alg !== 'rule') return
  const ns = (m.graph && m.graph.nodes) || []
  const a = []
  const s = []
  for (const n of ns) {
    if (!n || !n.devId || !findDev(n.devId)) continue
    if (n.kind === 'adj') { if (!a.includes(n.devId)) a.push(n.devId) }
    else if (n.kind === 'sen') { if (!s.includes(n.devId)) s.push(n.devId) }
  }
  selAdj.value = a
  selSen.value = s
}
function boundSensors(adjId) {
  return selSen.value.filter((s) => bindOf[s] === adjId)
}
/** 绑定：自动给出合理目标值，并清理失效绑定 */
function setBind(senId, adjId) {
  bindOf[senId] = adjId || ''
  if (adjId) {
    const lv = liveOf(senId)
    if (spOf[senId] == null && lv != null) spOf[senId] = Number((Math.abs(lv) * 1.05).toFixed(4))
    if (!has(selAdj, adjId)) { selAdj.value.push(adjId); applySelToGraph() }
  }
  syncRuns()
}
function setTarget(senId, v) {
  const n = Number(v)
  if (!Number.isFinite(n)) return
  spOf[senId] = n
}
function targetOf(senId) {
  if (spOf[senId] != null) return Number(spOf[senId])
  const lv = liveOf(senId)
  return lv == null ? 0 : Number((Math.abs(lv) * 1.05).toFixed(4))
}

// ==================== 控制回路 ====================
// 一个回路 = 一台可调设备 + 一台主控传感设备（其余绑定到同一可调设备的传感器作为辅助观测）
const loops = computed(() => {
  const out = []
  for (const adjId of selAdj.value) {
    const sids = boundSensors(adjId)
    if (!sids.length) continue
    if (!findDev(adjId) || !findDev(sids[0])) continue
    out.push({
      key: adjId,
      adjId,
      senId: sids[0],
      adjLabel: devName(adjId),
      senLabel: devName(sids[0]),
      aux: sids.slice(1),
    })
  }
  return out
})
function loopOfSen(senId) { return loops.value.find((l) => l.senId === senId) || null }
function isLoopSensor(senId) { return !!loopOfSen(senId) }
function loopOfAdj(adjId) { return loops.value.find((l) => l.adjId === adjId) || null }

// 固定增益（由模型版本写入）；未设置则按量程自动整定
const fixGain = reactive({})
function autoGainOf(lp) {
  const sc = Math.max(Math.abs(Number(liveOf(lp.senId) ?? 0)), 1e-3)
  const uRange = Math.max(spMax(lp.adjId) - spMin(lp.adjId), 1e-6)
  return { kp: (0.9 * uRange) / sc, ki: (0.9 * uRange) / sc, kd: (0.15 * uRange) / sc }
}
function gainOf(lp) {
  const f = fixGain[lp.key]
  return f || autoGainOf(lp)
}
const curVerId = ref('')   // 已应用的模型版本

// ==================== 运行（采集 / 调控） ====================
const sampling = ref(false)
const runHz = ref(1)                 // 采集频率 Hz
const useFilter = ref(true)          // 是否滤波（内部 EKF，参数不暴露）
const ctlOn = ref(true)              // 是否由 PID 调控可调设备
const FILT_Q = 0.005                 // 过程噪声（观测尺度比例）
const FILT_R = 0.015                 // 测量噪声（观测尺度比例）
const MAX_PTS = 600

const rt = reactive({ map: {} })     // loopKey -> 运行态
const ctx = new Map()                // loopKey -> { pid, kf }
const identOf = reactive({})         // loopKey -> 在线辨识的过程模型（含纯滞后 delay）
const identDiag = reactive({})       // loopKey -> 辨识诊断（成功率/激励/残差，用于 UI 提示）
let timer = null

function makeRun(lp) {
  const y0 = Number(liveOf(lp.senId) ?? 0)
  const scale = Math.max(Math.abs(y0), 1e-3)
  const u0 = curSp(lp.adjId) != null ? Number(curSp(lp.adjId)) : spDef(lp.adjId)
  ctx.set(lp.key, { pid: createPid({ min: spMin(lp.adjId), max: spMax(lp.adjId) }), kf: createEkf2() })
  return reactive({
    y0, scale, u0, uNow: u0,
    prevT: 0,
    qv: Math.pow(FILT_Q * scale, 2),
    qdv: Math.pow(FILT_Q * scale, 2) * 0.05,
    rv: Math.pow(FILT_R * scale, 2),
    lastRaw: null, lastEkf: null, lastD: null, conv: false,
    ptsRaw: [], ptsEkf: [], ptsU: [],
  })
}
function syncRuns() {
  const alive = {}
  for (const lp of loops.value) {
    alive[lp.key] = 1
    if (!rt.map[lp.key]) rt.map[lp.key] = makeRun(lp)
  }
  for (const k of Object.keys(rt.map)) {
    if (!alive[k]) { delete rt.map[k]; ctx.delete(k); delete identOf[k] }
  }
}
watch(loops, () => syncRuns(), { deep: true })

function toggleSample() {
  if (sampling.value) stopSample()
  else startSample()
}
function startSample() {
  if (!loops.value.length) return
  syncRuns()
  sampling.value = true
  if (timer) clearInterval(timer)
  timer = setInterval(tick, Math.round(1000 / runHz.value))
}
function stopSample() {
  sampling.value = false
  if (timer) { clearInterval(timer); timer = null }
}

function tick() {
  const now = performance.now() / 1000
  const ts = Date.now() / 1000
  for (const lp of loops.value) {
    const r = rt.map[lp.key]
    const c = ctx.get(lp.key)
    if (!r || !c) continue
    if (!r.prevT) r.prevT = now
    const dti = now - r.prevT
    if (!(dti > 0) || dti > 120) { r.prevT = now; continue }
    r.prevT = now

    const live = liveOf(lp.senId)
    if (live == null) { r.lastRaw = null; r.lastEkf = null; r.conv = false; continue }
    const y = Number(live)
    const sp = Number(targetOf(lp.senId)) || 0

    // —— 滤波（关时直接用原始观测）——
    let yF = y
    let dHat = null
    if (useFilter.value) {
      const m = identOf[lp.key] || null
      const dstep = m ? (m.delay || 0) : 0
      // 纯滞后：此刻"正在生效"的，是 dstep 拍之前发出的设定值（ptsU 末尾为上一拍发出的 u）
      const uEff = dstep > 0 && r.ptsU.length >= dstep
        ? Number(r.ptsU[r.ptsU.length - dstep].v)
        : r.uNow
      const est = c.kf.step(y, uEff, {
        a: m ? m.a : 1, b: m ? m.b : 0, c: m ? m.c : 0,
        qT: r.qv, qd: r.qdv, r: r.rv,
      })
      yF = est.t
      dHat = est.d
    }

    // —— PID 调控（关时保持手动设定）——
    if (ctlOn.value) {
      const g = gainOf(lp)
      c.pid.set({ ...g, min: spMin(lp.adjId), max: spMax(lp.adjId) })
      const out = c.pid.step(sp, yF, dti)
      let u = Number.isFinite(out.u) ? out.u : r.u0
      r.uNow = Math.min(spMax(lp.adjId), Math.max(spMin(lp.adjId), u))
      setSp(lp.adjId, r.uNow)
    } else {
      r.uNow = curSp(lp.adjId) != null ? Number(curSp(lp.adjId)) : r.u0
    }

    r.lastRaw = y
    r.lastEkf = useFilter.value ? yF : null
    r.lastD = dHat
    r.conv = Math.abs(sp - (useFilter.value ? yF : y)) <= Math.max(r.scale * 0.01, 1e-6)
    r.ptsRaw.push({ t: ts, v: y })
    r.ptsEkf.push({ t: ts, v: useFilter.value ? yF : null })
    r.ptsU.push({ t: ts, v: r.uNow })
    if (r.ptsRaw.length > MAX_PTS) {
      const cut = r.ptsRaw.length - MAX_PTS
      r.ptsRaw.splice(0, cut); r.ptsEkf.splice(0, cut); r.ptsU.splice(0, cut)
    }
    if (r.ptsRaw.length % 20 === 0) {
      const m = identify(lp)
      if (m) identOf[lp.key] = m
    }
  }
}

// ==================== 观测读数（运行中按模块查看） ====================
function lastRawOf(senId) {
  const lp = loopOfSen(senId)
  const r = lp ? rt.map[lp.key] : null
  return r ? r.lastRaw : liveOf(senId)
}
function lastEkfOf(senId) {
  const lp = loopOfSen(senId)
  const r = lp ? rt.map[lp.key] : null
  if (!r || !useFilter.value) return null
  return r.lastEkf
}
function badgeCls(senId) {
  const lp = loopOfSen(senId)
  const r = lp ? rt.map[lp.key] : null
  if (!sampling.value || !r) return 'idle'
  if (r.lastRaw == null) return 'na'
  return r.conv ? 'ok' : 'busy'
}
function badgeTxt(senId) {
  const lp = loopOfSen(senId)
  const r = lp ? rt.map[lp.key] : null
  if (!sampling.value || !r) return t('就绪')
  if (r.lastRaw == null) return t('无数据')
  return r.conv ? t('已收敛') : t('调节中')
}
function autoCtl(adjId) {
  const lp = loopOfAdj(adjId)
  return !!(lp && ctlOn.value && sampling.value)
}

// ==================== 过程模型：由在线实时数据辨识 ====================
// FOPDT（First Order Plus Dead Time，一阶惯性 + 纯滞后）离散模型：
//   y[k+1] = a·y[k] + b·u[k−d] + c
//   a = exp(−dt/τ)：τ 时间常数（惯性，越大越迟钝）
//   b = K·(1−a)   ：K 静态增益（单位调节量最终引起的被控量变化）
//   d 纯滞后拍数  ：θ = d·dt，动作发出到被控量"开始"响应的等待时间
// 必须辨识纯滞后：若模型无滞后而实际有，模型会让智能体误以为"加大增益立刻见效"，
// 从而学出过于激进的增益，真机上线即振荡，而模型内评估指标却很好看——
// 这是 model-based（基于模型）强化学习最典型的翻车方式。
const IDENT_MIN = 12
const DELAY_MAX = 60          // 纯滞后搜索上限（拍）
const DELAY_GAIN = 1.05       // 滞后选型：残差不超过全局最优 1.05 倍的最小滞后即为首选（防混叠）
const EXC_RATIO = 0.01        // 激励充分性：u 的波动标准差需达到量程的 1%
function solve3(M, v) {
  const A = [M[0].slice(), M[1].slice(), M[2].slice()]
  const b = v.slice()
  for (let c = 0; c < 3; c++) {
    let p = c
    for (let rr = c + 1; rr < 3; rr++) if (Math.abs(A[rr][c]) > Math.abs(A[p][c])) p = rr
    if (Math.abs(A[p][c]) < 1e-12) return null
    const tr = A[c]; A[c] = A[p]; A[p] = tr
    const tb = b[c]; b[c] = b[p]; b[p] = tb
    for (let rr = 0; rr < 3; rr++) {
      if (rr === c) continue
      const f = A[rr][c] / A[c][c]
      for (let k = c; k < 3; k++) A[rr][k] -= f * A[c][k]
      b[rr] -= f * b[c]
    }
  }
  return [b[0] / A[0][0], b[1] / A[1][1], b[2] / A[2][2]]
}
/** 给定纯滞后拍数 dstep，最小二乘拟合 a/b/c 并给出拟合质量；不可用返回 null */
function fitDelay(r, dstep) {
  const n = Math.min(r.ptsRaw.length, r.ptsU.length)
  let Syy = 0, Syu = 0, Sy1 = 0, Suu = 0, Su1 = 0, S11 = 0, Syt = 0, Sut = 0, St1 = 0
  const acc = (yk, uk, yn) => {
    Syy += yk * yk; Syu += yk * uk; Sy1 += yk; Suu += uk * uk; Su1 += uk; S11 += 1
    Syt += yk * yn; Sut += uk * yn; St1 += yn
  }
  for (let k = dstep; k < n - 1; k++) {
    const yk = Number(r.ptsRaw[k].v), uk = Number(r.ptsU[k - dstep].v), yn = Number(r.ptsRaw[k + 1].v)
    if (!Number.isFinite(yk) || !Number.isFinite(uk) || !Number.isFinite(yn)) continue
    acc(yk, uk, yn)
  }
  if (S11 < IDENT_MIN) return null
  const sol = solve3([[Syy, Syu, Sy1], [Syu, Suu, Su1], [Sy1, Su1, S11]], [Syt, Sut, St1])
  if (!sol) return null
  const [a, b, c] = sol
  if (!(a > 0.02 && a < 0.9995) || !Number.isFinite(b) || !Number.isFinite(c)) return null
  // 均方残差：在有效样本上重算，作为不同滞后之间可比的选型准则
  let sse = 0
  for (let k = dstep; k < n - 1; k++) {
    const yk = Number(r.ptsRaw[k].v), uk = Number(r.ptsU[k - dstep].v), yn = Number(r.ptsRaw[k + 1].v)
    if (!Number.isFinite(yk) || !Number.isFinite(uk) || !Number.isFinite(yn)) continue
    const pr = a * yk + b * uk + c
    sse += (yn - pr) * (yn - pr)
  }
  const uMean = Su1 / S11
  return { a, b, c, m: S11, sse, uVar: Math.max(0, Suu / S11 - uMean * uMean) }
}

function identify(lp) {
  const r = rt.map[lp.key]
  if (!r) return null
  const n = Math.min(r.ptsRaw.length, r.ptsU.length)
  if (n < IDENT_MIN) {
    identDiag[lp.key] = { ok: false, msg: t('样本不足') + `（${n}/${IDENT_MIN}）` }
    return null
  }
  const dt = Math.max(0.1, (r.ptsRaw[n - 1].t - r.ptsRaw[0].t) / (n - 1))
  const uRange = Math.max(spMax(lp.adjId) - spMin(lp.adjId), 1e-6)
  // 滞后越大可用样本越少，上限留出一半样本保证可辨识
  const dMax = Math.min(DELAY_MAX, Math.max(0, Math.floor((n - IDENT_MIN) / 2)))
  const cand = []
  let optMse = Infinity
  for (let dstep = 0; dstep <= dMax; dstep++) {
    const f = fitDelay(r, dstep)
    if (!f) continue
    const mse = f.sse / Math.max(1, f.m)
    cand.push({ a: f.a, b: f.b, c: f.c, m: f.m, uVar: f.uVar, delay: dstep, mse })
    if (mse < optMse) optMse = mse
  }
  // 节俭原则 + 混叠防护：周期性激励下，滞后 θ 与 θ+周期 的残差可能同样低（滞后混叠）。
  // 因此不取全局最优，而取"残差不显著差于全局最优（≤1.05 倍）"的**最小**滞后。
  let pick = null
  for (const cd of cand) {
    if (cd.mse <= optMse * DELAY_GAIN) { pick = cd; break }
  }
  if (!pick) {
    identDiag[lp.key] = { ok: false, msg: t('拟合失败（数据可能全为无效值）') }
    return null
  }
  const best = pick
  const uSd = Math.sqrt(best.uVar)
  if (!(uSd / uRange > EXC_RATIO)) {
    // 激励（Excitation）：u 不动作时 b/K 在数值上不可辨识，此时宁可用先验模型
    identDiag[lp.key] = { ok: false, msg: t('激励不足：可调设备设定值几乎未变化，增益 K 不可辨识') }
    return null
  }
  const m = {
    a: best.a, b: best.b, c: best.c, dt,
    delay: best.delay, theta: best.delay * dt,
    tau: -dt / Math.log(best.a), G: best.b / (1 - best.a),
    n: best.m, mse: best.mse, uSd, src: 'ident',
  }
  identDiag[lp.key] = {
    ok: true, msg: '',
    rmse: Math.sqrt(best.mse),
    rmsePct: (Math.sqrt(best.mse) / Math.max(r.scale, 1e-9)) * 100,
    tau: m.tau, theta: m.theta, G: m.G, n: m.n, delay: m.delay, dt,
  }
  return m
}
/** 先验模型（无足够数据时使用）：保守慢过程 + 用户给定的先验纯滞后 θ₀ */
function priorModel(lp) {
  const r = rt.map[lp.key]
  const scale = r ? r.scale : Math.max(Math.abs(Number(liveOf(lp.senId) ?? 0)), 1e-3)
  const uRange = Math.max(spMax(lp.adjId) - spMin(lp.adjId), 1e-6)
  const G = (0.15 * scale) / uRange
  const tau = 4, dt = 1
  const a = Math.exp(-dt / tau)
  const delay = Math.max(0, Math.round((Number(priTheta.value) || 0) / dt))
  const u0 = r ? r.u0 : 0
  const y0 = r ? r.y0 : 0
  return {
    a, b: G * (1 - a), c: y0 * (1 - a) - G * (1 - a) * u0, dt, delay,
    theta: delay * dt, n: 0, src: 'prior', tau, G,
  }
}
/** 推演步数：需覆盖「纯滞后 + 5 倍时间常数」，否则滞后段还没结束就截断，学不到滞后代价 */
function simSteps(models) {
  let dt = 1, span = 1
  for (const m of models) {
    if (!m) continue
    dt = Math.max(dt, m.dt || 1)
    const theta = Number.isFinite(m.theta) ? m.theta : (m.delay || 0) * (m.dt || 1)
    span = Math.max(span, theta + 5 * Math.max(m.tau || 0, 0))
  }
  return Math.min(300, Math.max(40, Math.ceil(span / dt)))
}

// ==================== 训练（PPO） ====================
// 状态 s = [ŷ, e, Δe, d̂]：ŷ 为滤波后观测，d̂ 为滤波估计出的隐藏状态（传感器测不到的扰动）
// 动作 a = [a_u, a_p, a_i, a_d]：a_u 直接调节量，a_p/a_i/a_d → K = K₀·exp(clip(a))
// 奖励 r = −(w₁|e| + w₂|Δe| + w₃·超调 + w₄·功耗)
const ACT_CLIP = 1.6
const maxIter = ref(30)
const ppoLr = ref(3e-3)
const ppoClip = ref(0.2)
const ppoGamma = ref(0.99)
const ppoLam = ref(0.95)
const ppoEnt = ref(0.01)
const ppoK = ref(4)
const ppoEps = ref(4)
const ppoSig = ref(0.4)
const distPct = ref(2)            // 环境扰动（隐藏噪声，%量程）
const modelPct = ref(10)          // 模型不确定度（域随机化幅度，%参数）
const priTheta = ref(2)           // 先验纯滞后 θ₀（秒，无数据时使用）
const rwErr = ref(1)
const rwDe = ref(0.1)
const rwOv = ref(0.5)
const rwPow = ref(0.3)

const trainBusy = ref(false)
const trainStop = ref(false)
const curve = ref([])          // [{ it, reward }]
const baseReward = ref(null)   // 零动作基线
const iterN = ref(0)
const bestReward = ref(null)
const lastReward = computed(() => (curve.value.length ? curve.value[curve.value.length - 1].reward : null))
const canTrain = computed(() => loops.value.length > 0)

function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v) }

function rollout(agent, m, steps, b0, lp, opt = {}) {
  const scale = Math.max(Math.abs(Number(liveOf(lp.senId) ?? 0)), 1e-3)
  const uMin = spMin(lp.adjId), uMax = spMax(lp.adjId)
  const uRange = Math.max(uMax - uMin, 1e-6)
  const uMaxAbs = Math.max(Math.abs(uMax), Math.abs(uMin), 1e-6)
  const u0 = curSp(lp.adjId) != null ? Number(curSp(lp.adjId)) : (uMin + uMax) / 2
  const sp = Number(targetOf(lp.senId)) || 0
  const y0 = Number(liveOf(lp.senId) ?? 0)
  const dir = Math.sign(sp - y0) || 1
  const dt = m.dt || 1
  const qT = Math.pow(FILT_Q * scale, 2)
  const qd = qT * 0.05
  const rv = Math.pow(FILT_R * scale, 2)
  const dStd = ((Number(distPct.value) || 0) / 100) * scale
  const nomD = m.delay || 0                   // 名义纯滞后拍数

  // —— 域随机化（Domain Randomization）：模型参数不确定性 ——
  // 每个采样回合开始时对 a / b / θ 各扰动 ±modelPct%，让策略对"模型不准则"鲁棒，
  // 而不是把模型当真值过拟合。评估与基线用名义模型（perturb=false），保证指标可比。
  const pu = (Number(modelPct.value) || 0) / 100
  const jit = () => 1 + (Math.random() * 2 - 1) * pu
  const pert = !!opt.perturb
  const mA = pert ? clamp(m.a * jit(), 0.05, 0.9995) : m.a
  const mB = pert ? m.b * jit() : m.b
  const mD = pert ? Math.max(0, Math.round(nomD * jit())) : nomD

  const pid = createPid({ min: uMin, max: uMax })
  pid.reset()
  const kf = createEkf2({ qT, qd, r: rv })
  let T = y0, u = u0, d = 0, ePrev = 0
  const uH = []                               // uH[j]：第 j 步末尾发出的调节量（纯滞后回放用）
  const s = [], acts = [], logps = [], rews = [], vals = []
  const actSum = new Float64Array(4)
  let costSum = 0
  for (let k = 0; k < steps; k++) {
    // 纯滞后：本拍真正生效的，是 (mD+1) 拍前发出的 u；尚未发出时用初值 u0
    const iu = k - 1 - mD
    const uEff = iu < 0 ? u0 : uH[iu]
    d += randn() * dStd                       // 隐藏扰动（传感器测不到的未建模动态）
    T = mA * T + mB * uEff + m.c + d          // 过程真实演化（含纯滞后）
    const est = kf.step(T, uEff, { a: mA, b: mB, c: m.c, qT, qd, r: rv })
    const e = sp - est.t
    const de = e - ePrev
    ePrev = e
    const st = new Float64Array([est.t / scale, e / scale, de / scale, est.d / scale])
    let a, logp = 0
    if (opt.zero) {
      a = new Float64Array(4)
    } else {
      const out = agent.act(st, !!opt.deterministic)
      a = out.a
      logp = out.logp
    }
    pid.set({
      kp: b0.kp * Math.exp(clamp(a[1], -ACT_CLIP, ACT_CLIP)),
      ki: b0.ki * Math.exp(clamp(a[2], -ACT_CLIP, ACT_CLIP)),
      kd: b0.kd * Math.exp(clamp(a[3], -ACT_CLIP, ACT_CLIP)),
      min: uMin, max: uMax,
    })
    const du = clamp(a[0], -1, 1) * 0.15 * uRange
    u = clamp(pid.step(sp, est.t, dt).u + du, uMin, uMax)
    uH.push(u)                                          // 记录本拍发出的动作，mD 拍后生效
    const power = Math.pow(Math.abs(u) / uMaxAbs, 3)   // 功耗 P ∝ 转速³
    const ov = Math.max(0, (T - sp) * dir) / scale
    const r = -(rwErr.value * Math.abs(e) / scale
      + rwDe.value * Math.abs(de) / scale
      + rwOv.value * ov
      + rwPow.value * power)
    s.push(st); acts.push(a); logps.push(logp); rews.push(r)
    if (!opt.zero) vals.push(agent.value(st))
    for (let q = 0; q < 4; q++) actSum[q] += a[q]
    costSum += -r
  }
  const lastVal = (s.length && !opt.zero) ? agent.value(s[s.length - 1]) : 0
  return {
    s, a: acts, logp: logps, rews, vals, lastVal,
    meanCost: costSum / Math.max(1, steps), actSum, steps,
  }
}

/** 确定性评估：平均代价 + 动作换算出的调节量/增益 */
function evaluate(agent, models, lps, steps, bases) {
  let cost = 0, n = 0
  const dims = []
  for (let i = 0; i < lps.length; i++) {
    const ep = rollout(agent, models[i], steps, bases[i], lps[i], { deterministic: true })
    cost += ep.meanCost
    n++
    const b = bases[i]
    const uRange = Math.max(spMax(lps[i].adjId) - spMin(lps[i].adjId), 1e-6)
    dims.push({
      adjId: lps[i].adjId, senId: lps[i].senId,
      adjLabel: lps[i].adjLabel, senLabel: lps[i].senLabel,
      du: Number((clamp(ep.actSum[0] / Math.max(1, ep.steps), -1, 1) * 0.15 * uRange).toFixed(4)),
      kp: Number((b.kp * Math.exp(clamp(ep.actSum[1] / Math.max(1, ep.steps), -ACT_CLIP, ACT_CLIP))).toFixed(6)),
      ki: Number((b.ki * Math.exp(clamp(ep.actSum[2] / Math.max(1, ep.steps), -ACT_CLIP, ACT_CLIP))).toFixed(6)),
      kd: Number((b.kd * Math.exp(clamp(ep.actSum[3] / Math.max(1, ep.steps), -ACT_CLIP, ACT_CLIP))).toFixed(6)),
    })
  }
  return { cost: n ? cost / n : 1e9, dims }
}

// ==================== 模型版本 ====================
const VER_KEY = 'nengtan.agc.models.v2'
const versions = ref([])
const activeVer = ref('')
const activeVerObj = computed(() => versions.value.find((v) => v.id === activeVer.value) || null)

function loadVers() {
  try {
    const raw = localStorage.getItem(VER_KEY)
    const arr = raw ? JSON.parse(raw) : []
    versions.value = Array.isArray(arr) ? arr : []
  } catch (e) { versions.value = [] }
}
function saveVers() {
  try { localStorage.setItem(VER_KEY, JSON.stringify(versions.value.slice(0, 20))) } catch (e) { /* 忽略 */ }
}
function hasVer(id) { return versions.value.some((v) => v.id === id) }
function applyVer(id) {
  const v = versions.value.find((x) => x.id === id)
  if (!v) return
  let hit = 0
  for (const d of v.dims) {
    const lp = loopOfAdj(d.adjId)
    if (!lp || lp.senId !== d.senId) continue
    fixGain[lp.key] = { kp: d.kp, ki: d.ki, kd: d.kd }
    hit++
  }
  if (!hit) { store.showToast(t('该版本与当前回路不匹配（可调设备或传感设备已变更）。'), 'warn'); return }
  curVerId.value = v.id
  store.showToast(t('已应用模型版本') + ' ' + v.name, 'success')
}
async function delVer(id) {
  const ok = await store.confirm({ title: t('删除模型版本'), message: t('删除后不可恢复，确认删除该版本？'), danger: true })
  if (!ok) return
  versions.value = versions.value.filter((v) => v.id !== id)
  if (activeVer.value === id) activeVer.value = versions.value.length ? versions.value[0].id : ''
  saveVers()
}
let verSeq = 0

// ==================== 训练主流程 ====================
const trainStateTxt = computed(() => {
  if (trainBusy.value) return `${t('训练中')} ${iterN.value}/${maxIter.value}`
  if (!curve.value.length) return t('未训练')
  return `${t('已完成')} ${iterN.value} ${t('轮')}`
})

async function startTrain() {
  if (trainBusy.value || !canTrain.value) return
  const lps = loops.value
  syncRuns()
  const bases = lps.map((lp) => gainOf(lp))
  const models = lps.map((lp) => identify(lp) || priorModel(lp))
  const steps = simSteps(models)
  trainBusy.value = true
  trainStop.value = false
  curve.value = []
  iterN.value = 0
  bestReward.value = null

  // 基线：零动作（K = K₀，无附加调节量）
  let bCost = 0
  for (let i = 0; i < lps.length; i++) {
    bCost += rollout(null, models[i], steps, bases[i], lps[i], { zero: true }).meanCost
  }
  baseReward.value = -(bCost / Math.max(1, lps.length))

  const agent = createPpoAgent({ sDim: 4, aDim: 4, hidden: 16, lr: ppoLr.value, sigma0: ppoSig.value })
  let best = { reward: -Infinity, dims: [] }

  for (let it = 1; it <= maxIter.value && !trainStop.value; it++) {
    const trans = []
    for (let i = 0; i < lps.length; i++) {
      for (let e = 0; e < ppoEps.value; e++) {
        const ep = rollout(agent, models[i], steps, bases[i], lps[i], { perturb: true })
        const { adv, ret } = computeGae(ep.rews, ep.vals, ep.lastVal, ppoGamma.value, ppoLam.value)
        const advN = standardize(adv)
        for (let k = 0; k < ep.s.length; k++) {
          trans.push({ s: ep.s[k], a: ep.a[k], logp: ep.logp[k], adv: advN[k], ret: ret[k] })
        }
      }
    }
    if (trans.length) {
      agent.update(trans, {
        clip: ppoClip.value, epochs: ppoK.value, entCoef: ppoEnt.value, vfCoef: 0.5, batchSize: 64,
      })
    }
    const ev = evaluate(agent, models, lps, steps, bases)
    const reward = -ev.cost
    if (reward > best.reward) best = { reward, dims: ev.dims }
    iterN.value = it
    bestReward.value = best.reward
    curve.value.push({ it, reward })
    await new Promise((r) => setTimeout(r, 0))   // 让出主线程，逐轮刷新曲线
  }

  trainBusy.value = false
  saveVersion(best, iterN.value)
  scheduleNext()
}
function stopTrain() { trainStop.value = true }

function saveVersion(best, iters) {
  if (!best || !Number.isFinite(best.reward)) return
  verSeq = versions.value.reduce((m, v) => Math.max(m, Number(String(v.name).replace(/\D/g, '')) || 0), 0) + 1
  const v = {
    id: 'm' + Date.now(),
    name: 'v' + verSeq,
    ts: Date.now(),
    alg: 'PPO',
    iters,
    reward: Number(best.reward.toFixed(6)),
    dims: best.dims,
  }
  versions.value = [v, ...versions.value].slice(0, 20)
  activeVer.value = v.id
  saveVers()
  store.showToast(t('训练完成，已存为模型版本') + ' ' + v.name, 'success')
}

// ==================== 奖励曲线 ====================
const RW = { W: 360, H: 110, GRID: [0, 27.5, 55, 82.5, 110] }
const rwScale = computed(() => {
  const vals = curve.value.map((p) => p.reward)
  if (baseReward.value != null) vals.push(baseReward.value)
  if (!vals.length) return { lo: 0, hi: 1 }
  let lo = Math.min(...vals), hi = Math.max(...vals)
  const pad = (hi - lo) * 0.08 || 1e-6
  return { lo: lo - pad, hi: hi + pad }
})
function rwY(v) {
  const { lo, hi } = rwScale.value
  return RW.H - ((Number(v) - lo) / ((hi - lo) || 1)) * RW.H
}
const rwPath = computed(() => {
  const c = curve.value
  if (c.length < 2) return ''
  return c.map((p, i) => `${((i / (c.length - 1)) * RW.W).toFixed(1)},${rwY(p.reward).toFixed(1)}`).join(' ')
})
const baseY = computed(() => (baseReward.value == null ? null : rwY(baseReward.value)))

// ==================== 自动训练 ====================
const autoMode = ref('off')      // off | 1h | 6h | daily
const autoAt = ref('02:00')
const nextAuto = ref(0)
const nowTs = ref(Date.now())
let autoTimer = null

function computeNext(from = Date.now()) {
  if (autoMode.value === 'off') return 0
  if (autoMode.value === 'daily') {
    const [h, m] = String(autoAt.value || '02:00').split(':').map((x) => Number(x) || 0)
    const d = new Date(from)
    d.setHours(h, m, 0, 0)
    if (d.getTime() <= from) d.setDate(d.getDate() + 1)
    return d.getTime()
  }
  const hours = autoMode.value === '1h' ? 1 : 6
  return from + hours * 3600 * 1000
}
function scheduleNext() { nextAuto.value = computeNext() }
watch([autoMode, autoAt], () => scheduleNext())
const nextAutoTxt = computed(() => {
  if (autoMode.value === 'off') return t('未开启自动训练')
  if (!nextAuto.value) return '—'
  const diff = Math.max(0, nextAuto.value - nowTs.value)
  const h = Math.floor(diff / 3600000)
  const m = Math.floor((diff % 3600000) / 60000)
  return `${t('下次训练')} ${shortTs(nextAuto.value)}（${h}h${String(m).padStart(2, '0')}m）`
})
function checkAuto() {
  nowTs.value = Date.now()
  if (autoMode.value === 'off' || trainBusy.value || !canTrain.value) return
  if (nextAuto.value && nowTs.value >= nextAuto.value) {
    nextAuto.value = computeNext()
    startTrain()
  }
}

// ==================== 初始化 ====================
// 首次拿到设备清单时给出合理默认：选第一台可调设备 + 同工序传感设备并自动绑定
let inited = false
/** 默认回路：取第一台可调设备 + 同工序传感设备并自动绑定（force = 进入新模型时重新给默认值） */
function autoPick(force) {
  if (inited && !force) return
  if (!adjList.value.length || !senList.value.length) return
  inited = true
  const a = adjList.value[0]
  selAdj.value = [a.id]
  const same = senList.value.filter((s) => s.unitId && a.unitId && String(s.unitId) === String(a.unitId))
  const pool = same.length ? same : senList.value
  selSen.value = pool.slice(0, 3).map((s) => s.id)
  for (const s of selSen.value) bindOf[s] = a.id
  syncRuns()
}
watch([() => adjList.value.length, () => senList.value.length], () => {
  // 清理失效选择/绑定
  const aids = adjList.value.map((d) => d.id)
  const sids = senList.value.map((d) => d.id)
  selAdj.value = selAdj.value.filter((id) => aids.includes(id))
  selSen.value = selSen.value.filter((id) => sids.includes(id))
  for (const k of Object.keys(bindOf)) {
    if (!sids.includes(k) || (bindOf[k] && !aids.includes(bindOf[k]))) delete bindOf[k]
  }
  autoPick()
  syncRuns()
}, { immediate: true })

onMounted(() => {
  loadVers()
  loadDesigns()
  if (versions.value.length) activeVer.value = versions.value[0].id
  scheduleNext()
  autoTimer = setInterval(checkAuto, 15000)
})
onBeforeUnmount(() => {
  trainStop.value = true
  runId.value = ''
  stopSample()
  if (autoTimer) clearInterval(autoTimer)
  if (saveTimer) clearTimeout(saveTimer)
})

// ==================== 格式化 ====================
function fmt(v, d) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  const a = Math.abs(n)
  const dg = a >= 1000 ? 0 : a >= 10 ? 1 : 2
  return n.toLocaleString('zh-CN', { maximumFractionDigits: Math.max(d == null ? dg : d, dg) })
}
function fmtSmall(v) {
  if (v == null || !Number.isFinite(Number(v))) return '—'
  const n = Number(v)
  const a = Math.abs(n)
  if (a >= 100) return n.toFixed(1)
  if (a >= 1) return n.toFixed(2)
  return n.toFixed(4)
}
function p2(n) { return String(n).padStart(2, '0') }
function shortTs(ts) {
  const d = new Date(ts)
  return `${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}`
}
function fullTs(ts) {
  const d = new Date(ts)
  return `${d.getFullYear()}-${p2(d.getMonth() + 1)}-${p2(d.getDate())} ${p2(d.getHours())}:${p2(d.getMinutes())}:${p2(d.getSeconds())}`
}

// ==================== ① 模型库（算法模型清单） ====================
// 一个模型 = 一套独立的群控算法（规则 / 强化学习 / 粒子群），各自保存自己的编排与设备选择。
const DESIGNS_KEY = 'nengtan.agc.designs.v1'
const ALG_TYPES = [
  { id: 'rule', ico: '⌥', label: t('规则'), desc: t('if-elif-else 阈值编排，直观可控') },
  { id: 'rl', ico: '◈', label: t('强化学习'), desc: t('PPO 在线辨识 + 策略寻优') },
  { id: 'pso', ico: '⁂', label: t('粒子群'), desc: t('在线寻优，让观测值逼近目标') },
]
function algMeta(id) { return ALG_TYPES.find((a) => a.id === id) || ALG_TYPES[0] }
function algIco(id) { return algMeta(id).ico }
function algLabel(id) { return algMeta(id).label }

const page = ref('lib')            // lib = 模型库；edit = 编排
const designs = ref([])
const cur = ref(null)              // 当前编排中的模型
const newOpen = ref(false)
const newName = ref('')
const newAlg = ref('rule')
const runId = ref('')              // 正在运行的模型 id

const isRule = computed(() => !!cur.value && cur.value.alg === 'rule')
/** 运行状态由父级（编排页右上角「运行」）统一下发，编排体自身不再各带开关 */
const running = computed(() => !!cur.value && runId.value === cur.value.id)
function isRunning(id) { return !!id && runId.value === id }

function blankPso() {
  return { vars: [], senId: '', target: 0, pNum: 12, iters: 20, w: 0.7, c1: 1.5, c2: 1.5, waitMs: 3000 }
}
function normalizeModel(m) {
  const mm = m || {}
  return {
    id: mm.id,
    name: mm.name || t('未命名模型'),
    alg: ALG_TYPES.some((a) => a.id === mm.alg) ? mm.alg : 'rule',
    ts: Number(mm.ts) || Date.now(),
    period: Number(mm.period) || 2,
    graph: {
      nodes: Array.isArray(mm.graph && mm.graph.nodes) ? mm.graph.nodes : [],
      edges: Array.isArray(mm.graph && mm.graph.edges) ? mm.graph.edges : [],
    },
    pso: { ...blankPso(), ...(mm.pso || {}) },
    selAdj: Array.isArray(mm.selAdj) ? mm.selAdj : [],
    selSen: Array.isArray(mm.selSen) ? mm.selSen : [],
    bindOf: mm.bindOf && typeof mm.bindOf === 'object' ? { ...mm.bindOf } : {},
    spOf: mm.spOf && typeof mm.spOf === 'object' ? { ...mm.spOf } : {},
  }
}
let saveTimer = null
function persist() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    try { localStorage.setItem(DESIGNS_KEY, JSON.stringify(designs.value.slice(0, 50))) } catch (e) { /* 忽略 */ }
  }, 200)
}
function loadDesigns() {
  try {
    const raw = localStorage.getItem(DESIGNS_KEY)
    const arr = raw ? JSON.parse(raw) : []
    designs.value = Array.isArray(arr) ? arr.filter((m) => m && m.id).map(normalizeModel) : []
  } catch (e) { designs.value = [] }
  seedDcExample()
}

// ==================== 内置示例：机房温控「机柜超温 → 降泵压」 ====================
// 首次在机房热控场景打开本视图时自动给出一个可直接运行的示例编排（只种一次，
// 用户删除后不再出现；场景未装载完成时跳过，下次打开视图再试）。
const DC_EXAMPLE_FLAG = 'nengtan.agc.seed.dc'
function seedDcExample() {
  if ((store.sceneId || '') !== 'dc-thermal') return
  try { if (localStorage.getItem(DC_EXAMPLE_FLAG) === '1') return } catch (e) { /* 忽略 */ }
  const senId = 'ext::n_dc_it::att_dc_it_temp'      // 机柜温度传感器
  const adjId = 'ext::n_dc_cw::att_dc_cw_pump'      // 循环水泵变压器
  if (!findDev(senId) || !findDev(adjId)) return
  if (designs.value.some((m) => m.id === 'dc_cool_rule_50c')) {
    try { localStorage.setItem(DC_EXAMPLE_FLAG, '1') } catch (e) { /* 忽略 */ }
    return
  }
  const m = normalizeModel({
    id: 'dc_cool_rule_50c',
    name: '示例 · 机柜超 50℃ → 循环水泵变压器 24V',
    alg: 'rule',
    ts: Date.now(),
    period: 2,
    graph: {
      nodes: [
        { id: 'sen_rack', kind: 'sen', devId: senId, label: '机柜温度传感器', unit: '℃', unitName: '算力设备', value: null, x: 80, y: 130 },
        { id: 'if_temp', kind: 'if', x: 330, y: 100, branches: [
          { id: 'b1', type: 'if', src: 'sen_rack', op: '>=', val: 50 },
          { id: 'b2', type: 'else', src: '', op: '>', val: 0 },
        ] },
        { id: 'adj_pump', kind: 'adj', devId: adjId, label: '循环水泵变压器', unit: 'V', unitName: '冷却水', value: 24, x: 620, y: 60 },
      ],
      edges: [
        { id: 'e_s2if', from: 'sen_rack', port: 'out', to: 'if_temp' },
        { id: 'e_if2adj', from: 'if_temp', port: 'b1', to: 'adj_pump' },
      ],
    },
    selAdj: [adjId],
    selSen: [senId],
  })
  designs.value = [m, ...designs.value]
  try { localStorage.setItem(DC_EXAMPLE_FLAG, '1') } catch (e) { /* 忽略 */ }
  persist()
}

// —— 进入 / 退出编排：设备选择与绑定随模型存取 ——
function loadSel(m) {
  const kept = (m.selAdj && m.selAdj.length) || (m.selSen && m.selSen.length) || Object.keys(m.bindOf || {}).length
  selAdj.value = (m.selAdj || []).slice()
  selSen.value = (m.selSen || []).slice()
  for (const k of Object.keys(bindOf)) delete bindOf[k]
  for (const k of Object.keys(spOf)) delete spOf[k]
  Object.assign(bindOf, m.bindOf || {})
  Object.assign(spOf, m.spOf || {})
  if (!kept) autoPick(true)
  // 规则模型：勾选 ⇄ 画布模块对齐（画布已有模块但没勾选时，以画布为准回勾，避免误删模块）
  if (m.alg === 'rule') {
    const hasDevNode = (m.graph && m.graph.nodes || []).some((n) => n && (n.kind === 'adj' || n.kind === 'sen'))
    if (hasDevNode && !selAdj.value.length && !selSen.value.length) syncSelFromGraph()
    else applySelToGraph()
  }
  syncRuns()
}
watch([selAdj, selSen, bindOf, spOf], () => {
  if (!cur.value) return
  cur.value.selAdj = selAdj.value.slice()
  cur.value.selSen = selSen.value.slice()
  cur.value.bindOf = { ...bindOf }
  cur.value.spOf = { ...spOf }
}, { deep: true })
// 模型的编排内容（规则图 / 粒子群参数 / 周期 / 名称）变更即落盘
watch(() => cur.value, (m) => { if (m) persist() }, { deep: true })

function enter(m) {
  if (!m) return
  // 只允许一个模型在运行：切到别的模型即停掉上一个（编排体卸载后定时器也随之失效）
  if (runId.value && runId.value !== m.id) runId.value = ''
  cur.value = m
  page.value = 'edit'
  loadSel(m)
}
function back() {
  stopRun()
  cur.value = null
  page.value = 'lib'
}
function openNew() {
  newName.value = ''
  newAlg.value = 'rule'
  newOpen.value = true
}
function createModel() {
  const nm = String(newName.value || '').trim()
  const m = normalizeModel({
    id: 'm' + Date.now() + Math.random().toString(36).slice(2, 6),
    name: nm || `${algLabel(newAlg.value)}${t('模型')}${designs.value.length + 1}`,
    alg: newAlg.value,
    ts: Date.now(),
  })
  designs.value = [m, ...designs.value]
  newOpen.value = false
  newName.value = ''
  persist()
  enter(m)
}
function renameModel(m) {
  const v = window.prompt(t('模型名称'), m.name)
  if (v == null) return
  const nm = String(v).trim()
  if (!nm) return
  m.name = nm
  persist()
}
function dupModel(m) {
  const i = designs.value.findIndex((x) => x.id === m.id)
  const copy = normalizeModel({
    ...JSON.parse(JSON.stringify(m)),
    id: 'm' + Date.now() + Math.random().toString(36).slice(2, 6),
    name: `${m.name} · ${t('副本')}`,
    ts: Date.now(),
  })
  designs.value.splice(i < 0 ? designs.value.length : i + 1, 0, copy)
  persist()
}
async function delModel(m) {
  const ok = await store.confirm({ title: t('删除模型'), message: t('删除后该模型的编排配置不可恢复，确认删除？'), danger: true })
  if (!ok) return
  if (runId.value === m.id) runId.value = ''
  designs.value = designs.value.filter((x) => x.id !== m.id)
  persist()
}

/** 模型卡片的摘要指标 */
function statOf(m) {
  if (!m) return []
  if (m.alg === 'rule') {
    return [
      { k: t('模块'), v: (m.graph.nodes || []).length },
      { k: t('连线'), v: (m.graph.edges || []).length },
      { k: t('周期'), v: `${m.period || 2}s` },
    ]
  }
  if (m.alg === 'pso') {
    return [
      { k: t('优化变量'), v: (m.pso.vars || []).length },
      { k: t('目标值'), v: fmt(m.pso.target) },
      { k: t('粒子数'), v: m.pso.pNum },
    ]
  }
  return [
    { k: t('可调'), v: (m.selAdj || []).length },
    { k: t('传感'), v: (m.selSen || []).length },
    { k: t('模型版本'), v: versions.value.length },
  ]
}

// ==================== ② 运行（编排页右上角「运行」） ====================
const canRun = computed(() => {
  const m = cur.value
  if (!m) return false
  if (m.alg === 'rule') return (m.graph.nodes || []).length > 0
  if (m.alg === 'pso') return (m.pso.vars || []).length > 0 && !!m.pso.senId
  return loops.value.length > 0
})
const runTip = computed(() => {
  const m = cur.value
  if (!m) return ''
  if (canRun.value) return t('按当前编排运行；再点一次停止')
  if (m.alg === 'rule') return t('请先把可调 / 传感设备拖入规则画布')
  if (m.alg === 'pso') return t('请先选择优化变量（可调设备）与优化目标（传感设备）')
  return t('请先在左栏绑定可调设备与传感设备，形成控制回路')
})
const runStateTxt = computed(() => {
  const m = cur.value
  if (!m) return ''
  if (m.alg === 'rule') {
    if (running.value) return t('规则运行中')
    return canRun.value ? t('就绪') : t('未编排')
  }
  if (m.alg === 'pso') return running.value ? t('寻优中') : t('待运行')
  if (trainBusy.value) return `${t('训练中')} ${iterN.value}/${maxIter.value}`
  if (sampling.value) return t('采集中')
  if (curve.value.length) return `${t('已完成')} ${iterN.value} ${t('轮')}`
  return t('待运行')
})
function toggleRun() {
  const m = cur.value
  if (!m) return
  if (running.value) { stopRun(); return }
  if (!canRun.value) return
  runId.value = m.id
  if (m.alg === 'rl') {
    syncRuns()
    startSample()
    if (canTrain.value) startTrain()
  }
}
function stopRun() {
  const m = cur.value
  if (!m) return
  if (m.alg === 'rl') { stopTrain(); stopSample() }
  runId.value = ''
}
/** 粒子群寻优结束（或被中断）由子面板回报 */
function onPsoRun(v) { if (!v) runId.value = '' }

defineExpose({ startSample, stopSample, enter, back })
</script>

<style scoped>
.agc { flex: 1 1 auto; min-height: 0; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.hd-sp { flex: 1 1 auto; }

/* ==================== ① 模型库 ==================== */
.agc-lib { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; padding-right: 4px; }
.lib-tip { margin: 0; font-size: 10.5px; line-height: 1.7; color: var(--muted); }
.lib-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(212px, 1fr));
  gap: 10px; align-content: start;
  /* 卡片不贴左侧边缘：留出与右侧滚动条对称的呼吸位 */
  padding-left: 6px;
}
.mcard {
  position: relative; display: flex; flex-direction: column; gap: 6px;
  padding: 8px 10px 7px; text-align: left; font-family: inherit; cursor: pointer;
  border: 1px solid var(--border); border-left: 3px solid var(--border); border-radius: 3px;
  background: var(--panel); transition: border-color .12s, box-shadow .12s;
}
.mcard:hover { border-color: var(--accent2); box-shadow: 0 1px 6px rgba(0, 0, 0, .08); }
.mcard.alg-rule { border-left-color: #D97A21; }
.mcard.alg-rl { border-left-color: #7A5AA8; }
.mcard.alg-pso { border-left-color: #17957F; }
.mcard.live { box-shadow: 0 0 0 1px var(--accent-d) inset; }
.mc-top { display: flex; align-items: center; gap: 6px; }
.mc-ic { font-size: 13px; color: var(--accent-d); font-style: normal; }
.mc-nm {
  flex: 1 1 auto; min-width: 0; font-size: 11.5px; font-weight: 600; color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mc-tg {
  flex: 0 0 auto; padding: 0 5px; border-radius: 8px; font-size: 9px; line-height: 14px;
  background: var(--bar); color: var(--muted); border: 1px solid var(--border);
}
.mc-tg.rule { color: #D97A21; border-color: rgba(217, 122, 33, .5); background: rgba(217, 122, 33, .10); }
.mc-tg.rl { color: #7A5AA8; border-color: rgba(122, 90, 168, .5); background: rgba(122, 90, 168, .10); }
.mc-tg.pso { color: #17957F; border-color: rgba(23, 149, 127, .5); background: rgba(23, 149, 127, .10); }
.mc-bd { display: flex; flex-direction: column; gap: 2px; }
.mc-st { display: flex; align-items: baseline; justify-content: space-between; font-size: 10px; }
.mc-st em { font-style: normal; color: var(--faint); }
.mc-st b { font-size: 10.5px; color: var(--muted); font-weight: 600; }
.mc-ft { display: flex; align-items: center; gap: 6px; padding-top: 3px; border-top: 1px dashed var(--line); }
.mc-ft .dim { font-size: 9.5px; color: var(--faint); }
.mc-ops { margin-left: auto; display: inline-flex; gap: 7px; }
.mc-ops .lk.danger:hover { color: var(--red); }
.mc-live {
  position: absolute; top: 6px; right: 8px; font-style: normal; font-size: 9px;
  color: var(--green); background: rgba(46, 139, 87, .12); border-radius: 8px; padding: 0 5px;
}
.mcard.new {
  align-items: center; justify-content: center; gap: 3px; min-height: 112px;
  border-style: dashed; color: var(--muted); background: transparent;
}
.mcard.new .plus { font-size: 20px; line-height: 1; color: var(--accent-d); }
.mcard.new .nt { font-size: 11.5px; font-weight: 600; color: var(--text); }
.mcard.new .nd { font-size: 9.5px; color: var(--faint); }
.lib-empty { padding: 26px 0; text-align: center; }
.lib-empty .t1 { margin: 0 0 4px; font-size: 12px; color: var(--muted); }
.lib-empty .t2 { margin: 0; font-size: 10.5px; color: var(--faint); }

/* ==================== ② 编排 ==================== */
.agc-edit { flex: 1 1 auto; min-height: 0; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.ed-top {
  display: flex; align-items: center; gap: 8px; flex: 0 0 auto;
  padding: 5px 8px; border: 1px solid var(--border); border-radius: 3px; background: var(--panel);
}
.ed-nm { font-size: 12.5px; color: var(--text); }
.ed-st { display: inline-flex; align-items: center; gap: 5px; font-size: 10.5px; color: var(--muted); }
.ed-st .dot { width: 7px; height: 7px; border-radius: 50%; background: #888; }
.ed-st.on { color: var(--accent-d); }
.ed-st.on .dot { background: var(--accent); animation: agc-pulse 1s infinite; }
.ed-bd { flex: 1 1 auto; min-height: 0; display: flex; gap: 12px; }

/* ==================== 新建模型 ==================== */
.mk-mask {
  position: fixed; inset: 0; z-index: 60; display: flex; align-items: center; justify-content: center;
  background: rgba(0, 0, 0, .38);
}
.mk-dlg {
  width: 460px; max-width: calc(100vw - 40px); max-height: 88vh; overflow: auto;
  display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: 4px;
  background: var(--panel); box-shadow: 0 8px 30px rgba(0, 0, 0, .25);
}
.mk-hd {
  display: flex; align-items: center; gap: 8px; padding: 8px 12px;
  border-bottom: 1px solid var(--border); background: var(--panel-2);
}
.mk-hd b { font-size: 12.5px; color: var(--text); }
.mk-x {
  margin-left: auto; padding: 0 4px; border: 0; background: none; cursor: pointer;
  font-family: inherit; font-size: 12px; color: var(--faint);
}
.mk-x:hover { color: var(--red); }
.mk-bd { padding: 10px 12px; display: flex; flex-direction: column; gap: 8px; }
.mk-f { display: flex; align-items: center; gap: 8px; }
.mk-f em { font-style: normal; flex: 0 0 auto; font-size: 10.5px; color: var(--muted); }
.mk-in {
  flex: 1 1 auto; min-width: 0; padding: 3px 6px; font-size: 11.5px; font-family: inherit; color: var(--text);
  background: var(--panel); border: 1px solid var(--border); border-radius: 3px; outline: none;
}
.mk-in:focus { border-color: var(--accent2); }
.mk-t { font-size: 10.5px; color: var(--muted); }
.mk-types { display: flex; flex-direction: column; gap: 6px; }
.mk-tp {
  display: grid; grid-template-columns: 24px 1fr; grid-template-rows: auto auto; gap: 0 8px;
  padding: 6px 8px; text-align: left; cursor: pointer; font-family: inherit;
  border: 1px solid var(--border); border-radius: 3px; background: var(--panel);
}
.mk-tp:hover { border-color: var(--accent2); }
.mk-tp.on { border-color: var(--accent-d); background: var(--accent-l); }
.mk-tp .tp-ic { grid-row: 1 / 3; align-self: center; font-style: normal; font-size: 15px; color: var(--accent-d); text-align: center; }
.mk-tp b { font-size: 11.5px; color: var(--text); }
.mk-tp span { font-size: 9.5px; color: var(--faint); }
.mk-tp.rule .tp-ic { color: #D97A21; }
.mk-tp.rl .tp-ic { color: #7A5AA8; }
.mk-tp.pso .tp-ic { color: #17957F; }
.mk-ft { display: flex; justify-content: flex-end; gap: 8px; padding: 8px 12px; border-top: 1px solid var(--border); }

/* ==================== 左栏 ==================== */
.agc-aside {
  flex: 0 0 336px; width: 336px; min-width: 0;
  display: flex; flex-direction: column; gap: 8px;
  overflow-y: auto; padding-right: 4px;
}
.agc-hd { display: flex; align-items: center; gap: 6px; padding: 2px 0 4px; border-bottom: 1px solid var(--line); }
.agc-hd b { font-size: 12.5px; color: var(--text); }
.hd-sub { margin-left: auto; font-size: 10px; color: var(--faint); }

.pnl { border: 1px solid var(--border); border-radius: 3px; background: var(--panel); }
.pnl-hd {
  display: flex; align-items: center; gap: 6px; padding: 5px 8px;
  background: var(--panel-2); border-bottom: 1px solid var(--border);
  font-size: 11.5px; font-weight: 600; color: var(--text); cursor: pointer; user-select: none;
}
.caret { font-style: normal; font-size: 9px; color: var(--faint); transition: transform .12s; display: inline-block; }
.caret.on { transform: rotate(90deg); }
.ph-t { letter-spacing: .2px; }
.cnt { font-style: normal; font-size: 9.5px; color: var(--faint); }
.hd-ops { margin-left: auto; display: inline-flex; gap: 6px; }
.lk {
  padding: 0; border: 0; background: none; cursor: pointer;
  font-size: 10px; color: var(--muted); font-family: inherit;
}
.lk:hover { color: var(--accent-d); text-decoration: underline; }
.pnl-bd { padding: 6px 8px 8px; display: flex; flex-direction: column; gap: 5px; }
.emp { margin: 0; font-size: 10.5px; line-height: 1.6; color: var(--muted); }
.emp.sm { font-size: 10px; color: var(--faint); }

.dev { border: 1px solid transparent; border-radius: 3px; }
.dev.on { background: var(--panel-2); border-color: var(--border); }
.dev-hd { display: flex; align-items: center; gap: 6px; padding: 3px 4px; cursor: pointer; }
.cbx {
  flex: 0 0 auto; width: 12px; height: 12px; border: 1px solid var(--border); border-radius: 2px;
  background: var(--panel); display: inline-flex; align-items: center; justify-content: center;
  font-size: 9px; line-height: 1; color: #fff;
}
.dev.on .cbx { background: var(--accent-d); border-color: var(--accent-d); }
.dev-hd .nm { flex: 1 1 auto; min-width: 0; font-size: 11px; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dev-hd .nm em { font-style: normal; font-size: 9.5px; color: var(--faint); margin-left: 5px; }
.dev-hd .val { flex: 0 0 auto; font-size: 11px; color: var(--text); font-weight: 600; }
.dev-hd .val i { font-style: normal; font-size: 9px; color: var(--faint); margin-left: 2px; }
.tag {
  flex: 0 0 auto; padding: 0 5px; border-radius: 8px; font-size: 9px; line-height: 14px;
  background: var(--bar); color: var(--muted); border: 1px solid var(--border);
}
.tag.pid { color: var(--accent-d); border-color: var(--accent-d); background: var(--accent-l); }
.tag.on { color: var(--green); border-color: var(--green); background: rgba(46,139,87,.10); }

.dev-bd { padding: 2px 4px 5px 22px; display: flex; flex-direction: column; gap: 4px; }
.sp-row { display: flex; align-items: center; gap: 6px; }
.rng { flex: 1 1 auto; min-width: 0; accent-color: var(--accent-d); height: 14px; }
.rng:disabled { opacity: .5; }
.sp-row .num { width: 66px; }
.meta { display: flex; align-items: center; gap: 8px; font-size: 9.5px; color: var(--faint); flex-wrap: wrap; }
.meta b { color: var(--muted); }
.row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.row > em { font-style: normal; font-size: 10px; color: var(--muted); flex: 0 0 auto; }
.row select { flex: 1 1 auto; min-width: 0; }
.row .num { width: 72px; }
.row.st { gap: 10px; }
.row.rd b { font-size: 11px; color: var(--text); }
.hintx { font-size: 9.5px; color: var(--faint); }
.kv { display: inline-flex; align-items: baseline; gap: 3px; }
.kv em { font-style: normal; font-size: 9.5px; color: var(--faint); }
.kv b { font-size: 10.5px; font-weight: 600; }
.kv b.raw { color: #E07B39; }
.kv b.ekf { color: #3AA655; }
.badge { margin-left: auto; padding: 0 5px; border-radius: 8px; font-size: 9px; line-height: 14px; background: var(--bar); color: var(--muted); }
.badge.ok { color: var(--green); background: rgba(46,139,87,.12); }
.badge.busy { color: var(--accent-d); background: var(--accent-l); }
.badge.na { color: var(--red); background: rgba(188,59,48,.10); }
.badge.idle { color: var(--faint); }

.io { display: flex; flex-direction: column; gap: 3px; padding: 2px 0 4px; }
.io-row { display: flex; gap: 6px; font-size: 10px; color: var(--muted); }
.io-row em { font-style: normal; flex: 0 0 auto; color: var(--faint); }
.io-row .warnx { color: var(--red); }
.io-row .okx { color: var(--green); }

/* ==================== 右栏 ==================== */
.agc-main { flex: 1 1 auto; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; padding-right: 4px; }

/* 规则控制：编排画布占据右栏主体 */
.card.rg { flex: 1 1 auto; min-height: 560px; }
.rf-fill { flex: 1 1 auto; min-height: 0; }
.rg .lg-i { font-size: 9.5px; margin-left: 6px; }
.rg .lg-i.adj { color: #D97A21; }
.rg .lg-i.sen { color: #17957F; }
.rg .lg-i.ifn { color: #7A5AA8; }
.drag-tip { color: var(--accent-d); border-left: 2px solid var(--accent-l); padding-left: 6px; }
.rg-st { padding-top: 2px; }
.rg-st .mono { font-size: 10px; color: var(--muted); }
.card { flex: 0 0 auto; display: flex; flex-direction: column; border: 1px solid var(--border); border-radius: 3px; background: var(--panel); }
.card.grow { flex: 1 1 auto; min-height: 190px; }
.card-hd {
  display: flex; align-items: center; gap: 8px; padding: 5px 8px;
  background: var(--panel-2); border-bottom: 1px solid var(--border);
}
.ct { font-size: 11.5px; font-weight: 600; color: var(--text); }
.cs { font-size: 10px; color: var(--faint); }
.ch-ops { margin-left: auto; display: inline-flex; align-items: center; gap: 8px; }
.ch-ops .rw { color: var(--accent-d); font-size: 11px; }
.ch-ops .best { color: var(--green); font-size: 11px; }
.ch-ops .dim { font-size: 10px; color: var(--faint); }
.cempty { height: 150px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 0 24px; text-align: center; font-size: 10.5px; color: var(--faint); }
.cempty.sm { height: 150px; }
.cempty .t1 { font-size: 11px; color: var(--muted); }
.cempty .t2 { font-size: 10px; max-width: 460px; }

.btn {
  padding: 2px 10px; font-size: 11px; font-family: inherit; color: var(--muted);
  background: var(--panel); border: 1px solid var(--border); border-radius: 3px; cursor: pointer;
}
.btn:hover:not(:disabled) { border-color: var(--accent2); color: var(--accent-d); }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn.primary { color: #fff; background: var(--accent-d); border-color: transparent; font-weight: 500; }
.btn.primary:hover:not(:disabled) { filter: brightness(1.08); color: #fff; }
.btn.stop { color: var(--red); border-color: var(--red); }
.btn.ghost { background: transparent; }
.btn.ghost:hover:not(:disabled) { background: var(--panel-2); }

.bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 7px 8px; }
.bar.mv { border-top: 1px dashed var(--line); gap: 8px; }
.sep { width: 1px; height: 14px; background: var(--line); }
.lb2 { font-style: normal; font-size: 10.5px; color: var(--muted); }
.nx { font-size: 10px; color: var(--faint); font-variant-numeric: tabular-nums; }
.chk { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; color: var(--muted); cursor: pointer; }
.chk input { accent-color: var(--accent-d); width: 12px; height: 12px; }
.tstate { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; color: var(--muted); }
.tstate .dot { width: 7px; height: 7px; border-radius: 50%; background: #777; }
.tstate.on { color: var(--accent-d); }
.tstate.on .dot { background: var(--accent); animation: agc-pulse 1s infinite; }
@keyframes agc-pulse { 50% { opacity: .35; } }

.hp { padding: 2px 8px 8px; border-bottom: 1px dashed var(--line); display: flex; flex-direction: column; gap: 6px; }
.hp-row { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.hp-row.obj { padding-top: 6px; border-top: 1px dotted var(--line); }
.hp-row .lb { font-size: 10px; color: var(--muted); }
.f { display: inline-flex; align-items: center; gap: 4px; }
.f > em { font-style: normal; font-size: 9.5px; color: var(--faint); white-space: nowrap; }
.num {
  padding: 2px 4px; font-size: 11px; font-family: var(--mono); text-align: right; color: var(--text);
  background: var(--panel); border: 1px solid var(--border); border-radius: 3px; outline: none;
}
.num:focus { border-color: var(--accent2); }
.num:disabled { opacity: .55; }
.num.w56 { width: 56px; }
.num.tm { width: 84px; text-align: center; }
select, .sel {
  padding: 2px 4px; font-size: 11px; font-family: inherit; color: var(--text);
  background: var(--panel); border: 1px solid var(--border); border-radius: 3px; outline: none; max-width: 100%;
}
.sel.xs { font-size: 10.5px; }
.grow { flex: 1 1 auto; }
i.u { font-style: normal; font-size: 9.5px; color: var(--faint); }
.mono { font-family: var(--mono); }

/* 奖励曲线 */
.rw-wrap { flex: 1 1 auto; min-height: 150px; display: flex; flex-direction: column; padding: 6px 8px 4px; }
.rw-svg { width: 100%; flex: 1 1 auto; min-height: 110px; }
.rw-svg .grid { stroke: var(--line); stroke-width: 1; vector-effect: non-scaling-stroke; }
.rw-svg .base { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 4 4; opacity: .7; vector-effect: non-scaling-stroke; }
.rw-svg .cv { fill: none; stroke: var(--accent-d); stroke-width: 1.8; vector-effect: non-scaling-stroke; }
.rw-ax { display: flex; justify-content: space-between; font-size: 9.5px; color: var(--faint); padding-top: 2px; }

/* 版本表 */
.vtb { display: flex; flex-direction: column; }
.vtr { display: grid; grid-template-columns: 60px 1.4fr 70px 60px 90px 70px; gap: 6px; align-items: center; padding: 4px 8px; font-size: 10.5px; color: var(--text); cursor: pointer; }
.vtr.hd { background: var(--panel-2); color: var(--faint); font-size: 9.5px; cursor: default; border-bottom: 1px solid var(--border); }
.vtr:not(.hd):hover { background: var(--panel-2); }
.vtr.on { background: var(--sel); }
.vtr.cur .mono { color: var(--green); }
.vtr .dim { color: var(--faint); }
.vtr .rw { color: var(--accent-d); }
.vempty { padding: 10px 8px; font-size: 10.5px; color: var(--faint); text-align: center; }
.vdim { border-top: 1px dashed var(--line); padding: 6px 8px 8px; }
.vdim-h { font-size: 10px; color: var(--muted); padding-bottom: 4px; }
.vrow { display: flex; align-items: baseline; gap: 6px; font-size: 10.5px; padding: 1px 0; }
.vrow .rn {
  flex: 0 0 auto; width: 15px; height: 15px; border-radius: 50%; text-align: center; line-height: 15px;
  font-size: 9px; color: var(--accent-d); background: var(--bar); border: 1px solid var(--border);
}
.vrow .rl { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vrow .rp { margin-left: auto; color: var(--accent-d); font-size: 10px; }
</style>
