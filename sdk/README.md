# DBFox DLC SDK

The SDK is a productized view of the contracts already enforced by the DBFox
runtime. It does not define a second runtime or package format.

- `frontend/` is the canonical TypeScript declaration package consumed by the
  DBFox renderer and DLC authors.
- `schema/manifest.schema.json` is generated from `engine.dlc.manifest.DlcManifest`.
- Backend extensions import the public Extension API from `dbfox_dlc_api`.
- Package authors use `dbfox-dlc` through `tools/dbfox-dlc` on macOS/Linux or
  `tools\dbfox-dlc.cmd` on Windows.

Regenerate the checked-in manifest schema with:

```text
python scripts/export_dlc_sdk_contracts.py
```
