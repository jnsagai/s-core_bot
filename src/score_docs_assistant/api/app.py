"""`create_app(config, services)`: FastAPI wrapped by the guard and request-context middleware,
in that order from the inside out (plan.md Key Design 4/6)."""

from __future__ import annotations

from fastapi import FastAPI
from starlette.types import ASGIApp

from score_docs_assistant.api.guard import HostOriginGuard
from score_docs_assistant.api.logging import RequestContextMiddleware
from score_docs_assistant.api.routes import register_error_handlers, register_routes
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.readiness import ReadinessService


def create_fastapi_app(*, config: AppConfig, readiness_service: ReadinessService) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    register_error_handlers(app)
    register_routes(app, config=config, readiness_service=readiness_service)
    return app


def create_app(*, config: AppConfig, readiness_service: ReadinessService) -> ASGIApp:
    fastapi_app = create_fastapi_app(config=config, readiness_service=readiness_service)
    guarded: ASGIApp = HostOriginGuard(
        fastapi_app,
        allowed_hosts=config.server.allowed_hosts,
        allowed_origins=config.server.allowed_origins,
        bound_port=config.server.port,
    )
    return RequestContextMiddleware(guarded)
