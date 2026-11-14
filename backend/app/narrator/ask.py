import re

from app.config import Settings
from app.narrator.llm import LlmProvider, build_llm_provider
from app.narrator.validator import _BANNED_PHRASES_RE
from app.schemas.narrative import (
    AskResponse,
    CitationItem,
    EvidenceItem,
    EvidenceStoreResponse,
    InteractiveStoryClaim,
    QuotedValue,
    ValidationSummary,
)
from app.schemas.observe import DetectedObject, ObserveResponse

_INJECTION_RE = re.compile(
    r"(ignore\s+(all\s+)?(previous|your)\s+instructions|"
    r"system\s+prompt|"
    r"disregard\s+rules|"
    r"say\s+planet\s*(nine|9|x))",
    re.IGNORECASE,
)

_ASTRO_DOMAIN_RE = re.compile(
    r"(object|star|source|motion|proper\s*motion|fastest|slowest|brightest|variable|"
    r"chi2|snr|gaia|wise|simbad|neossat|spherex|wavelength|spectrum|light\s*curve|"
    r"difference|patch|constellation|frame|visit|baseline|parallax|flag|zodi|dropout)",
    re.IGNORECASE,
)


def _cite(ev: EvidenceItem) -> CitationItem:
    return CitationItem(
        evidence_id=ev.evidence_id,
        source_name=ev.source_name,
        reference_id=ev.reference_id,
        url=ev.url,
        source_type=ev.source_type,
    )


class AskThisPatchService:
    """Evidence-scoped Q&A with deterministic ranking and prompt-injection defense (FR-32)."""

    def __init__(self, settings: Settings, llm_provider: LlmProvider | None = None) -> None:
        self.settings = settings
        self.llm_provider = llm_provider or build_llm_provider(settings)

    async def answer(
        self,
        observe: ObserveResponse,
        evidence: EvidenceStoreResponse,
        question: str,
    ) -> AskResponse:
        q_clean = question.strip()[: self.settings.ask_max_question_chars]

        # 1. Prompt-injection & banned-claim defense
        if _INJECTION_RE.search(q_clean) or _BANNED_PHRASES_RE.search(q_clean):
            return AskResponse(
                observation_id=observe.observation_id,
                question=q_clean,
                answer=(
                    "Request refused: I can only answer grounded scientific questions about "
                    "this patch's measured SPHEREx detections and verified catalog evidence."
                ),
                in_scope=False,
                claims=[],
                validation=ValidationSummary(status="passed"),
            )

        # 2. Scope check
        if not _ASTRO_DOMAIN_RE.search(q_clean):
            return AskResponse(
                observation_id=observe.observation_id,
                question=q_clean,
                answer="The answer is not in this patch's evidence.",
                in_scope=False,
                claims=[],
                validation=ValidationSummary(status="passed"),
            )

        q_low = q_clean.lower()
        ev_by_obj = {
            e.object_id: e
            for e in evidence.items
            if e.evidence_type == "measurement" and e.object_id is not None
        }

        # 3. Deterministic ranking/extremes (fastest, brightest, most variable)
        if any(k in q_low for k in ("fastest", "highest proper motion", "most motion")):
            movers = [
                o for o in observe.detected_objects if o.motion.pm_total_arcsec_yr is not None
            ]
            if not movers:
                return self._no_data_response(
                    observe,
                    q_clean,
                    "No multi-visit proper-motion measurements are available in this patch.",
                )
            top: DetectedObject = max(movers, key=lambda o: o.motion.pm_total_arcsec_yr or 0.0)
            ev = ev_by_obj.get(top.id)
            claims: list[InteractiveStoryClaim] = []
            if ev is not None:
                claims.append(
                    InteractiveStoryClaim(
                        statement=(
                            f"Object {top.id} ({top.name}) has the highest measured proper motion at "
                            f"{top.motion.pm_total_arcsec_yr} arcsec/yr."
                        ),
                        visual_marker_id=top.id,
                        action_type="show_motion_vector",
                        confidence_badge=(
                            "Candidate Moving Source"
                            if top.is_candidate_moving
                            else "Probable Association"
                        ),
                        citations=[_cite(ev)],
                        quoted_values=[
                            QuotedValue(
                                evidence_id=ev.evidence_id,
                                field="pm_total_arcsec_yr",
                                value=float(top.motion.pm_total_arcsec_yr or 0.0),
                                unit="arcsec/yr",
                            )
                        ],
                    )
                )
            return AskResponse(
                observation_id=observe.observation_id,
                question=q_clean,
                answer=(
                    f"The fastest-moving object in this patch is {top.id} ({top.name}) "
                    f"with measured proper motion {top.motion.pm_total_arcsec_yr} arcsec/yr."
                ),
                in_scope=True,
                claims=claims,
                validation=ValidationSummary(status="passed", accepted_claims=len(claims)),
            )

        if any(k in q_low for k in ("brightest", "highest snr")):
            if not observe.detected_objects:
                return self._no_data_response(
                    observe, q_clean, "No detected sources are present in this patch."
                )
            bright = max(observe.detected_objects, key=lambda o: o.snr)
            ev = ev_by_obj.get(bright.id)
            claims = []
            if ev is not None:
                claims.append(
                    InteractiveStoryClaim(
                        statement=f"Object {bright.id} ({bright.name}) has the highest SNR at {bright.snr}.",
                        visual_marker_id=bright.id,
                        action_type="focus_object",
                        confidence_badge="Probable Association",
                        citations=[_cite(ev)],
                        quoted_values=[
                            QuotedValue(
                                evidence_id=ev.evidence_id, field="snr", value=float(bright.snr)
                            )
                        ],
                    )
                )
            return AskResponse(
                observation_id=observe.observation_id,
                question=q_clean,
                answer=f"The highest-SNR source in this patch is {bright.id} ({bright.name}) at SNR {bright.snr}.",
                in_scope=True,
                claims=claims,
                validation=ValidationSummary(status="passed", accepted_claims=len(claims)),
            )

        if "gaia" in q_low:
            matched = [
                o
                for o in observe.detected_objects
                if o.gaia_counterpart.status == "has_counterpart"
            ]
            return AskResponse(
                observation_id=observe.observation_id,
                question=q_clean,
                answer=(
                    f"{len(matched)} of {len(observe.detected_objects)} detected objects have Gaia DR3 counterparts "
                    f"(Gaia query status: {observe.overlays.gaia_dr3_status.status})."
                ),
                in_scope=True,
                claims=[],
                validation=ValidationSummary(status="passed"),
            )

        # 4. General evidence-scoped answer (template or configured LLM)
        if getattr(self.llm_provider, "mode", "template") != "template":
            res = await self.llm_provider.answer_question(q_clean, evidence)
            raw_ans = str(res.get("answer") or "")
            if raw_ans and not _BANNED_PHRASES_RE.search(raw_ans):
                from app.narrator.validator import _NUMBER_RE, _matches_value

                ev_nums = [
                    float(v)
                    for e in evidence.items
                    for v in e.fact_payload.values()
                    if isinstance(v, (int, float)) and not isinstance(v, bool)
                ]
                stmt_no_ids = re.sub(r"\bobj_\d+\b", " ", raw_ans)
                unverified = [
                    m.group(0)
                    for m in _NUMBER_RE.finditer(stmt_no_ids)
                    if not any(_matches_value(float(m.group(0)), n) for n in ev_nums)
                ]
                if not unverified:
                    return AskResponse(
                        observation_id=observe.observation_id,
                        question=q_clean,
                        answer=raw_ans,
                        in_scope=True,
                        claims=[],
                        validation=ValidationSummary(status="passed"),
                    )

        return AskResponse(
            observation_id=observe.observation_id,
            question=q_clean,
            answer=(
                f"This patch in {observe.constellation} contains {observe.selection.selected_count} "
                f"SPHEREx frames across {observe.selection.visits_count} visits and "
                f"{len(observe.detected_objects)} detected sources."
            ),
            in_scope=True,
            claims=[],
            validation=ValidationSummary(status="passed"),
        )

    def _no_data_response(self, observe: ObserveResponse, q_clean: str, msg: str) -> AskResponse:
        return AskResponse(
            observation_id=observe.observation_id,
            question=q_clean,
            answer=msg,
            in_scope=True,
            claims=[],
            validation=ValidationSummary(status="passed"),
        )
