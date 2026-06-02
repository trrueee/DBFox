from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Mapping

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


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
    """Minimal alias resolver backed by a dict or an optional JSON file."""

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

    @classmethod
    def from_db(cls, db: "Session", datasource_id: str) -> "SemanticAliasResolver":
        """Build a resolver that merges DB-stored aliases with built-in defaults.

        DB aliases take priority over DEFAULT_ALIASES.
        """
        from engine.models import SemanticAlias

        resolver = cls()
        rows = db.query(SemanticAlias).filter(SemanticAlias.data_source_id == datasource_id).all()
        db_aliases: dict[str, str] = {}
        db_meta: dict[str, dict[str, str]] = {}
        for row in rows:
            db_aliases[row.alias] = row.target
            db_meta[row.alias] = {"target_type": row.target_type, "source": "db"}
        # DB takes priority — update over defaults
        resolver.aliases = {**DEFAULT_ALIASES, **db_aliases}
        resolver.db_alias_keys = set(db_aliases.keys())
        return resolver

    def resolve(self, text: str) -> list[AliasMatch]:
        normalized_text = text.lower()
        matches: list[AliasMatch] = []
        seen: set[tuple[str, str]] = set()

        for alias, target in self.aliases.items():
            if alias.lower() not in normalized_text:
                continue
            parsed = self._parse_target(alias, target)
            identity = (parsed.alias.lower(), parsed.target.lower())
            if identity in seen:
                continue
            seen.add(identity)
            matches.append(parsed)

        return matches

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
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {}

        aliases: dict[str, str] = {}
        for alias, target in raw.items():
            if isinstance(alias, str) and isinstance(target, str):
                aliases[alias] = target
        return aliases
