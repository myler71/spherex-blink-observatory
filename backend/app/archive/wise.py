from typing import Any

import httpx

from app.archive.http_client import parse_csv_rows, request_with_retries
from app.config import Settings


class AllWiseAdapter:
    """IRSA AllWISE catalog (allwise_p3as_psd) TAP client (FR-18, V-10)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def query_cone(
        self, ra_deg: float, dec_deg: float, fov_deg: float
    ) -> tuple[str, list[dict[str, Any]]]:
        radius_deg = max(fov_deg * 0.75, 0.02)
        sql = (
            "SELECT TOP 100 designation, ra, dec, w1mpro, w2mpro, w3mpro, w4mpro, pmra, pmdec "
            "FROM allwise_p3as_psd "
            f"WHERE 1=CONTAINS(POINT('ICRS', ra, dec), CIRCLE('ICRS', {ra_deg:.6f}, {dec_deg:.6f}, {radius_deg:.5f}))"
        )
        own = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            resp = await request_with_retries(
                client,
                "POST",
                self.settings.irsa_tap_url,
                timeout=self.settings.catalog_timeout_sec,
                retries=1,
                data={"QUERY": sql, "LANG": "ADQL", "FORMAT": "csv"},
            )
            rows = parse_csv_rows(resp.text)
            out: list[dict[str, Any]] = []
            for r in rows:
                if not r.get("ra") or not r.get("dec"):
                    continue
                out.append(
                    {
                        "designation": r.get("designation"),
                        "ra": float(r["ra"]),
                        "dec": float(r["dec"]),
                        "w1mpro": float(r["w1mpro"]) if r.get("w1mpro") else None,
                        "w2mpro": float(r["w2mpro"]) if r.get("w2mpro") else None,
                        "pmra": float(r["pmra"]) if r.get("pmra") else None,
                        "pmdec": float(r["pmdec"]) if r.get("pmdec") else None,
                    }
                )
            return "up", out
        except Exception:
            return "unavailable", []
        finally:
            if own:
                await client.aclose()
