import math
import warnings

import astropy.units as u
from astropy.coordinates import Angle, SkyCoord, get_constellation
from astropy.time import Time


def parse_ra_dec(ra_raw: str | float, dec_raw: str | float) -> tuple[float, float]:
    """Parse decimal degrees or sexagesimal RA/Dec strings safely into ICRS degrees."""
    if isinstance(ra_raw, (int, float)) and isinstance(dec_raw, (int, float)):
        ra_val = float(ra_raw)
        dec_val = float(dec_raw)
    else:
        ra_str = str(ra_raw).strip()
        dec_str = str(dec_raw).strip()
        if len(ra_str) > 64 or len(dec_str) > 64:
            raise ValueError("Coordinate string exceeds maximum length")
        try:
            ra_val = float(ra_str)
            dec_val = float(dec_str)
        except ValueError:
            ra_unit = u.hourangle if ("h" in ra_str.lower() or ":" in ra_str) else u.deg
            ra_ang = Angle(ra_str, unit=ra_unit)
            dec_ang = Angle(dec_str, unit=u.deg)
            ra_val = float(ra_ang.deg) % 360.0
            dec_val = float(dec_ang.deg)

    if not (math.isfinite(ra_val) and math.isfinite(dec_val)):
        raise ValueError("Coordinates must be finite")
    if not (0.0 <= ra_val <= 360.0):
        raise ValueError(f"RA out of range [0, 360]: {ra_val}")
    if not (-90.0 <= dec_val <= 90.0):
        raise ValueError(f"Dec out of range [-90, 90]: {dec_val}")
    return ra_val, dec_val


def propagate_skycoord(
    ra_deg: float,
    dec_deg: float,
    ref_epoch_jyear: float,
    pm_ra_mas_yr: float | None,
    pm_dec_mas_yr: float | None,
    parallax_mas: float | None,
    target_mjd: float,
) -> tuple[float, float]:
    """Propagate ICRS position from reference J-epoch to target MJD using Astropy."""
    if pm_ra_mas_yr is None or pm_dec_mas_yr is None:
        return ra_deg, dec_deg
    if not (math.isfinite(pm_ra_mas_yr) and math.isfinite(pm_dec_mas_yr)):
        return ra_deg, dec_deg

    obs_time = Time(ref_epoch_jyear, format="jyear", scale="tcb")
    new_time = Time(target_mjd, format="mjd", scale="utc")

    kwargs: dict[str, object] = {
        "ra": ra_deg * u.deg,
        "dec": dec_deg * u.deg,
        "pm_ra_cosdec": pm_ra_mas_yr * u.mas / u.yr,
        "pm_dec": pm_dec_mas_yr * u.mas / u.yr,
        "obstime": obs_time,
        "frame": "icrs",
    }
    if parallax_mas is not None and math.isfinite(parallax_mas) and parallax_mas > 0.0:
        kwargs["distance"] = (1000.0 / parallax_mas) * u.pc

    coord = SkyCoord(**kwargs)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        propagated = coord.apply_space_motion(new_obstime=new_time)
    return float(propagated.ra.deg) % 360.0, float(propagated.dec.deg)


def constellation_for_coord(ra_deg: float, dec_deg: float) -> str:
    coord = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
    return str(get_constellation(coord))


def angular_separation_key(ra: float, dec: float, other_ra: float, other_dec: float) -> float:
    """Haversine separation key: spherical ordering without inverse trig."""
    lat, other_lat = math.radians(dec), math.radians(other_dec)
    return (
        math.sin((lat - other_lat) / 2.0) ** 2
        + math.cos(lat) * math.cos(other_lat) * math.sin(math.radians(ra - other_ra) / 2.0) ** 2
    )
