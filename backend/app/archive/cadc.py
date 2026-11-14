from typing import Any

import httpx

from app.archive.http_client import parse_csv_rows, request_with_retries
from app.config import Settings


class CadcNeossatAdapter:
    """CSA/CADC NEOSSat observation metadata TAP client (FR-18, V-11)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def query_cone(
        self, ra_deg: float, dec_deg: float, fov_deg: float
    ) -> tuple[str, list[dict[str, Any]]]:
        radius_deg = max(fov_deg * 1.5, 0.2)
        sql = (
            "SELECT TOP 25 o.observationID, o.collection, o.target_name, o.instrument_name, "
            "p.time_bounds_lower, p.time_exposure "
            "FROM caom2.Observation o JOIN caom2.Plane p ON o.obsID = p.obsID "
            "WHERE o.collection = 'NEOSSAT' "
            f"AND 1=INTERSECTS(CIRCLE('ICRS', {ra_deg:.5f}, {dec_deg:.5f}, {radius_deg:.4f}), p.position_bounds)"
        )
        own = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            resp = await request_with_retries(
                client,
                "POST",
                self.settings.cadc_tap_url,
                timeout=self.settings.catalog_timeout_sec,
                retries=1,
                data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": sql},
            )
            rows = parse_csv_rows(resp.text)
            out = [
                {
                    "observation_id": r.get("observationID"),
                    "collection": r.get("collection", "NEOSSAT"),
                    "target_name": r.get("target_name"),
                    "instrument_name": r.get("instrument_name"),
                    "mjd": float(r["time_bounds_lower"]) if r.get("time_bounds_lower") else None,
                    "exposure_sec": float(r["time_exposure"]) if r.get("time_exposure") else None,
                    "note": "Supplementary CSA NEOSSat observation; not independent confirmation.",
                }
                for r in rows
            ]
            return "up", out
        except Exception:
            return "unavailable", []
        finally:
            if own:
                await client.aclose()
