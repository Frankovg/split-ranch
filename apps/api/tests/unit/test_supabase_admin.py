"""SupabaseAuthAdmin: request shape and status handling."""

from __future__ import annotations

import uuid

import httpx
import pytest

from split_ranch.integrations.supabase_admin import AuthAdminError, SupabaseAuthAdmin


def _admin(status: int, seen: list[httpx.Request]) -> SupabaseAuthAdmin:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={})

    return SupabaseAuthAdmin(
        supabase_url="https://ref.supabase.co/",
        secret_key="sb_secret_test",
        transport=httpx.MockTransport(handler),
    )


def test_delete_sends_secret_key_on_apikey_header() -> None:
    seen: list[httpx.Request] = []
    uid = uuid.uuid4()
    _admin(200, seen).delete_user(uid)
    (request,) = seen
    assert request.method == "DELETE"
    assert str(request.url) == f"https://ref.supabase.co/auth/v1/admin/users/{uid}"
    assert request.headers["apikey"] == "sb_secret_test"


def test_already_deleted_is_success() -> None:
    _admin(404, []).delete_user(uuid.uuid4())


@pytest.mark.parametrize("status", [401, 500])
def test_other_statuses_fail(status: int) -> None:
    with pytest.raises(AuthAdminError):
        _admin(status, []).delete_user(uuid.uuid4())
