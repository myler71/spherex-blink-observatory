import asyncio
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import HTTPException, Request

from app.archive.ads import AdsAdapter
from app.archive.bundle import MultiAgencyCatalogBundle
from app.archive.irsa import IrsaArchiveAdapter
from app.config import Settings
from app.narrator.llm import LlmProvider, build_llm_provider
from app.science.pipeline import ObservePipeline
from app.store.cache import CacheStore
from app.store.db import DatabaseStore


class SlidingWindowRateLimiter:
    def __init__(self, window_sec: float = 60.0) -> None:
        self.window_sec = window_sec
        self._hits: dict[tuple[str, str], deque[float]] = {}

    def check(self, scope: str, client_ip: str, limit: int) -> None:
        now = time.monotonic()
        key = (scope, client_ip)
        dq = self._hits.setdefault(key, deque())
        cutoff = now - self.window_sec
        while dq and dq[0] < cutoff:
            dq.popleft()
        if len(dq) >= limit:
            retry_after = max(1, int(self.window_sec - (now - dq[0])))
            raise HTTPException(
                status_code=429,
                detail={
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": f"Rate limit exceeded for {scope} ({limit}/min).",
                    "details": {"retry_after_sec": retry_after},
                },
                headers={"Retry-After": str(retry_after)},
            )
        dq.append(now)


@dataclass
class AppContainer:
    settings: Settings
    cache: CacheStore
    db: DatabaseStore
    pipeline: ObservePipeline
    ads: AdsAdapter
    llm: LlmProvider
    rate_limiter: SlidingWindowRateLimiter = field(default_factory=SlidingWindowRateLimiter)
    inflight_observe: dict[str, asyncio.Future[Any]] = field(default_factory=dict)
    narrative_tasks: dict[str, asyncio.Task[Any]] = field(default_factory=dict)

    @classmethod
    def build(
        cls,
        settings: Settings,
        pipeline_override: ObservePipeline | None = None,
        llm_override: LlmProvider | None = None,
    ) -> "AppContainer":
        cache = CacheStore(settings)
        db = DatabaseStore(settings)
        if pipeline_override is not None:
            pipe = pipeline_override
        else:
            archive = IrsaArchiveAdapter(settings=settings, cache=cache)
            catalogs = MultiAgencyCatalogBundle(settings=settings)
            pipe = ObservePipeline(settings=settings, archive=archive, catalogs=catalogs)
        ads = AdsAdapter(settings=settings)
        llm = llm_override or build_llm_provider(settings)
        return cls(settings=settings, cache=cache, db=db, pipeline=pipe, ads=ads, llm=llm)


def get_container(request: Request) -> AppContainer:
    return request.app.state.container  # type: ignore[no-any-return]


def client_ip_from_request(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
