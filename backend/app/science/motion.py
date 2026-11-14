import math

import astropy.units as u
import numpy as np
from astropy.coordinates import SkyCoord, get_body_barycentric_posvel
from astropy.time import Time

from app.config import Settings
from app.schemas.observe import MotionMeasurement
from app.science.link import LinkedTrack


def _count_visits(mjds: np.ndarray, gap_days: float) -> int:
    if len(mjds) == 0:
        return 0
    s = np.sort(mjds)
    visits = 1
    for i in range(1, len(s)):
        if (s[i] - s[i - 1]) > gap_days:
            visits += 1
    return visits


def _weighted_linear_fit(
    t_yr: np.ndarray, y_mas: np.ndarray, sigma_mas: np.ndarray
) -> tuple[float, float, float, float]:
    """Weighted least squares y = a + b * t. Returns (a, b, b_err, chi2)."""
    safe_sigma = np.where(np.isfinite(sigma_mas) & (sigma_mas > 0.0), sigma_mas, 1000.0)
    w = 1.0 / np.maximum(safe_sigma, 1e-3) ** 2
    X = np.column_stack([np.ones_like(t_yr), t_yr])
    XtWX = X.T @ (w[:, None] * X)
    try:
        cov = np.linalg.inv(XtWX)
    except np.linalg.LinAlgError:
        cov = np.linalg.pinv(XtWX)
    beta = cov @ (X.T @ (w * y_mas))
    resid = y_mas - X @ beta
    chi2 = float(np.sum(w * resid**2))
    return float(beta[0]), float(beta[1]), float(np.sqrt(max(cov[1, 1], 1e-9))), chi2


def fit_motion(
    track: LinkedTrack,
    pixel_scale_arcsec: float,
    settings: Settings,
) -> tuple[MotionMeasurement, float | None, float | None, bool]:
    """Fit inverse-variance weighted proper motion in (mu_alpha*, mu_delta) with cos(Dec)."""
    obs = track.observations
    mjds = np.array([o.mjd for o in obs], dtype=np.float64)
    n_visits = _count_visits(mjds, settings.visit_gap_days)
    baseline_days = float(np.max(mjds) - np.min(mjds)) if len(mjds) >= 2 else 0.0

    if len(obs) < 2 or n_visits < 2 or baseline_days <= 1.0:
        meas = MotionMeasurement(
            num_visits=n_visits,
            baseline_days=round(baseline_days, 3),
            parallax_status="not_separated",
            reason=f"Insufficient time baseline ({n_visits} visit(s), {baseline_days:.1f} d).",
        )
        return meas, None, None, False

    ra_rad = np.deg2rad([o.ra for o in obs])
    ra0 = float(np.rad2deg(np.arctan2(np.mean(np.sin(ra_rad)), np.mean(np.cos(ra_rad)))) % 360.0)
    dec0 = float(np.mean([o.dec for o in obs]))
    cos_dec0 = max(math.cos(math.radians(dec0)), 1e-4)
    t_ref = float(np.mean(mjds))
    t_yr = (mjds - t_ref) / 365.25

    dra_deg = np.array([((o.ra - ra0 + 180.0) % 360.0) - 180.0 for o in obs], dtype=np.float64)
    ddec_deg = np.array([o.dec - dec0 for o in obs], dtype=np.float64)
    x_mas = dra_deg * cos_dec0 * 3600.0 * 1000.0
    y_mas = ddec_deg * 3600.0 * 1000.0

    px_scale_mas = pixel_scale_arcsec * 1000.0
    sigma_mas = np.array(
        [
            (min(max(o.centroid_err_px, 0.08), 5.0) if math.isfinite(o.centroid_err_px) else 0.5)
            * px_scale_mas
            for o in obs
        ],
        dtype=np.float64,
    )

    _, mu_ra_cosdec, err_ra, chi2_ra = _weighted_linear_fit(t_yr, x_mas, sigma_mas)
    _, mu_dec, err_dec, chi2_dec = _weighted_linear_fit(t_yr, y_mas, sigma_mas)

    dof = max(2 * len(obs) - 4, 1)
    scale_err = max(1.0, math.sqrt((chi2_ra + chi2_dec) / dof))
    err_ra *= scale_err
    err_dec *= scale_err

    pm_total = float(math.hypot(mu_ra_cosdec, mu_dec))
    if pm_total > 1e-6:
        pm_err = float(
            math.sqrt(((mu_ra_cosdec * err_ra) ** 2 + (mu_dec * err_dec) ** 2) / (pm_total**2))
        )
    else:
        pm_err = float(math.hypot(err_ra, err_dec))

    sig = pm_total / max(pm_err, 1e-3)
    pa_deg = float(math.degrees(math.atan2(mu_ra_cosdec, mu_dec)) % 360.0)
    rms_resid_arcsec = float(
        math.sqrt((chi2_ra + chi2_dec) / dof) * float(np.mean(sigma_mas)) / 1000.0
    )
    # 5-parameter parallax separation check (>= 3 visits, >= 180 d baseline, cond < max_cond)
    plx_mas: float | None = None
    plx_err: float | None = None
    plx_status = "not_separated_insufficient_baseline"
    if n_visits >= 3 and baseline_days >= settings.parallax_min_baseline_days:
        try:
            times = Time(mjds, format="mjd", scale="tdb")
            pos_au, _ = get_body_barycentric_posvel("earth", times)
            xyz = pos_au.xyz.to_value(u.AU)  # shape (3, N)
            sc = SkyCoord(ra=ra0 * u.deg, dec=dec0 * u.deg, frame="icrs")
            ra_r = float(sc.ra.radian)
            dec_r = float(sc.dec.radian)
            p_ra = xyz[0] * math.sin(ra_r) - xyz[1] * math.cos(ra_r)
            p_dec = (
                xyz[0] * math.cos(ra_r) * math.sin(dec_r)
                + xyz[1] * math.sin(ra_r) * math.sin(dec_r)
                - xyz[2] * math.cos(dec_r)
            )
            # Build 5-param joint design matrix [a0, d0, mu_ra*, mu_dec, plx]
            n = len(obs)
            A = np.zeros((2 * n, 5), dtype=np.float64)
            b = np.zeros(2 * n, dtype=np.float64)
            w_joint = np.zeros(2 * n, dtype=np.float64)
            A[0:n, 0] = 1.0
            A[0:n, 2] = t_yr
            A[0:n, 4] = p_ra
            b[0:n] = x_mas
            w_joint[0:n] = 1.0 / sigma_mas**2
            A[n : 2 * n, 1] = 1.0
            A[n : 2 * n, 3] = t_yr
            A[n : 2 * n, 4] = p_dec
            b[n : 2 * n] = y_mas
            w_joint[n : 2 * n] = 1.0 / sigma_mas**2

            cond = float(np.linalg.cond(A))
            if cond < settings.parallax_max_cond:
                XtWX = A.T @ (w_joint[:, None] * A)
                cov5 = np.linalg.inv(XtWX)
                beta5 = cov5 @ (A.T @ (w_joint * b))
                plx_mas = round(float(beta5[4]), 3)
                plx_err = round(float(math.sqrt(max(cov5[4, 4], 1e-9))), 3)
                plx_status = "fitted"
            else:
                plx_status = f"not_separated_collinear (cond={cond:.1f})"
        except Exception:
            plx_status = "not_separated"

    # Classify moving candidate by significance AND physical motion floor (> 0.25"/yr)
    is_moving = (sig >= settings.pm_significance_sigma) and (pm_total >= 250.0)
    dx_px_yr = (mu_ra_cosdec / 1000.0) / pixel_scale_arcsec
    dy_px_yr = (mu_dec / 1000.0) / pixel_scale_arcsec

    meas = MotionMeasurement(
        pm_ra_cosdec_mas_yr=round(mu_ra_cosdec, 3),
        pm_dec_mas_yr=round(mu_dec, 3),
        pm_total_mas_yr=round(pm_total, 3),
        pm_total_arcsec_yr=round(pm_total / 1000.0, 4),
        position_angle_deg=round(pa_deg, 2),
        pm_ra_err_mas_yr=round(err_ra, 3),
        pm_dec_err_mas_yr=round(err_dec, 3),
        pm_total_err_mas_yr=round(pm_err, 3),
        significance_sigma=round(sig, 2),
        fit_residual_arcsec=round(rms_resid_arcsec, 4),
        num_visits=n_visits,
        baseline_days=round(baseline_days, 3),
        parallax_mas=plx_mas,
        parallax_err_mas=plx_err,
        parallax_status=plx_status,
        reason=None,
    )
    return meas, round(dx_px_yr, 4), round(dy_px_yr, 4), is_moving
