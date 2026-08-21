# R8A Untrusted Isolation Gate

> 文档类型：安全架构决策 / GO-NO-GO Gate
>
> 状态：当前
>
> 最后核验：2026-08-21
>
> 决策基线：`main@2625ac366113c031149fd226075932ddca0739b2`

## Decision

R8A is **NO-GO**. DBFox does not enable an untrusted DLC execution mode and does
not start R8B. Production DLCs remain authenticated trusted code: a package must
have valid integrity and signature evidence, its publisher must be explicitly
trusted, and activation re-verifies the selected digest and trust state after
restart.

This is a product boundary, not a temporary implementation gap. Under the
current two-language target (TypeScript/Electron desktop plus Python Engine),
there is no shared, mature primitive that gives arbitrary Python and JavaScript
the required filesystem, secret, network, subprocess, resource, crash, DOM, and
native-bridge containment on Windows, macOS, and Linux. Claiming otherwise would
turn cooperative manifest permissions into a fake sandbox.

## Threat model and required proof

The attacker controls every byte of a correctly signed DLC after the user has
chosen to run it as *untrusted*. Publisher authenticity is not treated as benign
behavior. A GO requires adversarial tests proving all of these boundaries:

| Surface | Required default-deny guarantee |
|---|---|
| Filesystem | Backend sees only its immutable package and explicitly granted data roots; no home, project, app data, keyring database, devices, or arbitrary paths. |
| Secrets and environment | No parent environment, local Engine token, inherited privileged handles/file descriptors, credential-vault access, or unrelated DLC state. |
| Network and subprocess | No direct network or child-process authority. Allowed operations cross typed, authenticated Host IPC with bounded inputs and outputs. |
| Resources | CPU time, memory, process count, output, storage, and wall time are enforced by the OS boundary; descendants cannot escape the limits. |
| Crash and lifecycle | Import, registration, execution, hang, crash, and forced termination cannot terminate or permanently stall the Engine or product Renderer. |
| Frontend | No product DOM, cookies/storage, Engine token, preload bridge, navigation, external network, or cross-DLC access. Only serializable typed messages cross the boundary. |

## Current implementation evidence

The current Host is intentionally correct for trusted code and fails the
untrusted threat model:

- `ContributionCompiler` imports the selected package and calls `register(host)`
  inside the Python Engine process. The module namespace prevents name
  collisions, but arbitrary imports can still reach `os`, `pathlib`, `socket`,
  `subprocess`, process environment, Engine memory, and OS credential APIs.
- Dynamic DLC tools are required to use the `in_process` backend. Manifest
  capabilities are checked against typed registrations; they do not mediate
  direct Python syscalls.
- `IsolatedProcessAttemptRunner` is a bounded transport for selected built-in
  tool attempts. Its child inherits ambient environment and OS access, and it
  has no AppContainer, App Sandbox/XPC, Landlock/seccomp, or cgroup policy. It is
  crash/timeout isolation, not hostile-code containment.
- Frontend modules are dynamically imported into the product Renderer and return
  React callbacks. They share the application DOM and can call the product's
  exposed `window.dbfoxDesktop` bridge. In particular, `engine.getConfig()`
  returns the local Engine bearer token. Error boundaries isolate React callback
  failures only; they cannot contain DOM mutation, data exfiltration, infinite
  loops, renderer crashes, or bridge calls.
- The `dlc-asset:` protocol proves digest/activity/path containment for package
  bytes. Electron `sandbox: true`, context isolation, CSP, navigation denial,
  and sender validation protect the product from ordinary web attacks, but code
  deliberately imported into the trusted product realm receives that realm's
  authority.

## Platform primitive evaluation

| Platform | Mature primitives investigated | Result for DBFox R8 |
|---|---|---|
| Windows | AppContainer / `CreateProcessInSandbox`, explicit environment and handle lists, Job Objects for process-tree and resource limits | Technically promising, but absent from the current Node/Python launcher and not a portable contract. It requires a Windows-specific broker/launcher, AppContainer filesystem/network policy, packaging compatibility, and adversarial escape tests. A plain Job Object controls resources but does not remove filesystem, token, registry, or network authority. |
| macOS | App Sandbox entitlements, sandbox inheritance, security-scoped access, and per-service XPC sandbox/privilege separation | Blocking. A normal child process is not an independent least-privilege boundary; Apple recommends XPC for privilege separation. DBFox has no separately signed XPC service, entitlement profile, broker, or notarized adversarial proof. Adding one would reintroduce a native platform service and change the fixed two-language/release architecture. |
| Linux | Landlock, seccomp-BPF, namespaces, cgroup v2, or an external container helper such as a Flatpak/bubblewrap boundary | Individually insufficient as the product contract. Kernel documentation explicitly states seccomp is not a sandbox. Landlock availability/ABI and network coverage vary, while cgroup limits require a delegated hierarchy. DBFox cannot silently fall back on hosts lacking the configured kernel/packaging boundary. |
| Electron frontend | Sandboxed renderer plus isolated origin/session, denied permissions/navigation/network, and no preload; `WebContentsView` as a possible process surface | Chromium can provide a credible starting boundary, but the current Frontend Host exchanges React functions and nodes in the product realm. A safe design requires a new serializable remote-UI protocol and a brokered operation API. `iframe`, `webview`, `WebContentsView`, context isolation, or CSP alone does not preserve the current API while isolating hostile code. |

## Rejected shortcuts

- Python `multiprocessing`, `subprocess`, virtual environments, import hooks, and
  module namespaces do not remove ambient OS authority.
- Cooperative manifest permissions and public SDK types describe intended Host
  use; arbitrary code can bypass them.
- Electron `utilityProcess` provides a Node-capable child process, not the
  required Python filesystem/network/secret sandbox.
- An iframe or separate Renderer without a distinct origin/session, no-preload
  policy, network mediation, resource controls, and typed serialization is not a
  complete frontend boundary.
- Maintaining separate trusted and pseudo-isolated implementations of the same
  contribution model would create dual semantics and a second runtime contract.

## R8B re-entry criteria

R8B stays unauthorized unless one proposal proves all items below before product
implementation begins:

1. One versioned, serializable backend IPC contract replaces every callable or
   Python object crossing the untrusted boundary; no Core object is exposed.
2. Windows AppContainer + Job Object, macOS separately signed XPC/App Sandbox,
   and Linux verified Landlock/seccomp/cgroup (or an equally strong packaged
   boundary) launchers all fail closed when unavailable.
3. Children receive an explicit minimal environment and handle/FD list, have no
   direct Engine token or credential-vault access, deny network/subprocess by
   default, and access only broker-granted filesystem roots.
4. Frontend code runs in a dedicated sandboxed process, origin, and ephemeral
   session with no product preload. A serializable remote-UI protocol replaces
   React callbacks; permissions, navigation, downloads, and requests are denied
   unless a typed broker grants them.
5. Packaged Windows, macOS, and Linux adversarial suites prove file, secret,
   network, subprocess, process-tree, CPU/memory, crash, DOM, bridge, navigation,
   and cross-DLC escape negatives. There is no unsupported-platform fallback.
6. The product owner explicitly accepts the native helpers, signing/notarization
   requirements, maintenance burden, and departure from the current two-language
   architecture.

## Reuse decision and debt

The investigation preferred OS and Electron security primitives over a custom
sandbox. None composes into the required cross-platform boundary without new
platform-specific launchers and a new serializable frontend/backend execution
model. Therefore DBFox adds no dependency, native helper, compatibility layer,
permission mapper, fallback chain, or second SSOT in R8A. The trusted R1-R7 path
remains unchanged.

## Primary references

- Microsoft: [AppContainer isolation](https://learn.microsoft.com/windows/win32/secauthz/appcontainer-isolation), [Create Process In Sandbox](https://learn.microsoft.com/windows/win32/secauthz/createprocessinsandbox), and [Job Objects](https://learn.microsoft.com/windows/win32/procthread/job-objects)
- Apple: [App Sandbox](https://developer.apple.com/documentation/security/app_sandbox), [App Sandbox inheritance](https://developer.apple.com/library/archive/documentation/Miscellaneous/Reference/EntitlementKeyReference/Chapters/EnablingAppSandbox.html), and [XPC Services](https://developer.apple.com/library/archive/documentation/MacOSX/Conceptual/BPSystemStartup/Chapters/CreatingXPCServices.html)
- Linux kernel: [Landlock](https://docs.kernel.org/userspace-api/landlock.html), [seccomp-BPF](https://docs.kernel.org/userspace-api/seccomp_filter.html), and [cgroup v2](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html)
- Electron: [Security checklist](https://www.electronjs.org/docs/latest/tutorial/security), [Process sandboxing](https://www.electronjs.org/docs/latest/tutorial/sandbox), [Web embeds](https://www.electronjs.org/docs/latest/tutorial/web-embeds), and [Session permissions](https://www.electronjs.org/docs/latest/api/session)
