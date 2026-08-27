<template>
  <svg class="ui-icon" :width="size" :height="size" viewBox="0 0 24 24" fill="none"
       stroke="currentColor" :stroke-width="stroke" stroke-linecap="round" stroke-linejoin="round"
       xmlns="http://www.w3.org/2000/svg" aria-hidden="true" v-html="icon"></svg>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  name: { type: String, required: true },
  size: { type: [Number, String], default: 16 },
  stroke: { type: [Number, String], default: 1.7 },
})

// 统一的线性图标集（24x24，currentColor 描边，1.7 粗细，圆角端点）
// 全部采用同一套描边语言，保证全局视觉一致、克制、贴近工业软件。
const I = {
  run: '<path d="M7 5 L19 12 L7 19 Z" fill="currentColor" stroke="none"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  reset: '<path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/>',
  rotate: '<polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10"/>',
  globe: '<circle cx="12" cy="12" r="9"/><line x1="3" y1="12" x2="21" y2="12"/><path d="M12 3a15 15 0 0 1 4 9 15 15 0 0 1-4 9 15 15 0 0 1-4-9 15 15 0 0 1 4-9z"/>',
  pencil: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.12 2.12 0 0 1 3 3L12 15l-4 1 1-4Z"/>',
  grid: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
  panorama: '<path d="M2 6a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2z"/><circle cx="8" cy="10" r="2"/><path d="m2 16 5-5 4 4 6-6 5 5"/>',
  front: '<rect x="5" y="4" width="14" height="16" rx="1"/><line x1="5" y1="12" x2="19" y2="12"/>',
  side: '<path d="M8 4 L20 7 L20 17 L8 20 Z"/>',
  target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><line x1="12" y1="1" x2="12" y2="4"/><line x1="12" y1="20" x2="12" y2="23"/><line x1="1" y1="12" x2="4" y2="12"/><line x1="20" y1="12" x2="23" y2="12"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  compare: '<line x1="12" y1="3" x2="12" y2="21"/><rect x="3" y="5" width="7" height="14" rx="1"/><rect x="14" y="5" width="7" height="14" rx="1"/>',
  report: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="12" y1="18" x2="12" y2="12"/><polyline points="9 15 12 18 15 15"/>',
  undo: '<polyline points="9 14 4 9 9 4"/><path d="M20 20v-7a4 4 0 0 0-4-4H4"/>',
  redo: '<polyline points="15 14 20 9 15 4"/><path d="M4 20v-7a4 4 0 0 1 4-4h12"/>',
  menu: '<line x1="3" y1="6" x2="21" y2="6"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="18" x2="21" y2="18"/>',
  export: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/>',
  help: '<circle cx="12" cy="12" r="9"/><path d="M9.09 9a3 3 0 0 1 5.83 1c0 2-3 3-3 3"/><line x1="12" y1="17" x2="12.01" y2="17"/>',
  panelLeft: '<polyline points="15 18 9 12 15 6"/>',
  panelRight: '<polyline points="9 6 15 12 9 18"/>',
  panelBottom: '<polyline points="6 9 12 15 18 9"/>',
  // 活动栏专用：更硬朗的工业软件风格图标
  explorer: '<line x1="3" y1="7" x2="21" y2="7"/><line x1="3" y1="12" x2="21" y2="12"/><line x1="3" y1="17" x2="21" y2="17"/><line x1="7" y1="7" x2="7" y2="17"/>',
  scene3d: '<path d="M12 2.2 L21.5 7.3 V16.7 L12 21.8 L2.5 16.7 V7.3 Z"/><path d="M2.5 7.3 L12 12 L21.5 7.3"/><path d="M12 12 V21.8"/>',
  link: '<circle cx="7.5" cy="16.5" r="3"/><circle cx="16.5" cy="7.5" r="3"/><path d="M10 14 L14 10"/>',
  save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
  open: '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>',
  newFile: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><line x1="12" y1="12" x2="12" y2="18"/><line x1="9" y1="15" x2="15" y2="15"/>',
  search: '<circle cx="11" cy="11" r="7"/><line x1="21" y1="21" x2="16.65" y2="16.65"/>',
  cube: '<path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
  database: '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5V19a8 3 0 0 0 16 0V5"/><path d="M4 12a8 3 0 0 0 16 0"/>',
  flow: '<circle cx="6" cy="6" r="2.5"/><circle cx="18" cy="18" r="2.5"/><circle cx="18" cy="6" r="2.5"/><line x1="8" y1="7" x2="16" y2="17"/><line x1="8" y1="5" x2="16" y2="5"/>',
  process: '<circle cx="5" cy="6" r="2"/><circle cx="5" cy="18" r="2"/><circle cx="19" cy="12" r="2"/><path d="M7 6h5a5 5 0 0 1 5 5M7 18h5a5 5 0 0 0 5-5"/>',
  material: '<path d="M12 3 20 7.5 V16.5 L12 21 4 16.5 V7.5 Z"/><path d="M4 7.5 12 12 20 7.5"/><path d="M12 12 V21"/>',
  product: '<path d="M3 8 12 3 21 8 V16 L12 21 3 16 Z"/><path d="M3 8 12 13 21 8"/><path d="M12 13 V21"/>',
  patrol: '<rect x="5" y="8" width="14" height="11" rx="2"/><circle cx="9.5" cy="13.5" r="1.4" fill="currentColor" stroke="none"/><circle cx="14.5" cy="13.5" r="1.4" fill="currentColor" stroke="none"/><line x1="12" y1="4" x2="12" y2="8"/><circle cx="12" cy="3" r="1.3" fill="currentColor" stroke="none"/>',
  scene: '<path d="M2 20a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V8l-7 5V8l-7 5V4a2 2 0 0 0-2-2H4a2 2 0 0 0-2 2Z"/><path d="M17 18h1"/><path d="M12 18h1"/><path d="M7 18h1"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  bolt: '<path d="M13 2 L4 14 H11 L9 22 L20 9 H13 Z" fill="currentColor" stroke="none"/>',
  tower: '<path d="M12 3 L5 21 M12 3 L19 21 M7 13 H17 M9 17 H15"/><line x1="5" y1="21" x2="19" y2="21"/>',
  pole: '<line x1="12" y1="3" x2="12" y2="21"/><line x1="7" y1="8" x2="17" y2="8"/><line x1="8" y1="12" x2="16" y2="12"/>',
  transformer: '<rect x="6" y="6" width="12" height="14" rx="1"/><path d="M13 8 L9 14 H12 L11 18 L15 11 H12 Z" fill="currentColor" stroke="none"/>',
  substation: '<rect x="4" y="4" width="16" height="16" rx="1"/><path d="M4 4 L20 20 M20 4 L4 20" opacity="0.5"/><path d="M13 7 L10 12 H12 L11 15 L14 10 H12 Z" fill="currentColor" stroke="none"/>',
  aux: '<path d="M3 21V9l6 4V9l6 4V5h6v16z"/><path d="M13 11 L10 15 H12 L11 18 L14 13 H12 Z" fill="currentColor" stroke="none"/>',
  zoomIn: '<circle cx="10.5" cy="10.5" r="6.5"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="10.5" y1="7.5" x2="10.5" y2="13.5"/><line x1="7.5" y1="10.5" x2="13.5" y2="10.5"/>',
  zoomOut: '<circle cx="10.5" cy="10.5" r="6.5"/><line x1="15" y1="15" x2="21" y2="21"/><line x1="7.5" y1="10.5" x2="13.5" y2="10.5"/>',
  fit: '<path d="M4 9 V4 H9"/><path d="M15 4 H20 V9"/><path d="M20 15 V20 H15"/><path d="M9 20 H4 V15"/><rect x="9" y="9" width="6" height="6" rx="1" opacity="0.5"/>',
  fullscreen: '<path d="M4 10 V4 H10"/><path d="M14 4 H20 V10"/><path d="M20 14 V20 H14"/><path d="M10 20 H4 V14"/>',
  refresh: '<polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
  brightness: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="M4.93 4.93l1.41 1.41"/><path d="M17.66 17.66l1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="M6.34 17.66l-1.41 1.41"/><path d="M19.07 4.93l-1.41 1.41"/>',
  close: '<line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>',
}

const icon = computed(() => I[props.name] || '')
</script>

<style scoped>
.ui-icon { display: block; flex: none; }
</style>
