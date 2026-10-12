"""FastAPI application factory."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, FastAPI, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from rhinvoice.api.errors import register_error_handlers
from rhinvoice.api.middleware import SecurityMiddleware
from rhinvoice.api.rate_limit import DemoLimits
from rhinvoice.api.routers import (
    articles,
    auth,
    backup,
    company,
    customers,
    demo,
    documents,
    dunning,
    e_invoices,
    imports,
    mail,
    numbering,
    onboarding,
    print_layout,
    recurring,
    reference,
    texts,
)
from rhinvoice.api.schemas import ApiModel
from rhinvoice.infrastructure.db.uow import database_is_reachable

if TYPE_CHECKING:
    from pathlib import Path

    from fastapi.routing import APIRoute

    from rhinvoice.api.container import Container

API_ROUTERS: tuple[APIRouter, ...] = (
    auth.router,
    backup.router,
    company.router,
    customers.router,
    articles.router,
    demo.router,
    numbering.router,
    onboarding.router,
    print_layout.router,
    documents.router,
    dunning.router,
    e_invoices.router,
    imports.router,
    mail.router,
    recurring.router,
    reference.router,
    texts.router,
)


class Health(ApiModel):
    status: str
    database: str


def operation_id(route: APIRoute) -> str:
    """Stable, readable operation ids such as ``auth_login`` for the generated client."""
    prefix = str(route.tags[0]) if route.tags else "default"
    return f"{prefix}_{route.name}"


def create_app(container: Container) -> FastAPI:
    app = FastAPI(
        title="Rhinvoice",
        version="0.4.0",
        summary="Self-hosted invoicing for CH, LI, DE and AT",
        docs_url="/api/docs",
        redoc_url=None,
        openapi_url="/api/openapi.json",
        generate_unique_id_function=operation_id,
    )
    app.state.container = container
    app.add_middleware(
        SecurityMiddleware,
        noindex=container.settings.demo,
        resetting=container.demo_reset.is_set,
        limits=DemoLimits.default() if container.settings.demo else None,
    )
    register_error_handlers(app)

    @app.get(
        "/api/health",
        tags=["system"],
        response_model=Health,
        responses={status.HTTP_503_SERVICE_UNAVAILABLE: {"model": Health}},
    )
    def health() -> JSONResponse:
        """Liveness and readiness: the app is up and the database answers."""
        database_ok = database_is_reachable(container.engine)
        body = Health(
            status="ok" if database_ok else "degraded",
            database="ok" if database_ok else "unreachable",
        )
        return JSONResponse(
            status_code=status.HTTP_200_OK if database_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
            content=body.model_dump(),
        )

    for router in API_ROUTERS:
        app.include_router(router)

    static_dir = container.settings.static_dir
    if static_dir is not None:
        _mount_frontend(app, static_dir)
    return app


def _mount_frontend(app: FastAPI, static_dir: Path) -> None:
    """Serve the built single page app; unknown paths fall back to index.html."""
    index = static_dir / "index.html"
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not Found")
        candidate = (static_dir / path).resolve()
        if path and candidate.is_file() and candidate.is_relative_to(static_dir.resolve()):
            return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
