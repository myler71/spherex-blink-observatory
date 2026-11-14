from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables (V-01..V-12)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application
    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://localhost:5173"]
    )
    pipeline_version: str = "1.0.0"

    # SPHEREx IRSA Archive (V-01, V-02, V-03)
    irsa_tap_url: str = "https://irsa.ipac.caltech.edu/TAP/sync"
    irsa_sia_url: str = "https://irsa.ipac.caltech.edu/SIA"
    irsa_cutout_base_url: str = "https://irsa.ipac.caltech.edu"
    # V-02: DR1 & QR3 supersede QR2
    spherex_releases: list[str] = Field(
        default_factory=lambda: [
            "spherex_dr1",
            "spherex_dr1_deep",
            "spherex_qr3",
            "spherex_qr3_deep",
        ]
    )
    # V-06: Reject only defect bits; NEVER reject 12 (FULLSAMPLE) or 21 (SOURCE)
    spherex_reject_flag_bits: list[int] = Field(
        default_factory=lambda: [0, 1, 2, 6, 9, 10, 11, 15, 17, 19, 25, 26, 27]
    )
    spherex_cutout_min_fov_deg: float = 0.01
    spherex_cutout_max_fov_deg: float = 0.5
    spherex_cutout_concurrency: int = 6
    spherex_http_timeout_sec: float = 30.0
    spherex_http_retries: int = 2
    spherex_max_frames_cap: int = 24
    spherex_default_max_frames: int = 12
    spherex_native_pixel_scale_arcsec: float = 6.16  # V-08

    # Science Pipeline Thresholds
    visit_gap_days: float = 5.0  # V-09
    match_radius_arcsec: float = 12.0
    gaia_match_radius_arcsec: float = 3.5
    simbad_match_radius_arcsec: float = 5.0
    detection_sigma: float = 3.2
    min_snr: float = 4.5
    pm_significance_sigma: float = 3.0
    parallax_min_baseline_days: float = 180.0
    parallax_max_cond: float = 100.0
    variability_reduced_chi2: float = 6.0
    band_match_fraction: float = 0.5
    max_reject_fraction: float = 0.85

    # External Catalogs & Literature (V-10, V-11)
    gaia_tap_url: str = "https://gea.esac.esa.int/tap-server/tap/sync"
    gaia_max_rows: int = 500
    # V-11: Harvard mirror first when cds.unistra.fr returns 404
    simbad_tap_urls: list[str] = Field(
        default_factory=lambda: [
            "https://simbad.harvard.edu/simbad/sim-tap/sync",
            "https://simbad.cds.unistra.fr/simbad/sim-tap/sync",
        ]
    )
    vizier_urls: list[str] = Field(
        default_factory=lambda: [
            "https://vizier.cfa.harvard.edu/viz-bin/votable",
            "https://vizier.cds.unistra.fr/viz-bin/votable",
        ]
    )
    ned_url: str = "https://ned.ipac.caltech.edu/cgi-bin/objsearch"
    cadc_tap_url: str = "https://ws.cadc-ccda.hia-iha.nrc-cnrc.gc.ca/argus/sync"
    horizons_api_url: str = "https://ssd.jpl.nasa.gov/api/horizons.api"
    nasa_ads_api_token: str = ""
    nasa_ads_api_url: str = "https://api.adsabs.harvard.edu/v1/search/query"
    catalog_timeout_sec: float = 6.0

    # Storage & Cache
    database_url: str = "postgresql+psycopg://spherex:spherex@localhost:5432/spherex"
    redis_url: str = "redis://localhost:6379/0"
    cache_dir: str = "./data/cache"
    cache_ttl_seconds: int = 86400
    disk_cache_max_mb: int = 1024

    # LLM Provider
    llm_provider: Literal["template", "fake", "openai_compatible"] = "template"
    llm_model: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    prompt_version: str = "1.0.0"
    embedding_dim: int = 384

    # Rate Limiting (per client IP per minute)
    observe_rate_limit_per_min: int = 30
    narrative_rate_limit_per_min: int = 20
    ask_rate_limit_per_min: int = 30
    ask_max_question_chars: int = 500


@lru_cache
def get_settings() -> Settings:
    return Settings()
