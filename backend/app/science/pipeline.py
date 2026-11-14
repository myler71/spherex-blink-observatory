import asyncio
import hashlib
import math
import time
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode

import astropy.units as u
from astropy.coordinates import SkyCoord

from app.config import Settings
from app.schemas.common import EncodedArray, ServiceStatus
from app.schemas.observe import (
    AttributionInfo,
    CatalogMatch,
    DetectedObject,
    FrameData,
    GaiaCounterpart,
    ObserveQuery,
    ObserveResponse,
    OverlayBundle,
    SelectionSummary,
    SkippedFrame,
    StageTimings,
)
from app.science.align import AlignedFrame, align_frames, build_reference_wcs
from app.science.calibrate import CalibratedFrame, calibrate_cutout
from app.science.comparisons import build_comparisons, build_flipbook_diffs
from app.science.coords import constellation_for_coord, propagate_skycoord
from app.science.detect import extract_sources
from app.science.display import render_wiseview
from app.science.link import link_detections
from app.science.motion import fit_motion
from app.science.ports import ArchivePort, CatalogOverlayPort
from app.science.select import select_observations
from app.science.stack import coadd_by_detector_visit
from app.science.targets import get_target_preset
from app.science.variability import compute_variability


def compute_observation_id(query: ObserveQuery, pipeline_version: str) -> str:
    canonical = (
        f"{round(query.ra, 5):.5f}:{round(query.dec, 5):.5f}:{round(query.fov, 4):.4f}:"
        f"{query.release or 'all'}:{query.mode}:{query.detector or 'all'}:"
        f"{query.wave_min or ''}:{query.wave_max or ''}:{query.max_frames}:"
        f"{int(query.propagate)}:{query.target or ''}:{pipeline_version}"
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"obs_{digest}"


def _build_wiseview_url(ra_deg: float, dec_deg: float, fov_deg: float) -> str:
    params = urlencode(
        {
            "ra": f"{ra_deg:.6f}",
            "dec": f"{dec_deg:.6f}",
            "size": f"{fov_deg * 3600.0:.1f}",
            "band": "3",
        }
    )
    return f"http://byw.tools/wiseview#{params}"


def _attribution_info() -> AttributionInfo:
    return AttributionInfo(
        acknowledgements={
            "NASA/IPAC IRSA SPHEREx": (
                "This publication makes use of data products from SPHEREx, a joint project of JPL and Caltech funded by NASA."
            ),
            "ESA Gaia DR3": "This work has made use of data from the European Space Agency (ESA) mission Gaia (DPAC).",
            "AllWISE": "This publication makes use of data products from WISE/NEOWISE (UCLA & JPL/Caltech).",
            "CDS SIMBAD/VizieR": "This research has made use of the SIMBAD database and VizieR, CDS, Strasbourg, France.",
            "CSA CADC NEOSSat": "This research used the Canadian Astronomy Data Centre (NRC/CSA).",
        },
        dois={
            "SPHEREx_DR1": "10.26131/IRSA678",
            "SPHEREx_QR3": "10.26131/IRSA662",
            "SPHEREx_QR2": "10.26131/IRSA652",
        },
        libraries=[
            "FastAPI",
            "Astropy",
            "Astroquery",
            "PyVO",
            "Reproject",
            "SEP",
            "Photutils",
            "SciPy",
            "LangGraph",
        ],
    )


class ObservePipeline:
    """Deep coordinator executing deterministic SPHEREx pipeline behind Archive/Catalog ports."""

    def __init__(
        self,
        settings: Settings,
        archive: ArchivePort,
        catalogs: CatalogOverlayPort | None = None,
    ) -> None:
        self.settings = settings
        self.archive = archive
        self.catalogs = catalogs

    async def run(self, query: ObserveQuery) -> ObserveResponse:
        t0 = time.perf_counter()
        stages_ms: dict[str, float] = {}
        warnings_list: list[str] = []

        # 1. Resolve target preset & epoch propagation (FR-04)
        t_s = time.perf_counter()
        ra_fetch, dec_fetch = query.ra, query.dec
        preset = get_target_preset(query.target) if query.target else None
        if query.propagate and preset is not None:
            now_mjd = (datetime.now(UTC).timestamp() / 86400.0) + 40587.0
            ra_fetch, dec_fetch = propagate_skycoord(
                ra_deg=preset.ra_deg,
                dec_deg=preset.dec_deg,
                ref_epoch_jyear=preset.ref_epoch_jyear,
                pm_ra_mas_yr=preset.pm_ra_mas_yr,
                pm_dec_mas_yr=preset.pm_dec_mas_yr,
                parallax_mas=preset.parallax_mas,
                target_mjd=now_mjd,
            )
        stages_ms["coords_ms"] = round((time.perf_counter() - t_s) * 1000.0, 2)

        # 2. Search archive observations (FR-01)
        t_s = time.perf_counter()
        releases = [query.release] if query.release else list(self.settings.spherex_releases)
        candidates = await self.archive.search_observations(ra_fetch, dec_fetch, releases=releases)
        stages_ms["search_ms"] = round((time.perf_counter() - t_s) * 1000.0, 2)
        if not candidates:
            raise LookupError(f"No SPHEREx observations cover ({ra_fetch:.5f}, {dec_fetch:.5f})")

        # 3. Select baseline-maximizing, band-matched frames (FR-02)
        t_s = time.perf_counter()
        sel = select_observations(
            candidates,
            max_frames=min(query.max_frames, self.settings.spherex_max_frames_cap),
            settings=self.settings,
            detector=query.detector,
            wave_min=query.wave_min,
            wave_max=query.wave_max,
        )
        if not sel.selected:
            raise LookupError("No SPHEREx observations match the requested filters.")
        if sel.single_visit_warning:
            warnings_list.append(sel.single_visit_warning)
        stages_ms["select_ms"] = round((time.perf_counter() - t_s) * 1000.0, 2)

        # 4. Concurrent cutout downloads + catalog overlays in parallel (FR-03, FR-16..18)
        t_s = time.perf_counter()
        epochs_mjd = [s.mjd_start for s in sel.selected]
        cutout_coro = self.archive.fetch_cutouts(sel.selected, ra_fetch, dec_fetch, query.fov)
        if query.include_overlays and self.catalogs is not None:
            cat_coro = self.catalogs.query_all(
                ra_fetch,
                dec_fetch,
                query.fov,
                epochs_mjd,
                include_neossat=query.include_csa_neossat,
                include_horizons=query.include_horizons,
            )
            fetch_results, cat_raw = await asyncio.gather(cutout_coro, cat_coro)
        else:
            fetch_results = await cutout_coro
            cat_raw = {}
        stages_ms["fetch_ms"] = round((time.perf_counter() - t_s) * 1000.0, 2)

        skipped: list[SkippedFrame] = []
        valid_paths = []
        for item in fetch_results:
            if item.local_path is None:
                skipped.append(
                    SkippedFrame(
                        obs_id=item.obs_id,
                        archive_url=item.archive_url,
                        reason=item.error or "Cutout download failed",
                    )
                )
            else:
                valid_paths.append(item)

        if not valid_paths:
            raise RuntimeError("All SPHEREx cutout downloads failed.")

        # 5. Run CPU-bound Astropy/Reproject/SEP science off event loop
        t_s = time.perf_counter()
        science_out = await asyncio.to_thread(
            self._run_science_sync,
            valid_paths,
            sel,
            query,
            ra_fetch,
            dec_fetch,
            cat_raw,
            warnings_list,
        )
        stages_ms["science_ms"] = round((time.perf_counter() - t_s) * 1000.0, 2)
        stages_ms["total_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

        obs_id_str = compute_observation_id(query, self.settings.pipeline_version)
        constellation = constellation_for_coord(ra_fetch, dec_fetch)
        share_url = f"/explorer?ra={query.ra:.6f}&dec={query.dec:.6f}&fov={query.fov:.3f}"
        query_echo = query.model_copy(update={"share_url": share_url})

        return ObserveResponse(
            observation_id=obs_id_str,
            pipeline_version=self.settings.pipeline_version,
            served_from="live",
            query=query_echo,
            constellation=constellation,
            reference_grid=science_out["grid"],
            selection=SelectionSummary(
                total_candidates=sel.total_candidates,
                selected_count=len(science_out["frames"]),
                visits_count=sel.visits_count,
                wavelength_bins_count=sel.wavelength_bins_count,
                matching_tolerance_um=sel.matching_tolerance_um,
                baseline_days=sel.baseline_days,
            ),
            frames=science_out["frames"],
            comparisons=science_out["comparisons"],
            coadds=science_out["coadds"],
            detected_objects=science_out["detected_objects"],
            overlays=science_out["overlays"],
            warnings=science_out["warnings"],
            skipped=skipped,
            attribution=_attribution_info(),
            timings=StageTimings(total_ms=stages_ms["total_ms"], stages_ms=stages_ms),
        )

    def _run_science_sync(
        self,
        valid_paths: list[Any],
        sel: Any,
        query: ObserveQuery,
        ra_center: float,
        dec_center: float,
        cat_raw: dict[str, Any],
        warnings_list: list[str],
    ) -> dict[str, Any]:
        meta_by_id = {m.obs_id: m for m in sel.selected}
        calibrated: list[CalibratedFrame] = []
        for item in valid_paths:
            m = meta_by_id.get(item.obs_id)
            rel = m.collection if m else "spherex_dr1"
            cal = calibrate_cutout(
                item.local_path,
                archive_url=item.archive_url,
                release=rel,
                settings=self.settings,
            )
            warnings_list.extend(cal.warnings)
            calibrated.append(cal)

        ref_wcs, grid = build_reference_wcs(
            ra_center,
            dec_center,
            query.fov,
            pixel_scale_arcsec=self.settings.spherex_native_pixel_scale_arcsec,
        )
        aligned: list[AlignedFrame] = align_frames(calibrated, ref_wcs, grid)
        flip_diffs = build_flipbook_diffs(aligned)
        per_frame_dets = [extract_sources(a, self.settings) for a in aligned]
        tracks = link_detections(per_frame_dets, aligned, self.settings)

        gaia_ok = cat_raw.get("gaia_status") == "up"
        gaia_trunc = bool(cat_raw.get("gaia_truncated", False))
        gaia_rows = cat_raw.get("gaia_rows", [])
        simbad_rows = cat_raw.get("simbad_rows", [])
        allwise_rows = cat_raw.get("allwise_rows", [])

        detected_objects: list[DetectedObject] = []
        for tr in tracks:
            motion, dx_yr, dy_yr, is_moving = fit_motion(tr, grid.pixel_scale_arcsec, self.settings)
            var_bins, lc_pts, is_var = compute_variability(tr, self.settings)

            # Gaia DR3 matching (FR-16, FR-17)
            gaia_cp = self._match_gaia(tr.mean_ra, tr.mean_dec, gaia_ok, gaia_trunc, gaia_rows)
            cat_matches = self._match_catalogs(tr.mean_ra, tr.mean_dec, simbad_rows, allwise_rows)
            obj_name = cat_matches[0].identifier if cat_matches else tr.track_id

            detected_objects.append(
                DetectedObject(
                    id=tr.track_id,
                    name=obj_name,
                    x=round(tr.mean_x, 3),
                    y=round(tr.mean_y, 3),
                    ra=round(tr.mean_ra, 6),
                    dec=round(tr.mean_dec, 6),
                    snr=round(tr.mean_snr, 2),
                    contaminated=tr.contaminated,
                    n_detections=len(tr.observations),
                    motion=motion,
                    dx_pixels_per_yr=dx_yr,
                    dy_pixels_per_yr=dy_yr,
                    is_candidate_moving=is_moving,
                    variability=var_bins,
                    is_variable=is_var,
                    light_curve=lc_pts,
                    gaia_counterpart=gaia_cp,
                    catalog_matches=cat_matches,
                )
            )

        frame_schemas: list[FrameData] = []
        for a, fdiff in zip(aligned, flip_diffs, strict=False):
            disp = render_wiseview(
                a.image,
                linear=query.linear,
                min_pct=query.min_pct,
                max_pct=query.max_pct,
                invert=query.invert,
            )
            fdiff_disp = render_wiseview(
                fdiff,
                linear=query.linear,
                min_pct=query.min_pct,
                max_pct=query.max_pct,
                invert=query.invert,
            )
            ny, nx = a.image.shape
            frame_schemas.append(
                FrameData(
                    obs_id=a.obs_id,
                    mjd=a.mjd,
                    iso_date=a.provenance.iso_date,
                    release=a.release,
                    detector=a.detector,
                    central_wavelength_um=a.provenance.central_wavelength_um,
                    bandwidth_um=a.provenance.bandwidth_um,
                    width=nx,
                    height=ny,
                    pixels=EncodedArray.from_numpy(a.image),
                    variance=EncodedArray.from_numpy(a.variance)
                    if query.include_variance
                    else None,
                    flags_mask=EncodedArray.from_numpy(a.flags_u8),
                    display_u8=EncodedArray.from_numpy(disp),
                    flipbook_diff_u8=EncodedArray.from_numpy(fdiff_disp),
                    provenance=a.provenance,
                    flag_summary=a.flag_summary,
                )
            )

        comp_prod, _, _ = build_comparisons(aligned, self.settings)
        coadds = [prod for prod, _ in coadd_by_detector_visit(aligned, self.settings)]

        overlays = OverlayBundle(
            gaia_dr3_status=ServiceStatus(status=cat_raw.get("gaia_status", "not_configured")),
            gaia_dr3=gaia_rows,
            gaia_truncated=gaia_trunc,
            allwise_status=ServiceStatus(status=cat_raw.get("allwise_status", "not_configured")),
            allwise=allwise_rows,
            simbad_status=ServiceStatus(status=cat_raw.get("simbad_status", "not_configured")),
            simbad=simbad_rows,
            vizier_status=ServiceStatus(status=cat_raw.get("vizier_status", "not_configured")),
            vizier=cat_raw.get("vizier_rows", []),
            ned_status=ServiceStatus(status=cat_raw.get("ned_status", "not_configured")),
            ned=cat_raw.get("ned_rows", []),
            neossat_status=ServiceStatus(status=cat_raw.get("neossat_status", "not_configured")),
            neossat=cat_raw.get("neossat_rows", []),
            horizons_status=ServiceStatus(status=cat_raw.get("horizons_status", "not_configured")),
            horizons=cat_raw.get("horizons_rows", []),
            wiseview_url=_build_wiseview_url(ra_center, dec_center, query.fov),
        )

        return {
            "grid": grid,
            "frames": frame_schemas,
            "comparisons": comp_prod,
            "coadds": coadds,
            "detected_objects": detected_objects,
            "overlays": overlays,
            "warnings": warnings_list,
        }

    def _match_gaia(
        self,
        ra_deg: float,
        dec_deg: float,
        gaia_ok: bool,
        gaia_truncated: bool,
        gaia_rows: list[dict[str, Any]],
    ) -> GaiaCounterpart:
        if not gaia_ok or gaia_truncated:
            reason = "Gaia DR3 query truncated" if gaia_truncated else "Gaia DR3 query unavailable"
            return GaiaCounterpart(
                status="unknown",
                wording=f"Gaia DR3 counterpart unknown ({reason}).",
            )
        if not gaia_rows:
            return GaiaCounterpart(
                status="no_counterpart",
                wording="no Gaia DR3 counterpart",
            )

        target_sc = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
        best_sep = math.inf
        best_row: dict[str, Any] | None = None
        for row in gaia_rows:
            g_ra = row.get("ra_epoch", row.get("ra"))
            g_dec = row.get("dec_epoch", row.get("dec"))
            if g_ra is None or g_dec is None:
                continue
            sc = SkyCoord(ra=float(g_ra) * u.deg, dec=float(g_dec) * u.deg, frame="icrs")
            sep_as = float(target_sc.separation(sc).arcsec)
            if sep_as < best_sep:
                best_sep = sep_as
                best_row = row

        if best_row is not None and best_sep <= self.settings.gaia_match_radius_arcsec:
            return GaiaCounterpart(
                status="has_counterpart",
                wording=f"Matched Gaia DR3 {best_row.get('source_id')}",
                separation_arcsec=round(best_sep, 3),
                source_id=str(best_row.get("source_id")),
                ra_deg=float(best_row.get("ra_epoch") or best_row["ra"]),
                dec_deg=float(best_row.get("dec_epoch") or best_row["dec"]),
                pmra_mas_yr=float(best_row["pmra"]) if best_row.get("pmra") is not None else None,
                pmdec_mas_yr=float(best_row["pmdec"])
                if best_row.get("pmdec") is not None
                else None,
                parallax_mas=float(best_row["parallax"])
                if best_row.get("parallax") is not None
                else None,
                phot_g_mean_mag=(
                    float(best_row["phot_g_mean_mag"])
                    if best_row.get("phot_g_mean_mag") is not None
                    else None
                ),
            )
        return GaiaCounterpart(
            status="no_counterpart",
            wording="no Gaia DR3 counterpart",
        )

    def _match_catalogs(
        self,
        ra_deg: float,
        dec_deg: float,
        simbad_rows: list[dict[str, Any]],
        allwise_rows: list[dict[str, Any]],
    ) -> list[CatalogMatch]:
        matches: list[CatalogMatch] = []
        target_sc = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")

        for cat_name, rows, id_key, rad in [
            ("SIMBAD", simbad_rows, "main_id", self.settings.simbad_match_radius_arcsec),
            ("AllWISE", allwise_rows, "designation", self.settings.gaia_match_radius_arcsec + 2.0),
        ]:
            best_sep = math.inf
            best_row: dict[str, Any] | None = None
            for r in rows:
                r_ra = r.get("ra_epoch", r.get("ra"))
                r_dec = r.get("dec_epoch", r.get("dec"))
                if r_ra is None or r_dec is None:
                    continue
                sc = SkyCoord(ra=float(r_ra) * u.deg, dec=float(r_dec) * u.deg, frame="icrs")
                sep_as = float(target_sc.separation(sc).arcsec)
                if sep_as <= rad and sep_as < best_sep:
                    best_sep = sep_as
                    best_row = r
            if best_row is not None:
                ident = str(best_row.get(id_key, "unknown"))
                matches.append(
                    CatalogMatch(
                        catalog=cat_name,
                        identifier=ident,
                        otype=str(best_row.get("otype")) if best_row.get("otype") else None,
                        separation_arcsec=round(best_sep, 3),
                        ra_deg=float(best_row["ra_epoch"])
                        if best_row.get("ra_epoch") is not None
                        else float(best_row["ra"]),
                        dec_deg=float(best_row["dec_epoch"])
                        if best_row.get("dec_epoch") is not None
                        else float(best_row["dec"]),
                        url=best_row.get("url"),
                        metadata=best_row,
                    )
                )
        return matches
