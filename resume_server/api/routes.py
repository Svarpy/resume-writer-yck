"""REST endpoints. Thin: parse the request, call a service, return JSON."""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from resume_server.errors import UnauthorizedError
from resume_server.services import Services

router = APIRouter()


def services(request: Request) -> Services:
    return request.app.state.services


bearer = HTTPBearer(
    auto_error=False,  # a missing token is reported by our own 401 below
    description="A login token from `/auth/login`, or a personal access token (`rwt_...`) created in the desktop "
                "app under Profile > Access Tokens.",
)


def current_user(request: Request, credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer)) -> str:
    if credentials is None or not credentials.credentials:
        raise UnauthorizedError("Missing bearer token")
    return services(request).auth.authenticate(credentials.credentials)


class SignupBody(BaseModel):
    username: str
    password: str
    display_name: str = ""
    email: str = ""


class LoginBody(BaseModel):
    username: str
    password: str


class ProfileBody(BaseModel):
    display_name: Optional[str] = None
    email: Optional[str] = None


class PasswordBody(BaseModel):
    old_password: str
    new_password: str


class TokenBody(BaseModel):
    name: str = "token"


class DefaultFormatBody(BaseModel):
    format_id: str


class SettingsChange(BaseModel):
    format_id: str = ""
    changes: dict[str, Any]


class SettingsReset(BaseModel):
    format_id: str = ""
    keys: Optional[list[str]] = Field(default=None, description="Settings to reset; omit to reset everything")


# -- auth ------------------------------------------------------------------------------
@router.post("/auth/signup", status_code=201, tags=["Account"])
def signup(body: SignupBody, svc: Services = Depends(services)) -> dict[str, Any]:
    svc.auth.signup(body.username, body.password, body.display_name, body.email)
    token, profile = svc.auth.login(body.username, body.password)
    return {"token": token, "profile": profile}


@router.post("/auth/login", tags=["Account"])
def login(body: LoginBody, svc: Services = Depends(services)) -> dict[str, Any]:
    token, profile = svc.auth.login(body.username, body.password)
    return {"token": token, "profile": profile}


@router.post("/auth/password", status_code=204, tags=["Account"])
def change_password(body: PasswordBody, user: str = Depends(current_user), svc: Services = Depends(services)) -> Response:
    svc.auth.change_password(user, body.old_password, body.new_password)
    return Response(status_code=204)


@router.get("/profile", tags=["Account"])
def get_profile(user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    return svc.auth.profile(user)


@router.patch("/profile", tags=["Account"])
def update_profile(body: ProfileBody, user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    return svc.auth.update_profile(user, body.display_name, body.email)


@router.get("/tokens", tags=["Account"])
def list_tokens(user: str = Depends(current_user), svc: Services = Depends(services)) -> list[dict[str, Any]]:
    return svc.auth.list_access_tokens(user)


@router.post("/tokens", status_code=201, tags=["Account"])
def create_token(body: TokenBody, user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    return svc.auth.create_access_token(user, body.name)


@router.delete("/tokens/{token_id}", status_code=204, tags=["Account"])
def revoke_token(token_id: str, user: str = Depends(current_user), svc: Services = Depends(services)) -> Response:
    svc.auth.revoke_access_token(user, token_id)
    return Response(status_code=204)


# -- state (cheap cache validation) -----------------------------------------------------
@router.get("/state", tags=["Cache"])
def state(user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    """Revision numbers of everything a client may cache. One tiny call tells a client whether its cache is current."""
    default = svc.formats.default(user)
    full = svc.settings.get(user, default["id"]) if default else svc.settings.get(user, "")
    return {
        "default_format_id": default["id"] if default else "",
        "default_format_rev": default["rev"] if default else 0,
        "formats_rev": svc.formats.revision(user),
        "user_settings_rev": full["user_rev"],
        "format_settings_rev": full["format_rev"],
    }


# -- formats -----------------------------------------------------------------------------
@router.get("/formats", tags=["Formats"])
def list_formats(user: str = Depends(current_user), svc: Services = Depends(services)) -> list[dict[str, Any]]:
    return svc.formats.list(user)


@router.post("/formats", status_code=201, tags=["Formats"])
async def add_format(name: str = Form(...), file: UploadFile = File(...), user: str = Depends(current_user),
                     svc: Services = Depends(services)) -> dict[str, Any]:
    data = await file.read(svc.formats.config.max_upload_bytes + 1)
    return svc.formats.add(user, name, data)


@router.get("/formats/default", tags=["Formats"])
def get_default_format(user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    default = svc.formats.default(user)
    return default if default else {}


@router.put("/formats/default", tags=["Formats"])
def set_default_format(body: DefaultFormatBody, user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    return svc.formats.set_default(user, body.format_id)


@router.get("/formats/{format_id}", tags=["Formats"])
def get_format(format_id: str, user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    return svc.formats.get(user, format_id)


@router.get("/formats/{format_id}/sample", tags=["Formats"])
def get_sample(format_id: str, user: str = Depends(current_user), svc: Services = Depends(services)) -> Response:
    return Response(
        content=svc.formats.sample(user, format_id),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )


@router.delete("/formats/{format_id}", status_code=204, tags=["Formats"])
def delete_format(format_id: str, user: str = Depends(current_user), svc: Services = Depends(services)) -> Response:
    svc.formats.delete(user, format_id)
    return Response(status_code=204)


# -- settings ----------------------------------------------------------------------------
@router.get("/settings", tags=["Settings"])
def get_settings(format_id: str = "", user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    return svc.settings.get(user, format_id)


@router.patch("/settings", tags=["Settings"])
def update_settings(body: SettingsChange, user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    return svc.settings.update(user, body.format_id, body.changes)


@router.post("/settings/reset", tags=["Settings"])
def reset_settings(body: SettingsReset, user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    return svc.settings.reset(user, body.format_id, body.keys)


# -- backup ------------------------------------------------------------------------------
@router.get("/backup/info", include_in_schema=False)
def backup_info(user: str = Depends(current_user), svc: Services = Depends(services)) -> dict[str, Any]:
    """What a backup would contain (document counts per collection). Administrators only."""
    return svc.backup.info(user)


@router.get("/backup", include_in_schema=False)
def backup(user: str = Depends(current_user), svc: Services = Depends(services)) -> Response:
    """Download the database backup zip. Administrators only (a plain 404 Not Found for every other role)."""
    from resume_core.backup import backup_basename

    return Response(
        content=svc.backup.create(user), media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{backup_basename()}.zip"'},
    )
