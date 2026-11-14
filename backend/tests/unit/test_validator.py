import pytest

from app.narrator.validator import CHAPTER_TITLES, ClaimValidator
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


def _sample_evidence() -> EvidenceStoreResponse:
    return EvidenceStoreResponse(
        observation_id="obs_test",
        pipeline_version="1.0.0",
        items=[
            EvidenceItem(
                evidence_id="ev_obs_1",
                evidence_type="observation_metadata",
                source_name="NASA SPHEREx",
                source_type="NASA SPHEREx",
                reference_id="2025W33_2C_0321_1",
                url="https://irsa.ipac.caltech.edu/ibe/data/spherex/sample.fits",
                fact_payload={"ra_deg": 269.452, "dec_deg": 4.693, "baseline_days": 402.76},
            ),
            EvidenceItem(
                evidence_id="ev_det_1",
                evidence_type="measurement",
                source_name="SPHEREx Pipeline",
                source_type="NASA SPHEREx",
                reference_id="obj_001",
                url="https://irsa.ipac.caltech.edu/Missions/spherex.html",
                object_id="obj_001",
                fact_payload={
                    "pm_total_arcsec_yr": 10.39,
                    "pm_total_err_arcsec_yr": 0.25,
                    "snr": 42.5,
                    "is_candidate_moving": True,
                    "is_variable": False,
                },
            ),
            EvidenceItem(
                evidence_id="ev_cat_1",
                evidence_type="catalogue_entry",
                source_name="SIMBAD",
                source_type="SIMBAD Catalog",
                reference_id="Barnard's Star",
                url="https://simbad.harvard.edu/simbad/sim-id?Ident=Barnard%27s+Star",
                object_id="obj_001",
                fact_payload={"identifier": "Barnard's Star", "otype": "PM*"},
            ),
            EvidenceItem(
                evidence_id="ev_det_2",
                evidence_type="measurement",
                source_name="SPHEREx Pipeline",
                source_type="NASA SPHEREx",
                reference_id="obj_002",
                url="https://irsa.ipac.caltech.edu/Missions/spherex.html",
                object_id="obj_002",
                fact_payload={"snr": 12.0, "is_candidate_moving": False, "is_variable": False},
            ),
        ],
    )


def _valid_story(claim: InteractiveStoryClaim | None = None) -> CosmicNarratorResponse:
    c = claim or InteractiveStoryClaim(
        statement="Source obj_001 exhibits high proper motion of 10.39 arcsec/yr at SNR 42.5.",
        visual_marker_id="obj_001",
        action_type="show_motion_vector",
        confidence_badge="Confirmed Catalog Object",
        citations=[
            CitationItem(
                evidence_id="ev_det_1",
                source_name="SPHEREx Pipeline",
                reference_id="obj_001",
                url="https://irsa.ipac.caltech.edu/Missions/spherex.html",
                source_type="NASA SPHEREx",
            ),
            CitationItem(
                evidence_id="ev_cat_1",
                source_name="SIMBAD",
                reference_id="Barnard's Star",
                url="https://simbad.harvard.edu/simbad/sim-id?Ident=Barnard%27s+Star",
                source_type="SIMBAD Catalog",
            ),
        ],
        quoted_values=[
            QuotedValue(
                evidence_id="ev_det_1", field="pm_total_arcsec_yr", value=10.39, unit="arcsec/yr"
            ),
            QuotedValue(evidence_id="ev_det_1", field="snr", value=42.5, unit=""),
        ],
    )
    chapters = [
        ChapterBlock(
            chapter_index=i + 1,
            chapter_title=CHAPTER_TITLES[i],
            summary_prose="Grounded observation summary.",
            claims=[c] if i == 2 else [],
        )
        for i in range(5)
    ]
    return CosmicNarratorResponse(
        observation_id="obs_test",
        patch_headline="Ophiuchus SPHEREx Time-Series Patch",
        constellation="Ophiuchus",
        ra_deg=269.452,
        dec_deg=4.693,
        wiseview_verification_url="http://byw.tools/wiseview#ra=269.452",
        generator="llm",
        chapters=chapters,
        validation=ValidationSummary(status="passed"),
    )


def test_validator_accepts_grounded_story() -> None:
    v = ClaimValidator()
    ev = _sample_evidence()
    res, ok = v.validate(_valid_story(), ev, valid_marker_ids={"obj_001", "obj_002"})
    assert ok is True
    assert res.validation.accepted_claims == 1
    assert res.validation.rejected_claims == 0


@pytest.mark.parametrize(
    "case_name,mutator",
    [
        (
            "01_invented_evidence_id",
            lambda c: c.citations[0].__setattr__("evidence_id", "ev_fake_999"),
        ),
        ("02_wrong_marker_id", lambda c: c.__setattr__("visual_marker_id", "obj_nonexistent")),
        ("03_altered_quoted_number", lambda c: c.quoted_values[0].__setattr__("value", 99.5)),
        (
            "04_unindexed_prose_number",
            lambda c: c.__setattr__("statement", "Source obj_001 moves at 88.88 arcsec/yr."),
        ),
        (
            "05_upgraded_badge_without_catalog",
            lambda c: (
                c.__setattr__("visual_marker_id", "obj_002"),
                c.__setattr__("citations", [c.citations[0]]),
                c.__setattr__("quoted_values", []),
                c.__setattr__("statement", "Source obj_002 is confirmed."),
            ),
        ),
        (
            "06_planet_nine_claim",
            lambda c: c.__setattr__("statement", "We discovered Planet Nine at 10.39 arcsec/yr."),
        ),
        (
            "07_planet_x_claim",
            lambda c: c.__setattr__(
                "statement", "This confirms Planet X motion of 10.39 arcsec/yr."
            ),
        ),
        (
            "08_ninth_planet_paraphrase",
            lambda c: c.__setattr__(
                "statement", "Evidence of the ninth planet moving 10.39 arcsec/yr."
            ),
        ),
        (
            "09_confirmed_discovery_phrase",
            lambda c: c.__setattr__(
                "statement", "This is a confirmed discovery at 10.39 arcsec/yr."
            ),
        ),
        (
            "10_first_detection_phrase",
            lambda c: c.__setattr__("statement", "Marks the first detection of 10.39 arcsec/yr."),
        ),
        ("11_missing_citations", lambda c: c.__setattr__("citations", [])),
        (
            "12_fabricated_url_in_citation",
            lambda c: c.citations[0].__setattr__("url", "https://evil.example.com/fake-doi"),
        ),
        (
            "13_moving_badge_on_non_mover",
            lambda c: (
                c.__setattr__("visual_marker_id", "obj_002"),
                c.__setattr__("confidence_badge", "Candidate Moving Source"),
                c.__setattr__(
                    "citations",
                    [
                        CitationItem(
                            evidence_id="ev_det_2",
                            source_name="SPHEREx Pipeline",
                            reference_id="obj_002",
                            url="https://irsa.ipac.caltech.edu/Missions/spherex.html",
                            source_type="NASA SPHEREx",
                        )
                    ],
                ),
                c.__setattr__("quoted_values", []),
                c.__setattr__("statement", "Object obj_002 is moving."),
            ),
        ),
        (
            "14_variable_badge_on_non_variable",
            lambda c: (
                c.__setattr__("visual_marker_id", "obj_002"),
                c.__setattr__("confidence_badge", "Candidate Variable"),
                c.__setattr__(
                    "citations",
                    [
                        CitationItem(
                            evidence_id="ev_det_2",
                            source_name="SPHEREx Pipeline",
                            reference_id="obj_002",
                            url="https://irsa.ipac.caltech.edu/Missions/spherex.html",
                            source_type="NASA SPHEREx",
                        )
                    ],
                ),
                c.__setattr__("quoted_values", []),
                c.__setattr__("statement", "Object obj_002 is variable."),
            ),
        ),
    ],
)
def test_validator_rejects_14_adversarial_drafts(case_name: str, mutator) -> None:
    v = ClaimValidator()
    ev = _sample_evidence()
    story = _valid_story()
    claim = story.chapters[2].claims[0]
    mutator(claim)
    cleaned, ok = v.validate(story, ev, valid_marker_ids={"obj_001", "obj_002"})
    assert ok is False, f"Expected adversarial draft {case_name} to fail"
    assert cleaned.validation.rejected_claims >= 1
    assert len(cleaned.chapters[2].claims) == 0
