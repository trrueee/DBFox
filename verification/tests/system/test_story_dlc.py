"""dbfox.story DLC backend: store semantics and operation surface."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

STORY_ROOT = Path(__file__).resolve().parents[3] / "dlcs" / "dbfox.story"
if str(STORY_ROOT) not in sys.path:
    sys.path.insert(0, str(STORY_ROOT))

from backend import contributions, store as story_store_module  # noqa: E402
from backend.store import StoryStateStore  # noqa: E402


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


class _FakeRuntimeInfo:
    data_path = Path(tempfile.mkdtemp())


class _FakeHost:
    resources = _FakeResources()
    operations = _FakeOperations()
    tools = _FakeTools()
    runtime_info = _FakeRuntimeInfo()


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
    }
    assert expected <= set(host.operations.specs)
    tool_names = {tool.name for tool in host.tools.registered}
    assert {"story_graph_query", "story_propose_relations", "story_revisions"} <= tool_names

    context = _FakeContext()
    host.operations.specs["worlds.ensure"].handler(type("I", (), {"title": None})(), context)
    host.operations.specs["entities.create"].handler(
        type("I", (), {"kind": "character", "name": "林晚", "summary": ""})(), context
    )
    host.operations.specs["entities.create"].handler(
        type("I", (), {"kind": "character", "name": "沈青梧", "summary": ""})(), context
    )
    proposed = host.operations.specs["relations.propose"].handler(
        type("I", (), {"relations": (
            {"from_name": "沈青梧", "to_name": "林晚", "kind": "庇护", "reason": ""},
        )})(), context
    )
    decided = host.operations.specs["relations.decide"].handler(
        type("I", (), {"edge_id": proposed.edges[0].id, "decision": "confirmed"})(), context
    )
    assert decided.edges[0].status == "confirmed"
    committed = host.operations.specs["revisions.commit"].handler(
        type("I", (), {"note": "首修订"})(), context
    )
    assert committed.confirmed_count == 1
