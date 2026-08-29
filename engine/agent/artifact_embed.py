"""Canonical inline Artifact authoring syntax for terminal Markdown answers."""

from __future__ import annotations

import re


ARTIFACT_EMBED_PATTERN = re.compile(
    r"\{\{artifact:(artifact_[A-Za-z0-9_-]+)\}\}"
)
_ARTIFACT_EMBED_PREFIX = "{{artifact:"
MAX_ARTIFACT_EMBEDS = 8


def artifact_embed_references(text: str) -> list[tuple[str, int, int]]:
    """Return embedded Artifact identities in document order with stable offsets."""

    return [
        (match.group(1), match.start(), match.end())
        for match in ARTIFACT_EMBED_PATTERN.finditer(text)
    ]


def has_invalid_artifact_embed_syntax(text: str) -> bool:
    """Require every reserved embed token to be valid and on its own Markdown line."""

    prefix_starts = {
        match.start()
        for match in re.finditer(re.escape(_ARTIFACT_EMBED_PREFIX), text)
    }
    matches = list(ARTIFACT_EMBED_PATTERN.finditer(text))
    if prefix_starts != {match.start() for match in matches}:
        return True
    for match in matches:
        line_start = text.rfind("\n", 0, match.start()) + 1
        line_end = text.find("\n", match.end())
        if line_end < 0:
            line_end = len(text)
        if text[line_start:line_end].strip() != match.group(0):
            return True
    return False


def artifact_embed_ids(text: str) -> list[str]:
    return [artifact_id for artifact_id, _, _ in artifact_embed_references(text)]


def has_duplicate_artifact_embeds(text: str) -> bool:
    artifact_ids = artifact_embed_ids(text)
    return len(artifact_ids) != len(set(artifact_ids))
