"""Typed Pydantic manifest schema and validation for DBFox DLC packages."""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


from engine.dlc.errors import DlcError, DlcErrorCode

DLC_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
PUBLISHER_ID_PATTERN = re.compile(r"^[a-z0-9]+(?:[._-][a-z0-9]+)*$")
SEMVER_PATTERN = re.compile(
    r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
    r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?(?:\+(?P<buildmetadata>[0-9A-Za-z.-]+))?$"
)
PERMISSION_TOKEN_PATTERN = re.compile(r"^[a-z0-9_]+(?::[a-zA-Z0-9_./-]+)?$")


class DlcEntrypoints(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    backend: str | None = Field(default="backend/entry.py", max_length=255)
    frontend: str | None = Field(default="frontend/index.js", max_length=255)


class DlcManifest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    manifest_schema_version: int = Field(
        alias="manifestSchemaVersion",
        default=1,
        ge=1,
        le=1,
    )
    id: str = Field(min_length=3, max_length=64)
    version: str = Field(min_length=1, max_length=64)
    display_name: str = Field(alias="displayName", min_length=1, max_length=128)
    publisher: str = Field(min_length=2, max_length=64)
    description: str = Field(default="", max_length=1024)
    extension_api_version: str = Field(
        alias="extensionApiVersion",
        default="1",
        min_length=1,
        max_length=16,
    )
    requires_dbfox: str = Field(
        alias="requiresDbfox",
        default=">=1.0.0",
        min_length=1,
        max_length=64,
    )
    entrypoints: DlcEntrypoints = Field(default_factory=DlcEntrypoints)
    permissions: list[str] = Field(default_factory=list, max_length=64)

    @field_validator("id")
    @classmethod
    def validate_dlc_id(cls, v: str) -> str:
        if not DLC_ID_PATTERN.match(v):
            raise DlcError(
                DlcErrorCode.INVALID_MANIFEST,
                f"Invalid DLC id format: '{v}'. Must be lowercase alphanumeric with '.', '_', or '-'.",
            )
        return v

    @field_validator("publisher")
    @classmethod
    def validate_publisher(cls, v: str) -> str:
        if not PUBLISHER_ID_PATTERN.match(v):
            raise DlcError(
                DlcErrorCode.INVALID_MANIFEST,
                f"Invalid publisher id format: '{v}'. Must be lowercase alphanumeric with '.', '_', or '-'.",
            )
        return v

    @field_validator("version")
    @classmethod
    def validate_version(cls, v: str) -> str:
        if not SEMVER_PATTERN.match(v):
            raise DlcError(
                DlcErrorCode.INVALID_MANIFEST,
                f"Invalid semver version format: '{v}'.",
            )
        return v

    @field_validator("permissions")
    @classmethod
    def validate_permissions(cls, v: list[str]) -> list[str]:
        seen = set()
        for p in v:
            if not isinstance(p, str) or len(p) > 128:
                raise DlcError(
                    DlcErrorCode.INVALID_MANIFEST,
                    f"Permission token too long or not a string: '{p}'",
                )
            if not PERMISSION_TOKEN_PATTERN.match(p):
                raise DlcError(
                    DlcErrorCode.INVALID_MANIFEST,
                    f"Invalid permission token format: '{p}'",
                )
            if p in seen:
                raise DlcError(
                    DlcErrorCode.INVALID_MANIFEST,
                    f"Duplicate permission token: '{p}'",
                )
            seen.add(p)
        return v

    @model_validator(mode="after")
    def validate_entrypoints_non_empty(self) -> "DlcManifest":
        if not self.entrypoints.backend and not self.entrypoints.frontend:
            raise DlcError(
                DlcErrorCode.INVALID_MANIFEST,
                "DLC manifest must declare at least one backend or frontend entrypoint.",
            )
        return self

    @classmethod
    def from_bytes(cls, raw_bytes: bytes) -> "DlcManifest":
        """Parse and strictly validate manifest from raw UTF-8 JSON bytes."""
        import json

        if len(raw_bytes) > 64 * 1024:
            raise DlcError(
                DlcErrorCode.PACKAGE_TOO_LARGE,
                f"manifest.json exceeds 64 KiB limit ({len(raw_bytes)} bytes)",
            )
        try:
            payload = json.loads(raw_bytes.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise DlcError(
                DlcErrorCode.INVALID_MANIFEST,
                f"Malformed JSON in manifest.json: {exc}",
            ) from exc

        if not isinstance(payload, dict):
            raise DlcError(
                DlcErrorCode.INVALID_MANIFEST,
                "manifest.json must be a JSON object",
            )

        try:
            return cls.model_validate(payload)
        except DlcError:
            raise
        except Exception as exc:
            raise DlcError(
                DlcErrorCode.INVALID_MANIFEST,
                f"Validation failed for manifest.json: {exc}",
            ) from exc
