import time
from typing import Any, Literal

from app.narrator.templates import build_template_narrative
from app.narrator.validator import CHAPTER_TITLES
from app.schemas.narrative import (
    ChapterBlock,
    CosmicNarratorResponse,
    InteractiveStoryClaim,
    ValidationSummary,
)


async def story_generator_node(state: dict[str, Any]) -> dict[str, Any]:
    """Node 4: Generate structured 5-chapter story via LlmProvider or deterministic template."""
    t0 = time.perf_counter()
    observe = state["observe"]
    evidence = state["evidence"]
    llm = state["llm_provider"]
    feedback = state.get("validation_feedback", [])
    retries = int(state.get("retries", 0))

    if getattr(llm, "mode", "template") == "template":
        draft = build_template_narrative(observe, evidence)
    else:
        template_base = build_template_narrative(observe, evidence)
        try:
            raw_chapters = await llm.generate_chapters(
                state["compact_summary"], evidence, feedback=feedback
            )
            chapters: list[ChapterBlock] = []
            for idx in range(5):
                raw_claims = raw_chapters[idx] if idx < len(raw_chapters) else []
                parsed_claims = [InteractiveStoryClaim.model_validate(c) for c in raw_claims]
                chapters.append(
                    ChapterBlock(
                        chapter_index=idx + 1,
                        chapter_title=CHAPTER_TITLES[idx],
                        summary_prose=template_base.chapters[idx].summary_prose,
                        claims=parsed_claims,
                    )
                )
            gen_mode: Literal["llm", "template", "fake"] = (
                "fake" if getattr(llm, "mode", "") == "fake" else "llm"
            )
            draft = CosmicNarratorResponse(
                observation_id=observe.observation_id,
                patch_headline=template_base.patch_headline,
                constellation=observe.constellation,
                ra_deg=observe.query.ra,
                dec_deg=observe.query.dec,
                wiseview_verification_url=observe.overlays.wiseview_url,
                generator=gen_mode,
                chapters=chapters,
                validation=ValidationSummary(status="passed", retries=retries),
            )
        except Exception:
            draft = template_base

    timings = dict(state.get("node_timings_ms", {}))
    timings["story_generator_ms"] = round((time.perf_counter() - t0) * 1000.0, 2)
    return {"draft": draft, "node_timings_ms": timings}
