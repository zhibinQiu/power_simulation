<template>
  <svg
    class="dev-glyph"
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    fill="none"
    :stroke="color"
    stroke-width="1.6"
    stroke-linecap="round"
    stroke-linejoin="round"
    v-html="inner"
  />
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  type: { type: String, required: true },
  color: { type: String, default: '#8a929b' },
  size: { type: [Number, String], default: 16 },
})

// 工业线稿符号：每种设备一类专属图标，避免 emoji，呈现稳重的工业软件观感
const GLYPHS = {
  // 计量设备
  // 皮带秤：输送带 + 托辊 + 物料
  belt_scale: '<rect x="3" y="9" width="18" height="6" rx="1"/><circle cx="7" cy="12" r="1.6"/><circle cx="17" cy="12" r="1.6"/><path d="M5 9V7M9 9V7M13 9V7M17 9V7"/>',
  // 失重秤：漏斗 + 下料箭头
  loss_in_weight: '<path d="M6 4h12l-4 8h-4z"/><path d="M12 12v8"/><path d="M9.5 15.5L12 18l2.5-2.5"/>',
  // 料斗秤：料仓 + 支架
  hopper_scale: '<path d="M7 4h10v5H7z"/><path d="M7 9v5h10V9"/><path d="M9 14v4h6v-4"/><path d="M10 18h4"/>',
  // 平台秤：平台 + 指示
  weighbridge: '<rect x="3" y="13" width="18" height="3" rx="1"/><path d="M6 16v3M18 16v3"/><path d="M12 13V10M9 10h6"/><circle cx="12" cy="8.4" r="1.4"/>',
  weigher: '<rect x="3" y="13" width="18" height="3" rx="1"/><path d="M6 16v3M18 16v3"/><path d="M12 13V10M9 10h6"/><circle cx="12" cy="8.4" r="1.4"/>',
  // 气体流量计：管道 + 流向箭头
  gas_flowmeter: '<path d="M3 12h18"/><path d="M14 9l4 3-4 3"/><path d="M8 9l4 3-4 3"/>',
  // 液体流量计：管道 + 液流线
  liquid_flowmeter: '<path d="M3 12h18"/><path d="M9 9.5v5M12.5 9.5v5M16 9.5v5"/>',
  // 电能表：表盘 + 指针
  power_meter: '<circle cx="12" cy="13" r="7"/><path d="M12 13l4-4"/><path d="M9 4h6"/>',
  // 成分分析仪：烧瓶
  composition_analyzer: '<path d="M9 3h6M10 3v5l-4 10a1.6 1.6 0 0 0 1.5 2.2h9A1.6 1.6 0 0 0 18 18l-4-10V3"/><path d="M8.5 14h7"/>',
  // CEMS：烟囱 + 排放弧
  cems: '<path d="M9 21V8h6v13"/><path d="M9 8h6"/><path d="M10.5 8c0-3 3-3 3-6"/><path d="M12 8c0-3.5 2.5-3.5 2.5-6.5"/>',
  // 测温仪：温度计
  thermo: '<path d="M10 4a2 2 0 0 1 4 0v10.5a4.5 4.5 0 1 1-4 0z"/><path d="M12 14v-2"/>',

  // 可调设备
  // 鼓风机：星形风机
  blower: '<circle cx="12" cy="12" r="2.6"/><path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3M6 6l2.1 2.1M15.9 15.9L18 18M18 6l-2.1 2.1M8.1 15.9L6 18"/>',
  // 引风机：斜置叶片风机
  id_fan: '<circle cx="12" cy="12" r="2.4"/><path d="M12 9.6L15.8 6M12 9.6l3.4 2.8M12 14.4L8.2 18M12 14.4L8.6 11.6"/>',
  // 皮带机：输送带 + 倾斜给料
  belt_conv: '<rect x="3" y="10" width="18" height="4.5" rx="1"/><circle cx="6.5" cy="14.5" r="1.5"/><circle cx="17.5" cy="14.5" r="1.5"/><path d="M9 10l2-3M14 10l2-3"/>',
  // 给料机：漏斗 + 出料
  feeder: '<path d="M6 4h12l-3 8H9z"/><path d="M10 12l-1.5 8M14 12l1.5 8"/>',
  // 泵：泵体 + 叶轮 + 管路
  pump: '<circle cx="12" cy="12" r="5"/><path d="M12 9l3 3-3 3-3-3z"/><path d="M3 12h4M17 12h4M12 3v4M12 17v4"/>',
  // 调节阀：管道 + 阀盘
  valve: '<path d="M3 12h18"/><circle cx="12" cy="12" r="3.2"/><path d="M12 5.5V4M12 20v-1.5"/>',
  // 燃烧器：火焰
  burner: '<path d="M12 3.5c1.6 2.2 4 4 4 7a4 4 0 1 1-8 0c0-3 2.4-4.8 4-7z"/><path d="M12 17.5v3"/>',
  // 喷吹系统：喷枪 + 喷射口
  injector: '<rect x="4" y="6" width="14" height="4" rx="1.5"/><path d="M18 8h3"/><path d="M7 10v4a2 2 0 0 0 2 2h3"/>',
  // 电极调节器：电极 + 电弧
  electrode_reg: '<path d="M8 3v8M16 3v8"/><path d="M9 11l3 4 3-4"/><path d="M12 15v4"/>',
  // 变频器：屏幕 + 波形
  vfd: '<rect x="4" y="4" width="16" height="16" rx="2"/><path d="M7 14l3-5 2.5 6L15 9l2 5"/>',
  // 氧枪：枪管 + 喷射
  oxygen_lance: '<path d="M12 3v9"/><path d="M8.5 3h7"/><path d="M12 12l-3.5 2M12 12l3.5 2"/>',
  // 冷却水泵：泵 + 水滴
  cool_pump: '<circle cx="12" cy="12" r="5"/><path d="M12 9l3 3-3 3-3-3z"/><path d="M3 12h4M17 12h4M12 3v4M12 17v4"/><path d="M18.5 3.5c0 1.4-1 1.9-1 1.9s-1-.5-1-1.9a1 1 0 0 1 2 0z"/>',
  // 除尘风机：风机 + 烟尘点
  dedust_fan: '<circle cx="12" cy="12" r="2.4"/><path d="M12 3.5v3M12 17.5v3M3.5 12h3M17.5 12h3M6 6l2.1 2.1M15.9 15.9L18 18M18 6l-2.1 2.1M8.1 15.9L6 18"/><circle cx="19" cy="19" r="1"/><circle cx="16" cy="21" r=".7"/>',
  // 余热锅炉：罐 + 蒸汽管 + 蒸汽
  waste_heat_boiler: '<rect x="5" y="4" width="14" height="16" rx="2"/><path d="M9 4v5a3 3 0 0 0 6 0V4"/><path d="M12 9v7"/><path d="M8 2.5c-1.2 0-1.2 1.5 0 1.5M12 2.5c-1.2 0-1.2 1.5 0 1.5M16 2.5c-1.2 0-1.2 1.5 0 1.5"/>',
  // 热风炉：竖炉 + 热浪
  hot_blast_stove: '<path d="M6 21V7a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v14"/><path d="M6 14h12"/><path d="M10 5V3M14 5V3"/><path d="M8 21c0-1.6 1-1.6 1 0M12 21c0-1.6 1-1.6 1 0M16 21c0-1.6 1-1.6 1 0"/>',

  // FlowEditor 旧图标别名（DEVICE_MAP icon 字段）：belt / hopper / pipe / gauge / flask / stack
  belt: '<rect x="3" y="9" width="18" height="6" rx="1"/><circle cx="7" cy="12" r="1.6"/><circle cx="17" cy="12" r="1.6"/><path d="M5 9V7M9 9V7M13 9V7M17 9V7"/>',
  hopper: '<path d="M6 4h12l-4 8h-4z"/><path d="M12 12v8"/><path d="M9.5 15.5L12 18l2.5-2.5"/>',
  pipe: '<path d="M3 12h18"/><path d="M14 9l4 3-4 3"/><path d="M8 9l4 3-4 3"/>',
  gauge: '<circle cx="12" cy="13" r="7"/><path d="M12 13l4-4"/><path d="M9 4h6"/>',
  flask: '<path d="M9 3h6M10 3v5l-4 10a1.6 1.6 0 0 0 1.5 2.2h9A1.6 1.6 0 0 0 18 18l-4-10V3"/><path d="M8.5 14h7"/>',
  stack: '<path d="M9 21V8h6v13"/><path d="M9 8h6"/><path d="M10.5 8c0-3 3-3 3-6"/><path d="M12 8c0-3.5 2.5-3.5 2.5-6.5"/>',
}

const inner = computed(() => GLYPHS[props.type] || GLYPHS.gauge)
</script>

<style scoped>
.dev-glyph { display: block; }
</style>
