from typing import Any

from astropy.coordinates import SkyCoord
from astropy.time import Time
import astropy.units as u
import httpx

from app.archive.http_client import request_with_retries
from app.config import Settings

# Curated bright Solar System bodies checked against observation epoch via Horizons ephemerides
_CHECKED_SOLAR_SYSTEM_BODIES: list[tuple[str, str]] = [
    ("499", "Mars"),
    ("599", "Jupiter"),
    ("699", "Saturn"),
    ("1", "Ceres"),
    ("4", "Vesta"),
]


class HorizonsAdapter:
    """JPL Horizons Solar System body ephemeris check at observation epoch (FR-18, V-11)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def query_epoch(
        self, ra_deg: float, dec_deg: float, fov_deg: float, mjd: float
    ) -> tuple[str, list[dict[str, Any]]]:
        t_iso = Time(mjd, format="mjd", scale="utc").strftime("%Y-%m-%d")
        target_sc = SkyCoord(ra=ra_deg * u.deg, dec=dec_deg * u.deg, frame="icrs")
        own = self._client is None
        client = self._client or httpx.AsyncClient()
        matches: list[dict[str, Any]] = []
        try:
            for cmd, name in _CHECKED_SOLAR_SYSTEM_BODIES:
                try:
                    resp = await request_with_retries(
                        client,
                        "GET",
                        self.settings.horizons_api_url,
                        timeout=self.settings.catalog_timeout_sec,
                        retries=0,
                        params={
                            "format": "json",
                            "COMMAND": f"'{cmd}'",
                            "EPHEM_TYPE": "'OBSERVER'",
                            "CENTER": "'500@399'",
                            "TLIST": f"'{t_iso}'",
                            "QUANTITIES": "'1'",
                        },
                    )
                    txt = resp.json().get("result", "")
                    if "$$SOE" in txt and "$$EOE" in txt:
                        soe = txt.split("$$SOE", 1)[1].split("$$EOE", 1)[0].strip()
                        parts = soe.splitlines()[0].split()
                        if len(parts) >= 8:
                            ra_str = f"{parts[2]}h{parts[3]}m{parts[4]}s"
                            dec_str = f"{parts[5]}d{parts[6]}m{parts[7]}s"
                            body_sc = SkyCoord(ra_str, dec_str, frame="icrs")
                            sep_deg = float(target_sc.separation(body_sc).deg)
                            if sep_deg <= max(fov_deg, 0.5):
                                matches.append(
                                    {
                                        "body_id": cmd,
                                        "name": name,
                                        "ra_deg": round(float(body_sc.ra.deg), 5),
                                        "dec_deg": round(float(body_sc.dec.deg), 5),
                                        "separation_arcsec": round(sep_deg * 3600.0, 2),
                                    }
                                )
                except Exception:
                    continue
            return "up", matches
        except Exception:
            return "unavailable", []
        finally:
            if own:
                await client.aclose()
