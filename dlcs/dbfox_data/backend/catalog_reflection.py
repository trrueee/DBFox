"""Live catalog reflection owned by the Data capability."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any

from dbfox_dlc_api import ToolInputError
from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.engine.reflection import Inspector, ObjectKind
from sqlalchemy.engine.interfaces import ReflectedColumn, ReflectedForeignKeyConstraint

from .connection import DataConnectionBoundary
from .contracts import DatabaseHandle
from .inventory import (
    ColumnInventory,
    ForeignKeyInventory,
    ForeignKeyReference,
    IncomingForeignKey,
    InspectedColumn,
    InspectedColumnObject,
    InspectedIndex,
    InspectedTable,
    OutgoingForeignKey,
    SchemaInventory,
    TableInventory,
)


_SYSTEM_SCHEMAS = frozenset(
    {"information_schema", "mysql", "performance_schema", "pg_catalog", "pg_toast", "sys"}
)


class DataCatalogReflector:
    """Reflect authorized databases through SQLAlchemy's dialect inspectors."""

    def __init__(self, connection: DataConnectionBoundary) -> None:
        self._connection = connection

    def inspect_catalog(
        self,
        handle: DatabaseHandle,
        *,
        invocation_id: str,
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> SchemaInventory:
        with self._connection.reflection_connection(
            handle,
            invocation_id=invocation_id,
            cancellation_probe=cancellation_probe,
        ) as connection:
            tables = self._reflect_catalog(
                sqlalchemy_inspect(connection),
                handle,
                cancellation_probe,
            )
        return SchemaInventory(
            database_resource_id=handle.database.id,
            dialect=handle.profile.provider,
            database_name=handle.database.database_name,
            tables=tables,
            table_count=len(tables),
            column_count=sum(len(table.columns) for table in tables),
        )

    def inspect_objects(
        self,
        handle: DatabaseHandle,
        targets: Sequence[str],
        *,
        invocation_id: str,
        cancellation_probe: Callable[[], bool] | None = None,
    ) -> list[InspectedTable | InspectedColumnObject]:
        normalized = [target.strip() for target in targets]
        if not normalized or any(not target for target in normalized):
            raise ToolInputError("At least one non-empty inspection target is required.")
        with self._connection.reflection_connection(
            handle,
            invocation_id=invocation_id,
            cancellation_probe=cancellation_probe,
        ) as connection:
            inspector = sqlalchemy_inspect(connection)
            return [
                self._inspect_object(inspector, handle, target)
                for target in normalized
            ]

    def _reflect_catalog(
        self,
        inspector: Inspector,
        handle: DatabaseHandle,
        cancellation_probe: Callable[[], bool] | None,
    ) -> list[TableInventory]:
        tables: list[TableInventory] = []
        for schema_name in self._schema_names(inspector, handle):
            if cancellation_probe and cancellation_probe():
                raise RuntimeError("Database catalog reflection was cancelled.")
            table_names = inspector.get_table_names(schema=schema_name)
            view_names = inspector.get_view_names(schema=schema_name)
            object_names = sorted(set(table_names) | set(view_names))
            if not object_names:
                continue
            columns = inspector.get_multi_columns(
                schema=schema_name,
                filter_names=object_names,
                kind=ObjectKind.ANY,
            )
            primary_keys = inspector.get_multi_pk_constraint(
                schema=schema_name,
                filter_names=table_names,
            )
            foreign_keys = inspector.get_multi_foreign_keys(
                schema=schema_name,
                filter_names=table_names,
            )
            comments = self._multi_table_comments(inspector, schema_name, object_names)
            for table_name in object_names:
                key = (schema_name, table_name)
                reflected_columns = columns.get(key, [])
                pk_columns = set(primary_keys.get(key, {}).get("constrained_columns") or [])
                reflected_fks = foreign_keys.get(key, [])
                fk_columns = {
                    str(column)
                    for foreign_key in reflected_fks
                    for column in foreign_key.get("constrained_columns") or []
                }
                tables.append(
                    TableInventory(
                        table_schema=self._stored_schema(handle, schema_name),
                        table_name=table_name,
                        table_type="view" if table_name in view_names else "table",
                        comment=self._comment_text(comments.get(key)),
                        columns=[
                            self._column_inventory(column, pk_columns, fk_columns)
                            for column in reflected_columns
                        ],
                        foreign_keys=self._foreign_key_inventory(reflected_fks),
                    )
                )
        return sorted(tables, key=lambda table: (table.table_schema, table.table_name))

    def _inspect_object(
        self,
        inspector: Inspector,
        handle: DatabaseHandle,
        target: str,
    ) -> InspectedTable | InspectedColumnObject:
        schema_name, table_name, column_name = self._resolve_target(
            inspector,
            handle,
            target,
        )
        if not inspector.has_table(table_name, schema=schema_name):
            raise ToolInputError(f"Table not found: {target}")
        reflected_columns = inspector.get_columns(table_name, schema=schema_name)
        primary_key = inspector.get_pk_constraint(table_name, schema=schema_name)
        primary_key_columns = [
            str(column)
            for column in primary_key.get("constrained_columns") or []
        ]
        foreign_keys = inspector.get_foreign_keys(table_name, schema=schema_name)
        outgoing = self._outgoing_foreign_keys(foreign_keys)
        fk_by_column = {item.column: item.references for item in outgoing}
        columns = [
            self._inspected_column(column, primary_key_columns, fk_by_column)
            for column in reflected_columns
        ]
        if column_name is not None:
            for column in columns:
                if column.name == column_name:
                    return InspectedColumnObject(
                        **column.model_dump(),
                        table=table_name,
                        schema_name=self._stored_schema(handle, schema_name),
                        dialect=handle.profile.provider,
                    )
            raise ToolInputError(f"Column not found: {target}")
        views = set(inspector.get_view_names(schema=schema_name))
        return InspectedTable(
            name=table_name,
            schema_name=self._stored_schema(handle, schema_name),
            type="view" if table_name in views else "table",
            dialect=handle.profile.provider,
            comment=self._table_comment(inspector, schema_name, table_name),
            columns=columns,
            primary_key=primary_key_columns,
            foreign_keys_out=outgoing,
            foreign_keys_in=self._incoming_foreign_keys(
                inspector,
                schema_name,
                table_name,
            ),
            indexes=[
                InspectedIndex(
                    name=str(index.get("name") or ""),
                    columns=[
                        str(column)
                        for column in index.get("column_names") or []
                        if column is not None
                    ],
                    unique=bool(index.get("unique")),
                )
                for index in inspector.get_indexes(table_name, schema=schema_name)
                if index.get("name")
            ],
        )

    @staticmethod
    def _schema_names(
        inspector: Inspector,
        handle: DatabaseHandle,
    ) -> list[str | None]:
        dialect = handle.profile.provider
        if dialect == "sqlite":
            return [None]
        if dialect == "mysql":
            return [handle.database.database_name]
        return [
            schema
            for schema in inspector.get_schema_names()
            if schema.casefold() not in _SYSTEM_SCHEMAS
            and not schema.casefold().startswith("pg_")
        ]

    @staticmethod
    def _stored_schema(handle: DatabaseHandle, schema_name: str | None) -> str:
        if schema_name:
            return schema_name
        return "main" if handle.profile.provider == "sqlite" else ""

    @staticmethod
    def _multi_table_comments(
        inspector: Inspector,
        schema_name: str | None,
        object_names: Sequence[str],
    ) -> Mapping[tuple[str | None, str], Mapping[str, Any]]:
        try:
            return inspector.get_multi_table_comment(
                schema=schema_name,
                filter_names=object_names,
                kind=ObjectKind.ANY,
            )
        except NotImplementedError:
            return {}

    @staticmethod
    def _table_comment(
        inspector: Inspector,
        schema_name: str | None,
        table_name: str,
    ) -> str | None:
        try:
            return DataCatalogReflector._comment_text(
                inspector.get_table_comment(table_name, schema=schema_name)
            )
        except NotImplementedError:
            return None

    @staticmethod
    def _comment_text(value: Mapping[str, Any] | None) -> str | None:
        if not value:
            return None
        text = value.get("text")
        return str(text) if text else None

    @staticmethod
    def _column_inventory(
        column: ReflectedColumn,
        primary_keys: set[str],
        foreign_keys: set[str],
    ) -> ColumnInventory:
        name = str(column["name"])
        column_type = str(column.get("type") or "")
        default = column.get("default")
        comment = column.get("comment")
        return ColumnInventory(
            column_name=name,
            data_type=column_type,
            column_type=column_type,
            is_nullable=bool(column.get("nullable", True)),
            column_default=str(default) if default is not None else None,
            is_primary_key=name in primary_keys,
            is_foreign_key=name in foreign_keys,
            column_comment=str(comment) if comment else None,
        )

    @staticmethod
    def _foreign_key_inventory(
        foreign_keys: Iterable[ReflectedForeignKeyConstraint],
    ) -> list[ForeignKeyInventory]:
        result: list[ForeignKeyInventory] = []
        for foreign_key in foreign_keys:
            constrained = foreign_key.get("constrained_columns") or []
            referred = foreign_key.get("referred_columns") or []
            for local_column, remote_column in zip(constrained, referred, strict=False):
                result.append(
                    ForeignKeyInventory(
                        column_name=str(local_column),
                        referenced_schema=(
                            str(foreign_key["referred_schema"])
                            if foreign_key.get("referred_schema")
                            else None
                        ),
                        referenced_table=str(foreign_key["referred_table"]),
                        referenced_column=str(remote_column),
                    )
                )
        return result

    @classmethod
    def _outgoing_foreign_keys(
        cls,
        foreign_keys: Iterable[ReflectedForeignKeyConstraint],
    ) -> list[OutgoingForeignKey]:
        return [
            OutgoingForeignKey(
                column=item.column_name,
                references=ForeignKeyReference(
                    schema_name=item.referenced_schema,
                    table=item.referenced_table,
                    column=item.referenced_column,
                ),
            )
            for item in cls._foreign_key_inventory(foreign_keys)
        ]

    def _incoming_foreign_keys(
        self,
        inspector: Inspector,
        schema_name: str | None,
        table_name: str,
    ) -> list[IncomingForeignKey]:
        table_names = inspector.get_table_names(schema=schema_name)
        all_foreign_keys = inspector.get_multi_foreign_keys(
            schema=schema_name,
            filter_names=table_names,
        )
        incoming: list[IncomingForeignKey] = []
        for (source_schema, source_table), foreign_keys in all_foreign_keys.items():
            for foreign_key in foreign_keys:
                referred_schema = foreign_key.get("referred_schema") or source_schema
                if (
                    str(foreign_key.get("referred_table") or "") != table_name
                    or referred_schema != schema_name
                ):
                    continue
                constrained = foreign_key.get("constrained_columns") or []
                referred = foreign_key.get("referred_columns") or []
                for local_column, remote_column in zip(constrained, referred, strict=False):
                    incoming.append(
                        IncomingForeignKey(
                            schema_name=source_schema,
                            table=source_table,
                            column=str(local_column),
                            references=ForeignKeyReference(
                                schema_name=schema_name,
                                table=table_name,
                                column=str(remote_column),
                            ),
                        )
                    )
        return incoming

    @staticmethod
    def _inspected_column(
        column: ReflectedColumn,
        primary_keys: Sequence[str],
        foreign_keys: Mapping[str, ForeignKeyReference],
    ) -> InspectedColumn:
        name = str(column["name"])
        default = column.get("default")
        comment = column.get("comment")
        return InspectedColumn(
            name=name,
            type=str(column.get("type") or ""),
            nullable=bool(column.get("nullable", True)),
            default=str(default) if default is not None else None,
            primary_key=name in primary_keys,
            foreign_key=foreign_keys.get(name),
            comment=str(comment) if comment else None,
        )

    @staticmethod
    def _resolve_target(
        inspector: Inspector,
        handle: DatabaseHandle,
        target: str,
    ) -> tuple[str | None, str, str | None]:
        parts = [part.strip() for part in target.split(".") if part.strip()]
        default_schema = DataCatalogReflector._default_schema(inspector, handle)
        if len(parts) == 1:
            return default_schema, parts[0], None
        if len(parts) == 2:
            if inspector.has_table(parts[1], schema=parts[0]):
                return parts[0], parts[1], None
            return default_schema, parts[0], parts[1]
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        raise ToolInputError(f"Invalid inspection target: {target}")

    @staticmethod
    def _default_schema(
        inspector: Inspector,
        handle: DatabaseHandle,
    ) -> str | None:
        if handle.profile.provider == "sqlite":
            return None
        if handle.profile.provider == "mysql":
            return handle.database.database_name
        return inspector.default_schema_name
