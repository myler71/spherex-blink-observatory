"""Warm cache, Redis, docs DB, and benchmarks for all mandatory verification targets offline."""

from __future__ import annotations

import asyncio
import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from app.config import Settings, get_settings
from app.jobs.ingest_docs import run_ingest_docs
from app.jobs.run_benchmarks import run_benchmarks
from app.narrator.evidence import EvidenceBuilder
from app.narrator.graph import NarratorOrchestrator
from app.narrator.llm import TemplateLlmProvider, build_llm_provider
from app.schemas.benchmarks import BenchmarkRunResponse
from app.schemas.narrative import CosmicNarratorResponse, EvidenceStoreResponse
from app.schemas.observe import ObserveQuery, ObserveResponse
from app.schemas.targets import TargetPreset
from app.science.pipeline import ObservePipeline, compute_observation_id
from app.science.targets import PRESET_TARGETS, list_target_presets
from app.store.cache import CacheStore
from app.store.db import DatabaseStore
from tests.synthetic.fits_generator import SyntheticDataset, generate_synthetic_dataset
from tests.synthetic.restorable_observation import (
    SyntheticArchiveAdapter,
    SyntheticCatalogAdapter,
    build_synthetic_scenario_for_target,
)

UI_TARGET_COORDS: dict[str, tuple[float, float]] = {
    "wise_0855": (133.79513, -7.24515),
    "barnards_star": (269.45208, 4.69339),
    "epsilon_indi_b": (331.04375, -56.78278),
    "rw_aurigae": (76.95654, 30.40144),
    "r_draconis": (248.1675, 66.75472),
    "negative_control": (134.84582, 40.9947),
}

REAL_SNAPSHOT_FILENAME = (
    "observe_66c778255e6b28cc2bb288953f0021f3909218dc775684c10b32cf56f4ebf4fa.json"
)


def _narrative_cache_key(settings: Settings, cache: CacheStore, observation_id: str) -> str:
    ads_flag = "ads1" if settings.nasa_ads_api_token.strip() else "ads0"
    llm = build_llm_provider(settings)
    model = settings.llm_model or getattr(llm, "mode", settings.llm_provider)
    return cache.versioned_key(
        f"{observation_id}:{settings.llm_provider}:{model}:{settings.prompt_version}:{ads_flag}"
    )


def _build_query_variants(preset: TargetPreset, max_frames: int) -> list[ObserveQuery]:
    coord_pairs: list[tuple[float, float]] = [(preset.ra_deg, preset.dec_deg)]
    ui_coords = UI_TARGET_COORDS.get(preset.id)
    if ui_coords is not None and ui_coords not in coord_pairs:
        coord_pairs.append(ui_coords)

    modes: list[Literal["motion", "variability", "both"]] = [preset.recommended_mode]
    if "both" not in modes:
        modes.append("both")
    if preset.is_negative_control and "motion" not in modes:
        modes.append("motion")

    queries: list[ObserveQuery] = []
    for ra_val, dec_val in coord_pairs:
        for target_val in (preset.id, None):
            for mode_val in modes:
                queries.append(
                    ObserveQuery(
                        ra=ra_val,
                        dec=dec_val,
                        fov=preset.default_fov_deg,
                        mode=mode_val,
                        max_frames=max_frames,
                        propagate=True,
                        target=target_val,
                    )
                )
    for mode_val in modes:
        queries.append(
            ObserveQuery(
                ra=preset.ra_deg,
                dec=preset.dec_deg,
                fov=preset.default_fov_deg,
                mode=mode_val,
                max_frames=max_frames,
                propagate=False,
                target=preset.id,
            )
        )
    return queries


def _load_real_snapshot(cache_dir: str) -> ObserveResponse | None:
    snap_path = Path(cache_dir) / "json" / REAL_SNAPSHOT_FILENAME
    if not snap_path.exists():
        return None
    raw = json.loads(snap_path.read_text(encoding="utf-8"))
    payload = raw.get("data", raw)
    return ObserveResponse.model_validate(payload)


async def _store_variant(
    settings: Settings,
    cache: CacheStore,
    orch: NarratorOrchestrator,
    evidence_builder: EvidenceBuilder,
    docs: list[dict[str, Any]],
    base_obs: ObserveResponse,
    query: ObserveQuery,
    *,
    skip_obs_ids: set[str],
) -> str | None:
    obs_id = compute_observation_id(query, settings.pipeline_version)
    if obs_id in skip_obs_ids:
        return None

    share_url = f"/explorer?ra={query.ra:.6f}&dec={query.dec:.6f}&fov={query.fov:.3f}"
    obs_variant = base_obs.model_copy(
        update={
            "observation_id": obs_id,
            "query": query.model_copy(update={"share_url": share_url}),
            "cached_at": datetime.now(UTC).isoformat(),
        }
    )
    ev = evidence_builder.build(obs_variant, docs=docs)
    story, final_ev = await orch.run_with_evidence(obs_variant, ev)

    cache.set_json("observe", cache.versioned_key(obs_id), obs_variant.model_dump(mode="json"))
    cache.set_json(
        "evidence", cache.versioned_key(f"ev:{obs_id}"), final_ev.model_dump(mode="json")
    )
    cache.set_json(
        "narrative",
        _narrative_cache_key(settings, cache, obs_id),
        story.model_dump(mode="json"),
    )
    return obs_id


async def _restore_real_snapshot(
    settings: Settings,
    cache: CacheStore,
    db: DatabaseStore,
    orch: NarratorOrchestrator,
    evidence_builder: EvidenceBuilder,
    snapshot: ObserveResponse,
) -> str:
    obs_id = snapshot.observation_id
    stamped = snapshot.model_copy(update={"cached_at": datetime.now(UTC).isoformat()})
    cache.set_json("observe", cache.versioned_key(obs_id), stamped.model_dump(mode="json"))

    ev_key = cache.versioned_key(f"ev:{obs_id}")
    cached_ev = cache.get_json("evidence", ev_key)
    if cached_ev is not None:
        ev = EvidenceStoreResponse.model_validate(cached_ev)
    else:
        docs = await db.search_documents(
            stamped.constellation,
            object_identifiers=[o.name for o in stamped.detected_objects[:5]],
            limit=5,
        )
        ev = evidence_builder.build(stamped, docs=docs)

    n_key = _narrative_cache_key(settings, cache, obs_id)
    cached_nar = cache.get_json("narrative", n_key)
    if cached_nar is not None:
        story = CosmicNarratorResponse.model_validate(cached_nar)
        final_ev = ev
    else:
        story, final_ev = await orch.run_with_evidence(stamped, ev)

    cache.set_json("evidence", ev_key, final_ev.model_dump(mode="json"))
    cache.set_json("narrative", n_key, story.model_dump(mode="json"))
    return obs_id


async def warm_five_verifications(
    settings: Settings | None = None,
    cache: CacheStore | None = None,
    db: DatabaseStore | None = None,
) -> dict[str, Any]:
    eff_settings = settings or get_settings()
    eff_cache = cache or CacheStore(eff_settings)
    eff_db = db or DatabaseStore(eff_settings)
    owns_db = db is None

    try:
        ingested_docs = await run_ingest_docs(eff_settings, eff_db)
        real_snapshot = _load_real_snapshot(eff_settings.cache_dir)
        skip_ids: set[str] = {real_snapshot.observation_id} if real_snapshot is not None else set()

        presets = list_target_presets() or list(PRESET_TARGETS)
        presets_by_id = {p.id: p for p in presets}
        datasets_by_id: dict[str, SyntheticDataset] = {}

        evidence_builder = EvidenceBuilder()
        orch = NarratorOrchestrator(
            settings=eff_settings,
            docs_store=eff_db,
            ads_adapter=None,
            llm_provider=TemplateLlmProvider(),
        )

        warmed_by_target: dict[str, list[str]] = {}
        stored_ids: set[str] = set()

        with tempfile.TemporaryDirectory(prefix="spherex-warm-verifications-") as tmp_dir:
            tmp_root = Path(tmp_dir)
            for preset in presets:
                scenario = build_synthetic_scenario_for_target(preset, seed=42)
                dataset = generate_synthetic_dataset(scenario, tmp_root / preset.id)
                datasets_by_id[preset.id] = dataset

                pipe = ObservePipeline(
                    settings=eff_settings,
                    archive=SyntheticArchiveAdapter(dataset),
                    catalogs=SyntheticCatalogAdapter(),
                )
                docs = await eff_db.search_documents(
                    preset.name, object_identifiers=[preset.id], limit=5
                )

                target_ids: list[str] = []
                for mf in (12, 4):
                    run_ra, run_dec = preset.ra_deg, preset.dec_deg
                    if preset.expected_variable and dataset.ground_truth.get("variable"):
                        var_gt = dataset.ground_truth["variable"]
                        run_ra = float(var_gt["ra"])
                        run_dec = float(var_gt["dec"])

                    base_query = ObserveQuery(
                        ra=run_ra,
                        dec=run_dec,
                        fov=preset.default_fov_deg,
                        mode=preset.recommended_mode,
                        max_frames=mf,
                        target=preset.id,
                    )
                    base_obs = await pipe.run(base_query)

                    # Store direct base observation_id plus every UI/API query shape.
                    queries_to_store = [base_query, *_build_query_variants(preset, mf)]
                    for q in queries_to_store:
                        q_obs_id = compute_observation_id(q, eff_settings.pipeline_version)
                        if q_obs_id in stored_ids:
                            continue
                        saved_id = await _store_variant(
                            eff_settings,
                            eff_cache,
                            orch,
                            evidence_builder,
                            docs,
                            base_obs,
                            q,
                            skip_obs_ids=skip_ids,
                        )
                        if saved_id is not None:
                            stored_ids.add(saved_id)
                            target_ids.append(saved_id)

                warmed_by_target[preset.id] = target_ids

            restored_real_id: str | None = None
            if real_snapshot is not None:
                restored_real_id = await _restore_real_snapshot(
                    eff_settings,
                    eff_cache,
                    eff_db,
                    orch,
                    evidence_builder,
                    real_snapshot,
                )

            class _SyntheticBenchmarkPipeline:
                async def run(self, query: ObserveQuery) -> ObserveResponse:
                    preset_obj = presets_by_id[query.target or ""]
                    ds = datasets_by_id[preset_obj.id]
                    eff_query = query
                    if preset_obj.expected_variable and ds.ground_truth.get("variable"):
                        var_gt = ds.ground_truth["variable"]
                        eff_query = query.model_copy(
                            update={"ra": float(var_gt["ra"]), "dec": float(var_gt["dec"])}
                        )
                    return await ObservePipeline(
                        settings=eff_settings,
                        archive=SyntheticArchiveAdapter(ds),
                        catalogs=SyntheticCatalogAdapter(),
                    ).run(eff_query)

            bench: BenchmarkRunResponse = await run_benchmarks(
                eff_settings,
                eff_cache,
                pipeline=_SyntheticBenchmarkPipeline(),  # type: ignore[arg-type]
                data_source="synthetic",
            )

        return {
            "ingested_docs": ingested_docs,
            "redis_available": eff_cache.redis_available(),
            "warmed_count": len(stored_ids),
            "warmed_by_target": warmed_by_target,
            "restored_real_observation_id": restored_real_id,
            "benchmark_run_id": bench.run_id,
            "benchmarks": [
                {"target_id": r.target_id, "status": r.status, "measured": r.measured_value}
                for r in bench.results
            ],
        }
    finally:
        if owns_db:
            await eff_db.close()


def main() -> None:
    summary = asyncio.run(warm_five_verifications())
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
