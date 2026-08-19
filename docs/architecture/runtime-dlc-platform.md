# Runtime DLC Platform Architecture & Feasibility Specification

## 1. Product Vision & Protocol-First Principle

### Product Vision
Any developer can build an extension conforming to the DBFox DLC Protocol, package it into a single `.dbfox-dlc` file, and distribute it directly to users. The user installs the package via **Install from File** in DBFox DLC Center, verifies and enables it, and all contributed capabilities (Tools, Resources, Context, Connectors, Dock Views, Artifact Renderers, Operations) become active after a controlled restart without modifying DBFox source code or recompiling the DBFox binary.

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

## 2. Current Static DLC Registration Map (Archaeology)

The DBFox product capabilities (Data, Workspace, GitHub) currently assemble at explicit compile-time composition roots. Runtime DLC Platform introduces dynamic registration into these exact same typed seams:

| Seam | Backend / Frontend | Compile-Time Baseline | Target Dynamic Host Seam |
|---|---|---|---|
| **Tool Extension** | Backend (`engine/runtime_composition.py`) | `register_data_extension`, `register_workspace_extension`, `register_github_extension` | `host.tools.register(...)` |
| **Resource Discovery** | Backend (`engine/runtime_composition.py`) | `list_database_resources`, `list_workspace_resources`, `list_github_resources` | `host.resources.register_provider(...)` |
| **Resource Resolution** | Backend (`engine/runtime_composition.py`) | `resolve_database`, `resolve_workspace`, `resolve_github` | `host.resources.register_resolver(...)` |
| **Context Contribution** | Backend (`engine/runtime_composition.py`) | `WorkspaceContextContributor`, `GitHubContextContributor` | `host.context.register(...)` |
| **Completion Constraints** | Backend (`engine/runtime_composition.py`) | `DataResultCitationConstraint` | `host.completion.register(...)` |
| **Artifact Contract** | Backend (`engine/agent/artifact.py`, `engine/github/contracts.py`) | `register_artifact_payload_contract` | `host.artifacts.register(...)` |
| **Operations / API** | Backend (`engine/api/`) | Static FastAPI routers (`/datasources`, `/projects/{id}/github`) | `POST /api/v1/dlcs/{dlc_id}/operations/{op}` |
| **Resource Connector** | Frontend (`desktop/src/features/resources/`) | `productResourceConnectors()` | `host.connectors.register(...)` |
| **Requested Resources** | Frontend (`desktop/src/features/resources/`) | `PRODUCT_REQUESTED_RESOURCE_CONTRIBUTORS` | `host.requestedResources.register(...)` |
| **Dock Views** | Frontend (`desktop/src/features/dock/`) | `productDockViews()` | `host.dockViews.register(...)` |
| **Artifact Renderers** | Frontend (`desktop/src/features/workspace/artifacts/`) | `productArtifactRenderers` | `host.artifactRenderers.register(...)` |

---

## 3. Package Format & Cryptographic Envelope

### Package Archive Layout (`.dbfox-dlc`)
An immutable ZIP-based archive with strict bounds and deterministic entry layout:
```text
<package_root>/
├── manifest.json       # Lifecycle metadata, compatibility bounds, permission declarations
├── integrity.json      # File SHA256 digest mapping for all package files (excluding signature.sig)
├── signature.sig       # Ed25519 digital signature of canonical manifest + integrity bytes
├── backend/            # Backend Python extension code
│   ├── __init__.py
│   ├── entry.py        # def register(host: BackendExtensionHost) -> None
│   └── vendor/         # Optional pure-Python vendored dependencies
├── frontend/           # Frontend pre-compiled ES module & styles
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
2. **`integrity.json` Entry Contract**:
   - Maps normalized POSIX relative file paths (`backend/entry.py`, `frontend/index.js`, etc.) to lowercase 64-character SHA256 hex digests.
   - `signature.sig` is **STRICTLY EXCLUDED** from `integrity.json`.
   - `manifest.json` and all other files inside the archive **MUST** be listed in `integrity.json`.
3. **Signed Message Bytes**:
   ```text
   b"DBFOX-DLC-V1\n" + canonical_manifest_bytes + b"\n" + canonical_integrity_bytes
   ```
4. **Signature Verification**:
   - Verified using Ed25519 against the publisher's public key.
   - Publisher Key ID: SHA256 fingerprint of raw Ed25519 public key bytes.
5. **Path Normalization & Archive Validation**:
   - Forward slashes `/` as path separators.
   - No leading `./` or `/`.
   - Rejection of `..` path traversal segments, absolute paths, symlinks, hardlinks, and device files.
   - Rejection of duplicate normalized paths (case-insensitive collisions).
   - Rejection of unlisted archive entries (every file in the ZIP must match an entry in `integrity.json`).

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
- **Registration Surface**:
  ```python
  class BackendExtensionHost:
      tools: ToolRegistrationScope
      resources: ResourceRegistrationScope
      context: ContextRegistrationScope
      artifacts: ArtifactRegistrationScope
      operations: OperationRegistrationScope
  ```
- **Transactional Staging**: Each DLC registers into an isolated staging scope. If any registration fails or conflicts, the staging scope is discarded and the DLC is marked `BROKEN` without corrupting committed host registries.

### Dependency Policy (FROZEN)
1. **Allowed**:
   - Python Standard Library.
   - DBFox Host Extension SDK (pre-bundled in host binary).
   - Pure-Python vendored dependencies inside the DLC package directory (e.g. `backend/vendor/` or subpackages).
2. **Prohibited**:
   - Native compiled C/Rust extensions (`.pyd`, `.so`, `.dylib`) are **STRICTLY PROHIBITED** in v1 in-process DLCs (deferred to R8 subprocess host).
   - Runtime package managers (`pip install`, `uv pip`, `setuptools`) are **STRICTLY PROHIBITED**.
   - DLC packages cannot mutate host `site-packages` or host environment variables.

### Realistic In-Process Trust & Isolation Claims
- **What IS Isolated**: Registration exceptions, syntax/import errors, duplicate identifier conflicts (transactionally rolled back, DLC marked `BROKEN`).
- **What is NOT Isolated in v1**: Infinite loops/hangs, `os._exit()`, and native memory corruption/crashes (these will terminate the sidecar process).
- **Process Isolation**: True process-level security isolation is deferred to R8 (Subprocess DLC Host).

---

## 5. Frontend Extension Host & Tauri Asset Protocol

### Tauri Custom Protocol
- **URI Scheme**: `dlc-asset://localhost/<package_digest>/frontend/<path>`
- **Rust Handler**:
  - Registered via `tauri::Builder::default().register_uri_scheme_protocol("dlc-asset", ...)`.
  - Parses `<package_digest>` and checks that it exists in the verified Installed Registry.
  - Enforces canonical path containment within `APP_DATA/dlcs/packages/sha256-<digest>/frontend/`.
  - Sets exact MIME types: `.js`/`.mjs` $\rightarrow$ `text/javascript; charset=utf-8`, `.css` $\rightarrow$ `text/css; charset=utf-8`, `.svg` $\rightarrow$ `image/svg+xml`, `.png` $\rightarrow$ `image/png`.

### Production CSP (`tauri.conf.json`)
```text
default-src 'self';
script-src 'self' dlc-asset:;
style-src 'self' 'unsafe-inline' dlc-asset:;
img-src 'self' data: dlc-asset: https:;
font-src 'self' dlc-asset:;
connect-src 'self' http://127.0.0.1:*;
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

### Manifest Permission Grammar
```text
Permission := "network" | "network:" Domain
            | "credentials" | "credentials:" CredentialType
            | "filesystem_read" | "filesystem_read:" Scope
            | "filesystem_write" | "filesystem_write:" Scope
            | "subprocess"
```

### Deterministic Checking Contract
When a DLC registers a Tool with `ToolExecutionSpec.security.required_capabilities`:
- `required_capabilities.network == true` $\implies$ Requires package permission `network` or matching `network:<domain>`.
- `required_capabilities.filesystem == true` $\implies$ Requires package permission `filesystem_read` or `filesystem_write`.
- `required_capabilities.subprocess == true` $\implies$ Requires package permission `subprocess`.
- **Enforcement**: If a Tool declares capabilities exceeding the package's declared permissions, tool registration is rejected during staging and the DLC is marked `BROKEN`.

---

## 7. Storage, Lifecycle & State Machine

### Storage Isolation
- **Per-DLC SQLite Database**: Stored at `APP_DATA/dlcs/data/<dlc_id>.sqlite3`.
- **Core Independence**: The DLC manages its own migrations and schema lifecycle completely outside the Core Alembic migration graph.
- **Zero Core Mutation**: Installing or uninstalling a DLC never modifies `engine/models.py` or Core database tables.

### Lifecycle State Machine
- **Desired State vs Runtime State**:
  - `desired_enabled`: User's desired configuration stored in `registry.json`.
  - `runtime_loaded`: Active registration in the currently running process.
- **Deterministic Transitions**:
  ```text
  [ NOT_INSTALLED ]
         │  (Install from File)
         ▼
  [ INSTALLED_DISABLED ] ──(Enable)──> [ ENABLE_PENDING_RESTART ] ──(Controlled Restart)──> [ ENABLED ]
         ▲                                                                                    │
         │                             (Disable)                                              │
         └─────────────────────── [ DISABLE_PENDING_RESTART ] <───────────────────────────────┘

  Error States:
  [ TAMPERED ]      (Digest mismatch on startup)
  [ INCOMPATIBLE ]  (DBFox or Extension API version incompatible)
  [ BROKEN ]        (Registration exception during startup activation)
  ```
- **Uninstall Data Retention**: Uninstall disables and removes executable package bytes only. Domain data in `APP_DATA/dlcs/data/<dlc_id>.sqlite3` is preserved by default unless the user explicitly triggers "Delete DLC Data". Historical Agent records (Runs, Turns, Invocations, Observations, Artifacts) remain immutable.

---

## 8. Cross-Platform Feasibility Status

- **Windows**: **Direct Production Proof** (Verified on native MSVC PyInstaller `--onefile` binary `dbfox-engine-x86_64-pc-windows-msvc.exe`).
- **macOS**: CI/release reproduction requirement (Mach-O bundle with Hardened Runtime).
- **Linux**: CI/release reproduction requirement (ELF onefile with locked glibc ABI).

---

## 9. Implementation Roadmap

- **R0 / R0.1**: Architecture Specification & Production Feasibility Closure (CURRENT).
- **R1**: Package Protocol, Verifier, Signature Engine & Installed Registry (No code execution).
- **R2**: Backend Runtime DLC Host (In-process transactional registration & fault isolation).
- **R3**: Frontend Runtime DLC Host (Tauri custom asset protocol & dynamic ESM loader).
- **R4**: Install from File UI & DLC Center in Desktop App.
- **R5**: Conformance Proof — Decouple `dbfox.github` into `dbfox.github-1.0.0.dbfox-dlc`.
- **R6**: Side-by-Side Update & Rollback Lifecycle.
- **R7**: Developer SDK & Packaging CLI (`dbfox-dlc build/sign/test`).
- **R8**: Untrusted Subprocess Sandbox Gate.
