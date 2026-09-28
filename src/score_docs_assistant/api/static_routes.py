"""Serve the built frontend bundle (specs/006-local-web-ui/contracts/ui-contract.md §2).

Mounted after every `/api/v1/*` and `/health/*` router (research.md R4), so a path collision with
an API route is impossible by construction. `GET /` gets a strict Content-Security-Policy and
`cache-control: no-store` (FR-010a); hashed files under `/assets/` get normal caching. When the
build output does not exist, `GET /` answers honestly with 503 instead of a stack trace or an
empty 200.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.staticfiles import StaticFiles

_CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; "
    "base-uri 'none'; form-action 'self'"
)

DEFAULT_DIST_DIR = Path(__file__).resolve().parents[3] / "frontend" / "dist"


def register_static_routes(app: FastAPI, *, dist_dir: Path = DEFAULT_DIST_DIR) -> None:
    index_path = dist_dir / "index.html"
    assets_dir = dist_dir / "assets"

    if assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=assets_dir), name="frontend-assets")

    @app.get("/", response_model=None)
    async def frontend_index(request: Request) -> FileResponse | JSONResponse:
        if not index_path.is_file():
            return JSONResponse(
                status_code=503,
                content={
                    "error": {
                        "code": "FRONTEND_NOT_BUILT",
                        "message": (
                            "The frontend bundle has not been built "
                            "(run `npm run build` in frontend/)."
                        ),
                        "request_id": getattr(request.state, "request_id", ""),
                        "retryable": False,
                    }
                },
            )
        # cache-control: no-store is already added to every response by RequestContextMiddleware.
        return FileResponse(index_path, headers={"content-security-policy": _CSP})
