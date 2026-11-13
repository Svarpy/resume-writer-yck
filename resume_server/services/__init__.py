"""Application services: all the business rules, independent of HTTP."""

from __future__ import annotations

from dataclasses import dataclass

from pymongo.database import Database

from resume_server.config import ServerConfig
from resume_server.db import FormatRepo, SettingsRepo, TokenRepo, UserRepo, ensure_indexes
from resume_server.services.auth import AuthService
from resume_server.services.backup import BackupService
from resume_server.services.formats import FormatService
from resume_server.services.settings import SettingsService


@dataclass
class Services:
    auth: AuthService
    formats: FormatService
    settings: SettingsService
    backup: BackupService


def build_services(config: ServerConfig, db: Database) -> Services:
    ensure_indexes(db)
    users, tokens, formats, settings = UserRepo(db), TokenRepo(db), FormatRepo(db), SettingsRepo(db)
    settings_service = SettingsService(settings, formats, users)
    users.backfill_roles()
    format_service = FormatService(formats, users, config)
    auth_service = AuthService(users, tokens, settings_service, config)
    return Services(auth=auth_service, formats=format_service, settings=settings_service,
                    backup=BackupService(db, users))
