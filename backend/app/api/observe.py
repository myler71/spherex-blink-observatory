import asyncio
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.api.deps import AppContainer, client_ip_from_request, get_container
from app.schemas.observe import ObserveQuery, ObserveResponse, SpectrumResponse
from app.science.coords import angular_separation_key, parse_ra_dec
from app.science.targets import get_target_preset

router = APIRouter(tags=["observe"])


@router.get("/observe", response_model=ObserveResponse)
async def observe_patch(
    request: Request,
    ra: str | None = Query(default=None),
    dec: str | None = Query(default=None),
    fov: float = Query(default=0.08, ge=0.01, le=0.5),
    release: str | None = Query(default=None),
    mode: Literal["motion", "variability", "both"] = Query(default="both"),
    detector: int | None = Query(default=None, ge=1, le=6),
    wave_min: float | None = Query(default=None, ge=0.5, le=6.0),
    wave_max: float | None = Query(default=None, ge=0.5, le=6.0),
    max_frames: int = Query(default=12, ge=1, le=24),
    propagate: bool = Query(default=True),
    target: str | None = Query(default=None),
    include_overlays: bool = Query(default=True),
    include_csa_neossat: bool = Query(default=False),
    include_horizons: bool = Query(default=False),
    include_variance: bool = Query(default=True),
    linear: float = Query(default=0.15, ge=0.001, le=1.0),
    min_pct: float = Query(default=1.5, ge=0.0, le=49.0),
    max_pct: float = Query(default=99.4, ge=50.0, le=100.0),
    invert: bool = Query(default=False),
    container: AppContainer = Depends(get_container),
) -> ObserveResponse:
    container.rate_limiter.check(
        "observe", client_ip_from_request(request), container.settings.observe_rate_limit_per_min
    )

    if target and (ra is None or dec is None):
        preset = get_target_preset(target)
        if preset is None:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": f"Unknown target preset: {target}"},
            )
        ra_val, dec_val = preset.ra_deg, preset.dec_deg
    elif ra is not None and dec is not None:
        try:
            ra_val, dec_val = parse_ra_dec(ra, dec)
        except ValueError as exc:
            raise HTTPException(
                status_code=422,
                detail={"code": "VALIDATION_ERROR", "message": str(exc)},
            ) from exc
    else:
        raise HTTPException(
            status_code=422,
            detail={
                "code": "VALIDATION_ERROR",
                "message": "Provide either (ra, dec) or a valid target preset ID.",
            },
        )

    obs_query = ObserveQuery(
        ra=ra_val,
        dec=dec_val,
        fov=fov,
        release=release,
        mode=mode,
        detector=detector,
        wave_min=wave_min,
        wave_max=wave_max,
        max_frames=min(max_frames, container.settings.spherex_max_frames_cap),
        propagate=propagate,
        target=target,
        include_overlays=include_overlays,
        include_csa_neossat=include_csa_neossat,
        include_horizons=include_horizons,
        include_variance=include_variance,
        linear=linear,
        min_pct=min_pct,
        max_pct=max_pct,
        invert=invert,
    )

    # Check warm cache first
    from app.science.pipeline import compute_observation_id

    obs_id = compute_observation_id(obs_query, container.settings.pipeline_version)
    cache_key = container.cache.versioned_key(obs_id)
    cached = container.cache.get_json("observe", cache_key)
    if cached is not None:
        resp_obj = ObserveResponse.model_validate(cached)
        return resp_obj.model_copy(update={"served_from": "cache"})

    # Singleflight coalescing for concurrent identical cold requests
    if cache_key in container.inflight_observe:
        return await asyncio.shield(container.inflight_observe[cache_key])  # type: ignore[no-any-return]

    loop = asyncio.get_running_loop()
    fut: asyncio.Future[ObserveResponse] = loop.create_future()
    # Retrieve unobserved exceptions without changing what coalesced awaiters receive.
    fut.add_done_callback(lambda done: None if done.cancelled() else done.exception())
    container.inflight_observe[cache_key] = fut
    try:
        async with asyncio.timeout(70.0):
            result = await container.pipeline.run(obs_query)
        stamped = result.model_copy(update={"cached_at": datetime.now(UTC).isoformat()})
        container.cache.set_json("observe", cache_key, stamped.model_dump(mode="json"))
        if not fut.done():
            fut.set_result(result)
        return result
    except LookupError as exc:
        err = HTTPException(
            status_code=404,
            detail={"code": "NO_COVERAGE", "message": str(exc)},
        )
        if not fut.done():
            fut.set_exception(err)
        raise err from exc
    except (RuntimeError, TimeoutError) as exc:
        msg = str(exc).strip() or (
            "Observation pipeline timeout after 70 seconds"
            if isinstance(exc, TimeoutError)
            else "Upstream SPHEREx archive operation failed"
        )
        msg_lower = msg.lower()

        if "timeout" in msg_lower or "timed out" in msg_lower or "504" in msg_lower:
            if "archive" in msg_lower or "tap" in msg_lower or "search" in msg_lower:
                err_code = "UPSTREAM_ARCHIVE_TIMEOUT"
                stage = "archive_search"
            else:
                err_code = "UPSTREAM_TIMEOUT"
                stage = "pipeline" if "pipeline" in msg_lower else "cutout_fetch"
        elif "archive" in msg_lower or "tap" in msg_lower or "search" in msg_lower:
            err_code = "UPSTREAM_ARCHIVE_FAILURE"
            stage = "archive_search"
        else:
            err_code = "UPSTREAM_CUTOUT_FAILURE"
            stage = "cutout_fetch"

        err = HTTPException(
            status_code=502,
            detail={
                "code": err_code,
                "message": msg,
                "details": {
                    "stage": stage,
                    "error_type": type(exc).__name__,
                },
            },
        )
        if not fut.done():
            fut.set_exception(err)
        raise err from exc
    except Exception as exc:
        err = HTTPException(
            status_code=500,
            detail={
                "code": "INTERNAL_ERROR",
                "message": f"Observe pipeline error ({type(exc).__name__}): {exc}",
            },
        )
        if not fut.done():
            fut.set_exception(err)
        raise err from exc
    finally:
        container.inflight_observe.pop(cache_key, None)
        if not fut.done():
            fut.set_exception(RuntimeError("Observe request aborted or cancelled"))


@router.get("/observe/{observation_id}", response_model=ObserveResponse)
async def get_stored_observation(
    observation_id: str,
    container: AppContainer = Depends(get_container),
) -> ObserveResponse:
    cache_key = container.cache.versioned_key(observation_id)
    cached = container.cache.get_json("observe", cache_key)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Observation {observation_id} not found"},
        )
    resp = ObserveResponse.model_validate(cached)
    return resp.model_copy(update={"served_from": "cache"})


@router.get("/observe/{observation_id}/spectrum", response_model=SpectrumResponse)
async def get_observation_spectrum(
    observation_id: str,
    object_id: str | None = Query(default=None),
    ra: float | None = Query(default=None, ge=0.0, le=360.0),
    dec: float | None = Query(default=None, ge=-90.0, le=90.0),
    container: AppContainer = Depends(get_container),
) -> SpectrumResponse:
    cache_key = container.cache.versioned_key(observation_id)
    cached = container.cache.get_json("observe", cache_key)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Observation {observation_id} not found"},
        )
    obs = ObserveResponse.model_validate(cached)

    # Extract spectrum points from stored detected_object light curve or query coords
    target_obj = None
    if object_id:
        target_obj = next((o for o in obs.detected_objects if o.id == object_id), None)
    elif ra is not None and dec is not None and obs.detected_objects:
        target_obj = min(
            obs.detected_objects,
            key=lambda o: angular_separation_key(o.ra, o.dec, ra, dec),
        )
    elif obs.detected_objects:
        target_obj = obs.detected_objects[0]

    from app.schemas.observe import SpectrumPoint

    pts: list[SpectrumPoint] = []
    if target_obj is not None:
        for lc in target_obj.light_curve:
            pts.append(
                SpectrumPoint(
                    obs_id=lc.obs_id,
                    mjd=lc.mjd,
                    detector=lc.detector,
                    wavelength_um=lc.wavelength_um,
                    bandwidth_um=lc.bandwidth_um,
                    flux=lc.flux,
                    flux_err=lc.flux_err,
                    snr=lc.snr,
                    contaminated=lc.contaminated,
                )
            )
        pts.sort(key=lambda p: p.wavelength_um)
        return SpectrumResponse(
            observation_id=observation_id,
            ra_deg=target_obj.ra,
            dec_deg=target_obj.dec,
            object_id=target_obj.id,
            points=pts,
        )

    return SpectrumResponse(
        observation_id=observation_id,
        ra_deg=ra if ra is not None else obs.query.ra,
        dec_deg=dec if dec is not None else obs.query.dec,
        object_id=object_id,
        points=[],
    )
