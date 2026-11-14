from pathlib import Path

import pytest

from app.config import Settings
from app.narrator.evidence import EvidenceBuilder
from app.narrator.graph import NarratorOrchestrator
from app.narrator.llm import FakeLlmProvider, TemplateLlmProvider
from app.narrator.validator import CHAPTER_TITLES
from app.schemas.observe import ObserveQuery
from app.science.pipeline import ObservePipeline
from app.store.documents import LocalDocumentStore
from tests.integration.test_observe_pipeline import _MockArchive, _MockCatalogs
from tests.synthetic.fits_generator import SyntheticScenario, generate_synthetic_dataset


@pytest.mark.asyncio
async def test_template_narrator_without_llm_key_passes_validator(tmp_path: Path) -> None:
    settings = Settings(llm_provider="template", cache_dir=str(tmp_path / "cache"))
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            fov_deg=0.08,
            num_visits=2,
            exposures_per_visit=2,
            visit_gap_days=365.25,
            detectors=[2],
            n_static_stars=4,
            mover_pm_ra_arcsec_yr=6.0,
            mover_flux=70.0,
            noise_sigma=0.08,
        ),
        tmp_path / "syn",
    )
    pipe = ObservePipeline(settings, archive=_MockArchive(ds), catalogs=_MockCatalogs())
    obs = await pipe.run(ObserveQuery(ra=180.0, dec=20.0, fov=0.08))

    docs = LocalDocumentStore(tmp_path / "docs.db")
    orch = NarratorOrchestrator(
        settings=settings, docs_store=docs, llm_provider=TemplateLlmProvider()
    )
    evidence = EvidenceBuilder().build(obs, docs=[])
    story = await orch.run(obs, evidence)

    assert story.generator == "template"
    assert len(story.chapters) == 5
    assert [c.chapter_title for c in story.chapters] == CHAPTER_TITLES
    assert story.validation.status in ("passed", "fallback_template")
    assert story.validation.rejected_claims == 0


@pytest.mark.asyncio
async def test_langgraph_retry_recovers_from_invalid_draft_then_accepts_valid(
    tmp_path: Path,
) -> None:
    settings = Settings(llm_provider="fake", cache_dir=str(tmp_path / "cache"))
    ds = generate_synthetic_dataset(
        SyntheticScenario(
            num_visits=2, exposures_per_visit=1, detectors=[2], mover_pm_ra_arcsec_yr=6.0
        ),
        tmp_path / "syn",
    )
    pipe = ObservePipeline(settings, archive=_MockArchive(ds), catalogs=_MockCatalogs())
    obs = await pipe.run(ObserveQuery(ra=180.0, dec=20.0, fov=0.08))

    docs = LocalDocumentStore(tmp_path / "docs.db")
    evidence = EvidenceBuilder().build(obs, docs=[])
    det_ev = next(e for e in evidence.items if e.evidence_type == "measurement")

    bad_claim = {
        "statement": "Discovered Planet Nine moving 999.0 arcsec/yr!",
        "visual_marker_id": det_ev.object_id,
        "action_type": "show_motion_vector",
        "confidence_badge": "Candidate Moving Source",
        "citations": [
            {
                "evidence_id": "ev_fake",
                "source_name": "Fake",
                "reference_id": "Fake",
                "url": "",
                "source_type": "NASA SPHEREx",
            }
        ],
        "quoted_values": [],
    }
    good_claim = {
        "statement": f"Object {det_ev.object_id} detected at SNR {det_ev.fact_payload['snr']}.",
        "visual_marker_id": det_ev.object_id,
        "action_type": "focus_object",
        "confidence_badge": "Candidate Moving Source"
        if det_ev.fact_payload.get("is_candidate_moving")
        else "Probable Association",
        "citations": [
            {
                "evidence_id": det_ev.evidence_id,
                "source_name": det_ev.source_name,
                "reference_id": det_ev.reference_id,
                "url": det_ev.url,
                "source_type": det_ev.source_type,
            }
        ],
        "quoted_values": [
            {
                "evidence_id": det_ev.evidence_id,
                "field": "snr",
                "value": float(det_ev.fact_payload["snr"]),
                "unit": "",
            }
        ],
    }

    fake_llm = FakeLlmProvider(
        scripted_chapters=[
            [bad_claim],  # Attempt 0: fails ClaimValidator
            [good_claim],  # Attempt 1: passes after retry
        ]
    )
    orch = NarratorOrchestrator(settings=settings, docs_store=docs, llm_provider=fake_llm)
    story = await orch.run(obs, evidence)

    assert story.generator == "fake"
    assert story.validation.retries == 1
    assert story.validation.status == "passed"
    assert len(story.node_timings_ms) >= 4
