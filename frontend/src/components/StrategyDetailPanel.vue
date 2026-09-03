<template>
  <div class="strategy-detail">
    <template v-if="strategy">
      <!-- 内置预置策略：只读展示 -->
      <template v-if="strategy.source === 'preset'">
        <CollapseSection :title="t('策略名称')" tone="blue" :show-more="false">
        <div class="card"><div class="kv2"><span>{{ t('名称') }}</span><b>{{ strategy.name }} <span class="tag">{{ t('内置') }}</span></b></div></div>
        <div class="note-box" v-if="strategy.description">{{ strategy.description }}</div>
        </CollapseSection>
        <CollapseSection :title="t('数值调整')" tone="amber" :show-more="false">
        <div class="note">{{ t('该策略为系统内置，点击「策略仿真」进入仿真模式解析测试。') }}</div>
        <div class="actions">
          <button class="x" :disabled="store.busy" @click="runSim">{{ t('策略仿真') }}</button>
        </div>
        </CollapseSection>
      </template>

      <!-- AI 优化模型（序列预测 / 强化学习 / 遗传算法 / 粒子群 / 聚类工况识别）：随实时传感器数据采集，后台定时训练、模型逐渐变优 -->
      <template v-else-if="strategy.source === 'ai'">
        <CollapseSection :title="t('模型名称')" tone="blue" :show-more="false">
          <div class="card">
            <div class="kv2"><span>{{ t('名称') }}</span><b>{{ strategy.name }} <span class="tag">{{ modelTag }}</span></b></div>
            <div class="kv2"><span>{{ t('状态') }}</span><b><span class="badge" :class="badgeCls">{{ badgeTxt }}</span></b></div>
          </div>
          <!-- 参数优化集中面板：GA / PSO / RL 三种算法在同一属性面板内切换 -->
          <div v-if="optAlgoOn" class="opt-tabs">
            <button v-for="a in optAlgos" :key="a.id" class="opt-tab" :class="{ on: strategy.id === a.id }" @click="enterOpt(a.id)">{{ t(a.label) }}</button>
          </div>
          <div class="note-box" v-if="strategy.description">{{ strategy.description }}</div>
          <div class="note" v-if="st.ready && !st.iteration">{{ isClu ? t('模型已就绪：可「开始自动训练」或「训练一轮」启动工况聚类识别。') : t('模型已就绪：可「开始自动训练」或「训练一轮」启动迭代优化。') }}</div>
        </CollapseSection>

        <CollapseSection :title="t('训练概览')" tone="green" :show-more="false">
          <div v-if="st.ready" class="stat-row">
            <div class="stat"><b>{{ st.iteration || 0 }}</b><span>{{ t('迭代轮数') }}</span></div>
            <div class="stat"><b>{{ fmtSamples }}</b><span>{{ t('传感器样本') }}</span></div>
            <div class="stat"><b>{{ bestTxt }}</b><span v-if="!isClu">{{ t('最优强度') }} {{ objUnit }}</span><span v-else>{{ t('工况簇数') }}</span></div>
            <div class="stat"><b :class="impCls">{{ impTxt }}</b><span v-if="!isClu">{{ t('较初始提升') }}</span><span v-else>{{ t('类内紧凑度') }}</span></div>
          </div>
          <div v-else class="note">{{ notReadyTip }}</div>
          <div v-if="st.ready" class="actions">
            <button class="x" :disabled="store.busy || llmBlocked" @click="toggleTrain">{{ st.running ? t('暂停训练') : t('开始自动训练') }}</button>
            <button class="x" :disabled="store.busy || st.running || llmBlocked" @click="trainOnce">{{ t('训练一轮') }}</button>
          </div>
          <div v-if="st.ready" class="actions">
            <button class="x" :disabled="store.busy" @click="resetModel">{{ t('重置') }}</button>
            <button class="x main" :disabled="store.busy || !st.iteration || isClu" @click="applyModel">{{ isClu ? t('工况识别（不下发参数）') : t('应用最优参数') }}</button>
          </div>
          <div v-if="st.ready" class="tip-row">
            <span class="dot" :class="{ on: st.running }"></span>
            <span class="muted">{{ st.running ? t('后台定时训练进行中：随实时传感器数据每轮迭代') : t('已暂停：点击「开始自动训练」恢复后台定时迭代') }}</span>
          </div>
        </CollapseSection>

        <!-- 手动模式调优提醒：系统提醒引导手动应用优化参数（聚类为工况识别，无参数下发提醒） -->
        <div v-if="st.ready && !st.auto_control && st.reminder && !isClu" class="reminder">
          <div class="rem-txt">{{ t('训练取得新进展：最优强度降至') }} <b>{{ st.reminder.best_fitness != null ? fmtFitness(st.reminder.best_fitness).toFixed(1) : '—' }}</b> {{ objUnit }}（{{ t('较上版提升') }} {{ st.reminder.improvement_pct != null ? st.reminder.improvement_pct.toFixed(1) : '0' }}%）。{{ t('建议手动应用优化参数调优可调设备。') }}</div>
          <div class="rem-actions">
            <button class="x main" :disabled="store.busy" @click="applyModel">{{ t('应用最优参数') }}</button>
            <button class="x" :disabled="store.busy" @click="ackReminder">{{ t('知道了') }}</button>
          </div>
        </div>

        <CollapseSection :title="t('控制与训练设置')" tone="amber" :show-more="false">
          <div class="set-block">
            <div class="set-row">
              <span class="set-label">{{ t('自动化控制') }}</span>
              <label class="chk">
                <input type="checkbox" :checked="!!st.auto_control" :disabled="store.busy" @change="toggleAutoControl" />
              </label>
            </div>
            <div class="note" v-if="st.auto_control">{{ t('已开启自动化控制：训练获得更优模型时将自动把新版本参数下发到可调设备，无需人工干预。') }}</div>
            <div class="note" v-else>{{ t('未开启自动化控制：训练取得进展时通过系统提醒引导手动调优。') }}</div>
          </div>
          <div class="set-block">
            <div class="set-row">
              <span class="set-label">{{ t('自训练频率') }}</span>
              <select class="inp sel" v-model.number="intervalDraft" @change="saveSchedule" :disabled="store.busy">
                <option :value="5">{{ t('每 5 秒') }}</option>
                <option :value="10">{{ t('每 10 秒') }}</option>
                <option :value="30">{{ t('每 30 秒') }}</option>
                <option :value="60">{{ t('每 60 秒') }}</option>
                <option :value="120">{{ t('每 2 分钟') }}</option>
                <option :value="300">{{ t('每 5 分钟') }}</option>
              </select>
            </div>
            <div class="set-row">
              <span class="set-label">{{ t('训练时段') }}</span>
              <label class="chk"><input type="checkbox" v-model="windowOn" @change="saveSchedule" :disabled="store.busy" /> {{ t('仅限时段内自训练') }}</label>
            </div>
            <div class="set-row time-row" v-if="windowOn">
              <input type="time" v-model="winStart" class="inp time" @change="saveSchedule" :disabled="store.busy" />
              <span class="muted">{{ t('至') }}</span>
              <input type="time" v-model="winEnd" class="inp time" @change="saveSchedule" :disabled="store.busy" />
            </div>
            <div class="note" v-if="st.ready && st.running && !st.in_window">{{ t('当前处于训练时段之外，自动训练已挂起，进入时段后自动恢复。') }}</div>
          </div>
        </CollapseSection>

        <!-- 聚类工况识别：工况簇分布（替代适应度曲线） -->
        <CollapseSection v-if="isClu" :title="t('工况簇分布')" tone="amber" :show-more="false">
          <div v-if="clusters.length" class="clu-list">
            <div v-for="c in clusters" :key="c.id" class="clu-row">
              <div class="clu-head">
                <b>{{ c.name }}</b>
                <span class="muted">{{ c.size }} {{ t('个快照') }} · {{ t('代表负荷') }} {{ c.load != null ? c.load.toFixed(2) : '—' }}</span>
                <b>{{ c.pct }}%</b>
              </div>
              <div class="clu-bar"><div class="clu-fill" :style="{ width: c.pct + '%' }"></div></div>
            </div>
          </div>
          <div v-else class="note">{{ t('尚无工况聚类结果：开启自动训练或「训练一轮」后，基于实时传感器数据识别典型工况。') }}</div>
          <div v-if="clusters.length" class="tip-row">
            <span class="muted">{{ t('类内紧凑度') }} {{ compactTxt }}（{{ t('越小代表工况分界越清晰') }}）· {{ t('随实时数据滚动更新') }}</span>
          </div>
        </CollapseSection>

        <CollapseSection v-else :title="t('适应度曲线')" tone="amber" :show-more="false">
          <div v-if="curve.length > 1" class="chart">
            <svg :viewBox="`0 0 ${CW} ${CH}`" preserveAspectRatio="none" class="chart-svg">
              <line v-for="g in gridY" :key="'g' + g" :x1="0" :x2="CW" :y1="g" :y2="g" class="grid" />
              <polyline :points="pts('best')" class="line-best" />
              <polyline :points="pts('avg')" class="line-avg" />
            </svg>
            <div class="legend">
              <span class="lg best">{{ t('最优') }}</span>
              <span class="lg avg">{{ t('平均') }}</span>
              <span class="lg muted">{{ t('当前最优') }} {{ bestTxt }} {{ objUnit }}</span>
            </div>
          </div>
          <div v-else class="note">{{ t('尚无训练轨迹：开启自动训练或「训练一轮」后生成（最优强度随迭代递减）。') }}</div>
        </CollapseSection>

        <!-- 决策变量：策略模型（强化学习 / 遗传算法 / 粒子群）——参与寻优的工艺参数 -->
        <CollapseSection :title="t('决策变量')" v-if="strategy.id !== 'ai::seq' && !isClu" tone="teal" :show-more="false">
          <div class="note">{{ t('参与寻优的工艺参数（默认中间视图勾选设备对应的工艺参数，可手动增删；未选择的参数保持当前设定值，不参与寻优）。') }}</div>
          <div v-if="decisionList.length" class="dv-list">
            <div v-for="row in decisionList" :key="row.dkey" class="dv-tag">
              <span class="dv-main">
                <b>{{ row.label }}</b>
                <span class="muted">{{ row.unit_name }} · {{ t('当前') }} {{ row.value }}{{ row.unit }}</span>
              </span>
              <button class="dv-del" :disabled="store.busy" :title="t('移除此参数（不参与寻优）')" @click="removeDecision(row.dkey)">×</button>
            </div>
          </div>
          <div v-else class="note">{{ decisionRows.length ? t('未选择任何参数参与优化（全部参数保持当前设定值）') : t('当前流程暂无可优化参数（kind=optim）：请先在「流程编排」中为工序添加可调参数。') }}</div>
          <div v-if="decisionAddOptions.length" class="dv-add">
            <select class="inp sel" value="" @change="onDecisionAdd($event.target.value)" :disabled="store.busy">
              <option value="" disabled>{{ t('手动添加参数…') }}</option>
              <option v-for="c in decisionAddOptions" :key="c.dkey" :value="c.dkey">{{ c.label }}（{{ c.unit_name }}）</option>
            </select>
          </div>
        </CollapseSection>

        <!-- 优化目标：策略模型——选择优化的最小化指标 -->
        <CollapseSection :title="t('优化目标')" v-if="strategy.id !== 'ai::seq' && !isClu" tone="green" :show-more="false">
          <div class="set-block">
            <div class="set-row">
              <span class="set-label">{{ t('目标方向') }}</span>
              <label class="chk" :title="t('勾选后表示所选目标指标越低越好（算法朝最小化方向寻优）；取消勾选则视为越高越好（对目标取负参与寻优）')">
                <input type="checkbox" :checked="objNeg" :disabled="store.busy" @change="onObjNeg" />
                <span>{{ t('取负值（该指标越低越好）') }}</span>
              </label>
            </div>
            <div class="set-row">
              <span class="set-label">{{ t('目标指标') }}</span>
              <select class="inp sel" :value="objKey" @change="onObjectiveChange" :disabled="store.busy">
                <optgroup v-for="g in objGroups" :key="g.label" :label="t(g.label)">
                  <option v-for="o in g.items" :key="o.key" :value="o.key">{{ t(o.label) }}（{{ o.unit }}）</option>
                </optgroup>
              </select>
            </div>
            <div class="note">{{ t('优化算法将朝着所选指标的方向搜索最优参数组合：勾选「取负值」= 该指标越低越好；取消 = 该指标越高越好（如产量、设备利用率）。') }}</div>
          </div>
        </CollapseSection>

        <!-- 聚类工况识别：聚类算法选择 -->
        <CollapseSection :title="t('聚类算法')" v-if="isClu" tone="teal" :show-more="false">
          <div class="set-block">
            <div class="set-row">
              <span class="set-label">{{ t('聚类方法') }}</span>
              <select class="inp sel" :value="cluModel" @change="onCluMethod" :disabled="store.busy">
                <option v-for="m in cluModels" :key="m.id" :value="m.id">{{ t(m.label) }}</option>
              </select>
            </div>
            <div class="set-row">
              <span class="set-label">{{ t('分组簇数') }}</span>
              <select class="inp sel" :value="cluK" @change="onCluK" :disabled="store.busy">
                <option :value="0">{{ t('自动') }}</option>
                <option v-for="k in 5" :key="k" :value="k">{{ k }}</option>
              </select>
            </div>
            <div class="note">{{ t('聚类工况识别将按所选算法对最近 10 分钟工况快照自动划分典型运行工况（低/中/高负荷），只输出工况识别结果，不直接下发参数。') }}</div>
            <div class="note">{{ t('「分组簇数」用于工况数据分析视图的多设备聚类分组（0=自动选择最佳分组数），修改后数据视图自动重新分析。') }}</div>
          </div>
        </CollapseSection>

        <CollapseSection :title="t('预测模型')" v-if="strategy.id === 'ai::seq'" tone="teal" :show-more="false">
          <div class="set-block">
            <div class="set-row">
              <span class="set-label">{{ t('时间序列模型') }}</span>
              <select class="inp sel" :value="seqModel" @change="onSeqModel" :disabled="store.busy">
                <option v-for="m in seqModels" :key="m.id" :value="m.id">{{ t(m.label) }}</option>
              </select>
            </div>
            <div class="note" v-if="seqModel === 'llm'">{{ t('时间序列大模型暂不实现：请选择 LSTM / LightGBM / XGBoost 后训练。') }}</div>
            <div class="note" v-else>{{ t('序列预测算法将基于所选模型外推未来工况，并据此设定最佳策略 / 调节变量进行仿真分析。') }}</div>
          </div>
        </CollapseSection>

        <!-- 预测目标 / 影响变量：序列预测算法 -->
        <CollapseSection :title="t('预测目标')" v-if="strategy.id === 'ai::seq'" tone="teal" :show-more="false">
          <div class="set-block">
            <div class="set-row">
              <span class="set-label">{{ t('预测对象') }}</span>
              <select class="inp sel" :value="ftKey" @change="onForecastTarget" :disabled="store.busy">
                <option v-for="t in ftOptions" :key="t.id" :value="t.id">{{ t(t.label) }}<template v-if="t.unit">（{{ t.unit }}）</template></option>
              </select>
            </div>
            <div class="note">{{ t('预测对象只能选择一个：从当前流程设备中选取（默认中间视图第一个勾选设备），且不能与「影响变量」重复。') }}</div>
          </div>
        </CollapseSection>

        <CollapseSection :title="t('影响变量')" v-if="strategy.id === 'ai::seq'" tone="teal" :show-more="false">
          <div class="note">{{ t('选择参与预测的监测设备指标（默认中间视图勾选设备，可手动增删；不勾选任意项 = 全部设备参与预测；已选为预测对象的设备自动剔除）。') }}</div>
          <div v-if="impactRows.length" class="dv-list">
            <label v-for="row in impactRows" :key="row.id" class="dv-row chk">
              <input type="checkbox" :checked="impactSet[row.id]" :disabled="store.busy" @change="onImpactToggle(row.id, $event.target.checked)" />
              <span class="dv-main">
                <b>{{ row.label }}</b>
                <span class="muted">{{ row.unit_name }} · {{ row.unit || '—' }}</span>
              </span>
            </label>
          </div>
          <div v-else class="note">{{ t('暂无实时设备数据（MQTT 未上报）：序列预测将回退为全厂工况负荷。') }}</div>
        </CollapseSection>

        <!-- 聚类工况识别：聚类特征变量 -->
        <CollapseSection :title="t('聚类特征')" v-if="isClu" tone="teal" :show-more="false">
          <div class="note">{{ t('选择参与工况聚类的监测设备指标（默认中间视图勾选设备，可手动增删；不勾选任意项 = 全部设备参与聚类）。') }}</div>
          <div v-if="featureRows.length" class="dv-list">
            <label v-for="row in featureRows" :key="row.id" class="dv-row chk">
              <input type="checkbox" :checked="featureSet[row.id]" :disabled="store.busy" @change="onFeatureToggle(row.id, $event.target.checked)" />
              <span class="dv-main">
                <b>{{ row.label }}</b>
                <span class="muted">{{ row.unit_name }} · {{ row.unit || '—' }}</span>
              </span>
            </label>
          </div>
          <div v-else class="note">{{ t('暂无实时设备数据（MQTT 未上报）：聚类将回退为基于全部可用指标。') }}</div>
        </CollapseSection>

        <CollapseSection :title="t('算法超参数')" tone="teal" :show-more="false">
          <div v-for="(hp, key) in hpSchema" :key="key" class="hp-row">
            <span class="hp-label">{{ t(hp.label) }}</span>
            <input class="hp-slider" type="range" :min="hp.min" :max="hp.max" :step="hp.step" v-model.number="hpDraft[key]" />
            <span class="hp-val">{{ fmtHp(hpDraft[key]) }}</span>
          </div>
          <div class="actions"><button class="x" :disabled="store.busy || !st.ready" @click="saveHyper">{{ t('保存超参数') }}</button></div>
        </CollapseSection>

        <CollapseSection :title="t('最优参数建议')" v-if="!isClu" tone="blue" :show-more="false">
          <div class="note" v-if="recommended">{{ t('以下参数来自当前生效版本') }} <b>{{ recommended.version_id }}</b>（{{ t('迭代') }} {{ recommended.iteration }} {{ t('轮') }} · {{ t('最优') }} {{ recommended.best_fitness }} {{ objUnit }}）。</div>
          <div v-if="bestParams.length" class="bp-list">
            <div v-for="bp in bestParams" :key="bp.unit_id + ':' + bp.key" class="bp-row">
              <div class="bp-left">
                <b>{{ bp.label }}</b>
                <span class="muted">{{ bp.unit_label }} · {{ bp.unit }}</span>
              </div>
              <div class="bp-right">
                <span class="muted init">{{ bp.initial }}</span>
                <span class="arrow" :class="{ up: bp.delta > 0, down: bp.delta < 0 }">{{ bp.delta > 0 ? '▲' : bp.delta < 0 ? '▼' : '·' }}</span>
                <b>{{ bp.value }}</b>
              </div>
            </div>
          </div>
          <div v-else class="note">{{ t('暂无最优参数建议：训练迭代后生成。') }}</div>
          <div class="note" v-if="st.archived && st.archived.best_fitness != null">{{ t('上一轮模型：迭代') }} {{ st.archived.iteration }} {{ t('轮') }} · {{ t('最优') }} {{ fmtFitness(st.archived.best_fitness) }} {{ objUnit }}</div>
        </CollapseSection>

        <CollapseSection :title="t('模型版本')" v-if="!isClu" tone="green" :show-more="false">
          <div class="note">{{ t('仅当新模型的评估指标（吨钢碳强度）优于当前版本时才自动替换为新版本；历史版本全部保留，可随时切换。') }}</div>
          <div v-if="versions.length" class="ver-list">
            <div v-for="v in versions" :key="v.id" class="ver-row" :class="{ active: v.active }">
              <div class="ver-head">
                <b>{{ v.id }}</b>
                <span class="ver-badge" v-if="v.active">{{ t('当前版本') }}</span>
                <span class="ver-badge cand" v-else>{{ t('历史版本') }}</span>
              </div>
              <div class="ver-meta muted">{{ t('迭代') }} {{ v.iteration }} {{ t('轮') }} · {{ v.samples != null ? v.samples + t('样本') : '' }} · {{ fmtTime(v.created_at) }}</div>
              <div class="ver-meta">
                <span class="muted">{{ t('最优强度') }}</span> <b>{{ v.best_fitness != null ? fmtFitness(v.best_fitness).toFixed(1) : '—' }}</b> {{ objUnit }}
                <span class="imp" :class="v.improvement_pct > 0.01 ? 'good' : 'bad'">{{ v.improvement_pct != null ? (v.improvement_pct >= 0 ? '↓' : '↑') + ' ' + Math.abs(v.improvement_pct).toFixed(1) + '%' : '' }}</span>
              </div>
              <div class="actions">
                <button class="x" :disabled="store.busy || v.active" @click="switchVer(v.id)">{{ v.active ? t('使用中') : t('切换到此版本') }}</button>
              </div>
            </div>
          </div>
          <div v-else class="note">{{ t('暂无版本：训练取得提升后自动保存新版本，也可手动存档。') }}</div>
          <div class="actions">
            <button class="x" :disabled="store.busy || !st.iteration" @click="saveVersion">{{ t('保存当前最优为版本') }}</button>
          </div>
        </CollapseSection>

        <CollapseSection :title="t('训练日志')" tone="purple" :show-more="false">
          <div v-if="st.logs && st.logs.length" class="logs">
            <div v-for="(lg, i) in st.logs" :key="i" class="lg-line">{{ lg }}</div>
          </div>
          <div v-else class="note">{{ t('暂无日志。') }}</div>
        </CollapseSection>

        <CollapseSection :title="t('工作机制')" tone="gray" :show-more="false">
          <div class="note" v-if="isClu">
            {{ t('实时传感器数据持续采集 → 构造最近 10 分钟「工况快照」（特征设备归一化读数 + 全厂负荷因子）→') }}
            {{ t('按所选聚类算法（K-Means / DBSCAN / 层次聚类）自动划分典型运行工况簇 → 输出各工况占比与代表负荷。') }}
            {{ t('聚类结果随数据滚动更新，用于辅助制定分工况调节策略，不直接下发参数。') }}
          </div>
          <div class="note" v-else>
            {{ t('实时传感器数据持续采集 → 后台按自训练频率定时训练（每轮迭代）→ 模型参数逐步收敛。') }}
            {{ t('只有新模型的评估指标（吨钢碳强度）优于当前版本时才替换为新版本，历史版本均保留可切换。') }}
            {{ t('开启「自动化控制」时，模型变优后自动把参数下发到可调设备；未开启时通过系统提醒手动调优。') }}
          </div>
        </CollapseSection>
      </template>

      <!-- 数据拟合（多项式 / 指数 / 对数 / 幂函数）：对历史工况序列做曲线拟合建模，输出方程与 R²，不下发参数 -->
      <template v-else-if="strategy.source === 'ai-fit'">
        <CollapseSection :title="t('模型名称')" tone="blue" :show-more="false">
          <div class="card">
            <div class="kv2"><span>{{ t('名称') }}</span><b>{{ strategy.name }} <span class="tag">{{ modelTag }}</span></b></div>
            <div class="kv2"><span>{{ t('状态') }}</span><b><span class="badge" :class="badgeCls">{{ badgeTxt }}</span></b></div>
          </div>
          <div class="note-box" v-if="strategy.description">{{ strategy.description }}</div>
          <div class="note" v-if="st.ready && !st.iteration">{{ t('模型已就绪：可「开始自动训练」或「训练一轮」启动曲线拟合。') }}</div>
        </CollapseSection>

        <CollapseSection :title="t('训练概览')" tone="green" :show-more="false">
          <div v-if="st.ready" class="stat-row">
            <div class="stat"><b>{{ st.iteration || 0 }}</b><span>{{ t('迭代轮数') }}</span></div>
            <div class="stat"><b>{{ fmtSamples }}</b><span>{{ t('传感器样本') }}</span></div>
            <div class="stat"><b>{{ fitR2Txt }}</b><span>{{ t('拟合优度 R²') }}</span></div>
            <div class="stat"><b class="fit-stat">{{ fitMethodLabel }}</b><span>{{ t('拟合方法') }}</span></div>
          </div>
          <div v-else class="note">{{ notReadyTip }}</div>
          <div v-if="st.ready" class="actions">
            <button class="x" :disabled="store.busy || llmBlocked" @click="toggleTrain">{{ st.running ? t('暂停训练') : t('开始自动训练') }}</button>
            <button class="x" :disabled="store.busy || st.running || llmBlocked" @click="trainOnce">{{ t('训练一轮') }}</button>
          </div>
          <div v-if="st.ready" class="actions">
            <button class="x" :disabled="store.busy" @click="resetModel">{{ t('重置') }}</button>
            <button class="x" :disabled="store.busy || !st.iteration" @click="refreshFit">{{ t('刷新拟合') }}</button>
          </div>
          <div v-if="st.ready" class="tip-row">
            <span class="dot" :class="{ on: st.running }"></span>
            <span class="muted">{{ st.running ? t('后台定时拟合进行中：随实时传感器数据每轮迭代') : t('已暂停：点击「开始自动训练」恢复后台定时迭代') }}</span>
          </div>
        </CollapseSection>

        <!-- 拟合设置：拟合对象 / 拟合方法（拟合对象与拟合变量互斥） -->
        <CollapseSection :title="t('拟合设置')" tone="teal" :show-more="false">
          <div class="set-block">
            <div class="set-row">
              <span class="set-label">{{ t('拟合对象') }}</span>
              <select class="inp sel" :value="fitTarget" @change="onFitTarget" :disabled="store.busy">
                <option v-for="t in fitTargets" :key="t.id" :value="t.id">{{ t(t.label) }}<template v-if="t.unit">（{{ t.unit }}）</template></option>
              </select>
            </div>
            <div class="set-row">
              <span class="set-label">{{ t('拟合方法') }}</span>
              <select class="inp sel" :value="fitMethod" @change="onFitMethod" :disabled="store.busy">
                <option v-for="m in fitMethods" :key="m.id" :value="m.id">{{ t(m.label) }}</option>
              </select>
            </div>
            <div class="note" v-if="fitMethodInfo">{{ fitMethodInfo }}</div>
          </div>
          <div class="note">{{ t('拟合对象只能选择一个：从当前流程设备中选取（默认中间视图第一个勾选设备），且不能与「拟合变量」重复。') }}</div>
        </CollapseSection>

        <!-- 拟合变量：参与拟合的设备序列（默认中间视图勾选，可手动增删；空 = 全部设备） -->
        <CollapseSection :title="t('拟合变量')" tone="teal" :show-more="false">
          <div class="note">{{ t('参与拟合的监测设备序列（默认中间视图勾选设备，可手动增删；未指定任意项 = 全部设备参与拟合；已选为拟合对象的设备自动剔除）。') }}</div>
          <div v-if="fitVarList.length" class="dv-list">
            <div v-for="row in fitVarList" :key="row.id" class="dv-tag">
              <span class="dv-main">
                <b>{{ row.label }}</b>
                <span class="muted">{{ row.unit_name }} · {{ row.unit || '—' }}</span>
              </span>
              <button class="dv-del" :disabled="store.busy" :title="t('移除此变量（不参与拟合）')" @click="removeFitVar(row.id)">×</button>
            </div>
          </div>
          <div v-else class="note">{{ t('未指定任何设备：全部设备参与拟合。') }}</div>
          <div v-if="fitVarAddOptions.length" class="dv-add">
            <select class="inp sel" value="" @change="onFitVarAdd($event.target.value)" :disabled="store.busy">
              <option value="" disabled>{{ t('手动添加设备…') }}</option>
              <option v-for="c in fitVarAddOptions" :key="c.id" :value="c.id">{{ c.label }}<template v-if="c.unit">（{{ c.unit }}）</template></option>
            </select>
          </div>
        </CollapseSection>

        <!-- 拟合结果：方程 + R² + 拟合曲线（实际值散点 + 拟合线，含外推） -->
        <CollapseSection :title="t('拟合结果')" tone="blue" :show-more="false">
          <div v-if="fitResult && fitResult.equation" class="fit-eq">
            <div class="fit-eq-main">{{ fitResult.equation }}</div>
            <div class="muted">{{ t('拟合方法') }} {{ fitResult.method_label || '—' }} · {{ t('样本') }} {{ fitResult.n || 0 }} {{ t('个') }} · R² = {{ fitResult.r2 != null ? fitResult.r2.toFixed(4) : '—' }}</div>
          </div>
          <div v-else class="note">{{ t('尚无拟合结果：开启自动训练或「训练一轮」后，基于最近样本窗口的实时数据拟合曲线。') }}</div>
          <div v-if="fitCurve.length > 1" class="chart">
            <svg :viewBox="`0 0 ${CW} ${CH}`" preserveAspectRatio="none" class="chart-svg">
              <line v-for="g in gridY" :key="'fg' + g" :x1="0" :x2="CW" :y1="g" :y2="g" class="grid" />
              <polyline :points="fitLinePts" class="line-best" />
              <circle v-for="(c, i) in fitDots" :key="'fd' + i" :cx="c.x" :cy="c.y" r="2.2" class="fit-dot" />
            </svg>
            <div class="legend">
              <span class="lg dot-blue">{{ t('实际值') }}</span>
              <span class="lg best">{{ t('拟合曲线') }}</span>
              <span class="lg muted">R² = {{ fitR2Txt }} · {{ t('曲线右端为外推') }}</span>
            </div>
          </div>
        </CollapseSection>

        <CollapseSection :title="t('算法超参数')" tone="teal" :show-more="false">
          <div v-for="(hp, key) in hpSchema" :key="key" class="hp-row">
            <span class="hp-label">{{ t(hp.label) }}</span>
            <input class="hp-slider" type="range" :min="hp.min" :max="hp.max" :step="hp.step" v-model.number="hpDraft[key]" />
            <span class="hp-val">{{ fmtHp(hpDraft[key]) }}</span>
          </div>
          <div class="actions"><button class="x" :disabled="store.busy || !st.ready" @click="saveHyper">{{ t('保存超参数') }}</button></div>
        </CollapseSection>

        <CollapseSection :title="t('训练日志')" tone="purple" :show-more="false">
          <div v-if="st.logs && st.logs.length" class="logs">
            <div v-for="(lg, i) in st.logs" :key="i" class="lg-line">{{ lg }}</div>
          </div>
          <div v-else class="note">{{ t('暂无日志。') }}</div>
        </CollapseSection>

        <CollapseSection :title="t('工作机制')" tone="gray" :show-more="false">
          <div class="note">
            {{ t('实时传感器数据持续采集 → 取最近样本窗口的目标序列（全厂工况负荷或指定设备指标）→') }}
            {{ t('按所选方法（多项式 / 指数 / 对数 / 幂函数）做最小二乘曲线拟合 → 输出拟合方程与 R² 拟合优度，') }}
            {{ t('并绘制「实际值 + 拟合曲线（含外推）」对比图。拟合仅用于建模分析，不直接下发参数。') }}
          </div>
        </CollapseSection>
      </template>

      <!-- 工艺策略（某工艺对应的绿色策略）：只读展示 + 启用/停用 + 查看工艺 -->
      <template v-else-if="strategy.source === 'green'">
        <CollapseSection :title="t('策略名称')" tone="blue" :show-more="false">
        <div class="card"><div class="kv2"><span>{{ t('名称') }}</span><b>{{ strategy.name }} <span class="tag">{{ t('工艺策略') }}</span></b></div></div>
        <div class="card">
          <div class="kv2"><span>{{ t('所属工艺') }}</span><b>{{ strategy.processLabel }}</b></div>
        </div>
        <div class="note-box" v-if="strategy.description">{{ strategy.description }}</div>
        <div class="card" v-if="strategy.saving || strategy.carbon">
          <div class="kv2" v-if="strategy.saving"><span>{{ t('节能效果') }}</span><b>{{ strategy.saving }}</b></div>
          <div class="kv2" v-if="strategy.carbon"><span>{{ t('减碳效果') }}</span><b>{{ strategy.carbon }} kgCO₂/t</b></div>
        </div>
        <div class="card" v-if="strategy.tags && strategy.tags.length">
          <div class="tag-row">
            <span v-for="t in strategy.tags" :key="t" class="tag">{{ t }}</span>
          </div>
        </div>
        </CollapseSection>
        <CollapseSection :title="t('启用状态')" tone="green" :show-more="false">
        <div class="card toggle-card">
          <span class="muted">{{ strategy.enabled ? t('该策略已在对应工艺中启用') : t('该策略未启用') }}</span>
          <button class="x" :class="{ on: strategy.enabled }" @click="toggleGreen">
            {{ strategy.enabled ? t('已启用') : t('启用策略') }}
          </button>
        </div>
        <button class="btn-mini" @click="goProcess">{{ t('查看工艺属性') }}</button>
        </CollapseSection>
      </template>

      <!-- 自定义策略：可编辑 -->
      <template v-else>
        <CollapseSection :title="t('策略名称')" tone="blue" :show-more="false">
        <div class="card"><input v-model="nameDraft" class="inp" @change="markDirty" /></div>
        </CollapseSection>
        <CollapseSection :title="t('来源')" tone="teal" :show-more="false">
        <div class="card">
          <span class="tag">{{ strategy.applied ? t('已应用') : t('自定义') }}</span>
          <span class="muted src-tip">{{ t('仿真模式下保存') }}</span>
        </div>
        </CollapseSection>
        <CollapseSection v-if="strategy.description" :title="t('描述')" tone="teal" :show-more="false">
        <div class="card">
          <textarea v-model="descDraft" class="inp" rows="2" @change="markDirty"></textarea>
        </div>
        </CollapseSection>

        <!-- 数值调整（可编辑） -->
        <CollapseSection :title="t('数值调整')" tone="amber" :show-more="false">
        <div v-if="opsDraft.length" class="ops">
          <div v-for="(op, i) in opsDraft" :key="i" class="op-row">
            <div class="op-head">
              <span class="op-note">{{ opNote(op) }}</span>
              <span class="op-kind">{{ op.action === 'set_param' ? t('参数') : op.action === 'apply_tech' ? t('技术') : t('操作') }}</span>
            </div>
            <div v-if="op.action === 'set_param'" class="op-edit">
              <span class="op-label">{{ op.target }} {{ opParamLabel(op) }}</span>
              <input v-model.number="op.value" type="number" class="inp num" @change="markDirty" />
              <span class="op-unit">{{ opUnit(op) }}</span>
            </div>
            <div v-else class="op-static muted">{{ opNote(op) }}</div>
          </div>
        </div>
        <div v-else class="note">{{ t('该策略暂无数值调整项。') }}</div>

        <div class="actions">
          <button class="x" :disabled="store.busy" @click="save">{{ t('保存修改') }}</button>
          <button class="x" :disabled="store.busy" @click="runSim">{{ t('策略仿真') }}</button>
        </div>
        </CollapseSection>
      </template>
    </template>
    <div v-else class="empty">{{ t('未选择策略，请先在左侧「策略」中选择。') }}</div>
  </div>
</template>

<script setup>
import { computed, ref, watch, onMounted } from 'vue'
import { useSimStore, EDITABLE_PARAMS, AI_MODEL_MAP } from '../stores/sim'
import CollapseSection from './CollapseSection.vue'
import { t } from '../i18n'

const store = useSimStore()

const strategy = computed(() => store.selectedStrategy)
const nameDraft = ref('')
const descDraft = ref('')
const opsDraft = ref([])
let hpInited = false   // AI 算法超参数草稿是否已初始化（避免轮询覆盖用户编辑）
let settingsInited = false  // 控制与训练设置草稿是否已初始化
const intervalDraft = ref(30)
const windowOn = ref(false)
const winStart = ref('08:00')
const winEnd = ref('18:00')

watch(strategy, (s) => {
  nameDraft.value = s ? s.name || '' : ''
  descDraft.value = s ? s.description || '' : ''
  opsDraft.value = s && s.ops ? JSON.parse(JSON.stringify(s.ops)) : []
  hpInited = false   // 切换条目后重新初始化 AI 算法超参数草稿
  settingsInited = false
}, { immediate: true })

// ==================== AI 优化模型（GA / PSO / RL 在线训练面板） ====================
// 后端状态（store.optimizers[id]）由全局轮询每数秒刷新，展示迭代/曲线/最优参数随实时数据逐渐变优。
const st = computed(() => store.optimizers[strategy.value.id] || {})
const modelTag = computed(() => (AI_MODEL_MAP[strategy.value.id] || {}).tag || 'AI')
const badgeCls = computed(() => (st.value.running ? 'run' : st.value.iteration > 0 ? 'pause' : 'idle'))
const badgeTxt = computed(() => (st.value.running ? t('训练中') : st.value.iteration > 0 ? t('已暂停') : t('待训练')))
const notReadyTip = computed(() => t('训练上下文未同步：进入面板后将随流程模型自动初始化'))
// 序列预测算法：可选的时序模型（后端 state.models 下发，缺省用内置默认）
const seqModels = computed(() => {
  const ms = st.value.models
  return Array.isArray(ms) && ms.length
    ? ms
    : [
        { id: 'lstm', label: 'LSTM 长短期记忆网络' },
        { id: 'lightgbm', label: 'LightGBM 梯度提升' },
        { id: 'xgboost', label: 'XGBoost 梯度提升' },
        { id: 'llm', label: '时间序列大模型（暂不实现）' },
      ]
})
const seqModel = computed(() => st.value.model || 'lstm')
const llmBlocked = computed(() => seqModel.value === 'llm')
function onSeqModel(e) {
  store.setOptimizerSettings(strategy.value.id, { model: e.target.value })
}

// 聚类工况识别：当前模型是否为聚类分析（CLU）
const isClu = computed(() => strategy.value.id === 'ai::clu')
// 聚类算法可选（后端 state.methods 下发，缺省用内置默认）
const cluModels = computed(() => {
  const ms = st.value.methods
  return Array.isArray(ms) && ms.length
    ? ms
    : [
        { id: 'kmeans', label: 'K-Means 均值聚类' },
        { id: 'dbscan', label: 'DBSCAN 密度聚类' },
        { id: 'hierarchical', label: '层次聚类' },
      ]
})
const cluModel = computed(() => st.value.method || 'kmeans')
function onCluMethod(e) {
  store.setOptimizerSettings(strategy.value.id, { method: e.target.value })
}
// 工况数据分析视图的多设备分组簇数（0=自动），由右侧属性面板统一配置
const cluK = computed(() => store.cluK || 0)
function onCluK(e) {
  store.cluK = Number(e.target.value)
}

// ---- 参数优化集中面板：GA / PSO / RL 三种算法在同一属性面板内切换（工具栏「参数优化」入口） ----
const optAlgos = [
  { id: 'ai::ga', label: '遗传算法' },
  { id: 'ai::pso', label: '粒子群' },
  { id: 'ai::rl', label: '强化学习' },
]
const optAlgoOn = computed(() => optAlgos.some((a) => a.id === strategy.value.id))
function enterOpt(id) {
  if (store.busy || id === strategy.value.id) return
  store.selectStrategy(id)
  store.showToast(`${t('已切换到参数优化算法')}：${optAlgos.find((a) => a.id === id).label}`, 'success')
}

// ---- 数据拟合（FIT）：拟合对象 / 方法 / 结果 / 曲线 ----
const fitMethods = computed(() => {
  const ms = st.value.methods
  return Array.isArray(ms) && ms.length ? ms : []
})
const fitMethod = computed(() => st.value.method || 'poly')
const fitTargets = computed(() => {
  const back = st.value.targets || [{ id: 'load', label: '全厂工况负荷', unit: '负荷系数' }]
  return mergeCandidates(back, flowDevices.value)
})
const fitTarget = computed(() => st.value.target || 'load')
const fitTargetTouched = ref(false)  // 用户手动调整过拟合对象后不再跟随中间视图
// 拟合变量候选：流程设备 + 后端候选，剔除拟合对象（与拟合对象互斥）
const fitVarRows = computed(() => {
  const back = st.value.fit_var_candidates || st.value.targets || []
  return mergeCandidates(back, flowDevices.value).filter(c => c.id !== fitTarget.value)
})
// 已选拟合变量列表（空 = 全部设备参与拟合）
const fitVarList = computed(() => {
  const fv = st.value.fit_vars
  if (!Array.isArray(fv) || !fv.length) return []
  const set = new Set(fv)
  return fitVarRows.value.filter(r => set.has(r.id))
})
// 可手动添加的拟合变量候选（未选中的设备）
const fitVarAddOptions = computed(() => fitVarRows.value.filter(r => !fitVarList.value.some(x => x.id === r.id)))
const fitVarTouched = ref(false)  // 用户手动调整过拟合变量后不再跟随中间视图
function removeFitVar(id) {
  fitVarTouched.value = true
  const list = (Array.isArray(st.value.fit_vars) ? st.value.fit_vars : []).filter(x => x !== id)
  store.setOptimizerSettings(strategy.value.id, { fit_vars: list })
}
function addFitVar(id) {
  fitVarTouched.value = true
  const cur = Array.isArray(st.value.fit_vars) ? [...st.value.fit_vars] : []
  if (!cur.includes(id)) cur.push(id)
  store.setOptimizerSettings(strategy.value.id, { fit_vars: cur })
}
function onFitVarAdd(v) {
  if (v) addFitVar(v)
}
// 中间视图当前勾选的设备 id（各算法输入的默认值来源）
const flowSelIds = computed(() => (Array.isArray(store.dvSelIds) ? store.dvSelIds : []))
// 拟合对象默认 = 中间视图第一个勾选设备；拟合变量默认 = 中间视图勾选设备（排除拟合对象，二者互斥）
watch(() => [flowSelIds.value, strategy.value.id, st.value.ready], ([ids]) => {
  if (strategy.value.id !== 'ai::fit' || !st.value.ready || !ids.length) return
  const patch = {}
  let fk = fitTarget.value
  if (!fitTargetTouched.value) {
    const first = ids[0]
    if (first && fitTargets.value.some(t => t.id === first) && (st.value.target || 'load') !== first) {
      patch.target = first
      fk = first
    }
  }
  if (!fitVarTouched.value) {
    const list = ids.filter(x => x !== fk)
    if (list.length) patch.fit_vars = list
  }
  if (Object.keys(patch).length) store.setOptimizerSettings('ai::fit', patch)
}, { immediate: true })
const fitResult = computed(() => st.value.fit || null)
const fitCurve = computed(() => st.value.curve || [])
const fitR2Txt = computed(() => (st.value.best_r2 != null ? Number(st.value.best_r2).toFixed(3) : '—'))
const fitMethodLabel = computed(() => {
  const m = fitMethods.value.find((x) => x.id === fitMethod.value)
  return m ? t(m.label) : '—'
})
const fitMethodInfo = computed(() => {
  const m = fitMethods.value.find((x) => x.id === fitMethod.value)
  return m ? m.desc : ''
})
function onFitMethod(e) {
  if (store.busy) return
  store.setOptimizerSettings(strategy.value.id, { method: e.target.value })
}
function onFitTarget(e) {
  if (store.busy) return
  fitTargetTouched.value = true
  const t = e.target.value
  const patch = { target: t }
  // 互斥：拟合对象不能同时作为拟合变量，从拟合变量中移除
  const fv = st.value.fit_vars
  if (Array.isArray(fv) && fv.includes(t)) patch.fit_vars = fv.filter(x => x !== t)
  store.setOptimizerSettings(strategy.value.id, patch)
}
function refreshFit() {
  store.refreshOptimizers()
  store.showToast(t('已刷新拟合结果'), 'info')
}
// 拟合曲线 SVG：散点 = 实际值，折线 = 拟合值（含外推）
const fitDots = computed(() => {
  const cs = fitCurve.value
  if (cs.length < 2) return []
  const ys = cs.filter((c) => c.y != null).map((c) => c.y)
  if (ys.length < 2) return []
  const min = Math.min(...ys)
  const max = Math.max(...ys)
  const span = max - min || 1
  const pad = 8
  const lastX = cs[cs.length - 1].x || 1
  return cs.filter((c) => c.y != null).map((c) => {
    const x = (c.x / lastX) * CW
    const y = CH - pad - ((c.y - min) / span) * (CH - 2 * pad)
    return { x: x.toFixed(1), y: y.toFixed(1) }
  })
})
const fitLinePts = computed(() => {
  const cs = fitCurve.value
  if (cs.length < 2) return ''
  const ys = cs.map((c) => (c.y != null ? c.y : c.yfit))
  const min = Math.min(...ys)
  const max = Math.max(...ys)
  const span = max - min || 1
  const pad = 8
  const lastX = cs[cs.length - 1].x || 1
  return cs
    .map((c) => {
      const v = c.y != null ? c.y : c.yfit
      const x = (c.x / lastX) * CW
      const y = CH - pad - ((v - min) / span) * (CH - 2 * pad)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
})

// ============ 中间视图联动：当前流程设备 ============
// 工况数据分析中间视图拖入的数据源 = 当前流程设备列表（各算法手动添加时的候选来源）
const flowDevices = computed(() => {
  const srcs = store.dvSources || []
  return srcs.map(s => ({
    id: s.id,
    label: s.label || s.id,
    unit: s.unit || '',
    unit_name: s.unitName || s.unit || '',
    unit_type: s.unitType || '',
  }))
})
// 合并候选：流程设备在前（带当前流程信息），后端 DEVICE_META 补全，按 id 去重
function mergeCandidates(back, flows) {
  const seen = {}
  const out = []
  for (const c of [...flows, ...back]) {
    if (!c || !c.id || seen[c.id]) continue
    seen[c.id] = 1
    out.push(c)
  }
  return out
}

// ---- 决策变量（策略模型：RL / GA / PSO） ----
const decisionRows = computed(() => st.value.space || [])
// 已选参与优化的参数列表（active=true）
const decisionList = computed(() => decisionRows.value.filter(r => !!r.active))
// 可手动添加的候选（当前未参与优化的参数）
const decisionAddOptions = computed(() => decisionRows.value.filter(r => !r.active))
const decisionTouched = ref(false)  // 用户手动调整过决策变量后不再跟随中间视图
// 决策变量默认 = 中间视图勾选设备对应的工艺参数（按设备所属工序 unitId/unitName 匹配）
const optDefaultUnits = computed(() => {
  const ids = flowSelIds.value
  const srcs = store.dvSources || []
  const set = new Set()
  for (const s of srcs) {
    if (ids.includes(s.id)) {
      if (s.unitId) set.add(String(s.unitId))
      else if (s.unitName) set.add(String(s.unitName))
    }
  }
  return set
})
watch(() => [optDefaultUnits.value.size, strategy.value.id, st.value.ready], () => {
  if (decisionTouched.value) return
  if (!['ai::ga', 'ai::pso', 'ai::rl'].includes(strategy.value.id) || !st.value.ready) return
  const rows = st.value.space || []
  const list = rows
    .filter(r => optDefaultUnits.value.has(String(r.unit_id)) || optDefaultUnits.value.has(String(r.unit_name)))
    .map(r => r.dkey)
  if (list.length) store.setOptimizerSettings(strategy.value.id, { decisions: list })
}, { immediate: true })
function removeDecision(dkey) {
  decisionTouched.value = true
  const list = decisionRows.value.filter(r => r.dkey !== dkey && r.active).map(r => r.dkey)
  store.setOptimizerSettings(strategy.value.id, { decisions: list })
}
function addDecision(dkey) {
  decisionTouched.value = true
  const list = decisionRows.value.filter(r => r.dkey === dkey || r.active).map(r => r.dkey)
  store.setOptimizerSettings(strategy.value.id, { decisions: list })
}
function onDecisionAdd(v) {
  if (v) addDecision(v)
}

// ---- 优化目标（策略模型：RL / GA / PSO） ----
const objOptions = computed(() => st.value.objectives || [{ key: 'intensity', label: '吨钢碳强度', unit: 'kgCO₂/t' }])
// 按 group 分组（全流程指标 / 工艺实时指标），每项为 { label, items: [...] }
const objGroups = computed(() => {
  const groups = []
  const map = {}
  for (const o of objOptions.value) {
    const g = o.group || '优化目标'
    if (!map[g]) { map[g] = []; groups.push({ label: g, items: map[g] }) }
    map[g].push(o)
  }
  return groups
})
const objKey = computed(() => st.value.objective || 'intensity')
const objUnit = computed(() => st.value.objective_unit || 'kgCO₂/t')
// 目标方向：勾选「取负值」= 该指标越低越好（算法朝最小化寻优）；取消 = 该指标越高越好
const objNeg = computed(() => st.value.objective_neg !== false)
function onObjectiveChange(e) {
  store.setOptimizerSettings(strategy.value.id, { objective: e.target.value })
}
function onObjNeg(e) {
  store.setOptimizerSettings(strategy.value.id, { objective_neg: e.target.checked })
}

// ---- 预测目标 / 影响变量（序列预测算法） ----
// 预测对象候选：当前流程设备优先，合并后端 forecast_targets（全厂负荷 + 全部监测设备）
const ftOptions = computed(() => {
  const back = st.value.forecast_targets ||
    [{ id: 'load', label: '全厂工况负荷', unit: '负荷系数', unit_name: '', unit_type: '' }]
  return mergeCandidates(back, flowDevices.value)
})
const ftKey = computed(() => st.value.forecast_target || 'load')
const ftTouched = ref(false)   // 用户手动调整过预测对象后不再跟随中间视图
function onForecastTarget(e) {
  ftTouched.value = true
  store.setOptimizerSettings(strategy.value.id, { forecast_target: e.target.value })
}
// 影响变量候选：流程设备 + 后端候选，剔除预测对象（二者互斥）
const impactRows = computed(() => {
  const back = st.value.impact_candidates || []
  const fk = ftKey.value
  return mergeCandidates(back, flowDevices.value).filter(c => c.id !== fk)
})
// 已选影响变量列表（空 = 全部设备参与预测）
const impactList = computed(() => {
  const iv = st.value.impact_vars
  if (!Array.isArray(iv) || !iv.length) return []
  const set = new Set(iv)
  return impactRows.value.filter(r => set.has(r.id))
})
// 可手动添加的影响变量候选（未选中的设备）
const impactAddOptions = computed(() => impactRows.value.filter(r => !impactList.value.some(x => x.id === r.id)))
const impactTouched = ref(false)  // 用户手动调整过影响变量后不再跟随中间视图
function removeImpact(id) {
  impactTouched.value = true
  const list = (Array.isArray(st.value.impact_vars) ? st.value.impact_vars : []).filter(x => x !== id)
  store.setOptimizerSettings(strategy.value.id, { impact_vars: list })
}
function addImpact(id) {
  impactTouched.value = true
  const cur = Array.isArray(st.value.impact_vars) ? [...st.value.impact_vars] : []
  if (!cur.includes(id)) cur.push(id)
  store.setOptimizerSettings(strategy.value.id, { impact_vars: cur })
}
function onImpactAdd(v) {
  if (v) addImpact(v)
}
// 默认输入：预测对象 = 中间视图第一个勾选设备；影响变量 = 中间视图勾选设备（排除预测对象）
watch(() => [flowSelIds.value, strategy.value.id, st.value.ready], ([ids]) => {
  if (strategy.value.id !== 'ai::seq' || !st.value.ready || !ids.length) return
  if (!ftTouched.value) {
    const first = ids[0]
    if (first && ftOptions.value.some(t => t.id === first) && (st.value.forecast_target || 'load') !== first) {
      store.setOptimizerSettings('ai::seq', { forecast_target: first })
    }
  }
  if (!impactTouched.value) {
    const fk = ftKey.value
    const list = ids.filter(x => x !== fk)
    if (list.length) store.setOptimizerSettings('ai::seq', { impact_vars: list })
  }
}, { immediate: true })

// ---- 聚类特征变量（聚类工况识别） ----
const featureRows = computed(() => mergeCandidates(st.value.feature_candidates || [], flowDevices.value))
const featureSet = computed(() => {
  const m = {}
  const fv = st.value.feature_vars
  const all = !Array.isArray(fv) || !fv.length
  for (const r of featureRows.value) m[r.id] = all || fv.includes(r.id)
  return m
})
const featureTouched = ref(false)  // 用户手动调整过聚类特征后不再跟随中间视图
function onFeatureToggle(id, checked) {
  featureTouched.value = true
  const list = featureRows.value.map(r => r.id).filter(rid => (rid !== id ? featureSet.value[rid] : checked))
  const payload = list.length === featureRows.value.length ? [] : list
  store.setOptimizerSettings(strategy.value.id, { feature_vars: payload })
}
// 聚类特征默认 = 中间视图勾选设备
watch(() => [flowSelIds.value, strategy.value.id, st.value.ready], ([ids]) => {
  if (strategy.value.id !== 'ai::clu' || !st.value.ready || featureTouched.value || !ids.length) return
  store.setOptimizerSettings('ai::clu', { feature_vars: ids })
}, { immediate: true })

// ---- 工况簇分布（聚类工况识别） ----
const clusters = computed(() => st.value.clusters || [])
const compactTxt = computed(() => (st.value.compactness != null ? Number(st.value.compactness).toFixed(3) : '—'))

const fmtSamples = computed(() => {
  const s = st.value.samples || 0
  return s >= 10000 ? (s / 10000).toFixed(1) + ' 万' : String(s)
})
// fitness（越小越好，方向已编码在符号中）→ 用户可读的目标值：取负方向时取反还原真实值
function fmtFitness(x) {
  if (x == null) return null
  const neg = st.value.objective_neg !== false
  return (neg ? x : -x)
}
const bestTxt = computed(() => {
  if (isClu.value) return clusters.value.length ? String(clusters.value.length) : '—'
  const f = fmtFitness(st.value.best_fitness)
  return f != null ? f.toFixed(1) : '—'
})
const impTxt = computed(() => {
  if (isClu.value) return compactTxt.value
  const p = st.value.improvement_pct
  if (p == null) return '—'
  return p >= 0 ? '↓ ' + Math.abs(p).toFixed(1) + '%' : '↑ ' + Math.abs(p).toFixed(1) + '%'
})
const impCls = computed(() => {
  if (isClu.value) return ''
  const p = st.value.improvement_pct
  if (p == null) return ''
  return p > 0.01 ? 'good' : p < -0.01 ? 'bad' : ''
})
// 当前生效版本的参数建议（推荐下发）；无版本时回退实时最优参数
const recommended = computed(() => st.value.recommended || null)
const bestParams = computed(() => {
  if (recommended.value && recommended.value.params && recommended.value.params.length) return recommended.value.params
  return st.value.best_params || []
})
// 模型版本列表：新→旧
const versions = computed(() => {
  const vs = st.value.versions || []
  return vs.slice().reverse()
})

// 适应度曲线（SVG 折线，最优/平均）
const CW = 320
const CH = 100
const curve = computed(() => st.value.history || [])
const gridY = computed(() => [CH / 4, CH / 2, (CH * 3) / 4])
function pts(key) {
  const c = curve.value
  if (c.length < 2) return ''
  let min = Infinity
  let max = -Infinity
  for (const p of c) {
    min = Math.min(min, p.best, p.avg)
    max = Math.max(max, p.best, p.avg)
  }
  const span = max - min || 1
  const pad = 8
  return c
    .map((p, i) => {
      const x = (i / (c.length - 1)) * CW
      const y = CH - pad - ((p[key] - min) / span) * (CH - 2 * pad)
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
}

// 算法超参数显示（聚类按算法过滤不适用的超参：DBSCAN 无 K，K-Means/层次聚类无 ε/最小样本数）
const hpSchema = computed(() => {
  const schema = st.value.hyper_schema || {}
  if (!isClu.value) return schema
  const out = {}
  const dbscan = cluModel.value === 'dbscan'
  for (const [key, hp] of Object.entries(schema)) {
    if (dbscan && key === 'k') continue
    if (!dbscan && (key === 'eps' || key === 'min_pts')) continue
    out[key] = hp
  }
  return out
})
// 算法超参数草稿（轮询刷新时不覆盖用户编辑：仅在首次/切换条目时初始化）
const hpDraft = ref({})
// 控制与训练设置草稿：同样仅在首次/切换条目时从后端状态初始化
watch(st, (s) => {
  if (!hpInited && s && s.hyperparams) {
    hpDraft.value = JSON.parse(JSON.stringify(s.hyperparams))
    hpInited = true
  }
  if (!settingsInited && s && s.schedule) {
    intervalDraft.value = s.schedule.interval || 30
    const w = s.schedule.window
    windowOn.value = !!w
    winStart.value = (w && w.start) || '08:00'
    winEnd.value = (w && w.end) || '18:00'
    settingsInited = true
  }
}, { deep: true })
function fmtHp(v) { return v == null ? '—' : Number(v) }

// 训练控制
function toggleTrain() {
  if (st.value.running) store.stopOptimizer(strategy.value.id)
  else store.startOptimizer(strategy.value.id)
}
function trainOnce() { store.trainOptimizer(strategy.value.id, 1) }
function resetModel() { store.resetOptimizer(strategy.value.id) }
function saveHyper() { store.setOptimizerHyper(strategy.value.id, { ...hpDraft.value }) }
function applyModel() { store.applyOptimizer(strategy.value.id) }
// ---- 控制与训练设置 ----
// 自动化控制开关：直接以事件目标值为准（st.auto_control 需等轮询刷新才更新，
// 用 !st.auto_control 取反在快速连点时可能按过时状态重复/反向提交，导致提示反复弹出）
function toggleAutoControl(e) {
  store.setOptimizerSettings(strategy.value.id, { auto_control: !!e.target.checked })
}
function saveSchedule() {
  store.setOptimizerSettings(strategy.value.id, {
    schedule: {
      interval: Math.max(5, Math.round(intervalDraft.value || 30)),
      window: windowOn.value ? { start: winStart.value || '08:00', end: winEnd.value || '18:00' } : null,
    },
  })
}
// ---- 模型版本 ----
function saveVersion() { store.archiveOptimizer(strategy.value.id) }
function switchVer(vid) { store.switchOptimizerVersion(strategy.value.id, vid) }
function ackReminder() { store.ackOptimizer(strategy.value.id) }
function fmtTime(iso) {
  if (!iso) return '—'
  const t = iso.includes('T') ? iso : iso.replace(' ', 'T')
  const d = new Date(t)
  if (isNaN(d.getTime())) return iso
  const p = (x) => String(x).padStart(2, '0')
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// 进入面板：同步最新流程为训练上下文并立即拉取训练状态（全局轮询已在 store.init 启动）
onMounted(() => {
  store.syncOptimizerContext().then(() => store.refreshOptimizers())
})

function opParamLabel(op) {
  const u = op.target
  const p = op.param
  if (!u || !p) return p || ''
  // 从参数元数据中查找该工序参数的显示名（label），找不到则回退原始 key
  for (const list of Object.values(EDITABLE_PARAMS)) {
    const found = list.find((x) => x.key === p)
    if (found) return found.label || p
  }
  return p
}
function opUnit(op) {
  const p = op.param
  if (!p) return ''
  for (const list of Object.values(EDITABLE_PARAMS)) {
    const found = list.find((x) => x.key === p)
    if (found) return found.unit || ''
  }
  return ''
}
function opNote(op) {
  return op.note || (op.action === 'set_param' ? `${op.target || ''} ${op.param || ''} = ${op.value}` : op.action || '')
}
function markDirty() {}

async function save() {
  if (!strategy.value) return
  await store.updateStrategy(strategy.value.id, {
    name: nameDraft.value.trim() || t('未命名策略'),
    description: descDraft.value,
    ops: opsDraft.value,
  })
}
function runSim() {
  if (!strategy.value) return
  store.runStrategySimulation(strategy.value.id)
}
// 工艺策略：跳转到对应工艺的属性面板
function goProcess() {
  if (!strategy.value) return
  store.selectAssetType(strategy.value.processType)
}
// 工艺策略：切换启用/停用
function toggleGreen() {
  if (!strategy.value) return
  store.toggleGreenStrategy(strategy.value.processType, strategy.value.sid)
  const on = store.greenStrategiesFor(strategy.value.processType).includes(strategy.value.sid)
  store.showToast(on ? `${t('已启用策略')}「${strategy.value.name}」` : `${t('已停用策略')}「${strategy.value.name}」`, 'success')
}
</script>

<style scoped>
.strategy-detail { padding: 2px 0; }
.inp { width: 100%; box-sizing: border-box; background: var(--input, var(--bg)); border: 1px solid var(--line); color: var(--text); border-radius: 3px; padding: 4px 8px; font-size: 11px; }
.inp:focus { border-color: var(--accent-d); box-shadow: 0 0 0 1px var(--accent-l); outline: none; }
.inp.num { width: 90px; text-align: right; flex: 0 0 auto; padding: 4px 8px; }
textarea.inp { resize: vertical; font-family: inherit; line-height: 1.5; }
.tag { display: inline-block; font-size: 10px; color: var(--accent2); border: 1px solid var(--line); border-radius: 3px; padding: 1px 6px; }
.tag-row { display: flex; gap: 6px; flex-wrap: wrap; }
.toggle-card { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.src-tip { margin-left: 8px; }
.toggle-card .x.on { background: var(--accent); color: var(--on-accent); border-color: var(--accent-d); }
.btn-mini { flex: 0 0 auto; font-size: 11px; padding: 3px 9px; border-radius: 3px; background: var(--panel-2); color: var(--accent2); border: 1px solid var(--line); cursor: pointer; margin-top: 8px; }
.btn-mini:hover { border-color: var(--accent2); }
.ops { display: flex; flex-direction: column; gap: 8px; }
.op-row { border: 1px solid var(--line); border-radius: 3px; padding: 6px 8px; background: var(--panel-2); }
.op-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.op-note { font-size: 11px; color: var(--text); }
.op-kind { font-size: 10px; color: var(--muted); border: 1px solid var(--line); border-radius: 3px; padding: 0 6px; }
.op-edit { display: flex; align-items: center; gap: 8px; }
.op-label { flex: 1; font-size: 11px; color: var(--muted); }
.op-unit { font-size: 11px; color: var(--muted); }
.op-static { font-size: 11px; }
.actions { display: flex; gap: 8px; margin-top: 14px; }
.actions .x { flex: 1; padding: 9px 0; font-size: 12px; }
/* ---- AI 优化模型训练面板 ---- */
.badge { display: inline-block; font-size: 10px; padding: 1px 9px; border-radius: 9px; border: 1px solid var(--line); color: var(--muted); }
.badge.run { color: #34d399; border-color: #34d399; background: rgba(52, 211, 153, .12); }
.badge.pause { color: var(--accent2); border-color: var(--accent2); background: rgba(56, 132, 255, .12); }
.actions .x.main { background: var(--accent); color: var(--on-accent); border-color: var(--accent-d); }
.actions .x.main:disabled { opacity: .5; cursor: not-allowed; }
.stat-row { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.stat { background: var(--panel-2); border: 1px solid var(--line); border-radius: 3px; padding: 8px 10px; display: flex; flex-direction: column; gap: 2px; }
.stat b { font-size: 15px; color: var(--text); font-variant-numeric: tabular-nums; }
.stat b.good { color: #34d399; }
.stat b.bad { color: #f87171; }
.stat span { font-size: 10px; color: var(--muted); }
.tip-row { display: flex; align-items: center; gap: 6px; margin-top: 12px; }
.dot { width: 6px; height: 6px; border-radius: 2px; background: var(--muted); flex: 0 0 auto; }
.dot.on { background: var(--green); }
.chart { width: 100%; }
.chart-svg { width: 100%; height: 96px; display: block; }
.chart-svg .grid { stroke: var(--line); stroke-width: 1; opacity: .5; }
.chart-svg .line-best { fill: none; stroke: #34d399; stroke-width: 2; stroke-linejoin: round; }
.chart-svg .line-avg { fill: none; stroke: #fbbf24; stroke-width: 1.2; opacity: .65; stroke-linejoin: round; }
.legend { display: flex; align-items: center; gap: 12px; margin-top: 6px; font-size: 10px; color: var(--muted); }
.legend .lg { display: inline-flex; align-items: center; gap: 4px; }
.legend .lg::before { content: ''; width: 14px; height: 3px; border-radius: 2px; }
.legend .lg.best::before { background: #34d399; }
.legend .lg.avg::before { background: #fbbf24; opacity: .7; }
.legend .lg.muted::before { display: none; }
.legend .lg.dot-blue::before { background: var(--accent2); width: 8px; height: 8px; border-radius: 50%; }
/* 参数优化集中面板：GA / PSO / RL 算法切换 tabs */
.opt-tabs { display: flex; gap: 6px; margin: 8px 0 2px; }
.opt-tab { flex: 1; padding: 6px 4px; font-size: 11.5px; border: 1px solid var(--line); border-radius: 4px;
  background: var(--panel-2); color: var(--muted); cursor: pointer; transition: all .12s; }
.opt-tab.on { border-color: var(--accent-d); color: var(--accent-d); background: var(--accent-l); font-weight: 600; }
.opt-tab:hover:not(.on) { border-color: var(--accent-d); color: var(--text); }
/* 数据拟合：方程展示与曲线散点 */
.fit-eq { padding: 8px 10px; background: var(--panel-2); border: 1px solid var(--line); border-radius: 4px; margin-bottom: 6px; }
.fit-eq-main { font-family: var(--mono, Consolas, Menlo, monospace); font-size: 13px; color: var(--accent2); margin-bottom: 4px; word-break: break-all; }
.fit-dot { fill: var(--accent2); opacity: .85; }
.fit-stat { font-size: 11px; }
.hp-row { display: flex; align-items: center; gap: 8px; padding: 5px 0; }
.hp-label { flex: 0 0 92px; font-size: 11px; color: var(--muted); }
.hp-slider { flex: 1; accent-color: var(--accent2); min-width: 0; }
.hp-val { flex: 0 0 46px; text-align: right; font-size: 11px; color: var(--text); font-variant-numeric: tabular-nums; }
.bp-list { display: flex; flex-direction: column; gap: 6px; }
.bp-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; background: var(--panel-2); border: 1px solid var(--line); border-radius: 3px; padding: 6px 8px; }
.bp-left { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.bp-left b { font-size: 11px; }
.bp-left .muted { font-size: 10px; }
.bp-right { display: flex; align-items: center; gap: 6px; font-size: 11px; flex: 0 0 auto; }
.bp-right .init { text-decoration: line-through; opacity: .7; }
.bp-right .arrow { color: var(--muted); font-size: 9px; }
.bp-right .arrow.up { color: #fbbf24; }
.bp-right .arrow.down { color: #34d399; }
.bp-right b { font-size: 12px; color: var(--accent2); font-variant-numeric: tabular-nums; }
.logs { display: flex; flex-direction: column; gap: 3px; }
.lg-line { font-size: 10px; color: var(--muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; line-height: 1.6; word-break: break-all; }
/* ---- 手动调优提醒 ---- */
.reminder { border: 1px solid #fbbf24; border-radius: 3px; background: rgba(251, 191, 36, .08); padding: 8px 10px; margin-bottom: 10px; }
.rem-txt { font-size: 11px; color: var(--text); line-height: 1.6; }
.rem-txt b { color: #fbbf24; }
.rem-actions { display: flex; gap: 8px; margin-top: 8px; }
.rem-actions .x { flex: 1; padding: 7px 0; font-size: 11px; }
.rem-actions .x.main { background: var(--accent); color: var(--on-accent); border-color: var(--accent-d); }
/* ---- 控制与训练设置 ---- */
.set-block { padding: 8px 0 2px; }
.set-block + .set-block { border-top: 1px dashed var(--line); margin-top: 8px; }
.set-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 4px 0; }
.set-label { font-size: 11px; color: var(--text); flex: 0 0 auto; }
.x.sw { flex: 0 0 auto; font-size: 11px; padding: 3px 10px; border-radius: 3px; background: var(--panel-2); color: var(--muted); border: 1px solid var(--line); cursor: pointer; }
.x.sw.on { background: var(--accent); color: var(--on-accent); border-color: var(--accent-d); }
.inp.sel { width: auto; min-width: 108px; flex: 0 0 auto; padding: 3px 6px; font-size: 11px; }
.inp.time { width: auto; min-width: 86px; flex: 0 0 auto; padding: 3px 6px; font-size: 11px; }
.chk { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--muted); cursor: pointer; }
.chk input { accent-color: var(--accent2); width: 15px; height: 15px; cursor: pointer; }
/* ---- 聚类工况识别（CLU）：工况簇分布 ---- */
.clu-list { display: flex; flex-direction: column; gap: 9px; padding: 2px 0 4px; }
.clu-row { display: flex; flex-direction: column; gap: 4px; }
.clu-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 11px; }
.clu-head b { font-size: 12px; color: var(--text); }
.clu-head .muted { font-size: 10px; }
.clu-head > b:last-child { font-size: 12px; color: var(--accent2); font-variant-numeric: tabular-nums; }
.clu-bar { height: 6px; border-radius: 3px; background: var(--panel-2); border: 1px solid var(--line); overflow: hidden; }
.clu-fill { height: 100%; border-radius: 3px; background: linear-gradient(90deg, var(--accent2), var(--accent)); transition: width .4s ease; }
/* ---- 决策变量 / 影响变量 / 拟合变量（已选列表 + 删除 + 手动添加） ---- */
.dv-list { display: flex; flex-direction: column; gap: 6px; padding: 2px 0 4px; }
.dv-row { display: flex; align-items: flex-start; gap: 8px; cursor: pointer; padding: 7px 9px; border: 1px solid var(--line); border-radius: 3px; background: var(--panel-2); transition: border-color .15s; }
.dv-row:hover { border-color: var(--accent-d); }
.dv-row input { margin-top: 3px; }
.dv-tag { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 7px 9px; border: 1px solid var(--line); border-radius: 3px; background: var(--panel-2); }
.dv-main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; font-size: 13px; }
.dv-main .muted { font-size: 12px; }
.dv-del { flex: 0 0 auto; width: 22px; height: 22px; border-radius: 50%; border: 1px solid var(--line); background: transparent; color: var(--muted); font-size: 14px; line-height: 1; cursor: pointer; display: flex; align-items: center; justify-content: center; transition: all .12s; }
.dv-del:hover:not(:disabled) { color: #f87171; border-color: #f87171; }
.dv-del:disabled { opacity: .5; cursor: not-allowed; }
.dv-add { margin-top: 8px; }
.dv-add .inp.sel { width: 100%; }
.time-row { justify-content: flex-end; gap: 6px; }
/* ---- 模型版本 ---- */
.ver-list { display: flex; flex-direction: column; gap: 8px; }
.ver-row { border: 1px solid var(--line); border-radius: 3px; padding: 8px; background: var(--panel-2); }
.ver-row.active { border-color: #34d399; background: rgba(52, 211, 153, .06); }
.ver-head { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.ver-head b { font-size: 12px; color: var(--accent2); }
.ver-badge { font-size: 10px; padding: 0 6px; border-radius: 8px; color: #34d399; border: 1px solid #34d399; background: rgba(52, 211, 153, .1); }
.ver-badge.cand { color: var(--muted); border-color: var(--line); background: transparent; }
.ver-meta { font-size: 10px; color: var(--muted); line-height: 1.7; }
.ver-meta b { color: var(--text); font-size: 11px; font-variant-numeric: tabular-nums; }
.ver-meta .imp { margin-left: 6px; font-size: 10px; }
.ver-meta .imp.good { color: #34d399; }
.ver-meta .imp.bad { color: #f87171; }
.ver-row .actions { margin-top: 8px; }
.ver-row .actions .x { padding: 6px 0; font-size: 11px; }
</style>
