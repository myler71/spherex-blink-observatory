import re

from app.archive.tavily import TavilyNasaSearch
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
    r"chi2|snr|gaia|wise|simbad|neossat|spherex|wavelength|spectrum|spectral|light\s*curve|"
    r"difference|patch|constellation|frame|visit|baseline|parallax|flag|zodi|dropout|band|sed)",
    re.IGNORECASE,
)

_SPECTRUM_RE = re.compile(
    r"(spectr(um|a|al)|wavelength|sed\b|spectral\s+energy|bandpass|bands?\b|infrared\s+spectrum)",
    re.IGNORECASE,
)

_NUMBER_RE = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![A-Za-z0-9_])")


def _collect_verified_numbers(evidence: EvidenceStoreResponse) -> list[float]:
    # Search excerpts, epochs, coordinates and identifiers are not scientific
    # measurements supporting arbitrary numeric statements.
    return [
        float(value)
        for item in evidence.items
        if item.evidence_type == "measurement"
        for field, value in item.fact_payload.items()
        if field not in {"ra", "dec", "ra_deg", "dec_deg", "mjd", "detector"}
        and isinstance(value, (int, float))
        and not isinstance(value, bool)
    ]


def _clean_text_for_number_check(text: str) -> str:
    s = re.sub(
        r"([-+]?\d+(?:\.\d+)?)\s*(µm|um|arcsec|mas|deg|days?|s|sec|yr|years?|mag|mJy|Jy|K)\b",
        r"\1 \2",
        text,
    )
    s = re.sub(r"https?://\S+", " ", s)
    s = re.sub(r"\b(ev|obs|obj|det|cal|ref|src|frame)_[a-zA-Z0-9_]+\b", " ", s)
    s = re.sub(r"\bev-[a-zA-Z0-9_-]+\b", " ", s)
    s = re.sub(r"\b2MASS\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bGaia\s*DR\d+\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bDR\d+\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bSPHEREx\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\b(AllWISE|WISE)\s*W\d\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bW[1-4]\b", " ", s)
    s = re.sub(r"\bSIMBAD\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNED\b", " ", s, flags=re.IGNORECASE)
    s = re.sub(r"\bNEOSSat\b", " ", s, flags=re.IGNORECASE)
    return s


def _validate_answer_content(
    raw_ans: str,
    observe: ObserveResponse,
    evidence: EvidenceStoreResponse,
    web_items: list[EvidenceItem] | None = None,
) -> tuple[bool, list[str]]:
    if not raw_ans.strip():
        return False, ["Empty answer"]
    if _BANNED_PHRASES_RE.search(raw_ans) or re.search(
        r"\bconfirms?\s+(?:the\s+)?discovery\b|\bnew\s+planet\b", raw_ans, re.I
    ):
        return False, ["Banned discovery phrase in answer"]
    if _INJECTION_RE.search(raw_ans):
        return False, ["Prompt injection artifact in answer"]

    verified_nums = _collect_verified_numbers(evidence)
    cleaned_text = _clean_text_for_number_check(raw_ans)

    unverified: list[str] = []
    for m in _NUMBER_RE.finditer(cleaned_text):
        val_str = m.group(0)
        try:
            val = float(val_str)
        except ValueError:
            continue
        if not any(
            abs(val - target) <= max(0.00005, abs(target) * 0.00001) for target in verified_nums
        ):
            unverified.append(val_str)

    if unverified:
        return False, [f"Unverified numeric value: {v}" for v in unverified]
    return True, []


def _build_grounded_spectrum_answer(
    observe: ObserveResponse,
    evidence: EvidenceStoreResponse,
    question: str,
    mode_label: str = "Deterministic pipeline analysis",
) -> str:
    obs_id = getattr(observe, "observation_id", "unknown")
    constellation = getattr(observe, "constellation", "the field")
    frames = getattr(observe, "frames", []) or []
    frame_wls = sorted(
        {round(f.central_wavelength_um, 4) for f in frames if f.central_wavelength_um is not None}
    )
    bandwidths = sorted({round(f.bandwidth_um, 4) for f in frames if f.bandwidth_um is not None})
    detectors = sorted({f.detector for f in frames if f.detector is not None})
    sel = getattr(observe, "selection", None)
    n_frames = len(frames) if frames else (sel.selected_count if sel else 0)
    n_visits = sel.visits_count if sel else 0
    n_bins = sel.wavelength_bins_count if sel else len(frame_wls)
    baseline_days = round(sel.baseline_days, 2) if sel else 0.0

    detected_objects = getattr(observe, "detected_objects", []) or []
    q_low = question.lower()
    matched_target = None
    for obj in detected_objects:
        if (obj.name.strip() and obj.name.lower() in q_low) or (
            obj.id.strip() and obj.id.lower() in q_low
        ):
            matched_target = obj
            break
        if any(m.identifier.strip() and m.identifier.lower() in q_low for m in obj.catalog_matches):
            matched_target = obj
            break
    if not matched_target and "barnard" in q_low:
        for obj in detected_objects:
            if "barnard" in obj.name.lower() or any(
                "barnard" in (m.identifier or "").lower() for m in obj.catalog_matches
            ):
                matched_target = obj
                break

    wls_str = ", ".join(f"{w} µm" for w in frame_wls) if frame_wls else "not recorded"
    bws_str = ", ".join(f"{b} µm" for b in bandwidths) if bandwidths else "not recorded"
    dets_str = (
        f"detectors [{', '.join(str(d) for d in detectors)}]" if detectors else "pipeline detectors"
    )

    lines: list[str] = [
        f"{mode_label} for SPHEREx observation {obs_id}:",
        "",
        "1. Observed Infrared Spectrum & Wavelength Availability:",
        f"This field in {constellation} contains {n_frames} SPHEREx frames across {n_visits} visits "
        f"({baseline_days} days baseline). Selection reports {n_bins} wavelength bins; frame-center wavelengths "
        f"are [{wls_str}] (bandwidths: {bws_str}; {dets_str}). Frame centers are not source-specific wavelengths.",
    ]
    lines.append(
        "Named catalog associations are positional candidates, not independently verified target identities."
    )

    if matched_target:
        sources = [matched_target]
    else:
        sources = detected_objects
        lines.append(
            "No named target association is established; the following are detected-source IDs."
        )
    for source in sources:
        lines.append(
            f"Source {source.id}: {len(source.light_curve)} source-specific photometry points."
        )
        for point in source.light_curve:
            lines.append(
                f"- {point.wavelength_um} µm: flux {point.flux} ± {point.flux_err} "
                f"(pipeline units; calibrated integrated-flux units are not recorded in this response); "
                f"SNR {point.snr}, MJD {point.mjd}, contaminated={point.contaminated}."
            )

    lines.extend(
        [
            "",
            "2. What the Evidence CAN Establish:",
            "The cached response provides sparse source-specific aperture photometry and per-point uncertainty "
            "where recorded. Consult the source's light curve rather than assigning a frame-center wavelength "
            "to every source. Field coordinates do not establish a named star's identity.",
            "",
            "3. What the Evidence CANNOT Establish (Measurement Limitations):",
            f"- Non-simultaneous epochs: The {n_frames} frames were acquired across different observation epochs "
            f"spanning a baseline of {baseline_days} days. Intrinsic source variability or proper motion between visits "
            "modulates observed flux ratios between bands, so these discrete points do not constitute a simultaneous spectral snapshot.",
            "- Incomplete spectral coverage: The patch provides sparse photometric bands, not a continuous spectrophotometric "
            "curve. Sparse samples cannot establish an absorption feature or a calibrated full spectrum.",
            "- No composition or temperature claims: Without continuous spectral coverage and multi-epoch calibrated "
            "spectral model fits, the evidence CANNOT establish atmospheric chemical composition, molecular absorption features "
            "(such as water ice or CO2), or definitive effective temperature.",
            "",
            "4. General Sources vs. Patch Measurements:",
            "Retrieved NASA links are unvalidated search-result background only. They do not validate patch measurements "
            "or support claim-level citations. No mission specification is inferred from search snippets.",
        ]
    )

    return "\n".join(lines)


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
        is_spectrum_q = bool(_SPECTRUM_RE.search(q_clean))
        ev_by_obj = {
            e.object_id: e
            for e in evidence.items
            if e.evidence_type == "measurement" and e.object_id is not None
        }

        # 3. Deterministic ranking/extremes (fastest, brightest, most variable)
        if not is_spectrum_q and any(
            k in q_low for k in ("fastest", "highest proper motion", "most motion")
        ):
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

        if not is_spectrum_q and any(k in q_low for k in ("brightest", "highest snr")):
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

        if not is_spectrum_q and "gaia" in q_low:
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

        if is_spectrum_q and getattr(self.llm_provider, "mode", "template") == "template":
            det_ans = _build_grounded_spectrum_answer(
                observe, evidence, q_clean, mode_label="Deterministic pipeline analysis"
            )
            return AskResponse(
                observation_id=observe.observation_id,
                question=q_clean,
                answer=det_ans,
                in_scope=True,
                claims=[],
                sources=[],
                validation=ValidationSummary(status="passed"),
            )

        web_items: list[EvidenceItem] = []
        # 4. External model path with NASA web search enrichment
        if getattr(self.llm_provider, "mode", "template") != "template":
            web_items = await TavilyNasaSearch(self.settings).search(f"SPHEREx {q_clean}")
            web_items = [
                item
                for item in web_items
                if not _INJECTION_RE.search(str(item.fact_payload))
                and not _BANNED_PHRASES_RE.search(str(item.fact_payload))
            ]
            frame_wls = sorted(
                {
                    round(f.central_wavelength_um, 4)
                    for f in getattr(observe, "frames", []) or []
                    if f.central_wavelength_um is not None
                }
            )
            obs_spectrum_ev = EvidenceItem(
                evidence_id="ev_spectrum_001",
                evidence_type="measurement",
                source_name="NASA SPHEREx Pipeline",
                source_type="NASA SPHEREx",
                reference_id=observe.observation_id,
                url="https://irsa.ipac.caltech.edu/Missions/spherex.html",
                object_id=None,
                fact_payload={
                    "wavelength_bins_count": getattr(
                        getattr(observe, "selection", None), "wavelength_bins_count", len(frame_wls)
                    ),
                    "wavelengths_um": frame_wls,
                    "selected_frames": getattr(
                        getattr(observe, "selection", None),
                        "selected_count",
                        len(getattr(observe, "frames", []) or []),
                    ),
                    "visits_count": getattr(getattr(observe, "selection", None), "visits_count", 1),
                    "baseline_days": round(
                        getattr(getattr(observe, "selection", None), "baseline_days", 0.0), 2
                    ),
                    "non_simultaneous": True,
                    "grounded_answer": _build_grounded_spectrum_answer(observe, evidence, q_clean)
                    if is_spectrum_q
                    else None,
                },
            )
            enriched_evidence = evidence.model_copy(
                update={"items": [obs_spectrum_ev] + evidence.items + web_items}
            )
            try:
                res = await self.llm_provider.answer_question(q_clean, enriched_evidence)
                raw_ans = str(res.get("answer") or "").strip()
            except Exception:
                raw_ans = ""

            if is_spectrum_q:
                draft = _build_grounded_spectrum_answer(observe, evidence, q_clean)
                valid = " ".join(raw_ans.split()) == " ".join(draft.split())
                _, errs = _validate_answer_content(raw_ans, observe, evidence, web_items)
                if not valid and not errs:
                    errs = [
                        "Spectrum prose was not the evidence-derived draft; using measured-data analysis"
                    ]
            else:
                valid, errs = _validate_answer_content(raw_ans, observe, evidence, web_items)
            if valid:
                return AskResponse(
                    observation_id=observe.observation_id,
                    question=q_clean,
                    answer=raw_ans,
                    in_scope=True,
                    claims=[],
                    sources=[_cite(item) for item in web_items],
                    validation=ValidationSummary(status="passed"),
                )

            if is_spectrum_q:
                fallback_ans = _build_grounded_spectrum_answer(
                    observe,
                    evidence,
                    q_clean,
                    mode_label="Grounded pipeline analysis (external model fallback)",
                )
                return AskResponse(
                    observation_id=observe.observation_id,
                    question=q_clean,
                    answer=fallback_ans,
                    in_scope=True,
                    claims=[],
                    sources=[_cite(item) for item in web_items],
                    validation=ValidationSummary(
                        status="fallback_template", rejection_reasons=errs
                    ),
                )
            else:
                n_sel = getattr(getattr(observe, "selection", None), "selected_count", 0)
                n_vis = getattr(getattr(observe, "selection", None), "visits_count", 0)
                n_det = len(getattr(observe, "detected_objects", []) or [])
                constell = getattr(observe, "constellation", "this region")
                return AskResponse(
                    observation_id=observe.observation_id,
                    question=q_clean,
                    answer=(
                        f"This patch in {constell} contains {n_sel} SPHEREx frames across {n_vis} visits and "
                        f"{n_det} detected sources."
                    ),
                    in_scope=True,
                    sources=[_cite(item) for item in web_items],
                    claims=[],
                    validation=ValidationSummary(
                        status="fallback_template", rejection_reasons=errs
                    ),
                )

        n_sel = getattr(getattr(observe, "selection", None), "selected_count", 0)
        n_vis = getattr(getattr(observe, "selection", None), "visits_count", 0)
        n_det = len(getattr(observe, "detected_objects", []) or [])
        constell = getattr(observe, "constellation", "this region")
        return AskResponse(
            observation_id=observe.observation_id,
            question=q_clean,
            answer=(
                f"This patch in {constell} contains {n_sel} SPHEREx frames across {n_vis} visits and "
                f"{n_det} detected sources."
            ),
            in_scope=True,
            sources=[_cite(item) for item in web_items],
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
