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

  const applyMention = (mention: string) => {
    const parts = question.split("@");
    parts.pop();
    setQuestion(parts.join("@") + "@" + mention + " ");
    setShowMentions(false);
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
    <div className="agent-composer">
      {/* Slash command dropdown */}
      {showCommands && (
        <div className="composer-dropdown">
          {SLASH_COMMANDS.map((c) => (
            <button
              key={c.cmd}
              type="button"
              className="composer-dropdown-item"
              onClick={() => applyCommand(c.cmd)}
            >
              <Slash size={11} />
              <span>{c.cmd}</span>
              <span className="composer-dropdown-label">{c.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* @mention dropdown */}
      {showMentions && mentionOptions.length > 0 && (
        <div className="composer-dropdown">
          {mentionOptions.map((m) => (
            <button
              key={m.value}
              type="button"
              className="composer-dropdown-item"
              onClick={() => applyMention(m.value)}
            >
              <AtSign size={11} />
              <span>{m.label}</span>
            </button>
          ))}
        </div>
      )}

      {/* Input form */}
      <form
        onSubmit={handleSubmit}
        className={`composer-form ${focused ? "composer-focused" : ""}`}
      >
        <span className="composer-icon">
          <SparklesIcon focused={focused} />
        </span>
        <input
          value={question}
          disabled={disabled}
          placeholder={placeholder}
          onFocus={() => setFocused(true)}
          onBlur={() => {
            setFocused(false);
            // Delay hiding dropdowns for click handling
            setTimeout(() => {
              setShowCommands(false);
              setShowMentions(false);
            }, 200);
          }}
          onChange={(e) => handleChange(e.target.value)}
          className="composer-input"
        />
        <button
          className="composer-send"
          disabled={disabled || !question.trim()}
          type="submit"
        >
          <Send size={13} />
        </button>
      </form>

      {/* Hint row */}
      <div className="composer-hint">
        <span>
          <Slash size={10} /> 命令
        </span>
        <span>
          <AtSign size={10} /> 引用表/字段
        </span>
        {question.trim().length > 0 && (
          <span style={{ marginLeft: "auto" }}>{question.trim().length}</span>
        )}
      </div>
    </div>
  );
}

function SparklesIcon({ focused }: { focused: boolean }) {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 24 24"
      fill="none"
      stroke={focused ? "var(--accent-primary)" : "var(--text-muted)"}
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M12 3L14 8L19 10L14 12L12 17L10 12L5 10L10 8L12 3Z" />
      <path d="M19 15L20 17L22 18L20 19L19 21L18 19L16 18L18 17L19 15Z" opacity="0.5" />
    </svg>
  );
}
