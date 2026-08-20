"""Compatibility and version constraint evaluation for DBFox DLC packages."""

from __future__ import annotations

import re
from dataclasses import dataclass

from engine.dlc.errors import DlcError, DlcErrorCode

CURRENT_DBFOX_VERSION = "1.0.3"
CURRENT_EXTENSION_API_VERSION = "1"
SUPPORTED_MANIFEST_SCHEMA_VERSIONS = {1, 2}


@dataclass(frozen=True)
class SemVer:
    major: int
    minor: int
    patch: int
    prerelease: str | None = None

    @classmethod
    def parse(cls, version_str: str) -> SemVer:
        m = re.match(
            r"^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)"
            r"(?:-(?P<prerelease>[0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?$",
            version_str.strip(),
        )
        if not m:
            raise ValueError(f"Invalid semver: '{version_str}'")
        return cls(
            major=int(m.group("major")),
            minor=int(m.group("minor")),
            patch=int(m.group("patch")),
            prerelease=m.group("prerelease"),
        )

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        if (self.major, self.minor, self.patch) != (other.major, other.minor, other.patch):
            return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)
        if self.prerelease is None and other.prerelease is not None:
            return False
        if self.prerelease is not None and other.prerelease is None:
            return True
        return (self.prerelease or "") < (other.prerelease or "")

    def __le__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self == other or self < other

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return not self <= other

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return not self < other



def parse_semver_constraint(constraint_str: str) -> list[tuple[str, SemVer]]:
    """Parse semver constraint like '>=1.0.0, <2.0.0' or '^1.0.0' or '>=1.0.0'."""
    clauses: list[tuple[str, SemVer]] = []
    parts = [p.strip() for p in constraint_str.split(",") if p.strip()]
    for part in parts:
        m = re.match(r"^(>=|<=|>|<|==|=|~=|\^)?\s*([0-9A-Za-z.-]+)$", part)
        if not m:
            raise ValueError(f"Unsupported version constraint syntax: '{part}'")
        op = m.group(1) or "=="
        if op == "=":
            op = "=="
        ver = SemVer.parse(m.group(2))
        clauses.append((op, ver))
    return clauses


def check_version_satisfies(target_version: str, constraint_str: str) -> bool:
    """Check if target_version satisfies semver constraint_str."""
    target = SemVer.parse(target_version)
    clauses = parse_semver_constraint(constraint_str)
    for op, required in clauses:
        if op == "==" and target != required:
            return False
        if op == ">=" and not (target >= required):
            return False
        if op == "<=" and not (target <= required):
            return False
        if op == ">" and not (target > required):
            return False
        if op == "<" and not (target < required):
            return False
        if op == "^":
            # Compatible with major version
            if target < required:
                return False
            if target.major != required.major:
                return False
    return True


def check_dlc_compatibility(
    manifest_schema_version: int,
    extension_api_version: str,
    requires_dbfox: str,
    *,
    dbfox_version: str = CURRENT_DBFOX_VERSION,
) -> None:
    """Check manifest schema, extension API, and DBFox version compatibility."""
    if manifest_schema_version not in SUPPORTED_MANIFEST_SCHEMA_VERSIONS:
        raise DlcError(
            DlcErrorCode.INCOMPATIBLE_SCHEMA,
            f"Unsupported manifest schema version: {manifest_schema_version}. Supported versions: {SUPPORTED_MANIFEST_SCHEMA_VERSIONS}",
        )

    if extension_api_version != CURRENT_EXTENSION_API_VERSION:
        raise DlcError(
            DlcErrorCode.INCOMPATIBLE_EXTENSION_API,
            f"Incompatible extension API version '{extension_api_version}'. Current DBFox API version: '{CURRENT_EXTENSION_API_VERSION}'",
        )

    try:
        satisfies = check_version_satisfies(dbfox_version, requires_dbfox)
    except Exception as exc:
        raise DlcError(
            DlcErrorCode.INCOMPATIBLE_DBFOX_VERSION,
            f"Malformed requiresDbfox constraint '{requires_dbfox}': {exc}",
        ) from exc

    if not satisfies:
        raise DlcError(
            DlcErrorCode.INCOMPATIBLE_DBFOX_VERSION,
            f"DBFox version '{dbfox_version}' does not satisfy DLC requirement '{requires_dbfox}'",
        )
