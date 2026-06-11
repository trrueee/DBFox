import React, { useState, useEffect, useRef, useMemo } from "react";
import { Search, CornerDownLeft } from "lucide-react";

export interface CommandItem {
  id: string;
  name: string;
  category: string;
  shortcut?: string;
  icon?: React.ReactNode;
  action: () => void;
}

interface CommandPaletteProps {
  open: boolean;
  onClose: () => void;
  commands: CommandItem[];
}

export const CommandPalette: React.FC<CommandPaletteProps> = ({ open, onClose, commands }) => {
  const [search, setSearch] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [mounted, setMounted] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      setMounted(true);
      setSearch("");
      setSelectedIndex(0);
      requestAnimationFrame(() => inputRef.current?.focus());
    } else if (mounted) {
      const timer = setTimeout(() => setMounted(false), 200);
      return () => clearTimeout(timer);
    }
  }, [open]);

  const filteredCommands = useMemo(() => {
    if (!search.trim()) return commands;
    const query = search.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.name.toLowerCase().includes(query) ||
        cmd.category.toLowerCase().includes(query)
    );
  }, [search, commands]);

  // Group by category
  const grouped = useMemo(() => {
    const map = new Map<string, CommandItem[]>();
    for (const cmd of filteredCommands) {
      const list = map.get(cmd.category) || [];
      list.push(cmd);
      map.set(cmd.category, list);
    }
    return Array.from(map.entries());
  }, [filteredCommands]);

  // Flattened index for keyboard nav
  let flatIndex = 0;
  const flatIndexMap = new Map<number, { cat: string; idx: number }>();
  for (const [cat, items] of grouped) {
    for (let i = 0; i < items.length; i++) {
      flatIndexMap.set(flatIndex, { cat, idx: i });
      flatIndex++;
    }
  }

  useEffect(() => {
    setSelectedIndex(0);
  }, [filteredCommands]);

  useEffect(() => {
    if (!open) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") { e.preventDefault(); onClose(); return; }
      if (e.key === "ArrowDown") { e.preventDefault(); setSelectedIndex((p) => (p + 1) % Math.max(1, flatIndexMap.size)); return; }
      if (e.key === "ArrowUp") { e.preventDefault(); setSelectedIndex((p) => (p - 1 + flatIndexMap.size) % Math.max(1, flatIndexMap.size)); return; }
      if (e.key === "Enter") {
        e.preventDefault();
        const target = flatIndexMap.get(selectedIndex);
        if (target) {
          const item = grouped.find(([c]) => c === target.cat)?.[1][target.idx];
          if (item) { item.action(); onClose(); }
        }
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [open, selectedIndex, flatIndexMap, grouped, onClose]);

  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector(`[data-cmd-index="${selectedIndex}"]`) as HTMLElement | null;
    el?.scrollIntoView({ block: "nearest" });
  }, [selectedIndex]);

  if (!mounted) return null;

  return (
    <div
      style={{
        position: "fixed", inset: 0,
        background: "rgba(15, 23, 42, 0.18)",
        backdropFilter: "blur(6px)",
        WebkitBackdropFilter: "blur(6px)",
        zIndex: 2000,
        display: "flex", justifyContent: "center",
        paddingTop: "14vh",
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: "min(620px, 94vw)",
          maxHeight: "440px",
          background: "var(--bg-surface, #ffffff)",
          borderRadius: 14,
          border: "1px solid var(--border-medium, #e6eaf2)",
          boxShadow: "0 20px 60px rgba(16, 24, 40, 0.12), 0 0 0 1px rgba(16, 24, 40, 0.04)",
          display: "flex", flexDirection: "column",
          overflow: "hidden",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search */}
        <div style={{
          display: "flex", alignItems: "center",
          padding: "12px 16px",
          borderBottom: "1px solid var(--border-subtle, #edf1f7)",
          gap: 10,
          background: "var(--bg-primary, #fafbfc)",
        }}>
          <Search size={15} style={{ color: "var(--text-muted, #98a2b3)", flexShrink: 0 }} />
          <input
            ref={inputRef}
            type="text"
            placeholder="输入指令或进行模糊检索..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{
              flex: 1, border: "none", background: "transparent", outline: "none",
              fontSize: "0.82rem", color: "var(--text-primary, #1f2a44)",
              fontFamily: "inherit",
            }}
          />
          <kbd style={{
            fontSize: "0.62rem", fontFamily: "var(--font-mono, 'Fira Code')",
            color: "var(--text-muted, #98a2b3)",
            background: "var(--bg-subtle, #f3f6fb)",
            border: "1px solid var(--border-subtle, #edf1f7)",
            borderRadius: 4, padding: "1px 6px",
            display: "flex", alignItems: "center", gap: 3,
          }}>
            Esc
          </kbd>
        </div>

        {/* Results */}
        <div ref={listRef} style={{ flex: 1, overflowY: "auto", padding: "8px" }}>
          {grouped.length === 0 ? (
            <div style={{ padding: "32px 20px", textAlign: "center", fontSize: "0.78rem", color: "var(--text-muted)" }}>
              没有找到匹配的指令
            </div>
          ) : (
            grouped.map(([category, items]) => (
              <div key={category} style={{ marginBottom: 4 }}>
                <div style={{
                  padding: "4px 12px 2px",
                  fontSize: "0.62rem", fontWeight: 600,
                  color: "var(--text-muted, #98a2b3)",
                  textTransform: "uppercase", letterSpacing: "0.04em",
                }}>
                  {category}
                </div>
                {items.map((cmd) => {
                  const currentFlat = [...flatIndexMap.entries()].find(([, v]) => v.cat === category && v.idx === items.indexOf(cmd))?.[0] ?? -1;
                  const active = currentFlat === selectedIndex;
                  return (
                    <button
                      key={cmd.id}
                      data-cmd-index={currentFlat}
                      onClick={() => { cmd.action(); onClose(); }}
                      style={{
                        display: "flex", alignItems: "center", width: "100%",
                        border: "none",
                        background: active ? "var(--bg-active, #e8edff)" : "transparent",
                        borderRadius: 8, padding: "9px 12px",
                        cursor: "pointer", textAlign: "left", gap: 10,
                        transition: "background 0.08s",
                      }}
                    >
                      <span style={{
                        display: "flex", alignItems: "center", justifyContent: "center",
                        width: 28, height: 28, borderRadius: 6, flexShrink: 0,
                        background: active ? "rgba(91, 92, 240, 0.1)" : "var(--bg-subtle, #f3f6fb)",
                        color: active ? "var(--accent-indigo, #5b5cf0)" : "var(--text-muted, #98a2b3)",
                      }}>
                        {cmd.icon || <CornerDownLeft size={13} />}
                      </span>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: "0.8rem", fontWeight: active ? 600 : 500, color: active ? "var(--accent-indigo)" : "var(--text-primary)" }}>
                          {cmd.name}
                        </div>
                      </div>
                      {cmd.shortcut && (
                        <kbd style={{
                          fontSize: "0.62rem", fontFamily: "var(--font-mono, 'Fira Code')",
                          color: "var(--text-muted)", background: "var(--bg-subtle)",
                          border: "1px solid var(--border-subtle)", borderRadius: 4,
                          padding: "1px 6px", flexShrink: 0,
                        }}>
                          {cmd.shortcut}
                        </kbd>
                      )}
                    </button>
                  );
                })}
              </div>
            ))
          )}
        </div>

        {/* Footer hint */}
        <div style={{
          padding: "6px 16px", borderTop: "1px solid var(--border-subtle, #edf1f7)",
          fontSize: "0.62rem", color: "var(--text-muted)",
          display: "flex", gap: 16,
          background: "var(--bg-primary, #fafbfc)",
        }}>
          <span>↑↓ 导航</span><span>↵ 打开</span><span>Esc 关闭</span>
        </div>
      </div>
    </div>
  );
};
