import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(autouse=True)
def _isolate_offline_test_env(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> None:
    if "live" in request.keywords:
        return
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:1/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unused:unused@127.0.0.1:1/unused")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("NASA_ADS_API_TOKEN", "")
    monkeypatch.setenv("LLM_PROVIDER", "template")
    monkeypatch.setenv("LLM_API_KEY", "")


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def isolated_cache_settings(tmp_path: Path):
    from tests.synthetic.restorable_observation import create_isolated_test_settings

    return create_isolated_test_settings(tmp_path / "cache")


@pytest.fixture
def isolated_cache_store(isolated_cache_settings):
    from app.store.cache import CacheStore

    return CacheStore(isolated_cache_settings)


@pytest.fixture
def synthetic_scenario_factory():
    from tests.synthetic.restorable_observation import build_synthetic_scenario_for_target

    return build_synthetic_scenario_for_target


@pytest.fixture
async def restored_barnards_observation(isolated_cache_store, tmp_path: Path):
    from tests.synthetic.restorable_observation import restore_synthetic_observation

    obs, _ = await restore_synthetic_observation(
        cache=isolated_cache_store,
        target="barnards_star",
        tmp_dir=tmp_path / "syn_staging",
        settings=isolated_cache_store.settings,
        seed=42,
    )
    return obs
