from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_rate_limiter_returns_429_with_retry_after(tmp_path: Path) -> None:
    settings = Settings(
        cache_dir=str(tmp_path / "cache"),
        observe_rate_limit_per_min=2,
        narrative_rate_limit_per_min=2,
        ask_rate_limit_per_min=2,
    )
    app = create_app(settings=settings)
    with TestClient(app) as client:
        # Exceed /api/v1/observe rate limit (422 invalid coords or 404 still hits limiter)
        r1 = client.get("/api/v1/targets")
        assert r1.status_code == 200
        # Trigger 3 requests to /observe/{id}/ask
        for _i in range(2):
            r = client.post(
                "/api/v1/observe/obs_missing/ask",
                json={"question": "What is the fastest object?"},
            )
            assert r.status_code in (404, 200)
        r3 = client.post(
            "/api/v1/observe/obs_missing/ask",
            json={"question": "What is the fastest object?"},
        )
        assert r3.status_code == 429
        assert "Retry-After" in r3.headers
        body = r3.json()
        assert body["error"]["code"] == "RATE_LIMIT_EXCEEDED"
