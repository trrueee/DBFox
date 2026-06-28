import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";

type MarkdownSegment =
  | { type: "markdown"; content: string }
  | { type: "table"; headers: string[]; rows: string[][] };

const MARKDOWN_COMPONENTS: Components = {
  h1: ({ children }) => <h1 className="hifi-md-h1">{children}</h1>,
  h2: ({ children }) => <h2 className="hifi-md-h2">{children}</h2>,
  h3: ({ children }) => <h3 className="hifi-md-h3">{children}</h3>,
  p: ({ children }) => <p className="hifi-md-p">{children}</p>,
  ul: ({ children }) => <ul className="hifi-md-ul">{children}</ul>,
  ol: ({ children }) => <ol className="hifi-md-ol">{children}</ol>,
  li: ({ children }) => <li className="hifi-md-li">{children}</li>,
  strong: ({ children }) => <strong className="hifi-md-strong">{children}</strong>,
  em: ({ children }) => <em className="hifi-md-em">{children}</em>,
  code: ({ children }) => <code className="hifi-md-code">{children}</code>,
  pre: ({ children }) => <pre className="hifi-md-pre">{children}</pre>,
  a: ({ children, href }) => (
    <a href={href} className="hifi-md-link" target="_blank" rel="noopener">
      {children}
    </a>
  ),
  blockquote: ({ children }) => <blockquote className="hifi-md-quote">{children}</blockquote>,
};

const TABLE_CELL_MARKDOWN_COMPONENTS: Components = {
  ...MARKDOWN_COMPONENTS,
  p: ({ children }) => <>{children}</>,
};

export function MarkdownContent({ content, className = "" }: { content: string; className?: string }) {
  const segments = splitMarkdownTables(content);

  return (
    <div className={`hifi-markdown-content ${className}`.trim()}>
      {segments.map((segment, index) => {
        if (segment.type === "table") {
          return <MarkdownTable key={index} headers={segment.headers} rows={segment.rows} />;
        }
        return (
          <ReactMarkdown key={index} components={MARKDOWN_COMPONENTS}>
            {segment.content}
          </ReactMarkdown>
        );
      })}
    </div>
  );
}

export function splitMarkdownTables(markdown: string): MarkdownSegment[] {
  const lines = markdown.split(/\r?\n/);
  const segments: MarkdownSegment[] = [];
  let markdownBuffer: string[] = [];
  let index = 0;

  const flushMarkdown = () => {
    const content = markdownBuffer.join("\n").trim();
    if (content) segments.push({ type: "markdown", content });
    markdownBuffer = [];
  };

  while (index < lines.length) {
    const current = lines[index];
    const next = lines[index + 1];

    if (isTableHeader(current, next)) {
      flushMarkdown();
      const headers = parseTableCells(current);
      index += 2;
      const rows: string[][] = [];

      while (index < lines.length && isTableRow(lines[index])) {
        const row = parseTableCells(lines[index]);
        rows.push(headers.map((_, cellIndex) => row[cellIndex] ?? ""));
        index += 1;
      }

      segments.push({ type: "table", headers, rows });
      continue;
    }

    markdownBuffer.push(current);
    index += 1;
  }

  flushMarkdown();
  return segments;
}

function MarkdownTable({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="hifi-md-table-wrap">
      <table className="hifi-md-table">
        <thead>
          <tr>
            {headers.map((header, index) => (
              <th key={index}>
                <MarkdownTableCell content={header} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {headers.map((_, cellIndex) => (
                <td key={cellIndex}>
                  <MarkdownTableCell content={row[cellIndex] || ""} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function MarkdownTableCell({ content }: { content: string }) {
  const parts = content.split(/<br\s*\/?>/gi);
  return (
    <>
      {parts.map((part, index) => (
        <span key={index} className="hifi-md-table-cell-line">
          {index > 0 && <br />}
          <ReactMarkdown components={TABLE_CELL_MARKDOWN_COMPONENTS}>{part}</ReactMarkdown>
        </span>
      ))}
    </>
  );
}

function isTableHeader(current: string | undefined, next: string | undefined): current is string {
  return Boolean(current && next && isTableRow(current) && isTableSeparator(next));
}

function isTableRow(line: string | undefined): line is string {
  if (!line) return false;
  const trimmed = line.trim();
  return trimmed.includes("|") && trimmed.replace(/\|/g, "").trim().length > 0;
}

function isTableSeparator(line: string): boolean {
  const cells = parseTableCells(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{3,}:?$/.test(cell.replace(/\s/g, "")));
}

function parseTableCells(line: string): string[] {
  let trimmed = line.trim();
  if (trimmed.startsWith("|")) trimmed = trimmed.slice(1);
  if (trimmed.endsWith("|")) trimmed = trimmed.slice(0, -1);
  return trimmed.split("|").map((cell) => cell.trim());
}
