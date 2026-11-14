import numpy as np

from app.config import Settings
from app.schemas.common import EncodedArray
from app.schemas.observe import CoaddProduct
from app.science.align import AlignedFrame
from app.science.display import render_wiseview


def coadd_by_detector_visit(
    frames: list[AlignedFrame],
    settings: Settings,
) -> list[tuple[CoaddProduct, np.ndarray]]:
    """Inverse-variance weighted co-add grouped strictly by (detector, visit, wavelength_bin) (FR-12)."""
    if not frames:
        return []

    sorted_frames = sorted(frames, key=lambda f: float(f.mjd or 0.0))
    visit_ids: list[int] = []
    cur_visit = 0
    prev_mjd: float | None = None
    for f in sorted_frames:
        m = float(f.mjd or 0.0)
        if prev_mjd is not None and (m - prev_mjd) > settings.visit_gap_days:
            cur_visit += 1
        visit_ids.append(cur_visit)
        prev_mjd = m

    groups: dict[tuple[int, int, str], list[AlignedFrame]] = {}
    for f, v_idx in zip(sorted_frames, visit_ids, strict=False):
        det = f.detector or 0
        wl = f.provenance.central_wavelength_um or 0.0
        bw = f.provenance.bandwidth_um or 0.04
        bin_idx = int(round(wl / max(bw, 0.025)))
        key = (det, v_idx, f"d{det}_v{v_idx}_b{bin_idx}")
        groups.setdefault(key, []).append(f)

    results: list[tuple[CoaddProduct, np.ndarray]] = []
    for (det, v_idx, bin_id), members in sorted(groups.items()):
        shape = members[0].image.shape
        num = np.zeros(shape, dtype=np.float64)
        den = np.zeros(shape, dtype=np.float64)
        for f in members:
            valid = (~f.bad_mask) & np.isfinite(f.image) & np.isfinite(f.variance) & (f.variance > 0)
            w = np.where(valid, 1.0 / np.maximum(f.variance, 1e-6), 0.0)
            num += np.where(valid, f.image * w, 0.0)
            den += w

        coadd = np.where(den > 0.0, num / np.maximum(den, 1e-12), 0.0).astype(np.float32)
        u8 = render_wiseview(coadd)
        mean_wl = float(
            np.mean([m.provenance.central_wavelength_um or 0.0 for m in members])
        )
        prod = CoaddProduct(
            detector=det,
            visit_index=v_idx,
            bin_id=bin_id,
            wavelength_um=round(mean_wl, 4),
            n_frames=len(members),
            contributing_obs_ids=[m.obs_id for m in members],
            pixels=EncodedArray.from_numpy(coadd),
            display_u8=EncodedArray.from_numpy(u8),
            effective_snr_gain=round(float(np.sqrt(len(members))), 4),
        )
        results.append((prod, coadd))

    return results
