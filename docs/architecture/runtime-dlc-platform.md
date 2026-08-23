# Runtime DLC Platform Architecture & Feasibility Specification

> 文档类型：架构规范
>
> 状态：当前

>
> 最后核验：2026-08-22
>
> 基线：`main@2625ac366113c031149fd226075932ddca0739b2` + R8A work package
>
> 上位 Issue：[#59](https://github.com/trrueee/DBFox/issues/59)
>
> 2026-08-22 收敛说明：本文的 DLC package、verification、snapshot 与 contribution
> lifecycle 继续有效；Project/Resource/Conversation authority 和 System DLC 迁移以
> [Agent Core 与 Capability DLC 架构合同](./agent-core-capability-dlc-contract.md) 为准。
> `Requested Resources` contributor 不再是目标 authority 路径。

## 1. Product Vision, Security Model & Protocol-First Principle

### Product Vision
Any developer can build an extension conforming to the DBFox DLC Protocol, package it into a single `.dbfox-dlc` file, and distribute it directly to users. The user installs the package via **Install from File** in DBFox DLC Center, verifies and enables it, and all contributed capabilities (Tools, Resources, Context, Connectors, Dock Views, Artifact Renderers, Operations) become active after a controlled restart without modifying DBFox source code or recompiling the DBFox binary.

### Security Model (FROZEN)
> **DBFox Runtime DLC v1 is an authenticated trusted-code extension system, not a sandboxed third-party code platform.**
>
> The guarantees are:
> - **Signature**: authenticates publisher identity.
> - **Integrity**: authenticates package bytes / installed payload integrity.
> - **Manifest capability declarations**: describe the authority requested by the DLC.
> - **Registration policy**: limits which typed DBFox contribution contracts the DLC may register.
>
> These DO NOT sandbox arbitrary in-process Python behavior. Trusted DLC Python can theoretically use `os`, `pathlib`, `socket`, environment variables, and process APIs outside the public Extension API. R3/R7 frontend JavaScript executes in the product Renderer and is not sandboxed merely because the public Host object is narrow. R8A formally concluded **NO-GO** for cross-platform untrusted execution; production remains trusted-publisher-only. Do not make stronger security claims in code, docs, or tests.


### Source-Agnostic Principle
The Runtime DLC Platform recognizes only the **DLC Package** (`.dbfox-dlc`). It does not hardcode marketplace, official index, or remote server dependencies into the runtime execution core:
```text
Local File ─────────┐
URL ────────────────┤
Official Index ─────┤ ──> .dbfox-dlc Package ──> Verifier ──> Atomic Installer ──> Installed Registry ──> Runtime DLC Host
Enterprise Index ───┤
Marketplace ────────┘
```
Local file installation is the foundational baseline. Marketplace and remote indices are optional distribution sources that simply deliver verified `.dbfox-dlc` packages to the same installer.

---

## 2. Current DLC Registration Map

Workspace and GitHub are package-owned capabilities. Data is shipped as a verified System DLC but remains default-disabled until its execution family finishes moving; the legacy Data execution family is the only temporary built-in domain contribution. Historical domain SQL is retained solely under Alembic migration boundaries.

| Seam | Backend / Frontend | Compile-Time Baseline | Target Dynamic Host Seam |
|---|---|---|---|
| **Tool Extension** | Backend snapshot | temporary legacy Data registrar | `host.tools.register(...)` |
| **Resource Discovery** | Backend snapshot | temporary legacy Data capability provider | `host.resources.register_provider(...)` |
| **Resource Resolution** | Backend snapshot | temporary database resolver | `host.resources.register_resolver(...)` |
| **Context Contribution** | Backend snapshot | none | `host.context.register(...)` |
| **Completion Semantics** | Backend snapshot | temporary Data semantic declarations | `host.completion.register_constraint/register_support(...)` |
| **Artifact Contract** | Backend (`engine/agent/artifact.py`) | Core/Data/Workspace contracts | `host.artifacts.register(...)` |
| **Operations / API** | Backend (`engine/api/`) | Static Core product routers | `POST /api/v1/dlcs/{dlc_id}/operations/{op}` |
| **Resource Connector** | Frontend (`desktop/src/features/resources/`) | `productResourceConnectors()` | `host.connectors.register(...)` |
| **Conversation Context Selection** | Frontend Host | `ConversationResourceIntent` + Project draft selection | `host.contextSelection.isSelected/list/add/remove(...)`（只响应显式用户动作） |
| **Dock Views** | Frontend (`desktop/src/features/dock/`) | `productDockViews()` | `host.dockViews.register(...)` |
| **Artifact Renderers** | Frontend (`desktop/src/features/workspace/artifacts/`) | `productArtifactRenderers` | `host.artifactRenderers.register(...)` |

---

## 3. Package Format & Cryptographic Envelope

### Package Archive Layout (`.dbfox-dlc`)
An immutable ZIP-based archive with strict bounds and deterministic entry layout:
```text
<package_root>/
├── manifest.json       # Control file: Lifecycle metadata, compatibility bounds, publisherKey, permissions
├── integrity.json      # Control file: SHA256 digest mapping for all payload files (excludes integrity.json and signature.sig)
├── signature.sig       # Control file: Ed25519 digital signature of canonical manifest + integrity bytes
├── backend/            # Payload files: Backend Python extension code
│   ├── __init__.py
│   ├── entry.py        # def register(host: BackendExtensionHost) -> None
│   └── vendor/         # Optional pure-Python vendored dependencies
├── frontend/           # Payload files: Frontend pre-compiled ES module & styles
│   ├── index.js        # export function register(host: FrontendExtensionHost): void
│   ├── index.css       # Scoped stylesheet
│   └── assets/         # Static icons / images
```

### Canonical JSON Encoding & Signed Payload Specification
To guarantee deterministic signature generation and verification across platforms:
1. **Canonical JSON Encoding**:
   - Keys sorted lexicographically by Unicode code point (`sort_keys=True`).
   - Compact separators with no extraneous whitespace: `separators=(',', ':')`.
   - UTF-8 character encoding with no ASCII escaping of non-ASCII characters (`ensure_ascii=False`).
   - No trailing newline inside signed canonical byte strings.
2. **`integrity.json` Entry Contract (Payload-Only)**:
   - Maps normalized POSIX relative file paths of **payload files only** (`backend/entry.py`, `frontend/index.js`, etc.) to lowercase 64-character SHA256 hex digests.
   - `integrity.json` and `signature.sig` are **STRICTLY EXCLUDED** from `integrity.json` (eliminating self-referential hash recursion).
   - `manifest.json` is independently authenticated because its exact canonical bytes are directly included in the signed message.
3. **Signed Message Bytes**:
   ```text
   b"DBFOX-DLC-V1\n" + canonical_manifest_bytes + b"\n" + canonical_integrity_bytes
   ```
4. **Signature Verification**:
   - Verified using Ed25519 against the publisher's public key.
   - Publisher Key ID: SHA256 fingerprint of raw Ed25519 public key bytes.
   - Product installation uses `manifestSchemaVersion: 2`. Its signed manifest MUST contain
     `publisherKey`, encoded as canonical padded Base64 of exactly 32 raw Ed25519 public-key
     bytes. The display-only `publisher` string never participates in trust decisions.
   - Schema v2 is a single-file contract: signature authenticity is checked against the
     embedded `publisherKey`; no adjacent `.pub` file or UI-supplied verification key is used.
   - Schema v1 remains only as the existing internal compatibility path and requires an
     explicit external public key. It is not the Install from File product flow.
   - Signature authenticity and publisher trust are separate gates. Invalid signatures fail
     as `INVALID_SIGNATURE`; an authentic signature from an unknown key yields
     `TRUST_REQUIRED` and cannot be installed until the actual package key is explicitly trusted.
5. **Path Normalization & Archive Allowlist**:
   - Forward slashes `/` as path separators.
   - No leading `./` or `/`.
   - Rejection of `..` path traversal segments, absolute paths, symlinks, hardlinks, and device files.
   - Rejection of duplicate normalized paths (case-insensitive collisions).
   - **Archive Allowlist**: The ZIP archive must contain ONLY `{ "manifest.json", "integrity.json", "signature.sig" }` plus every normalized path listed in `integrity.json`. Any unlisted archive entry causes immediate validation failure.

### Package Bounds
- **Manifest size**: $\le 64\text{ KiB}$
- **Package compressed size**: $\le 50\text{ MiB}$
- **Package extracted size**: $\le 150\text{ MiB}$
- **Total file count**: $\le 1,000\text{ files}$
- **Single file size**: $\le 20\text{ MiB}$
- **Path length**: $\le 255\text{ characters}$

---

## 4. Backend Extension Host & Dependency Policy

### Execution & Loading Strategy (v1)
- **Loading Mechanism**: In-process dynamic loading via `importlib.util.spec_from_file_location` from the verified content-addressed directory (`APP_DATA/dlcs/packages/sha256-<digest>/backend/entry.py`).
- **Module Namespace Isolation**:
  - Each DLC's Python code loads under a dedicated, unique top-level package namespace derived from its DLC id and package digest prefix:
    ```text
    _dbfox_dlc_<safe_id>_<digestprefix>
    ```
  - Pure-Python vendored dependencies are imported relative to the DLC package root (e.g. `from .vendor.commonlib import ...`).
  - **No Global `sys.path` Mutation**: DLC loading MUST NOT mutate process-global `sys.path` or install into `site-packages`.
  - **Collision Resistance**: DLC A and DLC B can each vendor their own version of `commonlib` under their respective namespaces without collision or ordering dependence.
- **Registration Surface**:
  ```python
  class BackendExtensionHost:
      tools: ToolRegistrationScope
      resources: ResourceRegistrationScope
      context: ContextRegistrationScope
      artifacts: ArtifactRegistrationScope
      operations: OperationRegistrationScope
  ```
- **Tool Admission Boundary**: A Tool that declares `requires_admission=True` implements
  `admit(input, ToolAdmissionContext)`. The context exposes only frozen Resource refs,
  exact current-Run `artifact(id)`, and `artifacts_relating_to(id, relation)`. The Tool
  returns a bounded decision and optional approval subject; Kernel re-runs admission
  immediately before execution, verifies the selected ref against frozen Run authority,
  and persists only a canonical subject fingerprint in the Approval contract.
- **Tool Run Read Boundary**: `ExtensionToolRunContext` exposes frozen Resources by full
  `(kind,id)` identity, exact current-Run Artifact/relation reads, and
  `approval_authorizes(subject, ref)`. It never exposes a metadata Session, Artifact or
  Approval repository, raw credential vault, or global execution authority.
- **Cancellation Boundary**: every execution context exposes its Host-issued
  `invocation_id`. Timeout and Run cancellation call the Tool's generic
  `cancel(invocation_id)` hook; a capability owns the mapping from that opaque identity
  to its active external operation. Kernel does not inspect Resource kinds or import a
  domain query/job registry.
- **Transactional Staging**: Each DLC registers into an isolated staging scope. If any registration fails or conflicts, the staging scope is discarded, temporary `sys.modules` entries are purged, and the DLC is marked `BROKEN` without corrupting committed host registries.

### Dependency Policy (FROZEN)
1. **Allowed**:
   - Python Standard Library.
   - DBFox Host Extension SDK (pre-bundled in host binary).
   - Pure-Python vendored dependencies inside the DLC package directory (under `backend/vendor/` or package submodules).
2. **Prohibited**:
   - Native compiled C/Rust extensions (`.pyd`, `.so`, `.dylib`) are **STRICTLY PROHIBITED** in v1 in-process DLCs. R8A did not authorize a subprocess host.
   - Runtime package managers (`pip install`, `uv pip`, `setuptools`) are **STRICTLY PROHIBITED**.
   - DLC packages are contractually prohibited from mutating host `site-packages` or host environment variables. R8A confirms that trusted in-process code is not OS-blocked from attempting it.

### Realistic In-Process Trust & Isolation Claims
- **What IS Transactionally Contained**: Registration exceptions, syntax/import errors, duplicate identifier conflicts (rolled back, DLC marked `BROKEN`). This is not security isolation.
- **What is NOT Isolated in v1**: Infinite loops/hangs, `os._exit()`, and native memory corruption/crashes (these will terminate the sidecar process).
- **Process Isolation**: R8A closed NO-GO. No untrusted subprocess mode exists; a subprocess, module namespace, iframe, CSP, or Electron renderer sandbox alone is not represented as one.

---

## 5. Frontend Extension Host & Electron Asset Protocol

### Implementation Status
- **Frontend Feasibility**: Accepted and characterized in R0/R0.1.
- **Frontend Runtime Implementation**: Closed in R3 and migrated to the Electron Main boundary in R7.0.

### Electron Custom Protocol
- **URI Scheme**: `dlc-asset://localhost/<package_digest>/frontend/<path>`
- **Main Handler**:
  - Registered via Electron `protocol.handle("dlc-asset", ...)`.
  - Parses `<package_digest>` and checks that it exists in the verified Installed Registry.
  - Enforces canonical path containment within `APP_DATA/dlcs/packages/sha256-<digest>/frontend/`.
  - Sets exact MIME types: `.js`/`.mjs` $\rightarrow$ `text/javascript; charset=utf-8`, `.css` $\rightarrow$ `text/css; charset=utf-8`, `.svg` $\rightarrow$ `image/svg+xml`, `.png` $\rightarrow$ `image/png`.

### Production CSP (`main/appProtocol.ts`)
```text
default-src 'self';
script-src 'self' dlc-asset:;
style-src 'self' 'unsafe-inline' dlc-asset:;
img-src 'self' data: dlc-asset: https:;
font-src 'self' dlc-asset:;
connect-src 'self' http://127.0.0.1:* dlc-asset:;
base-uri 'none';
object-src 'none';
form-action 'none';
frame-ancestors 'none';
```
*Note: Script execution from `http://127.0.0.1:*` is strictly forbidden. Only `'self'` and the constrained `dlc-asset:` scheme can execute scripts.*

### Host SDK Binding & Error Isolation
- **Host SDK Injection**: DBFox Host initializes `window.__DBFOX_EXTENSION_HOST__` exposing React, ReactDOM, Lucide icons, UI primitives, and contribution registries.
- **Single React Instance**: DLC frontend bundles mark `react` and `react-dom` as external, sharing the host React runtime to avoid duplicate instance and Hook ABI mismatch bugs.
- **Error Boundaries**: Every dynamic Dock view, Connector, and Artifact card is wrapped in a `DlcErrorBoundary`. Render crashes are isolated with a fallback UI and disable action, preventing host white-screens.

---

## 6. Permission Grammar & Tool Capability Contract

### Two Distinct Concepts: Host Execution Capability vs DLC Declared Scope
1. **Host Execution Capability**: `ToolExecutionSpec.capabilities: tuple[ToolCapability, ...]`
   - Defined in DBFox tool runtime: `metadata_read`, `metadata_write`, `database_read`, `database_write`, `filesystem_read`, `filesystem_write`, `network`, `subprocess`.
2. **DLC Declared Scope**: Manifest `permissions`
   - Scoped strings declared in `manifest.json`: e.g. `network:api.github.com`, `credentials:github`, `filesystem_read:project_workspace`.

### Deterministic Coverage Mapping
When a DLC registers a Tool with `ToolExecutionSpec.capabilities`:
- `ToolCapability.network` $\implies$ Requires package permission `network` or matching `network:<domain>`.
- `ToolCapability.filesystem_read` $\implies$ Requires package permission `filesystem_read` or `filesystem_read:<scope>`.
- `ToolCapability.filesystem_write` $\implies$ Requires package permission `filesystem_write` or `filesystem_write:<scope>`.
- `ToolCapability.subprocess` $\implies$ Requires package permission `subprocess`.
- `ToolCapability.database_read` $\implies$ Requires package permission `database_read`.
- `ToolCapability.database_write` $\implies$ Requires package permission `database_write`.
- `ToolCapability.metadata_read` $\implies$ Requires package permission `metadata_read`.
- `ToolCapability.metadata_write` $\implies$ Requires package permission `metadata_write`.

*Note: The package permission grants the authority to register tools requiring the generic ToolCapability. Hostname/domain/path scope metadata (e.g. `api.github.com`) remains package policy metadata for disclosure and future mediated enforcement.*

---

## 7. Storage, Lifecycle & State Machine

### Storage Isolation
- **Trusted Publisher Store**: `APP_DATA/dlcs/trusted_publishers.json` is the only durable
  publisher-trust SSOT. Schema v1 contains a bounded `fingerprint -> public_key_base64`
  mapping and no arbitrary publisher metadata. It is strictly validated, written by same-directory
  temporary file + `fsync` + atomic replace, and corruption fails closed without overwrite.
- **Trust Confirmation Reverification**: Before persisting trust, DBFox re-reads the selected
  `.dbfox-dlc`, recomputes its archive digest, re-parses the signed embedded key, and re-verifies
  its signature. Both digest and key fingerprint must match the inspected prompt identity; this
  prevents UI parameter forgery and inspect/trust TOCTOU substitution.
- **Per-DLC Data Root**: Stored at `APP_DATA/dlcs/data/<dlc_id>/`; the DLC owns any
  database and migration layout below that directory. Uninstall retains this directory by default.
- **Core Independence**: The DLC manages its own migrations and schema lifecycle completely outside the Core Alembic migration graph.
- **Zero Core Mutation**: Installing or uninstalling a DLC never modifies `engine/models.py` or Core database tables.

### Lifecycle State Machine: Desired State vs Active Runtime Truth
- **Durable Desired State (`registry.json`)**:
  - `desired_enabled`: User's durable desired state.
  - `selected_digest`: The content-addressed digest selected for activation.
  - `installed_versions`: A bounded set of verified immutable digest/version identities and their
    publisher/install metadata. Installing another version appends to this set without selecting,
    executing, or deleting any package.
  - Schema v1 single-version records are read strictly and converted in memory; the next mutation
    atomically writes schema v2. There is no legacy dual-write path, and the redundant
    `runtime_state` field is removed rather than retained as a second truth source.
  - `registry.json` is the machine-level single-writer SSOT for durable user intent, NOT proof of what the running process has loaded.
- **Active Runtime Truth (`RuntimeContributionSnapshot`)**:
  - In-memory process truth built once at startup.
  - Contains immutable activated DLC identities (`dlc_id`, `package_version`, `package_digest`), tools, resource providers, resolvers, context contributors, artifact contracts, and operations.
  - `snapshot_id`: Deterministically derived from DBFox release identity + built-in composition + sorted activated DLC identities (`(dlc_id, package_digest, package_version)`).
  - Snapshot is NOT a database table.

### Local Lifecycle API
- The existing `X-Local-Token` and trusted Renderer origin middleware protects every lifecycle
  route; no second authentication mechanism or externally reachable listener is introduced.
- `POST /api/v1/dlcs/packages/inspect` authenticates a local `.dbfox-dlc` without installing or
  executing it. `POST /api/v1/dlcs/publishers/trust` re-authenticates the same digest and embedded
  key before committing trust. `POST /api/v1/dlcs/install` installs only a trusted package and
  always starts with `desired_enabled=false`.
- `GET /api/v1/dlcs` and `GET /api/v1/dlcs/{dlc_id}` derive lifecycle state by joining
  `registry.json` desired state with the current immutable `RuntimeContributionSnapshot`; the
  registry's legacy `runtime_state` field is never treated as active truth.
- `POST /api/v1/dlcs/{dlc_id}/enable` and `/disable` change desired state only. The stable wire
  states are `installed_disabled`, `enable_pending_restart`, `active`,
  `disable_pending_restart`, and `activation_failed`.
- `POST /api/v1/dlcs/{dlc_id}/versions/{package_digest}/select` changes only the selected digest.
  An enabled DLC keeps its old active digest until restart. Selecting an older digest is rollback
  of executable package identity only; DLC-owned data and schema are never rolled back.
- `DELETE /api/v1/dlcs/{dlc_id}/versions/{package_digest}` removes only an explicit unselected,
  inactive version. Selected or active digests fail closed; versions are never garbage-collected
  merely because another version was installed or selected.
- `DELETE /api/v1/dlcs/{dlc_id}` requires desired-disabled state and absence from active runtime
  truth. It removes the registry reference and unreferenced content-addressed executable bytes,
  while retaining `APP_DATA/dlcs/data/<dlc_id>/`.
- Rejections use the existing RFC 9457 `application/problem+json` boundary with bounded public
  codes; filesystem paths, verifier diagnostics, and tracebacks do not cross the API boundary.

### Desktop DLC Center
- DLC management lives inside the existing Settings shell. The Renderer receives only a narrow
  `pickDlcPackage` preload method, backed by Electron's native dialog and restricted to
  an existing single `.dbfox-dlc` file; no generic filesystem or dialog capability is exposed.
- Install from File is an explicit `pick → inspect → trust when required → install disabled`
  sequence. Trusting a publisher never installs the package, and neither inspect nor install
  executes extension code.
- Cards present `desired_enabled` beside current `active` truth and show selected and active
  digests independently. The installed-version list exposes Selected, Active, Pending restart,
  explicit Select/Roll back, and safe old-version removal while warning that package rollback does
  not roll back DLC data. Pending enable/disable state remains visible until the controlled engine
  restart produces a newer generation, passes health checks, and refreshes the runtime projection.
- Uninstall is disabled while desired-enabled or active. Its confirmation states that executable
  bytes may be removed while `APP_DATA/dlcs/data/<dlc_id>/` is retained by default.
- The UI adds no package registry cache or second state model; generated Lifecycle API responses
  remain the source for durable intent and runtime projection display.

### Packaged Lifecycle Release Contract
- The committed `acme.echo` source fixture owns a backend typed operation and Artifact contract,
  plus visible frontend Dock and Artifact renderer contributions. It imports only the public
  Extension API and is assembled with the host verifier's existing canonical package helper.
- The final frozen Sidecar smoke drives the exact product lifecycle sequence:
  `absent → install-disabled → enable-pending → restart-active exact digest → disable-pending →
  restart-absent → inactive uninstall/data retained`. It also rejects a payload-tampered archive
  before registry mutation and proves the activation marker is absent before restart.
- Electron Main's asset protocol contract serves the selected digest only while it is present in the active
  projection and returns `403` for that same old digest after projection reset. Frontend tests load
  the committed fixture module and stage both visible contribution types through the real Host.
- `release-platform-contract` runs this proof against the final PyInstaller Sidecar on Linux,
  Windows, and macOS and uploads a host-tuple-bound JSON evidence report beside each installer.

### Two-Tiered Tool Execution Identity
1. **Tool Contract Identity**:
   - `tool_name`, `declared_version`, `contract_hash`.
2. **Tool Implementation Identity**:
   - `owner_id`: Capability owner (built-in owner or `dlc_id`).
   - `package_digest`: Specific content-addressed `.dbfox-dlc` package digest for DLC tools (`None` for built-ins).
   - `ToolAttemptRequest` freezes both contract hash and `ToolImplementationIdentity`. Both parent and isolated worker verify this identity before execution, preventing silent substitution across package versions.

### Deterministic Lifecycle Transitions
```text
[ NOT_INSTALLED ]
       │  (Install from File)
       ▼
[ INSTALLED_DISABLED ] ──(Enable)──> [ ENABLE_PENDING_RESTART ] ──(Controlled Restart)──> [ ENABLED ]
       ▲                                                                                    │
       │                             (Disable)                                              │
       └─────────────────────── [ DISABLE_PENDING_RESTART ] <───────────────────────────────┘

Error States:
[ TAMPERED ]      (Digest / integrity mismatch on startup pre-verification)
[ INCOMPATIBLE ]  (DBFox or Extension API version incompatible)
[ BROKEN ]        (Registration exception during startup activation; isolated without corrupting host)
```

---

## 8. Cross-Platform Feasibility & R3/R5 Architecture Gates

### Cross-Platform Feasibility Status
- **Windows**: **Direct Production Proof** (Verified on native MSVC PyInstaller `--onefile` binary `dbfox-engine-x86_64-pc-windows-msvc.exe`).
- **macOS**: CI/release reproduction requirement (Mach-O bundle with Hardened Runtime).
- **Linux**: CI/release reproduction requirement (ELF onefile with locked glibc ABI).

### R3 Activation Projection Handoff Contract
- `RuntimeContributionSnapshot` generates a wire-safe `RuntimeDlcActivationProjection`:
  - `snapshot_id`
  - `active_dlcs: tuple[dict(dlc_id, package_digest, frontend_entrypoint), ...]`
- The Electron asset protocol serves frontend assets ONLY for packages present in the active projection, guaranteeing zero split-brain between Python backend runtime and the Main asset host.

### R5 GitHub Data Ownership Gate Requirement (FROZEN)
- R5 GitHub conformance DOES NOT pass merely by moving GitHub Python/TS code into `.dbfox-dlc`.
- **R5 Final Proof Requirement**:
  - Core ORM (`engine/models.py`) must have ZERO GitHub-owned runtime model dependencies.
  - GitHub DLC must own its durable storage in `APP_DATA/dlcs/data/dbfox.github/state.sqlite3`.
  - Historical Core migration files may remain, but existing user data must migrate/adapt cleanly.

---

## 9. Implementation Roadmap

- **R0 / R0.1**: Architecture Specification & Production Feasibility Closure (CLOSED).
- **R1**: Package Protocol, Verifier, Signature Engine & Installed Registry (CLOSED).
- **R2**: Runtime Composition Identity + Backend Extension Host (CLOSED).
- **R3**: Frontend Runtime DLC Host (custom asset protocol & dynamic ESM loader) (CLOSED).
- **R4.0**: Single-file Publisher Trust (CLOSED).
- **R4.1**: Local-authenticated Lifecycle API (CLOSED).
- **R4.2**: Install from File UI & DLC Center in Desktop App (CLOSED).
- **R4.3**: Packaged cross-platform lifecycle proof (CLOSED).
- **R5**: Conformance Proof & Data Ownership — Decouple `dbfox.github` into `dbfox.github-1.0.0.dbfox-dlc` (CLOSED).
- **R6**: Side-by-Side Update & Rollback Lifecycle (CLOSED).
- **R7.0**: Electron Host Cutover — replaced the old Host without rewriting the Python Engine or
  routing business APIs through IPC (CLOSED).
- **R7.1**: Developer SDK & Packaging CLI (`dbfox-dlc build/sign/test`) (CLOSED).
- **R8A**: Untrusted Isolation Gate (CLOSED — NO-GO; trusted-publisher-only remains authoritative).
- **R8B**: Not authorized. Reopens only if every criterion in `r8-untrusted-isolation-gate.md` can be proved on Windows, macOS, and Linux.

