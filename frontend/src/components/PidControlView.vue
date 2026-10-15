<!-- ============ AI 群控（AGC）============
     两级结构：
       ① 模型库 —— 以卡片形式列出所有已设计的算法模型，支持新建（规则 / 强化学习 / 粒子群 / MPC）
       ② 编排   —— 进入某个模型后：左栏为「模块列表」（规则模型：拖入 / 点击即建模块；
                   强化学习 · 粒子群 · MPC 仍按可调 / 传感设备勾选配对回路），
                   右栏为该算法自己的编排体，右上角「运行」即按编排的算法执行。
     运行时不做整页的实时观测图表，改为点击左侧 / 画布 / 编排条上的任意模块查看它的实时值。
     规则：可调（橙）· 传感（青）· 条件（紫，分支内可用「并且 / 或者」写多条比较）· 循环（黄），
     只有可调模块可以设定数值。 -->
<template>
  <div class="agc">
    <!-- ══════════ ① 模型库 ══════════ -->
    <section v-if="page === 'lib'" class="agc-lib">
      <div class="lib-bar">
        <span class="lib-ttl">{{ t('模型库') }}</span>
        <span class="cnt">{{ designs.length }}</span>
        <!-- 群控策略属于具体的场景资源包：明确标出当前场景，避免把别场景的策略当成自己的 -->
        <span class="lib-scene">{{ t('场景') }} · {{ sceneLabel }}</span>
        <!-- 手动从服务端拉一次清单：群控编排单一真源在服务端，任何一端新建的策略都在这里同步过来 -->
        <button class="lib-refresh" :disabled="refreshing" :title="t('从服务端重新拉取本场景的模型库')" @click="refreshDesigns">
          <span class="rf-ic" :class="{ spin: refreshing }">⟳</span><span class="rf-tx">{{ refreshing ? t('刷新中…') : t('刷新') }}</span>
        </button>
      </div>
      <p class="lib-tip">{{ t('每个模型是一套群控算法：编排完成后点右上角「运行」；运行中点击模块可看实时值。') }}</p>

      <div class="lib-grid">
        <article v-for="m in designs" :key="m.id" class="mcard" :class="['alg-' + m.alg, { live: isRunning(m.id) }]" @click="enter(m)">
          <div class="mc-top">
            <span class="mc-ic">{{ algIco(m.alg) }}</span>
            <span class="mc-nm">{{ m.name }}</span>
            <span class="mc-tg" :class="m.alg">{{ algLabel(m.alg) }}</span>
          </div>
          <div class="mc-bd">
            <span v-for="s in statOf(m)" :key="s.k" class="mc-st"><em>{{ s.k }}</em><b class="mono">{{ s.v }}</b></span>
          </div>
          <div class="mc-ft">
            <span v-if="isRunning(m.id)" class="mc-live"><i class="dot"></i>{{ t('运行中') }}</span>
            <span class="mono mc-ts">{{ shortTs(m.ts) }}</span>
            <span class="mc-ops">
              <button class="lk" :class="isRunning(m.id) ? 'danger' : 'run'" :disabled="!isRunning(m.id) && !canRunModel(m)" :title="isRunning(m.id) ? t('停止') : (canRunModel(m) ? t('启动') : runTipOf(m))" @click.stop="toggleModel(m)">{{ isRunning(m.id) ? t('停止') : t('启动') }}</button>
              <button class="lk" @click.stop="renameModel(m)">{{ t('重命名') }}</button>
              <button class="lk" @click.stop="dupModel(m)">{{ t('复制') }}</button>
              <button class="lk danger" @click.stop="delModel(m)">{{ t('删除') }}</button>
            </span>
          </div>
        </article>

        <button class="mcard new" @click="openNew">
          <span class="plus">+</span>
          <span class="nt">{{ t('新建模型') }}</span>
          <span class="nd">{{ t('规则 / 强化学习 / 粒子群 / MPC') }}</span>
        </button>
      </div>

      <div v-if="!designs.length" class="lib-empty">
        <p class="t1">{{ t('「{scene}」下还没有算法模型', { scene: sceneLabel }) }}</p>
        <p class="t2">{{ t('点击「+ 新建模型」，选择规则 / 强化学习 / 粒子群 / MPC，即可进入编排。') }}</p>
        <!-- 群控策略按工程（场景）分档保存在官网：换浏览器看不到时，多半是打开了别的工程 -->
        <p class="t3">{{ t('新建的策略保存在官网当前工程下，所有人可见；若在别的浏览器看不到，请确认打开的是同一个工程。') }}</p>
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
        <button class="btn" :class="running ? 'danger' : 'primary'" :disabled="!canRun" :title="runTip" @click="toggleRun">
          {{ running ? t('停止') : t('运行') }}
        </button>
      </div>

      <div class="ed-bd">
        <!-- ─────── 左栏 ─────── -->
        <aside class="agc-aside">
          <!-- 规则模型：模块列表（拖入画布 / 点击加到画布） -->
          <template v-if="isRule">
            <section v-for="g in modGroups" :key="g.key" class="pnl">
              <div class="pnl-hd" :class="{ col: modFold[g.key] }" @click="modFold[g.key] = !modFold[g.key]">
                <i class="caret" :class="{ on: !modFold[g.key] }">▸</i>
                <span class="ph-t">{{ g.title }}</span>
                <em class="cnt mono">{{ g.items.length }}</em>
              </div>
              <div v-show="!modFold[g.key]" class="pnl-bd">
                <p v-if="!g.items.length" class="emp">{{ t('当前场景没有可用设备') }}</p>
                <div v-for="it in g.items" :key="it.key" class="mi" :class="'k-' + it.k"
                     draggable="true" :title="t('拖入画布，或点击直接添加到画布')"
                     @dragstart="onModDrag($event, it)" @click="addModFromLib(it)">
                  <i class="mi-ic">{{ it.ico }}</i>
                  <span class="mi-nm">{{ it.name }}<em>{{ it.desc }}</em></span>
                  <b v-if="it.val" class="mono mi-v">{{ it.val }}<i>{{ it.unit }}</i></b>
                </div>
              </div>
            </section>
          </template>

          <!-- 强化学习 / 粒子群：仍按设备勾选（RL 按勾选顺序与可调一一配对形成回路） -->
          <template v-else>
            <div class="agc-hd">
              <span class="hd-sub mono">{{ selAdj.length }}{{ t('可调') }} · {{ selSen.length }}{{ t('传感') }}</span>
              <span class="hd-sp"></span>
              <span class="hd-sub">{{ t('勾选参与回路的设备') }}</span>
            </div>

          <!-- ① 可调设备 -->
          <section class="pnl">
            <div class="pnl-hd" :class="{ col: fold.adj }" @click="fold.adj = !fold.adj">
              <i class="caret" :class="{ on: !fold.adj }">▸</i>
              <span class="ph-t">{{ t('① 可调设备') }}</span>
              <em class="cnt mono">{{ selAdj.length }}/{{ adjList.length }}</em>
              <span class="hd-ops">
                <button class="lk" @click.stop="pickAllAdj">{{ t('全选') }}</button>
                <button class="lk" @click.stop="clearAdj">{{ t('清空') }}</button>
              </span>
            </div>
            <div v-show="!fold.adj" class="pnl-bd">
              <p v-if="!adjList.length" class="emp">{{ t('当前场景没有可调设备（可调设备才能作为被控对象）。') }}</p>
              <div v-for="d in adjList" :key="d.id" class="dev" :class="{ on: has(selAdj, d.id) }">
                <div class="dev-hd" @click="toggle(selAdj, d.id)">
                  <span class="cbx"><i v-if="has(selAdj, d.id)">✓</i></span>
                  <span class="nm">{{ d.label }}<em>{{ d.unitName }}</em></span>
                  <b class="mono val">{{ fmt(curSp(d.id)) }}<i>{{ spUnit(d.id) }}</i></b>
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
            <div class="pnl-hd" :class="{ col: fold.sen }" @click="fold.sen = !fold.sen">
              <i class="caret" :class="{ on: !fold.sen }">▸</i>
              <span class="ph-t">{{ t('② 传感设备') }}</span>
              <em class="cnt mono">{{ selSen.length }}/{{ senList.length }}</em>
              <span class="hd-ops">
                <button class="lk" @click.stop="pickAllSen">{{ t('全选') }}</button>
                <button class="lk" @click.stop="clearSen">{{ t('清空') }}</button>
              </span>
            </div>
            <div v-show="!fold.sen" class="pnl-bd">
              <p v-if="cur && cur.alg === 'rl'" class="emp drag-tip">{{ t('强化学习：按勾选顺序与「① 可调设备」一一配对形成控制回路（第 1 台传感配第 1 台可调）。') }}</p>
              <p v-if="cur && cur.alg === 'mpc'" class="emp drag-tip">{{ t('MPC：按勾选顺序与「① 可调设备」一一配对形成控制回路（第 1 台传感配第 1 台可调），每拍按模型预测滚动求解最优调节量。') }}</p>
              <p v-if="!senList.length" class="emp">{{ t('当前场景没有传感设备。') }}</p>
              <div v-for="s in senList" :key="s.id" class="dev" :class="{ on: has(selSen, s.id) }">
                <div class="dev-hd" @click="toggle(selSen, s.id)">
                  <span class="cbx"><i v-if="has(selSen, s.id)">✓</i></span>
                  <span class="nm">{{ s.label }}<em>{{ s.unitName }}</em></span>
                  <b class="mono val">{{ fmt(liveOf(s.id)) }}<i>{{ s.unit || '' }}</i></b>
                </div>
                <div v-if="has(selSen, s.id)" class="dev-bd">
                  <template v-if="isLoopSensor(s.id)">
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
                  <div v-else class="row rd">
                    <em>{{ t('实时读数') }}</em>
                    <b class="mono">{{ fmt(liveOf(s.id)) }}</b><i class="u">{{ s.unit || '' }}</i>
                    <span class="hintx">{{ t('未参与回路：仅显示实时读数') }}</span>
                  </div>
                </div>
              </div>
            </div>
          </section>
          </template>
        </aside>

        <!-- ─────── 右栏：该算法的编排体 ─────── -->
        <main class="agc-main">
          <!-- 规则：可编排画布（点选画布卡片，实时值直接显示在卡片下方） -->
          <section v-if="isRule" class="card rg">
            <div class="card-hd">
              <span class="ct">{{ t('规则编排') }}</span>
              <span class="cs">{{ t('开始 → 可调 / 传感 → 条件判断（可含「并且 / 或者」多条件）→ 下游模块 → 结束') }}</span>
            </div>
            <RuleFlowEditor ref="rfRef" :key="cur.id" class="rf-fill" :graph="cur.graph" :running="running" :period="cur.period" :model-id="cur.id" />
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
                  <button class="btn" :class="{ primary: !sampling, danger: sampling }" @click="toggleSample">
                    {{ sampling ? t('停止采集') : t('开始采集') }}
                  </button>
                  <span class="tstate" :class="{ on: trainBusy }"><i class="dot"></i>{{ trainStateTxt }}</span>
                </span>
              </div>
              <div class="bar">
                <button class="btn primary" :disabled="trainBusy || !canTrain" @click="startTrain">{{ t('开始训练') }}</button>
                <button class="btn danger" :disabled="!trainBusy" @click="stopTrain">{{ t('停止') }}</button>
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
                  <p class="t2">{{ t('勾选可调设备与传感设备形成回路后，点击「运行」，这里显示奖励随迭代的变化。') }}</p>
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

          <!-- MPC：模型预测控制（按过程模型滚动求解最优调节量） -->
          <template v-else-if="cur.alg === 'mpc'">
            <section class="card">
              <div class="card-hd">
                <span class="ct">{{ t('MPC 编排') }}</span>
                <span class="cs">{{ t('可调设备 → 过程模型 → 预测时域内滚动求解最优调节量') }}</span>
              </div>
              <MpcTuner :cfg="cur.mpc" :loops="loops" :targets="spOf" :running="running" @update:running="onMpcRun" />
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
          <label class="mk-f">
            <em>{{ t('算法类型') }}</em>
            <select class="sel grow" v-model="newAlg">
              <option v-for="a in ALG_TYPES" :key="a.id" :value="a.id">{{ a.ico }} {{ a.label }}</option>
            </select>
          </label>
          <p class="mk-tip">{{ algDesc(newAlg) }}</p>
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
import { api } from '../api/client'
// 附加可调设备（变频器 / 半导体制冷电源…）不在工艺可调设备表内，量程兜底取通用附加设备库
import { ADJUSTABLE_MAP } from '../data/attachLibrary'
import RuleFlowEditor from './RuleFlowEditor.vue'
import PsoTuner from './PsoTuner.vue'
import MpcTuner from './MpcTuner.vue'
import { t } from '../i18n'
// 规则编排的「开始 / 结束」端点与通路判定：能否运行取决于是否形成「开始 → 结束」通路
import { hasFlowPath, ensureFlowEnds, upgradeBranches } from '../utils/ruleFlow'

/** 载入模型时把旧版编排升级到当前形态（AND / OR 收进条件内部），幂等 */
function upgradeGraph(g) {
  upgradeBranches(g)
  return g
}

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
  const val = Math.min(spMax(id), Math.max(spMin(id), n))
  // 编排编辑态（未运行）只改编排里的设定值、不下发到现场设备 —— 按约定「编排完成后点运行才生效」；
  // 运行中改值则即时下发（force：同值也重发，便于现场设备被改动 / 重启后重新对齐）。
  store.setExtSetpoint(id, val, running.value ? { force: true } : { localOnly: true })
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

// ==================== 设备选择 ====================
const cur = ref(null)                  // 当前编排中的模型
const selAdj = ref([])                 // 已选可调设备 id
const selSen = ref([])                 // 已选传感设备 id
const spOf = reactive({})              // 传感设备 id -> 目标值（PID 设定）
const fold = reactive({ adj: false, sen: false, alg: false, hp: true })

function has(arr, id) { return arr.includes(id) }
function toggle(arr, id) {
  const i = arr.indexOf(id)
  if (i >= 0) arr.splice(i, 1)
  else arr.push(id)
}
function pickAllAdj() { selAdj.value = adjList.value.map((d) => d.id) }
function clearAdj() { selAdj.value = [] }
function pickAllSen() { selSen.value = senList.value.map((d) => d.id) }
function clearSen() { selSen.value = [] }

// ─────────── 左栏模块列表 → 规则画布 ───────────
// 规则编排由左栏「模块」列表驱动：拖到画布即在落点建模块，点击则加到视图中心。
// 画布上增删模块不再反向同步任何勾选（勾选只用于「强化学习 / 粒子群」的回路配对）。
const rfRef = ref(null)
const modFold = reactive({ flow: false, logic: false, adj: false, sen: false })
const modGroups = computed(() => [
  {
    key: 'flow',
    title: t('流程'),
    items: [
      { key: 'flow-start', k: 'start', ico: '▶', name: t('开始'), desc: t('流程入口') },
      { key: 'flow-end', k: 'end', ico: '■', name: t('结束'), desc: t('流程出口') },
    ],
  },
  {
    key: 'logic',
    title: t('逻辑'),
    items: [
      // AND / OR 不再是独立模块：它们是「条件判断」内部多行条件之间的连接词
      { key: 'lg-if', k: 'if', ico: '⑃', name: t('条件判断'), desc: 'if / elif / else（多条件用并且 / 或者）' },
      { key: 'lg-loop', k: 'loop', ico: '↻', name: t('循环'), desc: t('重复执行下游') },
    ],
  },
  {
    key: 'adj',
    title: t('可调模块'),
    items: adjList.value.map((d) => ({
      key: 'adj-' + d.id, k: 'adj', devId: d.id, ico: '⚙',
      name: d.label || d.id, desc: d.unitName || '',
      val: fmt(curSp(d.id)), unit: spUnit(d.id),
    })),
  },
  {
    key: 'sen',
    title: t('传感模块'),
    items: senList.value.map((d) => ({
      key: 'sen-' + d.id, k: 'sen', devId: d.id, ico: '◉',
      name: d.label || d.id, desc: d.unitName || '',
      val: fmt(liveOf(d.id)), unit: d.unit || '',
    })),
  },
])
/** 拖起：把模块身份写进 dataTransfer（画布 drop 时按落点建模块） */
function onModDrag(e, it) {
  if (!e || !e.dataTransfer) return
  const p = { k: it.k }
  if (it.op) p.op = it.op
  if (it.devId) p.devId = it.devId
  e.dataTransfer.effectAllowed = 'copy'
  e.dataTransfer.setData('text/plain', JSON.stringify(p))
}
/** 点击：直接加到画布视图中心（与拖拽二选一，给不便拖拽的场景兜底） */
function addModFromLib(it) {
  if (!rfRef.value) return
  rfRef.value.addModule({ k: it.k, op: it.op, devId: it.devId })
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
// 一个回路 = 一台可调设备 + 一台传感设备，按左栏勾选顺序一一配对（不再单独维护绑定关系）
const loops = computed(() => {
  const out = []
  // 规则控制由画布连线表达关系，不形成 PID 回路
  if (cur.value && cur.value.alg === 'rule') return out
  const n = Math.min(selAdj.value.length, selSen.value.length)
  for (let i = 0; i < n; i++) {
    const adjId = selAdj.value[i]
    const senId = selSen.value[i]
    if (!findDev(adjId) || !findDev(senId)) continue
    out.push({ key: adjId, adjId, senId, adjLabel: devName(adjId), senLabel: devName(senId) })
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
// 首次拿到设备清单时给出合理默认：选第一台可调设备 + 同工序传感设备
let inited = false
/** 默认选择：取第一台可调设备 + 同工序传感设备（force = 进入新模型时重新给默认值） */
function autoPick(force) {
  if (inited && !force) return
  if (!adjList.value.length || !senList.value.length) return
  inited = true
  const a = adjList.value[0]
  selAdj.value = [a.id]
  const same = senList.value.filter((s) => s.unitId && a.unitId && String(s.unitId) === String(a.unitId))
  const pool = same.length ? same : senList.value
  selSen.value = pool.slice(0, 3).map((s) => s.id)
  syncRuns()
}
watch([() => adjList.value.length, () => senList.value.length], () => {
  // 清理失效选择
  const aids = adjList.value.map((d) => d.id)
  const sids = senList.value.map((d) => d.id)
  selAdj.value = selAdj.value.filter((id) => aids.includes(id))
  selSen.value = selSen.value.filter((id) => sids.includes(id))
  autoPick()
  syncRuns()
}, { immediate: true })

onMounted(() => {
  loadVers()
  loadDesigns()
  pullDesigns()   // 群控编排唯一真源：服务端 designs/agc（本地不留任何副本）
  if (versions.value.length) activeVer.value = versions.value[0].id
  scheduleNext()
  autoTimer = setInterval(checkAuto, 15000)
  // 服务端运行器状态轮询：规则执行在服务端（不依赖本页是否打开），本端只同步运行态与画布高亮
  rtTimer = setInterval(pollRuntime, 2000)
  pollRuntime()
  window.addEventListener('pagehide', flushDesigns)
  document.addEventListener('visibilitychange', onVisHide)
  syncTimer = setInterval(syncPeers, 8000)
})
// 多人在同一个官网实例上协作：定期把服务端（真源）的清单拉回来，
// 别人在这期间新建的策略就能直接出现在模型库里（不必重开浏览器）。
// 只在**模型库页**做（此时手上没有正在编辑的编排体），且有本地改动待推时跳过，避免覆盖自己。
let syncTimer = null
function syncPeers() {
  if (page.value !== 'lib' || cur.value) return
  if (pushPending || saveTimer) return
  if (document.visibilityState === 'hidden') return
  pullDesigns()
}
onBeforeUnmount(() => {
  trainStop.value = true
  // 不清 runId：运行态是全局的，关掉本视图服务端仍在跑，下次进来仍应显示「运行中」
  stopSample()
  if (syncTimer) { clearInterval(syncTimer); syncTimer = null }
  if (rtTimer) { clearInterval(rtTimer); rtTimer = null }
  flushDesigns()   // 切走视图也补发一次，避免防抖里的群控编排改动丢失
  window.removeEventListener('pagehide', flushDesigns)
  document.removeEventListener('visibilitychange', onVisHide)
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
// **群控编排绑定到场景资源包**：服务端 designs/agc.json 以 sceneId 分档存取。
// 历史上这里还按场景存一份 localStorage 兜底（DESIGNS_KEY + '::<scene>'），那份副本会让本显示的
// 是本机旧清单而不是服务端的同一份 —— 现已全部移除，浏览器不再留存任何群控存档（单一真源）。
const ALG_TYPES = [
  { id: 'rule', ico: '⌥', label: t('规则'), desc: t('if-elif-else 阈值编排，直观可控') },
  { id: 'rl', ico: '◈', label: t('强化学习'), desc: t('PPO 在线辨识 + 策略寻优') },
  { id: 'pso', ico: '⁂', label: t('粒子群'), desc: t('在线寻优，让观测值逼近目标') },
  { id: 'mpc', ico: '⧗', label: 'MPC', desc: t('模型预测控制：按过程模型滚动求解最优调节量') },
]
function algMeta(id) { return ALG_TYPES.find((a) => a.id === id) || ALG_TYPES[0] }
function algIco(id) { return algMeta(id).ico }
function algLabel(id) { return algMeta(id).label }
function algDesc(id) { return algMeta(id).desc }

const page = ref('lib')            // lib = 模型库；edit = 编排
const designs = ref([])
const newOpen = ref(false)
const newName = ref('')
const newAlg = ref('rule')
// 正在运行的模型 id。运行态是全局状态：写进服务端群控存档（agc 桶的 running 字段），
// 换电脑 / 重开浏览器打开仍是运行态，并由 sim store 的后台运行器继续按周期执行下发。
const runId = ref('')
// 运行态同样只认服务端（agcRuntime / 存档的 running 字段）：本地不再留存任何运行态副本

const isRule = computed(() => !!cur.value && cur.value.alg === 'rule')
/** 运行状态由父级（编排页右上角「运行」/ 模型库卡片「启动」）统一下发，编排体自身不再各带开关 */
const running = computed(() => !!cur.value && runId.value === cur.value.id)
function isRunning(id) { return !!id && runId.value === id }

function blankPso() {
  return { vars: [], senId: '', target: 0, pNum: 12, iters: 20, w: 0.7, c1: 1.5, c2: 1.5, waitMs: 3000 }
}
/** MPC 默认参数：预测时域 10 步、控制周期 5s、增量权重 λ、单步限幅 0（不限）、在线辨识开 */
function blankMpc() {
  return { np: 10, ts: 5, lam: 0.02, duMax: 0, ident: true, md: {} }
}
function normalizeModel(m) {
  const mm = m || {}
  return {
    id: mm.id,
    name: mm.name || t('未命名模型'),
    alg: ALG_TYPES.some((a) => a.id === mm.alg) ? mm.alg : 'rule',
    ts: Number(mm.ts) || Date.now(),
    period: Number(mm.period) || 2,
    graph: upgradeGraph({
      nodes: Array.isArray(mm.graph && mm.graph.nodes) ? mm.graph.nodes : [],
      edges: Array.isArray(mm.graph && mm.graph.edges) ? mm.graph.edges : [],
    }),
    pso: { ...blankPso(), ...(mm.pso || {}) },
    mpc: { ...blankMpc(), ...(mm.mpc || {}) },
    selAdj: Array.isArray(mm.selAdj) ? mm.selAdj : [],
    selSen: Array.isArray(mm.selSen) ? mm.selSen : [],
    spOf: mm.spOf && typeof mm.spOf === 'object' ? { ...mm.spOf } : {},
  }
}
let saveTimer = null
// 编排存档场景键：AI 群控模型按场景分档（与流程编排同一口径，切场景不串档）
function designScene() { return store.sceneId || 'steel' }
// 当前场景资源包的显示名：模型库里标出「属于哪个场景」，群控策略与场景一一对应
const sceneLabel = computed(() => {
  const sid = store.sceneId || 'steel'
  const meta = (store.sceneIndex || []).find((x) => x.id === sid)
  if (meta && meta.label) return meta.label
  const pk = store.scenePack && store.scenePack.meta
  if (pk && pk.label) return pk.label
  const sc = (store.scenarios || []).find((s) => s.id === sid)   // 内置钢包：注册表还没拉到时兜底「钢铁」
  return (sc && sc.label) || sid
})
let pushTimer = null
let pushPending = null   // 待推送的群控存档：防抖窗口内关页面时靠它补发（keepalive）
// 在途删除：删除请求发出到服务端确认之间，8s 轮询可能拉回「还没删掉」的旧档，
// 若不过滤，刚删掉的卡片会立刻复活（表现为「点删除没反应」）。服务端确认后清除。
const pendingRemoved = new Set()
function dropDesigns(id) {
  designs.value = designs.value.filter((x) => x.id !== id)
  if (!id) return
  pendingRemoved.add(id)
}
function persist() {
  const scene = designScene()
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null   // 置空：syncPeers 据此判断「本地是否还有待写的改动」
  }, 200)
  // 单一真源：清单只写服务端 designs/agc（本地不留副本）。
  // 服务端整档覆盖 —— 提交的清单里没有的条目即为已删除，不需要额外声明。
  // running 每次都取当前值（而非快照）—— 否则一次编辑保存会把刚切换的运行态覆盖回旧值。
  try {
    pushPending = { scene, data: { scene, designs: designs.value.slice(0, 50), updatedAt: Date.now(), running: runId.value ? [runId.value] : [] } }
    clearTimeout(pushTimer)
    pushTimer = setTimeout(() => {
      const p = pushPending
      pushPending = null
      if (!p) return
      api.designSave('agc', p.scene, p.data).then(() => {
        pendingRemoved.clear()   // 整档已被服务端接受：在途删除随之生效
      }).catch(() => { /* 服务端不可用时保持在途过滤，下次重试 */ })
    }, 600)
  } catch (e) { /* 忽略 */ }
}
// 页面关闭 / 切后台时立刻补发：普通 fetch 会在卸载阶段被取消，keepalive 才能送达，
// 否则「配完群控设备就关页面」时服务端仍是旧档，下次打开另一端实例会被还原。
function flushDesigns() {
  const p = pushPending
  if (!p) return
  pushPending = null
  clearTimeout(pushTimer)
  api.designSaveNow('agc', p.scene, p.data).catch(() => { /* 卸载阶段失败：下次编辑仍会带上 */ })
}
function onVisHide() { if (document.visibilityState === 'hidden') flushDesigns() }
function loadDesigns() {
  // 单一真源：本地不再读取任何群控存档 —— 清单由 pullDesigns() 从服务端 designs/agc 取回。
  // 挂载瞬间先用空清单渲染，服务端返回后立即替换（本地旧档不再有「抢先显示」的机会）。
  designs.value = []
}
// 服务端为准：服务器实例是群控编排的权威侧，服务端有存档就无条件采用，
// 本地 localStorage 只作离线兜底（不再按 ts 比对，否则两端永远不同步）
async function pullDesigns() {
  const scene = designScene()
  // 拉取前的本端清单：可能含有「本端刚建、还没来得及推送」的策略
  const before = designs.value.slice()
  try {
    const r = await api.designBucket('agc')
    // 只取本场景那一档：服务端按 sceneId 分档，别的场景的策略与本场景无关
    const remote = (r && r.data) ? r.data[scene] : null
    const arr = remote && Array.isArray(remote.designs)
      ? remote.designs.filter((m) => m && m.id && !pendingRemoved.has(m.id))
      : null
    if (!arr) {
      // 服务端本场景暂无存档：清单保持现状（本端刚建的模型会经 persist 写上去成为首档）
      seedDcExample()
      return
    }
    designs.value = arr.map(normalizeModel)
    // 并集保护：本端有、服务端没有的条目必然是「本端刚建还没推送」，
    // 先并入清单再回推一次服务端，避免刚建的策略被拉回的版本盖掉。
    // 在途删除的条目不参与并集 —— 否则刚删掉的模型会被自己重新并回来。
    const seen = new Set(designs.value.map((m) => m.id))
    const extra = before.filter((m) => m && m.id && !seen.has(m.id) && !pendingRemoved.has(m.id))
    if (extra.length) {
      designs.value = [...designs.value, ...extra.map((m) => normalizeModel(m))]
      persist()
    }
    // 运行态同样以服务端为准：换电脑 / 重开浏览器打开，运行中的策略在这里接着跑
    const run = remote && (Array.isArray(remote.running)
      ? remote.running
      : (typeof remote.running === 'string' ? [remote.running] : []))
    const rid = run.filter((id) => designs.value.some((m) => m.id === id))[0] || ''
    // 同样跳过本地优先窗口：拉存档与拉运行器状态是两条链路，别让旧值把刚点的启停弹回去
    if (rid !== runId.value && Date.now() >= runLocalUntil) {
      if (runId.value) stopModel(runId.value, true)
      if (rid) resumeRun(rid)
    }
  } catch (e) { /* 服务端不可用时保持当前清单，下次轮询再拉 */ }
  // 注意：内置示例只在「服务端本场景还没有存档」时补种（见上方 arr 为空分支）。
  // 服务端已有存档时一律以服务端清单为准 —— 用户删掉的策略不会在刷新后被补回来。
}

// 手动刷新：先把本端待发的改动补推上去，再从服务端整份拉回（跨端新建/删除立即对齐）
const refreshing = ref(false)
async function refreshDesigns() {
  if (refreshing.value) return
  refreshing.value = true
  try {
    flushDesigns()                 // 本端还有没发出去的编辑：先落服务端，避免被拉回的版本盖掉
    await pullDesigns()
    store.showToast(t('已刷新模型库'), 'success')
  } catch (e) {
    store.showToast(t('刷新失败，稍后重试'), 'warn')
  } finally {
    refreshing.value = false
  }
}

// ── 切场景：群控编排是场景资源包的一部分，必须整档换掉 ──
// 群控策略引用的设备是本场景特有的可调 / 传感设备（如 dc-thermal 的 ext::n_dc_* ），
// 换场景后继续显示旧场景的模型，用户一编辑就会被存成新场景的策略（正是此前串档的根因）。
let sceneSeq = 0                  // 连续切场景时只认最后一次（避免旧请求后到覆盖新场景清单）
watch(() => store.sceneId, async (nid, oid) => {
  if (!nid || nid === oid) return
  const seq = ++sceneSeq
  flushDesigns()                  // pending 里带着旧场景 id：先把旧场景的改动按旧场景落库
  if (runId.value) { stopModel(runId.value, true); runId.value = '' }
  cur.value = null                // 退出旧场景模型的编排
  page.value = 'lib'
  loadDesigns()                   // 新场景的本地兜底
  await pullDesigns()             // 再以服务端（新场景那一档）覆盖
  if (seq !== sceneSeq) return    // 期间又切了场景：交给那一次的处理收尾
})

// ==================== 内置示例：机房温控「机柜超温 → 降泵压」 ====================
// 首次在机房热控场景打开本视图时自动给出一个可直接运行的示例编排。
// 判据只有一条：**服务端清单里有没有这一条**（本地不再记 flag）—— 用户删掉后它就随服务端存档消失，
// 换任何浏览器都不会因为各自 flag 不同而重复种回去。
// 内置示例的 id：只在服务端本场景「还没有存档」时补种一次（见 pullDesigns），
// 用户删掉后服务端清单里就没有它了，刷新不会被重新种回去。
const EXAMPLE_ID = 'dc_cool_rule_50c'
function seedDcExample() {
  if ((store.sceneId || '') !== 'dc-thermal') return
  // 在途删除：刚点删除、服务端还没确认，别把它补回来
  if (pendingRemoved.has(EXAMPLE_ID)) return
  const senId = 'ext::n_dc_it::att_dc_it_temp'      // 机柜温度传感器
  const adjId = 'ext::n_dc_cw::att_dc_cw_pump'      // 循环水泵变压器
  if (!findDev(senId) || !findDev(adjId)) return
  if (designs.value.some((m) => m.id === EXAMPLE_ID)) return
  const m = normalizeModel({
    id: EXAMPLE_ID,
    name: '示例 · 机柜超 50℃ → 循环水泵变压器 24V',
    alg: 'rule',
    ts: Date.now(),
    period: 2,
    graph: {
      nodes: [
        { id: 'nd_start', kind: 'start', x: 40, y: 150 },
        { id: 'sen_rack', kind: 'sen', devId: senId, label: '机柜温度传感器', unit: '℃', unitName: '算力设备', value: null, x: 210, y: 130 },
        { id: 'if_temp', kind: 'if', x: 460, y: 100, branches: [
          { id: 'b1', type: 'if', src: 'sen_rack', op: '>=', val: 50 },
          { id: 'b2', type: 'else', src: '', op: '>', val: 0 },
        ] },
        { id: 'adj_pump', kind: 'adj', devId: adjId, label: '循环水泵变压器', unit: 'V', unitName: '冷却水', value: 24, x: 800, y: 60 },
        { id: 'nd_end', kind: 'end', x: 980, y: 150 },
      ],
      edges: [
        { id: 'e_st', from: 'nd_start', port: 'out', to: 'sen_rack' },
        { id: 'e_s2if', from: 'sen_rack', port: 'out', to: 'if_temp' },
        { id: 'e_if2adj', from: 'if_temp', port: 'b1', to: 'adj_pump' },
        { id: 'e_en', from: 'adj_pump', port: 'out', to: 'nd_end' },
      ],
    },
    selAdj: [adjId],
    selSen: [senId],
  })
  designs.value = [m, ...designs.value]
  persist()   // 示例也要写进服务端存档：它是所有客户端共用的同一份清单
}

// —— 进入 / 退出编排：设备选择与目标值随模型存取 ——
function loadSel(m) {
  const kept = (m.selAdj && m.selAdj.length) || (m.selSen && m.selSen.length)
  selAdj.value = (m.selAdj || []).slice()
  selSen.value = (m.selSen || []).slice()
  for (const k of Object.keys(spOf)) delete spOf[k]
  Object.assign(spOf, m.spOf || {})
  // 规则模型的模块由画布自己维护（左栏模块列表拖入），不参与设备勾选
  if (m.alg !== 'rule' && !kept) autoPick(true)
  // 存量编排可能没有「开始 / 结束」端点：进入编排时补齐，并把断开的两端自动接上
  if (m.alg === 'rule') ensureFlowEnds(m.graph)
  syncRuns()
}
watch([selAdj, selSen, spOf], () => {
  if (!cur.value) return
  cur.value.selAdj = selAdj.value.slice()
  cur.value.selSen = selSen.value.slice()
  cur.value.spOf = { ...spOf }
}, { deep: true })
// 模型的编排内容（规则图 / 粒子群参数 / 周期 / 名称）变更即落盘
watch(() => cur.value, (m) => { if (m) persist() }, { deep: true })
// 运行中改周期：重启后台运行器，让新的执行周期立即生效
watch(() => (cur.value ? Number(cur.value.period) || 2 : 0), () => {
  const m = cur.value
  if (m && isRunning(m.id) && m.alg === 'rule') { store.stopAgcRule(m.id); store.startAgcRule(m) }
})

function enter(m) {
  if (!m) return
  cur.value = m
  page.value = 'edit'
  loadSel(m)
  // 进入的正是运行中的强化学习模型：补上采样 / 训练（这类定时器只在编排页存活）
  if (isRunning(m.id) && m.alg === 'rl') {
    syncRuns()
    startSample()
    if (canTrain.value) startTrain()
  }
}
function back() {
  // 返回模型库不停策略：运行态是全局的，后台运行器继续按周期执行下发
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
  if (runId.value === m.id) stopModel(m.id, true)
  dropDesigns(m.id)
  persist()
}

/** 模型卡片的摘要指标 */
function statOf(m) {
  if (!m) return []
  if (m.alg === 'rule') {
    return [
      { k: t('模块'), v: (m.graph.nodes || []).length },
      { k: t('连线'), v: (m.graph.edges || []).length },
      { k: t('通路'), v: hasFlowPath(m.graph) ? t('已连通') : t('未连通') },
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
  if (m.alg === 'mpc') {
    return [
      { k: t('回路'), v: Math.min((m.selAdj || []).length, (m.selSen || []).length) },
      { k: t('预测时域'), v: `${(m.mpc && m.mpc.np) || 10}` },
      { k: t('周期'), v: `${(m.mpc && m.mpc.ts) || 5}s` },
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
  // 规则：必须形成「开始 → … → 结束」通路才允许执行
  if (m.alg === 'rule') return hasFlowPath(m.graph)
  if (m.alg === 'pso') return (m.pso.vars || []).length > 0 && !!m.pso.senId
  return loops.value.length > 0
})
const runTip = computed(() => {
  const m = cur.value
  if (!m) return ''
  if (canRun.value) return t('按当前编排运行；再点一次停止')
  if (m.alg === 'rule') return t('请先用「开始 / 结束」模块把流程连通：开始 → 条件判断 / 可调设备 → 结束')
  if (m.alg === 'pso') return t('请先选择优化变量（可调设备）与优化目标（传感设备）')
  return t('请先在左栏勾选可调设备与传感设备（按勾选顺序一一配对形成控制回路）')
})
const runStateTxt = computed(() => {
  const m = cur.value
  if (!m) return ''
  if (m.alg === 'rule') {
    if (running.value) return t('规则运行中')
    return canRun.value ? t('就绪') : t('未连通')
  }
  if (m.alg === 'pso') return running.value ? t('寻优中') : t('待运行')
  if (m.alg === 'mpc') return running.value ? t('MPC 运行中') : t('待运行')
  if (trainBusy.value) return `${t('训练中')} ${iterN.value}/${maxIter.value}`
  if (sampling.value) return t('采集中')
  if (curve.value.length) return `${t('已完成')} ${iterN.value} ${t('轮')}`
  return t('待运行')
})
// ─────────── 服务端运行器（策略在服务端常驻执行，本端只同步状态） ───────────
// 规则执行由 backend/app/domain/scene/agc_runner.py 常驻线程承担：点「运行」后只要不手动停止
// 就一直跑，关浏览器 / 换电脑都不影响。本端每 2s 拉一次状态：同步运行态（另一端启停也能看到）
// 与最近一轮执行结果（画布高亮）。服务端运行器不可用时才退回本地执行（见 startModel）。
let rtTimer = null
const backendRunner = ref(false)
// 本端刚改过运行态的「本地优先窗口」：存档推送后服务端运行器要 1~2s 才读到新值，
// 这期间轮询拉回来的仍是旧态 —— 若直接回灌，界面会瞬间弹回「启动」，表现为「要点好几下才生效」。
let runLocalUntil = 0
function markRunLocal() { runLocalUntil = Date.now() + 5000 }
/** 以服务端运行态为准同步本地显示（另一端点了启停，本端也跟着变） */
function syncRunFromServer(ids) {
  const id = (ids && ids.length) ? ids[0] : ''
  if (id === runId.value) return
  if (Date.now() < runLocalUntil) return                      // 本地优先窗口内：等服务端追上
  if (id && !designs.value.some((m) => m.id === id)) return   // 属于其它场景的模型，不管
  if (runId.value) store.stopAgcRule(runId.value)             // 本地兜底执行器让位给服务端
  runId.value = id
}
const zeroSeen = {}   // modelId -> 已处理过的归零时间戳（避免重复处理同一条）
async function pollRuntime() {
  try {
    const r = await api.agcRuntime()
    if (!r || !r.ok) { backendRunner.value = false; return }
    backendRunner.value = !!r.online
    if (r.last) store.agcLast = r.last
    // 服务端停止某策略时会把它的设定值归零并下发；本端把界面上的值同步成 0
    // （停止可能发生在另一端 / 浏览器没打开的时候，所以每次拉到新的归零记录都补一次）
    for (const mid of Object.keys(r.zero || {})) {
      const z = (r.zero || {})[mid]
      if (!z || !z.ts || (zeroSeen[mid] || 0) >= z.ts) continue
      zeroSeen[mid] = z.ts
      for (const id of (z.devs || [])) store.setExtSetpoint(id, 0, { localOnly: true })
    }
    // 只认本场景在跑的策略：服务端运行器同时跑着各场景的模型，别把别人的运行态显示到本场景
    const scene = designScene()
    const ids = (r.running || [])
      .filter((x) => x && x.id && (!x.scene || x.scene === scene))
      .map((x) => x.id)
    syncRunFromServer(ids)
  } catch (e) { backendRunner.value = false }   // 服务端不可用时沿用本地执行
}

/** 运行态是否可启动（模型库卡片按钮用，不依赖当前打开的模型） */
function canRunModel(m) {
  if (!m) return false
  if (m.alg === 'rule') return hasFlowPath(m.graph)
  if (m.alg === 'pso') return (m.pso.vars || []).length > 0 && !!m.pso.senId
  return (m.selAdj || []).length > 0 && (m.selSen || []).length > 0
}
function runTipOf(m) {
  if (!m) return ''
  if (m.alg === 'rule') return t('请先用「开始 / 结束」模块把流程连通：开始 → 条件判断 / 可调设备 → 结束')
  if (m.alg === 'pso') return t('请先选择优化变量（可调设备）与优化目标（传感设备）')
  return t('请先在左栏勾选可调设备与传感设备（按勾选顺序一一配对形成控制回路）')
}
/** 运行态立刻落到服务端：启停是低频动作，不等 600ms 防抖，避免「点了运行但另一端看不到」 */
function persistRunning() {
  markRunLocal()   // 本端刚改过：先以本端为准，别被尚未追上的服务端旧存档弹回去
  const scene = designScene()
  try {
    const data = { scene, designs: designs.value.slice(0, 50), updatedAt: Date.now(), running: runId.value ? [runId.value] : [] }
    // 已立即推送：清掉待发的防抖载荷，否则页面关闭时会再补发一份不带最新运行态的旧数据
    pushPending = null
    clearTimeout(pushTimer)
    api.designSaveNow('agc', scene, data).catch(() => { /* 失败不影响本地运行态，下次编辑仍会带上 */ })
  } catch (e) { /* 忽略 */ }
}
/** 启动：规则模型交给 store 的后台运行器（离开本页 / 关掉编排页也继续按周期执行下发） */
function startModel(m) {
  if (!m) return
  if (runId.value && runId.value !== m.id) stopModel(runId.value, true)   // 同时只允许一个策略在运行
  runId.value = m.id
  // 规则模型：服务端运行器在线时由它执行（关掉浏览器也照跑）；否则退回本地兜底执行
  if (m.alg === 'rule') { if (!backendRunner.value) store.startAgcRule(m) }
  else if (m.alg === 'rl') {
    syncRuns()
    startSample()
    if (canTrain.value) startTrain()
  }
  persistRunning()
}
/** 停止即归零：流程里所有可调模块的设定值置 0（不留残余设定值）。
 *  localOnly —— 服务端运行器在线时由它下发归零，本端只把界面上的设定值同步成 0；
 *               否则本端直接下发，保证设备真的停下来。 */
function zeroSetpoints(m, localOnly) {
  const ids = (((m && m.graph) ? m.graph.nodes : null) || [])
    .filter((n) => n && n.kind === 'adj' && n.devId)
    .map((n) => n.devId)
  for (const id of ids) {
    store.setExtSetpoint(id, 0, localOnly ? { localOnly: true } : { silent: true, force: true })
  }
  return ids
}
/** 停止：quiet = 内部切换（由其它动作连带），不重复写服务端 */
function stopModel(id, quiet) {
  const m = id ? designs.value.find((x) => x.id === id) : cur.value
  if (m && m.alg === 'rl') { stopTrain(); stopSample() }
  store.stopAgcRule((m && m.id) || id || '')
  // 停止后流程中所有涉及设定的值归零
  if (m && m.alg === 'rule') zeroSetpoints(m, backendRunner.value)
  runId.value = ''
  if (!quiet) persistRunning()
}
/** 恢复服务端记录的运行态（打开页面 / 换端时） */
function resumeRun(id) {
  const m = designs.value.find((x) => x.id === id)
  if (!m) return
  runId.value = id
  // 服务端运行器在线时不在这里再起一份本地执行器：它由服务端统一执行（关页面也照跑），
  // 若每个客户端都本地跑一轮，就会周期写本端的设备设定值 → 连带整档覆盖 flow 编排，
  // 把别人刚加的附加传感设备抹掉（表现为「一运行群控，编排附件就被还原」）。
  if (m.alg === 'rule' && !backendRunner.value) store.startAgcRule(m)
  // 强化学习 / 粒子群的采样与训练定时器只在编排页存活：进页时补，见 enter()
  else if (page.value === 'edit' && cur.value && cur.value.id === id && m.alg === 'rl') {
    syncRuns()
    startSample()
    if (canTrain.value) startTrain()
  }
}
function toggleModel(m) {
  if (!m) return
  if (isRunning(m.id)) stopModel(m.id)
  else if (canRunModel(m)) startModel(m)
}
function toggleRun() {
  const m = cur.value
  if (!m) return
  if (running.value) { stopModel(m.id); return }
  if (!canRun.value) return
  startModel(m)
}
function stopRun() { stopModel(runId.value) }
/** 粒子群寻优结束（或被中断）由子面板回报 */
function onPsoRun(v) { if (!v) stopModel(cur.value && cur.value.id) }
/** MPC 面板自报停止（例如配置不完整无法启动） */
function onMpcRun(v) { if (!v) stopModel(cur.value && cur.value.id) }

defineExpose({ startSample, stopSample, enter, back })
</script>

<style scoped>
/* ══════════════ AI 群控（AGC）· 视觉规范 ══════════════
   字号 4 档：13(--fs-h) · 12(--fs-t) · 11(--fs-b) · 10(--fs-s)
   字重 3 档：400 正文 · 500(--fw-m) 数值 · 600(--fw-t) 标题
   颜色 3 类：结构色 text·muted·faint
             语义色 accent 强调 · green 正常 · yellow 警告 · red 报警
             种类色 --k-adj 可调 · --k-sen 传感 · --k-if 条件 · --k-loop 循环
   层级表达顺序：留白 > 结构色 > 字重 > 彩色（彩色只给「标题 / 关键数值 / 状态」） */

.agc { flex: 1 1 auto; min-height: 0; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
/* 语义标签不再自带「默认加粗 / 斜体」的印刷样式，层级统一由字重令牌表达 */
.agc b, .agc strong { font-weight: var(--fw-m); }
.agc em, .agc i { font-style: normal; }
.hd-sp { flex: 1 1 auto; }
.grow { flex: 1 1 auto; }

/* ══════════ 通用控件（对齐全局按钮 / 表单规范，本页不另立一套） ══════════ */
.lk {
  padding: 0; border: 0; background: none; cursor: pointer; font-family: inherit;
  font-size: var(--fs-s); color: var(--muted);
}
.lk:hover { color: var(--accent-d); }
.lk.danger:hover { color: var(--red); }

.btn {
  padding: 0 var(--btn-pad-x); min-height: var(--btn-h); display: inline-flex; align-items: center; justify-content: center; gap: var(--sp-1);
  font-family: inherit; font-size: var(--fs-b); font-weight: var(--fw-m); line-height: 1;
  color: var(--text); background: var(--btn-bg); border: 1px solid transparent; border-radius: 2px;
  cursor: pointer; white-space: nowrap;
}
.btn:hover:not(:disabled) { background: var(--btn-bg-hover); }
.btn:disabled { opacity: .45; cursor: not-allowed; }
.btn.primary { color: var(--on-accent); background: var(--accent); font-weight: var(--fw-t); }
.btn.primary:hover:not(:disabled) { background: var(--accent-h); }
.btn.danger { color: var(--red); }
.btn.danger:hover:not(:disabled) { background: color-mix(in srgb, var(--red) 14%, transparent); }
.btn.ghost { background: var(--btn-bg); border-color: transparent; }
.btn.ghost:hover:not(:disabled) { background: var(--btn-bg-hover); }

.num, select, .sel, .mk-in {
  padding: 3px 6px; font-size: var(--fs-b); color: var(--text); max-width: 100%;
  background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); outline: none;
}
.num { font-family: var(--mono); font-variant-numeric: tabular-nums; text-align: right; }
select, .sel, .mk-in { font-family: inherit; }
.num:focus, select:focus, .sel:focus, .mk-in:focus { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent-l); }
.num:disabled, select:disabled, .sel:disabled { opacity: .5; }
.sel.xs { padding: 2px 4px; }
.num.w56 { width: 62px; }
.num.tm { width: 88px; text-align: center; }
input[type='checkbox'] { width: auto; padding: 0; border: 0; }
i.u { font-size: var(--fs-s); color: var(--faint); }
@keyframes agc-pulse { 50% { opacity: .35; } }

/* 徽标（算法标签 / 状态标签）：形状统一，只有语义色不同 */
.mc-tg, .tag, .badge {
  flex: 0 0 auto; padding: 0 6px; border-radius: 8px; white-space: nowrap;
  font-size: var(--fs-s); line-height: 15px; color: var(--muted);
  background: var(--bar); border: 1px solid var(--border);
}
.mc-tg.rule {
  color: var(--k-adj); border-color: color-mix(in srgb, var(--k-adj) 34%, transparent);
  background: color-mix(in srgb, var(--k-adj) 10%, transparent);
}
.mc-tg.rl {
  color: var(--k-if); border-color: color-mix(in srgb, var(--k-if) 34%, transparent);
  background: color-mix(in srgb, var(--k-if) 10%, transparent);
}
.mc-tg.pso {
  color: var(--k-sen); border-color: color-mix(in srgb, var(--k-sen) 34%, transparent);
  background: color-mix(in srgb, var(--k-sen) 10%, transparent);
}
.mc-tg.mpc {
  color: var(--k-loop); border-color: color-mix(in srgb, var(--k-loop) 34%, transparent);
  background: color-mix(in srgb, var(--k-loop) 10%, transparent);
}
.tag.on, .badge.ok {
  color: var(--green); border-color: color-mix(in srgb, var(--green) 34%, transparent);
  background: color-mix(in srgb, var(--green) 10%, transparent);
}
.badge.busy { color: var(--accent-d); border-color: transparent; background: var(--accent-l); }
.badge.na {
  color: var(--red); border-color: color-mix(in srgb, var(--red) 34%, transparent);
  background: color-mix(in srgb, var(--red) 10%, transparent);
}

/* ══════════ ① 模型库 ══════════ */
.agc-lib { flex: 1 1 auto; min-height: 0; display: flex; flex-direction: column; gap: 8px; overflow-y: auto; padding: 0 4px 0 8px; }
.lib-bar { display: flex; align-items: baseline; gap: 8px; }
.lib-ttl { font-size: var(--fs-t); font-weight: var(--fw-t); color: var(--text); }
/* 场景归属标记：群控策略随场景资源包走，明确写在这里避免跨场景误用 */
.lib-scene { font-size: var(--fs-s); color: var(--faint); white-space: nowrap; }
/* 刷新：群控清单单一真源在服务端，手动拉一次让本端与其它端对齐 */
.lib-refresh {
  margin-left: auto; display: inline-flex; align-items: center; gap: 4px;
  padding: 2px 9px; font-size: var(--fs-s); font-family: inherit; cursor: pointer;
  color: var(--faint); background: transparent;
  border: 1px solid var(--line, rgba(127, 127, 127, .35)); border-radius: 999px;
  transition: color .15s, border-color .15s, background .15s;
}
.lib-refresh:hover:not(:disabled) {
  color: var(--blue, #0860a8); border-color: color-mix(in srgb, var(--blue, #0860a8) 45%, transparent);
  background: color-mix(in srgb, var(--blue, #0860a8) 8%, transparent);
}
.lib-refresh:disabled { opacity: .55; cursor: default; }
.rf-ic { display: inline-block; line-height: 1; font-size: 1.05em; }
.rf-ic.spin { animation: rf-spin .8s linear infinite; }
@keyframes rf-spin { to { transform: rotate(360deg); } }
.lib-tip { margin: 0; max-width: 780px; font-size: var(--fs-s); line-height: 1.6; color: var(--faint); }
.lib-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(232px, 1fr));
  gap: 10px; align-content: start;
}

/* 模型卡：VSCode 风扁平条目——统一 1px 边框、hover 换底 + 描边，无彩色竖条、无投影 */
.mcard {
  position: relative; display: flex; flex-direction: column; gap: 8px; padding: 10px 12px;
  text-align: left; font-family: inherit; cursor: pointer;
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel);
  transition: background .12s, border-color .12s;
}
.mcard:hover { background: var(--panel-2); border-color: color-mix(in srgb, var(--accent-d) 42%, var(--border)); }
.mcard:focus-visible { outline: none; border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent-l); }
/* 运行中的卡片：绿色呼吸边框 + 外扩光环 + 顶部流光扫描，模型库里一眼看出哪个策略在跑 */
.mcard.live {
  overflow: hidden;
  background: color-mix(in srgb, var(--green) 5%, var(--panel));
  animation: agc-card-breathe 2.4s ease-in-out infinite;
}
/* 顶部流光：沿卡片上沿来回扫，表示策略在按周期持续执行 */
.mcard.live::before {
  content: ''; position: absolute; top: 0; left: 0; height: 2px; width: 36%;
  background: linear-gradient(90deg, transparent, var(--green), transparent);
  animation: agc-scan 2s linear infinite; pointer-events: none;
}
/* 外扩光环：与呼吸点同频，远看也能定位到运行中的那张卡 */
.mcard.live::after {
  content: ''; position: absolute; inset: -1px; border-radius: inherit; pointer-events: none;
  animation: agc-ring 2.4s ease-out infinite;
}
@keyframes agc-card-breathe {
  0%, 100% { border-color: color-mix(in srgb, var(--green) 32%, var(--border)); }
  50% { border-color: color-mix(in srgb, var(--green) 82%, var(--border)); }
}
@keyframes agc-scan { from { transform: translateX(-110%); } to { transform: translateX(320%); } }
@keyframes agc-ring {
  0% { box-shadow: 0 0 0 0 color-mix(in srgb, var(--green) 42%, transparent); }
  70%, 100% { box-shadow: 0 0 0 7px transparent; }
}
.mc-top { display: flex; align-items: center; gap: 7px; }
/* 算法标识由图标色块承载（取代原先的左侧彩色竖条） */
.mc-ic {
  flex: 0 0 auto; width: 20px; height: 20px; border-radius: 2px; font-size: var(--fs-b); line-height: 1;
  display: inline-flex; align-items: center; justify-content: center;
  color: var(--faint); background: color-mix(in srgb, currentColor 12%, transparent);
}
.mcard.alg-rule .mc-ic { color: var(--k-adj); }
.mcard.alg-rl .mc-ic { color: var(--k-if); }
.mcard.alg-pso .mc-ic { color: var(--k-sen); }
.mcard.alg-mpc .mc-ic { color: var(--k-loop); }
.mc-nm {
  flex: 1 1 auto; min-width: 0; font-size: var(--fs-t); font-weight: var(--fw-t); color: var(--text);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.mc-bd { display: flex; flex-wrap: wrap; gap: 2px 14px; }
.mc-st { display: inline-flex; align-items: baseline; gap: 5px; }
.mc-st em { font-size: var(--fs-s); color: var(--faint); }
.mc-st b { font-size: var(--fs-b); font-weight: var(--fw-m); color: var(--muted); }
.mc-ft { display: flex; align-items: center; gap: 8px; }
.mc-ts { font-size: var(--fs-s); color: var(--faint); }
.mc-live {
  display: inline-flex; align-items: center; gap: 5px; font-size: var(--fs-s); color: var(--green);
  animation: agc-live-txt 2.4s ease-in-out infinite;
}
.mc-live .dot {
  width: 6px; height: 6px; border-radius: 50%; background: var(--green);
  box-shadow: 0 0 0 0 color-mix(in srgb, var(--green) 55%, transparent);
  animation: agc-pulse 1.2s ease-in-out infinite;
}
@keyframes agc-live-txt { 0%, 100% { opacity: .72; } 50% { opacity: 1; } }
.mc-ops { margin-left: auto; display: inline-flex; gap: 8px; }
.mc-ops .lk { color: var(--faint); }
/* 模型库卡片上的「启动」：绿色，与卡片运行中的绿色呼吸点同一语义 */
.mc-ops .lk.run { color: var(--green); font-weight: var(--fw-m); }
.mc-ops .lk:disabled { opacity: .45; cursor: not-allowed; }
.mc-ops .lk:disabled:hover { color: var(--faint); }
.mcard:hover .mc-ops .lk { color: var(--muted); }
.mc-ops .lk:hover { color: var(--accent-d); }
.mc-ops .lk.danger:hover { color: var(--red); }
.mcard.new { align-items: center; justify-content: center; gap: 5px; min-height: 116px; border-style: solid; background: var(--btn-bg); }
.mcard.new:hover { background: var(--btn-bg-hover); border-color: color-mix(in srgb, var(--accent-d) 55%, var(--border)); }
.mcard.new .plus { font-size: 16px; line-height: 1; color: var(--faint); transition: color .12s; }
.mcard.new .nt { font-size: var(--fs-t); font-weight: var(--fw-t); color: var(--muted); transition: color .12s; }
.mcard.new .nd { font-size: var(--fs-s); color: var(--faint); }
.mcard.new:hover .plus, .mcard.new:hover .nt { color: var(--accent-d); }
.lib-empty { padding: 26px 0; text-align: center; }
.lib-empty .t1 { margin: 0 0 4px; font-size: var(--fs-t); color: var(--muted); }
.lib-empty .t2 { margin: 0; font-size: var(--fs-s); color: var(--faint); }
.lib-empty .t3 { margin: 6px 0 0; font-size: var(--fs-s); color: var(--faint); line-height: 1.6; }

/* ══════════ ② 编排 · 头部 ══════════ */
.agc-edit { flex: 1 1 auto; min-height: 0; min-width: 0; display: flex; flex-direction: column; gap: 8px; }
.ed-top {
  display: flex; align-items: center; gap: 8px; flex: 0 0 auto; padding: 6px 10px;
  border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel);
}
.ed-nm { font-size: var(--fs-t); font-weight: var(--fw-m); color: var(--text); }
.ed-st { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-s); color: var(--faint); }
.ed-st .dot, .tstate .dot { flex: 0 0 auto; width: 6px; height: 6px; border-radius: 50%; background: var(--faint); }
.ed-st.on { color: var(--green); }
.ed-st.on .dot { background: var(--green); animation: agc-pulse 1s infinite; }
.ed-bd { flex: 1 1 auto; min-height: 0; display: flex; gap: 12px; }

/* ══════════ ② 编排 · 左栏 ══════════ */
.agc-aside {
  flex: 0 0 336px; width: 336px; min-width: 0; display: flex; flex-direction: column; gap: 10px;
  overflow-y: auto; padding: 0 4px 0 8px;
}
.agc-hd { display: flex; align-items: center; gap: 6px; padding: 0 0 2px; }
.hd-sub { margin-left: auto; font-size: var(--fs-s); color: var(--faint); }

.pnl { border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel); overflow: hidden; }
.pnl-hd {
  display: flex; align-items: center; gap: 6px; padding: 6px 10px; cursor: pointer; user-select: none;
  background: var(--panel-2); 
  font-size: var(--fs-t); font-weight: var(--fw-t); color: var(--text);
}
.pnl-hd.col { border-bottom-color: transparent; }   /* 折叠时不要留一条悬空的横线 */
.caret { font-size: var(--fs-s); color: var(--faint); transition: transform .12s; display: inline-block; }
.caret.on { transform: rotate(90deg); }
.cnt { font-size: var(--fs-s); font-weight: 400; color: var(--faint); }
.hd-ops { margin-left: auto; display: inline-flex; gap: 8px; }
.pnl-bd { padding: 8px 10px 10px; display: flex; flex-direction: column; gap: 6px; }
.emp { margin: 0; font-size: var(--fs-s); line-height: 1.6; color: var(--faint); }
.drag-tip { color: var(--muted); border-left: 2px solid var(--border); padding-left: 8px; }

/* 模块列表项：拖入画布即在落点建模块，点击则加到画布中心 */
.mi {
  display: flex; align-items: center; gap: 6px; padding: 4px 6px; cursor: grab;
  border: 1px solid transparent; border-radius: var(--radius);
}
.mi:hover { background: var(--panel-2); border-color: var(--border); }
.mi:active { cursor: grabbing; }
.mi-ic { flex: 0 0 auto; width: 16px; text-align: center; font-size: var(--fs-b); color: var(--faint); }
.mi-nm { flex: 1 1 auto; min-width: 0; font-size: var(--fs-b); color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mi-nm em { font-size: var(--fs-s); color: var(--faint); margin-left: 5px; }
.mi-v { flex: 0 0 auto; font-size: var(--fs-b); font-weight: var(--fw-m); color: var(--text); }
.mi-v i { font-size: var(--fs-s); color: var(--faint); margin-left: 2px; }
.mi.k-start .mi-ic { color: var(--green); }
.mi.k-end .mi-ic { color: var(--red); }
.mi.k-if .mi-ic { color: var(--k-if); }
.mi.k-gate .mi-ic { color: color-mix(in srgb, var(--k-if) 52%, var(--k-sen)); font-weight: var(--fw-t); }
.mi.k-loop .mi-ic { color: var(--k-loop); }
.mi.k-adj .mi-ic { color: var(--k-adj); }
.mi.k-sen .mi-ic { color: var(--k-sen); }

.dev { border: 1px solid transparent; border-radius: var(--radius); }
.dev.on { background: var(--panel-2); border-color: var(--border); }
.dev-hd { display: flex; align-items: center; gap: 6px; padding: 4px 6px; cursor: pointer; }
.cbx {
  flex: 0 0 auto; width: 13px; height: 13px; border: 1px solid var(--border); border-radius: 2px;
  background: var(--panel); display: inline-flex; align-items: center; justify-content: center;
  font-size: var(--fs-s); line-height: 1; color: var(--on-accent);
}
.dev.on .cbx { background: var(--accent); border-color: var(--accent); }
.dev-hd .nm { flex: 1 1 auto; min-width: 0; font-size: var(--fs-b); color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dev-hd .nm em { font-size: var(--fs-s); color: var(--faint); margin-left: 5px; }
.dev-hd .val { flex: 0 0 auto; font-size: var(--fs-b); font-weight: var(--fw-m); color: var(--text); }
.dev-hd .val i { font-size: var(--fs-s); color: var(--faint); margin-left: 2px; }
.dev-bd { padding: 2px 6px 6px 25px; display: flex; flex-direction: column; gap: 6px; }
.sp-row { display: flex; align-items: center; gap: 6px; }
.rng { flex: 1 1 auto; min-width: 0; accent-color: var(--accent-d); height: 14px; }
.rng:disabled { opacity: .5; }
.sp-row .num { width: 68px; }
.row { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.row > em { font-size: var(--fs-s); color: var(--muted); flex: 0 0 auto; }
.row select { flex: 1 1 auto; min-width: 0; }
.row .num { width: 76px; }
.row.st { gap: 12px; }
.meta { display: flex; align-items: center; gap: 10px; font-size: var(--fs-s); color: var(--faint); flex-wrap: wrap; }
.hintx { font-size: var(--fs-s); color: var(--faint); }
.kv { display: inline-flex; align-items: baseline; gap: 4px; }
.kv em { font-size: var(--fs-s); color: var(--faint); }
.kv b { font-size: var(--fs-b); font-weight: var(--fw-m); color: var(--text); }

/* ══════════ ② 编排 · 右栏 ══════════ */
.agc-main { flex: 1 1 auto; min-width: 0; min-height: 0; display: flex; flex-direction: column; gap: 10px; overflow-y: auto; padding-right: 4px; }
.card { flex: 0 0 auto; display: flex; flex-direction: column; overflow: hidden; border: 1px solid var(--border); border-radius: var(--radius); background: var(--panel); }
.card.rg { flex: 1 1 auto; min-height: 560px; }
.card.grow { flex: 1 1 auto; min-height: 190px; }
.rf-fill { flex: 1 1 auto; min-height: 0; }
.card-hd { display: flex; align-items: center; gap: 8px; padding: 6px 10px; background: var(--panel-2);  }
.ct { font-size: var(--fs-t); font-weight: var(--fw-t); color: var(--text); }
.cs { font-size: var(--fs-s); color: var(--faint); }
.ch-ops { margin-left: auto; display: inline-flex; align-items: center; gap: 8px; }
.ch-ops .rw { font-size: var(--fs-b); font-weight: var(--fw-m); color: var(--accent-d); }
.ch-ops .best { font-size: var(--fs-b); font-weight: var(--fw-t); color: var(--text); }
.ch-ops .dim { font-size: var(--fs-s); color: var(--faint); }
.cempty { height: 150px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 4px; padding: 0 24px; text-align: center; }
.cempty.sm { height: 150px; }
.cempty .t1 { font-size: var(--fs-t); color: var(--muted); }
.cempty .t2 { font-size: var(--fs-s); line-height: 1.6; color: var(--faint); max-width: 460px; }

.bar { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 8px 10px; }
.bar.mv { border-top: 1px solid var(--line-soft); gap: 8px; }
.sep { width: 1px; height: 14px; background: var(--border); }
.lb2 { font-size: var(--fs-s); color: var(--muted); }
.nx { font-size: var(--fs-s); color: var(--faint); font-variant-numeric: tabular-nums; }
.chk { display: inline-flex; align-items: center; gap: 5px; font-size: var(--fs-b); color: var(--muted); cursor: pointer; }
.chk input { accent-color: var(--accent-d); width: 13px; height: 13px; }
.tstate { display: inline-flex; align-items: center; gap: 6px; font-size: var(--fs-s); color: var(--faint); }
.tstate.on { color: var(--green); }
.tstate.on .dot { background: var(--green); animation: agc-pulse 1s infinite; }

/* 超参数区：字段名 muted、单位 faint，不再出现第三种灰与额外强调色 */
.hp { padding: 4px 10px 10px; border-bottom: 1px solid var(--line-soft); display: flex; flex-direction: column; gap: 8px; }
.hp-row { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }
.hp-row.obj { padding-top: 8px; border-top: 1px solid var(--line-soft); }
.hp-row .lb { font-size: var(--fs-s); color: var(--muted); }
.f { display: inline-flex; align-items: center; gap: 5px; }
.f > em { font-size: var(--fs-s); color: var(--muted); white-space: nowrap; }

/* 奖励曲线 */
.rw-wrap { flex: 1 1 auto; min-height: 150px; display: flex; flex-direction: column; padding: 8px 10px 6px; }
.rw-svg { width: 100%; flex: 1 1 auto; min-height: 110px; }
.rw-svg .grid { stroke: var(--border); stroke-width: 1; vector-effect: non-scaling-stroke; }
.rw-svg .base { stroke: var(--faint); stroke-width: 1; stroke-dasharray: 4 4; vector-effect: non-scaling-stroke; }
.rw-svg .cv { fill: none; stroke: var(--accent-d); stroke-width: 1.8; vector-effect: non-scaling-stroke; }
.rw-ax { display: flex; justify-content: space-between; font-size: var(--fs-s); color: var(--faint); padding-top: 2px; }

/* 模型版本表 */
.vtb { display: flex; flex-direction: column; }
.vtr { display: grid; grid-template-columns: 64px 1.4fr 72px 56px 88px 72px; gap: 8px; align-items: center; padding: 5px 10px; font-size: var(--fs-b); color: var(--text); cursor: pointer; }
.vtr.hd { background: var(--panel-2);  font-size: var(--fs-s); color: var(--faint); cursor: default; }
.vtr:not(.hd):hover { background: var(--panel-2); }
.vtr.on { background: var(--sel); }
.vtr .dim { color: var(--faint); }
.vtr.cur .mono { color: var(--green); }
.vempty { padding: 12px 10px; font-size: var(--fs-s); color: var(--faint); text-align: center; }
.vdim { border-top: 1px solid var(--line-soft); padding: 8px 10px 10px; }
.vdim-h { font-size: var(--fs-s); color: var(--muted); padding-bottom: 5px; }
.vrow { display: flex; align-items: baseline; gap: 6px; font-size: var(--fs-b); padding: 2px 0; }
.vrow .rn {
  flex: 0 0 auto; width: 16px; height: 16px; border-radius: 50%; text-align: center; line-height: 16px;
  font-size: var(--fs-s); color: var(--accent-d); background: var(--bar); border: 1px solid var(--border);
}
.vrow .rl { color: var(--muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.vrow .rp { margin-left: auto; font-size: var(--fs-s); color: var(--accent-d); }

/* ══════════ 新建模型 ══════════ */
.mk-mask { position: fixed; inset: 0; z-index: 60; display: flex; align-items: center; justify-content: center; background: rgba(0, 0, 0, .38); }
.mk-dlg {
  width: 460px; max-width: calc(100vw - 40px); max-height: 88vh; overflow: auto; display: flex; flex-direction: column;
  border: 1px solid var(--border); border-radius: 4px; background: var(--panel); box-shadow: 0 8px 30px rgba(0, 0, 0, .25);
}
.mk-hd { display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: var(--panel-2);  }
.mk-hd b { font-size: var(--fs-h); font-weight: var(--fw-t); color: var(--text); }
.mk-x { margin-left: auto; padding: 0 4px; border: 0; background: none; cursor: pointer; font-family: inherit; font-size: var(--fs-t); color: var(--faint); }
.mk-x:hover { color: var(--red); }
.mk-bd { padding: 12px; display: flex; flex-direction: column; gap: 10px; }
.mk-f { display: flex; align-items: center; gap: 8px; }
.mk-f em { flex: 0 0 auto; font-size: var(--fs-b); color: var(--muted); }
/* 算法类型：下拉选择（种类增多后不再用平铺卡片，避免弹窗过高） */
.sel.grow { flex: 1 1 auto; min-width: 0; }
.mk-tip { margin: 0; padding: 6px 8px; font-size: var(--fs-s); line-height: 1.6; color: var(--faint); background: var(--panel-2); border-radius: var(--radius); }
.mk-ft { background: var(--head-bg);
 display: flex; justify-content: flex-end; gap: 8px; padding: 10px 12px;  }
</style>
