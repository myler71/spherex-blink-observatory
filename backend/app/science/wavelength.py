import logging
from io import BytesIO

import astropy.units as u
import numpy as np
from astropy.io import fits
from astropy.wcs import WCS


def compute_wavelength_at_pixels(
    hdul: fits.HDUList,
    x_pixels: np.ndarray,
    y_pixels: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute central wavelength and bandwidth (um) at native pixel positions via WCS-WAVE (V-05)."""
    x_arr = np.asarray(x_pixels, dtype=np.float64)
    y_arr = np.asarray(y_pixels, dtype=np.float64)

    if "WCS-WAVE" not in hdul or "IMAGE" not in hdul:
        nan_out = np.full(x_arr.shape, np.nan, dtype=np.float64)
        return nan_out, nan_out.copy()

    astropy_wcs_logger = logging.getLogger("astropy.wcs.wcs")
    prev_level = astropy_wcs_logger.level
    astropy_wcs_logger.setLevel(logging.ERROR)
    try:
        spectral_wcs = WCS(header=hdul["IMAGE"].header, fobj=hdul, key="W")
        spectral_wcs.sip = None
        wl_q, bw_q = spectral_wcs.pixel_to_world(x_arr, y_arr)
    finally:
        astropy_wcs_logger.setLevel(prev_level)

    wl_um = np.asarray(wl_q.to_value(u.micrometer), dtype=np.float64)
    bw_um = np.asarray(bw_q.to_value(u.micrometer), dtype=np.float64)
    return wl_um, bw_um


def compute_wavelength_from_header_and_wave_bytes(
    image_header: fits.Header,
    wave_table_bytes: bytes | None,
    x_pixels: np.ndarray,
    y_pixels: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    """Evaluate WCS-WAVE at arbitrary native pixels using preserved header + WCS-WAVE HDU bytes."""
    x_arr = np.asarray(x_pixels, dtype=np.float64)
    y_arr = np.asarray(y_pixels, dtype=np.float64)
    if wave_table_bytes is None:
        nan_out = np.full(x_arr.shape, np.nan, dtype=np.float64)
        return nan_out, nan_out.copy()

    with fits.open(BytesIO(wave_table_bytes), memmap=False) as wave_hdul:
        img_hdu = fits.ImageHDU(data=None, header=image_header, name="IMAGE")
        synth_hdul = fits.HDUList([fits.PrimaryHDU(), img_hdu, wave_hdul["WCS-WAVE"].copy()])
        return compute_wavelength_at_pixels(synth_hdul, x_arr, y_arr)
