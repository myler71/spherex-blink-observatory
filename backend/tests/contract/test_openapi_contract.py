from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app


def test_openapi_schema_matches_api_docs_and_routes(tmp_path: Path) -> None:
    settings = Settings(cache_dir=str(tmp_path / "cache"))
    app = create_app(settings=settings)
    with TestClient(app) as client:
        schema = client.get("/openapi.json").json()

    paths = schema["paths"]
    expected_paths = [
        "/api/v1/health",
        "/api/v1/targets",
        "/api/v1/observe",
        "/api/v1/observe/{observation_id}",
        "/api/v1/observe/{observation_id}/spectrum",
        "/api/v1/observe/{observation_id}/narrative",
        "/api/v1/observe/{observation_id}/evidence",
        "/api/v1/observe/{observation_id}/ask",
        "/api/v1/benchmarks",
        "/api/v1/candidates",
        "/api/v1/candidates/{candidate_id}/votes",
    ]
    for p in expected_paths:
        assert p in paths, f"Missing OpenAPI route: {p}"

    api_doc = Path(__file__).resolve().parents[2] / "docs" / "API.md"
    assert api_doc.exists(), "backend/docs/API.md missing"
    doc_text = api_doc.read_text(encoding="utf-8")
    for p in expected_paths:
        assert p in doc_text, f"{p} missing from backend/docs/API.md"
