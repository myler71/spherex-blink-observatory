from typing import Literal

from pydantic import BaseModel, Field

VoteLabel = Literal["Real Motion", "Variable Star", "Artifact"]


class CandidateCreate(BaseModel):
    observation_id: str = Field(min_length=3, max_length=128)
    object_id: str = Field(min_length=1, max_length=128)
    ra_deg: float = Field(ge=0.0, le=360.0, allow_inf_nan=False)
    dec_deg: float = Field(ge=-90.0, le=90.0, allow_inf_nan=False)
    reason: str = Field(min_length=3, max_length=500)


class CandidateVoteCreate(BaseModel):
    client_fingerprint: str = Field(min_length=4, max_length=128)
    vote_label: VoteLabel


class CandidateRecord(BaseModel):
    candidate_id: str
    observation_id: str
    object_id: str
    ra_deg: float
    dec_deg: float
    reason: str
    created_at: str
    vote_counts: dict[str, int] = Field(default_factory=dict)
    total_votes: int = 0
    consensus_label: str | None = None
    consensus_score: float = 0.0


class CandidatesListResponse(BaseModel):
    candidates: list[CandidateRecord]
