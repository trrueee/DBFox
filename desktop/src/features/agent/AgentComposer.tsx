import { useState, useCallback } from "react";
import { Send, AtSign, Slash } from "lucide-react";
import type { AgentWorkspaceContext } from "../../lib/api";

interface AgentComposerProps {
  disabled?: boolean;
  placeholder?: string;
  workspaceContext?: AgentWorkspaceContext | null;
  onSubmit: (question: string, workspaceContext?: AgentWorkspaceContext | null) => void;
}

const SLASH_COMMANDS = [
  { cmd: "/explain", label: "解释 SQL" },
  { cmd: "/fix", label: "修复错误" },
  { cmd: "/optimize", label: "优化查询" },
  { cmd: "/chart", label: "生成图表" },
  { cmd: "/export", label: "导出数据" },
  { cmd: "/schema", label: "查看表结构" },
];

export function AgentComposer({
  disabled,
  placeholder = "问 DataBox：生成 SQL、解释结果、修复错误…",
  workspaceContext,
  onSubmit,
}: AgentComposerProps) {
  const [question, setQuestion] = useState("");
  const [focused, setFocused] = useState(false);
  const [showCommands, setShowCommands] = useState(false);
  const [showMentions, setShowMentions] = useState(false);

  const handleSubmit = useCallback(
    (event: React.FormEvent) => {
      event.preventDefault();
      const trimmed = question.trim();
      if (!trimmed) return;
      onSubmit(trimmed, workspaceContext);
      setQuestion("");
      setShowCommands(false);
      setShowMentions(false);
    },
    [question, workspaceContext, onSubmit],
  );

  const handleChange = (value: string) => {
    setQuestion(value);
    setShowCommands(value.endsWith("/") || value === "/");
    setShowMentions(value.endsWith("@"));
  };

  const applyCommand = (cmd: string) => {
    const parts = question.split("/");
    parts.pop();
    setQuestion(parts.join("/") + cmd + " ");
    setShowCommands(false);
  };

  const contextTables = workspaceContext?.selected_table_names || [];
  const contextSql = Boolean(workspaceContext?.active_sql || workspaceContext?.selected_sql);
  const contextResult = Boolean(workspaceContext?.last_query_result_preview);

  const mentionOptions = [
    ...contextTables.map((t) => ({ label: `表: ${t}`, value: `table:${t}` })),
    ...(contextSql ? [{ label: "当前 SQL", value: "sql" }] : []),
    ...(contextResult ? [{ label: "最近结果", value: "result" }] : []),
  ];

  return (
    <div className="px-3 py-2 border-t border-[hsl(var(--border))] bg-[hsl(var(--secondary))] shrink-0">
      {/* Dropdown: slash commands */}
      {showCommands && (
        <div className="mb-1 rounded border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-sm overflow-hidden">
          {SLASH_COMMANDS.map((c) => (
            <button
              key={c.cmd}
              type="button"
              className="flex items-center gap-2 w-full px-3 py-1.5 text-left text-[0.72rem] text-[hsl(var(--foreground))] hover:bg-[hsl(var(--accent))] transition-colors border-none bg-transparent cursor-pointer font-sans"
              onClick={() => applyCommand(c.cmd)}
            >
              <Slash size={11} className="text-[hsl(var(--primary))]" />
              <span className="font-medium">{c.cmd}</span>
              <span className="ml-auto text-[0.62rem] text-[hsl(var(--muted-foreground))]">{c.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* Dropdown: @mentions */}
      {showMentions && mentionOptions.length > 0 && (
        <div className="mb-1 rounded border border-[hsl(var(--border))] bg-[hsl(var(--card))] shadow-sm overflow-hidden">
          {mentionOptions.map((m) => (
            <button
              key={m.value}
              type="button"
              className="flex items-center gap-2 w-full px-3 py-1.5 text-left text-[0.72rem] text-[hsl(var(--foreground))] hover:bg-[hsl(var(--accent))] transition-colors border-none bg-transparent cursor-pointer font-sans"
              onClick={() => {
                const parts = question.split("@");
                parts.pop();
                setQuestion(parts.join("@") + "@" + m.value + " ");
                setShowMentions(false);
              }}
            >
              <AtSign size={11} className="text-[hsl(var(--primary))]" />
              <span>{m.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* Input form */}
      <form
        onSubmit={handleSubmit}
        className={`flex items-center gap-2 px-3 py-1.5 rounded border transition-colors bg-[hsl(var(--card))] ${
          focused
            ? "border-[hsl(var(--primary))] ring-2 ring-[hsl(var(--primary)/0.15)]"
            : "border-[hsl(var(--border))]"
        }`}
      >
        <span className="shrink-0 flex items-center">
          <svg
            width="14" height="14" viewBox="0 0 24 24" fill="none"
            stroke={focused ? "hsl(var(--primary))" : "hsl(var(--muted-foreground))"}
            strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"
          >
            <path d="M12 3L14 8L19 10L14 12L12 17L10 12L5 10L10 8L12 3Z" />
            <path d="M19 15L20 17L22 18L20 19L19 21L18 19L16 18L18 17L19 15Z" opacity="0.5" />
          </svg>
        </span>
        <input
          value={question}
          disabled={disabled}
          placeholder={placeholder}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            setFocused(false);
            setTimeout(() => { setShowCommands(false); setShowMentions(false); }, 200);
          }}
          onChange={(e) => handleChange(e.target.value)}
          className="flex-1 min-w-0 border-none outline-none bg-transparent text-[0.78rem] text-[hsl(var(--foreground))] placeholder:text-[hsl(var(--muted-foreground))] font-sans py-1 disabled:opacity-50"
        />
        <button
          className="flex items-center justify-center w-7 h-7 rounded border-none bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] cursor-pointer shrink-0 transition-colors hover:brightness-110 disabled:bg-[hsl(var(--border))] disabled:cursor-not-allowed"
          disabled={disabled || !question.trim()}
          type="submit"
        >
          <Send size={12} />
        </button>
      </form>

      {/* Hint row */}
      <div className="flex gap-3 pt-1 px-1 text-[0.58rem] text-[hsl(var(--muted-foreground))] font-sans select-none">
        <span className="flex items-center gap-1"><Slash size={9} />命令</span>
        <span className="flex items-center gap-1"><AtSign size={9} />引用表/字段</span>
        {question.trim().length > 0 && (
          <span className="ml-auto font-mono">{question.trim().length}</span>
        )}
      </div>
    </div>
  );
}
