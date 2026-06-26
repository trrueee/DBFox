from __future__ import annotations

import importlib


def test_test_data_engine_is_split_into_policy_generator_fk_and_insert_modules() -> None:
    test_data = importlib.import_module("engine.test_data")

    assert hasattr(test_data, "__path__")
    for module_name in ("policy", "generator", "fk_resolver", "sqlite_insert_service"):
        module = importlib.import_module(f"engine.test_data.{module_name}")
        assert module is not None
