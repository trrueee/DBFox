from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("dbfox.semantic.alias")

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
    """Simple alias resolver: built-in defaults + DB-stored aliases (exact match only).

    NOTE: Vector semantic recall and formula expansion were removed in the MVP
    simplification (2026-06-20).  The resolver now only performs exact keyword
    matching against a merged builtin + DB alias map.
    """

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
        self.db_alias_keys: set[str] = set()

    @classmethod
    def from_db(
        cls,
        db: "Session",
        datasource_id: str,
    ) -> "SemanticAliasResolver":
        """Build a resolver that merges DB-stored aliases with built-in defaults.

        DB aliases take priority over DEFAULT_ALIASES.
        """
        from engine.models import SemanticAlias

        resolver = cls()

        rows = (
            db.query(SemanticAlias)
            .filter(
                SemanticAlias.data_source_id == datasource_id,
                SemanticAlias.target_type != "sensitive"
            )
            .all()
        )
        db_aliases: dict[str, str] = {}
        for row in rows:
            db_aliases[row.alias] = row.target  # type: ignore[index,assignment]

        resolver.aliases = {**DEFAULT_ALIASES, **db_aliases}
        resolver.db_alias_keys = set(db_aliases.keys())  # type: ignore[attr-defined]

        return resolver

    def resolve(self, text: str) -> list[AliasMatch]:
        """Exact keyword match against the merged alias map."""
        if not text:
            return []

        normalized_text = text.lower()
        matches: list[AliasMatch] = []
        seen_targets: set[str] = set()

        for alias, target in self.aliases.items():
            if alias.lower() not in normalized_text:
                continue
            parsed = self._parse_target(alias, target)
            parsed.source = "db" if alias in self.db_alias_keys else "builtin"
            parsed.reason = f"exact_match:{parsed.alias}->{parsed.target}[source={parsed.source}]"

            target_lower = parsed.target.lower()
            if target_lower not in seen_targets:
                seen_targets.add(target_lower)
                matches.append(parsed)

        return matches

    def _parse_target(self, alias: str, target: str) -> AliasMatch:
        source = "db" if alias in self.db_alias_keys else "builtin"
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
