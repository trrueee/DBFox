"""Fencing and invalidation for managed datasource connection resources.

Reusable database pools and SSH tunnels live longer than a request.  A
datasource update therefore needs more than replacing metadata: it must make
the former in-memory resource generation impossible to check out before its
old vault credentials are removed.
"""
from __future__ import annotations

from contextlib import contextmanager
import logging
import threading
from collections.abc import Callable, Generator

from engine.app.safe_errors import SafeLogOperation, log_unexpected_exception
from engine.connectivity.profile import ConnectionProfile, ManagedDatasourceResourceKey
from engine.errors import DataSourceConnectionError


logger = logging.getLogger("dbfox.connectivity.lifecycle")

PoolDisposer = Callable[[str], int]
TunnelCloser = Callable[[str], None]


def _default_pool_disposer(datasource_id: str) -> int:
    from engine.sql.pool_registry import get_pool_registry

    return get_pool_registry().dispose_datasource(datasource_id)


def _default_tunnel_closer(datasource_id: str) -> None:
    from engine.tunnel import close_active_tunnel

    close_active_tunnel(datasource_id)


class DatasourceResourceLifecycle:
    """Serialize connection checkout with committed datasource replacement.

    The lock is intentionally held only while a network connection is being
    acquired.  It prevents this race:

    1. an old request validates profile generation N;
    2. an update commits generation N+1 and disposes its pools/tunnels;
    3. the old request creates a fresh generation-N pool after disposal.

    Existing checked-out connections can finish, but their disposed pool can
    never lend them to another request.  New checkouts must use the committed
    generation.
    """

    def __init__(
        self,
        *,
        pool_disposer: PoolDisposer | None = None,
        tunnel_closer: TunnelCloser | None = None,
    ) -> None:
        self._pool_disposer = pool_disposer or _default_pool_disposer
        self._tunnel_closer = tunnel_closer or _default_tunnel_closer
        self._current: dict[str, ManagedDatasourceResourceKey] = {}
        self._retired: set[str] = set()
        self._lock = threading.RLock()

    @contextmanager
    def checkout(self, profile: ConnectionProfile) -> Generator[None, None, None]:
        """Fence one managed network connection checkout against replacement."""
        resource_key = profile.managed_resource_key
        if resource_key is None:
            yield
            return

        with self._lock:
            current = self._current.get(resource_key.datasource_id)
            if resource_key.datasource_id in self._retired:
                raise DataSourceConnectionError("Datasource connection configuration is no longer active.")
            # A process that has just started has no historical profile to
            # fence yet; the first checkout is therefore accepted without
            # registering it.  ``replace()`` is the committed transition that
            # publishes a current key.  This avoids treating independent
            # factory instances as a configuration update while still
            # rejecting every old profile after a real in-process update.
            if current is not None and current != resource_key:
                raise DataSourceConnectionError(
                    "Datasource connection configuration was replaced. Reload and retry."
                )
            yield

    def replace(
        self,
        previous: ConnectionProfile,
        current: ConnectionProfile,
    ) -> bool:
        """Publish a committed profile and remove every prior reusable resource.

        Call this only *after* the metadata transaction commits.  The new key
        is published before pool/tunnel disposal, so any concurrent stale
        checkout is rejected even if physical cleanup reports an operational
        error.  Callers must not delete replaced vault credentials if this
        method raises.
        """
        previous_key = previous.managed_resource_key
        current_key = current.managed_resource_key
        if previous_key is None or current_key is None:
            return False
        if previous_key.datasource_id != current_key.datasource_id:
            raise ValueError("Datasource resource replacement must keep the datasource id.")
        if previous_key == current_key:
            return False

        with self._lock:
            self._retired.discard(current_key.datasource_id)
            self._current[current_key.datasource_id] = current_key
            self._invalidate_resources_locked(current_key.datasource_id)
        return True

    def recover(self, current: ConnectionProfile) -> bool:
        """Publish a repaired profile when the persisted predecessor was invalid.

        Runtime privacy resets intentionally remove credential references and
        mark datasources as requiring credentials.  Such a datasource has no
        valid previous ``ConnectionProfile``, but saving newly enrolled
        credentials must still fence and dispose any process-local resources
        that may have survived before the repair.
        """
        current_key = current.managed_resource_key
        if current_key is None:
            return False

        with self._lock:
            self._retired.discard(current_key.datasource_id)
            self._current[current_key.datasource_id] = current_key
            self._invalidate_resources_locked(current_key.datasource_id)
        return True

    def retire(self, datasource_id: str) -> None:
        """Prevent any later checkout and dispose resources for a deleted datasource."""
        with self._lock:
            self._current.pop(datasource_id, None)
            self._retired.add(datasource_id)
            self._invalidate_resources_locked(datasource_id)

    def release_pools(self, datasource_id: str) -> int:
        """Dispose idle/checked-out pool ownership without retiring the profile."""
        with self._lock:
            try:
                return self._pool_disposer(datasource_id)
            except Exception as exc:
                log_unexpected_exception(
                    logger,
                    operation=SafeLogOperation.DATASOURCE_POOL_RELEASE,
                    exc=exc,
                )
                raise DataSourceConnectionError(
                    "Datasource connection pool could not be released."
                ) from None

    def clear(self) -> None:
        """Forget process-local fencing state after all application resources close."""
        with self._lock:
            self._current.clear()
            self._retired.clear()

    def _invalidate_resources_locked(self, datasource_id: str) -> None:
        """Remove pool/tunnel registry ownership while checkout is fenced."""
        try:
            self._pool_disposer(datasource_id)
            self._tunnel_closer(datasource_id)
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.DATASOURCE_POOL_RELEASE,
                exc=exc,
            )
            raise DataSourceConnectionError(
                "Datasource connection resources could not be invalidated."
            ) from None


_resource_lifecycle: DatasourceResourceLifecycle | None = None
_resource_lifecycle_lock = threading.Lock()


def get_datasource_resource_lifecycle() -> DatasourceResourceLifecycle:
    """Return the process-wide owner of managed pools and SSH tunnels."""
    global _resource_lifecycle
    if _resource_lifecycle is None:
        with _resource_lifecycle_lock:
            if _resource_lifecycle is None:
                _resource_lifecycle = DatasourceResourceLifecycle()
    return _resource_lifecycle


def close_all_managed_datasource_resources() -> None:
    """Dispose all managed connection resources during application shutdown."""
    lifecycle = get_datasource_resource_lifecycle()
    try:
        from engine.sql.pool_registry import get_pool_registry
        from engine.tunnel import close_all_tunnels

        get_pool_registry().dispose_all()
        close_all_tunnels()
    finally:
        lifecycle.clear()
