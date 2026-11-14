from fastapi import APIRouter

from app.schemas.targets import TargetsResponse
from app.science.targets import list_target_presets

router = APIRouter(tags=["targets"])


@router.get("/targets", response_model=TargetsResponse)
async def get_targets() -> TargetsResponse:
    return TargetsResponse(targets=list_target_presets())
