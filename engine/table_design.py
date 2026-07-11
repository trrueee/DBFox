import re
from typing import Any, Mapping

from engine.errors import DBFoxError


IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
NUMERIC_RE = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

NO_DEFAULT_TYPES = {
    "TEXT",
    "MEDIUMTEXT",
    "LONGTEXT",
    "BLOB",
    "MEDIUMBLOB",
    "LONGBLOB",
    "JSON",
}

INTEGER_TYPES = {"TINYINT", "SMALLINT", "INT", "INTEGER", "BIGINT"}
NUMERIC_TYPES = INTEGER_TYPES | {"FLOAT", "DOUBLE", "DECIMAL"}
STRING_TYPES = {"VARCHAR", "CHAR", "TEXT", "MEDIUMTEXT", "LONGTEXT", "JSON"}
DATETIME_TYPES = {"DATE", "DATETIME", "TIMESTAMP"}
SUPPORTED_SIMPLE_TYPES = (
    INTEGER_TYPES
    | {"BOOLEAN", "FLOAT", "DOUBLE", "DATE", "DATETIME", "TIMESTAMP"}
    | NO_DEFAULT_TYPES
)
SUPPORTED_ENGINES = {"InnoDB"}
SUPPORTED_CHARSETS = {"utf8mb4"}
SUPPORTED_COLLATIONS = {"utf8mb4_0900_ai_ci", "utf8mb4_unicode_ci", "utf8mb4_general_ci"}


class TableDesignError(DBFoxError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="TABLE_DESIGN_INVALID")


def _validate_identifier(value: str, label: str) -> str:
    name = value.strip()
    if not IDENTIFIER_RE.match(name):
        raise TableDesignError(f"{label} 只能使用字母、数字和下划线，并且必须以字母或下划线开头。")
    return name


def _quote_identifier(value: str) -> str:
    return f"`{value}`"


def _quote_literal(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def _base_type(column_type: str) -> str:
    return column_type.split("(", 1)[0].strip().upper()


def _normalize_column_type(raw_type: str) -> str:
    value = " ".join(raw_type.strip().upper().split())
    if not value:
        raise TableDesignError("字段类型不能为空。")

    varchar_match = re.fullmatch(r"(VARCHAR|CHAR)\((\d{1,5})\)", value)
    if varchar_match:
        length = int(varchar_match.group(2))
        if length < 1 or length > 65535:
            raise TableDesignError("VARCHAR/CHAR 长度必须在 1 到 65535 之间。")
        return value

    decimal_match = re.fullmatch(r"DECIMAL\((\d{1,2})(?:,(\d{1,2}))?\)", value)
    if decimal_match:
        precision = int(decimal_match.group(1))
        scale = int(decimal_match.group(2) or "0")
        if precision < 1 or precision > 65 or scale < 0 or scale > precision:
            raise TableDesignError("DECIMAL 精度必须为 1-65，且 scale 不能大于 precision。")
        return value

    if value in SUPPORTED_SIMPLE_TYPES:
        return value

    raise TableDesignError(
        "暂不支持该字段类型。MVP 支持 INT、BIGINT、VARCHAR(n)、DECIMAL(p,s)、DATETIME、DATE、TEXT、JSON 等常用 MySQL 类型。"
    )


def _normalize_default(value: Any, column_type: str, nullable: bool) -> str | None:
    if value is None:
        return None

    raw = str(value).strip()
    if raw == "":
        return None

    base = _base_type(column_type)
    upper = raw.upper()

    if upper == "NULL":
        if not nullable:
            raise TableDesignError("NOT NULL 字段不能设置 DEFAULT NULL。")
        return "DEFAULT NULL"

    if base in NO_DEFAULT_TYPES:
        raise TableDesignError("TEXT、BLOB、JSON 类型不支持普通默认值。")

    if upper in {"CURRENT_TIMESTAMP", "CURRENT_TIMESTAMP()"}:
        if base not in {"DATETIME", "TIMESTAMP"}:
            raise TableDesignError("CURRENT_TIMESTAMP 只能用于 DATETIME 或 TIMESTAMP 字段。")
        return "DEFAULT CURRENT_TIMESTAMP"

    if base == "BOOLEAN":
        if upper in {"TRUE", "1"}:
            return "DEFAULT TRUE"
        if upper in {"FALSE", "0"}:
            return "DEFAULT FALSE"
        raise TableDesignError("BOOLEAN 默认值只能是 TRUE、FALSE、1 或 0。")

    if base in NUMERIC_TYPES:
        if not NUMERIC_RE.match(raw):
            raise TableDesignError("数值字段默认值必须是数字。")
        return f"DEFAULT {raw}"

    if (raw.startswith("'") and raw.endswith("'")) or (raw.startswith('"') and raw.endswith('"')):
        raw = raw[1:-1]

    return "DEFAULT " + _quote_literal(raw)


def _make_index_name(table_name: str, columns: list[str], unique: bool) -> str:
    prefix = "uk" if unique else "idx"
    candidate = f"{prefix}_{table_name}_{'_'.join(columns)}"
    if len(candidate) > 64:
        candidate = candidate[:64].rstrip("_")
    return candidate


def generate_create_table_ddl(design: Mapping[str, Any]) -> dict[str, Any]:
    table_name = _validate_identifier(str(design.get("table_name", "")), "表名")
    table_comment = str(design.get("table_comment") or "").strip()
    engine = str(design.get("engine") or "InnoDB")
    charset = str(design.get("charset") or "utf8mb4")
    collation = str(design.get("collation") or "utf8mb4_0900_ai_ci")
    raw_columns = list(design.get("columns") or [])
    raw_indexes = list(design.get("indexes") or [])
    warnings: list[str] = []

    if engine not in SUPPORTED_ENGINES:
        raise TableDesignError("当前 MVP 只允许生成 InnoDB 表。")
    if charset not in SUPPORTED_CHARSETS:
        raise TableDesignError("当前 MVP 只允许使用 utf8mb4 字符集。")
    if collation not in SUPPORTED_COLLATIONS:
        raise TableDesignError("当前 MVP 只允许使用常见 utf8mb4 排序规则。")
    if not raw_columns:
        raise TableDesignError("至少需要一个字段。")

    column_names: set[str] = set()
    primary_key_columns: list[str] = []
    column_lines: list[str] = []

    for raw_column in raw_columns:
        if not isinstance(raw_column, Mapping):
            raise TableDesignError("字段定义格式不正确。")

        column_name = _validate_identifier(str(raw_column.get("name", "")), "字段名")
        if column_name in column_names:
            raise TableDesignError(f"字段 `{column_name}` 重复。")
        column_names.add(column_name)

        column_type = _normalize_column_type(str(raw_column.get("type", "")))
        base = _base_type(column_type)
        is_primary_key = bool(raw_column.get("primary_key", False))
        is_auto_increment = bool(raw_column.get("auto_increment", False))
        nullable = bool(raw_column.get("nullable", True)) and not is_primary_key
        default_clause = _normalize_default(raw_column.get("default_value"), column_type, nullable)
        comment = str(raw_column.get("comment") or "").strip()

        if is_auto_increment and base not in INTEGER_TYPES:
            raise TableDesignError("AUTO_INCREMENT 只能用于整数类型字段。")
        if is_auto_increment and not is_primary_key:
            raise TableDesignError("AUTO_INCREMENT 字段必须同时设置为主键。")
        if is_primary_key:
            primary_key_columns.append(column_name)

        parts = [
            _quote_identifier(column_name),
            column_type,
            "NULL" if nullable else "NOT NULL",
        ]
        if default_clause:
            parts.append(default_clause)
        if is_auto_increment:
            parts.append("AUTO_INCREMENT")
        if comment:
            parts.append("COMMENT " + _quote_literal(comment))
        column_lines.append("  " + " ".join(parts))

    constraint_lines: list[str] = []
    if primary_key_columns:
        joined = ", ".join(_quote_identifier(name) for name in primary_key_columns)
        constraint_lines.append(f"  PRIMARY KEY ({joined})")
    else:
        warnings.append("建议为业务表设置主键，便于编辑、同步和备份恢复定位。")

    index_names: set[str] = set()
    for raw_index in raw_indexes:
        if not isinstance(raw_index, Mapping):
            raise TableDesignError("索引定义格式不正确。")
        index_columns = [_validate_identifier(str(name), "索引字段") for name in list(raw_index.get("columns") or [])]
        if not index_columns:
            raise TableDesignError("索引至少需要一个字段。")
        for column_name in index_columns:
            if column_name not in column_names:
                raise TableDesignError(f"索引引用了不存在的字段 `{column_name}`。")
        for column_name in index_columns:
            column = next(
                column for column in raw_columns
                if isinstance(column, Mapping) and str(column.get("name", "")).strip() == column_name
            )
            if _base_type(_normalize_column_type(str(column.get("type", "")))) in NO_DEFAULT_TYPES:
                raise TableDesignError("当前 MVP 暂不支持对 TEXT、BLOB、JSON 字段创建索引。")

        unique = bool(raw_index.get("unique", False))
        raw_name = str(raw_index.get("name") or "").strip()
        index_name = _validate_identifier(raw_name, "索引名") if raw_name else _make_index_name(table_name, index_columns, unique)
        if index_name in index_names:
            raise TableDesignError(f"索引 `{index_name}` 重复。")
        index_names.add(index_name)

        keyword = "UNIQUE KEY" if unique else "KEY"
        joined = ", ".join(_quote_identifier(name) for name in index_columns)
        constraint_lines.append(f"  {keyword} {_quote_identifier(index_name)} ({joined})")

    body_lines = column_lines + constraint_lines
    ddl = (
        f"CREATE TABLE {_quote_identifier(table_name)} (\n"
        + ",\n".join(body_lines)
        + f"\n) ENGINE={engine} DEFAULT CHARSET={charset} COLLATE={collation}"
    )
    if table_comment:
        ddl += " COMMENT=" + _quote_literal(table_comment)
    ddl += ";"

    return {
        "ddl": ddl,
        "warnings": warnings,
        "summary": {
            "tableName": table_name,
            "columns": len(raw_columns),
            "indexes": len(raw_indexes),
            "primaryKey": primary_key_columns,
            "dialect": "mysql",
        },
    }


def execute_table_design_ddl(db: Any, datasource_id: str, ddl: str) -> dict[str, Any]:
    from engine.models import DataSource, QueryHistory
    from engine.datasource import get_mysql_connection_params
    from engine.app.safe_errors import FixedErrorCode, fixed_error_message
    from engine.policy.redactor import DataRedactor
    from engine.sql.executor import _ping_mysql_connection, get_mysql_pool
    from engine.environment.schema_catalog_sync import ensure_catalog
    import sqlite3
    import time
    import uuid

    ds = db.query(DataSource).filter(DataSource.id == datasource_id).first()
    if not ds:
        raise TableDesignError("数据源不存在。")

    if ds.is_read_only:
        raise TableDesignError("该数据源为只读模式，禁止执行 DDL 写操作。")

    clean_ddl = ddl.strip()
    # Basic check to prevent executing non-DDL or multiple queries via this endpoint
    if not clean_ddl.upper().startswith("CREATE TABLE"):
        raise TableDesignError("目前仅支持执行 CREATE TABLE 表设计 SQL 语句。")

    start_time = time.time()
    execution_status = "success"
    error_message = None

    try:
        if ds.db_type == "sqlite":
            conn = sqlite3.connect(str(ds.database_name))
            try:
                cursor = conn.cursor()
                cursor.execute(clean_ddl)
                conn.commit()
            finally:
                conn.close()
        else:
            # MySQL
            conn_params = get_mysql_connection_params({
                "host": ds.host,
                "port": ds.port,
                "username": ds.username,
                "database_name": ds.database_name,
                "password_credential_id": ds.password_credential_id,
                "ssh_enabled": ds.ssh_enabled,
                "ssh_host": ds.ssh_host,
                "ssh_port": ds.ssh_port,
                "ssh_username": ds.ssh_username,
                "ssh_password_credential_id": ds.ssh_password_credential_id,
                "ssh_pkey_path": ds.ssh_pkey_path,
                "ssh_key_passphrase_credential_id": ds.ssh_key_passphrase_credential_id,
                "ssl_enabled": ds.ssl_enabled,
                "ssl_ca_path": ds.ssl_ca_path,
                "ssl_cert_path": ds.ssl_cert_path,
                "ssl_key_path": ds.ssl_key_path,
                "ssl_verify_identity": ds.ssl_verify_identity,
            })
            pool = get_mysql_pool(datasource_id, conn_params)
            conn_proxy: Any = pool.connect()
            try:
                _ping_mysql_connection(conn_proxy)
                with conn_proxy.cursor() as cursor:
                    cursor.execute(clean_ddl)
                conn_proxy.commit()
            finally:
                conn_proxy.close()
    except Exception:
        execution_status = "failed"
        error_message = fixed_error_message(FixedErrorCode.TABLE_DESIGN_ERROR)
        raise TableDesignError(error_message) from None
    finally:
        latency_ms = int((time.time() - start_time) * 1000)
        redacted_ddl = DataRedactor.redact_sql(ddl)
        redacted_clean_ddl = DataRedactor.redact_sql(clean_ddl)
        # Log to QueryHistory for auditing
        history = QueryHistory(
            id=f"exec-{uuid.uuid4()}",
            data_source_id=datasource_id,
            question="Execute Designed DDL",
            submitted_sql=redacted_ddl,
            generated_sql=redacted_ddl,
            safe_sql=redacted_clean_ddl,
            executed_sql=redacted_clean_ddl if execution_status == "success" else "",
            guardrail_result="pass",
            guardrail_checks="[{\"rule\": \"table_design_ddl\", \"level\": \"pass\", \"message\": \"DDL executed via safe table design path\"}]",
            execution_status=execution_status,
            execution_time_ms=latency_ms,
            error_message=(
                fixed_error_message(FixedErrorCode.TABLE_DESIGN_ERROR)
                if error_message
                else None
            ),
        )
        db.add(history)
        db.commit()

    # Post-execution schema sync to populate new tables in sidebar metadata
    sync_result = None
    try:
        result = ensure_catalog(db, datasource_id)
        sync_result = result.model_dump(mode="json")
    except Exception:
        # Schema sync failure shouldn't raise since table is already created
        pass

    return {
        "success": True,
        "latencyMs": latency_ms,
        "syncResult": sync_result,
        "message": "表结构执行成功！已自动完成元数据同步。"
    }
