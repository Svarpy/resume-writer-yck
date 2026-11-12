"""FastAPI application factory."""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pymongo.database import Database

from resume_core.constants import APP_VERSION
from resume_server.config import ServerConfig, load_config
from resume_server.db import connect
from resume_server.errors import ServiceError
from resume_server.services import build_services
from resume_server.system import public_system_info, register_app_version


def create_app(config: Optional[ServerConfig] = None, db: Optional[Database] = None) -> FastAPI:
    """Build the API. ``db`` lets tests inject an in-memory database instead of connecting to MongoDB."""
    config = config or load_config()
    db = db if db is not None else connect(config)
    app = FastAPI(
        title="Resume Writer API", version=APP_VERSION,
        description=(
            "REST API of Resume Writer (accounts, resume formats, settings). Interactive documentation: "
            "click **Authorize** and paste an access token (desktop app: Profile > Access Tokens) or a login "
            "token from `POST /api/v1/auth/login`, then try any endpoint. Resumes themselves are generated on "
            "your own computer by the desktop app or the MCP server, never by this server."
        ),
        openapi_tags=[
            {"name": "Account", "description": "Sign up, sign in, profile, password and access tokens."},
            {"name": "Formats", "description": "Upload resume templates (formats), replace or download them, choose the default."},
            {"name": "Settings", "description": "Per-user and per-format settings, validated and versioned."},
            {"name": "System", "description": "Health and version information (no sign-in needed)."},
            {"name": "Cache", "description": "Revision numbers clients use to validate their local cache."},
        ],
    )
    app.state.config = config
    app.state.services = build_services(config, db)
    register_app_version(db)  # keeps the `system` collection's version list current
    app.state.db = db

    @app.exception_handler(ServiceError)
    async def service_error(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    @app.get("/api/v1/system", tags=["System"])
    def system_info() -> dict:
        """Application system data (current/latest version and the version history). Public."""
        return public_system_info(app.state.db)

    @app.get("/health", tags=["System"])
    def health() -> dict[str, str]:
        return {"status": "ok", "version": APP_VERSION}

    from resume_server.api.routes import router

    app.include_router(router, prefix="/api/v1")
    return app
