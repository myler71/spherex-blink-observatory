from datetime import UTC, datetime

from fastapi import APIRouter, Depends

from app.api.deps import AppContainer, get_container
from app.schemas.benchmarks import BenchmarkRunResponse

router = APIRouter(tags=["benchmarks"])


@router.get("/benchmarks", response_model=BenchmarkRunResponse)
async def get_benchmarks(
    container: AppContainer = Depends(get_container),
) -> BenchmarkRunResponse:
    cached = container.cache.get_json("benchmarks", "latest")
    if cached is not None:
        return BenchmarkRunResponse.model_validate(cached)
    return BenchmarkRunResponse(
        run_id="bench_none",
        created_at=datetime.now(UTC).isoformat(),
        pipeline_version=container.settings.pipeline_version,
        results=[],
    )
