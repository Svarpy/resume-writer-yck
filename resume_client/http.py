"""Thin HTTP wrapper: bearer token, error mapping, JSON/bytes helpers."""

from __future__ import annotations

from typing import Any, Callable, Optional

import httpx

from resume_client.errors import ApiError, AuthRequired, ServerUnavailable


class ApiHttp:
    def __init__(self, base_url: str, token: Callable[[], str], http: Optional[httpx.Client] = None) -> None:
        # ``http`` can be a FastAPI TestClient, which lets tests run the whole stack in-process.
        self._http = http or httpx.Client(base_url=base_url, timeout=15.0)
        self._token = token

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        headers = dict(kwargs.pop("headers", {}) or {})
        token = self._token()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            response = self._http.request(method, "/api/v1" + path, headers=headers, **kwargs)
        except httpx.HTTPError as exc:
            raise ServerUnavailable(f"Cannot reach the Resume Writer server: {exc}") from exc
        if response.status_code >= 400:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            if isinstance(detail, list):  # FastAPI request-validation errors
                detail = "; ".join(str(item.get("msg", item)) for item in detail)
            if response.status_code == 401:
                raise AuthRequired(str(detail))
            raise ApiError(str(detail), response.status_code)
        return response

    def json(self, method: str, path: str, **kwargs: Any) -> Any:
        response = self.request(method, path, **kwargs)
        return response.json() if response.content else None

    def bytes(self, path: str) -> bytes:
        return self.request("GET", path).content
