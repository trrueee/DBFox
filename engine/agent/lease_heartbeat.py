"""One renewal loop for Agent and explicit Workbench Session owners."""
from __future__ import annotations

from collections.abc import Callable
import logging
from threading import Event

from sqlalchemy.orm import Session

from engine.agent.repositories.session import SessionRepository
from engine.agent.run import SessionLeaseConflict
from engine.agent.session import SessionLease

logger = logging.getLogger("dbfox.agent.lease")


def heartbeat_session_lease(
    *, session_factory: Callable[[], Session], lease: SessionLease,
    ttl_seconds: int, stop: Event, lease_lost: Event | None = None,
) -> None:
    """Renew this exact owner/token until shutdown or authoritative lease loss."""
    interval = max(0.1, ttl_seconds / 3)
    delay = interval
    failures = 0
    while not stop.wait(delay):
        try:
            with session_factory() as db:
                SessionRepository(db).heartbeat(lease=lease, ttl_seconds=ttl_seconds)
                db.commit()
            failures = 0
            delay = interval
        except SessionLeaseConflict:
            if lease_lost is not None:
                lease_lost.set()
            logger.warning("Session lease was lost session_id=%s owner=%s token=%s",
                           lease.session_id, lease.owner, lease.token)
            return
        except Exception:
            failures += 1
            delay = min(interval, float(2 ** min(failures - 1, 5)))
            logger.exception("Session heartbeat failed; retrying session_id=%s attempt=%s",
                             lease.session_id, failures)
