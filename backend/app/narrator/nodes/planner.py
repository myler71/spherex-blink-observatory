import time
from typing import Any


async def research_planner_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 2: Derive search topics & queries from patch detections."""
    t0 = time.perf_counter()
    summary = state["compact_summary"]
    names = state.get("matched_names", [])
    topics: list[str] = ["SPHEREx"]
    if summary.get("num_movers", 0) > 0:
        topics.append("high proper motion brown dwarf")
    if summary.get("num_variables", 0) > 0:
        topics.append("infrared variable star")
    if summary.get("num_gaia_dropouts", 0) > 0:
        topics.append("Gaia optical dropout infrared source")

    query_text = " ".join(names[:3] + topics[:3])
    timings = dict(state.get("node_timings_ms", {}))
    timings["research_planner_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "research_query": query_text,
        "object_identifiers": names[:10],
        "node_timings_ms": timings,
    }
