"""Source-level domain cases, complemented by signed-package conformance."""
import importlib
from pathlib import Path
import sys
from types import ModuleType

import pytest

from dbfox_dlc_api import DataFrameField


def _backend(capability, module):
    name = "_creative_regression_" + capability
    if name not in sys.modules:
        package = ModuleType(name)
        package.__path__ = [str(Path(__file__).resolve().parents[3] / f"dlcs/dbfox.{capability}/backend")]
        sys.modules[name] = package
    return importlib.import_module(name + "." + module)


@pytest.fixture
def story(tmp_path):
    store = _backend("story", "store").StoryStateStore(tmp_path)
    store.ensure_world("project")
    return store


def test_chapter_move_uses_real_neighbor_after_deletion(story):
    chapters = [story.create_chapter("project", title=title, content="body", author="test") for title in ("A", "B", "C")]
    story.delete_chapter("project", chapters[1].id)
    story.move_chapter("project", chapters[2].id, "up")
    assert [chapter.title for chapter in story.list_chapter_catalog("project")] == ["C", "A"]


def test_restart_preserves_evidence_for_external_chapter_recovery(story):
    chapter = story.create_chapter("project", title="chapter", content="original", author="test")
    (story.root / chapter.content_path).write_text("external", encoding="utf-8")
    reopened = type(story)(story.root.parent)
    current = reopened.get_chapter("project", chapter.id)
    versions = reopened.list_chapter_versions("project", chapter.id)
    assert len(versions) == 2
    latest = reopened.get_chapter_version("project", chapter.id, versions[0].id)
    assert current.content == latest.content == "external"
    assert latest.author == "recovery"
    type(story)(story.root.parent).get_chapter("project", chapter.id)
    assert len(reopened.list_chapter_versions("project", chapter.id)) == 2


def test_relation_batch_rolls_back_on_second_invalid_target(story):
    for name in ("A", "B"):
        story.create_entity("project", kind="character", name=name, summary="")
    edges, _ = story.propose_relations("project", [{"from_name": "A", "to_name": "B", "kind": "related"}])
    with pytest.raises(ValueError):
        story.decide_batch("project", [{"edge_id": edges[0].id, "decision": "confirmed"},
                                       {"edge_id": "missing", "decision": "confirmed"}])
    assert story.list_edges("project")[0].status == "pending"


def test_same_name_relation_requires_identity(story):
    story.create_entity("project", kind="character", name="Same", summary="")
    scene = story.create_entity("project", kind="scene", name="Same", summary="")
    other = story.create_entity("project", kind="character", name="Other", summary="")
    relation = {"from_name": "Same", "to_name": "Other", "kind": "related"}
    with pytest.raises(ValueError, match="不唯一|Ambiguous"):
        story.propose_relations("project", [relation])
    assert story.list_edges("project") == ()
    edges, unknown = story.propose_relations("project", [{**relation, "from_id": scene.id, "to_id": other.id}])
    assert not unknown
    with story._connect() as connection:
        row = connection.execute("SELECT from_entity_id FROM relation_edges WHERE id = ?", (edges[0].id,)).fetchone()
        assert row[0] == scene.id


def _score():
    contracts = _backend("music", "contracts")
    return contracts.ScoreDocument(title="synthetic", measure_count=1, notes=(
        contracts.ScoreNote(id="held", measure=1, beat=0, duration=4, pitch=60, hand="right"),
        contracts.ScoreNote(id="overlap", measure=1, beat=1, duration=2, pitch=64, hand="right"),
    ))


def test_inverse_music_edit_survives_legacy_unique_hash_migration(tmp_path):
    store_type = _backend("music", "store").MusicStore
    ops = _backend("music", "score_ops")
    store = store_type(tmp_path)
    first = store.create_score("project", _score(), "initial")
    second = store.commit_revision("project", first.score_id, 1, ops.transpose(first.document, 1), "up")
    with store._connect() as connection, connection:
        connection.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_music_score_revision_hash ON score_revisions(score_id, content_hash)")
        connection.execute("PRAGMA user_version = 3")
    reopened = store_type(tmp_path)
    third = reopened.commit_revision("project", first.score_id, 2, ops.transpose(second.document, -1), "back")
    assert third.revision == 3
    assert third.content_hash == first.content_hash
    assert reopened.get_revision("project", first.score_id, 2).content_hash == second.content_hash
    with pytest.raises(ValueError, match="does not change"):
        reopened.commit_revision("project", first.score_id, 3, third.document, "unchanged")


def test_music_polyphony_counts_sustained_overlap_and_endpoints():
    ops = _backend("music", "score_ops")
    score = _score()
    assert ops.analyze("score", 1, score).maximum_polyphony == 2
    notes = (score.notes[0].model_copy(update={"duration": 1}), score.notes[1])
    touching = score.model_copy(update={"notes": notes})
    assert ops.analyze("score", 1, touching).maximum_polyphony == 1


def test_vega_lite_transform_key_order_does_not_change_validation():
    contracts = _backend("visualization", "contracts")
    validation = _backend("visualization", "validation")
    fields = {"category": DataFrameField(key="category", name="category", type="string", values=[]),
              "value": DataFrameField(key="value", name="value", type="number", values=[])}
    aggregate = [{"op": "sum", "field": "value", "as": "total"}]
    for transform in (dict(aggregate=aggregate, groupby=["category"]), dict(groupby=["category"], aggregate=aggregate)):
        block = contracts.ChartBlock(kind="chart", id="test", spec={"data": {"name": "dbfox_source"},
            "transform": [transform], "mark": "bar", "encoding": {
                "x": {"field": "category", "type": "nominal"}, "y": {"field": "total", "type": "quantitative"}}})
        validation._validate_chart(block, fields)
