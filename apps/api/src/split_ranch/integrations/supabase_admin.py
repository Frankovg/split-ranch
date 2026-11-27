"""Supabase Auth admin client: only what account deletion needs.

The new secret keys (`sb_secret_...`) are not JWTs: they go in the `apikey` header. The
`Authorization` header carries the same key, as supabase-js does, which the gateway accepts
for secret keys (and which legacy `service_role` JWT keys need).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

import httpx


class AuthAdminError(Exception):
    """The Auth admin request failed (network error or unexpected status)."""


class AuthAdmin(Protocol):
    def delete_user(self, user_id: UUID) -> None: ...


class SupabaseAuthAdmin:
    def __init__(
        self,
        *,
        supabase_url: str,
        secret_key: str,
        timeout_seconds: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._base_url = supabase_url.rstrip("/")
        self._headers = {"apikey": secret_key, "Authorization": f"Bearer {secret_key}"}
        self._timeout = timeout_seconds
        self._transport = transport

    def delete_user(self, user_id: UUID) -> None:
        """Hard-deletes the auth user (sessions and identities go with it).

        A 404 means it is already gone, which is the outcome we want.
        """
        url = f"{self._base_url}/auth/v1/admin/users/{user_id}"
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as client:
                response = client.delete(url, headers=self._headers)
        except httpx.HTTPError as exc:
            raise AuthAdminError(f"Auth admin request failed: {exc!r}") from exc
        if response.status_code == 404 or response.is_success:
            return
        raise AuthAdminError(f"Auth admin returned status {response.status_code}")
