from dataclasses import dataclass

from astropy.io import fits
import numpy as np
import sep

from app.config import Settings
from app.science.align import AlignedFrame
from app.science.wavelength import compute_wavelength_from_header_and_wave_bytes


@dataclass
class FrameDetection:
    obs_id: str
    mjd: float
    iso_date: str | None
    detector: int | None
    x: float
    y: float
    ra: float
    dec: float
    flux: float
    flux_err: float
    snr: float
    centroid_err_px: float
    wavelength_um: float
    bandwidth_um: float
    contaminated: bool


def extract_sources(frame: AlignedFrame, settings: Settings) -> list[FrameDetection]:
    """Run SEP background subtraction & source extraction on native-endian float32 arrays."""
    data = np.ascontiguousarray(frame.image, dtype=np.float32)
    var = np.ascontiguousarray(np.maximum(frame.variance, 1e-6), dtype=np.float32)
    mask = np.ascontiguousarray(frame.bad_mask, dtype=bool)
    ny, nx = data.shape

    if int(np.count_nonzero(~mask)) < 16:
        return []

    bw = max(4, min(16, nx // 3))
    bh = max(4, min(16, ny // 3))
    bkg = sep.Background(data, mask=mask, bw=bw, bh=bh, fw=3, fh=3)
    data_sub = np.ascontiguousarray(data - bkg.back(), dtype=np.float32)
    err = np.ascontiguousarray(np.sqrt(var), dtype=np.float32)

    try:
        objs = sep.extract(
            data_sub,
            thresh=settings.detection_sigma,
            err=err,
            mask=mask,
            minarea=3,
            deblend_nthresh=16,
            deblend_cont=0.005,
        )
    except Exception:
        return []

    if len(objs) == 0:
        return []

    xs = np.asarray(objs["x"], dtype=np.float64)
    ys = np.asarray(objs["y"], dtype=np.float64)

    # Photometry with circular aperture (r=2.5 px) for consistent SNR & contamination check
    ap_r = 2.5
    flux, flux_err, _ = sep.sum_circle(data_sub, xs, ys, ap_r, err=err, mask=mask)

    # Convert aligned centroids -> sky -> native frame pixels -> true WCS-WAVE wavelength
    ras, decs = frame.ref_wcs.pixel_to_world_values(xs, ys)
    x_nat, y_nat = frame.native_wcs.world_to_pixel_values(ras, decs)

    if isinstance(frame.image_header, fits.Header) and frame.wave_table_bytes is not None:
        wls, bws = compute_wavelength_from_header_and_wave_bytes(
            frame.image_header, frame.wave_table_bytes, x_nat, y_nat
        )
    else:
        wls = np.full(
            len(xs),
            frame.provenance.central_wavelength_um or 1.5,
            dtype=np.float64,
        )
        bws = np.full(
            len(xs),
            frame.provenance.bandwidth_um or 0.04,
            dtype=np.float64,
        )

    yy, xx = np.mgrid[0:ny, 0:nx]
    detections: list[FrameDetection] = []
    mjd_val = float(frame.mjd) if frame.mjd is not None else 0.0

    for i in range(len(objs)):
        flx = float(flux[i])
        ferr = max(float(flux_err[i]), 1e-6)
        snr = flx / ferr
        if not np.isfinite(snr) or snr < settings.min_snr:
            continue

        x_i = float(xs[i])
        y_i = float(ys[i])
        # Exclude edge artifacts within 1.5 px of border
        if x_i < 1.5 or x_i > nx - 2.5 or y_i < 1.5 or y_i > ny - 2.5:
            continue

        # Check aperture overlap with bad_mask
        ap_mask = ((xx - x_i) ** 2 + (yy - y_i) ** 2) <= (ap_r**2)
        contaminated = bool(np.any(mask & ap_mask))

        # Centroid uncertainty from second-moment variances with 0.08 px floor
        x2_err = float(objs["errx2"][i]) if "errx2" in objs.dtype.names else 0.0
        y2_err = float(objs["erry2"][i]) if "erry2" in objs.dtype.names else 0.0
        c_err = float(np.sqrt(max(0.0, x2_err) + max(0.0, y2_err)))
        c_err = max(c_err, 0.08, 0.6 / max(snr, 1.0))
        wl_i = float(wls[i]) if np.isfinite(wls[i]) else (frame.provenance.central_wavelength_um or 1.5)
        bw_i = float(bws[i]) if np.isfinite(bws[i]) else (frame.provenance.bandwidth_um or 0.04)

        detections.append(
            FrameDetection(
                obs_id=frame.obs_id,
                mjd=mjd_val,
                iso_date=frame.provenance.iso_date,
                detector=frame.detector,
                x=x_i,
                y=y_i,
                ra=float(ras[i]) % 360.0,
                dec=float(decs[i]),
                flux=flx,
                flux_err=ferr,
                snr=snr,
                centroid_err_px=c_err,
                wavelength_um=wl_i,
                bandwidth_um=bw_i,
                contaminated=contaminated,
            )
        )

    return detections
