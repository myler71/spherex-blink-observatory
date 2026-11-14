from app.narrator.validator import CHAPTER_TITLES
from app.schemas.narrative import (
    ChapterBlock,
    CitationItem,
    CosmicNarratorResponse,
    EvidenceItem,
    EvidenceStoreResponse,
    InteractiveStoryClaim,
    QuotedValue,
    ValidationSummary,
)
from app.schemas.observe import ObserveResponse


def _cite(ev: EvidenceItem) -> CitationItem:
    return CitationItem(
        evidence_id=ev.evidence_id,
        source_name=ev.source_name,
        reference_id=ev.reference_id,
        url=ev.url,
        source_type=ev.source_type,
    )


def build_template_narrative(
    observe: ObserveResponse,
    evidence: EvidenceStoreResponse,
) -> CosmicNarratorResponse:
    """Deterministic 5-chapter evidence-only narrative passing ClaimValidator with zero LLM calls."""
    ev_by_obj: dict[str, list[EvidenceItem]] = {}
    patch_ev = next(
        (e for e in evidence.items if e.evidence_type == "observation_metadata"),
        evidence.items[0],
    )
    paper_evs = [e for e in evidence.items if e.evidence_type == "paper"]

    for ev in evidence.items:
        if ev.object_id:
            ev_by_obj.setdefault(ev.object_id, []).append(ev)

    # Chapter 1: Where are we looking?
    ch1_claim = InteractiveStoryClaim(
        statement=(
            f"SPHEREx observed {observe.selection.selected_count} frames across "
            f"{observe.selection.visits_count} visits spanning {observe.selection.baseline_days} days "
            f"in {observe.constellation}."
        ),
        visual_marker_id=None,
        action_type="focus_object",
        confidence_badge="Probable Association",
        citations=[_cite(patch_ev)],
        quoted_values=[
            QuotedValue(
                evidence_id=patch_ev.evidence_id,
                field="baseline_days",
                value=float(observe.selection.baseline_days),
                unit="days",
            )
        ],
    )

    # Chapter 2: Who lives here?
    ch2_claims: list[InteractiveStoryClaim] = []
    for obj in observe.detected_objects[:3]:
        evs = ev_by_obj.get(obj.id, [])
        cat_evs = [e for e in evs if e.evidence_type == "catalogue_entry"]
        det_evs = [e for e in evs if e.evidence_type == "measurement"]
        if cat_evs and det_evs:
            ch2_claims.append(
                InteractiveStoryClaim(
                    statement=(
                        f"Source {obj.id} matches catalogued object {cat_evs[0].reference_id} "
                        f"at SNR {obj.snr}."
                    ),
                    visual_marker_id=obj.id,
                    action_type="focus_object",
                    confidence_badge="Confirmed Catalog Object",
                    citations=[_cite(det_evs[0]), _cite(cat_evs[0])],
                    quoted_values=[
                        QuotedValue(
                            evidence_id=det_evs[0].evidence_id,
                            field="snr",
                            value=float(obj.snr),
                        )
                    ],
                )
            )
        elif det_evs and obj.gaia_counterpart.status == "no_counterpart":
            ch2_claims.append(
                InteractiveStoryClaim(
                    statement=(
                        f"Source {obj.id} was detected at SNR {obj.snr} with no Gaia DR3 counterpart."
                    ),
                    visual_marker_id=obj.id,
                    action_type="focus_object",
                    confidence_badge="Gaia Optical Dropout (IR-Only Candidate)",
                    citations=[_cite(det_evs[0])],
                    quoted_values=[
                        QuotedValue(
                            evidence_id=det_evs[0].evidence_id,
                            field="snr",
                            value=float(obj.snr),
                        )
                    ],
                )
            )

    # Chapter 3: A universe in motion.
    ch3_claims: list[InteractiveStoryClaim] = []
    for obj in observe.detected_objects:
        if obj.is_candidate_moving and obj.motion.pm_total_arcsec_yr is not None:
            det_evs = [e for e in ev_by_obj.get(obj.id, []) if e.evidence_type == "measurement"]
            if det_evs:
                ch3_claims.append(
                    InteractiveStoryClaim(
                        statement=(
                            f"Candidate moving source {obj.id} has measured proper motion of "
                            f"{obj.motion.pm_total_arcsec_yr} arcsec/yr."
                        ),
                        visual_marker_id=obj.id,
                        action_type="show_motion_vector",
                        confidence_badge="Candidate Moving Source",
                        citations=[_cite(det_evs[0])],
                        quoted_values=[
                            QuotedValue(
                                evidence_id=det_evs[0].evidence_id,
                                field="pm_total_arcsec_yr",
                                value=float(obj.motion.pm_total_arcsec_yr),
                                unit="arcsec/yr",
                            )
                        ],
                    )
                )

    # Chapter 4: What does SPHEREx see?
    ch4_claims: list[InteractiveStoryClaim] = []
    for obj in observe.detected_objects:
        if obj.is_variable:
            det_evs = [e for e in ev_by_obj.get(obj.id, []) if e.evidence_type == "measurement"]
            if det_evs and "max_reduced_chi2" in det_evs[0].fact_payload:
                chi2 = float(det_evs[0].fact_payload["max_reduced_chi2"])
                ch4_claims.append(
                    InteractiveStoryClaim(
                        statement=(
                            f"Candidate variable source {obj.id} exhibits wavelength-matched "
                            f"variability with reduced chi-square {chi2}."
                        ),
                        visual_marker_id=obj.id,
                        action_type="open_light_curve",
                        confidence_badge="Candidate Variable",
                        citations=[_cite(det_evs[0])],
                        quoted_values=[
                            QuotedValue(
                                evidence_id=det_evs[0].evidence_id,
                                field="max_reduced_chi2",
                                value=chi2,
                            )
                        ],
                    )
                )

    # Chapter 5: The science behind this region.
    ch5_claims: list[InteractiveStoryClaim] = []
    for pev in paper_evs[:2]:
        ch5_claims.append(
            InteractiveStoryClaim(
                statement=f"Related literature: {pev.source_name} ({pev.reference_id}).",
                visual_marker_id=None,
                action_type="open_spectrum",
                confidence_badge="Probable Association",
                citations=[_cite(pev)],
                quoted_values=[],
            )
        )

    chapters = [
        ChapterBlock(
            chapter_index=1,
            chapter_title=CHAPTER_TITLES[0],
            summary_prose=(
                f"Field centered at RA {observe.query.ra:.4f} deg, Dec {observe.query.dec:.4f} deg "
                f"in {observe.constellation} ({observe.selection.selected_count} SPHEREx frames)."
            ),
            claims=[ch1_claim],
        ),
        ChapterBlock(
            chapter_index=2,
            chapter_title=CHAPTER_TITLES[1],
            summary_prose=(
                f"Extracted {len(observe.detected_objects)} sources and cross-matched against "
                "Gaia DR3, AllWISE, and SIMBAD."
            ),
            claims=ch2_claims,
        ),
        ChapterBlock(
            chapter_index=3,
            chapter_title=CHAPTER_TITLES[2],
            summary_prose=(
                f"Detected {sum(1 for o in observe.detected_objects if o.is_candidate_moving)} "
                "candidate moving source(s) via weighted multi-epoch astrometry."
            ),
            claims=ch3_claims,
        ),
        ChapterBlock(
            chapter_index=4,
            chapter_title=CHAPTER_TITLES[3],
            summary_prose=(
                f"Measured wavelength-matched light curves across {observe.selection.wavelength_bins_count} "
                "SPHEREx band bin(s)."
            ),
            claims=ch4_claims,
        ),
        ChapterBlock(
            chapter_index=5,
            chapter_title=CHAPTER_TITLES[4],
            summary_prose=(
                "Evidence-grounded summary assembled deterministically from retrieved catalogs and literature."
            ),
            claims=ch5_claims,
        ),
    ]

    return CosmicNarratorResponse(
        observation_id=observe.observation_id,
        patch_headline=f"{observe.constellation} SPHEREx Field Guide",
        constellation=observe.constellation,
        ra_deg=observe.query.ra,
        dec_deg=observe.query.dec,
        wiseview_verification_url=observe.overlays.wiseview_url,
        generator="template",
        chapters=chapters,
        validation=ValidationSummary(
            status="passed",
            retries=0,
            accepted_claims=sum(len(c.claims) for c in chapters),
            rejected_claims=0,
        ),
    )
