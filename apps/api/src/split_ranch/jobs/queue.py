"""Transactional job enqueueing.

Jobs are rows inserted through Procrastinate's own SQL function in the *same* transaction
as the business change, so they exist if and only if the change commits.
"""

from __future__ import annotations

import json
from typing import Any

import structlog
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

log = structlog.get_logger(__name__)

_DEFER_SQL = text(
    """
    SELECT app.procrastinate_defer_jobs_v1(
        ARRAY[ROW(:queue, :task, 0, :lock, :queueing_lock, CAST(:args AS jsonb), NULL)
              ::app.procrastinate_job_to_defer_v1]
    )
    """
)


def enqueue(
    session: Session,
    task_name: str,
    args: dict[str, Any],
    *,
    queue: str = "default",
    lock: str | None = None,
    queueing_lock: str | None = None,
) -> None:
    """Insert a Procrastinate job in the current transaction.

    A job with the same `queueing_lock` already waiting is treated as a duplicate.
    """
    # Procrastinate's functions/triggers use unqualified names: scope search_path locally.
    session.execute(text("SELECT set_config('search_path', 'app, public', true)"))
    try:
        with session.begin_nested():
            session.execute(
                _DEFER_SQL,
                {
                    "queue": queue,
                    "task": task_name,
                    "lock": lock,
                    "queueing_lock": queueing_lock,
                    "args": json.dumps(args, default=str),
                },
            )
    except IntegrityError:
        log.info("job_already_queued", task=task_name, queueing_lock=queueing_lock)
