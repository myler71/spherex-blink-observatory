from pathlib import Path

import pytest

from app.config import Settings
from app.jobs.ingest_docs import run_ingest_docs
from app.jobs.precache import run_precache
from app.jobs.run_benchmarks import run_benchmarks
from app.science.pipeline import ObservePipeline
from app.store.cache import CacheStore
from app.store.db import DatabaseStore
from tests.integration.test_observe_pipeline import _MockArchive, _MockCatalogs
from tests.synthetic.fits_generator import SyntheticScenario, generate_synthetic_dataset


@pytest.mark.asyncio
async def test_jobs_ingest_precache_and_benchmarks_offline(tmp_path: Path) -> None:
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=2,
            exposures_per_visit=2,
            visit_gap_days=365.25,
            detectors=[2],
            mover_pm_ra_arcsec_yr=10.0,
            mover_flux=70.0,
            noise_sigma=0.08,
        ),
        tmp_path / "syn",
    )
    settings = Settings(cache_dir=str(tmp_path / "cache"))
    cache = CacheStore(settings)
    db = DatabaseStore(settings)
    pipe = ObservePipeline(settings, archive=_MockArchive(ds), catalogs=_MockCatalogs())

    # 1. ingest_docs populates top-5 chunks matching mandatory targets
    ingested = await run_ingest_docs(settings, db)
    assert ingested >= 6
    hits = await db.search_documents(
        "coldest Y-type brown dwarf", object_identifiers=["wise_0855"], limit=5
    )
    assert any("wise_0855" in h["object_identifiers"] for h in hits)

    # 2. precache warms all 6 preset targets
    precached = await run_precache(settings, cache, db, pipeline=pipe)
    assert len(precached) == 6

    # 3. run_benchmarks computes results honestly from pipeline outputs
    bench = await run_benchmarks(settings, cache, pipeline=pipe, data_source="synthetic")
    assert len(bench.results) == 6
    assert cache.get_json("benchmarks", "latest") is not None
    await db.close()
