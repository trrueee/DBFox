# Backend Key Management Fallback Hardening Spec

Date: 2026-06-15
Priority: P1
Area: Backend security
Primary files: `engine/crypto.py`

## Problem

`engine/crypto.py` prefers OS Keychain for the AES-256-GCM master key, but falls back to storing the key on the filesystem when Keychain is unavailable. The fallback is useful for local-first operation, but a plaintext key file with weak filesystem permissions increases compromise risk.

## Goals

- Preserve local-first startup when OS Keychain is unavailable.
- Restrict filesystem fallback key access to the current OS user.
- Make fallback usage visible and diagnosable.
- Add tests that prove permission hardening is attempted.

## Non-Goals

- Do not remove filesystem fallback in this iteration.
- Do not migrate all existing encrypted datasource secrets.
- Do not introduce a remote secret manager.

## Proposed Design

Add a small key-file hardening layer in `engine/crypto.py`.

On POSIX systems:

- Create parent directory with `0o700`.
- Create or rewrite key file with `0o600`.
- After loading an existing key, validate mode. If group/world bits are present, tighten to `0o600` and log a warning.

On Windows:

- Prefer `os.chmod(path, stat.S_IREAD | stat.S_IWRITE)` as a baseline.
- Add a best-effort ACL hardening function using native Windows APIs or `icacls` only if it can be implemented without shell-injection risk.
- If ACL hardening cannot run, log a clear warning that OS Keychain is recommended.

Add a startup warning once per process when fallback is active:

```text
OS keychain unavailable; using local encrypted-key fallback. Restricting key file to current user.
```

## Acceptance Criteria

- New fallback key files are not group/world readable on POSIX.
- Existing permissive key files are tightened on next load.
- Windows fallback logs an actionable warning when ACL hardening cannot be verified.
- Normal encryption/decryption behavior remains backward compatible.
- Tests do not require a real OS Keychain.

## Test Plan

- Unit test: new fallback key path gets parent mode `0o700` and file mode `0o600` on POSIX.
- Unit test: permissive existing file is tightened.
- Unit test: fallback warning is emitted when Keychain access raises.
- Existing crypto tests continue to pass.

## Rollout

Ship as a backend-only hardening change. Add a release note under security hardening because users may see a new warning when Keychain is unavailable.
