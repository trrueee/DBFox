from __future__ import annotations

from typing import Final, cast

import sqlglot
from sqlglot import exp

from engine.sql.dialect_context import DialectContext
from engine.app.safe_errors import FixedErrorCode, fixed_error_message
from engine.sql.sql_backed_view import (
    SqlBackedFilter,
    SqlBackedSort,
    SqlBackedViewError,
    build_sql_backed_page_sql,
)
from engine.sql.result_view.models import (
    ResultPageQuery,
    ResultViewError,
    ResultViewQuery,
    VerifiedResultSource,
)


class ResultViewCompiler:
    def build_view_sql(
        self,
        query: ResultViewQuery,
        source: VerifiedResultSource,
        ctx: DialectContext,
        *,
        limit: int | None,
        offset: int | None,
    ) -> str:
        try:
            derived = build_sql_backed_page_sql(
                base_sql=source.safe_sql,
                dialect=ctx.sqlglot_dialect,
                columns=source.column_names,
                filters=[SqlBackedFilter.model_validate(item.model_dump()) for item in query.filters],
                search=query.search,
                searchable_columns=source.column_names,
                sorts=[SqlBackedSort.model_validate(item.model_dump()) for item in query.sort],
                limit=limit,
                offset=offset,
            )
            return derived.sql
        except SqlBackedViewError as exc:
            safe_code = _SQL_BACKED_ERROR_CODES.get(
                exc.code,
                FixedErrorCode.DERIVED_SQL_BUILD_FAILED,
            )
            raise ResultViewError(
                safe_code.value,
                fixed_error_message(safe_code),
            ) from None
        except Exception:
            raise ResultViewError(
                FixedErrorCode.DERIVED_SQL_BUILD_FAILED.value,
                fixed_error_message(FixedErrorCode.DERIVED_SQL_BUILD_FAILED),
            ) from None

    def build_page_sql(
        self,
        query: ResultPageQuery,
        source: VerifiedResultSource,
        ctx: DialectContext,
    ) -> str:
        return self.build_view_sql(
            query,
            source,
            ctx,
            limit=query.page_size + 1,
            offset=(query.page - 1) * query.page_size,
        )

    def build_count_sql(
        self,
        query: ResultPageQuery,
        source: VerifiedResultSource,
        ctx: DialectContext,
    ) -> str:
        source_sql = self.build_view_sql(query, source, ctx, limit=None, offset=None)
        try:
            parsed_base = sqlglot.parse_one(source_sql, read=ctx.sqlglot_dialect)
            if not isinstance(parsed_base, exp.Select):
                raise ResultViewError(
                    FixedErrorCode.COUNT_SQL_BUILD_FAILED.value,
                    fixed_error_message(FixedErrorCode.COUNT_SQL_BUILD_FAILED),
                )
            base_expr = cast(exp.Select, parsed_base)
            return (
                sqlglot.select("COUNT(*)")
                .from_(base_expr.subquery("dbfox_count"))
                .sql(dialect=ctx.sqlglot_dialect)
            )
        except ResultViewError:
            raise
        except Exception:
            raise ResultViewError(
                FixedErrorCode.COUNT_SQL_BUILD_FAILED.value,
                fixed_error_message(FixedErrorCode.COUNT_SQL_BUILD_FAILED),
            ) from None

    def build_export_sql(
        self,
        query: ResultViewQuery,
        source: VerifiedResultSource,
        ctx: DialectContext,
    ) -> str:
        return self.build_view_sql(query, source, ctx, limit=None, offset=None)


_SQL_BACKED_ERROR_CODES: Final[dict[str, FixedErrorCode]] = {
    FixedErrorCode.SOURCE_SQL_VALIDATION_FAILED.value: FixedErrorCode.SOURCE_SQL_VALIDATION_FAILED,
    FixedErrorCode.FILTER_COLUMN_NOT_ALLOWED.value: FixedErrorCode.FILTER_COLUMN_NOT_ALLOWED,
    FixedErrorCode.SORT_COLUMN_NOT_ALLOWED.value: FixedErrorCode.SORT_COLUMN_NOT_ALLOWED,
    FixedErrorCode.FILTER_OPERATOR_NOT_ALLOWED.value: FixedErrorCode.FILTER_OPERATOR_NOT_ALLOWED,
}
