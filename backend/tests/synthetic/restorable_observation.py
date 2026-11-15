"""Deterministic restorable synthetic observation setup for SPHEREx Blink Observatory.

Provides reusable, reproducible synthetic observations that can be restored into
CacheStore independent of cache expiry, cold starts, or live IRSA/catalog availability.
Guarantees isolation from environment secrets and external Redis servers.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.schemas.observe import ObserveQuery, ObserveResponse
from app.science.pipeline import ObservePipeline
from app.science.ports import ArchiveObservationMeta, CutoutFetchResult
from app.science.targets import TargetPreset, get_target_preset, list_target_presets
from app.store.cache import CacheStore
from tests.synthetic.fits_generator import (
    SyntheticDataset,
    SyntheticScenario,
    generate_synthetic_dataset,
)

SYNTHETIC_OBSERVATION_WARNING: str = (
    "SYNTHETIC: Deterministic test observation generated without live sky archive access"
)
SYNTHETIC_PROVENANCE_RELEASE: str = "synthetic-dr1"


class SyntheticArchiveAdapter:
    """In-memory mock archive serving cutouts from a generated SyntheticDataset."""

    def __init__(self, dataset: SyntheticDataset) -> None:
        self.dataset = dataset
        self.download_calls = 0

    async def search_observations(
        self,
        ra_deg: float,
        dec_deg: float,
        releases: list[str] | None = None,
    ) -> list[ArchiveObservationMeta]:
        return [
            ArchiveObservationMeta(
                obs_id=f.obs_id,
                plane_id=f"P_{f.obs_id}",
                collection=SYNTHETIC_PROVENANCE_RELEASE,
                mjd_start=f.mjd,
                mjd_end=f.mjd + 0.005,
                bandpass=f"SPHEREx-D{f.detector}",
                provenance_version="7.0.5-synthetic",
                raw_uri=f"/syn/{f.obs_id}.fits",
                cutout_url=f"https://irsa.ipac.caltech.edu/syn/{f.obs_id}.fits",
            )
            for f in self.dataset.frames
        ]

    async def fetch_cutouts(
        self,
        observations: list[ArchiveObservationMeta],
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
    ) -> list[CutoutFetchResult]:
        self.download_calls += 1
        by_id = {f.obs_id: f.fits_path for f in self.dataset.frames}
        return [
            CutoutFetchResult(
                obs_id=o.obs_id,
                archive_url=o.cutout_url,
                local_path=by_id.get(o.obs_id),
            )
            for o in observations
        ]


class SyntheticCatalogAdapter:
    """Mock catalog adapter returning consistent null or synthetic catalog overlays."""

    async def query_all(
        self,
        ra_deg: float,
        dec_deg: float,
        fov_deg: float,
        epochs_mjd: list[float],
        include_neossat: bool = False,
        include_horizons: bool = False,
    ) -> dict[str, Any]:
        return {
            "gaia_status": "up",
            "gaia_rows": [],
            "gaia_truncated": False,
            "allwise_status": "up",
            "allwise_rows": [],
            "simbad_status": "up",
            "simbad_rows": [],
            "vizier_status": "up",
            "vizier_rows": [],
            "ned_status": "up",
            "ned_rows": [],
            "neossat_status": "not_configured",
            "neossat_rows": [],
            "horizons_status": "not_configured",
            "horizons_rows": [],
        }


def get_target_preset_or_default(target: str | TargetPreset) -> TargetPreset:
    """Resolve a target preset by ID or return as-is if already a TargetPreset."""
    if isinstance(target, TargetPreset):
        return target
    preset = get_target_preset(target)
    if preset is None:
        raise ValueError(f"Unknown target preset ID: {target!r}")
    return preset


def build_synthetic_scenario_for_target(
    target: str | TargetPreset,
    *,
    seed: int = 42,
) -> SyntheticScenario:
    """Build a deterministic SyntheticScenario for a preset target.

    Follows the target dataset specification:
    - preset RA / dec / default FOV
    - 3 visits x 2 exposures (6 frames total)
    - 365.25-day baseline spacing
    - detector 2
    - 5 static stars
    - mover proper motion matching preset expected_pm_arcsec_yr (or 0.0)
    - mover flux 75.0
    - variable amplitude 0.65 if expected_variable else 0.0
    - noise sigma 0.08
    - deterministic seed 42
    """
    preset = get_target_preset_or_default(target)
    return SyntheticScenario(
        center_ra=preset.ra_deg,
        center_dec=preset.dec_deg,
        fov_deg=preset.default_fov_deg,
        num_visits=3,
        exposures_per_visit=2,
        visit_gap_days=365.25,
        detectors=[2],
        n_static_stars=5,
        mover_pm_ra_arcsec_yr=(preset.expected_pm_arcsec_yr or 0.0)
        if not preset.is_negative_control
        else 0.0,
        mover_flux=75.0,
        variable_amplitude=0.65 if preset.expected_variable else 0.0,
        noise_sigma=0.08,
        seed=seed,
    )


def create_isolated_test_settings(cache_dir: Path | str) -> Settings:
    """Create settings isolated from host .env and external Redis."""
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        database_url="postgresql+psycopg://unused:unused@127.0.0.1:1/unused",
        llm_api_key="",
        tavily_api_key="",
        nasa_ads_api_token="",
        cache_dir=str(cache_dir),
        redis_url="redis://127.0.0.1:1/0",  # Unavailable port guarantees no external Redis connection/leak
        llm_provider="template",
        observe_rate_limit_per_min=5000,
        narrative_rate_limit_per_min=5000,
        ask_rate_limit_per_min=5000,
    )


async def create_synthetic_observation(
    target: str | TargetPreset = "barnards_star",
    *,
    tmp_dir: Path | str,
    settings: Settings | None = None,
    seed: int = 42,
    query_override: ObserveQuery | None = None,
) -> ObserveResponse:
    """Generate a fully populated ObserveResponse deterministically from synthetic FITS."""
    preset = get_target_preset_or_default(target)
    scenario = build_synthetic_scenario_for_target(preset, seed=seed)

    work_dir = Path(tmp_dir) / f"syn_{preset.id}_s{seed}"
    work_dir.mkdir(parents=True, exist_ok=True)
    dataset = generate_synthetic_dataset(scenario, work_dir)

    eff_settings = settings or create_isolated_test_settings(Path(tmp_dir) / "cache")
    archive = SyntheticArchiveAdapter(dataset)
    catalogs = SyntheticCatalogAdapter()
    pipeline = ObservePipeline(settings=eff_settings, archive=archive, catalogs=catalogs)

    query = query_override or ObserveQuery(
        ra=preset.ra_deg,
        dec=preset.dec_deg,
        fov=preset.default_fov_deg,
        mode=preset.recommended_mode,
        target=preset.id,
    )

    observation = await pipeline.run(query)

    # Ensure the synthetic observation is explicitly and unambiguously labeled
    warnings = list(observation.warnings)
    if SYNTHETIC_OBSERVATION_WARNING not in warnings:
        warnings.insert(0, SYNTHETIC_OBSERVATION_WARNING)

    return observation.model_copy(
        update={
            "warnings": warnings,
            "observation_id": f"synthetic_{observation.observation_id}",
            "served_from": "cache",
            "cached_at": datetime.now(UTC).isoformat(),
        }
    )


def restore_observation_to_cache(
    cache: CacheStore,
    observation: ObserveResponse,
    *,
    ttl_seconds: int | None = None,
) -> str:
    """Store an ObserveResponse in CacheStore under its versioned key."""
    cache_key = cache.versioned_key(observation.observation_id)
    cache.set_json(
        "observe", cache_key, observation.model_dump(mode="json"), ttl_seconds=ttl_seconds
    )
    return cache_key


async def restore_synthetic_observation(
    cache: CacheStore,
    target: str | TargetPreset = "barnards_star",
    *,
    tmp_dir: Path | str,
    settings: Settings | None = None,
    seed: int = 42,
    ttl_seconds: int | None = None,
) -> tuple[ObserveResponse, str]:
    """Generate and restore a deterministic synthetic observation into CacheStore.

    Returns:
        tuple[ObserveResponse, str]: The restored observation and its versioned cache key.
    """
    obs = await create_synthetic_observation(
        target=target,
        tmp_dir=tmp_dir,
        settings=settings,
        seed=seed,
    )
    cache_key = restore_observation_to_cache(cache, obs, ttl_seconds=ttl_seconds)
    return obs, cache_key


async def restore_all_synthetic_observations(
    cache: CacheStore,
    *,
    tmp_dir: Path | str,
    settings: Settings | None = None,
    seed: int = 42,
    ttl_seconds: int | None = None,
) -> dict[str, ObserveResponse]:
    """Generate and restore synthetic observations for all 6 target presets into CacheStore."""
    results: dict[str, ObserveResponse] = {}
    for preset in list_target_presets():
        obs, _ = await restore_synthetic_observation(
            cache=cache,
            target=preset,
            tmp_dir=tmp_dir,
            settings=settings,
            seed=seed,
            ttl_seconds=ttl_seconds,
        )
        results[preset.id] = obs
    return results


def restore_synthetic_observation_sync(
    cache: CacheStore,
    target: str | TargetPreset = "barnards_star",
    *,
    tmp_dir: Path | str,
    settings: Settings | None = None,
    seed: int = 42,
    ttl_seconds: int | None = None,
) -> tuple[ObserveResponse, str]:
    """Synchronous convenience wrapper for non-async tests or scripts."""
    return asyncio.run(
        restore_synthetic_observation(
            cache=cache,
            target=target,
            tmp_dir=tmp_dir,
            settings=settings,
            seed=seed,
            ttl_seconds=ttl_seconds,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deterministic restorable synthetic observation utility independent of cache expiry."
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=Path(".cache/spherex"),
        help="Target cache directory to restore observations into",
    )
    parser.add_argument(
        "--target",
        type=str,
        default="barnards_star",
        help="Target preset ID ('barnards_star', 'wise_0855', etc.) or 'all'",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Deterministic pseudo-random seed (default: 42)",
    )
    parser.add_argument(
        "--ttl-seconds",
        type=int,
        default=None,
        help="Cache TTL in seconds (default: settings cache_ttl_seconds)",
    )
    parser.add_argument(
        "--output-json",
        type=Path,
        default=None,
        help="Optional destination path to write the serialized observation JSON",
    )
    args = parser.parse_args()

    settings = create_isolated_test_settings(args.cache_dir)
    cache = CacheStore(settings)
    tmp_staging = args.cache_dir / "_synthetic_staging"
    tmp_staging.mkdir(parents=True, exist_ok=True)

    if args.target.lower() == "all":
        print(f"Restoring synthetic observations for all presets into {args.cache_dir}...")
        results = asyncio.run(
            restore_all_synthetic_observations(
                cache=cache,
                tmp_dir=tmp_staging,
                settings=settings,
                seed=args.seed,
                ttl_seconds=args.ttl_seconds,
            )
        )
        for target_id, obs in results.items():
            print(
                f"  - {target_id}: {obs.observation_id} ({len(obs.detected_objects)} objects, {len(obs.frames)} frames)"
            )
    else:
        print(f"Restoring synthetic observation for {args.target} into {args.cache_dir}...")
        obs, key = asyncio.run(
            restore_synthetic_observation(
                cache=cache,
                target=args.target,
                tmp_dir=tmp_staging,
                settings=settings,
                seed=args.seed,
                ttl_seconds=args.ttl_seconds,
            )
        )
        print("Successfully restored observation:")
        print(f"  Observation ID : {obs.observation_id}")
        print(f"  Cache Key      : {key}")
        print(f"  Objects        : {len(obs.detected_objects)}")
        print(f"  Frames         : {len(obs.frames)}")
        print(f"  Warnings       : {obs.warnings}")

        if args.output_json:
            args.output_json.parent.mkdir(parents=True, exist_ok=True)
            args.output_json.write_text(obs.model_dump_json(indent=2), encoding="utf-8")
            print(f"  Written to     : {args.output_json}")


if __name__ == "__main__":
    main()
