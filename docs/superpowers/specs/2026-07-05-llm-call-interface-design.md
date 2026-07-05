# LLM Call Interface Design

Date: 2026-07-05
Status: approved design for implementation planning

## Goal

Make LLM calls stable and predictable by centralizing configuration resolution and client creation.

DBFox should have one internal LLM configuration model and one client factory path. The source of that configuration must stay explicit:

- product requests use frontend-provided configuration only;
- support, eval, E2E, and headless developer paths may read environment variables only at their boundary;
- normal unit tests do not depend on real local LLM environment variables.

## Current Problems

The current code has useful pieces, but configuration is resolved in too many places:

- `desktop/src/components/SettingsDialog.tsx` stores product LLM config locally and product calls pass `api_key`, `api_base`, and `model_name` in request payloads.
- `engine/llm/factory.py::get_chat_model()` mixes explicit arguments with environment-variable fallback.
- `engine/api/agent.py::_check_llm_credentials()` can accept `OPENAI_API_KEY` for product routes.
- `engine/agent/graph/context.py::GraphRuntimeContext.has_llm_credentials` reads environment variables from graph runtime code.
- `engine/agent_core/answer.py`, `engine/agent/nodes/turn_node.py`, `engine/schema_sync.py`, `engine/ai_enrich.py`, and `engine/ai_index.py` have separate LLM credential checks or fallbacks.
- `engine/tests/conftest.py` can translate `QWEN_API_KEY` into `OPENAI_*` for every test session, so ordinary tests can behave differently on machines with real keys.
- `engine/agent/tests/test_e2e_qwen.py` both reads `QWEN_*` and writes `OPENAI_*`, while also passing explicit request fields.

The product and support paths are therefore mixed. This makes failures hard to explain and lets local environment state change product or unit-test behavior.

## Design Principles

1. Configuration source and client construction are separate concerns.
2. Product code does not read LLM environment variables.
3. Environment variables are accepted only by named support/eval/E2E entrypoints.
4. All runtime LLM users receive a resolved `LlmConfig`, not loose `api_key`, `api_base`, and `model_name` strings.
5. One factory creates chat clients from `LlmConfig` plus per-call options.
6. Missing credentials fail at the boundary with a clear error or an explicit non-enriched result.
7. Secret values are never logged or persisted in plaintext.

## Core API

Add `engine/llm/config.py`:

```python
@dataclass(frozen=True)
class LlmConfig:
    api_key: str
    api_base: str
    model_name: str
    source: Literal["product", "support_env", "test"]
```

The config module owns defaults and validation:

```python
DEFAULT_LLM_API_BASE = "https://api.openai.com/v1"
DEFAULT_LLM_MODEL_NAME = "gpt-4o-mini"

def resolve_product_llm_config(
    *,
    api_key: str | None,
    api_base: str | None,
    model_name: str | None,
) -> LlmConfig:
    ...

def resolve_optional_product_llm_config(
    *,
    api_key: str | None,
    api_base: str | None,
    model_name: str | None,
) -> LlmConfig | None:
    ...

def resolve_support_llm_config_from_env(
    *,
    require_key: bool = True,
    environ: Mapping[str, str] | None = None,
) -> LlmConfig:
    ...
```

`resolve_product_llm_config()` must not inspect `os.environ`. It normalizes request-provided values and raises a typed missing-config error when no key is provided.

`resolve_optional_product_llm_config()` is for optional product features such as schema AI enrichment. It must not inspect `os.environ`; it returns `None` when no product key is provided.

`resolve_support_llm_config_from_env()` is the only engine-level function that reads LLM env vars. It supports:

- `OPENAI_API_KEY`, `QWEN_API_KEY`, `DBFOX_LLM_API_KEY`;
- `OPENAI_API_BASE`, `OPENAI_BASE_URL`, `QWEN_API_BASE`;
- `OPENAI_MODEL_NAME`, `QWEN_MODEL_NAME`.

Add or refactor `engine/llm/factory.py`:

```python
@dataclass(frozen=True)
class LlmCallOptions:
    temperature: float = 0.0
    max_tokens: int | None = None
    timeout: float = 120.0

def create_chat_model(config: LlmConfig, options: LlmCallOptions | None = None) -> ChatOpenAI:
    ...
```

`create_chat_model()` is the only path that calls provider-specific constructors such as `create_openai_client()`.

`get_chat_model()` can remain temporarily as a compatibility wrapper, but it must become explicit-config-only and delegate to `create_chat_model()`. It must not read environment variables.

## Runtime Boundaries

### Product Agent Runs

Product flow:

```text
frontend SettingsDialog/localStorage
-> AgentRunRequest api_key/api_base/model_name
-> resolve_product_llm_config()
-> GraphRuntimeContext.llm_config
-> create_chat_model()
```

`/agent/run` and `/agent/run/stream` validate product config from the request. If the request lacks an API key, they return the existing `NO_LLM_KEY` style error even when the host process has LLM env vars.

Graph nodes use `ctx.llm_config` instead of reading env or checking loose fields.

### Product Schema AI Enrichment

Product flow:

```text
frontend SchemaSyncOptions
-> sync_schema(ai_api_key, ai_api_base, ai_model_name)
-> resolve_optional_product_llm_config()
-> ai_enrich_catalog(..., llm_config)
-> create_chat_model()
```

When AI enrichment is requested without product credentials, schema sync returns a clear non-enriched warning instead of falling back to env.

### Support, Eval, And Headless Dev

Support flow:

```text
env
-> resolve_support_llm_config_from_env()
-> explicit AgentRunRequest fields or direct support runner config
-> normal runtime path
```

CLI/eval/headless code may read env only through the support resolver. After that boundary, runtime code receives an explicit `LlmConfig` or explicit request fields.

### E2E Real-LLM Tests

Real E2E tests read env only inside E2E helpers:

```text
QWEN_* / OPENAI_* env
-> e2e helper builds explicit request fields
-> AgentRunRequest
-> product runtime path
```

E2E tests must not write `OPENAI_*` env as a side effect. They either skip when required credentials are absent or run with explicit request config.

### Ordinary Unit Tests

Ordinary tests use fake `LlmConfig`, monkeypatched factories, or fake model objects.

Global test setup must not convert real local credentials into default LLM env vars. A developer with `QWEN_API_KEY` in their shell should get the same ordinary unit-test behavior as a developer without it.

## Migration Scope

The first implementation should update only LLM configuration and call sites:

- `engine/llm/config.py`;
- `engine/llm/factory.py`;
- `engine/llm/__init__.py`;
- Agent API credential validation;
- graph runtime context and model/progress/turn/answer call sites;
- schema sync and AI enrichment call sites;
- eval and E2E helpers;
- focused backend tests for resolver behavior, API boundaries, and ordinary-test isolation.

This design does not change provider support, prompt behavior, SQL safety behavior, SSE event contracts, workspace views, or datasource sync semantics beyond the AI enrichment credential boundary.

## Acceptance Criteria

1. Product `/agent/run` without request `api_key` fails even if `OPENAI_API_KEY` is set in the process environment.
2. Product schema AI enrichment without request credentials reports non-enriched or missing-config status without reading env.
3. `get_chat_model()` and graph runtime code do not inspect LLM env vars.
4. `resolve_support_llm_config_from_env()` accepts the supported env names and is covered by tests.
5. E2E tests build explicit request config from env and do not mutate `OPENAI_*`.
6. Ordinary tests do not change behavior based on real local LLM credentials.
7. All real client construction goes through `create_chat_model(LlmConfig, LlmCallOptions)`.
