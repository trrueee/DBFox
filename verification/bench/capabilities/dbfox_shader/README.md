# Shader capability bench

Status: current. This suite is owned by Shader verification; no Shader concepts were added to Core or the shared benchmark framework.

`capability.dbfox-shader.scripted` installs the **complete signed DLC**, verifies archived frontend bytes, creates migrated metadata, and runs the production Agent RunLoop, native Responses tool calls, Tool Runtime, resource authorization, observation/context projection, Artifact repository and public representation executor. Only model Responses are scripted. Human edits use registered public operations with separate request identities; their results never become model observations until a formal inspect. The fixture setup follows existing Core/Scene/Pixel suites and adds no dependency or production abstraction.

From the repository root, with the normal isolated test environment:

```powershell
python -m pytest verification/tests/bench/test_shader_bench.py -q --tb=short
```

For the unified CLI, inject an unused temporary `DBFOX_RUNTIME_DIR` and `DBFOX_TESTING=1` **before** Python starts, then:

```powershell
python -m verification.bench run capability.dbfox-shader.scripted --output <new-report-directory>
```

The runtime package, SQLite and signing fixture remain in a task-specific external temporary directory. Reports contain domain facts and producer identities, not credentials. Use `--case` to select a case. Repetitions are capped at five. `build_cases.py` reproduces the versioned dataset without calling product implementation helpers.

## Coverage and independent scoring

The fifteen cases cover creation, incremental source editing, a two-pass pipeline, recovery from a self-cycle, inspect-before-edit, stale version, no-op, explicit clarification in a second Run, a large document, bounded context, human-then-Agent editing, a negative read-only request, missing GPU execution, texture binding, and a multi-change procedural artwork.

The scorer independently reconstructs full canonical documents using fixed-version public pages and source windows, computes their SHA-256, checks every untouched object and field, validates exact final content, version increments and no-ops, and checks current head for hidden mutation. It reads complete texture bytes through the public boundary and independently verifies the requested four-corner RGBA order. It proves Artifact producer/run/resource identity and availability, and executes the registered representation to check its fixed version/fingerprint even after later changes. A scorer sensitivity test rejects incorrect source, missing Artifacts and replayed invocations.

The large task creates **62 stages / 438,486 canonical JSON bytes** in twenty bounded three-module mutations, then follows returned page cursors without omission or duplication. Another task creates 128 distinct uniforms in two batches. The stress task produces a five-octave domain-warped Coral Plasma and an ordered copy pass; it performs ten changed Agent mutations after creation, a separate human edit, a rejected stale mutation, explicit clarification, undo and refinement, reaching v12. Its exact canonical source and all producing calls are in the [trial evidence](evidence/domain/trials.json).

Frozen product `4df3568d`, signed digest `c252765548a9bce655c3e996d5877aff55dabb97a0e18e44c479f79118543565`: **17 tests passed / 28.41 seconds; CLI 15/15**. Maximum model observation is 8,260 bytes; the largest task uses 26 tool calls / 27 turns. [Report](evidence/domain/report.md), [summary](evidence/domain/summary.json), and [environment](evidence/domain/environment.json) retain the concrete evidence. Pyflakes passed for the suite and test file.

## Scope and remaining gates

No compute bridge is attached or simulated. Missing-executor compile and preview fail explicitly, preserve v1 and produce no successful compute Artifact. The production loop limits further work after consecutive failures; the script then reports the actual failure. A saved source, a shader-related title or a `compiled=true` fixture is never treated as GPU proof. **Successful driver compilation, error repair, visual preview and PNG export still require independent production Electron verification**, including the same Sidecar process as the activation executor. This suite is not a real-LLM creativity score, a completed separate red-team review, or the complete Shader Lead exit gate.

The initial large-task fixture sent all sixty modules in one roughly 410 KiB model call. That mutation committed, while the next model window did not contain its native output; forcing old v1 reads could not recover new IDs. The final fixture retains the full document size and uses bounded batches instead of increasing Core context budgets or reading private state into the model. The initial phenomenon is explicitly handed to the independent verifier for a focused compaction/recovery investigation. The two consecutive missing-GPU failures also exposed an incorrect fixture expectation that read tools would remain available; the fixture now follows the production finalization policy. Neither adjustment changes product behavior or weakens domain size, locality or no-replay assertions.
