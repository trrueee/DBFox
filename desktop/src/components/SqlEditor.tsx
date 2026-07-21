import { useEffect, useMemo, useRef, useState } from "react";
import Editor, { type Monaco, type OnMount } from "@monaco-editor/react";
import "./SqlEditor.css";

export interface SchemaColumnMeta {
  name: string;
  type: string;
  is_pk: boolean;
  is_fk: boolean;
  comment: string;
}

export interface SchemaTableMeta {
  id: string;
  label: string; // table name
  comment: string; // table comment
  fields: SchemaColumnMeta[];
}

interface SqlEditorProps {
  value: string;
  onChange: (value: string) => void;
  schemaTables?: SchemaTableMeta[];
  disabled?: boolean;
  className?: string;
  appearance?: "light" | "dark";
  ariaLabel?: string;
  testId?: string;
  onExecute?: (sql?: string) => void;
  onSelectionChange?: (selectedSql: string) => void;
}

type Disposable = { dispose: () => void };
type MonacoEditor = Parameters<OnMount>[0];
type SqlPosition = { lineNumber: number; column: number };
type SqlWord = { startColumn: number; endColumn: number };
type SqlModel = {
  getWordUntilPosition: (position: SqlPosition) => SqlWord;
  getLineContent: (lineNumber: number) => string;
  getValue: () => string;
};
type CompletionRange = {
  startLineNumber: number;
  endLineNumber: number;
  startColumn: number;
  endColumn: number;
};
type CompletionSuggestion = {
  label: string;
  kind: number;
  insertText: string;
  detail?: string;
  documentation?: string;
  sortText?: string;
  range: CompletionRange;
};

export function SqlEditor({
  value,
  onChange,
  schemaTables = [],
  disabled = false,
  className,
  appearance = "light",
  ariaLabel = "SQL 编辑器",
  testId,
  onExecute,
  onSelectionChange,
}: SqlEditorProps) {
  const [monacoInstance, setMonacoInstance] = useState<Monaco | null>(null);
  const providerRef = useRef<Disposable | null>(null);
  const selectionListenerRef = useRef<Disposable | null>(null);
  const executeRef = useRef(onExecute);
  const selectionChangeRef = useRef(onSelectionChange);

  useEffect(() => {
    executeRef.current = onExecute;
  }, [onExecute]);

  useEffect(() => {
    selectionChangeRef.current = onSelectionChange;
  }, [onSelectionChange]);

  const themeName = appearance === "dark" ? "dbfoxDark" : "lightLab";

  // Precompute escaped table names and regex patterns once when schemaTables changes
  const tablePatterns = useMemo(() =>
    schemaTables.map((t) => {
      const escaped = t.label.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");
      return {
        table: t,
        escaped,
        nameRegex: new RegExp(`\\b${escaped}\\b`, "i"),
        aliasRegex: new RegExp(`\\b${escaped}\\b\\s+(?:AS\\s+)?([a-zA-Z0-9_-]+)\\b`, "i"),
      };
    }),
  [schemaTables]);

  const handleMount: OnMount = (editor, monaco) => {
    editor.focus();
    defineSqlEditorThemes(monaco);
    monaco.editor.setTheme(themeName);
    setMonacoInstance(monaco);

    const notifySelectionChange = () => {
      selectionChangeRef.current?.(readSelectedSql(editor));
    };

    selectionListenerRef.current?.dispose();
    selectionListenerRef.current = editor.onDidChangeCursorSelection(notifySelectionChange);

    const executeCurrentSql = () => {
      const selectedSql = readSelectedSql(editor);
      executeRef.current?.(selectedSql || editor.getValue());
    };

    editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, executeCurrentSql);
    editor.addCommand(monaco.KeyCode.F9, executeCurrentSql);
    notifySelectionChange();
  };

  useEffect(() => () => {
    selectionListenerRef.current?.dispose();
    selectionListenerRef.current = null;
  }, []);

  useEffect(() => {
    if (!monacoInstance) return;

    // Dispose of any previous provider to avoid duplicate registers
    if (providerRef.current) {
      providerRef.current.dispose();
      providerRef.current = null;
    }

    providerRef.current = monacoInstance.languages.registerCompletionItemProvider("sql", {
      triggerCharacters: [".", " "],
      provideCompletionItems: (model: SqlModel, position: SqlPosition) => {
        const word = model.getWordUntilPosition(position);
        const lineContent = model.getLineContent(position.lineNumber);
        const textUntilCursor = lineContent.substring(0, position.column - 1);

        const range = {
          startLineNumber: position.lineNumber,
          endLineNumber: position.lineNumber,
          startColumn: word.startColumn,
          endColumn: word.endColumn,
        };

        // Helper to resolve alias to corresponding table
        const resolveAliasToTable = (sql: string, alias: string): SchemaTableMeta | null => {
          const cleanAlias = alias.trim().toLowerCase();
          if (!cleanAlias) return null;

          const escapedAlias = cleanAlias.replace(/[-/\\^$*+?.()|[\]{}]/g, "\\$&");

          for (const tp of tablePatterns) {
            const pattern = new RegExp(`\\b(?:FROM|JOIN|UPDATE|INTO|MERGE)\\s+[\`"]?${tp.escaped}[\`"]?\\s+(?:AS\\s+)?${escapedAlias}\\b`, "i");
            const patternSimple = new RegExp(`[\`"]?${tp.escaped}[\`"]?\\s+(?:AS\\s+)?${escapedAlias}\\b`, "i");
            if (pattern.test(sql) || patternSimple.test(sql)) {
              return tp.table;
            }
          }
          return schemaTables.find((t) => t.label.toLowerCase() === cleanAlias) || null;
        };

        // 1. Column Trigger (Dotted notation: e.g., users. or u.)
        const dotMatch = textUntilCursor.match(/([a-zA-Z0-9_]+)\.$/);
        if (dotMatch) {
          const aliasOrTable = dotMatch[1];
          const targetTable = resolveAliasToTable(model.getValue(), aliasOrTable);

          if (targetTable && targetTable.fields) {
            const columnSuggestions = targetTable.fields.map((col) => {
              let detail = `[Column] ${col.type}`;
              if (col.is_pk) detail += " | 🔑 PK";
              if (col.is_fk) detail += " | 🔗 FK";

              return {
                label: col.name,
                kind: monacoInstance.languages.CompletionItemKind.Property,
                insertText: col.name,
                detail,
                documentation: col.comment || undefined,
                range,
              };
            });
            return { suggestions: columnSuggestions };
          }
        }

        // 2. JOIN ... ON Trigger
        // Matches e.g. "JOIN users AS u ON " or "join departments ON  "
        const onMatch = textUntilCursor.match(/(?:JOIN|LEFT JOIN|RIGHT JOIN|INNER JOIN|CROSS JOIN)\s+([`"]?[a-zA-Z0-9_-]+[`"]?)(?:\s+(?:AS\s+)?([a-zA-Z0-9_-]+))?\s+ON\s*$/i);
        if (onMatch) {
          const joinedTableRaw = onMatch[1].replace(/[`"]/g, "");
          const joinedAlias = onMatch[2];

          const joinedTable = schemaTables.find(
            (t) => t.label.toLowerCase() === joinedTableRaw.toLowerCase()
          );

          if (joinedTable && joinedTable.fields) {
            // Find all tables that appear in the SQL before the cursor
            const activeTablesInQuery: Array<{ table: SchemaTableMeta; alias?: string }> = [];

            for (const tp of tablePatterns) {
              if (tp.nameRegex.test(textUntilCursor)) {
                const aliasMatch = textUntilCursor.match(tp.aliasRegex);
                const alias = aliasMatch ? aliasMatch[1] : undefined;
                activeTablesInQuery.push({ table: tp.table, alias });
              }
            }

            const onSuggestions: CompletionSuggestion[] = [];
            for (const other of activeTablesInQuery) {
              if (other.table.label.toLowerCase() === joinedTable.label.toLowerCase()) continue;

              for (const col1 of joinedTable.fields) {
                for (const col2 of other.table.fields) {
                  let isMatch = false;
                  let priority = 1;

                  if (
                    col1.name.toLowerCase() === col2.name.toLowerCase() &&
                    col1.name.toLowerCase().endsWith("_id")
                  ) {
                    isMatch = true;
                    priority = 3;
                  } else if (
                    col1.name.toLowerCase() === `${other.table.label.toLowerCase()}_id` &&
                    col2.is_pk
                  ) {
                    isMatch = true;
                    priority = 4;
                  } else if (
                    col2.name.toLowerCase() === `${joinedTable.label.toLowerCase()}_id` &&
                    col1.is_pk
                  ) {
                    isMatch = true;
                    priority = 4;
                  }

                  if (isMatch) {
                    const joinedName = joinedAlias || joinedTable.label;
                    const otherName = other.alias || other.table.label;

                    const suggestionText = `${joinedName}.${col1.name} = ${otherName}.${col2.name}`;

                    onSuggestions.push({
                      label: `${joinedName}.${col1.name} = ${otherName}.${col2.name}`,
                      kind: monacoInstance.languages.CompletionItemKind.Snippet,
                      insertText: suggestionText,
                      detail: `[Join Condition] ${joinedTable.label} ⟷ ${other.table.label} (${
                        priority === 4 ? "🔑 PK-FK Match" : "Name Match"
                      })`,
                      documentation: `Automatically inferred join matching condition based on schema definitions.`,
                      sortText: `0_${5 - priority}`,
                      range,
                    });
                  }
                }
              }
            }

            if (onSuggestions.length > 0) {
              return { suggestions: onSuggestions };
            }
          }
        }

        // 3. Default suggestions (Tables + Keywords + Functions)
        const tableSuggestions = schemaTables.map((t) => ({
          label: t.label,
          kind: monacoInstance.languages.CompletionItemKind.Field,
          insertText: t.label,
          detail: `[Table] ${t.comment || ""}`,
          range,
        }));

        const suggestions = [
          ...tableSuggestions,
          ...SQL_KEYWORDS.map((kw) => ({
            label: kw,
            kind: monacoInstance.languages.CompletionItemKind.Keyword,
            insertText: kw,
            range,
          })),
          ...SQL_FUNCTIONS.map((fn) => ({
            label: fn,
            kind: monacoInstance.languages.CompletionItemKind.Function,
            insertText: fn,
            range,
          })),
        ];

        return { suggestions };
      },
    });

    return () => {
      if (providerRef.current) {
        providerRef.current.dispose();
        providerRef.current = null;
      }
    };
  }, [schemaTables, monacoInstance, tablePatterns]);

  const wrapperClassName = [
    "sql-editor",
    `sql-editor--${appearance}`,
    className ?? "select-text",
  ].filter(Boolean).join(" ");

  return (
    <div
      className={wrapperClassName}
      data-testid={testId}
      aria-label={ariaLabel}
    >
      <Editor
        height="100%"
        defaultLanguage="sql"
        beforeMount={defineSqlEditorThemes}
        theme={themeName}
        value={value}
        onChange={(v) => onChange(v ?? "")}
        onMount={handleMount}
        loading={<div className="sql-editor-loading" aria-hidden="true" />}
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
          readOnly: disabled,
          domReadOnly: disabled,
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

function defineSqlEditorThemes(monaco: Monaco) {
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

  monaco.editor.defineTheme("dbfoxDark", {
    base: "vs-dark",
    inherit: true,
    rules: [
      { token: "keyword", foreground: "93C5FD", fontStyle: "bold" },
      { token: "string", foreground: "5EEAD4" },
      { token: "number", foreground: "FDBA74" },
      { token: "comment", foreground: "64748B", fontStyle: "italic" },
      { token: "operator", foreground: "CBD5E1" },
      { token: "identifier", foreground: "DBEAFE" },
      { token: "type", foreground: "86EFAC" },
      { token: "function", foreground: "C4B5FD" },
      { token: "delimiter", foreground: "94A3B8" },
    ],
    colors: {
      "editor.background": "#020617",
      "editor.foreground": "#DBEAFE",
      "editor.lineHighlightBackground": "#0B1120",
      "editor.selectionBackground": "#1D4ED8",
      "editor.inactiveSelectionBackground": "#172554",
      "editorCursor.foreground": "#34D399",
      "editorLineNumber.foreground": "#475569",
      "editorLineNumber.activeForeground": "#93C5FD",
      "editor.selectionHighlightBackground": "#1E3A8A",
      "editorBracketMatch.background": "#172554",
      "editorBracketMatch.border": "#34D399",
    },
  });
}

function readSelectedSql(editor: MonacoEditor) {
  const selection = editor.getSelection();
  const model = editor.getModel();
  if (!selection || !model || selection.isEmpty()) return "";
  return model.getValueInRange(selection).trim();
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
