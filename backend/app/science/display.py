from astropy.visualization import AsymmetricPercentileInterval, AsinhStretch
import numpy as np


def render_wiseview(
    image: np.ndarray,
    linear: float = 0.15,
    min_pct: float = 1.5,
    max_pct: float = 99.4,
    invert: bool = False,
) -> np.ndarray:
    """Deterministic WiseView-style AsinhStretch + percentile trim -> uint8 array (FR-14)."""
    arr = np.asarray(image, dtype=np.float32)
    finite = arr[np.isfinite(arr)]
    if finite.size == 0 or float(np.ptp(finite)) <= 0.0:
        out = np.zeros(arr.shape, dtype=np.uint8)
        return (255 - out) if invert else out

    interval = AsymmetricPercentileInterval(min_pct, max_pct)
    vmin, vmax = interval.get_limits(finite)
    if not (np.isfinite(vmin) and np.isfinite(vmax)) or vmax <= vmin:
        vmin, vmax = float(np.min(finite)), float(np.max(finite))
    if vmax <= vmin:
        return np.zeros(arr.shape, dtype=np.uint8)

    stretch = AsinhStretch(a=float(linear))
    clean = np.where(np.isfinite(arr), arr, vmin)
    unit_scaled = np.clip((clean.astype(np.float64) - float(vmin)) / float(vmax - vmin), 0.0, 1.0)
    scaled = np.asarray(stretch(unit_scaled), dtype=np.float64)
    scaled = np.clip(np.where(np.isfinite(scaled), scaled, 0.0), 0.0, 1.0)
    u8 = np.rint(scaled * 255.0).astype(np.uint8)
    if invert:
        u8 = (255 - u8).astype(np.uint8)
    return np.ascontiguousarray(u8, dtype=np.uint8)
