"""Shared test helpers: an in-process API server (mongomock) and clients that talk to it."""

from __future__ import annotations

import tempfile
from pathlib import Path

import mongomock
from fastapi.testclient import TestClient

from resume_client import ClientConfig, ResumeClient
from resume_server.api import create_app
from resume_server.config import ServerConfig

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "templates"
SERVER = ServerConfig(mongodb_uri="mongomock://", jwt_secret="y" * 40)


class CountingClient(TestClient):
    """TestClient that records which API calls were made."""

    def __init__(self, app) -> None:
        super().__init__(app)
        self.calls: list[str] = []
        self.down = False

    def request(self, method, url, *args, **kwargs):  # noqa: D102
        if self.down:
            import httpx

            raise httpx.ConnectError("server is down")
        self.calls.append(f"{method} {url}")
        return super().request(method, url, *args, **kwargs)

    def count(self, fragment: str) -> int:
        return sum(1 for call in self.calls if fragment in call)


class World:
    """One server + helpers to create clients that share (or do not share) a local data folder."""

    def __init__(self, ttl: float = 900.0) -> None:
        self.http = CountingClient(create_app(SERVER, mongomock.MongoClient()["client_tests"]))
        self.root = Path(tempfile.mkdtemp(prefix="rw-client-"))
        self.ttl = ttl
        self.now = [1000.0]

    def client(self, root: Path | None = None) -> ResumeClient:
        config = ClientConfig(api_url="http://testserver", cache_ttl=self.ttl, data_root=root or self.root)
        return ResumeClient(config, http=self.http)

    def login(self, username="alice", password="Passw0rd1", root: Path | None = None, signup=False) -> ResumeClient:
        client = self.client(root)
        (client.signup(username, password, display_name="Alice A") if signup else client.login(username, password))
        client.cache.clock = lambda: self.now[0]
        return client
