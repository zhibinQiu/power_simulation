"""自然语言策略解析器。

把中文/英文策略文本解析成结构化操作(ParsedOp)列表。
采用"关键词 + 正则 + 意图模板"的确定性解析（无需外部 LLM，离线可用），
同时保留 `llm_parse` 扩展点：若设置 OPENAI_API_KEY 可替换为大模型解析。

解析能力覆盖：
  - 改工序类型：把 高炉 改为 氢冶金
  - 改参数(绝对值/百分比/相对)：焦比 降到 300 / 喷煤 减少 20%
  - 增删工序：新增 一座 电炉 / 删除 转炉
  - 应用技术：应用 碳捕集 / 余热回收 / 富氢喷吹
"""
from __future__ import annotations

import copy
import re
from typing import Dict, List, Optional

from .models import ParseResult, ParsedOp
from .carbon_engine import DEFAULT_PARAMS

# 工序类型关键词 -> type id
UNIT_KEYWORDS: Dict[str, List[str]] = {
    "blast_furnace": ["高炉", "blast furnace", "bf"],
    "bof": ["转炉", "bof", "氧气转炉", "顶吹"],
    "eaf": ["电炉", "电弧炉", "eaf"],
    "hydrogen_bf": ["氢冶金", "氢基", "h2", "hybf", "氢还原", "氢高炉"],
    "h2_dri": ["氢基直接还原", "氢直接还原", "h2-dri", "绿氢竖炉", "氢竖炉", "直接还原竖炉"],
    "dri_midrex": ["直接还原", "dri", "midrex", "竖炉", "直接还原铁"],
    "smelting_reduction": ["熔融还原", "corex", "finex", "非焦冶", "非焦"],
    "biochar_injection": ["生物质", "biochar", "生物碳", "生物质喷吹", "生物质碳"],
    "sinter_plant": ["烧结", "烧结机", "sinter"],
    "coke_oven": ["焦炉", "焦炭", "coke"],
    "reheating_furnace": ["加热炉", "reheating", "均热炉"],
    "ladle_furnace": ["精炼", "lf", "精炼炉", "ladle"],
    "rh_vacuum": ["rh", "真空精炼", "rh精炼", "rh真空"],
    "vd_vacuum": ["vd", "真空脱气", "vd脱气", "真空处理"],
    "aod": ["aod", "不锈钢精炼", "aod精炼"],
    "caster": ["连铸", "铸机", "caster"],
    "ingot_casting": ["模铸", "铸锭", "ingot"],
    "rolling_mill": ["轧机", "轧钢", "热轧", "rolling", "热轧机"],
    "cold_rolling": ["冷轧", "cold rolling", "冷连轧", "冷轧机"],
    "pelletizing": ["球团", "pellet"],
}

# 参数关键词 -> param key
PARAM_KEYWORDS: Dict[str, List[str]] = {
    "coke_rate": ["焦比", "焦炭比", "焦炭负荷", "coke rate"],
    "coal_inj": ["喷煤", "喷吹", "煤比", "pci", "coal injection"],
    "coal_rate": ["煤比", "入炉煤", "非焦煤", "coal rate"],
    "hot_metal": ["铁水", "铁水产量", "hot metal", "铁水产量"],
    "hot_metal_in": ["铁水入炉", "入炉铁水"],
    "scrap": ["废钢", "scrap"],
    "dri": ["dri", "直接还原铁"],
    "dri_out": ["dri产量", "竖炉产量", "直接还原产量"],
    "pellet_rate": ["球团矿量", "球团量", "pellet rate"],
    "ore_rate": ["矿量", "矿石", "ore", "原料矿"],
    "biomass_rate": ["生物质量", "生物质碳量", "biochar rate"],
    "electricity": ["电耗", "用电量", "电力", "electricity", "耗电"],
    "h2_rate": ["氢耗", "氢气", "h2 rate", "用氢"],
    "fuel_rate": ["燃料", "燃料比", "sinter fuel"],
    "ng_rate": ["天然气", "ng", "燃气", "煤气"],
    "steel_in": ["钢水量", "钢水", "steel in"],
    "flux": ["熔剂", "石灰", "flux"],
    "capture_rate": ["捕集率", "capture rate"],
}

# 技术关键词 -> tech id
TECH_KEYWORDS: Dict[str, List[str]] = {
    "ccs": ["碳捕集", "ccs", "co2捕集", "碳捕集利用", "捕集"],
    "waste_heat": ["余热回收", "余热", "waste heat", "废热"],
    "h2_inj": ["氢喷吹", "富氢", "喷氢", "富氢喷吹", "h2 inj"],
}

NUM = r"([-+]?\d+(?:\.\d+)?)"

# 工序名上下文可选匹配（用于"把 X 改为 Y" / "X 的 参数" 中捕获被操作工序名）
TYPE_ALT = (
    "高炉|转炉|电炉|氢冶金|氢基直接还原|直接还原|直接还原铁|熔融还原|生物质|烧结|焦炉|加热炉|"
    "精炼|rh|rh真空|vd|vd脱气|aod|aod精炼|连铸|模铸|轧机|冷轧|冷连轧|球团|"
    "bf|bof|eaf|h2|h2-dri|dri|midrex|corex|finex|sinter|coke|lf|caster|rolling|pellet|"
    "热轧|氢竖炉|绿氢竖炉|竖炉"
)


def _find_keyword(table: Dict[str, List[str]], text: str) -> Optional[str]:
    """在关键词表中查找首个匹配的 key（大小写不敏感）。"""
    low = text.lower()
    for tid, kws in table.items():
        for kw in kws:
            if kw.lower() in low:
                return tid
    return None


def parse_strategy(text: str, model_units: Optional[List[dict]] = None) -> ParseResult:
    """把策略文本解析为操作列表。"""
    raw = text.strip()
    ops: List[ParsedOp] = []
    understood: List[str] = []
    warnings: List[str] = []

    # 1) 替换工序类型：'(把|将|让) X 改为/切换为 Y'
    for m in re.finditer(
        r"(?:把|将|让|把该|使)?\s*([0-9]*\s*[#号]?\s*[一-龥a-zA-Z]*?"
        r"(?:" + TYPE_ALT + r")?)"
        r"\s*(?:改为|切换[为成]?|换成|变为|替代为|改成|升级为|替换为|转成)\s*([一-龥a-zA-Z0-9]+)",
        raw, re.IGNORECASE):
        target_txt, to_txt = m.group(1).strip(), m.group(2).strip()
        to_type = _find_keyword(UNIT_KEYWORDS, to_txt)
        if to_type is None:
            warnings.append(f"无法识别目标工艺类型：'{to_txt}'")
            continue
        ops.append(ParsedOp(action="replace_type", target=target_txt or None,
                            to_type=to_type, note=f"将 [{target_txt or '匹配的工序'}] 改为 {to_type}"))
        understood.append(f"将 {target_txt or '匹配的工序'} 切换为 {to_type}")

    # 2) 增删工序
    for m in re.finditer(r"(新增|增加|添加|建设|扩建|上\s*一?\s*座|新建)\s*([0-9]*)?\s*([一-龥a-zA-Z]+)", raw):
        count = int(m.group(2)) if m.group(2) else 1
        ttype = _find_keyword(UNIT_KEYWORDS, m.group(3))
        if ttype is None:
            warnings.append(f"无法识别要新增的工序：'{m.group(3)}'")
            continue
        ops.append(ParsedOp(action="add_unit", to_type=ttype, count=count,
                            note=f"新增 {count} 座 {ttype}"))
        understood.append(f"新增 {count} 座 {ttype}")
    for m in re.finditer(r"(删除|移除|去掉|关闭|停掉|停用)\s*([0-9]*\s*[#号]?\s*[一-龥a-zA-Z]+)", raw):
        target = m.group(2).strip()
        ops.append(ParsedOp(action="remove_unit", target=target, note=f"删除 {target}"))
        understood.append(f"删除 {target}")

    # 3) 应用技术
    for m in re.finditer(r"(应用|采用|加装|部署|使用|开启|投用)\s*([一-龥a-zA-Z]+?)(?=技术|工艺|系统|装置|$|，|,|。|；|;)", raw):
        tech = _find_keyword(TECH_KEYWORDS, m.group(2))
        if tech is None:
            continue
        ops.append(ParsedOp(action="apply_tech", tech=tech, note=f"应用 {tech} 技术"))
        understood.append(f"应用 {tech} 技术")

    # 4) 参数调整（绝对值 / 百分比 / 相对）。需包含工序上下文或全局参数。
    #    模式A：'X 的 Y 降到/设为 V'
    #    模式B：'Y 降低/提高 P%'（全局作用于同类型工序）
    #    模式C：'Y 从 A 降到 B'
    param_pat = re.compile(
        r"([0-9]*\s*[#号]?\s*[一-龥a-zA-Z]*?"
        r"(?:" + TYPE_ALT + r")?)"
        r"\s*的?\s*(" + "|".join(k for kws in PARAM_KEYWORDS.values() for k in kws) + r")"
        r"\s*(?:从\s*" + NUM + r"\s*)?(?:降到|降至|降低到|降到|设为|设置为|改为|调整为|提高到|提升到|增至|增加至|提升到|限制为|控制为)\s*" + NUM,
        re.IGNORECASE)
    for m in param_pat.finditer(raw):
        target_txt = m.group(1).strip()
        pkey = _find_keyword(PARAM_KEYWORDS, m.group(2))
        val = float(m.group(4)) if m.group(4) else None
        if pkey is None or val is None:
            continue
        ttype = _find_keyword(UNIT_KEYWORDS, target_txt) if target_txt else None
        ops.append(ParsedOp(action="set_param", target=target_txt or ttype,
                            param=pkey, value=val, mode="absolute",
                            note=f"{target_txt or '全局'} 的 {pkey} 设为 {val}"))
        understood.append(f"{target_txt or '全局'} 的 {pkey} = {val}")

    # 模式C2：'Y 降低/提高 P%'
    pct_pat = re.compile(
        r"(" + "|".join(k for kws in PARAM_KEYWORDS.values() for k in kws) + r")"
        r"\s*(?:降低|减少|下降|下调|削减|压缩|提高|增加|提升|上调|增大)\s*" + NUM + r"\s*%?",
        re.IGNORECASE)
    for m in pct_pat.finditer(raw):
        pkey = _find_keyword(PARAM_KEYWORDS, m.group(1))
        val = float(m.group(2))
        # 由"降低/减少"判断方向
        direction = -1 if re.search(r"降低|减少|下降|下调|削减|压缩", m.group(0)) else 1
        ops.append(ParsedOp(action="set_param", param=pkey, value=val * direction,
                            mode="relative", note=f"{pkey} 相对{'提高' if direction>0 else '降低'} {abs(val)}%"))
        understood.append(f"{pkey} 相对{'提高' if direction>0 else '降低'} {val}%")

    if not ops:
        warnings.append("未识别出任何可执行的策略操作，请尝试包含工艺名称、参数或技术关键词。")

    confidence = min(1.0, 0.4 + 0.15 * len(ops)) if ops else 0.0
    return ParseResult(raw_text=raw, understood=understood, ops=ops,
                       confidence=round(confidence, 2), warnings=warnings)


def apply_ops(model, ops: List[ParsedOp]):
    """把解析出的操作应用到流程模型上，返回新的 ProcessModel（不修改原对象）。"""
    new = copy.deepcopy(model)
    # 单位名 -> id 解析
    name_index = {u.name.lower(): u.id for u in new.units}
    type_index = {}
    for u in new.units:
        type_index.setdefault(u.type, []).append(u.id)

    def resolve_target(op: ParsedOp) -> Optional[str]:
        t = (op.target or "").strip().lower()
        if not t:
            return None
        if t in name_index:
            return name_index[t]
        for nm, uid in name_index.items():
            if t in nm or nm in t:
                return uid
        # 按类型匹配（取第一个）
        tt = _find_keyword(UNIT_KEYWORDS, t)
        if tt and tt in type_index:
            return type_index[tt][0]
        return None

    for op in ops:
        if op.action == "replace_type":
            uid = resolve_target(op)
            if not uid:
                # 找不到精确目标：按类型匹配，替换同类型第一个工序
                tt = _find_keyword(UNIT_KEYWORDS, op.target or "")
                uid = type_index.get(tt, [None])[0] if tt else None
            if uid:
                for u in new.units:
                    if u.id == uid:
                        u.type = op.to_type
                        break
        elif op.action == "set_param":
            uid = resolve_target(op)
            targets = [uid] if uid else None
            if targets is None:
                # 全局：作用于所有含该参数的工序（按类型匹配 target）
                tt = _find_keyword(UNIT_KEYWORDS, op.target or "") if op.target else None
                targets = type_index.get(tt, []) if tt else [u.id for u in new.units]
            for u in new.units:
                if u.id in targets:
                    if op.mode == "absolute":
                        u.params[op.param] = op.value
                    else:  # relative
                        base = u.params.get(op.param, _global_default(op.param))
                        factor = (1 + op.value / 100.0) if op.mode == "relative" else 1.0
                        # relative 已带方向
                        u.params[op.param] = round(base * factor, 2)
        elif op.action == "add_unit":
            from . import presets as P
            # 同类型计数用于命名（高炉、高炉2、高炉3 …）；布局序号用全流程单元数
            base = P.default_unit(op.to_type, len(new.units), sum(1 for u in new.units if u.type == op.to_type))
            new.units.append(base)
        elif op.action == "remove_unit":
            uid = resolve_target(op)
            if uid:
                new.units = [u for u in new.units if u.id != uid]
                new.flows = [f for f in new.flows if f.from_unit != uid and f.to_unit != uid]
        elif op.action == "apply_tech":
            uid = resolve_target(op)
            targets = [uid] if uid else [u.id for u in new.units]
            for u in new.units:
                if u.id in targets and op.tech not in u.techs:
                    u.techs.append(op.tech)
    return new


def _global_default(param: str) -> float:
    for d in DEFAULT_PARAMS.values():
        if param in d:
            return d[param]
    return 0.0
