from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from sqlalchemy.orm import Session, selectinload

from engine.models import SchemaColumn, SchemaTable, WorkspaceTableScope
from engine.semantic.alias import AliasMatch, SemanticAliasResolver

TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_]+|[一-鿿]")


@dataclass
class ColumnLink:
    column: SchemaColumn
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    def add_reason(self, reason: str, score: float) -> None:
        self.score += score
        self.reasons.append(reason)


@dataclass
class TableLink:
    table: SchemaTable
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)
    columns: dict[str, ColumnLink] = field(default_factory=dict)

    def add_reason(self, reason: str, score: float) -> None:
        self.score += score
        self.reasons.append(reason)

    def column_link(self, column: SchemaColumn) -> ColumnLink:
        column_id = str(column.id)
        if column_id not in self.columns:
            self.columns[column_id] = ColumnLink(column=column)
        return self.columns[column_id]


@dataclass
class SchemaLinkingResult:
    datasource_id: str
    question: str
    original_table_count: int
    candidate_table_count: int
    tables: list[TableLink]
    mode: str = "rag"
    workspace_scope_applied: bool = False
    workspace_scope_table_count: int = 0
    semantic_aliases_used: list[dict[str, str]] = field(default_factory=list)

    @property
    def selected_table_count(self) -> int:
        return len(self.tables)

    def selected_table_names(self) -> list[str]:
        return [str(link.table.table_name) for link in self.tables]

    def selected_column_names(self) -> list[str]:
        names: list[str] = []
        for link in self.tables:
            table_name = str(link.table.table_name)
            for column in _sorted_columns(list(link.table.columns)):
                names.append(f"{table_name}.{column.column_name}")
        return names

    def reason_payload(self) -> list[dict[str, object]]:
        payload: list[dict[str, object]] = []
        for table_link in self.tables:
            table_name = str(table_link.table.table_name)
            payload.append(
                {
                    "targetType": "table",
                    "table": table_name,
                    "score": round(table_link.score, 3),
                    "reasons": table_link.reasons,
                }
            )
            for column_link in sorted(
                table_link.columns.values(),
                key=lambda item: (-item.score, str(item.column.column_name)),
            ):
                payload.append(
                    {
                        "targetType": "column",
                        "table": table_name,
                        "column": str(column_link.column.column_name),
                        "score": round(column_link.score, 3),
                        "reasons": column_link.reasons,
                    }
                )
        return payload

    def response_metadata(self, schema_context: str) -> dict[str, object]:
        return {
            "selectedTables": self.selected_table_names(),
            "selectedColumns": self.selected_column_names(),
            "schemaLinkingReasons": self.reason_payload(),
            "schemaContextSize": len(schema_context),
            "originalSchemaTableCount": self.original_table_count,
            "selectedSchemaTableCount": self.selected_table_count,
            "semanticAliasesUsed": self.semantic_aliases_used,
            "workspaceScopeApplied": self.workspace_scope_applied,
            "workspaceScopeTableCount": self.workspace_scope_table_count,
        }


class SchemaLinker:
    """Rule-based schema linker for the first lightweight semantic layer."""

    def __init__(
        self,
        db: Session,
        alias_resolver: SemanticAliasResolver | None = None,
        api_key: str | None = None,
        api_base: str | None = None,
        model_name: str | None = None,
    ) -> None:
        self.db = db
        self.alias_resolver = alias_resolver
        self.api_key = api_key
        self.api_base = api_base
        self.model_name = model_name

    def _get_alias_resolver(self, datasource_id: str) -> SemanticAliasResolver:
        if self.alias_resolver is not None:
            return self.alias_resolver
        return SemanticAliasResolver.from_db(
            self.db,
            datasource_id,
            api_key=self.api_key,
            api_base=self.api_base,
            model_name=self.model_name,
        )

    def _resolve_workspace_table_ids(
        self,
        datasource_id: str,
        project_id: str | None,
        workspace_table_ids: Sequence[str] | None,
    ) -> tuple[list[str] | None, bool, int]:
        """Resolve workspace scope from explicit ids or project+datasource combination.

        Returns (table_ids, scope_applied, scope_table_count).
        """
        if workspace_table_ids:
            return list(workspace_table_ids), True, len(workspace_table_ids)

        if project_id:
            scopes = (
                self.db.query(WorkspaceTableScope)
                .filter(
                    WorkspaceTableScope.project_id == project_id,
                    WorkspaceTableScope.data_source_id == datasource_id,
                    WorkspaceTableScope.enabled == True,
                )
                .all()
            )
            if scopes:
                ids: list[str] = [str(s.table_id) for s in scopes]
                return ids, True, len(ids)

        return None, False, 0

    def link(
        self,
        datasource_id: str,
        question: str,
        workspace_table_ids: Sequence[str] | None = None,
        project_id: str | None = None,
    ) -> SchemaLinkingResult:
        alias_resolver = self._get_alias_resolver(datasource_id)
        all_tables = (
            self.db.query(SchemaTable)
            .options(selectinload(SchemaTable.columns))
            .filter(SchemaTable.data_source_id == datasource_id)
            .all()
        )
        original_table_count = len(all_tables)

        resolved_ids, scope_applied, scope_count = self._resolve_workspace_table_ids(
            datasource_id, project_id, workspace_table_ids
        )

        if resolved_ids:
            workspace_id_set = {str(table_id) for table_id in resolved_ids}
            candidate_tables = [table for table in all_tables if str(table.id) in workspace_id_set]
        else:
            candidate_tables = all_tables

        if not candidate_tables:
            return SchemaLinkingResult(
                datasource_id=datasource_id,
                question=question,
                original_table_count=original_table_count,
                candidate_table_count=0,
                tables=[],
                workspace_scope_applied=scope_applied,
                workspace_scope_table_count=scope_count,
            )

        alias_matches = alias_resolver.resolve(question)
        sem_aliases_used = [
            {"alias": m.alias, "target": m.target, "source": m.source}
            for m in alias_matches
        ]
        table_links = [self._score_table(table, question, alias_matches) for table in candidate_tables]

        if len(candidate_tables) <= 8:
            selected = table_links
            for link in selected:
                if not link.reasons:
                    link.add_reason("small_schema_full_context", 0.0)
            return SchemaLinkingResult(
                datasource_id=datasource_id,
                question=question,
                original_table_count=original_table_count,
                candidate_table_count=len(candidate_tables),
                tables=selected,
                workspace_scope_applied=scope_applied,
                workspace_scope_table_count=scope_count,
                semantic_aliases_used=sem_aliases_used,
            )

        scored = sorted(table_links, key=lambda item: (-item.score, str(item.table.table_name)))
        selected = [link for link in scored if link.score > 0]
        if selected:
            selected = selected[:6]
        else:
            selected = scored[:5]
            for link in selected:
                link.add_reason("fallback_top_table", 0.0)

        selected = self._expand_foreign_keys(candidate_tables, selected)
        return SchemaLinkingResult(
            datasource_id=datasource_id,
            question=question,
            original_table_count=original_table_count,
            candidate_table_count=len(candidate_tables),
            tables=selected[:8],
            workspace_scope_applied=scope_applied,
            workspace_scope_table_count=scope_count,
            semantic_aliases_used=sem_aliases_used,
        )

    def full_context(
        self,
        datasource_id: str,
        question: str | None = None,
        workspace_table_ids: Sequence[str] | None = None,
        project_id: str | None = None,
    ) -> SchemaLinkingResult:
        all_tables = (
            self.db.query(SchemaTable)
            .options(selectinload(SchemaTable.columns))
            .filter(SchemaTable.data_source_id == datasource_id)
            .all()
        )
        original_table_count = len(all_tables)

        resolved_ids, scope_applied, scope_count = self._resolve_workspace_table_ids(
            datasource_id, project_id, workspace_table_ids
        )

        if resolved_ids:
            workspace_id_set = {str(table_id) for table_id in resolved_ids}
            selected_tables = [table for table in all_tables if str(table.id) in workspace_id_set]
        else:
            selected_tables = all_tables

        alias_resolver = self._get_alias_resolver(datasource_id)
        alias_matches = alias_resolver.resolve(question or "")
        sem_aliases_used = [
            {"alias": m.alias, "target": m.target, "source": m.source}
            for m in alias_matches
        ]

        links = [TableLink(table=table, reasons=["full_schema_context"]) for table in selected_tables]
        return SchemaLinkingResult(
            datasource_id=datasource_id,
            question=question or "",
            original_table_count=original_table_count,
            candidate_table_count=len(selected_tables),
            tables=links,
            mode="full",
            workspace_scope_applied=scope_applied,
            workspace_scope_table_count=scope_count,
            semantic_aliases_used=sem_aliases_used,
        )

    def _score_table(self, table: SchemaTable, question: str, alias_matches: list[AliasMatch]) -> TableLink:
        table_link = TableLink(table=table)
        q_lower = question.lower()
        q_tokens = _tokenize(question)
        table_name = str(table.table_name)
        table_name_lower = table_name.lower()
        table_tokens = _identifier_tokens(table_name)

        if table_name_lower in q_lower:
            table_link.add_reason("table_name_exact_match", 15.0)

        for token in q_tokens:
            if token in table_name_lower or token in table_tokens:
                table_link.add_reason(f"table_name_token_match:{token}", 8.0)

        table_comment = str(table.table_comment or "").lower()
        if table_comment:
            for token in q_tokens:
                if token in table_comment:
                    table_link.add_reason(f"table_comment_match:{token}", 5.0)

        for alias in alias_matches:
            if alias.table_name.lower() == table_name_lower:
                reason = f"alias_match:{alias.alias}->{alias.target}[source={alias.source}]"
                table_link.add_reason(reason, 12.0)

        for column in _sorted_columns(list(table.columns)):
            self._score_column(table_link, column, question, q_tokens, alias_matches)

        return table_link

    def _score_column(
        self,
        table_link: TableLink,
        column: SchemaColumn,
        question: str,
        q_tokens: list[str],
        alias_matches: list[AliasMatch],
    ) -> None:
        q_lower = question.lower()
        table_name_lower = str(table_link.table.table_name).lower()
        column_name = str(column.column_name)
        column_name_lower = column_name.lower()
        column_tokens = _identifier_tokens(column_name)
        column_link = table_link.column_link(column)

        if column_name_lower in q_lower:
            column_link.add_reason("column_name_exact_match", 3.0)

        for token in q_tokens:
            if token in column_name_lower or token in column_tokens:
                column_link.add_reason(f"column_name_token_match:{token}", 3.0)

        column_comment = str(column.column_comment or "").lower()
        if column_comment:
            for token in q_tokens:
                if token in column_comment:
                    column_link.add_reason(f"column_comment_match:{token}", 2.0)

        for alias in alias_matches:
            if (
                alias.target_type == "column"
                and alias.table_name.lower() == table_name_lower
                and alias.column_name
                and alias.column_name.lower() == column_name_lower
            ):
                reason = f"alias_column_match:{alias.alias}->{alias.target}[source={alias.source}]"
                column_link.add_reason(reason, 10.0)

        if column_link.score > 0:
            table_link.score += column_link.score
        else:
            table_link.columns.pop(str(column.id), None)

    def _expand_foreign_keys(self, candidate_tables: list[SchemaTable], selected: list[TableLink]) -> list[TableLink]:
        selected_ids = {str(link.table.id) for link in selected}
        table_links_by_id = {str(link.table.id): link for link in selected}
        column_id_to_name = {
            str(column.id): str(column.column_name)
            for table in candidate_tables
            for column in table.columns
        }

        for table in candidate_tables:
            table_id = str(table.id)
            if table_id in selected_ids:
                continue

            reasons: list[str] = []
            for selected_link in selected:
                reasons.extend(_foreign_key_reasons(table, selected_link.table, column_id_to_name))
                reasons.extend(_foreign_key_reasons(selected_link.table, table, column_id_to_name))

            if not reasons:
                continue

            table_link = table_links_by_id.get(table_id) or TableLink(table=table)
            for reason in reasons:
                table_link.add_reason(reason, 1.0)
            selected.append(table_link)
            selected_ids.add(table_id)
            table_links_by_id[table_id] = table_link
            if len(selected) >= 8:
                break

        return selected


def _tokenize(text: str) -> list[str]:
    return [token.lower() for token in TOKEN_PATTERN.findall(text) if token.strip()]


def _identifier_tokens(identifier: str) -> set[str]:
    return {part for part in re.split(r"[_\W]+", identifier.lower()) if part}


def _sorted_columns(columns: list[SchemaColumn]) -> list[SchemaColumn]:
    return sorted(columns, key=lambda column: (column.ordinal_position or 0, str(column.column_name)))


def _foreign_key_reasons(
    source_table: SchemaTable,
    target_table: SchemaTable,
    column_id_to_name: dict[str, str],
) -> list[str]:
    reasons: list[str] = []
    target_table_id = str(target_table.id)
    for column in source_table.columns:
        if not column.is_foreign_key or str(column.foreign_table_id or "") != target_table_id:
            continue
        target_column_name = column_id_to_name.get(str(column.foreign_column_id or ""), "id")
        reasons.append(
            "foreign_key_expansion:"
            f"{source_table.table_name}.{column.column_name}->{target_table.table_name}.{target_column_name}"
        )
    return reasons
