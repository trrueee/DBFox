from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

import numpy as np

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("databox.semantic.alias")

DEFAULT_ALIASES: dict[str, str] = {
    "销售额": "orders.total_amount",
    "GMV": "orders.total_amount",
    "订单金额": "orders.total_amount",
    "用户": "users",
    "客户": "users",
}


@dataclass
class AliasMatch:
    alias: str
    target: str
    target_type: str
    table_name: str
    column_name: str | None = None
    source: str = "builtin"
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.reason:
            self.reason = f"alias_match:{self.alias}->{self.target}[source={self.source}]"


class SemanticAliasResolver:
    """Alias resolver backed by a dict, DB-stored aliases, and vector semantic recall."""

    # Class-level cache mapping datasource_id -> dict with:
    # {"max_updated": datetime, "alias_matrix": np.ndarray, "aliases": list[SemanticAlias]}
    _vector_cache: dict[str, dict] = {}

    def __init__(
        self,
        aliases: Mapping[str, str] | None = None,
        json_path: str | Path | None = None,
    ) -> None:
        merged = dict(DEFAULT_ALIASES)
        if aliases:
            merged.update(dict(aliases))
        if json_path:
            merged.update(self._load_json_aliases(Path(json_path)))
        self.aliases = merged
        self.enable_embedding_recall = False
        self.datasource_id = None
        self.cache = None
        self.api_key = None
        self.api_base = None
        self.model_name = None
        self._embed_service = None

    @classmethod
    def from_db(
        cls,
        db: "Session",
        datasource_id: str,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> "SemanticAliasResolver":
        """Build a resolver that merges DB-stored aliases with built-in defaults.

        DB aliases take priority over DEFAULT_ALIASES.

        Also loads cached vector embeddings from the database into a class-level
        cache.  The cache is invalidated when any alias in the datasource has an
        ``updated_at`` timestamp newer than the cached ``max_updated``.
        """
        from engine.models import SemanticAlias, DataSource
        from sqlalchemy import func

        resolver = cls()
        resolver.datasource_id = datasource_id
        resolver.api_key = api_key
        resolver.api_base = api_base
        resolver.model_name = model_name

        # Check if datasource has embedding recall enabled
        ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
        resolver.enable_embedding_recall = ds.enable_embedding_recall if ds else False

        # Load all aliases for this data source
        rows = db.query(SemanticAlias).filter(SemanticAlias.data_source_id == datasource_id).all()
        db_aliases: dict[str, str] = {}
        db_meta: dict[str, dict[str, str]] = {}
        for row in rows:
            db_aliases[row.alias] = row.target  # type: ignore[index,assignment]
            db_meta[str(row.alias)] = {
                "target_type": str(row.target_type),
                "source": "db",
                "id": row.id
            }

        # DB takes priority — update over defaults
        resolver.aliases = {**DEFAULT_ALIASES, **db_aliases}
        resolver.db_alias_keys = set(db_aliases.keys())  # type: ignore[attr-defined]
        resolver.db_meta = db_meta

        # Cache management for vector embeddings
        if resolver.enable_embedding_recall and rows:
            try:
                # Query max(updated_at) to detect if cache is stale
                max_updated = db.query(func.max(SemanticAlias.updated_at)).filter(
                    SemanticAlias.data_source_id == datasource_id
                ).scalar()

                cached = cls._vector_cache.get(datasource_id)
                # Use > to avoid false positives from μs-precision mismatch
                if not cached or (max_updated is not None and max_updated > cached.get("max_updated")):
                    # Rebuild vector matrix cache
                    embeddings = []
                    cached_aliases = []
                    expected_dim = None
                    for row in rows:
                        if row.embedding_blob:
                            vec = np.frombuffer(row.embedding_blob, dtype=np.float32)
                            if len(vec) > 0:
                                if expected_dim is None:
                                    expected_dim = len(vec)
                                if len(vec) == expected_dim:
                                    embeddings.append(vec)
                                    cached_aliases.append(row)
                                else:
                                    logger.warning(
                                        "Skipping embedding for alias %s (dim=%d, expected=%d) — "
                                        "model may have changed. Re-sync embeddings.",
                                        row.alias, len(vec), expected_dim,
                                    )

                    if embeddings:
                        alias_matrix = np.vstack(embeddings)
                        cls._vector_cache[datasource_id] = {
                            "max_updated": max_updated,
                            "alias_matrix": alias_matrix,
                            "aliases": cached_aliases,
                        }
                    else:
                        cls._vector_cache[datasource_id] = {
                            "max_updated": max_updated,
                            "alias_matrix": None,
                            "aliases": [],
                        }

                resolver.cache = cls._vector_cache.get(datasource_id)
            except Exception as e:
                logger.warning("Failed to load or construct embedding cache: %s", e)
                resolver.cache = None
        else:
            resolver.cache = None

        return resolver

    def resolve(self, text: str) -> list[AliasMatch]:
        """Resolve aliases from text using dual-route (exact + vector) recall & formula expansion."""
        if not text:
            return []

        normalized_text = text.lower()
        matches: list[AliasMatch] = []
        exact_targets: set[str] = set()

        # 1. Phase 1: Keyword Exact Matching
        for alias, target in self.aliases.items():
            if alias.lower() not in normalized_text:
                continue
            parsed = self._parse_target(alias, target)
            parsed.source = "db" if hasattr(self, "db_alias_keys") and alias in self.db_alias_keys else "builtin"
            parsed.reason = f"exact_match:{parsed.alias}->{parsed.target}[source={parsed.source}]"
            matches.append(parsed)
            exact_targets.add(parsed.target.lower())

        # 2. Phase 2: Vector Semantic Recall (if enabled)
        if self.enable_embedding_recall and self.cache and self.cache.get("alias_matrix") is not None:
            try:
                if self._embed_service is None:
                    from engine.semantic.embeddings import EmbeddingService
                    self._embed_service = EmbeddingService(
                        api_key=self.api_key,
                        api_base=self.api_base,
                        model_name=self.model_name,
                    )
                query_embeddings = self._embed_service.embed([text])
                if query_embeddings:
                    query_vec = np.array(query_embeddings[0], dtype=np.float32)
                    alias_matrix = self.cache["alias_matrix"]
                    cached_aliases = self.cache["aliases"]

                    # Compute batch cosine similarities
                    from engine.semantic.embeddings import EmbeddingService
                    similarities = EmbeddingService.batch_cosine(query_vec, alias_matrix)
                    for idx, sim in enumerate(similarities):
                        if sim >= 0.75:
                            alias_row = cached_aliases[idx]
                            target_lower = alias_row.target.lower()
                            # Deduplicate: prioritize exact match if already retrieved
                            if target_lower not in exact_targets:
                                parsed = self._parse_target(alias_row.alias, alias_row.target)
                                parsed.source = "vector_recall"
                                parsed.reason = f"vector_recall:{alias_row.alias}->{alias_row.target}[similarity={sim:.4f}]"
                                matches.append(parsed)
            except Exception as e:
                logger.error("Vector semantic recall failed: %s", e)

        # 3. Synonym Decompounding / Formula Resolution
        expanded_matches: list[AliasMatch] = []
        for match in matches:
            expanded = self._resolve_compound_targets(match)
            expanded_matches.extend(expanded)

        # Deduplicate final matches by (alias, target)
        seen: set[tuple[str, str]] = set()
        final_matches: list[AliasMatch] = []
        for m in expanded_matches:
            identity = (m.alias.lower(), m.target.lower())
            if identity not in seen:
                seen.add(identity)
                final_matches.append(m)

        return final_matches

    def _resolve_compound_targets(
        self, match: AliasMatch, depth: int = 0, visited: set[str] | None = None
    ) -> list[AliasMatch]:
        """Recursively resolve formulas/compound targets into physical column/table references.

        - Physical references (containing ``.`` like ``orders.price``) are returned as-is.
        - Formula targets (``\u9500\u91cf * \u4ef7\u683c``) are split into tokens and each token is
          resolved against known aliases.
        - A shared ``visited`` set prevents infinite loops across sibling branches.
        - ``depth`` provides an additional safety limit (max 5 levels).
        """
        if visited is None:
            visited = set()

        # Stop infinite recursion or deep cycles
        if depth >= 5:
            return [match]

        # Physical column reference \u2014 no decomposition needed
        if "." in match.target:
            return [match]

        visited.add(match.alias.lower())

        # Split into tokens (English words + Chinese characters)
        words = re.findall(r"[a-zA-Z0-9_\u4e00-\u9fff]+", match.target)

        sub_matches: list[AliasMatch] = []
        for word in words:
            word_lower = word.lower()
            # Skip self-reference and already-visited aliases
            if word_lower == match.alias.lower() or word_lower in visited:
                continue

            if word in self.aliases:
                sub_target = self.aliases[word]
                sub_match = self._parse_target(word, sub_target)
                sub_match.reason = f"{sub_match.reason} (formula: {match.alias})"
                # Recursively expand with shared visited set
                resolved = self._resolve_compound_targets(sub_match, depth + 1, visited)
                sub_matches.extend(resolved)

        if not sub_matches:
            # No sub-aliases found, this match itself is a leaf
            return [match]

        return sub_matches

    def _parse_target(self, alias: str, target: str) -> AliasMatch:
        source = "db" if hasattr(self, "db_alias_keys") and alias in self.db_alias_keys else "builtin"
        normalized_target = target.strip()
        if "." in normalized_target:
            table_name, column_name = normalized_target.split(".", 1)
            match = AliasMatch(
                alias=alias,
                target=normalized_target,
                target_type="column",
                table_name=table_name.strip(),
                column_name=column_name.strip(),
                source=source,
            )
        else:
            match = AliasMatch(
                alias=alias,
                target=normalized_target,
                target_type="table",
                table_name=normalized_target,
                source=source,
            )
        return match

    def _load_json_aliases(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return {}

            aliases: dict[str, str] = {}
            for alias, target in raw.items():
                if isinstance(alias, str) and isinstance(target, str):
                    aliases[alias] = target
            return aliases
        except Exception as e:
            logger.warning("Failed to load JSON aliases from %s: %s", path, e)
            return {}
