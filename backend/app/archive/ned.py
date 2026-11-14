from typing import Any

import httpx

from app.archive.http_client import request_with_retries
from app.config import Settings


class NedAdapter:
    """NASA/IPAC Extragalactic Database (NED) cone adapter."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def query_cone(
        self, ra_deg: float, dec_deg: float, fov_deg: float
    ) -> tuple[str, list[dict[str, Any]]]:
        radius_arcmin = min(max(fov_deg * 60.0 * 0.75, 1.0), 10.0)
        own = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            resp = await request_with_retries(
                client,
                "GET",
                self.settings.ned_url,
                timeout=self.settings.catalog_timeout_sec,
                retries=0,
                params={
                    "search_type": "Near Position Search",
                    "in_csys": "Equatorial",
                    "in_equinox": "J2000.0",
                    "lon": f"{ra_deg:.5f}d",
                    "lat": f"{dec_deg:.5f}d",
                    "radius": f"{radius_arcmin:.2f}",
                    "of": "ascii_tab",
                },
            )
            lines = [
                ln for ln in resp.text.splitlines() if ln and not ln.startswith("#") and "|" in ln
            ]
            out: list[dict[str, Any]] = []
            for ln in lines[1:26]:
                cols = [c.strip() for c in ln.split("|")]
                if len(cols) >= 5:
                    out.append({"object_name": cols[1], "type": cols[4], "ra": cols[2], "dec": cols[3]})
            return "up", out
        except Exception:
            return "unavailable", []
        finally:
            if own:
                await client.aclose()
