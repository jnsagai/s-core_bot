"""`create_app(config, services)`: FastAPI wrapped by the guard and request-context middleware,
in that order from the inside out (plan.md Key Design 4/6)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from starlette.types import ASGIApp

from score_docs_assistant.answers.service import AnswerService
from score_docs_assistant.api.chat_routes import register_chat_routes
from score_docs_assistant.api.compare_routes import register_compare_routes
from score_docs_assistant.api.guard import HostOriginGuard, default_static_get_paths
from score_docs_assistant.api.logging import RequestContextMiddleware
from score_docs_assistant.api.routes import register_error_handlers, register_routes
from score_docs_assistant.api.search_routes import register_search_routes
from score_docs_assistant.api.static_routes import DEFAULT_DIST_DIR, register_static_routes
from score_docs_assistant.comparison.service import ComparisonService
from score_docs_assistant.config.schema import AppConfig
from score_docs_assistant.readiness import ReadinessService
from score_docs_assistant.retrieval.service import SearchService


def create_fastapi_app(
    *,
    config: AppConfig,
    readiness_service: ReadinessService,
    search_service: SearchService | None = None,
    answer_service: AnswerService | None = None,
    frontend_dist_dir: Path = DEFAULT_DIST_DIR,
) -> FastAPI:
    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
    register_error_handlers(app)
    register_routes(app, config=config, readiness_service=readiness_service)
    search = search_service or SearchService(config=config, provider=None)
    register_search_routes(app, search)
    answers = answer_service or AnswerService(config=config, search=search, provider=None)
    register_chat_routes(app, answers)
    register_compare_routes(
        app, ComparisonService(config=config, search=search, answers=answers), search
    )
    register_static_routes(app, dist_dir=frontend_dist_dir)
    return app


def create_app(
    *,
    config: AppConfig,
    readiness_service: ReadinessService,
    search_service: SearchService | None = None,
    answer_service: AnswerService | None = None,
    frontend_dist_dir: Path = DEFAULT_DIST_DIR,
) -> ASGIApp:
    fastapi_app = create_fastapi_app(
        config=config,
        readiness_service=readiness_service,
        search_service=search_service,
        answer_service=answer_service,
        frontend_dist_dir=frontend_dist_dir,
    )
    guarded: ASGIApp = HostOriginGuard(
        fastapi_app,
        allowed_hosts=config.server.allowed_hosts,
        allowed_origins=config.server.allowed_origins,
        bound_port=config.server.port,
        static_get_paths=default_static_get_paths,
    )
    return RequestContextMiddleware(guarded)
