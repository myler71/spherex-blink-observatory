from types import SimpleNamespace

import pytest

from app.config import Settings
from app.narrator.ask import AskThisPatchService
from app.schemas.narrative import EvidenceItem, EvidenceStoreResponse


@pytest.mark.asyncio
async def test_search_snippet_does_not_substitute_for_observed_spectrum(monkeypatch):
    web = EvidenceItem(
        evidence_id="ev_web_test",
        evidence_type="web_page",
        source_name="NASA SPHEREx",
        source_type="NASA Web Resource",
        reference_id="nasa",
        url="https://science.nasa.gov/mission/spherex/",
        fact_payload={"excerpt": "SPHEREx observes infrared light."},
    )

    async def search(self, query):
        return [web]

    class Provider:
        mode = "llm"

        async def answer_question(self, question, evidence):
            return {"answer": "SPHEREx observes infrared light."}

    monkeypatch.setattr("app.narrator.ask.TavilyNasaSearch.search", search)
    observation = SimpleNamespace(observation_id="obs_test")
    evidence = EvidenceStoreResponse(observation_id="obs_test", pipeline_version="1", items=[])
    result = await AskThisPatchService(Settings(), Provider()).answer(
        observation, evidence, "What is the SPHEREx spectrum?"
    )
    assert result.validation.status == "fallback_template"
    assert "central wavelengths" not in result.answer
    assert "not recorded" in result.answer
    assert result.sources[0].url == web.url
    assert result.claims == []
