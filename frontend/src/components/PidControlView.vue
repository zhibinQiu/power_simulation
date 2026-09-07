<template>
  <!-- ============ AI 群控主区：左设定 · 右图 ============
       左侧设定：数据源 / 回路组 + PID 参数 / 滤波（EKF 为勾选项）/ 运行控制；
       右侧图（从上至下）：① 实时序列  ② 滤波后的序列  ③ 优化模型控制的训练（占右区大范围）
       训练理念：无论遗传算法 / 粒子群 / 强化学习，训练输出始终是「控制 PID 参数」——
       一个可调设备 = Kp·Ki·Kd 三个参数，N 个可调设备 = 3N 维决策变量 -->
  <div class="pid-wrap">
    <!-- ============ 空态 ============ -->
    <div v-if="!adjOptions.length && !allMetering.length" class="pid-empty">
      <svg class="pid-empty-ico" width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3.2"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h.02a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h.02a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l.06.06a1.65 1.65 0 0 0 .33 1.82v.02a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>
      <p>{{ t('未找到任何工艺设备：请先加载/打开一个流程场景，再进入本控制实验。') }}</p>
    </div>
    <div v-else-if="!adjOptions.length" class="pid-empty">
      <p>{{ t('当前场景没有可调设备（PID 需要一个可调设备作为被调对象）。左侧场景中选取「可调设备」后即可启用本控制实验。') }}</p>
    </div>

    <template v-else>
      <div class="pid-main">
        <!-- ════════════ 左：设定 ════════════ -->
        <aside class="pid-set">
          <header class="pid-top">
            <span class="pid-kbd">PID · EKF</span>
            <span class="pid-ttl">{{ t('多回路整定台') }}</span>
            <span class="pid-sub">{{ grps.length }} {{ t('回路') }} · {{ t('平台实时读数') }}</span>
            <span class="pid-state" :class="stateCls"><i class="pid-dot"></i>{{ stateText }}</span>
          </header>

          <!-- ① 数据与回路（每组 = 1 个可调设备 → 3 个 PID 参数） -->
          <section class="set-sec">
            <div class="sec-head">
              <span class="sec-no">1</span><span class="sec-ttl">{{ t('数据与回路') }}</span>
              <button class="mini-btn add" :disabled="running || !canAddGrp"
                      :title="t('为另一台可调设备建立控制回路')" @click="addGroup">＋ {{ t('回路') }}</button>
            </div>
            <!-- 数据源：一律为平台实时读数，本视图不生成任何模拟数据 -->
            <p class="hint src-note">{{ t('数据源：平台实时读数（MQTT / 设备实时读数）。本视图不生成任何模拟数据，观测真值 y 直接取自实时链路。') }}</p>
            <div class="grp-list">
              <div class="grp-row" v-for="(g, i) in grps" :key="g.key" :class="{ on: i === viewIdx }" @click="viewIdx = i">
                <div class="grp-l1">
                  <span class="grp-no">{{ i + 1 }}</span>
                  <label class="cell" @click.stop>
                    <em>{{ t('被调（可调）') }}</em>
                    <select v-model="g.adjId" :disabled="running" @change="onGrpChange(i)">
                      <option v-for="d in adjOptions" :key="d.id" :value="d.id">{{ optTxt(d) }}</option>
                    </select>
                  </label>
                  <span class="grp-arrow">→</span>
                  <label class="cell" @click.stop>
                    <em>{{ t('观测（反馈）') }}</em>
                    <select v-model="g.obsId" :disabled="running" @change="onGrpChange(i)">
                      <optgroup v-if="obsOpts(i).primary.length" :label="t('同工艺')">
                        <option v-for="d in obsOpts(i).primary" :key="d.id" :value="d.id">{{ optTxt(d) }}</option>
                      </optgroup>
                      <optgroup v-if="obsOpts(i).secondary.length" :label="t('其它工艺')">
                        <option v-for="d in obsOpts(i).secondary" :key="d.id" :value="d.id">{{ optTxt(d) }}</option>
                      </optgroup>
                    </select>
                  </label>
                  <button class="mini-btn del" :title="t('移除该回路')" :disabled="running || grps.length <= 1" @click.stop="removeGroup(i)">✕</button>
                </div>
                <div class="grp-l2">
                  <label class="sp" @click.stop>
                    <em>{{ t('目标 SP') }}</em>
                    <input class="num" type="number" v-model.number="g.sp" :step="spStep(i)" :disabled="!grpOk(i)" @change="g.touch = true" />
                    <i class="u">{{ obsUnitOf(i) }}</i>
                  </label>
                  <span class="kv"><em>y</em><b class="mono" :style="{ color: cRaw }">{{ fmtNum(yRawOf(i)) }}</b></span>
                  <span class="kv"><em>ỹ</em><b class="mono" :style="{ color: cEkf }">{{ fmtNum(yEkfOf(i)) }}</b></span>
                  <span class="kv" :title="t('EKF 估计的、传感器测不到的机房热扰动 d̂')"><em>d̂</em><b class="mono dim">{{ fmtNum(dHatOf(i)) }}</b></span>
                  <span class="kv"><em>u</em><b class="mono acc">{{ fmtNum(uOf(i)) }}</b></span>
                  <span class="badge-s" :class="stBadge(i)">{{ stTxt(i) }}</span>
                </div>
                <div class="grp-l3" @click.stop>
                  <label class="chk auto"><input type="checkbox" v-model="g.kAuto" :disabled="running" />{{ t('自动整定') }}</label>
                  <span v-if="g.kAuto" class="auto-cfg mono">{{ kCfgTxt(i) }}</span>
                  <template v-else>
                    <label class="kv-g"><em>Kp</em><input class="num k" type="number" step="0.001" :value="g.kp == null ? 0 : g.kp" @input="onPidNum(i, 'kp', $event.target.value)" :disabled="running" /></label>
                    <label class="kv-g"><em>Ki</em><input class="num k" type="number" step="0.001" :value="g.ki == null ? 0 : g.ki" @input="onPidNum(i, 'ki', $event.target.value)" :disabled="running" /></label>
                    <label class="kv-g"><em>Kd</em><input class="num k" type="number" step="0.001" :value="g.kd == null ? 0 : g.kd" @input="onPidNum(i, 'kd', $event.target.value)" :disabled="running" /></label>
                  </template>
                </div>
              </div>
            </div>
          </section>

          <!-- ② 滤波（EKF 为勾选项） -->
          <section class="set-sec">
            <div class="sec-head"><span class="sec-no">2</span><span class="sec-ttl">{{ t('滤波') }}</span></div>
            <div class="flt-line">
              <label class="chk"><input type="checkbox" v-model="ekfOn" :disabled="running" />{{ t('EKF 滤波') }}</label>
              <template v-if="ekfOn">
                <label class="kv-g h"><em>σ<sub>m</sub></em><input class="num w48" type="number" step="0.1" v-model.number="ekfRmPct" :disabled="running" /><i class="u">%</i></label>
                <label class="kv-g h"><em>σ<sub>p</sub></em><input class="num w48" type="number" step="0.1" v-model.number="ekfQpct" :disabled="running" /><i class="u">%</i></label>
              </template>
            </div>
            <p class="hint">{{ t('EKF（二维增广状态）平滑平台实时读数作为 PID 反馈，并估计传感器测不到的机房热扰动 d̂：σm 越大越平滑、σp 越大越跟随；关闭则直接用原始读数作反馈，可在上图 ① 对比滤波效果。') }}</p>
          </section>

          <!-- ③ 运行控制 -->
          <section class="set-sec">
            <div class="sec-head"><span class="sec-no">3</span><span class="sec-ttl">{{ t('运行控制') }}</span></div>
            <div class="run-line">
              <button class="run-btn primary" :disabled="!canRun || trainBusy" @click="toggleRun">{{ running ? t('暂停') : t('开始运行') }}</button>
              <button class="run-btn" :disabled="running || trainBusy || !anyPoints" @click="resetRun">{{ t('复位') }}</button>
              <label class="chk" :title="t('运行中周期把各组 PID 输出写入被调设备真实设定（驱动仿真重算）')">
                <input type="checkbox" v-model="autoApply" :disabled="!canRun || trainBusy" />{{ t('自动下发') }}
              </label>
              <select class="freq" v-model="autoApplyEvery" :disabled="!autoApply || !canRun">
                <option value="tick">{{ t('每周期') }}</option>
                <option value="5s">{{ t('每 5s') }}</option>
              </select>
            </div>
            <div class="run-meta">
              <span>{{ totalPts }} {{ t('点') }} @{{ runHz }}Hz</span>
              <b v-if="convN > 0" class="ok-n">{{ convN }}/{{ grps.length }} {{ t('已收敛') }}</b>
              <button class="mini-btn" :disabled="!running || simBusy" :title="t('把当前各组 PID 输出写入被调设备设定')" @click="applyAll">{{ t('下发设定') }}</button>
            </div>
          </section>
        </aside>

        <!-- ════════════ 右：图（滤波前后对比 / 实时序列 / 训练 / 优化目标变化） ════════════ -->
        <main class="pid-charts">
          <!-- ① 滤波前后左右并列对比 -->
          <section class="ch-card">
            <div class="ch-head">
              <span class="ch-tag">①</span><span class="ch-ttl">{{ t('滤波前后对比') }}</span>
              <span class="ch-sub">{{ ekfOn ? t('左：原始观测 y（滤波前）｜右：EKF 输出 ỹ 与热扰动估计 d̂') : t('EKF 未勾选：左右均为原始观测 y') }}</span>
            </div>
            <div class="cmp-grid">
              <div class="cmp-cell">
                <div class="cmp-h"><i class="lg-dot" :style="{ background: cRaw }"></i>{{ t('滤波前 · 原始观测 y') }}</div>
                <MultiTrendChart v-if="rawChart.length" :series="rawChart" mode="raw" :height="112" :axis="true" />
                <div v-else class="ch-empty sm">{{ t('开始运行后显示') }}</div>
              </div>
              <div class="cmp-cell">
                <div class="cmp-h"><i class="lg-dot" :style="{ background: cEkf }"></i>{{ t('滤波后 · EKF 输出 ỹ') }}</div>
                <MultiTrendChart v-if="ekfChart.length" :series="ekfChart" mode="raw" :height="112" :axis="true" />
                <div v-else class="ch-empty sm">{{ t('开始运行后显示') }}</div>
              </div>
            </div>
          </section>

          <!-- ② 实时序列（当前回路完整实时曲线） -->
          <section class="ch-card">
            <div class="ch-head">
              <span class="ch-tag">②</span><span class="ch-ttl">{{ t('实时序列') }}</span>
              <span class="ch-sub">{{ t('原始观测 y · 叠加目标 SP') }}</span>
              <span class="ch-right" v-if="grps.length > 1">
                <select class="vsel" v-model.number="viewIdx">
                  <option v-for="(g, i) in grps" :key="g.key" :value="i">{{ t('回路') }} {{ i + 1 }}：{{ pairShort(i) }}</option>
                </select>
              </span>
            </div>
            <MultiTrendChart v-if="rawChart.length" :series="rawChart" mode="raw" :height="130" :axis="true" />
            <div v-else class="ch-empty">{{ t('点击左侧「开始运行」开始采集实时序列') }}</div>
          </section>

          <!-- ③ 优化模型控制的训练（占右区大范围） -->
          <section class="ch-card train">
            <div class="ch-head">
              <span class="ch-tag">③</span><span class="ch-ttl">{{ t('优化模型控制的训练') }}</span>
              <span class="ch-badge">{{ dimTxt }}</span>
              <span class="ch-right"><span class="tr-state" :class="{ on: trainBusy }"><i class="dot"></i>{{ trStateTxt }}</span></span>
            </div>
            <div class="tr-bar">
              <span class="seg">
                <button v-for="a in ALGS" :key="a.id" class="seg-btn" :class="{ on: trainAlg === a.id }"
                        :disabled="trainBusy || running" @click="trainAlg = a.id">{{ a.label }}</button>
              </span>
              <label v-if="trainAlg !== 'rl'" class="kv-g h"><em>{{ t('种群') }}</em><input class="num w48" type="number" min="6" max="60" step="2" v-model.number="popSize" :disabled="trainBusy || running" /></label>
              <label class="kv-g h"><em>{{ t('迭代') }}</em><input class="num w48" type="number" min="5" max="200" step="5" v-model.number="maxGen" :disabled="trainBusy || running" /></label>
              <button v-if="trainBusy" class="run-btn stop" @click="stopTrain">{{ t('停止') }}</button>
              <button v-else class="run-btn primary" :disabled="!canRun || running || trainBusy" @click="startTrain">{{ t('开始训练') }}</button>
              <button class="run-btn go" :disabled="!trainBest || running || trainBusy" @click="applyTrain">{{ t('应用最优参数并演示') }}</button>
              <button class="mini-btn" :disabled="trainBusy || !trainCurve.length" @click="clearTrain">{{ t('清空') }}</button>
              <button class="mini-btn set" :class="{ on: !foldSet }" @click="foldSet = !foldSet">{{ t('参数设定') }}{{ foldSet ? ' ▸' : ' ▾' }}</button>
            </div>
            <!-- 算法超参数 + 优化目标权重（按所选算法切换） -->
            <div class="tr-set" v-show="!foldSet">
              <div class="tr-set-row">
                <template v-if="trainAlg === 'ga'">
                  <label class="kv-g h"><em>{{ t('交叉率') }} P<sub>c</sub></em><input class="num w48" type="number" step="0.05" min="0" max="1" v-model.number="gaPc" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>{{ t('变异率') }} P<sub>m</sub></em><input class="num w48" type="number" step="0.02" min="0" max="1" v-model.number="gaPm" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>{{ t('变异幅度') }} σ</em><input class="num w48" type="number" step="0.05" min="0" v-model.number="gaMut" :disabled="lockCfg" /></label>
                </template>
                <template v-else-if="trainAlg === 'pso'">
                  <label class="kv-g h"><em>{{ t('惯性') }} w</em><input class="num w48" type="number" step="0.02" min="0" max="1" v-model.number="psoW" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>{{ t('个体') }} c<sub>1</sub></em><input class="num w48" type="number" step="0.1" min="0" v-model.number="psoC1" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>{{ t('群体') }} c<sub>2</sub></em><input class="num w48" type="number" step="0.1" min="0" v-model.number="psoC2" :disabled="lockCfg" /></label>
                </template>
                <template v-else>
                  <label class="kv-g h"><em>{{ t('学习率') }} lr</em><input class="num w48" type="number" step="0.001" min="0" v-model.number="ppoLr" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>{{ t('裁剪') }} ε</em><input class="num w48" type="number" step="0.05" min="0" max="1" v-model.number="ppoClip" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>{{ t('折扣') }} γ</em><input class="num w48" type="number" step="0.01" min="0" max="1" v-model.number="ppoGamma" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>GAE λ</em><input class="num w48" type="number" step="0.01" min="0" max="1" v-model.number="ppoLam" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>{{ t('熵系数') }}</em><input class="num w48" type="number" step="0.005" min="0" v-model.number="ppoEnt" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>{{ t('更新轮次') }} K</em><input class="num w48" type="number" step="1" min="1" v-model.number="ppoK" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>{{ t('采样轨迹') }}</em><input class="num w48" type="number" step="1" min="1" v-model.number="ppoEps" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>{{ t('探索') }} σ₀</em><input class="num w48" type="number" step="0.05" min="0" v-model.number="ppoSig" :disabled="lockCfg" /></label>
                  <label class="kv-g h" :title="t('训练环境假设：传感器测不到的机房热扰动幅度（随机游走）')"><em>{{ t('热扰动') }} d</em><input class="num w48" type="number" step="0.5" min="0" v-model.number="distPct" :disabled="lockCfg" /><i class="u">%</i></label>
                </template>
              </div>
              <div class="tr-set-row obj">
                <template v-if="trainAlg === 'rl'">
                  <span class="obj-lb">{{ t('奖励') }} r = −( w₁|e| + w₂|Δe| + w₃·{{ t('超调') }} + w₄·{{ t('功耗') }} )</span>
                  <label class="kv-g h"><em>w₁ {{ t('误差') }}</em><input class="num w48" type="number" step="0.1" min="0" v-model.number="rwErr" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>w₂ {{ t('波动') }}</em><input class="num w48" type="number" step="0.05" min="0" v-model.number="rwDe" :disabled="lockCfg" /></label>
                  <label class="kv-g h"><em>w₃ {{ t('超调') }}</em><input class="num w48" type="number" step="0.1" min="0" v-model.number="rwOv" :disabled="lockCfg" /></label>
                  <label class="kv-g h" :title="t('功耗按泵/风机相似定律 P ∝ 转速³ 折算，用于倒逼节能')"><em>w₄ {{ t('功耗') }}</em><input class="num w48" type="number" step="0.1" min="0" v-model.number="rwPow" :disabled="lockCfg" /></label>
                </template>
                <template v-else>
                  <span class="obj-lb">{{ t('优化目标（最小化）') }}</span>
                  <span class="obj-it">{{ t('收敛误差') }}<b>1</b></span>
                  <label class="kv-g h"><em>{{ t('输出能耗') }}</em><input class="num w48" type="number" step="0.5" min="0" v-model.number="lamU" :disabled="lockCfg" /><i class="u">%</i></label>
                  <label class="kv-g h"><em>{{ t('超调') }}</em><input class="num w48" type="number" step="0.5" min="0" v-model.number="lamOv" :disabled="lockCfg" /><i class="u">%</i></label>
                </template>
              </div>
            </div>
            <!-- 本轮训练所用过程模型的来源：在线实时数据辨识 / 数据不足时的先验估计 -->
            <div class="tr-ident" v-if="identInfo.length">
              <span class="id-lb">{{ t('过程模型') }}</span>
              <span class="id-it" v-for="m in identInfo" :key="m.idx">
                {{ t('回路') }} {{ m.idx + 1 }} · <template v-if="m.src === 'ident'">{{ t('在线实时数据辨识') }}（{{ m.n }} {{ t('点') }}）</template><template v-else>{{ t('先验估计：在线数据未呈现足够激励，先让回路运行并产生响应再训练') }}</template> · τ {{ fmtSmall(m.tau) }}s · G {{ fmtSmall(m.G) }}
              </span>
            </div>
            <div class="tr-vis">
              <svg v-if="trainCurve.length > 1" class="tr-svg" :viewBox="`0 0 ${CW} ${CHH}`" preserveAspectRatio="none">
                <line v-for="y in trGrid" :key="'g' + y" class="grid" :x1="0" :x2="CW" :y1="y" :y2="y" />
                <line v-if="trBaseY != null" class="base" :x1="0" :x2="CW" :y1="trBaseY" :y2="trBaseY" />
                <polyline class="cv" :points="trPath" />
              </svg>
              <div v-else-if="trainBusy" class="tr-empty">{{ t('训练准备中…') }}</div>
              <div v-else class="tr-empty">
                <p class="t1">{{ trEmptyT1 }}</p>
                <p class="t2">{{ trEmptyT2 }}</p>
              </div>
              <div class="tr-ax" v-if="trainCurve.length > 1"><span>1</span><span>{{ genN }} {{ t('代') }}</span></div>
            </div>
            <div class="tr-best" v-if="trainBest">
              <div class="tr-sum">
                <span class="gain" :class="{ ok: trainGain > 0 }">{{ t('平均归一误差') }} <b>{{ fmtSmall(trainBest.baseCost) }}</b> → <b>{{ fmtSmall(trainBest.cost) }}</b>（↓{{ trainGain }}%）</span>
                <span class="muted">{{ t('迭代') }} {{ genN }} {{ t('代') }} · {{ t('每代评估') }} {{ popSize }} {{ t('组候选') }}</span>
              </div>
              <div class="tr-rows">
                <div class="tr-row" v-for="d in trainBest.dims" :key="d.idx">
                  <span class="rn">{{ d.idx + 1 }}</span>
                  <span class="rl">{{ d.label }}</span>
                  <span class="rp mono">Kp {{ fmtSmall(d.kp) }} · Ki {{ fmtSmall(d.ki) }} · Kd {{ fmtSmall(d.kd) }}</span>
                </div>
              </div>
            </div>
          </section>

          <!-- ④ 优化目标变化情况：每代最优目标值 + 该代对应的 PID 参数（直接标在图上） -->
          <section class="ch-card">
            <div class="ch-head">
              <span class="ch-tag">④</span><span class="ch-ttl">{{ t('优化目标变化 · PID 参数轨迹') }}</span>
              <span class="ch-sub">{{ t('曲线 = 每代最优目标值；标注 = 该代对应的 Kp / Ki / Kd') }}</span>
              <span class="ch-right">{{ t('回路') }} {{ viewIdx + 1 }}：{{ pairShort(viewIdx) }}</span>
            </div>
            <div class="ov-wrap">
              <svg v-if="trainCurve.length > 1" class="ov-svg" :viewBox="`0 0 ${OVW} ${OVH}`" preserveAspectRatio="none">
                <line v-for="y in trGrid" :key="'o' + y" class="grid" :x1="0" :x2="OVW" :y1="y" :y2="y" />
                <polyline class="cv" :points="ovPath" />
              </svg>
              <template v-if="ovMarks.length">
                <span v-for="m in ovMarks" :key="'d' + m.i" class="ov-dot" :class="{ on: m.best }" :style="{ left: m.x + '%', top: m.y + '%' }"></span>
                <div v-for="m in ovMarks" :key="'t' + m.i" class="ov-tag" :class="{ on: m.best, below: m.y < 26 }"
                     :style="{ left: m.x + '%', top: (m.y < 26 ? m.y + 4 : m.y - 3) + '%' }">
                  <span class="g">{{ t('代') }} {{ m.g }} · {{ fmtSmall(m.cost) }}</span>
                  <span class="p">Kp {{ fmtSmall(m.kp) }} Ki {{ fmtSmall(m.ki) }} Kd {{ fmtSmall(m.kd) }}</span>
                </div>
              </template>
              <div v-if="trainCurve.length <= 1" class="tr-empty">
                <p class="t2">{{ t('完成一次训练后，这里显示优化目标随迭代的变化，以及每代对应的 PID 参数值。') }}</p>
              </div>
            </div>
          </section>
        </main>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, computed, watch, onBeforeUnmount } from 'vue'
import { useSimStore } from '../stores/sim'
import MultiTrendChart from './MultiTrendChart.vue'
import { createPid, createEkf2, gauss } from '../utils/control'
import { createPpoAgent, computeGae, standardize, randn } from '../utils/rl'
import { DEVICE_MAP } from '../data/flowLibrary'
import { t } from '../i18n'

const store = useSimStore()

const props = defineProps({
  // 数据源设备（DataView 拖入的设备列表，用于跟随选择/观测排序）
  devices: { type: Array, default: () => [] },
  curId: { type: String, default: null },
})

// ==================== 设备候选 ====================
const all = computed(() => store.allDevices || [])
const adjOptions = computed(() => all.value.filter((d) => d.adjustable))
const allMetering = computed(() => all.value.filter((d) => !d.adjustable))
const sourceMetering = computed(() => props.devices.filter((d) => !d.adjustable))

function findInfo(id) {
  if (!id) return null
  try { return store.findDevice(id) || null } catch (e) { return null }
}
function findDev(id) {
  const info = findInfo(id)
  return info ? info.device : null
}
function optTxt(d) { return (d.label || d.id) + (d.unit ? `（${d.unit}）` : '') }

function adjSpCfg(id) {
  const d = findDev(id)
  if (!d) return null
  const tmpl = d.type ? DEVICE_MAP[d.type] : null
  return (tmpl && tmpl.setpoint) || d.setpoint || null
}
function obsUnitOf(i) {
  const g = grps[i]
  if (!g) return ''
  const d = findDev(g.obsId)
  return (d && (d.unit || d.unitName)) || ''
}
function gUnit(i) {
  const c = adjSpCfg(grps[i] && grps[i].adjId)
  return (c && c.unit) || ''
}
function grpAdjMin(i) { const c = adjSpCfg(grps[i] && grps[i].adjId); return c ? Number(c.min) : 0 }
function grpAdjMax(i) { const c = adjSpCfg(grps[i] && grps[i].adjId); return c ? Number(c.max) : 1 }
function grpAdjCur(i) {
  const id = grps[i] && grps[i].adjId
  if (!id) return null
  const d = findDev(id)
  if (!d) return null
  const sp = store.deviceSetpoints[id]
  return sp != null ? Number(sp) : (adjSpCfg(id) ? Number(adjSpCfg(id).def) : null)
}
const ginfo = computed(() =>
  grps.map((g) => ({ adj: findDev(g.adjId), obs: findDev(g.obsId), adjInfo: findInfo(g.adjId) })))

// 同工艺观测（unitId 相等优先，其次 unitType；用户拖入的传感器排前）
function obsGroupsOf(adjInfo) {
  const sameUnit = [], sameType = [], rest = []
  for (const d of allMetering.value) {
    if (!adjInfo) { rest.push(d); continue }
    if (d.unitId && adjInfo.unitId && String(d.unitId) === String(adjInfo.unitId)) sameUnit.push(d)
    else if (d.unitType && adjInfo.unitType && String(d.unitType) === String(adjInfo.unitType)) sameType.push(d)
    else rest.push(d)
  }
  const primary = [...sameUnit, ...sameType]
  for (const s of sourceMetering.value) {
    if (!primary.some((d) => d.id === s.id) && !rest.some((d) => d.id === s.id)) primary.push(s)
  }
  const secondary = rest.filter((d) => !primary.some((p) => p.id === d.id))
  return { primary, secondary }
}
function obsOpts(i) { return obsGroupsOf(ginfo.value[i] && ginfo.value[i].adjInfo) }

// 回路默认设备分配：优先不与其他组重复的被调 + 其同工艺观测
function defaultPair() {
  const a = adjOptions.value
  if (!a.length) return { adjId: '', obsId: '' }
  let adjId = a.find((d) => !grps.some((g) => g.adjId === d.id))
  if (!adjId) adjId = a[grps.length % a.length]
  if (!adjId) adjId = a[0]
  const o = obsGroupsOf(findInfo(adjId.id)).primary[0] || allMetering.value[0] || null
  return { adjId: adjId.id, obsId: o ? o.id : '' }
}

// ==================== 回路组 ====================
const MAX_GRP = 8
let keySeq = 0
const grps = reactive([])
const viewIdx = ref(0)
const canAddGrp = computed(() => grps.length < MAX_GRP && grps.length < adjOptions.value.length)

function pushGrp() {
  const d = defaultPair()
  const g = reactive({
    key: 'g' + (++keySeq), adjId: d.adjId, obsId: d.obsId,
    sp: 0, touch: false, kAuto: true, kp: null, ki: null, kd: null,
  })
  grps.push(g)
  return g
}
function addGroup() {
  if (running.value || !canAddGrp.value) return
  pushGrp()
  rebuildRuns()
  clampView()
}
function removeGroup(i) {
  if (running.value || grps.length <= 1) return
  ctx.delete(grps[i].key)
  grps.splice(i, 1)
  rebuildRuns()
  clampView()
}
function clampView() {
  if (viewIdx.value > grps.length - 1) viewIdx.value = Math.max(0, grps.length - 1)
  if (viewIdx.value < 0) viewIdx.value = 0
}

// 读取观测实时值：live → 历史末点 → device.live/reading
function liveRead(id) {
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
function obsLiveOf(i) {
  const g = grps[i]
  return g ? liveRead(g.obsId) : null
}

// ==================== 运行状态 ====================
// 数据源固定为「平台实时读数」：本视图不生成任何模拟/仿真数据，观测真值 y 一律取自实时链路
const ekfOn = ref(true)          // EKF 滤波（勾选项：关闭时 PID 反馈直接用原始观测）
const ekfRmPct = ref(1.5)
const ekfQpct = ref(0.5)

const running = ref(false)
const runHz = ref(1)
const simBusy = ref(false)
const autoApply = ref(false)
const autoApplyEvery = ref('5s')
const cRaw = '#E07B39'
const cEkf = '#3AA655'
const cSp = '#9BB8CE'
const MAX_PTS = 600

// 运行时状态（响应式驱动图表）：rt.runs[i] 与 grps[i] 一一对应
const rt = reactive({ runs: [] })
const ctx = new Map() // g.key -> { pid, kf } 实例
const runModels = {}  // 回路 index -> 在线辨识的过程模型（供 EKF 预测与训练评估使用）
let timer = null
let lastApplyT = 0

function makeRun(i) {
  const g = grps[i]
  const y0v = obsLiveOf(i)
  const y0 = y0v == null ? 0 : y0v
  const scale = Math.max(Math.abs(y0), 1e-3)
  const adjc = grpAdjCur(i)
  const u0 = adjc != null ? adjc : (adjSpCfg(g.adjId) ? Number(adjSpCfg(g.adjId).def) : 0)
  // EKF（二维增广状态）：同时给出滤波值 T̂ 与传感器测不到的热扰动 d̂
  ctx.set(g.key, { pid: createPid(), kf: createEkf2() })
  return reactive({
    y0, scale, u0, uNow: u0, y: y0,
    startT: 0, prevT: 0,
    qv: Math.pow((ekfQpct.value / 100) * scale, 2),           // 过程噪声（T）
    qdv: Math.pow((ekfQpct.value / 100) * scale, 2) * 0.05,   // 扰动随机游走噪声（d，变化更慢）
    rv: Math.pow((ekfRmPct.value / 100) * scale, 2),          // 测量噪声
    lastRaw: null, lastEkf: null, lastD: null, conv: false,
    ptsRaw: [], ptsEkf: [], ptsU: [],
  })
}
function rebuildRuns() {
  rt.runs = grps.map((_, i) => makeRun(i))
}
function resetRun() {
  stopRun(false)
  rebuildRuns()
  // 每组目标默认：设定向可用裕量中点移动对应的稳态观测值（被调贴边界时可反向），无效时 ±5%
  for (let i = 0; i < grps.length; i++) {
    const g = grps[i]
    const r = rt.runs[i]
    if (!r) continue
    const ok = grpOk(i)
    if (!ok) { g.sp = 0; continue }
    if (!g.touch || !Number.isFinite(Number(g.sp)) || Number(g.sp) === 0) {
      const base = r.y0
      const u0c = r.u0
      const uMin = grpAdjMin(i), uMax = grpAdjMax(i)
      let def = null
      const G = effGain(i)
      if (Number.isFinite(u0c) && uMax > uMin && Number.isFinite(G) && G !== 0) {
        const uMid = (uMin + uMax) / 2
        const uT = u0c + 0.5 * (uMid - u0c)
        def = base + (uT - u0c) * G
      }
      if (def == null || !Number.isFinite(def)) def = base !== 0 ? base * 1.05 : 1
      g.sp = Number(def !== 0 ? Number(def.toFixed(4)) : (base !== 0 ? Number((base * 1.05).toFixed(4)) : 1))
    }
    const c = ctx.get(g.key)
    c.pid.reset()
    c.pid.set(pidCfgOf(i))
    c.kf.reset()
  }
  lastApplyT = 0
}

// 有效回路：被调与观测都存在
const grpOk = (i) => {
  const g = grps[i]
  return !!(g && g.adjId && g.obsId && findDev(g.adjId) && findDev(g.obsId))
}
const canRun = computed(() => grps.some((_, i) => grpOk(i)))

// 影响系数 G（自动：被调满量程对应观测约 ±15% 尺度）
function effGain(i) {
  const r = rt.runs[i]
  const s = r ? r.scale : Math.max(Math.abs(obsLiveOf(i) || 0), 1e-3)
  return (0.15 * s) / Math.max(grpAdjMax(i) - grpAdjMin(i), 1e-6)
}

// PID 整定（自动或手动）
function autoPidOf(i) {
  const r = rt.runs[i]
  const uRange = Math.max(grpAdjMax(i) - grpAdjMin(i), 1e-6)
  const sc = r ? r.scale : Math.max(Math.abs(obsLiveOf(i) || 0), 1e-3)
  return { kp: (0.9 * uRange) / sc, ki: (0.9 * uRange) / sc, kd: (0.15 * uRange) / sc, min: grpAdjMin(i), max: grpAdjMax(i) }
}
function pidCfgOf(i) {
  const g = grps[i]
  const min = grpAdjMin(i), max = grpAdjMax(i)
  if (!g || !g.kAuto) {
    return { kp: g && g.kp != null ? g.kp : 0, ki: g && g.ki != null ? g.ki : 0, kd: g && g.kd != null ? g.kd : 0, min, max }
  }
  return autoPidOf(i)
}
function kCfgTxt(i) {
  const c = pidCfgOf(i)
  return `Kp ${fmtSmall(c.kp)} · Ki ${fmtSmall(c.ki)} · Kd ${fmtSmall(c.kd)}`
}
function onPidNum(i, key, raw) {
  const g = grps[i]
  if (!g) return
  g.kAuto = false
  g[key] = Number(raw) || 0
  if (running.value) {
    const c = ctx.get(g.key)
    if (c) c.pid.set(pidCfgOf(i))
  }
}
function onGrpChange(i) {
  if (!running.value) resetRun()
}
function spStep(i) {
  const d = findDev(grps[i] && grps[i].obsId)
  if (d) {
    const base = Math.abs(Number(d.reading) || 1)
    if (base < 10) return 0.1
    if (base < 100) return 1
    return 10
  }
  return 1
}

// ==================== 运行 ====================
function toggleRun() {
  if (running.value) stopRun()
  else startRun()
}
function startRun() {
  if (!canRun.value) return
  // 已有曲线（暂停后继续）则保留历史；首次/复位后开始则清零重跑
  if (!anyPoints.value) resetRun()
  running.value = true
  timer = setInterval(tick, 1000 / runHz.value)
}
function stopRun(clearTimer = true) {
  running.value = false
  if (clearTimer && timer) { clearInterval(timer); timer = null }
}

function tick() {
  const now = performance.now() / 1000
  for (let i = 0; i < grps.length; i++) {
    const g = grps[i]
    const r = rt.runs[i]
    const c = ctx.get(g.key)
    if (!r || !c || !grpOk(i)) continue
    if (!r.prevT) r.prevT = now
    const dti = now - r.prevT
    if (!(dti > 0) || dti > 60) { r.prevT = now; continue }
    r.prevT = now
    const u = r.uNow != null ? Number(r.uNow) : r.u0

    // —— 观测真值 y：直接取平台实时读数（本视图不做任何数据合成；无读数则该回路本周期跳过） ——
    const live = obsLiveOf(i)
    if (live == null) {
      r.lastRaw = null
      r.lastEkf = null
      r.conv = false
      continue
    }
    const yRaw = Number(live)

    // —— EKF：滤波 T̂ + 估计热扰动 d̂（勾选生效；未勾选则反馈 = 原始观测） ——
    let yEkf = yRaw
    let dHat = null
    if (ekfOn.value) {
      const m = runModels[i] || null // 有在线辨识的过程模型时用它做预测，否则退化为「常值 + 扰动」
      const est = c.kf.step(yRaw, u, {
        a: m ? m.a : 1, b: m ? m.b : 0, c: m ? m.c : 0,
        qT: r.qv, qd: r.qdv, r: r.rv,
      })
      yEkf = est.t
      dHat = est.d
    } else if (c.kf.t != null) {
      c.kf.reset() // 关闭期间不留陈旧状态，再次勾选时从头滤波
    }

    // —— PID 输出 ——
    const pidOut = c.pid.step(Number(g.sp) || 0, yEkf, dti)
    let uOut = pidOut.u
    if (uOut == null || !Number.isFinite(uOut)) uOut = r.u0

    r.uNow = uOut
    r.lastRaw = yRaw
    r.lastEkf = yEkf
    r.lastD = dHat
    r.conv = Math.abs((Number(g.sp) || 0) - yEkf) <= Math.max(r.scale * 0.01, 1e-6)
    r.ptsRaw.push({ t: now, v: yRaw })
    r.ptsEkf.push({ t: now, v: yEkf })
    r.ptsU.push({ t: now, v: uOut })
    trimPts(r)
    // 每积累 20 个点尝试用在线数据重新辨识过程模型，供 EKF 预测与训练使用
    if (r.ptsRaw.length % 20 === 0) {
      const mm = identifyModel(i)
      if (mm) runModels[i] = mm
    }
  }

  // —— 自动下发：周期把各组 PID 输出写入真实设定（驱动仿真重算联动） ——
  if (autoApply.value) {
    const every = autoApplyEvery.value === 'tick' ? 0 : 5 // 秒
    if (!lastApplyT || now - lastApplyT >= every) {
      lastApplyT = now
      applyAllToStore()
    }
  }
  if (!rt.runs.some((r) => r != null)) stopRun()
}
function trimPts(r) {
  if (r.ptsRaw.length > MAX_PTS) {
    const cut = r.ptsRaw.length - MAX_PTS
    r.ptsRaw.splice(0, cut)
    r.ptsEkf.splice(0, cut)
    r.ptsU.splice(0, cut)
  }
}
function applyAllToStore() {
  for (let i = 0; i < grps.length; i++) {
    const g = grps[i]
    const r = rt.runs[i]
    if (!grpOk(i) || !r) continue
    store.setDeviceSetpoint(g.adjId, r.uNow != null ? r.uNow : r.u0)
  }
}
async function applyAll() {
  if (!running.value) return
  simBusy.value = true
  try { applyAllToStore() } finally { simBusy.value = false }
}

// ==================== 展示数值 ====================
function uOf(i) { const r = rt.runs[i]; return r ? r.uNow : (grps[i] ? grpAdjCur(i) : null) }
function yRawOf(i) { const r = rt.runs[i]; return r ? r.lastRaw : (grps[i] ? obsLiveOf(i) : null) }
function yEkfOf(i) { const r = rt.runs[i]; return r ? r.lastEkf : (grps[i] ? obsLiveOf(i) : null) }
function dHatOf(i) { const r = rt.runs[i]; return r ? r.lastD : null }
const totalPts = computed(() => (rt.runs.length && rt.runs[0] ? rt.runs[0].ptsRaw.length : 0))
const anyPoints = computed(() => totalPts.value > 0)
const convN = computed(() => rt.runs.reduce((n, r) => n + (r && r.conv ? 1 : 0), 0))
const stateCls = computed(() => {
  if (!running.value) return 'idle'
  return convN.value >= grps.length && grps.length ? 'ok' : 'busy'
})
const stateText = computed(() => {
  if (!running.value) return t('就绪')
  return convN.value >= grps.length && grps.length ? t('运行中 · 全部观测已收敛至目标') : t('运行中 · 调节中')
})
function stBadge(i) {
  if (!grpOk(i)) return 'na'
  const r = rt.runs[i]
  if (!running.value || !r) return 'idle'
  if (r.lastRaw == null) return 'na'   // 实时链路暂无读数
  return r.conv ? 'ok' : 'busy'
}
function stTxt(i) {
  if (!grpOk(i)) return t('无效')
  const r = rt.runs[i]
  if (!running.value || !r) return t('就绪')
  if (r.lastRaw == null) return t('无数据')
  return r.conv ? t('已收敛') : t('调节中')
}

// ==================== 曲线 series ====================
function spLine(r, sp) {
  if (!r || !r.ptsRaw.length) return []
  return [{ t: r.ptsRaw[0].t, v: sp }, { t: r.ptsRaw[r.ptsRaw.length - 1].t, v: sp }]
}
const curRun = computed(() => rt.runs[viewIdx.value] || null)
const rawChart = computed(() => {
  const r = curRun.value
  if (!r || !r.ptsRaw.length) return []
  const g = grps[viewIdx.value]
  const u = obsUnitOf(viewIdx.value)
  return [
    { id: 'raw', label: t('原始观测 y'), color: cRaw, unit: u, pts: r.ptsRaw },
    { id: 'sp', label: 'SP', color: cSp, unit: u, pts: spLine(r, g ? Number(g.sp) || 0 : 0) },
  ]
})
const ekfChart = computed(() => {
  const r = curRun.value
  if (!r || !r.ptsEkf.length) return []
  const g = grps[viewIdx.value]
  const u = obsUnitOf(viewIdx.value)
  return [
    { id: 'ekf', label: 'ỹ', color: cEkf, unit: u, pts: r.ptsEkf },
    { id: 'sp', label: 'SP', color: cSp, unit: u, pts: spLine(r, g ? Number(g.sp) || 0 : 0) },
  ]
})

// ==================== 文字 ====================
function pairTxt(i) {
  const g = grps[i]
  if (!g) return ''
  const a = findDev(g.adjId), o = findDev(g.obsId)
  const at = a ? (a.label || a.id) : (g.adjId || '—')
  const ot = o ? (o.label || o.id) : (g.obsId || '—')
  return at + ' → ' + ot
}
function pairShort(i) { return pairTxt(i) }
function fmtSmall(v) {
  if (v == null || !Number.isFinite(v)) return '0'
  if (Math.abs(v) >= 100) return v.toFixed(1)
  if (Math.abs(v) >= 1) return v.toFixed(2)
  return v.toFixed(4)
}
function fmtNum(v, d = 1) {
  if (v == null || !Number.isFinite(v)) return '—'
  const abs = Math.abs(v)
  const digits = abs >= 1000 ? 0 : abs >= 10 ? 1 : 2
  return v.toLocaleString('zh-CN', { maximumFractionDigits: Math.max(d, digits) })
}

// ==================== 优化模型控制的训练：以 PID 参数为决策变量 ====================
// 无论选择哪种算法，训练的都是「控制参数」本身：每个可调设备（回路）= Kp/Ki/Kd 三个参数，
// N 个可调设备 → 3N 维决策变量。搜索的是相对当前整定值的倍率系数（×0.1 ~ ×6）。
const ALGS = [
  { id: 'ga', label: t('遗传算法') },
  { id: 'pso', label: t('粒子群') },
  { id: 'rl', label: t('强化学习') },
]
const COEF_LO = 0.1
const COEF_HI = 6
const IDENT_MIN = 12 // 过程模型辨识所需的最少在线闭环采样点（u, y 配对）

const trainAlg = ref('ga')
const popSize = ref(14)
const maxGen = ref(24)
// 算法超参数（按所选算法生效）与优化目标权重
const foldSet = ref(false)   // false = 展开参数设定
const gaPc = ref(0.9)        // 遗传算法：交叉率
const gaPm = ref(0.12)       // 遗传算法：变异率
const gaMut = ref(0.3)       // 遗传算法：变异幅度（标准差）
const psoW = ref(0.72)       // 粒子群：惯性权重
const psoC1 = ref(1.5)       // 粒子群：个体学习因子
const psoC2 = ref(1.5)       // 粒子群：群体学习因子
const lamU = ref(2)          // 优化目标权重（GA/PSO）：输出能耗（相对设定初值的偏离）%
const lamOv = ref(3)         // 优化目标权重（GA/PSO）：超调惩罚 %
// —— 强化学习（PPO）超参 ——
const ppoLr = ref(3e-3)      // 学习率
const ppoClip = ref(0.2)     // PPO 裁剪系数 ε
const ppoGamma = ref(0.99)   // 折扣因子 γ
const ppoLam = ref(0.95)     // GAE λ
const ppoEnt = ref(0.01)     // 熵奖励系数
const ppoK = ref(4)          // 每轮更新 epoch 数
const ppoEps = ref(4)        // 每轮每条回路采样轨迹数
const ppoSig = ref(0.4)      // 初始探索幅度 σ₀
const distPct = ref(2)       // 训练环境假设：未建模热扰动幅度（观测尺度 %）
// —— 奖励权重：r = −(w₁|e| + w₂|Δe| + w₃·超调 + w₄·功耗) ——
const rwErr = ref(1)         // w₁ 跟踪误差
const rwDe = ref(0.1)        // w₂ 误差变化（波动）
const rwOv = ref(0.5)        // w₃ 超调
const rwPow = ref(0.3)       // w₄ 设备功耗（节能核心）
const lockCfg = computed(() => running.value || trainBusy.value)
const trainBusy = ref(false)
const trainStop = ref(false)
const genN = ref(0)
const trainCurve = ref([])  // [{ g, best }]
const trainBest = ref(null) // { coef, cost, baseCost, dims }
const identInfo = ref([])   // 本轮训练所用过程模型（由在线数据辨识 / 先验估计）

const validN = computed(() => grps.reduce((n, _, i) => n + (grpOk(i) ? 1 : 0), 0))
const dimTxt = computed(() => `${t('决策维度')} ${validN.value} × 3 = ${validN.value * 3} ${t('维（Kp·Ki·Kd）')}`)
const trStateTxt = computed(() => {
  if (trainBusy.value) return `${t('训练中')} ${genN.value}/${maxGen.value} ${t('代')}`
  if (!trainCurve.value.length) return t('未训练')
  return `${t('已完成')} ${genN.value} ${t('代')}`
})
const trEmptyT1 = computed(() => {
  if (trainAlg.value === 'ga') return t('遗传算法：以每组回路 Kp/Ki/Kd 为基因，锦标赛选择 + 交叉变异逐代进化')
  if (trainAlg.value === 'pso') return t('粒子群：每个粒子是一组 PID 参数，个体最优与群体最优共同引导收敛')
  return t('强化学习 PPO：状态 s = [T̂, e, Δe, d̂] 全部取自 EKF（含传感器测不到的热扰动 d̂），动作 a = [Kp, Ki, Kd] 动态整定，奖励同时惩罚误差 / 波动 / 超调 / 设备功耗')
})
const trEmptyT2 = computed(() =>
  `${t('目标：多回路收敛误差（归一化）+ 输出能耗最小；')}${t('训练在「由在线实时数据辨识出的一阶过程模型」上离线寻优（平台不内置任何模拟数据），不影响正在运行的曲线。')}`)
const trainGain = computed(() => {
  const b = trainBest.value
  if (!b || !b.baseCost) return 0
  return Math.max(0, Math.round((1 - b.cost / b.baseCost) * 100))
})

const CW = 360
const CHH = 100
const trGrid = [0, 25, 50, 75, 100]
const trScale = computed(() => {
  const c = trainCurve.value
  const vals = c.map((p) => p.best)
  if (trainBest.value) vals.push(trainBest.value.baseCost)
  if (!vals.length) return { lo: 0, hi: 1 }
  let lo = Math.min(...vals), hi = Math.max(...vals)
  const pad = (hi - lo) * 0.08 || 1e-6
  return { lo: lo - pad, hi: hi + pad }
})
function trY(v) {
  const { lo, hi } = trScale.value
  return CHH - ((Number(v) - lo) / (hi - lo || 1)) * CHH
}
const trPath = computed(() => {
  const c = trainCurve.value
  if (c.length < 2) return ''
  return c.map((p, i) => `${((i / (c.length - 1)) * CW).toFixed(1)},${trY(p.best).toFixed(1)}`).join(' ')
})
const trBaseY = computed(() => (trainBest.value ? trY(trainBest.value.baseCost) : null))

// ==================== ④ 优化目标变化 · PID 参数轨迹 ====================
// 曲线 = 每代最优目标值；在等距采样点 + 末代 + 最优代上标出该代对应的 Kp/Ki/Kd
const OVW = 360
const OVH = 100
const curveVal = (p) => (p.best != null ? p.best : p.cost)
const ovScale = computed(() => {
  const vals = trainCurve.value.map(curveVal)
  if (!vals.length) return { lo: 0, hi: 1 }
  let lo = Math.min(...vals), hi = Math.max(...vals)
  const pad = (hi - lo) * 0.08 || 1e-6
  return { lo: lo - pad, hi: hi + pad }
})
function ovY(v) {
  const { lo, hi } = ovScale.value
  return OVH - ((Number(v) - lo) / (hi - lo || 1)) * OVH
}
const ovPath = computed(() => {
  const c = trainCurve.value
  if (c.length < 2) return ''
  return c.map((p, i) => `${((i / (c.length - 1)) * OVW).toFixed(1)},${ovY(curveVal(p)).toFixed(1)}`).join(' ')
})
const ovMarks = computed(() => {
  const c = trainCurve.value
  if (c.length < 2) return []
  let bi = 0
  for (let i = 1; i < c.length; i++) if (curveVal(c[i]) < curveVal(c[bi])) bi = i
  const step = Math.max(1, Math.ceil(c.length / 6))
  const picks = []
  for (let i = 0; i < c.length; i += step) picks.push(i)
  if (picks[picks.length - 1] !== c.length - 1) picks.push(c.length - 1)
  if (!picks.includes(bi)) picks.push(bi)
  picks.sort((a, b) => a - b)
  return picks.map((i) => {
    const p = c[i]
    const v = curveVal(p)
    const d = (p.dims || []).find((x) => x.idx === viewIdx.value) || (p.dims || [])[0] || null
    return {
      i, g: p.g, cost: v, best: i === bi,
      x: (i / (c.length - 1)) * 100,   // 百分比，供 HTML 标注定位
      y: ovY(v),
      kp: d ? d.kp : null, ki: d ? d.ki : null, kd: d ? d.kd : null,
    }
  })
})

function clamp(v, lo, hi) { return v < lo ? lo : (v > hi ? hi : v) }
function randCoef(D) { return Array.from({ length: D }, () => COEF_LO + Math.random() * (COEF_HI - COEF_LO)) }

// 基准整定值（训练搜索的出发点：系数 1 = 当前整定值）
function basePids() {
  return grps.map((_, i) => {
    const a = autoPidOf(i)
    const m = pidCfgOf(i)
    return {
      kp: m.kp > 0 ? m.kp : a.kp,
      ki: m.ki > 0 ? m.ki : a.ki,
      kd: m.kd > 0 ? m.kd : a.kd,
    }
  })
}

// ==================== 过程模型：由在线实时数据辨识（平台不内置任何模拟数据） ====================
// 用回路运行期间采集到的 (u, y) 闭环采样，最小二乘拟合一阶离散模型：
//     y[k+1] = a·y[k] + b·u[k] + c
// 由 a 反解时间常数 τ = -Δt / ln(a)，由 b 反解稳态增益 G = b / (1 - a)。
function solve3(M, v) {
  const A = [M[0].slice(), M[1].slice(), M[2].slice()]
  const b = v.slice()
  for (let c = 0; c < 3; c++) {
    let p = c
    for (let r = c + 1; r < 3; r++) if (Math.abs(A[r][c]) > Math.abs(A[p][c])) p = r
    if (Math.abs(A[p][c]) < 1e-12) return null
    const tr = A[c]; A[c] = A[p]; A[p] = tr
    const tb = b[c]; b[c] = b[p]; b[p] = tb
    for (let r = 0; r < 3; r++) {
      if (r === c) continue
      const f = A[r][c] / A[c][c]
      for (let k = c; k < 3; k++) A[r][k] -= f * A[c][k]
      b[r] -= f * b[c]
    }
  }
  return [b[0] / A[0][0], b[1] / A[1][1], b[2] / A[2][2]]
}

function identifyModel(i) {
  const r = rt.runs[i]
  if (!r) return null
  const n = Math.min(r.ptsRaw.length, r.ptsU.length)
  if (n < IDENT_MIN) return null
  let Syy = 0, Syu = 0, Sy1 = 0, Suu = 0, Su1 = 0, S11 = 0, Syt = 0, Sut = 0, St1 = 0
  for (let k = 0; k < n - 1; k++) {
    const yk = Number(r.ptsRaw[k].v), uk = Number(r.ptsU[k].v), yn = Number(r.ptsRaw[k + 1].v)
    if (!Number.isFinite(yk) || !Number.isFinite(uk) || !Number.isFinite(yn)) continue
    Syy += yk * yk; Syu += yk * uk; Sy1 += yk; Suu += uk * uk; Su1 += uk; S11 += 1
    Syt += yk * yn; Sut += uk * yn; St1 += yn
  }
  if (S11 < IDENT_MIN) return null
  const sol = solve3([[Syy, Syu, Sy1], [Syu, Suu, Su1], [Sy1, Su1, S11]], [Syt, Sut, St1])
  if (!sol) return null
  const [a, b, c] = sol
  if (!(a > 0.02 && a < 0.9995) || !Number.isFinite(b)) return null
  const dt = Math.max(0.1, (r.ptsRaw[n - 1].t - r.ptsRaw[0].t) / (n - 1))
  return { a, b, c, dt, n, src: 'ident', tau: -dt / Math.log(a), G: b / (1 - a) }
}

// 在线数据不足时的先验估计（仅作为整定计算的初始猜测，不产生任何数据）
function priorModel(i) {
  const r = rt.runs[i]
  const scale = r ? r.scale : Math.max(Math.abs(obsLiveOf(i) || 0), 1e-3)
  const uRange = Math.max(grpAdjMax(i) - grpAdjMin(i), 1e-6)
  const G = (0.15 * scale) / uRange
  const tau = 4
  const dt = 1
  const a = Math.exp(-dt / tau)
  const u0 = r ? r.u0 : 0
  const y0 = r ? r.y0 : 0
  return { a, b: G * (1 - a), c: y0 * (1 - a) - G * (1 - a) * u0, dt, n: 0, src: 'prior', tau, G }
}

function buildModels() {
  return grps.map((_, i) => (grpOk(i) ? (identifyModel(i) || priorModel(i)) : null))
}
// 评估窗口步数：覆盖约 5 个时间常数
function simSteps(models) {
  let dt = 1, maxTau = 1
  for (const m of models) {
    if (!m) continue
    dt = Math.max(dt, m.dt || 1)
    if (m.tau > 0) maxTau = Math.max(maxTau, m.tau)
  }
  return Math.min(240, Math.max(30, Math.ceil((5 * maxTau) / dt)))
}

// 单组候选评估：在辨识出的过程模型上离线重放闭环 → 平均归一误差（含能耗/超调惩罚）
function evalCost(coef, base, models, steps) {
  const sims = []
  for (let i = 0; i < grps.length; i++) {
    const g = grps[i]
    const m = models[i]
    if (!m || !grpOk(i) || !Number.isFinite(Number(g.sp))) continue
    const y0v = Number(obsLiveOf(i) ?? 0)
    const scale = Math.max(Math.abs(y0v), 1e-3)
    const u0c = grpAdjCur(i)
    const u0 = u0c != null ? Number(u0c) : 0
    const uMin = grpAdjMin(i), uMax = grpAdjMax(i)
    const uRange = Math.max(uMax - uMin, 1e-6)
    const b = base[i]
    const pid = createPid({
      kp: b.kp * (coef[i * 3] ?? 1),
      ki: b.ki * (coef[i * 3 + 1] ?? 1),
      kd: b.kd * (coef[i * 3 + 2] ?? 1),
      min: uMin, max: uMax,
    })
    pid.reset()
    sims.push({ y0: y0v, u0, u: u0, y: y0v, scale, uRange, sp: Number(g.sp), pid, m })
  }
  if (!sims.length) return 1e9
  let cost = 0
  const wu = (Number(lamU.value) || 0) / 100     // 输出能耗惩罚
  const wov = (Number(lamOv.value) || 0) / 100   // 超调惩罚
  for (let k = 0; k < steps; k++) {
    for (const s of sims) {
      // 辨识得到的一阶离散模型：y⁺ = a·y + b·u + c
      s.y = s.m.a * s.y + s.m.b * s.u + s.m.c
      const e = s.sp - s.y
      const out = s.pid.step(s.sp, s.y, s.m.dt)
      s.u = out.u
      // 超调：沿目标方向越过 SP 后继续超出的量
      const dir = Math.sign(s.sp - s.y0) || 1
      const ov = Math.max(0, (s.y - s.sp) * dir)
      cost += Math.abs(e) / s.scale + wu * Math.abs(s.u - s.u0) / s.uRange + wov * ov / s.scale
    }
  }
  return cost / (sims.length * steps)
}

// —— 遗传算法 ——
function gaNext(pop, fits, size) {
  const scored = pop.map((c, i) => ({ c, f: fits[i] })).sort((a, b) => a.f - b.f)
  const pick = () => {
    const a = scored[Math.floor(Math.random() * scored.length)]
    const b = scored[Math.floor(Math.random() * scored.length)]
    return a.f <= b.f ? a.c : b.c
  }
  const pc = Number(gaPc.value) || 0
  const pm = Number(gaPm.value) || 0
  const mut = Number(gaMut.value) || 0
  const next = [scored[0].c.slice()]
  while (next.length < size) {
    const p1 = pick(), p2 = pick()
    const cross = Math.random() < pc
    const c = p1.map((v, j) => (cross && Math.random() < 0.5 ? p2[j] : v))
    for (let j = 0; j < c.length; j++) {
      if (Math.random() < pm) c[j] = clamp(c[j] + gauss() * mut, COEF_LO, COEF_HI)
    }
    next.push(c)
  }
  return next
}
// —— 粒子群 ——
function initPso(D, P) {
  const xs = [], vs = [], pbs = [], pbf = []
  for (let p = 0; p < P; p++) {
    const x = randCoef(D)
    xs.push(x)
    vs.push(Array.from({ length: D }, () => (Math.random() - 0.5) * 0.4))
    pbs.push(x.slice())
    pbf.push(Infinity)
  }
  return { xs, vs, pbs, pbf, gb: xs[0].slice(), gbf: Infinity }
}
function psoStep(st, coefs, fits) {
  const D = st.xs[0].length
  for (let p = 0; p < st.xs.length; p++) {
    if (fits[p] < st.pbf[p]) { st.pbf[p] = fits[p]; st.pbs[p] = coefs[p].slice() }
    if (fits[p] < st.gbf) { st.gbf = fits[p]; st.gb = coefs[p].slice() }
  }
  const w = Number(psoW.value) || 0
  const c1 = Number(psoC1.value) || 0
  const c2 = Number(psoC2.value) || 0
  const vmax = (COEF_HI - COEF_LO) * 0.25
  for (let p = 0; p < st.xs.length; p++) {
    for (let j = 0; j < D; j++) {
      const r1 = Math.random(), r2 = Math.random()
      let v = w * st.vs[p][j] + c1 * r1 * (st.pbs[p][j] - st.xs[p][j]) + c2 * r2 * (st.gb[j] - st.xs[p][j])
      v = clamp(v, -vmax, vmax)
      st.vs[p][j] = v
      st.xs[p][j] = clamp(st.xs[p][j] + v, COEF_LO, COEF_HI)
    }
  }
}
// —— 强化学习：PPO（近端策略优化）动态整定 PID 参数 ——
//   状态 s = [T̂, e, Δe, d̂]：全部来自 EKF 的纯净估计，d̂ 为传感器测不到的机房热扰动
//   动作 a = [a_p, a_i, a_d] → K = K₀ · exp(clip(a, ±1.6))，即 0.2 ~ 5 倍基准参数
//   奖励 r = −(w₁|e| + w₂|Δe| + w₃·超调 + w₄·功耗)
//   功耗按泵/风机相似定律 P ∝ 转速³ 折算，直接惩罚设备功耗，倒逼在达标前提下最小化能耗
const ACT_CLIP = 1.6

// 单条轨迹：在辨识出的过程模型上闭环仿真，同时用二维 EKF 估计 T̂ 与热扰动 d̂
function ppoRollout(agent, m, steps, b0, g, gi, deterministic = false) {
  const scale = Math.max(Math.abs(Number(obsLiveOf(gi) ?? 0)), 1e-3)
  const u0c = grpAdjCur(gi)
  const u0 = u0c != null ? Number(u0c) : 0
  const uMin = grpAdjMin(gi), uMax = grpAdjMax(gi)
  const uMaxAbs = Math.max(Math.abs(uMax), Math.abs(uMin), 1e-6)
  const sp = Number(g.sp) || 0
  const y0 = Number(obsLiveOf(gi) ?? 0)
  const dir = Math.sign(sp - y0) || 1
  const dt = m.dt || 1
  const qT = Math.pow((ekfQpct.value / 100) * scale, 2)
  const qd = qT * 0.05
  const rv = Math.pow((ekfRmPct.value / 100) * scale, 2)
  const dStd = ((Number(distPct.value) || 0) / 100) * scale // 训练环境假设：未建模热扰动随机游走幅度

  const pid = createPid({ min: uMin, max: uMax })
  pid.reset()
  const kf = createEkf2({ qT, qd, r: rv })
  let T = y0, u = u0, d = 0, ePrev = 0
  const s = [], acts = [], logps = [], rews = [], vals = []
  const actSum = new Float64Array(3)
  let costSum = 0
  for (let k = 0; k < steps; k++) {
    d += randn() * dStd                  // 机房热扰动（传感器测不到的未建模动态）
    T = m.a * T + m.b * u + m.c + d      // 过程真实演化
    const est = kf.step(T, u, { a: m.a, b: m.b, c: m.c, qT, qd, r: rv })
    const e = sp - est.t
    const de = e - ePrev
    ePrev = e
    const st = new Float64Array([est.t / scale, e / scale, de / scale, est.d / scale])
    const out = agent.act(st, deterministic)
    pid.set({
      kp: b0.kp * Math.exp(clamp(out.a[0], -ACT_CLIP, ACT_CLIP)),
      ki: b0.ki * Math.exp(clamp(out.a[1], -ACT_CLIP, ACT_CLIP)),
      kd: b0.kd * Math.exp(clamp(out.a[2], -ACT_CLIP, ACT_CLIP)),
      min: uMin, max: uMax,
    })
    u = pid.step(sp, est.t, dt).u
    const power = Math.pow(Math.abs(u) / uMaxAbs, 3)   // 功耗：P ∝ 转速³
    const ov = Math.max(0, (T - sp) * dir) / scale
    const r = -(rwErr.value * Math.abs(e) / scale
      + rwDe.value * Math.abs(de) / scale
      + rwOv.value * ov
      + rwPow.value * power)
    s.push(st)
    acts.push(out.a)
    logps.push(out.logp)
    rews.push(r)
    vals.push(agent.value(st))
    for (let q = 0; q < 3; q++) actSum[q] += out.a[q]
    costSum += -r
  }
  const lastVal = s.length ? agent.value(s[s.length - 1]) : 0
  return {
    s, a: acts, logp: logps, rews, vals, lastVal,
    meanCost: costSum / Math.max(1, steps), actSum, steps,
  }
}

// 一轮迭代：各回路采样若干轨迹 → GAE 优势 → PPO 更新 → 确定性评估
function ppoIterate(agent, models, steps, base) {
  const trans = []
  for (let i = 0; i < grps.length; i++) {
    const m = models[i]
    if (!m || !grpOk(i)) continue
    for (let e = 0; e < ppoEps.value; e++) {
      const ep = ppoRollout(agent, m, steps, base[i], grps[i], i)
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
  return ppoEvaluate(agent, models, steps, base)
}

// 确定性评估：平均代价 + 平均动作换算成的参数倍率（与 GA/PSO 的 coef 语义一致）
function ppoEvaluate(agent, models, steps, base) {
  const D = grps.length * 3
  const coef = new Array(D).fill(1)
  let cost = 0, n = 0
  for (let i = 0; i < grps.length; i++) {
    const m = models[i]
    if (!m || !grpOk(i)) continue
    const ep = ppoRollout(agent, m, steps, base[i], grps[i], i, true)
    cost += ep.meanCost
    n++
    for (let q = 0; q < 3; q++) {
      coef[i * 3 + q] = Math.exp(clamp(ep.actSum[q] / Math.max(1, ep.steps), -ACT_CLIP, ACT_CLIP))
    }
  }
  return { cost: n ? cost / n : 1e9, coef }
}

function coefDims(coef) {
  const base = basePids()
  const out = []
  for (let i = 0; i < grps.length; i++) {
    if (!grpOk(i)) continue
    const b = base[i]
    out.push({
      idx: i,
      label: pairShort(i),
      kp: b.kp * (coef[i * 3] ?? 1),
      ki: b.ki * (coef[i * 3 + 1] ?? 1),
      kd: b.kd * (coef[i * 3 + 2] ?? 1),
    })
  }
  return out
}

function clearTrain() {
  if (trainBusy.value) return
  trainCurve.value = []
  trainBest.value = null
  genN.value = 0
}
function stopTrain() {
  trainStop.value = true
}

async function startTrain() {
  if (running.value || trainBusy.value || !validN.value) return
  const base = basePids()
  const D = grps.length * 3
  // 先用在线实时数据辨识各回路过程模型（不足则退回先验估计）
  const models = buildModels()
  const steps = simSteps(models)
  identInfo.value = models
    .map((m, i) => (m && grpOk(i) ? { idx: i, src: m.src, n: m.n, tau: m.tau, G: m.G } : null))
    .filter(Boolean)
  trainBusy.value = true
  trainStop.value = false
  trainCurve.value = []
  trainBest.value = null
  genN.value = 0

  const baseCost = evalCost(new Array(D).fill(1), base, models, steps)
  let gBest = { coef: new Array(D).fill(1), cost: baseCost }
  let gaPop = null, pso = null, rl = null

  for (let gen = 1; gen <= maxGen.value && !trainStop.value; gen++) {
    if (trainAlg.value === 'rl') {
      // —— PPO：一轮 = 各回路采样轨迹 + GAE + 多次 epoch 更新 + 确定性评估 ——
      if (!rl) {
        rl = createPpoAgent({ sDim: 4, aDim: 3, hidden: 16, lr: ppoLr.value, sigma0: ppoSig.value })
      }
      const it = ppoIterate(rl, models, steps, base)
      if (it.cost < gBest.cost) gBest = { coef: it.coef.slice(), cost: it.cost }
      genN.value = gen
      trainCurve.value.push({ g: gen, best: it.cost, dims: coefDims(it.coef) })
    } else {
      let coefs = []
      if (trainAlg.value === 'ga') {
        if (!gaPop) gaPop = Array.from({ length: popSize.value }, () => randCoef(D))
        coefs = gaPop
      } else {
        if (!pso) pso = initPso(D, popSize.value)
        coefs = pso.xs.map((c) => c.slice())
      }
      const fits = coefs.map((c) => evalCost(c, base, models, steps))
      let bi = 0
      for (let k = 1; k < fits.length; k++) if (fits[k] < fits[bi]) bi = k
      if (fits[bi] < gBest.cost) gBest = { coef: coefs[bi].slice(), cost: fits[bi] }
      genN.value = gen
      // 记录该代最优目标值及其对应的 PID 参数，供「优化目标变化」图在曲线上标注
      trainCurve.value.push({ g: gen, best: fits[bi], dims: coefDims(coefs[bi]) })

      if (trainAlg.value === 'ga') gaPop = gaNext(gaPop, fits, popSize.value)
      else psoStep(pso, coefs, fits)
    }

    await new Promise((r) => setTimeout(r, 0)) // 让出主线程，曲线逐代刷新
  }

  trainBusy.value = false
  trainBest.value = { coef: gBest.coef.slice(), cost: gBest.cost, baseCost, dims: coefDims(gBest.coef) }
}

// 训练得到的最优 PID 参数写回各组回路，并立即运行演示
function applyTrain() {
  const b = trainBest.value
  if (!b || running.value || trainBusy.value) return
  for (const d of b.dims) {
    const g = grps[d.idx]
    if (!g) continue
    g.kAuto = false
    g.kp = Number(d.kp.toFixed(6))
    g.ki = Number(d.ki.toFixed(6))
    g.kd = Number(d.kd.toFixed(6))
  }
  resetRun()
  startRun()
}

// ==================== 设备跟随与初始化 ====================
function syncFromSelection() {
  if (running.value) return
  let changed = false
  const cur = props.devices.find((d) => d.id === props.curId) || null
  if (cur && grps.length) {
    const g0 = grps[0]
    if (cur.adjustable) { if (g0.adjId !== cur.id) { g0.adjId = cur.id; g0.touch = false; changed = true } }
    else if (cur.id !== g0.obsId && allMetering.value.some((d) => d.id === cur.id)) {
      g0.obsId = cur.id; g0.touch = false; changed = true
    }
  }
  if (!adjOptions.value.length || !grps.length) return
  // 每组设备有效性校正
  grps.forEach((g, i) => {
    if (!g.adjId || !adjOptions.value.some((d) => d.id === g.adjId)) {
      const d = defaultPair()
      g.adjId = d.adjId; g.obsId = d.obsId; g.touch = false; changed = true
    }
    if (!g.obsId || !allMetering.value.some((d) => d.id === g.obsId)) {
      const info = findInfo(g.adjId)
      const pick = obsGroupsOf(info).primary[0] || (allMetering.value.length ? allMetering.value[0] : null)
      if (pick && pick.id !== g.obsId) { g.obsId = pick.id; g.touch = false; changed = true }
    }
  })
  if (changed) resetRun()
}
watch(
  [() => props.curId, () => props.devices.length, () => adjOptions.value.length, () => allMetering.value.length],
  () => syncFromSelection(),
  { immediate: true }
)
// 回路配置 / 目标变化 → 已训练结果失效（需基于新配置重训）
watch(
  () => grps.map((g) => `${g.adjId}|${g.obsId}|${g.sp}`).join(';'),
  () => clearTrain()
)
// EKF 开关切换：重置滤波状态，避免曲线混用
watch(ekfOn, () => { if (!running.value) resetRun() })

// 初始化：默认一组回路
if (!grps.length) pushGrp()
resetRun()
onBeforeUnmount(() => {
  trainStop.value = true
  stopRun()
})

// 导出给外部
defineExpose({ resetRun, isRunning: () => running.value })
</script>

<style scoped>
.pid-wrap { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; }
.pid-empty {
  flex: 1 1 auto; display: flex; flex-direction: column; align-items: center; justify-content: center;
  gap: 10px; padding: 0 40px; text-align: center; color: var(--faint); font-size: 12px;
}
.pid-empty-ico { color: var(--muted); opacity: .6; }
.pid-main { flex: 1 1 auto; min-height: 0; display: flex; gap: 12px; }

/* ==================== 左：设定 ==================== */
.pid-set {
  flex: 0 0 348px; width: 348px; min-width: 0;
  display: flex; flex-direction: column; gap: 10px;
  overflow-y: auto; padding: 0 4px 8px 0;
}
.pid-top { flex: 0 0 auto; display: flex; align-items: center; gap: 7px; }
.pid-kbd { color: var(--accent-d); font-size: 12.5px; font-weight: 700; letter-spacing: .3px; }
.pid-ttl { font-size: 12.5px; font-weight: 600; color: var(--text); }
.pid-sub { font-size: 10px; color: var(--faint); }
.pid-state { margin-left: auto; display: inline-flex; align-items: center; gap: 5px; font-size: 10px; color: var(--muted); }
.pid-state .pid-dot { width: 7px; height: 7px; border-radius: 50%; }
.pid-state.idle .pid-dot { background: #777; }
.pid-state.ok .pid-dot { background: var(--green); box-shadow: 0 0 6px var(--green); }
.pid-state.ok { color: var(--green); }
.pid-state.busy .pid-dot { background: var(--accent); animation: pid-pulse 1s infinite; }
@keyframes pid-pulse { 50% { opacity: .35; } }

.set-sec { flex: 0 0 auto; }
.sec-head {
  display: flex; align-items: center; gap: 6px; padding-bottom: 6px;
  border-bottom: 1px solid var(--line); font-size: 12px; font-weight: 600; color: var(--text);
}
.sec-no {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 16px; height: 16px; padding: 0 5px; border-radius: 8px;
  background: var(--bar); color: var(--accent-d); font-size: 10px; font-weight: 600; line-height: 1;
}
.mini-btn {
  padding: 2px 8px; font-size: 10px; color: var(--accent2); background: transparent;
  border: 1px solid var(--accent2); border-radius: 3px; cursor: pointer;
}
.mini-btn:hover:not(:disabled) { background: var(--accent2); color: #fff; }
.mini-btn:disabled { opacity: .4; cursor: not-allowed; }
.mini-btn.add { margin-left: auto; }
.mini-btn.del { align-self: flex-end; color: #d57070; border-color: #d57070; padding: 1px 6px; }
.mini-btn.del:hover:not(:disabled) { background: #d57070; color: #fff; }

/* 数据源 */
.data-line { display: flex; align-items: center; gap: 8px; padding-top: 8px; flex-wrap: wrap; }
.seg { display: inline-flex; }
.seg-btn {
  padding: 3px 12px; font-size: 11px; color: var(--muted);
  background: transparent; border: 1px solid var(--border); cursor: pointer;
}
.seg:first-child .seg-btn { border-radius: 4px 0 0 4px; }
.seg:last-child .seg-btn { border-radius: 0 4px 4px 0; }
.seg-btn + .seg-btn { margin-left: -1px; }
.seg-btn.on { color: #fff; background: var(--accent-d); border-color: transparent; font-weight: 500; }
.seg-btn:disabled { opacity: .5; cursor: not-allowed; }
.tau { display: inline-flex; align-items: center; gap: 3px; }

/* 回路卡片 */
.grp-list { display: flex; flex-direction: column; gap: 6px; padding-top: 8px; }
.grp-row {
  display: flex; flex-direction: column; gap: 4px; padding: 5px 6px;
  border: 1px solid var(--border); border-radius: 5px; background: var(--panel); cursor: pointer;
}
.grp-row.on { border-color: var(--accent2); box-shadow: 0 0 0 1px var(--accent2); }
.grp-l1 { display: flex; align-items: flex-end; gap: 4px; }
.grp-no {
  flex: 0 0 auto; display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; margin-bottom: 3px; border-radius: 50%;
  font-size: 10px; font-weight: 600; color: var(--accent-d);
  background: var(--bar); border: 1px solid var(--border);
}
.cell { flex: 1 1 0; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
.cell em, .sp em, .kv em, .kv-g em, .tau em {
  font-style: normal; font-size: 9.5px; color: var(--faint); white-space: nowrap;
}
.grp-arrow { flex: 0 0 auto; align-self: flex-end; margin-bottom: 4px; color: var(--accent); font-size: 13px; }
.grp-l2 { display: flex; align-items: baseline; gap: 8px; flex-wrap: wrap; }
.sp { display: inline-flex; align-items: baseline; gap: 3px; }
.sp .num { width: 76px; }
.kv { display: inline-flex; align-items: baseline; gap: 3px; }
.kv b { font-size: 10.5px; font-variant-numeric: tabular-nums; }
.kv b.acc { color: var(--accent-d); }
.kv b.dim { color: var(--accent2); }
.badge-s {
  margin-left: auto; padding: 0 5px; border-radius: 8px; font-size: 9.5px; line-height: 15px;
  background: var(--bar); color: var(--muted);
}
.badge-s.ok { color: var(--green); background: rgba(58,166,85,.12); }
.badge-s.busy { color: var(--accent-d); background: rgba(0,94,148,.12); }
.badge-s.na { color: #d57070; background: rgba(213,112,112,.12); }
.grp-l3 { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding-top: 1px; }
.kv-g { display: inline-flex; align-items: center; gap: 3px; }
.kv-g .num { width: 64px; }
.kv-g.h .num { width: 48px; }
.kv-g .num.k { width: 56px; }
.auto-cfg { font-size: 9.5px; color: var(--faint); }

/* 滤波 */
.flt-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding-top: 8px; }
.hint { margin: 6px 0 0; font-size: 10px; line-height: 1.55; color: var(--muted); }

/* 运行控制 */
.run-line { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding-top: 8px; }
.run-btn {
  padding: 3px 12px; font-size: 11.5px; color: var(--muted); background: var(--panel);
  border: 1px solid var(--border); border-radius: 3px; cursor: pointer;
}
.run-btn:hover:not(:disabled) { border-color: var(--accent2); color: var(--accent-d); }
.run-btn:disabled { opacity: .45; cursor: not-allowed; }
.run-btn.primary { color: #fff; background: var(--accent-d); border-color: transparent; font-weight: 500; }
.run-btn.primary:hover:not(:disabled) { filter: brightness(1.08); color: #fff; }
.run-btn.go { color: var(--green); border-color: var(--green); }
.run-btn.go:hover:not(:disabled) { background: var(--green); color: #fff; }
.run-btn.stop { color: #d57070; border-color: #d57070; }
.run-meta { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding-top: 6px; font-size: 10px; color: var(--faint); }
.run-meta .ok-n { color: var(--green); font-weight: 500; }
.run-meta .mini-btn { margin-left: auto; }
.freq { padding: 2px 4px; font-size: 10.5px; }

/* 通用控件 */
select, .num {
  padding: 2px 4px; font-size: 11px; color: var(--text);
  background: var(--panel); border: 1px solid var(--border); border-radius: 3px; outline: none;
}
select { font-family: inherit; max-width: 100%; }
.num { font-family: var(--mono); text-align: right; }
.num.w48 { width: 48px; }
select:focus, .num:focus { border-color: var(--accent2); }
select:disabled, .num:disabled { opacity: .55; }
.chk { display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px; color: var(--muted); cursor: pointer; white-space: nowrap; }
.chk input { accent-color: var(--accent-d); width: 12px; height: 12px; }
em.u, i.u { font-style: normal; font-size: 9.5px; color: var(--faint); }
.mono { font-family: var(--mono); }

/* ==================== 右：图 ==================== */
.pid-charts {
  flex: 1 1 auto; min-width: 0; min-height: 0;
  display: flex; flex-direction: column; gap: 8px; overflow-y: auto; padding-right: 4px;
}
.ch-card {
  flex: 0 0 auto; display: flex; flex-direction: column;
  border: 1px solid var(--border); border-radius: 6px; background: var(--panel); padding: 2px 8px 4px;
}
.ch-head { display: flex; align-items: center; gap: 6px; padding: 4px 0 2px; }
.ch-tag { color: var(--accent-d); font-size: 11px; font-weight: 700; }
.ch-ttl { font-size: 12px; font-weight: 600; color: var(--text); }
.ch-sub { font-size: 10px; color: var(--faint); margin-left: 4px; }
.ch-right { margin-left: auto; display: inline-flex; align-items: center; gap: 8px; }
.vsel { font-size: 10.5px; max-width: 210px; }
.ch-empty {
  height: 130px; display: flex; align-items: center; justify-content: center;
  font-size: 10.5px; color: var(--faint);
}
.ch-badge {
  padding: 0 6px; border-radius: 8px; font-size: 9.5px; line-height: 15px;
  background: rgba(0,94,148,.12); color: var(--accent-d);
}

/* 训练区（占右区大范围） */
.train { flex: 1 1 auto; min-height: 300px; }
.tr-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 4px 0 6px; border-bottom: 1px dashed var(--line); }
.mini-btn.set.on { background: var(--accent2); color: #fff; }
.tr-set { padding: 6px 0 5px; border-bottom: 1px dashed var(--line); display: flex; flex-direction: column; gap: 5px; }
.tr-set-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.tr-set-row.obj { padding-top: 5px; border-top: 1px dotted var(--line); }
.obj-lb { font-size: 10.5px; color: var(--muted); }
.obj-it { font-size: 10px; color: var(--faint); }
.obj-it b { margin-left: 3px; color: var(--text); font-family: var(--mono); }
.tr-ident { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 5px 0 6px; border-bottom: 1px dashed var(--line); font-size: 10px; color: var(--faint); }
.tr-ident .id-lb { color: var(--muted); }

/* ② 滤波前后左右对比 */
.cmp-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media (max-width: 900px) { .cmp-grid { grid-template-columns: 1fr; } }
.cmp-cell { min-width: 0; }
.cmp-h { display: flex; align-items: center; gap: 5px; padding-bottom: 1px; font-size: 10.5px; color: var(--muted); }
.lg-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.ch-empty.sm { height: 112px; font-size: 10px; }

/* ④ 优化目标变化 · PID 参数轨迹 */
.ov-wrap { position: relative; height: 132px; margin-top: 4px; }
.ov-svg { position: absolute; inset: 0; width: 100%; height: 100%; }
.ov-svg .grid { stroke: var(--line); stroke-width: 1; vector-effect: non-scaling-stroke; }
.ov-svg .cv { fill: none; stroke: var(--accent-d); stroke-width: 1.8; vector-effect: non-scaling-stroke; }
.ov-dot {
  position: absolute; width: 7px; height: 7px; margin: -3.5px 0 0 -3.5px;
  border-radius: 50%; background: var(--accent-d);
}
.ov-dot.on { background: var(--green); box-shadow: 0 0 0 2px rgba(58,166,85,.22); }
.ov-tag {
  position: absolute; transform: translate(-50%, -100%); white-space: nowrap;
  font-size: 9px; line-height: 1.35; pointer-events: none;
}
.ov-tag.below { transform: translate(-50%, 0); }
.ov-tag .g { display: block; color: var(--faint); }
.ov-tag .p { display: block; font-family: var(--mono); color: var(--text); }
.ov-tag.on .p { color: var(--green); }
.tr-state { display: inline-flex; align-items: center; gap: 5px; font-size: 10px; color: var(--muted); }
.tr-state .dot { width: 7px; height: 7px; border-radius: 50%; background: #777; }
.tr-state.on { color: var(--accent-d); }
.tr-state.on .dot { background: var(--accent); animation: pid-pulse 1s infinite; }
.tr-vis { flex: 1 1 auto; min-height: 120px; display: flex; flex-direction: column; padding-top: 6px; }
.tr-svg { width: 100%; flex: 1 1 auto; min-height: 110px; }
.tr-svg .grid { stroke: var(--line); stroke-width: 1; }
.tr-svg .base { stroke: var(--muted); stroke-width: 1; stroke-dasharray: 4 4; opacity: .7; }
.tr-svg .cv { fill: none; stroke: var(--accent-d); stroke-width: 1.8; }
.tr-empty { flex: 1 1 auto; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 0 24px; text-align: center; }
.tr-empty .t1 { font-size: 11px; color: var(--muted); }
.tr-empty .t2 { font-size: 10px; color: var(--faint); }
.tr-ax { display: flex; justify-content: space-between; font-size: 9.5px; color: var(--faint); padding-top: 2px; }
.tr-best { flex: 0 0 auto; border-top: 1px dashed var(--line); margin-top: 4px; padding-top: 6px; }
.tr-sum { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; font-size: 10.5px; color: var(--muted); }
.tr-sum b { color: var(--text); font-variant-numeric: tabular-nums; }
.tr-sum .gain.ok { color: var(--green); }
.tr-sum .gain.ok b { color: var(--green); }
.tr-rows { display: flex; flex-direction: column; gap: 2px; padding-top: 5px; }
.tr-row { display: flex; align-items: baseline; gap: 6px; font-size: 10.5px; color: var(--text); }
.tr-row .rn {
  flex: 0 0 auto; width: 15px; height: 15px; border-radius: 50%; text-align: center; line-height: 15px;
  font-size: 9px; color: var(--accent-d); background: var(--bar); border: 1px solid var(--border);
}
.tr-row .rl { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
.tr-row .rp { margin-left: auto; color: var(--accent-d); font-size: 10px; }
</style>
