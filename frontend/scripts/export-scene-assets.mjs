// 从 flowLibrary.js 一次性导出「钢包场景资产」数据文件（流程字典场景化 · 数据源迁移工具）：
//   1) templates.json —— 行业预置方案模板快照 [{id,label,desc,icon,route,scheme}]，
//      scheme 与前端编排快照（buildScheme 输出）同构，可直接在画布装载；
//   2) dictionary.json —— 行业素材字典数据面（物料/产品/工艺/设备目录；函数/引擎耦合不上盘）。
//
// 产物写入 backend/data/scenes/steel/ —— 这是该场景资源包的数据真源：
//   - 运行时经 /api/scene/:id/resource 随包下发（scene_loader 包文件形态直读）；
//   - pack_ec.py 打包 .ec 时同样收编（行业包 = 目录即包）。
// 前端 loadTemplate/_schemeFromRoute 在场景包模板可用时直接装载快照，
// flowLibrary 的 buildScheme 退化为「兜底/离线」路径。
//
// 运行（frontend 目录内）：node scripts/export-scene-assets.mjs
// 注意：此后修改钢铁模板/素材字典，须重跑本脚本并提交两个 JSON。
import { writeFileSync, mkdirSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { buildScheme, MATERIALS, PRODUCT_IDS, PROCESS_TEMPLATES, DEVICE_TEMPLATES } from '../src/data/flowLibrary.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const OUT_DIR = join(__dirname, '..', '..', 'backend', 'data', 'scenes', 'steel')
mkdirSync(OUT_DIR, { recursive: true })

// 顺序 = UI 展示顺序（历史 Ribbon/菜单长流程在前，保持钢铁观感零变化）
const templates = [
  { id: 'long', label: '长流程模板', desc: '载入长流程炼钢模板（高炉-转炉长流程）', icon: 'flow', route: 'long', scheme: buildScheme('long') },
  { id: 'short', label: '短流程模板', desc: '载入短流程炼钢模板（电炉短流程）', icon: 'process', route: 'short', scheme: buildScheme('short') },
]

// 素材字典数据面（全部为纯数据；若有函数字段会被 JSON 丢弃，故导出后做完整性自检）
const dictionary = {
  format: 'dictionary/1',
  scene: 'steel',
  materials: MATERIALS,
  products: PRODUCT_IDS,
  processes: PROCESS_TEMPLATES,
  devices: DEVICE_TEMPLATES,
}

function writeJson(name, obj) {
  const raw = JSON.stringify(obj)
  if (raw === undefined) throw new Error(`不可序列化：${name}`)
  const text = JSON.stringify(JSON.parse(raw), null, 1) + '\n'
  writeFileSync(join(OUT_DIR, name), text, 'utf8')
  console.log(`已写出 backend/data/scenes/steel/${name}  (${(raw.length / 1024).toFixed(1)} KB)`)
}

// 完整性自检：模板快照应含真实节点/连接/设备（防止函数字段被 JSON 静默丢弃）
for (const tpl of templates) {
  const s = tpl.scheme
  const check = { nodes: (s.nodes || []).length, connections: (s.connections || []).length, groups: (s.groups || []).length, devices: (s.devices || []).length }
  if (!check.nodes) throw new Error(`模板 ${tpl.id} scheme 为空节点，导出中止`)
  console.log(`  · ${tpl.id}: ${JSON.stringify(check)}`)
}

writeJson('templates.json', templates)
writeJson('dictionary.json', dictionary)
console.log('完成。钢铁场景资产数据源 = backend/data/scenes/steel/{templates,dictionary}.json')
