"""Attack the actual materialized native schema, not a hand-written approximation."""
from __future__ import annotations

from uuid import uuid4

import pytest

from dbfox_dlc_api import ResourceScopeRef, ToolKey
from engine.runtime_composition import build_attempt_resource_resolver
from engine.tools.materialization import materialize_tools
from engine.tools.runtime import ToolRuntime
from verification.bench.capabilities.dbfox_shader.runtime import ShaderRuntime


@pytest.mark.parametrize("case", ["inspect", "preview-set", "uniform-update"])
def test_all_required_native_nullable_fields_are_accepted_by_the_same_runtime(tmp_path, case):
    with ShaderRuntime(tmp_path) as runtime:
        project = str(uuid4())
        first = runtime.operation(project, "documents.create", {"title": "Strict native schema",
            "expected_generation": 0, "request_id": str(uuid4())})
        identity = first["document"]["id"]
        version = 1
        if case == "inspect":
            name, minimal = "shader_inspect", {"section": "documents"}
        elif case == "preview-set":
            name, minimal = "shader_modify", {"document_id": identity, "expected_version": 1,
                "operations": [{"kind": "preview_set", "time_seconds": 2.5}]}
        else:
            added = runtime.operation(project, "documents.apply", {"document_id": identity, "expected_version": 1,
                "request_id": str(uuid4()), "operations": [{"kind": "uniform_create", "ref": "strength",
                    "pass_id": {"id": first["created_refs"]["pass"]}, "name": "strength", "type": "float", "value": 0.25}]})
            version = 2
            name, minimal = "shader_modify", {"document_id": identity, "expected_version": 2,
                "operations": [{"kind": "uniform_update", "uniform_id": {"id": added["created_refs"]["strength"]}, "value": 0.75}]}
        wire = runtime.registry.provider_name_for_key(ToolKey(owner_id="dbfox.shader", local_name=name))
        tool = runtime.registry.require(wire)
        # The domain itself supplies omitted-field defaults; retain all explicit
        # nulls required by the official strict materialization sent to Providers.
        full = tool.input_model.model_validate(minimal).model_dump(mode="json")
        materialized = materialize_tools(runtime.registry, execution_mode="agent",
            available_resource_kinds={"dbfox.shader.studio"}).require(wire)
        native = materialized.provider_schema()
        assert native["strict"] is True
        root_schema = native["parameters"]
        assert set(root_schema["required"]) == set(full)
        if case == "inspect":
            node, sent = root_schema, full
        else:
            node = root_schema["$defs"]["PreviewSet" if case == "preview-set" else "UniformUpdate"]
            sent = full["operations"][0]
            assert node["properties"]["kind"]["const"] == sent["kind"]
        assert set(node["required"]) == set(sent)
        explicit_nulls = [key for key, value in sent.items() if value is None]
        assert explicit_nulls
        for key in explicit_nulls:
            assert {"type": "null"} in node["properties"][key]["anyOf"]
        scope = ResourceScopeRef(kind="dbfox.shader.studio", id=project, version=version)
        resources = build_attempt_resource_resolver(snapshot=runtime.snapshot).resolve((scope,))
        invocation = str(uuid4())
        result = ToolRuntime(runtime.registry).invoke(tool_name=wire, raw_input=full, request=None,
            invocation_id=invocation, idempotency_key=invocation, scope_refs=(scope,), resources=resources)
        assert result.status == "success", result.error


@pytest.mark.parametrize("fault", ["required-null", "number-null", "bool-number", "unknown-null", "selector-null"])
def test_native_nullable_repair_does_not_accept_invalid_required_data(tmp_path, fault):
    with ShaderRuntime(tmp_path) as runtime:
        spec = runtime.snapshot.get_operation("dbfox.shader", "documents.apply").spec
        value = {"document_id": str(uuid4()), "expected_version": 1, "request_id": str(uuid4()),
            "operations": [{"kind": "preview_set", "width": 2}]}
        if fault == "required-null":
            value["document_id"] = None
        elif fault == "number-null":
            value["expected_version"] = None
        elif fault == "bool-number":
            value["operations"][0]["width"] = True
        elif fault == "unknown-null":
            value["operations"][0]["unknown"] = None
        else:
            value["operations"] = [{"kind": "stage_replace", "stage_id": {"id": None}, "source": ""}]
        with pytest.raises(ValueError):
            spec.input_model.model_validate(value)
