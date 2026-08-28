"""平台激活 API：查询激活状态 / 提交激活码激活。"""
from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .. import license as license_mod

router = APIRouter(prefix="/api/license", tags=["license"])


class ActivateRequest(BaseModel):
    code: str = Field(..., description="激活码，格式 NENG-XXXX-XXXX-XXXX-XXXX")


class ActivateResponse(BaseModel):
    ok: bool
    activated: bool
    message: str
    status: dict


@router.get("/status")
def license_status() -> dict:
    """查询平台激活状态。"""
    return license_mod.get_status()


@router.post("/activate", response_model=ActivateResponse)
def license_activate(req: ActivateRequest) -> ActivateResponse:
    """提交激活码激活平台。"""
    ok, message, status = license_mod.activate(req.code)
    return ActivateResponse(ok=ok, activated=status.get("activated", False),
                            message=message, status=status)
