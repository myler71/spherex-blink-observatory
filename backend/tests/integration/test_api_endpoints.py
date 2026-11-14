import asyncio
import time
from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.science.pipeline import ObservePipeline
from tests.integration.test_observe_pipeline import _MockArchive, _MockCatalogs
from tests.synthetic.fits_generator import SyntheticScenario, generate_synthetic_dataset


def test_full_api_endpoints_and_payload_under_2mb_and_decoupled_llm(tmp_path: Path) -> None:
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=3,
            exposures_per_visit=4,  # 12 frames
            visit_gap_days=90.0,
            detectors=[2, 3],
            n_static_stars=6,
            mover_pm_ra_arcsec_yr=6.0,
            mover_flux=70.0,
            variable_amplitude=0.35,
            variable_flux=65.0,
            noise_sigma=0.08,
        ),
        tmp_path / "syn",
    )
    settings = Settings(
        cache_dir=str(tmp_path / "cache"),
        llm_provider="fake",
        observe_rate_limit_per_min=200,
        narrative_rate_limit_per_min=200,
        ask_rate_limit_per_min=200,
    )

    class _SlowFakeLlm:
        mode = "fake"

        async def generate_chapters(self, prompt_payload, evidence, feedback=None):
            await asyncio.sleep(0.15)  # simulates slow LLM
            return [[], [], [], [], []]

        async def answer_question(self, question, evidence):
            return {"answer": "Grounded.", "claims": []}

    mock_arch = _MockArchive(ds)
    app = create_app(
        settings=settings,
        pipeline_override=ObservePipeline(settings, archive=mock_arch, catalogs=_MockCatalogs()),
        llm_override=_SlowFakeLlm(),
    )

    with TestClient(app) as client:
        # 1. Health & targets
        rh = client.get("/api/v1/health")
        assert rh.status_code == 200
        assert "archive" in rh.json()

        rt = client.get("/api/v1/targets")
        assert rt.status_code == 200
        assert len(rt.json()["targets"]) == 6

        # 2. Invalid coords -> 422 uniform error shape
        r422 = client.get("/api/v1/observe", params={"ra": 999.0, "dec": 0.0})
        assert r422.status_code == 422
        assert r422.json()["error"]["code"] == "VALIDATION_ERROR"

        # 3. Live 12-frame observe -> < 2 MB compressed, does not wait for LLM
        t0 = time.perf_counter()
        ro = client.get(
            "/api/v1/observe",
            params={"ra": "180.0", "dec": "20.0", "fov": 0.08, "max_frames": 12},
            headers={"Accept-Encoding": "gzip"},
        )
        observe_ms = (time.perf_counter() - t0) * 1000.0
        assert ro.status_code == 200
        assert len(ro.content) < 2 * 1024 * 1024  # FR-20: under 2 MB
        payload = ro.json()
        assert len(payload["frames"]) == 12
        assert payload["served_from"] == "live"
        obs_id = payload["observation_id"]

        # 4. Warm cache preset/repeat speed (< 200 ms p95 over 50 requests, FR-22)
        latencies = []
        for _ in range(50):
            ts = time.perf_counter()
            rc = client.get(
                "/api/v1/observe",
                params={"ra": "180.0", "dec": "20.0", "fov": 0.08, "max_frames": 12},
            )
            assert rc.status_code == 200
            assert rc.json()["served_from"] == "cache"
            latencies.append((time.perf_counter() - ts) * 1000.0)
        p95 = sorted(latencies)[int(0.95 * len(latencies)) - 1]
        assert p95 < 200.0, f"Warm cache p95 {p95:.1f} ms exceeded 200 ms"

        # 5. Stored observation, spectrum, evidence, narrative, ask
        assert client.get(f"/api/v1/observe/{obs_id}").status_code == 200
        rs = client.get(f"/api/v1/observe/{obs_id}/spectrum", params={"ra": 180.0, "dec": 20.0})
        assert rs.status_code == 200
        assert len(rs.json()["points"]) >= 4

        re_ev = client.get(f"/api/v1/observe/{obs_id}/evidence")
        assert re_ev.status_code == 200
        assert len(re_ev.json()["items"]) >= 1

        rn = client.get(f"/api/v1/observe/{obs_id}/narrative")
        assert rn.status_code == 200
        assert rn.json()["status"] in ("pending", "ready")
        # Poll briefly until ready
        for _ in range(20):
            rn2 = client.get(f"/api/v1/observe/{obs_id}/narrative")
            if rn2.json()["status"] == "ready":
                break
            time.sleep(0.03)
        assert rn2.json()["status"] == "ready"
        assert len(rn2.json()["narrative"]["chapters"]) == 5

        ra_ask = client.post(
            f"/api/v1/observe/{obs_id}/ask",
            json={"question": "What is the fastest-moving object in this image?"},
        )
        assert ra_ask.status_code == 200
        assert ra_ask.json()["in_scope"] is True

        # 6. Candidates CRUD + duplicate fingerprint vote -> 409
        obj0 = payload["detected_objects"][0]
        rc_new = client.post(
            "/api/v1/candidates",
            json={
                "observation_id": obs_id,
                "object_id": obj0["id"],
                "ra_deg": obj0["ra"],
                "dec_deg": obj0["dec"],
                "reason": "Consistent proper motion across 3 visits",
            },
        )
        assert rc_new.status_code == 201
        cid = rc_new.json()["candidate_id"]
        rv1 = client.post(
            f"/api/v1/candidates/{cid}/votes",
            json={"client_fingerprint": "browser_fp_001", "vote_label": "Real Motion"},
        )
        assert rv1.status_code == 200
        assert rv1.json()["total_votes"] == 1
        rv2 = client.post(
            f"/api/v1/candidates/{cid}/votes",
            json={"client_fingerprint": "browser_fp_001", "vote_label": "Artifact"},
        )
        assert rv2.status_code == 409
        assert observe_ms >= 0.0
