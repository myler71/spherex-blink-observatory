from typing import Any, Literal

from pydantic import BaseModel, Field

ConfidenceBadge = Literal[
    "Confirmed Catalog Object",
    "Probable Association",
    "Gaia Optical Dropout (IR-Only Candidate)",
    "Candidate Moving Source",
    "Candidate Variable",
]

ActionType = Literal[
    "focus_object",
    "show_motion_vector",
    "open_light_curve",
    "open_spectrum",
]

SourceType = Literal[
    "NASA SPHEREx",
    "ESA Gaia DR3",
    "CSA CADC NEOSSat",
    "SIMBAD Catalog",
    "AllWISE Catalog",
    "Peer-Reviewed Paper",
    "NASA Web Resource",
]


class EvidenceItem(BaseModel):
    evidence_id: str
    evidence_type: Literal[
        "measurement", "catalogue_entry", "paper", "observation_metadata", "web_page"
    ]
    source_name: str
    source_type: SourceType
    reference_id: str
    url: str
    object_id: str | None = None
    fact_payload: dict[str, Any] = Field(default_factory=dict)


class EvidenceStoreResponse(BaseModel):
    observation_id: str
    pipeline_version: str
    items: list[EvidenceItem] = Field(default_factory=list)


class CitationItem(BaseModel):
    evidence_id: str
    source_name: str
    reference_id: str
    url: str = ""
    source_type: SourceType


class QuotedValue(BaseModel):
    evidence_id: str
    field: str
    value: float
    unit: str = ""


class InteractiveStoryClaim(BaseModel):
    statement: str
    visual_marker_id: str | None = None
    action_type: ActionType = "focus_object"
    confidence_badge: ConfidenceBadge
    citations: list[CitationItem] = Field(default_factory=list)
    quoted_values: list[QuotedValue] = Field(default_factory=list)


class ChapterBlock(BaseModel):
    chapter_index: int = Field(ge=1, le=5)
    chapter_title: str
    summary_prose: str
    claims: list[InteractiveStoryClaim] = Field(default_factory=list)


class ValidationSummary(BaseModel):
    status: Literal["passed", "partial", "fallback_template"]
    retries: int = 0
    accepted_claims: int = 0
    rejected_claims: int = 0
    rejection_reasons: list[str] = Field(default_factory=list)


class CosmicNarratorResponse(BaseModel):
    observation_id: str
    patch_headline: str
    constellation: str
    ra_deg: float
    dec_deg: float
    wiseview_verification_url: str
    generator: Literal["llm", "template", "fake"]
    chapters: list[ChapterBlock] = Field(min_length=5, max_length=5)
    validation: ValidationSummary
    node_timings_ms: dict[str, float] = Field(default_factory=dict)


class NarrativeJobResponse(BaseModel):
    observation_id: str
    status: Literal["pending", "ready", "failed"]
    narrative: CosmicNarratorResponse | None = None
    error: str | None = None


class AskRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)


class AskResponse(BaseModel):
    observation_id: str
    question: str
    answer: str
    in_scope: bool
    claims: list[InteractiveStoryClaim] = Field(default_factory=list)
    sources: list[CitationItem] = Field(default_factory=list)
    validation: ValidationSummary
