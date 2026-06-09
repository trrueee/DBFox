from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from engine.evaluation.spider.spider_loader import SpiderExample, load_spider_examples


def _make_spider_root(base: Path, items: list[dict]) -> Path:
    """Create a minimal Spider dataset on disk."""
    dev = base / "dev.json"
    dev.write_text(json.dumps(items), encoding="utf-8")
    return base


class TestLoadSpiderExamples:
    def test_loads_dev_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_spider_root(root, [
                {"db_id": "school", "question": "How many students?", "query": "SELECT COUNT(*) FROM students"},
            ])
            examples = load_spider_examples(root)
            assert len(examples) == 1
            assert examples[0].db_id == "school"
            assert examples[0].question == "How many students?"
            assert examples[0].gold_sql == "SELECT COUNT(*) FROM students"

    def test_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_spider_root(root, [
                {"db_id": "a", "question": "q1", "query": "SELECT 1"},
                {"db_id": "b", "question": "q2", "query": "SELECT 2"},
                {"db_id": "c", "question": "q3", "query": "SELECT 3"},
            ])
            examples = load_spider_examples(root, limit=2)
            assert len(examples) == 2

    def test_db_id_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_spider_root(root, [
                {"db_id": "a", "question": "q1", "query": "SELECT 1"},
                {"db_id": "b", "question": "q2", "query": "SELECT 2"},
            ])
            examples = load_spider_examples(root, db_ids={"b"})
            assert len(examples) == 1
            assert examples[0].db_id == "b"

    def test_db_path_construction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_spider_root(root, [{"db_id": "concert_singer", "question": "q", "query": "SELECT 1"}])
            examples = load_spider_examples(root)
            expected = root / "database" / "concert_singer" / "concert_singer.sqlite"
            assert examples[0].db_path == expected

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_spider_examples("/nonexistent/path")

    def test_split_param(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            train = root / "train_spider.json"
            train.write_text(json.dumps([
                {"db_id": "x", "question": "q", "query": "SELECT 1"},
            ]), encoding="utf-8")
            examples = load_spider_examples(root, split="train_spider")
            assert len(examples) == 1

    def test_skips_non_dict_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_spider_root(root, [
                "not_a_dict",
                {"db_id": "x", "question": "q", "query": "SELECT 1"},
            ])
            examples = load_spider_examples(root)
            assert len(examples) == 1

    def test_difficulty_field(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_spider_root(root, [
                {"db_id": "x", "question": "q", "query": "SELECT 1", "difficulty": "hard"},
            ])
            examples = load_spider_examples(root)
            assert examples[0].difficulty == "hard"

    def test_frozen_dataclass(self) -> None:
        ex = SpiderExample(db_id="x", question="q", gold_sql="SELECT 1", db_path=Path("/tmp"))
        with pytest.raises(Exception):
            ex.db_id = "y"  # type: ignore[misc]

    def test_tiny_fixture_loads(self) -> None:
        fixture_root = Path("engine/tests/fixtures/spider_tiny")
        if not fixture_root.exists():
            pytest.skip("Spider tiny fixture not found")
        examples = load_spider_examples(fixture_root)
        assert len(examples) == 5
        assert examples[0].db_id == "tiny_school"
        assert examples[0].db_path.name == "tiny_school.sqlite"
        assert all(ex.db_path.parent.name == "tiny_school" for ex in examples)
