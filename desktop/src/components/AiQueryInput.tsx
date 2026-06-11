import { useState } from "react";
import { Settings, Sparkles } from "lucide-react";

interface AiQueryInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  loading: boolean;
  onToggleConfig: () => void;
}

const SUGGESTIONS = [
  "最近30天的订单总金额",
  "各分类商品的销量排名",
  "本月新增用户数",
  "客户地域分布统计",
  "每日活跃用户趋势",
];

export function AiQueryInput({ value, onChange, onSubmit, loading, onToggleConfig }: AiQueryInputProps) {
  const [focused, setFocused] = useState(false);
  const activeSuggestions = SUGGESTIONS;


  return (
    <div
      className="bg-card border border-border rounded-lg"
      style={{
        padding: 20,
        borderColor: focused ? "var(--accent-indigo)" : undefined,
        transition: "border-color 0.2s",
        position: "relative",
        overflow: "hidden",
      }}
    >
      {/* Subtle indigo accent bar at top */}
      <div
        style={{
          position: "absolute",
          top: 0,
          left: 0,
          right: 0,
          height: 3,
          background: "linear-gradient(90deg, var(--accent-indigo), var(--accent-teal))",
          opacity: focused ? 1 : 0.3,
          transition: "opacity 0.3s",
        }}
      />

      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 12 }}>
        <Sparkles size={16} style={{ color: "var(--accent-indigo)" }} />
        <span style={{ fontWeight: 600, fontSize: "0.9rem" }}>AI 智能问数</span>
        <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
          用自然语言描述你想查询的数据
        </span>
      </div>

      <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
        <textarea
          className="h-9 w-full rounded-sm border border-input bg-transparent px-3 py-1 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
          placeholder="例如：查询上个月销售额最高的 10 个商品..."
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSubmit();
            }
          }}
          rows={3}
          style={{ flex: 1, fontSize: "0.92rem", lineHeight: 1.7, resize: "vertical" }}
        />
        <div style={{ display: "flex", flexDirection: "column", gap: 6, flexShrink: 0 }}>
          <button
            className="inline-flex items-center gap-1.5 px-4 py-1.5 text-xs font-semibold bg-primary text-primary-foreground rounded-sm cursor-pointer border-none hover:brightness-110 transition-colors"
            onClick={onSubmit}
            disabled={loading || !value.trim()}
            style={{
              background: loading ? undefined : "linear-gradient(135deg, #2D3B8C, #4A5BC0)",
              padding: "10px 18px",
              position: "relative",
            }}
          >
            <Sparkles size={15} className={loading ? "animate-pulse-ring" : ""} />
            {loading ? "生成中..." : "生成 SQL"}
          </button>
          <button
            className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
            onClick={onToggleConfig}
            style={{ fontSize: "0.72rem" }}
          >
            <Settings size={11} />
            LLM 配置
          </button>
        </div>
      </div>

      {/* Suggestion chips */}
      {!value.trim() && !loading && (
        <div style={{ display: "flex", gap: 6, marginTop: 10, flexWrap: "wrap" }}>
          {activeSuggestions.map((s) => (
            <button
              key={s}
              className="inline-flex items-center gap-1 px-2 py-0.5 text-xs font-medium text-muted-foreground bg-transparent border border-border rounded-sm cursor-pointer hover:bg-accent hover:text-foreground transition-colors"
              onClick={() => onChange(s)}
              style={{
                fontSize: "0.76rem",
                background: "var(--bg-secondary)",
                borderRadius: 9999,
                padding: "4px 12px",
                border: "1px solid var(--border-light)",
              }}
            >
              {s}
            </button>
          ))}
        </div>
      )}

      {/* Character count */}
      {value.trim() && (
        <div style={{ marginTop: 8, fontSize: "0.72rem", color: "var(--text-muted)", textAlign: "right" }}>
          {value.length} 字符
        </div>
      )}
    </div>
  );
}
