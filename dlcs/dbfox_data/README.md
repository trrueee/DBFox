# dbfox.data

Official Data System DLC. Its durable model separates server/file connection
configuration (`ConnectionProfile`) from executable project resources
(`DatabaseResource`). A profile may own zero or many database resources; only
database resources are emitted as Agent authority.

Stage E exposes the canonical state and management operations. Stage F imports
legacy `DataSource` state and moves SQL, catalog, backup, completion, context,
and Workbench contributions onto this package.
