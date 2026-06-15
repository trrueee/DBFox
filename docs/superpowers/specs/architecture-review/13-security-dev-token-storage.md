# Security Dev Token Storage Hardening Spec

Date: 2026-06-15
Priority: P1
Area: Local development security
Primary files: `engine/main.py`, `desktop/.gitignore`, `.gitignore`

## Problem

In development mode, the local engine token is written to `desktop/.env.local`. This supports Vite development, but token files are easy to accidentally commit or expose through editor tooling.

## Goals

- Ensure generated dev token files are ignored.
- Make accidental token commits difficult.
- Preserve current dev workflow.
- Consider a better long-term token injection mechanism.

## Non-Goals

- Do not remove `X-Local-Token` authentication.
- Do not require Tauri IPC migration in this spec.
- Do not change production token generation.

## Proposed Design

Short-term hardening:

- Verify root `.gitignore` and `desktop/.gitignore` both ignore `.env.local`.
- Add a startup check in `engine/main.py` that warns if `desktop/.env.local` appears tracked by Git.
- Write only the token variable needed by Vite, not unrelated environment data.
- Use restrictive file permissions where possible.

Long-term option:

- Replace file-based dev token sharing with a Vite dev-server proxy that injects `X-Local-Token` server-side.
- Desktop frontend calls relative `/api` in dev; Vite proxy forwards to engine with the token.

## Acceptance Criteria

- `.env.local` is ignored in all relevant Git ignore files.
- Tests or script checks fail if `.env.local` becomes tracked.
- Dev startup still works without manual token copy.
- Documentation explains why the file exists and must stay untracked.

## Test Plan

- Unit test or script-level check for ignore coverage.
- Manual dev startup test: engine writes token, Vite frontend can call API.
- Negative check: `git check-ignore desktop/.env.local` succeeds.

## Rollout

Implement short-term guard first. Evaluate Vite proxy migration separately because it changes dev request routing.
