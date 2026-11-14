from typing import Any

import httpx

from app.archive.http_client import request_with_retries
from app.config import Settings


class AdsAdapter:
    """Harvard/SAO NASA ADS literature API client (graceful fallback when token absent)."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self._client = client

    async def search(self, query: str, rows: int = 5) -> tuple[str, list[dict[str, Any]]]:
        token = self.settings.nasa_ads_api_token.strip()
        if not token:
            return "not_configured", []

        own = self._client is None
        client = self._client or httpx.AsyncClient()
        try:
            resp = await request_with_retries(
                client,
                "GET",
                self.settings.nasa_ads_api_url,
                timeout=self.settings.catalog_timeout_sec,
                retries=1,
                headers={"Authorization": f"Bearer {token}"},
                params={
                    "q": query,
                    "fl": "bibcode,title,abstract,year,doi",
                    "rows": rows,
                    "sort": "citation_count desc",
                },
            )
            docs = resp.json().get("response", {}).get("docs", [])
            out: list[dict[str, Any]] = []
            for d in docs:
                bib = str(d.get("bibcode") or "")
                titles = d.get("title") or []
                title = str(titles[0]) if isinstance(titles, list) and titles else str(titles)
                dois = d.get("doi") or []
                doi = str(dois[0]) if isinstance(dois, list) and dois else None
                out.append(
                    {
                        "bibcode": bib,
                        "doi": doi,
                        "title": title,
                        "year": d.get("year"),
                        "abstract": str(d.get("abstract") or "")[:800],
                        "url": f"https://ui.adsabs.harvard.edu/abs/{bib}" if bib else "",
                    }
                )
            return "up", out
        except Exception:
            return "unavailable", []
        finally:
            if own:
                await client.aclose()
