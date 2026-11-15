from pathlib import Path

import pytest

from app.jobs.run_benchmarks import run_benchmarks
from app.store.cache import CacheStore
from tests.synthetic.restorable_observation import create_isolated_test_settings


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "center,near,far",
    [
        ((0.0, 80.0), (359.999, 80.0), (0.01, 80.0)),
        ((0.0, 89.0), (1.0, 89.0), (0.0, 89.1)),
    ],
)
async def test_unrelated_variable_cannot_pass_target_benchmark(
    tmp_path: Path,
    restored_barnards_observation,
    center,
    near,
    far,
):
    obs = restored_barnards_observation
    obs = obs.model_copy(
        update={"query": obs.query.model_copy(update={"ra": center[0], "dec": center[1]})}
    )
    primary = obs.detected_objects[0].model_copy(
        update={
            "ra": near[0],
            "dec": near[1],
            "is_variable": False,
            "is_candidate_moving": False,
        }
    )
    unrelated = primary.model_copy(
        update={"id": "obj_unrelated", "ra": far[0], "dec": far[1], "is_variable": True}
    )

    class Pipeline:
        async def run(self, query):
            return obs.model_copy(update={"detected_objects": [primary, unrelated]})

    settings = create_isolated_test_settings(tmp_path / "benchmark")
    result = await run_benchmarks(
        settings, CacheStore(settings), pipeline=Pipeline(), data_source="synthetic"
    )
    by_target = {item.target_id: item for item in result.results}
    assert by_target["rw_aurigae"].status == "fail"
    assert by_target["r_draconis"].status == "fail"


@pytest.mark.asyncio
async def test_unmeasured_negative_control_cannot_pass(
    tmp_path: Path, restored_barnards_observation
):
    obs = restored_barnards_observation
    primary = obs.detected_objects[0].model_copy(
        update={
            "ra": obs.query.ra,
            "dec": obs.query.dec,
            "is_variable": False,
            "is_candidate_moving": False,
            "motion": obs.detected_objects[0].motion.model_copy(
                update={
                    "pm_total_arcsec_yr": None,
                    "pm_total_err_mas_yr": None,
                }
            ),
            "variability": [],
        }
    )

    class Pipeline:
        async def run(self, query):
            return obs.model_copy(update={"detected_objects": [primary]})

    settings = create_isolated_test_settings(tmp_path / "benchmark")
    result = await run_benchmarks(
        settings, CacheStore(settings), pipeline=Pipeline(), data_source="synthetic"
    )
    negative = next(item for item in result.results if item.target_id == "negative_control")
    assert negative.status == "fail"
    assert negative.measured_uncertainty is None
