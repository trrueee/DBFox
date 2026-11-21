"""Playwright adapter for a dedicated Edge process owned by WindowsProcess.

Playwright objects stay on the computer worker. The Job handle is the only
cross-thread object: stop can terminate it without waiting for a page callback.
"""
from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from io import BytesIO
import hashlib
import logging
import os
from pathlib import Path
import subprocess
import shutil
from threading import Lock, Thread
import time
from uuid import uuid4
from typing import Any, TypeVar
from urllib.parse import urlsplit

from engine.computer.contracts import ActInput, BrowserState, BrowserTab, ComputerError, ComputerGrant, ComputerNode, MAX_NODES, Observation, Rect
from engine.computer.drivers import CapturedFrame, PreparedAction, encode_capture

logger = logging.getLogger(__name__)
T = TypeVar("T")

_ELEMENT_INFO = """e => ({
    role: e.getAttribute('role') || e.tagName.toLowerCase(),
    name: (e.getAttribute('aria-label') || Array.from(e.labels || []).map(x => x.textContent).join(' ') || e.innerText || e.getAttribute('placeholder') || e.getAttribute('title') || '').slice(0,160),
    value: e.type === 'password' ? null : (typeof e.value === 'string' ? e.value : e.isContentEditable ? e.textContent : null),
    sensitive: e.type === 'password', enabled: !e.disabled
})"""


def edge_executable() -> Path | None:
    for variable in ("ProgramFiles(x86)", "ProgramFiles"):
        root = os.environ.get(variable)
        if root:
            candidate = Path(root) / "Microsoft/Edge/Application/msedge.exe"
            if candidate.is_file():
                return candidate
    return None


def checked_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
        raise ComputerError("COMPUTER_URL_INVALID", "使用不含账号或密码的完整 HTTP 或 HTTPS 地址。", 400)
    if any(ord(char) < 32 for char in value):
        raise ComputerError("COMPUTER_URL_INVALID", "地址不能包含控制字符。", 400)
    return value


class OwnedBrowser:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._playwright: Any = None
        self._browsers: dict[str, tuple[Any, Any, Any]] = {}
        self._elements: dict[str, dict[str, Any]] = {}
        self._pages: dict[str, dict[str, Any]] = {}
        self._jobs: dict[str, Any] = {}
        self._drainers: dict[str, Thread] = {}
        self._lock = Lock()
        self._runner: asyncio.Runner | None = None

    def _run(self, operation: Coroutine[Any, Any, T]) -> T:
        if self._runner is None:
            self._runner = asyncio.Runner()
        return self._runner.run(operation)

    def _prepared(self, operation: Callable[[], Coroutine[Any, Any, None]]) -> PreparedAction:
        task: asyncio.Future[None] | None = None

        async def start() -> None:
            nonlocal task
            if task is not None:
                raise ComputerError("COMPUTER_INVOCATION_DUPLICATE", "操作已经提交，不会重复发送。")
            # Python 3.12+: enter the actual Playwright operation now, while
            # authorization is fenced. Do not merely enqueue it for a later Run.
            task = asyncio.eager_task_factory(asyncio.get_running_loop(), operation())

        async def finish() -> None:
            if task is not None:
                await task

        return PreparedAction(lambda: self._run(start()), lambda: self._run(finish()))

    def start(self, grant: ComputerGrant, check: Callable[[], None],
              launch: Callable[[Callable[[], None]], None]) -> None:
        from engine.local_execution.windows import WindowsProcess
        from playwright.async_api import async_playwright
        executable = edge_executable()
        if executable is None:
            raise ComputerError("COMPUTER_BROWSER_UNAVAILABLE", "未找到 Microsoft Edge。请安装浏览器后重试。", 503)
        profile = (self.directory / grant.id).resolve()
        profile.mkdir(parents=True, exist_ok=False)
        command = [str(executable), f"--user-data-dir={profile}", "--remote-debugging-port=0",
                   "--remote-debugging-address=127.0.0.1", "--no-first-run", "--no-default-browser-check", "about:blank"]

        def spawn() -> None:
            check()
            job = WindowsProcess.launch(executable, subprocess.list2cmdline(command), profile,
                                        {key: value for key, value in os.environ.items()
                                         if not key.startswith(("DBFOX_", "OPENAI_", "ANTHROPIC_", "AZURE_OPENAI_"))},
                                        interactive=False)
            with self._lock:
                self._jobs[grant.id] = job
            # Discard diagnostics, continuously drain pipes. They may contain
            # page URLs and never become a second durable browsing history.
            drainer = Thread(target=self._drain, args=(job,), name="computer-browser-output", daemon=True)
            self._drainers[grant.id] = drainer
            drainer.start()
            check()

        try:
            launch(spawn)
            logger.info("Computer browser startup stage=process-created")
            deadline = time.monotonic() + 12
            port_file = profile / "DevToolsActivePort"
            endpoint: list[str] = []
            port = 0
            while True:
                check()
                try:
                    endpoint = port_file.read_text(encoding="utf-8").splitlines()
                    port = int(endpoint[0])
                    if 0 < port < 65536 and len(endpoint) == 2 and endpoint[1].startswith("/devtools/browser/"):
                        break
                except (FileNotFoundError, PermissionError, ValueError, IndexError):
                    pass  # Chromium may still be publishing its ready endpoint.
                if time.monotonic() > deadline:
                    raise ComputerError("COMPUTER_BROWSER_START_FAILED", "受控浏览器未能建立连接。", 503)
                time.sleep(.05)
            async def connect() -> None:
                if self._playwright is None:
                    logger.info("Computer browser startup stage=driver-starting")
                    self._playwright = await async_playwright().start()
                check()
                logger.info("Computer browser startup stage=connecting")
                browser = await self._playwright.chromium.connect_over_cdp(f"ws://127.0.0.1:{port}{endpoint[1]}", timeout=5000)
                # The empty incognito context never adopts a personal profile.
                context = await browser.new_context(viewport={"width": 1280, "height": 800}, accept_downloads=False)
                logger.info("Computer browser startup stage=context-created")
                context.set_default_timeout(1800)
                context.set_default_navigation_timeout(5000)
                page = await context.new_page()
                self._browsers[grant.id] = (browser, context, page)
            self._run(connect())
            check()
        except BaseException:
            self.stop(grant.id)
            raise

    @staticmethod
    def _drain(job: Any) -> None:
        streams = {"stdout", "stderr"}
        while streams:
            try:
                for stream in tuple(streams):
                    if job.read(stream, 65536) is None:
                        streams.remove(stream)
            except OSError:
                return
            time.sleep(.05)

    def _page(self, grant: ComputerGrant) -> Any:
        entry = self._browsers.get(grant.id)
        if entry is None:
            raise ComputerError("COMPUTER_BROWSER_CLOSED", "受控浏览器已关闭。请重新共享，不会自动恢复操作。")
        browser, context, page = entry
        if page.is_closed() and context.pages:
            page = context.pages[0]
            self._browsers[grant.id] = (browser, context, page)
        if not browser.is_connected() or page.is_closed():
            raise ComputerError("COMPUTER_BROWSER_CLOSED", "受控页面已关闭。请重新共享。")
        return page

    def capture(self, grant: ComputerGrant, *, remember: bool = True) -> CapturedFrame:
        return self._run(self._capture(grant, remember=remember))

    async def _capture(self, grant: ComputerGrant, *, remember: bool) -> CapturedFrame:
        from PIL import Image
        page = self._page(grant)
        state = await self._state(grant)
        png = await page.screenshot(type="png", timeout=3000, mask=[page.locator('input[type="password"]')])
        png, width, height = encode_capture(Image.open(BytesIO(png)))
        nodes: list[ComputerNode] = []
        elements: dict[str, Any] = {}
        truncated = len(page.frames) > 8
        for frame in page.frames[:8]:
            handles = await frame.locator('a[href],button,input,textarea,select,[role],[contenteditable="true"]').element_handles()
            truncated = truncated or len(handles) + len(nodes) > MAX_NODES
            for element in handles:
                if len(nodes) >= MAX_NODES:
                    break
                box = await element.bounding_box()
                if not box or box["width"] <= 0 or box["height"] <= 0:
                    continue
                info = await element.evaluate(_ELEMENT_INFO)
                value = info["value"]
                info["value_sha256"] = hashlib.sha256(value.encode("utf-8")).hexdigest() if value is not None else None
                info["value"] = value[:160] if value is not None else None
                node_id = f"n{len(nodes)}"
                rect = Rect(x=int(box["x"]), y=int(box["y"]), width=max(1, int(box["width"])), height=max(1, int(box["height"])))
                nodes.append(ComputerNode(id=node_id, bounds=rect, **info))
                elements[node_id] = element
        if remember:
            self._elements[grant.id] = elements
        body = (await page.locator("body").inner_text(timeout=1200))[:4000] if await page.locator("body").count() else ""
        return CapturedFrame(title=(await page.title())[:240], url=page.url[:4096], bounds=Rect(x=0, y=0, width=1280, height=800),
                             png=png, image_width=width, image_height=height, nodes=tuple(nodes),
                             truncated=truncated, notes=(body,) if body else (), tabs=state.tabs, current_tab_id=state.current_tab_id)

    def state(self, grant: ComputerGrant) -> BrowserState:
        return self._run(self._state(grant))

    async def _state(self, grant: ComputerGrant) -> BrowserState:
        page = self._page(grant)
        context = self._browsers[grant.id][1]
        pages = self._pages.setdefault(grant.id, {})
        for identity, candidate in tuple(pages.items()):
            if candidate.is_closed():
                pages.pop(identity)
        for candidate in context.pages:
            if candidate not in pages.values():
                if len(pages) >= 8:
                    raise ComputerError("COMPUTER_TAB_LIMIT", "受控浏览器最多观察 8 个页面。请先由用户关闭多余页面。")
                pages["tab_" + uuid4().hex] = candidate
        tabs = []
        for identity, candidate in pages.items():
            tabs.append(BrowserTab(id=identity, title=(await candidate.title())[:240], url=candidate.url[:4096]))
        return BrowserState(title=(await page.title())[:240], url=page.url[:4096], tabs=tuple(tabs),
            current_tab_id=next(identity for identity, candidate in pages.items() if candidate is page))

    def prepare(self, grant: ComputerGrant, before: Observation, action: ActInput,
                check: Callable[[], None]) -> PreparedAction:
        return self._run(self._prepare(grant, before, action, check))

    async def _prepare(self, grant: ComputerGrant, before: Observation, action: ActInput,
                       check: Callable[[], None]) -> PreparedAction:
        page = self._page(grant)
        state = await self._state(grant)
        if state.current_tab_id != before.current_tab_id:
            raise ComputerError("COMPUTER_OBSERVATION_CHANGED", "当前页面已切换，请重新观察。")
        if page.url != before.url:
            raise ComputerError("COMPUTER_OBSERVATION_CHANGED", "页面已跳转，请重新观察。")
        node = next((node for node in before.nodes if node.id == action.node_id), None)
        element = self._elements.get(grant.id, {}).get(action.node_id or "")
        if action.node_id is not None:
            if node is None or element is None or not node.enabled or node.sensitive or not await element.is_visible():
                raise ComputerError("COMPUTER_ELEMENT_UNAVAILABLE", "页面元素已失效或属于敏感输入，请重新观察或由用户接管。")
            box = await element.bounding_box()
            info = await element.evaluate(_ELEMENT_INFO)
            if info["name"] != node.name or info["role"] != node.role or info["sensitive"] or not info["enabled"]:
                raise ComputerError("COMPUTER_OBSERVATION_CHANGED", "元素内容或权限已变化，请重新观察。")
            if box is None or any(abs(box[key] - getattr(node.bounds, key)) > 2 for key in ("x", "y", "width", "height")):
                raise ComputerError("COMPUTER_OBSERVATION_CHANGED", "页面元素位置已变化，请重新观察。")
        if action.action == "type_text" and element is None:
            raise ComputerError("COMPUTER_EDIT_REQUIRED", "写入文字需要观察中的可编辑元素。", 400)
        if action.action == "key":
            from engine.computer.keys import key_sequence
            key_sequence(action.key or "")  # Same declared shortcut boundary.
        if action.action in {"close_tab", "select_tab"} and not any(tab.id == action.tab_id for tab in before.tabs):
            raise ComputerError("COMPUTER_TAB_UNAVAILABLE", "此页面不属于当前观察，请重新观察。")

        # Reads and sensitivity checks precede the submission fence; only the
        # actual input/navigation request is started inside it.
        if action.action == "type_text":
            assert element is not None and node is not None
            current = await element.evaluate("e => ({sensitive:e.type === 'password', value:typeof e.value === 'string' ? e.value : e.isContentEditable ? e.textContent : null})")
            if current["sensitive"]:
                raise ComputerError("COMPUTER_SENSITIVE_INPUT", "敏感输入需要用户接管。")
            if current["value"] is None or hashlib.sha256(current["value"].encode("utf-8")).hexdigest() != node.value_sha256:
                raise ComputerError("COMPUTER_OBSERVATION_CHANGED", "输入内容已变化，未覆盖用户输入。")
        if action.action == "key":
            for frame in page.frames[:8]:
                if await frame.evaluate("() => document.activeElement?.type === 'password'"):
                    raise ComputerError("COMPUTER_SENSITIVE_INPUT", "敏感输入需要用户接管。")

        async def perform() -> None:
            check()
            if page.url != before.url:
                raise ComputerError("COMPUTER_OBSERVATION_CHANGED", "页面已变化，未发送操作。")
            if action.action == "type_text":
                assert element is not None and node is not None
                await element.fill(action.text or "", timeout=1500)
            elif action.action == "key":
                aliases = {"CTRL": "Control", "ALT": "Alt", "SHIFT": "Shift", "ESC": "Escape", "ENTER": "Enter",
                           "BACKSPACE": "Backspace", "DELETE": "Delete", "SPACE": "Space", "TAB": "Tab",
                           "PGUP": "PageUp", "PGDN": "PageDown", "LEFT": "ArrowLeft", "RIGHT": "ArrowRight",
                           "UP": "ArrowUp", "DOWN": "ArrowDown", "HOME": "Home", "END": "End", "INSERT": "Insert"}
                key = "+".join(aliases.get(part, part) for part in (action.key or "").upper().split("+"))
                await page.keyboard.press(key)
            elif action.action == "scroll":
                await page.mouse.wheel(0, action.scroll_y)
            elif action.action == "focus":
                await page.bring_to_front()
            elif action.action in {"back", "forward", "reload"}:
                await getattr(page, {"back": "go_back", "forward": "go_forward", "reload": "reload"}[action.action])(wait_until="commit", timeout=3000)
            elif action.action in {"new_tab", "select_tab", "close_tab"}:
                browser, context, _ = self._browsers[grant.id]
                if action.action == "new_tab":
                    if len(context.pages) >= 8:
                        raise ComputerError("COMPUTER_TAB_LIMIT", "受控浏览器最多打开 8 个页面。")
                    selected = await context.new_page()
                else:
                    selected = self._pages.get(grant.id, {}).get(action.tab_id or "")
                    if selected is None or selected.is_closed():
                        raise ComputerError("COMPUTER_TAB_UNAVAILABLE", "此页面已关闭，请重新观察。")
                    if action.action == "close_tab":
                        if len(context.pages) <= 1:
                            raise ComputerError("COMPUTER_LAST_TAB", "不能关闭最后一个受控页面。结束浏览请停止共享。")
                        await selected.close()
                        selected = page if page is not selected else context.pages[0]
                await selected.bring_to_front()
                self._browsers[grant.id] = (browser, context, selected)
            elif element is not None:
                await getattr(element, "dblclick" if action.action == "double_click" else "click")(timeout=1500, no_wait_after=True)
            elif action.point is not None:
                point = action.point
                await getattr(page.mouse, "dblclick" if action.action == "double_click" else "click")(point.x * 1279, point.y * 799)
        return self._prepared(perform)

    def navigate(self, grant: ComputerGrant, url: str, check: Callable[[], None]) -> PreparedAction:
        page, url = self._page(grant), checked_url(url)

        async def perform() -> None:
            check()
            await page.goto(url, wait_until="commit", timeout=4000)
        return self._prepared(perform)

    def stop(self, target_id: str) -> None:
        with self._lock:
            job = self._jobs.get(target_id)
        if job is not None:
            try:
                job.close_job()
            except OSError:
                pass  # Process may already have closed; no restart is attempted.

    def forget(self, target_id: str) -> None:
        self._elements.pop(target_id, None)
        self._pages.pop(target_id, None)
        entry = self._browsers.pop(target_id, None)
        if entry is not None:
            try:
                self._run(entry[0].close())
            except Exception:
                pass  # The Job is already stopped by the synchronous stop fence.
        self.stop(target_id)
        with self._lock:
            job = self._jobs.pop(target_id, None)
        if job is not None:
            drainer = self._drainers.pop(target_id, None)
            if drainer is not None:
                drainer.join(timeout=.5)
            job.close()
        root = self.directory.resolve()
        profile = (root / target_id).resolve()
        if profile.parent == root and target_id.startswith("computer_") and len(target_id) == 41:
            try:
                shutil.rmtree(profile)
            except FileNotFoundError:
                pass
            except OSError:
                logger.warning("Computer temporary browser profile cleanup deferred")

    def close(self) -> None:
        for target_id in tuple(self._jobs):
            self.forget(target_id)
        try:
            if self._playwright is not None:
                self._run(self._playwright.stop())
                self._playwright = None
        finally:
            if self._runner is not None:
                self._runner.close()
                self._runner = None
