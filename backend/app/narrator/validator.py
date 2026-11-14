import re
from typing import Any, Literal

from app.schemas.narrative import (
    ChapterBlock,
    CitationItem,
    CosmicNarratorResponse,
    EvidenceItem,
    EvidenceStoreResponse,
    InteractiveStoryClaim,
    ValidationSummary,
)

CHAPTER_TITLES: list[str] = [
    "Where are we looking?",
    "Who lives here?",
    "A universe in motion.",
    "What does SPHEREx see?",
    "The science behind this region.",
]

_BANNED_PHRASES_RE = re.compile(
    r"\b("
    r"planet[\s-]*(nine|9|x)|"
    r"(ninth|9th)[\s-]*planet|"
    r"confirmed\s*discovery|"
    r"first\s*detection|"
    r"discovered\s+(a\s+)?(new\s+)?planet"
    r")\b",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def _extract_numeric_values(payload: dict[str, Any]) -> list[float]:
    nums: list[float] = []
    for v in payload.values():
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            nums.append(float(v))
    return nums


def _matches_value(val: float, target: float, sigma: float = 0.0) -> bool:
    tol = max(0.05 * abs(target), 3.0 * sigma, 0.02)
    return abs(val - target) <= tol


class ClaimValidator:
    """Deterministic scientific & citation validator (FR-29). No LLM calls."""

    def validate(
        self,
        story: CosmicNarratorResponse,
        evidence: EvidenceStoreResponse,
        valid_marker_ids: set[str],
    ) -> tuple[CosmicNarratorResponse, bool]:
        ev_map: dict[str, EvidenceItem] = {e.evidence_id: e for e in evidence.items}
        reasons: list[str] = []

        if len(story.chapters) != 5:
            reasons.append(f"Expected 5 chapters, got {len(story.chapters)}")
            return story, False

        for idx, ch in enumerate(story.chapters):
            if ch.chapter_index != idx + 1 or ch.chapter_title != CHAPTER_TITLES[idx]:
                reasons.append(f"Invalid chapter {idx + 1} title/order: {ch.chapter_title!r}")

        if _BANNED_PHRASES_RE.search(story.patch_headline):
            reasons.append("Banned discovery phrase in patch_headline")

        new_chapters: list[ChapterBlock] = []
        accepted = 0
        rejected = 0

        for ch in story.chapters:
            if _BANNED_PHRASES_RE.search(ch.summary_prose):
                reasons.append(f"Banned discovery phrase in chapter {ch.chapter_index} prose")
                cleaned_prose = _BANNED_PHRASES_RE.sub(
                    "[redacted unverified claim]", ch.summary_prose
                )
            else:
                cleaned_prose = ch.summary_prose

            kept_claims: list[InteractiveStoryClaim] = []
            for claim in ch.claims:
                claim_errs = self._validate_claim(claim, ev_map, valid_marker_ids)
                if claim_errs:
                    rejected += 1
                    reasons.extend(claim_errs)
                else:
                    accepted += 1
                    # Rebuild citation URLs strictly from evidence store (never trust model-written URL)
                    fixed_cits = [
                        CitationItem(
                            evidence_id=c.evidence_id,
                            source_name=ev_map[c.evidence_id].source_name,
                            reference_id=ev_map[c.evidence_id].reference_id,
                            url=ev_map[c.evidence_id].url,
                            source_type=ev_map[c.evidence_id].source_type,
                        )
                        for c in claim.citations
                    ]
                    kept_claims.append(claim.model_copy(update={"citations": fixed_cits}))

            new_chapters.append(
                ch.model_copy(update={"summary_prose": cleaned_prose, "claims": kept_claims})
            )

        all_ok = len(reasons) == 0 and rejected == 0
        status: Literal["passed", "partial", "fallback_template"] = (
            "passed" if all_ok else ("partial" if accepted > 0 else "fallback_template")
        )
        updated = story.model_copy(
            update={
                "chapters": new_chapters,
                "validation": ValidationSummary(
                    status=status,
                    retries=story.validation.retries,
                    accepted_claims=accepted,
                    rejected_claims=rejected,
                    rejection_reasons=reasons,
                ),
            }
        )
        return updated, all_ok

    def _validate_claim(
        self,
        claim: InteractiveStoryClaim,
        ev_map: dict[str, EvidenceItem],
        valid_marker_ids: set[str],
    ) -> list[str]:
        errs: list[str] = []

        if _BANNED_PHRASES_RE.search(claim.statement):
            errs.append("Prohibited discovery claim in statement")

        if not claim.citations:
            errs.append("Claim has empty citations list")
            return errs

        # Check citation evidence IDs & server URL match
        cited_items: list[EvidenceItem] = []
        for cit in claim.citations:
            ev = ev_map.get(cit.evidence_id)
            if ev is None:
                errs.append(f"Unknown evidence_id: {cit.evidence_id}")
                continue
            if cit.url and cit.url != ev.url:
                errs.append(f"Fabricated or mismatched URL for {cit.evidence_id}")
            cited_items.append(ev)

        if not cited_items:
            return errs

        # Check visual_marker_id
        if claim.visual_marker_id is not None and claim.visual_marker_id not in valid_marker_ids:
            errs.append(f"Unknown visual_marker_id: {claim.visual_marker_id}")

        # Check quoted_values against cited evidence payloads
        for qv in claim.quoted_values:
            ev = ev_map.get(qv.evidence_id)
            if ev is None:
                errs.append(f"QuotedValue cites unknown evidence_id: {qv.evidence_id}")
                continue
            raw_val = ev.fact_payload.get(qv.field)
            if not isinstance(raw_val, (int, float)):
                errs.append(f"QuotedValue field {qv.field!r} missing from {qv.evidence_id}")
                continue
            sigma = float(ev.fact_payload.get("pm_total_err_arcsec_yr", 0.0) or 0.0)
            if not _matches_value(qv.value, float(raw_val), sigma=sigma):
                errs.append(f"QuotedValue {qv.field}={qv.value} contradicts evidence {raw_val}")

        # Check every standalone numeric literal in statement prose (ignoring marker IDs like obj_001)
        cleaned_stmt = re.sub(r"\bobj_\d+\b", " ", claim.statement)
        all_ev_nums: list[float] = []
        for ev in cited_items:
            all_ev_nums.extend(_extract_numeric_values(ev.fact_payload))
        for qv in claim.quoted_values:
            all_ev_nums.append(qv.value)

        for m in _NUMBER_RE.finditer(cleaned_stmt):
            num_val = float(m.group(0))
            if not any(_matches_value(num_val, ev_num) for ev_num in all_ev_nums):
                errs.append(f"Unverified numeric value {num_val} in statement")

        # Badge preconditions
        badge = claim.confidence_badge
        if badge == "Confirmed Catalog Object":
            has_cat = any(
                ev.evidence_type == "catalogue_entry"
                and (claim.visual_marker_id is None or ev.object_id == claim.visual_marker_id)
                for ev in cited_items
            )
            if not has_cat:
                errs.append(
                    "Confirmed Catalog Object badge requires linked catalogue_entry citation"
                )
        elif badge == "Candidate Moving Source":
            has_mov = any(bool(ev.fact_payload.get("is_candidate_moving")) for ev in cited_items)
            if not has_mov:
                errs.append(
                    "Candidate Moving Source badge requires is_candidate_moving=True evidence"
                )
        elif badge == "Candidate Variable":
            has_var = any(bool(ev.fact_payload.get("is_variable")) for ev in cited_items)
            if not has_var:
                errs.append("Candidate Variable badge requires is_variable=True evidence")
        elif badge == "Gaia Optical Dropout (IR-Only Candidate)":
            has_drop = any(
                ev.fact_payload.get("gaia_status") == "no_counterpart" for ev in cited_items
            )
            if not has_drop:
                errs.append(
                    "Gaia Optical Dropout badge requires gaia_status=no_counterpart evidence"
                )

        return errs
