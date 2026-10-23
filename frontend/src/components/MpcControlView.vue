<!-- ============ MPC 控温优化模型 ============
     两种用法：
       · 独立页面（默认）：自带完整标识条，占满一个功能视图窗口
       · 内嵌（embedded）：作为「工具 → AI → AI群控」模型库里的内置模型，嵌进群控页面渲染，
         此时不再重复画标题条（群控顶部已有模型名与「← 模型库」），只留状态点与启用开关
     页面回答三件事：
       ① 这个模型现在能不能启用（依赖 / 参数 / 功率公式 vs 实测 / 求解器自检 四项）
       ② 输入「目标温度 + 到达时限」，在约定时间内做不做得到
       ③ 做得到的话，能耗最小的分段档位是什么（风扇电压 / 制冷片电流 + 每段时长）
     计算全部在后端 app/domain/mpc（灰箱一阶 RC + 离散档位 DP），本页只负责输入与呈现。 -->
<template>
  <div class="mpc-view" :class="{ embedded: isEmbedded }">
    <!-- ===== 顶部：模型标识 + 可否启用 + 启用开关（内嵌时只留右侧状态与开关） ===== -->
    <header class="mpc-head">
      <div v-if="!isEmbedded" class="mpc-id">
        <span class="mpc-tag">MPC</span>
        <div class="mpc-id-txt">
          <div class="mpc-name">
            {{ t('MPC 控温优化模型') }}
            <span class="mpc-ver">v{{ status.model.version || '—' }}</span>
          </div>
          <div class="mpc-desc">
            {{ t('灰箱一阶 RC 前向模型 + 离散档位动态规划：给出目标温度与时限，求解能耗最小的风扇 / 制冷片设定') }}
          </div>
        </div>
      </div>
      <div class="mpc-state">
        <span class="mpc-dot" :class="stateCls"></span>
        <span class="mpc-state-txt">{{ stateText }}</span>
        <button
          class="mpc-sw"
          :class="{ on: status.enabled }"
          :disabled="!status.available || busy.enable"
          :title="status.available ? (status.enabled ? t('点击停用') : t('点击启用')) : t('自检未通过，无法启用')"
          @click="toggleEnable"
        >
          {{ status.enabled ? t('已启用 · 点击停用') : t('启用该模型') }}
        </button>
      </div>
    </header>

    <div class="mpc-body">
      <!-- ================= 左列：自检 + 输入 ================= -->
      <div class="mpc-col mpc-col-l">
        <!-- ① 可用性自检：这一块就是「是否能启用这个模型」的依据 -->
        <section class="mpc-card">
          <div class="mpc-card-hd">
            <span class="mpc-card-tt">{{ t('模型可用性') }}</span>
            <span class="mpc-pill" :class="status.available ? 'ok' : 'bad'">
              {{ status.available ? t('可以启用') : t('不可启用') }}
            </span>
          </div>
          <ul class="mpc-checks">
            <li v-for="c in status.checks" :key="c.key" :class="c.ok ? 'ok' : 'bad'">
              <span class="ck-mark">{{ c.ok ? '✓' : '✕' }}</span>
              <span class="ck-body">
                <span class="ck-label">{{ t(c.label) }}</span>
                <span class="ck-detail">{{ c.detail }}</span>
              </span>
            </li>
            <li v-if="!status.checks.length" class="mpc-muted">{{ loading.status ? t('正在自检…') : t('后端未响应') }}</li>
          </ul>
          <div class="mpc-kv">
            <div class="kv"><em>{{ t('时间常数 τ') }}</em><b>{{ fx(status.params.tau_s, 0) }} s</b></div>
            <div class="kv"><em>{{ t('平衡温度 b₀') }}</em><b>{{ fx(status.params.b0, 2) }} ℃</b></div>
            <div class="kv"><em>{{ t('风扇增益') }}</em><b>{{ fx(status.params.k_v, 3) }} K/V</b></div>
            <div class="kv"><em>{{ t('制冷片增益') }}</em><b>{{ fx(status.params.k_i_lin, 3) }} K/A</b></div>
            <div class="kv"><em>{{ t('最小保持') }}</em><b>{{ fx(status.params.min_hold_s, 0) }} s</b></div>
            <div class="kv"><em>{{ t('满功率档') }}</em><b>{{ fx(status.params.full_power.v_fan, 0) }} V + {{ fx(status.params.full_power.i_tec, 0) }} A</b></div>
          </div>
          <div class="mpc-levels">
            <div class="lv-row">
              <span class="lv-lb">{{ t('风扇档位') }}</span>
              <span class="lv-vals">
                <i v-for="v in status.levels.fan_v" :key="'f' + v">{{ v }}</i>
              </span>
            </div>
            <div class="lv-row">
              <span class="lv-lb">{{ t('制冷片档位') }}</span>
              <span class="lv-vals">
                <i v-for="i in status.levels.tec_i" :key="'t' + i" :class="{ off: status.levels.tec_blacklist.includes(i) }">{{ i }}</i>
              </span>
            </div>
            <p class="mpc-hint">{{ t('划掉的档位默认禁用（5 A 多耗 34.8 W 但不带来可测降温）') }}</p>
          </div>
        </section>

        <!-- ② 输入：目标温度 + 时限（本页的核心输入） -->
        <section class="mpc-card">
          <div class="mpc-card-hd">
            <span class="mpc-card-tt">{{ t('目标与时限') }}</span>
            <button class="mpc-mini follow" :class="{ on: allFollow }" @click="toggleAllFollow"
                    :title="t('当前温度 / 室温 / 水桶温度 是否跟随 MQTT 实时上报')">
              {{ allFollow ? t('实时跟随中') : t('改为跟随实时') }}
            </button>
          </div>
          <div class="mpc-form">
            <label class="fld">
              <span class="fld-top">
                {{ t('当前温度') }}
                <button type="button" class="fld-src" :class="chipCls('tNow')"
                        :title="chipTitle('tNow')" @click="toggleFollow('tNow')">
                  <i></i>{{ chipText('tNow') }}
                </button>
              </span>
              <input v-model.number="form.tNow" type="number" step="0.1" :min="lim.tNow[0]" :max="lim.tNow[1]"
                     @input="onManual('tNow')" />
              <em>℃</em>
            </label>
            <label class="fld">
              <span class="fld-top">
                {{ t('目标温度') }}
                <button type="button" class="fld-src auto" :class="{ off: autoTarget }"
                        :title="autoTarget ? t('按实时温度自动取「降 5 K」，手动改过后不再自动') : t('已手动指定')"
                        @click="resetAutoTarget">
                  <i></i>{{ autoTarget ? t('自动') : t('手动') }}
                </button>
              </span>
              <input v-model.number="form.tTarget" type="number" step="0.1" :min="lim.tTarget[0]" :max="lim.tTarget[1]"
                     @input="onManual('tTarget')" />
              <em>℃</em>
            </label>
            <label class="fld">
              <span>{{ t('到达时限') }}</span>
              <input v-model.number="form.horizonMin" type="number" step="1" :min="1" :max="60" />
              <em>min</em>
            </label>
            <label class="fld">
              <span class="fld-top">
                {{ t('室温') }}
                <button type="button" class="fld-src" :class="chipCls('tenv')"
                        :title="chipTitle('tenv')" @click="toggleFollow('tenv')">
                  <i></i>{{ chipText('tenv') }}
                </button>
              </span>
              <input v-model.number="form.tenv" type="number" step="0.5" @input="onManual('tenv')" />
              <em>℃</em>
            </label>
            <label class="fld">
              <span class="fld-top">
                {{ t('水桶温度') }}
                <button type="button" class="fld-src" :class="chipCls('twater')"
                        :title="chipTitle('twater')" @click="toggleFollow('twater')">
                  <i></i>{{ chipText('twater') }}
                </button>
              </span>
              <input v-model.number="form.twater" type="number" step="0.5" @input="onManual('twater')" />
              <em>℃</em>
            </label>
          </div>
          <p class="mpc-hint">
            {{ t('目标温度必须低于当前温度（本模型只做降温）；时限 1~60 min，最小动作保持 300 s。') }}
          </p>
          <p class="mpc-hint live-hint">
            <template v-if="fbErr">{{ fbErr }}</template>
            <template v-else>
              {{ t('实时来源：当前温度 = zhileng-temp，室温 = env-temp，水桶温度 = shuitong-temp（MQTT 上报，每 3 s 刷新）。点字段右上角标签可切回手动。') }}
            </template>
          </p>
          <div class="mpc-actions">
            <button class="mpc-btn primary" :disabled="busy.plan" @click="runPlan">
              {{ busy.plan ? t('求解中…') : t('求解能耗最优动作') }}
            </button>
            <button class="mpc-btn" @click="resetForm">{{ t('恢复 45→39 / 12min') }}</button>
            <span v-if="err" class="mpc-err">{{ err }}</span>
          </div>
        </section>
      </div>

      <!-- ================= 右列：结果 ================= -->
      <div class="mpc-col mpc-col-r">
        <section v-if="!res" class="mpc-card mpc-empty">
          <div class="mpc-empty-tt">{{ t('还没有求解结果') }}</div>
          <div class="mpc-empty-desc">
            {{ t('在左侧填入「目标温度」与「到达时限」，点「求解能耗最优动作」——系统会先判可达性，再给出最省电的分段档位。') }}
          </div>
          <!-- 刷新页面后 res 为空，但闭环可能还在跑：必须在这里也能停，不能逼用户先去求解 -->
          <div v-if="loopOn" class="mpc-empty-loop">
            <div>
              {{ t('闭环正在运行：目标 {t} ℃ · 第 {r} 轮 · 重解 {p} 次 · 剩余 {m} min', {
                  t: fx(loopData.t_target, 1), r: loopData.rounds,
                  p: loopData.replans, m: fx(loopData.remaining_min, 1) }) }}
            </div>
            <div class="mel-act">
              <span>{{ t('当前执行') }} {{ fx(loopData.action && loopData.action.v_fan, 0) }} V / {{ fx(loopData.action && loopData.action.i_tec, 2) }} A</span>
              <button class="mpc-btn sm danger" :disabled="busy.apply" @click="stopAll">
                {{ t('停止并归零') }}
              </button>
              <button class="mpc-btn sm" @click="runPlan">{{ t('求解（恢复完整界面）') }}</button>
            </div>
          </div>
        </section>

        <template v-else>
          <!-- 结论条 -->
          <section class="mpc-card mpc-verdict" :class="res.feasible ? 'ok' : 'bad'">
            <div class="vd-left">
              <span class="vd-badge">{{ res.feasible ? t('可达') : t('不可达') }}</span>
              <div class="vd-main">
                <div class="vd-line">
                  {{ fmtT(res.request.t_now) }} ℃ → {{ fmtT(res.request.t_target) }} ℃ /
                  {{ fx(res.request.horizon_min, 0) }} min
                  <span class="vd-mode" :class="res.mode">{{ modeLabel(res.mode) }}</span>
                </div>
                <div class="vd-sub">
                  {{ res.feasible
                    ? t('执行器满功率稳态 {tss} ℃，需要 ≤ {req} ℃，余量 {margin} K', {
                        tss: fx(res.feasibility.Tss_min, 2), req: fx(res.feasibility.Tss_req, 2),
                        margin: fx(res.feasibility.Tss_req - res.feasibility.Tss_min, 2) })
                    : t('差 {d} K：执行器满功率稳态 {tss} ℃ 高于需要的 {req} ℃', {
                        d: fx(res.shortfall_K, 2), tss: fx(res.feasibility.Tss_min, 2), req: fx(res.feasibility.Tss_req, 2) }) }}
                </div>
              </div>
            </div>
          </section>

          <!-- 满功率 → 智能调控 交班说明 -->
          <section v-if="res.mode === 'handover' && res.handover" class="mpc-card mpc-handover">
            <div class="mpc-card-hd">
              <span class="mpc-card-tt">{{ t('两段式：先满功率，降到阈值后交接') }}</span>
              <span class="mpc-sub">
                {{ t('当前温度高于 {th} ℃ 时按安全规则先满功率', { th: fx(res.handover.threshold_C, 0) }) }}
              </span>
            </div>
            <div class="ho-flow">
              <div class="ho-box hot">
                <em>{{ t('第一段 · 满功率') }}</em>
                <b>{{ fx(res.handover.t_min, 2) }}<i>min</i></b>
                <s>{{ t('{v} V / {i} A，耗 {e} Wh', {
                  v: fx(res.plan[0].v_fan, 0), i: fx(res.plan[0].i_tec, 0),
                  e: fx(res.handover.phase1_energy_wh, 3) }) }}</s>
              </div>
              <div class="ho-arrow">
                <span>{{ t('降到') }} {{ fx(res.handover.threshold_C, 0) }} ℃</span>
                <i>→</i>
              </div>
              <div class="ho-box cool">
                <em>{{ t('第二段 · 智能调控') }}</em>
                <b>{{ fx(res.handover.remaining_min, 2) }}<i>min</i></b>
                <s>{{ t('剩余时间按目标 {tt} ℃ 重解：{n} 段 × {d} s', {
                  tt: fmtT(res.request.t_target), n: res.handover.phase2_segments,
                  d: fx(res.handover.phase2_seg_s, 0) }) }}</s>
              </div>
            </div>
          </section>

          <section class="mpc-card mpc-metrics">
            <div class="mt">
              <em>{{ t('计划末温') }}</em>
              <b>{{ fx(res.final_T, 2) }}<i>℃</i></b>
              <s :class="res.target_ok ? 'ok' : 'bad'">{{ res.target_ok ? t('达标') : t('未达标') }}</s>
            </div>
            <div class="mt">
              <em>{{ t('计划电耗') }}</em>
              <b>{{ fx(res.energy_wh, 4) }}<i>Wh</i></b>
              <s>{{ t('全程满功率 {v}', { v: fx(res.baseline_wh, 3) }) }}</s>
            </div>
            <div class="mt">
              <em>{{ t('相对满功率节省') }}</em>
              <b>{{ res.saving_pct == null ? '—' : fx(res.saving_pct, 1) }}<i>%</i></b>
              <s>{{ t('按两个功率函数计算') }}</s>
            </div>
            <div class="mt">
              <em>{{ t('纯风扇 24 V 可达') }}</em>
              <b>{{ fx(res.fan_only.reach_T, 2) }}<i>℃</i></b>
              <s :class="res.fan_only.enough ? 'ok' : 'bad'">
                {{ res.fan_only.enough ? t('够用，无需制冷片') : t('不够，需开制冷片') }}
              </s>
            </div>
          </section>

          <!-- 分段动作 -->
          <section class="mpc-card">
            <div class="mpc-card-hd">
              <span class="mpc-card-tt">{{ t('能耗最优动作（每段设定值与运行时长）') }}</span>
              <span class="mpc-sub">{{ t('段时长是「本轮反馈未更新时该跑多久」的参考值；闭环按反馈重解，不按段切换') }}</span>
            </div>
            <div class="mpc-apply-bar">
              <button class="mpc-btn primary sm" :disabled="busy.apply || !enabled || loopOn"
                      @click="startLoop">
                {{ busy.apply ? t('下发中…') : (loopOn ? t('闭环运行中') : t('下发并开始闭环')) }}
              </button>
              <button class="mpc-btn sm danger" :disabled="busy.apply" @click="stopAll"
                      :title="t('停止始终真实执行，不受「试运行」影响')">
                {{ t('停止并归零') }}
              </button>
              <label class="ap-dry" :title="t('勾选时只校验点位与取值，不向设备发命令、不启动闭环')">
                <input type="checkbox" v-model="dryRun" />
                {{ t('试运行') }}
              </label>
              <span class="ap-map">
                {{ t('风扇 → {a}（恒压）· 制冷片 → {b}（恒流）', {
                    a: 'fengshan-power.voltage_set', b: 'zhileng-power.current_set' }) }}
              </span>
            </div>
            <div v-if="applyMsg" class="mpc-apply-msg" :class="applyOk ? 'ok' : 'bad'">
              {{ applyMsg }}
            </div>
            <div v-if="!enabled" class="mpc-apply-msg bad">
              {{ t('模型未启用：请先点右上角「启用该模型」，启用后才允许下发到设备。') }}
            </div>
            <table class="mpc-tb">
              <thead>
                <tr>
                  <th>{{ t('段') }}</th><th>{{ t('风扇') }}</th><th>{{ t('制冷片') }}</th>
                  <th>{{ t('运行时长') }}</th><th>{{ t('段末温度') }}</th><th>{{ t('功率') }}</th><th>{{ t('电耗') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="s in shownPlan" :key="s.index"
                    :class="{ 'seg-now': loopData && loopData.action && Math.abs(loopData.action.v_fan - s.v_fan) < 1e-9 && Math.abs(loopData.action.i_tec - s.i_tec) < 1e-9 }">
                  <td>{{ s.index + 1 }}</td>
                  <td class="hl">{{ fx(s.v_fan, 0) }} V</td>
                  <td :class="{ hl: s.i_tec > 0 }">{{ fx(s.i_tec, 2) }} A</td>
                  <td>{{ fmtDur(s.duration_s) }}</td>
                  <td>{{ fx(s.T_start, 2) }} → <b>{{ fx(s.T_end, 2) }}</b> ℃</td>
                  <td>{{ fx(s.power_w, 3) }} W</td>
                  <td>{{ fx(s.energy_wh, 4) }} Wh</td>
                </tr>
              </tbody>
            </table>
            <p class="mpc-hint">{{ t('点「下发并开始闭环」会把当前段（第 1 段的 v_fan / i_tec）真正写到两台电源；之后每台反馈设备各上报一次，就用最新温度与剩余时间重解一次并下发新的当前段。') }}</p>
          </section>

          <!-- 闭环运行状态（只在启动过闭环后出现，避免未启动时显示一堆 0） -->
          <section class="mpc-card" v-if="loopData && (loopData.running || loopData.rounds || loopData.reason)">
            <div class="mpc-card-hd">
              <span class="mpc-card-tt">
                {{ t('闭环运行状态') }}
                <span class="loop-badge" :class="loopData.running ? 'on' : 'off'">
                  {{ loopData.running ? t('运行中') : t('已停止') }}
                </span>
              </span>
              <span class="mpc-sub" v-if="loopData.running">
                {{ t('剩余 {m} min · 第 {r} 轮 · 重解 {p} 次 · 下发 {s} 次', {
                    m: fx(loopData.remaining_min, 1), r: loopData.rounds,
                    p: loopData.replans, s: loopData.sends }) }}
              </span>
              <span class="mpc-sub" v-else>{{ loopData.reason || t('尚未启动') }}</span>
            </div>

            <div class="loop-feeds">
              <span class="lf-tt">{{ t('本轮反馈') }} <b>{{ feedDone }}/{{ feedTotal }}</b></span>
              <span v-for="(f, k) in loopData.feeds" :key="k" class="lf-item"
                    :class="f.fresh ? 'ok' : (f.reported ? 'wait' : 'bad')">
                <i></i>{{ f.device }}
                <s v-if="f.age_s != null">{{ fx(f.age_s, 0) }}s</s>
                <s v-else>{{ t('无上报') }}</s>
              </span>
              <span class="lf-rule">{{ t('三台各报一次 → 重解并下发（最小间隔 {s}s）', { s: fx(loopData.params.min_replan_s, 0) }) }}</span>
            </div>

            <div class="loop-grid">
              <div class="lg-cell">
                <label>{{ t('当前执行') }}</label>
                <b v-if="loopData.action">{{ fx(loopData.action.v_fan, 0) }}<i>V</i> / {{ fx(loopData.action.i_tec, 2) }}<i>A</i></b>
                <b v-else>—</b>
              </div>
              <div class="lg-cell">
                <label>{{ t('最近重解温度') }}</label>
                <b>{{ fx(loopData.plan_t_s, 2) }}<i>℃</i></b>
              </div>
              <div class="lg-cell">
                <label>{{ t('最近重解时间') }}</label>
                <b class="sm">{{ loopData.plan_ts || '—' }}</b>
              </div>
              <div class="lg-cell">
                <label>{{ t('目标 / 时限') }}</label>
                <b>{{ fx(loopData.t_target, 1) }}<i>℃</i> / {{ fx(loopData.horizon_min, 0) }}<i>min</i></b>
              </div>
            </div>

            <div v-if="loopData.last_error" class="mpc-apply-msg bad">{{ loopData.last_error }}</div>

            <div class="loop-flow" v-if="loopData.lines && loopData.lines.length">
              <div v-for="(l, i) in loopData.lines.slice().reverse()" :key="i" class="lf-line">{{ l }}</div>
            </div>
          </section>

          <!-- 预测轨迹 -->
          <section class="mpc-card">
            <div class="mpc-card-hd">
              <span class="mpc-card-tt">{{ t('温度轨迹（模型预测）') }}</span>
              <span class="mpc-sub">{{ t('虚线为目标温度') }}</span>
            </div>
            <svg class="mpc-chart" :viewBox="`0 0 ${chart.w} ${chart.h}`" preserveAspectRatio="none">
              <line v-for="(g, i) in chart.grid" :key="'g' + i" :x1="chart.pad" :x2="chart.w - chart.pad"
                    :y1="g.y" :y2="g.y" class="cgrid" />
              <text v-for="(g, i) in chart.grid" :key="'t' + i" :x="chart.pad - 6" :y="g.y + 3"
                    class="clabel" text-anchor="end">{{ g.v }}℃</text>
              <line :x1="chart.pad" :x2="chart.w - chart.pad" :y1="chart.tgtY" :y2="chart.tgtY" class="ctarget" />
              <polyline :points="chart.line" class="cline" />
              <circle :cx="chart.last.x" :cy="chart.last.y" r="3" class="cdot" />
            </svg>
            <div class="mpc-chart-x">
              <span>0</span><span>{{ fx(res.request.horizon_min / 2, 0) }}</span><span>{{ fx(res.request.horizon_min, 0) }} min</span>
            </div>
          </section>

          <!-- 恒定动作对比（现场最好执行） -->
          <section class="mpc-card">
            <div class="mpc-card-hd">
              <span class="mpc-card-tt">{{ t('恒定动作对比') }}</span>
              <span class="mpc-sub">{{ t('全程只用一个档位时，按省电排序（只列能达标的）') }}</span>
            </div>
            <table class="mpc-tb">
              <thead>
                <tr><th>{{ t('风扇') }}</th><th>{{ t('制冷片') }}</th><th>{{ t('功率') }}</th><th>{{ t('末温') }}</th><th>{{ t('电耗') }}</th><th>{{ t('达标') }}</th></tr>
              </thead>
              <tbody>
                <tr v-for="(a, i) in res.alternatives" :key="'a' + i" :class="{ pick: i === 0 && a.ok }">
                  <td class="hl">{{ fx(a.v_fan, 0) }} V</td>
                  <td :class="{ hl: a.i_tec > 0 }">{{ fx(a.i_tec, 2) }} A</td>
                  <td>{{ fx(a.power_w, 3) }} W</td>
                  <td>{{ fx(a.final_T, 2) }} ℃</td>
                  <td>{{ fx(a.energy_wh, 4) }} Wh</td>
                  <td><span class="tg" :class="a.ok ? 'ok' : 'bad'">{{ a.ok ? t('是') : t('否') }}</span></td>
                </tr>
              </tbody>
            </table>
            <p class="mpc-hint" v-if="res.best_constant">
              {{ t('最省电的恒定档位：{v} V / {i} A，{e} Wh，末温 {t} ℃（分段解 {se} Wh，靠分段再省一点）', {
                  v: fx(res.best_constant.v_fan, 0), i: fx(res.best_constant.i_tec, 2),
                  e: fx(res.best_constant.energy_wh, 4), t: fx(res.best_constant.final_T, 2),
                  se: fx(res.energy_wh, 4) }) }}
            </p>
          </section>

          <!-- 其他档位到达目标所需时间 + 结论说明 -->
          <section class="mpc-card">
            <div class="mpc-card-hd"><span class="mpc-card-tt">{{ t('到目标温度的用时（恒定动作）') }}</span></div>
            <div class="mpc-kv three">
              <div class="kv"><em>24 V / 0 A</em><b>{{ res.time_to_target_min.fan24 == null ? '—' : fx(res.time_to_target_min.fan24, 2) + ' min' }}</b></div>
              <div class="kv"><em>20 V / 0 A</em><b>{{ res.time_to_target_min.fan20 == null ? '—' : fx(res.time_to_target_min.fan20, 2) + ' min' }}</b></div>
              <div class="kv"><em>24 V / 3 A</em><b>{{ res.time_to_target_min.fan24_tec3 == null ? '—' : fx(res.time_to_target_min.fan24_tec3, 2) + ' min' }}</b></div>
            </div>
            <ul class="mpc-notes">
              <li v-for="(n, i) in res.notes" :key="'n' + i">{{ n }}</li>
              <li>{{ t('本页只做「模型 + 求解」：给出的设定值序列由现场控制回路下发，平台当前不直接操作设备、也不做闭环跟踪。') }}</li>
            </ul>
          </section>
        </template>

        <!-- 决策日志：每次求解留一条流水（收到反馈 → 判定 → 下发档位 → 预计结果） -->
        <section class="mpc-card mpc-logcard">
          <div class="mpc-card-hd">
            <span class="mpc-card-tt">{{ t('决策日志') }}</span>
            <span class="mpc-sub">{{ t('落盘 backend/logs/mpc.log，刷新后仍在') }}</span>
            <span class="mpc-log-ops">
              <button class="mpc-mini" :disabled="logBusy.load" @click="loadLogs">
                {{ logBusy.load ? t('刷新中…') : t('刷新') }}
              </button>
              <button class="mpc-mini" :disabled="logBusy.clear || !logs.length" @click="clearLogs">
                {{ t('清空') }}
              </button>
            </span>
          </div>
          <p v-if="!logs.length" class="mpc-muted mpc-log-empty">
            {{ t('还没有日志：点左侧「求解能耗最优动作」，这里会出现一条「收到 45.0 ℃ → 判可达 → 下发 16 V / 0 A」的流水。') }}
          </p>
          <ol v-else class="mpc-loglist">
            <li v-for="(r, i) in logs" :key="r.ts + '-' + i" class="lg-item" :class="r.kind">
              <div class="lg-hd">
                <span class="lg-ts">{{ r.ts }}</span>
                <span class="lg-kind">{{ kindLabel(r.kind) }}</span>
                <span class="lg-tt">{{ r.title }}</span>
              </div>
              <ul class="lg-lines">
                <li v-for="(ln, j) in r.lines" :key="j">{{ ln }}</li>
              </ul>
            </li>
          </ol>
        </section>
      </div>
    </div>
  </div>
</template>

<script setup>
import { reactive, ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { api } from '../api/client'
import { t } from '../i18n'
import { useSimStore } from '../stores/sim'

const store = useSimStore()

// embedded=true：内嵌进 AI 群控（模型库 → MPC 控温优化）时不再占满整个视图、不重复标题条
const props = defineProps({
  embedded: { type: Boolean, default: false },
})
const isEmbedded = computed(() => !!props.embedded)

const status = reactive({
  available: false,
  enabled: false,
  model: {},
  params: { full_power: {} },
  levels: { fan_v: [], tec_i: [], tec_blacklist: [] },
  checks: [],
})
const lim = reactive({ tNow: [20, 60], tTarget: [20, 44.9] })

const form = reactive({ tNow: 45, tTarget: 39, horizonMin: 12, tenv: 26.5, twater: 31 })
const res = ref(null)
const err = ref('')
const busy = reactive({ status: false, enable: false, plan: false, apply: false })
const loading = reactive({ status: true })

// 下发闸门与回执：只有「自检通过 + 已启用」才允许写设备点位（后端会再校验一次）
const enabled = computed(() => !!status.available && !!status.enabled)
const applyMsg = ref('')
const applyOk = ref(false)
// 试运行默认勾选：第一次点「下发」只核对 6 条点位载荷，确认无误后再取消勾选真正写设备。
// 工业回路宁可按两次，也不要因为一次误点把 24 V / 3 A 直接推到现场。
const dryRun = ref(true)

/* ---- 闭环状态：轮次、各设备本轮是否已反馈、当前执行动作、最近重解时间 ----
   节拍由后端决定：三台设备（zhileng-temp / env-temp / shuitong-temp）各出现一次
   新上报算一轮，后端用这一轮的最新温度重解并下发。前端只做展示与起停。       */
const loopData = ref(null)
const loopOn = computed(() => !!(loopData.value && loopData.value.running))
let loopTimer = null
// true = 表格展示闭环最近一次重解的计划；false = 展示「求解」返回的计划。
// 点「下发并开始闭环」后切到 true，重新点「求解」时切回 false。
const preferLoop = ref(false)

// 闭环运行时，表格显示「最近一次重解」的计划（而不是点启动那一刻的旧计划），
// 否则会出现「表上写 18 V、实际执行 15 V」的对不上。
const shownPlan = computed(() => {
  const lp = loopData.value && loopData.value.plan
  if (preferLoop.value && lp && lp.length) return lp
  return (res.value && res.value.plan) || []
})

// 本轮已经上报过新数据的设备数（三台都上报 = 触发重解）
const feedDone = computed(() => {
  const f = (loopData.value && loopData.value.feeds) || {}
  return Object.values(f).filter((x) => x && x.fresh).length
})
const feedTotal = computed(() => Object.keys((loopData.value && loopData.value.feeds) || {}).length)

async function pollLoop() {
  try {
    const r = await api.mpcLoop()
    if (r && r.ok !== false) {
      loopData.value = r
      if (r.running) preferLoop.value = true   // 页面刷新后也能接上「显示最新重解计划」
    }
  } catch (e) {
    /* 轮询失败不打断页面（服务重启期间会短暂 502） */
  }
}

/* ---- 实时反馈：当前温度 / 室温 / 水桶温度 跟随 MQTT 上报 ----------------------------------
   数据链路：盒子 → 云端 Broker → 平台 mqtt_source（CLOUD_DEVICES）→ GET /api/mpc/feedback → 本页。
   点位：zhileng-temp / env-temp / shuitong-temp（见后端 params.FB_SOURCES）。
   注意：这里直接读「云端设备」而非仿真流程里的设备实例 —— 流程 model.json 为空时也能取到读数。 */
const LIVE_KEYS = ['tNow', 'tenv', 'twater']
// 接口字段名 -> 表单字段名（后端沿用了 plan 请求里的 t_now 命名）
const LIVE_API_KEY = { tNow: 't_now', tenv: 'tenv', twater: 'twater' }
const live = reactive({ tNow: null, tenv: null, twater: null })
const follow = reactive({ tNow: true, tenv: true, twater: true })
const fbMeta = reactive({ stale_s: 60, ts: '' })
const fbErr = ref('')
// 目标温度是否「随实时温度自动取降 5 K」；用户手动改过就固定下来
const autoTarget = ref(true)
let feedTimer = null

const allFollow = computed(() => LIVE_KEYS.every((k) => follow[k]))

function chipText(k) {
  const s = live[k]
  if (!follow[k]) return t('手动')
  if (!s) return t('读取中')
  if (s.value == null) return t('无上报')
  return `${Number(s.value).toFixed(1)} ℃`
}

function chipCls(k) {
  const s = live[k]
  if (!follow[k]) return { off: true }
  if (!s) return { wait: true }
  if (s.value == null) return { off: true }
  return { on: !!s.online, stale: !s.online }
}

function chipTitle(k) {
  const s = live[k]
  if (!s) return t('尚未读取实时值')
  const head = `${s.device}${s.prop ? '.' + s.prop : ''}`
  if (s.value == null) return `${head}：${t('当前无上报（设备离线或未订阅）')}`
  const age = s.age_s == null ? '' : t(' · {s} s 前', { s: s.age_s })
  const tsx = s.ts ? ' · ' + s.ts : ''
  const warn = s.online ? '' : t(' · 已超 {s} s 未更新（陈旧）', { s: fbMeta.stale_s })
  return `${head}${tsx}${age}${warn}`
}

/** 把实时值写进表单（只写「跟随中」的字段）；目标温度在自动模式下保持「降 5 K」。 */
function applyLive() {
  for (const k of LIVE_KEYS) {
    const s = live[k]
    if (!follow[k] || !s || s.value == null) continue
    form[k] = Number(s.value)
  }
  if (autoTarget.value && form.tNow != null && Number(form.tTarget) >= Number(form.tNow) - 0.05) {
    const tgt = Math.max(lim.tTarget[0], Math.round((Number(form.tNow) - 5) * 10) / 10)
    form.tTarget = Math.min(tgt, lim.tTarget[1])
  }
}

async function pollFeedback() {
  try {
    const r = await api.mpcFeedback()
    if (!r || r.ok === false) {
      fbErr.value = (r && r.error) || t('实时值不可用')
      return
    }
    fbErr.value = ''
    fbMeta.stale_s = r.stale_s || 60
    fbMeta.ts = r.snapshot_ts || ''
    const s = r.sources || {}
    for (const k of LIVE_KEYS) live[k] = s[LIVE_API_KEY[k]] || null
    applyLive()
  } catch (e) {
    fbErr.value = t('读取实时值失败：{msg}', { msg: e.message })
  }
}

// 手改某个字段 = 接管该字段（停止跟随），避免下一次轮询把它覆盖掉
function onManual(k) {
  follow[k] = false
  if (k === 'tTarget') autoTarget.value = false
}

function toggleFollow(k) {
  follow[k] = !follow[k]
  if (follow[k]) applyLive()
}

function toggleAllFollow() {
  const next = !allFollow.value
  for (const k of LIVE_KEYS) follow[k] = next
  if (next) applyLive()
}

function resetAutoTarget() {
  autoTarget.value = true
  applyLive()
}

// 决策日志（后端落盘、按时间倒序回显；刷新页面不丢）
const logs = ref([])
const logBusy = reactive({ load: false, clear: false })
const KIND_LABEL = { plan: '求解', reject: '拒绝', enable: '启用', disable: '停用' }
const kindLabel = (k) => t(KIND_LABEL[k] || k)

async function loadLogs() {
  if (logBusy.load) return
  logBusy.load = true
  try {
    const r = await api.mpcLogs(100)
    if (r && r.ok !== false) logs.value = Array.isArray(r.items) ? r.items : []
  } catch (e) {
    /* 日志读不到不影响求解：静默降级为空列表 */
  } finally {
    logBusy.load = false
  }
}

async function clearLogs() {
  if (logBusy.clear) return
  logBusy.clear = true
  try {
    const r = await api.mpcLogClear()
    if (r && r.ok === false) err.value = r.error || t('清空日志失败')
    else logs.value = []
  } catch (e) {
    err.value = t('清空日志失败：{msg}', { msg: e.message })
  } finally {
    logBusy.clear = false
  }
}

const fx = (v, n = 2) => (v == null || Number.isNaN(Number(v)) ? '—' : Number(v).toFixed(n))
const fmtT = (v) => fx(v, 1)
// 段时长：不足 1 min 显示秒，否则显示「分 + 秒」（现场按秒执行，最小段长 300 s）
const fmtDur = (s) => {
  if (s == null || Number.isNaN(Number(s))) return '—'
  const v = Number(s)
  return v < 60 ? `${v.toFixed(0)} s` : `${Math.floor(v / 60)} min ${Math.round(v % 60)} s`
}

// 三种模式：整段满功率（剩余时间不够再排一段）/ 满功率→智能调控交班 / 纯智能调控
const MODE_TEXT = {
  full_power: '满功率模式',
  handover: '满功率 → 智能调控',
  smart: '智能调控',
}
const modeLabel = (m) => t(MODE_TEXT[m] || '智能调控')

const stateCls = computed(() => (!status.available ? 'bad' : status.enabled ? 'on' : 'idle'))
const stateText = computed(() => {
  if (loading.status) return t('正在自检…')
  if (!status.available) return t('自检未通过，暂不可启用')
  return status.enabled ? t('已启用 · 求解结果可下发') : t('可用 · 尚未启用')
})

async function loadStatus() {
  loading.status = true
  try {
    const s = await api.mpcStatus()
    if (s && s.ok !== false) {
      Object.assign(status, s)
      if (s.limits) {
        lim.tNow = s.limits.t_now || lim.tNow
        lim.tTarget = s.limits.t_target || lim.tTarget
      }
    } else {
      status.available = false
      err.value = (s && s.error) || t('读取模型状态失败')
    }
  } catch (e) {
    status.available = false
    err.value = t('无法连接后端：{msg}', { msg: e.message })
  } finally {
    loading.status = false
  }
}

async function toggleEnable() {
  if (!status.available || busy.enable) return
  busy.enable = true
  err.value = ''
  try {
    const r = await api.mpcEnable(!status.enabled)
    if (r && r.ok === false) {
      err.value = r.error || t('启用失败')
    } else {
      Object.assign(status, r.status || {})
      store.showToast(status.enabled ? t('MPC 控温模型已启用') : t('MPC 控温模型已停用'), status.enabled ? 'success' : 'info')
      loadLogs()        // 启用 / 停用也记一条，便于对时间线
    }
  } catch (e) {
    err.value = t('切换失败：{msg}', { msg: e.message })
  } finally {
    busy.enable = false
  }
}

async function runPlan() {
  if (busy.plan) return
  err.value = ''
  busy.plan = true
  try {
    const r = await api.mpcPlan({
      t_now: Number(form.tNow),
      t_target: Number(form.tTarget),
      horizon_min: Number(form.horizonMin),
      tenv: Number(form.tenv),
      twater: Number(form.twater),
    })
    if (r && r.ok === false) {
      res.value = null
      err.value = r.error || t('求解失败')
    } else {
      res.value = r
      preferLoop.value = false      // 手动求解后，表格以这次求解为准
    }
  } catch (e) {
    err.value = t('求解失败：{msg}', { msg: e.message })
  } finally {
    busy.plan = false
    loadLogs()          // 请求被拒（如目标高于当前温度）也留了日志，一并回显
  }
}

function resetForm() {
  // 恢复的是「手动演示」场景：先把三个字段从实时跟随摘掉，再填固定值，
  // 否则下一次轮询（3 s）会把刚填的 45/26.5/31 立刻覆盖成实测值。
  for (const k of LIVE_KEYS) follow[k] = false
  autoTarget.value = false
  form.tNow = 45
  form.tTarget = 39
  form.horizonMin = 12
  form.tenv = 26.5
  form.twater = 31
}

/* ---- 闭环：下发现阶段 + 之后每「反馈齐一轮」重解一次 ----------------------------------
   映射由后端 actuator 决定（本页只显示，不参与计算）：
     v_fan -> fengshan-power.voltage_set   （恒压，work_mode=0）
     i_tec -> zhileng-power.current_set    （恒流，work_mode=1）
   后端会自动补齐 work_mode / output_on —— 少写一个 output_on 就是
   「命令成功、设备没反应」的经典假象，所以这里不做任何裁剪。            */
async function startLoop() {
  if (busy.apply) return
  if (!enabled.value) {
    applyOk.value = false
    applyMsg.value = t('模型未启用：请先点右上角「启用该模型」，启用后才允许下发到设备。')
    return
  }
  busy.apply = true
  applyMsg.value = ''
  try {
    const r = await api.mpcLoopStart({
      t_target: Number(form.tTarget),
      horizon_min: Number(form.horizonMin),
      dry_run: dryRun.value,
      note: t('页面启动闭环'),
    })
    applyOk.value = !!(r && r.ok)
    // 表单里的目标/时限可能与上一次「求解」不同；下发时后端是按最新反馈重解的，
    // 所以用返回的整份结果覆盖表格，保证「表上看到的」就是「刚下发的」。
    if (r && r.ok && r.plan_result && r.plan_result.plan) res.value = r.plan_result
    if (r && r.ok && r.dry_run) {
      const seg = (r.plan && r.plan[0]) || {}
      applyMsg.value = t('试运行通过（未下发、未启动闭环）：将下发风扇 {v} V → fengshan-power.voltage_set（恒压），制冷片 {i} A → zhileng-power.current_set（恒流）。核对无误后取消勾选「试运行」再点一次。', {
        v: fx(seg.v_fan, 0), i: fx(seg.i_tec, 2),
      })
    } else if (r && r.ok) {
      const seg = r.action || (r.plan && r.plan[0]) || {}
      applyMsg.value = t('已下发当前段并启动闭环：风扇 {v} V / 制冷片 {i} A。之后三台反馈设备各上报一次，就用最新温度与剩余时间重解并下发新的当前段。', {
        v: fx(seg.v_fan, 0), i: fx(seg.i_tec, 2),
      })
      store.showToast(t('已下发并进入闭环'), 'success')
      preferLoop.value = true
    } else {
      applyMsg.value = (r && (r.error || r.message)) || t('下发失败')
      store.showToast(applyMsg.value, 'error')
    }
    await pollLoop()
  } catch (e) {
    applyOk.value = false
    applyMsg.value = t('下发失败：{msg}', { msg: e.message })
  } finally {
    busy.apply = false
    loadLogs()
  }
}

async function stopAll() {
  if (busy.apply) return
  busy.apply = true
  applyMsg.value = ''
  try {
    // 停止永远真执行：不跟随「试运行」开关。
    // 试运行只用于「下发前核对」，一旦用户想停，就必须真的断输出 ——
    // 否则会出现「页面显示已归零、设备还在制冷」的最坏情况。
    const r = await api.mpcLoopStop(loopOn.value ? '页面停止闭环' : '页面手动停止')
    const ok = !!(r && r.ok)
    applyOk.value = ok
    applyMsg.value = ok
      ? (loopOn.value ? t('已停止闭环：两路输出归零（output_on=0，设定值清零）')
        : t('已停止：两路输出归零（output_on=0，设定值清零）'))
      : ((r && (r.error || r.message)) || t('停止失败'))
    if (ok) store.showToast(t('输出已归零'), 'info')
    await pollLoop()
  } catch (e) {
    applyOk.value = false
    applyMsg.value = t('停止失败：{msg}', { msg: e.message })
  } finally {
    busy.apply = false
    loadLogs()
  }
}

/* ---- 轨迹折线图：纯 SVG，不引第三方图表库（本页只需一条线） ---- */
const chart = computed(() => {
  const w = 640, h = 200, pad = 42
  const pts = (res.value && res.value.traj) || []
  const tgt = res.value ? res.value.request.t_target : 0
  if (!pts.length) return { w, h, pad, grid: [], line: '', tgtY: 0, last: { x: 0, y: 0 } }
  const ys = pts.map((p) => p.T).concat([tgt])
  let lo = Math.min(...ys), hi = Math.max(...ys)
  const span = Math.max(0.5, hi - lo)
  lo -= span * 0.08
  hi += span * 0.08
  const xMax = Math.max(1, pts[pts.length - 1].t_s)
  const sx = (t) => pad + (t / xMax) * (w - pad - 10)
  const sy = (T) => pad - 14 + (1 - (T - lo) / (hi - lo)) * (h - pad - 6)
  const grid = []
  for (let k = 0; k <= 4; k += 1) {
    const v = lo + ((hi - lo) * k) / 4
    grid.push({ y: sy(v), v: v.toFixed(1) })
  }
  const line = pts.map((p) => `${sx(p.t_s).toFixed(1)},${sy(p.T).toFixed(1)}`).join(' ')
  const last = { x: sx(pts[pts.length - 1].t_s), y: sy(pts[pts.length - 1].T) }
  return { w, h, pad, grid, line, tgtY: sy(tgt), last }
})

onMounted(() => {
  loadStatus()
  loadLogs()
  pollFeedback()
  pollLoop()
  feedTimer = setInterval(pollFeedback, 3000)
  // 闭环状态轮询：2 s 一次，**始终运行**（不只在自己启动后）。
  // 这样即使闭环是由其它地方启动的、或页面刚刷新，也能立刻看到真实状态，
  // 而不是显示一个「已停止」的假象。
  loopTimer = setInterval(pollLoop, 2000)
})

onBeforeUnmount(() => {
  if (feedTimer) {
    clearInterval(feedTimer)
    feedTimer = null
  }
  if (loopTimer) {
    clearInterval(loopTimer)
    loopTimer = null
  }
})
</script>

<style scoped>
.mpc-view {
  position: absolute; inset: 0;
  display: flex; flex-direction: column;
  background: var(--panel-2);
  color: var(--text);
  overflow: hidden;
}
/* 内嵌进 AI 群控：不再绝对定位占满视图，而是填满父级内容区；标题条退化为一行右侧状态 */
.mpc-view.embedded {
  position: relative; inset: auto; height: 100%;
  background: transparent;
}
.mpc-view.embedded .mpc-head {
  justify-content: flex-end;
  padding: 0 0 8px;
  background: transparent;
  border-bottom: none;
}
.mpc-view.embedded .mpc-body { padding: 0; }

/* ===== 顶部标识条 ===== */
.mpc-head {
  flex: none; display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 10px 14px; background: var(--panel); border-bottom: 1px solid var(--hairline);
}
.mpc-id { display: flex; align-items: center; gap: 10px; min-width: 0; }
.mpc-tag {
  flex: none; font-size: 11px; font-weight: 700; letter-spacing: .5px;
  padding: 5px 8px; border-radius: 5px;
  background: var(--accent-l); color: var(--accent-d); border: 1px solid var(--accent-d);
}
.mpc-id-txt { min-width: 0; }
.mpc-name { font-size: 14px; font-weight: 600; display: flex; align-items: center; gap: 7px; }
.mpc-ver { font-size: 10px; font-weight: 500; color: var(--muted); border: 1px solid var(--border);
  border-radius: 3px; padding: 0 4px; }
.mpc-desc { font-size: 11px; color: var(--muted); margin-top: 2px;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.mpc-state { flex: none; display: flex; align-items: center; gap: 8px; }
.mpc-dot { width: 7px; height: 7px; border-radius: 50%; background: var(--faint); }
.mpc-dot.ok { background: var(--green); }
.mpc-dot.on { background: var(--green); box-shadow: 0 0 0 3px rgba(46, 139, 87, .18); }
.mpc-dot.bad { background: var(--red); }
.mpc-dot.idle { background: var(--yellow); }
.mpc-state-txt { font-size: 12px; color: var(--muted); }
.mpc-sw {
  font-size: 12px; padding: 6px 12px; border-radius: 5px; cursor: pointer;
  background: var(--btn-bg); color: var(--text); border: 1px solid var(--border);
  transition: background .12s, border-color .12s;
}
.mpc-sw:hover:not(:disabled) { background: var(--btn-bg-hover); }
.mpc-sw.on { background: var(--accent-d); border-color: var(--accent-d); color: #fff; }
.mpc-sw:disabled { opacity: .5; cursor: not-allowed; }

/* ===== 主体两列 ===== */
.mpc-body {
  flex: 1 1 auto; min-height: 0; display: grid;
  grid-template-columns: minmax(300px, 360px) minmax(0, 1fr);
  gap: 10px; padding: 10px; overflow: hidden;
}
@media (max-width: 980px) { .mpc-body { grid-template-columns: 1fr; overflow: auto; } }
.mpc-col { min-height: 0; display: flex; flex-direction: column; gap: 10px; overflow: auto; padding-right: 2px; }

.mpc-card {
  background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  padding: 10px 12px; flex: none;
}
.mpc-card-hd { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
.mpc-card-tt { font-size: 12px; font-weight: 600; }
.mpc-sub { font-size: 10px; color: var(--faint); }
.mpc-pill { font-size: 10px; padding: 2px 7px; border-radius: 10px; border: 1px solid var(--border); }
.mpc-pill.ok { color: var(--green); border-color: var(--green); background: rgba(46, 139, 87, .08); }
.mpc-pill.bad { color: var(--red); border-color: var(--red); background: rgba(188, 59, 48, .08); }

/* 自检列表 */
.mpc-checks { list-style: none; margin: 0 0 8px; padding: 0; display: flex; flex-direction: column; gap: 6px; }
.mpc-checks li { display: flex; gap: 7px; font-size: 11px; line-height: 1.45; }
.ck-mark { flex: none; width: 14px; font-weight: 700; }
.mpc-checks li.ok .ck-mark { color: var(--green); }
.mpc-checks li.bad .ck-mark { color: var(--red); }
.ck-body { min-width: 0; display: flex; flex-direction: column; }
.ck-label { color: var(--text); }
.ck-detail { color: var(--muted); font-size: 10.5px; word-break: break-word; }
.mpc-muted { color: var(--faint); font-size: 11px; }

/* 键值表 */
.mpc-kv { display: grid; grid-template-columns: 1fr 1fr; gap: 4px 10px; }
.mpc-kv.three { grid-template-columns: repeat(3, 1fr); }
.mpc-kv .kv { display: flex; flex-direction: column; padding: 4px 6px; background: var(--panel-2); border-radius: 5px; }
.mpc-kv .kv em { font-style: normal; font-size: 10px; color: var(--muted); }
.mpc-kv .kv b { font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }

/* 档位 */
.mpc-levels { margin-top: 8px; display: flex; flex-direction: column; gap: 5px; }
.lv-row { display: flex; align-items: center; gap: 8px; }
.lv-lb { flex: none; width: 62px; font-size: 10px; color: var(--muted); }
.lv-vals { display: flex; flex-wrap: wrap; gap: 4px; }
.lv-vals i {
  font-style: normal; font-size: 10px; padding: 1px 5px; border-radius: 3px;
  background: var(--panel-3); color: var(--text); border: 1px solid var(--line-soft);
  font-variant-numeric: tabular-nums;
}
.lv-vals i.off { color: var(--faint); text-decoration: line-through; opacity: .65; }

/* 表单 */
.mpc-form { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
/* 每个字段两行：第一行「标题 + 实时值标签」，第二行「输入 + 单位」——
   单行排不下（标签最长 5 个汉字 + 值 + 单位 + 实时标签），挤在一起输入框只剩 30 px。 */
.fld { display: flex; flex-wrap: wrap; align-items: center; gap: 3px 5px;
  background: var(--panel-2); border: 1px solid var(--border); border-radius: 6px; padding: 4px 7px 5px; }
.fld > span { flex: 1 1 100%; font-size: 10.5px; color: var(--muted); }
.fld-top { display: flex; align-items: center; justify-content: space-between; gap: 6px; }
.fld input {
  flex: 1 1 auto; min-width: 0; background: transparent; border: none; outline: none;
  color: var(--text); font-size: 13px; font-weight: 600; font-variant-numeric: tabular-nums;
}
.fld em { flex: none; font-style: normal; font-size: 10px; color: var(--faint); }
.fld:focus-within { border-color: var(--accent-d); }

/* 实时值标签：绿=在线、黄=陈旧、灰=手动/无上报 */
.fld-src {
  display: inline-flex; align-items: center; gap: 4px; flex: none; cursor: pointer;
  font-size: 9px; line-height: 1.4; padding: 0 5px; border-radius: 8px;
  border: 1px solid var(--border); background: var(--panel-3); color: var(--faint);
}
.fld-src i { width: 5px; height: 5px; border-radius: 50%; background: currentColor; }
.fld-src.on { color: var(--green); border-color: rgba(46, 139, 87, .45); background: rgba(46, 139, 87, .09); }
.fld-src.stale { color: var(--yellow); border-color: rgba(190, 150, 20, .45); background: rgba(190, 150, 20, .1); }
.fld-src.off { color: var(--muted); }
.fld-src.auto { color: var(--accent-d); border-color: rgba(90, 130, 200, .45); background: var(--accent-l); }
.mpc-mini.follow.on { color: var(--green); border-color: rgba(46, 139, 87, .5); background: rgba(46, 139, 87, .1); }
.live-hint { opacity: .8; }

.mpc-hint { font-size: 10px; color: var(--faint); line-height: 1.5; margin: 8px 0 0; }
.mpc-actions { display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.mpc-btn {
  font-size: 12px; padding: 7px 12px; border-radius: 5px; cursor: pointer;
  background: var(--btn-bg); color: var(--text); border: 1px solid var(--border);
}
.mpc-btn:hover { background: var(--btn-bg-hover); }
.mpc-btn.primary { background: var(--accent-d); border-color: var(--accent-d); color: #fff; font-weight: 600; }
.mpc-btn.primary:hover { background: var(--accent-h); }
.mpc-btn:disabled { opacity: .55; cursor: not-allowed; }
.mpc-btn.sm { padding: 5px 10px; font-size: 11px; }
.mpc-btn.xs { padding: 2px 8px; font-size: 10px; line-height: 1.6; }
.mpc-err { font-size: 11px; color: var(--red); }

/* 下发条：按钮 + 点位映射 + 回执 */
.mpc-apply-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 0 10px; border-bottom: 1px solid var(--border); margin-bottom: 2px;
}
.ap-map { font-size: 10px; color: var(--faint); font-family: var(--mono, monospace); }
.ap-dry {
  display: inline-flex; align-items: center; gap: 4px; font-size: 10.5px;
  color: var(--muted); cursor: pointer; user-select: none;
}
.ap-dry input { width: 12px; height: 12px; cursor: pointer; }
.mpc-apply-msg {
  font-size: 10.5px; line-height: 1.6; padding: 6px 8px; border-radius: 4px; margin: 8px 0 4px;
}
.mpc-apply-msg.ok { color: var(--accent); background: rgba(34, 160, 120, .10); border-left: 2px solid var(--accent); }
.mpc-apply-msg.bad { color: var(--red); background: rgba(214, 69, 69, .10); border-left: 2px solid var(--red); }
.mpc-btn.danger { color: var(--red); border-color: rgba(214, 69, 69, .45); }
.mpc-btn.danger:hover { background: rgba(214, 69, 69, .10); }

/* 闭环状态卡片 */
.loop-badge {
  display: inline-block; margin-left: 6px; padding: 0 6px; border-radius: 8px;
  font-size: 9.5px; font-weight: 500; line-height: 15px; vertical-align: 1px;
  border: 1px solid var(--border); color: var(--muted);
}
.loop-badge.on { color: var(--green); border-color: var(--green); background: rgba(34, 160, 120, .10); }
.loop-badge.off { color: var(--faint); }
.loop-feeds {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
  padding: 8px 0; border-bottom: 1px solid var(--line-soft);
}
.lf-tt { font-size: 10px; color: var(--muted); }
.lf-tt b { color: var(--accent-d); font-variant-numeric: tabular-nums; }
.lf-item {
  display: inline-flex; align-items: center; gap: 4px; font-size: 10px;
  font-family: var(--mono, monospace); color: var(--muted);
  padding: 1px 6px; border-radius: 9px; border: 1px solid var(--border);
}
.lf-item i { width: 6px; height: 6px; border-radius: 50%; background: var(--faint); display: inline-block; }
.lf-item.ok { color: var(--green); border-color: rgba(34, 160, 120, .45); }
.lf-item.ok i { background: var(--green); }
.lf-item.wait { color: var(--orange, #d99a2b); border-color: rgba(217, 154, 43, .45); }
.lf-item.wait i { background: var(--orange, #d99a2b); }
.lf-item.bad { color: var(--red); border-color: rgba(214, 69, 69, .45); }
.lf-item.bad i { background: var(--red); }
.lf-item s { text-decoration: none; opacity: .75; }
.lf-rule { margin-left: auto; font-size: 9.5px; color: var(--faint); }
.loop-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; padding: 10px 0; }
.lg-cell label { display: block; font-size: 9.5px; color: var(--muted); margin-bottom: 2px; }
.lg-cell b { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; }
.lg-cell b.sm { font-size: 12px; color: var(--muted); }
.lg-cell b i { font-style: normal; font-size: 10px; color: var(--muted); margin: 0 2px 0 1px; }
.loop-flow {
  max-height: 132px; overflow-y: auto; border-top: 1px solid var(--line-soft); padding-top: 6px;
  font-family: var(--mono, monospace); font-size: 10px; line-height: 1.75; color: var(--muted);
}
.loop-flow .lf-line { white-space: pre-wrap; word-break: break-all; }
.mpc-tb tr.seg-now td { background: var(--accent-l); font-weight: 600; }

/* 空态 */
.mpc-empty { flex: 1 1 auto; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 6px; }
.mpc-empty-tt { font-size: 13px; font-weight: 600; color: var(--muted); }
.mpc-empty-desc { font-size: 11px; color: var(--faint); max-width: 420px; text-align: center; line-height: 1.6; }
.mpc-empty-loop {
  margin-top: 6px; padding: 8px 10px; border-radius: 5px; max-width: 460px;
  font-size: 11px; line-height: 1.7; color: var(--orange, #d99a2b);
  background: rgba(217, 154, 43, .10); border-left: 2px solid var(--orange, #d99a2b);
}
.mpc-empty-loop .mel-act { display: flex; align-items: center; gap: 8px; margin-top: 6px; }
.mpc-empty-loop .mel-act span { color: var(--muted); font-variant-numeric: tabular-nums; }

/* 结论条 */
.mpc-verdict { display: flex; align-items: center; }
.mpc-verdict.ok { border-left: 3px solid var(--green); }
.mpc-verdict.bad { border-left: 3px solid var(--red); }
.vd-left { display: flex; align-items: center; gap: 10px; }
.vd-badge { flex: none; font-size: 11px; font-weight: 700; padding: 4px 9px; border-radius: 5px; }
.mpc-verdict.ok .vd-badge { background: rgba(46, 139, 87, .12); color: var(--green); }
.mpc-verdict.bad .vd-badge { background: rgba(188, 59, 48, .12); color: var(--red); }
.vd-line { font-size: 13px; font-weight: 600; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.vd-mode { font-size: 10px; font-weight: 500; padding: 1px 6px; border-radius: 3px;
  background: var(--panel-3); color: var(--muted); border: 1px solid var(--line-soft); }
.vd-mode.full_power { color: var(--orange); border-color: var(--orange); }
.vd-mode.handover { color: var(--accent-d); border-color: var(--accent-d); background: var(--accent-l); }
.vd-sub { font-size: 10.5px; color: var(--muted); margin-top: 3px; }

/* 两段式交班 */
.mpc-handover { display: flex; flex-direction: column; gap: 10px; }
.ho-flow { display: grid; grid-template-columns: 1fr 96px 1fr; gap: 8px; align-items: stretch; }
@media (max-width: 760px) { .ho-flow { grid-template-columns: 1fr; } }
.ho-box {
  border: 1px solid var(--line-soft); border-radius: 6px; padding: 9px 11px;
  background: var(--panel-3); display: flex; flex-direction: column; gap: 2px;
  border-left-width: 3px;
}
.ho-box.hot { border-left-color: var(--orange); }
.ho-box.cool { border-left-color: var(--accent-d); }
.ho-box em { font-size: 10px; font-style: normal; color: var(--muted); }
.ho-box b { font-size: 17px; font-weight: 600; color: var(--text); line-height: 1.1; }
.ho-box b i { font-size: 10px; font-style: normal; font-weight: 500; color: var(--muted); margin-left: 3px; }
.ho-box s { font-size: 10px; text-decoration: none; color: var(--faint); line-height: 1.45; }
.ho-arrow {
  display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px;
  color: var(--muted); font-size: 10px;
}
.ho-arrow i { font-style: normal; font-size: 16px; color: var(--accent-d); line-height: 1; }

/* 指标 */
.mpc-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
@media (max-width: 760px) { .mpc-metrics { grid-template-columns: 1fr 1fr; } }
.mt { display: flex; flex-direction: column; gap: 2px; padding: 6px 8px; background: var(--panel-2); border-radius: 6px; }
.mt em { font-style: normal; font-size: 10px; color: var(--muted); }
.mt b { font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
.mt b i { font-style: normal; font-size: 10px; color: var(--muted); margin-left: 2px; }
.mt s { text-decoration: none; font-size: 10px; color: var(--faint); }
.mt s.ok { color: var(--green); }
.mt s.bad { color: var(--red); }

/* 表格 */
.mpc-tb { width: 100%; border-collapse: collapse; font-size: 11px; font-variant-numeric: tabular-nums; }
.mpc-tb th { text-align: left; font-weight: 500; color: var(--muted); font-size: 10px;
  padding: 4px 6px; border-bottom: 1px solid var(--hairline); }
.mpc-tb td { padding: 5px 6px; border-bottom: 1px solid var(--line-soft); }
.mpc-tb tr:last-child td { border-bottom: none; }
.mpc-tb td.hl { font-weight: 600; color: var(--accent-d); }
.mpc-tb tr.pick td { background: var(--accent-l); }
.tg { font-size: 10px; padding: 1px 6px; border-radius: 3px; }
.tg.ok { color: var(--green); background: rgba(46, 139, 87, .1); }
.tg.bad { color: var(--faint); background: var(--panel-3); }

/* 折线图 */
.mpc-chart { width: 100%; height: 190px; display: block; }
.cgrid { stroke: var(--line-soft); stroke-width: 1; }
.clabel { fill: var(--faint); font-size: 9px; }
.ctarget { stroke: var(--accent-d); stroke-width: 1; stroke-dasharray: 4 3; }
.cline { fill: none; stroke: var(--accent-d); stroke-width: 1.8; stroke-linejoin: round; }
.cdot { fill: var(--accent-d); }
.mpc-chart-x { display: flex; justify-content: space-between; font-size: 9px; color: var(--faint); padding: 0 4px; }

/* 说明 */
.mpc-notes { margin: 8px 0 0; padding-left: 16px; font-size: 10.5px; color: var(--muted); line-height: 1.6; }
.mpc-notes li + li { margin-top: 2px; }

/* ===== 决策日志 ===== */
.mpc-log-ops { margin-left: auto; display: flex; gap: 6px; flex: none; }
.mpc-mini {
  font-size: 10.5px; padding: 2px 8px; border-radius: 4px; cursor: pointer;
  background: var(--panel-3); color: var(--text); border: 1px solid var(--border);
}
.mpc-mini:hover:not(:disabled) { border-color: var(--accent-d); color: var(--accent-d); }
.mpc-mini:disabled { opacity: .45; cursor: default; }
.mpc-log-empty { font-size: 11px; line-height: 1.6; margin: 4px 0 0; }
.mpc-loglist { list-style: none; margin: 6px 0 0; padding: 0; max-height: 260px; overflow: auto; }
.lg-item {
  border-left: 2px solid var(--border); padding: 4px 0 6px 9px; margin-bottom: 7px;
}
.lg-item.plan { border-left-color: var(--accent-d); }
.lg-item.reject { border-left-color: var(--red); }
.lg-item.enable { border-left-color: var(--green); }
.lg-item.disable { border-left-color: var(--yellow); }
.lg-hd { display: flex; align-items: center; gap: 7px; font-size: 11px; }
.lg-ts { color: var(--faint); font-family: ui-monospace, "Cascadia Mono", Consolas, monospace; }
.lg-kind {
  font-size: 9.5px; padding: 0 4px; border-radius: 3px; flex: none;
  background: var(--accent-l); color: var(--accent-d);
}
.lg-item.reject .lg-kind { background: rgba(200, 60, 60, .14); color: var(--red); }
.lg-item.enable .lg-kind, .lg-item.disable .lg-kind { background: rgba(46, 139, 87, .12); color: var(--green); }
.lg-tt { color: var(--text); font-weight: 600; }
.lg-lines { list-style: none; margin: 3px 0 0; padding: 0; }
.lg-lines li {
  font-size: 10.5px; line-height: 1.55; color: var(--muted);
  font-family: ui-monospace, "Cascadia Mono", Consolas, monospace;
  white-space: pre-wrap; word-break: break-word;
}
</style>
