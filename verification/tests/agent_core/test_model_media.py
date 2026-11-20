"""Actual native image items, bounded sources and immutable durable references."""
import base64

from engine.agent.model_media import materialize_model_media, media_token_reservation
from engine.agent.observation import serialize_model_observation
from engine.representation import ArtifactRepresentationError


def _output(call_id: str, artifact_id: str) -> dict:
    return {"type": "function_call_output", "call_id": call_id,
        "output": serialize_model_observation(status="succeeded", summary="Actual image", facts={},
            artifact_ids=[artifact_id], retryable=False, media=[{
                "artifact_id": artifact_id, "representation_type": "test.image.v1", "operation": "image",
            }])}


def test_only_latest_image_is_materialized_without_changing_durable_transcript() -> None:
    items = [_output("first", "artifact1"), _output("second", "artifact2")]
    source = b"\x89PNG\r\nfixture"
    calls = []
    def read(ref):
        calls.append(ref.artifact_id)
        return source, "image/png"
    wire = materialize_model_media(items, read=read, check_cancelled=lambda: None)
    assert calls == ["artifact2"]
    assert wire[0] == items[0]
    assert isinstance(items[1]["output"], str) and "base64" not in items[1]["output"]
    text, image = wire[1]["output"]
    assert text == {"type": "input_text", "text": items[1]["output"]}
    assert image["type"] == "input_image"
    assert base64.b64decode(image["image_url"].split(",")[1]) == source
    assert media_token_reservation(items) == 4096


def test_expired_image_is_explicit_and_never_replaced_with_another_source() -> None:
    def unavailable(_ref):
        raise ArtifactRepresentationError("SOURCE_UNAVAILABLE", "Retained image expired.", status_code=410)
    original = [_output("first", "artifact1")]
    wire = materialize_model_media(original, read=unavailable, check_cancelled=lambda: None)
    assert '"media_status"' in wire[0]["output"] and "Request a new observation" in wire[0]["output"]
    assert "media_status" not in original[0]["output"]


def test_oversized_or_non_image_stream_never_becomes_model_input() -> None:
    items = [_output("first", "artifact1")]
    for source, mime in ((b"x" * (2 * 1024 * 1024 + 1), "image/png"), (b"html", "text/html")):
        wire = materialize_model_media(items, read=lambda _ref: (source, mime), check_cancelled=lambda: None)
        assert isinstance(wire[0]["output"], str) and '"INVALID_REQUEST"' in wire[0]["output"]


def test_plain_tools_keep_their_original_responses_protocol() -> None:
    items = [{"type": "function_call_output", "call_id": "plain", "output": "text"}]
    def forbidden(_ref):
        raise AssertionError("Plain tools must never read a media source")
    assert materialize_model_media(items, read=forbidden, check_cancelled=lambda: None) is items
    assert media_token_reservation(items) == 0
