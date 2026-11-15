import hashlib
import logging
from urllib.parse import urlsplit

import httpx

from app.config import Settings
from app.schemas.narrative import EvidenceItem

logger = logging.getLogger(__name__)
NASA_DOMAINS = ("nasa.gov", "ipac.caltech.edu")


class TavilyNasaSearch:
    """Search NASA and NASA/IPAC sources; returned snippets are untrusted context."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client

    async def search(self, query: str) -> list[EvidenceItem]:
        if not self.settings.tavily_api_key.strip():
            return []
        payload = {
            "query": query[:500],
            "include_domains": list(NASA_DOMAINS),
            "search_depth": "basic",
            "max_results": 5,
            "include_raw_content": False,
        }
        headers = {"Authorization": f"Bearer {self.settings.tavily_api_key}"}
        try:
            if self.client is not None:
                response = await self.client.post(
                    "https://api.tavily.com/search", json=payload, headers=headers, timeout=10
                )
            else:
                async with httpx.AsyncClient(timeout=10) as client:
                    response = await client.post(
                        "https://api.tavily.com/search", json=payload, headers=headers
                    )
            response.raise_for_status()
            data = response.json()
        except (httpx.HTTPError, ValueError):
            logger.warning(
                "NASA web search unavailable; continuing with existing observation evidence"
            )
            return []
        items: list[EvidenceItem] = []
        seen: set[str] = set()
        for result in data.get("results", [])[:5]:
            if not isinstance(result, dict):
                continue
            url = str(result.get("url") or "")
            parsed = urlsplit(url)
            host = (parsed.hostname or "").lower()
            if (
                parsed.scheme != "https"
                or parsed.username
                or parsed.password
                or not any(host == d or host.endswith("." + d) for d in NASA_DOMAINS)
            ):
                continue
            excerpt = str(result.get("content") or "").strip()[:2000]
            if not excerpt or url in seen:
                continue
            seen.add(url)
            items.append(
                EvidenceItem(
                    evidence_id="ev_web_" + hashlib.sha256(url.encode()).hexdigest()[:12],
                    evidence_type="web_page",
                    source_name=str(result.get("title") or host)[:300],
                    source_type="NASA Web Resource",
                    reference_id=url,
                    url=url,
                    fact_payload={"excerpt": excerpt},
                )
            )
        return items
