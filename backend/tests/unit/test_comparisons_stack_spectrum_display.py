from pathlib import Path

import numpy as np
import pytest

from app.config import Settings
from app.science.align import align_frames, build_reference_wcs
from app.science.calibrate import calibrate_cutout
from app.science.comparisons import build_comparisons, build_flipbook_diffs
from app.science.display import render_wiseview
from app.science.spectrum import extract_spectrum
from app.science.stack import coadd_by_detector_visit
from tests.synthetic.fits_generator import SyntheticScenario, generate_synthetic_dataset


def test_comparisons_dipole_on_mover_and_omits_mismatched_bands(tmp_path: Path) -> None:
    settings = Settings()
    # Matched band mover
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=2,
            exposures_per_visit=1,
            visit_gap_days=365.25,
            detectors=[2],
            n_static_stars=3,
            mover_pm_ra_arcsec_yr=12.0,  # ~2 px shift -> strong dipole
            mover_pm_dec_arcsec_yr=0.0,
            mover_flux=90.0,
            noise_sigma=0.05,
        ),
        tmp_path / "matched",
    )
    cal = [
        calibrate_cutout(
            f.fits_path, archive_url=f.obs_id, release="spherex_dr1", settings=settings
        )
        for f in ds.frames
    ]
    ref_wcs, grid = build_reference_wcs(
        180.0, 20.0, 0.08, settings.spherex_native_pixel_scale_arcsec
    )
    aligned = align_frames(cal, ref_wcs, grid)
    comp, diff_arr, add_arr = build_comparisons(aligned, settings)
    assert comp.status == "ok"
    assert diff_arr is not None and add_arr is not None
    assert comp.cross_band is False
    # Dipole: distinct negative and positive lobes near center
    assert float(np.min(diff_arr)) < -1.0
    assert float(np.max(diff_arr)) > 1.0

    # Flipbook diffs
    flips = build_flipbook_diffs(aligned)
    assert len(flips) == 2

    # Mismatched bands across visits -> omitted with reason
    ds_mis = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=2,
            exposures_per_visit=1,
            visit_gap_days=180.0,
            detectors=[1],
            n_static_stars=2,
        ),
        tmp_path / "mis",
    )
    cal_m = [
        calibrate_cutout(
            ds_mis.frames[0].fits_path, archive_url="a", release="spherex_dr1", settings=settings
        ),
    ]
    # Second frame from detector 6
    ds_mis6 = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=2,
            exposures_per_visit=1,
            visit_gap_days=180.0,
            detectors=[6],
            n_static_stars=2,
        ),
        tmp_path / "mis6",
    )
    cal_m.append(
        calibrate_cutout(
            ds_mis6.frames[1].fits_path, archive_url="b", release="spherex_dr1", settings=settings
        )
    )
    aligned_m = align_frames(cal_m, ref_wcs, grid)
    comp_m, diff_m, _ = build_comparisons(aligned_m, settings)
    assert comp_m.status == "omitted"
    assert diff_m is None
    assert comp_m.reason is not None


def test_coadd_snr_improves_by_sqrt_n(tmp_path: Path) -> None:
    settings = Settings()
    n_exp = 4
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=1,
            exposures_per_visit=n_exp,
            detectors=[2],
            n_static_stars=4,
            rotate_per_visit_deg=0.0,
            noise_sigma=0.30,
        ),
        tmp_path,
    )
    cal = [
        calibrate_cutout(
            f.fits_path, archive_url=f.obs_id, release="spherex_dr1", settings=settings
        )
        for f in ds.frames
    ]
    ref_wcs, grid = build_reference_wcs(
        180.0, 20.0, 0.08, settings.spherex_native_pixel_scale_arcsec
    )
    aligned = align_frames(cal, ref_wcs, grid)
    coadds = coadd_by_detector_visit(aligned, settings)
    assert len(coadds) == 1
    coadd_prod, coadd_arr = coadds[0]
    assert len(coadd_prod.contributing_obs_ids) == n_exp
    assert coadd_prod.effective_snr_gain == pytest.approx(np.sqrt(n_exp), rel=0.15)
    # Empirical background std reduction ~ sqrt(4) = 2x
    single_std = float(np.std(aligned[0].image[:10, :10]))
    coadd_std = float(np.std(coadd_arr[:10, :10]))
    assert (single_std / max(coadd_std, 1e-6)) == pytest.approx(np.sqrt(n_exp), rel=0.35)


def test_spectrum_sorted_and_wiseview_display_deterministic(tmp_path: Path) -> None:
    settings = Settings()
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=2,
            exposures_per_visit=3,
            detectors=[1, 3, 5],
            sloped_star_flux=30.0,
            noise_sigma=0.05,
        ),
        tmp_path,
    )
    cal = [
        calibrate_cutout(
            f.fits_path, archive_url=f.obs_id, release="spherex_dr1", settings=settings
        )
        for f in ds.frames
    ]
    ref_wcs, grid = build_reference_wcs(
        180.0, 20.0, 0.08, settings.spherex_native_pixel_scale_arcsec
    )
    aligned = align_frames(cal, ref_wcs, grid)
    gt_slope = ds.ground_truth["sloped_star"]
    spec = extract_spectrum("obs_syn", aligned, ra_deg=gt_slope["ra"], dec_deg=gt_slope["dec"])
    wls = [p.wavelength_um for p in spec.points]
    assert wls == sorted(wls)
    assert len(spec.points) == 6
    assert "different observation epochs" in spec.non_simultaneous_note.lower()

    u8_a = render_wiseview(aligned[0].image, linear=0.15, min_pct=1.5, max_pct=99.4, invert=False)
    u8_b = render_wiseview(aligned[0].image, linear=0.15, min_pct=1.5, max_pct=99.4, invert=False)
    np.testing.assert_array_equal(u8_a, u8_b)
    assert u8_a.dtype == np.uint8
