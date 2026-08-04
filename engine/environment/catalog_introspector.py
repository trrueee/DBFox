"""Database catalog reflection through one authoritative service."""
from __future__ import annotations

from collections import defaultdict
import logging
import ssl
from typing import Any, Callable, Iterable, Mapping, Sequence, TypeVar

from sqlalchemy import inspect as sqlalchemy_inspect
from sqlalchemy.engine.reflection import Inspector, ObjectKind
from sqlalchemy.engine.interfaces import ReflectedColumn, ReflectedForeignKeyConstraint
from sqlalchemy.orm import Session

from engine.app.safe_errors import FixedErrorCode, SafeLogOperation, log_unexpected_exception
from engine.connectivity.factory import ConnectionFactory
from engine.connectivity.profile import ConnectionProfile, ConnectionPurpose
from engine.datasource import datasource_connection_dict
from engine.environment.authoritative_inventory import (
    AuthoritativeInventory,
    SchemaInspectionError,
)
from engine.environment.inventory import (
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
from engine.errors import (
    DataSourceConnectionError,
    DataSourceCredentialUnavailableError,
    DataSourceSshConnectionError,
    DataSourceTlsConnectionError,
    ToolInputError,
)
from engine.models import DataSource
from engine.security.credential_vault import CredentialVaultUnavailableError

logger = logging.getLogger("dbfox.environment.catalog_introspector")

_SYSTEM_SCHEMAS = frozenset(
    {
        "information_schema",
        "mysql",
        "performance_schema",
        "pg_catalog",
        "pg_toast",
        "sys",
    }
)

_InspectionResult = TypeVar("_InspectionResult")


class CatalogIntrospector:
    """Reflect complete catalogs and explicit objects through one connection boundary."""

    def __init__(self, *, connection_factory: ConnectionFactory | None = None) -> None:
        self._connection_factory = connection_factory or ConnectionFactory()

    def inspect_catalog(self, db: Session, datasource_id: str) -> AuthoritativeInventory:
        inventory, generation = self._run_inspection(
            db,
            datasource_id,
            lambda datasource, profile: (
                self._reflect_catalog(datasource, profile),
                int(getattr(datasource, "connection_generation", 0) or 0),
            ),
        )

        return AuthoritativeInventory.from_completed_inventory(
            inventory,
            generation=generation,
        )

    def inspect_objects(
        self,
        db: Session,
        datasource_id: str,
        targets: Sequence[str],
    ) -> list[InspectedTable | InspectedColumnObject]:
        normalized = [target.strip() for target in targets]
        if not normalized or any(not target for target in normalized):
            raise ToolInputError("At least one non-empty inspection target is required.")

        return self._run_inspection(
            db,
            datasource_id,
            lambda _datasource, profile: self._inspect_objects(profile, normalized),
        )

    def _inspect_objects(
        self,
        profile: ConnectionProfile,
        normalized: Sequence[str],
    ) -> list[InspectedTable | InspectedColumnObject]:
        if profile.dialect == "duckdb":
            with self._connection_factory.connection_scope(
                profile,
                purpose=ConnectionPurpose.SCHEMA_SYNC,
                read_only=True,
            ) as connection:
                return [
                    self._inspect_duckdb_object(connection, profile, target)
                    for target in normalized
                ]

        with self._connection_factory.sqlalchemy_connection_scope(
            profile,
            purpose=ConnectionPurpose.SCHEMA_SYNC,
            read_only=True,
        ) as connection:
            inspector = sqlalchemy_inspect(connection)
            return [
                self._inspect_sqlalchemy_object(inspector, profile, target)
                for target in normalized
            ]

    def _run_inspection(
        self,
        db: Session,
        datasource_id: str,
        operation: Callable[[DataSource, ConnectionProfile], _InspectionResult],
    ) -> _InspectionResult:
        profile: ConnectionProfile | None = None
        try:
            datasource, profile = self._load_datasource(db, datasource_id)
            return operation(datasource, profile)
        except SchemaInspectionError:
            raise
        except (CredentialVaultUnavailableError, DataSourceCredentialUnavailableError):
            code = FixedErrorCode.SCHEMA_CREDENTIAL_UNAVAILABLE
        except DataSourceSshConnectionError:
            code = FixedErrorCode.SCHEMA_SSH_FAILED
        except (DataSourceTlsConnectionError, ssl.SSLError):
            code = FixedErrorCode.SCHEMA_TLS_FAILED
        except DataSourceConnectionError:
            code = self._connection_error_code(profile)
        except (ConnectionError, OSError, TimeoutError):
            code = self._connection_error_code(profile)
        except Exception as exc:
            log_unexpected_exception(
                logger,
                operation=SafeLogOperation.UNEXPECTED,
                exc=exc,
                level="warning",
            )
            code = FixedErrorCode.SCHEMA_INSPECTION_FAILED
        raise SchemaInspectionError(datasource_id, code) from None

    def _load_datasource(
        self,
        db: Session,
        datasource_id: str,
    ) -> tuple[DataSource, ConnectionProfile]:
        datasource = (
            db.query(DataSource)
            .filter(DataSource.id == datasource_id)
            .first()
        )
        if datasource is None:
            raise SchemaInspectionError(
                datasource_id,
                FixedErrorCode.SCHEMA_DATASOURCE_NOT_FOUND,
            )
        if (
            str(datasource.db_type or "").lower() not in {"sqlite", "duckdb"}
            and not datasource.password_credential_id
        ):
            raise SchemaInspectionError(
                datasource_id,
                FixedErrorCode.SCHEMA_CREDENTIAL_UNAVAILABLE,
            )
        try:
            profile = ConnectionProfile.from_mapping(
                datasource_connection_dict(datasource)
            )
        except DataSourceConnectionError:
            raise SchemaInspectionError(
                datasource_id,
                FixedErrorCode.SCHEMA_INSPECTION_FAILED,
            ) from None
        if profile.dialect == "duckdb" and profile.database_name.strip() == ":memory:":
            raise SchemaInspectionError(
                datasource_id,
                FixedErrorCode.SCHEMA_DUCKDB_MEMORY_UNSUPPORTED,
            )
        return datasource, profile

    def _reflect_catalog(
        self,
        datasource: DataSource,
        profile: ConnectionProfile,
    ) -> SchemaInventory:
        if profile.dialect == "duckdb":
            with self._connection_factory.connection_scope(
                profile,
                purpose=ConnectionPurpose.SCHEMA_SYNC,
                read_only=True,
            ) as connection:
                tables = self._reflect_duckdb_catalog(connection)
        else:
            with self._connection_factory.sqlalchemy_connection_scope(
                profile,
                purpose=ConnectionPurpose.SCHEMA_SYNC,
                read_only=True,
            ) as connection:
                tables = self._reflect_sqlalchemy_catalog(
                    sqlalchemy_inspect(connection),
                    profile,
                )
        return SchemaInventory(
            datasource_id=str(datasource.id),
            dialect=profile.dialect,
            database_name=profile.database_name,
            tables=tables,
            table_count=len(tables),
            column_count=sum(len(table.columns) for table in tables),
        )

    def _reflect_sqlalchemy_catalog(
        self,
        inspector: Inspector,
        profile: ConnectionProfile,
    ) -> list[TableInventory]:
        tables: list[TableInventory] = []
        for schema_name in self._schema_names(inspector, profile):
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
            comments = self._multi_table_comments(
                inspector,
                schema_name,
                object_names,
            )

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
                        table_schema=self._stored_schema(profile, schema_name),
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
        return sorted(
            tables,
            key=lambda table: (table.table_schema, table.table_name),
        )

    def _inspect_sqlalchemy_object(
        self,
        inspector: Inspector,
        profile: ConnectionProfile,
        target: str,
    ) -> InspectedTable | InspectedColumnObject:
        schema_name, table_name, column_name = self._resolve_target(
            inspector,
            profile,
            target,
        )
        if not inspector.has_table(table_name, schema=schema_name):
            raise ToolInputError(f"Table not found: {target}")

        reflected_columns = inspector.get_columns(table_name, schema=schema_name)
        primary_key = inspector.get_pk_constraint(
            table_name,
            schema=schema_name,
        )
        primary_key_columns = [
            str(column)
            for column in primary_key.get("constrained_columns") or []
        ]
        foreign_keys = inspector.get_foreign_keys(table_name, schema=schema_name)
        outgoing = self._outgoing_foreign_keys(foreign_keys)
        fk_by_column = {
            item.column: item.references
            for item in outgoing
        }
        columns = [
            self._inspected_column(
                column,
                primary_key_columns,
                fk_by_column,
            )
            for column in reflected_columns
        ]

        if column_name is not None:
            for column in columns:
                if column.name == column_name:
                    return InspectedColumnObject(
                        **column.model_dump(),
                        table=table_name,
                        schema_name=schema_name,
                        dialect=profile.dialect,
                    )
            raise ToolInputError(f"Column not found: {target}")

        views = set(inspector.get_view_names(schema=schema_name))
        return InspectedTable(
            name=table_name,
            schema_name=schema_name,
            type="view" if table_name in views else "table",
            dialect=profile.dialect,
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
        profile: ConnectionProfile,
    ) -> list[str | None]:
        if profile.dialect == "sqlite":
            return [None]
        if profile.dialect == "mysql":
            return [profile.database_name]
        return [
            schema
            for schema in inspector.get_schema_names()
            if schema.casefold() not in _SYSTEM_SCHEMAS
            and not schema.casefold().startswith("pg_")
        ]

    @staticmethod
    def _stored_schema(
        profile: ConnectionProfile,
        schema_name: str | None,
    ) -> str:
        if schema_name:
            return schema_name
        return "main" if profile.dialect == "sqlite" else ""

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
            return CatalogIntrospector._comment_text(
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

    @staticmethod
    def _outgoing_foreign_keys(
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
            for item in CatalogIntrospector._foreign_key_inventory(foreign_keys)
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
                for local_column, remote_column in zip(
                    constrained,
                    referred,
                    strict=False,
                ):
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
        profile: ConnectionProfile,
        target: str,
    ) -> tuple[str | None, str, str | None]:
        parts = [part.strip() for part in target.split(".") if part.strip()]
        if len(parts) == 1:
            return CatalogIntrospector._default_schema(inspector, profile), parts[0], None
        if len(parts) == 2:
            if inspector.has_table(parts[1], schema=parts[0]):
                return parts[0], parts[1], None
            return CatalogIntrospector._default_schema(inspector, profile), parts[0], parts[1]
        if len(parts) == 3:
            return parts[0], parts[1], parts[2]
        raise ToolInputError(f"Invalid inspection target: {target}")

    @staticmethod
    def _default_schema(
        inspector: Inspector,
        profile: ConnectionProfile,
    ) -> str | None:
        if profile.dialect == "sqlite":
            return None
        if profile.dialect == "mysql":
            return profile.database_name
        return inspector.default_schema_name

    def _reflect_duckdb_catalog(self, connection: Any) -> list[TableInventory]:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT table_schema, table_name, table_type
            FROM information_schema.tables
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
              AND table_type IN ('BASE TABLE', 'VIEW')
            ORDER BY table_schema, table_name
            """
        )
        table_rows = cursor.fetchall()

        cursor.execute(
            """
            SELECT table_schema, table_name, column_name, data_type,
                   is_nullable, column_default
            FROM information_schema.columns
            WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
            ORDER BY table_schema, table_name, ordinal_position
            """
        )
        columns_by_table: dict[tuple[str, str], list[ColumnInventory]] = defaultdict(list)
        for schema, table, column, data_type, nullable, default in cursor.fetchall():
            columns_by_table[(str(schema), str(table))].append(
                ColumnInventory(
                    column_name=str(column),
                    data_type=str(data_type or ""),
                    column_type=str(data_type or ""),
                    is_nullable=str(nullable).upper() == "YES",
                    column_default=str(default) if default is not None else None,
                )
            )

        primary_keys, foreign_keys = self._duckdb_constraints(connection)
        for key, columns in columns_by_table.items():
            pk_columns = primary_keys.get(key, set())
            fk_columns = {
                foreign_key.column_name
                for foreign_key in foreign_keys.get(key, [])
            }
            for column in columns:
                column.is_primary_key = column.column_name in pk_columns
                column.is_foreign_key = column.column_name in fk_columns

        return [
            TableInventory(
                table_schema=str(schema),
                table_name=str(table),
                table_type="view" if "VIEW" in str(table_type).upper() else "table",
                columns=columns_by_table.get((str(schema), str(table)), []),
                foreign_keys=foreign_keys.get((str(schema), str(table)), []),
            )
            for schema, table, table_type in table_rows
        ]

    @staticmethod
    def _duckdb_constraints(
        connection: Any,
    ) -> tuple[
        dict[tuple[str, str], set[str]],
        dict[tuple[str, str], list[ForeignKeyInventory]],
    ]:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT schema_name, table_name, constraint_type,
                   constraint_column_names, referenced_table,
                   referenced_column_names
            FROM duckdb_constraints()
            WHERE constraint_type IN ('PRIMARY KEY', 'FOREIGN KEY')
            ORDER BY schema_name, table_name, constraint_index
            """
        )
        primary_keys: dict[tuple[str, str], set[str]] = defaultdict(set)
        foreign_keys: dict[tuple[str, str], list[ForeignKeyInventory]] = defaultdict(list)
        for (
            schema,
            table,
            constraint_type,
            constrained_columns,
            referenced_table,
            referenced_columns,
        ) in cursor.fetchall():
            key = (str(schema), str(table))
            if str(constraint_type) == "PRIMARY KEY":
                primary_keys[key].update(
                    str(column)
                    for column in constrained_columns or []
                )
            elif referenced_table:
                for column, referenced_column in zip(
                    constrained_columns or [],
                    referenced_columns or [],
                    strict=False,
                ):
                    foreign_keys[key].append(
                        ForeignKeyInventory(
                            column_name=str(column),
                            referenced_schema=str(schema),
                            referenced_table=str(referenced_table),
                            referenced_column=str(referenced_column),
                        )
                    )
        return dict(primary_keys), dict(foreign_keys)

    def _inspect_duckdb_object(
        self,
        connection: Any,
        profile: ConnectionProfile,
        target: str,
    ) -> InspectedTable | InspectedColumnObject:
        inventory = self._reflect_duckdb_catalog(connection)
        parts = [part.strip() for part in target.split(".") if part.strip()]
        if len(parts) == 1:
            schema_name, table_name, column_name = "main", parts[0], None
        elif len(parts) == 2:
            qualified_table = next(
                (
                    table
                    for table in inventory
                    if table.table_schema == parts[0] and table.table_name == parts[1]
                ),
                None,
            )
            if qualified_table is not None:
                schema_name, table_name, column_name = parts[0], parts[1], None
            else:
                schema_name, table_name, column_name = "main", parts[0], parts[1]
        elif len(parts) == 3:
            schema_name, table_name, column_name = parts
        else:
            raise ToolInputError(f"Invalid inspection target: {target}")

        table = next(
            (
                item
                for item in inventory
                if item.table_schema == schema_name and item.table_name == table_name
            ),
            None,
        )
        if table is None:
            raise ToolInputError(f"Table not found: {target}")

        outgoing = [
            OutgoingForeignKey(
                column=foreign_key.column_name,
                references=ForeignKeyReference(
                    schema_name=foreign_key.referenced_schema,
                    table=foreign_key.referenced_table,
                    column=foreign_key.referenced_column,
                ),
            )
            for foreign_key in table.foreign_keys
        ]
        fk_by_column = {
            foreign_key.column: foreign_key.references
            for foreign_key in outgoing
        }
        columns = [
            InspectedColumn(
                name=column.column_name,
                type=str(column.column_type or column.data_type or ""),
                nullable=column.is_nullable,
                default=column.column_default,
                primary_key=column.is_primary_key,
                foreign_key=fk_by_column.get(column.column_name),
                comment=column.column_comment,
            )
            for column in table.columns
        ]
        if column_name is not None:
            for column in columns:
                if column.name == column_name:
                    return InspectedColumnObject(
                        **column.model_dump(),
                        table=table_name,
                        schema_name=schema_name,
                        dialect=profile.dialect,
                    )
            raise ToolInputError(f"Column not found: {target}")

        incoming = [
            IncomingForeignKey(
                schema_name=source.table_schema,
                table=source.table_name,
                column=foreign_key.column_name,
                references=ForeignKeyReference(
                    schema_name=schema_name,
                    table=table_name,
                    column=foreign_key.referenced_column,
                ),
            )
            for source in inventory
            for foreign_key in source.foreign_keys
            if foreign_key.referenced_table == table_name
            and (foreign_key.referenced_schema or source.table_schema) == schema_name
        ]
        return InspectedTable(
            name=table_name,
            schema_name=schema_name,
            type="view" if table.table_type == "view" else "table",
            dialect=profile.dialect,
            comment=table.comment,
            columns=columns,
            primary_key=[
                column.column_name
                for column in table.columns
                if column.is_primary_key
            ],
            foreign_keys_out=outgoing,
            foreign_keys_in=incoming,
            indexes=self._duckdb_indexes(connection, schema_name, table_name),
        )

    @staticmethod
    def _duckdb_indexes(
        connection: Any,
        schema_name: str,
        table_name: str,
    ) -> list[InspectedIndex]:
        cursor = connection.cursor()
        cursor.execute(
            """
            SELECT index_name, expressions, is_unique
            FROM duckdb_indexes()
            WHERE schema_name = ? AND table_name = ?
            ORDER BY index_name
            """,
            (schema_name, table_name),
        )
        return [
            InspectedIndex(
                name=str(name),
                columns=[
                    part.strip().strip('"')
                    for part in str(expressions or "").strip("[]").split(",")
                    if part.strip()
                ],
                unique=bool(unique),
            )
            for name, expressions, unique in cursor.fetchall()
        ]

    @staticmethod
    def _connection_error_code(
        profile: ConnectionProfile | None,
    ) -> FixedErrorCode:
        if profile is not None and profile.dialect == "sqlite":
            return FixedErrorCode.SCHEMA_SQLITE_PATH_UNAVAILABLE
        if profile is not None and profile.dialect == "duckdb":
            return FixedErrorCode.SCHEMA_DUCKDB_PATH_UNAVAILABLE
        return FixedErrorCode.SCHEMA_CONNECTION_FAILED


def inspect_catalog(db: Session, datasource_id: str) -> AuthoritativeInventory:
    return CatalogIntrospector().inspect_catalog(db, datasource_id)
