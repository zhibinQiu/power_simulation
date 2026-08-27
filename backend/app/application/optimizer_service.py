"""AI 优化模型用例门面：对 API 层屏蔽 optimizers 模块的内部状态/训练调度细节。

- 训练上下文同步（流程模型变更自动重建训练任务）；
- 训练控制（start / stop / train / reset / 超参与设置）；
- 版本管理（archive / switch_version / ack）与结果应用（apply）。

优化器实现（Genetic/ParticleSwarm/Reinforcement）位于 ../optimizers.py，
其后台训练由 TrainingScheduler 常驻线程驱动；本服务负责用例编排与状态透出。
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from ..models import ProcessModel
from .. import optimizers


class OptimizerService:
    """AI 优化（GA / PSO / RL）用例门面。"""

    # ------------------------- 上下文与状态 -------------------------

    def set_context(self, model: Optional[ProcessModel],
                    factors: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """同步训练上下文；流程模型实质变化时自动重建各优化器。"""
        return optimizers.set_context(model, factors)

    def list_states(self) -> Dict[str, Any]:
        """AI 优化模型列表与训练状态（前端每数秒轮询）。"""
        return {"models": [o.state() for o in optimizers.all_optimizers()]}

    def get_state(self, oid: str, full: bool = True) -> Dict[str, Any]:
        """单个优化器完整状态；不存在时抛出 KeyError（由路由层转 404）。"""
        return self._require(oid).state(full=full)

    # ------------------------- 训练控制 -------------------------

    def start(self, oid: str) -> Dict[str, Any]:
        """开启自动训练：后台调度线程随实时传感器数据定时迭代。"""
        o = self._require(oid)
        if not o.ready:
            raise ValueError("训练上下文未就绪：请先同步流程模型")
        o.running = True
        o.next_train_at = time.time() + 1.0  # 开启后立即安排首次迭代
        o._log("自动训练已开启：后台定时训练，随实时传感器数据持续优化")
        return {"ok": True, **o.state()}

    def stop(self, oid: str) -> Dict[str, Any]:
        o = self._require(oid)
        o.running = False
        o._log("自动训练已暂停")
        return {"ok": True, **o.state()}

    def train(self, oid: str, steps: int = 1) -> Dict[str, Any]:
        """手动触发训练（steps 步），用于无自动调度时的即时迭代。"""
        o = self._require(oid)
        if not o.ready:
            raise ValueError("训练上下文未就绪")
        for _ in range(int(steps)):
            o.step()
        return {"ok": True, **o.state()}

    def reset(self, oid: str) -> Dict[str, Any]:
        o = self._require(oid)
        o.reset()
        return {"ok": True, **o.state()}

    def set_hyper(self, oid: str, patch: Dict[str, float]) -> Dict[str, Any]:
        o = self._require(oid)
        o.set_hyper(patch)
        return {"ok": True, **o.state()}

    # ------------------------- 设置与结果 -------------------------

    def set_settings(self, oid: str, patch: Dict[str, Any]) -> Dict[str, Any]:
        """更新控制与自训练设置：{auto_control?: bool, schedule?: {interval?, window?}}。"""
        o = self._require(oid)
        o.set_settings(patch)
        return {"ok": True, **o.state()}

    def apply(self, oid: str) -> Dict[str, Any]:
        """把「当前生效版本」的最优参数应用到流程（返回新模型 + 仿真结果）。"""
        o = self._require(oid)
        m2, sim = o.apply()
        return {"model": m2, "sim": sim, **o.state()}

    def archive(self, oid: str) -> Dict[str, Any]:
        """把当前最优参数保存为模型版本（仅优于当前版本才替换生效）。"""
        o = self._require(oid)
        r = o.archive(force=True)
        return {"ok": True, "promoted": r["promoted"], "version": r["version"], **o.state()}

    def switch_version(self, oid: str, version_id: str) -> Dict[str, Any]:
        """在历史模型版本间切换（旧版本保留，可随时切回）。"""
        o = self._require(oid)
        o.switch_version(version_id)
        return {"ok": True, **o.state()}

    def ack(self, oid: str) -> Dict[str, Any]:
        """确认提醒：清除手动调优提醒 / 自动控制待下发标记。"""
        o = self._require(oid)
        o.ack()
        return {"ok": True, **o.state()}

    # ------------------------- 内部 -------------------------

    @staticmethod
    def _require(oid: str) -> optimizers.OptimizerBase:
        o = optimizers.get_optimizer(oid)
        if o is None:
            raise KeyError(oid)
        return o


# 模块级单例
optimizer_service = OptimizerService()
