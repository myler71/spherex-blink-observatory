import numpy as np

from app.config import Settings
from app.schemas.observe import LightCurvePoint, VariabilityBin
from app.science.link import LinkedTrack


def compute_variability(
    track: LinkedTrack,
    settings: Settings,
) -> tuple[list[VariabilityBin], list[LightCurvePoint], bool]:
    """Compute strictly wavelength-matched light curves and reduced chi2 per bin (FR-10)."""
    obs = sorted(track.observations, key=lambda o: (o.wavelength_um, o.mjd))
    if not obs:
        return [], [], False

    # Cluster detections into wavelength bins within band_match_fraction * local bandwidth
    bins: list[list[int]] = []
    bin_centers: list[float] = []
    for idx, det in enumerate(obs):
        tol = max(det.bandwidth_um * settings.band_match_fraction, 0.025)
        placed = False
        for b_idx, c_wl in enumerate(bin_centers):
            if abs(det.wavelength_um - c_wl) <= tol:
                bins[b_idx].append(idx)
                bin_centers[b_idx] = float(np.mean([obs[k].wavelength_um for k in bins[b_idx]]))
                placed = True
                break
        if not placed:
            bins.append([idx])
            bin_centers.append(det.wavelength_um)

    var_bins: list[VariabilityBin] = []
    lc_points: list[LightCurvePoint] = []
    any_variable = False

    for b_idx, member_idxs in enumerate(bins):
        bin_id = f"bin_{b_idx + 1}_{bin_centers[b_idx]:.3f}um"
        members = [obs[k] for k in member_idxs]
        bw_mean = float(np.mean([m.bandwidth_um for m in members]))
        fluxes = np.array([m.flux for m in members], dtype=np.float64)
        errs = np.array([max(m.flux_err, 1e-6) for m in members], dtype=np.float64)
        weights = 1.0 / errs**2
        w_mean = float(np.sum(weights * fluxes) / np.sum(weights))

        n_pts = len(members)
        dof = n_pts - 1
        if dof >= 1:
            chi2_red = float(np.sum(weights * (fluxes - w_mean) ** 2) / dof)
            is_var = chi2_red >= settings.variability_reduced_chi2
            reason = None
        else:
            chi2_red = None
            is_var = False
            reason = "Only 1 wavelength-matched measurement in bin."

        if is_var:
            any_variable = True

        var_bins.append(
            VariabilityBin(
                bin_id=bin_id,
                wavelength_center_um=round(bin_centers[b_idx], 4),
                bandwidth_um=round(bw_mean, 4),
                n_points=n_pts,
                dof=dof,
                weighted_mean_flux=round(w_mean, 4),
                reduced_chi2=round(chi2_red, 3) if chi2_red is not None else None,
                is_variable=is_var,
                cross_band=False,
                reason=reason,
            )
        )

        for m in sorted(members, key=lambda item: item.mjd):
            lc_points.append(
                LightCurvePoint(
                    obs_id=m.obs_id,
                    mjd=m.mjd,
                    iso_date=m.iso_date,
                    detector=m.detector,
                    wavelength_um=round(m.wavelength_um, 4),
                    bandwidth_um=round(m.bandwidth_um, 4),
                    bin_id=bin_id,
                    flux=round(m.flux, 4),
                    flux_err=round(m.flux_err, 4),
                    snr=round(m.snr, 2),
                    contaminated=m.contaminated,
                )
            )

    return var_bins, lc_points, any_variable
