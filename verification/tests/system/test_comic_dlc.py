"""Comic author tests; independent review and native acceptance are separate gates."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib
import importlib.util
from pathlib import Path
import sqlite3
import sys
from uuid import uuid4
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from dbfox_dlc_api import Artifact, ArtifactRepresentationContext, ArtifactRepresentationRequest, ResourceScopeRef
from engine.dlc import BuiltinContributionSet, ContributionCompiler, DlcPackageService
from engine.dlc.package_builder import build_dlc_package_from_source
from engine.tools.runtime.registry import ToolRegistry
from engine.tools.runtime.runtime import ToolRuntime

SOURCE = Path(__file__).resolve().parents[3] / "dlcs/dbfox.comic"
PACKAGE = "_comic_author_tests"
if PACKAGE not in sys.modules:
    spec = importlib.util.spec_from_file_location(PACKAGE, SOURCE / "backend/__init__.py", submodule_search_locations=[str(SOURCE / "backend")])
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
c, s, t, r = (importlib.import_module(PACKAGE + "." + name) for name in ("contracts", "store", "contributions", "representation"))


@pytest.fixture
def store(tmp_path):
    return s.ComicStore(tmp_path / "comic")


def create(store):
    return store.write("project", "create", c.CreateInput(title="灯塔归途"), "create").comic


def edit(store, comic, operation, key=None, **kwargs):
    return store.write(comic.project_id, "apply", c.ApplyInput(comic_id=comic.id, expected_version=comic.version, operation=operation), key or uuid4().hex, **kwargs).comic


def page(identity="page-1"):
    return {"kind": "page_create", "page": {"id": identity, "title": "归途", "panels": [{"id": identity + ".panel", "title": "抵达"}]}}


def test_round_trip_single_canonical_and_exact_reconcile(store):
    first = create(store)
    payload = c.ApplyInput(comic_id=first.id, expected_version=1, operation=page())
    result = store.write("project", "apply", payload, "edit")
    assert result.comic.version == 2
    again = s.ComicStore(store.path.parent)
    assert again.reconcile("project", "apply", payload, "edit") == result
    assert again.write("project", "apply", payload, "edit") == result
    assert again.get("project", first.id, 1).document.pages == []
    assert again.get("project", first.id).document.pages[0].panels[0].title == "抵达"
    with pytest.raises(s.ComicError, match="different input"):
        again.write("project", "apply", payload.model_copy(update={"expected_version": 2}), "edit")


def test_eight_named_operations_preserve_unrelated_content(store):
    comic = edit(store, create(store), page())
    operations = [
        {"kind": "panel_create", "page_id": "page-1", "panels": [{"id": "second"}]},
        {"kind": "panel_layout", "page_id": "page-1", "placements": [{"panel_id": "second", "rect": {"x": .5, "y": .1, "width": .4, "height": .4}}]},
        {"kind": "shot_set", "panel_id": "second", "shot": {"framing": "wide", "description": "海风"}},
        {"kind": "character_place", "panel_id": "second", "character": {"id": "fox", "label": "旅行者"}},
        {"kind": "bubble_create", "panel_id": "second", "bubble": {"id": "speech", "text": "我们到家了。", "speaker_id": "fox"}},
        {"kind": "caption_create", "panel_id": "second", "caption": {"id": "caption", "text": "黄昏"}},
        {"kind": "panel_reorder", "page_id": "page-1", "panel_ids": ["second", "page-1.panel"]},
    ]
    for operation in operations:
        comic = edit(store, comic, operation)
    doc = store.get("project", comic.id).document
    assert doc.pages[0].panels[0].id == "second"
    assert doc.pages[0].panels[1].title == "抵达"
    assert doc.pages[0].panels[0].elements[1].text == "我们到家了。"
    assert len({tool.name for tool in t.build_tools(store)}) == len(t.build_tools(store))
    assert {"page_create", "panel_create", "panel_layout", "shot_set", "character_place", "bubble_create", "caption_create", "panel_reorder"} <= {tool.name for tool in t.build_tools(store)}


@pytest.mark.parametrize("operation", [
    {"kind": "object_delete", "object_id": "missing"},
    {"kind": "panel_layout", "page_id": "page-1", "placements": [{"panel_id": "missing", "rect": {}}]},
    {"kind": "panel_reorder", "page_id": "page-1", "panel_ids": []},
    {"kind": "bubble_create", "panel_id": "page-1.panel", "bubble": {"id": "speech", "speaker_id": "absent"}},
    {"kind": "page_create", "page": {"id": "page-1"}},
])
def test_invalid_reference_changes_nothing(store, operation):
    comic = edit(store, create(store), page())
    with pytest.raises(s.ComicError):
        edit(store, comic, operation)
    assert store.get("project", comic.id).comic == comic


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1, 2, True])
def test_invalid_geometry_rejected(value):
    with pytest.raises(ValueError):
        c.Rect(x=value)


def test_stale_concurrent_and_precommit_cancellation(store):
    comic = create(store)
    with ThreadPoolExecutor(2) as workers:
        futures = [workers.submit(edit, store, comic, page(f"p{i}")) for i in range(2)]
    assert sum(f.exception() is None for f in futures) == 1
    assert store.get("project", comic.id).comic.version == 2
    calls = 0
    def cancel_at_commit():
        nonlocal calls
        calls += 1
        return calls == 2
    current = store.get("project", comic.id).comic
    with pytest.raises(s.ComicError, match="cancelled"):
        edit(store, current, page("cancelled-page"), cancelled=cancel_at_commit)
    assert store.get("project", comic.id).comic == current


def test_noop_undo_delete_and_id_reuse(store):
    comic = edit(store, create(store), page())
    same = edit(store, comic, {"kind": "page_reorder", "page_ids": ["page-1"]})
    assert same == comic
    removed = edit(store, comic, {"kind": "object_delete", "object_id": "page-1"})
    with pytest.raises(s.ComicError, match="cannot be reused"):
        edit(store, removed, page())
    restored = store.write("project", "undo", c.UndoInput(comic_id=comic.id, expected_version=3, target_version=2), "undo")
    assert restored.comic.version == 4
    assert store.get("project", comic.id).document == store.get("project", comic.id, 2).document
    deleted = store.write("project", "delete", c.VersionInput(comic_id=comic.id, expected_version=4), "delete")
    assert deleted.comic.status == "deleted" and len(store.resources("project")) == 1
    assert store.get("project", comic.id, 2).document.pages
    with pytest.raises(s.ComicError, match="deleted"):
        edit(store, deleted.comic, page("late"))


def test_historical_pages_diff_and_cross_project_rejection(store):
    comic = edit(store, create(store), page())
    newer = edit(store, comic, page("page-2"))
    fixed = store.inspect("project", c.InspectInput(comic_id=comic.id, version=2, section="pages"))
    assert fixed.total == 1 and fixed.comic.version == 2
    delta = store.diff("project", c.DiffInput(comic_id=comic.id, from_version=2, to_version=3))
    assert {d["id"] for d in delta.differences} == {"$document", "page-2", "page-2.panel"}
    with pytest.raises(s.ComicError):
        store.get("foreign", newer.id)


def test_declared_capacity_and_diff_pagination_beyond_element_count(store):
    comic = create(store)
    for index in range(32):
        comic = edit(store, comic, {"kind": "page_create", "page": {
            "id": f"large-{index}", "panels": [{"id": f"panel-{index}", "elements": [
                {"id": f"note-{index}-{n}", "kind": "note", "text": "海风与灯塔"} for n in range(128)]}]}})
    assert comic.element_count == 4096
    tail = store.diff("project", c.DiffInput(comic_id=comic.id, from_version=1, to_version=comic.version, offset=4096, limit=32))
    assert tail.total == 4161 and len(tail.differences) == 32
    final = store.diff("project", c.DiffInput(comic_id=comic.id, from_version=1, to_version=comic.version, offset=4160, limit=32))
    assert len(final.differences) == 1 and final.next_offset == final.total
    with pytest.raises(s.ComicError):
        edit(store, comic, {"kind": "note_create", "panel_id": "panel-0", "note": {"id": "over-limit"}})
    assert store.get("project", comic.id).comic == comic
    full = store.inspect("project", c.InspectInput(comic_id=comic.id, section="page", object_id="large-0"))
    assert len(full.model_dump_json().encode("utf-8")) < 256 * 1024


def test_page_count_and_text_limits():
    document = {"title": "边界", "pages": [{"id": f"p-{i}"} for i in range(128)]}
    assert len(c.ComicProject.model_validate(document).pages) == 128
    document["pages"].append({"id": "overflow"})
    with pytest.raises(ValueError):
        c.ComicProject.model_validate(document)
    with pytest.raises(ValueError):
        c.ComicProject.model_validate({"title": "文字上限", "pages": [{"id": "p", "panels": [{"id": "panel", "elements": [
            {"id": f"text-{i}", "kind": "caption", "text": "字" * 2000} for i in range(11)]}]}]})


@pytest.mark.parametrize("sql", ["UPDATE revisions SET hash='wrong' WHERE version=2", "UPDATE comics SET head=1", "UPDATE revisions SET parent=NULL WHERE version=2", "UPDATE revisions SET producer='someone-else' WHERE version=2"])
def test_corrupt_content_chain_or_receipt_fails_closed(store, sql):
    comic = create(store)
    payload = c.ApplyInput(comic_id=comic.id, expected_version=1, operation=page())
    store.write("project", "apply", payload, "write")
    with sqlite3.connect(store.path) as db:
        db.execute(sql)
    with pytest.raises(s.ComicError):
        store.reconcile("project", "apply", payload, "write")


def test_actual_tool_runtime_scope_and_reconcile(store):
    registry = ToolRegistry()
    for tool in t.build_tools(store):
        registry.register(tool)
    runtime = ToolRuntime(registry)
    scope = ResourceScopeRef(kind=c.LIBRARY_KIND, id="project", version=1)
    created = runtime.invoke(tool_name="comic_create", raw_input={"title": "Tool comic"}, request=None,
        idempotency_key="tool-create", invocation_id="tool-create", scope_refs=(scope,), resources={scope.canonical(): store.resolve_library(scope)})
    assert created.status == "success", created.error
    identity = created.output["comic"]["id"]
    scope = ResourceScopeRef(kind=c.DOCUMENT_KIND, id=identity, version=1)
    arguments = dict(tool_name="page_create", raw_input={"comic_id": identity, "expected_version": 1, "operation": page()}, request=None,
        idempotency_key="tool-page", invocation_id="tool-page", scope_refs=(scope,), resources={scope.canonical(): store.resolve(scope)})
    edited = runtime.invoke(**arguments)
    assert edited.status == "success", edited.error
    assert runtime.reconcile(**arguments).output == edited.output
    arguments.update(invocation_id="unauthorized", idempotency_key="unauthorized", scope_refs=(), resources={})
    assert runtime.invoke(**arguments).status == "failed"


def test_producer_bound_immutable_representation_and_safe_export(store):
    first = create(store)
    comic = edit(store, first, page(), "page-write")
    comic = edit(store, comic, {"kind": "caption_create", "panel_id": "page-1.panel", "caption": {"id": "caption", "text": "</script><script>alert(1)</script>"}}, "caption-write")
    scope = ResourceScopeRef(kind=c.DOCUMENT_KIND, id=comic.id, version=comic.version - 1)
    draft = t.artifact(comic, scope)
    artifact = Artifact(id="artifact", session_id="session", run_id="run", provenance={"tool_invocation_id": "caption-write"},
        **draft.model_dump(exclude={"key", "select_if_none", "payload_draft_refs", "visibility"}))
    provider = r.ComicRepresentation(store)
    context = ArtifactRepresentationContext(artifact_loader=lambda _: None)
    edit(store, comic, page("new-page"))
    result = provider.execute(artifact, ArtifactRepresentationRequest(operation="pages"), context)
    assert result.payload["total"] == 1 and result.source_version == "3"
    export = provider.execute(artifact, ArtifactRepresentationRequest(operation="export_html"), context)
    content = b"".join(export.chunks).decode()
    assert "\\u003c/script>" in content and content.count("<script>") == 1
    with pytest.raises(Exception):
        provider.execute(artifact.model_copy(update={"provenance": {"tool_invocation_id": "page-write"}}), ArtifactRepresentationRequest(operation="summary"), context)
    with pytest.raises(Exception):
        provider.execute(artifact, ArtifactRepresentationRequest(operation="pages", parameters={"comic_id": "forged"}), context)


def test_signed_complete_payload_activation_and_cleanup(tmp_path):
    key = ed25519.Ed25519PrivateKey.from_private_bytes(hashlib.sha256(b"Comic author test publisher").digest())
    package = build_dlc_package_from_source(SOURCE, private_key=key)
    archive = tmp_path / "comic.dbfox-dlc"
    archive.write_bytes(package.archive_bytes)
    service = DlcPackageService(tmp_path / "runtime")
    service.trust_publisher_from_file(archive, expected_package_digest=package.package_digest, expected_publisher_key_id=package.publisher_fingerprint)
    service.install_from_file(archive)
    service.set_desired_enabled(c.OWNER, True)
    compiler = ContributionCompiler(service.storage_root)
    active = compiler.compile(built_ins=BuiltinContributionSet())
    assert active.activation_failures == ()
    assert len(active.tools) == 20
    assert len(active.operations) == 8
    service.set_desired_enabled(c.OWNER, False)
    disabled = compiler.compile(built_ins=BuiltinContributionSet())
    assert disabled.tools == () and disabled.operations == () and disabled.artifact_representations == ()
    service.set_desired_enabled(c.OWNER, True)
    assert compiler.compile(built_ins=BuiltinContributionSet()).activation_failures == ()
