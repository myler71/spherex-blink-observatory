# SPHEREx Blink Observatory — Scientific Methodology (`docs/SCIENCE.md`)

## 1. Two-Brains Principle
All numerical astrophysical measurements originate in `backend/app/science/` or validated astronomical catalogs. No LLM or agentic workflow detects sources, estimates coordinates, fits motion, or computes variability.

## 2. Observation Selection & LVF Constraint
- **Releases:** SPHEREx **DR1** (`spherex_dr1`, `spherex_dr1_deep`) and **QR3** (`spherex_qr3`, `spherex_qr3_deep`) are queried via IRSA TAP (`spherex.artifact`, `spherex.plane`, `spherex.observation`), deduplicated by `observationid`/`planeid`.
- **Visit Clustering:** Exposures are grouped into visits separated by configurable time gaps (`> 5.0` days default).
- **Wavelength Matching:** SPHEREx employs Linear Variable Filters (LVFs) across 6 detectors (`0.75–5.0 µm`). Photometry and difference imaging compare only observations within the same wavelength bin (`|λ_i − λ_bin| <= band_match_fraction * Δλ_local`, default `0.5`). Cross-band comparisons never occur unless explicitly marked `cross_band=true`.

## 3. Target Epoch Propagation (`FR-04`)
Nearby high-proper-motion targets (e.g., Barnard's Star at ~10.39 arcsec/yr, WISE 0855 at ~8.15 arcsec/yr) drift multiple arcminutes between J2000/J2016.0 and 2025–2026 SPHEREx epochs. Reference coordinates `(ra, dec, pmra, pmdec, parallax, epoch)` are propagated to each visit epoch using `astropy.coordinates.SkyCoord.apply_space_motion()`.

## 4. Calibration, Quality Flags & Wavelength (`FR-05`, `FR-06`, `FR-15`)
- **Zodiacal Light Subtraction:** `clean = IMAGE - ZODI` (when `ZODI` HDU is present; otherwise recorded as a warning).
- **Quality Bitmask (`FLAGS`):** Verified against DR1/QR3 headers (`MSKN*`/`MSKD*`):
  - Rejected bits (default): `0` (`TRANSIENT`), `1` (`OVERFLOW`), `2` (`SUR_ERROR`), `6` (`NONFUNC`), `9` (`MISSING_DATA`), `10` (`HOT`), `11` (`COLD`), `15` (`NONLINEAR`), `17` (`PERSIST`), `19` (`OUTLIER`), `25` (`STREAK`), `26` (`BLOOM`), `27` (`SNOWBALL`).
  - Preserved informational bits: `12` (`FULLSAMPLE`), `21` (`SOURCE`), plus caution flags (`7: DICHROIC`, `14: PHANMISS`, `20: CROSSTALK`, `22–24: GHOST*`, `28: HALO`) reported in provenance.
- **Spectral WCS:** Per-pixel central wavelength and bandwidth are computed via `WCS(header, fobj=hdul, key="W")` with `sip = None`.

## 5. Astrometric Alignment & Uncertainty Propagation (`FR-07`)
All selected frames are reprojected onto a common north-up tangent-plane (`TAN`) reference WCS centered on the requested `(ra, dec)` at native SPHEREx pixel scale (~6.16 arcsec/px) using `reproject.reproject_interp`. Variance planes are transformed with bilinear interpolation and scaled by local pixel-area Jacobian squared, and bad-pixel masks are conservatively propagated so any output pixel touched by a masked input pixel (`reprojected_mask > 0`) is masked.

## 6. Source Extraction, Linking & Motion (`FR-08`, `FR-09`)
- **Detection:** `sep.Background` estimates spatially varying sky background and RMS; `sep.extract` extracts sub-pixel centroids `(x, y)`, windowed/isophotal fluxes, flux errors, SNR, and aperture mask contamination flags.
- **Linking:** Detections across all epochs are converted to 3D ICRS unit vectors and matched across epochs via `scipy.spatial.cKDTree` within configurable angular radius (`12.0` arcsec default).
- **Proper Motion & Parallax:** Inverse-variance weighted linear regression fits $\alpha^*(t) = \alpha^*_0 + \mu_{\alpha*} (t - t_0)$ (accounting for $\cos\delta$) and $\delta(t) = \delta_0 + \mu_\delta (t - t_0)$, reporting $\mu_{\alpha*}$, $\mu_\delta$, total $\mu$, position angle, formal $1\sigma$ uncertainties, reduced residual, and motion significance ($\mu / \sigma_\mu \ge 3.0$). When $\ge 3$ visits span $\ge 90$ days, a joint 5-parameter parallax + proper-motion linear design matrix is evaluated; otherwise `parallax_status` explains why parallax is not separated.

## 7. Variability, Comparisons, Co-adds & Spectra (`FR-10`–`FR-13`)
- **Variability:** Within each wavelength bin, reduced $\chi^2_\nu = \frac{1}{N-1}\sum_i \frac{(F_i - \bar{F}_w)^2}{\sigma_i^2}$ is reported alongside `dof = N - 1` (flagged variable when $\chi^2_\nu \ge 6.0$ and `dof >= 1`).
- **Difference & Addition:** Computed strictly between matched-wavelength frames from distinct visits, plus a "frame minus median reference" flipbook sequence.
- **Co-adds:** Inverse-variance weighted stacks per `(detector, visit, wavelength_bin)`.
- **On-the-fly Spectra:** Flux vs. true wavelength sorted ascending with observation provenance and an explicit non-simultaneity notice.

## 8. Known Limits & Caveats
- Undersampled SPHEREx pixels (~6.16"/px) mean bright saturated stars or heavily blended fields (e.g., Epsilon Indi A near Epsilon Indi B) can limit centroid accuracy or saturate detectors.
- Faint cold brown dwarfs (e.g., WISE 0855) may only be detected at $\ge 3\text{–}5\sigma$ in long-wavelength detectors (`D4–D6`, 2.4–5.0 µm).
- Gaia DR3 optical dropout (`no_counterpart`) indicates absence of a Gaia optical detection within matching radius under a non-truncated, successful Gaia query; it is never proof of object nature.
