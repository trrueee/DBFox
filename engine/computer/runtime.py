"""Host lifetime, one UI/COM worker, cancellation fences and private captures."""
from __future__ import annotations

from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import logging
from pathlib import Path
from threading import Event, Lock, Thread
import time
from typing import TypeVar
from uuid import uuid4

from sqlalchemy.orm import Session

from engine.agent.resource_refs import SessionResourceDiscoveryContext
from engine.computer.browser import OwnedBrowser, edge_executable
from engine.computer.contracts import (
    ActInput, BrowserState, ComputerError, ComputerGrant, GrantStatus, MAX_IMAGE_BYTES, Observation,
    OBSERVATION_AGE_MS, ShareInput, TARGET_KIND, TargetIdentity, TargetOption,
)
from engine.computer.native import NativeDesktop
from engine.computer.store import ComputerGrantStore, now_ms
from engine.resource import ResourceScopeRef

T = TypeVar("T")


@dataclass(frozen=True)
class _TargetLease:
    session_id: str
    cancelled: Event


class ComputerRuntime:
    def __init__(self, sessions: Callable[[], Session], directory: Path, *,
                 native: NativeDesktop | None = None, browser: OwnedBrowser | None = None) -> None:
        self.store = ComputerGrantStore(sessions)
        self.directory = directory
        self.captures = directory / "captures"
        self.captures.mkdir(parents=True, exist_ok=True)
        self.native = native or NativeDesktop()
        self.browser = browser or OwnedBrowser(directory / "browsers")
        self._worker = ThreadPoolExecutor(max_workers=1, thread_name_prefix="computer-uia")
        self._lock = Lock()
        self._targets: dict[str, _TargetLease] = {}
        self._invocations: dict[str, tuple[Event, str]] = {}
        self._inventory: dict[str, tuple[TargetIdentity, float]] = {}
        self._latest: dict[str, str] = {}
        self._closed = Event()
        self._monitor = Thread(target=self._supervise, name="computer-lifetime", daemon=True)
        self._monitor.start()
        self._trim_captures()

    def _call(self, function: Callable[[], T], *, timeout: float = 20, cancel: Event | None = None) -> T:
        if self._closed.is_set():
            raise ComputerError("COMPUTER_UNAVAILABLE", "电脑运行时已停止。", 503)
        future = self._worker.submit(function)
        try:
            return future.result(timeout=timeout)
        except FutureTimeout:
            if cancel is not None:
                cancel.set()
            future.cancel()
            raise ComputerError("COMPUTER_TIMEOUT", "目标没有及时响应。操作结果可能未知，请停止并重新观察，不要直接重试。") from None
        except ComputerError:
            raise
        except Exception as exc:
            # Diagnose frozen-driver/import failures without logging window
            # titles, page contents, action text or arbitrary exception messages.
            frame = exc.__traceback__
            while frame is not None and frame.tb_next is not None:
                frame = frame.tb_next
            logging.getLogger("dbfox.computer").warning(
                "Computer driver failed type=%s source=%s line=%s",
                type(exc).__name__,
                Path(frame.tb_frame.f_code.co_filename).name if frame is not None else "unknown",
                frame.tb_lineno if frame is not None else 0,
            )
            raise ComputerError("COMPUTER_DRIVER_FAILED", "目标暂时无法访问。请检查窗口或浏览器，再重新观察；不会自动重试操作。") from exc

    def inventory(self) -> tuple[TargetOption, ...]:
        targets = list(self._call(self.native.targets, timeout=10))
        executable = edge_executable()
        if executable is not None:
            targets.insert(0, TargetIdentity(kind="browser", title="受控浏览器 · Microsoft Edge",
                                            executable=str(executable), browser_channel="msedge"))
        with self._lock:
            self._inventory = {key: value for key, value in self._inventory.items() if value[1] > time.monotonic()}
            result = []
            for target in targets:
                token = "target_" + uuid4().hex
                self._inventory[token] = (target, time.monotonic() + 60)
                result.append(TargetOption(inventory_id=token, target=target))
        return tuple(result)

    def share(self, session_id: str, input: ShareInput) -> ComputerGrant:
        with self._lock:
            candidate = self._inventory.pop(input.inventory_id, None)
        if candidate is None or candidate[1] < time.monotonic():
            raise ComputerError("COMPUTER_INVENTORY_EXPIRED", "窗口列表已过期，请刷新并重新选择。")
        target = candidate[0]
        previous = tuple(grant for grant in self.store.list(session_id) if grant.target.kind == target.kind)
        grant = self.store.create(session_id, target, permission=input.permission, duration_minutes=input.duration_minutes,
                                  replace_existing=input.replace_existing)
        for old in previous:
            if old.status in (GrantStatus.ACTIVE, GrantStatus.PAUSED):
                self._interrupt(old.id)
        event = Event()
        with self._lock:
            self._targets[grant.id] = _TargetLease(session_id, event)

        def start() -> None:
            check = self._check(session_id, self.ref(grant), event)
            check()
            if target.kind == "browser":
                def launch(spawn: Callable[[], None]) -> None:
                    # Explicit user sharing authorizes creation of the dedicated
                    # process, including an observe-only browser. It grants no
                    # model navigation or page input.
                    with self.store.sessions() as db:
                        from engine.agent.repositories.write_transaction import begin_agent_write
                        begin_agent_write(db)
                        self.store.require(session_id, self.ref(grant))
                        check()
                        spawn()
                        db.commit()
                self.browser.start(grant, check, launch)
            else:
                self.native.capture(grant, remember=False)
        try:
            self._call(start, timeout=20, cancel=event)
        except BaseException:
            self._interrupt(grant.id)
            self.store.stop_target(session_id, grant.id, revoke=True)
            raise
        return grant

    @staticmethod
    def ref(grant: ComputerGrant) -> ResourceScopeRef:
        return ResourceScopeRef(kind=TARGET_KIND, id=grant.id, version=grant.version)

    def _check(self, session_id: str, ref: ResourceScopeRef, event: Event,
               is_cancelled: Callable[[], bool] = lambda: False, deadline: float | None = None) -> Callable[[], None]:
        with self._lock:
            lease = self._targets.get(ref.id)
        def check() -> None:
            if (self._closed.is_set() or event.is_set() or lease is None or lease.cancelled.is_set()
                    or is_cancelled() or (deadline is not None and time.monotonic() >= deadline)):
                raise ComputerError("COMPUTER_ACTION_CANCELLED", "电脑操作已停止或超过期限。请重新共享和观察。")
        return check

    @contextmanager
    def _operation(self, invocation_id: str, target_id: str) -> Iterator[Event]:
        event = Event()
        with self._lock:
            if invocation_id in self._invocations:
                raise ComputerError("COMPUTER_INVOCATION_DUPLICATE", "此操作正在执行，不会重复发送。")
            self._invocations[invocation_id] = (event, target_id)
        try:
            yield event
        finally:
            event.set()
            with self._lock:
                self._invocations.pop(invocation_id, None)

    def observe(self, session_id: str, ref: ResourceScopeRef, invocation_id: str,
                is_cancelled: Callable[[], bool], deadline: float | None = None) -> Observation:
        with self._operation(invocation_id, ref.id) as event:
            check = self._check(session_id, ref, event, is_cancelled, deadline)
            def capture() -> Observation:
                check()
                grant = self.store.require(session_id, ref)
                frame = (self.browser if grant.target.kind == "browser" else self.native).capture(grant)
                check()
                self.store.require(session_id, ref)
                identity = "observation_" + uuid4().hex
                (self.captures / (identity + ".png")).write_bytes(frame.png)
                observation = Observation(id=identity, target_id=grant.id, target_version=grant.version,
                    observed_at=now_ms(), title=frame.title, url=frame.url, window_handle=frame.window_handle,
                    bounds=frame.bounds, image_width=frame.image_width, image_height=frame.image_height,
                    image_sha256=hashlib.sha256(frame.png).hexdigest(), nodes=frame.nodes,
                    truncated=frame.truncated, notes=frame.notes, tabs=frame.tabs, current_tab_id=frame.current_tab_id)
                self._latest[ref.id] = identity
                self._trim_captures()
                return observation
            return self._call(capture, cancel=event)

    def act(self, session_id: str, ref: ResourceScopeRef, before: Observation | None, action: ActInput | str,
            invocation_id: str, is_cancelled: Callable[[], bool], deadline: float | None = None) -> None:
        with self._operation(invocation_id, ref.id) as event:
            check = self._check(session_id, ref, event, is_cancelled, deadline)
            def execute() -> None:
                check()
                grant = self.store.require(session_id, ref, control=True)
                driver = self.browser if grant.target.kind == "browser" else self.native
                if isinstance(action, str):
                    if grant.target.kind != "browser":
                        raise ComputerError("COMPUTER_BROWSER_REQUIRED", "导航只能用于明确共享的受控浏览器。", 400)
                    perform = self.browser.navigate(grant, action, check)
                else:
                    self.require_latest(ref, before)
                    assert before is not None
                    perform = driver.prepare(grant, before, action, check)
                check()
                # A pending stop sets the Event before contending for this short
                # SQLite lease. It cannot queue a new input behind a long read.
                with self.store.effect_lease(session_id, ref, lambda: event.is_set() or is_cancelled()):
                    check()
                    self._latest.pop(ref.id, None)
                    try:
                        perform()
                    except ComputerError:
                        raise
                    except Exception:
                        raise ComputerError("COMPUTER_OUTCOME_UNKNOWN", "操作结果未知。请重新观察，不要直接重复发送。") from None
            self._call(execute, timeout=12, cancel=event)

    def require_latest(self, ref: ResourceScopeRef, before: Observation | None) -> None:
        if (before is None or before.target_id != ref.id or before.target_version != str(ref.version)
                or self._latest.get(ref.id) != before.id or not 0 <= now_ms() - before.observed_at <= OBSERVATION_AGE_MS):
            raise ComputerError("COMPUTER_OBSERVATION_STALE", "需要此共享代次的最新实际观察；请重新观察后再操作。")

    def preview(self, session_id: str, target_id: str) -> tuple[bytes, str]:
        grant = self.store.get(session_id, target_id)
        def capture() -> tuple[bytes, str]:
            self.store.require(session_id, self.ref(grant))
            frame = (self.browser if grant.target.kind == "browser" else self.native).capture(grant, remember=False)
            self.store.require(session_id, self.ref(grant))
            return frame.png, frame.title
        return self._call(capture, timeout=8)

    def browser_state(self, session_id: str, target_id: str) -> BrowserState:
        grant = self.store.get(session_id, target_id)
        if grant.target.kind != "browser":
            raise ComputerError("COMPUTER_BROWSER_REQUIRED", "此目标不是受控浏览器。", 400)
        def read() -> BrowserState:
            self.store.require(session_id, self.ref(grant))
            return self.browser.state(grant)
        return self._call(read, timeout=5)

    def read_capture(self, observation: Observation) -> bytes:
        path = self.captures / (observation.id + ".png")
        try:
            if path.stat().st_size > MAX_IMAGE_BYTES or time.time() - path.stat().st_mtime > 86400:
                raise OSError("Capture retention exceeded")
            data = path.read_bytes()
        except OSError:
            raise ComputerError("COMPUTER_CAPTURE_EXPIRED", "截图已超出本机保留范围，请重新观察。", 410) from None
        if hashlib.sha256(data).hexdigest() != observation.image_sha256:
            raise ComputerError("COMPUTER_CAPTURE_CHANGED", "截图来源校验失败，不会使用替代图片。", 409)
        return data

    def _trim_captures(self) -> None:
        entries = sorted(self.captures.glob("observation_*.png"), key=lambda path: path.stat().st_mtime, reverse=True)
        retained = 0
        for index, path in enumerate(entries):
            stat = path.stat()
            retained += stat.st_size
            if index >= 512 or retained > 256 * 1024 * 1024 or time.time() - stat.st_mtime > 86400:
                path.unlink(missing_ok=True)

    def cancel(self, invocation_id: str) -> None:
        with self._lock:
            operation = self._invocations.get(invocation_id)
            lease = self._targets.get(operation[1]) if operation else None
        if operation:
            event, target_id = operation
            event.set()
            self._interrupt(target_id)
            if lease:
                self.store.stop_target(lease.session_id, target_id)

    def _interrupt(self, target_id: str) -> None:
        with self._lock:
            lease = self._targets.pop(target_id, None)
        if lease:
            lease.cancelled.set()
        self.browser.stop(target_id)
        if not self._closed.is_set():
            def forget() -> None:
                self.native.forget(target_id)
                self.browser.forget(target_id)
                self._latest.pop(target_id, None)
            self._worker.submit(forget)

    def stop(self, session_id: str | None, *, target_id: str | None = None, revoke: bool = False) -> None:
        with self._lock:
            ids = tuple(key for key, lease in self._targets.items()
                        if (session_id is None or lease.session_id == session_id) and (target_id is None or key == target_id))
        for identity in ids:
            self._interrupt(identity)
        if target_id is not None and session_id is not None:
            self.store.stop_target(session_id, target_id, revoke=revoke)
        else:
            self.store.stop(session_id, revoke=revoke)

    def resources(self, context: SessionResourceDiscoveryContext):
        return self.store.descriptors(context.session_id)

    def retire(self, session_id: str) -> None:
        self.stop(session_id, revoke=True)

    def _supervise(self) -> None:
        while not self._closed.wait(.5):
            with self._lock:
                entries = tuple(self._targets.items())
            for target_id, lease in entries:
                if lease.cancelled.is_set():
                    continue
                try:
                    active = self.store.get(lease.session_id, target_id).status == GrantStatus.ACTIVE
                except ValueError:
                    active = False
                if not active:
                    self._interrupt(target_id)

    def close(self) -> None:
        self.stop(None)
        self._closed.set()
        self._monitor.join(timeout=2)
        future = self._worker.submit(self.browser.close)
        try:
            future.result(timeout=5)
        except Exception:
            pass  # All owned Job handles have already been closed synchronously.
        self._worker.shutdown(wait=False, cancel_futures=True)
