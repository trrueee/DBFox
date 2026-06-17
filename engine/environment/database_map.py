"""Database Map — the Agent's "world model" of a datasource.

Combines static schema metadata (from catalog) with dynamic intelligence
(from memory / usage history) to give the Agent a rich understanding of
the database beyond raw DDL.

Layers:
  Layer 1 — Catalog:      tables, columns, PKs, FKs (from schema introspector)
  Layer 2 — Profiles:     null rates, distinct counts, sample values, enum guesses
  Layer 3 — Relationships: FK + inferred joins + user-verified joins
  Layer 4 — Semantics:    business terms → columns, metric definitions
  Layer 5 — Usage:        query frequency, successful join paths
  Layer 6 — Risk:         sensitive columns, PROD tables, large tables
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from engine.environment.models import CatalogSnapshot, TableSnapshot, ColumnSnapshot

logger = logging.getLogger("dbfox.environment.database_map")

# ── Risk / sensitivity ─────────────────────────────────────────────────────────

RiskLevel = Literal["safe", "warning", "danger", "unknown"]
ColumnCategory = Literal[
    "id", "foreign_key", "dimension", "metric", "timestamp",
    "text", "json", "boolean", "enum", "unknown",
]
TableCategory = Literal[
    "fact", "dimension", "bridge", "lookup", "log", "config", "unknown",
]


# ── Map data models ────────────────────────────────────────────────────────────


class ColumnProfile(BaseModel):
    """Intelligence-augmented column metadata."""

    column_name: str
    data_type: str = ""
    is_nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    fk_target: str | None = None  # "table.column"

    # Profiling (populated by live sampling when available)
    null_rate: float | None = None  # 0.0–1.0
    distinct_count: int | None = None
    sample_values: list[str] = Field(default_factory=list)
    enum_guess: list[str] = Field(default_factory=list)

    # Classification
    category: ColumnCategory = "unknown"
    is_sensitive: bool = False
    sensitivity_reason: str = ""

    # Semantic tags (from memory — business terms mapped to this column)
    semantic_tags: list[str] = Field(default_factory=list)


class TableProfile(BaseModel):
    """Intelligence-augmented table metadata."""

    table_name: str
    table_type: str = "table"

    # Stats
    row_count_estimate: int | None = None
    column_count: int = 0

    # Classification
    category: TableCategory = "unknown"
    business_module: str = ""  # e.g. "user", "order", "payment"
    description: str = ""

    # Columns
    columns: list[ColumnProfile] = Field(default_factory=list)

    # Risk
    risk_level: RiskLevel = "unknown"
    risk_reasons: list[str] = Field(default_factory=list)
    is_prod: bool = False

    # Usage heat (from memory trajectories)
    query_count: int = 0
    last_queried_at: str | None = None

    # Foreign keys (normalized form)
    foreign_keys: list[str] = Field(default_factory=list)  # "col → table.col"


class Relationship(BaseModel):
    """A known or inferred relationship between two tables."""

    from_table: str
    from_column: str
    to_table: str
    to_column: str

    source: Literal["fk_catalog", "inferred_naming", "inferred_data",
                     "user_verified", "trajectory_seen"] = "fk_catalog"
    confidence: float = 1.0  # 0.0–1.0
    usage_count: int = 0


class DatabaseMap(BaseModel):
    """Complete intelligence model of a datasource.

    Built from catalog snapshot + memory store + live profiling.
    Cached in agent state and refreshed when catalog changes.
    """

    datasource_id: str
    generated_at: str = ""

    # Layer 1: Catalog
    tables: list[TableProfile] = Field(default_factory=list)
    table_names: list[str] = Field(default_factory=list)

    # Layer 3: Relationships (all types)
    relationships: list[Relationship] = Field(default_factory=list)

    # Layer 4: Semantic index (term → table.column)
    semantic_index: dict[str, list[str]] = Field(default_factory=dict)

    # Layer 5: Usage stats
    total_query_count: int = 0
    most_queried_tables: list[str] = Field(default_factory=list)
    successful_join_paths: list[str] = Field(default_factory=list)

    # Layer 6: Risk
    prod_tables: list[str] = Field(default_factory=list)
    sensitive_columns: list[str] = Field(default_factory=list)  # "table.column"

    # ── Query helpers ──────────────────────────────────────────────────────

    def get_table(self, name: str) -> TableProfile | None:
        """Look up a table by exact or case-insensitive name."""
        for t in self.tables:
            if t.table_name.lower() == name.lower():
                return t
        return None

    def find_column(self, table_name: str, column_name: str) -> ColumnProfile | None:
        """Find a specific column in a table."""
        table = self.get_table(table_name)
        if table is None:
            return None
        for c in table.columns:
            if c.column_name.lower() == column_name.lower():
                return c
        return None

    def find_tables_by_module(self, module: str) -> list[TableProfile]:
        """Find tables belonging to a business module."""
        return [t for t in self.tables if t.business_module == module]

    def find_join_path(
        self, from_table: str, to_table: str
    ) -> list[Relationship]:
        """Find all known join paths between two tables."""
        results: list[Relationship] = []
        for r in self.relationships:
            if (r.from_table.lower() == from_table.lower()
                    and r.to_table.lower() == to_table.lower()):
                results.append(r)
            elif (r.from_table.lower() == to_table.lower()
                    and r.to_table.lower() == from_table.lower()):
                results.append(r)
        # Sort by confidence
        results.sort(key=lambda r: (r.confidence, r.usage_count), reverse=True)
        return results

    def resolve_term(self, term: str) -> list[str]:
        """Resolve a business term to table.column references."""
        term_lower = term.lower()
        results: list[str] = []
        for sem_term, targets in self.semantic_index.items():
            if term_lower in sem_term.lower():
                results.extend(targets)
        return results

    def find_sensitive_columns(self, table_name: str) -> list[str]:
        """List sensitive columns in a table."""
        return [sc for sc in self.sensitive_columns
                if sc.lower().startswith(table_name.lower() + ".")]

    def module_summary(self) -> dict[str, list[str]]:
        """Return tables grouped by business module."""
        groups: dict[str, list[str]] = {}
        for t in self.tables:
            module = t.business_module or "ungrouped"
            groups.setdefault(module, []).append(t.table_name)
        return groups

    def relationship_summary(self) -> str:
        """Compact relationship summary for prompt injection."""
        lines: list[str] = []
        for r in self.relationships[:20]:
            conf = "✓" if r.source == "fk_catalog" else f"~{r.confidence:.0%}"
            lines.append(
                f"{r.from_table}.{r.from_column} → "
                f"{r.to_table}.{r.to_column} [{conf}]"
            )
        return "\n".join(lines) if lines else "No relationships cataloged."


# ── Builder ────────────────────────────────────────────────────────────────────


class DatabaseMapBuilder:
    """Assembles a DatabaseMap from catalog + memory + heuristics."""

    def __init__(self) -> None:
        from engine.policy.sensitivity import _SENSITIVE_FALLBACK
        self._sensitive_re = _SENSITIVE_FALLBACK
        self._large_table_threshold: int = 1_000_000

    # ── Public API ─────────────────────────────────────────────────────────

    def build(
        self,
        catalog: CatalogSnapshot,
        *,
        memory_store: Any | None = None,
        profiles: dict[str, Any] | None = None,
    ) -> DatabaseMap:
        """Build a DatabaseMap from a catalog snapshot + optional enrichments."""
        tables = self._build_tables(catalog)
        relationships = self._build_relationships(catalog, tables)
        semantic_index = self._build_semantic_index(memory_store)
        usage = self._build_usage_stats(memory_store, catalog.datasource_id)
        risk = self._build_risk_profile(tables)

        # Enrich with live profiles if available
        if profiles:
            self._apply_profiles(tables, profiles)

        # Apply usage heat to tables
        self._apply_usage_heat(tables, usage)

        return DatabaseMap(
            datasource_id=catalog.datasource_id,
            generated_at=datetime.now(timezone.utc).isoformat(),
            tables=tables,
            table_names=[t.table_name for t in tables],
            relationships=relationships,
            semantic_index=semantic_index,
            total_query_count=usage.get("total", 0),
            most_queried_tables=usage.get("top_tables", []),
            successful_join_paths=usage.get("join_paths", []),
            prod_tables=risk["prod_tables"],
            sensitive_columns=risk["sensitive_columns"],
        )

    # ── Table building ─────────────────────────────────────────────────────

    def _build_tables(self, catalog: CatalogSnapshot) -> list[TableProfile]:
        tables: list[TableProfile] = []
        for ts in catalog.tables:
            columns = self._build_columns(ts)
            category = self._classify_table(ts.table_name, columns)
            module = self._guess_module(ts.table_name)

            risk: RiskLevel = "unknown"
            risk_reasons: list[str] = []
            is_prod = False

            tables.append(TableProfile(
                table_name=ts.table_name,
                table_type=ts.table_type,
                row_count_estimate=ts.row_count_estimate,
                column_count=len(columns),
                category=category,
                business_module=module,
                description=ts.comment or "",
                columns=columns,
                risk_level=risk,
                risk_reasons=risk_reasons,
                is_prod=is_prod,
            ))
        return tables

    def _build_columns(self, ts: TableSnapshot) -> list[ColumnProfile]:
        columns: list[ColumnProfile] = []
        for cs in ts.columns:
            category = self._classify_column(cs.column_name, cs.data_type)
            is_sensitive = self._is_sensitive(cs.column_name)

            fk_target: str | None = None
            # FK target resolution happens in _build_relationships via
            # ForeignKeySnapshot — ColumnSnapshot does not carry target IDs.

            columns.append(ColumnProfile(
                column_name=cs.column_name,
                data_type=cs.data_type,
                is_nullable=cs.is_nullable,
                is_primary_key=cs.is_primary_key,
                is_foreign_key=cs.is_foreign_key,
                fk_target=fk_target,
                category=category,
                is_sensitive=is_sensitive,
                sensitivity_reason="name matches sensitive pattern" if is_sensitive else "",
            ))
        return columns

    # ── Relationship building ──────────────────────────────────────────────

    def _build_relationships(
        self,
        catalog: CatalogSnapshot,
        tables: list[TableProfile],
    ) -> list[Relationship]:
        relationships: list[Relationship] = []

        # 1. FK relationships from catalog
        col_map: dict[str, TableProfile] = {}
        for t in tables:
            col_map[t.table_name.lower()] = t

        # FK from explicit catalog relationships (ForeignKeySnapshot)
        for fk in catalog.relationships:
            relationships.append(Relationship(
                from_table=ts.table_name,
                from_column=fk.column_name,
                to_table=fk.referenced_table,
                to_column=fk.referenced_column,
                source="fk_catalog",
                confidence=1.0,
            ))

        # 2. Inferred joins by naming convention (col_id → table.col)
        for t in tables:
            for col in t.columns:
                if col.column_name.endswith("_id") and not col.is_foreign_key:
                    ref_table = col.column_name[:-3]  # e.g., "account_id" → "account"
                    if ref_table in col_map or f"{ref_table}s" in col_map:
                        actual = ref_table if ref_table in col_map else f"{ref_table}s"
                        # Only add if not already present
                        if not any(
                            r.from_table == t.table_name
                            and r.from_column == col.column_name
                            and r.to_table == actual
                            for r in relationships
                        ):
                            relationships.append(Relationship(
                                from_table=t.table_name,
                                from_column=col.column_name,
                                to_table=actual,
                                to_column="id",
                                source="inferred_naming",
                                confidence=0.5,
                            ))

        return relationships

    # ── Semantic index ─────────────────────────────────────────────────────

    def _build_semantic_index(
        self, memory_store: Any | None
    ) -> dict[str, list[str]]:
        """Build term → column mapping from memory store."""
        index: dict[str, list[str]] = {}
        if memory_store is None:
            return index

        try:
            records = memory_store.search(
                types=["metric_definition", "schema_alias"],
                limit=50,
            )
            for r in records:
                if r.type == "metric_definition":
                    term = r.content.get("metric_name") or r.text.split("→")[0].strip()
                    expr = r.content.get("sql_expression") or r.content.get("business_definition", "")
                    if term and expr:
                        index.setdefault(term, []).append(expr)
                elif r.type == "schema_alias":
                    alias = r.content.get("alias") or r.text
                    target = r.content.get("target") or ""
                    if alias and target:
                        index.setdefault(alias, []).append(target)
        except Exception:
            pass

        return index

    # ── Usage stats ────────────────────────────────────────────────────────

    def _build_usage_stats(
        self, memory_store: Any | None, datasource_id: str
    ) -> dict[str, Any]:
        stats: dict[str, Any] = {
            "total": 0, "top_tables": [], "join_paths": [],
        }
        if memory_store is None:
            return stats

        try:
            records = memory_store.search(
                types=["successful_trajectory"],
                datasource_id=datasource_id,
                limit=50,
            )
            stats["total"] = len(records)

            table_counts: dict[str, int] = {}
            join_paths: list[str] = []

            for r in records:
                tables = r.content.get("selected_tables") or r.content.get("tables") or []
                for t in tables:
                    tn = str(t)
                    table_counts[tn] = table_counts.get(tn, 0) + 1

                jps = r.content.get("join_paths") or []
                for jp in jps:
                    if isinstance(jp, str) and jp not in join_paths:
                        join_paths.append(jp)

            stats["top_tables"] = sorted(
                table_counts, key=table_counts.get, reverse=True
            )[:10]
            stats["join_paths"] = join_paths[:10]
        except Exception:
            pass

        return stats

    # ── Risk profile ───────────────────────────────────────────────────────

    def _build_risk_profile(
        self, tables: list[TableProfile]
    ) -> dict[str, list[str]]:
        prod_tables: list[str] = []
        sensitive_columns: list[str] = []

        for t in tables:
            if t.is_prod:
                prod_tables.append(t.table_name)
            if t.row_count_estimate and t.row_count_estimate > self._large_table_threshold:
                if t.table_name not in prod_tables:
                    t.risk_reasons.append(f"large table ({t.row_count_estimate} rows)")
                    t.risk_level = "warning"

            for c in t.columns:
                if c.is_sensitive:
                    sensitive_columns.append(f"{t.table_name}.{c.column_name}")

        return {
            "prod_tables": prod_tables,
            "sensitive_columns": sensitive_columns,
        }

    # ── Classification heuristics ──────────────────────────────────────────

    def _classify_table(
        self, name: str, columns: list[ColumnProfile]
    ) -> TableCategory:
        nl = name.lower()
        if any(kw in nl for kw in ("fact", "sales", "transaction", "event")):
            return "fact"
        if any(kw in nl for kw in ("dim_", "dimension", "lookup", "ref_")):
            return "dimension"
        if any(kw in nl for kw in ("bridge", "map", "xref", "junction")):
            return "bridge"
        if any(kw in nl for kw in ("log", "audit", "history", "archive")):
            return "log"
        if any(kw in nl for kw in ("config", "setting", "param")):
            return "config"
        # Heuristic: many foreign keys → fact; many text/name columns → dimension
        fk_count = sum(1 for c in columns if c.is_foreign_key)
        pk_count = sum(1 for c in columns if c.is_primary_key)
        if fk_count >= 2:
            return "fact"
        if pk_count == 1 and fk_count <= 1:
            return "dimension"
        return "unknown"

    def _classify_column(self, name: str, data_type: str) -> ColumnCategory:
        nl = name.lower()
        dt = data_type.lower()

        if nl in ("id",) or nl.endswith("_id"):
            if nl == "id":
                return "id"
            return "foreign_key"
        if any(kw in nl for kw in ("name", "label", "title", "description", "type", "status", "category")):
            return "dimension"
        if any(kw in nl for kw in ("amount", "price", "total", "count", "sum", "qty", "quantity", "revenue", "cost")):
            return "metric"
        if any(kw in nl for kw in ("created", "updated", "timestamp", "date", "time")):
            return "timestamp"
        if "json" in dt or "text" in dt:
            return "json" if "json" in dt else "text"
        if "bool" in dt:
            return "boolean"
        if "enum" in dt:
            return "enum"
        return "unknown"

    def _is_sensitive(self, name: str) -> bool:
        return bool(self._sensitive_re.search(name))

    def _guess_module(self, table_name: str) -> str:
        """Guess a business module from table name prefix."""
        nl = table_name.lower()
        # Common prefixes that indicate business modules
        prefixes = [
            ("user", ["user", "account", "member", "customer"]),
            ("order", ["order", "sale", "purchase", "transaction", "cart"]),
            ("payment", ["payment", "invoice", "bill", "refund"]),
            ("product", ["product", "item", "sku", "goods", "inventory"]),
            ("shipping", ["ship", "delivery", "logistics", "warehouse"]),
            ("analytics", ["analytics", "report", "metric", "dashboard"]),
            ("system", ["config", "setting", "log", "audit", "migration"]),
        ]
        for module, keywords in prefixes:
            if any(kw in nl for kw in keywords):
                return module
        return ""

    # ── Profile enrichment ─────────────────────────────────────────────────

    def _apply_profiles(
        self,
        tables: list[TableProfile],
        profiles: dict[str, Any],
    ) -> None:
        """Apply live column profile data (null rates, distinct counts, samples)."""
        for t in tables:
            tp = profiles.get(t.table_name)
            if not isinstance(tp, dict):
                continue
            col_profiles = tp.get("columns") or {}
            for c in t.columns:
                cp = col_profiles.get(c.column_name)
                if isinstance(cp, dict):
                    c.null_rate = cp.get("null_rate")
                    c.distinct_count = cp.get("distinct_count")
                    c.sample_values = cp.get("sample_values") or []
                    c.enum_guess = cp.get("enum_guess") or []

    def _apply_usage_heat(
        self,
        tables: list[TableProfile],
        usage: dict[str, Any],
    ) -> None:
        """Apply usage heat data to table profiles."""
        top_tables = set(usage.get("top_tables", []))
        for t in tables:
            if t.table_name.lower() in {tt.lower() for tt in top_tables}:
                t.query_count = 1  # We don't have exact counts from memory search


# ── Convenience builder ────────────────────────────────────────────────────────


def build_database_map(
    datasource_id: str,
    *,
    db_session: Any = None,
    memory_store: Any | None = None,
) -> DatabaseMap | None:
    """Build a DatabaseMap for a datasource.

    Uses the catalog + memory to assemble a complete intelligence model.
    Returns None if the catalog is unavailable.
    """
    try:
        from engine.environment.service import EnvironmentService
        from engine.memory.long_term_store import get_long_term_store

        if db_session is None:
            logger.warning("No db_session provided — cannot build DatabaseMap.")
            return None

        service = EnvironmentService(db_session)
        catalog = service.get_catalog_snapshot(datasource_id)
        if catalog is None or not catalog.tables:
            logger.warning("Catalog is empty for datasource %s", datasource_id)
            return None

        store = memory_store or get_long_term_store()
        builder = DatabaseMapBuilder()
        return builder.build(catalog, memory_store=store)
    except Exception as exc:
        logger.error("Failed to build DatabaseMap for %s: %s", datasource_id, exc)
        return None


def render_map_for_prompt(db_map: DatabaseMap) -> str:
    """Render a compact DatabaseMap summary for LLM prompt injection.

    Designed to fit in ~500-800 tokens — enough for the model to understand
    the database landscape without consuming the full context window.
    """
    lines = ["## Database Map"]

    # Module summary
    modules = db_map.module_summary()
    if modules:
        lines.append("### Business Modules")
        for module, tables in sorted(modules.items()):
            lines.append(f"- **{module}**: {', '.join(tables[:8])}")

    # Statistics
    lines.append(f"### Stats: {len(db_map.tables)} tables, "
                 f"{len(db_map.relationships)} relationships, "
                 f"{db_map.total_query_count} prior queries")

    # Relationships (compact)
    if db_map.relationships:
        lines.append("### Key Relationships")
        for r in db_map.relationships[:15]:
            src_tag = "FK" if r.source == "fk_catalog" else "~"
            lines.append(f"- [{src_tag}] {r.from_table}.{r.from_column} → "
                         f"{r.to_table}.{r.to_column}")

    # Risk
    if db_map.prod_tables:
        lines.append(f"### PROD Tables: {', '.join(db_map.prod_tables)}")
    if db_map.sensitive_columns:
        lines.append(f"### Sensitive Columns: {', '.join(db_map.sensitive_columns[:10])}")

    # Most queried
    if db_map.most_queried_tables:
        lines.append(f"### Most Queried: {', '.join(db_map.most_queried_tables[:8])}")

    return "\n".join(lines)
