# DLC SDK, CLI, and conformance contract

> 文档类型：架构说明 / 开发者指南
>
> 状态：当前
>
> 最后核验：2026-08-21

## Stable author surfaces

DBFox exposes one backend import surface (`dbfox_dlc_api`), one frontend type
surface (`sdk/frontend`), and one Host-owned package contract. The renderer
consumes the same frontend declarations that DLC authors consume. The manifest
schema is generated from the Host Pydantic model, so neither artifact becomes a
second source of truth.

The CLI uses Python's standard `argparse` and `zipfile` implementations and the
existing `cryptography` Ed25519 dependency. It does not introduce another CLI
framework, archive library, verifier, registry, or package schema.

## Commands

Run `tools/dbfox-dlc` on macOS/Linux or `tools\dbfox-dlc.cmd` on Windows. The
same commands are available as `python -m engine.dlc.cli`.

```text
dbfox-dlc init ./my-dlc --id acme.example --publisher acme \
  --generate-key ../publisher-key.pem
dbfox-dlc build ./my-dlc --private-key ../publisher-key.pem \
  --output ./dist/acme.example.dbfox-dlc
dbfox-dlc test ./dist/acme.example.dbfox-dlc
```

`init` encrypts generated PKCS#8 private keys by default. A password may come
from an explicitly named environment variable for automation. The opt-in
`--unencrypted-key` flag exists for isolated conformance fixtures. Private key
bytes are never printed and the package builder only admits `backend/` and
`frontend/`, so a key beside the project manifest cannot enter an archive.

For an offline signing boundary:

```text
dbfox-dlc build ./my-dlc --unsigned --public-key ../publisher-key.pem.pub \
  --output ./dist/acme.example.unsigned.dbfox-dlc
dbfox-dlc sign ./dist/acme.example.unsigned.dbfox-dlc \
  --private-key ../publisher-key.pem \
  --output ./dist/acme.example.dbfox-dlc
```

The signing key must match the public key already bound into the unsigned
manifest. Outputs are never overwritten implicitly.

## Determinism and verifier reuse

The builder uses sorted normalized POSIX paths, canonical JSON, fixed ZIP
timestamps, fixed file modes, and stored ZIP entries. Ed25519 signatures are
deterministic, so identical source, manifest, and key produce identical archive
bytes and package digests across supported platforms.

The builder and Host verifier share the archive bounds, path normalization,
control-file allowlist, native-extension ban, entrypoint rules, canonical JSON,
signed-message construction, and frontend React ownership check. Frontend DLCs
must consume the React instance injected at
`window.__DBFOX_EXTENSION_HOST__`; unresolved bare React imports and recognizable
embedded React runtimes fail verification.

## Meaning of `test`

`test` copies the package into a new temporary directory, trusts only the
package's authenticated embedded key in memory, and runs the production Host
verifier. It then compiles Python source and asks Node to parse JavaScript as ES
modules without importing or executing either entrypoint. It never constructs
`DlcPackageService`, writes an installed registry, or runs extension code.

This is a conformance check, not a sandbox. Runtime containment for untrusted
publishers is exclusively an R8 decision.

## Reuse decision

The implementation reuses the runtime manifest, integrity, trust, and verifier
primitives plus the standard Python CLI/ZIP facilities. A separate package
format library and a Node-based signing implementation were rejected because
either would duplicate canonicalization and signature rules. No compatibility
layer, dual write, new runtime dependency, or migration debt was introduced.
