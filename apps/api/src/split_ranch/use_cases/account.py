"""Account deletion (GDPR erasure, Google Play requirement)."""

from __future__ import annotations

import structlog
from sqlalchemy import delete
from sqlalchemy.orm import Session

from split_ranch.core import clock
from split_ranch.core.actor import Actor
from split_ranch.core.errors import AppError, ServiceUnavailable
from split_ranch.core.logging import hash_user_id
from split_ranch.integrations.supabase_admin import AuthAdmin, AuthAdminError
from split_ranch.models import DEFAULT_NOTIFICATION_PREFS, PushToken
from split_ranch.use_cases.groups import leave_every_group
from split_ranch.use_cases.users import _user, ensure_user_cache

log = structlog.get_logger(__name__)


def delete_account(session: Session, actor: Actor, auth_admin: AuthAdmin | None) -> None:
    """Leave every group, anonymise the profile, drop push tokens, delete the auth user.

    Expenses, payments and history stay in the groups (the other members' records) and
    point to the anonymised row, shown as "Former member". Every DB change is flushed but
    committed only after Supabase deleted the auth user: if that call fails, nothing
    changed and the client can retry.
    """
    if auth_admin is None:
        raise ServiceUnavailable(
            "Account deletion is not configured", code="account_deletion_unavailable"
        )
    user = _user(session, actor.user_id)
    leave_every_group(session, actor.user_id)
    user.email = None
    user.display_name = None
    user.avatar_url = None
    user.notification_prefs = dict(DEFAULT_NOTIFICATION_PREFS)
    user.deleted_at = clock.now()
    session.execute(delete(PushToken).where(PushToken.user_id == actor.user_id))
    session.flush()

    try:
        auth_admin.delete_user(actor.user_id)
    except AuthAdminError as exc:
        session.rollback()
        log.warning("auth_user_delete_failed", user=hash_user_id(actor.user_id), error=str(exc))
        raise AppError(
            "Could not delete the sign-in account, try again",
            code="account_deletion_failed",
            status=502,
        ) from exc
    try:
        session.commit()
    except Exception:
        # The auth user is gone but the app data was not anonymised: needs a manual fix.
        log.error("account_delete_commit_failed", user=hash_user_id(actor.user_id))
        raise
    ensure_user_cache.forget(actor.user_id)
    log.info("account_deleted", user=hash_user_id(actor.user_id))
