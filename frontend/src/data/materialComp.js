// 物料详细化学成分定义（质量分数 %）——单一数据源
// 默认值为行业典型值（高碱度烧结矿 / 氧化球团 / 干熄焦 / 石灰石 / 块矿），供台账、
// 成分敏感分析与炉渣碱度计算使用；覆盖值经 store.setMaterialComp 写入
// materialOverrides[id].composition，随方案持久化。
//
// 字段结构：{ key, label, def, step, min, max, sub }
//   sub: 'ash' —— 灰分内部组成（占灰分的质量分数 %），在界面归入「灰分组成」子分组；
//         焦炭/煤/煤粉的灰分总量字段 ash（占燃料 %）与灰分组成字段 ash_*（占灰分 %）
//         是两个层级：燃料带入灰分量 = 用量 × ash%；灰分中 CaO 量 = 灰分量 × ash_cao%。
export const COMP_DEFS = {
  sinter: [
    { key: 'tfe', label: 'TFe（全铁）', def: 57.5, step: 0.1, min: 40, max: 70 },
    { key: 'feo', label: 'FeO（氧化亚铁）', def: 8.5, step: 0.1, min: 0, max: 30 },
    { key: 'cao', label: 'CaO', def: 10.5, step: 0.1, min: 0, max: 30 },
    { key: 'sio2', label: 'SiO₂', def: 5.2, step: 0.1, min: 0, max: 20 },
    { key: 'mgo', label: 'MgO', def: 2.0, step: 0.1, min: 0, max: 10 },
    { key: 'al2o3', label: 'Al₂O₃', def: 1.6, step: 0.1, min: 0, max: 10 },
    { key: 's', label: 'S（硫）', def: 0.02, step: 0.005, min: 0, max: 0.5 },
    { key: 'p', label: 'P（磷）', def: 0.05, step: 0.005, min: 0, max: 0.5 },
    { key: 'loi', label: '烧损（LOI）', def: 0.5, step: 0.1, min: 0, max: 10 },
  ],
  pellet: [
    { key: 'tfe', label: 'TFe（全铁）', def: 63.5, step: 0.1, min: 50, max: 70 },
    { key: 'feo', label: 'FeO（氧化亚铁）', def: 0.8, step: 0.1, min: 0, max: 10 },
    { key: 'cao', label: 'CaO', def: 1.2, step: 0.1, min: 0, max: 15 },
    { key: 'sio2', label: 'SiO₂', def: 4.5, step: 0.1, min: 0, max: 15 },
    { key: 'mgo', label: 'MgO', def: 0.8, step: 0.1, min: 0, max: 10 },
    { key: 'al2o3', label: 'Al₂O₃', def: 0.8, step: 0.1, min: 0, max: 10 },
    { key: 's', label: 'S（硫）', def: 0.005, step: 0.001, min: 0, max: 0.2 },
    { key: 'p', label: 'P（磷）', def: 0.03, step: 0.005, min: 0, max: 0.3 },
    { key: 'loi', label: '烧损（LOI）', def: 0.2, step: 0.1, min: 0, max: 5 },
  ],
  // 铁矿石（块矿）：高炉天然块炉料，SiO₂/Al₂O₃ 脉石为主要酸性物来源
  iron_ore: [
    { key: 'tfe', label: 'TFe（全铁）', def: 62.0, step: 0.1, min: 45, max: 70 },
    { key: 'feo', label: 'FeO（氧化亚铁）', def: 0.5, step: 0.1, min: 0, max: 10 },
    { key: 'cao', label: 'CaO', def: 0.2, step: 0.05, min: 0, max: 10 },
    { key: 'sio2', label: 'SiO₂', def: 5.5, step: 0.1, min: 0, max: 20 },
    { key: 'mgo', label: 'MgO', def: 0.3, step: 0.05, min: 0, max: 10 },
    { key: 'al2o3', label: 'Al₂O₃', def: 2.5, step: 0.1, min: 0, max: 10 },
    { key: 's', label: 'S（硫）', def: 0.03, step: 0.005, min: 0, max: 0.5 },
    { key: 'p', label: 'P（磷）', def: 0.05, step: 0.005, min: 0, max: 0.5 },
    { key: 'loi', label: '烧损（LOI）', def: 1.0, step: 0.1, min: 0, max: 10 },
  ],
  // 石灰石（熔剂）：CaO 主要外源，入炉受热分解 CaCO₃→CaO+CO₂（LOI≈42% 为分解失重）
  limestone: [
    { key: 'cao', label: 'CaO', def: 52.0, step: 0.1, min: 40, max: 56 },
    { key: 'sio2', label: 'SiO₂', def: 2.5, step: 0.1, min: 0, max: 10 },
    { key: 'mgo', label: 'MgO', def: 1.5, step: 0.1, min: 0, max: 10 },
    { key: 'al2o3', label: 'Al₂O₃', def: 1.0, step: 0.1, min: 0, max: 5 },
    { key: 'loi', label: '烧损（LOI）', def: 42.0, step: 0.5, min: 30, max: 46 },
  ],
  // 焦炭：干基工业分析 FC+A+V≈100%；灰分组成（sub:'ash'）为灰分内部构成，
  // 用于炉渣碱度计算（灰分中 CaO/SiO₂/MgO/Al₂O₃ 全部入渣）。
  coke: [
    { key: 'fc', label: '固定碳（FC）', def: 86.0, step: 0.1, min: 75, max: 92 },
    { key: 'ash', label: '灰分（A）', def: 12.5, step: 0.1, min: 5, max: 20 },
    { key: 'vm', label: '挥发分（V）', def: 1.2, step: 0.1, min: 0, max: 5 },
    { key: 's', label: '硫（S）', def: 0.7, step: 0.05, min: 0, max: 2 },
    { key: 'ash_sio2', label: 'SiO₂', def: 47.0, step: 0.5, min: 25, max: 65, sub: 'ash' },
    { key: 'ash_al2o3', label: 'Al₂O₃', def: 32.0, step: 0.5, min: 15, max: 45, sub: 'ash' },
    { key: 'ash_fe2o3', label: 'Fe₂O₃', def: 7.0, step: 0.5, min: 0, max: 25, sub: 'ash' },
    { key: 'ash_cao', label: 'CaO', def: 3.5, step: 0.1, min: 0, max: 15, sub: 'ash' },
    { key: 'ash_mgo', label: 'MgO', def: 1.2, step: 0.1, min: 0, max: 8, sub: 'ash' },
    { key: 'ash_base', label: 'K₂O+Na₂O（碱金属）', def: 1.2, step: 0.1, min: 0, max: 5, sub: 'ash' },
    { key: 'ash_so3', label: 'SO₃', def: 1.8, step: 0.1, min: 0, max: 8, sub: 'ash' },
  ],
  // 煤（炼焦煤）：焦炉入炉煤，工业分析 FC+V+A+M≈100%；元素碳 C 用于焦化过程碳核算；
  // 灰分组成供焦炭灰分溯源与炼焦配煤参考。
  coal: [
    { key: 'fc', label: '固定碳（FC）', def: 78.0, step: 0.1, min: 50, max: 90 },
    { key: 'vm', label: '挥发分（V）', def: 20.0, step: 0.1, min: 5, max: 40 },
    { key: 'ash', label: '灰分（A）', def: 9.0, step: 0.1, min: 3, max: 25 },
    { key: 'm', label: '水分（M）', def: 1.0, step: 0.1, min: 0, max: 10 },
    { key: 'c', label: '元素碳（C）', def: 82.0, step: 0.1, min: 60, max: 95 },
    { key: 'h', label: '氢（H）', def: 4.5, step: 0.1, min: 1, max: 8 },
    { key: 'n', label: '氮（N）', def: 1.3, step: 0.1, min: 0, max: 3 },
    { key: 's', label: '硫（S）', def: 0.5, step: 0.05, min: 0, max: 3 },
    { key: 'ash_sio2', label: 'SiO₂', def: 45.0, step: 0.5, min: 25, max: 65, sub: 'ash' },
    { key: 'ash_al2o3', label: 'Al₂O₃', def: 28.0, step: 0.5, min: 15, max: 45, sub: 'ash' },
    { key: 'ash_fe2o3', label: 'Fe₂O₃', def: 9.0, step: 0.5, min: 0, max: 25, sub: 'ash' },
    { key: 'ash_cao', label: 'CaO', def: 5.0, step: 0.1, min: 0, max: 15, sub: 'ash' },
    { key: 'ash_mgo', label: 'MgO', def: 1.5, step: 0.1, min: 0, max: 8, sub: 'ash' },
    { key: 'ash_base', label: 'K₂O+Na₂O（碱金属）', def: 1.2, step: 0.1, min: 0, max: 5, sub: 'ash' },
    { key: 'ash_so3', label: 'SO₃', def: 2.0, step: 0.1, min: 0, max: 8, sub: 'ash' },
  ],
  // 喷吹煤粉（PCI）：高炉风口喷吹，总量默认值与 tft.js TFT_CONFIG.pulverized_coal 对齐
  // （FC:0.81 / Celem:0.83 / H:0.04 / Ash:0.10 / H2O:0.05）；灰分组成直接参与
  // 炉渣碱度计算（煤灰随燃烧带上升进入炉渣）。
  pulverized_coal: [
    { key: 'fc', label: '固定碳（FC）', def: 75.0, step: 0.1, min: 50, max: 90 },
    { key: 'vm', label: '挥发分（V）', def: 10.0, step: 0.1, min: 5, max: 40 },
    { key: 'ash', label: '灰分（A）', def: 10.0, step: 0.1, min: 3, max: 25 },
    { key: 'h2o', label: '水分（H₂O）', def: 5.0, step: 0.1, min: 0, max: 15 },
    { key: 'c', label: '元素碳（C）', def: 83.0, step: 0.1, min: 60, max: 95 },
    { key: 'h', label: '氢（H）', def: 4.0, step: 0.1, min: 1, max: 8 },
    { key: 'n', label: '氮（N）', def: 1.2, step: 0.1, min: 0, max: 3 },
    { key: 's', label: '硫（S）', def: 0.5, step: 0.05, min: 0, max: 3 },
    { key: 'ash_sio2', label: 'SiO₂', def: 44.0, step: 0.5, min: 25, max: 65, sub: 'ash' },
    { key: 'ash_al2o3', label: 'Al₂O₃', def: 28.0, step: 0.5, min: 15, max: 45, sub: 'ash' },
    { key: 'ash_fe2o3', label: 'Fe₂O₃', def: 9.0, step: 0.5, min: 0, max: 25, sub: 'ash' },
    { key: 'ash_cao', label: 'CaO', def: 5.0, step: 0.1, min: 0, max: 15, sub: 'ash' },
    { key: 'ash_mgo', label: 'MgO', def: 1.5, step: 0.1, min: 0, max: 8, sub: 'ash' },
    { key: 'ash_base', label: 'K₂O+Na₂O（碱金属）', def: 1.3, step: 0.1, min: 0, max: 5, sub: 'ash' },
    { key: 'ash_so3', label: 'SO₃', def: 2.2, step: 0.1, min: 0, max: 8, sub: 'ash' },
  ],
}

// 读取物料成分值：优先取 materialOverrides[id].composition 覆盖值，否则取库默认值
export function compValue(overrides, matId, key, fallback = 0) {
  const c = overrides && overrides[matId] && overrides[matId].composition
  if (c && c[key] != null && c[key] !== '') return Number(c[key])
  const fs = COMP_DEFS[matId]
  const f = fs && fs.find((x) => x.key === key)
  return f && f.def != null ? f.def : fallback
}
