import logging
import sqlglot
from sqlglot import exp

from engine.models import DataSource
from engine.errors import DataBoxError

logger = logging.getLogger("databox.policy")

class PolicyEngine:
    @staticmethod
    def enforce_query_policy(ds: DataSource, sql_str: str) -> None:
        """
        Enforces read-only and environment policies on raw query execution.
        """
        if not ds.is_read_only and ds.env != "prod":
            return  # Fast path: development database and writable

        # Parse AST to identify commands
        try:
            expressions = sqlglot.parse(sql_str)
        except Exception as exc:
            # If parsing fails, fall back to simple string check to prevent SQL injection bypass
            logger.warning("SQL parsing failed in PolicyEngine, fallback to string checks: %s", exc)
            sql_lower = sql_str.lower().strip()
            # If read-only, block common mutation verbs
            if ds.is_read_only:
                for verb in ["insert", "update", "delete", "drop", "create", "alter", "truncate", "replace", "grant"]:
                    if sql_lower.startswith(verb) or f" {verb} " in sql_lower:
                        raise DataBoxError(
                            code="READ_ONLY_VIOLATION",
                            message=f"数据源 '{ds.name}' 已被设置为只读模式，禁止执行任何更改或写入 SQL 语句。"
                        )
            return

        # Walk AST to detect mutations
        mutations = (
            exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter, exp.Command, exp.Merge
        )

        for expr in expressions:
            if not expr:
                continue
            for node in expr.walk():
                if isinstance(node, mutations):
                    # Check Read-Only restriction
                    if ds.is_read_only:
                        raise DataBoxError(
                            code="READ_ONLY_VIOLATION",
                            message=f"数据源 '{ds.name}' 处于只读防护模式下，禁止执行写入/修改/定义 SQL (指令类型: {type(node).__name__})。"
                        )
                    # Check Production restriction (for safety, restrict DDL in prod)
                    if ds.env == "prod" and isinstance(node, (exp.Drop, exp.Create, exp.Alter)):
                        raise DataBoxError(
                            code="PROD_POLICY_VIOLATION",
                            message=f"数据源 '{ds.name}' 属于生产环境，已被 Policy 引擎安全锁定，拒绝通过此处执行结构定义变更 (DDL: {type(node).__name__})。"
                        )

    @staticmethod
    def enforce_ddl_policy(ds: DataSource) -> None:
        """
        Explicit check before table designer executing generated DDL.
        """
        if ds.is_read_only:
            raise DataBoxError(
                code="READ_ONLY_VIOLATION",
                message=f"数据源 '{ds.name}' 已开启只读保护，禁止执行任何结构变更变更 DDL。"
            )
        if ds.env == "prod":
            raise DataBoxError(
                code="PROD_POLICY_VIOLATION",
                message=f"数据源 '{ds.name}' 属于生产环境 (Production)，安全策略禁止通过桌面客户端直接执行结构修改/建表 DDL。"
            )

    @staticmethod
    def enforce_test_data_policy(ds: DataSource) -> None:
        """
        Checks before spawning fake test data.
        """
        if ds.is_read_only:
            raise DataBoxError(
                code="READ_ONLY_VIOLATION",
                message=f"数据源 '{ds.name}' 处于只读防护模式下，禁止生成测试数据。"
            )
        if ds.env == "prod":
            raise DataBoxError(
                code="PROD_POLICY_VIOLATION",
                message=f"数据源 '{ds.name}' 属于生产环境 (Production)，已被安全 Policy 引擎拦截：禁止在生产环境生成测试数据。"
            )

    @staticmethod
    def enforce_restore_policy(ds: DataSource) -> None:
        """
        Checks before database restore recovery actions.
        """
        if ds.is_read_only:
            raise DataBoxError(
                code="RESTORE_READONLY_ERROR",
                message=f"数据源 '{ds.name}' 处于只读模式下，禁止执行数据库覆盖还原操作。"
            )
        if ds.env == "prod":
            # In a production context, restore is a catastrophic operation if done casually
            raise DataBoxError(
                code="PROD_POLICY_VIOLATION",
                message=f"拒绝操作：数据源 '{ds.name}' 属于生产环境 (Production)，Policy 引擎默认禁止对其执行覆盖还原 (Restore) 操作。"
            )
