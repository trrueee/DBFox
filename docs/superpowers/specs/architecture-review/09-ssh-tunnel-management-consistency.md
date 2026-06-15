# SSH Tunnel Management Consistency Spec

Date: 2026-06-15
Priority: P2/P3
Area: Datasource connectivity

## Corrected Judgment

The earlier "MySQL SSH tunnel leak" framing is inaccurate. `test_connection` stops its temporary tunnel in `finally`, and formal query/schema paths use a managed `TunnelManager`. The real issue is consistency: test/health checks and real execution use different tunnel lifecycle paths.

## Code Evidence

- `engine/datasource.py:374-455` creates and stops a temporary PostgreSQL SSH tunnel for `test_connection`.
- `engine/datasource.py:466-561` creates and stops a temporary MySQL SSH tunnel for `test_connection`.
- `engine/datasource.py:40-188` defines `TunnelManager` with health checks, reconnect, and cleanup.
- `engine/datasource.py:201-203` exposes `get_or_create_tunnel_for_dict()` using `TunnelManager`.
- `engine/schema_sync.py:29-37` and `engine/schema_sync.py:282-290` use the managed tunnel path for schema sync.

## Problem

A user can test a connection through one tunnel path and execute/sync through another. This can create two short-lived SSH connections, different health behavior, and different logs. It is not a proven leak, but it makes support and observability harder.

## Goals

- Align test/health checks with the managed tunnel path when possible.
- Preserve the ability to test unsaved datasource configs.
- Avoid leaving managed tunnels open for discarded draft configs.
- Keep current cleanup guarantees.

## Non-Goals

- Do not rewrite SSH support.
- Do not force unsaved test connections into the persistent tunnel registry unless they have a stable temporary key and cleanup.
- Do not treat this as a critical security bug.

## Proposed Design

Use two explicit tunnel modes:

- Saved datasource mode:
  - health check and execution use `TunnelManager` keyed by datasource id.
  - delete/update closes or refreshes the corresponding managed tunnel.

- Draft test mode:
  - use a short-lived helper such as `open_temporary_tunnel(config)`.
  - helper owns start/stop and logging.
  - helper mirrors the same option mapping and keepalive defaults as `TunnelManager`.

The main cleanup is to share tunnel construction/config mapping, not to force every test into a long-lived tunnel.

## Acceptance Criteria

- Temporary and managed tunnel creation use the same config-normalization helper.
- Saved datasource health checks can reuse or refresh the managed tunnel.
- Draft test connections still close temporary tunnels deterministically.
- Logs identify whether a tunnel is `temporary_test` or `managed_datasource`.

## Test Plan

- Unit tests with mocked `SSHTunnelForwarder` prove temporary test tunnels stop on success and failure.
- Unit tests prove saved datasource health checks call the managed path.
- Regression tests for datasource delete closing active managed tunnel.
