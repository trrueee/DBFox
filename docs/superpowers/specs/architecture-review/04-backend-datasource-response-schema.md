# Backend Typed Datasource API Responses Spec

Date: 2026-06-15
Priority: P4
Area: Backend API contracts
Primary files: `engine/api/datasources.py`, `engine/schemas/datasource.py`

## Problem

`_datasource_to_dict()` returns `dict[str, Any]`. This keeps implementation flexible but gives FastAPI no response model for validation, documentation, or accidental field drift detection.

## Goals

- Define a typed datasource response model.
- Use `response_model` for datasource list/create/update/health responses where appropriate.
- Preserve current JSON field names consumed by the desktop frontend.
- Make nullable and optional fields explicit.

## Non-Goals

- Do not redesign datasource persistence models.
- Do not expose encrypted secret fields.
- Do not rename existing response keys in this iteration.

## Proposed Design

Add `DataSourceResponse` to `engine/schemas/datasource.py`.

Model includes existing public fields:

- identifiers: `id`, `project_id`, `environment_id`
- connection info: `name`, `db_type`, `host`, `port`, `database_name`, `username`, `connection_mode`
- safety/config: `is_read_only`, `env`, `status`
- SSH public config: `ssh_enabled`, `ssh_host`, `ssh_port`, `ssh_username`, `ssh_pkey_path`
- SSL public config: `ssl_enabled`, `ssl_ca_path`, `ssl_cert_path`, `ssl_key_path`, `ssl_verify_identity`
- health/sync metadata: `last_test_*`, `last_sync_*`
- `created_at`

Then annotate routes:

- `POST /datasources`
- `GET /datasources`
- future `PUT /datasources/{id}`
- nested `datasource` field inside health response.

Keep `_datasource_to_dict()` initially as a mapper, but validate it through `DataSourceResponse.model_validate()` in tests.

## Acceptance Criteria

- FastAPI route declarations use response models.
- Desktop API JSON shape remains backward compatible.
- Secret fields are absent.
- Tests fail if `_datasource_to_dict()` omits required public fields or returns wrong types.

## Test Plan

- Unit test `_datasource_to_dict()` validates against `DataSourceResponse`.
- API test for `GET /datasources` checks expected keys and absence of secret keys.
- API test for health response validates nested datasource shape.

## Rollout

Add the response model before any larger datasource API redesign. This creates a safer contract for the upcoming datasource management console.
