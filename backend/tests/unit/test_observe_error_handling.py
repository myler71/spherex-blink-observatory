from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_observe_tap_read_timeout_error_classification(tmp_path: Path) -> None:
    settings = Settings(
        cache_dir=str(tmp_path / "cache"),
        redis_url="redis://127.0.0.1:1/0",  # force isolated unavailable redis
        observe_rate_limit_per_min=100,
    )
    timeout_err = RuntimeError(
        "IRSA TAP archive search failed (ReadTimeout): ReadTimeout after 12.0s on POST https://irsa.ipac.caltech.edu/TAP/sync"
    )

    class _MockPipeline:
        async def run(self, query):
            raise timeout_err

    app = create_app(settings=settings, pipeline_override=_MockPipeline())
    with TestClient(app) as client:
        resp = client.get("/api/v1/observe", params={"target": "wise_0855"})
        assert resp.status_code == 502
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "UPSTREAM_ARCHIVE_TIMEOUT"
        assert "ReadTimeout" in data["error"]["message"]
        assert data["error"]["details"]["stage"] == "archive_search"
        assert data["error"]["details"]["error_type"] == "RuntimeError"


def test_observe_cutout_failure_error_classification(tmp_path: Path) -> None:
    settings = Settings(
        cache_dir=str(tmp_path / "cache"),
        redis_url="redis://127.0.0.1:1/0",
        observe_rate_limit_per_min=100,
    )
    cutout_err = RuntimeError("All SPHEREx cutout downloads failed.")

    class _MockPipeline:
        async def run(self, query):
            raise cutout_err

    app = create_app(settings=settings, pipeline_override=_MockPipeline())
    with TestClient(app) as client:
        resp = client.get("/api/v1/observe", params={"target": "wise_0855"})
        assert resp.status_code == 502
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "UPSTREAM_CUTOUT_FAILURE"
        assert data["error"]["details"]["stage"] == "cutout_fetch"


def test_observe_no_coverage_classification(tmp_path: Path) -> None:
    settings = Settings(
        cache_dir=str(tmp_path / "cache"),
        redis_url="redis://127.0.0.1:1/0",
        observe_rate_limit_per_min=100,
    )
    coverage_err = LookupError("No SPHEREx observations cover (10.00000, 20.00000)")

    class _MockPipeline:
        async def run(self, query):
            raise coverage_err

    app = create_app(settings=settings, pipeline_override=_MockPipeline())
    with TestClient(app) as client:
        resp = client.get("/api/v1/observe", params={"target": "wise_0855"})
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data
        assert data["error"]["code"] == "NO_COVERAGE"
        assert "No SPHEREx observations cover" in data["error"]["message"]


@pytest.mark.asyncio
async def test_pipeline_deadline_releases_coalesced_requests(tmp_path: Path, monkeypatch) -> None:
    import asyncio

    import httpx

    from tests.synthetic.restorable_observation import create_isolated_test_settings

    original_timeout = asyncio.timeout
    monkeypatch.setattr(
        asyncio, "timeout", lambda delay: original_timeout(0.02 if delay == 70.0 else delay)
    )
    calls = 0

    class Pipeline:
        async def run(self, query):
            nonlocal calls
            calls += 1
            await asyncio.sleep(1)

    app = create_app(
        settings=create_isolated_test_settings(tmp_path / "cache"),
        pipeline_override=Pipeline(),
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client,
    ):
        responses = await asyncio.gather(
            *[client.get("/api/v1/observe", params={"target": "wise_0855"}) for _ in range(2)]
        )
    assert calls == 1
    for response in responses:
        assert response.status_code == 502
        assert response.json()["error"]["code"] == "UPSTREAM_TIMEOUT"
        assert response.json()["error"]["details"]["stage"] == "pipeline"
