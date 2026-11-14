from dataclasses import dataclass, field
from pathlib import Path
import re

from astropy.io import fits
from astropy.wcs import WCS
import numpy as np
from packaging.version import Version

from app.config import Settings
from app.schemas.observe import FlagSummary, FrameProvenance
from app.science.flags import MASK_BIT_REJECTED, build_flag_mask_and_summary
from app.science.wavelength import compute_wavelength_at_pixels


@dataclass
class CalibratedFrame:
    obs_id: str
    release: str
    detector: int | None
    mjd: float | None
    image: np.ndarray
    variance: np.ndarray
    bad_mask: np.ndarray
    flags_u8: np.ndarray
    spatial_wcs: WCS
    image_header: fits.Header
    wave_table_bytes: bytes | None
    provenance: FrameProvenance
    flag_summary: FlagSummary
    epsf_rows: int = 0
    warnings: list[str] = field(default_factory=list)


def _parse_version(v: str) -> tuple[int, Version]:
    base = v.split("+", 1)[0].strip()
    m = re.match(r"^\d+(\.\d+)*", base)
    if not m:
        return (0, Version("0.0"))
    return (1, Version(m.group(0)))


def calibrate_cutout(
    fits_path: Path,
    archive_url: str,
    release: str,
    settings: Settings,
) -> CalibratedFrame:
    """Read MEF cutout, subtract ZODI, build FLAGS mask, and compute center WCS-WAVE."""
    warns: list[str] = []
    with fits.open(fits_path, memmap=False) as hdul:
        primary_ver = str(hdul[0].header.get("VERSION", ""))
        img_hdu = hdul["IMAGE"]
        img_hdr = img_hdu.header.copy()
        raw_img = np.ascontiguousarray(img_hdu.data, dtype=np.float32)

        obs_id = str(img_hdr.get("OBSID") or fits_path.stem)
        detector_raw = img_hdr.get("DETECTOR")
        detector = int(detector_raw) if detector_raw is not None else None
        mjd_raw = img_hdr.get("MJD-OBS")
        mjd = float(mjd_raw) if mjd_raw is not None else None
        iso_date = str(img_hdr.get("DATE-OBS")) if img_hdr.get("DATE-OBS") is not None else None
        psf_fwhm = (
            float(img_hdr.get("PSF_FWHM")) if img_hdr.get("PSF_FWHM") is not None else None
        )

        # ZODI subtraction (FR-05)
        zodi_level: float | None = None
        if "ZODI" in hdul:
            zodi = np.ascontiguousarray(hdul["ZODI"].data, dtype=np.float32)
            finite_zodi = zodi[np.isfinite(zodi)]
            if finite_zodi.size > 0:
                zodi_level = float(np.median(finite_zodi))
            clean_img = np.ascontiguousarray(raw_img - zodi, dtype=np.float32)
        else:
            clean_img = raw_img
            warns.append(f"{obs_id}: missing ZODI extension; image used without background subtraction.")

        # VARIANCE extension
        if "VARIANCE" in hdul:
            var = np.ascontiguousarray(hdul["VARIANCE"].data, dtype=np.float32)
        else:
            finite = clean_img[np.isfinite(clean_img)]
            est = float(np.nanvar(finite)) if finite.size > 1 else 1.0
            var = np.full(clean_img.shape, max(est, 1e-6), dtype=np.float32)
            warns.append(f"{obs_id}: missing VARIANCE extension; estimated uniform variance.")

        # FLAGS extension
        if "FLAGS" in hdul:
            flags_hdu = hdul["FLAGS"]
            bad_mask, flags_u8, flag_summary = build_flag_mask_and_summary(
                flags_hdu.data,
                reject_bits=settings.spherex_reject_flag_bits,
                flags_header=flags_hdu.header,
            )
        else:
            bad_mask = np.zeros(clean_img.shape, dtype=bool)
            flags_u8 = np.zeros(clean_img.shape, dtype=np.uint8)
            flag_summary = FlagSummary(
                total_pixels=int(clean_img.size),
                rejected_pixels=0,
                fraction_rejected=0.0,
            )
            warns.append(f"{obs_id}: missing FLAGS extension; only non-finite pixels masked.")

        # Also mask non-finite image or non-positive variance pixels
        nonfinite = (~np.isfinite(clean_img)) | (~np.isfinite(var)) | (var <= 0.0)
        bad_mask = bad_mask | nonfinite
        flags_u8[nonfinite] |= MASK_BIT_REJECTED

        # ePSF / legacy PSF dynamic row count check (V-08)
        epsf_rows = 0
        if "EPSF" in hdul and hdul["EPSF"].data is not None:
            epsf_rows = int(len(hdul["EPSF"].data))
        elif "PSF" in hdul:
            ok, ver = _parse_version(primary_ver)
            if ok and ver < Version("6.5.6") and "+psffix1" not in primary_ver:
                warns.append(
                    f"{obs_id}: legacy PSF (<6.5.6 without +psffix1) detected; PSF plane order transposed."
                )

        # Central wavelength & bandwidth via WCS-WAVE (V-05)
        ny, nx = clean_img.shape
        wl_arr, bw_arr = compute_wavelength_at_pixels(
            hdul, np.array([nx / 2.0]), np.array([ny / 2.0])
        )
        wl_c = float(wl_arr[0]) if np.isfinite(wl_arr[0]) else None
        bw_c = float(bw_arr[0]) if np.isfinite(bw_arr[0]) else None
        if wl_c is None:
            warns.append(f"{obs_id}: WCS-WAVE unavailable or non-finite at cutout center.")

        # Preserve WCS-WAVE table HDU serialized in memory for per-source lookup later
        wave_bytes: bytes | None = None
        if "WCS-WAVE" in hdul:
            wave_hdul = fits.HDUList([fits.PrimaryHDU(), hdul["WCS-WAVE"].copy()])
            from io import BytesIO

            buf = BytesIO()
            wave_hdul.writeto(buf)
            wave_bytes = buf.getvalue()

        spatial_wcs = WCS(img_hdr)

    provenance = FrameProvenance(
        obs_id=obs_id,
        release=release,
        detector=detector,
        mjd=mjd,
        iso_date=iso_date,
        central_wavelength_um=wl_c,
        bandwidth_um=bw_c,
        psf_fwhm_arcsec=psf_fwhm,
        zodi_level_mjy_sr=zodi_level,
        provenance_version=primary_ver or None,
        archive_url=archive_url,
        wavelength_method="WCS-WAVE" if wl_c is not None else "unavailable",
        missing_reason="WCS-WAVE missing" if wl_c is None else None,
    )

    return CalibratedFrame(
        obs_id=obs_id,
        release=release,
        detector=detector,
        mjd=mjd,
        image=clean_img,
        variance=var,
        bad_mask=bad_mask,
        flags_u8=flags_u8,
        spatial_wcs=spatial_wcs,
        image_header=img_hdr,
        wave_table_bytes=wave_bytes,
        provenance=provenance,
        flag_summary=flag_summary,
        epsf_rows=epsf_rows,
        warnings=warns,
    )
