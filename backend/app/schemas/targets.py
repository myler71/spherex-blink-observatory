from typing import Literal

from pydantic import BaseModel


class TargetPreset(BaseModel):
    id: str
    name: str
    object_type: str
    ra_deg: float
    dec_deg: float
    default_fov_deg: float = 0.08
    ref_epoch_jyear: float = 2016.0
    pm_ra_mas_yr: float
    pm_dec_mas_yr: float
    parallax_mas: float | None = None
    recommended_mode: Literal["motion", "variability", "both"]
    expected_pm_arcsec_yr: float | None = None
    expected_variable: bool
    citation: str
    reference_url: str
    is_negative_control: bool = False


class TargetsResponse(BaseModel):
    targets: list[TargetPreset]
