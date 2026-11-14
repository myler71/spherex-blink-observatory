from typing import Any
from urllib.parse import quote

import httpx

from app.archive.http_client import parse_csv_rows, request_with_retries
from app.config import Settings


class SimbadAdapter:
    """Dual-mirror SIMBAD TAP client (Harvard CFA + CDS Strasbourg, V-11)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def query_cone(
        self, ra_deg: float, dec_deg: float, fov_deg: float
    ) -> tuple[str, list[dict[str, Any]]]:
        radius_deg = max(fov_deg * 0.75, 0.02)
        sql = (
            "SELECT TOP 50 main_id, otype, ra, dec, pmra, pmdec, plx_value "
            "FROM basic "
            f"WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra_deg:.6f}, {dec_deg:.6f}, {radius_deg:.5f}))"
        )
        own = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            for base_url in self.settings.simbad_tap_urls:
                try:
                    resp = await request_with_retries(
                        client,
                        "POST",
                        base_url,
                        timeout=self.settings.catalog_timeout_sec,
                        retries=0,  # fast failover on 404/timeout
                        data={"REQUEST": "doQuery", "LANG": "ADQL", "FORMAT": "csv", "QUERY": sql},
                    )
                    rows = parse_csv_rows(resp.text)
                    out: list[dict[str, Any]] = []
                    for r in rows:
                        if not r.get("ra") or not r.get("dec"):
                            continue
                        mid = str(r.get("main_id") or "")
                        out.append(
                            {
                                "main_id": mid,
                                "otype": r.get("otype"),
                                "ra": float(r["ra"]),
                                "dec": float(r["dec"]),
                                "pmra": float(r["pmra"]) if r.get("pmra") else None,
                                "pmdec": float(r["pmdec"]) if r.get("pmdec") else None,
                                "plx_value": float(r["plx_value"]) if r.get("plx_value") else None,
                                "url": f"https://simbad.harvard.edu/simbad/sim-id?Ident={quote(mid)}",
                            }
                        )
                    return "up", out
                except Exception:
                    continue
            return "unavailable", []
        finally:
            if own:
                await client.aclose()
