from __future__ import annotations

from typing import Literal, TypedDict

import logging
import re

from sqlglot import exp
from dbfox_dlc_api import log_extension_diagnostic, log_extension_exception

from .parser import normalize_dialect as _sqlglot_dialect, parse_sql
from .readonly_query import (
    READONLY_FORBIDDEN_TYPES,
    is_readonly_query,
    readonly_side_effect_functions,
)
from .result_limits import MAX_ROWS
logger = logging.getLogger("dbfox.guardrail")


class GuardrailCheck(TypedDict):
    rule: str
    level: Literal["warn", "reject"]
    message: str


class GuardrailResult(TypedDict):
    result: Literal["pass", "warn", "reject"]
    originalSql: str
    safeSql: str
    checks: list[GuardrailCheck]
    message: str

# System schemas we must block access to
BLOCKED_SCHEMAS = {
    "information_schema",
    "mysql",
    "performance_schema",
    "sys",
    "pg_catalog",
    "pg_toast",
    "sqlite_master",
    "sqlite_temp_master",
}

# Dangerous functions we must block
DANGEROUS_FUNCTIONS = {
    "sleep", "benchmark", "load_file", "database", "user", "current_user", "version",
    "pg_sleep", "pg_read_file", "pg_write_file", "lo_import", "lo_export", "query_to_xml",
    "sys_eval", "sys_exec", "xp_cmdshell"
}

# sqlglot normalizes some MySQL functions into dedicated expression types, so
# string-based function-name checks are not enough for these security rules.
DANGEROUS_EXPRESSION_TYPES = (
    exp.CurrentUser,
    exp.CurrentSchema,
    exp.CurrentVersion,
)

# List of blocked SQL command types (anything that is not a SELECT)
def guardrail_check_with_ast(
    sql_str: str,
    dialect: str = "mysql",
) -> tuple[GuardrailResult, exp.Expression | None]:
    return _evaluate_guardrail(sql_str, dialect=dialect)


def count_statement_delimiters(sql: str) -> int:
    """Counts the number of semicolons that are not inside string literals or comments.

    MySQL executable comments (``/*!<digits> ... */``) are NOT stripped —
    their contents are treated as active SQL because MySQL will execute them.
    """
    # Remove single line comments:
    #   - ``-- `` / ``--\t`` → rest of line is comment (MySQL standard)
    #   - ``--`` at end of line → empty comment (MySQL requires a whitespace
    #     after ``--``, so ``--word`` is NOT a comment)
    #   - ``#`` line comments (MySQL)
    sql = re.sub(r"--(?:[ \t]+.*|$)", "", sql, flags=re.MULTILINE)
    sql = re.sub(r"#.*$", "", sql, flags=re.MULTILINE)

    # Remove regular block comments (``/* ... */``) but NOT MySQL executable
    # comments (``/*!<digits> ... */``).  Executable comments are left in-place
    # so their semicolons contribute to the multi-statement count.
    # We use a two-pass approach: first extract executable comments, strip
    # regular comments from the remainder, then re-insert the executable bodies.
    _EXEC_COMMENT_RE = re.compile(r"/\*!(\d+)(.*?)\*/", flags=re.DOTALL)
    exec_comment_bodies: list[str] = []
    placeholder = "\x00DBFOX_EXEC_COMMENT\x00"

    def _save_exec_comment(m: re.Match) -> str:
        exec_comment_bodies.append(m.group(2))  # the code inside /*!<ver> ... */
        return placeholder

    sql = _EXEC_COMMENT_RE.sub(_save_exec_comment, sql)
    # Now strip regular block comments from the remainder
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)
    # Re-insert the executable comment bodies
    for body in exec_comment_bodies:
        sql = sql.replace(placeholder, body, 1)

    in_single_quote = False
    in_double_quote = False
    in_backtick = False
    escaped = False
    semicolons = 0

    for char in sql:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "'" and not in_double_quote and not in_backtick:
            in_single_quote = not in_single_quote
        elif char == '"' and not in_single_quote and not in_backtick:
            in_double_quote = not in_double_quote
        elif char == '`' and not in_single_quote and not in_double_quote:
            in_backtick = not in_backtick
        elif char == ';' and not in_single_quote and not in_double_quote and not in_backtick:
            semicolons += 1

    return semicolons


# Pattern that matches MySQL executable comment openings: /*! followed by digits.
# Used to block these outright — they can hide dangerous SQL from the AST walker.
_MYSQL_EXEC_COMMENT_START = re.compile(r"/\*!\d")


def _projection_has_star(projection: exp.Expression) -> bool:
    """Check if a SELECT projection uses ``*`` (excluding safe COUNT(*))."""
    inner = projection.this if isinstance(projection, exp.Alias) else projection
    if isinstance(inner, exp.Count):
        return False
    if isinstance(inner, exp.Star):
        return True
    if isinstance(inner, exp.Column) and isinstance(inner.this, exp.Star):
        return True
    return False


def _outer_limit_value(limit: exp.Expression | None) -> int | None:
    """Return a literal outer LIMIT/FETCH value, if it is statically bounded."""
    if limit is None:
        return None

    value = limit.args.get("expression")
    if value is None:
        # SQLGlot represents ``FETCH FIRST n ROWS ONLY`` with ``count``.
        value = limit.args.get("count")
    if not isinstance(value, exp.Literal) or value.is_string:
        return None

    try:
        return int(value.this)
    except (TypeError, ValueError):
        return None


def _outer_limit_can_exceed_row_count(limit: exp.Expression | None) -> bool:
    """Whether a syntactic LIMIT can return more rows than its literal count."""
    if limit is None:
        return False
    options = limit.args.get("limit_options")
    if not isinstance(options, exp.LimitOptions):
        return False
    return bool(options.args.get("percent") or options.args.get("with_ties"))


_BROKEN_GENERATED_TOKENS = (
    "ORDER BY ARRAY(",
    "ORDER BY STRUCT(",
    "ORDER BY []",
    "ARRAY(",
    "STRUCT(",
)


def _reject(
    original_sql: str,
    *,
    checks: list[GuardrailCheck],
    message: str,
) -> GuardrailResult:
    return {
        "result": "reject",
        "originalSql": original_sql,
        "safeSql": "",
        "checks": checks,
        "message": message,
    }


def _preflight_rejection(sql_str: str) -> GuardrailResult | None:
    if not sql_str:
        return _reject(
            sql_str,
            checks=[{
                "rule": "empty_sql",
                "level": "reject",
                "message": "SQL 语句不能为空",
            }],
            message="拒绝执行：SQL 语句为空",
        )

    if _MYSQL_EXEC_COMMENT_START.search(sql_str):
        return _reject(
            sql_str,
            checks=[{
                "rule": "mysql_executable_comment",
                "level": "reject",
                "message": (
                    "禁止使用 MySQL 版本化可执行注释 (/*!...*/)。"
                    "此类注释可以隐藏高危 SQL 指令，存在绕过安全审计的风险。"
                ),
            }],
            message=(
                "拒绝执行：检测到 MySQL 可执行注释，"
                "该语法可能被用于绕过安全审计。"
            ),
        )

    if len(sql_str) > 20_000:
        return _reject(
            sql_str[:100] + "...",
            checks=[{
                "rule": "sql_too_long",
                "level": "reject",
                "message": "SQL 语句长度不能超过 20000 字符",
            }],
            message="拒绝执行：SQL 语句过长",
        )

    semicolons = count_statement_delimiters(sql_str)
    # SQLGlot below is the authority for statement count. A single delimiter
    # followed by a comment is still one statement; checking the raw string's
    # final character incorrectly rejected valid SQL such as
    # ``SELECT 1; -- explanation``.
    has_multiple_statements = semicolons > 1
    if has_multiple_statements:
        return _reject(
            sql_str,
            checks=[{
                "rule": "multi_statement",
                "level": "reject",
                "message": (
                    "检测到多条 SQL 语句。出于安全策略，"
                    "每次仅允许执行单条 SELECT 语句。"
                ),
            }],
            message="拒绝执行：检测到多语句注入",
        )
    return None


def _parse_guarded_expression(
    sql_str: str,
    dialect: str,
) -> tuple[
    exp.Expression | None,
    list[GuardrailCheck],
    GuardrailResult | None,
]:
    checks: list[GuardrailCheck] = []
    try:
        expressions = parse_sql(sql_str, dialect)
        if len(expressions) > 1:
            checks.append({
                "rule": "multi_statement",
                "level": "reject",
                "message": (
                    "检测到多条 SQL 语句。出于安全策略，"
                    "每次仅允许执行单条 SELECT 语句。"
                ),
            })
        if not expressions or not expressions[0]:
            raise ValueError("SQL parsing yielded empty AST")
        return expressions[0], checks, None  # type: ignore[return-value]
    except Exception as exc:
        log_extension_exception(
            logger,
            operation="dbfox.data.sql_guardrail_parse",
            exc=exc,
            fingerprint_subject=f"{sql_str}\x00{type(exc).__name__}\x00{exc}",
            level="warning",
        )
        return None, checks, _reject(
            sql_str,
            checks=[{
                "rule": "syntax_error",
                "level": "reject",
                "message": "SQL could not be parsed safely.",
            }],
            message="拒绝执行：语法解析失败",
        )


def _ast_rejection_checks(
    expression: exp.Expression, dialect: str
) -> list[GuardrailCheck]:
    checks: list[GuardrailCheck] = []
    if (
        not isinstance(
            expression,
            (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery, exp.With),
        )
        or not is_readonly_query(expression, dialect)
    ):
        checks.append({
            "rule": "select_only",
            "level": "reject",
            "message": (
                "出于安全性考量，目前仅支持执行 SELECT 数据查询语句。"
                "禁止执行写入、删除、更新或定义操作。"
            ),
        })

    for node in expression.walk():
        if isinstance(node, exp.Lock):
            checks.append({
                "rule": "row_locking_blocked",
                "level": "reject",
                "message": (
                    "在只读/安全模式下，禁止执行包含 row-locking "
                    "(FOR UPDATE / FOR SHARE) 的锁表或锁行操作。"
                ),
            })
        elif isinstance(node, exp.Into):
            checks.append({
                "rule": "into_outfile_blocked",
                "level": "reject",
                "message": (
                    "禁止执行文件写入/导出操作 "
                    "(INTO OUTFILE / INTO DUMPFILE)"
                ),
            })
        elif isinstance(node, READONLY_FORBIDDEN_TYPES):
            checks.append({
                "rule": "blocked_command_type",
                "level": "reject",
                "message": f"禁止执行 SQL 指令类型: {type(node).__name__}",
            })
        elif isinstance(node, exp.With) and node.args.get("recursive"):
            checks.append({
                "rule": "recursive_cte_blocked",
                "level": "reject",
                "message": (
                    "由于安全性与性能考量，"
                    "禁止执行包含 RECURSIVE (递归) 的 CTE 语句。"
                ),
            })
        elif isinstance(node, exp.Table):
            table_name = node.name.lower() if node.name else ""
            db_name = node.db.lower() if node.db else ""
            if db_name in BLOCKED_SCHEMAS or table_name in BLOCKED_SCHEMAS:
                checks.append({
                    "rule": "system_catalog_blocked",
                    "level": "reject",
                    "message": (
                        "禁止访问系统内部表或系统架构库: "
                        f"'{db_name or table_name}'"
                    ),
                })
        elif isinstance(node, DANGEROUS_EXPRESSION_TYPES):
            checks.append({
                "rule": "dangerous_function",
                "level": "reject",
                "message": (
                    "Blocked dangerous system information function: "
                    f"{type(node).__name__}"
                ),
            })
        elif isinstance(node, exp.SessionParameter):
            checks.append({
                "rule": "system_variable_blocked",
                "level": "reject",
                "message": (
                    "Blocked access to MySQL system variable: "
                    f"{node.name}"
                ),
            })
        elif isinstance(node, (exp.Anonymous, exp.Func)):
            func_name = node.name.lower() if node.name else ""
            if func_name in (
                DANGEROUS_FUNCTIONS | readonly_side_effect_functions(dialect)
            ):
                checks.append({
                    "rule": "dangerous_function",
                    "level": "reject",
                    "message": (
                        "禁止使用高危或系统信息泄露函数: "
                        f"'{func_name}'"
                    ),
                })
    return checks


def _append_select_star_warning(
    expression: exp.Expression,
    checks: list[GuardrailCheck],
) -> None:
    has_star = any(
        _projection_has_star(projection)
        for select in expression.find_all(exp.Select)
        for projection in select.expressions
    )
    if has_star:
        checks.append({
            "rule": "select_star",
            "level": "warn",
            "message": (
                "建议不要在生产环境使用 SELECT *。显式指定所需字段"
                "能显著优化查询性能并减少网卡开销。"
            ),
        })


def _render_bounded_sql(
    expression: exp.Expression,
    *,
    original_sql: str,
    sqlglot_dialect: str,
    checks: list[GuardrailCheck],
) -> tuple[str | None, GuardrailResult | None]:
    outer_limit = expression.args.get("limit")
    outer_limit_value = _outer_limit_value(outer_limit)
    safe_expression = expression.copy()
    must_apply_hard_cap = (
        outer_limit is None
        or outer_limit_value is None
        or outer_limit_value < 0
        or outer_limit_value > MAX_ROWS
        or _outer_limit_can_exceed_row_count(outer_limit)
    )
    if must_apply_hard_cap:
        try:
            safe_expression = safe_expression.limit(MAX_ROWS)
        except Exception as exc:
            log_extension_exception(
                logger,
                operation="dbfox.data.sql_guardrail_limit_enforcement",
                exc=exc,
                fingerprint_subject=(
                    f"{original_sql}\x00{type(exc).__name__}\x00{exc}"
                ),
                level="warning",
            )
            return None, _reject(
                original_sql,
                checks=[{
                    "rule": "result_limit_enforcement_failed",
                    "level": "reject",
                    "message": "无法为查询施加服务端结果集上限，已拒绝执行。",
                }],
                message="拒绝执行：无法施加服务端结果集上限。",
            )
        checks.append({
            "rule": "auto_limit" if outer_limit is None else "limit_hard_cap",
            "level": "warn",
            "message": (
                f"未检测到外层 LIMIT，系统已追加 LIMIT {MAX_ROWS} "
                "以约束服务端结果集。"
                if outer_limit is None
                else f"查询的外层 LIMIT 已收敛为服务端上限 {MAX_ROWS}。"
            ),
        })

    try:
        return safe_expression.sql(dialect=sqlglot_dialect), None
    except Exception as exc:
        log_extension_exception(
            logger,
            operation="dbfox.data.sql_guardrail_limit_enforcement",
            exc=exc,
            fingerprint_subject=(
                f"{original_sql}\x00{type(exc).__name__}\x00{exc}"
            ),
            level="warning",
        )
        return None, _reject(
            original_sql,
            checks=[{
                "rule": "safe_sql_render_failed",
                "level": "reject",
                "message": "安全 SQL 无法生成，已拒绝执行。",
            }],
            message="拒绝执行：安全 SQL 生成失败。",
        )


def _generated_syntax_checks(safe_sql: str) -> list[GuardrailCheck]:
    upper_sql = safe_sql.upper()
    checks: list[GuardrailCheck] = []
    for token in _BROKEN_GENERATED_TOKENS:
        if token not in upper_sql:
            continue
        log_extension_diagnostic(
            logger,
            operation="dbfox.data.sql_guardrail_generated_syntax",
            subject=safe_sql,
            subject_type="sql",
        )
        checks.append({
            "rule": "mysql_syntax_invalid",
            "level": "reject",
            "message": (
                "SQL contains a MySQL-unsupported generated ordering expression. "
                "请使用标准 MySQL ORDER BY column [ASC|DESC] 语法。"
            ),
        })
    return checks

def _evaluate_guardrail(
    sql_str: str,
    dialect: str = "mysql",
) -> tuple[GuardrailResult, exp.Expression | None]:
    sql_str = sql_str.strip()
    preflight_rejection = _preflight_rejection(sql_str)
    if preflight_rejection is not None:
        return preflight_rejection, None

    sqlglot_dialect = _sqlglot_dialect(dialect)
    expression, checks, parse_rejection = _parse_guarded_expression(
        sql_str,
        dialect,
    )
    if parse_rejection is not None:
        return parse_rejection, None
    if expression is None:
        checks.append({
            "rule": "guardrail_internal_error",
            "level": "reject",
            "message": "SQL 解析未产生可验证的语法树，已拒绝执行。",
        })
        return _reject(
            sql_str,
            checks=checks,
            message="拒绝执行：SQL 安全检查未能完成。",
        ), None

    checks.extend(_ast_rejection_checks(expression, dialect))
    if any(check["level"] == "reject" for check in checks):
        return _reject(
            sql_str,
            checks=checks,
            message="拒绝执行：检测到高危 SQL 指令，已被 Guardrail 强制拦截。",
        ), None

    _append_select_star_warning(expression, checks)

    safe_sql, render_rejection = _render_bounded_sql(
        expression,
        original_sql=sql_str,
        sqlglot_dialect=sqlglot_dialect,
        checks=checks,
    )
    if render_rejection is not None:
        return render_rejection, None
    if safe_sql is None:
        checks.append({
            "rule": "guardrail_internal_error",
            "level": "reject",
            "message": "安全 SQL 未生成，已拒绝执行。",
        })
        return _reject(
            sql_str,
            checks=checks,
            message="拒绝执行：SQL 安全检查未能完成。",
        ), None

    checks.extend(_generated_syntax_checks(safe_sql))
    if any(check["level"] == "reject" for check in checks):
        return _reject(
            sql_str,
            checks=checks,
            message=(
                "拒绝执行：检测到 MySQL 不支持的语法，"
                "已被 Guardrail 拦截。"
            ),
        ), None

    result_status: Literal["pass", "warn"] = (
        "warn"
        if any(check["level"] == "warn" for check in checks)
        else "pass"
    )
    result: GuardrailResult = {
        "result": result_status,
        "originalSql": sql_str,
        "safeSql": safe_sql,
        "checks": checks,
        "message": (
            "SQL 审核通过，但包含优化建议。"
            if result_status == "warn"
            else "SQL 安全审核通过！"
        ),
    }
    return result, expression


def guardrail_check(sql_str: str, dialect: str = "mysql") -> GuardrailResult:
    """Return the fail-closed SQL safety decision."""

    result, _parsed_ast = _evaluate_guardrail(sql_str, dialect=dialect)
    return result
