import { useMemo } from "react";
import "./ArtifactViews.css";
import { formatSqlForDisplay } from "./sqlDisplayFormatter";
import { tokenizeSql } from "./sqlTokenizer";

interface SqlCodeBlockProps {
  sql: string;
  dialect?: string;
  className?: string;
  ariaLabel?: string;
}

export function SqlCodeBlock({ sql, dialect, className, ariaLabel = "SQL 代码" }: SqlCodeBlockProps) {
  const classNames = ["sql-code-block", className].filter(Boolean).join(" ");
  const displaySql = useMemo(() => formatSqlForDisplay(sql, dialect), [dialect, sql]);

  return (
    <pre className={classNames} aria-label={ariaLabel} tabIndex={0}>
      <code>
        {tokenizeSql(displaySql).map((token, index) => (
          <span key={`${index}-${token.kind}`} className={`sql-token sql-token-${token.kind}`}>
            {token.text}
          </span>
        ))}
      </code>
    </pre>
  );
}
