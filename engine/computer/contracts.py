"""Canonical computer target, observation and action contracts."""
from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

OWNER = "dbfox.computer"
TARGET_KIND = "dbfox.computer.target"
OBSERVATION_ARTIFACT = "dbfox.computer.observation"
ACTION_ARTIFACT = "dbfox.computer.action"
REPRESENTATION = "dbfox.computer.capture.v1"
MAX_NODES = 64
MAX_IMAGE_BYTES = 2 * 1024 * 1024
OBSERVATION_AGE_MS = 120_000


class ComputerError(ValueError):
    """Expected error whose bounded message can cross the API/tool boundary."""

    def __init__(self, code: str, message: str, status: int = 409) -> None:
        super().__init__(message)
        self.code, self.status = code, status


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class GrantStatus(StrEnum):
    ACTIVE = "active"
    PAUSED = "paused"
    REVOKED = "revoked"
    INTERRUPTED = "interrupted"
    EXPIRED = "expired"


class Permission(StrEnum):
    OBSERVE = "observe"
    CONTROL = "control"


class TargetIdentity(Contract):
    kind: Literal["window", "browser"]
    title: str = Field(max_length=240)
    executable: str = Field(min_length=1, max_length=4096)
    process_id: int | None = Field(default=None, ge=1)
    process_started_at: int | None = Field(default=None, ge=0)
    window_handle: str | None = Field(default=None, pattern=r"^[0-9a-f]{1,16}$")
    browser_channel: Literal["msedge"] | None = None
    include_owned_dialogs: bool = True

    @model_validator(mode="after")
    def require_identity(self) -> TargetIdentity:
        if self.kind == "window" and any(value is None for value in (
            self.process_id, self.process_started_at, self.window_handle,
        )):
            raise ValueError("A window requires its observed handle and process identity")
        if self.kind == "browser" and self.browser_channel is None:
            raise ValueError("A browser requires an explicit installed browser channel")
        return self


class TargetOption(Contract):
    inventory_id: str
    target: TargetIdentity


class ComputerGrant(Contract):
    id: str
    session_id: str
    version: str
    target: TargetIdentity
    permission: Permission
    status: GrantStatus
    created_at: int
    expires_at: int


class ShareInput(Contract):
    inventory_id: str = Field(min_length=1, max_length=128)
    permission: Permission = Permission.OBSERVE
    duration_minutes: Literal[5, 15, 30] = 15
    replace_existing: bool = False


class TargetInput(Contract):
    target_id: str = Field(pattern=r"^computer_[0-9a-f]{32}$", description="ID of the explicitly shared target in this conversation's resource directory.")


class NavigateInput(TargetInput):
    url: str = Field(min_length=1, max_length=4096, description="Complete http or https URL to open in the dedicated browser. Never include credentials.")


class Point(Contract):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)


class Rect(Contract):
    x: int
    y: int
    width: int = Field(ge=0)
    height: int = Field(ge=0)


class ComputerNode(Contract):
    id: str = Field(pattern=r"^n[0-9]{1,3}$")
    role: str = Field(max_length=64)
    name: str = Field(max_length=160)
    value: str | None = Field(default=None, max_length=160)
    value_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    bounds: Rect
    enabled: bool = True
    sensitive: bool = False


class BrowserTab(Contract):
    id: str = Field(pattern=r"^tab_[0-9a-f]{32}$")
    title: str = Field(max_length=240)
    url: str = Field(max_length=4096)


class BrowserState(Contract):
    title: str = Field(max_length=240)
    url: str = Field(max_length=4096)
    tabs: tuple[BrowserTab, ...] = Field(max_length=8)
    current_tab_id: str


class Observation(Contract):
    id: str = Field(pattern=r"^observation_[0-9a-f]{32}$")
    target_id: str
    target_version: str
    observed_at: int
    title: str = Field(max_length=240)
    url: str | None = Field(default=None, max_length=4096)
    window_handle: str | None = None
    bounds: Rect
    image_width: int = Field(ge=1, le=2048)
    image_height: int = Field(ge=1, le=2048)
    image_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    nodes: tuple[ComputerNode, ...] = Field(default=(), max_length=MAX_NODES)
    truncated: bool = False
    notes: tuple[str, ...] = ()
    tabs: tuple[BrowserTab, ...] = Field(default=(), max_length=8)
    current_tab_id: str | None = None


class ActInput(TargetInput):
    observation_artifact_id: str = Field(min_length=1, max_length=128, description="Artifact ID from the latest actual observation. A stale observation must be refreshed before acting.")
    action: Literal["click", "double_click", "type_text", "key", "scroll", "focus", "back", "forward", "reload", "new_tab", "select_tab", "close_tab"]
    node_id: str | None = Field(default=None, pattern=r"^n[0-9]{1,3}$")
    point: Point | None = Field(default=None, description="Point in the observed image as fractions from 0 to 1; use only when no accessible element is available.")
    text: str | None = Field(default=None, min_length=1, max_length=2000)
    key: str | None = Field(default=None, min_length=1, max_length=64)
    scroll_y: int = Field(default=0, ge=-1800, le=1800)
    tab_id: str | None = Field(default=None, pattern=r"^tab_[0-9a-f]{32}$")

    @model_validator(mode="after")
    def require_action_fields(self) -> ActInput:
        if self.node_id is not None and self.point is not None:
            raise ValueError("Choose an accessible node or an image point, not both")
        if self.action in ("click", "double_click") and self.node_id is None and self.point is None:
            raise ValueError("A click requires an observed node or image point")
        if self.action == "type_text" and not self.text:
            raise ValueError("type_text requires text")
        if self.action == "key" and not self.key:
            raise ValueError("key requires an explicit key or permitted chord")
        if self.action == "scroll" and self.scroll_y == 0:
            raise ValueError("scroll requires a nonzero scroll_y")
        if self.action in {"select_tab", "close_tab"} and self.tab_id is None:
            raise ValueError("Tab actions require an observed tab_id")
        if self.text and "\0" in self.text:
            raise ValueError("Text cannot contain NUL")
        return self


class ActionEvidence(Contract):
    target_id: str
    action: str
    invocation_id: str
    before_observation_id: str | None
    after_observation_id: str | None
    performed_at: int
    disposition: Literal["performed"] = "performed"
    summary: str


class ActionResult(Contract):
    evidence: ActionEvidence
    observation: Observation | None = None
    warning: str | None = None
