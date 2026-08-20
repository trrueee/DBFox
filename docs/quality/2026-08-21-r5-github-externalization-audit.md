# R5.0 GitHub Externalization Seam Audit

> 文档类型：质量证据 / 架构审计
>
> 状态：当前
>
> 最后核验：2026-08-21

Baseline: `main@8d182f24eb349f154d4a44c01041fb07c69a1b3a`

## Decision

`dbfox.github` can be externalized through the existing Runtime DLC contribution
model. R5 must reuse the current Tool, Resource, Artifact, Context, Operation,
Connector, Requested Resource, Dock and Artifact Renderer seams. It must not add a
PluginManager, Service Locator, domain router, mirrored registry, or GitHub branch
to either Kernel.

Three general gaps are proven by the existing GitHub vertical and are added in
R5.0:

1. Context contributors receive a bounded projection of canonical succeeded
   Observation/Artifact pairs. This is an in-memory projection, not a second
   durable fact source, and oversized payloads are omitted.
2. Frontend extensions receive `host.operations.invoke(...)`. The host binds the
   active `dlc_id`; extension code cannot name or invoke another DLC.
3. Frontend extensions may open a Dock envelope only for a `viewType` registered
   by that same staged host. The private Workspace store is not exposed.

No dependency is added.

## Current dependency map

| GitHub responsibility | Current Core/static dependency | R5 target |
|---|---|---|
| Repository bindings | `GithubRepositoryBinding` in Core ORM | DLC-owned `state.sqlite3` |
| Binding/file HTTP API | Static `/projects/{id}/github` router | Typed DLC operations |
| Public GitHub client | `engine/github/service.py` | DLC backend source |
| Tools | Static `register_github_extension` | `host.tools.register` |
| Resource discovery/resolution | Static compiler imports | `host.resources` |
| Context rehydration | Direct Core Session queries | Bounded canonical Artifact input |
| Artifact schema | Import-time Core registration | `host.artifacts.register` |
| Connector/requested resource | Product composition arrays | Frontend host registration |
| Dock/Artifact presentation | Product composition arrays | Frontend host registration |
| Frontend management calls | Generated GitHub API client | DLC-bound operation invocation |

## Reuse assessment

- `DlcRuntimeInfo.data_path` is the sole runtime storage boundary. GitHub will use
  `<data_path>/state.sqlite3`.
- `DlcOperationSpec(scope="project")` already validates project existence and
  supplies the authoritative `project_id`; a second domain API router is not
  required.
- Resource providers can capture DLC-owned storage and receive only `project_id`.
  Resolvers can capture the same store and receive only the frozen resource ref.
- Tool settlement, package digest identity, Artifact validation and Context
  budgets remain Kernel-owned.
- React and ReactDOM remain host externals. GitHub bundles its other frontend
  implementation and scoped CSS; Core does not provide GitHub UI components.

## Rejected alternatives

- Keeping the static GitHub API as a compatibility facade would create dual
  routing and prevent the no-package absence proof.
- Letting DLC code access SQLAlchemy `Session` would expose Core persistence and
  preserve the current ownership violation.
- Writing a second DLC read-history log would duplicate canonical Observation and
  Artifact truth.
- Exposing Zustand stores or arbitrary navigation would turn the frontend host
  into a Service Locator.
- Adding GitHub fields to ContextSnapshot or the Workbench Shell would reintroduce
  domain branching.

## Migration boundary

R5.2 may contain one explicit, idempotent import from the historical Core table
into DLC storage. It must commit the DLC database before recording completion,
must never delete or mutate historical Core rows, and must not dual-write. The
bridge is removable once all supported pre-R5 databases have crossed the migration
floor; no new runtime code may depend on the old model.

The authoritative target path is
`APP_DATA/dlcs/data/dbfox.github/state.sqlite3`. Older architecture text using
`data/dbfox.github.sqlite3` is superseded and must be corrected with R5.2.

## Verification strategy

- R5.0: primitive unit tests, typecheck, focused backend/frontend suites.
- R5.1: build and activate a real `dbfox.github` package using only public API.
- R5.2: migration idempotency, failure preservation and restart tests.
- R5.3: static import/model/API/CSS absence checks.
- R5.4: no-package, install-disabled, restart-active, restart-inactive and retained
  data conformance tests.

This change introduces no compatibility layer, mapper, dependency, or second
durable source of truth.
