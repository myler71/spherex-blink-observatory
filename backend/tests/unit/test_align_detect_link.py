from pathlib import Path

import numpy as np
import pytest

from app.config import Settings
from app.science.align import align_frames, build_reference_wcs
from app.science.calibrate import calibrate_cutout
from app.science.detect import extract_sources
from app.science.link import link_detections
from tests.synthetic.fits_generator import SyntheticScenario, generate_synthetic_dataset


def test_align_rotated_static_stars_within_0_1_px_rms(tmp_path: Path) -> None:
    settings = Settings()
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=2,
            exposures_per_visit=1,
            detectors=[2],
            n_static_stars=10,
            rotate_per_visit_deg=23.0,
            noise_sigma=0.05,
        ),
        tmp_path,
    )
    cal_frames = [
        calibrate_cutout(f.fits_path, archive_url=f.obs_id, release="spherex_dr1", settings=settings)
        for f in ds.frames
    ]
    ref_wcs, grid = build_reference_wcs(180.0, 20.0, 0.08, settings.spherex_native_pixel_scale_arcsec)
    aligned = align_frames(cal_frames, ref_wcs, grid)
    assert len(aligned) == 2

    det0 = extract_sources(aligned[0], settings)
    det1 = extract_sources(aligned[1], settings)
    assert len(det0) >= 8
    assert len(det1) >= 8

    # Check static stars agree within 0.1 px RMS across aligned frames
    diffs: list[float] = []
    for s0 in det0:
        nearest = min(det1, key=lambda s1: np.hypot(s1.x - s0.x, s1.y - s0.y))
        dist = float(np.hypot(nearest.x - s0.x, nearest.y - s0.y))
        if dist < 1.0:
            diffs.append(dist)
    assert len(diffs) >= 6
    rms = float(np.sqrt(np.mean(np.square(diffs))))
    assert rms <= 0.1


def test_detect_marks_aperture_overlapping_masked_pixel_contaminated(tmp_path: Path) -> None:
    settings = Settings()
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=1,
            exposures_per_visit=1,
            detectors=[2],
            n_static_stars=5,
            inject_cosmic_rays=1,
            noise_sigma=0.05,
        ),
        tmp_path,
    )
    cal = calibrate_cutout(ds.frames[0].fits_path, archive_url="syn", release="spherex_dr1", settings=settings)
    ref_wcs, grid = build_reference_wcs(180.0, 20.0, 0.08, settings.spherex_native_pixel_scale_arcsec)
    aligned = align_frames([cal], ref_wcs, grid)[0]
    dets = extract_sources(aligned, settings)
    assert len(dets) >= 4

    # Corrupt pixel at first star centroid and re-extract -> flagged contaminated
    d0 = dets[0]
    ix, iy = int(round(d0.x)), int(round(d0.y))
    aligned.bad_mask[iy, ix] = True
    dets_after = extract_sources(aligned, settings)
    # Wait: if central pixel masked, nearby aperture check on second star edge:
    ix2, iy2 = int(round(dets[1].x)) + 1, int(round(dets[1].y))
    aligned.bad_mask[iy, ix] = False
    aligned.bad_mask[iy2, ix2] = True
    dets_edge = extract_sources(aligned, settings)
    matched = min(dets_edge, key=lambda s: np.hypot(s.x - dets[1].x, s.y - dets[1].y))
    assert matched.contaminated is True


def test_link_across_all_frames_including_star_absent_from_frame0(tmp_path: Path) -> None:
    settings = Settings()
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=3,
            exposures_per_visit=1,
            detectors=[2],
            n_static_stars=8,
            noise_sigma=0.05,
        ),
        tmp_path,
    )
    cal_frames = [
        calibrate_cutout(f.fits_path, archive_url=f.obs_id, release="spherex_dr1", settings=settings)
        for f in ds.frames
    ]
    ref_wcs, grid = build_reference_wcs(180.0, 20.0, 0.08, settings.spherex_native_pixel_scale_arcsec)
    aligned = align_frames(cal_frames, ref_wcs, grid)
    per_frame_dets = [extract_sources(a, settings) for a in aligned]

    # Remove one star from frame 0 to verify linking still links frames 1 & 2 (fixes A15 item 11)
    dropped = per_frame_dets[0].pop(0)
    tracks = link_detections(per_frame_dets, aligned, settings)
    found_dropped = [
        t for t in tracks if np.hypot(t.mean_x - dropped.x, t.mean_y - dropped.y) < 1.5
    ]
    assert len(found_dropped) == 1
    assert len(found_dropped[0].observations) == 2
