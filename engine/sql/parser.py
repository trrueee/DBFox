from functools import lru_cache
import sqlglot
from sqlglot import exp

def normalize_dialect(dialect_name: str | None) -> str:
    """Normalize user-provided or database-specific dialect name to sqlglot's standard name."""
    if not dialect_name:
        return "mysql"
    dialect_lower = dialect_name.lower()
    if "postgres" in dialect_lower:
        return "postgres"
    if "sqlite" in dialect_lower:
        return "sqlite"
    if "duckdb" in dialect_lower:
        return "duckdb"
    return "mysql"

@lru_cache(maxsize=256)
def parse_sql_cached(sql_str: str, dialect: str) -> list[exp.Expression]:
    """Parse SQL string with cached results using the normalized dialect."""
    # SQLGlot represents comments after a terminal semicolon as a standalone
    # ``Semicolon`` expression. It is not an executable statement and must not
    # make the single-statement safety contract report a false positive.
    return [
        expression
        for expression in sqlglot.parse(sql_str, read=dialect)
        if not isinstance(expression, exp.Semicolon)
    ]

def parse_sql(sql_str: str, dialect: str | None = None) -> list[exp.Expression]:
    """Parse SQL string into a list of expressions using AST caching."""
    normalized = normalize_dialect(dialect)
    return parse_sql_cached(sql_str, normalized)
