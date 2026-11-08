"""dbfox.story DLC backend: store semantics and operation surface."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

STORY_ROOT = Path(__file__).resolve().parents[3] / "dlcs" / "dbfox.story"
if str(STORY_ROOT) not in sys.path:
    sys.path.insert(0, str(STORY_ROOT))

from backend import contributions, store as story_store_module  # noqa: E402
from backend.store import ChapterConflictError, StoryStateStore  # noqa: E402
from backend.consistency import StoryChapterConsistencyConstraint  # noqa: E402


@pytest.fixture()
def store() -> StoryStateStore:
    return StoryStateStore(Path(tempfile.mkdtemp()))


def _seed(store: StoryStateStore, project_id: str = "p1") -> None:
    store.ensure_world(project_id, "测试世界")
    store.create_entity(project_id, kind="character", name="林晚", summary="主角")
    store.create_entity(project_id, kind="character", name="沈青梧", summary="守墓人")
    store.create_entity(project_id, kind="scene", name="旧宅", summary="第一章")


def test_world_is_singleton_per_project_and_default_resource(store: StoryStateStore) -> None:
    first = store.ensure_world("p1", "测试世界")
    second = store.ensure_world("p1", "改名也不会新建")
    assert first.id == second.id
    resources = store.list_resources("p1")
    assert len(resources) == 1
    assert resources[0].kind == "dbfox.story.world"
    assert resources[0].is_default is True
    assert store.list_resources("other") == ()


def test_world_lookup_has_a_valid_empty_and_populated_operation_contract(store: StoryStateStore) -> None:
    operations = []
    contributions._register_operations(SimpleNamespace(operations=SimpleNamespace(register=operations.append)), store)
    operation = next(spec for spec in operations if spec.name == "worlds.get")
    context = SimpleNamespace(project_id="new-project")

    empty = operation.output_model.model_validate(operation.handler(operation.input_model(), context))
    assert empty.model_dump(mode="json") == {"world": None}

    created = store.ensure_world("new-project", "雨夜修表铺")
    populated = operation.output_model.model_validate(operation.handler(operation.input_model(), context))
    assert populated.world == created


def test_propose_creates_pending_edges_and_reports_unknown_names(
    store: StoryStateStore,
) -> None:
    _seed(store)
    created, unknown = store.propose_relations(
        "p1",
        [
            {"from_name": "沈青梧", "to_name": "林晚", "kind": "庇护", "reason": "受托"},
            {"from_name": "不存在", "to_name": "林晚", "kind": "宿敌", "reason": ""},
        ],
    )
    assert len(created) == 1
    assert created[0].status == "pending"
    assert unknown == ("不存在",)
    edges = store.list_edges("p1", status="pending")
    assert [(edge.from_name, edge.kind, edge.to_name) for edge in edges] == [
        ("沈青梧", "庇护", "林晚")
    ]


def test_duplicate_pending_or_confirmed_proposals_are_skipped(
    store: StoryStateStore,
) -> None:
    _seed(store)
    first_batch, _ = store.propose_relations(
        "p1", [{"from_name": "林晚", "to_name": "沈青梧", "kind": "怀疑", "reason": ""}]
    )
    assert len(first_batch) == 1
    second_batch, _ = store.propose_relations(
        "p1", [{"from_name": "林晚", "to_name": "沈青梧", "kind": "怀疑", "reason": ""}]
    )
    # Duplicate pending triple is skipped, not double-created.
    assert len(second_batch) == 0
    store.decide_edge("p1", first_batch[0].id, "confirmed")
    third_batch, _ = store.propose_relations(
        "p1", [{"from_name": "林晚", "to_name": "沈青梧", "kind": "怀疑", "reason": ""}]
    )
    # Confirmed triple also blocks a new pending duplicate.
    assert len(third_batch) == 0


def test_graph_facts_expose_confirmed_only(store: StoryStateStore) -> None:
    _seed(store)
    created, _ = store.propose_relations(
        "p1",
        [
            {"from_name": "沈青梧", "to_name": "林晚", "kind": "庇护", "reason": "受托"},
            {"from_name": "林晚", "to_name": "沈青梧", "kind": "怀疑", "reason": "预感"},
        ],
    )
    store.decide_edge("p1", created[0].id, "confirmed")
    store.decide_edge("p1", created[1].id, "rejected")

    entities, relations = store.graph_facts("p1")
    assert [entity["name"] for entity in entities] == ["林晚", "沈青梧", "旧宅"]
    assert [(rel["from"], rel["kind"], rel["to"]) for rel in relations] == [
        ("沈青梧", "庇护", "林晚")
    ]


def test_revisions_are_immutable_and_count_confirmed_edges(
    store: StoryStateStore,
) -> None:
    _seed(store)
    created, _ = store.propose_relations(
        "p1", [{"from_name": "沈青梧", "to_name": "林晚", "kind": "庇护", "reason": ""}]
    )
    store.decide_edge("p1", created[0].id, "confirmed")
    revision, count = store.commit_revision("p1", "首修订")
    assert revision.seq == 1
    assert count == 1

    # A confirmed-then-revised edge is frozen: deciding it again is rejected.
    with pytest.raises(ValueError):
        store.decide_edge("p1", created[0].id, "rejected")

    # New confirmations land in the NEXT revision, never retroactively.
    more, _ = store.propose_relations(
        "p1", [{"from_name": "林晚", "to_name": "沈青梧", "kind": "怀疑", "reason": ""}]
    )
    store.decide_edge("p1", more[0].id, "confirmed")
    revision2, count2 = store.commit_revision("p1", "第二次")
    assert (revision2.seq, count2) == (2, 1)
    revisions = store.list_revisions("p1")
    assert [(item.seq, item.confirmed_count) for item in revisions] == [(1, 1), (2, 1)]


def test_chapters_use_markdown_files_and_append_versions(store: StoryStateStore) -> None:
    store.ensure_world("p1", "测试世界")
    chapter = store.create_chapter(
        "p1", title="第一章", content="开端", author="author"
    )
    chapter_path = store.root / chapter.content_path
    assert chapter_path.suffix == ".md"
    assert chapter_path.read_text(encoding="utf-8") == "开端"
    appended = store.append_chapter(
        "p1",
        chapter.id,
        content="发展",
        author="ai",
        expected_sha256=chapter.content_sha256,
    )
    assert appended.content == "开端\n\n发展"
    assert appended.content_sha256 != chapter.content_sha256
    with store._connect() as connection:
        current = connection.execute(
            "SELECT content, content_path FROM chapters WHERE id = ?", (chapter.id,)
        ).fetchone()
        versions = connection.execute(
            "SELECT author, content FROM chapter_versions WHERE chapter_id = ? ORDER BY seq",
            (chapter.id,),
        ).fetchall()
    assert current["content"] == ""
    assert current["content_path"] == chapter.content_path
    assert [(row["author"], row["content"]) for row in versions] == [
        ("author", "开端"),
        ("ai", "开端\n\n发展"),
    ]
    assert store.delete_chapter("p1", chapter.id) is True
    assert not chapter_path.exists()


def test_chapter_external_change_is_reconciled_as_an_immutable_version(
    store: StoryStateStore,
) -> None:
    store.ensure_world("p1", "测试世界")
    chapter = store.create_chapter(
        "p1", title="第一章", content="已登记正文", author="author"
    )
    chapter_path = store.root / chapter.content_path
    chapter_path.write_text("外部恢复正文", encoding="utf-8")

    reconciled = store.get_chapter("p1", chapter.id)
    versions = store.list_chapter_versions("p1", chapter.id)

    assert reconciled.content == "外部恢复正文"
    assert reconciled.content_sha256 != chapter.content_sha256
    assert [(item.seq, item.author) for item in versions] == [
        (2, "recovery"),
        (1, "author"),
    ]


def test_chapter_reconciliation_rejects_oversized_or_escaping_files(
    store: StoryStateStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store.ensure_world("p1", "测试世界")
    chapter = store.create_chapter(
        "p1", title="第一章", content="已登记正文", author="author"
    )
    chapter_path = store.root / chapter.content_path
    monkeypatch.setattr(story_store_module, "MAX_CHAPTER_CONTENT_BYTES", 16)
    chapter_path.write_text("x" * 17, encoding="utf-8")
    with pytest.raises(ValueError, match="字节上限"):
        store.get_chapter("p1", chapter.id)

    with store._connect() as connection, connection:
        connection.execute(
            "UPDATE chapters SET content_path = '../../outside.md' WHERE id = ?",
            (chapter.id,),
        )
    with pytest.raises(ValueError, match="越出故事目录"):
        store.get_chapter("p1", chapter.id)


def test_story_store_repairs_legacy_duplicate_version_sequences(
    store: StoryStateStore,
) -> None:
    store.ensure_world("p1", "测试世界")
    chapter = store.create_chapter(
        "p1", title="第一章", content="版本一", author="author"
    )
    with store._connect() as connection, connection:
        connection.execute("DROP INDEX idx_chapter_versions_seq")
        connection.execute(
            "INSERT INTO chapter_versions"
            " (id, chapter_id, seq, title, content, content_sha256, author, created_at)"
            " SELECT 'legacy-duplicate', chapter_id, seq, title, content,"
            " content_sha256, 'legacy', created_at FROM chapter_versions"
            " WHERE chapter_id = ?",
            (chapter.id,),
        )

    reopened = StoryStateStore(store.root.parent)
    assert [item.seq for item in reopened.list_chapter_versions("p1", chapter.id)] == [
        2,
        1,
    ]


def test_chapter_updates_use_compare_and_swap_and_versions_can_be_restored(
    store: StoryStateStore,
) -> None:
    store.ensure_world("p1", "测试世界")
    chapter = store.create_chapter(
        "p1", title="第一章", content="版本一", author="author"
    )
    updated = store.update_chapter(
        "p1",
        chapter.id,
        title="第一章",
        content="版本二",
        author="author",
        expected_sha256=chapter.content_sha256,
    )
    with pytest.raises(ChapterConflictError, match="重新读取"):
        store.update_chapter(
            "p1",
            chapter.id,
            title="过期覆盖",
            content="不应写入",
            author="author",
            expected_sha256=chapter.content_sha256,
        )

    original = store.list_chapter_versions("p1", chapter.id)[-1]
    restored = store.restore_chapter_version(
        "p1",
        chapter.id,
        original.id,
        expected_sha256=updated.content_sha256,
        author="author",
    )
    assert restored.content == "版本一"
    assert [item.seq for item in store.list_chapter_versions("p1", chapter.id)] == [
        3,
        2,
        1,
    ]


def test_story_completion_requires_graph_checks_before_and_after_write() -> None:
    constraint = StoryChapterConsistencyConstraint()
    graph_before = SimpleNamespace(
        status="succeeded",
        sequence=1,
        capabilities=("dbfox.story.graph_check",),
        facts={"world_generation": 3},
    )
    write = SimpleNamespace(
        status="succeeded",
        sequence=2,
        capabilities=("dbfox.story.chapter_write",),
        facts={"chapter": {"checked_world_generation": 3}},
    )
    missing_after = constraint.evaluate(
        context=SimpleNamespace(observations=[graph_before, write]),
        model_result=None,
    )
    assert missing_after.kind == "missing"
    graph_after_drift = SimpleNamespace(
        status="succeeded",
        sequence=3,
        capabilities=("dbfox.story.graph_check",),
        facts={"world_generation": 4},
    )
    drifted = constraint.evaluate(
        context=SimpleNamespace(observations=[graph_before, write, graph_after_drift]),
        model_result=None,
    )
    assert drifted.kind == "missing"
    graph_after = SimpleNamespace(
        status="succeeded",
        sequence=3,
        capabilities=("dbfox.story.graph_check",),
        facts={"world_generation": 3},
    )
    complete = constraint.evaluate(
        context=SimpleNamespace(observations=[graph_before, write, graph_after]),
        model_result=None,
    )
    assert complete.kind == "pass"


class _FakeResources:
    def __init__(self) -> None:
        self.providers: list[object] = []
        self.resolvers: dict[str, object] = {}

    def register_provider(self, provider) -> None:
        self.providers.append(provider)

    def register_resolver(self, kind, resolver) -> None:
        self.resolvers[kind] = resolver


class _FakeOperations:
    def __init__(self) -> None:
        self.specs: dict[str, object] = {}

    def register(self, spec) -> None:
        self.specs[spec.name] = spec


class _FakeTools:
    def __init__(self) -> None:
        self.registered: list[object] = []

    def register(self, tool) -> None:
        self.registered.append(tool)


class _FakeCompletion:
    def __init__(self) -> None:
        self.constraints: list[object] = []

    def register_constraint(self, constraint) -> None:
        self.constraints.append(constraint)


class _FakeRuntimeInfo:
    data_path = Path(tempfile.mkdtemp())


class _FakeHost:
    resources = _FakeResources()
    operations = _FakeOperations()
    tools = _FakeTools()
    completion = _FakeCompletion()
    runtime_info = _FakeRuntimeInfo()
    agent_guidance = _FakeTools()


class _FakeContext:
    project_id = "p1"
    dlc_id = "dbfox.story"
    operation_name = ""
    action_runs = None


def test_operation_surface_covers_world_entities_relations_revisions() -> None:
    host = _FakeHost()
    contributions.register(host)

    expected = {
        "worlds.ensure", "worlds.get",
        "entities.list", "entities.create", "entities.update", "entities.delete",
        "relations.list", "relations.propose", "relations.decide",
        "relations.decide_batch",
        "revisions.commit", "revisions.list",
        "chapters.list", "chapters.read", "chapters.create", "chapters.update",
        "chapters.append", "chapters.delete", "chapters.move",
        "chapter_versions.list", "chapter_versions.read", "chapter_versions.restore",
    }
    assert expected <= set(host.operations.specs)
    tool_names = {tool.name for tool in host.tools.registered}
    assert {"story_graph_query", "story_propose_relations", "story_revisions"} <= tool_names
    assert "story_append_chapter" in tool_names
    assert len(host.completion.constraints) == 1
    chapter_list_tool = next(
        tool for tool in host.tools.registered if tool.name == "story_chapters_list"
    )
    item_schema = chapter_list_tool.output_model.model_json_schema()["$defs"]["ChapterCatalogItem"]
    assert "content" not in item_schema["properties"]
    graph_tool = next(tool for tool in host.tools.registered if tool.name == "story_graph_query")
    projection = graph_tool.project_observation(
        status="success",
        output={"world_generation": 1, "entities": [], "relations": []},
        artifacts=[],
    )
    assert projection.facts["world_generation"] == 1

    context = _FakeContext()
    host.operations.specs["worlds.ensure"].handler(type("I", (), {"title": None})(), context)
    created_chapter = host.operations.specs["chapters.create"].handler(
        type("I", (), {"title": "第一章", "content": "正文"})(), context
    )
    catalog = host.operations.specs["chapters.list"].handler(object(), context)
    assert catalog.chapters[0].model_dump() == {
        "id": created_chapter.id,
        "seq": 1,
        "title": "第一章",
        "updated_at": created_chapter.updated_at,
    }
    read_chapter = host.operations.specs["chapters.read"].handler(
        type("I", (), {"chapter_id": created_chapter.id})(), context
    )
    assert read_chapter.content == "正文"
    host.operations.specs["entities.create"].handler(
        type("I", (), {"kind": "character", "name": "林晚", "summary": ""})(), context
    )
    host.operations.specs["entities.create"].handler(
        type("I", (), {"kind": "character", "name": "沈青梧", "summary": ""})(), context
    )
    proposed = host.operations.specs["relations.propose"].handler(
        host.operations.specs["relations.propose"].input_model(relations=(
            {"from_name": "沈青梧", "to_name": "林晚", "kind": "庇护", "reason": ""},
        )), context
    )
    decided = host.operations.specs["relations.decide"].handler(
        type("I", (), {"edge_id": proposed.edges[0].id, "decision": "confirmed"})(), context
    )
    assert decided.edges[0].status == "confirmed"
    committed = host.operations.specs["revisions.commit"].handler(
        type("I", (), {"note": "首修订"})(), context
    )
    assert committed.confirmed_count == 1
