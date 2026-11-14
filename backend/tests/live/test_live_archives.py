from pathlib import Path

import pytest

from app.archive.irsa import IrsaArchiveAdapter
from app.config import Settings
from app.store.cache import CacheStore


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_irsa_barnards_star_search_and_cutout(tmp_path: Path) -> None:
    settings = Settings(cache_dir=str(tmp_path / "live_cache"))
    cache = CacheStore(settings)
    adapter = IrsaArchiveAdapter(settings=settings, cache=cache)
    rows = await adapter.search_observations(269.452075, 4.693389)
    assert len(rows) > 0
    res = await adapter.fetch_cutouts(rows[:1], 269.452075, 4.693389, 0.08)
    assert res[0].local_path is not None and res[0].local_path.exists()
