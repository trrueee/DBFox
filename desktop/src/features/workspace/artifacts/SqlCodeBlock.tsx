import "./ArtifactViews.css";
import { tokenizeSql } from "./sqlTokenizer";

interface SqlCodeBlockProps {
  sql: string;
  className?: string;
  ariaLabel?: string;
}

export function SqlCodeBlock({ sql, className, ariaLabel = "SQL 代码" }: SqlCodeBlockProps) {
  const classNames = ["sql-code-block", className].filter(Boolean).join(" ");

  return (
    <pre className={classNames} aria-label={ariaLabel}>
      <code>
        {tokenizeSql(sql).map((token, index) => (
          <span key={`${index}-${token.kind}`} className={`sql-token sql-token-${token.kind}`}>
            {token.text}
          </span>
        ))}
      </code>
    </pre>
  );
}
