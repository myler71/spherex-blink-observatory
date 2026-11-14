import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
from astropy.io import fits
from astropy.wcs import WCS

FLAG_DEFINITIONS: dict[int, tuple[str, str]] = {
    0: ("TRANSIENT", "Transient detected during SUR"),
    1: ("OVERFLOW", "Overflow detected during SUR"),
    2: ("SUR_ERROR", "Error in onboard processing"),
    6: ("NONFUNC", "Permanently unusable"),
    7: ("DICHROIC", "Low efficiency due to dichroic"),
    9: ("MISSING_DATA", "Onboard data lost"),
    10: ("HOT", "Hot pixel"),
    11: ("COLD", "Anomalously low signal"),
    12: ("FULLSAMPLE", "Pixel full sample history is available"),
    14: ("PHANMISS", "Phantom correction was not applied"),
    15: ("NONLINEAR", "Nonlinearity correction cannot be applied reliably"),
    17: ("PERSIST", "Persistent charge above threshold"),
    19: ("OUTLIER", "Pixel flagged by Detect Outliers"),
    20: ("CROSSTALK", "Pixel affected by crosstalk."),
    21: ("SOURCE", "Pixel mapped to a known source"),
    25: ("STREAK", "Pixel affected by a streak"),
    26: ("BLOOM", "Pixel part of a bloom artifact"),
    27: ("SNOWBALL", "Pixel part of a snowball artifact"),
}


@dataclass
class SyntheticScenario:
    center_ra: float = 180.0
    center_dec: float = 20.0
    fov_deg: float = 0.08
    num_visits: int = 2
    exposures_per_visit: int = 2
    visit_gap_days: float = 180.0
    pixel_scale_arcsec: float = 6.16
    n_static_stars: int = 12
    mover_pm_ra_arcsec_yr: float = 0.0
    mover_pm_dec_arcsec_yr: float = 0.0
    mover_flux: float = 60.0
    variable_amplitude: float = 0.0
    variable_flux: float = 55.0
    sloped_star_flux: float = 0.0
    inject_cosmic_rays: int = 0
    rotate_per_visit_deg: float = 17.0
    noise_sigma: float = 0.25
    seed: int = 42
    detectors: list[int] = field(default_factory=lambda: [2, 3])
    wavelength_ranges_um: dict[int, tuple[float, float]] = field(
        default_factory=lambda: {
            1: (0.75, 1.09),
            2: (1.10, 1.62),
            3: (1.63, 2.41),
            4: (2.42, 3.82),
            5: (3.83, 4.41),
            6: (4.42, 5.00),
        }
    )


@dataclass
class SyntheticFrame:
    obs_id: str
    visit_index: int
    mjd: float
    detector: int
    central_wavelength_um: float
    bandwidth_um: float
    fits_path: Path


@dataclass
class SyntheticDataset:
    frames: list[SyntheticFrame]
    ground_truth: dict[str, Any]
    ground_truth_path: Path


def _gaussian_stamp(
    ny: int, nx: int, x0: float, y0: float, flux: float, sigma_px: float = 1.1
) -> np.ndarray:
    yy, xx = np.mgrid[0:ny, 0:nx]
    norm = 1.0 / (2.0 * np.pi * sigma_px * sigma_px)
    return flux * norm * np.exp(-(((xx - x0) ** 2 + (yy - y0) ** 2) / (2.0 * sigma_px**2)))


def _build_wcs_wave_hdu(
    nx: int, ny: int, lam_min: float, lam_max: float
) -> tuple[fits.BinTableHDU, dict[str, Any]]:
    gx = np.linspace(0, max(nx - 1, 1), 9, dtype=np.int32)
    gy = np.linspace(0, max(ny - 1, 1), 9, dtype=np.int32)
    vals = np.zeros((9, 9, 2), dtype=np.float32)
    bw = (lam_max - lam_min) / 17.0
    for iy, yv in enumerate(gy):
        frac_y = float(yv) / max(ny - 1, 1)
        for ix, xv in enumerate(gx):
            frac_x = float(xv) / max(nx - 1, 1)
            # Slight 2D curvature like real LVF
            lam = lam_min + (lam_max - lam_min) * (0.95 * frac_y + 0.05 * frac_x)
            vals[iy, ix, 0] = lam
            vals[iy, ix, 1] = bw

    col_x = fits.Column(name="X", format=f"{len(gx)}J", array=[gx])
    col_y = fits.Column(name="Y", format=f"{len(gy)}J", array=[gy])
    col_v = fits.Column(
        name="VALUES",
        format=f"{9 * 9 * 2}E",
        dim="(2, 9, 9)",
        array=[vals],
    )
    hdu = fits.BinTableHDU.from_columns([col_x, col_y, col_v], name="WCS-WAVE")
    # Spectral WCS cards on IMAGE header per FITS -TAB standard
    wcs_cards = {
        "WCSNAMEW": "Approximated per-pixel wavelength and bandwidth",
        "CTYPE1W": "WAVE-TAB",
        "CTYPE2W": "BAND-TAB",
        "CUNIT1W": "um",
        "CUNIT2W": "um",
        "CRPIX1W": 1.0,
        "CRPIX2W": 1.0,
        "CRVAL1W": 0.0,
        "CRVAL2W": 0.0,
        "CD1_1W": 1.0,
        "CD1_2W": 0.0,
        "CD2_1W": 0.0,
        "CD2_2W": 1.0,
        "PS1_0W": "WCS-WAVE",
        "PS1_1W": "VALUES",
        "PS1_2W": "X",
        "PS2_0W": "WCS-WAVE",
        "PS2_1W": "VALUES",
        "PS2_2W": "Y",
        "PV1_3W": 1,
        "PV2_3W": 2,
    }
    return hdu, wcs_cards


def generate_synthetic_dataset(scenario: SyntheticScenario, out_dir: Path) -> SyntheticDataset:
    out_dir.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(scenario.seed)

    nx = max(33, int(round(scenario.fov_deg * 3600.0 / scenario.pixel_scale_arcsec)))
    if nx % 2 == 0:
        nx += 1
    ny = nx
    cos_dec = max(np.cos(np.deg2rad(scenario.center_dec)), 1e-4)

    # Generate isolated static stars inside inner 72% of FOV so rotated frames keep them
    half_deg = scenario.fov_deg * 0.36
    static_stars: list[dict[str, float]] = []
    min_sep_deg = (4.5 * scenario.pixel_scale_arcsec) / 3600.0
    attempts = 0
    while len(static_stars) < scenario.n_static_stars and attempts < 2000:
        attempts += 1
        dra = float(rng.uniform(-half_deg, half_deg)) / cos_dec
        ddec = float(rng.uniform(-half_deg, half_deg))
        ra_s = (scenario.center_ra + dra) % 360.0
        dec_s = scenario.center_dec + ddec
        # Keep clear of center (where mover/variable/sloped sit)
        if np.hypot(dra * cos_dec, ddec) < min_sep_deg * 2.0:
            continue
        if any(
            np.hypot((ra_s - s["ra"]) * cos_dec, dec_s - s["dec"]) < min_sep_deg
            for s in static_stars
        ):
            continue
        static_stars.append(
            {
                "ra": ra_s,
                "dec": dec_s,
                "flux": float(rng.uniform(18.0, 55.0)),
            }
        )

    mjd0 = 60800.0
    frames: list[SyntheticFrame] = []
    planted: dict[str, Any] = {
        "center_ra": scenario.center_ra,
        "center_dec": scenario.center_dec,
        "static_stars": static_stars,
        "mover": None,
        "variable": None,
        "sloped_star": None,
        "cosmic_ray_coords": [],
    }

    # Place special targets at distinct offsets near center
    mover_ra0 = scenario.center_ra
    mover_dec0 = scenario.center_dec
    var_ra = (scenario.center_ra + (6.0 * scenario.pixel_scale_arcsec / 3600.0) / cos_dec) % 360.0
    var_dec = scenario.center_dec - (5.0 * scenario.pixel_scale_arcsec / 3600.0)
    slope_ra = (scenario.center_ra - (6.0 * scenario.pixel_scale_arcsec / 3600.0) / cos_dec) % 360.0
    slope_dec = scenario.center_dec + (5.0 * scenario.pixel_scale_arcsec / 3600.0)

    if scenario.mover_pm_ra_arcsec_yr != 0.0 or scenario.mover_pm_dec_arcsec_yr != 0.0:
        planted["mover"] = {
            "ra0": mover_ra0,
            "dec0": mover_dec0,
            "pm_ra_cosdec_arcsec_yr": scenario.mover_pm_ra_arcsec_yr,
            "pm_dec_arcsec_yr": scenario.mover_pm_dec_arcsec_yr,
            "mjd0": mjd0,
        }
    if scenario.variable_amplitude > 0.0:
        planted["variable"] = {
            "ra": var_ra,
            "dec": var_dec,
            "base_flux": scenario.variable_flux,
            "amplitude": scenario.variable_amplitude,
        }
    if scenario.sloped_star_flux > 0.0:
        planted["sloped_star"] = {
            "ra": slope_ra,
            "dec": slope_dec,
            "base_flux": scenario.sloped_star_flux,
        }

    # Pre-build EPSF table (variable row count check)
    epsf_rows = 25
    epsf_cols = fits.ColDefs(
        [
            fits.Column(name="BINX", format="J", array=np.arange(epsf_rows) % 5),
            fits.Column(name="BINY", format="J", array=np.arange(epsf_rows) // 5),
            fits.Column(
                name="XCENTER",
                format="E",
                array=np.linspace(0, nx, epsf_rows, dtype=np.float32),
            ),
            fits.Column(
                name="YCENTER",
                format="E",
                array=np.linspace(0, ny, epsf_rows, dtype=np.float32),
            ),
            fits.Column(
                name="NEFF_MEAN", format="E", array=np.full(epsf_rows, 6.2, dtype=np.float32)
            ),
            fits.Column(name="CWAVE", format="E", array=np.full(epsf_rows, 1.5, dtype=np.float32)),
            fits.Column(name="CBAND", format="E", array=np.full(epsf_rows, 0.04, dtype=np.float32)),
            fits.Column(
                name="EPSF",
                format="1089D",
                dim="(33, 33)",
                array=np.zeros((epsf_rows, 33, 33), dtype=np.float64),
            ),
        ]
    )
    epsf_hdu = fits.BinTableHDU.from_columns(epsf_cols, name="EPSF")
    epsf_hdu.header["OVSMPX"] = 5
    epsf_hdu.header["OVSMPY"] = 5

    for visit_idx in range(scenario.num_visits):
        theta_deg = visit_idx * scenario.rotate_per_visit_deg
        theta = np.deg2rad(theta_deg)
        cdelt = scenario.pixel_scale_arcsec / 3600.0
        for exp_idx in range(scenario.exposures_per_visit):
            det = scenario.detectors[exp_idx % len(scenario.detectors)]
            mjd = mjd0 + visit_idx * scenario.visit_gap_days + exp_idx * 0.02
            dt_yr = (mjd - mjd0) / 365.25
            obs_id = f"SYN_V{visit_idx}_E{exp_idx}_D{det}"

            w = WCS(naxis=2)
            w.wcs.ctype = ["RA---TAN", "DEC--TAN"]
            w.wcs.crval = [scenario.center_ra, scenario.center_dec]
            jitter_x = float(rng.uniform(-0.3, 0.3))
            jitter_y = float(rng.uniform(-0.3, 0.3))
            w.wcs.crpix = [(nx + 1) / 2.0 + jitter_x, (ny + 1) / 2.0 + jitter_y]
            w.wcs.pc = [
                [-cdelt * np.cos(theta), cdelt * np.sin(theta)],
                [cdelt * np.sin(theta), cdelt * np.cos(theta)],
            ]

            lam_min, lam_max = scenario.wavelength_ranges_um[det]
            wave_hdu, wcs_wave_cards = _build_wcs_wave_hdu(nx, ny, lam_min, lam_max)

            clean_img = np.zeros((ny, nx), dtype=np.float64)
            flags = np.full((ny, nx), 1 << 12, dtype=np.int32)  # FULLSAMPLE bit 12

            def _add_star(
                ra_v: float,
                dec_v: float,
                flux_v: float,
                wcs_obj: WCS = w,
                img_arr: np.ndarray = clean_img,
                flag_arr: np.ndarray = flags,
            ) -> None:
                px, py = wcs_obj.world_to_pixel_values(ra_v, dec_v)
                if 2 <= px < nx - 2 and 2 <= py < ny - 2:
                    img_arr[:] += _gaussian_stamp(ny, nx, float(px), float(py), flux_v)
                    ix, iy = int(round(float(px))), int(round(float(py)))
                    flag_arr[iy, ix] |= 1 << 21  # SOURCE bit 21

            for s in static_stars:
                _add_star(s["ra"], s["dec"], s["flux"])

            if planted["mover"] is not None:
                m_ra = mover_ra0 + (scenario.mover_pm_ra_arcsec_yr * dt_yr / 3600.0) / cos_dec
                m_dec = mover_dec0 + (scenario.mover_pm_dec_arcsec_yr * dt_yr / 3600.0)
                _add_star(m_ra, m_dec, scenario.mover_flux)

            if planted["variable"] is not None:
                sign = 1.0 if visit_idx % 2 == 0 else -1.0
                v_flux = scenario.variable_flux * (1.0 + sign * scenario.variable_amplitude)
                _add_star(var_ra, var_dec, v_flux)

            if planted["sloped_star"] is not None:
                lam_c_approx = 0.5 * (lam_min + lam_max)
                # Strongly sloped spectrum across wavelength, constant in time
                s_flux = scenario.sloped_star_flux * (1.0 + 1.5 * (lam_c_approx - 1.0))
                _add_star(slope_ra, slope_dec, s_flux)

            # Inject cosmic rays into first exposure
            if scenario.inject_cosmic_rays > 0 and visit_idx == 0 and exp_idx == 0:
                for cr_i in range(scenario.inject_cosmic_rays):
                    cx = 4 + cr_i * 3
                    cy = 4 + cr_i * 2
                    if cx < nx - 2 and cy < ny - 2:
                        clean_img[cy, cx] += 250.0
                        flags[cy, cx] |= 1 << 0  # TRANSIENT
                        planted["cosmic_ray_coords"].append((cx, cy))

            variance = np.full((ny, nx), scenario.noise_sigma**2, dtype=np.float32)
            zodi = np.full((ny, nx), 1.5, dtype=np.float32)
            noise = rng.normal(0.0, scenario.noise_sigma, size=(ny, nx))
            # Store big-endian float32 to match real FITS archive endianness
            image_data = (clean_img + noise + zodi).astype(">f4")

            primary = fits.PrimaryHDU()
            primary.header["VERSION"] = "7.0.5"
            img_hdu = fits.ImageHDU(data=image_data, header=w.to_header(), name="IMAGE")
            img_hdu.header["BUNIT"] = "MJy / sr"
            img_hdu.header["DETECTOR"] = det
            img_hdu.header["OBSID"] = obs_id
            img_hdu.header["MJD-OBS"] = mjd
            img_hdu.header["DATE-OBS"] = f"2025-05-{10 + visit_idx:02d}T00:00:00"
            img_hdu.header["PSF_FWHM"] = 9.0
            img_hdu.header["CRPIX1A"] = -100.0
            img_hdu.header["CRPIX2A"] = -100.0
            for k, v in wcs_wave_cards.items():
                img_hdu.header[k] = v

            flags_hdu = fits.ImageHDU(data=flags, name="FLAGS")
            for bit, (fname, fdesc) in FLAG_DEFINITIONS.items():
                flags_hdu.header[f"MSKN{bit:04d}"] = fname
                flags_hdu.header[f"MSKD{bit:04d}"] = fdesc

            var_hdu = fits.ImageHDU(data=variance.astype(">f4"), name="VARIANCE")
            zodi_hdu = fits.ImageHDU(data=zodi.astype(">f4"), name="ZODI")

            hdul = fits.HDUList(
                [primary, img_hdu, flags_hdu, var_hdu, zodi_hdu, epsf_hdu, wave_hdu]
            )
            fpath = out_dir / f"{obs_id}.fits"
            hdul.writeto(fpath, overwrite=True)

            # Evaluate central wavelength via real WCS-WAVE
            swcs = WCS(header=img_hdu.header, fobj=hdul, key="W")
            swcs.sip = None
            wl_q, bw_q = swcs.pixel_to_world(nx / 2.0, ny / 2.0)

            frames.append(
                SyntheticFrame(
                    obs_id=obs_id,
                    visit_index=visit_idx,
                    mjd=mjd,
                    detector=det,
                    central_wavelength_um=float(wl_q.to_value("um")),
                    bandwidth_um=float(bw_q.to_value("um")),
                    fits_path=fpath,
                )
            )

    gt_path = out_dir / "ground_truth.json"
    gt_path.write_text(json.dumps(planted, indent=2))
    return SyntheticDataset(frames=frames, ground_truth=planted, ground_truth_path=gt_path)
