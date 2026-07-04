# Data View Source Contracts Design

## Goal

DBFox has three ways to read tabular data: agent result artifacts, direct table preview, and SQL Console execution. These paths share pagination/export infrastructure, but their source identity and safety rules are different and must stay explicit.

## Source Contracts

### Result Artifact Source

Result artifact views are derived from a persisted SQL artifact. The client may request pagination/export with a source SQL artifact id and the displayed safe SQL, but the backend must load the persisted SQL artifact, verify the fingerprint, and only then compile filter, search, sort, page, or export SQL.

The artifact payload uses physical keys for stable persisted references:

- `sourceSqlArtifactKey`
- `sourceSqlSemanticKey`
- `safetyArtifactKey`
- `safetySemanticKey`

Readers must also accept legacy payload keys:

- `sourceSqlArtifactId`
- `sourceSqlSemanticId`
- `safetyArtifactId`
- `safetySemanticId`

### Table Source

Direct table preview is not an agent artifact. It is backed by synced schema catalog metadata and must identify a table by `datasourceId + tableId`. `tableName` is display context only and must not be the authoritative lookup key.

The backend loads `SchemaTable` by id and datasource, loads synced columns by table id, and builds a schema-qualified `SELECT * FROM schema.table` when schema metadata is present. Filter, search, sort, page, and export SQL are compiled by the shared result-view compiler and validated as derived SQL.

### SQL Console Source

SQL Console is the only user-authored SQL execution path in this design. It must run the full safety path:

`PolicyEngine -> SqlSafetyService/TrustGate -> execute_query`

Successful console executions create SQL, safety, and result-view artifacts. Subsequent pagination/export uses the Result Artifact Source path, not a console-specific shortcut.

## Error Contract

Result-view module errors are raised as `ResultViewError` and converted at the API boundary with `public_error`. Endpoint-local not-found checks should also return structured `public_error` payloads instead of plain string details.

## Non-Goals

This design does not introduce a public reusable SQL memory API. Datasource reusable SQL remains agent-internal context.
