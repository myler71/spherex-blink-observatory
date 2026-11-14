from typing import Literal

from pydantic import BaseModel


class BenchmarkTargetResult(BaseModel):
    target_id: str
    name: str
    mode: str
    data_source: Literal["real", "synthetic", "unavailable"]
    reference_value: str
    reference_citation: str
    measured_value: str | None = None
    measured_uncertainty: str | None = None
    residual: str | None = None
    snr: float | None = None
    num_visits: int = 0
    baseline_days: float = 0.0
    processing_ms: float = 0.0
    status: Literal["pass", "fail", "inconclusive"]
    reason: str


class BenchmarkRunResponse(BaseModel):
    run_id: str
    created_at: str
    pipeline_version: str
    results: list[BenchmarkTargetResult]
