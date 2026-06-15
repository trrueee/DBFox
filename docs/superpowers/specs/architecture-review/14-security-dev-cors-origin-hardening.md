# Security Development CORS Origin Hardening Spec

Date: 2026-06-15
Priority: P2
Area: Local API security
Primary files: `engine/main.py`

## Problem

Development CORS allows several localhost ports such as 5173, 5174, and 5175. If another local app occupies an allowed port, browser-origin checks alone are less meaningful. Token auth still protects requests, but origin policy should be tighter where practical.

## Goals

- Keep development convenient.
- Reduce allowed origins to the actual frontend dev server origin.
- Preserve production Tauri origin restrictions.
- Avoid weakening `X-Local-Token`.

## Non-Goals

- Do not remove HTTP API access in development.
- Do not require immediate IPC migration.
- Do not support arbitrary browser clients by default.

## Proposed Design

Make dev CORS origins explicit and configurable:

- Default to `http://localhost:5173`.
- Allow override via `DATABOX_DEV_CORS_ORIGINS`, comma-separated.
- Log configured origins at startup in dev mode.
- Reject wildcard origins unless `DATABOX_ALLOW_UNSAFE_DEV_CORS=1` is set.

Optionally, Vite can write or pass its actual dev origin to the engine startup process.

Production behavior remains:

- Tauri origins only.
- docs/openapi disabled in frozen mode.
- token middleware required.

## Acceptance Criteria

- Default dev origin list is minimal.
- Developers can intentionally add alternate ports.
- Unsafe wildcard mode is impossible without an explicit env flag.
- Existing local-token middleware tests pass.

## Test Plan

- Unit/API test allowed origin succeeds.
- Unit/API test unlisted localhost port is rejected.
- Env override test allows a configured alternate port.
- Production-mode test still rejects docs/openapi and non-Tauri origins.

## Rollout

Ship with a clear log message. If existing developers use alternate Vite ports, they can set `DATABOX_DEV_CORS_ORIGINS`.
