"""Bounded validation for Vega-Lite and restricted Vega documents."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Iterable
from typing import Any

from dbfox_dlc_api import DataFrameField, ToolInputError

from .contracts import ChartBlock, NAMED_DATASET, TableBlock, VisualizationDocument


_MAX_SPEC_BYTES = 128 * 1024
_MAX_SPEC_DEPTH = 24
_MAX_COLLECTION_ITEMS = 512
_MAX_STRING_CHARS = 4_096
_FORBIDDEN_KEYS = frozenset({"url", "href", "datasets", "values", "loader"})
_FORBIDDEN_EXPRESSION_TOKENS = re.compile(
    r"(?:https?://|fetch\s*\(|XMLHttpRequest|WebSocket|globalThis|window\.|document\.|"
    r"Function\s*\(|eval\s*\(|constructor|__proto__|prototype)",
    re.IGNORECASE,
)
_VEGA_LITE_MARKS = frozenset(
    {
        "arc", "area", "bar", "boxplot", "circle", "errorband", "errorbar",
        "line", "point", "rect", "rule", "square", "text", "tick", "trail",
    }
)
_VEGA_MARKS = frozenset(
    {"arc", "area", "group", "line", "rect", "rule", "shape", "symbol", "text", "trail"}
)
_VEGA_LITE_TRANSFORMS = frozenset(
    {"aggregate", "bin", "calculate", "density", "extent", "filter", "flatten", "fold", "impute", "joinaggregate", "loess", "pivot", "quantile", "regression", "sample", "stack", "timeUnit", "window"}
)
_VEGA_TRANSFORMS = frozenset(
    {"aggregate", "bin", "collect", "countpattern", "extent", "fold", "formula", "identifier", "joinaggregate", "project", "sample", "stack", "window"}
)


def validate_visualization_document(
    document: VisualizationDocument,
    fields: Iterable[DataFrameField],
) -> None:
    field_by_name = {field.name: field for field in fields}
    if not field_by_name:
        raise ToolInputError("Visualization data must expose at least one field.")
    for block in document.blocks:
        if block.kind == "metric" and block.field is not None:
            _require_field(block.field, field_by_name)
            if block.aggregation in {"sum", "mean", "median"}:
                _require_numeric(block.field, field_by_name)
        elif isinstance(block, ChartBlock):
            _validate_chart(block, field_by_name)
        elif isinstance(block, TableBlock):
            for field_name in block.fields:
                _require_field(field_name, field_by_name)


def _validate_chart(block: ChartBlock, fields: dict[str, DataFrameField]) -> None:
    try:
        encoded = json.dumps(
            block.spec,
            ensure_ascii=False,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ToolInputError("Visualization specs must be finite JSON values.") from exc
    if len(encoded.encode("utf-8")) > _MAX_SPEC_BYTES:
        raise ToolInputError("A visualization spec exceeds the 128 KiB safety budget.")
    _walk(block.spec, depth=0)
    if block.grammar == "vega-lite":
        _validate_vega_lite(block.spec, fields)
    else:
        _validate_vega(block.spec)
    derived = _derived_fields(block.spec)
    for field_name, channel_type, aggregate in _field_references(block.spec):
        if field_name not in fields and field_name not in derived:
            raise ToolInputError(
                f"Visualization field {field_name!r} is not provided by the source."
            )
        if field_name in fields:
            if channel_type == "quantitative" or aggregate in {
                "sum", "mean", "median", "variance", "stdev", "q1", "q3",
            }:
                _require_numeric(field_name, fields)
            if channel_type == "temporal" and fields[field_name].type not in {
                "datetime", "date", "time", "string",
            }:
                raise ToolInputError(
                    f"Visualization field {field_name!r} is not temporal."
                )


def _walk(value: Any, *, depth: int) -> None:
    if depth > _MAX_SPEC_DEPTH:
        raise ToolInputError("Visualization spec nesting exceeds the safety budget.")
    if isinstance(value, dict):
        if len(value) > _MAX_COLLECTION_ITEMS:
            raise ToolInputError("Visualization spec objects exceed the safety budget.")
        for raw_key, item in value.items():
            key = str(raw_key)
            if len(key) > 256 or key in _FORBIDDEN_KEYS:
                raise ToolInputError(
                    f"Visualization spec property {key!r} is not permitted."
                )
            if key in {"calculate", "expr", "filter", "update", "test"} and isinstance(item, str):
                _validate_expression(item)
            _walk(item, depth=depth + 1)
    elif isinstance(value, list):
        if len(value) > _MAX_COLLECTION_ITEMS:
            raise ToolInputError("Visualization spec arrays exceed the safety budget.")
        for item in value:
            _walk(item, depth=depth + 1)
    elif isinstance(value, str) and len(value) > _MAX_STRING_CHARS:
        raise ToolInputError("Visualization spec strings exceed the safety budget.")


def _validate_expression(expression: str) -> None:
    if len(expression) > 512 or _FORBIDDEN_EXPRESSION_TOKENS.search(expression):
        raise ToolInputError("Visualization expressions contain a forbidden operation.")


def _validate_vega_lite(
    spec: dict[str, Any],
    fields: dict[str, DataFrameField],
) -> None:
    data = spec.get("data")
    if data != {"name": NAMED_DATASET}:
        raise ToolInputError(
            f"Vega-Lite specs must use the named data source {NAMED_DATASET!r}."
        )
    for mark in _values_for_key(spec, "mark"):
        mark_type = mark if isinstance(mark, str) else mark.get("type") if isinstance(mark, dict) else None
        if mark_type not in _VEGA_LITE_MARKS:
            raise ToolInputError(f"Vega-Lite mark {mark_type!r} is not permitted.")
    for transform in _values_for_key(spec, "transform"):
        if not isinstance(transform, list):
            raise ToolInputError("Vega-Lite transform must be an array.")
        for item in transform:
            if not isinstance(item, dict) or not item:
                raise ToolInputError("Vega-Lite transforms must be objects.")
            transform_type = next(iter(item))
            if transform_type not in _VEGA_LITE_TRANSFORMS:
                raise ToolInputError(
                    f"Vega-Lite transform {transform_type!r} is not permitted."
                )
    _validate_selection_params(spec, fields)


def _validate_vega(spec: dict[str, Any]) -> None:
    data = spec.get("data")
    if not isinstance(data, list) or not any(
        isinstance(item, dict) and item.get("name") == NAMED_DATASET
        for item in data
    ):
        raise ToolInputError(
            f"Vega specs must declare the named data source {NAMED_DATASET!r}."
        )
    for entry in data:
        if not isinstance(entry, dict):
            raise ToolInputError("Vega data declarations must be objects.")
        if entry.get("name") != NAMED_DATASET and entry.get("source") != NAMED_DATASET:
            raise ToolInputError("Derived Vega data must use the authorized named source.")
        transforms = entry.get("transform", [])
        if not isinstance(transforms, list):
            raise ToolInputError("Vega data transforms must be an array.")
        for transform in transforms:
            transform_type = transform.get("type") if isinstance(transform, dict) else None
            if transform_type not in _VEGA_TRANSFORMS:
                raise ToolInputError(f"Vega transform {transform_type!r} is not permitted.")
    for mark in _values_for_key(spec, "marks"):
        if not isinstance(mark, list):
            raise ToolInputError("Vega marks must be an array.")
        for item in mark:
            mark_type = item.get("type") if isinstance(item, dict) else None
            if mark_type not in _VEGA_MARKS:
                raise ToolInputError(f"Vega mark {mark_type!r} is not permitted.")


def _validate_selection_params(
    spec: dict[str, Any],
    fields: dict[str, DataFrameField],
) -> None:
    params = spec.get("params", [])
    if not isinstance(params, list) or len(params) > 16:
        raise ToolInputError("Vega-Lite params must be a bounded array.")
    names: set[str] = set()
    for param in params:
        if not isinstance(param, dict):
            raise ToolInputError("Vega-Lite params must be objects.")
        name = param.get("name")
        if (
            not isinstance(name, str)
            or re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]{0,63}", name) is None
            or name in {"datum", "event", "item", "parent"}
            or name in names
        ):
            raise ToolInputError("Vega-Lite parameter names must be unique safe identifiers.")
        names.add(name)
        select = param.get("select")
        if select is None:
            if any(key not in {"name", "value", "bind"} for key in param):
                raise ToolInputError(
                    "Variable parameters only support name, value, and a safe input binding."
                )
            _validate_input_binding(param.get("bind"))
            continue
        if isinstance(select, str):
            select_type = select
        elif isinstance(select, dict):
            raw_select_type = select.get("type")
            select_type = raw_select_type if isinstance(raw_select_type, str) else ""
        else:
            raise ToolInputError("Vega-Lite selection params are invalid.")
        if select_type not in {"point", "interval"}:
            raise ToolInputError("Only point and interval selections are permitted.")
        if any(key not in {"name", "value", "select", "bind"} for key in param):
            raise ToolInputError(
                "Selection parameters contain unsupported root properties."
            )
        if isinstance(select, dict):
            selected_fields = select.get("fields")
            if selected_fields is not None:
                if (
                    not isinstance(selected_fields, list)
                    or not 1 <= len(selected_fields) <= 64
                    or any(
                        not isinstance(field_name, str) or field_name not in fields
                        for field_name in selected_fields
                    )
                ):
                    raise ToolInputError(
                        "Selection fields must exist in the source DataFrame."
                    )
        binding = param.get("bind")
        if not (binding is None or binding in ("scales", "legend")):
            raise ToolInputError(
                "Selection bindings are limited to scales or legends."
            )
        if binding == "legend" and select_type != "point":
            raise ToolInputError("Legend bindings require a point selection.")
        if binding == "scales" and select_type != "interval":
            raise ToolInputError("Scale bindings require an interval selection.")


def _validate_input_binding(binding: Any) -> None:
    if binding is None:
        return
    if not isinstance(binding, dict):
        raise ToolInputError("Variable parameter bindings must be bounded input objects.")
    input_type = binding.get("input")
    allowed_keys = {
        "checkbox": {"input", "name"},
        "range": {"input", "name", "min", "max", "step"},
        "radio": {"input", "name", "options", "labels"},
        "select": {"input", "name", "options", "labels"},
    }
    if not isinstance(input_type, str):
        raise ToolInputError(
            "Only checkbox, range, radio, and select parameter bindings are permitted."
        )
    permitted = allowed_keys.get(input_type)
    if permitted is None or any(key not in permitted for key in binding):
        raise ToolInputError(
            "Only checkbox, range, radio, and select parameter bindings are permitted."
        )
    label = binding.get("name")
    if label is not None and (not isinstance(label, str) or len(label) > 120):
        raise ToolInputError("Parameter binding labels exceed the safety budget.")
    if input_type == "range":
        numbers = [binding.get(key) for key in ("min", "max", "step")]
        if any(
            value is not None
            and (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not math.isfinite(value)
            )
            for value in numbers
        ):
            raise ToolInputError("Range parameter bounds must be numeric.")
        minimum, maximum, step = numbers
        if minimum is not None and maximum is not None and minimum >= maximum:
            raise ToolInputError("Range parameter minimum must be below its maximum.")
        if step is not None and step <= 0:
            raise ToolInputError("Range parameter step must be positive.")
    if input_type in {"radio", "select"}:
        options = binding.get("options")
        labels = binding.get("labels")
        if not isinstance(options, list) or not 1 <= len(options) <= 50:
            raise ToolInputError("Parameter options must contain 1 to 50 values.")
        if any(
            isinstance(option, (dict, list))
            or (isinstance(option, str) and len(option) > 256)
            or (isinstance(option, float) and not math.isfinite(option))
            for option in options
        ):
            raise ToolInputError("Parameter options must be bounded finite scalar values.")
        if labels is not None and (
            not isinstance(labels, list)
            or len(labels) != len(options)
            or any(not isinstance(label, str) or len(label) > 120 for label in labels)
        ):
            raise ToolInputError("Parameter option labels are invalid.")


def _field_references(value: Any):
    if isinstance(value, dict):
        field = value.get("field")
        if isinstance(field, str):
            yield field, value.get("type"), value.get("aggregate")
        for item in value.values():
            yield from _field_references(item)
    elif isinstance(value, list):
        for item in value:
            yield from _field_references(item)


def _derived_fields(value: Any) -> set[str]:
    result: set[str] = set()
    if isinstance(value, dict):
        alias = value.get("as")
        if isinstance(alias, str):
            result.add(alias)
        elif isinstance(alias, list):
            result.update(item for item in alias if isinstance(item, str))
        for item in value.values():
            result.update(_derived_fields(item))
    elif isinstance(value, list):
        for item in value:
            result.update(_derived_fields(item))
    return result


def _values_for_key(value: Any, key: str):
    if isinstance(value, dict):
        if key in value:
            yield value[key]
        for item in value.values():
            yield from _values_for_key(item, key)
    elif isinstance(value, list):
        for item in value:
            yield from _values_for_key(item, key)


def _require_field(name: str, fields: dict[str, DataFrameField]) -> None:
    if name not in fields:
        raise ToolInputError(f"Visualization field {name!r} is not provided by the source.")


def _require_numeric(name: str, fields: dict[str, DataFrameField]) -> None:
    if fields[name].type not in {"integer", "number"}:
        raise ToolInputError(f"Visualization field {name!r} is not numeric.")
