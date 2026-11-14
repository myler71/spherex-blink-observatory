import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.deps import AppContainer, client_ip_from_request, get_container
from app.narrator.ask import AskThisPatchService
from app.narrator.evidence import EvidenceBuilder
from app.narrator.graph import NarratorOrchestrator
from app.schemas.narrative import (
    AskRequest,
    AskResponse,
    CosmicNarratorResponse,
    EvidenceStoreResponse,
    NarrativeJobResponse,
)
from app.schemas.observe import ObserveResponse

router = APIRouter(tags=["narrative"])


def _load_obs_or_404(container: AppContainer, observation_id: str) -> ObserveResponse:
    cached = container.cache.get_json("observe", container.cache.versioned_key(observation_id))
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "NOT_FOUND", "message": f"Observation {observation_id} not found"},
        )
    return ObserveResponse.model_validate(cached)


def _narrative_cache_key(container: AppContainer, observation_id: str) -> str:
    s = container.settings
    ads_flag = "ads1" if s.nasa_ads_api_token.strip() else "ads0"
    model = s.llm_model or getattr(container.llm, "mode", s.llm_provider)
    return container.cache.versioned_key(
        f"{observation_id}:{s.llm_provider}:{model}:{s.prompt_version}:{ads_flag}"
    )


@router.get("/observe/{observation_id}/evidence", response_model=EvidenceStoreResponse)
async def get_observation_evidence(
    observation_id: str,
    container: AppContainer = Depends(get_container),
) -> EvidenceStoreResponse:
    obs = _load_obs_or_404(container, observation_id)
    ev_key = container.cache.versioned_key(f"ev:{observation_id}")
    cached_ev = container.cache.get_json("evidence", ev_key)
    if cached_ev is not None:
        return EvidenceStoreResponse.model_validate(cached_ev)

    docs = await container.db.search_documents(
        obs.constellation,
        object_identifiers=[o.name for o in obs.detected_objects[:5]],
        limit=5,
    )
    ev = EvidenceBuilder().build(obs, docs=docs)
    container.cache.set_json("evidence", ev_key, ev.model_dump(mode="json"))
    return ev


@router.get("/observe/{observation_id}/narrative", response_model=NarrativeJobResponse)
async def get_observation_narrative(
    request: Request,
    observation_id: str,
    container: AppContainer = Depends(get_container),
) -> NarrativeJobResponse:
    container.rate_limiter.check(
        "narrative",
        client_ip_from_request(request),
        container.settings.narrative_rate_limit_per_min,
    )
    obs = _load_obs_or_404(container, observation_id)
    n_key = _narrative_cache_key(container, observation_id)
    cached_nar = container.cache.get_json("narrative", n_key)
    if cached_nar is not None:
        return NarrativeJobResponse(
            observation_id=observation_id,
            status="ready",
            narrative=CosmicNarratorResponse.model_validate(cached_nar),
        )

    # Check if background task already running
    existing_task = container.narrative_tasks.get(n_key)
    if existing_task is not None:
        if not existing_task.done():
            return NarrativeJobResponse(observation_id=observation_id, status="pending")
        container.narrative_tasks.pop(n_key, None)
        if existing_task.exception() is not None:
            return NarrativeJobResponse(
                observation_id=observation_id,
                status="failed",
                error=str(existing_task.exception()),
            )
        story = existing_task.result()
        return NarrativeJobResponse(
            observation_id=observation_id,
            status="ready",
            narrative=story,
        )

    async def _run_job() -> CosmicNarratorResponse:
        ev = await get_observation_evidence(observation_id, container)
        orch = NarratorOrchestrator(
            settings=container.settings,
            docs_store=container.db,
            ads_adapter=container.ads,
            llm_provider=container.llm,
        )
        story = await orch.run(obs, ev)
        container.cache.set_json(
            "evidence",
            container.cache.versioned_key(f"ev:{observation_id}"),
            ev.model_dump(mode="json"),
        )
        ttl = 60 if story.validation.status == "fallback_template" else None
        container.cache.set_json("narrative", n_key, story.model_dump(mode="json"), ttl_seconds=ttl)
        return story

    # For zero-key template mode it finishes in <2 ms; for LLM modes run async and return pending
    if getattr(container.llm, "mode", "template") == "template":
        story = await _run_job()
        return NarrativeJobResponse(
            observation_id=observation_id,
            status="ready",
            narrative=story,
        )

    task = asyncio.create_task(_run_job())
    container.narrative_tasks[n_key] = task
    return NarrativeJobResponse(observation_id=observation_id, status="pending")


@router.post("/observe/{observation_id}/ask", response_model=AskResponse)
async def ask_this_patch(
    request: Request,
    observation_id: str,
    body: AskRequest,
    container: AppContainer = Depends(get_container),
) -> AskResponse:
    container.rate_limiter.check(
        "ask", client_ip_from_request(request), container.settings.ask_rate_limit_per_min
    )
    obs = _load_obs_or_404(container, observation_id)
    ev = await get_observation_evidence(observation_id, container)
    svc = AskThisPatchService(settings=container.settings, llm_provider=container.llm)
    return await svc.answer(obs, ev, body.question)
