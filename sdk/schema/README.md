# DLC package schemas

`manifest.schema.json` is generated from the Host's Pydantic manifest model.
The generated JSON Schema documents field types and bounds; the Host verifier
remains authoritative for cross-field version rules, archive integrity,
signature authenticity, trust, compatibility, and entrypoint presence.

CI runs the exporter in `--check` mode so this artifact cannot drift from the
runtime model.
