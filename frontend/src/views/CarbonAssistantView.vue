<script setup>
import { ref } from 'vue'
import CarbonMarketView from '../components/CarbonMarketView.vue'
import CarbonCompliancePanel from '../components/carbon/CarbonCompliancePanel.vue'
import CarbonReportSidebar from '../components/carbon/CarbonReportSidebar.vue'

const marketViewRef = ref(null)
const complianceRef = ref(null)
const reportOpen = ref(false)
// 页签：market（CEA / CCER 行情） | ledger（企业台账与策略），由顶栏「视图」菜单二级菜单控制
const tab = ref('market')

function loadAll() {
  if (marketViewRef.value && marketViewRef.value.loadAll) {
    marketViewRef.value.loadAll()
  }
}
function switchInstrument(v) {
  if (marketViewRef.value && marketViewRef.value.switchInstrument) {
    marketViewRef.value.switchInstrument(v)
  }
}
function switchTab(id) {
  tab.value = id
}
// 刷新企业台账与策略数据（供 RibbonToolbar 台账页签「刷新台账」按钮调用）
function refreshLedger() {
  if (complianceRef.value && complianceRef.value.loadAll) {
    complianceRef.value.loadAll()
  }
}
// 打开报告生成侧边栏（供 RibbonToolbar「生成碳资产报告」按钮调用）
function openReport() { reportOpen.value = true }

defineExpose({ loadAll, switchInstrument, switchTab, tab, refreshLedger, openReport })
</script>

<template>
  <div class="carbon-assistant-view" @click.stop>
    <!-- 内容区：行情 / 台账两个视图，页签由顶栏「视图」菜单二级菜单控制 -->
    <div class="view-content">
      <CarbonMarketView v-show="tab === 'market'" ref="marketViewRef" />
      <CarbonCompliancePanel v-show="tab === 'ledger'" ref="complianceRef" />
    </div>

    <CarbonReportSidebar v-model="reportOpen" />
  </div>
</template>

<style scoped>
.carbon-assistant-view {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
/* 内容区：两个视图（行情 / 台账）在此绝对定位填满 */
.view-content {
  position: relative;
  flex: 1;
  min-height: 0;
  min-width: 0;
}
</style>
