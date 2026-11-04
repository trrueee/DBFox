# DLC SDK, CLI, and conformance contract

> 文档类型：架构说明 / 开发者指南
>
> 状态：当前
>
> 最后核验：2026-08-31
>
> 上位合同：[DBFox Core Kernel 宪章](./core-kernel-constitution.md)

## Stable author surfaces

API v2 的可选对话输入能力见[对话附件合同](./conversation-attachments.md)。后端新增
`ATTACHMENT_RESOURCE_KIND`、只读 `AttachmentResourceHandle`、
`SessionResourceDiscoveryContext` 与 `ExtensionSessionResourceProvider`；
`host.resources.register_session_provider(provider, retire=...)` 必须返回本 owner 的资源。
会话目录以当前 Run 已处理的输入顺序为上界，工具继续冻结精确 Invocation refs。
`DlcOperationSpec.scope="session"` 从 URL 的 `session_id` 获取可信会话，Host 推导所属项目，
拒绝不匹配的 `project_id`；`context.resource(ref)` 只接受本次已绑定范围。
工具引用 Host 附件 kind 的特例仅允许该精确 kind，并要求 `filesystem_read`。
Context Artifact observation 可带 `run_status`，成功工具不等于整个分析完成。

前端 Dock contribution 可声明 `attachmentExtensions`；DockTab 可带 `sessionId`，
DockViewContext 提供 `workbenchScopeId`，Operation invoke options 可带 `sessionId`。
Artifact envelope 的 `session_id` 用于私有来源的 Representation 分页与导出。
格式选择来自当前已注册 contribution；本版 Data 只声明 `xlsx`。这些均为可选新增，
旧 Project Operation 与 provider 合同继续通过 conformance，未新增 PDF/CSV 读取实现。

DBFox exposes one backend import surface (`dbfox_dlc_api`), one frontend type
surface (`sdk/frontend`), and one Host-owned package contract. The renderer
consumes the same frontend declarations that DLC authors consume. The manifest
schema is generated from the Host Pydantic model, so neither artifact becomes a
second source of truth.

The current backend contract is Extension API v2. `dbfox_dlc_api.DLC_API_VERSION`
and manifest `extensionApiVersion` resolve to the same authoritative value
(`"2"`). The exact Python author surface is contract-tested against
`verification/tests/system/fixtures/dlc_api_v2_surface.txt`; Engine-private
modules are not an alternative author surface.

Stable means compatible, not immutable implementation. An optional additive
contract may remain in API v2 only when existing packages continue to conform,
the public-surface snapshot and documentation are deliberately updated, and the
Host fails closed when the contribution is absent. Removal or incompatible
semantic change requires a new `extensionApiVersion`, a migration path, and an
explicit retirement rule. Experimental contracts stay outside the public
`__all__` and stable frontend declarations.

Dependency direction is enforced in engineering contracts: DLC backends may
import `dbfox_dlc_api`, but not `engine.*` or another `dlcs.*`; frontend packages
use the injected Host SDK and may not import `desktop/src` private modules.

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
