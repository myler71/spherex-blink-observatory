from typing import Any

import httpx

from app.archive.http_client import request_with_retries
from app.config import Settings


class VizierAdapter:
    """Dual-mirror VizieR cone availability probe."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def query_cone(
        self, ra_deg: float, dec_deg: float, fov_deg: float
    ) -> tuple[str, list[dict[str, Any]]]:
        radius_arcmin = max(fov_deg * 60.0 * 0.75, 1.0)
        own = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            for base_url in self.settings.vizier_urls:
                try:
                    resp = await request_with_retries(
                        client,
                        "GET",
                        base_url,
                        timeout=self.settings.catalog_timeout_sec,
                        retries=0,
                        params={
                            "-source": "II/328",
                            "-c": f"{ra_deg:.5f} {dec_deg:+.5f}",
                            "-c.rm": f"{radius_arcmin:.2f}",
                            "-out.max": "25",
                        },
                    )
                    if resp.status_code == 200:
                        return "up", [
                            {
                                "catalog": "II/328 (AllWISE)",
                                "url": str(resp.url),
                                "bytes": len(resp.content),
                            }
                        ]
                except Exception:
                    continue
            return "unavailable", []
        finally:
            if own:
                await client.aclose()
