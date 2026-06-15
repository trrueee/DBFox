# ORM Debug Repr Methods Spec

Date: 2026-06-15
Priority: Code Quality
Area: Backend models
Primary files: `engine/models.py`

## Problem

ORM models in `engine/models.py` lack helpful `__repr__` methods. During debugging, logs and interactive sessions show generic object identities rather than useful domain identifiers.

## Goals

- Improve local debugging and logs.
- Avoid leaking secrets in repr output.
- Keep reprs concise and stable.

## Non-Goals

- Do not change database schema.
- Do not alter serialization or API response behavior.
- Do not include encrypted secret fields.

## Proposed Design

Add `__repr__` to high-value models first:

- `DataSource`: id, name, db_type, env, status.
- `Project`: id, name, status.
- `SchemaTable`: id, table_name, data_source_id.
- `ChatConversation`: id, title, updated_at.
- Agent eval/run models: id, status, datasource_id where applicable.

Pattern:

```python
def __repr__(self) -> str:
    return f"<DataSource id={self.id!r} name={self.name!r} db_type={self.db_type!r} env={self.env!r}>"
```

Rules:

- Never include password ciphertext, nonce, tokens, SQL text, full prompts, or large JSON blobs.
- Prefer identifiers and small labels.

## Acceptance Criteria

- Repr output is useful for the main ORM models.
- No repr includes secret-like fields.
- Tests cover representative repr output.
- Existing ORM behavior remains unchanged.

## Test Plan

- Unit tests instantiate models and assert repr contains expected safe fields.
- Unit test checks `DataSource.__repr__` does not include password fields.

## Rollout

Small backend quality change. Can be bundled with logging improvements.
