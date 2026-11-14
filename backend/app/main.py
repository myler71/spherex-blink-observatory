import json
import logging
import time
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.api import benchmarks, candidates, health, narrative, observe, targets
from app.api.deps import AppContainer
from app.config import Settings, get_settings
from app.narrator.llm import LlmProvider
from app.schemas.common import ErrorResponse
from app.science.pipeline import ObservePipeline

logger = logging.getLogger("spherex.api")


def create_app(
    settings: Settings | None = None,
    pipeline_override: ObservePipeline | None = None,
    llm_override: LlmProvider | None = None,
) -> FastAPI:
    cfg = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.container = AppContainer.build(
            cfg,
            pipeline_override=pipeline_override,
            llm_override=llm_override,
        )
        try:
            yield
        finally:
            await app.state.container.db.close()

    app = FastAPI(
        title="SPHEREx Blink Observatory API",
        version=cfg.pipeline_version,
        lifespan=lifespan,
    )

    app.add_middleware(GZipMiddleware, minimum_size=1024)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_logging_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        t0 = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)
        response.headers["X-Request-ID"] = req_id
        logger.info(
            json.dumps(
                {
                    "request_id": req_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status": response.status_code,
                    "duration_ms": elapsed_ms,
                }
            )
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail
        if isinstance(detail, dict) and "code" in detail and "message" in detail:
            payload = ErrorResponse.create(
                str(detail["code"]),
                str(detail["message"]),
                detail.get("details"),
            )
        else:
            payload = ErrorResponse.create("HTTP_ERROR", str(detail))
        return JSONResponse(
            status_code=exc.status_code,
            content=payload.model_dump(),
            headers=exc.headers,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        payload = ErrorResponse.create(
            "VALIDATION_ERROR",
            "Request validation failed",
            exc.errors(),
        )
        return JSONResponse(status_code=422, content=payload.model_dump())

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception", exc_info=exc)
        payload = ErrorResponse.create("INTERNAL_ERROR", "Internal server error")
        return JSONResponse(status_code=500, content=payload.model_dump())

    prefix = "/api/v1"
    app.include_router(health.router, prefix=prefix)
    app.include_router(targets.router, prefix=prefix)
    app.include_router(observe.router, prefix=prefix)
    app.include_router(narrative.router, prefix=prefix)
    app.include_router(benchmarks.router, prefix=prefix)
    app.include_router(candidates.router, prefix=prefix)

    return app


app = create_app()
