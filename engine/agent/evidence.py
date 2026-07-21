"""Precise links from answer claims to immutable Agent artifacts."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


CITATION_PATTERN = re.compile(r"\{\{cite:(artifact_[A-Za-z0-9_-]+)\}\}")


def citation_references(text: str) -> list[tuple[str, int, int]]:
    """Return explicit Artifact citations with stable answer offsets."""
    return [(match.group(1), match.start(), match.end()) for match in CITATION_PATTERN.finditer(text)]


class EvidenceLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["artifact", "metric", "column", "row", "cell_range", "sql_fragment"] = "artifact"
    value: dict[str, Any] = Field(default_factory=dict)


class Evidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    session_id: str
    run_id: str
    claim_id: str
    artifact_id: str
    label: str
    query_fingerprint: str
    observed_at: datetime
    locator: EvidenceLocator = Field(default_factory=EvidenceLocator)
    value: str | int | float | None = None
