"""种子本体：钢铁能碳一体化领域语义层（概念 / 关系 / 规则）。

内置数据（builtin=True）仅可编辑不可删除；用户可在其上扩展。
"""
from __future__ import annotations

from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# 概念 Concepts（category: 工序/设备/物料/指标/能源/排放/其他）
# ---------------------------------------------------------------------------
SEED_CONCEPTS: List[Dict[str, Any]] = [
    # 工序
    {"name": "烧结", "category": "工序", "description": "铁矿石粉造块工序，将矿粉烧结成烧结矿供高炉使用",
     "aliases": ["烧结工序"], "keywords": ["烧结"]},
    {"name": "炼焦", "category": "工序", "description": "煤在隔绝空气下干馏成焦炭的工序，产出焦炭与焦炉煤气",
     "aliases": ["焦化工序"], "keywords": ["炼焦", "焦化"]},
    {"name": "高炉炼铁", "category": "工序", "description": "用焦炭还原铁矿石冶炼生铁的工序，是高炉-转炉长流程核心工序",
     "aliases": ["炼铁工序", "高炉工序"], "keywords": ["炼铁", "高炉"]},
    {"name": "转炉炼钢", "category": "工序", "description": "以铁水为原料，通过顶吹/底吹氧气去除杂质冶炼粗钢的工序",
     "aliases": ["炼钢工序", "转炉工序"], "keywords": ["炼钢", "转炉"]},
    {"name": "连铸", "category": "工序", "description": "将钢水连续浇铸成钢坯的工序",
     "aliases": ["连铸工序"], "keywords": ["连铸"]},
    {"name": "热轧", "category": "工序", "description": "钢坯加热后轧制成板材/带材/型材的工序",
     "aliases": ["热轧工序"], "keywords": ["热轧"]},
    {"name": "冷轧", "category": "工序", "description": "热轧卷在常温下进一步轧薄、改善表面与性能的工序",
     "aliases": ["冷轧工序"], "keywords": ["冷轧"]},
    {"name": "电炉炼钢", "category": "工序", "description": "以废钢为原料、电弧加热冶炼的短流程炼钢工序",
     "aliases": ["电弧炉工序", "短流程"], "keywords": ["电炉", "电弧炉"]},
    # 设备
    {"name": "高炉本体", "category": "设备", "description": "冶炼生铁的核心竖炉设备，炉容决定产能",
     "aliases": ["高炉"], "keywords": ["高炉本体"]},
    {"name": "热风炉", "category": "设备", "description": "为高炉鼓入高温热风的蓄热式换热设备",
     "aliases": [], "keywords": ["热风炉"]},
    {"name": "喷煤系统", "category": "设备", "description": "向高炉喷吹煤粉以部分替代焦炭的节能设备",
     "aliases": ["煤粉喷吹"], "keywords": ["喷煤"]},
    {"name": "转炉", "category": "设备", "description": "顶吹/底吹氧气炼钢的容器设备",
     "aliases": ["氧气顶吹转炉"], "keywords": ["转炉设备"]},
    {"name": "连铸机", "category": "设备", "description": "钢水连铸成坯的核心设备",
     "aliases": [], "keywords": ["连铸机"]},
    {"name": "加热炉", "category": "设备", "description": "热轧前将钢坯加热至轧制温度的炉子，消耗煤气/电力",
     "aliases": ["轧钢加热炉"], "keywords": ["加热炉"]},
    {"name": "轧机", "category": "设备", "description": "将钢坯/带钢轧制成形的核心设备",
     "aliases": [], "keywords": ["轧机"]},
    # 物料
    {"name": "焦炭", "category": "物料", "description": "高炉主要还原剂与热源，由炼焦工序产出",
     "aliases": ["冶金焦"], "keywords": ["焦炭"]},
    {"name": "铁矿石", "category": "物料", "description": "高炉炼铁的主要原料（含烧结矿/球团矿）",
     "aliases": ["矿粉", "烧结矿", "球团"], "keywords": ["铁矿石", "矿石"]},
    {"name": "喷吹煤", "category": "物料", "description": "经喷煤系统喷入高炉的煤粉，部分替代焦炭",
     "aliases": ["煤粉"], "keywords": ["喷吹煤"]},
    {"name": "废钢", "category": "物料", "description": "电炉/转炉炼钢的补充原料",
     "aliases": [], "keywords": ["废钢"]},
    {"name": "生铁", "category": "物料", "description": "高炉冶炼产物，转炉炼钢主要原料",
     "aliases": ["铁水"], "keywords": ["生铁", "铁水"]},
    {"name": "粗钢", "category": "物料", "description": "转炉/电炉冶炼出的钢水浇铸产物，钢材生产的中间产品",
     "aliases": ["钢水"], "keywords": ["粗钢", "钢水"]},
    # 指标
    {"name": "焦比", "category": "指标", "description": "冶炼单位铁水消耗的焦炭量，焦比=焦炭消耗量/铁水产量，单位 kg/t",
     "aliases": ["焦炭比"], "keywords": ["焦比"],
     "properties": {"unit": "kg/t", "formula": "焦炭消耗量 / 铁水产量"}},
    {"name": "燃料比", "category": "指标", "description": "冶炼单位铁水消耗的焦炭与喷吹煤折合总量，单位 kg/t",
     "aliases": [], "keywords": ["燃料比"],
     "properties": {"unit": "kg/t", "formula": "(焦炭消耗量 + 喷吹煤消耗量) / 铁水产量"}},
    {"name": "综合能耗", "category": "指标", "description": "吨钢（或全厂）综合能源消耗，折标准煤，单位 kgce/t",
     "aliases": ["吨钢综合能耗"], "keywords": ["综合能耗", "能耗"],
     "properties": {"unit": "kgce/t"}},
    {"name": "工序能耗", "category": "指标", "description": "某工序单位产品的能源消耗，如高炉工序能耗",
     "aliases": [], "keywords": ["工序能耗"],
     "properties": {"unit": "kgce/t"}},
    {"name": "碳排放强度", "category": "指标", "description": "单位粗钢产品的 CO2 排放量，强度=总碳排放/粗钢产量，单位 tCO2/t",
     "aliases": ["碳强度", "吨钢碳排放"], "keywords": ["碳排放强度", "碳强度"],
     "properties": {"unit": "tCO2/t", "formula": "总碳排放 / 粗钢产量"}},
    {"name": "碳排放总量", "category": "指标", "description": "一定时期内全厂（或某工序）CO2 排放总量，单位 tCO2",
     "aliases": ["总排放"], "keywords": ["碳排放总量", "总排放"],
     "properties": {"unit": "tCO2"}},
    {"name": "电耗", "category": "指标", "description": "单位产品电力消耗，如电炉工序电耗，单位 kWh/t",
     "aliases": [], "keywords": ["电耗"],
     "properties": {"unit": "kWh/t"}},
    # 能源
    {"name": "电力", "category": "能源", "description": "外购电力，间接碳排放的主要来源",
     "aliases": ["外购电", "电"], "keywords": ["电力", "外购电"]},
    {"name": "高炉煤气", "category": "能源", "description": "高炉副产煤气，热值较低，可回收利用",
     "aliases": ["BFG"], "keywords": ["高炉煤气"]},
    {"name": "转炉煤气", "category": "能源", "description": "转炉副产煤气，热值高，可回收利用",
     "aliases": ["LDG"], "keywords": ["转炉煤气"]},
    {"name": "焦炉煤气", "category": "能源", "description": "炼焦副产煤气，热值高，广泛用于加热炉",
     "aliases": ["COG"], "keywords": ["焦炉煤气"]},
    # 排放
    {"name": "CO2", "category": "排放", "description": "二氧化碳，钢铁行业最主要的温室气体排放物",
     "aliases": ["二氧化碳", "碳排放"], "keywords": ["co2", "二氧化碳"]},
    {"name": "SO2", "category": "排放", "description": "二氧化硫，烧结/焦化工序主要大气污染物",
     "aliases": [], "keywords": ["so2", "二氧化硫"]},
    {"name": "NOx", "category": "排放", "description": "氮氧化物，燃烧过程产生的污染物",
     "aliases": [], "keywords": ["nox", "氮氧化物"]},
]

# ---------------------------------------------------------------------------
# 关系 Relations（source/target 为概念 name，存储时解析为 id）
# ---------------------------------------------------------------------------
SEED_RELATIONS: List[Dict[str, Any]] = [
    # 属于（工序包含设备）
    {"source": "高炉本体", "target": "高炉炼铁", "type": "属于", "description": "高炉本体是高炉炼铁工序的核心设备"},
    {"source": "热风炉", "target": "高炉炼铁", "type": "属于", "description": "热风炉是高炉炼铁工序的配套设备"},
    {"source": "喷煤系统", "target": "高炉炼铁", "type": "属于", "description": "喷煤系统属于高炉炼铁工序"},
    {"source": "转炉", "target": "转炉炼钢", "type": "属于", "description": "转炉是转炉炼钢工序的核心设备"},
    {"source": "连铸机", "target": "连铸", "type": "属于", "description": "连铸机是连铸工序的核心设备"},
    {"source": "加热炉", "target": "热轧", "type": "属于", "description": "加热炉属于热轧工序"},
    {"source": "轧机", "target": "热轧", "type": "属于", "description": "轧机属于热轧工序"},
    # 包含（工序包含工序/指标）
    {"source": "高炉炼铁", "target": "焦比", "type": "包含", "description": "高炉炼铁工序的关键指标包括焦比"},
    {"source": "高炉炼铁", "target": "燃料比", "type": "包含", "description": "高炉炼铁工序的关键指标包括燃料比"},
    {"source": "转炉炼钢", "target": "电耗", "type": "包含", "description": "转炉炼钢涉及电耗指标"},
    {"source": "电炉炼钢", "target": "电耗", "type": "包含", "description": "电炉炼钢的关键指标是电耗"},
    # 消耗 / 使用
    {"source": "高炉炼铁", "target": "焦炭", "type": "消耗", "description": "高炉炼铁消耗焦炭作为还原剂与热源"},
    {"source": "高炉炼铁", "target": "铁矿石", "type": "消耗", "description": "高炉炼铁消耗铁矿石"},
    {"source": "高炉炼铁", "target": "喷吹煤", "type": "消耗", "description": "高炉炼铁喷吹煤粉以替代部分焦炭"},
    {"source": "高炉炼铁", "target": "电力", "type": "消耗", "description": "高炉炼铁消耗电力（鼓风/上料等）"},
    {"source": "电炉炼钢", "target": "电力", "type": "消耗", "description": "电炉炼钢主要消耗电力"},
    {"source": "电炉炼钢", "target": "废钢", "type": "消耗", "description": "电炉炼钢以废钢为主要原料"},
    {"source": "热轧", "target": "焦炉煤气", "type": "消耗", "description": "热轧加热炉消耗焦炉煤气"},
    {"source": "热轧", "target": "电力", "type": "消耗", "description": "热轧工序轧机消耗电力"},
    # 产出
    {"source": "高炉炼铁", "target": "生铁", "type": "产出", "description": "高炉炼铁产出生铁（铁水）"},
    {"source": "转炉炼钢", "target": "粗钢", "type": "产出", "description": "转炉炼钢产出粗钢"},
    {"source": "炼焦", "target": "焦炭", "type": "产出", "description": "炼焦工序产出焦炭"},
    {"source": "炼焦", "target": "焦炉煤气", "type": "产出", "description": "炼焦工序副产焦炉煤气"},
    {"source": "高炉炼铁", "target": "高炉煤气", "type": "产出", "description": "高炉副产高炉煤气"},
    {"source": "转炉炼钢", "target": "转炉煤气", "type": "产出", "description": "转炉副产转炉煤气"},
    # 排放
    {"source": "高炉炼铁", "target": "CO2", "type": "排放", "description": "高炉炼铁是钢铁厂最大 CO2 排放源"},
    {"source": "烧结", "target": "SO2", "type": "排放", "description": "烧结工序排放 SO2"},
    {"source": "烧结", "target": "CO2", "type": "排放", "description": "烧结工序排放 CO2"},
    {"source": "炼焦", "target": "SO2", "type": "排放", "description": "炼焦工序排放 SO2"},
    {"source": "转炉炼钢", "target": "CO2", "type": "排放", "description": "转炉炼钢排放 CO2"},
    {"source": "热轧", "target": "CO2", "type": "排放", "description": "热轧加热炉燃烧煤气排放 CO2"},
    # 影响
    {"source": "焦比", "target": "碳排放强度", "type": "影响", "description": "焦比越高，炼铁工序碳排放强度越高"},
    {"source": "燃料比", "target": "综合能耗", "type": "影响", "description": "燃料比直接影响炼铁工序能耗"},
    {"source": "喷吹煤", "target": "焦比", "type": "影响", "description": "提高喷煤比可降低焦比"},
    {"source": "高炉煤气", "target": "综合能耗", "type": "影响", "description": "副产煤气回收利用可降低全厂综合能耗"},
]

# ---------------------------------------------------------------------------
# 规则 Rules（keywords 命中触发；can_answer=True 可直接回答）
# ---------------------------------------------------------------------------
SEED_RULES: List[Dict[str, Any]] = [
    {
        "name": "焦比定义与计算",
        "description": "焦比是冶炼单位铁水消耗的焦炭量，计算公式：焦比 = 焦炭消耗量 / 铁水产量。焦比越低代表炼铁燃料效率越高。",
        "keywords": ["焦比", "焦炭比", "焦炭消耗", "怎么算焦比", "如何计算焦比"],
        "if_question": "用户询问焦比的定义、计算方式或数值水平",
        "conclusion": "焦比 = 焦炭消耗量 / 铁水产量（kg/t），是衡量炼铁燃料效率的核心指标。",
        "answer_template": "焦比是炼铁工序的关键经济指标，表示冶炼 1 吨铁水消耗的焦炭量。\n"
                           "计算公式：**焦比 = 焦炭消耗量 ÷ 铁水产量**，单位 kg/t。\n"
                           "焦比越低，说明喷煤、精料等降焦措施效果越好，燃料成本与碳排放也越低。",
        "can_answer": True,
        "source": "seed",
    },
    {
        "name": "碳排放强度定义",
        "description": "碳排放强度 = 总碳排放 / 粗钢产量（tCO2/t），是衡量吨钢碳排放水平的核心指标，可直接用实时数据计算。",
        "keywords": ["碳排放强度", "碳强度", "吨钢碳排放", "怎么算碳排放", "如何计算碳强度"],
        "if_question": "用户询问碳排放强度、吨钢碳排放的定义或计算",
        "conclusion": "碳排放强度 = 总碳排放 / 粗钢产量（tCO2/t）。",
        "answer_template": "碳排放强度表示每生产 1 吨粗钢产生的 CO2 排放量：\n"
                           "**碳排放强度 = 总碳排放 ÷ 粗钢产量**，单位 tCO2/t。\n"
                           "若要查看当前实时值，可调用实时设备/仿真技能获取最新数据后计算。",
        "can_answer": True,
        "source": "seed",
    },
    {
        "name": "综合能耗与工序能耗",
        "description": "综合能耗是全厂/吨钢总能源消耗（kgce/t）；工序能耗是某工序单位产品的能耗。高炉炼铁、烧结是能耗与碳排大户。",
        "keywords": ["综合能耗", "工序能耗", "能耗", "吨钢能耗", "能耗构成"],
        "if_question": "用户询问综合能耗/工序能耗的定义或哪道工序能耗高",
        "conclusion": "综合能耗为吨钢总能耗（kgce/t）；长流程中高炉炼铁与烧结工序能耗占比最高。",
        "answer_template": "综合能耗指全厂吨钢能源消耗总量（kgce/t）；工序能耗指单个工序单位产品的能耗。\n"
                           "在长流程（高炉-转炉）中，**高炉炼铁、烧结**的能耗与碳排放占比最高。\n"
                           "可调用「仿真」或「实时设备」技能获取各工序能耗与排放数据。",
        "can_answer": True,
        "source": "seed",
    },
    {
        "name": "降碳路径（喷煤替代焦炭）",
        "description": "提高喷煤比以部分替代焦炭（焦炭碳排放系数高于煤粉），可降低焦比与碳排放强度。",
        "keywords": ["降碳", "减排", "降焦比", "怎么降碳", "如何减排", "低碳"],
        "if_question": "用户询问如何降低碳排放/焦比",
        "conclusion": "提高喷煤比替代焦炭、提升副产煤气回收利用率是长流程主要降碳路径。",
        "answer_template": "钢铁长流程主要降碳路径包括：\n"
                           "1. **提高喷煤比**：用煤粉部分替代焦炭，降低焦比与燃料成本；\n"
                           "2. **副产煤气回收利用**：高炉/转炉/焦炉煤气回用于加热炉，减少外购能源；\n"
                           "3. **废钢短流程**：电炉炼钢（废钢+电）碳排放强度远低于长流程；\n"
                           "4. **电气化与绿电**：提升电炉比例、采购绿电降低间接排放。",
        "can_answer": True,
        "source": "seed",
    },
    {
        "name": "设备能耗构成",
        "description": "转炉炼钢与电炉炼钢的主要能耗均为电力；热轧主要消耗煤气（加热炉）与电力（轧机）。",
        "keywords": ["电耗", "转炉能耗", "电炉能耗", "热轧能耗", "哪个设备耗电"],
        "if_question": "用户询问设备/工序的能耗（电耗）构成",
        "conclusion": "电炉/转炉以电力为主，热轧为煤气+电力。",
        "answer_template": "各工序主要能耗构成：\n"
                           "- **电炉炼钢**：以电力为主（电弧加热），电耗指标高；\n"
                           "- **转炉炼钢**：以电力+氧气为主，电耗指标相对低；\n"
                           "- **热轧**：加热炉消耗煤气（焦炉/高炉/转炉煤气），轧机消耗电力。",
        "can_answer": True,
        "source": "seed",
    },
    {
        "name": "副产煤气回收",
        "description": "高炉煤气（BFG）、转炉煤气（LDG）、焦炉煤气（COG）为钢铁厂三大副产煤气，回收利用可显著降低能耗与外购能源。",
        "keywords": ["煤气", "副产煤气", "回收", "bfg", "ldg", "cog"],
        "if_question": "用户询问副产煤气种类或回收利用",
        "conclusion": "三大副产煤气：BFG（高炉）、LDG（转炉）、COG（焦炉），回收利用是节能关键。",
        "answer_template": "钢铁厂三大副产煤气：\n"
                           "1. **高炉煤气（BFG）**：热值低、产量大，高炉工序副产；\n"
                           "2. **转炉煤气（LDG）**：热值高，转炉工序副产；\n"
                           "3. **焦炉煤气（COG）**：热值最高，炼焦工序副产。\n"
                           "回收利用于加热炉等可替代外购燃料，显著降低全厂综合能耗与成本。",
        "can_answer": True,
        "source": "seed",
    },
    {
        "name": "长流程 vs 短流程",
        "description": "长流程（高炉-转炉）以铁矿石为原料碳排放高；短流程（电炉-废钢）碳排放约为长流程的 1/3，是低碳转型方向。",
        "keywords": ["长流程", "短流程", "电炉", "转炉", "碳排放对比"],
        "if_question": "用户询问长流程/短流程的碳排放对比",
        "conclusion": "短流程（电炉+废钢）吨钢碳排放约为长流程（高炉+转炉）的 1/3。",
        "answer_template": "钢铁两种主要工艺流程碳排放差异很大：\n"
                           "1. **长流程（高炉-转炉）**：以铁矿石为原料，焦炭还原过程排放大量 CO2，吨钢碳排放高；\n"
                           "2. **短流程（电炉-废钢）**：以废钢为原料、电弧加热，吨钢碳排放约为长流程的 1/3。\n"
                           "提高电炉钢比例（废钢资源化）是钢铁行业碳达峰的关键路径。",
        "can_answer": True,
        "source": "seed",
    },
    {
        "name": "工序排放源定位",
        "description": "识别各工序主要排放源：高炉炼铁排放 CO2 最多；烧结排放 SO2 与 CO2；炼焦排放 SO2；转炉/热轧排放 CO2。",
        "keywords": ["排放源", "哪个工序排放", "co2 排放", "污染来源"],
        "if_question": "用户询问哪道工序/设备排放最多或排放源构成",
        "conclusion": "高炉炼铁是全厂最大 CO2 排放源；烧结/焦化是 SO2 主要来源。",
        "answer_template": "各工序主要排放源：\n"
                           "- **CO2**：高炉炼铁（最大）、烧结、转炉炼钢、热轧（加热炉）；\n"
                           "- **SO2**：烧结、炼焦；\n"
                           "- **NOx**：各类燃烧过程（加热炉、烧结机头）。\n"
                           "如需精确数值，可调用实时设备/仿真技能查看各工序当前排放。",
        "can_answer": True,
        "source": "seed",
    },
]
