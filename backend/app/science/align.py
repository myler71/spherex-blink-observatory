from dataclasses import dataclass

from astropy.wcs import WCS
import numpy as np
from reproject import reproject_interp

from app.schemas.observe import FlagSummary, FrameProvenance, WcsGrid
from app.science.calibrate import CalibratedFrame
from app.science.flags import MASK_BIT_OUT_OF_BOUNDS, MASK_BIT_REJECTED


@dataclass
class AlignedFrame:
    obs_id: str
    release: str
    detector: int | None
    mjd: float | None
    image: np.ndarray
    variance: np.ndarray
    bad_mask: np.ndarray
    out_of_bounds: np.ndarray
    flags_u8: np.ndarray
    ref_wcs: WCS
    native_wcs: WCS
    image_header: object
    wave_table_bytes: bytes | None
    provenance: FrameProvenance
    flag_summary: FlagSummary


def build_reference_wcs(
    ra_deg: float,
    dec_deg: float,
    fov_deg: float,
    pixel_scale_arcsec: float = 6.16,
) -> tuple[WCS, WcsGrid]:
    """Build north-up tangent-plane reference WCS with polar singularity guard."""
    safe_dec = max(-89.9, min(89.9, float(dec_deg)))
    n_px = max(15, int(round((fov_deg * 3600.0) / pixel_scale_arcsec)))
    if n_px % 2 == 0:
        n_px += 1
    cdelt = pixel_scale_arcsec / 3600.0

    w = WCS(naxis=2)
    w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
    w.wcs.crval = [float(ra_deg) % 360.0, safe_dec]
    crpix = (n_px + 1) / 2.0
    w.wcs.crpix = [crpix, crpix]
    w.wcs.cdelt = [-cdelt, cdelt]

    grid = WcsGrid(
        crval1=float(w.wcs.crval[0]),
        crval2=float(w.wcs.crval[1]),
        crpix1=crpix,
        crpix2=crpix,
        cdelt1=-cdelt,
        cdelt2=cdelt,
        naxis1=n_px,
        naxis2=n_px,
        pixel_scale_arcsec=pixel_scale_arcsec,
    )
    return w, grid


def align_frames(
    calibrated: list[CalibratedFrame],
    ref_wcs: WCS,
    grid: WcsGrid,
) -> list[AlignedFrame]:
    """Reproject calibrated frames onto reference grid with variance and mask propagation."""
    shape_out = (grid.naxis2, grid.naxis1)
    aligned: list[AlignedFrame] = []

    for frame in calibrated:
        valid = (~frame.bad_mask) & np.isfinite(frame.image) & np.isfinite(frame.variance) & (frame.variance > 0)
        img_clean = np.where(valid, frame.image, 0.0).astype(np.float32)
        var_clean = np.where(valid, frame.variance, 0.0).astype(np.float32)
        valid_f = valid.astype(np.float32)
        bad_f = frame.bad_mask.astype(np.float32)

        reproj_img, footprint = reproject_interp(
            (img_clean, frame.spatial_wcs),
            ref_wcs,
            shape_out=shape_out,
            order="bilinear",
            return_footprint=True,
        )
        reproj_var, _ = reproject_interp(
            (var_clean, frame.spatial_wcs),
            ref_wcs,
            shape_out=shape_out,
            order="bilinear",
            return_footprint=True,
        )
        reproj_valid, _ = reproject_interp(
            (valid_f, frame.spatial_wcs),
            ref_wcs,
            shape_out=shape_out,
            order="bilinear",
            return_footprint=True,
        )
        reproj_bad, _ = reproject_interp(
            (bad_f, frame.spatial_wcs),
            ref_wcs,
            shape_out=shape_out,
            order="bilinear",
            return_footprint=True,
        )
        reproj_u8, _ = reproject_interp(
            (frame.flags_u8.astype(np.float32), frame.spatial_wcs),
            ref_wcs,
            shape_out=shape_out,
            order="nearest-neighbor",
            return_footprint=True,
        )

        oob = (footprint < 0.99) | (~np.isfinite(reproj_img)) | (~np.isfinite(reproj_var))
        out_bad = oob | (reproj_bad > 0.0) | (reproj_valid < 0.25)

        img_out = np.ascontiguousarray(np.where(oob, 0.0, reproj_img), dtype=np.float32)
        # Analytical variance scaling + undersampling floor (2%)
        safe_valid = np.maximum(np.where(np.isfinite(reproj_valid), reproj_valid, 0.25), 0.25)
        raw_var = np.where(np.isfinite(reproj_var) & (reproj_var > 0), reproj_var, 1.0)
        var_scaled = (raw_var / safe_valid) + (0.02 * np.abs(img_out)) ** 2
        var_out = np.ascontiguousarray(np.maximum(var_scaled, 1e-6), dtype=np.float32)

        u8_out = np.where(np.isfinite(reproj_u8), reproj_u8, 0).astype(np.uint8)
        u8_out[out_bad] |= MASK_BIT_REJECTED
        u8_out[oob] |= MASK_BIT_OUT_OF_BOUNDS

        aligned.append(
            AlignedFrame(
                obs_id=frame.obs_id,
                release=frame.release,
                detector=frame.detector,
                mjd=frame.mjd,
                image=img_out,
                variance=var_out,
                bad_mask=out_bad,
                out_of_bounds=oob,
                flags_u8=np.ascontiguousarray(u8_out, dtype=np.uint8),
                ref_wcs=ref_wcs,
                native_wcs=frame.spatial_wcs,
                image_header=frame.image_header,
                wave_table_bytes=frame.wave_table_bytes,
                provenance=frame.provenance,
                flag_summary=frame.flag_summary,
            )
        )

    return aligned
