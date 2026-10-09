"""Skills 体系：系统内置能力单元。

- base.py        Skill 数据类与注册表
- builtin.py     内置 skills（查询设备/仿真/碳市场/排放因子）
- methodology.py 方法学 skills（碳核算 / 策略推荐等）
- registry.py    全局注册表单例
"""
from .base import Skill, SkillRegistry
from .registry import get_registry, init_registry

__all__ = ["Skill", "SkillRegistry", "get_registry", "init_registry"]
