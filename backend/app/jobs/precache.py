import asyncio
from datetime import UTC, datetime

from app.archive.bundle import MultiAgencyCatalogBundle
from app.archive.irsa import IrsaArchiveAdapter
from app.config import Settings, get_settings
from app.narrator.evidence import EvidenceBuilder
from app.narrator.graph import NarratorOrchestrator
from app.schemas.observe import ObserveQuery
from app.science.pipeline import ObservePipeline, compute_observation_id
from app.science.targets import list_target_presets
from app.store.cache import CacheStore
from app.store.db import DatabaseStore


async def run_precache(
    settings: Settings,
    cache: CacheStore,
    db: DatabaseStore,
    pipeline: ObservePipeline | None = None,
) -> dict[str, str]:
    pipe = pipeline or ObservePipeline(
        settings=settings,
        archive=IrsaArchiveAdapter(settings=settings, cache=cache),
        catalogs=MultiAgencyCatalogBundle(settings=settings),
    )
    orch = NarratorOrchestrator(settings=settings, docs_store=db)
    status_map: dict[str, str] = {}

    for preset in list_target_presets():
        q = ObserveQuery(
            ra=preset.ra_deg,
            dec=preset.dec_deg,
            fov=preset.default_fov_deg,
            mode=preset.recommended_mode,
            target=preset.id,
        )
        obs_id = compute_observation_id(q, settings.pipeline_version)
        try:
            obs = await pipe.run(q)
            stamped = obs.model_copy(update={"cached_at": datetime.now(UTC).isoformat()})
            cache.set_json("observe", cache.versioned_key(obs_id), stamped.model_dump(mode="json"))
            docs = await db.search_documents(preset.name, object_identifiers=[preset.id], limit=5)
            ev = EvidenceBuilder().build(stamped, docs=docs)
            cache.set_json(
                "evidence", cache.versioned_key(f"ev:{obs_id}"), ev.model_dump(mode="json")
            )
            story = await orch.run(stamped, ev)
            model = settings.llm_model or settings.llm_provider
            ads_flag = "ads1" if settings.nasa_ads_api_token.strip() else "ads0"
            n_key = cache.versioned_key(
                f"{obs_id}:{settings.llm_provider}:{model}:{settings.prompt_version}:{ads_flag}"
            )
            cache.set_json("narrative", n_key, story.model_dump(mode="json"))
            status_map[preset.id] = "cached"
        except Exception as exc:
            status_map[preset.id] = f"error: {str(exc)[:120]}"
    return status_map


def main() -> None:
    settings = get_settings()
    cache = CacheStore(settings)
    db = DatabaseStore(settings)
    res = asyncio.run(run_precache(settings, cache, db))
    print("Precache results:", res)


if __name__ == "__main__":
    main()
