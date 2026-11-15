"""Regression tests demonstrating observation cache expiry independence and synthetic recovery.

Verifies:
1. Cache expiry causes AI / narrative / ask endpoints to fail with HTTP 404 when no cached observation exists.
2. Restoring deterministic synthetic observations immediately restores all AI endpoints to HTTP 200.
3. Restored synthetic observations are clearly labeled with SYNTHETIC_OBSERVATION_WARNING.
4. AI ask answers remain deterministic and grounded after cache expiry and restoration.
5. All six preset targets can be restored into cold/empty caches without external archive calls.
6. Redis isolation (redis://127.0.0.1:1/0) prevents environment credential leak and ensures local fallback.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.narrator.llm import TemplateLlmProvider
from app.science.targets import list_target_presets
from tests.synthetic.restorable_observation import (
    SYNTHETIC_OBSERVATION_WARNING,
    create_isolated_test_settings,
    restore_all_synthetic_observations,
    restore_synthetic_observation,
)


@pytest.mark.asyncio
async def test_ai_endpoints_fail_on_cache_expiry_and_recover_with_synthetic_restoration(
    tmp_path: Path,
) -> None:
    """Demonstrate that cache expiry breaks AI endpoints and restorable observation restores them."""
    cache_dir = tmp_path / "cache"
    settings = create_isolated_test_settings(cache_dir)
    app = create_app(settings=settings, llm_override=TemplateLlmProvider())

    with TestClient(app) as client:
        container = app.state.container

        # Step 1: Seed initial synthetic observation into cache
        obs, cache_key = await restore_synthetic_observation(
            cache=container.cache,
            target="barnards_star",
            tmp_dir=tmp_path / "staging",
            settings=settings,
            seed=42,
        )
        obs_id = obs.observation_id
        assert SYNTHETIC_OBSERVATION_WARNING in obs.warnings

        # Step 2: Verify all endpoints work when observation is present
        r_get = client.get(f"/api/v1/observe/{obs_id}")
        assert r_get.status_code == 200
        assert r_get.json()["served_from"] == "cache"
        assert SYNTHETIC_OBSERVATION_WARNING in r_get.json()["warnings"]

        r_ask = client.post(
            f"/api/v1/observe/{obs_id}/ask",
            json={"question": "What is the fastest-moving object in this image?"},
        )
        assert r_ask.status_code == 200
        payload_ask = r_ask.json()
        assert payload_ask["in_scope"] is True
        assert len(payload_ask["claims"]) >= 1

        r_ev = client.get(f"/api/v1/observe/{obs_id}/evidence")
        assert r_ev.status_code == 200
        assert len(r_ev.json()["items"]) >= 1

        r_nar = client.get(f"/api/v1/observe/{obs_id}/narrative")
        assert r_nar.status_code == 200
        assert r_nar.json()["status"] == "ready"
        assert len(r_nar.json()["narrative"]["chapters"]) == 5

        # Step 3: Simulate Cache Expiry (e.g., TTL expired or cache pruned)
        json_path = container.cache._json_path("observe", cache_key)
        assert json_path.exists(), "Cache JSON file should exist before simulated expiry"

        # Explicitly write an expired envelope into the cache file
        expired_envelope = {
            "cached_at": "2020-01-01T00:00:00Z",
            "expires_at": time.time() - 3600.0,  # 1 hour in the past
            "data": obs.model_dump(mode="json"),
        }
        json_path.write_text(json.dumps(expired_envelope), encoding="utf-8")

        # Cache get_json should detect expiration and return None
        assert container.cache.get_json("observe", cache_key) is None
        assert not json_path.exists(), "CacheStore should unlink expired file upon access"

        # Step 4: Verify all AI & observe endpoints return 404 NOT_FOUND on expired cache
        r_get_exp = client.get(f"/api/v1/observe/{obs_id}")
        assert r_get_exp.status_code == 404
        assert r_get_exp.json()["error"]["code"] == "NOT_FOUND"

        r_ask_exp = client.post(
            f"/api/v1/observe/{obs_id}/ask",
            json={"question": "What is the fastest-moving object in this image?"},
        )
        assert r_ask_exp.status_code == 404
        assert r_ask_exp.json()["error"]["code"] == "NOT_FOUND"

        r_ev_exp = client.get(f"/api/v1/observe/{obs_id}/evidence")
        assert r_ev_exp.status_code == 404
        assert r_ev_exp.json()["error"]["code"] == "NOT_FOUND"

        r_nar_exp = client.get(f"/api/v1/observe/{obs_id}/narrative")
        assert r_nar_exp.status_code == 404
        assert r_nar_exp.json()["error"]["code"] == "NOT_FOUND"

        # Step 5: Restore synthetic observation into cache
        restored_obs, restored_key = await restore_synthetic_observation(
            cache=container.cache,
            target="barnards_star",
            tmp_dir=tmp_path / "staging_recover",
            settings=settings,
            seed=42,
        )
        assert restored_obs.observation_id == obs_id
        assert restored_key == cache_key

        # Step 6: Verify all endpoints immediately recover and function deterministically
        r_get_rec = client.get(f"/api/v1/observe/{obs_id}")
        assert r_get_rec.status_code == 200
        assert r_get_rec.json()["served_from"] == "cache"

        r_ask_rec = client.post(
            f"/api/v1/observe/{obs_id}/ask",
            json={"question": "What is the fastest-moving object in this image?"},
        )
        assert r_ask_rec.status_code == 200
        assert r_ask_rec.json()["in_scope"] is True
        assert r_ask_rec.json()["answer"] == payload_ask["answer"]

        r_ev_rec = client.get(f"/api/v1/observe/{obs_id}/evidence")
        assert r_ev_rec.status_code == 200

        r_nar_rec = client.get(f"/api/v1/observe/{obs_id}/narrative")
        assert r_nar_rec.status_code == 200
        assert r_nar_rec.json()["status"] == "ready"


@pytest.mark.asyncio
async def test_all_six_presets_restorable_in_empty_cache_without_network(tmp_path: Path) -> None:
    """Verify that all six target presets can be seeded into a fresh empty cache."""
    cache_dir = tmp_path / "fresh_cache"
    settings = create_isolated_test_settings(cache_dir)
    app = create_app(settings=settings, llm_override=TemplateLlmProvider())

    with TestClient(app) as client:
        container = app.state.container

        # Restore all 6 presets
        seeded = await restore_all_synthetic_observations(
            cache=container.cache,
            tmp_dir=tmp_path / "staging_all",
            settings=settings,
            seed=42,
        )
        assert len(seeded) == 6

        # Query each target via the API
        presets = list_target_presets()
        assert len(presets) == 6

        for preset in presets:
            obs = seeded[preset.id]
            r = client.get(f"/api/v1/observe/{obs.observation_id}")
            assert r.status_code == 200, f"Preset {preset.id} should be found in cache"
            data = r.json()
            assert data["query"]["target"] == preset.id
            assert SYNTHETIC_OBSERVATION_WARNING in data["warnings"]

            # Verify ask endpoint responds for each target
            r_ask = client.post(
                f"/api/v1/observe/{obs.observation_id}/ask",
                json={"question": "What sources were detected in this patch?"},
            )
            assert r_ask.status_code == 200
            assert r_ask.json()["in_scope"] is True


def test_redis_isolation_fallback_without_env_leak(tmp_path: Path) -> None:
    """Ensure settings use an unreachable redis URL and fall back to local disk safely."""
    settings = create_isolated_test_settings(tmp_path / "cache_redis")
    assert settings.redis_url == "redis://127.0.0.1:1/0"

    from app.store.cache import CacheStore

    cache = CacheStore(settings)
    assert not cache.redis_available(), "Redis should be reported unavailable"

    # Disk cache still works deterministically
    cache.set_json("test_ns", "key_1", {"msg": "isolated"})
    val = cache.get_json("test_ns", "key_1")
    assert val == {"msg": "isolated"}
