from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import AppContainer, get_container
from app.schemas.candidates import (
    CandidateCreate,
    CandidateRecord,
    CandidatesListResponse,
    CandidateVoteCreate,
)

router = APIRouter(tags=["candidates"])


@router.get("/candidates", response_model=CandidatesListResponse)
async def list_candidates(
    container: AppContainer = Depends(get_container),
) -> CandidatesListResponse:
    return CandidatesListResponse(candidates=await container.db.list_candidates())


@router.post("/candidates", response_model=CandidateRecord, status_code=201)
async def create_candidate(
    body: CandidateCreate,
    container: AppContainer = Depends(get_container),
) -> CandidateRecord:
    return await container.db.create_candidate(body)


@router.post("/candidates/{candidate_id}/votes", response_model=CandidateRecord)
async def vote_candidate(
    candidate_id: str,
    body: CandidateVoteCreate,
    container: AppContainer = Depends(get_container),
) -> CandidateRecord:
    try:
        rec = await container.db.vote_candidate(candidate_id, body)
    except PermissionError as exc:
        raise HTTPException(
            status_code=409,
            detail={"code": "DUPLICATE_VOTE", "message": str(exc)},
        ) from exc
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Candidate {candidate_id} not found"},
        )
    return rec
