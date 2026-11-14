import asyncio
import time
from typing import Any

from app.narrator.evidence import EvidenceBuilder


async def retriever_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 3: Parallel local hybrid store search + NASA ADS literature search."""
    t0 = time.perf_counter()
    docs_store = state["docs_store"]
    ads_adapter = state.get("ads_adapter")
    observe = state["observe"]
    query = state.get("research_query", "SPHEREx")
    obj_ids = state.get("object_identifiers", [])

    async def _local_search() -> list[dict[str, Any]]:
        if hasattr(docs_store, "search_documents"):
            return await docs_store.search_documents(query, object_identifiers=obj_ids, limit=5)  # type: ignore[no-any-return]
        return list(await asyncio.to_thread(docs_store.search, query, obj_ids, 5))

    async def _ads_search() -> list[dict[str, Any]]:
        if ads_adapter is None:
            return []
        _, papers = await ads_adapter.search(query, rows=5)
        return list(papers)

    local_docs, ads_papers = await asyncio.gather(_local_search(), _ads_search())
    # Rebuild evidence bundle enriched with retrieved literature if not pre-supplied
    base_ev = state.get("evidence")
    if base_ev is None or local_docs or ads_papers:
        evidence = EvidenceBuilder().build(observe, docs=local_docs, ads_papers=ads_papers)
    else:
        evidence = base_ev

    timings = dict(state.get("node_timings_ms", {}))
    timings["retriever_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "retrieved_docs": local_docs,
        "ads_papers": ads_papers,
        "evidence": evidence,
        "node_timings_ms": timings,
    }
