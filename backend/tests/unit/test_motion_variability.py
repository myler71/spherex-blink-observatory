from pathlib import Path

import numpy as np
import pytest

from app.config import Settings
from app.science.align import align_frames, build_reference_wcs
from app.science.calibrate import calibrate_cutout
from app.science.detect import extract_sources
from app.science.link import link_detections
from app.science.motion import fit_motion
from app.science.variability import compute_variability
from tests.synthetic.fits_generator import SyntheticScenario, generate_synthetic_dataset


def test_subpixel_mover_065px_recovered_and_50_static_stars_zero_false_movers(
    tmp_path: Path,
) -> None:
    settings = Settings()
    # 0.65 px at 6.16"/px over 1 year = 4.004"/yr
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.18,
            num_visits=2,
            exposures_per_visit=2,
            visit_gap_days=365.25,
            detectors=[2],
            n_static_stars=50,
            mover_pm_ra_arcsec_yr=4.004,
            mover_pm_dec_arcsec_yr=0.0,
            mover_flux=70.0,
            noise_sigma=0.05,
        ),
        tmp_path,
    )
    cal = [
        calibrate_cutout(f.fits_path, archive_url=f.obs_id, release="spherex_dr1", settings=settings)
        for f in ds.frames
    ]
    ref_wcs, grid = build_reference_wcs(180.0, 20.0, 0.18, settings.spherex_native_pixel_scale_arcsec)
    aligned = align_frames(cal, ref_wcs, grid)
    per_frame = [extract_sources(a, settings) for a in aligned]
    tracks = link_detections(per_frame, aligned, settings)

    movers = []
    false_movers = []
    gt_mover = ds.ground_truth["mover"]
    for tr in tracks:
        m, dx_yr, dy_yr, is_moving = fit_motion(tr, grid.pixel_scale_arcsec, settings)
        dist_gt = np.hypot(
            (tr.mean_ra - gt_mover["ra0"]) * np.cos(np.deg2rad(20.0)) * 3600.0,
            (tr.mean_dec - gt_mover["dec0"]) * 3600.0,
        )
        if dist_gt < 5.0:
            movers.append((m, is_moving))
        elif is_moving:
            false_movers.append((tr.mean_ra, tr.mean_dec, m))

    assert len(movers) == 1
    mover_meas, is_moving = movers[0]
    assert is_moving is True
    assert mover_meas.pm_ra_cosdec_mas_yr is not None
    assert abs(mover_meas.pm_ra_cosdec_mas_yr / 1000.0 - 4.004) <= 0.15 * 6.16
    assert len(false_movers) == 0


def test_cos_dec_factor_at_dec_60_and_single_visit_null_motion(tmp_path: Path) -> None:
    settings = Settings()
    # Dec = 60 deg: cos(60) = 0.5 -> mu_alpha* must reflect true angular rate
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            center_ra=120.0,
            center_dec=60.0,
            fov_deg=0.08,
            num_visits=2,
            exposures_per_visit=1,
            visit_gap_days=365.25,
            detectors=[2],
            n_static_stars=4,
            mover_pm_ra_arcsec_yr=6.0,
            mover_pm_dec_arcsec_yr=0.0,
            mover_flux=70.0,
            noise_sigma=0.05,
        ),
        tmp_path,
    )
    cal = [
        calibrate_cutout(f.fits_path, archive_url=f.obs_id, release="spherex_dr1", settings=settings)
        for f in ds.frames
    ]
    ref_wcs, grid = build_reference_wcs(120.0, 60.0, 0.08, settings.spherex_native_pixel_scale_arcsec)
    aligned = align_frames(cal, ref_wcs, grid)
    per_frame = [extract_sources(a, settings) for a in aligned]
    tracks = link_detections(per_frame, aligned, settings)
    gt_mover = ds.ground_truth["mover"]
    mover_track = min(
        tracks,
        key=lambda t: np.hypot(
            (t.mean_ra - gt_mover["ra0"]) * 0.5, t.mean_dec - gt_mover["dec0"]
        ),
    )
    m, _, _, is_moving = fit_motion(mover_track, grid.pixel_scale_arcsec, settings)
    assert is_moving is True
    assert m.pm_ra_cosdec_mas_yr == pytest.approx(6000.0, abs=600.0)

    # Single-visit track returns null motion with reason
    single_tracks = link_detections([per_frame[0]], [aligned[0]], settings)
    m_single, _, _, is_moving_single = fit_motion(single_tracks[0], grid.pixel_scale_arcsec, settings)
    assert is_moving_single is False
    assert m_single.pm_total_mas_yr is None
    assert m_single.reason is not None


def test_variability_ignores_sloped_spectrum_but_flags_30pct_same_band_change(
    tmp_path: Path,
) -> None:
    settings = Settings()
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=3,
            exposures_per_visit=2,
            visit_gap_days=90.0,
            detectors=[1, 6],  # wildly different wavelengths -> tests LVF trap!
            n_static_stars=4,
            variable_amplitude=0.35,
            variable_flux=60.0,
            sloped_star_flux=30.0,
            noise_sigma=0.10,
        ),
        tmp_path,
    )
    cal = [
        calibrate_cutout(f.fits_path, archive_url=f.obs_id, release="spherex_dr1", settings=settings)
        for f in ds.frames
    ]
    ref_wcs, grid = build_reference_wcs(180.0, 20.0, 0.08, settings.spherex_native_pixel_scale_arcsec)
    aligned = align_frames(cal, ref_wcs, grid)
    per_frame = [extract_sources(a, settings) for a in aligned]
    tracks = link_detections(per_frame, aligned, settings)

    gt_var = ds.ground_truth["variable"]
    gt_slope = ds.ground_truth["sloped_star"]

    var_track = min(tracks, key=lambda t: np.hypot(t.mean_ra - gt_var["ra"], t.mean_dec - gt_var["dec"]))
    slope_track = min(
        tracks, key=lambda t: np.hypot(t.mean_ra - gt_slope["ra"], t.mean_dec - gt_slope["dec"])
    )

    bins_var, lc_var, is_var = compute_variability(var_track, settings)
    assert is_var is True
    assert any(b.is_variable and not b.cross_band for b in bins_var)
    assert len(lc_var) >= 4

    bins_slope, lc_slope, is_slope_var = compute_variability(slope_track, settings)
    assert is_slope_var is False
    assert all(not b.cross_band for b in bins_slope)
