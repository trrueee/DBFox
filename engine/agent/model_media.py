"""Bounded native image input; durable Context keeps immutable references only."""
from __future__ import annotations

import base64
from collections.abc import Callable
from typing import Any

from pydantic import ValidationError

from engine.json_codec import JsonCodecError, canonical_dumps, loads
from engine.representation import ArtifactRepresentationError
from engine.tools.runtime.observation import ToolMediaReference

MAX_MODEL_IMAGE_BYTES = 2 * 1024 * 1024
MODEL_IMAGE_RESERVED_TOKENS = 4096


def media_reference(item: dict[str, Any]) -> ToolMediaReference | None:
    if item.get("type") != "function_call_output" or not isinstance(item.get("output"), str):
        return None
    try:
        payload = loads(item["output"])
        media = payload.get("media") if isinstance(payload, dict) else None
        if not media:
            return None
        if not isinstance(media, list) or len(media) != 1:
            raise ValueError("Media reference exceeds the one-image contract")
        return ToolMediaReference.model_validate(media[0])
    except (JsonCodecError, ValidationError, ValueError):
        return None


def media_token_reservation(items: list[dict[str, Any]]) -> int:
    return MODEL_IMAGE_RESERVED_TOKENS if any(media_reference(item) for item in items) else 0


def materialize_model_media(
    items: list[dict[str, Any]], *, read: Callable[[ToolMediaReference], tuple[bytes, str]],
    check_cancelled: Callable[[], None],
) -> list[dict[str, Any]]:
    """Include one latest image without changing stored transcript or prompt hash.

    Older source references remain visible as text. A failed read is explicitly
    reported to the model so it can request a new observation, never substituted.
    """
    latest = next((index for index in range(len(items) - 1, -1, -1) if media_reference(items[index])), None)
    if latest is None:
        return items
    result = [dict(item) for item in items]
    ref = media_reference(items[latest])
    assert ref is not None
    check_cancelled()
    try:
        data, media_type = read(ref)
        check_cancelled()
        if media_type not in {"image/png", "image/jpeg", "image/webp"} or not 0 < len(data) <= MAX_MODEL_IMAGE_BYTES:
            raise ArtifactRepresentationError("INVALID_REQUEST", "Model image exceeds its media contract.")
    except ArtifactRepresentationError as exc:
        value = loads(str(items[latest]["output"]))
        assert isinstance(value, dict)
        value["media_status"] = {"code": exc.code, "message": "Image unavailable. Request a new observation before acting."}
        result[latest] = {**result[latest], "output": canonical_dumps(value)}
        return result
    result[latest] = {**result[latest], "output": [
        {"type": "input_text", "text": str(items[latest]["output"])},
        {"type": "input_image", "image_url": "data:" + media_type + ";base64," + base64.b64encode(data).decode("ascii"), "detail": "auto"},
    ]}
    return result
