import time
from typing import Any

from app.narrator.templates import build_template_narrative
from app.narrator.validator import ClaimValidator


async def claim_validator_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 5: Deterministic validation with bounded retry & template fallback (FR-29)."""
    t0 = time.perf_counter()
    observe = state["observe"]
    evidence = state["evidence"]
    draft = state["draft"]
    retries = int(state.get("retries", 0))
    max_retries = int(state.get("max_retries", 2))

    valid_markers = {o.id for o in observe.detected_objects}
    validator = ClaimValidator()
    cleaned, ok = validator.validate(draft, evidence, valid_markers)

    timings = dict(state.get("node_timings_ms", {}))
    timings["claim_validator_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)

    if ok:
        final = cleaned.model_copy(
            update={
                "node_timings_ms": timings,
                "validation": cleaned.validation.model_copy(update={"retries": retries}),
            }
        )
        return {"final_story": final, "should_retry": False, "node_timings_ms": timings}

    if retries < max_retries and getattr(state["llm_provider"], "mode", "template") != "template":
        return {
            "retries": retries + 1,
            "validation_feedback": cleaned.validation.rejection_reasons[:10],
            "should_retry": True,
            "node_timings_ms": timings,
        }

    # Retry budget exhausted: keep valid partial claims if any, else deterministic template
    total_surviving = sum(len(ch.claims) for ch in cleaned.chapters)
    if total_surviving > 0:
        final = cleaned.model_copy(
            update={
                "node_timings_ms": timings,
                "validation": cleaned.validation.model_copy(
                    update={"status": "partial", "retries": retries}
                ),
            }
        )
    else:
        tmpl = build_template_narrative(observe, evidence)
        final = tmpl.model_copy(
            update={
                "generator": "template",
                "node_timings_ms": timings,
                "validation": tmpl.validation.model_copy(
                    update={
                        "status": "fallback_template",
                        "retries": retries,
                        "rejected_claims": cleaned.validation.rejected_claims,
                        "rejection_reasons": cleaned.validation.rejection_reasons,
                    }
                ),
            }
        )
    return {"final_story": final, "should_retry": False, "node_timings_ms": timings}
