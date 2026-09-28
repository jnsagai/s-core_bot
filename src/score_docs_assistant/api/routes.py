"""Routes: `/health/live`, `/health/ready`, `/api/v1/capabilities`, and the shared error envelope
for 404/405/500 (contracts/http-api.md). Exactly these three routes exist in F001."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from score_docs_assistant import __version__
from score_docs_assistant.api.schemas import (
    AppInfo,
    CapabilitiesResponse,
    CapabilityStateOut,
    LimitsOut,
    LivenessResponse,
    ModelsOut,
    ReadinessResponse,
)
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.domain.readiness import CapabilityState
from score_docs_assistant.readiness import ReadinessService

APP_NAME = "S-CORE Docs Assistant — Community Project"

_STATUS_CODE_TO_ERROR_CODE = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED"}


def _request_id(request: Request) -> str:
    state = getattr(request, "state", None)
    return str(getattr(state, "request_id", "")) if state is not None else ""


def _capability_state_out(state: CapabilityState) -> CapabilityStateOut:
    return CapabilityStateOut(available=state.available, reasons=[r.value for r in state.reasons])


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        code = _STATUS_CODE_TO_ERROR_CODE.get(exc.status_code, "HTTP_ERROR")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": code,
                    "message": str(exc.detail),
                    "request_id": _request_id(request),
                    "retryable": False,
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "An internal error occurred.",
                    "request_id": _request_id(request),
                    "retryable": False,
                }
            },
        )


def register_routes(
    app: FastAPI, *, config: AppConfig, readiness_service: ReadinessService
) -> None:
    @app.get("/health/live", response_model=LivenessResponse)
    async def health_live() -> LivenessResponse:
        return LivenessResponse()

    @app.get("/health/ready", response_model=ReadinessResponse)
    async def health_ready() -> JSONResponse:
        readiness = readiness_service.get()
        body = ReadinessResponse(
            ready=readiness.ready,
            capabilities={
                capability.value: _capability_state_out(state)
                for capability, state in readiness.capabilities.items()
            },
        )
        status_code = 200 if readiness.ready else 503
        return JSONResponse(status_code=status_code, content=body.model_dump())

    @app.get("/api/v1/capabilities", response_model=CapabilitiesResponse)
    async def capabilities() -> CapabilitiesResponse:
        readiness = readiness_service.get()
        modes = {
            capability.value: _capability_state_out(state)
            for capability, state in readiness.capabilities.items()
        }
        return CapabilitiesResponse(
            app=AppInfo(name=APP_NAME, version=__version__),
            profile=config.profile,
            modes=modes,
            limits=LimitsOut(
                question_characters=config.limits.question_characters,
                history_characters=config.limits.history_characters,
                active_generations=config.limits.active_generations,
                queued_generations=config.limits.queued_generations,
                request_deadline_seconds=config.limits.request_deadline_seconds,
            ),
            models=ModelsOut(
                generation=config.runtime.generation_model,
                embedding=config.runtime.embedding_model,
            ),
        )
