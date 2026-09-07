"""Independent attacks of complete signed Comic through production boundaries."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading
from uuid import uuid4

import pytest

from dbfox_dlc_api import ArtifactRepresentationContext, ArtifactRepresentationError, ArtifactRepresentationRequest, DlcOperationError
from engine.agent.repositories.artifact import ArtifactRepository
from engine.models import AgentRun
from dbfox_dlc_api import ToolKey
from verification.testkit.comic_independent import InstalledComic


@pytest.fixture
def comic(tmp_path):
    runtime = InstalledComic(tmp_path)
    try:
        yield runtime
    finally:
        runtime.close()


def counts(runtime):
    paths = list(runtime.service.storage_root.rglob("comic.sqlite3"))
    assert len(paths) == 1
    with sqlite3.connect(paths[0]) as db:
        return tuple(db.execute("SELECT COUNT(*) FROM " + table).fetchone()[0] for table in ("revisions", "receipts", "object_ids"))


def page(identity="page-one"):
    return {"kind": "page_create", "page": {"id": identity, "panels": [{"id": identity + ".panel"}]}}


def apply(runtime, summary, operation, identity=None):
    return runtime.op("comics.apply", {"comic_id": summary.id, "expected_version": summary.version,
        "request_id": identity or uuid4().hex, "operation": operation}).comic


def test_real_admission_rejects_foreign_project_and_tool_rejects_wrong_frozen_comic(comic):
    first, second = comic.create(), comic.create()
    before = counts(comic)
    with pytest.raises(ValueError, match="not available"):
        comic.refs("dbfox.comic.document", first.id, project="foreign-project")
    with pytest.raises(DlcOperationError, match="does not exist in this Project"):
        comic.op("comics.get", {"comic_id": first.id}, project="foreign-project")
    refs = comic.refs("dbfox.comic.document", first.id)
    result = comic.invoke("page_create", {"comic_id": second.id, "expected_version": 1, "operation": page()}, refs)
    assert result.status == "failed" and not result.artifact_drafts
    assert counts(comic) == before


def test_concurrent_human_edit_cannot_be_overwritten_by_frozen_agent(comic):
    initial = comic.create()
    refs = comic.refs("dbfox.comic.document", initial.id)
    barrier = threading.Barrier(2)
    def edit(identity):
        barrier.wait(timeout=3)
        try:
            return apply(comic, initial, page(identity))
        except DlcOperationError as exc:
            assert exc.code == "COMIC_STALE"
            return None
    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(edit, ("human-a", "human-b")))
    winner = next(outcome for outcome in outcomes if outcome is not None)
    assert sum(o is not None for o in outcomes) == 1 and winner.version == 2
    before = counts(comic)
    # Even a fresh caller-supplied expected_version cannot enlarge the frozen ref.
    result = comic.invoke("page_create", {"comic_id": initial.id, "expected_version": 2, "operation": page("agent-stale")}, refs)
    assert result.status == "failed" and not result.artifact_drafts
    assert counts(comic) == before
    assert comic.op("comics.get", {"comic_id": initial.id}).comic == winner


@pytest.mark.parametrize("cancel_poll", [3, 4])
def test_runtime_cancellation_before_and_after_commit_has_honest_recovery(comic, cancel_poll):
    initial = comic.create()
    refs = comic.refs("dbfox.comic.document", initial.id)
    before = counts(comic)
    identity = uuid4().hex
    payload = {"comic_id": initial.id, "expected_version": 1, "operation": page()}
    polled = 0
    def cancelled():
        nonlocal polled
        polled += 1
        return polled >= cancel_poll
    outcome = comic.invoke("page_create", payload, refs, identity, cancel=cancelled)
    assert outcome.status == "failed" and not outcome.artifact_drafts
    assert polled >= cancel_poll
    durable = counts(comic)
    recovered = comic.invoke("page_create", payload, refs, identity, reconcile=True)
    if cancel_poll == 3:
        assert durable == before
        assert recovered.status == "failed" and recovered.error_code == "TOOL_RECONCILIATION_NOT_APPLIED"
    else:
        assert durable == (before[0] + 1, before[1] + 1, before[2] + 2)
        assert recovered.status == "success" and recovered.output["comic"]["version"] == 2
        again = comic.invoke("page_create", payload, refs, identity, reconcile=True)
        assert again.output == recovered.output and counts(comic) == durable


def test_failed_multi_placement_and_linked_character_deletion_do_not_leave_partial_writes(comic):
    current = apply(comic, comic.create(), {"kind": "page_create", "page": {"id": "page", "panels": [
        {"id": "one", "elements": [{"kind": "character", "id": "speaker", "label": "旅行者"},
            {"kind": "bubble", "id": "speech", "text": "保持对白", "speaker_id": "speaker"}]}, {"id": "two"}]}})
    before = comic.op("comics.get", {"comic_id": current.id, "version": 2, "section": "page", "object_id": "page"})
    totals = counts(comic)
    attacks = [
        {"kind": "panel_layout", "page_id": "page", "placements": [
            {"panel_id": "one", "rect": {"x": .1, "y": .1, "width": .3, "height": .3}},
            {"panel_id": "not-owned", "rect": {"x": .5, "y": .5, "width": .3, "height": .3}}]},
        {"kind": "object_delete", "object_id": "speaker"},
        {"kind": "element_update", "panel_id": "two", "element": {"kind": "bubble", "id": "speech", "text": "wrong panel"}},
    ]
    for operation in attacks:
        with pytest.raises(DlcOperationError):
            apply(comic, current, operation)
        assert counts(comic) == totals
        assert comic.op("comics.get", {"comic_id": current.id, "version": 2, "section": "page", "object_id": "page"}) == before


def test_cjk_observation_pages_advance_without_losing_complete_entries(comic):
    content = "灯塔归途" * 500
    initial = comic.create()
    current = apply(comic, initial, {"kind": "page_create", "page": {"id": "large-page", "panels": [{
        "id": "large-panel", "elements": [{"kind": "caption", "id": f"caption-{i}", "text": content} for i in range(10)]}]}})
    refs = comic.refs("dbfox.comic.document", current.id)
    tool = comic.registry.require(comic.registry.provider_name_for_key(ToolKey("dbfox.comic", "comic_inspect")))
    seen, offset = [], 0
    for _ in range(10):
        result = comic.invoke("comic_inspect", {"comic_id": current.id, "version": current.version,
            "section": "elements", "object_id": "large-panel", "offset": offset, "limit": 32}, refs)
        assert result.status == "success", result.error
        projection = tool.project_observation(status="success", output=result.output, artifacts=())
        value = projection.provider_payload
        assert len(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()) <= 24000
        assert value["total"] == 10 and value["offset"] == offset and value["next_offset"] > offset
        assert all(item["text"] == content for item in value["items"])
        seen.extend(item["id"] for item in value["items"])
        offset = value["next_offset"]
        if not value["has_more"]:
            break
    assert seen == [f"caption-{i}" for i in range(10)] and offset == 10


def test_actual_action_artifact_rejects_forgery_and_survives_delete_reactivation(comic):
    current = apply(comic, comic.create(), page())
    current = apply(comic, current, {"kind": "caption_create", "panel_id": "page-one.panel",
        "caption": {"id": "unsafe-text", "text": "</script><img src=x onerror=alert(1)>\u2028<script>坏指令</script>"}})
    request = {"comic_id": current.id, "expected_version": current.version, "request_id": uuid4().hex}
    result = comic.op("comics.artifact", request)
    with comic.factory() as db:
        assert db.get(AgentRun, result.run_id).status == "completed"
        artifacts = ArtifactRepository(db).list_for_run(result.run_id)
    assert len(artifacts) == 1 and artifacts[0].id == result.artifact_id
    artifact = artifacts[0]
    def read(target=artifact, operation="export_json", parameters=None):
        provider = comic.snapshot.get_artifact_representation(target.type, "dbfox.comic.document.v1").provider
        return provider.execute(target, ArtifactRepresentationRequest(operation=operation, parameters=parameters or {}),
            ArtifactRepresentationContext(artifact_loader=lambda _: artifact))
    frozen = b"".join(read().chunks)
    html = b"".join(read(operation="export_html").chunks).decode()
    assert html.count("<script>") == 1 and "<img src=x" not in html and "\\u003cimg src=x" in html
    for forged in (artifact.model_copy(update={"provenance": {"tool_invocation_id": "different-invocation"}}),
        artifact.model_copy(update={"payload": {**artifact.payload, "project_id": "foreign-project"}}),
        artifact.model_copy(update={"resource_refs": ()})):
        with pytest.raises(ArtifactRepresentationError):
            read(forged)
    with pytest.raises(ArtifactRepresentationError):
        read(parameters={"version": 1})
    comic.op("comics.delete", {"comic_id": current.id, "expected_version": current.version, "request_id": uuid4().hex})
    comic.service.set_desired_enabled("dbfox.comic", False)
    comic.reload()
    assert not comic.snapshot.get_artifact_representation(artifact.type, "dbfox.comic.document.v1")
    comic.service.set_desired_enabled("dbfox.comic", True)
    comic.reload()
    assert b"".join(read().chunks) == frozen
    assert json.loads(frozen)["pages"][0]["panels"][0]["elements"][0]["id"] == "unsafe-text"
