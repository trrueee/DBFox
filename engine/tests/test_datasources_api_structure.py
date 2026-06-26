from __future__ import annotations

import importlib


def test_datasources_api_is_split_into_focused_route_modules() -> None:
    datasources = importlib.import_module("engine.api.datasources")

    assert hasattr(datasources, "__path__")
    for module_name in ("crud", "health", "schema", "metadata", "common"):
        module = importlib.import_module(f"engine.api.datasources.{module_name}")
        assert module is not None
