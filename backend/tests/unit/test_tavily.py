import json

import httpx
import pytest

from app.archive.tavily import TavilyNasaSearch
from app.config import Settings


@pytest.mark.asyncio
async def test_search_scopes_and_filters_results():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-key"
        payload = json.loads(request.content)
        assert payload["include_domains"] == ["nasa.gov", "ipac.caltech.edu"]
        assert payload["query"] == "SPHEREx infrared spectrum"
        return httpx.Response(
            200,
            json={
                "results": [
                    {
                        "url": "https://science.nasa.gov/mission/spherex/",
                        "title": "SPHEREx",
                        "content": "NASA infrared survey.",
                    },
                    {
                        "url": "https://nasa.gov.evil.example/page",
                        "title": "Spoof",
                        "content": "bad",
                    },
                    {"url": "http://nasa.gov/insecure", "title": "Insecure", "content": "bad"},
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        search = TavilyNasaSearch(Settings(tavily_api_key="test-key"), client=client)
        results = await search.search("SPHEREx infrared spectrum")
    assert len(results) == 1
    assert results[0].url == "https://science.nasa.gov/mission/spherex/"
    assert results[0].fact_payload["excerpt"] == "NASA infrared survey."


@pytest.mark.asyncio
async def test_missing_key_performs_no_network_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("unexpected request")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        search = TavilyNasaSearch(Settings(tavily_api_key=""), client=client)
        assert await search.search("SPHEREx") == []
