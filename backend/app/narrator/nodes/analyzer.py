import time
from typing import Any


async def patch_analyzer_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 1: Summarize compact patch & catalog context (never raw pixels)."""
    t0 = time.perf_counter()
    observe = state["observe"]
    movers = [o for o in observe.detected_objects if o.is_candidate_moving]
    variables = [o for o in observe.detected_objects if o.is_variable]
    dropouts = [
        o for o in observe.detected_objects if o.gaia_counterpart.status == "no_counterpart"
    ]
    matched_names: list[str] = []
    for o in observe.detected_objects:
        if o.catalog_matches:
            matched_names.append(o.catalog_matches[0].identifier)

    compact_summary = {
        "constellation": observe.constellation,
        "ra_deg": observe.query.ra,
        "dec_deg": observe.query.dec,
        "fov_deg": observe.query.fov,
        "baseline_days": observe.selection.baseline_days,
        "visits_count": observe.selection.visits_count,
        "num_detections": len(observe.detected_objects),
        "num_movers": len(movers),
        "num_variables": len(variables),
        "num_gaia_dropouts": len(dropouts),
        "matched_names": matched_names[:10],
    }
    timings = dict(state.get("node_timings_ms", {}))
    timings["patch_analyzer_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    return {
        "compact_summary": compact_summary,
        "matched_names": matched_names,
        "node_timings_ms": timings,
    }
