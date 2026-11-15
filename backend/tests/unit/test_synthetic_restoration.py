"""Unit tests for the restorable synthetic observation utility.

Verifies:
1. Preset scenario builder conforms to the exact specification across all 6 targets.
2. Synthetic generation is deterministic and reproducible across repeated runs.
3. Restored observations are unambiguously labeled as synthetic.
4. Direct AskThisPatchService integration works seamlessly without live external archives.
5. CacheStore storage and versioned keying behave predictably.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.narrator.ask import AskThisPatchService
from app.narrator.evidence import EvidenceBuilder
from app.narrator.llm import TemplateLlmProvider
from app.science.targets import list_target_presets
from app.store.cache import CacheStore
from tests.synthetic.restorable_observation import (
    SYNTHETIC_OBSERVATION_WARNING,
    SYNTHETIC_PROVENANCE_RELEASE,
    build_synthetic_scenario_for_target,
    create_isolated_test_settings,
    create_synthetic_observation,
    restore_synthetic_observation,
)


def test_build_synthetic_scenario_conforms_to_spec() -> None:
    """Verify that build_synthetic_scenario_for_target adheres to the dataset spec for all 6 targets."""
    presets = list_target_presets()
    assert len(presets) == 6

    for preset in presets:
        sc = build_synthetic_scenario_for_target(preset.id, seed=42)
        assert sc.center_ra == preset.ra_deg
        assert sc.center_dec == preset.dec_deg
        assert sc.fov_deg == preset.default_fov_deg
        assert sc.num_visits == 3
        assert sc.exposures_per_visit == 2
        assert sc.visit_gap_days == 365.25
        assert sc.detectors == [2]
        assert sc.n_static_stars == 5
        assert sc.mover_flux == 75.0
        assert sc.noise_sigma == 0.08
        assert sc.seed == 42

        if preset.recommended_mode == "motion":
            assert sc.mover_pm_ra_arcsec_yr == preset.expected_pm_arcsec_yr
            assert sc.variable_amplitude == 0.0
        elif preset.expected_variable:
            assert sc.variable_amplitude == 0.65
        else:
            # Negative control
            assert sc.mover_pm_ra_arcsec_yr == 0.0
            assert sc.variable_amplitude == 0.0


@pytest.mark.asyncio
async def test_synthetic_observation_determinism(tmp_path: Path) -> None:
    """Ensure two runs with the same seed yield identical observation properties."""
    settings = create_isolated_test_settings(tmp_path / "cache")

    obs1 = await create_synthetic_observation(
        target="barnards_star",
        tmp_dir=tmp_path / "run1",
        settings=settings,
        seed=42,
    )
    obs2 = await create_synthetic_observation(
        target="barnards_star",
        tmp_dir=tmp_path / "run2",
        settings=settings,
        seed=42,
    )

    assert obs1.observation_id == obs2.observation_id
    assert len(obs1.detected_objects) == len(obs2.detected_objects)
    assert len(obs1.frames) == len(obs2.frames)

    # First object properties match
    o1 = obs1.detected_objects[0]
    o2 = obs2.detected_objects[0]
    assert o1.id == o2.id
    assert o1.ra == o2.ra
    assert o1.dec == o2.dec
    assert o1.motion.pm_total_arcsec_yr == o2.motion.pm_total_arcsec_yr


@pytest.mark.asyncio
async def test_synthetic_observation_clear_labeling(tmp_path: Path) -> None:
    """Ensure observation warnings and frame provenance clearly identify synthetic origin."""
    settings = create_isolated_test_settings(tmp_path / "cache")
    obs = await create_synthetic_observation(
        target="rw_aurigae",
        tmp_dir=tmp_path / "syn_rw",
        settings=settings,
        seed=42,
    )

    # 1. Warning label check
    assert SYNTHETIC_OBSERVATION_WARNING in obs.warnings
    assert obs.observation_id.startswith("synthetic_obs_")

    # 2. Frame provenance check
    assert len(obs.frames) > 0
    for frame in obs.frames:
        assert frame.provenance.archive_url.startswith("https://irsa.ipac.caltech.edu/syn/")
        assert frame.provenance.release == SYNTHETIC_PROVENANCE_RELEASE

    # 3. Selection summary check
    assert obs.selection.visits_count == 3


@pytest.mark.asyncio
async def test_direct_ask_service_with_synthetic_observation(tmp_path: Path) -> None:
    """Verify that AskThisPatchService operates reliably on a synthetic observation without cache or network."""
    settings = create_isolated_test_settings(tmp_path / "cache")
    obs = await create_synthetic_observation(
        target="barnards_star",
        tmp_dir=tmp_path / "syn_ask",
        settings=settings,
        seed=42,
    )
    evidence = EvidenceBuilder().build(obs, docs=[])
    ask_svc = AskThisPatchService(settings=settings, llm_provider=TemplateLlmProvider())

    # 1. Fastest moving object check
    ans_fast = await ask_svc.answer(
        obs, evidence, "What is the fastest-moving object in this image?"
    )
    assert ans_fast.in_scope is True
    assert len(ans_fast.claims) >= 1
    fastest = max(
        [o for o in obs.detected_objects if o.motion.pm_total_arcsec_yr is not None],
        key=lambda o: o.motion.pm_total_arcsec_yr or 0.0,
    )
    assert fastest.id in ans_fast.answer

    # 2. Out-of-scope refusal
    ans_oos = await ask_svc.answer(obs, evidence, "What is the current population of Tokyo?")
    assert ans_oos.in_scope is False
    assert "not in this patch" in ans_oos.answer.lower()


@pytest.mark.asyncio
async def test_cache_restore_and_retrieval(tmp_path: Path) -> None:
    """Verify CacheStore keying and storage of synthetic observations."""
    settings = create_isolated_test_settings(tmp_path / "cache_store")
    cache = CacheStore(settings)

    obs, key = await restore_synthetic_observation(
        cache=cache,
        target="negative_control",
        tmp_dir=tmp_path / "staging_nc",
        settings=settings,
        seed=42,
    )

    expected_key = cache.versioned_key(obs.observation_id)
    assert key == expected_key

    retrieved = cache.get_json("observe", key)
    assert retrieved is not None
    assert retrieved["observation_id"] == obs.observation_id
    assert retrieved["query"]["target"] == "negative_control"
