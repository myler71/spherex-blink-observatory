import numpy as np

from app.config import Settings
from app.schemas.common import EncodedArray
from app.schemas.observe import ComparisonProduct
from app.science.align import AlignedFrame
from app.science.display import render_wiseview


def build_comparisons(
    frames: list[AlignedFrame],
    settings: Settings,
) -> tuple[ComparisonProduct, np.ndarray | None, np.ndarray | None]:
    """Compute difference (I_later - I_earlier) and addition (I_1 + I_2) for widest matched pair."""
    if len(frames) < 2:
        return (
            ComparisonProduct(
                status="omitted",
                reason="Fewer than 2 aligned frames available for comparison.",
            ),
            None,
            None,
        )

    best_pair: tuple[float, AlignedFrame, AlignedFrame] | None = None
    for i in range(len(frames)):
        f1 = frames[i]
        wl1 = f1.provenance.central_wavelength_um
        bw1 = f1.provenance.bandwidth_um or 0.04
        mjd1 = f1.mjd or 0.0
        if wl1 is None:
            continue
        for j in range(i + 1, len(frames)):
            f2 = frames[j]
            wl2 = f2.provenance.central_wavelength_um
            bw2 = f2.provenance.bandwidth_um or 0.04
            mjd2 = f2.mjd or 0.0
            if wl2 is None:
                continue
            dt = abs(mjd2 - mjd1)
            if dt <= settings.visit_gap_days:
                continue
            tol = max(max(bw1, bw2) * settings.band_match_fraction, 0.025)
            if abs(wl1 - wl2) <= tol:
                if best_pair is None or dt > best_pair[0]:
                    earlier, later = (f1, f2) if mjd1 <= mjd2 else (f2, f1)
                    best_pair = (dt, earlier, later)

    if best_pair is None:
        return (
            ComparisonProduct(
                status="omitted",
                reason="No wavelength-matched frame pair from distinct visits available.",
            ),
            None,
            None,
        )

    dt, earlier, later = best_pair
    valid = (~earlier.bad_mask) & (~later.bad_mask)
    diff_arr = np.where(valid, later.image - earlier.image, 0.0).astype(np.float32)
    add_arr = np.where(valid, later.image + earlier.image, 0.0).astype(np.float32)

    diff_u8 = render_wiseview(diff_arr)
    add_u8 = render_wiseview(add_arr)

    comp = ComparisonProduct(
        status="ok",
        earlier_obs_id=earlier.obs_id,
        later_obs_id=later.obs_id,
        wavelength_um=round(
            0.5
            * (
                (earlier.provenance.central_wavelength_um or 0.0)
                + (later.provenance.central_wavelength_um or 0.0)
            ),
            4,
        ),
        delta_days=round(dt, 3),
        cross_band=False,
        difference_pixels=EncodedArray.from_numpy(diff_arr),
        difference_u8=EncodedArray.from_numpy(diff_u8),
        addition_pixels=EncodedArray.from_numpy(add_arr),
        addition_u8=EncodedArray.from_numpy(add_u8),
    )
    return comp, diff_arr, add_arr


def build_flipbook_diffs(frames: list[AlignedFrame]) -> list[np.ndarray]:
    """Compute per-frame (frame - median reference) sequence for paired WiseView flipbook."""
    if not frames:
        return []
    stack = np.stack(
        [np.where(f.bad_mask, np.nan, f.image) for f in frames],
        axis=0,
    )
    med = np.nanmedian(stack, axis=0)
    med = np.where(np.isfinite(med), med, 0.0)
    diffs: list[np.ndarray] = []
    for f in frames:
        d = np.where(f.bad_mask, 0.0, f.image - med).astype(np.float32)
        diffs.append(d)
    return diffs
