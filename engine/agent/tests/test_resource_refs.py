"""Tests for strict typed resource_refs codec."""

from __future__ import annotations

import pytest

from engine.agent.resource_refs import (
    MAX_INPUT_RESOURCE_REFS,
    dump_resource_refs,
    load_resource_refs,
)
from engine.tools.runtime.attempt import ResourceScopeRef


def test_dump_and_load_roundtrip() -> None:
    refs = (
        ResourceScopeRef(kind="database", id="ds-1", version=1),
        ResourceScopeRef(kind="workspace", id="proj-1", version="v1"),
    )
    raw = dump_resource_refs(refs)
    loaded = load_resource_refs(raw)
    assert loaded == refs


def test_dump_at_max_limit_succeeds() -> None:
    refs = tuple(
        ResourceScopeRef(kind="database", id=f"ds-{i}", version=1)
        for i in range(MAX_INPUT_RESOURCE_REFS)
    )
    raw = dump_resource_refs(refs)
    loaded = load_resource_refs(raw)
    assert loaded is not None
    assert len(loaded) == MAX_INPUT_RESOURCE_REFS


def test_dump_exceeding_max_limit_rejected() -> None:
    refs = tuple(
        ResourceScopeRef(kind="database", id=f"ds-{i}", version=1)
        for i in range(MAX_INPUT_RESOURCE_REFS + 1)
    )
    with pytest.raises(ValueError, match="exceeds maximum"):
        dump_resource_refs(refs)


def test_dump_duplicate_canonical_key_rejected() -> None:
    refs = (
        ResourceScopeRef(kind="database", id="ds-1", version=1),
        ResourceScopeRef(kind="database", id="ds-1", version=2),
    )
    with pytest.raises(ValueError, match="duplicate resource ref"):
        dump_resource_refs(refs)


def test_load_null_returns_none() -> None:
    assert load_resource_refs(None) is None


def test_load_empty_list_returns_empty_tuple() -> None:
    assert load_resource_refs("[]") == ()


def test_load_malformed_json_rejected() -> None:
    with pytest.raises(ValueError, match="malformed resource_refs_json"):
        load_resource_refs("{not valid json")


def test_load_non_list_json_rejected() -> None:
    with pytest.raises(ValueError, match="must be a list"):
        load_resource_refs('{"kind": "database", "id": "ds-1"}')

    with pytest.raises(ValueError, match="must be a list"):
        load_resource_refs('"just a string"')

    with pytest.raises(ValueError, match="must be a list"):
        load_resource_refs("123")


def test_load_non_dict_item_rejected() -> None:
    with pytest.raises(ValueError, match="resource ref item must be dict"):
        load_resource_refs('["not-a-dict"]')


def test_load_missing_kind_or_id_rejected() -> None:
    with pytest.raises(ValueError, match="missing kind/id"):
        load_resource_refs('[{"kind": "database"}]')

    with pytest.raises(ValueError, match="missing kind/id"):
        load_resource_refs('[{"id": "ds-1"}]')


def test_load_invalid_extra_field_rejected() -> None:
    with pytest.raises(ValueError):
        load_resource_refs('[{"kind": "database", "id": "ds-1", "unexpected_extra": "bad"}]')


def test_load_exceeding_max_rejected() -> None:
    items = [
        {"kind": "database", "id": f"ds-{i}", "version": 1}
        for i in range(MAX_INPUT_RESOURCE_REFS + 1)
    ]
    import json
    with pytest.raises(ValueError, match="exceeds maximum"):
        load_resource_refs(json.dumps(items))


def test_load_duplicate_key_rejected() -> None:
    items = [
        {"kind": "database", "id": "ds-1", "version": 1},
        {"kind": "database", "id": "ds-1", "version": 2},
    ]
    import json
    with pytest.raises(ValueError, match="duplicate resource ref"):
        load_resource_refs(json.dumps(items))
