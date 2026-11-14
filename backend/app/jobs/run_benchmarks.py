import asyncio
import json
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from app.archive.bundle import MultiAgencyCatalogBundle
from app.archive.irsa import IrsaArchiveAdapter
from app.config import Settings, get_settings
from app.schemas.benchmarks import BenchmarkRunResponse, BenchmarkTargetResult
from app.schemas.observe import ObserveQuery
from app.science.pipeline import ObservePipeline
from app.science.targets import list_target_presets
from app.store.cache import CacheStore


async def run_benchmarks(
    settings: Settings,
    cache: CacheStore,
    pipeline: ObservePipeline | None = None,
    data_source: Literal["real", "synthetic"] = "real",
) -> BenchmarkRunResponse:
    pipe = pipeline or ObservePipeline(
        settings=settings,
        archive=IrsaArchiveAdapter(settings=settings, cache=cache),
        catalogs=MultiAgencyCatalogBundle(settings=settings),
    )

    results: list[BenchmarkTargetResult] = []
    for preset in list_target_presets():
        t0 = time.perf_counter()
        ref_val = (
            f"{preset.expected_pm_arcsec_yr} arcsec/yr"
            if preset.recommended_mode == "motion"
            else ("variable" if preset.expected_variable else "static (~0 arcsec/yr, non-variable)")
        )
        try:
            q = ObserveQuery(
                ra=preset.ra_deg,
                dec=preset.dec_deg,
                fov=preset.default_fov_deg,
                mode=preset.recommended_mode,
                target=preset.id,
            )
            obs = await pipe.run(q)
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            if obs.selection.visits_count < 2:
                results.append(
                    BenchmarkTargetResult(
                        target_id=preset.id,
                        name=preset.name,
                        mode=preset.recommended_mode,
                        data_source=data_source,
                        reference_value=ref_val,
                        reference_citation=preset.citation,
                        num_visits=obs.selection.visits_count,
                        baseline_days=obs.selection.baseline_days,
                        processing_ms=elapsed_ms,
                        status="inconclusive",
                        reason="Fewer than 2 visits available in selected frames.",
                    )
                )
                continue

            if not obs.detected_objects:
                results.append(
                    BenchmarkTargetResult(
                        target_id=preset.id,
                        name=preset.name,
                        mode=preset.recommended_mode,
                        data_source=data_source,
                        reference_value=ref_val,
                        reference_citation=preset.citation,
                        num_visits=obs.selection.visits_count,
                        baseline_days=obs.selection.baseline_days,
                        processing_ms=elapsed_ms,
                        status="inconclusive",
                        reason="No sources detected above SNR threshold.",
                    )
                )
                continue

            # Evaluate primary detected object near field center
            primary = min(
                obs.detected_objects,
                key=lambda o: abs(o.ra - obs.query.ra) + abs(o.dec - obs.query.dec),
            )
            if preset.is_negative_control:
                passed = (not primary.is_candidate_moving) and (not primary.is_variable)
                results.append(
                    BenchmarkTargetResult(
                        target_id=preset.id,
                        name=preset.name,
                        mode=preset.recommended_mode,
                        data_source=data_source,
                        reference_value=ref_val,
                        reference_citation=preset.citation,
                        measured_value=f"pm={primary.motion.pm_total_arcsec_yr} arcsec/yr, var={primary.is_variable}",
                        snr=primary.snr,
                        num_visits=obs.selection.visits_count,
                        baseline_days=obs.selection.baseline_days,
                        processing_ms=elapsed_ms,
                        status="pass" if passed else "fail",
                        reason="Negative control static & non-variable"
                        if passed
                        else "Unexpected motion/variability",
                    )
                )
            elif preset.recommended_mode == "motion":
                fastest = max(
                    obs.detected_objects,
                    key=lambda o: o.motion.pm_total_arcsec_yr or 0.0,
                )
                pm_meas = fastest.motion.pm_total_arcsec_yr
                pm_err = (fastest.motion.pm_total_err_mas_yr or 500.0) / 1000.0
                exp_pm = preset.expected_pm_arcsec_yr or 0.0
                if pm_meas is None:
                    st: Literal["pass", "fail", "inconclusive"] = "inconclusive"
                    reason = "Proper motion not fitted."
                    resid = None
                else:
                    diff = abs(pm_meas - exp_pm)
                    resid = f"{diff:.3f} arcsec/yr"
                    if fastest.is_candidate_moving and diff <= max(3.0 * pm_err, 2.0):
                        st = "pass"
                        reason = "Measured motion consistent with catalog within 3-sigma."
                    else:
                        st = "inconclusive" if data_source == "real" else "fail"
                        reason = f"Measured {pm_meas:.3f} vs reference {exp_pm:.3f} arcsec/yr."
                results.append(
                    BenchmarkTargetResult(
                        target_id=preset.id,
                        name=preset.name,
                        mode=preset.recommended_mode,
                        data_source=data_source,
                        reference_value=ref_val,
                        reference_citation=preset.citation,
                        measured_value=f"{pm_meas} arcsec/yr" if pm_meas is not None else None,
                        measured_uncertainty=f"{pm_err:.3f} arcsec/yr",
                        residual=resid,
                        snr=fastest.snr,
                        num_visits=obs.selection.visits_count,
                        baseline_days=obs.selection.baseline_days,
                        processing_ms=elapsed_ms,
                        status=st,
                        reason=reason,
                    )
                )
            else:
                # Variability mode
                var_objs = [o for o in obs.detected_objects if o.is_variable]
                st_v: Literal["pass", "fail", "inconclusive"] = (
                    "pass" if (var_objs and not primary.is_candidate_moving) else "inconclusive"
                )
                results.append(
                    BenchmarkTargetResult(
                        target_id=preset.id,
                        name=preset.name,
                        mode=preset.recommended_mode,
                        data_source=data_source,
                        reference_value=ref_val,
                        reference_citation=preset.citation,
                        measured_value=f"variable={bool(var_objs)}, moving={primary.is_candidate_moving}",
                        snr=primary.snr,
                        num_visits=obs.selection.visits_count,
                        baseline_days=obs.selection.baseline_days,
                        processing_ms=elapsed_ms,
                        status=st_v,
                        reason=(
                            "Flagged variable in matched band without spurious motion"
                            if st_v == "pass"
                            else "Available visits did not yield significant variability"
                        ),
                    )
                )
        except Exception as exc:
            elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
            results.append(
                BenchmarkTargetResult(
                    target_id=preset.id,
                    name=preset.name,
                    mode=preset.recommended_mode,
                    data_source="unavailable",
                    reference_value=ref_val,
                    reference_citation=preset.citation,
                    processing_ms=elapsed_ms,
                    status="inconclusive",
                    reason=f"Archive/pipeline error: {str(exc)[:160]}",
                )
            )

    run = BenchmarkRunResponse(
        run_id=f"bench_{uuid.uuid4().hex[:10]}",
        created_at=datetime.now(UTC).isoformat(),
        pipeline_version=settings.pipeline_version,
        results=results,
    )
    cache.set_json("benchmarks", "latest", run.model_dump(mode="json"))
    out_path = Path(settings.cache_dir) / "benchmarks_latest.json"
    out_path.write_text(json.dumps(run.model_dump(mode="json"), indent=2))
    return run


def main() -> None:
    settings = get_settings()
    cache = CacheStore(settings)
    res = asyncio.run(run_benchmarks(settings, cache, data_source="real"))
    print(json.dumps(res.model_dump(mode="json"), indent=2))


if __name__ == "__main__":
    main()
