from fastapi import APIRouter, Depends

from app.api.deps import AppContainer, get_container
from app.schemas.common import ServiceStatus

router = APIRouter(tags=["health"])


@router.get("/health", response_model=dict[str, ServiceStatus])
async def health_check(
    container: AppContainer = Depends(get_container),
) -> dict[str, ServiceStatus]:
    db_status = await container.db.check_health()
    redis_status = (
        ServiceStatus(status="up")
        if container.cache.redis_available()
        else ServiceStatus(status="unavailable", detail="Using atomic disk fallback")
    )
    llm_mode = container.settings.llm_provider
    if llm_mode == "openai_compatible" and container.settings.llm_api_key.strip():
        llm_status = ServiceStatus(status="up", detail=container.settings.llm_model or "configured")
    elif llm_mode == "fake":
        llm_status = ServiceStatus(status="up", detail="fake")
    else:
        llm_status = ServiceStatus(status="not_configured", detail="Using deterministic template")

    ads_status = (
        ServiceStatus(status="up")
        if container.settings.nasa_ads_api_token.strip()
        else ServiceStatus(status="not_configured", detail="NASA_ADS_API_TOKEN absent")
    )
    return {
        "archive": ServiceStatus(status="up", detail="IRSA TAP/SIA configured"),
        "redis": redis_status,
        "postgres": db_status,
        "llm": llm_status,
        "ads": ads_status,
    }
