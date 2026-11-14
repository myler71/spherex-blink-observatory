from astropy.io import fits
import numpy as np
import sep

from app.schemas.observe import SpectrumPoint, SpectrumResponse
from app.science.align import AlignedFrame
from app.science.wavelength import compute_wavelength_from_header_and_wave_bytes


def extract_spectrum(
    observation_id: str,
    frames: list[AlignedFrame],
    ra_deg: float,
    dec_deg: float,
    object_id: str | None = None,
) -> SpectrumResponse:
    """Extract forced-aperture spectrum at (ra, dec) across all frames sorted by true WCS-WAVE wavelength."""
    points: list[SpectrumPoint] = []
    ap_r = 2.5

    for f in frames:
        x_ref, y_ref = f.ref_wcs.world_to_pixel_values(ra_deg, dec_deg)
        x_f = float(x_ref)
        y_f = float(y_ref)
        ny, nx = f.image.shape
        if not (1.0 <= x_f < nx - 1.0 and 1.0 <= y_f < ny - 1.0):
            continue

        data = np.ascontiguousarray(f.image, dtype=np.float32)
        var = np.ascontiguousarray(np.maximum(f.variance, 1e-6), dtype=np.float32)
        mask = np.ascontiguousarray(f.bad_mask, dtype=bool)
        err = np.ascontiguousarray(np.sqrt(var), dtype=np.float32)

        flux, flux_err, _ = sep.sum_circle(
            data, np.array([x_f]), np.array([y_f]), ap_r, err=err, mask=mask
        )
        flx = float(flux[0])
        ferr = max(float(flux_err[0]), 1e-6)
        snr = flx / ferr if np.isfinite(flx) else 0.0

        yy, xx = np.mgrid[0:ny, 0:nx]
        contaminated = bool(np.any(mask & (((xx - x_f) ** 2 + (yy - y_f) ** 2) <= ap_r**2)))

        x_nat, y_nat = f.native_wcs.world_to_pixel_values(ra_deg, dec_deg)
        if isinstance(f.image_header, fits.Header) and f.wave_table_bytes is not None:
            wls, bws = compute_wavelength_from_header_and_wave_bytes(
                f.image_header, f.wave_table_bytes, np.array([x_nat]), np.array([y_nat])
            )
            wl = float(wls[0]) if np.isfinite(wls[0]) else (f.provenance.central_wavelength_um or 0.0)
            bw = float(bws[0]) if np.isfinite(bws[0]) else (f.provenance.bandwidth_um or 0.04)
        else:
            wl = f.provenance.central_wavelength_um or 0.0
            bw = f.provenance.bandwidth_um or 0.04

        points.append(
            SpectrumPoint(
                obs_id=f.obs_id,
                mjd=f.mjd,
                detector=f.detector,
                wavelength_um=round(wl, 4),
                bandwidth_um=round(bw, 4),
                flux=round(flx, 4),
                flux_err=round(ferr, 4),
                snr=round(snr, 2),
                contaminated=contaminated,
            )
        )

    points.sort(key=lambda p: p.wavelength_um)
    return SpectrumResponse(
        observation_id=observation_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        object_id=object_id,
        points=points,
    )
