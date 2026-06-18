from __future__ import annotations

from typing import NotRequired, TypedDict

import logging
import re

import sqlglot
from sqlglot import exp
from engine.sql.parser import normalize_dialect as _sqlglot_dialect, parse_sql

from engine.errors import GuardrailValidationError

logger = logging.getLogger("dbfox.guardrail")


class GuardrailCheck(TypedDict):
    rule: str
    level: str
    message: str


class GuardrailResult(TypedDict):
    result: str  # "pass" | "warn" | "reject"
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
BLOCKED_COMMAND_TYPES = (
    exp.Insert,
    exp.Update,
    exp.Delete,
    exp.Drop,
    exp.Create,
    exp.Alter,
    exp.Command,
    exp.Merge,
    exp.Execute,
    exp.TruncateTable,
    exp.LoadData,
    exp.Copy,
)


def guardrail_parsed_ast(sql_str: str, dialect: str = "mysql") -> exp.Expression | None:
    """Return a parsed AST for trusted internal consumers, or None if unavailable."""
    sql_str = sql_str.strip()
    if not sql_str:
        return None

    try:
        expressions = parse_sql(sql_str, dialect)
    except Exception:
        return None
    if len(expressions) != 1 or not expressions[0]:
        return None
    return expressions[0]  # type: ignore[return-value]


def guardrail_check_with_ast(
    sql_str: str,
    dialect: str = "mysql",
) -> tuple[GuardrailResult, exp.Expression | None]:
    result = guardrail_check(sql_str, dialect=dialect)
    parsed_ast = None
    if result["result"] != "reject":
        parsed_ast = guardrail_parsed_ast(sql_str, dialect=dialect)
    return result, parsed_ast


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


def _is_select_node(node: exp.Expression) -> bool:
    """Check if an AST node is a read-only SELECT or set operation."""
    if isinstance(node, exp.Select):
        return True
    if isinstance(node, (exp.Union, exp.Intersect, exp.Except)):
        return _is_select_node(node.left) and _is_select_node(node.right)  # type: ignore[arg-type]
    if isinstance(node, exp.Subquery):
        return _is_select_node(node.this)
    if isinstance(node, exp.With):
        return _is_select_node(node.this)
    return False


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

def guardrail_check(sql_str: str, dialect: str = "mysql") -> GuardrailResult:
    """
    Analyzes SQL using sqlglot AST parsing to enforce V1 security guidelines.
    Checks:
    - Syntactic validity
    - Single statement restriction (no multi-statements)
    - SELECT query ONLY (blocks DDL/DML/DCL/dangerous commands)
    - Blocks access to system databases (mysql, information_schema, etc.)
    - Blocks dangerous built-in functions (sleep, benchmark, load_file, etc.)
    - Blocks SELECT INTO OUTFILE / DUMPFILE
    - Automatically injects LIMIT 1000 if not provided
    - Appends warnings for SELECT *
    
    Returns:
        dict (GuardrailResult): {
            "result": "pass" | "warn" | "reject",
            "originalSql": str,
            "safeSql": str,
            "checks": list of dicts,
            "message": str,
        }
    """
    sql_str = sql_str.strip()
    if not sql_str:
        return {
            "result": "reject",
            "originalSql": sql_str,
            "safeSql": "",
            "checks": [{"rule": "empty_sql", "level": "reject", "message": "SQL 语句不能为空"}],
            "message": "拒绝执行：SQL 语句为空"
        }

    # Block MySQL executable comments (/*!<digits> ... */) upfront.
    # These can hide dangerous SQL (e.g. /*!50001 DROP TABLE t;*/) from both
    # the delimiter counter and the AST walker because sqlglot treats them as
    # inert comment nodes while MySQL WILL execute their contents.
    if _MYSQL_EXEC_COMMENT_START.search(sql_str):
        return {
            "result": "reject",
            "originalSql": sql_str,
            "safeSql": "",
            "checks": [{
                "rule": "mysql_executable_comment",
                "level": "reject",
                "message": (
                    "禁止使用 MySQL 版本化可执行注释 (/*!...*/)。"
                    "此类注释可以隐藏高危 SQL 指令，存在绕过安全审计的风险。"
                ),
            }],
            "message": "拒绝执行：检测到 MySQL 可执行注释，该语法可能被用于绕过安全审计。",
        }

    # Enforce safe length limit
    if len(sql_str) > 20000:
        return {
            "result": "reject",
            "originalSql": sql_str[:100] + "...",
            "safeSql": "",
            "checks": [{"rule": "sql_too_long", "level": "reject", "message": "SQL 语句长度不能超过 20000 字符"}],
            "message": "拒绝执行：SQL 语句过长"
        }

    # Pre-parse multi-statement check using our custom delimiter counter
    semicolons = count_statement_delimiters(sql_str)
    if semicolons > 1 or (semicolons == 1 and not sql_str.strip().endswith(";")):
        return {
            "result": "reject",
            "originalSql": sql_str,
            "safeSql": "",
            "checks": [{
                "rule": "multi_statement",
                "level": "reject",
                "message": "检测到多条 SQL 语句。出于安全策略，每次仅允许执行单条 SELECT 语句。"
            }],
            "message": "拒绝执行：检测到多语句注入"
        }

    # Map input dialect to standard sqlglot dialect name
    sqlglot_dialect = _sqlglot_dialect(dialect)

    checks: list[GuardrailCheck] = []
    has_errors = False

    # 1. Parse and check multiple statements
    try:
        # sqlglot.parse parses multi-statement strings separated by semicolon
        expressions = parse_sql(sql_str, dialect)
        if len(expressions) > 1:
            checks.append({
                "rule": "multi_statement",
                "level": "reject",
                "message": "检测到多条 SQL 语句。出于安全策略，每次仅允许执行单条 SELECT 语句。"
            })
            has_errors = True

        if not expressions or not expressions[0]:
            raise ValueError("SQL parsing yielded empty AST")

        expression: exp.Expression = expressions[0]  # type: ignore[assignment]
    except Exception as e:
        return {
            "result": "reject",
            "originalSql": sql_str,
            "safeSql": "",
            "checks": [{"rule": "syntax_error", "level": "reject", "message": f"SQL 语法解析错误: {str(e)}"}],
            "message": "拒绝执行：语法解析失败"
        }

    # 2. Enforce SELECT only — delegated to module-level helper for testability
    if not isinstance(expression, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery, exp.With)) \
       or not _is_select_node(expression):
        checks.append({
            "rule": "select_only",
            "level": "reject",
            "message": "出于安全性考量，目前仅支持执行 SELECT 数据查询语句。禁止执行写入、删除、更新或定义操作。"
        })
        has_errors = True

    # 3. Walk the AST to detect nested hazards (subqueries, tables, functions)
    for node in expression.walk():
        # Check forbidden command types nested
        if isinstance(node, BLOCKED_COMMAND_TYPES):
            checks.append({
                "rule": "blocked_command_type",
                "level": "reject",
                "message": f"禁止执行 SQL 指令类型: {type(node).__name__}"
            })
            has_errors = True

        # Check recursive CTE / WITH clause
        elif isinstance(node, exp.With) and node.args.get("recursive"):
            checks.append({
                "rule": "recursive_cte_blocked",
                "level": "reject",
                "message": "由于安全性与性能考量，禁止执行包含 RECURSIVE (递归) 的 CTE 语句。"
            })
            has_errors = True

        # Check SELECT ... FOR UPDATE / LOCK IN SHARE MODE
        elif isinstance(node, exp.Lock):
            checks.append({
                "rule": "row_locking_blocked",
                "level": "reject",
                "message": "在只读/安全模式下，禁止执行包含 row-locking (FOR UPDATE / FOR SHARE) 的锁表或锁行操作。"
            })
            has_errors = True

        # Check for system catalog tables / schemas
        elif isinstance(node, exp.Table):
            table_name = node.name.lower() if node.name else ""
            db_name = node.db.lower() if node.db else ""
            
            if db_name in BLOCKED_SCHEMAS or table_name in BLOCKED_SCHEMAS:
                checks.append({
                    "rule": "system_catalog_blocked",
                    "level": "reject",
                    "message": f"禁止访问系统内部表或系统架构库: '{db_name or table_name}'"
                })
                has_errors = True

        # Check normalized dangerous functions such as CURRENT_USER(),
        # DATABASE()/SCHEMA(), and VERSION().
        elif isinstance(node, DANGEROUS_EXPRESSION_TYPES):
            checks.append({
                "rule": "dangerous_function",
                "level": "reject",
                "message": f"Blocked dangerous system information function: {type(node).__name__}"
            })
            has_errors = True

        # Block MySQL system variables such as @@version.
        elif isinstance(node, exp.SessionParameter):
            checks.append({
                "rule": "system_variable_blocked",
                "level": "reject",
                "message": f"Blocked access to MySQL system variable: {node.name}"
            })
            has_errors = True

        # Check for dangerous functions
        elif isinstance(node, (exp.Anonymous, exp.Func)):
            func_name = node.name.lower() if node.name else ""
            if func_name in DANGEROUS_FUNCTIONS:
                checks.append({
                    "rule": "dangerous_function",
                    "level": "reject",
                    "message": f"禁止使用高危或系统信息泄露函数: '{func_name}'"
                })
                has_errors = True
                
        # Check SELECT INTO OUTFILE / DUMPFILE
        elif isinstance(node, exp.Into):
            checks.append({
                "rule": "into_outfile_blocked",
                "level": "reject",
                "message": "禁止执行文件写入/导出操作 (INTO OUTFILE / INTO DUMPFILE)"
            })
            has_errors = True

    # If any blocker rule is violated, immediately reject
    if has_errors:
        return {
            "result": "reject",
            "originalSql": sql_str,
            "safeSql": "",
            "checks": checks,
            "message": "拒绝执行：检测到高危 SQL 指令，已被 Guardrail 强制拦截。"
        }

    # 4. Check for SELECT * Warning while excluding safe aggregate COUNT(*).
    has_star = any(
        _projection_has_star(projection)
        for select in expression.find_all(exp.Select)
        for projection in select.expressions
    )
            
    if has_star:
        checks.append({
            "rule": "select_star",
            "level": "warn",
            "message": "建议不要在生产环境使用 SELECT *。显式指定所需字段能显著优化查询性能并减少网卡开销。"
        })

    # 5. Check and inject LIMIT 1000 if no limit exists
    # Find if there is an outer limit
    has_limit = expression.args.get("limit") is not None
    safe_expression = expression.copy()
    
    if not has_limit:
        # Inject LIMIT 1000 to the AST in a type-safe way
        try:
            if isinstance(expression, (exp.Select, exp.Union, exp.Intersect, exp.Except)):
                safe_expression = safe_expression.limit(1000)  # type: ignore[attr-defined]
                checks.append({
                    "rule": "auto_limit",
                    "level": "warn",
                    "message": "未检测到 LIMIT 约束，系统已自动追加 LIMIT 1000 以防大表全表扫描挂起连接。"
                })
        except Exception:
            logger.warning("LIMIT injection via AST failed; query will run without auto-LIMIT")
            checks.append({
                "rule": "auto_limit_failed",
                "level": "warn",
                "message": "系统未能自动追加 LIMIT 约束，查询将以原始形式执行。"
            })
            
    safe_sql = safe_expression.sql(dialect=sqlglot_dialect)

    # 6. Post-generation syntax sanity — catch patterns that are valid in
    #    sqlglot's AST but produce invalid MySQL (BigQuery/Spark-isms).
    _SAFE_SQL_UPPER = safe_sql.upper()
    _BROKEN_TOKENS = (
        "ORDER BY ARRAY(", "ORDER BY STRUCT(", "ORDER BY []",
        "ARRAY(", "STRUCT(",
    )
    for token in _BROKEN_TOKENS:
        if token in _SAFE_SQL_UPPER:
            logger.warning(
                "guardrail_check: detected broken MySQL syntax token=%r in safe_sql=%r",
                token, safe_sql,
            )
            checks.append({
                "rule": "mysql_syntax_invalid",
                "level": "reject",
                "message": (
                    "SQL contains a MySQL-unsupported generated ordering expression. "
                    "请使用标准 MySQL ORDER BY column [ASC|DESC] 语法。"
                ),
            })
            has_errors = True

    if has_errors:
        return {
            "result": "reject",
            "originalSql": sql_str,
            "safeSql": "",
            "checks": checks,
            "message": "拒绝执行：检测到 MySQL 不支持的语法，已被 Guardrail 拦截。",
        }

    # If warnings exist, the overall result is "warn", otherwise "pass"
    warn_count = sum(1 for c in checks if c["level"] == "warn")
    result_status = "warn" if warn_count > 0 else "pass"
    message_summary = "SQL 审核通过，但包含优化建议。" if result_status == "warn" else "SQL 安全审核通过！"

    return {
        "result": result_status,
        "originalSql": sql_str,
        "safeSql": safe_sql,
        "checks": checks,
        "message": message_summary,
    }
