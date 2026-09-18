<!-- 2D 工艺图「程序化设备图形」渲染器
     图形数据来自 data/twin2dFigures.js（纯代码绘制、零图片资源，详见该文件头注释）。
     这里只负责把元素描述数组渲染成 SVG —— 与图形内容解耦，新增设备只需在图形库里加一条。

     两个渲染细节：
      · vector-effect="non-scaling-stroke"：图形在自己的 viewBox 里被放大到显示盒，
        普通描边会跟着放粗（24 单位 → 200px 时 0.85 会变 7px），加上它后描边恒为
        el.sw 个**屏幕像素**，缩放时线宽质感不变；
      · filter：指向 Twin2DView <defs> 里的投影滤镜，是伪 3D 立体感的主要来源之一。 -->
<template>
  <svg :x="box.x" :y="box.y" :width="box.w" :height="box.h"
    :viewBox="`0 0 ${vb[0]} ${vb[1]}`" class="t2d-figsvg">
    <!-- 投影施加在**整组**上一次（而不是每个元素一次）：滤镜实例数从「元素数」降到
         「设备台数」，管线流向动画每帧重绘时的栅格化成本随之大幅下降。 -->
    <g filter="url(#f-fig)">
    <template v-for="(el, ei) in els" :key="ei">
      <path v-if="el.tag === 'path'" :d="el.d" :fill="el.fill || 'none'" :stroke="el.stroke || 'none'"
        :stroke-width="el.sw || 0" :stroke-linecap="el.lc" :stroke-linejoin="el.lj"
        :opacity="el.opacity" :filter="el.filter" vector-effect="non-scaling-stroke"/>
      <circle v-else-if="el.tag === 'circle'" :cx="el.cx" :cy="el.cy" :r="el.r"
        :fill="el.fill || 'none'" :stroke="el.stroke || 'none'" :stroke-width="el.sw || 0"
        :opacity="el.opacity" :filter="el.filter" vector-effect="non-scaling-stroke"/>
      <ellipse v-else-if="el.tag === 'ellipse'" :cx="el.cx" :cy="el.cy" :rx="el.rx" :ry="el.ry"
        :fill="el.fill || 'none'" :stroke="el.stroke || 'none'" :stroke-width="el.sw || 0"
        :opacity="el.opacity" :filter="el.filter" :transform="el.transform || ''"
        vector-effect="non-scaling-stroke"/>
      <rect v-else-if="el.tag === 'rect'" :x="el.x" :y="el.y" :width="el.width" :height="el.height"
        :rx="el.rx || 0" :fill="el.fill || 'none'" :stroke="el.stroke || 'none'"
        :stroke-width="el.sw || 0" :opacity="el.opacity" :filter="el.filter"
        vector-effect="non-scaling-stroke"/>
      <polygon v-else-if="el.tag === 'polygon'" :points="polyPts(el.pts)" :fill="el.fill || 'none'"
        :stroke="el.stroke || 'none'" :stroke-width="el.sw || 0" :opacity="el.opacity"
        :filter="el.filter" vector-effect="non-scaling-stroke"/>
    </template>
    </g>
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { figureOf } from '../data/twin2dFigures'

const props = defineProps({
  type: { type: String, default: '' },
  box: { type: Object, required: true },   // 图形显示盒（节点局部坐标）
})

const vb = computed(() => figureOf(props.type).vb)
const els = computed(() => figureOf(props.type).els)
function polyPts(pts) {
  return (pts || []).map((p) => p.join(',')).join(' ')
}
</script>

<style scoped>
.t2d-figsvg { overflow: visible; }
</style>
