from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.common import EncodedArray, ServiceStatus


class ObserveQuery(BaseModel):
    ra: float = Field(ge=0.0, le=360.0, allow_inf_nan=False)
    dec: float = Field(ge=-90.0, le=90.0, allow_inf_nan=False)
    fov: float = Field(default=0.08, ge=0.01, le=0.5, allow_inf_nan=False)
    release: str | None = None
    mode: Literal["motion", "variability", "both"] = "both"
    detector: int | None = Field(default=None, ge=1, le=6)
    wave_min: float | None = Field(default=None, ge=0.5, le=6.0, allow_inf_nan=False)
    wave_max: float | None = Field(default=None, ge=0.5, le=6.0, allow_inf_nan=False)
    max_frames: int = Field(default=12, ge=1, le=24)
    propagate: bool = True
    target: str | None = None
    include_overlays: bool = True
    include_csa_neossat: bool = False
    include_horizons: bool = False
    include_variance: bool = True
    linear: float = Field(default=0.15, ge=0.001, le=1.0, allow_inf_nan=False)
    min_pct: float = Field(default=1.5, ge=0.0, le=49.0, allow_inf_nan=False)
    max_pct: float = Field(default=99.4, ge=50.0, le=100.0, allow_inf_nan=False)
    invert: bool = False
    share_url: str = ""


class WcsGrid(BaseModel):
    crval1: float
    crval2: float
    crpix1: float
    crpix2: float
    cdelt1: float
    cdelt2: float
    ctype1: str = "RA---TAN"
    ctype2: str = "DEC--TAN"
    naxis1: int
    naxis2: int
    pixel_scale_arcsec: float


class FlagSummary(BaseModel):
    total_pixels: int
    rejected_pixels: int
    fraction_rejected: float
    bit_counts: dict[str, int] = Field(default_factory=dict)
    bit_descriptions: dict[str, str] = Field(default_factory=dict)


class FrameProvenance(BaseModel):
    obs_id: str
    release: str
    detector: int | None = None
    mjd: float | None = None
    iso_date: str | None = None
    central_wavelength_um: float | None = None
    bandwidth_um: float | None = None
    psf_fwhm_arcsec: float | None = None
    zodi_level_mjy_sr: float | None = None
    provenance_version: str | None = None
    archive_url: str
    wavelength_method: str = "WCS-WAVE"
    missing_reason: str | None = None


class FrameData(BaseModel):
    obs_id: str
    mjd: float | None = None
    iso_date: str | None = None
    release: str
    detector: int | None = None
    central_wavelength_um: float | None = None
    bandwidth_um: float | None = None
    width: int
    height: int
    pixels: EncodedArray
    variance: EncodedArray | None = None
    flags_mask: EncodedArray
    display_u8: EncodedArray
    flipbook_diff_u8: EncodedArray | None = None
    provenance: FrameProvenance
    flag_summary: FlagSummary


class SkippedFrame(BaseModel):
    obs_id: str
    archive_url: str
    reason: str


class SelectionSummary(BaseModel):
    total_candidates: int
    selected_count: int
    visits_count: int
    wavelength_bins_count: int
    matching_tolerance_um: float
    baseline_days: float


class MotionMeasurement(BaseModel):
    pm_ra_cosdec_mas_yr: float | None = None
    pm_dec_mas_yr: float | None = None
    pm_total_mas_yr: float | None = None
    pm_total_arcsec_yr: float | None = None
    position_angle_deg: float | None = None
    pm_ra_err_mas_yr: float | None = None
    pm_dec_err_mas_yr: float | None = None
    pm_total_err_mas_yr: float | None = None
    significance_sigma: float | None = None
    fit_residual_arcsec: float | None = None
    num_visits: int
    baseline_days: float
    parallax_mas: float | None = None
    parallax_err_mas: float | None = None
    parallax_status: str
    reason: str | None = None


class VariabilityBin(BaseModel):
    bin_id: str
    wavelength_center_um: float
    bandwidth_um: float
    n_points: int
    dof: int
    weighted_mean_flux: float
    reduced_chi2: float | None = None
    is_variable: bool
    cross_band: bool = False
    reason: str | None = None


class LightCurvePoint(BaseModel):
    obs_id: str
    mjd: float
    iso_date: str | None = None
    detector: int | None = None
    wavelength_um: float
    bandwidth_um: float
    bin_id: str
    flux: float
    flux_err: float
    snr: float
    contaminated: bool


class GaiaCounterpart(BaseModel):
    status: Literal["has_counterpart", "no_counterpart", "unknown"]
    wording: str
    separation_arcsec: float | None = None
    source_id: str | None = None
    ra_deg: float | None = None
    dec_deg: float | None = None
    pmra_mas_yr: float | None = None
    pmdec_mas_yr: float | None = None
    parallax_mas: float | None = None
    phot_g_mean_mag: float | None = None


class CatalogMatch(BaseModel):
    catalog: str
    identifier: str
    otype: str | None = None
    separation_arcsec: float
    ra_deg: float
    dec_deg: float
    url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class DetectedObject(BaseModel):
    id: str
    name: str
    x: float
    y: float
    ra: float
    dec: float
    snr: float
    contaminated: bool
    n_detections: int
    motion: MotionMeasurement
    dx_pixels_per_yr: float | None = None
    dy_pixels_per_yr: float | None = None
    is_candidate_moving: bool
    variability: list[VariabilityBin] = Field(default_factory=list)
    is_variable: bool
    light_curve: list[LightCurvePoint] = Field(default_factory=list)
    gaia_counterpart: GaiaCounterpart
    catalog_matches: list[CatalogMatch] = Field(default_factory=list)


class ComparisonProduct(BaseModel):
    status: Literal["ok", "omitted"]
    reason: str | None = None
    earlier_obs_id: str | None = None
    later_obs_id: str | None = None
    wavelength_um: float | None = None
    delta_days: float | None = None
    cross_band: bool = False
    difference_pixels: EncodedArray | None = None
    difference_u8: EncodedArray | None = None
    addition_pixels: EncodedArray | None = None
    addition_u8: EncodedArray | None = None


class CoaddProduct(BaseModel):
    detector: int
    visit_index: int
    bin_id: str
    wavelength_um: float
    n_frames: int
    contributing_obs_ids: list[str]
    pixels: EncodedArray
    display_u8: EncodedArray
    effective_snr_gain: float


class SpectrumPoint(BaseModel):
    obs_id: str
    mjd: float | None = None
    detector: int | None = None
    wavelength_um: float
    bandwidth_um: float
    flux: float
    flux_err: float
    snr: float
    contaminated: bool


class SpectrumResponse(BaseModel):
    observation_id: str
    ra_deg: float
    dec_deg: float
    object_id: str | None = None
    non_simultaneous_note: str = (
        "Flux measurements originate from different observation epochs (MJD); "
        "intrinsic source variability can modulate apparent spectral shape."
    )
    points: list[SpectrumPoint] = Field(default_factory=list)


class OverlayBundle(BaseModel):
    gaia_dr3_status: ServiceStatus
    gaia_dr3: list[dict[str, Any]] = Field(default_factory=list)
    gaia_truncated: bool = False
    allwise_status: ServiceStatus
    allwise: list[dict[str, Any]] = Field(default_factory=list)
    simbad_status: ServiceStatus
    simbad: list[dict[str, Any]] = Field(default_factory=list)
    vizier_status: ServiceStatus
    vizier: list[dict[str, Any]] = Field(default_factory=list)
    ned_status: ServiceStatus
    ned: list[dict[str, Any]] = Field(default_factory=list)
    neossat_status: ServiceStatus
    neossat: list[dict[str, Any]] = Field(default_factory=list)
    horizons_status: ServiceStatus
    horizons: list[dict[str, Any]] = Field(default_factory=list)
    wiseview_url: str


class AttributionInfo(BaseModel):
    acknowledgements: dict[str, str]
    dois: dict[str, str]
    libraries: list[str]


class StageTimings(BaseModel):
    total_ms: float
    stages_ms: dict[str, float] = Field(default_factory=dict)


class ObserveResponse(BaseModel):
    observation_id: str
    pipeline_version: str
    served_from: Literal["live", "cache"]
    cached_at: str | None = None
    query: ObserveQuery
    constellation: str
    reference_grid: WcsGrid
    selection: SelectionSummary
    frames: list[FrameData]
    comparisons: ComparisonProduct
    coadds: list[CoaddProduct] = Field(default_factory=list)
    detected_objects: list[DetectedObject] = Field(default_factory=list)
    overlays: OverlayBundle
    warnings: list[str] = Field(default_factory=list)
    skipped: list[SkippedFrame] = Field(default_factory=list)
    attribution: AttributionInfo
    timings: StageTimings
