# LLM Call Interface Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a unified and explicit LLM call interface so product requests, support/eval runs, E2E tests, and ordinary unit tests do not mix configuration sources.

**Architecture:** Add a small `engine.llm.config` module that owns `LlmConfig` and the only env-backed support resolver. Refactor `engine.llm.factory` so all real client construction goes through `create_chat_model(LlmConfig, LlmCallOptions)`, while product paths resolve config only from request data. Keep compatibility wrappers where needed, but remove hidden env fallback from runtime product code.

**Tech Stack:** Python dataclasses, FastAPI route helpers, pytest, existing LangChain OpenAI-compatible provider wrapper.

---

## File Structure

- Create: `engine/llm/config.py`
  - Define `LlmConfig`, `LlmConfigurationError`, defaults, product resolver, optional product resolver, and support env resolver.
- Modify: `engine/llm/factory.py`
  - Add `LlmCallOptions` and `create_chat_model()`.
  - Make `LLMClientFactory` build through `create_chat_model()`.
  - Keep `get_chat_model()` as explicit-config-only compatibility wrapper.
- Modify: `engine/llm/__init__.py`
  - Export the new config and factory API.
- Modify: `engine/api/agent.py`
  - Validate `/agent/run` and `/agent/run/stream` credentials from request fields only.
- Modify: `engine/agent/graph/context.py`
  - Remove LLM env reads from `GraphRuntimeContext.has_llm_credentials`.
- Modify: `engine/agent/nodes/model_node.py`, `engine/agent/progress/llm_judge.py`, `engine/agent/nodes/turn_node.py`, `engine/agent_core/answer.py`
  - Ensure runtime model creation remains explicit-config-only.
- Modify: `engine/schema_sync.py`, `engine/ai_enrich.py`, `engine/ai_index.py`, `engine/environment/schema_catalog_sync.py`
  - Make product AI enrichment use optional product config only.
- Modify: `engine/tests/conftest.py`
  - Stop globally translating real `QWEN_API_KEY` into `OPENAI_*`.
- Modify: `engine/agent/tests/test_e2e_qwen.py`
  - Build explicit request config from `QWEN_*` without mutating `OPENAI_*`.
- Test: `engine/tests/test_llm_config.py`
  - Cover product/support resolver boundaries and factory delegation.
- Test: `engine/tests/test_agent_llm_boundaries.py`
  - Cover product Agent API credential behavior.
- Test: `engine/tests/test_ai_enrich.py`
  - Cover optional enrichment missing-key behavior.

## Task 1: LLM Config Resolvers

**Files:**
- Create: `engine/llm/config.py`
- Test: `engine/tests/test_llm_config.py`

- [ ] **Step 1: Write failing resolver tests**

Create `engine/tests/test_llm_config.py` with:

```python
from __future__ import annotations

import pytest


def test_product_resolver_ignores_environment(monkeypatch) -> None:
    from engine.llm.config import resolve_product_llm_config

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    config = resolve_product_llm_config(
        api_key=" sk-product ",
        api_base=" https://product.example/v1 ",
        model_name=" gpt-product ",
    )

    assert config.api_key == "sk-product"
    assert config.api_base == "https://product.example/v1"
    assert config.model_name == "gpt-product"
    assert config.source == "product"


def test_product_resolver_requires_request_api_key_even_when_env_exists(monkeypatch) -> None:
    from engine.llm.config import LlmConfigurationError, resolve_product_llm_config

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    with pytest.raises(LlmConfigurationError) as exc_info:
        resolve_product_llm_config(api_key=None, api_base=None, model_name=None)

    assert exc_info.value.code == "NO_LLM_KEY"


def test_optional_product_resolver_returns_none_without_key(monkeypatch) -> None:
    from engine.llm.config import resolve_optional_product_llm_config

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    assert resolve_optional_product_llm_config(
        api_key=None,
        api_base="https://product.example/v1",
        model_name="gpt-product",
    ) is None


def test_support_resolver_reads_env_aliases() -> None:
    from engine.llm.config import resolve_support_llm_config_from_env

    config = resolve_support_llm_config_from_env(environ={
        "QWEN_API_KEY": "sk-qwen",
        "QWEN_API_BASE": "https://dashscope.example/v1",
        "QWEN_MODEL_NAME": "qwen-plus",
    })

    assert config.api_key == "sk-qwen"
    assert config.api_base == "https://dashscope.example/v1"
    assert config.model_name == "qwen-plus"
    assert config.source == "support_env"


def test_support_resolver_prefers_openai_api_base_over_base_url() -> None:
    from engine.llm.config import resolve_support_llm_config_from_env

    config = resolve_support_llm_config_from_env(environ={
        "OPENAI_API_KEY": "sk-openai",
        "OPENAI_API_BASE": "https://api-base.example/v1",
        "OPENAI_BASE_URL": "https://base-url.example/v1",
    })

    assert config.api_base == "https://api-base.example/v1"
```

- [ ] **Step 2: Run resolver tests and verify they fail**

Run:

```bash
pytest engine/tests/test_llm_config.py -q
```

Expected: import failure because `engine.llm.config` does not exist.

- [ ] **Step 3: Implement config module**

Create `engine/llm/config.py`:

```python
from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

DEFAULT_LLM_API_BASE = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL_NAME = "gpt-4o-mini"


class LlmConfigurationError(ValueError):
    def __init__(self, message: str, *, code: str = "LLM_CONFIG_ERROR") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class LlmConfig:
    api_key: str
    api_base: str
    model_name: str
    source: Literal["product", "support_env", "test"] = "product"


def _clean(value: str | None) -> str:
    return str(value or "").strip()


def resolve_product_llm_config(
    *,
    api_key: str | None,
    api_base: str | None,
    model_name: str | None,
) -> LlmConfig:
    key = _clean(api_key)
    if not key:
        raise LlmConfigurationError("请先在设置中配置 LLM API Key。", code="NO_LLM_KEY")
    return LlmConfig(
        api_key=key,
        api_base=_clean(api_base) or DEFAULT_LLM_API_BASE,
        model_name=_clean(model_name) or DEFAULT_LLM_MODEL_NAME,
        source="product",
    )


def resolve_optional_product_llm_config(
    *,
    api_key: str | None,
    api_base: str | None,
    model_name: str | None,
) -> LlmConfig | None:
    if not _clean(api_key):
        return None
    return resolve_product_llm_config(api_key=api_key, api_base=api_base, model_name=model_name)


def resolve_support_llm_config_from_env(
    *,
    require_key: bool = True,
    environ: Mapping[str, str] | None = None,
) -> LlmConfig:
    env = environ if environ is not None else os.environ
    key = _clean(env.get("OPENAI_API_KEY") or env.get("QWEN_API_KEY") or env.get("DBFOX_LLM_API_KEY"))
    if require_key and not key:
        raise LlmConfigurationError("LLM API key is required for support-mode LLM calls.", code="NO_LLM_KEY")
    base = _clean(env.get("OPENAI_API_BASE") or env.get("OPENAI_BASE_URL") or env.get("QWEN_API_BASE"))
    model = _clean(env.get("OPENAI_MODEL_NAME") or env.get("QWEN_MODEL_NAME"))
    return LlmConfig(
        api_key=key,
        api_base=base or DEFAULT_LLM_API_BASE,
        model_name=model or DEFAULT_LLM_MODEL_NAME,
        source="support_env",
    )
```

- [ ] **Step 4: Run resolver tests and verify they pass**

Run:

```bash
pytest engine/tests/test_llm_config.py -q
```

Expected: resolver tests pass.

## Task 2: Unified Factory

**Files:**
- Modify: `engine/llm/factory.py`
- Modify: `engine/llm/__init__.py`
- Test: `engine/tests/test_llm_config.py`

- [ ] **Step 1: Add failing factory tests**

Append to `engine/tests/test_llm_config.py`:

```python
def test_create_chat_model_delegates_to_openai_provider(monkeypatch) -> None:
    from engine.llm.config import LlmConfig
    from engine.llm.factory import LlmCallOptions, create_chat_model
    import engine.llm.factory as factory

    captured: dict[str, object] = {}

    def fake_create_openai_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "create_openai_client", fake_create_openai_client)

    create_chat_model(
        LlmConfig(
            api_key="sk-product",
            api_base="https://product.example/v1",
            model_name="gpt-product",
            source="product",
        ),
        LlmCallOptions(temperature=0.2, max_tokens=123, timeout=9.0),
    )

    assert captured == {
        "model_name": "gpt-product",
        "api_key": "sk-product",
        "api_base": "https://product.example/v1",
        "temperature": 0.2,
        "max_tokens": 123,
        "timeout": 9.0,
    }


def test_get_chat_model_is_explicit_config_only(monkeypatch) -> None:
    import engine.llm.factory as factory

    captured: dict[str, object] = {}

    def fake_create_openai_client(**kwargs: object) -> object:
        captured.update(kwargs)
        return object()

    monkeypatch.setattr(factory, "create_openai_client", fake_create_openai_client)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.setenv("OPENAI_API_BASE", "https://env.example/v1")
    monkeypatch.setenv("OPENAI_MODEL_NAME", "env-model")

    factory.get_chat_model(api_key="sk-product", api_base="https://product.example/v1", model_name="gpt-product")

    assert captured["api_key"] == "sk-product"
    assert captured["api_base"] == "https://product.example/v1"
    assert captured["model_name"] == "gpt-product"
```

- [ ] **Step 2: Run factory tests and verify they fail**

Run:

```bash
pytest engine/tests/test_llm_config.py -q
```

Expected: import failure for `LlmCallOptions` or `create_chat_model`.

- [ ] **Step 3: Refactor factory**

Modify `engine/llm/factory.py` so it imports `LlmConfig`, `DEFAULT_LLM_API_BASE`, and `DEFAULT_LLM_MODEL_NAME`, defines `LlmCallOptions`, and delegates all provider construction through `create_chat_model()`:

```python
@dataclass(frozen=True)
class LlmCallOptions:
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout: float = 120.0


def create_chat_model(
    config: LlmConfig,
    options: LlmCallOptions | None = None,
) -> "ChatOpenAI":
    resolved_options = options or LlmCallOptions()
    return create_openai_client(
        model_name=config.model_name,
        api_key=config.api_key,
        api_base=config.api_base,
        temperature=resolved_options.temperature,
        max_tokens=resolved_options.max_tokens,
        timeout=resolved_options.timeout,
    )
```

Update `get_chat_model()` to build a product-style explicit config without reading env:

```python
config = LlmConfig(
    api_key=(api_key or "").strip(),
    api_base=(api_base or DEFAULT_LLM_API_BASE).strip(),
    model_name=(model_name or DEFAULT_LLM_MODEL_NAME).strip(),
    source="product",
)
return create_chat_model(config, LlmCallOptions(...))
```

- [ ] **Step 4: Export new API**

Modify `engine/llm/__init__.py` to export:

```python
from engine.llm.config import (
    LlmConfig,
    LlmConfigurationError,
    resolve_optional_product_llm_config,
    resolve_product_llm_config,
    resolve_support_llm_config_from_env,
)
from engine.llm.factory import LLMClientFactory, LlmCallOptions, create_chat_model, get_chat_model
```

- [ ] **Step 5: Run factory tests**

Run:

```bash
pytest engine/tests/test_llm_config.py engine/tests/test_llm_factory.py -q
```

Expected: pass.

## Task 3: Product Agent Boundary

**Files:**
- Modify: `engine/api/agent.py`
- Modify: `engine/agent/graph/context.py`
- Test: `engine/tests/test_agent_llm_boundaries.py`

- [ ] **Step 1: Write failing Agent boundary tests**

Create `engine/tests/test_agent_llm_boundaries.py`:

```python
from __future__ import annotations

import pytest
from fastapi import HTTPException


def test_product_agent_run_requires_request_key_even_when_env_exists(monkeypatch) -> None:
    import engine.api.agent as agent_module
    from engine.agent_core.types import AgentRunRequest

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    monkeypatch.delenv("DBFOX_TESTING", raising=False)

    with pytest.raises(HTTPException) as exc_info:
        agent_module.api_agent_run(
            AgentRunRequest(datasource_id="ds-1", question="hello"),
            object(),  # type: ignore[arg-type]
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail["code"] == "NO_LLM_KEY"


def test_graph_context_credentials_only_use_request_config(monkeypatch) -> None:
    from engine.agent.graph.context import GraphRuntimeContext

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    ctx = GraphRuntimeContext(
        thread_id="thread-1",
        registry=object(),  # type: ignore[arg-type]
        db=object(),  # type: ignore[arg-type]
        request=object(),  # type: ignore[arg-type]
        api_key=None,
    )

    assert ctx.has_llm_credentials is False
```

- [ ] **Step 2: Run Agent boundary tests and verify they fail**

Run:

```bash
pytest engine/tests/test_agent_llm_boundaries.py -q
```

Expected: first test reaches runtime or second test returns `True` because env is still accepted.

- [ ] **Step 3: Update Agent API credential validation**

Modify `_check_llm_credentials()` in `engine/api/agent.py`:

```python
def _check_llm_credentials(req: AgentRunRequest) -> None:
    try:
        resolve_product_llm_config(
            api_key=req.api_key,
            api_base=req.api_base,
            model_name=req.model_name,
        )
    except LlmConfigurationError as exc:
        raise DBFoxError(str(exc), code=exc.code) from exc
```

Remove product LLM credential fallback to `OPENAI_API_KEY`.

- [ ] **Step 4: Update graph context credential check**

Modify `GraphRuntimeContext.has_llm_credentials` in `engine/agent/graph/context.py`:

```python
@property
def has_llm_credentials(self) -> bool:
    return bool((self.api_key or "").strip())
```

- [ ] **Step 5: Run Agent boundary tests**

Run:

```bash
pytest engine/tests/test_agent_llm_boundaries.py engine/tests/test_agent_api.py::test_api_agent_run_rolls_back_db_session_on_unhandled_exception -q
```

Expected: pass.

## Task 4: Schema AI Enrichment Boundary

**Files:**
- Modify: `engine/schema_sync.py`
- Modify: `engine/environment/schema_catalog_sync.py`
- Modify: `engine/ai_enrich.py`
- Modify: `engine/ai_index.py`
- Test: `engine/tests/test_ai_enrich.py`
- Test: `engine/tests/test_llm_config.py`

- [ ] **Step 1: Write failing enrichment boundary test**

Append to `engine/tests/test_ai_enrich.py`:

```python
def test_ai_enrich_does_not_use_environment_api_key(monkeypatch, db_session) -> None:
    from engine.ai_enrich import ai_enrich_catalog
    from engine.models import DataSource, SchemaTable

    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")

    datasource = DataSource(id="ds-ai-env", name="AI Env", db_type="sqlite", database_name=":memory:")
    table = SchemaTable(
        id="table-ai-env",
        data_source_id="ds-ai-env",
        table_name="orders",
        table_schema="main",
        table_type="table",
        schema_hash="stale",
    )
    db_session.add_all([datasource, table])
    db_session.commit()

    result = ai_enrich_catalog(db_session, "ds-ai-env", api_key=None)

    assert result["ai_enriched"] is False
    assert result["reason"] == "请先在设置中配置 LLM API Key。"
```

- [ ] **Step 2: Run enrichment test and verify it fails**

Run:

```bash
pytest engine/tests/test_ai_enrich.py::test_ai_enrich_does_not_use_environment_api_key -q
```

Expected: test fails because env key is still considered available.

- [ ] **Step 3: Refactor enrichment config passing**

Modify `engine/environment/schema_catalog_sync.py` to resolve optional product config before calling `ai_enrich_catalog()`:

```python
from engine.llm.config import resolve_optional_product_llm_config

llm_config = resolve_optional_product_llm_config(
    api_key=ai_api_key,
    api_base=ai_api_base,
    model_name=ai_model_name,
)
enrich_result = ai_enrich_catalog(db, datasource_id, llm_config=llm_config)
```

Modify `engine/ai_enrich.py` signature to accept `llm_config: LlmConfig | None = None`. Return the missing-key result when `llm_config is None`. Pass `llm_config` into `enrich_tables_batch()`.

Modify `engine/ai_index.py` so `enrich_tables_batch()` and `_call_llm()` accept `llm_config: LlmConfig`. `_call_aliyun_llm()` must use `llm_config.api_key`, `llm_config.api_base`, and `llm_config.model_name`, not `os.getenv()`.

- [ ] **Step 4: Keep compatibility for direct callers**

For temporary direct callers of `ai_enrich_catalog(..., api_key=..., api_base=..., model_name=...)`, build `llm_config` with `resolve_optional_product_llm_config()` inside `ai_enrich_catalog()` only when `llm_config` was not supplied. Do not read env.

- [ ] **Step 5: Run enrichment tests**

Run:

```bash
pytest engine/tests/test_ai_enrich.py engine/tests/test_llm_config.py -q
```

Expected: pass.

## Task 5: Test And E2E Isolation

**Files:**
- Modify: `engine/tests/conftest.py`
- Modify: `engine/agent/tests/test_e2e_qwen.py`
- Test: `engine/tests/test_llm_config.py`

- [ ] **Step 1: Add failing test isolation assertion**

Append to `engine/tests/test_llm_config.py`:

```python
def test_support_env_resolution_has_no_global_test_side_effect(monkeypatch) -> None:
    import os

    from engine.llm.config import resolve_support_llm_config_from_env

    monkeypatch.setenv("QWEN_API_KEY", "sk-qwen")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    config = resolve_support_llm_config_from_env(environ={
        "QWEN_API_KEY": "sk-qwen",
        "QWEN_API_BASE": "https://dashscope.example/v1",
        "QWEN_MODEL_NAME": "qwen-plus",
    })

    assert config.api_key == "sk-qwen"
    assert os.environ.get("OPENAI_API_KEY") is None
```

- [ ] **Step 2: Remove global Qwen-to-OpenAI mutation**

Modify `engine/tests/conftest.py` by deleting:

```python
_qwen_key = os.environ.get("QWEN_API_KEY", "").strip()
if _qwen_key:
    os.environ.setdefault("OPENAI_API_KEY", _qwen_key)
    os.environ.setdefault("OPENAI_API_BASE", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    os.environ.setdefault("OPENAI_MODEL_NAME", "qwen-plus")
```

Keep `DBFOX_TESTING`, confirmation bypass, and guardrail bypass setup unchanged.

- [ ] **Step 3: Update E2E helper**

Modify `engine/agent/tests/test_e2e_qwen.py` by removing:

```python
os.environ.setdefault("OPENAI_API_KEY", QWEN_API_KEY)
os.environ.setdefault("OPENAI_MODEL_NAME", QWEN_MODEL_NAME)
os.environ.setdefault("OPENAI_API_BASE", QWEN_API_BASE)
```

Keep every `AgentRunRequest` explicit with `api_key=QWEN_API_KEY`, `api_base=QWEN_API_BASE`, and `model_name=QWEN_MODEL_NAME`.

- [ ] **Step 4: Run isolation tests**

Run:

```bash
pytest engine/tests/test_llm_config.py engine/agent/tests/test_e2e_qwen.py::TestRealModelToolCalling::test_model_sees_alias_tool_names -q
```

Expected: pass without requiring a real LLM key for the alias-only E2E test.

## Task 6: Final Verification

**Files:**
- All modified files

- [ ] **Step 1: Run focused backend tests**

Run:

```bash
pytest engine/tests/test_llm_config.py engine/tests/test_llm_factory.py engine/tests/test_agent_llm_boundaries.py engine/tests/test_agent_api.py::test_api_agent_run_rolls_back_db_session_on_unhandled_exception engine/tests/test_ai_enrich.py -q
```

Expected: pass.

- [ ] **Step 2: Search for remaining product LLM env reads**

Run:

```bash
rg -n "OPENAI_API_KEY|OPENAI_API_BASE|OPENAI_BASE_URL|QWEN_API_KEY|QWEN_API_BASE|QWEN_MODEL_NAME|DBFOX_LLM_API_KEY" engine/llm engine/api/agent.py engine/agent engine/agent_core/answer.py engine/schema_sync.py engine/ai_enrich.py engine/ai_index.py engine/environment/schema_catalog_sync.py engine/tests/conftest.py engine/agent/tests/test_e2e_qwen.py
```

Expected remaining env reads only in:

- `engine/llm/config.py`;
- non-LLM product env features such as persistence/test flags;
- E2E helper constants in `engine/agent/tests/test_e2e_qwen.py`;
- test assertions that intentionally verify boundaries.

- [ ] **Step 3: Run whitespace check**

Run:

```bash
git diff --check
```

Expected: no errors.

- [ ] **Step 4: Commit implementation**

Run:

```bash
git add engine/llm/config.py engine/llm/factory.py engine/llm/__init__.py engine/api/agent.py engine/agent/graph/context.py engine/agent/nodes/model_node.py engine/agent/progress/llm_judge.py engine/agent/nodes/turn_node.py engine/agent_core/answer.py engine/schema_sync.py engine/environment/schema_catalog_sync.py engine/ai_enrich.py engine/ai_index.py engine/tests/conftest.py engine/agent/tests/test_e2e_qwen.py engine/tests/test_llm_config.py engine/tests/test_agent_llm_boundaries.py engine/tests/test_ai_enrich.py
git commit -m "refactor: unify llm call configuration"
```
