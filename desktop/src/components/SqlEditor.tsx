import Editor, { type OnMount } from "@monaco-editor/react";

interface SqlEditorProps {
  value: string;
  onChange: (value: string) => void;
}

export function SqlEditor({ value, onChange }: SqlEditorProps) {
  const handleMount: OnMount = (editor, monaco) => {
    editor.focus();

    // Define light lab theme
    monaco.editor.defineTheme("lightLab", {
      base: "vs",
      inherit: true,
      rules: [
        { token: "keyword", foreground: "2D3B8C", fontStyle: "bold" },
        { token: "string", foreground: "0D7377" },
        { token: "number", foreground: "B45309" },
        { token: "comment", foreground: "8E8F92", fontStyle: "italic" },
        { token: "operator", foreground: "5C5D60" },
        { token: "identifier", foreground: "1A1A1C" },
        { token: "type", foreground: "2E7D32" },
        { token: "function", foreground: "4A5BC0" },
        { token: "delimiter", foreground: "5C5D60" },
      ],
      colors: {
        "editor.background": "#FAF9F6",
        "editor.foreground": "#1A1A1C",
        "editor.lineHighlightBackground": "#F3F2EE",
        "editor.selectionBackground": "#E8EAFA",
        "editor.inactiveSelectionBackground": "#F3F2EE",
        "editorCursor.foreground": "#2D3B8C",
        "editorLineNumber.foreground": "#8E8F92",
        "editorLineNumber.activeForeground": "#2D3B8C",
        "editor.selectionHighlightBackground": "#E8EAFA",
        "editorBracketMatch.background": "#E8EAFA",
        "editorBracketMatch.border": "#2D3B8C",
      },
    });

    monaco.editor.setTheme("lightLab");

    monaco.languages.registerCompletionItemProvider("sql", {
      provideCompletionItems: (model: any, position: any) => {
        const word = model.getWordUntilPosition(position);
        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        };
        const suggestions: any[] = [
          ...SQL_KEYWORDS.map((kw) => ({
            label: kw,
            kind: monaco.languages.CompletionItemKind.Keyword,
            insertText: kw,
            range,
          })),
          ...SQL_FUNCTIONS.map((fn) => ({
            label: fn,
            kind: monaco.languages.CompletionItemKind.Function,
            insertText: fn,
            range,
          })),
        ];
        return { suggestions };
      },
    });
  };

  return (
    <div className="select-text" style={{ height: "100%", userSelect: "text" }}>
      <Editor
        height="100%"
        defaultLanguage="sql"
        value={value}
        onChange={(v) => onChange(v ?? "")}
        onMount={handleMount}
        options={{
          fontSize: 13.5,
          fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', Consolas, monospace",
          fontLigatures: true,
          lineNumbers: "on",
          minimap: { enabled: false },
          scrollBeyondLastLine: false,
          wordWrap: "on",
          padding: { top: 10, bottom: 10 },
          tabSize: 2,
          automaticLayout: true,
          bracketPairColorization: { enabled: true },
          matchBrackets: "always",
          autoClosingBrackets: "always",
          autoClosingQuotes: "always",
          formatOnPaste: true,
          suggest: { showKeywords: true, showSnippets: true },
          folding: true,
          lineDecorationsWidth: 6,
          lineNumbersMinChars: 4,
          glyphMargin: false,
          renderLineHighlight: "line",
          cursorBlinking: "smooth",
          cursorSmoothCaretAnimation: "on",
          smoothScrolling: true,
        }}
      />
    </div>
  );
}

const SQL_KEYWORDS = [
  "SELECT", "FROM", "WHERE", "AND", "OR", "NOT", "IN", "EXISTS",
  "JOIN", "LEFT JOIN", "RIGHT JOIN", "INNER JOIN", "OUTER JOIN",
  "ON", "AS", "DISTINCT", "ALL", "UNION", "EXCEPT", "INTERSECT",
  "GROUP BY", "ORDER BY", "HAVING", "LIMIT", "OFFSET",
  "INSERT INTO", "VALUES", "UPDATE", "SET", "DELETE",
  "CREATE TABLE", "ALTER TABLE", "DROP TABLE", "TRUNCATE",
  "INDEX", "PRIMARY KEY", "FOREIGN KEY", "REFERENCES",
  "ASC", "DESC", "NULLS FIRST", "NULLS LAST",
  "IS NULL", "IS NOT NULL", "BETWEEN", "LIKE", "ILIKE",
  "TRUE", "FALSE", "CASE", "WHEN", "THEN", "ELSE", "END",
  "CAST", "COALESCE", "NULLIF",
  "WITH", "RECURSIVE", "OVER", "PARTITION BY", "ROW_NUMBER",
  "CROSS JOIN", "NATURAL JOIN", "USING",
];

const SQL_FUNCTIONS = [
  "COUNT", "SUM", "AVG", "MIN", "MAX",
  "ROUND", "FLOOR", "CEIL", "CEILING", "ABS",
  "UPPER", "LOWER", "LENGTH", "TRIM", "SUBSTRING", "REPLACE", "CONCAT",
  "NOW", "CURDATE", "CURTIME", "DATE", "YEAR", "MONTH", "DAY",
  "DATEDIFF", "DATE_ADD", "DATE_SUB", "DATE_FORMAT",
  "IF", "IFNULL", "COALESCE", "NULLIF",
  "GROUP_CONCAT", "JSON_EXTRACT", "JSON_UNQUOTE",
];
